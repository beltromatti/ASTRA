"""ASN Aquila — Crew Berthing (Deck 4 · Section C), rebuilt in the kit's language (ARTE-INTERNI). SM_BERTH_Room of art/blender/berths.py, same frame and same places (data/ship/aquila_berths.json:
the compartment runs aft of the lift on x 0 .. -24, y +-3.6, seven groups of two racks and a column of lockers along each side wall, an aisle between them, the washroom door beside the lift,
the lounge aft with its table and four stools where the two who cannot sleep sit), with the shell and the light of the rooms of the plan: pale panels and wall cloth in bays whose pilasters
stand at the locker columns, a dark deck with a lighter aisle, a low ceiling with its beams on the same frames, cable trays and a pipe run over the aisle, dimmed warm aisle lights and red
night lights at the skirting (somebody is always asleep), a lounge with a proper table, stools, a shelf of books and games, a coffee corner and the fleet news. The racks and the lockers
are still berths.py's. Built in its own frame (x aft from the forward wall, y from the starboard wall) and turned into the compartment's frame by one transform.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_berths.py -- [--preview <dir>] [--samples N]
(the FBX export stays with berths.py, which calls room() here).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_decor as DC  # noqa: E402
import ship_furn2 as N  # noqa: E402
import ship_furniture as F  # noqa: E402
import ship_furniture2 as G  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
import ship_shell as SH  # noqa: E402
import ship_themes as TH  # noqa: E402
from bridge3_lib import T, frame  # noqa: E402
from ship_lib import (CARPET_SLATE, COMPOSITE, FABRIC_NAVY, LAMP, LAMP_DIM, LAMP_HOT, OAK, PLASTER_SLATE, RUBBER, STEEL, STRUCT, SWATCH, TRIM, WALNUT, SParts)  # noqa: E402
from ship_rooms import WF, WS, build_shell, place  # noqa: E402

ROOT = SL.ROOT
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_berths.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
OFF = WS + WF
ST = D["stacks"]
RW, LW = ST["rack_width"], ST["locker_width"]
AW = D["aisle_half_width"]
NEWS, SIGN, HEAD_SIGN = "MI_UI_Mess_News", "MI_SIGN_Berth_3C", "MI_SIGN_Head"
# where the ship's frames stand (the locker columns): u along the compartment
FRAMES = [-(ST["x_start"] - g * (2 * RW + LW) - 2 * RW - LW / 2) for g in range(ST["groups"])]


def style():
    edges_far = [u + OFF for u in FRAMES]
    edges_near = [LEN + 2 * OFF - OFF - u for u in FRAMES]
    return TH.crew(floor=CARPET_SLATE, floor_mode="covering", floor2=CARPET_SLATE, border=0.0, accent="red_dim", wall_lo=PLASTER_SLATE, wall_pattern=("panel", "cloth"), ceiling="flat",
                   downlights=False, wain_h=1.0, bay_edges={"far": edges_far, "near": edges_near})


def room(name: str = "SM_BERTH_Room"):
    """The compartment's mesh in its frame (the forward wall at x 0, the compartment running aft to x -24, y +-3.6; the lift's gate at y 0)."""
    SL.load_labels()
    b = SParts(bevel=0.005, fine_bevel=0.0)
    with b.at(frame(OFF, HW + OFF, 0.0, 180.0)):
        build_room(b)
    return b.build(name, uv_meter=1.0)


def build_room(b: SParts) -> None:
    lift, hd, lo = D["lift"], D["head_door"], D["lounge"]
    v_lift, v_head = HW - lift["y"], HW - hd["y"]
    doors = [{"wall": "left", "x": v_lift + OFF, "w": lift["width"], "h": lift["height"]}, {"wall": "left", "x": v_head + OFF, "w": hd["width"], "h": hd["height"]}]
    spec = {"key": "berths", "L": LEN + 2 * OFF, "D": 2 * HW + 2 * OFF, "h": H, "doors": doors}
    build_shell(b, spec, style(), doors=doors, bare=(), ceil_t=0.3, floor_t=0.3)
    with b.at(T(OFF, OFF, 0.0)):                                   # from here: u aft from the forward wall's face, v from the starboard wall's face
        v_mid = HW
        # the aisle: a lighter runner down the middle, edged with a thin lit line, and the guide
        b.soft.swatch_box((0.3, v_mid - AW + 0.1, 0.0), (LEN - 0.3, v_mid + AW - 0.1, 0.012), "grey5")
        for v in (v_mid - AW + 0.1, v_mid + AW - 0.112):
            b.emit.lamp_box((0.3, v, 0.0), (LEN - 0.3, v + 0.012, 0.014), "red_dim", LAMP_DIM)
        # the forward wall: the washroom door (closed) with its sign, the lift's frame and the compartment's sign
        dv0, dv1 = v_head - hd["width"] / 2, v_head + hd["width"] / 2
        b.body.box((0.0, dv0, 0.0), (0.06, dv1, hd["height"]), COMPOSITE)
        b.fine.box((-0.0, dv0 + 0.06, 0.06), (0.012, dv1 - 0.06, hd["height"] - 0.06), PLASTER_SLATE)
        b.fine.box((0.06, dv0 + 0.1, 0.95), (0.1, dv0 + 0.2, 1.1), STEEL)                              # the handle
        b.emit.screen((0.07, v_head, hd["height"] + 0.22), 0.56, 0.14, HEAD_SIGN, (1, 0, 0))
        lv0, lv1 = v_lift - lift["width"] / 2, v_lift + lift["width"] / 2
        for (a, c, z0, z1) in ((lv0 - 0.14, lv0, 0.0, lift["height"] + 0.14), (lv1, lv1 + 0.14, 0.0, lift["height"] + 0.14), (lv0, lv1, lift["height"], lift["height"] + 0.14)):
            b.body.box((0.0, a, z0), (0.12, c, z1), STEEL)
        b.emit.screen((0.01, HW - 2.35, 2.05), 1.2, 0.3, SIGN, (1, 0, 0))
        # the ceiling: the ship's frames as beams, the cable trays and the pipe run over the aisle, the dimmed warm aisle lights between the beams
        spec2 = {"L": LEN + 2 * OFF, "D": 2 * HW + 2 * OFF, "h": H}
        SH.beams(b, spec2, style(), [u + OFF for u in FRAMES], 0.22)
        for sgn in (-1, 1):
            v = v_mid + sgn * (AW - 0.18)
            b.body.box((0.2, v - 0.16, H - 0.12), (LEN - 0.2, v + 0.16, H - 0.1), STEEL)
            b.body.box((0.2, v - 0.16, H - 0.16), (LEN - 0.2, v - 0.14, H - 0.1), STEEL)
            b.body.box((0.2, v + 0.14, H - 0.16), (LEN - 0.2, v + 0.16, H - 0.1), STEEL)
            for k in range(3):
                b.fine.cyl((0.2, v - 0.08 + k * 0.08, H - 0.13), (LEN - 0.2, v - 0.08 + k * 0.08, H - 0.13), 0.022, RUBBER, seg=8)
        b.body.cyl((0.1, v_mid - 0.35, H - 0.22), (LEN - 0.1, v_mid - 0.35, H - 0.22), 0.07, STEEL, seg=14)
        edges = [0.4] + [u for u in FRAMES] + [LEN - 0.4]
        for a, c in zip(edges[:-1], edges[1:]):
            if c - a > 1.2:
                SH.band(b, a + 0.4, c - 0.4, v_mid, 0.4, H - 0.05, "warm_dim", LAMP_DIM)
        # the lounge: a table with its four stools (where the two who cannot sleep sit), the fleet news on the aft wall, a shelf of books and games, the coffee corner
        t = lo["table"]
        tu, tv = -t["x"], HW - t["y"]
        place(b, tu, tv, 0, F.table, t["length"], t["width"], t["height"], OAK, TRIM, True)
        for (sx, sy) in ((tu + 0.75, tv + 0.85), (tu - 0.75, tv + 0.85), (tu + 0.75, tv - 0.85), (tu - 0.75, tv - 0.85)):
            place(b, sx, sy, 0, F.stool, 0.19, 0.48, FABRIC_NAVY)
        for (mu, mv, s_) in ((tu + 0.4, tv + 0.2, 1), (tu - 0.5, tv - 0.25, 2), (tu + 0.1, tv - 0.3, 3)):
            place(b, mu, mv, 0, DC.mug, z=t["height"])
        place(b, tu - 0.1, tv + 0.05, 0, DC.book_stack, 2, 5, 0.18, 0.13, z=t["height"])
        sc = lo["screen"]
        sw, sh = sc["y1"] - sc["y0"], sc["z1"] - sc["z0"]
        sv = HW - (sc["y0"] + sc["y1"]) / 2
        b.body.box((LEN - 0.05, sv - sw / 2 - 0.06, sc["z0"] - 0.06), (LEN, sv + sw / 2 + 0.06, sc["z1"] + 0.06), STEEL)
        b.emit.screen((LEN - 0.056, sv, (sc["z0"] + sc["z1"]) / 2), sw, sh, NEWS, (-1, 0, 0))
        place(b, 22.85, 0.19, 90, F.shelf, 1.5, 0.3, 1.9, 4, WALNUT, True, 3, True)                            # books and games
        b.body.box((21.3, 0.0, 0.0), (21.8, 0.45, 0.95), COMPOSITE)                                   # the coffee corner
        place(b, 21.55, 0.23, 90, G.coffee_machine, z=0.95)
        place(b, LEN, 6.45, 180, DC.notice_board, 1.0, 0.7, 5, z=1.7)


# ------------------------------------------------------------------------------------------------------------------------------------- preview
def preview(out: str, samples: int = 24) -> None:
    import bpy
    import bridge3_preview as PV
    import ship_preview as SP
    import berths as BR
    obj = room("SM_BERTH_Room")
    SP.setup(1600, 900, samples, exposure=0.0, world=(0.05, 0.052, 0.058))
    for slot, page in ((NEWS, "Mess_News"), (SIGN, "Berth_3C"), (HEAD_SIGN, "Head")):
        try:
            PV.screen_mat(slot, page, 2.4)
        except Exception:
            pass
    SP.instance(obj, (0, 0, 0), 0)
    obj.hide_render = True
    stacks = {v: BR.stack(f"SM_BERTH_Stack_{v}", v, 11 + k) for k, v in enumerate("ABC")}
    lockers = BR.lockers()
    for o in list(stacks.values()) + [lockers]:
        o.hide_render = True
    for mesh, x, y, yaw in BR.layout():
        src = lockers if mesh == "SM_BERTH_Lockers" else stacks[mesh[-1]]
        dup = bpy.data.objects.new(mesh, src.data)
        bpy.context.scene.collection.objects.link(dup)
        dup.location = (x, -y, 0.0)
        dup.rotation_euler = (0.0, 0.0, math.radians(-yaw))
    gain = 1.5
    SP.rect_light("aisle", (-10.0, -0.07, H - 0.1), (18.0, 0.3), 24000 * 0.03 * gain, (1.0, 0.84, 0.67))
    SP.rect_light("lounge", (D["lounge"]["table"]["x"], D["lounge"]["table"]["y"], H - 0.1), (2.0, 1.2), 8000 * 0.03 * gain, (1.0, 0.88, 0.75))
    views = {"aisle": ((-0.8, 0.0, 1.62), (-20.0, 0.0, 1.5), 84), "stacks": ((-6.0, 0.9, 1.6), (-9.0, 3.5, 1.2), 82), "lounge": ((-15.0, 1.2, 1.65), (-23.0, -0.8, 1.3), 84),
             "lift": ((-6.0, -1.0, 1.65), (0.0, 0.6, 1.8), 84)}
    for n, (eye, tgt, fov) in views.items():
        cam = SP.look_camera(n, eye, tgt, fov)
        SP.render(cam, os.path.join(out, f"berths_{n}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        preview(out, int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24)
    else:
        o = room()
        print("BERTH_ROOM tris", sum(len(p.vertices) - 2 for p in o.data.polygons), "slots", len(o.data.materials))
