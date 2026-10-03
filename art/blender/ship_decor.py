"""ASN Aquila interior kit (ARTE-INTERNI): set dressing — the things that make a room look lived in: rugs, framed pictures, notice boards with their notes, mugs, a bowl of fruit, a stack of
books, a coffee table with what is on it, side tables with lamps, pendant lights, cushions, coat hooks. Every function builds ONE piece in its own frame (origin on the floor, x = front,
unless a function says it hangs on a wall: then the origin is the centre of its back face, x = out from the wall) into an SParts.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Rx, Ry, Rz, T
from ship_lib import (SWATCH, BEDDING, BRASS, CARPET_RUST, CARPET_SAND, CARPET_SLATE, CERAMIC, COMPOSITE, CORK, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, FRUIT, IVORY, LAMP, LAMP_DIM,
                      LAMINATE, LEATHER_NAVY, LEATHER_OX, LEATHER_TAN, OAK, PAPER, PLASTER_IVORY, STEEL, STRUCT, TRIM, WALNUT, WEAVE_RUST, WEAVE_SAND, WEAVE_SLATE, WEAVE_TEAL, SParts)

PICTURE_COLORS = ["navy", "teal", "mustard", "rust", "cream", "slate", "denim", "forest", "tan", "white", "oxblood"]


# ------------------------------------------------------------------------------------------------------------------------------- floor
def rug(b: SParts, w: float, d: float, field: str = CARPET_RUST, edge: str = CARPET_SAND, band: float = 0.16, pile: float = 0.014) -> None:
    """A rug centred on the origin (w along x, d along y): a field of one carpet with a border of another and a thin line between, 14 mm thick with rounded edges."""
    MK.rbox(b.soft, (-w / 2, -d / 2, 0.0), (w / 2, d / 2, pile), 0.004, edge, 2)
    MK.rbox(b.soft, (-w / 2 + band, -d / 2 + band, 0.001), (w / 2 - band, d / 2 - band, pile + 0.003), 0.004, field, 2)
    b.fine.box((-w / 2 + band * 0.5 - 0.006, -d / 2 + band * 0.5, pile), (w / 2 - band * 0.5 + 0.006, -d / 2 + band * 0.5 + 0.012, pile + 0.0035), STRUCT)
    b.fine.box((-w / 2 + band * 0.5 - 0.006, d / 2 - band * 0.5 - 0.012, pile), (w / 2 - band * 0.5 + 0.006, d / 2 - band * 0.5, pile + 0.0035), STRUCT)
    b.fine.box((-w / 2 + band * 0.5 - 0.006, -d / 2 + band * 0.5, pile), (-w / 2 + band * 0.5 + 0.006, d / 2 - band * 0.5, pile + 0.0035), STRUCT)
    b.fine.box((w / 2 - band * 0.5 - 0.006, -d / 2 + band * 0.5, pile), (w / 2 - band * 0.5 + 0.006, d / 2 - band * 0.5, pile + 0.0035), STRUCT)


# ------------------------------------------------------------------------------------------------------------------------------- walls
def picture(b: SParts, w: float, h: float, seed: int = 1, frame: str = WALNUT, kind: str = "bands") -> None:
    """A framed picture hanging on a wall facing +x (origin: the middle of its back face): a frame, a mount and an abstract canvas — bands of colour, a sun over a horizon, a
    grid of squares — in the ship's own tints."""
    rng = random.Random(seed)
    t = 0.03
    MK.rbox(b.body, (0.0, -w / 2, -h / 2), (t, w / 2, h / 2), 0.006, frame, 2)
    b.fine.swatch_box((t - 0.004, -w / 2 + 0.03, -h / 2 + 0.03), (t, w / 2 - 0.03, h / 2 - 0.03), "paper")
    iw, ih = w - 0.12, h - 0.12
    x = t - 0.002
    if kind == "bands":
        n = rng.randint(3, 5)
        y = -ih / 2
        for k in range(n):
            hh = ih / n * rng.uniform(0.7, 1.3)
            hh = min(hh, ih / 2 - y)
            if hh <= 0.01:
                break
            b.fine.swatch_box((x, -iw / 2, y), (x + 0.003, iw / 2, y + hh), rng.choice(PICTURE_COLORS))
            y += hh
    elif kind == "sun":
        b.fine.swatch_box((x, -iw / 2, -ih / 2), (x + 0.003, iw / 2, ih * 0.1), rng.choice(("navy", "slate", "denim")))
        b.fine.swatch_box((x, -iw / 2, ih * 0.1), (x + 0.003, iw / 2, ih / 2), rng.choice(("cream", "sand", "w_birch")))
        b.fine.swatch_cyl((x + 0.001, iw * 0.15, ih * 0.12), (x + 0.004, iw * 0.15, ih * 0.12), min(iw, ih) * 0.2, rng.choice(("rust", "orange", "red")), seg=20)
    else:                                                                    # squares
        n = 3
        for i in range(n):
            for j in range(n):
                b.fine.swatch_box((x, -iw / 2 + i * iw / n + 0.01, -ih / 2 + j * ih / n + 0.01), (x + 0.003, -iw / 2 + (i + 1) * iw / n - 0.01, -ih / 2 + (j + 1) * ih / n - 0.01),
                                  rng.choice(PICTURE_COLORS))


def notice_board(b: SParts, w: float = 1.2, h: float = 0.8, seed: int = 1) -> None:
    """A cork notice board in a steel frame with a dozen notes pinned to it (origin: the middle of the back face, facing +x)."""
    rng = random.Random(seed)
    b.body.box((0.0, -w / 2, -h / 2), (0.028, w / 2, h / 2), TRIM)
    b.fine.box((0.02, -w / 2 + 0.025, -h / 2 + 0.025), (0.03, w / 2 - 0.025, h / 2 - 0.025), CORK)
    for k in range(rng.randint(9, 14)):
        pw, ph = rng.uniform(0.07, 0.14), rng.uniform(0.09, 0.17)
        y = rng.uniform(-w / 2 + 0.05, w / 2 - 0.05 - pw)
        z = rng.uniform(-h / 2 + 0.05, h / 2 - 0.05 - ph)
        tint = rng.choice(("paper", "paper", "white", "sand", "teal", "yellow", "rose"))
        b.fine.swatch_box((0.03, y, z), (0.033, y + pw, z + ph), tint)
        b.fine.cyl((0.033, y + pw / 2, z + ph - 0.012), (0.037, y + pw / 2, z + ph - 0.012), 0.005, STEEL, seg=6)


def coat_hooks(b: SParts, n: int = 4, pitch: float = 0.18) -> None:
    """A rail of hooks on a wall (origin at the rail's middle, facing +x) with a jacket or two hanging."""
    w = n * pitch
    b.body.box((0.0, -w / 2, -0.03), (0.03, w / 2, 0.03), WALNUT)
    for k in range(n):
        y = -w / 2 + (k + 0.5) * pitch
        b.fine.cyl((0.03, y, 0.0), (0.075, y, 0.0), 0.007, STEEL, seg=6)
        b.fine.cyl((0.075, y, 0.0), (0.075, y, 0.04), 0.007, STEEL, seg=6)
        if k % 2 == 0:
            MK.rbox(b.soft, (0.05, y - 0.12, -0.55), (0.1, y + 0.12, -0.05), 0.03, (FABRIC_NAVY, FABRIC_GREY, FABRIC_SAND)[(k // 2) % 3], 2)


# ---------------------------------------------------------------------------------------------------------------------------- small things
def mug(b: SParts, mat: str = CERAMIC, h: float = 0.095, r: float = 0.04) -> None:
    """A mug standing on whatever is below (origin at its base centre), the handle towards +y."""
    MK.lathe(b.fine, [(r * 0.85, 0.0), (r, h * 0.05), (r, h), (r * 0.9, h), (r * 0.85, h * 0.9), (r * 0.8, h * 0.08)], (0, 0, 0), mat, seg=14)
    b.fine.cyl((0.0, r * 0.95, h * 0.22), (0.0, r + 0.025, h * 0.22), 0.0045, mat, seg=5)
    b.fine.cyl((0.0, r + 0.025, h * 0.22), (0.0, r + 0.025, h * 0.78), 0.0045, mat, seg=5)
    b.fine.cyl((0.0, r + 0.025, h * 0.78), (0.0, r * 0.95, h * 0.78), 0.0045, mat, seg=5)


def book_stack(b: SParts, n: int = 3, seed: int = 1, w: float = 0.2, d: float = 0.15) -> None:
    """A stack of books lying flat (origin at the base centre), each a little off the one below."""
    rng = random.Random(seed)
    z = 0.0
    for k in range(n):
        th = rng.uniform(0.018, 0.034)
        ww, dd = w * rng.uniform(0.85, 1.05), d * rng.uniform(0.9, 1.05)
        with b.at(T(rng.uniform(-0.012, 0.012), rng.uniform(-0.012, 0.012), z) @ Rz(rng.uniform(-12, 12))):
            b.soft.paint(MK.rbox(b.soft, (-dd / 2, -ww / 2, 0.0), (dd / 2, ww / 2, th), 0.004, SWATCH, 1), rng.choice(PICTURE_COLORS))
            b.fine.swatch_box((-dd / 2 + 0.006, -ww / 2 + 0.012, th * 0.1), (dd / 2 - 0.006, ww / 2 - 0.004, th * 0.9), "paper")
        z += th


def fruit_bowl(b: SParts, seed: int = 1, r: float = 0.14) -> None:
    """A shallow bowl of fruit: apples, oranges, a lemon (origin at the bowl's base centre)."""
    rng = random.Random(seed)
    MK.lathe(b.fine, [(r * 0.35, 0.0), (r * 0.4, 0.01), (r * 0.8, 0.04), (r, 0.07), (r * 0.95, 0.07), (r * 0.76, 0.045), (r * 0.32, 0.02)], (0, 0, 0), CERAMIC, seg=20)
    for k in range(7):
        a = k * 2.4
        rr = r * 0.45 * (0.3 if k == 0 else 1.0)
        c = (rr * math.cos(a), rr * math.sin(a), 0.07 + (0.02 if k == 0 else 0.0))
        rad = rng.uniform(0.032, 0.04)
        b.soft.paint(MK.puff(b.soft, c, (rad, rad, rad * 0.95), SWATCH, e=1.0, nu=10, nv=6), rng.choice(("f_apple", "f_apple", "f_orange", "f_lettuce", "f_banana")))


def cushion_pair(b: SParts, mat_a: str, mat_b: str, w: float = 0.42) -> None:
    """Two throw cushions leaning against a seat back (origin at the seat's back edge, +x forward)."""
    MK.puff(b.soft, (0.05, -0.22, 0.12), (0.06, w / 2, w / 2), mat_a, e=0.55, rot=Ry(-28.0) @ Rx(10.0))
    MK.puff(b.soft, (0.07, 0.2, 0.11), (0.06, w / 2 - 0.02, w / 2 - 0.02), mat_b, e=0.55, rot=Ry(-24.0) @ Rx(-12.0))


def coffee_table_set(b: SParts, w: float = 1.1, d: float = 0.6, h: float = 0.4, top: str = OAK, seed: int = 1) -> None:
    """A low table with what people leave on it: a stack of books, a mug, a small plant or a bowl."""
    import ship_furn2 as N
    N.low_table(b, w, d, h, top)
    rng = random.Random(seed)
    with b.at(T(rng.uniform(-0.1, 0.1), -w * 0.3, h)):
        book_stack(b, rng.randint(2, 4), seed)
    with b.at(T(0.05, w * 0.12, h)):
        mug(b, rng.choice((CERAMIC, LAMINATE, LEATHER_NAVY)))
    if rng.random() < 0.6:
        with b.at(T(-0.08, w * 0.34, h)):
            fruit_bowl(b, seed, 0.1)


def side_table(b: SParts, r: float = 0.24, h: float = 0.52, top: str = OAK, lamp: bool = True, seed: int = 1) -> None:
    """A round side table on a steel column and foot, with a small table lamp (a glowing shade) or a mug and a book."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.02), r * 0.75, STRUCT, seg=20)
    b.body.cyl((0, 0, 0.02), (0, 0, h - 0.04), 0.025, TRIM, seg=10)
    MK.rbox(b.body, (-r, -r, h - 0.04), (r, r, h), 0.014, top, 2)
    if lamp:
        b.fine.cyl((0, 0, h), (0, 0, h + 0.015), 0.07, STRUCT, seg=14)
        b.fine.cyl((0, 0, h + 0.015), (0, 0, h + 0.2), 0.01, BRASS, seg=8)
        b.emit.lamp_cyl((0, 0, h + 0.16), (0, 0, h + 0.3), 0.08, "white_warm", LAMP, seg=14, r2=0.1)
    else:
        with b.at(T(0.04, -0.06, h)):
            mug(b)
        with b.at(T(-0.06, 0.07, h)):
            book_stack(b, 2, seed, 0.18, 0.13)


def pendant(b: SParts, z_ceil: float, drop: float = 0.9, r: float = 0.22, cell: str = "white_warm", mat: str = BRASS) -> None:
    """A dome pendant hung from the ceiling at z_ceil on a thin rod, the light shining down out of the dome (origin on the floor under it)."""
    zt = z_ceil - drop
    b.fine.cyl((0, 0, zt + 0.12), (0, 0, z_ceil), 0.006, TRIM, seg=6)
    b.fine.cyl((0, 0, z_ceil - 0.04), (0, 0, z_ceil), 0.05, TRIM, seg=12)
    MK.lathe(b.body, [(0.001, zt + 0.2), (r * 0.25, zt + 0.19), (r * 0.7, zt + 0.12), (r, zt + 0.02), (r, zt), (r * 0.97, zt), (r * 0.66, zt + 0.1), (r * 0.2, zt + 0.17)], (0, 0, 0), mat, seg=24)
    b.emit.lamp_cyl((0, 0, zt - 0.004), (0, 0, zt + 0.004), r * 0.95, cell, LAMP, seg=24)


def wall_sconce(b: SParts, cell: str = "white_warm") -> None:
    """A wall light facing +x (origin: the middle of its back plate): a brushed plate and a half-cylinder shade throwing light up and down."""
    b.body.box((0.0, -0.05, -0.09), (0.02, 0.05, 0.09), TRIM)
    b.fine.box((0.02, -0.035, -0.07), (0.07, 0.035, 0.07), STRUCT)
    b.emit.lamp_box((0.07, -0.03, -0.065), (0.072, 0.03, 0.065), cell, LAMP_DIM)
    b.emit.lamp_box((0.02, -0.03, 0.09), (0.07, 0.03, 0.093), cell, LAMP_DIM)
    b.emit.lamp_box((0.02, -0.03, -0.093), (0.07, 0.03, -0.09), cell, LAMP_DIM)
