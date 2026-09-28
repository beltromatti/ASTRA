"""Hull panel textures for the capital ships (a tile of 32 x 32 m of plating, seamless):

  T_HullPanels_N    normal map (DirectX convention, Unreal's): panel seams, fastener rows, hatches, vent grilles,
                    patch plates
  T_HullPanels_MSK  masks, linear: R = cavity and grime (1 open, darker in seams, recesses and dirt), G = roughness
                    offset (0.5 = none), B = tone of each plate (0.5 = none)

What makes a hull read as built out of hundreds of plates from a kilometre away is the tone of each plate and the dark
lines between them; the grooves, rivets and grilles are for the fighters that fly by at fifty metres.

Run: uv run --with numpy --with pillow python tools/art/hull_panels.py -> art/_cache/textures/T_HullPanels_*.png
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

N = 2048                  # pixels per tile
TILE_M = 32.0             # metres per tile
PX = N / TILE_M           # pixels per metre
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "art", "_cache", "textures")


def blur(a: np.ndarray, sigma_px: float) -> np.ndarray:
    """Seamless gaussian blur (FFT on the torus)."""
    fy = np.fft.fftfreq(a.shape[0])[:, None]
    fx = np.fft.fftfreq(a.shape[1])[None, :]
    g = np.exp(-2.0 * (np.pi * sigma_px) ** 2 * (fx * fx + fy * fy))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g)).astype(np.float32)


def fractal_noise(rng: np.random.Generator, octaves=((64, 1.0), (24, 0.5), (8, 0.25))) -> np.ndarray:
    """Seamless value-ish noise: white noise low-passed at several scales (sigma in pixels), normalised to 0..1."""
    out = np.zeros((N, N), np.float32)
    for sigma, amp in octaves:
        w = blur(rng.standard_normal((N, N)).astype(np.float32), sigma)
        out += amp * w / (w.std() + 1e-9)
    out -= out.min()
    return out / (out.max() + 1e-9)


def wrap_rect(a: np.ndarray, x0: int, y0: int, x1: int, y1: int, value, mode: str = "set") -> None:
    """Write value into the rectangle [x0, x1) x [y0, y1), wrapping around the tile."""
    ys = np.arange(y0, y1) % N
    xs = np.arange(x0, x1) % N
    ix = np.ix_(ys, xs)
    if mode == "set":
        a[ix] = value
    elif mode == "add":
        a[ix] += value
    elif mode == "min":
        a[ix] = np.minimum(a[ix], value)
    elif mode == "max":
        a[ix] = np.maximum(a[ix], value)


def groove_rect(H: np.ndarray, x0: int, y0: int, x1: int, y1: int, w: int, depth: float) -> None:
    """A thin rectangular groove (a hatch outline)."""
    for (a, b, c, d) in ((x0, y0, x1, y0 + w), (x0, y1 - w, x1, y1), (x0, y0, x0 + w, y1), (x1 - w, y0, x1, y1)):
        wrap_rect(H, a, b, c, d, -depth, "min")


def dot(H: np.ndarray, cx: float, cy: float, r: float, height: float) -> None:
    """A fastener: a small dome."""
    x0, x1, y0, y1 = int(cx - r - 1), int(cx + r + 2), int(cy - r - 1), int(cy + r + 2)
    yy, xx = np.mgrid[y0:y1, x0:x1]
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
    bump = np.clip(1.0 - d * d, 0.0, 1.0) ** 0.5 * height
    ys, xs = np.arange(y0, y1) % N, np.arange(x0, x1) % N
    ix = np.ix_(ys, xs)
    H[ix] = np.maximum(H[ix], bump)


def main() -> None:
    rng = np.random.default_rng(2491)
    pid = np.zeros((N, N), np.int32)          # which plate each pixel belongs to
    H = np.zeros((N, N), np.float32)          # relief of the details inside the plates (the seams come later)
    tone = np.zeros((N, N), np.float32)
    rough = np.zeros((N, N), np.float32)
    recess = np.zeros((N, N), np.float32)     # where dirt collects inside plates (grilles, hatch grooves)
    plates = []
    # --- rows of plates (courses), each shifted so the joints stagger like real plating
    y = 0
    heights = []
    while y < N:
        h = int(rng.choice([1.5, 2.0, 2.0, 2.5, 3.0, 3.0, 4.0, 5.0, 6.0]) * PX)
        if N - (y + h) < 1.2 * PX:
            h = N - y
        heights.append((y, y + h))
        y += h
    k = 1
    for (y0, y1) in heights:
        ox = int(rng.integers(0, N))
        x = 0
        while x < N:
            w = int(rng.choice([2.0, 3.0, 4.0, 4.0, 5.0, 6.0, 8.0, 10.0]) * PX)
            if N - (x + w) < 1.5 * PX:
                w = N - x
            x0, x1 = ox + x, ox + x + w
            wrap_rect(pid, x0, y0, x1, y1, k)
            t = float(np.clip(rng.normal(0.0, 0.38), -1.0, 1.0))
            wrap_rect(tone, x0, y0, x1, y1, t)
            wrap_rect(rough, x0, y0, x1, y1, float(np.clip(rng.normal(0.0, 0.3), -1.0, 1.0)))
            plates.append((x0, y0, x1, y1))
            x += w
            k += 1
    # --- the seams: where a pixel's plate differs from its neighbour's, widened into a soft V groove
    edge = np.zeros((N, N), bool)
    for ax in (0, 1):
        edge |= pid != np.roll(pid, 1, axis=ax)
    seam = edge.astype(np.float32)
    seam = np.maximum.reduce([np.roll(seam, s, axis=a) for a in (0, 1) for s in (-1, 0, 1)])   # ~3 px = 5 cm
    seam = np.clip(blur(seam, 0.9) * 1.6, 0.0, 1.0)
    # --- details inside the plates
    for (x0, y0, x1, y1) in plates:
        w, h = x1 - x0, y1 - y0
        r = rng.random()
        if r < 0.28 and min(w, h) > 1.4 * PX:
            # fastener rows along the long edges
            inset, step = 0.09 * PX, 0.28 * PX
            if w >= h:
                for yy in (y0 + inset, y1 - inset):
                    for xx in np.arange(x0 + inset, x1 - inset, step):
                        dot(H, xx, yy, 2.2, 0.45)
            else:
                for xx in (x0 + inset, x1 - inset):
                    for yy in np.arange(y0 + inset, y1 - inset, step):
                        dot(H, xx, yy, 2.2, 0.45)
        elif r < 0.42 and min(w, h) > 1.8 * PX:
            # a hatch: an inset outline, two recessed handles
            m = int(rng.uniform(0.25, 0.5) * PX)
            hx0, hy0, hx1, hy1 = x0 + m, y0 + m, x1 - m, y1 - m
            if w > 4.5 * PX:   # hatches are not the size of the whole plate
                cw = int(rng.uniform(1.2, 2.2) * PX)
                cx = int(rng.integers(hx0, hx1 - cw))
                hx0, hx1 = cx, cx + cw
            groove_rect(H, hx0, hy0, hx1, hy1, 3, 0.7)
            groove_rect(recess, hx0, hy0, hx1, hy1, 3, -1.0)
            for hy in (hy0 + int(0.2 * PX), hy1 - int(0.28 * PX)):
                wrap_rect(H, hx0 + int(0.2 * PX), hy, hx0 + int(0.45 * PX), hy + int(0.08 * PX), -0.5, "min")
        elif r < 0.52 and min(w, h) > 1.4 * PX:
            # a vent grille: parallel slots in a recessed frame
            gw, gh = min(w - 0.5 * PX, rng.uniform(0.8, 2.0) * PX), min(h - 0.5 * PX, rng.uniform(0.5, 1.2) * PX)
            gx0 = int(x0 + (w - gw) / 2)
            gy0 = int(y0 + (h - gh) / 2)
            wrap_rect(H, gx0 - 4, gy0 - 4, int(gx0 + gw) + 4, int(gy0 + gh) + 4, -0.15, "min")
            for sx in np.arange(gx0 + 4, gx0 + gw - 4, 11):
                wrap_rect(H, int(sx), gy0 + 3, int(sx) + 5, int(gy0 + gh) - 3, -0.9, "min")
                wrap_rect(recess, int(sx), gy0 + 3, int(sx) + 5, int(gy0 + gh) - 3, 1.0, "max")
        elif r < 0.64 and min(w, h) > 1.6 * PX:
            # a patch plate: a thinner doubler riveted on, a slightly different paint
            m = int(rng.uniform(0.3, 0.6) * PX)
            wrap_rect(H, x0 + m, y0 + m, x1 - m, y1 - m, 0.22, "max")
            wrap_rect(tone, x0 + m, y0 + m, x1 - m, y1 - m, float(rng.uniform(-0.6, 0.6)), "add")
    # soften the relief a touch so it mips cleanly, then cut the seams in
    H = blur(H, 0.6) - 1.0 * seam
    # --- normal map (DirectX: +G = image down)
    strength = 2.2
    dhx = (np.roll(H, -1, axis=1) - np.roll(H, 1, axis=1)) * 0.5
    dhy = (np.roll(H, -1, axis=0) - np.roll(H, 1, axis=0)) * 0.5
    n = np.stack([-dhx * strength, -dhy * strength, np.ones_like(H)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    nrm = ((n * 0.5 + 0.5) * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    # --- masks
    grime = fractal_noise(rng)                               # big soft dirt patches (isotropic: a hull has no "down")
    near_seam = np.clip(blur(seam, 6.0) * 2.2, 0.0, 1.0)     # dirt that gathers along the joints
    in_recess = np.clip(blur(recess, 2.0) * 1.5, 0.0, 1.0)
    cavity = 1.0 - 0.55 * seam - 0.22 * near_seam - 0.35 * in_recess - 0.18 * np.clip((grime - 0.55) * 2.2, 0.0, 1.0)
    cavity = np.clip(cavity, 0.0, 1.0)
    rgh = np.clip(0.5 + 0.22 * rough + 0.18 * near_seam + 0.15 * (grime - 0.5), 0.0, 1.0)
    tn = np.clip(0.5 + 0.5 * tone * 0.9 + 0.06 * (grime - 0.5), 0.0, 1.0)
    msk = (np.stack([cavity, rgh, tn], axis=-1) * 255.0 + 0.5).clip(0, 255).astype(np.uint8)
    os.makedirs(OUT, exist_ok=True)
    Image.fromarray(nrm, "RGB").save(os.path.join(OUT, "T_HullPanels_N.png"))
    Image.fromarray(msk, "RGB").save(os.path.join(OUT, "T_HullPanels_MSK.png"))
    # a small preview: the masks as a lit panel (for eyes, not for the engine)
    light = np.clip(n[..., 0] * -0.45 + n[..., 1] * -0.45 + n[..., 2] * 0.77, 0, 1)
    pv = (0.5 + 0.5 * (tn - 0.5) * 1.2) * cavity * (0.35 + 0.65 * light)
    Image.fromarray((np.clip(pv, 0, 1) * 255).astype(np.uint8), "L").resize((1024, 1024)).save(os.path.join(OUT, "_preview_hull_panels.png"))
    print("plates", len(plates), "rows", len(heights), "->", os.path.abspath(OUT))


if __name__ == "__main__":
    main()
