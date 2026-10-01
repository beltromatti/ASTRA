#!/usr/bin/env python3
"""Textures of the war's visual effects (AstraWarFX, materials in tools/ue_scripts/make_war_fx.py), and preview sheets to look at.

  uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_textures.py [--preview docs/progressi/vfx]

Writes into art/_cache/fx/ (not in git):
  T_WAR_Fire.png    2048x2048, 8x8 frames of 256 px, an exploding fireball from its first white instant to the last red embers.
                    R = temperature (0 cold .. 1 white-hot; the material maps it to colour), G = density, B = fine detail.
  T_WAR_Smoke.png   2048x2048, 8x8 frames: a billowing puff of smoke. R = density, G = light (the side facing the star is lit),
                    B = ember glow (hot spots inside it that die first).
Every frame lives inside the disc inscribed in its square (the effects draw them on a sphere seen as a disc: nothing is sampled outside
it) and fades to nothing before the disc's rim, so a frame never shows a hard edge, and two neighbours never bleed into each other.

With --preview it also writes contact sheets (the textures through the material's own colour ramp) and the checks of the shader maths
used by the shield, the darts and the beams, into the folder given.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "art", "_cache", "fx")
FRAME = 256
GRID = 8


# ------------------------------------------------------------------------------------------------------------------ noise
def _hash(ix, iy, iz, seed):
    h = (ix.astype(np.int64) * 374761393 + iy.astype(np.int64) * 668265263 + iz.astype(np.int64) * 2147483629 + seed * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF
    return (h & 0xFFFFFF).astype(np.float64) / float(0xFFFFFF)


def _fade(t):
    return t * t * t * (t * (t * 6 - 15) + 10)


def value3(x, y, z, seed=0):
    """3D value noise in [0,1] (trilinear on a hashed lattice, quintic fade)."""
    x0, y0, z0 = np.floor(x), np.floor(y), np.floor(z)
    fx, fy, fz = _fade(x - x0), _fade(y - y0), _fade(z - z0)
    ix, iy, iz = x0.astype(np.int64), y0.astype(np.int64), z0.astype(np.int64)

    def h(dx, dy, dz):
        return _hash(ix + dx, iy + dy, iz + dz, seed)

    c00 = h(0, 0, 0) * (1 - fx) + h(1, 0, 0) * fx
    c10 = h(0, 1, 0) * (1 - fx) + h(1, 1, 0) * fx
    c01 = h(0, 0, 1) * (1 - fx) + h(1, 0, 1) * fx
    c11 = h(0, 1, 1) * (1 - fx) + h(1, 1, 1) * fx
    c0 = c00 * (1 - fy) + c10 * fy
    c1 = c01 * (1 - fy) + c11 * fy
    return c0 * (1 - fz) + c1 * fz


def fbm3(x, y, z, octaves=5, seed=0, lac=2.03, gain=0.5):
    total, amp, norm = np.zeros_like(x), 0.5, 0.0
    for o in range(octaves):
        total += amp * value3(x, y, z, seed + 17 * o)
        norm += amp
        x, y, z, amp = x * lac + 5.2, y * lac + 1.3, z * lac + 9.7, amp * gain
    return total / norm


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def grid():
    y, x = np.mgrid[0:FRAME, 0:FRAME]
    return (x + 0.5) / FRAME * 2 - 1, (y + 0.5) / FRAME * 2 - 1


# ------------------------------------------------------------------------------------------------------------------ the fireball
def fire_frame(t: float, seed: int = 3) -> np.ndarray:
    """One frame of the fireball at t in [0,1]: float32 (FRAME, FRAME, 3): temperature, density, detail."""
    x, y = grid()
    r = np.hypot(x, y)
    z = t * 1.7 + seed
    # the gas is thrown outward and turns over: the field is warped more and more as it ages
    wx = fbm3(x * 1.7 + 3.1, y * 1.7 - 1.7, z, 4, seed)
    wy = fbm3(x * 1.7 - 5.2, y * 1.7 + 2.3, z + 7.0, 4, seed + 5)
    amt = 0.16 + 0.34 * t
    px, py = x + (wx - 0.5) * 2.0 * amt, y + (wy - 0.5) * 2.0 * amt
    rw = np.hypot(px, py)
    # billows: puffy cauliflower structure at two scales, ridges where the gas folds
    b1 = 1.0 - np.abs(2.0 * fbm3(px * 2.3 + 1.0, py * 2.3, z * 1.2, 4, seed + 2) - 1.0)
    b2 = 1.0 - np.abs(2.0 * fbm3(px * 5.2, py * 5.2 + 3.0, z * 1.9, 3, seed + 4) - 1.0)
    d = 0.62 * b1 + 0.38 * b2
    hot_n = fbm3(px * 3.1 - 2.0, py * 3.1 + 5.0, z * 1.5, 4, seed + 7)
    # the envelope swells fast and slows; its edge bulges where the billows are
    R = 0.20 + 0.62 * (1.0 - (1.0 - t) ** 2.3)
    edge = R * (0.80 + 0.70 * (d - 0.5) * (0.55 + 0.9 * t) + 0.25 * (b1 - 0.5))
    rn = rw / np.maximum(edge, 1e-3)
    dens = smoothstep(1.04, 0.62, rn) * (0.40 + 1.0 * d)
    # temperature: hot inside, cooling with the radius and with time; hot pockets of fresher gas
    cool = (1.0 - t) ** 1.1
    T = ((1.0 - np.clip(rn, 0, 1)) ** 1.5 * 1.25 + 0.55 * (hot_n - 0.45) * (1.0 - np.clip(rn, 0, 1)) + 0.12 * (d - 0.5)) * cool * 1.15
    # the first instants are a white ball
    first = np.exp(-t * 11.0)
    T = np.maximum(T, first * smoothstep(1.0, 0.3, rn))
    dens = np.maximum(dens, first * smoothstep(1.0, 0.4, rn))
    # as it ages the cloud breaks into filaments with dark gaps between them
    holes = (1.0 - t * 0.75) + t * 0.75 * smoothstep(0.28, 0.72, d + 0.15 * (hot_n - 0.5))
    dens = dens * holes
    T = np.clip(T, 0, 1)
    dens = np.clip(dens, 0, 1) * (1.0 - smoothstep(0.62, 1.0, t))
    rim = smoothstep(0.985, 0.86, r)                      # nothing at the rim of the disc
    out = np.stack([T * rim, dens * rim, np.clip(d, 0, 1) * rim], axis=-1)
    return out.astype(np.float32)


def blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur of a 2D array by FFT (the frame is zero at its borders, so wrapping does not matter)."""
    ky = np.fft.fftfreq(a.shape[0])[:, None]
    kx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * (math.pi * sigma) ** 2 * (kx ** 2 + ky ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def smoke_frame(t: float, seed: int = 8) -> np.ndarray:
    """One frame of a puff of smoke at t: density, light, embers. Soft, voluminous, slowly turning over."""
    x, y = grid()
    r = np.hypot(x, y)
    z = t * 0.7 + seed
    wx = fbm3(x * 1.1 + 2.0, y * 1.1 + 8.1, z, 3, seed)
    wy = fbm3(x * 1.1 - 6.0, y * 1.1 - 3.3, z + 4.0, 3, seed + 3)
    amt = 0.26 + 0.14 * t
    px, py = x + (wx - 0.5) * 2.0 * amt, y + (wy - 0.5) * 2.0 * amt
    rw = np.hypot(px, py)
    d1 = fbm3(px * 1.9 + 5.0, py * 1.9, z * 1.1, 4, seed + 11)
    d2 = fbm3(px * 4.2, py * 4.2 + 3.0, z * 1.5, 3, seed + 31)
    R = 0.55 + 0.38 * (1.0 - (1.0 - t) ** 1.8)
    edge = R * (0.85 + 0.60 * (d1 - 0.5))
    body = smoothstep(edge * 1.08, edge * 0.15, rw)
    vol = body * (0.10 + 1.15 * np.clip(d1, 0, 1) ** 1.5) * (0.80 + 0.40 * d2)     # the volume of the cloud: billows inside it, not a flat plate
    dens = np.clip(vol * 1.1, 0, 0.92)
    # light from the upper left, taken from a blurred copy of the volume (a soft height field): billows get a lit side and a dark one
    h = blur(vol, 5.0)
    gy, gx = np.gradient(h)
    lit = np.clip(0.50 - (gx * 0.75 + gy * 0.75) * 30.0, 0.05, 1.0) * (0.78 + 0.22 * d2)
    embers = np.clip(np.exp(-((rw / (R * 0.55)) ** 2)) * (d1 - 0.25) * 3.2, 0, 1) * (1.0 - smoothstep(0.0, 0.55, t)) * body
    rim = smoothstep(0.985, 0.84, r)
    out = np.stack([dens * rim, lit * rim, embers * rim], axis=-1)
    return out.astype(np.float32)


def sheet(fn, frames: int = GRID * GRID) -> np.ndarray:
    img = np.zeros((GRID * FRAME, GRID * FRAME, 3), np.float32)
    for f in range(frames):
        t = f / (frames - 1)
        img[(f // GRID) * FRAME:(f // GRID + 1) * FRAME, (f % GRID) * FRAME:(f % GRID + 1) * FRAME] = fn(t)
    return img


def to_png(a: np.ndarray, path: str) -> None:
    rgba = np.concatenate([np.clip(a, 0, 1), np.ones(a.shape[:2] + (1,), np.float32)], axis=-1)
    Image.fromarray((rgba * 255 + 0.5).astype(np.uint8), "RGBA").save(path, optimize=True)


# ------------------------------------------------------------------------------------------------------------------ previews
def fire_colour(tex: np.ndarray, col=(1.0, 0.5, 0.16)) -> np.ndarray:
    """The material's ramp: temperature -> colour, as M_WAR_Fire does it (see make_war_fx.py). col tints the middle of the ramp."""
    T, dens = tex[..., 0], tex[..., 1]
    c = np.asarray(col, np.float32)
    dark = c * np.asarray([0.55, 0.12, 0.02], np.float32)             # dull red
    hot = np.asarray([1.0, 0.93, 0.78], np.float32)                    # white-yellow
    a = smoothstep(0.05, 0.42, T)[..., None]
    b = smoothstep(0.50, 0.92, T)[..., None]
    rgb = dark * (1 - a) + c * a
    rgb = rgb * (1 - b) + hot * b
    return rgb * ((T ** 1.25) * 1.7 + 0.06)[..., None] * dens[..., None]


def tonemap(x: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    x = x * exposure
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1) ** (1 / 2.2)


def preview_sheets(folder: str, fire, smoke) -> None:
    os.makedirs(folder, exist_ok=True)
    if fire is not None:
        preview_fire(folder, fire)
    if smoke is not None:
        preview_smoke(folder, smoke)


def preview_fire(folder: str, fire: np.ndarray) -> None:
    img = tonemap(fire_colour(fire), 1.63)
    Image.fromarray((img * 255).astype(np.uint8)).resize((1024, 1024), Image.LANCZOS).save(os.path.join(folder, "fire_sheet.png"))
    # a few frames large, side by side
    pick = [0, 4, 9, 16, 26, 40, 54, 63]
    strip = np.concatenate([tonemap(fire_colour(fire[(f // GRID) * FRAME:(f // GRID + 1) * FRAME, (f % GRID) * FRAME:(f % GRID + 1) * FRAME]), 1.63) for f in pick], axis=1)
    Image.fromarray((strip * 255).astype(np.uint8)).save(os.path.join(folder, "fire_frames.png"))


def preview_smoke(folder: str, smoke: np.ndarray) -> None:
    # the smoke on a dark star field, lit from the upper left
    dens, lit, emb = smoke[..., 0], smoke[..., 1], smoke[..., 2]
    base = np.asarray([0.16, 0.15, 0.14], np.float32)
    rgb = base * (0.25 + 0.75 * lit)[..., None] * 38.0 / 116.0 * 3.0 + np.asarray([1.0, 0.42, 0.12], np.float32) * emb[..., None] * 0.5
    bg = np.zeros_like(rgb) + 0.02
    out = bg * (1 - dens[..., None]) + rgb * dens[..., None]
    Image.fromarray((np.clip(out, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)).resize((1024, 1024), Image.LANCZOS).save(os.path.join(folder, "smoke_sheet.png"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", default="", help="folder for the contact sheets and shader checks")
    ap.add_argument("--only", default="", help="fire | smoke | shaders")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    fire = smoke = None
    if a.only in ("", "fire"):
        t0 = time.time()
        fire = sheet(fire_frame)
        to_png(fire, os.path.join(OUT, "T_WAR_Fire.png"))
        print(f"T_WAR_Fire.png {time.time() - t0:.0f} s")
    if a.only in ("", "smoke"):
        t0 = time.time()
        smoke = sheet(smoke_frame)
        to_png(smoke, os.path.join(OUT, "T_WAR_Smoke.png"))
        print(f"T_WAR_Smoke.png {time.time() - t0:.0f} s")
    if a.preview:
        preview_sheets(a.preview, fire, smoke)
        if a.only in ("", "shaders"):
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            try:
                import war_fx_shader_preview as SP
            except ImportError:
                SP = None
            if SP:
                SP.render_all(a.preview)
    print("WAR_FX_TEXTURES_OK")


if __name__ == "__main__":
    main()
