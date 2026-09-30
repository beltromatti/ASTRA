"""ASN Aquila — Bridge v3 (Deck 1 · Section A): procedural generator driven by data/ship/aquila_bridge.json (version 3).

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/bridge_v3.py -- <output_dir> [options]

Options:
  --only A,B          build only these meshes (names without the SM_BRG3_ prefix are accepted)
  --no-export         build (and preview) without writing FBX files
  --preview <dir>     render the preview views into <dir> (Eevee); --views seated,standing,... to choose, --samples N
  --save-blend <f>    write the assembled preview scene as a .blend (quick re-renders: --render-blend <f>)
  --render-blend <f>  skip the build: open a .blend written by --save-blend and only render the views

Layout coordinates (data file): X forward, Y starboard, Z up, metres. Every builder works in that frame (bridge3_lib.FB
mirrors Y on the way out, the U() convention of bridge.py v2), so the FBX meshes land exactly on the data in Unreal.

Exported meshes (origin = bridge origin unless noted; opaque ones are Nanite in Unreal, the translucent ones are not):
  environment   SM_BRG3_Deck, SM_BRG3_WallPort, SM_BRG3_WallStarboard, SM_BRG3_WallBack, SM_BRG3_Ceiling, SM_BRG3_Window,
                SM_BRG3_Rails, SM_BRG3_ViewscreenFrame, SM_BRG3_MasterDisplay
  translucent   SM_BRG3_WindowGlass, SM_BRG3_RailGlass, SM_BRG3_ViewscreenImage, SM_BRG3_Holo<Station>
  props         origin on the floor under the seat / standing point, facing +X:
                SM_BRG3_ConsoleHelm/Ops/Tactical/Comms/Sensors/Engineering/Flight, SM_BRG3_ChairCaptain/XO/Crew,
                SM_BRG3_HoloTable (origin at the table centre on the floor)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as L  # noqa: E402
import bridge3_preview as PV  # noqa: E402
import bridge3_shell as SH  # noqa: E402
import bridge3_walls as WL  # noqa: E402
import bridge3_ceiling as CE  # noqa: E402
import bridge3_frame as FR  # noqa: E402
import bridge3_consoles as CO  # noqa: E402
import bridge3_holo as HO  # noqa: E402
import bridge3_seats as SE  # noqa: E402
import bridge3_table as TB  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "tools", "ue_scripts"))
sys.path.insert(0, os.path.join(L.ROOT, "tools", "ue_scripts"))
import bridge3_layout as LAY  # noqa: E402

ROOT = L.ROOT
DATA_PATH = os.path.join(ROOT, "data", "ship", "aquila_bridge.json")


def load_data() -> dict:
    return json.load(open(DATA_PATH, encoding="utf-8"))


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out_dir": os.path.join(ROOT, "art", "export", "bridge_v3"), "only": None, "export": True, "preview": None,
           "views": None, "samples": 48, "save_blend": None, "render_blend": None, "quality": "full"}
    it = iter(range(len(argv)))
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            out["only"] = set(x if x.startswith("SM_") else "SM_BRG3_" + x for x in argv[i + 1].split(","))
            i += 1
        elif a == "--no-export":
            out["export"] = False
        elif a == "--preview":
            out["preview"] = argv[i + 1]
            i += 1
        elif a == "--views":
            out["views"] = argv[i + 1].split(",")
            i += 1
        elif a == "--samples":
            out["samples"] = int(argv[i + 1])
            i += 1
        elif a == "--save-blend":
            out["save_blend"] = argv[i + 1]
            i += 1
        elif a == "--render-blend":
            out["render_blend"] = argv[i + 1]
            i += 1
        elif not a.startswith("--"):
            out["out_dir"] = a
        i += 1
    return out


# --------------------------------------------------------------------------------------------------------- build registry
_memo: dict = {}


def builders(c: SH.Ctx) -> list[tuple[str, object]]:
    def rails(n):
        if "rails" not in _memo:
            _memo["rails"] = FR.build_rails(c, "SM_BRG3_Rails", "SM_BRG3_RailGlass")
        return _memo["rails"][0]

    def rail_glass(n):
        if "rails" not in _memo:
            _memo["rails"] = FR.build_rails(c, "SM_BRG3_Rails", "SM_BRG3_RailGlass")
        return _memo["rails"][1]

    st = {x["id"]: x for x in c.D["stations"]}
    out = [
        ("SM_BRG3_Deck", lambda n: SH.build_deck(c, n)),
        ("SM_BRG3_WallPort", lambda n: _info(n, WL.build_side_wall(c, -1, n, c.D["stations"]))),
        ("SM_BRG3_WallStarboard", lambda n: _info(n, WL.build_side_wall(c, 1, n, c.D["stations"]))),
        ("SM_BRG3_WallBack", lambda n: FR.build_back_wall(c, n)),
        ("SM_BRG3_Ceiling", lambda n: CE.build_ceiling(c, n)),
        ("SM_BRG3_Window", lambda n: FR.build_window(c, n)),
        ("SM_BRG3_WindowGlass", lambda n: FR.build_window_glass(c, n)),
        ("SM_BRG3_Rails", rails),
        ("SM_BRG3_RailGlass", rail_glass),
        ("SM_BRG3_ViewscreenFrame", lambda n: FR.build_viewscreen_frame(c, n)),
        ("SM_BRG3_ViewscreenImage", lambda n: FR.build_viewscreen_image(c, n)),
        ("SM_BRG3_MasterDisplay", lambda n: FR.build_master_display(c, n)),
        ("SM_BRG3_HoloTable", lambda n: TB.build_holo_table(c.D, n)),
        ("SM_BRG3_ChairCrew", lambda n: SE.build_chair_crew(n)),
        ("SM_BRG3_ChairCaptain", lambda n: _info(n, SE.build_chair_command(n, True, ["SCREEN_captain_1", "SCREEN_captain_2"]))),
        ("SM_BRG3_ChairXO", lambda n: _info(n, SE.build_chair_command(n, False, ["SCREEN_xo_1"]))),
    ]
    for kind in ("helm", "ops", "tactical", "comms", "sensors", "engineering", "flight"):
        cap = kind.capitalize()
        out.append((f"SM_BRG3_Console{cap}", (lambda k: lambda n: _info(n, CO.build_console(k, n, st[k])))(kind)))
        out.append((f"SM_BRG3_Holo{cap}", (lambda k: lambda n: _info(n, HO.build_holo_panels(k, n)))(kind)))
    return out


INFO: dict = {}


def _info(name: str, result):
    """Builders that return (object, info): keep the info for the manifest, hand back the object."""
    obj, info = result
    INFO[name] = info
    return obj


def main() -> None:
    args = parse_args()
    D = load_data()
    c = SH.Ctx(D)
    L.load_label_atlas()
    A.reset_scene()
    t0 = time.time()
    objs: dict[str, bpy.types.Object] = {}
    report = []
    for name, build in builders(c):
        if args["only"] and name not in args["only"]:
            continue
        t = time.time()
        obj = build(name)
        objs[name] = obj
        st = A.stats(obj)
        report.append(st)
        print(f"  {name}: {st['tris']} tris, {len(st['materials'])} slots, {time.time() - t:.1f}s")
    print("built", len(objs), "meshes in", round(time.time() - t0, 1), "s; tris", sum(r["tris"] for r in report))

    if args["preview"]:
        views = args["views"] or ["overview"]
        preview_scene(D, c, objs, args, views)


def assemble(D: dict, objs: dict) -> list:
    """Place linked instances of every built mesh where the Unreal build puts it (data file placements); hide the originals."""
    from mathutils import Matrix
    out = []
    for pl in LAY.placements(D):
        src = objs.get(pl["mesh"])
        if src is None:
            continue
        inst = bpy.data.objects.new(pl["label"], src.data)
        bpy.context.scene.collection.objects.link(inst)
        x, y, z = pl["pos"]
        inst.matrix_world = Matrix.Translation((x, -y, z)) @ Matrix.Rotation(-math.radians(pl["yaw"]), 4, "Z")
        out.append(inst)
    for o in objs.values():
        o.hide_render = True
        o.hide_viewport = True
    return out


VIEWS = {
    # name: (eye layout xyz, yaw, pitch, fov)
    "overview": ((-7.5, -7.0, 9.0), 40.0, -32.0, 75.0),
    "top": ((0.0, 0.0, 22.0), 0.0, -90.0, 60.0),
    "seated": ((0.0, 0.0, 1.38), 0.0, -2.0, 90.0),
    "standing": ((-4.6, 0.0, 1.72), 0.0, -3.0, 90.0),
    "helm_back": ((5.4, -3.6, 1.1), 146.0, -4.0, 90.0),
    "crew_chair": ((7.3, -1.1, 0.75), 205.0, -6.0, 60.0),
    "captain_front": ((2.0, 1.1, 1.1), -155.0, -6.0, 60.0),
    "port": ((0.0, 2.4, 1.65), -90.0, 4.0, 90.0),
    "starboard": ((0.0, -2.4, 1.65), 90.0, 4.0, 90.0),
    "ceiling": ((-4.0, 0.0, 1.7), 0.0, 38.0, 100.0),
    "helm_close": ((4.2, -4.0, 1.55), 35.0, -14.0, 70.0),
    "chair_close": ((1.6, 1.3, 1.25), -140.0, -8.0, 62.0),
    "well": ((2.7, 0.0, 1.2), 0.0, -12.0, 90.0),
    "wall_s": ((-1.0, 0.5, 1.6), 78.0, 2.0, 80.0),
    "wall_p": ((-1.0, -0.5, 1.6), -78.0, 2.0, 80.0),
    "bay_close": ((-3.3, 5.0, 1.7), 97.0, 3.0, 70.0),
    "back": ((5.0, 0.0, 1.6), 180.0, 2.0, 90.0),
    "helm_console": ((3.6, -2.2, 1.3), 0.0, -12.0, 65.0),
    "tactical_close": ((-1.0, 1.4, 1.5), -140.0, -8.0, 62.0),
}


def preview_scene(D, c, objs, args, views) -> None:
    lay = LAY
    assemble(D, objs)
    PV.set_world((0.0, 0.0, 0.0), 0.0)
    PV.sky_dome(yaw_deg=float(os.environ.get("BRG3_SKYYAW", "0")))
    PV.make_materials(D.get("screens", {}))
    PV.configure_render(1600, 900, args["samples"], exposure=float(os.environ.get("BRG3_EXPOSURE", "0")))
    PV.json_lights(D, lay, PV.GAIN)
    for v in views:
        eye, yaw, pitch, fov = VIEWS[v]
        cam = PV.add_camera(v, eye, yaw, pitch, fov)
        PV.render(cam, os.path.join(args["preview"], f"{v}.jpg"))
        print("rendered", v)


if __name__ == "__main__":
    main()
