"""ASN Aquila interior kit: the rooms of the keel (NAVE-2, Deck 12) — the fuel and coolant tank hall, the reaction-mass vessel hall and the crawlway hub where the maintenance
tunnels meet. The tunnels themselves are the modules of tone K (ship_corridor.build_crawl_module). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math

import ship_furniture as F
import ship_furniture3 as H
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Ry, T
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_RUST, LAMP_DIM, LAMP_HOT, RUBBER, STEEL, STRUCT, TRIM, SParts,
                      lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, place)
from ship_rooms_hub import on_wall
from ship_rooms_engineering import pipe_rack, valve_wheel, valve_wheel_flat


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "engineering_dim", cove: str = "white_warm") -> Style:
    return Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- pieces
def big_tank(b: SParts, l: float = 11.0, r: float = 1.3, zc: float = 1.55, band: str = "engineering") -> None:
    """A big horizontal tank along x centred on the origin (axis at the height zc): a barrel with welded bands, two domed ends with flanged pipe stubs, three saddles on the floor,
    two manhole domes on top with hand wheels, a level gauge on the +y flank (a lit column), a ladder at the +x end and a tag."""
    b.body.cyl((-l / 2, 0, zc), (l / 2, 0, zc), r, STEEL, seg=24)
    for sx in (-l / 2, l / 2):
        b.body.sphere((sx, 0, zc), r, STEEL, seg=24, rings=8, squash=(0.32, 1.0, 1.0))
    for k in range(1, int(l / 2.0)):
        x = -l / 2 + k * 2.0
        b.soft.cyl((x, 0, zc), (x + 0.05, 0, zc), r + 0.012, STRUCT, seg=24)
    for sx in (-l / 2 + 1.0, 0.0, l / 2 - 1.0):
        b.body.box((sx - 0.15, -r * 0.8, 0.0), (sx + 0.15, r * 0.8, zc - r * 0.55), STRUCT)
        b.body.box((sx - 0.25, -r * 0.9, 0.0), (sx + 0.25, r * 0.9, 0.08), TRIM)
    for sx in (-l / 2 + 2.6, l / 2 - 2.6):
        b.body.cyl((sx, 0, zc + r - 0.05), (sx, 0, zc + r + 0.28), 0.34, CRATE_GREY, seg=14)
        b.body.cyl((sx, 0, zc + r + 0.28), (sx, 0, zc + r + 0.34), 0.38, TRIM, seg=14)
        for k in range(8):
            a = 2 * math.pi * k / 8
            b.soft.cyl((sx + 0.3 * math.cos(a), 0.3 * math.sin(a), zc + r + 0.34), (sx + 0.3 * math.cos(a), 0.3 * math.sin(a), zc + r + 0.4), 0.02, STEEL, seg=6)
        with b.at(T(sx, 0, zc + r + 0.4)):
            valve_wheel_flat(b, 0.16)
    for sx in (-l / 2 - 0.35, l / 2 + 0.35):
        b.body.cyl((sx, 0.0, zc), (sx + (0.45 if sx < 0 else -0.45), 0.0, zc), 0.16, TRIM, seg=12)
        b.soft.cyl((sx, 0.0, zc), (sx + (0.04 if sx < 0 else -0.04), 0.0, zc), 0.25, STEEL, seg=12)
    b.soft.box((0.0, r - 0.02, 0.5), (0.2, r + 0.08, zc + 0.9), STRUCT)
    b.soft.box((0.2, r + 0.02, 0.6), (0.24, r + 0.07, zc + 0.8), DGLASS)
    b.emit.lamp_box((0.2, r + 0.071, 0.62), (0.24, r + 0.075, 1.5 + 0.5 * math.sin(l)), "cyan", LAMP_DIM)
    b.emit.label((-l * 0.25, r + 0.002, zc), 0.8, 0.2, (0, 1, 0), "eq_pipe")
    for k in range(6):                                                                                              # a ladder up the +x end to the tank's top
        z = 0.4 + k * 0.4
        b.soft.cyl((l / 2 + 0.1, -0.2, z), (l / 2 + 0.1, 0.2, z), 0.012, TRIM, seg=5)
    for sy in (-0.2, 0.2):
        b.soft.cyl((l / 2 + 0.1, sy, 0.2), (l / 2 + 0.1, sy, zc + r), 0.015, TRIM, seg=6)


def sphere_vessel(b: SParts, r: float = 1.45, seg: int = 20) -> None:
    """A spherical pressure vessel on a skirt, centred on the origin on the floor: the sphere with an equatorial band and meridian seams, a skirt ring with a manway and bolts, a
    manhole on top, a pipe down the skirt to a floor flange, a pressure gauge and a lit level strip."""
    zc = 0.5 + r
    b.body.cyl((0, 0, 0.0), (0, 0, 0.5), 0.95, STRUCT, seg=18)
    b.soft.cyl((0, 0, 0.5), (0, 0, 0.56), 1.02, TRIM, seg=18)
    b.body.sphere((0, 0, zc), r, STEEL, seg=seg, rings=14)
    b.soft.cyl((0, 0, zc - 0.03), (0, 0, zc + 0.03), r * 1.008, STRUCT, seg=seg)
    for k in range(6):
        ang = 2 * math.pi * k / 6
        b.soft.cyl((0.95 * math.cos(ang), 0.95 * math.sin(ang), 0.1), (0.95 * math.cos(ang), 0.95 * math.sin(ang), 0.45), 0.03, TRIM, seg=6)
    b.body.cyl((0, 0, zc + r - 0.06), (0, 0, zc + r + 0.2), 0.32, CRATE_GREY, seg=14)
    b.body.cyl((0, 0, zc + r + 0.2), (0, 0, zc + r + 0.26), 0.36, TRIM, seg=14)
    b.body.box((0.85, -0.3, 0.0), (1.0, 0.3, 0.4), CRATE_ORANGE)
    b.body.cyl((0.0, r * 0.9, 0.3), (0.0, r + 0.6, 0.3), 0.1, TRIM, seg=10)
    b.soft.cyl((0.0, r + 0.6, 0.3), (0.0, r + 0.6, 0.0), 0.1, TRIM, seg=10)
    b.soft.cyl((0.0, r + 0.5, 0.3), (0.0, r + 0.52, 0.3), 0.18, STEEL, seg=12)
    b.soft.cyl((r * 0.9, 0.0, zc + 0.2), (r * 0.9 + 0.1, 0.0, zc + 0.2), 0.07, DGLASS, seg=12)
    b.emit.lamp_box((r * 0.78, -0.02, 0.9), (r * 0.78 + 0.04, 0.02, 2.6), "cyan_dim", LAMP_DIM)


def valve_stand(b: SParts, n: int = 3) -> None:
    """A valve stand facing +x: a frame carrying a header and n branches with hand wheels and gauges, a hazard strip and a tag."""
    b.body.box((-0.2, -0.15 - 0.4 * n, 0.0), (-0.12, 0.15 + 0.4 * n, 1.9), COMPOSITE)
    b.body.cyl((0.0, -0.4 * n, 1.2), (0.0, 0.4 * n, 1.2), 0.1, STEEL, seg=12)
    for k in range(n):
        y = (k - (n - 1) / 2) * 0.8
        b.body.cyl((0.0, y, 1.2), (0.0, y, 0.2), 0.06, TRIM, seg=10)
        b.soft.cyl((0.0, y, 0.5), (0.3, y, 0.5), 0.02, TRIM, seg=6)
        with b.at(T(0.34, y, 0.5) @ Ry(-90)):
            valve_wheel(b, 0.15)
        b.soft.cyl((0.0, y + 0.18, 1.3), (0.06, y + 0.18, 1.3), 0.06, DGLASS, seg=12)
    b.emit.label((-0.119, 0.0, 1.75), 0.8, 0.2, (1, 0, 0), "tag_%02d" % (n % 12))
    b.emit.label((-0.119, 0.0, 0.1), 0.8, 0.07, (1, 0, 0), "hazard_h")


# ---------------------------------------------------------------------------------------------------------------------- tank hall
def tank(name: str = "SM_SHIP_Tank"):
    """32 x 16 x 3.4: the fuel and coolant tanks. Four big horizontal tanks (two rows of two, 11 m long) with a six-metre aisle between the halves for the hub path and the
    manifold; the manifold with its valve stands and a pump skid in the aisle; saddles, ladders and manholes; floor grating and drip lines; the gauge board by the door."""
    spec, L, D, H_ = _dims("tank")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("engineering_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, (x, y) in enumerate(((7.0, 4.8), (25.0, 4.8), (7.0, 11.4), (25.0, 11.4))):
        place(b, x, y, 0, big_tank, 11.0, 1.3, 1.6, "engineering")
    # the manifold across the aisle: two headers along y with the valve stands and a pump skid
    for y in (3.2, 13.0):
        b.body.cyl((13.4, y, 0.6), (18.6, y, 0.6), 0.16, STEEL, seg=14)
    b.body.cyl((16.0, 3.2, 0.6), (16.0, 13.0, 0.6), 0.2, STEEL, seg=14)
    for y in (3.2, 13.0):
        for x in (13.4, 18.6):
            b.soft.cyl((x - 0.03, y, 0.6), (x + 0.03, y, 0.6), 0.24, TRIM, seg=14)
    place(b, 16.4, 5.0, 0, valve_stand, 3)
    place(b, 15.6, 11.0, 180, valve_stand, 3)
    place(b, 16.0, 8.0, 90, H.pump_set, 1.6, "engineering")
    b.soft.box((13.2, 1.6, 0.0), (18.8, 14.4, 0.012), RUBBER)
    for (x0, x1, y0, y1) in ((13.2, 18.8, 1.6, 14.4),):
        lamp_strip(b.emit, (x0, y0, 0.02), (x1, y0, 0.02), 0.05, 0.004, "amber_dim", LAMP_DIM)
        lamp_strip(b.emit, (x0, y1, 0.02), (x1, y1, 0.02), 0.05, 0.004, "amber_dim", LAMP_DIM)
    place(b, xl + 0.3, 8.0, 0, H.wall_rack_panel, 4.0, 2.2, "scr_ship", "amber")
    place(b, xr - 0.02, 8.0, 180, H.wall_rack_panel, 4.0, 2.2, "scr_data", "amber")
    b.emit.label_fit((xl + 0.002, 11.0, 2.6), 1.6, "eq_pipe", (1, 0, 0))
    b.emit.label_fit((xr - 0.002, 11.0, 2.6), 1.6, "eq_gas", (-1, 0, 0))
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 17.6, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 18.4, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 12.0, 1, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "conduits", "safety"))
    dress_wall(b, "near", L, D, H_, 19.5, 31.5, 2, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "panelboard", "vent"))
    ceiling_services(b, L, D, H_, [(8.0, "pipes"), (3.0, "tray")], 1.0, 31.0, 4)
    ceiling_panels(b, L, D, H_, 6, 3, "white_warm", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- reaction mass
def reaction_mass(name: str = "SM_SHIP_ReactionMass"):
    """40 x 16 x 3.4: the reaction-mass vessels. Four spherical pressure vessels (two at each end of the hall) on their skirts with a ring of pipes on the floor joining them,
    the aisle between the pairs free for the hub path; hazard borders, ladders, a gauge wall at each end and the control post by the door."""
    spec, L, D, H_ = _dims("reaction_mass")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("engineering_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, x in enumerate((5.5, 12.5, 27.5, 34.5)):
        place(b, x, 8.6, 0, sphere_vessel, 1.45, 20)
        b.soft.box((x - 1.9, 6.6, 0.0), (x + 1.9, 10.6, 0.012), CRATE_ORANGE)
        b.soft.box((x - 1.8, 6.7, 0.012), (x + 1.8, 10.5, 0.016), RUBBER)
    for (xa, xb) in ((5.5, 12.5), (27.5, 34.5)):                                                                    # the floor pipes joining the pairs
        b.body.cyl((xa, 8.6 - 2.0, 0.3), (xb, 8.6 - 2.0, 0.3), 0.11, TRIM, seg=10)
    b.body.cyl((12.5, 6.6, 0.3), (27.5, 6.6, 0.3), 0.14, STEEL, seg=12)
    b.body.cyl((12.5, 6.6, 0.3), (12.5, 8.6 - 2.0, 0.3), 0.11, TRIM, seg=10)
    b.body.cyl((27.5, 6.6, 0.3), (27.5, 8.6 - 2.0, 0.3), 0.11, TRIM, seg=10)
    place(b, 20.0, 5.0, 0, valve_stand, 4)
    place(b, 20.0, 12.5, 180, valve_stand, 4)
    place(b, xl + 0.3, 8.0, 0, H.wall_rack_panel, 4.4, 2.2, "scr_ship", "amber")
    place(b, xr - 0.02, 8.0, 180, H.wall_rack_panel, 4.4, 2.2, "scr_data", "amber")
    place(b, 22.0, 2.4, 90, F.desk, 1.6, 0.7, 0.8, STEEL, False)
    place(b, 22.0, 2.6, -90, F.monitor, 0.5, 0.3, "scr_ship", False, z=0.8)
    place(b, 22.0, 1.5, 90, H.chair_op, FABRIC_RUST)
    b.emit.label_fit((20.0, yf - 0.002, 2.5), 2.4, "eq_gas", (0, -1, 0))
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 23.6, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 24.4, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 14.0, 1, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "conduits", "safety"))
    dress_wall(b, "near", L, D, H_, 26.0, 39.5, 2, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "panelboard", "vent"))
    dress_wall(b, "far", L, D, H_, 1.0, 39.0, 3, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "conduits", "panelboard", "safety"))
    ceiling_panels(b, L, D, H_, 8, 3, "white_cool", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- crawlway hub
def crawlway(name: str = "SM_SHIP_Crawlway"):
    """16 x 16 x 3.0: where the maintenance tunnels meet. A manifold of three vertical pipes with flanges and valve wheels in the middle, pipe racks across the room, a bench with
    a terminal, equipment lockers, a stack of spare hoses and a ladder to a ceiling hatch; amber light, grating over the floor."""
    spec, L, D, H_ = _dims("crawlway")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("engineering_dim", "amber"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    with b.at(T(11.0, 10.0, 0.0)):
        for k, (dx, dy, r) in enumerate(((0.0, 0.0, 0.34), (0.8, 0.4, 0.22), (-0.7, 0.5, 0.18))):
            b.body.cyl((dx, dy, 0.0), (dx, dy, H_), r, [STEEL, CRATE_BLUE, TRIM][k], seg=16)
            for z in (0.5, 1.4, 2.3):
                b.soft.cyl((dx, dy, z), (dx, dy, z + 0.06), r * 1.3, STRUCT, seg=16)
        with b.at(T(0.36, -0.2, 1.3) @ Ry(-90)):
            valve_wheel(b, 0.2)
    pipe_rack(b, 8.0, 2.0, 12.0, 2.3, 4, 3)
    pipe_rack(b, 13.5, 3.0, 13.0, 2.3, 3, 4)
    place(b, xl + 0.4, 6.0, 0, F.locker_row, 5, 0.5, 2.0, 0.55, CRATE_GREY)
    place(b, 4.0, yf - 0.3, -90, F.bench, 3.0, 0.5, 0.46, FABRIC_GREY)
    place(b, 4.0, yf - 0.02, -90, F.wall_screen, 1.6, 0.9, "scr_ship", z=1.7)
    for k in range(4):                                                                                              # spare hoses coiled on the floor, one on top of the other
        b.soft.cyl((xr - 1.0, 5.9, 0.12 + k * 0.2), (xr - 1.0, 6.5, 0.12 + k * 0.2), 0.34, RUBBER if k % 2 else CRATE_ORANGE, seg=14)
    place(b, xr - 0.45, 3.6, 180, F.rack, 2.4, 0.9, 2.2, 3, 21, 0.8, [CRATE_GREY, CRATE_ORANGE])
    yl = D - WS - WF - 0.14                                                                                          # the ladder to a hatch in the ceiling
    for xx in (11.7, 12.3):
        b.body.box((xx - 0.02, yl - 0.02, 0.0), (xx + 0.02, yl + 0.02, H_), TRIM)
    for k in range(int(H_ / 0.3)):
        b.soft.cyl((11.7, yl, 0.25 + 0.3 * k), (12.3, yl, 0.25 + 0.3 * k), 0.011, TRIM, seg=6)
    b.body.box((11.4, yl - 0.35, H_ - 0.06), (12.6, yl + 0.1, H_), CRATE_ORANGE)
    b.emit.label_fit((xl + 0.002, 11.0, 2.2), 1.2, "eq_maint", (1, 0, 0))
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 9.4, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 10.2, 1.4)
    dress_wall(b, "near", L, D, H_, 8.0, 15.5, 1, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "conduits", "vent"))
    ceiling_panels(b, L, D, H_, 3, 3, "amber", 1.6, 1.0, 0.5, LAMP_HOT)
    return b.build(name)
