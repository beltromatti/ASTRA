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
from ship_lib import (BARK, BRASS, CERAMIC, COMPOSITE, LAMP, LAMP_HOT, LEAF_GREEN, LETTUCE, SOIL, STEEL, STEM, STRUCT, SWATCH, TERRACOTTA, TRIM, WHITE_GLOSS, SParts)

PH = "MI_SHIP_PH_"
# the Poly Haven models used (ship_assets.register: name, glTF id, material map, objects picked, decimation); every one is in docs/licenze.csv
SA.register("syngonium", "potted_plant_02", {"potted_plant_02_leaves": PH + "Syngonium"}, pick=["potted_plant_02_leaves"], decimate=0.4, two_sided=["potted_plant_02_leaves"])
SA.register("haworthia", "potted_plant_04", {"potted_plant_04": PH + "Haworthia"}, decimate=0.35, two_sided=["potted_plant_04"], drop=())
SA.register("ficus", "potted_plant_01", {"potted_plant_01_leaves": PH + "FicusLeaf", "potted_plant_01_pot": PH + "FicusWood"}, pick=["potted_plant_01_leaves", "potted_plant_01_stem"],
            decimate=0.12, two_sided=["potted_plant_01_leaves"])
SA.register("pachira_d", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_d", "pachira_aquatica_01_leaves_d"], decimate=0.35, two_sided=["pachira_aquatica_01_leaves"])
SA.register("pachira_c", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_c", "pachira_aquatica_01_leaves_c"], decimate=0.4, two_sided=["pachira_aquatica_01_leaves"])
SA.register("pachira_a", "pachira_aquatica_01", {"pachira_aquatica_01_bark": PH + "PachiraBark", "pachira_aquatica_01_leaves": PH + "PachiraLeaf"},
            pick=["pachira_aquatica_01_bark_a", "pachira_aquatica_01_leaves_a"], decimate=0.4, two_sided=["pachira_aquatica_01_leaves"])
for k in "bc":
    SA.register(f"fern_{k}", "fern_02", {"fern_02": PH + "Fern"}, pick=[f"fern_02_{k}"], decimate=0.6, two_sided=["fern_02"])
for k in "abc":
    SA.register(f"calathea_{k}", "calathea_orbifolia_01", {"calathea_orbifolia_01": PH + "Calathea"}, pick=[f"calathea_orbifolia_01_{k}"], decimate=0.6 if k == "a" else 0.7,
                two_sided=["calathea_orbifolia_01"])
for k in "bc":
    SA.register(f"anthurium_{k}", "anthurium_botany_01", {"anthurium_botany_01": PH + "Anthurium"}, pick=[f"anthurium_botany_01_{k}"], decimate=0.45, two_sided=["anthurium_botany_01"])


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
    """A long planter: a rounded tray in `skin` on a recessed foot with a brushed rim and a mound of soil standing proud of it, planted with ferns, calatheas and anthuriums in a row (a
    money tree at one end when `tall`). Centred on the origin, `w` along y (the long side), `d` along x. Returns the height of the plantation."""
    rng = random.Random(seed)
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.07), (d / 2, w / 2, h), 0.02, skin, 2)
    b.fine.box((-d / 2 + 0.05, -w / 2 + 0.05, 0.0), (d / 2 - 0.05, w / 2 - 0.05, 0.07), STRUCT)
    b.fine.box((-d / 2 - 0.006, -w / 2 - 0.006, h - 0.03), (d / 2 + 0.006, w / 2 + 0.006, h - 0.012), TRIM)                      # the rim line
    MK.rbox(b.soft, (-d / 2 + 0.05, -w / 2 + 0.05, h - 0.02), (d / 2 - 0.05, w / 2 - 0.05, h + 0.055), 0.03, SOIL, 2)           # the soil, heaped a little
    kinds = kinds or ["fern_b", "calathea_b", "fern_c", "anthurium_c", "calathea_c", "fern_b", "calathea_a", "anthurium_b"]
    n = max(2, int(round(w / 0.62 * density)))
    top = h
    for k in range(n):
        y = -w / 2 + (k + 0.5) * w / n + rng.uniform(-0.05, 0.05)
        kind = kinds[(k + seed) % len(kinds)]
        sc = rng.uniform(0.8, 1.15) * (min(1.0, d / 0.5))
        SA.add(b.soft, kind, (rng.uniform(-d * 0.15, d * 0.15), y, h + 0.02), rng.uniform(0, 360), sc)
        top = max(top, h + SA.get(kind)["size"][2] * sc)
    if tall:
        SA.add(b.soft, "pachira_c", (0.0, w / 2 - 0.45, h + 0.02), rng.uniform(0, 360), 0.9)
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


# ------------------------------------------------------------------------------------------------------------------------ crops
def lettuce_head(b: SParts, r: float = 0.11, leaves: int = 9, seed: int = 1, tile: int = 1, mat: str = LETTUCE) -> None:
    """A lettuce rosette of real leaf geometry (origin at its base): leaves round a core, the outer ones opening wide, ruffled at the margin. About 100 triangles."""
    rng = random.Random(seed)
    for k in range(leaves):
        a = k * 2.399963 + rng.uniform(-0.2, 0.2)
        t = k / max(1, leaves - 1)
        pitch = 0.9 - 0.75 * t                                    # inner leaves stand up, outer ones lie out
        d = (math.cos(a) * math.cos(pitch), math.sin(a) * math.cos(pitch), math.sin(pitch))
        MK.leaf(b.soft, (0.0, 0.0, 0.01), d, (0, 0, 1), r * (0.65 + 0.5 * t) * rng.uniform(0.9, 1.1), r * (0.55 + 0.45 * t), mat, tile=tile, droop=0.35 + 0.3 * t, fold=0.25, cup=0.5,
                nu=3, nv=1, wave=0.01 if t > 0.4 else 0.0, shape=0.9, seed=k + seed)


def desk_plant(b: SParts, seed: int = 1) -> None:
    """A small plant for a desk or a shelf (origin at the middle of the pot's base): a twelve-sided pot, wider at the rim, in ceramic or terracotta, with a rosette of fleshy leaves or a
    sprig of herbs in it; about 250 triangles (a scanned plant of that size costs three thousand)."""
    rng = random.Random(seed)
    r, h = rng.uniform(0.045, 0.06), rng.uniform(0.07, 0.1)
    b.fine.cyl((0, 0, 0.0), (0, 0, h), r * 0.8, rng.choice((CERAMIC, TERRACOTTA, WHITE_GLOSS)), seg=12, r2=r)
    b.soft.cyl((0, 0, h - 0.01), (0, 0, h), r * 0.96, SOIL, seg=12)
    with b.at(T(0.0, 0.0, h)):
        if seed % 2:
            lettuce_head(b, 0.075, 8, seed, 1, LEAF_GREEN)
        else:
            herb_bush(b, 0.15, seed)


def herb_bush(b: SParts, h: float = 0.28, seed: int = 1, mat: str = LEAF_GREEN, tile: int = 3) -> None:
    """A basil-like herb: a few stems with pairs of small broad leaves (origin at the base)."""
    rng = random.Random(seed)
    for s in range(3):
        a = s * 2.1 + rng.uniform(0, 1)
        lean = rng.uniform(0.05, 0.25)
        hs = h * rng.uniform(0.7, 1.0)
        for j in range(4):
            z = 0.05 + hs * (j + 1) / 4
            for side in (-1, 1):
                la = a + side * 1.4 + j * 0.5
                MK.leaf(b.soft, (math.cos(a) * lean * z, math.sin(a) * lean * z, z), (math.cos(la), math.sin(la), 0.35), (0, 0, 1), 0.05 + 0.012 * (3 - j), 0.035 + 0.01 * (3 - j), mat, tile=tile,
                        droop=0.3, fold=0.3, nu=2, nv=1, shape=0.9, seed=s * 10 + j)


def grain_clump(b: SParts, h: float = 0.5, n: int = 9, seed: int = 1, mat: str = LEAF_GREEN) -> None:
    """A clump of wheat or leek blades (origin at the base): long thin leaves arching out, a seed head on a few."""
    rng = random.Random(seed)
    for k in range(n):
        a = k * 2.4 + rng.uniform(-0.3, 0.3)
        lean = rng.uniform(0.1, 0.5)
        MK.leaf(b.soft, (0.0, 0.0, 0.0), (math.cos(a) * lean, math.sin(a) * lean, 1.0), (math.cos(a + 1.57), math.sin(a + 1.57), 0), h * rng.uniform(0.7, 1.0), 0.022, mat, tile=2, droop=0.5,
                fold=0.2, nu=3, nv=1, shape=0.55, seed=k)


def tomato_vine(b: SParts, h: float = 1.3, seed: int = 1) -> None:
    """A tomato plant on a string (origin at the base): a stem, leaves up the stem and a few red fruits."""
    rng = random.Random(seed)
    pts = [(0.0, 0.0, 0.0), (0.02, 0.01, h * 0.35), (-0.01, 0.02, h * 0.7), (0.03, -0.01, h)]
    b.soft.tube(pts, 0.008, STEM, seg=5)
    for j in range(7):
        z = 0.2 + (h - 0.25) * j / 6
        a = j * 2.2 + rng.uniform(0, 1)
        MK.leaf(b.soft, (0.0, 0.0, z), (math.cos(a), math.sin(a), 0.4), (0, 0, 1), 0.2, 0.12, LEAF_GREEN, tile=3, droop=0.5, fold=0.2, nu=3, nv=1, shape=0.8, seed=j)
        if j in (2, 4):
            c = (math.cos(a + 0.6) * 0.07, math.sin(a + 0.6) * 0.07, z - 0.05)
            for f in range(3):
                b.soft.paint(MK.puff(b.soft, (c[0] + 0.03 * f, c[1] + 0.02 * f, c[2] - 0.03 * f), (0.026, 0.026, 0.024), SWATCH, e=1.0, nu=8, nv=5), "f_tomato")


def seedling_mat(b: SParts, w: float, d: float, seed: int = 1, density: int = 70) -> None:
    """A tray of micro-greens: a mat of tiny two-leaf seedlings (centred on the origin, w along x, d along y)."""
    rng = random.Random(seed)
    for k in range(density):
        x, y = rng.uniform(-w / 2 + 0.03, w / 2 - 0.03), rng.uniform(-d / 2 + 0.03, d / 2 - 0.03)
        a = rng.uniform(0, 6.28)
        for side in (-1, 1):
            MK.leaf(b.soft, (x, y, 0.0), (math.cos(a + side * 1.2) * 0.8, math.sin(a + side * 1.2) * 0.8, 0.5), (0, 0, 1), 0.045, 0.03, LEAF_GREEN, tile=1, droop=0.3, fold=0.2,
                    nu=1, nv=1, shape=0.9, seed=k)


def grow_rack(b: SParts, length: float = 4.8, tiers: int = 4, depth: float = 0.66, crop: str = "lettuce", seed: int = 1, height: float = 2.35, led: str = "white_cool") -> None:
    """One vertical-farm rack, origin at the middle of its foot on the floor, length along x: steel uprights every 1.2 m, a water tray on every tier with the crop growing in a row of
    net pots, a bar of LED light under the tier above (a pale bar with a thin violet edge: a grow light that is also a light to see by), a nutrient line along the back with drip
    fittings. `crop`: lettuce | herb | grain | tomato | seedling | mix."""
    rng = random.Random(seed)
    hl = length / 2
    zs = [0.28 + t * (height - 0.45) / tiers for t in range(tiers)]
    # frame
    n_up = max(2, int(round(length / 1.2)) + 1)
    for k in range(n_up):
        x = -hl + k * length / (n_up - 1)
        for sy in (-depth / 2, depth / 2 - 0.05):
            b.body.box((x - 0.03, sy, 0.0), (x + 0.03, sy + 0.05, height), STRUCT)
    b.body.box((-hl, -depth / 2, height - 0.04), (hl, depth / 2, height), STRUCT)
    for t, z in enumerate(zs):
        b.body.box((-hl, -depth / 2 + 0.02, z - 0.05), (hl, depth / 2 - 0.02, z), STEEL)                    # the tray's floor
        b.fine.box((-hl + 0.02, -depth / 2 + 0.03, z), (hl - 0.02, -depth / 2 + 0.05, z + 0.085), STEEL)     # tray walls
        b.fine.box((-hl + 0.02, depth / 2 - 0.05, z), (hl - 0.02, depth / 2 - 0.03, z + 0.085), STEEL)
        b.soft.box((-hl + 0.025, -depth / 2 + 0.05, z + 0.0), (hl - 0.025, depth / 2 - 0.05, z + 0.03), "MI_SHIP_Terracotta" if False else SOIL)   # the nutrient bath
        b.soft.box((-hl + 0.03, -depth / 2 + 0.055, z + 0.03), (hl - 0.03, depth / 2 - 0.055, z + 0.05), WHITE_GLOSS)                    # the foam board the plants stand in
        kind = crop if crop != "mix" else ("lettuce", "herb", "grain", "seedling")[(t + seed) % 4]
        if kind == "seedling":
            with b.at(T(0.0, 0.0, z + 0.055)):
                seedling_mat(b, length - 0.15, depth - 0.18, seed + t, int(length * 22))
        else:
            n = max(2, int(length / 0.3))
            for k in range(n):
                px = -hl + (k + 0.5) * length / n
                b.soft.swatch_cyl((px, 0.0, z + 0.05), (px, 0.0, z + 0.058), 0.04, "charcoal", seg=10)                                    # the net pot's collar
                with b.at(T(px, 0.0, z + 0.055)):
                    if kind == "lettuce":
                        lettuce_head(b, 0.13 + rng.uniform(-0.015, 0.02), 9, seed * 100 + t * 20 + k, 1 if (k + t) % 3 else 0, LETTUCE if (k + t) % 2 else LEAF_GREEN)
                    elif kind == "herb":
                        herb_bush(b, 0.22 + rng.uniform(0, 0.08), seed + k)
                    elif kind == "tomato" and k % 2 == 0:
                        tomato_vine(b, min(0.55, zs[t + 1] - z - 0.15) if t + 1 < len(zs) else 0.55, seed + k)
                    else:
                        grain_clump(b, 0.35 + rng.uniform(0, 0.12), 7, seed + k)
        # the grow-light bar under the tier above (the top tier's sits under the crown)
        zl = (zs[t + 1] if t + 1 < len(zs) else height - 0.02) - 0.055
        b.body.box((-hl + 0.04, -depth / 2 + 0.07, zl - 0.03), (hl - 0.04, depth / 2 - 0.07, zl), STRUCT)
        b.emit.lamp_box((-hl + 0.06, -depth / 2 + 0.1, zl - 0.034), (hl - 0.06, depth / 2 - 0.1, zl - 0.03), led, LAMP_HOT)
        b.emit.lamp_box((-hl + 0.06, -depth / 2 + 0.075, zl - 0.034), (hl - 0.06, -depth / 2 + 0.1, zl - 0.03), "violet", LAMP)
        b.emit.lamp_box((-hl + 0.06, depth / 2 - 0.1, zl - 0.034), (hl - 0.06, depth / 2 - 0.075, zl - 0.03), "violet", LAMP)
    # the nutrient line along the back of the rack, drip tubes down to every tray
    b.body.cyl((-hl, depth / 2 - 0.03, height - 0.1), (hl, depth / 2 - 0.03, height - 0.1), 0.025, STEEL, seg=10)
    for k in range(n_up - 1):
        x = -hl + (k + 0.5) * length / (n_up - 1)
        b.fine.cyl((x, depth / 2 - 0.03, height - 0.1), (x, depth / 2 - 0.03, 0.3), 0.007, BRASS, seg=5)
