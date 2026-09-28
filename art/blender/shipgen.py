"""ASTRA procedural starship generator (v1): faction style + class + seed -> capital ship mesh.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen.py -- <out_dir> [--preview <png_dir>] [--only name,...]

Design language (docs/STILE.md §2):
- ASTRA Navy: long horizontal layered hulls with a dorsal spine, sharp but calm bow, ivory ceramic plates over a
  gunmetal frame, folding radiator panels on the flanks, navy-blue livery band, white/blue nav lights.
- Kharon Mandate: angular brutal armour slabs, asymmetric, forward-raked blade bows, basalt/graphite with oxidised
  copper, exposed radiators glowing orange, amber/red lights, patched survivors.
Ships are built along +X (bow at +X), metres; the pivot is the hull centre. Material slots (Unreal instances):
  MI_HULL_Plate (faction ceramic/armour plates), MI_HULL_Frame (structure), MI_HULL_Livery (band), MI_HULL_Engine
  (nozzles), MI_HULL_Glow (engine exhaust, emissive), MI_HULL_Lights (windows/nav lights, emissive),
  MI_HULL_Radiator (radiator panels; Mandate ones glow).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

PARTS = ("Plate", "Frame", "Livery", "Engine", "Glow", "Lights", "Radiator")
PLATE, FRAME, LIVERY, ENGINE, GLOW, LIGHTS, RADIATOR = (f"MI_HULL_{p}" for p in PARTS)


def faction_slots(obj, faction: str) -> None:
    """Rename the generic slots to the faction's (MI_HULL_A_Plate, MI_HULL_M_Plate, ...): each fleet has its livery."""
    for m in obj.data.materials:
        if m and m.name.startswith("MI_HULL_") and m.name.count("_") == 2:
            new = m.name.replace("MI_HULL_", f"MI_HULL_{faction}_")
            obj.data.materials[obj.data.materials.find(m.name)] = A.material(new)


# ------------------------------------------------------------------ lofting
def section_astra(w: float, h: float) -> list[tuple[float, float]]:
    """Octagonal section with a flat keel and a raised deck line (y, z), counter-clockwise."""
    return [(-0.55 * w, -h), (0.55 * w, -h), (w, -0.35 * h), (w, 0.3 * h), (0.6 * w, h), (-0.6 * w, h),
            (-w, 0.3 * h), (-w, -0.35 * h)]


def section_mandate(w: float, h: float, skew: float) -> list[tuple[float, float]]:
    """Faceted armour section, slightly asymmetric (skew shifts the upper ridge to one side)."""
    return [(-0.35 * w, -h), (0.4 * w, -h), (w, -0.2 * h), (0.75 * w + skew * w, 0.55 * h), (0.1 * w + skew * w, h),
            (-0.55 * w + skew * w, 0.7 * h), (-w, -0.05 * h)]


def loft(b: A.Builder, stations, mat: str) -> None:
    """stations: list of (x, section[(y,z)...], z_offset). All sections must have the same vertex count."""
    bm = b.bm
    rings = []
    for x, sec, zo in stations:
        rings.append([bm.verts.new((x, y, z + zo)) for y, z in sec])
    idx = b.mi(mat)
    faces = []
    n = len(rings[0])
    for r0, r1 in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            faces.append(bm.faces.new((r0[i], r0[j], r1[j], r1[i])))
    faces.append(bm.faces.new(list(reversed(rings[0]))))
    faces.append(bm.faces.new(rings[-1]))
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def profile(t: float, pts: list[tuple[float, float]]) -> float:
    """Piecewise-linear profile through (t, value) points, t in [0, 1] from stern to bow."""
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


# ------------------------------------------------------------------ parts
def turret(b: A.Builder, pos, scale: float, top: bool = True, mat_plate=PLATE) -> None:
    x, y, z = pos
    s = 1 if top else -1
    b.cylinder((x, y, z), (x, y, z + s * 1.2 * scale), 2.4 * scale, FRAME, segments=16)
    b.box((x - 0.4 * scale, y, z + s * 2.2 * scale), (5.0 * scale, 3.6 * scale, 2.0 * scale), mat_plate)
    for dy in (-0.8, 0.8):
        b.cylinder((x + 1.8 * scale, y + dy * scale, z + s * 2.3 * scale), (x + 9.5 * scale, y + dy * scale, z + s * 2.3 * scale),
                   0.33 * scale, FRAME, segments=10)


def engine_cluster(b: A.Builder, x: float, y: float, z: float, r: float, glow_len: float = 0.0) -> None:
    b.cylinder((x, y, z), (x - 1.6 * r, y, z), r * 1.08, FRAME, segments=24)            # housing
    b.cylinder((x - 1.6 * r, y, z), (x - 2.6 * r, y, z), r * 0.8, ENGINE, segments=24, radius2=r * 1.05)  # bell
    b.cylinder((x - 2.3 * r, y, z), (x - 2.55 * r, y, z), r * 0.85, GLOW, segments=24)   # hot throat disc


def radiator_panel(b: A.Builder, x0: float, x1: float, y: float, z: float, span: float, side: int, angle_deg: float,
                   mat=RADIATOR) -> None:
    """A thin radiator wing hinged on the hull flank, opened by angle_deg."""
    a = math.radians(angle_deg)
    cy = y + side * math.cos(a) * span / 2
    cz = z + math.sin(a) * span / 2
    m = (Matrix.Translation(((x0 + x1) / 2, cy, cz)) @ Matrix.Rotation(side * a, 4, "X")
         @ Matrix.Diagonal((x1 - x0, span, 0.35, 1.0)))
    geom = bmesh.ops.create_cube(b.bm, size=1.0, matrix=m)
    b._assign(geom["verts"], mat)


def window_rows(b: A.Builder, x0: float, x1: float, y: float, z: float, rows: int, rng: random.Random, side: int) -> None:
    """Rows of small lit windows on a flank (emissive), with gaps."""
    for r in range(rows):
        zz = z + r * 2.2
        x = x0
        while x < x1:
            run = rng.uniform(6, 24)
            if rng.random() < 0.7:
                b.box((min(x + run / 2, x1), y, zz), (min(run, x1 - x), 0.25, 0.6), LIGHTS)
            x += run + rng.uniform(3, 10)


def greebles(b: A.Builder, x0: float, x1: float, y0: float, y1: float, z: float, n: int, rng: random.Random,
             up: bool = True, scale: float = 1.0) -> None:
    s = 1 if up else -1
    for _ in range(n):
        sx, sy, sz = rng.uniform(3, 14) * scale, rng.uniform(2, 8) * scale, rng.uniform(0.5, 2.5) * scale
        b.box((rng.uniform(x0, x1), rng.uniform(y0, y1), z + s * sz / 2), (sx, sy, sz), rng.choice([FRAME, PLATE, PLATE]))


# ------------------------------------------------------------------ factions
def astra_ship(name: str, length: float, seed: int, carrier: bool = False, beam: float = 0.13, turrets: int = 4):
    rng = random.Random(seed)
    L = length
    W = L * beam / 2            # half width
    Hh = L * 0.055              # half height
    b = A.Builder()
    # main hull: stern block, long body, tapering calm bow
    wprof = [(0.0, 0.78), (0.08, 0.92), (0.2, 1.0), (0.62, 1.0), (0.82, 0.8), (0.95, 0.42), (1.0, 0.16)]
    hprof = [(0.0, 0.9), (0.1, 1.0), (0.65, 1.0), (0.85, 0.78), (1.0, 0.3)]
    zprof = [(0.0, 0.0), (0.7, 0.0), (1.0, -0.25)]
    st = []
    for i in range(29):
        t = i / 28
        st.append((-L / 2 + t * L, section_astra(W * profile(t, wprof), Hh * profile(t, hprof)), Hh * profile(t, zprof)))
    loft(b, st, PLATE)
    # dorsal spine (layered: narrower raised ridge over the middle two thirds). On the carrier it stops just aft of
    # the bridge, which sits on its own pedestal at the front of the spine (see docs: data/ship/aquila_bridge.json,
    # BridgeOffset = (172, 0, 62) m in the hull frame): nothing may rise into the bridge or in front of its window.
    sp = []
    t_end = 0.70 if carrier else 0.74
    for i in range(13):
        t = 0.12 + (t_end - 0.12) * i / 12
        taper = 1.0 - 0.6 * max(0.0, (t - 0.55) / 0.19)
        sp.append((-L / 2 + t * L, section_astra(W * 0.42 * taper, Hh * 0.55), Hh * 1.05))
    loft(b, sp, FRAME)
    # keel (lower layer)
    kl = []
    for i in range(9):
        t = 0.1 + 0.55 * i / 8
        kl.append((-L / 2 + t * L, section_astra(W * 0.55, Hh * 0.35), -Hh * 1.15))
    loft(b, kl, FRAME)
    # livery band along the flank + gold pinstripe
    for side in (1, -1):
        b.box((0.05 * L, side * W * 1.005, Hh * 0.05), (L * 0.62, 0.3, Hh * 0.28), LIVERY)
        b.box((0.05 * L, side * W * 1.012, Hh * 0.2), (L * 0.62, 0.2, Hh * 0.03), RADIATOR if False else LIGHTS)
    # command section: a low, wide brow at the front of the spine with the panoramic bridge window facing forward
    # (no tall tower: spaceships do not need a mast)
    bx = 0.22 * L
    if carrier:
        # the bridge's pedestal: from the hull up to just under the bridge floor (1.45 Hh), tapering forward
        top = Hh * 1.45 - 1.6   # below the bridge well slab (bridge floor 62 m, well -0.6 m, slab -0.9 m)
        brow = []
        for i in range(7):
            t = i / 6
            half = (top - Hh * 0.85) / 2
            brow.append((bx - L * 0.03 + t * L * 0.045, section_astra(W * 0.42 * (1.0 - 0.35 * t), half * (1.0 - 0.3 * t)),
                         top - half * (1.0 - 0.3 * t)))
        loft(b, brow, PLATE)
    else:
        brow = []
        for i in range(7):
            t = i / 6
            taper = 1.0 - 0.55 * t
            brow.append((bx - L * 0.07 + t * L * 0.1, section_astra(W * 0.5 * taper, Hh * 0.38 * (1.0 - 0.4 * t)), Hh * 1.45))
        loft(b, brow, PLATE)
        b.box((bx + L * 0.028, 0.0, Hh * 1.45), (L * 0.006, W * 0.42, Hh * 0.22), LIGHTS)   # bridge window band
    for k in range(3):   # sensor masts, short
        b.cylinder((bx - L * 0.05 + k * 5, (k - 1) * W * 0.18, Hh * 1.8), (bx - L * 0.05 + k * 5, (k - 1) * W * 0.18, Hh * (2.1 + 0.1 * k)),
                   0.3 + 0.05 * k, FRAME, segments=6)
    # turrets on the spine and keel
    for k in range(turrets):
        tx = -L / 2 + L * (0.32 + 0.1 * k)
        turret(b, (tx, 0.0, Hh * 1.6), L / 520)
        if k % 2 == 0:
            turret(b, (tx + L * 0.05, 0.0, -Hh * 1.5), L / 620, top=False)
    # carrier: flight deck openings on both flanks (dark recesses with lit edges)
    if carrier:
        for side in (1, -1):
            b.box((-0.02 * L, side * W * 0.98, -Hh * 0.35), (L * 0.22, 0.6, Hh * 0.6), FRAME)
            b.box((-0.02 * L, side * W * 0.985, -Hh * 0.05), (L * 0.22, 0.3, 0.4), LIGHTS)
            b.box((-0.02 * L, side * W * 0.985, -Hh * 0.65), (L * 0.22, 0.3, 0.4), LIGHTS)
    # radiators (folding panels on the flanks, half open)
    for side in (1, -1):
        for k in range(3):
            x0 = -L / 2 + L * (0.14 + 0.1 * k)
            radiator_panel(b, x0, x0 + L * 0.08, side * W * 0.95, Hh * 0.55, W * 0.9, side, 18.0)
    # engines
    ne = 3 if L > 500 else 2
    for k in range(ne):
        ez = (k - (ne - 1) / 2) * Hh * 0.75
        for side in ((1, -1) if ne == 2 else (1, -1)):
            engine_cluster(b, -L / 2 + 0.5, side * W * 0.45, ez * 0.6, Hh * 0.42)
    # windows and greebles
    for side in (1, -1):
        window_rows(b, -L * 0.25, L * 0.3, side * W * 1.01, Hh * 0.35, 2, rng, side)
    greebles(b, -L * 0.4, L * 0.35, -W * 0.8, W * 0.8, Hh * 1.0, int(L / 9), rng, True, L / 780)
    greebles(b, -L * 0.4, L * 0.2, -W * 0.7, W * 0.7, -Hh * 1.0, int(L / 14), rng, False, L / 780)
    # nav lights (red port = +Y in Blender = -Y in Unreal... port/starboard handled with light colour in the material)
    for side in (1, -1):
        b.box((L * 0.02, side * W * 1.02, Hh * 0.8), (2.0, 0.4, 1.0), LIGHTS)
    obj = b.to_object(name)
    A.finish(obj, bevel=max(0.05, L / 3000), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def mandate_ship(name: str, length: float, seed: int, beam: float = 0.16, turrets: int = 3):
    rng = random.Random(seed)
    L = length
    W = L * beam / 2
    Hh = L * 0.06
    skew = rng.uniform(-0.18, 0.18)
    b = A.Builder()
    # blade bow raked forward, heavy stern; faceted asymmetric section
    wprof = [(0.0, 0.85), (0.15, 1.0), (0.55, 0.95), (0.8, 0.62), (0.93, 0.3), (1.0, 0.12)]
    hprof = [(0.0, 1.0), (0.45, 1.0), (0.8, 0.7), (1.0, 0.55)]
    zprof = [(0.0, 0.0), (0.6, 0.0), (1.0, 0.35)]        # the blade rises forward
    st = []
    for i in range(25):
        t = i / 24
        st.append((-L / 2 + t * L, section_mandate(W * profile(t, wprof), Hh * profile(t, hprof), skew), Hh * profile(t, zprof)))
    loft(b, st, PLATE)
    # armour slabs bolted on, offset and patched
    for _ in range(int(L / 12)):
        t = rng.uniform(0.05, 0.8)
        x = -L / 2 + t * L
        side = rng.choice((1, -1))
        w = W * profile(t, wprof)
        sz = (rng.uniform(8, 30) * L / 400, rng.uniform(0.8, 2.0) * L / 400, rng.uniform(4, 12) * L / 400)
        b.box((x, side * (w * 0.92 + sz[1] / 2), rng.uniform(-0.5, 0.6) * Hh), sz, rng.choice([PLATE, FRAME, LIVERY]))
    # dorsal blade fin (asymmetric, raked forward like the bow) with the command slit
    fx = -L * 0.1
    fin = []
    for i in range(7):
        t = i / 6
        fin.append((fx - L * 0.1 + t * L * 0.2, section_mandate(W * 0.18 * (1.0 - 0.5 * t), Hh * 0.55 * (0.6 + 0.6 * t), -skew), Hh * (1.25 + 0.35 * t)))
    loft(b, fin, PLATE)
    b.box((fx + L * 0.08, -skew * W * 0.4, Hh * 1.9), (L * 0.01, W * 0.12, Hh * 0.15), LIGHTS)
    # exposed radiator fins glowing orange along the dorsal line
    for k in range(5):
        x0 = -L / 2 + L * (0.12 + 0.08 * k)
        b.box((x0, (k % 2 - 0.5) * W * 0.6, Hh * 1.25), (L * 0.05, 0.6, Hh * 0.6), RADIATOR)
    # turrets
    for k in range(turrets):
        tx = -L / 2 + L * (0.4 + 0.12 * k)
        turret(b, (tx, 0.0, Hh * (1.0 + 0.3 * (k == 0))), L / 480)
    # engines: a brutal row
    ne = 3 if L > 350 else 2
    for k in range(ne):
        ey = (k - (ne - 1) / 2) * W * 0.7
        engine_cluster(b, -L / 2 + 0.5, ey, -Hh * 0.1, Hh * 0.5)
    # amber running lights and windows
    for side in (1, -1):
        window_rows(b, -L * 0.3, L * 0.15, side * W * 0.95, Hh * 0.1, 1, rng, side)
    greebles(b, -L * 0.45, L * 0.2, -W * 0.7, W * 0.7, Hh * 0.95, int(L / 11), rng, True, L / 600)
    obj = b.to_object(name)
    A.finish(obj, bevel=max(0.05, L / 3000), segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def freighter(name: str, length: float, seed: int):
    rng = random.Random(seed)
    L = length
    b = A.Builder()
    # spine truss with container racks, cab at the bow, engine block at the stern
    b.box((0, 0, 0), (L * 0.8, L * 0.04, L * 0.04), FRAME)
    for k in range(10):
        x = -L * 0.35 + k * L * 0.07
        for (dy, dz) in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            if rng.random() < 0.85:
                b.box((x, dy * L * 0.045, dz * L * 0.045), (L * 0.06, L * 0.045, L * 0.045), rng.choice([PLATE, LIVERY, FRAME]))
    b.box((L * 0.43, 0, L * 0.02), (L * 0.12, L * 0.09, L * 0.08), PLATE)
    b.box((L * 0.48, 0, L * 0.045), (L * 0.012, L * 0.07, L * 0.02), LIGHTS)
    b.box((-L * 0.44, 0, 0), (L * 0.1, L * 0.11, L * 0.11), FRAME)
    for dy in (-1, 1):
        engine_cluster(b, -L * 0.49, dy * L * 0.03, 0.0, L * 0.025)
    obj = b.to_object(name)
    A.finish(obj, bevel=0.1, segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


# ------------------------------------------------------------------ small craft (fighters, bombers, drones)
def craft(name: str, length: float, kind: str, seed: int, mandate: bool = False):
    """Small craft along +X: a lofted fuselage, wings, engines with glow, a lit canopy. kind: fighter|bomber|drone."""
    rng = random.Random(seed)
    b = A.Builder()
    L = length
    w = L * (0.09 if kind != "bomber" else 0.12)
    h = L * (0.07 if kind != "bomber" else 0.09)
    sec = (lambda ww, hh: section_mandate(ww, hh, 0.12)) if mandate else section_astra
    stations = []
    for k in range(7):
        t = k / 6
        wf = profile(t, [(0, 0.55), (0.15, 0.9), (0.55, 1.0), (0.85, 0.6), (1.0, 0.12)])
        hf = profile(t, [(0, 0.6), (0.2, 0.9), (0.55, 1.0), (0.85, 0.7), (1.0, 0.15)])
        stations.append((-L / 2 + t * L, sec(w * wf, h * hf), h * 0.1 * t))
    loft(b, stations, PLATE)
    # canopy (lit from inside) on fighters and bombers
    if kind != "drone":
        b.box((L * 0.2, 0, h * 0.95), (L * 0.16, w * 0.7, h * 0.35), LIGHTS)
    # wings: swept for fighters, straight and thick for bombers, three short vanes for drones
    if kind == "drone":
        for ang in (90, 210, 330):
            a = math.radians(ang)
            b.box((-L * 0.1, math.cos(a) * w * 1.6, math.sin(a) * w * 1.6), (L * 0.35, w * (2.2 if ang == 90 else 1.4), L * 0.02), FRAME)
    else:
        span = L * (0.75 if kind == "fighter" else 0.9)
        chord = L * (0.3 if kind == "fighter" else 0.36)
        for sy in (-1, 1):
            m = (Matrix.Translation((-L * 0.12, sy * span * 0.28, -h * 0.2)) @ Matrix.Rotation(math.radians(sy * (28 if kind == "fighter" else 8)), 4, "Z")
                 @ Matrix.Diagonal((chord, span * 0.56, L * 0.025, 1.0)))
            geom = bmesh.ops.create_cube(b.bm, size=1.0, matrix=m)
            b._assign(geom["verts"], PLATE)
            b.box((-L * 0.12 - chord * 0.35, sy * span * 0.5, -h * 0.2), (chord * 0.3, L * 0.05, L * 0.03), LIVERY)
            if kind == "bomber":   # torpedo pods under the wings
                b.cylinder((-L * 0.05, sy * span * 0.3, -h * 0.75), (L * 0.28, sy * span * 0.3, -h * 0.75), L * 0.035, FRAME, segments=12)
    # engines
    ne = 1 if kind == "drone" else 2
    for i in range(ne):
        yy = 0.0 if ne == 1 else (i - 0.5) * w * 1.1
        engine_cluster(b, -L * 0.47, yy, 0.0, L * (0.045 if kind != "bomber" else 0.05))
    obj = b.to_object(name)
    A.finish(obj, bevel=0.02, segments=1)
    A.box_uv(obj, texel_m=2.0)
    return obj


SHIPS = {
    # name: (builder, kwargs)
    "SM_SHIP_ASTRA_Aquila": (astra_ship, dict(length=780.0, seed=1, carrier=True, beam=0.14, turrets=4)),
    "SM_SHIP_ASTRA_Praetorian": (astra_ship, dict(length=920.0, seed=7, carrier=False, beam=0.15, turrets=6)),
    "SM_SHIP_ASTRA_Vigilant": (astra_ship, dict(length=280.0, seed=3, carrier=False, beam=0.12, turrets=2)),
    "SM_SHIP_MANDATE_Acheron": (mandate_ship, dict(length=460.0, seed=11, beam=0.17, turrets=3)),
    "SM_SHIP_MANDATE_Styx": (mandate_ship, dict(length=260.0, seed=13, beam=0.16, turrets=2)),
    "SM_SHIP_MANDATE_Lethe": (mandate_ship, dict(length=160.0, seed=17, beam=0.15, turrets=1)),
    "SM_SHIP_GUILD_Freighter": (freighter, dict(length=340.0, seed=5)),
    "SM_CRAFT_ASTRA_Falcon": (craft, dict(length=18.0, kind="fighter", seed=21)),
    "SM_CRAFT_ASTRA_Hammer": (craft, dict(length=26.0, kind="bomber", seed=23)),
    "SM_CRAFT_ASTRA_Wasp": (craft, dict(length=8.0, kind="drone", seed=25)),
    "SM_CRAFT_MANDATE_Harpy": (craft, dict(length=16.0, kind="fighter", seed=27, mandate=True)),
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
        faction_slots(obj, {"ASTRA": "A", "MANDATE": "M", "GUILD": "G"}[name.split("_")[2]])
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
        if preview:
            os.makedirs(preview, exist_ok=True)
            A.render_preview([obj], os.path.join(preview, name + ".png"), size=1000, view=(145.0, 22.0), dist_mul=1.1)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print("SHIPS_OK", json.dumps(report))


if __name__ == "__main__":
    main()
