"""ASN Aquila interior kit: Deck 1 (NAVE-2) — the Captain's ready room and the piece of the bridge corridor that gives it a door.

The ready room is the block between the two corridors of the bridge complex (docs/BIBBIA.md §6): 12 m long, 4.2 m across (the two corridors' shells face each other 4.2 m
apart), flush with the bridge's back wall at its forward end and with the corridors' aft ends. Its frame is the lane rooms' (origin on the floor at the corridor-side
corner, x along the corridor, y into the room), placed by ship_deck1.py at world (-20.8, -2.1). A working room, not a showpiece: a desk with the Captain's chair under a
viewport on the stern wall, two visitors' chairs, shelves, a sofa and an armchair round a low table, a holographic table by the forward wall (the plot on the wall screen
behind it). The old corridor kit (kit_corridor.py, the bridge's corridors are its shells) has no door in a side wall, so `corridor_door` is its window module with the
opening cut in the inner wall; the plan replaces the module that the bridge builder placed there (tools/ue_scripts/build_ship_interior.py removes the old actors).
"""
from __future__ import annotations

import math
import random

import kit_corridor as KC
import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_spec as SPEC
from bridge3_lib import Rx, T, frame
from ship_lib import (COMPOSITE, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMP, LAMP_DIM, LEATHER, RUBBER, STEEL, STRUCT, TRIM, WOOD, SParts)
from ship_rooms import Style, WF, WS, build_shell, place


WALL_HI = FABRIC_SAND               # the upper walls (the wainscot is wood)
HULL_PLATE = "MI_HULL_A_Plate"      # the hull's plating (an instance of the project: the fairings under the bridge's corridors have it)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ----------------------------------------------------------------------------------------------------------------------------------------------------- the corridor
DOOR_W, DOOR_H = 1.4, 2.2           # the opening in the corridor's inner wall (the plate over it: 1.36 x 0.17 m)
DOOR_X0 = 0.3                        # along the module: the opening is 0.3 .. 1.7, the first wall bay (0.14 .. 1.86) of the kit's panels


def corridor_door(name: str = "SM_SHIP_BridgeCorridorDoor"):
    """SM_COR_ShellWindow_4m (the bridge's window module, kit_corridor.py) with a 1.4 x 2.2 m door in the wall opposite the window: the kit's own module with the opening cut
    in (`kit_corridor.shell(..., door=...)`: frame, sill and status bars of the v3 corridor). Same frame and materials as the kit's module."""
    return KC.shell(name, window=True, door=(DOOR_X0, DOOR_W, DOOR_H))   # the v3 kit cuts the door itself (ARTE-PLANCIA-2)


def captain_chair(b: SParts, mat: str = LEATHER) -> None:
    """A high-backed swivel chair facing +x: a five-spoke base on casters, a gas column, a deep seat, a tall back with a headrest and two padded arms."""
    for k in range(5):
        a = math.radians(72.0 * k + 18.0)
        c, s = math.cos(a), math.sin(a)
        b.fine.cyl((0.04 * c, 0.04 * s, 0.11), (0.30 * c, 0.30 * s, 0.07), 0.016, TRIM, seg=6)
        b.fine.cyl((0.30 * c, 0.30 * s, 0.0), (0.30 * c, 0.30 * s, 0.065), 0.022, RUBBER, seg=8)
    b.body.cyl((0, 0, 0.10), (0, 0, 0.44), 0.035, TRIM, seg=10)
    b.body.box((-0.24, -0.24, 0.43), (0.24, 0.24, 0.47), STRUCT)
    b.soft.box((-0.27, -0.27, 0.47), (0.27, 0.27, 0.56), mat)
    b.soft.box((-0.31, -0.26, 0.56), (-0.20, 0.26, 1.16), mat)
    b.soft.box((-0.33, -0.19, 1.16), (-0.23, 0.19, 1.40), mat)
    b.fine.box((-0.325, -0.265, 0.56), (-0.31, -0.25, 1.16), TRIM)
    b.fine.box((-0.325, 0.25, 0.56), (-0.31, 0.265, 1.16), TRIM)
    for sy in (-0.31, 0.31):
        b.fine.box((-0.23, sy - 0.012, 0.56), (-0.20, sy + 0.012, 0.69), TRIM)
        b.soft.box((-0.22, sy - 0.04, 0.69), (0.20, sy + 0.04, 0.735), mat)
        b.fine.box((0.14, sy - 0.01, 0.56), (0.17, sy + 0.01, 0.69), TRIM)


def executive_desk(b: SParts, w: float = 2.0, d: float = 0.95, h: float = 0.76) -> None:
    """The Captain's desk, w along y, the sitter on its -x side: a wooden top with a leather inlay, a pedestal of three drawers at either end, a modesty panel on the
    visitors' side."""
    hw, hd = w / 2, d / 2
    for sg in (-1, 1):
        y0, y1 = (-hw, -hw + 0.52) if sg < 0 else (hw - 0.52, hw)
        b.body.box((-hd, y0, 0.06), (hd, y1, h - 0.05), WOOD)
        b.body.box((-hd + 0.03, y0 + 0.03, 0.0), (hd - 0.03, y1 - 0.03, 0.06), STRUCT)
        for k in range(3):
            z0 = 0.10 + k * 0.20
            b.fine.box((-hd - 0.014, y0 + 0.03, z0), (-hd, y1 - 0.03, z0 + 0.18), WOOD)
            b.fine.box((-hd - 0.035, (y0 + y1) / 2 - 0.09, z0 + 0.075), (-hd - 0.014, (y0 + y1) / 2 + 0.09, z0 + 0.095), TRIM)
    b.body.box((hd - 0.03, -hw + 0.52, 0.12), (hd, hw - 0.52, h - 0.05), WOOD)
    b.body.box((-hd - 0.03, -hw - 0.03, h - 0.05), (hd + 0.03, hw + 0.03, h), WOOD)
    b.soft.box((-hd + 0.10, -hw + 0.14, h), (hd - 0.10, hw - 0.14, h + 0.004), LEATHER)
    for (lo, hi) in (((-hd + 0.095, -hw + 0.135, h), (hd - 0.095, -hw + 0.14, h + 0.0045)), ((-hd + 0.095, hw - 0.14, h), (hd - 0.095, hw - 0.135, h + 0.0045)),
                     ((-hd + 0.095, -hw + 0.14, h), (-hd + 0.10, hw - 0.14, h + 0.0045)), ((hd - 0.10, -hw + 0.14, h), (hd - 0.095, hw - 0.14, h + 0.0045))):
        b.fine.box(lo, hi, TRIM)


def credenza(b: SParts, w: float = 2.6, d: float = 0.45, h: float = 0.78, doors: int = 4) -> None:
    """A wooden sideboard facing +x, w along y: a carcase on a recessed plinth, flush doors with brass pulls, an overhanging top."""
    b.body.box((-d / 2, -w / 2, 0.07), (d / 2, w / 2, h - 0.03), WOOD)
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.03, 0.0), (d / 2 - 0.03, w / 2 - 0.03, 0.07), STRUCT)
    b.body.box((-d / 2 - 0.012, -w / 2 - 0.012, h - 0.03), (d / 2 + 0.02, w / 2 + 0.012, h), WOOD)
    for k in range(doors):
        y0 = -w / 2 + k * w / doors
        y1 = y0 + w / doors
        b.fine.box((d / 2, y0 + 0.012, 0.11), (d / 2 + 0.012, y1 - 0.012, h - 0.07), WOOD)
        b.fine.box((d / 2 + 0.012, (y0 + y1) / 2 - 0.1, h - 0.22), (d / 2 + 0.03, (y0 + y1) / 2 + 0.1, h - 0.2), TRIM)
    for k in range(1, doors):
        y = -w / 2 + k * w / doors
        b.fine.box((d / 2 + 0.001, y - 0.004, 0.11), (d / 2 + 0.012, y + 0.004, h - 0.07), RUBBER)


def desk_lamp(b: SParts) -> None:
    """A banker's lamp: a brass foot, a stem, a dome shade that glows from within."""
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.02), 0.075, TRIM, seg=14)
    b.fine.cyl((0, 0, 0.02), (0, 0, 0.30), 0.012, TRIM, seg=8)
    b.fine.cyl((0.02, 0, 0.27), (0.02, 0, 0.36), 0.075, STRUCT, seg=14, r2=0.03)
    b.emit.lamp_cyl((0.02, 0, 0.268), (0.02, 0, 0.274), 0.06, "white_warm", LAMP, seg=12)


def desk_set(b: SParts) -> None:
    """On the desk, in the sitter's frame (facing +x, the sitter at -x): the display, a data pad, the blotter, a lamp, a mug, a stack of pads."""
    with b.at(T(0.28, 0.0, 0.0)):
        b.soft.box((-0.65, -0.45, 0.0), (-0.15, 0.45, 0.008), STRUCT)                    # a blotter of dark card
    with b.at(frame(0.30, -0.45, 0.0, 180.0)):
        F.monitor(b, 0.55, 0.32, "scr_ship")
    with b.at(frame(0.30, 0.52, 0.0, 180.0)):
        F.monitor(b, 0.40, 0.25, "scr_data")
    with b.at(frame(0.22, 0.90, 0.0, 0.0)):
        desk_lamp(b)
    b.fine.box((-0.28, -0.20, 0.0), (-0.08, 0.04, 0.012), IVORY)                          # a data pad
    b.fine.box((-0.275, -0.195, 0.012), (-0.085, 0.035, 0.014), DGLASS)
    b.fine.cyl((0.0, -0.78, 0.0), (0.0, -0.78, 0.09), 0.035, IVORY, seg=10)               # a mug
    b.fine.cyl((0.0, -0.78, 0.085), (0.0, -0.78, 0.09), 0.03, STRUCT, seg=10)
    b.fine.box((-0.12, 0.30, 0.0), (0.0, 0.50, 0.035), IVORY)                             # a stack of paper
    b.fine.box((0.36, -0.14, 0.0), (0.40, 0.14, 0.05), TRIM)                              # the brass name plate on the visitors' edge


def ship_model(b: SParts, length: float = 0.62) -> None:
    """The Aquila in a model, bow towards +x, resting on its stand (the origin is the stand's centre on its table): a lofted hull with the flight deck, the island on the
    starboard side, four twin turrets, the engine bells aglow, a livery band, on a wooden base with two brass cradles."""
    s = length / 0.62
    b.body.box((-0.34 * s, -0.09 * s, 0.0), (0.34 * s, 0.09 * s, 0.025), WOOD)
    b.fine.box((-0.345 * s, -0.095 * s, 0.025), (0.345 * s, 0.095 * s, 0.03), TRIM)
    for xc in (-0.12, 0.14):
        b.fine.cyl((xc * s, 0.0, 0.03), (xc * s, 0.0, 0.082), 0.011, TRIM, seg=8)
        b.fine.box(((xc - 0.03) * s, -0.04 * s, 0.082), ((xc + 0.03) * s, 0.04 * s, 0.088), TRIM)
    sta = (0.0, 0.1, 0.3, 0.55, 0.78, 0.92, 1.0)
    hw = (0.80, 0.95, 1.0, 1.0, 0.92, 0.55, 0.12)
    ht = (0.9, 1.0, 1.0, 1.0, 0.95, 0.8, 0.55)
    rings = []
    for t, wf, hf in zip(sta, hw, ht):
        x = (-0.30 + 0.60 * t) * s
        w, hgt = 0.045 * s * wf, 0.036 * s * hf
        z0 = 0.095 * s
        rings.append([(x, -w, z0 + 0.42 * hgt), (x, -0.8 * w, z0), (x, 0.8 * w, z0), (x, w, z0 + 0.42 * hgt), (x, 0.92 * w, z0 + hgt), (x, -0.92 * w, z0 + hgt)])
    b.soft.loft(rings, COMPOSITE)
    z_deck = 0.095 * s + 0.036 * s
    b.soft.box((-0.26 * s, -0.036 * s, z_deck), (0.22 * s, 0.036 * s, z_deck + 0.002), STEEL)                  # the flight deck
    b.soft.box((-0.27 * s, 0.026 * s, z_deck), (-0.17 * s, 0.044 * s, z_deck + 0.030 * s), STRUCT)               # the island, starboard side
    b.soft.box((-0.25 * s, 0.030 * s, z_deck + 0.030 * s), (-0.19 * s, 0.040 * s, z_deck + 0.044 * s), STEEL)
    for xt in (0.02, 0.12, 0.22):
        b.soft.cyl((xt * s, 0.0, z_deck), (xt * s, 0.0, z_deck + 0.007 * s), 0.011 * s, STEEL, seg=8)
        b.soft.box((xt * s, -0.003 * s, z_deck + 0.003 * s), ((xt + 0.026) * s, 0.003 * s, z_deck + 0.007 * s), STRUCT)
    b.soft.box((-0.30 * s, -0.047 * s, 0.095 * s + 0.010 * s), (0.28 * s, -0.0455 * s, 0.095 * s + 0.020 * s), FABRIC_NAVY)       # the blue band of the livery
    for yb in (-0.020, 0.0, 0.020):
        b.emit.lamp_cyl((-0.298 * s, yb * s, 0.095 * s + 0.020 * s), (-0.304 * s, yb * s, 0.095 * s + 0.020 * s), 0.011 * s, "amber", LAMP_DIM, seg=10)


def flag_stand(b: SParts) -> None:
    """The ship's ensign on a stand, facing +x: a weighted brass base, a pole with a gilt finial, a cross-bar, the cloth (navy field, a sand stripe) hanging from it."""
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.045), 0.18, STRUCT, seg=18)
    b.fine.cyl((0, 0, 0.045), (0, 0, 0.06), 0.15, TRIM, seg=18)
    b.fine.cyl((0, 0, 0.06), (0, 0, 2.16), 0.014, TRIM, seg=8)
    b.fine.sphere((0, 0, 2.2), 0.032, TRIM, seg=10, rings=6)
    b.fine.cyl((0, -0.46, 2.04), (0, 0.46, 2.04), 0.008, TRIM, seg=6)
    b.soft.box((0.004, -0.44, 1.46), (0.016, 0.44, 2.02), FABRIC_NAVY)
    b.soft.box((0.016, -0.44, 1.56), (0.021, 0.44, 1.62), FABRIC_SAND)
    b.soft.box((0.016, -0.12, 1.70), (0.021, 0.12, 1.92), FABRIC_SAND)
    b.soft.box((0.021, -0.07, 1.74), (0.026, 0.07, 1.88), FABRIC_NAVY)


def globe(b: SParts) -> None:
    """A lit globe of Aurelia on a brass stand: a ring foot, a stem, a half meridian, the glowing sphere."""
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.03), 0.16, STRUCT, seg=16)
    b.fine.cyl((0, 0, 0.03), (0, 0, 0.62), 0.016, TRIM, seg=8)
    b.fine.cyl((0, 0, 0.62), (0, 0, 0.66), 0.045, TRIM, seg=12)
    H.lamp_sphere(b.emit, (0, 0, 0.90), 0.20, "cyan_dim", LAMP_DIM)
    rng = random.Random(5)
    for k in range(9):                                                                  # the dark lands on the lit sea
        a, e = rng.uniform(0, 2 * math.pi), rng.uniform(-1.1, 1.1)
        n = (math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e))
        rr = rng.uniform(0.035, 0.065)
        b.soft.sphere((0.195 * n[0], 0.195 * n[1], 0.90 + 0.195 * n[2]), rr, FABRIC_RUST if k % 3 else STRUCT, seg=8, rings=5, squash=(1.0, 1.0, 1.0))
    H.ring(b.fine, 0.0, 0.0, 0.896, 0.208, 0.012, 0.008, TRIM, seg=32)
    for k in range(18):                                                                 # the half meridian that holds it, round the +y side
        a0, a1 = math.radians(-90 + 180 * k / 18), math.radians(-90 + 180 * (k + 1) / 18)
        r = 0.225
        b.fine.cyl((0.0, r * math.cos(a0), 0.90 + r * math.sin(a0)), (0.0, r * math.cos(a1), 0.90 + r * math.sin(a1)), 0.008, TRIM, seg=5)


def starfield(b: SParts, x_face: float, yc: float, w: float, h: float, zc: float, seed: int = 11) -> None:
    """A viewport on a wall facing +x (the wall's finished face at x_face, centre yc, zc): a wooden frame, dark glass, a field of stars and the limb of a planet."""
    rng = random.Random(seed)
    fw, fd = 0.09, 0.07
    y0, y1, z0, z1 = yc - w / 2, yc + w / 2, zc - h / 2, zc + h / 2
    b.body.box((x_face, y0 - fw, z0 - fw), (x_face + fd, y1 + fw, z0), WOOD)
    b.body.box((x_face, y0 - fw, z1), (x_face + fd, y1 + fw, z1 + fw), WOOD)
    b.body.box((x_face, y0 - fw, z0), (x_face + fd, y0, z1), WOOD)
    b.body.box((x_face, y1, z0), (x_face + fd, y1 + fw, z1), WOOD)
    b.fine.box((x_face + fd, y0 - fw, z0 - fw), (x_face + fd + 0.01, y1 + fw, z0 - fw + 0.02), TRIM)
    b.fine.box((x_face + fd, y0 - fw, z1 + fw - 0.02), (x_face + fd + 0.01, y1 + fw, z1 + fw), TRIM)
    b.fine.box((x_face + fd, y0 - fw, z0), (x_face + fd + 0.01, y0 - fw + 0.02, z1), TRIM)
    b.fine.box((x_face + fd, y1 + fw - 0.02, z0), (x_face + fd + 0.01, y1 + fw, z1), TRIM)
    b.body.box((x_face, y0, z0), (x_face + 0.03, y1, z1), DGLASS)
    xe = x_face + 0.031
    for k in range(70):
        y = rng.uniform(y0 + 0.04, y1 - 0.04)
        z = rng.uniform(z0 + 0.04, z1 - 0.04)
        sz = rng.choice((0.008, 0.008, 0.012, 0.016))
        cell = rng.choice(("white", "ice", "ice", "white_cool", "amber", "cyan_dim"))
        b.emit.lamp_box((xe, y - sz / 2, z - sz / 2), (xe + 0.002, y + sz / 2, z + sz / 2), cell, LAMP_DIM)
    # a planet low on the right: the part of its disc inside the viewport (a dim blue face) and its lit limb
    cy, cz, r = y1 - 0.40, z0 - 0.70, 1.10
    disc = _clip_polygon([(cy + r * math.cos(a), cz + r * math.sin(a)) for a in (2 * math.pi * k / 96 for k in range(96))], y0 + 0.015, y1 - 0.015, z0 + 0.015, z1 - 0.015)
    if len(disc) >= 3:
        b.emit.lamp_face([(xe, py, pz) for py, pz in disc], "command_dim", (1, 0, 0), LAMP_DIM)
    seg = 90
    for k in range(seg):
        a0, a1 = math.radians(20 + 140 * k / seg), math.radians(20 + 140 * (k + 1) / seg)
        p0 = (cy + r * math.cos(a0), cz + r * math.sin(a0))
        p1 = (cy + r * math.cos(a1), cz + r * math.sin(a1))
        if not all(y0 + 0.03 < q[0] < y1 - 0.03 and z0 + 0.03 < q[1] < z1 - 0.03 for q in (p0, p1)):
            continue
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 1.06
        ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        b.emit.lamp_cbox((xe + 0.001, mid[0], mid[1]), (0.002, ln, 0.016), "cyan", LAMP_DIM, Rx(ang))
        b.emit.lamp_cbox((xe + 0.0005, mid[0] - 0.0, mid[1] - 0.022 * math.sin((a0 + a1) / 2)), (0.002, ln, 0.03), "cyan_dim", LAMP_DIM, Rx(ang))


def _clip_polygon(poly, y0: float, y1: float, z0: float, z1: float):
    """A convex polygon [(y, z)] clipped to a rectangle (Sutherland-Hodgman)."""
    def clip(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            a, c = pts[i - 1], pts[i]
            ia, ic = inside(a), inside(c)
            if ic:
                if not ia:
                    out.append(cut(a, c))
                out.append(c)
            elif ia:
                out.append(cut(a, c))
        return out

    def at_y(v):
        return lambda a, c: (v, a[1] + (c[1] - a[1]) * (v - a[0]) / (c[0] - a[0]))

    def at_z(v):
        return lambda a, c: (a[0] + (c[0] - a[0]) * (v - a[1]) / (c[1] - a[1]), v)

    pts = clip(poly, lambda p: p[0] >= y0, at_y(y0))
    pts = clip(pts, lambda p: p[0] <= y1, at_y(y1)) if pts else pts
    pts = clip(pts, lambda p: p[1] >= z0, at_z(z0)) if pts else pts
    pts = clip(pts, lambda p: p[1] <= z1, at_z(z1)) if pts else pts
    return pts


# ----------------------------------------------------------------------------------------------------------------------------------------------------- the room
def ready_room(name: str = "SM_SHIP_ReadyRoom"):
    """12 x 4.2 x 2.9: the Captain's ready room. From the stern wall: the viewport over a sideboard (the ship's model, a decanter, a lamp), the Captain's desk with the high
    chair behind it and two visitors' chairs in front, the ensign and a globe in the corners, a wall of books by the door's side, the door; forward of it a sofa along the far
    wall, an armchair either side of a low table, a floor lamp, and at the forward wall a holographic table under its ring of light, the plot on the wall screen behind it."""
    spec, L, D, H_ = _dims("ready_room")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=WALL_HI, wain_h=1.05, ceil=IVORY, accent="warm_dim", cove="white_warm",
               ribs=False, skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # under the floor, down into the island's top, a fairing of the hull's plating between the two that the bridge's builder put under the corridors (quarters.py): the room does not float
    b.body.box((0.0, 0.05, -1.85), (L, D - 0.05, -0.30), HULL_PLATE)
    # the stern wall: viewport, sideboard and what stands on it
    starfield(b, xl, 2.0, 2.7, 1.0, 1.62)
    place(b, xl + 0.225, 2.0, 0, credenza, 2.7, 0.45, 0.78, 4)
    place(b, xl + 0.23, 1.45, 90, ship_model, 0.62, z=0.78)
    place(b, xl + 0.23, 2.55, 0, desk_lamp, z=0.78)
    for (yy, hh) in ((2.95, 0.30), (3.09, 0.24)):
        b.fine.cyl((xl + 0.22, yy, 0.78), (xl + 0.22, yy, 0.78 + hh * 0.7), 0.045, DGLASS, seg=12, r2=0.06)
        b.fine.cyl((xl + 0.22, yy, 0.78 + hh * 0.7), (xl + 0.22, yy, 0.78 + hh), 0.016, DGLASS, seg=8)
    place(b, xl + 0.35, 0.50, 0, flag_stand)
    place(b, xl + 0.45, yf - 0.40, 0, F.potted_plant, 1.5, 4)
    # the desk and its chairs, on a rug
    place(b, 2.55, 2.0, 0, G.rug, 3.6, 3.0, FABRIC_RUST, FABRIC_SAND)
    place(b, 2.25, 2.0, 0, executive_desk, 2.0, 0.95, 0.76)
    place(b, 2.25, 2.0, 0, desk_set, z=0.76)
    place(b, 1.22, 2.0, 0, captain_chair)
    place(b, 3.50, 1.75, 180, F.armchair, FABRIC_NAVY)
    place(b, 3.50, 2.75, 180, F.armchair, FABRIC_NAVY)
    # the near wall aft of the door: a low cabinet under two framed charts
    place(b, 2.30, 0.05 + 0.20, 90, credenza, 2.0, 0.40, 0.56, 3)
    place(b, 1.70, 0.05 + 0.06, 90, F.wall_screen, 1.0, 0.62, "scr_map", z=1.62)
    place(b, 3.00, 0.05 + 0.06, 90, F.wall_screen, 1.0, 0.62, "scr_star", z=1.62)
    # the far wall: the globe, three bookcases
    place(b, 1.55, yf - 0.30, 0, globe)
    for k, xc in enumerate((3.65, 4.85, 6.05)):
        place(b, xc, yf - 0.17, -90, F.shelf, 1.15, 0.34, 2.1, 6, WOOD, True, 20 + k)
    # the lounge: a sofa on the far wall, a low table, an armchair at each side of it, a floor lamp, a rug
    place(b, 8.30, 2.15, 0, G.rug, 3.5, 2.7, FABRIC_SAND, FABRIC_RUST)
    place(b, 8.30, yf - 0.44, -90, F.sofa, 2.4, FABRIC_RUST)
    place(b, 8.30, 2.45, 0, F.low_table, 1.2, 0.5, 0.4, WOOD)
    place(b, 6.95, 2.45, 0, F.armchair, FABRIC_NAVY)
    place(b, 8.30, 0.95, 90, F.armchair, FABRIC_NAVY)
    place(b, 9.75, yf - 0.30, 0, F.lamp_standard, 1.5, "white_warm")
    place(b, 6.65, yf - 0.35, 0, F.potted_plant, 1.4, 6)
    place(b, 7.60, 0.05 + 0.06, 90, F.wall_screen, 1.1, 0.64, "scr_news", z=1.62)
    place(b, 9.00, 0.05 + 0.06, 90, F.wall_screen, 1.1, 0.64, "scr_sched", z=1.62)
    # the forward wall: the plot, and the holographic table in front of it
    place(b, xr - 0.06, 2.0, 180, F.wall_screen, 2.6, 1.3, "scr_tac", z=1.62)
    place(b, 10.45, 2.0, 0, G.holo_table, 0.70, 0.9)
    # light: warm panels over the desk, the door and the lounge, a ring over the table
    for (cx, w) in ((2.3, 1.8), (5.2, 1.2), (8.2, 2.2)):
        F.ceiling_light_panel(b, cx - w / 2, cx + w / 2, 1.75, 2.25, H_ - 0.05, "white_warm", LAMP)
    H.lamp_ring(b.emit, 10.45, 2.0, H_ - 0.06, 0.78, 0.05, 0.02, "cyan_dim")
    # the door's inner side: a status light
    b.emit.lamp_box((5.0 + 0.80, WF + 0.002, 1.3), (5.0 + 0.84, WF + 0.012, 1.5), "green", LAMP_DIM)
    return b.build(name)
