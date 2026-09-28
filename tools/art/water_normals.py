"""A tileable sea-surface normal map for New Ravenna's ocean: many small wind waves (a directional spectrum of sines,
wavelengths that repeat exactly on the tile), sharpened crests. DirectX normal convention (Unreal).

Run: uv run --with numpy --with pillow python tools/art/water_normals.py -> art/_cache/textures/T_Water_N.png
"""
import os

import numpy as np
from PIL import Image

N = 1024
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "art", "_cache", "textures")


def main() -> None:
    rng = np.random.default_rng(7)
    y, x = np.mgrid[0:N, 0:N] / N
    h = np.zeros((N, N))
    # integer wave numbers keep every component periodic on the tile; the wind blows along +x, spread +-50 degrees
    for _ in range(90):
        k = rng.integers(2, 40)
        ang = rng.normal(0.0, 0.55)
        kx, ky = int(round(k * np.cos(ang))), int(round(k * np.sin(ang)))
        if kx == 0 and ky == 0:
            continue
        amp = 1.0 / (kx * kx + ky * ky) ** 0.75
        ph = rng.uniform(0, 2 * np.pi)
        s = np.sin(2 * np.pi * (kx * x + ky * y) + ph)
        h += amp * (s - 0.35 * s * s)          # a trochoid-like sharper crest
    dhx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * N
    dhy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * N
    s = 0.006
    n = np.stack([-dhx * s, -dhy * s, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255 + 0.5).clip(0, 255).astype(np.uint8), "RGB").save(os.path.join(OUT, "T_Water_N.png"))
    print("WATER_OK", float(np.abs(n[..., :2]).mean()))


if __name__ == "__main__":
    main()
