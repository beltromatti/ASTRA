"""Original sounds of the damage inside the Aquila (DISTRUZIONE, docs/DISTRUZIONE.md), synthesised (no third-party audio): what the Captain
hears in the rooms near a hit: a fire's roar and crackle, air venting through a breach, the containment field's hum, the fixed suppression
discharging, a pressure bulkhead slamming shut, a blow going off inside the hull, a hole opening to space.

Loops are seamless (every periodic part has a whole number of cycles in the loop, the noise is cross-faded at its seam); one-shots end in silence.
Run: uv run --with numpy --with soundfile --with scipy python tools/art/damage_sounds.py -> art/_cache/audio/SW_*.wav
Import: tools/ue.py py "exec(open('tools/ue_scripts/import_damage_audio.py').read())"
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "audio")
rng = np.random.default_rng(23)


def t_(sec):
    return np.arange(int(sec * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def seamless(x, fade=0.6):
    """Makes a noisy signal loop: its tail is cross-faded into its head (equal power), so the end meets the start without a click."""
    n = int(fade * SR)
    head, tail = x[:n].copy(), x[-n:].copy()
    w = np.linspace(0.0, 1.0, n)
    out = x[:-n].copy()
    out[:n] = head * np.sqrt(w) + tail * np.sqrt(1.0 - w)
    return out


def slow_noise(n, rate_hz, seed):
    """A smooth random curve in 0..1 with about rate_hz wanderings a second (for amplitudes that breathe)."""
    r = np.random.default_rng(seed)
    pts = r.uniform(0, 1, int(n / SR * rate_hz) + 4)
    xs = np.linspace(0, len(pts) - 1, n)
    return np.interp(xs, np.arange(len(pts)), pts)


def fire_loop(dur=10.0):
    """A compartment on fire: the low roar of the flames drawing air, a bed of hiss, and the crackle of what burns (sparse, uneven)."""
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    roar = lp(rng.normal(0, 1, n), 380, 3) * (0.55 + 0.45 * slow_noise(n, 0.7, 1))
    roar += 0.5 * bp(rng.normal(0, 1, n), 120, 900) * (0.4 + 0.6 * slow_noise(n, 1.9, 2))
    hiss = hp(rng.normal(0, 1, n), 3500) * 0.05 * (0.4 + 0.6 * slow_noise(n, 3.0, 3))
    crackle = np.zeros(n)
    rate = 24.0
    for _ in range(int(rate * dur * 1.0)):
        i = int(rng.uniform(0, n - 400))
        m = int(rng.uniform(0.0015, 0.007) * SR)
        tt = np.arange(m) / SR
        amp = rng.uniform(0.2, 1.0) ** 2.2
        burst = rng.normal(0, 1, m) * np.exp(-tt * rng.uniform(500, 1500))
        crackle[i:i + m] += burst * amp
    # a few louder pops (a seam splitting, a panel cooking)
    for _ in range(int(dur * 0.9)):
        i = int(rng.uniform(0, n - 3000))
        m = int(0.012 * SR)
        tt = np.arange(m) / SR
        crackle[i:i + m] += np.sin(2 * np.pi * rng.uniform(180, 520) * tt) * np.exp(-tt * 350) * rng.uniform(0.6, 1.4)
    crackle = bp(crackle, 700, 7000) * 1.6
    x = norm(np.tanh(1.4 * (roar * 1.0 + hiss + crackle * 0.55)), 0.8)
    return seamless(x)[: int(dur * SR)]


def vent_loop(dur=8.0):
    """Air going out through a hole in the hull: a hard rush, a low rumble where the pressure goes, a thin whistle from the edge of the hole."""
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    rush = bp(rng.normal(0, 1, n), 260, 4200, 3) * (0.7 + 0.3 * slow_noise(n, 1.1, 5))
    rumble = lp(rng.normal(0, 1, n), 110, 3) * 1.8 * (0.6 + 0.4 * slow_noise(n, 0.6, 6))
    whistle_f = 2350 + 180 * slow_noise(n, 0.35, 7)
    whistle = np.sin(2 * np.pi * np.cumsum(whistle_f) / SR) * 0.035 * (0.5 + 0.5 * slow_noise(n, 0.9, 8))
    x = norm(np.tanh(1.2 * (rush * 0.9 + rumble * 0.5 + whistle)), 0.8)
    return seamless(x)[: int(dur * SR)]


def field_hum(dur=6.0):
    """A containment field holding a breach: a deep hum on a low fundamental with its first harmonics, a slow flutter, and a thin shimmer of charge."""
    t = t_(dur)
    f0 = 110.0                                        # a whole number of cycles in the loop (660), as is every other periodic part; high enough for a laptop speaker
    hum = sum(a * np.sin(2 * np.pi * f0 * k * t + ph) for k, a, ph in ((1, 1.0, 0.0), (2, 0.55, 1.1), (3, 0.32, 2.3), (4, 0.16, 0.4), (6, 0.08, 4.0)))
    flutter = 1.0 + 0.10 * np.sin(2 * np.pi * 7.0 * t) + 0.06 * np.sin(2 * np.pi * (5.0 / dur) * t)
    beat = 1.0 + 0.2 * np.sin(2 * np.pi * (3.0 / dur) * t)
    n = len(t)
    charge = seamless(bp(rng.normal(0, 1, n + int(0.6 * SR)), 2800, 7000))[:n]          # the only part that is noise: cross-faded at the seam
    shimmer = charge * (0.5 + 0.5 * np.sin(2 * np.pi * 11.0 * t)) ** 2 * 0.07
    x = hum * flutter * beat + shimmer
    return norm(np.tanh(0.9 * x), 0.7)


def suppress_loop(dur=6.0):
    """The fixed suppression discharging: a wide, soft hiss with a little rumble from the cold gas."""
    n = int((dur + 0.6) * SR)
    hiss = bp(rng.normal(0, 1, n), 700, 9500, 2) * (0.75 + 0.25 * slow_noise(n, 2.0, 11))
    rumble = lp(rng.normal(0, 1, n), 150, 2) * 0.5
    x = norm(np.tanh(1.1 * (hiss + rumble)), 0.75)
    return seamless(x)[: int(dur * SR)]


def bulkhead_slam():
    """A section's pressure bulkhead closing: the drive's whine, the leaf slamming home with a deep thud and a clang, the locks, the frame ringing."""
    t = t_(2.0)
    x = np.zeros_like(t)
    # the drive whine winding up over 0.35 s
    f = 420 + 700 * np.clip(t / 0.35, 0, 1)
    x += np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 0.05, 0, 1) * (t < 0.36) * 0.16
    # the slam
    s = np.maximum(t - 0.36, 0.0)
    on = (t >= 0.36).astype(float)
    x += np.sin(2 * np.pi * (46 + 38 * np.exp(-s * 22)) * s) * np.exp(-s * 8.0) * on * 1.5
    x += bp(rng.normal(0, 1, len(t)), 350, 2400) * np.exp(-s * 26) * on * 0.9
    x += sum(np.sin(2 * np.pi * fq * s) * np.exp(-s * d) * a for fq, d, a in ((133, 5.5, 0.35), (251, 7.0, 0.25), (437, 9.0, 0.16), (811, 13.0, 0.09))) * on
    # the locks, a beat later
    for at, amp in ((0.62, 0.55), (0.71, 0.4)):
        s2 = np.maximum(t - at, 0.0)
        x += bp(rng.normal(0, 1, len(t)), 600, 3200) * np.exp(-s2 * 90) * (t >= at) * amp
    return norm(np.tanh(1.3 * lp(x, 7500)), 0.9)


def blast_inside():
    """A blow that came through the plating and went off in a compartment: the crack, the boom that shakes the frame, tearing metal, a rattle of debris."""
    t = t_(3.0)
    n = len(t)
    crack = rng.normal(0, 1, n) * np.exp(-t * 90) * 1.2
    boom = np.sin(2 * np.pi * (34 + 70 * np.exp(-t * 14)) * t) * np.exp(-t * 4.5) * 1.8
    body = lp(rng.normal(0, 1, n), 320, 3) * np.exp(-t * 6.5) * 1.5
    tear = np.zeros(n)
    seg = 2048
    noise = rng.normal(0, 1, n)
    for i in range(0, n - seg, seg // 2):                  # a band sweeping down: metal giving way
        fc = 2600 * np.exp(-i / n * 4.0) + 300
        tear[i:i + seg] += bp(noise[i:i + seg], fc * 0.6, min(fc * 1.7, SR / 2 - 100)) * np.hanning(seg)
    tear *= np.exp(-t * 5.0) * 0.55
    ring = sum(np.sin(2 * np.pi * fq * t + rng.uniform(0, 6)) * np.exp(-t * d) * a for fq, d, a in ((97, 3.0, 0.5), (173, 4.0, 0.35), (262, 5.5, 0.25), (419, 7.0, 0.16), (733, 11.0, 0.09)))
    debris = np.zeros(n)
    for _ in range(46):                                    # pieces falling and skittering after it
        i = int(rng.uniform(0.15, 1.8) * SR)
        m = int(rng.uniform(0.002, 0.012) * SR)
        if i + m >= n:
            continue
        tt = np.arange(m) / SR
        debris[i:i + m] += rng.normal(0, 1, m) * np.exp(-tt * 700) * rng.uniform(0.1, 0.6) * np.exp(-i / SR * 1.8)
    x = crack + boom + body + tear + ring * 0.8 + bp(debris, 800, 6500) * 1.3
    x = np.tanh(1.2 * lp(x, 9000)) * np.clip(t / 0.002, 0, 1)
    return norm(x * np.clip((t[-1] - t) / 0.4, 0, 1), 0.92)


def decompression():
    """A hole opening to space in a room: a thump, the rush of the air going swelling and thinning to a hiss, the structure groaning."""
    t = t_(3.6)
    n = len(t)
    thump = np.sin(2 * np.pi * (60 + 90 * np.exp(-t * 20)) * t) * np.exp(-t * 9) * 1.3
    env = np.clip(t / 0.05, 0, 1) * np.exp(-t * 0.9) * (1.0 + 0.5 * np.exp(-t * 10))
    rush = bp(rng.normal(0, 1, n), 200, 5200, 3) * env
    rumble = lp(rng.normal(0, 1, n), 140, 3) * env * 1.6
    groan = np.sin(2 * np.pi * np.cumsum(70 + 30 * np.sin(2 * np.pi * 0.8 * t)) / SR) * 0.18 * np.exp(-t * 0.8) * np.clip(t / 0.3, 0, 1)
    x = thump + rush * 0.9 + rumble * 0.5 + groan
    x = np.tanh(1.1 * x) * np.clip((t[-1] - t) / 0.5, 0, 1)
    return norm(x, 0.9)


SOUNDS = (("SW_Fire_Loop", fire_loop), ("SW_Vent_Loop", vent_loop), ("SW_Field_Hum", field_hum), ("SW_Suppress_Loop", suppress_loop),
          ("SW_Bulkhead_Slam", bulkhead_slam), ("SW_Blast_Inside", blast_inside), ("SW_Decompression", decompression))
LOOPS = {"SW_Fire_Loop", "SW_Vent_Loop", "SW_Field_Hum", "SW_Suppress_Loop"}


def seam_jump(x):
    """How big the step at the loop's seam is, against the signal's own sample-to-sample movement (about 1 or less: no click)."""
    step = abs(float(x[0] - x[-1]))
    typical = float(np.mean(np.abs(np.diff(x[: SR]))))
    return step / (typical + 1e-9)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in SOUNDS:
        x = fn().astype(np.float32)
        sf.write(os.path.join(OUT, name + ".wav"), x, SR, subtype="PCM_16")
        print("%-20s %5.2f s  peak %.2f  rms %.3f%s" % (name, len(x) / SR, float(np.max(np.abs(x))), float(np.sqrt(np.mean(x ** 2))),
                                                         ("  seam %.2f" % seam_jump(x)) if name in LOOPS else ""))
    print("DAMAGE_SOUNDS_OK")
