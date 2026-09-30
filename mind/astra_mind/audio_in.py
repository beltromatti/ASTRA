"""Push-to-talk microphone capture (16 kHz mono PCM16) with sounddevice/PortAudio.

The game sends ptt down/up; the audio is recorded here, next to the speech recogniser.

- Pre-roll: once the microphone has been opened it stays open for a while and the last 300 ms are kept in a ring, so the
  first syllable is never lost to the moment the key goes down (opening a Core Audio input takes 30-150 ms; people begin to
  speak as they press). Only those 300 ms exist in memory, and nothing is ever written to disk. After `IDLE_CLOSE_S`
  without a press the stream is closed again (the orange indicator goes off). A Bluetooth headset is a different matter:
  an open input switches the whole headset to its telephone mode (mono, low quality, and the game's sound drops with it)
  every time it is opened. When the default input is such a headset the computer's own microphone is opened instead (only
  this stream, no system setting is touched); if there is none, the headset is opened per press and closed at release.
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
OPEN_WAIT_S = 2.0           # a key press waits this long at most for the device to open (see PushToTalk.begin)
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
        self._opening: asyncio.Future | None = None     # the device being opened in a worker thread
        self._device_name = ""
        self.overflows = 0
        self.last: Recording | None = None
        self.mode = os.environ.get("ASTRA_MIC", "auto").lower()           # auto | always | ptt | off (no device: silent takes)

    # ------------------------------------------------------------------------------------------ device
    @staticmethod
    def input_name() -> str:
        try:
            import sounddevice as sd
            return str(sd.query_devices(kind="input")["name"])
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def pick_device() -> tuple[int | None, str]:
        """(device index or None for the system's default, its name). When the default input is a Bluetooth headset the
        computer's own microphone is used instead: an open input switches the whole headset to its telephone mode (mono,
        low quality, and the game's sound drops with it) every time it is opened, while the built-in one costs nothing.
        The system's settings are not touched: only this stream is opened on the other device."""
        try:
            import sounddevice as sd
            default = sd.query_devices(kind="input")
            name = str(default["name"])
            if any(k in name.lower() for k in _BLUETOOTH):
                for i, d in enumerate(sd.query_devices()):
                    dn = str(d["name"]).lower()
                    if d["max_input_channels"] > 0 and any(k in dn for k in ("macbook", "built-in", "builtin", "internal", "imac", "mac mini", "mac studio")):
                        return i, str(d["name"])
            return None, name
        except Exception:  # noqa: BLE001
            return None, ""

    def _keep_open(self) -> bool:
        if self.mode in ("ptt", "off"):
            return False
        if self.mode == "always":
            return True
        return not any(k in self._device_name.lower() for k in _BLUETOOTH)

    def _open(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
        except Exception as exc:  # noqa: BLE001
            log.error("sounddevice unavailable: %s", exc)
            return False
        self._first_block.clear()
        device, self._device_name = self.pick_device()
        try:
            kw = {"device": device} if device is not None else {}
            self._stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16", blocksize=BLOCK, latency="low",
                                             callback=self._callback, **kw)
            self._stream.start()
            log.info("microphone: %s", self._device_name)
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
    def _open_primed(self) -> bool:
        """(worker thread) Open the device and let it deliver its first block."""
        if not self._open():
            return False
        self._first_block.wait(timeout=1.0)
        return True

    def _late_open(self, fut: asyncio.Future) -> None:
        """An open that outlived its key press finished: a microphone nobody is using follows the usual closing rule."""
        if self._take is None and not fut.cancelled() and fut.exception() is None and fut.result():
            self._schedule_close()

    async def begin(self, on_chunk: Callable[[bytes], None] | None = None, wait_s: float = OPEN_WAIT_S) -> bool:
        """Key down, without ever holding up the event loop: opening the device can block for as long as the system
        wants (its microphone-permission prompt, a headset switching profile; measured: the whole mind stopped, crew
        voices included, while PortAudio waited inside CoreAudio), so it is opened in a worker thread and waited for at
        most `wait_s`. Not open by then: this press records nothing (the open goes on; the next press finds the
        microphone ready, or fails at once while the system is still deciding)."""
        if self.mode == "off":
            # no device at all (tests driving the key, a machine without a microphone): the key takes the floor, and
            # the take is silent
            with self._lock:
                self._take = _Take(chunks=[], on_chunk=None)
            self._last_press = time.monotonic()
            return True
        if self._stream is None:
            if self._opening is not None and not self._opening.done():
                log.warning("microphone: the system is still opening it (a permission prompt?): this press is not recorded")
                return False
            loop = asyncio.get_running_loop()
            self._opening = fut = loop.run_in_executor(None, self._open_primed)
            try:
                if not await asyncio.wait_for(asyncio.shield(fut), wait_s):
                    return False
            except asyncio.TimeoutError:
                log.warning("microphone: not open after %.1f s (a permission prompt?): this press is not recorded", wait_s)
                fut.add_done_callback(self._late_open)
                return False
        return self.start(on_chunk)                                         # open: start() no longer blocks

    def start(self, on_chunk: Callable[[bytes], None] | None = None) -> bool:
        """Key down. `on_chunk(pcm16)` is called (in the running event loop) with the pre-roll and then every 20 ms block.
        Blocks while the device opens: from the event loop use `begin`."""
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
