"""ASN Aquila interior kit: the medical rooms of Deck 6 (docs/BIBBIA.md §6: Medbay, surgery, quarantine, pharmacy) — the surgery, the quarantine ward
and the pharmacy. The Medbay itself is the older, hand-built room (art/blender/medbay.py). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furn4 as MD
import ship_furniture as F
import ship_furniture2 as G
import ship_spec as SPEC
from bridge3_lib import T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TILE, TRIM, WOOD, SParts, lamp_strip)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, place
from ship_rooms_service import cart


def clinic_style(accent: str = "medical_dim", cove: str = "medical") -> Style:
    """The medical rooms' shell (NAVE-3): not a 2020 hospital — ivory walls over a dark deck floor, a brushed rail at 1.2 m, a rib of water-green light every 4 m on the end walls and a cove
    of the same light (the medical colour of docs/STILE.md, #2EC4B6)."""
    return Style(floor=DECK, floor_mode="plates", wall_lo=IVORY, wall_hi=IVORY, wain_h=1.2, ceil=IVORY, accent=accent, cove=cove, ribs=True, rib_mat=TRIM, skirt=STRUCT)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ---------------------------------------------------------------------------------------------------------------- pieces
def op_table(b: SParts) -> None:
    """An operating table, its long axis along x (the head at -x), origin on the floor under its column (ship_furn4.op_table)."""
    MD.op_table(b)


def surgical_lamp(b: SParts, z_ceil: float = 3.6) -> None:
    """A twin surgical lamp hung from the ceiling over the origin (ship_furn4.surgical_lamp): two jointed arms, two broad lit heads of seven lenses over the table (z 2.3)."""
    MD.surgical_lamp(b, z_ceil, 0.6, 2.3)


def anesthesia_cart(b: SParts) -> None:
    """An anaesthesia machine on wheels facing +x (ship_furn4.anesthesia_machine)."""
    MD.anesthesia_machine(b)


def instrument_tray(b: SParts) -> None:
    """An instrument trolley (ship_furn4.instrument_trolley): two steel trays, the upper one laid with instruments."""
    MD.instrument_trolley(b, 3)


# ------------------------------------------------------------------------------------------------------------------ surgery
def surgery(name: str = "SM_SHIP_Surgery"):
    """16 x 16: two operating tables under surgical lamps, anaesthesia machines at the heads, instrument tables, scrub sinks by the door, cabinets and screens."""
    spec, L, D, H = _dims("surgery")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = clinic_style()
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, x in enumerate((5.0, 11.0)):
        place(b, x, 9.0, 0, op_table)
        place(b, x, 9.0, 0, surgical_lamp, H - 0.05)
        place(b, x - 1.5, 9.0, 0, anesthesia_cart)
        place(b, x + 0.3, 7.7, 0, instrument_tray)
    place(b, 8.0, 12.6, -90, F.monitor, 0.6, 0.35, "scr_lab", True, z=1.2)
    # two scrub sinks by the door, a supply trolley
    for x in (1.9, 3.7):
        place(b, x, WF + 0.4, 90, F.steel_sink_unit, 1.6, 0.7)
    place(b, 8.6, 1.4, 90, cart)
    # the far wall: counters with glass-fronted cabinets above, monitors
    for x in (2.6, 6.2, 9.8, 13.4):
        place(b, x, yf - 0.36, -90, F.counter, 3.5, 0.7, 0.92, LAMINATE, COMPOSITE, True, False)
    b.body.box((0.8, yf - 0.42, 1.55), (L - 0.8, yf, 2.5), IVORY)
    for k in range(int((L - 1.6) / 1.2)):
        b.fine.box((0.82 + k * 1.2, yf - 0.435, 1.58), (0.82 + (k + 1) * 1.2 - 0.05, yf - 0.42, 2.47), LAMINATE)
    b.emit.lamp_box((0.8, yf - 0.44, 1.50), (L - 0.8, yf - 0.40, 1.53), "medical", LAMP)
    place(b, 4.6, yf - 0.55, -90, F.monitor, 0.6, 0.34, "scr_lab", True, z=0.92)
    place(b, 11.4, yf - 0.55, -90, F.monitor, 0.6, 0.34, "scr_map", True, z=0.92)
    # sterile cabinets on the right wall, screens on the left wall
    place(b, xr - 0.26, 3.4, 180, F.locker_row, 5, 0.6, 2.0, 0.5, IVORY)
    place(b, xl + 0.02, 9.0, 0, F.wall_screen, 2.2, 1.2, "scr_lab", z=1.85)
    place(b, xr - 0.02, 12.0, 180, F.wall_screen, 2.0, 1.1, "scr_map", z=1.85)
    ceiling_panels(b, L, D, H, 4, 3, "white_cool", 1.2, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------- quarantine
def quarantine(name: str = "SM_SHIP_Quarantine"):
    """24 x 16: an air-lock zone by the door, a nurse station, and six isolation cells along the far wall (glass fronts, a bed, a monitor each)."""
    spec, L, D, H = _dims("quarantine")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = clinic_style()
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    yc0 = 9.5                                              # the cells' glass front
    pitch, x0 = 3.7, 0.4
    for k in range(7):                                     # partitions between and beside the cells
        x = x0 + k * pitch
        b.body.box((x - 0.05, yc0, 0.0), (x + 0.05, yf, H), COMPOSITE)
        b.fine.box((x - 0.06, yc0 - 0.04, 0.0), (x + 0.06, yc0, H), TRIM)
    for k in range(6):
        xa, xb = x0 + k * pitch + 0.05, x0 + (k + 1) * pitch - 0.05
        xm = (xa + xb) / 2
        b.body.box((xa, yc0 - 0.03, 0.0), (xb, yc0 + 0.03, 0.9), COMPOSITE)                # the low front
        b.body.box((xa, yc0 - 0.03, 2.55), (xb, yc0 + 0.03, H), COMPOSITE)                 # the header
        b.fine.box((xa, yc0 - 0.012, 0.9), (xa + 0.55, yc0 + 0.012, 2.55), GLASS)         # glass either side of the opening
        b.fine.box((xb - 0.55, yc0 - 0.012, 0.9), (xb, yc0 + 0.012, 2.55), GLASS)
        b.fine.box((xm - 0.5, yc0 - 0.05, 0.0), (xm - 0.45, yc0 + 0.05, 2.55), TRIM)      # the door frame (an opening 1.0 m wide)
        b.fine.box((xm + 0.45, yc0 - 0.05, 0.0), (xm + 0.5, yc0 + 0.05, 2.55), TRIM)
        b.emit.lamp_box((xm - 0.12, yc0 - 0.055, 2.62), (xm + 0.12, yc0 - 0.05, 2.7), "red" if k in (1, 4) else "green", LAMP)
        place(b, xm - 0.55, yf - 1.16, -90, MD.hospital_bed, 20 + k, [FABRIC_NAVY, FABRIC_GREY, FABRIC_SAND][k % 3])
        place(b, xm + 0.35, yf - 0.55, 0, MD.iv_stand, k)
        place(b, xm - 0.55 - 0.85, yf - 0.3, -90, MD.bedside_cabinet, k)
        place(b, xm + 1.2, yf - 0.02, -90, F.wall_screen, 0.7, 0.4, "scr_lab", z=1.5)
        place(b, xm + 1.1, yc0 + 1.6, 0, F.chair, FABRIC_GREY)
        b.emit.lamp_box((xa + 0.2, yc0 + 0.3, H - 0.08), (xb - 0.2, yc0 + 0.36, H - 0.05), "medical_dim", LAMP_DIM)
    # the air-lock zone: hazard lines across the floor, a decontamination cabinet, gloves and gowns on the wall
    b.emit.label((10.0, 3.0, 0.006), 6.0, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    b.emit.label((10.0, 3.35, 0.006), 6.0, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    place(b, 15.2, WF + 0.5, 90, F.locker_row, 4, 0.6, 2.0, 0.5, IVORY)
    place(b, 6.0, WF + 0.4, 90, F.steel_sink_unit, 1.6, 0.7)
    # the nurse station: a desk with monitors, chairs, a supply cart
    place(b, 15.0, 6.2, 0, F.desk, 2.4, 0.8, 0.78, LAMINATE, False)
    for k, tile in enumerate(("scr_lab", "scr_map", "scr_lab")):
        place(b, 15.35, 5.5 + k * 0.7, 0, F.monitor, 0.5, 0.3, tile, True, z=0.78)
    place(b, 13.9, 6.2, 0, F.chair, FABRIC_GREY)
    place(b, 18.2, 3.0, 90, cart)
    place(b, xr - 0.02, 6.0, 180, F.wall_screen, 2.6, 1.4, "scr_lab", z=1.8)
    b.emit.label_fit((xl + 0.002, 5.0, 2.6), 0.9, "hazard", (1, 0, 0))
    ceiling_panels(b, L, D, H, 5, 2, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------- pharmacy
def pharmacy(name: str = "SM_SHIP_Pharmacy"):
    """12 x 16: a counter across the room with a screen above, shelves of medicines behind it on three walls, refrigerators, a desk."""
    spec, L, D, H = _dims("pharmacy")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = clinic_style()
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for (xa, xb) in ((0.35, 4.8), (7.2, L - 0.35)):                     # the counter line at y 4.2 (the gap in front of the door stays open)
        place(b, (xa + xb) / 2, 4.2, 90, F.counter, xb - xa, 0.7, 1.05, LAMINATE, COMPOSITE, True, False)
        with b.at(frame((xa + xb) / 2, 4.2, 1.05, 90)):
            G.cage_wall(b, xb - xa, 1.5, 0.1)
    b.emit.lamp_box((0.35, 4.0, 2.58), (L - 0.35, 4.05, 2.62), "medical", LAMP)
    b.emit.label_fit((6.0, 4.02, 2.8), 1.6, "room_pharmacy", (0, -1, 0))
    for k in range(3):                                                  # shelves of medicines on the side walls and the far wall
        place(b, xl + 0.2, 6.6 + 2.9 * k, 0, F.shelf, 2.8, 0.4, 2.4, 6, STEEL, True, 60 + k, True)
        place(b, xr - 0.2, 6.6 + 2.9 * k, 180, F.shelf, 2.8, 0.4, 2.4, 6, STEEL, True, 70 + k, True)
    for k in range(2):
        place(b, 3.0 + 6.0 * k, yf - 0.2, -90, F.shelf, 2.8, 0.4, 2.4, 6, STEEL, True, 80 + k, True)
    place(b, 6.0, yf - 0.45, -90, G.sample_fridge, 0.9, 0.75, 2.0)
    place(b, 6.0, 8.4, 90, F.desk, 1.6, 0.7, 0.78, LAMINATE, True)
    place(b, 6.0, 8.4, 90, F.monitor, 0.5, 0.3, "scr_menu", False, z=0.78)
    place(b, 6.0, 7.4, 90, F.chair, FABRIC_GREY)
    place(b, xl + 0.02, 2.0, 0, F.wall_screen, 1.6, 0.9, "scr_dir", z=1.8)
    ceiling_panels(b, L, D, H, 2, 3, "white_cool", 1.4, 1.0, 0.5, LAMP_HOT)
    return b.build(name)
