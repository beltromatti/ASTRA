"""Original sounds of the small arms of the Aquila (ABBORDAGGI, docs/ABBORDAGGI.md), synthesised (no third-party audio): the service rifle (a suppressed
carbine in a steel corridor: a soft crack, a thump and the corridor's ring), the sidearm (sharper and louder), the click of an empty weapon, the
reloads (magazine out and in, the bolt), drawing from the holster, a round ticking on a bulkhead, the crack of one passing the head, the thud in a man.

Every one-shot ends in silence. Run: uv run --with numpy --with soundfile --with scipy python tools/art/weapon_sounds.py -> art/_cache/audio/SW_*.wav
Import: tools/ue.py py "ONLY=['SW_Rifle_Shot','SW_Pistol_Shot','SW_Gun_Dry','SW_Rifle_Reload','SW_Pistol_Reload','SW_Gun_Draw','SW_Bullet_Impact','SW_Bullet_Whiz','SW_Body_Hit']; exec(open('tools/ue_scripts/import_audio.py').read())"
"""
import os

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt

SR = 48000
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "audio")
rng = np.random.default_rng(1811)


def t_(sec):
    return np.arange(int(sec * SR)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, min(hi, SR / 2 - 200)], "band", fs=SR, output="sos"), x)


def norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def at(sig, start_s, total_s):
    """The signal placed in a silence of total_s seconds, beginning at start_s."""
    out = np.zeros(int(total_s * SR))
    i = int(start_s * SR)
    n = min(len(sig), len(out) - i)
    if n > 0:
        out[i:i + n] += sig[:n]
    return out


def noise(sec):
    return rng.normal(0, 1, int(sec * SR))


def corridor(x, strength=1.0):
    """A steel corridor round the shot: a few early reflections and a short dark tail."""
    out = x.copy()
    n = len(out)
    for delay_ms, g in ((14, 0.34), (31, 0.26), (57, 0.19), (93, 0.12), (141, 0.07)):
        d = int(delay_ms * SR / 1000)
        if d < n:
            out[d:] += lp(x[: n - d], 3200 - delay_ms * 8) * g * strength
    t = np.arange(n) / SR
    tail = lp(noise(n / SR), 1700) * np.exp(-t * 7.5) * np.convolve(np.abs(x), np.ones(int(0.02 * SR)) / (0.02 * SR), "same").max() * 0.5 * strength
    tail[: int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))
    return out + tail


def rifle_shot():
    """A suppressed rifle round: a soft crack, the thump of the action and the corridor's ring."""
    t = t_(0.9)
    crack = bp(noise(0.9), 1400, 6500) * np.exp(-t * 90) * 0.7
    thump = np.sin(2 * np.pi * np.cumsum(np.maximum(60, 190 * np.exp(-t * 38))) / SR) * np.exp(-t * 34) * 1.0
    puff = lp(noise(0.9), 3200) * np.exp(-t * 26) * 0.45
    action = bp(noise(0.9), 600, 2600) * np.exp(-np.maximum(t - 0.012, 0) * 70) * (t > 0.012) * 0.22      # the bolt working
    x = corridor(crack + thump + puff + action, 1.0)
    return norm(np.tanh(1.4 * x), 0.85)


def pistol_shot():
    """A 9 mm round from the sidearm: sharper, louder, a short crack with less body."""
    t = t_(0.8)
    crack = bp(noise(0.8), 900, 8000) * np.exp(-t * 130) * 1.0
    thump = np.sin(2 * np.pi * np.cumsum(np.maximum(95, 330 * np.exp(-t * 50))) / SR) * np.exp(-t * 48) * 0.8
    blast = lp(noise(0.8), 4200) * np.exp(-t * 55) * 0.6
    x = corridor(crack + thump + blast, 1.15)
    return norm(np.tanh(1.8 * x), 0.95)


def gun_dry():
    """The click of an empty weapon: the hammer or striker on nothing, a hard small tick and a ring."""
    t = t_(0.22)
    tick = bp(noise(0.22), 2200, 9000) * np.exp(-t * 520) * 1.0
    ring = np.sin(2 * np.pi * 1850 * t) * np.exp(-t * 90) * 0.4 + np.sin(2 * np.pi * 3100 * t) * np.exp(-t * 130) * 0.2
    second = at(bp(noise(0.05), 1500, 6000) * np.exp(-t[: int(0.05 * SR)] * 300) * 0.3, 0.045, 0.22)
    return norm(tick + ring + second, 0.8)


def magazine_out(total=0.4):
    """The catch, then the magazine sliding out of the well."""
    c = at(bp(noise(0.04), 1800, 7000) * np.exp(-t_(0.04) * 300) * 0.8, 0.0, total)
    slide = at(bp(noise(0.16), 500, 2400) * np.hanning(int(0.16 * SR)) * 0.4, 0.05, total)
    return c + slide


def magazine_in(total=0.4):
    """The magazine into the well: a slide and the thunk of it seating, a click."""
    slide = at(bp(noise(0.12), 600, 2600) * np.hanning(int(0.12 * SR)) * 0.35, 0.0, total)
    t = t_(0.2)
    thunk = at(np.sin(2 * np.pi * 150 * t) * np.exp(-t * 45) * 0.9 + bp(noise(0.2), 900, 5000) * np.exp(-t * 130) * 0.6, 0.11, total)
    click = at(bp(noise(0.03), 2500, 8000) * np.exp(-t_(0.03) * 400) * 0.5, 0.2, total)
    return slide + thunk + click


def bolt(total=0.5):
    """The bolt racked: a scrape back, a clack forward."""
    t = t_(0.14)
    back = at(bp(noise(0.14), 800, 4200) * np.hanning(len(t)) * 0.45, 0.0, total)
    t2 = t_(0.15)
    fwd = at(bp(noise(0.15), 1200, 7000) * np.exp(-t2 * 150) * 0.8 + np.sin(2 * np.pi * 760 * t2) * np.exp(-t2 * 70) * 0.4, 0.2, total)
    return back + fwd


def rifle_reload():
    total = 2.5
    x = at(magazine_out(), 0.2, total) + at(magazine_in(), 1.05, total) + at(bolt(), 1.7, total)
    x += at(lp(noise(0.5), 900) * np.hanning(int(0.5 * SR)) * 0.12, 0.0, total)                 # cloth and straps
    return norm(x, 0.7)


def pistol_reload():
    total = 2.0
    x = at(magazine_out(), 0.15, total) + at(magazine_in(), 0.95, total)
    t = t_(0.15)
    x += at(bp(noise(0.15), 1500, 8000) * np.exp(-t * 160) * 0.7 + np.sin(2 * np.pi * 900 * t) * np.exp(-t * 90) * 0.35, 1.45, total)    # the slide released
    x += at(lp(noise(0.4), 900) * np.hanning(int(0.4 * SR)) * 0.1, 0.0, total)
    return norm(x, 0.65)


def gun_draw():
    """A weapon drawn: the strap and the cloth, a small click of the holster's catch or the sling's clip."""
    total = 0.7
    cloth = at(lp(noise(0.3), 1300) * np.hanning(int(0.3 * SR)) * 0.4, 0.0, total)
    t = t_(0.06)
    click = at(bp(noise(0.06), 1800, 6500) * np.exp(-t * 220) * 0.7, 0.28, total)
    settle = at(np.sin(2 * np.pi * 210 * t_(0.12)) * np.exp(-t_(0.12) * 50) * 0.35, 0.4, total)
    return norm(cloth + click + settle, 0.6)


def bullet_impact():
    """A round ticking on a bulkhead: a hard tick and a short ping."""
    t = t_(0.35)
    tick = bp(noise(0.35), 2500, 11000) * np.exp(-t * 400) * 0.9
    ping = (np.sin(2 * np.pi * 2350 * t) * 0.35 + np.sin(2 * np.pi * 3720 * t) * 0.18) * np.exp(-t * 36)
    return norm(tick + ping, 0.7)


def bullet_whiz():
    """A round passing close: a crack and a thin zip that falls in pitch."""
    t = t_(0.3)
    crack = bp(noise(0.3), 2000, 9000) * np.exp(-t * 110) * 0.8
    sweep = np.sin(2 * np.pi * np.cumsum(np.maximum(1100, 5200 - 14000 * t)) / SR) * np.exp(-t * 14) * 0.35
    zip_ = bp(noise(0.3), 2500, 7000) * np.exp(-t * 18) * 0.25
    return norm(crack + sweep + zip_, 0.75)


def body_hit():
    """A round in a man: a dull thud."""
    t = t_(0.4)
    thud = np.sin(2 * np.pi * np.cumsum(np.maximum(48, 110 * np.exp(-t * 26))) / SR) * np.exp(-t * 20) * 1.0
    slap = lp(noise(0.4), 900) * np.exp(-t * 55) * 0.6
    return norm(thud + slap, 0.7)


SOUNDS = {
    "SW_Rifle_Shot": rifle_shot,
    "SW_Pistol_Shot": pistol_shot,
    "SW_Gun_Dry": gun_dry,
    "SW_Rifle_Reload": rifle_reload,
    "SW_Pistol_Reload": pistol_reload,
    "SW_Gun_Draw": gun_draw,
    "SW_Bullet_Impact": bullet_impact,
    "SW_Bullet_Whiz": bullet_whiz,
    "SW_Body_Hit": body_hit,
}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for name, fn in SOUNDS.items():
        x = fn().astype(np.float32)
        # a one-shot ends in silence: a few milliseconds of fade
        n = int(0.01 * SR)
        x[-n:] *= np.linspace(1, 0, n)
        sf.write(os.path.join(OUT, name + ".wav"), x, SR, subtype="PCM_16")
        print(f"{name}: {len(x) / SR:.2f} s, peak {np.max(np.abs(x)):.2f}")
    print("WEAPON_SOUNDS_OK", sorted(SOUNDS))
