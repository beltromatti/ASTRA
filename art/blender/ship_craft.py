"""ASN Aquila interior kit: the craft that stand inside the ship's rooms (NAVE-2) — the Kestrel assault shuttle of the Deck 8 bay.

The Kestrel is the Marines' boarding craft (docs/BIBBIA.md §3 Boarding, §6 Deck 8): twelve fanti sit on two benches in its troop bay, it latches on to a hull with a
plasma breaching collar and opens a way through with it. It is built here as a prop in its own frame (origin on the floor under the middle of the craft, nose towards
+x, y to starboard, z up), parked on four legs with the troop ramp down, so a Captain can walk up the ramp and see the bay. 11.7 m with the ramp, 7.6 m over the wing
tips, 3.1 m to the top of the masts: it fits the 3.7 m bay with room to spare for the gantry. Same conventions as ship_furniture*.py."""
from __future__ import annotations

import math

from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (COMPOSITE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, IVORY, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL,
                      STRUCT, TRIM, SParts, lamp_strip)

BELLY = 0.62                         # the fuselage's underside over the floor
FLOOR = 0.70                         # the troop bay's floor (the ramp's hinge)
ROOF = 2.70                          # the troop bay's roof
BAY_W = 1.45                         # half-width of the troop bay
BAY_C = 0.40                         # the chamfer of its corners
X_BAY0, X_BAY1 = -5.0, -0.45         # the troop bay's extent


def _octagon(w: float, z0: float, z1: float, c: float):
    """The outline of the troop bay's section as 16 points (the 8 corners of a chamfered rectangle and the middle of each edge), counter-clockwise seen from +x."""
    corners = [(w, z0 + c), (w, z1 - c), (w - c, z1), (-(w - c), z1), (-w, z1 - c), (-w, z0 + c), (-(w - c), z0), (w - c, z0)]
    out = []
    for i, p in enumerate(corners):
        q = corners[(i + 1) % 8]
        out += [p, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)]
    return out


def _section(x: float, w: float, z0: float, z1: float, rnd: float, c: float = BAY_C, e: float = 3.0):
    """One ring of the fuselage's loft at station x: the octagon of the troop bay blended into a rounded box (a superellipse of exponent e) by `rnd` (0..1), point for
    point (the rounded box is sampled at the angle of each point of the octagon, so the rings never twist)."""
    zc, hh = (z0 + z1) / 2, (z1 - z0) / 2
    out = []
    for (py, pz) in _octagon(w, z0, z1, c * (1.0 - 0.5 * rnd)):
        t = math.atan2((pz - zc) / hh, py / w)
        ey = w * math.copysign(abs(math.cos(t)) ** (2 / e), math.cos(t))
        ez = zc + hh * math.copysign(abs(math.sin(t)) ** (2 / e), math.sin(t))
        out.append((x, (1 - rnd) * py + rnd * ey, (1 - rnd) * pz + rnd * ez))
    return out


def _plate(fb, x0: float, x1: float, p0, p1, t: float, mat: str) -> None:
    """A plate along the edge p0 -> p1 of a counter-clockwise outline in (y, z), from the edge inwards by t, extruded along x from x0 to x1."""
    dy, dz = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dy, dz)
    ang = math.degrees(math.atan2(dz, dy))
    ny, nz = dz / ln, -dy / ln                                   # the outward normal
    cy, cz = (p0[0] + p1[0]) / 2 - ny * t / 2, (p0[1] + p1[1]) / 2 - nz * t / 2
    fb.cbox(((x0 + x1) / 2, cy, cz), (x1 - x0, ln, t), mat, Rx(ang))


def _nacelle(b: SParts, y: float, z: float, x0: float = -5.15, x1: float = -0.9) -> None:
    """A wing-tip engine pod: a barrel with a blunt intake cone in front and a nozzle with a glowing throat behind, a fin standing on it."""
    r = 0.42
    b.body.cyl((x0 + 0.5, y, z), (x1, y, z), r, CRATE_OLIVE, seg=18)
    b.body.cyl((x1, y, z), (x1 + 0.8, y, z), r, CRATE_OLIVE, seg=18, r2=0.16)                                  # the intake cone
    b.soft.cyl((x1 + 0.78, y, z), (x1 + 0.86, y, z), 0.16, STRUCT, seg=18, r2=0.12)
    b.body.cyl((x0 + 0.5, y, z), (x0, y, z), r, STRUCT, seg=18, r2=0.33)                                       # the nozzle
    b.soft.cyl((x0, y, z), (x0 - 0.12, y, z), 0.33, TRIM, seg=18, r2=0.36)                                       # its lip
    b.emit.lamp_cyl((x0 - 0.115, y, z), (x0 - 0.12, y, z), 0.27, "cyan", LAMP, seg=18)                           # the throat, idling
    b.soft.cyl((x0 + 0.9, y, z), (x0 + 0.95, y, z), r + 0.01, TRIM, seg=18)                                      # a band
    b.soft.cyl((x1 - 0.5, y, z), (x1 - 0.46, y, z), r + 0.01, CRATE_ORANGE, seg=18)                              # an orange band
    for k in range(5):                                                                                           # panel seams along the barrel
        a = math.radians(k * 72.0 + 18.0)
        b.soft.box((x0 + 1.0, y + (r + 0.004) * math.sin(a) - 0.01, z + (r + 0.004) * math.cos(a) - 0.01),
                   (x1 - 0.7, y + (r + 0.004) * math.sin(a) + 0.01, z + (r + 0.004) * math.cos(a) + 0.01), STRUCT)
    # the fin on top: a swept trapezoid, 6 cm thick, with a light on its tip
    b.body.extrude_y([(x0 + 0.3, z + r - 0.04), (x0 + 1.9, z + r - 0.04), (x0 + 1.4, z + 1.45), (x0 + 0.35, z + 1.45)], y - 0.03, y + 0.03, CRATE_GREY)
    b.emit.lamp_box((x0 + 0.35, y - 0.035, z + 1.38), (x0 + 0.65, y + 0.035, z + 1.45), "amber", LAMP)


def _wing(b: SParts, s: int) -> None:
    """One wing (s = +1 starboard, -1 port): a thick swept stub with a pod at its tip, two rocket pods under it and a leading edge of grey."""
    poly = [(-2.6, s * 1.30), (1.2, s * 1.30), (-0.7, s * 3.70), (-2.9, s * 3.70)]
    if s < 0:
        poly = poly[::-1]
    b.body.prism(poly, 1.02, 1.36, CRATE_OLIVE)
    lead = [(1.2, s * 1.30), (1.32, s * 1.30), (-0.58, s * 3.70), (-0.7, s * 3.70)]
    b.body.prism(lead if s > 0 else lead[::-1], 1.02, 1.36, CRATE_GREY)                                              # the leading edge
    _nacelle(b, s * 3.70, 1.19)
    for yy in (s * 2.05, s * 2.95):                                                                              # the hardpoints: a pylon and a rocket pod
        b.body.box((-1.9, yy - 0.04, 0.86), (-0.9, yy + 0.04, 1.02), STRUCT)
        b.body.cyl((-2.4, yy, 0.76), (-0.3, yy, 0.76), 0.14, CRATE_GREY, seg=12)
        b.body.cyl((-0.3, yy, 0.76), (0.12, yy, 0.76), 0.14, CRATE_ORANGE, seg=12, r2=0.06)
        for k in range(3):                                                                                       # the tube mouths, behind
            a = math.radians(k * 120.0)
            b.soft.cyl((-2.43, yy + 0.07 * math.sin(a), 0.76 + 0.07 * math.cos(a)), (-2.40, yy + 0.07 * math.sin(a), 0.76 + 0.07 * math.cos(a)), 0.035, STRUCT, seg=8)
    for xx in (-2.3, -1.4, -0.5):                                                                                # flap and aileron seams on the upper surface
        b.soft.box((xx - 0.012, s * 1.4, 1.36), (xx + 0.012, s * 3.6, 1.365), STRUCT)
    b.emit.lamp_box((-2.75, s * 3.50, 1.355), (-2.55, s * 3.70, 1.36), "red" if s > 0 else "green", LAMP)


def _leg(b: SParts, x: float, y: float, brace: float) -> None:
    """A landing leg: a pad, a strut and a hydraulic damper, a brace towards the middle."""
    b.body.box((x - 0.26, y - 0.2, 0.0), (x + 0.26, y + 0.2, 0.07), STRUCT)
    b.body.cyl((x, y, 0.06), (x, y, BELLY + 0.02), 0.075, TRIM, seg=10)
    b.body.cyl((x, y, 0.24), (x, y, 0.5), 0.10, STRUCT, seg=10)
    sy = -1.0 if y > 0 else 1.0
    b.soft.cyl((x + brace, y + sy * 0.55, BELLY + 0.02), (x, y, 0.28), 0.03, TRIM, seg=6)
    b.soft.box((x - 0.2, y - 0.17, 0.07), (x + 0.2, y + 0.17, 0.085), CRATE_ORANGE)


def _bench(b: SParts, side: int, x0: float, x1: float) -> None:
    """A troop bench along the wall (side = +1 starboard, -1 port): a sprung seat with a back, a lap harness and a grab handle for every place, a helmet hook above."""
    yw = side * 1.34
    n = int(round((x1 - x0) / 0.6))
    pitch = (x1 - x0) / n
    b.body.box((x0, yw - side * 0.46, FLOOR + 0.40), (x1, yw, FLOOR + 0.46), COMPOSITE)                              # the seat board
    b.body.box((x0, yw - side * 0.46, FLOOR), (x1, yw - side * 0.42, FLOOR + 0.40), STRUCT)                          # its front panel
    for k in range(n):
        xa = x0 + k * pitch
        b.soft.box((xa + 0.04, yw - side * 0.44, FLOOR + 0.46), (xa + pitch - 0.04, yw - side * 0.04, FLOOR + 0.52), FABRIC_NAVY)       # the cushion
        b.soft.box((xa + 0.05, yw - side * 0.08, FLOOR + 0.52), (xa + pitch - 0.05, yw - side * 0.02, FLOOR + 1.28), FABRIC_NAVY)         # the back
        b.soft.box((xa + 0.09, yw - side * 0.17, FLOOR + 0.52), (xa + 0.13, yw - side * 0.13, FLOOR + 1.20), RUBBER)                       # the shoulder straps
        b.soft.box((xa + pitch - 0.13, yw - side * 0.17, FLOOR + 0.52), (xa + pitch - 0.09, yw - side * 0.13, FLOOR + 1.20), RUBBER)
        b.soft.box((xa + 0.10, yw - side * 0.36, FLOOR + 0.52), (xa + pitch - 0.10, yw - side * 0.32, FLOOR + 0.545), RUBBER)               # the lap strap
        b.soft.box((xa + pitch / 2 - 0.03, yw - side * 0.31, FLOOR + 0.545), (xa + pitch / 2 + 0.03, yw - side * 0.29, FLOOR + 0.58), TRIM)  # the buckle
        b.soft.cyl((xa + pitch / 2, yw - side * 0.04, FLOOR + 1.62), (xa + pitch / 2, yw - side * 0.10, FLOOR + 1.62), 0.025, TRIM, seg=6)  # the helmet hook
    b.soft.cyl((x0, yw - side * 0.52, FLOOR + 1.75), (x1, yw - side * 0.52, FLOOR + 1.75), 0.022, TRIM, seg=6)                           # the overhead grab rail
    for k in range(n + 1):
        xa = x0 + k * pitch
        b.soft.cyl((xa, yw - side * 0.52, FLOOR + 1.75), (xa, yw - side * 0.30, FLOOR + 1.98), 0.015, TRIM, seg=5)


def kestrel(b: SParts, collar: int = 1, number: str = "eq_k1") -> None:
    """The Kestrel, nose towards +x, centred on the origin (x -7.6 .. 5.4 with the ramp), parked on its legs with the troop ramp down. `collar`: the side (+1 starboard,
    -1 port) of the plasma breaching collar; `number`: the label tile of its hull number."""
    # ----------------------------------------------------------------------------------------------------- the forward fuselage (a solid loft)
    stations = [(-0.45, 1.45, BELLY, ROOF, 0.0), (1.0, 1.45, BELLY, 2.74, 0.0), (2.2, 1.38, BELLY + 0.02, 2.62, 0.35), (3.2, 1.2, BELLY + 0.06, 2.34, 0.7),
                (4.2, 0.92, BELLY + 0.14, 1.98, 1.0), (4.9, 0.60, BELLY + 0.26, 1.64, 1.0), (5.35, 0.34, BELLY + 0.36, 1.46, 1.0)]
    b.body.loft([_section(x, w, z0, z1, rn) for (x, w, z0, z1, rn) in stations], CRATE_OLIVE)
    b.body.box((2.0, -1.10, BELLY - 0.02), (4.4, 1.10, BELLY + 0.08), STRUCT)                                         # the belly armour plate
    # the nose: a sensor blister, a chin turret with two barrels
    b.body.sphere((5.30, 0.0, 1.10), 0.22, STRUCT, seg=14, rings=8, squash=(1.1, 1.0, 0.8))
    b.soft.sphere((5.46, 0.0, 1.10), 0.09, DGLASS, seg=10, rings=6)
    b.emit.lamp_box((5.25, -0.30, 1.36), (5.30, -0.20, 1.40), "green", LAMP)
    b.emit.lamp_box((5.25, 0.20, 1.36), (5.30, 0.30, 1.40), "red", LAMP)
    b.body.sphere((3.9, 0.0, BELLY - 0.04), 0.27, STRUCT, seg=14, rings=8, squash=(1.0, 1.0, 0.8))
    for sy in (-0.09, 0.09):
        b.soft.cyl((3.95, sy, BELLY - 0.12), (4.75, sy, BELLY - 0.12), 0.032, TRIM, seg=8)
        b.soft.cyl((4.62, sy, BELLY - 0.12), (4.75, sy, BELLY - 0.12), 0.045, STRUCT, seg=8)
    # the canopy: dark glass in a few frames, two pilots' seats, a lit console behind the glass
    glass = [(1.45, 0.62, 2.55, 2.97), (2.25, 0.70, 2.50, 3.10), (3.0, 0.66, 2.38, 3.04), (3.7, 0.54, 2.20, 2.72), (4.25, 0.38, 2.02, 2.30)]
    b.soft.loft([[(x, y, z) for (_x, y, z) in _section(x, w, z0, z1, 0.8, 0.25)] for (x, w, z0, z1) in glass], DGLASS)
    for (x, w, z0, z1) in glass[1:4]:                                                                              # the frame ribs: thin rings round the glass
        b.soft.loft([[(x - 0.02, y * 1.005, z) for (_x, y, z) in _section(x, w + 0.012, z0, z1 + 0.01, 0.8, 0.25)],
                     [(x + 0.02, y * 1.005, z) for (_x, y, z) in _section(x, w + 0.012, z0, z1 + 0.01, 0.8, 0.25)]], TRIM, caps=False)
    for sy in (-0.36, 0.36):
        b.soft.box((2.3, sy - 0.18, 2.52), (2.75, sy + 0.18, 2.95), FABRIC_GREY)
    b.emit.lamp_box((3.35, -0.42, 2.56), (3.7, 0.42, 2.60), "cyan", LAMP_DIM)
    # ----------------------------------------------------------------------------------------------------- the troop bay: an octagonal tube open at the tail
    out = _octagon(BAY_W, BELLY, ROOF, BAY_C)
    pts8 = out[0::2]
    for i in range(8):
        if i != 6:                                                                                                   # (the floor is built below)
            _plate(b.body, X_BAY0, X_BAY1, pts8[i], pts8[(i + 1) % 8], 0.11, CRATE_OLIVE)                          # the skin, 11 cm
    b.body.box((X_BAY0, -1.34, FLOOR - 0.08), (X_BAY1, 1.34, FLOOR), STRUCT)                                         # the floor structure
    b.body.box((X_BAY0, -1.30, FLOOR), (X_BAY1, 1.30, FLOOR + 0.02), DECK)                                           # the floor plates
    inner = _octagon(BAY_W - 0.11, FLOOR + 0.02, ROOF - 0.11, 0.355)                                               # the lining of the walls and the roof: composite panels
    in8 = inner[0::2]
    for i in range(8):
        if i != 6:                                                                                                   # (the floor is the deck plating)
            _plate(b.soft, X_BAY0 + 0.05, X_BAY1 - 0.05, in8[i], in8[(i + 1) % 8], 0.02, COMPOSITE)
    b.body.box((X_BAY1 - 0.1, -1.34, FLOOR), (X_BAY1, -0.46, ROOF - 0.12), STRUCT)                                  # the forward bulkhead with a hatch to the cockpit
    b.body.box((X_BAY1 - 0.1, 0.46, FLOOR), (X_BAY1, 1.34, ROOF - 0.12), STRUCT)
    b.body.box((X_BAY1 - 0.1, -0.46, 2.12), (X_BAY1, 0.46, ROOF - 0.12), STRUCT)
    b.soft.box((X_BAY1 - 0.11, -0.50, FLOOR), (X_BAY1 - 0.09, -0.46, 2.14), TRIM)
    b.soft.box((X_BAY1 - 0.11, 0.46, FLOOR), (X_BAY1 - 0.09, 0.50, 2.14), TRIM)
    b.soft.box((X_BAY1 - 0.11, -0.50, 2.12), (X_BAY1 - 0.09, 0.50, 2.16), TRIM)
    b.emit.lamp_box((X_BAY1 - 0.115, -0.30, 2.22), (X_BAY1 - 0.105, 0.30, 2.26), "amber", LAMP_DIM)
    for side in (1, -1):
        _bench(b, side, -4.5, -0.95)
    # the roof strips of the bay, a rifle rack on the bulkhead, a medical case
    lamp_strip(b.emit, (-4.6, -0.5, ROOF - 0.125), (-0.95, -0.5, ROOF - 0.125), 0.07, 0.01, "white_warm", LAMP_DIM)
    lamp_strip(b.emit, (-4.6, 0.5, ROOF - 0.125), (-0.95, 0.5, ROOF - 0.125), 0.07, 0.01, "white_warm", LAMP_DIM)
    for k in range(4):
        b.soft.box((X_BAY1 - 0.17, -1.28 + k * 0.1, FLOOR + 0.9), (X_BAY1 - 0.11, -1.22 + k * 0.1, FLOOR + 1.75), STRUCT)           # four rifles in the rack
    b.body.box((X_BAY1 - 0.4, -1.25, FLOOR + 1.0), (X_BAY1 - 0.11, -1.0, FLOOR + 1.9), COMPOSITE)
    b.body.box((X_BAY1 - 0.19, 1.0, FLOOR + 0.9), (X_BAY1 - 0.11, 1.3, FLOOR + 1.35), PAINT_RED)                      # the medical case
    b.emit.label((X_BAY1 - 0.191, 1.15, FLOOR + 1.12), 0.18, 0.18, (-1, 0, 0), "icon_aid", up=(0, 0, 1))
    # the opening's frame at the tail (jambs and header proud of the skin) and the ramp-down light
    for i in range(8):
        if i != 6:
            _plate(b.body, X_BAY0 - 0.04, X_BAY0 + 0.06, pts8[i], pts8[(i + 1) % 8], 0.16, TRIM)
    b.emit.lamp_box((X_BAY0 - 0.045, -1.00, ROOF - 0.20), (X_BAY0 - 0.04, 1.00, ROOF - 0.15), "red", LAMP)
    # ----------------------------------------------------------------------------------------------------- the ramp (down): a slab, rails, tread strips, rams
    ramp = [(-5.0, FLOOR), (-7.65, 0.03), (-7.65, 0.12), (-5.0, FLOOR + 0.09)]
    b.body.extrude_y(ramp, -1.25, 1.25, DECK)
    for k in range(1, 9):
        t = k / 9.0
        xa, za = -5.0 + t * (-7.65 + 5.0), FLOOR + 0.09 + t * (0.12 - FLOOR - 0.09)
        b.soft.box((xa - 0.03, -1.15, za), (xa + 0.03, 1.15, za + 0.012), RUBBER)
    b.soft.box((-7.68, -1.25, 0.0), (-7.60, 1.25, 0.14), CRATE_ORANGE)                                                # the lip, orange
    for sy in (-1.25, 1.19):                                                                                          # the side kerbs follow the slope
        b.soft.extrude_y([(-5.0, FLOOR + 0.09), (-7.65, 0.12), (-7.65, 0.19), (-5.0, FLOOR + 0.16)], sy, sy + 0.06, TRIM)
    for sy in (-1.05, 1.05):                                                                                          # the two hydraulic rams
        b.soft.cyl((-4.95, sy, 1.95), (-6.0, sy, 0.62), 0.04, TRIM, seg=6)
        b.soft.cyl((-4.95, sy, 1.95), (-5.5, sy, 1.32), 0.06, STRUCT, seg=6)
    b.emit.lamp_box((-7.64, -1.1, 0.125), (-7.60, 1.1, 0.135), "amber", LAMP)
    # ----------------------------------------------------------------------------------------------------- wings, engines, legs
    _wing(b, 1)
    _wing(b, -1)
    _leg(b, 2.6, 1.05, -0.5)
    _leg(b, 2.6, -1.05, -0.5)
    _leg(b, -3.5, 1.25, 0.5)
    _leg(b, -3.5, -1.25, 0.5)
    # ----------------------------------------------------------------------------------------------------- the dorsal: intake scoops, spine, masts, beacon
    for sy in (-0.72, 0.72):
        b.body.extrude_y([(-4.5, ROOF), (-2.4, ROOF), (-2.4, 2.90), (-2.8, 3.08), (-4.2, 3.08), (-4.5, 2.90)], sy - 0.33, sy + 0.33, CRATE_GREY)
        b.soft.extrude_y([(-2.41, 2.78), (-2.41, 2.90), (-2.79, 3.075), (-2.79, 3.0)], sy - 0.27, sy + 0.27, DGLASS)
        for k in range(5):
            b.soft.box((-4.1 + k * 0.28, sy - 0.27, 3.08), (-4.06 + k * 0.28, sy + 0.27, 3.12), STRUCT)
    b.body.box((-2.2, -0.12, ROOF), (1.4, 0.12, 2.86), CRATE_GREY)
    b.soft.cyl((-1.0, 0.0, 2.86), (-1.0, 0.0, 3.10), 0.025, TRIM, seg=6)
    b.soft.cyl((0.4, 0.0, 2.86), (0.4, 0.0, 3.05), 0.02, TRIM, seg=6)
    b.emit.lamp_cbox((-1.0, 0.0, 3.115), (0.08, 0.08, 0.05), "red", LAMP)
    b.soft.box((-0.2, -0.22, 2.86), (0.4, 0.22, 2.90), STRUCT)
    # the fuel and umbilical ports on the shoulder (the bay's hoses plug in here)
    for sy in (-1.0, 1.0):
        b.soft.cyl((-1.9, sy * 1.12, 2.72), (-1.9, sy * 1.12, 2.78), 0.09, TRIM, seg=10)
        b.emit.lamp_cyl((-1.9, sy * 1.12, 2.78), (-1.9, sy * 1.12, 2.785), 0.06, "amber", LAMP_DIM, seg=10)
    # ----------------------------------------------------------------------------------------------------- the side: sliding door, windows, hazard bands, number
    def sb(fb, sy: int, x0: float, x1: float, z0: float, z1: float, ya: float, yb: float, mat: str) -> None:
        """A box on the side `sy`: from the distance ya to yb out from the craft's axis."""
        lo, hi = sorted((sy * ya, sy * yb))
        fb.box((x0, lo, z0), (x1, hi, z1), mat)

    for sy in (-1, 1):
        sb(b.body, sy, -4.3, -2.7, 0.98, 2.3, 1.44, 1.475, TRIM)                                                      # the side hatch (closed): a frame ...
        sb(b.soft, sy, -4.24, -2.76, 1.04, 2.24, 1.47, 1.49, CRATE_GREY)                                              # ... a lighter door in it ...
        sb(b.soft, sy, -2.95, -2.85, 1.55, 1.75, 1.49, 1.52, TRIM)                                                    # ... and its handle
        for k in range(3):                                                                                            # small windows above the wing, along the troop bay
            sb(b.soft, sy, -2.0 + k * 0.45, -1.7 + k * 0.45, 1.85, 2.15, 1.44, 1.47, DGLASS)
        for xx in (-4.7, -2.45, -0.7, 0.9):                                                                           # panel seams
            sb(b.soft, sy, xx - 0.01, xx + 0.01, 0.95, 2.3, 1.44, 1.46, STRUCT)
        b.emit.label((-0.2, sy * 1.452, 0.82), 3.4, 0.12, (0, sy, 0), "hazard_h", up=(0, 0, 1))                      # a hazard band over the wing root
        b.emit.label_fit((2.3, sy * 1.452, 1.8), 1.0, number, (0, sy, 0), up=(0, 0, 1))                               # the hull number
        b.emit.label_fit((0.6, sy * 1.452, 2.35), 0.5, "pict_shuttle", (0, sy, 0), up=(0, 0, 1))
    # ----------------------------------------------------------------------------------------------------- the breaching collar: a ring round a forward hatch on the `collar` side
    yc = collar * (1.45 + 0.02)
    with b.at(frame(-3.5, yc, 1.55, 0.0, 0.0, -90.0 if collar > 0 else 90.0)):                                       # the ring's own z is the craft's +-y: it stands off the skin
        b.body.arc_sweep([(-0.12, 0.0), (0.12, 0.0), (0.12, 0.22), (-0.12, 0.22)], 0.0, 0.0, 0.92, 0.0, 360.0, TRIM, seg=32, z0=0.0, loop=True)
        b.soft.arc_sweep([(-0.03, 0.22), (0.03, 0.22), (0.03, 0.26), (-0.03, 0.26)], 0.0, 0.0, 0.92, 0.0, 360.0, CRATE_ORANGE, seg=32, z0=0.0, loop=True)
        for k in range(8):                                                                                           # the clamp lugs
            a = math.radians(k * 45.0 + 22.5)
            cx, cy = 0.92 * math.cos(a), 0.92 * math.sin(a)
            b.body.box((cx - 0.1, cy - 0.1, 0.0), (cx + 0.1, cy + 0.1, 0.34), STRUCT)
            b.emit.lamp_box((cx - 0.03, cy - 0.03, 0.34), (cx + 0.03, cy + 0.03, 0.36), "amber", LAMP_DIM)
