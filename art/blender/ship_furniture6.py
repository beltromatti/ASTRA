"""ASN Aquila interior kit: furniture and equipment of the flight and logistics decks (NAVE-2, Decks 9-11) — a fighter's nose section and an engine on their stands, a wing on
a jig, the avionics bench, missile and shell racks, the munitions hoist, sprinkler lines, cargo containers, a pallet truck and a forklift. Sixth library, after
ship_furniture.py .. ship_furniture5.py; same conventions: every function builds one piece in ITS OWN frame (origin on the floor, +x the piece's front, +y its left, z up) into a
`SParts` (body = bevelled hard-surface, fine = small details, soft = cloth, rubber and thin details, emit = lamps and labels); rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math
import random

from mathutils import Vector

import ship_furniture as F
import ship_furniture2 as G
from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMINATE,
                      LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, SParts, lamp_strip)


def _ellipse_ring(x: float, ry: float, rz: float, zc: float, n: int = 16):
    return [(x, ry * math.cos(2 * math.pi * k / n), zc + rz * math.sin(2 * math.pi * k / n)) for k in range(n)]


# ---------------------------------------------------------------------------------------------------------------------- the aircraft shop
def fighter_nose(b: SParts) -> None:
    """A fighter's nose section on its maintenance trolley, nose towards +x, 3.4 m long: a pale radome, a grey skin with two access panels open on the +y side showing the
    avionics bay (black boxes, a wire harness hanging out), a bubble canopy on top, an instrument panel in the cockpit; the trolley is a steel frame with two saddles and four wheels."""
    zc = 1.15
    rings = [_ellipse_ring(-1.3, 0.70, 0.60, zc), _ellipse_ring(-0.5, 0.66, 0.56, zc), _ellipse_ring(0.5, 0.52, 0.46, zc), _ellipse_ring(1.3, 0.34, 0.30, zc),
             _ellipse_ring(1.9, 0.20, 0.17, zc), _ellipse_ring(2.1, 0.05, 0.045, zc)]
    b.body.loft(rings, CRATE_GREY)
    b.body.loft([_ellipse_ring(1.2, 0.34, 0.30, zc), _ellipse_ring(1.65, 0.27, 0.24, zc), _ellipse_ring(1.9, 0.2, 0.17, zc), _ellipse_ring(2.1, 0.05, 0.045, zc)], IVORY)   # the radome
    glass = [_ellipse_ring(-0.9, 0.34, 0.26, zc + 0.52), _ellipse_ring(-0.3, 0.42, 0.30, zc + 0.56), _ellipse_ring(0.4, 0.36, 0.26, zc + 0.45), _ellipse_ring(0.85, 0.2, 0.12, zc + 0.36)]
    b.soft.loft(glass, DGLASS)
    b.body.box((-0.1, 0.52, zc - 0.22), (0.9, 0.56, zc + 0.2), STRUCT)                                               # the avionics bay, seen through the open panel
    b.soft.box((-0.05, 0.55, zc - 0.16), (0.25, 0.6, zc - 0.02), COMPOSITE)
    b.soft.box((0.3, 0.55, zc - 0.16), (0.55, 0.6, zc - 0.02), COMPOSITE)
    b.soft.box((-0.05, 0.55, zc + 0.02), (0.25, 0.6, zc + 0.14), COMPOSITE)
    b.emit.lamp_box((0.6, 0.6, zc + 0.05), (0.62, 0.62, zc + 0.09), "green", LAMP)
    b.emit.lamp_box((-0.0, 0.6, zc - 0.1), (0.02, 0.62, zc - 0.06), "amber", LAMP_DIM)
    b.soft.tube([(0.2, 0.58, zc + 0.1), (0.3, 0.8, zc - 0.1), (0.45, 0.95, zc - 0.5), (0.55, 1.0, 0.25)], 0.02, RUBBER, seg=6)
    b.soft.tube([(0.3, 0.58, zc - 0.05), (0.4, 0.75, zc - 0.2), (0.5, 0.9, zc - 0.55), (0.65, 0.95, 0.3)], 0.016, CRATE_ORANGE, seg=6)
    b.soft.box((0.9, 0.5, zc - 0.25), (1.05, 0.56, zc + 0.2), CRATE_OLIVE)                                          # the removed panel, leaning on the trolley
    b.soft.box((-0.6, -0.5, zc + 0.35), (0.2, 0.5, zc + 0.37), STRUCT)                                              # the cockpit's instrument panel under the canopy
    b.emit.lamp_box((-0.45, -0.3, zc + 0.37), (-0.1, 0.3, zc + 0.375), "cyan", LAMP_DIM)
    b.body.box((-1.2, -0.6, 0.32), (1.6, -0.5, 0.42), STRUCT)                                                      # the trolley: two rails, two saddles, four wheels
    b.body.box((-1.2, 0.5, 0.32), (1.6, 0.6, 0.42), STRUCT)
    for sx in (-0.7, 0.8):
        b.body.box((sx - 0.05, -0.62, 0.42), (sx + 0.05, 0.62, 0.55), TRIM)
        for sy in (-0.56, 0.56):
            b.body.cyl((sx, sy * 0.95, 0.16), (sx, sy * 1.12, 0.16), 0.16, RUBBER, seg=12)
            b.body.box((sx - 0.03, sy - 0.03, 0.16), (sx + 0.03, sy + 0.03, 0.34), TRIM)
    b.soft.cyl((1.6, 0.0, 0.37), (2.3, 0.0, 0.7), 0.02, TRIM, seg=6)
    b.soft.cyl((-1.32, 0.0, zc), (-1.3, 0.0, zc), 0.73, TRIM, seg=16)                                                 # the cut end: a flange, a dark inside with two ribs and a few wires
    b.soft.cyl((-1.335, 0.0, zc), (-1.32, 0.0, zc), 0.6, STRUCT, seg=16)
    for r in (0.5, 0.3):
        b.soft.cyl((-1.345, 0.0, zc), (-1.335, 0.0, zc), r, TRIM, seg=16)
    b.soft.cyl((-1.36, 0.0, zc), (-1.345, 0.0, zc), 0.2, STRUCT, seg=12)
    b.soft.tube([(-1.35, 0.1, zc + 0.1), (-1.6, 0.3, zc - 0.1), (-1.9, 0.35, zc - 0.5), (-2.0, 0.3, 0.2)], 0.025, RUBBER, seg=6)
    b.soft.tube([(-1.35, -0.1, zc), (-1.55, -0.3, zc - 0.1), (-1.8, -0.4, zc - 0.5), (-1.9, -0.35, 0.25)], 0.02, CRATE_ORANGE, seg=6)


def engine_stand(b: SParts) -> None:
    """A turbofan engine on a wheeled stand, axis along x (intake towards +x), 3.4 m: a cone and spinner at the intake, a fan case with a ring of blades visible, a long
    core with bands, an annular combustor, a nozzle with a lit throat; accessory gearbox and pipes underneath; the stand is a frame with two cradles and four wheels."""
    zc = 1.0
    b.body.cyl((-1.7, 0.0, zc), (-1.2, 0.0, zc), 0.38, STEEL, seg=18, r2=0.28)                                      # the nozzle
    b.emit.lamp_cyl((-1.72, 0.0, zc), (-1.7, 0.0, zc), 0.24, "engineering", LAMP, seg=18)
    b.body.cyl((-1.2, 0.0, zc), (-0.1, 0.0, zc), 0.5, STRUCT, seg=18, r2=0.42)                                      # the turbine and the core
    for k in range(5):
        b.soft.cyl((-1.1 + k * 0.22, 0.0, zc), (-1.07 + k * 0.22, 0.0, zc), 0.52, TRIM, seg=18)
    b.body.cyl((-0.1, 0.0, zc), (0.9, 0.0, zc), 0.46, CRATE_GREY, seg=18, r2=0.58)                                  # the compressor flaring into the fan case
    b.body.cyl((0.9, 0.0, zc), (1.45, 0.0, zc), 0.62, STEEL, seg=20)                                                # the fan case
    b.soft.cyl((1.45, 0.0, zc), (1.5, 0.0, zc), 0.66, TRIM, seg=20)
    b.body.cyl((1.5, 0.0, zc), (1.7, 0.0, zc), 0.28, STRUCT, seg=14, r2=0.1)                                        # the spinner
    for k in range(18):                                                                                             # fan blades, seen from the front
        a = 2 * math.pi * k / 18
        b.soft.box((1.43, 0.12 * math.cos(a) + 0.2 * math.cos(a) - 0.015, zc + 0.32 * math.sin(a) - 0.015), (1.47, 0.12 * math.cos(a) + 0.5 * math.cos(a) + 0.015, zc + 0.5 * math.sin(a) + 0.015), TRIM)
    b.body.box((-0.4, -0.18, zc - 0.62), (0.7, 0.18, zc - 0.4), CRATE_OLIVE)                                        # the accessory gearbox
    b.soft.tube([(0.7, 0.1, zc - 0.5), (0.9, 0.35, zc - 0.3), (1.1, 0.5, zc - 0.05)], 0.03, RUBBER, seg=6)
    b.soft.tube([(-0.4, 0.1, zc - 0.5), (-0.6, 0.45, zc - 0.2), (-0.8, 0.55, zc + 0.2)], 0.025, CRATE_ORANGE, seg=6)
    b.body.box((-1.3, -0.45, 0.28), (1.5, -0.35, 0.38), STRUCT)                                                     # the stand
    b.body.box((-1.3, 0.35, 0.28), (1.5, 0.45, 0.38), STRUCT)
    for sx in (-0.6, 0.9):
        b.body.box((sx - 0.06, -0.5, 0.38), (sx + 0.06, 0.5, 0.5), TRIM)
        b.body.box((sx - 0.05, -0.5, 0.5), (sx + 0.05, -0.38, zc - 0.3), TRIM)
        b.body.box((sx - 0.05, 0.38, 0.5), (sx + 0.05, 0.5, zc - 0.3), TRIM)
        for sy in (-0.5, 0.5):
            b.body.cyl((sx, sy * 0.95, 0.14), (sx, sy * 1.12, 0.14), 0.14, RUBBER, seg=12)
    b.emit.label((0.0, 0.64, zc), 0.5, 0.125, (0, 1, 0), "tag_08")


def wing_jig(b: SParts) -> None:
    """A stub wing section on two jig stands, leading edge towards +x: a swept slab with a flap and an aileron, an actuator on the underside, the stands with adjusting screws."""
    poly = [(-0.9, -1.4), (0.9, -1.4), (0.5, 1.4), (-0.7, 1.4)]
    b.body.prism(poly, 1.0, 1.28, CRATE_GREY)
    b.body.prism([(0.9, -1.4), (1.02, -1.4), (0.62, 1.4), (0.5, 1.4)], 1.0, 1.28, IVORY)
    for sy in (-0.9, -0.45, 0.0, 0.45, 0.9):
        b.soft.box((-0.88 + 0.3 * abs(sy), sy - 0.006, 1.28), (0.6 - 0.3 * abs(sy) * 0.9, sy + 0.006, 1.285), STRUCT)
    for sy in (-1.1, 0.0, 1.1):                                                                                   # the flap's hinge brackets under the trailing edge
        b.body.box((-0.95, sy - 0.07, 1.05), (-0.82, sy + 0.07, 1.2), TRIM)
    b.body.box((-0.92, -1.3, 1.02), (-0.8, 1.3, 1.28), STRUCT)                                                    # the trailing-edge strip (the flap's gap)
    b.emit.lamp_box((-0.62, 1.36, 1.1), (-0.5, 1.42, 1.2), "red", LAMP)
    b.soft.box((-0.7, -0.7, 0.9), (-0.3, -0.3, 1.0), COMPOSITE)
    b.soft.cyl((-0.5, 0.2, 0.92), (-0.1, 0.5, 0.98), 0.03, TRIM, seg=6)
    for sy in (-1.0, 1.0):
        b.body.box((-0.1, sy - 0.2, 0.0), (0.4, sy + 0.2, 0.06), STRUCT)
        b.body.box((0.0, sy - 0.05, 0.06), (0.3, sy + 0.05, 0.98), TRIM)
        b.body.box((-0.05, sy - 0.12, 0.98), (0.35, sy + 0.12, 1.0), STEEL)
        b.soft.cyl((0.15, sy, 0.3), (0.15, sy, 0.7), 0.025, TRIM, seg=6)


def avionics_bench(b: SParts, w: float = 2.4) -> None:
    """An avionics test bench facing +x: a steel top on a cabinet, a rack of four black boxes with lit faces on a riser behind, an oscilloscope screen, a harness with a connector."""
    b.body.box((-0.4, -w / 2, 0.0), (0.4, w / 2, 0.88), COMPOSITE)
    b.body.box((-0.42, -w / 2 - 0.01, 0.88), (0.42, w / 2 + 0.01, 0.92), STEEL)
    b.body.box((-0.4, -w / 2, 0.92), (-0.36, w / 2, 1.9), STRUCT)
    for k in range(4):
        z = 0.98 + k * 0.22
        n = 3
        for j in range(n):
            y0 = -w / 2 + 0.1 + j * (w - 0.2) / n
            b.soft.box((-0.36, y0, z), (-0.1, y0 + (w - 0.2) / n - 0.06, z + 0.18), CRATE_GREY)
            b.emit.lamp_box((-0.1, y0 + 0.04, z + 0.06), (-0.095, y0 + 0.12, z + 0.1), ("green", "amber", "cyan")[(j + k) % 3], LAMP_DIM)
            b.emit.lamp_box((-0.1, y0 + 0.16, z + 0.06), (-0.095, y0 + 0.3, z + 0.08), "white_dim", LAMP_DIM)
    b.soft.box((0.0, -0.32, 0.92), (0.3, 0.32, 1.22), STRUCT)
    b.soft.box((0.0, -0.3, 1.0), (0.01, 0.3, 1.2), DGLASS)
    b.emit.label((0.012, 0.0, 1.1), 0.58, 0.27, (1, 0, 0), "scr_wave")
    b.soft.tube([(0.35, w / 2 - 0.2, 0.92), (0.6, w / 2 - 0.1, 0.95), (0.7, w / 2 + 0.1, 0.5), (0.65, w / 2 + 0.3, 0.1)], 0.02, RUBBER, seg=6)


def landing_strut(b: SParts) -> None:
    """A landing gear leg standing on a maintenance stand: a pad, a leg with a damper, a wheel, a torque link, the stand's two frames."""
    b.body.cyl((0.0, 0.0, 0.0), (0.0, 0.0, 0.05), 0.4, STRUCT, seg=14)
    b.body.cyl((0.0, 0.0, 0.05), (0.0, 0.0, 1.2), 0.1, TRIM, seg=10)
    b.body.cyl((0.0, 0.0, 0.5), (0.0, 0.0, 0.95), 0.14, STEEL, seg=10)
    b.body.cyl((0.0, -0.14, 0.32), (0.0, 0.14, 0.32), 0.3, RUBBER, seg=16)
    b.soft.cyl((0.0, -0.15, 0.32), (0.0, -0.1, 0.32), 0.16, TRIM, seg=10)
    b.soft.cyl((0.0, 0.1, 0.32), (0.0, 0.15, 0.32), 0.16, TRIM, seg=10)
    b.soft.cyl((0.0, 0.0, 0.95), (0.0, 0.2, 1.15), 0.025, TRIM, seg=6)
    b.soft.cyl((0.25, 0.0, 0.05), (0.0, 0.0, 0.9), 0.02, TRIM, seg=6)
    b.soft.cyl((-0.25, 0.0, 0.05), (0.0, 0.0, 0.9), 0.02, TRIM, seg=6)


# ---------------------------------------------------------------------------------------------------------------------- the magazine
def missile(b: SParts, l: float = 2.6, r: float = 0.1, body: str = IVORY, nose: str = CRATE_ORANGE) -> None:
    """A missile lying along +x, centred on the origin: a body, an ogive nose, four tail fins, a seeker lens, a yellow band, a warning plate."""
    b.soft.cyl((-l / 2, 0, 0), (l / 2 - 0.35, 0, 0), r, body, seg=10)
    b.soft.cyl((l / 2 - 0.35, 0, 0), (l / 2, 0, 0), r, nose, seg=10, r2=0.015)
    b.soft.box((-l / 2 + 0.02, -r - 0.1, -0.008), (-l / 2 + 0.32, r + 0.1, 0.008), STRUCT)                           # the fins: two plates crossing
    b.soft.box((-l / 2 + 0.02, -0.008, -r - 0.1), (-l / 2 + 0.32, 0.008, r + 0.1), STRUCT)
    b.soft.cyl((0.2, 0, 0), (0.28, 0, 0), r + 0.004, CRATE_ORANGE, seg=12)
    b.soft.cyl((-0.5, 0, 0), (-0.45, 0, 0), r + 0.004, PAINT_RED, seg=12)


def missile_rack(b: SParts, tiers: int = 3, per: int = 2, l: float = 2.6) -> None:
    """A steel rack for horizontal missiles along x facing +y... facing +x: `tiers` levels of `per` missiles side by side in cradles, on a base with forklift pockets; a hazard
    plate and a lit lock at the end."""
    pitch = 0.34
    w = per * pitch + 0.2
    b.body.box((-l / 2 - 0.05, -w / 2, 0.0), (l / 2 + 0.05, w / 2, 0.12), STRUCT)
    for sx in (-l / 2 + 0.3, l / 2 - 0.5):
        for sy in (-w / 2 + 0.02, w / 2 - 0.08):
            b.body.box((sx - 0.04, sy, 0.12), (sx + 0.04, sy + 0.06, 0.2 + tiers * 0.4), TRIM)
        for t in range(tiers):
            z = 0.2 + t * 0.4
            b.body.box((sx - 0.05, -w / 2 + 0.02, z), (sx + 0.05, w / 2 - 0.02, z + 0.04), STEEL)
    for t in range(tiers):
        for k in range(per):
            y = (k - (per - 1) / 2) * pitch
            with b.at(T(0.0, y, 0.2 + t * 0.4 + 0.04 + 0.1)):
                missile(b, l - 0.1)
    b.emit.label((l / 2 + 0.052, 0.0, 0.07), w - 0.2, 0.06, (1, 0, 0), "hazard_h")


def shell_rack(b: SParts, w: float = 2.0, rows: int = 3, h: float = 1.5) -> None:
    """A rack of railgun slugs standing on end, facing +x: a frame with two perforated plates holding rows of olive rounds with orange bands and tip caps, a lit lock and a tag."""
    d = 0.6
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.1), STRUCT)
    b.body.box((-d / 2, -w / 2, h), (d / 2, w / 2, h + 0.05), STEEL)
    for sy in (-w / 2, w / 2 - 0.05):
        for sx in (-d / 2, d / 2 - 0.05):
            b.body.box((sx, sy, 0.1), (sx + 0.05, sy + 0.05, h), TRIM)
    n = int(w / 0.2)
    rows_y = [(-d / 2 + 0.17 + 0.13 * k) for k in range(rows)] if rows > 1 else [0.0]
    for r_i in range(rows):
        for k in range(n):
            y = -w / 2 + 0.12 + k * (w - 0.24) / max(1, n - 1)
            x = rows_y[r_i] * 0.9
            b.soft.cyl((x, y, 0.1), (x, y, h - 0.25), 0.07, CRATE_OLIVE, seg=10)
            b.soft.cyl((x, y, h - 0.35), (x, y, h - 0.3), 0.073, CRATE_ORANGE, seg=10)
            b.soft.cyl((x, y, h - 0.25), (x, y, h), 0.07, STEEL, seg=10, r2=0.03)
    b.emit.lamp_box((d / 2 + 0.002, -0.06, 0.04), (d / 2 + 0.01, 0.06, 0.08), "red", LAMP_DIM)
    b.emit.label_fit((d / 2 + 0.002, 0.0, 0.2), 0.8, "eq_ammo", (1, 0, 0))


def hoist_platform(b: SParts, w: float = 1.9) -> None:
    """The head of a munitions hoist let into the floor, centred on the origin: a square plate with a hazard border, four corner posts, two chain guards and a gate side
    towards +x, a beacon, a control post with an up and a down button."""
    hw = w / 2
    b.body.box((-hw - 0.15, -hw - 0.15, 0.0), (hw + 0.15, hw + 0.15, 0.02), CRATE_ORANGE)
    b.body.box((-hw, -hw, 0.02), (hw, hw, 0.04), STRUCT)
    b.soft.box((-hw + 0.1, -hw + 0.1, 0.04), (hw - 0.1, hw - 0.1, 0.045), RUBBER)
    for sx in (-hw, hw):
        for sy in (-hw, hw):
            b.body.cyl((sx, sy, 0.04), (sx, sy, 1.1), 0.04, CRATE_ORANGE, seg=8)
    for (a, c) in (((-hw, -hw), (-hw, hw)), ((-hw, -hw), (hw, -hw)), ((-hw, hw), (hw, hw))):
        for z in (0.55, 0.95):
            b.soft.tube([(a[0], a[1], z), ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, z - 0.06), (c[0], c[1], z)], 0.012, CRATE_ORANGE, seg=5)
    b.emit.lamp_cyl((hw, hw, 1.1), (hw, hw, 1.2), 0.06, "amber", LAMP, seg=10)
    b.body.box((hw + 0.3, -0.12, 0.0), (hw + 0.5, 0.12, 1.05), STRUCT)
    b.emit.lamp_box((hw + 0.5, -0.07, 0.8), (hw + 0.51, -0.03, 0.84), "green", LAMP)
    b.emit.lamp_box((hw + 0.5, 0.03, 0.8), (hw + 0.51, 0.07, 0.84), "red", LAMP)
    b.emit.label_fit((hw + 0.502, 0.0, 0.95), 0.2, "eq_ammo", (1, 0, 0))


def sprinkler_line(b: SParts, p0, p1, every: float = 1.6) -> None:
    """A fire-suppression main along p0 -> p1 under the ceiling: a red pipe on brackets with a sprinkler head hanging every `every` m."""
    a, c = Vector(p0), Vector(p1)
    b.soft.cyl(a, c, 0.04, PAINT_RED, seg=8)
    n = max(1, int((c - a).length / every))
    for k in range(n + 1):
        p = a + (c - a) * (k / n)
        b.soft.cyl(p, p + Vector((0, 0, -0.1)), 0.015, TRIM, seg=6)
        b.soft.cyl(p + Vector((0, 0, -0.1)), p + Vector((0, 0, -0.13)), 0.05, CRATE_ORANGE, seg=8)
        b.soft.cyl(p, p + Vector((0, 0, 0.3)), 0.012, TRIM, seg=5)


# ---------------------------------------------------------------------------------------------------------------------- cargo
def cargo_container(b: SParts, w: float = 3.0, d: float = 1.5, h: float = 1.6, mat: str = CRATE_BLUE, tag: str = "eq_stores") -> None:
    """A cargo container facing +x (its door end): a ribbed box with corner castings, two door leaves with locking bars, a label; w along y, d along x."""
    b.body.box((-d / 2, -w / 2, 0.06), (d / 2, w / 2, h), mat)
    for k in range(1, int(w / 0.3)):
        y = -w / 2 + k * w / int(w / 0.3)
        b.soft.box((-d / 2 - 0.012, y - 0.025, 0.12), (-d / 2, y + 0.025, h - 0.1), STRUCT)
        b.soft.box((d / 2, y - 0.025, 0.12), (d / 2 + 0.012, y + 0.025, h - 0.1), STRUCT)
    for sx in (-d / 2, d / 2 - 0.1):
        for sy in (-w / 2, w / 2 - 0.1):
            b.body.box((sx, sy, 0.0), (sx + 0.1, sy + 0.1, 0.1), STEEL)
            b.body.box((sx, sy, h - 0.1), (sx + 0.1, sy + 0.1, h), STEEL)
    b.soft.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.06), STRUCT)
    b.soft.box((d / 2 + 0.002, -w / 2 + 0.05, 0.14), (d / 2 + 0.02, w / 2 - 0.05, h - 0.08), STRUCT)
    for k in (-1, 1):
        b.soft.box((d / 2 + 0.02, k * w * 0.22 - 0.02, 0.2), (d / 2 + 0.04, k * w * 0.22 + 0.02, h - 0.16), TRIM)
    b.soft.box((d / 2 + 0.02, -0.01, 0.2), (d / 2 + 0.03, 0.01, h - 0.16), STRUCT)
    b.emit.label_fit((d / 2 + 0.032, w * 0.3, h - 0.24), min(0.8, w * 0.4), tag, (1, 0, 0))
    b.emit.lamp_box((d / 2 + 0.02, -w / 2 + 0.1, 0.18), (d / 2 + 0.03, -w / 2 + 0.16, 0.22), "green", LAMP_DIM)


def pallet_truck(b: SParts) -> None:
    """A manual pallet truck facing +x: a steel chassis with two forks and a roller at each tip, a tiller handle with a grip, a hydraulic lever."""
    for sy in (-0.28, 0.28):
        b.body.box((-0.1, sy - 0.08, 0.03), (1.15, sy + 0.08, 0.13), CRATE_ORANGE)
        b.body.cyl((1.1, sy - 0.07, 0.07), (1.1, sy + 0.07, 0.07), 0.05, RUBBER, seg=8)
    b.body.box((-0.15, -0.4, 0.13), (0.1, 0.4, 0.2), CRATE_ORANGE)
    b.body.box((-0.12, -0.08, 0.2), (0.0, 0.08, 0.35), TRIM)
    b.soft.cyl((-0.06, 0.0, 0.3), (-0.55, 0.0, 1.05), 0.02, TRIM, seg=6)
    b.soft.cyl((-0.55, -0.12, 1.05), (-0.55, 0.12, 1.05), 0.025, RUBBER, seg=8)


def forklift(b: SParts) -> None:
    """A small electric forklift facing +x: an olive-and-orange chassis with a counterweight, a cab frame with a roof guard and a seat, a mast with a carriage and two forks,
    four wheels, a beacon."""
    b.body.box((-1.0, -0.55, 0.22), (0.7, 0.55, 0.7), CRATE_OLIVE)
    b.body.box((-1.05, -0.58, 0.28), (-0.7, 0.58, 0.95), CRATE_ORANGE)                                                # the counterweight
    for sx in (-0.7, 0.2):
        for sy in (-0.5, 0.5):
            b.body.box((sx - 0.025, sy - 0.025, 0.7), (sx + 0.025, sy + 0.025, 2.0), TRIM)
    b.body.box((-0.75, -0.55, 2.0), (0.25, 0.55, 2.04), TRIM)
    for k in range(5):
        b.soft.box((-0.7 + k * 0.2, -0.52, 2.04), (-0.66 + k * 0.2, 0.52, 2.06), STRUCT)
    b.soft.box((-0.55, -0.28, 0.7), (-0.15, 0.28, 0.8), FABRIC_GREY)
    b.soft.box((-0.58, -0.28, 0.8), (-0.52, 0.28, 1.25), FABRIC_GREY)
    b.soft.cyl((0.1, 0.0, 0.7), (0.2, 0.0, 1.15), 0.02, TRIM, seg=6)
    b.soft.box((0.08, -0.17, 1.12), (0.18, 0.17, 1.15), RUBBER)
    for sy in (-0.28, 0.28):                                                                                         # the mast and the carriage
        b.body.box((0.7, sy - 0.04, 0.1), (0.8, sy + 0.04, 2.3), STEEL)
    b.body.box((0.78, -0.4, 0.5), (0.86, 0.4, 1.0), STRUCT)
    for sy in (-0.28, 0.28):
        b.body.box((0.8, sy - 0.05, 0.05), (1.9, sy + 0.05, 0.1), STEEL)
        b.body.box((0.8, sy - 0.05, 0.05), (0.88, sy + 0.05, 0.6), STEEL)
    for sx in (-0.6, 0.45):
        for sy in (-0.55, 0.55):
            b.body.cyl((sx, sy * 0.92, 0.24), (sx, sy * 1.12, 0.24), 0.24, RUBBER, seg=14)
            b.soft.cyl((sx, sy * 1.11, 0.24), (sx, sy * 1.14, 0.24), 0.12, TRIM, seg=10)
    b.emit.lamp_cyl((-0.5, 0.0, 2.06), (-0.5, 0.0, 2.16), 0.07, "amber", LAMP, seg=10)
    b.emit.label((0.0, -0.556, 0.5), 0.5, 0.125, (0, -1, 0), "hazard_h")
