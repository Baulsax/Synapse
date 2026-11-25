
import json
import logging
import re
import threading
import time

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from pynput.keyboard import (
    Controller as KeyboardController,
    Key,
    KeyCode,
)
from pynput.mouse import (
    Controller as MouseController,
    Button,
)

from core.app_paths import APP_DATA_DIR


logger = logging.getLogger(__name__)


class MacroEngine(QObject):

    recording_state_changed = Signal(str)
    playback_state_changed = Signal(str)

    actions_changed = Signal(object)
    playback_progress = Signal(int, int)

    error_occurred = Signal(str)

    hotkeys_changed = Signal(object)
    hotkey_capture_started = Signal(str)
    hotkey_capture_finished = Signal(str, object)
    hotkey_capture_rejected = Signal(str)

    MACRO_DIRECTORY = APP_DATA_DIR / "macros"
    HOTKEY_FILE = APP_DATA_DIR / "macro_hotkeys.json"

    FORMAT_VERSION = 1

    HOTKEY_ACTIONS = (
        "record_toggle",
        "playback_toggle",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.keyboard = KeyboardController()
        self.mouse = MouseController()

        self.actions = []

        self.recording_state = "stopped"
        self.playback_state = "stopped"

        self.record_mouse_movement = True

        self._recording_start = None
        self._recording_pause_start = None
        self._recording_paused_duration = 0.0

        self._recording_lock = threading.RLock()
        self._playback_lock = threading.RLock()

        self._playback_thread = None
        self._playback_stop = threading.Event()
        self._playback_resume = threading.Event()
        self._playback_resume.set()

        self._playback_speed = 1.0
        self._repeat_count = 1

        self.hotkey_playback_speed = 1.0
        self.hotkey_repeat_count = 1

        self._held_keys = set()
        self._held_buttons = set()

        self._hotkeys = {
            "record_toggle": None,
            "playback_toggle": None,
        }

        self._hotkey_capture_action = None
        self._suppressed_inputs = set()

        self.MACRO_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        self._load_hotkeys()

    # ======================================
    # RECORDING
    # ======================================

    def start_recording(self, clear=True):
        with self._recording_lock:

            if self.recording_state != "stopped":
                return False

            if self.playback_state != "stopped":
                return False

            if clear:
                self.actions.clear()

            self._recording_start = time.time()
            self._recording_pause_start = None
            self._recording_paused_duration = 0.0

            self.recording_state = "recording"

        self.recording_state_changed.emit("recording")
        self.actions_changed.emit(list(self.actions))

        logger.info("Macro recording started.")

        return True

    def pause_recording(self):
        with self._recording_lock:

            if self.recording_state != "recording":
                return False

            self._recording_pause_start = time.time()
            self.recording_state = "paused"

        self.recording_state_changed.emit("paused")

        return True

    def resume_recording(self):
        with self._recording_lock:

            if self.recording_state != "paused":
                return False

            if self._recording_pause_start is not None:
                self._recording_paused_duration += (
                    time.time() - self._recording_pause_start
                )

            self._recording_pause_start = None
            self.recording_state = "recording"

        self.recording_state_changed.emit("recording")

        return True

    def stop_recording(self):
        with self._recording_lock:

            if self.recording_state == "stopped":
                return False

            if self.recording_state == "paused":
                if self._recording_pause_start is not None:
                    self._recording_paused_duration += (
                        time.time() - self._recording_pause_start
                    )

            self._recording_pause_start = None
            self.recording_state = "stopped"

        self.recording_state_changed.emit("stopped")
        self.actions_changed.emit(list(self.actions))

        logger.info(
            "Macro recording stopped. Recorded %s actions.",
            len(self.actions)
        )

        return True

    def handle_raw_input(self, event):
        """
        Receive original input events from the shared InputManager.

        Hotkey handling happens before recording, so the hotkey itself
        is not added to the macro timeline.
        """

        input_type = str(
            getattr(event, "input_type", "")
        ).lower()

        control = str(
            getattr(event, "control", "")
        ).upper()

        state = str(
            getattr(event, "state", "")
        ).lower()

        identity = (input_type, control)

        is_pressed = state in (
            "pressed",
            "press",
            "down",
        )

        is_released = state in (
            "released",
            "release",
            "up",
        )

        # A hotkey's release event must not leak into the recording.
        if is_released and identity in self._suppressed_inputs:
            self._suppressed_inputs.discard(identity)
            return

        # Capture mode takes priority over normal recording.
        if self._hotkey_capture_action is not None:

            if not is_pressed:
                return

            action_name = self._hotkey_capture_action

            # Left-click is intentionally not assignable.
            if input_type == "button" and control == "LEFT":
                self.hotkey_capture_rejected.emit(
                    "Left-click cannot be used as a hotkey because "
                    "it would interfere with normal mouse use. "
                    "Choose another key or mouse button."
                )
                return

            descriptor = {
                "input_type": input_type,
                "control": control,
            }

            if input_type not in ("keyboard", "button"):
                self.hotkey_capture_rejected.emit(
                    "That input type cannot be used as a macro hotkey."
                )
                return

            other_action = (
                "playback_toggle"
                if action_name == "record_toggle"
                else "record_toggle"
            )

            if self._hotkeys.get(other_action) == descriptor:
                self.hotkey_capture_rejected.emit(
                    "That input is already assigned to the other macro hotkey."
                )
                return

            self._hotkeys[action_name] = descriptor
            self._hotkey_capture_action = None

            self._suppressed_inputs.add(identity)

            self._save_hotkeys()

            self.hotkeys_changed.emit(self.get_hotkeys())
            self.hotkey_capture_finished.emit(
                action_name,
                descriptor
            )

            logger.info(
                "Assigned macro hotkey %s: %s",
                action_name,
                descriptor
            )

            return

        # Suppress the configured hotkey press and its matching release.
        if is_pressed:
            for action_name, descriptor in self._hotkeys.items():

                if not descriptor:
                    continue

                if (
                    descriptor.get("input_type") == input_type
                    and descriptor.get("control") == control
                ):
                    self._suppressed_inputs.add(identity)

                    self._handle_hotkey(action_name)
                    return

        if not self._should_record_input():
            return

        if (
            input_type == "mouse"
            and control == "MOVE"
            and not self.record_mouse_movement
        ):
            return

        if self._recording_start is None:
            return

        timestamp = getattr(event, "timestamp", time.time())

        elapsed = (
            timestamp
            - self._recording_start
            - self._recording_paused_duration
        )

        action = {
            "input_type": getattr(event, "input_type", ""),
            "control": getattr(event, "control", ""),
            "state": getattr(event, "state", ""),
            "device_id": getattr(event, "device_id", ""),
            "device_name": getattr(event, "device_name", ""),
            "time": max(0.0, elapsed),
            "value": getattr(event, "value", None),
            "x": getattr(event, "x", None),
            "y": getattr(event, "y", None),
        }

        with self._recording_lock:

            if self.recording_state != "recording":
                return

            self.actions.append(action)

        self.actions_changed.emit(list(self.actions))

    def _should_record_input(self):
        with self._recording_lock:
            return self.recording_state == "recording"

    # ======================================
    # HOTKEYS
    # ======================================

    def begin_hotkey_capture(self, action_name):
        if action_name not in self.HOTKEY_ACTIONS:
            return False

        if self._hotkey_capture_action is not None:
            self.cancel_hotkey_capture()

        self._hotkey_capture_action = action_name
        self.hotkey_capture_started.emit(action_name)

        logger.info(
            "Listening for macro hotkey: %s",
            action_name
        )

        return True

    def cancel_hotkey_capture(self):
        if self._hotkey_capture_action is None:
            return False

        action_name = self._hotkey_capture_action
        self._hotkey_capture_action = None

        self.hotkey_capture_rejected.emit(
            "Hotkey assignment cancelled."
        )

        logger.info(
            "Cancelled macro hotkey capture: %s",
            action_name
        )

        return True

    def clear_hotkey(self, action_name):
        if action_name not in self.HOTKEY_ACTIONS:
            return False

        self._hotkeys[action_name] = None

        self._save_hotkeys()
        self.hotkeys_changed.emit(self.get_hotkeys())

        return True

    def get_hotkey(self, action_name):
        descriptor = self._hotkeys.get(action_name)

        if descriptor is None:
            return None

        return dict(descriptor)

    def get_hotkeys(self):
        return {
            name: dict(value) if value else None
            for name, value in self._hotkeys.items()
        }

    def set_hotkey_playback_options(
        self,
        speed=1.0,
        repeat_count=1
    ):
        try:
            self.hotkey_playback_speed = max(
                0.1,
                min(5.0, float(speed))
            )
        except (TypeError, ValueError):
            self.hotkey_playback_speed = 1.0

        try:
            self.hotkey_repeat_count = max(
                0,
                int(repeat_count)
            )
        except (TypeError, ValueError):
            self.hotkey_repeat_count = 1

    def _handle_hotkey(self, action_name):
        if action_name == "record_toggle":

            if self.playback_state != "stopped":
                return

            if self.recording_state == "stopped":
                self.start_recording(clear=True)
            else:
                # Pressing the recording hotkey again stops recording,
                # including when recording is currently paused.
                self.stop_recording()

        elif action_name == "playback_toggle":

            if self.recording_state != "stopped":
                return

            if self.playback_state == "stopped":
                self.play(
                    speed=self.hotkey_playback_speed,
                    repeat_count=self.hotkey_repeat_count
                )
            else:
                self.stop_playback()

    def _save_hotkeys(self):
        self.HOTKEY_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temporary_path = self.HOTKEY_FILE.with_suffix(".tmp")

        data = {
            "hotkeys": self._hotkeys,
        }

        try:
            with open(
                temporary_path,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    data,
                    file,
                    indent=4
                )

            temporary_path.replace(self.HOTKEY_FILE)

        except Exception:
            logger.exception("Could not save macro hotkeys.")

    def _load_hotkeys(self):
        if not self.HOTKEY_FILE.exists():
            return

        try:
            with open(
                self.HOTKEY_FILE,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            stored = data.get("hotkeys", {})

            for action_name in self.HOTKEY_ACTIONS:
                descriptor = stored.get(action_name)

                if not isinstance(descriptor, dict):
                    continue

                input_type = str(
                    descriptor.get("input_type", "")
                ).lower()

                control = str(
                    descriptor.get("control", "")
                ).upper()

                if input_type not in ("keyboard", "button"):
                    continue

                if not control:
                    continue

                if input_type == "button" and control == "LEFT":
                    continue

                self._hotkeys[action_name] = {
                    "input_type": input_type,
                    "control": control,
                }

        except Exception:
            logger.exception("Could not load macro hotkeys.")

    @staticmethod
    def describe_hotkey(descriptor):
        if not descriptor:
            return "Not set"

        input_type = descriptor.get("input_type")
        control = descriptor.get("control", "")

        if input_type == "keyboard":
            return control

        if input_type == "button":
            return f"Mouse {control.title()}"

        return str(control)

    # ======================================
    # ACTION MANAGEMENT
    # ======================================

    def clear_actions(self):
        with self._recording_lock:

            if self.recording_state != "stopped":
                return False

            if self.playback_state != "stopped":
                return False

            self.actions.clear()

        self.actions_changed.emit([])

        return True

    def replace_actions(self, actions):
        if not isinstance(actions, list):
            return False

        if self.recording_state != "stopped":
            return False

        if self.playback_state != "stopped":
            return False

        validated = []

        for action in actions:
            if not isinstance(action, dict):
                continue

            try:
                input_type = str(action["input_type"])
                control = str(action["control"])
                state = str(action["state"])
                action_time = float(action["time"])

                if action_time < 0:
                    continue

                validated.append({
                    "input_type": input_type,
                    "control": control,
                    "state": state,
                    "device_id": str(
                        action.get("device_id", "")
                    ),
                    "device_name": str(
                        action.get("device_name", "")
                    ),
                    "time": action_time,
                    "value": action.get("value"),
                    "x": action.get("x"),
                    "y": action.get("y"),
                })

            except (KeyError, TypeError, ValueError):
                continue

        # Keep the supplied order. Timeline reordering intentionally
        # changes action order, even when timestamps are close together.
        with self._recording_lock:
            self.actions = validated

        self.actions_changed.emit(list(self.actions))

        return True

    # ======================================
    # PLAYBACK CONTROL
    # ======================================

    def play(
        self,
        speed=1.0,
        repeat_count=1
    ):
        with self._playback_lock:

            if self.playback_state != "stopped":
                return False

            if self.recording_state != "stopped":
                return False

            if not self.actions:
                return False

            try:
                speed = float(speed)
            except (TypeError, ValueError):
                speed = 1.0

            if speed <= 0:
                speed = 1.0

            try:
                repeat_count = max(0, int(repeat_count))
            except (TypeError, ValueError):
                repeat_count = 1

            self._playback_speed = speed
            self._repeat_count = repeat_count

            self._playback_stop.clear()
            self._playback_resume.set()

            self._held_keys.clear()
            self._held_buttons.clear()

            self.playback_state = "playing"

            self._playback_thread = threading.Thread(
                target=self._playback_worker,
                daemon=True,
                name="SynapseMacroPlayback"
            )

            self._playback_thread.start()

        self.playback_state_changed.emit("playing")

        logger.info(
            "Macro playback started. Speed: %s, repeats: %s",
            speed,
            "infinite" if repeat_count == 0 else repeat_count
        )

        return True

    def pause_playback(self):
        with self._playback_lock:

            if self.playback_state != "playing":
                return False

            self._playback_resume.clear()
            self.playback_state = "paused"

        self.playback_state_changed.emit("paused")

        return True

    def resume_playback(self):
        with self._playback_lock:

            if self.playback_state != "paused":
                return False

            self._playback_resume.set()
            self.playback_state = "playing"

        self.playback_state_changed.emit("playing")

        return True

    def stop_playback(self):
        with self._playback_lock:

            if self.playback_state == "stopped":
                return False

            self._playback_stop.set()
            self._playback_resume.set()

        return True

    def stop_all(self):
        self.cancel_hotkey_capture()
        self.stop_recording()
        self.stop_playback()

    # ======================================
    # PLAYBACK WORKER
    # ======================================

    def _playback_worker(self):
        actions = list(self.actions)

        completed_repeats = 0

        try:
            while not self._playback_stop.is_set():

                previous_time = 0.0

                for index, action in enumerate(actions):

                    if self._playback_stop.is_set():
                        break

                    action_time = max(
                        previous_time,
                        float(action.get("time", 0.0))
                    )

                    delay = action_time - previous_time

                    if not self._wait_playback_delay(delay):
                        break

                    if self._playback_stop.is_set():
                        break

                    self._execute_action(action)

                    previous_time = action_time

                    self.playback_progress.emit(
                        index + 1,
                        len(actions)
                    )

                if self._playback_stop.is_set():
                    break

                completed_repeats += 1

                if (
                    self._repeat_count != 0
                    and completed_repeats >= self._repeat_count
                ):
                    break

                self.playback_progress.emit(
                    0,
                    len(actions)
                )

        except Exception as error:
            logger.exception("Macro playback failed.")
            self.error_occurred.emit(str(error))

        finally:
            self._release_all_inputs()

            with self._playback_lock:
                self.playback_state = "stopped"
                self._playback_thread = None

            self.playback_state_changed.emit("stopped")

            self.playback_progress.emit(0, len(actions))

            logger.info(
                "Macro playback finished after %s repeat(s).",
                completed_repeats
            )

    def _wait_playback_delay(self, delay):
        remaining = max(
            0.0,
            delay / self._playback_speed
        )

        while remaining > 0:

            if self._playback_stop.is_set():
                return False

            if not self._playback_resume.is_set():
                self._playback_resume.wait(0.05)
                continue

            interval = min(remaining, 0.05)
            started = time.monotonic()

            self._playback_stop.wait(interval)

            elapsed = time.monotonic() - started

            if self._playback_resume.is_set():
                remaining -= elapsed

        return not self._playback_stop.is_set()

    # ======================================
    # ACTION EXECUTION
    # ======================================

    def _execute_action(self, action):
        input_type = action.get("input_type")
        control = action.get("control")
        state = action.get("state")

        if input_type == "keyboard":
            self._execute_keyboard_action(
                action,
                state
            )

        elif input_type == "button":
            self._execute_mouse_button_action(
                action,
                state
            )

        elif input_type == "mouse":
            self._execute_mouse_action(action)

    def _execute_keyboard_action(self, action, state):
        key = self._resolve_keyboard_key(action)

        if key is None:
            return

        if state == "pressed":
            self.keyboard.press(key)
            self._held_keys.add(key)

        elif state == "released":
            self.keyboard.release(key)
            self._held_keys.discard(key)

    def _execute_mouse_button_action(self, action, state):
        button = self._resolve_mouse_button(
            action.get("control")
        )

        if button is None:
            return

        x = action.get("x")
        y = action.get("y")

        if x is not None and y is not None:
            self.mouse.position = (int(x), int(y))

        if state == "pressed":
            self.mouse.press(button)
            self._held_buttons.add(button)

        elif state == "released":
            self.mouse.release(button)
            self._held_buttons.discard(button)

    def _execute_mouse_action(self, action):
        control = action.get("control")

        if control == "MOVE":

            x = action.get("x")
            y = action.get("y")

            if x is not None and y is not None:
                self.mouse.position = (int(x), int(y))

        elif control in (
            "SCROLL_UP",
            "SCROLL_DOWN",
            "SCROLL_LEFT",
            "SCROLL_RIGHT"
        ):

            amount = max(
                1,
                int(action.get("value") or 1)
            )

            dx = 0
            dy = 0

            if control == "SCROLL_UP":
                dy = amount
            elif control == "SCROLL_DOWN":
                dy = -amount
            elif control == "SCROLL_RIGHT":
                dx = amount
            elif control == "SCROLL_LEFT":
                dx = -amount

            self.mouse.scroll(dx, dy)

    # ======================================
    # KEY RESOLUTION
    # ======================================

    @staticmethod
    def _resolve_keyboard_key(action):
        control = str(action.get("control", ""))

        special_keys = {
            "VK_8": Key.backspace,
            "VK_9": Key.tab,
            "VK_13": Key.enter,
            "VK_16": Key.shift,
            "VK_17": Key.ctrl,
            "VK_18": Key.alt,
            "VK_19": Key.pause,
            "VK_20": Key.caps_lock,
            "VK_27": Key.esc,
            "VK_32": Key.space,
            "VK_33": Key.page_up,
            "VK_34": Key.page_down,
            "VK_35": Key.end,
            "VK_36": Key.home,
            "VK_37": Key.left,
            "VK_38": Key.up,
            "VK_39": Key.right,
            "VK_40": Key.down,
            "VK_44": Key.print_screen,
            "VK_45": Key.insert,
            "VK_46": Key.delete,
            "VK_91": Key.cmd,
            "VK_92": Key.cmd,
            "VK_93": Key.menu,
            "VK_144": Key.num_lock,
            "VK_145": Key.scroll_lock,
            "VK_160": Key.shift,
            "VK_161": Key.shift,
            "VK_162": Key.ctrl,
            "VK_163": Key.ctrl,
            "VK_164": Key.alt,
            "VK_165": Key.alt,
        }

        if control in special_keys:
            return special_keys[control]

        value = action.get("value")

        if value is not None:
            try:
                value = int(value)

                if 65 <= value <= 90:
                    return chr(value).lower()

                if 48 <= value <= 57:
                    return chr(value)

                if 112 <= value <= 135:
                    return getattr(
                        Key,
                        f"f{value - 111}",
                        None
                    )

                punctuation = {
                    186: ";",
                    187: "=",
                    188: ",",
                    189: "-",
                    190: ".",
                    191: "/",
                    192: "`",
                    219: "[",
                    220: "\\",
                    221: "]",
                    222: "'",
                }

                if value in punctuation:
                    return punctuation[value]

                return KeyCode.from_vk(value)

            except (TypeError, ValueError):
                pass

        return None

    @staticmethod
    def _resolve_mouse_button(control):
        buttons = {
            "LEFT": Button.left,
            "RIGHT": Button.right,
            "MIDDLE": Button.middle,
            "X1": Button.x1,
            "X2": Button.x2,
        }

        return buttons.get(str(control).upper())

    # ======================================
    # INPUT CLEANUP
    # ======================================

    def _release_all_inputs(self):
        for key in list(self._held_keys):

            try:
                self.keyboard.release(key)
            except Exception:
                logger.exception(
                    "Could not release macro keyboard key: %r",
                    key
                )

        self._held_keys.clear()

        for button in list(self._held_buttons):

            try:
                self.mouse.release(button)
            except Exception:
                logger.exception(
                    "Could not release macro mouse button: %r",
                    button
                )

        self._held_buttons.clear()

    # ======================================
    # MACRO STORAGE
    # ======================================

    @staticmethod
    def _safe_macro_name(name):
        name = str(name).strip()

        name = re.sub(
            r'[<>:"/\\|?*\x00-\x1f]',
            "_",
            name
        )

        name = name.strip(" .")

        if not name:
            raise ValueError("Macro name cannot be empty.")

        return name[:100]

    def save_macro(self, name):
        if self.recording_state != "stopped":
            raise RuntimeError(
                "Stop recording before saving a macro."
            )

        if self.playback_state != "stopped":
            raise RuntimeError(
                "Stop playback before saving a macro."
            )

        name = self._safe_macro_name(name)

        self.MACRO_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        path = self.MACRO_DIRECTORY / f"{name}.json"

        data = {
            "format_version": self.FORMAT_VERSION,
            "name": name,
            "actions": list(self.actions),
        }

        temporary_path = path.with_suffix(".tmp")

        with open(
            temporary_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                indent=4
            )

        temporary_path.replace(path)

        logger.info("Saved macro: %s", name)

        return path

    def load_macro(self, path):
        if self.recording_state != "stopped":
            raise RuntimeError(
                "Stop recording before loading a macro."
            )

        if self.playback_state != "stopped":
            raise RuntimeError(
                "Stop playback before loading a macro."
            )

        path = Path(path)

        if not path.exists() or path.suffix.lower() != ".json":
            raise FileNotFoundError(
                "The selected macro file does not exist."
            )

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid macro file.")

        if data.get("format_version") != self.FORMAT_VERSION:
            raise ValueError(
                "Unsupported macro file version."
            )

        actions = data.get("actions")

        if not isinstance(actions, list):
            raise ValueError(
                "Macro file contains invalid actions."
            )

        if not self.replace_actions(actions):
            raise RuntimeError(
                "Could not load macro actions."
            )

        logger.info("Loaded macro: %s", path.stem)

        return data.get("name", path.stem)

    @classmethod
    def list_macros(cls):
        cls.MACRO_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        return sorted(
            cls.MACRO_DIRECTORY.glob("*.json"),
            key=lambda path: path.stem.lower()
        )
