"""ASN Aquila — Flight Deck (Deck 9 · Section B), from data/ship/aquila_hangar.json.

  SM_HGR_Deck    the hall: non-skid deck plates, catapult tracks running into the two launch tubes, ribbed side walls
                 with panels, catwalks, the aft wall with the lift and the control booth, the front wall with the
                 tubes, a ceiling of trusses, crane rails and light fixtures, pipes along the walls
  SM_HGR_Glass   the booth's window
  SM_HGR_Detail  (ARTE-INTERNI, ship_hangar.py) the deck's markings, the ground crew's equipment along the walls, the dressed wall bays, the bridge crane, the tubes' beacons

Coordinates in the data are Unreal's (X forward, Y starboard, Z up); U() flips Y for Blender so the meshes land right.
blender -b --factory-startup --python-exit-code 1 -P art/blender/hangar.py -- art/export/hangar [--preview <dir>]
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_hangar.json"), encoding="utf-8"))
LEN, HW, HGT = D["length"], D["half_width"], D["height"]
T = 0.5     # wall thickness


def U(x, y, z):
    return (x, -y, z)


def box(b, x0, x1, y0, y1, z0, z1, mat):
    """An axis-aligned box from Unreal-convention bounds."""
    lo = U(min(x0, x1), max(y0, y1), min(z0, z1))
    hi = U(max(x0, x1), min(y0, y1), max(z0, z1))
    b.box_minmax((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]), mat)


def wall_with_openings(b, x, y0, y1, openings, mat, trim):
    """A wall at x spanning y0..y1 (0..HGT), cut into rectangles around the openings [(yc, w, z0, z1)]."""
    ys = sorted({y0, y1} | {o[0] - o[1] / 2 for o in openings} | {o[0] + o[1] / 2 for o in openings})
    for ya, yb in zip(ys, ys[1:]):
        cuts = [o for o in openings if o[0] - o[1] / 2 <= ya + 1e-6 and o[0] + o[1] / 2 >= yb - 1e-6]
        zs = [0.0, HGT]
        for o in cuts:
            zs += [o[2], o[3]]
        zs = sorted(set(zs))
        for za, zb in zip(zs, zs[1:]):
            inside = any(o[2] <= za + 1e-6 and o[3] >= zb - 1e-6 for o in cuts)
            if not inside and zb - za > 1e-3:
                box(b, x - T / 2, x + T / 2, ya, yb, za, zb, mat)
    for yc, w, z0, z1 in openings:   # frames around the openings
        for (a0, a1, c0, c1) in ((yc - w / 2 - 0.4, yc - w / 2, z0, z1 + 0.4), (yc + w / 2, yc + w / 2 + 0.4, z0, z1 + 0.4), (yc - w / 2, yc + w / 2, z1, z1 + 0.4)):
            box(b, x - T, x + T, a0, a1, c0, c1, trim)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/hangar"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    b = A.Builder()
    tubes = D["tubes"]
    # --- the deck: 4 x 4 m non-skid plates with seams, the catapult tracks, the lanes
    for i in range(int(LEN / 4)):
        for j in range(int(2 * HW / 4)):
            x0, y0 = i * 4.0, -HW + j * 4.0
            box(b, x0 + 0.03, x0 + 3.97, y0 + 0.03, y0 + 3.97, -0.25, 0.0, A.MAT_FLOOR)
    box(b, 0, LEN, -HW, HW, -0.6, -0.25, A.MAT_STRUCTURE)
    for tb in tubes:
        for side in (-1, 1):   # twin catapult rails from mid-deck into the tube
            yy = tb["y"] + side * 2.6
            box(b, 40.0, LEN + tb["length"], yy - 0.25, yy + 0.25, 0.0, 0.08, A.MAT_TRIM)
        box(b, 40.0, LEN + tb["length"], tb["y"] - 0.12, tb["y"] + 0.12, 0.0, 0.03, A.MAT_GUIDE)   # the centre light line
    # --- side walls: ribs every 8 m, panels between, a catwalk along each wall, pipes
    cw = D["catwalk"]
    for side in (-1, 1):
        yw = side * HW
        box(b, 0, LEN, yw - side * 0.0, yw + side * T, 0, HGT, A.MAT_PANEL)
        for k in range(int(LEN / 8) + 1):
            x = k * 8.0
            box(b, x - 0.5, x + 0.5, yw - side * 1.2, yw, 0, HGT, A.MAT_STRUCTURE)
        # the catwalk: grate floor, fascia, railing
        yc = yw - side * cw["width"]
        box(b, 0, LEN, min(yw, yc), max(yw, yc), cw["z"] - 0.12, cw["z"], A.MAT_GRATE)
        box(b, 0, LEN, yc - 0.06, yc + 0.06, cw["z"] - 0.5, cw["z"], A.MAT_STRUCTURE)
        box(b, 0, LEN, yc - 0.04, yc + 0.04, cw["z"] + 1.05, cw["z"] + 1.12, A.MAT_TRIM)
        for k in range(int(LEN / 2)):
            box(b, k * 2.0, k * 2.0 + 0.06, yc - 0.03, yc + 0.03, cw["z"], cw["z"] + 1.1, A.MAT_TRIM)
        for z, r in ((2.2, 0.18), (2.7, 0.12), (15.5, 0.25)):   # fuel and coolant lines
            yy = yw - side * (1.5 + r)
            b.cylinder(U(0.5, yy, z), U(LEN - 0.5, yy, z), r, A.MAT_TRIM, segments=10)
        for k in range(18):   # light panels high on the walls
            x = 4 + k * 8.0
            box(b, x - 1.5, x + 1.5, yw - side * 0.05, yw - side * 0.02, 17.5, 18.1, A.MAT_LIGHT)
    # --- the aft wall: the lift, the booth window above it, the booth itself behind
    lift = D["lift"]
    bo = D["booth"]
    wall_with_openings(b, 0.0, -HW, HW, [(lift["y"], lift["width"], 0.0, lift["height"]),
                                         (0.0, 2 * bo["half_width"], bo["window_bottom"], bo["window_top"])], A.MAT_PANEL, A.MAT_TRIM)
    box(b, -bo["depth"], 0.0, -bo["half_width"] - 0.5, bo["half_width"] + 0.5, bo["floor"] - 0.3, bo["floor"], A.MAT_FLOOR)
    box(b, -bo["depth"], 0.0, -bo["half_width"] - 0.5, bo["half_width"] + 0.5, bo["window_top"] + 1.2, bo["window_top"] + 1.5, A.MAT_STRUCTURE)
    box(b, -bo["depth"] - 0.3, -bo["depth"], -bo["half_width"] - 0.5, bo["half_width"] + 0.5, bo["floor"] - 0.3, bo["window_top"] + 1.5, A.MAT_PANEL)
    for side in (-1, 1):
        box(b, -bo["depth"], 0.0, side * (bo["half_width"] + 0.2), side * (bo["half_width"] + 0.5), bo["floor"] - 0.3, bo["window_top"] + 1.5, A.MAT_PANEL)
    box(b, -2.2, -0.6, -bo["half_width"] + 1, bo["half_width"] - 1, bo["floor"], bo["floor"] + 1.0, A.MAT_STRUCTURE)    # the launch consoles
    box(b, -2.25, -0.55, -bo["half_width"] + 1, bo["half_width"] - 1, bo["floor"] + 1.0, bo["floor"] + 1.06, A.MAT_RUBBER)
    for k in range(6):
        y = -bo["half_width"] + 2.5 + k * (2 * bo["half_width"] - 5) / 5
        box(b, -1.9, -1.8, y - 0.55, y + 0.55, bo["floor"] + 1.1, bo["floor"] + 1.75, A.MAT_SCREEN)
    # the lift shaft behind its door
    box(b, -3.6, 0.0, lift["y"] - 2.0, lift["y"] - 1.6, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, -3.6, 0.0, lift["y"] + 1.6, lift["y"] + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, -3.6, -3.2, lift["y"] - 2.0, lift["y"] + 2.0, 0.0, 3.6, A.MAT_STRUCTURE)
    box(b, -3.6, 0.0, lift["y"] - 2.0, lift["y"] + 2.0, 3.6, 3.9, A.MAT_STRUCTURE)
    box(b, -3.2, 0.0, lift["y"] - 1.6, lift["y"] + 1.6, -0.1, 0.0, A.MAT_FLOOR)
    box(b, -0.05, 0.05, lift["y"] - 1.9, lift["y"] + 1.9, 3.4, 3.55, A.MAT_LIGHT)
    # --- the front wall with the two launch tubes, and the tubes
    wall_with_openings(b, LEN, -HW, HW, [(tb["y"], tb["width"], 0.0, tb["height"]) for tb in tubes], A.MAT_PANEL, A.MAT_TRIM)
    for tb in tubes:
        y0, y1, h, x0, x1 = tb["y"] - tb["width"] / 2, tb["y"] + tb["width"] / 2, tb["height"], LEN, LEN + tb["length"]
        box(b, x0, x1, y0 - T, y0, 0, h, A.MAT_STRUCTURE)
        box(b, x0, x1, y1, y1 + T, 0, h, A.MAT_STRUCTURE)
        box(b, x0, x1, y0 - T, y1 + T, h, h + T, A.MAT_STRUCTURE)
        box(b, x0, x1, y0, y1, -0.25, 0.0, A.MAT_FLOOR)
        for k in range(5):   # light rings down the tube
            x = x0 + 1.0 + k * (tb["length"] - 2.0) / 4
            box(b, x - 0.15, x + 0.15, y0 + 0.02, y0 + 0.12, 0.3, h - 0.3, A.MAT_LIGHT)
            box(b, x - 0.15, x + 0.15, y1 - 0.12, y1 - 0.02, 0.3, h - 0.3, A.MAT_LIGHT)
            box(b, x - 0.15, x + 0.15, y0 + 0.3, y1 - 0.3, h - 0.12, h - 0.02, A.MAT_LIGHT)
    # --- the ceiling: plates, trusses across the hall, crane rails along it, big light fixtures
    box(b, 0, LEN, -HW, HW, HGT, HGT + 0.3, A.MAT_STRUCTURE)
    for k in range(int(LEN / 12) + 1):
        x = k * 12.0
        box(b, x - 0.4, x + 0.4, -HW, HW, HGT - 1.6, HGT, A.MAT_STRUCTURE)         # the truss chords
        box(b, x - 0.15, x + 0.15, -HW, HW, HGT - 1.6, HGT - 1.3, A.MAT_TRIM)
    for yy in (-9.0, 9.0):
        box(b, 0, LEN, yy - 0.4, yy + 0.4, HGT - 2.2, HGT - 1.6, A.MAT_STRUCTURE)    # crane rails
    for k in range(6):
        x = 12 + k * 22.0
        for yy in (-16.0, 0.0, 16.0):
            box(b, x - 3.0, x + 3.0, yy - 1.2, yy + 1.2, HGT - 1.8, HGT - 1.65, A.MAT_LIGHT)
            box(b, x - 3.2, x + 3.2, yy - 1.4, yy + 1.4, HGT - 1.65, HGT - 1.5, A.MAT_STRUCTURE)
    deck = b.to_object("SM_HGR_Deck")
    A.finish(deck, bevel=0.02, segments=1)
    A.box_uv(deck, texel_m=2.0)
    A.export_fbx(deck, os.path.join(out, "SM_HGR_Deck.fbx"))
    report = [A.stats(deck)]
    A.clear_objects()
    # ARTE-INTERNI: what a working flight deck has and the hall lacks (art/blender/ship_hangar.py): the deck's markings, the ground crew's equipment, the dressed wall bays, the crane and the beacons
    import ship_hangar
    det = ship_hangar.detail("SM_HGR_Detail")
    A.export_fbx(det, os.path.join(out, "SM_HGR_Detail.fbx"))
    report.append(A.stats(det))
    A.clear_objects()
    g = A.Builder()
    box(g, -0.05, 0.05, -bo["half_width"], bo["half_width"], bo["window_bottom"], bo["window_top"], A.MAT_GLASS)
    glass = g.to_object("SM_HGR_Glass")
    A.box_uv(glass, texel_m=2.0)
    A.export_fbx(glass, os.path.join(out, "SM_HGR_Glass.fbx"))
    report.append(A.stats(glass))
    if preview:
        os.makedirs(preview, exist_ok=True)
        A.clear_objects()
    print("HANGAR_OK", json.dumps(report))


if __name__ == "__main__":
    main()
