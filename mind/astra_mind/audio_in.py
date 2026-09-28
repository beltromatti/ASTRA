"""Push-to-talk microphone capture (16 kHz mono PCM16) with sounddevice/PortAudio.
The game sends ptt down/up; audio is recorded here, next to the speech recogniser."""
from __future__ import annotations

import logging
import threading

log = logging.getLogger("astra.mic")


class PushToTalk:
    def __init__(self, rate: int = 16000) -> None:
        self.rate = rate
        self._chunks: list[bytes] = []
        self._stream = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            log.error("sounddevice unavailable: %s", exc)
            return False
        with self._lock:
            self._chunks = []

        def cb(indata, frames, t, status):  # noqa: ANN001
            with self._lock:
                self._chunks.append(bytes(indata))

        try:
            self._stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16", callback=cb, blocksize=0)
            self._stream.start()
            return True
        except Exception as exc:  # noqa: BLE001 - typically: no microphone permission yet
            log.error("microphone unavailable: %s", exc)
            self._stream = None
            return False

    def stop(self) -> bytes:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None
        with self._lock:
            data = b"".join(self._chunks)
            self._chunks = []
        return data
