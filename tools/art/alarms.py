"""Original ship alarm sounds, synthesised (no third-party audio): red alert whoop, yellow two-tone chime, all-clear.
Run: uv run --with numpy --with soundfile python tools/art/alarms.py -> art/_cache/audio/*.wav (48 kHz mono)"""
import os

import numpy as np
import soundfile as sf

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "audio")


def env(n, a=0.01, r=0.1):
    e = np.ones(n)
    na, nr = int(a * SR), int(r * SR)
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def room(x, t60=0.9, mix=0.25):
    """Cheap metallic room: a few damped comb echoes (a steel bulkhead space)."""
    y = x.copy()
    for d_ms, g in ((29, 0.55), (37, 0.5), (43, 0.45), (53, 0.4)):
        d = int(d_ms * SR / 1000)
        fb = np.zeros(len(x) + int(t60 * SR))
        fb[:len(x)] += x
        for i in range(d, len(fb)):
            fb[i] += g * fb[i - d] * 0.92
        y = np.pad(y, (0, len(fb) - len(y))) + mix * fb / 4
    return y / (np.max(np.abs(y)) + 1e-9) * 0.9


def whoop():
    parts = []
    for _ in range(3):
        n = int(0.85 * SR)
        t = np.arange(n) / SR
        f = 320 * (900 / 320) ** (t / t[-1])
        ph = 2 * np.pi * np.cumsum(f) / SR
        s = np.sin(ph) + 0.45 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph) + 0.12 * np.sin(5 * ph)
        s = np.tanh(1.6 * s) * env(n, 0.02, 0.08)
        parts += [s, np.zeros(int(0.12 * SR))]
    return room(np.concatenate(parts))


def chime(freqs, dur=0.55, gap=0.08):
    parts = []
    for fq in freqs:
        n = int(dur * SR)
        t = np.arange(n) / SR
        s = (np.sin(2 * np.pi * fq * t) + 0.3 * np.sin(2 * np.pi * 2.01 * fq * t) + 0.12 * np.sin(2 * np.pi * 3.02 * fq * t))
        s *= np.exp(-t * 4.5) * env(n, 0.005, 0.05)
        parts += [s, np.zeros(int(gap * SR))]
    return room(np.concatenate(parts), t60=0.7, mix=0.2)


os.makedirs(OUT, exist_ok=True)
sf.write(os.path.join(OUT, "SW_Alert_Red.wav"), whoop().astype(np.float32), SR, subtype="PCM_16")
sf.write(os.path.join(OUT, "SW_Alert_Yellow.wav"), chime([880, 660, 880, 660]).astype(np.float32), SR, subtype="PCM_16")
sf.write(os.path.join(OUT, "SW_Alert_Clear.wav"), chime([660, 880, 1100]).astype(np.float32), SR, subtype="PCM_16")
print("ALARMS_OK", sorted(os.listdir(OUT)))
