"""The bridge's sensor cues, synthesised (no third-party audio). In the vacuum nothing is heard from outside the hull (docs/STILE.md §9): what the
bridge hears of a battle out there is its own consoles. A warship's death, which the sensors see as a flash, a cloud of debris and a reactor's
pulse, is rendered on the bridge's speakers as a deep swell: a console's sonification, not the sound of the explosion (there is none).

    uv run --with numpy --with soundfile --with scipy python tools/art/battle_cues.py -> art/_cache/audio/SW_Sensor_Kill.wav
    tools/ue.py py "SRC=None; exec(open('tools/ue_scripts/import_battle_cues.py').read())"

Played by AstraViewscreen.cpp (the director sees a ship destroyed): louder and longer for a capital ship, quieter the farther it was.
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


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def norm(x, peak=0.9):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def sensor_kill() -> np.ndarray:
    """A deep swell with a soft attack, a body that falls in pitch, a crackle of debris returns and a long tail: 3.2 s."""
    t = t_(3.2)
    attack = 1.0 - np.exp(-t / 0.06)
    body_env = attack * np.exp(-t / 1.05)
    # the reactor's pulse: a sub tone falling from 62 to 38 Hz, with its octave quieter
    f = 38.0 + 24.0 * np.exp(-t / 0.7)
    phase = 2 * np.pi * np.cumsum(f) / SR
    body = (np.sin(phase) + 0.35 * np.sin(2 * phase + 0.4)) * body_env
    # the cloud: low noise swelling and falling
    cloud = lp(rng.standard_normal(t.size), 220.0, 4) * (attack * np.exp(-t / 0.75)) * 2.2
    # the debris returns: sparse filtered clicks for the first second and a half, thinning out
    clicks = np.zeros(t.size)
    for _ in range(70):
        at = rng.uniform(0.05, 1.6) ** 1.6
        i = int(at * SR)
        if i < t.size - 400:
            clicks[i:i + 400] += rng.uniform(0.2, 1.0) * np.exp(-np.arange(400) / 60.0) * rng.choice([-1.0, 1.0])
    clicks = bp(clicks, 900.0, 3800.0, 2) * 0.25
    # the console's tone underneath: a faint band of the sensor rendering, so it reads as the bridge's speakers, not as air
    console = bp(rng.standard_normal(t.size), 1400.0, 1700.0, 2) * 0.05 * np.exp(-t / 0.5)
    x = body * 1.0 + cloud * 0.55 + clicks + console
    # fade the very end
    x *= np.clip((3.2 - t) / 0.4, 0.0, 1.0)
    return norm(x, 0.85)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "SW_Sensor_Kill.wav")
    sf.write(path, sensor_kill().astype(np.float32), SR, subtype="PCM_16")
    print("wrote", path)


if __name__ == "__main__":
    main()
