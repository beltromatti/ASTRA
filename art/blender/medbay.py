"""ASN Aquila — the Medbay (Deck 6 · Section C), from data/ship/aquila_medbay.json.

  SM_MED_Ward            the ward: clean pale deck and walls, the forward wall with the lift, the duty desk and the
                         supply wall by the entrance, the bays of the twelve beds (pilasters, curtain tracks, pleated
                         curtains drawn between the beds and gathered at the aisle), the central console, the glass
                         partition of the theatre, and in the theatre the operating table under its lamps, the
                         diagnostic scanner, the anaesthesia cart, the instrument trolleys and the cabinets
  SM_MED_Glass           the theatre's glass partition (translucent: not Nanite)
  SM_MED_Bed             one bed: chassis, the backrest raised 20 degrees, mattress and pillow, rails, the headwall on
                         the wall behind it with its monitor on an arm (standby screen) and a drip stand; origin = the
                         floor under the backrest's hinge, +X towards the head of the bed (placed twelve times)
  SM_MED_Blanket         a patient's blanket, shaped over a body lying on the bed (patient frame: origin at the hinge
                         on the mattress top, +X towards the head)
  SM_MED_BlanketFolded   an empty bed's blanket folded at the foot (patient frame)
  SM_MED_Vitals          the monitor's live face over the standby screen (patient frame)

Coordinates are Unreal's (X forward, Y starboard, Z up); U() flips Y for Blender (the FBX import mirrors it back).
blender -b --factory-startup --python-exit-code 1 -P art/blender/medbay.py -- art/export/medbay
"""
from __future__ import annotations

import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import hullkit as K  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_medbay.json"), encoding="utf-8"))
LEN, HW, HGT = D["length"], D["half_width"], D["height"]
T = 0.3
BEDS = D["beds"]
HINGE_Y = BEDS["hinge_y"]                 # the backrest's hinge, |y| on the ward
MAT_TOP = BEDS["mattress_top"]
RECLINE = math.radians(BEDS["recline_deg"])

WALL = "MI_MED_Wall"
FLOOR = "MI_MED_Floor"
LINEN = "MI_MED_Linen"
BLANKET = "MI_MED_Blanket"
CURTAIN = "MI_MED_Curtain"
PLASTIC = "MI_MED_Plastic"
RED = "MI_MED_Red"
CROSS = "MI_MED_Cross"
STANDBY = "MI_MED_ScreenStandby"
VITALS = "MI_MED_Vitals"
WARD = "MI_MED_Ward"
SCAN = "MI_MED_Scan"

# the monitor over each bed (bed frame): centre, facing (UE yaw, towards the foot of the bed and the aisle), size
MON_C = (1.08, 0.6, 1.74)
MON_YAW = -168.0
MON_W, MON_H = 0.52, 0.325


def U(x, y, z):
    return (x, -y, z)


GLASS_BOXES: list[tuple] = []   # glass inside the ward (cabinet fronts, the mirror): built into SM_MED_Glass


def box(b, x0, x1, y0, y1, z0, z1, mat):
    if mat == A.MAT_GLASS and getattr(b, "defer_glass", False):
        GLASS_BOXES.append((x0, x1, y0, y1, z0, z1))
        return
    lo = U(min(x0, x1), max(y0, y1), min(z0, z1))
    hi = U(max(x0, x1), min(y0, y1), max(z0, z1))
    b.box_minmax(lo, hi, mat)


def cyl(b, p0, p1, r, mat, seg=16, r2=None):
    b.cylinder(U(*p0), U(*p1), r, mat, segments=seg, radius2=r2)


def place(x, y, z, yaw_deg=0.0, pitch_deg=0.0):
    """A part's frame in Blender space from an Unreal position, yaw (X towards Y) and pitch (X towards Z)."""
    return (Matrix.Translation(U(x, y, z)) @ Matrix.Rotation(math.radians(-yaw_deg), 4, "Z")
            @ Matrix.Rotation(math.radians(-pitch_deg), 4, "Y"))


def screen(b, x, y, z, yaw_deg, w, h, mat, pitch_deg=0.0, depth=0.004):
    """A UI face (w x h m) looking along the Unreal yaw, its texture upright and readable."""
    b.screen(place(x, y, z, yaw_deg, pitch_deg) @ Matrix.Diagonal((depth, w, h, 1.0)), mat)


def blob(b, c, size, mat, e=0.45, ez=0.8, yaw_deg=0.0, pitch_deg=0.0, seg=(24, 12)):
    """A puffy superellipsoid (pillows, bags): boxy in plan (e < 1), rounded top and bottom (ez)."""
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=seg[0], v_segments=seg[1], radius=1.0)

    def sp(v, ex):
        return math.copysign(abs(v) ** ex, v)
    m = place(*c, yaw_deg, pitch_deg)
    idx = b.mi(mat)
    vmap = {}
    for v in tmp.verts:
        x, y, z = v.co
        local = Vector((sp(x, e) * size[0] / 2, sp(y, e) * size[1] / 2, sp(z, ez) * size[2] / 2))
        vmap[v] = b.bm.verts.new(m @ local)
    for f in tmp.faces:
        nf = b.bm.faces.new([vmap[v] for v in f.verts])
        nf.material_index = idx
    tmp.free()


def shell(b, outer, inner, mat):
    """A thin soft shell between two grids of points (sections x points, Unreal coordinates): the outer and inner
    surfaces, their rims and end caps; normals made consistent."""
    K_, N_ = len(outer), len(outer[0])
    O = [[b.bm.verts.new(U(*p)) for p in row] for row in outer]
    I = [[b.bm.verts.new(U(*p)) for p in row] for row in inner]
    faces = []
    for k in range(K_ - 1):
        for i in range(N_ - 1):
            faces.append(b.bm.faces.new((O[k][i], O[k][i + 1], O[k + 1][i + 1], O[k + 1][i])))
            faces.append(b.bm.faces.new((I[k][i], I[k + 1][i], I[k + 1][i + 1], I[k][i + 1])))
        faces.append(b.bm.faces.new((O[k][0], O[k + 1][0], I[k + 1][0], I[k][0])))
        faces.append(b.bm.faces.new((O[k][-1], I[k][-1], I[k + 1][-1], O[k + 1][-1])))
    for i in range(N_ - 1):
        faces.append(b.bm.faces.new((O[0][i], I[0][i], I[0][i + 1], O[0][i + 1])))
        faces.append(b.bm.faces.new((O[-1][i], O[-1][i + 1], I[-1][i + 1], I[-1][i])))
    idx = b.mi(mat)
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(b.bm, faces=faces)


def soft(obj, texel=0.6, angle=70.0):
    """Fabric: smooth shading, world-scale UVs (the cloth textures tile at texel metres)."""
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    A.box_uv(obj, texel_m=texel)
    return obj


# ------------------------------------------------------------------------------------------------ curtains
def curtain(b, p0, p1, z0, z1, amp=0.045, wave=0.26, thick=0.008, flare=1.25):
    """A pleated curtain hanging straight from a track between two points (plan), from z1 down to z0."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy)
    tx, ty = dx / L, dy / L
    nx, ny = -ty, tx
    n = max(8, int(L / wave * 8))
    rows = 6
    outer, inner = [], []
    for r in range(rows + 1):
        z = z0 + (z1 - z0) * r / rows
        a = amp * (flare - (flare - 1.0) * r / rows)       # the pleats open a little towards the hem
        o, i_ = [], []
        for k in range(n + 1):
            s = L * k / n
            off = a * math.sin(2 * math.pi * s / wave)
            x, y = p0[0] + tx * s + nx * off, p0[1] + ty * s + ny * off
            o.append((x, y, z))
            i_.append((x - nx * thick, y - ny * thick, z))
        outer.append(o)
        inner.append(i_)
    shell(b, outer, inner, CURTAIN)


def track(b, p0, p1, z):
    """A ceiling curtain track with its drop rods."""
    x0, y0 = p0
    x1, y1 = p1
    L = math.hypot(x1 - x0, y1 - y0)
    cyl(b, (x0, y0, z), (x1, y1, z), 0.018, A.MAT_TRIM, seg=8)
    for k in range(int(L / 1.4) + 1):
        f = min(1.0, k * 1.4 / L) if L > 0 else 0.0
        x, y = x0 + (x1 - x0) * f, y0 + (y1 - y0) * f
        cyl(b, (x, y, z), (x, y, HGT), 0.008, A.MAT_TRIM, seg=6)


# ------------------------------------------------------------------------------------------------ the ward
def ward():
    b = A.Builder()
    b.defer_glass = True
    GLASS_BOXES.clear()
    hx = BEDS["x"]
    # --- the deck: a pale resin floor, a coved skirting, a guide line down the aisle from the lift to the theatre
    box(b, -LEN, 0, -HW, HW, -0.25, 0.0, FLOOR)
    for side in (-1, 1):
        box(b, -LEN, 0, side * (HW - 0.05), side * HW, 0.0, 0.14, PLASTIC)
    box(b, -LEN, -LEN + 0.05, -HW, HW, 0.0, 0.14, PLASTIC)
    box(b, -23.6, -0.6, -0.04, 0.04, 0.0, 0.004, A.MAT_ACCENT)
    # --- the side walls: panels, pilasters between the bays, the bumper rail, a cove of light near the ceiling
    for side in (-1, 1):
        yw = side * HW
        box(b, -LEN, 0, yw, yw + side * T, 0, HGT, WALL)
        for k in range(8):
            x = -5.3 - 3.0 * k
            box(b, x - 0.16, x + 0.16, yw - side * 0.22, yw, 0, HGT, WALL)
            box(b, x - 0.06, x + 0.06, yw - side * 0.2, yw - side * 0.26, 1.15, 1.33, PLASTIC)     # sanitiser
            box(b, x - 0.03, x + 0.03, yw - side * 0.26, yw - side * 0.27, 1.18, 1.22, A.MAT_ACCENT)
        for x0, x1 in ((-5.2, -0.4), (-29.7, -24.0)):
            box(b, x0, x1, yw - side * 0.08, yw, 0.86, 0.96, PLASTIC)                           # the bumper rail
        box(b, -LEN + 0.3, -0.3, yw - side * 0.35, yw, 3.2, 3.28, WALL)                         # the cove's lip
        box(b, -LEN + 0.3, -0.3, yw - side * 0.06, yw - side * 0.02, 3.3, 3.5, A.MAT_LIGHT)      # its light
    box(b, -LEN - T, -LEN, -HW, HW, 0, HGT, WALL)                                               # the aft wall
    # --- the forward wall with the lift (as in Main Engineering)
    lift = D["lift"]
    ly, lw, lh = lift["y"], lift["width"], lift["height"]
    box(b, 0, T, -HW, ly - lw / 2, 0, HGT, WALL)
    box(b, 0, T, ly + lw / 2, HW, 0, HGT, WALL)
    box(b, 0, T, ly - lw / 2, ly + lw / 2, lh, HGT, WALL)
    for (a0, a1, c0, c1) in ((ly - lw / 2 - 0.4, ly - lw / 2, 0, lh + 0.4), (ly + lw / 2, ly + lw / 2 + 0.4, 0, lh + 0.4),
                             (ly - lw / 2, ly + lw / 2, lh, lh + 0.4)):
        box(b, -0.1, 0.6, a0, a1, c0, c1, A.MAT_TRIM)
    box(b, 0.5, 3.8, ly - 2.0, ly + 2.0, -0.1, 0.0, A.MAT_FLOOR)
    box(b, 3.4, 3.8, ly - 2.0, ly + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly - 2.0, ly - 1.6, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly + 1.6, ly + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly - 2.0, ly + 2.0, 3.6, 3.9, A.MAT_STRUCTURE)
    # the ward board on the forward wall, to starboard of the lift, and the medical cross above the duty desk
    box(b, -0.06, 0.0, 2.6, 7.4, 1.35, 2.95, A.MAT_RUBBER)
    screen(b, -0.07, 5.0, 2.15, 180.0, 4.6, 1.44, WARD)
    for (a0, a1, c0, c1) in ((-0.45, 0.45, -0.14, 0.14), (-0.14, 0.14, -0.45, 0.45)):
        box(b, -0.05, 0.0, 5.0 + a0, 5.0 + a1, 3.55 + c0, 3.55 + c1, CROSS)
    # the hand-wash station by the lift (port)
    box(b, -0.7, 0.0, -4.6, -2.4, 0.0, 0.88, PLASTIC)
    box(b, -0.75, 0.0, -4.65, -2.35, 0.88, 0.92, A.MAT_TRIM)
    box(b, -0.55, -0.1, -4.0, -3.0, 0.8, 0.9, A.MAT_STRUCTURE)
    cyl(b, (-0.05, -3.5, 1.15), (-0.3, -3.5, 1.15), 0.02, A.MAT_TRIM, seg=8)
    box(b, -0.08, 0.0, -4.55, -2.45, 1.3, 2.3, A.MAT_GLASS)                                     # a mirror, dark
    # --- the supply wall (port, by the entrance): tall cabinets, drawers below, a glass-fronted upper half
    sw = D["supply_wall"]
    yw = sw["side"] * HW
    for k in range(4):
        x0 = sw["x0"] - k * 1.0
        box(b, x0 - 0.97, x0, yw - sw["side"] * 0.62, yw, 0.0, 2.3, PLASTIC)
        for r in range(4):
            box(b, x0 - 0.92, x0 - 0.05, yw - sw["side"] * 0.64, yw - sw["side"] * 0.62, 0.1 + r * 0.26, 0.32 + r * 0.26, WALL)
            box(b, x0 - 0.6, x0 - 0.37, yw - sw["side"] * 0.66, yw - sw["side"] * 0.64, 0.25 + r * 0.26, 0.28 + r * 0.26, A.MAT_TRIM)
        box(b, x0 - 0.92, x0 - 0.05, yw - sw["side"] * 0.64, yw - sw["side"] * 0.62, 1.2, 2.2, A.MAT_GLASS)
        for r in range(3):
            box(b, x0 - 0.92, x0 - 0.05, yw - sw["side"] * 0.6, yw - sw["side"] * 0.2, 1.4 + r * 0.3, 1.42 + r * 0.3, A.MAT_TRIM)
            for q in range(5):   # boxes of supplies on the shelves
                box(b, x0 - 0.88 + q * 0.17, x0 - 0.75 + q * 0.17, yw - sw["side"] * 0.55, yw - sw["side"] * 0.3,
                    1.42 + r * 0.3, 1.55 + r * 0.3 + 0.05 * (q % 2), LINEN if (q + r) % 3 else CROSS)
    # --- the duty desk (starboard, by the entrance): a counter towards the aisle, the desk behind it, two screens
    dd = D["duty_desk"]
    x0, x1 = dd["x"] - dd["length"] / 2, dd["x"] + dd["length"] / 2
    y0 = dd["y"] - dd["depth"] / 2
    box(b, x0, x1, y0, y0 + 0.16, 0.0, 1.12, PLASTIC)
    box(b, x0 - 0.05, x1 + 0.05, y0 - 0.06, y0 + 0.2, 1.12, 1.16, A.MAT_TRIM)
    box(b, x0, x1, y0 + 0.16, y0 + dd["depth"], 0.0, 0.74, WALL)
    box(b, x0, x1, y0 + 0.16, y0 + dd["depth"] + 0.05, 0.74, 0.78, PLASTIC)
    box(b, x0, x1, y0 - 0.005, y0, 0.3, 0.34, A.MAT_ACCENT)
    for k, xs in enumerate((dd["x"] - 0.9, dd["x"] + 0.9)):
        box(b, xs - 0.3, xs + 0.3, y0 + 0.38, y0 + 0.42, 0.9, 1.3, A.MAT_RUBBER)
        cyl(b, (xs, y0 + 0.45, 0.78), (xs, y0 + 0.45, 0.95), 0.025, A.MAT_TRIM, seg=8)
        screen(b, xs, y0 + 0.425, 1.1, 90.0, 0.56, 0.35, WARD if k else VITALS)
    box(b, -5.6, -1.4, HW - 0.5, HW, 0.0, 2.1, PLASTIC)                                          # records and linen
    box(b, -5.55, -1.45, HW - 0.52, HW - 0.5, 0.1, 2.0, WALL)
    # --- the bays: curtain tracks and the curtains (drawn between the beds, gathered at the aisle)
    xs = [-5.3 - 3.0 * k for k in range(7)]
    for side in (-1, 1):
        for k, xd in enumerate(xs):
            track(b, (xd, side * (HW - 0.3)), (xd, side * 6.05), 2.45)
            if 0 < k < 6:
                curtain(b, (xd, side * (HW - 0.28)), (xd, side * 6.1), 0.32, 2.42)
            else:
                curtain(b, (xd, side * (HW - 0.28)), (xd, side * (HW - 0.62)), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
            if k < 6:   # the aisle side: the curtain gathered at both corners of the bay
                curtain(b, (xd - 0.08, side * 6.05), (xd - 0.4, side * 6.05), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
                curtain(b, (xd - 2.6, side * 6.05), (xd - 2.92, side * 6.05), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
        track(b, (xs[0], side * 6.05), (xs[-1], side * 6.05), 2.45)
    # --- the central console: storage below, a double-sided sloped board on top, a terminal where the doctor stands
    cc = D["central_console"]
    cx0, cx1, chw = cc["x0"], cc["x1"], cc["half_width"]
    box(b, cx1, cx0, -chw, chw, 0.0, 0.92, PLASTIC)
    box(b, cx1 - 0.05, cx0 + 0.05, -chw - 0.05, chw + 0.05, 0.92, 0.96, A.MAT_TRIM)
    for side in (-1, 1):
        box(b, cx1 + 0.1, cx0 - 0.1, side * (chw - 0.01), side * chw, 0.12, 0.8, WALL)
        box(b, cx1 + 0.1, cx0 - 0.1, side * (chw + 0.001), side * (chw + 0.006), 0.4, 0.43, A.MAT_ACCENT)
        for k in range(3):   # the board: three screens a side, leaning back
            xm = cx0 - 1.4 - k * 2.7
            with K.part(b, place(xm, side * 0.155, 1.28, 90.0 * side, 18.0)):
                b.box((-0.025, 0, 0), (0.04, 2.5, 0.62), A.MAT_RUBBER)
            screen(b, xm, side * 0.155, 1.28, 90.0 * side, 2.42, 0.56, WARD, pitch_deg=18.0)
            cyl(b, (xm, 0, 0.96), (xm, 0, 1.05), 0.05, A.MAT_TRIM, seg=10)
    # the doctor's terminal, in front of where she stands (facing the lift): its screen towards her
    doc = next(c for c in D["crew"] if c["station"] == "doctor")
    tx_ = doc["x"] + 0.5
    box(b, tx_ + 0.02, tx_ + 0.14, doc["y"] - 0.16, doc["y"] + 0.16, 0.0, 0.98, PLASTIC)
    with K.part(b, place(tx_, doc["y"], 1.1, 180.0, 30.0)):
        b.box((-0.025, 0, 0), (0.04, 0.46, 0.32), A.MAT_RUBBER)
    screen(b, tx_ - 0.004, doc["y"], 1.1, 180.0, 0.42, 0.28, VITALS, pitch_deg=30.0)
    # --- the theatre's partition (the glass is SM_MED_Glass): posts, head, sills; the sliding door's opening
    P = D["partition"]
    px, dhw = P["x"], P["door_half_width"]
    posts = [-HW, -6.3, -3.6, -dhw, dhw, 3.6, 6.3, HW]
    for y in posts:
        box(b, px - 0.08, px + 0.08, y - 0.06, y + 0.06, 0.0, 2.7, A.MAT_TRIM)
    box(b, px - 0.12, px + 0.12, -HW, HW, 2.7, HGT, WALL)
    for y0, y1 in ((-HW, -dhw), (dhw, HW)):
        box(b, px - 0.08, px + 0.08, y0, y1, 0.0, 0.12, A.MAT_TRIM)
    for (a0, a1, c0, c1) in ((-0.3, 0.3, -0.1, 0.1), (-0.1, 0.1, -0.3, 0.3)):
        box(b, px + 0.12, px + 0.14, a0, a1, 3.3 + c0, 3.3 + c1, CROSS)
    box(b, px - 0.05, px + 0.05, -dhw - 1.25, -dhw - 0.05, 2.6, 2.7, A.MAT_TRIM)                # the door's track
    # --- the theatre
    sg = D["surgery"]
    tx, ty = sg["table"]
    cyl(b, (tx, ty, 0.0), (tx, ty, 0.1), 0.45, A.MAT_STRUCTURE, seg=24)
    box(b, tx - 0.3, tx + 0.3, ty - 0.18, ty + 0.18, 0.1, 0.78, PLASTIC)
    box(b, tx - 1.0, tx + 1.0, ty - 0.29, ty + 0.29, 0.78, 0.86, A.MAT_TRIM)
    box(b, tx - 0.98, tx + 0.98, ty - 0.27, ty + 0.27, 0.86, 0.94, A.MAT_RUBBER)
    for side in (-1, 1):   # arm boards
        box(b, tx + 0.35, tx + 0.5, ty + side * 0.29, ty + side * 0.85, 0.84, 0.9, A.MAT_RUBBER)
    # the theatre lamps: a ceiling hub, arms, two heads with their lens clusters
    hub = (tx + 0.2, ty + 0.9)
    cyl(b, (hub[0], hub[1], HGT), (hub[0], hub[1], HGT - 0.45), 0.07, PLASTIC, seg=16)
    for (hx_, hy_, hz, r) in ((tx + 0.1, ty + 0.05, 2.05, 0.38), (tx - 0.75, ty - 0.55, 2.2, 0.26)):
        cyl(b, (hub[0], hub[1], HGT - 0.4), (hx_, hy_, HGT - 0.4), 0.035, PLASTIC, seg=10)
        cyl(b, (hx_, hy_, HGT - 0.4), (hx_, hy_, hz + 0.2), 0.03, PLASTIC, seg=10)
        cyl(b, (hx_, hy_, hz + 0.02), (hx_, hy_, hz + 0.2), r, PLASTIC, seg=28, r2=r * 0.8)
        cyl(b, (hx_, hy_, hz), (hx_, hy_, hz + 0.02), r * 0.92, A.MAT_LIGHT, seg=28)
        for q in range(7):   # lenses
            a = 2 * math.pi * q / 7
            rr = r * 0.55 if q else 0.0
            cyl(b, (hx_ + math.cos(a) * rr, hy_ + math.sin(a) * rr, hz - 0.012), (hx_ + math.cos(a) * rr, hy_ + math.sin(a) * rr, hz),
                r * 0.18, A.MAT_TRIM, seg=12)
    # the anaesthesia cart at the head of the table
    ax_, ay_ = tx + 1.35, ty + 0.55
    box(b, ax_ - 0.3, ax_ + 0.3, ay_ - 0.28, ay_ + 0.28, 0.12, 1.3, PLASTIC)
    screen(b, ax_ - 0.31, ay_, 1.05, 180.0, 0.44, 0.28, VITALS)
    for q in range(3):
        cyl(b, (ax_ + 0.15, ay_ - 0.2 + q * 0.2, 1.3), (ax_ + 0.15, ay_ - 0.2 + q * 0.2, 1.55), 0.05, (A.MAT_TRIM, CROSS, A.MAT_TRIM)[q], seg=10)
    for (qx, qy) in ((-0.25, -0.23), (-0.25, 0.23), (0.25, -0.23), (0.25, 0.23)):
        cyl(b, (ax_ + qx, ay_ + qy, 0.0), (ax_ + qx, ay_ + qy, 0.12), 0.05, A.MAT_RUBBER, seg=10)
    # instrument trolleys
    for (ix, iy) in ((tx - 0.4, ty - 1.2), (tx + 0.6, ty - 1.15)):
        for zz in (0.35, 0.9):
            box(b, ix - 0.38, ix + 0.38, iy - 0.24, iy + 0.24, zz, zz + 0.025, A.MAT_TRIM)
        for (qx, qy) in ((-0.36, -0.22), (-0.36, 0.22), (0.36, -0.22), (0.36, 0.22)):
            cyl(b, (ix + qx, iy + qy, 0.05), (ix + qx, iy + qy, 0.925), 0.012, A.MAT_TRIM, seg=6)
        for q in range(5):
            box(b, ix - 0.3 + q * 0.13, ix - 0.25 + q * 0.13, iy - 0.12, iy + 0.12, 0.925, 0.935, A.MAT_TRIM)
    # the diagnostic scanner: a table through a ring, its display on a stand
    sx, sy = sg["scanner"]
    box(b, sx - 1.2, sx - 0.45, sy - 0.32, sy + 0.32, 0.0, 0.66, PLASTIC)                    # the base stops short of the ring
    box(b, sx - 1.2, sx + 1.2, sy - 0.3, sy + 0.3, 0.66, 0.7, PLASTIC)                        # the table slides through it
    box(b, sx - 1.15, sx + 1.15, sy - 0.27, sy + 0.27, 0.7, 0.78, LINEN)
    ring_r, ring_w = 1.0, 0.55
    for q in range(40):
        a0, a1 = 2 * math.pi * q / 40, 2 * math.pi * (q + 1) / 40
        for (rr, th, m) in ((ring_r, 0.22, PLASTIC), (ring_r - 0.19, 0.03, CROSS)):
            p0 = (sx, sy + math.cos(a0) * rr, 1.02 + math.sin(a0) * rr)
            p1 = (sx, sy + math.cos(a1) * rr, 1.02 + math.sin(a1) * rr)
            if p0[2] < 0.02 and p1[2] < 0.02:
                continue
            with K.part(b, Matrix.Translation(U(*[(u + v) / 2 for u, v in zip(p0, p1)]))
                        @ Matrix.Rotation(-(a0 + a1) / 2, 4, "X")):
                b.box((0, 0, 0), (ring_w if m == PLASTIC else ring_w + 0.02, th, rr * (a1 - a0) * 1.04), m)
    box(b, sx - 0.4, sx + 0.4, sy - 0.9, sy + 0.9, 0.0, 0.06, PLASTIC)
    stand = (sx + 1.6, sy - 2.3)
    cyl(b, (stand[0], stand[1], 0.0), (stand[0], stand[1], 1.2), 0.04, A.MAT_TRIM, seg=10)
    cyl(b, (stand[0], stand[1], 0.0), (stand[0], stand[1], 0.03), 0.3, A.MAT_STRUCTURE, seg=20)
    with K.part(b, place(stand[0], stand[1], 1.5, 140.0)):
        b.box((-0.03, 0, 0), (0.05, 0.86, 0.56), A.MAT_RUBBER)
    screen(b, stand[0] + math.cos(math.radians(140)) * 0.005, stand[1] + math.sin(math.radians(140)) * 0.005, 1.5, 140.0, 0.8, 0.5, SCAN)
    # the theatre's cabinets on the aft wall, its big display, the crash cart by the door
    cxw = sg["cabinets_x"]
    for k in range(10):
        y0 = -HW + 0.4 + k * 1.72
        if abs(y0 + 0.86) < 1.3:
            continue
        box(b, cxw - 0.02, -LEN, y0, y0 + 1.66, 0.0, 2.2, PLASTIC)
        box(b, cxw - 0.03, cxw - 0.02, y0 + 0.05, y0 + 1.61, 1.1, 2.1, A.MAT_GLASS)
        box(b, cxw - 0.04, cxw - 0.02, y0 + 0.05, y0 + 1.61, 0.1, 1.0, WALL)
    box(b, -LEN + 0.02, -LEN + 0.06, -1.2, 1.2, 1.3, 2.8, A.MAT_RUBBER)
    screen(b, -LEN + 0.065, 0.0, 2.05, 0.0, 2.3, 1.44, SCAN)
    box(b, -23.55, -22.95, -2.6, -1.9, 0.12, 1.05, RED)                                       # crash cart
    box(b, -23.58, -22.92, -2.63, -1.87, 1.05, 1.09, A.MAT_TRIM)
    box(b, -23.35, -23.1, -2.45, -2.05, 1.09, 1.3, A.MAT_RUBBER)
    # --- the ceiling: panels of light over the beds and the aisle, the theatre's bright field, air grilles
    box(b, -LEN, 0, -HW, HW, HGT, HGT + 0.3, WALL)
    for x in hx:
        for side in (-1, 1):
            box(b, x - 0.55, x + 0.55, side * 7.3 - 0.45, side * 7.3 + 0.45, HGT - 0.03, HGT, A.MAT_LIGHT)
    for k in range(8):
        x = -2.0 - k * 2.9
        for yy in (-3.2, 3.2):
            box(b, x - 0.6, x + 0.6, yy - 0.3, yy + 0.3, HGT - 0.03, HGT, A.MAT_LIGHT)
    box(b, tx - 1.4, tx + 1.4, ty - 1.6, ty + 1.6, HGT - 0.04, HGT, A.MAT_LIGHT)
    for (gx, gy) in ((-4.0, 0.0), (-12.0, 0.0), (-20.0, 0.0), (-27.0, -3.5), (-27.0, 3.5)):
        box(b, gx - 0.35, gx + 0.35, gy - 0.35, gy + 0.35, HGT - 0.025, HGT, A.MAT_GRATE)
    obj = b.to_object("SM_MED_Ward")
    A.finish(obj, bevel=0.012, segments=1)
    A.box_uv(obj, texel_m=2.0)
    return obj


def glass():
    b = A.Builder()
    P = D["partition"]
    px, dhw = P["x"], P["door_half_width"]
    posts = [-HW, -6.3, -3.6, -dhw, dhw, 3.6, 6.3, HW]
    for y0, y1 in zip(posts[:-1], posts[1:]):
        if y0 == -dhw:
            continue
        box(b, px - 0.012, px + 0.012, y0 + 0.06, y1 - 0.06, 0.12, 2.7, A.MAT_GLASS)
    # the sliding door, half open (towards port)
    box(b, px - 0.04, px - 0.016, -dhw - 1.2, -dhw * 0.25, 0.02, 2.6, A.MAT_GLASS)
    for g in GLASS_BOXES:   # the ward's own glass: cabinet fronts, the mirror
        box(b, *g, A.MAT_GLASS)
    obj = b.to_object("SM_MED_Glass")
    A.box_uv(obj, texel_m=2.0)
    return obj


# ------------------------------------------------------------------------------------------------ one bed
def bed():
    """Bed frame: origin on the floor under the backrest's hinge, +X towards the head (the wall is at +1.4)."""
    b = A.Builder()
    head, foot, hw = 0.95, -1.25, 0.5
    back_len = 0.92
    # chassis: base, casters, the lifting column, the platform
    box(b, -1.05, 0.78, -0.36, 0.36, 0.12, 0.26, PLASTIC)
    for (cx_, cy_) in ((-0.95, -0.3), (-0.95, 0.3), (0.68, -0.3), (0.68, 0.3)):
        cyl(b, (cx_, cy_, 0.0), (cx_, cy_, 0.12), 0.055, A.MAT_RUBBER, seg=12)
    box(b, -0.4, 0.15, -0.2, 0.2, 0.26, 0.46, A.MAT_TRIM)
    box(b, foot + 0.03, 0.0, -hw, hw, 0.44, 0.48, PLASTIC)
    with K.part(b, Matrix.Translation(U(0.0, 0.0, 0.48)) @ Matrix.Rotation(-RECLINE, 4, "Y")):
        box(b, 0.0, back_len, -hw, hw, -0.04, 0.0, PLASTIC)
    # the mattress: the leg section flat, the back section along the backrest (the hinge on its top face at z MAT_TOP)
    th = MAT_TOP - 0.48
    box(b, foot + 0.04, 0.0, -0.47, 0.47, 0.48, MAT_TOP, LINEN)
    with K.part(b, Matrix.Translation(U(0.0, 0.0, MAT_TOP)) @ Matrix.Rotation(-RECLINE, 4, "Y")):
        box(b, 0.0, back_len - 0.02, -0.47, 0.47, -th, 0.0, LINEN)
    # side rails on the leg section, raised
    for side in (-1, 1):
        y = side * 0.52
        for (xa, xb) in ((-0.95, -0.2),):
            cyl(b, (xa, y, 0.9), (xb, y, 0.9), 0.016, A.MAT_TRIM, seg=8)
            cyl(b, (xa, y, 0.72), (xb, y, 0.72), 0.012, A.MAT_TRIM, seg=8)
            for xx in (xa, (xa + xb) / 2, xb):
                cyl(b, (xx, y, 0.5), (xx, y, 0.9), 0.014, A.MAT_TRIM, seg=8)
    # head- and footboards
    box(b, head - 0.04, head, -hw, hw, 0.44, 1.12, PLASTIC)
    box(b, head - 0.045, head - 0.04, -hw + 0.06, hw - 0.06, 0.95, 1.05, A.MAT_ACCENT)
    box(b, foot, foot + 0.04, -hw, hw, 0.44, 0.98, PLASTIC)
    box(b, foot - 0.02, foot, -0.18, 0.18, 0.72, 0.94, A.MAT_RUBBER)                              # the chart
    # the pillow on the backrest
    d = 0.7
    blob(b, (d * math.cos(RECLINE) - 0.06 * math.sin(RECLINE), 0.0, MAT_TOP + d * math.sin(RECLINE) + 0.06 * math.cos(RECLINE)),
         (0.34, 0.62, 0.13), LINEN, pitch_deg=math.degrees(RECLINE) + 8.0)
    # the headwall on the wall behind the bed: services, reading light, the monitor on its arm
    wx = head + 0.45
    box(b, wx - 0.07, wx, -0.85, 0.85, 0.8, 2.12, PLASTIC)
    box(b, wx - 0.08, wx - 0.07, -0.8, 0.8, 2.04, 2.1, A.MAT_LIGHT)
    box(b, wx - 0.08, wx - 0.07, -0.8, 0.8, 0.84, 0.87, A.MAT_ACCENT)
    for q, m in enumerate((A.MAT_TRIM, CROSS, A.MAT_TRIM, RED)):
        cyl(b, (wx - 0.07, -0.62 + q * 0.14, 1.32), (wx - 0.11, -0.62 + q * 0.14, 1.32), 0.028, m, seg=10)
    mx, my, mz = MON_C
    cyl(b, (wx - 0.07, my, mz), (mx + 0.05, my, mz), 0.022, A.MAT_TRIM, seg=8)
    with K.part(b, place(mx, my, mz, MON_YAW)):
        b.box((-0.03, 0, 0), (0.05, MON_W + 0.05, MON_H + 0.05), A.MAT_RUBBER)
    fx, fy = math.cos(math.radians(MON_YAW)), math.sin(math.radians(MON_YAW))
    screen(b, mx + fx * 0.0045, my + fy * 0.0045, mz, MON_YAW, MON_W, MON_H, STANDBY)
    # the drip stand at the head
    px_, py_ = 0.78, -0.66
    cyl(b, (px_, py_, 0.06), (px_, py_, 2.05), 0.012, A.MAT_TRIM, seg=8)
    cyl(b, (px_ - 0.14, py_, 2.0), (px_ + 0.14, py_, 2.0), 0.008, A.MAT_TRIM, seg=6)
    for q in range(5):
        a = 2 * math.pi * q / 5
        cyl(b, (px_, py_, 0.06), (px_ + math.cos(a) * 0.26, py_ + math.sin(a) * 0.26, 0.05), 0.012, A.MAT_TRIM, seg=6)
        cyl(b, (px_ + math.cos(a) * 0.26, py_ + math.sin(a) * 0.26, 0.0), (px_ + math.cos(a) * 0.26, py_ + math.sin(a) * 0.26, 0.05), 0.022, A.MAT_RUBBER, seg=8)
    blob(b, (px_ + 0.1, py_, 1.84), (0.04, 0.12, 0.2), LINEN, e=0.6, ez=0.6)
    obj = b.to_object("SM_MED_Bed")
    A.finish(obj, bevel=0.008, segments=1)
    bpy.context.view_layer.objects.active = obj
    A.box_uv(obj, texel_m=0.7)
    return obj


# ------------------------------------------------------------------------------------------------ the patient's things
def _interp(tab, s):
    if s <= tab[0][0]:
        return tab[0][1]
    for (s0, v0), (s1, v1) in zip(tab, tab[1:]):
        if s <= s1:
            f = (s - s0) / (s1 - s0)
            f = f * f * (3 - 2 * f)
            return v0 + (v1 - v0) * f
    return tab[-1][1]


# the body under the blanket, measured on the mannequins lying in the bed (pelvis 10 cm off the mattress, thighs 18 cm
# thick, the toes up to 26 cm at s -1.05): heights of the blanket's top over the mattress, and the half-width of the bump
BODY_H = [(-1.22, 0.05), (-1.18, 0.2), (-1.13, 0.3), (-1.07, 0.32), (-1.0, 0.26), (-0.92, 0.22), (-0.85, 0.21), (-0.6, 0.22),
          (-0.35, 0.23), (-0.12, 0.25), (0.05, 0.25), (0.14, 0.24)]
BODY_W = [(-1.22, 0.34), (-1.04, 0.33), (-0.6, 0.32), (-0.2, 0.33), (0.14, 0.33)]
FEET_S = -1.08


def _bump(t):
    """Across the body: a broad, flat-topped rise (the blanket rests on both legs, not on a ridge)."""
    t = min(1.0, abs(t))
    return (1.0 - t * t) ** 0.7


def _section(s, lift=0.0):
    """The blanket's cross-section at s along the bed (patient frame): points and their outward normals (2-D, in the
    plane across the bed: (c, h)) — over the body, then down the mattress's sides."""
    base = 0.025 + lift
    h_body = _interp(BODY_H, s)
    w_body = _interp(BODY_W, s)
    feet = max(0.0, 1.0 - abs(s - FEET_S) / 0.1)
    pts = []
    n = 34
    for i in range(n + 1):
        c = -0.47 + 0.94 * i / n
        one = _bump(c / w_body)
        two = max(_bump((c - 0.1) / 0.1), _bump((c + 0.1) / 0.1))
        h = base + h_body * ((1 - feet) * one + feet * two)
        h += 0.005 * math.sin(19 * s + 5 * c) * math.sin(13 * c + 2 * s)       # the weave of the folds
        pts.append((c, h))
    for side in (-1, 1):
        drape = [(0.49, base - 0.02), (0.505, base - 0.07), (0.515, base - 0.14), (0.52, base - 0.22)]
        ext = [(side * c, h) for c, h in drape]
        pts = (list(reversed(ext)) + pts) if side < 0 else (pts + ext)
    # 2-D normals from the polyline (outwards: up over the top, sideways down the drape)
    nrm = []
    for i in range(len(pts)):
        a = pts[max(0, i - 1)]
        b_ = pts[min(len(pts) - 1, i + 1)]
        tx, th = b_[0] - a[0], b_[1] - a[1]
        L = math.hypot(tx, th) or 1.0
        nrm.append((-th / L, tx / L))
    return pts, nrm


def _to_frame(s, c, h):
    """Patient frame: s along the bed (the backrest from s = 0 up, tilted by the recline), c across, h off the mattress."""
    if s <= 0.0:
        return (s, c, h)
    return (s * math.cos(RECLINE) - h * math.sin(RECLINE), c, s * math.sin(RECLINE) + h * math.cos(RECLINE))


def blanket():
    b = A.Builder()
    thick = 0.012
    # up to the waist (the arms and the gown above it), the sheet folded over its edge
    for (s0, s1, lift, mat, steps) in ((-1.22, 0.1, 0.0, BLANKET, 60), (0.02, 0.14, 0.014, LINEN, 6)):
        outer, inner = [], []
        for k in range(steps + 1):
            s = s0 + (s1 - s0) * k / steps
            pts, nrm = _section(s, lift)
            outer.append([_to_frame(s, c, h) for c, h in pts])
            inner.append([_to_frame(s, c - nc * thick, h - nh * thick) for (c, h), (nc, nh) in zip(pts, nrm)])
        shell(b, outer, inner, mat)
    obj = b.to_object("SM_MED_Blanket")
    return soft(obj, texel=0.5)


def folded():
    b = A.Builder()
    blob(b, (-1.0, 0.0, 0.045), (0.36, 0.86, 0.09), BLANKET, e=0.3, ez=0.5)
    blob(b, (-1.0, 0.0, 0.1), (0.3, 0.8, 0.035), BLANKET, e=0.3, ez=0.5)
    obj = b.to_object("SM_MED_BlanketFolded")
    return soft(obj, texel=0.5, angle=60.0)


def vitals():
    b = A.Builder()
    mx, my, mz = MON_C
    fx, fy = math.cos(math.radians(MON_YAW)), math.sin(math.radians(MON_YAW))
    screen(b, mx + fx * 0.008, my + fy * 0.008, mz - MAT_TOP, MON_YAW, MON_W - 0.004, MON_H - 0.004, VITALS)
    return b.to_object("SM_MED_Vitals")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/medbay"
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    report = []
    for fn in (ward, glass, bed, blanket, folded, vitals):
        A.clear_objects()
        obj = fn()
        A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    print("MEDBAY_OK", json.dumps(report))


if __name__ == "__main__":
    main()
