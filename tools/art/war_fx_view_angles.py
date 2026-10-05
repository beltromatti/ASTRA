"""A dart, a beam and a wake seen from every side, old shading against new (the numpy port of tools/ue_scripts/war_fx_hlsl.py's DART and TUBE).

  uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_view_angles.py [out.png]

Why it exists (VFX-2, 5 Oct): the slugs and the beams were shaded by the Fresnel term of a cylinder or a stretched sphere, which is at most sin(theta), theta being the angle
between the view and the axis: seen from behind or along the line of fire (the main viewscreen's camera, the bridge, the Aquila's broadside camera: every view of "our" fire) a
slug was a dark disc and a beam a faint halo. This draws the same cylinder from 90 (side-on) down to 0 degrees (end-on) and from behind, with the shading that was and the shading
that is: the lateral profile normalised by sin(theta), the end discs shaded as discs, the along-axis fade (tail, ends) used only as far as the axis lies across the view.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

EXPOSURE = 1.0 / 116.0


def tonemap(x: np.ndarray, exposure: float = EXPOSURE) -> np.ndarray:
    x = np.maximum(x * exposure, 0.0)
    y = np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)
    return (y ** (1 / 2.2) * 255 + 0.5).astype(np.uint8)


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t


def saturate(x):
    return np.clip(x, 0.0, 1.0)


def raycast(theta_deg: float, behind: bool, length_m: float, width_m: float, scale: float, size=(560, 220)):
    """Orthographic view of a cylinder along local z (head at +z). theta: angle between the axis and the view vector (the vector to the camera); behind: the camera
    sees the tail (the slug flies away from it). Returns arrays on the pixel grid: hit mask, LP (shader local position, cm: x,y radial +-50, z +-50), NW (radial direction),
    CamV (unit vector to the camera) and the axis."""
    W, H = size
    th = math.radians(theta_deg)
    ax = np.array([0.0, 0.0, 1.0])
    # the view vector in the cylinder's frame: in the xz plane, theta from +z (head toward the camera) or from -z (tail toward the camera)
    v = np.array([math.sin(th), 0.0, math.cos(th) * (-1.0 if behind else 1.0)])
    ea = np.cross(np.array([0.0, 1.0, 0.0]), v)          # screen right
    ea /= np.linalg.norm(ea)
    eb = np.cross(v, ea)                                  # screen up
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)
    a = (xs - W / 2 + 0.5) * scale
    b = -(ys - H / 2 + 0.5) * scale
    O = a[..., None] * ea + b[..., None] * eb + v * 10000.0
    D = -v
    R = width_m / 2
    Lh = length_m / 2
    # barrel: x^2 + y^2 = R^2
    A = D[0] ** 2 + D[1] ** 2
    B = 2 * (O[..., 0] * D[0] + O[..., 1] * D[1])
    C = O[..., 0] ** 2 + O[..., 1] ** 2 - R * R
    disc = B * B - 4 * A * C if A > 1e-12 else np.full(C.shape, -1.0)
    t_best = np.full(C.shape, np.inf)
    kind = np.zeros(C.shape, np.int8)
    if A > 1e-12:
        sq = np.sqrt(np.maximum(disc, 0))
        t0 = (-B - sq) / (2 * A)
        P0 = O + D * t0[..., None]
        ok = (disc > 0) & (np.abs(P0[..., 2]) <= Lh)
        t_best = np.where(ok, t0, t_best)
        kind = np.where(ok, 1, kind)
    for sgn in (1, -1):                                   # the two end discs
        if abs(D[2]) > 1e-9:
            tc = (sgn * Lh - O[..., 2]) / D[2]
            Pc = O + D * tc[..., None]
            okc = (Pc[..., 0] ** 2 + Pc[..., 1] ** 2 <= R * R) & (tc < t_best)
            t_best = np.where(okc, tc, t_best)
            kind = np.where(okc, 2, kind)
    hit = np.isfinite(t_best)
    P = O + D * np.where(hit, t_best, 0.0)[..., None]
    LP = np.stack([P[..., 0] / R * 50.0, P[..., 1] / R * 50.0, P[..., 2] / Lh * 50.0], -1)
    radial = np.stack([P[..., 0], P[..., 1], np.zeros_like(P[..., 0])], -1)
    NW = radial / (np.linalg.norm(radial, axis=-1, keepdims=True) + 1e-9)
    return hit, LP, NW, v, ax, kind


# ---------------------------------------------------------------------------------------------------------------- the shaders, old and new
def ndv_old(NW, v):
    return np.abs((NW * v).sum(-1))


def ndv_new(LP, NW, v, ax):
    sinT = np.linalg.norm(np.cross(ax, v))
    r = np.hypot(LP[..., 0], LP[..., 1]) / 50.0
    cap = (np.abs(LP[..., 2]) > 49.5) & (r < 0.97)
    side = np.abs((NW * v).sum(-1)) / max(sinT, 0.12)
    ndv = np.where(cap, np.sqrt(saturate(1 - r * r * r)), saturate(side))
    return ndv, sinT


def dart_old(Col, Inten, Style, ndv, LP, age=0.0, p2=0.0, seed=0.3, tm=1.0):
    t = saturate(LP[..., 2] / 100.0 + 0.5)
    head = smoothstep(0.0, 0.92, t)
    tail = head ** 1.3
    core = ndv ** 6.0
    halo = ndv ** 1.4
    hot = core * (0.55 + 0.45 * head)
    white = np.array([1.0, 0.96, 0.88])
    c = lerp(np.asarray(Col), white, saturate(hot * 1.5)[..., None])
    fade = 1.0
    edge = smoothstep(0.0, 0.2, ndv)
    return c * (Inten * (halo * 0.5 + hot * 1.7) * tail * fade * edge)[..., None]


def dart_new(Col, Inten, ndv, sinT, LP, width_m):
    t = saturate(LP[..., 2] / 100.0 + 0.5)
    side = smoothstep(0.05, 0.35, sinT)
    # the silhouette tapers to points at both ends (the dart is a spindle), as far as the axis lies across the view
    taper = lerp(1.0, np.sqrt(saturate(1.0 - (2.0 * t - 1.0) ** 2)), side)
    lat = np.sqrt(saturate(1.0 - ndv * ndv))
    q = lat / np.maximum(taper, 0.06)
    ndv_t = np.sqrt(saturate(1.0 - q * q))
    tt = lerp(0.5, t, side)
    head = smoothstep(0.0, 0.92, tt)
    tail = lerp(1.0, head ** 1.3, side)
    core = ndv_t ** 6.0
    halo = ndv_t ** 1.4
    hot = core * (0.55 + 0.45 * head)
    white = np.array([1.0, 0.96, 0.88])
    c = lerp(np.asarray(Col), white, saturate(hot * 1.5)[..., None])
    edge = smoothstep(0.0, 0.2, ndv_t)
    return c * (Inten * (halo * 0.5 + hot * 1.7) * tail * edge)[..., None]


def tube_old(Col, Inten, ndv, LP, length_m, style=1, tm=1.0, seed=0.3):
    t = saturate(LP[..., 2] / 100.0 + 0.5)
    L = max(length_m, 1.0)
    e = min(1.0, 18.0 / L)
    ends = smoothstep(0.0, e, t) * smoothstep(1.0, 1.0 - e, t)
    core = ndv ** 4.5
    halo = ndv ** 1.25
    white = np.array([1.0, 0.97, 0.9])
    c = lerp(np.asarray(Col), white, saturate(core * 1.3)[..., None])
    pulse = 0.82 + 0.18 * np.sin(t * L / 7.0 - tm * 42.0 + seed * 6.2831853)
    edge = smoothstep(0.0, 0.18, ndv)
    return c * (Inten * (halo * 0.45 + core * 1.5) * ends * pulse * edge)[..., None]


def tube_new(Col, Inten, ndv, sinT, LP, length_m, style=1, tm=1.0, seed=0.3, wake_exp=2.2):
    t = saturate(LP[..., 2] / 100.0 + 0.5)
    side = smoothstep(0.05, 0.35, sinT)
    tt = lerp(0.5, t, side)
    L = max(length_m, 1.0)
    e = min(1.0, 18.0 / L)
    ends = lerp(1.0, smoothstep(0.0, e, tt) * smoothstep(1.0, 1.0 - e, tt), side)
    core = ndv ** 4.5
    halo = ndv ** 1.25
    white = np.array([1.0, 0.97, 0.9])
    c = lerp(np.asarray(Col), white, saturate(core * 1.3)[..., None])
    pulse = 1.0
    fade = 1.0
    if style == 1:
        pulse = 0.82 + 0.18 * np.sin(t * L / 7.0 - tm * 42.0 + seed * 6.2831853)
    elif style == 5:                                      # a slug's wake: bright at the head, gone at the tail
        fade = lerp(0.5, tt ** wake_exp, side) if False else lerp(0.35, tt ** wake_exp, side)
        ends = lerp(1.0, smoothstep(0.0, 0.02, tt) * smoothstep(1.0, 0.99, tt), side)
    edge = smoothstep(0.0, 0.18, ndv)
    return c * (Inten * (halo * 0.45 + core * 1.5) * ends * pulse * fade * edge)[..., None]


def render_row(angle, behind, what, new, length_m=200.0, width_m=14.0, scale=0.5, size=(560, 220)):
    hit, LP, NW, v, ax, kind = raycast(angle, behind, length_m, width_m, scale, size)
    nd_old = ndv_old(NW, v)
    nd_new, sinT = ndv_new(LP, NW, v, ax)
    if what == "dart":
        col = (0.42, 0.7, 1.0)
        img = dart_new(col, 700, nd_new, sinT, LP, width_m) if new else dart_old(col, 700, "dart", nd_old, LP)
    elif what == "beam":
        col = (0.22, 0.58, 1.0)
        img = tube_new(col, 520, nd_new, sinT, LP, length_m, 1) if new else tube_old(col, 520, nd_old, LP, length_m)
    else:                                                  # the wake (new only)
        col = (0.42, 0.7, 1.0)
        img = tube_new(col, 260, nd_new, sinT, LP, length_m, 5) if new else tube_old(col, 260, nd_old, LP, length_m)
    return np.where(hit[..., None], img, 0.0)


def sheet(out: str) -> None:
    angles = [(90, False), (60, False), (30, False), (12, False), (4, False), (0.5, False), (4, True), (30, True)]
    labels = ["90 side", "60", "30", "12", "4", "0.5 head-on", "4 behind", "30 behind"]
    W, H = 280, 110
    rows = []
    for what in ("dart", "beam", "wake"):
        for new in (False, True):
            if what == "wake" and not new:
                continue
            tiles = []
            for (ang, behind), lab in zip(angles, labels):
                im = render_row(ang, behind, what, new, size=(W, H), scale=1.0 if what != "wake" else 1.0, length_m=200.0, width_m=14.0)
                bg = np.zeros_like(im) + 0.4
                img = Image.fromarray(tonemap(im + bg))
                d = ImageDraw.Draw(img)
                d.text((4, 2), f"{what} {'new' if new else 'old'} {lab}", fill=(255, 255, 0))
                tiles.append(np.asarray(img))
            rows.append(np.concatenate(tiles, axis=1))
    full = np.concatenate(rows, axis=0)
    Image.fromarray(full).save(out)
    print("wrote", out, full.shape)


if __name__ == "__main__":
    sheet(sys.argv[1] if len(sys.argv) > 1 else "docs/progressi/vfx/view_angles.png")
    print("WAR_FX_VIEW_ANGLES_OK")
