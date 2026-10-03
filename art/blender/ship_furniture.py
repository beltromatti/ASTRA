"""ASN Aquila interior kit: furniture and fittings for the rooms (bridge v3 language: dark composite, ivory, brushed metal, light lines).

Every function builds one piece in ITS OWN frame (origin on the floor, x = the piece's front, y = its left, z up) into a `SParts`
(groups: body = bevelled hard-surface, fine = small details, soft = cushions and cloth, emit = lamps and labels); the caller places it with
`with b.at(frame(x, y, 0.0, yaw)):` (bridge3_lib.frame). All sizes in metres.
"""
from __future__ import annotations

import math
import random

from bridge3_lib import Rx, Ry, Rz, T, frame
import ship_lib as SL
import ship_furn2 as N
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, DECK, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, LEATHER, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts)

CRATES = [CRATE_OLIVE, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY]


# ---------------------------------------------------------------------------------------------------------------- seating
def stool(b: SParts, r: float = 0.19, h: float = 0.46, mat: str = FABRIC_NAVY) -> None:
    N.stool(b, r, h, mat)


def chair(b: SParts, seat: str = FABRIC_NAVY, frame_mat: str = TRIM, h: float = 0.46, w: float = 0.46) -> None:
    """A ship's chair facing +x: a padded seat and back on four tapered steel legs (ship_furn2)."""
    N.chair(b, seat, frame_mat, h, w)


def armchair(b: SParts, mat: str = FABRIC_GREY) -> None:
    N.armchair(b, mat)


def sofa(b: SParts, w: float = 2.0, mat: str = FABRIC_NAVY, arms: bool = True) -> None:
    """A sofa facing +x, w long along y (ship_furn2)."""
    N.sofa(b, w, mat, arms)


def bench(b: SParts, w: float = 1.8, d: float = 0.42, h: float = 0.46, mat: str = FABRIC_GREY) -> None:
    N.bench(b, w, d, h, mat)


# ---------------------------------------------------------------------------------------------------------------- tables
def table(b: SParts, w: float = 1.4, d: float = 0.8, h: float = 0.74, top: str = LAMINATE, base: str = TRIM, pedestal: bool = False) -> None:
    """A table centred on the origin, w along x, d along y (ship_furn2)."""
    N.table(b, w, d, h, top, base, pedestal)


def low_table(b: SParts, w: float = 1.1, d: float = 0.6, h: float = 0.38, mat: str = WOOD) -> None:
    N.low_table(b, w, d, h, mat)


def desk(b: SParts, w: float = 1.4, d: float = 0.7, h: float = 0.74, top: str = WOOD, drawers: bool = True) -> None:
    """A desk, its front (the sitter's side) towards -x... centred, kneehole toward -x (ship_furn2)."""
    N.desk(b, w, d, h, top, drawers)


# ---------------------------------------------------------------------------------------------------------------- storage
def shelf(b: SParts, w: float = 1.0, d: float = 0.34, h: float = 2.0, shelves: int = 5, mat: str = WOOD, books: bool = True, seed: int = 1,
          back: bool = True) -> None:
    """A shelving unit facing +x (its back at -d/2), w along y; books and small things on the shelves (ship_furn2)."""
    N.shelf(b, w, d, h, shelves, mat, books, seed, back)


def crate(b: SParts, w: float = 0.6, d: float = 0.4, h: float = 0.4, mat: str = CRATE_OLIVE, label: str | None = None, lite: bool = False) -> None:
    """A stores crate: shell, lid, corner posts, a tag. `lite` (racks, stacks): the shell and the lid only, in the soft group (no bevel)."""
    if lite:
        b.soft.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h - 0.03), mat)
        b.soft.box((-d / 2 - 0.006, -w / 2 - 0.006, h - 0.03), (d / 2 + 0.006, w / 2 + 0.006, h), TRIM)
        return
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), mat)
    b.fine.box((-d / 2 - 0.006, -w / 2 - 0.006, h - 0.03), (d / 2 + 0.006, w / 2 + 0.006, h), TRIM)
    for sx in (-d / 2, d / 2 - 0.03):
        for sy in (-w / 2, w / 2 - 0.03):
            b.fine.box((sx, sy, 0.0), (sx + 0.03, sy + 0.03, h), TRIM)
    if label:
        b.emit.label((d / 2 + 0.002, 0.0, h * 0.55), min(w * 0.7, 0.36), min(w * 0.7, 0.36) / 4, (1, 0, 0), label)


def pallet(b: SParts, w: float = 1.2, d: float = 0.8) -> None:
    for sx in (-d / 2 + 0.06, 0.0, d / 2 - 0.06):
        b.fine.box((sx - 0.05, -w / 2, 0.02), (sx + 0.05, w / 2, 0.12), WOOD)
    b.body.box((-d / 2, -w / 2, 0.12), (d / 2, w / 2, 0.145), WOOD)


def barrel(b: SParts, r: float = 0.28, h: float = 0.8, mat: str = CRATE_BLUE) -> None:
    b.body.cyl((0, 0, 0.0), (0, 0, h), r, mat, seg=16)
    for z in (0.15, h - 0.15):
        b.fine.cyl((0, 0, z - 0.02), (0, 0, z + 0.02), r + 0.008, TRIM, seg=16)
    b.fine.cyl((0, 0, h), (0, 0, h + 0.012), r * 0.9, TRIM, seg=16)


def rack(b: SParts, w: float = 2.4, d: float = 0.9, h: float = 2.6, levels: int = 4, seed: int = 3, load: float = 0.75, mats=None) -> None:
    """Heavy stores rack facing +x: uprights, beams and crates / boxes on the levels."""
    rng = random.Random(seed)
    mats = mats or CRATES
    for sx in (-d / 2, d / 2 - 0.06):
        for sy in (-w / 2, w / 2 - 0.06):
            b.body.box((sx, sy, 0.0), (sx + 0.06, sy + 0.06, h), STRUCT)
    zs = [0.25 + k * (h - 0.3) / levels for k in range(levels)]
    for z in zs:
        for sx in (-d / 2, d / 2 - 0.05):
            b.body.box((sx, -w / 2, z), (sx + 0.05, w / 2, z + 0.09), CRATE_ORANGE)
        b.fine.box((-d / 2, -w / 2 + 0.06, z + 0.09), (d / 2, w / 2 - 0.06, z + 0.105), STEEL)
    for i, z in enumerate(zs):
        y = -w / 2 + 0.1
        zc = z + 0.105
        top = (zs[i + 1] if i + 1 < len(zs) else h) - 0.02
        while y < w / 2 - 0.3:
            if rng.random() > load:
                y += rng.uniform(0.3, 0.6)
                continue
            cw = rng.choice([0.5, 0.6, 0.8])
            ch = min(rng.choice([0.3, 0.4, 0.5]), top - zc - 0.05)
            if ch < 0.2 or y + cw > w / 2 - 0.08:
                break
            with b.at(T(0.0, y + cw / 2, zc)):
                crate(b, cw, min(d - 0.12, rng.choice([0.5, 0.6, 0.7])), ch, rng.choice(mats), None, True)
            y += cw + rng.uniform(0.02, 0.08)


def locker_row(b: SParts, n: int = 4, w: float = 0.45, h: float = 1.95, d: float = 0.5, mat: str = COMPOSITE) -> None:
    """A row of tall lockers along y, doors facing +x."""
    for k in range(n):
        y0 = k * w
        b.body.box((-d / 2, y0 + 0.004, 0.0), (d / 2, y0 + w - 0.004, h), mat)
        b.fine.box((d / 2, y0 + 0.02, 0.06), (d / 2 + 0.012, y0 + w - 0.02, h - 0.06), STRUCT)
        b.fine.box((d / 2 + 0.012, y0 + w - 0.09, h * 0.5 - 0.1), (d / 2 + 0.03, y0 + w - 0.07, h * 0.5 + 0.1), TRIM)
        for j in range(3):
            b.fine.box((d / 2 + 0.012, y0 + 0.07, h - 0.16 - j * 0.04), (d / 2 + 0.02, y0 + w - 0.07, h - 0.14 - j * 0.04), RUBBER)
        b.emit.lamp_box((d / 2 + 0.012, y0 + 0.05, 0.16), (d / 2 + 0.018, y0 + 0.08, 0.19), "green", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------- work surfaces
def counter(b: SParts, w: float = 2.0, d: float = 0.65, h: float = 0.92, top: str = STEEL, body: str = COMPOSITE, doors: bool = True,
            sink: bool = False) -> None:
    """A base counter facing +x (front at +d/2), w along y; optionally with an inset sink."""
    b.body.box((-d / 2, -w / 2, 0.08), (d / 2 - 0.02, w / 2, h - 0.04), body)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.01, h - 0.04), (d / 2 + 0.02, w / 2 + 0.01, h), top)
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2 - 0.06, w / 2, 0.08), STRUCT)
    if doors:
        n = max(1, int(w / 0.6))
        for k in range(n):
            y0 = -w / 2 + k * w / n
            b.fine.box((d / 2 - 0.02, y0 + 0.012, 0.12), (d / 2 - 0.006, y0 + w / n - 0.012, h - 0.09), IVORY if body == COMPOSITE else body)
            b.fine.box((d / 2 - 0.006, y0 + w / n - 0.09, h - 0.24), (d / 2 + 0.01, y0 + w / n - 0.07, h - 0.14), TRIM)
    if sink:
        b.fine.box((-0.2, -0.3, h - 0.045), (0.2, 0.3, h - 0.02), DGLASS)
        b.fine.cyl((-0.22, 0.0, h), (-0.22, 0.0, h + 0.26), 0.014, TRIM, seg=8)
        b.fine.cyl((-0.22, 0.0, h + 0.26), (-0.10, 0.0, h + 0.26), 0.014, TRIM, seg=8)


def range_cooker(b: SParts, w: float = 0.9, d: float = 0.75, h: float = 0.92, kind: str = "range") -> None:
    """A galley cooking unit facing +x: steel body, oven door with a window, a rail; kind = range (four burners) | griddle | fryer (two wells)."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), STEEL)
    b.fine.box((d / 2, -w / 2 + 0.04, 0.12), (d / 2 + 0.03, w / 2 - 0.04, 0.62), STRUCT)
    if kind != "fryer":
        b.fine.box((d / 2 + 0.03, -w / 2 + 0.10, 0.24), (d / 2 + 0.035, w / 2 - 0.10, 0.5), DGLASS)
    b.fine.cyl((d / 2 + 0.06, -w / 2 + 0.06, 0.66), (d / 2 + 0.06, w / 2 - 0.06, 0.66), 0.014, TRIM, seg=8)
    if kind == "range":
        for sy in (-0.22, 0.22):
            for sx in (-0.19, 0.19):
                b.fine.cyl((sx, sy, h), (sx, sy, h + 0.012), 0.10, RUBBER, seg=16)
                b.fine.cyl((sx, sy, h + 0.012), (sx, sy, h + 0.02), 0.05, TRIM, seg=12)
    elif kind == "griddle":
        b.fine.box((-d / 2 + 0.03, -w / 2 + 0.03, h), (d / 2 - 0.03, w / 2 - 0.03, h + 0.012), TRIM)
        b.fine.box((-d / 2 + 0.03, -w / 2 + 0.03, h + 0.012), (d / 2 - 0.03, -w / 2 + 0.06, h + 0.06), STEEL)
        b.fine.box((-d / 2 + 0.03, w / 2 - 0.06, h + 0.012), (d / 2 - 0.03, w / 2 - 0.03, h + 0.06), STEEL)
        b.fine.box((-d / 2 + 0.03, -w / 2 + 0.06, h + 0.012), (-d / 2 + 0.06, w / 2 - 0.06, h + 0.06), STEEL)
    else:
        for sy in (-0.21, 0.21):
            b.fine.box((-0.22, sy - 0.16, h), (0.22, sy + 0.16, h + 0.012), DGLASS)
            b.fine.box((0.0, sy - 0.10, h + 0.012), (0.20, sy + 0.10, h + 0.05), TRIM)
            b.fine.box((0.20, sy - 0.015, h + 0.03), (0.34, sy + 0.015, h + 0.05), RUBBER)
    for k in range(4):
        b.fine.cyl((d / 2 + 0.005, -0.27 + k * 0.18, h - 0.07), (d / 2 + 0.03, -0.27 + k * 0.18, h - 0.07), 0.022, RUBBER, seg=10)
    b.emit.lamp_box((d / 2 + 0.03, 0.30, h - 0.10), (d / 2 + 0.035, 0.34, h - 0.06), "amber", LAMP_DIM)


def hood(b: SParts, w: float = 2.4, d: float = 1.0, z: float = 2.05, top: float = 3.4) -> None:
    """An extraction hood: a sloped steel canopy over a range line, a duct to the ceiling, a lit underside."""
    b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.26), STEEL)
    b.body.box((-d / 2 + 0.12, -w / 2 + 0.12, z + 0.26), (d / 2 - 0.12, w / 2 - 0.12, z + 0.5), STEEL)
    b.body.box((-0.25, -0.3, z + 0.5), (0.25, 0.3, top), STEEL)
    b.emit.lamp_box((-d / 2 + 0.1, -w / 2 + 0.15, z - 0.006), (d / 2 - 0.1, w / 2 - 0.15, z), "white_warm", LAMP)


def steel_sink_unit(b: SParts, w: float = 1.6, d: float = 0.75, h: float = 0.92) -> None:
    counter(b, w, d, h, STEEL, STEEL, True, False)
    for sy in (-w / 4, w / 4):
        b.fine.box((-d / 2 + 0.1, sy - 0.32, h - 0.02), (d / 2 - 0.1, sy + 0.32, h + 0.001), DGLASS)
        b.fine.cyl((-d / 2 + 0.06, sy, h), (-d / 2 + 0.06, sy, h + 0.32), 0.016, TRIM, seg=8)
        b.fine.cyl((-d / 2 + 0.06, sy, h + 0.32), (-d / 2 + 0.2, sy, h + 0.32), 0.016, TRIM, seg=8)


def pot(b: SParts, r: float = 0.16, h: float = 0.2) -> None:
    b.fine.cyl((0, 0, 0.0), (0, 0, h), r, STEEL, seg=14)
    b.fine.cyl((0, 0, h), (0, 0, h + 0.012), r * 1.06, TRIM, seg=14)
    b.fine.box((r, -0.02, h - 0.05), (r + 0.14, 0.02, h - 0.03), TRIM)


def monitor(b: SParts, w: float = 0.6, h: float = 0.36, tile: str = "scr_map", stand: bool = True) -> None:
    """A screen facing +x with a stand; the picture is a label tile of the atlas."""
    b.body.box((-0.02, -w / 2 - 0.02, 0.0), (0.02, w / 2 + 0.02, h + 0.04), TRIM)
    b.body.box((-0.016, -w / 2 - 0.006, 0.006), (0.016, w / 2 + 0.006, h + 0.034), DGLASS)
    b.emit.label((0.0165, 0.0, 0.02 + h / 2), w, h, (1, 0, 0), tile)
    if stand:
        b.fine.box((-0.12, -0.12, -0.02), (0.05, 0.12, 0.0), STRUCT)


def wall_screen(b: SParts, w: float, h: float, tile: str, frame_w: float = 0.05) -> None:
    """A framed wall display facing +x, its centre at the origin (z centre): the frame, a dark glass, the picture."""
    b.body.box((-0.06, -w / 2 - frame_w, -h / 2 - frame_w), (0.0, w / 2 + frame_w, h / 2 + frame_w), TRIM)
    b.body.box((-0.045, -w / 2, -h / 2), (0.002, w / 2, h / 2), DGLASS)
    b.emit.label((0.0025, 0.0, 0.0), w, h, (1, 0, 0), tile)
    b.emit.lamp_box((-0.058, -w / 2, h / 2 + frame_w), (-0.052, w / 2, h / 2 + frame_w + 0.012), "cool_dim", LAMP_DIM)


# ---------------------------------------------------------------------------------------------------------------- plants, decor
def planter(b: SParts, w: float = 1.0, d: float = 0.5, h: float = 0.45, plants: int = 3, seed: int = 5, tall: bool = False) -> None:
    """A planter box with real plants (ship_plants.planter_bed): origin at its centre on the floor, w along y."""
    import ship_plants as PL
    PL.planter_bed(b, w, d, h, seed, tall, density=0.45 + 0.2 * plants)


def potted_plant(b: SParts, h: float = 1.1, seed: int = 2) -> None:
    """A potted plant of about height h (a scanned plant in a pot of the ship: ship_plants): a palm for the tallest, a money tree, a syngonium, a snake plant, a zebra plant on a desk."""
    import ship_plants as PL
    if h >= 1.7:
        PL.floor_tree(b, "pachira_c", 0.3, scale=1.1, yaw=seed * 47.0)
    elif h >= 1.3:
        PL.floor_tree(b, "pachira_c" if seed % 2 else "ficus", 0.28, scale=0.95, yaw=seed * 53.0) if seed % 2 else PL.potted(b, "ficus", "tub", 0.28, 0.45, yaw=seed * 53.0)
    elif h >= 0.85:
        if seed % 3 == 0:
            PL.snake_plant(b, seed=seed)
        else:
            PL.potted(b, "syngonium", "bowl", 0.25, 0.34, yaw=seed * 61.0)
    else:
        PL.haworthia(b, yaw=seed * 40.0)


def lamp_standard(b: SParts, h: float = 1.5, cell: str = "white_warm") -> None:
    N.lamp_standard(b, h, cell)


def ceiling_light_panel(b: SParts, x0: float, x1: float, y0: float, y1: float, z: float, cell: str = "white_cool", mat: str = LAMP_HOT) -> None:
    """A luminous ceiling panel: a brushed ring frame (4 cm bars, 6 cm deep) with a bright lamp face recessed 2 cm inside it, flush at height z."""
    t = 0.04
    b.body.box((x0, y0, z - 0.06), (x1, y0 + t, z), TRIM)
    b.body.box((x0, y1 - t, z - 0.06), (x1, y1, z), TRIM)
    b.body.box((x0, y0 + t, z - 0.06), (x0 + t, y1 - t, z), TRIM)
    b.body.box((x1 - t, y0 + t, z - 0.06), (x1, y1 - t, z), TRIM)
    b.body.box((x0 + t, y0 + t, z - 0.025), (x1 - t, y1 - t, z - 0.01), STRUCT)
    b.emit.lamp_box((x0 + t, y0 + t, z - 0.04), (x1 - t, y1 - t, z - 0.032), cell, mat)


def pipe_run(b: SParts, p0, p1, r: float = 0.06, mat: str = TRIM, clamps: float = 1.2) -> None:
    """A straight pipe between two points with clamps every `clamps` m."""
    from mathutils import Vector
    a, c = Vector(p0), Vector(p1)
    b.fine.cyl(a, c, r, mat, seg=12)
    n = max(1, int((c - a).length / clamps))
    for k in range(n + 1):
        p = a + (c - a) * (k / n)
        b.fine.cyl(p - (c - a).normalized() * 0.02, p + (c - a).normalized() * 0.02, r * 1.25, STRUCT, seg=12)


def hazard_stripe(b: SParts, p, w: float, h: float, facing, up=(0, 0, 1)) -> None:
    b.emit.label(p, w, h, facing, "hazard_h", up=up)
