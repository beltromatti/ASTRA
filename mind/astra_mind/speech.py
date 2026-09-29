"""The crew's speech: one voice at a time, in speaking order, synthesised one line ahead of playback.

Game protocol (see server.py): line{id,speaker,name,text,lang,tone,channel} · audio_begin{line,speaker,rate} ·
<binary: uint32 LE line id + PCM16 mono> · audio_end{line}."""
from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Callable

from .tts import TTSEngine

log = logging.getLogger("astra.speech")


class Voice:
    """Serialises the crew's lines in speaking order. Synthesis runs one line ahead; each line is sent when the previous
    one has finished playing (the game plays audio as it arrives, so sending early would make officers talk over each
    other). Lines from event reports are low priority: when the Captain speaks, the unspoken ones are dropped."""

    GAP_S = 0.25                    # a breath between two lines

    def __init__(self, tts: TTSEngine, sink, who: Callable[[str], tuple[str, str, bool]]) -> None:  # noqa: ANN001
        self.tts = tts
        self.sink = sink            # async (kind, payload) -> None
        self.who = who              # speaker id -> (display name, voice id, is it a crew member aboard)
        self.q: asyncio.Queue = asyncio.Queue()
        self._n = 0
        self.first_audio: dict[int, float] = {}
        self.enqueued: dict[int, float] = {}
        self.low_priority = False   # set while an event turn is speaking
        self.busy_until = 0.0       # monotonic time when the line being played ends

    async def say(self, speaker: str, text: str, lang: str, tone: str) -> None:
        self._n += 1
        lid = self._n
        self.enqueued[lid] = time.perf_counter()
        name, _, crew = self.who(speaker)
        await self.sink("json", {"type": "line", "id": lid, "speaker": speaker, "name": name, "text": text,
                                 "lang": lang, "tone": tone, "channel": not crew})
        await self.q.put((lid, speaker, text, lang, self.low_priority))

    def busy_s(self) -> float:
        """Seconds of speech still ahead (playing + queued, estimated)."""
        return max(0.0, self.busy_until - time.monotonic()) + 3.0 * self.q.qsize()

    def drop_low_priority(self) -> int:
        keep, dropped = [], 0
        while not self.q.empty():
            item = self.q.get_nowait()
            self.q.task_done()
            if item[4]:
                dropped += 1
            else:
                keep.append(item)
        for item in keep:
            self.q.put_nowait(item)
        return dropped

    async def run(self) -> None:
        ready: asyncio.Queue = asyncio.Queue(maxsize=1)      # one line synthesised ahead

        async def synth() -> None:
            while True:
                lid, speaker, text, lang, _ = await self.q.get()
                chunks: asyncio.Queue = asyncio.Queue()
                await ready.put((lid, speaker, chunks))
                try:
                    voice = self.who(speaker)[1]
                    async for pcm in self.tts.stream(text, voice, lang if self.tts.supported(lang) else "en"):
                        await chunks.put(pcm)
                except Exception:  # noqa: BLE001
                    log.exception("voice line %s failed", lid)
                finally:
                    await chunks.put(None)
                    self.q.task_done()

        asyncio.create_task(synth())
        rate = self.tts.sample_rate
        while True:
            lid, speaker, chunks = await ready.get()
            wait = self.busy_until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await self.sink("json", {"type": "audio_begin", "line": lid, "speaker": speaker, "rate": rate})
            t_first, samples = None, 0
            while (pcm := await chunks.get()) is not None:
                if t_first is None:
                    t_first = time.monotonic()
                    self.first_audio[lid] = time.perf_counter()
                samples += len(pcm) // 2
                await self.sink("audio", struct.pack("<I", lid) + pcm)
                self.busy_until = t_first + samples / rate + self.GAP_S
            await self.sink("json", {"type": "audio_end", "line": lid})
            log.debug("voice line %d (%s): waited %.2f s, %.2f s of audio", lid, speaker, max(0.0, wait), samples / rate)
