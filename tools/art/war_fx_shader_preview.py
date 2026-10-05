"""Pictures of the war's effect shaders, from a numpy port of their maths (tools/ue_scripts/war_fx_hlsl.py is the shader; this follows it line by
line), so that the shield's hexagons, a flash's streaks, a dart, a beam and a drive's plume can be looked at and tuned before the editor compiles
the real thing. Called by tools/art/war_fx_textures.py --preview <folder>, or:

  uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_shader_preview.py docs/progressi/vfx

The exposure of the pictures is the game's in space (fixed EV 6.6: an emissive of 116 reads as white, docs/STILE.md §8), through the same
filmic curve as the textures' sheets.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image

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


def stars(shape, seed=5, density=0.0016):
    rng = np.random.default_rng(seed)
    img = np.zeros(shape + (3,), np.float32)
    m = rng.random(shape) < density
    img[m] = (rng.random((m.sum(), 1)) ** 3 * 40.0 + 6.0) * np.asarray([1.0, 0.95, 0.9], np.float32)
    return img


# ----------------------------------------------------------------------------------------------------------------------------------- shield
def hex_cell(p):
    """The shader's hexagon lattice: returns (local xy in the cell, cell id xy)."""
    s = np.asarray([1.0, 1.7320508])
    a = np.floor(p / s) + 0.5
    b = np.floor((p - np.asarray([0.5, 1.0])) / s) + 0.5
    hh0 = p - a * s
    hh1 = p - (b + 0.5) * s
    use0 = (hh0 ** 2).sum(-1) < (hh1 ** 2).sum(-1)
    loc = np.where(use0[..., None], hh0, hh1)
    cid = np.where(use0[..., None], a, b + 0.5)
    return loc, cid


def shield_shade(P, u, ax, hits, infos, collapse, cell, tm, col, gain=1.0):
    """The M_WAR_Shield shader (war_fx_hlsl.SHIELD) on arrays of pixels: P (H,W,3) metres on the ellipsoid, u the unit direction."""
    nrm = np.abs(u / ax)
    nrm = nrm / np.maximum(nrm.sum(-1, keepdims=True), 1e-4)
    w = nrm ** 8
    w = w / np.maximum(w.sum(-1, keepdims=True), 1e-4)
    # pixel footprint (the shader's ddx/ddy of P)
    dPdx = np.gradient(P, axis=1)
    dPdy = np.gradient(P, axis=0)
    mpp = np.linalg.norm(dPdx, axis=-1) + np.linalg.norm(dPdy, axis=-1)
    fw = mpp / cell
    aa = saturate(1.0 - fw * 1.6)
    edge_w = np.maximum(0.07, fw * 1.1)
    cdir = np.asarray(collapse[:3], np.float64)
    cdir = cdir / (np.linalg.norm(cdir) + 1e-4)
    lit = np.zeros(P.shape[:2])
    for k in range(3):
        q = [P[..., [1, 2]], P[..., [0, 2]], P[..., [0, 1]]][k]
        wk = w[..., k]
        p = q / cell
        loc, cid = hex_cell(p)
        a2 = np.abs(loc)
        eg = 0.5 - np.maximum(a2[..., 0] * 0.5 + a2[..., 1] * 0.8660254, a2[..., 0])
        cen = cid * np.asarray([1.0, 1.7320508]) * cell
        Pc = np.stack([P[..., 0], cen[..., 0], cen[..., 1]], -1) if k == 0 else (
            np.stack([cen[..., 0], P[..., 1], cen[..., 1]], -1) if k == 1 else np.stack([cen[..., 0], cen[..., 1], P[..., 2]], -1))
        hsh = (np.sin(((cid + k * 17.0) * np.asarray([127.1, 311.7])).sum(-1)) * 43758.5453) % 1.0
        flick = 0.55 + 0.45 * ((np.sin((hsh + np.floor(tm * 13.0 + hsh * 9.0)) * 78.233) * 43758.5453) % 1.0)
        cl = np.zeros(P.shape[:2])
        for hit, inf in zip(hits, infos):
            Ph = np.asarray(hit[:3], np.float64)
            Ph = Ph / (np.linalg.norm(Ph) + 1e-4) * ax
            dd = np.linalg.norm(Pc - Ph, axis=-1)
            R = max(inf[0], 1.0)
            age = inf[1]
            front = R * (0.2 + 0.95 * age)
            qb = (dd - front) / (0.30 * R + cell)
            qc = dd / (0.42 * R + cell)
            band = np.exp(-qb * qb)
            core = np.exp(-qc * qc) * (1.0 - age)
            jag = lerp(1.0, flick, saturate(0.25 + inf[2]))
            cl += max(hit[3], 0.0) * (0.85 * band + 1.1 * core) * jag
        on = smoothstep(0.5, 0.9, ((Pc / ax) / (np.linalg.norm(Pc / ax, axis=-1, keepdims=True) + 1e-6) * cdir).sum(-1))
        cl += collapse[3] * on * (0.5 + 0.9 * flick)
        edge = 1.0 - smoothstep(0.0, edge_w, eg)
        body = 0.30 * smoothstep(0.0, 0.25, eg)
        pat = lerp(0.45, edge + body, aa)
        lit += wk * cl * pat
    bloom = np.zeros(P.shape[:2])
    for hit, inf in zip(hits, infos):
        Ph = np.asarray(hit[:3], np.float64)
        Ph = Ph / (np.linalg.norm(Ph) + 1e-4) * ax
        dd = np.linalg.norm(P - Ph, axis=-1)
        R = max(inf[0], 1.0)
        qc = dd / (0.55 * R + cell)
        bloom += max(hit[3], 0.0) * np.exp(-qc * qc) * (1.0 - inf[1]) * 0.35
    total = lit + bloom
    c = lerp(np.asarray(col)[None, None, :], np.asarray([1.0, 0.97, 0.92])[None, None, :], saturate(total * 0.22)[..., None])
    return c * (total * gain * 48.0)[..., None]


def render_shell(axes, hits, infos, collapse, cell, cam, target, fov_deg, outside, size=(960, 540), tm=1.3, col=(0.28, 0.6, 1.0), bg=None):
    W, H = size
    ax = np.asarray(axes, np.float64)
    fwd = np.asarray(target, np.float64) - np.asarray(cam, np.float64)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    f = 0.5 * W / math.tan(math.radians(fov_deg) / 2)
    ys, xs = np.mgrid[0:H, 0:W]
    d = fwd[None, None] * f + right[None, None] * (xs - W / 2 + 0.5)[..., None] - up[None, None] * (ys - H / 2 + 0.5)[..., None]
    d /= np.linalg.norm(d, axis=-1, keepdims=True)
    o = np.asarray(cam, np.float64)
    o2 = o / ax
    d2 = d / ax
    a = (d2 * d2).sum(-1)
    b = 2 * (o2[None, None] * d2).sum(-1)
    c = (o2 ** 2).sum() - 1.0
    disc = b * b - 4 * a * c
    hit = disc > 0
    sq = np.sqrt(np.maximum(disc, 0))
    t = np.where(outside, (-b - sq) / (2 * a), (-b + sq) / (2 * a))
    hit &= t > 0
    p = o[None, None] + d * t[..., None]
    u = p / ax
    u /= np.linalg.norm(u, axis=-1, keepdims=True) + 1e-9
    P = u * ax
    img = stars((H, W)) if bg is None else bg.copy()
    sh = shield_shade(P, u, ax, hits, infos, collapse, cell, tm, col)
    img = img + np.where(hit[..., None], sh, 0.0)
    return img


def preview_shield(folder: str) -> None:
    ax = np.asarray([472.0, 122.0, 85.0])             # the Aquila's shell
    cell = 14.0

    def unit(v):
        v = np.asarray(v, np.float64)
        return v / np.linalg.norm(v)
    # three blows of different ages on the port flank, one on the bow, and the stern sector falling
    hits = [np.r_[unit([0.35, -1.0, 0.1]), 1.1 * 0.9], np.r_[unit([0.05, -1.0, 0.25]), 0.8 * 0.5], np.r_[unit([-0.25, -1.0, -0.05]), 0.6 * 0.2],
            np.r_[unit([1.0, -0.2, 0.1]), 1.4 * 0.7], np.r_[unit([1, 0, 0]), 0.0], np.r_[unit([1, 0, 0]), 0.0]]
    infos = [(34.0, 0.10, 0.2, 0.1), (26.0, 0.45, 0.5, 0.3), (18.0, 0.8, 0.9, 0.6), (30.0, 0.2, 0.1, 0.8), (10.0, 1.0, 0.0, 0.0), (10.0, 1.0, 0.0, 0.0)]
    collapse = np.r_[unit([-1, 0, 0]), 0.0]
    os.makedirs(folder, exist_ok=True)
    cam = np.asarray([-300.0, -900.0, 260.0])
    img = render_shell(ax, hits, infos, collapse, cell, cam, [20, 0, 0], 38, True)
    Image.fromarray(tonemap(img)).save(os.path.join(folder, "shield_outside.png"))
    # the sector at the stern falls
    hits2 = [np.r_[unit([-1, 0.15, 0]), 1.8 * 0.8]] + [np.r_[unit([1, 0, 0]), 0.0]] * 5
    infos2 = [(40.0, 0.12, 1.0, 0.4)] + [(10.0, 1.0, 0.0, 0.0)] * 5
    collapse2 = np.r_[unit([-1, 0, 0]), 0.85]
    img2 = render_shell(ax, hits2, infos2, collapse2, cell, np.asarray([-1000.0, -420.0, 190.0]), [-250, 0, 0], 42, True)
    Image.fromarray(tonemap(img2)).save(os.path.join(folder, "shield_collapse.png"))
    # from the bridge, inside her own shell, looking forward: a blow on the bow
    hits3 = [np.r_[unit([1.0, -0.12, 0.06]), 1.2 * 0.85], np.r_[unit([0.95, 0.2, 0.1]), 0.9 * 0.5]] + [np.r_[unit([1, 0, 0]), 0.0]] * 4
    infos3 = [(34.0, 0.12, 0.2, 0.2), (26.0, 0.5, 0.4, 0.7)] + [(10.0, 1.0, 0.0, 0.0)] * 4
    bg = stars((540, 960), 9)
    img3 = render_shell(ax, hits3, infos3, np.r_[unit([1, 0, 0]), 0.0], cell, np.asarray([172.0, 0.0, 62.0]), [472, 0, 40], 90, False, bg=bg, col=(0.28, 0.6, 1.0))
    Image.fromarray(tonemap(img3)).save(os.path.join(folder, "shield_bridge.png"))


# ----------------------------------------------------------------------------------------------------------------------------------- glows
def glow_shade(xy, ndv, col, inten, age, kind, seed=0.3, tm=1.0):
    """war_fx_hlsl.GLOW on arrays (xy: the view-space normal's xy, ndv: |n.z|)."""
    r = np.hypot(xy[..., 0], xy[..., 1])
    rim = smoothstep(1.0, 0.80, r)
    fade = saturate(1.0 - age)
    white = np.asarray([1.0, 0.97, 0.9])
    col = np.asarray(col)
    ax_, ay_ = np.abs(xy[..., 0]), np.abs(xy[..., 1])
    if kind == 0:
        q = r / 0.20
        psf = 1.0 / (1.0 + q * q) ** 1.3
        out = lerp(col, white, (psf * psf)[..., None]) * psf[..., None] * (fade ** 0.8) * rim[..., None]
    elif kind == 1:
        q = r / 0.16
        core = np.exp(-q * q)
        p2 = r / 0.28
        psf = 1.0 / (1.0 + p2 * p2) ** 1.4
        sh = np.exp(-ay_ * 18.0) * np.exp(-ax_ * 4.5)
        sv = np.exp(-ax_ * 30.0) * np.exp(-ay_ * 4.0) * 0.35
        out = lerp(col, white, saturate(core * 1.4)[..., None]) * (core * 1.6 + psf * 0.5 + (sh + sv) * 0.6)[..., None] * (fade ** 1.6) * rim[..., None]
    elif kind == 2:
        q = r / 0.14
        psf = 1.0 / (1.0 + q * q) ** 1.5
        tw = 0.78 + 0.22 * math.sin(seed * 57 + tm * 23) * math.sin(seed * 13 + tm * 11)
        arms = np.exp(-ay_ * 24.0) * np.exp(-ax_ * 3.2) * 0.5 + np.exp(-ax_ * 24.0) * np.exp(-ay_ * 3.2) * 0.5
        out = lerp(col, white, psf[..., None]) * (psf + arms * 0.5)[..., None] * tw * (fade ** 0.45) * rim[..., None]
    else:
        qs = (ndv - 0.16) / 0.11
        limb = np.exp(-qs * qs)
        body = ndv ** 3.0 * 0.05
        out = lerp(col, white, 0.3) * (limb + body)[..., None] * (fade ** 1.3) * smoothstep(0.0, 0.08, ndv)[..., None]
    return out * inten


def preview_glows(folder: str) -> None:
    S = 256
    ys, xs = np.mgrid[0:S, 0:S]
    xy = np.stack([(xs + 0.5) / S * 2 - 1, -((ys + 0.5) / S * 2 - 1)], -1)
    r = np.hypot(xy[..., 0], xy[..., 1])
    nz = np.sqrt(np.maximum(1 - r * r, 0.0))
    inside = r < 1.0
    ndv = np.where(inside, nz, 0.0)
    tiles = []
    for kind, col, inten, age in ((0, (1.0, 0.8, 0.5), 220, 0.0), (1, (0.45, 0.7, 1.0), 300, 0.1), (1, (1.0, 0.62, 0.25), 460, 0.05), (2, (1.0, 0.8, 0.55), 300, 0.2), (3, (1.0, 0.7, 0.4), 140, 0.2)):
        g = glow_shade(xy, ndv, col, inten, age, kind) * inside[..., None]
        tiles.append(tonemap(g + 0.002 * 116))
    Image.fromarray(np.concatenate(tiles, axis=1)).save(os.path.join(folder, "glows.png"))


# ----------------------------------------------------------------------------------------------------------------------------------- darts, beams, plume
def tube_view(W=960, H=300):
    """A dart, a beam, a trail and a plume seen from the side (a cylinder: ndv from the radial direction), and a dart head-on."""
    img = stars((H, W), 3) * 0.5
    white = np.asarray([1.0, 0.96, 0.88])
    ys, xs = np.mgrid[0:H, 0:W].astype(np.float64)

    def draw_tube(cx, cy, length, width, col, inten, style, age=0.0, p2=0.0, tm=1.0, seed=0.3, vertical=False, plume=0):
        # a tube along x from (cx - length/2) to (cx + length/2), head at +x; width in pixels
        dx = (xs - cx) / length + 0.5
        dy = (ys - cy) / (width / 2)
        inside = (np.abs(dy) < 1.0) & (dx >= 0) & (dx <= 1)
        ndv = np.sqrt(np.maximum(1 - dy * dy, 0.0))
        t = np.clip(dx, 0, 1)
        L = length / 6.0                              # metres: 6 px a metre in this picture
        if style == "dart":
            head = smoothstep(0.0, 0.92, t)
            tail = head ** 1.3
            core = ndv ** 6
            halo = ndv ** 1.4
            hot = core * (0.55 + 0.45 * head)
            c = lerp(np.asarray(col), white, saturate(hot * 1.5)[..., None])
            fade = (1 - age) ** 1.5
            # the ellipsoid's own taper: the silhouette follows sqrt(1 - (2t-1)^2)
            taper = np.sqrt(np.maximum(1 - (2 * t - 1) ** 2, 0.0))
            inside &= np.abs(dy) < np.maximum(taper, 0.05)
            ndv = np.sqrt(np.maximum(1 - (dy / np.maximum(taper, 0.05)) ** 2, 0.0))
            core = ndv ** 6
            halo = ndv ** 1.4
            hot = core * (0.55 + 0.45 * head)
            c = lerp(np.asarray(col), white, saturate(hot * 1.5)[..., None])
            edge = smoothstep(0.0, 0.2, ndv)
            v = c * (inten * (halo * 0.5 + hot * 1.7) * tail * fade * edge)[..., None]
        elif style == "bead":                         # a trail's bead: an ellipsoid that overlaps its neighbours, dimming with age
            taper = np.sqrt(np.maximum(1 - (2 * t - 1) ** 2, 0.0))
            inside &= np.abs(dy) < np.maximum(taper, 0.05)
            ndv = np.sqrt(np.maximum(1 - (dy / np.maximum(taper, 0.05)) ** 2, 0.0))
            core = ndv ** 6
            halo = ndv ** 1.4
            hot = core * (0.55 + 0.45 * smoothstep(0.0, 0.92, t)) * 0.5
            c = lerp(np.asarray(col), white, saturate(hot * 1.5)[..., None])
            a = lerp(age, p2, t)
            fade = saturate(1 - a) ** 1.3
            c = lerp(c, np.asarray(col)[None, None] * 0.55, a[..., None])
            edge = smoothstep(0.0, 0.2, ndv)
            v = c * (inten * (halo * 0.5 + hot * 1.7) * fade * edge)[..., None]
        elif style == "beam":
            e = min(1.0, 18.0 / L)
            ends = smoothstep(0.0, e, t) * smoothstep(1.0, 1.0 - e, t)
            core = ndv ** 4.5
            halo = ndv ** 1.25
            c = lerp(np.asarray(col), white, saturate(core * 1.3)[..., None])
            pulse = 0.82 + 0.18 * np.sin(t * L / 7.0 - tm * 42.0 + seed * 6.2831853)
            edge = smoothstep(0.0, 0.18, ndv)
            v = c * (inten * (halo * 0.45 + core * 1.5) * ends * pulse * edge)[..., None]
        elif style == "trail":
            core = ndv ** 4.5
            halo = ndv ** 1.25
            c = lerp(np.asarray(col), white, saturate(core * 1.3)[..., None])
            a = lerp(age, p2, t)
            fade = saturate(1 - a) ** 1.3
            c = lerp(c, np.asarray(col)[None, None] * 0.55, a[..., None])
            edge = smoothstep(0.0, 0.18, ndv)
            v = c * (inten * (halo * 0.45 + core * 1.5) * fade * edge)[..., None]
        else:  # plume: x from the bell (t = 0, left) to the tip
            taper = ndv ** lerp(0.9, 9.0, t)
            body = saturate(1 - t) ** 1.5
            dia = 0.80 + 0.20 * np.cos(t * (length / 6.0) * 0.55 - tm * 14.0 + seed * 6.2831853)
            corec = np.asarray([0.82, 0.92, 1.0]) if plume == 0 else np.asarray([1.0, 0.7, 0.34])
            edgec = np.asarray([0.24, 0.52, 1.0]) if plume == 0 else np.asarray([0.6, 0.2, 0.95])
            c = lerp(edgec, corec, ((ndv ** 3) * (1 - t * 0.7))[..., None])
            e = smoothstep(0.0, 0.1, ndv)
            v = c * (inten * taper * body * dia * e)[..., None]
        return np.where(inside[..., None], v, 0.0)

    out = img.copy()
    out += draw_tube(160, 40, 300, 7, (0.42, 0.7, 1.0), 700, "dart")                 # an ASTRA slug
    out += draw_tube(620, 40, 300, 7, (1.0, 0.42, 0.12), 700, "dart")                 # a Mandate slug
    out += draw_tube(300, 120, 520, 9, (0.22, 0.58, 1.0), 520, "beam")                # a laser beam
    out += draw_tube(840, 120, 200, 9, (1.0, 0.16, 0.07), 520, "beam", seed=0.7)      # a Mandate beam
    for i in range(6):                                                                  # a missile trail of six beads, overlapping, fading
        out += draw_tube(100 + i * 70, 190, 120, 8 + 3 * i, (0.62, 0.82, 1.0), 90, "bead", age=(6 - i) / 7.0, p2=(5 - i) / 7.0)
    out += draw_tube(300, 250, 330, 28, (1, 1, 1), 70, "plume", plume=0)             # an ASTRA drive
    out += draw_tube(700, 250, 330, 28, (1, 1, 1), 70, "plume", plume=1, seed=0.6)   # a Mandate drive
    return tonemap(out)


def preview_tubes(folder: str) -> None:
    Image.fromarray(tube_view()).save(os.path.join(folder, "darts_beams_plumes.png"))


def render_all(folder: str) -> None:
    os.makedirs(folder, exist_ok=True)
    preview_glows(folder)
    preview_tubes(folder)
    preview_shield(folder)


if __name__ == "__main__":
    render_all(sys.argv[1] if len(sys.argv) > 1 else "docs/progressi/vfx")
    print("WAR_FX_SHADER_PREVIEW_OK")
