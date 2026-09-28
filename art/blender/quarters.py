"""ASN Aquila — the Captain's quarters (Deck 1 · Section A), from data/ship/aquila_quarters.json.

  SM_QTR_Room                       the cabin: a navy carpet, dark wood wainscot and furniture, warm pale walls, a
                                    coffered ceiling with downlights; the desk under the great aft window with its
                                    terminal (the Captain's log) and lamp, the Captain's chair and two for visitors;
                                    a sofa, a low table and an armchair; the bunk in its alcove with a reading light and
                                    a shelf; a bookcase; a galley corner with the coffee machine; a sideboard under the
                                    starboard window (the Aquila's model stands on it, placed in Unreal); the sector
                                    chart on the forward wall
  SM_QTR_Glass                      the windows (translucent: not Nanite)
  SM_SHIP_ASTRA_AquilaBridgeBlock   outside: the cabin's hull-plated block on its pedestal, overhanging the island's
                                    aft slope; the housing of the bridge lift beside it; the fairings under the two
                                    corridors behind the bridge (they floated over the island)

Everything is in the cabin's frame (world_origin in the data); coordinates are Unreal's, U() flips Y for Blender.
blender -b --factory-startup --python-exit-code 1 -P art/blender/quarters.py -- art/export/quarters
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import hullkit as K  # noqa: E402
from medbay import U, blob, box, cyl, place, screen  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_quarters.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
OX, OY, OZ = D["world_origin"]
FIN = 0.05            # interior finish
EXT = 0.35            # the outer skin
WOOD = "MI_QTR_Wood"
WALL = "MI_QTR_Wall"
CARPET = "MI_QTR_Carpet"
LEATHER = A.MAT_LEATHER
LINEN = "MI_MED_Linen"
BLANKET = "MI_MED_Blanket"
MAP = "MI_QTR_Map"
LOG = "MI_QTR_Log"
PLATE, FRAME, LIGHTS = "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Lights"
BOOKS = [LEATHER, "MI_MED_Red", BLANKET, LINEN, WOOD]


def L(x, y, z):
    """World (bridge frame) to the cabin's frame."""
    return x - OX, y - OY, z - OZ


def wall_with_holes(b, axis, pos0, pos1, u0, u1, z0, z1, holes, mat):
    """A wall slab: axis 'x' = the slab spans y (u) at x in [pos0, pos1]; 'y' = it spans x (u) at y in [pos0, pos1].
    holes: (u0, u1, z0, z1) rectangles left open (doors, windows)."""
    cuts_u = sorted({u0, u1, *[h[0] for h in holes], *[h[1] for h in holes]})
    for ua, ub in zip(cuts_u, cuts_u[1:]):
        zs = [(z0, z1)]
        for hu0, hu1, hz0, hz1 in holes:
            if hu0 <= ua and ub <= hu1:
                zs = [(z0, hz0), (hz1, z1)]
        for za, zb in zs:
            if zb - za < 1e-3:
                continue
            if axis == "x":
                box(b, pos0, pos1, ua, ub, za, zb, mat)
            else:
                box(b, ua, ub, pos0, pos1, za, zb, mat)


# ------------------------------------------------------------------------------------------------ the cabin
def room():
    b = A.Builder()
    door = D["door"]
    wa, ws = D["window_aft"], D["window_side"]
    # floor: carpet on the structure; wood skirting
    box(b, -LEN, 0, -HW, HW, -0.3, -0.02, A.MAT_STRUCTURE)
    box(b, -LEN, 0, -HW, HW, -0.02, 0.0, CARPET)
    # the walls' finish: dark wood wainscot to 1 m under a rail, warm panels above (openings left for the door and windows)
    fwd_holes = [(door["y"] - door["width"] / 2, door["y"] + door["width"] / 2, 0.0, door["height"])]
    aft_holes = [(wa["y0"], wa["y1"], wa["z0"], wa["z1"])]
    stb_holes = [(ws["x0"], ws["x1"], ws["z0"], ws["z1"])]
    for (axis, p0, p1, u0, u1, holes) in (("x", -FIN, 0.0, -HW, HW, fwd_holes), ("x", -LEN, -LEN + FIN, -HW, HW, aft_holes),
                                          ("y", -HW, -HW + FIN, -LEN, 0.0, []), ("y", HW - FIN, HW, -LEN, 0.0, stb_holes)):
        wall_with_holes(b, axis, p0, p1, u0, u1, 0.0, 1.0, holes, WOOD)
        wall_with_holes(b, axis, p0, p1, u0, u1, 1.0, H, holes, WALL)
    # the structural layer behind the finish (the exterior skin is SM_SHIP_...; this closes the cabin on its own)
    wall_with_holes(b, "x", 0.0, 0.3, -HW - 0.05, HW + 0.05, -0.3, H + 0.05, fwd_holes, A.MAT_STRUCTURE)
    # rails, skirting, the door's frame
    # the wainscot's rail stops at the door and the windows; the skirting runs along the side walls
    for (x0, x1) in ((-LEN + FIN, ws["x0"] - 0.12), (ws["x1"] + 0.12, -FIN)):
        box(b, x0, x1, HW - FIN - 0.04, HW - FIN, 0.98, 1.04, WOOD)
    box(b, -LEN + FIN, -FIN, -HW + FIN, -HW + FIN + 0.04, 0.98, 1.04, WOOD)
    for (y0, y1) in ((-HW + FIN, -HW + FIN + 0.04), (HW - FIN - 0.04, HW - FIN)):
        box(b, -LEN + FIN, -FIN, y0, y1, 0.0, 0.1, WOOD)
    dgap = door["width"] / 2 + 0.14
    for (y0, y1) in ((-HW + FIN, door["y"] - dgap), (door["y"] + dgap, HW - FIN)):
        box(b, -FIN - 0.04, -FIN, y0, y1, 0.98, 1.04, WOOD)
    for (y0, y1) in ((-HW + FIN, wa["y0"] - 0.12), (wa["y1"] + 0.12, HW - FIN)):
        box(b, -LEN + FIN, -LEN + FIN + 0.04, y0, y1, 0.98, 1.04, WOOD)
    dy0, dy1 = door["y"] - door["width"] / 2, door["y"] + door["width"] / 2
    for (y0, y1, z0, z1) in ((dy0 - 0.12, dy0, 0.0, door["height"] + 0.12), (dy1, dy1 + 0.12, 0.0, door["height"] + 0.12),
                             (dy0, dy1, door["height"], door["height"] + 0.12)):
        box(b, -0.1, 0.3, y0, y1, z0, z1, A.MAT_TRIM)
    # the windows' frames (the glass is SM_QTR_Glass): the aft window with its mullions, the starboard window
    x = -LEN
    for (y0, y1, z0, z1) in ((wa["y0"] - 0.1, wa["y0"], wa["z0"], wa["z1"]), (wa["y1"], wa["y1"] + 0.1, wa["z0"], wa["z1"]),
                             (wa["y0"] - 0.1, wa["y1"] + 0.1, wa["z1"], wa["z1"] + 0.1)):
        box(b, x - 0.35, x + 0.08, y0, y1, z0, z1, A.MAT_STRUCTURE)
    box(b, x - 0.35, x + 0.3, wa["y0"] - 0.1, wa["y1"] + 0.1, wa["z0"] - 0.06, wa["z0"], WOOD)       # a deep wooden sill
    for my in wa["mullions"]:
        box(b, x - 0.35, x + 0.05, my - 0.06, my + 0.06, wa["z0"], wa["z1"], A.MAT_STRUCTURE)
    for (x0, x1, z0, z1) in ((ws["x0"] - 0.1, ws["x0"], ws["z0"], ws["z1"]), (ws["x1"], ws["x1"] + 0.1, ws["z0"], ws["z1"]),
                             (ws["x0"] - 0.1, ws["x1"] + 0.1, ws["z1"], ws["z1"] + 0.1), (ws["x0"] - 0.1, ws["x1"] + 0.1, ws["z0"] - 0.06, ws["z0"])):
        box(b, x0, x1, HW - 0.08, HW + 0.35, z0, z1, A.MAT_STRUCTURE if z1 > ws["z0"] + 0.01 else WOOD)
    # the ceiling: panels, a wooden coffer with a cove of light, downlights
    box(b, -LEN, 0, -HW, HW, H, H + 0.05, WALL)
    cx0, cx1, cy0, cy1 = -LEN + 1.2, -1.2, -HW + 1.0, HW - 1.0
    for (x0, x1, y0, y1) in ((cx0, cx1, cy0, cy0 + 0.25), (cx0, cx1, cy1 - 0.25, cy1), (cx0, cx0 + 0.25, cy0, cy1), (cx1 - 0.25, cx1, cy0, cy1)):
        box(b, x0, x1, y0, y1, H - 0.22, H, WOOD)
    for (x0, x1, y0, y1) in ((cx0 + 0.25, cx1 - 0.25, cy0 + 0.25, cy0 + 0.29), (cx0 + 0.25, cx1 - 0.25, cy1 - 0.29, cy1 - 0.25)):
        box(b, x0, x1, y0, y1, H - 0.2, H - 0.16, A.MAT_LIGHT)
    for (lx, ly) in ((-1.6, -2.2), (-1.6, 2.2), (-4.3, -3.6), (-4.3, 3.6), (-7.2, -3.6), (-7.2, 2.4), (-1.7, 0.0)):
        cyl(b, (lx, ly, H - 0.012), (lx, ly, H), 0.07, A.MAT_LIGHT, seg=16)
        cyl(b, (lx, ly, H - 0.02), (lx, ly, H - 0.012), 0.085, A.MAT_TRIM, seg=16)
    # --- the desk under the aft window, facing the door; the Captain's chair behind it, two chairs before it
    dk = D["desk"]
    dx0, dx1 = dk["x"] - dk["depth"] / 2, dk["x"] + dk["depth"] / 2
    dy0, dy1 = dk["y"] - dk["width"] / 2, dk["y"] + dk["width"] / 2
    box(b, dx0, dx1, dy0, dy1, 0.72, 0.76, WOOD)
    for (y0, y1) in ((dy0 + 0.05, dy0 + 0.55), (dy1 - 0.55, dy1 - 0.05)):
        box(b, dx0 + 0.05, dx1 - 0.05, y0, y1, 0.0, 0.72, WOOD)
        for k in range(3):
            box(b, dx1 - 0.05, dx1 - 0.03, y0 + 0.18, y1 - 0.18, 0.18 + k * 0.2, 0.2 + k * 0.2, A.MAT_TRIM)
    box(b, dx1 - 0.06, dx1 - 0.03, dy0 + 0.55, dy1 - 0.55, 0.25, 0.72, WOOD)
    # the terminal (the Captain's log), a lamp, a mug, a data pad
    tx = dx0 + 0.3
    cyl(b, (tx, dk["y"], 0.76), (tx, dk["y"], 0.95), 0.02, A.MAT_TRIM, seg=8)
    box(b, tx - 0.12, tx + 0.12, dk["y"] - 0.12, dk["y"] + 0.12, 0.76, 0.775, A.MAT_TRIM)
    with K.part(b, place(tx, dk["y"], 1.08, 180.0, 15.0)):
        b.box((-0.025, 0, 0), (0.035, 0.66, 0.43), A.MAT_RUBBER)
    screen(b, tx - 0.004, dk["y"], 1.08, 180.0, 0.62, 0.39, LOG, pitch_deg=15.0)
    lx, ly = dx0 + 0.25, dy1 - 0.2
    cyl(b, (lx, ly, 0.76), (lx, ly, 0.78), 0.08, A.MAT_TRIM, seg=16)
    cyl(b, (lx, ly, 0.78), (lx + 0.05, ly - 0.05, 1.18), 0.012, A.MAT_TRIM, seg=8)
    cyl(b, (lx + 0.12, ly - 0.12, 1.12), (lx + 0.05, ly - 0.05, 1.2), 0.1, A.MAT_TRIM, seg=16, r2=0.04)
    cyl(b, (lx + 0.125, ly - 0.125, 1.115), (lx + 0.12, ly - 0.12, 1.12), 0.09, A.MAT_LIGHT, seg=16)
    cyl(b, (dx0 + 0.55, dy0 + 0.35, 0.76), (dx0 + 0.55, dy0 + 0.35, 0.86), 0.045, LINEN, seg=14)          # the mug
    box(b, dx0 + 0.4, dx0 + 0.62, dy0 + 0.55, dy0 + 0.86, 0.76, 0.772, A.MAT_RUBBER)                       # a data pad
    # the Captain's chair (high back, leather), facing the door
    chx, chy = dx0 - 0.85, dk["y"]
    cyl(b, (chx, chy, 0.08), (chx, chy, 0.42), 0.03, A.MAT_TRIM, seg=10)
    for k in range(5):
        a = 2 * math.pi * k / 5
        cyl(b, (chx, chy, 0.08), (chx + math.cos(a) * 0.32, chy + math.sin(a) * 0.32, 0.05), 0.02, A.MAT_TRIM, seg=6)
        cyl(b, (chx + math.cos(a) * 0.32, chy + math.sin(a) * 0.32, 0.0), (chx + math.cos(a) * 0.32, chy + math.sin(a) * 0.32, 0.05), 0.03, A.MAT_RUBBER, seg=8)
    box(b, chx - 0.28, chx + 0.28, chy - 0.28, chy + 0.28, 0.42, 0.54, LEATHER)
    box(b, chx - 0.34, chx - 0.24, chy - 0.26, chy + 0.26, 0.54, 1.32, LEATHER)
    for s_ in (-1, 1):
        box(b, chx - 0.25, chx + 0.2, chy + s_ * 0.3 - 0.04, chy + s_ * 0.3 + 0.04, 0.62, 0.68, LEATHER)
        cyl(b, (chx, chy + s_ * 0.3, 0.54), (chx, chy + s_ * 0.3, 0.62), 0.015, A.MAT_TRIM, seg=6)
    # two chairs for visitors, facing the desk
    for gy in (dk["y"] - 0.55, dk["y"] + 0.55):
        gx = dx1 + 0.75
        box(b, gx - 0.24, gx + 0.24, gy - 0.24, gy + 0.24, 0.42, 0.5, LEATHER)
        box(b, gx + 0.18, gx + 0.26, gy - 0.23, gy + 0.23, 0.5, 0.95, LEATHER)
        for (ex, ey) in ((-0.2, -0.2), (-0.2, 0.2), (0.2, -0.2), (0.2, 0.2)):
            cyl(b, (gx + ex, gy + ey, 0.0), (gx + ex, gy + ey, 0.42), 0.015, A.MAT_TRIM, seg=6)
    # --- the sitting area (port): a sofa against the wall, a low table, an armchair
    sf = D["sofa"]
    sy0 = -HW + FIN
    box(b, sf["x1"], sf["x0"], sy0, sy0 + sf["depth"], 0.1, 0.42, LEATHER)
    for k in range(2):
        xa = sf["x1"] + 0.12 + k * (sf["x0"] - sf["x1"] - 0.24) / 2
        xb = xa + (sf["x0"] - sf["x1"] - 0.24) / 2 - 0.02
        box(b, xa, xb, sy0 + 0.22, sy0 + sf["depth"] - 0.02, 0.42, 0.55, LEATHER)
        box(b, xa, xb, sy0 + 0.02, sy0 + 0.24, 0.42, 0.92, LEATHER)
    for xe in (sf["x1"], sf["x0"] - 0.12):
        box(b, xe, xe + 0.12, sy0, sy0 + sf["depth"], 0.1, 0.68, LEATHER)
    box(b, sf["x1"], sf["x0"], sy0, sy0 + sf["depth"], 0.0, 0.1, WOOD)
    tcx = (sf["x0"] + sf["x1"]) / 2
    box(b, tcx - 0.65, tcx + 0.65, -2.95, -2.3, 0.38, 0.42, WOOD)
    for (ex, ey) in ((-0.58, -2.88), (-0.58, -2.37), (0.58, -2.88), (0.58, -2.37)):
        cyl(b, (tcx + ex, ey, 0.0), (tcx + ex, ey, 0.38), 0.018, A.MAT_TRIM, seg=6)
    box(b, tcx - 0.2, tcx + 0.05, -2.75, -2.55, 0.42, 0.44, A.MAT_RUBBER)                                  # a data pad
    ax_, ay_ = sf["x1"] - 0.8, -2.2
    with K.part(b, place(ax_, ay_, 0.0, 120.0)):
        b.box((0.0, 0.0, 0.27), (0.75, 0.8, 0.34), LEATHER)
        b.box((0.0, 0.0, 0.52), (0.62, 0.66, 0.1), LEATHER)
        b.box((-0.33, 0.0, 0.75), (0.12, 0.8, 0.6), LEATHER)
        for s_ in (-1, 1):
            b.box((0.0, s_ * 0.36, 0.6), (0.75, 0.1, 0.3), LEATHER)
    # the ship's plaque above the sofa is a sign in Unreal (MI_SIGN_Aquila)
    # --- the bunk in its alcove (port, forward): platform, mattress, blanket, pillow, partition, shelf, reading light
    bk = D["bunk"]
    box(b, bk["x1"], bk["x0"], bk["y0"], bk["y1"], 0.0, bk["top"] - 0.2, WOOD)
    box(b, bk["x1"] + 0.03, bk["x0"] - 0.03, bk["y0"] + 0.03, bk["y1"] - 0.03, bk["top"] - 0.2, bk["top"], LINEN)
    box(b, bk["x1"] + 0.02, bk["x0"] - 0.55, bk["y0"] + 0.02, bk["y1"] + 0.02, bk["top"] - 0.05, bk["top"] + 0.03, BLANKET)
    box(b, bk["x0"] - 0.62, bk["x0"] - 0.5, bk["y0"] + 0.02, bk["y1"] + 0.02, bk["top"] - 0.03, bk["top"] + 0.045, LINEN)   # the sheet folded back
    blob(b, (bk["x0"] - 0.3, (bk["y0"] + bk["y1"]) / 2, bk["top"] + 0.06), (0.36, 0.7, 0.13), LINEN)
    box(b, bk["x1"] - 0.2, bk["x1"] - 0.12, -HW + FIN, bk["y1"] + 0.35, 0.0, 2.0, WOOD)                    # the partition
    box(b, bk["x1"] + 0.05, bk["x0"] - 0.05, -HW + FIN, -HW + 0.3, 1.62, 1.66, WOOD)                     # the shelf
    rng = random.Random(7)
    y = bk["x1"] + 0.15
    while y < bk["x0"] - 0.6:
        w = rng.uniform(0.03, 0.06)
        box(b, y, y + w, -HW + 0.08, -HW + 0.26, 1.66, 1.66 + rng.uniform(0.18, 0.25), rng.choice(BOOKS))
        y += w + 0.004
    box(b, bk["x0"] - 0.5, bk["x0"] - 0.3, -HW + 0.1, -HW + 0.13, 1.66, 1.86, A.MAT_RUBBER)               # a photograph
    box(b, bk["x0"] - 0.48, bk["x0"] - 0.32, -HW + 0.13, -HW + 0.135, 1.68, 1.84, LINEN)
    cyl(b, (bk["x0"] - 0.55, -HW + FIN, 1.3), (bk["x0"] - 0.55, -HW + 0.2, 1.3), 0.02, A.MAT_TRIM, seg=8)
    cyl(b, (bk["x0"] - 0.55, -HW + 0.25, 1.32), (bk["x0"] - 0.55, -HW + 0.17, 1.26), 0.06, A.MAT_TRIM, seg=12, r2=0.03)
    cyl(b, (bk["x0"] - 0.55, -HW + 0.255, 1.325), (bk["x0"] - 0.55, -HW + 0.25, 1.32), 0.055, A.MAT_LIGHT, seg=12)
    # --- the bookcase (starboard wall)
    bc = D["bookcase"]
    by0, by1 = HW - FIN - bc["depth"], HW - FIN
    box(b, bc["x1"], bc["x0"], by1 - 0.02, by1, 0.0, bc["height"], WOOD)
    for xe in (bc["x1"], bc["x0"] - 0.04):
        box(b, xe, xe + 0.04, by0, by1, 0.0, bc["height"], WOOD)
    for k in range(6):
        z = 0.08 + k * (bc["height"] - 0.1) / 5
        box(b, bc["x1"], bc["x0"], by0, by1, z, z + 0.03, WOOD)
        if k == 5:
            continue
        xx = bc["x1"] + 0.06
        while xx < bc["x0"] - 0.1:
            if rng.random() < 0.12:   # a gap, a lying stack, an object now and then
                xx += rng.uniform(0.1, 0.25)
                continue
            w = rng.uniform(0.025, 0.06)
            h = rng.uniform(0.2, (bc["height"] - 0.1) / 5 - 0.08)
            box(b, xx, xx + w, by0 + 0.04, by1 - 0.04, z + 0.03, z + 0.03 + h, rng.choice(BOOKS))
            xx += w + 0.003
    # --- the galley corner (forward, starboard): cabinet, counter, coffee machine, mugs, sink, wall cabinets
    gl = D["galley"]
    box(b, gl["x1"], gl["x0"], gl["y0"], gl["y1"], 0.0, 0.88, WOOD)
    box(b, gl["x1"] - 0.03, gl["x0"], gl["y0"] - 0.03, gl["y1"], 0.88, 0.92, A.MAT_TRIM)
    for k in range(3):
        ya = gl["y0"] + 0.1 + k * (gl["y1"] - gl["y0"] - 0.2) / 3
        box(b, gl["x1"] - 0.01, gl["x1"], ya + 0.05, ya + (gl["y1"] - gl["y0"] - 0.2) / 3 - 0.05, 0.1, 0.8, WOOD)
        box(b, gl["x1"] - 0.03, gl["x1"] - 0.01, ya + 0.2, ya + 0.45, 0.72, 0.74, A.MAT_TRIM)
    cmx, cmy = (gl["x0"] + gl["x1"]) / 2, gl["y1"] - 0.45
    box(b, cmx - 0.18, cmx + 0.15, cmy - 0.17, cmy + 0.17, 0.92, 1.36, A.MAT_RUBBER)
    box(b, cmx - 0.19, cmx - 0.18, cmy - 0.1, cmy + 0.1, 1.2, 1.3, A.MAT_TRIM)
    cyl(b, (cmx - 0.22, cmy, 1.12), (cmx - 0.22, cmy, 1.06), 0.02, A.MAT_TRIM, seg=8)
    box(b, cmx - 0.19, cmx - 0.185, cmy + 0.1, cmy + 0.13, 1.28, 1.31, A.MAT_LIGHT)
    for my in (cmy - 0.45, cmy - 0.62):
        cyl(b, (cmx - 0.05, my, 0.92), (cmx - 0.05, my, 1.02), 0.04, LINEN, seg=14)
    box(b, cmx - 0.15, cmx + 0.1, gl["y0"] + 0.3, gl["y0"] + 0.75, 0.9, 0.92, A.MAT_STRUCTURE)             # the sink
    cyl(b, (cmx + 0.14, gl["y0"] + 0.52, 0.92), (cmx + 0.14, gl["y0"] + 0.52, 1.18), 0.012, A.MAT_TRIM, seg=8)
    cyl(b, (cmx + 0.14, gl["y0"] + 0.52, 1.18), (cmx - 0.02, gl["y0"] + 0.52, 1.14), 0.012, A.MAT_TRIM, seg=8)
    box(b, gl["x1"] + 0.25, gl["x0"], gl["y0"], gl["y1"], 1.55, 2.3, WOOD)
    # --- the sideboard under the starboard window (the Aquila's model stands on it)
    mp = D["model_pedestal"]
    box(b, mp["x"] - 0.85, mp["x"] + 0.85, HW - FIN - 0.42, HW - FIN, 0.0, 0.78, WOOD)
    box(b, mp["x"] - 0.86, mp["x"] + 0.86, HW - FIN - 0.43, HW - FIN, 0.78, 0.8, WOOD)
    for k in range(2):
        xa = mp["x"] - 0.8 + k * 0.8
        box(b, xa + 0.02, xa + 0.78, HW - FIN - 0.425, HW - FIN - 0.42, 0.12, 0.72, WOOD)
    cyl(b, (mp["x"], HW - 0.3, 0.8), (mp["x"], HW - 0.3, 0.82), 0.12, A.MAT_STRUCTURE, seg=20)
    cyl(b, (mp["x"], HW - 0.3, 0.82), (mp["x"], HW - 0.3, 0.98), 0.012, A.MAT_TRIM, seg=8)
    # --- the sector chart on the forward wall (port of the door), in a dark bezel
    ms = D["map_screen"]
    w_, h_ = ms["y1"] - ms["y0"], (ms["y1"] - ms["y0"]) / 2
    box(b, -FIN - 0.04, -FIN, ms["y0"] - 0.05, ms["y1"] + 0.05, ms["zc"] - h_ / 2 - 0.05, ms["zc"] + h_ / 2 + 0.05, A.MAT_RUBBER)
    screen(b, -FIN - 0.045, (ms["y0"] + ms["y1"]) / 2, ms["zc"], 180.0, w_, h_, MAP)
    obj = b.to_object("SM_QTR_Room")
    A.finish(obj, bevel=0.006, segments=1)
    A.box_uv(obj, texel_m=1.2)
    return obj


def glass():
    b = A.Builder()
    wa, ws = D["window_aft"], D["window_side"]
    ys = [wa["y0"], *wa["mullions"], wa["y1"]]
    for y0, y1 in zip(ys, ys[1:]):
        box(b, -LEN - 0.2, -LEN - 0.18, y0 + (0.06 if y0 != wa["y0"] else 0.0), y1 - (0.06 if y1 != wa["y1"] else 0.0), wa["z0"], wa["z1"], A.MAT_GLASS)
    box(b, ws["x0"], ws["x1"], HW + 0.18, HW + 0.2, ws["z0"], ws["z1"], A.MAT_GLASS)
    obj = b.to_object("SM_QTR_Glass")
    A.box_uv(obj, texel_m=2.0)
    return obj


# ------------------------------------------------------------------------------------------------ outside
def exterior():
    b = A.Builder()
    wa, ws = D["window_aft"], D["window_side"]
    fx = D["corridor_end_x"] - OX            # the corridor's end, in the cabin's frame (+0.8)
    xa, xf = -LEN - EXT, fx
    yp, ys_ = -HW - EXT, HW + EXT
    zt = H + 0.4
    # the forward face around the corridor's end (the tube meets the block there), the sides, the aft face, the roof
    tube = (-1.85, 1.85, -0.3, 3.25)
    wall_with_holes(b, "x", 0.3, xf, yp, ys_, -0.3, zt, [tube], PLATE)
    wall_with_holes(b, "y", yp, -HW, xa, xf, -0.3, zt, [], PLATE)
    wall_with_holes(b, "y", HW, ys_, xa, xf, -0.3, zt, [(ws["x0"], ws["x1"], ws["z0"], ws["z1"])], PLATE)
    wall_with_holes(b, "x", xa, -LEN, yp, ys_, -0.3, zt, [(wa["y0"], wa["y1"], wa["z0"], wa["z1"])], PLATE)
    box(b, xa, xf, yp, ys_, H + 0.05, zt, PLATE)
    # a raised fairing on the roof, frames round the windows, a sill that sheds nothing (space has no rain: it is a
    # hood for the window's edge), running lights at the aft corners
    K.block(b, ((xa + xf) / 2 - 0.6, 0.0, zt + 0.25), (xf - xa - 2.2, 2 * ys_ - 1.6, 0.5), FRAME, c=0.35)
    for (y0, y1, z0, z1) in ((wa["y0"] - 0.25, wa["y0"], wa["z0"] - 0.25, wa["z1"] + 0.25), (wa["y1"], wa["y1"] + 0.25, wa["z0"] - 0.25, wa["z1"] + 0.25),
                             (wa["y0"], wa["y1"], wa["z1"], wa["z1"] + 0.25), (wa["y0"], wa["y1"], wa["z0"] - 0.25, wa["z0"])):
        box(b, xa - 0.22, xa, y0, y1, z0, z1, FRAME)
    box(b, xa - 0.6, xa, wa["y0"] - 0.4, wa["y1"] + 0.4, wa["z1"] + 0.25, wa["z1"] + 0.4, FRAME)
    for (x0, x1, z0, z1) in ((ws["x0"] - 0.2, ws["x0"], ws["z0"] - 0.2, ws["z1"] + 0.2), (ws["x1"], ws["x1"] + 0.2, ws["z0"] - 0.2, ws["z1"] + 0.2),
                             (ws["x0"], ws["x1"], ws["z1"], ws["z1"] + 0.2), (ws["x0"], ws["x1"], ws["z0"] - 0.2, ws["z0"])):
        box(b, x0, x1, ys_, ys_ + 0.2, z0, z1, FRAME)
    for (yy, m) in ((yp - 0.05, LIGHTS), (ys_ + 0.05, LIGHTS)):
        box(b, xa - 0.1, xa + 0.3, yy - 0.08, yy + 0.08, zt - 0.3, zt - 0.1, m)
    # the pedestal: down into the island's aft slope (it swallows the lower part), panelled bands
    K.slab(b, xa, xf, K.chamfer_rect(ys_, 7.0, 0.08, top=1.0, bottom=0.8), K.chamfer_rect(ys_, 7.0, 0.08, top=1.0, bottom=0.8),
           PLATE, -7.3, -7.3)
    for z in (-1.2, -3.4, -5.6):
        box(b, xa - 0.08, xa, yp + 0.4, ys_ - 0.4, z - 0.12, z, FRAME)
    # the housing of the bridge lift (behind the port corridor's end), on its own pedestal
    pb = D["port_block"]
    px0, _, _ = L(pb["x0"], 0, 0)
    px1, _, _ = L(pb["x1"], 0, 0)
    _, py0, _ = L(0, pb["y0"], 0)
    _, py1, _ = L(0, pb["y1"], 0)
    pc = ((px0 + px1) / 2, (py0 + py1) / 2)
    # (hullkit builds in Blender's frame: its y is flipped by hand)
    K.block(b, (pc[0], -pc[1], zt - 1.95), (px0 - px1, py1 - py0, 3.9), PLATE, c=0.18)
    K.slab(b, px1, px0, K.chamfer_rect((py1 - py0) / 2, 7.0, 0.06, top=1.0, bottom=0.8),
           K.chamfer_rect((py1 - py0) / 2, 7.0, 0.06, top=1.0, bottom=0.8), PLATE, -7.3, -7.3, -pc[1], -pc[1])
    box(b, px1 - 0.1, px1, pc[1] - 1.2, pc[1] + 1.2, 0.6, 2.4, FRAME)
    box(b, px1 - 0.12, px1 - 0.1, pc[1] - 1.0, pc[1] + 1.0, 2.1, 2.2, LIGHTS)
    # the fairings under the two corridors behind the bridge (from their floor down into the island's top)
    for yc in (-3.9, 3.9):
        _, ly, _ = L(0, yc, 0)
        box(b, fx, fx + 12.0, ly - 1.9, ly + 1.9, -1.8, -0.25, PLATE)
    obj = b.to_object("SM_SHIP_ASTRA_AquilaBridgeBlock")
    A.finish(obj, bevel=0.03, segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/quarters"
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    report = []
    for fn in (room, glass, exterior):
        A.clear_objects()
        obj = fn()
        A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    print("QUARTERS_OK", json.dumps(report))


if __name__ == "__main__":
    main()
