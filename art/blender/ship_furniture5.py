"""ASN Aquila interior kit: furniture of the Marines' deck (NAVE-2) — the barracks' footlockers, boot racks and training corner, the kit room's helmet shelves and armour bays,
the firing range's booths, targets, baffles and back stop. Fifth library, after ship_furniture.py .. ship_furniture4.py (the shuttle bay's); same conventions: every function
builds one piece in ITS OWN frame (origin on the floor, +x the piece's front, +y its left, z up) into a `SParts` (body = bevelled hard-surface, fine = small details, soft =
cloth, rubber and thin details, emit = lamps and labels); rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math
import random

import ship_furniture2 as G
from bridge3_lib import Ry
from ship_lib import (COMPOSITE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, FABRIC_GREY, FABRIC_RUST, IVORY, LAMP, LAMP_DIM, RUBBER, STEEL, STRUCT, TRIM, SParts)


# ---------------------------------------------------------------------------------------------------------------------- the barracks
def footlocker(b: SParts, w: float = 0.9, d: float = 0.45, h: float = 0.45, mat: str = CRATE_OLIVE) -> None:
    """A marine's footlocker (lid side +x): an olive steel box with a lid, two latches, a handle at each end and a stencilled strip."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h - 0.07), mat)
    b.body.box((-d / 2 - 0.01, -w / 2 - 0.01, h - 0.07), (d / 2 + 0.01, w / 2 + 0.01, h), mat)
    b.soft.box((-d / 2 - 0.012, -w / 2 - 0.012, h - 0.075), (d / 2 + 0.012, w / 2 + 0.012, h - 0.065), TRIM)
    for sy in (-w / 4, w / 4):
        b.soft.box((d / 2 + 0.008, sy - 0.04, h - 0.14), (d / 2 + 0.03, sy + 0.04, h - 0.04), TRIM)
    for sy in (-w / 2 - 0.02, w / 2):
        b.soft.box((-0.07, sy, h - 0.2), (0.07, sy + 0.02, h - 0.17), TRIM)
    b.emit.label((d / 2 + 0.002, 0.0, 0.14), w * 0.5, w * 0.5 / 8.0, (1, 0, 0), "hazard_h")


def boot_rack(b: SParts, n: int = 6) -> None:
    """A low two-tier boot rack along y, facing +x: a steel frame with n pairs of boots on each tier (toes towards +x) and an olive backboard."""
    w = n * 0.34
    b.body.box((-0.17, -w / 2, 0.0), (0.2, w / 2, 0.04), STRUCT)
    for z in (0.04, 0.36):
        b.body.box((-0.17, -w / 2, z), (0.2, w / 2, z + 0.025), TRIM)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((-0.17, sy, 0.0), (-0.14, sy + 0.03, 0.72), TRIM)
        b.body.box((0.17, sy, 0.0), (0.2, sy + 0.03, 0.4), TRIM)
    for tier, z in enumerate((0.065, 0.385)):
        for k in range(n):
            y = -w / 2 + 0.17 + k * 0.34
            for sy in (-0.07, 0.07):
                b.soft.box((-0.1, y + sy - 0.05, z), (0.16, y + sy + 0.05, z + 0.08), RUBBER)                                  # the foot
                b.soft.box((-0.1, y + sy - 0.05, z + 0.08), (0.0, y + sy + 0.05, z + 0.26), FABRIC_GREY if (k + tier) % 2 else RUBBER)   # the shaft
    b.soft.box((-0.17, -w / 2, 0.66), (-0.14, w / 2, 0.72), CRATE_OLIVE)


def training_corner(b: SParts, h_ceil: float = 3.4) -> None:
    """The marines' corner for exercise, origin in the middle of a 3.4 x 2.6 m rubber mat: a pull-up frame across y at +x, a rack of dumbbells at -x, a heavy bag on a chain
    from the ceiling (at `h_ceil`), a flat bench with a barbell on posts."""
    b.soft.box((-1.7, -1.3, 0.0), (1.7, 1.3, 0.02), RUBBER)
    b.soft.box((-1.7, -1.3, 0.02), (1.7, -1.26, 0.026), CRATE_ORANGE)
    b.soft.box((-1.7, 1.26, 0.02), (1.7, 1.3, 0.026), CRATE_ORANGE)
    for sy in (-1.0, 1.0):                                                                              # the pull-up frame: two posts and a bar
        b.body.cyl((1.2, sy, 0.02), (1.2, sy, 2.4), 0.04, TRIM, seg=10)
        b.body.box((1.1, sy - 0.15, 0.02), (1.3, sy + 0.15, 0.04), STRUCT)
    b.body.cyl((1.2, -1.0, 2.35), (1.2, 1.0, 2.35), 0.025, STEEL, seg=10)
    b.soft.cyl((1.2, -0.1, 2.35), (1.2, 0.1, 2.35), 0.032, RUBBER, seg=8)
    for k in range(6):                                                                                  # the dumbbell rack: two shelves of three pairs
        z = 0.42 + (k // 3) * 0.4
        y = -0.55 + (k % 3) * 0.55
        b.body.box((-1.7, y - 0.22, z - 0.04), (-1.4, y + 0.22, z), STEEL)
        for sy in (-0.14, 0.14):
            b.soft.cyl((-1.68, y + sy, z + 0.07), (-1.42, y + sy, z + 0.07), 0.04, STRUCT, seg=8)
            b.soft.cyl((-1.64, y + sy, z + 0.07), (-1.54, y + sy, z + 0.07), 0.1, RUBBER, seg=10)
            b.soft.cyl((-1.56, y + sy, z + 0.07), (-1.46, y + sy, z + 0.07), 0.1, RUBBER, seg=10)
    for sy in (-0.9, -0.55, 0.0, 0.55, 0.9):
        b.body.box((-1.7, sy - 0.02, 0.0), (-1.66, sy + 0.02, 0.8), TRIM)
    b.soft.cyl((-0.1, -0.4, 0.55), (-0.1, -0.4, 1.7), 0.17, FABRIC_RUST, seg=14)                       # the heavy bag on its chain
    b.soft.cyl((-0.1, -0.4, 1.7), (-0.1, -0.4, 1.74), 0.18, RUBBER, seg=14)
    b.soft.cyl((-0.1, -0.4, 0.51), (-0.1, -0.4, 0.55), 0.18, RUBBER, seg=14)
    b.soft.cyl((-0.1, -0.4, 1.74), (-0.1, -0.4, h_ceil), 0.012, TRIM, seg=5)
    b.body.box((0.2, 0.5, 0.0), (0.9, 0.56, 0.4), STRUCT)                                               # the bench and the barbell
    b.body.box((0.2, 0.9, 0.0), (0.9, 0.96, 0.4), STRUCT)
    b.soft.box((0.15, 0.48, 0.4), (0.95, 0.98, 0.46), FABRIC_GREY)
    for sx in (0.35, 0.75):
        b.body.box((sx - 0.03, 0.2, 0.0), (sx + 0.03, 0.24, 1.0), TRIM)
        b.body.box((sx - 0.03, 1.22, 0.0), (sx + 0.03, 1.26, 1.0), TRIM)
    b.body.cyl((0.55, 0.1, 1.02), (0.55, 1.36, 1.02), 0.016, STEEL, seg=8)
    for sy in (0.2, 1.26):
        b.soft.cyl((0.55, sy - 0.04, 1.02), (0.55, sy + 0.04, 1.02), 0.2, RUBBER, seg=14)


# ---------------------------------------------------------------------------------------------------------------------- the kit room
def helmet_shelf(b: SParts, w: float = 2.4, rows: int = 3, seed: int = 1) -> None:
    """A wall shelf unit facing +x for helmets: rows of shelves under a lit sign, a helmet on each (a dome with a dark visor), a status lamp under each."""
    rng = random.Random(seed)
    h = 0.5 * rows + 0.2
    b.body.box((-0.3, -w / 2, 0.0), (-0.22, w / 2, h), COMPOSITE)
    n = int(w / 0.45)
    for r in range(rows):
        z = 0.2 + r * 0.5
        b.body.box((-0.3, -w / 2, z), (0.0, w / 2, z + 0.03), STEEL)
        for k in range(n):
            y = -w / 2 + (k + 0.5) * w / n
            b.soft.sphere((-0.14, y, z + 0.03 + 0.14), 0.145, [CRATE_OLIVE, CRATE_GREY, CRATE_OLIVE][(k + r) % 3], seg=12, rings=8, squash=(1.1, 1.0, 0.95))
            b.soft.box((-0.03, y - 0.09, z + 0.03 + 0.1), (0.01, y + 0.09, z + 0.03 + 0.17), DGLASS)
            b.emit.lamp_box((-0.01, y - 0.03, z - 0.012), (0.0, y + 0.03, z), "green" if rng.random() > 0.15 else "amber", LAMP_DIM)
    b.body.box((-0.3, -w / 2, h), (0.0, w / 2, h + 0.04), TRIM)
    b.emit.label_fit((-0.001, 0.0, h + 0.2), min(1.4, w - 0.4), "eq_helmets", (1, 0, 0))


def armour_bay(b: SParts, mat: str = COMPOSITE) -> None:
    """A bay for one suit of battle dress facing +x, 1 m wide: a backing panel with a header, the armour on its dummy, a boot tray with a pair of boots, a lit seal-check lamp."""
    b.body.box((-0.34, -0.5, 0.0), (-0.28, 0.5, 2.1), COMPOSITE)
    b.body.box((-0.34, -0.5, 2.1), (0.0, 0.5, 2.14), TRIM)
    b.body.box((-0.34, -0.5, 0.0), (0.12, -0.46, 0.02), STRUCT)
    b.body.box((-0.34, 0.46, 0.0), (0.12, 0.5, 0.02), STRUCT)
    G.armor_stand(b, mat)
    b.soft.box((-0.2, -0.3, 0.0), (0.14, 0.3, 0.04), RUBBER)
    b.soft.box((-0.05, -0.2, 0.04), (0.1, -0.08, 0.14), RUBBER)
    b.soft.box((-0.05, 0.08, 0.04), (0.1, 0.2, 0.14), RUBBER)
    b.emit.lamp_box((-0.27, -0.12, 1.9), (-0.26, 0.12, 1.94), "green", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------------- the firing range
def range_booth(b: SParts, w: float = 2.0, left: bool = True, right: bool = True, lane: str = "eq_lane1") -> None:
    """One firing booth, origin at the shooter's place on the floor, +x downrange: a counter at 1.0 m with a steel top and a ledge, a small control screen on it, the dividers
    (floor to above head height) on the sides asked for, a rubber mat under the feet, ear defenders on a hook, the lane's number hung over the counter, a hazard strip at its foot."""
    b.body.box((0.5, -w / 2 + 0.06, 0.06), (1.1, w / 2 - 0.06, 1.0), COMPOSITE)
    b.body.box((0.46, -w / 2 + 0.04, 1.0), (1.14, w / 2 - 0.04, 1.05), STEEL)
    b.body.box((0.5, -w / 2 + 0.06, 0.0), (1.1, w / 2 - 0.06, 0.06), STRUCT)
    b.soft.box((1.05, -w / 2 + 0.1, 1.05), (1.14, w / 2 - 0.1, 1.12), TRIM)                              # the ledge
    b.body.box((0.62, -0.25, 1.05), (0.9, 0.25, 1.11), STRUCT)                                          # the control screen on its stand
    b.soft.box((0.62, -0.23, 1.11), (0.64, 0.23, 1.33), DGLASS)
    b.emit.label((0.641, 0.0, 1.22), 0.44, 0.2, (1, 0, 0), "scr_data")
    b.soft.box((-1.1, -0.45, 0.0), (0.2, 0.45, 0.012), RUBBER)                                          # the mat
    for sy, on in ((-1, left), (1, right)):
        if on:
            y = sy * (w / 2 - 0.03)
            b.body.box((-1.7, y - 0.03, 0.0), (0.7, y + 0.03, 1.95), COMPOSITE)
            b.soft.box((-1.7, y - 0.035, 1.92), (0.7, y + 0.035, 1.97), TRIM)
            b.soft.box((-1.7, y - 0.035, 0.0), (0.7, y + 0.035, 0.1), STRUCT)
    sy = -1 if left else 1
    b.soft.cyl((-0.9, sy * (w / 2 - 0.07), 1.5), (-0.9, sy * (w / 2 - 0.12), 1.5), 0.015, TRIM, seg=6)   # the ear defenders on their hook
    b.soft.sphere((-0.9, sy * (w / 2 - 0.16), 1.42), 0.045, CRATE_ORANGE, seg=8, rings=6)
    b.emit.label((1.141, 0.0, 0.2), w - 0.4, 0.07, (1, 0, 0), "hazard_h")
    b.emit.label_fit((0.9, 0.0, 2.55), 0.7, lane, (-1, 0, 0))
    for sy2 in (-0.3, 0.3):
        b.soft.cyl((0.9, sy2, 2.6), (0.9, sy2, 3.5), 0.01, TRIM, seg=5)


def target_stand(b: SParts, kind: int = 0) -> None:
    """A silhouette target on a weighted foot, its face towards +x (turn it to face the shooters): a pale board with a dark human shape (kind 0) or rings (kind 1),
    a scoring lamp above it and two stays."""
    b.body.box((-0.2, -0.28, 0.0), (0.2, 0.28, 0.14), STRUCT)
    b.body.box((-0.03, -0.03, 0.14), (0.03, 0.03, 0.55), TRIM)
    b.body.box((-0.03, -0.3, 0.55), (0.0, 0.3, 1.75), IVORY)
    b.soft.box((-0.04, -0.3, 0.55), (-0.03, 0.3, 1.75), STRUCT)
    if kind == 0:
        b.soft.sphere((0.004, 0.0, 1.55), 0.1, STRUCT, seg=10, rings=6, squash=(0.12, 1.0, 1.0))
        b.soft.box((0.0, -0.26, 1.12), (0.012, 0.26, 1.42), STRUCT)
        b.soft.box((0.0, -0.17, 0.6), (0.012, 0.17, 1.12), STRUCT)
    else:
        for r, mat in ((0.26, STRUCT), (0.17, CRATE_ORANGE), (0.08, STRUCT)):
            b.soft.cyl((0.0, 0.0, 1.15), (0.012, 0.0, 1.15), r, mat, seg=18)
    b.emit.lamp_box((-0.02, -0.1, 1.78), (0.02, 0.1, 1.82), "green", LAMP)
    for sy in (-0.3, 0.3):
        b.soft.cyl((-0.02, sy, 0.55), (-0.02, sy, 1.75), 0.012, TRIM, seg=5)


def baffle_row(b: SParts, x0: float, x1: float, y0: float, y1: float, z_ceil: float, pitch: float = 3.0, tilt: float = 24.0) -> None:
    """Ceiling baffles over the downrange part of a range: steel plates tilted down towards +x, hung from the ceiling on rods, with an orange edge, one every `pitch` m."""
    n = int((x1 - x0) / pitch)
    w = y1 - y0
    for k in range(n):
        x = x0 + (k + 0.5) * pitch
        b.body.cbox((x, (y0 + y1) / 2, z_ceil - 0.42), (1.0, w, 0.07), CRATE_GREY, Ry(tilt))
        b.soft.cbox((x + 0.45, (y0 + y1) / 2, z_ceil - 0.62), (0.08, w, 0.09), CRATE_ORANGE, Ry(tilt))
        for yy in (y0 + 0.5, (y0 + y1) / 2, y1 - 0.5):
            b.soft.cyl((x - 0.35, yy, z_ceil), (x - 0.35, yy, z_ceil - 0.28), 0.015, TRIM, seg=5)


def bullet_trap(b: SParts, x_wall: float, y0: float, y1: float, z_ceil: float) -> None:
    """The back stop of a range, seen from the firing line: two armour plates sloped like a funnel into a dark slot, red slot lights, hazard bands on the floor; `x_wall` is
    the end wall's face, the trap reaches 2 m out of it."""
    xm = (y0 + y1) / 2
    b.body.extrude_y([(x_wall - 2.0, 0.0), (x_wall, 1.5), (x_wall, 1.62), (x_wall - 2.0, 0.12)], y0, y1, CRATE_GREY)
    b.body.extrude_y([(x_wall - 2.0, z_ceil), (x_wall, z_ceil - 1.5), (x_wall, z_ceil - 1.62), (x_wall - 2.0, z_ceil - 0.12)], y0, y1, CRATE_GREY)
    b.soft.box((x_wall - 0.2, y0, 1.62), (x_wall - 0.02, y1, z_ceil - 1.62), DGLASS)
    b.emit.lamp_box((x_wall - 0.25, y0 + 0.2, 1.64), (x_wall - 0.2, y1 - 0.2, 1.68), "red", LAMP_DIM)
    b.emit.lamp_box((x_wall - 0.25, y0 + 0.2, z_ceil - 1.68), (x_wall - 0.2, y1 - 0.2, z_ceil - 1.64), "red", LAMP_DIM)
    b.emit.label((x_wall - 2.3, xm, 0.006), y1 - y0 - 0.4, 0.3, (0, 0, 1), "hazard_h", up=(1, 0, 0))
