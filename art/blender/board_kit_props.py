"""ABBORDAGGI-3 — the boarding kit's props and the fallen (Blender builders; board_kit_defs.py has the frames and the budgets).

Every prop stands on the floor with its origin under the middle of its footprint, its front (the side a man uses) towards +x, his right hand towards +y. They are the Kharon Mandate's: heavy plate
on graphite frames, black iron, oxidised copper and verdigris, hazard paint worn to amber, cloth the colour of rust, lamps in the dim amber and red of a ship on emergency power, their words in stencil.
The game gives each a box of collision of its own (the instanced meshes carry none), so a prop is as solid as its footprint and no more.

The fallen are three poses of the same man in a dark coverall and a vest: on his back, face down, on his side (the game turns and mirrors them): soft shapes, a few hundred triangles.
"""
from __future__ import annotations

import math
import random

from bridge3_lib import Parts

from board_kit_defs import CLOTH, COPPER, FRAME, HAZARD, IRON, LAMP_DIM, LAMP_HOT, PLATE, SCREEN, SKIN, SOOT, STENCIL, UNIFORM, VERD
from board_kit_parts import _rot_x, _rot_y, _rot_z


# ============================================================================================================================ small helpers
def _label(b: Parts, text: str, c, h: float, facing=(1.0, 0.0, 0.0)) -> float:
    """Stencil lettering on a face of a prop (facing: the way the face looks); the plate behind it is the caller's."""
    return b.emit.text(text, c, h, facing, STENCIL, up=(0.0, 0.0, 1.0))


def _posts(b: Parts, hx: float, hy: float, z0: float, z1: float, t: float, mat: str = FRAME) -> None:
    """Four corner posts of a box (half sizes hx, hy), t square."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = (hx - t, hx) if sx > 0 else (-hx, -hx + t)
            y0, y1 = (hy - t, hy) if sy > 0 else (-hy, -hy + t)
            b.body.box((x0, y0, z0), (x1, y1, z1), mat)


def _wheel(b: Parts, c, r: float, axis: str = "x", mat: str = COPPER, spokes: int = 6) -> None:
    """A valve wheel: a hub, a spoked rim as spokes of cylinders, in the plane across `axis` (x: the wheel faces +x)."""
    cx, cy, cz = c
    if axis == "x":
        b.fine.cyl((cx - 0.02, cy, cz), (cx + 0.05, cy, cz), 0.03, FRAME, seg=8)
        for k in range(spokes):
            a = k * math.pi / (spokes / 2)
            b.fine.cyl((cx + 0.04, cy, cz), (cx + 0.04, cy + math.cos(a) * r, cz + math.sin(a) * r), 0.013, mat, seg=5)
    else:
        b.fine.cyl((cx, cy - 0.02, cz), (cx, cy + 0.05, cz), 0.03, FRAME, seg=8)
        for k in range(spokes):
            a = k * math.pi / (spokes / 2)
            b.fine.cyl((cx, cy + 0.04, cz), (cx + math.cos(a) * r, cy + 0.04, cz + math.sin(a) * r), 0.013, mat, seg=5)


def _gauge(b: Parts, c, r: float = 0.07, facing: str = "x") -> None:
    """A dial: a dark can with a lit face (dim amber)."""
    cx, cy, cz = c
    if facing == "x":
        b.fine.cyl((cx, cy, cz), (cx + 0.05, cy, cz), r, FRAME, seg=12)
        b.emit.lamp_cyl((cx + 0.05, cy, cz), (cx + 0.056, cy, cz), r * 0.75, "amber_dim", LAMP_DIM, seg=12)
    else:
        b.fine.cyl((cx, cy, cz), (cx, cy + 0.05, cz), r, FRAME, seg=12)
        b.emit.lamp_cyl((cx, cy + 0.05, cz), (cx, cy + 0.056, cz), r * 0.75, "amber_dim", LAMP_DIM, seg=12)


# ============================================================================================================================ stores
def crate(b: Parts) -> None:
    """A supply crate, 0.9 m square, 0.85 high: plated sides in a frame with cross braces, a lid with straps, STORES stencilled on its front."""
    hx = hy = 0.45
    h = 0.85
    fb = b.body
    fb.box((-hx, -hy, 0.05), (hx, hy, h), PLATE)
    fb.box((-hx - 0.012, -hy - 0.012, 0.0), (hx + 0.012, hy + 0.012, 0.07), FRAME)                       # the skid
    fb.box((-hx - 0.015, -hy - 0.015, h - 0.05), (hx + 0.015, hy + 0.015, h + 0.02), FRAME)                # the lid's rim
    _posts(b, hx + 0.012, hy + 0.012, 0.07, h - 0.05, 0.07)
    for z in (0.07 + 0.05, h - 0.05 - 0.08):
        for sx in (-1, 1):
            fb.box((sx * (hx + 0.012) - 0.012, -hy, z), (sx * (hx + 0.012) + 0.012, hy, z + 0.05), FRAME)
        for sy in (-1, 1):
            fb.box((-hx, sy * (hy + 0.012) - 0.012, z), (hx, sy * (hy + 0.012) + 0.012, z + 0.05), FRAME)
    # the cross braces: a diagonal on each face
    zc = 0.07 + (h - 0.05 - 0.07) / 2
    span = h - 0.05 - 0.07 - 0.2
    ln = math.hypot(2 * hy - 0.28, span)
    ang = math.degrees(math.atan2(span, 2 * hy - 0.28))
    for sx in (-1, 1):
        b.fine.cbox((sx * (hx + 0.014), 0.0, zc), (0.022, ln, 0.05), FRAME, rot=_rot_x(ang if sx > 0 else -ang))
    ln2 = math.hypot(2 * hx - 0.28, span)
    ang2 = math.degrees(math.atan2(span, 2 * hx - 0.28))
    for sy in (-1, 1):
        b.fine.cbox((0.0, sy * (hy + 0.014), zc), (ln2, 0.022, 0.05), FRAME, rot=_rot_y(-ang2 if sy > 0 else ang2))
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.fine.box((sx * (hx + 0.012) - 0.02, sy * (hy + 0.012) - 0.02, h + 0.02), (sx * (hx + 0.012) + 0.02, sy * (hy + 0.012) + 0.02, h + 0.045), IRON)    # corner bolts
    for y in (-0.22, 0.22):
        b.fine.box((-hx, y - 0.025, h + 0.02), (hx, y + 0.025, h + 0.036), IRON)                               # the lid's straps
    b.fine.box((hx + 0.012, -0.2, 0.34), (hx + 0.03, 0.2, 0.52), IRON)                                         # the stencil plate
    _label(b, "STORES", (hx + 0.0305, 0.0, 0.43), 0.1)
    for k in (-1, 1):
        b.fine.box((-0.08, k * (hy + 0.012) - 0.015, 0.6), (0.08, k * (hy + 0.012) + 0.015 + (0.03 if k > 0 else -0.03), 0.64), COPPER)    # a handle each side


def crate_long(b: Parts) -> None:
    """A long crate, 1.8 x 0.6 x 0.6 (it stands with its length along y): munitions, AMMO on the front."""
    hx, hy, h = 0.3, 0.9, 0.6
    fb = b.body
    fb.box((-hx, -hy, 0.05), (hx, hy, h), PLATE)
    fb.box((-hx - 0.012, -hy - 0.012, 0.0), (hx + 0.012, hy + 0.012, 0.07), FRAME)
    fb.box((-hx - 0.015, -hy - 0.015, h - 0.05), (hx + 0.015, hy + 0.015, h + 0.02), FRAME)
    for y in (-0.82, -0.3, 0.3, 0.82):
        fb.box((-hx - 0.014, y - 0.035, 0.07), (hx + 0.014, y + 0.035, h - 0.05), FRAME)                       # the ribs
    for sx in (-1, 1):
        b.fine.cbox((sx * (hx + 0.016), 0.0, 0.33), (0.02, 1.5, 0.04), IRON, rot=None)                           # a rail down each long side
    b.fine.box((hx + 0.014, -0.2, 0.25), (hx + 0.03, 0.2, 0.42), IRON)
    _label(b, "AMMO", (hx + 0.0305, 0.0, 0.335), 0.09)
    b.fine.box((hx + 0.014, 0.52, 0.2), (hx + 0.034, 0.74, 0.28), HAZARD)                                       # a hazard tag
    for y in (-0.55, 0.55):
        b.fine.box((-0.09, y - 0.02, h + 0.02), (0.09, y + 0.02, h + 0.04), COPPER)                           # the lid's handles
    for sy in (-1, 1):
        b.fine.cbox((0.0, sy * (hy + 0.014), 0.33), (0.2, 0.02, 0.08), COPPER)


def barrel(b: Parts) -> None:
    """A drum: a plated cylinder in hoops, a bung, FUEL on a plate."""
    r, h = 0.3, 0.95
    b.body.cyl((0.0, 0.0, 0.0), (0.0, 0.0, h), r, PLATE, seg=16)
    for z in (0.08, 0.47, 0.87):
        b.fine.cyl((0.0, 0.0, z - 0.035), (0.0, 0.0, z + 0.035), r + 0.014, FRAME, seg=16)
    b.fine.cyl((0.0, 0.0, h), (0.0, 0.0, h + 0.02), r - 0.025, IRON, seg=16)
    b.fine.cyl((0.12, 0.1, h + 0.02), (0.12, 0.1, h + 0.055), 0.045, COPPER, seg=8)
    b.fine.cyl((-0.13, -0.08, h + 0.02), (-0.13, -0.08, h + 0.04), 0.03, VERD, seg=8)
    b.fine.box((r - 0.02, -0.15, 0.55), (r + 0.016, 0.15, 0.78), IRON)
    _label(b, "FUEL", (r + 0.0165, 0.0, 0.665), 0.1)
    b.fine.box((r - 0.02, -0.15, 0.32), (r + 0.012, 0.15, 0.4), HAZARD)


def locker(b: Parts) -> None:
    """A free-standing locker, 0.5 deep, 0.9 wide, 2 high: two louvred doors with handles and numbers."""
    hx, hy, h = 0.25, 0.45, 2.0
    fb = b.body
    fb.box((-hx, -hy, 0.08), (hx, hy, h), FRAME)
    for i, y0 in enumerate((-0.43, 0.01)):
        fb.box((hx, y0, 0.12), (hx + 0.03, y0 + 0.42, h - 0.06), PLATE)
        for k in range(6):
            b.fine.box((hx + 0.03, y0 + 0.07, h - 0.4 + k * 0.06), (hx + 0.04, y0 + 0.35, h - 0.38 + k * 0.06), IRON)
        b.fine.box((hx + 0.03, y0 + (0.33 if i == 0 else 0.06), 0.95), (hx + 0.07, y0 + (0.37 if i == 0 else 0.10), 1.22), COPPER)
        b.fine.box((hx + 0.03, y0 + 0.13, 0.24), (hx + 0.037, y0 + 0.29, 0.31), IRON)
        b.emit.text(f"{i + 4:02d}", (hx + 0.0375, y0 + 0.21, 0.275), 0.04, (1.0, 0.0, 0.0), STENCIL, up=(0.0, 0.0, 1.0))
    for sx in (-1, 1):
        for sy in (-1, 1):
            fb.box((sx * (hx - 0.04) - 0.03, sy * (hy - 0.04) - 0.03, 0.0), (sx * (hx - 0.04) + 0.03, sy * (hy - 0.04) + 0.03, 0.08), IRON)
    fb.box((-hx - 0.012, -hy - 0.012, h), (hx + 0.012, hy + 0.012, h + 0.04), IRON)


def rack(b: Parts) -> None:
    """A storage rack, 0.6 deep, 1.6 wide, 2 high: four shelves in a frame with its stores (small cases, drums, a coil of cable)."""
    hx, hy, h = 0.3, 0.8, 2.0
    fb = b.body
    _posts(b, hx, hy, 0.0, h, 0.06)
    shelves = (0.12, 0.68, 1.24, 1.8)
    for z in shelves:
        fb.box((-hx, -hy, z), (hx, hy, z + 0.035), PLATE)
    fb.box((-hx, -hy, 0.0), (-hx + 0.02, hy, h), IRON)                                                  # the back plate (thin)
    ln = math.hypot(2 * hy - 0.1, h - 0.1) - 0.1
    for sgn in (-1, 1):                                                                                  # the back's cross braces
        b.fine.cbox((-hx + 0.03, 0.0, h / 2), (0.02, ln, 0.05), FRAME, rot=_rot_x(sgn * math.degrees(math.atan2(h - 0.1, 2 * hy - 0.1))))
    rng = random.Random(41)
    for z in shelves:
        y = -hy + 0.1
        while y < hy - 0.25:
            kind = rng.random()
            if kind < 0.5:
                w = rng.uniform(0.28, 0.5)
                d = rng.uniform(0.28, 0.4)
                hh = rng.uniform(0.2, 0.42)
                b.fine.box((-0.02 - d / 2, y, z + 0.035), (-0.02 + d / 2, y + w, z + 0.035 + hh), PLATE if rng.random() < 0.6 else IRON)
                b.fine.box((-0.02 - d / 2 - 0.004, y + w * 0.1, z + 0.035 + hh * 0.5), (-0.02 + d / 2 + 0.004, y + w * 0.9, z + 0.035 + hh * 0.5 + 0.035), FRAME)
            elif kind < 0.8:
                w = 0.26
                b.fine.cyl((-0.02, y + w / 2, z + 0.035), (-0.02, y + w / 2, z + 0.035 + rng.uniform(0.3, 0.45)), w / 2, VERD if rng.random() < 0.3 else COPPER, seg=10)
            else:
                w = 0.3
                b.fine.cyl((0.02, y + 0.02, z + 0.035 + 0.1), (0.02, y + 0.02 + w, z + 0.035 + 0.1), 0.1, SOOT, seg=8)
            y += w + rng.uniform(0.04, 0.12)
    b.fine.box((hx, -hy + 0.02, 1.8 + 0.035), (hx + 0.012, hy - 0.02, 1.8 + 0.1), IRON)
    _label(b, "LOCKER 3", (hx + 0.0125, 0.0, 1.8 + 0.067), 0.05)


# ============================================================================================================================ the crew's rooms
def bunk(b: Parts) -> None:
    """A double bunk, 0.9 deep and 2 m long (along y), 1.9 high: iron frame, two mattresses in rust-red blankets with a pillow each, a ladder at the end, a drawer under."""
    hx, hy = 0.45, 1.0
    fb = b.body
    _posts(b, hx, hy, 0.0, 1.9, 0.06)
    for z in (0.34, 1.12):
        for sx in (-1, 1):
            fb.box((sx * (hx - 0.03) - 0.03, -hy, z), (sx * (hx - 0.03) + 0.03, hy, z + 0.07), FRAME)         # the side rails
        for sy in (-1, 1):
            fb.box((-hx, sy * (hy - 0.03) - 0.03, z), (hx, sy * (hy - 0.03) + 0.03, z + 0.07), FRAME)
        fb.box((-hx + 0.06, -hy + 0.06, z + 0.035), (hx - 0.06, hy - 0.06, z + 0.06), IRON)                  # the slats' plate
    sb = b.soft
    for z in (0.34, 1.12):
        sb.box((-hx + 0.08, -hy + 0.08, z + 0.06), (hx - 0.08, hy - 0.08, z + 0.17), CLOTH)                       # the mattress
        sb.box((-hx + 0.07, -hy + 0.45, z + 0.17), (hx - 0.07, hy - 0.08, z + 0.19), CLOTH)                      # the blanket over the legs, a little proud
        sb.sphere((0.0, -hy + 0.3, z + 0.22), 0.16, CLOTH, seg=8, rings=5, squash=(1.1, 1.2, 0.5))              # the pillow
    # the drawer under the lower bunk and a reading lamp on the upper
    fb.box((-hx + 0.06, hy - 0.62, 0.06), (hx - 0.06, hy - 0.08, 0.3), FRAME)
    b.fine.box((hx - 0.06, hy - 0.5, 0.15), (hx - 0.03, hy - 0.2, 0.19), COPPER)
    # the ladder at the +y end
    for x in (-0.12, 0.12):
        b.fine.cyl((x, hy + 0.03, 0.05), (x, hy + 0.03, 1.5), 0.018, COPPER, seg=6)
    for k in range(5):
        z = 0.28 + k * 0.28
        b.fine.cyl((-0.12, hy + 0.03, z), (0.12, hy + 0.03, z), 0.014, COPPER, seg=6)
    b.fine.box((hx - 0.02, hy - 0.05, 1.35), (hx + 0.012, hy - 0.01, 1.8), IRON)                                # the number plate on the post
    b.emit.text("B-04", (hx + 0.0125, hy - 0.03, 1.58), 0.04, (1.0, 0.0, 0.0), STENCIL, up=(0.0, 0.0, 1.0))


def table(b: Parts) -> None:
    """A mess table, 0.9 x 1.6, 0.78 high: a plated top in a rim on two trestles, trays and cups left on it."""
    hx, hy = 0.45, 0.8
    fb = b.body
    fb.box((-hx, -hy, 0.73), (hx, hy, 0.78), PLATE)
    for sx in (-1, 1):
        fb.box((sx * hx - (0.025 if sx > 0 else -0.0), -hy, 0.7), (sx * hx + (0.0 if sx > 0 else 0.025), hy, 0.8), FRAME)
    for sy in (-1, 1):
        fb.box((-hx, sy * hy - (0.025 if sy > 0 else -0.0), 0.7), (hx, sy * hy + (0.0 if sy > 0 else 0.025), 0.8), FRAME)
    for y in (-0.6, 0.6):
        for x in (-0.36, 0.36):
            fb.box((x - 0.035, y - 0.035, 0.0), (x + 0.035, y + 0.035, 0.73), FRAME)
        fb.box((-0.36, y - 0.025, 0.12), (0.36, y + 0.025, 0.17), FRAME)
        fb.box((-0.4, y - 0.05, 0.0), (0.4, y + 0.05, 0.03), IRON)
    for (y, rot) in ((-0.5, 0.0), (0.38, 15.0)):
        b.fine.cbox((0.12, y, 0.795), (0.34, 0.26, 0.03), IRON, rot=_rot_z(rot))
    for (x, y) in ((0.12, -0.5), (-0.1, -0.1), (0.2, 0.62)):
        b.fine.cyl((x, y, 0.78), (x, y, 0.86), 0.04, COPPER, seg=8)
    b.fine.cbox((-0.18, 0.4, 0.785), (0.26, 0.18, 0.012), FRAME, rot=_rot_z(-20.0))
    b.emit.lamp_cbox((-0.18, 0.4, 0.792), (0.2, 0.12, 0.004), "amber_dim", LAMP_DIM, rot=_rot_z(-20.0))


def bench(b: Parts) -> None:
    """A bench, 0.35 x 1.6, 0.46 high: a cushion on a plated seat, two folded legs."""
    hx, hy = 0.175, 0.8
    b.body.box((-hx, -hy, 0.4), (hx, hy, 0.44), PLATE)
    b.body.box((-hx - 0.01, -hy, 0.37), (hx + 0.01, hy, 0.4), FRAME)
    for y in (-0.62, 0.62):
        b.body.box((-hx + 0.02, y - 0.03, 0.0), (hx - 0.02, y + 0.03, 0.4), FRAME)
        b.body.box((-hx - 0.03, y - 0.05, 0.0), (hx + 0.03, y + 0.05, 0.03), IRON)
    b.soft.box((-hx + 0.01, -hy + 0.05, 0.44), (hx - 0.01, hy - 0.05, 0.49), CLOTH)


def console(b: Parts) -> None:
    """A dead console, 0.7 deep, 1.2 wide, 1.15 high: a cabinet with a sloped panel of keys, a screen on a bracket (dark glass with a trace of amber), a few dim lamps. Its front is +x."""
    fb = b.body
    fb.box((-0.35, -0.6, 0.0), (0.3, 0.6, 0.72), FRAME)
    fb.box((-0.35, -0.6, 0.0), (0.35, 0.6, 0.06), IRON)                                                  # the plinth
    for k in range(3):
        y0 = -0.56 + k * 0.38
        fb.box((0.3, y0, 0.1), (0.322, y0 + 0.34, 0.66), PLATE)                                           # three panels on the cabinet's front
        b.fine.box((0.322, y0 + 0.12, 0.34), (0.34, y0 + 0.22, 0.4), COPPER)
    fb.extrude_y([(-0.35, 0.72), (0.35, 0.72), (0.2, 0.9), (-0.35, 0.9)], -0.6, 0.6, PLATE)               # the desk's slope
    for r in range(4):
        for c in range(14):
            x = 0.31 - r * 0.1
            z = 0.735 + r * 0.04
            y = -0.52 + c * 0.08
            b.fine.box((x - 0.035, y, z), (x + 0.035, y + 0.06, z + 0.022), IRON if (r + c) % 5 else COPPER)
    fb.box((-0.35, -0.6, 0.9), (-0.15, 0.6, 1.1), FRAME)                                                  # the housing of the screen
    b.body.cbox((-0.12, 0.0, 1.0), (0.05, 1.0, 0.36), SCREEN, rot=_rot_y(-14.0))                              # the screen, tilted back
    b.fine.cbox((-0.135, 0.0, 1.0), (0.02, 1.08, 0.44), FRAME, rot=_rot_y(-14.0))
    for y in (-0.55, -0.45, 0.45, 0.55):
        b.emit.lamp_box((0.28, y - 0.015, 0.7), (0.31, y + 0.015, 0.718), "amber_dim" if y > 0 else "red_dim", LAMP_DIM)
    b.fine.cyl((0.0, 0.0, 0.9), (0.0, 0.0, 0.95), 0.05, IRON, seg=8)


def bed(b: Parts) -> None:
    """A ward bed, 0.9 x 2.0, 0.85 high: a frame on wheels, a mattress under a blanket, rails, a drip stand and a bedside monitor."""
    hx, hy = 0.45, 1.0
    fb = b.body
    fb.box((-hx, -hy, 0.28), (hx, hy, 0.4), FRAME)
    for x in (-0.36, 0.36):
        for y in (-0.85, 0.85):
            b.fine.cyl((x, y, 0.05), (x, y, 0.28), 0.03, IRON, seg=6)
            b.fine.cyl((x, y, 0.0), (x, y, 0.06), 0.05, FRAME, seg=8)
    fb.box((-hx, -hy - 0.04, 0.28), (hx, -hy, 0.95), PLATE)                                               # the head board
    fb.box((-hx, hy, 0.28), (hx, hy + 0.03, 0.7), PLATE)                                                  # the foot board
    b.soft.box((-hx + 0.04, -hy + 0.05, 0.4), (hx - 0.04, hy - 0.05, 0.54), CLOTH)
    b.soft.box((-hx + 0.03, -0.25, 0.54), (hx - 0.03, hy - 0.06, 0.58), CLOTH)
    b.soft.sphere((0.0, -hy + 0.25, 0.6), 0.15, CLOTH, seg=8, rings=5, squash=(1.1, 1.3, 0.5))
    for sx in (-1, 1):
        for k in range(4):
            y = -0.3 + k * 0.32
            b.fine.cyl((sx * (hx - 0.01), y, 0.58), (sx * (hx - 0.01), y, 0.84), 0.012, IRON, seg=5)
        b.fine.cyl((sx * (hx - 0.01), -0.3, 0.84), (sx * (hx - 0.01), 0.66, 0.84), 0.013, IRON, seg=5)
    b.fine.cyl((hx + 0.12, -hy + 0.2, 0.0), (hx + 0.12, -hy + 0.2, 1.7), 0.015, IRON, seg=6)                    # the drip stand (it stands beside the bed)
    b.fine.cyl((hx + 0.12, -hy + 0.2, 1.7), (hx + 0.12, -hy + 0.55, 1.7), 0.012, IRON, seg=6)
    b.fine.cyl((hx + 0.04, -hy + 0.2, 0.0), (hx + 0.2, -hy + 0.2, 0.0), 0.03, FRAME, seg=6)
    b.body.cbox((0.0, -hy - 0.07, 0.8), (0.34, 0.03, 0.2), SCREEN, rot=None)
    b.emit.lamp_box((-0.12, -hy - 0.088, 0.79), (0.12, -hy - 0.083, 0.805), "amber_dim", LAMP_DIM)


def cell(b: Parts) -> None:
    """A brig cell, 1.8 deep and 2 wide, 2.3 high: iron bars on its front and sides, a plated back, a bunk shelf and a basin."""
    hx, hy, h = 0.9, 1.0, 2.3
    fb = b.body
    fb.box((-hx, -hy, 0.0), (hx, hy, 0.06), IRON)                                                         # the base
    fb.box((-hx - 0.02, -hy, 0.0), (-hx + 0.04, hy, h), PLATE)                                            # the back
    for z in (0.06, h - 0.06):
        fb.box((-hx, -hy, z - 0.03), (hx, -hy + 0.06, z + 0.03), FRAME)
        fb.box((-hx, hy - 0.06, z - 0.03), (hx, hy, z + 0.03), FRAME)
        fb.box((hx - 0.06, -hy, z - 0.03), (hx, hy, z + 0.03), FRAME)
    fb.box((-hx, -hy, h - 0.03), (hx, hy, h + 0.03), FRAME)
    for sy in (-1, 1):
        fb.box((-hx, sy * hy - (0.03 if sy > 0 else -0.0), 0.0), (hx, sy * hy + (0.0 if sy > 0 else 0.03), 0.06), FRAME)
    for k in range(13):                                                                                      # the front's bars
        y = -hy + 0.09 + k * (2 * hy - 0.18) / 12
        if abs(y - 0.55) < 0.28:
            continue                                                                                          # the door's gap (the leaf is a frame of its own)
        b.fine.cyl((hx - 0.03, y, 0.06), (hx - 0.03, y, h - 0.06), 0.017, IRON, seg=6)
    fb.box((hx - 0.06, 0.25, 0.06), (hx, 0.29, h - 0.06), FRAME)                                          # the door's posts and its leaf of bars
    fb.box((hx - 0.06, 0.81, 0.06), (hx, 0.85, h - 0.06), FRAME)
    for k in range(5):
        y = 0.32 + k * 0.1
        b.fine.cyl((hx - 0.03, y, 0.1), (hx - 0.03, y, h - 0.12), 0.015, IRON, seg=6)
    fb.box((hx - 0.07, 0.25, 1.0), (hx + 0.01, 0.85, 1.08), FRAME)
    b.fine.box((hx - 0.01, 0.78, 1.0), (hx + 0.035, 0.84, 1.14), COPPER)                                       # the lock
    for sy in (-1, 1):                                                                                         # the sides' bars
        for k in range(8):
            x = -hx + 0.14 + k * (2 * hx - 0.28) / 7
            b.fine.cyl((x, sy * (hy - 0.03), 0.06), (x, sy * (hy - 0.03), h - 0.06), 0.017, IRON, seg=6)
    fb.box((-hx + 0.04, -hy + 0.02, 0.42), (-0.1, -hy + 0.62, 0.48), PLATE)                              # the bunk shelf (along the left wall)
    fb.box((-hx + 0.04, -hy + 0.02, 0.0), (-0.1, -hy + 0.06, 0.42), FRAME)
    b.soft.box((-hx + 0.06, -hy + 0.04, 0.48), (-0.12, -hy + 0.6, 0.54), CLOTH)
    fb.box((-hx + 0.04, 0.35, 0.0), (-hx + 0.4, 0.95, 0.5), PLATE)                                        # a basin block
    b.fine.box((-hx + 0.12, 0.45, 0.5), (-hx + 0.32, 0.85, 0.53), IRON)
    b.fine.cyl((-hx + 0.22, 0.65, 0.53), (-hx + 0.22, 0.65, 0.62), 0.025, COPPER, seg=6)
    b.emit.lamp_box((hx - 0.045, 0.0, h - 0.2), (hx - 0.015, 0.14, h - 0.16), "red_dim", LAMP_DIM)


# ============================================================================================================================ the machinery
def machine(b: Parts) -> None:
    """A pump set, 0.9 x 1.4, 1.1 high (its shaft along y): an iron motor and a copper volute on one skid, an inlet standing up and an outlet to the front, a gauge, a hazard band."""
    fb = b.body
    fb.box((-0.45, -0.7, 0.0), (0.45, 0.7, 0.12), FRAME)
    _hazard_band_x(b, 0.45, -0.66, 0.66, 0.02, 0.1)
    fb.cyl((0.0, -0.66, 0.52), (0.0, -0.06, 0.52), 0.3, IRON, seg=14)                                    # the motor
    for y in (-0.6, -0.5, -0.4, -0.3, -0.2, -0.12):
        b.fine.cyl((0.0, y - 0.015, 0.52), (0.0, y + 0.015, 0.52), 0.325, FRAME, seg=14)
    fb.cyl((0.0, -0.7, 0.52), (0.0, -0.66, 0.52), 0.24, FRAME, seg=14)
    for y in (-0.55, -0.15):
        fb.box((-0.3, y - 0.05, 0.12), (0.3, y + 0.05, 0.24), FRAME)
    fb.cyl((0.0, -0.06, 0.52), (0.0, 0.1, 0.52), 0.1, FRAME, seg=10)                                      # the coupling
    fb.cyl((0.0, 0.1, 0.52), (0.0, 0.5, 0.52), 0.36, COPPER, seg=14)                                      # the pump
    fb.cyl((0.0, 0.5, 0.52), (0.0, 0.6, 0.52), 0.2, FRAME, seg=12)
    fb.cyl((0.0, 0.3, 0.52), (0.0, 0.3, 1.02), 0.12, COPPER, seg=10)                                      # the inlet up
    b.fine.cyl((0.0, 0.3, 1.0), (0.0, 0.3, 1.05), 0.17, VERD, seg=10)
    fb.cyl((0.0, 0.3, 0.52), (0.4, 0.3, 0.52), 0.09, COPPER, seg=10)                                      # the outlet to the front
    b.fine.cyl((0.38, 0.3, 0.52), (0.43, 0.3, 0.52), 0.14, VERD, seg=10)
    b.fine.box((-0.16, -0.5, 0.82), (0.16, -0.18, 0.96), FRAME)                                           # the terminal box
    b.fine.cyl((0.0, -0.34, 0.96), (0.0, -0.34, 1.12), 0.018, VERD, seg=6)
    _gauge(b, (0.33, 0.52, 0.78), 0.06)
    b.fine.box((0.45 - 0.01, -0.2, 0.15), (0.45 + 0.012, 0.2, 0.26), IRON)
    _label(b, "PUMP 2", (0.45 + 0.0125, 0.0, 0.205), 0.07)
    b.emit.lamp_box((0.44, 0.55, 0.15), (0.465, 0.62, 0.2), "red_dim", LAMP_DIM)


def _hazard_band_x(b: Parts, x: float, y0: float, y1: float, z0: float, z1: float) -> None:
    """A hazard band on the +x face of a prop at x (the stripes run across y)."""
    b.fine.box((x, y0, z0), (x + 0.008, y1, z1), IRON)
    step = 0.14
    n = int((y1 - y0) / step) + 2
    for k in range(-1, n):
        ya = y0 + k * step
        poly = [(ya, z0), (ya + step * 0.5, z0), (ya + step * 0.5 + (z1 - z0), z1), (ya + (z1 - z0), z1)]
        pts = [(min(max(py, y0), y1), pz) for (py, pz) in poly]
        if len(set(pts)) < 3 or max(p[0] for p in pts) - min(p[0] for p in pts) < 0.01:
            continue
        b.fine.extrude_x(pts, x + 0.008, x + 0.013, HAZARD)


def motor(b: Parts) -> None:
    """A motor-generator, 1.0 x 1.0, 1.2 high: a ribbed iron drum on a base frame with an end bell, a terminal box, conduits and a hazard band."""
    fb = b.body
    fb.box((-0.5, -0.5, 0.0), (0.5, 0.5, 0.14), FRAME)
    for x in (-0.3, 0.3):
        fb.box((x - 0.05, -0.5, 0.14), (x + 0.05, 0.5, 0.3), FRAME)
    fb.cyl((0.0, -0.46, 0.7), (0.0, 0.34, 0.7), 0.42, IRON, seg=16)
    for y in (-0.4, -0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3):
        b.fine.cyl((0.0, y - 0.015, 0.7), (0.0, y + 0.015, 0.7), 0.44, FRAME, seg=16)
    b.fine.sphere((0.0, 0.34, 0.7), 0.4, FRAME, seg=14, rings=6, squash=(1.0, 0.5, 1.0))                     # the end bell
    fb.cyl((0.0, -0.5, 0.7), (0.0, -0.46, 0.7), 0.3, FRAME, seg=14)
    b.fine.box((-0.2, -0.16, 1.1), (0.2, 0.16, 1.28), FRAME)                                              # the terminal box on top
    b.fine.box((-0.17, -0.13, 1.28), (0.17, 0.13, 1.3), IRON)
    for x in (-0.1, 0.0, 0.1):
        b.fine.cyl((x, 0.0, 1.28), (x, 0.0, 1.45), 0.02, VERD, seg=6)
    b.fine.cyl((-0.5, -0.3, 0.2), (-0.15, -0.3, 0.2), 0.03, VERD, seg=6)                                   # a conduit to the frame
    _hazard_band_x(b, 0.5, -0.45, 0.45, 0.02, 0.12)
    b.fine.box((0.4, -0.2, 0.62), (0.46, 0.2, 0.8), FRAME)                                                # the data plate on the drum's front
    _label(b, "GEN 1", (0.4605, 0.0, 0.71), 0.1)
    b.emit.lamp_box((0.44, 0.22, 0.88), (0.46, 0.3, 0.92), "red_dim", LAMP_DIM)


def tank(b: Parts) -> None:
    """A tank, 1.4 across and 2.2 high: a plated drum in bands with domed ends, a ladder, a level gauge, a pipe with a valve wheel, COOLANT on its front."""
    r, h = 0.7, 2.2
    b.body.cyl((0.0, 0.0, 0.1), (0.0, 0.0, h), r, PLATE, seg=18)
    b.body.cyl((0.0, 0.0, 0.0), (0.0, 0.0, 0.12), r - 0.06, FRAME, seg=18)
    b.fine.sphere((0.0, 0.0, h), r, PLATE, seg=18, rings=5, squash=(1.0, 1.0, 0.22))
    for z in (0.22, 0.85, 1.5, 2.1):
        b.fine.cyl((0.0, 0.0, z - 0.04), (0.0, 0.0, z + 0.04), r + 0.018, FRAME, seg=18)
    ang = math.radians(60.0)                                                                                # the ladder, up the right side of the drum
    lx, ly = math.cos(ang) * (r + 0.07), math.sin(ang) * (r + 0.07)
    for off in (-0.12, 0.12):
        x, y = lx - math.sin(ang) * off, ly + math.cos(ang) * off
        b.fine.cyl((x, y, 0.2), (x, y, 2.05), 0.017, COPPER, seg=6)
    for k in range(7):
        z = 0.35 + k * 0.27
        b.fine.cyl((lx - math.sin(ang) * -0.12, ly + math.cos(ang) * -0.12, z), (lx - math.sin(ang) * 0.12, ly + math.cos(ang) * 0.12, z), 0.012, COPPER, seg=5)
    for z in (0.5, 1.8):
        b.fine.box((lx - 0.03 + math.cos(ang) * -0.04, ly - 0.03 + math.sin(ang) * -0.04, z - 0.03), (lx + 0.03 + math.cos(ang) * -0.04, ly + 0.03 + math.sin(ang) * -0.04, z + 0.03), FRAME)
    b.fine.cyl((0.0, -0.55, 0.45), (r + 0.14, -0.55, 0.45), 0.07, COPPER, seg=10)                            # the pipe at the bottom, to the front
    b.fine.cyl((r + 0.1, -0.55, 0.45), (r + 0.16, -0.55, 0.45), 0.11, VERD, seg=10)
    _wheel(b, (r + 0.05, -0.55, 0.62), 0.1, "x")
    b.fine.cyl((r + 0.05, -0.55, 0.45), (r + 0.05, -0.55, 0.6), 0.025, FRAME, seg=6)
    gx = math.cos(math.radians(-25.0)) * (r + 0.02)
    gy = math.sin(math.radians(-25.0)) * (r + 0.02)
    b.fine.box((gx - 0.04, gy - 0.05, 0.4), (gx + 0.03, gy + 0.05, 1.8), FRAME)
    b.emit.lamp_box((gx + 0.03, gy - 0.015, 0.5), (gx + 0.045, gy + 0.015, 1.2), "amber_dim", LAMP_DIM)         # the level
    b.fine.box((r - 0.01, 0.2, 1.1), (r + 0.02, 0.62, 1.34), IRON)
    _label(b, "COOLANT", (r + 0.0205, 0.41, 1.22), 0.075, facing=(1.0, 0.0, 0.0))


def reactor(b: Parts) -> None:
    """A reactor stack, 1.2 across and 2.8 high: a black core in shield rings and heat fins, conduits up the sides, a hazard-banded base, red lamps."""
    r, h = 0.6, 2.8
    fb = b.body
    fb.cyl((0.0, 0.0, 0.0), (0.0, 0.0, 0.2), r + 0.06, FRAME, seg=18)
    fb.cyl((0.0, 0.0, 0.2), (0.0, 0.0, h - 0.2), 0.36, IRON, seg=16)
    for k in range(5):
        z = 0.32 + k * 0.5
        fb.cyl((0.0, 0.0, z), (0.0, 0.0, z + 0.3), r, PLATE, seg=18)                                       # the shield rings
        b.fine.cyl((0.0, 0.0, z - 0.02), (0.0, 0.0, z + 0.04), r + 0.03, FRAME, seg=18)
        b.fine.cyl((0.0, 0.0, z + 0.26), (0.0, 0.0, z + 0.32), r + 0.03, FRAME, seg=18)
    fb.cyl((0.0, 0.0, h - 0.2), (0.0, 0.0, h), r - 0.12, FRAME, seg=16)                                    # the cap
    b.fine.sphere((0.0, 0.0, h), r - 0.12, IRON, seg=14, rings=4, squash=(1.0, 1.0, 0.3))
    for k in range(8):
        a = k * math.pi / 4 + 0.2
        x, y = math.cos(a) * (r + 0.06), math.sin(a) * (r + 0.06)
        b.fine.cyl((x, y, 0.25), (x, y, h - 0.35), 0.035, COPPER if k % 2 else VERD, seg=6)               # the conduits
        b.fine.box((x - 0.03, y - 0.03, 0.6 + (k % 3) * 0.8), (x + 0.03, y + 0.03, 0.66 + (k % 3) * 0.8), FRAME)
    for z in (0.62, 1.12, 1.62, 2.12):                                                                      # the lamps on the rings, on the front
        b.emit.lamp_box((r + 0.02, -0.03, z), (r + 0.045, 0.03, z + 0.12), "red_dim", LAMP_DIM)
    b.fine.box((r + 0.02, -0.18, 0.05), (r + 0.06, 0.18, 0.17), IRON)
    _label(b, "CORE 1", (r + 0.061, 0.0, 0.11), 0.06)
    b.emit.lamp_cyl((0.0, 0.0, h + 0.07), (0.0, 0.0, h + 0.1), 0.05, "red", LAMP_HOT, seg=10)


def breech(b: Parts) -> None:
    """A gun breech, 1.4 deep and 1.1 wide, 1.5 high: the barrel's stub into the wall (towards -x), the breech block, recoil cylinders, a loading tray and a ready lamp. It is worked from +x."""
    fb = b.body
    for sy in (-1, 1):
        fb.box((-0.45, sy * 0.5 - 0.04, 0.0), (0.55, sy * 0.5 + 0.04, 1.4), FRAME)                          # the cradle's cheeks
        fb.box((-0.45, sy * 0.5 - 0.06, 0.0), (0.55, sy * 0.5 + 0.06, 0.1), IRON)
    fb.box((-0.2, -0.5, 0.0), (0.5, 0.5, 0.1), IRON)
    fb.box((0.1, -0.4, 0.45), (0.6, 0.4, 1.15), IRON)                                                      # the breech block
    fb.box((0.6, -0.34, 0.55), (0.66, 0.34, 1.05), FRAME)                                                  # its face plate (the breech door)
    b.fine.cyl((0.66, 0.0, 0.8), (0.74, 0.0, 0.8), 0.1, COPPER, seg=10)
    _wheel(b, (0.7, 0.0, 0.8), 0.17, "x", mat=COPPER, spokes=4)
    fb.cyl((-0.7, 0.0, 0.8), (0.1, 0.0, 0.8), 0.24, IRON, seg=14)                                           # the barrel's stub
    for x in (-0.55, -0.1):
        b.fine.cyl((x - 0.03, 0.0, 0.8), (x + 0.03, 0.0, 0.8), 0.27, FRAME, seg=14)
    for sy in (-1, 1):                                                                                      # the recoil cylinders over it
        fb.cyl((-0.5, sy * 0.3, 1.2), (0.3, sy * 0.3, 1.2), 0.07, COPPER, seg=8)
        b.fine.cyl((-0.5, sy * 0.3, 1.2), (-0.35, sy * 0.3, 1.2), 0.09, VERD, seg=8)
    fb.box((0.2, -0.25, 0.3), (0.7, 0.25, 0.4), FRAME)                                                      # the loading tray, folded out
    for sy in (-1, 1):
        b.fine.box((0.2, sy * 0.25 - (0.02 if sy > 0 else 0.0), 0.4), (0.7, sy * 0.25 + (0.0 if sy > 0 else 0.02), 0.46), FRAME)
    b.fine.box((0.2, -0.46, 1.0), (0.5, -0.4, 1.3), PLATE)                                                  # the elevation quadrant on the left cheek
    b.emit.lamp_box((0.62, 0.22, 1.1), (0.67, 0.3, 1.14), "red_dim", LAMP_DIM)
    b.emit.lamp_box((0.62, -0.3, 1.1), (0.67, -0.22, 1.14), "amber_dim", LAMP_DIM)
    b.fine.box((0.56, -0.3, 0.2), (0.6, 0.3, 0.3), IRON)
    _label(b, "GUN 3", (0.601, 0.0, 0.25), 0.06)


def banner(b: Parts) -> None:
    """A banner, 0.9 wide and 2.2 high, hanging from a bar: rust-red cloth with the ferry's mark (a hull under a mast) and KHARON MANDATE. It hangs against a wall that is behind it (-x)."""
    fb = b.fine
    fb.cyl((0.0, -0.5, 2.38), (0.0, 0.5, 2.38), 0.022, COPPER, seg=8)
    for y in (-0.5, 0.5):
        fb.sphere((0.0, y, 2.38), 0.035, COPPER, seg=8, rings=4)
    b.soft.box((0.0, -0.45, 0.28), (0.022, 0.45, 2.36), CLOTH)
    # the mark: a hull (a long low boat with a high prow), a mast and a sail, as flat plates in stencil
    x0 = 0.0225
    b.fine.extrude_x([(y, z) for (y, z) in [(-0.34, 1.62), (0.34, 1.62), (0.26, 1.46), (-0.26, 1.46)]], x0, x0 + 0.004, STENCIL)
    b.fine.extrude_x([(-0.01, 1.62), (0.01, 1.62), (0.01, 2.1), (-0.01, 2.1)], x0, x0 + 0.004, STENCIL)
    b.fine.extrude_x([(0.03, 1.7), (0.03, 2.08), (0.28, 1.7)], x0, x0 + 0.004, STENCIL)
    b.fine.extrude_x([(-0.03, 1.74), (-0.03, 2.04), (-0.22, 1.74)], x0, x0 + 0.004, STENCIL)
    for k in range(4):
        y = -0.36 + k * 0.24
        b.fine.extrude_x([(y, 1.34), (y + 0.12, 1.34), (y + 0.06, 1.28)], x0, x0 + 0.004, STENCIL)           # the waves
    b.emit.text("KHARON", (x0 + 0.0005, 0.0, 0.98), 0.12, (1.0, 0.0, 0.0), STENCIL, up=(0.0, 0.0, 1.0))
    b.emit.text("MANDATE", (x0 + 0.0005, 0.0, 0.76), 0.12, (1.0, 0.0, 0.0), STENCIL, up=(0.0, 0.0, 1.0))


# ============================================================================================================================ the fallen
def _limb(b: Parts, p0, p1, r0: float, r1: float, mat: str, seg: int = 7) -> None:
    """A limb segment: a tapering cylinder with a ball at its far end (soft: shaded smooth)."""
    b.soft.cyl(p0, p1, r0, mat, seg=seg, r2=r1, caps=False)
    b.soft.sphere(p1, r1 * 1.08, mat, seg=seg, rings=4)


def _torso(b: Parts, chest, hips, vest_up: bool, vest_dy: float = 0.0, tilt: float = 0.0) -> None:
    """The trunk of a fallen man: a chest and a pelvis (rounded), the waist between, the vest's plate on the side that is up. `chest` and `hips` are floor-relative centres."""
    sb = b.soft
    sb.sphere(chest, 1.0, UNIFORM, seg=10, rings=6, squash=(0.27, 0.2, 0.12))
    sb.sphere(hips, 1.0, UNIFORM, seg=9, rings=5, squash=(0.15, 0.18, 0.1))
    sb.cyl((hips[0] + 0.08, hips[1], hips[2]), (chest[0] - 0.12, chest[1], chest[2]), 0.1, UNIFORM, seg=8, caps=False)
    z = chest[2] + (0.1 if vest_up else -0.0)
    b.body.cbox((chest[0] + 0.02, chest[1] + vest_dy, z), (0.36, 0.3, 0.04), PLATE, rot=_rot_z(tilt))
    b.fine.cbox((chest[0] - 0.04, chest[1] + vest_dy, z + 0.022), (0.08, 0.26, 0.006), IRON, rot=_rot_z(tilt))


def _head(b: Parts, c, face_up: bool = True, face_dir=(0.0, 0.0, 1.0)) -> None:
    """A head with a helmet over its crown: the face (skin) towards face_dir, the helmet's shell on the other side."""
    sb = b.soft
    sb.sphere(c, 0.1, SKIN, seg=9, rings=6, squash=(1.05, 0.9, 0.95))
    off = (-face_dir[0] * 0.025, -face_dir[1] * 0.025, -face_dir[2] * 0.025)
    sb.sphere((c[0] + off[0], c[1] + off[1], c[2] + off[2]), 0.112, UNIFORM, seg=9, rings=6, squash=(1.0 if abs(face_dir[0]) < 0.5 else 0.7, 1.0, 1.0 if abs(face_dir[2]) < 0.5 else 0.75))


def _hand(b: Parts, c) -> None:
    b.soft.sphere(c, 0.04, SKIN, seg=6, rings=4, squash=(1.3, 1.0, 0.8))


def _boot(b: Parts, c, yaw: float) -> None:
    b.body.cbox(c, (0.27, 0.1, 0.1), IRON, rot=_rot_z(yaw))


def body_a(b: Parts) -> None:
    """A fallen man on his back (head towards +x, his right towards +y): one arm out, one along his side, one knee bent."""
    _torso(b, (0.42, 0.0, 0.13), (0.0, 0.0, 0.1), True)
    _head(b, (0.8, 0.02, 0.1), face_dir=(-0.2, 0.0, 1.0))
    b.soft.cyl((0.62, 0.0, 0.11), (0.72, 0.01, 0.1), 0.055, SKIN, seg=7, caps=False)
    _limb(b, (0.56, 0.22, 0.1), (0.38, 0.42, 0.06), 0.05, 0.04, UNIFORM)
    _limb(b, (0.38, 0.42, 0.06), (0.2, 0.62, 0.04), 0.04, 0.036, UNIFORM)
    _hand(b, (0.14, 0.67, 0.04))
    _limb(b, (0.56, -0.22, 0.1), (0.3, -0.3, 0.06), 0.05, 0.04, UNIFORM)
    _limb(b, (0.3, -0.3, 0.06), (0.1, -0.28, 0.05), 0.04, 0.036, UNIFORM)
    _hand(b, (0.03, -0.28, 0.05))
    _limb(b, (-0.04, -0.1, 0.1), (-0.48, -0.14, 0.08), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.48, -0.14, 0.08), (-0.9, -0.2, 0.06), 0.06, 0.05, UNIFORM)
    _boot(b, (-0.98, -0.2, 0.06), 0.0)
    _limb(b, (-0.04, 0.1, 0.1), (-0.4, 0.3, 0.1), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.4, 0.3, 0.1), (-0.78, 0.2, 0.06), 0.06, 0.05, UNIFORM)
    _boot(b, (-0.86, 0.2, 0.06), -15.0)


def body_b(b: Parts) -> None:
    """A fallen man face down: one arm forward past his head, the other under him, his legs apart."""
    _torso(b, (0.4, 0.0, 0.13), (0.0, 0.0, 0.1), True)
    _head(b, (0.78, -0.04, 0.1), face_dir=(0.0, -0.4, -1.0))
    b.soft.cyl((0.62, 0.0, 0.12), (0.7, -0.03, 0.1), 0.055, UNIFORM, seg=7, caps=False)
    _limb(b, (0.56, 0.2, 0.12), (0.8, 0.3, 0.07), 0.05, 0.04, UNIFORM)
    _limb(b, (0.8, 0.3, 0.07), (1.02, 0.36, 0.04), 0.04, 0.036, UNIFORM)
    _hand(b, (1.08, 0.37, 0.04))
    _limb(b, (0.56, -0.2, 0.12), (0.46, -0.1, 0.06), 0.05, 0.04, UNIFORM)
    _limb(b, (-0.04, -0.1, 0.1), (-0.5, -0.2, 0.08), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.5, -0.2, 0.08), (-0.92, -0.3, 0.06), 0.06, 0.05, UNIFORM)
    _boot(b, (-1.0, -0.3, 0.06), 10.0)
    _limb(b, (-0.04, 0.1, 0.1), (-0.5, 0.18, 0.08), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.5, 0.18, 0.08), (-0.9, 0.34, 0.06), 0.06, 0.05, UNIFORM)
    _boot(b, (-0.98, 0.37, 0.06), -20.0)


def body_c(b: Parts) -> None:
    """A fallen man on his side, knees drawn up, an arm under his head."""
    _torso(b, (0.38, 0.0, 0.15), (0.0, 0.03, 0.13), False, vest_dy=-0.09, tilt=8.0)
    _head(b, (0.76, 0.05, 0.12), face_dir=(0.0, 0.8, 0.5))
    _limb(b, (0.56, 0.1, 0.2), (0.7, 0.2, 0.06), 0.05, 0.04, UNIFORM)
    _limb(b, (0.7, 0.2, 0.06), (0.62, 0.05, 0.05), 0.04, 0.036, UNIFORM)
    _limb(b, (0.5, -0.1, 0.24), (0.3, -0.28, 0.14), 0.05, 0.04, UNIFORM)
    _limb(b, (0.3, -0.28, 0.14), (0.42, -0.4, 0.08), 0.04, 0.036, UNIFORM)
    _hand(b, (0.46, -0.44, 0.07))
    _limb(b, (-0.04, 0.0, 0.14), (-0.3, -0.25, 0.2), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.3, -0.25, 0.2), (-0.62, -0.1, 0.07), 0.06, 0.05, UNIFORM)
    _boot(b, (-0.7, -0.07, 0.06), 25.0)
    _limb(b, (-0.04, 0.08, 0.1), (-0.26, -0.05, 0.1), 0.085, 0.06, UNIFORM)
    _limb(b, (-0.26, -0.05, 0.1), (-0.6, 0.12, 0.06), 0.06, 0.05, UNIFORM)
    _boot(b, (-0.68, 0.15, 0.06), -10.0)


def builders() -> dict:
    return {
        "crate": crate, "crate_long": crate_long, "barrel": barrel, "locker": locker, "rack": rack, "bunk": bunk, "table": table, "bench": bench, "console": console,
        "machine": machine, "motor": motor, "tank": tank, "reactor": reactor, "breech": breech, "bed": bed, "cell": cell, "banner": banner,
        "body_a": body_a, "body_b": body_b, "body_c": body_c,
    }
