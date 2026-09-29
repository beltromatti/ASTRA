"""A battle scar for the hulls (a decal where a hit lands), procedural and seamless at the edges:

  T_FX_Scorch (RGBA, linear data):
    R  soot: how burnt the plating is (0 bare metal showing through, 1 deep soot)
    G  embers: the jagged cracks still glowing while the hit is fresh (the game cools them)
    B  breach: the torn centre of a heavy hit (black, with a molten rim while hot)
    A  where the decal paints at all (an irregular burn with spatter and blast streaks)

Run: uv run --with numpy --with pillow python tools/art/scorch.py -> art/_cache/fx/T_FX_Scorch.png
"""
import os

import numpy as np
from PIL import Image

N = 1024
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "art", "_cache", "fx")
rng = np.random.default_rng(71)


def value_noise(n, cells, seed):
    """Smooth value noise on an n x n grid with `cells` lattice cells (bicubic-ish via smoothstep)."""
    r = np.random.default_rng(seed)
    g = r.random((cells + 1, cells + 1))
    x = np.linspace(0, cells, n, endpoint=False)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = g[i][:, i]
    b = g[i + 1][:, i]
    c = g[i][:, i + 1]
    d = g[i + 1][:, i + 1]
    fy, fx = f[:, None], f[None, :]
    return (a * (1 - fy) + b * fy) * (1 - fx) + (c * (1 - fy) + d * fy) * fx


def fbm(n, base, octaves, seed):
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += value_noise(n, base * 2 ** o, seed + o) * amp
        tot += amp
        amp *= 0.5
    return out / tot


y, x = np.mgrid[0:N, 0:N] / (N - 1) * 2 - 1
r = np.sqrt(x * x + y * y)
ang = np.arctan2(y, x)
warp = fbm(N, 3, 5, 3) - 0.5
edge = 0.62 + 0.22 * np.sin(ang * 3 + 1.3) * 0.3 + warp * 0.55          # an irregular rim
burn = np.clip(1 - (r / np.maximum(edge, 0.15)) ** 1.6, 0, 1)
# blast streaks radiating from the centre
streak = np.zeros_like(r)
for k in range(15):
    a0 = rng.uniform(-np.pi, np.pi)
    width = rng.uniform(0.03, 0.09)
    length = rng.uniform(0.55, 0.95)
    d = np.abs(np.angle(np.exp(1j * (ang - a0))))
    streak += np.clip(1 - d / width, 0, 1) * np.clip(1 - r / length, 0, 1) * rng.uniform(0.4, 0.9)
# spatter: droplets thrown out beyond the rim
spatter = np.zeros_like(r)
for k in range(140):
    a0, d0 = rng.uniform(-np.pi, np.pi), rng.uniform(0.35, 0.95)
    cx, cy, rad = d0 * np.cos(a0), d0 * np.sin(a0), rng.uniform(0.004, 0.02)
    spatter = np.maximum(spatter, np.clip(1 - np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / rad, 0, 1))
detail = fbm(N, 16, 4, 11)
alpha = np.clip(burn * (0.75 + 0.35 * detail) + streak * 0.55 * (0.6 + 0.4 * detail) + spatter * 0.8, 0, 1)
alpha *= np.clip((1 - r) * 4, 0, 1)                                       # never at the texture's border
soot = np.clip(0.35 + 0.65 * burn + 0.3 * (detail - 0.5), 0, 1)
# embers: thin bright cracks in the hot heart
cracks = np.abs(fbm(N, 10, 5, 23) - 0.5)
embers = np.clip(1 - cracks / 0.035, 0, 1) * np.clip(1 - r / 0.45, 0, 1) ** 1.5
embers = np.maximum(embers, np.clip(1 - r / 0.1, 0, 1) ** 2 * 0.3)       # a faint hot heart, not a star
# breach: the torn centre (a jagged hole painted black)
hole_edge = 0.12 + 0.14 * (fbm(N, 14, 3, 31) - 0.5) + 0.03 * np.sin(ang * 5 + 0.7)   # torn, not drilled
breach = np.clip((hole_edge - r) / 0.02, 0, 1)
img = np.stack([soot, embers, breach, alpha], axis=-1)
os.makedirs(OUT, exist_ok=True)
Image.fromarray((img * 255).astype(np.uint8), "RGBA").save(os.path.join(OUT, "T_FX_Scorch.png"))
print("SCORCH_OK", os.path.join(OUT, "T_FX_Scorch.png"))
