
import logging

from pynput.keyboard import Key
from pynput.mouse import Button


logger = logging.getLogger(__name__)


class InputsMixin:

    # ======================================
    # INPUT HANDLING
    # ======================================

    @staticmethod
    def _input_descriptor(block):
        if not block:
            return None

        fields = block.get("fields", {})
        extra_state = block.get("extraState", {})

        device = (
            extra_state.get("device")
            or fields.get("DEVICE")
        )

        control = (
            extra_state.get("control")
            or fields.get("CONTROL")
        )

        if not device or not control:
            return None

        if control == "Click to add an input":
            return None

        return device, control

    def _collect_stop_inputs(self, workflow_data):
        stop_inputs = set()
        visited = set()

        def visit(block):
            if not block:
                return

            block_id = block.get("id")

            if block_id and block_id in visited:
                return

            if block_id:
                visited.add(block_id)

            if block.get("type") == "automation_stop_if_input":
                input_data = block.get("inputs", {}).get("INPUT", {})

                input_block = (
                    input_data.get("block")
                    or input_data.get("shadow")
                )

                descriptor = self._input_descriptor(input_block)

                if descriptor:
                    stop_inputs.add(descriptor)
                else:
                    logger.warning(
                        "Stop If Input has no valid input connected."
                    )

            visit(block.get("next", {}).get("block"))

            for input_data in block.get("inputs", {}).values():
                visit(
                    input_data.get("block")
                    or input_data.get("shadow")
                )

        top_blocks = (
            workflow_data.get("blocks", {}).get("blocks", [])
        )

        for block in top_blocks:
            visit(block)

        return stop_inputs

    # ======================================
    # MOUSE HELPERS
    # ======================================

    def _mouse_click(self, button):
        if self._current_stop_event().is_set():
            return

        self.mouse.click(button)

    # ======================================
    # KEYBOARD HELPERS
    # ======================================

    @staticmethod
    def _resolve_key(control):
        if not control:
            return None

        control = str(control)

        special_keys = {
            "SHIFT": Key.shift,
            "CTRL": Key.ctrl_l,
            "ALT": Key.alt_l,
            "LWIN": Key.cmd_l,
            "RWIN": Key.cmd_r,

            "UP": Key.up,
            "DOWN": Key.down,
            "LEFT": Key.left,
            "RIGHT": Key.right,

            "HOME": Key.home,
            "END": Key.end,
            "PAGEUP": Key.page_up,
            "PAGEDOWN": Key.page_down,

            "BACKSPACE": Key.backspace,
            "DELETE": Key.delete,
            "INSERT": Key.insert,
            "ENTER": Key.enter,
            "TAB": Key.tab,
            "ESC": Key.esc,
            "SPACE": Key.space,

            "CAPSLOCK": Key.caps_lock,
            "PRINTSCREEN": Key.print_screen,
            "SCROLLLOCK": Key.scroll_lock,
            "PAUSE": Key.pause,
            "APPS": Key.menu,

            "NUMLOCK": Key.num_lock
        }

        if control in special_keys:
            return special_keys[control]

        if len(control) == 1:
            return control.lower()

        key_name = control.lower()

        try:
            return getattr(Key, key_name)
        except AttributeError:
            logger.warning(
                "Unsupported keyboard key: %s",
                control
            )
            return None

    def _press_key(self, key):
        if self._current_stop_event().is_set():
            return

        try:
            self.keyboard.press(key)

            try:
                self.keyboard.release(key)
            except Exception:
                logger.exception(
                    "Failed to release key after pressing it."
                )
                raise

        except Exception:
            logger.exception(
                "Failed to press keyboard key: %r",
                key
            )

    def _key_down(self, key):
        if self._current_stop_event().is_set():
            return

        try:
            self.keyboard.press(key)

            with self._execution_lock:
                self._held_keys.add(key)

        except Exception:
            logger.exception(
                "Failed to hold keyboard key: %r",
                key
            )

    def _key_up(self, key):
        try:
            self.keyboard.release(key)

            with self._execution_lock:
                self._held_keys.discard(key)

        except Exception:
            logger.exception(
                "Failed to release keyboard key: %r",
                key
            )

    def _release_all_keys(self):
        with self._execution_lock:
            for key in list(self._held_keys):
                try:
                    self.keyboard.release(key)
                except Exception:
                    logger.exception(
                        "Failed to release held key: %r",
                        key
                    )

            self._held_keys.clear()

    def _type_text(self, text):
        stop_event = self._current_stop_event()

        for character in str(text):
            if stop_event.is_set():
                break

            try:
                self.keyboard.type(character)

            except Exception:
                logger.exception(
                    "Failed to type character: %r",
                    character
                )
                break

            # Allow the receiving application to process the
            # completed keystroke before the next one is injected.
            delay = self.TEXT_CHARACTER_DELAY

            if character in self.SHIFTED_TEXT_CHARACTERS:
                delay += self.TEXT_SHIFTED_CHARACTER_DELAY

            if stop_event.wait(delay):
                break
