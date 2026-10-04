"""Local text-to-speech with Pocket TTS (Kyutai, CPU) and a small mastering chain, so every officer sounds like a person on
the same intercom: the pauses the model leaves between sentences are shortened, the speech is a little faster (WSOLA
time stretch: same pitch and timbre), every voice is brought to the same loudness (calibrated per voice and language) and
a look-ahead limiter keeps the peaks clean.

- One model per language (~430 MB each); the two most recently used stay in memory. A language is prepared ahead of time
  (`prepare`) so that a Captain who switches language does not wait for a model to load in the middle of an answer.
- Voice states are cached per (language, voice). Nothing touches the network once the files are in the Hugging Face cache
  (an offline machine, or a slow connection, used to freeze the whole crew for ~20 s while a model "checked for updates").
- Generation runs in a worker thread that can be stopped at once (barge-in): `SpeechStream.stop()`.
- A language Pocket TTS does not speak (Japanese, Russian...), or one it speaks whose model is not on the machine yet, is said
  by the operating system's own voices (macOS `say`, Windows SAPI), mastered the same way; the line is never held up for a download
  and never dropped for want of a model.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .env import CACHE
from .voice_audio import Limiter, PauseCompressor, TimeStretcher, f32_to_pcm16, frame_rms_db, from_db, integrated_lufs, resample
from .voice_qos import boost_thread
from .voice_text import speakable

log = logging.getLogger("astra.tts")

MODEL_FOR_LANG = {"it": "italian", "en": "english", "es": "spanish", "fr": "french", "de": "german",
                  "pt": "portuguese", "nl": "dutch"}
SAMPLE_RATE = 24000

SPEED = float(os.environ.get("ASTRA_TTS_SPEED", "1.12"))             # 1.0 = the model's own pace
TARGET_LUFS = float(os.environ.get("ASTRA_TTS_LUFS", "-19"))         # every voice's integrated loudness
CEILING_DB = -1.5                                                     # peak ceiling of the limiter
MIN_CPS = 5.0                                                         # slowest speech there is, characters a second (a cap on runaway generation)
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


# the catalogue: who is a woman, who a man (the system voices that stand in for other languages are picked by it)
GENDER = {"alba": "f", "anna": "f", "azelma": "f", "bill_boerst": "m", "caro_davy": "f", "charles": "m", "cosette": "f",
          "eponine": "f", "estelle": "f", "eve": "f", "fantine": "f", "george": "m", "giovanni": "m", "jane": "f",
          "javert": "m", "jean": "m", "juergen": "m", "lola": "f", "marius": "m", "mary": "f", "michael": "m", "paul": "m",
          "peter_yearsley": "m", "rafael": "m", "stuart_bell": "m", "vera": "f", "daan": "m"}
VOICES = list(GENDER)

# macOS's own voices, for the languages Pocket TTS does not speak (a Captain who speaks Japanese, Russian or Arabic to his crew
# is answered in it, in a plainer voice, instead of by the English model reading foreign text): (woman, man) in order of preference.
# Windows has no such table: its voices are whatever the machine has installed, chosen by language and sex (_WindowsVoices)
SYSTEM_VOICES = {"it": (("Alice", "Federica"), ("Eddy (Italian (Italy))", "Reed (Italian (Italy))")),
                 "en": (("Samantha", "Karen"), ("Daniel", "Eddy (English (US))")),
                 "es": (("Mónica", "Paulina"), ("Eddy (Spanish (Spain))", "Jorge")),
                 "fr": (("Amélie", "Eddy (French (France))"), ("Thomas", "Jacques")),
                 "de": (("Anna", "Eddy (German (Germany))"), ("Eddy (German (Germany))", "Reed (German (Germany))")),
                 "pt": (("Luciana", "Joana"), ("Eddy (Portuguese (Brazil))", "Reed (Portuguese (Brazil))")),
                 "nl": (("Ellen", "Claire"), ("Xander", "Ellen")),
                 "ja": (("Kyoko", "O-Ren"), ("Otoya", "Hattori")), "zh": (("Tingting", "Meijia", "Sinji"), ("Sinji", "Tingting")),
                 "ko": (("Yuna",), ("Yuna",)), "ru": (("Milena",), ("Yuri", "Milena")), "pl": (("Zosia", "Ewa"), ("Krzysztof", "Zosia")),
                 "ar": (("Majed", "Laila"), ("Majed", "Tarik")), "hi": (("Lekha",), ("Rishi", "Lekha")), "tr": (("Yelda",), ("Cem", "Yelda")),
                 "sv": (("Alva",), ("Oskar", "Alva")), "da": (("Sara",), ("Magnus", "Sara")), "fi": (("Satu",), ("Satu",)),
                 "el": (("Melina",), ("Nikos", "Melina")), "cs": (("Zuzana",), ("Zuzana",)), "uk": (("Lesya",), ("Lesya",)),
                 "ro": (("Ioana",), ("Ioana",)), "hu": (("Tünde",), ("Tünde",)), "sk": (("Laura",), ("Laura",)), "th": (("Kanya",), ("Kanya",)),
                 "he": (("Carmit",), ("Carmit",)), "nb": (("Nora",), ("Henrik", "Nora"))}


class _MacVoices:
    """`say` (macOS): the whole line is made at once (a fraction of a second), then mastered like the others."""

    def __init__(self) -> None:
        self._have: set[str] | None = None

    def installed(self) -> set[str]:
        if self._have is None:
            self._have = set()
            try:
                out = subprocess.run(["say", "-v", "?"], capture_output=True, timeout=10).stdout.decode("utf-8", errors="replace")       # portable-ok: macOS; _WindowsVoices does it on Windows
                for line in out.splitlines():
                    head = line.split("#")[0].rstrip()
                    parts = head.rsplit(None, 1)
                    if parts:
                        self._have.add(parts[0].strip())
            except (OSError, subprocess.SubprocessError):
                pass
        return self._have

    def pick(self, lang: str, gender: str = "f") -> str | None:
        table = SYSTEM_VOICES.get(lang)
        if not table:
            return None
        have = self.installed()
        mine, other = (table[0], table[1]) if gender == "f" else (table[1], table[0])
        return next((v for v in (*mine, *other) if v in have), None)         # (a voice of the other sex beats none)

    def render(self, text: str, voice: str, sr: int) -> np.ndarray:
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            r = subprocess.run(["say", "-v", voice, "-o", f.name, f"--data-format=LEI16@{sr}", text], capture_output=True, timeout=60)   # portable-ok: macOS; _WindowsVoices does it on Windows
            if r.returncode != 0:
                raise RuntimeError(f"say failed: {r.stderr.decode(errors='replace')[:120]}")
            x, rate = sf.read(f.name, dtype="float32")
        return x if x.ndim == 1 else x[:, 0]


# Windows SAPI, through PowerShell's System.Speech (every Windows has both). The scripts reach PowerShell as -EncodedCommand (UTF-16 in base64:
# no quoting to get wrong) and the line, the voice and the file travel in environment variables, so no text is ever part of a command line.
_SAPI_LIST = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($v in $s.GetInstalledVoices()) {
    if ($v.Enabled) { $i = $v.VoiceInfo; '{0}|{1}|{2}' -f $i.Name, $i.Culture.Name, $i.Gender }
}
$s.Dispose()
"""
_SAPI_SAY = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SelectVoice($env:ASTRA_SAPI_VOICE)
$s.SetOutputToWaveFile($env:ASTRA_SAPI_OUT)
$s.Speak($env:ASTRA_SAPI_TEXT)
$s.Dispose()
"""


def powershell_command(script: str) -> list[str]:
    """The command line that runs a PowerShell script without a profile or a prompt and without any quoting of it (-EncodedCommand)."""
    import base64
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]


def parse_sapi_listing(text: str) -> dict[str, tuple[str, str]]:
    """`Name|culture|Gender` lines (the listing script's output) -> {voice name: (language code, 'f' | 'm' | '')}."""
    voices: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        parts = [p.strip() for p in line.strip().lstrip("\ufeff").split("|")]
        if len(parts) == 3 and parts[0] and parts[1]:
            g = parts[2].lower()
            voices[parts[0]] = (parts[1].split("-")[0].lower(), "m" if g.startswith("m") else "f" if g.startswith("f") else "")
    return voices


class _WindowsVoices:
    """SAPI (Windows): the voices the machine has, by language and sex. A line takes a second or two (a PowerShell to start): they are
    the stand-in for a language Pocket TTS lacks and for one whose model is still being downloaded, not the voices of the game."""

    def __init__(self) -> None:
        self._voices: dict[str, tuple[str, str]] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _run(script: str, env: dict[str, str] | None = None, timeout: float = 30.0) -> subprocess.CompletedProcess:
        return subprocess.run(powershell_command(script), capture_output=True, timeout=timeout, env=env,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def catalogue(self) -> dict[str, tuple[str, str]]:
        with self._lock:
            if self._voices is None:
                self._voices = {}
                try:
                    r = self._run(_SAPI_LIST)
                    if r.returncode == 0:
                        self._voices = parse_sapi_listing(r.stdout.decode("utf-8", errors="replace"))
                    else:
                        log.warning("the Windows voices could not be listed: %s", r.stderr.decode(errors="replace")[:160])
                except (OSError, subprocess.SubprocessError):
                    log.warning("the Windows voices could not be listed (no PowerShell?)")
            return self._voices

    def installed(self) -> set[str]:
        return set(self.catalogue())

    def pick(self, lang: str, gender: str = "f") -> str | None:
        voices = self.catalogue()
        mine = [n for n, (lg, g) in voices.items() if lg == lang and g == gender]
        other = [n for n, (lg, g) in voices.items() if lg == lang and g != gender]
        return (mine or other or [None])[0]                                   # (a voice of the other sex beats none)

    def render(self, text: str, voice: str, sr: int) -> np.ndarray:
        fd, out = tempfile.mkstemp(suffix=".wav")                               # (a NamedTemporaryFile cannot be opened by PowerShell while this holds it)
        os.close(fd)
        try:
            r = self._run(_SAPI_SAY, env={**os.environ, "ASTRA_SAPI_VOICE": voice, "ASTRA_SAPI_OUT": out, "ASTRA_SAPI_TEXT": text}, timeout=60.0)
            if r.returncode != 0:
                raise RuntimeError(f"SAPI failed: {r.stderr.decode(errors='replace')[:160]}")
            x, rate = sf.read(out, dtype="float32")
        finally:
            try:
                os.unlink(out)
            except OSError:
                pass
        x = x if x.ndim == 1 else x[:, 0]
        return resample(x, rate, sr) if rate != sr else x


class SystemVoices:
    """The operating system's own voices (macOS `say`, Windows SAPI) for the languages Pocket TTS lacks, and while a language's model is
    still being downloaded. Other systems have none: a language Pocket does not speak then goes to the English model, or is reported
    unmakeable when its script is not Latin."""

    def __init__(self, platform: str | None = None) -> None:
        platform = platform or sys.platform
        self._impl = _MacVoices() if platform == "darwin" else _WindowsVoices() if platform == "win32" else None

    def warm(self) -> None:
        """List the voices in the background (Windows: a PowerShell, a second or more) so that the first line is not the one that waits."""
        if isinstance(self._impl, _WindowsVoices):
            threading.Thread(target=self._impl.catalogue, name="sapi-voices", daemon=True).start()

    def installed(self) -> set[str]:
        return self._impl.installed() if self._impl else set()

    def pick(self, lang: str, gender: str = "f") -> str | None:
        return self._impl.pick(lang, gender) if self._impl else None

    def render(self, text: str, voice: str, sr: int) -> np.ndarray:
        if self._impl is None:
            raise RuntimeError("this system has no voices of its own for the mind to use")
        return self._impl.render(text, voice, sr)


def _hf_hub_dir() -> Path:
    """Where Hugging Face keeps downloaded models on this machine (its own precedence: HF_HUB_CACHE, HF_HOME, XDG_CACHE_HOME)."""
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(var):
            return Path(os.environ[var])
    home = os.environ.get("HF_HOME") or str(Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "huggingface")
    return Path(home) / "hub"


def _cache_has_pocket_tts() -> bool:
    return (_hf_hub_dir() / "models--kyutai--pocket-tts").exists()


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
        self.system = SystemVoices()
        self.system.warm()
        self._cached: set[str] = set()                                       # languages whose model was found in the local cache

    # ------------------------------------------------------------------------------------------ facts
    def supported(self, lang: str) -> bool:
        """Pocket TTS speaks it."""
        return lang in MODEL_FOR_LANG

    def can_speak(self, lang: str) -> bool:
        """Some voice speaks it: Pocket TTS, or (macOS) one of the system's."""
        return self.available(lang) or lang in MODEL_FOR_LANG or self.system.pick(lang) is not None

    def loaded(self, lang: str) -> bool:
        return MODEL_FOR_LANG.get(lang, "english") in self._models

    def available(self, lang: str) -> bool:
        """Pocket TTS can speak it now: its model is in memory or in the local cache. A language it supports whose model is still to
        be downloaded (a first start; the download runs in the background) is not: a line would wait minutes for it, so a system
        voice speaks meanwhile (a line said in a plainer voice beats a line never said)."""
        if lang not in MODEL_FOR_LANG:
            return False
        if self.loaded(lang) or lang in self._cached:
            return True
        if any(_hf_hub_dir().glob(f"models--kyutai--pocket-tts/snapshots/*/languages/{MODEL_FOR_LANG[lang]}/model.safetensors")):
            self._cached.add(lang)
            return True
        return False

    @staticmethod
    def _read_gains(path: Path) -> dict[str, dict[str, float]]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
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
                _USER_GAINS.write_text(json.dumps(self._user, indent=1, sort_keys=True), encoding="utf-8")
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
        """Generator of processed float32 chunks for one line of Pocket TTS: pauses shortened, sped up, gained, limited."""
        with self._lock:
            model = self._model(lang)
            state = self._voice(lang, voice)

            cap = int(self.sample_rate * (len(text) / MIN_CPS + 2.5))         # no line runs longer than the slowest speech could

            def chunks():
                n = 0
                for chunk in model.generate_audio_stream(state, text, stop=stop):
                    a = chunk.detach().cpu().numpy().astype(np.float32).reshape(-1)
                    n += len(a)
                    yield a
                    if n > cap:
                        log.warning("TTS: %d s of audio for %d characters: stopped (the model did not find the end)", n // self.sample_rate, len(text))
                        stop.set()
                        return

            yield from self._master(chunks(), self.sample_rate, speed, gain_db, limit, stop, stream)

    def _run_system(self, text: str, voice: str, speed: float, stop: threading.Event, stream: SpeechStream | None):
        """The same for one of macOS's voices: made whole, its loudness measured, then mastered like the others."""
        x = self.system.render(text, voice, self.sample_rate)
        gain_db = float(np.clip(self.target_lufs - integrated_lufs(x, self.sample_rate), -15.0, 15.0))
        block = int(self.sample_rate * 0.08)
        yield from self._master((x[i:i + block] for i in range(0, len(x), block)), self.sample_rate, speed, gain_db, True, stop, stream)

    def _master(self, source, sr: int, speed: float, gain_db: float, limit: bool, stop: threading.Event, stream: SpeechStream | None):
        """Pauses shortened, sped up, gained, limited: what any voice goes through on its way out."""
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

        for a in source:
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
        thread; `stop()` on the result ends it at once. A language Pocket TTS does not speak, or whose model is not on the machine
        yet, goes to a system voice when there is one (macOS); else a language it does not speak goes to the English model, and one
        it speaks waits for its model (downloaded on first use)."""
        system_voice = None
        if not self.available(lang):
            system_voice = self.system.pick(lang, GENDER.get(voice, "f"))
            if system_voice is None and not self.supported(lang):
                lang = "en"
                letters = [c for c in text if c.isalpha()]
                if letters and sum(1 for c in letters if ord(c) > 0x24F) / len(letters) > 0.3:
                    # no voice for this script here: the English model would grind on the characters for many seconds and
                    # produce noise: the line is reported unmakeable instead (the floor drops it, and says so)
                    st = SpeechStream(self.sample_rate)
                    st.error = RuntimeError(f"no voice for this language ({text[:20]!r}...) on this machine")
                    st.done = True
                    st.q.put_nowait(None)
                    log.error("%s", st.error)
                    return st
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
                if system_voice is not None:
                    source = self._run_system(text, system_voice, sp, st.stop_event, st)
                else:
                    source = self._run(speakable(text, lang), voice, lang, sp, self.profile(lang, voice).gain_db, True, st.stop_event, st)
                first = True
                for a in source:
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
        out = list(self._run(speakable(text, lang), voice, lang, sp, g, limit, threading.Event(), None))
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


def cache_status() -> dict[str, tuple[bool, int]]:
    """For every language: (its model is in the Hugging Face cache, how many of the 27 catalogue voices are)."""
    home = _hf_hub_dir()
    out: dict[str, tuple[bool, int]] = {}
    for lang, name in MODEL_FOR_LANG.items():
        has_model = any(home.glob(f"models--kyutai--pocket-tts/snapshots/*/languages/{name}/model.safetensors"))
        voices = len({p.name for p in home.glob(f"models--kyutai--pocket-tts-without-voice-cloning/snapshots/*/languages/{name}/embeddings/*.safetensors")})
        out[lang] = (has_model, voices)
    return out


def fetch_models(langs: list[str], voices: list[str] | None = None) -> None:
    """Download (or find in the cache) the model of each language and the voices of the catalogue (or `voices`): about 440 MB a language, plus a
    few hundred kilobytes per voice."""
    eng = TTSEngine(max_resident=1)
    for lang in langs:
        for v in (voices or VOICES):
            eng._voice(lang, v)
        eng._models.clear()
        eng._voices.clear()


def main() -> None:
    """python -m astra_mind.tts [--fetch it,en,...] [--voices alba,...]: what is cached, and download the rest (about 440 MB a
    language, plus a few hundred kilobytes per voice)."""
    import argparse
    ap = argparse.ArgumentParser(prog="python -m astra_mind.tts")
    ap.add_argument("--fetch", nargs="?", const=",".join(MODEL_FOR_LANG), help="languages to download (default: all seven)")
    ap.add_argument("--voices", default="", help="voices to prepare (default: all of the catalogue)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.fetch:
        fetch_models(args.fetch.split(","), args.voices.split(",") if args.voices else None)
    for lang, (m, n) in cache_status().items():
        print(f"{lang}: model {'cached' if m else 'MISSING'}, {n}/27 voices")


if __name__ == "__main__":
    main()
