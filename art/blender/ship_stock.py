"""ASN Aquila interior kit (ARTE-INTERNI-2): what the ship's stores hold. The stores were racks of plain boxes in three paint colours; this is stock — cartons with their tape and their
labels, stacking totes with a hand slot, sacks that sag, drums with ridges, gas bottles in their colours, tool cases with latches, a pallet of cartons in shrink-wrap, cans in a tray — and the
rack and the pallet that carry them. Every item is built in its own frame (origin at the middle of its base, front +x) into an SParts and costs a few tens to a few hundred triangles
(a carton: 8). The finishes are the palette's (`MI_SHIP_Swatch`: one slot for every colour), so a store adds no material slot.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Rz, T
from ship_lib import CRATE_ORANGE, LAMP_DIM, RUBBER, STEEL, STRUCT, SWATCH, TRIM, WOOD, SParts, swatch_uv

CARTON_COLORS = ("tan", "sand", "tan", "cream", "w_pine")
TOTE_COLORS = ("blue", "grey3", "olive", "orange", "denim", "grey5")
SACK_COLORS = ("sand", "cream", "tan", "white", "w_birch")
BOTTLE_COLORS = {"o2": "forest", "n2": "grey2", "h2": "red", "air": "denim", "co2": "grey4", "water": "cyan"}
LABEL_TILES = ("small_00", "small_01", "small_02", "small_03", "small_04", "small_05", "small_09", "small_10", "small_11", "small_12", "small_15")


def _quad(b: SParts, pts, facing, color: str) -> None:
    f = b.soft.face(pts, SWATCH, facing)
    b.soft.paint([f], color)


def carton(b: SParts, w: float = 0.4, d: float = 0.3, h: float = 0.3, color: str = "tan", seed: int = 1, label: bool = True) -> None:
    """A cardboard carton (origin at the middle of its base, front +x, w along y): the visible faces in the palette's cardboard, a strip of tape along the top and down the front, a printed label."""
    rng = random.Random(seed)
    b.soft.swatch_slab((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), color, sides=True)
    _quad(b, [(-d / 2, -0.03, h + 0.0006), (d / 2, -0.03, h + 0.0006), (d / 2, 0.03, h + 0.0006), (-d / 2, 0.03, h + 0.0006)], (0, 0, 1), "w_teak")                 # the tape across the top
    _quad(b, [(d / 2 + 0.0006, -0.03, h * 0.55), (d / 2 + 0.0006, 0.03, h * 0.55), (d / 2 + 0.0006, 0.03, h), (d / 2 + 0.0006, -0.03, h)], (1, 0, 0), "w_teak")             # and down the front
    if label and w > 0.22 and h > 0.16:
        lw = min(w * 0.45, 0.2)
        b.emit.label_fit((d / 2 + 0.002, w * 0.2 * rng.choice((-1, 1)), h * 0.32), lw, rng.choice(LABEL_TILES), (1, 0, 0))


def tote(b: SParts, w: float = 0.6, d: float = 0.4, h: float = 0.3, color: str = "blue", seed: int = 1) -> None:
    """A stacking tote: a tub in `color` with a lid of pale grey, a hand slot and two clips on the front (the faces that can be seen: the front, the top, the flanks); 24 triangles."""
    b.soft.swatch_slab((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h - 0.04), color, sides=True)
    b.soft.swatch_slab((-d / 2 - 0.008, -w / 2 - 0.008, h - 0.04), (d / 2 + 0.008, w / 2 + 0.008, h), "grey3", sides=True)
    _quad(b, [(d / 2 + 0.0008, -0.09, h - 0.14), (d / 2 + 0.0008, 0.09, h - 0.14), (d / 2 + 0.0008, 0.09, h - 0.09), (d / 2 + 0.0008, -0.09, h - 0.09)], (1, 0, 0), "charcoal")
    for sy in (-w * 0.3, w * 0.3):
        _quad(b, [(d / 2 + 0.0112, sy - 0.015, h - 0.06), (d / 2 + 0.0112, sy + 0.015, h - 0.06), (d / 2 + 0.0112, sy + 0.015, h - 0.01), (d / 2 + 0.0112, sy - 0.015, h - 0.01)], (1, 0, 0), "charcoal")


def sack(b: SParts, w: float = 0.5, d: float = 0.35, h: float = 0.28, color: str = "sand", seed: int = 1) -> None:
    """A sack in a stack: a squashed superellipsoid with a gathered top and a printed band; about 90 triangles."""
    rng = random.Random(seed)
    b.soft.paint(MK.puff(b.soft, (0.0, 0.0, h * 0.5), (d / 2, w / 2, h / 2), SWATCH, e=0.55, nu=8, nv=5, rot=Rz(rng.uniform(-6, 6))), color)
    b.soft.paint(b.soft.cyl((0.0, -w * 0.16, h - 0.012), (0.0, w * 0.16, h + 0.012), 0.022, SWATCH, seg=5), "grey4")
    _quad(b, [(d / 2 * 0.9, -w * 0.2, h * 0.3), (d / 2 * 0.9, w * 0.2, h * 0.3), (d / 2 * 0.9, w * 0.2, h * 0.62), (d / 2 * 0.9, -w * 0.2, h * 0.62)], (1, 0, 0), rng.choice(("red", "navy", "forest")))


def drum(b: SParts, r: float = 0.28, h: float = 0.85, color: str = "blue", seed: int = 1) -> None:
    """A steel drum: a body with a rolled ring at the middle and a chime at each end, a bung plate on top; about 140 triangles."""
    prof = [(r * 0.94, 0.0), (r, 0.02), (r, h * 0.5 - 0.015), (r * 0.975, h * 0.5), (r, h * 0.5 + 0.015), (r, h - 0.02), (r * 0.94, h)]
    b.soft.paint(MK.lathe(b.soft, prof, (0, 0, 0), SWATCH, seg=10), color)
    b.soft.paint(b.soft.cyl((r * 0.4, 0.0, h), (r * 0.4, 0.0, h + 0.012), 0.04, SWATCH, seg=6), "grey3")


def gas_bottle(b: SParts, kind: str = "o2", h: float = 1.3, r: float = 0.11) -> None:
    """A gas bottle: a cylinder with a domed shoulder, a band of the gas's colour, a valve with a hand wheel; about 130 triangles."""
    col = BOTTLE_COLORS.get(kind, "grey2")
    prof = [(r * 0.9, 0.0), (r, 0.02), (r, h * 0.72), (r * 0.7, h * 0.86), (r * 0.28, h * 0.94), (r * 0.28, h * 0.955)]
    b.soft.paint(MK.lathe(b.soft, prof, (0, 0, 0), SWATCH, seg=8), "grey3")
    b.soft.paint(MK.lathe(b.soft, [(r * 1.004, h * 0.62), (r * 1.004, h * 0.74), (r * 0.72, h * 0.84)], (0, 0, 0), SWATCH, seg=8), col)
    b.soft.cyl((0, 0, h * 0.95), (0, 0, h * 1.0), 0.035, STEEL, seg=6)
    b.soft.cyl((0.0, -0.045, h * 1.0), (0.0, 0.045, h * 1.0), 0.008, STEEL, seg=4)


def tool_case(b: SParts, w: float = 0.6, d: float = 0.4, h: float = 0.22, color: str = "olive", seed: int = 1) -> None:
    """A hard case: the faces that are seen, two latches and a carrying handle on top; about 30 triangles."""
    b.soft.swatch_slab((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), color, sides=True)
    for sy in (-w * 0.3, w * 0.3):
        _quad(b, [(d / 2 + 0.0008, sy - 0.03, h * 0.35), (d / 2 + 0.0008, sy + 0.03, h * 0.35), (d / 2 + 0.0008, sy + 0.03, h * 0.68), (d / 2 + 0.0008, sy - 0.03, h * 0.68)], (1, 0, 0), "grey3")
    b.soft.swatch_slab((-0.03, -0.09, h), (0.03, 0.09, h + 0.014), "charcoal", sides=True)


def can_tray(b: SParts, n: int = 12, seed: int = 1, r: float = 0.035, h: float = 0.1) -> None:
    """A shrink-wrapped tray of tinned food, seen as a block of tins: a cardboard tray, the tins' block with a band of the brand's colour round it; about 30 triangles."""
    rng = random.Random(seed)
    cols = rng.sample(("red", "forest", "mustard", "denim", "olive", "plum"), 2)
    per_row = max(2, int(math.sqrt(n * 1.5)))
    rows = max(1, int(math.ceil(n / per_row)))
    w, d = per_row * 2 * r + 0.02, rows * 2 * r + 0.02
    b.soft.swatch_slab((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.02), "tan", sides=True)
    b.soft.swatch_slab((-d / 2 + 0.01, -w / 2 + 0.01, 0.02), (d / 2 - 0.01, w / 2 - 0.01, 0.02 + h), "grey5", sides=True)
    _quad(b, [(d / 2 - 0.0092, -w / 2 + 0.01, 0.045), (d / 2 - 0.0092, w / 2 - 0.01, 0.045), (d / 2 - 0.0092, w / 2 - 0.01, 0.02 + h * 0.8), (d / 2 - 0.0092, -w / 2 + 0.01, 0.02 + h * 0.8)], (1, 0, 0), cols[0])


def pallet(b: SParts, w: float = 1.2, d: float = 0.8) -> None:
    """A wooden pallet: three runners and a deck of seven boards with gaps (origin at the middle of its base, its top at 0.145); 80 triangles."""
    for sx in (-d / 2 + 0.05, 0.0, d / 2 - 0.05):
        b.soft.swatch_slab((sx - 0.045, -w / 2, 0.0), (sx + 0.045, w / 2, 0.1), "w_pine", sides=True)
    n = 7
    for k in range(n):
        y0 = -w / 2 + k * (w / n)
        b.soft.swatch_slab((-d / 2, y0 + 0.01, 0.1), (d / 2, y0 + w / n - 0.01, 0.145), "w_pine", sides=True)


def stacked_cartons(b: SParts, w: float = 1.1, d: float = 0.7, layers: int = 4, seed: int = 1, wrap: bool = True) -> None:
    """A pallet load: `layers` of cartons in a brick pattern on a pallet, wound in shrink-wrap (a pale film as a few thin flat bands on the faces), a strap on top. Origin on the pallet's base."""
    rng = random.Random(seed)
    pallet(b, w, d)
    ch = rng.choice((0.22, 0.26, 0.3))
    col = rng.choice(CARTON_COLORS)
    for L in range(layers):
        z = 0.145 + L * ch
        for i in range(2):
            for j in range(3 if L % 2 == 0 else 2):
                cw = w / (3 if L % 2 == 0 else 2) - 0.012
                with b.at(T(-d / 4 + i * d / 2, -w / 2 + (j + 0.5) * w / (3 if L % 2 == 0 else 2), z)):
                    carton(b, cw, d / 2 - 0.012, ch - 0.004, col, seed + L * 7 + i * 3 + j, label=(i == 1 and rng.random() < 0.7))
    top = 0.145 + layers * ch
    if wrap:
        for k in range(3):                                                                          # the film: three bands round the load, a hair proud of it
            z0 = 0.2 + k * (top - 0.26) / 3
            for (a0, a1, c0, c1, fac) in ((d / 2 + 0.003, d / 2 + 0.003, -w / 2 - 0.003, w / 2 + 0.003, (1, 0, 0)), (-d / 2 - 0.003, -d / 2 - 0.003, -w / 2 - 0.003, w / 2 + 0.003, (-1, 0, 0))):
                _quad(b, [(a0, c0, z0), (a1, c1, z0), (a1, c1, z0 + 0.12), (a0, c0, z0 + 0.12)], fac, "grey8")
            for sy, fy in ((w / 2 + 0.003, (0, 1, 0)), (-w / 2 - 0.003, (0, -1, 0))):
                _quad(b, [(-d / 2 - 0.003, sy, z0), (d / 2 + 0.003, sy, z0), (d / 2 + 0.003, sy, z0 + 0.12), (-d / 2 - 0.003, sy, z0 + 0.12)], fy, "grey8")
    b.soft.paint(b.soft.box((-d / 2 - 0.004, -0.015, top - 0.002), (d / 2 + 0.004, 0.015, top + 0.004), SWATCH), "charcoal")      # the strap


# --------------------------------------------------------------------------------------------------------------------------------------- the rack
def pick_item(rng: random.Random, kind: str, room_w: float, room_h: float, room_d: float):
    """The next piece of stock for a bay `room_w` wide (along y), `room_h` high and `room_d` deep, picked by `rng` in the style of the store `kind` (dry | cold | general): returns
    (function, arguments, the width it takes along y); the caller builds it centred on the run's next free spot."""
    pick = rng.random()
    s = rng.randrange(999)
    if kind == "cold":
        if pick < 0.5:
            w = min(room_w, rng.choice((0.5, 0.6)))
            return tote, (w, min(room_d, 0.4), min(room_h, rng.choice((0.28, 0.34))), rng.choice(("white", "cream", "grey1")), s), w
        if pick < 0.85:
            w = min(room_w, rng.choice((0.4, 0.5)))
            return carton, (w, min(room_d, 0.34), min(room_h, rng.choice((0.28, 0.34, 0.4))), rng.choice(("white", "cream", "cyan")), s), w
        return can_tray, (12, s), 0.34
    if kind == "dry":
        if pick < 0.42:
            w = min(room_w, rng.choice((0.4, 0.5, 0.6)))
            return carton, (w, min(room_d, rng.choice((0.3, 0.4))), min(room_h, rng.choice((0.26, 0.32, 0.4))), rng.choice(CARTON_COLORS), s), w
        if pick < 0.62:
            w = min(room_w, 0.6)
            return tote, (w, min(room_d, 0.4), min(room_h, 0.3), rng.choice(TOTE_COLORS), s), w
        if pick < 0.82:
            w = min(room_w, 0.55)
            return sack, (w, 0.36, min(room_h, 0.28), rng.choice(SACK_COLORS), s), w
        return can_tray, (12, s), 0.34
    if pick < 0.3:                                                                                  # general stores
        w = min(room_w, rng.choice((0.4, 0.5, 0.6)))
        return carton, (w, min(room_d, 0.36), min(room_h, rng.choice((0.26, 0.34, 0.42))), rng.choice(CARTON_COLORS), s), w
    if pick < 0.55:
        w = min(room_w, 0.6)
        return tote, (w, min(room_d, 0.4), min(room_h, 0.3), rng.choice(TOTE_COLORS), s), w
    if pick < 0.75:
        w = min(room_w, 0.62)
        return tool_case, (w, min(room_d, 0.4), min(room_h, 0.24), rng.choice(("olive", "orange", "charcoal", "grey3")), s), w
    if pick < 0.88 and room_h > 0.8:
        return drum, (0.26, min(room_h - 0.03, 0.85), rng.choice(("blue", "olive", "grey3", "red")), s), 0.58
    if room_h > 0.5:
        return gas_bottle, (rng.choice(("o2", "n2", "air", "co2")), min(room_h - 0.03, 1.3), 0.095), 0.24
    w = min(room_w, 0.5)
    return carton, (w, min(room_d, 0.36), min(room_h, 0.3), rng.choice(CARTON_COLORS), s), w


def fill_bay(b: SParts, rng: random.Random, kind: str, y0: float, y1: float, z: float, gap_h: float, depth: float, load: float = 0.8) -> None:
    """Stock along one deck of a rack or a shelf, from y0 to y1 at height z, with at most `gap_h` of headroom: runs of items with small gaps and the odd empty stretch."""
    y = y0
    while y < y1 - 0.1:
        if rng.random() > load:
            y += rng.uniform(0.2, 0.45)
            continue
        fn, args, wd = pick_item(rng, kind, y1 - y, gap_h, depth)
        if y + wd > y1:
            break
        with b.at(T(0.0, y + wd / 2, z)):
            fn(b, *args)
        y += wd + rng.uniform(0.015, 0.06)


def rack(b: SParts, w: float = 2.4, d: float = 0.9, h: float = 2.6, levels: int = 4, seed: int = 3, load: float = 0.8, kind: str = "dry") -> None:
    """A heavy stores rack facing +x: steel uprights on foot plates, orange beams (the colour of safety), a steel deck on each level, and stock on the levels: items of the store's `kind`
    (dry: cartons, totes, sacks, tinned food; cold: insulated cartons and totes; general: cartons, totes, cases, drums, gas bottles) in runs along the bay, a label on the lowest beam."""
    rng = random.Random(seed)
    for sx in (-d / 2, d / 2 - 0.06):
        for sy in (-w / 2, w / 2 - 0.06):
            b.body.box((sx, sy, 0.0), (sx + 0.06, sy + 0.06, h), STRUCT)
            b.fine.box((sx - 0.03, sy - 0.03, 0.0), (sx + 0.09, sy + 0.09, 0.012), TRIM)
    zs = [0.25 + k * (h - 0.3) / levels for k in range(levels)]
    for z in zs:
        for sx in (-d / 2, d / 2 - 0.05):
            b.body.box((sx, -w / 2, z), (sx + 0.05, w / 2, z + 0.09), CRATE_ORANGE)
        b.fine.box((-d / 2, -w / 2 + 0.06, z + 0.09), (d / 2, w / 2 - 0.06, z + 0.105), STEEL)
    for i, z in enumerate(zs):
        top = (zs[i + 1] if i + 1 < len(zs) else h) - 0.03
        fill_bay(b, rng, kind, -w / 2 + 0.08, w / 2 - 0.08, z + 0.105, top - z - 0.105, d - 0.1, load)
    b.emit.label_fit((d / 2 + 0.002, 0.0, zs[0] + 0.045), 0.5, "small_09", (1, 0, 0))


def cell_wall_rack(b: SParts, w: float = 2.4, d: float = 0.5, h: float = 2.0, seed: int = 1, kind: str = "dry") -> None:
    """A wall shelving unit of totes and cartons (origin on the floor at the middle of its back, front +x): a steel frame with five decks, stock in runs on each."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.02, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.03, h), STRUCT)
    rows = 5
    zs = [0.08 + k * (h - 0.12) / (rows - 1) for k in range(rows)]
    for z in zs:
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.02), STEEL)
    for i, z in enumerate(zs[:-1]):
        fill_bay(b, rng, kind, -w / 2 + 0.06, w / 2 - 0.06, z + 0.02, zs[i + 1] - z - 0.05, d - 0.06, 0.88)
