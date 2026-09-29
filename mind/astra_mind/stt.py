"""Local speech-to-text: WhisperKit (large-v3-turbo on the Neural Engine) behind its local HTTP server.
The server is started on demand and kept alive; requests carry a glossary prompt so the game's proper nouns survive."""
from __future__ import annotations

import asyncio
import io
import logging
import shutil
import subprocess
import time
import wave
from pathlib import Path

import httpx

from .env import HOME

log = logging.getLogger("astra.stt")

MODEL_DIR = HOME / "voice" / "models" / "models" / "argmaxinc" / "whisperkit-coreml" / "openai_whisper-large-v3-v20240930_turbo"
PORT = 50060
GLOSSARY = ("ASN Aquila, Kharon Mandate, Janus Gate, Keeper Station, New Ravenna, Port Aurelius, Aurelia, Tiberius, "
            "Ceres Belt, Vulcan, Teal Veil, Serra, Ferri, Voss, Tanaka, Martin, Nair, Mensah, Price, Kovac, Okonkwo, "
            "Lindqvist, Reyes, Varek Solm, railgun, VLS, point defense, EMCON, Falcon, Hammer, Wasp, Alpha, Bravo.")


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class WhisperKit:
    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self.url = f"http://127.0.0.1:{PORT}/v1/audio/transcriptions"

    async def ready(self) -> bool:
        try:
            r = await self._client.get(f"http://127.0.0.1:{PORT}/", timeout=1.0)
            return r.status_code < 500
        except httpx.HTTPError:
            return False

    async def start(self) -> None:
        if await self.ready():
            return
        exe = shutil.which("whisperkit-cli")
        if not exe or not MODEL_DIR.exists():
            log.warning("WhisperKit unavailable (cli: %s, model: %s)", exe, MODEL_DIR.exists())
            return
        log.info("starting WhisperKit server")
        self._proc = subprocess.Popen([exe, "serve", "--model-path", str(MODEL_DIR), "--port", str(PORT),
                                       "--host", "127.0.0.1", "--without-timestamps"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 90:
            if await self.ready():
                log.info("WhisperKit ready in %.1f s", time.perf_counter() - t0)
                return
            await asyncio.sleep(0.5)
        log.error("WhisperKit did not start")

    async def transcribe(self, pcm16: bytes, rate: int = 16000, language: str | None = None,
                         glossary: bool = True) -> tuple[str, str]:
        """Returns (text, language code)."""
        data = {"model": "large-v3-turbo", "response_format": "verbose_json"}
        if glossary:
            data["prompt"] = GLOSSARY
        if language:
            data["language"] = language
        files = {"file": ("speech.wav", pcm16_to_wav(pcm16, rate), "audio/wav")}
        r = await self._client.post(self.url, data=data, files=files)
        r.raise_for_status()
        j = r.json()
        return (j.get("text") or "").strip(), (j.get("language") or language or "en")

    def stop_server(self) -> None:
        """The server this mind started goes with it: a mind that stops must not leave the model loaded behind it (a
        server found already running, started by someone else, is left alone)."""
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    async def close(self) -> None:
        await self._client.aclose()
        self.stop_server()
