from dataclasses import replace

from PySide6.QtCore import QTimer


class InputManager:

    MODIFIER_KEYS = {
        "VK_16": "SHIFT",
        "VK_17": "CTRL",
        "VK_18": "ALT",
        "VK_160": "SHIFT",
        "VK_161": "SHIFT",
        "VK_162": "CTRL",
        "VK_163": "CTRL",
        "VK_164": "ALT",
        "VK_165": "ALT",
    }

    SPECIAL_KEYS = {
        "VK_8": "BACKSPACE",
        "VK_9": "TAB",
        "VK_13": "ENTER",
        "VK_19": "PAUSE",
        "VK_20": "CAPSLOCK",
        "VK_27": "ESC",
        "VK_32": "SPACE",
        "VK_33": "PAGEUP",
        "VK_34": "PAGEDOWN",
        "VK_35": "END",
        "VK_36": "HOME",
        "VK_37": "LEFT",
        "VK_38": "UP",
        "VK_39": "RIGHT",
        "VK_40": "DOWN",
        "VK_44": "PRINTSCREEN",
        "VK_45": "INSERT",
        "VK_46": "DELETE",
        "VK_91": "LWIN",
        "VK_92": "RWIN",
        "VK_93": "APPS",
        "VK_106": "NUM_MULTIPLY",
        "VK_107": "NUM_ADD",
        "VK_109": "NUM_SUBTRACT",
        "VK_110": "NUM_DECIMAL",
        "VK_111": "NUM_DIVIDE",
        "VK_144": "NUMLOCK",
        "VK_145": "SCROLLLOCK",

        "VK_186": ";",
        "VK_187": "=",
        "VK_188": ",",
        "VK_189": "-",
        "VK_190": ".",
        "VK_191": "/",
        "VK_192": "`",
        "VK_219": "[",
        "VK_220": "\\",
        "VK_221": "]",
        "VK_222": "'",
    }

    UNSAFE_CAPTURE_MOUSE_BUTTONS = {
        "LEFT",
        "RIGHT",
        "MIDDLE",
    }

    def __init__(self, provider):
        self.provider = provider

        # Existing normalized workflow input callback.
        self.on_input = None

        # New raw callback for macro recording and other systems.
        self.on_raw_input = None

        self.capture_callback = None
        self.capture_armed = False
        self.capture_generation = 0

        self.is_running = False

        self.held_modifiers = {}
        self.used_modifiers = {}
        self.held_keys = {}

    # ======================================
    # INPUT CAPTURE
    # ======================================

    def capture_next_input(self, callback):
        self.capture_generation += 1
        generation = self.capture_generation

        self.capture_callback = callback
        self.capture_armed = False

        QTimer.singleShot(
            300,
            lambda: self._arm_capture(generation)
        )

    def cancel_input_capture(self):
        self.capture_generation += 1
        self.capture_callback = None
        self.capture_armed = False

    def _arm_capture(self, generation):
        if generation != self.capture_generation:
            return

        if self.capture_callback is None:
            return

        self.capture_armed = True

    def _capture_allowed(self, event):
        if event.input_type == "button":
            return (
                event.control.upper()
                not in self.UNSAFE_CAPTURE_MOUSE_BUTTONS
            )

        return event.input_type in ("keyboard", "mouse")

    # ======================================
    # PROVIDER LIFECYCLE
    # ======================================

    def start(self):
        if self.is_running:
            return

        self.provider.on_input = self._handle_input
        self.provider.start()

        self.is_running = True

    def stop(self):
        if not self.is_running:
            return

        self.provider.stop()
        self.is_running = False

        self.cancel_input_capture()

        self.held_modifiers.clear()
        self.used_modifiers.clear()
        self.held_keys.clear()

    # ======================================
    # INPUT PROCESSING
    # ======================================

    def _handle_input(self, event):
        # Raw observers see every original event, including key releases.
        if self.on_raw_input:
            try:
                self.on_raw_input(event)
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Raw input observer failed."
                )

        if event.input_type == "keyboard":
            self._handle_keyboard_event(event)
        else:
            self._emit_input(event)

    def _handle_keyboard_event(self, event):
        device = event.device_id
        key = event.control

        modifiers = self.held_modifiers.setdefault(device, set())
        used = self.used_modifiers.setdefault(device, set())
        held = self.held_keys.setdefault(device, set())

        modifier_name = self.MODIFIER_KEYS.get(key)

        if event.state == "pressed":

            if modifier_name:
                modifiers.add(key)
                return

            if key in held:
                return

            held.add(key)

            active_modifiers = {
                self.MODIFIER_KEYS[modifier]
                for modifier in modifiers
            }

            used.update(modifiers)

            key_name = self._format_key(key)

            ordered_modifiers = [
                name for name in ("CTRL", "ALT", "SHIFT")
                if name in active_modifiers
            ]

            control = "+".join(
                ordered_modifiers + [key_name]
            )

            combined_event = replace(
                event,
                control=control,
                state="pressed",
                source="global_keyboard_hook"
            )

            self._emit_input(combined_event)
            return

        if event.state == "released":
            held.discard(key)

            if modifier_name:
                modifiers.discard(key)

                if key not in used:
                    standalone_event = replace(
                        event,
                        control=modifier_name,
                        state="pressed",
                        source="global_keyboard_hook"
                    )

                    self._emit_input(standalone_event)

                if not modifiers:
                    used.clear()

    def _format_key(self, key):
        if key in self.SPECIAL_KEYS:
            return self.SPECIAL_KEYS[key]

        if key.startswith("VK_"):
            try:
                value = int(key[3:])

                if 48 <= value <= 57 or 65 <= value <= 90:
                    return chr(value)

                if 112 <= value <= 135:
                    return f"F{value - 111}"

                if 96 <= value <= 105:
                    return f"NUM{value - 96}"

            except ValueError:
                pass

        return key

    # ======================================
    # EVENT DISPATCH
    # ======================================

    def _emit_input(self, event):
        if (
            self.capture_callback
            and self.capture_armed
            and event.state == "pressed"
        ):
            if self._capture_allowed(event):
                callback = self.capture_callback

                self.capture_callback = None
                self.capture_armed = False

                callback(event)

        if self.on_input:
            self.on_input(event)

    def get_devices(self):
        return self.provider.enumerate_devices()