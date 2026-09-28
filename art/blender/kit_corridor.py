"""ASN Aquila interior kit: corridors (v2) — procedural generator.

Usage:  blender -b --factory-startup --python-exit-code 1 -P art/blender/kit_corridor.py -- <output_dir>

Module frame (Blender): X along the corridor (0..4 m), Y across (inner walls at +-1.6), Z up (floor 0, ceiling 3.0).
The FBX export flips Y, so in Unreal the window side (+Y here) becomes -Y.

Shells (structure only; wall panels are separate meshes placed by the level layout, for variety):
  SM_COR_Shell_4m          straight corridor: shell, U-ribs, floor plates, service trench under a walkway grate,
                           chamfer pipe runs, ceiling panels + light channel, accent strips, skirting guide lights
  SM_COR_ShellWindow_4m    same with a 3 m panoramic window on +Y (mullion on the middle rib)
  SM_COR_WindowGlass       two glass panes for the window shell
  SM_COR_Bulkhead          watertight bulkhead (0.5 m) with 1.4 x 2.3 m door opening, frame, sill, status lights
  SM_COR_DoorLeaf          sliding door leaf (half door; use mirrored for the other half)
  SM_COR_EndCap            end wall
Wall panels (modelled for the +Y wall: back face on y=0, front towards -Y; X 0..1.72):
  SM_COR_PanelLow_Plain / _Vent / _Access      1.72 x 1.06 m (z 0.22..1.28 on the wall)
  SM_COR_PanelUp_Plain / _Screen / _Vent       1.72 x 1.10 m (z 1.32..2.42)
  SM_COR_PanelLowShort_Plain                   1.72 x 0.62 m (under the window, z 0.22..0.84)
"""
from __future__ import annotations

import json
import math
import os
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

W, H, C, T = 3.2, 3.0, 0.5, 0.2      # inner width, height, top chamfer, shell thickness
L = 4.0                               # module length
HW = W / 2
BAYS = ((0.14, 1.86), (2.14, 3.86))   # wall panel bays between ribs
PANEL_W = 1.72
LOW_Z = (0.22, 1.28)
UP_Z = (1.32, 2.42)
TRENCH_HW, TRENCH_D = 0.55, 0.16      # service trench half width and depth
WIN_X, WIN_Z = (0.5, 3.5), (0.9, 2.4)


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


def ring_solid(b: A.Builder, inner, outer, x0: float, x1: float, mat: str) -> None:
    """Closed ring solid between two profiles, extruded along X."""
    bm = b.bm
    n = len(inner)
    vi0 = [bm.verts.new((x0, y, z)) for y, z in inner]
    vi1 = [bm.verts.new((x1, y, z)) for y, z in inner]
    vo0 = [bm.verts.new((x0, y, z)) for y, z in outer]
    vo1 = [bm.verts.new((x1, y, z)) for y, z in outer]
    idx = b.mi(mat)
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((vi0[i], vi1[i], vi1[j], vi0[j])))   # inner surface
        faces.append(bm.faces.new((vo0[i], vo0[j], vo1[j], vo1[i])))   # outer surface
        faces.append(bm.faces.new((vi0[i], vi0[j], vo0[j], vo0[i])))   # end x0
        faces.append(bm.faces.new((vi1[i], vo1[i], vo1[j], vi1[j])))   # end x1
    for f in faces:
        f.material_index = idx
    import bmesh
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def u_rib(b: A.Builder, x0: float, x1: float, depth: float = 0.08) -> None:
    """Structural rib following walls, chamfers and ceiling; open at the floor (nothing to trip on)."""
    outer = inner_profile()                 # corridor inner surface
    ins = offset_convex(outer, -depth)      # inset towards the corridor axis
    # U polygon: along the corridor surface from bottom-right up and around to bottom-left, back along the inset
    poly = [(HW, 0.0), outer[2], outer[3], outer[4], outer[5], (-HW, 0.0),
            (-HW + depth, 0.0), ins[5], ins[4], ins[3], ins[2], (HW - depth, 0.0)]
    b.prism(poly, x0, x1, A.MAT_STRUCTURE)


def box_rot_x(b: A.Builder, center, size, angle_deg: float, mat: str) -> None:
    """Box rotated about the X axis (for parts following the 45-degree chamfers)."""
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


def shell(name: str, window: bool = False):
    # 1) shell: one prism per profile edge (the mitred offset profiles tile exactly), no booleans.
    #    Edge 0 (floor) is split around the service trench; the +Y wall (edge 1) around the window.
    inner = inner_profile()
    outer = offset_convex(inner, T)
    sh = A.Builder()
    n = len(inner)
    for i in range(1, n):
        j = (i + 1) % n
        quad = [inner[i], outer[i], outer[j], inner[j]]
        if window and i == 1:
            (yi, zi0), (yo, zo0) = inner[1], outer[1]
            zi1, zo1 = inner[2][1], outer[2][1]
            x0, x1 = WIN_X
            z0, z1 = WIN_Z
            sh.prism(quad, 0.0, x0, A.MAT_STRUCTURE)
            sh.prism(quad, x1, L, A.MAT_STRUCTURE)
            sh.prism([(yi, zi0), (yo, zo0), (yo, z0), (yi, z0)], x0, x1, A.MAT_STRUCTURE)     # below the window
            sh.prism([(yi, z1), (yo, z1), (yo, zo1), (yi, zi1)], x0, x1, A.MAT_STRUCTURE)     # above the window
        else:
            sh.prism(quad, 0.0, L, A.MAT_STRUCTURE)
    (yl, _), (yr, _) = inner[0], inner[1]
    (yol, zo), (yor, _) = outer[0], outer[1]
    sh.prism([(yol, zo), (-TRENCH_HW, zo), (-TRENCH_HW, 0.0), (yl, 0.0)], 0.0, L, A.MAT_STRUCTURE)
    sh.prism([(TRENCH_HW, zo), (yor, zo), (yr, 0.0), (TRENCH_HW, 0.0)], 0.0, L, A.MAT_STRUCTURE)
    sh.prism([(-TRENCH_HW, zo), (TRENCH_HW, zo), (TRENCH_HW, -TRENCH_D), (-TRENCH_HW, -TRENCH_D)], 0.0, L, A.MAT_STRUCTURE)
    obj = sh.to_object(name + "_shell")

    b = A.Builder()
    # 2) U ribs: half ribs at the ends (two modules make a full one), full rib in the middle
    for (x0, x1) in ((0.0, 0.1), (L / 2 - 0.1, L / 2 + 0.1), (L - 0.1, L)):
        u_rib(b, x0, x1)
    if window:  # mullion through the wall thickness where the middle rib crosses the window
        b.box_minmax((L / 2 - 0.1, HW, WIN_Z[0]), (L / 2 + 0.1, HW + T, WIN_Z[1]), A.MAT_STRUCTURE)

    # 3) floor: non-skid plates either side of the walkway grate over the service trench
    for (x0, x1) in ((0.02, 1.98), (2.02, 3.98)):
        for s in (1, -1):
            b.box_minmax((x0, s * (TRENCH_HW + 0.03), 0.0), (x1, s * (HW - 0.05), 0.012), A.MAT_FLOOR)
        b.box_minmax((x0, -TRENCH_HW + 0.012, -0.008), (x1, TRENCH_HW - 0.012, 0.012), A.MAT_GRATE)
    for s in (1, -1):
        # grate edge frames and support ledges
        b.box_minmax((0.0, s * TRENCH_HW - 0.012, -0.03), (L, s * (TRENCH_HW + 0.03), 0.014), A.MAT_TRIM)
        # trench wall liners (catch the light through the grate)
    # trench contents: three service pipes, a cable bundle, brackets every metre
    pipes = ((-0.30, -0.085, 0.052), (-0.08, -0.105, 0.036), (0.12, -0.11, 0.03))
    for (y, z, r) in pipes:
        b.cylinder((0.0, y, z), (L, y, z), r, A.MAT_TRIM, segments=14)
    for k in range(6):
        y = 0.30 + 0.028 * (k % 3)
        z = -0.135 + 0.025 * (k // 3)
        b.cylinder((0.0, y, z), (L, y, z), 0.012, A.MAT_RUBBER, segments=8)
    for xb in (0.5, 1.5, 2.5, 3.5):
        b.box_minmax((xb - 0.02, -0.45, -TRENCH_D), (xb + 0.02, 0.45, -0.14), A.MAT_STRUCTURE)
        for (y, z, r) in pipes:
            b.box_minmax((xb - 0.025, y - r - 0.01, -0.145), (xb + 0.025, y + r + 0.01, z - r * 0.4), A.MAT_TRIM)

    # 4) skirting with guide lights, both walls
    for s in (1, -1):
        b.box_minmax((0.0, s * (HW - 0.04), 0.0), (L, s * HW, 0.18), A.MAT_TRIM)
        for k in range(8):
            xc = 0.25 + 0.5 * k
            b.box_minmax((xc - 0.05, s * (HW - 0.044), 0.075), (xc + 0.05, s * (HW - 0.039), 0.087), A.MAT_GUIDE)

    # 5) upper wall band: department accent strip under the chamfer
    for s in (1, -1):
        for (x0, x1) in BAYS:
            b.box_minmax((x0 - 0.02, s * (HW - 0.012), 2.445), (x1 + 0.02, s * HW, 2.47), A.MAT_ACCENT)
            b.box_minmax((x0 - 0.02, s * (HW - 0.02), 2.43), (x1 + 0.02, s * HW, 2.445), A.MAT_TRIM)

    # 6) chamfers: two pipes and a cable tray, with brackets
    for s in (1, -1):
        for (t, off, r) in ((0.28, 0.075, 0.042), (0.58, 0.065, 0.03)):
            y, z = chamfer_point(s, t, off)
            b.cylinder((0.0, y, z), (L, y, z), r, A.MAT_TRIM, segments=14)
            for xb in (0.5, 1.5, 2.5, 3.5):
                yb, zb = chamfer_point(s, t, off * 0.5)
                box_rot_x(b, (xb, yb, zb), (0.035, r * 2.4, off), -45.0 * s, A.MAT_STRUCTURE)
        yt, zt = chamfer_point(s, 0.86, 0.03)
        box_rot_x(b, (L / 2, yt, zt), (L, 0.2, 0.04), -45.0 * s, A.MAT_STRUCTURE)       # cable tray
        for k in range(4):
            yk, zk = chamfer_point(s, 0.80 + 0.04 * k, 0.065)
            b.cylinder((0.0, yk, zk), (L, yk, zk), 0.011, A.MAT_RUBBER, segments=8)

    # 7) ceiling: two panels per bay either side of the light channel
    for (x0, x1) in ((0.12, 1.88), (2.12, 3.88)):
        for yc in (-0.62, 0.62):
            b.box(((x0 + x1) / 2, yc, H - 0.0075), (x1 - x0, 0.95, 0.015), A.MAT_PANEL)
        b.box(((x0 + x1) / 2, 0.0, H - 0.03), (x1 - x0, 0.22, 0.06), A.MAT_TRIM)
        b.box(((x0 + x1) / 2, 0.0, H - 0.065), (x1 - x0 - 0.04, 0.14, 0.012), A.MAT_LIGHT)

    # 8) handrails (not under the window)
    for s in (1, -1):
        if window and s == 1:
            continue
        y = s * (HW - 0.075)
        b.cylinder((0.0, y, 1.02), (L, y, 1.02), 0.021, A.MAT_TRIM, segments=12)
        for xb in (0.5, 1.5, 2.5, 3.5):
            b.box_minmax((xb - 0.02, s * (HW - 0.06), 1.0), (xb + 0.02, s * (HW + 0.0), 1.04), A.MAT_TRIM)

    # 9) window frame (inner side) and sill
    if window:
        x0, x1 = WIN_X
        z0, z1 = WIN_Z
        b.box_minmax((x0 - 0.06, HW - 0.03, z1), (x1 + 0.06, HW, z1 + 0.06), A.MAT_TRIM)          # head
        b.box_minmax((x0 - 0.06, HW - 0.06, z0 - 0.06), (x1 + 0.06, HW + 0.04, z0), A.MAT_TRIM)   # sill
        b.box_minmax((x0 - 0.06, HW - 0.03, z0), (x0, HW, z1), A.MAT_TRIM)
        b.box_minmax((x1, HW - 0.03, z0), (x1 + 0.06, HW, z1), A.MAT_TRIM)
        for (a0, a1) in ((x0, L / 2 - 0.1), (L / 2 + 0.1, x1)):   # rubber seals around the glass
            b.box_minmax((a0, HW + 0.08, z0), (a1, HW + 0.12, z0 + 0.02), A.MAT_RUBBER)
            b.box_minmax((a0, HW + 0.08, z1 - 0.02), (a1, HW + 0.12, z1), A.MAT_RUBBER)

    extra = b.to_object(name + "_extra")
    A.finish(obj, bevel=0.01)
    A.finish(extra, bevel=0.006)
    return A.join([obj, extra], name)


def window_glass(name: str):
    b = A.Builder()
    for (x0, x1) in ((WIN_X[0], L / 2 - 0.1), (L / 2 + 0.1, WIN_X[1])):
        b.box_minmax((x0, HW + 0.095, WIN_Z[0] + 0.02), (x1, HW + 0.105, WIN_Z[1] - 0.02), A.MAT_GLASS)
    return A.finish(b.to_object(name), bevel=0.0)


def bulkhead(name: str):
    depth = 0.5
    outer = offset_convex(inner_profile(), T)
    plate = A.Builder()
    plate.prism(outer, 0.0, depth, A.MAT_STRUCTURE)
    obj = plate.to_object(name + "_plate")
    cut = A.Builder()
    cut.box_minmax((-0.1, -0.7, 0.0), (depth + 0.1, 0.7, 2.3), A.MAT_STRUCTURE)
    A.boolean(obj, cut.to_object("cut_door"))
    b = A.Builder()
    # door frame (trim), sill, decorative panels and status light bars on both faces
    for (cy, cz, sy, sz) in ((0.0, 2.36, 1.64, 0.12), (-0.76, 1.15, 0.12, 2.42), (0.76, 1.15, 0.12, 2.42)):
        b.box((depth / 2, cy, cz), (depth + 0.06, sy, sz), A.MAT_TRIM)
    b.box_minmax((0.0, -0.7, 0.0), (depth, 0.7, 0.014), A.MAT_TRIM)
    for x, sgn in ((-0.012, -1), (depth + 0.012, 1)):
        for (cy, cz, sy, sz) in ((-1.22, 1.3, 0.62, 2.1), (1.22, 1.3, 0.62, 2.1), (0.0, 2.72, 1.9, 0.36)):
            b.box((x, cy, cz), (0.024, sy, sz), A.MAT_PANEL)
        b.box((x + sgn * 0.012, 0.0, 2.5), (0.014, 0.5, 0.05), A.MAT_LIGHT)
        for cy in (-0.9, 0.9):   # vertical status bars beside the door (alert colour)
            b.box((x + sgn * 0.012, cy, 1.2), (0.014, 0.04, 1.6), A.MAT_ACCENT)
    extra = b.to_object(name + "_extra")
    A.finish(obj, bevel=0.012)
    A.finish(extra, bevel=0.006)
    return A.join([obj, extra], name)


def door_leaf(name: str):
    b = A.Builder()
    b.box((0.0, 0.35, 1.15), (0.08, 0.7, 2.3), A.MAT_PANEL)
    b.box((0.0, 0.35, 0.12), (0.1, 0.72, 0.2), A.MAT_TRIM)
    b.box((0.0, 0.02, 1.15), (0.1, 0.04, 2.3), A.MAT_RUBBER)
    b.box((0.0, 0.52, 1.05), (0.1, 0.05, 0.3), A.MAT_TRIM)
    b.box((0.0, 0.35, 2.05), (0.1, 0.5, 0.03), A.MAT_ACCENT)
    b.box((0.0, 0.35, 1.6), (0.1, 0.36, 0.5), A.MAT_TRIM)     # window frame (glass later)
    return A.finish(b.to_object(name), bevel=0.006)


def end_cap(name: str):
    b = A.Builder()
    b.prism(offset_convex(inner_profile(), T), 0.0, 0.2, A.MAT_STRUCTURE)
    for (cy, cz, sy, sz) in ((-0.8, 1.2, 1.4, 2.0), (0.8, 1.2, 1.4, 2.0)):
        b.box((-0.01, cy, cz), (0.02, sy, sz), A.MAT_PANEL)
    b.box((-0.01, 0.0, 2.5), (0.02, 2.0, 0.04), A.MAT_ACCENT)
    return A.finish(b.to_object(name), bevel=0.01)


# ------------------------------------------------------------------ wall panels
def _panel_base(b: A.Builder, h: float, relief: bool = True):
    """Panel slab (1.5 cm) + a 4 mm raised field inset 6 cm: two levels that catch the light."""
    b.box_minmax((0.0, -0.015, 0.0), (PANEL_W, 0.0, h), A.MAT_PANEL)
    if relief:
        b.box_minmax((0.06, -0.019, 0.06), (PANEL_W - 0.06, -0.015, h - 0.06), A.MAT_PANEL)


def panel_plain(name: str, h: float):
    b = A.Builder()
    _panel_base(b, h)
    return A.finish(b.to_object(name), bevel=0.004)


def panel_vent(name: str, h: float, zc: float):
    """Louvred vent: opening cut through the slab, angled slats, dark plenum behind."""
    b = A.Builder()
    _panel_base(b, h, relief=False)
    obj = b.to_object(name + "_slab")
    vw, vh = 1.0, 0.34
    x0, z0 = (PANEL_W - vw) / 2, zc - vh / 2
    cut = A.Builder()
    cut.box_minmax((x0, -0.05, z0), (x0 + vw, 0.05, z0 + vh), A.MAT_PANEL)
    A.boolean(obj, cut.to_object("cut_vent"))
    e = A.Builder()
    e.box_minmax((x0 - 0.03, -0.022, z0 - 0.03), (x0 + vw + 0.03, -0.015, z0 + vh + 0.03), A.MAT_TRIM)   # bezel
    cut2 = A.Builder()
    cut2.box_minmax((x0, -0.05, z0), (x0 + vw, 0.05, z0 + vh), A.MAT_TRIM)
    bez = e.to_object(name + "_bezel")
    A.boolean(bez, cut2.to_object("cut_bezel"))
    s = A.Builder()
    n = 8
    for k in range(n):
        zc_k = z0 + (k + 0.5) * vh / n
        box_rot_x(s, (x0 + vw / 2, -0.008, zc_k), (vw, 0.004, vh / n * 1.25), 35.0, A.MAT_TRIM)
    s.box_minmax((x0, 0.0, z0), (x0 + vw, 0.03, z0 + vh), A.MAT_RUBBER)    # dark plenum
    slats = s.to_object(name + "_slats")
    A.finish(obj, bevel=0.004)
    A.finish(bez, bevel=0.003)
    A.finish(slats, bevel=0.0)
    return A.join([obj, bez, slats], name)


def panel_access(name: str, h: float):
    """Access hatch: grooved outline, recessed pull handles, four fasteners."""
    b = A.Builder()
    _panel_base(b, h, relief=False)
    obj = b.to_object(name + "_slab")
    hx0, hx1, hz0, hz1 = 0.36, PANEL_W - 0.36, 0.16, h - 0.2
    g = 0.006
    cut = A.Builder()
    for (lo, hi) in (((hx0, -0.03, hz0), (hx1, 0.0, hz0 + g)), ((hx0, -0.03, hz1 - g), (hx1, 0.0, hz1)),
                     ((hx0, -0.03, hz0), (hx0 + g, 0.0, hz1)), ((hx1 - g, -0.03, hz0), (hx1, 0.0, hz1))):
        cut.box_minmax((lo[0], lo[1], lo[2]), (hi[0], -0.009, hi[2]), A.MAT_PANEL)
    A.boolean(obj, cut.to_object("cut_groove"))
    e = A.Builder()
    for xc in (hx0 + 0.16, hx1 - 0.16):
        e.box_minmax((xc - 0.07, -0.02, hz1 - 0.16), (xc + 0.07, -0.015, hz1 - 0.1), A.MAT_TRIM)
        e.cylinder((xc - 0.05, -0.028, hz1 - 0.13), (xc + 0.05, -0.028, hz1 - 0.13), 0.008, A.MAT_TRIM, segments=10)
    for (xc, zc) in ((hx0 + 0.05, hz0 + 0.05), (hx1 - 0.05, hz0 + 0.05), (hx0 + 0.05, hz1 - 0.05), (hx1 - 0.05, hz1 - 0.05)):
        e.cylinder((xc, -0.015, zc), (xc, -0.021, zc), 0.011, A.MAT_TRIM, segments=12)
    e.box_minmax((0.5 * PANEL_W - 0.12, -0.017, hz0 + 0.08), (0.5 * PANEL_W + 0.12, -0.015, hz0 + 0.14), A.MAT_ACCENT)
    extra = e.to_object(name + "_extra")
    A.finish(obj, bevel=0.003)
    A.finish(extra, bevel=0.002)
    return A.join([obj, extra], name)


def panel_screen(name: str, h: float):
    """Wall display: recessed screen with a trim bezel at eye height."""
    b = A.Builder()
    _panel_base(b, h, relief=False)
    obj = b.to_object(name + "_slab")
    sw, sh = 0.9, 0.52
    x0, z0 = (PANEL_W - sw) / 2, 0.14
    cut = A.Builder()
    cut.box_minmax((x0, -0.05, z0), (x0 + sw, -0.006, z0 + sh), A.MAT_PANEL)
    A.boolean(obj, cut.to_object("cut_screen"))
    e = A.Builder()
    e.box_minmax((x0 - 0.035, -0.024, z0 - 0.035), (x0 + sw + 0.035, -0.015, z0), A.MAT_TRIM)
    e.box_minmax((x0 - 0.035, -0.024, z0 + sh), (x0 + sw + 0.035, -0.015, z0 + sh + 0.035), A.MAT_TRIM)
    e.box_minmax((x0 - 0.035, -0.024, z0), (x0, -0.015, z0 + sh), A.MAT_TRIM)
    e.box_minmax((x0 + sw, -0.024, z0), (x0 + sw + 0.035, -0.015, z0 + sh), A.MAT_TRIM)
    e.box_minmax((x0, -0.008, z0), (x0 + sw, -0.006, z0 + sh), A.MAT_SCREEN)
    e.box_minmax((x0 + sw - 0.06, -0.026, z0 - 0.03), (x0 + sw - 0.02, -0.024, z0 - 0.01), A.MAT_GUIDE)  # status LED
    extra = e.to_object(name + "_extra")
    A.finish(obj, bevel=0.003)
    A.finish(extra, bevel=0.002)
    return A.join([obj, extra], name)


def main() -> None:
    out_dir = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "art/export/kit_corridor"
    A.reset_scene()
    builders = [
        ("SM_COR_Shell_4m", lambda n: shell(n)),
        ("SM_COR_ShellWindow_4m", lambda n: shell(n, window=True)),
        ("SM_COR_WindowGlass", window_glass),
        ("SM_COR_Bulkhead", bulkhead),
        ("SM_COR_DoorLeaf", door_leaf),
        ("SM_COR_EndCap", end_cap),
        ("SM_COR_PanelLow_Plain", lambda n: panel_plain(n, LOW_Z[1] - LOW_Z[0])),
        ("SM_COR_PanelLow_Vent", lambda n: panel_vent(n, LOW_Z[1] - LOW_Z[0], 0.3)),
        ("SM_COR_PanelLow_Access", lambda n: panel_access(n, LOW_Z[1] - LOW_Z[0])),
        ("SM_COR_PanelUp_Plain", lambda n: panel_plain(n, UP_Z[1] - UP_Z[0])),
        ("SM_COR_PanelUp_Screen", lambda n: panel_screen(n, UP_Z[1] - UP_Z[0])),
        ("SM_COR_PanelUp_Vent", lambda n: panel_vent(n, UP_Z[1] - UP_Z[0], 0.8)),
        ("SM_COR_PanelLowShort_Plain", lambda n: panel_plain(n, 0.62)),
    ]
    report = []
    for name, build in builders:
        A.clear_objects()
        obj = build(name)
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("KIT_OK", json.dumps(report))


if __name__ == "__main__":
    main()
