"""Local text-to-speech with Pocket TTS (Kyutai, CPU) and a small mastering chain, so every officer sounds like a person on
the same intercom: the pauses the model leaves between sentences are shortened, the speech is a little faster (WSOLA
time stretch: same pitch and timbre), every voice is brought to the same loudness (calibrated per voice and language) and
a look-ahead limiter keeps the peaks clean.

- One model per language (~430 MB each); the two most recently used stay in memory. A language is prepared ahead of time
  (`prepare`) so that a Captain who switches language does not wait for a model to load in the middle of an answer.
- Voice states are cached per (language, voice). Nothing touches the network once the files are in the Hugging Face cache
  (an offline machine, or a slow connection, used to freeze the whole crew for ~20 s while a model "checked for updates").
- Generation runs in a worker thread that can be stopped at once (barge-in): `SpeechStream.stop()`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .env import CACHE
from .voice_audio import Limiter, PauseCompressor, TimeStretcher, f32_to_pcm16, frame_rms_db, from_db, integrated_lufs
from .voice_qos import boost_thread

log = logging.getLogger("astra.tts")

MODEL_FOR_LANG = {"it": "italian", "en": "english", "es": "spanish", "fr": "french", "de": "german",
                  "pt": "portuguese", "nl": "dutch"}
SAMPLE_RATE = 24000

SPEED = float(os.environ.get("ASTRA_TTS_SPEED", "1.12"))             # 1.0 = the model's own pace
TARGET_LUFS = float(os.environ.get("ASTRA_TTS_LUFS", "-19"))         # every voice's integrated loudness
CEILING_DB = -1.5                                                     # peak ceiling of the limiter
MAX_PAUSE_MS = float(os.environ.get("ASTRA_TTS_PAUSE_MS", "300"))    # longest silence kept inside a line
MAX_RESIDENT = int(os.environ.get("ASTRA_TTS_RESIDENT", "2"))        # language models kept in memory
BOOST = os.environ.get("ASTRA_VOICE_QOS", "1") != "0"                # raise the speech threads' priority (voice_qos.py)
# how a line is delivered changes the pace a little (the timbre and the words come from the officer's model)
TONE_SPEED = {"calm": -0.03, "warm": -0.03, "weary": -0.06, "measured": -0.02, "respectful": -0.02, "contemptuous": -0.02,
              "cold": 0.0, "focused": 0.02, "urgent": 0.06, "furious": 0.05, "shaken": 0.03}

_GAINS_FILE = Path(__file__).with_name("voice_gains.json")           # shipped: measured for every catalogue voice
_OVERRIDES_FILE = Path(__file__).with_name("voice_overrides.json")   # shipped: who speaks for a voice hard to understand in a language
_USER_GAINS = CACHE / "voice_gains.json"                              # measured on this machine for what was missing

CALIBRATION = {
    "en": ["Coming to zero four five, mark ten, half ahead, Captain.", "Red alert, shields forward, weapons hot.",
           "Unknown contact at fifty kilometres, drifting cold, no transponder."],
    "it": ["Rotta zero quattro cinque, punto dieci, mezza forza, capitano.", "Allarme rosso, scudi a prua, armi pronte.",
           "Contatto sconosciuto a cinquanta chilometri, deriva a freddo, nessuna risposta."],
    "es": ["Rumbo cero cuatro cinco, marca diez, media máquina, capitán.", "Alerta roja, escudos a proa, armas listas.",
           "Contacto desconocido a cincuenta kilómetros, a la deriva, sin respuesta."],
    "fr": ["Cap zéro quatre cinq, cote dix, demi-vitesse, capitaine.", "Alerte rouge, boucliers à l'avant, armes prêtes.",
           "Contact inconnu à cinquante kilomètres, à la dérive, aucune réponse."],
    "de": ["Kurs null vier fünf, Neigung zehn, halbe Kraft voraus, Captain.", "Roter Alarm, Schilde nach vorn, Waffen bereit.",
           "Unbekannter Kontakt in fünfzig Kilometern, treibt ohne Antrieb, keine Antwort."],
    "pt": ["Rumo zero quatro cinco, marca dez, meia força, capitão.", "Alerta vermelho, escudos à proa, armas prontas.",
           "Contato desconhecido a cinquenta quilômetros, à deriva, sem resposta."],
    "nl": ["Koers nul vier vijf, hoek tien, halve kracht vooruit, kapitein.", "Rood alarm, schilden naar voren, wapens gereed.",
           "Onbekend contact op vijftig kilometer, drijft koud, geen antwoord."],
}


def _cache_has_pocket_tts() -> bool:
    home = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    return (home / "hub" / "models--kyutai--pocket-tts").exists()


# With the files already in the cache, never ask the Hub "is there a newer one?" (set before huggingface_hub is imported)
if _cache_has_pocket_tts():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")


def _online_retry(fn):
    """Call fn(); if the Hub is switched off and the file was not in the cache after all, allow the network once."""
    try:
        return fn()
    except Exception:  # noqa: BLE001
        import huggingface_hub.constants as hc
        if not hc.HF_HUB_OFFLINE:
            raise
        log.warning("not in the Hugging Face cache: fetching it")
        hc.HF_HUB_OFFLINE = False
        try:
            return fn()
        finally:
            hc.HF_HUB_OFFLINE = True


@dataclass
class VoiceProfile:
    gain_db: float = 0.0
    lufs: float = TARGET_LUFS               # loudness of the voice before the gain
    peak_db: float = -3.0


class SpeechStream:
    """The audio of one line, as it is generated: an async iterator of PCM16 (mono, `sample_rate`) chunks. While it runs
    it learns the line's shape: `boundaries` are the pauses (seconds into the audio) where the voice can stop cleanly,
    `seconds` how much audio there is so far, `done` when generation has finished."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.q: asyncio.Queue = asyncio.Queue()
        self.stop_event = threading.Event()
        self.samples = 0
        self.boundaries: list[float] = []
        self.done = False
        self.error: Exception | None = None
        self.t_start = time.perf_counter()
        self.t_first: float | None = None          # seconds from the start of generation to the first chunk
        self.t_done: float | None = None

    @property
    def seconds(self) -> float:
        return self.samples / self.sample_rate

    def stop(self) -> None:
        """Stop generating now (the line will not be spoken)."""
        self.stop_event.set()

    def __aiter__(self) -> "SpeechStream":
        return self

    async def __anext__(self) -> bytes:
        item = await self.q.get()
        if item is None:
            if self.error:
                raise self.error
            raise StopAsyncIteration
        return item

    async def aclose(self) -> None:
        self.stop()


class _PauseFinder:
    """Finds the pauses in finished audio as it streams by (10 ms frames, 90 ms or more of quiet)."""

    def __init__(self, sr: int, min_ms: float = 90.0) -> None:
        self.frame = int(sr * 0.010)
        self.min = int(min_ms / 10)
        self._carry = np.zeros(0, dtype=np.float32)
        self._t = 0                    # frames seen
        self._ref = -120.0
        self._run = 0
        self.found: list[float] = []   # centre of each pause, seconds into the audio

    def feed(self, x: np.ndarray) -> None:
        buf = np.concatenate([self._carry, x])
        n = len(buf) // self.frame
        self._carry = buf[n * self.frame:]
        if n == 0:
            return
        for v in frame_rms_db(buf[: n * self.frame], self.frame):
            self._ref = max(float(v), self._ref - 0.03)
            if v < max(-58.0, self._ref - 30.0):
                self._run += 1
            else:
                if self._run >= self.min and self._t - self._run > 0:
                    self.found.append((self._t - self._run / 2) * 0.010)
                self._run = 0
            self._t += 1


class TTSEngine:
    def __init__(self, speed: float | None = None, target_lufs: float | None = None, max_resident: int | None = None) -> None:
        self.sample_rate = SAMPLE_RATE
        self.speed = SPEED if speed is None else speed
        self.target_lufs = TARGET_LUFS if target_lufs is None else target_lufs
        self.max_resident = max_resident or MAX_RESIDENT
        self._models: OrderedDict[str, object] = OrderedDict()            # language name -> model, least recently used first
        self._voices: dict[tuple[str, str], object] = {}
        self._profiles: dict[tuple[str, str], VoiceProfile] = {}
        self._lock = threading.RLock()                                       # one generation at a time: they would only fight for the CPU
        self._shipped = self._read_gains(_GAINS_FILE)
        self._user = self._read_gains(_USER_GAINS)
        # (language, voice) -> the voice that speaks instead where the first is hard to understand (voice_casting.py)
        self.overrides: dict[tuple[str, str], str] = {tuple(k.split("/", 1)): v for k, v in self._read_gains(_OVERRIDES_FILE).items()}

    # ------------------------------------------------------------------------------------------ facts
    def supported(self, lang: str) -> bool:
        return lang in MODEL_FOR_LANG

    def loaded(self, lang: str) -> bool:
        return MODEL_FOR_LANG.get(lang, "english") in self._models

    @staticmethod
    def _read_gains(path: Path) -> dict[str, dict[str, float]]:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}

    def voice_for(self, voice: str, lang: str) -> str:
        return self.overrides.get((lang, voice), voice)

    # ------------------------------------------------------------------------------------------ models
    def _model(self, lang: str):
        """The language's model, loaded if need be (the least recently used one leaves when too many are resident)."""
        name = MODEL_FOR_LANG.get(lang, "english")
        with self._lock:
            if name in self._models:
                self._models.move_to_end(name)
                return self._models[name]
            from pocket_tts import TTSModel
            t0 = time.perf_counter()
            model = _online_retry(lambda: TTSModel.load_model(language=name))
            self._models[name] = model
            self.sample_rate = int(model.sample_rate)
            log.info("TTS model %s loaded in %.1f s", name, time.perf_counter() - t0)
            while len(self._models) > self.max_resident:
                old, _ = self._models.popitem(last=False)
                for k in [k for k in self._voices if k[0] == old]:
                    del self._voices[k]
                log.info("TTS model %s released", old)
            return model

    def _voice(self, lang: str, voice: str):
        name = MODEL_FOR_LANG.get(lang, "english")
        key = (name, voice)
        with self._lock:
            model = self._model(lang)
            if key not in self._voices:
                t0 = time.perf_counter()
                try:
                    self._voices[key] = _online_retry(lambda: model.get_state_for_audio_prompt(voice))
                except Exception:  # noqa: BLE001 - a voice this language does not have: its default one speaks instead
                    from pocket_tts.default_parameters import get_default_voice_for_language
                    fallback = get_default_voice_for_language(name)
                    log.warning("voice %s missing for %s: using %s", voice, name, fallback)
                    self._voices[key] = model.get_state_for_audio_prompt(fallback)
                log.info("TTS voice %s/%s prepared in %.2f s", name, voice, time.perf_counter() - t0)
            return self._voices[key]

    def warm(self, lang: str, voices: list[str], calibrate: bool = True) -> None:
        """Load the language, prepare the voices, calibrate the ones without a known loudness and speak one short line so
        the first real one is as fast as the rest (blocking: call it from a thread). The lock is taken per step: lines
        being spoken are never held up for the whole warm-up."""
        if not self.supported(lang):
            return
        for v in voices:
            v = self.voice_for(v, lang)
            self._voice(lang, v)
            if calibrate:
                self.profile(lang, v)
        self.render("Ready.", voices[0] if voices else "alba", lang, gain_db=0.0, limit=False)

    async def prepare(self, lang: str, voices: list[str] | None = None) -> None:
        """Get a language ready in the background (a Captain who has just switched to it is about to be answered in it)."""
        if not self.supported(lang) or (self.loaded(lang) and not voices):
            return
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.warm(lang, voices or ["alba"], calibrate=bool(voices)))

    # ------------------------------------------------------------------------------------------ loudness
    def profile(self, lang: str, voice: str) -> VoiceProfile:
        """The gain that brings this voice to the target loudness in this language (shipped table, else measured once)."""
        key = (lang, voice)
        if key in self._profiles:
            return self._profiles[key]
        k = f"{lang}/{voice}"
        rec = self._shipped.get(k) or self._user.get(k)
        if rec is None:
            rec = self._measure(lang, voice)
            self._user[k] = rec
            try:
                _USER_GAINS.parent.mkdir(parents=True, exist_ok=True)
                _USER_GAINS.write_text(json.dumps(self._user, indent=1, sort_keys=True))
            except OSError:
                pass
        p = VoiceProfile(gain_db=self._gain_for(rec["lufs"], rec["peak"]), lufs=rec["lufs"], peak_db=rec["peak"])
        self._profiles[key] = p
        return p

    def _gain_for(self, lufs: float, peak: float) -> float:
        """Gain to the target loudness, but never more than the limiter can carry (6 dB of peak reduction at most: beyond
        that a spiky voice would sound crushed, so it stays a little quieter instead)."""
        return float(np.clip(min(self.target_lufs - lufs, CEILING_DB - peak + 6.0), -12.0, 18.0))

    def measure(self, lang: str, voice: str) -> dict[str, float]:
        """Loudness and peak of a voice as it leaves the model (through the pause and speed stages, before any gain)."""
        audio = np.concatenate([self.render(t, voice, lang, gain_db=0.0, limit=False) for t in CALIBRATION.get(lang, CALIBRATION["en"])])
        lufs = integrated_lufs(audio, self.sample_rate)
        pk = 20 * float(np.log10(max(float(np.percentile(np.abs(audio), 99.9)), 1e-6)))
        return {"lufs": round(lufs, 2), "peak": round(pk, 2)}

    def _measure(self, lang: str, voice: str) -> dict[str, float]:
        rec = self.measure(lang, voice)
        log.info("voice %s/%s measured: %.1f LUFS, peak %.1f dB", lang, voice, rec["lufs"], rec["peak"])
        return rec

    # ------------------------------------------------------------------------------------------ generation
    def _run(self, text: str, voice: str, lang: str, speed: float, gain_db: float, limit: bool, stop: threading.Event,
             stream: SpeechStream | None):
        """Generator of processed float32 chunks for one line: pauses shortened, sped up, gained, limited."""
        sr = self.sample_rate
        with self._lock:
            model = self._model(lang)
            state = self._voice(lang, voice)
            sr = self.sample_rate
            pauses, stretch = PauseCompressor(sr, max_pause_ms=MAX_PAUSE_MS), TimeStretcher(sr, speed)
            gain = from_db(gain_db)
            lim = Limiter(sr, ceiling_db=CEILING_DB) if limit else None
            finder = _PauseFinder(sr)
            samples = 0

            def emit(a: np.ndarray) -> np.ndarray | None:
                nonlocal samples
                if len(a) == 0:
                    return None
                a = a * gain
                if lim is not None:
                    a = lim.process(a)
                    if len(a) == 0:
                        return None
                finder.feed(a)
                samples += len(a)
                if stream is not None:
                    stream.samples = samples
                    stream.boundaries = list(finder.found)
                return a

            for chunk in model.generate_audio_stream(state, text, stop=stop):
                a = chunk.detach().cpu().numpy().astype(np.float32).reshape(-1)
                out = emit(stretch.process(pauses.process(a)))
                if out is not None:
                    yield out
                if stop.is_set():
                    return
            if stop.is_set():
                return
            out = emit(stretch.process(pauses.flush()))
            if out is not None:
                yield out
            out = emit(stretch.flush())
            if out is not None:
                yield out
            if lim is not None:
                last = lim.flush()
                if len(last):
                    finder.feed(last)
                    samples += len(last)
                    if stream is not None:
                        stream.samples = samples
                        stream.boundaries = list(finder.found)
                    yield last

    def stream(self, text: str, voice: str, lang: str, *, speed: float | None = None, tone: str | None = None) -> SpeechStream:
        """Start speaking `text`: an async iterator of PCM16 chunks (call it from the event loop). It runs in a worker
        thread; `stop()` on the result ends it at once."""
        lang = lang if self.supported(lang) else "en"
        voice = self.voice_for(voice, lang)
        sp = max(0.8, min(1.5, (self.speed if speed is None else speed) + TONE_SPEED.get(tone or "", 0.0)))
        st = SpeechStream(self.sample_rate)
        loop = asyncio.get_running_loop()

        def put(item) -> None:
            loop.call_soon_threadsafe(st.q.put_nowait, item)

        def work() -> None:
            if BOOST:
                boost_thread()               # performance cores, like the game (threads made below inherit it)
            try:
                prof = self.profile(lang, voice)
                first = True
                for a in self._run(text, voice, lang, sp, prof.gain_db, True, st.stop_event, st):
                    if first:
                        st.t_first = time.perf_counter() - st.t_start
                        st.sample_rate = self.sample_rate
                        first = False
                    put(f32_to_pcm16(a))
            except Exception as exc:  # noqa: BLE001 - reported to the consumer
                log.exception("TTS failed")
                st.error = exc
            finally:
                st.done = True
                st.t_done = time.perf_counter() - st.t_start
                put(None)

        threading.Thread(target=work, name="tts", daemon=True).start()
        return st

    def render(self, text: str, voice: str, lang: str, speed: float | None = None, gain_db: float | None = None, limit: bool = True) -> np.ndarray:
        """The whole line as float32, blocking (calibration, casting, benchmarks)."""
        lang = lang if self.supported(lang) else "en"
        voice = self.voice_for(voice, lang)
        sp = self.speed if speed is None else speed
        g = self.profile(lang, voice).gain_db if gain_db is None else gain_db
        out = list(self._run(text, voice, lang, sp, g, limit, threading.Event(), None))
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)
