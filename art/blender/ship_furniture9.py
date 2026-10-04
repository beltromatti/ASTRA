"""ASN Aquila interior kit (NAVE-3): furniture of the rooms the redesign adds — a dental clinic, a morgue, a brig, a chapel, a barber's, a simulator, the hull's lifepods and airlocks, the
life-support plants, a lobby's kiosk. Same conventions as ship_furniture.py: every function builds one piece in ITS OWN frame (origin on the floor, x = the piece's front, y = its left,
z up) into a SParts; the caller places it with ship_rooms.place()."""
from __future__ import annotations

import math
import random

from bridge3_lib import T
import ship_furniture as F
import ship_furniture3 as H3
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, GLASS, IVORY, LAMINATE,
                      LAMP, LAMP_DIM, LAMP_HOT, LEATHER, PAINT_RED, RUBBER, STEEL, STRUCT, TILE, TRIM, WOOD, SParts)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- medical
def dental_chair(b: SParts) -> None:
    """A dental chair, the patient looking along +x, reclined: a base and column, a seat, a back tilted 28 degrees with a headrest at -x... the head is at -x, the feet at +x."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.07), 0.38, STRUCT, seg=18)
    b.body.cyl((0, 0, 0.07), (0, 0, 0.42), 0.10, STEEL, seg=12)
    b.body.box((-0.30, -0.28, 0.40), (0.40, 0.28, 0.48), STEEL)
    b.soft.box((-0.28, -0.26, 0.48), (0.40, 0.26, 0.58), LEATHER)
    ang = math.radians(28.0)
    ca, sa = math.cos(ang), math.sin(ang)
    b.soft.box((-0.30 - 0.62 * ca, -0.26, 0.54 + 0.62 * sa - 0.02), (-0.28, 0.26, 0.60 + 0.02), LEATHER)               # the back, raked up to the head
    b.soft.box((-0.30 - 0.82 * ca, -0.13, 0.54 + 0.78 * sa + 0.02), (-0.30 - 0.58 * ca, 0.13, 0.54 + 0.78 * sa + 0.22), LEATHER)       # the headrest
    b.body.box((0.38, -0.2, 0.30), (0.62, 0.2, 0.36), STEEL)                                                          # the footrest
    b.soft.box((0.40, -0.18, 0.36), (0.62, 0.18, 0.42), LEATHER)
    for sy in (-0.30, 0.30):                                                                                         # arms
        b.body.box((-0.1, sy - 0.03, 0.58), (0.3, sy + 0.03, 0.62), STEEL)
        b.fine.cyl((0.1, sy, 0.48), (0.1, sy, 0.58), 0.02, TRIM, seg=6)


def dental_unit(b: SParts) -> None:
    """The delivery unit that goes with the chair (its own frame: facing -x, origin under its column): a column, an arm with a tray of instruments, a lamp on a boom, a spittoon bowl, a screen."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.06), 0.28, STRUCT, seg=16)
    b.body.cyl((0, 0, 0.06), (0, 0, 1.0), 0.06, STEEL, seg=10)
    b.body.box((-0.55, -0.25, 0.98), (0.1, 0.25, 1.04), STEEL)                                                         # the tray
    for k in range(5):
        b.fine.cyl((-0.5 + 0.08 * k, -0.2 + 0.1 * k, 1.04), (-0.5 + 0.08 * k, -0.2 + 0.1 * k, 1.07), 0.012, TRIM, seg=6)
    b.fine.cyl((-0.45, -0.2, 1.04), (-0.45, -0.2, 1.14), 0.01, RUBBER, seg=6)
    b.body.cyl((0, 0, 1.0), (0, 0, 1.85), 0.03, TRIM, seg=8)                                                          # the boom
    b.body.box((-0.9, -0.03, 1.85), (0.0, 0.03, 1.9), TRIM)
    b.body.box((-1.15, -0.2, 1.74), (-0.85, 0.2, 1.9), COMPOSITE)                                                      # the lamp head
    b.emit.lamp_box((-1.15, -0.16, 1.735), (-0.87, 0.16, 1.742), "white_cool", LAMP_HOT)
    b.body.box((0.1, 0.5, 0.0), (0.5, 0.8, 0.85), COMPOSITE)                                                           # the cuspidor cabinet and its bowl
    b.fine.cyl((0.3, 0.65, 0.85), (0.3, 0.65, 0.9), 0.14, TILE, seg=14)


def autopsy_table(b: SParts) -> None:
    """A steel table with a raised rim and a drain, long along x, on a pedestal; a lamp stalk at the head and a hanging scale."""
    b.body.box((-0.6, -0.4, 0.0), (0.6, 0.4, 0.1), STRUCT)
    b.body.box((-0.45, -0.25, 0.1), (0.45, 0.25, 0.8), STEEL)
    b.body.box((-1.05, -0.32, 0.8), (1.05, 0.32, 0.86), STEEL)
    for sy in (-0.32, 0.32):
        b.body.box((-1.05, sy - 0.015 if sy < 0 else sy - 0.015, 0.86), (1.05, sy + 0.015, 0.9), STEEL)
    b.body.box((-1.05, -0.32, 0.86), (-1.02, 0.32, 0.9), STEEL)
    b.fine.cyl((0.9, 0.0, 0.86), (0.9, 0.0, 0.9), 0.04, RUBBER, seg=8)
    b.body.cyl((-1.12, 0.0, 0.0), (-1.12, 0.0, 2.0), 0.03, TRIM, seg=8)
    b.body.box((-1.15, -0.3, 2.0), (-0.4, 0.3, 2.06), TRIM)
    b.emit.lamp_box((-1.0, -0.25, 1.994), (-0.5, 0.25, 2.0), "white_cool", LAMP_HOT)


def mortuary_wall(b: SParts, cols: int = 4, rows: int = 3) -> None:
    """A wall of refrigerated drawers facing +x (origin at its floor centre, the wall runs along y): a steel body, drawer fronts with handles, temperature read-outs and a tag each."""
    w = cols * 0.62
    b.body.box((-0.45, -w / 2, 0.0), (0.0, w / 2, rows * 0.62 + 0.3), STEEL)
    for r in range(rows):
        for c in range(cols):
            y0 = -w / 2 + c * 0.62 + 0.03
            z0 = 0.18 + r * 0.62
            b.body.box((0.0, y0, z0), (0.03, y0 + 0.56, z0 + 0.56), COMPOSITE)
            b.fine.box((0.03, y0 + 0.2, z0 + 0.4), (0.06, y0 + 0.36, z0 + 0.43), TRIM)
            b.emit.lamp_box((0.031, y0 + 0.06, z0 + 0.46), (0.034, y0 + 0.18, z0 + 0.5), "cyan", LAMP_DIM)
            b.emit.label((0.032, y0 + 0.28, z0 + 0.14), 0.3, 0.075, (1, 0, 0), "small_%02d" % ((r * cols + c) % 12))
    b.fine.box((-0.45, -w / 2, 0.0), (0.03, w / 2, 0.1), TRIM)


def hospital_trolley(b: SParts) -> None:
    """A mortuary trolley: a steel top on a frame with four castors, a folded sheet."""
    b.body.box((-1.0, -0.3, 0.74), (1.0, 0.3, 0.78), STEEL)
    for sx in (-0.9, 0.9):
        for sy in (-0.25, 0.25):
            b.fine.cyl((sx, sy, 0.1), (sx, sy, 0.74), 0.02, TRIM, seg=6)
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.1), 0.05, RUBBER, seg=8)
    b.body.box((-0.9, -0.25, 0.3), (0.9, 0.25, 0.33), STEEL)
    b.soft.box((-0.95, -0.28, 0.78), (0.4, 0.28, 0.82), BEDDING)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- security
def brig_cell(b: SParts, w: float = 3.2, d: float = 3.6, h: float = 3.2, lamp: str = "red") -> None:
    """A cell, facing +x (the bars are on the +x side; origin on the floor at the back wall's centre): the cell block's side walls, a bunk with a thin mattress, a steel toilet and basin,
    a bolted stool and table, a ceiling lamp in a cage, and a front of vertical bars with a sliding gate and a status lamp."""
    hw = w / 2
    b.body.box((-0.1, -hw, 0.0), (0.0, hw, h), COMPOSITE)
    for sy in (-hw, hw):
        b.body.box((-0.1, sy - 0.05, 0.0), (d, sy + 0.05, h), COMPOSITE)
    b.body.box((0.0, -hw + 0.55, 0.0), (1.9, -hw + 1.55, 0.42), STEEL)                                                # the bunk (a steel shelf, along x)
    b.soft.box((0.02, -hw + 0.6, 0.42), (1.86, -hw + 1.5, 0.5), FABRIC_GREY)
    b.body.box((0.0, hw - 0.7, 0.0), (0.5, hw - 0.1, 0.42), STEEL)                                                    # the toilet and basin in one steel unit
    b.fine.cyl((0.3, hw - 0.4, 0.42), (0.3, hw - 0.4, 0.46), 0.17, STEEL, seg=14)
    b.fine.box((0.0, hw - 1.3, 0.8), (0.4, hw - 0.9, 0.95), STEEL)
    b.fine.cyl((d - 0.7, hw - 0.4, 0.0), (d - 0.7, hw - 0.4, 0.42), 0.18, STEEL, seg=12)                              # a bolted stool
    b.emit.lamp_box((d / 2 - 0.2, -0.2, h - 0.06), (d / 2 + 0.2, 0.2, h - 0.04), "white_warm", LAMP)
    # the bars
    xb = d
    for k in range(int(w / 0.14) + 1):
        y = -hw + 0.05 + k * (w - 0.1) / int(w / 0.14)
        b.body.cyl((xb, y, 0.0), (xb, y, h), 0.02, STEEL, seg=6)
    b.body.box((xb - 0.04, -hw, 0.0), (xb + 0.04, hw, 0.08), STRUCT)
    b.body.box((xb - 0.04, -hw, 2.4), (xb + 0.04, hw, 2.5), STRUCT)
    b.body.box((xb - 0.04, -hw, h - 0.1), (xb + 0.04, hw, h), STRUCT)
    b.fine.box((xb + 0.04, -0.05, 1.0), (xb + 0.1, 0.05, 1.3), TRIM)                                                  # the lock
    b.emit.lamp_box((xb + 0.04, 0.12, 1.2), (xb + 0.07, 0.17, 1.26), lamp, LAMP)
    b.emit.label((xb + 0.05, -0.55, 2.25), 0.5, 0.125, (1, 0, 0), "eq_cell")


def counter_desk(b: SParts, w: float = 3.2, d: float = 0.9, h: float = 1.1) -> None:
    """A raised watch desk facing +x: a tall front, a lower work surface behind it, two screens, a radio, a key rack."""
    b.body.box((0.0, -w / 2, 0.0), (d, w / 2, h), COMPOSITE)
    b.body.box((-0.02, -w / 2 - 0.02, h), (d + 0.02, w / 2 + 0.02, h + 0.04), STEEL)
    b.body.box((-0.55, -w / 2 + 0.2, 0.0), (0.0, w / 2 - 0.2, 0.76), COMPOSITE)
    b.body.box((-0.57, -w / 2 + 0.18, 0.76), (0.0, w / 2 - 0.18, 0.79), LAMINATE)
    for k, tile in enumerate(("scr_lab", "scr_map", "scr_data")):
        yy = -0.75 + 0.75 * k
        b.fine.box((-0.42, yy - 0.28, 0.79), (-0.38, yy + 0.28, 1.16), TRIM)
        b.fine.box((-0.38, yy - 0.26, 0.82), (-0.372, yy + 0.26, 1.14), DGLASS)
        b.emit.label((-0.37, yy, 0.98), 0.5, 0.28, (1, 0, 0), tile)
    b.emit.lamp_box((d - 0.02, -w / 2 + 0.1, 0.1), (d, w / 2 - 0.1, 0.12), "amber", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- recreation
def pew(b: SParts, w: float = 2.6) -> None:
    """A chapel pew facing +x (ship_furn3.pew): walnut cheeks, a padded seat, a leaning back, a hymn-book shelf and a kneeler for the row behind."""
    import ship_furn3 as N3
    N3.pew(b, w)


def altar(b: SParts) -> None:
    """An altar facing +x (ship_furn3.altar): pale stone, a cloth, two brass candlesticks with lit candles, a bowl and a book."""
    import ship_furn3 as N3
    N3.altar(b)


def barber_chair(b: SParts) -> None:
    """A barber's chair facing +x (ARTE-INTERNI-2: ship_decor_salon.barber_chair): a chrome base and hydraulic column, a rolled leather seat, a tilted back with a headrest, padded arms on chrome
    posts, a footrest."""
    import ship_decor_salon as DS
    DS.barber_chair(b)


def sim_pod(b: SParts) -> None:
    """A cockpit simulator facing +x: a motion base on three actuators, a cockpit tub, a canopy of dark glass, a hand controller; an open hatch on the left."""
    b.body.box((-1.0, -0.9, 0.0), (1.0, 0.9, 0.12), STRUCT)
    for (x, y) in ((-0.7, -0.6), (-0.7, 0.6), (0.8, 0.0)):
        b.body.cyl((x, y, 0.12), (x, y, 0.55), 0.09, STEEL, seg=10)
        b.fine.cyl((x, y, 0.12), (x, y, 0.3), 0.12, TRIM, seg=10)
    b.body.box((-1.05, -0.85, 0.55), (1.05, 0.85, 0.65), COMPOSITE)
    b.body.box((-0.95, -0.7, 0.65), (0.4, 0.7, 1.05), IVORY)                                                      # the tub
    b.body.box((0.2, -0.45, 0.65), (1.0, 0.45, 0.95), IVORY)                                                       # the nose
    b.body.box((0.22, -0.55, 1.05), (0.3, 0.55, 1.5), DGLASS)                                                      # the windscreen (the canopy is hinged up, the seat open)
    b.fine.box((0.2, -0.58, 1.02), (0.32, 0.58, 1.06), TRIM)
    b.fine.box((0.2, -0.58, 1.46), (0.32, 0.58, 1.52), TRIM)
    for sy in (-0.58, 0.58):
        b.fine.box((0.2, sy - 0.03, 1.02), (0.32, sy + 0.03, 1.52), TRIM)
    b.soft.box((-0.7, -0.22, 0.65), (-0.3, 0.22, 0.85), FABRIC_NAVY)
    b.soft.box((-0.75, -0.22, 0.82), (-0.65, 0.22, 1.25), FABRIC_NAVY)
    b.emit.lamp_box((0.99, -0.1, 0.8), (1.0, 0.1, 0.84), "cyan", LAMP_DIM)
    b.emit.label((0.0, 0.705, 0.8), 0.6, 0.15, (0, 1, 0), "eq_sim")


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the hull
def lifepod(b: SParts, l: float = 3.0, w: float = 1.6, h: float = 1.8, side: int = -1) -> None:
    """An escape pod on its launch cradle, long along x (the nose at +x, the hatch and the portholes on the `side` (-1 = -y) side): a smooth ivory egg with an orange dorsal strake, three
    portholes in brushed rims, a round hatch with an orange rim and a green lamp, a nozzle cluster at the tail, and the cradle's rails and straps."""
    zc = 0.35 + h / 2
    sg = float(side)

    def skin(x: float, dz: float) -> float:                                                    # half-width of the egg at x, dz above its middle
        t = 1.0 - (x / (l / 2)) ** 2 - (dz / (h / 2)) ** 2
        return (w / 2) * math.sqrt(max(t, 0.0))
    b.body.sphere((0.0, 0.0, zc), w / 2, IVORY, seg=32, rings=18, squash=(l / w, 1.0, h / w))
    b.soft.box((-1.05, -0.06, zc + h / 2 - 0.1), (1.0, 0.06, zc + h / 2 + 0.02), CRATE_ORANGE)                          # the dorsal strake
    for k in range(3):                                                                              # portholes
        x, dz = 0.1 + 0.42 * k, 0.28
        y = sg * skin(x, dz)
        b.fine.cyl((x, y - 0.03 * sg, zc + dz), (x, y + 0.012 * sg, zc + dz), 0.17, TRIM, seg=14)
        b.fine.cyl((x, y + 0.012 * sg, zc + dz), (x, y + 0.02 * sg, zc + dz), 0.12, DGLASS, seg=14)
    xh, dzh = -0.85, -0.2                                                                           # the hatch
    yh = sg * skin(xh, dzh)
    b.fine.cyl((xh, yh - 0.05 * sg, zc + dzh), (xh, yh + 0.025 * sg, zc + dzh), 0.40, CRATE_ORANGE, seg=22)
    b.fine.cyl((xh, yh + 0.025 * sg, zc + dzh), (xh, yh + 0.04 * sg, zc + dzh), 0.33, CRATE_GREY, seg=22)
    b.fine.cyl((xh, yh + 0.04 * sg, zc + dzh), (xh, yh + 0.06 * sg, zc + dzh), 0.05, TRIM, seg=8)
    b.emit.lamp_box((xh + 0.2, yh + 0.03 * sg - 0.012, zc + dzh + 0.44), (xh + 0.34, yh + 0.03 * sg + 0.012, zc + dzh + 0.5), "green", LAMP)
    for k in range(4):                                                                              # the nozzle cluster
        a = k * math.pi / 2 + math.pi / 4
        b.fine.cyl((-l / 2 + 0.2, 0.22 * math.cos(a), zc + 0.22 * math.sin(a)), (-l / 2 - 0.1, 0.22 * math.cos(a), zc + 0.22 * math.sin(a)), 0.07, TRIM, seg=10, r2=0.11)
    b.body.box((-l / 2 + 0.7, -0.3, 0.0), (l / 2 - 0.7, 0.3, 0.30), STRUCT)                          # the cradle: a spine on the rails and two cross saddles with straps
    for x in (-0.8, 0.8):
        b.body.box((x - 0.1, -w / 2 + 0.1, 0.22), (x + 0.1, w / 2 - 0.1, 0.36), TRIM)
        b.soft.box((x - 0.04, -w / 2 + 0.2, 0.36), (x + 0.04, w / 2 - 0.2, 0.40), RUBBER)


def round_hatch(b: SParts, r: float = 0.55, wheel: bool = True) -> None:
    """A pressure hatch facing +x, centred on the origin at z = 0 (the caller lifts it): a heavy frame ring, a dished door, a hand wheel, two status lamps."""
    b.body.cyl((0.0, 0.0, 0.0), (0.12, 0.0, 0.0), r + 0.1, STEEL, seg=28)
    b.body.cyl((0.1, 0.0, 0.0), (0.16, 0.0, 0.0), r, COMPOSITE, seg=28)
    b.fine.cyl((0.16, 0.0, 0.0), (0.2, 0.0, 0.0), 0.08, TRIM, seg=12)
    if wheel:
        for k in range(3):
            a = k * math.pi / 3
            b.fine.cyl((0.2, -0.26 * math.cos(a), -0.26 * math.sin(a)), (0.2, 0.26 * math.cos(a), 0.26 * math.sin(a)), 0.014, TRIM, seg=6)
    b.emit.lamp_box((0.12, -r - 0.22, r * 0.5), (0.16, -r - 0.12, r * 0.5 + 0.1), "green", LAMP)
    b.emit.lamp_box((0.12, -r - 0.22, r * 0.5 - 0.15), (0.16, -r - 0.12, r * 0.5 - 0.05), "red", LAMP_DIM)


def launch_rail(b: SParts, l: float = 3.4) -> None:
    """A pair of launch rails on the floor, long along y, with cross ties and a yellow edge."""
    for sx in (-0.35, 0.35):
        b.fine.box((sx - 0.04, 0.0, 0.0), (sx + 0.04, l, 0.05), STEEL)
    for k in range(int(l / 0.6)):
        b.fine.box((-0.45, 0.2 + k * 0.6, 0.0), (0.45, 0.28 + k * 0.6, 0.025), TRIM)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- the plants
def scrubber_column(b: SParts, r: float = 0.55, h: float = 3.0) -> None:
    """A CO2 scrubber column: a tall cylinder with welded bands, a lit sight glass, ducts at the head and foot, a ladder."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.12), r + 0.1, STRUCT, seg=22)
    b.body.cyl((0, 0, 0.12), (0, 0, h - 0.2), r, STEEL, seg=22)
    b.body.sphere((0, 0, h - 0.2), r, STEEL, seg=22, rings=7, squash=(1, 1, 0.3))
    for z in (0.7, 1.4, 2.1):
        H3.ring(b.fine, 0.0, 0.0, z, r - 0.004, 0.02, 0.06, STRUCT, 22)
    b.fine.box((r - 0.02, -0.06, 0.9), (r + 0.03, 0.06, 1.7), DGLASS)
    b.emit.lamp_box((r + 0.03, -0.03, 0.95), (r + 0.036, 0.03, 1.65), "cyan_dim", LAMP_DIM)
    b.fine.cyl((0, 0, h - 0.3), (r + 0.7, 0, h - 0.3), 0.12, TRIM, seg=12)
    b.fine.cyl((0, 0, 0.4), (-r - 0.6, 0, 0.4), 0.12, TRIM, seg=12)
    b.fine.box((-0.04, -r - 0.03, 0.4), (0.04, -r + 0.04, h - 0.6), TRIM)


def electrolyser(b: SParts, w: float = 1.8, d: float = 0.8, h: float = 2.1) -> None:
    """An oxygen electrolyser stack facing +x: a cabinet with a window onto the cell stack, a lit gas panel, two pipes on top."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), COMPOSITE)
    b.fine.box((d / 2, -w / 2 + 0.15, 0.4), (d / 2 + 0.03, w / 2 - 0.15, 1.5), DGLASS)
    for k in range(9):
        b.fine.box((d / 2 + 0.031, -w / 2 + 0.22 + k * 0.15, 0.5), (d / 2 + 0.036, -w / 2 + 0.25 + k * 0.15, 1.4), CRATE_BLUE)
    b.emit.lamp_box((d / 2 + 0.031, -w / 2 + 0.2, 1.55), (d / 2 + 0.036, w / 2 - 0.2, 1.58), "cyan", LAMP_DIM)
    for sy in (-0.35, 0.35):
        b.fine.cyl((0, sy, h), (0, sy, h + 0.4), 0.07, TRIM, seg=10)
    b.emit.label((d / 2 + 0.032, 0.0, 1.8), 0.6, 0.15, (1, 0, 0), "eq_oxygen")


def reactor_vessel(b: SParts, r: float = 1.15, h: float = 3.0) -> None:
    """A small standby reactor: a thick vessel in a ring of shield plates, coolant pipes up and out, a control-rod drive on top and a lit status band."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.18), r + 0.5, STRUCT, seg=28)
    b.body.cyl((0, 0, 0.18), (0, 0, h - 0.5), r, CRATE_GREY, seg=28)
    b.body.sphere((0, 0, h - 0.5), r, CRATE_GREY, seg=28, rings=8, squash=(1, 1, 0.4))
    for k in range(0, 8, 2):                                                                                          # four shield slabs round the foot
        a = math.radians(45 * k)
        b.body.box((r * 0.9 * math.cos(a) - 0.1, r * 0.9 * math.sin(a) - 0.3, 0.2), (r * 1.4 * math.cos(a) + 0.1, r * 1.4 * math.sin(a) + 0.3, 1.8), IVORY)
    for z in (0.7, 1.6, 2.4):
        H3.ring(b.fine, 0.0, 0.0, z, r - 0.004, 0.03, 0.08, STEEL, 28)
    b.body.cyl((0, 0, h - 0.2), (0, 0, h + 0.5), 0.22, STEEL, seg=14)
    for k in range(3):
        a = math.radians(120 * k + 30)
        b.fine.cyl((r * 0.8 * math.cos(a), r * 0.8 * math.sin(a), h - 0.4), (r * 0.8 * math.cos(a), r * 0.8 * math.sin(a), h + 0.8), 0.08, TRIM, seg=10)
    H3.lamp_ring(b.emit, 0.0, 0.0, 1.2, r + 0.005, 0.12, 0.012, "amber", LAMP_DIM, 28)
    b.emit.label((r + 0.01, 0.0, 2.7), 0.6, 0.15, (1, 0, 0), "eq_standby")


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- air hall
def kiosk(b: SParts, w: float = 1.2, h: float = 1.5, tile: str = "scr_dir") -> None:
    """A free-standing information kiosk facing +x: a column with a wide screen, a base plate, a lit pictogram band."""
    b.body.box((-0.2, -w / 2, 0.0), (0.2, w / 2, 0.14), STRUCT)
    b.body.box((-0.1, -0.2, 0.14), (0.1, 0.2, h - 0.5), COMPOSITE)
    b.body.box((-0.18, -w / 2, h - 0.5), (0.12, w / 2, h), TRIM)
    b.fine.box((0.12, -w / 2 + 0.05, h - 0.45), (0.135, w / 2 - 0.05, h - 0.05), DGLASS)
    b.emit.label((0.1355, 0.0, h - 0.25), w - 0.12, (w - 0.12) * 0.5625, (1, 0, 0), tile)
    b.emit.lamp_box((0.12, -w / 2 + 0.05, h - 0.52), (0.14, w / 2 - 0.05, h - 0.5), "cyan", LAMP_DIM)


def cell_wall_rack(b: SParts, w: float = 2.4, d: float = 0.5, h: float = 2.0, seed: int = 1) -> None:
    """A set of shelves of stock (boxes, tins, folded cloth) facing +x, for a shop or a store."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.05), STRUCT)
    for sy in (-w / 2, w / 2 - 0.04):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.04, h), TRIM)
    levels = int(h / 0.5)
    for k in range(levels):
        z = 0.15 + k * (h - 0.2) / levels
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.03), STEEL)
        y = -w / 2 + 0.1
        while y < w / 2 - 0.25:
            cw = rng.uniform(0.18, 0.4)
            ch = rng.uniform(0.14, 0.34)
            mat = rng.choice([CRATE_OLIVE, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY, FABRIC_SAND, FABRIC_NAVY])
            b.soft.box((-d / 2 + 0.06, y, z + 0.03), (d / 2 - 0.04, y + cw, z + 0.03 + ch), mat)
            y += cw + 0.04


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- drones
def drone(b: SParts) -> None:
    """A small recon drone facing +x, origin on the floor under it (it rests on four skids at z 0.12): a flat fuselage with a sensor eye, four rotor arms with discs, orange tips."""
    b.body.box((-0.35, -0.2, 0.18), (0.4, 0.2, 0.34), IVORY)
    b.body.box((0.35, -0.12, 0.2), (0.5, 0.12, 0.3), COMPOSITE)
    b.emit.lamp_cyl((0.505, 0.0, 0.25), (0.515, 0.0, 0.25), 0.04, "cyan", LAMP_DIM, seg=10)
    for sx, sy in ((0.3, 0.45), (0.3, -0.45), (-0.3, 0.45), (-0.3, -0.45)):
        b.fine.box((min(0.0, sx) - 0.02, min(0.0, sy) - 0.02, 0.25), (max(0.0, sx) + 0.02, max(0.0, sy) + 0.02, 0.29), TRIM)
        b.fine.cyl((sx, sy, 0.27), (sx, sy, 0.3), 0.05, STEEL, seg=10)
        b.soft.cyl((sx, sy, 0.31), (sx, sy, 0.315), 0.2, CRATE_GREY, seg=18)
        b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.2), 0.012, TRIM, seg=6)
    b.soft.box((-0.38, -0.05, 0.3), (-0.3, 0.05, 0.36), CRATE_ORANGE)


def charging_bench(b: SParts, l: float = 6.0) -> None:
    """A long bench of charging cradles facing +x (the bench runs along y): a steel top, four cradles with a status lamp each and a drone on every other one, a cable duct, a rail of tools."""
    b.body.box((-0.45, -l / 2, 0.0), (0.45, l / 2, 0.78), COMPOSITE)
    b.body.box((-0.47, -l / 2 - 0.02, 0.78), (0.47, l / 2 + 0.02, 0.82), STEEL)
    n = int(l / 1.4)
    for k in range(n):
        y = -l / 2 + 0.7 + k * 1.4
        b.fine.box((-0.3, y - 0.45, 0.82), (0.3, y + 0.45, 0.86), TRIM)
        b.emit.lamp_box((0.3, y - 0.1, 0.83), (0.31, y + 0.1, 0.85), "green" if k % 2 == 0 else "amber", LAMP_DIM)
        if k % 2 == 0:
            with b.at(T(0.0, y, 0.7)):
                drone(b)
    b.body.box((-0.45, -l / 2, 1.5), (-0.4, l / 2, 2.1), COMPOSITE)
    b.emit.label((-0.395, 0.0, 1.95), 1.0, 0.25, (1, 0, 0), "eq_drone")
