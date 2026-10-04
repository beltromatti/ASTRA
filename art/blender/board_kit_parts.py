"""ABBORDAGGI-3 — the boarding kit's pieces: the builders (Blender). The sizes and the frames are board_kit_defs.py's. The language is the Aquila's corridor kit (ribbed bays, handrails, louvres, pipes and cable
trays on the ceiling, a light channel, thin guide lights on the floor) in the Kharon Mandate's hand: heavier, darker plating, oxidised copper and verdigris, hazard paint worn to amber, their words in stencil
(docs/STILE.md §2: "survivor ships, patched with pride"), and the orange-red of emergency light.

Each builder takes a `Parts` (bridge3_lib: body = bevelled hard surface, fine = small hardware, emit = lamps and lettering, never bevelled) and adds its geometry in the piece's frame. Nothing here exports.
"""
from __future__ import annotations

import math
import random

from bridge3_lib import Parts

from board_kit_defs import (BAY_H, BAY_W, BLAST_H, CLOTH, COPPER, DECK, DOOR_H, FRAME, HAZARD, IRON, LAMP, LAMP_DIM, LAMP_HOT, MOTTO, PLATE, RIB_D, RIB_H, RIB_W, RUBBER, SCREEN, SOOT, STENCIL,
                            UNIFORM, VERD)


# ============================================================================================================================ small helpers
def _rivets(b: Parts, x0: float, x1: float, z0: float, z1: float, y: float, step: float = 0.72, size: float = 0.036) -> None:
    """A row of rivet heads round a panel's edge (x0..x1, z0..z1 at depth y): boxes, 12 triangles each."""
    nx = max(1, int(round((x1 - x0) / step)))
    nz = max(1, int(round((z1 - z0) / step)))
    pts = []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        pts += [(x, z0), (x, z1)]
    for k in range(1, nz):
        z = z0 + (z1 - z0) * k / nz
        pts += [(x0, z), (x1, z)]
    for (x, z) in pts:
        b.fine.box((x - size / 2, y, z - size / 2), (x + size / 2, y + 0.012, z + size / 2), IRON)


def _frame_bay(b: Parts, w: float = BAY_W, h: float = BAY_H, lower_top: float = 1.0, upper: bool = True) -> None:
    """The common structure of a bay: the back plate, the frame with its middle rail at `lower_top`, the two inset panels (rivetted), the skirting."""
    fb = b.body
    fb.box((0.0, 0.0, 0.0), (w, 0.04, h), PLATE)                                             # the back plate (the cube wall behind is the collision: this is what is seen)
    t = 0.075
    fb.box((0.0, 0.04, 0.0), (t, 0.10, h), FRAME)                                            # the stiles
    fb.box((w - t, 0.04, 0.0), (w, 0.10, h), FRAME)
    fb.box((t, 0.04, 0.0), (w - t, 0.085, 0.14), FRAME)                                      # the skirting
    fb.box((t, 0.04, h - t), (w - t, 0.10, h), FRAME)                                        # the top rail
    fb.box((t, 0.04, lower_top - 0.035), (w - t, 0.095, lower_top + 0.035), FRAME)           # the middle rail
    fb.box((t + 0.04, 0.04, 0.16), (w - t - 0.04, 0.062, lower_top - 0.05), PLATE)            # the lower panel
    if upper:
        fb.box((t + 0.04, 0.04, lower_top + 0.06), (w - t - 0.04, 0.062, h - t - 0.04), PLATE)   # the upper panel
    _rivets(b, t + 0.09, w - t - 0.09, 0.2, lower_top - 0.09, 0.062)
    if upper:
        _rivets(b, t + 0.09, w - t - 0.09, lower_top + 0.11, h - t - 0.09, 0.062)


def _bolt_plate(b: Parts, cx: float, cz: float, sx: float, sz: float, y: float = 0.062, mat: str = FRAME) -> None:
    b.fine.box((cx - sx / 2, y, cz - sz / 2), (cx + sx / 2, y + 0.03, cz + sz / 2), mat)
    for dx in (-1, 1):
        for dz in (-1, 1):
            b.fine.box((cx + dx * (sx / 2 - 0.035) - 0.014, y + 0.03, cz + dz * (sz / 2 - 0.035) - 0.014), (cx + dx * (sx / 2 - 0.035) + 0.014, y + 0.042, cz + dz * (sz / 2 - 0.035) + 0.014), IRON)


def _handrail(b: Parts, x0: float, x1: float, z: float, y: float = 0.17) -> None:
    b.fine.cyl((x0, y, z), (x1, y, z), 0.022, COPPER, seg=8)
    for x in (x0 + 0.05, x1 - 0.05):
        b.fine.box((x - 0.02, 0.06, z - 0.02), (x + 0.02, y, z + 0.02), FRAME)


def _stencil(b: Parts, text: str, cx: float, cz: float, h: float, y: float = 0.066, cell: str | None = None, mat: str = STENCIL) -> float:
    """Stencil lettering on the front of a bay (reads left to right as the viewer sees it)."""
    return b.emit.text(text, (cx, y, cz), h, (0, 1, 0), mat, up=(0, 0, 1), cell=cell)


def _hazard_band(b: Parts, x0: float, x1: float, z0: float, z1: float, y: float, step: float = 0.16, side: int = 1) -> None:
    """Diagonal hazard stripes between x0..x1, z0..z1 (parallelograms in the wall's plane, amber on black iron), standing out of the face at depth y: towards +y (side 1) or towards -y (side -1)."""
    s = 1 if side >= 0 else -1
    base = (y, y + s * 0.008) if s > 0 else (y + s * 0.008, y)
    b.fine.box((x0, base[0], z0), (x1, base[1], z1), IRON)
    n = int((x1 - x0) / step) + 2
    y0, y1 = (y + 0.008, y + 0.014) if s > 0 else (y - 0.014, y - 0.008)
    for k in range(-1, n):
        xa = x0 + k * step
        poly = [(xa, z0), (xa + step * 0.5, z0), (xa + step * 0.5 + (z1 - z0), z1), (xa + (z1 - z0), z1)]
        pts = [(min(max(px, x0), x1), pz) for (px, pz) in poly]
        if len(set(pts)) < 3 or max(p[0] for p in pts) - min(p[0] for p in pts) < 0.01:
            continue
        b.fine.extrude_y(pts, y0, y1, HAZARD)


# ============================================================================================================================ the wall bays
def wall_a(b: Parts, text: list[str] | None = None) -> None:
    """The plain bay: plates, rails, a handrail, a stencil panel with the Mandate's words."""
    from bridge3_lib import text_proto
    _frame_bay(b)
    _handrail(b, 0.2, BAY_W - 0.2, 1.0)
    lines = text or ["FERRY GUARD"]
    # the stencil plate, as wide as the longest line needs (at most the bay's inner width) and as tall as the lines
    heights = []
    for ln in lines:
        w1 = text_proto(ln)["width"]                       # in font-size units: cap height 0.7 of it
        heights.append(min(0.17, 1.38 / max(w1, 1e-3) * 0.7))
    h = min(heights)
    total = h * 1.7 * len(lines)
    width = max(text_proto(ln)["width"] * h / 0.7 for ln in lines) + 0.16
    cz = 1.72
    b.fine.box((1.0 - width / 2, 0.062, cz - total / 2 - 0.04), (1.0 + width / 2, 0.075, cz + total / 2 + 0.04), IRON)
    for i, ln in enumerate(lines):
        _stencil(b, ln, 1.0, cz + total / 2 - h * 0.85 - i * h * 1.7, h, y=0.0765)
    _bolt_plate(b, 0.42, 2.18, 0.2, 0.2)
    _bolt_plate(b, BAY_W - 0.42, 2.18, 0.2, 0.2)


def wall_b(b: Parts) -> None:
    """The pipe bank: three runs of copper, a riser, a valve wheel, a gauge."""
    _frame_bay(b, upper=True)
    for i, z in enumerate((0.38, 0.72, 1.46)):
        b.fine.cyl((0.1, 0.16, z), (BAY_W - 0.1, 0.16, z), 0.06, COPPER, seg=8)
        for x in (0.3, 1.0, 1.7):
            b.fine.cyl((x - 0.03, 0.16, z), (x + 0.03, 0.16, z), 0.078, FRAME, seg=8)          # the collars
            b.fine.box((x - 0.03, 0.04, z - 0.1), (x + 0.03, 0.12, z + 0.1), FRAME)
    b.fine.cyl((1.7, 0.12, 0.2), (1.7, 0.12, BAY_H - 0.2), 0.045, VERD, seg=8)                  # the riser
    # the valve wheel on the middle run
    wc = (0.95, 0.24, 0.72)
    b.fine.cyl((wc[0], wc[1] - 0.05, wc[2]), (wc[0], wc[1] + 0.02, wc[2]), 0.035, FRAME, seg=8)
    for k in range(6):
        a = k * math.pi / 3
        b.fine.box((wc[0] + math.cos(a) * 0.11 - 0.012, wc[1] + 0.02, wc[2] + math.sin(a) * 0.11 - 0.012), (wc[0] + math.cos(a) * 0.11 + 0.012, wc[1] + 0.045, wc[2] + math.sin(a) * 0.11 + 0.012), COPPER)
    b.fine.box((wc[0] - 0.12, wc[1] + 0.02, wc[2] - 0.014), (wc[0] + 0.12, wc[1] + 0.034, wc[2] + 0.014), COPPER)
    b.fine.box((wc[0] - 0.014, wc[1] + 0.02, wc[2] - 0.12), (wc[0] + 0.014, wc[1] + 0.034, wc[2] + 0.12), COPPER)
    # a gauge: a dark disc with a lit rim
    b.fine.cyl((0.4, 0.062, 1.9), (0.4, 0.13, 1.9), 0.09, FRAME, seg=14)
    b.emit.lamp_cyl((0.4, 0.13, 1.9), (0.4, 0.136, 1.9), 0.065, "amber_dim", LAMP_DIM, seg=14)
    _stencil(b, "COOLANT 2", 1.35, 1.95, 0.1, y=0.0765)


def wall_c(b: Parts) -> None:
    """The louvre and the junction box."""
    _frame_bay(b)
    # louvres: ten slats, tilted, in a frame
    b.body.box((0.36, 0.062, 1.2), (1.64, 0.1, 2.3), IRON)
    for k in range(10):
        z = 1.26 + k * 0.1
        b.fine.box((0.4, 0.07, z), (1.6, 0.13, z + 0.016), FRAME, rot=None)
        b.fine.box((0.4, 0.105, z + 0.015), (1.6, 0.135, z + 0.03), FRAME)
    # junction box with conduits
    b.body.box((1.3, 0.062, 0.34), (1.78, 0.17, 0.82), FRAME)
    b.fine.box((1.34, 0.17, 0.38), (1.74, 0.176, 0.78), IRON)
    b.emit.lamp_box((1.52, 0.176, 0.7), (1.6, 0.18, 0.74), "amber", LAMP_DIM)
    for x in (1.38, 1.54, 1.7):
        b.fine.cyl((x, 0.1, 0.82), (x, 0.1, 1.15), 0.02, VERD, seg=6)
    _handrail(b, 0.2, 1.2, 0.9)
    b.fine.cyl((0.35, 0.1, 0.16), (0.35, 0.1, 0.86), 0.05, COPPER, seg=8)                      # a stand-pipe


def wall_d(b: Parts) -> None:
    """A locker front: three doors with louvres and handles."""
    fb = b.body
    fb.box((0.0, 0.0, 0.0), (BAY_W, 0.04, BAY_H), PLATE)
    for i in range(3):
        x0 = 0.05 + i * 0.63
        fb.box((x0, 0.04, 0.12), (x0 + 0.58, 0.13, 2.2), FRAME)                              # a locker door
        fb.box((x0 + 0.04, 0.13, 0.16), (x0 + 0.54, 0.145, 2.16), PLATE)
        for k in range(5):
            b.fine.box((x0 + 0.12, 0.145, 1.78 + k * 0.07), (x0 + 0.46, 0.152, 1.8 + k * 0.07), IRON)
        b.fine.box((x0 + 0.46, 0.145, 1.02), (x0 + 0.5, 0.2, 1.3), COPPER)                    # the handle
        b.fine.box((x0 + 0.2, 0.145, 0.25), (x0 + 0.38, 0.152, 0.34), IRON)                   # a number plate
        b.emit.text(f"{i + 1:02d}", (x0 + 0.29, 0.153, 0.295), 0.05, (0, 1, 0), STENCIL, up=(0, 0, 1))
    fb.box((0.0, 0.04, 2.2), (BAY_W, 0.1, 2.35), FRAME)
    fb.box((0.0, 0.04, 2.35), (BAY_W, 0.07, BAY_H), PLATE)


def wall_e(b: Parts) -> None:
    """A hatch bay: a framed hatch with a wheel and a hazard band under it."""
    _frame_bay(b, upper=False)
    fb = b.body
    fb.box((0.4, 0.06, 0.2), (1.6, 0.17, 2.3), IRON)                                         # the hatch's frame
    fb.box((0.5, 0.17, 0.3), (1.5, 0.2, 2.2), PLATE)                                         # the door
    for z in (0.55, 1.1, 1.65, 2.0):
        b.fine.box((0.5, 0.2, z), (1.5, 0.225, z + 0.045), FRAME)
    wc = (1.0, 0.225, 1.25)
    b.fine.cyl((wc[0], wc[1], wc[2]), (wc[0], wc[1] + 0.06, wc[2]), 0.05, COPPER, seg=10)
    for k in range(8):
        a = k * math.pi / 4
        b.fine.cyl((wc[0], wc[1] + 0.05, wc[2]), (wc[0] + math.cos(a) * 0.2, wc[1] + 0.05, wc[2] + math.sin(a) * 0.2), 0.018, COPPER, seg=6)
    _hazard_band(b, 0.4, 1.6, 0.14, 0.26, 0.12)
    _stencil(b, "HATCH", 1.0, 2.37, 0.12, y=0.0765)
    b.emit.lamp_box((1.64, 0.1, 1.1), (1.69, 0.13, 1.2), "red_dim", LAMP_DIM)               # a status lamp beside it


def wall_f(b: Parts) -> None:
    """The bay the war has had: a torn lower plate, a bent flap, soot, hanging cables."""
    fb = b.body
    fb.box((0.0, 0.0, 0.0), (BAY_W, 0.04, BAY_H), PLATE)
    t = 0.075
    fb.box((0.0, 0.04, 0.0), (t, 0.10, BAY_H), FRAME)
    fb.box((BAY_W - t, 0.04, 0.0), (BAY_W, 0.10, BAY_H), FRAME)
    fb.box((t, 0.04, 0.0), (BAY_W - t, 0.085, 0.14), FRAME)
    fb.box((t, 0.04, BAY_H - t), (BAY_W - t, 0.10, BAY_H), FRAME)
    # soot over the back plate, and the upper panel half gone
    fb.box((t + 0.04, 0.04, 1.0), (BAY_W - t - 0.04, 0.056, 2.2), SOOT)
    # the torn hole: a jagged black insert, and the flap of plate bent out of it
    rng = random.Random(17)
    poly = []
    cx, cz = 0.95, 0.85
    for k in range(11):
        a = k * 2 * math.pi / 11
        r = 0.34 + rng.random() * 0.26
        poly.append((cx + math.cos(a) * r * 1.1, cz + math.sin(a) * r))
    b.fine.extrude_y(poly, 0.045, 0.062, SOOT)
    b.body.box((1.2, 0.05, 0.5), (1.78, 0.062, 1.3), FRAME)
    fb.cbox((1.25, 0.2, 1.25), (0.62, 0.025, 0.4), PLATE, rot=_rot_y(-55))                     # the flap
    b.fine.cyl((0.45, 0.1, 1.9), (0.45, 0.1, 0.05), 0.02, RUBBER, seg=6)                      # a cable down the wall
    b.fine.cyl((1.5, 0.1, 2.2), (1.52, 0.2, 1.4), 0.018, RUBBER, seg=6)
    b.fine.cyl((0.3, 0.1, 2.3), (0.4, 0.12, 1.5), 0.016, RUBBER, seg=6)
    b.emit.lamp_box((1.55, 0.062, 2.2), (1.6, 0.07, 2.25), "red_dim", LAMP_DIM)


def wall_plain(b: Parts) -> None:
    w = 1.0
    fb = b.body
    fb.box((0.0, 0.0, 0.0), (w, 0.04, BAY_H), PLATE)
    t = 0.075
    fb.box((0.0, 0.04, 0.0), (t, 0.10, BAY_H), FRAME)
    fb.box((w - t, 0.04, 0.0), (w, 0.10, BAY_H), FRAME)
    fb.box((t, 0.04, 0.0), (w - t, 0.085, 0.14), FRAME)
    fb.box((t, 0.04, BAY_H - t), (w - t, 0.10, BAY_H), FRAME)
    fb.box((t, 0.04, 1.0 - 0.035), (w - t, 0.095, 1.035), FRAME)
    fb.box((t + 0.04, 0.04, 0.16), (w - t - 0.04, 0.062, 0.95), PLATE)
    fb.box((t + 0.04, 0.04, 1.08), (w - t - 0.04, 0.062, BAY_H - t - 0.04), PLATE)
    _rivets(b, t + 0.09, w - t - 0.09, 0.2, 0.9, 0.062, step=0.6)


def _rot_y(deg: float):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def _rot_x(deg: float):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _rot_z(deg: float):
    from mathutils import Matrix
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def rib(b: Parts) -> None:
    """A full-height rib: web and flange, gussets at the foot, bolted plates up it."""
    fb = b.body
    fb.box((0.0, RIB_D - 0.04, 0.0), (RIB_W, RIB_D, RIB_H), FRAME)                          # the front flange
    fb.box((0.075, 0.0, 0.0), (RIB_W - 0.075, RIB_D - 0.04, RIB_H), IRON)                      # the web
    for sx in (0.0, RIB_W - 0.05):
        fb.extrude_x([(0.0, 0.0), (RIB_D - 0.04, 0.0), (0.0, 0.3)], sx, sx + 0.05, FRAME)      # the gussets (profile in y, z)
    for z in (0.65, 1.55, 2.4):
        _bolt_plate(b, RIB_W / 2, z, 0.18, 0.2, y=RIB_D, mat=PLATE)
    b.emit.lamp_box((RIB_W / 2 - 0.012, RIB_D + 0.001, 0.2), (RIB_W / 2 + 0.012, RIB_D + 0.004, 2.8), "red_dim", LAMP_DIM)    # a thin guide light up its face


def cornice(b: Parts) -> None:
    b.body.box((0.0, 0.0, 0.0), (BAY_W, 0.18, 0.22), FRAME)
    b.body.box((0.0, 0.0, 0.22), (BAY_W, 0.1, 0.27), IRON)
    for x in (0.3, 1.0, 1.7):
        b.fine.box((x - 0.05, 0.18, 0.04), (x + 0.05, 0.2, 0.18), PLATE)


def header(b: Parts) -> None:
    """A band over a door (1 m wide: the game stretches it over the opening and up to the ceiling)."""
    fb = b.body
    fb.box((0.0, 0.0, 0.0), (1.0, 0.04, 0.5), PLATE)
    fb.box((0.0, 0.04, 0.0), (1.0, 0.075, 0.07), FRAME)
    fb.box((0.0, 0.04, 0.43), (1.0, 0.075, 0.5), FRAME)
    for x in (0.1, 0.5, 0.9):
        b.fine.box((x - 0.016, 0.075, 0.2), (x + 0.016, 0.087, 0.3), IRON)


# ============================================================================================================================ ceilings (z down from the ceiling's plane)
def pipes(b: Parts) -> None:
    for y in (-0.115, 0.115):
        b.fine.cyl((0.0, y, -0.12), (2.0, y, -0.12), 0.085, COPPER, seg=8)
    for x in (0.01, 1.0, 1.99):
        b.fine.box((x - 0.03, -0.2, -0.2), (x + 0.03, 0.2, -0.17), FRAME)                      # the clamp's strap under both
        for y in (-0.115, 0.115):
            b.fine.box((x - 0.012, y - 0.012, -0.17), (x + 0.012, y + 0.012, 0.0), FRAME)        # the rods to the ceiling
    for x in (0.03, 1.97):
        for y in (-0.115, 0.115):
            b.fine.cyl((x, y, -0.12), (x + (0.025 if x < 1 else -0.025), y, -0.12), 0.105, VERD, seg=8)    # the flange rings


def tray(b: Parts) -> None:
    b.body.box((0.0, -0.22, -0.16), (2.0, 0.22, -0.145), FRAME)
    for y in (-0.22, 0.22):
        b.body.box((0.0, y - 0.01, -0.16), (2.0, y + 0.01, -0.06), FRAME)
    for i, y in enumerate((-0.15, -0.075, 0.0, 0.075, 0.15)):
        b.fine.cyl((0.0, y, -0.12), (2.0, y, -0.12), 0.024, RUBBER if i % 2 else VERD, seg=6)
    for x in (0.4, 1.6):
        for y in (-0.22, 0.22):
            b.fine.box((x - 0.012, y - 0.012, -0.145), (x + 0.012, y + 0.012, 0.0), FRAME)


def _lamp_cage(b: Parts, cell: str | None, lens_mat: str | None) -> None:
    b.body.box((-0.17, -0.1, -0.06), (0.17, 0.1, 0.0), FRAME)                                # the housing against the ceiling
    for x in (-0.15, 0.15):
        for y in (-0.085, 0.085):
            b.fine.cyl((x, y, -0.06), (x, y, -0.2), 0.009, IRON, seg=5)                        # the cage's four bars
    for y in (-0.085, 0.085):
        b.fine.cyl((-0.15, y, -0.2), (0.15, y, -0.2), 0.008, IRON, seg=5)
    for x in (-0.15, 0.15):
        b.fine.cyl((x, -0.085, -0.2), (x, 0.085, -0.2), 0.008, IRON, seg=5)
    b.fine.cyl((0.0, -0.085, -0.2), (0.0, 0.085, -0.2), 0.008, IRON, seg=5)
    if cell:
        b.emit.lamp_box((-0.13, -0.07, -0.085), (0.13, 0.07, -0.062), cell, LAMP)             # the lens
    else:
        b.body.box((-0.13, -0.07, -0.085), (0.13, 0.07, -0.062), SOOT)


def lamp(b: Parts) -> None:
    _lamp_cage(b, "amber", LAMP)


def lamp_red(b: Parts) -> None:
    _lamp_cage(b, "red", LAMP)


def lamp_dead(b: Parts) -> None:
    _lamp_cage(b, None, None)


def vent(b: Parts) -> None:
    b.body.box((-0.45, -0.3, -0.07), (0.45, 0.3, 0.0), FRAME)
    for k in range(9):
        y = -0.26 + k * 0.065
        b.fine.box((-0.4, y, -0.06), (0.4, y + 0.025, -0.02), IRON)


def cables(b: Parts) -> None:
    """A bundle hanging from a torn ceiling panel."""
    b.body.box((-0.28, -0.2, -0.05), (0.28, 0.2, 0.0), SOOT)
    rng = random.Random(5)
    for k in range(5):
        x0, y0 = rng.uniform(-0.2, 0.2), rng.uniform(-0.15, 0.15)
        pts = [(x0, y0, -0.03), (x0 + rng.uniform(-0.08, 0.08), y0 + rng.uniform(-0.08, 0.08), -0.35), (x0 + rng.uniform(-0.2, 0.2), y0 + rng.uniform(-0.2, 0.2), -0.7 - rng.random() * 0.4)]
        b.fine.tube(pts, 0.018 + rng.random() * 0.012, RUBBER if k % 2 else COPPER, seg=5)
    b.fine.cyl((0.0, 0.0, -0.05), (0.0, 0.0, -0.3), 0.02, FRAME, seg=6)


# ============================================================================================================================ floors (z up from the floor)
def floor(b: Parts) -> None:
    b.body.box((0.0, 0.0, 0.0), (2.0, 2.0, 0.012), DECK)
    for a in ((0.0, 0.0, 2.0, 0.03), (0.0, 1.97, 2.0, 2.0), (0.0, 0.0, 0.03, 2.0), (1.97, 0.0, 2.0, 2.0)):
        b.fine.box((a[0], a[1], 0.0), (a[2], a[3], 0.016), FRAME)
    for (x, y) in ((0.12, 0.12), (1.88, 0.12), (0.12, 1.88), (1.88, 1.88)):
        b.fine.box((x - 0.025, y - 0.025, 0.012), (x + 0.025, y + 0.025, 0.02), IRON)


def threshold(b: Parts) -> None:
    w, d = 1.8, 0.5
    b.body.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.012), IRON)
    step = 0.2
    n = int(w / step)
    for k in range(n):
        x0 = -w / 2 + k * step
        poly = [(x0, -d / 2), (x0 + step * 0.5, -d / 2), (x0 + step * 0.5 + d * 0.5, d / 2), (x0 + d * 0.5, d / 2)]
        pts = [(min(max(px, -w / 2), w / 2), py) for (px, py) in poly]
        if max(p[0] for p in pts) - min(p[0] for p in pts) > 0.01:
            b.fine.prism(pts, 0.012, 0.0155, HAZARD)


def guide(b: Parts) -> None:
    b.emit.lamp_box((0.0, -0.025, 0.0), (2.0, 0.025, 0.012), "red_dim", LAMP_DIM)


def debris(b: Parts) -> None:
    rng = random.Random(23)
    for k in range(5):
        cx, cy = rng.uniform(-0.5, 0.5), rng.uniform(-0.4, 0.4)
        n = rng.randint(4, 6)
        poly = []
        for i in range(n):
            a = i * 2 * math.pi / n + rng.uniform(-0.3, 0.3)
            r = rng.uniform(0.12, 0.34)
            poly.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 0.7))
        z0 = rng.uniform(0.0, 0.05)
        b.fine.prism(_convex_hull(poly), z0, z0 + 0.03 + rng.random() * 0.03, PLATE if k % 2 else FRAME)
    b.fine.cyl((-0.3, -0.5, 0.05), (0.5, 0.45, 0.07), 0.035, COPPER, seg=6)


def _convex_hull(pts):
    """A convex polygon (counter-clockwise) from points (Andrew's monotone chain)."""
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b2):
        return (a[0] - o[0]) * (b2[1] - o[1]) - (a[1] - o[1]) * (b2[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# ============================================================================================================================ openings (x across, y through, z up)
def jamb(b: Parts) -> None:
    """A door jamb: 20 cm across, 40 deep (it stands in both rooms' walls), 2.5 high."""
    fb = b.body
    fb.box((-0.1, -0.2, 0.0), (0.1, 0.2, 2.5), FRAME)
    for sy in (-1, 1):
        fb.box((-0.12, sy * 0.2 - (0.012 if sy > 0 else -0.012) - 0.02, 0.0), (0.12, sy * 0.2 + (0.0 if sy > 0 else 0.0), 0.05), IRON)
        _bolt_plate_y(b, 0.0, 1.0, 0.16, 0.5, sy * 0.2)
        _bolt_plate_y(b, 0.0, 1.9, 0.16, 0.5, sy * 0.2)
        b.emit.lamp_box((-0.025, sy * 0.2 + (0.0 if sy > 0 else -0.012), 2.1), (0.025, sy * 0.2 + (0.012 if sy > 0 else 0.0), 2.16), "amber_dim", LAMP_DIM)


def _bolt_plate_y(b: Parts, cx: float, cz: float, sx: float, sz: float, y: float) -> None:
    """A bolted plate on the face of a piece that looks along +y (y > 0) or -y (y < 0)."""
    s = 1 if y > 0 else -1
    lo, hi = (y, y + s * 0.02) if s > 0 else (y + s * 0.02, y)
    b.fine.box((cx - sx / 2, lo, cz - sz / 2), (cx + sx / 2, hi, cz + sz / 2), PLATE)


def door_header(b: Parts) -> None:
    fb = b.body
    fb.box((-0.5, -0.2, 0.0), (0.5, 0.2, 0.4), FRAME)
    for sy in (-1, 1):
        fb.box((-0.5, sy * 0.2 - (0.0 if sy > 0 else 0.03), 0.05), (0.5, sy * 0.2 + (0.03 if sy > 0 else 0.0), 0.35), PLATE)
        for x in (-0.38, -0.12, 0.12, 0.38):
            b.fine.box((x - 0.015, sy * 0.2 - (0.0 if sy > 0 else 0.012), 0.16), (x + 0.015, sy * 0.2 + (0.012 if sy > 0 else 0.0), 0.24), IRON)
    b.emit.lamp_box((-0.06, 0.2, 0.06), (0.06, 0.212, 0.1), "amber", LAMP_DIM)
    b.emit.lamp_box((-0.06, -0.212, 0.06), (0.06, -0.2, 0.1), "amber", LAMP_DIM)


def blast_jamb(b: Parts) -> None:
    fb = b.body
    fb.box((-0.17, -0.25, 0.0), (0.17, 0.25, 2.6), IRON)
    for sy in (-1, 1):
        for k in range(10):
            z = 0.1 + k * 0.24
            lo, hi = ((0.25, 0.262) if sy > 0 else (-0.262, -0.25))
            if k % 2 == 0:
                b.fine.box((-0.15, lo, z), (0.15, hi, z + 0.12), HAZARD)
        _bolt_plate_y(b, 0.0, 2.3, 0.26, 0.2, sy * 0.25)
    fb.box((-0.2, -0.28, 0.0), (0.2, 0.28, 0.06), FRAME)


def blast_header(b: Parts) -> None:
    fb = b.body
    fb.box((-0.5, -0.25, 0.0), (0.5, 0.25, 0.5), IRON)
    for sy in (-1, 1):
        lo, hi = ((0.25, 0.265) if sy > 0 else (-0.265, -0.25))
        _hazard_band(b, -0.46, 0.46, 0.04, 0.17, 0.25 if sy > 0 else -0.25, side=sy)
        b.emit.lamp_box((-0.28, lo, 0.28), (-0.12, hi, 0.34), "red_dim", LAMP_DIM)
        b.emit.lamp_box((0.12, lo, 0.28), (0.28, hi, 0.34), "red_dim", LAMP_DIM)
        b.emit.lamp_cyl((0.0, (hi if sy > 0 else lo), 0.33), (0.0, (hi + 0.04 if sy > 0 else lo - 0.04), 0.33), 0.06, "red", LAMP_HOT, seg=10)     # the beacon over the door


def blast_leaf(b: Parts) -> None:
    fb = b.body
    fb.box((-0.5, -0.05, 0.0), (0.5, 0.05, BLAST_H), PLATE)
    for sy in (-1, 1):
        lo, hi = ((0.05, 0.075) if sy > 0 else (-0.075, -0.05))
        for z in (0.35, 1.2, 2.05):
            fb.box((-0.5, lo, z - 0.05), (0.5, hi, z + 0.05), FRAME)
        for x in (-0.46, 0.46):
            fb.box((x - 0.04, lo, 0.0), (x + 0.04, hi, BLAST_H), FRAME)
        _hazard_band(b, -0.42, 0.42, 0.06, 0.2, 0.075 if sy > 0 else -0.075, side=sy)
        wz = 1.2
        b.fine.cyl((0.0, lo, wz), (0.0, hi + (0.07 if sy > 0 else -0.07), wz), 0.05, COPPER, seg=10)
