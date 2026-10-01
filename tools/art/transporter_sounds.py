"""Original sounds of the Transporter Room (TELETRASPORTO, docs/TELETRASPORTO.md §7), synthesised (no third-party audio): the charge-up when a cycle begins, the
dematerialization (a cluster of shimmering tones rising, glitter thickening, a bright chord that dies), the rematerialization (the same turned round, ending in a soft settling),
the chirp of a lock held, the buzz of a fault, and the hum of the pads while a cycle runs (a seamless loop).

Loops are seamless (every periodic part has a whole number of cycles in the loop, the noise is cross-faded at its seam); one-shots end in silence.
Run:    uv run --with numpy --with soundfile --with scipy python tools/art/transporter_sounds.py            -> art/_cache/audio/SW_Xport_*.wav and a one-line report each
Import: tools/ue.py py "exec(open('tools/ue_scripts/import_transporter_audio.py').read())"                  -> /Game/ASTRA/Audio/Transporter/SW_Xport_<Id>
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "audio")
rng = np.random.default_rng(2491)


def t_(sec):
    return np.arange(int(sec * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def norm(x, peak=0.85):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def env(n, attack, release, curve=2.0):
    """An amplitude envelope: a rise of `attack` seconds and a fall of `release` seconds (both curved), flat between."""
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a > 0:
        e[:a] = np.linspace(0, 1, a) ** curve
    if r > 0:
        e[-r:] = np.minimum(e[-r:], np.linspace(1, 0, r) ** curve)
    return e


def sweep(f0, f1, dur, power=1.0):
    """Phase of a tone gliding from f0 to f1 Hz in dur seconds (power > 1 stays low longer, then rises quickly)."""
    t = t_(dur)
    x = (t / dur) ** power
    f = f0 + (f1 - f0) * x
    return 2 * np.pi * np.cumsum(f) / SR


def glitter(dur, density0, density1, lo=2800.0, hi=9000.0, level=0.5, seed=1):
    """Short bright pings: sine blips with a fast decay, thickening (or thinning) over the sound; their pitch scatters between lo and hi."""
    r = np.random.default_rng(seed)
    n = int(dur * SR)
    out = np.zeros(n)
    t = t_(dur)
    dens = np.interp(t, [0, dur], [density0, density1])           # blips a second
    p = np.clip(dens / SR, 0, 1)
    hits = np.nonzero(r.uniform(0, 1, n) < p)[0]
    for i in hits:
        m = int(r.uniform(0.004, 0.03) * SR)
        if i + m >= n:
            continue
        tt = np.arange(m) / SR
        f = np.exp(r.uniform(np.log(lo), np.log(hi)))
        out[i:i + m] += np.sin(2 * np.pi * f * tt) * np.exp(-tt * r.uniform(120, 420)) * r.uniform(0.3, 1.0)
    return out * level


def shimmer_cluster(dur, f0, f1, partials=9, spread=0.012, trem=(9.0, 19.0), power=1.0, seed=2):
    """The signature: a cluster of slightly detuned tones that glide together from f0 to f1, each trembling at its own rate (the lattice 'sparkles')."""
    r = np.random.default_rng(seed)
    t = t_(dur)
    out = np.zeros(len(t))
    for k in range(partials):
        det = 1.0 + r.uniform(-spread, spread) * (k + 1)
        mult = [1.0, 1.0, 2.0, 1.5, 3.0, 2.0, 1.0, 4.0, 2.5][k % 9]
        ph = sweep(f0 * det * mult, f1 * det * mult, dur, power)
        tr = 0.55 + 0.45 * np.sin(2 * np.pi * r.uniform(*trem) * t + r.uniform(0, 6.28))
        out += np.sin(ph + r.uniform(0, 6.28)) * tr / (1.0 + 0.35 * k)
    return out


def energize():
    """A cycle begins: a charge-up, rising and brightening, over about a second."""
    dur = 1.05
    t = t_(dur)
    sw = np.sin(sweep(160, 1500, dur, 2.2)) + 0.5 * np.sin(sweep(320, 3000, dur, 2.2)) + 0.25 * np.sin(sweep(480, 4500, dur, 2.4))
    noise = bp(rng.normal(0, 1, len(t)), 1500, 7000) * (t / dur) ** 2 * 0.35
    thump = np.sin(2 * np.pi * 62 * t) * np.exp(-t * 7.0) * 0.55
    x = (sw * (0.2 + 0.8 * (t / dur) ** 1.4) + noise) * env(len(t), 0.03, 0.12) + thump
    return norm(x, 0.8)


def demat():
    """Dematerialization, a few seconds: the cluster of tones climbs, the glitter thickens, a low whoosh builds, and the last second is a bright chord that dies away."""
    dur = 3.8
    t = t_(dur)
    body = shimmer_cluster(dur, 420, 1700, partials=9, power=1.35, seed=3)
    air = bp(rng.normal(0, 1, len(t)), 700, 4200) * (0.2 + 0.8 * (t / dur) ** 1.6) * 0.30
    low = np.sin(2 * np.pi * 74 * t + 1.7 * np.sin(2 * np.pi * 0.7 * t)) * (0.25 + 0.5 * np.sin(np.pi * t / dur)) * 0.45
    gl = glitter(dur, 8, 150, seed=5, level=0.55)
    # the chord that rings out at the end: three tones a fifth and an octave apart
    chord = np.zeros(len(t))
    tail = t > dur - 1.1
    tt = np.where(tail, t - (dur - 1.1), 0)
    for f, a in ((1320.0, 1.0), (1980.0, 0.7), (2640.0, 0.5)):
        chord += a * np.sin(2 * np.pi * f * t) * np.exp(-tt * 3.4) * tail
    x = (body * 0.55 + air + low + gl) * env(len(t), 0.18, 0.5, 1.6) + chord * 0.32
    return norm(lp(x, 11000, 2), 0.85)


def remat():
    """Rematerialization, the same turned round: the tones fall into place, the glitter thins out, the first second is a bright chord that gathers, and the end is a soft settling."""
    dur = 3.8
    t = t_(dur)
    body = shimmer_cluster(dur, 1700, 420, partials=9, power=0.75, seed=4)
    air = bp(rng.normal(0, 1, len(t)), 700, 4200) * (1.0 - 0.8 * (t / dur) ** 0.8) * 0.30
    low = np.sin(2 * np.pi * 70 * t + 1.3 * np.sin(2 * np.pi * 0.6 * t + 1.0)) * (0.25 + 0.5 * np.sin(np.pi * t / dur)) * 0.45
    gl = glitter(dur, 150, 6, seed=6, level=0.55)
    chord = np.zeros(len(t))
    head = t < 1.0
    for f, a in ((1320.0, 1.0), (1980.0, 0.7), (2640.0, 0.5)):
        chord += a * np.sin(2 * np.pi * f * t) * (t / 1.0) ** 2.2 * head
    settle = np.sin(2 * np.pi * 88 * t) * np.exp(-np.clip(t - (dur - 0.35), 0, None) * 11.0) * (t > dur - 0.35) * 0.7
    x = (body * 0.55 + air + low + gl) * env(len(t), 0.05, 0.55, 1.6) + chord * 0.30 + settle
    return norm(lp(x, 11000, 2), 0.85)


def lock():
    """A lock held: two short chirps, the second higher, with a little room round them."""
    dur = 0.75
    n = int(dur * SR)
    x = np.zeros(n)
    for start, f0, f1 in ((0.0, 1180.0, 1330.0), (0.17, 1560.0, 1820.0)):
        i = int(start * SR)
        m = int(0.12 * SR)
        tt = np.arange(m) / SR
        ph = 2 * np.pi * np.cumsum(np.linspace(f0, f1, m)) / SR
        x[i:i + m] += (np.sin(ph) + 0.35 * np.sin(2 * ph)) * np.exp(-tt * 20.0) * env(m, 0.003, 0.02, 1.0)
    out = x.copy()
    for d, g in ((0.043, 0.38), (0.087, 0.24), (0.141, 0.14)):          # a few echoes: the room
        k = int(d * SR)
        out[k:] += x[:-k] * g
    return norm(out, 0.7)


def fault():
    """A fault: two sawtooth tones a few hertz apart that sag in pitch, a burst of noise, a rattle at fourteen times a second; over in a second."""
    dur = 1.15
    t = t_(dur)
    f = 205.0 * (1.0 - 0.28 * (t / dur))
    ph1, ph2 = 2 * np.pi * np.cumsum(f) / SR, 2 * np.pi * np.cumsum(f * 1.047) / SR
    saw = (2 * ((ph1 / (2 * np.pi)) % 1.0) - 1) + (2 * ((ph2 / (2 * np.pi)) % 1.0) - 1)
    rattle = 0.45 + 0.55 * (np.sin(2 * np.pi * 14 * t) > 0)
    burst = lp(rng.normal(0, 1, len(t)), 2400) * np.exp(-t * 9.0) * 0.9
    x = (lp(saw, 1800, 2) * 0.5 * rattle + burst) * env(len(t), 0.004, 0.45, 1.5)
    return norm(x, 0.78)


def hum(dur=6.0):
    """The pads' hum while a cycle runs: a low drone and its harmonics beating slowly, a faint shimmer on top; every periodic part has a whole number of cycles in the loop."""
    t = t_(dur)
    x = np.zeros(len(t))
    for f, a, beat in ((55.0, 1.0, 0.5), (110.0, 0.55, 1.0), (165.0, 0.30, 1.5), (220.0, 0.18, 0.5), (330.0, 0.10, 2.0)):
        for det, sign in ((0.0, 1.0), (beat / dur * 2, -1.0)):
            f2 = round((f + det) * dur) / dur                                   # whole cycles
            x += a * 0.5 * np.sin(2 * np.pi * f2 * t + sign * 0.6)
    shimmer = np.zeros(len(t))
    for f in (1320.0, 1980.0, 2640.0):
        f2 = round(f * dur) / dur
        shimmer += np.sin(2 * np.pi * f2 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * (round(3 * dur) / dur) * t + f * 0.01))
    x = x * (0.85 + 0.15 * np.sin(2 * np.pi * (2.0) * t)) + shimmer * 0.018
    return norm(x, 0.34)


SOUNDS = {
    "SW_Xport_Energize": energize,
    "SW_Xport_Demat": demat,
    "SW_Xport_Remat": remat,
    "SW_Xport_Lock": lock,
    "SW_Xport_Fault": fault,
    "SW_Xport_Hum": hum,
}


def report(name, x):
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(np.max(np.abs(x)))
    n = len(x)
    # a rough picture of where the energy sits, third by third (spectral centroid, Hz): a rising sweep rises, a falling one falls
    cents = []
    for k in range(3):
        seg = x[k * n // 3:(k + 1) * n // 3]
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        fr = np.fft.rfftfreq(len(seg), 1 / SR)
        cents.append(float((sp * fr).sum() / (sp.sum() + 1e-9)))
    seam = float(abs(x[0] - x[-1]))
    return f"{name}: {n / SR:.2f} s, peak {peak:.2f}, rms {rms:.3f}, centroid by thirds {cents[0]:.0f}/{cents[1]:.0f}/{cents[2]:.0f} Hz, seam {seam:.3f}"


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn().astype(np.float32)
        sf.write(os.path.join(OUT, name + ".wav"), x, SR, subtype="PCM_16")
        print(report(name, x))
    print("TRANSPORTER_SOUNDS_OK")
