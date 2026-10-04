"""Automatic voice casting: every Pocket TTS catalogue voice reads bridge lines in every language the game speaks, through the
production chain (pauses, speed, loudness, limiter); the speech recogniser writes down what it hears (word error rate =
intelligibility), and a pitch estimate tells the voices apart.

It produces three things:
  - docs/bench/voci_casting_<date>.md   the table (WER per language, loudness, pace, pitch) and the officers' voices checked
  - astra_mind/voice_gains.json         the gain that brings each voice in each language to the target loudness (shipped)
  - astra_mind/voice_overrides.json     where an officer's voice is hard to understand in a language, the voice that speaks
                                        for them there (same gender, nearest pitch, clearly clearer, and a voice that speaks
                                        for one officer only: ten officers must not end up with three voices)

Run:  uv run python -m astra_mind.voice_casting [--langs it,en,es,fr,de,pt,nl] [--voices alba,eve] [--no-write]
      uv run python -m astra_mind.voice_casting --recompute [docs/bench/voci_casting_<date>.md]
          the overrides again from the measurements of an earlier run (rules changed, nothing to synthesise)"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import re
from pathlib import Path

import numpy as np

from .env import REPO_ROOT
from .stt import Recognizer
from .voice_stt_backends import ParakeetBackend
from .tts import CALIBRATION, GENDER, TTSEngine, VOICES
from .voice_audio import f32_to_pcm16, resample

LANGS = ["it", "en", "es", "fr", "de", "pt", "nl"]
# the calibration lines plus one line full of the game's names: intelligibility of what the Captain must understand
EXTRA = {
    "en": "Praetorian and Vigilant hold the line, Acheron is turning to port.",
    "it": "La Praetorian e la Vigilant tengono la linea, l'Acheron sta virando a sinistra.",
    "es": "El Praetorian y el Vigilant mantienen la línea, el Acheron gira a babor.",
    "fr": "Le Praetorian et le Vigilant tiennent la ligne, l'Acheron vire à bâbord.",
    "de": "Praetorian und Vigilant halten die Linie, die Acheron dreht nach Backbord.",
    "pt": "O Praetorian e o Vigilant seguram a linha, o Acheron vira a bombordo.",
    "nl": "Praetorian en Vigilant houden de linie, de Acheron draait naar bakboord.",
}
GAINS_FILE = Path(__file__).with_name("voice_gains.json")
OVERRIDES_FILE = Path(__file__).with_name("voice_overrides.json")

NUMBER_WORDS = set("""zero uno due tre quattro cinque sei sette otto nove dieci venti trenta quaranta cinquanta cento null eins zwei drei
vier fünf funf sechs sieben acht neun zehn zwanzig dreißig dreissig vierzig fünfzig funfzig cero uno dos tres cuatro cinco seis siete
ocho nueve diez veinte treinta cuarenta cincuenta zéro zero un deux trois quatre cinq six sept huit neuf dix vingt trente quarante
cinquante dois três quatro cinco seis sete oito nove dez vinte trinta quarenta cinquenta nul een twee drie vier vijf zes zeven acht
negen tien twintig dertig veertig vijftig one two three four five six seven eight nine ten twenty thirty forty fifty hundred""".split())
SPELLING = {"kilometers": "kilometres", "kilometer": "kilometre", "capitan": "capitano", "captain": "captain", "capitain": "capitaine",
            "kapitan": "kapitän", "quilómetros": "kilómetros", "quilômetros": "quilómetros"}


def words(s: str) -> list[str]:
    """Lower-case words without numbers (digits vs spelled-out numbers are not intelligibility errors)."""
    out = []
    for w in re.findall(r"[a-zà-ÿß0-9]+", s.lower()):
        w = SPELLING.get(w, w)
        if w.isdigit() or w in NUMBER_WORDS:
            continue
        out.append(w)
    return out


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    if not r:
        return 0.0
    d = np.zeros((len(r) + 1, len(h) + 1), dtype=int)
    d[:, 0] = range(len(r) + 1)
    d[0, :] = range(len(h) + 1)
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i, j] = min(d[i - 1, j] + 1, d[i, j - 1] + 1, d[i - 1, j - 1] + (r[i - 1] != h[j - 1]))
    return float(d[len(r), len(h)] / len(r))


def pitch_hz(x: np.ndarray, rate: int) -> float:
    """Median F0 over voiced frames (autocorrelation), rough but enough to tell voices apart."""
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


def lines_for(lang: str) -> list[str]:
    return list(CALIBRATION[lang]) + [EXTRA[lang]]


async def cast(langs: list[str], voices: list[str], stt: Recognizer, tts: TTSEngine) -> list[dict]:
    rows: list[dict] = []
    loop = asyncio.get_running_loop()
    for lang in langs:
        for v in voices:
            errs, pitches, dur, nwords, t_first = [], [], 0.0, 0, []
            meas = await loop.run_in_executor(None, tts.measure, lang, v)            # loudness before the gain (for the table of gains)
            gain = tts._gain_for(meas["lufs"], meas["peak"])
            tts._user[f"{lang}/{v}"] = meas                                          # (the stream below uses this, no second measurement)
            tts._profiles.pop((lang, v), None)
            for line in lines_for(lang):
                st = tts.stream(line, v, lang, speed=tts.speed)
                pcm = b"".join([c async for c in st])
                t_first.append(st.t_first or 0.0)
                x = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
                dur += len(x) / tts.sample_rate
                nwords += len(line.split())
                heard, _ = await stt.transcribe(f32_to_pcm16(resample(x, tts.sample_rate, 16000)), language=lang, glossary=False)
                errs.append(wer(line, heard))
                pitches.append(pitch_hz(x, tts.sample_rate))
            rows.append({"lang": lang, "voice": v, "wer": float(np.mean(errs)), "lufs": meas["lufs"], "peak": meas["peak"],
                         "gain": round(gain, 2), "wps": nwords / dur if dur else 0.0,
                         "pitch": float(np.median([p for p in pitches if p > 0] or [0])), "first_ms": float(np.median(t_first)) * 1000})
            print(lang, v, {k: (round(x, 3) if isinstance(x, float) else x) for k, x in rows[-1].items() if k not in ("lang", "voice")}, flush=True)
    return rows


def propose_overrides(rows: list[dict], crew_voices: dict[str, str], limit: float = 0.30, margin: float = 0.10) -> dict[str, str]:
    """For every officer voice that is hard to understand in a language (error rate over `limit`): a free voice of the same
    gender that is clearly clearer (`margin` lower) and has the nearest pitch. A voice never speaks for two officers, and
    never replaces one that another officer keeps: the bridge must not end up with three officers on one voice. The worst
    voice is served first; where no free voice is clearly better the officer keeps his own (a slightly harder voice that is
    his beats an easier one that is somebody else's)."""
    out: dict[str, str] = {}
    for lang in sorted({r["lang"] for r in rows}):
        rl = {r["voice"]: r for r in rows if r["lang"] == lang}
        taken = set(crew_voices.values())
        for officer, v in sorted(crew_voices.items(), key=lambda kv: -(rl[kv[1]]["wer"] if kv[1] in rl else 0.0)):
            if v not in rl or rl[v]["wer"] <= limit:
                continue
            free = [r for r in rl.values() if GENDER.get(r["voice"]) == GENDER.get(v) and r["voice"] not in taken
                    and r["wer"] <= rl[v]["wer"] - margin and r["wer"] <= limit]
            if not free:
                continue
            best = min(free, key=lambda r: (abs(r["pitch"] - rl[v]["pitch"]) / 40.0) + r["wer"])
            out[f"{lang}/{v}"] = best["voice"]
            taken.add(best["voice"])
    return out


def rows_from_report(path: Path) -> list[dict]:
    """The measurements of an earlier run, read back from its report (the per-language tables)."""
    rows: list[dict] = []
    lang: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"## ([a-z]{2})\s*$", line)
        if m:
            lang = m.group(1)
            continue
        if line.startswith("## "):
            lang = None
        if lang and line.startswith("| ") and not line.startswith(("| Voce", "|---")):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(c) == 9:
                rows.append({"lang": lang, "voice": c[0], "wer": float(c[2]), "lufs": float(c[3]), "peak": float(c[4]), "gain": float(c[5]),
                             "wps": float(c[6]), "pitch": float(c[7]), "first_ms": float(c[8])})
    return rows


def write_report(rows: list[dict], langs: list[str], crew: dict[str, str], overrides: dict[str, str], path: Path) -> None:
    date = dt.date.today().isoformat()
    by = {(r["lang"], r["voice"]): r for r in rows}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f"# Casting automatico delle voci (Pocket TTS) — {date}\n\n")
        fh.write("Ogni voce del catalogo legge in ogni lingua tre battute di plancia e una piena di nomi di navi, attraverso la catena di produzione "
                 "(pause accorciate, velocità x1,12, volume uniformato, limitatore); il riconoscitore (Parakeet, senza glossario) le ritrascrive.\n"
                 "WER = parole sbagliate / parole, numeri esclusi (più basso = più intelligibile). LUFS e picco sono della voce *prima* del guadagno; "
                 "«guad.» è il guadagno che la porta a -19 LUFS (con un limitatore che non comprime oltre 6 dB); «p/s» parole al secondo di voce.\n\n")
        for lang in langs:
            fh.write(f"## {lang}\n\n| Voce | Genere | WER | LUFS | picco dB | guad. dB | p/s | tono Hz | primo suono ms |\n|---|---|---|---|---|---|---|---|---|\n")
            for r in sorted((r for r in rows if r["lang"] == lang), key=lambda r: r["wer"]):
                fh.write(f"| {r['voice']} | {GENDER.get(r['voice'], '?')} | {r['wer']:.2f} | {r['lufs']:.1f} | {r['peak']:.1f} | {r['gain']:+.1f} | "
                         f"{r['wps']:.2f} | {r['pitch']:.0f} | {r['first_ms']:.0f} |\n")
            fh.write("\n")
        fh.write("## Le voci degli ufficiali, lingua per lingua\n\n| Ufficiale | Voce | " + " | ".join(f"WER {l}" for l in langs) + " |\n|---|---|" + "---|" * len(langs) + "\n")
        for officer, v in crew.items():
            fh.write(f"| {officer} | {v} | " + " | ".join(f"{by[(l, v)]['wer']:.2f}" if (l, v) in by else "—" for l in langs) + " |\n")
        fh.write("\n")
        if overrides:
            fh.write("### Sostituzioni (WER oltre 0,30 nella lingua e una voce libera dello stesso genere con almeno 0,10 in meno; ogni sostituta parla per un solo ufficiale)\n\n"
                     "| Lingua/voce | parla al suo posto | WER prima → dopo |\n|---|---|---|\n")
            for k, v in sorted(overrides.items()):
                lg, orig = k.split("/", 1)
                a, b = by.get((lg, orig)), by.get((lg, v))
                fh.write(f"| {k} | {v} | {a['wer']:.2f} → {b['wer']:.2f} |\n" if a and b else f"| {k} | {v} | |\n")
            kept = [(o, v, lg, by[(lg, v)]["wer"]) for lg in langs for o, v in crew.items()
                    if (lg, v) in by and by[(lg, v)]["wer"] > 0.30 and f"{lg}/{v}" not in overrides]
            if kept:
                fh.write("\nVoci degli ufficiali che restano sopra 0,30 (nessuna voce libera è chiaramente migliore): " +
                         ", ".join(f"{lg}/{v} ({o}) {w:.2f}" for o, v, lg, w in kept) + ".\n")
        else:
            fh.write("Nessuna voce degli ufficiali supera WER 0,30 in nessuna lingua: nessuna sostituzione.\n")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default=",".join(LANGS))
    ap.add_argument("--voices", default=",".join(VOICES))
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--recompute", nargs="?", const="", metavar="REPORT",
                    help="only the overrides and the report again, from the measurements of an earlier run (default: the newest report)")
    args = ap.parse_args()
    if args.recompute is not None:
        from .crew import CREW
        src = Path(args.recompute) if args.recompute else max((REPO_ROOT / "docs" / "bench").glob("voci_casting_*.md"))
        rows = rows_from_report(src)
        langs = list(dict.fromkeys(r["lang"] for r in rows))
        crew = {o.id: o.voice for o in CREW.values()}
        overrides = propose_overrides(rows, crew)
        if not args.no_write:
            OVERRIDES_FILE.write_text(json.dumps(overrides, indent=1, sort_keys=True), encoding="utf-8")
            write_report(rows, langs, crew, overrides, src)
            print("REPORT", src)
        print("OVERRIDES", json.dumps(overrides, indent=1))
        return
    langs, voices = args.langs.split(","), args.voices.split(",")
    tts, stt = TTSEngine(), Recognizer(backends=[ParakeetBackend()])         # one engine only: no second opinion in the measurement
    await stt.start()
    if not await stt.ready():
        raise SystemExit("no speech recogniser available")
    rows = await cast(langs, voices, stt, tts)
    await stt.close()
    from .crew import CREW
    crew = {o.id: o.voice for o in CREW.values()}
    overrides = propose_overrides(rows, crew)
    date = dt.date.today().isoformat()
    if not args.no_write:
        gains = json.loads(GAINS_FILE.read_text(encoding="utf-8")) if GAINS_FILE.exists() else {}
        for r in rows:
            gains[f"{r['lang']}/{r['voice']}"] = {"lufs": r["lufs"], "peak": r["peak"]}
        GAINS_FILE.write_text(json.dumps(gains, indent=1, sort_keys=True), encoding="utf-8")
        OVERRIDES_FILE.write_text(json.dumps(overrides, indent=1, sort_keys=True), encoding="utf-8")
        out = REPO_ROOT / "docs" / "bench" / f"voci_casting_{date}.md"
        write_report(rows, langs, crew, overrides, out)
        print("REPORT", out)
    print("OVERRIDES", json.dumps(overrides))


if __name__ == "__main__":
    asyncio.run(main())
