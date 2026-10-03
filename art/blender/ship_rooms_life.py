"""ASN Aquila interior kit (NAVE-3): the rooms where the crew lives off duty — the barber's and tailor's, the bar, the chapel, the ship's store, the simulator bay — the quarters the
redesign adds (the crew's berthing bays, the senior officers' suites, the officers' single cabins) and the drone bay. Frames and sizes: ship_rooms.py / ship_spec.py / ship_spec3.py."""
from __future__ import annotations

import ship_cabin as SC
import ship_furn3 as N3
import ship_mess as MS
import ship_furniture as F
import ship_decor as DC
import ship_spec3 as SPEC3
import ship_themes as TH
import ship_furniture2 as G
import ship_furniture3 as H3
import ship_furniture4 as F4
import ship_furniture8 as K8
import ship_furniture9 as N
import ship_spec as SPEC
from bridge3_lib import T
from ship_lib import (CARPET_SAND, CARPET_SLATE, CERAMIC, LEATHER_NAVY, OAK, PLASTER_IVORY, PLASTER_SLATE, WALNUT, WEAVE_SLATE, BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMINATE, LAMP,
                      LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TILE, TRIM, WOOD, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_label

_DW, _DH = 1.0, 2.1                     # a cabin's hatch


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _warm_style(floor: str = FABRIC_GREY, wall_lo: str = WOOD, accent: str = "warm_dim") -> Style:
    return Style(floor=floor, floor_mode="covering", seams=False, wall_lo=wall_lo, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent=accent, cove="white_warm", ribs=False, skirt=WOOD)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------- barber & tailor
def barber(name: str = "SM_SHIP_Barber"):
    """12 x 16: two barber's chairs in front of a lit mirror wall (the near wall, x 1-5 and 7-11), waiting benches along the right wall; at the far end the tailor's corner — a
    cutting table, a sewing machine on a desk, a dress form, rolls of cloth on shelves, a fitting mirror."""
    spec, L, D, H = _dims("barber")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _warm_style(TILE, COMPOSITE, "warm_dim"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for (xa, xb) in ((1.0, 5.0), (7.0, 11.0)):                                             # the mirrors: a lit frame, a dark glass, counters with tools beneath
        b.body.box((xa, WF, 0.95), (xb, WF + 0.03, 2.5), TRIM)
        b.fine.box((xa + 0.05, WF + 0.03, 1.0), (xb - 0.05, WF + 0.04, 2.45), DGLASS)
        b.emit.lamp_box((xa, WF + 0.03, 2.5), (xb, WF + 0.1, 2.55), "white_warm", LAMP)
        place(b, (xa + xb) / 2, WF + 0.4, 90, F.counter, xb - xa, 0.6, 0.92, LAMINATE, COMPOSITE, True, False)
    for x in (3.0, 9.0):
        place(b, x, 2.8, -90, N.barber_chair)
    for k in range(3):
        place(b, xr - 0.4, 7.0 + k * 0.9, 180, F.chair, FABRIC_NAVY)
    place(b, xr - 1.4, 8.0, 180, F.low_table, 0.5, 1.4, 0.42, WOOD)
    place(b, 7.0, 12.3, 0, F.table, 2.4, 1.2, 0.95, LAMINATE, TRIM, False)                    # the tailor's corner
    place(b, 3.0, 13.2, 90, F.desk, 1.4, 0.7, 0.76, WOOD, True)
    place(b, 3.0, 12.2, 90, F.chair, FABRIC_GREY)
    place(b, 1.4, 11.0, 0, F.potted_plant, 1.2, 6)
    for k in range(2):
        place(b, 2.0 + 4.5 * k, yf - 0.2, -90, F.shelf, 2.4, 0.4, 2.1, 5, WOOD, False, 8 + k, True)
    for k in range(5):                                                                     # rolls of cloth on the shelves
        b.soft.cyl((1.0 + k * 0.4, yf - 0.4, 1.28), (1.0 + k * 0.4 + 0.3, yf - 0.4, 1.28), 0.07, (FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, FABRIC_GREY, BEDDING)[k], seg=10)
    b.body.cyl((10.0, 12.6, 0.0), (10.0, 12.6, 1.0), 0.04, TRIM, seg=8)                    # the dress form
    b.soft.cyl((10.0, 12.6, 1.0), (10.0, 12.6, 1.5), 0.17, FABRIC_SAND, seg=14, r2=0.13)
    b.soft.sphere((10.0, 12.6, 1.58), 0.09, FABRIC_SAND, seg=10, rings=6)
    b.body.box((xr - 0.05, 12.0, 0.5), (xr, 14.6, 2.1), TRIM)                              # the fitting mirror
    b.fine.box((xr - 0.065, 12.1, 0.55), (xr - 0.05, 14.5, 2.05), DGLASS)
    wall_label(b, 6.0, WF + 0.12, 2.75, (0, 1, 0), "eq_clippers", 0.6)
    ceiling_panels(b, L, D, H, 2, 3, "white_warm", 1.6, 1.0, 0.6, LAMP)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- the bar
def bar(name: str = "SM_SHIP_Bar"):
    """24 x 16 x 3.6: the crew's bar — a long counter across the right half with stools, the back bar and its bottles on the far wall, pendant lamps over the counter, tables and chairs on the
    left half, a billiard table and two arcade cabinets by the right wall, a wall screen with the news; warm light, dark wood."""
    spec, L, D, H = _dims("bar")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _warm_style(DECK, WOOD, "amber_dim"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 18.4, 12.9, -90, G.bar_counter, 7.0, 0.7, 1.08)
    place(b, 18.4, yf - 0.25, -90, G.back_bar, 6.4, 2.1, 0.34, 5)
    for k in range(5):
        place(b, 15.9 + k * 1.3, 11.9, 0, G.bar_stool, 0.72, FABRIC_RUST)
    for (x, y) in ((3.4, 4.2), (3.4, 8.6), (8.2, 4.2), (8.2, 8.6), (8.2, 12.6)):            # four-seat tables
        place(b, x, y, 0, F.table, 1.2, 0.9, 0.74, WOOD, TRIM, True)
        for (dx, dy, yaw) in ((-0.9, 0.0, 0), (0.9, 0.0, 180), (0.0, -0.75, 90), (0.0, 0.75, -90)):
            place(b, x + dx, y + dy, yaw, F.chair, FABRIC_RUST)
    place(b, 13.0, 4.8, 0, G.billiard_table, 2.7, 1.5, 0.84)
    for k in range(2):
        place(b, xr - 0.4, 3.0 + k * 1.0, 180, G.arcade_cabinet, "scr_map", "violet")
    place(b, xl + 0.02, 10.0, 0, F.wall_screen, 2.4, 1.3, "scr_news", z=1.7)
    place(b, xl + 0.3, 14.4, 0, F.sofa, 2.4, FABRIC_RUST)
    wall_label(b, 18.4, yf - 0.002, 3.1, (0, -1, 0), "eq_bar", 0.7)
    ceiling_panels(b, L, D, H, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_DIM)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------- the chapel
def chapel(name: str = "SM_SHIP_Chapel"):
    """16 x 16 x 3.7: a nave with five rows of pews either side of a central aisle with a runner on it, an altar of pale stone with two candlesticks and a lectern at the far end under a
    stained-glass window of the ship's colours between two narrow ones, candelabras at the front, banners, plants; soft warm light from the cove; for all faiths."""
    spec, L, D, H = _dims("chapel")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.4, ceil=COMPOSITE, accent="warm_dim", cove="white_warm", ribs=True, skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    b.soft.swatch_box((7.1, 1.2, 0.0), (8.9, yf - 2.6, 0.012), "oxblood")                                       # the runner down the aisle
    b.soft.swatch_box((7.1, 1.2, 0.0), (7.16, yf - 2.6, 0.014), "mustard")
    b.soft.swatch_box((8.84, 1.2, 0.0), (8.9, yf - 2.6, 0.014), "mustard")
    for k in range(5):
        for xc in (4.8, 11.2):
            place(b, xc, 4.2 + k * 1.5, 90, N3.pew, 2.6)
    b.soft.swatch_box((5.0, yf - 2.6, 0.0), (11.0, yf - 0.1, 0.12), "w_walnut")                                    # the chancel: a low platform, the altar and its lectern on it
    place(b, 8.0, yf - 1.6, -90, N3.altar)
    place(b, 10.2, yf - 1.2, -110, N3.lectern, z=0.12)
    for x in (5.6, 10.4):
        place(b, x, yf - 0.9, 0, N3.candle_stand, 1, z=0.12)
    place(b, 8.0, yf, -90, N3.mosaic_window, 2.4, 3.0, 3, z=1.75)                                                  # the window and its two companions
    for x in (5.6, 10.4):
        place(b, x, yf, -90, N3.mosaic_window, 0.8, 2.4, int(x), z=1.65)
    b.body.box((5.3, yf - 0.1, 0.0), (5.45, yf, 3.6), TRIM)
    b.body.box((10.55, yf - 0.1, 0.0), (10.7, yf, 3.6), TRIM)
    for x in (2.0, 14.0):
        place(b, x, yf, -90, MS.banner, 0.7, 2.1, z=3.0)
    for (x, y) in ((1.0, 14.6), (15.0, 14.6), (1.0, 1.2)):
        place(b, x, y, 0, F.potted_plant, 1.5, int(x + y))
    wall_label(b, 8.0, WF + 0.02, 2.6, (0, 1, 0), "eq_silence", 0.7)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- the store
def shop(name: str = "SM_SHIP_Shop"):
    """16 x 16: the ship's store — shelving on three walls with the stock, a gondola down the middle, a clothing rail, a chilled cabinet, a counter with a till and a screen at the right
    by the door, baskets by the entrance."""
    spec, L, D, H = _dims("shop")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="warm_dim", cove="white_warm", rib_mat=TRIM, skirt=STRUCT))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(3):
        place(b, xl + 0.28, 4.0 + k * 3.6, 0, N.cell_wall_rack, 3.2, 0.5, 2.1, 30 + k)
        place(b, 3.0 + k * 3.6, yf - 0.28, -90, N.cell_wall_rack, 3.2, 0.5, 2.1, 40 + k)
    place(b, xr - 0.28, 9.6, 180, N.cell_wall_rack, 3.0, 0.5, 2.1, 50)
    place(b, 7.0, 8.0, 90, N.cell_wall_rack, 4.0, 0.5, 1.5, 60)
    place(b, 7.0, 8.0, -90, N.cell_wall_rack, 4.0, 0.5, 1.5, 61)
    b.body.cyl((10.0, 11.0, 1.7), (10.0, 14.0, 1.7), 0.02, STEEL, seg=8)                      # a clothing rail
    for k in range(7):
        b.soft.box((10.0 - 0.02, 11.2 + k * 0.4, 0.8), (10.0 + 0.02, 11.4 + k * 0.4, 1.7), (FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, FABRIC_GREY)[k % 4])
    for y in (11.0, 14.0):
        b.body.cyl((10.0, y, 0.0), (10.0, y, 1.7), 0.02, TRIM, seg=6)
    place(b, 11.4, 3.6, 180, F.counter, 3.0, 0.7, 1.05, LAMINATE, COMPOSITE, True, False)
    place(b, 11.4, 3.6, 180, F.monitor, 0.4, 0.25, "scr_menu", False, z=1.05)
    place(b, 13.0, 3.6, 180, F.chair, FABRIC_GREY)
    place(b, 2.0, 2.0, 0, F.crate, 0.5, 0.4, 0.25, CRATE_BLUE, None, True)
    wall_label(b, 8.0, WF + 0.02, 2.5, (0, 1, 0), "eq_till", 0.8)
    ceiling_panels(b, L, D, H, 3, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------- simulators
def sim_bay(name: str = "SM_SHIP_SimBay"):
    """24 x 16 x 3.7: four cockpit simulators on motion bases in a row, facing a wall of projection screens, the instructor's console and a debrief table at the right, the pilots' kit
    lockers on the left; dim blue light so the screens read."""
    spec, L, D, H = _dims("sim_bay")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="cyan_dim", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (4.0, 8.2, 12.4, 16.6):
        place(b, x, 8.6, 90, N.sim_pod)
    b.body.box((1.0, yf - 0.1, 0.4), (19.5, yf, 3.2), STRUCT)                                  # the projection wall: four screens in a frame
    for k in range(4):
        xa = 1.4 + k * 4.4
        b.fine.box((xa, yf - 0.12, 0.7), (xa + 4.0, yf - 0.1, 3.0), DGLASS)
        b.emit.label((xa + 2.0, yf - 0.125, 1.85), 3.9, 2.2, (0, -1, 0), ("scr_star", "scr_tac", "scr_map", "scr_star")[k])
    place(b, 23.2, 4.0, 180, H3.work_console, 3.0, "flight", 3, None, True, True)
    place(b, 22.35, 4.0, 0, H3.chair_op, FABRIC_NAVY)
    place(b, xl + 0.3, 3.2, 0, F.locker_row, 6, 0.5, 1.95, 0.5, COMPOSITE)
    place(b, 20.0, 10.0, 0, F.table, 2.0, 1.0, 0.74, LAMINATE, TRIM, False)
    for (dx, dy, yaw) in ((-1.1, 0.0, 0), (1.1, 0.0, 180), (0.0, -0.7, 90)):
        place(b, 20.0 + dx, 10.0 + dy, yaw, F.chair, FABRIC_NAVY)
    wall_label(b, 6.0, WF + 0.02, 2.6, (0, 1, 0), "eq_sim", 0.8)
    ceiling_panels(b, L, D, H, 4, 3, "cyan", 1.6, 1.2, 0.6, LAMP_DIM)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- quarters
def berthing(name: str = "SM_SHIP_BerthingBay"):
    """24 x 16 x 3.4: a crew berthing bay — fourteen double bunks in two rows either side of a central aisle (twenty-eight sleepers: the places are at the bunks, the lower ones at the
    mattress and the upper ones 0.96 m higher), each bunk with its curtain, reading lamp and net pocket and a locker at its foot against the far wall; at the aisle's end a table with
    benches and a rug, a notice board and the watch roster on the wall, hooks with jackets by the door, a few plants; the light is low and warm (somebody is always asleep)."""
    spec, L, D, H = _dims("berthing")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = TH.crew(floor=CARPET_SLATE, floor2=CARPET_SAND, wall_lo=PLASTER_SLATE, wall_hi=PLASTER_IVORY, wall_acc=WEAVE_SLATE, wall_pattern=("panel", "cloth", "panel"), ceiling="bands",
                 accent="warm_dim", strip="white_warm", light_cell="white_warm", bands=2, bay=2.0, wain_h=1.0)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    blankets = (FABRIC_NAVY, FABRIC_GREY, FABRIC_RUST, FABRIC_SAND)
    for i, x in enumerate(SPEC3.BERTH_X):
        for j, y in enumerate(SPEC3.BERTH_Y):
            place(b, x, y, 90, G.bunk_bed, 2.05, 0.95, 2, blankets[(i + j) % 4], 3 * i + j)
        place(b, x, yf - 0.3, -90, G.wardrobe, 0.9, 0.55, 2.0)
    place(b, 9.9, 7.0, 0, DC.rug, 3.0, 5.0, CARPET_SLATE, CARPET_SAND)
    place(b, 10.0, 12.6, 0, F.table, 2.6, 1.0, 0.74, OAK, TRIM, False)
    for dy in (-0.75, 0.75):
        place(b, 10.0, 12.6 + dy, 90 if dy < 0 else -90, F.bench, 2.4, 0.4, 0.46, LEATHER_NAVY)
    for k, (dx, dy) in enumerate(((-0.9, -0.2), (-0.2, 0.25), (0.7, -0.3), (1.1, 0.2))):
        place(b, 10.0 + dx, 12.6 + dy, 0, DC.mug, (CERAMIC, LAMINATE, LEATHER_NAVY, CERAMIC)[k], z=0.74)
    place(b, 9.4, 12.5, 12, DC.book_stack, 2, 5, z=0.74)
    place(b, xr - 0.04, 7.5, 180, DC.notice_board, 2.4, 1.0, 2, z=1.45)
    place(b, xr - 0.04, 12.0, 180, F.wall_screen, 1.6, 0.9, "scr_sched", z=1.7)
    place(b, 4.6, WF + 0.05, 90, DC.coat_hooks, 5, 0.2, z=1.7)
    place(b, 15.4, WF + 0.05, 90, DC.coat_hooks, 5, 0.2, z=1.7)
    for x in (8.6, 11.4):
        place(b, x, 1.2, 0, F.potted_plant, 1.2, int(x))
    wall_label(b, 2.0, WF + 0.02, 2.2, (0, 1, 0), "eq_bunk", 0.7)
    for x in (7.0, 13.0):                                                                          # picture rail: the squadron prints
        place(b, x, yf - 0.02, -90, DC.picture, 1.2, 0.8, int(x), WALNUT, ("squares", "bands")[int(x) % 2], z=1.9)
    return b.build(name)


def suites(name: str = "SM_SHIP_Suites"):
    """24 x 12 x 3.2: four senior officers' suites off a hall that runs the length of the block (the door from the passage is at x 10): each a bedroom and a sitting room of 6 x 9 m — a
    coat cupboard, a sofa, a coffee table and an armchair on a rug, a desk with its screen, a shelf; a double bed under a wide window with its nightstands, a bench, a wardrobe, a basin
    with its mirror; two lights (ship_cabin.py)."""
    spec, L, D, H = _dims("suites")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _warm_style(FABRIC_GREY, WOOD, "warm_dim"))
    SC.suites_block(b, spec)
    for x in (4.0, 14.0, 20.0):
        place(b, x, 1.0, 0, F.potted_plant, 1.0, int(x))
    place(b, 12.0, WF + 0.02, 90, F.wall_screen, 1.6, 0.9, "scr_news", z=1.8)
    return b.build(name)


def single_cabins(name: str = "SM_SHIP_SingleCabins"):
    """24 x 4 x 3.2: a row of six officers' cabins, each 4 x 2.8 m, behind a gallery along the passage's wall with a hatch apiece (ship_cabin.py): a bed along the far wall under a window,
    a nightstand, a desk with its screen and its lamp, a wardrobe and a basin, a rug and a light of its own; the partitions are plaster and oak and the rugs and blankets differ."""
    spec, L, D, H = _dims("single_cabins")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _warm_style(FABRIC_GREY, WOOD, "warm_dim"))
    SC.single_row(b, spec)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------------------------------------------------------- drone bay
def drone_bay(name: str = "SM_SHIP_DroneBay"):
    """32 x 16 x 3.7: the drone bay — two long benches of charging cradles with drones on them, a launch tube's door in the far wall, shelves of spare rotors and sensor pods, a tool wall
    and a workbench, the controllers' console by the door; bright white light."""
    spec, L, D, H = _dims("drone_bay")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="amber_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 8.0, 9.0, 0, N.charging_bench, 6.0)
    place(b, 24.0, 9.0, 180, N.charging_bench, 6.0)
    place(b, 16.0, yf - 0.02, -90, F4.launch_portal, 5.0, 3.2, "eq_launch")
    for k in range(2):
        place(b, 3.0 + 4.0 * k, yf - 0.35, -90, F.shelf, 3.0, 0.5, 2.1, 5, STEEL, True, 15 + k, True)
    place(b, 28.5, yf - 0.4, -90, G.tool_wall, 3.0, 1.4, 4)
    place(b, 27.0, 11.6, 0, G.workbench, 2.4, 0.8, 0.95, True)
    place(b, 31.2, 2.4, 180, H3.work_console, 3.0, "flight", 2, None, False, True)
    place(b, 30.25, 2.4, 0, H3.chair_op, FABRIC_NAVY)
    dress_wall(b, "near", L, D, H, 14.0, 31.5, 4, accent="amber", accent_dim="amber_dim", kinds=("plain", "vent", "panelboard", "safety"))
    ceiling_panels(b, L, D, H, 5, 3, "white_cool", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
