"""ASN Aquila — the Flight Deck (Deck 9 · Section B), the detail of ARTE-INTERNI. SM_HGR_Deck (art/blender/hangar.py) is the hall: the deck plates, the catapult tracks, the walls with their ribs, the
catwalks, the booth, the tubes, the trusses. This is what a working flight deck has and that hall lacks, in the same frame (data/ship/aquila_hangar.json: x forward from the aft wall where the lift
is, y starboard, 145 x 56 x 20 m; the Falcons park in the port bays at y -21, the Hammers in the starboard bays at y 20, the drones on their racks at x 5.5):
  - the deck's markings: a dashed taxi line down the middle, the outline of every craft's bay at its yaw, red-and-white safety lines along both walls, a hazard border round the lift;
  - the ground crew's equipment in service groups along both walls between the bays — tow tugs, fuel and foam carts, GPU carts, tool chests, pod trolleys, pallet trucks, a forklift, cargo
    containers, missile racks — and a forklift and a pallet truck about the deck;
  - the walls' bays between the ribs dressed (panels, vents, breaker panels, conduit bundles, extinguishers, screens) below the catwalks, two tall brushed panels with a hazard band above them;
  - lamps on the catwalk rails, cable trays under the catwalks, sprinkler mains, a bridge crane on the runways, the beacons and hazard frames at the mouths of the tubes.
One mesh (SM_HGR_Detail) over the hall; the pieces are the ship's (ship_furniture4.py / 6.py, ship_walls.py).

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_hangar.py -- [--preview <dir>] [--samples N]
(the FBX export stays with hangar.py, which calls detail() here).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_furniture4 as F4  # noqa: E402
import ship_furniture6 as F6  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_walls as W  # noqa: E402
from bridge3_lib import T, frame  # noqa: E402
from ship_lib import (CRATE_BLUE, CRATE_ORANGE, LAMP, RUBBER, STEEL, STRUCT, TRIM, SParts)  # noqa: E402
from ship_rooms import place  # noqa: E402

ROOT = SL.ROOT
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_hangar.json"), encoding="utf-8"))
LEN, HW, HGT = D["length"], D["half_width"], D["height"]
CW, CZ = D["catwalk"]["width"], D["catwalk"]["z"]
BAYS = D["bays"]
TUBES = D["tubes"]


def craft_spots() -> list:
    """(x, y, yaw) of every parked craft: the Falcons, the Hammers."""
    out = []
    for sq in ("alpha", "bravo"):
        bay = BAYS[sq]
        for k in range(bay["count"]):
            out.append((bay["x0"] + k * bay["pitch"], bay["y"], bay["yaw"]))
    return out


def deck_markings(b: SParts) -> None:
    """Paint on the deck: a dashed taxi line, bay outlines at the crafts' yaw, red-and-white safety lines at the walls, a hazard border round the lift."""
    for k in range(int((LEN - 24.0) / 6.0)):                                                      # the dashed line down the middle
        x = 10.0 + 6.0 * k
        b.soft.swatch_box((x, -0.1, 0.0), (x + 3.0, 0.1, 0.012), "yellow")
    for (x, y, yaw) in craft_spots():                                                              # a bay: an outline of white lines 12 x 8 m round the craft, a tick at the nose
        with b.at(frame(x, y, 0.0, yaw)):
            for (a0, a1, c0, c1) in ((-6.0, 6.0, -4.0, -3.85), (-6.0, 6.0, 3.85, 4.0), (-6.0, -5.85, -4.0, 4.0), (5.85, 6.0, -4.0, 4.0)):
                b.soft.swatch_box((a0, c0, 0.0), (a1, c1, 0.012), "white")
            b.soft.swatch_box((6.0, -0.4, 0.0), (7.5, 0.4, 0.012), "yellow")
    for side in (-1, 1):                                                                           # the safety lines: red and white blocks along the walls
        y0 = side * (HW - 1.9)
        for k in range(int((LEN - 4.0) / 1.0)):
            b.soft.swatch_box((2.0 + k, y0 - 0.2, 0.0), (3.0 + k, y0 + 0.2, 0.012), "red" if k % 2 else "white")
    for (x0, x1, y0, y1) in ((0.2, 6.0, -3.2, -2.9), (0.2, 6.0, 2.9, 3.2), (5.7, 6.0, -3.2, 3.2)):    # the lift's hazard border
        b.soft.swatch_box((x0, y0, 0.0), (x1, y1, 0.012), "yellow")
    for tb in TUBES:                                                                               # the tubes' mouths: a hazard band across the deck
        b.soft.swatch_box((LEN - 3.0, tb["y"] - tb["width"] / 2, 0.0), (LEN - 2.4, tb["y"] + tb["width"] / 2, 0.012), "yellow")


def equipment(b: SParts) -> None:
    """The ground crew's equipment in service groups along both walls between the bays, a forklift and a pallet truck on the deck."""
    rng = random.Random(9)
    for side in (-1, 1):
        y = side * (HW - 4.0)
        yaw_in = 90 if side < 0 else -90                                                           # facing the middle of the deck
        for g in range(8):
            xg = 14.0 + g * 16.0
            pieces = [(F4.tow_tug, ()), (F4.fuel_cart, ()), (F4.gpu_cart, ()), (F4.tool_chest, (0.9, 0.55, 1.05)), (F4.foam_cart, ()), (F4.pod_trolley, (2,))]
            rng.shuffle(pieces)
            for j in range(3):
                fn, args = pieces[(j + g) % len(pieces)]
                place(b, xg + j * 3.4 - 3.4, y + rng.uniform(-0.4, 0.4), yaw_in + rng.uniform(-18, 18), fn, *args)
            if g % 2 == 0:
                place(b, xg + 3.2, y - side * 1.6, yaw_in + 90, F6.cargo_container, 3.0, 1.5, 1.6, CRATE_BLUE, "eq_stores")
            else:
                place(b, xg + 3.0, y - side * 1.4, yaw_in, F6.missile_rack, 3, 2, 2.6)
    place(b, 28.0, -8.5, 20, F6.forklift)
    place(b, 31.0, -7.0, -30, F6.pallet_truck)
    place(b, 70.0, 8.5, 160, F6.forklift)


def wall_bays(b: SParts) -> None:
    """The bays between the ribs on both side walls: layered equipment panels up to the catwalk, two tall brushed panels with a hazard band above."""
    rng = random.Random(21)
    kinds = ("plain", "panelboard", "vent", "conduits", "safety", "screen", "hydrant")
    for side in (1, -1):
        fr = frame(0.0, side * HW, 0.0, 0.0) if side > 0 else frame(LEN, -HW, 0.0, 180.0)           # s along the wall, t outward, z up (the room at negative t)
        with b.at(fr):
            for k in range(int(LEN / 8)):
                s0, s1 = 8.0 * k + 0.9, 8.0 * (k + 1) - 0.9
                for j in range(2):                                                                  # two bays under each 8 m panel
                    a0 = s0 + j * (s1 - s0) / 2
                    a1 = s0 + (j + 1) * (s1 - s0) / 2
                    W.bay(b.soft, kinds[(2 * k + j + (3 if side < 0 else 0)) % len(kinds)], a0 + 0.1, a1 - 0.1, 8.2, rng, "flight", "flight_dim")
                W.panel(b.soft, s0, s1, CZ + 1.6, CZ + 6.0)
                W.panel(b.soft, s0, s1, CZ + 6.3, HGT - 3.0)
                b.emit.label(((s0 + s1) / 2, -0.07, CZ + 6.15), s1 - s0 - 0.6, (s1 - s0 - 0.6) / 10.0, (0, -1, 0), "hazard_h")


def catwalk_details(b: SParts) -> None:
    """On and under the catwalks: lamps on the rail posts, a cable tray beneath, hangers; a sprinkler main under each, the crane over the deck."""
    for side in (1, -1):
        yr = side * (HW - CW)
        for k in range(int(LEN / 8)):
            x = 4.0 + 8.0 * k
            b.emit.lamp_box((x - 0.2, yr - side * 0.06 - 0.03, CZ + 1.12), (x + 0.2, yr - side * 0.06 + 0.03, CZ + 1.2), "white_cool", LAMP)
        b.body.box((1.0, side * (HW - CW / 2) - 0.3, CZ - 0.55), (LEN - 1.0, side * (HW - CW / 2) + 0.3, CZ - 0.5), STRUCT)
        for k in range(3):
            b.fine.cyl((1.0, side * (HW - CW / 2) - 0.15 + k * 0.15, CZ - 0.46), (LEN - 1.0, side * (HW - CW / 2) - 0.15 + k * 0.15, CZ - 0.46), 0.03, RUBBER, seg=6)
        F6.sprinkler_line(b, (1.0, side * (HW - CW - 0.4), CZ - 0.6), (LEN - 1.0, side * (HW - CW - 0.4), CZ - 0.6), 3.2)
    zr = HGT - 4.6
    xb = 60.0                                                                                       # the bridge crane on the runways at y +-9
    for y in (-9.0, 9.0):
        b.body.box((xb - 0.8, y - 0.55, zr), (xb + 0.8, y + 0.55, zr + 0.9), STRUCT)
    b.body.box((xb - 0.45, -9.2, zr + 0.9), (xb + 0.45, 9.2, zr + 1.9), CRATE_ORANGE)
    b.body.box((xb - 0.9, -1.2, zr + 0.2), (xb + 0.9, 1.2, zr + 0.9), STRUCT)
    b.fine.cyl((xb, 0.0, zr + 0.2), (xb, 0.0, 3.0), 0.03, STEEL, seg=6)
    b.body.box((xb - 0.25, -0.2, 2.5), (xb + 0.25, 0.2, 3.0), CRATE_ORANGE)
    b.fine.cyl((xb, 0.0, 2.5), (xb, 0.0, 2.1), 0.04, STEEL, seg=8)
    b.emit.lamp_box((xb - 0.6, 1.2, zr + 0.3), (xb + 0.6, 1.205, zr + 0.4), "amber", LAMP)
    for tb in TUBES:                                                                                # beacons and a hazard frame at each tube's mouth
        for sy in (-1, 1):
            y = tb["y"] + sy * (tb["width"] / 2 + 0.4)
            b.body.box((LEN - 0.6, y - 0.3, 0.0), (LEN - 0.1, y + 0.3, tb["height"] + 1.0), STRUCT)
            for k in range(4):
                b.emit.lamp_cyl((LEN - 0.35, y, 2.0 + k * 3.0), (LEN - 0.35, y, 2.25 + k * 3.0), 0.25, "amber", LAMP, seg=12)
        b.body.box((LEN - 0.6, tb["y"] - tb["width"] / 2 - 0.4, tb["height"] + 0.4), (LEN - 0.1, tb["y"] + tb["width"] / 2 + 0.4, tb["height"] + 1.0), STRUCT)
        b.emit.label_fit((LEN - 0.62, tb["y"], tb["height"] + 0.7), 6.0, "eq_launch", (-1, 0, 0))


def detail(name: str = "SM_HGR_Detail"):
    SL.load_labels()
    b = SParts(bevel=0.01, fine_bevel=0.0)
    deck_markings(b)
    equipment(b)
    wall_bays(b)
    catwalk_details(b)
    return b.build(name, uv_meter=2.0)


# ------------------------------------------------------------------------------------------------------------------------------------- preview
def preview(out: str, samples: int = 24) -> None:
    import bpy
    import ship_preview as SP
    detail_obj = detail()
    SP.setup(1600, 900, samples, exposure=0.0, world=(0.05, 0.052, 0.058))
    SP.instance(detail_obj, (0, 0, 0), 0)
    detail_obj.hide_render = True
    gain = 1.5
    for k in range(6):
        x = 12 + k * 22.0
        for yy in (-16.0, 0.0, 16.0):
            SP.rect_light(f"hb{k}{yy}", (x, yy, HGT - 1.9), (6.0, 2.4), 60000 * 0.03 * gain, (0.95, 0.96, 1.0))
    views = {"deck": ((6.0, 0.0, 1.7), (60.0, 0.0, 3.0), 80), "bays": ((20.0, -4.0, 1.7), (50.0, -22.0, 2.0), 80), "wall": ((40.0, 0.0, 1.7), (40.0, 27.0, 5.0), 82),
             "crane": ((30.0, 0.0, 2.0), (70.0, 0.0, 14.0), 80), "tubes": ((110.0, 0.0, 1.7), (145.0, -12.0, 4.0), 80)}
    for n, (eye, tgt, fov) in views.items():
        cam = SP.look_camera(n, eye, tgt, fov)
        SP.render(cam, os.path.join(out, f"hangar_{n}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        preview(out, int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24)
    else:
        o = detail()
        print("HGR_DETAIL tris", sum(len(p.vertices) - 2 for p in o.data.polygons), "slots", len(o.data.materials))
