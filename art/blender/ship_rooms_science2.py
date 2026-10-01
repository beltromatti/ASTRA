"""ASN Aquila interior kit: the rest of the science rooms of Deck 5 (NAVE-2) — the sensor archive, the sensor array room and the laboratories of biology,
astrometrics and physics. Frames and sizes: ship_rooms.py / ship_spec.py; the Transporter Room is in ship_rooms_science.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_finish, wall_label,
                        wall_matrix)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ---------------------------------------------------------------------------------------------------------------------- sensor archive
def sensor_archive(name: str = "SM_SHIP_SensorArchive"):
    """16 x 16 x 3.4: four double rows of data racks back to back (the door opens on the first aisle), a cold vault of memory columns at the far end, the archivist's
    desk and the index terminals by the door."""
    spec, L, D, H_ = _dims("sensor_archive")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="science_dim", cove="ice",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    n, w = 16, 0.62
    # the stacks: pairs of rows, backs together
    for k, x0 in enumerate((3.4, 6.7, 10.0, 13.3)):
        place(b, x0 + 1.425, 4.91, 0, H.rack_row, n, w, 0.95, 2.2, "cyan" if k % 2 == 0 else "violet", 10 * k)                      # faces +x
        place(b, x0 + 0.475, 4.91 + (n - 1) * w, 180, H.rack_row, n, w, 0.95, 2.2, "cyan" if k % 2 else "violet", 10 * k + 5)      # faces -x
    for xa in (2.7, 6.0, 9.3, 12.6):                                                                                                 # aisle guide lines
        lamp_strip(b.emit, (xa, 3.6, 0.006), (xa, 14.6, 0.006), 0.04, 0.004, "ice", LAMP_DIM)
    # the cold vault along the far wall: memory columns
    for k in range(6):
        place(b, 2.6 + k * 2.2, yf - 0.55, -90, H.pattern_buffer, 2.4, 0.32, "violet")
    on_wall(b, "far", L, D, W.cable_runs, b.body, 1.2, 14.8, H_, random.Random(5), True, 2)
    # reception: the archivist's desk facing the door, two index terminals on the near wall, a notice board
    place(b, 11.4, 2.0, -90, F.desk, 2.0, 0.8, 0.76, LAMINATE, True)
    place(b, 11.4, 2.0, -90, F.monitor, 0.5, 0.3, "scr_data", False, z=0.76)
    place(b, 11.4, 1.0, 90, H.chair_op, FABRIC_GREY)
    for x in (1.8, 3.0):
        place(b, x, WF + 0.4, 90, F.counter, 1.0, 0.6, 1.05, LAMINATE, COMPOSITE, True, False)
        place(b, x, WF + 0.5, 90, F.monitor, 0.45, 0.28, "scr_data", True, z=1.05)
    place(b, xr - 0.02, 3.0, 180, F.wall_screen, 2.0, 1.1, "scr_dir", z=1.8)
    place(b, xl + 0.3, 7.0, 0, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    dress_wall(b, "left", L, D, H_, 10.5, 14.5, 2, accent="science", accent_dim="science_dim", kinds=("panelboard", "conduits"))
    ceiling_panels(b, L, D, H_, 4, 3, "ice", 1.6, 0.5, 2.4, LAMP_HOT)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------- sensor room
def sensor_room(name: str = "SM_SHIP_SensorRoom"):
    """16 x 16 x 3.6: three operator consoles in a row facing a wall of three big displays, racks along the side walls, a sensor globe on a pedestal."""
    spec, L, D, H_ = _dims("sensor_room")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="science_dim", cove="science_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((3.4, "scr_wave"), (8.0, "scr_tac"), (12.6, "scr_star")):                                  # the display wall
        place(b, x, yf - 0.02, -90, H.wall_rack_panel, 4.1, 2.6, tile, "cyan")
    b.emit.lamp_box((1.0, yf - 0.1, 3.05), (L - 1.0, yf - 0.06, 3.1), "science_dim", LAMP_DIM)
    for k, x in enumerate((3.4, 8.0, 12.6)):                                                                    # the consoles and the operators behind them
        place(b, x, 8.2, -90, H.work_console, 3.0, "science", 2, ["scr_wave", "scr_data", "scr_map"][k:] + ["scr_lab"], True, True)
        place(b, x, 6.9, 90, H.chair_op, FABRIC_NAVY)
    place(b, xl + 0.5, 5.2, 0, H.rack_row, 8, 0.62, 0.95, 2.2, "science", 3)
    place(b, xr - 0.5, 5.2 + 7 * 0.62, 180, H.rack_row, 8, 0.62, 0.95, 2.2, "cyan", 11)
    with b.at(T(8.0, 12.0, 0.0)):                                                                              # the sensor globe
        b.body.cyl((0, 0, 0.0), (0, 0, 0.9), 0.55, STRUCT, seg=20, r2=0.45)
        H.ring(b.body, 0.0, 0.0, 0.9, 0.46, 0.08, 0.06, TRIM, 24)
        H.lamp_sphere(b.emit, (0, 0, 1.55), 0.5, "cyan_dim", LAMP_DIM, 20, 12)
        H.lamp_ring(b.emit, 0.0, 0.0, 1.55, 0.62, 0.025, 0.03, "cyan", LAMP, 32)
        H.lamp_ring(b.emit, 0.0, 0.0, 0.004, 1.6, 0.05, 0.004, "science", LAMP_DIM, 40)
    dress_wall(b, "near", L, D, H_, 8.0, 15.0, 4, accent="science", accent_dim="science_dim", kinds=("plain", "vent", "safety", "screen"))
    ceiling_services(b, L, D, H_, [(4.0, "tray"), (12.0, "duct")], 1.0, 15.0, 6)
    ceiling_panels(b, L, D, H_, 3, 3, "white_cool", 1.6, 0.9, 0.5, LAMP_HOT)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------- bio lab
def lab_bio(name: str = "SM_SHIP_LabBio"):
    """24 x 16 x 3.6: a wall of lit tanks along the far wall, two grow benches under lamp bars, sample freezers and a glovebox on the left wall, a dissection table
    under a lamp and a microscope counter on the right, the lead scientist's desk by the door."""
    from ship_rooms_med import op_table, surgical_lamp
    spec, L, D, H_ = _dims("lab_bio")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=TILE, floor_mode="covering", wall_lo=IVORY, wall_hi=IVORY, wain_h=1.2, ceil=IVORY, accent="science_dim", cove="white_warm",
               rib_mat=TRIM, skirt=STEEL)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(5):
        place(b, 2.2 + k * 4.4, yf - 0.4, -90, H.aquarium, 3.6, 0.8, 2.1, 20 + k, ["cyan_dim", "green_dim", "cyan_dim", "ice_dim", "green_dim"][k])
    place(b, 4.2, 8.6, 0, H.bench_grow, 5.4, 1.1, 2, 1, "science")
    place(b, 7.6, 8.6, 0, H.bench_grow, 5.4, 1.1, 2, 2, "white_warm")
    place(b, xl + 0.45, 3.0, 0, G.sample_fridge, 0.9, 0.75, 2.0)
    place(b, xl + 0.45, 4.0, 0, G.sample_fridge, 0.9, 0.75, 2.0)
    place(b, xl + 0.5, 6.4, 0, H.glovebox, 1.8, 1.0, 1.5)
    place(b, xl + 0.4, 12.0, 0, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    place(b, 17.0, 7.4, 0, op_table)                                                                            # the dissection table under its lamp
    place(b, 17.0, 7.4, 0, surgical_lamp, H_ - 0.05)
    place(b, 19.6, 6.0, 180, F.steel_sink_unit, 1.6, 0.7)
    place(b, xr - 0.4, 12.2, 180, F.counter, 5.0, 0.7, 0.92, LAMINATE, COMPOSITE, True, False)
    for y in (10.4, 11.5, 12.6):
        place(b, xr - 0.4, y, 180, G.microscope, z=0.92)
    place(b, xr - 0.45, 14.0, 180, F.monitor, 0.55, 0.32, "scr_lab", True, z=0.92)
    place(b, 12.6, 1.2, 90, F.desk, 1.6, 0.7, 0.76, LAMINATE, True)
    place(b, 12.6, 1.2, 90, F.monitor, 0.5, 0.3, "scr_lab", False, z=0.76)
    place(b, 13.4, 2.0, -90, H.chair_op, FABRIC_GREY)
    place(b, xr - 0.02, 3.5, 180, F.wall_screen, 2.4, 1.3, "scr_lab", z=1.8)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 3, accent="science", accent_dim="science_dim", kinds=("plain", "safety", "vent"))
    ceiling_panels(b, L, D, H_, 6, 3, "white_cool", 1.4, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------------- astrometrics
def lab_astro(name: str = "SM_SHIP_LabAstro"):
    """24 x 16 x 3.6: a dark room under a field of stars: a triptych of star charts on the far wall, a round holographic table in the middle ringed by six tilted
    consoles and their stools, a light ring in the floor."""
    from ship_rooms_social import _star_field
    spec, L, D, H_ = _dims("lab_astro")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=STRUCT, wain_h=1.2, ceil=STRUCT, accent="science_dim", cove="science_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((5.0, "scr_star"), (12.0, "scr_star"), (19.0, "scr_map")):
        place(b, x, yf - 0.02, -90, H.wall_rack_panel, 6.2, 2.9, tile, "cyan")
    b.emit.lamp_box((1.0, yf - 0.1, 3.3), (L - 1.0, yf - 0.06, 3.35), "science_dim", LAMP_DIM)
    cx, cy = 12.0, 8.2
    place(b, cx, cy, 0, G.holo_table, 1.35, 0.95)
    H.lamp_sphere(b.emit, (cx, cy, 1.55), 0.34, "cyan", LAMP, 18, 10)
    H.lamp_ring(b.emit, cx, cy, 0.004, 3.6, 0.05, 0.004, "science", LAMP_DIM, 48)
    H.lamp_ring(b.emit, cx, cy, 0.004, 2.0, 0.04, 0.004, "science_dim", LAMP_DIM, 36)
    for k in range(6):
        a = 360.0 * k / 6 + 30.0
        ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
        place(b, cx + 2.6 * ca, cy + 2.6 * sa, a, H.work_console, 1.5, "science", 1, ["scr_star", "scr_data", "scr_wave"][k % 3:], False, False)
        place(b, cx + 3.6 * ca, cy + 3.6 * sa, a + 180, F.stool, 0.19, 0.6, FABRIC_NAVY)
    _star_field(b, L, D, H_, 260, 9)
    place(b, xl + 0.5, 8.0, 0, F.counter, 7.0, 0.65, 0.92, LAMINATE, COMPOSITE, True, False)                  # a data counter on the left wall
    for k, y in enumerate((5.6, 8.0, 10.4)):
        place(b, xl + 0.6, y, 0, F.monitor, 0.6, 0.34, ["scr_star", "scr_data", "scr_wave"][k], True, z=0.92)
    place(b, xr - 0.4, 3.5, 180, F.locker_row, 4, 0.45, 1.95, 0.5, COMPOSITE)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 5, accent="science", accent_dim="science_dim", kinds=("plain", "vent", "safety", "conduits"))
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------- physics lab
def lab_phys(name: str = "SM_SHIP_LabPhys"):
    """24 x 16 x 3.8: a beamline on a steel frame (a tube, magnet blocks every 1.4 m) running to a ring detector standing on its edge, a shielded control booth with a dark
    window and a desk, cryo dewars and their lines, gas bottles, a work bench."""
    spec, L, D, H_ = _dims("lab_phys")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="science_dim", cove="science_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    ybeam = 11.0
    for x in (3.0, 6.0, 9.0, 12.0, 15.0):                                                                       # the frame and the beam tube
        b.body.box((x - 0.12, ybeam - 0.5, 0.0), (x + 0.12, ybeam + 0.5, 0.9), STEEL)
        b.body.box((x - 0.3, ybeam - 0.55, 0.9), (x + 0.3, ybeam + 0.55, 0.96), STRUCT)
    b.body.cyl((2.4, ybeam, 1.25), (17.6, ybeam, 1.25), 0.13, STEEL, seg=14)
    for k in range(10):
        x = 3.3 + k * 1.4
        b.body.box((x, ybeam - 0.34, 0.96), (x + 0.5, ybeam + 0.34, 1.62), [CRATE_BLUE, CRATE_ORANGE][k % 2])
        b.fine.box((x + 0.02, ybeam - 0.36, 1.2), (x + 0.48, ybeam - 0.34, 1.3), TRIM)
        b.emit.lamp_box((x + 0.1, ybeam + 0.34, 1.5), (x + 0.4, ybeam + 0.345, 1.54), "science", LAMP_DIM)
    H.vertical_ring(b, 19.6, ybeam, 1.95, 1.5, 0.4, 0.7, COMPOSITE, 40)                                         # the detector ring on its edge
    H.vertical_ring(b, 19.6, ybeam, 1.95, 1.46, 0.04, 0.78, TRIM, 40)
    H.vertical_ring(b, 19.6, ybeam, 1.95, 1.90, 0.04, 0.78, TRIM, 40)
    b.body.box((18.4, ybeam - 0.6, 0.0), (20.8, ybeam + 0.6, 0.4), STRUCT)
    for k in range(12):
        a = math.radians(30 * k)
        px, pz = 19.6 + 1.7 * math.cos(a), 1.95 + 1.7 * math.sin(a)
        b.emit.lamp_box((px - 0.05, ybeam - 0.36, pz - 0.05), (px + 0.05, ybeam - 0.35, pz + 0.05), "cyan" if k % 3 else "amber", LAMP_DIM)
    for sx in (18.4, 20.7):
        b.body.box((sx, ybeam - 0.3, 0.4), (sx + 0.1, ybeam + 0.3, 1.4), STEEL)
    b.body.box((1.0, 5.5, 0.0), (9.0, 5.6, 2.6), COMPOSITE)                                                      # the shielded booth
    b.fine.box((2.0, 5.46, 1.0), (7.6, 5.64, 2.2), DGLASS)
    b.body.box((9.0, 5.5, 0.0), (9.1, 5.6, 2.6), TRIM)
    b.body.box((1.0, 5.5, 2.6), (9.1, 5.7, 3.0), STRUCT)
    b.emit.lamp_box((1.0, 5.45, 2.65), (9.1, 5.48, 2.7), "science", LAMP_DIM)
    b.emit.label((5.0, 5.45, 2.85), 1.6, 0.16, (0, -1, 0), "hazard")
    place(b, 5.0, 3.8, -90, F.desk, 3.0, 0.8, 0.76, LAMINATE, True)
    for x, tile in ((4.0, "scr_data"), (5.0, "scr_wave"), (6.0, "scr_lab")):
        place(b, x, 3.8, -90, F.monitor, 0.6, 0.34, tile, False, z=0.76)
    place(b, 5.0, 2.8, 90, H.chair_op, FABRIC_NAVY)
    place(b, 1.4, 3.0, 0, H.rack_row, 4, 0.62, 0.95, 2.2, "science", 7)
    for k in range(3):                                                                                           # cryo dewars, bottles, a bench
        place(b, 21.4, 3.0 + k * 1.2, 0, H.tank_v, 0.46, 1.7, STEEL, "cyan", "eq_gas")
    for k in range(4):
        place(b, 23.2, 3.0 + k * 0.4, 0, F.barrel, 0.14, 1.3, [CRATE_BLUE, CRATE_OLIVE, CRATE_GREY, CRATE_BLUE][k])
    H.pipe_bundle(b, (21.4, 3.0, 2.4), (21.4, ybeam, 2.4), 2, 0.04, 0.03, (1, 0, 0), None, 1.5)
    place(b, 12.0, 14.6, -90, G.workbench, 4.0, 0.8, 0.95, True)
    place(b, 6.0, 14.6, -90, G.tool_wall, 2.8, 1.4, 6)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 6, accent="science", accent_dim="science_dim", kinds=("plain", "panelboard", "conduits", "safety"))
    ceiling_services(b, L, D, H_, [(7.0, "tray"), (13.8, "duct")], 1.0, 23.0, 8)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
