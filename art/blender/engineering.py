"""ASN Aquila — Main Engineering (Deck 7 · Section F), from data/ship/aquila_engineering.json.

  SM_ENG_Hall    the hall: deck plates, ribbed walls with panels, the forward wall with the lift, the gallery around the
                 hall at mid-height with its stairs, the reactor pit and its railing, conduits from the core to the walls,
                 the master systems display (a long table), wall consoles, coolant lines, the ceiling's trusses and lights
  SM_ENG_Core    the reactor core: a dark housing with slots, containment coils, and the plasma behind (its own slot,
                 MI_ENG_Plasma, pulses in Unreal)

Coordinates in the data are Unreal's (X forward, Y starboard, Z up); U() flips Y for Blender.
blender -b --factory-startup --python-exit-code 1 -P art/blender/engineering.py -- art/export/engineering
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_engineering.json"), encoding="utf-8"))
LEN, HW, HGT = D["length"], D["half_width"], D["height"]
T = 0.5
PLASMA = "MI_ENG_Plasma"
COOLANT = "MI_ENG_Coolant"


def U(x, y, z):
    return (x, -y, z)


def box(b, x0, x1, y0, y1, z0, z1, mat):
    lo = U(min(x0, x1), max(y0, y1), min(z0, z1))
    hi = U(max(x0, x1), min(y0, y1), max(z0, z1))
    b.box_minmax(lo, hi, mat)


def cyl(b, p0, p1, r, mat, seg=16, r2=None):
    b.cylinder(U(*p0), U(*p1), r, mat, segments=seg, radius2=r2)


def ring(b, x, y, z, r, thick, mat, seg=32):
    """A horizontal ring (torus-like, as short cylinders around a circle)."""
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        cyl(b, (x + math.cos(a0) * r, y + math.sin(a0) * r, z), (x + math.cos(a1) * r, y + math.sin(a1) * r, z), thick, mat, seg=6)


def hall():
    b = A.Builder()
    R = D["reactor"]
    rx, ry = R["x"], R["y"]
    # --- the deck: plates around the reactor pit (a disc is cut out by skipping the plates inside it)
    for i in range(int(LEN / 2)):
        for j in range(int(2 * HW / 2)):
            x0, y0 = -LEN + i * 2.0, -HW + j * 2.0
            cx, cy = x0 + 1.0, y0 + 1.0
            if math.hypot(cx - rx, cy - ry) < R["pit_radius"] - 0.2:
                continue
            box(b, x0 + 0.02, x0 + 1.98, y0 + 0.02, y0 + 1.98, -0.2, 0.0, A.MAT_FLOOR)
    box(b, -LEN, 0, -HW, HW, -0.55, -0.2, A.MAT_STRUCTURE)
    # the pit: a sunken ring floor and its wall
    pr, pd = R["pit_radius"], R["pit_depth"]
    cyl(b, (rx, ry, -pd - 0.3), (rx, ry, -pd), pr, A.MAT_STRUCTURE, seg=40)
    for k in range(40):   # the pit wall
        a0, a1 = 2 * math.pi * k / 40, 2 * math.pi * (k + 1) / 40
        mx, my = rx + math.cos((a0 + a1) / 2) * (pr + 0.15), ry + math.sin((a0 + a1) / 2) * (pr + 0.15)
        seglen = pr * (a1 - a0) + 0.05
        ang = (a0 + a1) / 2
        from mathutils import Matrix
        import hullkit as K
        with K.part(b, Matrix.Translation(U(mx, my, -pd / 2 - 0.1)) @ Matrix.Rotation(-ang, 4, "Z")):
            b.box((0, 0, 0), (0.3, seglen, pd + 0.2), A.MAT_PANEL)
    # the railing around the pit
    ring(b, rx, ry, 1.08, pr + 0.1, 0.04, A.MAT_TRIM, seg=48)
    ring(b, rx, ry, 0.55, pr + 0.1, 0.03, A.MAT_TRIM, seg=48)
    for k in range(24):
        a = 2 * math.pi * k / 24
        cyl(b, (rx + math.cos(a) * (pr + 0.1), ry + math.sin(a) * (pr + 0.1), 0), (rx + math.cos(a) * (pr + 0.1), ry + math.sin(a) * (pr + 0.1), 1.1), 0.035, A.MAT_TRIM, seg=6)
    # --- walls: ribs every 4 m, panels, the accent line, coolant lines (blue) and power trunks
    for side in (-1, 1):
        yw = side * HW
        box(b, -LEN, 0, yw, yw + side * T, 0, HGT, A.MAT_PANEL)
        for k in range(int(LEN / 4) + 1):
            x = -k * 4.0
            box(b, x - 0.35, x + 0.35, yw - side * 0.9, yw, 0, HGT, A.MAT_STRUCTURE)
        box(b, -LEN, 0, yw - side * 0.06, yw - side * 0.02, 1.2, 1.28, A.MAT_ACCENT)
        for z, r, m in ((3.2, 0.22, COOLANT), (3.8, 0.22, COOLANT), (11.8, 0.35, A.MAT_TRIM), (12.6, 0.2, A.MAT_TRIM)):
            yy = yw - side * (1.2 + r)
            cyl(b, (-LEN + 0.5, yy, z), (-0.5, yy, z), r, m, seg=12)
        for k in range(10):   # lamps high on the walls
            x = -2 - k * 4.0
            box(b, x - 1.2, x + 1.2, yw - side * 0.05, yw - side * 0.02, 12.9, 13.3, A.MAT_LIGHT)
    box(b, -LEN - T, -LEN, -HW, HW, 0, HGT, A.MAT_PANEL)            # the aft wall
    for k in range(7):                                               # the aft wall's great conduits
        y = -HW + 2 + k * (2 * HW - 4) / 6
        box(b, -LEN + 0.1, -LEN + 1.0, y - 0.6, y + 0.6, 0, HGT, A.MAT_STRUCTURE)
    # the forward wall with the lift
    lift = D["lift"]
    ly, lw, lh = lift["y"], lift["width"], lift["height"]
    box(b, 0, T, -HW, ly - lw / 2, 0, HGT, A.MAT_PANEL)
    box(b, 0, T, ly + lw / 2, HW, 0, HGT, A.MAT_PANEL)
    box(b, 0, T, ly - lw / 2, ly + lw / 2, lh, HGT, A.MAT_PANEL)
    for (a0, a1, c0, c1) in ((ly - lw / 2 - 0.4, ly - lw / 2, 0, lh + 0.4), (ly + lw / 2, ly + lw / 2 + 0.4, 0, lh + 0.4), (ly - lw / 2, ly + lw / 2, lh, lh + 0.4)):
        box(b, -0.1, 0.6, a0, a1, c0, c1, A.MAT_TRIM)
    box(b, 0.5, 3.8, ly - 2.0, ly + 2.0, -0.1, 0.0, A.MAT_FLOOR)     # the lift car's floor behind the door
    box(b, 3.4, 3.8, ly - 2.0, ly + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly - 2.0, ly - 1.6, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly + 1.6, ly + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, 0.5, 3.8, ly - 2.0, ly + 2.0, 3.6, 3.9, A.MAT_STRUCTURE)
    # --- the gallery at mid-height along both walls and the aft wall, stairs down at the forward end
    G = D["gallery"]
    gz, gw = G["z"], G["width"]
    for side in (-1, 1):
        y0, y1 = side * (HW - 0.9 - gw), side * (HW - 0.9)
        box(b, -LEN + 1, -3, min(y0, y1), max(y0, y1), gz - 0.15, gz, A.MAT_GRATE)
        yc = y0
        box(b, -LEN + 1, -3, yc - 0.04, yc + 0.04, gz + 1.05, gz + 1.12, A.MAT_TRIM)
        for k in range(int((LEN - 4) / 2)):
            x = -3 - k * 2.0
            box(b, x - 0.03, x + 0.03, yc - 0.03, yc + 0.03, gz, gz + 1.1, A.MAT_TRIM)
        # stairs: from the deck at x -3 up to the gallery at x -11
        steps = 16
        for s in range(steps):
            x = -3.0 - s * (8.0 / steps)
            z = (s + 1) * gz / steps
            box(b, x - 0.5, x, min(y0, y1), max(y0, y1), z - 0.08, z, A.MAT_GRATE)
    box(b, -LEN + 1, -LEN + 1 + gw, -HW + 0.9, HW - 0.9, gz - 0.15, gz, A.MAT_GRATE)
    # --- conduits from the core to the walls (at the gallery's height and under the ceiling)
    for k in range(6):
        a = 2 * math.pi * (k + 0.5) / 6
        for z, r in ((gz + 2.2, 0.35), (HGT - 1.6, 0.45)):
            x0, y0 = rx + math.cos(a) * (R["radius"] + 0.6), ry + math.sin(a) * (R["radius"] + 0.6)
            dx, dy = math.cos(a), math.sin(a)
            ty = (HW - 1.2 - math.copysign(1.0, dy) * y0) / abs(dy) if abs(dy) > 1e-3 else 1e9
            tx = (x0 + LEN - 1.2) / abs(dx) if dx < -1e-3 else ((-1.2 - x0) / dx if dx > 1e-3 else 1e9)
            t = max(0.5, min(tx, ty))
            cyl(b, (x0, y0, z), (x0 + dx * t, y0 + dy * t, z), r, A.MAT_TRIM, seg=12)
            for q in range(1, int(t / 3)):   # collars
                cyl(b, (x0 + dx * q * 3, y0 + dy * q * 3, z), (x0 + dx * (q * 3 + 0.25), y0 + dy * (q * 3 + 0.25), z), r + 0.08, A.MAT_STRUCTURE, seg=12)
    # --- the master systems display: a long table facing aft, its top a screen
    mc = D["master_console"]
    mx, my, ml, mw = mc["x"], mc["y"], mc["length"], mc["width"]
    box(b, mx - mw / 2, mx + mw / 2, my - ml / 2, my + ml / 2, 0, 0.95, A.MAT_STRUCTURE)
    box(b, mx - mw / 2 - 0.1, mx + mw / 2 + 0.1, my - ml / 2 - 0.1, my + ml / 2 + 0.1, 0.95, 1.0, A.MAT_TRIM)
    box(b, mx - mw / 2 + 0.15, mx + mw / 2 - 0.15, my - ml / 2 + 0.15, my + ml / 2 - 0.15, 1.0, 1.02, "MI_ASTRA_ScreenMaster")
    box(b, mx + mw / 2 + 0.01, mx + mw / 2 + 0.05, my - ml / 2 + 0.2, my + ml / 2 - 0.2, 0.78, 0.84, A.MAT_ACCENT)
    # --- wall consoles (a desk and two screens each)
    for wc in D["wall_consoles"]:
        x, side = wc["x"], wc["side"]
        yw = side * (HW - 0.9)
        box(b, x - 1.6, x + 1.6, yw - side * 1.1, yw, 0, 0.9, A.MAT_STRUCTURE)
        box(b, x - 1.7, x + 1.7, yw - side * 1.2, yw, 0.9, 0.96, A.MAT_RUBBER)
        for k in (-0.8, 0.8):
            box(b, x + k - 0.7, x + k + 0.7, yw - side * 0.35, yw - side * 0.3, 1.3, 2.2, A.MAT_SCREEN)
    # --- the ceiling: plates, trusses across, lamps
    box(b, -LEN, 0, -HW, HW, HGT, HGT + 0.3, A.MAT_STRUCTURE)
    for k in range(int(LEN / 6) + 1):
        x = -k * 6.0
        box(b, x - 0.3, x + 0.3, -HW, HW, HGT - 1.2, HGT, A.MAT_STRUCTURE)
    for k in range(6):
        x = -3 - k * 6.5
        for yy in (-8.0, 8.0):
            box(b, x - 1.8, x + 1.8, yy - 0.8, yy + 0.8, HGT - 1.3, HGT - 1.22, A.MAT_LIGHT)
    obj = b.to_object("SM_ENG_Hall")
    A.finish(obj, bevel=0.015, segments=1)
    A.box_uv(obj, texel_m=2.0)
    return obj


def core():
    """The reactor core: a housing of vertical staves with slots through which the plasma shows, containment coils."""
    b = A.Builder()
    R = D["reactor"]
    r = R["radius"]
    pd = R["pit_depth"]
    cyl(b, (0, 0, -pd), (0, 0, HGT), r * 0.62, PLASMA, seg=32)                  # the plasma column
    staves = 24
    for k in range(staves):
        a0 = 2 * math.pi * k / staves
        a1 = a0 + 2 * math.pi / staves * 0.62
        for (za, zb) in ((-pd, 1.2), (1.9, 5.2), (5.9, 9.2), (9.9, HGT)):
            p = [U(math.cos(a0) * r, math.sin(a0) * r, 0), U(math.cos(a1) * r, math.sin(a1) * r, 0)]
            mx, my = (p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2
            import hullkit as K
            from mathutils import Matrix
            ang = math.atan2(my, mx)
            with K.part(b, Matrix.Translation((mx, my, (za + zb) / 2)) @ Matrix.Rotation(ang, 4, "Z")):
                b.box((0, 0, 0), (0.35, r * (a1 - a0) * 1.05, zb - za), A.MAT_STRUCTURE)
    for z in (-pd + 0.3, 1.55, 5.55, 9.55, HGT - 0.5):                          # containment coils
        for dz in (-0.2, 0.2):
            ring(b, 0, 0, z + dz, r + 0.25, 0.22, A.MAT_TRIM, seg=40)
        ring(b, 0, 0, z, r + 0.32, 0.12, PLASMA, seg=40)
    cyl(b, (0, 0, HGT - 0.6), (0, 0, HGT), r + 1.2, A.MAT_STRUCTURE, seg=32)     # the cap into the ceiling
    cyl(b, (0, 0, -pd), (0, 0, -pd + 0.6), r + 1.0, A.MAT_STRUCTURE, seg=32)      # the base in the pit
    obj = b.to_object("SM_ENG_Core")
    A.finish(obj, bevel=0.01, segments=1)
    A.box_uv(obj, texel_m=2.0)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/engineering"
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    report = []
    for fn in (hall, core):
        A.clear_objects()
        obj = fn()
        A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    print("ENGINEERING_OK", json.dumps(report))


if __name__ == "__main__":
    main()
