"""ASN Aquila interior kit: furniture and equipment of the social, work and berthing rooms (second library; the first is ship_furniture.py).

Same conventions: every function builds one piece in ITS OWN frame (origin on the floor, +x its front, +y its left, z up) into a `SParts`
(body = bevelled hard-surface, fine = small details, soft = cloth, emit = lamps and labels); rooms place it with ship_rooms.place().
"""
from __future__ import annotations

import math
import random

from bridge3_lib import T, frame
import ship_furniture as F
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, DECK, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, LEATHER, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM,
                      WOOD, SParts)


# ---------------------------------------------------------------------------------------------------------------- recreation
def billiard_table(b: SParts, l: float = 2.7, w: float = 1.5, h: float = 0.84) -> None:
    """A billiard table, its long side along x: cloth, wooden rails, six pockets, a triangle of balls."""
    hx, hy = l / 2, w / 2
    b.body.box((-hx + 0.08, -hy + 0.08, h - 0.05), (hx - 0.08, hy - 0.08, h - 0.02), LEAF)
    for a, c in (((-hx, -hy), (hx, -hy + 0.09)), ((-hx, hy - 0.09), (hx, hy)), ((-hx, -hy + 0.09), (-hx + 0.09, hy - 0.09)),
                 ((hx - 0.09, -hy + 0.09), (hx, hy - 0.09))):
        b.body.box((a[0], a[1], h - 0.06), (c[0], c[1], h + 0.05), WOOD)
    b.body.box((-hx + 0.04, -hy + 0.04, h - 0.26), (hx - 0.04, hy - 0.04, h - 0.06), WOOD)
    for sx in (-hx + 0.24, hx - 0.24):
        for sy in (-hy + 0.2, hy - 0.2):
            b.body.box((sx - 0.08, sy - 0.08, 0.0), (sx + 0.08, sy + 0.08, h - 0.26), WOOD)
            b.fine.box((sx - 0.1, sy - 0.1, 0.0), (sx + 0.1, sy + 0.1, 0.03), TRIM)
    for px, py in ((-hx + 0.05, -hy + 0.05), (-hx + 0.05, hy - 0.05), (hx - 0.05, -hy + 0.05), (hx - 0.05, hy - 0.05), (0, -hy + 0.045), (0, hy - 0.045)):
        b.fine.cyl((px, py, h - 0.045), (px, py, h + 0.052), 0.048, DGLASS, seg=10)
    cols = [PAINT_RED, CRATE_BLUE, CRATE_ORANGE, BEDDING, FABRIC_RUST, CRATE_OLIVE]
    k = 0
    for row in range(4):
        for i in range(row + 1):
            b.fine.sphere((0.55 + row * 0.052, (i - row / 2) * 0.058, h - 0.02 + 0.028), 0.028, cols[k % len(cols)], seg=8, rings=6)
            k += 1
    b.fine.sphere((-0.55, 0.0, h - 0.02 + 0.028), 0.028, BEDDING, seg=8, rings=6)


def pendant_bar(b: SParts, l: float, w: float, z_bar: float, z_ceil: float, cell: str = "white_warm", mat: str = LAMP) -> None:
    """A lamp bar hanging from the ceiling on two wires, centred on the origin (x along l)."""
    b.body.box((-l / 2, -w / 2, z_bar), (l / 2, w / 2, z_bar + 0.06), TRIM)
    b.emit.lamp_box((-l / 2 + 0.04, -w / 2 + 0.03, z_bar - 0.006), (l / 2 - 0.04, w / 2 - 0.03, z_bar), cell, mat)
    for sx in (-l / 2 + 0.15, l / 2 - 0.15):
        b.fine.cyl((sx, 0, z_bar + 0.06), (sx, 0, z_ceil), 0.006, TRIM, seg=6)


def arcade_cabinet(b: SParts, screen: str = "scr_map", accent: str = "violet") -> None:
    """An upright arcade cabinet facing +x: a side profile extruded, a screen, a control ledge with buttons, a lit marquee."""
    prof = [(-0.40, 0.0), (0.30, 0.0), (0.30, 0.92), (0.47, 0.98), (0.47, 1.06), (0.30, 1.10), (0.30, 1.86), (-0.40, 1.86)]
    b.body.extrude_y(prof, -0.36, 0.36, COMPOSITE)
    b.fine.box((0.302, -0.34, 0.06), (0.31, 0.34, 0.90), STRUCT)
    b.fine.box((0.302, -0.30, 1.16), (0.315, 0.30, 1.68), DGLASS)
    b.emit.label((0.316, 0.0, 1.42), 0.58, 0.48, (1, 0, 0), screen)
    b.emit.lamp_box((0.302, -0.30, 1.72), (0.32, 0.30, 1.83), accent, LAMP)
    for k, cell in enumerate(("red", "green", "amber", "cyan")):
        b.fine.cyl((0.40, -0.16 + k * 0.105, 1.02), (0.40, -0.16 + k * 0.105, 1.045), 0.022, TRIM, seg=8)
        b.emit.lamp_cyl((0.40, -0.16 + k * 0.105, 1.045), (0.40, -0.16 + k * 0.105, 1.058), 0.017, cell, LAMP_DIM, seg=8)
    b.fine.cyl((0.40, 0.24, 1.02), (0.40, 0.24, 1.14), 0.011, TRIM, seg=8)
    b.fine.sphere((0.40, 0.24, 1.16), 0.028, PAINT_RED, seg=8, rings=6)


def bar_stool(b: SParts, h: float = 0.72, mat: str = FABRIC_RUST) -> None:
    b.body.cyl((0, 0, 0.0), (0, 0, 0.03), 0.20, STRUCT, seg=14)
    b.body.cyl((0, 0, 0.03), (0, 0, h - 0.07), 0.028, TRIM, seg=8)
    b.fine.cyl((0, 0, 0.26), (0, 0, 0.28), 0.17, TRIM, seg=14)          # foot ring
    b.soft.cyl((0, 0, h - 0.07), (0, 0, h), 0.19, mat, seg=18)


def bar_counter(b: SParts, w: float = 6.0, d: float = 0.7, h: float = 1.08) -> None:
    """A snack bar facing +x: a dark body, a wooden top that overhangs the customer side, a foot rail, a lit under-edge."""
    b.body.box((-d / 2, -w / 2, 0.08), (d / 2 - 0.06, w / 2, h - 0.05), COMPOSITE)
    b.body.box((-d / 2 - 0.05, -w / 2 - 0.03, h - 0.05), (d / 2 + 0.28, w / 2 + 0.03, h), WOOD)
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2 - 0.10, w / 2, 0.08), STRUCT)
    n = max(1, int(w / 0.9))
    for k in range(n + 1):
        y = -w / 2 + k * w / n
        b.fine.box((d / 2 - 0.06, y - 0.01, 0.10), (d / 2 - 0.045, y + 0.01, h - 0.08), TRIM)
    b.fine.cyl((d / 2 + 0.16, -w / 2 + 0.1, 0.24), (d / 2 + 0.16, w / 2 - 0.1, 0.24), 0.021, TRIM, seg=8)
    for y in (-w / 2 + 0.1, w / 2 - 0.1):
        b.fine.cyl((d / 2 + 0.16, y, 0.0), (d / 2 + 0.16, y, 0.24), 0.014, TRIM, seg=6)
    b.emit.lamp_box((d / 2 + 0.05, -w / 2 + 0.05, h - 0.09), (d / 2 + 0.056, w / 2 - 0.05, h - 0.075), "warm_dim", LAMP_DIM)


def coffee_machine(b: SParts) -> None:
    b.body.box((-0.24, -0.34, 0.0), (0.24, 0.34, 0.62), STEEL)
    b.fine.box((0.24, -0.30, 0.34), (0.26, 0.30, 0.58), STRUCT)
    b.fine.box((0.26, -0.26, 0.40), (0.275, -0.02, 0.54), DGLASS)
    b.emit.lamp_box((0.26, 0.04, 0.50), (0.275, 0.22, 0.53), "amber", LAMP_DIM)
    for y in (-0.15, 0.15):
        b.fine.cyl((0.20, y, 0.34), (0.20, y, 0.30), 0.012, TRIM, seg=6)
        b.fine.cyl((0.20, y, 0.30), (0.20, y, 0.10), 0.008, TRIM, seg=6)
    b.fine.box((0.10, -0.2, 0.0), (0.26, 0.2, 0.06), STRUCT)
    for y in (-0.15, 0.15):
        b.fine.cyl((0.20, y, 0.06), (0.20, y, 0.14), 0.035, BEDDING, seg=10)


def back_bar(b: SParts, w: float = 5.0, h: float = 2.1, d: float = 0.34, seed: int = 4) -> None:
    """The shelves behind a bar (facing +x): three glass shelves of bottles and mugs, a back panel that glows warm."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.03, w / 2, h), STRUCT)
    b.emit.lamp_box((-d / 2 + 0.03, -w / 2 + 0.1, 0.9), (-d / 2 + 0.036, w / 2 - 0.1, h - 0.1), "warm_dim", LAMP_DIM)
    for z in (0.95, 1.45, 1.95):
        b.body.box((-d / 2, -w / 2, z), (d / 2 - 0.04, w / 2, z + 0.025), WOOD)
        y = -w / 2 + 0.12
        while y < w / 2 - 0.12:
            r = rng.uniform(0.03, 0.05)
            hh = rng.uniform(0.16, 0.30)
            mat = rng.choice([GLASS, DGLASS, CRATE_ORANGE, CRATE_OLIVE, BEDDING, FABRIC_RUST])
            mat = DGLASS if mat == GLASS else mat
            b.fine.cyl((0.0, y, z + 0.025), (0.0, y, z + 0.025 + hh), r, mat, seg=8, r2=r * 0.7)
            y += r * 2 + rng.uniform(0.02, 0.12)
    for sy in (-w / 2, w / 2 - 0.04):
        b.body.box((-d / 2, sy, 0.0), (d / 2 - 0.04, sy + 0.04, h), WOOD)
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2 - 0.04, w / 2, 0.9), COMPOSITE)


def ring_lamp(b: SParts, r: float = 0.8, seg: int = 28, cell: str = "amber", w: float = 0.05, mat: str = LAMP) -> None:
    """A luminous ring standing on the +x facing wall (the ring lies in the yz plane, its centre at the origin height)."""
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        p0 = (0.0, r * math.cos(a0), r * math.sin(a0))
        p1 = (0.0, r * math.cos(a1), r * math.sin(a1))
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2)
        ln = math.dist(p0, p1) * 1.02
        ang = math.degrees(math.atan2(p1[2] - p0[2], p1[1] - p0[1]))
        from bridge3_lib import Rx
        b.emit.lamp_cbox(mid, (0.02, ln, w), cell, mat, Rx(ang))


def candle(b: SParts, h: float = 0.14) -> None:
    b.fine.cyl((0, 0, 0.0), (0, 0, h), 0.018, BEDDING, seg=8)
    b.emit.lamp_cyl((0, 0, h), (0, 0, h + 0.03), 0.008, "amber", LAMP, seg=6, r2=0.003)


def telescope(b: SParts) -> None:
    """A standing telescope facing +x (looks out and up a little): tripod, mount, tube with a lens."""
    for k in range(3):
        a = math.radians(90 + 120 * k)
        b.fine.cyl((0.0, 0.0, 1.05), (0.42 * math.cos(a) * 0.9, 0.42 * math.sin(a) * 0.9, 0.0), 0.016, TRIM, seg=6)
    b.body.cyl((0, 0, 1.02), (0, 0, 1.18), 0.045, STRUCT, seg=10)
    from mathutils import Vector
    a0, a1 = Vector((-0.2, 0.0, 1.30)), Vector((0.62, 0.0, 1.50))
    b.body.cyl(a0, a1, 0.055, STEEL, seg=12, r2=0.075)
    b.fine.cyl(a1, a1 + Vector((0.02, 0.0, 0.005)), 0.08, TRIM, seg=12)
    b.fine.cyl(a0 + (a1 - a0) * 0.35 + Vector((0, 0, 0.06)), a0 + (a1 - a0) * 0.35 + Vector((0.02, 0, 0.16)), 0.014, TRIM, seg=6)
    b.emit.lamp_box((-0.24, -0.02, 1.27), (-0.2, 0.02, 1.31), "cyan", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------- berthing
def bunk_bed(b: SParts, l: float = 2.05, w: float = 0.95, levels: int = 2, blanket: str = FABRIC_NAVY, seed: int = 1) -> None:
    """A bunk bed with its head at -x: posts, frames, mattresses, sheets, a blanket, pillows, a ladder on the +y side, a reading lamp per bunk."""
    rng = random.Random(seed)
    hl, hw = l / 2, w / 2
    zs = [0.34, 1.30][:levels] if levels == 2 else [0.40]
    top = 1.86 if levels == 2 else 1.0
    for sx in (-hl, hl - 0.06):
        for sy in (-hw, hw - 0.06):
            b.body.box((sx, sy, 0.0), (sx + 0.06, sy + 0.06, top), TRIM)
    for z in zs:
        b.body.box((-hl, -hw, z - 0.06), (hl, hw, z), COMPOSITE)
        b.soft.box((-hl + 0.04, -hw + 0.04, z), (hl - 0.04, hw - 0.04, z + 0.14), BEDDING)
        b.soft.box((-hl + 0.62, -hw + 0.03, z + 0.14), (hl - 0.03, hw - 0.03, z + 0.20), blanket)
        b.soft.box((-hl + 0.06, -hw + 0.12, z + 0.14), (-hl + 0.42, hw - 0.12, z + 0.24), BEDDING)
        b.emit.lamp_box((-hl + 0.07, hw - 0.30, z + 0.62), (-hl + 0.10, hw - 0.20, z + 0.66), "warm_dim" if rng.random() > 0.3 else "white_warm", LAMP_DIM)
        b.fine.box((-hl + 0.06, hw - 0.05, z + 0.55), (-hl + 0.12, hw - 0.02, z + 0.7), TRIM)
    if levels == 2:
        b.body.box((-hl + 0.1, -hw - 0.0, 1.30 + 0.14), (hl - 0.1, -hw + 0.02, 1.30 + 0.42), TRIM)          # guard rail (open side is +y: the ladder)
        for k in range(5):
            z = 0.28 + k * 0.28
            b.fine.box((hl - 0.45, hw - 0.02, z), (hl - 0.20, hw + 0.03, z + 0.03), TRIM)
        b.fine.box((hl - 0.47, hw - 0.02, 0.2), (hl - 0.43, hw + 0.03, 1.5), TRIM)
        b.fine.box((hl - 0.22, hw - 0.02, 0.2), (hl - 0.18, hw + 0.03, 1.5), TRIM)


def wardrobe(b: SParts, w: float = 0.9, d: float = 0.55, h: float = 2.0, mat: str = COMPOSITE) -> None:
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), mat)
    for sy in (-w / 2, 0.0):
        b.fine.box((d / 2, sy + 0.012, 0.06), (d / 2 + 0.012, sy + w / 2 - 0.012, h - 0.06), IVORY)
        b.fine.box((d / 2 + 0.012, sy + w / 2 - 0.07, h * 0.5 - 0.12), (d / 2 + 0.03, sy + w / 2 - 0.05, h * 0.5 + 0.12), TRIM)
    b.emit.lamp_box((d / 2 + 0.012, -0.012, h - 0.12), (d / 2 + 0.018, 0.012, h - 0.06), "green", LAMP_DIM)


def vanity(b: SParts, w: float = 1.0, d: float = 0.5) -> None:
    """A small washbasin unit facing +x: a cabinet, a basin, a tap, a lit mirror above it."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.85), COMPOSITE)
    b.body.box((-d / 2 - 0.01, -w / 2 - 0.01, 0.85), (d / 2 + 0.01, w / 2 + 0.01, 0.88), STEEL)
    b.fine.box((-0.16, -0.22, 0.875), (0.16, 0.22, 0.882), DGLASS)
    b.fine.cyl((-0.20, 0.0, 0.88), (-0.20, 0.0, 1.02), 0.012, TRIM, seg=6)
    b.fine.cyl((-0.20, 0.0, 1.02), (-0.10, 0.0, 1.02), 0.012, TRIM, seg=6)
    b.fine.box((-d / 2 - 0.0, -w / 2 + 0.06, 1.28), (-d / 2 + 0.03, w / 2 - 0.06, 1.98), TRIM)
    b.fine.box((-d / 2 + 0.03, -w / 2 + 0.08, 1.30), (-d / 2 + 0.035, w / 2 - 0.08, 1.96), DGLASS)
    b.emit.lamp_box((-d / 2 + 0.03, -w / 2 + 0.06, 1.97), (-d / 2 + 0.05, w / 2 - 0.06, 2.0), "white_warm", LAMP)


def rug(b: SParts, w: float, d: float, mat: str = FABRIC_RUST, edge: str = FABRIC_SAND) -> None:
    """A rug centred on the origin (x = w, y = d), 1.2 cm thick, with a border."""
    b.soft.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.012), edge)
    b.soft.box((-w / 2 + 0.06, -d / 2 + 0.06, 0.012), (w / 2 - 0.06, d / 2 - 0.06, 0.016), mat)


# ---------------------------------------------------------------------------------------------------------------- science
def lab_island(b: SParts, w: float = 4.0, d: float = 1.3, h: float = 0.92, seed: int = 1, sink: bool = True) -> None:
    """A lab island facing +x on both sides (w along y): a worktop, cabinets, a central reagent shelf with bottles, taps, a hanging lamp bar."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2 + 0.03, 0.08), (d / 2, w / 2 - 0.03, h - 0.04), COMPOSITE)
    b.body.box((-d / 2 - 0.02, -w / 2, h - 0.04), (d / 2 + 0.02, w / 2, h), LAMINATE)
    b.body.box((-d / 2, -w / 2 + 0.03, 0.0), (d / 2, w / 2 - 0.03, 0.08), STRUCT)
    n = max(1, int(w / 0.6))
    for side in (-1, 1):
        for k in range(n):
            y0 = -w / 2 + 0.03 + k * (w - 0.06) / n
            x = side * d / 2
            b.fine.box((x if side > 0 else x - 0.012, y0 + 0.012, 0.11), (x + 0.012 if side > 0 else x, y0 + (w - 0.06) / n - 0.012, h - 0.07), IVORY)
            b.fine.box((x + (0.012 if side > 0 else -0.026), y0 + (w - 0.06) / n - 0.09, h - 0.26),
                       (x + (0.03 if side > 0 else -0.012), y0 + (w - 0.06) / n - 0.07, h - 0.16), TRIM)
    # reagent shelf on the top, along the centre line
    b.fine.box((-0.02, -w / 2 + 0.1, h), (0.02, w / 2 - 0.1, h + 0.02), TRIM)
    for sy in (-w / 2 + 0.1, w / 2 - 0.12):
        b.fine.box((-0.02, sy, h), (0.02, sy + 0.02, h + 0.62), TRIM)
    for z in (h + 0.30, h + 0.60):
        b.fine.box((-0.1, -w / 2 + 0.1, z), (0.1, w / 2 - 0.1, z + 0.015), STEEL)
    for z in (h + 0.02, h + 0.315):
        y = -w / 2 + 0.2
        while y < w / 2 - 0.2:
            r = rng.uniform(0.025, 0.045)
            hh = rng.uniform(0.10, 0.22)
            mat = rng.choice([DGLASS, CRATE_ORANGE, BEDDING, CRATE_BLUE, DGLASS])
            b.fine.cyl((rng.uniform(-0.05, 0.05), y, z), (0.0, y, z + hh), r, mat, seg=8, r2=r * 0.85)
            y += r * 2 + rng.uniform(0.03, 0.14)
    if sink:
        for side in (-1, 1):
            b.fine.box((side * 0.32 - 0.16, -0.5, h - 0.02), (side * 0.32 + 0.16, 0.0, h + 0.001), DGLASS)
            b.fine.cyl((side * 0.20, -0.25, h), (side * 0.20, -0.25, h + 0.30), 0.012, TRIM, seg=6)
    b.emit.lamp_box((-0.03, -w / 2 + 0.1, h + 0.62), (0.03, w / 2 - 0.1, h + 0.64), "white_cool", LAMP)


def fume_hood(b: SParts, w: float = 1.6, d: float = 0.9, h: float = 2.5) -> None:
    """A fume cupboard facing +x: a base cabinet, a raised sash of dark glass, a lit interior, an exhaust duct to the ceiling."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.9), COMPOSITE)
    b.body.box((-d / 2, -w / 2, 0.9), (d / 2, w / 2, 0.98), STEEL)
    b.body.box((-d / 2, -w / 2, 0.98), (-d / 2 + 0.05, w / 2, h), STEEL)
    for sy in (-w / 2, w / 2 - 0.06):
        b.body.box((-d / 2, sy, 0.98), (d / 2, sy + 0.06, h - 0.3), STEEL)
    b.body.box((-d / 2, -w / 2, h - 0.3), (d / 2, w / 2, h), STEEL)
    b.fine.box((d / 2 - 0.02, -w / 2 + 0.06, 1.05), (d / 2, w / 2 - 0.06, h - 0.32), DGLASS)
    b.fine.box((d / 2 - 0.03, -w / 2 + 0.04, 1.02), (d / 2 + 0.01, w / 2 - 0.04, 1.08), TRIM)
    b.emit.lamp_box((-d / 2 + 0.1, -w / 2 + 0.2, h - 0.34), (d / 2 - 0.1, w / 2 - 0.2, h - 0.325), "white_cool", LAMP)
    b.emit.label((d / 2 + 0.002, 0.0, h - 0.15), 0.5, 0.125, (1, 0, 0), "eq_lab")
    b.fine.box((d / 2 + 0.005, w / 2 - 0.2, 0.62), (d / 2 + 0.02, w / 2 - 0.05, 0.75), STRUCT)
    b.emit.lamp_box((d / 2 + 0.02, w / 2 - 0.17, 0.66), (d / 2 + 0.024, w / 2 - 0.08, 0.7), "green", LAMP_DIM)


def microscope(b: SParts) -> None:
    b.body.box((-0.14, -0.10, 0.0), (0.12, 0.10, 0.03), STEEL)
    b.body.box((-0.12, -0.03, 0.03), (-0.06, 0.03, 0.34), STEEL)
    from mathutils import Vector
    b.body.cyl(Vector((-0.09, 0, 0.32)), Vector((0.06, 0, 0.42)), 0.032, STEEL, seg=10)
    b.fine.cyl(Vector((0.06, 0, 0.42)), Vector((0.10, 0, 0.5)), 0.022, TRIM, seg=8)
    b.fine.box((-0.02, -0.06, 0.15), (0.06, 0.06, 0.165), TRIM)
    b.fine.cyl(Vector((0.02, 0, 0.30)), Vector((0.02, 0, 0.18)), 0.014, TRIM, seg=6)


def centrifuge(b: SParts) -> None:
    b.body.box((-0.22, -0.22, 0.0), (0.22, 0.22, 0.26), STEEL)
    b.body.cyl((0, 0, 0.26), (0, 0, 0.30), 0.19, TRIM, seg=16)
    b.fine.box((0.22, -0.12, 0.10), (0.235, 0.12, 0.22), DGLASS)
    b.emit.lamp_box((0.222, -0.05, 0.16), (0.24, 0.05, 0.19), "cyan", LAMP_DIM)


def sample_fridge(b: SParts, w: float = 0.9, d: float = 0.75, h: float = 2.0) -> None:
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), STEEL)
    b.fine.box((d / 2, -w / 2 + 0.03, 0.06), (d / 2 + 0.012, w / 2 - 0.03, h - 0.06), DGLASS)
    b.emit.lamp_box((d / 2 + 0.012, -w / 2 + 0.06, 0.1), (d / 2 + 0.016, -w / 2 + 0.09, h - 0.1), "ice", LAMP_DIM)
    b.fine.box((d / 2 + 0.012, w / 2 - 0.09, h * 0.5 - 0.2), (d / 2 + 0.03, w / 2 - 0.07, h * 0.5 + 0.2), TRIM)
    b.emit.label((d / 2 + 0.014, 0.0, h - 0.2), 0.36, 0.09, (1, 0, 0), "small_15")


def holo_table(b: SParts, r: float = 0.9, h: float = 0.9) -> None:
    """A round holographic table: a pedestal, a dark disc, a rim of light, a faint column of projected light above the emitter."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.06), 0.5, STRUCT, seg=20, r2=0.5)
    b.body.cyl((0, 0, 0.06), (0, 0, h - 0.1), 0.24, COMPOSITE, seg=18, r2=0.3)
    b.body.cyl((0, 0, h - 0.1), (0, 0, h), r, STEEL, seg=32, r2=r)
    b.fine.cyl((0, 0, h), (0, 0, h + 0.012), r - 0.05, DGLASS, seg=32)
    for k in range(48):
        a0, a1 = 2 * math.pi * k / 48, 2 * math.pi * (k + 1) / 48
        p0, p1 = (r * 0.95 * math.cos(a0), r * 0.95 * math.sin(a0)), (r * 0.95 * math.cos(a1), r * 0.95 * math.sin(a1))
        from ship_lib import lamp_strip
        lamp_strip(b.emit, (p0[0], p0[1], h + 0.013), (p1[0], p1[1], h + 0.013), 0.018, 0.004, "cyan", LAMP_DIM)
    b.emit.lamp_cyl((0, 0, h + 0.012), (0, 0, h + 0.42), 0.16, "cyan", LAMP_DIM, seg=16, r2=0.05)
    b.emit.lamp_cyl((0, 0, h + 0.42), (0, 0, h + 0.46), 0.05, "ice", LAMP, seg=12, r2=0.05)


def spectrometer(b: SParts, w: float = 1.0, d: float = 0.6) -> None:
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.36), STEEL)
    b.body.box((-d / 2 + 0.05, -w / 2 + 0.1, 0.36), (d / 2 - 0.05, w / 2 - 0.1, 0.5), COMPOSITE)
    b.fine.box((d / 2 - 0.05, -w / 2 + 0.16, 0.38), (d / 2 - 0.045, w / 2 - 0.16, 0.48), DGLASS)
    b.emit.lamp_box((d / 2 - 0.045, -w / 2 + 0.2, 0.40), (d / 2 - 0.04, w / 2 - 0.2, 0.42), "cyan", LAMP_DIM)
    b.fine.cyl((0.0, -w / 2 + 0.12, 0.5), (0.0, -w / 2 + 0.12, 0.7), 0.02, TRIM, seg=8)


# ---------------------------------------------------------------------------------------------------------------- workshop
def lathe(b: SParts, l: float = 2.4, d: float = 0.9, h: float = 1.05) -> None:
    """A bench lathe, its axis along y (the operator stands on +x): a cabinet base, a bed, headstock, chuck, tailstock, a lit work area."""
    b.body.box((-d / 2, -l / 2, 0.0), (d / 2, -l / 2 + 0.6, 0.9), CRATE_GREY)
    b.body.box((-d / 2, l / 2 - 0.6, 0.0), (d / 2, l / 2, 0.9), CRATE_GREY)
    b.body.box((-0.22, -l / 2 + 0.05, 0.9), (0.28, l / 2 - 0.05, 0.98), STEEL)
    b.body.box((-0.24, -l / 2 + 0.05, 0.98), (0.10, -l / 2 + 0.85, 1.36), CRATE_GREY)                # headstock
    b.body.cyl((0.0, -l / 2 + 0.85, 1.16), (0.0, -l / 2 + 1.02, 1.16), 0.16, STEEL, seg=18)         # chuck
    for k in range(3):
        a = math.radians(90 * k + 30)
        b.fine.box((0.15 * math.cos(a) - 0.02, -l / 2 + 1.02, 1.16 + 0.15 * math.sin(a) - 0.02), (0.15 * math.cos(a) + 0.02, -l / 2 + 1.1, 1.16 + 0.15 * math.sin(a) + 0.02), TRIM)
    b.body.box((-0.24, l / 2 - 0.85, 0.98), (0.10, l / 2 - 0.05, 1.22), CRATE_GREY)                # tailstock
    b.fine.cyl((0.0, l / 2 - 0.85, 1.16), (0.0, l / 2 - 1.15, 1.16), 0.03, TRIM, seg=8)
    b.body.box((0.05, -0.1, 0.98), (0.30, 0.3, 1.06), STEEL)                                        # carriage
    b.fine.box((0.12, -0.05, 1.06), (0.26, 0.2, 1.10), CRATE_ORANGE)
    b.fine.cyl((0.36, 0.1, 1.06), (0.36, 0.1, 1.24), 0.012, TRIM, seg=6)
    b.emit.lamp_box((0.15, -l / 2 + 0.35, 1.4), (0.18, l / 2 - 0.35, 1.43), "white_cool", LAMP)
    b.fine.box((0.30, -l / 2 + 0.06, 0.94), (0.315, -l / 2 + 0.5, 1.10), STRUCT)
    b.emit.lamp_box((0.316, -l / 2 + 0.1, 1.02), (0.322, -l / 2 + 0.2, 1.06), "green", LAMP_DIM)


def mill(b: SParts, w: float = 1.3, d: float = 1.0) -> None:
    """A vertical milling machine facing +x: a base, a column, a head with a spindle, a moving table."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.75), CRATE_GREY)
    b.body.box((-d / 2, -0.22, 0.75), (-d / 2 + 0.35, 0.22, 2.1), CRATE_GREY)
    b.body.box((-d / 2, -0.28, 1.75), (0.25, 0.28, 2.1), CRATE_GREY)
    b.body.cyl((0.12, 0, 1.75), (0.12, 0, 1.3), 0.06, STEEL, seg=12)
    b.fine.cyl((0.12, 0, 1.3), (0.12, 0, 1.15), 0.02, TRIM, seg=8)
    b.body.box((-0.3, -w / 2 + 0.05, 0.75), (0.3, w / 2 - 0.05, 0.86), STEEL)
    b.fine.box((-0.3, -w / 2 + 0.05, 0.86), (0.3, w / 2 - 0.05, 0.9), TRIM)
    b.fine.box((-0.15, -0.2, 0.9), (0.10, 0.2, 1.0), CRATE_BLUE)
    b.emit.lamp_box((0.25, -0.15, 1.95), (0.27, 0.15, 2.05), "white_cool", LAMP)


def drill_press(b: SParts) -> None:
    b.body.box((-0.3, -0.22, 0.0), (0.3, 0.22, 0.05), STRUCT)
    b.body.cyl((-0.18, 0, 0.05), (-0.18, 0, 1.75), 0.05, STEEL, seg=10)
    b.body.box((-0.24, -0.11, 1.45), (0.2, 0.11, 1.78), CRATE_GREY)
    b.body.cyl((0.1, 0, 1.45), (0.1, 0, 1.0), 0.03, STEEL, seg=8)
    b.fine.cyl((0.1, 0, 1.0), (0.1, 0, 0.88), 0.01, TRIM, seg=6)
    b.body.box((-0.2, -0.16, 0.7), (0.24, 0.16, 0.74), STEEL)
    for k in range(3):
        a = math.radians(120 * k)
        b.fine.cyl((0.24 + 0.0, 0, 1.55), (0.24 + 0.16 * math.cos(a), 0.16 * math.sin(a), 1.55 + 0.08 * math.sin(a + 1)), 0.008, TRIM, seg=6)


def workbench(b: SParts, w: float = 2.4, d: float = 0.8, h: float = 0.95, vise: bool = True) -> None:
    """A heavy steel workbench facing +x, drawers under the top, a vise on the left corner, a lower shelf."""
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, h - 0.06), (d / 2 + 0.02, w / 2 + 0.02, h), STEEL)
    b.body.box((-d / 2 + 0.04, -w / 2 + 0.03, h - 0.24), (d / 2 - 0.04, w / 2 - 0.03, h - 0.06), COMPOSITE)
    for k in range(3):
        y0 = -w / 2 + 0.08 + k * (w - 0.16) / 3
        b.fine.box((d / 2 - 0.04, y0 + 0.02, h - 0.22), (d / 2 - 0.025, y0 + (w - 0.16) / 3 - 0.02, h - 0.08), CRATE_GREY)
        b.fine.box((d / 2 - 0.025, y0 + (w - 0.16) / 3 * 0.5 - 0.1, h - 0.16), (d / 2 - 0.005, y0 + (w - 0.16) / 3 * 0.5 + 0.1, h - 0.145), TRIM)
    for sx in (-d / 2 + 0.06, d / 2 - 0.06):
        for sy in (-w / 2 + 0.06, w / 2 - 0.06):
            b.body.box((sx - 0.03, sy - 0.03, 0.0), (sx + 0.03, sy + 0.03, h - 0.24), CRATE_ORANGE)
    b.body.box((-d / 2 + 0.05, -w / 2 + 0.05, 0.22), (d / 2 - 0.05, w / 2 - 0.05, 0.25), STEEL)
    if vise:
        b.body.box((d / 2 - 0.16, w / 2 - 0.34, h), (d / 2 + 0.04, w / 2 - 0.10, h + 0.12), CRATE_GREY)
        b.fine.box((d / 2 - 0.03, w / 2 - 0.34, h + 0.06), (d / 2 + 0.06, w / 2 - 0.10, h + 0.13), STEEL)
        b.fine.cyl((d / 2 + 0.04, w / 2 - 0.22, h + 0.06), (d / 2 + 0.3, w / 2 - 0.22, h + 0.06), 0.012, TRIM, seg=6)


def tool_wall(b: SParts, w: float = 3.0, h: float = 1.5, seed: int = 2) -> None:
    """A pegboard on the wall facing +x with hung tools (silhouettes: hammers, spanners, cutters, saws) and shadow-line outlines."""
    rng = random.Random(seed)
    b.body.box((-0.03, -w / 2, 0.0), (0.0, w / 2, h), COMPOSITE)
    for k in range(int(w / 0.15)):
        b.fine.box((0.0, -w / 2 + 0.05 + k * 0.15, 0.05), (0.004, -w / 2 + 0.054 + k * 0.15, h - 0.05), STRUCT)
    y = -w / 2 + 0.14
    while y < w / 2 - 0.25:
        kind = rng.choice(["hammer", "spanner", "cutter", "saw", "driver"])
        ln = rng.uniform(0.25, 0.5)
        z = rng.uniform(0.4, h - 0.2 - ln * 0.4)
        if kind == "hammer":
            b.fine.box((0.004, y - 0.008, z - ln * 0.6), (0.02, y + 0.008, z), WOOD)
            b.fine.box((0.004, y - 0.05, z), (0.03, y + 0.05, z + 0.05), STEEL)
        elif kind == "spanner":
            b.fine.box((0.004, y - 0.012, z - ln * 0.7), (0.014, y + 0.012, z), STEEL)
            b.fine.box((0.004, y - 0.035, z), (0.014, y + 0.035, z + 0.05), STEEL)
        elif kind == "cutter":
            b.fine.box((0.004, y - 0.03, z - ln * 0.5), (0.014, y - 0.006, z), CRATE_ORANGE)
            b.fine.box((0.004, y + 0.006, z - ln * 0.5), (0.014, y + 0.03, z), CRATE_ORANGE)
        elif kind == "saw":
            b.fine.box((0.004, y - 0.05, z - ln * 0.6), (0.010, y + 0.05, z), STEEL)
            b.fine.box((0.004, y - 0.03, z), (0.02, y + 0.03, z + 0.09), CRATE_ORANGE)
        else:
            b.fine.box((0.004, y - 0.008, z - ln * 0.6), (0.014, y + 0.008, z), STEEL)
            b.fine.box((0.004, y - 0.02, z), (0.024, y + 0.02, z + 0.1), CRATE_ORANGE)
        y += rng.uniform(0.18, 0.28)
    b.emit.lamp_box((0.0, -w / 2 + 0.1, h + 0.02), (0.06, w / 2 - 0.1, h + 0.05), "white_cool", LAMP)


def welding_bay(b: SParts, w: float = 3.2, d: float = 2.6) -> None:
    """A welding cell: three amber curtains on a frame, a steel table with clamps, a fume arm, two gas cylinders on a chain, hazard tape."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, -w / 2 + 0.05, 2.5), STRUCT)
    b.body.box((-d / 2, w / 2 - 0.05, 0.0), (d / 2, w / 2, 2.5), STRUCT)
    b.body.box((-d / 2, -w / 2, 2.45), (d / 2, w / 2, 2.55), STRUCT)
    for sy in (-w / 2 + 0.05, w / 2 - 0.09):
        b.fine.box((-d / 2 + 0.05, sy, 0.0), (-d / 2 + 0.07, sy + 0.04, 2.5), CRATE_ORANGE)
    b.soft.box((-d / 2 + 0.04, -w / 2 + 0.06, 0.15), (-d / 2 + 0.08, w / 2 - 0.06, 2.42), CRATE_ORANGE)
    b.body.box((-0.4, -0.8, 0.0), (0.6, 0.8, 0.82), STEEL)
    b.body.box((-0.45, -0.85, 0.82), (0.65, 0.85, 0.88), STEEL)
    for k in range(6):
        b.fine.cyl((0.65 - 0.02, -0.7 + k * 0.28, 0.885), (0.65 - 0.02, -0.7 + k * 0.28, 0.9), 0.05, STRUCT, seg=8)
    b.fine.box((0.1, -0.3, 0.88), (0.3, 0.1, 0.92), CRATE_GREY)
    b.body.cyl((-0.3, 0.7, 2.4), (-0.3, 0.7, 1.9), 0.05, STEEL, seg=8)
    b.fine.cyl((-0.3, 0.7, 1.9), (0.3, 0.4, 1.4), 0.04, TRIM, seg=8)
    for k, y in enumerate((w / 2 - 0.4, w / 2 - 0.85)):
        b.body.cyl((-d / 2 + 0.3, y, 0.0), (-d / 2 + 0.3, y, 1.4), 0.12, CRATE_BLUE if k == 0 else CRATE_OLIVE, seg=14)
        b.body.sphere((-d / 2 + 0.3, y, 1.4), 0.12, CRATE_BLUE if k == 0 else CRATE_OLIVE, seg=14, rings=7, squash=(1, 1, 0.6))
        b.fine.cyl((-d / 2 + 0.3, y, 1.44), (-d / 2 + 0.3, y, 1.52), 0.03, TRIM, seg=8)
    b.fine.box((-d / 2 + 0.06, w / 2 - 0.95, 0.9), (-d / 2 + 0.08, w / 2 - 0.15, 0.94), TRIM)
    b.emit.label((-d / 2 + 0.09, 0.0, 2.2), 1.2, 0.15, (1, 0, 0), "hazard")


def parts_bins(b: SParts, w: float = 2.0, h: float = 1.9, d: float = 0.5, seed: int = 3) -> None:
    """A steel frame of small-parts bins (open front, coloured), labelled."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.03, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.03, h), STRUCT)
    rows, cols = 6, int(w / 0.25)
    for r in range(rows + 1):
        b.body.box((-d / 2, -w / 2, 0.05 + r * (h - 0.08) / rows), (d / 2, w / 2, 0.065 + r * (h - 0.08) / rows), STEEL)
    for r in range(rows):
        for c in range(cols):
            y0 = -w / 2 + 0.05 + c * (w - 0.1) / cols
            z0 = 0.065 + r * (h - 0.08) / rows
            b.fine.box((-d / 2 + 0.05, y0 + 0.008, z0), (d / 2 - 0.02, y0 + (w - 0.1) / cols - 0.008, z0 + (h - 0.08) / rows - 0.06), rng.choice([CRATE_BLUE, CRATE_ORANGE, CRATE_GREY, CRATE_OLIVE]))


def overhead_rail(b: SParts, l: float, y: float, z: float, hoist_x: float | None = None) -> None:
    """A gantry rail along x at height z (drawn from x = 0 to l) with a hoist on a trolley."""
    b.body.box((0.0, y - 0.09, z), (l, y + 0.09, z + 0.16), CRATE_ORANGE)
    b.fine.box((0.0, y - 0.13, z + 0.16), (l, y + 0.13, z + 0.2), STEEL)
    hx = l * 0.4 if hoist_x is None else hoist_x
    b.body.box((hx - 0.3, y - 0.2, z - 0.36), (hx + 0.3, y + 0.2, z), CRATE_GREY)
    b.fine.cyl((hx, y, z - 0.36), (hx, y, z - 0.9), 0.012, TRIM, seg=6)
    b.fine.box((hx - 0.06, y - 0.04, z - 1.0), (hx + 0.06, y + 0.04, z - 0.9), CRATE_ORANGE)
    b.emit.lamp_box((hx - 0.04, y + 0.2, z - 0.24), (hx + 0.04, y + 0.202, z - 0.2), "amber", LAMP)


# ---------------------------------------------------------------------------------------------------------------- armory
def rifle(b: SParts, l: float = 0.95) -> None:
    """A carbine lying along +x centred on the origin: receiver, barrel, stock, magazine, sight. About 4 cm thick."""
    b.fine.box((-l / 2 + 0.18, -0.02, -0.03), (l / 2 - 0.30, 0.02, 0.03), CRATE_GREY)
    b.fine.box((-l / 2, -0.016, -0.05), (-l / 2 + 0.22, 0.016, 0.03), COMPOSITE)
    b.fine.cyl((l / 2 - 0.30, 0, 0.005), (l / 2, 0, 0.005), 0.011, STRUCT, seg=6)
    b.fine.box((-0.02, -0.014, -0.11), (0.03, 0.014, -0.03), COMPOSITE)
    b.fine.box((-0.1, -0.008, 0.03), (0.06, 0.008, 0.055), TRIM)
    b.emit.lamp_box((0.10, -0.004, 0.02), (0.12, 0.004, 0.03), "red", LAMP_DIM)


def weapon_rack(b: SParts, w: float = 2.0, n: int = 6, h: float = 1.9, seed: int = 1) -> None:
    """A wall rack facing +x holding n carbines upright (barrels up), a cable lock bar, a status lamp for each and a red 'ordnance' plate."""
    b.body.box((-0.06, -w / 2, 0.1), (0.0, w / 2, h), COMPOSITE)
    b.body.box((-0.03, -w / 2, 0.0), (0.16, w / 2, 0.1), STRUCT)
    b.fine.box((0.0, -w / 2 + 0.02, 1.35), (0.05, w / 2 - 0.02, 1.38), STEEL)
    b.fine.box((0.0, -w / 2 + 0.02, 0.6), (0.05, w / 2 - 0.02, 0.63), STEEL)
    from bridge3_lib import Ry
    for k in range(n):
        y = -w / 2 + (k + 0.5) * w / n
        with b.at(T(0.10, y, 0.99) @ Ry(-90)):
            rifle(b, 0.95)
        b.emit.lamp_box((0.0, y - 0.012, 1.42), (0.006, y + 0.012, 1.45), "green" if (k + seed) % 5 else "amber", LAMP_DIM)
    b.emit.label((0.002, 0.0, h - 0.12), min(w * 0.6, 1.2), min(w * 0.6, 1.2) / 4, (1, 0, 0), "eq_ammo")


def ammo_locker(b: SParts, w: float = 0.9, d: float = 0.6, h: float = 1.9, mat: str = CRATE_OLIVE) -> None:
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), mat)
    b.fine.box((d / 2, -w / 2 + 0.03, 0.08), (d / 2 + 0.014, w / 2 - 0.03, h - 0.08), STRUCT)
    for z in (0.6, 1.2):
        b.fine.box((d / 2 + 0.014, -w / 2 + 0.03, z), (d / 2 + 0.02, w / 2 - 0.03, z + 0.02), TRIM)
    b.fine.box((d / 2 + 0.014, w / 2 - 0.12, h * 0.5 - 0.1), (d / 2 + 0.035, w / 2 - 0.08, h * 0.5 + 0.1), TRIM)
    b.emit.label((d / 2 + 0.016, 0.0, h - 0.18), 0.5, 0.125, (1, 0, 0), "hazard")
    b.emit.lamp_box((d / 2 + 0.016, -w / 2 + 0.06, 0.16), (d / 2 + 0.022, -w / 2 + 0.1, 0.2), "red", LAMP_DIM)


def cage_wall(b: SParts, w: float = 4.0, h: float = 2.6, pitch: float = 0.12) -> None:
    """A security cage panel in the yz plane (x = 0, y along w): a steel frame and a fine grid of bars."""
    b.body.box((-0.03, -w / 2, 0.0), (0.03, -w / 2 + 0.05, h), STEEL)
    b.body.box((-0.03, w / 2 - 0.05, 0.0), (0.03, w / 2, h), STEEL)
    b.body.box((-0.03, -w / 2, h - 0.05), (0.03, w / 2, h), STEEL)
    b.body.box((-0.03, -w / 2, 0.0), (0.03, w / 2, 0.06), STEEL)
    for k in range(1, int(w / pitch)):
        b.fine.box((-0.006, -w / 2 + k * pitch - 0.004, 0.06), (0.006, -w / 2 + k * pitch + 0.004, h - 0.05), STRUCT)
    for k in range(1, int(h / (pitch * 1.6))):
        b.fine.box((-0.006, -w / 2 + 0.05, k * pitch * 1.6 - 0.004), (0.006, w / 2 - 0.05, k * pitch * 1.6 + 0.004), STRUCT)


def armor_stand(b: SParts, mat: str = COMPOSITE) -> None:
    """A dummy in combat armour facing +x: stand, torso, shoulders, helmet with a visor, a chest lamp."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.03), 0.28, STRUCT, seg=16)
    b.body.cyl((0, 0, 0.03), (0, 0, 1.0), 0.03, TRIM, seg=8)
    b.body.box((-0.13, -0.18, 0.95), (0.13, 0.18, 1.55), mat)
    b.body.box((-0.16, -0.30, 1.42), (0.16, -0.16, 1.58), IVORY)
    b.body.box((-0.16, 0.16, 1.42), (0.16, 0.30, 1.58), IVORY)
    b.fine.box((0.13, -0.12, 1.15), (0.145, 0.12, 1.5), CRATE_GREY)
    b.emit.lamp_box((0.145, -0.03, 1.4), (0.15, 0.03, 1.46), "cyan", LAMP_DIM)
    b.body.cyl((0, 0, 1.55), (0, 0, 1.62), 0.06, TRIM, seg=8)
    b.body.sphere((0.0, 0.0, 1.72), 0.13, mat, seg=14, rings=9, squash=(1.1, 1.0, 1.0))
    b.fine.box((0.08, -0.10, 1.68), (0.14, 0.10, 1.76), DGLASS)
    for sy in (-0.2, 0.2):
        b.fine.box((-0.08, sy - 0.05, 0.4), (0.08, sy + 0.05, 0.95), mat)


def gun_bench(b: SParts, w: float = 2.0, d: float = 0.8) -> None:
    F.counter(b, w, d, 0.95, STEEL, COMPOSITE, True, False)
    b.fine.box((-d / 2 - 0.02, -w / 2 + 0.1, 0.95), (-d / 2 + 0.02, w / 2 - 0.1, 1.5), STRUCT)
    b.emit.lamp_box((-d / 2 + 0.02, -w / 2 + 0.2, 1.42), (-d / 2 + 0.05, w / 2 - 0.2, 1.46), "white_cool", LAMP)
    b.fine.box((-0.15, -0.5, 0.95), (0.2, 0.5, 0.97), RUBBER)


# ---------------------------------------------------------------------------------------------------------------- wall pieces
def wall_shelf_row(b: SParts, w: float, z: float, depth: float = 0.25, mat: str = WOOD, items: str = "books", seed: int = 1) -> None:
    """A shelf on a wall facing +x, centred on y = 0 (w wide), at height z, with books / mugs on it."""
    rng = random.Random(seed)
    b.body.box((0.0, -w / 2, z), (depth, w / 2, z + 0.03), mat)
    y = -w / 2 + 0.06
    while y < w / 2 - 0.1:
        bw = rng.uniform(0.02, 0.05)
        bh = rng.uniform(0.16, 0.28)
        b.fine.box((0.02, y, z + 0.03), (0.02 + rng.uniform(0.12, depth - 0.05), y + bw, z + 0.03 + bh),
                   rng.choice([FABRIC_NAVY, FABRIC_RUST, FABRIC_GREY, BEDDING, FABRIC_SAND, CRATE_OLIVE]))
        y += bw + 0.004
        if rng.random() < 0.1:
            y += rng.uniform(0.08, 0.2)


def pict_plate(b: SParts, w: float, tile: str, z: float = 1.6) -> None:
    """A wall label of the atlas facing +x centred on y = 0 (a signboard)."""
    b.emit.label_fit((0.002, 0.0, z), w, tile, (1, 0, 0))
