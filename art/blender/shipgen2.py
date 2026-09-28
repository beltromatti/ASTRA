"""ASTRA capital ships v2 (docs/STILE.md §2), built with the hard-surface kit (hullkit.py).

  Kharon Mandate — brutal, angular, asymmetric, blades raked forward; basalt armour, oxidised copper, radiators
  glowing orange, amber lights. The Acheron cruiser splits its bow into two blades around a spinal gun.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen2.py -- <out_dir> [--preview <png_dir>] [--only a,b]
Material slots are the v1 ones (MI_HULL_<faction>_<Part>), so Unreal's instances keep working.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bpy  # noqa: E402
import hullkit as K  # noqa: E402

PARTS = ("Plate", "Frame", "Livery", "Engine", "Glow", "Lights", "Radiator")
PLATE, FRAME, LIVERY, ENGINE, GLOW, LIGHTS, RADIATOR = (f"MI_HULL_{p}" for p in PARTS)


def profile(t: float, pts) -> float:
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


# ============================================================================================ Kharon Mandate
def light_strips(b, x0: float, x1: float, y: float, z: float, rows: int, rng: random.Random, s: float, lit: float = 0.6) -> None:
    """Deck lights that read from kilometres away: strips of lit ports, a few metres long, in broken rows."""
    for r in range(rows):
        zz = z + r * 3.4 * s
        x = x0 + rng.uniform(0, 6) * s
        while x < x1:
            ln = rng.uniform(4, 16) * s
            if rng.random() < lit:
                b.box((min(x + ln / 2, x1), y, zz), (min(ln, x1 - x), 0.3 * s, 1.1 * s), LIGHTS)
            x += ln + rng.uniform(3, 14) * s


def mandate_body(b, rng, stations_x, wp, hp, zp, W, H, skew, s, cell=9.0, mats=None):
    st = []
    x0, x1 = stations_x
    n = max(8, int((x1 - x0) / (14 * s)))
    for i in range(n + 1):
        t = i / n
        st.append((x0 + t * (x1 - x0), K.blade(W * profile(t, wp), H * profile(t, hp), skew), H * profile(t, zp)))
    h = K.Hull(b, st, PLATE, cell=cell * s)
    h.plate(rng, depth=(0.35 * s, 1.2 * s), recess=0.7 * s, margin=0.45 * s, skip=0.1, max_run=(3, 2),
            mats=mats if mats is not None else {LIVERY: 0.05, FRAME: 0.12})
    return h


def mandate_tower(b, rng, x: float, y: float, base: float, s: float, height: float = 1.0) -> None:
    """The command tower: stacked raked blocks narrowing upwards, an amber slit, masts."""
    hh = height
    K.slab(b, x - 44 * s, x + 30 * s, K.chamfer_rect(12 * s, 9 * s * hh, 0.3), K.chamfer_rect(8 * s, 7 * s * hh, 0.3), PLATE,
           base + 8 * s * hh, base + 11 * s * hh, y, y)
    K.slab(b, x - 26 * s, x + 38 * s, K.chamfer_rect(9 * s, 6 * s * hh, 0.35, top=0.7), K.chamfer_rect(3.5 * s, 4 * s * hh, 0.35, top=0.6),
           PLATE, base + 23 * s * hh, base + 28 * s * hh, y, y)
    K.slab(b, x - 18 * s, x + 16 * s, K.chamfer_rect(6 * s, 4 * s * hh, 0.4), K.chamfer_rect(3.5 * s, 3 * s * hh, 0.4), FRAME,
           base + 34 * s * hh, base + 36 * s * hh, y, y)
    for k in range(2):
        b.box((x + 32 * s - k * 4 * s, y, base + 25 * s * hh - k * 2.6 * s), (0.8 * s, 10 * s - k * 2.5 * s, 1.4 * s), LIGHTS)
    for side in (-1, 1):
        light_strips(b, x - 24 * s, x + 30 * s, y + side * 9.4 * s, base + 21 * s * hh, 2, rng, s, lit=0.8)
    K.mast(b, x - 4 * s, y, base + 38 * s * hh, 24 * s, FRAME, LIGHTS)
    K.mast(b, x + 8 * s, y + 3 * s, base + 37 * s * hh, 13 * s, FRAME, LIGHTS, dish=4.5 * s)


def mandate_engines(b, x: float, W: float, H: float, s: float, big: int, small: int) -> None:
    K.slab(b, x - 18 * s, x + 16 * s, K.chamfer_rect(W * 1.08, H * 1.1, 0.3), K.chamfer_rect(W * 0.96, H, 0.3), FRAME)
    K.engine_bank(b, x - 18 * s, 0, -H * 0.12, min(W, H) * 0.34, big, 1, W * 0.62, FRAME, ENGINE, GLOW)
    if small:
        K.engine_bank(b, x - 18 * s, 0, H * 0.62, min(W, H) * 0.17, small, 1, W * 0.9, FRAME, ENGINE, GLOW)
    K.running_lights(b, [(x - 14 * s, sy * W * 1.09, H * 0.95) for sy in (-1, 1)], 1.8 * s, LIGHTS)


def flank_armour(b, rng, x0: float, x1: float, W_at, H_at, s: float) -> None:
    for side in (-1, 1):
        x = x0
        while x < x1:
            ln = rng.uniform(30, 56) * s
            xm = min(x + ln, x1)
            w, hh = W_at(x + ln / 2), H_at(x + ln / 2) * rng.uniform(0.5, 0.75)
            zc = rng.uniform(-0.3, 0.05) * H_at(x)
            K.slab(b, x, xm, K.chamfer_rect(1.5 * s, hh, 0.45), K.chamfer_rect(1.5 * s, hh * 0.85, 0.45),
                   rng.choice([PLATE, PLATE, PLATE, FRAME, LIVERY]), zc, zc + 1.8 * s, side * (w + 2.8 * s), side * (w + 2.3 * s))
            x = xm + rng.uniform(5, 14) * s


def keel(b, x0: float, x1: float, depth: float, H: float, s: float, mat=FRAME) -> None:
    """A ventral blade keel, deepest amidships."""
    K.slab(b, x0, (x0 + x1) / 2, K.chamfer_rect(2.2 * s, depth * 0.4, 0.3), K.chamfer_rect(2.6 * s, depth, 0.3), mat,
           -H * 0.95 - depth * 0.3, -H * 0.95 - depth * 0.8)
    K.slab(b, (x0 + x1) / 2, x1, K.chamfer_rect(2.6 * s, depth, 0.3), K.chamfer_rect(1.4 * s, depth * 0.25, 0.3), mat,
           -H * 0.95 - depth * 0.8, -H * 0.95 - depth * 0.1)


def mandate_acheron(name: str, length: float = 460.0, seed: int = 11):
    """Cruiser: a heavy stern, a waist with the launch bays, armoured shoulders, two blades around the spinal gun."""
    rng = random.Random(seed)
    L = length
    s = L / 460.0
    b = A.Builder()
    W, H = 38 * s, 30 * s
    skew = -0.1
    x_st, x_fr = -L / 2, L * 0.22
    wp = [(0.0, 0.95), (0.22, 1.0), (0.3, 0.74), (0.52, 0.74), (0.6, 1.06), (0.9, 1.0), (1.0, 0.86)]
    hp = [(0.0, 1.0), (0.22, 1.0), (0.3, 0.78), (0.52, 0.8), (0.62, 1.0), (1.0, 0.76)]
    zp = [(0.0, 0.0), (0.8, 0.0), (1.0, 0.1)]
    mandate_body(b, rng, (x_st, x_fr), wp, hp, zp, W, H, skew, s)
    tt = lambda x: (x - x_st) / (x_fr - x_st)  # noqa: E731
    # the blades
    for side in (-1, 1):
        pst = []
        m = 12
        for i in range(m + 1):
            t = i / m
            x = x_fr - 8 * s + t * (L / 2 - x_fr + 8 * s)
            w = 14 * s * profile(t, [(0, 1.0), (0.55, 0.85), (1.0, 0.16)])
            h = 21 * s * profile(t, [(0, 1.0), (0.7, 0.7), (1.0, 0.2)])
            pst.append((x, [(yy + side * (12 * s + w), zz) for yy, zz in K.blade(w, h, 0.25 * side)], H * 0.1 + 9 * s * t * t))
        pr = K.Hull(b, pst, PLATE, cell=7.5 * s)
        pr.plate(rng, depth=(0.3 * s, 1.0 * s), recess=0.5 * s, margin=0.4 * s, skip=0.12, max_run=(2, 2), mats={LIVERY: 0.08})
        K.running_lights(b, [(L / 2 - 2 * s, side * 13 * s, H * 0.1 + 11 * s)], 2.2 * s, LIGHTS)
        light_strips(b, x_fr + 10 * s, L / 2 - 30 * s, side * (12 * s + 27 * s * 0.98), H * 0.1, 2, rng, s, lit=0.5)
    # the spinal gun: rails, accelerator rings, the muzzle
    b.cylinder((x_fr - 40 * s, 0, H * 0.2), (L / 2 - 10 * s, 0, H * 0.2 + 4 * s), 3.4 * s, FRAME, segments=16)
    b.cylinder((L / 2 - 18 * s, 0, H * 0.2 + 3.5 * s), (L / 2 - 8 * s, 0, H * 0.2 + 4.1 * s), 4.8 * s, FRAME, segments=16)
    for k in range(7):
        x = x_fr - 30 * s + k * 17 * s
        b.cylinder((x, 0, H * 0.2 + 0.45 * s * k), (x + 3 * s, 0, H * 0.2 + 0.45 * s * k), 5.6 * s, LIVERY, segments=16)
    # stern, keel, flank armour (not over the waist: the launch bays are there)
    mandate_engines(b, x_st, W, H, s, 3, 2)
    keel(b, x_st + 40 * s, x_fr - 10 * s, 16 * s, H, s)
    Wat = lambda x: W * profile(tt(x), wp)  # noqa: E731
    Hat = lambda x: H * profile(tt(x), hp)  # noqa: E731
    flank_armour(b, rng, x_st + 26 * s, x_st + 0.28 * (x_fr - x_st), Wat, Hat, s)
    flank_armour(b, rng, x_st + 0.58 * (x_fr - x_st), x_fr - 24 * s, Wat, Hat, s)
    for side in (-1, 1):   # the waist: launch bays and lit decks
        xm = x_st + 0.41 * (x_fr - x_st)
        K.hangar(b, xm, side * Wat(xm) * 0.98, -6 * s, 44 * s, 14 * s, 12 * s, FRAME, LIGHTS, side=side)
        light_strips(b, x_st + 30 * s, x_fr - 30 * s, side * (Wat(0) * 1.0 + 0.2 * s), 6 * s, 2, rng, s, lit=0.45)
    # the tower on the shoulders, dorsal radiators over the stern
    mandate_tower(b, rng, x_st + 0.64 * (x_fr - x_st), -W * 0.36, H * 0.96, s)
    for row, yy in enumerate((-W * 0.3, W * 0.3)):
        K.fins(b, x_st + 30 * s + row * 7 * s, x_st + 0.27 * (x_fr - x_st), yy, H * 0.98, 12 * s, 9, RADIATOR, thick=1.0 * s, rake=0.3)
    # turrets: triples on the shoulders and the stern deck, twins under the keel's flanks
    for x, y in ((x_fr - 30 * s, W * 0.3), (x_fr - 30 * s, -W * 0.05), (x_st + 0.22 * (x_fr - x_st), 0.0)):
        K.turret(b, (x, y, Hat(x) * 0.98 + 1.2 * s), 1.3 * s, 3, PLATE, FRAME)
    for x in (x_fr - 50 * s, x_st + 0.72 * (x_fr - x_st)):
        for side in (-1, 1):
            K.turret(b, (x, side * W * 0.5, -Hat(x) * 0.9), 0.95 * s, 2, PLATE, FRAME, up=-1)
    K.vls_grid(b, (x_fr - 64 * s, W * 0.35, Hat(x_fr - 64 * s) * 0.97), 4, 3, 3.3 * s, PLATE, FRAME)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=max(0.04, 0.12 * s), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def mandate_styx(name: str, length: float = 260.0, seed: int = 13):
    """Destroyer: a long spear of a bow (a third of the ship), swept armour sponsons at the stern, a low tower."""
    rng = random.Random(seed)
    L = length
    s = L / 260.0
    b = A.Builder()
    W, H = 20 * s, 17 * s
    skew = 0.12
    x_st, x_fr = -L / 2, L * 0.12
    wp = [(0.0, 0.9), (0.2, 1.0), (0.7, 0.95), (1.0, 0.7)]
    hp = [(0.0, 1.0), (0.6, 0.95), (1.0, 0.7)]
    zp = [(0.0, 0.0), (1.0, 0.05)]
    mandate_body(b, rng, (x_st, x_fr), wp, hp, zp, W, H, skew, s, cell=7.0)
    # the spear
    sp = []
    m = 12
    for i in range(m + 1):
        t = i / m
        x = x_fr - 6 * s + t * (L / 2 - x_fr + 6 * s)
        sp.append((x, K.blade(W * 0.7 * profile(t, [(0, 1.0), (0.5, 0.6), (1.0, 0.1)]), H * 0.7 * profile(t, [(0, 1.0), (0.7, 0.55), (1.0, 0.18)]),
                              skew), H * 0.05 + 4 * s * t))
    spear = K.Hull(b, sp, PLATE, cell=6.0 * s)
    spear.plate(rng, depth=(0.25 * s, 0.8 * s), recess=0.4 * s, margin=0.35 * s, skip=0.15, max_run=(2, 2), mats={LIVERY: 0.1})
    K.running_lights(b, [(L / 2 - 1 * s, 0, H * 0.05 + 5 * s)], 1.6 * s, LIGHTS)
    # swept sponsons at the stern (armour wings with the radiators)
    for side in (-1, 1):
        K.slab(b, x_st + 8 * s, x_st + 70 * s, K.chamfer_rect(4 * s, 6 * s, 0.35), K.chamfer_rect(2 * s, 3 * s, 0.35), PLATE,
               -2 * s, 0, side * (W + 10 * s), side * (W + 1 * s))
        K.fins(b, x_st + 14 * s, x_st + 56 * s, side * (W + 7 * s), 2 * s, 7 * s, 6, RADIATOR, thick=0.8 * s, rake=0.25)
        light_strips(b, x_st + 20 * s, x_fr - 20 * s, side * W * 0.99, 2 * s, 2, rng, s, lit=0.5)
    mandate_engines(b, x_st, W, H, s, 2, 0)
    keel(b, x_st + 30 * s, x_fr, 9 * s, H, s)
    tt = lambda x: (x - x_st) / (x_fr - x_st)  # noqa: E731
    flank_armour(b, rng, x_st + 76 * s, x_fr - 16 * s, lambda x: W * profile(tt(x), wp), lambda x: H * profile(tt(x), hp), s)
    mandate_tower(b, rng, x_st + 0.55 * (x_fr - x_st), W * 0.2, H * 0.95, s * 0.62, height=0.8)
    K.turret(b, (x_fr - 18 * s, 0, H * 0.72 + 1 * s), 0.72 * s, 2, PLATE, FRAME)
    K.turret(b, (x_st + 0.3 * (x_fr - x_st), 0, H * 0.95 + 1 * s), 0.72 * s, 2, PLATE, FRAME)
    K.turret(b, (x_st + 0.6 * (x_fr - x_st), 0, -H * 0.9), 0.6 * s, 2, PLATE, FRAME, up=-1)
    K.vls_grid(b, (x_fr - 40 * s, -W * 0.3, H * 0.9), 3, 2, 3.0 * s, PLATE, FRAME)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=max(0.04, 0.1 * s), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def mandate_lethe(name: str, length: float = 160.0, seed: int = 17):
    """Frigate: a compact armoured arrowhead, a single engine block, radiators on the back."""
    rng = random.Random(seed)
    L = length
    s = L / 160.0
    b = A.Builder()
    W, H = 22 * s, 11 * s
    x_st, x_fr = -L / 2, L / 2
    wp = [(0.0, 0.85), (0.25, 1.0), (0.55, 0.8), (0.85, 0.4), (1.0, 0.06)]
    hp = [(0.0, 1.0), (0.4, 1.0), (0.85, 0.6), (1.0, 0.2)]
    zp = [(0.0, 0.0), (1.0, 0.25)]
    mandate_body(b, rng, (x_st + 10 * s, x_fr), wp, hp, zp, W, H, 0.15, s, cell=5.5)
    mandate_engines(b, x_st + 10 * s, W * 0.7, H, s * 0.7, 2, 0)
    for side in (-1, 1):
        K.fins(b, x_st + 20 * s, x_st + 70 * s, side * W * 0.45, H * 0.95, 5 * s, 7, RADIATOR, thick=0.6 * s, rake=0.3)
        light_strips(b, x_st + 20 * s, x_fr - 50 * s, side * W * 0.97, 0, 1, rng, s, lit=0.6)
        K.running_lights(b, [(x_st + 30 * s, side * W * 1.02, 0)], 1.2 * s, LIGHTS)
    K.slab(b, x_st + 50 * s, x_st + 86 * s, K.chamfer_rect(6 * s, 3.5 * s, 0.35, top=0.7), K.chamfer_rect(3 * s, 2.5 * s, 0.35, top=0.6),
           PLATE, H * 0.95 + 3 * s, H * 1.0 + 3 * s, 0, 0)
    b.box((x_st + 86 * s, 0, H * 1.0 + 3.6 * s), (0.6 * s, 5 * s, 0.8 * s), LIGHTS)
    K.turret(b, (x_fr - 40 * s, 0, H * 0.75), 0.55 * s, 2, PLATE, FRAME)
    K.mast(b, x_st + 62 * s, 0, H * 0.95 + 6.5 * s, 9 * s, FRAME, LIGHTS)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=max(0.04, 0.08 * s), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


# ================================================================================================ ASTRA Navy
def astra_sec(w: float, h: float) -> list[tuple[float, float]]:
    """ASTRA's calm hull section: a wide deck, sloping flanks, a narrower keel."""
    return K.chamfer_rect(w, h, 0.3, top=0.9, bottom=0.72)


def astra_plating(h, rng, s):
    h.plate(rng, depth=(0.25 * s, 0.8 * s), recess=0.4 * s, margin=0.4 * s, skip=0.14, max_run=(3, 2), mats={FRAME: 0.12})


def astra_engines(b, x: float, W: float, H: float, s: float, cols: int, rows: int, r: float) -> None:
    K.slab(b, x - 16 * s, x + 12 * s, K.chamfer_rect(W * 0.8, H * 0.95, 0.3), K.chamfer_rect(W * 0.76, H * 0.9, 0.3), FRAME)
    K.engine_bank(b, x - 16 * s, 0, 0, r, cols, rows, r * 2.35, FRAME, ENGINE, GLOW)
    K.running_lights(b, [(x - 12 * s, sy * W * 0.82, H * 0.9) for sy in (-1, 1)], 1.6 * s, LIGHTS)


def radiator_wings(b, x0: float, x1: float, y: float, z: float, span: float, angle: float, n: int, s: float) -> None:
    """Folding radiator panels hinged on the flanks, half open."""
    from mathutils import Matrix
    a = math.radians(angle)
    step = (x1 - x0) / n
    for k in range(n):
        xa, xb = x0 + k * step + 1.5 * s, x0 + (k + 1) * step - 1.5 * s
        for side in (-1, 1):
            with K.part(b, Matrix.Translation(((xa + xb) / 2, side * y, z)) @ Matrix.Rotation(side * a, 4, "X")):
                b.box((0, side * span / 2, 0), (xb - xa, span, 0.5 * s), RADIATOR)
                for j in range(4):   # ribs
                    b.box((0, side * span * (0.15 + 0.23 * j), 0.35 * s), (xb - xa, 0.6 * s, 0.4 * s), FRAME)


def livery_band(b, x0: float, x1: float, y: float, z: float, h: float, rng: random.Random, s: float) -> None:
    x = x0
    while x < x1:
        ln = rng.uniform(40, 90) * s
        xm = min(x + ln, x1)
        b.box(((x + xm) / 2, y, z), (xm - x, 0.35 * s, h), LIVERY)
        x = xm + rng.uniform(3, 8) * s


def astra_ship2(name: str, length: float, seed: int, kind: str):
    """kind: carrier (Aquila: launch tubes at the bow, the island that carries the bridge), battleship
    (Praetorian: a citadel and six triple turrets), destroyer (Vigilant)."""
    rng = random.Random(seed)
    L = length
    b = A.Builder()
    if kind == "carrier":
        s, W, H = L / 780.0, 50.0, 24.0
    elif kind == "battleship":
        s, W, H = L / 920.0, 62.0, 30.0
    else:
        s, W, H = L / 280.0, 18.0, 10.0
    W, H = W * (L / 780.0 if kind == "carrier" else 1.0) if False else W, H
    x_st, x_bw = -L / 2 + 18 * s, L / 2
    # --- the lower hull
    wp = {"carrier": [(0.0, 0.9), (0.08, 1.0), (0.72, 1.0), (1.0, 0.62)],
          "battleship": [(0.0, 0.85), (0.1, 1.0), (0.66, 1.0), (0.9, 0.62), (1.0, 0.2)],
          "destroyer": [(0.0, 0.85), (0.12, 1.0), (0.6, 1.0), (0.88, 0.55), (1.0, 0.12)]}[kind]
    hp = {"carrier": [(0.0, 0.95), (0.1, 1.0), (0.75, 1.0), (1.0, 0.72)],
          "battleship": [(0.0, 0.9), (0.1, 1.0), (0.7, 1.0), (1.0, 0.45)],
          "destroyer": [(0.0, 0.9), (0.1, 1.0), (0.7, 0.95), (1.0, 0.35)]}[kind]
    n = max(10, int((x_bw - x_st) / (16 * s)))
    st = [(x_st + (i / n) * (x_bw - x_st), astra_sec(W * profile(i / n, wp), H * profile(i / n, hp)),
           -H * 0.15 * max(0.0, (i / n - 0.8) / 0.2)) for i in range(n + 1)]
    lower = K.Hull(b, st, PLATE, cell=(9.0 if kind != "destroyer" else 6.0) * s)
    astra_plating(lower, rng, s)
    tt = lambda x: (x - x_st) / (x_bw - x_st)  # noqa: E731
    Wat = lambda x: W * profile(min(1.0, max(0.0, tt(x))), wp)  # noqa: E731
    Hat = lambda x: H * profile(min(1.0, max(0.0, tt(x))), hp)  # noqa: E731
    # --- the upper deck (layered), and on it the spine
    up0, up1 = {"carrier": (-L * 0.42, L * 0.17), "battleship": (-L * 0.4, L * 0.26), "destroyer": (-L * 0.36, L * 0.2)}[kind]
    uw, uh = W * 0.6, (9.0 if kind != "destroyer" else 4.5) * s
    un = max(6, int((up1 - up0) / (16 * s)))
    ust = [(up0 + (i / un) * (up1 - up0), K.chamfer_rect(uw * profile(i / un, [(0, 0.85), (0.15, 1.0), (0.85, 1.0), (1.0, 0.7)]), uh, 0.35, top=0.8),
            H * 0.92 + uh - 1.0 * s) for i in range(un + 1)]
    upper = K.Hull(b, ust, PLATE, cell=8.0 * s)
    astra_plating(upper, rng, s)
    deck = H * 0.92 + 2 * uh - 1.0 * s        # top of the upper deck
    K.slab(b, up0 + 20 * s, up1 - 40 * s, K.chamfer_rect(uw * 0.32, 3.2 * s, 0.4), K.chamfer_rect(uw * 0.26, 2.6 * s, 0.4), FRAME,
           deck + 2.4 * s, deck + 2.0 * s)
    # --- the keel
    K.slab(b, x_st + 40 * s, up1, K.chamfer_rect(W * 0.45, 4 * s, 0.35), K.chamfer_rect(W * 0.3, 3 * s, 0.35), FRAME,
           -H * 0.95 - 2.5 * s, -H * 0.95 - 2.0 * s)
    # --- command: the carrier's island carries the bridge (BridgeOffset (172, 0, 62) m: the island's top stays
    #     just under the bridge floor, nothing rises in front of the bridge window)
    if kind == "carrier":
        top = 60.4 * s                     # just under the bridge's floor slab (bridge floor at 62 m)
        ib = Hat(170 * s) * 0.9            # the island rises from the hull's deck
        # the tower: wide at the base, tapering to the bridge's footprint (x 158..184, y +-11), the front raked
        # back steeply so the bow, the flight deck and its turrets stay in sight from the bridge window
        K.frustum(b, (112 * s, 212 * s, 19 * s), (152 * s, 184 * s, 11.5 * s), ib, top, PLATE, chamfer=0.18)
        K.frustum(b, (96 * s, 150 * s, 15 * s), (118 * s, 150 * s, 10 * s), ib, ib + 22 * s, FRAME, chamfer=0.2)
        for side in (-1, 1):
            for k in range(4):   # lit decks on the tower's flanks, stepping in as it rises
                zz = ib + (6 + 8 * k) * s
                f = (zz - ib) / (top - ib)
                hy = 19 * s + (11.5 * s - 19 * s) * f + 0.3 * s
                xa = 112 * s + (152 * s - 112 * s) * f + 4 * s
                xb = 212 * s + (184 * s - 212 * s) * f - 4 * s
                light_strips(b, xa, xb, side * hy, zz, 1, rng, s, lit=0.8)
        K.running_lights(b, [(182 * s, sy * 11 * s, top - 0.8 * s) for sy in (-1, 1)], 1.0 * s, LIGHTS)
        K.mast(b, 156 * s, 8 * s, top - 1.0 * s, 10 * s, FRAME, LIGHTS, dish=4 * s)
        # launch tubes: two lit mouths in the flat bow
        for sy in (-1, 1):
            K.hangar(b, x_bw, sy * W * 0.62 * 0.48, -H * 0.18, 26 * s, 13 * s, 22 * s, FRAME, LIGHTS)
    else:
        cx = up1 - 70 * s if kind == "battleship" else up1 - 26 * s
        cw = uw * 0.7
        ch = (14.0 if kind == "battleship" else 5.0) * s
        K.slab(b, cx - (70 if kind == "battleship" else 22) * s, cx + (26 if kind == "battleship" else 10) * s,
               K.chamfer_rect(cw, ch, 0.3, top=0.8), K.chamfer_rect(cw * 0.75, ch * 0.9, 0.3, top=0.75), PLATE, deck + ch, deck + ch * 0.95)
        b.box((cx + (26 if kind == "battleship" else 10) * s - 0.3 * s, 0, deck + ch * 1.6), (0.6 * s, cw * 1.3, 1.4 * s), LIGHTS)
        K.mast(b, cx - 10 * s, 0, deck + 2 * ch, (18 if kind == "battleship" else 8) * s, FRAME, LIGHTS, dish=(5 if kind == "battleship" else 2) * s)
    # --- turrets
    if kind == "carrier":
        mounts = [(232 * s, 0.0, Hat(232 * s), 1.0), (300 * s, 0.0, Hat(300 * s), 1.0), (-150 * s, 0.0, deck + 2.5 * s, 1.0), (-240 * s, 0.0, deck + 2.5 * s, 1.0)]
        for x, y, z, sc in mounts:
            K.turret(b, (x, y, z * 0.99), 1.6 * s * sc, 2, PLATE, FRAME)
        for x in (60 * s, -120 * s):
            K.turret(b, (x, 0, -H * 0.9), 1.2 * s, 2, PLATE, FRAME, up=-1)
    elif kind == "battleship":
        for k, x in enumerate((up1 + 50 * s, up1 + 120 * s, up1 + 185 * s)):
            K.turret(b, (x, 0.0, Hat(x) + (6 * s if k == 0 else 0)), 2.2 * s, 3, PLATE, FRAME)
        for x in (up0 + 60 * s, up0 + 140 * s, up0 + 220 * s):
            K.turret(b, (x, 0.0, deck + 2.5 * s), 2.0 * s, 3, PLATE, FRAME)
        for x in (0.0, -160 * s):
            for side in (-1, 1):
                K.turret(b, (x, side * W * 0.45, -H * 0.9), 1.3 * s, 2, PLATE, FRAME, up=-1)
    else:
        K.turret(b, (up1 + 34 * s, 0.0, Hat(up1 + 34 * s)), 0.9 * s, 2, PLATE, FRAME)
        K.turret(b, (up0 + 30 * s, 0.0, deck + 1.5 * s), 0.9 * s, 2, PLATE, FRAME)
    # --- VLS banks on the upper deck, flanking the spine
    for x in ((0.0, -70 * s) if kind == "carrier" else ((-40 * s, 40 * s) if kind == "battleship" else (-10 * s,))):
        for sy in (-1, 1):
            K.vls_grid(b, (x, sy * uw * 0.6, deck), 4, 3, 3.3 * s, PLATE, FRAME)
    # --- flanks: navy livery, lit decks, radiator wings, running lights
    for side in (-1, 1):
        livery_band(b, x_st + 30 * s, x_bw - 60 * s, side * (W * 1.0 + 0.3 * s), H * 0.1, 7 * s if kind != "destroyer" else 3.2 * s, rng, s)
        light_strips(b, x_st + 40 * s, x_bw - 70 * s, side * (W * 1.0 + 0.2 * s), -H * 0.45, 3 if kind != "destroyer" else 1, rng, s, lit=0.55)
    if kind != "destroyer":
        radiator_wings(b, x_st + 50 * s, up0 + (up1 - up0) * 0.55, W * 0.9, H * 0.72, W * 0.7, 22.0, 4, s)
    else:
        radiator_wings(b, x_st + 20 * s, 0.0, W * 0.9, H * 0.72, W * 0.8, 22.0, 2, s)
    K.running_lights(b, [(x_bw - 20 * s, sy * Wat(x_bw - 20 * s), 0) for sy in (-1, 1)], 1.6 * s, LIGHTS)
    # --- engines
    if kind == "carrier":
        astra_engines(b, x_st, W, H, s, 3, 2, 9.0 * s)
    elif kind == "battleship":
        astra_engines(b, x_st, W, H, s, 3, 2, 11.0 * s)
    else:
        astra_engines(b, x_st, W, H, s, 2, 1, 5.5 * s)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=max(0.04, 0.1 * s), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


# =================================================================================================== craft
def craft2(name: str, kind: str, seed: int, mandate: bool = False):
    """Small craft v2 (built to be seen up close on the flight deck): a lofted fuselage with a chine, a lit canopy
    frame, wings with hardpoints and wingtip lights, tail fins, engines with glowing throats, landing skids.
    kind: fighter (Falcon, Harpy) | bomber (Hammer) | drone (Wasp)."""
    rng = random.Random(seed)
    b = A.Builder()
    L = {"fighter": 18.0 if not mandate else 16.0, "bomber": 26.0, "drone": 8.0}[kind]
    w = L * (0.075 if kind == "fighter" else (0.1 if kind == "bomber" else 0.12))
    h = L * (0.06 if kind != "drone" else 0.1)
    sec = (lambda ww, hh: K.blade(ww, hh, 0.1)) if mandate else (lambda ww, hh: K.chamfer_rect(ww, hh, 0.38, top=0.8, bottom=0.7))
    wp = [(0.0, 0.62), (0.12, 0.95), (0.5, 1.0), (0.78, 0.7), (1.0, 0.1)]
    hp = [(0.0, 0.7), (0.15, 0.95), (0.5, 1.0), (0.8, 0.75), (1.0, 0.15)]
    st = [(-L / 2 + (i / 12) * L, sec(w * profile(i / 12, wp), h * profile(i / 12, hp)), h * 0.12 * max(0.0, i / 12 - 0.6)) for i in range(13)]
    fus = K.Hull(b, st, PLATE, cell=max(0.8, L / 16))
    fus.plate(rng, depth=(0.02, 0.06), recess=0.04, margin=0.05, skip=0.35, max_run=(2, 2), mats={FRAME: 0.18} if not mandate else {LIVERY: 0.15})
    if kind != "drone":
        # the canopy: a glazed lit block framed by the fuselage, raked back
        cx = L * (0.2 if kind == "fighter" else 0.25)
        K.slab(b, cx - L * 0.12, cx + L * 0.1, K.chamfer_rect(w * 0.55, h * 0.35, 0.45, top=0.6), K.chamfer_rect(w * 0.3, h * 0.2, 0.45, top=0.5),
               LIGHTS, h * 0.95, h * 0.85)
        K.slab(b, cx - L * 0.125, cx - L * 0.11, K.chamfer_rect(w * 0.6, h * 0.38, 0.4), K.chamfer_rect(w * 0.6, h * 0.38, 0.4), FRAME, h * 0.95, h * 0.95)
    # wings
    if kind == "drone":
        from mathutils import Matrix
        for ang in (90, 210, 330):
            a = math.radians(ang)
            with K.part(b, Matrix.Rotation(a - math.pi / 2, 4, "X")):
                K.slab(b, -L * 0.35, L * 0.05, K.chamfer_rect(w * 1.8, 0.08, 0.2), K.chamfer_rect(w * 0.6, 0.06, 0.2), FRAME, 0.0, 0.0, w * 1.6, w * 1.1)
        b.cylinder((L * 0.5, 0, 0), (L * 0.56, 0, 0), w * 0.45, LIGHTS, segments=16)   # the sensor eye
    else:
        span = L * (0.72 if kind == "fighter" else 0.88) * (1.1 if mandate else 1.0)
        root_c, tip_c = L * (0.42 if kind == "fighter" else 0.36), L * (0.14 if kind == "fighter" else 0.2)
        sweep = L * (0.18 if kind == "fighter" else 0.06) * (-1.0 if mandate else 1.0)
        for side in (-1, 1):
            y0, y1 = side * w * 0.9, side * span / 2
            bm = b.bm
            z = -h * 0.25
            verts = [bm.verts.new(v) for v in (
                (-L * 0.28, y0, z - 0.12), (-L * 0.28 + root_c, y0, z - 0.12), (-L * 0.28 + sweep + root_c * 0.5 + tip_c * 0.5, y1, z + (0.3 if not mandate else -0.2)),
                (-L * 0.28 + sweep + root_c * 0.5 - tip_c * 0.5, y1, z + (0.3 if not mandate else -0.2)),
                (-L * 0.28, y0, z + 0.12), (-L * 0.28 + root_c, y0, z + 0.12), (-L * 0.28 + sweep + root_c * 0.5 + tip_c * 0.5, y1, z + (0.36 if not mandate else -0.14)),
                (-L * 0.28 + sweep + root_c * 0.5 - tip_c * 0.5, y1, z + (0.36 if not mandate else -0.14)))]
            import bmesh as _bm
            idx = b.mi(PLATE)
            faces = [bm.faces.new((verts[a], verts[bb], verts[c], verts[d])) for a, bb, c, d in
                     ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))]
            for f in faces:
                f.material_index = idx
            _bm.ops.recalc_face_normals(bm, faces=faces)
            tipx = -L * 0.28 + sweep + root_c * 0.5
            K.running_lights(b, [(tipx, y1, z + 0.3)], max(0.2, L * 0.012), LIGHTS)
            b.box((tipx - tip_c * 0.1, y1 - side * L * 0.04, z + 0.25), (tip_c * 0.8, L * 0.035, 0.1), LIVERY)   # wingtip livery
            # hardpoints: missiles (fighters) or torpedoes (bombers) under the wings
            for k in range(2 if kind == "fighter" else 1):
                yy = side * (w * 1.6 + (span / 2 - w) * (0.35 + 0.3 * k))
                r = L * (0.012 if kind == "fighter" else 0.035)
                b.cylinder((-L * 0.18, yy, z - 0.45 - r), (L * 0.05 + (L * 0.12 if kind == "bomber" else 0), yy, z - 0.45 - r), r, FRAME, segments=10)
        # tail fins: twin, canted outwards (the Harpy has a single blade)
        for side in ((-1, 1) if not mandate else (0,)):
            yb = side * w * 0.55
            K.slab(b, -L * 0.48, -L * 0.3, K.chamfer_rect(0.1, h * 0.9, 0.2), K.chamfer_rect(0.08, h * 0.35, 0.2), PLATE,
                   h * 1.3, h * 1.55, yb + side * 0.2, yb + side * 0.5)
    # engines
    ne = 1 if kind == "drone" else 2
    for i in range(ne):
        yy = 0.0 if ne == 1 else (i - 0.5) * w * 1.15
        r = L * (0.04 if kind == "fighter" else (0.05 if kind == "bomber" else 0.06))
        b.cylinder((-L * 0.44, yy, 0), (-L * 0.53, yy, 0), r * 1.15, FRAME, segments=16)
        b.cylinder((-L * 0.53, yy, 0), (-L * 0.56, yy, 0), r * 0.85, ENGINE, segments=16, radius2=r * 1.05)
        b.cylinder((-L * 0.535, yy, 0), (-L * 0.545, yy, 0), r * 0.9, GLOW, segments=16)
    # landing skids (parked on the deck they touch it)
    if kind != "drone":
        for x, yy in ((L * 0.28, 0.0), (-L * 0.15, w * 1.1), (-L * 0.15, -w * 1.1)):
            b.cylinder((x, yy, -h * 0.9), (x, yy, -h * 1.35), max(0.08, L * 0.006), FRAME, segments=8)
            b.box((x, yy, -h * 1.38), (L * 0.05, L * 0.012, 0.06), FRAME)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=max(0.01, L * 0.001), segments=1)
    A.box_uv(obj, texel_m=2.0)
    return obj


# ================================================================================================= stations
def listening_post(name: str, seed: int = 31):
    """Thule Watch class listening post (ASTRA): a long truss spine, a cluster of habitat and operations modules, three
    great dishes, arrays of antennas, radiator and solar wings. Built to be seen dark and drifting as well as alive."""
    rng = random.Random(seed)
    b = A.Builder()
    s = 1.0
    # the spine: a square truss 220 m long (four longerons and cross members)
    L = 220.0
    for sy in (-1, 1):
        for sz in (-1, 1):
            b.cylinder((-L / 2, sy * 4, sz * 4), (L / 2, sy * 4, sz * 4), 0.7, FRAME, segments=8)
    for k in range(23):
        x = -L / 2 + k * L / 22
        for (y0, z0, y1, z1) in ((-4, -4, 4, -4), (-4, 4, 4, 4), (-4, -4, -4, 4), (4, -4, 4, 4), (-4, -4, 4, 4)):
            b.cylinder((x, y0, z0), (x + (L / 22 if (y0, z0, y1, z1) == (-4, -4, 4, 4) else 0.01), y1, z1), 0.35, FRAME, segments=6)
    # the operations core: stacked modules around the middle of the spine
    core = K.Hull(b, [(x, K.chamfer_rect(w, h, 0.35), 0.0) for x, w, h in
                      ((-34, 10, 10), (-30, 16, 15), (-10, 18, 17), (10, 18, 17), (30, 16, 15), (34, 10, 10))], PLATE, cell=5.0)
    core.plate(rng, depth=(0.2, 0.6), recess=0.3, margin=0.3, skip=0.15, max_run=(2, 2), mats={FRAME: 0.15, LIVERY: 0.05})
    for k, (x, r) in enumerate(((-60, 9), (55, 8), (-85, 6.5), (80, 6))):   # habitat drums along the spine
        b.cylinder((x - 12, 0, 0), (x + 12, 0, 0), r, PLATE, segments=20)
        for j in range(3):
            b.cylinder((x - 12 + j * 11, 0, 0), (x - 11 + j * 11, 0, 0), r + 0.5, FRAME, segments=20)
    # three great dishes looking up and out, on pylons
    for k, (x, y, z, r, tilt) in enumerate(((-20, 0, 26, 22, 0), (70, 16, 14, 14, 35), (-100, -14, 12, 12, -30))):
        from mathutils import Matrix
        with K.part(b, Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.radians(tilt), 4, "X")):
            b.cylinder((0, 0, -z + 5), (0, 0, 0), 1.6, FRAME, segments=10)
            b.cylinder((0, 0, 0), (0, 0, r * 0.28), r * 0.12, FRAME, segments=24, radius2=r)     # the bowl
            b.cylinder((0, 0, r * 0.28), (0, 0, r * 0.3), r, PLATE, segments=32)
            b.cylinder((0, 0, 0), (0, 0, r * 0.75), 0.4, FRAME, segments=6)                     # the feed
            b.box((0, 0, r * 0.78), (2.4, 2.4, 2.4), FRAME)
    # antenna arrays and masts
    for k in range(9):
        x = -L / 2 + 20 + k * 22
        K.mast(b, x, rng.choice((-1, 1)) * 4, rng.choice((-1, 1)) * 4, rng.uniform(10, 28), FRAME, LIGHTS)
    # solar and radiator wings on both flanks
    for side in (-1, 1):
        for k in range(3):
            x = -95 + k * 40
            b.box((x, side * 34, 0), (30, 52, 0.4), RADIATOR if k == 1 else LIVERY)
            b.cylinder((x, side * 5, 0), (x, side * 8, 0), 0.8, FRAME, segments=8)
    K.running_lights(b, [(L / 2, 0, 5), (-L / 2, 0, 5), (0, 0, 20)], 1.2, LIGHTS)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=0.05, segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


# =================================================================================================== Free Guilds
def guild_freighter(name: str, length: float = 340.0, seed: int = 5):
    """Free Guilds bulk freighter: a blunt crew section at the bow (a raised bridge with a lit visor, habitat decks,
    a docking collar), a square truss spine carrying bays of cargo pods in the Guilds' mismatched colours (some bays
    half empty so the truss shows, some carrying bulk tanks), a drive section with radiator wings and fins, four big
    bells. Built to read at 20 km as a long working ship, and up close as a lived-in one."""
    rng = random.Random(seed)
    b = A.Builder()
    s = length / 340.0
    x_bow, x_st = length / 2, -length / 2
    # --- the crew section
    cx0, cx1 = x_bow - 64 * s, x_bow
    st = [(cx0 + t * (cx1 - cx0), K.chamfer_rect(w * s, h * s, 0.3, top=0.85, bottom=0.8), z * s)
          for t, w, h, z in ((0.0, 9, 8, 0), (0.12, 13, 11, 0), (0.55, 13, 12, 1), (0.82, 11, 10, 1.5), (1.0, 6, 5, 1.0))]
    crew = K.Hull(b, st, PLATE, cell=4.0 * s)
    crew.plate(rng, depth=(0.15 * s, 0.5 * s), recess=0.3 * s, margin=0.25 * s, skip=0.2, max_run=(2, 2), mats={LIVERY: 0.16, FRAME: 0.1})
    bx = x_bow - 20 * s                      # the bridge: a raised block with a wide lit visor
    K.slab(b, bx - 16 * s, bx + 5 * s, K.chamfer_rect(8 * s, 3.2 * s, 0.35, top=0.7), K.chamfer_rect(6.5 * s, 2.4 * s, 0.35, top=0.55),
           PLATE, 14.0 * s, 14.6 * s)
    b.box((bx + 5 * s + 0.15 * s, 0, 15.2 * s), (0.4 * s, 9.5 * s, 1.1 * s), LIGHTS)
    for side in (-1, 1):
        K.window_band(b, cx0 + 8 * s, x_bow - 14 * s, side * 13.6 * s, -5 * s, 3, rng, LIGHTS, pitch=2.6 * s, lit=0.6)
        livery_band(b, cx0 + 6 * s, x_bow - 12 * s, side * 13.55 * s, 4.5 * s, 2.2 * s, rng, s)
    K.mast(b, bx - 20 * s, 0, 13.5 * s, 14 * s, FRAME, LIGHTS, dish=5 * s)
    K.mast(b, bx - 8 * s, 5 * s, 17.6 * s, 6 * s, FRAME, LIGHTS)
    b.cylinder((x_bow, 0, 1 * s), (x_bow + 2.5 * s, 0, 1 * s), 3.4 * s, FRAME, segments=16)      # docking collar
    b.cylinder((x_bow + 2.5 * s, 0, 1 * s), (x_bow + 2.8 * s, 0, 1 * s), 2.6 * s, LIGHTS, segments=16)
    b.cylinder((cx0 - 8 * s, 0, 0), (cx0 + 1 * s, 0, 0), 6.0 * s, FRAME, segments=12)              # the neck
    # --- the spine: a square truss with flank bracing
    xs0, xs1 = x_st + 64 * s, cx0 - 6 * s
    t = 3.6 * s
    for sy in (-1, 1):
        for sz in (-1, 1):
            b.cylinder((xs0, sy * t, sz * t), (xs1, sy * t, sz * t), 0.6 * s, FRAME, segments=8)
    n = max(4, int((xs1 - xs0) / (9 * s)))
    for k in range(n + 1):
        x = xs0 + k * (xs1 - xs0) / n
        for (y0, z0, y1, z1) in ((-t, -t, t, -t), (-t, t, t, t), (-t, -t, -t, t), (t, -t, t, t)):
            b.cylinder((x, y0, z0), (x, y1, z1), 0.35 * s, FRAME, segments=6)
        if k < n:
            x2 = xs0 + (k + 1) * (xs1 - xs0) / n
            za, zb = (-t, t) if k % 2 == 0 else (t, -t)
            for sy in (-1, 1):
                b.cylinder((x, sy * t, za), (x2, sy * t, zb), 0.28 * s, FRAME, segments=6)
    # --- the cargo: bays of pods (20 x 9 x 9 m) clamped around the spine, bulk tanks, a few empty cradles
    colours = [(PLATE, 0.34), (LIVERY, 0.28), (ENGINE, 0.2), (FRAME, 0.1), (RADIATOR, 0.08)]

    def pick():
        r, acc = rng.random(), 0.0
        for m, p in colours:
            acc += p
            if r < acc:
                return m
        return PLATE

    pitch = 23.0 * s
    bays = int((xs1 - xs0 - 4 * s) / pitch)
    x_first = xs0 + (xs1 - xs0 - bays * pitch) / 2 + pitch / 2
    kinds = ["pods"] * bays
    for k in rng.sample(range(bays), 2):
        kinds[k] = "tanks"
    kinds[rng.choice([k for k in range(bays) if kinds[k] == "pods"])] = "cradle"
    off = t + 4.5 * s + 0.5 * s
    for k in range(bays):
        x = x_first + k * pitch
        if kinds[k] == "tanks":
            for (ty, tz) in ((11.6, 0), (-11.6, 0), (0, 11.6), (0, -11.6)):
                y, z, r = ty * s, tz * s, 7.2 * s
                b.cylinder((x - 8.5 * s, y, z), (x + 8.5 * s, y, z), r, PLATE if rng.random() < 0.6 else ENGINE, segments=24)
                for sx in (-1, 1):
                    b.cylinder((x + sx * 8.5 * s, y, z), (x + sx * 10.2 * s, y, z), r, PLATE, segments=24, radius2=r * 0.55)
                for dx in (-6.0, 0.0, 6.0):
                    b.cylinder((x + (dx - 0.4) * s, y, z), (x + (dx + 0.4) * s, y, z), r + 0.3 * s, FRAME, segments=24)
                b.box((x, y * 0.42, z * 0.42), (3 * s, 2.4 * s + abs(y) * 0.2, 2.4 * s + abs(z) * 0.2), FRAME)
            continue
        slots = [(sy * off, sz * off, 0.85) for sy in (-1, 1) for sz in (-1, 1)]
        slots += [(sy * (off + 9.4 * s), sz * off, 0.55) for sy in (-1, 1) for sz in (-1, 1)]
        for (y, z, p) in slots:
            outer = abs(y) > off + 1
            if kinds[k] == "cradle" and rng.random() < 0.75:
                # an empty cradle: the clamps and the rails without their pod
                b.box((x, y, z - math.copysign(4.6 * s, z)), (20 * s, 0.5 * s, 0.5 * s), FRAME)
                continue
            if rng.random() > p:
                continue
            m = pick()
            K.block(b, (x, y, z), (20 * s, 9 * s, 9 * s), m, c=0.07)
            for sx in (-1, 1):
                b.box((x + sx * 9.75 * s, y, z), (0.6 * s, 9.4 * s, 9.4 * s), FRAME)
            for dx in (-3.4, 3.4):
                b.box((x + dx * s, y, z), (0.35 * s, 9.15 * s, 9.15 * s), FRAME)
            if not outer:
                for sx in (-1, 1):   # clamps to the spine's corner
                    b.box((x + sx * 6.5 * s, math.copysign(t + 0.25 * s, y), math.copysign(t + 0.25 * s, z)), (2.4 * s, 1.4 * s, 1.4 * s), FRAME)
            if rng.random() < 0.18:
                K.running_lights(b, [(x + 10.1 * s, y + math.copysign(4.4 * s, y), z + math.copysign(4.4 * s, z))], 0.5 * s, LIGHTS)
    # --- the drive section: reactor and tanks, radiators, the thrust frame and four big bells
    dx0, dx1 = x_st + 8 * s, xs0 + 6 * s
    st = [(dx0 + t_ * (dx1 - dx0), K.chamfer_rect(w * s, h * s, 0.3), 0.0)
          for t_, w, h in ((0.0, 16, 14), (0.15, 17, 15), (0.7, 16, 14), (1.0, 10, 9))]
    drive = K.Hull(b, st, PLATE, cell=5.0 * s)
    drive.plate(rng, depth=(0.2 * s, 0.6 * s), recess=0.3 * s, margin=0.3 * s, skip=0.15, max_run=(2, 2), mats={LIVERY: 0.25, FRAME: 0.15})
    for side in (-1, 1):
        b.cylinder((dx0 + 12 * s, side * 8 * s, 15.5 * s), (dx1 - 12 * s, side * 8 * s, 15.5 * s), 3.2 * s, ENGINE, segments=16)   # tanks
        b.cylinder((dx0 + 12 * s, side * 8 * s, -15.5 * s), (dx1 - 12 * s, side * 8 * s, -15.5 * s), 3.2 * s, ENGINE, segments=16)
        livery_band(b, dx0 + 4 * s, dx1 - 6 * s, side * 17.5 * s, 7 * s, 2.4 * s, rng, s)
        K.window_band(b, dx0 + 10 * s, dx1 - 10 * s, side * 17.6 * s, -9 * s, 1, rng, LIGHTS, pitch=2.6 * s, lit=0.5)
    radiator_wings(b, dx0 + 10 * s, dx1 - 8 * s, 17.0 * s, 0.0, 20 * s, 12.0, 2, s)
    K.fins(b, dx0 + 6 * s, dx1 - 12 * s, 0.0, 15.2 * s, 9 * s, 8, RADIATOR, thick=0.45 * s)
    for k in range(8):
        x = dx0 + 6 * s + k * (dx1 - 18 * s - dx0) / 7
        b.box((x, 0.0, -15.2 * s - 4.5 * s), (0.45 * s, 5.4 * s, 9 * s), RADIATOR)
    K.slab(b, x_st + 2 * s, dx0 + 1 * s, K.chamfer_rect(15 * s, 15 * s, 0.3), K.chamfer_rect(16 * s, 14 * s, 0.3), FRAME)
    K.engine_bank(b, x_st + 2 * s, 0, 0, 5.4 * s, 2, 2, 13 * s, FRAME, ENGINE, GLOW)
    K.running_lights(b, [(x_bow - 4 * s, sy * 7.5 * s, 4 * s) for sy in (-1, 1)] +
                     [(dx0 + 3 * s, sy * 17.2 * s, 11 * s) for sy in (-1, 1)] + [(x_st + 4 * s, 0, 15.3 * s)], 1.1 * s, LIGHTS)
    obj = b.to_object(name)
    if os.environ.get("NOBEVEL") != "1":
        A.finish(obj, bevel=0.06, segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


SHIPS = {
    "SM_CRAFT_ASTRA_Falcon": (craft2, dict(kind="fighter", seed=21)),
    "SM_CRAFT_ASTRA_Hammer": (craft2, dict(kind="bomber", seed=23)),
    "SM_CRAFT_ASTRA_Wasp": (craft2, dict(kind="drone", seed=25)),
    "SM_CRAFT_MANDATE_Harpy": (craft2, dict(kind="fighter", seed=27, mandate=True)),
    "SM_STATION_ASTRA_Watch": (listening_post, dict(seed=31)),
    "SM_SHIP_ASTRA_Aquila": (astra_ship2, dict(length=780.0, seed=1, kind="carrier")),
    "SM_SHIP_ASTRA_Praetorian": (astra_ship2, dict(length=920.0, seed=7, kind="battleship")),
    "SM_SHIP_ASTRA_Vigilant": (astra_ship2, dict(length=280.0, seed=3, kind="destroyer")),
    "SM_SHIP_MANDATE_Acheron": (mandate_acheron, dict(length=460.0, seed=11)),
    "SM_SHIP_MANDATE_Styx": (mandate_styx, dict(length=260.0, seed=13)),
    "SM_SHIP_MANDATE_Lethe": (mandate_lethe, dict(length=160.0, seed=17)),
    "SM_SHIP_GUILD_Freighter": (guild_freighter, dict(length=340.0, seed=5)),
}

PREVIEW = {  # faction colours for the workbench previews
    "M": {"Plate": (0.2, 0.19, 0.18), "Frame": (0.07, 0.07, 0.08), "Livery": (0.45, 0.26, 0.12), "Engine": (0.25, 0.25, 0.27),
          "Glow": (1.0, 0.45, 0.25), "Lights": (1.0, 0.7, 0.3), "Radiator": (0.9, 0.35, 0.1)},
    "G": {"Plate": (0.48, 0.42, 0.3), "Frame": (0.06, 0.06, 0.07), "Livery": (0.48, 0.13, 0.01), "Engine": (0.35, 0.35, 0.37),
          "Glow": (0.9, 0.9, 1.0), "Lights": (1.0, 0.95, 0.85), "Radiator": (0.05, 0.05, 0.06)},
    "A": {"Plate": (0.8, 0.78, 0.72), "Frame": (0.25, 0.27, 0.3), "Livery": (0.1, 0.2, 0.45), "Engine": (0.3, 0.3, 0.32),
          "Glow": (0.55, 0.8, 1.0), "Lights": (1.0, 0.9, 0.7), "Radiator": (0.18, 0.19, 0.2)},
}


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/ships"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    only = argv[argv.index("--only") + 1].split(",") if "--only" in argv else None
    A.reset_scene()
    report = []
    for name, (fn, kw) in SHIPS.items():
        if only and name not in only:
            continue
        A.clear_objects()
        obj = fn(name, **kw)
        fac = {"ASTRA": "A", "MANDATE": "M", "GUILD": "G"}[name.split("_")[2]]
        for m in obj.data.materials:
            if m and m.name.startswith("MI_HULL_") and m.name.count("_") == 2:
                obj.data.materials[obj.data.materials.find(m.name)] = A.material(m.name.replace("MI_HULL_", f"MI_HULL_{fac}_"))
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
        if preview:
            os.makedirs(preview, exist_ok=True)
            pal = PREVIEW.get(fac, PREVIEW["A"])
            for m in obj.data.materials:
                part = m.name.split("_")[-1]
                if part in pal:
                    m.diffuse_color = (*pal[part], 1)
            for tag, view in (("a", (150.0, 18.0)), ("b", (35.0, 12.0)), ("c", (90.0, 4.0))):
                render(obj, os.path.join(preview, f"{name}_{tag}.png"), view)
    with open(os.path.join(out_dir, "report_v2.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("SHIPS_V2_OK", json.dumps(report))


def render(obj, path: str, view) -> None:
    """Workbench preview that keeps the faction colours (astra_bpy's own preview repaints the materials)."""
    from mathutils import Vector
    scene = bpy.context.scene
    mins = Vector([min((obj.matrix_world @ Vector(c))[i] for c in obj.bound_box) for i in range(3)])
    maxs = Vector([max((obj.matrix_world @ Vector(c))[i] for c in obj.bound_box) for i in range(3)])
    center, radius = (mins + maxs) / 2, (maxs - mins).length / 2
    az, el = math.radians(view[0]), math.radians(view[1])
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50
    cam_data.clip_end = 20000
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + d * radius * 3.0
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = True
    sh.cavity_type = "BOTH"
    sh.show_shadows = True
    sh.shadow_intensity = 0.6
    scene.render.resolution_x = 1400
    scene.render.resolution_y = 700
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)


if __name__ == "__main__":
    main()
