"""ASN Aquila interior kit (ARTE-INTERNI-2): ceilings and floors that are not flat planes. The shell v2 (ship_shell.py) gives every room a floor and a ceiling of one of a few kinds; this module is
the vocabulary for the rooms that want more — the structure of a ceiling seen from below (trusses, coffers, hung clouds), the lights that hang in it (grow-light arrays, a sky screen that
reads as a screen), the finishes of a floor (a field of planks with a border, a checker of tiles, zones, rugs, runners, inlays). Every function builds into an SParts in the ROOM frame
(x along the corridor 0..L, y into the room 0..D, z up; ship_rooms.py), at the heights the room tells it, with the same primitives as the furniture, so a room calls them after build_shell.

  ceilings  truss, truss_row, grow_array, sky_screen, irrigation_line, coffers, clouds
  floors    field, checker, border_line, runner, rug_zone
"""
from __future__ import annotations

import math
import random

from bridge3_lib import Rz
from ship_lib import (BRASS, COMPOSITE, LAMP, LAMP_DIM, LAMP_HOT, OAK, PLASTER_IVORY, STEEL, STRUCT, SWATCH, TRIM, WALNUT, SParts)

WS = 0.20
WF = 0.05


# ===================================================================================================================================== ceilings
def truss(b: SParts, x: float, y0: float, y1: float, z_top: float, depth: float = 0.5, pitch: float = 1.0, chord_mat: str = STRUCT, web_mat: str = TRIM,
          glow: str | None = None, width: float = 0.09) -> None:
    """A lattice girder across the room along y at x (a Warren truss: a top chord against the ceiling at z_top, a bottom chord `depth` below it, diagonals every `pitch`, a post at every
    node, a bracket plate at the ends). `glow`: a lamp cell for a thin strip of light along the underside of the bottom chord (the girder washes the ceiling's soffit)."""
    ch = 0.09
    b.body.box((x - width / 2, y0, z_top - ch), (x + width / 2, y1, z_top), chord_mat)
    b.body.box((x - width / 2, y0, z_top - depth), (x + width / 2, y1, z_top - depth + ch), chord_mat)
    n = max(2, int(round((y1 - y0) / pitch)))
    step = (y1 - y0) / n
    zt, zb = z_top - ch, z_top - depth + ch
    for k in range(n + 1):
        y = y0 + k * step
        if 0 < k < n:
            b.soft.box((x - 0.018, y - 0.018, zb), (x + 0.018, y + 0.018, zt), web_mat)                           # a post at the node
    for k in range(n):
        ya, yb = y0 + k * step, y0 + (k + 1) * step
        if k % 2 == 0:
            b.soft.cyl((x, ya, zb), (x, yb, zt), 0.014, web_mat, seg=5, caps=False)
        else:
            b.soft.cyl((x, ya, zt), (x, yb, zb), 0.014, web_mat, seg=5, caps=False)
    for y in (y0, y1):                                                                                          # the end plates where the girder meets the wall
        b.soft.box((x - width / 2 - 0.02, y - 0.02, z_top - depth), (x + width / 2 + 0.02, y + 0.02, z_top), chord_mat)
    if glow:
        b.emit.lamp_box((x - 0.02, y0 + 0.2, z_top - depth - 0.004), (x + 0.02, y1 - 0.2, z_top - depth), glow, LAMP_DIM)


def truss_row(b: SParts, xs, y0: float, y1: float, z_top: float, depth: float = 0.5, pitch: float = 1.0, glow: str | None = None) -> None:
    for x in xs:
        truss(b, x, y0, y1, z_top, depth, pitch, glow=glow)


def grow_array(b: SParts, x0: float, x1: float, y0: float, y1: float, z_top: float, drop: float = 0.34, bars: int = 12, white: str = "white_cool", edge: str = "violet",
               hang_from: float | None = None) -> None:
    """A grow-light array hung under the ceiling: a rectangular frame (x0..x1 by y0..y1) whose underside is `drop` below z_top, a row of `bars` LED bars along y (each a brushed
    housing with a pale diffuser, the first and the last carrying a violet edge: a grow light that is also a light to see by), four hanger rods to the structure above, a driver
    box at one end with a status lamp. `hang_from`: the z the rods end at (the ceiling by default)."""
    zb = z_top - drop
    t = 0.045
    b.body.box((x0, y0, zb), (x1, y0 + t, zb + 0.06), STRUCT)
    b.body.box((x0, y1 - t, zb), (x1, y1, zb + 0.06), STRUCT)
    b.body.box((x0, y0, zb), (x0 + t, y1, zb + 0.06), STRUCT)
    b.body.box((x1 - t, y0, zb), (x1, y1, zb + 0.06), STRUCT)
    pitch = (x1 - x0 - 2 * t) / bars
    for k in range(bars):
        xa = x0 + t + k * pitch
        xc = xa + pitch / 2
        b.soft.box((xc - 0.034, y0 + t, zb + 0.005), (xc + 0.034, y1 - t, zb + 0.04), TRIM)                      # the housing
        cell = edge if k in (0, bars - 1) else white
        b.emit.lamp_box((xc - 0.024, y0 + t + 0.03, zb + 0.0), (xc + 0.024, y1 - t - 0.03, zb + 0.006), cell, LAMP if cell == white else LAMP_DIM)
    for yy in (y0 + (y1 - y0) * 0.25, y0 + (y1 - y0) * 0.75):                                                    # two cross rails carry the housings
        b.soft.box((x0 + t, yy - 0.025, zb + 0.04), (x1 - t, yy + 0.025, zb + 0.06), STRUCT)
    zr = z_top if hang_from is None else hang_from
    for (xr, yr) in ((x0 + 0.18, y0 + 0.2), (x1 - 0.18, y0 + 0.2), (x0 + 0.18, y1 - 0.2), (x1 - 0.18, y1 - 0.2)):
        b.soft.cyl((xr, yr, zb + 0.06), (xr, yr, zr), 0.007, STEEL, seg=4, caps=False)
    b.soft.box((x1 - 0.55, y1 - 0.5, zb + 0.06), (x1 - 0.1, y1 - 0.12, zb + 0.2), STRUCT)                           # the driver
    b.emit.lamp_box((x1 - 0.5, y1 - 0.121, zb + 0.15), (x1 - 0.44, y1 - 0.118, zb + 0.18), "green", LAMP_DIM)


def _noise(rng: random.Random, nx: int, ny: int, cells: int) -> list[list[float]]:
    """A smooth value noise on an nx x ny grid (random lattice of cells x cells points, bilinear): the clouds of the sky screen."""
    lat = [[rng.random() for _ in range(cells + 2)] for _ in range(cells + 2)]
    out = []
    for j in range(ny):
        row = []
        v = j / max(1, ny - 1) * cells
        j0 = int(v)
        fv = v - j0
        fv = fv * fv * (3 - 2 * fv)
        for i in range(nx):
            u = i / max(1, nx - 1) * cells
            i0 = int(u)
            fu = u - i0
            fu = fu * fu * (3 - 2 * fu)
            a = lat[j0][i0] * (1 - fu) + lat[j0][i0 + 1] * fu
            c = lat[j0 + 1][i0] * (1 - fu) + lat[j0 + 1][i0 + 1] * fu
            row.append(a * (1 - fv) + c * fv)
        out.append(row)
    return out


SKY_RAMP = ("cyan_dim", "cyan", "ice", "white")                       # (alert-proof palette cells: deep to pale) the sky never turns red: the ship's alert has its own lights


def sky_screen(b: SParts, x0: float, x1: float, y0: float, y1: float, z: float, seed: int = 1, cell: float = 0.2, sun: tuple | None = None, bezel: float = 0.07,
               mat: str = LAMP_DIM, field=None, frame_mat: str = TRIM) -> None:
    """A luminous sky window that reads as a screen: a brushed bezel, a dark backing plate and a field of square pixels `cell` m wide (a 6 mm gap between them), coloured in a sky
    gradient with soft clouds and (`sun` = (x, y) in room coordinates) a warm glare; `field` (a function (u, v) 0..1 -> a lamp cell name) replaces the sky. Flush with the ceiling at z
    (the pixels face down, the bezel stands 6 cm proud). One quad a pixel."""
    w, d = x1 - x0, y1 - y0
    nx, ny = max(2, int(round(w / cell))), max(2, int(round(d / cell)))
    rng = random.Random(seed)
    clouds = _noise(rng, nx, ny, 5)
    fine = _noise(rng, nx, ny, 11)
    # the frame and the backing
    for (a0, a1, c0, c1) in ((x0 - bezel, x1 + bezel, y0 - bezel, y0), (x0 - bezel, x1 + bezel, y1, y1 + bezel), (x0 - bezel, x0, y0, y1), (x1, x1 + bezel, y0, y1)):
        b.body.box((a0, c0, z - 0.06), (a1, c1, z + 0.006), frame_mat)
    b.fine.box((x0, y0, z + 0.0), (x1, y1, z + 0.004), STRUCT)
    gx = 0.006
    for j in range(ny):
        for i in range(nx):
            u, v = (i + 0.5) / nx, (j + 0.5) / ny
            if field is not None:
                c = field(u, v)
            else:
                t = 0.25 + 0.55 * u + (v - 0.5) * 0.12                    # deeper at one end, paler towards the horizon end, a little darker at the long edges
                t += (clouds[j][i] - 0.5) * 0.9 + (fine[j][i] - 0.5) * 0.25
                edge = min(u, 1 - u, v, 1 - v)
                t -= max(0.0, 0.06 - edge) * 3.0                          # the vignette: the outer ring of pixels is dimmer
                idx = max(0, min(len(SKY_RAMP) - 1, int(t * len(SKY_RAMP))))
                c = SKY_RAMP[idx]
                if sun is not None:
                    sx, sy = sun
                    px, py = x0 + u * w, y0 + v * d
                    r = math.hypot(px - sx, (py - sy) * 0.8)
                    if r < 0.55:
                        c = "white_warm"
                    elif r < 1.1 and idx >= 2:
                        c = "white"
            xa, ya = x0 + i * w / nx + gx / 2, y0 + j * d / ny + gx / 2
            xb, yb = x0 + (i + 1) * w / nx - gx / 2, y0 + (j + 1) * d / ny - gx / 2
            b.emit.lamp_face([(xa, ya, z - 0.002), (xb, ya, z - 0.002), (xb, yb, z - 0.002), (xa, yb, z - 0.002)], c, (0, 0, -1), mat)


def irrigation_line(b: SParts, x0: float, x1: float, y: float, z: float, nozzles: float = 1.4, r: float = 0.034, mat: str = STEEL, hang: float | None = None, drop: float = 0.3) -> None:
    """A water line along x at (y, z) with a clamp every 1.6 m, a brass drip nozzle on a short drop every `nozzles` m (a bead of water at its tip), the feed valve at one end."""
    b.soft.cyl((x0, y, z), (x1, y, z), r, mat, seg=8, caps=False)
    x = x0 + 0.5
    while x < x1 - 0.2:
        b.soft.cyl((x, y, z - r), (x, y, z - r - drop), 0.006, BRASS, seg=4, caps=False)
        b.soft.cyl((x, y, z - r - drop), (x, y, z - r - drop - 0.035), 0.012, BRASS, seg=5, r2=0.005)
        x += nozzles
    x = x0 + 0.8
    while x < x1:
        b.soft.box((x - 0.02, y - r - 0.012, z - r - 0.012), (x + 0.02, y + r + 0.012, z + r + 0.012), TRIM)
        if hang is not None:
            b.soft.cyl((x, y, z + r), (x, y, hang), 0.005, STEEL, seg=4, caps=False)
        x += 1.6
    b.soft.cyl((x0, y, z), (x0 + 0.18, y, z), r * 1.7, TRIM, seg=8)                                               # the valve body and its wheel
    b.soft.cyl((x0 + 0.09, y, z + r * 1.7), (x0 + 0.09, y, z + r * 1.7 + 0.1), 0.01, STEEL, seg=4, caps=False)
    b.soft.cyl((x0 + 0.09, y - 0.05, z + r * 1.7 + 0.1), (x0 + 0.09, y + 0.05, z + r * 1.7 + 0.1), 0.007, STEEL, seg=4, caps=False)


def coffers(b: SParts, spec: dict, xs, ys, z: float, beam_mat: str = OAK, depth: float = 0.2, beam_w: float = 0.2, lit: str | None = "white_warm", pad: float = 0.4, rim_mat: str | None = None,
            ceil_mat: str | None = None, lit_mat: str = LAMP_DIM) -> None:
    """A coffered ceiling: a grid of beams (`xs` across the room along y, `ys` along x, each beam_w wide and `depth` deep from the ceiling plane at z), the panels between them recessed
    a little and (`lit`) each carrying a light panel inset by `pad`: a brushed rim on the lit panel. Beams stop at the room's finished walls."""
    L, D = spec["L"], spec["D"]
    x0, x1, y0, y1 = WS + WF, L - WS - WF, WF, D - WS - WF
    for x in xs:
        b.body.box((x - beam_w / 2, y0, z - depth), (x + beam_w / 2, y1, z), beam_mat)
    for y in ys:
        b.body.box((x0, y - beam_w / 2, z - depth), (x1, y + beam_w / 2, z), beam_mat)
    cx = [x0] + sorted(xs) + [x1]
    cy = [y0] + sorted(ys) + [y1]
    for i in range(len(cx) - 1):
        for j in range(len(cy) - 1):
            ax = cx[i] + (beam_w / 2 if i > 0 else 0.0)
            bx = cx[i + 1] - (beam_w / 2 if i < len(cx) - 2 else 0.0)
            ay = cy[j] + (beam_w / 2 if j > 0 else 0.0)
            by = cy[j + 1] - (beam_w / 2 if j < len(cy) - 2 else 0.0)
            if bx - ax < 0.6 or by - ay < 0.6:
                continue
            if ceil_mat:
                b.soft.box((ax, ay, z - 0.012), (bx, by, z - 0.004), ceil_mat)
            if lit:
                lx0, lx1, ly0, ly1 = ax + pad, bx - pad, ay + pad, by - pad
                if lx1 - lx0 > 0.5 and ly1 - ly0 > 0.5:
                    t = 0.025
                    r = rim_mat or TRIM
                    b.body.box((lx0 - t, ly0 - t, z - 0.045), (lx1 + t, ly0, z - 0.01), r)
                    b.body.box((lx0 - t, ly1, z - 0.045), (lx1 + t, ly1 + t, z - 0.01), r)
                    b.body.box((lx0 - t, ly0, z - 0.045), (lx0, ly1, z - 0.01), r)
                    b.body.box((lx1, ly0, z - 0.045), (lx1 + t, ly1, z - 0.01), r)
                    b.emit.lamp_box((lx0, ly0, z - 0.04), (lx1, ly1, z - 0.034), lit, lit_mat)


def clouds(b: SParts, rects, z: float, drop: float = 0.45, mat: str = PLASTER_IVORY, glow: str = "white_warm", rim: str = TRIM, hang: float | None = None) -> None:
    """Acoustic clouds: flat islands hung `drop` below the ceiling (z) over the places people gather — a rounded-edge slab of `mat`, a lit gap round its rim (indirect light up on the
    ceiling), four hanger rods. `rects` = [(x0, y0, x1, y1)]."""
    for (x0, y0, x1, y1) in rects:
        zb = z - drop
        b.body.box((x0, y0, zb), (x1, y1, zb + 0.07), mat)
        b.fine.box((x0 - 0.01, y0 - 0.01, zb - 0.01), (x1 + 0.01, y1 + 0.01, zb + 0.0), rim)
        g = 0.06
        b.emit.lamp_box((x0 + g, y0 - 0.02, zb + 0.07), (x1 - g, y0, zb + 0.074), glow, LAMP_DIM)
        b.emit.lamp_box((x0 + g, y1, zb + 0.07), (x1 - g, y1 + 0.02, zb + 0.074), glow, LAMP_DIM)
        b.emit.lamp_box((x0 - 0.02, y0 + g, zb + 0.07), (x0, y1 - g, zb + 0.074), glow, LAMP_DIM)
        b.emit.lamp_box((x1, y0 + g, zb + 0.07), (x1 + 0.02, y1 - g, zb + 0.074), glow, LAMP_DIM)
        zr = z if hang is None else hang
        for (xr, yr) in ((x0 + 0.3, y0 + 0.3), (x1 - 0.3, y0 + 0.3), (x0 + 0.3, y1 - 0.3), (x1 - 0.3, y1 - 0.3)):
            b.soft.cyl((xr, yr, zb + 0.07), (xr, yr, zr), 0.006, STEEL, seg=4, caps=False)


# ===================================================================================================================================== floors
def field(b: SParts, x0: float, x1: float, y0: float, y1: float, mat: str, z: float = 0.0, h: float = 0.012) -> None:
    """A rectangle of floor finish `h` thick on top of the shell's floor (z = 0): a zone of a different covering (wood in a carpeted room), a threshold strip, a plinth for a rug."""
    b.soft.box((x0, y0, z), (x1, y1, z + h), mat)


def checker(b: SParts, x0: float, x1: float, y0: float, y1: float, tile: float, mat_a: str, mat_b: str, z: float = 0.0, h: float = 0.008, gap: float = 0.004) -> None:
    """A chequerboard of tiles `tile` m square in two finishes (a diamond laid on the floor reads at the same price: pass tile and an angle through `place`); one flat top face a tile."""
    nx, ny = max(1, int(round((x1 - x0) / tile))), max(1, int(round((y1 - y0) / tile)))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    for i in range(nx):
        for j in range(ny):
            m = mat_a if (i + j) % 2 == 0 else mat_b
            b.soft.box((x0 + i * sx + gap, y0 + j * sy + gap, z), (x0 + (i + 1) * sx - gap, y0 + (j + 1) * sy - gap, z + h), m)


def border_line(b: SParts, x0: float, x1: float, y0: float, y1: float, w: float = 0.02, mat: str = BRASS, z: float = 0.0, h: float = 0.006) -> None:
    """A thin line (brass by default) round a rectangle on the floor: the edge of a zone, an inlay."""
    b.fine.box((x0, y0, z), (x1, y0 + w, z + h), mat)
    b.fine.box((x0, y1 - w, z), (x1, y1, z + h), mat)
    b.fine.box((x0, y0 + w, z), (x0 + w, y1 - w, z + h), mat)
    b.fine.box((x1 - w, y0 + w, z), (x1, y1 - w, z + h), mat)


def runner(b: SParts, x0: float, y0: float, x1: float, y1: float, mat: str, edge: str, band: float = 0.06, z: float = 0.0, h: float = 0.012) -> None:
    """A long carpet runner between two corners (axis-aligned): the field and an edge band along both long sides."""
    b.soft.box((x0, y0, z), (x1, y1, z + h), edge)
    if abs(x1 - x0) > abs(y1 - y0):
        b.soft.box((x0, y0 + band, z + 0.001), (x1, y1 - band, z + h + 0.002), mat)
    else:
        b.soft.box((x0 + band, y0, z + 0.001), (x1 - band, y1, z + h + 0.002), mat)


# ---------------------------------------------------------------------------------------------------------------------------- floors of pieces
def _top_quad(fb, x0: float, x1: float, y0: float, y1: float, z: float, mat: str, rng: random.Random, flip_uv: bool = False) -> None:
    """One flat piece of floor facing up (a plank, a tile): its UVs are the world position plus a random offset, so every piece shows another part of the material's texture (a real floor
    is not one sheet of wood); the faces carry the custom-UV flag, the builder's projection leaves them alone."""
    ou, ov = rng.random() * 8.0, rng.random() * 8.0
    pts = [(x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)]
    uvs = [((y if flip_uv else x) + ou, (x if flip_uv else y) + ov) for (x, y, _z) in pts]
    fb.face(pts, mat, (0, 0, 1), uvs=uvs, flag=True)


def planks(b: SParts, x0: float, x1: float, y0: float, y1: float, mat: str, plank_w: float = 0.16, plank_l: float = 1.9, along: str = "x", seed: int = 1, z: float = 0.0,
          gap: float = 0.003, mats=None) -> None:
    """A floor of single planks (`plank_w` wide, `plank_l` long, a 3 mm joint: the structure under shows dark in it) in staggered rows, the grain along `along` ('x' or 'y');
    `mats` (a tuple of finishes) is picked from at random per plank. One flat face a plank (a 16 x 16 m room is ~900 of them, 1.8 k triangles). Lay it on a floor built without a
    covering (`floor_fn`), or over one with `z` a little above it."""
    rng = random.Random(seed)
    along_x = along == "x"
    a0, a1, c0, c1 = (x0, x1, y0, y1) if along_x else (y0, y1, x0, x1)           # a: along the grain, c: across it
    nrows = max(1, int(round((c1 - c0) / plank_w)))
    pw = (c1 - c0) / nrows
    for r in range(nrows):
        ca, cb = c0 + r * pw + gap / 2, c0 + (r + 1) * pw - gap / 2
        cut = a0 - rng.uniform(0.0, plank_l)
        while cut < a1 - 0.02:
            ln = plank_l * rng.uniform(0.55, 1.0)
            pa, pb = max(a0, cut) + gap / 2, min(a1, cut + ln) - gap / 2
            cut += ln
            if pb - pa < 0.12:
                continue
            m = mats[rng.randrange(len(mats))] if mats else mat
            if along_x:
                _top_quad(b.body, pa, pb, ca, cb, z, m, rng)
            else:
                _top_quad(b.body, ca, cb, pa, pb, z, m, rng, flip_uv=True)


def tiles(b: SParts, x0: float, x1: float, y0: float, y1: float, tile: float, mat_a: str, mat_b: str | None = None, pattern: str = "checker", seed: int = 1, z: float = 0.0,
          gap: float = 0.004) -> None:
    """A floor of single tiles `tile` m square, flat faces with a small joint: `pattern` checker (two finishes alternate), 'plain' (one finish, every tile its own offset in the texture),
    'diamond' (a checker turned 45 degrees: pieces cut at the edges are dropped, fill the border with a zone of `plain` first)."""
    rng = random.Random(seed)
    nx, ny = max(1, int(round((x1 - x0) / tile))), max(1, int(round((y1 - y0) / tile)))
    sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
    for i in range(nx):
        for j in range(ny):
            m = mat_b if (mat_b and pattern == "checker" and (i + j) % 2) else mat_a
            _top_quad(b.body, x0 + i * sx + gap / 2, x0 + (i + 1) * sx - gap / 2, y0 + j * sy + gap / 2, y0 + (j + 1) * sy - gap / 2, z, m, rng)


# ---------------------------------------------------------------------------------------------------------------------------------- rugs
def rug_ornate(b: SParts, w: float, d: float, field: str, border: str, motif=("oxblood", "cream", "mustard"), seed: int = 1, band: float = 0.22, pile: float = 0.016,
               medallion=True, corners: bool = True) -> None:
    """A woven rug centred on the origin (w along x, d along y): a border of one wool carpet, a field of another inside a thin cream line, a medallion of three nested lozenges in the
    palette's colours, a small lozenge in each corner of the field, a fringe strip at both short ends. About 30 boxes (a few hundred triangles); the colours come from the palette so
    that one slot (MI_SHIP_Swatch) paints every motif."""
    import ship_mk as MK
    rng = random.Random(seed)
    MK.rbox(b.soft, (-w / 2, -d / 2, 0.0), (w / 2, d / 2, pile), 0.004, border, 1)
    fx0, fx1, fy0, fy1 = -w / 2 + band, w / 2 - band, -d / 2 + band, d / 2 - band
    MK.rbox(b.soft, (fx0, fy0, 0.001), (fx1, fy1, pile + 0.002), 0.003, field, 1)
    ln = 0.014
    for (a0, a1, c0, c1) in ((fx0 - 0.05, fx1 + 0.05, fy0 - 0.05, fy0 - 0.05 + ln), (fx0 - 0.05, fx1 + 0.05, fy1 + 0.05 - ln, fy1 + 0.05), (fx0 - 0.05, fx0 - 0.05 + ln, fy0 - 0.05, fy1 + 0.05),
                             (fx1 + 0.05 - ln, fx1 + 0.05, fy0 - 0.05, fy1 + 0.05)):
        b.soft.swatch_box((a0, c0, pile - 0.002), (a1, c1, pile + 0.0035), motif[1])
    z0 = pile + 0.002
    if medallion == "chain":                                                                                     # a runner: lozenges in a row down the length
        r = min(fx1 - fx0, fy1 - fy0) * 0.5
        long_axis = 0 if (fx1 - fx0) >= (fy1 - fy0) else 1
        span = (fx1 - fx0) if long_axis == 0 else (fy1 - fy0)
        n = max(1, int(span / (r * 2.6)))
        for i in range(n):
            c = -span / 2 + (i + 0.5) * span / n
            for k, (sc, col) in enumerate(((1.0, motif[0]), (0.7, motif[1]), (0.4, motif[2]))):
                h2 = r * sc * 0.92
                lo = (c - h2 * 0.7071, -h2 * 0.7071) if long_axis == 0 else (-h2 * 0.7071, c - h2 * 0.7071)
                faces = b.soft.box((lo[0], lo[1], z0 + 0.0008 * k), (lo[0] + h2 * 1.4142, lo[1] + h2 * 1.4142, z0 + 0.0022 + 0.0008 * k), SWATCH, Rz(45.0))
                b.soft.paint(faces, col)
        corners = False
    elif medallion:
        r = min(fx1 - fx0, fy1 - fy0) * 0.5
        for k, (s, col) in enumerate(((1.0, motif[0]), (0.74, motif[1]), (0.52, motif[2]), (0.28, motif[0]))):
            h2 = r * s
            faces = b.soft.box((-h2 * 0.7071, -h2 * 0.7071, z0 + 0.0008 * k), (h2 * 0.7071, h2 * 0.7071, z0 + 0.0022 + 0.0008 * k), SWATCH, Rz(45.0))
            b.soft.paint(faces, col)
    if corners:
        for sx in (-1, 1):
            for sy in (-1, 1):
                cx, cy = sx * (fx1 - 0.3) if sx > 0 else sx * (-fx0 - 0.3), sy * (fy1 - 0.3) if sy > 0 else sy * (-fy0 - 0.3)
                for s, col in ((0.16, motif[2]), (0.09, motif[0])):
                    faces = b.soft.box((cx - s, cy - s, z0), (cx + s, cy + s, z0 + 0.002), SWATCH, Rz(45.0))
                    b.soft.paint(faces, col)
    for sx in (-1, 1):                                                                                           # the fringe: a pale strip and a row of cuts
        xa = sx * (w / 2)
        b.soft.swatch_box((min(xa, xa + sx * 0.07), -d / 2 + 0.02, 0.0), (max(xa, xa + sx * 0.07), d / 2 - 0.02, 0.004), "cream")
        n = int((d - 0.1) / 0.09)
        for k in range(n):
            y = -d / 2 + 0.05 + (k + 0.5) * (d - 0.1) / n
            b.soft.swatch_box((min(xa + sx * 0.07, xa + sx * 0.12), y - 0.003, 0.0), (max(xa + sx * 0.07, xa + sx * 0.12), y + 0.003, 0.0035), "cream")


def compass_rose(b: SParts, cx: float, cy: float, r: float, z: float = 0.0, points: int = 16, disk: str | None = None, colors=("cream", "brass", "navy")) -> None:
    """A compass rose inlaid in the floor (centre cx, cy; radius r): a disc of stone (`disc`, a finish of the room's table) 1 cm proud, with a brass ring at its rim and one inside it, and
    a star of `points` kites — the cardinal ones the longest and cream, the intercardinals two thirds and brass, the rest half and navy — each a flat prism pointing at its bearing from a
    brass boss at the middle. The kites are convex quads (the Builder's `prism`), a few hundred triangles in all."""
    th = 0.01
    if disk:
        b.soft.cyl((cx, cy, z), (cx, cy, z + th), r, disk, seg=64)
    for rr, w in ((r - 0.03, 0.035), (r * 0.74, 0.02)):
        n = 72
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            p0, p1 = (cx + rr * math.cos(a0), cy + rr * math.sin(a0)), (cx + rr * math.cos(a1), cy + rr * math.sin(a1))
            ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
            mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
            b.soft.paint(b.soft.box((mx - ln / 2 - 0.004, my - w / 2, z + th), (mx + ln / 2 + 0.004, my + w / 2, z + th + 0.004), SWATCH, Rz(ang)), "brass")
    for k in range(points):
        ang = math.radians(360.0 * k / points)
        ln = r * 0.7 if k % 4 == 0 else r * 0.5 if k % 2 == 0 else r * 0.34
        wd = r * 0.07 if k % 4 == 0 else r * 0.05
        col = colors[0] if k % 4 == 0 else colors[1] if k % 2 == 0 else colors[2]
        ca, sa = math.cos(ang), math.sin(ang)
        pts = [(0.0, 0.0), (ln * 0.2, wd), (ln, 0.0), (ln * 0.2, -wd)]
        poly = [(cx + x * ca - y * sa, cy + x * sa + y * ca) for (x, y) in pts]
        b.soft.paint(b.soft.prism(poly, z + th, z + th + 0.006, SWATCH), col)
    b.soft.paint(b.soft.cyl((cx, cy, z + th), (cx, cy, z + th + 0.012), r * 0.07, SWATCH, seg=20), "brass")


def stars(b: SParts, x0: float, x1: float, y0: float, y1: float, z: float, n: int = 160, seed: int = 5) -> None:
    """A starfield on a ceiling (a dark plane at z): `n` tiny lamp squares in the cool palette, a few bigger ones, flat faces facing down (one quad each)."""
    rng = random.Random(seed)
    for k in range(n):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        s = rng.choice((0.025, 0.03, 0.04, 0.05))
        cell = rng.choice(("white_cool", "ice", "cool_dim", "white_dim", "white_cool"))
        b.emit.lamp_face([(x, y, z), (x + s, y, z), (x + s, y + s, z), (x, y + s, z)], cell, (0, 0, -1), LAMP_DIM)
