"""ASN Aquila interior kit: the workshops of the lower decks (NAVE-2, Deck 11) — the fabrication shop (metal printers, a casting furnace, a robot cell, machine tools, a
measuring table) and the repair bay (hull plates, the training mock-up, welding cells, EVA suits, cable drums, spare pumps). The Machine Shop is the older workshop
(ship_rooms_work.py). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations


import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture4 as K
import ship_furniture7 as K7
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import T
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, FABRIC_GREY, LAMP, LAMP_DIM, LAMP_HOT, STEEL, STRUCT, TRIM, SParts,
                      lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, place)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "engineering_dim", cove: str = "white_warm", lo: str = COMPOSITE, hi: str = COMPOSITE) -> Style:
    return Style(floor=DECK, floor_mode="plates", wall_lo=lo, wall_hi=hi, wain_h=1.2, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- fabrication shop
def fab_shop(name: str = "SM_SHIP_FabShop"):
    """28 x 16 x 3.8: where the ship makes what it lacks. Three metal printers in a row on the far wall and the casting corner at the far right (furnace under its hood, the mould
    rack and the quench tank); a robot cell in the middle with its conveyor and the output bins; feedstock spools and a plate rack along the left wall; two milling machines, a
    lathe and a bench against the right wall; the measuring table by the door; a gantry along the middle of the room."""
    spec, L, D, H_ = _dims("fab_shop")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("engineering_dim", "white_cool", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (3.6, 6.4, 9.2):
        place(b, x, yf - 0.9, -90, K7.printer_3d, 2.4, 1.8, 2.3)
    place(b, 24.0, yf - 0.9, -90, K7.furnace)
    place(b, 24.0, yf - 0.9, -90, F.hood, 1.8, 1.8, 2.05, H_)
    place(b, 20.4, yf - 0.3, -90, K7.mould_rack, 1.6)
    # the robot cell: a conveyor along x, the arm reaching over it from the far side, bins at its end, a hazard border on the floor
    place(b, 15.5, 8.8, 0, K7.conveyor, 8.0)
    place(b, 15.0, 11.4, -90, K7.robot_arm)
    place(b, 21.6, 8.8, 180, G.parts_bins, 2.0, 1.9, 0.5, 4)
    for (x0, x1, y0, y1) in ((11.0, 20.0, 7.6, 13.0),):
        lamp_strip(b.emit, (x0, y0, 0.004), (x1, y0, 0.004), 0.06, 0.004, "amber_dim", LAMP_DIM)
        lamp_strip(b.emit, (x0, y1, 0.004), (x1, y1, 0.004), 0.06, 0.004, "amber_dim", LAMP_DIM)
        lamp_strip(b.emit, (x0, y0, 0.004), (x0, y1, 0.004), 0.06, 0.004, "amber_dim", LAMP_DIM)
        lamp_strip(b.emit, (x1, y0, 0.004), (x1, y1, 0.004), 0.06, 0.004, "amber_dim", LAMP_DIM)
    # a large-format printer for hull parts in the left half, a cage for the finished parts and a quality bench on the right
    place(b, 6.0, 7.4, 0, K7.printer_3d, 3.6, 2.4, 2.8)
    place(b, 6.0, 5.0, 90, F.stool, 0.19, 0.62, FABRIC_GREY)
    place(b, 24.0, 11.4, 180, G.parts_bins, 2.0, 1.9, 0.5, 8)
    place(b, 20.0, 6.0, 0, F.table, 2.4, 0.9, 0.9, STEEL, TRIM, False)
    place(b, 20.0, 6.0, 0, F.monitor, 0.5, 0.3, "scr_data", False, z=0.9)
    place(b, 20.0, 5.0, 90, F.stool, 0.19, 0.62, FABRIC_GREY)
    # left wall: feedstock and plates
    place(b, xl + 0.3, 4.0, 0, K7.spool_rack, 2.4, 2.0)
    place(b, xl + 0.3, 7.0, 0, K7.spool_rack, 2.4, 2.0)
    place(b, xl + 0.45, 10.4, 0, F.rack, 3.0, 0.9, 2.6, 4, 12, 0.8, [CRATE_GREY, CRATE_OLIVE])
    b.emit.label_fit((xl + 0.002, 5.5, 2.4), 1.2, "eq_stores", (1, 0, 0))
    # right wall: the machine tools and a bench
    place(b, xr - 0.7, 4.0, 180, G.mill, 1.3, 1.0)
    place(b, xr - 0.7, 6.4, 180, G.mill, 1.3, 1.0)
    place(b, xr - 0.6, 9.4, 180, G.lathe, 2.4, 0.9, 1.05)
    place(b, xr - 0.55, 12.2, 180, G.workbench, 2.4, 0.8, 0.95, True)
    # by the door: the measuring table, a rolling chest, extinguisher and first aid
    place(b, 22.0, 2.7, 90, K7.cmm_table)
    place(b, 13.0, 1.4, 180, K.tool_chest, 0.8, 0.5, 1.0)
    with b.at(T(1.0, 0.0, 0.0)):
        G.overhead_rail(b, 26.0, 5.6, H_ - 0.5, 14.0)
    for x in (3.0, 9.0, 15.0, 21.0, 26.0):
        b.soft.cyl((x, 5.6, H_ - 0.5), (x, 5.6, H_), 0.03, TRIM, seg=6)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 12.2, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 12.9, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 13.5, 20.0, 2, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "conduits", "vent"))
    dress_wall(b, "near", L, D, H_, 24.5, 27.5, 3, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "panelboard"))
    dress_wall(b, "far", L, D, H_, 12.0, 19.0, 4, accent="engineering", accent_dim="engineering_dim", kinds=("panelboard", "vent", "conduits"))
    ceiling_services(b, L, D, H_, [(3.0, "duct"), (10.5, "tray"), (14.4, "pipes")], 1.0, 27.0, 8)
    ceiling_panels(b, L, D, H_, 5, 3, "white_cool", 1.6, 1.3, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- repair bay
def repair_bay(name: str = "SM_SHIP_RepairBay"):
    """32 x 16 x 3.7: the damage control depot. Racks of hull plates and the two training mock-ups on the far wall, the EVA suits, cable drums and shoring props along the left wall,
    a long work table with a plasma cutter in the middle, two welding cells and the spare pumps on pallets on the right, a gantry down each side of the room and a row of tool
    chests and benches by the entrance wall."""
    spec, L, D, H_ = _dims("repair_bay")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("red_dim", "white_warm", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (3.4, 6.2, 9.0):
        place(b, x, yf - 0.45, -90, K7.plate_rack, 2.4, 2.2, 6)
    place(b, 15.0, yf - 0.1, -90, K7.hull_mockup, 3.4, 2.4)
    place(b, 20.4, yf - 0.1, -90, K7.hull_mockup, 3.4, 2.4)
    b.emit.label_fit((17.7, yf - 0.01, 3.1), 2.4, "eq_dc", (0, -1, 0))
    place(b, xl + 0.2, 6.0, 0, K7.eva_rack, 4)
    for k, y in enumerate((9.6, 11.0, 12.6)):
        place(b, 2.2, y, 0, K7.cable_drum, 0.6, 0.7, (CRATE_ORANGE, CRATE_BLUE, CRATE_OLIVE)[k])
    for k, x in enumerate((3.0, 3.5, 4.0, 4.5)):                                                                       # shoring props leaning on the wall by the plate racks
        b.body.cyl((x + 0.2, 3.0, 0.0), (x + 0.2, 3.0, 2.3), 0.05, CRATE_ORANGE, seg=8)
        b.soft.cyl((x + 0.2, 3.0, 2.3), (x + 0.2, 3.0, 2.38), 0.08, STEEL, seg=8)
    for k, (x, y) in enumerate(((5.2, 8.0), (8.2, 8.0), (5.2, 11.4), (8.2, 11.4))):                                      # spare hull plates on pallets
        place(b, x, y, 90 * (k % 2), F.pallet, 1.2, 0.8)
        place(b, x, y, 90 * (k % 2) + 3 * k, K7.plate_stack, 1.1, 0.7, 4 + k % 3, z=0.145)
    place(b, 12.2, 10.6, 0, K7.jib_crane, 2.6, H_ - 0.1)
    place(b, 15.0, 5.4, 0, F.table, 4.0, 1.1, 0.9, STEEL, TRIM, False)
    with b.at(T(15.0, 5.4, 0.9)):                                                                                      # the plasma cutter, a sheet being cut, offcuts, the clamps
        b.body.box((-1.7, -0.3, 0.0), (-1.1, 0.3, 0.3), CRATE_BLUE)
        b.soft.box((-0.8, -0.4, 0.0), (0.7, 0.4, 0.04), CRATE_GREY)
        b.soft.box((-0.1, -0.02, 0.04), (0.3, 0.02, 0.045), CRATE_ORANGE)
        b.soft.box((0.9, -0.2, 0.0), (1.4, 0.2, 0.08), STEEL)
        b.emit.lamp_box((-1.5, 0.3, 0.18), (-1.4, 0.32, 0.22), "green", LAMP)
    for k, y in enumerate((7.0, 3.6)):
        place(b, xr - 1.4, y + 4.4, 180, G.welding_bay, 3.2, 2.6)
    place(b, 25.0, 4.0, 90, F.pallet, 1.2, 0.8)
    place(b, 25.0, 4.0, 90, H.pump_set, 1.6, "engineering", z=0.145)
    place(b, 28.0, 3.0, 90, F.pallet, 1.2, 0.8)
    place(b, 28.0, 3.0, 90, H.pump_set, 1.6, "engineering", z=0.145)
    for y in (4.6, 11.4):
        with b.at(T(1.0, 0.0, 0.0)):
            G.overhead_rail(b, 30.0, y, H_ - 0.5, 9.0 if y < 8 else 22.0)
        for x in (3.0, 9.0, 15.0, 21.0, 27.0, 31.0):
            b.soft.cyl((x, y, H_ - 0.5), (x, y, H_), 0.03, TRIM, seg=6)
    place(b, 12.0, 1.4, 180, K.tool_chest, 0.8, 0.5, 1.0)
    place(b, 19.0, 0.9, 90, G.workbench, 3.0, 0.8, 0.95, True)
    place(b, 23.0, 0.7, 180, K.tool_chest, 0.8, 0.5, 1.0)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 14.4, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 15.2, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="red", accent_dim="red_dim", kinds=("plain", "vent", "safety", "panelboard"))
    dress_wall(b, "near", L, D, H_, 25.0, 31.5, 2, accent="red", accent_dim="red_dim", kinds=("plain", "conduits", "vent"))
    dress_wall(b, "right", L, D, H_, 1.0, 5.0, 3, accent="red", accent_dim="red_dim", kinds=("plain", "panelboard"))
    ceiling_services(b, L, D, H_, [(3.0, "duct"), (8.0, "pipes")], 1.0, 31.0, 6)
    ceiling_panels(b, L, D, H_, 6, 3, "white_warm", 1.6, 1.3, 0.6, LAMP_HOT)
    return b.build(name)
