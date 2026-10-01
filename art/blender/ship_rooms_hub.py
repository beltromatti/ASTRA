"""ASN Aquila interior kit: the hub rooms and the vertical pieces — the Mess Concourse (Deck 4's hero space: the Mess Hall portal, the lift
bank, the directory, the planter island), the Berthing Lobby, the stair tower (two switchback flights and a ladder trunk in an 8 x 8 m
shaft, one deck tall) and the standalone ladder trunk.
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_furniture2 as G
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, luminaire_strips, place, wall_finish, wall_label, wall_matrix)
from ship_rooms_social import _ring


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def on_wall(b: SParts, wall: str, L: float, D: float, fn, *args, **kw):
    """Run a wall-furniture function (ship_walls: wall-local frame, negative t into the room) on the finished face of a room wall."""
    with b.at(wall_matrix(wall, L, D) @ T(0.0, -WF, 0.0)):
        return fn(*args, **kw)


def handrail(b: SParts, p0, p1, h: float = 0.95, post_every: float = 1.1, mid: bool = False) -> None:
    """A tubular handrail from p0 to p1 (both on the walking surface line), posts to the floor line, an optional mid rail."""
    from mathutils import Vector
    a, c = Vector(p0), Vector(p1)
    up = Vector((0, 0, h))
    b.fine.cyl(a + up, c + up, 0.021, TRIM, seg=8)
    if mid:
        b.fine.cyl(a + up * 0.5, c + up * 0.5, 0.012, TRIM, seg=6)
    n = max(1, int((c - a).length / post_every))
    for k in range(n + 1):
        p = a + (c - a) * (k / n)
        b.fine.cyl(p, p + up, 0.014, TRIM, seg=6)


# ------------------------------------------------------------------------------------------------------------ hub pieces
def lift_door(b: SParts) -> None:
    """One lift door on a wall facing +x (centred on y = 0): a brushed frame, two leaves with a seam, a floor display, a call panel."""
    b.body.box((0.0, -0.98, 0.0), (0.09, -0.86, 2.62), TRIM)
    b.body.box((0.0, 0.86, 0.0), (0.09, 0.98, 2.62), TRIM)
    b.body.box((0.0, -0.98, 2.5), (0.09, 0.98, 2.62), TRIM)
    for sy in (-0.85, 0.01):
        b.body.box((0.02, sy, 0.02), (0.06, sy + 0.84, 2.5), COMPOSITE)
        b.fine.box((0.06, sy + 0.05, 0.10), (0.064, sy + 0.79, 2.42), STRUCT)
    b.fine.box((0.06, -0.01, 0.02), (0.07, 0.01, 2.5), TRIM)
    b.body.box((0.0, -0.5, 2.66), (0.09, 0.5, 2.9), STRUCT)                                                # the display over the door
    b.fine.box((0.09, -0.46, 2.69), (0.095, 0.46, 2.87), DGLASS)
    for k, cell in enumerate(("amber", "amber", "amber")):
        b.emit.lamp_box((0.096, -0.28 + k * 0.28, 2.74), (0.10, -0.2 + k * 0.28, 2.82), cell, LAMP_DIM)
    b.emit.lamp_box((0.096, 0.38, 2.74), (0.10, 0.44, 2.82), "cyan", LAMP)
    b.body.box((0.0, 1.06, 0.95), (0.05, 1.24, 1.5), TRIM)                                                 # the call panel
    b.emit.lamp_box((0.05, 1.11, 1.30), (0.056, 1.19, 1.36), "cyan", LAMP)
    b.emit.lamp_box((0.05, 1.11, 1.08), (0.056, 1.19, 1.14), "amber", LAMP)


def portal(b: SParts, opening: float = 3.4, h_open: float = 3.3, height: float = 3.7, plate: str = "room_mess", plate_w: float = 1.8) -> None:
    """A tall doorway surround on a wall facing +x, centred on y = 0: pilasters with light lines, a header carrying the name plate."""
    hw = opening / 2
    for s in (-1, 1):
        y0, y1 = (hw, hw + 0.6) if s > 0 else (-hw - 0.6, -hw)
        b.body.box((0.0, y0, 0.0), (0.16, y1, height), COMPOSITE)
        b.body.box((0.0, y0 if s > 0 else y1 - 0.05, 0.0), (0.18, (y0 + 0.05) if s > 0 else y1, height), TRIM)
        b.body.box((0.0, (y1 - 0.05) if s > 0 else y0, 0.0), (0.18, y1 if s > 0 else (y0 + 0.05), height), TRIM)
        yl = hw + 0.015 if s > 0 else -hw - 0.045
        b.emit.lamp_box((0.0, yl, 0.25), (0.17, yl + 0.03, height - 0.5), "white_warm", LAMP)
    b.body.box((0.0, -hw - 0.6, h_open), (0.16, hw + 0.6, height), COMPOSITE)
    b.body.box((0.0, -hw - 0.6, h_open), (0.18, hw + 0.6, h_open + 0.05), TRIM)
    b.body.box((0.0, -hw - 0.6, height - 0.05), (0.18, hw + 0.6, height), TRIM)
    b.emit.label((0.165, 0.0, (h_open + height) / 2), plate_w, (height - h_open) * 0.62, (1, 0, 0), plate)
    b.fine.box((0.0, -hw, 0.0), (0.4, hw, 0.012), TRIM)                                                     # the threshold plate


def stele(b: SParts, w: float = 1.3, d: float = 0.5, h: float = 2.4, plate: str = "room_directory") -> None:
    """A free-standing information stele: a plinth, a dark body with a screen on each of its two faces, a lit cap, a plate above the screen."""
    b.body.box((-d / 2 - 0.08, -w / 2 - 0.08, 0.0), (d / 2 + 0.08, w / 2 + 0.08, 0.14), STRUCT)
    b.body.box((-d / 2, -w / 2, 0.14), (d / 2, w / 2, h), COMPOSITE)
    for s in (-1, 1):
        x = s * d / 2
        b.fine.box((x if s > 0 else x - 0.012, -w / 2 + 0.05, 0.9), (x + 0.012 if s > 0 else x, w / 2 - 0.05, 2.0), TRIM)
        b.fine.box((x + (0.012 if s > 0 else -0.018), -w / 2 + 0.08, 0.95), (x + (0.018 if s > 0 else -0.012), w / 2 - 0.08, 1.95), DGLASS)
        b.emit.label((x + s * 0.0185, 0.0, 1.45), w - 0.16, 0.98, (s, 0, 0), "scr_dir" if s > 0 else "scr_map")
        b.emit.label((x + s * 0.001, 0.0, 2.22), w - 0.2, (w - 0.2) / 4.2, (s, 0, 0), plate)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, h), (d / 2 + 0.02, w / 2 + 0.02, h + 0.06), TRIM)
    b.emit.lamp_box((-d / 2 + 0.05, -w / 2 + 0.08, h + 0.06), (d / 2 - 0.05, w / 2 - 0.08, h + 0.07), "white_cool", LAMP)


def extinguisher_free(b: SParts) -> None:
    """A fire extinguisher hung on a wall facing +x (origin on the wall's finished face at the floor line): use on_wall for wall-local placement."""
    W.extinguisher(b.body, 0.0, 0.9)


# ------------------------------------------------------------------------------------------------------------------ concourse
def concourse(name: str = "SM_SHIP_Concourse"):
    """17.7 x 36 x 3.7. x = 0 is the Mess Hall's forward face (aft wall), x = L the Spine's opening (forward wall); y 0 (port) .. 36 (starboard):
    the near and far walls are the walls of the side passages (their gates at x 3.7 and 11.7)."""
    spec, L, D, H = _dims("concourse")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="warm_dim", cove="white_warm",
               rib_mat=TRIM, skirt=STRUCT)
    doors = [{"wall": "left", "x": 18.0, "w": 3.4, "h": 3.3}, {"wall": "right", "x": 18.0, "w": 4.0, "h": 3.4}]
    for gx in (3.7, 11.7):
        doors.append({"wall": "near", "x": gx, "w": 3.2, "h": 3.0})
        doors.append({"wall": "far", "x": gx, "w": 3.2, "h": 3.0})
    build_shell(b, spec, st, doors=doors, bare=("near", "far"), far_door=True)
    xa, xf = WS + WF, L - WS - WF                       # the finished faces of the aft and forward walls
    # the Mess Hall's portal on the aft wall, the lift bank beside it
    place(b, xa, 18.0, 0, portal, 3.4, 3.3, 3.7, "room_mess", 1.9)
    for yc in (25.6, 28.4):
        place(b, xa, yc, 0, lift_door)
    b.body.box((xa, 24.5, 3.1), (xa + 0.12, 29.5, 3.7), COMPOSITE)
    b.body.box((xa, 24.5, 3.1), (xa + 0.14, 29.5, 3.15), TRIM)
    b.emit.label((xa + 0.125, 26.2, 3.4), 1.5, 0.3, (1, 0, 0), "room_lift")
    b.emit.label((xa + 0.125, 28.8, 3.4), 0.42, 0.42, (1, 0, 0), "pict_lift")
    lamp_strip(b.emit, (0.6, 24.5, 0.006), (3.4, 24.5, 0.006), 0.05, 0.004, "amber_dim", LAMP_DIM)
    lamp_strip(b.emit, (0.6, 29.5, 0.006), (3.4, 29.5, 0.006), 0.05, 0.004, "amber_dim", LAMP_DIM)
    lamp_strip(b.emit, (3.4, 24.5, 0.006), (3.4, 29.5, 0.006), 0.05, 0.004, "amber_dim", LAMP_DIM)
    # the directory, the planter island with its ring light, benches around it
    place(b, 2.7, 11.5, 0, stele, 1.3, 0.5, 2.4, "room_directory")
    place(b, 9.0, 18.0, 0, F.planter, 4.4, 2.2, 0.55, 5, 3, True)
    place(b, 6.75, 18.0, 0, F.bench, 3.6, 0.5, 0.46, FABRIC_GREY)
    place(b, 11.25, 18.0, 0, F.bench, 3.6, 0.5, 0.46, FABRIC_GREY)
    _ring(b.emit, 9.0, 18.0, H - 0.075, 3.3, "white_warm", 64, 0.07, LAMP)
    _ring(b.emit, 9.0, 18.0, H - 0.075, 2.5, "warm_dim", 48, 0.04, LAMP_DIM)
    b.body.cyl((9.0, 18.0, H - 0.05), (9.0, 18.0, H - 0.075), 3.4, TRIM, seg=64)
    _ring(b.emit, 9.0, 18.0, 0.004, 3.7, "guide_warm", 64, 0.04, LAMP_DIM)
    # floor guide lines: along the gates, to the Mess portal and the Spine
    for x in (3.7, 11.7):
        for (y0, y1) in ((0.6, 9.5), (26.5, D - 0.6)) if x == 3.7 else ((0.6, 14.4), (21.6, D - 0.6)):
            lamp_strip(b.emit, (x, y0, 0.006), (x, y1, 0.006), 0.04, 0.004, "guide", LAMP_DIM)
    lamp_strip(b.emit, (0.5, 18.0, 0.006), (5.0, 18.0, 0.006), 0.04, 0.004, "guide", LAMP_DIM)
    lamp_strip(b.emit, (13.0, 18.0, 0.006), (L - 0.4, 18.0, 0.006), 0.04, 0.004, "guide", LAMP_DIM)
    # the side walls between the gates: benches with screens above, plants at the corners
    for (y, yaw) in ((0.7, 90), (D - 0.7, -90)):
        place(b, 7.7, y, yaw, F.bench, 3.8, 0.5, 0.46, FABRIC_NAVY)
        place(b, 7.7, 0.08 if y < 1 else D - 0.08, yaw, F.wall_screen, 2.6, 1.4, "scr_map" if y < 1 else "scr_news", z=1.75)
    for (x, y) in ((1.2, 1.4), (1.2, D - 1.4), (L - 1.2, 1.4), (L - 1.2, D - 1.4)):
        place(b, x, y, 0, F.planter, 1.2, 0.7, 0.5, 3, int(x * 3 + y), True)
    # the forward wall around the Spine's opening: section plate and pictograms, screens
    place(b, xf, 11.6, 180, F.wall_screen, 2.4, 1.3, "scr_sched", z=1.8)
    place(b, xf, 24.4, 180, F.wall_screen, 2.4, 1.3, "scr_lab", z=1.8)
    b.emit.label_fit((xf - 0.002, 14.6, 2.9), 0.9, "sec_4B", (-1, 0, 0))
    b.emit.label_fit((xf - 0.002, 21.4, 2.9), 0.7, "pict_obs", (-1, 0, 0))
    b.emit.label_fit((xf - 0.002, 14.6, 1.7), 0.5, "arrow_fwd", (-1, 0, 0))
    ceiling_panels(b, L, D, H, 3, 6, "white_warm", 1.6, 0.9, 0.5, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------ berthing lobby
def berth_lobby(name: str = "SM_SHIP_BerthLobby"):
    """14.6 x 36 x 3.6. x = 0 is the aft wall the Berthing's entrance (y 18, 3 m wide) opens through, 0.4 m ahead of the Berthing's face."""
    spec, L, D, H = _dims("berth_lobby")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent="warm_dim", cove="white_warm",
               rib_mat=TRIM, skirt=WOOD)
    doors = [{"wall": "left", "x": 18.0, "w": 3.2, "h": 3.1}]
    for gx in (5.3, 9.3):
        doors.append({"wall": "near", "x": gx, "w": 3.2, "h": 3.0})
        doors.append({"wall": "far", "x": gx, "w": 3.2, "h": 3.0})
    build_shell(b, spec, st, doors=doors, bare=("near", "far"))
    xa, xf = WS + WF, L - WS - WF
    place(b, xa, 18.0, 0, portal, 3.2, 3.1, 3.6, "room_berthing", 1.9)
    b.emit.label_fit((xa + 0.165, 18.0, 3.28), 0.9, "room_deck3", (1, 0, 0))
    # the reveal between the lobby and the Berthing (0.4 m): floor and jambs
    b.body.box((-0.4, 16.4, -0.3), (0.0, 19.6, 0.0), STRUCT)
    b.body.box((-0.4, 16.4, -0.012), (0.0, 19.6, 0.0), DECK)
    b.body.box((-0.4, 16.36, 0.0), (0.0, 16.4, 3.1), TRIM)
    b.body.box((-0.4, 19.6, 0.0), (0.0, 19.64, 3.1), TRIM)
    b.body.box((-0.4, 16.36, 3.1), (0.0, 19.64, 3.16), TRIM)
    # two sitting groups by the forward wall, a rug, low tables, plants
    for k, yc in enumerate((8.0, 28.0)):
        place(b, 10.6, yc, 0, G.rug, 4.4, 6.0, FABRIC_NAVY, FABRIC_SAND)
        place(b, 10.6, yc, 0, F.low_table, 0.7, 1.4, 0.4, WOOD)
        place(b, 12.6, yc, 180, F.sofa, 2.8, FABRIC_RUST if k == 0 else FABRIC_NAVY)
        place(b, 8.7, yc - 1.4, 0, F.armchair, FABRIC_SAND)
        place(b, 8.7, yc + 1.4, 0, F.armchair, FABRIC_SAND)
        place(b, 13.5, yc + (2.6 if k == 0 else -2.6), 0, F.potted_plant, 1.3, k + 1)
    place(b, xf, 18.0, 180, F.wall_screen, 3.6, 1.9, "scr_sched", z=1.95)
    b.emit.label_fit((xf - 0.002, 18.0, 3.05), 1.5, "eq_notice", (-1, 0, 0))
    place(b, xf - 0.3, 14.0, 180, F.locker_row, 4, 0.5, 1.95, 0.5, COMPOSITE)
    place(b, xf - 0.3, 25.6, 180, F.locker_row, 4, 0.5, 1.95, 0.5, COMPOSITE)
    # a drinks point by the near gate, benches on the side walls between the gates
    place(b, 2.6, 0.7, 90, G.coffee_machine, z=0.0)
    for (y, yaw) in ((0.7, 90), (D - 0.7, -90)):
        place(b, 7.3, y, yaw, F.bench, 2.6, 0.5, 0.46, FABRIC_NAVY)
    ceiling_panels(b, L, D, H, 3, 6, "white_warm", 1.5, 0.8, 0.5, LAMP)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------- stair tower
RISER, TREAD, NSTEP = 0.20, 0.27, 10
FLIGHT_X = (0.45, 2.05)                                         # flight A (up from the hall, along +y)
FLIGHT_X2 = (2.45, 4.05)                                        # flight B (back along -y to the deck above)
Y_HALL = 3.8                                                    # the hall's slab reaches y 3.8 (the well starts there)
Y_LAND = Y_HALL + NSTEP * TREAD                                 # 6.5: the half landing
HOLE = (5.0, 6.55, 6.0, 7.75)                                   # the ladder trunk's opening (x0, y0, x1, y1), against the far wall
SHAFT_H = 4.0


def _slab(b: SParts, x0: float, y0: float, x1: float, y1: float) -> None:
    b.body.box((x0, y0, -0.30), (x1, y1, -0.012), STRUCT)
    b.body.box((x0, y0, -0.012), (x1, y1, 0.0), DECK)


def _flight(b: SParts, xr: tuple[float, float], y_start: float, dirn: int, z_start: float, riser: float = RISER, tread: float = TREAD, nstep: int = NSTEP) -> None:
    """A flight of `nstep` steps (ten for the usual 4 m rise): treads with a nosing, risers, two stringers under the treads; y_start is the foot of the flight, dirn +1 goes
    towards +y."""
    x0, x1 = xr
    for k in range(1, nstep + 1):
        za, zb = z_start + riser * (k - 1), z_start + riser * k
        ya = y_start + dirn * (k - 1) * tread
        yb = y_start + dirn * k * tread
        lo, hi = min(ya, yb), max(ya, yb)
        b.body.box((x0, lo - (0.02 if dirn > 0 else 0.0), zb - 0.045), (x1, hi + (0.02 if dirn < 0 else 0.0), zb), STEEL)
        yr = ya
        b.fine.box((x0 + 0.03, yr - 0.011, za), (x1 - 0.03, yr + 0.011, zb - 0.04), STRUCT)
        b.fine.box((x0 + 0.05, min(ya, yb) + 0.02, zb - 0.052), (x1 - 0.05, max(ya, yb) - 0.02, zb - 0.045), RUBBER)                 # the anti-slip strip
    rise = riser * nstep
    ye = y_start + dirn * nstep * tread
    prof = [(y_start, z_start - 0.35), (ye, z_start + rise - 0.35), (ye, z_start + rise - 0.05), (y_start, z_start - 0.05)]
    for xs in ((x0 - 0.04, x0 + 0.02), (x1 - 0.02, x1 + 0.04)):
        b.body.extrude_x(prof, xs[0], xs[1], STRUCT)
    # a light line under the nosings on the side facing the well
    b.emit.lamp_box((x1 - 0.03 if dirn > 0 else x0 + 0.0, min(y_start, ye), z_start), (x1 if dirn > 0 else x0 + 0.03, min(y_start, ye) + 0.001, z_start + 0.001), "cool_dim", LAMP_DIM)


def stair_tower(name: str = "SM_SHIP_StairTower", top: bool = False, bottom: bool = False, deep: bool = False, cap: bool = False):
    """One deck of a stair tower: 8 x 8 m in plan, the shaft 4.0 m tall (this deck's floor to the floor above). The entry hall (the door at
    x 2 of the near wall) is on the deck's floor; two switchback flights rise from it through a well to the deck above (flight A along +y at
    x .45..2.05, the half landing at 2.0 m, flight B back along -y at x 2.45..4.05 arriving on the floor above at y 3.8); a ladder trunk stands
    in the other half (a hatch in the floor against the far wall, the ladder climbs through the hatch of the deck above). `top` closes the
    shaft with a roof, `bottom` closes the well with a floor. `deep`: the 5.3 m rise of Deck 3 to Deck 2 (twelve steps of 22 cm and a 24 cm tread a flight, the shaft 5.3 m);
    `cap`: the top of the column (Deck 2): the hall, the well the flights of the deck below arrive through and the roof, no flights of its own."""
    spec, L, D, H = _dims("stair_tower")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="covering", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="cool_dim", ribs=False,
               skirt=STRUCT, seams=False)
    riser, tread, nstep = (5.3 / 24.0, 0.24, 12) if deep else (RISER, TREAD, NSTEP)
    hz = 5.3 if deep else 3.9 if cap else SHAFT_H
    y_land = Y_HALL + nstep * tread
    doors = spec["doors"]
    for wname in ("left", "right", "far", "near"):
        wall_finish(b, wname, L, D, hz, st, doors, structure=(wname != "near"))
    # floors: the hall, the right half, the well's foot (bottom) and the ladder hatch
    _slab(b, 0.0, 0.0, L, Y_HALL)
    hx0, hy0, hx1, hy1 = HOLE
    if bottom:
        _slab(b, 4.05, Y_HALL, L, D)
        _slab(b, 0.0, Y_HALL, 4.05, D)
    else:
        _slab(b, 4.05, Y_HALL, L, hy0)
        _slab(b, 4.05, hy0, hx0, D)
        _slab(b, hx1, hy0, L, D)
        b.body.box((hx0 - 0.05, hy0 - 0.05, 0.0), (hx1 + 0.05, hy0, 0.10), TRIM)                              # the hatch coaming
        b.body.box((hx0 - 0.05, hy0, 0.0), (hx0, hy1, 0.10), TRIM)
        b.body.box((hx1, hy0, 0.0), (hx1 + 0.05, hy1, 0.10), TRIM)
        b.emit.lamp_box((hx0 - 0.05, hy0 - 0.052, 0.04), (hx1 + 0.05, hy0 - 0.049, 0.06), "amber", LAMP_DIM)
    # the flights and the half landing (the cap of a column has none: the flights of the deck below arrive through its well)
    z_top = riser * nstep
    if not cap:
        _flight(b, FLIGHT_X, Y_HALL, +1, 0.0, riser, tread, nstep)
        _flight(b, FLIGHT_X2, y_land, -1, z_top, riser, tread, nstep)
        b.body.box((WS, y_land, z_top - 0.35), (4.05, D - WS, z_top), STRUCT)
        b.body.box((WS, y_land, z_top - 0.012), (4.05, D - WS, z_top), DECK)
        b.fine.box((WS, y_land, z_top - 0.35), (4.05, y_land + 0.03, z_top), TRIM)
        # rails: the wall side of flight A, the well sides, the edge of the hall's slab and of the landing, the outer side of flight B
        handrail(b, (FLIGHT_X[0] - 0.12, Y_HALL, 0.0), (FLIGHT_X[0] - 0.12, y_land, z_top), 0.95, 1.4)
        handrail(b, (FLIGHT_X[1] + 0.1, Y_HALL, 0.0), (FLIGHT_X[1] + 0.1, y_land, z_top), 0.95, 1.4)
        handrail(b, (FLIGHT_X2[0] - 0.1, y_land, z_top), (FLIGHT_X2[0] - 0.1, Y_HALL, 2 * z_top), 0.95, 1.4)
        handrail(b, (FLIGHT_X2[1] + 0.1, y_land, z_top), (FLIGHT_X2[1] + 0.1, Y_HALL, 2 * z_top), 0.95, 1.4)
        handrail(b, (4.05, y_land, z_top), (4.05, D - WS, z_top), 1.05, 1.0, True)
    handrail(b, (4.05, Y_HALL, 0.0), (4.05, D - WS, 0.0), 1.05, 1.0, True)
    handrail(b, (FLIGHT_X[1], Y_HALL, 0.0), (FLIGHT_X2[0], Y_HALL, 0.0), 1.05, 0.4)
    # the ladder against the far wall: two rails, rungs, standoff brackets; it climbs through the hatch above
    yl = D - WS - WF - 0.14
    for xr in (hx0 + 0.20, hx1 - 0.20):
        b.body.box((xr - 0.02, yl - 0.02, 0.0), (xr + 0.02, yl + 0.02, hz + 1.1), TRIM)
    for k in range(int((hz + 1.0) / 0.3)):
        b.fine.cyl((hx0 + 0.20, yl, 0.25 + 0.3 * k), (hx1 - 0.20, yl, 0.25 + 0.3 * k), 0.011, TRIM, seg=6)
    for zb in (0.4, 1.4, 2.4, 3.4, 4.4, 5.4)[:6 if deep else 5]:
        for xr in (hx0 + 0.20, hx1 - 0.20):
            b.fine.box((xr - 0.015, yl + 0.02, zb), (xr + 0.015, D - WS - WF, zb + 0.05), STRUCT)
    on_wall(b, "far", L, D, W.pictogram_plate, b.body, 5.5, 1.6, 0.36, "pict_ladder")
    # hall furnishings: lockers and a first-aid box on the right wall, an extinguisher, the stair plate, the stair pictogram
    place(b, L - WS - WF - 0.26, 3.5, 180, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    on_wall(b, "left", L, D, W.extinguisher, b.body, 1.2, 0.0)
    on_wall(b, "left", L, D, W.first_aid, b.body, 2.4, 1.3)
    b.emit.label_fit((WS + WF + 0.002, 3.4, 2.15), 1.0, "room_stairs", (1, 0, 0))
    b.emit.label_fit((WS + WF + 0.002, 3.4, 1.3), 0.4, "pict_stairs", (1, 0, 0))
    # lights: two panels on the underside of the floor above, light lines at the flights and the landing
    F.ceiling_light_panel(b, 1.0, 2.6, 1.2, 1.8, 3.68, "white_cool", LAMP_HOT)
    F.ceiling_light_panel(b, 5.4, 7.0, 1.2, 1.8, 3.68, "white_cool", LAMP_HOT)
    if not cap:
        lamp_strip(b.emit, (WS + WF + 0.02, Y_HALL, 1.0), (WS + WF + 0.02, y_land, 3.0), 0.05, 0.006, "cool_dim", LAMP_DIM)
    lamp_strip(b.emit, (0.6, D - WS - WF - 0.02, 2.8), (3.9, D - WS - WF - 0.02, 2.8), 0.05, 0.006, "white_cool", LAMP)
    lamp_strip(b.emit, (0.6, D - WS - WF - 0.02, 0.9), (3.9, D - WS - WF - 0.02, 0.9), 0.05, 0.006, "cool_dim", LAMP_DIM)
    if top or cap:
        b.body.box((0.0, 0.0, hz - 0.3), (L, D, hz), STRUCT)
        F.ceiling_light_panel(b, 1.2, 2.8, 5.2, 5.8, hz - 0.3, "white_cool", LAMP_HOT)
    return b.build(name)


def stair_tower_top(name: str = "SM_SHIP_StairTowerTop"):
    return stair_tower(name, top=True)


def stair_tower_bottom(name: str = "SM_SHIP_StairTowerBottom"):
    return stair_tower(name, bottom=True)


def stair_tower_deep(name: str = "SM_SHIP_StairTower53"):
    return stair_tower(name, deep=True)


def stair_tower_cap(name: str = "SM_SHIP_StairTowerCap"):
    return stair_tower(name, cap=True)


# --------------------------------------------------------------------------------------------------------------- ladder trunk
def ladder_trunk(name: str = "SM_SHIP_LadderTrunk"):
    """A maintenance ladder trunk, 2 x 2 m, one deck tall: a floor with a hatch, three walls (open on +x), a ladder against the back wall
    that climbs through the hatch above, a light."""
    b = SParts(bevel=0.005, fine_bevel=0.003)
    hz = SHAFT_H
    for (lo, hi) in (((0.0, 0.0, -0.30), (2.0, 0.55, -0.012)), ((0.0, 1.45, -0.30), (2.0, 2.0, -0.012)), ((0.0, 0.55, -0.30), (0.5, 1.45, -0.012)),
                     ((1.5, 0.55, -0.30), (2.0, 1.45, -0.012))):
        b.body.box(lo, hi, STRUCT)
    b.body.box((0.0, 0.0, -0.012), (2.0, 2.0, 0.0), DECK)
    for (lo, hi) in (((0.0, 0.0, 0.0), (0.06, 2.0, hz)), ((0.0, 0.0, 0.0), (2.0, 0.06, hz)), ((0.0, 1.94, 0.0), (2.0, 2.0, hz))):
        b.body.box(lo, hi, COMPOSITE)
    for (lo, hi) in (((0.5, 0.5, 0.0), (1.5, 0.55, 0.10)), ((0.5, 1.45, 0.0), (1.5, 1.5, 0.10)), ((0.45, 0.55, 0.0), (0.5, 1.45, 0.10)),
                     ((1.5, 0.55, 0.0), (1.55, 1.45, 0.10))):
        b.body.box(lo, hi, TRIM)
    yl = 1.86
    for xr in (0.7, 1.3):
        b.body.box((xr - 0.02, yl - 0.02, 0.0), (xr + 0.02, yl + 0.02, hz + 1.1), TRIM)
    for k in range(int((hz + 1.0) / 0.3)):
        b.fine.cyl((0.7, yl, 0.25 + 0.3 * k), (1.3, yl, 0.25 + 0.3 * k), 0.011, TRIM, seg=6)
    for zb in (0.4, 1.4, 2.4, 3.4, 4.4):
        for xr in (0.7, 1.3):
            b.fine.box((xr - 0.015, yl + 0.02, zb), (xr + 0.015, 1.94, zb + 0.05), STRUCT)
    b.emit.lamp_box((0.9, 1.9, 2.0), (1.1, 1.935, 2.1), "white_cool", LAMP)
    b.emit.lamp_box((0.5, 0.548, 0.06), (1.5, 0.552, 0.09), "amber", LAMP_DIM)
    b.emit.label_fit((0.04, 1.0, 1.6), 0.5, "pict_ladder", (1, 0, 0))
    return b.build(name)
