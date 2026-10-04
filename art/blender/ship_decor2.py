"""ASN Aquila interior kit (ARTE-INTERNI-2): more of what makes a room look lived in, the pieces the second round of the rooms needs — a banker's lamp, a globe on a stand, a library ladder,
a card catalogue, a plinth with the ship's model, a record player, a corkboard of photographs, an easel, a trophy case. Same conventions as ship_decor.py: every function builds ONE piece in its
own frame (origin on the floor, +x its front, unless it hangs on a wall) into an SParts.
"""
from __future__ import annotations

import math
import random

from mathutils import Vector

import ship_mk as MK
from bridge3_lib import Rx, Ry, Rz, T
from ship_lib import (BRASS, CERAMIC, DGLASS, LAMP, LAMP_DIM, LEATHER_TAN, OAK, STEEL, STRUCT, SWATCH, TRIM, WALNUT, SParts)


# ---------------------------------------------------------------------------------------------------------------------------------- lamps
def banker_lamp(b: SParts) -> None:
    """A banker's lamp on a table (origin at its foot): a brass foot and stem, a half-cylinder green shade over a warm tube of light, a pull chain."""
    MK.lathe(b.fine, [(0.001, 0.0), (0.06, 0.0), (0.065, 0.012), (0.05, 0.026), (0.022, 0.04), (0.012, 0.06), (0.011, 0.2)], (0, 0, 0), BRASS, seg=16)
    b.fine.cyl((0, 0, 0.19), (0.0, 0.0, 0.215), 0.016, BRASS, seg=8)
    prof = [(-0.15, 0.215), (-0.15, 0.255), (-0.09, 0.3), (0.0, 0.318), (0.09, 0.3), (0.15, 0.255), (0.15, 0.215), (0.14, 0.215), (0.14, 0.25), (0.085, 0.29), (0.0, 0.306), (-0.085, 0.29),
            (-0.14, 0.25), (-0.14, 0.215)]
    shade = b.soft.extrude_y(prof, -0.19, 0.19, SWATCH)                                                         # the green glass shade: an arch of thin section
    b.soft.paint(shade, "forest")
    b.emit.lamp_box((-0.02, -0.17, 0.212), (0.02, 0.17, 0.222), "white_warm", LAMP_DIM)
    b.fine.cyl((0.0, 0.17, 0.3), (0.0, 0.2, 0.18), 0.002, BRASS, seg=4, caps=False)


# ---------------------------------------------------------------------------------------------------------------------------- globe
def globe(b: SParts, r: float = 0.22, seed: int = 1) -> None:
    """A terrestrial globe on a turned wooden stand (origin on the floor under it; 1.0 m to the equator): three legs and a ring, a brass meridian arc, a sphere with continents of the
    palette on a deep blue sea, tilted 23 degrees."""
    rng = random.Random(seed)
    zc = 0.92
    for k in range(3):
        a = 2.0944 * k
        b.fine.cyl((0.28 * math.cos(a), 0.28 * math.sin(a), 0.0), (0.06 * math.cos(a), 0.06 * math.sin(a), 0.78), 0.018, WALNUT, seg=6, r2=0.014)
    MK.lathe(b.fine, [(0.07, 0.74), (0.2, 0.755), (0.205, 0.78), (0.17, 0.795), (0.085, 0.78)], (0, 0, 0), WALNUT, seg=24)
    tilt = Rx(23.0)
    with b.at(T(0.0, 0.0, zc) @ tilt):
        sea = b.soft.sphere((0, 0, 0), r, SWATCH, seg=24, rings=14)
        b.soft.paint(sea, "denim")
        for k in range(9):                                                                                   # continents: flattened lumps lying on the surface
            lon, lat = rng.uniform(0, 6.28), rng.uniform(-1.2, 1.2)
            n = Vector((math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)))
            rot = Vector((0, 0, 1)).rotation_difference(n).to_matrix().to_4x4()
            s = rng.uniform(0.05, 0.1)
            with b.at(T(*(n * r * 0.985)) @ rot):
                f = MK.puff(b.soft, (0, 0, 0), (s * 1.3, s, 0.012), SWATCH, e=0.7, nu=10, nv=4)
                b.soft.paint(f, rng.choice(("forest", "olive", "sand", "forest")))
        b.fine.cyl((0, 0, -r - 0.03), (0, 0, r + 0.03), 0.006, BRASS, seg=6)
        pts = [((r + 0.02) * math.cos(math.radians(a)), 0.0, (r + 0.02) * math.sin(math.radians(a))) for a in range(-85, 86, 17)]        # the meridian: a brass half ring
        b.fine.tube(pts, 0.004, BRASS, seg=4, caps=False)


# -------------------------------------------------------------------------------------------------------------------------------- ladder
def library_ladder(b: SParts, h: float = 2.6, lean: float = 0.32, w: float = 0.42) -> None:
    """A library ladder (origin at the foot, centred across it; the top leans towards -x by `lean`): two oak stiles, a rung every 25 cm, two brass hooks at the top, two small wheels at the
    foot, a handrail."""
    top = (-lean, h)
    for sy in (-w / 2, w / 2):
        b.body.cyl((0, sy, 0.0), (top[0], sy, top[1]), 0.021, OAK, seg=8)
    n = int(h / 0.26)
    for k in range(1, n + 1):
        t = (k * 0.26 - 0.08) / h
        x = -lean * t
        b.fine.cyl((x, -w / 2, k * 0.26 - 0.08), (x, w / 2, k * 0.26 - 0.08), 0.014, OAK, seg=6)
    for sy in (-w / 2, w / 2):
        b.fine.cyl((top[0] - 0.03, sy, top[1] - 0.04), (top[0] + 0.01, sy, top[1] + 0.06), 0.008, BRASS, seg=5)
        b.fine.cyl((0.0, sy - 0.02, 0.04), (0.0, sy + 0.02, 0.04), 0.04, STRUCT, seg=10)
    b.fine.cyl((-lean - 0.05, -w / 2, h - 0.02), (-lean - 0.05, w / 2, h - 0.02), 0.011, BRASS, seg=6)


# ------------------------------------------------------------------------------------------------------------------------ card catalogue
def card_catalog(b: SParts, w: float = 1.3, d: float = 0.5, h: float = 1.05, rows: int = 5, seed: int = 1) -> None:
    """A card catalogue (origin on the floor at the middle of its back, front +x): a walnut cabinet on a plinth, a grid of small drawers with a brass pull and a label card, a rod through
    each row; a brass nameplate on top."""
    rng = random.Random(seed)
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.08), (d / 2, w / 2, h), 0.012, WALNUT, 1)
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.03, 0.0), (d / 2 - 0.03, w / 2 - 0.03, 0.08), STRUCT)
    cols = max(3, int(w / 0.2))
    dh = (h - 0.14) / rows
    dw = (w - 0.1) / cols
    for r in range(rows):
        for c in range(cols):
            y0, z0 = -w / 2 + 0.05 + c * dw, 0.1 + r * dh
            b.fine.box((d / 2, y0 + 0.006, z0 + 0.006), (d / 2 + 0.012, y0 + dw - 0.006, z0 + dh - 0.006), OAK)
            b.fine.box((d / 2 + 0.012, y0 + dw / 2 - 0.025, z0 + dh / 2 - 0.004), (d / 2 + 0.03, y0 + dw / 2 + 0.025, z0 + dh / 2 + 0.004), BRASS)
            b.soft.swatch_box((d / 2 + 0.012, y0 + dw / 2 - 0.02, z0 + dh - 0.04), (d / 2 + 0.0135, y0 + dw / 2 + 0.02, z0 + dh - 0.014), "paper")
    b.fine.box((-0.08, -0.15, h), (0.08, 0.15, h + 0.004), BRASS)


# ------------------------------------------------------------------------------------------------------------------------------- plinth
def plinth(b: SParts, w: float = 0.7, d: float = 0.5, h: float = 0.95, plate: bool = True) -> float:
    """A pedestal for something worth looking at (origin on the floor at its middle): a walnut column on a darker foot with a brass plate on the front; returns the height of its top."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.06), STRUCT)
    MK.rbox(b.soft, (-d / 2 + 0.03, -w / 2 + 0.03, 0.06), (d / 2 - 0.03, w / 2 - 0.03, h - 0.04), 0.008, WALNUT, 1)
    b.body.box((-d / 2, -w / 2, h - 0.04), (d / 2, w / 2, h), STRUCT)
    if plate:
        b.fine.box((d / 2 - 0.028, -0.09, 0.45), (d / 2 - 0.02, 0.09, 0.5), BRASS)
    return h
