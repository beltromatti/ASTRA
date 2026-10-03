"""Fast checks of the voice pieces that need no model and no microphone (seconds to run):

    uv run python -m bench.voice_units

The audio processors (loudness meter, limiter, time stretcher, pause compressor, speech trimming), the game's names and the
language decision, and the recogniser's decisions (which engine answers, hallucinations, partial decodes) with stand-in
engines. Each check prints ok or FAIL; the exit code is the number of failures."""
from __future__ import annotations

import asyncio
import sys
import time
import traceback

import numpy as np

from astra_mind.stt import Recognizer
from astra_mind.voice_audio import (Limiter, PauseCompressor, TimeStretcher, f32_to_pcm16, integrated_lufs, k_weight, peak_db, speech_frames, trim_speech)
from astra_mind.voice_glossary import GLOSSARY, phon
from astra_mind.voice_lang import resolve_language
from astra_mind.voice_stt_backends import BackendResult, SttBackend

SR = 24000
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def feed(proc, x: np.ndarray, sizes: list[int]) -> np.ndarray:  # noqa: ANN001
    out, i, k = [], 0, 0
    while i < len(x):
        n = sizes[k % len(sizes)]
        out.append(proc.process(x[i:i + n]))
        i += n
        k += 1
    out.append(proc.flush())
    return np.concatenate(out)


def speechlike(seconds: float = 6.0, sr: int = SR, seed: int = 0) -> np.ndarray:
    """Voiced bursts (harmonics of a moving 110-160 Hz pitch, syllable-rate envelope) with pauses, and a few plosive spikes."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    f0 = 110 + 40 * np.sin(2 * np.pi * 0.7 * t)
    ph = 2 * np.pi * np.cumsum(f0) / sr
    v = sum(np.sin(h * ph) / h for h in range(1, 14))
    env = np.clip(np.sin(2 * np.pi * 3.2 * t) * 1.6, 0, 1) * (np.sin(2 * np.pi * 0.35 * t) > -0.55)
    x = 0.2 * v * env / np.abs(v).max()
    for c in rng.integers(0, len(x) - 200, 12):
        x[c:c + 40] += rng.uniform(0.3, 0.6) * rng.standard_normal(40)
    return x.astype(np.float32)


def units() -> None:
    t = np.arange(SR * 5) / SR
    sine = (10 ** (-20 / 20) * np.sin(2 * np.pi * 997 * t)).astype(np.float32)
    check("loudness: a -20 dBFS 997 Hz sine is -23.0 LUFS", abs(integrated_lufs(sine, SR) - (-23.0)) < 0.1, f"{integrated_lufs(sine, SR):.2f}")
    check("loudness: silence is -70", integrated_lufs(np.zeros(SR), SR) == -70.0)
    check("loudness: +6 dB of gain is +6 LU", abs(integrated_lufs(sine * 2, SR) - integrated_lufs(sine, SR) - 6.02) < 0.05)
    check("K-weighting is stable (no NaN)", np.isfinite(k_weight(sine, SR)).all())

    x = speechlike()
    loud = np.clip(x * 10 ** (16 / 20), -6, 6).astype(np.float32)
    ys = {}
    for sizes in ([1920], [777, 1234, 5000, 31], [SR]):
        lim = Limiter(SR, ceiling_db=-1.5)
        ys[tuple(sizes)] = feed(lim, loud, sizes)
    y = ys[(1920,)]
    check("limiter: no sample above the ceiling", float(np.abs(y).max()) <= 10 ** (-1.5 / 20) + 1e-6, f"{peak_db(y):.2f} dB")
    check("limiter: same length in and out", all(len(v) == len(loud) for v in ys.values()))
    check("limiter: chunk size does not change the output", max(float(np.abs(ys[(1920,)] - v).max()) for v in ys.values()) < 1e-6)
    quiet = (x * 0.2).astype(np.float32)
    check("limiter: a signal under the ceiling passes untouched", float(np.abs(feed(Limiter(SR), quiet, [1920]) - quiet).max()) < 1e-6)
    check("limiter: no NaN on silence", np.isfinite(feed(Limiter(SR), np.zeros(5000, np.float32), [1000])).all())

    for speed in (1.12, 1.25, 0.9):
        y1 = feed(TimeStretcher(SR, speed), x, [1920])
        y2 = feed(TimeStretcher(SR, speed), x, [333, 4001, 77])
        check(f"stretch x{speed}: length ratio", abs(len(x) / len(y1) - speed) < 0.02, f"{len(x) / len(y1):.3f}")
        check(f"stretch x{speed}: chunk size does not change the output", len(y1) == len(y2) and float(np.abs(y1 - y2).max()) < 1e-6)
    v = 0.3 * np.sin(2 * np.pi * 140 * t)
    ys = feed(TimeStretcher(SR, 1.2), v.astype(np.float32), [1920])
    zc = lambda a: np.sum(np.diff(np.signbit(a[SR // 2: -SR // 2])) != 0) / (len(a[SR // 2: -SR // 2]) / SR) / 2  # noqa: E731
    check("stretch keeps the pitch", abs(zc(ys) - 140) < 3, f"{zc(ys):.1f} Hz")
    check("stretch x1.0 is a pass-through", np.array_equal(feed(TimeStretcher(SR, 1.0), x, [1920]), x))

    sp = np.concatenate([np.zeros(int(0.9 * SR)), x[: 2 * SR], np.zeros(int(1.4 * SR)), x[2 * SR: 3 * SR], np.zeros(int(0.8 * SR))]).astype(np.float32)
    pc = PauseCompressor(SR)
    y = feed(pc, sp, [1920])
    dur = len(y) / SR
    check("pauses: leading, inner and trailing silences are shortened", dur < len(sp) / SR - 1.5, f"{len(sp) / SR:.2f} -> {dur:.2f} s")
    on_in = float(np.sum(np.abs(sp) > 0.01))
    on_out = float(np.sum(np.abs(y) > 0.01))
    check("pauses: no speech sample is lost", on_out == on_in, f"{on_in:.0f} vs {on_out:.0f}")

    noisy = np.concatenate([np.random.default_rng(3).standard_normal(SR) * 0.002, x[: 2 * SR], np.random.default_rng(4).standard_normal(SR) * 0.002]).astype(np.float32)
    tr, frac, sp_s = trim_speech(noisy, SR)
    check("trim: the silence around speech goes, the speech stays", 2.0 <= len(tr) / SR <= 2.9 and sp_s > 1.0, f"{len(tr) / SR:.2f} s")
    check("trim: noise alone is not speech", len(trim_speech(np.random.default_rng(5).standard_normal(SR * 2).astype(np.float32) * 0.003, SR)[0]) == 0)
    check("vad: an empty buffer has no speech frames", not speech_frames(np.zeros(0, np.float32), SR).any())


def glossary_and_language() -> None:
    fix = lambda s: GLOSSARY.correct(s)[0]  # noqa: E731
    check("glossary: Pretoriano -> Praetorian", fix("Apri un canale con la Pretoriano.") == "Apri un canale con la Praetorian.")
    check("glossary: Flegetonte -> Phlegethon", fix("Fuoco sul Flegetonte") == "Fuoco sul Phlegethon")
    check("glossary: two words become one name", fix("portaci attraverso il Janus gate verso Cassia") == "portaci attraverso il Janus Gate verso Cassia")
    check("glossary: the word after a name is not swallowed", fix("take us through the Janus gate to Cassia") == "take us through the Janus Gate to Cassia")
    check("glossary: Styx from 'sticks'", fix("keep the railguns on the sticks") == "keep the railguns on the Styx")
    check("glossary: ordinary words are left alone", fix("la serra è vicina alla terra, il price è alto, la mensa chiude") == "la serra è vicina alla terra, il price è alto, la mensa chiude")
    check("glossary: nothing to fix, nothing changed", GLOSSARY.correct("Avanti tutta.")[1] == [])
    check("glossary: an officer called out first is read as the name (Mensa -> Mensah)", fix("Mensa, qual è la temperatura del reattore?") == "Mensah, qual è la temperatura del reattore?")
    check("glossary: ... even split in two", fix("Men sa, wie hoch ist die Temperatur?") == "Mensah, wie hoch ist die Temperatur?")
    check("glossary: Boss and Foss are Voss at the start of an order", fix("Boss, fire the missiles.") == "Voss, fire the missiles." and fix("Foss, starten Sie Raketen.") == "Voss, starten Sie Raketen.")
    check("glossary: a name cut short after a title", fix("Doutora Lind, como estão os feridos?") == "Doutora Lindqvist, como estão os feridos?")
    check("glossary: the name at the end of an order", fix("How is the reactor, Mansa?") == "How is the reactor, Mensah?")
    check("glossary: ordinary first and last words are not names",
          all(fix(s) == s for s in ("Bene, avanti tutta.", "Fuoco, subito!", "Yes, sir.", "Perfetto, grazie.", "Focus fire on the target.", "Fire, now.",
                                    "Tattico, fuoco a volontà.", "Sensori, rapporto.", "Timoniere, indietro adagio.", "Avanti tutta, grazie.", "Copy that, sir.",
                                    "Rapporto danni, subito.", "Tank the damage, ops.")))
    check("glossary: a lost first vowel (Queron, Cheron -> Acheron)", fix("Tattico, fuoco sulla Queron.") == "Tattico, fuoco sulla Acheron."
          and fix("fire on the Cheron") == "fire on the Acheron")
    check("glossary: a two-word name run together (Janusgate)", fix("portaci attraverso il Janusgate verso Cassia") == "portaci attraverso il Janus Gate verso Cassia")
    check("glossary: the plural of railgun stays plural", fix("mantieni i raiguns sulla Styx") == "mantieni i railguns sulla Styx")
    check("glossary: a five-letter slip (Akron -> Acheron), a spelling of Cassia", fix("fire on the Akron") == "fire on the Acheron" and fix("rotta per Casia") == "rotta per Cassia")
    check("glossary: LET in capitals is Lethe, 'let' is a word", fix("lancez les missiles sur le LET") == "lancez les missiles sur le Lethe" and fix("Let me know when ready.") == "Let me know when ready.")
    check("glossary: the prompt lists names and stays short", "Praetorian" in GLOSSARY.prompt() and len(GLOSSARY.prompt()) < 500)
    check("phonetic key ignores accents and doubled letters", phon("Praetórian") == phon("Pretorian"))

    check("language: a two-word Italian phrase stays Italian", resolve_language("Mi sentite?", "it")[0] == "it")
    check("language: 'Mi sentite?' is Italian even after English", resolve_language("Mi sentite?", "en")[0] == "it")
    check("language: 'Scudi a prua' is Italian (crew vocabulary)", resolve_language("Scudi a prua", "en")[0] == "it")
    check("language: a full English order after Italian switches", resolve_language("Helm, come to heading two one seven and full ahead", "it")[0] == "en")
    check("language: Spanish is Spanish", resolve_language("Comunicaciones, abra un canal con el Praetorian", "it")[0] == "es")
    check("language: empty text keeps the last language", resolve_language("", "de")[0] == "de")
    check("language: Swedish is Swedish (a language with a system voice, not one of the seven)", resolve_language("Kapten, sätt kurs två ett sju, full fart framåt.", "it")[0] == "sv")
    check("language: 'Avante toda' is Spanish for a Captain who speaks Spanish, Portuguese for one who speaks Portuguese",
          resolve_language("Avante toda.", "es")[0] == "es" and resolve_language("Avante toda.", "pt")[0] == "pt")
    check("language: a language the engine reports counts", resolve_language("ok", "en", backend_lang="ja")[0] in ("ja", "en"))


def speech_text() -> None:
    from astra_mind.voice_text import speakable
    check("text: English order with a percent and a bearing", speakable("Set course 217, mark 0, thrust 50%.", "en") == "Set course two one seven, mark zero, thrust fifty percent.")
    check("text: contact id, kilometres, bearing digit by digit (Italian)",
          speakable("Contatto T-21 a 45 km, rilevamento 045.", "it") == "Contatto T ventuno a quarantacinque chilometri, rilevamento zero quattro cinque.")
    check("text: Spanish and French numbers", speakable("Rumbo 217, 50 %", "es") == "Rumbo dos uno siete, cincuenta por ciento"
          and speakable("Cap 217, 45 km", "fr") == "Cap deux un sept, quarante-cinq kilomètres")
    check("text: decimals and thousands (Italian)", speakable("3,5 km/s e 1.200 metri", "it") == "tre virgola cinque chilometri al secondo e milleduecento metri")
    check("text: a decimal written with a dot outside English, a comma thousand in English",
          speakable("Velocità 3.2 km/s a 1.200 m", "it") == "Velocità tre virgola due chilometri al secondo a milleduecento metri"
          and speakable("range 1,200 metres", "en") == "range one thousand two hundred metres")
    check("text: em dashes, brackets and ellipses become pauses", speakable("Quota (12 km) — sotto…", "it") == "Quota, dodici chilometri, sotto.")
    check("text: a language without a front end is left alone", speakable("今日は217です", "ja") == "今日は217です")
    check("text: words are untouched", speakable("Agli ordini, Capitano.", "it") == "Agli ordini, Capitano.")

    import os
    import tempfile
    from astra_mind.tts import TTSEngine
    with tempfile.TemporaryDirectory() as td:
        was = os.environ.get("HF_HOME")
        os.environ["HF_HOME"] = td                                   # a machine with nothing downloaded yet
        try:
            eng = TTSEngine()
            check("tts: a language whose model is not on the machine is not available (a system voice speaks meanwhile, the model is fetched)",
                  not eng.available("it") and eng.can_speak("it") and eng.supported("it"))
            check("tts: a language Pocket does not speak is not available either", not eng.available("ja") and not eng.available("xx"))
        finally:
            if was is None:
                os.environ.pop("HF_HOME", None)
            else:
                os.environ["HF_HOME"] = was


class Fake(SttBackend):
    """A stand-in engine: says what it is told, takes a given time."""

    def __init__(self, name: str, langs: frozenset[str] | None, text: str = "", conf: float | None = 0.95, lang: str | None = None, delay: float = 0.0,
                 prompt: bool = False, fast: bool = False) -> None:
        self.name, self.languages, self.text, self.conf, self.lang, self.delay = name, langs, text, conf, lang, delay
        self.takes_prompt = prompt
        self.fast = fast
        self.calls = 0

    async def start(self) -> bool:
        return True

    async def transcribe(self, pcm16: bytes, *, lang: str | None = None, prompt: str | None = None) -> BackendResult:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return BackendResult(text=self.text, lang=self.lang, conf=self.conf, seconds=self.delay, backend=self.name)


def speech_pcm(seconds: float = 2.0, tail: float = 0.0) -> bytes:
    x = speechlike(seconds + tail, sr=16000)
    if tail:
        x[int(seconds * 16000):] = 0
    return f32_to_pcm16(x)


async def recogniser() -> None:
    fast = Fake("parakeet", frozenset({"it", "en", "es"}), "Timoniere, rotta due uno sette.", 0.97)
    slow = Fake("whisperkit", None, "肝腸、張り道217", None, lang="ja")
    r = Recognizer(backends=[fast, slow], prior="it")
    await r.start()
    tr = await r.recognise(speech_pcm())
    check("recogniser: a sure fast engine answers alone", tr.text.startswith("Timoniere") and slow.calls == 0 and not tr.escalated)
    check("recogniser: language comes with the text", tr.lang == "it")

    fast.conf = 0.62
    fast.text = "Kancho, Harimichinihakujna na Zensoku"
    tr = await r.recognise(speech_pcm())
    check("recogniser: the first unsure phrase does not wait for the second engine to start (it goes with the first's words)",
          not tr.escalated and slow.calls == 0, f"escalated={tr.escalated} calls={slow.calls}")
    await asyncio.sleep(0.05)                                      # (the second engine comes up in the background)
    tr = await r.recognise(speech_pcm())
    check("recogniser: an unsure fast engine asks the other, whose language is not the fast one's", tr.escalated and tr.backend == "whisperkit" and "217" in tr.text and tr.lang != "")

    r2 = Recognizer(backends=[Fake("parakeet", frozenset({"it", "en"}), "x", 0.9), Fake("whisperkit", None, "Timoniere, rotta due uno sette", None, lang="it")], prior="ja")
    tr = await r2.recognise(speech_pcm())
    check("recogniser: a Captain speaking a language the fast engine lacks goes straight to the other", tr.backend == "whisperkit" and r2.backends[0].calls == 0)

    # a second engine that is still compiling its model: the phrase goes without it, and it is taken up when it is ready
    import astra_mind.stt as stt_module

    class SlowStart(Fake):
        loaded = False                       # (what WhisperKitBackend calls a model that is loaded and has decoded a request)

        async def start(self) -> bool:
            await asyncio.sleep(30.0)
            self.loaded = True
            return True

        async def ready(self) -> bool:
            return True

    slow2 = SlowStart("whisperkit", None, "Kancho, jikai.", None, lang="ja")
    r12 = Recognizer(backends=[Fake("parakeet", frozenset({"it"}), "Kancho, Harimichinihakujna na Zensoku", 0.7, fast=True), slow2], prior="it")
    await r12.ready()
    was = stt_module.SECOND_WAIT_S
    stt_module.SECOND_WAIT_S = 0.2
    try:
        t0 = time.perf_counter()
        tr = await r12.recognise(speech_pcm())
        check("recogniser: a second engine still compiling does not hold the phrase (it goes without it)",
              not tr.escalated and tr.text.startswith("Kancho, Harimichinihakujna") and time.perf_counter() - t0 < 1.5, f"{time.perf_counter() - t0:.2f}s escalated={tr.escalated}")
        slow2.loaded = True
        tr = await r12.recognise(speech_pcm())
        check("recogniser: ... and is picked up once its server is ready", tr.escalated and tr.text == "Kancho, jikai.", f"escalated={tr.escalated} {tr.text!r}")
    finally:
        stt_module.SECOND_WAIT_S = was

    r10 = Recognizer(backends=[Fake("parakeet", frozenset({"it"}), "x", 0.9, fast=True), Fake("whisperkit", None, "y", None, lang="ja")], prior="ja")
    await r10.ready()
    check("recogniser: for a Captain whose language the fast engine lacks the second engine is up at boot", r10._up.get("whisperkit") is True)
    r11 = Recognizer(backends=[Fake("parakeet", frozenset({"it"}), "x", 0.9, fast=True), Fake("whisperkit", None, "y", None, lang="ja")], prior="it")
    await r11.ready()
    check("recogniser: ... and stays down for one who speaks the fast engine's", r11._up.get("whisperkit") is None)

    garbage = "Kancho, Harimichinihakujna na Zensoku"
    r2b = Recognizer(backends=[Fake("parakeet", frozenset({"it", "en"}), garbage, 0.7, fast=True),
                               Fake("whisperkit", None, "Thanks for watching!", None, lang="en")], prior="it")
    await r2b._usable(r2b.fallback, True)                         # (the second engine already up)
    tr = await r2b.recognise(speech_pcm())
    check("recogniser: a second opinion that is a subtitle credit is ignored", tr.text == garbage and tr.escalated, f"{tr.text!r}")
    crew_word = Fake("parakeet", frozenset({"it"}), "Avanti tutta?", 0.7, fast=True)
    second_c = Fake("whisperkit", None, "Avanti tutta.", None, lang="it")
    tr = await Recognizer(backends=[crew_word, second_c], prior="it").recognise(speech_pcm())
    check("recogniser: an unsure phrase with a crew word in it stays with the fast engine (Whisper is no better on European speech)",
          not tr.escalated and second_c.calls == 0 and tr.text == "Avanti tutta?", f"escalated={tr.escalated} calls={second_c.calls}")
    sure = Fake("parakeet", frozenset({"it"}), garbage, 0.9, fast=True)
    second_s = Fake("whisperkit", None, "Avanti tutta.", None, lang="it")
    tr = await Recognizer(backends=[sure, second_s], prior="it").recognise(speech_pcm())
    check("recogniser: a phrase the fast engine is sure of never goes to the second", not tr.escalated and second_s.calls == 0)

    r3 = Recognizer(backends=[Fake("whisperkit", None, "Thank you for watching!", None, lang="en")], prior="en")
    tr = await r3.recognise(speech_pcm())
    check("recogniser: a subtitle credit heard by Whisper is dropped", tr.text == "")
    r4 = Recognizer(backends=[Fake("parakeet", None, "Thank you.", 0.99)], prior="en")
    check("recogniser: ... but Parakeet's own 'Thank you.' is kept", (await r4.recognise(speech_pcm())).text == "Thank you.")

    r5 = Recognizer(backends=[Fake("parakeet", None, "hello", 0.99)], prior="en")
    tr = await r5.recognise(f32_to_pcm16(np.random.default_rng(1).standard_normal(16000 * 2).astype(np.float32) * 0.003))
    check("recogniser: noise is never sent to an engine", tr.text == "" and not tr.speech and r5.backends[0].calls == 0)

    r6 = Recognizer(backends=[Fake("parakeet", None, "Avanti tutta.", 0.97, delay=0.05, fast=True)], prior="it")
    await r6.ready()
    pcm = speech_pcm(3.0, tail=0.6)
    sess = r6.session(partial_every_s=0.5)
    for i in range(0, len(pcm), 640):
        sess.feed(pcm[i:i + 640])
        await asyncio.sleep(0.02)
    t0 = time.perf_counter()
    tr = await sess.finish(pcm)
    check("session: when the last decode covers everything said, the result is there at once", tr.partial_hit and time.perf_counter() - t0 < 0.05,
          f"{time.perf_counter() - t0:.3f}s hit={tr.partial_hit}")
    tt = np.arange(int(3.4 * 16000)) / 16000
    vowel = f32_to_pcm16((0.2 * sum(np.sin(2 * np.pi * 130 * h * tt) / h for h in range(1, 10)) / 2.5).astype(np.float32))   # speech to the very end
    r7 = Recognizer(backends=[Fake("parakeet", None, "Avanti tutta.", 0.97, delay=0.3, fast=True)], prior="it")
    await r7.ready()
    s2 = r7.session(partial_every_s=1.0)                          # decodes at 1.0, 2.0 and 3.0 s: 0.4 s of speech come after the last
    for i in range(0, len(vowel), 640):
        s2.feed(vowel[i:i + 640])
        await asyncio.sleep(0.02)
    tr = await s2.finish(vowel)
    check("session: speech after the last partial means a final decode", not tr.partial_hit and tr.text == "Avanti tutta.", f"hit={tr.partial_hit} {tr.text!r}")

    # a slow first engine makes no drafts (it would take longer than the sentence); an unsure draft is not the answer
    slow_first = Fake("whisperkit", None, "Avanti tutta.", None, lang="it", delay=0.05)
    r8 = Recognizer(backends=[slow_first], prior="it")
    await r8.ready()
    s3 = r8.session(partial_every_s=0.5)
    for i in range(0, len(pcm), 640):
        s3.feed(pcm[i:i + 640])
        await asyncio.sleep(0.02)
    check("session: a slow engine decodes nothing while the key is held", slow_first.calls == 0, f"{slow_first.calls} calls")
    fast_unsure = Fake("parakeet", frozenset({"it"}), garbage, 0.7, delay=0.02, fast=True)
    second = Fake("whisperkit", None, "Avanti tutta.", None, lang="it", delay=0.05)
    r9 = Recognizer(backends=[fast_unsure, second], prior="it")
    await r9.ready()
    await r9._usable(second, True)                                # (the second engine already up)
    s4 = r9.session(partial_every_s=0.5)
    for i in range(0, len(pcm), 640):
        s4.feed(pcm[i:i + 640])
        await asyncio.sleep(0.02)
    calls_before = second.calls
    tr = await s4.finish(pcm)
    check("session: an unsure draft is decoded again at release, with the second engine (and drafts never called it)",
          calls_before == 0 and second.calls == 1 and tr.escalated and not tr.partial_hit and tr.text == "Avanti tutta.", f"before={calls_before} calls={second.calls} {tr.text!r}")

    r8 = Recognizer(backends=[Fake("parakeet", None, "Tattico, fuoco sull'Acheronte", 0.97)], prior="it")
    tr = await r8.recognise(speech_pcm())
    check("recogniser: the game's names are corrected in the result", tr.text == "Tattico, fuoco sull'Acheron" and tr.fixes, tr.text)


def speech_rules() -> None:
    """Where a line without a rethink hook (a voice from outside: the missed part is replayed) goes on after a cut (astra_mind/speech.py)."""
    from astra_mind.speech import _tail
    t = "Aquila, this is Archon Solm. You are in our space. Withdraw at once. Stand down within two minutes."
    check("tail: cut in the first sentence starts again from its beginning", _tail(t, 0.05) == t)
    k = t.index("You are")
    check("tail: cut in a later sentence goes on from the start of that sentence", _tail(t, (k + 8) / len(t)) == t[k:], str(_tail(t, (k + 8) / len(t))))
    k2 = t.index("Withdraw")
    check("tail: a sentence that was nearly over is not said again", _tail(t, (k2 - 3) / len(t)) == t[k2:], str(_tail(t, (k2 - 3) / len(t))))
    check("tail: nothing is left when the end of the last sentence was heard", _tail(t, 0.985) is None)
    check("tail: one sentence is said again only if hardly begun", _tail("Contact lost on the long range plot", 0.3) is not None
          and _tail("Contact lost on the long range plot", 0.7) is None)


def main() -> int:
    for fn in (units, glossary_and_language, speech_text, speech_rules):
        try:
            fn()
        except Exception:  # noqa: BLE001
            FAILS.append(fn.__name__)
            print("FAIL", fn.__name__, "crashed:\n" + traceback.format_exc())
    try:
        asyncio.run(recogniser())
    except Exception:  # noqa: BLE001
        FAILS.append("recogniser")
        print("FAIL recogniser crashed:\n" + traceback.format_exc())
    print(f"\n{'all checks pass' if not FAILS else str(len(FAILS)) + ' FAILED: ' + ', '.join(FAILS)}")
    return len(FAILS)


if __name__ == "__main__":
    sys.exit(main())
