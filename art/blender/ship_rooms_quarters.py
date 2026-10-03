"""ASN Aquila interior kit: the officers' deck (NAVE-2, Deck 3) — the officers' staterooms, the wardroom (mess and lounge) and the gymnasium. Frames and sizes: ship_rooms.py /
ship_spec.py."""
from __future__ import annotations


import ship_cabin as SC
import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture5 as K5
import ship_furniture8 as K8
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import T
from ship_lib import (COMPOSITE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMP, LAMP_DIM, LAMP_HOT, RUBBER, STEEL,
                      STRUCT, TRIM, WOOD, SParts)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, place)
from ship_rooms_hub import on_wall
from ship_rooms_work import CAB_XL, CAB_XR, CAB_Y

_DW, _DH = 0.95, 2.1                    # a cabin door (the hatches of the crew cabins)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ---------------------------------------------------------------------------------------------------------------------- staterooms
STATEROOM_BED_Y = tuple(round((0.06 if k == 0 else yc - 2.0 + 0.06) + 0.55, 2) for k, yc in enumerate(CAB_Y))      # the beds' middle across the four cabins of a side


def staterooms(name: str = "SM_SHIP_Staterooms"):
    """20 x 16 x 3.2: eight officers' staterooms (four a side) round a hall (ship_cabin.py): each with a single bed and its nightstand under a viewport with curtains, a desk with a screen, a
    lamp and a plant, a wardrobe, a basin with a lit mirror, a rug, a light of its own; the hall has two sofas and two armchairs on a rug round a coffee table, a dining table under its
    pendants with a place laid, a sideboard with a coffee machine, a shelf, pictures between the hatches, plants and a wall screen. The layout of the crew cabins (the hatches are the same)."""
    spec, L, D, H_ = _dims("staterooms")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent="warm_dim", cove="white_warm",
               ribs=False, skirt=WOOD)
    build_shell(b, spec, st)
    SC.quarters_block(b, spec, True, CAB_Y, CAB_XL, CAB_XR, 20)
    SC.hall_dress(b, spec, True, CAB_Y, CAB_XL, CAB_XR)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- wardroom
def wardroom(name: str = "SM_SHIP_Wardroom"):
    """24 x 16 x 3.6: the officers' mess and lounge. Two long dining tables (ten places each) with a sideboard on the left half; the right half is the lounge: two conversation
    groups on rugs, a bar with its back bar and stools on the right wall, an aquarium on the far wall, shelves of books, a wall of screens showing the stars."""
    spec, L, D, H_ = _dims("wardroom")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent="warm_dim", cove="white_warm", ribs=False,
               skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for y in (4.4, 10.8):
        place(b, 6.4, y, 0, F.table, 4.4, 1.2, 0.76, WOOD, TRIM, False)
        with b.at(T(6.4, y, 0.76)):
            b.emit.lamp_box((-1.8, -0.01, 0.0), (1.8, 0.01, 0.004), "white_warm", LAMP_DIM)
            for k in range(3):
                b.soft.cyl((-1.2 + k * 1.2, 0.0, 0.0), (-1.2 + k * 1.2, 0.0, 0.2), 0.05, DGLASS, seg=8)
        for k in range(4):
            x = 6.4 - 1.65 + k * 1.1
            place(b, x, y - 0.95, 90, F.chair, FABRIC_RUST)
            place(b, x, y + 0.95, -90, F.chair, FABRIC_RUST)
        place(b, 3.7, y, 0, F.chair, FABRIC_NAVY)
        place(b, 9.1, y, 180, F.chair, FABRIC_NAVY)
    place(b, 6.4, yf - 0.4, -90, F.counter, 4.0, 0.6, 0.92, WOOD, COMPOSITE, True, False)
    place(b, 6.4, yf - 0.02, -90, F.wall_screen, 3.4, 1.2, "scr_menu", z=2.0)
    # the lounge: two groups round low tables, the bar on the right wall, the aquarium, shelves
    for k, yc in enumerate((4.6, 11.4)):
        place(b, 16.6, yc, 0, G.rug, 5.2, 4.2, FABRIC_NAVY if k == 0 else FABRIC_RUST, FABRIC_SAND)
        place(b, 16.6, yc, 0, F.low_table, 1.2, 0.7, 0.4, WOOD)
        place(b, 14.9, yc, 0, F.sofa, 2.4, FABRIC_RUST if k == 0 else FABRIC_NAVY)
        place(b, 18.3, yc - 1.1, 135, F.armchair, FABRIC_SAND)
        place(b, 18.3, yc + 1.1, -135, F.armchair, FABRIC_SAND)
    place(b, xr - 0.5, 8.0, 180, G.bar_counter, 4.6, 0.7, 1.08)
    for k in range(4):
        place(b, xr - 1.7, 6.3 + k * 1.1, 180, G.bar_stool, 0.72, FABRIC_RUST)
    place(b, xr - 0.02, 8.0, 180, G.back_bar, 4.6, 2.1, 0.34, 6)
    place(b, 17.6, yf - 0.55, -90, H.aquarium, 3.2, 0.8, 2.1, 3)
    place(b, xl, 8.0, 0, F.shelf, 2.4, 0.34, 2.0, 5, WOOD, True, 4)
    place(b, 2.0, 14.6, 0, F.potted_plant, 1.4, 2)
    place(b, 21.5, 14.6, 0, F.potted_plant, 1.4, 3)
    b.emit.label_fit((12.4, WF + 0.002, 1.9), 1.0, "eq_notice", (0, 1, 0))
    for x in (7.0, 17.0):
        for y in (3.0, 8.0, 13.0):
            F.ceiling_light_panel(b, x - 0.9, x + 0.9, y - 0.3, y + 0.3, H_ - 0.05, "white_warm", LAMP)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- gym
def gym(name: str = "SM_SHIP_Gym"):
    """24 x 16 x 3.7: the crew's gymnasium. A row of five treadmills facing screens on the far wall, two weight benches with their racks, the exercise corner (mat, pull-up frame,
    heavy bag, dumbbells) at the right, a wall of mirrors on the left, lockers, benches and a water cooler by the door."""
    spec, L, D, H_ = _dims("gym")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, x in enumerate((3.0, 5.4, 7.8, 10.2, 12.6)):
        place(b, x, yf - 1.15, 90, K8.treadmill)
        place(b, x, yf - 0.02, -90, F.wall_screen, 1.5, 0.85, ("scr_star", "scr_map", "scr_ship", "scr_data", "scr_wave")[k], z=2.0)
    b.soft.box((1.2, yf - 2.5, 0.0), (14.4, yf - 0.1, 0.02), RUBBER)
    place(b, 6.0, 7.0, 0, K8.weight_bench)
    place(b, 6.0, 4.2, 0, K8.weight_bench)
    b.soft.box((3.3, 2.6, 0.0), (8.7, 8.5, 0.015), RUBBER)
    place(b, 20.4, 7.6, 180, K5.training_corner, H_)
    for y0 in (2.5, 6.5):                                                                                      # the mirrors on the left wall
        b.body.box((xl, y0, 0.55), (xl + 0.03, y0 + 3.6, 2.5), TRIM)
        b.soft.box((xl + 0.03, y0 + 0.05, 0.6), (xl + 0.035, y0 + 3.55, 2.45), STEEL)
    place(b, xr - 0.35, 3.4, 180, F.locker_row, 6, 0.5, 2.0, 0.5, COMPOSITE)
    place(b, 15.6, 1.4, 90, F.bench, 2.6, 0.45, 0.46, FABRIC_GREY)
    b.body.box((18.4, WF + 0.05, 0.0), (19.0, WF + 0.4, 1.1), COMPOSITE)
    b.soft.cyl((18.7, WF + 0.22, 1.1), (18.7, WF + 0.22, 1.5), 0.15, DGLASS, seg=12)
    b.emit.lamp_box((18.5, WF + 0.401, 0.7), (18.9, WF + 0.405, 0.74), "cyan", LAMP_DIM)
    b.emit.label_fit((14.2, WF + 0.002, 2.0), 1.0, "eq_watch", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 21.0, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 7.0, 1, accent="cyan", accent_dim="cyan_dim", kinds=("plain", "vent", "safety"))
    dress_wall(b, "right", L, D, H_, 8.0, 15.5, 2, accent="cyan", accent_dim="cyan_dim", kinds=("plain", "panelboard", "vent"))
    ceiling_services(b, L, D, H_, [(3.0, "duct")], 1.0, 23.0, 3)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
