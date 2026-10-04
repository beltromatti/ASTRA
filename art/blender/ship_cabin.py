"""ASN Aquila interior kit (ARTE-INTERNI): the cabins. The crew's cabins (Deck 4, 6, 9), the officers' staterooms (Deck 3), the officers' single cabins (Deck 2, 4) and the suites share one
language: a partition of plaster with a wainscot (oak on the cabin's side, walnut on the passage's), an architrave round every hatch with its lit number and status lamp, a ceiling light
of its own in every cabin (the plan has a lamp for each: ship_spec.py) and a valance light over the window, a viewport on the outer wall with curtains, a bed or a bunk with a nightstand
and its lamp, a desk with a screen, a lamp, a mug and a plant, a wardrobe, a basin, a rug, a picture, the things a person leaves about. Every cabin is dressed from its own seed, so
no two are alike. The layouts (where the bed, the desk, the wardrobe stand) are the ones of the rooms before: the sleepers' places (ship_spec.py) are on the beds.
"""
from __future__ import annotations

import math
import random

import ship_decor as DC
import ship_decor2 as D2
import ship_furniture as F
import ship_furniture2 as G
import ship_furniture4 as F4
import ship_furniture8 as K8
import ship_mk as MK
import ship_plants as PL
from bridge3_lib import Rz, T
from ship_lib import (BRASS, CARPET_RUST, CARPET_SAND, CARPET_SLATE, CERAMIC, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, LAMINATE, LAMP, LAMP_DIM, LEATHER_NAVY, LEATHER_OX,
                      OAK, PLASTER_IVORY, RUBBER, STEEL, STRUCT, TRIM, WALNUT, WOOD, SParts)
from ship_rooms import WF, WS, place

DW, DH = 0.95, 2.1                                            # a cabin's hatch
BLANKETS = (FABRIC_NAVY, FABRIC_RUST, FABRIC_GREY, FABRIC_SAND)
CURTAINS = (FABRIC_SAND, FABRIC_GREY, FABRIC_RUST, FABRIC_NAVY)
RUGS = ((CARPET_SAND, FABRIC_SAND), (CARPET_SLATE, FABRIC_SAND), (CARPET_RUST, FABRIC_SAND), (CARPET_SLATE, FABRIC_RUST))
BOOKC = ["navy", "oxblood", "forest", "mustard", "slate", "teal", "rust", "denim", "plum"]


def pick(seq, k: int):
    return seq[k % len(seq)]


# ------------------------------------------------------------------------------------------------------------------------------------------------------ partitions
def partition(b: SParts, axis: str, pos: float, a0: float, a1: float, H: float, openings=(), hall: int = 0, t: float = 0.12, wain: float = 1.05) -> None:
    """A partition wall between two rooms: a plaster core `t` thick and a finish 1.5 cm thick on both faces — oak wainscot with a brass rail on a cabin's face, walnut on a passage's
    (`hall` = +1 / -1: the face towards +/- of the wall's normal is the passage's; 0: both are cabins'), a skirting, an architrave round every opening. axis 'y': the wall runs along y at
    x = pos from y = a0 to a1 (normal x); axis 'x': along x at y = pos. openings = [(centre, width, height)] along the wall."""
    def box(fb, s0: float, s1: float, a: float, c: float, z0: float, z1: float, mat: str) -> None:
        if z1 - z0 < 1e-4 or c - a < 1e-4:
            return
        if axis == "y":
            fb.box((pos + s0, a, z0), (pos + s1, c, z1), mat)
        else:
            fb.box((a, pos + s0, z0), (c, pos + s1, z1), mat)

    spans = sorted((yc - w / 2, yc + w / 2, h) for (yc, w, h) in openings)
    pieces = []                                                    # (a, c, z0): solid from z0 up to the ceiling
    cur = a0
    for (sa, sb, h) in spans:
        if sa > cur:
            pieces.append((cur, sa, 0.0))
        pieces.append((sa, sb, h))
        cur = sb
    if cur < a1:
        pieces.append((cur, a1, 0.0))
    for (a, c, z0) in pieces:
        box(b.soft, -t / 2, t / 2, a, c, z0, H, PLASTER_IVORY)
        for s in (-1, 1):
            passage = bool(hall) and s == hall
            lo = WALNUT if passage else OAK
            s0, s1 = (t / 2, t / 2 + 0.015) if s > 0 else (-t / 2 - 0.015, -t / 2)
            if z0 < wain:
                box(b.soft, s0, s1, a, c, z0, wain, lo)
                if z0 == 0.0:
                    box(b.fine, s0 - 0.004 if s < 0 else s0, s1 + 0.004 if s > 0 else s1, a, c, 0.0, 0.09, STRUCT if passage else WALNUT)             # the skirting
                box(b.fine, s0 - 0.003 if s < 0 else s0, s1 + 0.003 if s > 0 else s1, a, c, wain - 0.012, wain + 0.012, BRASS)                         # the rail
            box(b.soft, s0, s1, a, c, max(z0, wain + 0.012), H, PLASTER_IVORY)
    for (yc, w, h) in openings:                                     # the architrave on both faces and the threshold
        for s in (-1, 1):
            s0, s1 = (t / 2, t / 2 + 0.028) if s > 0 else (-t / 2 - 0.028, -t / 2)
            box(b.fine, s0, s1, yc - w / 2 - 0.06, yc - w / 2, 0.0, h + 0.06, WALNUT)
            box(b.fine, s0, s1, yc + w / 2, yc + w / 2 + 0.06, 0.0, h + 0.06, WALNUT)
            box(b.fine, s0, s1, yc - w / 2, yc + w / 2, h, h + 0.06, WALNUT)
        box(b.fine, -t / 2, t / 2, yc - w / 2, yc + w / 2, 0.0, 0.012, BRASS)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the cabin's own pieces
def sky(b: SParts, w: float, h: float, seed: int = 1, planet: float = 0.0, density: float = 16.0) -> None:
    """The view out of a viewport (origin: the middle of its back face, facing +x): a deep blue backdrop with a field of stars — a few big, many small, the small ones denser along a
    diagonal band (the galaxy's arm) — each a tiny lamp; w x h is the clear size. `planet` > 0: the limb of a planet rises from the bottom edge to that fraction of the height at the
    middle (a disc of deep blue under a bright rim of atmosphere, built of thin columns)."""
    rng = random.Random(seed)
    b.soft.swatch_box((0.0, -w / 2, -h / 2), (0.006, w / 2, h / 2), "navy")
    n = max(24, int(w * h * density))
    for k in range(n):
        if k < n * 0.62:                                      # along the band: y = 0.8 z (w / h) plus noise
            z = rng.uniform(-h / 2 + 0.03, h / 2 - 0.03)
            y = max(-w / 2 + 0.03, min(w / 2 - 0.03, (z / h) * w * 0.8 + rng.gauss(0.0, w * 0.1)))
        else:
            y, z = rng.uniform(-w / 2 + 0.03, w / 2 - 0.03), rng.uniform(-h / 2 + 0.03, h / 2 - 0.03)
        s = rng.choice((0.006, 0.006, 0.008, 0.008, 0.011, 0.016))
        b.emit.lamp_box((0.006, y, z), (0.0075, y + s, z + s), rng.choice(("white_cool", "ice", "white_dim", "cool_dim", "white_warm")), LAMP_DIM)
    if planet > 0.0:
        sag = planet * h
        R = (w * w / 4 + sag * sag) / (2 * sag)
        cz = -h / 2 + sag - R
        m = max(28, int(w * 14))
        for i in range(m):
            y0, y1 = -w / 2 + w * i / m, -w / 2 + w * (i + 1) / m
            ym = (y0 + y1) / 2
            zt = cz + math.sqrt(max(R * R - ym * ym, 0.0))
            if zt - 0.03 > -h / 2:
                b.emit.lamp_box((0.0062, y0, -h / 2), (0.0072, y1, zt - 0.02), "command_dim", LAMP_DIM)
                b.emit.lamp_box((0.0062, y0, zt - 0.025), (0.0074, y1, zt), "cyan_dim", LAMP_DIM)


def viewport(b: SParts, w: float = 2.4, h: float = 0.9, cloth: str = FABRIC_SAND, seed: int = 1, planet: float = 0.0) -> None:
    """A window onto space on the outer wall (origin: the middle of its back face, facing +x): a walnut frame, the star field in it, an oak sill, a brass rod with two pleated curtains."""
    t = 0.045
    b.body.box((0.0, -w / 2, -h / 2), (0.05, w / 2, -h / 2 + t), WALNUT)
    b.body.box((0.0, -w / 2, h / 2 - t), (0.05, w / 2, h / 2), WALNUT)
    b.body.box((0.0, -w / 2, -h / 2 + t), (0.05, -w / 2 + t, h / 2 - t), WALNUT)
    b.body.box((0.0, w / 2 - t, -h / 2 + t), (0.05, w / 2, h / 2 - t), WALNUT)
    with b.at(T(0.01, 0.0, 0.0)):
        sky(b, w - 2 * t, h - 2 * t, seed, planet)
    b.fine.box((0.0, -w / 2 - 0.05, -h / 2 - 0.045), (0.15, w / 2 + 0.05, -h / 2 - 0.012), OAK)                      # the sill
    zt, zb = h / 2 + 0.16, -h / 2 - 0.2
    b.fine.cyl((0.1, -w / 2 - 0.34, zt), (0.1, w / 2 + 0.34, zt), 0.011, BRASS, seg=8)
    for sy in (-1, 1):                                                                                          # two curtains, each a row of slim folds in two depths
        n, pw = 9, 0.045
        for j in range(n):
            y0 = (w / 2 + 0.01 + j * pw) if sy > 0 else (-w / 2 - 0.01 - (j + 1) * pw)
            off = 0.016 * math.sin(j * 1.9)
            b.soft.box((0.08 + off, y0, zb), (0.1 + off, y0 + pw, zt - 0.012), cloth)


def cabin_light(b: SParts, x0: float, x1: float, y0: float, y1: float, H: float, cell: str = "white_warm") -> None:
    """The light of a cabin: a recessed panel in a brushed frame."""
    xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
    px, py = 0.55, 0.26
    b.body.box((xc - px - 0.04, yc - py - 0.04, H - 0.05), (xc + px + 0.04, yc + py + 0.04, H), TRIM)
    b.body.box((xc - px, yc - py, H - 0.055), (xc + px, yc + py, H - 0.045), STRUCT)
    b.emit.lamp_box((xc - px, yc - py, H - 0.06), (xc + px, yc + py, H - 0.055), cell, LAMP)


def valance(b: SParts, sgn: int, xo: float, y0: float, y1: float, H: float, depth: float = 0.22) -> None:
    """A soffit along the outer wall with a strip of warm light hidden behind it (it washes the wall and the window): sgn = +1 when the room lies to +x of the wall."""
    xa, xb = xo, xo + sgn * depth
    b.body.box((min(xa, xb), y0, H - 0.16), (max(xa, xb), y1, H - 0.1), PLASTER_IVORY)
    xl = xo + sgn * 0.02
    b.emit.lamp_box((min(xl, xl + sgn * 0.12), y0 + 0.05, H - 0.105), (max(xl, xl + sgn * 0.12), y1 - 0.05, H - 0.1), "warm_dim", LAMP_DIM)


def nightstand(b: SParts, seed: int = 1) -> None:
    """A bedside table 0.4 x 0.4 x 0.5 facing +x: a walnut carcase on a recessed plinth, two drawers with brass knobs, on top a lamp with a glowing shade, a clock and a book."""
    rng = random.Random(seed)
    b.body.box((-0.17, -0.17, 0.0), (0.17, 0.17, 0.06), STRUCT)
    MK.rbox(b.soft, (-0.2, -0.2, 0.06), (0.2, 0.2, 0.5), 0.01, WALNUT, 2)
    for z0, z1 in ((0.30, 0.46), (0.10, 0.27)):
        b.fine.box((0.2, -0.17, z0), (0.212, 0.17, z1), OAK)
        b.fine.box((0.212, -0.04, (z0 + z1) / 2 - 0.008), (0.235, 0.04, (z0 + z1) / 2 + 0.008), BRASS)
    z = 0.5
    b.fine.cyl((-0.1, -0.08, z), (-0.1, -0.08, z + 0.012), 0.065, STRUCT, seg=14)
    b.fine.cyl((-0.1, -0.08, z + 0.012), (-0.1, -0.08, z + 0.2), 0.008, BRASS, seg=8)
    b.emit.lamp_cyl((-0.1, -0.08, z + 0.15), (-0.1, -0.08, z + 0.27), 0.07, "warm_dim", LAMP, seg=14, r2=0.095)
    b.soft.swatch_box((0.02, 0.06, z), (0.14, 0.16, z + 0.022), pick(BOOKC, rng.randrange(len(BOOKC))))
    b.soft.swatch_box((0.03, 0.065, z + 0.022), (0.13, 0.155, z + 0.04), "paper")
    b.fine.box((0.09, -0.15, z), (0.13, -0.07, z + 0.045), STRUCT)                                               # an alarm clock
    b.emit.lamp_box((0.13, -0.14, z + 0.012), (0.132, -0.08, z + 0.034), "cyan_dim", LAMP_DIM)


def desk_set(b: SParts, seed: int = 1, plant: bool = True) -> None:
    """What stands on a desk (origin: the middle of the desk top, front = +x towards the sitter): a flat screen on a stand, a keyboard, an articulated lamp, a mug, a stack of books,
    a small plant."""
    rng = random.Random(seed)
    b.fine.box((-0.2, -0.1, 0.0), (-0.1, 0.1, 0.012), STRUCT)
    b.fine.box((-0.17, -0.02, 0.012), (-0.14, 0.02, 0.12), TRIM)
    b.body.box((-0.19, -0.27, 0.11), (-0.15, 0.27, 0.43), STRUCT)
    b.emit.label((-0.148, 0.0, 0.27), 0.5, 0.28, (1, 0, 0), rng.choice(("scr_data", "scr_ship", "scr_news", "scr_data")))
    b.soft.box((0.0, -0.2, 0.0), (0.16, 0.2, 0.016), RUBBER)                                                       # the keyboard
    b.fine.box((0.19, 0.22, 0.0), (0.23, 0.26, 0.012), STRUCT)                                                      # a mouse
    b.fine.cyl((-0.1, -0.4, 0.0), (-0.1, -0.4, 0.015), 0.07, STRUCT, seg=14)                                        # the lamp: base, two arms, a shade
    b.fine.cyl((-0.1, -0.4, 0.015), (-0.04, -0.37, 0.3), 0.007, STEEL, seg=6)
    b.fine.cyl((-0.04, -0.37, 0.3), (0.05, -0.33, 0.4), 0.007, STEEL, seg=6)
    b.emit.lamp_cyl((0.04, -0.33, 0.39), (0.12, -0.31, 0.34), 0.03, "white_warm", LAMP, seg=12, r2=0.06)
    with b.at(T(0.06, 0.36, 0.0)):
        DC.mug(b, rng.choice((CERAMIC, LAMINATE, LEATHER_NAVY)))
    with b.at(T(-0.05, 0.3, 0.0) @ Rz(rng.uniform(-15, 15))):
        DC.book_stack(b, rng.randint(2, 4), seed, 0.2, 0.15)
    if plant:
        with b.at(T(0.0, -0.2, 0.0)):
            PL.desk_plant(b, seed)


def boots(b: SParts) -> None:
    """A pair of boots by the wardrobe (origin: between them, toes towards +x): a foot and a shaft each, in leather."""
    for sy in (-0.1, 0.1):
        b.soft.box((-0.12, sy - 0.05, 0.0), (0.12, sy + 0.05, 0.07), LEATHER_OX)
        b.soft.box((-0.13, sy - 0.045, 0.06), (-0.04, sy + 0.045, 0.24), LEATHER_OX)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ one cabin
def fit_cabin(b: SParts, side: int, k: int, xo: float, y_lo: float, y_hi: float, wall_lo: float, wall_hi: float, H: float, officer: bool, seed: int) -> None:
    """Furnish one cabin of the 20 x 16 block: `side` 0 (the outer wall at x = xo, the hall to +x) or 1 (mirrored), k the cabin's number along the side; y_lo / y_hi where the furniture
    stops, wall_lo / wall_hi the finished faces of the walls on either end (the sleepers' places are on the bed: ship_spec.py)."""
    rng = random.Random(seed)
    sgn = 1 if side == 0 else -1
    yaw = 0 if side == 0 else 180                                   # facing the room
    yaw_in = 180 if side == 0 else 0                                # facing the outer wall
    blanket = pick(BLANKETS, k + side)
    cloth = pick(CURTAINS, k + side)
    rug = pick(RUGS, k + side * 2 + (1 if officer else 0))
    if officer:                                                     # the bed (the sleeper's place is on it), the nightstand at its head, the viewport over both
        place(b, xo + sgn * 1.14, y_lo + 0.55, yaw, K8.officer_bed, 1.0, 2.1, blanket)
        place(b, xo + sgn * 0.22, y_lo + 1.27, yaw, nightstand, seed)
        place(b, xo, y_lo + 1.95, yaw, viewport, 2.9, 0.9, cloth, seed, 0.32 if seed % 3 else 0.0, z=1.65)
    else:
        place(b, xo + sgn * 1.09, y_lo + 0.5, yaw, G.bunk_bed, 2.05, 0.95, 2, blanket, seed)
        place(b, xo + sgn * 0.22, y_lo + 1.2, yaw, nightstand, seed)
        place(b, xo, y_hi - 0.85, yaw, viewport, 1.3, 0.8, cloth, seed, z=1.6)
    valance(b, sgn, xo, y_lo + 0.1, y_hi - 0.1, H)
    cabin_light(b, xo + sgn * 0.9, xo + sgn * 3.8, y_lo + 0.3, y_hi - 0.3, H, "white_warm")
    place(b, xo + sgn * 0.35, y_hi - 0.75, yaw_in, F.desk, 1.0, 0.6, 0.75, WOOD, True)                         # the desk by the window, its things, the chair
    place(b, xo + sgn * 0.35, y_hi - 0.75, yaw, desk_set, seed, officer, z=0.75)
    place(b, xo + sgn * 1.05, y_hi - 0.75 + rng.uniform(-0.05, 0.05), yaw_in + rng.uniform(-14, 14), F.chair, FABRIC_GREY)
    place(b, xo + sgn * 3.6, y_lo + 0.29, 90, G.wardrobe, 0.9, 0.55, 2.0)                                       # the wardrobe, boots, coats, the basin, the rug, pictures
    place(b, xo + sgn * 2.85, y_lo + 0.45, rng.uniform(70, 110), boots)
    place(b, xo + sgn * 2.4, wall_lo + 0.0, 90, DC.coat_hooks, 3, 0.2, z=1.65)
    place(b, xo + sgn * 2.4, y_hi - 0.27, -90, G.vanity, 0.9, 0.5)
    place(b, xo + sgn * 2.6, (y_lo + y_hi) / 2, yaw, G.rug, 1.8, 1.6, rug[0], rug[1])
    place(b, xo + sgn * 1.9, wall_hi, -90, DC.picture, 0.5, 0.38, seed + 3, WALNUT, ("sun", "squares", "bands")[seed % 3], z=1.5)
    if not officer:
        place(b, xo + sgn * 1.7, wall_lo, 90, DC.picture, 0.55, 0.42, seed, WALNUT, ("bands", "sun", "squares")[seed % 3], z=1.45)
        place(b, xo + sgn * 2.2, y_lo + 1.5, rng.uniform(80, 100), F4.duffel, 0.8, 0.18, pick((FABRIC_SAND, FABRIC_GREY, FABRIC_NAVY), k))
    # ARTE-INTERNI-2: what the person keeps: photographs on the desk, an armchair and a lamp in the free corner, and in an officer's cabin a shelf over the bed (books, a photograph, the ship in
    # miniature) and, in some, a guitar by the wardrobe or a shadow box of medals
    place(b, xo + sgn * 0.2, y_hi - 0.38, yaw_in, D2.photo_frames, 3, seed, z=0.75)
    place(b, xo + sgn * 3.15, y_hi - 0.85, yaw_in + sgn * 38.0, F.armchair, pick((FABRIC_SAND, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST), k + 1))
    place(b, xo + sgn * 3.72, y_hi - 0.3, 0, F.lamp_standard, 1.45)
    if officer:
        place(b, xo + sgn * 1.3, wall_lo, 90, D2.wall_shelf, 1.4, seed + 9, z=1.5)
        if seed % 3 == 0:
            place(b, xo + sgn * 3.0, wall_lo + 0.12, 90 + rng.uniform(-6, 6), D2.guitar)
        elif seed % 3 == 1:
            place(b, xo + sgn * 2.65, wall_lo, 90, D2.medal_frame, 0.5, 0.35, seed, z=1.75)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the block
def quarters_block(b: SParts, spec: dict, officer: bool, cab_y: tuple, cab_xl: float, cab_xr: float, seed0: int = 0) -> None:
    """The 20 x 16 block of eight cabins (four a side) round a commons hall: the partitions, the hatches with their number and status lamp, the cabins; the hall is dressed by the caller."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for side, xw in ((0, cab_xl), (1, cab_xr)):
        sgn = 1 if side == 0 else -1
        partition(b, "y", xw, WF, yf, H, [(yc, DW, DH) for yc in cab_y], hall=sgn)
        for k, yc in enumerate(cab_y):
            xh = xw + sgn * 0.075                                                                             # the wall's finished face
            b.emit.lamp_box((min(xh, xh + sgn * 0.004), yc + DW / 2 + 0.1, 1.45), (max(xh, xh + sgn * 0.004), yc + DW / 2 + 0.16, 1.52), "green", LAMP_DIM)
            b.emit.label_fit((xw + sgn * 0.0755, yc, 2.34), 0.30, f"cabin_{k + 1 + 4 * side:02d}", (sgn, 0, 0))
        for yw in (4.0, 8.0, 12.0):
            partition(b, "x", yw, xl if side == 0 else xw, xw if side == 0 else xr, H, (), hall=0)
        xo = xl if side == 0 else xr
        for k, yc in enumerate(cab_y):
            y_lo = 0.06 if k == 0 else yc - 2.0 + 0.06
            y_hi = yf if k == 3 else yc + 2.0 - 0.06
            wall_lo = WF if k == 0 else yc - 2.0 + 0.075
            wall_hi = yf if k == 3 else yc + 2.0 - 0.075
            fit_cabin(b, side, k, xo, y_lo, y_hi, wall_lo, wall_hi, H, officer, seed0 + side * 4 + k)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the commons hall
def hall_dress(b: SParts, spec: dict, officer: bool, cab_y: tuple, cab_xl: float, cab_xr: float) -> None:
    """The commons hall between the two rows of cabins (x 5..15 of the 20 x 16 block): a long runner down the middle, a seating group on a rug round a coffee table with its books and its mug
    (two sofas, two armchairs, floor lamps), a dining table at the far end under two pendants with a place laid for each chair, a sideboard with a coffee machine and a shelf, pictures on
    the partitions between the hatches, a notice board, plants, the screens."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    yf = D - WS - WF
    xm = (cab_xl + cab_xr) / 2
    place(b, xm, 8.0, 0, DC.rug, 2.4, 14.4, CARPET_SLATE, FABRIC_SAND, 0.12)                                       # the runner
    place(b, xm, 9.9, 0, DC.rug, 4.8, 4.4, CARPET_RUST, FABRIC_SAND)
    place(b, xm, 9.9, 0, DC.coffee_table_set, 1.3, 0.75, 0.4, OAK, 7 + int(officer))
    place(b, xm, 11.3, -90, F.sofa, 2.6, LEATHER_NAVY if officer else FABRIC_NAVY)
    place(b, xm, 8.5, 90, F.sofa, 2.6, LEATHER_NAVY if officer else FABRIC_NAVY)
    place(b, xm + 2.15, 9.9, 180, F.armchair, FABRIC_SAND)
    place(b, xm - 2.15, 9.9, 0, F.armchair, FABRIC_SAND)
    place(b, xm + 2.1, 11.7, 0, F.lamp_standard, 1.55, "white_warm")
    place(b, xm - 2.1, 8.1, 0, F.lamp_standard, 1.55, "white_warm")
    # the dining table at the far end under two pendants, a place laid for every chair
    place(b, xm, 14.0, 0, F.table, 3.0, 0.9, 0.75, OAK, TRIM, False)
    for x in (xm - 1.0, xm, xm + 1.0):
        place(b, x, 13.0, 90, F.chair, FABRIC_RUST)
        place(b, x, 15.0, -90, F.chair, FABRIC_RUST)
        for yy, yw in ((13.28, 90), (14.72, -90)):
            place(b, x, yy, yw, DC.table_setting, int(x * 3 + yy), z=0.75)
    for x in (xm - 0.9, xm + 0.9):
        place(b, x, 14.0, 0, DC.pendant, H, 0.8, 0.2)
    place(b, xm, 14.0, 0, DC.fruit_bowl, 4, 0.14, z=0.75)
    # sideboard and shelf on the far wall
    place(b, xm - 3.4, yf - 0.3, -90, F.counter, 2.4, 0.5, 0.9, WALNUT, OAK, True, False)
    place(b, xm - 3.4, yf - 0.3, -90, G.coffee_machine, z=0.9)
    place(b, xm + 3.4, yf - 0.19, -90, F.shelf, 1.6, 0.34, 2.0, 5, WALNUT, True, 3, True)
    place(b, xm, yf - 0.02, -90, F.wall_screen, 2.0, 1.1, "scr_news", z=1.9)
    # the partitions between the hatches: pictures, a notice board; the screens by the door
    for side, xw in ((0, cab_xl), (1, cab_xr)):
        sgn = 1 if side == 0 else -1
        for k, yw in enumerate((4.0, 8.0, 12.0)):
            place(b, xw + sgn * 0.075, yw, 0 if side == 0 else 180, DC.picture, 0.9, 0.6, 11 + k + side * 3, WALNUT, ("bands", "sun", "squares")[(k + side) % 3], z=1.75)
    place(b, cab_xl + 0.075, 0.9, 0, DC.notice_board, 0.9, 0.7, 3, z=1.65)
    place(b, xm + 2.6, WF + 0.02, 90, F.wall_screen, 2.2, 1.2, "scr_sched", z=1.8)
    place(b, xm - 2.6, WF + 0.02, 90, F.wall_screen, 2.2, 1.2, "scr_map", z=1.8)
    # plants: two money trees at the far corners of the hall, a green plant at each near corner and by the partitions
    for x in (cab_xl + 0.8, cab_xr - 0.8):
        place(b, x, yf - 0.8, 0, F.potted_plant, 1.9, int(x))
    for (x, y) in ((cab_xl + 0.7, 0.85), (cab_xr - 0.7, 0.85), (cab_xl + 0.7, 7.9), (cab_xr - 0.7, 7.9)):
        place(b, x, y, 0, F.potted_plant, 1.0, int(x + y))


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the officers' single cabins
def single_row(b: SParts, spec: dict, seed0: int = 40) -> None:
    """24 x 4: six single cabins in a row, each 4 m wide and 2.8 m deep, behind a gallery 0.9 m wide along the corridor's wall (the room's one door opens into the gallery; every cabin has
    its own hatch off it). A cabin: the bed along the far wall with its head at the left partition and a nightstand, a window over the bed and the desk, a desk with its screen, lamp and
    plant at the right, a wardrobe and a basin on the gallery's wall, a rug, a light of its own."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    yg = 0.9                                                                  # the gallery wall's centre line
    y0 = yg + 0.075                                                           # its cabin face
    partition(b, "x", yg, xl, xr, H, [(2.0 + 4.0 * k, DW, DH) for k in range(6)], hall=-1)
    for k in range(1, 6):
        partition(b, "y", 4.0 * k, yg, yf, H, (), hall=0)
    place(b, L / 2, 0.5, 0, DC.rug, L - 1.4, 0.62, CARPET_SLATE, FABRIC_SAND, 0.1)                                    # the gallery's runner, its light and its pictures
    b.emit.lamp_box((xl + 1.0, 0.36, H - 0.05), (xr - 1.0, 0.44, H - 0.044), "warm_dim", LAMP_DIM)
    for k in range(6):
        xh = 2.0 + 4.0 * k
        yh = yg - 0.075
        b.emit.lamp_box((xh + DW / 2 + 0.09, yh - 0.004, 1.45), (xh + DW / 2 + 0.15, yh, 1.52), "green", LAMP_DIM)
        b.emit.label_fit((xh, yg - 0.0755, 2.34), 0.30, f"cabin_{k + 7:02d}", (0, -1, 0))
        if k > 0:
            place(b, 4.0 * k, yg - 0.075, -90, DC.picture, 0.8, 0.5, seed0 + k, WALNUT, ("bands", "sun", "squares")[k % 3], z=1.75)
    for k in range(6):
        seed = seed0 + k
        rng = random.Random(seed)
        x0 = xl if k == 0 else 4.0 * k + 0.075
        x1 = xr if k == 5 else 4.0 * (k + 1) - 0.075
        blanket = pick(BLANKETS, k)
        place(b, x0 + 1.14, yf - 0.55, 0, K8.officer_bed, 1.0, 2.1, blanket)                                  # the bed (the sleeper's place is on it)
        place(b, x0 + 0.22, yf - 1.27, 0, nightstand, seed)
        place(b, x0 + 2.0, yf, -90, viewport, 2.4, 0.9, pick(CURTAINS, k), seed, z=1.65)
        place(b, x1 - 0.8, yf - 0.3, 90, F.desk, 1.0, 0.6, 0.75, WOOD, True)
        place(b, x1 - 0.8, yf - 0.3, -90, desk_set, seed, True, z=0.75)
        place(b, x1 - 0.8 + rng.uniform(-0.05, 0.05), yf - 1.0, 90 + rng.uniform(-14, 14), F.chair, FABRIC_GREY)
        place(b, x0 + 3.1, y0 + 0.29, 90, G.wardrobe, 0.9, 0.55, 2.0)
        place(b, x0 + 0.8, y0 + 0.27, 90, G.vanity, 0.9, 0.5)
        place(b, x0 + 2.0, 2.15, 0, G.rug, 1.6, 1.4, *pick(RUGS, k))
        place(b, x1, yf - 1.5, 180, DC.picture, 0.5, 0.4, seed + 2, WALNUT, ("sun", "bands", "squares")[k % 3], z=1.55)
        cabin_light(b, x0 + 1.0, x0 + 3.0, y0 + 0.3, yf - 0.3, H, "white_warm")


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the senior officers' suites
def suites_block(b: SParts, spec: dict, seed0: int = 60) -> None:
    """24 x 12: four suites of 6 x 9 m off a hall 2.3 m wide along the near wall, a hatch each. A suite, from the hatch inwards: a coat cupboard, a sitting area (a sofa, a coffee table
    and an armchair on a rug, a desk with its screen and its lamp by the partition, a shelf, floor lamps), then the sleeping area (a double bed under a wide window with a nightstand and a
    lamp at each side, a bench at its foot, a wardrobe, a basin with its mirror); two lights, one for each area."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    yh = 2.6                                                                                 # the hall's wall (centre line)
    ys = yh + 0.075
    partition(b, "x", yh, xl, xr, H, [(3.0 + 6.0 * k, 1.0, DH) for k in range(4)], hall=-1)
    for k in range(1, 4):
        partition(b, "y", 6.0 * k, yh, yf, H, (), hall=0)
    for k in range(4):                                                                       # the hatches' plates, the hall's pictures between them
        xc = 3.0 + 6.0 * k
        b.emit.lamp_box((xc + 0.62, yh - 0.079, 1.45), (xc + 0.68, yh - 0.075, 1.52), "green", LAMP_DIM)
        b.emit.label_fit((xc, yh - 0.0755, 2.34), 0.30, f"cabin_{k + 9:02d}", (0, -1, 0))
        if k > 0:
            place(b, 6.0 * k, yh - 0.075, -90, DC.picture, 1.0, 0.65, seed0 + k, WALNUT, ("bands", "sun", "squares")[k % 3], z=1.75)
    place(b, 12.0, 1.3, 0, DC.rug, 21.0, 0.9, CARPET_SLATE, FABRIC_SAND, 0.1)
    b.emit.lamp_box((xl + 1.0, 1.2, H - 0.05), (xr - 1.0, 1.4, H - 0.044), "warm_dim", LAMP_DIM)
    # ARTE-INTERNI-2: the wall in front of the entrance is a composed view, not a blank partition (the door at x 10 looked at plaster 1.7 m away): a console with a lamp and a plant, a large
    # picture over it, a wall light each side
    dx = next((d["x"] for d in spec["doors"] if d["wall"] == "near"), 10.0)
    yw = yh - 0.075
    place(b, dx, yw - 0.2, -90, F.counter, 1.5, 0.4, 0.86, WALNUT, WALNUT, True, False)
    place(b, dx - 0.45, yw - 0.2, 0, F.lamp_standard, 0.35, "white_warm", z=0.86)
    place(b, dx + 0.45, yw - 0.2, 0, F.potted_plant, 0.9, 5, z=0.86)
    place(b, dx, yw, -90, DC.picture, 1.5, 0.95, 21, WALNUT, "sun", z=1.35)
    for sx in (-1.15, 1.15):
        place(b, dx + sx, yw, -90, DC.wall_sconce, "white_warm", z=1.9)
    for k in range(4):
        seed = seed0 + k * 7
        rng = random.Random(seed)
        xa, xb = 6.0 * k, 6.0 * (k + 1)
        x0 = xl if k == 0 else xa + 0.075
        x1 = xr if k == 3 else xb - 0.075
        xc = 3.0 + xa
        blanket = pick(BLANKETS, k)
        # the sitting area: the sofa faces +y (the sitter's place is on it), the table and the armchair opposite
        place(b, xc + 0.6, 4.4, 90, F.sofa, 1.8, pick((FABRIC_NAVY, LEATHER_NAVY, FABRIC_GREY, LEATHER_OX), k))
        place(b, xc + 0.6, 5.45, 0, DC.coffee_table_set, 1.1, 0.6, 0.4, OAK, seed)
        place(b, xc + 0.6, 6.55, -90, F.armchair, pick((FABRIC_SAND, FABRIC_RUST, FABRIC_GREY, FABRIC_NAVY), k + 1))
        place(b, xc + 0.6, 5.45, 0, DC.rug, 3.0, 2.8, *pick(RUGS, k))
        place(b, xc + 1.75, 4.1, 0, F.lamp_standard, 1.5, "white_warm")
        place(b, x1 - 1.1, 3.9, 0, F.table, 0.9, 0.9, 0.74, OAK, TRIM, True)                                          # a dining nook for two by the partition
        for sy, yw in ((-1, 90), (1, -90)):
            place(b, x1 - 1.1, 3.9 + sy * 0.62, yw, F.chair, pick((FABRIC_RUST, FABRIC_SAND, FABRIC_NAVY), k))
            place(b, x1 - 1.1, 3.9 + sy * 0.28, yw, DC.table_setting, seed + sy, z=0.74)
        place(b, x0 + 0.35, 6.0, 180, F.desk, 1.2, 0.6, 0.75, WOOD, True)
        place(b, x0 + 0.35, 6.0, 0, desk_set, seed, True, z=0.75)
        place(b, x0 + 1.1 + rng.uniform(-0.05, 0.05), 6.0, 180 + rng.uniform(-12, 12), F.chair, FABRIC_GREY)
        place(b, x0 + 0.19, 3.6, 0, F.shelf, 1.2, 0.34, 2.0, 5, WALNUT, True, seed, True)
        place(b, x0 + 0.6, ys + 0.29, 90, G.wardrobe, 0.9, 0.55, 2.0)
        place(b, x1 - 0.003, 4.4, 180, DC.picture, 0.9, 0.6, seed + 4, WALNUT, ("sun", "squares", "bands")[k % 3], z=1.7)
        # the sleeping area: the double bed under its window, a nightstand each side
        place(b, xc, yf - 1.14, -90, K8.officer_bed, 1.4, 2.1, blanket)
        for sx in (-1.0, 1.0):
            place(b, xc + sx, yf - 0.22, -90, nightstand, seed + int(sx))
        place(b, xc, yf, -90, viewport, 2.6, 0.9, pick(CURTAINS, k), seed, 0.3 if k % 2 == 0 else 0.0, z=1.7)
        place(b, xc, yf - 2.55, -90, F.bench, 1.3, 0.42, 0.45, pick((FABRIC_SAND, FABRIC_GREY, FABRIC_RUST), k))
        place(b, x1 - 0.285, 8.6, 180, G.wardrobe, 0.9, 0.55, 2.0)
        place(b, x0 + 0.27, 9.6, 0, G.vanity, 0.9, 0.5)
        place(b, xc, 9.7, 0, G.rug, 3.0, 2.6, *pick(RUGS, k + 2))
        place(b, x0 + 0.5, yf - 0.6, 0, F.potted_plant, 1.0, seed)
        place(b, x1 - 0.5, yf - 0.6, 0, F.potted_plant, 1.0, seed + 1)
        cabin_light(b, xc - 0.9, xc + 0.9, 4.0, 6.5, H, "white_warm")
        cabin_light(b, xc - 0.9, xc + 0.9, 8.6, 11.0, H, "warm_dim")
