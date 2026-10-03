"""ASN Aquila interior kit (ARTE-INTERNI): the wet rooms — the heads and showers (thirty-seven of them in the ship) and the laundries (sixteen). The same layouts as ship_rooms_service.py had
(stalls along both side walls, two basin islands in the middle, three shower stalls at the far end; washers along both side walls, two folding tables in the middle) but with what such rooms
have: stall partitions on posts with a gap at the floor and a lock that shows red or green, toilets with a cistern, a seat and a roll of paper, basins sunk into counters with taps, soap and
paper-towel dispensers, a mirror with a light, hand dryers, shower stalls with tile trays, a pleated curtain, a rail and a shower head, a bench and a hook; front-loading washers with a round
door, a detergent drawer and a lit display, dryers stacked on the washers on one side, baskets of clothes, a folding table with stacks of folded things, a clothes rail with hangers and
garments, an ironing board, a shelf of detergent, a notice board and a plant. The pieces follow the kit's conventions (origin on the floor, +x the front, `SParts`).
"""
from __future__ import annotations

import math
import random

import ship_decor as DC
import ship_furniture as F
import ship_mk as MK
import ship_plants as PL
import ship_spec as SPEC
from bridge3_lib import T
from ship_lib import (BRASS, CERAMIC, COMPOSITE, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM, PERF, PLASTER_TEAL, RUBBER, STEEL, STRUCT, SWATCH, TILE,
                      TILE_FLOOR, TILE_WALL, TRIM, WEAVE_TEAL, WHITE_GLOSS, SParts)
from ship_rooms import Style, WF, WS, build_shell, place, wall_label

TEAL = PLASTER_TEAL


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ------------------------------------------------------------------------------------------------------------------------------------------------------ pieces
def toilet(b: SParts, seed: int = 1) -> None:
    """A toilet facing +x (origin: the middle of the bowl's foot): a rounded bowl on a plinth with a seat and a lid, a cistern behind it with a flush plate, a roll of paper on a holder at the
    wall, a floor drain."""
    MK.rbox(b.soft, (-0.06, -0.19, 0.0), (0.4, 0.19, 0.4), 0.06, CERAMIC, 2)
    b.soft.box((0.02, -0.15, 0.4), (0.38, 0.15, 0.415), WHITE_GLOSS)
    b.fine.box((0.06, -0.11, 0.416), (0.34, 0.11, 0.42), STRUCT)
    MK.rbox(b.soft, (-0.28, -0.2, 0.3), (-0.08, 0.2, 0.78), 0.03, CERAMIC, 1)
    b.fine.box((-0.08, -0.05, 0.62), (-0.07, 0.05, 0.7), STEEL)
    b.fine.cyl((-0.2, 0.24, 0.64), (-0.2, 0.3, 0.64), 0.006, STEEL, seg=5)
    b.soft.cyl((-0.2, 0.3, 0.64), (-0.2, 0.37, 0.64), 0.055, WHITE_GLOSS, seg=10)


def basin_island(b: SParts, w: float = 2.8, seed: int = 1) -> None:
    """A washing island, its long axis along y (origin: its middle on the floor): a counter of white laminate on a recessed plinth with a steel top, three ceramic basins a side with
    chromed taps, a bar of mirror down the middle with a light on top, soap and paper-towel dispensers at its ends, a waste bin under each end."""
    hw = w / 2
    b.body.box((-0.27, -hw + 0.1, 0.0), (0.27, hw - 0.1, 0.07), STRUCT)
    MK.rbox(b.soft, (-0.3, -hw, 0.07), (0.3, hw, 0.82), 0.012, WHITE_GLOSS, 1)
    b.body.box((-0.34, -hw - 0.03, 0.82), (0.34, hw + 0.03, 0.86), STEEL)
    n = 3
    for sx in (-1, 1):
        for k in range(n):
            y = -hw + (k + 0.5) * w / n
            MK.lathe(b.fine, [(0.1, 0.84), (0.19, 0.862), (0.2, 0.866), (0.17, 0.866), (0.1, 0.8), (0.08, 0.79)], (sx * 0.17, y, 0.0), CERAMIC, seg=14)
            MK.rod(b.fine, (sx * 0.06, y, 0.86), (sx * 0.06, y, 1.0), 0.012, 0.012, STEEL, 6)
            MK.rod(b.fine, (sx * 0.06, y, 1.0), (sx * 0.14, y, 0.98), 0.012, 0.012, STEEL, 6)
            b.fine.box((sx * 0.05 - 0.015, y + 0.12, 0.86), (sx * 0.05 + 0.015, y + 0.15, 0.93), TEAL)                 # the soap pump
    b.fine.box((-0.02, -hw, 1.2), (0.02, hw, 2.0), STEEL)                                                         # the mirror
    b.fine.box((-0.04, -hw - 0.02, 1.98), (0.04, hw + 0.02, 2.02), TRIM)
    b.emit.lamp_box((-0.035, -hw + 0.1, 2.02), (0.035, hw - 0.1, 2.05), "white_cool", LAMP)
    for sy in (-hw + 0.02, hw - 0.02):
        for sx in (-1, 1):
            MK.rbox(b.soft, (sx * 0.05 - 0.04, sy - 0.08, 1.05), (sx * 0.05 + 0.04, sy + 0.08, 1.35), 0.01, WHITE_GLOSS, 1)


def shower_stall(b: SParts, w: float = 2.0, d: float = 1.3, seed: int = 1) -> None:
    """A shower stall against the far wall (origin: the middle of its front edge on the floor, +x towards the stall's back — turn it to face the room): a tile tray with a drain and a step,
    three tiled walls with a band of colour, a shower head on a rail with a mixer, a niche with a bottle, a fold-down bench, a hook and a pleated curtain on a rail across the front."""
    rng = random.Random(seed)
    b.body.box((0.0, -w / 2, 0.0), (d, w / 2, 0.06), TILE_FLOOR)
    b.fine.box((0.0, -w / 2, 0.06), (0.04, w / 2, 0.12), STEEL)                                                   # the step
    b.fine.cyl((d * 0.6, 0.0, 0.06), (d * 0.6, 0.0, 0.065), 0.07, STEEL, seg=12)                                  # the drain
    b.body.box((d - 0.03, -w / 2, 0.0), (d, w / 2, 2.2), TILE_WALL)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((0.0, sy, 0.0), (d, sy + 0.03, 2.2), TILE_WALL)
    b.emit.lamp_box((d - 0.03, -w / 2 + 0.03, 1.2), (d - 0.025, w / 2 - 0.03, 1.23), "cyan_dim", LAMP_DIM)         # the coloured band
    b.fine.cyl((d - 0.05, 0.3, 0.9), (d - 0.05, 0.3, 2.1), 0.012, STEEL, seg=8)                                   # the rail, the mixer, the head
    b.fine.cyl((d - 0.05, 0.3, 1.1), (d - 0.12, 0.3, 1.1), 0.02, STEEL, seg=8)
    b.fine.cyl((d - 0.05, 0.3, 2.0), (d - 0.3, 0.3, 2.1), 0.012, STEEL, seg=8)
    b.fine.cyl((d - 0.3, 0.3, 2.1), (d - 0.3, 0.3, 2.08), 0.09, STEEL, seg=14)
    b.fine.box((d - 0.06, -0.5, 1.15), (d - 0.03, -0.2, 1.4), STRUCT)                                              # a niche with a bottle
    b.soft.swatch_cyl((d - 0.08, -0.35, 1.15), (d - 0.08, -0.35, 1.32), 0.03, rng.choice(("m_teal", "m_white", "teal")), seg=8)
    b.fine.box((d - 0.25, -w / 2 + 0.03, 0.45), (d - 0.03, -w / 2 + 0.45, 0.48), WHITE_GLOSS)                     # the fold-down bench
    b.fine.cyl((d - 0.03, w / 2 - 0.35, 1.7), (d - 0.08, w / 2 - 0.35, 1.7), 0.01, STEEL, seg=6)                   # a hook
    zt = 2.05
    b.fine.cyl((0.04, -w / 2, zt), (0.04, w / 2, zt), 0.009, STEEL, seg=6)
    n = 11
    cw = w * 0.45 / n
    for j in range(n):                                                                                            # the curtain: pleats of pale teal, drawn to the right
        off = 0.012 * (1 if j % 2 else -1)
        y0 = w / 2 - 0.02 - (j + 1) * cw
        b.soft.box((0.035 + off, y0, 0.18), (0.05 + off, y0 + cw * 0.95, zt - 0.02), WEAVE_TEAL)


def hand_dryer(b: SParts) -> None:
    """A wall hand dryer (origin: the middle of its back plate, facing +x): a white body with a nozzle slot and a lit rim."""
    MK.rbox(b.soft, (0.0, -0.14, -0.15), (0.17, 0.14, 0.15), 0.02, WHITE_GLOSS, 1)
    b.fine.box((0.17, -0.08, -0.09), (0.19, 0.08, -0.07), STRUCT)
    b.emit.lamp_box((0.17, -0.1, 0.13), (0.172, 0.1, 0.14), "green", LAMP_DIM)


def washer(b: SParts, mat: str = WHITE_GLOSS, dryer: bool = False) -> None:
    """A front-loading washing machine (or dryer: `dryer`) facing +x, 0.62 wide, 0.65 deep, 0.9 high: a rounded body on four feet, a round glass door in a steel ring, a control panel with a
    lit display and a dial, a detergent drawer."""
    for sx in (-0.26, 0.26):
        for sy in (-0.24, 0.24):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.03), 0.02, RUBBER, seg=6)
    MK.rbox(b.soft, (-0.31, -0.31, 0.03), (0.31, 0.31, 0.9), 0.02, mat, 1)
    b.fine.box((0.31, -0.28, 0.76), (0.318, 0.28, 0.88), STRUCT)
    b.emit.lamp_box((0.318, -0.2, 0.8), (0.32, 0.0, 0.84), "cyan_dim", LAMP_DIM)
    b.fine.cyl((0.318, 0.12, 0.82), (0.325, 0.12, 0.82), 0.03, STEEL, seg=10)
    if not dryer:                                                                                                  # the detergent drawer
        b.fine.box((0.31, -0.27, 0.69), (0.316, -0.08, 0.74), STEEL)
    b.fine.cyl((0.31, 0.0, 0.4), (0.33, 0.0, 0.4), 0.235, STEEL, seg=20)
    b.fine.cyl((0.33, 0.0, 0.4), (0.338, 0.0, 0.4), 0.2, DGLASS, seg=20)
    b.fine.cyl((0.338, 0.0, 0.4), (0.342, 0.0, 0.4), 0.09, STRUCT, seg=12)


def washer_tower(b: SParts, mat: str = WHITE_GLOSS) -> None:
    """A washer with a dryer stacked on it (1.8 m): the pair on one frame."""
    washer(b, mat, False)
    with b.at(T(0.0, 0.0, 0.9)):
        washer(b, mat, True)


def laundry_basket(b: SParts, seed: int = 1) -> None:
    """A laundry basket, 0.5 across: a tapered wicker-coloured tub with two handles, heaped with clothes of several colours."""
    rng = random.Random(seed)
    b.soft.cyl((0, 0, 0.0), (0, 0, 0.34), 0.22, "MI_SHIP_Cork", seg=14, r2=0.26)
    for sy in (-0.27, 0.27):
        b.fine.box((-0.04, sy - 0.01, 0.26), (0.04, sy + 0.01, 0.3), STRUCT)
    for k in range(5):
        a = rng.uniform(0, 6.28)
        r = rng.uniform(0.0, 0.14)
        b.soft.paint(MK.puff(b.soft, (r * math.cos(a), r * math.sin(a), 0.34 + rng.uniform(0.0, 0.06)), (0.12, 0.1, 0.07), SWATCH, e=0.7, nu=8, nv=5), rng.choice(("navy", "teal", "cream", "rust", "mustard", "denim", "white")))


def folding_table(b: SParts, w: float = 2.6, d: float = 0.9, h: float = 0.9, seed: int = 1) -> None:
    """A steel folding table (origin: its middle on the floor) with stacks of folded clothes, a basket under it and a rail for the finished things; along x."""
    rng = random.Random(seed)
    b.body.box((-w / 2, -d / 2, h - 0.04), (w / 2, d / 2, h), STEEL)
    for sx in (-w / 2 + 0.1, w / 2 - 0.1):
        for sy in (-d / 2 + 0.08, d / 2 - 0.08):
            MK.rod(b.fine, (sx, sy, 0.0), (sx, sy, h - 0.04), 0.02, 0.025, STEEL, 8)
    b.fine.box((-w / 2 + 0.1, -d / 2 + 0.08, 0.2), (w / 2 - 0.1, d / 2 - 0.08, 0.22), STEEL)
    for k in range(4):
        x = -w / 2 + 0.35 + k * (w - 0.7) / 3
        for j in range(rng.randint(2, 5)):
            b.soft.swatch_box((x - 0.18, -0.15 + rng.uniform(-0.1, 0.1), h + j * 0.045), (x + 0.18, 0.15 + rng.uniform(-0.1, 0.1), h + (j + 1) * 0.045), rng.choice(("navy", "teal", "cream", "rust", "mustard", "denim", "white", "slate")))


def clothes_rail(b: SParts, w: float = 1.6, seed: int = 1) -> None:
    """A rolling rail facing +x: two posts on castors, a bar at 1.6 m, hangers with shirts and trousers of several colours hanging from it (w along y)."""
    rng = random.Random(seed)
    for sy in (-w / 2, w / 2):
        b.fine.cyl((0, sy, 0.0), (0, sy, 1.62), 0.014, STEEL, seg=6)
        b.fine.cyl((-0.2, sy, 0.03), (0.2, sy, 0.03), 0.012, STEEL, seg=6)
        for sx in (-0.2, 0.2):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.05), 0.025, RUBBER, seg=6)
    b.fine.cyl((0, -w / 2, 1.62), (0, w / 2, 1.62), 0.014, STEEL, seg=6)
    y = -w / 2 + 0.12
    while y < w / 2 - 0.1:
        col = rng.choice(("navy", "teal", "cream", "rust", "mustard", "denim", "white", "slate", "forest"))
        if rng.random() < 0.7:
            b.soft.swatch_box((-0.03, y, 0.9 + rng.uniform(0, 0.1)), (0.03, y + 0.06, 1.58), col)                      # a shirt
        else:
            b.soft.swatch_box((-0.04, y, 0.5), (0.04, y + 0.08, 1.58), col)                                         # trousers
        y += 0.075


def ironing_board(b: SParts) -> None:
    """An ironing board with an iron on it (origin: its middle, the narrow end at +x)."""
    b.soft.box((-0.55, -0.18, 0.85), (0.5, 0.18, 0.88), FABRIC_SAND)
    for sy in (-1, 1):
        MK.rod(b.fine, (-0.3, sy * 0.15, 0.85), (0.3, sy * -0.15, 0.0), 0.012, 0.012, STEEL, 6)
        MK.rod(b.fine, (0.3, sy * 0.15, 0.85), (-0.3, sy * -0.15, 0.0), 0.012, 0.012, STEEL, 6)
    MK.rbox(b.soft, (-0.4, -0.06, 0.88), (-0.2, 0.06, 0.95), 0.015, TEAL, 1)
    b.fine.box((-0.42, -0.07, 0.88), (-0.18, 0.07, 0.89), STEEL)


def detergent_shelf(b: SParts, w: float = 1.6, seed: int = 1) -> None:
    """A wall shelf unit facing +x (w along y, 1.7 m high, three shelves): bottles and boxes of detergent, softener and stain remover."""
    rng = random.Random(seed)
    b.body.box((-0.14, -w / 2, 0.0), (-0.12, w / 2, 1.7), STEEL)
    for z in (0.5, 1.0, 1.5):
        b.body.box((-0.14, -w / 2, z), (0.12, w / 2, z + 0.02), STEEL)
        y = -w / 2 + 0.06
        while y < w / 2 - 0.1:
            if rng.random() < 0.5:
                bw = rng.uniform(0.12, 0.2)
                b.soft.swatch_box((-0.1, y, z + 0.02), (0.08, y + bw, z + 0.02 + rng.uniform(0.15, 0.28)), rng.choice(("teal", "white", "denim", "forest", "mustard", "m_teal")))
                y += bw + 0.02
            else:
                for j in range(2):
                    b.soft.swatch_cyl((-0.02, y + 0.045, z + 0.02), (-0.02, y + 0.045, z + 0.26), 0.045, rng.choice(("teal", "white", "denim", "mustard", "rose")), seg=8)
                    y += 0.095
                y += 0.02


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the rooms
def heads(name: str = "SM_SHIP_Heads"):
    """12 x 16 x 3.4: stalls along both side walls (partitions of teal laminate on steel posts with a gap at the floor, a door with a lock that shows red or green, a toilet with its cistern and
    paper), two washing islands in the middle (three basins a side, a mirror with a light), three shower stalls at the far end with their curtains, hand dryers and a notice by the door, a
    cleaning cart in the corner."""
    spec, L, D, H = _dims("heads")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, Style(floor=TILE, floor_mode="covering", wall_lo=TILE, wall_hi=TILE, wain_h=2.2, ceil=IVORY, accent="cyan_dim", strip="white_cool", ribs=False))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for side in (0, 1):
        sgn = 1 if side == 0 else -1
        xw = xl if side == 0 else xr
        xa, xb = sorted((xw, xw + sgn * 1.6))
        for k in range(5):                                                                                       # partitions: laminate with a gap under it, a steel post at the aisle end
            b.soft.box((xa, 3.2 + k - 0.02, 0.15), (xb, 3.2 + k + 0.02, 1.9), TEAL)
            b.body.box((xw + sgn * 1.6 - 0.025, 3.2 + k - 0.025, 0.0), (xw + sgn * 1.6 + 0.025, 3.2 + k + 0.025, 1.95), STEEL)
        for k in range(4):
            y0 = 3.2 + k
            place(b, xw + sgn * 0.42, y0 + 0.5, 0.0 if side == 0 else 180.0, toilet, k)
            xd = xw + sgn * 1.6
            b.soft.box((xd - 0.02, y0 + 0.03, 0.15), (xd + 0.02, y0 + 0.97, 1.85), TEAL)                        # the door
            b.fine.box((xd - 0.03, y0 + 0.08, 0.15), (xd + 0.03, y0 + 0.11, 1.85), TRIM)
            b.emit.lamp_box((xd - 0.03 * sgn - 0.005, y0 + 0.85, 1.4), (xd - 0.03 * sgn + 0.005, y0 + 0.9, 1.45), "green" if (k + side) % 3 else "red", LAMP_DIM)
            b.fine.box((xd - 0.03 * sgn - 0.006, y0 + 0.82, 1.0), (xd - 0.03 * sgn + 0.006, y0 + 0.92, 1.1), STEEL)  # the lock
            b.fine.box((xa + 0.02, y0 + 0.2, 1.95), (xb - 0.02, y0 + 0.8, 1.99), PERF)                                # a vent over the stall
    for k, y in enumerate((6.4, 9.4)):
        place(b, 6.0, y, 0, basin_island, 2.8, k)
    place(b, 6.0, 12.2, 0, F.potted_plant, 0.9, 5)
    for k in range(3):                                                                                           # the showers along the far wall, facing the room
        x = xl + 0.9 + k * 3.6
        place(b, x, yf - 1.3, 90, shower_stall, 2.0, 1.3, k)
    for y in (8.4, 9.8):                                                                                         # hand dryers by the islands
        place(b, xr - 0.02, y, 180, hand_dryer, z=1.3)
    wall_label(b, 6.0, WF + 0.02, 2.05, (0, 1, 0), "pict_heads", 0.3, 0.3)
    return b.build(name)


def laundry(name: str = "SM_SHIP_Laundry"):
    """12 x 16 x 3.4: a wall of washers (a dryer stacked on every one) down the left, plain washers down the right, two folding tables with stacks of clothes in the middle (the workers
    stand between them), baskets, a clothes rail, an ironing board, shelves of detergent along the far wall, a notice board, a plant."""
    spec, L, D, H = _dims("laundry")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, Style(floor=TILE_FLOOR, floor_mode="covering", wall_lo=TILE, wall_hi=COMPOSITE, wain_h=1.4, ceil=IVORY, accent="cool_dim", strip="white_cool", ribs=False))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(6):
        y = 3.2 + k * 1.05
        place(b, xl + 0.34, y, 0, washer_tower, STEEL if k % 2 else WHITE_GLOSS)
        place(b, xr - 0.34, y, 180, washer, WHITE_GLOSS)
    for k in range(3):
        place(b, xr - 1.3, 3.2 + k * 2.1 + 0.5, 20 * k, laundry_basket, k + 3)
    place(b, 6.0, 6.5, 0, folding_table, 2.6, 0.9, 0.9, 1)
    place(b, 6.0, 9.5, 0, folding_table, 2.6, 0.9, 0.9, 2)
    place(b, 3.0, 12.0, 90, clothes_rail, 1.6, 3)
    place(b, 9.0, 12.4, -60, ironing_board)
    for k in range(3):
        place(b, 2.6 + 2.8 * k, yf - 0.2, -90, detergent_shelf, 1.6, 4 + k)
    place(b, xl + 0.02, 1.6, 0, DC.notice_board, 0.9, 0.7, 6, z=1.6)
    place(b, xr - 0.6, yf - 0.6, 0, F.potted_plant, 1.0, 3)
    wall_label(b, 6.0, WF + 0.02, 2.05, (0, 1, 0), "room_laundry", 0.9)
    return b.build(name)
