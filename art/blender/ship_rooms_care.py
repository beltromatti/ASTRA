"""ASN Aquila interior kit (NAVE-3): the rooms of care and of order — the dental clinic, the morgue and the counselling office of the medical complex (Deck 6), the brig and the security
office (Deck 8). Frames and sizes: ship_rooms.py / ship_spec.py / ship_spec3.py."""
from __future__ import annotations

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H3
import ship_furniture8 as H8
import ship_furniture9 as N
import ship_spec as SPEC
from bridge3_lib import frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_GREY, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL,
                      STRUCT, TILE, TRIM, WOOD, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, luminaire_strips, place, wall_label
from ship_rooms_med import surgical_lamp
from ship_rooms_service import cart


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _clinic_style(accent: str = "medical_dim", cove: str = "white_cool") -> Style:
    return Style(floor=TILE, floor_mode="covering", wall_lo=TILE, wall_hi=IVORY, wain_h=2.0, ceil=IVORY, accent=accent, cove=cove, ribs=False, skirt=STEEL)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------- dental clinic
def dentist(name: str = "SM_SHIP_Dentist"):
    """12 x 16: two treatment bays (a reclined chair, the delivery unit and the lamp over it, a stool), reception by the door with waiting chairs, and a sterilising counter with sinks and a
    cabinet wall on the far side."""
    spec, L, D, H = _dims("dentist")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _clinic_style())
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for xc in (3.0, 9.0):                                                                  # the bays: the patient's head towards the door's side, the dentist at the head
        place(b, xc, 9.4, 90, N.dental_chair)
        place(b, xc + 1.15, 9.4, 0, N.dental_unit)
        place(b, xc, 7.5, 90, F.stool, 0.19, 0.62)
    b.body.box((5.9, 6.9, 0.0), (6.1, 12.4, H), COMPOSITE)                                  # a screen between the two bays
    b.fine.box((5.9, 6.9, 1.2), (6.1, 12.4, 2.3), DGLASS)
    for k in range(3):                                                                     # waiting chairs, a table with magazines
        place(b, xl + 0.4, 1.4 + k * 0.7, 0, F.chair, FABRIC_NAVY)
    place(b, xl + 1.6, 2.1, 0, F.low_table, 0.5, 1.4, 0.42, WOOD)
    place(b, 9.0, 2.6, 180, F.desk, 1.6, 0.7, 0.78, LAMINATE, False)                      # reception
    place(b, 9.0, 2.6, 180, F.monitor, 0.5, 0.3, "scr_sched", True, z=0.78)
    place(b, 9.8, 2.6, 180, F.chair, FABRIC_GREY)
    for x in (2.6, 6.2, 9.8):                                                              # the sterilising counter and the cabinets above it
        place(b, x, yf - 0.36, -90, F.counter, 3.5, 0.7, 0.92, LAMINATE, COMPOSITE, True, False)
    place(b, 8.4, yf - 0.4, -90, F.steel_sink_unit, 1.6, 0.7)
    b.body.box((0.8, yf - 0.42, 1.55), (L - 0.8, yf, 2.5), COMPOSITE)
    for k in range(int((L - 1.6) / 1.2)):
        b.fine.box((0.82 + k * 1.2, yf - 0.435, 1.58), (0.82 + (k + 1) * 1.2 - 0.05, yf - 0.42, 2.47), DGLASS)
    b.emit.lamp_box((0.8, yf - 0.44, 1.50), (L - 0.8, yf - 0.40, 1.53), "medical", LAMP)
    place(b, 4.4, yf - 0.55, -90, F.monitor, 0.6, 0.34, "scr_lab", True, z=0.92)
    place(b, xl + 0.02, 12.0, 0, F.wall_screen, 2.0, 1.1, "scr_lab", z=1.85)
    place(b, xr - 0.02, 7.0, 180, F.wall_screen, 1.4, 0.8, "scr_ship", z=1.85)
    wall_label(b, 2.5, WF + 0.02, 2.2, (0, 1, 0), "eq_dental", 0.6)
    ceiling_panels(b, L, D, H, 3, 3, "white_cool", 1.2, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- morgue
def morgue(name: str = "SM_SHIP_Morgue"):
    """12 x 16: a cold room — two walls of refrigerated drawers on the far side, an autopsy table under a surgical lamp, a trolley, scrub sinks by the door, cold white light."""
    spec, L, D, H = _dims("morgue")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _clinic_style("ice_dim", "ice"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 3.2, yf - 0.02, -90, N.mortuary_wall, 4, 3)
    place(b, 8.8, yf - 0.02, -90, N.mortuary_wall, 4, 3)
    place(b, 6.0, 7.2, 0, N.autopsy_table)
    place(b, 5.45, 7.2, 0, surgical_lamp, H - 0.05)
    place(b, 10.2, 4.6, 90, N.hospital_trolley)
    place(b, 1.9, WF + 0.4, 90, F.steel_sink_unit, 1.6, 0.7)
    place(b, 3.7, WF + 0.4, 90, F.steel_sink_unit, 1.6, 0.7)
    place(b, xr - 0.02, 10.0, 180, F.wall_screen, 1.4, 0.8, "scr_lab", z=1.8)
    place(b, xr - 0.26, 12.4, 180, F.locker_row, 3, 0.6, 2.0, 0.5, IVORY)
    wall_label(b, 6.0, WF + 0.02, 2.3, (0, 1, 0), "eq_cold", 0.7)
    ceiling_panels(b, L, D, H, 2, 3, "ice", 1.4, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------------------------------------------------------ counselling
def counselling(name: str = "SM_SHIP_Counselling"):
    """12 x 16: a quiet room — warm wood and fabric, a rug with a sofa and armchairs round a low table, bookshelves, plants, a ring lamp on the wall, and in a corner a desk for the
    counsellor and the chaplain's two armchairs. Warm light."""
    spec, L, D, H = _dims("counselling")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="covering", wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.1, ceil=COMPOSITE, accent="warm_dim", cove="white_warm", strip="white_warm", ribs=False, seams=False)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 4.6, 5.8, 0, G.rug, 4.6, 3.4, FABRIC_RUST, FABRIC_SAND)
    place(b, 4.6, 7.0, -90, F.sofa, 2.2, FABRIC_NAVY, True)
    place(b, 2.5, 5.0, 0, F.armchair, FABRIC_GREY)
    place(b, 6.7, 5.0, 180, F.armchair, FABRIC_GREY)
    place(b, 4.6, 5.2, 0, F.low_table, 1.1, 0.6, 0.38, WOOD)
    for (x, y, yaw) in ((9.4, 12.4, 0), (11.0, 12.4, 180)):                                # the chaplain's corner
        place(b, x, y, yaw, F.armchair, FABRIC_SAND)
    place(b, 10.2, 12.4, 0, F.low_table, 0.5, 0.5, 0.45, WOOD)
    place(b, 3.4, 12.6, 90, F.desk, 1.5, 0.7, 0.76, WOOD, True)                            # the counsellor's desk, a visitor's chair across it
    place(b, 3.4, 11.6, 90, F.chair, FABRIC_GREY)
    place(b, 3.4, 13.6, -90, F.chair, FABRIC_NAVY)
    for k in range(2):
        place(b, 1.5 + k * 3.0, yf - 0.2, -90, F.shelf, 2.4, 0.34, 2.1, 5, WOOD, True, 5 + k, True)
    place(b, xl + 0.4, 9.4, 0, F.potted_plant, 1.4, 3)
    place(b, xr - 0.4, 3.0, 0, F.potted_plant, 1.2, 4)
    ceiling_panels(b, L, D, H, 2, 2, "white_warm", 1.8, 1.0, 0.6, LAMP_DIM)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- brig
def brig(name: str = "SM_SHIP_Brig"):
    """24 x 16: the guardroom by the door (a raised watch desk with its screens, a weapon rack, a bench), and along the far wall five cells (a bunk, a steel toilet, a bolted stool, a
    barred front with a lock and a status lamp); red-white light, a hazard line across the floor at the bars."""
    spec, L, D, H = _dims("brig")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="red_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, xc in enumerate((2.2, 5.7, 9.2, 12.7, 16.2)):
        place(b, xc, yf - 0.05, -90, N.brig_cell, 3.2, 3.5, 3.2, "red" if k in (1, 3) else "green")
    b.emit.label((9.2, yf - 3.45, 0.006), 17.0, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    place(b, 20.3, 8.6, 180, N.counter_desk, 3.4, 0.9, 1.1)
    place(b, 21.9, 8.6, 180, F.chair, FABRIC_GREY)
    place(b, xr - 0.02, 3.4, 180, G.weapon_rack, 2.0, 4, 1.9, 2)
    place(b, 1.2, 3.0, 0, F.bench, 2.0, 0.42, 0.46, FABRIC_GREY)
    place(b, xr - 0.02, 12.6, 180, F.wall_screen, 1.8, 1.0, "scr_ship", z=1.8)
    wall_label(b, 17.0, WF + 0.02, 2.3, (0, 1, 0), "eq_inmate", 0.7)
    ceiling_panels(b, L, D, H, 6, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------- security office
def security_office(name: str = "SM_SHIP_SecurityOffice"):
    """16 x 16: the master-at-arms' office — a counter by the door with the duty marine behind it, a camera wall of screens, desk pods, the watch commander's desk on the far wall, a
    case of arms-room keys and an evidence shelf, a map table."""
    spec, L, D, H = _dims("security_office")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="red_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 3.0, 2.0, -90, N.counter_desk, 4.4, 0.9, 1.1)                                  # the duty marine's counter by the door (x 0.8 .. 5.2)
    place(b, 3.0, 3.2, -90, F.chair, FABRIC_GREY)
    for k in range(3):                                                                     # the camera wall
        place(b, xl + 0.02, 5.0 + k * 3.0, 0, F.wall_screen, 2.6, 1.4, ("scr_map", "scr_tac", "scr_data")[k], z=1.5)
    for (x, y) in ((8.0, 9.0), (11.0, 9.0)):                                               # desk pods
        place(b, x, y, 90, H8.desk_pod, 1.4, 0.8)
        place(b, x, y - 0.9, 90, F.chair, FABRIC_NAVY)
    place(b, 12.4, 12.6, -90, F.desk, 2.0, 0.8, 0.78, LAMINATE, True)                      # the watch commander's desk, his back to the far wall
    place(b, 12.4, 13.6, -90, F.chair, FABRIC_GREY)
    place(b, 12.4, 12.6, -90, F.monitor, 0.6, 0.36, "scr_tac", True, z=0.78)
    place(b, xr - 0.28, 5.0, 180, F.locker_row, 5, 0.5, 1.95, 0.5, COMPOSITE)
    place(b, 4.0, yf - 0.25, -90, F.shelf, 2.4, 0.4, 2.0, 4, STEEL, False, 3, True)
    place(b, 8.0, 13.4, 0, G.holo_table, 0.8, 0.9)
    wall_label(b, 8.0, WF + 0.02, 2.4, (0, 1, 0), "eq_evidence", 0.8)
    ceiling_panels(b, L, D, H, 3, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
