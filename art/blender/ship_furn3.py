"""ASN Aquila interior kit (ARTE-INTERNI): furniture, third generation — the gymnasium's equipment (treadmills, bikes, rowers, benches, racks, dumbbells, kettlebells, mats, ropes, a
boxing bag, wall bars), the wardroom's aquarium and ship model, and other things a film set has that a greybox lacks. Same conventions as ship_furn2.py: one piece per function in its own
frame (origin on the floor, x = the piece's front, y = its left, z up) into an `SParts`; rooms place it with ship_rooms.place(). Plates, mats and padding go in the `soft` group (no bevel,
smooth), steel and plastic in `body` / `fine`, lamps and screens in `emit`.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Rx, Ry, Rz, T
from ship_lib import (BRASS, COMPOSITE, LEAF_GREEN, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, LAMP, LAMP_DIM, LEATHER_NAVY, LEATHER_OX, OAK, PAINT_RED, RUBBER, STEEL, STRUCT, SWATCH, TRIM,
                      WALNUT, WHITE_GLOSS, SParts)

MAT_COLORS = ["teal", "navy", "rust", "mustard", "forest", "plum", "slate", "denim"]


# ------------------------------------------------------------------------------------------------------------------------------------------------------ cardio
def treadmill(b: SParts, seed: int = 1) -> None:
    """A treadmill facing +x (the runner stands on the belt, the console at +x): a deck on a steel frame with a rubber belt between two black side rails, rollers at both ends, two uprights
    carrying a tilted console with its screen and a safety key on a cord, handrails, a lit strip along the deck. Origin: the belt's middle on the floor."""
    b.body.box((-0.95, -0.34, 0.09), (0.78, 0.34, 0.2), STRUCT)
    MK.rbox(b.soft, (-0.92, -0.265, 0.2), (0.74, 0.265, 0.238), 0.012, RUBBER, 1)
    for y0, y1 in ((-0.335, -0.265), (0.265, 0.335)):                                                           # the side rails
        MK.rbox(b.soft, (-0.93, y0, 0.2), (0.75, y1, 0.27), 0.015, STRUCT, 1)
    for x in (-0.92, 0.74):
        b.fine.cyl((x, -0.3, 0.2), (x, 0.3, 0.2), 0.035, TRIM, seg=10)
    b.body.box((-0.98, -0.3, 0.0), (-0.78, 0.3, 0.09), STRUCT)                                                  # feet
    b.body.box((0.56, -0.3, 0.0), (0.78, 0.3, 0.09), STRUCT)
    for sy in (-0.33, 0.33):                                                                                     # the uprights and the handrails
        MK.rod(b.body, (0.62, sy, 0.2), (0.66, sy, 1.12), 0.028, 0.022, TRIM, 8)
        b.fine.cyl((0.66, sy, 1.12), (0.0, sy, 0.98), 0.019, STEEL, seg=8)
        b.soft.cyl((0.4, sy, 1.03), (0.08, sy, 0.99), 0.026, RUBBER, seg=8)
    MK.rbox(b.soft, (0.5, -0.32, 1.04), (0.74, 0.32, 1.2), 0.02, STRUCT, 2, rot=Ry(-28.0))                       # the console
    b.emit.label((0.495, 0.0, 1.12), 0.4, 0.17, (-0.85, 0.0, 0.53), "scr_data", up=(0.53, 0.0, 0.85))
    b.fine.cyl((0.5, 0.18, 1.08), (0.46, 0.18, 0.98), 0.004, STEEL, seg=5)                                      # the safety cord and its key
    b.fine.box((0.43, 0.15, 0.96), (0.47, 0.21, 0.99), PAINT_RED)
    b.emit.lamp_box((-0.9, -0.336, 0.15), (0.7, -0.332, 0.18), "cyan_dim", LAMP_DIM)
    b.emit.lamp_box((-0.9, 0.332, 0.15), (0.7, 0.336, 0.18), "cyan_dim", LAMP_DIM)


def exercise_bike(b: SParts, seed: int = 1) -> None:
    """A stationary bike facing +x: a flywheel housing, a frame, a padded saddle and handlebars on posts, pedals, a small screen. Origin on the floor under the middle of the frame."""
    b.body.box((-0.45, -0.26, 0.0), (-0.3, 0.26, 0.04), STRUCT)
    b.body.box((0.3, -0.26, 0.0), (0.45, 0.26, 0.04), STRUCT)
    b.body.cyl((0.0, -0.08, 0.34), (0.0, 0.08, 0.34), 0.29, COMPOSITE, seg=20)                                    # the flywheel's housing
    b.fine.cyl((0.0, -0.085, 0.34), (0.0, 0.085, 0.34), 0.07, STEEL, seg=12)
    MK.rod(b.body, (-0.38, 0.0, 0.04), (-0.3, 0.0, 0.5), 0.03, 0.03, TRIM, 8)                               # the frame: posts and a top tube
    MK.rod(b.body, (0.36, 0.0, 0.04), (0.28, 0.0, 0.8), 0.03, 0.03, TRIM, 8)
    MK.rod(b.body, (-0.3, 0.0, 0.5), (0.28, 0.0, 0.8), 0.028, 0.028, TRIM, 8)
    MK.rod(b.fine, (-0.3, 0.0, 0.5), (-0.34, 0.0, 0.92), 0.02, 0.02, STEEL, 8)
    MK.rbox(b.soft, (-0.46, -0.1, 0.92), (-0.2, 0.1, 0.99), 0.03, LEATHER_NAVY, 2)
    MK.rod(b.fine, (0.28, 0.0, 0.8), (0.3, 0.0, 1.1), 0.02, 0.02, STEEL, 8)
    b.fine.cyl((0.3, -0.22, 1.1), (0.3, 0.22, 1.1), 0.016, STEEL, seg=8)
    b.soft.cyl((0.3, -0.22, 1.1), (0.3, -0.12, 1.1), 0.022, RUBBER, seg=8)
    b.soft.cyl((0.3, 0.12, 1.1), (0.3, 0.22, 1.1), 0.022, RUBBER, seg=8)
    b.body.box((0.27, -0.09, 1.12), (0.37, 0.09, 1.22), STRUCT)
    b.emit.label((0.3695, 0.0, 1.17), 0.15, 0.08, (1.0, 0.0, 0.0), "scr_data")
    for sy in (-0.19, 0.19):                                                                                     # the pedals
        b.fine.box((0.1, sy - 0.05, 0.14), (0.24, sy + 0.05, 0.16), STRUCT)
        b.fine.cyl((0.0, sy * 0.9, 0.0), (0.17, sy, 0.15), 0.012, STEEL, seg=6)


def rower(b: SParts, seed: int = 1) -> None:
    """A rowing machine facing +x (the rower sits at -x facing the flywheel): a long monorail on two feet, a sliding seat, footplates with straps, a flywheel cage with a handle on its chain,
    a screen on an arm. Origin: the middle of the rail on the floor."""
    b.body.box((-1.05, -0.04, 0.2), (0.7, 0.04, 0.26), TRIM)
    for x in (-1.05, 0.5):
        b.body.box((x, -0.25, 0.0), (x + 0.12, 0.25, 0.05), STRUCT)
        b.body.box((x + 0.03, -0.03, 0.05), (x + 0.09, 0.03, 0.2), STRUCT)
    MK.rbox(b.soft, (-0.62, -0.16, 0.26), (-0.3, 0.16, 0.34), 0.03, LEATHER_NAVY, 2)
    b.fine.box((-0.64, -0.1, 0.2), (-0.28, 0.1, 0.26), STRUCT)
    b.body.cyl((0.62, -0.12, 0.42), (0.62, 0.12, 0.42), 0.28, COMPOSITE, seg=22)                                  # the flywheel's cage
    b.fine.cyl((0.62, -0.13, 0.42), (0.62, 0.13, 0.42), 0.05, STEEL, seg=10)
    for sy in (-0.12, 0.12):
        MK.rbox(b.soft, (0.3, sy - 0.07, 0.31), (0.5, sy + 0.07, 0.35), 0.01, STRUCT, 1, rot=Ry(-25.0))
    b.fine.cyl((0.5, 0.0, 0.36), (-0.15, 0.0, 0.42), 0.004, STEEL, seg=4)
    b.soft.cyl((-0.15, -0.18, 0.42), (-0.15, 0.18, 0.42), 0.015, RUBBER, seg=8)
    MK.rod(b.fine, (0.62, 0.0, 0.5), (0.64, 0.0, 0.85), 0.018, 0.018, STEEL, 8)
    b.body.box((0.56, -0.12, 0.85), (0.7, 0.12, 0.98), STRUCT)
    b.emit.label((0.6995, 0.0, 0.915), 0.18, 0.1, (1.0, 0.0, 0.0), "scr_data")


# ------------------------------------------------------------------------------------------------------------------------------------------------------ weights
def _plate(b: SParts, x: float, y: float, z: float, r: float, w: float = 0.04, mat: str = RUBBER) -> None:
    """A weight plate on a bar running along y: a disc with a bright ring on its face and a hub."""
    b.soft.cyl((x, y - w / 2, z), (x, y + w / 2, z), r, mat, seg=18)
    b.fine.cyl((x, y - w / 2 - 0.002, z), (x, y + w / 2 + 0.002, z), 0.03, STEEL, seg=10)


def barbell(b: SParts, plates=(0.22, 0.17), length: float = 2.2) -> None:
    """A barbell lying along y at the origin's height (origin at its middle): a steel bar with knurled grips, collars and plates of different sizes at both ends."""
    hl = length / 2
    b.fine.cyl((0, -hl, 0), (0, hl, 0), 0.0125, STEEL, seg=8)
    b.fine.cyl((0, -hl + 0.02, 0), (0, -hl + 0.42, 0), 0.0155, STRUCT, seg=8)
    b.fine.cyl((0, hl - 0.42, 0), (0, hl - 0.02, 0), 0.0155, STRUCT, seg=8)
    for sy in (-1, 1):
        y = sy * (hl - 0.1)
        for r in plates:
            _plate(b, 0.0, y, 0.0, r)
            y -= sy * 0.045
        b.fine.cyl((0, y, 0), (0, y + sy * 0.022, 0), 0.026, TRIM, seg=8)                                          # the collar


def bench_press(b: SParts, seed: int = 1) -> None:
    """A weight bench with its bar rack (the lifter lies on his back with the head at +x, under the bar): a padded flat bench, two uprights with J-hooks and safety arms, a loaded barbell
    on the hooks, a plate tree beside it with spare plates. Origin: the bench's middle on the floor."""
    MK.rbox(b.soft, (-0.6, -0.14, 0.4), (0.4, 0.14, 0.47), 0.03, LEATHER_NAVY, 2)
    b.body.box((-0.5, -0.05, 0.0), (0.3, 0.05, 0.4), STRUCT)
    b.body.box((-0.6, -0.25, 0.0), (-0.45, 0.25, 0.04), STRUCT)
    b.body.box((0.2, -0.3, 0.0), (0.38, 0.3, 0.04), STRUCT)
    for sy in (-0.42, 0.42):
        b.body.box((0.36, sy - 0.04, 0.0), (0.44, sy + 0.04, 1.3), STRUCT)
        b.body.box((0.3, sy - 0.1, 0.0), (0.5, sy + 0.1, 0.03), STRUCT)
        b.fine.box((0.28, sy - 0.02, 0.98), (0.4, sy + 0.02, 1.04), TRIM)                                       # the J-hooks
        b.fine.box((0.2, sy - 0.02, 0.38), (0.4, sy + 0.02, 0.42), TRIM)                                        # the safety arms
    with b.at(T(0.28, 0.0, 1.06)):
        barbell(b, (0.22, 0.17, 0.1))
    with b.at(T(0.9, 0.62, 0.0)):                                                                                # a plate tree
        b.body.cyl((0, 0, 0.0), (0, 0, 1.0), 0.03, TRIM, seg=8)
        b.body.cyl((0, 0, 0.0), (0, 0, 0.03), 0.22, STRUCT, seg=14)
        for k, r in enumerate((0.22, 0.2, 0.17, 0.15, 0.13)):
            b.soft.cyl((0.0, 0.0, 0.1 + k * 0.1), (0.0, 0.0, 0.1 + k * 0.1 + 0.04), r, RUBBER, seg=16)


def squat_rack(b: SParts, seed: int = 1) -> None:
    """A power rack facing +x, 1.3 m wide: four posts with numbered holes, two J-hooks and two safety bars across, a pull-up bar on top, plate pegs on the sides, a loaded barbell on the hooks.
    Origin: the middle of the floor inside it."""
    for sx in (-0.5, 0.5):
        for sy in (-0.65, 0.65):
            b.body.box((sx - 0.04, sy - 0.04, 0.0), (sx + 0.04, sy + 0.04, 2.2), STRUCT)
            b.fine.box((sx - 0.001, sy - 0.03, 0.4), (sx + 0.001, sy + 0.03, 1.9), TRIM)
        b.body.box((sx - 0.04, -0.65, 2.14), (sx + 0.04, 0.65, 2.2), STRUCT)
        b.body.box((sx - 0.05, -0.72, 0.0), (sx + 0.05, -0.58, 0.03), STRUCT)
        b.body.box((sx - 0.05, 0.58, 0.0), (sx + 0.05, 0.72, 0.03), STRUCT)
    for sy in (-0.65, 0.65):
        b.body.box((-0.5, sy - 0.04, 2.14), (0.5, sy + 0.04, 2.2), STRUCT)
        b.body.box((-0.5, sy - 0.04, 0.04), (0.5, sy + 0.04, 0.1), STRUCT)
    b.body.cyl((0.5, -0.65, 2.0), (0.5, 0.65, 2.0), 0.017, STEEL, seg=10)                                       # the pull-up bar
    for sy in (-0.65, 0.65):
        b.fine.box((0.35, sy - 0.03, 1.18), (0.58, sy + 0.03, 1.22), TRIM)                                       # J-hooks
        b.fine.box((0.35, sy - 0.03, 1.22), (0.58, sy + 0.03, 1.27), STEEL)
        b.fine.cyl((-0.55, sy * 1.0, 0.8), (-0.75, sy * 1.0, 0.8), 0.02, STEEL, seg=8)                         # plate pegs on the back
    for z in (0.5, 0.62):                                                                                         # safety bars
        b.fine.cyl((0.0, -0.68, z), (0.0, 0.68, z), 0.015, PAINT_RED, seg=8)
    with b.at(T(0.46, 0.0, 1.31)):
        barbell(b, (0.22, 0.2, 0.17))


def dumbbell_rack(b: SParts, pairs: int = 6, seed: int = 1) -> None:
    """A two-tier dumbbell rack facing +x, 2.0 m long: a steel frame with two sloped shelves, a row of rubber hex dumbbells on each, the weights painted on their ends. Origin on the floor at
    the middle of the rack."""
    rng = random.Random(seed)
    hl = 1.0
    for sy in (-hl + 0.05, 0.0, hl - 0.05):
        b.body.box((-0.22, sy - 0.025, 0.0), (-0.18, sy + 0.025, 0.95), STRUCT)
        b.body.box((0.18, sy - 0.025, 0.0), (0.22, sy + 0.025, 0.74), STRUCT)
        b.body.box((-0.22, sy - 0.05, 0.0), (0.22, sy + 0.05, 0.03), STRUCT)
    for z0 in (0.45, 0.8):                                                                                       # two shelves
        b.body.box((-0.18, -hl, z0), (0.2, hl, z0 + 0.03), STEEL)
    n = pairs
    for tier, z in enumerate((0.5, 0.84)):
        for k in range(n):
            y = -hl + 0.16 + k * (2 * hl - 0.32) / max(n - 1, 1)
            r = 0.055 + 0.003 * (k + tier * 3)
            xh = 0.0 if tier == 0 else -0.02
            for sx in (-0.11, 0.11):
                b.soft.cyl((xh + sx - 0.03, y, z + r * 0.9), (xh + sx + 0.03, y, z + r * 0.9), r, RUBBER, seg=6)
            b.fine.cyl((xh - 0.09, y, z + r * 0.9), (xh + 0.09, y, z + r * 0.9), 0.013, STEEL, seg=6)


def kettlebells(b: SParts, n: int = 6, seed: int = 1) -> None:
    """A row of kettlebells on a low rack along y (origin at its middle on the floor, front +x): cast-iron bells of growing size, each a round body with a handle, in painted colours."""
    b.body.box((-0.16, -n * 0.17, 0.0), (0.16, n * 0.17, 0.04), STRUCT)
    for k in range(n):
        y = -n * 0.17 + 0.17 + k * 0.34
        r = 0.08 + 0.012 * k
        col = ("rust", "navy", "forest", "mustard", "teal", "plum")[k % 6]
        b.soft.paint(MK.puff(b.soft, (0.0, y, 0.04 + r), (r, r, r), SWATCH, e=1.0, nu=10, nv=6), col)
        b.fine.cyl((0.0, y - r * 0.55, 0.04 + r * 1.7), (0.0, y + r * 0.55, 0.04 + r * 1.7), r * 0.14, STRUCT, seg=6)
        b.fine.cyl((0.0, y - r * 0.5, 0.04 + r * 1.2), (0.0, y - r * 0.55, 0.04 + r * 1.7), r * 0.14, STRUCT, seg=6)
        b.fine.cyl((0.0, y + r * 0.5, 0.04 + r * 1.2), (0.0, y + r * 0.55, 0.04 + r * 1.7), r * 0.14, STRUCT, seg=6)


def medicine_balls(b: SParts, n: int = 6, seed: int = 1) -> None:
    """A rack of medicine balls (origin at its middle on the floor, front +x): a steel stand with six cradles, a ball of each colour."""
    b.body.box((-0.2, -n * 0.2, 0.0), (0.2, n * 0.2, 0.03), STRUCT)
    b.body.box((-0.2, -n * 0.2, 0.3), (0.2, n * 0.2, 0.33), STEEL)
    for sy in (-n * 0.2, n * 0.2 - 0.03):
        b.body.box((-0.2, sy, 0.0), (0.2, sy + 0.03, 0.33), STRUCT)
    for k in range(n):
        y = -n * 0.2 + 0.2 + k * 0.4
        col = ("rust", "navy", "mustard", "teal", "plum", "forest")[k % 6]
        b.soft.paint(MK.puff(b.soft, (0.0, y, 0.33 + 0.12), (0.12, 0.12, 0.12), SWATCH, e=1.0, nu=12, nv=8), col)


def yoga_mat(b: SParts, seed: int = 1, rolled: bool = False) -> None:
    """A yoga mat lying along x (0.6 x 1.8 m, origin at its centre on the floor), or rolled up; with a foam roller or a block at its head on some."""
    rng = random.Random(seed)
    col = MAT_COLORS[seed % len(MAT_COLORS)]
    if rolled:
        b.soft.paint(MK.puff(b.soft, (0.0, 0.0, 0.08), (0.3, 0.08, 0.08), SWATCH, e=1.0, nu=10, nv=6), col)
        return
    b.soft.paint(MK.rbox(b.soft, (-0.9, -0.3, 0.0), (0.9, 0.3, 0.012), 0.004, SWATCH, 1), col)
    if seed % 3 == 0:
        b.soft.cyl((0.95, -0.15, 0.08), (0.95, 0.15, 0.08), 0.075, FABRIC_GREY, seg=10)
    elif seed % 3 == 1:
        b.soft.box((0.7, -0.1, 0.012), (0.82, 0.1, 0.1), FABRIC_SAND)


def plyo_boxes(b: SParts, seed: int = 1) -> None:
    """Three plyometric boxes of 0.5, 0.6 and 0.75 m side by side (origin at their middle on the floor, front +x): wood boxes with a black rubber top and handholds."""
    for k, (h, y) in enumerate(((0.5, -0.65), (0.6, 0.0), (0.75, 0.65))):
        MK.rbox(b.soft, (-0.3, y - 0.27, 0.0), (0.3, y + 0.27, h), 0.012, OAK, 1)
        b.soft.box((-0.3, y - 0.27, h), (0.3, y + 0.27, h + 0.012), RUBBER)
        b.fine.box((0.299, y - 0.09, h * 0.55), (0.304, y + 0.09, h * 0.55 + 0.05), STRUCT)


def heavy_bag(b: SParts, h_ceil: float = 3.4) -> None:
    """A boxing bag on a chain from the ceiling (origin on the floor under it): a leather cylinder with a taped seam and straps, rounded ends, a swivel and the chain up to the ceiling."""
    b.soft.cyl((0, 0, 0.58), (0, 0, 1.62), 0.17, LEATHER_OX, seg=16)
    b.soft.cyl((0, 0, 0.55), (0, 0, 0.58), 0.14, LEATHER_OX, seg=16, r2=0.17)
    b.soft.cyl((0, 0, 1.62), (0, 0, 1.66), 0.17, LEATHER_OX, seg=16, r2=0.1)
    for z in (0.8, 1.2, 1.55):
        b.soft.cyl((0, 0, z), (0, 0, z + 0.025), 0.1725, STRUCT, seg=16)
    b.fine.cyl((0, 0, 1.66), (0, 0, 1.78), 0.02, STEEL, seg=8)
    b.fine.cyl((0, 0, 1.78), (0, 0, h_ceil), 0.008, STEEL, seg=5)
    b.fine.cyl((0, 0, h_ceil - 0.05), (0, 0, h_ceil), 0.04, STRUCT, seg=10)


def wall_bars(b: SParts, w: float = 0.9, h: float = 2.6) -> None:
    """A Swedish ladder on the wall (origin: the middle of its back face on the floor, facing +x): two oak uprights with fourteen round rungs and a pull-up bar on top."""
    for sy in (-w / 2, w / 2 - 0.06):
        b.body.box((0.0, sy, 0.0), (0.09, sy + 0.06, h), OAK)
    n = 14
    for k in range(n):
        z = 0.2 + k * (h - 0.35) / (n - 1)
        b.fine.cyl((0.04, -w / 2 + 0.06, z), (0.04, w / 2 - 0.06, z), 0.016, OAK, seg=8)
    b.fine.cyl((0.12, -w / 2 - 0.04, h - 0.02), (0.12, w / 2 + 0.04, h - 0.02), 0.017, STEEL, seg=8)


def battle_ropes(b: SParts, seed: int = 1) -> None:
    """Two heavy ropes lying in loose waves along +x from an anchor post (origin at the post's base): a steel post with a ring, each rope a thick cord with a taped end."""
    rng = random.Random(seed)
    b.body.box((-0.05, -0.05, 0.0), (0.05, 0.05, 0.9), STRUCT)
    b.body.box((-0.2, -0.2, 0.0), (0.2, 0.2, 0.03), STRUCT)
    for sy in (-0.08, 0.08):
        pts = [(0.0, sy, 0.75)]
        for k in range(1, 14):
            pts.append((0.0 + 0.3 * k, sy + 0.22 * math.sin(k * 1.1 + sy * 9.0), 0.02 + 0.03 * (k % 2)))
        pts[1] = (0.15, sy, 0.3)
        b.soft.tube(pts, 0.025, FABRIC_NAVY if sy < 0 else FABRIC_RUST, seg=8)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the wardroom's things
def aquarium(b: SParts, w: float = 3.2, d: float = 0.8, h: float = 2.1, seed: int = 1, water: str = "cyan_dim") -> None:
    """A wall tank facing +x: a walnut base cabinet with doors and brass pulls, a brushed frame, the water — a glowing back panel in two shades of blue-green and glowing sides — a gravel
    bed with rocks, tall plants of real leaf geometry, a shoal of fish, a lamp hood on top with its tubes. Origin: the middle of the tank's back on the floor."""
    rng = random.Random(seed)
    hw = w / 2
    zb = 0.7
    MK.rbox(b.soft, (-d / 2, -hw, 0.06), (d / 2, hw, zb), 0.012, WALNUT, 1)
    b.body.box((-d / 2 + 0.03, -hw + 0.03, 0.0), (d / 2 - 0.03, hw - 0.03, 0.06), STRUCT)
    nd = max(2, int(w / 0.8))
    for k in range(nd):
        y0 = -hw + 0.03 + k * (w - 0.06) / nd
        y1 = -hw + 0.03 + (k + 1) * (w - 0.06) / nd
        b.fine.box((d / 2, y0 + 0.01, 0.1), (d / 2 + 0.014, y1 - 0.01, zb - 0.04), OAK)
        b.fine.box((d / 2 + 0.014, (y0 + y1) / 2 - 0.01 + (0.15 if k % 2 else -0.15), 0.36), (d / 2 + 0.03, (y0 + y1) / 2 + 0.01 + (0.15 if k % 2 else -0.15), 0.56), BRASS)
    b.body.box((-d / 2 - 0.02, -hw - 0.02, zb), (d / 2 + 0.02, hw + 0.02, zb + 0.06), STEEL)
    for sy in (-hw, hw - 0.06):                                                                                  # the frame
        b.body.box((-d / 2, sy, zb + 0.06), (d / 2, sy + 0.06, h - 0.2), TRIM)
    b.body.box((-d / 2, -hw, h - 0.2), (d / 2, hw, h), STRUCT)                                                  # the hood
    b.emit.lamp_box((-d / 2 + 0.04, -hw + 0.06, zb + 0.08), (-d / 2 + 0.05, hw - 0.06, h - 0.22), "cyan_dim", LAMP_DIM)                    # the glowing back, two shades
    b.emit.lamp_box((-d / 2 + 0.04, -hw + 0.06, zb + 0.08), (-d / 2 + 0.052, hw - 0.06, zb + 0.6), "medical_dim", LAMP_DIM)
    for sy in (-hw + 0.06, hw - 0.062):
        b.emit.lamp_box((-d / 2 + 0.05, sy, zb + 0.08), (d / 2 - 0.06, sy + 0.002, h - 0.22), "cyan_dim", LAMP_DIM)
    b.emit.lamp_box((-d / 2 + 0.08, -hw + 0.1, h - 0.22), (d / 2 - 0.1, hw - 0.1, h - 0.2), "white_cool", LAMP)           # the lamp tubes under the hood
    b.soft.paint(MK.rbox(b.soft, (-d / 2 + 0.05, -hw + 0.06, zb + 0.06), (d / 2 - 0.08, hw - 0.06, zb + 0.15), 0.03, SWATCH, 1), "sand")                  # the gravel
    for k in range(5):                                                                                           # rocks
        y = rng.uniform(-hw + 0.3, hw - 0.3)
        r = rng.uniform(0.08, 0.16)
        b.soft.paint(MK.puff(b.soft, (rng.uniform(-0.1, 0.1), y, zb + 0.14), (r, r * 0.8, r * 0.6), SWATCH, e=0.8, nu=8, nv=5), rng.choice(("grey3", "grey5", "slate", "charcoal")))
    for k in range(int(w / 0.34)):                                                                               # kelp and reeds
        y = -hw + 0.2 + k * (w - 0.4) / max(int(w / 0.34) - 1, 1) + rng.uniform(-0.05, 0.05)
        for j in range(rng.randint(2, 3)):
            a = rng.uniform(0, 6.28)
            hh = rng.uniform(0.6, 1.1)
            MK.leaf(b.soft, (rng.uniform(-0.15, 0.05), y + rng.uniform(-0.05, 0.05), zb + 0.14), (math.cos(a) * 0.2, math.sin(a) * 0.2, 1.0), (math.cos(a + 1.57), math.sin(a + 1.57), 0), hh,
                    rng.uniform(0.05, 0.09), LEAF_GREEN, tile=2, droop=0.35, fold=0.1, nu=4, nv=1, shape=0.55, seed=k * 7 + j)
    cols = ("orange", "yellow", "cyan", "red", "mustard", "blue")
    for k in range(10):                                                                                          # a shoal: a body, a tail and a fin each, all facing the same way (mostly)
        y = rng.uniform(-hw + 0.25, hw - 0.25)
        z = rng.uniform(zb + 0.4, h - 0.45)
        x = rng.uniform(-d / 2 + 0.15, d / 2 - 0.2)
        s = rng.uniform(0.7, 1.3)
        dirn = 1 if k % 4 else -1
        col = cols[k % len(cols)]
        with b.at(T(x, y, z) @ Rz(90.0 * dirn + rng.uniform(-15, 15))):
            b.soft.paint(MK.puff(b.soft, (0.0, 0.0, 0.0), (0.045 * s, 0.014 * s, 0.022 * s), SWATCH, e=0.8, nu=8, nv=5), col)
            b.soft.swatch_box((-0.002, -0.07 * s, -0.025 * s), (0.002, -0.04 * s, 0.025 * s), col)
    b.emit.label((d / 2 + 0.032, 0.0, 0.2), 0.5, 0.125, (1, 0, 0), "eq_water")


def ship_model(b: SParts, l: float = 0.9, seed: int = 1) -> None:
    """A model of the ship on a brass stand (origin: the middle of its plinth on the table, bow towards +x): a walnut plinth with a brass plate, two brass struts, a long hull of lofted
    sections — a blunt bow, a slim waist, a broad stern with two engine pods and a dorsal fin — in pale grey with a dark belly, small lamps at the engines."""
    b.fine.box((-l * 0.5, -0.1, 0.0), (l * 0.5, 0.1, 0.03), WALNUT)
    b.fine.box((-0.07, 0.1, 0.004), (0.07, 0.102, 0.022), BRASS)
    for x in (-l * 0.22, l * 0.2):
        b.fine.cyl((x, 0.0, 0.03), (x, 0.0, 0.16), 0.006, BRASS, seg=6)
    rings = []
    n = 14
    for k in range(n + 1):
        t = k / n
        x = -l * 0.5 + l * t
        body = math.sin(math.pi * min(1.0, t * 1.15)) ** 0.5 if t < 0.87 else max(0.0, 1.0 - (t - 0.87) / 0.13) * 0.8
        ry = 0.012 + 0.052 * body * (0.55 + 0.45 * math.sin(math.pi * t) ** 0.3)
        rz = 0.008 + 0.036 * body
        rings.append([(x, ry * math.cos(a), 0.17 + rz * math.sin(a)) for a in [2 * math.pi * i / 14 for i in range(14)]])
    MK.stack(b.fine, rings, WHITE_GLOSS)
    b.fine.box((-l * 0.12, -0.003, 0.17 + 0.03), (l * 0.1, 0.003, 0.17 + 0.075), WHITE_GLOSS)                  # the dorsal fin
    for sy in (-0.055, 0.055):                                                                                   # engine pods
        b.fine.cyl((-l * 0.5, sy, 0.17), (-l * 0.18, sy, 0.17), 0.016, STRUCT, seg=8, r2=0.012)
        b.emit.lamp_cyl((-l * 0.5 - 0.004, sy, 0.17), (-l * 0.5, sy, 0.17), 0.012, "cyan", LAMP_DIM, seg=8)
    b.emit.lamp_box((l * 0.42, -0.003, 0.17 + 0.0), (l * 0.44, 0.003, 0.17 + 0.01), "white_warm", LAMP_DIM)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ floors and rings
def lifting_platform(b: SParts, w: float = 2.8, d: float = 2.8) -> None:
    """A lifting platform (origin at its middle): a black rubber slab 2 cm thick with an oak inlay in the middle where the bar is dropped and a thin lit line round it."""
    b.soft.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.02), RUBBER)
    b.soft.swatch_box((-w / 2 + 0.4, -d / 2 + 0.4, 0.02), (w / 2 - 0.4, d / 2 - 0.4, 0.026), "w_oak")
    b.emit.lamp_box((-w / 2 + 0.38, -d / 2 + 0.38, 0.02), (w / 2 - 0.38, -d / 2 + 0.4, 0.0225), "amber_dim", LAMP_DIM)
    b.emit.lamp_box((-w / 2 + 0.38, d / 2 - 0.4, 0.02), (w / 2 - 0.38, d / 2 - 0.38, 0.0225), "amber_dim", LAMP_DIM)


def boxing_ring(b: SParts, s: float = 4.6) -> None:
    """A boxing ring (origin at its middle on the floor): a platform 0.9 m high with a navy apron and a canvas, four corner posts in padded covers, three ropes a side in red, white and
    blue, a flight of three steps at the corner (-x, -y)."""
    h = 0.9
    hs = s / 2
    b.body.box((-hs - 0.3, -hs - 0.3, 0.0), (hs + 0.3, hs + 0.3, h - 0.06), STRUCT)
    b.soft.swatch_box((-hs - 0.32, -hs - 0.32, h - 0.3), (hs + 0.32, hs + 0.32, h - 0.06), "navy")                         # the apron
    b.soft.box((-hs - 0.3, -hs - 0.3, h - 0.06), (hs + 0.3, hs + 0.3, h), FABRIC_SAND)                                    # the canvas
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (hs - 0.05), sy * (hs - 0.05)
            b.body.cyl((x, y, h), (x, y, h + 1.5), 0.05, STEEL, seg=10)
            b.soft.swatch_box((x - 0.07, y - 0.07, h + 0.35), (x + 0.07, y + 0.07, h + 1.25), "red" if sx + sy > 0 else "blue")
    for z, col in ((0.45, "red"), (0.8, "white"), (1.15, "blue")):
        for sx, sy, tx, ty in ((-1, -1, 1, -1), (1, -1, 1, 1), (1, 1, -1, 1), (-1, 1, -1, -1)):
            p0 = (sx * (hs - 0.05), sy * (hs - 0.05), h + z)
            p1 = (tx * (hs - 0.05), ty * (hs - 0.05), h + z)
            b.soft.paint(b.soft.tube([p0, ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, h + z - 0.03), p1], 0.022, SWATCH, seg=6), col)
    for k in range(3):                                                                                           # the steps: each one taller and further in
        x1 = -hs - 0.3 - 0.28 * k
        b.body.box((x1 - 0.28, -hs - 0.3, 0.0), (x1, -hs + 0.5, 0.28 * (3 - k) - 0.02), STRUCT)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the chapel
def pew(b: SParts, w: float = 2.6) -> None:
    """A chapel pew facing +x (the congregation sits looking towards +x), w along y: two walnut cheeks with a high back and a lower front, a seat plank with a slim navy pad, a back plank
    leaning a little, a rail along the top, a shelf with hymn books on the back for the row behind and a padded kneeler on a frame at the foot."""
    for sy in (-w / 2, w / 2 - 0.05):
        MK.rbox(b.soft, (-0.34, sy, 0.0), (-0.18, sy + 0.05, 1.0), 0.012, WALNUT, 1)                              # the cheek's tall back
        MK.rbox(b.soft, (-0.34, sy, 0.0), (0.3, sy + 0.05, 0.5), 0.012, WALNUT, 1)                                # and its lower front
    MK.rbox(b.soft, (-0.26, -w / 2 + 0.05, 0.42), (0.26, w / 2 - 0.05, 0.47), 0.008, WALNUT, 1)                    # the seat
    b.soft.box((-0.2, -w / 2 + 0.08, 0.47), (0.22, w / 2 - 0.08, 0.5), FABRIC_NAVY)                               # its pad
    MK.rbox(b.soft, (-0.33, -w / 2 + 0.05, 0.47), (-0.28, w / 2 - 0.05, 0.92), 0.008, WALNUT, 1, rot=Ry(-8.0))   # the back
    MK.rbox(b.soft, (-0.35, -w / 2, 0.92), (-0.25, w / 2, 0.99), 0.02, WALNUT, 1)                                 # the rail on top
    b.fine.box((-0.43, -w / 2 + 0.1, 0.68), (-0.34, w / 2 - 0.1, 0.7), WALNUT)                                    # the shelf behind
    n = int((w - 0.2) / 0.11)
    for k in range(n):
        b.soft.swatch_box((-0.42, -w / 2 + 0.1 + k * 0.105, 0.7), (-0.35, -w / 2 + 0.1 + k * 0.105 + 0.085, 0.7 + 0.15 + 0.01 * (k % 3)), ("navy", "oxblood", "forest")[k % 3])
    MK.rbox(b.soft, (-0.62, -w / 2 + 0.2, 0.0), (-0.52, w / 2 - 0.2, 0.12), 0.015, FABRIC_NAVY, 1)                 # the kneeler for the row behind


def altar(b: SParts) -> None:
    """An altar facing +x: a block of pale stone with a plinth, a white cloth runner, two tall brass candlesticks with a lit candle each, a brass bowl between them and an open book on a stand."""
    b.body.box((-0.36, -0.86, 0.0), (0.36, 0.86, 0.06), STRUCT)
    MK.rbox(b.soft, (-0.4, -0.9, 0.06), (0.4, 0.9, 0.9), 0.015, WHITE_GLOSS, 1)
    b.body.box((-0.44, -0.94, 0.9), (0.44, 0.94, 0.95), STRUCT)
    b.soft.box((-0.3, -0.72, 0.95), (0.3, 0.72, 0.962), FABRIC_SAND)
    b.soft.box((0.4, -0.72, 0.62), (0.44, 0.72, 0.95), FABRIC_SAND)                                                 # the cloth hanging over the front
    for sy in (-0.55, 0.55):
        MK.lathe(b.fine, [(0.001, 0.962), (0.05, 0.965), (0.05, 0.98), (0.014, 1.0), (0.014, 1.2), (0.03, 1.22), (0.03, 1.25)], (0.0, sy, 0.0), BRASS, seg=12)
        b.fine.cyl((0.0, sy, 1.25), (0.0, sy, 1.43), 0.02, WHITE_GLOSS, seg=8)
        b.emit.lamp_cyl((0.0, sy, 1.43), (0.0, sy, 1.47), 0.009, "amber", LAMP, seg=6, r2=0.002)
    MK.lathe(b.fine, [(0.001, 0.962), (0.07, 0.97), (0.11, 1.03), (0.12, 1.06), (0.1, 1.06), (0.001, 1.0)], (0.0, 0.0, 0.0), BRASS, seg=16)
    MK.rbox(b.soft, (-0.12, 0.2, 0.962), (0.08, 0.5, 0.99), 0.01, WALNUT, 1, rot=Ry(-12.0))
    b.soft.swatch_box((-0.1, 0.22, 0.99), (0.06, 0.48, 1.0), "paper")


def lectern(b: SParts) -> None:
    """A lectern facing +x: a walnut column on a base with a sloped top and a lip, a reading lamp on a gooseneck, an open book."""
    b.body.box((-0.22, -0.25, 0.0), (0.22, 0.25, 0.05), STRUCT)
    MK.rbox(b.soft, (-0.14, -0.14, 0.05), (0.14, 0.14, 1.0), 0.01, WALNUT, 1)
    MK.rbox(b.soft, (-0.28, -0.32, 1.0), (0.26, 0.32, 1.06), 0.015, WALNUT, 1, rot=Ry(-18.0))
    b.soft.swatch_box((-0.18, -0.22, 1.062), (0.12, 0.22, 1.072), "paper")
    b.fine.cyl((-0.2, 0.28, 1.06), (-0.22, 0.28, 1.28), 0.006, BRASS, seg=6)
    b.emit.lamp_cyl((-0.22, 0.28, 1.27), (-0.12, 0.22, 1.22), 0.02, "white_warm", LAMP, seg=10, r2=0.045)


def candle_stand(b: SParts, seed: int = 1) -> None:
    """A floor candelabra (origin on the floor): a heavy brass foot, a column, three arms with a candle each, the flames small lamps."""
    MK.lathe(b.fine, [(0.001, 0.0), (0.16, 0.0), (0.16, 0.03), (0.07, 0.07), (0.03, 0.14), (0.02, 0.3), (0.035, 0.34), (0.02, 0.4), (0.02, 1.15)], (0, 0, 0), BRASS, seg=14)
    for sy, z in ((-0.22, 1.1), (0.0, 1.22), (0.22, 1.1)):
        b.fine.cyl((0.0, 0.0, 1.05), (0.0, sy, z - 0.05), 0.009, BRASS, seg=6)
        b.fine.cyl((0.0, sy, z - 0.05), (0.0, sy, z), 0.025, BRASS, seg=8)
        b.fine.cyl((0.0, sy, z), (0.0, sy, z + 0.17), 0.018, WHITE_GLOSS, seg=8)
        b.emit.lamp_cyl((0.0, sy, z + 0.17), (0.0, sy, z + 0.21), 0.008, "amber", LAMP, seg=6, r2=0.002)


def mosaic_window(b: SParts, w: float = 2.4, h: float = 3.0, seed: int = 1) -> None:
    """A stained-glass window of coloured light on a wall (origin: the middle of its back face, facing +x): a dark frame with its leads and, in every cell of a grid, a pane of one of the
    ship's colours — the colour set by the angle and the distance from the middle, so that the whole is a rosette of many faiths. A tenth of the cells are warm white."""
    t = 0.07
    b.body.box((0.0, -w / 2, -h / 2), (0.08, w / 2, -h / 2 + t), WALNUT)
    b.body.box((0.0, -w / 2, h / 2 - t), (0.08, w / 2, h / 2), WALNUT)
    b.body.box((0.0, -w / 2, -h / 2 + t), (0.08, -w / 2 + t, h / 2 - t), WALNUT)
    b.body.box((0.0, w / 2 - t, -h / 2 + t), (0.08, w / 2, h / 2 - t), WALNUT)
    b.soft.box((0.0, -w / 2 + t, -h / 2 + t), (0.02, w / 2 - t, h / 2 - t), STRUCT)
    cells = ("command", "medical", "science", "engineering", "flight", "security", "green", "white_warm")
    nx, nz = int(round(w / 0.2)), int(round(h / 0.2))
    cw, ch = (w - 2 * t) / nx, (h - 2 * t) / nz
    rng = random.Random(seed)
    for i in range(nx):
        for j in range(nz):
            u = (i + 0.5) / nx * 2 - 1
            v = (j + 0.5) / nz * 2 - 1
            r = math.hypot(u, v * 0.8)
            a = math.atan2(v, u)
            k = (int((a + math.pi) / (2 * math.pi) * 8) + int(r * 3.2)) % len(cells)
            cell = "white_warm" if rng.random() < 0.1 else cells[k]
            y0 = -w / 2 + t + i * cw
            z0 = -h / 2 + t + j * ch
            b.emit.lamp_box((0.02, y0 + 0.012, z0 + 0.012), (0.03, y0 + cw - 0.012, z0 + ch - 0.012), cell, LAMP_DIM)
