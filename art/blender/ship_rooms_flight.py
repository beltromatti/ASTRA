"""ASN Aquila interior kit: the rooms of the flight and logistics decks (NAVE-2, Decks 9 and 10) — Flight Operations (the flight control room), the pilots' ready room, the aircraft
workshop, the munitions magazine and the cargo hold. Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture4 as K
import ship_furniture5 as K5
import ship_furniture6 as K6
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY,
                      LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, WOOD, SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_label, wall_matrix)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "flight_dim", cove: str = "white_cool", floor: str = DECK, wain: float = 1.2, lo: str = COMPOSITE, hi: str = COMPOSITE) -> Style:
    return Style(floor=floor, floor_mode="plates", wall_lo=lo, wall_hi=hi, wain_h=wain, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- flight operations
def flight_ops(name: str = "SM_SHIP_FlightOps"):
    """24 x 16 x 3.6: the room that runs the flight deck. A wall of three status boards on the far wall (the deck, the launch queue, the weather and the wave), two rows of
    controllers' consoles facing it with a free aisle in the middle for the Air Boss and the CAG, a holographic plot table in front of the boards, camera feeds on the left wall,
    the log shelves and a coffee corner on the right."""
    spec, L, D, H_ = _dims("flight_ops")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style())
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((5.0, "scr_tac"), (12.0, "scr_ship"), (19.0, "scr_map")):
        place(b, x, yf - 0.02, -90, H.wall_rack_panel, 6.0, 2.5, tile, "flight")
    b.emit.label_fit((12.0, yf - 0.01, 3.2), 3.2, "st_flight", (0, -1, 0))
    b.emit.lamp_box((1.5, yf - 0.08, 0.5), (L - 1.5, yf - 0.05, 0.54), "flight_dim", LAMP_DIM)
    tiles = ["scr_ship", "scr_data", "scr_map", "scr_tac"]
    for k, x in enumerate((4.5, 8.0, 16.0, 19.5)):                                                                   # the first row (high consoles with screens)
        place(b, x, 10.4, -90, H.work_console, 3.0, "flight", 2, tiles[k:] + tiles[:k], True, True)
        place(b, x, 9.15, 90, H.chair_op, FABRIC_NAVY)
    for k, x in enumerate((3.8, 7.4, 16.6, 20.2)):                                                                   # the second row (low ones: one can see over them)
        place(b, x, 6.0, -90, H.work_console, 3.0, "flight", 2, tiles[k:] + tiles[:k], False, False)
        place(b, x, 4.75, 90, H.chair_op, FABRIC_NAVY)
    place(b, 12.0, 12.8, 0, G.holo_table, 1.0, 0.95)
    for dx in (-1.9, 1.9):                                                                                           # a pair of stools by the plot table for the Air Boss and the CAG
        place(b, 12.0 + dx, 12.8, 0, F.stool, 0.19, 0.72, FABRIC_RUST)
    # left wall: camera feeds; right wall: log shelves, the coffee corner
    for y, tile in ((5.0, "scr_map"), (9.0, "scr_ship"), (13.0, "scr_tac")):
        place(b, xl, y, 0, F.wall_screen, 2.6, 1.5, tile, z=1.9)
    b.emit.label_fit((xl + 0.002, 7.0, 3.0), 1.4, "eq_comm", (1, 0, 0))
    place(b, xr - 0.2, 10.4, 180, F.shelf, 2.4, 0.34, 2.0, 5)
    place(b, xr - 0.4, 6.4, 180, F.counter, 2.4, 0.65, 0.92, STEEL, COMPOSITE, True, True)
    place(b, xr - 0.45, 5.6, 180, G.coffee_machine)
    on_wall(b, "right", L, D, W.first_aid, b.body, D - 3.0, 1.4)
    on_wall(b, "right", L, D, W.extinguisher, b.body, D - 3.8, 0.0)
    b.emit.label_fit((12.4, WF + 0.002, 2.0), 1.0, "eq_watch", (0, 1, 0))
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="flight", accent_dim="flight_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 13.0, 23.5, 2, accent="flight", accent_dim="flight_dim", kinds=("plain", "conduits", "vent", "screen"))
    ceiling_services(b, L, D, H_, [(2.0, "tray"), (14.8, "tray")], 1.0, 23.0, 6)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- pilots' ready room
def pilot_ready(name: str = "SM_SHIP_PilotReady"):
    """24 x 16 x 3.6: the pilots' room before a sortie. A briefing screen and a podium at the far end, three rows of armchairs in two blocks with an aisle between, flight-suit
    lockers and a helmet shelf on the left wall, a lounge corner with a sofa pair, a screen and a coffee counter on the right, the squadron board by the door."""
    spec, L, D, H_ = _dims("pilot_ready")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("flight_dim", "white_warm", lo=CRATE_BLUE, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 12.0, yf - 0.02, -90, F.wall_screen, 6.4, 2.6, "scr_tac", z=2.0)
    place(b, 12.0, yf - 1.6, 90, F.desk, 1.4, 0.6, 1.05, STEEL, False)
    place(b, 12.0, yf - 1.2, -90, F.monitor, 0.5, 0.3, "scr_data", False, z=1.05)
    for r, y in enumerate((5.2, 7.2, 9.2)):
        for k, x in enumerate((4.0, 5.7, 7.4, 9.1, 14.9, 16.6, 18.3, 20.0)):
            place(b, x, y, 90, F.armchair, FABRIC_NAVY if (k + r) % 3 else FABRIC_GREY)
    # left wall: flight-suit lockers and the helmets
    place(b, xl + 0.35, 4.0, 0, F.locker_row, 8, 0.5, 2.0, 0.55, CRATE_GREY)
    place(b, xl + 0.3, 11.6, 0, K5.helmet_shelf, 2.6, 3, 2)
    b.emit.label_fit((xl + 0.002, 8.6, 2.5), 1.4, "eq_kit", (1, 0, 0))
    # right wall: the lounge corner and the coffee counter
    place(b, xr - 0.5, 10.4, 180, F.sofa, 2.0, FABRIC_RUST)
    place(b, xr - 0.5, 13.2, 180, F.sofa, 2.0, FABRIC_RUST)
    place(b, xr - 1.8, 11.8, 0, F.low_table, 1.2, 0.6, 0.38, WOOD)
    place(b, xr - 0.02, 11.8, 180, F.wall_screen, 2.4, 1.3, "scr_news", z=1.9)
    place(b, xr - 0.4, 6.8, 180, F.counter, 2.0, 0.65, 0.92, STEEL, COMPOSITE, True, True)
    place(b, xr - 0.45, 6.4, 180, G.coffee_machine)
    place(b, xr - 0.02, 4.0, 180, F.wall_screen, 2.0, 1.2, "scr_sched", z=1.8)
    b.emit.label_fit((12.4, WF + 0.002, 1.9), 1.2, "eq_roster", (0, 1, 0))
    place(b, 6.5, WF + 0.22, 90, K5.boot_rack, 4)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 17.4, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 18.2, 0.0)
    dress_wall(b, "near", L, D, H_, 13.0, 17.0, 1, accent="flight", accent_dim="flight_dim", kinds=("plain", "vent", "safety"))
    dress_wall(b, "near", L, D, H_, 19.0, 23.5, 2, accent="flight", accent_dim="flight_dim", kinds=("plain", "panelboard"))
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.8, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- aircraft workshop
def aircraft_shop(name: str = "SM_SHIP_AircraftShop"):
    """28 x 16 x 3.7: where the Air Group's fighters are repaired. A fighter's nose section on its trolley under the gantry in the middle of the right half, a turbofan on its stand,
    a wing on a jig and a landing leg on a stand; avionics benches along the left wall, the tool wall and the parts racks on the far wall, benches and a rolling chest by the door."""
    spec, L, D, H_ = _dims("aircraft_shop")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("flight_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 19.5, 8.5, 0, K6.fighter_nose)
    place(b, 6.6, 11.8, 0, K6.engine_stand)
    place(b, 24.8, 5.0, 90, K6.wing_jig)
    place(b, 24.6, 11.8, 0, K6.landing_strut)
    with b.at(T(1.0, 0.0, 0.0)):                                                                                       # the gantry over the nose and the engine
        G.overhead_rail(b, 26.0, 8.5, H_ - 0.45, 18.5)
        G.overhead_rail(b, 26.0, 11.8, H_ - 0.45, 5.6)
    for y in (8.5, 11.8):
        for x in (3.0, 9.0, 15.0, 21.0, 26.0):
            b.soft.cyl((x, y, H_ - 0.45), (x, y, H_), 0.03, TRIM, seg=6)
    for y in (3.0, 6.2):
        place(b, xl + 0.5, y, 0, K6.avionics_bench, 2.4)
    place(b, xl + 0.4, 9.0, 0, F.locker_row, 4, 0.5, 2.0, 0.55, PAINT_RED)
    b.emit.label_fit((xl + 0.002, 10.0, 2.45), 1.2, "eq_gas", (1, 0, 0))
    place(b, 12.0, yf - 0.02, -90, G.tool_wall, 3.4, 1.5, 6)
    place(b, 5.0, yf - 0.45, -90, F.rack, 3.0, 0.9, 2.6, 4, 12, 0.8, [CRATE_GREY, CRATE_OLIVE])
    place(b, 17.0, yf - 0.45, -90, F.rack, 3.0, 0.9, 2.6, 4, 14, 0.8, [CRATE_OLIVE, CRATE_ORANGE])
    place(b, 21.5, yf - 0.45, -90, F.rack, 3.0, 0.9, 2.6, 4, 15, 0.8, [CRATE_GREY, CRATE_BLUE])
    place(b, 10.0, 6.6, 0, G.workbench, 2.4, 0.8, 0.95, True)
    place(b, 8.5, 6.6, 180, K.tool_chest, 0.8, 0.5, 1.0)
    place(b, 8.4, 3.0, 90, G.workbench, 3.0, 0.8, 0.95, True)
    place(b, 14.0, 3.0, 90, G.parts_bins, 2.4, 1.9, 0.5, 4)
    place(b, 26.4, 8.4, 180, G.parts_bins, 2.4, 1.9, 0.5, 5)
    on_wall(b, "right", L, D, W.extinguisher, b.body, D - 14.0, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 17.4, 1.4)
    dress_wall(b, "near", L, D, H_, 13.0, 27.5, 1, accent="flight", accent_dim="flight_dim", kinds=("plain", "vent", "panelboard", "safety", "conduits"))
    dress_wall(b, "left", L, D, H_, 11.0, 15.5, 2, accent="flight", accent_dim="flight_dim", kinds=("vent", "plain"))
    ceiling_panels(b, L, D, H_, 5, 3, "white_cool", 1.6, 1.3, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- magazine
def magazine(name: str = "SM_SHIP_Magazine"):
    """24 x 16 x 3.6: the munitions store of the air group and the ship's guns. Two lineups of missile racks (three tiers of two) with an aisle between, railgun slugs standing in
    racks along the left wall, the head of the munitions hoist on the right under a rail with a trolley hoist, a sprinkler main across the ceiling, the magazine control desk by
    the door and an orange-and-black border round every rack."""
    spec, L, D, H_ = _dims("magazine")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("security_dim", "white_warm", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    rack_x = [3.35 + 3.1 * k for k in range(7)]
    for x in rack_x:                                                                                                  # the far lineup: the missiles lie along the wall, seen from the aisle
        place(b, x, yf - 0.5, 0, K6.missile_rack, 3, 2, 2.6)
    for x in (rack_x[0], rack_x[1], rack_x[5], rack_x[6]):                                                            # the second lineup, leaving the middle free
        place(b, x, 10.6, 0, K6.missile_rack, 3, 2, 2.6)
    for k, y in enumerate((3.4, 5.6, 7.8)):
        place(b, xl + 0.4, y, 0, K6.shell_rack, 2.0, 3, 1.5)
    place(b, 12.0, 6.0, 0, K6.hoist_platform, 1.9)
    with b.at(T(1.0, 0.0, 0.0)):
        G.overhead_rail(b, 22.0, 6.0, H_ - 0.5, 11.0)
    for x in (3.0, 8.0, 13.0, 18.0, 22.0):
        b.soft.cyl((x, 6.0, H_ - 0.5), (x, 6.0, H_), 0.03, TRIM, seg=6)
    for y in (3.2, 8.4):
        K6.sprinkler_line(b, (1.0, y, H_ - 0.28), (L - 1.0, y, H_ - 0.28))
    b.emit.label_fit((xr - 0.002, 8.0, 2.3), 1.6, "eq_ammo", (-1, 0, 0))
    place(b, 20.0, 5.0, 90, F.desk, 1.6, 0.7, 0.8, STEEL, False)
    place(b, 20.0, 5.2, -90, F.monitor, 0.5, 0.3, "scr_sched", False, z=0.8)
    place(b, 20.0, 4.1, 90, H.chair_op, FABRIC_RUST)
    for x in rack_x:
        b.emit.label((x, 13.15, 0.006), 2.9, 0.1, (0, 0, 1), "hazard_h", up=(1, 0, 0))
    on_wall(b, "right", L, D, W.extinguisher, b.body, D - 3.0, 0.0)
    on_wall(b, "right", L, D, W.first_aid, b.body, D - 3.8, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "safety", "panelboard"))
    dress_wall(b, "near", L, D, H_, 13.0, 23.5, 2, accent="security", accent_dim="security_dim", kinds=("plain", "safety", "conduits"))
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- cargo hold
def cargo_hold(name: str = "SM_SHIP_CargoHold"):
    """32 x 16 x 3.7: containers stacked along the far wall, two lanes of pallets with crates down the middle (the way from the door to the middle of the room stays free), a
    forklift and a pallet truck parked, the floor hatch of the cargo lift on the right, tall racks along the side walls, a gantry rail down each lane with a hoist, yellow lane lines."""
    spec, L, D, H_ = _dims("cargo_hold")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("flight_dim", "white_warm", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    mats = [CRATE_ORANGE, CRATE_GREY, CRATE_BLUE, CRATE_GREY, CRATE_ORANGE, CRATE_OLIVE, CRATE_GREY, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY]
    for k in range(9):                                                                                                # containers along the far wall, door ends towards the room
        x = 2.0 + k * 3.35
        place(b, x, yf - 0.8, -90, K6.cargo_container, 3.0, 1.5, 1.6, mats[k], "eq_stores")
        if k % 3 != 1:
            place(b, x, yf - 0.8, -90, K6.cargo_container, 3.0, 1.5, 1.6, mats[(k + 4) % 10], "eq_stores", z=1.6)
    for k, (x, y) in enumerate(((5.0, 7.0), (5.0, 9.4), (9.0, 7.0), (23.0, 7.0), (23.0, 9.4), (27.0, 7.0), (27.0, 9.4))):    # pallets with stacked crates
        place(b, x, y, 90 * (k % 2), F.pallet, 1.2, 0.8)
        for j in range(2 + k % 2):
            place(b, x, y, 90 * (k % 2) + 4 * j, F.crate, 0.9, 0.62, 0.5, mats[(k + j) % 10], None, False, z=0.145 + 0.5 * j)
    place(b, 21.0, 4.0, 180, K6.forklift)
    place(b, 12.5, 12.0, 90, K6.pallet_truck)
    place(b, 28.5, 4.0, 0, K6.hoist_platform, 1.9)
    for y in (4.6, 11.6):
        with b.at(T(1.0, 0.0, 0.0)):
            G.overhead_rail(b, 30.0, y, H_ - 0.45, 9.0 if y < 8 else 24.0)
        for x in (3.0, 9.0, 15.0, 21.0, 27.0, 31.0):
            b.soft.cyl((x, y, H_ - 0.45), (x, y, H_), 0.03, TRIM, seg=6)
    place(b, xl + 0.45, 3.0, 0, F.rack, 3.0, 0.9, 2.6, 4, 12, 0.8, [CRATE_GREY, CRATE_OLIVE])
    place(b, xl + 0.45, 8.0, 0, F.rack, 3.0, 0.9, 2.6, 4, 13, 0.8, [CRATE_OLIVE, CRATE_BLUE])
    place(b, xr - 0.45, 12.0, 180, F.rack, 3.0, 0.9, 2.6, 4, 14, 0.8, [CRATE_GREY, CRATE_ORANGE])
    for x in (13.0, 19.0):                                                                                            # lane lines
        lamp_strip(b.emit, (x, 1.5, 0.004), (x, 11.8, 0.004), 0.08, 0.004, "amber_dim", LAMP_DIM)
    for y in (3.2, 6.0, 11.4):
        lamp_strip(b.emit, (1.5, y, 0.004), (L - 1.5, y, 0.004), 0.05, 0.004, "amber_dim", LAMP_DIM)
    b.emit.label_fit((16.0, WF + 0.002, 2.4), 1.6, "eq_stores", (0, 1, 0))
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 7.4, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 8.0, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="flight", accent_dim="flight_dim", kinds=("plain", "vent", "safety", "panelboard"))
    dress_wall(b, "near", L, D, H_, 13.0, 31.5, 2, accent="flight", accent_dim="flight_dim", kinds=("plain", "conduits", "vent", "safety"))
    ceiling_services(b, L, D, H_, [(2.8, "duct"), (9.0, "tray")], 1.0, 31.0, 7)
    ceiling_panels(b, L, D, H_, 6, 3, "white_warm", 1.6, 1.3, 0.6, LAMP_HOT)
    return b.build(name)
