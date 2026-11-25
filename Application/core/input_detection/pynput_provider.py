import time

from PySide6.QtCore import QObject, Signal, Slot, Qt
from pynput import keyboard, mouse

from core.input_detection.input_event import InputEvent


class _InputBridge(QObject):
    event_received = Signal(object)


class PynputInputProvider:

    MOUSE_MOVE_INTERVAL = 0.008

    def __init__(self):
        self.on_input = None
        self.is_running = False

        self.keyboard_listener = None
        self.mouse_listener = None

        self._last_mouse_move = 0.0

        self.bridge = _InputBridge()
        self.bridge.event_received.connect(
            self._deliver_event,
            Qt.ConnectionType.QueuedConnection
        )

    def start(self):
        if self.is_running:
            return

        self.keyboard_listener = keyboard.Listener(
            on_press=self._on_key_pressed,
            on_release=self._on_key_released
        )

        self.mouse_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll
        )

        self.keyboard_listener.start()
        self.mouse_listener.start()

        self.is_running = True

    def stop(self):
        if not self.is_running:
            return

        self.is_running = False

        if self.keyboard_listener:
            self.keyboard_listener.stop()
            self.keyboard_listener.join(timeout=1)
            self.keyboard_listener = None

        if self.mouse_listener:
            self.mouse_listener.stop()
            self.mouse_listener.join(timeout=1)
            self.mouse_listener = None

    # ======================================
    # KEYBOARD
    # ======================================

    def _get_key_code(self, key):
        value = getattr(key, "vk", None)

        if value is None:
            inner_value = getattr(key, "value", None)
            value = getattr(inner_value, "vk", None)

        if value is None:
            character = getattr(key, "char", None)

            if character:
                value = ord(character.upper())

        if value is None:
            name = getattr(key, "name", None)

            if name and name.lower().startswith("f"):
                try:
                    number = int(name[1:])

                    if 1 <= number <= 24:
                        value = 111 + number

                except ValueError:
                    pass

        if value is None:
            return None

        return f"VK_{value}", value

    def _on_key_pressed(self, key):
        self._handle_key(key, "pressed")

    def _on_key_released(self, key):
        self._handle_key(key, "released")

    def _handle_key(self, key, state):
        result = self._get_key_code(key)

        if result is None:
            return

        control, value = result

        event = InputEvent(
            device_id="keyboard",
            device_name="Keyboard",
            input_type="keyboard",
            control=control,
            state=state,
            source="global_keyboard_hook",
            timestamp=time.time(),
            value=value
        )

        self.bridge.event_received.emit(event)

    # ======================================
    # MOUSE MOVEMENT
    # ======================================

    def _on_mouse_move(self, x, y):
        now = time.monotonic()

        if (
            now - self._last_mouse_move
            < self.MOUSE_MOVE_INTERVAL
        ):
            return

        self._last_mouse_move = now

        event = InputEvent(
            device_id="mouse",
            device_name="Mouse",
            input_type="mouse",
            control="MOVE",
            state="moved",
            source="global_mouse_hook",
            timestamp=time.time(),
            x=int(x),
            y=int(y)
        )

        self.bridge.event_received.emit(event)

    # ======================================
    # MOUSE BUTTONS
    # ======================================

    def _on_mouse_click(self, x, y, button, pressed):
        button_name = getattr(
            button,
            "name",
            str(button)
        ).upper()

        event = InputEvent(
            device_id="mouse",
            device_name="Mouse",
            input_type="button",
            control=button_name,
            state="pressed" if pressed else "released",
            source="global_mouse_hook",
            timestamp=time.time(),
            x=int(x),
            y=int(y)
        )

        self.bridge.event_received.emit(event)

    # ======================================
    # MOUSE SCROLL
    # ======================================

    def _on_mouse_scroll(self, x, y, dx, dy):
        if dy == 0 and dx == 0:
            return

        if dy:
            control = "SCROLL_UP" if dy > 0 else "SCROLL_DOWN"
            amount = abs(dy)
        else:
            control = "SCROLL_RIGHT" if dx > 0 else "SCROLL_LEFT"
            amount = abs(dx)

        event = InputEvent(
            device_id="mouse",
            device_name="Mouse",
            input_type="mouse",
            control=control,
            state="pressed",
            source="global_mouse_hook",
            timestamp=time.time(),
            value=amount,
            x=int(x),
            y=int(y)
        )

        self.bridge.event_received.emit(event)

    # ======================================
    # DISPATCH
    # ======================================

    @Slot(object)
    def _deliver_event(self, event):
        if self.is_running and self.on_input:
            self.on_input(event)

    def enumerate_devices(self):
        return [
            {
                "device_id": "keyboard",
                "device_name": "Keyboard",
                "input_type": "keyboard"
            },
            {
                "device_id": "mouse",
                "device_name": "Mouse",
                "input_type": "mouse"
            }
        ]