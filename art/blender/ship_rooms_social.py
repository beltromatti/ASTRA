"""ASN Aquila interior kit: the social rooms of Deck 4 — the crew lounge, the games room, the library, the quiet room, the observation
deck (a flank window wall) and the bow observation deck (a special: its own frame, a panoramic window on the forward wall).
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_furniture2 as G
import ship_spec as SPEC
from bridge3_lib import T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
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
    spec, L, D, H = _dims("lounge")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=1.05, ceil=IVORY, accent="warm_dim",
               cove="white_warm", rib_mat=TRIM, skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    # two conversation groups on rugs: armchairs turned in, a low table, a sofa, a floor lamp, a plant
    for k, yc in enumerate((5.3, 12.7)):
        place(b, 5.9, yc, 0, G.rug, 6.6, 4.6, FABRIC_RUST if k == 0 else FABRIC_NAVY, FABRIC_SAND)
        place(b, 5.9, yc, 0, F.low_table, 1.3, 0.7, 0.4, WOOD)
        place(b, 4.0, yc - 1.3, 45, F.armchair, FABRIC_SAND)
        place(b, 4.0, yc + 1.3, -45, F.armchair, FABRIC_SAND)
        place(b, 7.9, yc, 180, F.sofa, 2.6, FABRIC_NAVY if k == 0 else FABRIC_RUST)
        place(b, 2.9, yc + (2.0 if k == 0 else -2.0), 0, F.lamp_standard, 1.5)
        place(b, 9.1, yc + (2.1 if k == 0 else -2.1), 0, F.potted_plant, 1.2, k)
    place(b, 0.32, 9.0, 0, F.wall_screen, 2.0, 1.1, "scr_news", z=1.9)
    place(b, 0.30, 9.0, 0, F.bench, 1.4, 0.36, 0.44, FABRIC_GREY)
    # the café corner: two tables with chairs, a snack bar with stools, a back bar with mugs and bottles, a coffee machine
    for xt in (15.4, 19.6):
        place(b, xt, 5.4, 0, F.table, 1.2, 0.8, 0.74, LAMINATE, TRIM, False)
        place(b, xt, 4.3, 90, F.chair, FABRIC_RUST)
        place(b, xt, 6.5, -90, F.chair, FABRIC_RUST)
    place(b, 20.7, 5.4, 180, F.chair, FABRIC_RUST)
    place(b, 14.3, 5.4, 0, F.chair, FABRIC_RUST)
    place(b, 23.0, 2.0, 0, F.potted_plant, 1.4, 5)
    place(b, 23.73, 5.4, 180, F.wall_screen, 2.2, 1.2, "scr_menu", z=1.9)
    place(b, 19.0, 12.6, -90, G.bar_counter, 6.8, 0.7, 1.08)
    for i in range(5):
        place(b, 16.4 + 1.3 * i, 11.5, 0, G.bar_stool, 0.72, FABRIC_RUST)
    place(b, 19.0, yf - 0.17, -90, G.back_bar, 6.4, 2.1, 0.34, 4)
    for x in (17.2, 20.8):
        place(b, x, 12.7, -90, G.coffee_machine, z=1.08)
    place(b, 22.6, 14.7, 0, F.locker_row, 2, 0.5, 1.2, 0.5, COMPOSITE)
    # the far door (x 14) opens onto the side passage: keep a notice board beside it
    place(b, 12.2, yf - 0.02, -90, F.wall_screen, 1.1, 0.8, "scr_sched", z=1.7)
    ceiling_panels(b, L, D, H, 4, 3, "white_warm", 2.5, 0.6, 0.6, LAMP)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------- games
def games(name: str = "SM_SHIP_Games"):
    spec, L, D, H = _dims("games")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_NAVY, floor_mode="covering", seams=False, wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.05, ceil=COMPOSITE, accent="violet",
               cove="violet", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    # card tables (felt tops, four chairs, a pendant lamp)
    for k, (xt, yt) in enumerate(((6.0, 5.0), (6.0, 11.0), (13.0, 4.0))):
        place(b, xt, yt, 0, F.table, 1.3, 1.3, 0.74, LEAF, TRIM, True)
        for dx, dy, yaw in ((-1.0, 0, 0), (1.0, 0, 180), (0, -1.0, 90), (0, 1.0, -90)):
            place(b, xt + dx, yt + dy, yaw, F.chair, FABRIC_RUST if (k + int(dx + dy)) % 2 else FABRIC_GREY)
        place(b, xt, yt, 0, G.pendant_bar, 1.4, 0.3, 2.3, H - 0.05, "white_warm", LAMP)
        rng = random.Random(k)
        for j in range(5):
            place(b, xt + rng.uniform(-0.4, 0.4), yt + rng.uniform(-0.4, 0.4), rng.uniform(0, 360), _card, z=0.74)
    # the billiard table with its long lamp
    place(b, 17.0, 8.0, 0, G.billiard_table, 2.7, 1.5, 0.84)
    place(b, 17.0, 8.0, 0, G.pendant_bar, 2.4, 0.3, 2.3, H - 0.05, "white_warm", LAMP)
    for y in (5.2, 10.8):
        place(b, 17.0, y, 0, F.chair, FABRIC_GREY)
    # a row of arcade cabinets along the far wall
    screens = ["scr_map", "scr_lab", "scr_news", "scr_dir", "scr_sched", "scr_menu"]
    accents = ["violet", "cyan", "amber", "green", "red", "ice"]
    for i in range(6):
        place(b, 16.5 + 1.0 * i, yf - 0.36, -90, G.arcade_cabinet, screens[i], accents[i])
    place(b, 0.32, 8.0, 0, F.wall_screen, 3.0, 1.2, "scr_sched", z=2.0)
    place(b, 0.9, 13.6, 0, F.potted_plant, 1.5, 3)
    place(b, 22.9, 2.4, 0, F.potted_plant, 1.5, 4)
    place(b, 23.2, 5.6, 180, F.sofa, 2.4, FABRIC_RUST)
    place(b, 21.9, 5.6, 0, F.low_table, 0.9, 0.6, 0.4, WOOD)
    ceiling_panels(b, L, D, H, 4, 3, "white_warm", 2.5, 0.5, 0.5, LAMP)
    for y in (3.0, 13.0):
        lamp_strip(b.emit, (2.0, y, H - 0.06), (L - 2.0, y, H - 0.06), 0.06, 0.006, "violet", LAMP_DIM)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------ library
def library(name: str = "SM_SHIP_Library"):
    spec, L, D, H = _dims("library")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=FABRIC_GREY, floor_mode="covering", seams=False, wall_lo=WOOD, wall_hi=COMPOSITE, wain_h=0.9, ceil=COMPOSITE, accent="warm_dim",
               cove="warm_dim", ribs=False, skirt=WOOD)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF + 0.17, L - WS - WF - 0.17
    for k in range(5):
        place(b, xl, 1.95 + 2.9 * k, 0, F.shelf, 2.9, 0.34, 2.6, 7, WOOD, True, 11 + k, True)
    for k in range(1, 5):
        place(b, xr, 1.95 + 2.9 * k, 180, F.shelf, 2.9, 0.34, 2.6, 7, WOOD, True, 21 + k, True)
    for k in range(5):
        place(b, 1.9 + 2.85 * k, yf - 0.17, -90, F.shelf, 2.8, 0.34, 2.6, 7, WOOD, True, 31 + k, True)
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
    place(b, 13.6, 3.0, 0, F.chair, FABRIC_GREY)
    place(b, 10.0, 12.2, 0, F.potted_plant, 1.3, 7)
    ceiling_panels(b, L, D, H, 3, 3, "white_warm", 2.2, 0.5, 0.5, LAMP)
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
    spans = window_wall(b, "far", L, D, H, st, 5)
    yf = D - WS - WF
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
        place(b, xa, 7.0, 0 if xa < xb else 180, F.armchair, FABRIC_GREY)
        place(b, xb, 7.0, 180 if xa < xb else 0, F.armchair, FABRIC_GREY)
        place(b, xt, 7.0, 0, F.low_table, 0.9, 0.6, 0.4, WOOD)
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


