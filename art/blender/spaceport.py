"""Port Aurelius: the spaceport on the plateau above the bay (Port Aurelius Field) and the city's buildings.

  SM_NR_Apron      the field's concrete apron with taxi lines
  SM_NR_Pad        a landing pad (30 m radius): painted ring and chevrons, edge lights
  SM_NR_Tower      the control tower: base, shaft, glazed cab, beacon mast
  SM_NR_Hangar     a maintenance hangar with its big door
  SM_NR_Terminal   the terminal: a long glazed hall
  SM_NR_Bldg_A     a glass tower (for the tall blocks), 120 m before scaling
  SM_NR_Bldg_B     a slab block with ribbon windows, 40 m
  SM_NR_Bldg_C     a stepped block, 70 m
  nr_port.json     the field's layout (metres, relative to the field's centre, Blender axes)

Material slots are the Unreal instances (MI_NR_*), made by tools/ue_scripts/make_planet_materials.py.
Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/spaceport.py -- art/export/newravenna_port [--preview <dir>]
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import hullkit as K  # noqa: E402

CONCRETE, PAINT, GLASS, FACADE, METAL, LIGHT, DARK = ("MI_NR_Concrete", "MI_NR_Paint", "MI_NR_Glass", "MI_NR_Facade", "MI_HULL_A_Frame",
                                                     "MI_ASTRA_Light", "MI_NR_Dark")


def done(b, name, bevel=0.03):
    obj = b.to_object(name)
    A.finish(obj, bevel=bevel, segments=1)
    A.box_uv(obj, texel_m=4.0)
    return obj


def apron():
    b = A.Builder()
    b.box((0, 0, 0.15), (1300, 330, 0.3), CONCRETE)
    for x in range(-600, 601, 100):                      # expansion joints (dark lines)
        b.box((x, 0, 0.305), (0.4, 330, 0.02), DARK)
    for y in (-150.0, 150.0):
        b.box((0, y * 0.9, 0.305), (1300, 0.4, 0.02), DARK)
    b.box((0, -40, 0.31), (1200, 1.2, 0.02), PAINT)       # the taxi line
    for x in range(-550, 551, 60):
        b.box((x, -40, 0.32), (8, 0.5, 0.02), PAINT)
    return done(b, "SM_NR_Apron", 0.0)


def pad():
    b = A.Builder()
    b.cylinder((0, 0, 0), (0, 0, 0.5), 30.0, CONCRETE, segments=48)
    rng = 48
    for k in range(rng):                                  # the painted ring
        a0, a1 = 2 * math.pi * k / rng, 2 * math.pi * (k + 0.8) / rng
        r = 25.0
        b.box(((math.cos(a0) + math.cos(a1)) * r / 2, (math.sin(a0) + math.sin(a1)) * r / 2, 0.52),
              (r * (a1 - a0) * 1.02, 1.1, 0.03), PAINT)
    for sy in (-1, 1):                                    # the chevrons: where the nose goes
        for k in range(3):
            x = 4 + k * 5.0
            for side in (-1, 1):
                with K.part(b, _rot(x, side * 1.6 * sy, 0.52, side * 0.6)):
                    b.box((0, 0, 0), (4.0, 0.8, 0.03), PAINT)
    b.box((-12, 0, 0.52), (6, 0.8, 0.03), PAINT)
    for k in range(16):                                   # edge lights
        a = 2 * math.pi * k / 16
        b.box((math.cos(a) * 29.2, math.sin(a) * 29.2, 0.6), (0.5, 0.5, 0.2), LIGHT)
    return done(b, "SM_NR_Pad", 0.02)


def _rot(x, y, z, ang):
    from mathutils import Matrix
    return Matrix.Translation((x, y, z)) @ Matrix.Rotation(ang, 4, "Z")


def tower():
    b = A.Builder()
    K.block(b, (0, 0, 5), (18, 18, 10), FACADE, c=0.08)
    b.box((9.1, 0, 3), (0.3, 8, 4), GLASS)                # the entrance
    K.frustum(b, (-4.5, 4.5, 4.5), (-3.8, 3.8, 3.8), 10, 46, FACADE, chamfer=0.25)       # the shaft
    for z in range(14, 46, 4):
        b.box((0, 0, z), (9.3, 9.3, 0.25), METAL)
    K.frustum(b, (-6.5, 6.5, 6.5), (-9, 9, 9), 46, 48, METAL, chamfer=0.3)          # the cab's floor, flaring out
    K.frustum(b, (-8.6, 8.6, 8.6), (-8.2, 8.2, 8.2), 48, 54, GLASS, chamfer=0.3)     # glazed cab (raked)
    for k in range(8):                                     # mullions
        a = 2 * math.pi * (k + 0.5) / 8
        b.cylinder((math.cos(a) * 8.9, math.sin(a) * 8.9, 48), (math.cos(a) * 8.5, math.sin(a) * 8.5, 54), 0.15, METAL, segments=6)
    K.frustum(b, (-9.2, 9.2, 9.2), (-7, 7, 7), 54, 55.5, METAL, chamfer=0.3)         # the roof
    K.mast(b, 0, 0, 55.5, 9, METAL, LIGHT, dish=1.6)
    b.box((0, 0, 65), (0.9, 0.9, 0.9), LIGHT)             # the beacon
    return done(b, "SM_NR_Tower")


def hangar():
    b = A.Builder()
    L, W, H = 70.0, 46.0, 18.0
    b.box((0, 0, H / 2 - 2), (L, W, H - 4), FACADE)
    K.slab(b, -L / 2, L / 2, K.chamfer_rect(W / 2 + 0.5, 4.5, 0.6, top=0.4), K.chamfer_rect(W / 2 + 0.5, 4.5, 0.6, top=0.4), METAL, H - 2.5, H - 2.5)
    b.box((L / 2 + 0.15, 0, 7.5), (0.3, W - 6, 15), DARK)          # the big door
    for k in range(7):
        b.box((L / 2 + 0.35, -W / 2 + 3 + k * (W - 6) / 6, 7.5), (0.2, 0.4, 15), METAL)
    b.box((L / 2 + 0.3, 0, 15.6), (0.3, W - 5, 0.8), LIGHT)        # floodlight strip
    for x in range(-30, 31, 10):                                    # ribs along the flanks
        for sy in (-1, 1):
            b.box((x, sy * (W / 2 + 0.2), H / 2 - 2), (0.6, 0.4, H - 4), METAL)
    return done(b, "SM_NR_Hangar")


def terminal():
    b = A.Builder()
    L, W, H = 120.0, 30.0, 12.0
    b.box((0, 0, 1.5), (L, W, 3), FACADE)                            # plinth
    b.box((0, 0, 7.5), (L - 2, W - 2, 9), GLASS)                     # the glazed hall
    for x in range(-58, 59, 6):
        b.box((x, W / 2 - 1, 7.5), (0.35, 0.3, 9), METAL)
        b.box((x, -W / 2 + 1, 7.5), (0.35, 0.3, 9), METAL)
    K.slab(b, -L / 2 - 4, L / 2 + 4, K.chamfer_rect(W / 2 + 4, 0.8, 0.3), K.chamfer_rect(W / 2 + 4, 0.8, 0.3), FACADE, H + 0.5, H + 0.5)   # the roof, overhanging
    for k in range(6):
        b.box((-45 + k * 18, 0, H + 2), (8, 5, 2), METAL)            # plant on the roof
    return done(b, "SM_NR_Terminal")


def bldg_a():
    """A glass tower: curtain wall between mullions, a crown, plant on the roof (120 m)."""
    b = A.Builder()
    H, w = 120.0, 15.0
    b.box((0, 0, 2.5), (2 * w + 2, 2 * w + 2, 5), FACADE)            # podium
    b.box((0, 0, 5 + (H - 5) / 2), (2 * w, 2 * w, H - 5), GLASS)
    for k in range(11):
        t = -w + k * (2 * w) / 10
        for (x, y, sx, sy) in ((t, w, 0.4, 0.5), (t, -w, 0.4, 0.5), (w, t, 0.5, 0.4), (-w, t, 0.5, 0.4)):
            b.box((x, y, 5 + (H - 5) / 2), (sx, sy, H - 5), METAL)
    for z in range(20, int(H), 20):
        b.box((0, 0, z), (2 * w + 0.6, 2 * w + 0.6, 0.6), METAL)      # floor bands every 20 m
    K.frustum(b, (-w, w, w), (-w * 0.6, w * 0.6, w * 0.6), H, H + 8, FACADE, chamfer=0.2)   # the crown
    K.mast(b, 0, 0, H + 8, 14, METAL, LIGHT)
    return done(b, "SM_NR_Bldg_A")


def bldg_b():
    """A slab block with ribbon windows (40 m)."""
    b = A.Builder()
    H, lx, ly = 40.0, 22.0, 11.0
    floors = 11
    for f in range(floors):
        z = f * (H / floors)
        b.box((0, 0, z + 1.1), (2 * lx, 2 * ly, 2.2), FACADE)
        b.box((0, 0, z + 2.9), (2 * lx - 0.6, 2 * ly - 0.6, 1.4), GLASS)
    b.box((0, 0, H + 0.4), (2 * lx + 0.4, 2 * ly + 0.4, 0.8), FACADE)
    for k in range(3):
        b.box((-12 + k * 12, 0, H + 1.8), (6, 5, 2), METAL)
    return done(b, "SM_NR_Bldg_B")


def bldg_c():
    """A stepped block: three tiers and terraces (70 m)."""
    b = A.Builder()
    tiers = ((16, 16, 30), (12, 12, 25), (8, 8, 15))
    z = 0.0
    for i, (w, d, h) in enumerate(tiers):
        b.box((0, 0, z + h / 2), (2 * w, 2 * d, h), FACADE)
        for f in range(int(h // 4)):
            b.box((0, 0, z + 2.6 + f * 4), (2 * w + 0.3, 2 * d + 0.3, 1.2), GLASS)
        z += h
        b.box((0, 0, z + 0.3), (2 * w + 1, 2 * d + 1, 0.6), METAL)
    K.mast(b, 0, 0, z + 0.6, 10, METAL, LIGHT)
    return done(b, "SM_NR_Bldg_C")


LAYOUT = {
    # relative to the field's centre (Blender axes: +y north); the apron runs east-west along the field's south half
    "apron": [(0.0, -120.0, 0.0)],
    "pads": [(-450.0, -150.0, 0.3), (-230.0, -150.0, 0.3), (-10.0, -150.0, 0.3), (210.0, -150.0, 0.3), (430.0, -150.0, 0.3)],
    "tower": [(-560.0, 150.0, 0.0)],
    "hangars": [(-320.0, 170.0, 0.0), (-200.0, 170.0, 0.0), (-80.0, 170.0, 0.0)],
    "terminal": [(260.0, 170.0, 0.0)],
}


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/newravenna_port"
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    report = []
    for fn in (apron, pad, tower, hangar, terminal, bldg_a, bldg_b, bldg_c):
        A.clear_objects()
        obj = fn()
        A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    with open(os.path.join(out, "nr_port.json"), "w", encoding="utf-8") as f:
        json.dump(LAYOUT, f, indent=1)
    print("PORT_OK", json.dumps(report))


if __name__ == "__main__":
    main()
