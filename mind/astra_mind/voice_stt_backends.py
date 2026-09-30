"""Speech-recognition backends behind one interface. Each takes 16 kHz mono PCM16 and returns text (and the language and a
confidence when the engine reports them):

- ParakeetBackend: NVIDIA Parakeet TDT 0.6B v3 / Ultra (25 European languages) on the Apple Neural Engine, through the
  `astra-stt` Swift helper (mind/stt_server, FluidAudio). About 40x faster than the audio, no GPU: the game keeps it.
- WhisperKitBackend: Whisper large-v3-turbo on the Neural Engine behind `whisperkit-cli serve` (99 languages, reports the
  language, takes a prompt with the game's names). The fallback for everything Parakeet does not speak.
- FasterWhisperBackend: faster-whisper (CTranslate2) on the CPU: portable to Windows and Linux, the fallback of last resort.

A backend that cannot start says so from `start()` and is skipped."""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .env import CACHE, HOME

log = logging.getLogger("astra.stt")

MIND_DIR = Path(__file__).resolve().parents[1]                     # .../mind
PARAKEET_LANGS = frozenset("en es fr de it pt ro nl da sv fi hu et lv lt mt pl cs sk sl hr bg el ru uk".split())
VOICE_MODELS = Path(os.environ["ASTRA_VOICE_MODELS"]) if os.environ.get("ASTRA_VOICE_MODELS") else HOME / "voice" / "models"


@dataclass
class BackendResult:
    text: str
    lang: str | None = None                # the language the engine says it heard (None: it does not say)
    conf: float | None = None              # 0..1 when the engine reports one
    seconds: float = 0.0                   # processing time inside the engine
    words: list[tuple[str, float, float]] = field(default_factory=list)    # (word, start s, end s) when known
    backend: str = ""


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class SttBackend:
    name = "backend"
    languages: frozenset[str] | None = None        # None: any
    takes_prompt = False
    reports_language = False

    async def start(self) -> bool:                 # noqa: D102
        return False

    async def transcribe(self, pcm16: bytes, *, lang: str | None = None, prompt: str | None = None) -> BackendResult:
        raise NotImplementedError

    def stop(self) -> None:
        return None

    async def close(self) -> None:
        self.stop()

    def speaks(self, lang: str) -> bool:
        return self.languages is None or lang in self.languages


# ================================================================================================ Parakeet (ANE)
def find_parakeet_binary() -> Path | None:
    """The astra-stt helper: ASTRA_STT_BIN, the app's bin folder, or the SwiftPM build next to the sources."""
    for c in (os.environ.get("ASTRA_STT_BIN"), HOME / "bin" / "astra-stt", MIND_DIR / "bin" / "astra-stt",
              MIND_DIR / "stt_server" / ".build" / "release" / "astra-stt",
              Path(__file__).resolve().parents[2] / "mind" / "stt_server" / ".build" / "release" / "astra-stt"):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return Path(c)
    return None


class ParakeetBackend(SttBackend):
    name = "parakeet"
    languages = PARAKEET_LANGS
    takes_prompt = False
    reports_language = False

    def __init__(self, model: str | None = None, binary: Path | None = None, compute: str = "ane") -> None:
        self.model = model or os.environ.get("ASTRA_STT_MODEL", "ultra")
        self.binary = binary or find_parakeet_binary()
        self.compute = compute
        self._proc: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._failed = False
        self._pending: dict[int, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._n = 0
        self._last_start = 0.0
        self._starting: asyncio.Lock = asyncio.Lock()
        self.load_s = 0.0

    @staticmethod
    def available() -> bool:
        return platform.system() == "Darwin" and platform.machine() == "arm64" and find_parakeet_binary() is not None

    async def start(self) -> bool:
        async with self._starting:
            if self._proc and self._proc.returncode is None and self._ready.is_set():
                return True
            if self.binary is None or not self.binary.exists():
                log.warning("Parakeet unavailable: no astra-stt binary (build it: cd mind/stt_server && swift build -c release)")
                return False
            if time.monotonic() - self._last_start < 5.0 and self._failed:
                return False                                        # do not spin restarting a helper that dies at once
            self._last_start = time.monotonic()
            self._failed = False
            self._ready.clear()
            args = [str(self.binary), "--model", self.model, "--compute", self.compute]
            root = VOICE_MODELS
            folder = {"ultra": "parakeet-ultra-coreml", "redux": "parakeet-redux-coreml", "v2": "parakeet-tdt-0.6b-v2-coreml"}.get(
                self.model, "parakeet-tdt-0.6b-v3-coreml")
            if (root / folder).exists():
                args += ["--models-dir", str(root)]
            CACHE.mkdir(parents=True, exist_ok=True)
            errlog = open(CACHE / "astra-stt.log", "ab")
            log.info("starting Parakeet (%s) on the Neural Engine", self.model)
            t0 = time.perf_counter()
            self._proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                              stderr=errlog)
            self._reader = asyncio.create_task(self._read_loop(self._proc))
            try:
                # the first ever start downloads ~600 MB and compiles for the Neural Engine: minutes; later starts take a second
                await asyncio.wait_for(self._ready.wait(), timeout=600)
            except asyncio.TimeoutError:
                log.error("Parakeet did not start in time")
                self.stop()
                return False
            if self._failed:
                return False
            self.load_s = time.perf_counter() - t0
            log.info("Parakeet ready in %.1f s", self.load_s)
            return True

    async def _read_loop(self, proc: asyncio.subprocess.Process) -> None:
        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "ready" in msg:
                    if msg.get("ready"):
                        self._ready.set()
                    else:
                        log.error("Parakeet failed to load: %s", msg.get("error"))
                        self._failed = True
                        self._ready.set()
                    continue
                fut = self._pending.pop(msg.get("id", -1), None)
                if fut and not fut.done():
                    fut.set_result(msg)
        finally:
            self._failed = self._failed or not self._ready.is_set()
            self._ready.set()
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("the Parakeet helper stopped"))
            self._pending.clear()

    async def transcribe(self, pcm16: bytes, *, lang: str | None = None, prompt: str | None = None) -> BackendResult:
        if not (self._proc and self._proc.returncode is None and self._ready.is_set() and not self._failed):
            if not await self.start():
                raise RuntimeError("Parakeet is not available")
        assert self._proc and self._proc.stdin
        async with self._lock:
            self._n += 1
            rid = self._n
            fut = asyncio.get_running_loop().create_future()
            self._pending[rid] = fut
            header = {"op": "transcribe", "id": rid, "n": len(pcm16) // 2}
            if lang and lang in PARAKEET_LANGS:
                header["lang"] = lang
            self._proc.stdin.write((json.dumps(header) + "\n").encode() + pcm16)
            await self._proc.stdin.drain()
            msg = await asyncio.wait_for(fut, timeout=30)
        if not msg.get("ok"):
            raise RuntimeError(f"Parakeet: {msg.get('error')}")
        words = [(w["w"], float(w["s"]), float(w["e"])) for w in msg.get("words", [])]
        return BackendResult(text=(msg.get("text") or "").strip(), lang=None, conf=float(msg.get("conf", 0.0)),
                             seconds=float(msg.get("ms", 0)) / 1000.0, words=words, backend=self.name)

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc and proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
        if self._reader:
            self._reader.cancel()
            self._reader = None
        self._ready.clear()


# ================================================================================================ WhisperKit (ANE)
class WhisperKitBackend(SttBackend):
    """Whisper large-v3-turbo (CoreML, Neural Engine) behind `whisperkit-cli serve`; a server already running on the
    port (someone else's) is used and left alone."""
    name = "whisperkit"
    languages = None
    takes_prompt = True
    reports_language = True

    def __init__(self, port: int = 50060, model_dir: Path | None = None, extra_args: list[str] | None = None) -> None:
        import httpx
        self.port = port
        self.model_dir = model_dir or (VOICE_MODELS / "models" / "argmaxinc" / "whisperkit-coreml" / "openai_whisper-large-v3-v20240930_turbo")
        self.extra_args = extra_args if extra_args is not None else [
            "--without-timestamps", "--chunking-strategy", "none", "--temperature-fallback-count", "0",
            "--concurrent-worker-count", "1"]
        self._proc: subprocess.Popen | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self.url = f"http://127.0.0.1:{port}/v1/audio/transcriptions"
        self._start_lock = asyncio.Lock()
        self.last_used = time.monotonic()

    @staticmethod
    def available() -> bool:
        return shutil.which("whisperkit-cli") is not None

    async def ready(self) -> bool:
        import httpx
        try:
            r = await self._client.get(f"http://127.0.0.1:{self.port}/", timeout=1.0)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    async def start(self) -> bool:
        async with self._start_lock:
            if await self.ready():
                return True
            exe = shutil.which("whisperkit-cli")
            if not exe or not self.model_dir.exists():
                log.warning("WhisperKit unavailable (cli: %s, model: %s)", bool(exe), self.model_dir.exists())
                return False
            log.info("starting WhisperKit server (port %d)", self.port)
            self._proc = subprocess.Popen([exe, "serve", "--model-path", str(self.model_dir), "--port", str(self.port), "--host", "127.0.0.1",
                                           *self.extra_args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            t0 = time.perf_counter()
            while time.perf_counter() - t0 < 300:
                if await self.ready():
                    log.info("WhisperKit ready in %.1f s", time.perf_counter() - t0)
                    return True
                if self._proc.poll() is not None:
                    log.error("WhisperKit server exited (code %s)", self._proc.returncode)
                    return False
                await asyncio.sleep(0.4)
            log.error("WhisperKit did not start")
            return False

    async def transcribe(self, pcm16: bytes, *, lang: str | None = None, prompt: str | None = None) -> BackendResult:
        if not await self.ready() and not await self.start():
            raise RuntimeError("WhisperKit is not available")
        data = {"model": "large-v3-turbo", "response_format": "verbose_json", "temperature": "0"}
        if prompt:
            data["prompt"] = prompt
        if lang:
            data["language"] = lang
        files = {"file": ("speech.wav", pcm16_to_wav(pcm16), "audio/wav")}
        t0 = time.perf_counter()
        r = await self._client.post(self.url, data=data, files=files)
        r.raise_for_status()
        j = r.json()
        self.last_used = time.monotonic()
        return BackendResult(text=(j.get("text") or "").strip(), lang=(j.get("language") or lang), conf=None,
                             seconds=time.perf_counter() - t0, backend=self.name)

    def stop(self) -> None:
        """The server this mind started goes with it: a mind that stops must not leave the model loaded behind it (a
        server found already running, started by someone else, is left alone)."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    async def close(self) -> None:
        await self._client.aclose()
        self.stop()


# ================================================================================================ faster-whisper (CPU, portable)
class FasterWhisperBackend(SttBackend):
    """faster-whisper (CTranslate2, int8 on the CPU): runs on Windows, Linux and macOS without a Neural Engine. Install with
    `uv sync --extra portable`. Whisper's language identification and initial prompt work as in WhisperKit."""
    name = "faster-whisper"
    languages = None
    takes_prompt = True
    reports_language = True

    def __init__(self, model: str | None = None, threads: int = 4, compute_type: str = "int8") -> None:
        self.model_name = model or os.environ.get("ASTRA_FW_MODEL", "small")
        self.threads = threads
        self.compute_type = compute_type
        self._model = None
        self._lock = asyncio.Lock()

    @staticmethod
    def available() -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:  # noqa: BLE001
            return False

    async def start(self) -> bool:
        if self._model is not None:
            return True
        try:
            from faster_whisper import WhisperModel
        except Exception:  # noqa: BLE001
            log.warning("faster-whisper is not installed (uv sync --extra portable)")
            return False
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        self._model = await loop.run_in_executor(None, lambda: WhisperModel(self.model_name, device="cpu", compute_type=self.compute_type,
                                                                            cpu_threads=self.threads))
        log.info("faster-whisper %s loaded in %.1f s", self.model_name, time.perf_counter() - t0)
        return True

    async def transcribe(self, pcm16: bytes, *, lang: str | None = None, prompt: str | None = None) -> BackendResult:
        if self._model is None and not await self.start():
            raise RuntimeError("faster-whisper is not available")
        audio = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
        model = self._model

        def run() -> BackendResult:
            t0 = time.perf_counter()
            segs, info = model.transcribe(audio, language=lang, initial_prompt=prompt, beam_size=1, best_of=1, temperature=0.0,
                                          without_timestamps=True, condition_on_previous_text=False, vad_filter=False)
            text = " ".join(s.text.strip() for s in segs).strip()
            return BackendResult(text=text, lang=info.language, conf=float(info.language_probability), seconds=time.perf_counter() - t0,
                                 backend="faster-whisper")

        async with self._lock:
            return await asyncio.get_running_loop().run_in_executor(None, run)

    def stop(self) -> None:
        self._model = None
