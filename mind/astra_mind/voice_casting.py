"""Automatic voice casting: every Pocket TTS catalogue voice reads bridge lines in several languages; WhisperKit
re-transcribes them (word error rate = intelligibility) and a pitch estimate tells voices apart.
Run: uv run python -m astra_mind.voice_casting [--langs it,en] -> docs/bench/voci_casting_<date>.md"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import re
import time

import numpy as np

from .env import REPO_ROOT
from .stt import WhisperKit
from .tts import TTSEngine

GENDER = {"alba": "f", "anna": "f", "azelma": "f", "bill_boerst": "m", "caro_davy": "f", "charles": "m", "cosette": "f",
          "eponine": "f", "estelle": "f", "eve": "f", "fantine": "f", "george": "m", "giovanni": "m", "jane": "f",
          "javert": "m", "jean": "m", "juergen": "m", "lola": "f", "marius": "m", "mary": "f", "michael": "m", "paul": "m",
          "peter_yearsley": "m", "rafael": "m", "stuart_bell": "m", "vera": "f", "daan": "m"}
VOICES = ["alba", "anna", "azelma", "bill_boerst", "caro_davy", "charles", "cosette", "eponine", "estelle", "eve",
          "fantine", "george", "giovanni", "jane", "javert", "jean", "juergen", "lola", "marius", "mary", "michael",
          "paul", "peter_yearsley", "rafael", "stuart_bell", "vera", "daan"]
LINES = {
    "it": ["Rotta zero quattro cinque, punto dieci, mezza forza, capitano.",
           "Allarme rosso, scudi a prua, armi pronte.",
           "Contatto sconosciuto a cinquanta chilometri, deriva a freddo, nessuna risposta."],
    "en": ["Coming to zero four five, mark ten, half ahead, Captain.",
           "Red alert, shields forward, weapons hot.",
           "Unknown contact at fifty kilometres, drifting cold, no transponder."],
}


NUMBER_WORDS = set("""zero uno due tre quattro cinque sei sette otto nove dieci venti trenta quaranta cinquanta
one two three four five six seven eight nine ten twenty thirty forty fifty hundred cento""".split())
SPELLING = {"kilometers": "kilometres", "kilometer": "kilometre", "capitan": "capitano"}


def words(s: str) -> list[str]:
    """Lower-case words without numbers (digits vs spelled-out numbers are not intelligibility errors)."""
    out = []
    for w in re.findall(r"[a-zà-ÿ0-9]+", s.lower()):
        w = SPELLING.get(w, w)
        if w.isdigit() or w in NUMBER_WORDS:
            continue
        out.append(w)
    return out


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = range(len(r) + 1)
    d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r), len(h)] / max(1, len(r))


def pitch_hz(pcm: np.ndarray, rate: int) -> float:
    """Median F0 over voiced frames (autocorrelation), rough but enough to tell voices apart."""
    x = pcm.astype(np.float32) / 32768.0
    frame, hop = int(0.04 * rate), int(0.02 * rate)
    f0s = []
    for i in range(0, len(x) - frame, hop):
        f = x[i:i + frame] - x[i:i + frame].mean()
        if np.sqrt((f ** 2).mean()) < 0.02:
            continue
        ac = np.correlate(f, f, "full")[frame - 1:]
        lo, hi = int(rate / 350), int(rate / 70)
        k = lo + int(np.argmax(ac[lo:hi]))
        if ac[k] > 0.3 * ac[0]:
            f0s.append(rate / k)
    return float(np.median(f0s)) if f0s else 0.0


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="it,en")
    args = ap.parse_args()
    langs = args.langs.split(",")
    tts, stt = TTSEngine(), WhisperKit()
    await stt.start()
    rows = []
    for v in VOICES:
        res = {"voice": v}
        pitches = []
        for lang in langs:
            errs, rt = [], []
            for line in LINES[lang]:
                t0 = time.perf_counter()
                chunks = [c async for c in tts.stream(line, v, lang)]
                pcm = np.frombuffer(b"".join(chunks), dtype="<i2")
                rt.append((len(pcm) / tts.sample_rate) / max(1e-3, time.perf_counter() - t0))
                idx = (np.arange(int(len(pcm) * 16000 / tts.sample_rate)) * tts.sample_rate / 16000).astype(int)
                heard, _ = await stt.transcribe(pcm[idx].astype("<i2").tobytes(), language=lang, glossary=False)
                errs.append(wer(line, heard))
                pitches.append(pitch_hz(pcm, tts.sample_rate))
            res[f"wer_{lang}"] = float(np.mean(errs))
        res["pitch"] = float(np.median([p for p in pitches if p > 0] or [0]))
        rows.append(res)
        print(v, {k: (round(x, 3) if isinstance(x, float) else x) for k, x in res.items()}, flush=True)
    await stt.close()
    rows.sort(key=lambda r: np.mean([r[f"wer_{l}"] for l in langs]))
    date = dt.date.today().isoformat()
    out = REPO_ROOT / "docs" / "bench" / f"voci_casting_{date}.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(f"# Casting automatico delle voci (Pocket TTS) — {date}\n\n")
        fh.write("Ogni voce legge 3 battute di plancia per lingua; WhisperKit le ritrascrive (senza glossario).\n")
        fh.write("WER = parole sbagliate / parole, numeri esclusi (più basso = più intelligibile).\n\n")
        fh.write("| Voce | Genere | " + " | ".join(f"WER {l}" for l in langs) + " |\n|---|---|" + "---|" * len(langs) + "\n")
        for r in rows:
            fh.write(f"| {r['voice']} | {GENDER.get(r['voice'], '?')} | " + " | ".join(f"{r[f'wer_{l}']:.2f}" for l in langs) + " |\n")
    print("REPORT", out)


if __name__ == "__main__":
    asyncio.run(main())
