import threading
from typing import List

import numpy as np
import sounddevice as sd

from app_logging import get_logger


logger = get_logger(__name__)


class PushToTalkRecorder:
    def __init__(self, sample_rate: int, channels: int, dtype: str) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype

        self._frames: List[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        self.is_recording = False

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.warning("Recording warning: %s", status)
        with self._lock:
            self._frames.append(indata.copy())

    def start(self) -> None:
        if self.is_recording:
            return

        with self._lock:
            self._frames = []

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=self.dtype,
            callback=self._callback,
        )
        self._stream.start()
        self.is_recording = True

    def stop(self) -> np.ndarray | None:
        if not self.is_recording:
            return None

        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        finally:
            self._stream = None
            self.is_recording = False

        with self._lock:
            if not self._frames:
                return None
            return np.concatenate(self._frames, axis=0)
