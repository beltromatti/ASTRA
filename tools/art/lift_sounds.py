"""The lifts' sounds (docs/ASCENSORI.md), synthesised: no third-party audio.

  SW_Lift_Hum     the car's hum while it moves: a maglev's low electrical drone with an air rush over it, a seamless loop (the game turns its volume and its pitch up with the car's
                  speed: Source/ASTRA/AstraLiftCar.cpp, UpdateHum)
  SW_Lift_Thump   the soft knock of the car's guides taking up the load as it sets off and as it stops (a muffled thud with a short latch tick)
  SW_Lift_Chime   the arrival chime: two soft tones, the second a fourth above the first, with a shimmer

Run: uv run --with numpy --with soundfile --with scipy python tools/art/lift_sounds.py [out_dir]   -> art/_cache/audio/*.wav (then tools/ue_scripts/build_lifts.py imports them)
"""
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "art", "_cache", "audio")
rng = np.random.default_rng(23)


def t_(sec: float) -> np.ndarray:
    return np.arange(int(sec * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def circular_noise(n: int, lo: float, hi: float) -> np.ndarray:
    """Band-limited noise whose end continues into its start (filtered in the frequency domain, so the buffer is one period of it): what a seamless loop is made of."""
    spec = np.fft.rfft(rng.normal(0, 1, n))
    f = np.fft.rfftfreq(n, 1 / SR)
    band = np.clip((f - lo) / max(lo * 0.5, 1.0), 0, 1) * np.clip((hi - f) / max(hi * 0.5, 1.0), 0, 1)
    return np.fft.irfft(spec * band, n)


def hum() -> np.ndarray:
    """A 6 s loop. Every tone has a whole number of cycles in it, the rush and the slow beating are periodic, so the loop has no seam."""
    dur = 6.0
    n = int(dur * SR)
    t = np.arange(n) / SR
    base = 120.0                                                 # a whole number of Hz is a whole number of cycles in the loop; and a laptop's speakers give nothing below a hundred or so
    x = np.zeros(n)
    for k, a in ((1, 0.5), (2, 0.5), (3, 0.36), (4, 0.24), (5, 0.14), (7, 0.07)):
        # a slow drift of each partial (a whole number of beats in the loop), as the field never holds perfectly steady
        beat = 1 + 0.08 * np.sin(2 * np.pi * (k % 3 + 1) / dur * t + k)
        x += a * beat * np.sin(2 * np.pi * base * k * t + k * 0.7)
    x += 0.10 * np.sin(2 * np.pi * (base * 11.0) * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 2 / dur * t))      # a thin electrical whine (1.2 kHz), breathing
    rush = circular_noise(n, 250.0, 3200.0)
    rush *= 0.5 + 0.5 * np.sin(2 * np.pi * 3 / dur * t + 1.2) ** 2
    rumble = circular_noise(n, 45.0, 220.0)
    x = x + rush / (np.std(rush) + 1e-9) * 0.22 + rumble / (np.std(rumble) + 1e-9) * 0.14
    x = np.tanh(1.2 * x)
    return norm(x, 0.8)


def thump() -> np.ndarray:
    """The guides taking the load: a muffled thud (a sine that drops from 90 to 38 Hz), a puff of low noise, and a short latch tick."""
    t = t_(0.9)
    thud = np.sin(2 * np.pi * np.cumsum(46 + 70 * np.exp(-t * 22)) / SR) * np.exp(-t * 6.5)
    body = np.sin(2 * np.pi * np.cumsum(170 + 140 * np.exp(-t * 30)) / SR) * np.exp(-t * 15) * 0.55         # the wood of the knock: what a small speaker can reproduce
    puff = lp(rng.normal(0, 1, len(t)), 900) * np.exp(-t * 11) * 0.6
    tick = np.zeros_like(t)
    m = int(0.03 * SR)
    tick[int(0.012 * SR):int(0.012 * SR) + m] = bp(rng.normal(0, 1, m), 1200, 3200) * np.exp(-np.arange(m) / SR * 150) * 0.22
    x = 1.0 * thud + body + puff + tick
    x *= np.minimum(1.0, t / 0.004)                               # (no click at the start)
    return norm(lp(np.tanh(1.4 * x), 3500), 0.85)


def chime() -> np.ndarray:
    """An arrival chime: a soft two-tone ding-dong in a clean metal voice, the second tone a perfect fourth up, a faint shimmer on top."""
    t = t_(1.5)

    def tone(f, t0, decay, gain):
        tt = np.maximum(0.0, t - t0)
        env = (t >= t0) * np.exp(-tt * decay) * np.minimum(1.0, tt / 0.006)
        return gain * env * (np.sin(2 * np.pi * f * tt) + 0.32 * np.sin(2 * np.pi * 2.76 * f * tt) * np.exp(-tt * 9) + 0.12 * np.sin(2 * np.pi * 5.4 * f * tt) * np.exp(-tt * 16))
    x = tone(784.0, 0.0, 3.4, 1.0) + tone(1046.5, 0.22, 2.8, 0.9)
    x += 0.05 * hp(rng.normal(0, 1, len(t)), 5000) * np.exp(-t * 7) * (t > 0.2)
    return norm(lp(x, 9000), 0.7)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for name, wave in (("SW_Lift_Hum", hum()), ("SW_Lift_Thump", thump()), ("SW_Lift_Chime", chime())):
        sf.write(os.path.join(OUT, name + ".wav"), wave.astype(np.float32), SR, subtype="PCM_16")
        seam = abs(float(wave[0] - wave[-1]))
        print(f"{name}: {len(wave) / SR:.2f} s, peak {np.max(np.abs(wave)):.2f}, rms {np.sqrt(np.mean(wave ** 2)):.3f}, first-last {seam:.4f}")


if __name__ == "__main__":
    main()
