"""ASN Aquila interior kit: the rooms of the Marines' deck (NAVE-2, Deck 8) — the assault-shuttle bay with its two Kestrels, the barracks, the kit room and the
firing range. The Armory is the older one (ship_rooms_work.py). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_craft as C
import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture4 as K
import ship_furniture5 as K5
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, WOOD, SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_label, wall_matrix)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "security_dim", cove: str = "security_dim", floor: str = DECK, wain: float = 1.2, lo: str = COMPOSITE, hi: str = COMPOSITE) -> Style:
    return Style(floor=floor, floor_mode="plates", wall_lo=lo, wall_hi=hi, wain_h=wain, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- shuttle bay
KESTREL_X, KESTREL_Y = SPEC.KESTREL_X, SPEC.KESTREL_Y          # where the craft stand (room frame): the nose 0.45 m short of the launch portal, symmetrical about x = 16


def shuttle_bay(name: str = "SM_SHIP_ShuttleBay"):
    """32 x 16 x 3.7: the two Kestrels parked nose to the far wall, each in front of its launch tube's door (a floor rail runs from the cradle to the portal), the ramps down
    towards the entrance; between them the bay boss's console against the middle pier of the far wall; a tool bench, the rocket-pod cage and the parts store along the left wall,
    ground power, a tow tug, fuel and foam carts along the right one; hoses hang from the ceiling to the craft's fuel ports."""
    spec, L, D, H_ = _dims("shuttle_bay")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # the craft, the launch portals, the floor markings and rails
    for cx, tag, col in zip(KESTREL_X, ("eq_k1", "eq_k2"), (-1, 1)):
        with b.at(frame(cx, KESTREL_Y, 0.0, 90.0)):
            C.kestrel(b, col, tag)
        place(b, cx, yf, -90, K.launch_portal, 5.6, 3.2, "eq_launch")
        for sx in (-0.5, 0.5):                                                                                        # the launch rails: steel with a lit channel between them
            b.body.box((cx + sx - 0.06, 1.2, 0.0), (cx + sx + 0.06, yf - 0.4, 0.025), TRIM)
        lamp_strip(b.emit, (cx, 1.4, 0.004), (cx, yf - 0.6, 0.004), 0.05, 0.004, "amber", LAMP_DIM)
        for sx in (-4.3, 4.3):                                                                                        # the parking box: hazard bands along both sides
            b.emit.label((cx + sx, 8.0, 0.006), 13.0, 0.16, (0, 0, 1), "hazard_h", up=(1, 0, 0))
        b.emit.label((cx, 15.3, 0.006), 8.6, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
        b.emit.label_fit((cx, WF + 0.002, 3.05), 1.5, tag, (0, 1, 0))                                                 # the craft's name over its ramp, on the entrance wall
        b.emit.label_fit((cx, WF + 0.002, 2.78), 1.1, "eq_launch", (0, 1, 0))
        for sx in (-2.0, 2.0):                                                                                        # the fuel hoses from the ceiling to the dorsal ports
            K.umbilical(b, (cx + sx * 0.55, KESTREL_Y - 1.9 - 0.2, H_ - 0.12), (cx + sx * 0.56, KESTREL_Y - 1.9, 2.82), 0.045)
    # the bay boss's station on the middle pier, between the two portals
    place(b, 16.0, yf - 0.55, -90, H.work_console, 4.4, "security", 3, ["scr_tac", "scr_ship", "scr_sched", "scr_map"], True, True)
    place(b, 16.0, yf - 1.9, 90, H.chair_op, FABRIC_RUST)
    place(b, 12.3, yf - 0.6, -90, F.counter, 1.2, 0.6, 0.92, STEEL, COMPOSITE, True, False)
    place(b, 19.7, yf - 0.6, -90, F.counter, 1.2, 0.6, 0.92, STEEL, COMPOSITE, True, False)
    b.emit.label_fit((16.0, yf - 0.01, 2.95), 2.4, "eq_launch", (0, -1, 0))
    # left wall: the tool bench, a rolling chest, the parts store, the rocket-pod cage and crates
    place(b, xl + 0.5, 3.5, 0, G.workbench, 2.6, 0.8, 0.95, True)
    place(b, xl + 0.02, 3.5, 0, G.tool_wall, 2.6, 1.4, 5)
    place(b, 1.9, 5.5, 180, K.tool_chest, 0.8, 0.5, 1.0)
    place(b, xl + 0.45, 7.2, 0, G.parts_bins, 2.4, 1.9, 0.5, 6)
    cage_x, cage_y0, cage_y1 = 3.4, 10.0, 14.8
    with b.at(frame(cage_x, (cage_y0 + cage_y1) / 2, 0.0, 0.0)):
        G.cage_wall(b, cage_y1 - cage_y0, 2.6)
    for y0, y1 in ((cage_y0, cage_y0), (cage_y1, cage_y1)):
        with b.at(frame((cage_x + xl) / 2, y0, 0.0, 90.0)):
            G.cage_wall(b, cage_x - xl, 2.6)
    for k in range(2):                                                                                                # four rocket pods on two racks inside the cage
        with b.at(T(xl + 1.4, cage_y0 + 1.5 + k * 2.1, 0.0)):
            for j in range(2):
                b.body.cyl((-0.6, 0.0, 0.5 + j * 0.45), (0.9, 0.0, 0.5 + j * 0.45), 0.14, CRATE_GREY, seg=12)
                b.body.cyl((0.9, 0.0, 0.5 + j * 0.45), (1.25, 0.0, 0.5 + j * 0.45), 0.14, CRATE_ORANGE, seg=12, r2=0.06)
            b.body.box((-0.4, -0.3, 0.0), (0.2, 0.3, 0.1), STRUCT)
            b.body.box((0.4, -0.3, 0.0), (1.0, 0.3, 0.1), STRUCT)
            b.body.box((-0.35, -0.22, 0.1), (-0.25, 0.22, 0.4), STRUCT)
    place(b, xl + 0.8, cage_y0 + 0.6, 0, F.crate, 0.8, 0.55, 0.45, CRATE_OLIVE, "eq_ammo", False)
    with b.at(frame(xl + 0.5, 8.9, 0.0, 0.0)):
        b.emit.label_fit((0.0, 0.0, 2.4), 1.0, "eq_ammo", (1, 0, 0))
    # right wall: ground power with its cable out to the nearest craft, fuel and foam
    for k, y in enumerate((3.0, 4.7)):
        place(b, xr - 0.95, y, 90, K.gpu_cart)
    b.soft.tube([(xr - 1.45, 3.0, 0.5), (xr - 1.9, 3.4, 0.05), (xr - 3.2, 4.2, 0.03), (KESTREL_X[1] + 2.8, 5.0, 0.03), (KESTREL_X[1] + 1.45, 5.6, 0.2), (KESTREL_X[1] + 1.2, 5.9, 0.6)],
                0.035, CRATE_ORANGE, seg=6)
    place(b, xr - 0.8, 11.0, 90, K.fuel_cart)
    place(b, xr - 0.55, 13.4, 90, K.foam_cart)
    # the aisle between the craft keeps its middle clear (the way from the doors to the bay boss); along its edges: ordnance trolleys, the tug, the platoon's kit
    place(b, 13.0, 12.4, 90, K.pod_trolley, 2)
    place(b, 19.0, 4.6, -90, K.pod_trolley, 2)
    place(b, 19.1, 11.2, 90, K.tow_tug)
    place(b, 12.9, 3.9, 180, K.tool_chest, 0.8, 0.5, 1.0)
    place(b, 12.9, 5.1, 180, K.tool_chest, 0.8, 0.5, 1.0)
    place(b, 19.0, 2.2, 90, F.pallet, 1.2, 0.8)
    for j in range(3):
        place(b, 19.0, 2.2, 90 + 6 * j, F.crate, 0.8, 0.55, 0.45, [CRATE_OLIVE, CRATE_GREY, CRATE_OLIVE][j], None, False, z=0.145 + 0.45 * (j % 2))
    place(b, 18.7, 2.5, 80, K.duffel, 0.8, 0.2)
    place(b, 19.5, 1.9, 120, K.duffel, 0.7, 0.19, FABRIC_GREY)
    for cx in KESTREL_X:
        for sx in (-2.3, 2.3):
            place(b, cx + sx, 1.0, 0, K.floor_hatch, 0.9, 0.6)
        for sx in (-1.25, 1.25):                                                                                      # chocks at the rear legs
            place(b, cx + sx, KESTREL_Y - 3.5 - 0.5, 90, K.chock)
            place(b, cx + sx, KESTREL_Y - 3.5 + 0.5, -90, K.chock)
        b.emit.label_fit((cx, 0.9, 0.006), 2.2, "eq_k1" if cx < 16 else "eq_k2", (0, 0, 1), up=(0, 1, 0))
    on_wall(b, "right", L, D, W.extinguisher, b.body, D - 14.9, 0.0)
    on_wall(b, "right", L, D, W.first_aid, b.body, D - 15.2, 1.4)
    b.emit.label_fit((xr - 0.01, 9.5, 2.55), 1.3, "eq_fuel", (-1, 0, 0), up=(0, 0, 1))
    # the crew's benches by the entrance and a notice board
    place(b, 4.2, 0.4, 90, F.bench, 2.2, 0.42, 0.46, FABRIC_GREY)
    place(b, 27.8, 0.4, 90, F.bench, 2.2, 0.42, 0.46, FABRIC_GREY)
    b.emit.label_fit((10.5, WF + 0.002, 2.1), 1.1, "eq_roster", (0, 1, 0))
    # the walls and the ceiling are working surfaces too
    dress_wall(b, "near", L, D, H_, 0.5, 12.5, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 19.5, 31.5, 2, accent="security", accent_dim="security_dim", kinds=("plain", "conduits", "vent", "screen"))
    dress_wall(b, "far", L, D, H_, 0.5, 5.4, 3, accent="security", accent_dim="security_dim", kinds=("panelboard", "conduits", "vent"))
    dress_wall(b, "far", L, D, H_, 26.6, 31.5, 4, accent="security", accent_dim="security_dim", kinds=("panelboard", "vent", "conduits"))
    dress_wall(b, "left", L, D, H_, 4.5, 15.5, 5, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "conduits", "hatch"))
    ceiling_services(b, L, D, H_, [(3.2, "duct"), (14.4, "tray")], 1.0, 31.0, 5)
    ceiling_panels(b, L, D, H_, 6, 3, "white_cool", 1.6, 1.3, 0.6, LAMP_HOT)
    for cx in KESTREL_X:
        for sx in (-2.6, 2.6):
            lamp_strip(b.emit, (cx + sx, 2.6, H_ - 0.06), (cx + sx, 13.8, H_ - 0.06), 0.16, 0.02, "white_cool", LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- barracks
BUNK_X, BUNK_Y = SPEC.BUNK_X, SPEC.BUNK_Y                    # the eight double bunks along the far wall (ship_spec.py's sleeping places follow them)


def barracks(name: str = "SM_SHIP_Barracks"):
    """24 x 16 x 3.4: a squad bay for sixteen. Eight double bunks along the far wall, head to the wall, each with its wardrobe beside it and its footlocker at the foot; a
    corner with a screen and two sofas on the left, a long table with benches in the middle, the exercise corner against the right wall, the tall lockers and the boot rack
    along the entrance wall. The light is kept low (a warm cove and a few panels): somebody is always asleep."""
    spec, L, D, H_ = _dims("barracks")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_warm", lo=CRATE_OLIVE, hi=CRATE_GREY))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    blankets = (FABRIC_GREY, FABRIC_NAVY, FABRIC_SAND, FABRIC_RUST)
    for k, x in enumerate(BUNK_X):
        place(b, x, BUNK_Y, -90, G.bunk_bed, 2.05, 0.95, 2, blankets[k % 4], k)
        place(b, x - 0.975, yf - 0.275, -90, G.wardrobe, 0.9, 0.55, 2.0)
        place(b, x, BUNK_Y - 1.025 - 0.27, -90, K5.footlocker)
        b.emit.label_fit((x - 0.975, yf - 0.002, 2.25), 0.5, "eq_kit", (0, -1, 0))
    # the left corner: the squad's screen on the wall, two sofas facing it, a low table and a rug
    place(b, xl, 7.4, 0, F.wall_screen, 2.6, 1.4, "scr_news", z=1.85)
    place(b, 3.9, 6.2, 180, F.sofa, 2.0, FABRIC_GREY)
    place(b, 3.9, 8.6, 180, F.sofa, 2.0, FABRIC_GREY)
    place(b, xl, 4.2, 0, F.wall_screen, 0.9, 0.6, "pict_shuttle", z=1.9)
    place(b, xl, 10.6, 0, F.wall_screen, 0.9, 0.6, "scr_star", z=1.9)
    place(b, 2.3, 7.4, 0, F.low_table, 1.2, 0.6, 0.38, WOOD)
    place(b, 3.0, 7.4, 0, G.rug, 3.4, 4.6, FABRIC_NAVY, FABRIC_SAND)
    place(b, 3.2, 11.1, 0, F.potted_plant, 1.2, 3)
    # the table in the middle: eight places, a card game, mugs, a thermos
    place(b, 16.5, 8.4, 0, F.table, 3.2, 0.9, 0.74, LAMINATE, TRIM, False)
    place(b, 16.5, 7.35, 90, F.bench, 3.0, 0.36, 0.46, FABRIC_GREY)
    place(b, 16.5, 9.45, -90, F.bench, 3.0, 0.36, 0.46, FABRIC_GREY)
    for k, (dx, dy) in enumerate(((-1.0, -0.2), (-0.3, 0.25), (0.6, -0.25), (1.2, 0.15))):
        with b.at(T(16.5 + dx, 8.4 + dy, 0.74)):
            b.soft.cyl((0, 0, 0), (0, 0, 0.1), 0.04, [PAINT_RED, CRATE_BLUE, BEDDING, CRATE_OLIVE][k], seg=8)
    with b.at(T(16.5, 8.4, 0.74)):
        b.soft.box((-0.12, -0.08, 0.0), (0.0, 0.08, 0.008), BEDDING)
        b.soft.cyl((0.35, 0.3, 0.0), (0.35, 0.3, 0.26), 0.05, STEEL, seg=10)
    # the exercise corner against the right wall (its rack on the wall side)
    place(b, 21.9, 7.0, 180, K5.training_corner, 3.4)
    # the entrance wall: the boot rack, the tall lockers, the squad roster, a banner
    place(b, 4.4, WF + 0.22, 90, K5.boot_rack, 6)
    place(b, 23.2, WF + 0.27, 90, F.locker_row, 8, 0.5, 2.0, 0.5, COMPOSITE)
    b.emit.label_fit((12.4, WF + 0.002, 1.9), 1.0, "eq_roster", (0, 1, 0))
    b.soft.box((6.3, WF, 0.9), (7.4, WF + 0.02, 2.7), FABRIC_RUST)
    b.soft.box((6.3, WF + 0.02, 2.6), (7.4, WF + 0.03, 2.7), CRATE_ORANGE)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 8.4, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 8.9, 1.4)
    dress_wall(b, "near", L, D, H_, 11.6, 18.6, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "left", L, D, H_, 10.0, 13.0, 2, accent="security", accent_dim="security_dim", kinds=("plain", "vent"))
    dress_wall(b, "right", L, D, H_, 1.0, 5.0, 3, accent="security", accent_dim="security_dim", kinds=("plain", "conduits"))
    dress_wall(b, "right", L, D, H_, 9.0, 13.0, 4, accent="security", accent_dim="security_dim", kinds=("panelboard", "vent"))
    ceiling_services(b, L, D, H_, [(11.4, "tray")], 1.0, 23.0, 2)
    ceiling_panels(b, L, D, H_, 4, 2, "white_warm", 2.0, 1.0, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- kit room
def kit_room(name: str = "SM_SHIP_KitRoom"):
    """16 x 16 x 3.4: where the marines keep and check their battle dress. Six armour bays and a helmet shelf along the left wall, two rows of personal lockers on the far wall
    with benches in front of them, a rack of kit bags on the right wall, the armourer's bench by the door."""
    spec, L, D, H_ = _dims("kit_room")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_cool", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(6):
        place(b, xl + 0.34, 3.4 + k * 1.05, 0, K5.armour_bay, COMPOSITE if k % 2 else CRATE_GREY)
    b.emit.label_fit((xl + 0.002, 6.0, 2.5), 2.0, "eq_armour", (1, 0, 0))
    place(b, xl + 0.3, 11.6, 0, K5.helmet_shelf, 2.6, 3, 1)
    for x0 in (1.4, 8.6):
        place(b, x0, yf - 0.28, -90, F.locker_row, 6, 0.5, 2.0, 0.55, CRATE_GREY)
    for x0, k in ((3.0, 0), (10.2, 1)):
        place(b, x0, 12.9, 90, F.bench, 3.0, 0.4, 0.46, FABRIC_GREY)
        place(b, x0 - 1.2, 12.9, 90 + 20 * k, K.duffel, 0.8, 0.2, FABRIC_SAND)
        place(b, x0 + 1.15, 12.95, 90 - 10 * k, K.duffel, 0.7, 0.19, FABRIC_GREY)
    # the checking table in the middle: armour plates, a helmet and gloves laid out, stools on both sides
    place(b, 8.0, 7.2, 0, F.table, 3.0, 1.0, 0.8, STEEL, TRIM, False)
    with b.at(T(8.0, 7.2, 0.8)):
        for k, dx in enumerate((-1.0, -0.2, 0.7)):
            b.soft.box((dx - 0.2, -0.28, 0.0), (dx + 0.2, 0.2, 0.05), [CRATE_OLIVE, CRATE_GREY, CRATE_OLIVE][k])
        b.soft.sphere((1.15, 0.1, 0.14), 0.14, CRATE_OLIVE, seg=12, rings=8, squash=(1.1, 1.0, 0.95))
        b.soft.box((-0.3, 0.25, 0.0), (0.0, 0.4, 0.03), RUBBER)
    for x in (7.0, 8.0, 9.0):
        place(b, x, 6.3, 0, F.stool, 0.19, 0.62, FABRIC_GREY)
        place(b, x, 8.1, 0, F.stool, 0.19, 0.62, FABRIC_GREY)
    place(b, xr - 0.45, 6.5, 180, F.rack, 3.0, 0.9, 2.6, 4, 12, 0.8, [CRATE_OLIVE, CRATE_GREY])
    place(b, xr - 0.45, 10.5, 180, F.rack, 3.0, 0.9, 2.6, 4, 15, 0.8, [CRATE_GREY, CRATE_OLIVE])
    place(b, 3.0, 0.7, 90, G.workbench, 2.4, 0.8, 0.95, True)
    place(b, 3.0, 0.7, 90, F.monitor, 0.5, 0.3, "scr_lab", False, z=0.95)
    place(b, 9.8, 1.0, 90, F.bench, 2.4, 0.4, 0.46, FABRIC_GREY)
    place(b, 12.0, 0.5, 90, F.crate, 0.8, 0.55, 0.45, CRATE_OLIVE, "eq_ammo", False)
    b.emit.label_fit((9.0, WF + 0.002, 2.0), 1.0, "eq_kit", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 11.8, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 12.6, 0.0)
    dress_wall(b, "near", L, D, H_, 0.5, 4.0, 5, accent="security", accent_dim="security_dim", kinds=("plain", "vent"))
    dress_wall(b, "near", L, D, H_, 7.5, 15.0, 6, accent="security", accent_dim="security_dim", kinds=("plain", "panelboard", "safety"))
    dress_wall(b, "right", L, D, H_, 1.0, 4.4, 7, accent="security", accent_dim="security_dim", kinds=("vent", "conduits"))
    ceiling_services(b, L, D, H_, [(8.0, "duct")], 1.0, 15.0, 3)
    ceiling_panels(b, L, D, H_, 3, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- firing range
LANE_Y, BOOTH_X = SPEC.RANGE_LANE_Y, SPEC.RANGE_BOOTH_X      # the six lanes' centres and the shooters' place (the counters stand 0.5 m in front of it)


def firing_range(name: str = "SM_SHIP_FiringRange"):
    """40 x 16 x 3.6: six lanes down the length of the room, 33 m from the firing line to the back stop. The shooters' booths (a counter, dividers, a screen) stand at the left
    end with the gear area behind them; the lanes run down the room under angled steel baffles to silhouette targets at 21 m and 31 m and the armour funnel of the back stop;
    a safety fence of steel bars along the entrance side with a gate to the target end; the range officer's desk, the ammunition issue counter and the benches stand on the near
    side of the fence, where the door is."""
    spec, L, D, H_ = _dims("firing_range")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    y_a, y_b = LANE_Y[0] - 1.0, LANE_Y[-1] + 1.0
    for k, y in enumerate(LANE_Y):
        place(b, BOOTH_X, y, 0, K5.range_booth, 2.0, k == 0, True, f"eq_lane{k + 1}")
        place(b, 26.0, y, 180, K5.target_stand, 0)
        place(b, 36.0, y, 180, K5.target_stand, 1 if k % 2 else 0)
        for x in (26.0, 36.0):                                                                                    # a spot over each target
            b.body.box((x - 0.2, y - 0.2, H_ - 0.45), (x + 0.2, y + 0.2, H_ - 0.38), STRUCT)
            b.emit.lamp_box((x - 0.16, y - 0.16, H_ - 0.455), (x + 0.16, y + 0.16, H_ - 0.45), "white_cool", LAMP_HOT)
    for k in range(1, 6):                                                                                         # the lane lines and the distance bands on the floor
        y = LANE_Y[0] - 1.0 + 2.0 * k
        lamp_strip(b.emit, (6.8, y, 0.004), (37.8, y, 0.004), 0.04, 0.004, "white_dim", LAMP_DIM)
    for x in (11.0, 16.0, 21.0, 26.0, 31.0, 36.0):
        lamp_strip(b.emit, (x, y_a + 0.1, 0.004), (x, y_b - 0.1, 0.004), 0.06, 0.004, "amber_dim", LAMP_DIM)
    K5.baffle_row(b, 8.5, 37.0, y_a, y_b, H_, 3.0, 24.0)
    K5.bullet_trap(b, xr, y_a, y_b, H_)
    # the safety fence along the entrance side with a gate to the target end, and its low wall
    fence_y = y_a - 0.25
    gates = ((12.4, 14.2), (33.8, 35.6))                                                                           # (the first is on the way from the door to the middle of the room)
    xs = [(3.4, 7.4), (7.4, gates[0][0]), (gates[0][1], 17.4), (17.4, 21.4), (21.4, 25.4), (25.4, 29.4), (29.4, gates[1][0]), (gates[1][1], xr - 0.1)]
    for x0, x1 in xs:
        with b.at(frame((x0 + x1) / 2, fence_y, 0.0, 90.0)):
            G.cage_wall(b, x1 - x0, 2.3)
    for g0, g1 in gates:                                                                                          # a gate: red posts, a header and its sign on both faces
        for sx in (g0, g1):
            b.body.box((sx - 0.05, fence_y - 0.05, 0.0), (sx + 0.05, fence_y + 0.05, 2.4), PAINT_RED)
        b.body.box((g0 - 0.05, fence_y - 0.05, 2.3), (g1 + 0.05, fence_y + 0.05, 2.4), PAINT_RED)
        b.emit.label_fit(((g0 + g1) / 2, fence_y - 0.07, 2.0), 1.2, "eq_range", (0, -1, 0))
        b.emit.label_fit(((g0 + g1) / 2, fence_y + 0.07, 2.0), 1.2, "eq_range", (0, 1, 0))
    # the gear area behind the booths: benches with kit, the clearing barrel, hearing protection, a first aid box
    for y in (5.5, 9.5, 13.5):
        place(b, xl + 0.4, y, 0, F.bench, 2.6, 0.4, 0.46, FABRIC_GREY)
    place(b, 1.2, 13.4, 120, K.duffel, 0.8, 0.2, FABRIC_SAND)
    place(b, 1.4, 5.8, 70, K.duffel, 0.7, 0.19, FABRIC_GREY)
    place(b, 1.8, 7.7, 0, F.barrel, 0.28, 0.8, CRATE_OLIVE)
    b.emit.label_fit((xl + 0.002, 7.7, 2.0), 1.0, "eq_clear", (1, 0, 0))
    b.emit.label_fit((xl + 0.002, 11.4, 2.0), 1.4, "eq_range", (1, 0, 0))
    place(b, xl, 3.2, 0, F.wall_screen, 1.6, 0.9, "scr_sched", z=1.6)
    # the near side: the range officer's desk facing the lanes, the ammunition issue counter, a rack of ear defenders
    place(b, 15.0, 2.0, 90, F.desk, 1.8, 0.7, 0.76, STEEL, False)
    place(b, 15.0, 2.2, -90, F.monitor, 0.5, 0.3, "scr_tac", False, z=0.76)
    place(b, 16.0, 2.2, -90, F.monitor, 0.5, 0.3, "scr_data", False, z=0.76)
    place(b, 15.0, 1.2, 90, H.chair_op, FABRIC_RUST)
    place(b, 24.0, 0.45, 90, F.counter, 3.0, 0.6, 1.05, STEEL, COMPOSITE, True, False)
    b.emit.label_fit((24.0, WF + 0.002, 2.1), 1.4, "eq_ammo", (0, 1, 0))
    b.emit.label_fit((12.6, WF + 0.002, 2.1), 1.5, "eq_range", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 8.2, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 7.4, 0.0)
    dress_wall(b, "near", L, D, H_, 0.5, 8.5, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 19.0, 22.0, 2, accent="security", accent_dim="security_dim", kinds=("plain", "conduits"))
    dress_wall(b, "near", L, D, H_, 27.0, 39.0, 3, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "panelboard", "screen"))
    dress_wall(b, "far", L, D, H_, 8.0, 38.0, 4, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "panelboard", "conduits", "safety"))
    ceiling_panels(b, L, D, H_, 3, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    for x in (13.0, 19.0):
        for y in (6.5, 12.5):
            F.ceiling_light_panel(b, x - 0.7, x + 0.7, y - 0.3, y + 0.3, H_ - 0.05, "white_cool", LAMP_HOT)
    return b.build(name)
