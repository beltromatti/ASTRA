"""ASN Aquila — the Mess Hall (Deck 4 · Section B), rebuilt in the kit's language (ARTE-INTERNI). SM_MESS_Hall of art/blender/messhall.py, same frame and same places (data/ship/aquila_mess.json:
the hall runs aft of the lift on x 0 .. -38, y +-10, the twelve tables and their benches where the diners sit, the serving line on the port wall with the kitchen behind its pass, the
drinks station on the starboard side, the news and the memorial screens on the aft wall), but with the shell, the light and the dressing of the rooms of the plan: a terrazzo floor with a
slate aisle, walnut and plaster walls in bays with a light slot on every frame, a ceiling of luminous bands over the four rows of tables between beams on the ship's frames (the
actor lights of build_messhall.py are the same four rows), oak tables with steel edges on pedestal feet and padded benches, a serving line with its food, a kitchen you can see into,
the herb wall, banners, plants. The hall is built as a room in its own frame (x along the hall from the forward wall aft, y from the starboard wall to the port one) and turned into the
hall's frame by one transform.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_mess.py -- [--preview <dir>] [--samples N]
(the FBX export stays with messhall.py, which calls hall() here).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_decor as DC  # noqa: E402
import ship_furniture as F  # noqa: E402
import ship_furn2 as N  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
import ship_plants as PL  # noqa: E402
import ship_themes as TH  # noqa: E402
from bridge3_lib import Rz, T, frame  # noqa: E402
from ship_lib import (BRASS, CARPET_SLATE, CERAMIC, COMPOSITE, LAMP, LAMP_DIM, LAMP_HOT, LEATHER_NAVY, LEATHER_OX, LEATHER_TAN, OAK, PERF, PLASTER_IVORY, STEEL, STRUCT, SWATCH, TERRAZZO,
                      TILE_FLOOR, TILE_WALL, TRIM, WALNUT, WHITE_GLOSS, SParts)
from ship_rooms import WF, WS, build_shell, place

ROOT = SL.ROOT
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_mess.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
NEWS, MEMORIAL, MENU = "MI_UI_Mess_News", "MI_UI_Mess_Memorial", "MI_UI_Mess_Menu"
RIBS = [4.75 * k for k in range(1, 8)]                 # the ship's frames along the hall (local x; the old hall had them at -4.75 k)


def loc(xh: float, yh: float) -> tuple[float, float]:
    """Hall frame (x aft negative, y to starboard) -> the room frame built here (x aft positive from the forward wall, y 0 at the starboard wall)."""
    return (-xh, HW - yh)


def style():
    return TH.mess(floor=SL.TERRAZZO_DARK, floor2=CARPET_SLATE, border=0.0, wall_lo=WALNUT, wall_hi=PLASTER_IVORY, ceil=PLASTER_IVORY, wall_acc=SL.WEAVE_SAND, wall_slat=OAK, wain_h=1.05,
                   wall_pattern=("panel", "panel", "slats", "panel", "cloth", "panel"), bay=2.375, skirt=STEEL, ceiling="bands", band_ys=(3.1, 6.9, 13.1, 16.9), band_w=0.6,
                   beam_pitch=4.75, downlights=False, accent="warm_dim", light_cell="white_warm", seams=False)


# ------------------------------------------------------------------------------------------------------------------------------ the tables
def mess_table(b: SParts, length: float = 7.0, width: float = 1.0, h: float = 0.74) -> None:
    """A long mess table (origin at its centre): an oak top 4 cm thick with a rolled edge and a steel band, on two pedestal feet, with a caddy of condiments and a napkin dispenser."""
    MK.rbox(b.soft, (-length / 2, -width / 2, h - 0.04), (length / 2, width / 2, h), 0.014, OAK, 2)
    b.fine.box((-length / 2 + 0.02, -width / 2 + 0.02, h - 0.065), (length / 2 - 0.02, width / 2 - 0.02, h - 0.04), STEEL)
    for lx in (-length / 2 + 0.9, length / 2 - 0.9):
        b.body.cyl((lx, 0, 0.03), (lx, 0, h - 0.065), 0.055, TRIM, seg=12, r2=0.065)
        b.body.cyl((lx, 0, 0.0), (lx, 0, 0.03), 0.3, STRUCT, seg=18, r2=0.27)
        b.fine.box((lx - 0.28, -0.07, h - 0.075), (lx + 0.28, 0.07, h - 0.065), TRIM)
    b.fine.box((-0.17, -0.08, h), (0.17, 0.08, h + 0.03), STEEL)                                   # the caddy
    for k, col in enumerate(("red", "mustard", "white")):
        b.fine.swatch_cyl((-0.08 + k * 0.08, 0.0, h + 0.03), (-0.08 + k * 0.08, 0.0, h + 0.14), 0.022, col, seg=8)
    b.fine.box((0.5, -0.06, h), (0.62, 0.06, h + 0.1), STEEL)                                      # the napkin dispenser


def mess_bench(b: SParts, length: float = 6.8, width: float = 0.38, h: float = 0.45, mat: str = LEATHER_NAVY) -> None:
    """A padded bench (origin at its centre on the floor): a pad 6 cm thick with rounded edges on a steel rail with three pairs of feet."""
    MK.rbox(b.soft, (-length / 2, -width / 2, h - 0.065), (length / 2, width / 2, h), 0.025, mat, 2)
    b.body.box((-length / 2 + 0.05, -width / 2 + 0.04, h - 0.1), (length / 2 - 0.05, width / 2 - 0.04, h - 0.065), TRIM)
    for lx in (-length / 2 + 0.5, 0.0, length / 2 - 0.5):
        b.body.box((lx - 0.03, -0.03, 0.0), (lx + 0.03, 0.03, h - 0.1), TRIM)
        b.body.box((lx - 0.04, -width / 2 + 0.05, 0.0), (lx + 0.04, width / 2 - 0.05, 0.022), STRUCT)


# ----------------------------------------------------------------------------------------------------------------------------- serving line
def serving_line(b: SParts, x0: float, x1: float, y_wall: float, y_front: float, zc: float) -> None:
    """The serving line along the port wall (room frame: x0..x1 along the hall, the counter between y_front and the wall at y_wall > y_front): a steel counter with a panelled front and a
    kick plate, six pans of food in the top with their serving spoons, the tray rail on brackets, stacks of trays, a cutlery bin, a heat lamp bar overhead."""
    w = x1 - x0
    b.body.box((x0, y_front, 0.0), (x1, y_front + 0.06, 0.1), STRUCT)
    MK.rbox(b.soft, (x0, y_front + 0.02, 0.1), (x1, y_wall - 0.05, zc - 0.04), 0.01, STEEL, 2)
    b.body.box((x0 - 0.03, y_front - 0.03, zc - 0.04), (x1 + 0.03, y_wall - 0.05, zc), STEEL)
    for k in range(5):                                                                                # panels in the front
        xa = x0 + 0.2 + k * (w - 0.4) / 5
        b.fine.box((xa, y_front + 0.012, 0.22), (xa + (w - 0.4) / 5 - 0.1, y_front + 0.025, zc - 0.2), WHITE_GLOSS)
    foods = ("f_apple", "f_carrot", "f_bread", "f_lettuce", "f_orange", "f_cheese", "f_tomato")
    for k in range(6):
        px = x0 + 0.45 + k * (w - 0.9) / 5
        py = (y_front + y_wall) / 2 + 0.05
        b.fine.box((px - 0.34, py - 0.22, zc - 0.012), (px + 0.34, py + 0.22, zc + 0.01), TRIM)
        b.fine.box((px - 0.315, py - 0.195, zc + 0.002), (px + 0.315, py + 0.195, zc + 0.012), STEEL)
        # the food, heaped: a dome of one colour with a few lumps of another on it
        b.soft.paint(MK.puff(b.soft, (px, py, zc + 0.012), (0.29, 0.18, 0.075), SWATCH, e=0.7, nu=14, nv=6), foods[k % len(foods)])
        for j in range(4):
            b.soft.paint(MK.puff(b.soft, (px - 0.15 + j * 0.1, py + (0.05 if j % 2 else -0.05), zc + 0.075), (0.04, 0.035, 0.03), SWATCH, e=0.9, nu=8, nv=5), foods[(k + 2) % len(foods)])
        b.fine.cyl((px + 0.24, py - 0.1, zc + 0.05), (px + 0.1, py - 0.16, zc + 0.22), 0.011, STEEL, seg=6)
        b.fine.cyl((px + 0.1, py - 0.16, zc + 0.22), (px + 0.07, py - 0.17, zc + 0.19), 0.03, STEEL, seg=8, r2=0.02)
    for z in (zc - 0.06, zc - 0.18):                                                                    # the tray rail
        b.fine.cyl((x0, y_front - 0.28, z), (x1, y_front - 0.28, z), 0.018, STEEL, seg=10)
    for k in range(int(w / 1.2) + 1):
        xb = x0 + 0.3 + k * 1.2
        if xb < x1:
            b.fine.box((xb - 0.02, y_front - 0.3, zc - 0.2), (xb + 0.02, y_front, zc - 0.04), STEEL)
    b.body.box((x0 + 0.1, y_wall - 0.78, zc + 0.5), (x1 - 0.1, y_wall - 0.1, zc + 0.53), STEEL)         # the sneeze guard's shelf (the glass is SM_MESS_Glass)
    b.emit.lamp_box((x0 + 0.4, y_wall - 0.7, zc + 0.495), (x1 - 0.4, y_wall - 0.2, zc + 0.5), "amber", LAMP_DIM)    # the heat lamp bar
    for s_ in range(3):                                                                                 # stacks of trays at the aft end
        sx = x1 + 0.45
        for k in range(14):
            b.soft.swatch_box((sx - 0.2, y_front + 0.3 + s_ * 0.5 - 0.23, 0.9 + k * 0.022), (sx + 0.2, y_front + 0.3 + s_ * 0.5 + 0.23, 0.9 + k * 0.022 + 0.016), "slate")
    b.body.box((x1 + 0.1, y_front + 0.05, 0.0), (x1 + 0.8, y_front + 1.7, 0.9), COMPOSITE)
    b.fine.box((x1 + 0.25, y_front + 1.75, 0.9), (x1 + 0.55, y_front + 2.05, 1.05), STEEL)


def kitchen(b: SParts, x0: float, x1: float, y0: float, y1: float) -> None:
    """The kitchen behind the pass (room frame: x0..x1 along the hall, y0 = the port wall's outer face, y1 = the kitchen's back wall): a tiled floor and back wall, a bank of ovens, the range
    with its hood and a stock pot, a prep table, pots on a rail, shelves, the cook's station light."""
    L = x1 - x0
    b.body.box((x0 - 0.5, y0, -0.3), (x1 + 0.5, y1, -0.02), STRUCT)
    b.body.box((x0 - 0.5, y0, -0.02), (x1 + 0.5, y1, 0.0), TILE_FLOOR)
    b.body.box((x0 - 0.5, y1, 0.0), (x1 + 0.5, y1 + 0.3, H), STRUCT)
    b.body.box((x0 - 0.5, y1 - 0.04, 0.0), (x1 + 0.5, y1, H), TILE_WALL)
    for xe in (x0 - 0.5, x1 + 0.5):
        b.body.box((xe - 0.15, y0, 0.0), (xe + 0.15, y1, H), TILE_WALL)
    b.body.box((x0 - 0.5, y0, H - 0.4), (x1 + 0.5, y1, H - 0.3), STRUCT)
    b.body.box((x0 - 0.5, y0, H - 0.05), (x1 + 0.5, y1, H), STRUCT)
    b.emit.lamp_box((x0 - 0.4, y0 + 0.2, H - 0.056), (x1 + 0.4, y1 - 0.2, H - 0.05), "white_cool", LAMP_HOT)
    for k in range(3):                                                                                  # ovens
        ox = x0 + 0.6 + k * 1.1
        b.body.box((ox - 0.5, y1 - 0.9, 0.0), (ox + 0.5, y1 - 0.04, 1.6), STEEL)
        b.fine.box((ox - 0.4, y1 - 0.92, 0.35), (ox + 0.4, y1 - 0.9, 1.2), STRUCT)
        b.fine.box((ox - 0.36, y1 - 0.93, 0.42), (ox + 0.36, y1 - 0.92, 1.12), SL.DGLASS)
        b.fine.cyl((ox - 0.35, y1 - 0.96, 1.3), (ox + 0.35, y1 - 0.96, 1.3), 0.015, TRIM, seg=8)
        b.emit.lamp_box((ox + 0.3, y1 - 0.935, 1.45), (ox + 0.4, y1 - 0.93, 1.5), "amber", LAMP_DIM)
    rx0, rx1 = x0 + 3.4, x1 - 0.6                                                                       # the range
    b.body.box((rx0, y1 - 0.9, 0.0), (rx1, y1 - 0.04, 0.9), STEEL)
    for k in range(4):
        b.fine.cyl((rx0 + 0.5 + k * 0.75, y1 - 0.45, 0.9), (rx0 + 0.5 + k * 0.75, y1 - 0.45, 0.915), 0.16, SL.RUBBER, seg=16)
    b.fine.cyl((rx0 + 0.5, y1 - 0.45, 0.915), (rx0 + 0.5, y1 - 0.45, 1.15), 0.18, STEEL, seg=18)
    b.fine.cyl((rx0 + 1.25, y1 - 0.45, 0.915), (rx0 + 1.25, y1 - 0.45, 1.0), 0.16, STEEL, seg=18)
    b.body.box((rx0 - 0.1, y1 - 1.0, 2.2), (rx1 + 0.1, y1 - 0.04, 2.3), STEEL)                        # the hood
    b.body.box((rx0 + 0.4, y1 - 0.8, 2.3), (rx1 - 0.4, y1 - 0.3, H - 0.3), STEEL)
    for k in range(5):                                                                                  # pots on a rail
        px = rx0 + 0.3 + k * 0.5
        b.fine.cyl((px, y1 - 1.2, 2.05), (px, y1 - 1.2, 1.75), 0.006, STEEL, seg=6)
        b.fine.cyl((px, y1 - 1.2, 1.75), (px, y1 - 1.2, 1.55), 0.1 + 0.02 * (k % 2), STEEL, seg=14)
    for k in range(3):
        b.fine.box((x0 - 0.3, y1 - 0.4, 1.9 + k * 0.45), (x0 + 1.6, y1 - 0.04, 1.93 + k * 0.45), STEEL)
    place(b, (rx0 + rx1) / 2 - 0.2, y0 + 1.1, 0, F.table, 3.6, 0.9, 0.9, STEEL, STEEL, False)          # the prep table
    for k in range(4):
        b.soft.swatch_box(((rx0 + rx1) / 2 - 1.6 + k * 0.8, y0 + 0.8, 0.9), ((rx0 + rx1) / 2 - 1.2 + k * 0.8, y0 + 1.2, 0.93), ("f_lettuce", "f_carrot", "f_tomato", "f_bread")[k])


# ------------------------------------------------------------------------------------------------------------------------------------ the hall
def build_room(b: SParts) -> None:
    """Everything in the room frame (x aft from the forward wall, y from the starboard wall): the caller wraps it in the transform into the hall's frame."""
    rng = random.Random(4)
    g, dr, t, sc = D["galley"], D["drinks"], D["tables"], D["screens"]
    lift, lift_y = D["lift"], HW - D["lift"]["y"]
    px0, px1 = loc(g["x0"], 0)[0], loc(g["x1"], 0)[0]                     # the pass: x 1.6 .. 9.4 along the hall
    doors = [{"wall": "left", "x": lift_y, "w": lift["width"], "h": lift["height"]},
             {"wall": "far", "x": (px0 + px1) / 2, "w": px1 - px0, "h": 2.35, "z0": 1.2}]
    spec = {"key": "mess_hall", "L": LEN, "D": 2 * HW, "h": H, "doors": doors}
    build_shell(b, spec, style(), doors=doors, bare=(), ceil_t=0.3, floor_t=0.3)
    xl, xr, yn, yf = WS + WF, LEN - WS - WF, WS + WF, 2 * HW - WS - WF           # the finished faces: forward wall, aft wall, starboard wall, port wall
    # the floor's aisle: a slate strip down the middle from the gate to the aft wall, with a thin lit line on each side
    b.body.box((xl + 0.2, HW - 0.9, 0.0), (xr - 0.2, HW + 0.9, 0.006), CARPET_SLATE)
    for y in (HW - 0.9, HW + 0.9):
        b.emit.lamp_box((xl + 0.2, y - 0.008, 0.0), (xr - 0.2, y + 0.008, 0.005), "warm_dim", LAMP_DIM)
    # the tables and their benches (the places of the diners: ship_spec's mess posts and the actors of build_messhall)
    for xc in t["x_centres"]:
        for yc in t["y_centres"]:
            lx, ly = loc(xc, yc)
            place(b, lx, ly, 0, mess_table, t["length"], t["width"], t["height"])
            for side in (-1, 1):
                place(b, lx, ly + side * t["bench_offset"] * -1.0, 0, mess_bench, t["length"] - 0.2, t["bench_width"], t["bench_height"], LEATHER_NAVY if (int(xc) + int(yc)) % 2 else LEATHER_OX)
    # the serving line on the port wall (y 20), the kitchen behind its pass
    cx0, cx1 = px0, px1
    serving_line(b, cx0, cx1, yf, HW - g["y_counter"], g["height"])
    kitchen(b, cx0, cx1, 2 * HW, 2 * HW + 2.8)
    ex = (cx0 + cx1) / 2
    b.emit.screen((ex, yf - 0.03, 2.95), 5.6, 0.72, MENU, (0, -1, 0))                                  # the menu board over the pass (the live face)
    b.body.box((cx0 + 0.9, yf - 0.06, 2.55), (cx1 - 0.9, yf - 0.03, 3.35), STRUCT)
    # the drinks station on the starboard wall: counter, urn, dispensers, cups on a rack, a shelf of mugs behind
    dx0, dx1 = loc(dr["x0"], 0)[0], loc(dr["x1"], 0)[0]
    dy1 = HW - dr["y_counter"] + dr["depth"] / 2
    b.body.box((dx0, yn, 0.0), (dx1, dy1, dr["height"] - 0.04), COMPOSITE)
    b.body.box((dx0 - 0.03, yn, dr["height"] - 0.04), (dx1 + 0.03, dy1 + 0.03, dr["height"]), STEEL)
    ux = dx0 + 0.7
    b.body.cyl((ux, yn + 0.35, dr["height"]), (ux, yn + 0.35, dr["height"] + 0.62), 0.22, STEEL, seg=22)
    b.fine.cyl((ux, yn + 0.35, dr["height"] + 0.62), (ux, yn + 0.35, dr["height"] + 0.68), 0.12, SL.RUBBER, seg=16)
    place(b, dx0 + 2.6, yn + 0.4, 90, G_coffee, z=dr["height"])
    for r_ in range(2):
        for k in range(8):
            b.fine.cyl((dx1 - 0.3 - k * 0.14, yn + 0.55 + r_ * 0.14, dr["height"]), (dx1 - 0.3 - k * 0.14, yn + 0.55 + r_ * 0.14, dr["height"] + 0.09), 0.04, CERAMIC, seg=10, r2=0.032)
    for k in range(3):
        b.fine.box((dx0 + 0.1, yn, 1.5 + k * 0.4), (dx1 - 0.1, yn + 0.28, 1.53 + k * 0.4), STEEL)
        for j in range(int((dx1 - dx0) / 0.2)):
            b.fine.cyl((dx0 + 0.2 + j * 0.2, yn + 0.14, 1.53 + k * 0.4), (dx0 + 0.2 + j * 0.2, yn + 0.14, 1.62 + k * 0.4), 0.036, (CERAMIC, LEATHER_NAVY, SL.LAMINATE)[(j + k) % 3], seg=8)
    # the water fountain, the notice board and the herb wall further aft on the starboard wall
    place(b, 10.3, yn, 0, _fountain)
    place(b, 15.5, yn + 0.003, 90, DC.notice_board, 4.2, 1.2, 3, z=1.8)
    herb_wall(b, 20.0, 27.0, yn)
    # the aft wall: the fleet news and the memorial in frames with a picture light; a planting between them with a money tree
    for key, slot in (("news", NEWS), ("memorial", MEMORIAL)):
        s = sc[key]
        yc = HW - (s["y0"] + s["y1"]) / 2
        w_, h_ = s["y1"] - s["y0"], s["z1"] - s["z0"]
        zc = (s["z0"] + s["z1"]) / 2
        b.body.box((xr - 0.1, yc - w_ / 2 - 0.14, s["z0"] - 0.14), (xr, yc + w_ / 2 + 0.14, s["z1"] + 0.14), STRUCT)
        b.fine.box((xr - 0.12, yc - w_ / 2 - 0.05, s["z0"] - 0.05), (xr - 0.1, yc + w_ / 2 + 0.05, s["z1"] + 0.05), TRIM)
        b.emit.screen((xr - 0.105, yc, zc), w_, h_, slot, (-1, 0, 0))
        b.body.box((xr - 0.16, yc - w_ / 2 - 0.14, s["z1"] + 0.2), (xr, yc + w_ / 2 + 0.14, s["z1"] + 0.24), TRIM)
        b.emit.lamp_box((xr - 0.15, yc - w_ / 2, s["z1"] + 0.19), (xr - 0.02, yc + w_ / 2, s["z1"] + 0.2), "white_warm", LAMP)
    with b.at(T(xr - 0.4, HW, 0.0)):
        PL.planter_bed(b, 2.6, 0.7, 0.55, 3, True, 0.7, OAK)
    for yy in (yn + 1.0, yf - 1.0):
        place(b, xr - 0.8, yy, 0, PL.floor_tree, "pachira_d", 0.32, CERAMIC, 1.0, rng.uniform(0, 360))
    # banners on the frames, wall lights between: the Navy's colours
    for k, x in enumerate((RIBS[0] + 2.375, RIBS[2] + 2.375, RIBS[4] + 2.375)):
        for yw, yaw in ((yn + 0.08, 90), (yf - 0.08, -90)):
            if yw > 10 and px0 - 0.5 < x < px1 + 0.5:
                continue
            place(b, x, yw, yaw, banner, 0.7, 2.1, z=1.0)
    b.emit.label_fit((xr - 0.03, HW, 3.55), 4.0, "room_mess", (-1, 0, 0)) if "room_mess" in SL.LABELS else None


def G_coffee(b: SParts) -> None:
    import ship_furniture2 as G
    G.coffee_machine(b)


def _fountain(b: SParts) -> None:
    """A wall water fountain (origin at the wall, x out from the wall... here: along the starboard wall): a steel basin with a spout and a button."""
    b.body.box((-0.3, 0.0, 0.0), (0.3, 0.4, 0.95), STEEL)
    b.fine.box((-0.25, 0.04, 0.95), (0.25, 0.4, 0.99), SL.DGLASS)
    b.fine.cyl((0.0, 0.05, 0.99), (0.0, 0.05, 1.12), 0.012, TRIM, seg=8)


def banner(b: SParts, w: float = 0.7, h: float = 2.1) -> None:
    """A hanging banner on a wall facing +x (origin: top of its back edge, centre; hangs down by h): navy cloth with a gold stripe and a small crest, on a brass rod."""
    b.fine.cyl((0.04, -w / 2 - 0.04, 0.0), (0.04, w / 2 + 0.04, 0.0), 0.012, BRASS, seg=8)
    b.soft.swatch_box((0.02, -w / 2, -h), (0.045, w / 2, -0.02), "navy")
    b.soft.swatch_box((0.045, -0.04, -h + 0.05), (0.05, 0.04, -0.2), "mustard")
    b.soft.swatch_box((0.045, -w / 2 + 0.05, -h + 0.02), (0.05, w / 2 - 0.05, -h + 0.07), "mustard")
    b.emit.label((0.052, 0.0, -0.8), 0.28, 0.28, (1, 0, 0), "pict_navy") if "pict_navy" in SL.LABELS else None


def herb_wall(b: SParts, x0: float, x1: float, y_wall: float) -> None:
    """The herbs along the starboard wall: three shelves of troughs with basil, mint and chives under a bar of grow light (the old hydroponic trough, grown up)."""
    w = x1 - x0
    for k, z in enumerate((1.1, 1.65, 2.2)):
        b.body.box((x0, y_wall, z), (x1, y_wall + 0.34, z + 0.04), STEEL)
        b.fine.box((x0, y_wall + 0.3, z + 0.04), (x1, y_wall + 0.34, z + 0.2), STEEL)
        b.soft.box((x0 + 0.03, y_wall + 0.04, z + 0.04), (x1 - 0.03, y_wall + 0.3, z + 0.12), SL.SOIL)
        for j in range(int(w / 0.34)):
            with b.at(T(x0 + 0.2 + j * 0.34, y_wall + 0.17, z + 0.12)):
                if (j + k) % 3 == 0:
                    PL.grain_clump(b, 0.3, 6, j + k * 9)
                else:
                    PL.herb_bush(b, 0.2, j + k * 7)
        b.emit.lamp_box((x0 + 0.05, y_wall + 0.06, z + 0.5), (x1 - 0.05, y_wall + 0.30, z + 0.505), "white_warm", LAMP_HOT)
        b.fine.box((x0 + 0.05, y_wall + 0.06, z + 0.505), (x1 - 0.05, y_wall + 0.30, z + 0.53), TRIM)


def hall(name: str = "SM_MESS_Hall"):
    """The Mess Hall's mesh in the hall's frame (the forward wall at x 0, the hall running aft to x -38, y +-10; the lift's gate at y 0)."""
    SL.load_labels()
    b = SParts(bevel=0.005, fine_bevel=0.0)
    with b.at(frame(0.0, HW, 0.0, 180.0)):
        build_room(b)
    return b.build(name, uv_meter=1.0)


# ------------------------------------------------------------------------------------------------------------------------------------- preview
def preview(out: str, samples: int = 24) -> None:
    import ship_preview as SP
    import bridge3_preview as PV
    import bpy
    obj = hall()
    SP.setup(1600, 900, samples, exposure=0.0, world=(0.05, 0.052, 0.058))
    for slot, page in ((NEWS, "Mess_News"), (MEMORIAL, "Mess_Memorial"), (MENU, "Mess_Menu")):
        try:
            PV.screen_mat(slot, page, 2.4)
        except Exception:
            pass
    SP.instance(obj, (0, 0, 0), 0)
    obj.hide_render = True
    # the four rows of tables' lights as in build_messhall.py (actors: no gain), plus the counter and forward fields, scaled like the preview's formula (lumens * 0.03 * gain)
    gain = 1.5
    for yc in D["tables"]["y_centres"]:
        SP.rect_light(f"row{yc}", (-23.4, yc, H - 0.1), (27.0, 0.6), 28000 * 0.03 * gain * (1 + 0.4 * math.log10(1 + 16)), (1.0, 0.93, 0.84))
    SP.rect_light("counter", (-5.5, -7.6, H - 0.1), (7.0, 1.2), 14000 * 0.03 * gain, (1.0, 0.95, 0.9))
    SP.rect_light("fwd", (-5.5, 5.5, H - 0.1), (6.0, 6.0), 12000 * 0.03 * gain, (1.0, 0.93, 0.84))
    SP.rect_light("bounce", (-19.0, 0.0, H - 0.4), (36.0, 18.0), 0.35 * 36 * 18, (1.0, 0.96, 0.9), direction=(0, 0, 1))
    views = {"gate": ((-1.2, 0.0, 1.65), (-24.0, 0.0, 1.4), 82), "port": ((-14.0, 4.0, 1.65), (-8.0, -9.5, 1.5), 80), "stbd": ((-12.0, -4.0, 1.65), (-16.0, 9.5, 1.5), 80),
             "aft": ((-9.0, 0.0, 1.7), (-38.0, 0.0, 1.7), 78), "tables": ((-6.0, -9.0, 1.7), (-26.0, 5.0, 0.9), 76), "kitchen": ((-4.5, -4.0, 1.65), (-5.5, -11.0, 1.6), 70)}
    for n, (eye, tgt, fov) in views.items():
        cam = SP.look_camera(n, eye, tgt, fov)
        SP.render(cam, os.path.join(out, f"mess_{n}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        preview(out, int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24)
    else:
        o = hall()
        print("MESS_HALL tris", sum(len(p.vertices) - 2 for p in o.data.polygons), "slots", len(o.data.materials))
