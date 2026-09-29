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


def door_chime():
    """Someone at the Captain's door: a warm two-note chime (a falling fourth), soft bell partials, a short tail."""
    x = np.zeros(int(1.5 * SR))
    for start, fq in ((0.0, 988.0), (0.32, 740.0)):
        t = t_(1.1)
        tone = sum(np.sin(2 * np.pi * fq * m * t) * a * np.exp(-t * d) for m, a, d in ((1, 1.0, 3.2), (2.01, 0.28, 5.5), (3.0, 0.1, 8.0)))
        tone *= np.clip(t / 0.006, 0, 1)
        i = int(start * SR)
        x[i:i + len(t)] += tone[: len(x) - i]
    return norm(lp(x, 6000), 0.55)


def pod_launch():
    """A lifepod leaving the ship: the hatch slamming, the explosive bolts, the launch rail's rush, the pod's motor
    burning for a few seconds and fading, the frame's ring."""
    t = t_(6.0)
    x = np.zeros_like(t)
    slam = np.sin(2 * np.pi * 70 * t) * np.exp(-t * 18) * 0.8 + bp(rng.normal(0, 1, len(t)), 200, 1200) * np.exp(-t * 25) * 0.5
    x += slam
    for k, when in enumerate((0.55, 0.6, 0.66, 0.7)):                 # the bolts, a ragged volley
        i = int(when * SR)
        n = len(t) - i
        tt = t[:n]
        x[i:] += (np.sin(2 * np.pi * (48 + 20 * k) * tt) * np.exp(-tt * 14) * 0.9
                  + hp(rng.normal(0, 1, n), 1500) * np.exp(-tt * 60) * 0.6)
    i = int(0.72 * SR)
    tt = t[: len(t) - i]
    rush = bp(rng.normal(0, 1, len(tt)), 180, 2400) * np.clip(tt / 0.1, 0, 1) * np.exp(-tt * 1.1) * 0.9
    motor = (np.sin(2 * np.pi * np.cumsum(90 + 30 * np.exp(-tt)) / SR) * 0.35 + lp(rng.normal(0, 1, len(tt)), 400) * 0.6) \
        * np.clip(tt / 0.2, 0, 1) * np.exp(-tt * 0.7)
    x[i:] += rush + motor
    x += frame_ring(t, 0.5, 7)
    return norm(np.tanh(1.3 * x), 0.9)


def pod_hum(dur=12.0):
    """Inside a drifting lifepod (loopable): the CO2 scrubber's fan, the electronics, a faint tick of the beacon."""
    t = t_(dur)
    fan = sum(np.sin(2 * np.pi * f * t) * a for f, a in ((120, 0.2), (240, 0.08), (361, 0.05)))
    air = lp(rng.normal(0, 1, len(t)), 900) * 0.25
    tick = np.zeros_like(t)
    for k in range(int(dur / 4)):                                     # the beacon's ping, every 4 s (dur divisible)
        i = int((k * 4 + 1.0) * SR)
        n = int(0.09 * SR)
        tick[i:i + n] += np.sin(2 * np.pi * 1320 * t[:n]) * np.exp(-t[:n] * 40) * 0.25
    x = fan + air + tick
    fade = int(0.5 * SR)                                              # seamless loop: cross-fade the ends
    x[:fade] = x[:fade] * np.linspace(0, 1, fade) + x[-fade:] * np.linspace(1, 0, fade)
    return norm(x[:-fade], 0.5)


def breach_felt():
    """The Aquila's reactor letting go, felt in the pod: no sound crosses the vacuum, but the shock and the debris
    reach the pod's shell — a deep thud that swells, the hull groaning, fragments pinging off it."""
    t = t_(9.0)
    swell = lp(rng.normal(0, 1, len(t)), 90) * np.clip(t / 0.4, 0, 1) * np.exp(-t * 0.5) * 3.0
    thud = np.sin(2 * np.pi * (30 + 18 * np.exp(-t * 2)) * t) * np.exp(-t * 0.9) * 1.2
    groan = np.sin(2 * np.pi * np.cumsum(55 + 12 * np.sin(2 * np.pi * 0.3 * t)) / SR) * np.clip((t - 0.8) / 1.5, 0, 1) * np.exp(-t * 0.35) * 0.35
    pings = np.zeros_like(t)
    for k in range(40):
        i = int(rng.uniform(0.6, 7.5) * SR)
        n = int(0.25 * SR)
        f = rng.uniform(900, 3200)
        pings[i:i + n] += np.sin(2 * np.pi * f * t[:n]) * np.exp(-t[:n] * rng.uniform(18, 40)) * rng.uniform(0.1, 0.35)
    x = swell + thud + groan + pings + frame_ring(t, 0.8, 9)
    return norm(np.tanh(1.2 * x), 0.95)


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


def entry_plasma(dur=10.0):
    """Atmospheric entry heard from the cockpit: a rising roar of air and plasma on the hull, buffeting, crackle, then
    easing off as the Falcon slows (the game starts it at the entry interface)."""
    t = t_(dur)
    env = np.clip(t / 3.0, 0, 1) ** 1.5 * np.clip((dur - t) / 3.5, 0, 1)
    roar = lp(hp(rng.normal(0, 1, len(t)), 30), 500, order=3) * 1.6
    hiss = bp(rng.normal(0, 1, len(t)), 1200, 5000) * 0.35
    buffet = 1 + 0.35 * np.sin(2 * np.pi * (3.1 + 1.5 * np.sin(t * 0.7)) * t) * np.sin(2 * np.pi * 0.43 * t)
    crackle = np.zeros_like(t)
    for _ in range(260):
        i = rng.integers(0, len(t) - 400)
        crackle[i:i + 400] += np.exp(-np.arange(400) / 45.0) * rng.normal(0, 1, 400) * 0.6
    x = (roar + hiss) * buffet * env + crackle * env ** 2
    return norm(np.tanh(1.3 * x), 0.85)


def pad(up=True):
    """The Captain's datapad: the rubber-bumpered slate taken up (or put down) — a soft handling thump, the screen
    waking with a small rising two-tone (falling when it goes to sleep)."""
    t = t_(0.45)
    thump = lp(rng.normal(0, 1, len(t)), 900) * np.exp(-t * 45) * 0.7
    tones = np.zeros_like(t)
    for k, fq in enumerate((1318.5, 1760.0) if up else (1760.0, 1318.5)):
        i = int((0.08 + k * 0.07) * SR)
        tt = t[: len(t) - i]
        tones[i:] += np.sin(2 * np.pi * fq * tt) * np.exp(-tt * 30) * np.clip(tt / 0.003, 0, 1) * 0.35
    return norm(thump + tones, 0.45)


def berth_ambience(dur=26.0):
    """Crew Berthing at night (loopable): the air handlers' low wash, the reactor felt faintly through the deck,
    a hull creak now and then, the far tick of the ship settling — quieter and softer than the bridge."""
    t = t_(dur)
    air = lp(hp(rng.normal(0, 1, len(t)), 30), 240, order=4) * (1 + 0.2 * np.sin(2 * np.pi * t / 11.0))
    hum = (np.sin(2 * np.pi * 50 * t) * 0.12 + np.sin(2 * np.pi * 23 * t) * 0.18) * (1 + 0.1 * np.sin(2 * np.pi * t / 7.0))
    creaks = np.zeros_like(t)
    for _ in range(int(dur / 6)):
        i = rng.integers(0, len(t) - SR)
        m = int(rng.uniform(0.3, 0.8) * SR)
        tt = np.arange(m) / SR
        f0 = rng.uniform(70, 140)
        creaks[i:i + m] += np.sin(2 * np.pi * (f0 + 25 * np.sin(2 * np.pi * 3 * tt)) * tt) * np.sin(np.pi * tt / tt[-1]) * 0.12
    ticks = np.zeros_like(t)
    for _ in range(int(dur / 2.5)):
        i = rng.integers(0, len(t) - 2000)
        ticks[i:i + 2000] += hp(rng.normal(0, 1, 2000), 2500) * np.exp(-np.arange(2000) / 180.0) * 0.05
    x = air * 0.9 + hum + lp(creaks, 900) + ticks
    n = SR
    fade = np.linspace(0, 1, n)
    x[:n] = x[:n] * fade + x[-n:] * (1 - fade)
    return norm(x[:-n], 0.45)


def jam_static():
    """The sensors station when the Mandate's jammers come on: a burst of rasping noise sweeping through the
    receivers, the strobe's pulse in it, then settling to a hiss."""
    t = t_(2.2)
    noise = rng.normal(0, 1, len(t))
    sweep = np.sin(2 * np.pi * (300 + 2600 * t / t[-1]) * t)
    rasp = bp(noise, 900, 5200) * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 37 * t)))    # the strobe's chopping
    env = np.clip(t / 0.05, 0, 1) * (0.35 + 0.65 * np.exp(-t * 1.6))
    return norm((rasp * 0.8 + sweep * bp(noise, 200, 3000) * 0.3) * env, 0.5)


os.makedirs(OUT, exist_ok=True)
for name, fn in (("SW_Rail_Fire", rail_fire), ("SW_VLS_Launch", vls_launch), ("SW_Torpedo_Launch", lambda: vls_launch(True)),
                 ("SW_PD_Burst", pd_burst), ("SW_Catapult", catapult), ("SW_Console_Chirp", chirp), ("SW_Door_Chime", door_chime),
                 ("SW_Bridge_Ambience", bridge_ambience), ("SW_Door_Open", door), ("SW_Door_Close", lambda: door(False)), ("SW_Transit", transit),
                 ("SW_Sparks", sparks), ("SW_Falcon_Engine", falcon_engine), ("SW_Lock_Beep", lock_beep), ("SW_Lock_Solid", lock_solid),
                 ("SW_Missile_Warning", missile_warning), ("SW_Entry_Plasma", entry_plasma),
                 # last: new sounds must not shift the random stream of the ones above
                 ("SW_Pod_Launch", pod_launch), ("SW_Pod_Hum", pod_hum), ("SW_Breach_Felt", breach_felt),
                 ("SW_Pad_Up", pad), ("SW_Pad_Down", lambda: pad(False)), ("SW_Berth_Ambience", berth_ambience),
                 ("SW_Jam_Static", jam_static)):
    sf.write(os.path.join(OUT, name + ".wav"), fn().astype(np.float32), SR, subtype="PCM_16")
print("SHIP_SOUNDS_OK", sorted(f for f in os.listdir(OUT) if f.endswith(".wav")))
