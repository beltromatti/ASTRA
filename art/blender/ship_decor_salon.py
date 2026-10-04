"""ASN Aquila interior kit (ARTE-INTERNI-2): the barber's and the tailor's — a barber's pole, a salon dryer chair, a wall shelf of bottles, a sewing machine, a rack of cloth bolts, a dress
form, a three-way fitting mirror. Same conventions as ship_decor.py: every function builds ONE piece in its own frame (origin on the floor, +x its front, unless it hangs on a wall) into an SParts.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Ry, Rz, T
from ship_lib import BRASS, CERAMIC, DGLASS, LAMP_DIM, STEEL, STRUCT, SWATCH, TRIM, WALNUT, SParts


def barber_pole(b: SParts, h: float = 1.0) -> None:
    """A barber's pole standing on the floor by the door (origin at its foot): a brass foot and cap, a white cylinder with red and blue bands round it."""
    MK.lathe(b.fine, [(0.001, 0.0), (0.13, 0.0), (0.13, 0.03), (0.1, 0.06), (0.085, 0.1)], (0, 0, 0), BRASS, seg=20)
    b.soft.paint(b.soft.cyl((0, 0, 0.1), (0, 0, h), 0.082, SWATCH, seg=20), "white")
    n = 9
    for k in range(n):
        z0 = 0.1 + (h - 0.1) * k / n
        b.soft.paint(b.soft.cyl((0.0, 0.0, z0), (0.0, 0.0, z0 + (h - 0.1) / n * 0.5), 0.0845, SWATCH, seg=20), "red" if k % 2 == 0 else "blue")
    MK.lathe(b.fine, [(0.085, h), (0.1, h + 0.02), (0.07, h + 0.07), (0.03, h + 0.1), (0.001, h + 0.1)], (0, 0, 0), BRASS, seg=20)
    b.emit.lamp_cyl((0, 0, h + 0.1), (0, 0, h + 0.14), 0.03, "white_warm", LAMP_DIM, seg=10)


def barber_chair(b: SParts) -> None:
    """A barber's chair (origin on the floor under the seat, facing +x): a chrome base and a two-stage hydraulic column, a rolled leather seat, a back tilted a little with its headrest, padded
    arms on chrome posts, a footrest with a rubber pad."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.05), 0.34, STEEL, seg=24, r2=0.3)
    MK.lathe(b.fine, [(0.1, 0.05), (0.1, 0.12), (0.075, 0.14), (0.075, 0.3), (0.06, 0.32), (0.06, 0.42)], (0, 0, 0), STEEL, seg=16)
    b.soft.paint(MK.rbox(b.soft, (-0.28, -0.29, 0.42), (0.3, 0.29, 0.58), 0.06, SWATCH, 2), "oxblood")             # the seat
    back = b.soft
    with b.at(T(-0.3, 0.0, 0.56) @ Ry(-12.0)):
        back.paint(MK.rbox(back, (-0.07, -0.29, 0.0), (0.07, 0.29, 0.62), 0.05, SWATCH, 2), "oxblood")             # the back
        back.paint(MK.rbox(back, (-0.06, -0.15, 0.6), (0.06, 0.15, 0.82), 0.04, SWATCH, 2), "oxblood")             # the headrest
    for sy in (-1, 1):                                                                                              # arms: a chrome post and a padded rest
        b.fine.cyl((0.0, sy * 0.34, 0.44), (0.0, sy * 0.34, 0.64), 0.018, STEEL, seg=8)
        b.soft.paint(MK.rbox(b.soft, (-0.2, sy * 0.34 - 0.04, 0.62), (0.22, sy * 0.34 + 0.04, 0.7), 0.025, SWATCH, 1), "charcoal")
    b.fine.cyl((0.28, -0.14, 0.18), (0.4, -0.14, 0.34), 0.014, STEEL, seg=6)                                       # the footrest
    b.fine.cyl((0.28, 0.14, 0.18), (0.4, 0.14, 0.34), 0.014, STEEL, seg=6)
    b.soft.paint(MK.rbox(b.soft, (0.34, -0.2, 0.3), (0.58, 0.2, 0.36), 0.02, SWATCH, 1), "charcoal")


def cloth_shelf(b: SParts, w: float = 2.4, h: float = 2.1, rows: int = 4, seed: int = 1) -> None:
    """A shelving unit of rolled cloth (origin on the floor at the middle of its back, front +x): a walnut frame, `rows` shelves each with a row of rolls lying across it in the palette's
    colours and lengths."""
    rng = random.Random(seed)
    b.body.box((-0.2, -w / 2, 0.0), (-0.17, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((-0.2, sy, 0.0), (0.2, sy + 0.03, h), WALNUT)
    for k in range(rows):
        z = 0.1 + k * (h - 0.2) / (rows - 1)
        b.body.box((-0.2, -w / 2, z), (0.2, w / 2, z + 0.025), WALNUT)
        y = -w / 2 + 0.08
        while y < w / 2 - 0.2:
            r = rng.uniform(0.055, 0.075)
            col = rng.choice(("navy", "oxblood", "forest", "mustard", "teal", "plum", "rose", "slate", "cream", "denim", "tan"))
            b.soft.paint(b.soft.cyl((-0.14, y + r, z + 0.025 + r), (0.17, y + r, z + 0.025 + r), r, SWATCH, seg=10), col)
            y += 2 * r + 0.01


def hood_dryer(b: SParts) -> None:
    """A salon dryer chair (origin on the floor under the seat, front +x): a pedestal and a cushioned seat, a hood on an arm behind it, a lit status lamp."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.05), 0.28, STRUCT, seg=18)
    b.body.cyl((0, 0, 0.05), (0, 0, 0.42), 0.05, TRIM, seg=10)
    b.soft.paint(MK.rbox(b.soft, (-0.26, -0.26, 0.42), (0.26, 0.26, 0.5), 0.03, SWATCH, 2), "rose")
    b.soft.paint(MK.rbox(b.soft, (-0.3, -0.25, 0.5), (-0.2, 0.25, 1.0), 0.04, SWATCH, 2), "rose")
    b.fine.cyl((-0.28, 0.0, 1.0), (-0.28, 0.0, 1.9), 0.022, TRIM, seg=8)
    b.fine.cyl((-0.28, 0.0, 1.9), (0.1, 0.0, 1.85), 0.018, TRIM, seg=8)
    MK.lathe(b.soft, [(0.001, 1.95), (0.16, 1.93), (0.28, 1.84), (0.3, 1.62), (0.27, 1.55), (0.24, 1.58), (0.25, 1.65), (0.22, 1.82), (0.001, 1.88)], (0.1, 0.0, 0.0), CERAMIC, seg=20)
    b.emit.lamp_box((0.38, -0.02, 1.85), (0.4, 0.02, 1.87), "green", LAMP_DIM)


def bottle_shelf(b: SParts, w: float = 2.0, h: float = 1.9, rows: int = 4, seed: int = 1) -> None:
    """A wall shelf of bottles and jars (origin at the middle of its back, front +x): steel shelves with a lit underside, bottles in the palette's colours (shampoo, tonic, lotion), jars, a
    few boxes."""
    rng = random.Random(seed)
    b.body.box((-0.03, -w / 2, 0.0), (0.0, w / 2, h), STRUCT)
    zs = [0.3 + k * (h - 0.35) / (rows - 1) for k in range(rows)]
    for z in zs:
        b.body.box((0.0, -w / 2, z), (0.22, w / 2, z + 0.02), STEEL)
        b.emit.lamp_box((0.0, -w / 2 + 0.03, z - 0.012), (0.2, w / 2 - 0.03, z - 0.008), "white_warm", LAMP_DIM)
        y = -w / 2 + 0.06
        while y < w / 2 - 0.1:
            kind = rng.random()
            col = rng.choice(("teal", "rose", "mustard", "white", "denim", "forest", "cream", "orange", "plum"))
            if kind < 0.6:
                r, hh = rng.uniform(0.028, 0.04), rng.uniform(0.15, 0.24)
                b.soft.paint(b.soft.cyl((0.11, y + r, z + 0.02), (0.11, y + r, z + 0.02 + hh), r, SWATCH, seg=8), col)
                b.soft.paint(b.soft.cyl((0.11, y + r, z + 0.02 + hh), (0.11, y + r, z + 0.02 + hh + 0.03), r * 0.45, SWATCH, seg=6), "grey3")
                y += 2 * r + 0.012
            elif kind < 0.85:
                r, hh = rng.uniform(0.04, 0.055), rng.uniform(0.07, 0.1)
                b.soft.paint(b.soft.cyl((0.11, y + r, z + 0.02), (0.11, y + r, z + 0.02 + hh), r, SWATCH, seg=10), col)
                y += 2 * r + 0.012
            else:
                bw = rng.uniform(0.08, 0.14)
                b.soft.swatch_slab((0.04, y, z + 0.02), (0.17, y + bw, z + 0.02 + rng.uniform(0.1, 0.16)), col)
                y += bw + 0.012


def sewing_machine(b: SParts) -> None:
    """A sewing machine on a table top (origin under it on the surface, front +x): a base plate, the arm and head, a spool on top, the needle and a lit lamp."""
    b.body.box((-0.2, -0.16, 0.0), (0.2, 0.16, 0.025), STEEL)
    b.soft.paint(MK.rbox(b.soft, (-0.18, -0.07, 0.025), (0.0, 0.07, 0.3), 0.03, SWATCH, 2), "cream")
    b.soft.paint(MK.rbox(b.soft, (-0.18, -0.07, 0.24), (0.2, 0.07, 0.31), 0.03, SWATCH, 2), "cream")
    b.soft.paint(MK.rbox(b.soft, (0.12, -0.06, 0.12), (0.2, 0.06, 0.31), 0.025, SWATCH, 2), "cream")
    b.fine.cyl((-0.1, 0.0, 0.31), (-0.1, 0.0, 0.37), 0.025, STEEL, seg=10)
    b.soft.paint(b.soft.cyl((-0.1, 0.0, 0.37), (-0.1, 0.0, 0.41), 0.03, SWATCH, seg=10), "red")
    b.fine.cyl((0.19, 0.0, 0.11), (0.19, 0.0, 0.2), 0.004, STEEL, seg=4)
    b.emit.lamp_box((0.14, -0.02, 0.23), (0.17, 0.02, 0.24), "white_warm", LAMP_DIM)


def fabric_bolts(b: SParts, n: int = 7, seed: int = 1) -> None:
    """Bolts of cloth standing on end on a plinth (origin at the middle of its base): `n` rolls of the palette's colours of different heights, a brass tag on each end."""
    rng = random.Random(seed)
    b.body.box((-0.25, -0.1 - n * 0.075, 0.0), (0.25, 0.1 + n * 0.075, 0.05), STRUCT)
    for k in range(n):
        y = -n * 0.075 + 0.075 + k * 0.15
        h = rng.uniform(0.7, 1.15)
        col = rng.choice(("navy", "oxblood", "forest", "mustard", "teal", "plum", "rose", "slate", "cream", "denim"))
        b.soft.paint(b.soft.cyl((0.0, y, 0.05), (0.0, y, 0.05 + h), 0.062, SWATCH, seg=10), col)
        b.soft.paint(b.soft.cyl((0.0, y, 0.05 + h), (0.0, y, 0.05 + h + 0.004), 0.03, SWATCH, seg=8), "tan")


def dress_form(b: SParts, h: float = 1.55) -> None:
    """A tailor's dress form on a stand (origin on the floor under it): a three-legged foot, a pole, a turned torso with its shoulders, a neck cap, a tape measure round the waist."""
    for k in range(3):
        a = 2.0944 * k
        b.fine.cyl((0.0, 0.0, 0.05), (0.26 * math.cos(a), 0.26 * math.sin(a), 0.0), 0.014, TRIM, seg=6)
    b.fine.cyl((0, 0, 0.05), (0, 0, 1.0), 0.016, TRIM, seg=8)
    b.soft.paint(MK.lathe(b.soft, [(0.001, 0.98), (0.14, 1.0), (0.17, 1.12), (0.15, 1.24), (0.17, 1.38), (0.2, 1.46), (0.1, 1.54), (0.045, 1.58), (0.001, 1.6)], (0, 0, 0), SWATCH, seg=18), "sand")
    b.soft.paint(b.soft.cyl((0, 0, 1.2), (0, 0, 1.215), 0.157, SWATCH, seg=18), "mustard")
    b.fine.cyl((0, 0, 1.6), (0, 0, 1.66), 0.02, BRASS, seg=8)


def fitting_mirror(b: SParts, w: float = 1.0, h: float = 2.0) -> None:
    """A three-way tailor's mirror on the floor (origin at the middle of its foot, the glass facing +x): a centre panel and two wings in a walnut frame, a brass foot."""
    for k, (yy, ang) in enumerate(((0.0, 0.0), (-w * 0.5 - 0.02, 0.35), (w * 0.5 + 0.02, -0.35))):
        x0 = 0.0 if k == 0 else -0.04
        pw = w * (1.0 if k == 0 else 0.55)
        with b.at(T(0.0, yy, 0.0) @ Rz(math.degrees(ang))):
            b.body.box((-0.03, -pw / 2, 0.15), (0.0, pw / 2, 0.15 + h), WALNUT)
            b.fine.box((0.0, -pw / 2 + 0.04, 0.2), (0.004, pw / 2 - 0.04, 0.11 + h), DGLASS)
    b.fine.box((-0.2, -w * 0.9, 0.0), (0.12, w * 0.9, 0.04), BRASS)
