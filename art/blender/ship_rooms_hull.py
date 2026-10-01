"""ASN Aquila interior kit (NAVE-3): the rooms on the hull galleries (Decks 5-11) and the small rooms every section has — the EVA airlock, the lifepod bay, the suit lockers, the section's
stores, the crew lockers, the technical space, and the damage-control station that stands behind every stair tower. Frames and sizes: ship_rooms.py / ship_spec.py / ship_spec3.py."""
from __future__ import annotations

import random

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H3
import ship_furniture5 as F5
import ship_furniture7 as H7
import ship_furniture9 as N
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import T, frame
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER,
                      STEEL, STRUCT, TRIM, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_label
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _work_style(accent: str = "amber_dim", cove: str = "white_warm", floor: str = DECK) -> Style:
    return Style(floor=floor, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ------------------------------------------------------------------------------------------------------------------------------------------------------------ the airlock
def airlock(name: str = "SM_SHIP_Airlock"):
    """8 x 4 x 2.7: the hull's EVA airlock. By the door an ante-room (the suits on a rack, a bench, a status board); a pressure hatch in the partition at x 4; the chamber (a
    grating floor, hand rails, a lamp in a cage) and, in the hull wall, the outer hatch with its wheel and a porthole."""
    spec, L, D, H = _dims("airlock")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _work_style("amber_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # the partition between the ante-room and the chamber, the inner hatch
    b.body.box((3.9, WF, 0.0), (4.1, D - WS - WF, H), STRUCT)
    place(b, 3.9, 1.9, 180, N.round_hatch, 0.5, z=1.15)
    b.emit.label((3.88, 0.9, 2.1), 0.6, 0.15, (-1, 0, 0), "eq_cycle")
    # the ante-room: three suits on the left wall, a bench under the far wall, the board by the partition
    place(b, xl + 0.02, 1.95, 0, H7.eva_rack, 3)
    place(b, 2.6, yf - 0.28, -90, F.bench, 2.2, 0.5, 0.46, FABRIC_GREY)
    place(b, 3.88, 3.1, 180, F.wall_screen, 0.8, 0.5, "scr_ship", z=1.5)
    # the chamber: the outer hatch in the hull's wall, grating on the floor, rails, a caged lamp
    place(b, 5.9, yf, -90, N.round_hatch, 0.62, z=1.2)
    b.fine.box((4.2, 0.2, 0.0), (L - 0.3, D - 0.3, 0.02), STEEL)
    for k in range(8):
        b.fine.box((4.2 + k * 0.5, 0.2, 0.02), (4.22 + k * 0.5, D - 0.3, 0.03), TRIM)
    for y in (0.5, 3.5):
        b.fine.cyl((4.3, y, 1.0), (L - 0.4, y, 1.0), 0.02, TRIM, seg=8)
    b.emit.lamp_box((5.4, 1.6, H - 0.07), (6.4, 2.4, H - 0.05), "white_cool", LAMP_HOT)
    b.emit.label((5.9, yf - 0.002, 2.25), 0.9, 0.225, (0, -1, 0), "hazard")
    wall_label(b, 2.0, WF + 0.02, 2.2, (0, 1, 0), "eq_suit", 0.6)
    ceiling_panels(b, 3.6, D, H, 1, 1, "white_warm", 0.8, 1.4, 0.6, LAMP_HOT)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------- the lifepods
def pod_bay(name: str = "SM_SHIP_PodBay"):
    """8 x 4 x 2.7: two lifepods on their launch rails, nose to the hull's launch doors, hatches towards each other; a seat and a muster board by the door."""
    spec, L, D, H = _dims("pod_bay")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _work_style("amber_dim", "white_warm"))
    yf = D - WS - WF
    for k, (x, side) in enumerate(((3.9, -1), (6.3, 1))):
        place(b, x, 0.6, 0, N.launch_rail, 3.3)
        place(b, x, 2.15, 90, N.lifepod, 3.0, 1.6, 1.8, side)
        b.body.box((x - 0.95, yf - 0.12, 0.0), (x + 0.95, yf, 2.3), STEEL)                                          # the launch door in the hull's wall
        b.fine.box((x - 0.85, yf - 0.16, 0.1), (x + 0.85, yf - 0.12, 2.2), STRUCT)
        b.fine.box((x - 0.02, yf - 0.18, 0.1), (x + 0.02, yf - 0.16, 2.2), TRIM)
        b.emit.label((x, yf - 0.185, 2.1), 1.4, 0.14, (0, -1, 0), "hazard")
        b.emit.lamp_box((x - 0.5, yf - 0.17, 2.36), (x + 0.5, yf - 0.165, 2.4), "amber", LAMP)
    place(b, 0.6, 2.7, 0, F.bench, 1.6, 0.42, 0.46, FABRIC_NAVY)
    wall_label(b, 0.8, WF + 0.02, 1.9, (0, 1, 0), "eq_muster", 0.6)
    b.emit.label((0.3, 1.5, 1.7), 0.5, 0.5, (1, 0, 0), "pict_pods")
    luminaire_strips(b, L, D, H, [1.4, 2.6], "white_warm", 0.8, L - 0.8, LAMP_DIM, 0.2)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------- the suit lockers
def suit_locker(name: str = "SM_SHIP_SuitLocker"):
    """8 x 4 x 2.7: two racks of EVA suits on the far wall, a bench with a helmet shelf above it, lockers along the right wall, boots under the racks."""
    spec, L, D, H = _dims("suit_locker")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _work_style("amber_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 2.0, yf - 0.08, -90, H7.eva_rack, 2)
    place(b, 5.0, yf - 0.08, -90, H7.eva_rack, 3)
    place(b, 6.6, 1.2, 0, F.bench, 2.0, 0.42, 0.46, FABRIC_GREY)
    place(b, xr - 0.2, 1.4, 180, F.locker_row, 2, 0.45, 1.95, 0.4, COMPOSITE)
    place(b, 3.2, 0.9, 90, F.shelf, 1.8, 0.3, 1.0, 2, STEEL, False, 3, False)
    for k in range(4):
        b.soft.sphere((1.0 + k * 0.55, 0.9, 1.05), 0.14, IVORY, seg=10, rings=6)
        b.soft.box((1.0 + k * 0.55 + 0.08, 0.84, 1.0), (1.0 + k * 0.55 + 0.17, 0.96, 1.1), DGLASS)
    b.emit.label((2.0, WF + 0.002, 2.2), 0.7, 0.175, (0, 1, 0), "eq_suit")
    ceiling_panels(b, L, D, H, 2, 1, "white_warm", 1.2, 1.4, 0.6, LAMP_HOT)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------------------------- damage-control station
def dc_station(name: str = "SM_SHIP_DcStation"):
    """8 x 8 x 3.4: the section's damage-control station. Red-doored lockers on the far wall, hose reels and a rack of breathing apparatus on the walls, shoring props and hull-patch plates
    leaning in a corner, a bench with a plot table (the section's plan), a status screen; red light."""
    from ship_rooms_engineering import hose_reel, scba_rack
    spec, L, D, H = _dims("dc_station")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _work_style("red_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 2.0, yf - 0.3, -90, F.locker_row, 4, 0.5, 2.1, 0.55, PAINT_RED)
    place(b, 6.0, yf - 0.3, -90, F.locker_row, 2, 0.5, 2.1, 0.55, PAINT_RED)
    place(b, xl + 0.02, 3.4, 0, hose_reel, 0.4, PAINT_RED)
    place(b, xl + 0.02, 5.0, 0, hose_reel, 0.4, PAINT_RED)
    place(b, xr - 0.02, 3.6, 180, scba_rack, 4, 0.32)
    place(b, xr - 0.02, 5.8, 180, F.wall_screen, 1.8, 1.0, "scr_ship", z=1.75)
    for k, x in enumerate((6.9, 7.2, 7.5)):                                                                               # shoring props in the corner by the door, patch plates against the wall
        b.body.cyl((x, 0.7, 0.0), (x, 0.7, 2.3), 0.05, CRATE_ORANGE, seg=8)
        b.fine.cyl((x, 0.7, 2.3), (x, 0.7, 2.38), 0.08, STEEL, seg=8)
    for k in range(3):
        b.body.box((xl + 0.1, 0.5 + k * 0.5, 0.0), (xl + 0.18, 0.95 + k * 0.5, 1.2 + k * 0.1), STEEL)
        b.fine.box((xl + 0.1, 0.5 + k * 0.5, 0.5), (xl + 0.19, 0.95 + k * 0.5, 0.56), PAINT_RED)
    place(b, 3.8, 4.0, 90, F.table, 1.6, 0.9, 0.86, STEEL, TRIM, False)
    b.emit.label((3.8, 4.0, 0.865), 1.5, 0.8, (0, 0, 1), "scr_ship", up=(1, 0, 0))
    place(b, 3.8, 3.1, 90, F.stool, 0.19, 0.5)
    on_wall(b, "left", L, D, W.extinguisher, b.body, 6.6, 0.0)
    b.emit.label((4.0, WF + 0.02, 2.7), 1.6, 0.4, (0, 1, 0), "eq_dcs")
    b.emit.label((4.0, 4.0, 0.006), 3.0, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    ceiling_panels(b, L, D, H, 2, 2, "white_warm", 1.4, 1.0, 0.5, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the section's stores
def store_s(name: str = "SM_SHIP_StoreS"):
    """8 x 16 x 3.4: the section's stores — steel shelving down both sides with the stock in tins and boxes, a pallet of crates at the far end, a storekeeper's desk and a tally board by
    the door."""
    spec, L, D, H = _dims("store_s")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, accent="amber_dim", strip="white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    rng = random.Random(41)
    for k in range(3):                                                                                                    # the shelving, long along y, facing the aisle
        y = 4.4 + k * 3.6
        place(b, xl + 0.28, y, 0, N.cell_wall_rack, 3.0, 0.5, 2.1, 10 + k)
        place(b, xr - 0.28, y, 180, N.cell_wall_rack, 3.0, 0.5, 2.1, 20 + k)
    place(b, 4.0, yf - 1.3, 90, F.pallet, 1.2, 0.8)
    for j in range(rng.randint(3, 4)):
        place(b, 4.0 + rng.uniform(-0.15, 0.15), yf - 1.3 + rng.uniform(-0.1, 0.1), 90 + rng.uniform(-6, 6), F.crate, 0.55, 0.4, 0.4,
              rng.choice([CRATE_OLIVE, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY]), None, True, z=0.145 + j * 0.4)
    place(b, 5.9, 1.5, 180, F.desk, 1.2, 0.6, 0.8, LAMINATE, True)
    place(b, 6.0, 1.5, 180, F.monitor, 0.4, 0.25, "scr_sched", False, z=0.8)
    wall_label(b, 4.0, WF + 0.02, 2.4, (0, 1, 0), "eq_stores", 0.9)
    ceiling_panels(b, L, D, H, 1, 4, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


def locker_s(name: str = "SM_SHIP_LockerS"):
    """8 x 16 x 3.4: a crew locker room — rows of lockers down both walls, benches between them, a boot rack at the far end, a hand basin and a mirror by the door."""
    spec, L, D, H = _dims("locker_s")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, accent="cool_dim", strip="white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for y0 in (3.0, 6.0, 9.0, 12.0):                                                                                      # rows of five lockers (0.5 m each), doors to the aisle
        place(b, xl + 0.25, y0, 0, F.locker_row, 5, 0.5, 1.95, 0.5, COMPOSITE)
        place(b, xr - 0.25, y0 + 2.5, 180, F.locker_row, 5, 0.5, 1.95, 0.5, COMPOSITE)
    for y in (6.0, 10.0):
        place(b, 4.0, y, 0, F.bench, 2.4, 0.4, 0.46, FABRIC_GREY)
    place(b, 4.0, yf - 0.3, -90, F5.boot_rack, 6)
    place(b, 6.4, WF + 0.3, 90, G.vanity, 1.0, 0.5)
    wall_label(b, 4.0, yf - 0.002, 2.3, (0, -1, 0), "eq_kit2", 0.7)
    ceiling_panels(b, L, D, H, 1, 4, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


def tech_s(name: str = "SM_SHIP_TechS"):
    """8 x 16 x 3.4: a technical space — the section's switchgear and data cabinets, a transformer, a pipe run and a duct under the ceiling, a bench, amber light."""
    spec, L, D, H = _dims("tech_s")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _work_style("amber_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(4):
        place(b, xl + 0.4, 3.6 + k * 1.0, 0, H3.hv_cabinet, 0.9, 0.7, 2.2, 1)
    place(b, xr - 0.55, 7.4, 180, H3.rack_row, 4, 0.62, 0.95, 2.2, "cyan", 7)
    place(b, 4.0, yf - 0.9, -90, H3.transformer, 1.6, 1.2, 1.9)
    place(b, 4.0, 10.6, 0, G.workbench, 2.4, 0.8, 0.95, True)
    wall_label(b, 2.0, WF + 0.002, 2.4, (0, 1, 0), "tag_06", 0.7)
    ceiling_services(b, L, D, H, [(5.0, "pipes"), (11.0, "duct")], 1.0, L - 1.0, 5)
    ceiling_panels(b, L, D, H, 1, 4, "white_warm", 1.6, 1.0, 0.5, LAMP_HOT)
    return b.build(name)
