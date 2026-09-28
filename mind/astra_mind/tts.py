"""Local text-to-speech with Pocket TTS (Kyutai, CPU). One model per language, loaded on first use and kept;
voice states cached per (language, voice). Generation runs in a worker thread and streams PCM16 chunks."""
from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from typing import AsyncIterator

import numpy as np

log = logging.getLogger("astra.tts")

MODEL_FOR_LANG = {"it": "italian", "en": "english", "es": "spanish", "fr": "french", "de": "german",
                  "pt": "portuguese", "nl": "dutch"}


class TTSEngine:
    def __init__(self) -> None:
        self._models: dict[str, object] = {}
        self._voices: dict[tuple[str, str], object] = {}
        self._lock = threading.Lock()          # one generation at a time: they would only fight for the CPU
        self.sample_rate = 24000

    def supported(self, lang: str) -> bool:
        return lang in MODEL_FOR_LANG

    def _model(self, lang: str):
        name = MODEL_FOR_LANG.get(lang, "english")
        if name not in self._models:
            from pocket_tts import TTSModel
            t0 = time.perf_counter()
            self._models[name] = TTSModel.load_model(language=name)
            self.sample_rate = int(self._models[name].sample_rate)
            log.info("TTS model %s loaded in %.1f s", name, time.perf_counter() - t0)
        return self._models[name]

    def _voice(self, lang: str, voice: str):
        key = (MODEL_FOR_LANG.get(lang, "english"), voice)
        if key not in self._voices:
            t0 = time.perf_counter()
            self._voices[key] = self._model(lang).get_state_for_audio_prompt(voice)
            log.info("TTS voice %s/%s prepared in %.1f s", key[0], voice, time.perf_counter() - t0)
        return self._voices[key]

    def warm(self, lang: str, voices: list[str]) -> None:
        with self._lock:
            for v in voices:
                self._voice(lang, v)

    async def stream(self, text: str, voice: str, lang: str) -> AsyncIterator[bytes]:
        """Yields PCM16 mono chunks at self.sample_rate as soon as they are generated."""
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()

        def work() -> None:
            try:
                with self._lock:
                    model = self._model(lang)
                    state = self._voice(lang, voice)
                    for chunk in model.generate_audio_stream(state, text):
                        a = chunk.detach().cpu().numpy().astype(np.float32).reshape(-1)
                        pcm = (np.clip(a, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
                        loop.call_soon_threadsafe(q.put_nowait, pcm)
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                log.exception("TTS failed")
                loop.call_soon_threadsafe(q.put_nowait, exc)
            finally:
                loop.call_soon_threadsafe(q.put_nowait, None)

        threading.Thread(target=work, name="tts", daemon=True).start()
        while True:
            item = await q.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item
