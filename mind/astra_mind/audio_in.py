"""Push-to-talk microphone capture (16 kHz mono PCM16) with sounddevice/PortAudio.

The game sends ptt down/up; the audio is recorded here, next to the speech recogniser.

- Pre-roll: once the microphone has been opened it stays open for a while and the last 300 ms are kept in a ring, so the
  first syllable is never lost to the moment the key goes down (opening a Core Audio input takes 30-150 ms; people begin to
  speak as they press). Only those 300 ms exist in memory, and nothing is ever written to disk. After `IDLE_CLOSE_S`
  without a press the stream is closed again (the orange indicator goes off). A Bluetooth headset is opened per press only:
  an open input switches the whole headset to its telephone mode (mono, low quality) for as long as it is open.
- Post-roll: a press ends slightly before the last sound has left the audio buffers; `finish()` waits 100 ms for them.
- Trimming: the silence before and after the speech is cut (voice_audio.trim_speech) and a recording with no speech in it
  comes back empty, so the recogniser never sees a key click or a breath.
- Streaming: `start(on_chunk=...)` hands the pre-roll and then every 20 ms block to the recogniser while the key is held, so
  it can decode as the Captain speaks and little is left to do at release.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .voice_audio import pcm16_to_f32, peak_db, trim_speech

log = logging.getLogger("astra.mic")

RATE = 16000
BLOCK = 320                 # 20 ms
PREROLL_S = 0.30
POSTROLL_S = 0.10
IDLE_CLOSE_S = 300.0
PAD_MS = 220.0
_BLUETOOTH = ("airpods", "bluetooth", "beats", "buds", "wh-1000", "wf-1000", "bose", "jabra", "hands-free", "hfp")


@dataclass
class Recording:
    pcm: bytes                  # what was recorded, trimmed to the speech (empty: no speech in it)
    raw: bytes                  # everything: pre-roll, the press, post-roll
    raw_s: float = 0.0
    speech_s: float = 0.0
    peak_db: float = -120.0
    preroll_s: float = 0.0      # how much audio before the key press was available (0 on the first press)
    open_s: float = 0.0         # how long opening the microphone took (the first press, or after an idle close)


@dataclass
class _Take:
    """One key press being recorded: the blocks so far, and who wants each new one."""
    chunks: list[bytes] = field(default_factory=list)
    on_chunk: Callable[[bytes], None] | None = None
    preroll_s: float = 0.0
    open_s: float = 0.0


class PushToTalk:
    def __init__(self, rate: int = RATE) -> None:
        self.rate = rate
        self._lock = threading.Lock()
        self._stream = None
        self._ring: collections.deque[bytes] = collections.deque(maxlen=int(PREROLL_S * rate / BLOCK) + 1)
        self._take: _Take | None = None                # the press being held
        self._closing: _Take | None = None             # the press just released, still collecting its post-roll
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_press = 0.0
        self._closer: threading.Timer | None = None
        self._first_block = threading.Event()
        self.overflows = 0
        self.last: Recording | None = None
        self.mode = os.environ.get("ASTRA_MIC", "auto").lower()           # auto | always | ptt

    # ------------------------------------------------------------------------------------------ device
    @staticmethod
    def input_name() -> str:
        try:
            import sounddevice as sd
            return str(sd.query_devices(kind="input")["name"])
        except Exception:  # noqa: BLE001
            return ""

    def _keep_open(self) -> bool:
        if self.mode == "ptt":
            return False
        if self.mode == "always":
            return True
        name = self.input_name().lower()
        return not any(k in name for k in _BLUETOOTH)

    def _open(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            log.error("sounddevice unavailable: %s", exc)
            return False
        self._first_block.clear()
        try:
            self._stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16", blocksize=BLOCK, latency="low",
                                             callback=self._callback)
            self._stream.start()
            return True
        except Exception as exc:  # noqa: BLE001 - typically: no microphone permission yet
            log.error("microphone unavailable: %s", exc)
            self._stream = None
            return False

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        with self._lock:
            self._ring.clear()
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                log.debug("closing the microphone failed", exc_info=True)

    def _callback(self, indata, frames, t, status) -> None:  # noqa: ANN001
        if status:
            self.overflows += 1
        b = bytes(indata)
        cb = None
        with self._lock:
            take = self._take
            if take is not None:
                take.chunks.append(b)
                cb = take.on_chunk
            else:
                self._ring.append(b)
            if self._closing is not None:
                self._closing.chunks.append(b)
        self._first_block.set()
        if cb is not None and self._loop is not None:
            try:
                self._loop.call_soon_threadsafe(cb, b)
            except RuntimeError:
                pass                                                       # the loop is gone

    def _schedule_close(self) -> None:
        if self._closer is not None:
            self._closer.cancel()
        if not self._keep_open():
            self._close()
            return
        self._closer = threading.Timer(IDLE_CLOSE_S, self._idle_close)
        self._closer.daemon = True
        self._closer.start()

    def _idle_close(self) -> None:
        if self._take is None and time.monotonic() - self._last_press >= IDLE_CLOSE_S - 1:
            log.info("microphone closed after %.0f s without use", IDLE_CLOSE_S)
            self._close()

    # ------------------------------------------------------------------------------------------ recording
    def start(self, on_chunk: Callable[[bytes], None] | None = None) -> bool:
        """Key down. `on_chunk(pcm16)` is called (in the running event loop) with the pre-roll and then every 20 ms block."""
        if self._closer is not None:
            self._closer.cancel()
        t0 = time.perf_counter()
        was_open = self._stream is not None
        if not self._open():
            return False
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        if not was_open:
            self._first_block.wait(timeout=1.0)                             # let the device deliver its first block
        with self._lock:
            pre = list(self._ring) if was_open else []
            self._ring.clear()
            take = _Take(chunks=list(pre), on_chunk=on_chunk if self._loop is not None else None,
                         preroll_s=sum(len(b) for b in pre) / 2 / self.rate, open_s=0.0 if was_open else time.perf_counter() - t0)
            self._take = take
        self._last_press = time.monotonic()
        if on_chunk is not None and self._loop is not None and pre:
            self._loop.call_soon(on_chunk, b"".join(pre))
        return True

    def _release(self) -> _Take | None:
        with self._lock:
            take, self._take = self._take, None
            self._closing = take
        return take

    def stop(self) -> bytes:
        """Key up, at once: the recording trimmed to its speech (empty when there is none)."""
        take = self._release()
        with self._lock:
            self._closing = None
        self._schedule_close()
        return self._analyse(take).pcm

    async def finish(self, post_roll_s: float = POSTROLL_S) -> Recording:
        """Key up: wait for the last sound to leave the audio buffers, then the whole recording."""
        take = self._release()
        if post_roll_s > 0:
            await asyncio.sleep(post_roll_s)
        with self._lock:
            if self._closing is take:
                self._closing = None
        self._schedule_close()
        return self._analyse(take)

    def _analyse(self, take: _Take | None) -> Recording:
        raw = b"".join(take.chunks) if take is not None else b""
        x = pcm16_to_f32(raw)
        trimmed, _, speech_s = trim_speech(x, self.rate, pad_ms=PAD_MS)
        pcm = (np.clip(trimmed, -1, 1) * 32767).astype("<i2").tobytes()
        rec = Recording(pcm=pcm, raw=raw, raw_s=len(x) / self.rate, speech_s=speech_s, peak_db=peak_db(x) if len(x) else -120.0,
                        preroll_s=take.preroll_s if take else 0.0, open_s=take.open_s if take else 0.0)
        self.last = rec
        log.debug("recorded %.2f s (%.2f s of speech, peak %.0f dB, pre-roll %.2f s, opened in %.0f ms)", rec.raw_s, rec.speech_s,
                  rec.peak_db, rec.preroll_s, rec.open_s * 1000)
        return rec

    def close(self) -> None:
        if self._closer is not None:
            self._closer.cancel()
        self._close()
