"""Textures of the v3 ships (procedural, CC0-free of third-party content): the wear mask the hull material breaks its paint with and
the damage decal atlas.

  T_ShipWear_M      2048 x 2048, seamless, linear RGBA (a 16 m tile at the material's default scale):
                      R  chip breakup: cellular flakes + fractal noise (0.5 = neutral); the paint chips where wear + (R - 0.5) crosses a threshold
                      G  scratches: thin lines at random angles (1 = a scratch)
                      B  grime: soft blotches and stains (1 = dirty)
                      A  streaks: long thin smears along the tile's v axis (the flow of soot and coolant)
  T_ShipDamage_A    4096 x 2048 = a 4 x 2 atlas of 1024 cells, linear RGBA, the game's damage decals:
                      R soot (how burnt), G embers (glowing cracks while hot), B breach (torn-through centre, black), A opacity
                      cells (row 0): 0 burn  1 hole  2 torn plate  3 impact star
                      cells (row 1): 4 strafing run  5 melt  6 gouges  7 blast scorch
  T_ShipDamage_N    the same atlas as a normal map (DirectX, +G down): the rims of the holes, the dents, the cracks

Run: uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/ship3_textures.py [out_dir]
Default output art/_cache/textures/ (gitignored; the Unreal script tools/ue_scripts/make_ship_materials_v3.py imports from there).
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", "art", "_cache", "textures")
N = 2048


# ---------------------------------------------------------------------------------------------------------- seamless tools
def blur(a: np.ndarray, sigma_px: float) -> np.ndarray:
    """Seamless gaussian blur (FFT on the torus)."""
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g)).astype(np.float32)


def blur_aniso(a: np.ndarray, sx: float, sy: float) -> np.ndarray:
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * (np.pi ** 2) * ((sx * fx) ** 2 + (sy * fy) ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g)).astype(np.float32)


def norm01(a: np.ndarray) -> np.ndarray:
    a = a - a.min()
    return a / (a.max() + 1e-9)


def fractal(rng, n: int, octaves) -> np.ndarray:
    out = np.zeros((n, n), np.float32)
    for sigma, amp in octaves:
        w = blur(rng.standard_normal((n, n)).astype(np.float32), sigma)
        out += amp * w / (w.std() + 1e-9)
    return norm01(out)


def worley(rng, n: int, cells: int) -> np.ndarray:
    """Seamless cellular noise F1 distance (0 at a feature point) on an n x n torus with cells x cells feature points, in cell units."""
    pts = rng.random((cells, cells, 2)).astype(np.float32)
    u = (np.arange(n) + 0.5) / n * cells
    ci = np.floor(u).astype(int)
    fu = (u - ci).astype(np.float32)
    best = np.full((n, n), 9.0, np.float32)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            pj = (ci + dj) % cells
            pi = (ci + di) % cells
            fx = pts[pj[:, None], pi[None, :], 0] + di                # feature point of the neighbour cell, relative to the pixel's cell
            fy = pts[pj[:, None], pi[None, :], 1] + dj
            d = np.sqrt((fx - fu[None, :]) ** 2 + (fy - fu[:, None]) ** 2)
            np.minimum(best, d, out=best)
    return best


def wear_texture(rng) -> np.ndarray:
    n = N
    # R: flakes (small dark/bright cells) mixed with fractal noise, centred on 0.5
    w1 = worley(rng, n, 40)
    flakes = 1.0 - np.clip(w1 * 1.1, 0, 1)                                   # bright at each feature point
    fr = fractal(rng, n, ((90, 1.0), (32, 0.6), (11, 0.35), (4, 0.2)))
    chip = 0.5 + 0.55 * (fr - 0.5) + 0.35 * (flakes - 0.35)
    chip = np.clip(chip, 0, 1)
    # G: scratches
    sc = np.zeros((n, n), np.float32)
    for _ in range(420):
        x0, y0 = rng.random(2) * n
        a = rng.uniform(0, np.pi)
        ln = rng.uniform(0.04, 0.5) * n
        m = int(ln)
        t = np.linspace(0, ln, m)
        xx = ((x0 + t * np.cos(a)) % n).astype(int)
        yy = ((y0 + t * np.sin(a)) % n).astype(int)
        v = rng.uniform(0.5, 1.0)
        sc[yy, xx] = np.maximum(sc[yy, xx], v)
    sc = np.clip(blur(sc, 0.9) * 5.0, 0, 1)
    # B: grime blotches and stains
    gr = fractal(rng, n, ((160, 1.0), (60, 0.7), (22, 0.4)))
    gr = np.clip((gr - 0.35) * 1.8, 0, 1)
    # A: streaks along v (image y): noise stretched vertically
    st = blur_aniso(rng.standard_normal((n, n)).astype(np.float32), 1.4, 90.0)
    st = norm01(st)
    st = np.clip((st - 0.42) * 2.4, 0, 1)
    return np.stack([chip, sc, gr, st], axis=-1)


# --------------------------------------------------------------------------------------------------------------- damage
def vnoise(n: int, cells: int, seed: int) -> np.ndarray:
    r = np.random.default_rng(seed)
    g = r.random((cells + 1, cells + 1))
    x = np.linspace(0, cells, n, endpoint=False)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a, b, c, d = g[i][:, i], g[i + 1][:, i], g[i][:, i + 1], g[i + 1][:, i + 1]
    fy, fx = f[:, None], f[None, :]
    return (a * (1 - fy) + b * fy) * (1 - fx) + (c * (1 - fy) + d * fy) * fx


def fbm(n: int, base: int, octaves: int, seed: int) -> np.ndarray:
    out = np.zeros((n, n))
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        out += vnoise(n, base * 2 ** o, seed + o) * amp
        tot += amp
        amp *= 0.5
    return out / tot


C = 1024
Y, X = np.mgrid[0:C, 0:C] / (C - 1) * 2 - 1
R = np.sqrt(X * X + Y * Y)
ANG = np.arctan2(Y, X)


def soft(a: np.ndarray, edge: float, width: float) -> np.ndarray:
    return np.clip((edge - a) / width, 0.0, 1.0)


def cell_burn(rng, seed: int):
    warp = fbm(C, 3, 5, seed) - 0.5
    edge = 0.62 + 0.22 * np.sin(ANG * 3 + 1.3) * 0.3 + warp * 0.55
    burn = soft(R, np.maximum(edge, 0.15), np.maximum(edge, 0.15) * 0.6)
    streak = np.zeros_like(R)
    for k in range(15):
        a0 = rng.uniform(-np.pi, np.pi)
        wd = rng.uniform(0.03, 0.09)
        ln = rng.uniform(0.55, 0.95)
        d = np.abs(np.angle(np.exp(1j * (ANG - a0))))
        streak += np.clip(1 - d / wd, 0, 1) * np.clip(1 - R / ln, 0, 1) * rng.uniform(0.4, 0.9)
    detail = fbm(C, 16, 4, seed + 11)
    alpha = np.clip(burn * (0.75 + 0.35 * detail) + streak * 0.55 * (0.6 + 0.4 * detail), 0, 1) * np.clip((1 - R) * 4, 0, 1)
    soot = np.clip(0.35 + 0.65 * burn + 0.3 * (detail - 0.5), 0, 1)
    cr = np.abs(fbm(C, 10, 5, seed + 23) - 0.5)
    emb = np.clip(1 - cr / 0.035, 0, 1) * np.clip(1 - R / 0.45, 0, 1) ** 1.5
    height = -0.15 * burn
    return soot, emb, np.zeros_like(R), alpha, height


def cell_hole(rng, seed: int):
    """A breach: a torn-through centre with petals of peeled plate round it, glowing rim, soot fan."""
    jag = fbm(C, 12, 4, seed) - 0.5
    petals = 0.06 * np.sin(ANG * 7 + rng.uniform(0, 6)) + 0.05 * np.sin(ANG * 11 + rng.uniform(0, 6))
    hole_r = 0.20 + petals + 0.16 * jag
    breach = np.clip((hole_r - R) / 0.015, 0, 1)
    rim = np.clip(1 - np.abs(R - hole_r) / 0.05, 0, 1)
    burn_r = 0.62 + 0.3 * (fbm(C, 4, 4, seed + 5) - 0.5)
    burn = soft(R, burn_r, burn_r * 0.7)
    fan = np.zeros_like(R)
    for k in range(9):
        a0 = rng.uniform(-np.pi, np.pi)
        wd = rng.uniform(0.05, 0.12)
        d = np.abs(np.angle(np.exp(1j * (ANG - a0))))
        fan += np.clip(1 - d / wd, 0, 1) * np.clip(1 - R / rng.uniform(0.6, 0.98), 0, 1) * rng.uniform(0.4, 0.9)
    detail = fbm(C, 18, 4, seed + 9)
    alpha = np.clip(np.maximum(burn * (0.8 + 0.3 * detail), fan * 0.6) + breach, 0, 1) * np.clip((1 - R) * 4, 0, 1)
    soot = np.clip(0.4 + 0.6 * burn + 0.3 * (detail - 0.5), 0, 1)
    emb = np.clip(rim * (0.5 + 0.8 * (fbm(C, 20, 4, seed + 3))), 0, 1) * (1 - breach * 0.5)
    height = np.where(R < hole_r, -1.0, 0.0) + 0.5 * rim * (R >= hole_r)
    return soot, emb, breach, alpha, height


def cell_torn(rng, seed: int):
    """A plate torn and curled back along a gash."""
    gx, gy = X * np.cos(0.5) + Y * np.sin(0.5), -X * np.sin(0.5) + Y * np.cos(0.5)
    jag = fbm(C, 14, 4, seed) - 0.5
    gash = np.clip((0.14 + 0.08 * jag + 0.05 * np.sin(gx * 9) - np.abs(gy)) / 0.02, 0, 1) * np.clip((0.85 - np.abs(gx)) / 0.05, 0, 1)
    flap = np.clip((0.30 - np.abs(gy - 0.16)) / 0.03, 0, 1) * np.clip((0.7 - np.abs(gx)) / 0.05, 0, 1) * (gy > 0.10)
    burn = soft(np.sqrt(gx ** 2 * 0.5 + gy ** 2 * 1.6), 0.55, 0.4)
    detail = fbm(C, 18, 4, seed + 9)
    alpha = np.clip(burn * (0.7 + 0.4 * detail) + gash + flap * 0.5, 0, 1) * np.clip((1 - R) * 4, 0, 1)
    soot = np.clip(0.3 + 0.7 * burn + 0.3 * (detail - 0.5), 0, 1)
    emb = np.clip(gash * (0.4 + 0.9 * fbm(C, 22, 4, seed + 3)) * 0.8, 0, 1)
    height = -gash + 0.8 * flap
    return soot, emb, gash * 0.85, alpha, height


def cell_star(rng, seed: int):
    """An impact: a crater with radial cracks and a scorched ring."""
    crater = np.clip((0.13 - R) / 0.03, 0, 1)
    rays = np.zeros_like(R)
    for k in range(18):
        a0 = rng.uniform(-np.pi, np.pi)
        wd = 0.012 + rng.uniform(0, 0.012)
        d = np.abs(np.angle(np.exp(1j * (ANG - a0))))
        rays = np.maximum(rays, np.clip(1 - d / wd, 0, 1) * np.clip(1 - R / rng.uniform(0.3, 0.95), 0, 1))
    burn = soft(R, 0.34 + 0.08 * (fbm(C, 5, 4, seed) - 0.5), 0.2)
    detail = fbm(C, 20, 4, seed + 9)
    alpha = np.clip(burn * (0.8 + 0.3 * detail) + rays * 0.9 + crater, 0, 1) * np.clip((1 - R) * 4, 0, 1)
    soot = np.clip(0.4 + 0.6 * burn, 0, 1)
    emb = np.clip(rays * 0.8 + crater * 0.5, 0, 1) * np.clip(1 - R / 0.6, 0, 1)
    height = -crater * 0.8 - rays * 0.35
    return soot, emb, crater * 0.6, alpha, height


def cell_strafe(rng, seed: int):
    """A run of cannon hits: pits along a line, each with a small scorch."""
    alpha = np.zeros_like(R)
    soot = np.zeros_like(R)
    emb = np.zeros_like(R)
    br = np.zeros_like(R)
    height = np.zeros_like(R)
    n = 13
    for k in range(n):
        t = -0.85 + 1.7 * k / (n - 1)
        cx = t
        cy = 0.05 * np.sin(k * 1.7) + rng.uniform(-0.03, 0.03)
        r = rng.uniform(0.035, 0.07)
        d = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        pit = np.clip((r - d) / (r * 0.35), 0, 1)
        halo = np.clip((r * 3.0 - d) / (r * 2.0), 0, 1)
        alpha = np.maximum(alpha, np.clip(halo * 0.85 + pit, 0, 1))
        soot = np.maximum(soot, 0.4 + 0.6 * halo)
        emb = np.maximum(emb, pit * 0.7)
        br = np.maximum(br, pit * 0.7)
        height -= pit * 0.9
    alpha *= np.clip((1 - R) * 4, 0, 1)
    return np.clip(soot, 0, 1), emb, br, np.clip(alpha, 0, 1), height


def cell_melt(rng, seed: int):
    """A patch where the plate ran: rippled, glossy, dark."""
    n1 = fbm(C, 4, 5, seed)
    mask = soft(R + (n1 - 0.5) * 0.6, 0.62, 0.35)
    ripple = 0.5 + 0.5 * np.sin((R + (n1 - 0.5) * 0.4) * 60.0)
    core = soft(R + (n1 - 0.5) * 0.5, 0.28, 0.2)
    alpha = np.clip(mask * (0.85 + 0.2 * ripple), 0, 1) * np.clip((1 - R) * 4, 0, 1)
    soot = np.clip(0.55 + 0.45 * core, 0, 1)
    emb = np.clip(core * (0.3 + 0.7 * (fbm(C, 12, 4, seed + 2))), 0, 1) * 0.7
    height = -0.3 * mask + 0.25 * ripple * mask
    return soot, emb, core * 0.35, alpha, height


def cell_gouge(rng, seed: int):
    """Long scratches and gouges where something dragged along the hull."""
    alpha = np.zeros_like(R)
    height = np.zeros_like(R)
    for k in range(9):
        a0 = rng.uniform(-0.5, 0.5)
        off = rng.uniform(-0.7, 0.7)
        w = rng.uniform(0.008, 0.03)
        d = np.abs(-X * np.sin(a0) + Y * np.cos(a0) - off)
        ln = np.clip((0.95 - np.abs(X * np.cos(a0) + Y * np.sin(a0))) / 0.08, 0, 1)
        line = np.clip(1 - d / w, 0, 1) * ln
        alpha = np.maximum(alpha, line)
        height -= line * rng.uniform(0.4, 1.0)
    soot = np.clip(0.3 + 0.7 * alpha, 0, 1)
    emb = alpha * 0.15
    return soot, emb, np.zeros_like(R), np.clip(alpha, 0, 1), height


def cell_blast(rng, seed: int):
    """A big soft scorch: a blast that licked along the hull, with long streaks away from the centre."""
    n1 = fbm(C, 3, 5, seed) - 0.5
    burn = soft(R + n1 * 0.5, 0.75, 0.6)
    streak = np.zeros_like(R)
    for k in range(24):
        a0 = rng.uniform(-np.pi, np.pi)
        wd = rng.uniform(0.02, 0.07)
        d = np.abs(np.angle(np.exp(1j * (ANG - a0))))
        streak += np.clip(1 - d / wd, 0, 1) * np.clip(1 - R / rng.uniform(0.5, 1.0), 0, 1) * rng.uniform(0.3, 0.8)
    detail = fbm(C, 14, 4, seed + 4)
    alpha = np.clip(burn * (0.6 + 0.4 * detail) + streak * 0.5, 0, 1) * np.clip((1 - R) * 3, 0, 1)
    soot = np.clip(0.45 + 0.55 * burn, 0, 1)
    emb = np.clip(soft(R, 0.22, 0.2) * fbm(C, 18, 4, seed + 8), 0, 1) * 0.5
    return soot, emb, np.zeros_like(R), alpha, -0.05 * burn


CELLS = (cell_burn, cell_hole, cell_torn, cell_star, cell_strafe, cell_melt, cell_gouge, cell_blast)


def height_to_normal(h: np.ndarray, strength: float) -> np.ndarray:
    dhx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dhy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    nrm = np.stack([-dhx * strength, -dhy * strength, np.ones_like(h)], axis=-1)     # DirectX: +G down the image
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    return nrm * 0.5 + 0.5


def damage_atlas():
    rng = np.random.default_rng(2491)
    A = np.zeros((2 * C, 4 * C, 4), np.float32)
    Nn = np.zeros((2 * C, 4 * C, 3), np.float32)
    for i, fn in enumerate(CELLS):
        soot, emb, br, alpha, height = fn(rng, 100 + 17 * i)
        cx, cy = (i % 4) * C, (i // 4) * C
        A[cy:cy + C, cx:cx + C] = np.stack([soot, emb, br, alpha], axis=-1)
        h = blur(np.asarray(height, np.float32), 1.2)
        Nn[cy:cy + C, cx:cx + C] = height_to_normal(h, 6.0 if i not in (5, 7) else 2.5)
        # the border of each cell is flat and empty so neighbours never bleed in
        A[cy:cy + C, cx:cx + 3, 3] = 0
        A[cy:cy + C, cx + C - 3:cx + C, 3] = 0
    return A, Nn


def save_png(arr: np.ndarray, path: str, mode: str) -> None:
    img = Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8), mode)
    img.save(path, optimize=True)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(31)
    w = wear_texture(rng)
    save_png(w, os.path.join(OUT, "T_ShipWear_M.png"), "RGBA")
    A, Nn = damage_atlas()
    save_png(A, os.path.join(OUT, "T_ShipDamage_A.png"), "RGBA")
    save_png(Nn, os.path.join(OUT, "T_ShipDamage_N.png"), "RGB")
    # a contact sheet for the eyes (not imported)
    sheet = np.concatenate([A[..., 3], Nn[..., 0]], axis=0)
    Image.fromarray((sheet * 255).astype(np.uint8), "L").resize((1024, 1024)).save(os.path.join(OUT, "_preview_ship_damage.png"))
    print("SHIP3_TEXTURES_OK", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
