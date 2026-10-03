"""ASN Aquila interior kit: the work and berthing rooms of the other decks — the science lab, the machine shop, the armory, the crew cabins.
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_cabin as SC
import ship_furniture as F
import ship_furniture2 as G
import ship_spec as SPEC
from bridge3_lib import T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, luminaire_strips, place, wall_finish, wall_label, wall_matrix)
from ship_rooms_hub import on_wall
import ship_walls as W


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ------------------------------------------------------------------------------------------------------------------------ lab
def lab(name: str = "SM_SHIP_Lab"):
    spec, L, D, H = _dims("lab")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=TILE, floor_mode="covering", wall_lo=IVORY, wall_hi=IVORY, wain_h=1.2, ceil=IVORY, accent="science_dim", cove="white_cool",
               rib_mat=TRIM, skirt=STEEL)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl = WS + WF
    # fume hoods and sample freezers along the left wall
    for i, y in enumerate((2.3, 4.1, 5.9)):
        place(b, xl + 0.45, y, 0, G.fume_hood, 1.6, 0.9, 2.5)
    for i, y in enumerate((8.0, 9.0, 10.0, 11.0)):
        place(b, xl + 0.375, y, 0, G.sample_fridge, 0.9, 0.75, 2.0)
    place(b, xl + 0.3, 13.6, 0, F.locker_row, 3, 0.5, 1.95, 0.5, COMPOSITE)
    # the instrument bench along the far wall: counters with a spectrometer, a centrifuge, microscopes, monitors; wall cabinets above
    for x in (3.4, 7.0, 10.6, 14.2, 17.8, 21.4):
        place(b, x, yf - 0.4, -90, F.counter, 3.5, 0.75, 0.92, LAMINATE, COMPOSITE, True, False)
    place(b, 3.0, yf - 0.4, -90, G.spectrometer, 1.0, 0.6, z=0.92)
    place(b, 5.4, yf - 0.4, -90, G.centrifuge, z=0.92)
    place(b, 7.0, yf - 0.4, -90, G.microscope, z=0.92)
    place(b, 8.6, yf - 0.4, -90, G.microscope, z=0.92)
    place(b, 12.0, yf - 0.4, -90, G.spectrometer, 1.0, 0.6, z=0.92)
    place(b, 15.6, yf - 0.4, -90, G.centrifuge, z=0.92)
    place(b, 17.8, yf - 0.4, -90, G.microscope, z=0.92)
    for x, tile in ((5.0, "scr_lab"), (9.0, "scr_map"), (13.4, "scr_lab"), (17.0, "scr_sched"), (20.6, "scr_lab")):
        place(b, x, yf - 0.55, -90, F.monitor, 0.55, 0.32, tile, True, z=0.92)
    b.body.box((1.0, yf - 0.42, 1.75), (L - 1.0, yf, 2.55), COMPOSITE)
    for k in range(int((L - 2.0) / 1.1)):
        b.fine.box((1.02 + k * 1.1, yf - 0.435, 1.78), (1.02 + (k + 1) * 1.1 - 0.05, yf - 0.42, 2.52), IVORY)
    b.emit.lamp_box((1.0, yf - 0.44, 1.70), (L - 1.0, yf - 0.40, 1.73), "white_cool", LAMP)
    for x in (6.0, 12.0, 18.0):
        place(b, x, yf - 0.02, -90, _sign, "eq_lab")
    for x in (5.0, 9.0, 13.0, 17.0):                                  # stools where the scientists sit
        place(b, x, yf - 1.35, 0, F.stool, 0.19, 0.6, FABRIC_NAVY)
    # two long islands between the door and the holo table, with stools
    for i, y in enumerate((6.6, 10.6)):
        place(b, 12.6, y, 90, G.lab_island, 6.6, 1.3, 0.92, 3 + i, i == 0)
        for k in range(4):
            place(b, 10.2 + k * 1.6, y + 1.0 + (0.25 if y > 8 else 0.0), 0, F.stool, 0.19, 0.6, FABRIC_NAVY)
    place(b, 19.2, 7.0, 0, G.holo_table, 0.85, 0.92)
    place(b, 21.2, 7.0, 180, F.chair, FABRIC_NAVY)
    # the right wall: a wall display and shelving; near the door: steel shelving with sample boxes and a hand-wash sink
    place(b, L - 0.32, 11.0, 180, F.wall_screen, 3.2, 1.7, "scr_lab", z=1.95)
    place(b, L - 0.75, 3.2, 180, F.shelf, 2.6, 0.5, 2.0, 5, STEEL, False, 5, False)
    place(b, 3.2, WF + 0.3, 90, F.shelf, 2.4, 0.5, 2.0, 5, STEEL, False, 9, False)
    place(b, 6.4, WF + 0.4, 90, F.steel_sink_unit, 1.6, 0.7)
    ceiling_panels(b, L, D, H, 6, 3, "white_cool", 1.4, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


def _sign(b: SParts, tile: str) -> None:
    b.emit.label_fit((0.0, 0.0, 2.9), 0.9, tile, (1, 0, 0))


# --------------------------------------------------------------------------------------------------------------------- workshop
def workshop(name: str = "SM_SHIP_Workshop"):
    spec, L, D, H = _dims("workshop")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="engineering_dim", cove="engineering",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl = WS + WF
    # machine line along the far wall: two lathes, a mill, a drill press, a bench with a vise and a tool wall above
    for x in (5.6, 9.0):
        place(b, x, yf - 0.62, -90, G.lathe, 2.4, 0.9, 1.05)
    place(b, 12.6, yf - 0.6, -90, G.mill, 1.3, 1.0)
    place(b, 15.3, yf - 0.5, -90, G.drill_press)
    place(b, 18.4, yf - 0.45, -90, G.workbench, 3.0, 0.8, 0.95, True)
    place(b, 18.4, yf - 0.02, -90, G.tool_wall, 3.0, 1.5, 2)
    place(b, 22.0, yf - 0.4, -90, G.parts_bins, 2.6, 1.9, 0.5, 3)
    for x in (2.2, 3.4):
        place(b, x, yf - 0.45, -90, F.locker_row, 2, 0.45, 1.95, 0.5, COMPOSITE)
    # the central benches, each with a stool, a monitor, a work lamp
    for x in (8.2, 13.2):
        place(b, x, 8.4, 90, G.workbench, 3.6, 0.9, 0.95, True)
        place(b, x - 1.0, 7.4, 0, F.stool, 0.19, 0.62, FABRIC_RUST)
    place(b, 8.2, 8.4, 90, F.monitor, 0.5, 0.3, "scr_map", False, z=0.95)
    # the welding bay in the right rear corner
    place(b, 25.0, 11.6, 180, G.welding_bay, 3.2, 2.6)
    # the overhead gantry along the shop
    with b.at(T(2.0, 8.0, 0.0)):
        G.overhead_rail(b, 24.0, 0.0, H - 0.5, 9.0)
    # the left wall: a tool wall and heavy shelving; the right wall: stock racks, gas cylinders
    place(b, xl, 6.0, 0, G.tool_wall, 3.4, 1.5, 4)
    place(b, xl + 0.45, 11.6, 0, F.rack, 3.0, 0.9, 2.6, 4, 12, 0.8, [CRATE_GREY, CRATE_ORANGE])
    place(b, L - xl - 0.45, 4.0, 180, F.rack, 3.0, 0.9, 2.6, 4, 15, 0.8, [CRATE_GREY, CRATE_BLUE])
    for k in range(3):
        place(b, L - 0.7, 7.0 + k * 0.32, 0, F.barrel, 0.14, 1.3, [CRATE_BLUE, CRATE_OLIVE, CRATE_GREY][k])
    # floor markings around the machines, hazard lines
    b.emit.label((10.0, yf - 1.85, 0.006), 15.0, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    b.emit.label((25.0, 9.9, 0.006), 3.6, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    luminaire_strips(b, L, D, H, [4.0, 8.6, 13.2], "white_cool", 1.6, L - 1.6, LAMP_HOT, 0.3)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- armory
def armory(name: str = "SM_SHIP_Armory"):
    spec, L, D, H = _dims("armory")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="security_dim", cove="security_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # the cage line across the room at y 4.2 with the service counter opposite the door and a gap by the right wall
    for (xa, xb) in ((0.3, 4.4), (7.6, 12.6)):
        n = (xb - xa)
        with b.at(frame((xa + xb) / 2, 4.2, 0.0, 90)):
            G.cage_wall(b, n, 2.7)
    place(b, 6.0, 4.2, 90, F.counter, 3.2, 0.7, 1.05, STEEL, COMPOSITE, True, False)
    b.body.box((4.4, 4.0, 2.4), (7.6, 4.4, 2.7), STEEL)                                        # the header of the window
    b.emit.label((6.0, 3.98, 2.55), 1.6, 0.2, (0, -1, 0), "hazard")
    b.emit.label_fit((6.0, 3.9, 1.7), 0.8, "eq_ammo", (0, -1, 0))
    place(b, 9.0, 1.4, 90, F.desk, 1.4, 0.6, 0.78, STEEL, False)
    place(b, 9.0, 1.4, 90, F.monitor, 0.4, 0.25, "scr_sched", False, z=0.78)
    place(b, 2.0, 1.2, 0, F.bench, 1.6, 0.4, 0.46, FABRIC_GREY)
    # behind the cage: weapon racks on the far wall and the right wall, ammunition lockers on the left wall, armour dummies, a gun bench
    for i, x in enumerate((3.0, 6.6, 10.2)):
        place(b, x, yf - 0.02, -90, G.weapon_rack, 3.2, 8, 1.9, i)
    place(b, xr - 0.02, 8.0, 180, G.weapon_rack, 3.0, 6, 1.9, 4)
    place(b, xr - 0.02, 11.6, 180, G.weapon_rack, 3.0, 6, 1.9, 5)
    for k in range(5):
        place(b, xl + 0.3, 5.4 + k * 1.0, 0, G.ammo_locker, 0.9, 0.6, 1.9, [CRATE_OLIVE, CRATE_GREY][k % 2])
    for k in range(3):
        place(b, 13.2 + 0.0, 5.6 + k * 1.0, 180, G.armor_stand)
    place(b, 8.6, 11.0, -90, G.gun_bench, 2.6, 0.8)
    place(b, 8.6, 11.0, -90, F.monitor, 0.5, 0.3, "scr_lab", False, z=0.95)
    for k in range(3):
        place(b, 5.4 + 0.6 * k, 8.0, 90 + 10 * k, F.crate, 0.6, 0.4, 0.4, CRATE_OLIVE, None)
    b.emit.label((3.0, 4.3, 0.006), 2.6, 0.14, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    ceiling_panels(b, L, D, H, 3, 3, "white_cool", 1.6, 0.9, 0.5, LAMP_HOT)
    for y in (4.2, 11.0):
        lamp_strip(b.emit, (1.0, y, H - 0.06), (L - 1.0, y, H - 0.06), 0.05, 0.006, "security_dim", LAMP_DIM)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------- cabins
CAB_Y = (2.0, 6.0, 10.0, 14.0)          # the centres of the four cabins along each side (y)
CAB_XL, CAB_XR = 5.0, 15.0              # the hall's walls (x)


def cabins(name: str = "SM_SHIP_Cabins"):
    """20 x 16: a commons hall in the middle (x 5..15), four crew cabins on each side (each 4.75 x 4 m: a bunk with its nightstand and lamp, a desk with a screen and a plant under a window
    with curtains, a wardrobe, a basin, a rug, a light of its own: ship_cabin.py); the hall is the same as the officers' (a seating group, a table laid for dinner, a coffee corner)."""
    spec, L, D, H = _dims("cabins")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent="warm_dim", cove="white_warm",
               ribs=False, skirt=WOOD)
    build_shell(b, spec, st)
    SC.quarters_block(b, spec, False, CAB_Y, CAB_XL, CAB_XR, 0)
    SC.hall_dress(b, spec, False, CAB_Y, CAB_XL, CAB_XR)
    return b.build(name)
