"""ASN Aquila interior kit: furniture and equipment of the security and flight decks (NAVE-2) — the shuttle bay's launch portals, hoses and ground equipment, the
barracks' bays and footlockers, the firing range's booths, targets and baffles, the kit room's armour bays. Fourth library, after ship_furniture.py, ship_furniture2.py
and ship_furniture3.py; same conventions: every function builds one piece in ITS OWN frame (origin on the floor, +x the piece's front, +y its left, z up) into a `SParts`
(body = bevelled hard-surface, fine = small details, soft = cloth, emit = lamps and labels); rooms place it with ship_rooms.place()."""
from __future__ import annotations

import math

from mathutils import Vector

from ship_lib import (COMPOSITE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, FABRIC_GREY, FABRIC_SAND, LAMP, LAMP_DIM, PAINT_RED, RUBBER,
                      STEEL, STRUCT, TRIM, SParts)


# ---------------------------------------------------------------------------------------------------------------------- the shuttle bay
def launch_portal(b: SParts, w: float = 5.6, h: float = 3.2, tag: str = "eq_launch", with_leaves: bool = True) -> None:
    """A launch tube's door in a wall, seen from the room (x = out of the wall, y across, centred on y = 0): a heavy brushed frame, two sliding leaves of grey plate with
    an orange hazard band at the top and a dark seam between them, a guide rail along the floor, a pair of beacons and the tube's tag over the header."""
    t = 0.22
    for sy in (-1, 1):                                                                                  # the jambs and their wear plates
        y0 = sy * (w / 2 + 0.14)
        b.body.box((0.0, y0 - 0.14, 0.0), (t, y0 + 0.14, h + 0.26), TRIM)
        b.body.box((t - 0.02, sy * (w / 2) - (0.0 if sy > 0 else 0.12), 0.0), (t + 0.04, sy * (w / 2) + (0.12 if sy > 0 else 0.0), h), STRUCT)
    b.body.box((0.0, -w / 2 - 0.28, h), (t, w / 2 + 0.28, h + 0.26), TRIM)                              # the header
    b.body.box((t - 0.02, -w / 2, h - 0.14), (t + 0.04, w / 2, h), STRUCT)
    for sy in ((-1, 1) if with_leaves else ()):                                                           # the two leaves, a dark seam between them
        lo, hi = sorted((sy * 0.02, sy * w / 2))
        b.body.box((0.02, lo, 0.05), (0.12, hi, h - 0.14), CRATE_GREY)
        for k in range(1, 4):                                                                           # horizontal stiffeners
            z = k * (h - 0.2) / 4
            b.fine.box((0.115, lo + 0.04, z), (0.135, hi - 0.04, z + 0.07), STRUCT)
        for k in range(1, 5):                                                                           # the rivet seams of the leaf, vertical
            ya = lo + k * (hi - lo) / 5
            b.fine.box((0.115, ya - 0.006, 0.12), (0.125, ya + 0.006, h - 0.2), TRIM)
        b.emit.label((0.136, (lo + hi) / 2, h - 0.34), (hi - lo) - 0.2, 0.2, (1, 0, 0), "hazard_h")
        b.fine.box((0.115, sy * 0.02 - (0.03 if sy > 0 else 0.0), 0.05), (0.14, sy * 0.02 + (0.0 if sy > 0 else 0.03), h - 0.14), STRUCT)   # the lip at the seam
    b.body.box((-0.02, -w / 2 - 0.2, 0.0), (0.6, w / 2 + 0.2, 0.03), STRUCT)                           # the floor rail's plate
    b.fine.box((0.1, -w / 2, 0.03), (0.24, w / 2, 0.05), TRIM)
    for sy in (-1, 1):                                                                                  # beacons on the header's ends
        yb = sy * (w / 2 + 0.14)
        b.fine.box((0.05, yb - 0.1, h + 0.26), (0.19, yb + 0.1, h + 0.30), STRUCT)
        b.emit.lamp_cyl((0.12, yb, h + 0.30), (0.12, yb, h + 0.40), 0.07, "amber", LAMP, seg=10)
    b.emit.lamp_box((t, -w / 2 + 0.2, h - 0.25), (t + 0.004, w / 2 - 0.2, h - 0.22), "red", LAMP_DIM)    # the 'tube live' bar
    b.emit.label_fit((t + 0.002, 0.0, h + 0.13), min(2.4, w - 0.6), tag, (1, 0, 0))


def umbilical(b: SParts, p0, p1, r: float = 0.045, sag: float = 0.55, mat: str = RUBBER) -> None:
    """A hose from a ceiling drop p0 down to a craft's port p1: a cubic curve that leaves p0 downwards and reaches p1 from above, with collars at both ends."""
    a, c = Vector(p0), Vector(p1)
    c1 = a + Vector((0.0, 0.0, -1.2))
    c2 = c + Vector((0.0, 0.0, 0.9 + sag))
    pts = []
    for k in range(11):
        t = k / 10.0
        u = 1.0 - t
        pts.append(u ** 3 * a + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t ** 3 * c)
    b.fine.tube([tuple(p) for p in pts], r, mat, seg=8)
    b.fine.cyl(a + Vector((0, 0, 0.12)), a + Vector((0, 0, -0.18)), r * 1.6, TRIM, seg=10)
    b.fine.cyl(c + Vector((0, 0, 0.16)), c + Vector((0, 0, -0.02)), r * 1.5, TRIM, seg=10)
    b.emit.lamp_cyl(a + Vector((0, 0, -0.18)), a + Vector((0, 0, -0.185)), r * 1.2, "amber", LAMP_DIM, seg=10)


def gpu_cart(b: SParts) -> None:
    """A ground power unit on wheels facing +x: an olive housing with louvres, a cable reel with an orange cable, a tow handle, a gauge and a status lamp."""
    b.body.box((-0.55, -0.4, 0.22), (0.45, 0.4, 1.0), CRATE_OLIVE)
    b.body.box((-0.6, -0.42, 0.14), (0.5, 0.42, 0.24), STRUCT)
    b.body.box((-0.5, -0.36, 1.0), (0.4, 0.36, 1.04), TRIM)
    for k in range(6):
        b.fine.box((0.45, -0.3, 0.55 + k * 0.07), (0.465, 0.0, 0.58 + k * 0.07), STRUCT)
    b.fine.box((0.45, 0.06, 0.52), (0.47, 0.32, 0.86), COMPOSITE)
    b.fine.cyl((0.47, 0.19, 0.74), (0.475, 0.19, 0.74), 0.07, DGLASS, seg=12)
    b.emit.lamp_box((0.46, 0.1, 0.60), (0.47, 0.14, 0.64), "green", LAMP)
    b.emit.lamp_box((0.46, 0.2, 0.60), (0.47, 0.24, 0.64), "amber", LAMP_DIM)
    b.emit.label_fit((0.452, -0.15, 0.9), 0.34, "eq_gpu", (1, 0, 0))
    for sy in (-0.44, 0.44):                                                                       # the cable reel on the side, a wound orange cable
        b.body.cyl((0.0, sy, 0.64), (0.0, sy * 1.12, 0.64), 0.3, STRUCT, seg=16)
        b.body.cyl((0.0, sy * 1.0, 0.64), (0.0, sy * 1.08, 0.64), 0.27, CRATE_ORANGE, seg=16)
    for sx in (-0.4, 0.3):                                                                         # the wheels
        for sy in (-0.42, 0.42):
            b.body.cyl((sx, sy * 0.95, 0.14), (sx, sy * 1.12, 0.14), 0.14, RUBBER, seg=12)
    b.fine.cyl((0.5, 0.0, 0.3), (0.95, 0.0, 0.72), 0.02, TRIM, seg=6)                             # the tow handle
    b.fine.cyl((0.95, -0.25, 0.72), (0.95, 0.25, 0.72), 0.02, TRIM, seg=6)


def tool_chest(b: SParts, w: float = 0.8, d: float = 0.5, h: float = 1.0) -> None:
    """A rolling tool cabinet facing +x: a red body, five drawers with handles, a steel top with a lip, casters."""
    b.body.box((-d / 2, -w / 2, 0.1), (d / 2, w / 2, h), PAINT_RED)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.01, h), (d / 2 + 0.02, w / 2 + 0.01, h + 0.03), STEEL)
    b.body.box((-d / 2, -w / 2, 0.06), (d / 2, w / 2, 0.1), STRUCT)
    for k in range(5):
        z0 = 0.14 + k * (h - 0.2) / 5
        b.fine.box((d / 2, -w / 2 + 0.02, z0), (d / 2 + 0.012, w / 2 - 0.02, z0 + (h - 0.2) / 5 - 0.02), STRUCT)
        b.fine.box((d / 2 + 0.012, -w / 2 + 0.1, z0 + (h - 0.2) / 10 - 0.012), (d / 2 + 0.03, w / 2 - 0.1, z0 + (h - 0.2) / 10 + 0.012), TRIM)
    for sx in (-d / 2 + 0.06, d / 2 - 0.06):
        for sy in (-w / 2 + 0.06, w / 2 - 0.06):
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.06), 0.035, RUBBER, seg=8)


def foam_cart(b: SParts) -> None:
    """A wheeled foam fire-fighting cart facing +x: a red cylinder tank on a frame with a hose and nozzle on a hook, a pressure gauge."""
    b.body.cyl((0.0, 0.0, 0.3), (0.0, 0.0, 1.1), 0.28, PAINT_RED, seg=18)
    b.body.sphere((0.0, 0.0, 1.1), 0.28, PAINT_RED, seg=18, rings=6, squash=(1, 1, 0.55))
    b.fine.cyl((0.0, 0.0, 0.7), (0.0, 0.0, 0.76), 0.285, TRIM, seg=18)
    b.body.box((-0.34, -0.3, 0.12), (0.34, 0.3, 0.3), STRUCT)
    for sy in (-0.34, 0.34):
        b.body.cyl((-0.1, sy, 0.14), (-0.1, sy * 1.1, 0.14), 0.14, RUBBER, seg=12)
    b.fine.cyl((0.28, 0.0, 0.9), (0.28, 0.0, 0.96), 0.05, DGLASS, seg=10)
    b.fine.cyl((-0.3, 0.0, 0.3), (-0.55, 0.0, 0.95), 0.02, TRIM, seg=6)                           # the handle
    b.fine.tube([(0.25, 0.0, 0.6), (0.33, 0.12, 0.55), (0.36, 0.22, 0.5), (0.3, 0.3, 0.7), (0.15, 0.3, 0.85)], 0.025, RUBBER, seg=6)
    b.fine.box((0.1, 0.27, 0.82), (0.3, 0.34, 0.9), TRIM)
    b.emit.label((0.286, 0.0, 0.55), 0.3, 0.075, (1, 0, 0), "hazard")


def tow_tug(b: SParts) -> None:
    """A small tow tractor facing +x: an olive chassis with an orange bonnet, a cab frame with a roof light, a seat, a steering column, a hitch bar, four fat wheels."""
    b.body.box((-0.9, -0.55, 0.22), (0.8, 0.55, 0.62), CRATE_OLIVE)
    b.body.box((0.1, -0.5, 0.62), (0.85, 0.5, 0.98), CRATE_ORANGE)                                  # the bonnet
    b.fine.box((0.85, -0.35, 0.7), (0.87, 0.35, 0.9), STRUCT)
    b.emit.lamp_box((0.86, -0.42, 0.78), (0.875, -0.3, 0.84), "white_warm", LAMP)
    b.emit.lamp_box((0.86, 0.3, 0.78), (0.875, 0.42, 0.84), "white_warm", LAMP)
    for sx in (-0.85, -0.1):                                                                        # the cab frame
        for sy in (-0.5, 0.5):
            b.body.box((sx - 0.025, sy - 0.025, 0.62), (sx + 0.025, sy + 0.025, 1.7), TRIM)
    b.body.box((-0.9, -0.55, 1.7), (-0.05, 0.55, 1.74), TRIM)
    b.emit.lamp_cyl((-0.5, 0.0, 1.74), (-0.5, 0.0, 1.84), 0.08, "amber", LAMP, seg=10)
    b.soft.box((-0.75, -0.28, 0.62), (-0.35, 0.28, 0.72), FABRIC_GREY)                              # the seat
    b.soft.box((-0.78, -0.28, 0.72), (-0.72, 0.28, 1.15), FABRIC_GREY)
    b.fine.cyl((-0.1, 0.0, 0.62), (0.0, 0.0, 1.05), 0.02, TRIM, seg=6)                              # the steering column and wheel
    b.fine.box((-0.12, -0.17, 1.03), (-0.02, 0.17, 1.06), RUBBER)
    for sx in (-0.65, 0.55):
        for sy in (-0.55, 0.55):
            b.body.cyl((sx, sy * 0.92, 0.24), (sx, sy * 1.12, 0.24), 0.24, RUBBER, seg=14)
            b.fine.cyl((sx, sy * 1.11, 0.24), (sx, sy * 1.14, 0.24), 0.13, TRIM, seg=10)
    b.body.box((-1.5, -0.08, 0.3), (-0.9, 0.08, 0.36), STRUCT)                                      # the hitch
    b.fine.cyl((-1.45, 0.0, 0.3), (-1.45, 0.0, 0.42), 0.04, TRIM, seg=8)
    b.emit.label((0.0, -0.556, 0.5), 0.5, 0.125, (0, -1, 0), "hazard_h")


def fuel_cart(b: SParts) -> None:
    """A fuel bowser facing +x: an orange horizontal tank with domed ends on a chassis, a pump housing with a gauge, a hose reel with a hose and nozzle, four wheels, its tag."""
    b.body.cyl((-0.85, 0.0, 0.72), (0.85, 0.0, 0.72), 0.40, CRATE_ORANGE, seg=18)
    for sx in (-0.85, 0.85):
        b.body.sphere((sx, 0.0, 0.72), 0.40, CRATE_ORANGE, seg=18, rings=6, squash=(0.45, 1.0, 1.0))
    for sx in (-0.4, 0.4):
        b.fine.cyl((sx, 0.0, 0.72), (sx + 0.04, 0.0, 0.72), 0.405, TRIM, seg=18)
    b.body.box((-1.0, -0.42, 0.2), (1.0, 0.42, 0.3), STRUCT)
    b.body.box((-0.7, -0.38, 0.3), (-0.5, 0.38, 0.5), STRUCT)
    b.body.box((0.5, -0.38, 0.3), (0.7, 0.38, 0.5), STRUCT)
    b.body.box((0.35, 0.18, 0.2), (0.85, 0.42, 0.62), COMPOSITE)                                    # the pump housing with a gauge and a lamp
    b.fine.cyl((0.85, 0.3, 0.46), (0.87, 0.3, 0.46), 0.055, DGLASS, seg=12)
    b.emit.lamp_box((0.855, 0.2, 0.30), (0.865, 0.24, 0.34), "green", LAMP)
    b.body.cyl((0.0, -0.4, 0.95), (0.0, -0.5, 0.95), 0.2, STRUCT, seg=14)                           # the hose reel on the other flank
    b.body.cyl((0.0, -0.46, 0.95), (0.0, -0.52, 0.95), 0.17, RUBBER, seg=14)
    b.fine.tube([(0.1, -0.52, 0.78), (0.3, -0.58, 0.5), (0.55, -0.55, 0.35), (0.75, -0.5, 0.45)], 0.03, RUBBER, seg=6)
    b.fine.box((0.72, -0.53, 0.4), (0.88, -0.47, 0.5), TRIM)
    for sx in (-0.65, 0.65):
        for sy in (-0.42, 0.42):
            b.body.cyl((sx, sy * 0.95, 0.17), (sx, sy * 1.12, 0.17), 0.17, RUBBER, seg=12)
    b.fine.cyl((-1.0, 0.0, 0.32), (-1.5, 0.0, 0.75), 0.025, TRIM, seg=6)                           # the tow bar
    b.emit.label_fit((0.0, 0.405, 0.72), 0.7, "eq_fuel", (0, 1, 0), up=(0, 0, 1))


def pod_trolley(b: SParts, pods: int = 2) -> None:
    """An ordnance trolley facing +x: a steel deck on four wheels carrying rocket pods (grey tubes with orange noses) in cradles, lashing straps, a tow bar and a hazard tag."""
    b.body.box((-1.05, -0.45, 0.20), (1.05, 0.45, 0.27), STRUCT)
    for sy in (-0.5, 0.5):
        b.body.box((-1.0, sy * 0.9 - 0.025, 0.12), (1.0, sy * 0.9 + 0.025, 0.2), TRIM)
    for k in range(pods):
        sy = (k - (pods - 1) / 2) * 0.34
        b.body.cyl((-0.95, sy, 0.56), (0.62, sy, 0.56), 0.14, CRATE_GREY, seg=12)
        b.body.cyl((0.62, sy, 0.56), (0.98, sy, 0.56), 0.14, CRATE_ORANGE, seg=12, r2=0.06)
        for a in range(3):
            ang = math.radians(a * 120.0)
            b.soft.cyl((-0.97, sy + 0.07 * math.sin(ang), 0.56 + 0.07 * math.cos(ang)), (-0.94, sy + 0.07 * math.sin(ang), 0.56 + 0.07 * math.cos(ang)), 0.035, STRUCT, seg=8)
    for sx in (-0.55, 0.35):                                                                       # the cradles
        b.body.box((sx - 0.05, -0.38, 0.27), (sx + 0.05, 0.38, 0.4), STRUCT)
        b.soft.box((sx - 0.025, -0.4, 0.62), (sx + 0.025, 0.4, 0.7), FABRIC_SAND)                  # the lashing strap over the pods
    for sx in (-0.7, 0.7):
        for sy in (-0.45, 0.45):
            b.body.cyl((sx, sy * 0.96, 0.12), (sx, sy * 1.1, 0.12), 0.12, RUBBER, seg=10)
    b.soft.cyl((1.05, 0.0, 0.26), (1.7, 0.0, 0.5), 0.022, TRIM, seg=6)
    b.emit.label((0.0, 0.452, 0.235), 0.4, 0.05, (0, 1, 0), "hazard_h")


def floor_hatch(b: SParts, w: float = 0.9, d: float = 0.6, cell: str = "amber") -> None:
    """A service hatch let into the floor (hose and cable pit): a brushed frame, a lid with a lit edge and a recessed handle; lies flush (2 cm)."""
    b.body.box((-w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.012), TRIM)
    b.soft.box((-w / 2 + 0.05, -d / 2 + 0.05, 0.012), (w / 2 - 0.05, d / 2 - 0.05, 0.02), STRUCT)
    b.emit.lamp_box((-w / 2 + 0.06, -d / 2 + 0.06, 0.02), (w / 2 - 0.06, -d / 2 + 0.075, 0.023), cell, LAMP_DIM)
    b.soft.box((-0.08, -0.03, 0.02), (0.08, 0.03, 0.026), TRIM)


def chock(b: SParts) -> None:
    """A wheel chock lying along +x (a wedge of orange rubber, 25 cm wide)."""
    b.soft.extrude_y([(0.0, 0.0), (0.3, 0.0), (0.0, 0.14)], -0.125, 0.125, CRATE_ORANGE)


def duffel(b: SParts, l: float = 0.8, r: float = 0.2, mat: str = FABRIC_SAND) -> None:
    """A kit bag lying along y: a fat cylinder with a strap and a handle."""
    b.soft.cyl((0.0, -l / 2, r), (0.0, l / 2, r), r, mat, seg=12)
    b.soft.sphere((0.0, -l / 2, r), r, mat, seg=10, rings=6, squash=(1.0, 0.45, 1.0))
    b.soft.sphere((0.0, l / 2, r), r, mat, seg=10, rings=6, squash=(1.0, 0.45, 1.0))
    b.soft.cyl((0.0, -0.05, r), (0.0, 0.05, r), r + 0.01, RUBBER, seg=12)
    b.soft.box((-0.02, -0.1, 2 * r), (0.02, 0.1, 2 * r + 0.04), RUBBER)
