"""ASN Aquila interior kit: the service rooms — the galley, the galley pass, the stores (dry, cold, general), heads, laundry, hydroponics.
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_decor as DC
import ship_mk as MK
import ship_plants as PL
import ship_themes as TH
import ship_spec as SPEC
from bridge3_lib import T, frame
from ship_lib import (BRASS, CARPET_MOSS, CERAMIC, GRASS, LEATHER_TAN, MOSS, OAK, PERF, PLASTER_IVORY, PLASTER_SAGE, TERRAZZO, TILE_FLOOR, TILE_HEX, WEAVE_SAND, WHITE_GLOSS, BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DGLASS, DECK, FABRIC_GREY, FABRIC_NAVY, IVORY, LAMINATE,
                      LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_panels, luminaire_strips, place, wall_label

CRATES = [CRATE_OLIVE, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY]


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ------------------------------------------------------------------------------------------------------------- pieces
def cold_room(b: SParts, w: float, d: float, h: float, door_side: str = "front") -> None:
    """A walk-in cold room: insulated panel box, a heavy door with a handle and a temperature display, frost-blue lamp. Origin at its
    back-left corner on the floor; x = width along the room's x, y = depth; the door is on the +y face."""
    b.body.box((0, 0, 0.0), (w, d, h), IVORY)
    for k in range(1, int(w / 0.6)):
        b.fine.box((k * 0.6 - 0.006, 0, 0.0), (k * 0.6 + 0.006, d, h), STEEL)
    b.body.box((0, 0, 0.0), (w, d, 0.12), STEEL)
    b.body.box((0, 0, h - 0.10), (w, d, h), STEEL)
    dx = w / 2
    b.body.box((dx - 0.52, d, 0.0), (dx + 0.52, d + 0.09, 2.1), STEEL)
    b.fine.box((dx - 0.46, d + 0.09, 0.06), (dx + 0.46, d + 0.11, 2.04), STRUCT)
    b.fine.box((dx + 0.30, d + 0.11, 0.9), (dx + 0.36, d + 0.17, 1.3), TRIM)
    b.fine.box((dx + 0.30, d + 0.11, 1.2), (dx + 0.48, d + 0.15, 1.24), TRIM)
    b.emit.label((dx, d + 0.115, 1.75), 0.4, 0.1, (0, 1, 0), "small_15")
    b.emit.lamp_box((dx - 0.44, d + 0.11, 2.14), (dx + 0.44, d + 0.115, 2.19), "ice", LAMP)


def cart(b: SParts, w: float = 0.9, d: float = 0.55, h: float = 1.0, tiers: int = 3) -> None:
    for sx in (-d / 2 + 0.03, d / 2 - 0.03):
        for sy in (-w / 2 + 0.03, w / 2 - 0.03):
            b.fine.cyl((sx, sy, 0.1), (sx, sy, h), 0.014, STEEL, seg=6)
            b.fine.cyl((sx, sy, 0.0), (sx, sy, 0.07), 0.035, RUBBER, seg=8)
    for k in range(tiers):
        z = 0.14 + k * (h - 0.2) / max(1, tiers - 1)
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.02), STEEL)
    b.fine.cyl((-d / 2, -w / 2, h), (-d / 2, w / 2, h), 0.016, STEEL, seg=8)


def prep_island(b: SParts, w: float = 3.0, d: float = 1.0, seed: int = 1) -> None:
    """A stainless prep island: a steel top with a lower shelf of gastronorm trays, a cutting board with chopped vegetables and a knife, a mixing bowl, a stack of plates, a tray of food and a
    pot with its lid; origin at its centre."""
    rng = random.Random(seed)
    h = 0.92
    b.body.box((-d / 2, -w / 2, h - 0.05), (d / 2, w / 2, h), STEEL)
    b.fine.box((-d / 2 + 0.03, -w / 2 + 0.03, h - 0.09), (d / 2 - 0.03, w / 2 - 0.03, h - 0.05), STRUCT)
    for sx in (-d / 2 + 0.06, d / 2 - 0.06):
        for sy in (-w / 2 + 0.07, 0.0, w / 2 - 0.07):
            b.body.box((sx - 0.025, sy - 0.025, 0.0), (sx + 0.025, sy + 0.025, h - 0.05), STEEL)
    b.body.box((-d / 2 + 0.05, -w / 2 + 0.05, 0.20), (d / 2 - 0.05, w / 2 - 0.05, 0.23), STEEL)
    for k in range(3):                                                # trays on the lower shelf
        with b.at(T(0.0, -w / 2 + 0.45 + k * 0.95, 0.23)):
            DC.gastro_tray(b, 0.5, 0.32, 0.1, rng.choice(("f_lettuce", "f_carrot", "f_tomato", "f_cheese", "f_bread")), 0.8)
    for k in range(3):                                                # on the top: a board, a bowl, plates, a tray, a pot
        y = -w / 2 + 0.45 + k * 0.95
        with b.at(T(-0.02, y, h)):
            if k == 0:
                DC.cutting_board(b, 0.42, 0.3, seed)
            elif k == 1:
                DC.stock_pot(b, 0.15, 0.2, True)
                with b.at(T(0.0, 0.34, 0.0)):
                    DC.plate_stack(b, 7)
            else:
                with b.at(T(0.0, -0.1, 0.0)):
                    DC.mixing_bowl(b, 0.17)
                with b.at(T(0.0, 0.28, 0.0)):
                    DC.gastro_tray(b, 0.5, 0.3, 0.06, "f_orange", 0.6)
    b.emit.label((d / 2 - 0.0, 0.0, 0.5), 0.5, 0.125, (1, 0, 0), "eq_food")


def dishwasher(b: SParts, w: float = 1.8, d: float = 0.9, h: float = 1.55) -> None:
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), STEEL)
    b.fine.box((d / 2, -w / 2 + 0.08, 0.5), (d / 2 + 0.05, w / 2 - 0.08, 1.35), STRUCT)
    b.fine.box((d / 2 + 0.05, -w / 2 + 0.14, 0.62), (d / 2 + 0.055, w / 2 - 0.14, 1.23), DGLASS)
    b.emit.lamp_box((d / 2 + 0.056, -w / 2 + 0.16, 1.28), (d / 2 + 0.06, w / 2 - 0.16, 1.31), "green", LAMP)
    for sy in (-w / 2 - 0.6, w / 2 + 0.0):                            # the loading table and rack rail
        b.body.box((-d / 2, sy, 0.86), (d / 2, sy + 0.6, 0.90), STEEL)
        b.fine.box((-d / 2 + 0.03, sy + 0.02, 0.0), (-d / 2 + 0.06, sy + 0.05, 0.86), STEEL)
        b.fine.box((d / 2 - 0.06, sy + 0.55, 0.0), (d / 2 - 0.03, sy + 0.58, 0.86), STEEL)
    for k in range(3):
        b.fine.box((-0.3, -w / 2 - 0.55 + k * 0.18, 0.90), (0.3, -w / 2 - 0.42 + k * 0.18, 0.93), TRIM)


def pot_rack(b: SParts, L: float, seed: int = 4) -> None:
    """Two rails hung from the ceiling over the prep islands with pots, pans and utensils hanging from them."""
    rng = random.Random(seed)
    for y in (-0.5, 0.5):
        b.fine.cyl((0, y, 2.55), (L, y, 2.55), 0.012, STEEL, seg=6)
    for sx in (0.05, L - 0.05):
        b.fine.cyl((sx, -0.5, 2.55), (sx, -0.5, 3.4), 0.01, STEEL, seg=6)
        b.fine.cyl((sx, 0.5, 2.55), (sx, 0.5, 3.4), 0.01, STEEL, seg=6)
    x = 0.3
    while x < L - 0.3:
        y = rng.choice((-0.5, 0.5))
        r = rng.uniform(0.09, 0.15)
        b.fine.cyl((x, y, 2.55), (x, y, 2.42), 0.006, STEEL, seg=6)
        with b.at(T(x, y, 2.2)):
            if rng.random() < 0.5:
                DC.stock_pot(b, r, rng.uniform(0.08, 0.16), False)
            else:
                DC.saucepan(b, r * 0.8, 0.07)
        x += rng.uniform(0.22, 0.42)


# -------------------------------------------------------------------------------------------------------------------- galley
def galley(name: str = "SM_SHIP_Galley"):
    spec, L, D, H = _dims("galley")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=TILE, floor_mode="covering", wall_lo=TILE, wall_hi=COMPOSITE, wain_h=1.9, ceil=IVORY, accent="warm_dim", strip="white_warm",
               rib_mat=TRIM, skirt=STEEL)
    build_shell(b, spec, st)
    yf = D - WS - WF                                                     # the far wall's finished face
    kinds = ["range", "range", "griddle", "range", "fryer", "fryer", "range", "range", "griddle", "range"]
    x0 = 6.6
    for i, k in enumerate(kinds):
        place(b, x0 + 0.92 * i, yf - 0.375, -90, F.range_cooker, 0.9, 0.75, 0.92, k)
    place(b, x0 + 0.92 * 4.5, yf - 0.5, -90, F.hood, 9.6, 1.0, 2.1, H)
    # the extraction duct, a steel back-panel behind the cookers and a gas warning
    b.body.box((x0 - 0.5, yf - 0.02, 0.92), (x0 + 0.92 * 9.5, yf, 2.1), STEEL)
    wall_label(b, x0 + 2.0, yf - 0.03, 1.55, (0, -1, 0), "eq_gas", 0.6)
    wall_label(b, x0 + 6.4, yf - 0.03, 1.55, (0, -1, 0), "tag_02", 0.5)
    # walk-in cold rooms on the left, dumbwaiter hatch in the left wall
    for y0 in (5.6, 9.6):
        place(b, WS + WF, y0 + 3.6, -90, cold_room, 3.6, 3.2, H - 0.25)
    b.body.box((WS + WF, 3.6, 0.95), (WS + WF + 0.12, 4.6, 1.95), STEEL)                          # dumbwaiter
    b.fine.box((WS + WF + 0.12, 3.7, 1.05), (WS + WF + 0.14, 4.5, 1.85), STRUCT)
    b.emit.label((WS + WF + 0.15, 4.1, 2.15), 0.9, 0.28, (1, 0, 0), "room_dumbwaiter")
    b.emit.lamp_box((WS + WF + 0.12, 4.5, 1.0), (WS + WF + 0.125, 4.56, 1.06), "amber", LAMP)
    # dish station at the right end: sinks, the dishwasher, racks
    place(b, L - WS - WF - 0.4, 12.5, 180, F.steel_sink_unit, 1.6, 0.75)
    place(b, L - WS - WF - 0.5, 9.9, 180, dishwasher)
    place(b, L - WS - WF - 0.4, 6.3, 180, F.counter, 1.6, 0.75, 0.92, STEEL, STEEL, True, False)
    # the prep islands with hanging pots above
    place(b, 8.0, 7.0, 90, prep_island, 3.2, 1.0, 1)
    place(b, 13.5, 7.0, 90, prep_island, 3.2, 1.0, 2)
    with b.at(T(5.5, 7.0, 0.0)):
        pot_rack(b, 11.0, 4)
    # along the near wall: steel shelving and carts; a wash sink by the door
    for x in (1.5, 3.4, 5.3):
        place(b, x, WF + 0.4, 90, F.shelf, 1.6, 0.6, 1.9, 4, STEEL, False, 7 + int(x), False)
    place(b, 7.6, WF + 0.4, 90, F.counter, 1.4, 0.7, 0.92, STEEL, STEEL, True, True)
    place(b, 13.0, WF + 0.4, 90, F.steel_sink_unit, 1.8, 0.7)
    for x in (16.0, 17.4):
        place(b, x, 1.4, 90, cart)
    for x in (19.5, 21.0):
        place(b, x, WF + 0.4, 90, F.shelf, 1.3, 0.6, 1.9, 4, STEEL, False, 3 + int(x), False)
    # the chief cook's small desk and screen by the door, waste sorting
    place(b, 12.5, 3.2, 180, F.desk, 1.2, 0.6, 0.85, STEEL, False)
    place(b, 12.6, 3.2, 180, F.monitor, 0.5, 0.3, "scr_menu", False, z=0.85)
    for k, mat in enumerate((CRATE_OLIVE, CRATE_BLUE, CRATE_GREY)):
        place(b, 22.6, 1.4 + k * 0.6, 180, F.barrel, 0.22, 0.6, mat)
    ceiling_panels(b, L, D, H, 6, 3, "white_warm", 2.0)
    luminaire_strips(b, L, D, H, [yf - 1.2], "white_warm", x0 - 0.5, x0 + 0.92 * 9.5, LAMP_HOT)
    return b.build(name, uv_meter=1.0)


def galley_pass(name: str = "SM_SHIP_GalleyPass"):
    spec, L, D, H = _dims("galley_pass")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=TILE, floor_mode="covering", wall_lo=TILE, wall_hi=COMPOSITE, wain_h=1.9, ceil=IVORY, accent="warm_dim", ribs=False, skirt=STEEL)
    build_shell(b, spec, st)
    yf = D - WS - WF
    # a service counter and trolleys along the far wall, the dumbwaiter riser at its middle
    place(b, 6.0, yf - 0.35, -90, F.counter, 6.0, 0.7, 0.92, STEEL, STEEL, True, False)
    place(b, 17.0, yf - 0.35, -90, F.counter, 6.0, 0.7, 0.92, STEEL, STEEL, True, False)
    b.body.box((10.0, yf - 0.9, 0.0), (14.0, yf, 2.5), STEEL)
    b.fine.box((10.3, yf - 0.94, 0.35), (13.7, yf - 0.9, 2.1), STRUCT)
    b.emit.label((12.0, yf - 0.945, 2.3), 1.6, 0.2, (0, -1, 0), "room_dumbwaiter")
    b.emit.lamp_box((10.4, yf - 0.94, 1.0), (10.44, yf - 0.9, 1.06), "green", LAMP)
    for x in (2.2, 21.8):
        place(b, x, 2.0, 0, cart)
    luminaire_strips(b, L, D, H, [2.0], "white_warm", 2.0, L - 2.0, LAMP_HOT, 0.28)
    return b.build(name)


# --------------------------------------------------------------------------------------------------------------------- stores
def _rack_block(b: SParts, xs: list[float], y0: float, y1: float, seed: int = 1, load: float = 0.8, levels: int = 4, mats=None) -> None:
    """Back-to-back racks in aisles: pairs of columns at the x positions `xs` (pair centres), along y from y0 to y1."""
    rng = random.Random(seed)
    for xc in xs:
        y = y0
        while y + 2.4 <= y1 + 0.01:
            place(b, xc - 0.45, y + 1.2, 180, F.rack, 2.4, 0.9, 2.6, levels, rng.randint(0, 999), load, mats)
            place(b, xc + 0.45, y + 1.2, 0, F.rack, 2.4, 0.9, 2.6, levels, rng.randint(0, 999), load, mats)
            y += 2.4


def store_room(key: str, name: str, cold: bool = False):
    spec, L, D, H = _dims(key)
    b = SParts(bevel=0.005, fine_bevel=0.003)
    if cold:
        st = Style(floor=STEEL, floor_mode="covering", wall_lo=IVORY, wall_hi=IVORY, wain_h=1.2, ceil=IVORY, accent="ice_dim", strip="ice", skirt=STEEL,
                   rib_mat=STEEL)
    else:
        st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, accent="amber_dim", strip="white_cool")
    build_shell(b, spec, st)
    dx = spec["doors"][0]["x"]
    lay_x = [2.8, 6.0, 9.2] if dx > 12 else [2.8, 6.0]
    right = [17.2, 20.4] if dx < 16 else [17.4, 20.6]
    lay_x = [x for x in lay_x if abs(x - dx) > 2.4] + [x for x in right if abs(x - dx) > 2.4]
    mats = [CRATE_BLUE, CRATE_GREY, IVORY] if cold else CRATES
    _rack_block(b, lay_x, 3.4 if dx > 12 else 3.4, D - 0.5, seed=sum(map(ord, key)) % 100, load=0.85, mats=mats)
    # by the door: the storekeeper's counter with a terminal, a tally board and a trolley
    place(b, dx + 2.2, 1.6, 90, F.desk, 1.6, 0.7, 0.85, LAMINATE, True)
    place(b, dx + 2.2, 1.6, 90, F.monitor, 0.5, 0.3, "scr_sched", False, z=0.85)
    place(b, dx - 2.2, 1.0, 90, cart)
    wall_label(b, dx + 4.0, WF + 0.02, 2.0, (0, 1, 0), "eq_stores", 0.9)
    wall_label(b, dx - 4.0, WF + 0.02, 2.0, (0, 1, 0), "tag_09", 0.6)
    # the far wall: a cargo hatch (double doors with hazard lines) and stacked pallets
    xh = L - 5.0
    yf = D - WS - WF
    b.body.box((xh - 1.7, yf - 0.1, 0.0), (xh + 1.7, yf, 3.0), STEEL)
    b.fine.box((xh - 1.55, yf - 0.14, 0.05), (xh + 1.55, yf - 0.1, 2.9), STRUCT)
    b.fine.box((xh - 0.03, yf - 0.16, 0.05), (xh + 0.03, yf - 0.14, 2.9), TRIM)
    b.emit.label((xh, yf - 0.165, 3.15), 1.6, 0.16, (0, -1, 0), "hazard")
    b.emit.lamp_box((xh - 1.6, yf - 0.14, 3.02), (xh + 1.6, yf - 0.135, 3.06), "amber", LAMP)
    rng = random.Random(9)
    for k, px in enumerate((xh - 7.5, xh - 4.0, xh + 3.6)):
        place(b, px, yf - 1.6, 90, F.pallet, 1.2, 0.8)
        for j in range(rng.randint(2, 4)):
            place(b, px + rng.uniform(-0.15, 0.15), yf - 1.6 + rng.uniform(-0.2, 0.2), 90 + rng.uniform(-8, 8), F.crate, 0.55, 0.4, 0.4, rng.choice(mats),
                  None, True, z=0.145 + j * 0.4)
    luminaire_strips(b, L, D, H, [5.0, 12.0], "ice" if cold else "white_cool", 2.0, L - 2.0, LAMP_HOT)
    if cold:
        for y in (6.0, 12.0):
            b.emit.lamp_box((2.0, y - 0.02, H - 0.06), (L - 2.0, y + 0.02, H - 0.055), "cyan_dim", LAMP_DIM)
    return b.build(name)


def store_dry(name: str = "SM_SHIP_StoreDry"):
    return store_room("store_dry", name, False)


def store_cold(name: str = "SM_SHIP_StoreCold"):
    return store_room("store_cold", name, True)


def iso_box(b: SParts, l: float = 3.0, w: float = 2.4, h: float = 2.4, mat: str = CRATE_GREY) -> None:
    b.body.box((-w / 2, -l / 2, 0.0), (w / 2, l / 2, h), mat)
    for k in range(1, 8):
        b.fine.box((-w / 2 - 0.008, -l / 2 + k * l / 8 - 0.02, 0.06), (w / 2 + 0.008, -l / 2 + k * l / 8 + 0.02, h - 0.06), TRIM)
    for sx in (-w / 2, w / 2 - 0.09):
        for sy in (-l / 2, l / 2 - 0.09):
            b.body.box((sx, sy, 0.0), (sx + 0.09, sy + 0.09, h), STEEL)
    b.fine.box((-w / 2 - 0.01, -0.25, 0.9), (-w / 2, 0.25, 1.1), TRIM)


def hold(name: str = "SM_SHIP_Hold"):
    spec, L, D, H = _dims("hold")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, accent="amber_dim", strip="white_cool")
    build_shell(b, spec, st)
    rng = random.Random(21)
    # floor lanes with hazard stripes
    for x in (7.5, 16.5):
        b.emit.label((x, D / 2, 0.006), D - 2.0, 0.22, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    # ISO boxes in two stacks, crates on pallets between, a loader
    for i, x in enumerate((3.4, 6.0)):
        for j in range(2):
            place(b, x, 3.4 + 2.8 + j * 5.8, 0, iso_box, 5.6, 2.4, 2.4, rng.choice(CRATES))
        if i == 0:
            place(b, x, 3.4 + 2.8, 0, iso_box, 5.6, 2.4, 0.9, CRATE_OLIVE, z=2.4)
    for j in range(3):
        for i in range(3):
            px, py = 11.0 + i * 1.4, 4.0 + j * 3.5
            place(b, px, py, 0, F.pallet, 1.2, 0.8)
            for k in range(rng.randint(2, 4)):
                place(b, px, py, rng.uniform(-6, 6), F.crate, 0.6, 0.45, 0.4, rng.choice(CRATES), None, True, z=0.145 + k * 0.4)
    for j in range(3):
        place(b, 20.5, 3.0 + j * 2.6, 0, F.barrel, 0.28, 0.85, rng.choice([CRATE_BLUE, CRATE_ORANGE, CRATE_OLIVE]))
        place(b, 21.3, 3.0 + j * 2.6, 0, F.barrel, 0.28, 0.85, rng.choice([CRATE_BLUE, CRATE_ORANGE, CRATE_OLIVE]))
    place(b, 16.0, 12.5, 200, _loader)
    place(b, 12.5, 1.6, 90, F.desk, 1.5, 0.7, 0.85, LAMINATE, True)
    place(b, 12.5, 1.6, 90, F.monitor, 0.5, 0.3, "scr_sched", False, z=0.85)
    wall_label(b, 8.0, WF + 0.02, 2.2, (0, 1, 0), "eq_stores", 0.9)
    wall_label(b, 16.0, WF + 0.02, 2.2, (0, 1, 0), "tag_09", 0.6)
    for x in (3.0, 9.0, 15.0, 21.0):
        b.body.box((x - 0.5, D - WS - WF - 0.04, 2.4), (x + 0.5, D - WS - WF, 3.0), COMPOSITE)
        b.emit.label((x, D - WS - WF - 0.045, 2.7), 0.8, 0.2, (0, -1, 0), "hazard")
    luminaire_strips(b, L, D, H, [4.0, 8.0, 12.0], "white_cool", 2.0, L - 2.0, LAMP_HOT)
    return b.build(name)


def _loader(b: SParts) -> None:
    """A small cargo loader: a low chassis with forks, a mast and a cab."""
    b.body.box((-0.7, -0.5, 0.12), (0.7, 0.5, 0.55), CRATE_ORANGE)
    b.body.box((-0.4, -0.4, 0.55), (0.3, 0.4, 1.5), STEEL)
    b.fine.box((-0.4, -0.4, 1.5), (0.3, 0.4, 1.53), TRIM)
    b.body.box((0.7, -0.5, 0.0), (0.78, 0.5, 1.4), STEEL)
    for sy in (-0.3, 0.3):
        b.body.box((0.78, sy - 0.06, 0.03), (1.75, sy + 0.06, 0.09), STEEL)
    for sx in (-0.45, 0.45):
        for sy in (-0.52, 0.52):
            b.fine.cyl((sx, sy, 0.15), (sx, sy + (0.06 if sy > 0 else -0.06), 0.15), 0.15, RUBBER, seg=14)
    b.emit.lamp_box((-0.72, -0.2, 0.3), (-0.70, 0.2, 0.36), "red", LAMP_DIM)
    b.emit.lamp_box((0.6, 0.0, 1.56), (0.66, 0.06, 1.62), "amber", LAMP)


# ------------------------------------------------------------------------------------------------------------ heads, laundry
def heads(name: str = "SM_SHIP_Heads"):
    """12 x 16 x 3.4: the heads and showers (ship_wet.py)."""
    import ship_wet
    return ship_wet.heads(name)


def _toilet(b: SParts) -> None:
    b.body.box((-0.30, -0.19, 0.0), (0.05, 0.19, 0.42), IVORY)
    b.body.box((0.05, -0.15, 0.0), (0.42, 0.15, 0.36), IVORY)
    b.fine.box((-0.32, -0.20, 0.42), (-0.06, 0.20, 0.50), IVORY)
    b.fine.box((-0.30, -0.10, 0.5), (-0.10, 0.10, 0.6), STEEL)


def _basin_island(b: SParts) -> None:
    b.body.box((-0.3, -1.4, 0.0), (0.3, 1.4, 0.86), TILE)
    b.body.box((-0.34, -1.44, 0.86), (0.34, 1.44, 0.9), STEEL)
    for k in range(4):
        y = -1.05 + k * 0.7
        b.fine.box((-0.2, y - 0.2, 0.86), (0.2, y + 0.2, 0.895), DGLASS)
        for sx in (-0.30, 0.30):
            b.fine.cyl((sx * 0.8, y, 0.9), (sx * 0.8, y, 1.1), 0.014, TRIM, seg=8)
            b.body.box((sx * 0.93 - 0.02, y - 0.3, 1.2), (sx * 0.93 + 0.02, y + 0.3, 1.95), DGLASS)
    b.fine.box((-0.04, -1.44, 1.9), (0.04, 1.44, 1.96), STEEL)


def laundry(name: str = "SM_SHIP_Laundry"):
    """12 x 16 x 3.4: the laundry (ship_wet.py)."""
    import ship_wet
    return ship_wet.laundry(name)


def _washer(b: SParts, mat: str = STEEL) -> None:
    b.body.box((-0.3, -0.45, 0.0), (0.3, 0.45, 1.05), mat)
    b.fine.cyl((0.30, 0.0, 0.55), (0.34, 0.0, 0.55), 0.26, STRUCT, seg=20)
    b.fine.cyl((0.335, 0.0, 0.55), (0.345, 0.0, 0.55), 0.2, DGLASS, seg=20)
    b.fine.box((0.30, -0.3, 0.92), (0.33, 0.3, 1.0), STRUCT)
    b.emit.lamp_box((0.331, -0.24, 0.94), (0.335, -0.2, 0.98), "green", LAMP_DIM)


# -------------------------------------------------------------------------------------------------------------- hydroponics
def _nutrient_tank(b: SParts, r: float = 0.55, h: float = 2.1) -> None:
    """A nutrient tank: a white vessel with a domed head, a level gauge (a lit slot), a pump and two feed lines going up into the ceiling (origin on the floor at its centre)."""
    MK.lathe(b.body, [(r * 0.9, 0.0), (r, 0.06), (r, h - 0.2), (r * 0.8, h - 0.06), (r * 0.35, h), (r * 0.3, h), (r * 0.3, h - 0.02), (r * 0.74, h - 0.1), (r * 0.94, h - 0.24), (r * 0.94, 0.1)],
             (0, 0, 0), WHITE_GLOSS, seg=24)
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.1), r * 1.04, STEEL, seg=24)
    b.fine.cyl((0, 0, h * 0.5 - 0.02), (0, 0, h * 0.5 + 0.02), r * 1.012, STEEL, seg=24)
    b.emit.lamp_box((r * 0.96, -0.03, 0.4), (r * 0.99, 0.03, h - 0.5), "green", LAMP_DIM)
    b.body.cyl((0, 0, h), (0, 0, 3.4), 0.035, STEEL, seg=8)
    b.body.cyl((0.2, 0, h - 0.08), (0.2, 0, 3.4), 0.025, BRASS, seg=8)


def hydro(name: str = "SM_SHIP_Hydro"):
    """24 x 16 x 3.4: a hydroponics bay — four rows of vertical-farm racks (two 9 m runs each, three tiers of trays with lettuce, herbs, wheat and seedlings growing under bars of light),
    an aisle between the rows where the botanists work, the nutrient tanks along the left wall, the controller and the seed cabinet by the door; the ceiling is a grid of luminous panels
    and the floor is tile with a drain channel. The racks and aisles are where they were (the botanists' places are in the aisle)."""
    spec, L, D, H = _dims("hydro")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = TH.lab(floor=TILE_FLOOR, floor2=TILE_HEX, wall_lo=PLASTER_SAGE, wall_hi=PLASTER_IVORY, wall_acc=PERF, wain_h=1.2, accent="green_dim", strip="white_cool", light_cell="white_cool",
                wall_pattern=("panel", "perf", "panel"), ceiling="grid", skirt=STEEL)
    build_shell(b, spec, st)
    rng = random.Random(31)
    dx = spec["doors"][0]["x"]
    crops = ("lettuce", "herb", "grain", "mix")
    for r, y in enumerate((5.0, 8.0, 11.0, 14.0)):
        for k, seg_x0 in enumerate((2.0, 13.8)):
            place(b, seg_x0 + 4.5, y, 0, PL.grow_rack, 9.0, 3, 1.1, crops[(r + k) % 4], 3 * r + k, 2.9, "white_cool")
    # a drain channel down the aisle, with a grate
    for y in (6.5, 9.5, 12.5):
        b.fine.box((WS + WF + 1.0, y - 0.07, -0.004), (L - WS - WF - 1.0, y + 0.07, 0.0), STRUCT)
        b.fine.box((WS + WF + 1.0, y - 0.05, 0.0), (L - WS - WF - 1.0, y + 0.05, 0.004), STEEL)
    # the nutrient tanks along the left wall, the controller and the seed cabinet near the door, a botanist's bench
    for k in range(3):
        place(b, WS + WF + 0.7, 3.0 + k * 2.0, 0, _nutrient_tank, 0.62, 2.1)
    b.body.box((L - WS - WF - 1.0, 2.0, 0.0), (L - WS - WF, 3.4, 1.9), COMPOSITE)
    b.emit.label((L - WS - WF - 1.005, 2.7, 1.5), 0.9, 0.5, (-1, 0, 0), "scr_lab")
    place(b, dx, 2.4, 90, F.desk, 1.4, 0.7, 0.8, LAMINATE, True)
    place(b, dx - 0.4, 2.1, 90, DC.mug, CERAMIC, z=0.8)
    place(b, dx + 0.4, 2.0, 90, PL.haworthia, 1.0, 20.0, z=0.8)
    place(b, dx + 3.0, WF + 0.3, 90, F.shelf, 1.8, 0.4, 2.1, 5, STEEL, True, 7, True)
    place(b, dx + 5.0, WF + 0.3, 90, F.shelf, 1.8, 0.4, 2.1, 5, STEEL, True, 8, True)
    F.pipe_run(b, (1.0, 1.0, H - 0.4), (L - 1.0, 1.0, H - 0.4), 0.09)
    F.pipe_run(b, (1.0, 1.4, H - 0.6), (L - 1.0, 1.4, H - 0.6), 0.05, STEEL)
    wall_label(b, 8.0, WF + 0.02, 2.1, (0, 1, 0), "room_hydro", 0.9)
    return b.build(name)


def garden(name: str = "SM_SHIP_Garden"):
    """24 x 16 x 3.4: a garden — the park of the ship: a terrazzo path down the middle with a bench every few metres, long planting beds either side of it with ferns, calatheas,
    anthuriums and money trees, a lantern on a post at the bends, vines hanging from a pergola of oak beams, and a ceiling that is the sky (a wide pale-blue luminous panel with a warm
    sun lamp). The places are those of the hydroponics bay (the botanists work on the path)."""
    spec, L, D, H = _dims("hydro")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = TH.living(floor=TERRAZZO, floor2=CARPET_MOSS, border=0.0, inlay=None, wall_lo=PLASTER_SAGE, wall_hi=PLASTER_IVORY, wall_acc=WEAVE_SAND, wain_h=0.9, accent="green_dim",
                   wall_pattern=("panel", "slats", "panel"), ceiling="flat", skirt=OAK, strip="white_warm", light_cell="ice")
    build_shell(b, spec, st)
    rng = random.Random(57)
    x0, x1, y0, y1 = WS + WF, L - WS - WF, WF, D - WS - WF
    # the sky: a luminous panel over most of the ceiling in a pale daylight white-blue, with a warm "sun" strip along one side
    b.emit.lamp_box((x0 + 1.0, y0 + 1.5, H - 0.056), (x1 - 1.0, y1 - 1.5, H - 0.05), "ice", LAMP)
    b.body.box((x0 + 0.9, y0 + 1.4, H - 0.09), (x1 - 0.9, y0 + 1.5, H - 0.05), TRIM)
    b.body.box((x0 + 0.9, y1 - 1.5, H - 0.09), (x1 - 0.9, y1 - 1.4, H - 0.05), TRIM)
    b.body.box((x0 + 0.9, y0 + 1.5, H - 0.09), (x0 + 1.0, y1 - 1.5, H - 0.05), TRIM)
    b.body.box((x1 - 1.0, y0 + 1.5, H - 0.09), (x1 - 0.9, y1 - 1.5, H - 0.05), TRIM)
    # the pergola: oak beams across the path with vines hanging from them
    for xb in (4.0, 9.0, 14.0, 19.0):
        b.body.box((xb - 0.07, y0 + 0.4, H - 0.5), (xb + 0.07, y1 - 0.4, H - 0.3), OAK)
    # the path (a terrazzo strip that the field of the floor already is) edged in oak, the cross path from the door
    for ya, yb in ((6.2, 6.28), (9.72, 9.8)):
        b.body.box((x0, ya, 0.0), (x1, yb, 0.03), OAK)
    dx_ = spec["doors"][0]["x"] - 1.1
    b.body.box((dx_, y0, 0.0), (dx_ + 0.08, 6.2, 0.03), OAK)
    b.body.box((dx_ + 2.12, y0, 0.0), (dx_ + 2.2, 6.2, 0.03), OAK)
    # the planting beds: four beds of moss and lawn with mounds, ferns, calatheas, hostas, tufts of grass, flowers and stones, and a money tree in each
    for (xa, xb, ya, yb, seed) in ((x0 + 0.4, 8.6, y0 + 1.2, 6.0, 1), (11.4, x1 - 0.4, y0 + 1.2, 6.0, 2), (x0 + 0.4, 11.0, 10.0, y1 - 0.5, 3), (13.0, x1 - 0.4, 10.0, y1 - 0.5, 4)):
        w_, d_ = yb - ya, xb - xa
        with b.at(frame((xa + xb) / 2, (ya + yb) / 2, 0.0, 90.0)):
            PL.garden_bed(b, d_, w_, 0.42, seed, tree="pachira_a" if seed == 3 else "pachira_d", cover=MOSS if seed % 2 else GRASS)
    # vines hanging from the pergola beams
    for xb in (4.0, 9.0, 14.0, 19.0):
        y = y0 + 0.9
        while y < y1 - 0.8:
            with b.at(T(xb, y, H - 0.5)):
                PL.hanging_vine(b, rng.uniform(0.5, 1.4), int(xb * 10 + y * 3))
            y += rng.uniform(1.1, 2.1)
    # benches along the path, lanterns on posts, a drinking fountain
    for xb in (6.5, 11.8, 17.0):
        place(b, xb, 9.45, -90, F.bench, 2.0, 0.5, 0.46, LEATHER_TAN)
        place(b, xb, 6.5, 90, F.bench, 2.0, 0.5, 0.46, LEATHER_TAN)
    for (xp, yp) in ((3.0, 7.9), (21.0, 7.9), (12.0, 7.9)):
        place(b, xp, yp, 0, F.lamp_standard, 2.0)
    place(b, x1 - 0.4, 8.0, 180, DC.picture, 1.8, 1.0, 5, OAK, "sun", z=1.9)
    for k, xw in enumerate((5.0, 12.0, 19.0)):                                                                    # green walls on the far wall
        place(b, xw, y1 - 0.1, -90, PL.living_wall, 2.8, 2.5, 0.25, 20 + k)
    wall_label(b, 8.0, WF + 0.02, 2.1, (0, 1, 0), "room_hydro", 0.9)
    return b.build(name)
