"""ASN Aquila — the Mess Hall (Deck 4 · Section B), from data/ship/aquila_mess.json.

  SM_MESS_Hall    the hall: a warm grey deck, blue-grey wainscot under pale panels, the ship's ribs every few metres
                  and the beams across the ceiling, light troffers over the tables, ducts along the sides; the lift in
                  the forward wall; the serving line along the port wall (a steel counter with its pans of food, the
                  tray rail, the stacks of trays) and the kitchen beyond the pass (ovens, the range and its hood,
                  pots, shelves); the drinks station on the starboard side (the coffee urn, the dispenser, cups);
                  twelve long tables with padded benches; on the aft wall the two big screens (the fleet's news and
                  the memorial to the Aquila's dead) with a planter between them; the notice board, a water fountain
                  and a shelf of hydroponic greens along the starboard wall; the galley's menu board over the pass
  SM_MESS_Glass   the serving line's sneeze guards (translucent: not Nanite)
  SM_MESS_Tray    one diner's tray: a plate of food, a cup, the cutlery (tray frame: origin at its centre on the table
                  top, +X across the table, away from the diner)

Coordinates are Unreal's (X forward, Y starboard, Z up) in the hall's frame; U() flips Y for Blender.
blender -b --factory-startup --python-exit-code 1 -P art/blender/messhall.py -- art/export/messhall
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
from medbay import blob, box, cyl, screen  # noqa: E402
from quarters import wall_with_holes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_mess.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
FIN = 0.06
FLOOR = "MI_MESS_Floor"
WALL = "MI_MESS_Wall"
PANEL = "MI_MESS_Panel"
TABLE = "MI_MESS_Table"
SEAT = "MI_MESS_Seat"
TRAY = "MI_MESS_Tray"
PLATE = "MI_MESS_Plate"
CUP = "MI_MESS_Cup"
FOODS = ("MI_MESS_Food1", "MI_MESS_Food2", "MI_MESS_Food3")
LEAF = "MI_MESS_Leaf"
BOARD = "MI_MESS_Board"
NOTE = "MI_MESS_Note"
OVEN = "MI_MESS_Oven"
STEEL = A.MAT_TRIM
FRAME = A.MAT_STRUCTURE
NEWS, MEMORIAL, MENU = "MI_UI_Mess_News", "MI_UI_Mess_Memorial", "MI_UI_Mess_Menu"
RIBS = [-4.75 * k for k in range(1, 8)]          # the ship's frames along the hall


# ------------------------------------------------------------------------------------------------ the hall
def hall():
    """The Mess Hall's mesh: ARTE-INTERNI rebuilt it in the kit's language (art/blender/ship_mess.py: same frame, same tables and benches, the serving line, the drinks station, the
    screens; the shell, light and dressing of the rooms of the plan). hall_v1 below is the M1 hall it replaces."""
    import ship_mess
    return ship_mess.hall("SM_MESS_Hall")


def hall_v1():
    b = A.Builder()
    rng = random.Random(4)
    lift = D["lift"]
    g, dr, t, sc = D["galley"], D["drinks"], D["tables"], D["screens"]
    # the deck: structure, a warm grey covering, darker bands where the aisles run
    box(b, -LEN, 0, -HW, HW, -0.3, -0.02, FRAME)
    box(b, -LEN, 0, -HW, HW, -0.02, 0.0, FLOOR)
    box(b, -LEN + 0.3, -1.0, -0.9, 0.9, 0.0, 0.004, PANEL)   # the central aisle
    # the walls: wainscot to 1.05 m, pale panels above; openings: the lift, the pass to the kitchen
    lift_hole = [(lift["y"] - lift["width"] / 2, lift["y"] + lift["width"] / 2, 0.0, lift["height"])]
    pass_hole = [(g["x1"], g["x0"], 1.2, 2.35)]
    for (axis, p0, p1, u0, u1, holes) in (("x", -FIN, 0.0, -HW, HW, lift_hole), ("x", -LEN, -LEN + FIN, -HW, HW, []),
                                          ("y", -HW, -HW + FIN, -LEN, 0.0, pass_hole), ("y", HW - FIN, HW, -LEN, 0.0, [])):
        wall_with_holes(b, axis, p0, p1, u0, u1, 0.0, 1.05, holes, PANEL)
        wall_with_holes(b, axis, p0, p1, u0, u1, 1.05, H, holes, WALL)
    # the structure behind the finish
    wall_with_holes(b, "x", 0.0, 0.3, -HW - 0.05, HW + 0.05, -0.3, H + 0.3, lift_hole, FRAME)
    box(b, -LEN - 0.3, -LEN, -HW - 0.05, HW + 0.05, -0.3, H + 0.3, FRAME)
    wall_with_holes(b, "y", HW, HW + 0.3, -LEN - 0.3, 0.3, -0.3, H + 0.3, [], FRAME)
    # a rail on the wainscot, the skirting
    for (y0, y1) in ((-HW + FIN, -HW + FIN + 0.04), (HW - FIN - 0.04, HW - FIN)):
        box(b, -LEN + FIN, -FIN, y0, y1, 1.03, 1.08, STEEL)
        box(b, -LEN + FIN, -FIN, y0, y1, 0.0, 0.1, FRAME)
    # the ribs: pilasters on the side walls and beams across the ceiling
    for x in RIBS:
        for (y0, y1) in ((-HW + FIN, -HW + FIN + 0.16), (HW - FIN - 0.16, HW - FIN)):
            if y0 < 0 and g["x1"] - 0.3 < x < g["x0"] + 0.3:
                continue   # no rib through the pass
            box(b, x - 0.16, x + 0.16, y0, y1, 0.0, H, FRAME)
        box(b, x - 0.16, x + 0.16, -HW + FIN, HW - FIN, H - 0.34, H, FRAME)
    # the ceiling: panels, light troffers over the tables, ducts along the sides
    box(b, -LEN, 0, -HW, HW, H, H + 0.05, WALL)
    for yc in t["y_centres"]:
        for (x0, x1) in zip([0.0] + RIBS, RIBS + [-LEN]):
            if x0 - x1 < 1.2:
                continue
            box(b, x1 + 0.4, x0 - 0.4, yc - 0.32, yc + 0.32, H - 0.02, H, A.MAT_LIGHT)
            box(b, x1 + 0.35, x0 - 0.35, yc - 0.36, yc - 0.32, H - 0.05, H, STEEL)
            box(b, x1 + 0.35, x0 - 0.35, yc + 0.32, yc + 0.36, H - 0.05, H, STEEL)
    for ys in (-1, 1):
        y = ys * (HW - 0.55)
        cyl(b, (-LEN + FIN, y, H - 0.62), (-FIN, y, H - 0.62), 0.24, STEEL, seg=18)
        for x in RIBS:
            box(b, x - 0.05, x + 0.05, y - 0.3, y + 0.3, H - 0.4, H - 0.34, FRAME)   # hangers
    # the lift's frame and a light over it
    ly0, ly1 = lift["y"] - lift["width"] / 2, lift["y"] + lift["width"] / 2
    for (y0, y1, z0, z1) in ((ly0 - 0.14, ly0, 0.0, lift["height"] + 0.14), (ly1, ly1 + 0.14, 0.0, lift["height"] + 0.14),
                             (ly0, ly1, lift["height"], lift["height"] + 0.14)):
        box(b, -0.12, 0.3, y0, y1, z0, z1, A.MAT_TRIM)
    box(b, -0.14, -0.06, ly0, ly1, lift["height"] + 0.2, lift["height"] + 0.26, A.MAT_LIGHT)

    # --- the serving line: a steel counter, its pans of food under the sneeze guard (SM_MESS_Glass), the tray rail
    cx0, cx1 = g["x1"], g["x0"]          # aft, forward
    yc0, yc1 = -HW + FIN, g["y_counter"]    # wall side, aisle side
    zc = g["height"]
    box(b, cx0, cx1, yc0, yc1, 0.0, zc - 0.04, PANEL)
    box(b, cx0 - 0.03, cx1 + 0.03, yc0, yc1 + 0.03, zc - 0.04, zc, STEEL)
    box(b, cx0, cx1, yc1 - 0.02, yc1, 0.08, zc - 0.1, STEEL)           # the front's steel face
    box(b, cx0, cx1, yc1, yc1 + 0.06, 0.0, 0.1, FRAME)                  # kick plate
    # the tray rail: tubes on brackets along the aisle side
    for zz in (zc - 0.06, zc - 0.18):
        cyl(b, (cx0, yc1 + 0.28, zz), (cx1, yc1 + 0.28, zz), 0.018, STEEL, seg=10)
    for x in [cx0 + 0.3 + k * 1.2 for k in range(int((cx1 - cx0) / 1.2))]:
        box(b, x - 0.02, x + 0.02, yc1, yc1 + 0.3, zc - 0.2, zc - 0.04, STEEL)
    # six pans in the counter top (steel wells with the day's food in them)
    for k in range(6):
        px = cx1 - 0.9 - k * 1.1
        box(b, px - 0.34, px + 0.34, yc1 - 0.62, yc1 - 0.2, zc - 0.012, zc + 0.004, STEEL)
        blob(b, (px, yc1 - 0.41, zc - 0.005), (0.62, 0.36, 0.05), FOODS[k % 3], e=0.3, ez=0.6)
        cyl(b, (px + 0.26, yc1 - 0.3, zc + 0.01), (px + 0.1, yc1 - 0.45, zc + 0.22), 0.012, STEEL, seg=8)   # a ladle
    # the guard's posts
    for x in (cx0 + 0.15, (cx0 + cx1) / 2, cx1 - 0.15):
        cyl(b, (x, yc1 - 0.15, zc), (x, yc1 - 0.15, zc + 0.52), 0.015, STEEL, seg=8)
    box(b, cx0 + 0.1, cx1 - 0.1, yc1 - 0.72, yc1 - 0.1, zc + 0.5, zc + 0.53, STEEL)   # the guard's top (a shelf)
    # stacks of trays at the forward end, a bin of cutlery
    for s_ in range(3):
        sx = cx1 + 0.35 + s_ * 0.0
        for k in range(14):
            box(b, sx - 0.02 - 0.18, sx - 0.02 + 0.18, yc1 + 0.4 + s_ * 0.5 - 0.23, yc1 + 0.4 + s_ * 0.5 + 0.23, 0.9 + k * 0.022,
                0.9 + k * 0.022 + 0.016, TRAY)
    box(b, cx1 + 0.08, cx1 + 0.62, yc1 + 0.2, yc1 + 1.6, 0.0, 0.9, PANEL)
    box(b, cx1 + 0.2, cx1 + 0.5, yc1 + 1.62, yc1 + 1.9, 0.9, 1.05, STEEL)
    # the kitchen beyond the pass (seen through it): back wall, ovens, the range and its hood, pots, shelves
    ky0, ky1 = -HW - 2.8, -HW
    box(b, cx0 - 0.5, cx1 + 0.5, ky0 - 0.2, ky1, -0.3, -0.02, FRAME)
    box(b, cx0 - 0.5, cx1 + 0.5, ky0 - 0.2, ky1, -0.02, 0.0, FLOOR)
    box(b, cx0 - 0.5, cx1 + 0.5, ky0 - 0.3, ky0, 0.0, H, PANEL)
    for xe in (cx0 - 0.5, cx1 + 0.5):
        box(b, xe - 0.15, xe + 0.15, ky0, ky1, 0.0, H, PANEL)
    box(b, cx0 - 0.5, cx1 + 0.5, ky0, ky1, H - 0.4, H - 0.3, WALL)
    box(b, cx0 - 0.5, cx1 + 0.5, ky0, ky1, H - 0.05, H, A.MAT_LIGHT)
    for k in range(3):
        ox = cx0 + 0.6 + k * 1.1
        box(b, ox - 0.5, ox + 0.5, ky0, ky0 + 0.85, 0.0, 1.6, OVEN)
        box(b, ox - 0.4, ox + 0.4, ky0 + 0.85, ky0 + 0.87, 0.35, 1.2, A.MAT_RUBBER)       # the oven's dark door
        cyl(b, (ox - 0.35, ky0 + 0.92, 1.3), (ox + 0.35, ky0 + 0.92, 1.3), 0.015, STEEL, seg=8)
    rx0, rx1 = cx0 + 3.4, cx1 - 0.6
    box(b, rx0, rx1, ky0, ky0 + 0.9, 0.0, 0.9, STEEL)
    for k in range(4):
        cyl(b, (rx0 + 0.5 + k * 0.75, ky0 + 0.45, 0.9), (rx0 + 0.5 + k * 0.75, ky0 + 0.45, 0.905), 0.16, A.MAT_RUBBER, seg=16)
    cyl(b, (rx0 + 0.5, ky0 + 0.45, 0.905), (rx0 + 0.5, ky0 + 0.45, 1.15), 0.18, STEEL, seg=18)   # a stock pot
    cyl(b, (rx0 + 1.25, ky0 + 0.45, 0.905), (rx0 + 1.25, ky0 + 0.45, 1.0), 0.16, STEEL, seg=18)
    box(b, rx0 - 0.1, rx1 + 0.1, ky0, ky0 + 1.0, 2.2, 2.3, STEEL)                             # the hood
    for k in range(5):
        px = rx0 + 0.3 + k * 0.5
        cyl(b, (px, ky0 + 1.2, 2.05), (px, ky0 + 1.2, 1.75), 0.006, STEEL, seg=6)                # pots on a rail
        cyl(b, (px, ky0 + 1.2, 1.75), (px, ky0 + 1.2, 1.55), 0.1 + 0.02 * (k % 2), STEEL, seg=14)
    for k in range(3):
        box(b, cx0 - 0.3, cx0 + 1.6, ky0, ky0 + 0.4, 1.9 + k * 0.45, 1.93 + k * 0.45, STEEL)   # shelves
    # the menu board over the pass (a live-looking static screen)
    screen(b, (cx0 + cx1) / 2, -HW + FIN + 0.03, 2.95, 90.0, 5.6, 0.72, MENU)
    box(b, cx0 + 0.9, cx1 - 0.9, -HW + FIN, -HW + FIN + 0.03, 2.55, 3.35, FRAME)

    # --- the drinks station (starboard, forward)
    dx0, dx1 = dr["x1"], dr["x0"]
    dy0, dy1 = dr["y_counter"] - dr["depth"] / 2, HW - FIN
    box(b, dx0, dx1, dy0, dy1, 0.0, dr["height"] - 0.04, PANEL)
    box(b, dx0 - 0.03, dx1 + 0.03, dy0 - 0.03, dy1, dr["height"] - 0.04, dr["height"], STEEL)
    ux = dx1 - 0.7
    cyl(b, (ux, dy1 - 0.35, dr["height"]), (ux, dy1 - 0.35, dr["height"] + 0.62), 0.22, STEEL, seg=22)      # the urn
    cyl(b, (ux, dy1 - 0.35, dr["height"] + 0.62), (ux, dy1 - 0.35, dr["height"] + 0.68), 0.12, A.MAT_RUBBER, seg=16)
    box(b, ux - 0.04, ux + 0.04, dy1 - 0.62, dy1 - 0.56, dr["height"] + 0.1, dr["height"] + 0.16, A.MAT_RUBBER)   # the tap
    box(b, ux - 1.9, ux - 1.0, dy1 - 0.55, dy1 - 0.05, dr["height"], dr["height"] + 0.75, PANEL)            # dispenser
    for k in range(3):
        box(b, ux - 1.82 + k * 0.28, ux - 1.64 + k * 0.28, dy1 - 0.58, dy1 - 0.55, dr["height"] + 0.35, dr["height"] + 0.62,
            A.MAT_RUBBER)                                                               # its three nozzles
    for r_ in range(2):
        for k in range(8):   # cups upside down on the rack
            cyl(b, (dx0 + 0.3 + k * 0.14, dy0 + 0.25 + r_ * 0.14, dr["height"]), (dx0 + 0.3 + k * 0.14, dy0 + 0.25 + r_ * 0.14,
                dr["height"] + 0.09), 0.04, CUP, seg=12, r2=0.032)
    # a water fountain and the notice board further aft on the starboard wall; the shelf of greens
    box(b, -10.6, -10.0, HW - 0.4, HW - FIN, 0.0, 0.95, STEEL)
    cyl(b, (-10.3, HW - 0.25, 0.95), (-10.3, HW - 0.25, 1.05), 0.03, STEEL, seg=8)
    bx0, bx1 = -17.6, -13.4
    box(b, bx0 - 0.08, bx1 + 0.08, HW - FIN - 0.04, HW - FIN, 1.12, 2.48, FRAME)
    box(b, bx0, bx1, HW - FIN - 0.06, HW - FIN - 0.04, 1.2, 2.4, BOARD)
    for k in range(16):   # notes pinned to it
        nx = rng.uniform(bx0 + 0.2, bx1 - 0.35)
        nz = rng.uniform(1.3, 2.1)
        w_, h_ = rng.uniform(0.16, 0.3), rng.uniform(0.2, 0.3)
        box(b, nx, nx + w_, HW - FIN - 0.075, HW - FIN - 0.06, nz, nz + h_, NOTE if k % 4 else "MI_MESS_Food2")
        cyl(b, (nx + w_ / 2, HW - FIN - 0.08, nz + h_ - 0.03), (nx + w_ / 2, HW - FIN - 0.09, nz + h_ - 0.03), 0.012, A.MAT_ACCENT, seg=6)
    gx0, gx1 = -27.0, -20.0
    box(b, gx0, gx1, HW - 0.5, HW - FIN, 1.3, 1.34, STEEL)
    box(b, gx0, gx1, HW - 0.48, HW - FIN, 1.34, 1.52, PANEL)          # the hydroponic trough
    for k in range(18):
        lx = gx0 + 0.25 + k * (gx1 - gx0 - 0.5) / 17
        blob(b, (lx, HW - 0.28, 1.62 + 0.06 * (k % 3)), (0.34, 0.3, 0.26 + 0.05 * (k % 2)), LEAF, e=0.8, ez=0.7)
    box(b, gx0, gx1, HW - 0.5, HW - FIN, 2.05, 2.09, A.MAT_LIGHT)     # grow light

    # --- the tables and their benches
    for xc in t["x_centres"]:
        for yc in t["y_centres"]:
            x0, x1 = xc - t["length"] / 2, xc + t["length"] / 2
            box(b, x0, x1, yc - t["width"] / 2, yc + t["width"] / 2, t["height"] - 0.04, t["height"], TABLE)
            box(b, x0 - 0.01, x1 + 0.01, yc - t["width"] / 2 - 0.01, yc + t["width"] / 2 + 0.01, t["height"] - 0.06,
                t["height"] - 0.04, STEEL)
            for lx in (x0 + 0.9, x1 - 0.9):
                cyl(b, (lx, yc, 0.02), (lx, yc, t["height"] - 0.06), 0.05, STEEL, seg=12)
                box(b, lx - 0.06, lx + 0.06, yc - 0.42, yc + 0.42, 0.0, 0.03, STEEL)
            for side in (-1, 1):
                by = yc + side * t["bench_offset"]
                bw = t["bench_width"] / 2
                zb = t["bench_height"]
                box(b, x0 + 0.1, x1 - 0.1, by - bw, by + bw, zb - 0.07, zb, SEAT)
                box(b, x0 + 0.15, x1 - 0.15, by - bw + 0.03, by + bw - 0.03, zb - 0.1, zb - 0.07, STEEL)
                for lx in (x0 + 0.6, xc, x1 - 0.6):
                    box(b, lx - 0.03, lx + 0.03, by - 0.03, by + 0.03, 0.0, zb - 0.1, STEEL)
                    box(b, lx - 0.04, lx + 0.04, by - bw + 0.05, by + bw - 0.05, 0.0, 0.025, STEEL)
            # the table's own things: a caddy of condiments in the middle
            box(b, xc - 0.15, xc + 0.15, yc - 0.08, yc + 0.08, t["height"], t["height"] + 0.04, STEEL)
            for k in range(3):
                cyl(b, (xc - 0.08 + k * 0.08, yc, t["height"] + 0.04), (xc - 0.08 + k * 0.08, yc, t["height"] + 0.17), 0.022,
                    (A.MAT_ACCENT, FOODS[0], A.MAT_RUBBER)[k], seg=10)

    # --- the aft wall: the fleet's news and the memorial, framed; a planter between them
    xa = -LEN + FIN
    for key, mat in (("news", NEWS), ("memorial", MEMORIAL)):
        s = sc[key]
        yc, zc_ = (s["y0"] + s["y1"]) / 2, (s["z0"] + s["z1"]) / 2
        w, h = s["y1"] - s["y0"], s["z1"] - s["z0"]
        box(b, xa, xa + 0.1, s["y0"] - 0.14, s["y1"] + 0.14, s["z0"] - 0.14, s["z1"] + 0.14, FRAME)
        screen(b, xa + 0.105, yc, zc_, 0.0, w, h, mat)
        box(b, xa, xa + 0.14, s["y0"] - 0.14, s["y1"] + 0.14, s["z1"] + 0.2, s["z1"] + 0.24, A.MAT_LIGHT)   # a picture light
    box(b, xa, xa + 0.7, -1.3, 1.3, 0.0, 0.6, PANEL)
    for k in range(9):
        blob(b, (xa + 0.35, -1.0 + k * 0.25, 0.75 + 0.1 * (k % 2)), (0.4, 0.34, 0.4 + 0.08 * (k % 3)), LEAF, e=0.85, ez=0.7)
    obj = b.to_object("SM_MESS_Hall")
    A.finish(obj, bevel=0.01, segments=1)
    A.box_uv(obj, texel_m=1.2)
    return obj


def glass():
    b = A.Builder()
    g = D["galley"]
    zc = g["height"]
    yc1 = g["y_counter"]
    # the sneeze guard: a sloped pane over the pans from the shelf down towards the diners
    box(b, g["x1"] + 0.12, g["x0"] - 0.12, yc1 - 0.1, yc1 - 0.08, zc + 0.26, zc + 0.5, A.MAT_GLASS)
    obj = b.to_object("SM_MESS_Glass")
    A.box_uv(obj, texel_m=2.0)
    return obj


def tray():
    """One diner's tray on the table top: +X across the table (away from the diner)."""
    b = A.Builder()
    box(b, -0.17, 0.17, -0.23, 0.23, 0.0, 0.018, TRAY)
    box(b, -0.175, 0.175, -0.235, 0.235, 0.018, 0.026, TRAY)
    box(b, -0.16, 0.16, -0.22, 0.22, 0.018, 0.02, TRAY)
    cyl(b, (0.0, -0.02, 0.02), (0.0, -0.02, 0.035), 0.125, PLATE, seg=28, r2=0.11)
    blob(b, (0.03, -0.06, 0.04), (0.12, 0.1, 0.035), FOODS[0], e=0.7, ez=0.6)
    blob(b, (-0.04, 0.02, 0.04), (0.1, 0.09, 0.03), FOODS[1], e=0.8, ez=0.6)
    blob(b, (0.04, 0.04, 0.04), (0.07, 0.07, 0.03), FOODS[2], e=0.9, ez=0.7)
    cyl(b, (0.09, 0.16, 0.02), (0.09, 0.16, 0.115), 0.038, CUP, seg=16, r2=0.034)
    box(b, -0.11, -0.1, 0.13, 0.2, 0.02, 0.024, STEEL)     # fork
    box(b, -0.08, -0.07, 0.13, 0.21, 0.02, 0.024, STEEL)   # knife
    obj = b.to_object("SM_MESS_Tray")
    A.finish(obj, bevel=0.003, segments=1)
    A.box_uv(obj, texel_m=0.4)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/messhall"
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    report = []
    for fn in (hall, glass, tray):
        A.clear_objects()
        obj = fn()
        A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    print("MESS_OK", json.dumps(report))


if __name__ == "__main__":
    main()
