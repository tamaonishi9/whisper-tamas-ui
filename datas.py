from dataclasses import dataclass, field
import threading


@dataclass
class AppState:
    enabled: bool = True
    current_mode: str | None = None
    input_mode: str = "p2t"
    is_recording: bool = False
    should_exit: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
