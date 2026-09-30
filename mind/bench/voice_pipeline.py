"""Benchmark of the whole voice pipeline, run from mind/:

    uv run python -m bench.voice_pipeline stt   [--langs it,en,...] [--backends parakeet-ultra,...] [--load gpu,cpu:4] [--quick]
    uv run python -m bench.voice_pipeline live  [--backends ...]       recognition as the key is held (real-time feeding)
    uv run python -m bench.voice_pipeline lang                         language decisions over sessions
    uv run python -m bench.voice_pipeline other                        languages the crew is not spoken in (the STT fallback path)
    uv run python -m bench.voice_pipeline tts   [--langs ...]          first sound, real-time factor, loudness, pace, intelligibility
    uv run python -m bench.voice_pipeline mic                          push-to-talk capture against a fake sound device
    uv run python -m bench.voice_pipeline floor                        the speech-floor scenarios (bench/voice_floor.py) + real-voice timings
    uv run python -m bench.voice_pipeline report                       docs/bench/voce_<date>.md from the results gathered so far
    uv run python -m bench.voice_e2e [--lang it|en]                    the whole glue end to end (fake game, fake microphone, fake model); its results
                                                                       join the report
Several sections can follow one another on one line (`stt live tts`); the `stt` flags --per-lang N and --slow-every N shrink the corpus and the sample
the slow engines see.

Results of every section are kept in mind/.cache/voice_bench/results_<section>.json (a section run again replaces its own)."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import statistics
import struct
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import numpy as np

from astra_mind.env import CACHE, REPO_ROOT
from astra_mind.stt import Recognizer
from astra_mind.tts import CALIBRATION, TTSEngine
from astra_mind.voice_audio import f32_to_pcm16, integrated_lufs, peak_db, resample
from astra_mind.voice_casting import wer as wer_fn
from astra_mind.voice_glossary import GLOSSARY
from astra_mind.voice_stt_backends import FasterWhisperBackend, ParakeetBackend, SherpaParakeetBackend, WhisperKitBackend

from . import voice_corpus as vc

OUT = CACHE / "voice_bench"
TODAY = dt.date.today().isoformat()


def save(section: str, data) -> None:  # noqa: ANN001
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"results_{section}.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))


def load(section: str):
    f = OUT / f"results_{section}.json"
    return json.loads(f.read_text()) if f.exists() else None


def load_avg() -> float:
    return os.getloadavg()[0]


def pct(xs: list[float], q: float) -> float:
    return float(np.percentile(xs, q)) if xs else float("nan")


# ------------------------------------------------------------------------------------------------ load generators
class Load:
    """A synthetic game next to the benchmark: GPU busy (a Metal matmul loop) and/or N busy CPU processes."""

    def __init__(self, spec: str) -> None:
        self.procs: list[subprocess.Popen] = []
        for part in [p for p in spec.split(",") if p]:
            if part == "gpu":
                code = ("import torch,time\nd=torch.device('mps')\na=torch.randn(3072,3072,device=d,dtype=torch.float16)\n"
                        "while True:\n    for _ in range(20): b=a@a\n    torch.mps.synchronize()\n")
                self.procs.append(subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            elif part.startswith("cpu"):
                n = int(part.split(":")[1]) if ":" in part else 4
                for _ in range(n):
                    self.procs.append(subprocess.Popen([sys.executable, "-c", "while True: pass"]))
        time.sleep(2.0 if self.procs else 0.0)

    def stop(self) -> None:
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=3)
            except subprocess.TimeoutExpired:
                p.kill()


# ------------------------------------------------------------------------------------------------ backends under test
def make_backend(name: str):
    name = name.split("#")[0]                       # "parakeet-ultra#r3": the same engine under another key (a second run's own copy)
    if name == "parakeet-ultra":
        return ParakeetBackend(model="ultra")
    if name == "parakeet-onnx":                    # the same model on the CPU (sherpa-onnx): the portable path
        return SherpaParakeetBackend(model_dir=Path(os.environ["BENCH_SHERPA"]) if os.environ.get("BENCH_SHERPA") else None)
    if name == "parakeet-v3":
        return ParakeetBackend(model="v3")
    if name == "whisperkit-baseline":            # the server's defaults (temperature fallback and chunking on): what the mind runs
        return WhisperKitBackend(port=50071, extra_args=["--without-timestamps"])
    if name == "whisperkit-tuned":               # the flags tried and dropped: no temperature fallback, no chunking, one worker
        return WhisperKitBackend(port=50072, extra_args=["--without-timestamps", "--chunking-strategy", "none", "--temperature-fallback-count", "0",
                                                         "--concurrent-worker-count", "1"])
    if name in ("whisperkit-turbo632", "whisperkit-small216"):           # quantised variants (downloaded to BENCH_MODELS)
        folder = {"whisperkit-turbo632": "openai_whisper-large-v3-v20240930_turbo_632MB", "whisperkit-small216": "openai_whisper-small_216MB"}[name]
        return WhisperKitBackend(port=50073 if name.endswith("632") else 50074, model_dir=Path(os.environ.get("BENCH_MODELS", str(CACHE / "models"))) / folder)
    if name.startswith("faster-whisper"):
        model = name.split("-", 2)[2] if name.count("-") >= 2 else "small"
        return FasterWhisperBackend(model=model)
    raise SystemExit(f"unknown backend {name}")


def entities_found(text: str, ents: list[str]) -> int:
    t = text.lower()
    return sum(1 for e in ents if e.lower() in t)


# ------------------------------------------------------------------------------------------------ STT: accuracy and latency
async def sec_stt(args) -> None:  # noqa: ANN001
    langs = args.langs.split(",")
    tts = TTSEngine()
    await asyncio.get_running_loop().run_in_executor(None, tts.warm, "en", ["george"], False)
    print("building the corpus...", flush=True)
    clips = vc.build(tts, langs, per_lang=args.per_lang or (6 if args.quick else None))
    print(len(clips), "clips", flush=True)
    del tts
    results = load("stt") or {}
    ld = Load(args.load) if args.load else None
    recs: dict[str, Recognizer] = {}
    try:
        for bname in args.backends.split(","):
            rec = Recognizer(backends=[make_backend(bname)])
            await rec.start()
            if not await rec.ready():
                print(bname, "unavailable, skipped", flush=True)
                continue
            await rec.recognise(f32_to_pcm16(clips[0].pcm))                                # warm-up
            recs[bname] = rec
        # the engines take turns clip by clip, so whatever else the machine is doing, it does to all of them alike
        rows: dict[str, list] = {b: [] for b in recs}
        t_all = time.perf_counter()
        every = args.slow_every or (2 if args.quick else 3)
        n_cond = len(vc.CONDITIONS)
        for i, c in enumerate(clips):
            for bname, rec in recs.items():
                # the slower engines see a sample of the corpus, the same for all of them and balanced across the conditions
                # (a plain every-third clip would always land on the same condition: they come in threes)
                if bname.startswith(("whisperkit", "faster")) and (i // n_cond + i % n_cond) % every != 0:
                    continue
                t0 = time.perf_counter()
                tr = await rec.recognise(f32_to_pcm16(c.pcm), lang_hint=None)
                wall = time.perf_counter() - t0
                rows[bname].append({"lang": c.lang, "speaker": c.speaker, "cond": c.condition, "dur": c.seconds, "wall": wall, "decode": tr.decode_s,
                                    "wer": wer_fn(c.text, tr.text), "wer_raw": wer_fn(c.text, tr.raw), "n_ent": len(c.entities),
                                    "ent_raw": entities_found(tr.raw, c.entities), "ent_fix": entities_found(tr.text, c.entities),
                                    "lang_out": tr.lang, "conf": tr.conf, "text": tr.text, "raw": tr.raw, "ref": c.text, "ents": c.entities})
            if i % 60 == 0:
                print(f"  {i}/{len(clips)} clips ({time.perf_counter() - t_all:.0f} s)", flush=True)
        for bname, r in rows.items():
            key = bname + ("@" + args.load if args.load else "")
            results[key] = {"rows": r, "load_avg": load_avg(), "seconds": time.perf_counter() - t_all}
            summarise(key, r)
        save("stt", results)
    finally:
        for rec in recs.values():
            await rec.close()
        if ld:
            ld.stop()


def summarise(name: str, rows: list[dict]) -> None:
    for cond in ("clean", "noisy", "hard"):
        r = [x for x in rows if x["cond"] == cond]
        if r:
            print(f"{name:26s} {cond:5s} n={len(r):4d}  WER {100*np.mean([x['wer'] for x in r]):5.1f}%  latency median {1000*statistics.median([x['wall'] for x in r]):5.0f} ms "
                  f"p95 {1000*pct([x['wall'] for x in r], 95):5.0f} ms", flush=True)


# ------------------------------------------------------------------------------------------------ STT live: the key is held
async def sec_live(args) -> None:  # noqa: ANN001
    """A person holding the key: the audio arrives in 20 ms blocks in real time; at release, the time to the text."""
    langs = args.langs.split(",")
    tts = TTSEngine()
    await asyncio.get_running_loop().run_in_executor(None, tts.warm, "en", ["george"], False)
    clips = vc.build(tts, langs, conditions=["clean", "noisy"], pocket=["alba"], say_n=1, per_lang=5)
    clips = [c for i, c in enumerate(clips)]
    del tts
    results = load("live") or {}
    ld = Load(args.load) if args.load else None
    try:
        for bname in args.backends.split(","):
            backend = make_backend(bname)
            rec = Recognizer(backends=[backend])
            await rec.start()
            if not await rec.ready():
                continue
            await rec.recognise(f32_to_pcm16(clips[0].pcm))
            rows = []
            for c in clips[:: args.stride]:
                pcm = f32_to_pcm16(c.pcm)
                sess = rec.session()
                block = 320 * 2
                t0 = time.perf_counter()
                for i in range(0, len(pcm), block):
                    sess.feed(pcm[i:i + block])
                    await asyncio.sleep(max(0.0, t0 + (i + block) / 2 / 16000 - time.perf_counter()))
                # the key goes up 120 ms after the last word (a typical release), post-roll 100 ms of silence
                sil = np.zeros(int(0.22 * 16000), dtype="<i2").tobytes()
                for i in range(0, len(sil), block):
                    sess.feed(sil[i:i + block])
                    await asyncio.sleep(0.02)
                full = pcm + sil
                t1 = time.perf_counter()
                tr = await sess.finish(full)
                lat = time.perf_counter() - t1
                rows.append({"lang": c.lang, "cond": c.condition, "dur": c.seconds, "latency": lat, "partial_hit": tr.partial_hit,
                             "wer": wer_fn(c.text, tr.text)})
            key = bname + ("@" + args.load if args.load else "")
            results[key] = {"rows": rows, "load_avg": load_avg()}
            lat = [r["latency"] for r in rows]
            print(f"{key:28s} live: median {1000*statistics.median(lat):5.0f} ms  p95 {1000*pct(lat, 95):5.0f} ms  max {1000*max(lat):5.0f} ms  "
                  f"served from a partial {100*np.mean([r['partial_hit'] for r in rows]):.0f}%  WER {100*np.mean([r['wer'] for r in rows]):.1f}%", flush=True)
            await rec.close()
            save("live", results)
    finally:
        if ld:
            ld.stop()


# ------------------------------------------------------------------------------------------------ language decisions
async def sec_lang(args) -> None:  # noqa: ANN001
    from astra_mind.voice_lang import resolve_language, text_scores
    stt_rows = (load("stt") or {}).get("parakeet-ultra", {}).get("rows", [])
    if not stt_rows:
        raise SystemExit("run the stt section (parakeet-ultra) first: the language test uses its transcripts")
    langs = sorted({r["lang"] for r in stt_rows})
    wk = (load("stt") or {}).get("whisperkit-baseline", {}).get("rows", [])
    out: dict = {}
    for name, fn in (("only the text (lingua)", lambda r, prior: max(text_scores(r["text"]).items(), key=lambda kv: kv[1])[0] if r["text"] else prior),
                     ("text + crew vocabulary, no history", lambda r, prior: resolve_language(r["text"], "en" if False else prior, None)[0]),
                     ):
        pass
    correct = {"lingua": 0, "no_prior": 0, "prior_same": 0, "prior_wrong": 0}
    n = 0
    short = {"lingua": 0, "no_prior": 0, "prior_same": 0, "prior_wrong": 0}
    n_short = 0
    for r in stt_rows:
        if not r["text"] or r["cond"] != "clean":
            continue
        n += 1
        ts = text_scores(r["text"])
        best = max(ts.items(), key=lambda kv: kv[1])[0] if ts else ""
        d = {"lingua": best,
             "no_prior": resolve_language(r["text"], "zz")[0],
             "prior_same": resolve_language(r["text"], r["lang"])[0],
             "prior_wrong": resolve_language(r["text"], "en" if r["lang"] != "en" else "it")[0]}
        is_short = len(r["text"].split()) <= 3
        n_short += is_short
        for k, v in d.items():
            correct[k] += v == r["lang"]
            short[k] += is_short and v == r["lang"]
    out["overall"] = {k: v / n for k, v in correct.items()}
    out["short_phrases"] = {k: v / max(1, n_short) for k, v in short.items()}
    out["n"], out["n_short"] = n, n_short
    # a session: ten orders in one language after another, with the prior carried by the recogniser's own decisions
    flips = 0
    total = 0
    for lang in langs:
        prior = lang
        seq = [r for r in stt_rows if r["lang"] == lang and r["cond"] == "clean" and r["text"]][:24]
        for r in seq:
            got, conf = resolve_language(r["text"], prior)
            total += 1
            flips += got != lang
            prior = got
    out["session_flips"] = {"orders": total, "wrong": flips}
    # Whisper's own detection, where measured
    if wk:
        ok = sum(1 for r in wk if r["text"] and r["lang_out"] == r["lang"])
        out["whisper_out"] = {"n": len(wk), "correct": ok / max(1, len(wk))}
    save("lang", out)
    print(json.dumps(out, indent=1))


# ------------------------------------------------------------------------------------------------ languages beyond the crew's
async def sec_other(args) -> None:  # noqa: ANN001
    rec = Recognizer()
    await rec.start()
    if not await rec.ready():
        raise SystemExit("no recogniser")
    rows = []
    for lang, (voice, text) in vc.OTHER.items():
        x = vc.say_clip(voice, text)
        if x is None:
            continue
        pcm = f32_to_pcm16(x)
        rec.prior = "en"                                     # a Captain who has not spoken it before
        t0 = time.perf_counter()
        tr = await rec.recognise(pcm)
        first = time.perf_counter() - t0
        rec.prior = lang                                     # ... and one who speaks it all the time
        t0 = time.perf_counter()
        tr2 = await rec.recognise(pcm)
        again = time.perf_counter() - t0
        cer = char_error(text, tr.text) if lang in ("ja", "zh") else None
        # and the crew answering in it: a system voice speaks the same phrase, the recogniser checks it
        tts = getattr(sec_other, "tts", None) or TTSEngine()
        sec_other.tts = tts
        spoken = {"first_ms": None, "lufs": None, "heard": ""}
        if tts.can_speak(lang):
            t0 = time.perf_counter()
            st = tts.stream(text, "alba", lang)
            pcm_out = b"".join([c async for c in st])
            xs = np.frombuffer(pcm_out, dtype="<i2").astype(np.float32) / 32768.0
            heard, _ = await rec.transcribe(f32_to_pcm16(resample(xs, tts.sample_rate, 16000)), language=None, glossary=False)
            spoken = {"first_ms": (st.t_first or 0) * 1000, "lufs": integrated_lufs(xs, tts.sample_rate), "heard": heard}
        rows.append({"lang": lang, "voice": voice, "first": {"lang": tr.lang, "backend": tr.backend, "escalated": tr.escalated, "s": first, "text": tr.text},
                     "known": {"lang": tr2.lang, "backend": tr2.backend, "s": again, "text": tr2.text}, "cer": cer, "ref": text, "spoken": spoken})
        print(f"{lang}: first phrase -> {tr.lang} via {tr.backend} in {first:.2f}s | known -> {tr2.lang} via {tr2.backend} in {again:.2f}s | {tr.text!r} | crew voice {spoken['first_ms']}", flush=True)
    save("other", rows)
    await rec.close()


def char_error(ref: str, hyp: str) -> float:
    r = re.sub(r"[\W\d_]+", "", ref)
    h = re.sub(r"[\W\d_]+", "", hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = range(len(r) + 1)
    d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return float(d[len(r), len(h)] / max(1, len(r)))


# ------------------------------------------------------------------------------------------------ TTS
async def sec_tts(args) -> None:  # noqa: ANN001
    from astra_mind.crew import CREW
    from astra_mind.voice_casting import EXTRA
    langs = args.langs.split(",")
    tts = TTSEngine()
    rec = Recognizer(backends=[ParakeetBackend()])
    await rec.start()
    await rec.ready()
    rows = []
    ld = Load(args.load) if args.load else None
    voices = [o.voice for o in CREW.values()]
    try:
        for lang in langs:
            texts = CALIBRATION[lang] + [EXTRA[lang]]
            await asyncio.get_running_loop().run_in_executor(None, tts.warm, lang, voices, False)
            model = tts._model(lang)
            for v in voices:
                state = tts._voice(lang, v)
                tts.profile(lang, v)
                for text in texts:
                    # the first version's path: the raw model, chunks straight to PCM16
                    def old():
                        t0 = time.perf_counter()
                        ch, first_sound = [], None
                        for c in model.generate_audio_stream(state, text):
                            a = c.detach().cpu().numpy().astype(np.float32).reshape(-1)
                            ch.append(a)
                            if first_sound is None and np.sqrt(np.mean(a ** 2)) > 10 ** (-50 / 20):
                                first_sound = time.perf_counter() - t0
                        return np.concatenate(ch), first_sound, time.perf_counter() - t0
                    xo, fs_old, tot_old = await asyncio.get_running_loop().run_in_executor(None, old)
                    t0 = time.perf_counter()
                    st = tts.stream(text, v, lang)
                    chunks, first_sound = [], None
                    async for c in st:
                        a = np.frombuffer(c, dtype="<i2").astype(np.float32) / 32768.0
                        chunks.append(a)
                        if first_sound is None and np.sqrt(np.mean(a ** 2)) > 10 ** (-50 / 20):
                            first_sound = time.perf_counter() - t0
                    tot_new = time.perf_counter() - t0
                    xn = np.concatenate(chunks)
                    heard_o, _ = await rec.transcribe(f32_to_pcm16(resample(xo, tts.sample_rate, 16000)), language=lang, glossary=False)
                    heard_n, _ = await rec.transcribe(f32_to_pcm16(resample(xn, tts.sample_rate, 16000)), language=lang, glossary=False)
                    rows.append({"lang": lang, "voice": v, "chars": len(text),
                                 "old": {"dur": len(xo) / tts.sample_rate, "lufs": integrated_lufs(xo, tts.sample_rate), "peak": peak_db(xo),
                                         "first_sound": fs_old, "total": tot_old, "wer": wer_fn(text, heard_o)},
                                 "new": {"dur": len(xn) / tts.sample_rate, "lufs": integrated_lufs(xn, tts.sample_rate), "peak": peak_db(xn),
                                         "first_sound": first_sound, "first_chunk": st.t_first, "total": tot_new, "wer": wer_fn(text, heard_n),
                                         "pauses": len(st.boundaries)}})
                print(lang, v, "old dur %.2f -> new %.2f s; first sound %.0f -> %.0f ms" % (rows[-1]["old"]["dur"], rows[-1]["new"]["dur"],
                                                                                           1000 * (rows[-1]["old"]["first_sound"] or 0), 1000 * (rows[-1]["new"]["first_sound"] or 0)), flush=True)
    finally:
        if ld:
            ld.stop()
    key = "tts" + ("@" + args.load if args.load else "")
    data = load("tts") or {}
    data[key] = {"rows": rows, "load_avg": load_avg(), "speed": tts.speed, "target_lufs": tts.target_lufs}
    save("tts", data)
    await rec.close()


# ------------------------------------------------------------------------------------------------ mic against a fake device
class FakeDevice:
    """A stand-in for `sounddevice`: 20 ms blocks delivered in real time from a shared signal (silence when nothing is queued)."""

    signal_lock = threading.Lock()
    queue = np.zeros(0, dtype=np.int16)
    open_delay = 0.12

    class RawInputStream:
        def __init__(self, samplerate, channels, dtype, blocksize, latency, callback):  # noqa: ANN001
            self.cb, self.n, self.rate = callback, blocksize, samplerate
            self.run = False
            self.th: threading.Thread | None = None

        def start(self) -> None:
            time.sleep(FakeDevice.open_delay)                               # opening a Core Audio input takes time
            self.run = True
            self.th = threading.Thread(target=self._loop, daemon=True)
            self.th.start()

        def _loop(self) -> None:
            t = time.perf_counter()
            rng = np.random.default_rng(1)
            while self.run:
                t += self.n / self.rate
                time.sleep(max(0.0, t - time.perf_counter()))
                with FakeDevice.signal_lock:
                    q = FakeDevice.queue
                    take = q[: self.n]
                    FakeDevice.queue = q[self.n:]
                block = np.zeros(self.n, dtype=np.int16)
                block[: len(take)] = take
                block = (block + rng.integers(-3, 4, self.n)).astype(np.int16)
                self.cb(block.tobytes(), self.n, None, None)

        def stop(self) -> None:
            self.run = False

        def close(self) -> None:
            self.run = False

    @staticmethod
    def query_devices(kind=None):  # noqa: ANN001
        return {"name": "Fake microphone"}


async def sec_mic(args) -> None:  # noqa: ANN001
    fake = types.ModuleType("sounddevice")
    fake.RawInputStream = FakeDevice.RawInputStream
    fake.query_devices = FakeDevice.query_devices
    sys.modules["sounddevice"] = fake
    from astra_mind.audio_in import PushToTalk
    tts = TTSEngine()
    x = vc.pocket_clip(tts, "alba", "it", "Timoniere, rotta due uno sette, avanti tutta.")
    speech = f32_to_pcm16(x)
    sp = np.frombuffer(speech, dtype="<i2")
    res: dict = {}

    def say(delay_s: float, sig: np.ndarray) -> None:
        def go() -> None:
            time.sleep(delay_s)
            with FakeDevice.signal_lock:
                FakeDevice.queue = np.concatenate([FakeDevice.queue, sig])
        threading.Thread(target=go, daemon=True).start()

    ptt = PushToTalk()
    got_chunks: list[bytes] = []
    # press 1: the device has to be opened (no pre-roll); speech begins 50 ms after the press
    t0 = time.perf_counter()
    ok = ptt.start(got_chunks.append)
    res["first_press_open_ms"] = (time.perf_counter() - t0) * 1000
    say(0.05, sp)
    await asyncio.sleep(len(sp) / 16000 + 0.4)
    rec1 = await ptt.finish()
    res["first_press"] = {"ok": ok, "speech_s": rec1.speech_s, "raw_s": rec1.raw_s, "preroll_s": rec1.preroll_s, "on_chunk_blocks": len(got_chunks)}
    # press 2: the device stays open; speech begins 200 ms BEFORE the press (the person starts talking as the finger goes down)
    await asyncio.sleep(0.6)
    say(0.0, sp)
    await asyncio.sleep(0.2)
    got2: list[bytes] = []
    ptt.start(got2.append)
    await asyncio.sleep(len(sp) / 16000 - 0.1)
    rec2 = await ptt.finish()
    # the first 200 ms of the phrase must be in the recording: compare the start of the speech with the reference
    lead = np.frombuffer(rec2.raw, dtype="<i2")
    corr = np.correlate(lead[: 16000].astype(np.float64), sp[: 3200].astype(np.float64), "valid")
    offset = int(np.argmax(corr))
    res["second_press"] = {"preroll_s": rec2.preroll_s, "speech_s": rec2.speech_s, "phrase_starts_at_s": offset / 16000,
                           "first_syllable_kept": rec2.preroll_s >= 0.19 and offset / 16000 < 0.15}
    # press 3: nothing said: an empty recording
    await asyncio.sleep(0.3)
    ptt.start()
    await asyncio.sleep(0.8)
    rec3 = await ptt.finish()
    res["silence_press"] = {"pcm_bytes": len(rec3.pcm), "raw_s": rec3.raw_s, "speech_s": rec3.speech_s}
    # press 4: released early (the last word is still in the buffers): the post-roll keeps it
    await asyncio.sleep(0.3)
    ptt.start()
    say(0.05, sp)
    await asyncio.sleep(len(sp) / 16000 - 0.05)                # the key goes up right at the end of the phrase
    rec4 = await ptt.finish()
    res["release_at_the_end"] = {"speech_s": rec4.speech_s, "phrase_s": len(sp) / 16000}
    ptt.close()
    print(json.dumps(res, indent=1))
    save("mic", res)


# ------------------------------------------------------------------------------------------------ the floor
def virtual_scenarios() -> list[dict]:
    """The scripted scenarios of the floor and the replay of the live test, each in a loop of its own in virtual time. Run in a thread: a
    loop cannot be started from inside the one this section runs in."""
    from . import voice_floor as vf
    from . import voice_replay as vr
    rows = []
    for sc in [*vf.SCENARIOS, *vr.SCENARIOS]:
        try:
            bad = vf.run(sc())
        except Exception as e:  # noqa: BLE001
            bad = [f"crashed {e!r}"]
        rows.append({"name": sc.__name__, "doc": (sc.__doc__ or "").strip().splitlines()[0], "bad": bad})
    return rows


async def sec_floor(args) -> None:  # noqa: ANN001
    rows = await asyncio.get_running_loop().run_in_executor(None, virtual_scenarios)
    print(f"{sum(1 for r in rows if not r['bad'])}/{len(rows)} scenarios pass")
    real = await real_floor()
    save("floor", {"scenarios": rows, "real": real})


async def real_floor() -> dict:
    """The floor with the real voice engine and a recording sink: how long a stop and an answer really take."""
    from astra_mind.speech import Voice
    from astra_mind.server import speaker_identity
    tts = TTSEngine()
    ev: list[tuple] = []

    async def sink(kind, payload):  # noqa: ANN001
        t = asyncio.get_running_loop().time()
        if kind == "audio":
            ev.append((t, "audio", struct.unpack("<I", payload[:4])[0], (len(payload) - 4) / 2 / tts.sample_rate))
        else:
            ev.append((t, payload["type"], payload.get("id") or payload.get("line"), payload))

    await asyncio.get_running_loop().run_in_executor(None, tts.warm, "it", ["alba", "giovanni", "eve"], False)
    v = Voice(tts, sink, speaker_identity)
    task = asyncio.create_task(v.run())
    stops, answers, firsts = [], [], []
    long = "Capitano, tutti i ponti riferiscono di essere pronti. La sala macchine conferma che il reattore regge al novanta per cento, il tattico ha i railgun carichi e la squadriglia Alpha è sul ponte."
    for i in range(10):
        ev.clear()
        t_say = asyncio.get_running_loop().time()
        await v.say("xo", long, "it", "calm")
        await asyncio.sleep(1.5 + 0.23 * i)                       # the key goes down at different places in the line
        t_down = asyncio.get_running_loop().time()
        v.captain_begin()
        await asyncio.sleep(0.9)
        v.captain_end(None)
        await asyncio.sleep(0.4)
        v.captain_turn_begin()
        t_ans = asyncio.get_running_loop().time()
        await v.say("helm", "Agli ordini, Capitano: rotta due-uno-sette.", "it", "focused", answer=True)
        v.captain_turn_end()
        await v.q.join()
        await asyncio.sleep(0.3)
        cancel = [e for e in ev if e[1] == "cancel"]
        if cancel:
            stops.append(cancel[0][0] - t_down)
        begins = [e for e in ev if e[1] == "audio_begin" and e[0] >= t_ans]
        if begins:
            answers.append(begins[0][0] - t_ans)
        b0 = [e for e in ev if e[1] == "audio_begin"]
        if b0:
            firsts.append(b0[0][0] - t_say)
        await v.clear("bench")
        await asyncio.sleep(0.5)
    task.cancel()
    return {"stop_s": stops, "answer_s": answers, "first_line_s": firsts}


# ------------------------------------------------------------------------------------------------ memory
def rss_mb(pid: int) -> float:
    try:
        return int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip() or 0) / 1024
    except (ValueError, OSError):
        return 0.0


async def sec_mem(args) -> None:  # noqa: ANN001
    """Resident memory of what the voice adds to the mind, step by step."""
    from astra_mind.crew import CREW
    res = {"start": rss_mb(os.getpid())}
    import astra_mind.server  # noqa: F401 - the whole mind's imports (lingua, pydantic, httpx, torch...)
    res["imports"] = rss_mb(os.getpid())
    tts = TTSEngine()
    voices = [o.voice for o in CREW.values()]
    for lg in ("en", "it"):
        await asyncio.get_running_loop().run_in_executor(None, tts.warm, lg, voices, False)
        res[f"tts_{lg}"] = rss_mb(os.getpid())
    from astra_mind.voice_lang import resolve_language
    resolve_language("Timoniere, rotta due uno sette", "it")
    res["lingua"] = rss_mb(os.getpid())
    b = ParakeetBackend()
    rec = Recognizer(backends=[b])
    await rec.start()
    await rec.ready()
    await rec.recognise(f32_to_pcm16(np.random.default_rng(0).standard_normal(16000 * 2).astype(np.float32) * 0.1))
    res["python_with_stt"] = rss_mb(os.getpid())
    res["astra_stt_helper"] = rss_mb(b._proc.pid) if b._proc else 0.0
    await rec.close()
    w = WhisperKitBackend(port=50075)
    if w.model_dir.exists():
        await w.start()
        res["whisperkit_server"] = rss_mb(w._proc.pid) if w._proc else 0.0
        w.stop()
    # the portable engines, loaded into this process one after the other: what each adds
    noise = f32_to_pcm16(np.random.default_rng(0).standard_normal(16000 * 2).astype(np.float32) * 0.1)
    sherpa_dir = Path(os.environ["BENCH_SHERPA"]) if os.environ.get("BENCH_SHERPA") else None
    if SherpaParakeetBackend.available(sherpa_dir):
        before = rss_mb(os.getpid())
        sb = SherpaParakeetBackend(model_dir=sherpa_dir)
        await sb.start()
        await sb.transcribe(noise)
        res["parakeet_onnx_added"] = rss_mb(os.getpid()) - before
        sb.stop()
    if FasterWhisperBackend.available():
        before = rss_mb(os.getpid())
        fb = FasterWhisperBackend(model="small")
        if await fb.start():
            await fb.transcribe(noise)
            res["faster_whisper_small_added"] = rss_mb(os.getpid()) - before
        fb.stop()
    print(json.dumps({k: round(v) for k, v in res.items()}, indent=1))
    save("mem", {k: round(v) for k, v in res.items()})


# ------------------------------------------------------------------------------------------------ report
def fmt_ms(x: float) -> str:
    return f"{1000 * x:.0f}"


def stt_key(x: dict) -> tuple:
    return (x["lang"], x["speaker"], x["cond"], x["ref"])


def stt_anchor_rows(base: dict, name: str) -> tuple[str, list[dict], list[dict]] | None:
    """(anchor name, this engine's rows, the anchor's rows) on the clips both saw. The anchor is a Parakeet Ultra run: the one with the
    most clips in common (on a tie the smaller run, which was interleaved with this engine, so the machine was doing the same to both)."""
    best = None
    for rn, rd in base.items():
        if not rn.startswith("parakeet-ultra") or rn == name:
            continue
        theirs = {stt_key(x): x for x in rd["rows"]}
        mine = [x for x in base[name]["rows"] if stt_key(x) in theirs]
        cand = (len(mine), -len(rd["rows"]), rn, mine, [theirs[stt_key(x)] for x in mine])
        if best is None or cand[:2] > best[:2]:
            best = cand
    return None if best is None or best[0] < 30 else (best[2], best[3], best[4])


def wer_cond(rows: list[dict], cond: str) -> str:
    r = [x["wer"] for x in rows if cond == "all" or x["cond"] == cond]
    return f"{100 * np.mean(r):.1f} %" if r else "—"


def ents_now(rows: list[dict]) -> tuple[int, int, int]:
    """(names found in the raw text, names found after today's glossary, names in the references) over the rows that kept the raw text."""
    raw_hits = now_hits = total = 0
    for x in rows:
        if "raw" not in x:
            continue
        fixed = GLOSSARY.correct(x["raw"])[0]
        raw_hits += entities_found(x["raw"], x["ents"])
        now_hits += entities_found(fixed, x["ents"])
        total += len(x["ents"])
    return raw_hits, now_hits, total


def summary_lines(stt, live, lang, other, tts, floor, mem) -> list[str]:  # noqa: ANN001
    """The few numbers that answer the owner's complaints, from the results of the sections that were run."""
    S: list[str] = ["## Sintesi", ""]
    if stt:
        base = {n: d for n, d in stt.items() if "@" not in n}
        pk = base.get("parakeet-ultra")
        if pk:
            walls = [x["wall"] for x in pk["rows"]]
            S.append(f"- **Riconoscimento, da registrazione finita a testo** — **Parakeet Ultra** sul Neural Engine (tutto il corpus, {len(walls)} frasi): mediana {fmt_ms(statistics.median(walls))} ms, "
                     f"p95 {fmt_ms(pct(walls, 95))} ms; WER {wer_cond(pk['rows'], 'clean')} pulito, {wer_cond(pk['rows'], 'noisy')} rumoroso, {wer_cond(pk['rows'], 'hard')} difficile.")
        for n, d in base.items():
            if n.startswith("parakeet-ultra"):
                continue
            pair = stt_anchor_rows(base, n)
            if pair is None:
                continue
            an, mine, theirs = pair
            note = ""
            if abs(base[n]["load_avg"] - base[an]["load_avg"]) > 2.0:
                note = f" (misure in prove diverse: carico medio {base[n]['load_avg']:.1f} contro {base[an]['load_avg']:.1f}, i tempi non sono confrontabili, il WER sì)"
            S.append(f"  - **{n}** sulle stesse {len(mine)} frasi di {an}{note}: mediana {fmt_ms(statistics.median([x['wall'] for x in mine]))} ms "
                     f"(p95 {fmt_ms(pct([x['wall'] for x in mine], 95))}) contro {fmt_ms(statistics.median([x['wall'] for x in theirs]))} ms; "
                     f"WER pulito {wer_cond(mine, 'clean')} contro {wer_cond(theirs, 'clean')}, rumoroso {wer_cond(mine, 'noisy')} contro {wer_cond(theirs, 'noisy')}.")
        pk = base.get("parakeet-ultra")
        if pk:
            raw_hits, now_hits, n_ent = ents_now(pk["rows"])
            if n_ent:
                S.append(f"- **Nomi del gioco** (Praetorian, Acheron, Voss…), a voce sintetica con accento straniero: trovati {100 * raw_hits / n_ent:.0f} % dal motore da solo, "
                         f"{100 * now_hits / n_ent:.0f} % con il glossario attuale (tabella sotto: il resto sono nomi che il motore non scrive affatto o scrive troppo lontani).")
    if live:
        for n, d in live.items():
            if "@" in n:
                continue
            lat = [x["latency"] + 0.1 for x in d["rows"]]
            S.append(f"- **Dal rilascio del tasto al testo** ({n}; parlato in tempo reale, il tasto sale 220 ms dopo l'ultima parola; comprende i 100 ms di post-roll del microfono): "
                     f"mediana {fmt_ms(statistics.median(lat))} ms, p95 {fmt_ms(pct(lat, 95))} ms, massimo {fmt_ms(max(lat))} ms su {len(lat)} frasi; "
                     f"{100 * np.mean([x['partial_hit'] for x in d['rows']]):.0f} % delle risposte era già pronta da una decodifica fatta mentre il Capitano parlava.")
    if lang:
        S.append(f"- **Lingua dell'ordine**: giusta nel {100 * lang['overall']['prior_wrong']:.1f} % dei casi anche quando la lingua precedente era sbagliata "
                 f"({100 * lang['short_phrases']['prior_wrong']:.1f} % sulle frasi di tre parole o meno); {lang['session_flips']['wrong']} errori su {lang['session_flips']['orders']} ordini in sessione.")
    if tts:
        d = tts.get("tts") or next(iter(tts.values()))
        rows = d["rows"]
        lo, ln = [x["old"]["lufs"] for x in rows], [x["new"]["lufs"] for x in rows]
        do, dn = np.mean([x["old"]["dur"] for x in rows]), np.mean([x["new"]["dur"] for x in rows])
        S.append(f"- **Sintesi**: righe {100 * (1 - dn / do):.0f} % più brevi ({do:.2f} → {dn:.2f} s in media); volume delle voci da {min(lo):.1f}…{max(lo):.1f} LUFS (σ {np.std(lo):.1f}) "
                 f"a {min(ln):.1f}…{max(ln):.1f} LUFS (σ {np.std(ln):.1f}); primo suono mediano {fmt_ms(statistics.median([x['old']['first_sound'] or 0 for x in rows]))} → "
                 f"{fmt_ms(statistics.median([x['new']['first_sound'] or 0 for x in rows]))} ms; generazione {np.mean([x['new']['total'] / x['new']['dur'] for x in rows]):.2f} s "
                 f"di calcolo per secondo di parlato (carico medio {d['load_avg']:.1f}).")
    if floor:
        ok = sum(1 for r in floor["scenarios"] if not r["bad"])
        real = floor.get("real", {})
        extra = ""
        if real.get("stop_s"):
            extra = (f"; con la voce vera chi parla si ferma in {fmt_ms(statistics.median(real['stop_s']))} ms (massimo {fmt_ms(max(real['stop_s']))}) dalla pressione del tasto "
                     f"e la risposta parte {fmt_ms(statistics.median(real['answer_s']))} ms dopo essere stata scritta")
        S.append(f"- **Palco del parlato**: {ok}/{len(floor['scenarios'])} scenari con orologio virtuale superati (nessun sottotitolo senza audio, nessuna riga persa in silenzio, "
                 f"il Capitano per primo, una voce alla volta){extra}.")
    if mem:
        S.append(f"- **Memoria**: la parte di voce aggiunge circa {mem.get('python_with_stt', 0) - mem.get('imports', 0)} MB al processo Python (due lingue di sintesi comprese) e "
                 f"{mem.get('astra_stt_helper', 0)} MB di helper Parakeet; WhisperKit ({mem.get('whisperkit_server', 0)} MB) si carica solo se serve e si scarica dopo dieci minuti.")
    S.append("")
    return S


def decisions_lines(stt, live, tts, floor, mem, other) -> list[str]:  # noqa: ANN001
    """What was decided on these measurements, with the numbers that decided it (whatever sections were run)."""
    D: list[str] = ["## Decisioni prese su queste misure", ""]
    base = {n: d for n, d in (stt or {}).items() if "@" not in n}

    def med(rows, key="wall"):  # noqa: ANN001, ANN202
        return statistics.median([x[key] for x in rows]) if rows else float("nan")

    pk, wb, wt, v3 = base.get("parakeet-ultra"), base.get("whisperkit-baseline"), base.get("whisperkit-tuned"), base.get("parakeet-v3")
    if pk and wb:
        pair = stt_anchor_rows(base, "whisperkit-baseline")
        if pair:
            an, mine, theirs = pair
            D.append(f"1. **Il motore di riconoscimento è Parakeet Ultra sul Neural Engine.** Mediana {fmt_ms(med(theirs))} ms contro {fmt_ms(med(mine))} ms di Whisper large-v3-turbo "
                     f"sulle stesse frasi (×{med(mine) / max(1e-9, med(theirs)):.0f} più veloce); WER pulito {wer_cond(theirs, 'clean')} contro {wer_cond(mine, 'clean')}, "
                     f"rumoroso {wer_cond(theirs, 'noisy')} contro {wer_cond(mine, 'noisy')}, difficile {wer_cond(theirs, 'hard')} contro {wer_cond(mine, 'hard')}. "
                     "Whisper resta per le lingue che Parakeet non conosce (giapponese, cinese, coreano, arabo, turco…).")
    if pk and v3:
        D.append(f"2. **Ultra e non v3**: stessa velocità (nella prova in cui giravano insieme, con la macchina carica: 120 e 123 ms di mediana), WER pulito {wer_cond(pk['rows'], 'clean')} contro {wer_cond(v3['rows'], 'clean')} e in condizioni difficili "
                 f"{wer_cond(pk['rows'], 'hard')} contro {wer_cond(v3['rows'], 'hard')}.")
    if wb and wt:
        D.append(f"3. **I flag di WhisperKit non si toccano.** «Tarato» (senza fallback di temperatura né divisione in blocchi) guadagna {100 * (1 - med(wt['rows']) / med(wb['rows'])):.0f} % di tempo "
                 f"e nel rumore peggiora molto (WER difficile {wer_cond(wt['rows'], 'hard')} contro {wer_cond(wb['rows'], 'hard')}): il fallback di temperatura serve quando l'audio è brutto.")
    if pk and wb:
        D.append("4. **Il secondo parere di Whisper non si chiede per confidenza bassa sulle lingue europee**: sulle stesse frasi Whisper non fa meglio di Parakeet, e chiedergli "
                 "un parere su ogni frase con confidenza sotto 0,86 avrebbe fatto attendere circa il 6 % delle frasi pulite, il 14 % delle rumorose e il 54 % di quelle in battaglia "
                 "di 1,8 s per un risultato in media peggiore. La regola è: confidenza sotto 0,84 **e** nessuna parola di plancia nel testo (è quello che Parakeet scrive per una lingua "
                 "che non conosce: 6 frasi su 6 in sei lingue non europee; 0,5 % delle frasi europee pulite, 1 % delle rumorose, 11 % delle difficili).")
    variants = [n for n in base if n.startswith(("whisperkit-turbo632", "whisperkit-small216", "faster-whisper", "parakeet-onnx"))]
    if variants:
        parts = []
        for n in variants:
            pair = stt_anchor_rows(base, n)
            if pair:
                an, mine, theirs = pair
                parts.append(f"{n}: mediana {fmt_ms(med(mine))} ms (Parakeet Ultra {fmt_ms(med(theirs))} ms), WER pulito {wer_cond(mine, 'clean')} (Ultra {wer_cond(theirs, 'clean')}), "
                             f"rumoroso {wer_cond(mine, 'noisy')} (Ultra {wer_cond(theirs, 'noisy')})")
        if parts:
            D.append("5. **Le alternative provate** (stesso campione, motori alternati): " + "; ".join(parts) + ".")
    if live:
        d = live.get("parakeet-ultra")
        if d:
            lat = [x["latency"] + 0.1 for x in d["rows"]]
            D.append(f"6. **Bozze mentre il tasto è premuto**: dal rilascio al testo mediana {fmt_ms(statistics.median(lat))} ms, massimo {fmt_ms(max(lat))} ms "
                     f"({100 * np.mean([x['partial_hit'] for x in d['rows']]):.0f} % delle risposte già pronte alla pressione del tasto).")
    if tts:
        d = tts.get("tts") or next(iter(tts.values()))
        rows = d["rows"]
        D.append(f"7. **Sintesi**: velocità ×{d['speed']} (le righe durano {100 * (1 - np.mean([x['new']['dur'] for x in rows]) / np.mean([x['old']['dur'] for x in rows])):.0f} % di meno con le pause accorciate), "
                 f"volume uniforme a {d['target_lufs']} LUFS (σ {np.std([x['old']['lufs'] for x in rows]):.1f} → {np.std([x['new']['lufs'] for x in rows]):.1f} dB), "
                 "voci sostituite dove una è poco comprensibile in una lingua (una sostituta per un solo ufficiale).")
    if floor:
        D.append("8. **Palco del parlato**: il Capitano prende la parola al tasto (chi parla si ferma alla pausa entro mezzo secondo), la sua risposta passa prima di tutto, "
                 "le altre righe sono dette, unite, accorciate o scartate secondo regole chiare e mai in silenzio. Dal test dal vivo del capo (risposte suonate 30-45 s dopo, dietro rapporti "
                 "vecchi e un messaggio del nemico di 20 s): la risposta a un ordine passa prima di ogni rapporto e di ogni voce da fuori; un ordine scritto ferma chi parla ma non una risposta "
                 "già in corso (il tasto sì); una notizia vecchia non si dice in ritardo (18 s dalla notizia, un turno di evento non si fa se anche l'ultima notizia ha più di 12 s); un messaggio "
                 "lungo interrotto riprende dalla frase tagliata, ridotto a prima e ultima frase se il resto supera 10 s; un avviso di pericolo non aspetta un ponte silenzioso.")
    D.append("")
    return D


def italian_numbers(lines: list[str]) -> list[str]:
    """Decimal commas in the prose and the tables (not in code blocks): the report is in Italian, 14,5 % and not 14.5 %."""
    out, fenced = [], False
    for line in lines:
        if line.startswith("```"):
            fenced = not fenced
        out.append(line if fenced or line.startswith("```") else re.sub(r"(?<![\w.])(\d+)\.(\d+)(?![\w.])", r"\1,\2", line))
    return out


def report(args) -> None:  # noqa: ANN001
    out = REPO_ROOT / "docs" / "bench" / f"voce_{TODAY}.md"
    L: list[str] = [f"# Voce: riconoscimento, sintesi, palco del parlato — {TODAY}", ""]
    stt, live, lang, other, tts, mic, floor, mem, e2e = (load(s) for s in ("stt", "live", "lang", "other", "tts", "mic", "floor", "mem", "e2e"))
    L += ["Macchina: MacBook Air M4 16 GB. **Durante le misure l'editor di Unreal era aperto e altri agenti compilavano** (il carico medio, su 10 core, è scritto accanto a "
          "ogni misura): i tempi sono quelli di un Mac già occupato, non di uno libero. Il parlato di prova è sintetico (Pocket TTS e voci di sistema macOS), non registrazioni "
          "di persone: misura le differenze tra motori, il peso dei nomi del gioco, del rumore e della lingua, non la precisione assoluta su una persona stanca con il "
          "microfono del portatile. Dove più motori sono confrontati, si alternano clip per clip (quello che il resto della macchina fa in quel momento lo fa a tutti).", ""]
    L += summary_lines(stt, live, lang, other, tts, floor, mem)
    if stt:
        L += ["## 1. Riconoscimento vocale", ""]
        L += ["Frasi d'ordine (2–7 s) in sette lingue, cinque voci per frase (tre Pocket TTS, due voci di sistema), tre condizioni: pulito, rumoroso (15 dB sopra "
              "ventilazione, ronzio del reattore e bip delle console) e difficile (6 dB, riverbero, un'altra voce che parla, esplosioni). "
              "WER = parole sbagliate / parole, numeri esclusi (oltre 100 % vuol dire che il motore ha scritto più parole sbagliate o inventate di quante ne fossero state dette: "
              "rumore preso per parole). Latenza = tempo da una registrazione finita al testo (motore + taglio del silenzio + glossario). I campioni più piccoli (le prove delle "
              "alternative e sotto carico usano le prime tre frasi di ogni lingua, le più brevi) hanno WER più alti dell'intero corpus: si confrontano solo sulle stesse frasi.", ""]
        L += ["| Motore | condizione | n | WER | latenza mediana ms | p95 ms | carico medio |", "|---|---|---|---|---|---|---|"]
        for name, d in stt.items():
            rows = d["rows"]
            for cond in ("clean", "noisy", "hard"):
                r = [x for x in rows if x["cond"] == cond]
                if r:
                    L.append(f"| {name} | {cond} | {len(r)} | {100 * np.mean([x['wer'] for x in r]):.1f} % | {fmt_ms(statistics.median([x['wall'] for x in r]))} | "
                             f"{fmt_ms(pct([x['wall'] for x in r], 95))} | {d['load_avg']:.1f} |")
        L += ["", "### WER per lingua (condizione pulita)", "", "| Motore | " + " | ".join(sorted({x['lang'] for d in stt.values() for x in d['rows']})) + " |",
              "|---|" + "---|" * len({x['lang'] for d in stt.values() for x in d['rows']})]
        langs = sorted({x['lang'] for d in stt.values() for x in d['rows']})
        for name, d in stt.items():
            cells = []
            for lg in langs:
                r = [x for x in d["rows"] if x["lang"] == lg and x["cond"] == "clean"]
                cells.append(f"{100 * np.mean([x['wer'] for x in r]):.1f}" if r else "—")
            L.append(f"| {name} | " + " | ".join(cells) + " |")
        base = {n: d for n, d in stt.items() if "@" not in n}
        rows_tab = []
        for name in base:
            pair = None if name.startswith("parakeet-ultra") else stt_anchor_rows(base, name)
            if pair is None:
                continue
            an, mine, theirs = pair
            rows_tab.append(f"| {name} | {len(mine)} | {wer_cond(mine, 'clean')} | {wer_cond(mine, 'noisy')} | {wer_cond(mine, 'hard')} | "
                            f"{wer_cond(theirs, 'clean')} / {wer_cond(theirs, 'noisy')} / {wer_cond(theirs, 'hard')} ({an}) | "
                            f"{fmt_ms(statistics.median([x['wall'] for x in mine]))} / {fmt_ms(statistics.median([x['wall'] for x in theirs]))} | "
                            f"{fmt_ms(pct([x['wall'] for x in mine], 95))} / {fmt_ms(pct([x['wall'] for x in theirs], 95))} | {base[name]['load_avg']:.1f} |")
        if rows_tab:
            L += ["", "### Ogni motore contro Parakeet Ultra, sulle stesse frasi", "",
                  "Un motore che ha visto solo un campione del corpus (i Whisper: uno ogni due o tre frasi, bilanciato tra le condizioni) si confronta con Parakeet Ultra sulle "
                  "*stesse* frasi. Latenza «motore / Parakeet»: i due si alternano clip per clip nella stessa prova.", "",
                  "| Motore | frasi | WER pulito | WER rumoroso | WER difficile | Parakeet Ultra: pulito / rumoroso / difficile | latenza mediana ms | p95 ms | carico medio |",
                  "|---|---|---|---|---|---|---|---|---|"] + rows_tab
        L += ["", "### Nomi del gioco (Praetorian, Acheron, Lindqvist, Janus Gate…)", "",
              "I nomi sono detti da voci sintetiche con l'accento della loro lingua: un motore che scrive «Queron» per «Acheron» sbaglia per lo stesso motivo per cui sbaglierebbe con una persona "
              "che lo pronuncia all'italiana. «Glossario attuale» = il glossario del codice di oggi applicato al testo grezzo salvato (correzioni fonetiche, nome dell'ufficiale in vocativo a "
              "inizio frase, vocale iniziale persa); la colonna «glossario alla misura» è quello che c'era quando la misura è stata fatta.", "",
              "| Motore | nomi trovati grezzi | glossario alla misura | glossario attuale | totale |", "|---|---|---|---|---|"]
        for name, d in stt.items():
            n = sum(x["n_ent"] for x in d["rows"])
            raw_hits, now_hits, n_now = ents_now(d["rows"])
            L.append(f"| {name} | {sum(x['ent_raw'] for x in d['rows'])} ({100 * sum(x['ent_raw'] for x in d['rows']) / max(1, n):.0f} %) | "
                     f"{sum(x['ent_fix'] for x in d['rows'])} ({100 * sum(x['ent_fix'] for x in d['rows']) / max(1, n):.0f} %) | "
                     + (f"{now_hits} ({100 * now_hits / max(1, n_now):.0f} %)" if n_now else "—") + f" | {n} |")
        pk = stt.get("parakeet-ultra")
        if pk and any("raw" in x for x in pk["rows"]):
            by_e: dict[str, list[int]] = {}
            for x in pk["rows"]:
                if "raw" not in x:
                    continue
                fixed = GLOSSARY.correct(x["raw"])[0]
                for e in x["ents"]:
                    c = by_e.setdefault(e, [0, 0, 0])
                    c[0] += 1
                    c[1] += e.lower() in x["raw"].lower()
                    c[2] += e.lower() in fixed.lower()
            L += ["", "Per nome (Parakeet Ultra, tutte le condizioni):", "", "| Nome | frasi | grezzo | glossario attuale |", "|---|---|---|---|"]
            for e, (n_e, a, b) in sorted(by_e.items(), key=lambda kv: kv[1][2] / kv[1][0]):
                L.append(f"| {e} | {n_e} | {100 * a / n_e:.0f} % | {100 * b / n_e:.0f} % |")
        L.append("")
    if live:
        L += ["## 2. Dal rilascio del tasto al testo (parlato ricevuto in tempo reale, decodifica incrementale)", "",
              "Il parlato arriva a blocchi di 20 ms come dal microfono; il tasto si rilascia 220 ms dopo l'ultima parola. Latenza = da `finish()` al testo; "
              "a questa si aggiungono i 100 ms di post-roll del microfono (l'ultimo suono deve uscire dai buffer del sistema), quindi **dal rilascio del tasto al testo** = latenza + 0,1 s.", "",
              "| Motore | frasi | mediana ms | p95 ms | max ms | risposta da una decodifica parziale | WER |", "|---|---|---|---|---|---|---|"]
        for name, d in live.items():
            r = d["rows"]
            lat = [x["latency"] for x in r]
            L.append(f"| {name} | {len(r)} | {fmt_ms(statistics.median(lat))} | {fmt_ms(pct(lat, 95))} | {fmt_ms(max(lat))} | {100 * np.mean([x['partial_hit'] for x in r]):.0f} % | "
                     f"{100 * np.mean([x['wer'] for x in r]):.1f} % |")
        L.append("")
    if lang:
        L += ["## 3. Lingua dell'ordine", "", f"Testi trascritti da Parakeet (condizione pulita, {lang['n']} frasi, di cui {lang['n_short']} di tre parole o meno).", "",
              "| Metodo | corretta su tutte | corretta su frasi brevi |", "|---|---|---|"]
        names = {"lingua": "solo il testo (lingua)", "no_prior": "testo + vocabolario di bordo, senza storia", "prior_same": "… con la lingua dell'ordine precedente = quella giusta",
                 "prior_wrong": "… con la lingua precedente sbagliata (cambio di lingua)"}
        for k, nm in names.items():
            L.append(f"| {nm} | {100 * lang['overall'][k]:.1f} % | {100 * lang['short_phrases'][k]:.1f} % |")
        L += ["", f"Sessioni di ordini nella stessa lingua: {lang['session_flips']['wrong']} errori su {lang['session_flips']['orders']} ordini.", ""]
    if other:
        L += ["## 4. Lingue fuori dall'equipaggio (percorso di riserva)", "", "Una frase in ciascuna lingua, detta da una voce di sistema macOS. «Prima frase»: il Capitano non l'ha mai usata (storia = inglese); «nota»: "
              "parla sempre quella. «Risposta dell'equipaggio»: la stessa frase detta dalla voce di sistema che sostituisce Pocket TTS (che non parla queste lingue), "
              "ritrascritta dal riconoscitore.", "",
              "| Lingua | prima frase: lingua, motore, s | nota: lingua, motore, s | CER (ja, zh) | risposta dell'equipaggio: primo suono ms, LUFS |", "|---|---|---|---|---|"]
        for r in other:
            sp = r.get("spoken") or {}
            L.append(f"| {r['lang']} | {r['first']['lang']}, {r['first']['backend']}{' (2° parere)' if r['first']['escalated'] else ''}, {r['first']['s']:.2f} | "
                     f"{r['known']['lang']}, {r['known']['backend']}, {r['known']['s']:.2f} | {'—' if r['cer'] is None else f'{100 * r['cer']:.0f} %'} | "
                     f"{'—' if sp.get('first_ms') is None else f'{sp['first_ms']:.0f} ms, {sp['lufs']:.1f}'} |")
        L.append("")
    if tts:
        L += ["## 5. Sintesi vocale", "",
              "Le dieci voci degli ufficiali, quattro frasi per lingua (tre battute di plancia e una piena di nomi di navi). «Prima» è il percorso della prima versione "
              "(modello grezzo, voce originale, blocchi convertiti a PCM16 così come escono); «dopo» è la catena attuale (numeri in lettere, pause accorciate, velocità, "
              "volume uniforme, limitatore) con le sostituzioni di voce del casting dove una voce è poco comprensibile in una lingua. «Primo suono» = dal via della "
              "generazione al primo blocco sopra −50 dBFS; RTF = secondi di calcolo per secondo di parlato (sotto 1 si genera più in fretta di quanto si ascolta).", ""]
        for key, d in tts.items():
            rows = d["rows"]
            L += [f"### {key} (carico medio {d['load_avg']:.1f}; velocità x{d['speed']}, obiettivo {d['target_lufs']} LUFS)", "",
                  "| Lingua | durata prima→dopo | primo suono ms prima→dopo | primo chunk ms | RTF prima→dopo (s di calcolo per s di parlato) | LUFS prima (min…max, σ) | LUFS dopo (min…max, σ) | WER prima→dopo |",
                  "|---|---|---|---|---|---|---|---|"]
            for lg in sorted({r["lang"] for r in rows}):
                r = [x for x in rows if x["lang"] == lg]
                lo = [x["old"]["lufs"] for x in r]
                ln = [x["new"]["lufs"] for x in r]
                L.append(f"| {lg} | {np.mean([x['old']['dur'] for x in r]):.2f} → {np.mean([x['new']['dur'] for x in r]):.2f} s "
                         f"({100 * (np.mean([x['new']['dur'] for x in r]) / np.mean([x['old']['dur'] for x in r]) - 1):+.0f} %) | "
                         f"{fmt_ms(statistics.median([x['old']['first_sound'] or 0 for x in r]))} → {fmt_ms(statistics.median([x['new']['first_sound'] or 0 for x in r]))} | "
                         f"{fmt_ms(statistics.median([x['new']['first_chunk'] or 0 for x in r]))} | "
                         f"{np.mean([x['old']['total'] / x['old']['dur'] for x in r]):.2f} → {np.mean([x['new']['total'] / x['new']['dur'] for x in r]):.2f} | "
                         f"{min(lo):.1f}…{max(lo):.1f}, {np.std(lo):.1f} | {min(ln):.1f}…{max(ln):.1f}, {np.std(ln):.1f} | "
                         f"{100 * np.mean([x['old']['wer'] for x in r]):.1f} → {100 * np.mean([x['new']['wer'] for x in r]):.1f} % |")
            allo = [x["old"]["lufs"] for x in rows]
            alln = [x["new"]["lufs"] for x in rows]
            L += ["", f"Tutte le lingue: volume da {min(allo):.1f}…{max(allo):.1f} LUFS (σ {np.std(allo):.1f}) a {min(alln):.1f}…{max(alln):.1f} LUFS (σ {np.std(alln):.1f}); "
                      f"durata media {np.mean([x['old']['dur'] for x in rows]):.2f} → {np.mean([x['new']['dur'] for x in rows]):.2f} s; "
                      f"picco massimo dopo {max(x['new']['peak'] for x in rows):.1f} dBFS.", ""]
    if mic:
        L += ["## 6. Microfono (dispositivo finto)", "", "```", json.dumps(mic, indent=1), "```", ""]
    if floor:
        ok = sum(1 for r in floor["scenarios"] if not r["bad"])
        L += ["## 7. Il palco del parlato", "", f"Scenari con orologio virtuale: **{ok}/{len(floor['scenarios'])}** superati (invarianti: nessun sottotitolo senza audio, una voce alla volta, "
              "nessuna riga persa in silenzio, audio a passo, pause naturali, Capitano per primo, sottotitolo abbastanza lungo). Gli scenari `s*` provano il palco da solo "
              "(`bench/voice_floor.py`); gli `r*` rifanno la sequenza del test dal vivo del capo (rapporti in coda, un messaggio lungo del nemico, tre ordini scritti) attraverso "
              "il server vero, con l'agente, il router e la selezione delle priorità, e solo il modello di linguaggio e le voci finti (`bench/voice_replay.py`).", "",
              "| Scenario | esito |", "|---|---|"]
        for r in floor["scenarios"]:
            L.append(f"| {r['name']}: {r['doc']} | {'ok' if not r['bad'] else 'FALLITO: ' + '; '.join(r['bad'])} |")
        real = floor.get("real", {})
        if real.get("stop_s"):
            L += ["", "Con la voce vera (dieci prove, il tasto scende in punti diversi di una riga lunga):", "",
                  f"- **Fermata del parlante**: mediana {fmt_ms(statistics.median(real['stop_s']))} ms, massima {fmt_ms(max(real['stop_s']))} ms dopo la pressione del tasto",
                  f"- **Risposta al Capitano** (da quando il modello la scrive al primo suono): mediana {fmt_ms(statistics.median(real['answer_s']))} ms, massima {fmt_ms(max(real['answer_s']))} ms",
                  f"- **Prima riga su piano libero** (dall'accodamento al primo suono): mediana {fmt_ms(statistics.median(real['first_line_s']))} ms", ""]
    if mem:
        L += ["## 8. Memoria residente (MB)", "", "| Passo | MB |", "|---|---|"]
        for k, label in (("start", "Python appena avviato"), ("imports", "dopo gli import della mente (torch, lingua, pydantic…)"), ("tts_en", "+ Pocket TTS inglese, dieci voci"),
                         ("tts_it", "+ Pocket TTS italiano, dieci voci"), ("lingua", "+ rilevatore di lingua"), ("python_with_stt", "+ sessione di riconoscimento"),
                         ("astra_stt_helper", "processo a parte: helper Parakeet (il modello vive nel Neural Engine)"),
                         ("whisperkit_server", "processo a parte: server WhisperKit large-v3-turbo (solo se serve la lingua di riserva)"),
                         ("parakeet_onnx_added", "percorso portabile: Parakeet ONNX su CPU, aggiunto al processo Python"),
                         ("faster_whisper_small_added", "percorso portabile: faster-whisper small (int8), aggiunto al processo Python")):
            if k in mem:
                L.append(f"| {label} | {mem[k]} |")
        L.append("")
    if e2e:
        L += ["## 9. Da capo a fondo (gioco finto, microfono finto, modello di linguaggio finto)", "",
              "`bench/voice_e2e.py`: la colla della mente (tasto, sessione di riconoscimento, transcript, palco, voci) con il riconoscimento e le voci veri e la risposta dell'equipaggio "
              "sostituita da una riga fissa (nessuna chiamata di rete: la parte del modello non c'è, quindi «dal transcript alla prima parola» è la sola parte della mente). "
              "Il Capitano preme il tasto, comincia a parlare un quarto di secondo dopo e lascia il tasto 0,2 s dopo l'ultima parola.", "",
              "| Misura | " + " | ".join(sorted(e2e)) + " |", "|---|" + "---|" * len(e2e)]
        for key, label in (("key_up_to_transcript_ms", "dal rilascio del tasto al transcript nel gioco (ms)"),
                           ("key_up_to_first_word_ms", "dal rilascio alla prima parola della risposta, senza il modello (ms)"),
                           ("transcript_to_the_crew_turn_ms", "dal transcript al turno dell'equipaggio (ms)"),
                           ("the_crew_line_queued_to_first_word_ms", "dalla riga in coda alla prima parola (ms)"),
                           ("key_down_to_cancel_ms", "dal tasto premuto al `cancel` di chi parlava (ms)"),
                           ("cancel_fade_ms", "dissolvenza chiesta al gioco (ms)"),
                           ("over_key_up_to_first_word_ms", "dopo aver interrotto un ufficiale: dal rilascio alla prima parola (ms)"),
                           ("typed_to_first_word_ms", "ordine scritto su un ponte silenzioso: dall'invio alla prima parola (ms)"),
                           ("typed_over_an_answer_second_begins_after_first_ends_ms", "secondo ordine scritto mentre la prima risposta suona: la seconda comincia dopo la fine della prima (ms)"),
                           ("load_avg", "carico medio della macchina")):
            L.append(f"| {label} | " + " | ".join(str(e2e[k].get(key, "—")) for k in sorted(e2e)) + " |")
        L.append("| ritardo del ciclo degli eventi mentre la mente ascolta, pensa e parla: mediana / p99 / massimo (ms), tick oltre 50 ms | " +
                 " | ".join((f"{e2e[k]['loop_lag_ms']['p50']} / {e2e[k]['loop_lag_ms']['p99']} / {e2e[k]['loop_lag_ms']['max']}, {e2e[k]['loop_lag_ms']['over_50_ms']} su {e2e[k]['loop_lag_ms']['ticks']}"
                            if e2e[k].get("loop_lag_ms") else "—") for k in sorted(e2e)) + " |")
        L.append("")
        for k in sorted(e2e):
            if e2e[k].get("problems"):
                L.append(f"**{k}: problemi** — " + "; ".join(e2e[k]["problems"]))
        L.append("")
    L += decisions_lines(stt, live, tts, floor, mem, other)
    L += ["## Limiti di queste misure", "",
          "- **Il parlato è sintetico** (Pocket TTS con l'accento del suo modello e voci di sistema macOS), non persone: il WER comprende anche gli errori della sintesi (l'italiano di Pocket è la "
          "lingua meno intelligibile) e i nomi del gioco vengono pronunciati all'inglese o alla lingua della frase. Con una persona vera i numeri saranno diversi, in un senso o nell'altro; "
          "i confronti tra motori, condizioni e lingue restano validi.",
          "- **Gli alias del glossario sono stati ricavati da queste stesse trascrizioni**: la percentuale di nomi trovati è misurata sul campione da cui sono nati (le regole generali, cioè il "
          "nome dell'ufficiale a inizio frase, la vocale iniziale persa, i nomi a pezzi, no).",
          "- **La macchina era occupata** (editor di Unreal e altri agenti): i tempi sono quelli di un Mac già carico; il carico medio è accanto a ogni misura.",
          "- **Microfono finto**: la cattura e il pre-roll sono provati contro un dispositivo finto che consegna blocchi da 20 ms in tempo reale; il microfono vero, le cuffie Bluetooth e il "
          "permesso di sistema non si sono potuti provare qui.",
          "- **I rifacimenti del test dal vivo (`r1`…`r4`) usano un modello di linguaggio e voci finti**: provano l'ordine e i tempi che decide la mente (priorità, tagli, notizie vecchie, "
          "riprese), non la qualità di ciò che l'equipaggio scrive; il test dal vivo vero, con il gioco e le voci vere, resta da rifare dopo l'unione.",
          "- **Il gioco non c'è**: la colla della mente è provata con un gioco finto; come il gioco riproduce l'audio (coda procedurale, attenuazione, musica) è nella diagnosi di "
          "`docs/protocollo_voce.md` e va verificato col gioco vero dopo le correzioni C++.", ""]
    out.write_text("\n".join(italian_numbers("\n".join(L).split("\n"))) + "\n", encoding="utf-8")
    print("REPORT", out)


# ------------------------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(prog="bench.voice_pipeline")
    ap.add_argument("sections", nargs="+", metavar="section", choices=["stt", "live", "lang", "other", "tts", "mic", "floor", "mem", "report"],
                    help="one or more of stt live lang other tts mic floor mem report, run in this order")
    ap.add_argument("--langs", default="it,en,es,fr,de,pt,nl")
    ap.add_argument("--backends", default="parakeet-ultra")
    ap.add_argument("--load", default="", help="synthetic game next to the benchmark: gpu, cpu:4, gpu,cpu:4")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--slow-every", type=int, default=0, help="stt: the Whisper engines decode one clip in N (default 3, 2 with --quick)")
    ap.add_argument("--per-lang", type=int, default=0, help="stt: only the first N orders of every language (default all 12, 6 with --quick)")
    args = ap.parse_args()
    logging_level = os.environ.get("BENCH_LOG", "WARNING")
    import logging
    logging.basicConfig(level=getattr(logging, logging_level), format="%(name)s %(message)s")
    runners = {"stt": sec_stt, "live": sec_live, "lang": sec_lang, "other": sec_other, "tts": sec_tts, "mic": sec_mic, "floor": sec_floor, "mem": sec_mem}
    for section in args.sections:
        if section == "report":
            report(args)
        else:
            asyncio.run(runners[section](args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
