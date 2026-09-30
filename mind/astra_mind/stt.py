"""The Captain's ears: push-to-talk audio in, text and language out, fast enough that an order feels heard at once.

- Backends (voice_stt_backends.py): Parakeet on the Neural Engine first (25 European languages, ~40x faster than the
  audio, no GPU); Whisper large-v3-turbo (WhisperKit) for every other language and for phrases Parakeet is unsure of;
  faster-whisper on the CPU as the portable last resort.
- The audio is trimmed to the speech (silence and breath never reach the recogniser: Whisper "hears" subtitles in
  silence) and, while the Captain still holds the key, a session decodes what has been said so far, so at release only
  the last words are left, or nothing at all.
- The result carries the language the Captain spoke (the crew answers in it): the text detector, the crew's own
  vocabulary, the engine's report and the language of the previous order are weighed together (voice_lang.py).
- The game's names are fixed afterwards (voice_glossary.py) or offered as a prompt where the engine takes one.

`python -m astra_mind.stt` prints which engines are available here; `--fetch` downloads the Parakeet model (`--fetch-portable`:
the ONNX export for machines without the Neural Engine helper).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field

import numpy as np

from .env import CACHE
from .voice_audio import f32_to_pcm16, pcm16_to_f32, resample, speech_frames, trim_speech
from .voice_glossary import GLOSSARY, Glossary
from .voice_lang import resolve_language
from .voice_stt_backends import (BackendResult, FasterWhisperBackend, ParakeetBackend, PARAKEET_LANGS, SherpaParakeetBackend, SttBackend,
                                 WhisperKitBackend, fetch_sherpa_model)

log = logging.getLogger("astra.stt")

RATE = 16000
MIN_SPEECH_S = 0.15                 # less than this is a key click or a breath, not an order
SURE_CONF = 0.86                    # Parakeet's own confidence above which its text is taken as it is
PAD_MS = 220.0                      # silence kept around the speech: the ends of words are quiet
BOOT_WAIT_S = 4.0                   # how long a first phrase waits for the fast engine before the other one answers it
IDLE_RELEASE_S = 600.0              # the second engine is let go after this long without a phrase

# things Whisper "hears" in silence or noise (its training data is full of subtitle credits)
_HALLUCINATION = re.compile(
    r"(amara\.org|sottotitoli|sous-?titr|untertitel|ondertitel|subt[ií]tulos|legendas|subtitles?\b|thanks? for (watching|listening)|"
    r"thank you for watching|gracias por ver|obrigad[oa] por assistir|grazie per (la visione|aver guardato)|merci d.avoir regard|"
    r"danke f[üu]r(s)? (das )?(zuschauen|zuh[öo]ren)|bedankt voor het kijken|\bcc by\b|www\.)", re.I)
_FILLER_ONLY = re.compile(r"^\W*(thank you|thanks|bye|you|okay|ok|hmm+|uh+|um+|ah+|eh+|mh+)\W*$", re.I)


@dataclass
class Transcript:
    text: str                                   # what the Captain said (names corrected); "" when nothing was understood
    lang: str                                   # the language he spoke: the crew answers in it
    lang_conf: float = 0.0
    backend: str = ""
    raw: str = ""                               # what the engine wrote, before the corrections
    fixes: list[tuple[str, str]] = field(default_factory=list)
    conf: float | None = None                   # the engine's own confidence, when it has one
    audio_s: float = 0.0                        # length of the recording
    speech_s: float = 0.0                       # of which speech
    latency_s: float = 0.0                      # from the end of the recording (finish) to this result
    decode_s: float = 0.0                       # time inside the engine
    partial_hit: bool = False                   # the result came from a decode made while the key was still held
    escalated: bool = False                     # a second engine was asked (uncertain phrase or another language)
    speech: bool = True                         # False: nothing that sounds like speech was recorded


class Recognizer:
    """Backends, language and names behind one object. `recognise(pcm16)` for a finished recording, `session()` for one
    that is still being made."""

    def __init__(self, backends: list[SttBackend] | None = None, glossary: Glossary = GLOSSARY, prior: str | None = None) -> None:
        if backends is None:
            # the fast engine for the 25 European languages: the Neural Engine helper here, the same model on the CPU elsewhere;
            # then the engines that know every language, for the phrases the first is unsure of
            backends = []
            if ParakeetBackend.available():
                backends.append(ParakeetBackend())
            elif SherpaParakeetBackend.available():
                backends.append(SherpaParakeetBackend())
            if WhisperKitBackend.available():
                backends.append(WhisperKitBackend())
            if FasterWhisperBackend.available():
                backends.append(FasterWhisperBackend())
            forced = os.environ.get("ASTRA_STT", "").lower()      # parakeet | parakeet-onnx | whisperkit | faster-whisper: tried first
            backends.sort(key=lambda b: 0 if b.name == forced else 1)
        self.backends = backends
        self.glossary = glossary
        self.prior = prior or self._saved_language()              # the language of the last order
        self._boot: asyncio.Task | None = None
        self._reaper: asyncio.Task | None = None
        self._up: dict[str, bool | None] = {}                     # True up, False failed, None not tried yet
        self.stats = {"n": 0, "escalated": 0, "partial_hits": 0, "empty": 0}

    @staticmethod
    def _saved_language() -> str:
        try:
            return (CACHE / "captain_lang.txt").read_text().strip() or "en"
        except OSError:
            return "en"

    @property
    def primary(self) -> SttBackend | None:
        return self.backends[0] if self.backends else None

    @property
    def fallback(self) -> SttBackend | None:
        return self.backends[1] if len(self.backends) > 1 else None

    # ------------------------------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        """Bring the first engine up in the background (the first ever start downloads and compiles a model: minutes) so
        the mind can open its door at once."""
        if self._boot is None:
            self._boot = asyncio.create_task(self._bring_up())
            self._reaper = asyncio.create_task(self._reap_idle())

    async def _reap_idle(self) -> None:
        """The second engine (Whisper, 1.5 GB) is started when a phrase needs it and let go after ten idle minutes."""
        while True:
            await asyncio.sleep(60)
            for b in self.backends[1:]:
                last = getattr(b, "last_used", None)
                if self._up.get(b.name) and last is not None and time.monotonic() - last > IDLE_RELEASE_S:
                    log.info("%s idle for %.0f minutes: released", b.name, IDLE_RELEASE_S / 60)
                    b.stop()
                    self._up[b.name] = None

    async def _bring_up(self) -> None:
        for b in self.backends:
            try:
                self._up[b.name] = await b.start()
            except Exception:  # noqa: BLE001
                log.exception("%s failed to start", b.name)
                self._up[b.name] = False
            if self._up[b.name]:
                break                                             # the others start only when they are needed (a model each)
        if not any(self._up.values()):
            log.error("no speech recogniser could start: the Captain can only type")

    async def ready(self) -> bool:
        await self.start()
        assert self._boot is not None
        await asyncio.shield(self._boot)
        return any(self._up.values())

    def stop_server(self) -> None:
        for b in self.backends:
            b.stop()

    async def close(self) -> None:
        for b in self.backends:
            await b.close()

    def session(self, rate: int = RATE, partial_every_s: float = 1.0) -> "RecognitionSession":
        return RecognitionSession(self, rate, partial_every_s)

    # ------------------------------------------------------------------------------------------ legacy call
    async def transcribe(self, pcm16: bytes, rate: int = RATE, language: str | None = None, glossary: bool = True) -> tuple[str, str]:
        """(text, language): the first version's signature (the offline tools and the voice casting call it)."""
        await self.ready()                     # (offline tools want the answer, however long the first start takes)
        tr = await self.recognise(pcm16, rate, lang_hint=language, use_glossary=glossary)
        return tr.text, tr.lang

    # ------------------------------------------------------------------------------------------ the work
    async def recognise(self, pcm16: bytes, rate: int = RATE, *, lang_hint: str | None = None, use_glossary: bool = True,
                        raw_audio: bool = False) -> Transcript:
        """Text and language of a finished recording. `raw_audio` skips the silence trimming (already-clean audio)."""
        t_in = time.perf_counter()
        x = pcm16_to_f32(pcm16)
        if rate != RATE:
            x = resample(x, rate, RATE)
        audio_s = len(x) / RATE
        if raw_audio:
            trimmed, speech_s = x, audio_s
        else:
            trimmed, _, speech_s = trim_speech(x, RATE, pad_ms=PAD_MS)
        if speech_s < MIN_SPEECH_S or len(trimmed) < int(RATE * 0.2):
            self.stats["empty"] += 1
            return Transcript(text="", lang=lang_hint or self.prior, audio_s=audio_s, speech_s=speech_s, speech=False,
                              latency_s=time.perf_counter() - t_in)
        tr = await self._decode(f32_to_pcm16(trimmed), lang_hint, use_glossary)
        tr.audio_s, tr.speech_s = audio_s, speech_s
        tr.latency_s = time.perf_counter() - t_in
        self.stats["n"] += 1
        return tr

    async def _usable(self, backend: SttBackend, wait: bool) -> bool:
        """Is this engine up? One that has not been tried is started now; the first engine, still starting in the
        background, is waited for only when `wait`."""
        state = self._up.get(backend.name)
        if state is not None:
            return state
        if backend is self.primary:
            if not wait or self._boot is None:
                return False
            try:
                await asyncio.wait_for(asyncio.shield(self._boot), timeout=BOOT_WAIT_S)
            except asyncio.TimeoutError:
                return False
            return bool(self._up.get(backend.name))
        try:
            self._up[backend.name] = await backend.start()
        except Exception:  # noqa: BLE001
            log.exception("%s failed to start", backend.name)
            self._up[backend.name] = False
        return bool(self._up[backend.name])

    async def _engine(self, backend: SttBackend, pcm: bytes, lang: str | None, use_glossary: bool, wait: bool = True) -> BackendResult | None:
        if not await self._usable(backend, wait):
            return None
        try:
            return await backend.transcribe(pcm, lang=lang, prompt=self.glossary.prompt() if (use_glossary and backend.takes_prompt) else None)
        except Exception:  # noqa: BLE001
            log.exception("%s failed on a phrase", backend.name)
            return None

    async def _decode(self, pcm: bytes, lang_hint: str | None, use_glossary: bool) -> Transcript:
        await self.start()
        prior = lang_hint or self.prior
        prim, fall = self.primary, self.fallback
        escalated = False
        res: BackendResult | None = None
        # a Captain who speaks a language the fast engine does not know goes straight to the one that does
        if prim is not None and not prim.speaks(prior) and fall is not None:
            res = await self._engine(fall, pcm, lang_hint, use_glossary)
            escalated = res is not None
        if res is None and prim is not None:
            res = await self._engine(prim, pcm, lang_hint if (lang_hint and prim.speaks(lang_hint)) else None, use_glossary)
        if res is None and fall is not None:
            res = await self._engine(fall, pcm, lang_hint, use_glossary)
            escalated = res is not None
        if res is None:
            return Transcript(text="", lang=prior)
        # the fast engine is unsure (another language, noise, a very short phrase): ask the one that knows every language
        if res.backend == getattr(prim, "name", "") and res.conf is not None and res.conf < SURE_CONF and fall is not None and not escalated:
            second = await self._engine(fall, pcm, lang_hint, use_glossary)
            if second is not None and second.text:
                escalated = True
                res = self._arbitrate(res, second, prior)
        return self._finish(res, prior, escalated, use_glossary)

    @staticmethod
    def _arbitrate(a: BackendResult, b: BackendResult, prior: str) -> BackendResult:
        """Two engines disagree about an uncertain phrase: the one whose language the Captain plausibly speaks wins."""
        if not a.text:
            return b
        if b.lang and b.lang not in PARAKEET_LANGS:
            return b                                        # Japanese, Chinese, Arabic...: Parakeet only romanises them
        _, ca = resolve_language(a.text, prior)
        if ca >= 0.6 or b.lang is None:
            return a
        _, cb = resolve_language(b.text, prior, backend_lang=b.lang)
        return b if cb > ca else a

    def _finish(self, res: BackendResult, prior: str, escalated: bool, use_glossary: bool) -> Transcript:
        text = re.sub(r"\s+", " ", res.text).strip()
        raw = text
        if not res.backend.startswith("parakeet") and (_HALLUCINATION.search(text) or _FILLER_ONLY.match(text)):
            log.info("dropped a recogniser hallucination: %r", text)
            text = ""
        fixes: list[tuple[str, str]] = []
        if text and use_glossary:
            text, fixes = self.glossary.correct(text)
        lang, lconf = resolve_language(text, prior, res.lang)
        if text and lconf >= 0.45:
            self.prior = lang
        if escalated:
            self.stats["escalated"] += 1
        return Transcript(text=text, lang=lang, lang_conf=lconf, backend=res.backend, raw=raw, fixes=fixes, conf=res.conf,
                          decode_s=res.seconds, escalated=escalated)


class RecognitionSession:
    """One recording that is still being made. `feed()` the audio as it arrives; every second or so the speech so far is
    decoded in the background. `finish()` (the key is released) returns at once when the last decode already covers
    everything that was said, and otherwise decodes the whole recording."""

    def __init__(self, rec: Recognizer, rate: int = RATE, partial_every_s: float = 1.0) -> None:
        self.rec = rec
        self.rate = rate
        self.every = partial_every_s
        self._chunks: list[bytes] = []
        self._n = 0                                   # samples received
        self._last_n = 0                              # samples the running or last partial covers
        self._task: asyncio.Task | None = None
        self._best: tuple[int, Transcript] | None = None
        self._closed = False

    def feed(self, pcm16: bytes) -> None:
        if self._closed or not pcm16:
            return
        self._chunks.append(pcm16)
        self._n += len(pcm16) // 2
        if (self._task is None or self._task.done()) and self._n - self._last_n >= int(self.every * self.rate):
            self._last_n = self._n
            self._task = asyncio.get_running_loop().create_task(self._partial(self._n))

    async def _partial(self, n: int) -> None:
        try:
            tr = await self.rec.recognise(b"".join(self._chunks)[: n * 2], self.rate)
            if tr.speech and tr.text and not self._closed:
                self._best = (n, tr)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.debug("partial decode failed", exc_info=True)

    def cancel(self) -> None:
        self._closed = True
        if self._task and not self._task.done():
            self._task.cancel()

    async def finish(self, pcm16: bytes | None = None) -> Transcript:
        """The result. `pcm16` is the whole recording when the caller has it already trimmed or complete; else the fed audio."""
        t0 = time.perf_counter()
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=1.5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        self._closed = True
        pcm = pcm16 if pcm16 is not None else b"".join(self._chunks)
        best = self._best
        if best is not None and not self._tail_has_speech(pcm, best[0]):
            tr = best[1]
            tr.latency_s = time.perf_counter() - t0
            tr.partial_hit = True
            self.rec.stats["partial_hits"] += 1
            return tr
        out = await self.rec.recognise(pcm, self.rate)
        out.latency_s = time.perf_counter() - t0
        return out

    def _tail_has_speech(self, pcm: bytes, covered: int) -> bool:
        """Was anything said after the point the last decode reached?"""
        on = speech_frames(pcm16_to_f32(pcm), self.rate)
        first = int(covered / (self.rate * 0.020))
        return bool(on[first:].any()) if first < len(on) else False


# the first version's name for the recogniser (server.py, voice_casting.py and the offline tools import it)
WhisperKit = Recognizer


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m astra_mind.stt", description="Which speech engines this machine can run")
    ap.add_argument("--fetch", action="store_true",
                    help="download what this machine needs: the Parakeet model through the helper (Apple Silicon) or the ONNX export (elsewhere)")
    ap.add_argument("--fetch-portable", action="store_true", help="download the ONNX export of Parakeet (any platform, ~490 MB)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)                     # (its lines carry the download's long signed address)
    print("Parakeet (Neural Engine):", "yes" if ParakeetBackend.available() else "no (build it: mind/stt_server/build.sh)")
    print("Parakeet (ONNX, CPU, any platform):", "yes" if SherpaParakeetBackend.available() else "no (uv sync --extra portable; --fetch-portable)")
    print("WhisperKit:", "yes" if WhisperKitBackend.available() else "no (whisperkit-cli)")
    print("faster-whisper:", "yes" if FasterWhisperBackend.available() else "no (uv sync --extra portable)")
    if args.fetch_portable or (args.fetch and not ParakeetBackend.available()):
        print("Parakeet (ONNX) model:", fetch_sherpa_model())
    elif args.fetch:
        async def go() -> None:
            b = ParakeetBackend()
            print("ready:", await b.start())
            b.stop()
        asyncio.run(go())


if __name__ == "__main__":
    main()
