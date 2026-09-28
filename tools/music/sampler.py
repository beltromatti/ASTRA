"""A small orchestral sampler for ASTRA's score: renders note events with the VSCO 2 Community Edition samples (CC0,
github.com/sgossner/VSCO-2-CE, sparse-cloned into art/_cache/vsco2) into a mixed, reverberated, mastered stereo WAV.

Sample names use the "C3 = middle C" convention (a file named A3 sounds at 440 Hz): MIDI = 12 * (octave + 2) + pc.
Velocity layers: v1 is the softest. Sustains last 9-15 s; longer notes are extended by crossfaded re-bows.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

SR = 48000
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIB = os.path.join(ROOT, "art", "_cache", "vsco2")
PC = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}

# name -> (folder, kind, pan -1..1, bus, gain dB)   kind: "sus" (held, extendable) | "short" (natural decay)
INSTRUMENTS = {
    "vln_sus": ("Strings/Violin Section/susVib", "sus", -0.45, "strings", 0.0),
    "vln_trem": ("Strings/Violin Section/Trem", "sus", -0.45, "strings", -1.0),
    "vln_spic": ("Strings/Violin Section/Spic", "short", -0.45, "strings", 0.0),
    "vla_sus": ("Strings/Viola Section/susvib", "sus", -0.12, "strings", 0.0),
    "vla_trem": ("Strings/Viola Section/trem", "sus", -0.12, "strings", -1.0),
    "vla_spic": ("Strings/Viola Section/spic", "short", -0.12, "strings", 0.0),
    "vc_sus": ("Strings/Cello Section/susvib", "sus", 0.25, "strings", 0.0),
    "vc_trem": ("Strings/Cello Section/trem", "sus", 0.25, "strings", -1.0),
    "vc_spic": ("Strings/Cello Section/spic", "short", 0.25, "strings", 0.0),
    "cb_sus": ("Strings/Solo Contrabass/SusVib", "sus", 0.45, "strings", 3.0),
    "cb_trem": ("Strings/Solo Contrabass/Trem", "sus", 0.45, "strings", 3.0),
    "cb_spic": ("Strings/Solo Contrabass/Spic", "short", 0.45, "strings", 3.0),
    "hn_sus": ("Brass/F Horn/sus", "sus", -0.25, "brass", -3.0),
    "hn_stac": ("Brass/F Horn/stac", "short", -0.25, "brass", 0.0),
    "tbn_sus": ("Brass/Tenor Trombone/sus", "sus", 0.3, "brass", -1.0),
    "tbn_stac": ("Brass/Tenor Trombone/stac", "short", 0.3, "brass", -1.0),
    "tuba_sus": ("Brass/Tuba/sus", "sus", 0.35, "brass", 0.0),
    "tpt_sus": ("Brass/Trumpet/sus", "sus", 0.1, "brass", -3.0),
    "tpt_stac": ("Brass/Trumpet/stac", "short", 0.1, "brass", -3.0),
    "fl_sus": ("Woodwinds/Flute/susvib", "sus", -0.3, "winds", -2.0),
    "cl_sus": ("Woodwinds/Clarinet/susLong", "sus", -0.2, "winds", -2.0),
    "harp": ("Strings/Harp", "short", -0.55, "winds", -2.0),
}
BUS_WET = {"strings": 0.42, "brass": 0.38, "winds": 0.45, "perc": 0.3}


@dataclass
class Note:
    instr: str
    midi: int
    start: float          # s
    dur: float            # s
    vel: float = 0.6      # 0..1
    attack: float = 0.0   # extra fade-in (s): 0 = the sample's own attack
    release: float = 0.6  # fade-out after dur (s)


@dataclass
class Hit:
    """A percussion sample at a time (no pitch mapping): path relative to LIB, gain dB, pan, optional pitch shift."""
    path: str
    start: float
    gain_db: float = 0.0
    pan: float = 0.0
    semis: float = 0.0


@dataclass
class Score:
    length: float                       # loop length (s)
    notes: list[Note] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    tail: float = 6.0                   # rendered past the end, folded onto the start (seamless loop)
    loop: bool = True

    def n(self, instr: str, midi: int, start: float, dur: float, vel: float = 0.6, attack: float = 0.0, release: float = 0.6):
        self.notes.append(Note(instr, midi, start, dur, vel, attack, release))

    def hit(self, path: str, start: float, gain_db: float = 0.0, pan: float = 0.0, semis: float = 0.0):
        self.hits.append(Hit(path, start, gain_db, pan, semis))


# ------------------------------------------------------------------------------------------------ samples
@functools.lru_cache(maxsize=None)
def sample_map(instr: str) -> list[tuple[int, int, str]]:
    """(midi, velocity layer, path) for every file of an instrument."""
    folder = os.path.join(LIB, INSTRUMENTS[instr][0])
    out = []
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(".wav"):
            continue
        m = re.search(r"_([A-G]#?)(-?\d)_", f)
        v = re.search(r"_v(\d)", f)
        if not m:
            continue
        midi = 12 * (int(m.group(2)) + 2) + PC[m.group(1)]
        out.append((midi, int(v.group(1)) if v else 1, os.path.join(folder, f)))
    if not out:
        raise FileNotFoundError(folder)
    return out


@functools.lru_cache(maxsize=512)
def load(path: str) -> np.ndarray:
    """Stereo float32 at SR."""
    x, sr = sf.read(path, dtype="float32", always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    x = x[:, :2]
    if sr != SR:
        fr = Fraction(SR, sr).limit_denominator(1000)
        x = resample_poly(x, fr.numerator, fr.denominator, axis=0).astype(np.float32)
    # trim leading silence (keep 5 ms before the onset)
    env = np.abs(x).max(axis=1)
    thr = env.max() * 0.02
    on = int(np.argmax(env > thr))
    return x[max(0, on - int(0.005 * SR)):]


@functools.lru_cache(maxsize=2048)
def shifted(path: str, semis: float) -> np.ndarray:
    x = load(path)
    if abs(semis) < 1e-3:
        return x
    ratio = 2 ** (semis / 12.0)
    fr = Fraction(1 / ratio).limit_denominator(400)
    return resample_poly(x, fr.numerator, fr.denominator, axis=0).astype(np.float32)


def pick(instr: str, midi: int, vel: float, rr: int) -> tuple[str, float]:
    """The closest sample (pitch first, then velocity layer), round-robin among equals. Returns (path, semitone shift)."""
    smap = sample_map(instr)
    layers = sorted({v for _, v, _ in smap})
    want_layer = layers[min(len(layers) - 1, int(vel * len(layers)))]
    best = min(abs(m - midi) for m, _, _ in smap)
    near = [(m, v, p) for m, v, p in smap if abs(m - midi) == best]
    lay = min({v for _, v, _ in near}, key=lambda v: abs(v - want_layer))
    cands = [(m, p) for m, v, p in near if v == lay]
    m, p = cands[rr % len(cands)]
    return p, float(midi - m)


def render_note(n: Note, rr: int) -> np.ndarray:
    folder, kind, _, _, _ = INSTRUMENTS[n.instr]
    path, semis = pick(n.instr, n.midi, n.vel, rr)
    x = shifted(path, semis)
    need = int((n.dur + n.release) * SR)
    if kind == "sus" and need > len(x) - int(0.2 * SR):
        # re-bow: extend a held note with crossfaded copies of its sustained middle
        body = x[int(1.5 * SR):]
        xf = int(1.0 * SR)
        out = x.copy()
        while len(out) < need + xf:
            fade = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
            seg = body.copy()
            out[-xf:] = out[-xf:] * (1 - fade) + seg[:xf] * fade
            out = np.concatenate([out, seg[xf:]])
        x = out
    y = x[:need].copy() if kind == "sus" else x[:max(need, int(min(len(x), 2.5 * SR)))].copy()
    if n.attack > 0:
        a = min(len(y), int(n.attack * SR))
        y[:a] *= (np.linspace(0, 1, a, dtype=np.float32) ** 1.5)[:, None]
    if kind == "sus":
        r = min(len(y), int(n.release * SR))
        y[-r:] *= (np.linspace(1, 0, r, dtype=np.float32) ** 2)[:, None]
    # level: the layer gives the timbre; fine dynamics inside it
    g = 10 ** (INSTRUMENTS[n.instr][4] / 20) * (0.35 + 0.65 * n.vel)
    return y * g


# ------------------------------------------------------------------------------------------------- mixing
def pan_gains(p: float) -> tuple[float, float]:
    a = (p + 1) * np.pi / 4
    return float(np.cos(a)), float(np.sin(a))


def hall_ir(rt60: float = 2.6, seed: int = 7) -> np.ndarray:
    """A synthetic concert-hall impulse response (stereo): pre-delay, early reflections, a dark exponential tail."""
    rng = np.random.default_rng(seed)
    n = int(rt60 * 1.2 * SR)
    t = np.arange(n) / SR
    ir = np.zeros((n, 2), np.float32)
    decay = np.exp(-6.91 * t / rt60)
    for c in range(2):
        noise = rng.standard_normal(n).astype(np.float32)
        # air absorption: the tail darkens (two bands with different decays)
        lo = sosfilt(butter(2, 2500, "low", fs=SR, output="sos"), noise)
        hi = noise - lo
        ir[:, c] = (lo * decay + hi * np.exp(-6.91 * t / (rt60 * 0.45))) * 0.25
    pre = int(0.022 * SR)
    ir = np.concatenate([np.zeros((pre, 2), np.float32), ir])
    for d, g in ((0.011, 0.5), (0.019, 0.42), (0.027, 0.35), (0.041, 0.3), (0.055, 0.22), (0.071, 0.18)):
        k = pre + int(d * SR)
        ir[k, 0] += g * rng.uniform(0.7, 1.0)
        ir[k + int(0.0013 * SR), 1] += g * rng.uniform(0.7, 1.0)
    fade = np.linspace(0, 1, int(0.004 * SR))
    ir[pre:pre + len(fade)] *= fade[:, None]
    return ir / np.abs(ir).sum(axis=0).max() * 6.0


def render(score: Score, out_path: str, loudness_db: float = -20.0) -> None:
    total = score.length + score.tail
    n_total = int(total * SR) + SR
    buses = {b: np.zeros((n_total, 2), np.float32) for b in BUS_WET}
    rr_count: dict[tuple[str, int], int] = {}
    for n in score.notes:
        key = (n.instr, n.midi)
        rr = rr_count.get(key, 0)
        rr_count[key] = rr + 1
        y = render_note(n, rr)
        s = int(n.start * SR)
        e = min(n_total, s + len(y))
        l, r = pan_gains(INSTRUMENTS[n.instr][2])
        bus = buses[INSTRUMENTS[n.instr][3]]
        bus[s:e, 0] += y[:e - s, 0] * l * 1.41
        bus[s:e, 1] += y[:e - s, 1] * r * 1.41
    for h in score.hits:
        x = shifted(os.path.join(LIB, h.path), h.semis) * (10 ** (h.gain_db / 20))
        s = int(h.start * SR)
        e = min(n_total, s + len(x))
        l, r = pan_gains(h.pan)
        buses["perc"][s:e, 0] += x[:e - s, 0] * l * 1.41
        buses["perc"][s:e, 1] += x[:e - s, 1] * r * 1.41
    ir = hall_ir()
    mix = np.zeros((n_total, 2), np.float32)
    for b, y in buses.items():
        if not np.any(y):
            continue
        wet = np.stack([fftconvolve(y[:, c], ir[:, c])[:n_total] for c in range(2)], axis=1)
        mix += y * (1 - BUS_WET[b] * 0.5) + wet * BUS_WET[b]
    # tidy the low end, fold the tail into the start (seamless loop), master
    mix = sosfilt(butter(2, 32, "high", fs=SR, output="sos"), mix, axis=0).astype(np.float32)
    L = int(score.length * SR)
    if score.loop:
        tail = mix[L:L + int(score.tail * SR)]
        out = mix[:L].copy()
        out[:len(tail)] += tail
    else:
        out = mix[:int(total * SR)].copy()
        f = int(1.5 * SR)
        out[-f:] *= (np.linspace(1, 0, f, dtype=np.float32) ** 2)[:, None]
    out = master(out, loudness_db)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    sf.write(out_path, out, SR, subtype="PCM_16")
    print(f"{os.path.basename(out_path)}: {len(out) / SR:.1f} s, {len(score.notes)} notes, {len(score.hits)} hits")


def master(x: np.ndarray, loudness_db: float) -> np.ndarray:
    # gentle RMS compression (2:1 above -24 dB), then a soft limiter; loudness set well under the dialogue
    rms = np.sqrt(np.convolve((x ** 2).mean(axis=1), np.ones(int(0.3 * SR)) / int(0.3 * SR), mode="same") + 1e-12)
    lvl = 20 * np.log10(rms)
    over = np.maximum(0, lvl - (-24))
    gain = 10 ** (-over * 0.5 / 20)
    y = x * gain[:, None]
    cur = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-12)
    y = y * 10 ** ((loudness_db - cur) / 20)
    y = np.tanh(y * 1.2) / 1.2
    peak = np.abs(y).max()
    if peak > 0.89:
        y = y * 0.89 / peak
    return y.astype(np.float32)


# ----------------------------------------------------------------------------------------------- theory
NOTE = {n: i for i, n in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])}
NOTE.update({"Db": 1, "Eb": 3, "Gb": 6, "Ab": 8, "Bb": 10})


def m(name: str) -> int:
    """'D4' -> MIDI in scientific pitch (D4 = 62)."""
    mm = re.fullmatch(r"([A-G][b#]?)(-?\d)", name)
    return 12 * (int(mm.group(2)) + 1) + NOTE[mm.group(1)]
