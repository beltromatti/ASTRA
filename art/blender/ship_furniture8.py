"""ASN Aquila interior kit: furniture and equipment of the command deck (NAVE-2, Deck 2) and the officers' deck (Deck 3) — the conference table, the filing cabinets and the
moving shelves of the archive, a desk with its partition, the vertical launch cells of the VLS magazine, the turret trunk and the railgun breech of the barbette, the officers'
beds, the gym's machines. Eighth library, after ship_furniture.py .. ship_furniture7.py; same conventions: every function builds one piece in ITS OWN frame (origin on the floor,
+x the piece's front, +y its left, z up) into a `SParts` (body = bevelled hard-surface, fine = small details, soft = cloth, rubber and thin details, emit = lamps and labels);
rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math
import random


from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM,
                      PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, WOOD, SParts)


# ---------------------------------------------------------------------------------------------------------------------- offices and meetings
def conference_table(b: SParts, l: float = 6.4, w: float = 1.6, seats: int = 6) -> None:
    """A long conference table, its length along x: a dark wood top with a brushed edge, a lit inlay line down the middle, at every seat a tablet and a name plate, a carafe and
    glasses in the middle, a conference unit at each end; on a central plinth and two end legs."""
    b.body.box((-l / 2, -w / 2, 0.72), (l / 2, w / 2, 0.76), WOOD)
    b.soft.box((-l / 2 - 0.01, -w / 2 - 0.01, 0.70), (l / 2 + 0.01, w / 2 + 0.01, 0.72), TRIM)
    for sx in (-l / 2 + 0.5, l / 2 - 0.5):
        b.body.box((sx - 0.3, -w / 2 + 0.2, 0.0), (sx + 0.3, w / 2 - 0.2, 0.72), COMPOSITE)
    b.body.box((-l / 2 + 1.0, -0.2, 0.05), (l / 2 - 1.0, 0.2, 0.72), COMPOSITE)
    b.emit.lamp_box((-l / 2 + 0.3, -0.012, 0.761), (l / 2 - 0.3, 0.012, 0.765), "cool_dim", LAMP_DIM)
    for k in range(seats):
        x = -l / 2 + 0.8 + k * (l - 1.6) / max(1, seats - 1)
        for sy in (-1, 1):
            b.soft.box((x - 0.17, sy * 0.45 - 0.12, 0.76), (x + 0.17, sy * 0.45 + 0.12, 0.77), STRUCT)
            b.emit.label((x, sy * 0.45, 0.771), 0.3, 0.2, (0, 0, 1), "scr_data", up=(1, 0, 0))
            b.soft.box((x - 0.07, sy * 0.72 - 0.015, 0.76), (x + 0.07, sy * 0.72 + 0.015, 0.775), CRATE_GREY)
    for k in range(3):
        x = -0.9 + k * 0.9
        b.soft.cyl((x, 0.0, 0.76), (x, 0.0, 0.94), 0.045, DGLASS, seg=10)
        b.soft.cyl((x + 0.2, 0.1, 0.76), (x + 0.2, 0.1, 0.83), 0.03, DGLASS, seg=8)


def desk_pod(b: SParts, w: float = 1.4, d: float = 0.8) -> None:
    """A desk with its low partition, facing +x (the sitter's side is -x... facing the partition): a laminate top on two pedestals, a monitor and a keyboard, a tray, a lamp,
    a fabric partition behind with a pin board and a pair of photographs."""
    b.body.box((-d / 2, -w / 2, 0.72), (d / 2, w / 2, 0.76), LAMINATE)
    for sy in (-w / 2 + 0.1, w / 2 - 0.4):
        b.body.box((-d / 2 + 0.05, sy, 0.0), (d / 2 - 0.05, sy + 0.3, 0.72), COMPOSITE)
        for k in range(3):
            b.soft.box((d / 2 - 0.05, sy + 0.03, 0.08 + k * 0.2), (d / 2 - 0.04, sy + 0.27, 0.24 + k * 0.2), CRATE_GREY)
    b.body.box((d / 2 - 0.02, -w / 2 - 0.1, 0.0), (d / 2 + 0.02, w / 2 + 0.1, 1.45), STRUCT)
    b.soft.box((d / 2 + 0.02, -w / 2 - 0.08, 0.5), (d / 2 + 0.06, w / 2 + 0.08, 1.4), FABRIC_GREY)               # fabric on both faces of the partition
    b.soft.box((d / 2 - 0.06, -w / 2 - 0.08, 0.5), (d / 2 - 0.02, w / 2 + 0.08, 1.4), FABRIC_GREY)
    b.soft.box((d / 2 - 0.065, -0.4, 1.0), (d / 2 - 0.06, 0.3, 1.3), CRATE_OLIVE)                                  # the pin board and two photographs on the sitter's side
    b.soft.box((d / 2 - 0.065, 0.35, 1.0), (d / 2 - 0.06, 0.5, 1.15), BEDDING)
    b.soft.box((0.1, -0.2, 0.76), (0.22, 0.2, 0.78), STRUCT)
    b.soft.box((0.3, -0.25, 0.76), (0.32, 0.25, 1.18), DGLASS)
    b.emit.label((0.299, 0.0, 0.97), 0.48, 0.28, (-1, 0, 0), "scr_data")


def filing_cabinet(b: SParts, n: int = 3, w: float = 0.5, h: float = 1.35) -> None:
    """A row of n steel filing cabinets facing +x (each w wide, h high, four drawers with handles and label holders), a lock bar on the first."""
    d = 0.6
    for k in range(n):
        y0 = k * w
        b.body.box((-d / 2, y0 + 0.004, 0.0), (d / 2, y0 + w - 0.004, h), CRATE_GREY)
        for j in range(4):
            z = 0.06 + j * (h - 0.1) / 4
            b.soft.box((d / 2, y0 + 0.03, z), (d / 2 + 0.012, y0 + w - 0.03, z + (h - 0.1) / 4 - 0.025), STEEL)
            b.soft.box((d / 2 + 0.012, y0 + w * 0.3, z + (h - 0.1) / 8 - 0.012), (d / 2 + 0.03, y0 + w * 0.7, z + (h - 0.1) / 8 + 0.012), TRIM)
            b.soft.box((d / 2 + 0.012, y0 + w * 0.35, z + (h - 0.1) / 4 - 0.07), (d / 2 + 0.016, y0 + w * 0.65, z + (h - 0.1) / 4 - 0.045), IVORY)
    b.soft.box((d / 2 + 0.02, 0.02, 0.1), (d / 2 + 0.035, n * w - 0.02, 0.13), TRIM)


def compact_shelving(b: SParts, l: float = 3.0, d: float = 1.0, h: float = 2.2) -> None:
    """A moving archive shelf unit, its length l along y and its depth d along x: a steel carriage on rails in the floor, shelves of grey file boxes open on BOTH long faces (the
    aisles lie on the +x and -x sides), an end panel at each end with a handwheel on the +y one and an index card holder, a lit tag."""
    b.body.box((-d / 2, -l / 2, 0.0), (d / 2, l / 2, 0.08), STRUCT)
    for sy in (-l / 2, l / 2 - 0.05):
        b.body.box((-d / 2, sy, 0.08), (d / 2, sy + 0.05, h), COMPOSITE)
    b.body.box((-0.02, -l / 2, 0.08), (0.02, l / 2, h), STRUCT)
    rng = random.Random(7)
    n = int((l - 0.1) / 0.12)
    for lev in range(5):
        z = 0.1 + lev * (h - 0.2) / 5
        for sx in (-1, 1):
            lo, hi = sorted((sx * 0.02, sx * (d / 2 - 0.02)))
            b.body.box((lo, -l / 2 + 0.05, z), (hi, l / 2 - 0.05, z + 0.03), STEEL)
            for k in range(n):
                y = -l / 2 + 0.07 + k * (l - 0.14) / n
                x0, x1 = sorted((sx * 0.05, sx * (d / 2 - 0.08)))
                b.soft.box((x0, y, z + 0.03), (x1, y + (l - 0.14) / n - 0.012, z + (h - 0.2) / 5 - 0.05), rng.choice([CRATE_GREY, CRATE_GREY, STEEL, FABRIC_SAND, CRATE_OLIVE]))
    b.body.box((-0.15, l / 2, 0.8), (0.15, l / 2 + 0.06, 1.3), STRUCT)
    b.soft.cyl((0.0, l / 2 + 0.06, 1.05), (0.0, l / 2 + 0.1, 1.05), 0.14, TRIM, seg=12)
    for k in range(4):
        a = math.pi / 2 * k
        b.soft.box((0.12 * math.cos(a) - 0.012, l / 2 + 0.1, 1.05 + 0.12 * math.sin(a) - 0.012), (0.12 * math.cos(a) + 0.012, l / 2 + 0.13, 1.05 + 0.12 * math.sin(a) + 0.012), STEEL)
    b.emit.lamp_box((-d / 2 + 0.1, -l / 2 - 0.003, h - 0.12), (d / 2 - 0.1, -l / 2, h - 0.08), "white_dim", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------------- weapons
def vls_cell(b: SParts, h: float = 2.8, tag: int = 0) -> None:
    """A vertical launch cell standing on the floor, rising to the height h under the ceiling: a square steel tube with brushed corner posts, bands of red and yellow, a hinged
    cap with a gas vent stub on top, an access panel with a status lamp and a number tag on the +x face."""
    b.body.box((-0.46, -0.46, 0.0), (0.46, 0.46, 0.1), STRUCT)
    b.body.box((-0.42, -0.42, 0.1), (0.42, 0.42, h - 0.2), CRATE_GREY)
    for sx in (-0.45, 0.39):
        for sy in (-0.45, 0.39):
            b.soft.box((sx, sy, 0.1), (sx + 0.06, sy + 0.06, h - 0.2), TRIM)
    for z in (0.5, 1.9):
        b.soft.box((-0.435, -0.435, z), (0.435, 0.435, z + 0.12), PAINT_RED)
    b.soft.box((-0.435, -0.435, 1.15), (0.435, 0.435, 1.22), CRATE_ORANGE)
    b.body.box((-0.46, -0.46, h - 0.2), (0.46, 0.46, h - 0.12), STEEL)
    b.body.box((-0.4, -0.4, h - 0.12), (0.4, 0.4, h - 0.04), CRATE_GREY)
    b.body.cyl((0.0, 0.0, h - 0.04), (0.0, 0.0, h), 0.14, TRIM, seg=10)
    b.soft.box((0.42, -0.3, 0.3), (0.44, 0.3, 1.4), STRUCT)
    b.emit.lamp_box((0.44, -0.2, 1.2), (0.45, -0.1, 1.28), "green", LAMP)
    b.emit.lamp_box((0.44, 0.0, 1.2), (0.45, 0.1, 1.28), "amber", LAMP_DIM)
    b.emit.label((0.442, 0.0, 0.7), 0.4, 0.1, (1, 0, 0), "tag_%02d" % (tag % 12))


def turret_trunk(b: SParts, r: float = 3.0, h: float = 3.6) -> None:
    """The armoured trunk of a gun turret rising through the room (centred on the origin, floor to ceiling): a heavy ring bearing with a lit seam at mid height, riveted armour
    bands, a hatch with hazard marks on the +x side, four hydraulic rams standing round its foot with their pipes, and the drive motors on a skirt."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.35), r + 0.45, STRUCT, seg=32)
    b.body.cyl((0, 0, 0.35), (0, 0, h), r, CRATE_GREY, seg=32)
    for z in (0.9, 1.7, 2.9):
        b.soft.cyl((0, 0, z), (0, 0, z + 0.08), r + 0.04, TRIM, seg=32)
    b.emit.lamp_cyl((0, 0, 1.78), (0, 0, 1.8), r + 0.045, "security", LAMP_DIM, seg=32)
    for k in range(24):
        a = 2 * math.pi * k / 24
        b.soft.cyl((math.cos(a) * (r + 0.01), math.sin(a) * (r + 0.01), 0.9), (math.cos(a) * (r + 0.05), math.sin(a) * (r + 0.05), 0.9), 0.04, STEEL, seg=6)
        b.soft.cyl((math.cos(a) * (r + 0.01), math.sin(a) * (r + 0.01), 1.7), (math.cos(a) * (r + 0.05), math.sin(a) * (r + 0.05), 1.7), 0.04, STEEL, seg=6)
    b.body.box((r - 0.1, -0.55, 0.35), (r + 0.18, 0.55, 2.2), STRUCT)                                           # the hatch frame and its door
    b.body.box((r + 0.12, -0.45, 0.45), (r + 0.2, 0.45, 2.1), CRATE_ORANGE)
    b.emit.label((r + 0.202, 0.0, 1.9), 0.8, 0.12, (1, 0, 0), "hazard_h")
    b.soft.cyl((r + 0.2, 0.3, 1.2), (r + 0.3, 0.3, 1.2), 0.05, TRIM, seg=8)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        cx, cy = (r + 0.7) * math.cos(a), (r + 0.7) * math.sin(a)
        b.body.cyl((cx, cy, 0.0), (cx, cy, 1.2), 0.13, STEEL, seg=10)
        b.soft.cyl((cx, cy, 1.2), (cx * 0.88, cy * 0.88, 1.75), 0.06, TRIM, seg=8)
        b.soft.cyl((cx, cy, 0.3), (cx, cy, 0.9), 0.17, CRATE_ORANGE, seg=10)
    for k in range(3):                                                                                           # the drive motors: a skid, a finned barrel, a terminal box
        a = math.radians(160 + 25 * k)
        cx, cy = (r + 1.0) * math.cos(a), (r + 1.0) * math.sin(a)
        b.body.box((cx - 0.55, cy - 0.35, 0.0), (cx + 0.55, cy + 0.35, 0.14), STRUCT)
        b.body.cyl((cx - 0.45, cy, 0.5), (cx + 0.45, cy, 0.5), 0.32, CRATE_BLUE, seg=14)
        for j in range(6):
            b.soft.cyl((cx - 0.35 + j * 0.14, cy, 0.5), (cx - 0.33 + j * 0.14, cy, 0.5), 0.345, TRIM, seg=14)
        b.body.box((cx - 0.12, cy - 0.15, 0.78), (cx + 0.12, cy + 0.15, 0.95), STRUCT)
        b.soft.tube([(cx, cy, 0.95), (cx * 0.92, cy * 0.92, 1.3), (cx * 0.85, cy * 0.85, 1.6)], 0.04, RUBBER, seg=6)
        b.emit.lamp_box((cx + 0.46, cy - 0.04, 0.5), (cx + 0.47, cy + 0.04, 0.56), "green", LAMP_DIM)


def railgun_breech(b: SParts) -> None:
    """The breech end of a railgun, facing +x into the room's wall (its barrel runs on through the wall): two thick copper-orange rails on insulated spacers, a cradle with the
    shell loading tray, six capacitor cylinders along each side with lit rings, thick feed cables to a power cabinet, a recoil buffer and a hazard-marked muzzle-side bulkhead."""
    zc = 1.45
    for sy in (-0.42, 0.42):
        b.body.box((-1.2, sy - 0.14, zc - 0.26), (3.4, sy + 0.14, zc + 0.26), CRATE_ORANGE)
        b.soft.box((-1.2, sy - 0.16, zc - 0.05), (3.4, sy + 0.16, zc + 0.05), STEEL)
    for k in range(7):
        x = -1.0 + k * 0.5
        b.body.box((x - 0.07, -0.36, zc - 0.28), (x + 0.07, 0.36, zc + 0.28), COMPOSITE)
    b.body.box((-1.5, -0.7, zc - 0.5), (-1.2, 0.7, zc + 0.5), STRUCT)
    b.body.box((-1.7, -0.5, zc - 0.3), (-1.5, 0.5, zc + 0.3), CRATE_GREY)
    for sy in (-0.35, 0.35):
        b.soft.cyl((-1.7, sy, zc), (-2.3, sy, zc), 0.1, STEEL, seg=10)
    b.body.box((-0.5, -0.3, 0.0), (1.0, 0.3, zc - 0.55), STRUCT)                                              # the loading tray and its stand
    b.soft.box((-0.4, -0.2, zc - 0.55), (0.9, 0.2, zc - 0.5), STEEL)
    b.body.cyl((-0.2, 0.0, zc - 0.5), (0.7, 0.0, zc - 0.5), 0.12, CRATE_OLIVE, seg=10)
    for side in (-1, 1):
        for k in range(6):
            x = -0.8 + k * 0.62
            y = side * 1.15
            b.body.cyl((x, y, 0.0), (x, y, 2.3), 0.22, CRATE_GREY, seg=12)
            for z in (0.6, 1.2, 1.8):
                b.soft.cyl((x, y, z), (x, y, z + 0.05), 0.235, STRUCT, seg=12)
                b.emit.lamp_cyl((x, y, z + 0.05), (x, y, z + 0.075), 0.235, "security_dim", LAMP_DIM, seg=12)
            b.soft.tube([(x, y, 2.3), (x, y * 0.5, 2.6), (x + 0.1, side * 0.45, zc + 0.3)], 0.035, CRATE_ORANGE, seg=6)
    b.body.cyl((3.4, 0.0, zc), (3.9, 0.0, zc), 0.62, STEEL, seg=18)                                           # the sleeve the barrel runs through the wall in, with a flange and its lit rim
    b.body.cyl((3.4, 0.0, zc), (3.46, 0.0, zc), 0.85, STRUCT, seg=18)
    b.emit.lamp_cyl((3.46, 0.0, zc), (3.47, 0.0, zc), 0.8, "security_dim", LAMP_DIM, seg=18)
    b.emit.label((3.2, 0.0, 0.5), 1.6, 0.2, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    b.body.box((-0.6, 1.8, 0.0), (0.6, 2.5, 2.1), CRATE_BLUE)
    b.emit.label((-0.6, 2.15, 1.8), 0.7, 0.18, (-1, 0, 0), "icon_hv")


# ---------------------------------------------------------------------------------------------------------------------- the officers' deck
def officer_bed(b: SParts, w: float = 1.0, l: float = 2.1, blanket: str = FABRIC_NAVY) -> None:
    """A single bed with a headboard at -x (its foot towards +x): a frame, a mattress with sheets, a folded blanket, two pillows, a reading lamp on the wall behind, a drawer
    under the foot."""
    b.body.box((-l / 2, -w / 2, 0.12), (l / 2, w / 2, 0.36), WOOD)
    b.soft.box((-l / 2 + 0.04, -w / 2 + 0.04, 0.36), (l / 2 - 0.04, w / 2 - 0.04, 0.5), BEDDING)
    b.soft.box((-l / 2 + 0.7, -w / 2 + 0.03, 0.5), (l / 2 - 0.03, w / 2 - 0.03, 0.56), blanket)
    b.soft.box((-l / 2 + 0.05, -w / 2 + 0.1, 0.5), (-l / 2 + 0.45, -0.03, 0.6), BEDDING)
    b.soft.box((-l / 2 + 0.05, 0.03, 0.5), (-l / 2 + 0.45, w / 2 - 0.1, 0.6), BEDDING)
    b.body.box((-l / 2 - 0.06, -w / 2 - 0.03, 0.0), (-l / 2, w / 2 + 0.03, 1.0), WOOD)
    b.body.box((l / 2, -w / 2, 0.12), (l / 2 + 0.04, w / 2, 0.55), WOOD)
    for sy in (-w / 2 + 0.05, w / 2 - 0.1):
        b.body.box((-l / 2, sy, 0.0), (-l / 2 + 0.06, sy + 0.05, 0.12), TRIM)
        b.body.box((l / 2 - 0.06, sy, 0.0), (l / 2, sy + 0.05, 0.12), TRIM)
    b.emit.lamp_box((-l / 2 - 0.07, w / 2 - 0.3, 0.9), (-l / 2 - 0.064, w / 2 - 0.15, 0.95), "white_warm", LAMP)


def treadmill(b: SParts) -> None:
    """A treadmill facing +x: a belt on a steel frame, side rails, an upright with a console screen and a handlebar, a lit speed strip."""
    b.body.box((-0.9, -0.38, 0.1), (0.7, 0.38, 0.22), CRATE_GREY)
    b.soft.box((-0.85, -0.3, 0.22), (0.62, 0.3, 0.235), RUBBER)
    for sy in (-0.38, 0.32):
        b.body.box((-0.9, sy, 0.1), (0.7, sy + 0.06, 0.32), STRUCT)
    b.body.box((0.62, -0.34, 0.0), (0.76, 0.34, 0.12), STRUCT)
    for sy in (-0.36, 0.36):
        b.body.box((0.6, sy - 0.03, 0.2), (0.7, sy + 0.03, 1.2), TRIM)
    b.body.box((0.58, -0.3, 1.05), (0.72, 0.3, 1.45), STRUCT)
    b.soft.box((0.5, -0.25, 1.1), (0.58, 0.25, 1.4), DGLASS)
    b.emit.label((0.499, 0.0, 1.25), 0.5, 0.26, (-1, 0, 0), "scr_data")
    b.soft.cyl((0.6, -0.36, 1.2), (0.6, 0.36, 1.2), 0.025, RUBBER, seg=8)
    b.emit.lamp_box((-0.8, -0.395, 0.18), (0.6, -0.385, 0.2), "cyan_dim", LAMP_DIM)


def weight_bench(b: SParts) -> None:
    """A weight bench with a bar rack, facing +x: a padded flat bench, two uprights holding a barbell with rubber plates, a plate tree and a mirror-side rail."""
    b.body.box((-0.4, -0.15, 0.0), (0.9, 0.15, 0.4), STRUCT)
    b.soft.box((-0.4, -0.18, 0.4), (0.9, 0.18, 0.47), FABRIC_GREY)
    for sx in (0.0, 0.7):
        for sy in (-0.45, 0.45):
            b.body.box((sx - 0.03, sy - 0.03, 0.0), (sx + 0.03, sy + 0.03, 1.15), TRIM)
    b.body.cyl((0.35, -0.7, 1.1), (0.35, 0.7, 1.1), 0.016, STEEL, seg=8)
    for sy in (-0.55, 0.55):
        b.soft.cyl((0.35, sy - 0.04, 1.1), (0.35, sy + 0.04, 1.1), 0.2, RUBBER, seg=14)
    b.body.cyl((1.2, 0.0, 0.0), (1.2, 0.0, 1.3), 0.025, TRIM, seg=8)
    for k in range(4):
        b.soft.cyl((1.2, -0.08, 0.3 + k * 0.28), (1.2, 0.08, 0.3 + k * 0.28), 0.14 - k * 0.012, RUBBER, seg=10)
