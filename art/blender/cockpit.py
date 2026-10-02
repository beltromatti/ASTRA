"""The Falcon's cockpit, seen from the pilot's seat (first person), version 2 (ARTE-PLANCIA-2): a fighter of 2491 in the language of the bridge v3
(gunmetal, carbon, ivory, brass, lit panels, the decor pages for the displays), built on the bridge toolkit (bridge3_lib, bridge3_controls).

What the pilot sees, from the eye (the origin) outwards: the front canopy bow with its liner, lit edge and bolts, the sill rails with their latches
and lit edge, the spine over the head with the canopy jettison ring, the rear-view mirror on the left bow; the anti-glare dash hood with the HUD projector (the HUD
itself is drawn by the game), the standby compass; the instrument panel under the hood (three displays with their soft keys, standby instruments,
engine instruments, a caution panel, switch banks with guarded toggles, a keypad); the side consoles (the throttle quadrant and the comms on the
left, the sensor scope, the ordnance switches and the ejection arm on the right); the stick between the knees; the ejection seat with its harness and
the striped ejection loop; and outside: the nose with its dark anti-glare deck, the navy stripe and panel lines, the shoulders, the wings, the twin
fins and the engines (the Falcon v3's hull: ship3_craft.build_falcon).

Frame: metres, +X forward, +Z up, +Y to the pilot's right (layout frame, as the bridge: FB mirrors Y on the way out, the FBX lands 1:1 in Unreal),
the pilot's eye at the origin (the fighter pawn's camera). The outside matches the Falcon v3: the eye sits 3.2 m ahead of the Falcon's centre,
1.15 m above its axis.

Slots (the Unreal instances, astra_editor.assign_materials_by_slot): the interior uses the bridge v3's (MI_BRG3_*, MI_ASTRA_Structure/Trim/Rubber),
the outside the Falcon's own hull instances (MI_HULL_A_Plate / Frame / Livery), so that the nose looks like the Falcon's hull seen from outside.

Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/cockpit.py -- art/export/cockpit [--preview <dir>] [--views pilot,dash,...] [--samples N] [--no-export]
"""
from __future__ import annotations

import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_controls as CT  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Parts, Rx, Ry, Rz, T, lerp  # noqa: E402
from bridge3_marks import emblem  # noqa: E402

PLATE, FRAME, LIVERY = "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Livery"
NAME = "SM_CRAFT_ASTRA_Falcon_Cockpit"

SILL_Z = -0.36                      # the sill line of the canopy
AX = -1.15                          # the Falcon's axis, 1.15 m under the eye


# ============================================================================================================== frames and sections
def basis(origin, x_axis, z_axis) -> Matrix:
    """A right-handed frame at `origin`: local x = x_axis, local z = z_axis (unit vectors, orthogonal), local y = z cross x."""
    x, z = Vector(x_axis).normalized(), Vector(z_axis).normalized()
    y = z.cross(x)
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], origin[i]
    return m


def chamfer_rect(w: float, h: float, c: float = 0.25, top: float = 1.0, bottom: float = 1.0):
    """An octagon from a w x h rectangle (half sizes), corners cut by c (fraction); top/bottom narrow the upper/lower halves. Counter-clockwise."""
    cw, ch = c * w, c * h
    return [(-w * bottom + cw, -h), (w * bottom - cw, -h), (w, -h + ch), (w, h - ch), (w * top - cw, h), (-w * top + cw, h), (-w, h - ch), (-w, -h + ch)]


def rect_sec(w: float, d: float, c: float = 0.0):
    """A bow's section (n across the arch, a along x): w x d, the two edges on the pilot's side cut by c."""
    return [(-w / 2 + c, -d / 2), (w / 2 - c, -d / 2), (w / 2, -d / 2 + c), (w / 2, d / 2), (-w / 2, d / 2), (-w / 2, -d / 2 + c)]


def canopy_half(x: float) -> float:
    return 0.62 - 0.22 * max(0.0, (x - 0.4) / 0.7)


def canopy_top(x: float) -> float:
    return 0.42 - 0.18 * max(0.0, (x - 0.2) / 0.9) ** 2 - 0.05 * max(0.0, (-0.3 - x) / 0.6)


def canopy_path(x: float, n: int = 32):
    """The canopy's cross-section at station x as (y, z) points from the right sill over the top to the left sill."""
    half, top = canopy_half(x), canopy_top(x)
    return [(half * math.cos(math.pi * k / n), SILL_Z + (top - SILL_Z) * math.sin(math.pi * k / n)) for k in range(n + 1)]


def _outward(pts, i):
    """The unit normal (in the plane of the arch) at point i of an arch, pointing away from the middle of the opening."""
    y, z = pts[i]
    a, b = pts[max(0, i - 1)], pts[min(len(pts) - 1, i + 1)]
    ty, tz = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(ty, tz)
    ny, nz = tz / ln, -ty / ln
    if ny * y + nz * (z - SILL_Z) < 0:
        ny, nz = -ny, -nz
    return ny, nz


def sweep(fb: FB, x: float, section, mat: str, n: int = 32, caps: bool = True, lo: int = 0, hi: int | None = None):
    """A bow at station x: `section` ((n, a) polygon: n outwards in the plane of the arch, a along x) swept along the canopy path (points lo..hi)."""
    pts = canopy_path(x, n)
    hi = len(pts) - 1 if hi is None else hi
    rings = []
    for i in range(lo, hi + 1):
        y, z = pts[i]
        ny, nz = _outward(pts, i)
        rings.append([(x + av, y + ny * nv, z + nz * nv) for (nv, av) in section])
    fb.loft(rings, mat, caps=caps, closed=True)
    return pts


def bolt_row(em: FB, x: float, off: float, nv: float, pitch: float, mat: str = L.TRIM, r: float = 0.0062, n: int = 32) -> None:
    """Flat hex bolt heads along a canopy path (at `nv` from its centre line) on the face of the bow that looks back at the pilot (x - off)."""
    pts = canopy_path(x, n)
    acc = pitch * 0.5
    for i in range(1, len(pts) - 1):
        (y0, z0), (y1, z1) = pts[i - 1], pts[i]
        acc += math.hypot(y1 - y0, z1 - z0)
        if acc >= pitch:
            acc = 0.0
            ny, nz = _outward(pts, i)
            hex_pad(em, x - off, pts[i][0] + ny * nv, pts[i][1] + nz * nv, r, (-1, 0, 0), mat, up=(0, 0, 1))


def lit_line(em: FB, x: float, off: float, nv: float, w: float, cell: str, mat: str = L.LAMP_DIM, n: int = 32, lo: int = 0, hi: int | None = None) -> None:
    """A thin lit line along a bow (on its back face), `w` wide, at `nv` from the centre line of the bow."""
    pts = canopy_path(x, n)
    hi = len(pts) - 1 if hi is None else hi
    rings = []
    for i in range(lo, hi + 1):
        y, z = pts[i]
        ny, nz = _outward(pts, i)
        rings.append([(x - off, y + ny * (nv - w / 2), z + nz * (nv - w / 2)), (x - off, y + ny * (nv + w / 2), z + nz * (nv + w / 2))])
    faces = em.loft(rings, mat, caps=False, closed=False)
    em._paint(faces, L.cell_uv(cell))


def brass_line(em: FB, x: float, off: float, nv: float, w: float, n: int = 32) -> None:
    """A thin brass line along a bow (on its back face), `w` wide, at `nv` from the centre line of the bow."""
    pts = canopy_path(x, n)
    rings = []
    for i in range(len(pts)):
        y, z = pts[i]
        ny, nz = _outward(pts, i)
        rings.append([(x - off, y + ny * (nv - w / 2), z + nz * (nv - w / 2)), (x - off, y + ny * (nv + w / 2), z + nz * (nv + w / 2))])
    em.loft(rings, L.BRASS, caps=False, closed=False)


def rail(fb: FB, pts, w: float, h: float, mat: str, caps: bool = True):
    """A rectangular bar through the points (x, y, z) with a w x h section (w across y, h along z), the section kept upright."""
    rings = [[(x, y - w / 2, z - h / 2), (x, y + w / 2, z - h / 2), (x, y + w / 2, z + h / 2), (x, y - w / 2, z + h / 2)] for (x, y, z) in pts]
    return fb.loft(rings, mat, caps=caps, closed=True)


def hex_pad(em: FB, x: float, y: float, z: float, r: float, facing, mat: str = L.TRIM, up=(0, 0, 1)) -> None:
    """A flat hexagon (a bolt head) of circumradius r at (x, y, z) on a surface whose normal is `facing`."""
    f = Vector(facing).normalized()
    u = Vector(up) - f * Vector(up).dot(f)
    u = u.normalized() if u.length > 1e-6 else Vector((1, 0, 0))
    r_ = f.cross(u)
    c = Vector((x, y, z))
    em.face([tuple(c + (r_ * math.cos(math.radians(60 * k)) + u * math.sin(math.radians(60 * k))) * r) for k in range(6)], mat, tuple(f))


def stencil(em: FB, text: str, center, height: float, facing, up, cell: str = "white_dim", mat: str = L.LAMP_DIM, tracking: float = 0.0, align: str = "center") -> float:
    """A lit placard: lettering as crisp flat geometry painted as a lamp (a few hundred triangles a word)."""
    return em.text(text, center, height, facing, mat, up=up, cell=cell, tracking=tracking, align=align)


def ink(fine: FB, text: str, center, height: float, up=(1, 0, 0), tracking: float = 0.003, facing=(0, 0, 1), mat: str = L.RUBBER) -> float:
    """Dark lettering printed on a light plate (the ivory control plates): crisp flat geometry like the lit placards."""
    return fine.text(text, center, height, facing, mat, up=up, tracking=tracking)


# =========================================================================================================== the canopy
def latch(b: Parts, x: float, s: int) -> None:
    """A canopy latch on the sill rail at station x (s = -1 port, +1 starboard)."""
    fb, fine, em = b.body, b.fine, b.emit
    y = s * 0.62
    fb.box((x - 0.050, y - 0.046, SILL_Z - 0.052), (x + 0.050, y + 0.046, SILL_Z + 0.012), L.STRUCT)
    fine.box((x - 0.040, y - 0.036, SILL_Z + 0.012), (x + 0.040, y + 0.036, SILL_Z + 0.0215), L.TRIM)
    em.box((x - 0.0405, y - 0.0365, SILL_Z + 0.0214), (x + 0.0405, y - 0.0335, SILL_Z + 0.0224), L.BRASS)
    fine.cyl((x - 0.018, y, SILL_Z + 0.0215), (x - 0.018, y, SILL_Z + 0.0290), 0.0080, L.STRUCT, seg=12)
    fine.cbox((x + 0.010, y, SILL_Z + 0.0270), (0.066, 0.015, 0.0075), L.STRUCT, Rz(-12 * s))
    fine.cyl((x + 0.040, y + s * 0.006, SILL_Z + 0.0215), (x + 0.040, y + s * 0.006, SILL_Z + 0.0300), 0.0060, L.STRUCT, seg=10)
    em.lamp_cyl((x - 0.028, y - s * 0.021, SILL_Z + 0.0215), (x - 0.028, y - s * 0.021, SILL_Z + 0.0234), 0.0040, "green", L.LAMP_DIM, seg=8)


def canopy(b: Parts) -> None:
    """The bows, the sill rails, the spine, the mirror, the jettison ring."""
    fb, fine, em = b.body, b.fine, b.emit
    # ---- the front bow: the biggest thing the pilot sees in flight. Gunmetal, a matte liner on the face towards the pilot with a lit line on its inner
    # edge and a brass line on its outer edge, a row of bolts between, a rubber seal where the glass meets it
    fw, fd = 0.046, 0.062
    sweep(fb, 0.62, rect_sec(fw, fd, 0.010), L.STRUCT)
    lit_line(em, 0.62, fd / 2 + 0.0008, -0.0195, 0.0036, "cyan_dim")
    brass_line(em, 0.62, fd / 2 + 0.0008, 0.0195, 0.0024)
    bolt_row(em, 0.62, fd / 2 + 0.0008, 0.0, 0.09, r=0.0050)
    # ---- the rear bows: slimmer still, the mid one with a liner and a lit line too
    mw, md = 0.036, 0.050
    sweep(fb, -0.34, rect_sec(mw, md, 0.008), L.STRUCT)
    lit_line(em, -0.34, md / 2 + 0.0008, -0.0145, 0.003, "cyan_dim")
    bolt_row(em, -0.34, md / 2 + 0.0008, 0.0, 0.12, r=0.0040)
    sweep(fb, -1.05, rect_sec(0.044, 0.060, 0.010), L.STRUCT)
    # ---- the sill rails with a lit inner edge, the latch blocks (a brass inlay each) and a row of quarter-turn fasteners
    for s in (-1, 1):
        pts = [(-1.15, s * 0.62, SILL_Z), (0.40, s * 0.62, SILL_Z), (0.62, s * canopy_half(0.62), SILL_Z)]
        rail(fb, pts, 0.07, 0.05, L.STRUCT)
        rail(fine, [(-1.12, s * 0.62, SILL_Z + 0.0262), (0.40, s * 0.62, SILL_Z + 0.0262)], 0.050, 0.0012, L.TRIM)
        em.lamp_cbox((-0.36, s * 0.586, SILL_Z + 0.0265), (1.52, 0.006, 0.003), "ice_dim" if s < 0 else "cyan_dim", L.LAMP_DIM)
        for xl in (-0.70, -0.10, 0.30):
            latch(b, xl, s)
        for k in range(14):
            hex_pad(em, -1.02 + k * 0.105, s * 0.640, SILL_Z + 0.0268, 0.0055, (0, 0, 1), L.TRIM, up=(1, 0, 0))
    # ---- the spine over the head, with an overhead strip (a lit placard and two lamps) and the hinge pins at the back
    spine = [(x, 0.0, canopy_top(x)) for x in (0.62, 0.35, 0.05, -0.34, -0.70, -1.05)]
    rail(fb, spine, 0.046, 0.040, L.STRUCT)
    rail(fine, [(0.58, 0.0, canopy_top(0.58) - 0.0215), (-0.30, 0.0, canopy_top(-0.30) - 0.0215)], 0.030, 0.0012, L.RUBBER)
    with b.at(basis((0.10, 0.0, canopy_top(0.10) - 0.0225), (1, 0, 0), (0, 0, -1))):
        stencil(em, "CANOPY", (0.0, 0.0, 0.0006), 0.0075, (0, 0, 1), (1, 0, 0), "white_dim")
        for k, cell in enumerate(("green", "amber", "ice")):
            em.lamp_cyl((-0.060 + k * 0.012, 0.0, 0.0), (-0.060 + k * 0.012, 0.0, 0.0016), 0.0035, cell, L.LAMP_DIM, seg=8)
    # ---- the canopy jettison ring: a ring of striped segments (amber lit / dark rubber) on a post under the front bow's crown
    jz = canopy_top(0.58) - 0.032
    n = 16
    ring = [(0.575, 0.026 * math.cos(2 * math.pi * k / n), jz - 0.026 + 0.026 * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
    for k in range(n):
        if k % 2 == 0:
            em.lamp_cyl(ring[k], ring[k + 1], 0.0058, "amber", L.LAMP_DIM, seg=6)
        else:
            fine.cyl(ring[k], ring[k + 1], 0.0058, L.RUBBER, seg=6)
    fine.cyl((0.5875, 0.0, canopy_top(0.5875) - 0.004), (0.575, 0.0, jz), 0.0045, L.TRIM, seg=8)
    # ---- the rear-view mirror on a stalk from the left side of the front bow (off the middle, where the game's HUD draws): a small dark glass in a gunmetal frame with a brass lip
    fine.cyl((0.592, -0.300, 0.258), (0.552, -0.262, 0.212), 0.0065, L.TRIM, seg=8)
    with b.at(T(0.545, -0.256, 0.200) @ Rz(-15) @ Ry(-10)):
        fb.box((-0.011, -0.052, -0.021), (0.011, 0.052, 0.021), L.STRUCT)
        fine.box((-0.0125, -0.046, -0.015), (-0.0105, 0.046, 0.015), L.DGLASS)
        em.box((-0.0136, -0.049, 0.0185), (-0.0118, 0.049, 0.0212), L.BRASS)


# ================================================================================================================= the dash
P0, P1 = (0.575, -0.86), (0.76, -0.37)                         # the instrument face: its lower and upper edge (x, z)
FACE_L = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
FACE_U = ((P1[0] - P0[0]) / FACE_L, (P1[1] - P0[1]) / FACE_L)   # along the face, upwards
FACE_N = (-FACE_U[1], FACE_U[0])                              # out of the face, towards the pilot (back and up)
HOOD = [(0.63, -0.338), (0.72, -0.30), (0.90, -0.285), (1.00, -0.33), (1.06, -0.40)]          # the hood's upper line (x, z)


def face_frame(s: float, y: float = 0.0, lift: float = 0.0) -> Matrix:
    """The frame on the instrument face, the same convention as the console controls (bridge3_controls): origin `s` metres up the face from its
    lower edge and `y` across, `lift` out of it; local x = up along the face, y = to the pilot's right, z = out of the face, towards the pilot."""
    o = (P0[0] + FACE_U[0] * s + FACE_N[0] * lift, y, P0[1] + FACE_U[1] * s + FACE_N[1] * lift)
    return basis(o, (FACE_U[0], 0.0, FACE_U[1]), (FACE_N[0], 0.0, FACE_N[1]))


def hood_z(x: float) -> float:
    for (x0, z0), (x1, z1) in zip(HOOD[:-1], HOOD[1:]):
        if x0 <= x <= x1:
            return lerp(z0, z1, (x - x0) / (x1 - x0))
    return HOOD[-1][1]


def hood_frame(x: float, y: float = 0.0) -> Matrix:
    """A frame on the hood's top at (x, y): local x along the slope (forward), z the normal (up)."""
    d = 0.01
    dz = hood_z(x + d) - hood_z(x - d)
    ang = math.atan2(dz, 2 * d)
    return basis((x, y, hood_z(x)), (math.cos(ang), 0.0, math.sin(ang)), (-math.sin(ang), 0.0, math.cos(ang)))


def decor_disc(em: FB, c, r: float, page: str, up=(1, 0, 0), facing=(0, 0, 1), seg: int = 36, zoom: float = 1.0) -> None:
    """A round picture: a disc of radius r showing the middle of the decor tile `page` (the tile's width = 2 r / zoom), so a round instrument fits a round bezel."""
    u0, v0, u1, v1 = L.DECOR_RECTS[page]
    du, dv = 0.75 / L.DECOR_SIZE[0], 0.75 / L.DECOR_SIZE[1]
    u0, u1, v0, v1 = u0 + du, u1 - du, v0 + dv, v1 - dv
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    f = Vector(facing)
    uu = Vector(up)
    rr = f.cross(uu)                                   # the picture's right in the local frame is (up x facing) seen from the viewer: build with both and let FB.face orient
    pts, uvs = [], []
    for k in range(seg):
        a = 2 * math.pi * k / seg
        ca, sa = math.cos(a), math.sin(a)
        pts.append(tuple(Vector(c) + (rr * ca + uu * sa) * r))
        uvs.append((cu + ca * (u1 - u0) / 2 * zoom * -1.0, cv + sa * (v1 - v0) / 2 * zoom))
    em.face(pts, L.DECOR, facing, uvs=uvs, flag=True)


def mfd(b: Parts, s: float, y: float, w: float, h: float, page: str, keys: bool = True, tag: str | None = None) -> None:
    """A multifunction display on the instrument face: a gunmetal bezel standing proud of it with a row of soft keys on its bottom and top bars, the picture
    (a page of the decor atlas) behind dark glass, a lit hairline at the foot of the glass, a lit placard under it."""
    fb, fine, em = b.body, b.fine, b.emit
    bz, kb, hz = 0.013, 0.016, 0.017
    with b.at(face_frame(s, y)):
        fb.box((-h / 2 - kb, -w / 2 - bz, -0.002), (h / 2 + kb, -w / 2, hz), L.STRUCT)
        fb.box((-h / 2 - kb, w / 2, -0.002), (h / 2 + kb, w / 2 + bz, hz), L.STRUCT)
        fb.box((h / 2, -w / 2, -0.002), (h / 2 + kb, w / 2, hz), L.STRUCT)
        fb.box((-h / 2 - kb, -w / 2, -0.002), (-h / 2, w / 2, hz), L.STRUCT)
        fine.box((-h / 2 - 0.001, -w / 2 - 0.001, -0.002), (h / 2 + 0.001, w / 2 + 0.001, 0.0035), L.DGLASS)
        em.decor((0, 0, 0.0038), w, h, (0, 0, 1), page, up=(1, 0, 0))
        em.lamp_box((-h / 2, -w / 2, 0.0036), (-h / 2 + 0.0014, w / 2, 0.0041), "cyan_dim", L.LAMP_DIM)
        em.box((-h / 2 - kb, -w / 2 - bz, hz - 0.0004), (-h / 2 - kb + 0.0022, w / 2 + bz, hz + 0.0016), L.BRASS)
        if keys:
            for k in range(5):
                yk = -w / 2 + w * (k + 0.5) / 5
                for xs in (-h / 2 - kb / 2, h / 2 + kb / 2):
                    fine.box((xs - 0.0042, yk - 0.0085, hz - 0.001), (xs + 0.0042, yk + 0.0085, hz + 0.0042), L.RUBBER)
                    em.lamp_box((xs - 0.0013, yk - 0.0062, hz + 0.0042), (xs + 0.0013, yk + 0.0062, hz + 0.0049), "ice_dim" if k != 2 else "cyan", L.LAMP_DIM)
        if tag:
            stencil(em, tag, (-h / 2 - kb - 0.0105, 0.0, 0.0006), 0.0058, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.004)


def gauge(b: Parts, s: float, y: float, d: float, page: str, zoom: float = 0.9, tag: str | None = None) -> None:
    """A round standby instrument: a gunmetal housing, a brass ring, dark glass and the round decor picture, four lit ticks on the housing."""
    fb, fine, em = b.body, b.fine, b.emit
    with b.at(face_frame(s, y)):
        fb.cyl((0, 0, -0.002), (0, 0, 0.016), d / 2 + 0.013, L.STRUCT, seg=36)
        em.cyl((0, 0, 0.0158), (0, 0, 0.0172), d / 2 + 0.0126, L.BRASS, seg=36)
        fine.cyl((0, 0, 0.0165), (0, 0, 0.0178), d / 2 + 0.0004, L.DGLASS, seg=36)
        decor_disc(em, (0, 0, 0.0181), d / 2, page, seg=40, zoom=zoom)
        for a in (0, 90, 180, 270):
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            em.lamp_box((ca * (d / 2 + 0.0085) - 0.0015, sa * (d / 2 + 0.0085) - 0.0015, 0.0172), (ca * (d / 2 + 0.0085) + 0.0015, sa * (d / 2 + 0.0085) + 0.0015, 0.0182), "ice_dim", L.LAMP_DIM)
        if tag:
            stencil(em, tag, (-d / 2 - 0.0215, 0.0, 0.0), 0.0058, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.004)


def tog(b: Parts, x: float, y: float, cell: str = "green", guard: bool = False, up: bool = False) -> None:
    """A toggle switch (in the frame of the surface it sits on: x uphill, y across, z out), a small lit pip beside it, optionally under a flip guard."""
    fine, em = b.fine, b.emit
    fine.cyl((x, y, -0.002), (x, y, 0.007), 0.0078, L.STRUCT, seg=10)
    lean = 0.0065 if up else -0.0065
    fine.cyl((x, y, 0.007), (x + lean, y, 0.027), 0.0030, L.TRIM, seg=8, r2=0.0042)
    fine.sphere((x + lean, y, 0.0275), 0.0046, L.TRIM, seg=8, rings=5)
    em.lamp_cyl((x + 0.0175, y, -0.0005), (x + 0.0175, y, 0.0012), 0.0027, cell, L.LAMP_DIM, seg=8)
    if guard:
        for sy in (-1, 1):
            fine.box((x - 0.0020, y + sy * 0.0145 - 0.0016, -0.002), (x + 0.0020, y + sy * 0.0145 + 0.0016, 0.036), L.STRUCT)
        fine.box((x - 0.0030, y - 0.0165, 0.0345), (x + 0.0030, y + 0.0165, 0.0385), L.STRUCT)
        em.lamp_box((x - 0.0030, y - 0.0125, 0.0385), (x + 0.0030, y + 0.0125, 0.0395), "red_dim", L.LAMP_DIM)


def rotary(b: Parts, x: float, y: float, r: float = 0.0115, cell: str = "ice", ticks: int = 9, sweep_deg: float = 240.0, pointer_deg: float = 20.0) -> None:
    """A rotary selector: a skirt, a knurled knob with a lit pointer, tick dots round it."""
    fine, em = b.fine, b.emit
    fine.cyl((x, y, -0.002), (x, y, 0.005), r + 0.005, L.STRUCT, seg=20)
    fine.cyl((x, y, 0.005), (x, y, 0.0165), r, L.TRIM, seg=20, r2=r * 0.9)
    fine.cyl((x, y, 0.0165), (x, y, 0.0178), r * 0.82, L.STRUCT, seg=20)
    for k in range(ticks):
        t = math.radians(-sweep_deg / 2 + sweep_deg * k / (ticks - 1) + 90)
        em.lamp_box((x + math.cos(t) * (r + 0.0105) - 0.0011, y + math.sin(t) * (r + 0.0105) - 0.0011, -0.0004), (x + math.cos(t) * (r + 0.0105) + 0.0011, y + math.sin(t) * (r + 0.0105) + 0.0011, 0.0010), "ice_dim", L.LAMP_DIM)
    px, py = x + math.cos(math.radians(90 + pointer_deg)) * r * 0.55, y + math.sin(math.radians(90 + pointer_deg)) * r * 0.55
    em.lamp_cyl((px, py, 0.0178), (px, py, 0.0188), 0.0018, cell, L.LAMP, seg=6)


def label_row(b: Parts, x: float, y0: float, items, height: float = 0.0056, cell: str = "ice_dim") -> None:
    """Lit placards in a row on a surface frame (x uphill, y across): items = [(y offset, text)]."""
    for (dy, txt) in items:
        stencil(b.emit, txt, (x, y0 + dy, -0.0004), height, (0, 0, 1), (1, 0, 0), cell, tracking=0.0035)


def dash(b: Parts) -> None:
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    rng = random.Random(11)
    # ---- the block: anti-glare hood over a face that leans back, the front lip, the front down to the floor
    prof = [(0.575, -0.86), (0.76, -0.37), (0.63, -0.365), (0.63, -0.338), (0.72, -0.30), (0.90, -0.285), (1.00, -0.33), (1.06, -0.40), (1.06, -1.04), (0.50, -1.04), (0.50, -0.86)]
    fb.extrude_y(prof, -0.57, 0.57, L.STRUCT)
    # the hood's top: a dark matte anti-glare inlay with a lit line along its front edge and a brass line at the rear edge, the lip with a lit slot under it
    with b.at(hood_frame(0.82, 0.0)):
        fine.box((-0.17, -0.545, -0.001), (0.17, 0.545, 0.0025), L.RUBBER)
    em.box((0.628, -0.57, -0.3400), (0.642, 0.57, -0.3345), L.BRASS)
    em.lamp_box((0.640, -0.545, -0.3665), (0.700, 0.545, -0.3640), "ice_dim", L.LAMP_DIM)          # the light under the lip, over the face
    # ---- the HUD projector on the hood (the picture itself is drawn by the game): a gunmetal housing that tapers towards the canopy, a dark lens on its slope, cooling
    # slats on the sides, a brass line, its legend and three status lamps on the face towards the pilot
    with b.at(hood_frame(0.80, 0.0)):
        fb.extrude_y([(-0.060, -0.002), (0.060, -0.002), (0.060, 0.026), (0.034, 0.050), (-0.030, 0.050), (-0.060, 0.030)], -0.088, 0.088, L.STRUCT)
        with b.at(T(0.002, 0.0, 0.050) @ Ry(8)):
            fine.box((-0.030, -0.074, -0.0005), (0.030, 0.074, 0.0012), L.DGLASS)
            em.lamp_box((-0.030, -0.074, 0.0012), (0.030, -0.0715, 0.0019), "cyan_dim", L.LAMP_DIM)
            em.lamp_box((-0.030, 0.0715, 0.0012), (0.030, 0.074, 0.0019), "cyan_dim", L.LAMP_DIM)
        em.box((-0.0603, -0.0885, 0.0252), (0.0603, 0.0885, 0.0272), L.BRASS)
        for k in range(8):
            fine.box((-0.046 + k * 0.0125, -0.0900, 0.006), (-0.0425 + k * 0.0125, -0.0878, 0.022), L.RUBBER)
            fine.box((-0.046 + k * 0.0125, 0.0878, 0.006), (-0.0425 + k * 0.0125, 0.0900, 0.022), L.RUBBER)
        with b.at(basis((-0.0603, 0.0, 0.0), (0, 0, 1), (-1, 0, 0))):
            stencil(em, "HUD", (0.0125, 0.0, 0.0004), 0.0070, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.006)
            for dy, cell in ((-0.056, "green"), (-0.038, "cyan"), (0.038, "amber"), (0.056, "ice")):
                em.lamp_cyl((0.0125, dy, -0.0004), (0.0125, dy, 0.0014), 0.0036, cell, L.LAMP_DIM, seg=8)
    # ---- the two annunciators at the rear corners of the hood: MASTER CAUTION (amber) and MASTER ARM (red): a dark bezel, a lit lens, dark lettering
    for (yy, txt, cell) in ((-0.215, "MASTER CAUTION", "amber_dim"), (0.215, "MASTER ARM", "red_dim")):
        with b.at(hood_frame(0.675, yy)):
            fine.box((-0.021, -0.050, -0.002), (0.021, 0.050, 0.0045), L.STRUCT)
            em.lamp_box((-0.016, -0.045, 0.0045), (0.016, 0.045, 0.0058), cell, L.LAMP_DIM)
            fine.text(txt, (0.0, 0.0, 0.0061), 0.0065, (0, 0, 1), L.RUBBER, up=(1, 0, 0))
    # ---- a standby compass (a ball in a bracket) at the foot of the front bow, ambient light sensors, a dimmer wheel on the hood
    with b.at(hood_frame(0.72, 0.24)):
        fine.box((-0.022, -0.022, -0.002), (0.022, 0.022, 0.010), L.STRUCT)
        fine.cyl((0.0, 0.0, 0.010), (0.0, 0.0, 0.022), 0.0085, L.TRIM, seg=10)
        fine.sphere((0.0, 0.0, 0.040), 0.021, L.DGLASS, seg=16, rings=10)
        em.lamp_cyl((0.016, 0.0, 0.0405), (0.0172, 0.0, 0.0408), 0.004, "amber", L.LAMP_DIM, seg=8)
    for yy in (-0.30, 0.30, -0.45, 0.45):
        with b.at(hood_frame(0.69, yy)):
            fine.cyl((0, 0, -0.002), (0, 0, 0.004), 0.011, L.STRUCT, seg=14)
            fine.cyl((0, 0, 0.004), (0, 0, 0.0048), 0.0075, L.DGLASS, seg=14)
    with b.at(hood_frame(0.77, -0.30)):
        fine.cyl((0, 0, -0.002), (0, 0, 0.006), 0.017, L.STRUCT, seg=20)
        fine.cyl((0, 0, 0.006), (0, 0, 0.0145), 0.0125, L.TRIM, seg=20)
        for k in range(12):
            a = 2 * math.pi * k / 12
            fine.box((math.cos(a) * 0.0125 - 0.0008, math.sin(a) * 0.0125 - 0.0008, 0.006), (math.cos(a) * 0.0125 + 0.0008, math.sin(a) * 0.0125 + 0.0008, 0.0145), L.STRUCT)
        stencil(em, "DIM", (0.0, 0.034, 0.0002), 0.0058, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.004)
    # ---- the hood's detail: steel frames along its two edges with their screws, a row of six round caution lamps at its rear edge, vent slots either side of the HUD, panel seams
    for sd in (-1, 1):
        with b.at(hood_frame(0.825, sd * 0.552)):
            fine.box((-0.175, -0.016, -0.001), (0.175, 0.016, 0.0030), L.STRUCT)
            for k in range(6):
                hex_pad(em, -0.150 + k * 0.060, 0.0, 0.0031, 0.0048, (0, 0, 1), L.TRIM, up=(1, 0, 0))
        with b.at(hood_frame(0.84, sd * 0.36)):
            fine.box((-0.16, -0.0012, -0.001), (0.16, 0.0012, 0.0028), L.STRUCT)
        with b.at(hood_frame(0.80, sd * 0.16)):
            for k in range(5):
                fine.box((-0.040 + k * 0.020 - 0.0045, -0.026, -0.001), (-0.040 + k * 0.020 + 0.0045, 0.026, 0.0016), L.DGLASS)
            em.box((-0.052, -0.030, 0.0), (0.052, -0.0285, 0.0019), L.BRASS)
            em.box((-0.052, 0.0285, 0.0), (0.052, 0.030, 0.0019), L.BRASS)
    with b.at(hood_frame(0.662, 0.0)):
        for k in range(6):
            yy = -0.125 + k * 0.050
            fine.cyl((0.0, yy, -0.002), (0.0, yy, 0.005), 0.0105, L.STRUCT, seg=14)
            em.lamp_cyl((0.0, yy, 0.0045), (0.0, yy, 0.0062), 0.0072, ("amber", "green", "cyan", "amber", "green", "red")[k], L.LAMP_DIM, seg=12)
    # ---- the instrument face: a coaming round it (rails along the sides and the foot with a brass line), ribs between the zones, corner screws
    with b.at(face_frame(0.0, 0.0)):
        fb.box((-0.004, -0.570, -0.002), (0.010, 0.570, 0.020), L.STRUCT)
        em.box((0.0098, -0.566, 0.0196), (0.0112, 0.566, 0.0212), L.BRASS)
        for sy in (-1, 1):
            fb.box((0.0, sy * 0.5575 - 0.0125, -0.002), (FACE_L, sy * 0.5575 + 0.0125, 0.014), L.STRUCT)
        for sy in (-1, 1):
            fb.box((0.012, sy * 0.205 - 0.003, -0.002), (FACE_L - 0.004, sy * 0.205 + 0.003, 0.012), L.STRUCT)            # ribs between the zones
            em.lamp_box((0.012, sy * 0.205 - 0.0008, 0.0119), (FACE_L - 0.004, sy * 0.205 + 0.0008, 0.0127), "ice_dim", L.LAMP_DIM)
        for (sv, yv) in ((0.012, -0.545), (0.012, 0.545), (FACE_L - 0.012, -0.545), (FACE_L - 0.012, 0.545)):
            hex_pad(em, sv, yv, 0.0142, 0.0058, (0, 0, 1), L.TRIM, up=(1, 0, 0))
    # ---- the displays: a wide one in the middle, one on each side, standby instruments and the engine page between them, the caution panel
    mfd(b, 0.350, 0.0, 0.300, 0.165, "radar", tag="MAIN")
    mfd(b, 0.350, -0.318, 0.206, 0.150, "navmfd", tag="NAV")
    mfd(b, 0.350, 0.318, 0.206, 0.150, "weapons", tag="WPN")
    gauge(b, 0.175, -0.118, 0.098, "attitude", zoom=0.90, tag="ATT")
    gauge(b, 0.175, 0.118, 0.098, "compass", zoom=0.97, tag="HDG")
    with b.at(face_frame(0.175, 0.0)):
        fb.box((-0.058, -0.030, -0.002), (0.058, 0.030, 0.012), L.STRUCT)
        fine.box((-0.052, -0.025, 0.012), (0.052, 0.025, 0.0150), L.DGLASS)
        em.decor((0, 0, 0.0153), 0.050, 0.104, (0, 0, 1), "engine", up=(1, 0, 0))
    with b.at(face_frame(0.175, -0.345)):
        fb.box((-0.058, -0.095, -0.002), (0.058, 0.095, 0.011), L.STRUCT)
        fine.box((-0.053, -0.090, 0.011), (0.053, 0.090, 0.0145), L.DGLASS)
        em.decor((0, 0, 0.0148), 0.180, 0.106, (0, 0, 1), "gauges", up=(1, 0, 0))
        stencil(em, "ENG", (-0.0655, -0.080, 0.0004), 0.0058, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.004)
    with b.at(face_frame(0.175, 0.345)):
        fb.box((-0.058, -0.095, -0.002), (0.058, 0.095, 0.011), L.STRUCT)
        fine.box((-0.053, -0.090, 0.011), (0.053, 0.090, 0.0145), L.DGLASS)
        em.decor((0, 0, 0.0148), 0.170, 0.0637, (0, 0, 1), "caution", up=(1, 0, 0))
        stencil(em, "CAUTION", (-0.0655, -0.070, 0.0004), 0.0058, (0, 0, 1), (1, 0, 0), "amber_dim", tracking=0.004)
    # ---- the switch banks: the left one (power, fuel, hydraulics), the right one (weapons, under guards), a rotary and a keypad in the middle
    for r_, (xr, tags) in enumerate(((0.082, ("BATT", "GEN L", "GEN R", "FUEL", "XFER", "HYD", "APU", "O2")), (0.032, ("NAV", "STROBE", "FORM", "LAND", "CABIN", "FLOOD", "CHAFF", "FLARE")))):
        with b.at(face_frame(0.0, 0.0)):
            for k in range(8):
                yy = -0.508 + k * 0.0395
                tog(b, xr, yy, ("green", "green", "green", "amber", "cyan", "green", "amber", "cyan")[(k + r_) % 8], up=(k * 3 + r_) % 5 != 0)
                stencil(em, tags[k], (xr + 0.0235, yy, -0.0004), 0.0050, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.003)
    with b.at(face_frame(0.0, 0.0)):
        for k in range(5):                                               # the weapons bank, under flip guards, red and amber
            yy = 0.285 + k * 0.0535
            tog(b, 0.062, yy, "amber" if k % 2 else "red", guard=(k in (0, 2, 4)), up=(k % 2 == 0))
        stencil(em, "ARM", (0.0895, 0.285, -0.0004), 0.0056, (0, 0, 1), (1, 0, 0), "red_dim", tracking=0.003)
        stencil(em, "MSL", (0.0895, 0.392, -0.0004), 0.0056, (0, 0, 1), (1, 0, 0), "amber_dim", tracking=0.003)
        stencil(em, "GUN", (0.0895, 0.499, -0.0004), 0.0056, (0, 0, 1), (1, 0, 0), "amber_dim", tracking=0.003)
        for k, yy in enumerate((-0.170, -0.105, 0.105, 0.170)):          # selector knobs between the banks and the keypad
            rotary(b, 0.060, yy, 0.0115, ("ice", "cyan", "green", "amber")[k], pointer_deg=(-70, -20, 25, 60)[k])
        CT.key_grid(fine, em, 0.020, -0.040, 2, 4, 0.0265, rng, cells=("ice_dim", "ice_dim", "cyan_dim", "amber_dim"), size=0.0205)
    # ---- the knee panel (the front of the footwell: a rubber knee pad, a vent, a placard) and the cheeks of the block
    soft.box((0.4995, -0.31, -0.95), (0.516, 0.31, -0.875), L.RUBBER)
    for k in range(9):
        fine.box((0.4985, -0.18 + k * 0.040, -1.00), (0.5005, -0.164 + k * 0.040, -0.945), L.RUBBER)


# ====================================================================================================== the side consoles
CON_A = math.atan(0.05)


def ctop(x: float) -> float:
    """The top of the side consoles at station x (a plane rising a little towards the dash)."""
    return -0.445 + 0.05 * (x + 0.20)


def console_frame(x: float = 0.0, y: float = 0.0) -> Matrix:
    """A frame on the top of a side console at station x, y: local x along the slope (forward), y to the pilot's right, z the normal (up)."""
    return basis((x, y, ctop(x)), (math.cos(CON_A), 0.0, math.sin(CON_A)), (-math.sin(CON_A), 0.0, math.cos(CON_A)))


def console_body(b: Parts, y0: float, y1: float) -> None:
    """The shell of a side console (carbon) with its steel top plate, a brass line on the outboard edge, a lit line on the inboard one, four corner screws."""
    fb, fine, em = b.body, b.fine, b.emit
    fb.extrude_y([(-0.20, -1.06), (-0.20, -0.457), (0.42, -0.426), (0.42, -1.06)], y0, y1, L.COMPOSITE)
    fine.extrude_y([(-0.20, -0.457), (0.42, -0.426), (0.42, -0.4135), (-0.20, -0.4445)], y0, y1, L.STRUCT)
    left = y0 < 0
    with b.at(console_frame(0.0, 0.0)):
        if left:
            em.box((-0.20, y0, 0.0004), (0.42, y0 + 0.0030, 0.0016), L.BRASS)
            em.lamp_box((-0.20, y1 - 0.0030, 0.0004), (0.42, y1, 0.0014), "ice_dim", L.LAMP_DIM)
        else:
            em.box((-0.20, y1 - 0.0030, 0.0004), (0.42, y1, 0.0016), L.BRASS)
            em.lamp_box((-0.20, y0, 0.0004), (0.42, y0 + 0.0030, 0.0014), "ice_dim", L.LAMP_DIM)
        for xx in (-0.17, 0.39):
            for yy in (y0 + 0.014, y1 - 0.014):
                hex_pad(em, xx, yy, 0.0013, 0.0050, (0, 0, 1), L.TRIM, up=(1, 0, 0))


def grab_handle(b: Parts, x: float, y: float) -> None:
    """A grab handle on top of a console's rear end (the pilot climbs in over it): a steel bar on two posts."""
    fine = b.fine
    with b.at(console_frame(0.0, 0.0)):
        for dx in (-0.045, 0.045):
            fine.cyl((x + dx, y, -0.001), (x + dx, y, 0.040), 0.0075, L.TRIM, seg=10)
        fine.cyl((x - 0.045, y, 0.040), (x + 0.045, y, 0.040), 0.0085, L.TRIM, seg=10)


def conduit(b: Parts, y: float, z: float, x0: float, x1: float) -> None:
    """A cable conduit along the inboard face of a console at height z (y is the face): a rubber tube in steel clips and a lead dropping to the floor."""
    fine, soft = b.fine, b.soft
    sgn = 1.0 if y < 0 else -1.0                                                   # towards the pilot's axis
    soft.cyl((x0, y + sgn * 0.0075, z), (x1, y + sgn * 0.0075, z), 0.0105, L.RUBBER, seg=10)
    soft.cyl((x1, y + sgn * 0.0075, z), (x1, y + sgn * 0.0075, -1.04), 0.0065, L.RUBBER, seg=8)
    for k in range(5):
        xc = lerp(x0 + 0.03, x1 - 0.03, k / 4)
        fine.box((xc - 0.007, min(y, y + sgn * 0.019), z - 0.0175), (xc + 0.007, max(y, y + sgn * 0.019), z + 0.0175), L.STRUCT)


def throttle(b: Parts) -> None:
    """The throttle quadrant in the left console's frame: a plate with a slot and detent ticks, IDLE / MIL / AB legends, and the lever with its grip (finger
    grooves, two buttons and a hat on the head)."""
    fine, em, soft = b.fine, b.emit, b.soft
    y = -0.500
    fine.box((-0.130, y - 0.046, -0.003), (0.380, y + 0.046, 0.0035), L.IVORY)
    fine.box((-0.095, y - 0.0115, 0.0030), (0.345, y + 0.0115, 0.0042), L.RUBBER)
    for k in range(12):
        fine.box((-0.095 + k * 0.040 - 0.0008, y + 0.0165, 0.0030), (-0.095 + k * 0.040 + 0.0008, y + 0.0235, 0.0040), L.STRUCT)
    em.lamp_box((0.205, y + 0.0155, 0.0030), (0.345, y + 0.0165, 0.0036), "amber", L.LAMP_DIM)                          # the afterburner range
    for (xx, txt) in ((-0.060, "IDLE"), (0.115, "MIL"), (0.275, "AB")):
        ink(fine, txt, (xx, y - 0.033, 0.0036), 0.0085, tracking=0.005)
    ink(fine, "THROTTLE", (0.12, y + 0.0370, 0.0036), 0.0050, tracking=0.006)
    # the lever: a pivot housing with a brass collar, a shaft leaning forward, the grip
    fine.cyl((0.02, y, 0.0), (0.02, y, 0.028), 0.030, L.STRUCT, seg=32, r2=0.024)
    em.cyl((0.02, y, 0.0275), (0.02, y, 0.0300), 0.0305, L.BRASS, seg=32, r2=0.0245)
    fine.cyl((0.02, y, 0.028), (0.075, y, 0.150), 0.0105, L.TRIM, seg=12)
    soft.cyl((0.072, y, 0.140), (0.108, y, 0.252), 0.0235, L.RUBBER, seg=24, r2=0.0275)
    fine.cyl((0.108, y, 0.252), (0.1115, y, 0.263), 0.0285, L.DGLASS, seg=24)
    for k in range(3):                                                                         # finger grooves
        zz = 0.165 + k * 0.030
        fine.cyl((0.072 + (zz - 0.140) * 0.32, y, zz), (0.072 + (zz - 0.140) * 0.32, y, zz + 0.004), 0.0272 + k * 0.0006, L.STRUCT, seg=24)
    for dy, cell in ((-0.010, "cyan"), (0.010, "amber")):                                       # two buttons on the head
        em.lamp_cyl((0.1115 - 0.012, y + dy, 0.2635), (0.1115 - 0.012, y + dy, 0.2655), 0.0042, cell, L.LAMP_DIM, seg=8)
    for (dx, dy) in ((0.007, 0.0), (-0.007, 0.0), (0.0, 0.007), (0.0, -0.007)):                 # the hat switch
        em.lamp_box((0.1195 + dx - 0.0022, y + dy - 0.0022, 0.2635), (0.1195 + dx + 0.0022, y + dy + 0.0022, 0.2650), "ice_dim", L.LAMP_DIM)


def trim_wheel(b: Parts, x: float, y: float) -> None:
    """A thumb wheel in a slot: a wheel standing half out of the surface (axis along y) with three grooves and a lit tick on its rim."""
    fine, em = b.fine, b.emit
    fine.box((x - 0.034, y - 0.020, -0.002), (x + 0.034, y + 0.020, 0.003), L.IVORY)
    fine.cyl((x, y - 0.013, 0.0035), (x, y + 0.013, 0.0035), 0.020, L.STRUCT, seg=28)
    for dy in (-0.008, 0.0, 0.008):
        fine.cyl((x, y + dy - 0.0012, 0.0035), (x, y + dy + 0.0012, 0.0035), 0.0206, L.STRUCT, seg=28)
    em.lamp_box((x - 0.0016, y - 0.0040, 0.0233), (x + 0.0016, y + 0.0040, 0.0243), "ice", L.LAMP_DIM)


def left_console(b: Parts) -> None:
    fine, em, soft = b.fine, b.emit, b.soft
    rng = random.Random(21)
    y0, y1 = -0.610, -0.395
    console_body(b, y0, y1)
    with b.at(console_frame(0.0, 0.0)):
        throttle(b)
        trim_wheel(b, -0.100, -0.430)
        # the armrest at the rear: a leather pad on a steel frame with a brass edge
        fine.box((-0.195, -0.600, -0.002), (-0.045, -0.405, 0.006), L.STRUCT)
        soft.box((-0.185, -0.592, 0.006), (-0.055, -0.413, 0.030), L.LEATHER)
        em.box((-0.056, -0.592, 0.0060), (-0.0545, -0.413, 0.0300), L.BRASS)
        # a row of toggles along the outboard edge with their legends
        for k, t in enumerate(("L GEN", "R GEN", "PUMP", "INTL", "EXTL", "ANTI")):
            xx = 0.040 + k * 0.047
            tog(b, xx, -0.580, ("green", "amber", "green", "cyan", "green", "amber")[k], up=(k % 2 == 0))
            stencil(em, t, (xx, -0.598, 0.0004), 0.0046, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.003)
        # the comms panel (forward): an ivory plate with a small signal display, a keypad, two rotaries, a lit placard
        with b.at(T(0.300, -0.500, 0.0)):
            fine.box((-0.075, -0.085, -0.002), (0.095, 0.085, 0.0035), L.IVORY)
            fine.box((0.040, -0.062, 0.0035), (0.088, 0.062, 0.0085), L.STRUCT)
            fine.box((0.043, -0.059, 0.0085), (0.085, 0.059, 0.0098), L.DGLASS)
            em.decor((0.064, 0.0, 0.0100), 0.116, 0.0435, (0, 0, 1), "wave", up=(1, 0, 0))
            CT.key_grid(fine, em, -0.050, -0.030, 3, 4, 0.0245, rng, cells=("ice_dim", "ice_dim", "cyan_dim", "ice_dim", "amber_dim"), size=0.0195)
            rotary(b, 0.000, 0.058, 0.0115, "cyan", pointer_deg=30)
            rotary(b, -0.045, 0.058, 0.0115, "ice", pointer_deg=-40)
            ink(fine, "COMMS", (-0.066, 0.0, 0.0036), 0.0070, tracking=0.005)
            ink(fine, "SQL", (-0.0075, 0.058, 0.0036), 0.0048, tracking=0.004)
            ink(fine, "VOL", (-0.0525, 0.058, 0.0036), 0.0048, tracking=0.004)
    grab_handle(b, -0.15, -0.585)
    conduit(b, -0.395, -0.93, -0.18, 0.40)
    # the inboard face (towards the pilot's knee): a vent, a map pocket with a brass edge, a lit placard
    for k in range(7):
        fine.box((-0.12 + k * 0.045, -0.3950, -0.84), (-0.098 + k * 0.045, -0.3925, -0.74), L.RUBBER)
    soft.box((0.05, -0.3975, -0.70), (0.44, -0.3935, -0.52), L.RUBBER)
    em.box((0.05, -0.3975, -0.5224), (0.44, -0.3930, -0.5192), L.BRASS)
    stencil(em, "FLT", (0.245, -0.3918, -0.61), 0.0100, (0, 1, 0), (0, 0, 1), "ice_dim", tracking=0.0)


def right_console(b: Parts) -> None:
    fine, em = b.fine, b.emit
    rng = random.Random(22)
    y0, y1 = 0.395, 0.610
    console_body(b, y0, y1)
    with b.at(console_frame(0.0, 0.0)):
        # the sensor scope forward: a square display in a gunmetal bezel on a slanted pad
        with b.at(T(0.280, 0.500, 0.0) @ Ry(-24)):
            fine.box((-0.095, -0.095, -0.004), (0.095, 0.095, 0.016), L.STRUCT)
            fine.box((-0.085, -0.085, 0.016), (0.085, 0.085, 0.0185), L.DGLASS)
            em.decor((0.0, 0.0, 0.0188), 0.162, 0.162, (0, 0, 1), "radar", up=(1, 0, 0))
        # the sensor controls: a trackball, three sliders (gain, range, filter) with their legends
        fine.box((-0.030, 0.408, -0.002), (0.172, 0.572, 0.0030), L.IVORY)
        CT.trackball(fine, em, 0.080, 0.440, r=0.024)
        CT.slider_bank(fine, em, 0.070, 0.505, 3, 0.030, 0.130, rng, cells=("cyan", "green", "amber"))
        for k, t in enumerate(("GAIN", "RNG", "FLT")):
            ink(fine, t, (-0.0105, 0.505 + k * 0.030, 0.0031), 0.0046)
        ink(fine, "SENSOR", (0.150, 0.490, 0.0031), 0.0056, tracking=0.005)
        # a row of toggles along the outboard edge and the ejection arm: a hazard-striped plate (amber lit and dark rubber) at the rear
        for k, t in enumerate(("ECM", "RWR", "JAM", "IFF", "LASE")):
            tog(b, -0.080 + k * 0.047, 0.580, ("green", "cyan", "green", "amber", "green")[k], up=(k % 2 == 1))
            stencil(em, t, (-0.080 + k * 0.047, 0.598, 0.0004), 0.0046, (0, 0, 1), (1, 0, 0), "ice_dim", tracking=0.003)
        fine.box((-0.170, 0.440, -0.003), (-0.100, 0.550, 0.004), L.STRUCT)
        for k in range(7):
            yy = 0.4475 + k * 0.0150
            if k % 2 == 0:
                em.lamp_box((-0.160, yy - 0.0065, 0.0040), (-0.110, yy + 0.0065, 0.0070), "amber_dim", L.LAMP_DIM)
            else:
                fine.box((-0.160, yy - 0.0065, 0.0040), (-0.110, yy + 0.0065, 0.0070), L.RUBBER)
        stencil(em, "EJECT ARM", (-0.1805, 0.495, 0.0004), 0.0055, (0, 0, 1), (1, 0, 0), "red_dim", tracking=0.005)
    for k in range(7):
        fine.box((-0.12 + k * 0.045, 0.3925, -0.84), (-0.098 + k * 0.045, 0.3950, -0.74), L.RUBBER)
    stencil(em, "SENS", (0.245, 0.3918, -0.61), 0.0100, (0, -1, 0), (0, 0, 1), "ice_dim", tracking=0.0)
    grab_handle(b, -0.15, 0.585)
    conduit(b, 0.395, -0.93, -0.18, 0.40)


# ============================================================================================================ stick, seat, floor
def stick(b: Parts) -> None:
    """The stick between the knees: a bellows boot on the floor, a steel column with a brass collar, a moulded grip with a trigger, a hat switch and two buttons."""
    fine, em, soft = b.fine, b.emit, b.soft
    soft.cyl((0.420, 0.0, -1.04), (0.404, 0.0, -0.90), 0.062, L.RUBBER, seg=20, r2=0.034)
    for k in range(4):                                                                          # the bellows' folds
        zz = -1.02 + k * 0.034
        soft.cyl((0.420 - (zz + 1.04) * 0.114, 0.0, zz), (0.420 - (zz + 1.04) * 0.114, 0.0, zz + 0.010), 0.062 - (zz + 1.04) * 0.20 + 0.004, L.RUBBER, seg=20)
    fine.cyl((0.404, 0.0, -0.90), (0.372, 0.0, -0.60), 0.0155, L.TRIM, seg=12)
    fine.cyl((0.372, 0.0, -0.60), (0.372, 0.0, -0.58), 0.026, L.STRUCT, seg=16)
    em.cyl((0.372, 0.0, -0.600), (0.372, 0.0, -0.5935), 0.0275, L.BRASS, seg=16)
    soft.cyl((0.372, 0.0, -0.58), (0.360, 0.0, -0.52), 0.024, L.RUBBER, seg=28, r2=0.031)
    soft.cyl((0.360, 0.0, -0.52), (0.352, 0.0, -0.455), 0.031, L.RUBBER, seg=28, r2=0.0275)
    fine.cyl((0.352, 0.0, -0.455), (0.350, 0.0, -0.438), 0.0315, L.DGLASS, seg=28)
    fine.box((0.372, -0.011, -0.545), (0.404, 0.011, -0.505), L.STRUCT)                          # the trigger (front)
    fine.box((0.366, -0.013, -0.552), (0.380, 0.013, -0.540), L.STRUCT)
    for dy, cell in ((-0.016, "red"), (0.016, "amber")):                                         # two buttons and a hat switch on the head
        em.lamp_cyl((0.3375, dy, -0.4380), (0.3365, dy, -0.4380), 0.0052, cell, L.LAMP_DIM, seg=8)
    for (dx, dy) in ((0.0085, 0.0), (-0.0085, 0.0), (0.0, 0.0085), (0.0, -0.0085)):
        em.lamp_box((0.3470 + dx - 0.0027, dy - 0.0027, -0.4378), (0.3470 + dx + 0.0027, dy + 0.0027, -0.4366), "ice_dim", L.LAMP_DIM)


def pillow(soft: FB, x0: float, x1: float, hw0: float, hw1: float, z0: float, z1: float, mat: str, c: float = 0.8, rake: float = 0.0, bulge: float = 1.0) -> None:
    """A cushion: rounded sections in the horizontal plane (x thickness x0..x1, half width hw0 at the bottom to hw1 at the top) lofted from z0 to z1; `rake` shifts
    the top forward by that much; `bulge` swells the middle."""
    rings = []
    n = 5
    for k in range(n):
        t = k / (n - 1)
        hw = lerp(hw0, hw1, t) * (1.0 + 0.04 * (bulge - 1.0) * math.sin(math.pi * t) * 10)
        th = (x1 - x0) / 2 * (1.0 - 0.12 * (1.0 - math.sin(math.pi * t)))
        xc = (x0 + x1) / 2 + rake * t
        zz = lerp(z0, z1, t)
        rings.append([(xc + v, u, zz) for (u, v) in chamfer_rect(hw, th, c)])
    soft.loft(rings, mat, caps=True, closed=True)


def strap(fine: FB, p0, p1, w: float, mat: str = L.RUBBER) -> None:
    """A webbing strap between two points: a flat bar of width w, 4 mm thick, its flat side facing the pilot (back and up)."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    ln = d.length
    if ln < 1e-4:
        return
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    fine.cbox(tuple((a + b) / 2), (ln, 0.004, w), mat, Rz(yaw) @ Ry(-pitch) @ Rx(90))


def seat(b: Parts) -> None:
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    # the pan and the back: gunmetal shells with leather cushions, the headrest, side bolsters
    fb.box((-0.62, -0.265, -0.865), (-0.10, 0.265, -0.800), L.STRUCT)
    pillow(soft, -0.56, -0.14, 0.215, 0.215, -0.800, -0.752, L.LEATHER, c=0.7)
    fb.extrude_y([(-0.72, -0.88), (-0.62, -0.88), (-0.58, -0.80), (-0.505, 0.05), (-0.485, 0.30), (-0.555, 0.32), (-0.68, 0.32), (-0.70, -0.30)], -0.255, 0.255, L.STRUCT)
    pillow(soft, -0.555, -0.495, 0.200, 0.172, -0.78, 0.00, L.LEATHER, c=0.7, rake=0.045)
    pillow(soft, -0.510, -0.448, 0.140, 0.140, 0.04, 0.26, L.LEATHER, c=0.8, rake=0.012)
    xf_of = lambda z_: -0.495 + 0.045 * (z_ + 0.78) / 0.78                                                  # the back cushion's front face at height z_
    for z_ in (-0.55, -0.30, -0.05):                                                                        # the back cushion's seams, with a line of white stitching either side
        xf = xf_of(z_)
        fine.box((xf - 0.002, -0.17, z_ - 0.002), (xf + 0.0015, 0.17, z_ + 0.002), L.RUBBER)
        for dz in (-0.008, 0.008):
            em.box((xf - 0.001 + 0.045 * dz / 0.78, -0.165, z_ + dz - 0.0005), (xf + 0.0011 + 0.045 * dz / 0.78, 0.165, z_ + dz + 0.0005), PLATE)
    for yy in (-0.085, 0.085):                                                                              # the long seams, each between two stitched lines
        for dy in (-0.007, 0.007):
            em.cyl((xf_of(-0.745) + 0.0004, yy + dy, -0.745), (xf_of(-0.020) + 0.0004, yy + dy, -0.020), 0.0006, PLATE, seg=4, caps=False)
        fine.cyl((xf_of(-0.745) + 0.0002, yy, -0.745), (xf_of(-0.020) + 0.0002, yy, -0.020), 0.0016, L.RUBBER, seg=4, caps=False)
    for sd in (-1, 1):                                                                                      # the edge piping of the back cushion
        em.cyl((xf_of(-0.745) + 0.0004, sd * 0.165, -0.745), (xf_of(-0.020) + 0.0004, sd * 0.150, -0.020), 0.0008, PLATE, seg=4, caps=False)
    fine.cyl((-0.456, 0.0, 0.150), (-0.4365, 0.0, 0.150), 0.064, L.STRUCT, seg=32)                           # a gunmetal badge riveted on the headrest with the ASTRA roundel
    emblem(em, (-0.4361, 0.0, 0.150), 0.052, L.IVORY, (1, 0, 0), (0, 0, 1))
    for sd in (-1, 1):
        fb.box((-0.62, sd * 0.262 - 0.014, -0.84), (-0.22, sd * 0.262 + 0.014, -0.62), L.STRUCT)               # side bolsters of the pan
        fb.box((-0.74, sd * 0.285 - 0.016, -1.04), (-0.68, sd * 0.285 + 0.016, 0.34), L.TRIM)                   # the seat rails
    # the ejection loop over the headrest: a ring of striped segments (amber lit / dark rubber) on two posts
    n = 20
    loop = [(-0.490, 0.095 * math.cos(2 * math.pi * k / n), 0.385 + 0.075 * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
    for k in range(n):
        if k % 2 == 0:
            em.lamp_cyl(loop[k], loop[k + 1], 0.0095, "amber", L.LAMP_DIM, seg=6)
        else:
            fine.cyl(loop[k], loop[k + 1], 0.0095, L.RUBBER, seg=6)
    for sd in (-1, 1):
        fine.cyl((-0.52, sd * 0.075, 0.26), (-0.490, sd * 0.095, 0.385), 0.0115, L.TRIM, seg=8)
    # the pack behind the back (rocket and parachute) with a lit placard, the harness: shoulder straps down to the buckle, lap belts out to the pan's sides
    fb.box((-0.84, -0.17, -0.55), (-0.66, 0.17, 0.50), L.COMPOSITE)
    em.box((-0.6615, -0.17, 0.355), (-0.6595, 0.17, 0.370), L.BRASS)
    stencil(em, "EJECT", (-0.6592, 0.0, 0.425), 0.0150, (1, 0, 0), (0, 0, 1), "amber_dim", tracking=0.004)
    stencil(em, "PULL BOTH HANDLES", (-0.6592, 0.0, 0.392), 0.0055, (1, 0, 0), (0, 0, 1), "ice_dim", tracking=0.004)
    buckle = (-0.215, 0.0, -0.735)
    for sd in (-1, 1):
        strap(fine, (-0.482, sd * 0.125, 0.10), (buckle[0] - 0.02, sd * 0.040, buckle[2] + 0.02), 0.046)
        strap(fine, (-0.58, sd * 0.255, -0.765), (buckle[0] + 0.005, sd * 0.050, buckle[2]), 0.044)
        em.box((-0.482, sd * 0.125 - 0.026, 0.0975), (-0.4785, sd * 0.125 + 0.026, 0.1025), L.BRASS)
    fine.box((-0.250, -0.042, -0.745), (-0.190, 0.042, -0.722), L.STRUCT)
    em.box((-0.248, -0.038, -0.7222), (-0.192, 0.038, -0.7205), L.BRASS)
    em.lamp_cyl((-0.219, 0.0, -0.7224), (-0.219, 0.0, -0.7196), 0.011, "green", L.LAMP_DIM, seg=10)
    fb.box((-0.56, -0.20, -1.02), (-0.16, 0.20, -0.865), L.COMPOSITE)                                           # the survival pack under the pan
    em.box((-0.56, -0.20, -0.9485), (-0.16, 0.20, -0.9455), L.BRASS)


def tub(b: Parts) -> None:
    fb, fine, em = b.body, b.fine, b.emit
    fb.box((-0.60, -0.60, -1.10), (1.06, 0.60, -1.04), L.DECK)
    for xx in (-0.3, 0.1, 0.5, 0.9):                                                           # floor ribs
        fb.box((xx - 0.012, -0.60, -1.04), (xx + 0.012, 0.60, -1.025), L.STRUCT)
    for sd in (-1, 1):                                                                         # lit strips along the footwell, under the consoles
        em.lamp_box((-0.10, sd * 0.380 - 0.0035, -1.0398), (0.50, sd * 0.380 + 0.0035, -1.0384), "cyan_dim", L.LAMP_DIM)
    for sd in (-1, 1):                                                                         # the rudder pedals: a steel arm, a rubber pad, a lit legend
        fb.box((0.76, sd * 0.20 - 0.07, -1.00), (0.80, sd * 0.20 + 0.07, -0.86), L.STRUCT)
        fb.box((0.755, sd * 0.20 - 0.065, -0.99), (0.762, sd * 0.20 + 0.065, -0.88), L.RUBBER)
        fine.cyl((0.78, sd * 0.20 - 0.07, -1.04), (0.78, sd * 0.20 - 0.07, -0.99), 0.012, L.TRIM, seg=8)
        stencil(em, "L" if sd < 0 else "R", (0.7545, sd * 0.20, -0.935), 0.018, (-1, 0, 0), (0, 0, 1), "ice_dim")
    # the bulkhead behind the seat: a carbon panel with vents, an oxygen bottle, a lit placard
    fb.box((-0.90, -0.60, -1.04), (-0.86, 0.60, 0.10), L.COMPOSITE)
    for k in range(6):
        fine.box((-0.8590, -0.18, -0.50 + k * 0.035), (-0.8570, 0.18, -0.482 + k * 0.035), L.RUBBER)
    fb.cyl((-0.82, -0.44, -1.04), (-0.82, -0.44, -0.45), 0.07, L.STRUCT, seg=18)
    em.cyl((-0.82, -0.44, -0.55), (-0.82, -0.44, -0.53), 0.0705, L.BRASS, seg=18)
    em.lamp_box((-0.8585, 0.30, -0.80), (-0.8575, 0.50, -0.78), "green_dim", L.LAMP_DIM)


# ======================================================================================================================== outside
NOSE = [(0.95, 1.02, -0.292, -2.02), (2.2, 0.87, -0.345, -1.96), (3.6, 0.585, -0.59, -1.71), (4.8, 0.34, -0.81, -1.49), (5.8, 0.135, -0.99, -1.31)]   # x, half width, top z, bottom z


def _ring(x: float, hw: float, top: float, bot: float, y0: float = 0.0, shrink: float = 1.0):
    sec = chamfer_rect(hw * shrink, (top - bot) / 2, 0.38, top=0.80, bottom=0.70)
    zc = (top + bot) / 2
    return [(x, y0 + y, zc + z) for (y, z) in sec]


def nose_params(x: float):
    """(half width, top z, bottom z) of the nose at station x."""
    for (x0, h0, t0, b0), (x1, h1, t1, b1) in zip(NOSE[:-1], NOSE[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            return lerp(h0, h1, f), lerp(t0, t1, f), lerp(b0, b1, f)
    return (NOSE[-1][1], NOSE[-1][2], NOSE[-1][3]) if x > NOSE[-1][0] else (NOSE[0][1], NOSE[0][2], NOSE[0][3])


def ztop(x: float) -> float:
    return nose_params(x)[1]


def top_half(x: float) -> float:
    """The half width of the flat top of the nose at x."""
    return 0.42 * nose_params(x)[0]


def nose_pt(x: float, side: int, t: float):
    """A point of the nose's skin at station x on the sloping shoulder: t = 0 at the outer edge of the flat top, 1 at the widest corner."""
    hw, top, bot = nose_params(x)
    h, zc = (top - bot) / 2, (top + bot) / 2
    return (x, side * lerp(0.42 * hw, hw, t), lerp(zc + h, zc + h - 0.38 * h, t))


def ribbon(fb: FB, pts, thick: float, mat: str) -> None:
    """A flat strip through (x, y_centre, z, half_width) points, `thick` metres thick (its centre on the given z)."""
    rings = [[(x, y - hw, z - thick / 2), (x, y + hw, z - thick / 2), (x, y + hw, z + thick / 2), (x, y - hw, z + thick / 2)] for (x, y, z, hw) in pts]
    fb.loft(rings, mat, caps=True, closed=True)


def seam(fine: FB, p0, p1, r: float = 0.0030, mat: str = FRAME) -> None:
    """A panel line: a thin dark rod laid on the skin between two points."""
    fine.cyl(p0, p1, r, mat, seg=4, caps=False)


def hatch(b: Parts, origin, x_axis, n_axis, length: float, width: float, screws: int = 3, mat: str = FRAME) -> None:
    """An access hatch outlined on the skin: a frame of four bars standing 3 mm proud with a screw along each long side. Frame at `origin`: x (the hatch's length)
    along `x_axis`, z out of the skin along `n_axis`."""
    w, h = width, length
    fine, em = b.fine, b.emit
    with b.at(basis(origin, x_axis, n_axis)):
        bw = 0.010
        fine.box((-h / 2, -w / 2, 0.0), (h / 2, -w / 2 + bw, 0.003), mat)
        fine.box((-h / 2, w / 2 - bw, 0.0), (h / 2, w / 2, 0.003), mat)
        fine.box((-h / 2, -w / 2 + bw, 0.0), (-h / 2 + bw, w / 2 - bw, 0.003), mat)
        fine.box((h / 2 - bw, -w / 2 + bw, 0.0), (h / 2, w / 2 - bw, 0.003), mat)
        for k in range(screws):
            xs = -h / 2 + bw / 2 + (h - bw) * k / max(1, screws - 1)
            for ys in (-w / 2 + bw / 2, w / 2 - bw / 2):
                hex_pad(em, xs, ys, 0.0032, 0.0036, (0, 0, 1), L.TRIM, up=(1, 0, 0))


def exterior(b: Parts) -> None:
    fb, fine, em = b.body, b.fine, b.emit
    # ---- the nose: plates on a frame, a dark anti-glare deck from the hood forward, the navy livery stripe, panel lines, hatches, stencils, the probe
    fb.loft([_ring(*s) for s in NOSE], PLATE, caps=True, closed=True)
    ribbon(fine, [(x, 0.0, ztop(x) + 0.0007, top_half(x) - 0.03) for x in (0.95, 1.4, 2.2, 3.0)], 0.0014, L.RUBBER)
    ribbon(fine, [(x, 0.0, ztop(x) + 0.0010, 0.085) for x in (3.0, 3.6, 4.8, 5.62)], 0.0020, LIVERY)
    for sd in (-1, 1):                                                                                   # dark service panels either side of the stripe
        for (xa, xb) in ((3.15, 3.55), (3.85, 4.30), (4.50, 4.85)):
            ya, yb = 0.115, min(top_half(xa), top_half(xb)) - 0.03
            if yb - ya > 0.04:
                ribbon(fine, [(xa, sd * (ya + yb) / 2, ztop(xa) + 0.0008, (yb - ya) / 2), (xb, sd * (ya + yb) / 2, ztop(xb) + 0.0008, (yb - ya) / 2)], 0.0014, FRAME)
    for x in (3.0, 3.6, 4.2, 4.8, 5.3):                                                                 # transverse seams across the top and down the shoulders
        hw = top_half(x)
        fine.box((x - 0.004, -hw, ztop(x) - 0.0005), (x + 0.004, hw, ztop(x) + 0.0015), FRAME)
    for x in (1.5, 2.2, 3.0, 3.6, 4.2, 4.8, 5.3):
        for sd in (-1, 1):
            seam(fine, nose_pt(x, sd, 0.0), nose_pt(x, sd, 1.0))
    for t in (0.0, 0.5, 1.0):                                                                           # longitudinal lines along the shoulders
        for sd in (-1, 1):
            xs = (0.95, 1.5, 2.2, 3.0, 3.6, 4.2, 4.8, 5.3)
            for x0, x1 in zip(xs[:-1], xs[1:]):
                seam(fine, nose_pt(x0, sd, t), nose_pt(x1, sd, t))
    for sd in (-1, 1):
        for (x, t0, t1, xw) in ((1.25, 0.18, 0.82, 0.55), (2.45, 0.22, 0.78, 0.42)):                    # access hatches on the shoulders
            tm = (t0 + t1) / 2
            ex = Vector(nose_pt(x + 0.1, sd, tm)) - Vector(nose_pt(x - 0.1, sd, tm))
            ey = Vector(nose_pt(x, sd, t1)) - Vector(nose_pt(x, sd, t0))
            hatch(b, nose_pt(x, sd, tm), ex, ex.cross(ey) if ex.cross(ey).z > 0 else ey.cross(ex), xw, ey.length * 0.62)
        x, tm = 3.35, 0.5                                                                                # the callsign stencils: ASN to port, ALPHA 1 to starboard
        ex = Vector(nose_pt(x + 0.1, sd, tm)) - Vector(nose_pt(x - 0.1, sd, tm))
        ey = Vector(nose_pt(x, sd, 1.0)) - Vector(nose_pt(x, sd, 0.0))
        n = ex.cross(ey) if ex.cross(ey).z > 0 else ey.cross(ex)
        fine.text("ASN" if sd < 0 else "ALPHA 1", nose_pt(x, sd, tm), 0.06, tuple(n.normalized()), FRAME, up=tuple(ex), lift=0.0025)
    for sd in (-1, 1):
        fine.text("NO STEP", (1.55, sd * 0.28, ztop(1.55) + 0.0018), 0.050, (0, 0, 1), PLATE, up=(1, 0, 0))
        for k in range(8):                                                                               # formation strips: lit dashes along the edge of the deck
            x0 = 1.25 + k * 0.52
            xa, xb = x0, x0 + 0.20
            ya, yb = sd * (top_half(xa) - 0.040), sd * (top_half(xb) - 0.040)
            em.lamp_face([(xa, ya - 0.006, ztop(xa) + 0.0016), (xa, ya + 0.006, ztop(xa) + 0.0016), (xb, yb + 0.006, ztop(xb) + 0.0016), (xb, yb - 0.006, ztop(xb) + 0.0016)],
                         "cyan_dim", (0, 0, 1), L.LAMP_DIM)
    emblem(fine, (2.30, 0.0, ztop(2.30) + 0.0022), 0.13, PLATE, (0, 0, 1), (1, 0, 0))
    # the sensor probe, a dome and the lights on the nose
    fb.cyl((5.80, 0.0, -1.18), (6.45, 0.0, -1.18), 0.040, L.TRIM, seg=10, r2=0.012)
    em.lamp_cyl((6.45, 0.0, -1.18), (6.52, 0.0, -1.18), 0.012, "red", L.LAMP, seg=8)
    fb.sphere((5.35, 0.0, ztop(5.35)), 0.060, L.STRUCT, seg=12, rings=6, squash=(1.0, 1.0, 0.55))
    em.lamp_cbox((5.55, 0.0, ztop(5.55) + 0.012), (0.05, 0.05, 0.012), "white", L.LAMP_DIM)
    # ---- the shoulders beside the cockpit: plated decks with a dark walkway panel along the canopy edge, a brass line, panel lines and a hatch each
    for sd in (-1, 1):
        rings = [[(x, sd * 0.95 + y, -1.28 + z) for (y, z) in chamfer_rect(0.39, 0.88, 0.3, top=0.9)] for x in (-0.9, 0.0, 0.95)]
        fb.loft(rings, PLATE, caps=True, closed=True)
        ribbon(fine, [(x, sd * 0.80, -0.3995, 0.20) for x in (-0.88, 0.0, 0.94)], 0.0016, FRAME)
        em.box((-0.90, sd * 0.61 - 0.0030, -0.3994), (0.95, sd * 0.61 + 0.0030, -0.3978), L.BRASS)
        for x in (-0.45, 0.30):
            fine.box((x - 0.004, sd * 1.00 - 0.34, -0.4000), (x + 0.004, sd * 1.00 + 0.34, -0.3978), FRAME)
        fine.box((-0.90, sd * 1.01 - 0.003, -0.4000), (0.95, sd * 1.01 + 0.003, -0.3978), FRAME)
        hatch(b, (0.50, sd * 1.15, -0.3972), (1, 0, 0), (0, 0, 1), 0.46, 0.30)
    fine.text("ALPHA 1", (-0.30, 1.14, -0.3968), 0.045, (0, 0, 1), FRAME, up=(1, 0, 0))
    fine.text("ASN", (-0.30, -1.14, -0.3968), 0.045, (0, 0, 1), FRAME, up=(1, 0, 0))
    # ---- the aft fuselage with the turtle deck behind the seat, panel lines across it
    aft = [(-0.9, 1.35, -0.40, -2.15), (-1.7, 1.35, 0.02, -2.2), (-4.0, 1.35, -0.12, -2.2), (-8.0, 1.15, -0.35, -2.1), (-10.9, 0.85, -0.6, -1.85)]
    fb.loft([_ring(*s) for s in aft], PLATE, caps=True, closed=True)
    for x in (-2.4, -3.4, -4.6, -6.0, -7.4):
        zt = lerp(-0.12, -0.35, (x + 4.0) / -4.0) if x < -4.0 else lerp(0.02, -0.12, (x + 1.7) / -2.3)
        fine.box((x - 0.005, -0.5, zt - 0.0005), (x + 0.005, 0.5, zt + 0.0035), FRAME)
    # ---- the wings (v3: swept back, root chord 7.56 from x -8.24, tip chord 2.52 from x -5.0): skin, spanwise and chordwise panel lines, the roundel, the tip light,
    # a missile on each of two hardpoints
    for sd in (-1, 1):
        z0r, z0t = AX - 0.27, AX - 0.27 + 0.25
        root = [(-8.24, sd * 1.215, z0r - 0.12), (-0.68, sd * 1.215, z0r - 0.12), (-0.68, sd * 1.215, z0r + 0.12), (-8.24, sd * 1.215, z0r + 0.12)]
        tip = [(-5.0, sd * 6.48, z0t - 0.05), (-2.48, sd * 6.48, z0t - 0.05), (-2.48, sd * 6.48, z0t + 0.05), (-5.0, sd * 6.48, z0t + 0.05)]
        fb.loft([root, tip], PLATE, caps=True, closed=True)
        rte, rle, tte, tle = (Vector(root[3]), Vector(root[2]), Vector(tip[3]), Vector(tip[2]))

        def wing_pt(u: float, v: float, lift: float = 0.0):
            p = (rte * (1 - v) + rle * v) * (1 - u) + (tte * (1 - v) + tle * v) * u
            return (p.x, p.y, p.z + lift)

        for v in (0.30, 0.62):
            seam(fine, wing_pt(0.04, v), wing_pt(0.97, v))
        for u in (0.18, 0.36, 0.54, 0.72, 0.90):
            seam(fine, wing_pt(u, 0.0), wing_pt(u, 1.0))
        emblem(fine, wing_pt(0.45, 0.50, 0.0032), 0.70, LIVERY, (0, 0, 1), (1, 0, 0))
        em.lamp_cbox((-3.7, sd * 6.5, z0t + 0.06), (0.30, 0.10, 0.07), "red" if sd < 0 else "green", L.LAMP)
        for k in range(2):
            yy = sd * (2.2 + (6.48 - 1.35) * (0.35 + 0.3 * k))
            zz = lerp(z0r, z0t, (abs(yy) - 1.215) / 5.265)
            fb.cyl((-6.4, yy, zz - 0.42), (-2.3, yy, zz - 0.42), 0.12, L.STRUCT, seg=12)
            fb.cyl((-2.3, yy, zz - 0.42), (-1.9, yy, zz - 0.42), 0.12, L.TRIM, seg=12, r2=0.02)
            fine.box((-4.8, yy - 0.05, zz - 0.30), (-3.0, yy + 0.05, zz - 0.05), FRAME)
        # the twin fin, canted outwards, with its roundel
        fins = [[(-11.84, sd * 0.75, AX + 1.4), (-8.6, sd * 0.75, AX + 1.4), (-8.6, sd * 0.95, AX + 1.4), (-11.84, sd * 0.95, AX + 1.4)],
                [(-11.6, sd * 1.25, AX + 2.38), (-10.2, sd * 1.25, AX + 2.38), (-10.2, sd * 1.35, AX + 2.38), (-11.6, sd * 1.35, AX + 2.38)]]
        fb.loft(fins, FRAME, caps=True, closed=True)
        fb.cyl((-10.9, sd * 0.62, AX), (-12.3, sd * 0.62, AX), 0.72, L.STRUCT, seg=20)                    # the drive bells
        em.lamp_cyl((-12.3, sd * 0.62, AX), (-12.5, sd * 0.62, AX), 0.55, "ice", L.LAMP, seg=20)


# ================================================================================================================== assemble
STAGES = {"canopy": canopy, "dash": dash, "left": left_console, "right": right_console, "stick": stick, "seat": seat, "tub": tub, "outside": exterior}


def build(name: str = NAME):
    wanted = os.environ.get("CKP_PARTS", ",".join(STAGES)).split(",")
    b = Parts(bevel=0.005, fine_bevel=0.002)
    b.bevel_segments = 1
    for p in wanted:
        STAGES[p](b)
    return b.build(name, uv_meter=0.5, small_uv_meter=0.12)


VIEWS = {
    # name: (eye (layout frame, the pilot's eye is the origin), yaw, pitch, fov)
    "pilot": ((0.0, 0.0, 0.0), 0.0, 0.0, 88.0),
    "pilot_low": ((0.0, 0.0, 0.0), 0.0, -22.0, 88.0),
    "dash": ((0.0, 0.0, 0.0), 0.0, -44.0, 72.0),
    "dash_close": ((0.20, 0.0, -0.30), 0.0, -40.0, 50.0),
    "left": ((0.0, 0.0, 0.0), -62.0, -26.0, 80.0),
    "right": ((0.0, 0.0, 0.0), 62.0, -26.0, 80.0),
    "back": ((0.0, 0.0, 0.0), 180.0, 12.0, 88.0),
    "up": ((0.0, 0.0, 0.0), 0.0, 52.0, 88.0),
    "outside": ((7.5, -7.0, 2.6), 142.0, -14.0, 60.0),
    "wingview": ((0.0, 0.0, 0.0), -90.0, -8.0, 88.0),
    "knees": ((-0.2, 0.0, 0.1), 0.0, -58.0, 80.0),
    "throttle": ((-0.05, -0.25, -0.10), -68.0, -48.0, 55.0),
    "sensors": ((-0.05, 0.25, -0.10), 68.0, -48.0, 55.0),
    "hood": ((0.0, 0.0, 0.0), 0.0, -24.0, 50.0),
    "bow": ((0.0, 0.0, 0.0), -38.0, 4.0, 60.0),
}


def preview(obj, out_dir: str, views: list[str], samples: int) -> None:
    import bridge3_preview as PV
    os.makedirs(out_dir, exist_ok=True)
    PV.make_materials({})
    PV.set_world((0.0, 0.0, 0.0), 0.0)
    PV.sky_dome(yaw_deg=float(os.environ.get("CKP_SKYYAW", "20")), strength=float(os.environ.get("CKP_SKY", "0.55")))
    PV.configure_render(int(os.environ.get("CKP_W", "1600")), int(os.environ.get("CKP_H", "900")), samples, exposure=float(os.environ.get("CKP_EXPOSURE", "0")))
    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = float(os.environ.get("CKP_SUN", "3.2"))
    sun.color = (1.0, 0.93, 0.82)
    sun.angle = math.radians(1.2)
    so = bpy.data.objects.new("Sun", sun)
    bpy.context.scene.collection.objects.link(so)
    d = Vector((-0.55, 0.35, -0.75))                                  # light travels from the star (ahead, to the right, above) into the cockpit
    so.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    fill = bpy.data.lights.new("PlanetShine", "AREA")
    fill.energy = 180.0
    fill.color = (0.45, 0.65, 1.0)
    fill.size = 5.0
    fo = bpy.data.objects.new("PlanetShine", fill)
    bpy.context.scene.collection.objects.link(fo)
    fo.location = (3.0, 4.0, -3.0)
    fo.rotation_euler = Vector((-0.4, -0.6, 1.0)).to_track_quat("-Z", "Y").to_euler()
    cab = bpy.data.lights.new("CabinGlow", "POINT")
    cab.energy = float(os.environ.get("CKP_CABIN", "9.0"))
    cab.color = (0.7, 0.85, 1.0)
    cab.shadow_soft_size = 0.2
    co = bpy.data.objects.new("CabinGlow", cab)
    bpy.context.scene.collection.objects.link(co)
    co.location = (0.55, 0.0, -0.1)
    for v in views:
        eye, yaw, pitch, fov = VIEWS[v]
        cam = PV.add_camera(v, eye, yaw, pitch, fov)
        PV.render(cam, os.path.join(out_dir, f"{v}.jpg"))
        print("rendered", v)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv and not argv[0].startswith("--") else os.path.join(L.ROOT, "art", "export", "cockpit")
    prev = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else ["pilot", "dash", "left", "right", "back", "outside"]
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 40
    export = "--no-export" not in argv
    A.reset_scene()
    L.load_label_atlas()
    L.load_decor_atlas()
    obj = build(NAME)
    st = A.stats(obj)
    print("COCKPIT", st["tris"], "tris", len(st["materials"]), "slots", st["materials"])
    if export:
        os.makedirs(out_dir, exist_ok=True)
        A.export_fbx(obj, os.path.join(out_dir, NAME + ".fbx"))
        print("COCKPIT_OK", out_dir)
    if prev:
        preview(obj, prev, views, samples)


if __name__ == "__main__":
    main()
