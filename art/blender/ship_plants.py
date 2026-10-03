"""ASN Aquila interior kit (ARTE-INTERNI): the plants. Real ones from Poly Haven (CC0: a scanned fern, a calathea, a syngonium, a money tree — ship_assets.py) and procedural
ones made of real leaf geometry (ship_mk.leaf: a snake plant, a palm, a vine, the crops of the hydroponics bays), in pots and planters of the ship's own design.

Every function builds ONE piece in its own frame (origin on the floor at the middle of the piece) into an SParts, like the furniture:
  potted(b, kind, pot, ...)      a plant of `kind` in a pot of the ship (a ceramic cylinder or a bowl on a steel foot)
  planter_bed(b, w, d, h, ...)   a long planter (steel box with a soil bed) planted with ferns, calatheas and anthuriums, and a tree at one end if `tall`
  floor_tree(b, ...)             a money tree in a big round tub
  snake_plant, palm, vine, hanging_basket, lettuce_head, tray_*      procedural plants
"""
from __future__ import annotations

import math
import random

import ship_assets as SA
import ship_mk as MK
from bridge3_lib import Rz, T
from ship_lib import (BARK, BRASS, CERAMIC, COMPOSITE, LEAF_GREEN, LETTUCE, SOIL, STEEL, STEM, STRUCT, TERRACOTTA, TRIM, WHITE_GLOSS, SParts)

PH = "MI_SHIP_PH_"
# the Poly Haven models used (ship_assets.register: name, glTF id, material map, objects picked, decimation); every one is in docs/licenze.csv
SA.register("syngonium", "potted_plant_02", {"potted_plant_02_leaves": PH + "Syngonium"}, pick=["potted_plant_02_leaves"], decimate=0.55, two_sided=["potted_plant_02_leaves"])
SA.register("haworthia", "potted_plant_04", {"potted_plant_04": PH + "Haworthia"}, two_sided=["potted_plant_04"], drop=())
SA.register("ficus", "potted_plant_01", {"potted_plant_01_leaves": PH + "FicusLeaf", "potted_plant_01_pot": PH + "FicusWood"}, pick=["potted_plant_01_leaves", "potted_plant_01_stem"],
            decimate=0.2, two_sided=["potted_plant_01_leaves"])
SA.register("pachira_d", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_d", "pachira_aquatica_01_leaves_d"], decimate=0.5, two_sided=["pachira_aquatica_01_leaves"])
SA.register("pachira_c", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_c", "pachira_aquatica_01_leaves_c"], decimate=0.6, two_sided=["pachira_aquatica_01_leaves"])
SA.register("pachira_a", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_a", "pachira_aquatica_01_leaves_a"], decimate=0.6, two_sided=["pachira_aquatica_01_leaves"])
for k in "bc":
    SA.register(f"fern_{k}", "fern_02", {"fern_02": PH + "Fern"}, pick=[f"fern_02_{k}"], two_sided=["fern_02"])
for k in "abc":
    SA.register(f"calathea_{k}", "calathea_orbifolia_01", {"calathea_orbifolia_01": PH + "Calathea"}, pick=[f"calathea_orbifolia_01_{k}"], two_sided=["calathea_orbifolia_01"])
for k in "bc":
    SA.register(f"anthurium_{k}", "anthurium_botany_01", {"anthurium_botany_01": PH + "Anthurium"}, pick=[f"anthurium_botany_01_{k}"], decimate=0.6, two_sided=["anthurium_botany_01"])


# ------------------------------------------------------------------------------------------------------------------------------------ pots
def pot(b: SParts, kind: str = "cyl", r: float = 0.2, h: float = 0.4, mat: str = CERAMIC, soil: bool = True, soil_dz: float = 0.04) -> float:
    """A pot centred on the origin; returns the height of the soil surface. kind: cyl (a straight ceramic cylinder with a rolled rim), bowl (a wide low bowl on a steel foot),
    cone (a tapered pot), tub (a big round tub for a tree)."""
    if kind == "bowl":
        b.body.cyl((0, 0, 0.0), (0, 0, h * 0.2), r * 0.3, STEEL, seg=20, r2=r * 0.36)
        MK.lathe(b.body, [(r * 0.34, h * 0.16), (r * 0.5, h * 0.2), (r * 0.78, h * 0.45), (r * 0.96, h * 0.82), (r, h), (r * 0.93, h), (r * 0.88, h * 0.78), (r * 0.62, h * 0.38),
                          (r * 0.3, h * 0.26)], (0, 0, 0), mat, seg=28)
        top = h * 0.8
    elif kind == "cone":
        MK.lathe(b.body, [(r * 0.62, 0.0), (r * 0.64, h * 0.04), (r * 0.9, h * 0.9), (r, h * 0.96), (r, h), (r * 0.9, h), (r * 0.84, h * 0.88), (r * 0.58, h * 0.07)], (0, 0, 0), mat, seg=28)
        top = h * 0.88
    elif kind == "tub":
        MK.lathe(b.body, [(r * 0.86, 0.0), (r * 0.9, h * 0.04), (r, h * 0.12), (r * 1.0, h * 0.9), (r * 1.04, h), (r * 0.94, h), (r * 0.9, h * 0.9), (r * 0.82, h * 0.08)], (0, 0, 0), mat, seg=32)
        b.fine.cyl((0, 0, h * 0.5 - 0.02), (0, 0, h * 0.5 + 0.02), r * 1.012, STEEL, seg=32)
        top = h * 0.9
    else:                                                                    # cyl
        MK.lathe(b.body, [(r * 0.94, 0.0), (r * 0.98, h * 0.03), (r, h * 0.1), (r, h * 0.94), (r * 1.04, h * 0.97), (r * 1.04, h), (r * 0.94, h), (r * 0.92, h * 0.9), (r * 0.88, h * 0.06)], (0, 0, 0), mat, seg=28)
        top = h * 0.9
    if soil:
        b.soft.cyl((0, 0, top - 0.01), (0, 0, top + soil_dz * 0.0), r * 0.9, SOIL, seg=24)
    return top


def potted(b: SParts, kind: str = "syngonium", pot_kind: str = "bowl", pot_r: float = 0.22, pot_h: float = 0.3, mat: str = CERAMIC, scale: float = 1.0, yaw: float = 0.0) -> float:
    """A Poly Haven plant (leaves and stems only) standing in a pot of the ship. Returns the plant's top height. Origin on the floor at the pot's centre."""
    top = pot(b, pot_kind, pot_r, pot_h, mat)
    SA.add(b.soft, kind, (0.0, 0.0, top - 0.01), yaw, scale)
    return top + SA.get(kind)["size"][2] * scale


def haworthia(b: SParts, scale: float = 1.0, yaw: float = 0.0) -> float:
    """The scanned zebra plant in its white ceramic pot (a desk plant, 27 cm)."""
    SA.add(b.soft, "haworthia", (0.0, 0.0, 0.0), yaw, scale)
    return SA.get("haworthia")["size"][2] * scale


def floor_tree(b: SParts, kind: str = "pachira_d", tub_r: float = 0.34, mat: str = CERAMIC, scale: float = 1.0, yaw: float = 0.0, pot_h: float = 0.45) -> float:
    """A money tree standing in a big round tub (a lounge, a concourse, a garden). Origin on the floor at the tub's centre; returns the height of the top."""
    top = pot(b, "tub", tub_r, pot_h, mat)
    SA.add(b.soft, kind, (0.0, 0.0, top - 0.005), yaw, scale)
    return top + SA.get(kind)["size"][2] * scale


# --------------------------------------------------------------------------------------------------------------------------------- planters
def planter_bed(b: SParts, w: float = 2.0, d: float = 0.7, h: float = 0.45, seed: int = 1, tall: bool = False, density: float = 1.0, skin=STEEL, kinds=None) -> float:
    """A long planter: a steel tray on a brushed foot with a rolled lip and a bed of soil, planted with ferns, calatheas and anthuriums in a row (a tree at one end when `tall`).
    Centred on the origin, `w` along y (the long side), `d` along x. Returns the height of the plantation."""
    rng = random.Random(seed)
    MK.rbox(b.body, (-d / 2, -w / 2, 0.06), (d / 2, w / 2, h), 0.02, skin, 2)
    b.body.box((-d / 2 - 0.015, -w / 2 - 0.015, h - 0.035), (d / 2 + 0.015, w / 2 + 0.015, h), TRIM)
    b.fine.box((-d / 2 + 0.05, -w / 2 + 0.05, 0.0), (d / 2 - 0.05, w / 2 - 0.05, 0.06), STRUCT)
    b.soft.box((-d / 2 + 0.025, -w / 2 + 0.025, h - 0.06), (d / 2 - 0.025, w / 2 - 0.025, h - 0.012), SOIL)
    kinds = kinds or ["fern_b", "calathea_b", "fern_c", "anthurium_c", "calathea_c", "fern_b", "calathea_a", "anthurium_b"]
    n = max(2, int(round(w / 0.62 * density)))
    top = h
    for k in range(n):
        y = -w / 2 + (k + 0.5) * w / n + rng.uniform(-0.05, 0.05)
        kind = kinds[(k + seed) % len(kinds)]
        sc = rng.uniform(0.75, 1.1) * (min(1.0, d / 0.5))
        SA.add(b.soft, kind, (rng.uniform(-d * 0.15, d * 0.15), y, h - 0.04), rng.uniform(0, 360), sc)
        top = max(top, h + SA.get(kind)["size"][2] * sc)
    if tall:
        SA.add(b.soft, "pachira_c", (0.0, w / 2 - 0.45, h - 0.04), rng.uniform(0, 360), 0.9)
        top = h + SA.get("pachira_c")["size"][2] * 0.9
    return top


# ------------------------------------------------------------------------------------------------------------------ procedural plants
def snake_plant(b: SParts, r: float = 0.2, h: float = 0.75, n: int = 14, seed: int = 1, mat: str = LEAF_GREEN) -> None:
    """Upright sword leaves (sansevieria) in a cluster, in a pot of the ship: origin on the floor at the pot's centre."""
    rng = random.Random(seed)
    top = pot(b, "cone", 0.17, 0.3, CERAMIC)
    for k in range(n):
        a = k * 2.399963
        rr = rng.uniform(0.0, r * 0.45)
        base = (rr * math.cos(a), rr * math.sin(a), top - 0.02)
        lean = rng.uniform(0.04, 0.26)
        d = (math.cos(a) * lean, math.sin(a) * lean, 1.0)
        L = h * rng.uniform(0.55, 1.0) - 0.25
        MK.leaf(b.soft, base, d, (math.cos(a + 1.57), math.sin(a + 1.57), 0), L, rng.uniform(0.055, 0.085), mat, tile=2, droop=0.08, fold=0.18, nu=4, nv=1, twist=rng.uniform(-30, 30), shape=0.55, seed=k)


def palm(b: SParts, h: float = 1.9, fronds: int = 9, seed: int = 3, tub_r: float = 0.3) -> float:
    """A kentia-style palm: slim canes from a tub, long arching fronds with paired leaflets (real leaf geometry)."""
    rng = random.Random(seed)
    top = pot(b, "tub", tub_r, 0.5, CERAMIC)
    for c in range(3):
        a0 = c * 2.1 + rng.uniform(0, 1)
        cane_h = h * rng.uniform(0.55, 0.75)
        lean = rng.uniform(0.0, 0.12)
        pts = [(0.05 * math.cos(a0) + lean * math.cos(a0) * (k / 6.0) ** 2, 0.05 * math.sin(a0) + lean * math.sin(a0) * (k / 6.0) ** 2, top + cane_h * k / 6.0) for k in range(7)]
        b.soft.tube(pts, 0.014, BARK, seg=6)
        tipx, tipy, tipz = pts[-1]
        for f in range(fronds // 3 + 2):
            a = a0 + f * 2.399 + rng.uniform(-0.2, 0.2)
            pitch = rng.uniform(0.35, 1.0)
            dirv = (math.cos(a) * math.cos(pitch), math.sin(a) * math.cos(pitch), math.sin(pitch) + 0.55)
            n = 9
            flen = rng.uniform(0.7, 1.0)
            for j in range(n):
                s = (j + 1) / (n + 1)
                # the rachis arches: points along the frond
                bx = tipx + dirv[0] * flen * s * 0.8
                by = tipy + dirv[1] * flen * s * 0.8
                bz = tipz + dirv[2] * flen * s * 0.8 - 0.55 * flen * s * s
                for side in (-1, 1):
                    la = a + side * 1.25
                    ll = flen * 0.32 * math.sin(math.pi * (0.15 + 0.85 * s) ) + 0.05
                    MK.leaf(b.soft, (bx, by, bz), (math.cos(la) * 0.9, math.sin(la) * 0.9, -0.25), (0, 0, 1), ll, 0.035, LEAF_GREEN, tile=2, droop=0.3, fold=0.12, nu=3, nv=1,
                            shape=0.6, backface=False, seed=j)
            # the rachis itself
            pts_r = [(tipx + dirv[0] * flen * t * 0.8, tipy + dirv[1] * flen * t * 0.8, tipz + dirv[2] * flen * t * 0.8 - 0.55 * flen * t * t) for t in (0.0, 0.3, 0.6, 0.9)]
            b.soft.tube(pts_r, 0.006, STEM, seg=4, caps=False)
    return top + h
