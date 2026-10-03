"""ASN Aquila interior kit: corridors (v3, ARTE-PLANCIA-2) — procedural generator in the language of the bridge v3.

Usage:  blender -b --factory-startup --python-exit-code 1 -P art/blender/kit_corridor.py -- <output_dir> [--preview <dir>] [--views run,run_back,...] [--samples N] [--no-export]

Module frame (the layout frame: the one Unreal gets, bridge3_lib mirrors Y on the way out): X along the corridor (0..4 m), Y across (inner walls at +-1.6), Z up (floor 0,
ceiling 3.0). The hull side of the window module is -Y (as it always was in Unreal; the old v2 generator drew it on +Y and the FBX export flipped it).

What changed from v2 (same names, same sizes, same origins: the level scripts place these meshes by number): the walls are two-toned (a dark composite wainscot, ivory above the
rail), the department colour is a lit band under the chamfer, the ribs are portals with a lit inner line, the walkway grate sits over a lit trench, the handrails and the lines of
the floor are brass, the ceiling has a lit channel, the wall panels carry real things (a display with a page of the decor atlas, louvres, an access hatch with its placard, vertical
light slits), the bulkhead is a heavy door frame with hazard stripes and status bars. All of it is Nanite-friendly hard surface on the bridge v3's shared materials.

Shells (structure only; wall panels are separate meshes placed by the level layout, for variety):
  SM_COR_Shell_4m          straight corridor: shell, portal ribs, floor plates, service trench under a walkway grate, chamfer pipe runs, ceiling panels + light channel,
                           accent band, skirting guide lights, handrails
  SM_COR_ShellWindow_4m    same with a 3 m panoramic window on -Y (mullion on the middle rib); `shell(name, window=True, door=(x0, w, h))` also cuts a door in the +Y wall
  SM_COR_WindowGlass       two glass panes for the window shell
  SM_COR_Bulkhead          watertight bulkhead (0.5 m) with 1.4 x 2.3 m door opening, frame, sill, hazard stripes, status bars, placards
  SM_COR_DoorLeaf          sliding door leaf (half door; use mirrored for the other half), occupying y -0.7..0
  SM_COR_EndCap            end wall
Wall panels (modelled for the -Y wall: back face on y=0, front towards +Y; X 0..1.72):
  SM_COR_PanelLow_Plain / _Vent / _Access      1.72 x 1.06 m (z 0.22..1.28 on the wall)
  SM_COR_PanelUp_Plain / _Screen / _Vent       1.72 x 1.10 m (z 1.32..2.42)
  SM_COR_PanelLowShort_Plain                   1.72 x 0.62 m (under the window, z 0.22..0.84)
The helpers inner_profile, offset_convex, u_rib, box_rot_x, chamfer_point and the constants are the v2's, unchanged: ship_rooms_bridge.corridor_door builds on them.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as B3  # noqa: E402
from bridge3_lib import FB, Parts, Rx, lerp  # noqa: E402

W, H, C, T = 3.2, 3.0, 0.5, 0.2      # inner width, height, top chamfer, shell thickness
L = 4.0                               # module length
HW = W / 2
BAYS = ((0.14, 1.86), (2.14, 3.86))   # wall panel bays between ribs
PANEL_W = 1.72
LOW_Z = (0.22, 1.28)
UP_Z = (1.32, 2.42)
TRENCH_HW, TRENCH_D = 0.55, 0.16      # service trench half width and depth
WIN_X, WIN_Z = (0.5, 3.5), (0.9, 2.4)

STRUCT, TRIM, RUBBER, DGLASS = B3.STRUCT, B3.TRIM, B3.RUBBER, B3.DGLASS
COMPOSITE, IVORY, DECK, BRASS = B3.COMPOSITE, B3.IVORY, B3.DECK, B3.BRASS
LAMP, LAMP_DIM, LAMP_HOT = B3.LAMP, B3.LAMP_DIM, B3.LAMP_HOT
GRATE, GLASS = A.MAT_GRATE, A.MAT_GLASS
NAVY = "MI_BRG3_Navy"                 # navy paint: the wainscot of the command deck
RAIL_Z = 1.02                         # the handrail's height


# ============================================================================================================ the v2 helpers (kept as they were)
def inner_profile(inset: float = 0.0) -> list[tuple[float, float]]:
    w2, h, c = HW - inset, H - inset, C
    z0 = inset if inset > 0 else 0.0
    return [(-w2, z0), (w2, z0), (w2, h - c), (w2 - c, h), (-w2 + c, h), (-w2, h - c)]


def offset_convex(poly, d):
    n = len(poly)
    lines = []
    for i in range(n):
        p0, p1 = Vector(poly[i]), Vector(poly[(i + 1) % n])
        e = (p1 - p0).normalized()
        lines.append((p0 + Vector((e.y, -e.x)) * d, e))
    out = []
    for i in range(n):
        (a, da), (b, db) = lines[i - 1], lines[i]
        det = da.x * (-db.y) - da.y * (-db.x)
        t = ((b.x - a.x) * (-db.y) - (b.y - a.y) * (-db.x)) / det
        p = a + da * t
        out.append((p.x, p.y))
    return out


def u_rib(b: A.Builder, x0: float, x1: float, depth: float = 0.08) -> None:
    """Structural rib following walls, chamfers and ceiling; open at the floor (nothing to trip on). (v2: the door module of ship_rooms_bridge uses it.)"""
    outer = inner_profile()                 # corridor inner surface
    ins = offset_convex(outer, -depth)      # inset towards the corridor axis
    poly = [(HW, 0.0), outer[2], outer[3], outer[4], outer[5], (-HW, 0.0),
            (-HW + depth, 0.0), ins[5], ins[4], ins[3], ins[2], (HW - depth, 0.0)]
    b.prism(poly, x0, x1, A.MAT_STRUCTURE)


def box_rot_x(b: A.Builder, center, size, angle_deg: float, mat: str) -> None:
    """Box rotated about the X axis (for parts following the 45-degree chamfers). (v2, Blender's frame.)"""
    import bmesh
    m = Matrix.Translation(center) @ Matrix.Rotation(math.radians(angle_deg), 4, "X") @ Matrix.Diagonal((*size, 1.0))
    geom = bmesh.ops.create_cube(b.bm, size=1.0, matrix=m)
    b._assign(geom["verts"], mat)


def chamfer_point(side: int, t: float, off: float):
    """Point on the chamfer (t=0 at the wall top, t=1 at the ceiling), pushed `off` towards the corridor."""
    y = side * (HW - C * t)
    z = (H - C) + C * t
    n = Vector((-side, -1.0)).normalized()
    return y + n.x * off, z + n.y * off


# ================================================================================================================================ small helpers
def new_parts() -> Parts:
    b = Parts(bevel=0.007, fine_bevel=0.003)
    b.bevel_segments = 1
    return b


def finish(b: Parts, name: str):
    return b.build(name, uv_meter=1.0, small_uv_meter=0.25)


def hex_head(em: FB, x: float, y: float, z: float, r: float, facing, up=(0, 0, 1), mat: str = TRIM) -> None:
    """A flat hexagon (a screw head) of circumradius r on a surface whose normal is `facing`."""
    f = Vector(facing).normalized()
    u = Vector(up) - f * Vector(up).dot(f)
    u = u.normalized() if u.length > 1e-6 else Vector((1, 0, 0))
    r_ = f.cross(u)
    c = Vector((x, y, z))
    em.face([tuple(c + (r_ * math.cos(math.radians(60 * k)) + u * math.sin(math.radians(60 * k))) * r) for k in range(6)], mat, tuple(f))


def inward(a, b_):
    """The unit normal (y, z) of the segment a -> b_ in the profile plane that points to the middle of the corridor."""
    dy, dz = b_[0] - a[0], b_[1] - a[1]
    n = Vector((dz, -dy))
    n.normalize()
    mid = Vector(((a[0] + b_[0]) / 2, (a[1] + b_[1]) / 2))
    if n.dot(Vector((0.0, 1.4)) - mid) < 0:
        n = -n
    return n


# ========================================================================================================================== the module
def rib_v3(b: Parts, x0: float, x1: float, depth: float = 0.08, lit: bool = True) -> None:
    """A structural portal rib: the v2's U in gunmetal with a lit line along its inner face (centred on the rib; a half rib at the end of the module gives half of the line,
    two modules together one whole line), a brass line on the edge where it meets the wall panels."""
    fb, em = b.body, b.emit
    outer = inner_profile()
    ins = offset_convex(outer, -depth)
    poly = [(HW, 0.0), outer[2], outer[3], outer[4], outer[5], (-HW, 0.0), (-HW + depth, 0.0), ins[5], ins[4], ins[3], ins[2], (HW - depth, 0.0)]
    fb.extrude_x(poly, x0, x1, STRUCT)
    if not lit:
        return
    xa, xb = (x0 + x1) / 2 - 0.012, (x0 + x1) / 2 + 0.012
    xa, xb = max(xa, 0.0), min(xb, L)
    path = [(HW - depth, 0.0), ins[2], ins[3], ins[4], ins[5], (-HW + depth, 0.0)]
    for p0, p1 in zip(path[:-1], path[1:]):
        n = inward(p0, p1)
        em.lamp_face([(xa, p0[0] + n.x * 0.0008, p0[1] + n.y * 0.0008), (xb, p0[0] + n.x * 0.0008, p0[1] + n.y * 0.0008),
                      (xb, p1[0] + n.x * 0.0008, p1[1] + n.y * 0.0008), (xa, p1[0] + n.x * 0.0008, p1[1] + n.y * 0.0008)], "white_warm", (0, n.x, n.y), LAMP_DIM)


def shell_core(b: Parts, window: bool, door) -> None:
    """The shell: one prism per profile edge (the mitred offset profiles tile exactly), no booleans. Edge 0 (floor) is split around the service trench; the -Y wall (edge 5)
    around the window; with `door` = (x0, width, height) the +Y wall (edge 1) has a door opening."""
    fb = b.body
    inner = inner_profile()
    outer = offset_convex(inner, T)
    n = len(inner)
    for i in range(1, n):
        j = (i + 1) % n
        quad = [inner[i], outer[i], outer[j], inner[j]]
        if window and i == 5:
            (yi, zi_t), (yo, zo_t) = inner[5], outer[5]
            (_, zi_b), (_, zo_b) = inner[0], outer[0]
            x0, x1 = WIN_X
            z0, z1 = WIN_Z
            fb.extrude_x(quad, 0.0, x0, COMPOSITE)
            fb.extrude_x(quad, x1, L, COMPOSITE)
            fb.extrude_x([(yi, zi_b), (yo, zo_b), (yo, z0), (yi, z0)], x0, x1, COMPOSITE)         # below the window
            fb.extrude_x([(yi, z1), (yo, z1), (yo, zo_t), (yi, zi_t)], x0, x1, COMPOSITE)         # above the window
        elif door and i == 1:
            dx0, dw, dh = door
            (yi, zi_b), (yo, zo_b) = inner[1], outer[1]
            (_, zi_t), (_, zo_t) = inner[2], outer[2]
            fb.extrude_x(quad, 0.0, dx0, COMPOSITE)
            fb.extrude_x(quad, dx0 + dw, L, COMPOSITE)
            fb.extrude_x([(yi, dh), (yo, dh), (yo, zo_t), (yi, zi_t)], dx0, dx0 + dw, COMPOSITE)  # over the door
        else:
            fb.extrude_x(quad, 0.0, L, COMPOSITE)
    (yl, _), (yr, _) = inner[0], inner[1]
    (yol, zo), (yor, _) = outer[0], outer[1]
    fb.extrude_x([(yol, zo), (-TRENCH_HW, zo), (-TRENCH_HW, 0.0), (yl, 0.0)], 0.0, L, STRUCT)
    fb.extrude_x([(TRENCH_HW, zo), (yor, zo), (yr, 0.0), (TRENCH_HW, 0.0)], 0.0, L, STRUCT)
    fb.extrude_x([(-TRENCH_HW, zo), (TRENCH_HW, zo), (TRENCH_HW, -TRENCH_D), (-TRENCH_HW, -TRENCH_D)], 0.0, L, STRUCT)


def floor_and_trench(b: Parts) -> None:
    """Non-skid plates either side of the walkway grate with a brass line each, the grate over the service trench (a lit strip each side of it, a lit trench floor under it:
    it shows through the perforations), the pipes, cables and brackets in the trench."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    for (x0, x1) in ((0.02, 1.98), (2.02, 3.98)):
        for s in (1, -1):
            fb.box((x0, s * (TRENCH_HW + 0.03), 0.0), (x1, s * (HW - 0.05), 0.012), DECK)
            em.box((x0 + 0.01, s * 1.047, 0.0118), (x1 - 0.01, s * 1.053, 0.0127), BRASS)
        fb.box((x0, -TRENCH_HW + 0.012, -0.008), (x1, TRENCH_HW - 0.012, 0.012), GRATE)
    for s in (1, -1):
        fb.box((0.0, s * TRENCH_HW - s * 0.012, -0.03), (L, s * (TRENCH_HW + 0.03), 0.014), STRUCT)                # the grate's edge frames and ledges
        em.lamp_box((0.02, s * (TRENCH_HW - 0.0095), 0.0139), (L - 0.02, s * (TRENCH_HW - 0.0045), 0.0148), "cool_dim", LAMP_DIM)
        em.lamp_box((0.05, s * 0.465, -TRENCH_D + 0.0015), (L - 0.05, s * 0.475, -TRENCH_D + 0.0030), "cyan_dim", LAMP_DIM)     # the trench's lit floor
    pipes = ((-0.30, -0.085, 0.052), (-0.08, -0.105, 0.036), (0.12, -0.11, 0.03))
    for (y, z, r) in pipes:
        fine.cyl((0.0, y, z), (L, y, z), r, TRIM, seg=14)
    for k in range(6):
        y = 0.30 + 0.028 * (k % 3)
        z = -0.135 + 0.025 * (k // 3)
        soft.cyl((0.0, y, z), (L, y, z), 0.012, RUBBER, seg=8)
    for xb in (0.5, 1.5, 2.5, 3.5):
        fb.box((xb - 0.02, -0.45, -TRENCH_D), (xb + 0.02, 0.45, -0.14), STRUCT)
        for (y, z, r) in pipes:
            fine.box((xb - 0.025, y - r - 0.01, -0.145), (xb + 0.025, y + r + 0.01, z - r * 0.4), STRUCT)
            if r > 0.04:
                em.cyl((xb - 0.027, y, z), (xb + 0.027, y, z), r + 0.0012, BRASS, seg=12)


def skirting_and_rails(b: Parts, window: bool, door) -> None:
    """Skirting with guide lights on both walls, the brass handrails (not under the window, not in front of the door's opening), the accent band under the chamfers."""
    fb, fine, em = b.body, b.fine, b.emit
    xa = xb_ = None
    if door:
        xa, xb_ = door[0] - 0.07, door[0] + door[1] + 0.07
    for s in (1, -1):
        runs = [(0.0, L)]
        if door and s == 1:
            runs = [(0.0, xa), (xb_, L)]
        for (r0, r1) in runs:
            fb.box((r0, s * (HW - 0.04), 0.0), (r1, s * HW, 0.18), STRUCT)
            em.box((r0, s * (HW - 0.0415), 0.176), (r1, s * (HW - 0.0395), 0.182), BRASS)
        for k in range(8):
            xc = 0.25 + 0.5 * k
            if door and s == 1 and xa - 0.05 < xc < xb_ + 0.05:
                continue
            em.lamp_box((xc - 0.06, s * (HW - 0.0445), 0.075), (xc + 0.06, s * (HW - 0.0395), 0.087), "guide", LAMP_DIM)
    for s in (1, -1):                                                                              # the department band under the chamfer: lit, with a brass line under it
        for (x0, x1) in BAYS:
            if window and s == -1 and x0 < WIN_X[1] + 0.06 and x1 > WIN_X[0] - 0.06:
                continue
            if door and s == 1 and x0 < xb_ and x1 > xa:
                continue
            em.lamp_box((x0 - 0.02, s * (HW - 0.0125), 2.447), (x1 + 0.02, s * HW, 2.471), "command_dim", LAMP_DIM)
            em.box((x0 - 0.02, s * (HW - 0.0185), 2.436), (x1 + 0.02, s * HW, 2.446), BRASS)
    for s in (1, -1):                                                                              # handrails
        if window and s == -1:
            continue
        y = s * (HW - 0.075)
        r0 = xb_ + 0.1 if (door and s == 1) else 0.0
        em.cyl((r0, y, RAIL_Z), (L, y, RAIL_Z), 0.021, BRASS, seg=12)
        for xb in (0.5, 1.5, 2.5, 3.5):
            if xb < r0:
                continue
            fine.box((xb - 0.02, s * (HW - 0.06), RAIL_Z - 0.02), (xb + 0.02, s * HW, RAIL_Z + 0.02), STRUCT)


def chamfers_and_ceiling(b: Parts) -> None:
    """Two pipe runs and a cable tray on each chamfer with their brackets (a brass band at each), and the ceiling: two dark panels a bay either side of the light channel, a gunmetal
    housing with a lit diffuser, the channel's brass edge lines."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    for s in (1, -1):
        for (t, off, r) in ((0.28, 0.075, 0.042), (0.58, 0.065, 0.03)):
            y, z = chamfer_point(s, t, off)
            fine.cyl((0.0, y, z), (L, y, z), r, TRIM, seg=14)
            for xb in (0.5, 1.5, 2.5, 3.5):
                yb, zb = chamfer_point(s, t, off * 0.5)
                fine.cbox((xb, yb, zb), (0.035, r * 2.4, off), STRUCT, Rx(-45.0 * s))
                em.cyl((xb - 0.0225, y, z), (xb + 0.0225, y, z), r + 0.0012, BRASS, seg=12)
        yt, zt = chamfer_point(s, 0.86, 0.03)
        fine.cbox((L / 2, yt, zt), (L, 0.2, 0.04), STRUCT, Rx(-45.0 * s))
        for k in range(4):
            yk, zk = chamfer_point(s, 0.80 + 0.04 * k, 0.065)
            soft.cyl((0.0, yk, zk), (L, yk, zk), 0.011, RUBBER, seg=8)
    for (x0, x1) in ((0.12, 1.88), (2.12, 3.88)):
        for yc in (-0.62, 0.62):
            fb.box((x0, yc - 0.475, H - 0.015), (x1, yc + 0.475, H), COMPOSITE)
            for (xa, xb_, ya, yb) in ((x0, x1, yc - 0.475, yc - 0.445), (x0, x1, yc + 0.445, yc + 0.475), (x0, x0 + 0.03, yc - 0.475, yc + 0.475), (x1 - 0.03, x1, yc - 0.475, yc + 0.475)):
                fine.box((xa, ya, H - 0.0185), (xb_, yb, H - 0.015), IVORY)                      # the frame of the panel
            gx0, gx1 = lerp(x0, x1, 0.5) - 0.28, lerp(x0, x1, 0.5) + 0.28                       # a vent grille: slats over a dark plenum
            fine.box((gx0, yc - 0.13, H - 0.0175), (gx1, yc + 0.13, H - 0.015), RUBBER)
            for k in range(7):
                yk = yc - 0.11 + k * 0.0367
                fine.box((gx0 + 0.01, yk - 0.004, H - 0.0205), (gx1 - 0.01, yk + 0.004, H - 0.0175), STRUCT)
        fb.box((x0, -0.11, H - 0.06), (x1, 0.11, H), STRUCT)
        em.lamp_box((x0 + 0.02, -0.07, H - 0.0655), (x1 - 0.02, 0.07, H - 0.060), "white_warm", LAMP_HOT)
        for s in (-1, 1):
            em.box((x0, s * 0.112, H - 0.058), (x1, s * 0.116, H - 0.052), BRASS)


def window_frame(b: Parts) -> None:
    """The window on -Y: a gunmetal frame (head, sill with a brass top, jambs), the rubber seals round the glass, a mullion through the wall thickness on the middle rib."""
    fb, fine, em = b.body, b.fine, b.emit
    x0, x1 = WIN_X
    z0, z1 = WIN_Z
    fb.box((L / 2 - 0.1, -HW - T, z0), (L / 2 + 0.1, -HW, z1), STRUCT)                                             # the mullion
    fb.box((x0 - 0.06, -HW, z1), (x1 + 0.06, -HW + 0.03, z1 + 0.06), STRUCT)                                       # head
    fb.box((x0 - 0.06, -HW - 0.04, z0 - 0.06), (x1 + 0.06, -HW + 0.06, z0), STRUCT)                                # sill
    fb.box((x0 - 0.06, -HW, z0), (x0, -HW + 0.03, z1), STRUCT)
    fb.box((x1, -HW, z0), (x1 + 0.06, -HW + 0.03, z1), STRUCT)
    em.box((x0 - 0.06, -HW + 0.0605, z0 - 0.0015), (x1 + 0.06, -HW + 0.0645, z0 + 0.0005), BRASS)                   # brass lip of the sill
    em.box((x0 - 0.0015, -HW + 0.030, z0), (x0 + 0.0015, -HW + 0.0335, z1), BRASS)
    em.box((x1 - 0.0015, -HW + 0.030, z0), (x1 + 0.0015, -HW + 0.0335, z1), BRASS)
    em.box((x0, -HW + 0.030, z1 - 0.0015), (x1, -HW + 0.0335, z1 + 0.0005), BRASS)
    for (a0, a1) in ((x0, L / 2 - 0.1), (L / 2 + 0.1, x1)):
        fine.box((a0, -HW - 0.12, z0), (a1, -HW - 0.08, z0 + 0.02), RUBBER)
        fine.box((a0, -HW - 0.12, z1 - 0.02), (a1, -HW - 0.08, z1), RUBBER)


def door_frame_v3(b: Parts, door) -> None:
    """The frame of a door in the +Y wall (v2's trim frame, ship_rooms_bridge.corridor_door): jambs 7 cm wide and a head, 3 cm proud of the finished wall and through the wall's
    thickness, steel with a brass line on the edge of the opening, a brass sill, a lit status bar either side."""
    fb, em = b.body, b.emit
    x0d, dw, dh = door
    x1d = x0d + dw
    yin, yout = HW - 0.03, HW + T
    for (xs0, xs1) in ((x0d - 0.07, x0d), (x1d, x1d + 0.07)):
        fb.box((xs0, yin, 0.0), (xs1, yout, dh + 0.07), STRUCT)
    fb.box((x0d - 0.07, yin, dh), (x1d + 0.07, yout, dh + 0.07), STRUCT)
    fb.box((x0d, yin + 0.01, 0.0), (x1d, yout, 0.014), STRUCT)
    em.box((x0d, yin + 0.012, 0.0138), (x1d, yin + 0.026, 0.0152), BRASS)
    for (xa, xb_, za, zb) in ((x0d - 0.0015, x0d + 0.0015, 0.0, dh), (x1d - 0.0015, x1d + 0.0015, 0.0, dh), (x0d, x1d, dh - 0.0015, dh + 0.0015)):
        em.box((xa, yin - 0.0010, za), (xb_, yin + 0.0005, zb), BRASS)
    for xs in (x0d - 0.11, x1d + 0.07):
        em.lamp_box((xs, HW - 0.02, 0.35), (xs + 0.04, HW - 0.0185, 1.9), "command_dim", LAMP_DIM)


def shell(name: str, window: bool = False, door=None):
    """A 4 m module. `door` = (x0, width, height): a door opening in the +Y wall (the module of the ready room)."""
    b = new_parts()
    shell_core(b, window, door)
    for (x0, x1) in ((0.0, 0.1), (L / 2 - 0.1, L / 2 + 0.1), (L - 0.1, L)):
        rib_v3(b, x0, x1)
    floor_and_trench(b)
    skirting_and_rails(b, window, door)
    chamfers_and_ceiling(b)
    if window:
        window_frame(b)
    if door:
        door_frame_v3(b, door)
    return finish(b, name)


def window_glass(name: str):
    b = new_parts()
    for (x0, x1) in ((WIN_X[0], L / 2 - 0.1), (L / 2 + 0.1, WIN_X[1])):
        b.body.box((x0, -HW - 0.105, WIN_Z[0] + 0.02), (x1, -HW - 0.095, WIN_Z[1] - 0.02), GLASS)
    b.bevel = 0.0
    return finish(b, name)


# ============================================================================================================================ bulkhead, door, cap
def bulkhead_face(b: Parts, x: float, sgn: int) -> None:
    """One face of the bulkhead (x = its plane; sgn = -1 for the face that looks along -x, +1 for the one that looks along +x): the steel frame's hazard stripes, the ivory panels
    with their brass borders and placards, the light bar over the door, the status bars beside it."""
    fb, fine, em = b.body, b.fine, b.emit
    f = (sgn, 0, 0)
    xs = x + sgn * 0.0125                                                                       # the surface of the ivory panels
    for s in (-1, 1):                                                                           # hazard stripes up the frame's jambs: amber lit and dark rubber alternating
        for k in range(12):
            z = 0.10 + k * 0.18
            xa, xb = (x + sgn * 0.030, x + sgn * 0.0318)
            lo, hi = min(xa, xb), max(xa, xb)
            if k % 2 == 0:
                em.lamp_box((lo, s * 0.76 - 0.036, z), (hi, s * 0.76 + 0.036, z + 0.09), "amber_dim", LAMP_DIM)
            else:
                fine.box((lo, s * 0.76 - 0.036, z), (hi, s * 0.76 + 0.036, z + 0.09), RUBBER)
    for (cy, cz, sy, sz) in ((-1.22, 1.3, 0.62, 2.1), (1.22, 1.3, 0.62, 2.1), (0.0, 2.72, 1.9, 0.36)):
        lo, hi = (x - 0.012, x) if sgn < 0 else (x, x + 0.012)
        fb.box((lo, cy - sy / 2, cz - sz / 2), (hi, cy + sy / 2, cz + sz / 2), IVORY)
        for (ya, yb, za, zb) in ((cy - sy / 2, cy + sy / 2, cz - sz / 2, cz - sz / 2 + 0.004), (cy - sy / 2, cy + sy / 2, cz + sz / 2 - 0.004, cz + sz / 2),
                                 (cy - sy / 2, cy - sy / 2 + 0.004, cz - sz / 2, cz + sz / 2), (cy + sy / 2 - 0.004, cy + sy / 2, cz - sz / 2, cz + sz / 2)):
            em.box((min(xs, xs + sgn * 0.0012), ya, za), (max(xs, xs + sgn * 0.0012), yb, zb), BRASS)
    em.label((xs + sgn * 0.0004, -1.22, 1.62), 0.46, 0.115, f, "tag_23")                        # PRESSURE DOOR 1A-01
    em.label((xs + sgn * 0.0004, 1.22, 1.62), 0.46, 0.115, f, "tag_33")                         # COMPARTMENT SEAL
    em.label((xs + sgn * 0.0004, -1.22, 1.20), 0.21, 0.21, f, "icon_hv")
    em.label((xs + sgn * 0.0004, 1.22, 1.20), 0.21, 0.21, f, "icon_exit")
    em.label((xs + sgn * 0.0004, 0.0, 2.72), 0.52, 0.13, f, "tag_39")                           # BRIDGE ACCESS
    xl = x + sgn * 0.0006                                                                       # the light bar over the door and the status bars beside it
    em.lamp_box((min(xl, xl + sgn * 0.0014), -0.25, 2.465), (max(xl, xl + sgn * 0.0014), 0.25, 2.505), "white_cool", LAMP_DIM)
    for cy in (-0.9, 0.9):
        em.lamp_box((min(xl, xl + sgn * 0.0014), cy - 0.018, 0.2), (max(xl, xl + sgn * 0.0014), cy + 0.018, 1.9), "command_dim", LAMP_DIM)


def bulkhead(name: str):
    depth = 0.5
    b = new_parts()
    fb, em = b.body, b.emit
    outer = offset_convex(inner_profile(), T)
    # the plate round the opening (y -0.7..0.7, z 0..2.3): a jamb each side and the lintel, the outer profile cut by the opening's lines
    ywall = max(p[0] for p in outer)
    ytop = max(p[0] for p in outer if p[1] >= max(q[1] for q in outer) - 1e-6)
    zlo, zch, ztop = min(p[1] for p in outer), outer[2][1], max(p[1] for p in outer)
    for s in (-1, 1):
        fb.extrude_x([(s * 0.7, zlo), (s * ywall, zlo), (s * ywall, zch), (s * ytop, ztop), (s * 0.7, ztop)], 0.0, depth, COMPOSITE)
    fb.extrude_x([(-0.7, 2.3), (0.7, 2.3), (0.7, ztop), (-0.7, ztop)], 0.0, depth, COMPOSITE)
    # the frame: a steel surround standing 3 cm out of both faces, the sill with a brass line, the brass line on the opening's edge
    for (cy, cz, sy, sz) in ((0.0, 2.36, 1.64, 0.12), (-0.76, 1.15, 0.12, 2.42), (0.76, 1.15, 0.12, 2.42)):
        fb.box((-0.03, cy - sy / 2, cz - sz / 2), (depth + 0.03, cy + sy / 2, cz + sz / 2), STRUCT)
    fb.box((0.0, -0.7, 0.0), (depth, 0.7, 0.014), STRUCT)
    em.box((0.0, -0.7, 0.0138), (depth, 0.7, 0.0152), BRASS)
    bulkhead_face(b, 0.0, -1)
    bulkhead_face(b, depth, 1)
    return finish(b, name)


def door_leaf(name: str):
    """A sliding door leaf, 0.08 thick, y -0.7..0, 2.3 high: dark composite, a rubber seal on the meeting edge, a steel kick plate, a window in a steel frame, a lit department band,
    a brass line, a handle pad. (Placed by the level scripts, mirrored for the other half.)"""
    b = new_parts()
    fb, fine, em = b.body, b.fine, b.emit
    fb.box((-0.04, -0.70, 0.0), (0.04, 0.0, 2.3), NAVY)
    fb.box((-0.05, -0.04, 0.0), (0.05, 0.0, 2.3), RUBBER)
    fb.box((-0.05, -0.71, 0.02), (0.05, -0.70 + 0.01, 0.22), STRUCT)
    for (ya, yb, za, zb) in ((-0.53, -0.17, 1.35, 1.38), (-0.53, -0.17, 1.82, 1.85), (-0.53, -0.50, 1.35, 1.85), (-0.20, -0.17, 1.35, 1.85)):
        fb.box((-0.05, ya, za), (0.05, yb, zb), STRUCT)
    fine.box((-0.03, -0.50, 1.38), (0.03, -0.20, 1.82), DGLASS)
    fb.box((-0.05, -0.545, 0.90), (0.05, -0.495, 1.20), STRUCT)
    em.lamp_box((-0.0505, -0.60, 2.035), (0.0505, -0.10, 2.065), "command_dim", LAMP_DIM)
    em.box((-0.0408, -0.68, 2.20), (0.0408, -0.06, 2.206), BRASS)
    em.box((-0.0408, -0.68, 0.30), (0.0408, -0.06, 0.306), BRASS)
    return finish(b, name)


def end_cap(name: str):
    """The end wall: the outer profile 0.2 m deep, on its face (x < 0) two ivory panels with brass borders: a tall display of the decks' status and a board of placards, a lit band over them."""
    b = new_parts()
    fb, fine, em = b.body, b.fine, b.emit
    fb.extrude_x(offset_convex(inner_profile(), T), 0.0, 0.2, COMPOSITE)
    f = (-1, 0, 0)
    for (cy, cz, sy, sz) in ((-0.8, 1.2, 1.4, 2.0), (0.8, 1.2, 1.4, 2.0)):
        fb.box((-0.02, cy - sy / 2, cz - sz / 2), (0.0, cy + sy / 2, cz + sz / 2), IVORY)
        for (ya, yb, za, zb) in ((cy - sy / 2, cy + sy / 2, cz - sz / 2, cz - sz / 2 + 0.004), (cy - sy / 2, cy + sy / 2, cz + sz / 2 - 0.004, cz + sz / 2),
                                 (cy - sy / 2, cy - sy / 2 + 0.004, cz - sz / 2, cz + sz / 2), (cy + sy / 2 - 0.004, cy + sy / 2, cz - sz / 2, cz + sz / 2)):
            em.box((-0.0212, ya, za), (-0.0200, yb, zb), BRASS)
    fb.box((-0.034, -1.10, 0.52), (-0.020, -0.50, 1.88), STRUCT)                                  # the display's bezel
    fine.box((-0.0345, -1.075, 0.545), (-0.034, -0.525, 1.855), DGLASS)
    em.decor((-0.0350, -0.80, 1.20), 0.55, 1.10, f, "decks")
    for k, tag in enumerate(("tag_00", "tag_02", "tag_01", "tag_10")):                          # the placards of the right panel
        em.label((-0.0212, 0.80, 1.78 - k * 0.30), 0.60, 0.15, f, tag)
    xe = -0.02 - 0.05                                                                              # a fire extinguisher in two straps, a first-aid box
    fb.cyl((xe, 0.40, 0.24), (xe, 0.40, 0.64), 0.05, STRUCT, seg=16)
    fb.cyl((xe, 0.40, 0.64), (xe, 0.40, 0.69), 0.028, STRUCT, seg=12)
    em.cyl((xe, 0.40, 0.69), (xe, 0.40, 0.72), 0.022, BRASS, seg=12)
    em.lamp_cyl((xe, 0.40, 0.44), (xe, 0.40, 0.48), 0.0515, "red_dim", LAMP_DIM, seg=16)
    for zc in (0.33, 0.56):
        fb.box((xe - 0.055, 0.40 - 0.058, zc - 0.012), (-0.02, 0.40 + 0.058, zc + 0.012), STRUCT)
    fb.box((-0.12, 0.88, 0.28), (-0.02, 1.28, 0.58), IVORY)
    em.label((-0.1206, 1.08, 0.43), 0.17, 0.17, f, "icon_aid")
    em.lamp_box((-0.0212, -1.2, 2.40), (-0.0200, 1.2, 2.44), "command_dim", LAMP_DIM)
    em.box((-0.0212, -1.2, 2.446), (-0.0200, 1.2, 2.452), BRASS)
    return finish(b, name)


# ============================================================================================================================ wall panels
def _slab(b: Parts, h: float, mat: str, relief: bool = True, border: bool = True) -> None:
    """Panel slab (1.5 cm) + a 4 mm raised field inset 6 cm, a brass line round the field."""
    fb, em = b.body, b.emit
    fb.box((0.0, 0.0, 0.0), (PANEL_W, 0.015, h), mat)
    if relief:
        fb.box((0.06, 0.015, 0.06), (PANEL_W - 0.06, 0.019, h - 0.06), mat)
    if border:
        w = 0.0032
        for (xa, xb, za, zb) in ((0.06, PANEL_W - 0.06, 0.06, 0.06 + w), (0.06, PANEL_W - 0.06, h - 0.06 - w, h - 0.06), (0.06, 0.06 + w, 0.06, h - 0.06), (PANEL_W - 0.06 - w, PANEL_W - 0.06, 0.06, h - 0.06)):
            em.box((xa, 0.0189, za), (xb, 0.0200, zb), BRASS)


def _louvres(b: Parts, x0: float, z0: float, vw: float, vh: float, n: int = 8) -> None:
    """A louvred vent in front of a dark plenum, inside a steel bezel with a brass inner line."""
    fine, em = b.fine, b.emit
    fine.box((x0, 0.002, z0), (x0 + vw, 0.016, z0 + vh), RUBBER)                                    # the dark plenum
    for k in range(n):
        zc = z0 + (k + 0.5) * vh / n
        fine.cbox((x0 + vw / 2, 0.012, zc), (vw - 0.02, 0.004, vh / n * 1.25), STRUCT, Rx(35.0))
    for (xa, xb, za, zb) in ((x0 - 0.03, x0 + vw + 0.03, z0 - 0.03, z0), (x0 - 0.03, x0 + vw + 0.03, z0 + vh, z0 + vh + 0.03), (x0 - 0.03, x0, z0, z0 + vh), (x0 + vw, x0 + vw + 0.03, z0, z0 + vh)):
        fine.box((xa, 0.0150, za), (xb, 0.022, zb), STRUCT)
    em.box((x0 - 0.0015, 0.0215, z0 - 0.0015), (x0 + vw + 0.0015, 0.0222, z0 + 0.0015), BRASS)
    em.box((x0 - 0.0015, 0.0215, z0 + vh - 0.0015), (x0 + vw + 0.0015, 0.0222, z0 + vh + 0.0015), BRASS)


def panel_plain(name: str, h: float):
    """A dark composite wainscot panel: the field, vertical seams, a brass border, a small silkscreen code."""
    b = new_parts()
    fine, em = b.fine, b.emit
    _slab(b, h, NAVY)
    for k in range(1, 8):
        xk = 0.06 + (PANEL_W - 0.12) * k / 8
        fine.box((xk - 0.0015, 0.019, 0.075), (xk + 0.0015, 0.0204, h - 0.075), STRUCT)
    em.label((0.17, 0.0201, 0.115), 0.10, 0.025, (0, 1, 0), "small_03")
    return finish(b, name)


def panel_vent(name: str, h: float, zc: float, light: bool = False):
    """Louvred vent: an opening in the slab (the slab is built round it), slats, a dark plenum behind; a placard under it."""
    b = new_parts()
    fb, em = b.body, b.emit
    mat = IVORY if light else NAVY
    vw, vh = 1.0, 0.34
    x0, z0 = (PANEL_W - vw) / 2, zc - vh / 2
    fb.box((0.0, 0.0, 0.0), (x0, 0.015, h), mat)
    fb.box((x0 + vw, 0.0, 0.0), (PANEL_W, 0.015, h), mat)
    fb.box((x0, 0.0, 0.0), (x0 + vw, 0.015, z0), mat)
    fb.box((x0, 0.0, z0 + vh), (x0 + vw, 0.015, h), mat)
    _louvres(b, x0, z0, vw, vh)
    if light:
        em.label((x0 + 0.10, 0.0160, z0 - 0.07), 0.14, 0.035, (0, 1, 0), "small_09")                                          # AIR
        em.label((x0 + vw - 0.10, 0.0160, z0 - 0.07), 0.14, 0.035, (0, 1, 0), "small_02")                                     # 1A-05
    else:
        em.label((PANEL_W / 2, 0.0160, z0 + vh + 0.09), 0.30, 0.075, (0, 1, 0), "tag_07")                                    # VENT 1A-04
    return finish(b, name)


def panel_access(name: str, h: float):
    """Access hatch in a dark panel: a raised ivory hatch inside a dark gap, two brass pull bars, six fasteners, a status lamp, the placard under it."""
    b = new_parts()
    fb, fine, em = b.body, b.fine, b.emit
    _slab(b, h, NAVY, relief=True, border=True)
    hx0, hx1, hz0, hz1 = 0.36, PANEL_W - 0.36, 0.20, h - 0.12
    fb.box((hx0 - 0.012, 0.019, hz0 - 0.012), (hx1 + 0.012, 0.0215, hz1 + 0.012), RUBBER)             # the gap
    fb.box((hx0, 0.0215, hz0), (hx1, 0.0245, hz1), IVORY)                                           # the hatch
    for xc in (hx0 + 0.16, hx1 - 0.16):
        fine.box((xc - 0.07, 0.0245, hz1 - 0.16), (xc + 0.07, 0.0285, hz1 - 0.10), STRUCT)
        em.cyl((xc - 0.05, 0.0310, hz1 - 0.13), (xc + 0.05, 0.0310, hz1 - 0.13), 0.0085, BRASS, seg=10)
    for xc in (hx0 + 0.05, (hx0 + hx1) / 2, hx1 - 0.05):
        for zc in (hz0 + 0.05, hz1 - 0.05):
            hex_head(em, xc, 0.0247, zc, 0.0075, (0, 1, 0), up=(0, 0, 1))
    em.lamp_cyl((hx1 - 0.06, 0.0245, hz0 + 0.07), (hx1 - 0.06, 0.0262, hz0 + 0.07), 0.0075, "green_dim", LAMP_DIM, seg=10)
    em.label((PANEL_W / 2, 0.0201, 0.095), 0.46, 0.115, (0, 1, 0), "tag_11")                          # MAINTENANCE ACCESS 1A-12
    return finish(b, name)


def panel_light(name: str, h: float, with_screen: bool = False):
    """An ivory panel of the upper wall: the field with a brass line, two vertical light slits (dark glass with a lit core), a brass cap line; with a display instead of the slits."""
    b = new_parts()
    fb, fine, em = b.body, b.fine, b.emit
    _slab(b, h, IVORY, relief=True, border=True)
    for (xf, zf) in ((0.09, 0.09), (PANEL_W - 0.09, 0.09), (0.09, h - 0.09), (PANEL_W - 0.09, h - 0.09), (PANEL_W / 2, 0.09), (PANEL_W / 2, h - 0.09)):
        hex_head(em, xf, 0.0191, zf, 0.0055, (0, 1, 0), up=(0, 0, 1))
    if with_screen:
        sw, sh = 0.90, 0.5625
        zc = 0.14 + 0.28 + 0.03
        fb.box((PANEL_W / 2 - sw / 2 - 0.035, 0.019, zc - sh / 2 - 0.035), (PANEL_W / 2 + sw / 2 + 0.035, 0.026, zc + sh / 2 + 0.035), STRUCT)
        fine.box((PANEL_W / 2 - sw / 2, 0.026, zc - sh / 2), (PANEL_W / 2 + sw / 2, 0.0268, zc + sh / 2), DGLASS)
        em.decor((PANEL_W / 2, 0.0270, zc), sw, sh, (0, 1, 0), "ship")
        em.box((PANEL_W / 2 - sw / 2 - 0.0014, 0.0255, zc - sh / 2 - 0.035), (PANEL_W / 2 + sw / 2 + 0.0014, 0.0262, zc - sh / 2 - 0.0325), BRASS)
        em.lamp_cyl((PANEL_W / 2 + sw / 2 - 0.05, 0.026, zc - sh / 2 - 0.0175), (PANEL_W / 2 + sw / 2 - 0.05, 0.0275, zc - sh / 2 - 0.0175), 0.0055, "green_dim", LAMP_DIM, seg=10)
        em.label((PANEL_W / 2 - sw / 2 + 0.12, 0.0262, zc - sh / 2 - 0.0175), 0.17, 0.0425, (0, 1, 0), "small_06")
    else:
        for xc in (PANEL_W * 0.25, PANEL_W * 0.75):
            fine.box((xc - 0.022, 0.019, 0.16), (xc + 0.022, 0.0215, h - 0.16), DGLASS)
            em.lamp_box((xc - 0.012, 0.0215, 0.175), (xc + 0.012, 0.0222, h - 0.175), "white_cool", LAMP_DIM)
    return finish(b, name)


# ================================================================================================================================ main, preview
BUILDERS = [
    ("SM_COR_Shell_4m", lambda n: shell(n)),
    ("SM_COR_ShellWindow_4m", lambda n: shell(n, window=True)),
    ("SM_COR_WindowGlass", window_glass),
    ("SM_COR_Bulkhead", bulkhead),
    ("SM_COR_DoorLeaf", door_leaf),
    ("SM_COR_EndCap", end_cap),
    ("SM_COR_PanelLow_Plain", lambda n: panel_plain(n, LOW_Z[1] - LOW_Z[0])),
    ("SM_COR_PanelLow_Vent", lambda n: panel_vent(n, LOW_Z[1] - LOW_Z[0], 0.3)),
    ("SM_COR_PanelLow_Access", lambda n: panel_access(n, LOW_Z[1] - LOW_Z[0])),
    ("SM_COR_PanelUp_Plain", lambda n: panel_light(n, UP_Z[1] - UP_Z[0])),
    ("SM_COR_PanelUp_Screen", lambda n: panel_light(n, UP_Z[1] - UP_Z[0], with_screen=True)),
    ("SM_COR_PanelUp_Vent", lambda n: panel_vent(n, UP_Z[1] - UP_Z[0], 0.8, light=True)),
    ("SM_COR_PanelLowShort_Plain", lambda n: panel_plain(n, 0.62)),
]


VIEWS = {
    # name: (eye in the run's frame (x along the corridor, y across, z up), yaw, pitch, fov)
    "run": ((0.8, 0.0, 1.65), 0.0, -2.0, 82.0),
    "run_back": ((11.2, 0.0, 1.65), 180.0, -2.0, 82.0),
    "window": ((4.4, 1.0, 1.55), -62.0, -3.0, 78.0),
    "wall": ((6.0, -0.9, 1.6), 90.0, 0.0, 70.0),
    "wall_low": ((2.0, 0.9, 1.25), -90.0, -12.0, 70.0),
    "floor": ((1.6, 0.0, 1.7), 0.0, -48.0, 80.0),
    "ceiling": ((2.0, 0.0, 1.3), 0.0, 42.0, 82.0),
    "door": ((13.0, 0.0, 1.6), 0.0, -3.0, 76.0),
    "door_back": ((17.2, 0.5, 1.6), 180.0, -3.0, 76.0),
    "cap": ((3.0, 0.0, 1.6), 180.0, -3.0, 76.0),
    "doormod": ((5.0, -0.8, 1.5), 90.0, -2.0, 72.0),
}


def preview(out_dir: str, views: list[str], samples: int) -> None:
    """Assemble a 12 m run the way tools/ue_scripts/build_bridge_v3.py does (shells, panels picked at random with the same weights, the window module in the middle with its
    glass and short panels, the end cap), a bulkhead with its two leaves beyond it, light it like the level (a warm rect light per module) and render the views."""
    import bridge3_preview as PV
    A.clear_objects()
    objs = {name: build(name) for name, build in BUILDERS}
    objs["PV_ShellDoor"] = shell("PV_ShellDoor", window=True, door=(0.3, 1.4, 2.2))
    for o in objs.values():
        o.hide_render = True
        o.hide_viewport = True
    PV.make_materials({})
    PV.set_world((0.0, 0.0, 0.0), 0.0)
    PV.sky_dome(yaw_deg=60.0)                                                     # the star map outside the window
    PV.configure_render(int(os.environ.get("KC_W", "1600")), int(os.environ.get("KC_H", "900")), samples, exposure=float(os.environ.get("KC_EXPOSURE", "0.4")))

    def put(name: str, x: float, y: float, z: float, yaw: float, mirror: bool = False) -> None:
        o = bpy.data.objects.new(name + "_i", objs[name].data)
        bpy.context.scene.collection.objects.link(o)
        o.location = (x, -y, z)
        o.rotation_euler = (0.0, 0.0, math.radians(-yaw))
        if mirror:
            o.scale = (1.0, -1.0, 1.0)

    rng = random.Random(11)
    LOW = [("SM_COR_PanelLow_Plain", 0.6), ("SM_COR_PanelLow_Access", 0.2), ("SM_COR_PanelLow_Vent", 0.2)]
    UP = [("SM_COR_PanelUp_Plain", 0.55), ("SM_COR_PanelUp_Screen", 0.25), ("SM_COR_PanelUp_Vent", 0.2)]

    def pick(options):
        r, acc = rng.random(), 0.0
        for nm, w in options:
            acc += w
            if r <= acc:
                return nm
        return options[-1][0]

    for i, xm in enumerate((0.0, 4.0, 8.0)):
        win = i == 1
        put("PV_ShellDoor" if (win and os.environ.get("KC_DOORMODULE")) else "SM_COR_ShellWindow_4m" if win else "SM_COR_Shell_4m", xm, 0.0, 0.0, 0.0)
        if win:
            put("SM_COR_WindowGlass", xm, 0.0, 0.0, 0.0)
        for side in (-1, 1):
            for (b0, b1) in BAYS:
                items = [("SM_COR_PanelLowShort_Plain", 0.22)] if (win and side == -1) else [(pick(LOW), 0.22), (pick(UP), 1.32)]
                if win and side == 1 and os.environ.get("KC_DOORMODULE") and b0 < 1.9:                 # the door module: no panels over its opening
                    continue
                for name, z in items:
                    if side == -1:
                        put(name, xm + b0, -1.6, z, 0.0)
                    else:
                        put(name, xm + b1, 1.6, z, 180.0)
        ld = bpy.data.lights.new(f"Rect{i}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = 3.4, 0.14
        ld.energy = 3500 * 0.030 * (1.0 + 0.4 * math.log10(1 + 3.4 * 0.14)) * float(os.environ.get("KC_GAIN", "1.0"))
        ld.color = (1.0, 0.878, 0.78)
        ld.use_shadow = False
        lo = bpy.data.objects.new(f"Rect{i}", ld)
        bpy.context.scene.collection.objects.link(lo)
        lo.location = (xm + 2.0, 0.0, 2.9)
        lo.rotation_euler = (0.0, 0.0, 0.0)
    put("SM_COR_EndCap", 0.0, 0.0, 0.0, 180.0)
    put("SM_COR_Bulkhead", 12.0, 0.0, 0.0, 0.0)
    put("SM_COR_DoorLeaf", 12.25, 0.0, 0.0, 0.0)
    put("SM_COR_DoorLeaf", 12.25, 0.0, 0.0, 0.0, mirror=True)
    for k, xm in enumerate((12.5, 16.5)):                                   # beyond the bulkhead: the next modules, so the door's far side has a corridor behind it
        put("SM_COR_Shell_4m", xm, 0.0, 0.0, 0.0)
        for side in (-1, 1):
            for (b0, b1) in BAYS:
                for name, z in ((pick(LOW), 0.22), (pick(UP), 1.32)):
                    if side == -1:
                        put(name, xm + b0, -1.6, z, 0.0)
                    else:
                        put(name, xm + b1, 1.6, z, 180.0)
        ld = bpy.data.lights.new(f"RectB{k}", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = 3.4, 0.14
        ld.energy = 3500 * 0.030 * (1.0 + 0.4 * math.log10(1 + 3.4 * 0.14))
        ld.color = (1.0, 0.878, 0.78)
        ld.use_shadow = False
        lo = bpy.data.objects.new(f"RectB{k}", ld)
        bpy.context.scene.collection.objects.link(lo)
        lo.location = (xm + 2.0, 0.0, 2.9)
    put("SM_COR_EndCap", 20.5, 0.0, 0.0, 0.0)
    os.makedirs(out_dir, exist_ok=True)
    for v in views:
        eye, yaw, pitch, fov = VIEWS[v]
        cam = PV.add_camera(v, eye, yaw, pitch, fov)
        PV.render(cam, os.path.join(out_dir, f"{v}.jpg"))
        print("rendered", v)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv and not argv[0].startswith("--") else "art/export/kit_corridor"
    prev = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else ["run", "run_back", "window"]
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 40
    export = "--no-export" not in argv
    A.reset_scene()
    B3.load_label_atlas()
    B3.load_decor_atlas()
    report = []
    built = {}
    for name, build in BUILDERS:
        A.clear_objects()
        obj = build(name)
        if export:
            A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
        built[name] = obj
    if export:
        with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)
        print("KIT_OK", json.dumps(report))
    else:
        print("KIT_STATS", json.dumps([(r["name"], r["tris"]) for r in report]))
    if prev:
        preview(prev, views, samples)


if __name__ == "__main__":
    main()
