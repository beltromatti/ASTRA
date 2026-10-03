"""ASN Aquila interior kit (ARTE-INTERNI): medical furniture and equipment, fourth generation — the things of a ward and a theatre: bedside cabinets, visitors' chairs, drip stands, a crash
cart with its defibrillator, a diagnostic scanner, a patient trolley, a wheelchair, a medical sink, a sharps bin, a hand-sanitiser, an operating table, a surgical lamp, an anaesthesia machine,
an instrument trolley, a supply cabinet. Same conventions as ship_furn2/3 (one piece per function, origin on the floor, x = the front, y = the left, z up). The ward of the Medbay
(ship_medbay.py) and the other medical rooms (ship_rooms_med.py, ship_rooms_care.py) use them.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Ry, T
from ship_lib import (BEDDING, BRASS, COMPOSITE, FABRIC_GREY, FABRIC_NAVY, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, PLASTER_TEAL, RUBBER, STEEL, STRUCT, SWATCH, TRIM,
                      WHITE_GLOSS, SParts)

TEAL = PLASTER_TEAL


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the ward
def bedside_cabinet(b: SParts, seed: int = 1) -> None:
    """A bedside cabinet 0.5 x 0.45 x 0.78 on four castors, facing +x: a white carcase, a drawer and a cupboard behind a teal door with steel pulls, on top a cup, a jug, a tissue box and a
    tablet on its charger."""
    for sx in (-0.17, 0.17):
        for sy in (-0.2, 0.2):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.07), 0.025, RUBBER, seg=8)
    MK.rbox(b.soft, (-0.225, -0.25, 0.07), (0.225, 0.25, 0.76), 0.012, WHITE_GLOSS, 1)
    b.body.box((-0.235, -0.26, 0.76), (0.235, 0.26, 0.785), STEEL)
    b.fine.box((0.225, -0.22, 0.52), (0.234, 0.22, 0.72), TEAL)
    b.fine.box((0.225, -0.22, 0.12), (0.234, 0.22, 0.48), TEAL)
    b.fine.box((0.234, -0.12, 0.64), (0.25, 0.12, 0.655), STEEL)
    b.fine.box((0.234, -0.12, 0.38), (0.25, 0.12, 0.395), STEEL)
    z = 0.785
    b.soft.swatch_box((-0.12, -0.18, z), (-0.04, -0.1, z + 0.065), "white")                                    # a tissue box
    b.fine.cyl((0.0, 0.1, z), (0.0, 0.1, z + 0.18), 0.04, WHITE_GLOSS, seg=10, r2=0.035)                       # a jug
    b.fine.cyl((0.12, -0.1, z), (0.12, -0.1, z + 0.09), 0.032, WHITE_GLOSS, seg=10, r2=0.038)                  # a cup
    b.fine.box((0.1, 0.0, z), (0.2, 0.17, z + 0.012), STRUCT)                                                  # a tablet on its charger
    b.emit.lamp_box((0.101, 0.01, z + 0.012), (0.199, 0.16, z + 0.0135), "cool_dim", LAMP_DIM)


def visitor_chair(b: SParts, seed: int = 1) -> None:
    """A visitor's chair facing +x: a wipe-clean teal seat and back on a chromed frame with four legs."""
    for sx in (-0.2, 0.2):
        for sy in (-0.2, 0.2):
            MK.rod(b.fine, (sx, sy, 0.0), (sx * 0.95, sy * 0.95, 0.44), 0.012, 0.014, STEEL, 8)
    MK.rbox(b.soft, (-0.22, -0.23, 0.44), (0.22, 0.23, 0.5), 0.02, TEAL, 2)
    MK.rbox(b.soft, (-0.26, -0.22, 0.52), (-0.21, 0.22, 0.88), 0.02, TEAL, 2, rot=Ry(-8.0))
    for sy in (-0.2, 0.2):
        MK.rod(b.fine, (-0.22, sy, 0.5), (-0.26, sy, 0.56), 0.01, 0.01, STEEL, 6)


def iv_stand(b: SParts, seed: int = 1) -> None:
    """A drip stand (origin at its foot): a five-star base on castors, a steel pole, a hook rail with two bags of fluid and a pump."""
    for k in range(5):
        a = 2 * math.pi * k / 5
        b.fine.cyl((0, 0, 0.05), (math.cos(a) * 0.27, math.sin(a) * 0.27, 0.05), 0.012, STEEL, seg=6)
        b.fine.cyl((math.cos(a) * 0.27, math.sin(a) * 0.27, 0.0), (math.cos(a) * 0.27, math.sin(a) * 0.27, 0.05), 0.02, RUBBER, seg=8)
    b.fine.cyl((0, 0, 0.05), (0, 0, 1.9), 0.012, STEEL, seg=8)
    b.fine.cyl((-0.15, 0, 1.9), (0.15, 0, 1.9), 0.008, STEEL, seg=6)
    for sx, col in ((-0.13, "m_saline"), (0.13, "m_saline")):
        b.soft.paint(MK.puff(b.soft, (sx, 0.0, 1.78), (0.045, 0.02, 0.1), SWATCH, e=0.6, nu=8, nv=6), col)
    b.body.box((-0.06, -0.05, 1.2), (0.06, 0.05, 1.42), STRUCT)
    b.emit.lamp_box((0.0601, -0.03, 1.32), (0.062, 0.03, 1.38), "green", LAMP_DIM)


def crash_cart(b: SParts) -> None:
    """A crash cart facing +x: a red body of five drawers on four castors, a steel top with a defibrillator (a screen and two paddles) and an oxygen bottle on the side, a handle."""
    for sx in (-0.26, 0.26):
        for sy in (-0.3, 0.3):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.1), 0.035, RUBBER, seg=8)
    MK.rbox(b.soft, (-0.3, -0.35, 0.1), (0.3, 0.35, 1.0), 0.015, PAINT_RED, 1)
    for k in range(5):
        z = 0.14 + k * 0.17
        b.fine.box((0.3, -0.31, z), (0.31, 0.31, z + 0.15), PAINT_RED)
        b.fine.box((0.31, -0.1, z + 0.065), (0.34, 0.1, z + 0.08), STEEL)
    b.body.box((-0.32, -0.37, 1.0), (0.32, 0.37, 1.03), STEEL)
    b.body.box((-0.2, -0.22, 1.03), (0.12, 0.22, 1.19), STRUCT)
    b.emit.label((0.121, 0.0, 1.12), 0.26, 0.11, (1, 0, 0), "scr_wave")
    for sy in (-0.1, 0.1):
        b.fine.cyl((0.18, sy, 1.03), (0.18, sy, 1.09), 0.03, STEEL, seg=8)
    b.fine.cyl((-0.1, 0.4, 0.2), (-0.1, 0.4, 0.8), 0.07, STEEL, seg=10)
    b.fine.cyl((-0.1, 0.4, 0.8), (-0.1, 0.4, 0.86), 0.03, BRASS, seg=8)
    b.fine.cyl((-0.34, -0.3, 0.8), (-0.34, 0.3, 0.8), 0.014, STEEL, seg=6)                                        # the push handle
    b.fine.cyl((-0.3, -0.3, 0.75), (-0.34, -0.3, 0.8), 0.014, STEEL, seg=6)
    b.fine.cyl((-0.3, 0.3, 0.75), (-0.34, 0.3, 0.8), 0.014, STEEL, seg=6)


def scanner_ring(b: SParts, seed: int = 1) -> None:
    """A diagnostic scanner with its patient table, the axis along x (origin: the middle of the ring on the floor): a ring of white shell with a dark bore and a lit seam, a gantry foot,
    the table on its column sliding through, a pad, a head rest, a display on a stand at the side."""
    r_out, r_in, w = 1.0, 0.42, 0.62
    zc = 1.12
    rings = []
    n = 28
    prof = [(r_out, -w / 2), (r_out, w / 2), (r_in + 0.12, w / 2 + 0.02), (r_in, w / 2 - 0.04), (r_in, -w / 2 + 0.04), (r_in + 0.12, -w / 2 - 0.02)]
    for (rr, xx) in prof:
        rings.append([(xx, zc * 0 + rr * math.cos(2 * math.pi * i / n), zc + rr * math.sin(2 * math.pi * i / n)) for i in range(n)])
    MK.stack(b.body, rings + [rings[0]], WHITE_GLOSS, cap_bottom=False, cap_top=False)
    b.body.box((-0.4, -0.7, 0.0), (0.4, 0.7, 0.12), STRUCT)
    b.body.box((-0.3, -0.5, 0.12), (0.3, 0.5, 0.22), WHITE_GLOSS)
    b.body.box((-1.7, -0.22, 0.0), (-0.9, 0.22, 0.62), WHITE_GLOSS)                                               # the table's column and its slide
    MK.rbox(b.soft, (-1.9, -0.3, 0.62), (1.5, 0.3, 0.7), 0.02, WHITE_GLOSS, 1)
    MK.rbox(b.soft, (-1.8, -0.27, 0.7), (1.4, 0.27, 0.78), 0.03, FABRIC_NAVY, 2)
    MK.rbox(b.soft, (-1.88, -0.12, 0.78), (-1.68, 0.12, 0.84), 0.02, FABRIC_NAVY, 1)
    b.emit.lamp_box((-0.3, -0.3, 0.619), (0.3, -0.298, 0.7), "medical", LAMP_DIM)


def patient_trolley(b: SParts, seed: int = 1) -> None:
    """A patient trolley facing +x (head at -x): a steel chassis on four castors, a mattress and a pillow under a folded blanket, side rails raised, a drip pole at the head."""
    for sx in (-0.85, 0.85):
        for sy in (-0.3, 0.3):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.1), 0.045, RUBBER, seg=8)
    b.body.box((-0.9, -0.28, 0.1), (0.9, 0.28, 0.16), STEEL)
    b.body.box((-0.2, -0.1, 0.16), (0.2, 0.1, 0.42), STRUCT)
    MK.rbox(b.soft, (-1.0, -0.36, 0.42), (1.0, 0.36, 0.5), 0.02, STEEL, 1)
    MK.rbox(b.soft, (-0.98, -0.34, 0.5), (0.98, 0.34, 0.6), 0.04, BEDDING, 2)
    MK.puff(b.soft, (-0.75, 0.0, 0.66), (0.17, 0.25, 0.06), BEDDING, e=0.6)
    MK.rbox(b.soft, (-0.2, -0.345, 0.52), (0.97, 0.345, 0.65), 0.04, FABRIC_GREY, 2)
    for sy in (-0.37, 0.37):
        b.fine.cyl((-0.6, sy, 0.8), (0.6, sy, 0.8), 0.014, STEEL, seg=6)
        b.fine.cyl((-0.6, sy, 0.5), (-0.6, sy, 0.8), 0.012, STEEL, seg=6)
        b.fine.cyl((0.6, sy, 0.5), (0.6, sy, 0.8), 0.012, STEEL, seg=6)


def wheelchair(b: SParts, seed: int = 1) -> None:
    """A wheelchair facing +x: two big wheels with push rims, two small casters, a steel frame, a navy sling seat and back, two arm rests and foot plates."""
    for sy in (-0.3, 0.3):
        b.soft.cyl((-0.05, sy - 0.015, 0.31), (-0.05, sy + 0.015, 0.31), 0.31, RUBBER, seg=18)
        b.fine.cyl((-0.05, sy - 0.02, 0.31), (-0.05, sy + 0.02, 0.31), 0.04, STEEL, seg=8)
        b.soft.cyl((0.38, sy - 0.015, 0.07), (0.38, sy + 0.015, 0.07), 0.07, RUBBER, seg=10)
        MK.rod(b.fine, (0.38, sy, 0.14), (0.3, sy * 0.9, 0.45), 0.01, 0.01, STEEL, 6)
        MK.rod(b.fine, (-0.2, sy * 0.85, 0.45), (-0.25, sy * 0.85, 0.95), 0.012, 0.012, STEEL, 6)
        MK.rod(b.fine, (-0.25, sy * 0.85, 0.95), (-0.4, sy * 0.85, 0.95), 0.012, 0.012, STEEL, 6)
        b.fine.box((-0.15, sy * 0.85 - 0.025, 0.62), (0.2, sy * 0.85 + 0.025, 0.65), STRUCT)
        b.fine.box((0.35, sy * 0.6 - 0.05, 0.0 + 0.1), (0.5, sy * 0.6 + 0.05, 0.11), STEEL)
    MK.rbox(b.soft, (-0.18, -0.24, 0.45), (0.22, 0.24, 0.49), 0.015, FABRIC_NAVY, 1)
    MK.rbox(b.soft, (-0.24, -0.24, 0.5), (-0.21, 0.24, 0.9), 0.015, FABRIC_NAVY, 1)


def sanitiser(b: SParts) -> None:
    """A wall dispenser of hand gel (origin: the middle of its back plate, facing +x): a white body with a teal lever and a lit drip tray."""
    MK.rbox(b.soft, (0.0, -0.06, -0.12), (0.1, 0.06, 0.12), 0.012, WHITE_GLOSS, 1)
    b.fine.box((0.1, -0.02, 0.0), (0.14, 0.02, 0.05), TEAL)
    b.fine.box((0.04, -0.05, -0.16), (0.12, 0.05, -0.12), STEEL)
    b.emit.lamp_box((0.1, -0.03, 0.08), (0.101, 0.03, 0.1), "green", LAMP_DIM)


def sharps_bin(b: SParts) -> None:
    """A yellow sharps bin on a wall bracket (origin: back, facing +x)."""
    b.soft.paint(MK.rbox(b.soft, (0.0, -0.1, -0.1), (0.12, 0.1, 0.1), 0.012, SWATCH, 1), "yellow")
    b.fine.box((0.12, -0.05, 0.04), (0.14, 0.05, 0.06), STRUCT)


def medical_sink(b: SParts, w: float = 1.8, d: float = 0.6) -> None:
    """A clinical hand-wash station against a wall, facing +x (origin: the middle of the footprint on the floor): a steel unit with two deep basins, elbow-operated taps, a splash-back and a
    mirror, a soap and a paper-towel dispenser, a waste bin under the counter."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2 - 0.02, w / 2, 0.06), STRUCT)
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.06), (d / 2 - 0.02, w / 2, 0.84), 0.01, WHITE_GLOSS, 1)
    b.fine.box((d / 2 - 0.02, -w / 2 + 0.04, 0.12), (d / 2 - 0.01, 0.0, 0.8), STEEL)
    b.fine.box((d / 2 - 0.02, 0.04, 0.12), (d / 2 - 0.01, w / 2 - 0.04, 0.8), STEEL)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, 0.84), (d / 2 + 0.02, w / 2 + 0.02, 0.88), STEEL)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, 0.88), (-d / 2 + 0.03, w / 2 + 0.02, 1.25), STEEL)                  # the splash-back
    for sy in (-w * 0.25, w * 0.25):
        b.fine.box((-0.12, sy - 0.22, 0.86), (0.14, sy + 0.22, 0.88), STEEL)                                      # the basin's rim
        b.fine.box((-0.1, sy - 0.2, 0.86), (0.12, sy + 0.2, 0.862), STRUCT)
        MK.rod(b.fine, (-d / 2 + 0.08, sy, 0.88), (-d / 2 + 0.08, sy, 1.05), 0.012, 0.012, STEEL, 6)
        MK.rod(b.fine, (-d / 2 + 0.08, sy, 1.05), (-d / 2 + 0.22, sy, 1.02), 0.012, 0.012, STEEL, 6)
        b.fine.box((0.0, sy + 0.1, 0.92), (0.16, sy + 0.18, 0.94), STEEL)
    b.fine.box((-d / 2 + 0.03, -w / 2 + 0.05, 1.3), (-d / 2 + 0.05, w / 2 - 0.05, 2.0), STEEL)                     # the mirror
    b.emit.lamp_box((-d / 2 + 0.05, -w / 2 + 0.05, 2.0), (-d / 2 + 0.07, w / 2 - 0.05, 2.03), "white_cool", LAMP_DIM)
    for sy in (-w / 2 + 0.2, w / 2 - 0.2):
        MK.rbox(b.soft, (-d / 2 + 0.03, sy - 0.08, 1.02), (-d / 2 + 0.12, sy + 0.08, 1.2), 0.01, WHITE_GLOSS, 1)


def supply_cabinet(b: SParts, w: float = 1.0, d: float = 0.62, h: float = 2.3, seed: int = 1, glass=None) -> None:
    """A tall supply cabinet facing +x: four drawers with steel pulls below, above them an open case of shelves — boxes, bottles, packs — behind a glass front. The glass is returned through
    `glass`: a list that receives the front as (x0, x1, y0, y1, z0, z1) in the piece's frame; the caller turns it into the translucent mesh (the case stays open here, so that the stores
    show through the glass and, without it, are still there)."""
    rng = random.Random(seed)
    zc = 1.1
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.06), (d / 2, w / 2, zc), 0.01, WHITE_GLOSS, 1)
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.03, 0.0), (d / 2 - 0.03, w / 2 - 0.03, 0.06), STRUCT)
    nd = 4 if zc > 0.9 else 3
    for k in range(nd):
        z = 0.1 + k * 0.24
        b.fine.box((d / 2, -w / 2 + 0.03, z), (d / 2 + 0.012, w / 2 - 0.03, z + 0.21), TEAL)
        b.fine.box((d / 2 + 0.012, -0.12, z + 0.1), (d / 2 + 0.03, 0.12, z + 0.115), STEEL)
    b.soft.box((-d / 2, -w / 2, zc), (-d / 2 + 0.025, w / 2, h), WHITE_GLOSS)                                       # the case: back, sides, top
    for sy in (-w / 2, w / 2 - 0.025):
        b.soft.box((-d / 2, sy, zc), (d / 2, sy + 0.025, h), WHITE_GLOSS)
    b.soft.box((-d / 2, -w / 2, h - 0.04), (d / 2, w / 2, h), WHITE_GLOSS)
    for z in (zc, 1.45, 1.8):                                                                                       # the shelves and their stores
        b.fine.box((-d / 2 + 0.02, -w / 2 + 0.025, z), (d / 2 - 0.03, w / 2 - 0.025, z + 0.015), STEEL)
        y = -w / 2 + 0.06
        while y < w / 2 - 0.12:
            if rng.random() < 0.55:                                                                                 # a box of supplies
                bw, bh = rng.uniform(0.1, 0.2), rng.uniform(0.1, 0.2)
                b.soft.swatch_box((-d * 0.3, y, z + 0.015), (d * 0.2, y + bw, z + 0.015 + bh), rng.choice(("white", "cream", "teal", "m_teal", "m_white", "sand")))
                y += bw + 0.02
            else:                                                                                                   # bottles
                for j in range(rng.randint(2, 3)):
                    b.soft.swatch_cyl((0.0, y + 0.03, z + 0.015), (0.0, y + 0.03, z + 0.17), 0.028, rng.choice(("m_saline", "m_white", "m_yellow", "m_teal", "m_orange")), seg=8)
                    y += 0.062
                y += 0.02
    b.emit.lamp_box((-d / 2 + 0.03, -w / 2 + 0.04, h - 0.045), (d / 2 - 0.04, w / 2 - 0.04, h - 0.04), "white_cool", LAMP_DIM)
    if glass is not None:
        glass.append((d / 2 - 0.02, d / 2 - 0.012, -w / 2 + 0.03, w / 2 - 0.03, zc + 0.03, h - 0.04))


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the theatre
def op_table(b: SParts) -> None:
    """An operating table, its long axis along x (the head at -x), origin on the floor under its column: a round base, a telescopic column in two steel stages, a steel frame with a navy
    pad in four sections, a head rest, two arm boards on swivel posts, side rails, a lit foot-end."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.07), 0.38, STRUCT, seg=20, r2=0.34)
    b.body.cyl((0, 0, 0.07), (0, 0, 0.45), 0.13, STEEL, seg=14)
    b.body.cyl((0, 0, 0.45), (0, 0, 0.78), 0.1, TRIM, seg=14)
    MK.rbox(b.soft, (-0.12, -0.2, 0.74), (0.12, 0.2, 0.82), 0.02, STEEL, 1)
    b.body.box((-1.05, -0.33, 0.8), (1.05, 0.33, 0.86), STEEL)
    for x0, x1 in ((-1.0, -0.6), (-0.58, -0.05), (-0.03, 0.55), (0.57, 1.02)):
        MK.rbox(b.soft, (x0, -0.31, 0.86), (x1, 0.31, 0.93), 0.025, FABRIC_NAVY, 2)
    MK.rbox(b.soft, (-1.18, -0.14, 0.82), (-1.0, 0.14, 0.93), 0.03, FABRIC_NAVY, 2)
    for sy in (-0.52, 0.52):
        b.body.box((-0.55, sy - 0.11, 0.86), (-0.05, sy + 0.11, 0.885), STEEL)
        b.fine.cyl((-0.3, sy * 0.62, 0.86), (-0.3, sy * 0.95, 0.86), 0.014, TRIM, seg=6)
    for sy in (-0.345, 0.345):
        b.fine.cyl((-0.9, sy, 0.83), (0.95, sy, 0.83), 0.012, TRIM, seg=6)
    b.emit.lamp_box((1.05, -0.12, 0.81), (1.052, 0.12, 0.85), "medical", LAMP_DIM)


def surgical_lamp(b: SParts, z_ceil: float = 3.6, reach: float = 0.55, z_head: float = 2.34) -> None:
    """A twin surgical lamp hung from the ceiling over the origin: a mount plate, a stem, a hub, two jointed arms each ending in a broad lit head of seven lenses in a ring of light — the
    heads at `reach` either side and `z_head` high."""
    b.body.cyl((0, 0, z_ceil - 0.07), (0, 0, z_ceil), 0.19, STRUCT, seg=18)
    b.body.cyl((0, 0, z_ceil - 0.55), (0, 0, z_ceil - 0.07), 0.04, TRIM, seg=10)
    b.body.sphere((0, 0, z_ceil - 0.55), 0.07, STEEL, seg=12, rings=8)
    for k, sgn in enumerate((1, -1)):
        x = sgn * reach
        b.body.cyl((0, 0, z_ceil - 0.55), (x, 0.0, z_ceil - 0.72), 0.03, TRIM, seg=8)
        b.body.sphere((x, 0, z_ceil - 0.72), 0.05, STEEL, seg=10, rings=6)
        b.body.cyl((x, 0, z_ceil - 0.72), (x, 0, z_head + 0.22), 0.03, TRIM, seg=8)
        r = 0.42 if k == 0 else 0.34
        b.body.cyl((x, 0, z_head + 0.22), (x, 0, z_head + 0.12), 0.1, STEEL, seg=12)
        b.body.cyl((x, 0, z_head + 0.12), (x, 0, z_head), r, COMPOSITE, seg=26, r2=r * 0.85)
        b.emit.lamp_cyl((x, 0, z_head + 0.001), (x, 0, z_head - 0.003), r * 0.9, "white_cool", LAMP_HOT, seg=26)
        for j in range(7):
            a = 2 * math.pi * j / 6
            rr = r * 0.55 if j else 0.0
            b.fine.cyl((x + math.cos(a) * rr, math.sin(a) * rr, z_head - 0.004), (x + math.cos(a) * rr, math.sin(a) * rr, z_head), r * 0.17, STEEL, seg=10)
        b.fine.cyl((x + r * 0.5, 0, z_head + 0.06), (x + r * 0.5 + 0.26, 0, z_head + 0.06), 0.012, STEEL, seg=6)  # the sterile handle


def anesthesia_machine(b: SParts) -> None:
    """An anaesthesia machine on four wheels facing +x: a cabinet of drawers, a work shelf, a tall back with a gas panel and two flow tubes, a screen on an arm, a ventilator bellows
    in a clear dome, hoses to the patient."""
    for sx in (-0.26, 0.26):
        for sy in (-0.33, 0.33):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.1), 0.04, RUBBER, seg=8)
    MK.rbox(b.soft, (-0.3, -0.36, 0.1), (0.3, 0.36, 0.95), 0.015, WHITE_GLOSS, 1)
    for k in range(3):
        b.fine.box((0.3, -0.32, 0.15 + k * 0.26), (0.31, 0.32, 0.37 + k * 0.26), TEAL)
        b.fine.box((0.31, -0.08, 0.24 + k * 0.26), (0.33, 0.08, 0.255 + k * 0.26), STEEL)
    b.body.box((-0.32, -0.38, 0.95), (0.34, 0.38, 0.99), STEEL)
    MK.rbox(b.soft, (-0.3, -0.34, 0.99), (-0.12, 0.34, 1.75), 0.02, WHITE_GLOSS, 1)
    for sy in (-0.2, -0.12):                                                                                      # the two flow tubes
        b.fine.cyl((-0.1, sy, 1.1), (-0.1, sy, 1.5), 0.016, STEEL, seg=8)
    for sy, col in ((-0.2, "m_orange"), (-0.12, "m_teal")):
        b.soft.paint(MK.puff(b.soft, (-0.1, sy, 1.3), (0.02, 0.02, 0.025), SWATCH, e=1.0, nu=6, nv=4), col)
    b.fine.cyl((0.05, 0.22, 0.99), (0.05, 0.22, 1.1), 0.075, WHITE_GLOSS, seg=14)
    b.fine.cyl((0.05, 0.22, 1.1), (0.05, 0.22, 1.3), 0.065, STEEL, seg=14)
    MK.rod(b.fine, (-0.2, 0.0, 1.75), (0.1, 0.0, 1.8), 0.02, 0.02, STEEL, 6)
    b.body.box((0.06, -0.2, 1.62), (0.14, 0.2, 1.9), STRUCT)
    b.emit.label((0.1405, 0.0, 1.76), 0.38, 0.2, (1, 0, 0), "scr_wave")
    for sy in (-0.1, 0.1):
        b.soft.tube([(0.2, sy, 1.3), (0.4, sy * 2, 1.2), (0.6, sy * 3, 0.9)], 0.014, STRUCT, seg=6)


def instrument_trolley(b: SParts, seed: int = 1) -> None:
    """An instrument trolley facing +x, 0.76 x 0.48 m: two steel trays on four posts with castors, the upper one laid with instruments in rows (scalpels, forceps, scissors, clamps) on a
    blue drape, the lower with bowls and a sterile pack."""
    rng = random.Random(seed)
    for sx in (-0.34, 0.34):
        for sy in (-0.21, 0.21):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.07), 0.03, RUBBER, seg=8)
            b.fine.cyl((sx, sy, 0.07), (sx, sy, 0.92), 0.012, STEEL, seg=6)
    for z in (0.35, 0.9):
        b.body.box((-0.38, -0.24, z), (0.38, 0.24, z + 0.025), STEEL)
        b.fine.box((-0.38, -0.24, z + 0.025), (0.38, -0.225, z + 0.045), STEEL)
        b.fine.box((-0.38, 0.225, z + 0.025), (0.38, 0.24, z + 0.045), STEEL)
    b.soft.swatch_box((-0.33, -0.2, 0.925), (0.33, 0.2, 0.932), "m_teal")
    for k in range(9):
        y = -0.18 + k * 0.045
        x0 = -0.28 + rng.uniform(0, 0.06)
        ln = rng.uniform(0.15, 0.27)
        b.fine.box((x0, y, 0.932), (x0 + ln, y + 0.01, 0.94), STEEL)
        b.fine.box((x0 + ln * 0.55, y - 0.004, 0.932), (x0 + ln * 0.8, y + 0.014, 0.945), STEEL)
    b.fine.cyl((0.2, 0.0, 0.375), (0.2, 0.0, 0.43), 0.09, STEEL, seg=12, r2=0.11)
    b.soft.swatch_box((-0.3, -0.18, 0.375), (-0.05, 0.1, 0.43), "m_white")


def hospital_bed_light(b: SParts) -> None:
    """A wall-mounted examination lamp on a swing arm (origin: the middle of its wall plate, facing +x): a plate, two arm segments, a lit round head."""
    b.fine.cyl((0.0, 0.0, -0.03), (0.04, 0.0, 0.03), 0.07, STEEL, seg=12)
    MK.rod(b.fine, (0.05, 0.0, 0.0), (0.45, 0.2, 0.05), 0.014, 0.014, STEEL, 6)
    MK.rod(b.fine, (0.45, 0.2, 0.05), (0.75, -0.05, -0.1), 0.014, 0.014, STEEL, 6)
    b.fine.cyl((0.75, -0.05, -0.1), (0.75, -0.05, -0.2), 0.12, WHITE_GLOSS, seg=16, r2=0.14)
    b.emit.lamp_cyl((0.75, -0.05, -0.2), (0.75, -0.05, -0.204), 0.12, "white_cool", LAMP, seg=16)


def hospital_bed(b: SParts, seed: int = 1, blanket: str = FABRIC_NAVY) -> None:
    """A hospital bed, the head at -x, 2.1 x 1.0 m (origin: its middle on the floor; the mattress top 0.6 m up, where a patient lies: the sleeper's place is on it): four braked castors, a
    base and two lifting columns, a steel platform, a mattress in two parts — the back section raised 20 degrees — a pillow, a sheet and a blanket folded back, white head and foot boards with
    a teal panel, two side rails on the leg section, a push handle, a controller on a lead, a net with a book."""
    for sx in (-0.85, 0.8):
        for sy in (-0.4, 0.4):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.1), 0.045, RUBBER, seg=8)
    b.body.box((-0.9, -0.38, 0.1), (0.85, 0.38, 0.17), STEEL)
    for sx in (-0.5, 0.4):
        b.body.box((sx - 0.06, -0.12, 0.17), (sx + 0.06, 0.12, 0.4), STRUCT)
    b.body.box((-1.0, -0.46, 0.4), (1.0, 0.46, 0.46), STEEL)
    MK.rbox(b.soft, (-0.2, -0.45, 0.46), (0.97, 0.45, 0.58), 0.03, WHITE_GLOSS, 1)                                   # the leg section
    with b.at(T(-0.2, 0.0, 0.52) @ Ry(-20.0)):                                                                      # the raised back section, hinged at the hip
        MK.rbox(b.soft, (-0.8, -0.45, 0.0), (0.0, 0.45, 0.12), 0.03, WHITE_GLOSS, 1)
        MK.puff(b.soft, (-0.62, 0.0, 0.17), (0.2, 0.3, 0.07), BEDDING, e=0.6)
    MK.rbox(b.soft, (-0.18, -0.465, 0.52), (0.97, 0.465, 0.64), 0.04, blanket, 2)
    MK.rbox(b.soft, (-0.2, -0.46, 0.6), (-0.04, 0.46, 0.665), 0.03, BEDDING, 1)                                       # the fold of the sheet
    b.body.box((-1.06, -0.47, 0.34), (-1.0, 0.47, 1.05), WHITE_GLOSS)                                               # the head board with a teal panel
    b.fine.box((-1.065, -0.4, 0.5), (-1.06, 0.4, 0.95), TEAL)
    b.body.box((0.99, -0.47, 0.34), (1.05, 0.47, 0.9), WHITE_GLOSS)                                                 # the foot board
    b.fine.box((1.05, -0.4, 0.45), (1.055, 0.4, 0.85), TEAL)
    for sy in (-0.49, 0.49):                                                                                         # side rails on the leg section, raised
        b.fine.cyl((-0.1, sy, 0.8), (0.8, sy, 0.8), 0.014, STEEL, seg=8)
        b.fine.cyl((-0.1, sy, 0.68), (0.8, sy, 0.68), 0.012, STEEL, seg=8)
        for sx in (-0.1, 0.35, 0.8):
            b.fine.cyl((sx, sy, 0.46), (sx, sy, 0.8), 0.012, STEEL, seg=6)
    b.fine.cyl((1.05, -0.3, 0.9), (1.05, 0.3, 0.9), 0.016, STEEL, seg=8)                                              # the push handle
    b.soft.tube([(0.95, 0.49, 0.78), (0.98, 0.52, 0.55), (0.9, 0.5, 0.35)], 0.006, STRUCT, seg=5)                   # the controller on its lead
    b.fine.box((0.86, 0.485, 0.34), (0.94, 0.515, 0.42), STRUCT)
    b.soft.box((0.1, 0.46, 0.2), (0.4, 0.485, 0.4), FABRIC_GREY)                                                     # a net with a book
    b.soft.swatch_box((0.15, 0.462, 0.25), (0.3, 0.48, 0.34), "denim")
