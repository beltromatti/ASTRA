"""Original ship sounds, synthesised (no third-party audio). In space only what travels through the hull is heard
(docs/STILE.md §9): our own guns and launchers felt through the frame, point defence, the flight deck catapult, the
bridge's air and machinery, console chirps.

Run: uv run --with numpy --with soundfile --with scipy python tools/art/ship_sounds.py -> art/_cache/audio/*.wav
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "audio")
rng = np.random.default_rng(11)


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


def frame_ring(t, strength=1.0, seed=0):
    """The ship's frame ringing after a mechanical shock (a few inharmonic metal modes)."""
    r = np.random.default_rng(seed)
    return strength * sum(np.sin(2 * np.pi * f * t + r.uniform(0, 6)) * np.exp(-t * d) * a
                          for f, d, a in ((97, 3.5, 0.3), (173, 4.5, 0.22), (262, 6.0, 0.14), (419, 8.0, 0.08), (733, 12.0, 0.05)))


def rail_fire():
    """A twin railgun turret firing, felt through the hull: capacitor snap, a deep kick, the frame ringing."""
    t = t_(1.6)
    kick = np.sin(2 * np.pi * (34 + 60 * np.exp(-t * 18)) * t) * np.exp(-t * 7)
    snap_t = t[: int(0.03 * SR)]
    snap = np.zeros_like(t)
    snap[: len(snap_t)] = np.sin(2 * np.pi * np.cumsum(9000 - 260000 * snap_t) / SR) * np.exp(-snap_t * 120) * 0.35
    crack = bp(rng.normal(0, 1, len(t)), 900, 3500) * np.exp(-t * 55) * 0.5
    x = 1.3 * kick + snap + crack + frame_ring(t, 0.7, 1)
    return norm(np.tanh(1.5 * lp(x, 5000)))


def vls_launch(heavy=False):
    """A missile (or torpedo) leaving the vertical launcher: hatch clunk, the motor's roar fading as it clears the ship."""
    dur = 2.6 if heavy else 2.0
    t = t_(dur)
    clunk = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 25) + bp(rng.normal(0, 1, len(t)), 200, 1200) * np.exp(-t * 40) * 0.6
    n = rng.normal(0, 1, len(t))
    roar = np.zeros_like(t)
    seg = 2048
    for i in range(0, len(t) - seg, seg // 2):   # a band sweeping up as the missile accelerates away
        f = 250 + 1300 * (i / len(t)) ** 0.7
        w = np.hanning(seg)
        roar[i:i + seg] += bp(n[i:i + seg], f * 0.6, min(f * 1.8, SR / 2 - 100)) * w
    shape = np.clip(t / 0.08, 0, 1) * np.exp(-np.maximum(t - 0.3, 0) * (1.6 if heavy else 2.2))
    rumble = lp(rng.normal(0, 1, len(t)), 120) * shape * 3.0
    x = 0.9 * clunk + roar * shape * 0.8 + rumble + frame_ring(t, 0.25, 2)
    return norm(np.tanh(1.3 * x))


def pd_burst():
    """Point-defence mounts firing a burst (muffled by the hull): a fast mechanical rattle."""
    t = t_(0.7)
    x = np.zeros_like(t)
    rate = 55.0
    for k in range(int(0.45 * rate)):
        i = max(0, int((k / rate + rng.uniform(-0.002, 0.002)) * SR))
        m = min(len(t) - i, int(0.018 * SR))
        if m <= 0:
            continue
        tt = np.arange(m) / SR
        x[i:i + m] += (rng.normal(0, 1, m) * 0.7 + np.sin(2 * np.pi * 140 * tt)) * np.exp(-tt * 260)
    return norm(np.tanh(2.0 * lp(x, 1600)) * np.exp(-np.maximum(t - 0.45, 0) * 12))


def catapult():
    """A fighter launched from the flight deck: the shuttle's electric whine rising, the thud of the stop, the ring."""
    t = t_(2.0)
    f = 180 + 900 * np.clip(t / 1.1, 0, 1) ** 1.6
    whine = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 0.15, 0, 1) * (t < 1.15) * 0.35
    whine += np.sin(4 * np.pi * np.cumsum(f) / SR) * 0.12 * (t < 1.15)
    stop_t = np.maximum(t - 1.15, 0)
    thud = np.sin(2 * np.pi * 48 * stop_t) * np.exp(-stop_t * 9) * (t >= 1.15) * 1.2
    hiss = bp(rng.normal(0, 1, len(t)), 2000, 7000) * np.exp(-stop_t * 6) * (t >= 1.15) * 0.25
    ring = frame_ring(stop_t, 0.5, 3) * (t >= 1.15)
    return norm(np.tanh(1.2 * (lp(whine, 4000) + thud + hiss + ring)))


def chirp():
    """A console acknowledging an input: two soft tones."""
    parts = []
    for fq in (1760, 2349):
        t = t_(0.07)
        parts.append(np.sin(2 * np.pi * fq * t) * np.exp(-t * 25) * np.clip(t / 0.004, 0, 1))
    return norm(np.concatenate(parts + [np.zeros(int(0.05 * SR))]), 0.5)


def door(opening=True):
    """A pressure door: the seal releasing (hiss), the leaves' motor, the soft stop (or the seal closing)."""
    t = t_(0.9)
    hiss = bp(rng.normal(0, 1, len(t)), 2500, 7500) * np.exp(-t * (7 if opening else 11)) * 0.5
    f = (260 + 220 * np.clip(t / 0.55, 0, 1)) if opening else (480 - 220 * np.clip(t / 0.55, 0, 1))
    motor = (np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25 + np.sin(4 * np.pi * np.cumsum(f) / SR) * 0.08) * (t < 0.58) * np.clip(t / 0.05, 0, 1)
    stop_t = np.maximum(t - 0.58, 0)
    stop = np.sin(2 * np.pi * 62 * stop_t) * np.exp(-stop_t * 22) * (t >= 0.58) * (0.5 if opening else 0.9)
    seal = bp(rng.normal(0, 1, len(t)), 300, 1500) * np.exp(-stop_t * 30) * (t >= 0.58) * (0.0 if opening else 0.4)
    x = (hiss if opening else hiss * 0.4) + motor + stop + seal
    return norm(np.tanh(1.3 * x), 0.8)


def transit():
    """A Janus transit felt through the hull: a rising drone, the gate's crack, the long ring of the frame."""
    t = t_(5.0)
    rise = np.clip(t / 2.2, 0, 1)
    f = 30 + 90 * rise ** 2
    drone = (np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(4 * np.pi * np.cumsum(f) / SR)) * rise * (t < 2.3)
    hiss = bp(rng.normal(0, 1, len(t)), 400, 5000) * rise ** 3 * (t < 2.3) * 0.5
    bt = np.maximum(t - 2.3, 0)
    boom = (np.sin(2 * np.pi * (28 + 40 * np.exp(-bt * 6)) * bt) * np.exp(-bt * 1.6) * 1.6
            + lp(rng.normal(0, 1, len(t)), 300) * np.exp(-bt * 2.5) * 1.2) * (t >= 2.3)
    ring = frame_ring(bt, 0.9, 5) * (t >= 2.3)
    return norm(np.tanh(1.2 * (drone + hiss + boom + ring)))


def sparks():
    """A shorted fixture: the arc's snap and buzz, then a shower of crackles thinning out as the sparks die."""
    t = t_(1.6)
    x = np.zeros_like(t)
    arc_t = t[: int(0.22 * SR)]
    buzz = (np.sign(np.sin(2 * np.pi * 120 * arc_t)) * 0.3 + bp(rng.normal(0, 1, len(arc_t)), 1500, 9000) * 0.9)
    x[: len(arc_t)] += buzz * np.exp(-arc_t * 9) * (0.6 + 0.4 * (rng.random(len(arc_t)) > 0.5))
    snap_n = int(0.012 * SR)
    x[:snap_n] += hp(rng.normal(0, 1, snap_n), 800) * 1.6
    for _ in range(140):                      # crackles, dense at first, sparse as the shower cools
        at = rng.exponential(0.28)
        if at > 1.5:
            continue
        i = int(at * SR)
        m = int(rng.uniform(0.0008, 0.004) * SR)
        if i + m >= len(x):
            continue
        x[i:i + m] += hp(rng.normal(0, 1, m), 2500) * np.exp(-np.arange(m) / m * 4) * rng.uniform(0.2, 0.8) * np.exp(-at * 1.5)
    return norm(np.tanh(1.4 * hp(x, 300)), 0.85)


def bridge_ambience(dur=24.0):
    """The bridge at rest: the reactor's deep hum through the deck, air handling, and far electronics (loopable)."""
    t = t_(dur)
    hum = (np.sin(2 * np.pi * 50 * t) * 0.35 + np.sin(2 * np.pi * 100 * t) * 0.18 + np.sin(2 * np.pi * 150 * t) * 0.07
           + np.sin(2 * np.pi * 23 * t) * 0.25) * (1 + 0.08 * np.sin(2 * np.pi * t / 6.0))
    air = lp(hp(rng.normal(0, 1, len(t)), 40), 320, order=4) * 1.4 * (1 + 0.15 * np.sin(2 * np.pi * t / 8.0 + 1))
    blips = np.zeros_like(t)
    for _ in range(int(dur / 3)):
        i = rng.integers(0, len(t) - SR // 5)
        m = int(0.06 * SR)
        tt = np.arange(m) / SR
        blips[i:i + m] += np.sin(2 * np.pi * rng.choice([1320, 1580, 1975, 2640]) * tt) * np.exp(-tt * 40) * 0.08
    x = hum + air * 0.6 + blips
    # seamless loop: crossfade the last second into the first
    n = SR
    fade = np.linspace(0, 1, n)
    x[:n] = x[:n] * fade + x[-n:] * (1 - fade)
    x = x[:-n]
    return norm(x, 0.6)


def falcon_engine(dur=8.0):
    """A Falcon's engines felt through the airframe (loopable): the turbopumps' whine, the drive's rumble, the air in
    the cockpit. The game bends its pitch and level with the throttle."""
    t = t_(dur)
    wob = 1 + 0.004 * np.sin(2 * np.pi * 0.7 * t) + 0.002 * np.sin(2 * np.pi * 2.3 * t)
    rumble = sum(np.sin(2 * np.pi * 62 * k * t * wob + k) / k ** 1.2 for k in range(1, 9)) * 0.35
    whine = (np.sin(2 * np.pi * 1840 * t * wob) * 0.09 + np.sin(2 * np.pi * 3680 * t * wob) * 0.035 + np.sin(2 * np.pi * 2760 * t * wob) * 0.02)
    roar = lp(hp(rng.normal(0, 1, len(t)), 60), 900, order=4) * 0.9 * (1 + 0.1 * np.sin(2 * np.pi * t / 3.1))
    air = hp(rng.normal(0, 1, len(t)), 4000) * 0.025
    x = rumble + whine + roar + air
    n = SR
    fade = np.linspace(0, 1, n)
    x[:n] = x[:n] * fade + x[-n:] * (1 - fade)
    return norm(x[:-n], 0.7)


def lock_beep():
    """The seeker searching: one short beep."""
    t = t_(0.09)
    return norm(np.sin(2 * np.pi * 1650 * t) * np.minimum(1, t * 400) * np.exp(-t * 18), 0.5)


def lock_solid():
    """The seeker locked: a steady tone (exactly 2100 cycles in a second: it loops without a seam)."""
    t = t_(1.0)
    return norm(np.sin(2 * np.pi * 2100 * t) + 0.25 * np.sin(2 * np.pi * 4200 * t), 0.45)


def missile_warning():
    """Missile inbound on the Falcon: a fast warble (loops seamlessly)."""
    t = t_(1.0)
    f = np.where((t * 8) % 1 < 0.5, 950, 1420)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return norm(np.tanh(3 * np.sin(ph)) * 0.8, 0.55)


os.makedirs(OUT, exist_ok=True)
for name, fn in (("SW_Rail_Fire", rail_fire), ("SW_VLS_Launch", vls_launch), ("SW_Torpedo_Launch", lambda: vls_launch(True)),
                 ("SW_PD_Burst", pd_burst), ("SW_Catapult", catapult), ("SW_Console_Chirp", chirp),
                 ("SW_Bridge_Ambience", bridge_ambience), ("SW_Door_Open", door), ("SW_Door_Close", lambda: door(False)), ("SW_Transit", transit),
                 ("SW_Sparks", sparks), ("SW_Falcon_Engine", falcon_engine), ("SW_Lock_Beep", lock_beep), ("SW_Lock_Solid", lock_solid),
                 ("SW_Missile_Warning", missile_warning)):
    sf.write(os.path.join(OUT, name + ".wav"), fn().astype(np.float32), SR, subtype="PCM_16")
print("SHIP_SOUNDS_OK", sorted(f for f in os.listdir(OUT) if f.endswith(".wav")))
