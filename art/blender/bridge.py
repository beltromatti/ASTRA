"""ASN Aquila — Bridge (Deck 1 · Section A). Procedural generator driven by data/ship/aquila_bridge.json.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/bridge.py -- <output_dir> [--preview <png_dir>]

All layout coordinates are in the Unreal convention of the data file (X forward, Y starboard, Z up, metres);
U(x, y, z) converts them to Blender (Y flipped), so the exported meshes land exactly on the data in Unreal.

Meshes (origin = bridge origin unless noted):
  SM_BRG_Shell          floors (upper deck, well, dais, wings), stairs, walls with panels and pilasters,
                        panoramic window frame (6 facets), ceiling with coffered dome and light coves
  SM_BRG_WindowGlass    the six window panes
  SM_BRG_Railing        well railings (posts, top rail, glass infill)
Props (origin at the officer position on the floor, facing +X):
  SM_BRG_ConsoleSeated  seated console desk with three screens
  SM_BRG_ChairCrew      crew chair
  SM_BRG_ChairCaptain   captain's chair with armrest consoles
  SM_BRG_TacticalRail   curved standing console (tactical)
  SM_BRG_HoloTable      holographic plotting table (origin at the table centre)
  SM_BRG_MasterDisplay  back-wall master systems display (origin at the wall, bottom centre)
"""
from __future__ import annotations

import json
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_bridge.json"), encoding="utf-8"))

UPPER, WELL, DAIS = D["levels"]["upper"], D["levels"]["well"], D["levels"]["dais"]
CEIL = D["ceiling"]["height"]
WIN = D["window"]
R_WIN = WIN["radius"]
ANG = [math.radians(a) for a in WIN["angles_deg"]]
BACK_X = D["walls"]["back_x"]
BACK_HW = D["walls"]["back_half_width"]
WELL_X = D["well"]["edge_x"]
WELL_HW = D["well"]["half_width"]
WALL_T = 0.3
FLOOR_BOTTOM = -0.9


def U(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
    """Unreal-convention layout point -> Blender coordinates."""
    return (x, -y, z)


def arc(a: float, r: float = R_WIN) -> tuple[float, float]:
    return (r * math.cos(a), r * math.sin(a))


FRONT_P = arc(ANG[0])     # port end of the window (x, y)
FRONT_S = arc(ANG[-1])    # starboard end


def side_wall_y(x: float, side: int) -> float:
    """Inner surface of the side wall at abscissa x (side +1 starboard, -1 port)."""
    t = (x - BACK_X) / (FRONT_S[0] - BACK_X)
    return side * (BACK_HW + t * (abs(FRONT_S[1]) - BACK_HW))


def slab(b: A.Builder, poly_xy, z0: float, z1: float, mat: str) -> None:
    """Vertical prism from a convex (x, y) polygon in layout coordinates."""
    bm = b.bm
    lo = [bm.verts.new(U(x, y, z0)) for x, y in poly_xy]
    hi = [bm.verts.new(U(x, y, z1)) for x, y in poly_xy]
    faces = [bm.faces.new(lo), bm.faces.new(list(reversed(hi)))]
    n = len(poly_xy)
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    idx = b.mi(mat)
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def obox(b: A.Builder, p0, p1, z0: float, z1: float, depth: float, mat: str, offset: float = 0.0) -> None:
    """Box along the segment p0->p1 (layout x, y), `depth` thick, shifted `offset` along the segment's right normal."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    nx, ny = dy / length, -dx / length          # right-hand normal in layout coordinates
    cx = (x0 + x1) / 2 + nx * offset
    cy = (y0 + y1) / 2 + ny * offset
    yaw = math.atan2(-dy, dx)                    # angle in Blender (Y flipped)
    m = (Matrix.Translation(U(cx, cy, (z0 + z1) / 2)) @ Matrix.Rotation(yaw, 4, "Z")
         @ Matrix.Diagonal((length, depth, z1 - z0, 1.0)))
    geom = bmesh.ops.create_cube(b.bm, size=1.0, matrix=m)
    b._assign(geom["verts"], mat)


def lbox(b: A.Builder, lo, hi, mat: str) -> None:
    """Axis-aligned box from layout min/max corners."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    b.box_minmax((min(x0, x1), min(-y0, -y1), z0), (max(x0, x1), max(-y0, -y1), z1), mat)


# ------------------------------------------------------------------ shell
def shell(name: str):
    b = A.Builder()
    yw = side_wall_y(WELL_X, 1)
    # --- floors: upper deck, side wings, well, dais
    slab(b, [(BACK_X, -BACK_HW), (WELL_X, -yw), (WELL_X, yw), (BACK_X, BACK_HW)], FLOOR_BOTTOM, UPPER, A.MAT_FLOOR_BRIDGE)
    # the well edge line y = +-WELL_HW meets the window facet between 20 and 40 degrees
    a20, a40 = arc(ANG[4]), arc(ANG[5])
    t = (WELL_HW - a20[1]) / (a40[1] - a20[1])
    xe = a20[0] + t * (a40[0] - a20[0])
    for s in (1, -1):
        wing = [(WELL_X, s * WELL_HW), (xe, s * WELL_HW), (arc(ANG[5])[0], s * arc(ANG[5])[1]),
                (FRONT_S[0], s * FRONT_S[1]), (WELL_X, s * yw)]
        slab(b, wing, FLOOR_BOTTOM, UPPER, A.MAT_FLOOR_BRIDGE)
    well = [(WELL_X, -WELL_HW), (xe, -WELL_HW), arc(ANG[2]), arc(ANG[3]), arc(ANG[4]), (xe, WELL_HW), (WELL_X, WELL_HW)]
    slab(b, well, FLOOR_BOTTOM, WELL, A.MAT_FLOOR_BRIDGE)
    # stairs into the well (three risers of 0.2 m)
    sw = D["well"]["stair_width"]
    for yc in D["well"]["stairs_y"]:
        lbox(b, (WELL_X, yc - sw / 2, WELL), (WELL_X + 0.35, yc + sw / 2, -0.2), A.MAT_FLOOR_BRIDGE)
        lbox(b, (WELL_X + 0.35, yc - sw / 2, WELL), (WELL_X + 0.70, yc + sw / 2, -0.4), A.MAT_FLOOR_BRIDGE)
        for k, x in enumerate((WELL_X, WELL_X + 0.35)):     # step nosings with guide lights
            z = -0.2 * (k + 1)
            lbox(b, (x - 0.03, yc - sw / 2, z - 0.03), (x + 0.02, yc + sw / 2, z + 0.004), A.MAT_TRIM)
            lbox(b, (x - 0.032, yc - sw / 2 + 0.05, z - 0.02), (x - 0.028, yc + sw / 2 - 0.05, z - 0.01), A.MAT_GUIDE)
    # edge nosing of the well, with a guide light line
    lbox(b, (WELL_X - 0.04, -WELL_HW + sw, UPPER - 0.04), (WELL_X + 0.02, WELL_HW - sw, UPPER + 0.004), A.MAT_TRIM)
    lbox(b, (WELL_X + 0.018, -WELL_HW + sw, UPPER - 0.03), (WELL_X + 0.022, WELL_HW - sw, UPPER - 0.015), A.MAT_GUIDE)
    # dais for the command chairs (rounded plan)
    dais = []
    for k in range(24):
        a = 2 * math.pi * k / 24
        dais.append((1.25 * math.cos(a), 2.9 * math.sin(a)))
    slab(b, dais, UPPER - 0.05, DAIS, A.MAT_FLOOR_BRIDGE)
    ring_out = [(1.29 * math.cos(2 * math.pi * k / 24), 2.94 * math.sin(2 * math.pi * k / 24)) for k in range(24)]
    slab(b, ring_out, DAIS - 0.03, DAIS - 0.01, A.MAT_GUIDE)   # thin light line under the dais lip

    # --- back wall with two door openings
    doors = sorted(d["pos"][1] for d in D["doors"])
    dw = D["doors"][0]["width"]
    dh = D["doors"][0]["height"]
    cuts = [(-BACK_HW, doors[0] - dw / 2), (doors[0] + dw / 2, doors[1] - dw / 2), (doors[1] + dw / 2, BACK_HW)]
    for (y0, y1) in cuts:
        lbox(b, (BACK_X - WALL_T, y0, UPPER), (BACK_X, y1, CEIL), A.MAT_STRUCTURE)
    for yc in doors:
        lbox(b, (BACK_X - WALL_T, yc - dw / 2, dh), (BACK_X, yc + dw / 2, CEIL), A.MAT_STRUCTURE)
        # door frame
        lbox(b, (BACK_X - 0.02, yc - dw / 2 - 0.12, UPPER), (BACK_X + 0.06, yc - dw / 2, dh + 0.12), A.MAT_TRIM)
        lbox(b, (BACK_X - 0.02, yc + dw / 2, UPPER), (BACK_X + 0.06, yc + dw / 2 + 0.12, dh + 0.12), A.MAT_TRIM)
        lbox(b, (BACK_X - 0.02, yc - dw / 2, dh), (BACK_X + 0.06, yc + dw / 2, dh + 0.12), A.MAT_TRIM)
        lbox(b, (BACK_X + 0.06, yc - 0.3, dh + 0.04), (BACK_X + 0.07, yc + 0.3, dh + 0.08), A.MAT_ACCENT)
    # back wall panels (around the master display and doors)
    for (y0, y1) in ((-BACK_HW + 0.2, doors[0] - dw / 2 - 0.25), (doors[1] + dw / 2 + 0.25, BACK_HW - 0.2)):
        for (z0, z1) in ((0.25, 1.35), (1.4, 2.9), (2.95, 4.05)):
            lbox(b, (BACK_X, y0, z0), (BACK_X + 0.018, y1, z1), A.MAT_PANEL)
    for (y0, y1) in ((doors[0] + dw / 2 + 0.25, doors[1] - dw / 2 - 0.25),):
        lbox(b, (BACK_X, y0, 0.25), (BACK_X + 0.018, y1, 1.1), A.MAT_PANEL)
        lbox(b, (BACK_X, y0, 3.5), (BACK_X + 0.018, y1, 4.05), A.MAT_PANEL)
    lbox(b, (BACK_X, -BACK_HW, 0.0), (BACK_X + 0.04, BACK_HW, 0.18), A.MAT_TRIM)     # skirting

    # --- side walls: structure slab, pilasters, panels, skirting
    for s in (1, -1):
        p0 = (BACK_X, s * BACK_HW)
        p1 = (FRONT_S[0], s * abs(FRONT_S[1]))
        # outward is the right-hand normal when walking p0->p1 on starboard, left on port
        obox(b, p0, p1, UPPER, CEIL, WALL_T, A.MAT_STRUCTURE, offset=-WALL_T / 2 * s)
        obox(b, p0, p1, 0.0, 0.18, 0.04, A.MAT_TRIM, offset=0.02 * s)
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n_bays = 6
        for k in range(n_bays):
            f0 = (k + 0.06) / n_bays
            f1 = (k + 0.94) / n_bays
            q0 = (p0[0] + (p1[0] - p0[0]) * f0, p0[1] + (p1[1] - p0[1]) * f0)
            q1 = (p0[0] + (p1[0] - p0[0]) * f1, p0[1] + (p1[1] - p0[1]) * f1)
            for (z0, z1) in ((0.25, 1.35), (1.4, 2.9), (2.95, 4.05)):
                obox(b, q0, q1, z0, z1, 0.018, A.MAT_PANEL, offset=0.009 * s)
            # pilaster between bays
            fp = k / n_bays
            c = (p0[0] + (p1[0] - p0[0]) * fp, p0[1] + (p1[1] - p0[1]) * fp)
            d = (0.12 * (p1[0] - p0[0]) / L, 0.12 * (p1[1] - p0[1]) / L)
            obox(b, (c[0] - d[0], c[1] - d[1]), (c[0] + d[0], c[1] + d[1]), UPPER, CEIL, 0.14, A.MAT_STRUCTURE,
                 offset=0.07 * s)
        # cove light at the top of the wall (lip + hidden strip)
        obox(b, p0, p1, 4.1, 4.16, 0.22, A.MAT_TRIM, offset=0.11 * s)
        obox(b, p0, p1, 4.17, 4.19, 0.05, A.MAT_LIGHT, offset=0.05 * s)

    # --- panoramic window: sill band, head band, mullions (the glass is a separate mesh)
    for k in range(len(ANG) - 1):
        pa, pb = arc(ANG[k], R_WIN), arc(ANG[k + 1], R_WIN)
        # a positive offset moves along the right normal of pa->pb, which points inwards for increasing angles
        obox(b, pa, pb, FLOOR_BOTTOM, WIN["sill"], 0.7, A.MAT_STRUCTURE, offset=0.05)
        obox(b, pa, pb, WIN["sill"] - 0.04, WIN["sill"] + 0.02, 0.5, A.MAT_TRIM, offset=0.26)       # sill cap
        obox(b, pa, pb, WIN["head"], CEIL + 0.3, 0.7, A.MAT_STRUCTURE, offset=0.05)
        obox(b, pa, pb, WIN["head"] - 0.03, WIN["head"], 0.36, A.MAT_TRIM, offset=0.2)
        obox(b, pa, pb, WIN["sill"] + 0.02, WIN["sill"] + 0.045, 0.04, A.MAT_GUIDE, offset=0.45)    # sill light
    for k, a in enumerate(ANG):
        heavy = k in (0, len(ANG) - 1)
        w = 0.5 if heavy else 0.26
        r0, r1 = R_WIN - 0.35, R_WIN + 0.35
        c0, c1 = arc(a, r0), arc(a, r1)
        # radial box: build it along the radius, width w
        obox(b, c0, c1, FLOOR_BOTTOM, CEIL + 0.3, w, A.MAT_STRUCTURE)
        cc0, cc1 = arc(a, R_WIN - 0.37), arc(a, R_WIN - 0.3)
        obox(b, cc0, cc1, WIN["sill"], WIN["head"], w + 0.06, A.MAT_TRIM)

    # --- ceiling: slab with the dome opening (boolean), dome drum, cap with light, radial beams
    outline = [(BACK_X - WALL_T, -BACK_HW - WALL_T), (FRONT_P[0], FRONT_P[1] - WALL_T)]
    outline += [arc(a, R_WIN + 0.35) for a in ANG]
    outline += [(FRONT_S[0], FRONT_S[1] + WALL_T), (BACK_X - WALL_T, BACK_HW + WALL_T)]
    cb = A.Builder()
    slab(cb, outline, CEIL, CEIL + 0.3, A.MAT_STRUCTURE)
    ceiling = cb.to_object(name + "_ceiling")
    dc = D["ceiling"]["dome_center"]
    dr = D["ceiling"]["dome_radius"]
    cut = A.Builder()
    slab(cut, [(dc[0] + dr * math.cos(2 * math.pi * (k + 0.5) / 8), dc[1] + dr * math.sin(2 * math.pi * (k + 0.5) / 8))
               for k in range(8)], CEIL - 0.1, CEIL + 0.5, A.MAT_PANEL)
    A.boolean(ceiling, cut.to_object("cut_dome"))
    oct_pts = [(dc[0] + dr * math.cos(2 * math.pi * (k + 0.5) / 8), dc[1] + dr * math.sin(2 * math.pi * (k + 0.5) / 8))
               for k in range(8)]
    dh = D["ceiling"]["dome_height"]
    for k in range(8):
        pa, pb = oct_pts[k], oct_pts[(k + 1) % 8]
        obox(b, pa, pb, CEIL, dh, 0.2, A.MAT_PANEL, offset=0.1)          # drum wall (outside the octagon)
        obox(b, pa, pb, CEIL - 0.12, CEIL, 0.25, A.MAT_TRIM, offset=-0.1)  # lip hiding the cove strip
        obox(b, pa, pb, CEIL + 0.02, CEIL + 0.05, 0.06, A.MAT_LIGHT, offset=0.02)
    slab(b, [(dc[0] + (dr + 0.25) * math.cos(2 * math.pi * (k + 0.5) / 8), dc[1] + (dr + 0.25) * math.sin(2 * math.pi * (k + 0.5) / 8))
             for k in range(8)], dh, dh + 0.2, A.MAT_PANEL)
    slab(b, [(dc[0] + 1.1 * math.cos(2 * math.pi * k / 16), dc[1] + 1.1 * math.sin(2 * math.pi * k / 16)) for k in range(16)],
         dh - 0.02, dh, A.MAT_LIGHT)
    # coffered ceiling: 1.2 m ivory panels on a 1.26 m grid (dark gaps), inside the outline and clear of the dome
    def inside(px, py):
        n = len(outline)
        sign = 0
        for i in range(n):
            (ax, ay), (bx, by) = outline[i], outline[(i + 1) % n]
            c = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            if abs(c) < 1e-9:
                continue
            if sign == 0:
                sign = 1 if c > 0 else -1
            elif (c > 0) != (sign > 0):
                return False
        return True
    pitch, size = 1.26, 1.2
    for i in range(-8, 9):
        for j in range(-8, 9):
            cx, cy = dc[0] + i * pitch, j * pitch
            corners = [(cx + sx * size / 2, cy + sy * size / 2) for sx in (-1, 1) for sy in (-1, 1)]
            if not all(inside(px, py) for px, py in corners):
                continue
            if math.hypot(cx - dc[0], cy - dc[1]) < dr + 1.0:
                continue
            lbox(b, (cx - size / 2, cy - size / 2, CEIL - 0.025), (cx + size / 2, cy + size / 2, CEIL), A.MAT_STRUCTURE)
            lbox(b, (cx - 0.11, cy - 0.11, CEIL - 0.03), (cx + 0.11, cy + 0.11, CEIL - 0.024), A.MAT_GUIDE)   # recessed downlight
    # radial beams from the dome towards the window mullions and the walls
    for a in ANG[1:-1]:
        p_in = (dc[0] + (dr + 0.1) * math.cos(a), dc[1] + (dr + 0.1) * math.sin(a))
        p_out = arc(a, R_WIN - 0.4)
        obox(b, p_in, p_out, CEIL - 0.32, CEIL, 0.26, A.MAT_STRUCTURE)
        obox(b, p_in, p_out, CEIL - 0.335, CEIL - 0.32, 0.05, A.MAT_LIGHT)
    for yb in (-3.9, 3.9):
        obox(b, (BACK_X, yb), (dc[0] - dr * 0.7, yb * 0.55), CEIL - 0.32, CEIL, 0.26, A.MAT_STRUCTURE)

    obj = b.to_object(name + "_main")
    A.finish(obj, bevel=0.01)
    A.finish(ceiling, bevel=0.01)
    return A.join([obj, ceiling], name)


def window_glass(name: str):
    b = A.Builder()
    for k in range(len(ANG) - 1):
        pa, pb = arc(ANG[k], R_WIN + 0.1), arc(ANG[k + 1], R_WIN + 0.1)
        obox(b, pa, pb, WIN["sill"], WIN["head"], 0.03, A.MAT_GLASS)
    return A.finish(b.to_object(name), bevel=0.0)


def railing(name: str):
    """Well railings: along the well edge (between the stairs) and along both wing edges."""
    b = A.Builder()
    sw = D["well"]["stair_width"]
    runs = [((WELL_X - 0.08, -WELL_HW + sw), (WELL_X - 0.08, WELL_HW - sw))]
    a20, a40 = arc(ANG[4]), arc(ANG[5])
    t = (WELL_HW - a20[1]) / (a40[1] - a20[1])
    xe = a20[0] + t * (a40[0] - a20[0])
    for s in (1, -1):
        runs.append(((WELL_X + 0.75, s * (WELL_HW + 0.08)), (xe - 0.45, s * (WELL_HW + 0.08))))
    for (p0, p1) in runs:
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(2, int(L / 1.2) + 1)
        for k in range(n):
            f = k / (n - 1)
            x = p0[0] + (p1[0] - p0[0]) * f
            y = p0[1] + (p1[1] - p0[1]) * f
            b.cylinder(U(x, y, 0.0), U(x, y, 1.02), 0.025, A.MAT_TRIM, segments=12)
        b.cylinder(U(p0[0], p0[1], 1.05), U(p1[0], p1[1], 1.05), 0.03, A.MAT_TRIM, segments=16)
        obox(b, p0, p1, 0.12, 0.95, 0.012, A.MAT_GLASS)
        obox(b, p0, p1, 0.06, 0.1, 0.05, A.MAT_TRIM)
        obox(b, p0, p1, 1.08, 1.09, 0.02, A.MAT_GUIDE)
    return A.finish(b.to_object(name), bevel=0.004)


# ------------------------------------------------------------------ props
def console_seated(name: str):
    """Seated console: pedestal, sloped desk with touch surface, three angled screens. Officer at the origin, facing +X."""
    b = A.Builder()
    x0 = 0.45            # front edge of the desk (towards the officer)
    w = 1.7
    # pedestal
    lbox(b, (x0 + 0.15, -0.55, 0.0), (x0 + 0.65, 0.55, 0.68), A.MAT_STRUCTURE)
    lbox(b, (x0 + 0.1, -0.6, 0.0), (x0 + 0.7, 0.6, 0.06), A.MAT_TRIM)
    # desk top (slightly sloped towards the officer) made as a prism profile in the x-z plane
    prof = [(x0, 0.70), (x0 + 0.62, 0.78), (x0 + 0.62, 0.84), (x0 - 0.02, 0.76)]
    bm = b.bm
    vl = [bm.verts.new(U(px, -w / 2, pz)) for px, pz in prof]
    vr = [bm.verts.new(U(px, w / 2, pz)) for px, pz in prof]
    faces = [bm.faces.new(vl), bm.faces.new(list(reversed(vr)))]
    for i in range(4):
        j = (i + 1) % 4
        faces.append(bm.faces.new((vl[i], vl[j], vr[j], vr[i])))
    idx = b.mi(A.MAT_RUBBER)
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    # touch surface inlay on the desk (local frame: X normal up, Y across, Z along the desk towards the screens)
    ang = math.atan2(0.08, 0.62)
    m = (Matrix.Translation(U(x0 + 0.3, 0.0, 0.8045)) @ Matrix.Rotation(-ang, 4, "Y") @ Matrix.Rotation(math.radians(-90), 4, "Y")
         @ Matrix.Diagonal((0.006, -1.1, -0.42, 1.0)))
    b.screen(m, "MI_ASTRA_ScreenTouch")
    # three screens on a spine, angled towards the officer
    lbox(b, (x0 + 0.6, -0.06, 0.8), (x0 + 0.7, 0.06, 1.05), A.MAT_STRUCTURE)
    for (yc, yaw, slot) in ((-0.56, 22.0, "MI_ASTRA_ScreenA"), (0.0, 0.0, "MI_ASTRA_ScreenB"), (0.56, -22.0, "MI_ASTRA_ScreenC")):
        # layout y (starboard) -> Blender -y; the screen faces the officer (-X)
        m = (Matrix.Translation(U(x0 + 0.68 - abs(yc) * 0.25, yc, 1.2)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
             @ Matrix.Rotation(math.radians(-12), 4, "Y"))
        geom = bmesh.ops.create_cube(bm, size=1.0, matrix=m @ Matrix.Diagonal((0.05, 0.56, 0.36, 1.0)))
        b._assign(geom["verts"], A.MAT_STRUCTURE)
        # screen: its local +Y must run towards the officer's right (Blender -Y) so the image is not mirrored
        b.screen(m @ Matrix.Translation((-0.026, 0, 0)) @ Matrix.Diagonal((0.01, -0.52, 0.32, 1.0)), slot)
    # status light strip on the desk edge
    lbox(b, (x0 - 0.03, -w / 2 + 0.1, 0.735), (x0 - 0.02, w / 2 - 0.1, 0.75), A.MAT_ACCENT)
    return A.finish(b.to_object(name), bevel=0.006)


def chair(name: str, captain: bool = False):
    """Bridge chair: five-star base (crew) or plinth (captain), rounded seat and backrest cushions on ivory shells,
    curved backrest, headrest, armrests (captain: armrest consoles with screens). Faces +X, origin on the floor."""
    k = 1.12 if captain else 1.0
    parts = []
    base = A.Builder()
    if captain:
        base.cylinder((0, 0, 0.0), (0, 0, 0.08), 0.34, A.MAT_STRUCTURE, segments=40)
        base.cylinder((0, 0, 0.08), (0, 0, 0.36), 0.12, A.MAT_TRIM, segments=32)
        base.cylinder((0, 0, 0.078), (0, 0, 0.086), 0.345, A.MAT_GUIDE, segments=40)
    else:
        for i in range(5):
            a = 2 * math.pi * i / 5
            base.cylinder((0.03 * math.cos(a), 0.03 * math.sin(a), 0.07), (0.30 * math.cos(a), 0.30 * math.sin(a), 0.045),
                          0.024, A.MAT_STRUCTURE, segments=10)
            base.cylinder((0.30 * math.cos(a), 0.30 * math.sin(a), 0.0), (0.30 * math.cos(a), 0.30 * math.sin(a), 0.05),
                          0.026, A.MAT_RUBBER, segments=12)
        base.cylinder((0, 0, 0.04), (0, 0, 0.1), 0.07, A.MAT_STRUCTURE, segments=24)
        base.cylinder((0, 0, 0.1), (0, 0, 0.4), 0.032, A.MAT_TRIM, segments=20)
    base.box((0.0, 0, 0.415), (0.3, 0.3, 0.04), A.MAT_STRUCTURE)
    parts.append(A.finish(base.to_object(name + "_base"), bevel=0.004))
    # seat
    seat_shell = A.rounded_box(name + "_seatshell", (0.02, 0, 0.45), (0.53 * k, 0.53 * k, 0.05), 0.02, A.MAT_STRUCTURE)
    seat = A.rounded_box(name + "_seat", (0.035, 0, 0.505), (0.49 * k, 0.49 * k, 0.075), 0.034, A.MAT_LEATHER,
                         cuts=(3, 3, 0))
    A.transform(seat, rot_deg=(0, -3.0, 0))
    parts += [seat_shell, seat]
    # backrest: curved slabs (concave towards the sitter), reclined 12 degrees
    def back_part(nm, thick, width, height, mat, dx, rr):
        o = A.arc_slab(nm, width, height, thick, 0.62 if captain else 0.7, mat, segments=14, round_radius=rr)
        A.transform(o, loc=(dx, 0, -height / 2))
        A.transform(o, rot_deg=(0, -12.0, 0))
        A.transform(o, loc=(-0.25 * k, 0, 0.83 * k + 0.02))
        return o
    parts.append(back_part(name + "_backshell", 0.03, 0.54 * k, 0.68 * k, A.MAT_STRUCTURE, -0.058, 0.012))
    parts.append(back_part(name + "_back", 0.05, 0.48 * k, 0.6 * k, A.MAT_LEATHER, 0.0, 0.022))
    # headrest on two posts
    hz = 1.24 * k
    head = A.rounded_box(name + "_head", (-0.345 * k, 0, hz), (0.075, 0.3 * k, 0.15), 0.03, A.MAT_LEATHER, cuts=(0, 2, 0))
    parts.append(head)
    posts = A.Builder()
    for sy in (-0.08, 0.08):
        posts.cylinder((-0.36 * k, sy * k, hz - 0.2), (-0.36 * k, sy * k, hz - 0.03), 0.011, A.MAT_TRIM, segments=10)
    parts.append(A.finish(posts.to_object(name + "_posts"), bevel=0.0))
    # armrests
    for side in (1, -1):
        y = side * 0.305 * k
        arm = A.rounded_box(name + f"_arm{side}", (0.0, y, 0.665), (0.4 * k, (0.13 if captain else 0.075), 0.045), 0.018,
                            A.MAT_LEATHER if not captain else A.MAT_STRUCTURE)
        parts.append(arm)
        sup = A.Builder()
        sup.box((-0.12, y, 0.55), (0.05, 0.035, 0.2), A.MAT_TRIM)
        sup.box((0.0, y, 0.44), (0.3, 0.035, 0.03), A.MAT_TRIM)
        if captain:
            m = Matrix.Translation((0.06, y, 0.69)) @ Matrix.Rotation(math.radians(10), 4, "Y") @ Matrix.Diagonal((0.2, 0.09, 0.006, 1.0))
            geom = bmesh.ops.create_cube(sup.bm, size=1.0, matrix=m)
            sup._assign(geom["verts"], A.MAT_SCREEN)
            sup.box((0.2, y, 0.69), (0.03, 0.1, 0.012), A.MAT_ACCENT)
        parts.append(A.finish(sup.to_object(name + f"_sup{side}"), bevel=0.003))
    obj = A.join(parts, name)
    A.box_uv(obj)
    return obj


def tactical_rail(name: str):
    """Curved standing console: an arc segment centred on the captain's chair, facing forward (+X)."""
    b = A.Builder()
    r0, r1 = 1.35, 1.8          # distance from the captain's chair: the rail stands 0.4 m in front of the officer
    span = math.radians(60)
    n = 12
    # console body as a series of wedge boxes along the arc, centred at the officer origin (0,0)
    cx = 2.2                    # arc centre is 2.2 m in front of the officer (the captain's chair)
    for k in range(n):
        a0 = math.pi - span / 2 + span * k / n
        a1 = math.pi - span / 2 + span * (k + 1) / n
        # arc around (cx, 0) in layout coordinates, the officer stands behind the rail (at x ~ 0)
        pts_in = [(cx + r0 * math.cos(a), r0 * math.sin(a)) for a in (a0, a1)]
        pts_out = [(cx + r1 * math.cos(a), r1 * math.sin(a)) for a in (a0, a1)]
        poly = [pts_in[0], pts_in[1], pts_out[1], pts_out[0]]
        slab(b, poly, 0.0, 0.95, A.MAT_STRUCTURE)
        slab(b, poly, 0.95, 1.0, A.MAT_RUBBER)
        # sloped screen strip on top, facing the officer (outer side)
        mid_in = ((pts_in[0][0] + pts_in[1][0]) / 2, (pts_in[0][1] + pts_in[1][1]) / 2)
        mid_out = ((pts_out[0][0] + pts_out[1][0]) / 2, (pts_out[0][1] + pts_out[1][1]) / 2)
        seg = math.hypot(pts_in[1][0] - pts_in[0][0], pts_in[1][1] - pts_in[0][1])
        cxm = (mid_in[0] * 0.35 + mid_out[0] * 0.65)
        cym = (mid_in[1] * 0.35 + mid_out[1] * 0.65)
        yaw = math.atan2(-(mid_out[1] - mid_in[1]), mid_out[0] - mid_in[0])
        m = (Matrix.Translation(U(cxm, cym, 1.02)) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Rotation(math.radians(-20), 4, "Y")
             @ Matrix.Rotation(math.radians(-90), 4, "Y") @ Matrix.Diagonal((0.012, -seg * 0.96, 0.3, 1.0)))
        b.screen(m, "MI_ASTRA_ScreenTactical", u_range=(k / n, (k + 1) / n))
    # front face light line
    return A.finish(b.to_object(name), bevel=0.006)


def holo_table(name: str):
    b = A.Builder()
    r = D["holo_table"]["radius"]
    h = D["holo_table"]["height"]
    circle = lambda rr, n=48: [(rr * math.cos(2 * math.pi * k / n), rr * math.sin(2 * math.pi * k / n)) for k in range(n)]
    slab(b, circle(r * 0.55), 0.0, h - 0.12, A.MAT_STRUCTURE)            # pedestal
    slab(b, circle(r * 0.7), 0.0, 0.08, A.MAT_TRIM)                       # foot
    slab(b, circle(r), h - 0.12, h - 0.02, A.MAT_STRUCTURE)               # table rim body
    slab(b, circle(r + 0.03), h - 0.03, h + 0.02, A.MAT_TRIM)             # rim
    slab(b, circle(r - 0.06, 64), h - 0.02, h + 0.006, A.MAT_TRIM)       # dark projection surface (the plot draws on it)
    slab(b, circle(r * 0.56, 48), h - 0.3, h - 0.26, A.MAT_ACCENT)        # glow ring under the top
    return A.finish(b.to_object(name), bevel=0.006)


def master_display(name: str):
    md = D["master_display"]
    b = A.Builder()
    w, h, z0 = md["width"], md["height"], md["bottom"]
    lbox(b, (0.0, -w / 2 - 0.12, z0 - 0.12), (0.12, w / 2 + 0.12, z0 + h + 0.12), A.MAT_STRUCTURE)
    b.screen(Matrix.Translation(U(0.125, 0.0, z0 + h / 2)) @ Matrix.Diagonal((0.01, w, h, 1.0)), "MI_ASTRA_ScreenMaster")
    lbox(b, (0.1, -w / 2 - 0.12, z0 - 0.16), (0.16, w / 2 + 0.12, z0 - 0.12), A.MAT_ACCENT)
    return A.finish(b.to_object(name), bevel=0.008)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/bridge"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    builders = [
        ("SM_BRG_Shell", shell),
        ("SM_BRG_WindowGlass", window_glass),
        ("SM_BRG_Railing", railing),
        ("SM_BRG_ConsoleSeated", console_seated),
        ("SM_BRG_ChairCrew", lambda n: chair(n)),
        ("SM_BRG_ChairCaptain", lambda n: chair(n, captain=True)),
        ("SM_BRG_TacticalRail", tactical_rail),
        ("SM_BRG_HoloTable", holo_table),
        ("SM_BRG_MasterDisplay", master_display),
    ]
    only = os.environ.get("ASTRA_ONLY")
    report = []
    for name, build in builders:
        if only and name not in only.split(","):
            continue
        A.clear_objects()
        obj = build(name)
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
        if preview:
            os.makedirs(preview, exist_ok=True)
            view = (200.0, 35.0) if name == "SM_BRG_Shell" else (215.0, 25.0)
            A.render_preview([obj], os.path.join(preview, name + ".png"), view=view,
                             dist_mul=0.9 if name == "SM_BRG_Shell" else 1.4)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("BRIDGE_OK", json.dumps(report))


if __name__ == "__main__":
    main()
