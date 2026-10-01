"""ASN Aquila interior kit: furniture and machines of the fabrication and repair decks (NAVE-2, Decks 11-12) — the metal printers, the robot arm and its conveyor, the casting
furnace, the spool and plate racks, the measuring table, the hull mock-up the damage control teams train on, the EVA suit rack, the cable drums. Seventh library, after
ship_furniture.py .. ship_furniture6.py; same conventions: every function builds one piece in ITS OWN frame (origin on the floor, +x the piece's front, +y its left, z up) into a
`SParts` (body = bevelled hard-surface, fine = small details, soft = cloth, rubber and thin details, emit = lamps and labels); rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math
import random


from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, IVORY, LAMP, LAMP_DIM, LAMP_HOT, RUBBER, STEEL, STRUCT, TRIM, SParts)


# ---------------------------------------------------------------------------------------------------------------------- fabrication
def printer_3d(b: SParts, w: float = 2.4, d: float = 1.8, h: float = 2.3) -> None:
    """A large metal printer facing +x: a cabinet, a body with a big dark window onto the build chamber (a hot glow, a print head on its gantry, the half-printed part on the
    plate), a hazard strip, a control tablet, a spool of feedstock on top and a status beacon."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.8), COMPOSITE)
    b.body.box((-d / 2, -w / 2, 0.8), (d / 2, w / 2, h), CRATE_GREY)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, 0.0), (d / 2 + 0.02, w / 2 + 0.02, 0.08), STRUCT)
    b.soft.box((d / 2, -w / 2 + 0.2, 0.95), (d / 2 + 0.02, w / 2 - 0.2, 1.95), TRIM)                                       # the window frame
    b.soft.box((d / 2 + 0.02, -w / 2 + 0.26, 1.0), (d / 2 + 0.03, w / 2 - 0.26, 1.9), DGLASS)
    b.soft.box((-0.2, -w / 2 + 0.3, 1.0), (0.5, w / 2 - 0.3, 1.04), STEEL)                                                   # the plate inside
    b.soft.box((-0.1, -0.35, 1.04), (0.2, 0.35, 1.5), CRATE_GREY)                                                            # the part, half printed
    b.soft.box((-0.1, -0.35, 1.5), (0.2, 0.35, 1.56), CRATE_ORANGE)
    b.soft.box((-0.2, -w / 2 + 0.3, 1.78), (0.5, w / 2 - 0.3, 1.82), TRIM)                                                  # the gantry bar and the head
    b.soft.box((0.05, -0.12, 1.62), (0.25, 0.12, 1.78), STRUCT)
    b.emit.lamp_box((0.04, -0.06, 1.6), (0.06, 0.06, 1.7), "white_cool", LAMP)
    b.emit.lamp_box((-0.2, -w / 2 + 0.3, 1.5), (-0.19, w / 2 - 0.3, 1.9), "engineering", LAMP_DIM)                         # the glow on the back wall of the chamber
    b.soft.box((d / 2 + 0.002, -0.35, 0.3), (d / 2 + 0.03, 0.35, 0.8), STRUCT)                                              # the control tablet on the cabinet
    b.emit.label((d / 2 + 0.032, 0.0, 0.62), 0.6, 0.28, (1, 0, 0), "scr_data")
    b.emit.label((d / 2 + 0.003, 0.0, 0.14), w - 0.4, 0.08, (1, 0, 0), "hazard_h")
    b.body.cyl((-0.1, -0.5, h), (-0.1, 0.5, h), 0.3, CRATE_ORANGE, seg=14)                                                  # the spool
    b.soft.cyl((-0.1, -0.52, h), (-0.1, -0.5, h), 0.34, TRIM, seg=14)
    b.soft.cyl((-0.1, 0.5, h), (-0.1, 0.52, h), 0.34, TRIM, seg=14)
    b.soft.tube([(-0.1, 0.3, h + 0.3), (0.2, 0.1, h + 0.1), (0.35, 0.0, h - 0.02)], 0.012, STEEL, seg=5)
    b.emit.lamp_cyl((d / 2 - 0.2, w / 2 - 0.2, h), (d / 2 - 0.2, w / 2 - 0.2, h + 0.1), 0.05, "green", LAMP, seg=10)


def _link(b: SParts, p0, p1, r: float, mat: str) -> None:
    b.body.cyl(p0, p1, r, mat, seg=10)
    b.body.sphere(p1, r * 1.25, TRIM, seg=10, rings=6)


def robot_arm(b: SParts) -> None:
    """A six-axis industrial robot arm on a base plate, reaching towards +x: a turntable, two long links with joints, a wrist and a two-finger gripper holding a part, hoses
    along the links, a lit status ring on the base."""
    b.body.box((-0.5, -0.5, 0.0), (0.5, 0.5, 0.1), STRUCT)
    b.body.cyl((0, 0, 0.1), (0, 0, 0.55), 0.3, CRATE_ORANGE, seg=14)
    b.emit.lamp_cyl((0, 0, 0.5), (0, 0, 0.53), 0.31, "engineering", LAMP_DIM, seg=14)
    b.body.sphere((0, 0, 0.7), 0.26, TRIM, seg=12, rings=7)
    _link(b, (0, 0, 0.7), (-0.15, 0.0, 1.7), 0.15, CRATE_ORANGE)
    _link(b, (-0.15, 0.0, 1.7), (0.95, 0.0, 2.0), 0.12, CRATE_ORANGE)
    _link(b, (0.95, 0.0, 2.0), (1.3, 0.0, 1.55), 0.08, CRATE_GREY)
    b.body.cyl((1.3, 0.0, 1.55), (1.3, 0.0, 1.35), 0.07, STEEL, seg=10)
    for sy in (-0.1, 0.1):
        b.body.box((1.27, sy - 0.015, 1.12), (1.33, sy + 0.015, 1.35), TRIM)
    b.soft.box((1.2, -0.12, 1.02), (1.4, 0.12, 1.12), CRATE_GREY)
    b.soft.tube([(0.05, 0.12, 0.9), (-0.05, 0.2, 1.4), (0.2, 0.2, 2.0), (0.9, 0.12, 2.1), (1.2, 0.1, 1.7)], 0.02, RUBBER, seg=6)


def furnace(b: SParts) -> None:
    """A crucible furnace on a frame facing +x: a grey drum with a heat-glowing mouth on top, a tilting handle and a pouring spout, a thermocouple, the control panel and a bank of
    lamps; the mould rack beside it is a separate piece."""
    b.body.box((-0.7, -0.7, 0.0), (0.7, 0.7, 0.14), STRUCT)
    for sx in (-0.6, 0.6):
        for sy in (-0.6, 0.6):
            b.body.box((sx - 0.04, sy - 0.04, 0.14), (sx + 0.04, sy + 0.04, 0.8), TRIM)
    b.body.cyl((0, 0, 0.5), (0, 0, 1.35), 0.55, CRATE_GREY, seg=18)
    for z in (0.7, 1.05):
        b.soft.cyl((0, 0, z), (0, 0, z + 0.04), 0.57, TRIM, seg=18)
    b.body.cyl((0, 0, 1.35), (0, 0, 1.4), 0.57, STEEL, seg=18)
    b.emit.lamp_cyl((0, 0, 1.4), (0, 0, 1.41), 0.34, "engineering", LAMP, seg=16)
    b.emit.lamp_cyl((0, 0, 1.41), (0, 0, 1.42), 0.18, "white_warm", LAMP_HOT, seg=12)
    b.body.box((0.45, -0.12, 1.2), (0.85, 0.12, 1.4), STEEL)                                                              # the spout
    b.soft.cyl((-0.5, -0.1, 1.2), (-1.0, -0.1, 1.6), 0.025, TRIM, seg=6)
    b.soft.cyl((-1.0, -0.1, 1.6), (-1.0, 0.2, 1.6), 0.04, RUBBER, seg=6)
    b.body.box((0.5, -0.4, 0.4), (0.62, 0.4, 1.0), STRUCT)
    b.emit.label((0.622, 0.0, 0.8), 0.6, 0.15, (1, 0, 0), "tag_06")
    for k in range(3):
        b.emit.lamp_box((0.622, -0.3 + k * 0.2, 0.55), (0.63, -0.22 + k * 0.2, 0.6), ("green", "amber", "red")[k], LAMP_DIM)


def mould_rack(b: SParts, w: float = 1.6) -> None:
    """A rack of sand and steel moulds for the furnace, facing +x: three shelves of boxy moulds in dark steel and a few cast parts waiting, a quench tank on the floor."""
    b.body.box((-0.3, -w / 2, 0.0), (-0.25, w / 2, 1.5), STRUCT)
    for sy in (-w / 2, w / 2 - 0.05):
        b.body.box((-0.3, sy, 0.0), (0.2, sy + 0.05, 1.5), TRIM)
    for z in (0.3, 0.8, 1.3):
        b.body.box((-0.3, -w / 2, z), (0.2, w / 2, z + 0.04), STEEL)
        for k in range(3):
            y = -w / 2 + 0.3 + k * 0.5
            b.soft.box((-0.2, y - 0.18, z + 0.04), (0.12, y + 0.18, z + 0.28), [STRUCT, CRATE_GREY, STRUCT][k])
            b.soft.box((0.02, y - 0.06, z + 0.28), (0.08, y + 0.06, z + 0.32), CRATE_ORANGE)
    b.body.box((0.4, -0.5, 0.0), (1.2, 0.5, 0.5), COMPOSITE)
    b.soft.box((0.45, -0.45, 0.5), (1.15, 0.45, 0.52), DGLASS)
    b.emit.lamp_box((0.45, -0.45, 0.52), (1.15, 0.45, 0.525), "cyan_dim", LAMP_DIM)


def conveyor(b: SParts, l: float = 4.0) -> None:
    """A belt conveyor along x (the belt 0.6 m wide at 0.85 m): steel side rails on legs, rollers at the ends, a dark belt with small parts riding on it, a motor and two sensor posts."""
    for sy in (-0.34, 0.34):
        b.body.box((-l / 2, sy - 0.03, 0.78), (l / 2, sy + 0.03, 0.92), STEEL)
    for k in range(int(l / 1.0) + 1):
        x = -l / 2 + k * l / int(l / 1.0)
        for sy in (-0.3, 0.3):
            b.body.box((x - 0.03, sy - 0.03, 0.0), (x + 0.03, sy + 0.03, 0.78), TRIM)
    b.soft.box((-l / 2, -0.3, 0.86), (l / 2, 0.3, 0.88), RUBBER)
    for x in (-l / 2 + 0.05, l / 2 - 0.05):
        b.body.cyl((x, -0.32, 0.86), (x, 0.32, 0.86), 0.06, STRUCT, seg=10)
    rng = random.Random(4)
    for k in range(5):
        x = -l / 2 + 0.5 + k * (l - 1.0) / 4
        b.soft.box((x - 0.12, rng.uniform(-0.12, 0.05) - 0.1, 0.88), (x + 0.12, rng.uniform(-0.12, 0.05) + 0.1, 0.88 + rng.uniform(0.06, 0.14)), [CRATE_GREY, CRATE_ORANGE, STEEL][k % 3])
    b.body.box((l / 2 - 0.4, 0.4, 0.3), (l / 2, 0.8, 0.7), CRATE_BLUE)
    for x in (-l * 0.15, l * 0.2):
        b.body.box((x - 0.03, 0.34, 0.92), (x + 0.03, 0.4, 1.4), STRUCT)
        b.body.box((x - 0.03, -0.34, 1.34), (x + 0.03, 0.4, 1.4), STRUCT)
        b.emit.lamp_box((x - 0.01, -0.01, 1.3), (x + 0.01, 0.01, 1.34), "red", LAMP)


def spool_rack(b: SParts, w: float = 2.4, h: float = 2.0) -> None:
    """A wall rack of feedstock spools facing +x: three levels of lying spools (wire and filament on steel reels, different colours), a lit tag under each level."""
    d = 0.5
    b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.03, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.05):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.05, h), TRIM)
    rng = random.Random(5)
    n = int(w / 0.42)
    for lev in range(3):
        z = 0.1 + lev * 0.65
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.04), STEEL)
        for k in range(n):
            y = -w / 2 + 0.25 + k * (w - 0.5) / max(1, n - 1)
            c = rng.choice([CRATE_ORANGE, CRATE_GREY, CRATE_BLUE, CRATE_OLIVE])
            b.soft.cyl((0.0, y - 0.1, z + 0.04 + 0.22), (0.0, y + 0.1, z + 0.04 + 0.22), 0.2, c, seg=12)
            b.soft.cyl((0.0, y - 0.12, z + 0.04 + 0.22), (0.0, y - 0.1, z + 0.04 + 0.22), 0.24, STEEL, seg=12)
            b.soft.cyl((0.0, y + 0.1, z + 0.04 + 0.22), (0.0, y + 0.12, z + 0.04 + 0.22), 0.24, STEEL, seg=12)
        b.emit.lamp_box((d / 2 - 0.005, -w / 2 + 0.1, z - 0.01), (d / 2, w / 2 - 0.1, z + 0.01), "engineering_dim", LAMP_DIM)


def cmm_table(b: SParts) -> None:
    """A coordinate measuring machine facing +x: a granite plate on a stand, a bridge with a probe arm, the part under test, a monitor and a keyboard on a side table."""
    b.body.box((-0.6, -0.5, 0.0), (0.6, 0.5, 0.82), COMPOSITE)
    b.body.box((-0.7, -0.6, 0.82), (0.7, 0.6, 0.92), STRUCT)
    for sy in (-0.55, 0.55):
        b.body.box((-0.1, sy - 0.04, 0.92), (0.1, sy + 0.04, 1.6), STEEL)
    b.body.box((-0.1, -0.6, 1.5), (0.1, 0.6, 1.62), STEEL)
    b.body.box((-0.05, -0.08, 1.2), (0.05, 0.08, 1.5), CRATE_GREY)
    b.soft.cyl((0.0, 0.0, 1.0), (0.0, 0.0, 1.2), 0.01, TRIM, seg=6)
    b.soft.sphere((0.0, 0.0, 1.0), 0.02, CRATE_ORANGE, seg=8, rings=5)
    b.soft.box((-0.3, -0.25, 0.92), (0.3, 0.25, 1.0), CRATE_GREY)
    b.soft.cyl((0.0, 0.0, 1.0), (0.0, 0.0, 1.08), 0.1, STEEL, seg=10)
    b.body.box((-0.3, 0.9, 0.0), (0.3, 1.5, 0.75), STEEL)
    b.soft.box((0.0, 1.0, 0.75), (0.04, 1.4, 1.05), DGLASS)
    b.emit.label((0.041, 1.2, 0.9), 0.4, 0.2, (1, 0, 0), "scr_data")
    b.soft.box((0.05, 1.0, 0.75), (0.25, 1.4, 0.78), STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- repair
def hull_mockup(b: SParts, w: float = 3.4, h: float = 2.4) -> None:
    """The damage control teams' training piece, facing +x: a section of hull plate standing on two stands with a ragged breach cut in it (four jagged edges round a dark
    opening) and an orange patch plate bolted half over it, weld seams, a shoring prop and a hazard strip."""
    b.body.box((-0.05, -w / 2, 0.3), (0.05, w / 2, h), CRATE_GREY)
    for sy in (-w / 2 + 0.3, w / 2 - 0.3):
        b.body.box((-0.4, sy - 0.06, 0.0), (0.4, sy + 0.06, 0.3), STRUCT)
        b.body.box((-0.07, sy - 0.1, 0.3), (0.07, sy + 0.1, 0.9), TRIM)
    b.soft.box((0.04, -0.5, 0.95), (0.06, 0.4, 1.9), STRUCT)                                                               # the breach: a dark hole with torn lips
    for k in range(7):
        a = 2 * math.pi * k / 7
        y, z = 0.45 * 0.6 * math.cos(a) - 0.05, 1.42 + 0.5 * math.sin(a)
        b.soft.box((0.04, y - 0.07, z - 0.05), (0.1 + 0.03 * (k % 3), y + 0.07, z + 0.05), STEEL)
    b.soft.box((0.06, -0.9, 0.7), (0.1, 0.1, 1.45), CRATE_ORANGE)                                                          # the patch, half in place
    for sy in (-0.85, -0.45, -0.05):
        for z in (0.75, 1.4):
            b.soft.cyl((0.1, sy, z), (0.115, sy, z), 0.025, TRIM, seg=8)
    for z in (0.7, 1.7):
        b.soft.box((0.05, -w / 2, z - 0.015), (0.062, w / 2, z + 0.015), STRUCT)
    b.soft.cyl((0.6, 0.9, 0.0), (0.12, 0.7, 1.6), 0.04, CRATE_ORANGE, seg=8)
    b.emit.label((0.052, 1.2, 0.5), 1.0, 0.12, (1, 0, 0), "hazard_h")


def plate_rack(b: SParts, w: float = 2.4, h: float = 2.2, n: int = 6) -> None:
    """A rack of hull plates standing on edge, facing +x: a steel frame with dividers and n armour plates in different greys, each with a stencilled number."""
    d = 0.8
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.1), STRUCT)
    for sy in (-w / 2, w / 2 - 0.05):
        b.body.box((-d / 2, sy, 0.1), (-d / 2 + 0.05, sy + 0.05, h), TRIM)
        b.body.box((d / 2 - 0.05, sy, 0.1), (d / 2, sy + 0.05, h * 0.7), TRIM)
    b.body.box((-d / 2, -w / 2, h - 0.05), (-d / 2 + 0.05, w / 2, h), TRIM)
    for k in range(n):
        y = -w / 2 + 0.2 + k * (w - 0.4) / max(1, n - 1)
        b.body.box((-d / 2 + 0.12, y - 0.04, 0.12), (d / 2 - 0.12, y + 0.04, h - 0.2), [CRATE_GREY, STEEL, CRATE_GREY, CRATE_OLIVE][k % 4])
        b.soft.box((d / 2 - 0.125, y - 0.04, h - 0.5), (d / 2 - 0.12, y + 0.04, h - 0.25), CRATE_ORANGE)


def eva_rack(b: SParts, n: int = 4) -> None:
    """A wall rack of EVA suits, facing +x: n white suits with orange stripes and bright helmets hanging from hooks, a pair of boots under each, a pressure tag, a steel back
    panel."""
    pitch = 0.9
    w = n * pitch
    b.body.box((-0.1, -w / 2, 0.0), (-0.04, w / 2, 2.2), COMPOSITE)
    b.body.box((-0.1, -w / 2, 2.2), (0.3, w / 2, 2.25), TRIM)
    for k in range(n):
        y = -w / 2 + pitch / 2 + k * pitch
        b.soft.box((-0.02, y - 0.22, 1.1), (0.2, y + 0.22, 1.85), IVORY)                                                   # the torso and the life-support pack behind it
        b.soft.box((-0.04, y - 0.18, 1.2), (-0.0, y + 0.18, 1.8), CRATE_GREY)
        b.soft.box((0.0, y - 0.22, 1.5), (0.205, y + 0.22, 1.56), CRATE_ORANGE)
        for sy in (-0.3, 0.3):
            b.soft.cyl((0.08, y + sy, 1.8), (0.1, y + sy, 1.15), 0.07, IVORY, seg=8)                                       # the arms
        for sy in (-0.1, 0.1):
            b.soft.cyl((0.08, y + sy, 1.1), (0.1, y + sy, 0.3), 0.09, IVORY, seg=8)                                        # the legs
            b.soft.box((0.0, y + sy - 0.07, 0.1), (0.24, y + sy + 0.07, 0.3), CRATE_GREY)                                  # the boots
        b.soft.sphere((0.09, y, 2.0), 0.19, IVORY, seg=12, rings=8)
        b.soft.box((0.2, y - 0.14, 1.94), (0.26, y + 0.14, 2.1), DGLASS)
        b.emit.lamp_box((0.205, y - 0.04, 1.62), (0.215, y + 0.04, 1.66), "green", LAMP_DIM)
    b.emit.label_fit((-0.039, 0.0, 2.35), min(1.6, w - 0.2), "eq_clean", (1, 0, 0))


def cable_drum(b: SParts, r: float = 0.6, w: float = 0.7, mat: str = CRATE_ORANGE) -> None:
    """A big cable drum standing on its flange, axis along y: two wooden-brown flanges, a core wound with cable (mat) and a loose end running to the floor."""
    b.body.cyl((0, -w / 2, r), (0, -w / 2 + 0.05, r), r, STRUCT, seg=18)
    b.body.cyl((0, w / 2 - 0.05, r), (0, w / 2, r), r, STRUCT, seg=18)
    b.soft.cyl((0, -w / 2 + 0.05, r), (0, w / 2 - 0.05, r), r * 0.78, mat, seg=18)
    b.soft.cyl((0, -w / 2 + 0.05, r), (0, w / 2 - 0.05, r), r * 0.3, STEEL, seg=10)
    b.soft.tube([(r * 0.78, w / 2 - 0.15, r), (r * 0.9, w / 2 - 0.1, r * 0.4), (r * 1.4, w / 2 - 0.2, 0.04), (r * 1.9, w / 2 - 0.4, 0.03)], 0.025, mat, seg=6)


def plate_stack(b: SParts, w: float = 1.1, d: float = 0.7, n: int = 5) -> None:
    """A stack of hull plates lying on a pallet (the pallet is the caller's), n layers in alternating greys with two strapping bands; origin on the pallet's top (z = 0)."""
    for k in range(n):
        b.body.box((-d / 2, -w / 2, k * 0.07), (d / 2, w / 2, k * 0.07 + 0.06), [CRATE_GREY, STEEL, CRATE_GREY, CRATE_OLIVE][k % 4])
    for sx in (-d * 0.28, d * 0.28):
        b.soft.box((sx - 0.015, -w / 2 - 0.004, 0.0), (sx + 0.015, w / 2 + 0.004, n * 0.07), CRATE_ORANGE)
    b.emit.label((d / 2 + 0.002, 0.0, n * 0.035), 0.4, 0.05, (1, 0, 0), "hazard_h")


def jib_crane(b: SParts, reach: float = 2.6, h: float = 3.0) -> None:
    """A floor-standing jib crane: a column on a base plate, a horizontal jib reaching towards +x with a brace, a hoist on its trolley and a hook with a sling; the column
    reaches the ceiling height `h` (a collar and a lamp)."""
    b.body.box((-0.4, -0.4, 0.0), (0.4, 0.4, 0.08), STRUCT)
    b.body.cyl((0, 0, 0.08), (0, 0, h - 0.4), 0.14, CRATE_ORANGE, seg=12)
    b.body.box((-0.1, -0.1, h - 0.4), (reach, 0.1, h - 0.28), CRATE_ORANGE)
    b.soft.cyl((0.1, 0, h - 0.8), (reach - 0.3, 0, h - 0.34), 0.03, TRIM, seg=6)
    b.body.box((reach * 0.7 - 0.25, -0.15, h - 0.72), (reach * 0.7 + 0.25, 0.15, h - 0.4), CRATE_GREY)
    b.soft.cyl((reach * 0.7, 0, h - 0.72), (reach * 0.7, 0, h - 1.5), 0.012, TRIM, seg=5)
    b.soft.box((reach * 0.7 - 0.07, -0.05, h - 1.62), (reach * 0.7 + 0.07, 0.05, h - 1.5), CRATE_ORANGE)
    b.emit.lamp_box((reach * 0.7 - 0.04, 0.15, h - 0.6), (reach * 0.7 + 0.04, 0.152, h - 0.56), "amber", LAMP)
