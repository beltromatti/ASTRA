"""ASN Aquila — Main Engineering (Deck 7 · Section F), the detail of ARTE-INTERNI. SM_ENG_Hall (art/blender/engineering.py) is the hall: the deck, the pit, the walls with their ribs, the gallery,
the master table, the conduits. This is what a working engine room has and that hall lacks, built from the kit's machines and wall bays and placed over it in the same frame (data/ship/
aquila_engineering.json: x forward, y starboard, the hall runs aft of the lift on x 0 .. -42, y +-14, 14 m high, the reactor at x -26):
  - the walls' bays between the ribs dressed as in the corridors (panels in brushed frames, vents, breaker panels, conduit bundles, extinguishers), up to the ceiling;
  - under the galleries a row of machines each side — switchgear, transformers, pump sets, pressure tanks, battery racks, control cabinets — clear of the wall consoles and the places of the watch;
  - round the pit a ring of light on the deck, hazard lines, four control pedestals facing the core, a second railing run in front of each;
  - the gallery's lamps, cable trays beneath it, a bridge crane over the pit on its runways, high-bay luminaires hung from the trusses (where the actor lights of build_engineering.py are),
    ducts and cable trays along the ceiling, the sign over the lift.
The detail is one mesh (SM_ENG_Detail); the pieces are the ship's (ship_furniture3.py machines, ship_walls.py bays), so the hall reads as the same ship as the corridors.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_engineering.py -- [--preview <dir>] [--samples N]
(the FBX export stays with engineering.py, which calls detail() here).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_furniture as F  # noqa: E402
import ship_furniture3 as H3  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
import ship_walls as W  # noqa: E402
from bridge3_lib import Rz, T, frame  # noqa: E402
from ship_lib import (COMPOSITE, CRATE_GREY, CRATE_ORANGE, LAMP, LAMP_DIM, LAMP_HOT, RUBBER, STEEL, STRUCT, TRIM, SParts)  # noqa: E402
from ship_rooms import place  # noqa: E402

ROOT = SL.ROOT
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_engineering.json"), encoding="utf-8"))
LEN, HW, HGT = D["length"], D["half_width"], D["height"]
R = D["reactor"]
RX, RY = R["x"], R["y"]
GZ, GW = D["gallery"]["z"], D["gallery"]["width"]
CREW = [(c["x"], c["y"]) for c in D["crew"]]


def clear_of_crew(x: float, y: float, r: float = 1.6) -> bool:
    return all(math.hypot(x - cx, y - cy) > r for cx, cy in CREW)


def wall_bays(b: SParts) -> None:
    """The bays between the ribs on both side walls: below the gallery layered panels in the corridors' language (breaker panels, vents, conduit bundles, extinguishers, screens) on the
    wall plane (the ribs stand 0.9 m proud of it, every 4 m), above it two tall panels in brushed frames up to the ceiling with a hazard line between."""
    rng = random.Random(14)
    kinds = ("plain", "panelboard", "vent", "conduits", "safety", "screen")
    for side in (1, -1):
        # the wall's frame: s along the wall, t outward from its face, z up; the room is at negative t
        fr = frame(-LEN, 14.0, 0.0, 0.0) if side > 0 else frame(0.0, -14.0, 0.0, 180.0)
        with b.at(fr):
            for k in range(int(LEN / 4)):
                s0, s1 = 4.0 * k + 0.5, 4.0 * (k + 1) - 0.5
                W.bay(b.soft, kinds[(k + (0 if side > 0 else 3)) % len(kinds)], s0, s1, 6.0, rng, "amber", "engineering_dim")
                W.panel(b.soft, s0, s1, 7.2, 9.9)
                W.panel(b.soft, s0, s1, 10.3, HGT - 0.8)
                b.emit.label((( s0 + s1) / 2, -0.06, 10.1), s1 - s0 - 0.3, (s1 - s0 - 0.3) / 8.0, (0, -1, 0), "hazard_h")


def machines(b: SParts) -> None:
    """A row of machines under each gallery (y +-12): switchgear, transformers, pump sets, tanks, battery racks, control cabinets, clear of the wall consoles (x -8, -18) and of the watch."""
    plan = [(-13.5, "hv3", "battery"), (-22.0, "pump", "hv2"), (-25.0, "xfmr", "tank"), (-28.0, "tank", "xfmr"), (-31.0, "battery", "pump"), (-34.0, "hv2", "hv3"), (-37.0, "pump", "battery"),
            (-12.0, "racks", "racks")]
    for side in (1, -1):
        yaw = -90 if side > 0 else 90
        y = side * 12.15
        for x, kind_s, kind_p in plan:
            kind = kind_s if side > 0 else kind_p
            if not clear_of_crew(x, y):
                continue
            if kind == "hv3":
                place(b, x, y, yaw, H3.hv_cabinet, 0.9, 0.7, 2.2, 3)
            elif kind == "hv2":
                place(b, x, y, yaw, H3.hv_cabinet, 0.9, 0.7, 2.2, 2)
            elif kind == "pump":
                place(b, x, y, 90, H3.pump_set, 1.8, "engineering")
            elif kind == "xfmr":
                place(b, x, y, yaw, H3.transformer, 1.6, 1.2, 1.9)
            elif kind == "tank":
                place(b, x, y, yaw, H3.tank_v, 0.7, 2.6, STEEL, "engineering")
            elif kind == "battery":
                place(b, x, y, yaw, H3.battery_rack, 1.4, 0.8, 2.0)
            elif kind == "racks":
                place(b, x, y, yaw, H3.rack_row, 3, 0.62, 0.95, 2.2, "engineering", 5)


def pit_surroundings(b: SParts) -> None:
    """Round the pit: a ring of light on the deck outside the railing, a hazard ring, four control pedestals on the diagonals facing the core."""
    pr = R["pit_radius"]
    H3.lamp_ring(b.emit, RX, RY, 0.0, pr + 0.55, 0.12, 0.006, "cyan_dim", LAMP_DIM, 72)
    H3.lamp_ring(b.emit, RX, RY, 0.0, pr + 0.95, 0.30, 0.004, "engineering_dim", LAMP_DIM, 72)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        x, y = RX + math.cos(a) * (pr + 3.2), RY + math.sin(a) * (pr + 3.2)
        place(b, x, y, math.degrees(a) + 180, H3.work_console, 2.2, "engineering", 2, None, True)


def overhead(b: SParts) -> None:
    """The bridge crane on its runways over the pit, the high-bay luminaires hung from the trusses, ducts and cable trays along the ceiling."""
    zr = HGT - 3.4
    for y in (-12.8, 12.8):                                                                         # the runway girders
        b.body.box((-LEN + 1.0, y - 0.25, zr), (-1.0, y + 0.25, zr + 0.55), COMPOSITE)
        b.fine.box((-LEN + 1.0, y - 0.3, zr + 0.55), (-1.0, y + 0.3, zr + 0.6), STEEL)
    xb = RX - 5.5
    b.body.box((xb - 0.35, -12.9, zr + 0.6), (xb + 0.35, 12.9, zr + 1.25), CRATE_ORANGE)           # the bridge girder across
    for y in (-12.8, 12.8):
        b.body.box((xb - 0.55, y - 0.4, zr + 0.55), (xb + 0.55, y + 0.4, zr + 1.3), STRUCT)         # its end carriages
    yt = 2.0
    b.body.box((xb - 0.7, yt - 0.6, zr + 0.0), (xb + 0.7, yt + 0.6, zr + 0.6), STRUCT)             # the trolley, the hoist drum, the rope and the hook block
    b.body.cyl((xb, yt - 0.4, zr + 0.3), (xb, yt + 0.4, zr + 0.3), 0.22, STEEL, seg=14)
    b.fine.cyl((xb, yt, zr), (xb, yt, zr - 5.0), 0.02, STEEL, seg=6)
    b.body.box((xb - 0.18, yt - 0.14, zr - 5.5), (xb + 0.18, yt + 0.14, zr - 5.0), CRATE_ORANGE)
    b.fine.cyl((xb, yt, zr - 5.5), (xb, yt, zr - 5.9), 0.03, STEEL, seg=8)
    b.emit.lamp_box((xb - 0.5, yt + 0.6, zr + 0.2), (xb + 0.5, yt + 0.605, zr + 0.28), "amber", LAMP)
    for k in range(6):                                                                              # high-bay luminaires on rods from the trusses
        x = -3.0 - k * 6.5
        for yy in (-8.0, 8.0):
            zt = HGT - 4.2
            b.fine.cyl((x, yy, zt + 0.3), (x, yy, HGT - 1.3), 0.02, STEEL, seg=6)
            MK.lathe(b.body, [(0.03, zt + 0.55), (0.25, zt + 0.5), (0.7, zt + 0.12), (0.72, zt + 0.02), (0.64, zt + 0.02), (0.22, zt + 0.35)], (x, yy, 0.0), STEEL, seg=18)
            b.emit.lamp_cyl((x, yy, zt + 0.02), (x, yy, zt + 0.012), 0.62, "white_cool", LAMP_HOT, seg=18)
    H3.duct_run(b, (-1.5, -5.0, HGT - 1.45), (-LEN + 1.5, -5.0, HGT - 1.45), 1.0, 0.7, STEEL, 2.0)
    H3.duct_run(b, (-1.5, 5.0, HGT - 1.45), (-LEN + 1.5, 5.0, HGT - 1.45), 1.0, 0.7, STEEL, 2.0)
    for y in (-2.0, 2.0):
        H3.pipe_bundle(b, (-1.5, y, HGT - 1.0), (-LEN + 1.5, y, HGT - 1.0), 4, 0.07, 0.04, (0, 1, 0), None, 2.4)


def gallery_details(b: SParts) -> None:
    """Under and on the galleries: lamps on the rail posts, cable trays beneath, ladders to the roof hatches at the aft corners."""
    for side in (1, -1):
        yr = side * (HW - 0.9 - GW)                                                                 # the rail's line
        for k in range(int((LEN - 4) / 4)):
            x = -3.0 - 2.0 - k * 4.0
            b.emit.lamp_box((x - 0.12, yr - side * 0.06 - 0.03, GZ + 1.12), (x + 0.12, yr - side * 0.06 + 0.03, GZ + 1.18), "white_cool", LAMP)
        b.body.box((-LEN + 1.0, side * (HW - 0.9 - GW * 0.5) - 0.3, GZ - 0.5), (-3.0, side * (HW - 0.9 - GW * 0.5) + 0.3, GZ - 0.46), STRUCT)
        for k in range(3):
            b.fine.cyl((-LEN + 1.0, side * (HW - 0.9 - GW * 0.5) - 0.15 + k * 0.15, GZ - 0.42), (-3.0, side * (HW - 0.9 - GW * 0.5) - 0.15 + k * 0.15, GZ - 0.42), 0.03, RUBBER, seg=6)
        for x in (-6.0, -14.0, -22.0, -30.0, -38.0):                                                 # hangers under the gallery
            b.fine.box((x - 0.03, side * (HW - 0.9 - GW) - 0.02, GZ - 0.5), (x + 0.03, side * (HW - 0.9) + 0.02, GZ - 0.15), TRIM)


def detail(name: str = "SM_ENG_Detail"):
    SL.load_labels()
    b = SParts(bevel=0.01, fine_bevel=0.0)
    wall_bays(b)
    machines(b)
    pit_surroundings(b)
    overhead(b)
    gallery_details(b)
    return b.build(name, uv_meter=2.0)


# ------------------------------------------------------------------------------------------------------------------------------------- preview
def preview(out: str, samples: int = 24) -> None:
    import bpy
    import engineering as E
    import ship_preview as SP
    hall = E.hall()
    core = E.core()
    det = detail()
    SP.setup(1600, 900, samples, exposure=0.0, world=(0.04, 0.045, 0.055))
    SP.instance(hall, (0, 0, 0), 0)
    SP.instance(core, (RX, -RY, 0.0), 0)
    SP.instance(det, (0, 0, 0), 0)
    for o in (hall, core, det):
        o.hide_render = True
    gain = 1.5
    for k in range(6):
        x = -3.0 - k * 6.5
        for yy in (-8.0, 8.0):
            SP.rect_light(f"hb{k}{yy}", (x, yy, HGT - 4.2), (1.4, 1.4), 16000 * 0.03 * gain, (0.92, 0.95, 1.0))
    for k in range(6):
        x = -3.0 - k * 6.5
        for yy in (-8.0, 8.0):
            SP.rect_light(f"cl{k}{yy}", (x, yy, HGT - 1.5), (3.4, 1.4), 5200 * 0.03 * gain, (0.92, 0.95, 1.0))
    views = {"hall": ((-1.0, 0.0, 1.7), (-26.0, 0.0, 5.0), 80), "gallery": ((-6.0, 11.0, 7.5), (-26.0, -6.0, 5.0), 80), "core": ((-14.0, 0.0, 1.7), (-26.0, 0.0, 6.0), 70),
             "wall": ((-14.0, -6.0, 1.7), (-22.0, 13.0, 3.0), 80), "machines": ((-20.0, 5.0, 1.7), (-32.0, 12.0, 1.8), 80), "crane": ((-8.0, 0.0, 3.0), (-28.0, 0.0, 11.0), 80)}
    for n, (eye, tgt, fov) in views.items():
        cam = SP.look_camera(n, eye, tgt, fov)
        SP.render(cam, os.path.join(out, f"eng_{n}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        preview(out, int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24)
    else:
        o = detail()
        print("ENG_DETAIL tris", sum(len(p.vertices) - 2 for p in o.data.polygons), "slots", len(o.data.materials))
