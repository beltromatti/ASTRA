"""ASN Aquila interior kit (NAVE-3): the plants that keep the ship alive and thinking — the atmosphere plant, the water reclamation plant, the waste processing plant, the computer core,
the auxiliary power plant and the damage-control central. Frames and sizes: ship_rooms.py / ship_spec.py / ship_spec3.py."""
from __future__ import annotations

import math

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture7 as H7
import ship_furniture9 as N
import ship_spec as SPEC
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_RUST, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL,
                      STRUCT, TRIM, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, place, wall_label
from ship_rooms_engineering import (air_handler, compressor, heat_exchanger, horizontal_tank, pipe_rack, skid, valve_wheel)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "engineering_dim", cove: str = "white_warm") -> Style:
    return Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# --------------------------------------------------------------------------------------------------------------------------------------------------------- atmosphere plant
def air_plant(name: str = "SM_SHIP_AirPlant"):
    """24 x 16 x 3.7: where the air is made — three CO2 scrubber columns joined by a duct, two oxygen electrolyser stacks and an air handler along the far wall, a compressor, two oxygen
    tanks, the control console by the right wall, pipe racks overhead."""
    spec, L, D, H_ = _dims("air_plant")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("engineering_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (3.5, 6.5, 9.5):
        place(b, x, 5.6, 0, N.scrubber_column, 0.55, 3.0)
    H.duct_run(b, (3.5, 5.6, 3.35), (9.5, 5.6, 3.35), 0.5, 0.3, STEEL, 1.4)
    for x in (13.5, 16.5):
        place(b, x, yf - 0.6, -90, N.electrolyser, 1.8, 0.8, 2.1)
    place(b, 4.4, yf - 0.7, -90, air_handler, 2.6, 1.2, 1.9)
    place(b, 9.0, yf - 0.7, -90, air_handler, 2.6, 1.2, 1.9)
    place(b, 13.5, 8.2, 0, compressor, 2.4, "engineering")
    for x in (20.4, 22.4):
        place(b, x, 11.6, 0, H.tank_v, 0.9, 2.9, STEEL, "science", "eq_oxygen")
    H.pipe_bundle(b, (20.4, 11.6, 0.5), (22.4, 11.6, 0.5), 2, 0.06, 0.03, (0, 1, 0), None, 2.0)
    place(b, 21.6, 3.0, 180, H.work_console, 2.4, "engineering", 2, None, False, True)
    place(b, 22.8, 3.0, 180, H.chair_op, FABRIC_RUST)
    pipe_rack(b, 12.0, 1.8, 7.0, 2.3, 4, 5)
    place(b, xl + 0.35, 9.0, 0, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 5, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "panelboard", "safety"))
    wall_label(b, 3.0, WF + 0.02, 2.5, (0, 1, 0), "eq_scrub", 0.8)
    ceiling_services(b, L, D, H_, [(3.4, "duct"), (9.0, "pipes")], 1.0, 23.0, 7)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ water reclamation plant
def water_plant(name: str = "SM_SHIP_WaterPlant"):
    """24 x 16 x 3.7: three vertical water tanks, two filtration columns, a heat exchanger and three pump sets on skids, a manifold of hand valves along the far wall, a sampling bench
    and the control desk; blue bands on everything that carries drinking water."""
    spec, L, D, H_ = _dims("water_plant")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("ice_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (3.4, 6.0, 8.6):
        place(b, x, 11.8, 0, H.tank_v, 0.95, 3.0, STEEL, "science", "eq_potable")
    for x in (13.0, 15.6):
        place(b, x, 11.8, 0, N.scrubber_column, 0.5, 2.8)
    place(b, 20.4, 8.0, 0, heat_exchanger, 3.6, 0.58, "engineering")
    for k, x in enumerate((4.0, 7.0, 10.0)):
        place(b, x, 6.6, 90, H.pump_set, 1.6, "engineering")
    b.body.cyl((3.0, yf - 0.55, 2.3), (L - 2.0, yf - 0.55, 2.3), 0.12, STEEL, seg=14)
    for k, x in enumerate((6.0, 9.0, 12.0, 15.0, 18.0, 21.0)):
        b.body.cyl((x, yf - 0.55, 2.3), (x, yf - 0.55, 1.4), 0.05, TRIM, seg=8)
        place(b, x, yf - 0.58, -90, valve_wheel, 0.17, CRATE_BLUE)
    place(b, 15.0, 3.6, 90, G.workbench, 3.0, 0.8, 0.95, False)
    place(b, 15.0, 2.6, -90, F.stool, 0.19, 0.62)
    place(b, 21.6, 3.0, 180, H.work_console, 2.4, "engineering", 2, None, False, True)
    place(b, 22.8, 3.0, 180, H.chair_op, FABRIC_RUST)
    pipe_rack(b, 12.0, 1.8, 8.0, 2.3, 3, 9)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 3, accent="ice", accent_dim="ice_dim", kinds=("plain", "vent", "panelboard", "hydrant"))
    wall_label(b, 3.0, WF + 0.02, 2.5, (0, 1, 0), "eq_potable", 0.8)
    ceiling_services(b, L, D, H_, [(3.4, "pipes"), (9.0, "tray")], 1.0, 23.0, 3)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------- waste processing
def waste_plant(name: str = "SM_SHIP_WastePlant"):
    """24 x 16 x 3.7: the end of the loop — a sorting conveyor from the hatch to a compactor and a reclaimer (a furnace and its stack), bins by material, a sorting bench, a hose and
    a drain, green and amber light."""
    spec, L, D, H_ = _dims("waste_plant")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("green_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    b.body.box((2.0, yf - 1.8, 0.0), (5.0, yf - 0.1, 2.4), CRATE_GREY)                         # the intake hopper under the hatch in the far wall
    b.body.box((2.4, yf - 1.6, 2.4), (4.6, yf - 0.3, 2.9), STEEL)
    b.emit.label((3.5, yf - 0.12, 2.0), 1.4, 0.35, (0, -1, 0), "eq_waste")
    place(b, 5.0, 10.0, 0, H7.conveyor, 6.0)
    b.body.box((11.0, 8.6, 0.0), (14.0, 11.6, 1.6), CRATE_GREY)                                # the compactor
    b.body.box((11.2, 8.8, 1.6), (13.8, 11.4, 2.0), STEEL)
    b.body.cyl((12.5, 10.0, 2.0), (12.5, 10.0, 3.2), 0.28, TRIM, seg=14)
    b.fine.box((14.0, 9.2, 0.4), (14.05, 10.8, 1.2), DGLASS)
    place(b, 19.0, 11.0, 90, H7.furnace)
    for k, x in enumerate((8.0, 10.0, 12.0, 14.0)):                                           # bins by material
        place(b, x, 3.4, 0, F.barrel, 0.3, 0.9, (CRATE_BLUE, CRATE_OLIVE, CRATE_ORANGE, CRATE_GREY)[k])
    place(b, 17.0, 4.2, 90, G.workbench, 3.0, 0.8, 0.95, False)
    place(b, 17.0, 3.2, -90, F.stool, 0.19, 0.62)
    place(b, 21.6, 3.0, 180, H.work_console, 2.0, "engineering", 2, None, False, True)
    place(b, 22.8, 3.0, 180, H.chair_op, FABRIC_RUST)
    place(b, xl + 0.35, 6.0, 0, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    dress_wall(b, "near", L, D, H_, 14.0, 23.5, 6, accent="green", accent_dim="green_dim", kinds=("plain", "vent", "safety", "conduits"))
    ceiling_services(b, L, D, H_, [(5.0, "duct"), (11.0, "pipes")], 1.0, 23.0, 8)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------- computer core
def computer_core(name: str = "SM_SHIP_ComputerCore"):
    """24 x 16 x 3.7: a ship's brain — two cold aisles between back-to-back rows of server racks, two data cores at the far end, coolant pipes overhead, a console on the right wall for
    the systems officer; blue light, a hum."""
    spec, L, D, H_ = _dims("computer_core")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="cyan_dim", strip="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for (x0, yaw0, x1, yaw1) in ((3.4, 0, 6.6, 180), (13.4, 0, 16.6, 180)):             # two aisles: the racks face each other across 2.0 m
        place(b, x0, 6.0, yaw0, H.rack_row, 9, 0.62, 0.95, 2.2, "cyan", int(x0))
        place(b, x1, 11.58, yaw1, H.rack_row, 9, 0.62, 0.95, 2.2, "cyan", int(x1) + 3)
    place(b, 20.6, 7.4, 0, H.data_core, 0.55, 2.5, "cyan")
    place(b, 20.6, 10.6, 0, H.data_core, 0.55, 2.5, "ice")
    place(b, xr - 0.3, 3.4, 180, H.work_console, 2.8, "science", 2, None, False, True)
    place(b, xr - 1.2, 3.4, 180, H.chair_op, FABRIC_GREY)
    place(b, xl + 0.02, 12.0, 0, F.wall_screen, 2.4, 1.3, "scr_data", z=1.5)
    for y in (4.2, 8.0):
        b.body.cyl((xl + 0.2, y, 0.0), (xl + 0.2, y, 1.3), 0.12, PAINT_RED, seg=12)         # fire-suppression bottles
    b.emit.label((xr - 0.003, 8.0, 2.3), 1.2, 0.3, (-1, 0, 0), "eq_core")
    ceiling_services(b, L, D, H_, [(2.6, "pipes"), (8.6, "tray"), (14.6, "pipes")], 1.0, 23.0, 4)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_DIM)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------- auxiliary power
def aux_reactor(name: str = "SM_SHIP_AuxReactor"):
    """32 x 16 x 3.7: the standby reactor — the vessel in its shield ring in the middle of the hall, two heat exchangers and two pump sets on the far side, a row of switchgear cabinets on the
    left wall, the control console by the right wall, a handrailed ring round the vessel."""
    spec, L, D, H_ = _dims("aux_reactor")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("amber_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 16.0, 7.2, 0, N.reactor_vessel, 1.15, 3.0)
    for a in range(0, 360, 20):                                                                 # the rail round the vessel's floor ring
        x, y = 16.0 + 2.1 * math.cos(math.radians(a)), 7.2 + 2.1 * math.sin(math.radians(a))
        b.fine.cyl((x, y, 0.0), (x, y, 1.0), 0.02, TRIM, seg=6)
    H.ring(b.fine, 16.0, 7.2, 1.0, 2.1, 0.03, 0.04, TRIM, 36)
    for x in (8.0, 24.0):
        place(b, x, 11.4, 0, heat_exchanger, 3.6, 0.58, "engineering")
        place(b, x + 2.4, 5.0, 90, H.pump_set, 1.6, "engineering")
    for k in range(5):
        place(b, xl + 0.4, 3.2 + k * 1.0, 0, H.hv_cabinet, 0.9, 0.7, 2.2, 1)
    place(b, xr - 0.3, 3.0, 180, H.work_console, 3.0, "engineering", 2, None, False, True)
    place(b, xr - 1.2, 3.0, 180, H.chair_op, FABRIC_RUST)
    pipe_rack(b, 16.0, 1.6, 4.6, 2.3, 4, 13)
    dress_wall(b, "near", L, D, H_, 16.0, 31.5, 4, accent="amber", accent_dim="amber_dim", kinds=("plain", "vent", "panelboard", "safety"))
    wall_label(b, 6.0, WF + 0.02, 2.6, (0, 1, 0), "eq_hv2", 0.9)
    ceiling_services(b, L, D, H_, [(3.0, "tray"), (10.0, "pipes")], 1.0, 31.0, 6)
    ceiling_panels(b, L, D, H_, 5, 3, "white_warm", 1.6, 1.4, 0.7, LAMP_HOT)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------- damage-control central
def dc_central(name: str = "SM_SHIP_DcCentral"):
    """24 x 16 x 3.6: the ship's damage picture — a plot table with the ship's plan on it under a ring of light, consoles down both walls, a wall of status screens, the damage-control
    officer's chair on the far side, the teams' lockers by the door; red and white light."""
    spec, L, D, H_ = _dims("dc_central")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("red_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 12.0, 7.4, 0, F.table, 4.0, 1.8, 0.86, STEEL, TRIM, False)
    b.emit.label((12.0, 7.4, 0.865), 3.9, 1.7, (0, 0, 1), "scr_ship", up=(0, 1, 0))
    H.lamp_ring(b.emit, 12.0, 7.4, H_ - 0.12, 2.6, 0.1, 0.01, "red_dim", LAMP_DIM, 36)
    for (x, y, yaw) in ((9.0, 7.4, 0), (15.0, 7.4, 180), (12.0, 9.4, -90)):
        place(b, x, y, yaw, H.chair_op, FABRIC_GREY)
    for k in range(3):
        place(b, xl + 0.5, 4.4 + k * 3.4, 0, H.work_console, 2.6, "engineering", 2, None, False, True)
        place(b, xr - 0.5, 4.4 + k * 3.4, 180, H.work_console, 2.6, "engineering", 2, None, False, True)
    place(b, 12.0, yf - 0.05, -90, H.wall_rack_panel, 6.0, 2.2, "scr_ship", "red")
    place(b, 6.0, yf - 0.05, -90, H.wall_rack_panel, 3.0, 2.2, "scr_tac", "red")
    place(b, 18.0, yf - 0.05, -90, H.wall_rack_panel, 3.0, 2.2, "scr_data", "red")
    place(b, 6.0, WF + 0.35, 90, F.locker_row, 4, 0.5, 2.1, 0.55, PAINT_RED)
    wall_label(b, 15.0, WF + 0.02, 2.5, (0, 1, 0), "eq_plot", 0.9)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
