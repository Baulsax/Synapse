from dataclasses import dataclass


@dataclass
class InputEvent:
    device_id: str
    device_name: str

    input_type: str
    control: str

    state: str
    source: str

    timestamp: float
    value: int | None = None
    data: bytes | None = None

    # Optional screen coordinates for mouse events.
    x: int | None = None
    y: int | None = None