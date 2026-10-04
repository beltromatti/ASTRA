"""ASN Aquila interior kit: the social rooms of Deck 4 — the crew lounge, the games room, the library, the quiet room, the observation
deck (a flank window wall) and the bow observation deck (a special: its own frame, a panoramic window on the forward wall).
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_cabin as SC
import ship_furn3 as N3
import ship_furniture as F
import ship_decor as DC
import ship_plants as PL
import ship_decor2 as D2
import ship_surfaces as SU
import ship_themes as TH
import ship_furniture2 as G
import ship_spec as SPEC
from bridge3_lib import T, frame
from ship_lib import (BRASS, PLASTER_IVORY, CARPET_RUST, CARPET_SAND, CARPET_SLATE, CERAMIC, LEATHER_NAVY, LEATHER_OX, LEATHER_TAN, OAK, TUFT_SAND, WALNUT, WEAVE_RUST, WEAVE_SAND, WEAVE_TEAL, BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, luminaire_strips, place, wall_label, window_wall)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _card(b: SParts) -> None:
    b.fine.box((-0.045, -0.03, 0.0), (0.045, 0.03, 0.004), BEDDING)


def _book(b: SParts) -> None:
    b.fine.box((-0.15, -0.11, 0.0), (0.15, 0.11, 0.025), FABRIC_RUST)
    b.fine.box((-0.14, -0.10, 0.025), (0.14, 0.10, 0.04), BEDDING)


def _ring(fb, cx: float, cy: float, z: float, r: float, cell: str, seg: int = 48, w: float = 0.05, mat: str = LAMP_DIM) -> None:
    """A ring of lamp segments lying flat at height z (a floor inlay or a ceiling ring)."""
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        lamp_strip(fb, (cx + r * math.cos(a0), cy + r * math.sin(a0), z), (cx + r * math.cos(a1), cy + r * math.sin(a1), z), w, 0.006, cell, mat)


# ------------------------------------------------------------------------------------------------------------------- lounge
def lounge(name: str = "SM_SHIP_Lounge"):
    """24 x 16 x 3.6: the crew lounge — two conversation groups on rugs (a sofa, two armchairs, a low table with what people leave on it, side tables with lamps, a floor lamp,
    a plant), a library wall of open shelving on the far wall, the café corner (tables, chairs, the bar with its stools and the back bar), a news screen and a bench on the left wall,
    pictures between the pillars, planters and a floor tree; a cove-lit ceiling, warm 3300 K. The places are those of ship_spec: the sofas' seats, the armchairs, the cafe's chairs and
    the bar's stools stand where the crew sits."""
    spec, L, D, H = _dims("lounge")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = TH.living(wall_pattern=("panel", "cloth", "slats", "panel"), wall_acc=WEAVE_SAND)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # two conversation groups on rugs: armchairs turned in, a low table, a sofa, side tables with lamps, a floor lamp, a plant
    for k, yc in enumerate((5.3, 12.7)):
        place(b, 5.9, yc, 0, DC.rug, 6.6, 4.6, CARPET_RUST if k == 0 else CARPET_SLATE, CARPET_SAND)
        place(b, 5.9, yc, 0, DC.coffee_table_set, 1.3, 0.7, 0.4, OAK, 3 + k)
        place(b, 4.0, yc - 1.3, 45, F.armchair, LEATHER_TAN if k == 0 else WEAVE_TEAL)
        place(b, 4.0, yc + 1.3, -45, F.armchair, LEATHER_TAN if k == 0 else WEAVE_TEAL)
        place(b, 7.9, yc, 180, F.sofa, 2.6, LEATHER_NAVY if k == 0 else TUFT_SAND)
        place(b, 8.3, yc + (2.0 if k == 0 else -2.0), 0, DC.side_table, 0.24, 0.52, OAK, True, k)
        place(b, 2.7, yc + (2.1 if k == 0 else -2.1), 0, F.lamp_standard, 1.55)
        place(b, 9.5, yc + (2.1 if k == 0 else -2.1) * -1.0, 0, F.potted_plant, 1.2, k + 1)
    place(b, 0.32, 9.0, 0, F.wall_screen, 2.0, 1.1, "scr_news", z=1.9)
    place(b, 0.30, 9.0, 0, F.bench, 1.4, 0.36, 0.44, LEATHER_NAVY)
    # the library wall: open shelving along the far wall, left half, with books and the odd object
    for k in range(4):
        place(b, 2.1 + 2.5 * k, yf - 0.17, -90, F.shelf, 2.4, 0.34, 2.45, 6, WALNUT, True, 11 + k, True)
    place(b, 10.8, yf - 0.3, -90, F.planter, 1.4, 0.5, 0.5, 4, 2, True)
    # the café corner: two tables with chairs, a snack bar with stools, a back bar with mugs and bottles, a coffee machine
    for xt in (15.4, 19.6):
        place(b, xt, 5.4, 0, F.table, 1.2, 0.8, 0.74, OAK, TRIM, False)
        place(b, xt, 4.3, 90, F.chair, WEAVE_RUST)
        place(b, xt, 6.5, -90, F.chair, WEAVE_RUST)
        place(b, xt + 0.2, 5.5, 0, DC.mug, CERAMIC, z=0.74)
        place(b, xt - 0.2, 5.3, 0, DC.fruit_bowl, int(xt), 0.1, z=0.74) if xt > 18 else place(b, xt - 0.2, 5.3, 0, F.potted_plant, 0.5, 7, z=0.74)
    place(b, 20.7, 5.4, 180, F.chair, WEAVE_RUST)
    place(b, 14.3, 5.4, 0, F.chair, WEAVE_RUST)
    place(b, xr - 0.4, 2.2, 0, F.potted_plant, 1.4, 5)
    place(b, 23.73, 5.4, 180, F.wall_screen, 2.2, 1.2, "scr_menu", z=1.9)
    place(b, 19.0, 12.6, -90, G.bar_counter, 6.8, 0.7, 1.08)
    for i in range(5):
        place(b, 16.4 + 1.3 * i, 11.5, 0, G.bar_stool, 0.72, LEATHER_OX)
    place(b, 19.0, yf - 0.17, -90, G.back_bar, 6.4, 2.1, 0.34, 4)
    for x in (17.2, 20.8):
        place(b, x, 12.7, -90, G.coffee_machine, z=1.08)
    for x in (16.9, 19.0, 21.1):
        place(b, x, 12.6, 0, DC.pendant, H - 0.05, 0.95, 0.2)
    place(b, 22.6, 14.7, 0, F.locker_row, 2, 0.5, 1.2, 0.5, COMPOSITE)
    place(b, 12.2, yf - 0.02, -90, F.wall_screen, 1.1, 0.8, "scr_sched", z=1.7)
    # pictures between the pillars on the near wall and the right wall; a notice board by the door
    for k, x in enumerate((2.0, 4.4, 6.8)):
        place(b, x, WF + 0.065, 90, DC.picture, 1.0 if k != 1 else 1.4, 0.7, 5 + k, WALNUT, ("bands", "sun", "squares")[k], z=1.75)
    place(b, 12.6, WF + 0.065, 90, DC.notice_board, 1.1, 0.75, 4, z=1.6)
    place(b, xr - 0.04, 9.0, 180, DC.picture, 1.6, 0.9, 11, WALNUT, "sun", z=1.8)
    # a floor tree by the café, planters under the bar's screen
    place(b, xr - 1.0, 9.0, 0, PL.floor_tree, "pachira_c", 0.3, CERAMIC, 1.1, 20.0)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------- games
def games(name: str = "SM_SHIP_Games"):
    """24 x 16 x 3.6: the games room. Three card tables under their lamps (chips, cards, mugs), a billiard table with its long lamp, six arcade cabinets along the far wall, three pinball
    machines down the left wall, a table-football table, a jukebox, a dartboard with its throwing line on the right wall, a corner of bean bags and a sofa on a rug, a shelf of board games,
    pictures, plants; the crew's places (cards, pool, the arcade) where they were."""
    spec, L, D, H = _dims("games")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    st = Style(floor=FABRIC_NAVY, floor_mode="covering", seams=False, wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="violet",
               cove="violet", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # card tables (felt tops, four chairs, a pendant lamp, cards, chips and mugs)
    for k, (xt, yt) in enumerate(((6.0, 5.0), (6.0, 11.0), (13.0, 4.0))):
        place(b, xt, yt, 0, F.table, 1.3, 1.3, 0.74, LEAF, TRIM, True)
        for dx, dy, yaw in ((-1.0, 0, 0), (1.0, 0, 180), (0, -1.0, 90), (0, 1.0, -90)):
            place(b, xt + dx, yt + dy, yaw, F.chair, FABRIC_RUST if (k + int(dx + dy)) % 2 else FABRIC_GREY)
        place(b, xt, yt, 0, G.pendant_bar, 1.4, 0.3, 2.3, H - 0.05, "white_warm", LAMP)
        rng = random.Random(k)
        for j in range(5):
            place(b, xt + rng.uniform(-0.4, 0.4), yt + rng.uniform(-0.4, 0.4), rng.uniform(0, 360), _card, z=0.74)
        for j in range(4):                                                                                       # a stack of chips and a mug at every seat
            ang = j * 90.0
            cx, cy = xt + 0.5 * math.cos(math.radians(ang)), yt + 0.5 * math.sin(math.radians(ang))
            b.soft.swatch_cyl((cx, cy, 0.74), (cx, cy, 0.74 + 0.012 * (2 + (j + k) % 4)), 0.025, ("red", "navy", "white", "mustard")[j], seg=8)
            place(b, xt + 0.3 * math.cos(math.radians(ang + 40)), yt + 0.3 * math.sin(math.radians(ang + 40)), 0, DC.mug, z=0.74)
    # the billiard table with its long lamp and a rack of cues
    place(b, 17.0, 8.0, 0, G.billiard_table, 2.7, 1.5, 0.84)
    place(b, 17.0, 8.0, 0, G.pendant_bar, 2.4, 0.3, 2.3, H - 0.05, "white_warm", LAMP)
    for y in (5.2, 10.8):
        place(b, 17.0, y, 0, F.chair, FABRIC_GREY)
    for k in range(4):
        b.soft.cyl((xr - 0.12, 6.0 + k * 0.12, 0.2), (xr - 0.12, 6.0 + k * 0.12, 1.7), 0.011, WALNUT, seg=6)
    b.fine.box((xr - 0.16, 5.9, 0.0), (xr - 0.04, 6.6, 0.2), WALNUT)
    # a row of arcade cabinets along the far wall
    screens = ["scr_map", "scr_lab", "scr_news", "scr_dir", "scr_sched", "scr_menu"]
    accents = ["violet", "cyan", "amber", "green", "red", "ice"]
    for i in range(6):
        place(b, 16.5 + 1.0 * i, yf - 0.36, -90, G.arcade_cabinet, screens[i], accents[i])
    # pinball down the left wall, table football and the jukebox
    for k, y in enumerate((3.2, 4.6, 6.0)):
        place(b, xl + 0.78, y, 0, N3.pinball, k, ("scr_wave", "scr_map", "scr_lab")[k])
    place(b, 12.0, 10.6, 0, N3.foosball_table, 1)
    place(b, 3.0, yf - 0.5, -90, N3.jukebox)
    # the dartboard on the right wall with its throwing line, and the shelf of board games by the door
    place(b, xr, 12.0, 180, N3.dart_board, z=1.7)
    b.soft.swatch_box((xr - 2.75, 11.4, 0.0), (xr - 2.7, 12.6, 0.012), "yellow")
    place(b, 3.5, WF + 0.19, 90, F.shelf, 2.4, 0.34, 2.0, 5, WOOD, True, 6, True)
    # the corner of bean bags, a sofa on a rug and plants
    place(b, 22.0, 4.0, 0, DC.rug, 3.6, 3.6, CARPET_RUST, FABRIC_SAND)
    place(b, 23.2, 5.6, 180, F.sofa, 2.4, FABRIC_RUST)
    place(b, 21.9, 5.6, 0, DC.coffee_table_set, 0.9, 0.6, 0.4, WOOD, 12)
    for k, (x, y, c) in enumerate(((21.2, 2.6, FABRIC_NAVY), (22.4, 2.2, FABRIC_RUST), (21.6, 3.8, FABRIC_SAND))):
        place(b, x, y, 40.0 * k, N3.bean_bag, c, k)
    place(b, 0.32, 8.0, 0, F.wall_screen, 3.0, 1.2, "scr_sched", z=2.0)
    place(b, 0.9, 13.6, 0, F.potted_plant, 1.5, 3)
    place(b, 22.9, 2.4, 0, F.potted_plant, 1.5, 4)
    for k, x in enumerate((8.0, 13.0, 18.0)):
        place(b, x, WF + 0.02, 90, DC.picture, 1.0, 0.7, 20 + k, WALNUT, ("bands", "sun", "squares")[k], z=1.9)
    for y in (3.0, 13.0):
        lamp_strip(b.emit, (2.0, y, H - 0.06), (L - 2.0, y, H - 0.06), 0.06, 0.006, "violet", LAMP_DIM)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------ library
def _library_floor(b: SParts, spec: dict, st, rng) -> None:
    """The library's floor: oak planks the long way down the room, a brass line round the central hall (the shelves stand outside it)."""
    L, D = spec["L"], spec["D"]
    SU.planks(b, 0.0, L, 0.0, D, OAK, 0.17, 2.0, "x", seed=5)
    SU.border_line(b, 0.95, L - 0.95, 0.95, D - 0.95, 0.02, BRASS)
    SU.border_line(b, 1.1, L - 1.1, 1.1, D - 1.1, 0.008, BRASS)


def _library_ceiling(b: SParts, spec: dict, st, rng) -> None:
    """The library's ceiling: a plaster soffit with oak beams every 4 m both ways (sixteen coffers, each with its lit panel in a brushed rim), a lit line round the foot of the walls."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    zc = H - 0.05
    b.body.box((WS + WF, WF, zc), (L - WS - WF, D - WS - WF, H), PLASTER_IVORY)
    SU.coffers(b, spec, (4.0, 8.0, 12.0), (4.0, 8.0, 12.0), zc, OAK, 0.22, 0.24, "white_warm", 0.95)
    b.emit.lamp_box((WS + WF + 0.02, WF + 0.02, zc - 0.012), (L - WS - WF - 0.02, WF + 0.05, zc - 0.006), "warm_dim", LAMP_DIM)


def library(name: str = "SM_SHIP_Library"):
    """16 x 16 x 3.6: the library — shelves of books on three walls, an oak plank floor with a brass line round the central hall and three rugs (a big one under the reading table, a small
    one in the armchair nook, a runner from the door), a coffered ceiling, the reading table with its four chairs, its lamps and an open book, the nook with its armchair, a side table and a
    floor lamp, a second armchair by the door side, the librarian's desk by the door with a terminal. The places are those of ship_spec (the table's chairs, the nook, the desk)."""
    spec, L, D, H = _dims("library")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = TH.living(wall_pattern=("slats", "panel", "cloth", "slats"), floor_fn=_library_floor, ceiling_fn=_library_ceiling)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF + 0.17, L - WS - WF - 0.17
    for k in range(5):
        place(b, xl, 1.95 + 2.9 * k, 0, F.shelf, 2.9, 0.34, 2.6, 7, WOOD, True, 11 + k, True)
    for k in range(1, 5):
        place(b, xr, 1.95 + 2.9 * k, 180, F.shelf, 2.9, 0.34, 2.6, 7, WOOD, True, 21 + k, True)
    for k in range(5):
        place(b, 1.9 + 2.85 * k, yf - 0.17, -90, F.shelf, 2.8, 0.34, 2.6, 7, WOOD, True, 31 + k, True)
    # the rugs: a big one under the reading table, a small one in the nook, a runner from the door
    place(b, 6.5, 9.0, 0, SU.rug_ornate, 4.6, 3.1, CARPET_RUST, CARPET_SLATE, ("navy", "cream", "mustard"), 3)
    place(b, 11.0, 5.5, 0, SU.rug_ornate, 2.8, 2.1, CARPET_SLATE, CARPET_SAND, ("oxblood", "cream", "teal"), 5, 0.16)
    place(b, 6.0, 3.95, 90, SU.rug_ornate, 7.1, 1.15, CARPET_SLATE, CARPET_SAND, ("oxblood", "cream", "mustard"), 7, 0.14, 0.014, "chain")
    # the reading table: four chairs, a lamp, an open book; a pendant bar above
    place(b, 6.5, 9.0, 0, F.table, 3.0, 0.9, 0.74, WOOD, TRIM, False)
    for x in (5.0, 8.0):
        place(b, x, 8.0, 90, F.chair, FABRIC_NAVY)
        place(b, x, 10.0, -90, F.chair, FABRIC_NAVY)
    place(b, 6.5, 9.0, 0, F.lamp_standard, 0.4, "white_warm", z=0.74)
    place(b, 6.5, 9.0, 0, G.pendant_bar, 2.6, 0.25, 2.4, H - 0.05, "white_warm", LAMP)
    place(b, 5.2, 9.0, 8, _book, z=0.74)
    # a reading nook with an armchair, a side table and a floor lamp; a second one by the near corner
    place(b, 11.6, 5.4, 180, F.armchair, FABRIC_RUST)
    place(b, 10.4, 5.4, 0, F.low_table, 0.5, 0.5, 0.5, WOOD)
    place(b, 12.9, 6.6, 0, F.lamp_standard, 1.5)
    place(b, 2.6, 4.6, 0, F.armchair, FABRIC_SAND)
    place(b, 1.5, 6.4, 0, F.potted_plant, 1.5, 2)
    # the librarian's desk by the door with a terminal
    place(b, 14.4, 3.0, 0, F.desk, 1.6, 0.7, 0.75, WOOD, True)
    place(b, 14.4, 3.0, 0, F.monitor, 0.5, 0.3, "scr_dir", False, z=0.75)
    place(b, 15.4, 4.2, -100, F.chair, FABRIC_GREY)                                                  # the librarian's chair is pushed aside: she stands at the desk (the place at 13.15, 3.0)
    place(b, 10.0, 12.2, 0, F.potted_plant, 1.3, 7)
    # the table's lamps and what is on it, the globe, the card catalogues, the ladder, the ship's model on its plinth, a second corner for reading
    for k, (dx, yaw_) in enumerate(((-1.0, 90.0), (1.0, -90.0))):
        place(b, 6.5 + dx, 9.0, yaw_, D2.banker_lamp, z=0.74)
    place(b, 7.6, 9.2, 15, DC.book_stack, 3, 11, z=0.74)
    place(b, 6.2, 8.75, 0, DC.mug, CERAMIC, z=0.74)
    place(b, 2.6, 9.4, 40, D2.globe, 0.22, 3)
    place(b, xl + 0.52, 12.3, 0, D2.library_ladder, 2.6, 0.32, 0.42)
    for k, x in enumerate((1.6, 3.0)):
        place(b, x, WF + 0.26, 90, D2.card_catalog, 1.2, 0.5, 1.05, 5, 20 + k)
    top = 0.95
    place(b, 9.4, 12.9, 90, D2.plinth, 0.7, 0.5, top)
    place(b, 9.4, 12.9, 90, N3.ship_model, 0.62, z=top)
    place(b, 12.6, 11.6, 0, DC.rug, 3.0, 2.4, CARPET_SLATE, CARPET_SAND)
    place(b, 12.0, 11.0, -45, F.armchair, FABRIC_NAVY)
    place(b, 13.4, 12.4, 135, F.armchair, FABRIC_RUST)
    place(b, 12.7, 11.8, 0, F.low_table, 0.55, 0.55, 0.45, WOOD)
    place(b, 14.1, 10.8, 0, F.lamp_standard, 1.5)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------- quiet
def quiet(name: str = "SM_SHIP_Quiet"):
    spec, L, D, H = _dims("quiet")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_SAND, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=IVORY, wain_h=1.4, ceil=IVORY, accent="warm_dim",
               cove="warm_dim", ribs=False, skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    # rows of low benches facing the far wall
    for y in (7.6, 9.8):
        for x in (3.6, 8.4):
            place(b, x, y, 90, F.bench, 3.0, 0.5, 0.44, FABRIC_SAND)
    # the far wall: a ring of light, a dark disc, a low plinth with candles
    place(b, 6.0, yf - 0.03, -90, G.ring_lamp, 0.9, 32, "amber", 0.05, LAMP, z=2.0)
    b.fine.cyl((6.0, yf - 0.03, 2.0), (6.0, yf - 0.02, 2.0), 0.85, DGLASS, seg=32)
    place(b, 6.0, yf - 0.3, 0, F.crate, 1.6, 0.5, 0.75, COMPOSITE, None)
    for k in range(5):
        place(b, 5.2 + 0.4 * k, yf - 0.3, 0, G.candle, 0.10 + 0.03 * (k % 3), z=0.75)
    b.body.box((5.0, yf - 0.6, 0.0), (7.0, yf - 0.55, 0.06), TRIM)
    for x in (1.0, 11.0):
        place(b, x, 14.6, 0, F.potted_plant, 1.5, int(x))
    for x, y in ((1.2, 3.0), (10.8, 3.0)):
        place(b, x, y, 0, F.lamp_standard, 1.2)
    place(b, 3.0, 5.2, 0, F.stool, 0.22, 0.32, FABRIC_RUST)
    place(b, 9.0, 5.2, 0, F.stool, 0.22, 0.32, FABRIC_RUST)
    ceiling_panels(b, L, D, H, 2, 2, "white_warm", 2.4, 0.4, 0.4, LAMP_DIM)
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------- observation deck
def _star_field(b: SParts, L: float, D: float, H: float, n: int = 140, seed: int = 5) -> None:
    rng = random.Random(seed)
    for k in range(n):
        x, y = rng.uniform(1.0, L - 1.0), rng.uniform(1.0, D - 1.0)
        s = rng.choice([0.03, 0.04, 0.05])
        b.emit.lamp_box((x, y, H - 0.062), (x + s, y + s, H - 0.05), rng.choice(["white_cool", "ice", "cool_dim", "white_dim"]), LAMP_DIM)


def observation(name: str = "SM_SHIP_Observation", key: str = "observation"):
    spec, L, D, H = _dims(key)
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="cool_dim", cove="cool_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st, skip=("far",))
    spans = window_wall(b, "far", L, D, H, st, 5, glass=False)
    yf = D - WS - WF
    for k, (s0, s1) in enumerate(spans):                                   # the windows: the view out, stars and, in the middle bays, the limb of Aurelia
        place(b, (s0 + s1) / 2, D - WS / 2 + 0.03, -90, SC.sky, s1 - s0, 2.55, 5 + k, 0.3 if k in (1, 2, 3) else 0.0, z=1.85)
    # a cushioned bench under the windows in three lengths, two telescopes in the gaps
    for xc, w in ((4.1, 5.8), (12.0, 6.0), (19.9, 5.8)):
        place(b, xc, yf - 0.4, 90, F.bench, w, 0.6, 0.45, FABRIC_NAVY)
    for x in (8.0, 16.0):
        place(b, x, yf - 0.9, 90, G.telescope)
    # the star table at the centre with stools, two conversation nooks
    place(b, 12.0, 7.0, 0, G.holo_table, 0.9, 0.9)
    for a in (45, 135, 225, 315):
        place(b, 12.0 + 1.55 * math.cos(math.radians(a)), 7.0 + 1.55 * math.sin(math.radians(a)), 0, F.stool, 0.19, 0.46, FABRIC_NAVY)
    for (xa, xb, xt) in ((6.0, 9.2, 7.6), (18.0, 14.8, 16.4)):
        place(b, xt, 7.0, 0, DC.rug, 4.6, 3.6, CARPET_SLATE, FABRIC_SAND)
        place(b, xa, 7.0, 0 if xa < xb else 180, F.armchair, FABRIC_GREY)
        place(b, xb, 7.0, 180 if xa < xb else 0, F.armchair, FABRIC_GREY)
        place(b, xt, 7.0, 0, DC.coffee_table_set, 0.9, 0.6, 0.4, WALNUT, int(xt))
        place(b, xt, 8.9, 0, DC.side_table, 0.22, 0.52, WALNUT, True, int(xt))
        place(b, xt, 5.1, 0, DC.side_table, 0.22, 0.52, WALNUT, True, int(xt) + 1)
    place(b, 0.32, 8.0, 0, F.wall_screen, 3.2, 1.8, "scr_map", z=1.9)
    place(b, L - 0.32, 8.0, 180, F.wall_screen, 3.2, 1.8, "scr_lab", z=1.9)
    place(b, 1.2, 14.0, 0, F.potted_plant, 1.4, 9)
    place(b, 22.8, 14.0, 0, F.potted_plant, 1.4, 10)
    _star_field(b, L, D, H)
    lamp_strip(b.emit, (2.0, 3.4, H - 0.06), (L - 2.0, 3.4, H - 0.06), 0.05, 0.006, "cool_dim", LAMP_DIM)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------ bow observation deck
def bow_obs(name: str = "SM_SHIP_BowObs"):
    """20 x 32: x is forward (0 = the aft wall the Spine runs into at y 16, 20 = the panoramic window), y across."""
    spec, L, D, H = _dims("bow_obs")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="cool_dim", cove="cool_dim",
               rib_mat=TRIM, skirt=STRUCT)
    doors = [{"wall": "left", "x": 16.0, "w": 3.2, "h": 3.2}]
    build_shell(b, spec, st, doors=doors, skip=("right",), bare=())
    spans = window_wall(b, "right", L, D, H, st, 5, pier=0.5)
    xw = L - WS - WF
    # a floor inlay: a compass ring around the centre, guide lines to the window
    _ring(b.emit, 9.5, 16.0, 0.004, 4.6, "cool_dim", 64, 0.05)
    _ring(b.emit, 9.5, 16.0, 0.004, 3.4, "guide", 48, 0.03)
    for y in (16.0,):
        lamp_strip(b.emit, (1.2, y, 0.004), (xw - 3.0, y, 0.004), 0.05, 0.006, "guide", LAMP_DIM)
    # a rail along the window (watchers lean on it), four benches in the middle, planters at both ends
    b.fine.cyl((xw - 1.3, 1.0, 1.05), (xw - 1.3, D - 1.0, 1.05), 0.024, TRIM, seg=10)
    for y in [1.0 + k * 2.0 for k in range(int((D - 2.0) / 2.0) + 1)]:
        b.fine.cyl((xw - 1.3, y, 0.0), (xw - 1.3, y, 1.05), 0.015, TRIM, seg=8)
    for y, w in ((6.5, 6.0), (25.5, 6.0)):
        place(b, 11.6, y, 0, F.bench, w, 0.6, 0.46, FABRIC_NAVY)
        place(b, 13.6, y, 0, F.bench, w, 0.6, 0.46, FABRIC_NAVY)
    for y in (2.2, D - 2.2):
        place(b, xw - 2.2, y, 0, F.planter, 2.2, 0.9, 0.5, 4, 7 + int(y), True)
        place(b, 2.4, y, 0, F.planter, 2.2, 0.9, 0.5, 3, 5 + int(y), True)
    place(b, 9.5, 16.0, 0, F.planter, 1.6, 1.6, 0.5, 5, 21, True)
    b.emit.label_fit((0.27, 16.0, 3.05), 3.2, "room_bow_obs", (1, 0, 0))
    place(b, 0.32, 7.0, 0, F.wall_screen, 3.0, 1.3, "scr_map", z=1.8)
    place(b, 0.32, 25.0, 0, F.wall_screen, 3.0, 1.3, "scr_news", z=1.8)
    ceiling_panels(b, L, D, H, 4, 5, "white_cool", 2.0, 0.6, 0.6, LAMP)
    return b.build(name)


