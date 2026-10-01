"""ASN Aquila interior kit: furniture and machinery of the working decks (NAVE-2) — consoles, server racks, the transporter's pads and emitters, tanks, pumps,
pipework, switchgear, bunks and lockers of the barracks, targets of the range, the Kestrel assault shuttle. Third library, after ship_furniture.py and
ship_furniture2.py; same conventions: every function builds one piece in ITS OWN frame (origin on the floor, +x the piece's front, +y its left, z up) into a
`SParts` (body = bevelled hard-surface, fine = small details, soft = cloth, emit = lamps and labels); rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math
import random

from mathutils import Vector

import ship_furniture as F
import ship_furniture2 as G
from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)


def dim(accent: str) -> str:
    """The dim palette cell of an accent (violet has none of its own: the science dim)."""
    return {"violet": "science_dim", "white": "white_dim", "blue": "command_dim", "ice": "ice_dim"}.get(accent, accent + "_dim")


# ---------------------------------------------------------------------------------------------------------------------------- rings
def ring(fb, cx: float, cy: float, z: float, r: float, w: float, h: float, mat: str, seg: int = 48) -> None:
    """A flat ring (an annulus with a rectangular section) about the vertical axis through (cx, cy): inner radius r, radial width w, from z up by h."""
    fb.arc_sweep([(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)], cx, cy, r, 0.0, 360.0, mat, seg=seg, z0=z, loop=True)


def lamp_ring(fb, cx: float, cy: float, z: float, r: float, w: float, h: float, cell: str, mat: str = LAMP_DIM, seg: int = 48) -> None:
    fb.lamp_arc([(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)], cx, cy, r, 0.0, 360.0, cell, mat, seg=seg, z0=z, loop=True)


# ------------------------------------------------------------------------------------------------------------------------ consoles
def holo_frame(fb, x: float, y0: float, y1: float, z0: float, z1: float, cell: str = "cyan_dim", lines: int = 3) -> None:
    """A hologram sheet drawn the way a projection reads: a thin outline and a few lines across it (never a solid pane that hides what is behind)."""
    t = 0.012
    for (a, b_, c, d) in ((y0, y1, z0, z0 + t), (y0, y1, z1 - t, z1), (y0, y0 + t, z0, z1), (y1 - t, y1, z0, z1)):
        fb.lamp_box((x, a, c), (x + 0.006, b_, d), cell, LAMP_DIM)
    for k in range(1, lines + 1):
        z = z0 + (z1 - z0) * k / (lines + 1)
        fb.lamp_box((x, y0 + 0.05, z), (x + 0.006, y0 + 0.05 + (y1 - y0 - 0.1) * (0.4 + 0.15 * ((k * 5) % 4)), z + 0.008), cell, LAMP_DIM)


# ------------------------------------------------------------------------------------------------------------------------ consoles
def work_console(b: SParts, w: float = 3.2, accent: str = "science", screens: int = 3, tiles=None, holo: bool = True, riser: bool = True) -> None:
    """A working console facing +x (the operator stands on +x): an ivory and gunmetal shell with a sloped dark-glass work surface and button rows,
    a riser at the back with `screens` live-looking screens in a brushed frame, a hologram panel floating over it, a light line round the base.
    `riser=False`: a low console one can see over (the transporter's): the screens lie in the sloped surface instead."""
    tiles = tiles or ["scr_lab", "scr_map", "scr_sched", "scr_news"]
    hw = w / 2
    prof = [(-0.46, 0.0), (0.40, 0.0), (0.40, 0.78), (0.20, 0.98), (-0.12, 0.98), (-0.12, 1.06), (-0.46, 1.06)]
    b.body.extrude_y(prof, -hw, hw, IVORY)
    b.body.box((0.36, -hw + 0.03, 0.06), (0.405, hw - 0.03, 0.74), STRUCT)                                   # the kick panel
    b.body.box((-0.46, -hw, 0.0), (0.42, hw, 0.07), STRUCT)                                                   # the plinth
    for sy in (-hw - 0.02, hw - 0.02):
        b.body.box((-0.46, sy, 0.0), (0.42, sy + 0.04, 1.06), STEEL)                                          # the end cheeks
    # the work surface: dark glass in a brushed frame on the slope, button rows
    b.fine.box((0.215, -hw + 0.08, 0.93), (0.395, hw - 0.08, 0.99), TRIM)
    b.fine.box((0.22, -hw + 0.10, 0.935), (0.385, hw - 0.10, 0.995), DGLASS)
    n = max(3, int((w - 0.5) / 0.1))
    for row, xx in enumerate((0.30, 0.345)):
        for k in range(n):
            y = -hw + 0.28 + k * (w - 0.56) / (n - 1)
            if (k + row) % 3 == 1:
                continue
            cell = ("cyan", "white_cool", accent, "green", "amber")[(k * 7 + row * 3) % 5]
            b.emit.lamp_box((xx - 0.012, y - 0.014, 0.945 + row * 0.02), (xx + 0.012, y + 0.014, 0.95 + row * 0.02), cell, LAMP_DIM)
    if riser:
        # the riser: a frame and screens
        sw = (w - 0.4) / screens
        b.body.box((-0.46, -hw, 1.06), (-0.40, hw, 1.58), COMPOSITE)
        for k in range(screens):
            y0 = -hw + 0.2 + k * sw
            b.fine.box((-0.405, y0 + 0.02, 1.12), (-0.385, y0 + sw - 0.02, 1.54), TRIM)
            b.fine.box((-0.385, y0 + 0.045, 1.14), (-0.378, y0 + sw - 0.045, 1.52), DGLASS)
            b.emit.label((-0.377, y0 + sw / 2, 1.33), sw - 0.1, 0.36, (1, 0, 0), tiles[k % len(tiles)])
        b.emit.lamp_box((-0.46, -hw + 0.02, 1.58), (-0.40, hw - 0.02, 1.60), dim(accent), LAMP_DIM)
        if holo:
            holo_frame(b.emit, 0.05, -hw + 0.5, hw - 0.5, 1.36, 1.7)                                              # a hologram sheet hung on two posts
            for sy in (-hw + 0.5, hw - 0.5):
                b.fine.cyl((0.05, sy, 1.06), (0.05, sy, 1.36), 0.012, TRIM, seg=6)
    else:
        b.body.box((-0.46, -hw, 1.06), (-0.40, hw, 1.12), COMPOSITE)                                           # a low back lip, nothing to see over
        sw = (w - 0.5) / screens
        for k in range(screens):                                                                                # the screens lie in the slope, facing the operator
            y0 = -hw + 0.25 + k * sw
            c = (0.30, y0 + sw / 2, 0.88)
            b.emit.label((0.285, y0 + sw / 2, 0.865), sw - 0.12, 0.17, (0.7, 0, 0.7), tiles[k % len(tiles)], up=(-0.7, 0, 0.7))
        if holo:
            holo_frame(b.emit, 0.0, -0.5, 0.5, 1.12, 1.36, "cyan_dim", 2)                                          # a low hologram sheet over the surface
    b.emit.lamp_box((0.42, -hw + 0.05, 0.12), (0.425, hw - 0.05, 0.14), dim(accent), LAMP_DIM)             # the base glow


def chair_op(b: SParts, mat: str = FABRIC_NAVY) -> None:
    """An operator's swivel chair on a column (not a wheeled office chair): facing +x, a shaped shell back with a head rest and arms."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.04), 0.30, STRUCT, seg=16)
    b.body.cyl((0, 0, 0.04), (0, 0, 0.42), 0.04, TRIM, seg=8)
    b.soft.box((-0.22, -0.23, 0.42), (0.22, 0.23, 0.50), mat)
    b.body.box((-0.26, -0.22, 0.50), (-0.20, 0.22, 1.02), COMPOSITE)
    b.soft.box((-0.20, -0.20, 0.52), (-0.14, 0.20, 0.96), mat)
    b.soft.box((-0.24, -0.12, 1.02), (-0.16, 0.12, 1.16), mat)
    for sy in (-0.25, 0.22):
        b.body.box((-0.18, sy, 0.62), (0.18, sy + 0.03, 0.66), TRIM)
        b.fine.box((-0.02, sy, 0.50), (0.02, sy + 0.03, 0.62), TRIM)


# --------------------------------------------------------------------------------------------------------------------- racks, data
def server_rack(b: SParts, w: float = 0.62, d: float = 0.95, h: float = 2.2, seed: int = 1, accent: str = "cyan", door: bool = True) -> None:
    """A data rack facing +x: a gunmetal cabinet, a tinted door with rows of status lights and a label. Built unbevelled (a room has dozens of them)."""
    rng = random.Random(seed)
    hw = w / 2
    x = d / 2
    b.soft.box((-d / 2, -hw, 0.05), (x, hw, h), STRUCT)
    b.soft.box((-d / 2 - 0.02, -hw - 0.01, 0.0), (x + 0.02, hw + 0.01, 0.07), TRIM)
    b.soft.box((-d / 2 - 0.02, -hw - 0.01, h), (x + 0.02, hw + 0.01, h + 0.03), TRIM)
    b.soft.box((x, -hw + 0.03, 0.12), (x + 0.03, hw - 0.03, h - 0.08), COMPOSITE)
    if door:
        b.soft.box((x + 0.03, -hw + 0.07, 0.2), (x + 0.036, hw - 0.07, h - 0.16), DGLASS)
    rows = int((h - 0.5) / 0.17)
    for r in range(rows):
        z = 0.24 + r * 0.17
        cell = rng.choice((accent, accent, "green", "ice", "white_dim"))
        n = rng.choice((3, 4, 5))
        b.emit.lamp_box((x + 0.036, -hw + 0.09, z), (x + 0.04, -hw + 0.09 + n * 0.035, z + 0.012), cell, LAMP_DIM)
        if rng.random() < 0.4:
            b.emit.lamp_box((x + 0.036, hw - 0.14, z), (x + 0.04, hw - 0.1, z + 0.012), rng.choice(("amber", "green")), LAMP_DIM)
    b.soft.box((x + 0.03, hw - 0.095, h - 0.34), (x + 0.04, hw - 0.075, h - 0.2), TRIM)                      # the handle
    b.emit.label((x + 0.037, 0.0, h - 0.10), w - 0.14, (w - 0.14) / 4.0, (1, 0, 0), "small_%02d" % rng.randint(0, 12))


RACK_TAGS = ("tag_05", "tag_15", "tag_06", "tag_12")             # the tags a row of racks may carry at its ends: DATA TRUNK, COMM RELAY, POWER 480 V, BREAKER PANEL


def rack_row(b: SParts, n: int, w: float = 0.62, d: float = 0.95, h: float = 2.2, accent: str = "cyan", seed: int = 1) -> None:
    """n racks side by side along y (origin at the first one's centre), a cable trough over them."""
    for k in range(n):
        with b.at(T(0.0, k * w, 0.0)):
            server_rack(b, w, d, h, seed + k, accent)
    b.soft.box((-d / 2 - 0.05, -w / 2, h + 0.03), (d / 2 + 0.05, (n - 0.5) * w, h + 0.2), STRUCT)
    b.soft.box((-d / 2 - 0.04, -w / 2 + 0.02, h + 0.2), (d / 2 + 0.04, (n - 0.5) * w - 0.02, h + 0.215), TRIM)
    for yy, face in ((-w / 2 - 0.002, -1), ((n - 0.5) * w + 0.002, 1)):                                           # the row's end faces: a row tag and a light bar
        b.emit.label((0.0, yy, h * 0.55), 0.7, 0.175, (0, face, 0), RACK_TAGS[(seed + (3 if face > 0 else 0)) % len(RACK_TAGS)])
        b.emit.lamp_box((-0.38, yy + (0.004 if face > 0 else -0.004), 0.3), (0.38, yy + (0.012 if face > 0 else -0.012), 0.33), accent, LAMP_DIM)


def data_core(b: SParts, r: float = 0.55, h: float = 2.5, accent: str = "cyan") -> None:
    """A free-standing cylindrical data core: a ring of vertical light bars round a dark column, caps at both ends, cables down to the floor."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.10), r + 0.12, STRUCT, seg=24)
    b.body.cyl((0, 0, 0.10), (0, 0, h - 0.12), r, COMPOSITE, seg=24)
    b.body.cyl((0, 0, h - 0.12), (0, 0, h), r + 0.10, STRUCT, seg=24)
    for k in range(12):
        a = math.radians(k * 30.0)
        px, py = (r + 0.005) * math.cos(a), (r + 0.005) * math.sin(a)
        b.emit.lamp_box((px - 0.012, py - 0.012, 0.35), (px + 0.012, py + 0.012, h - 0.35), accent if k % 3 else "ice", LAMP_DIM)
    for z in (0.7, 1.3, 1.9):
        ring(b.fine, 0.0, 0.0, z, r, 0.025, 0.04, TRIM, 24)
    lamp_ring(b.emit, 0.0, 0.0, h - 0.125, r + 0.02, 0.07, 0.006, accent, LAMP, 24)


# ------------------------------------------------------------------------------------------------------------------------ transporter
def transporter_pad(b: SParts, r: float = 0.62) -> None:
    """One transporter pad (origin at its centre on the dais): a thick steel disc with a recessed dark centre, a lit double ring, four tick lights."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.06), r, STEEL, seg=28)
    b.body.cyl((0, 0, 0.06), (0, 0, 0.075), r * 0.90, STRUCT, seg=28)
    b.fine.cyl((0, 0, 0.075), (0, 0, 0.083), r * 0.70, DGLASS, seg=28)
    lamp_ring(b.emit, 0.0, 0.0, 0.074, r * 0.72, 0.045, 0.012, "cyan", LAMP, 28)
    lamp_ring(b.emit, 0.0, 0.0, 0.074, r * 0.90, 0.025, 0.012, "ice", LAMP_DIM, 28)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        b.emit.lamp_box((r * 0.55 * math.cos(a) - 0.015, r * 0.55 * math.sin(a) - 0.015, 0.083), (r * 0.55 * math.cos(a) + 0.015, r * 0.55 * math.sin(a) + 0.015, 0.09), "white", LAMP)


def transporter_dais(b: SParts, r: float = 3.3, pads: int = 6, pad_r: float = 0.62, ring_r: float = 2.0, h: float = 0.30) -> None:
    """The platform: a raised octagonal-looking disc (a 24-gon) with a brushed rim, a lit guide line round it, the pads on a ring and a hub disc in the middle."""
    b.body.cyl((0, 0, 0.0), (0, 0, h), r, STRUCT, seg=24)
    b.body.cyl((0, 0, h), (0, 0, h + 0.012), r - 0.04, DECK, seg=24)
    ring(b.body, 0.0, 0.0, 0.0, r - 0.02, 0.06, h + 0.02, TRIM, 24)
    lamp_ring(b.emit, 0.0, 0.0, h + 0.014, r - 0.30, 0.05, 0.008, "science", LAMP_DIM, 48)
    lamp_ring(b.emit, 0.0, 0.0, h + 0.014, 0.85, 0.05, 0.008, "science", LAMP_DIM, 32)
    for k in range(pads):
        a = 2 * math.pi * k / pads + math.pi / pads * 0.0
        with b.at(T(ring_r * math.cos(a), ring_r * math.sin(a), h + 0.012)):
            transporter_pad(b, pad_r)
    b.body.cyl((0, 0, h + 0.012), (0, 0, h + 0.05), 0.55, STEEL, seg=24)
    lamp_ring(b.emit, 0.0, 0.0, h + 0.05, 0.40, 0.03, 0.008, "cyan", LAMP, 24)
    # the safety line round the platform: hazard tape on the deck
    for k in range(24):
        a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 0.5) / 24
        rr = r + 0.28
        lamp_strip(b.emit, (rr * math.cos(a0), rr * math.sin(a0), 0.006), (rr * math.cos(a1), rr * math.sin(a1), 0.006), 0.12, 0.004, "flight", LAMP_DIM)


def emitter_ring(b: SParts, r: float = 3.0, z: float = 2.95, pads: int = 6, ring_r: float = 2.0, h_ceil: float = 3.8) -> None:
    """The emitter assembly over the dais: a heavy ring hung from the ceiling on struts, a glowing underside, and a coil pod over each pad."""
    ring(b.body, 0.0, 0.0, z, r - 0.18, 0.36, 0.22, COMPOSITE, 24)
    ring(b.fine, 0.0, 0.0, z - 0.02, r - 0.20, 0.04, 0.04, TRIM, 24)
    ring(b.fine, 0.0, 0.0, z - 0.02, r + 0.16, 0.04, 0.04, TRIM, 24)
    lamp_ring(b.emit, 0.0, 0.0, z - 0.006, r - 0.10, 0.20, 0.008, "cyan", LAMP_HOT, 48)
    for k in range(6):
        a = math.radians(30 + 60 * k)
        x, y = r * math.cos(a), r * math.sin(a)
        b.body.cyl((x, y, z + 0.22), (x, y, h_ceil), 0.07, TRIM, seg=8)
        b.body.cyl((x, y, h_ceil - 0.22), (x, y, h_ceil - 0.04), 0.16, STRUCT, seg=12)
    for k in range(pads):
        a = 2 * math.pi * k / pads
        x, y = ring_r * math.cos(a), ring_r * math.sin(a)
        b.body.cyl((x, y, z + 0.22), (x, y, z + 0.5), 0.34, STRUCT, seg=14, r2=0.26)
        b.body.cyl((x, y, z + 0.5), (x, y, h_ceil - 0.3), 0.07, TRIM, seg=8)
        b.body.cyl((x, y, z + 0.0), (x, y, z + 0.22), 0.42, COMPOSITE, seg=16, r2=0.34)
        b.body.cyl((x, y, z - 0.07), (x, y, z), 0.46, TRIM, seg=16, r2=0.42)
        b.emit.lamp_cyl((x, y, z - 0.075), (x, y, z - 0.07), 0.32, "ice", LAMP_HOT, seg=16)
        lamp_ring(b.emit, x, y, z - 0.06, 0.34, 0.06, 0.006, "cyan", LAMP, 16)
    # a column of light from the hub down towards the platform
    b.emit.lamp_cyl((0, 0, z - 0.3), (0, 0, z - 0.01), 0.26, "cyan_dim", LAMP_DIM, seg=16, r2=0.34)


def pattern_buffer(b: SParts, h: float = 2.7, r: float = 0.42, accent: str = "cyan") -> None:
    """A pattern buffer: a tall cylinder of dark glass bars round a glowing column of light, a heavy cap at each end, a status plate at its foot."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.30), r + 0.10, STRUCT, seg=20)
    b.body.cyl((0, 0, 0.30), (0, 0, 0.40), r + 0.14, TRIM, seg=20)
    b.body.cyl((0, 0, h - 0.40), (0, 0, h - 0.30), r + 0.14, TRIM, seg=20)
    b.body.cyl((0, 0, h - 0.30), (0, 0, h), r + 0.10, STRUCT, seg=20)
    b.emit.lamp_cyl((0, 0, 0.40), (0, 0, h - 0.40), r * 0.42, accent, LAMP, seg=14)
    b.emit.lamp_cyl((0, 0, 0.40), (0, 0, h - 0.40), r * 0.62, dim(accent), LAMP_DIM, seg=14)
    for k in range(8):
        a = math.radians(45 * k + 22.5)
        px, py = (r * 0.98) * math.cos(a), (r * 0.98) * math.sin(a)
        b.body.cyl((px, py, 0.40), (px, py, h - 0.40), 0.028, DGLASS, seg=6)
    for z in (0.9, 1.5, 2.1):
        ring(b.fine, 0.0, 0.0, z, r - 0.02, 0.05, 0.04, TRIM, 20)
    b.fine.box((r + 0.02, -0.18, 0.5), (r + 0.06, 0.18, 0.9), TRIM)
    b.fine.box((r + 0.06, -0.15, 0.53), (r + 0.065, 0.15, 0.87), DGLASS)
    b.emit.label((r + 0.066, 0.0, 0.70), 0.28, 0.28 / 4.2, (1, 0, 0), "small_03")


def decon_booth(b: SParts, w: float = 1.5, d: float = 1.5, h: float = 2.4) -> None:
    """A decontamination booth facing +x: a closed cabinet with a heavy sliding door, a hazard header, a status panel and a window."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), COMPOSITE)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, h), (d / 2 + 0.02, w / 2 + 0.02, h + 0.05), TRIM)
    x = d / 2
    b.fine.box((x, -0.42, 0.04), (x + 0.04, 0.42, 2.12), STEEL)
    b.fine.box((x + 0.04, -0.34, 0.12), (x + 0.045, 0.34, 2.04), STRUCT)
    b.fine.box((x + 0.045, -0.16, 1.2), (x + 0.05, 0.16, 1.7), DGLASS)
    b.fine.box((x + 0.04, 0.44, 0.95), (x + 0.07, 0.62, 1.4), TRIM)
    b.emit.lamp_box((x + 0.07, 0.47, 1.2), (x + 0.075, 0.59, 1.26), "amber", LAMP)
    b.emit.lamp_box((x + 0.07, 0.47, 1.05), (x + 0.075, 0.59, 1.11), "green", LAMP_DIM)
    b.emit.label((x + 0.002, 0.0, 2.25), 1.0, 0.18, (1, 0, 0), "hazard")
    b.emit.label((x + 0.002, 0.0, h - 0.1), 0.7, 0.175, (1, 0, 0), "eq_clean")


# ------------------------------------------------------------------------------------------------------------------------- pipework
def pipe_bundle(b: SParts, p0, p1, n: int = 3, r: float = 0.055, gap: float = 0.03, axis_up=(0, 0, 1), mats=None, clamps: float = 1.4) -> None:
    """n pipes side by side along p0 -> p1 (spread across `axis_up` x the run), with clamps."""
    a, c = Vector(p0), Vector(p1)
    run = (c - a).normalized()
    side = run.cross(Vector(axis_up)).normalized()
    mats = mats or [TRIM, STRUCT, STEEL, RUBBER, TRIM]
    off = [(k - (n - 1) / 2) * (2 * r + gap) for k in range(n)]
    for k in range(n):
        b.fine.cyl(a + side * off[k], c + side * off[k], r * (1.0 if k % 2 == 0 else 0.8), mats[k % len(mats)], seg=10)
    cnt = max(1, int((c - a).length / clamps))
    for j in range(cnt + 1):
        p = a + (c - a) * (j / cnt)
        b.fine.box(p - side * (off[-1] + r + 0.02) - Vector((0.03, 0.03, 0.03)) + Vector((0, 0, 0)), p + side * (off[-1] + r + 0.02) + Vector((0.03, 0.03, 0.03)), STRUCT)


def duct_run(b: SParts, p0, p1, w: float = 0.6, h: float = 0.4, mat: str = STEEL, ribs: float = 1.0) -> None:
    """A rectangular air duct between two points (axis-aligned runs only) with joint flanges every `ribs` m."""
    a, c = Vector(p0), Vector(p1)
    lo = Vector((min(a.x, c.x), min(a.y, c.y), min(a.z, c.z)))
    hi = Vector((max(a.x, c.x), max(a.y, c.y), max(a.z, c.z)))
    if abs(a.x - c.x) > abs(a.y - c.y):                                   # along x
        b.body.box((lo.x, lo.y - w / 2, lo.z - h / 2), (hi.x, lo.y + w / 2, lo.z + h / 2), mat)
        x = lo.x + ribs
        while x < hi.x - 0.05:
            b.fine.box((x - 0.03, lo.y - w / 2 - 0.025, lo.z - h / 2 - 0.025), (x + 0.03, lo.y + w / 2 + 0.025, lo.z + h / 2 + 0.025), TRIM)
            x += ribs
    else:                                                                  # along y
        b.body.box((lo.x - w / 2, lo.y, lo.z - h / 2), (lo.x + w / 2, hi.y, lo.z + h / 2), mat)
        y = lo.y + ribs
        while y < hi.y - 0.05:
            b.fine.box((lo.x - w / 2 - 0.025, y - 0.03, lo.z - h / 2 - 0.025), (lo.x + w / 2 + 0.025, y + 0.03, lo.z + h / 2 + 0.025), TRIM)
            y += ribs


def tank_v(b: SParts, r: float = 0.9, h: float = 2.8, mat: str = STEEL, band: str = "science", tag: str | None = None) -> None:
    """A vertical pressure tank: a cylinder with domed ends, welded bands, a ladder, a level gauge with a lit scale and a stub of pipe at the foot; `tag`: the label tile on it
    (an atlas tile such as eq_water; by default one of the bridge's tags by size)."""
    b.body.cyl((0, 0, 0.30), (0, 0, h - 0.30), r, mat, seg=24)
    b.body.sphere((0, 0, h - 0.30), r, mat, seg=24, rings=8, squash=(1, 1, 0.35))
    b.body.sphere((0, 0, 0.30), r, mat, seg=24, rings=8, squash=(1, 1, 0.35))
    for k in range(4):
        z = 0.45 + k * (h - 0.9) / 3
        ring(b.fine, 0.0, 0.0, z, r - 0.005, 0.02, 0.07, STRUCT, 24)
    for k in range(4):
        a = math.radians(90 * k + 45)
        b.body.box((r * math.cos(a) * 0.96 - 0.05, r * math.sin(a) * 0.96 - 0.05, 0.0), (r * math.cos(a) * 0.96 + 0.05, r * math.sin(a) * 0.96 + 0.05, 0.34), TRIM)
    b.fine.box((r - 0.02, -0.04, 0.6), (r + 0.04, 0.04, h - 0.8), TRIM)                                       # the gauge
    b.emit.lamp_box((r + 0.04, -0.015, 0.7), (r + 0.045, 0.015, h - 0.9), dim(band), LAMP_DIM)
    b.emit.lamp_box((r + 0.04, -0.03, 0.7 + (h - 1.6) * 0.62), (r + 0.05, 0.03, 0.74 + (h - 1.6) * 0.62), "white", LAMP)
    b.fine.cyl((0, r + 0.0, 0.2), (0, r + 0.35, 0.2), 0.06, TRIM, seg=10)
    b.emit.label((r * 0.7, -r * 0.7, 1.3), 0.5, 0.125, (0.7, -0.7, 0), tag or "tag_%02d" % ((int(r * 10 + h * 10)) % 12))


def pump_set(b: SParts, l: float = 1.6, accent: str = "engineering") -> None:
    """A motor-pump set on a skid, its axis along y: a squat electric motor with cooling fins, a coupling, a volute casing with two flanged pipes up and a gauge."""
    b.body.box((-0.4, -l / 2, 0.0), (0.4, l / 2, 0.10), STRUCT)
    b.body.cyl((0, -l / 2 + 0.2, 0.42), (0, -0.1, 0.42), 0.30, CRATE_GREY, seg=18)
    for k in range(7):
        y = -l / 2 + 0.25 + k * 0.1
        b.fine.cyl((0, y, 0.42), (0, y + 0.03, 0.42), 0.325, TRIM, seg=18)
    b.body.cyl((0, -0.1, 0.42), (0, 0.15, 0.42), 0.07, STEEL, seg=10)
    b.body.cyl((0, 0.15, 0.42), (0, l / 2 - 0.15, 0.42), 0.27, STEEL, seg=18, r2=0.34)
    b.body.cyl((0, l / 2 - 0.15, 0.42), (0, l / 2 - 0.02, 0.42), 0.36, STEEL, seg=18)
    for sx in (-0.18, 0.18):
        b.body.cyl((sx, l / 2 - 0.4, 0.62), (sx, l / 2 - 0.4, 1.15), 0.075, TRIM, seg=10)
        ring(b.fine, sx, l / 2 - 0.4, 1.12, 0.075, 0.04, 0.04, STEEL, 12)
    b.fine.cyl((0.0, 0.2, 0.74), (0.0, 0.2, 0.9), 0.014, TRIM, seg=6)
    b.fine.cyl((0.0, 0.2, 0.9), (0.0, 0.2, 0.93), 0.06, DGLASS, seg=12)
    b.emit.lamp_box((0.28, -l / 2 + 0.22, 0.58), (0.31, -l / 2 + 0.3, 0.64), "green", LAMP_DIM)
    b.emit.lamp_box((-0.4, -l / 2, 0.02), (0.4, -l / 2 + 0.01, 0.08), dim(accent), LAMP_DIM)


def hv_cabinet(b: SParts, w: float = 0.9, d: float = 0.7, h: float = 2.2, bays: int = 1) -> None:
    """A high-voltage switchgear cabinet facing +x: a dark steel body, door(s) with a viewing window and a lit mimic, a red hazard header, an earthing bar."""
    hw = w * bays / 2
    b.body.box((-d / 2, -hw, 0.0), (d / 2, hw, h), CRATE_GREY)
    b.body.box((-d / 2 - 0.02, -hw - 0.01, h), (d / 2 + 0.02, hw + 0.01, h + 0.04), TRIM)
    for k in range(bays):
        y0 = -hw + k * w
        b.fine.box((d / 2, y0 + 0.03, 0.10), (d / 2 + 0.025, y0 + w - 0.03, h - 0.08), STRUCT)
        b.fine.box((d / 2 + 0.025, y0 + 0.14, 1.20), (d / 2 + 0.03, y0 + w - 0.14, 1.78), DGLASS)
        b.emit.lamp_box((d / 2 + 0.03, y0 + 0.2, 1.45), (d / 2 + 0.034, y0 + w - 0.2, 1.47), "amber", LAMP_DIM)
        b.emit.lamp_box((d / 2 + 0.03, y0 + 0.2, 1.52), (d / 2 + 0.034, y0 + 0.3, 1.58), "green", LAMP)
        b.fine.box((d / 2 + 0.025, y0 + w - 0.14, 0.9), (d / 2 + 0.06, y0 + w - 0.10, 1.1), TRIM)
        b.emit.label((d / 2 + 0.027, y0 + w / 2, h - 0.22), w - 0.2, (w - 0.2) / 4.0, (1, 0, 0), "hazard")
        b.emit.label((d / 2 + 0.027, y0 + w / 2, 0.45), min(0.5, w - 0.2), min(0.5, w - 0.2) / 4.0, (1, 0, 0), "icon_hv")


def battery_rack(b: SParts, w: float = 1.4, d: float = 0.8, h: float = 2.0, accent: str = "engineering") -> None:
    """A capacitor / battery rack facing +x: shelves of grey cell blocks with orange busbars and a charge bar graph per shelf."""
    b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.04, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.05):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.05, h), STRUCT)
    for k in range(4):
        z = 0.1 + k * (h - 0.2) / 4
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.04), STEEL)
        n = 5
        for j in range(n):
            y0 = -w / 2 + 0.08 + j * (w - 0.16) / n
            b.body.box((-d / 2 + 0.06, y0, z + 0.04), (d / 2 - 0.05, y0 + (w - 0.16) / n - 0.025, z + 0.38), CRATE_GREY)
            b.fine.box((d / 2 - 0.06, y0 + 0.03, z + 0.12), (d / 2 - 0.03, y0 + 0.07, z + 0.34), CRATE_ORANGE)
        b.emit.lamp_box((d / 2 - 0.005, -w / 2 + 0.1, z + 0.40), (d / 2 + 0.005, w / 2 - 0.1 - (k % 3) * 0.2, z + 0.43), accent, LAMP_DIM)


# ----------------------------------------------------------------------------------------------------------------------------- wall
def wall_rack_panel(b: SParts, w: float = 2.4, h: float = 2.2, tile: str = "scr_map", accent: str = "cyan") -> None:
    """A wall-mounted display wall facing +x: a brushed frame, a dark panel, a big picture and a strip of status lights below it."""
    b.body.box((-0.07, -w / 2 - 0.05, 0.0), (0.0, w / 2 + 0.05, h), TRIM)
    b.body.box((-0.06, -w / 2, 0.05), (0.002, w / 2, h - 0.05), DGLASS)
    b.emit.label((0.004, 0.0, h * 0.58), w - 0.1, (h - 0.55), (1, 0, 0), tile)
    for k in range(int(w / 0.18)):
        y = -w / 2 + 0.12 + k * 0.18
        b.emit.lamp_box((0.004, y, 0.14), (0.008, y + 0.08, 0.17), (accent, "green", "amber", accent)[k % 4], LAMP_DIM)


# --------------------------------------------------------------------------------------------------------------------- small helpers
def lamp_sphere(fb, c, r: float, cell: str, mat: str = LAMP_DIM, seg: int = 14, rings: int = 8, squash=(1.0, 1.0, 1.0)) -> None:
    """A glowing sphere (a hologram globe, an indicator ball): a sphere painted with a lamp cell."""
    from bridge3_lib import cell_uv
    faces = fb.sphere(c, r, mat, seg=seg, rings=rings, squash=squash)
    fb._paint(faces, cell_uv(cell))


def vertical_ring(b: SParts, x: float, y: float, zc: float, r: float, w: float, th: float, mat: str, seg: int = 36) -> None:
    """A ring standing on edge in the xz plane (axis along y) centred at (x, y, zc): inner radius r, radial width w, thickness th along y."""
    with b.at(T(x, y - th / 2, zc) @ Rx(-90)):
        ring(b.body, 0.0, 0.0, 0.0, r, w, th, mat, seg)


def bench_grow(b: SParts, l: float = 5.0, d: float = 1.1, tiers: int = 2, seed: int = 1, lamp: str = "science") -> None:
    """A grow bench along y: a steel table with two tiers of planter trays under a long lamp bar each, plants (soft blobs), a water line."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -l / 2, 0.0), (d / 2, l / 2, 0.06), STRUCT)
    for sy in (-l / 2 + 0.05, l / 2 - 0.1):
        for sx in (-d / 2 + 0.04, d / 2 - 0.09):
            b.body.box((sx, sy, 0.0), (sx + 0.05, sy + 0.05, 1.9), STEEL)
    for t in range(tiers):
        z = 0.78 + t * 0.62
        b.body.box((-d / 2, -l / 2 + 0.03, z), (d / 2, l / 2 - 0.03, z + 0.04), STEEL)
        b.soft.box((-d / 2 + 0.06, -l / 2 + 0.1, z + 0.04), (d / 2 - 0.06, l / 2 - 0.1, z + 0.12), SOIL)
        n = int(l / 0.42)
        for k in range(n):
            y = -l / 2 + 0.22 + k * (l - 0.44) / max(1, n - 1)
            hh = rng.uniform(0.14, 0.3)
            b.soft.sphere((rng.uniform(-0.1, 0.1), y, z + 0.14 + hh * 0.5), rng.uniform(0.11, 0.17), LEAF, seg=8, rings=6, squash=(1, 1, hh / 0.2))
        b.body.box((-d / 2 + 0.05, -l / 2 + 0.05, z + 0.5), (d / 2 - 0.05, l / 2 - 0.05, z + 0.54), TRIM)
        b.emit.lamp_box((-d / 2 + 0.1, -l / 2 + 0.1, z + 0.495), (d / 2 - 0.1, l / 2 - 0.1, z + 0.50), lamp if t % 2 == 0 else "white_warm", LAMP)


def aquarium(b: SParts, w: float = 3.2, d: float = 0.8, h: float = 2.1, seed: int = 1, water: str = "cyan_dim") -> None:
    """A wall tank facing +x: a dark base cabinet, a glowing water body between a frame of brushed bars, plants and a few drifting lights, a lamp hood on top."""
    rng = random.Random(seed)
    hw = w / 2
    b.body.box((-d / 2, -hw, 0.0), (d / 2, hw, 0.62), COMPOSITE)
    b.body.box((-d / 2 - 0.02, -hw - 0.02, 0.62), (d / 2 + 0.02, hw + 0.02, 0.68), STEEL)
    b.body.box((-d / 2, -hw, h - 0.16), (d / 2, hw, h), COMPOSITE)
    for sy in (-hw, hw - 0.06):
        b.body.box((-d / 2, sy, 0.68), (d / 2, sy + 0.06, h - 0.16), TRIM)
    b.emit.lamp_box((-d / 2 + 0.04, -hw + 0.06, 0.74), (d / 2 - 0.1, hw - 0.06, h - 0.2), water, LAMP_DIM)                # the water
    b.fine.box((d / 2 - 0.1, -hw + 0.06, 0.68), (d / 2 - 0.08, hw - 0.06, h - 0.16), TRIM)             # the front frame line
    for k in range(int(w / 0.5)):
        y = -hw + 0.3 + k * 0.5 + rng.uniform(-0.1, 0.1)
        hh = rng.uniform(0.5, 1.3)
        b.soft.sphere((d / 2 - 0.22, y, 0.74 + hh * 0.5), rng.uniform(0.1, 0.17), LEAF, seg=8, rings=6, squash=(1, 1, hh / 0.2))
    b.body.box((-d / 2 + 0.02, -hw + 0.1, 0.68), (-d / 2 + 0.2, hw - 0.1, 0.9), SOIL)
    b.emit.lamp_box((-d / 2 + 0.1, -hw + 0.1, h - 0.18), (d / 2 - 0.1, hw - 0.1, h - 0.165), "white_cool", LAMP)
    b.emit.label((d / 2 + 0.002, 0.0, 0.34), 0.5, 0.125, (1, 0, 0), "eq_water")


def glovebox(b: SParts, w: float = 1.6, d: float = 0.9, h: float = 1.5) -> None:
    """A sealed glovebox on a bench height base, facing +x: a dark window with two glove ports and an airlock drawer on the side."""
    hw = w / 2
    b.body.box((-d / 2, -hw, 0.0), (d / 2, hw, 0.78), COMPOSITE)
    b.body.box((-d / 2, -hw, 0.78), (d / 2, hw, 0.82), STEEL)
    b.body.box((-d / 2, -hw, 0.82), (d / 2, hw, h), STEEL)
    b.fine.box((d / 2 - 0.02, -hw + 0.08, 0.9), (d / 2 + 0.01, hw - 0.08, h - 0.08), DGLASS)
    for sy in (-0.35, 0.35):
        b.fine.cyl((d / 2 + 0.01, sy, 1.15), (d / 2 + 0.07, sy, 1.15), 0.085, RUBBER, seg=12)
        b.fine.cyl((d / 2 + 0.07, sy, 1.15), (d / 2 + 0.22, sy, 1.0), 0.07, RUBBER, seg=10)
    b.fine.box((-0.15, hw, 0.9), (0.15, hw + 0.2, 1.2), TRIM)
    b.emit.lamp_box((d / 2 + 0.005, -0.1, h - 0.09), (d / 2 + 0.012, 0.1, h - 0.07), "green", LAMP)
    b.emit.label((d / 2 + 0.003, 0.0, 0.4), 0.6, 0.15, (1, 0, 0), "eq_lab")


def transformer(b: SParts, w: float = 1.6, d: float = 1.2, h: float = 1.9) -> None:
    """A dry-type power transformer facing +x: a grey steel tank on a base with rows of cooling fins on both sides, a lid, three porcelain bushings with caps on top, a
    nameplate, a temperature gauge and a lit status."""
    hw = w / 2
    b.body.box((-d / 2 - 0.04, -hw - 0.04, 0.0), (d / 2 + 0.04, hw + 0.04, 0.12), STRUCT)
    b.body.box((-d / 2, -hw, 0.12), (d / 2, hw, h - 0.3), CRATE_GREY)
    b.body.box((-d / 2 - 0.03, -hw - 0.03, h - 0.3), (d / 2 + 0.03, hw + 0.03, h - 0.24), TRIM)
    for sy in (-1, 1):
        for k in range(8):
            z = 0.3 + k * (h - 0.95) / 7
            lo, hi = sorted((sy * hw, sy * (hw + 0.07)))
            b.fine.box((-d / 2 + 0.06, lo, z), (d / 2 - 0.06, hi, z + 0.11), STEEL)
    for k in range(3):
        y = (k - 1) * w * 0.3
        b.body.cyl((0, y, h - 0.24), (0, y, h + 0.05), 0.075, IVORY, seg=12)
        for j in range(3):
            b.fine.cyl((0, y, h - 0.2 + j * 0.08), (0, y, h - 0.17 + j * 0.08), 0.11, IVORY, seg=12)
        b.body.cyl((0, y, h + 0.05), (0, y, h + 0.12), 0.045, TRIM, seg=8)
    b.fine.box((d / 2, -0.25, 0.9), (d / 2 + 0.012, 0.25, 1.2), TRIM)
    b.emit.label((d / 2 + 0.014, 0.0, 1.05), 0.46, 0.115, (1, 0, 0), "tag_06")
    b.fine.cyl((d / 2, 0.45, 1.55), (d / 2 + 0.03, 0.45, 1.55), 0.07, DGLASS, seg=12)
    b.emit.lamp_box((d / 2, -0.55, 0.3), (d / 2 + 0.012, -0.47, 0.34), "green", LAMP_DIM)
