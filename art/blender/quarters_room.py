"""ASN Aquila — the Captain's quarters, the cabin (Deck 1 · Section A), version 2 (ARTE-PLANCIA-2): SM_QTR_Room built on the bridge toolkit (bridge3_lib / bridge3_life).

A captain's cabin of 2491 as a film would dress it: dark walnut wainscot in raised panels under a brass-lined rail, cream panelled walls with wood pilasters, a navy carpet in a
border of wood with a brass line and a compass rose inlay, a coffered ceiling with a lit cove and brass downlights, a stern gallery (the great aft window with its wood mullions,
drapes and a cushioned window seat), the desk with its terminal, banker's lamp and the small things of a working life, cognac leather chairs and a sofa, a bar-and-galley corner, the bunk in
its alcove, a bookcase with books and brass instruments, a sideboard with the ship's model stand under the starboard window, charts in brass frames, a clock and a barometer, a navy
pennant, the Captain's cap on its hook.

Everything is in the cabin's frame (world_origin in the data): Unreal's axes (x forward, y starboard, z up), metres, the origin on the floor, on the inner face of the forward wall, on the
door's axis; the cabin runs aft (negative x). bridge3_lib mirrors Y on the way out, so the FBX lands 1:1 in Unreal.
The positions come from data/ship/aquila_quarters.json (door, windows, desk, sofa, bunk, bookcase, galley, map screen, model pedestal): the level script places lights, the ship's model, the
plaque and the bunk's controller on the same numbers.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as B3  # noqa: E402
import bridge3_life as LF  # noqa: E402
from bridge3_lib import FB, Parts, Rx, Ry, Rz, T, lerp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_quarters.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
FIN = 0.05                                   # the finish layer on the structure

WOOD, WALL, CARPET = "MI_QTR_Wood", "MI_QTR_Wall", "MI_QTR_Carpet"
LEATHER = "MI_QTR_Leather"                   # cognac leather (an instance made by tools/ue_scripts/build_quarters.py)
LINEN, BLANKET, RED = "MI_MED_Linen", "MI_MED_Blanket", "MI_MED_Red"
MAP, LOG = "MI_QTR_Map", "MI_QTR_Log"
STRUCT, TRIM, RUBBER, DGLASS = B3.STRUCT, B3.TRIM, B3.RUBBER, B3.DGLASS
BRASS, LAMP, LAMP_DIM = B3.BRASS, B3.LAMP, B3.LAMP_DIM
BOOKS = [LEATHER, RED, BLANKET, LINEN, WOOD]


def new_parts() -> Parts:
    b = Parts(bevel=0.006, fine_bevel=0.0025)
    b.bevel_segments = 1
    return b


def slab(fb: FB, axis: str, p0: float, p1: float, u0: float, u1: float, z0: float, z1: float, holes, mat: str) -> None:
    """A wall slab: axis 'x' = it spans y (u) at x in [p0, p1]; 'y' = it spans x (u) at y in [p0, p1]. `holes`: (u0, u1, z0, z1) rectangles left open (doors, windows)."""
    cuts = sorted({u0, u1, *[h[0] for h in holes], *[h[1] for h in holes]})
    for ua, ub in zip(cuts, cuts[1:]):
        zs = [(z0, z1)]
        for hu0, hu1, hz0, hz1 in holes:
            if hu0 <= ua and ub <= hu1:
                zs = [(z0, hz0), (hz1, z1)]
        for za, zb in zs:
            if zb - za < 1e-3:
                continue
            if axis == "x":
                fb.box((p0, ua, za), (p1, ub, zb), mat)
            else:
                fb.box((ua, p0, za), (ub, p1, zb), mat)


def hex_head(em: FB, x: float, y: float, z: float, r: float, facing, up=(0, 0, 1), mat: str = BRASS) -> None:
    """A flat hexagon (a screw head, a stud) of circumradius r on a surface whose normal is `facing`."""
    f = Vector(facing).normalized()
    u = Vector(up) - f * Vector(up).dot(f)
    u = u.normalized() if u.length > 1e-6 else Vector((1, 0, 0))
    r_ = f.cross(u)
    c = Vector((x, y, z))
    em.face([tuple(c + (r_ * math.cos(math.radians(60 * k)) + u * math.sin(math.radians(60 * k))) * r) for k in range(6)], mat, tuple(f))


def pillow(soft: FB, c, size, mat: str, yaw: float = 0.0, tilt: float = 0.0, puff: float = 0.18) -> None:
    """A cushion: a rounded block (an octagonal section lofted with a swell in the middle) centred at c, size (x, y, z), turned by yaw and tipped by tilt about y."""
    sx, sy, sz = size
    rings = []
    n = 5
    for k in range(n):
        t = k / (n - 1)
        sw = 1.0 - puff * (1.0 - math.sin(math.pi * t) ** 0.5)
        hw, hh = sx / 2 * sw, sz / 2 * sw
        rings.append([(-sy / 2 + (t * sy), px, pz) for (px, pz) in B3_chamfer(hw, hh, 0.55)])
    with soft.at(T(*c) @ Rz(yaw) @ Ry(tilt)):
        soft.loft(rings, mat, caps=True, closed=True)


def B3_chamfer(w: float, h: float, c: float):
    cw, ch = c * w, c * h
    return [(-w + cw, -h), (w - cw, -h), (w, -h + ch), (w, h - ch), (w - cw, h), (-w + cw, h), (-w, h - ch), (-w, -h + ch)]


# =============================================================================================================================== the shell
def shell(b: Parts) -> None:
    """The floor (structure, a wood border and a navy carpet field with a brass line and the compass rose), the walls' finish with their openings, the structural layer behind the
    forward wall, the skirting, the wainscot panels, the rails, the ceiling."""
    fb, em = b.body, b.emit
    door = D["door"]
    wa, ws = D["window_aft"], D["window_side"]
    x0, x1, y0, y1 = -LEN + FIN, -FIN, -HW + FIN, HW - FIN                                   # the inner faces
    # ---- the floor: structure, the wood border (0.8 m), the carpet field with a brass line round it
    fb.box((-LEN, -HW, -0.3), (0, HW, -0.02), STRUCT)
    bw = 0.8
    fb.box((-LEN, -HW, -0.02), (0, HW, 0.0), WOOD)
    fb.box((x0 + bw, y0 + bw, 0.0), (x1 - bw, y1 - bw, 0.007), CARPET)
    for (xa, xb, ya, yb) in ((x0 + bw - 0.012, x1 - bw + 0.012, y0 + bw - 0.012, y0 + bw - 0.006), (x0 + bw - 0.012, x1 - bw + 0.012, y1 - bw + 0.006, y1 - bw + 0.012),
                             (x0 + bw - 0.012, x0 + bw - 0.006, y0 + bw - 0.012, y1 - bw + 0.012), (x1 - bw + 0.006, x1 - bw + 0.012, y0 + bw - 0.012, y1 - bw + 0.012)):
        em.box((xa, ya, 0.0), (xb, yb, 0.0075), BRASS)
    # ---- the walls' finish: wood to 1 m under a rail, the wall material above, openings left for the door and the windows
    fwd_holes = [(door["y"] - door["width"] / 2, door["y"] + door["width"] / 2, 0.0, door["height"])]
    aft_holes = [(wa["y0"], wa["y1"], wa["z0"], wa["z1"])]
    stb_holes = [(ws["x0"], ws["x1"], ws["z0"], ws["z1"])]
    walls = (("x", -FIN, 0.0, -HW, HW, fwd_holes), ("x", -LEN, -LEN + FIN, -HW, HW, aft_holes), ("y", -HW, -HW + FIN, -LEN, 0.0, []), ("y", HW - FIN, HW, -LEN, 0.0, stb_holes))
    for (axis, p0, p1, u0, u1, holes) in walls:
        slab(fb, axis, p0, p1, u0, u1, 0.0, 1.0, holes, WOOD)
        slab(fb, axis, p0, p1, u0, u1, 1.0, H, holes, WALL)
    slab(fb, "x", 0.0, 0.3, -HW - 0.05, HW + 0.05, -0.3, H + 0.05, fwd_holes, STRUCT)          # the structural layer behind the finish (the block's skin is SM_SHIP_...)
    # ---- the ceiling slab
    fb.box((-LEN, -HW, H), (0, HW, H + 0.05), WALL)


# ======================================================================================================================== the walls dressed
def wall_frame(name: str) -> Matrix:
    """The frame of a wall's finished face: local x (s) along the wall, local y (d) from the wall into the room, local z up (right-handed). Origin on the face at s = 0."""
    o, u, n = {"fwd": ((-FIN, 0.0, 0.0), (0, 1, 0), (-1, 0, 0)), "aft": ((-LEN + FIN, 0.0, 0.0), (0, -1, 0), (1, 0, 0)),
               "port": ((0.0, -HW + FIN, 0.0), (1, 0, 0), (0, 1, 0)), "stbd": ((0.0, HW - FIN, 0.0), (-1, 0, 0), (0, -1, 0))}[name]
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = u[i], n[i], (0.0, 0.0, 1.0)[i], o[i]
    return m


def free_runs(s0: float, s1: float, holes, margin: float = 0.0, min_len: float = 0.3):
    """The intervals of [s0, s1] outside the holes (each widened by `margin`)."""
    cuts = sorted((max(s0, a - margin), min(s1, b + margin)) for a, b in holes)
    runs, cur = [], s0
    for a, b in cuts:
        if a - cur >= min_len:
            runs.append((cur, a))
        cur = max(cur, b)
    if s1 - cur >= min_len:
        runs.append((cur, s1))
    return runs


def wall_s_holes():
    """The openings of each wall as intervals along its own s axis with the height where they start: (s0, s1, z0)."""
    door, wa, ws = D["door"], D["window_aft"], D["window_side"]
    return {"fwd": [(door["y"] - door["width"] / 2, door["y"] + door["width"] / 2, 0.0)], "aft": [(-wa["y1"], -wa["y0"], wa["z0"])],
            "port": [], "stbd": [(-ws["x1"], -ws["x0"], ws["z0"])]}


def dress_wall(b: Parts, name: str, s0: float, s1: float) -> None:
    """One wall's panelling: the skirting with a brass line, the wainscot's raised panels between stiles, the dado rail, the pilasters of the upper wall, the picture rail, the crown."""
    fb, fine, em = b.body, b.fine, b.emit
    holes = wall_s_holes()[name]
    spans = [(a, bb) for a, bb, _ in holes]
    low = [(a, bb) for a, bb, z0 in holes if z0 < 1.0]                       # the openings that cut the wainscot (the door, the aft window)
    with b.at(wall_frame(name)):
        for (ra, rb) in free_runs(s0, s1, spans, margin=0.14, min_len=0.05):                                            # skirting and its brass line
            fb.box((ra, 0.0, 0.0), (rb, 0.026, 0.14), WOOD)
            em.box((ra, 0.0255, 0.1385), (rb, 0.0275, 0.1415), BRASS)
        for (ra, rb) in free_runs(s0, s1, low, margin=0.14, min_len=0.4):                                               # the wainscot: a raised panel between stiles ~1 m apart
            n = max(1, int(round((rb - ra) / 1.0)))
            for k in range(n):
                pa, pb = ra + (rb - ra) * k / n, ra + (rb - ra) * (k + 1) / n
                fine.box((pa + 0.07, 0.0, 0.20), (pb - 0.07, 0.014, 0.88), WOOD)
                em.box((pa + 0.07, 0.0135, 0.20), (pb - 0.07, 0.0150, 0.2025), BRASS)
                em.box((pa + 0.07, 0.0135, 0.8775), (pb - 0.07, 0.0150, 0.88), BRASS)
        for (ra, rb) in free_runs(s0, s1, spans, margin=0.14, min_len=0.05):                                            # the dado rail
            fb.box((ra, 0.0, 0.98), (rb, 0.045, 1.04), WOOD)
            em.box((ra, 0.0445, 0.995), (rb, 0.0462, 1.003), BRASS)
        for (ra, rb) in free_runs(s0, s1, spans, margin=0.20, min_len=0.5):                                             # the upper wall: wood pilasters, a brass picture rail
            n = max(1, int(round((rb - ra) / 1.3)))
            for k in range(n + 1):
                sp = ra + (rb - ra) * k / n
                fine.box((sp - 0.04, 0.0, 1.04), (sp + 0.04, 0.012, H - 0.12), WOOD)
            for k in range(n):
                pa, pb = ra + (rb - ra) * k / n + 0.09, ra + (rb - ra) * (k + 1) / n - 0.09
                if pb - pa < 0.3:
                    continue
                for (sa, sb, za, zb) in ((pa, pb, 1.20, 1.2035), (pa, pb, 2.20, 2.2035), (pa, pa + 0.0035, 1.20, 2.2035), (pb - 0.0035, pb, 1.20, 2.2035)):
                    em.box((sa, 0.0, za), (sb, 0.0016, zb), BRASS)
            em.box((ra, 0.0, 2.36), (rb, 0.0138, 2.3665), BRASS)
        fb.box((s0, 0.0, H - 0.12), (s1, 0.07, H), WOOD)                                                                # the crown
        em.box((s0, 0.069, H - 0.118), (s1, 0.0715, H - 0.112), BRASS)


def door_frame(b: Parts) -> None:
    """The door's frame: an architrave of wood on the cabin's side with a brass line on its face, a brass kick plate."""
    fb, em = b.body, b.emit
    dw, dh = D["door"]["width"], D["door"]["height"]
    yc = D["door"]["y"]
    for (y0, y1, z0, z1) in ((yc - dw / 2 - 0.12, yc - dw / 2, 0.0, dh + 0.12), (yc + dw / 2, yc + dw / 2 + 0.12, 0.0, dh + 0.12), (yc - dw / 2, yc + dw / 2, dh, dh + 0.12)):
        fb.box((-FIN - 0.04, y0, z0), (-FIN, y1, z1), WOOD)
    xf = -FIN - 0.04
    em.box((xf - 0.0006, yc - dw / 2, dh + 0.06 - 0.0015), (xf, yc + dw / 2, dh + 0.06 + 0.0015), BRASS)
    for sd in (-1, 1):
        em.box((xf - 0.0006, yc + sd * (dw / 2 + 0.06) - 0.0015, 0.0), (xf, yc + sd * (dw / 2 + 0.06) + 0.0015, dh + 0.12), BRASS)


def windows(b: Parts) -> None:
    """The stern gallery: the great aft window in wood with brass caps on the mullions and a deep sill; the starboard window with its frame and sill."""
    fb, em = b.body, b.emit
    wa, ws = D["window_aft"], D["window_side"]
    x = -LEN
    for (y0, y1, z0, z1) in ((wa["y0"] - 0.1, wa["y0"], wa["z0"], wa["z1"]), (wa["y1"], wa["y1"] + 0.1, wa["z0"], wa["z1"]), (wa["y0"] - 0.1, wa["y1"] + 0.1, wa["z1"], wa["z1"] + 0.1)):
        fb.box((x - 0.35, y0, z0), (x + 0.08, y1, z1), WOOD)
    fb.box((x - 0.35, wa["y0"] - 0.1, wa["z0"] - 0.06), (x + 0.30, wa["y1"] + 0.1, wa["z0"]), WOOD)                           # a deep wooden sill
    em.box((x + 0.30, wa["y0"] - 0.1, wa["z0"] - 0.058), (x + 0.3015, wa["y1"] + 0.1, wa["z0"] - 0.002), BRASS)
    for my in wa["mullions"]:
        fb.box((x - 0.35, my - 0.06, wa["z0"]), (x + 0.07, my + 0.06, wa["z1"]), WOOD)
        em.box((x + 0.07, my - 0.062, wa["z0"]), (x + 0.0715, my + 0.062, wa["z0"] + 0.03), BRASS)
        em.box((x + 0.07, my - 0.062, wa["z1"] - 0.03), (x + 0.0715, my + 0.062, wa["z1"]), BRASS)
    for (x0, x1, z0, z1) in ((ws["x0"] - 0.1, ws["x0"], ws["z0"], ws["z1"]), (ws["x1"], ws["x1"] + 0.1, ws["z0"], ws["z1"]), (ws["x0"] - 0.1, ws["x1"] + 0.1, ws["z1"], ws["z1"] + 0.1),
                             (ws["x0"] - 0.1, ws["x1"] + 0.1, ws["z0"] - 0.06, ws["z0"])):
        fb.box((x0, HW - 0.08, z0), (x1, HW + 0.35, z1), WOOD)
    em.box((ws["x0"] - 0.1, HW - 0.1, ws["z0"] - 0.058), (ws["x1"] + 0.1, HW - 0.0985, ws["z0"] - 0.002), BRASS)


# ============================================================================================================================== the ceiling
DOWNLIGHTS = ((-1.6, -2.2), (-1.6, 2.2), (-4.3, -3.6), (-4.3, 3.6), (-7.2, -3.6), (-7.2, 2.4), (-1.7, 0.0))


def ceiling(b: Parts) -> None:
    """The coffered ceiling: a wooden frame round the cove with two cross beams, the cove's warm light on the inside of the long beams, brass lines, the downlights with their brass rims, a
    brass ring of the compass in the middle."""
    fb, fine, em = b.body, b.fine, b.emit
    cx0, cx1, cy0, cy1 = -LEN + 1.2, -1.2, -HW + 1.0, HW - 1.0
    for (x0, x1, y0, y1) in ((cx0, cx1, cy0, cy0 + 0.25), (cx0, cx1, cy1 - 0.25, cy1), (cx0, cx0 + 0.25, cy0, cy1), (cx1 - 0.25, cx1, cy0, cy1)):
        fb.box((x0, y0, H - 0.22), (x1, y1, H), WOOD)
    for xb in (-3.4, -5.3):                                                                            # the cross beams, a little lower than the frame
        fb.box((xb - 0.09, cy0 + 0.25, H - 0.16), (xb + 0.09, cy1 - 0.25, H), WOOD)
        em.box((xb - 0.0915, cy0 + 0.25, H - 0.158), (xb - 0.09, cy1 - 0.25, H - 0.152), BRASS)
        em.box((xb + 0.09, cy0 + 0.25, H - 0.158), (xb + 0.0915, cy1 - 0.25, H - 0.152), BRASS)
    for (xa, xb) in ((cx0 + 0.25, -5.3 - 0.09), (-5.3 + 0.09, -3.4 - 0.09), (-3.4 + 0.09, cx1 - 0.25)):
        for (x0_, x1_, y0_, y1_) in ((xa + 0.08, xb - 0.08, cy0 + 0.33, cy0 + 0.36), (xa + 0.08, xb - 0.08, cy1 - 0.36, cy1 - 0.33), (xa + 0.08, xa + 0.11, cy0 + 0.33, cy1 - 0.33),
                                     (xb - 0.11, xb - 0.08, cy0 + 0.33, cy1 - 0.33)):
            fine.box((x0_, y0_, H - 0.012), (x1_, y1_, H), WOOD)
    for sd in (-1, 1):
        y = cy1 - 0.25 if sd > 0 else cy0 + 0.25
        em.lamp_box((cx0 + 0.25, y - (0.012 if sd > 0 else 0.0), H - 0.205), (cx1 - 0.25, y + (0.0 if sd > 0 else 0.012), H - 0.165), "white_warm", LAMP_DIM)    # the cove
        em.box((cx0 + 0.25, y - (0.0016 if sd > 0 else 0.0), H - 0.2225), (cx1 - 0.25, y + (0.0 if sd > 0 else 0.0016), H - 0.2185), BRASS)
    for (x0, x1, y0, y1) in ((cx0, cx1, cy0 - 0.0016, cy0), (cx0, cx1, cy1, cy1 + 0.0016), (cx0 - 0.0016, cx0, cy0, cy1), (cx1, cx1 + 0.0016, cy0, cy1)):
        em.box((x0, y0, H - 0.2225), (x1, y1, H - 0.2185), BRASS)
    for (lx, ly) in DOWNLIGHTS:                                                                         # downlights: a brass rim, a lit lens
        em.cyl((lx, ly, H - 0.012), (lx, ly, H), 0.085, BRASS, seg=24, r2=0.085)
        em.cyl((lx, ly, H - 0.0145), (lx, ly, H - 0.012), 0.062, STRUCT, seg=24)
        em.lamp_cyl((lx, ly, H - 0.0165), (lx, ly, H - 0.0145), 0.055, "white_warm", LAMP, seg=24)
    for r_ in (0.55, 0.62):                                                                            # the ring of the compass in the coffer's middle
        for k in range(48):
            a0, a1 = 2 * math.pi * k / 48, 2 * math.pi * (k + 1) / 48
            em.cyl((-4.3 + r_ * math.cos(a0), 0.0 + r_ * math.sin(a0), H - 0.004), (-4.3 + r_ * math.cos(a1), 0.0 + r_ * math.sin(a1), H - 0.004), 0.0035, BRASS, seg=4)


def compass_rose(b: Parts, cx: float, cy: float, r: float) -> None:
    """A compass rose inlaid in the carpet in brass: two rings and a three-ring rule, four long points (the bow is +x) and four short ones."""
    em = b.emit
    z = 0.0079

    def ring(r0: float, r1: float, seg: int = 64) -> None:
        for k in range(seg):
            a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
            em.face([(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z), (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z), (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z),
                     (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z)], BRASS, (0, 0, 1))

    ring(r * 0.97, r)
    ring(r * 0.90, r * 0.915)
    ring(r * 0.60, r * 0.612)
    for k in range(8):
        a = math.radians(45.0 * k)
        ln = r * (0.88 if k % 2 == 0 else 0.58)
        wd = ln * (0.075 if k % 2 == 0 else 0.055)
        ca, sa = math.cos(a), math.sin(a)
        tip = (cx + ca * ln, cy + sa * ln, z)
        l_ = (cx + ca * ln * 0.30 - sa * wd, cy + sa * ln * 0.30 + ca * wd, z)
        r_ = (cx + ca * ln * 0.30 + sa * wd, cy + sa * ln * 0.30 - ca * wd, z)
        em.face([(cx, cy, z), l_, tip, r_], BRASS, (0, 0, 1))


# ============================================================================================================================ upholstery
def cushion(soft: FB, c, size, mat: str, yaw: float = 0.0, tilt: float = 0.0, puff: float = 0.0, roll: float = 0.0, round_: float = 0.55) -> None:
    """A cushion: a rounded block, size (length x, width y, height z) centred at c, turned by yaw, tipped by tilt (about y) and rolled (about x). The section across the length is a
    superellipse (`round_` 1 = an ellipse, 0 = nearly square) lofted along the length with rounded ends; the faces are smooth-shaded by the `soft` group."""
    lx, wy, hz = size
    p = 2.0 + 5.0 * (1.0 - round_)
    n_sec, n_len = 20, 11
    rings = []
    for k in range(n_len):
        u = math.sin(math.pi / 2 * (-1.0 + 2.0 * k / (n_len - 1)))
        sc = max(0.10, (1.0 - abs(u) ** 5) ** 0.2)
        ring = []
        for j in range(n_sec):
            a = 2 * math.pi * j / n_sec
            ca, sa = math.cos(a), math.sin(a)
            ring.append((u * lx / 2, wy / 2 * sc * math.copysign(abs(ca) ** (2.0 / p), ca), hz / 2 * sc * math.copysign(abs(sa) ** (2.0 / p), sa)))
        rings.append(ring)
    with soft.at(T(*c) @ Rz(yaw) @ Ry(tilt) @ Rx(roll)):
        soft.loft(rings, mat, caps=True, closed=True)


def curtain(soft: FB, p: float, a0: float, a1: float, z0: float, z1: float, mat: str, folds: int = 5, amp: float = 0.05, seed: int = 1, axis: str = "y", into: float = 1.0) -> None:
    """A pleated drape hanging between a0 and a1 along `axis` ('y': a sheet in the plane x = p; 'x': in the plane y = p) from z1 (the rod) down to z0: a thin solid sheet whose
    folds open towards the floor; `into` is the sign of the direction to the room across the sheet."""
    rng = random.Random(seed)
    n_a, n_z = 40, 9
    ph = rng.uniform(0, math.pi)
    rings = []
    for k in range(n_z):
        t = k / (n_z - 1)                                              # 0 at the rod, 1 at the floor
        z = lerp(z1, z0, t)
        am = amp * (0.45 + 0.55 * t ** 1.3)
        front, back = [], []
        for j in range(n_a):
            along = lerp(a0, a1, j / (n_a - 1))
            off = into * (am * math.sin(2 * math.pi * folds * j / (n_a - 1) + ph) + 0.004)
            front.append((p + off, along, z) if axis == "y" else (along, p + off, z))
            back.append((p + off - into * 0.012, along, z) if axis == "y" else (along, p + off - into * 0.012, z))
        rings.append(front + back[::-1])
    soft.loft(rings, mat, caps=True, closed=True)


def stud_rows(em: FB, x: float, ys, zs, facing=(1, 0, 0), r: float = 0.0085) -> None:
    """Brass buttons / studs on a surface at x (a grid of flat hexagons)."""
    for y in ys:
        for z in zs:
            hex_head(em, x, y, z, r, facing)


# ================================================================================================================================ the desk
def desk(b: Parts) -> None:
    """The Captain's desk (the data: x, y, width along y, depth along x): a walnut top with a cognac leather inlay in a brass line, two pedestals of three drawers with brass pulls on the
    sitter's side (aft), a modesty panel with a brass compass on the visitors' side; on it the terminal (the Captain's log), a banker's lamp, papers, a pen stand, a mug, a datapad,
    a framed picture, a model Falcon and a globe."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    dk = D["desk"]
    dx0, dx1 = dk["x"] - dk["depth"] / 2, dk["x"] + dk["depth"] / 2
    dy0, dy1 = dk["y"] - dk["width"] / 2, dk["y"] + dk["width"] / 2
    ytop = 0.76
    fb.box((dx0 - 0.03, dy0 - 0.03, 0.72), (dx1 + 0.03, dy1 + 0.03, ytop), WOOD)
    ix0, ix1, iy0, iy1 = dx0 + 0.08, dx1 - 0.08, dy0 + 0.12, dy1 - 0.12
    fine.box((ix0, iy0, ytop), (ix1, iy1, ytop + 0.0035), LEATHER)
    for (xa, xb, ya, yb) in ((ix0 - 0.004, ix1 + 0.004, iy0 - 0.004, iy0), (ix0 - 0.004, ix1 + 0.004, iy1, iy1 + 0.004), (ix0 - 0.004, ix0, iy0, iy1), (ix1, ix1 + 0.004, iy0, iy1)):
        em.box((xa, ya, ytop), (xb, yb, ytop + 0.0042), BRASS)
    for (y0, y1) in ((dy0 + 0.05, dy0 + 0.55), (dy1 - 0.55, dy1 - 0.05)):
        fb.box((dx0 + 0.05, y0, 0.08), (dx1 - 0.05, y1, 0.72), WOOD)
        fb.box((dx0 + 0.09, y0 + 0.035, 0.0), (dx1 - 0.09, y1 - 0.035, 0.08), WOOD)                        # the recessed plinth
        for k in range(3):                                                                                   # three drawers, fronts on the sitter's side
            z0 = 0.11 + k * 0.205
            fine.box((dx0 + 0.035, y0 + 0.025, z0), (dx0 + 0.05, y1 - 0.025, z0 + 0.185), WOOD)
            ym = (y0 + y1) / 2
            em.box((dx0 + 0.020, ym - 0.07, z0 + 0.078), (dx0 + 0.035, ym + 0.07, z0 + 0.094), BRASS)
            for sd in (-1, 1):
                em.box((dx0 + 0.020, ym + sd * 0.07 - 0.004, z0 + 0.078 - 0.012), (dx0 + 0.035, ym + sd * 0.07 + 0.004, z0 + 0.094 + 0.012), BRASS)
    fb.box((dx1 - 0.06, dy0 + 0.55, 0.12), (dx1 - 0.03, dy1 - 0.55, 0.72), WOOD)                            # the modesty panel and its brass medallion
    fine.box((dx1 - 0.03, dy0 + 0.62, 0.20), (dx1 - 0.018, dy1 - 0.62, 0.64), WOOD)
    ring_y, ring_z = dk["y"], 0.42
    for r0, r1 in ((0.12, 0.128), (0.095, 0.100)):
        for k in range(36):
            a0, a1 = 2 * math.pi * k / 36, 2 * math.pi * (k + 1) / 36
            pts = [(dx1 - 0.0175, ring_y + r0 * math.cos(a0), ring_z + r0 * math.sin(a0)), (dx1 - 0.0175, ring_y + r0 * math.cos(a1), ring_z + r0 * math.sin(a1)),
                   (dx1 - 0.0175, ring_y + r1 * math.cos(a1), ring_z + r1 * math.sin(a1)), (dx1 - 0.0175, ring_y + r1 * math.cos(a0), ring_z + r1 * math.sin(a0))]
            em.face(pts, BRASS, (1, 0, 0))
    for k in range(8):
        a = math.radians(45.0 * k)
        ln = 0.095 if k % 2 == 0 else 0.055
        wd = ln * 0.12
        ca, sa = math.cos(a), math.sin(a)
        em.face([(dx1 - 0.0175, ring_y, ring_z), (dx1 - 0.0175, ring_y + ca * ln * 0.3 - sa * wd, ring_z + sa * ln * 0.3 + ca * wd), (dx1 - 0.0175, ring_y + ca * ln, ring_z + sa * ln),
                 (dx1 - 0.0175, ring_y + ca * ln * 0.3 + sa * wd, ring_z + sa * ln * 0.3 - ca * wd)], BRASS, (1, 0, 0))
    # ---- on the desk
    z = ytop + 0.0035
    tx = dx0 + 0.30
    em.cyl((tx, dk["y"], z), (tx, dk["y"], z + 0.014), 0.085, BRASS, seg=24, r2=0.075)                    # the terminal: a brass foot and neck, a tilted dark housing, the Captain's log on it
    em.cyl((tx + 0.02, dk["y"], z + 0.014), (tx + 0.02, dk["y"], 0.99), 0.013, BRASS, seg=10)
    with b.at(T(tx + 0.04, dk["y"], 1.08) @ Ry(14)):
        fb.box((-0.0, -0.335, -0.220), (0.032, 0.335, 0.220), STRUCT)
        em.screen((-0.0008, 0.0, 0.0), 0.62, 0.39, LOG, (-1, 0, 0), up=(0, 0, 1))
        em.box((-0.0012, -0.318, -0.2035), (-0.0004, 0.318, -0.2015), BRASS)
    fine.box((dx0 + 0.07, dk["y"] - 0.19, z), (dx0 + 0.20, dk["y"] + 0.19, z + 0.012), STRUCT)           # a slim keyboard with a lit edge
    em.lamp_box((dx0 + 0.07, dk["y"] - 0.19, z + 0.0115), (dx0 + 0.0715, dk["y"] + 0.19, z + 0.0125), "amber_dim", LAMP_DIM)
    lx, ly = dx0 + 0.15, dy1 - 0.20                                                                          # the banker's lamp: a brass base, a stem, a long shade lit from inside
    em.cyl((lx, ly, z), (lx, ly, z + 0.022), 0.075, BRASS, seg=20, r2=0.06)
    em.cyl((lx, ly, z + 0.022), (lx, ly, z + 0.24), 0.011, BRASS, seg=8)
    soft.cyl((lx, ly - 0.17, z + 0.27), (lx, ly + 0.17, z + 0.27), 0.065, STRUCT, seg=18)
    em.lamp_cyl((lx, ly - 0.172, z + 0.27), (lx, ly + 0.172, z + 0.27), 0.052, "white_warm", LAMP_DIM, seg=18)
    soft.cyl((lx, ly - 0.17, z + 0.27), (lx, ly - 0.172, z + 0.27), 0.066, BRASS, seg=18)
    for k, (yy, rot) in enumerate(((dy0 + 0.35, 8.0), (dy0 + 0.40, -6.0))):                                    # papers and a pen stand
        fine.cbox((dx0 + 0.45, yy, z + 0.003 + 0.0035 * k), (0.21, 0.30, 0.003), LINEN, Rz(rot))
    em.cyl((dx0 + 0.30, dy0 + 0.70, z), (dx0 + 0.30, dy0 + 0.70, z + 0.05), 0.022, BRASS, seg=14)
    for k in range(2):
        soft.cyl((dx0 + 0.30 + 0.004 * (k * 2 - 1), dy0 + 0.70, z + 0.04), (dx0 + 0.30 + 0.02 * (k * 2 - 1), dy0 + 0.70 + 0.01, z + 0.15), 0.004, STRUCT, seg=6)
    LF.mug(soft, dx0 + 0.55, dy0 + 0.20, z, B3.IVORY, True, em, 30.0)
    LF.datapad(fb, em, dx1 - 0.22, dy1 - 0.52, z, yaw=200.0, page="checklist", w=0.17)
    LF.photo(fb, em, dx1 - 0.14, dy0 + 0.42, z, yaw=180.0, w=0.12, page="orbit")
    LF.falcon_model(fb, em, dx1 - 0.18, dy1 - 0.20, z, yaw=-60.0, scale=1.5)
    LF.globe(soft, em, dx1 - 0.22, dy0 + 0.95, z, yaw=0.0, r=0.06)


def captain_chair(b: Parts) -> None:
    """The Captain's chair behind the desk (aft of it, facing the door): a five-spoke brass base on castors, a gas column, a deep cognac seat, a tall back with button tufting and a headrest,
    wooden arms with leather pads and brass caps."""
    fb, em, soft = b.body, b.emit, b.soft
    dk = D["desk"]
    cx, cy = dk["x"] - dk["depth"] / 2 - 0.85, dk["y"]
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.3
        c, s = math.cos(a), math.sin(a)
        em.cyl((cx + 0.04 * c, cy + 0.04 * s, 0.11), (cx + 0.31 * c, cy + 0.31 * s, 0.07), 0.016, BRASS, seg=8)
        soft.cyl((cx + 0.31 * c, cy + 0.31 * s, 0.0), (cx + 0.31 * c, cy + 0.31 * s, 0.065), 0.03, B3.RUBBER, seg=10)
    fb.cyl((cx, cy, 0.10), (cx, cy, 0.44), 0.038, STRUCT, seg=12)
    em.cyl((cx, cy, 0.30), (cx, cy, 0.32), 0.046, BRASS, seg=12)
    fb.box((cx - 0.25, cy - 0.25, 0.43), (cx + 0.25, cy + 0.25, 0.47), STRUCT)
    cushion(soft, (cx + 0.01, cy, 0.52), (0.58, 0.60, 0.12), LEATHER, puff=0.10)
    cushion(soft, (cx - 0.255, cy, 0.95), (0.13, 0.54, 0.84), LEATHER, tilt=-8.0, puff=0.08)
    cushion(soft, (cx - 0.285, cy, 1.50), (0.12, 0.30, 0.22), LEATHER, tilt=-8.0, puff=0.10)
    stud_rows(em, cx - 0.1905, [cy - 0.17, cy, cy + 0.17], [0.72, 0.92, 1.12], facing=(1, 0, 0), r=0.0085)
    for sd in (-1, 1):
        fb.box((cx - 0.26, cy + sd * 0.325 - 0.014, 0.50), (cx - 0.22, cy + sd * 0.325 + 0.014, 0.68), WOOD)
        fb.box((cx - 0.23, cy + sd * 0.325 - 0.016, 0.66), (cx + 0.20, cy + sd * 0.325 + 0.016, 0.69), WOOD)
        cushion(soft, (cx - 0.02, cy + sd * 0.325, 0.71), (0.40, 0.07, 0.04), LEATHER, puff=0.12)
        em.cyl((cx + 0.20, cy + sd * 0.325, 0.675), (cx + 0.215, cy + sd * 0.325, 0.675), 0.021, BRASS, seg=14)


def visitor_chairs(b: Parts) -> None:
    """Two visitors' chairs facing the desk: four turned walnut legs with brass caps, a cognac seat, a back with studs along its rail."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    dk = D["desk"]
    gx = dk["x"] + dk["depth"] / 2 + 0.75
    for gy in (dk["y"] - 0.55, dk["y"] + 0.55):
        for (ex, ey) in ((-0.2, -0.2), (-0.2, 0.2), (0.2, -0.2), (0.2, 0.2)):
            fine.cyl((gx + ex, gy + ey, 0.02), (gx + ex, gy + ey, 0.44), 0.017, WOOD, seg=10, r2=0.014)
            em.cyl((gx + ex, gy + ey, 0.0), (gx + ex, gy + ey, 0.02), 0.019, BRASS, seg=10)
        fb.box((gx - 0.24, gy - 0.24, 0.42), (gx + 0.24, gy + 0.24, 0.46), WOOD)
        cushion(soft, (gx, gy, 0.50), (0.48, 0.46, 0.09), LEATHER, puff=0.10)
        fb.box((gx + 0.19, gy - 0.23, 0.46), (gx + 0.24, gy - 0.20, 0.96), WOOD)
        fb.box((gx + 0.19, gy + 0.20, 0.46), (gx + 0.24, gy + 0.23, 0.96), WOOD)
        cushion(soft, (gx + 0.21, gy, 0.74), (0.06, 0.40, 0.40), LEATHER, tilt=6.0, puff=0.10)
        fb.box((gx + 0.185, gy - 0.23, 0.94), (gx + 0.245, gy + 0.23, 0.99), WOOD)
        stud_rows(em, gx + 0.185 - 0.0005, [gy - 0.15, gy - 0.05, gy + 0.05, gy + 0.15], [0.965], facing=(-1, 0, 0), r=0.0075)



# ======================================================================================================================== the sitting area
def sofa(b: Parts) -> None:
    """The sofa against the port wall (data: x0 forward end, x1 aft end, depth): a walnut base on brass feet, three cognac seat cushions, three back cushions, rolled arms, two throw pillows
    and a folded navy blanket on one arm."""
    fb, em, soft = b.body, b.emit, b.soft
    sf = D["sofa"]
    xa, xb = sf["x1"], sf["x0"]                                              # aft end, forward end
    ya = -HW + FIN
    yb = ya + sf["depth"]
    fb.box((xa + 0.02, ya + 0.02, 0.10), (xb - 0.02, yb - 0.02, 0.30), WOOD)
    for (px, py) in ((xa + 0.10, ya + 0.10), (xa + 0.10, yb - 0.10), (xb - 0.10, ya + 0.10), (xb - 0.10, yb - 0.10)):
        em.cyl((px, py, 0.0), (px, py, 0.10), 0.03, BRASS, seg=10, r2=0.022)
    seat_len = (xb - xa - 0.5) / 3
    for k in range(3):
        xc = xa + 0.25 + seat_len * (k + 0.5)
        cushion(soft, (xc, ya + 0.45 + 0.07, 0.38), (seat_len - 0.012, 0.64, 0.16), LEATHER, puff=0.10)
        cushion(soft, (xc, ya + 0.17, 0.62), (seat_len - 0.012, 0.22, 0.46), LEATHER, tilt=0.0, puff=0.12, roll=0.0)
    for xe in (xa + 0.125, xb - 0.125):                                                                     # rolled arms
        cushion(soft, (xe, (ya + yb) / 2, 0.46), (yb - ya - 0.04, 0.25, 0.25), LEATHER, yaw=90.0, round_=1.0)
        fb.box((xe - 0.115, ya + 0.04, 0.30), (xe + 0.115, yb - 0.04, 0.40), WOOD)
    cushion(soft, (xa + 0.45, ya + 0.38, 0.62), (0.40, 0.14, 0.40), "MI_MED_Blanket", yaw=-14.0, tilt=-24.0, puff=0.18)
    cushion(soft, (xb - 0.50, ya + 0.38, 0.62), (0.40, 0.14, 0.40), LINEN, yaw=18.0, tilt=-24.0, puff=0.18)
    cushion(soft, (xb - 0.125, ya + 0.50, 0.605), (0.09, 0.40, 0.04), "MI_MED_Blanket", puff=0.05)


def low_table(b: Parts) -> None:
    """The low table before the sofa: a walnut top with a brass line, four turned legs with brass caps; a tray with books and a plant."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    sf = D["sofa"]
    tcx = (sf["x0"] + sf["x1"]) / 2
    ty = -2.625
    fb.box((tcx - 0.65, ty - 0.325, 0.38), (tcx + 0.65, ty + 0.325, 0.42), WOOD)
    for (xa, xb, ya, yb) in ((tcx - 0.65, tcx + 0.65, ty - 0.325, ty - 0.321), (tcx - 0.65, tcx + 0.65, ty + 0.321, ty + 0.325), (tcx - 0.65, tcx - 0.646, ty - 0.325, ty + 0.325),
                             (tcx + 0.646, tcx + 0.65, ty - 0.325, ty + 0.325)):
        em.box((xa, ya, 0.4205), (xb, yb, 0.4225), BRASS)
    for (ex, ey) in ((-0.58, -0.28), (-0.58, 0.28), (0.58, -0.28), (0.58, 0.28)):
        fine.cyl((tcx + ex, ty + ey, 0.016), (tcx + ex, ty + ey, 0.38), 0.022, WOOD, seg=10, r2=0.016)
        em.cyl((tcx + ex, ty + ey, 0.0), (tcx + ex, ty + ey, 0.016), 0.024, BRASS, seg=10)
    z = 0.4225
    fine.box((tcx - 0.28, ty - 0.20, z), (tcx + 0.10, ty + 0.20, z + 0.014), WOOD)                              # a tray
    em.box((tcx - 0.28, ty - 0.20, z + 0.014), (tcx + 0.10, ty - 0.196, z + 0.022), BRASS)
    em.box((tcx - 0.28, ty + 0.196, z + 0.014), (tcx + 0.10, ty + 0.20, z + 0.022), BRASS)
    for k, (col, w_) in enumerate(((LEATHER, 0.032), (RED, 0.026), ("MI_MED_Blanket", 0.03))):                   # a stack of books
        fine.cbox((tcx - 0.12, ty - 0.02, z + 0.014 + 0.016 + k * 0.034), (0.20 - 0.01 * k, 0.14, w_), col, Rz(8.0 * (k - 1)))
    LF.plant(soft, tcx + 0.34, ty + 0.0, z, size=0.8, seed=4)
    LF.datapad(fb, em, tcx + 0.30, ty + 0.22, z, yaw=-20.0, page="starmap", w=0.15)


def armchair(b: Parts) -> None:
    """A cognac armchair facing the table: a walnut frame on brass feet, a seat, a curved back with studs, rolled arms."""
    fb, em, soft = b.body, b.emit, b.soft
    ax, ay = D["sofa"]["x1"] - 0.8, -2.2
    with b.at(T(ax, ay, 0.0) @ Rz(-12.0)):
        fb.box((-0.36, -0.40, 0.10), (0.36, 0.40, 0.30), WOOD)
        for (px, py) in ((-0.30, -0.34), (-0.30, 0.34), (0.30, -0.34), (0.30, 0.34)):
            em.cyl((px, py, 0.0), (px, py, 0.10), 0.028, BRASS, seg=10, r2=0.02)
        cushion(soft, (0.04, 0.0, 0.38), (0.62, 0.64, 0.15), LEATHER, puff=0.10)
        cushion(soft, (-0.30, 0.0, 0.66), (0.16, 0.62, 0.52), LEATHER, tilt=-14.0, puff=0.12)
        for sd in (-1, 1):
            cushion(soft, (0.01, sd * 0.38, 0.50), (0.66, 0.17, 0.17), LEATHER, round_=1.0)
            fb.box((-0.28, sd * 0.38 - 0.07, 0.30), (0.30, sd * 0.38 + 0.07, 0.42), WOOD)
        stud_rows(em, -0.226, [-0.18, 0.0, 0.18], [0.74, 0.88], facing=(1, 0, 0), r=0.0075)


def floor_lamp(b: Parts, x: float, y: float) -> None:
    """A brass floor lamp: a weighted base, a slim stem, a pleated shade lit from inside."""
    em, soft = b.emit, b.soft
    em.cyl((x, y, 0.0), (x, y, 0.03), 0.17, BRASS, seg=24, r2=0.15)
    em.cyl((x, y, 0.03), (x, y, 1.45), 0.012, BRASS, seg=10)
    em.cyl((x, y, 0.62), (x, y, 0.64), 0.03, BRASS, seg=12)
    soft.cyl((x, y, 1.42), (x, y, 1.72), 0.115, "MI_MED_Linen", seg=24, r2=0.17)
    em.lamp_cyl((x, y, 1.43), (x, y, 1.71), 0.105, "white_warm", LAMP_DIM, seg=24, r2=0.155)


# ======================================================================================================================== the bunk
def bunk(b: Parts) -> None:
    """The bunk in its alcove at the forward end of the port wall (data: x0 forward end, x1 aft end, y0..y1, top of the mattress): a walnut frame with a panelled headboard against
    the forward wall, a linen mattress, a navy duvet folded back, two pillows, a folded throw, the partition with raised panels, a shelf of books over it, a curtain."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    bk = D["bunk"]
    xf, xa, y0, y1 = bk["x0"], bk["x1"], bk["y0"], bk["y1"]                                   # xf = forward end (-0.35), xa = aft end (-2.55)
    fb.box((xa, y0, 0.08), (xf, y1, 0.28), WOOD)
    for (px, py) in ((xa + 0.06, y0 + 0.06), (xa + 0.06, y1 - 0.06), (xf - 0.06, y0 + 0.06), (xf - 0.06, y1 - 0.06)):
        em.cyl((px, py, 0.0), (px, py, 0.08), 0.03, BRASS, seg=10, r2=0.022)
    fine.box((xa + 0.01, y1 - 0.0, 0.10), (xf - 0.01, y1 + 0.012, 0.26), WOOD)                   # the fascia on the open side
    em.box((xa + 0.01, y1 + 0.012, 0.255), (xf - 0.01, y1 + 0.0135, 0.262), BRASS)
    fb.box((xf - 0.05, y0, 0.28), (xf, y1, 1.25), WOOD)                                            # the headboard against the forward wall
    for (ya_, yb_) in ((y0 + 0.07, (y0 + y1) / 2 - 0.035), ((y0 + y1) / 2 + 0.035, y1 - 0.07)):
        fine.box((xf - 0.062, ya_, 0.42), (xf - 0.05, yb_, 1.12), WOOD)
    stud_rows(em, xf - 0.0625, [y0 + 0.14, (y0 + y1) / 2, y1 - 0.14], [1.19], facing=(-1, 0, 0), r=0.01)
    cushion(soft, ((xa + xf) / 2 + 0.02, (y0 + y1) / 2, 0.40), (2.12, 1.10, 0.20), LINEN, puff=0.05, round_=0.4)
    cushion(soft, ((xa + xf) / 2 - 0.32, (y0 + y1) / 2, 0.51), (1.50, 1.12, 0.07), "MI_MED_Blanket", puff=0.03, round_=0.5)
    fine.box((xf - 0.62 - 0.03, y0 + 0.02, 0.50), (xf - 0.62, y1 - 0.02, 0.505), LINEN)               # the sheet folded back over the duvet
    for sd in (-1, 1):
        cushion(soft, (xf - 0.30, (y0 + y1) / 2 + sd * 0.27, 0.56), (0.42, 0.46, 0.13), LINEN, puff=0.18, yaw=sd * 6.0)
    cushion(soft, (xa + 0.26, (y0 + y1) / 2, 0.545), (0.36, 1.02, 0.07), "MI_MED_Blanket", puff=0.06)       # a folded throw at the foot
    fb.box((xa - 0.20, -HW + FIN, 0.0), (xa - 0.12, y1 + 0.35, 2.0), WOOD)                           # the partition
    for (ya_, yb_) in ((-HW + FIN + 0.15, y0 + 0.30), (y0 + 0.50, y1 + 0.25)):
        fine.box((xa - 0.20 - 0.012, ya_, 0.25), (xa - 0.20, yb_, 1.75), WOOD)
    em.box((xa - 0.2125, y1 + 0.20, 0.95), (xa - 0.20, y1 + 0.22, 1.15), BRASS)                          # a brass pull
    fb.box((xa + 0.05, -HW + FIN, 1.62), (xf - 0.05, -HW + 0.30, 1.66), WOOD)                         # the shelf over the bed
    em.box((xa + 0.05, -HW + 0.298, 1.62), (xf - 0.05, -HW + 0.30, 1.66), BRASS)
    rng = random.Random(7)
    x = xa + 0.15
    while x < xf - 0.65:
        w = rng.uniform(0.03, 0.06)
        fine.box((x, -HW + 0.08, 1.66), (x + w, -HW + 0.26, 1.66 + rng.uniform(0.18, 0.25)), rng.choice(BOOKS))
        x += w + 0.004
    LF.photo(fb, em, xf - 0.30, -HW + 0.20, 1.66, yaw=90.0, w=0.14, page="ship")
    em.cyl((xf - 0.55, -HW + FIN, 1.30), (xf - 0.55, -HW + 0.20, 1.30), 0.02, BRASS, seg=8)                # the reading light's arm and shade
    soft.cyl((xf - 0.55, -HW + 0.25, 1.32), (xf - 0.55, -HW + 0.17, 1.26), 0.06, STRUCT, seg=12, r2=0.03)
    em.lamp_cyl((xf - 0.55, -HW + 0.255, 1.325), (xf - 0.55, -HW + 0.25, 1.32), 0.055, "white_warm", LAMP, seg=12)
    for k in range(10):                                                                                    # the curtain, tied back at the partition: pleats
        yk = y1 + 0.27 + k * 0.042
        h = 2.0 - 0.08 * (k % 3)
        soft.cyl((xa - 0.12 - 0.01 * (k % 2), yk, 0.04), (xa - 0.12 - 0.01 * (k % 2), yk, h), 0.026, "MI_MED_Blanket", seg=8)
    em.cyl((xa - 0.12, y1 + 0.25, 2.05), (xa - 0.12, y1 + 0.70, 2.05), 0.012, BRASS, seg=8)



# ====================================================================================================================== the bookcase
def telescope(em: FB, fine: FB, x: float, y: float, z: float, length: float = 0.5, yaw: float = 0.0) -> None:
    """A brass telescope lying on a shelf on two small wooden cradles: three sections and a lens cap."""
    with em.at(T(x, y, z) @ Rz(yaw)), fine.at(T(x, y, z) @ Rz(yaw)):
        sections = ((0.024, 0.46), (0.020, 0.30), (0.016, 0.24))                                     # radius, share of the length
        cur = -length / 2
        for r0, share in sections:
            ln = length * share
            em.cyl((cur, 0.0, 0.026), (cur + ln, 0.0, 0.026), r0, BRASS, seg=14)
            cur += ln
        em.cyl((-length / 2 - 0.012, 0.0, 0.026), (-length / 2, 0.0, 0.026), 0.026, BRASS, seg=14)
        for xx in (-length / 4, length / 4):
            fine.box((xx - 0.012, -0.03, 0.0), (xx + 0.012, 0.03, 0.012), WOOD)


def bookcase(b: Parts) -> None:
    """The bookcase on the starboard wall (data): walnut with a cornice and a brass trim, a lower cabinet with doors, five shelves of books, a brass telescope, a globe, a model ship, a framed
    picture."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    bc = D["bookcase"]
    xa, xf = bc["x1"], bc["x0"]                                      # aft end, forward end
    y0, y1 = HW - FIN - bc["depth"], HW - FIN
    h = bc["height"]
    fb.box((xa, y1 - 0.02, 0.0), (xf, y1, h), WOOD)                                                # the back
    for xe in (xa, xf - 0.04):
        fb.box((xe, y0, 0.0), (xe + 0.04, y1, h), WOOD)
    levels = [0.08 + k * (h - 0.1) / 5 for k in range(6)]
    for k, z in enumerate(levels):
        fb.box((xa, y0, z), (xf, y1, z + 0.03), WOOD)
        em.box((xa + 0.04, y0 - 0.0015, z + 0.0), (xf - 0.04, y0, z + 0.03), BRASS)
    fb.box((xa - 0.04, y0 - 0.03, h), (xf + 0.04, y1, h + 0.05), WOOD)                                # the cornice
    em.box((xa - 0.04, y0 - 0.0315, h + 0.005), (xf + 0.04, y0 - 0.03, h + 0.045), BRASS)
    n_doors = 3
    for k in range(n_doors):                                                                           # the lower cabinet's doors
        da, db = xa + 0.06 + k * (xf - xa - 0.12) / n_doors, xa + 0.06 + (k + 1) * (xf - xa - 0.12) / n_doors
        fine.box((da + 0.01, y0 - 0.02, levels[0] + 0.03), (db - 0.01, y0, levels[1] - 0.02), WOOD)
        fine.box((da + 0.05, y0 - 0.026, levels[0] + 0.07), (db - 0.05, y0 - 0.02, levels[1] - 0.06), WOOD)
        em.box(((da + db) / 2 - 0.05, y0 - 0.034, (levels[0] + levels[1]) / 2 + 0.0), ((da + db) / 2 + 0.05, y0 - 0.026, (levels[0] + levels[1]) / 2 + 0.014), BRASS)
    rng = random.Random(7)
    for k in range(1, 5):
        z = levels[k] + 0.03
        x = xa + 0.06
        zone = (xf - 0.06) if k not in (2, 3) else (xf - 0.60)                                          # two shelves keep room at the forward end for objects
        while x < zone - 0.05:
            if rng.random() < 0.10:
                x += rng.uniform(0.08, 0.18)
                continue
            w = rng.uniform(0.025, 0.055)
            hh = rng.uniform(0.18, (levels[k + 1] - levels[k]) - 0.08)
            col = rng.choice(BOOKS)
            fine.box((x, y0 + 0.05, z), (x + w, y1 - 0.04, z + hh), col)
            if rng.random() < 0.35:
                em.box((x + 0.003, y0 + 0.0485, z + hh * 0.55), (x + w - 0.003, y0 + 0.0495, z + hh * 0.55 + 0.012), BRASS)
            x += w + 0.002
    telescope(em, fine, xf - 0.32, (y0 + y1) / 2 + 0.02, levels[2] + 0.03, 0.5, yaw=8.0)
    LF.globe(soft, em, xf - 0.30, (y0 + y1) / 2, levels[3] + 0.03, yaw=0.0, r=0.07)
    LF.plant(soft, xf - 0.30, (y0 + y1) / 2, levels[4] + 0.03, size=1.1, seed=11)


# ======================================================================================================================== the galley
def galley(b: Parts) -> None:
    """The galley corner at the forward wall, starboard side (data: y0..y1 along the wall): walnut base cabinets with brass pulls, an ivory top with a brass nosing and a backsplash, a sink
    with a brass tap, an espresso machine, a kettle and mugs, wall cabinets with glass doors lit underneath."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    gl = D["galley"]
    y0, y1 = gl["y0"], gl["y1"]
    xw = -FIN                                                          # against the wall
    xf = xw - 0.67                                                     # the counter's front
    mods = [(y0, y0 + 1.0), (y0 + 1.0, y0 + 1.8), (y0 + 1.8, y0 + 2.5), (y0 + 2.5, y1)]
    fb.box((xf, y0, 0.0), (xw, y1, 0.10), STRUCT)
    for (ya, yb) in mods:
        fb.box((xf + 0.02, ya + 0.01, 0.10), (xw, yb - 0.01, 0.86), WOOD)
        fine.box((xf, ya + 0.025, 0.14), (xf + 0.02, yb - 0.025, 0.82), WOOD)
        fine.box((xf - 0.006, ya + 0.075, 0.19), (xf, yb - 0.075, 0.77), WOOD)
        em.box((xf - 0.016, (ya + yb) / 2 - 0.07, 0.72), (xf - 0.006, (ya + yb) / 2 + 0.07, 0.736), BRASS)
    fb.box((xf - 0.03, y0, 0.86), (xw, y1, 0.90), B3.IVORY)                                                 # the top
    em.box((xf - 0.0315, y0, 0.865), (xf - 0.03, y1, 0.895), BRASS)
    fb.box((xw - 0.02, y0, 0.90), (xw, y1, 1.40), B3.IVORY)                                                 # the backsplash
    em.box((xw - 0.0215, y0, 1.395), (xw - 0.02, y1, 1.401), BRASS)
    sy = y0 + 1.4                                                                                             # the sink and its tap
    fine.box((xf + 0.10, sy - 0.30, 0.895), (xw - 0.08, sy + 0.30, 0.9005), STRUCT)
    fine.box((xf + 0.12, sy - 0.27, 0.80), (xw - 0.10, sy + 0.27, 0.8975), STRUCT)
    em.cyl((xw - 0.07, sy, 0.90), (xw - 0.07, sy, 1.12), 0.012, BRASS, seg=10)
    em.cyl((xw - 0.07, sy, 1.12), (xw - 0.16, sy, 1.10), 0.011, BRASS, seg=10)
    cy = y0 + 2.15                                                                                            # the espresso machine
    fb.box((xw - 0.40, cy - 0.17, 0.90), (xw - 0.07, cy + 0.17, 1.30), STRUCT)
    fb.box((xw - 0.40, cy - 0.17, 1.26), (xw - 0.07, cy + 0.17, 1.32), BRASS)
    fine.box((xw - 0.43, cy - 0.12, 0.90), (xw - 0.40, cy + 0.12, 0.93), STRUCT)
    em.cyl((xw - 0.43, cy - 0.06, 1.10), (xw - 0.40, cy - 0.06, 1.10), 0.028, BRASS, seg=14)
    em.cyl((xw - 0.43, cy + 0.06, 1.10), (xw - 0.40, cy + 0.06, 1.10), 0.028, BRASS, seg=14)
    em.lamp_cyl((xw - 0.4015, cy, 1.20), (xw - 0.40, cy, 1.20), 0.012, "amber", LAMP_DIM, seg=10)
    for yy, rot in ((cy - 0.34, 20.0), (cy + 0.36, 160.0)):
        LF.mug(soft, xw - 0.24, yy, 0.90, B3.IVORY, True, em, rot)
    soft.cyl((xw - 0.20, y0 + 3.05, 0.90), (xw - 0.20, y0 + 3.05, 1.06), 0.09, STRUCT, seg=18, r2=0.06)           # a kettle
    em.cyl((xw - 0.20, y0 + 3.05, 1.06), (xw - 0.20, y0 + 3.05, 1.075), 0.065, BRASS, seg=18)
    LF.plant(soft, xw - 0.18, y1 - 0.20, 0.90, size=0.8, seed=21)
    za, zb = 1.55, 2.30                                                                                       # wall cabinets with glass doors
    fb.box((xw - 0.35, y0, za), (xw, y1, zb), WOOD)
    for (ya, yb) in mods:
        fine.box((xw - 0.358, ya + 0.025, za + 0.025), (xw - 0.35, yb - 0.025, zb - 0.025), WOOD)
        fine.box((xw - 0.366, ya + 0.075, za + 0.075), (xw - 0.358, yb - 0.075, zb - 0.075), WOOD)
        em.box((xw - 0.3672, ya + 0.075, za + 0.075), (xw - 0.366, yb - 0.075, za + 0.0785), BRASS)
        em.box((xw - 0.3672, ya + 0.075, zb - 0.0785), (xw - 0.366, yb - 0.075, zb - 0.075), BRASS)
        em.box((xw - 0.3672, (ya + yb) / 2 - 0.06, za + 0.09), (xw - 0.3585, (ya + yb) / 2 + 0.06, za + 0.104), BRASS)
    em.lamp_box((xw - 0.33, y0 + 0.05, za - 0.004), (xw - 0.03, y1 - 0.05, za), "white_warm", LAMP_DIM)         # the light under them


# ================================================================================================================ the sideboard and the window
def sideboard(b: Parts) -> None:
    """The sideboard under the starboard window (data: model_pedestal x): a walnut cabinet with two panelled doors and brass pulls, its top with a brass line and the brass cradle of the
    ship's model (the model itself is placed in Unreal), a small brass plaque."""
    fb, fine, em = b.body, b.fine, b.emit
    mp = D["model_pedestal"]
    x0, x1 = mp["x"] - 0.85, mp["x"] + 0.85
    ya, yb = HW - FIN - 0.42, HW - FIN
    fb.box((x0, ya, 0.0), (x1, yb, 0.78), WOOD)
    fb.box((x0 - 0.01, ya - 0.01, 0.78), (x1 + 0.01, yb, 0.80), WOOD)
    em.box((x0 - 0.0115, ya - 0.0115, 0.7925), (x1 + 0.0115, ya - 0.01, 0.7975), BRASS)
    for k in range(2):
        xa = x0 + 0.04 + k * 0.80
        fine.box((xa, ya - 0.012, 0.10), (xa + 0.77, ya, 0.74), WOOD)
        fine.box((xa + 0.07, ya - 0.018, 0.17), (xa + 0.70, ya - 0.012, 0.67), WOOD)
        em.box((xa + 0.31 + (0.2 if k == 0 else -0.2), ya - 0.03, 0.40), (xa + 0.33 + (0.2 if k == 0 else -0.2), ya - 0.018, 0.54), BRASS)
    cx, cy = mp["x"], HW - 0.30
    em.cyl((cx, cy, 0.80), (cx, cy, 0.82), 0.14, BRASS, seg=24, r2=0.12)
    em.cyl((cx, cy, 0.82), (cx, cy, 0.99), 0.012, BRASS, seg=8)
    for dx in (-0.26, 0.26):
        em.cyl((cx + dx, cy, 0.80), (cx + dx, cy, 0.98), 0.010, BRASS, seg=8)
    em.box((cx - 0.30, cy - 0.012, 0.975), (cx + 0.30, cy + 0.012, 0.99), BRASS)
    em.box((cx - 0.10, ya - 0.0125, 0.806), (cx + 0.10, ya - 0.0105, 0.836), BRASS)


def window_seat(b: Parts) -> None:
    """The window seat under the left of the great aft window: a walnut box with panelled front and a brass line, a cognac cushion, five pillows, a throw."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    y0, y1 = -3.7, -0.7
    xw = -LEN + FIN
    fb.box((xw, y0, 0.0), (xw + 0.55, y1, 0.44), WOOD)
    for k in range(3):
        ya, yb = y0 + 0.08 + k * (y1 - y0 - 0.08) / 3, y0 + (k + 1) * (y1 - y0 - 0.08) / 3
        fine.box((xw + 0.55, ya + 0.04, 0.06), (xw + 0.562, yb - 0.04, 0.40), WOOD)
    em.box((xw + 0.5625, y0, 0.425), (xw + 0.5645, y1, 0.431), BRASS)
    cushion(soft, (xw + 0.29, (y0 + y1) / 2, 0.50), (2.96, 0.56, 0.10), LEATHER, round_=0.5, yaw=90.0)
    for k, (yy, col, tl, ya_) in enumerate(((y0 + 0.30, "MI_MED_Blanket", -22.0, 8.0), (y0 + 0.75, LINEN, -26.0, -10.0), (y0 + 1.55, LEATHER, -22.0, 6.0),
                                           (y0 + 2.15, "MI_MED_Blanket", -24.0, -8.0), (y0 + 2.62, LINEN, -26.0, 12.0))):
        cushion(soft, (xw + 0.14, yy, 0.67), (0.40, 0.14, 0.40), col, yaw=ya_ + 90.0, tilt=tl, puff=0.18)


def drapes(b: Parts) -> None:
    """Navy drapes in pleats on brass rods with rings and finials: either side of the great aft window, either side of the starboard window."""
    em, soft = b.emit, b.soft
    xw = -LEN + FIN + 0.07
    zrod = 2.88
    em.cyl((xw, -4.50, zrod), (xw, 4.50, zrod), 0.014, BRASS, seg=10)
    for sd in (-1, 1):
        em.sphere((xw, sd * 4.52, zrod), 0.028, BRASS, seg=10, rings=6)
        y0, y1 = (3.70, 4.50) if sd > 0 else (-4.50, -3.70)
        curtain(soft, xw - 0.03, y0, y1, 0.02, zrod - 0.03, "MI_MED_Blanket", folds=5, amp=0.045, seed=3 + sd, axis="y", into=1.0)
        for k in range(7):
            yk = y0 + 0.06 + k * (y1 - y0 - 0.12) / 6
            em.cyl((xw - 0.012, yk - 0.018, zrod - 0.016), (xw - 0.012, yk + 0.018, zrod - 0.016), 0.019, BRASS, seg=10)
    ws = D["window_side"]
    ys = HW - FIN - 0.07
    zr2 = 2.75
    em.cyl((ws["x0"] - 0.55, ys, zr2), (ws["x1"] + 0.55, ys, zr2), 0.013, BRASS, seg=10)
    for xend in (ws["x0"] - 0.57, ws["x1"] + 0.57):
        em.sphere((xend, ys, zr2), 0.026, BRASS, seg=10, rings=6)
    curtain(soft, ys - 0.03, ws["x0"] - 0.55, ws["x0"] + 0.05, 0.02, zr2 - 0.03, "MI_MED_Blanket", folds=4, amp=0.04, seed=11, axis="x", into=-1.0)
    curtain(soft, ys - 0.03, ws["x1"] - 0.05, ws["x1"] + 0.55, 0.02, zr2 - 0.03, "MI_MED_Blanket", folds=4, amp=0.04, seed=12, axis="x", into=-1.0)


# =================================================================================================================== the walls' pictures and things
def clock(em: FB, fine: FB, y: float, z: float, r: float = 0.12) -> None:
    """A ship's clock on the forward wall: a brass bezel, an ivory face with twelve ticks and two hands."""
    from bridge3_marks import annulus, disc
    x = -FIN - 0.004
    f, up = (-1, 0, 0), (0, 0, 1)
    disc(em, (x, y, z), r * 0.92, B3.IVORY, f, up)
    annulus(em, (x - 0.0006, y, z), r * 0.92, r, BRASS, f, up)
    for k in range(12):
        a = math.radians(30.0 * k)
        ln = r * (0.16 if k % 3 == 0 else 0.08)
        ra, rb = r * 0.86 - ln, r * 0.86
        ca, sa = math.cos(a), math.sin(a)
        fine.box((x - 0.0012, y + sa * ra - 0.0025, z + ca * ra - 0.0025), (x - 0.0006, y + sa * rb + 0.0025, z + ca * rb + 0.0025), STRUCT)
    for ang, ln in ((300.0, 0.50), (60.0, 0.72)):
        a = math.radians(ang)
        fine.cbox((x - 0.0016, y + math.sin(a) * r * ln / 2, z + math.cos(a) * r * ln / 2), (0.001, 0.006, r * ln), STRUCT, Rx(-ang))
    em.cyl((x - 0.0022, y, z), (x - 0.0030, y, z), 0.008, BRASS, seg=10)


def picture_frame(b: Parts, wall: str, s: float, z: float, w: float, h: float, page: str) -> None:
    """A framed chart on a wall (wall frame, s along it): a walnut frame with a brass inner line and a page of the decor atlas behind glass."""
    fb, fine, em = b.body, b.fine, b.emit
    with b.at(wall_frame(wall)):
        bw = 0.05
        for (sa, sb, za, zb) in ((s - w / 2 - bw, s + w / 2 + bw, z - h / 2 - bw, z - h / 2), (s - w / 2 - bw, s + w / 2 + bw, z + h / 2, z + h / 2 + bw),
                                 (s - w / 2 - bw, s - w / 2, z - h / 2, z + h / 2), (s + w / 2, s + w / 2 + bw, z - h / 2, z + h / 2)):
            fb.box((sa, 0.0, za), (sb, 0.032, zb), WOOD)
        for (sa, sb, za, zb) in ((s - w / 2, s + w / 2, z - h / 2, z - h / 2 + 0.004), (s - w / 2, s + w / 2, z + h / 2 - 0.004, z + h / 2),
                                 (s - w / 2, s - w / 2 + 0.004, z - h / 2, z + h / 2), (s + w / 2 - 0.004, s + w / 2, z - h / 2, z + h / 2)):
            em.box((sa, 0.030, za), (sb, 0.0315, zb), BRASS)
        fine.box((s - w / 2, 0.0, z - h / 2), (s + w / 2, 0.026, z + h / 2), DGLASS)
        em.decor((s, 0.0268, z), w - 0.012, h - 0.012, (0, 1, 0), page, up=(0, 0, 1))


def sector_chart(b: Parts) -> None:
    """The sector chart on the forward wall (data: map_screen): a wide walnut frame with a brass inner line round the live screen (MI_QTR_Map)."""
    fb, em = b.body, b.emit
    ms = D["map_screen"]
    w_ = ms["y1"] - ms["y0"]
    h_ = w_ / 2
    yc = (ms["y0"] + ms["y1"]) / 2
    zc = ms["zc"]
    bw = 0.07
    for (ya, yb, za, zb) in ((yc - w_ / 2 - bw, yc + w_ / 2 + bw, zc - h_ / 2 - bw, zc - h_ / 2), (yc - w_ / 2 - bw, yc + w_ / 2 + bw, zc + h_ / 2, zc + h_ / 2 + bw),
                             (yc - w_ / 2 - bw, yc - w_ / 2, zc - h_ / 2, zc + h_ / 2), (yc + w_ / 2, yc + w_ / 2 + bw, zc - h_ / 2, zc + h_ / 2)):
        fb.box((-FIN - 0.04, ya, za), (-FIN, yb, zb), WOOD)
    for (ya, yb, za, zb) in ((yc - w_ / 2, yc + w_ / 2, zc - h_ / 2, zc - h_ / 2 + 0.005), (yc - w_ / 2, yc + w_ / 2, zc + h_ / 2 - 0.005, zc + h_ / 2),
                             (yc - w_ / 2, yc - w_ / 2 + 0.005, zc - h_ / 2, zc + h_ / 2), (yc + w_ / 2 - 0.005, yc + w_ / 2, zc - h_ / 2, zc + h_ / 2)):
        em.box((-FIN - 0.0415, ya, za), (-FIN - 0.04, yb, zb), BRASS)
    fb.box((-FIN - 0.032, yc - w_ / 2, zc - h_ / 2), (-FIN, yc + w_ / 2, zc + h_ / 2), STRUCT)
    em.screen((-FIN - 0.0325, yc, zc), w_, h_, MAP, (-1, 0, 0), up=(0, 0, 1))


def wall_things(b: Parts) -> None:
    """The things on the walls: the clock and the Captain's cap on its hook board right of the door, the ASTRA Navy pennant and the commission aft on the port wall, wall lamps over the
    sofa, framed charts."""
    from bridge3_marks import emblem
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    clock(em, fine, 1.12, 2.02, 0.12)
    with b.at(wall_frame("fwd")):                                                                              # the hook board: three brass hooks, the cap, a scarf
        fb.box((0.95, 0.0, 1.55), (1.29, 0.026, 1.66), WOOD)
        em.box((0.95, 0.0255, 1.605), (1.29, 0.0275, 1.607), BRASS)
        for sx in (1.0, 1.12, 1.24):
            em.cyl((sx, 0.026, 1.60), (sx, 0.066, 1.60), 0.006, BRASS, seg=8)
            em.cyl((sx, 0.066, 1.60), (sx, 0.066, 1.625), 0.006, BRASS, seg=8)
        zc = 1.50                                                                                                  # the cap, hung by its band: a black band, a navy crown flaring out, a peak, the badge
        soft.cyl((1.12, 0.034, zc), (1.12, 0.066, zc), 0.094, B3.RUBBER, seg=28)
        soft.cyl((1.12, 0.066, zc), (1.12, 0.112, zc), 0.094, "MI_MED_Blanket", seg=28, r2=0.122)
        soft.cyl((1.12, 0.112, zc), (1.12, 0.118, zc), 0.122, "MI_MED_Blanket", seg=28)
        fine.cbox((1.12, 0.098, zc - 0.088), (0.17, 0.085, 0.008), B3.RUBBER, Rx(-16.0))
        em.cyl((1.12, 0.118, zc), (1.12, 0.1205, zc), 0.016, BRASS, seg=14)
        em.box((1.12 - 0.04, 0.0675, zc + 0.0), (1.12 + 0.04, 0.0685, zc + 0.003), BRASS)
    with b.at(wall_frame("port")):
        for xs in (-3.45, -5.75):                                                                              # wall lamps over the sofa: a brass arm, a lit shade
            em.cyl((xs, 0.0, 1.75), (xs, 0.10, 1.75), 0.011, BRASS, seg=8)
            em.cyl((xs, 0.10, 1.70), (xs, 0.10, 1.80), 0.011, BRASS, seg=8)
            soft.cyl((xs, 0.13, 1.70), (xs, 0.13, 1.86), 0.045, "MI_MED_Linen", seg=16, r2=0.075)
            em.lamp_cyl((xs, 0.13, 1.705), (xs, 0.13, 1.855), 0.038, "white_warm", LAMP_DIM, seg=16, r2=0.068)
        fb.box((-7.30, 0.0, 1.30), (-6.20, 0.014, 2.00), WOOD)                                                  # the pennant's board and a navy pennant with the roundel
        fine.box((-7.28, 0.014, 1.32), (-6.22, 0.018, 1.98), "MI_MED_Blanket")
        emblem(em, (-6.75, 0.0182, 1.65), 0.22, "MI_MED_Linen", (0, 1, 0), (0, 0, 1))
        em.box((-7.30, 0.0, 2.00), (-6.20, 0.02, 2.012), BRASS)
    picture_frame(b, "aft", 4.27, 1.70, 0.26, 0.17, "orbit")
    picture_frame(b, "aft", -4.27, 1.70, 0.26, 0.17, "starmap")


def corner_plants(b: Parts) -> None:
    """A tall plant in a brass planter in the aft starboard corner, a smaller one by the bunk's partition."""
    soft, em = b.soft, b.emit
    LF.plant(soft, -8.05, 4.05, 0.0, size=2.4, seed=3, pot=B3.IVORY)
    em.cyl((-8.05, 4.05, 0.0), (-8.05, 4.05, 0.012), 0.20, BRASS, seg=20)
    floor_lamp(b, -3.05, -4.20)


# =========================================================================================================================== assemble
def build_room(name: str = "SM_QTR_Room"):
    b = new_parts()
    shell(b)
    for wall, (s0, s1) in (("fwd", (-HW + FIN, HW - FIN)), ("aft", (-HW + FIN, HW - FIN)), ("port", (-LEN + FIN, -FIN)), ("stbd", (FIN, LEN - FIN))):
        dress_wall(b, wall, s0, s1)
    door_frame(b)
    windows(b)
    ceiling(b)
    compass_rose(b, -3.4, 0.0, 0.85)
    for part in (desk, captain_chair, visitor_chairs, sofa, low_table, armchair, bunk, bookcase, galley, sideboard, window_seat, drapes, sector_chart, wall_things, corner_plants):
        part(b)
    return b.build(name, uv_meter=1.2, small_uv_meter=0.3)


def build_glass(name: str = "SM_QTR_Glass"):
    """The windows' panes (translucent: not Nanite): the aft window's three bays between its mullions, the starboard window."""
    b = new_parts()
    fb = b.body
    wa, ws = D["window_aft"], D["window_side"]
    ys = [wa["y0"], *wa["mullions"], wa["y1"]]
    for y0, y1 in zip(ys, ys[1:]):
        fb.box((-LEN - 0.2, y0 + (0.06 if y0 != wa["y0"] else 0.0), wa["z0"]), (-LEN - 0.18, y1 - (0.06 if y1 != wa["y1"] else 0.0), wa["z1"]), A.MAT_GLASS)
    fb.box((ws["x0"], HW + 0.18, ws["z0"]), (ws["x1"], HW + 0.2, ws["z1"]), A.MAT_GLASS)
    b.bevel = 0.0
    return b.build(name, uv_meter=2.0)


# ================================================================================================================================ preview
VIEWS = {
    # name: (eye, yaw, pitch, fov) in the cabin's frame
    "entry": ((-0.5, 0.0, 1.62), 180.0, -4.0, 82.0),
    "sofa": ((-1.0, 2.0, 1.55), -120.0, -8.0, 80.0),
    "desk": ((-3.0, -1.0, 1.55), 139.0, -8.0, 80.0),
    "bunk": ((-2.5, 1.0, 1.5), -79.0, -6.0, 80.0),
    "galley": ((-3.0, -1.0, 1.55), 59.0, -6.0, 80.0),
    "bookcase": ((-3.0, -2.0, 1.55), 90.0, -4.0, 80.0),
    "door": ((-6.5, 0.5, 1.5), 0.0, -2.0, 80.0),
    "ceiling": ((-4.3, 0.0, 1.2), 180.0, 55.0, 85.0),
    "window": ((-3.5, 0.3, 1.5), 180.0, 0.0, 70.0),
    "deskclose": ((-5.4, 1.2, 1.65), 160.0, -22.0, 58.0),
    "sideboard": ((-3.0, 1.8, 1.45), 70.0, -8.0, 62.0),
    "bunkclose": ((-3.4, -2.2, 1.35), -95.0, -14.0, 60.0),
    "hooks": ((-1.6, 0.3, 1.5), 8.0, -4.0, 55.0),
    "seat": ((-4.6, 1.0, 1.45), 175.0, -12.0, 62.0),
}


def preview(out_dir: str, views: list[str], samples: int) -> None:
    """The cabin as the level lights it (tools/ue_scripts/build_quarters.py: a cove, three downlights, the desk lamp, the reading light), rendered in Eevee."""
    import bpy
    import bridge3_preview as PV
    A.clear_objects()
    build_room()
    build_glass()
    PV.make_materials({})
    PV.make_cabin_materials()
    PV.set_world((0.0, 0.0, 0.0), 0.0)
    PV.sky_dome(yaw_deg=180.0, strength=float(os.environ.get("QR_SKY", "0.30")))
    PV.configure_render(int(os.environ.get("QR_W", "1600")), int(os.environ.get("QR_H", "900")), samples, exposure=float(os.environ.get("QR_EXPOSURE", "0.5")))
    gain = float(os.environ.get("QR_GAIN", "1.0"))

    def light(kind, name, loc, energy, color, pitch=-90.0, yaw=0.0, size=None, cone=None, shadows=False):
        ld = bpy.data.lights.new(name, kind)
        ld.energy = energy * gain
        ld.color = color
        ld.use_shadow = shadows
        if kind == "AREA":
            ld.shape = "RECTANGLE"
            ld.size, ld.size_y = size
        if kind == "SPOT":
            ld.spot_size = math.radians(cone[0] * 2)
            ld.spot_blend = max(0.05, (cone[0] - cone[1]) / cone[0])
            ld.shadow_soft_size = 0.1
        if kind == "POINT":
            ld.shadow_soft_size = 0.08
        o = bpy.data.objects.new(name, ld)
        bpy.context.scene.collection.objects.link(o)
        o.location = (loc[0], -loc[1], loc[2])
        d = Vector((math.cos(math.radians(pitch)) * math.cos(math.radians(yaw)), -math.cos(math.radians(pitch)) * math.sin(math.radians(yaw)), math.sin(math.radians(pitch))))
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()

    warm31, warm29, warm27 = (1.0, 0.708, 0.458), (1.0, 0.683, 0.403), (1.0, 0.654, 0.343)
    light("AREA", "Cove", (-4.3, 0.0, H - 0.2), 5200 * 0.030 * (1 + 0.4 * math.log10(1 + 28.0)), warm31, size=(5.6, 5.0))
    for nm, (x, y), lm in (("Sofa", (-4.3, -3.6), 1400), ("Desk", (-7.2, 2.4), 1400), ("Galley", (-1.6, 2.2), 900)):
        light("SPOT", "Down_" + nm, (x, y, H - 0.02), lm * 0.16, warm29, cone=(48.0, 20.0), shadows=(nm == "Sofa"))
    dk, bk = D["desk"], D["bunk"]
    light("POINT", "DeskLamp", (dk["x"] - 0.45 + 0.12, dk["y"] + 0.88, 1.08), 450 * 0.16, warm27)
    light("SPOT", "Reading", (bk["x0"] - 0.55, -HW + 0.3, 1.26), 300 * 0.16, warm27, pitch=-60.0, yaw=90.0, cone=(40.0, 16.0))
    os.makedirs(out_dir, exist_ok=True)
    for v in views:
        eye, yaw, pitch, fov = VIEWS[v]
        cam = PV.add_camera(v, eye, yaw, pitch, fov)
        PV.render(cam, os.path.join(out_dir, f"{v}.jpg"))
        print("rendered", v)


def main() -> None:
    """blender -b --factory-startup --python-exit-code 1 -P art/blender/quarters_room.py -- [--preview <dir>] [--views entry,desk,...] [--samples N] (a quick look at the cabin alone)"""
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    B3.load_label_atlas()
    B3.load_decor_atlas()
    obj = build_room()
    st = A.stats(obj)
    print("QUARTERS_ROOM", st["tris"], "tris", len(st["materials"]), "slots", st["materials"])
    if "--preview" in argv:
        views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else ["entry", "desk", "sofa"]
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
        preview(argv[argv.index("--preview") + 1], views, samples)


if __name__ == "__main__":
    main()
