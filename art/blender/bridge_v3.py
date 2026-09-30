"""ASN Aquila — Bridge v3 (Deck 1 · Section A): procedural generator driven by data/ship/aquila_bridge.json (version 3).

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/bridge_v3.py -- [<output_dir>] [options]

  <output_dir>        FBX files + manifest.json (default art/export/bridge_v3, not in git)
Options:
  --only A,B          build only these meshes (names without the SM_BRG3_ prefix are accepted; no manifest is written)
  --no-export         build (and preview) without writing FBX files
  --preview <dir>     render the preview views into <dir> (Eevee); --views seated,standing,... to choose, --samples N
  --save-blend <f>    write the assembled preview scene (meshes, materials, lights) as a .blend to open in Blender

Layout coordinates (data file): X forward, Y starboard, Z up, metres. Every builder works in that frame (bridge3_lib.FB
mirrors Y on the way out, the U() convention of bridge.py v2), so the FBX meshes land exactly on the data in Unreal.

Exported meshes (origin = bridge origin unless noted; opaque ones are Nanite in Unreal, the translucent ones are not):
  environment   SM_BRG3_Deck, SM_BRG3_WallPort, SM_BRG3_WallStarboard, SM_BRG3_WallBack, SM_BRG3_Ceiling, SM_BRG3_Window,
                SM_BRG3_Rails, SM_BRG3_ViewscreenFrame, SM_BRG3_MasterDisplay (origin at the back-wall plane)
  translucent   SM_BRG3_WindowGlass, SM_BRG3_RailGlass, SM_BRG3_ViewscreenImage, SM_BRG3_Holo<Station>
  props         origin on the floor under the seat / standing point, facing +X:
                SM_BRG3_ConsoleHelm/Ops/Tactical/Comms/Sensors/Engineering/Flight, SM_BRG3_ChairCaptain/XO/Crew,
                SM_BRG3_HoloTable (origin at the table centre on the floor of the well)
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
import bridge3_checks as CK  # noqa: E402
import bridge3_frame as FR  # noqa: E402
import bridge3_consoles as CO  # noqa: E402
import bridge3_holo as HO  # noqa: E402
import bridge3_seats as SE  # noqa: E402
import bridge3_table as TB  # noqa: E402

sys.path.insert(0, os.path.join(L.ROOT, "tools", "ue_scripts"))
import bridge3_layout as LAY  # noqa: E402

ROOT = L.ROOT
DATA_PATH = os.path.join(ROOT, "data", "ship", "aquila_bridge.json")


def load_data() -> dict:
    with open(DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out_dir": os.path.join(ROOT, "art", "export", "bridge_v3"), "only": None, "export": True, "preview": None,
           "views": None, "samples": 48, "save_blend": None}
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
        elif not a.startswith("--"):
            out["out_dir"] = a
        i += 1
    return out


# --------------------------------------------------------------------------------------------------------- build registry
_memo: dict = {}
INFO: dict = {}


def _info(name: str, result):
    """Builders that return (object, info): keep the info for the manifest, hand back the object."""
    obj, info = result
    INFO[name] = info
    return obj


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


# ------------------------------------------------------------------------------------------------------------ manifest
def bounds_unreal(obj) -> dict:
    """Bounding box in the Unreal frame (metres): Blender +Y is Unreal -Y."""
    import mathutils
    cs = [obj.matrix_world @ mathutils.Vector(v) for v in obj.bound_box]
    lo = [min(v.x for v in cs), min(-v.y for v in cs), min(v.z for v in cs)]
    hi = [max(v.x for v in cs), max(-v.y for v in cs), max(v.z for v in cs)]
    return {"min": [round(x, 3) for x in lo], "max": [round(x, 3) for x in hi]}


def slot_kind(name: str) -> str:
    if name.startswith("SCREEN_"):
        return "screen"
    return "translucent" if name == L.GLASS else "shared"


def origin_of(name: str) -> str:
    short = name[len(LAY.PREFIX):]
    if short == "MasterDisplay":
        return "the back-wall plane, centred in y, floor level (+x into the room)"
    if short == "HoloTable":
        return "the table centre on the floor of the well"
    if short in LAY.ENV_MESHES:
        return "bridge origin"
    return "seat / standing point on the floor of its level, facing +X"


def build_manifest(D: dict, c: SH.Ctx, objs: dict, stats: dict, checks: dict) -> dict:
    layout = LAY.placements(D)
    uses: dict = {}
    for pl in layout:
        uses[pl["mesh"]] = uses.get(pl["mesh"], 0) + 1
    meshes, screens = {}, {}
    shared: list[str] = []
    scr: list[str] = []
    for name, obj in objs.items():
        st = stats[name]
        slots = [{"name": m, "kind": slot_kind(m)} for m in st["materials"]]
        for sl in slots:
            bucket = scr if sl["kind"] == "screen" else shared
            if sl["name"] not in bucket:
                bucket.append(sl["name"])
        meshes[name] = {"file": name + ".fbx", "tris": st["tris"], "size_m": st["size_m"], "bounds_m": bounds_unreal(obj), "slots": slots,
                        "nanite": not LAY.is_translucent(name), "translucent": LAY.is_translucent(name), "instances": uses.get(name, 0),
                        "origin": origin_of(name)}
    for name, info in INFO.items():
        lst = info.get("screens", []) if isinstance(info, dict) else info
        for sc in lst:
            slot = sc["screen"]
            size = sc.get("size_m", [0, 0])
            meta = D["screens"].get(slot, {})
            screens[slot] = {"mesh": name, "size_m": size, "aspect": round(size[0] / size[1], 3) if size[1] else None,
                             "surface": meta.get("surface", sc.get("surface")), "page": meta.get("page"), "instance": meta.get("instance"),
                             "uv": "0-1 over the image area, u to the viewer's right, v up"}
    gv = FR.viewscreen_geom(c)
    screens["SCREEN_viewscreen_1"] = {"mesh": "SM_BRG3_ViewscreenImage", "size_m": [gv["w"], gv["h"]], "aspect": round(gv["w"] / gv["h"], 3),
                                      "surface": "viewscreen", "page": "Viewscreen", "instance": None,
                                      "arc": {"radius_m": gv["R"], "half_angle_deg": round(gv["half_deg"], 2), "z_bottom": gv["z0"], "z_top": gv["z1"]},
                                      "uv": "0-1 over the image area, u to the viewer's right (seen from the Captain), v up"}
    md = D["master_display"]
    screens["SCREEN_master_1"] = {"mesh": "SM_BRG3_MasterDisplay", "size_m": [md["width"], md["height"]], "aspect": round(md["width"] / md["height"], 3),
                                  "surface": "wall", "page": "Master", "instance": D["screens"]["SCREEN_master_1"].get("instance"),
                                  "uv": "0-1 over the image area"}
    tris_scene = sum(m["tris"] * max(1, m["instances"]) for m in meshes.values())
    return {"version": 3, "generator": "art/blender/bridge_v3.py", "data": "data/ship/aquila_bridge.json",
            "frame": "Unreal (X forward, Y starboard, Z up), metres; the FBX meshes are in Blender space (Y mirrored) and Unreal imports them 1:1",
            "meshes": meshes, "placements": layout, "screens": screens,
            "materials": {"shared": sorted(shared), "screens": sorted(scr), "counts": {"shared": len(shared), "screens": len(scr)}},
            "budget": {"unique_meshes": len(meshes), "triangles_unique": sum(m["tris"] for m in meshes.values()), "triangles_in_scene": tris_scene,
                       "shared_material_slots": len(shared), "screen_slots": len(scr)},
            "layout_checks": {k: v for k, v in checks.items() if k != "footprints"}}


FANS = {"helm": (58.0, 0.5, 1.28), "ops": (58.0, 0.5, 1.28), "comms": (52.0, 0.5, 1.20), "sensors": (52.0, 0.5, 1.20),
        "engineering": (52.0, 0.5, 1.20), "flight": (52.0, 0.5, 1.20), "tactical": (64.0, 0.46, 0.98)}


def run_checks(D: dict, c: SH.Ctx) -> dict:
    """Footprints (consoles as fans), clearances between them and to the walls, clearance along the walking routes."""
    stations = [dict(st, type=(st["id"] if st.get("type") == "bay" else st.get("type"))) for st in D["stations"]]
    D2 = dict(D, stations=stations)
    back = SH.Wall((c.BACK_X, -c.BACK_HW), (c.BACK_X, c.BACK_HW), 0, n_out=(-1.0, 0.0))
    res = CK.check_layout(D2, FANS, [c.walls[1], c.walls[-1], back])
    res["routes"] = CK.check_routes(D2, FANS)
    return res


# ------------------------------------------------------------------------------------------------------------------ main
def main() -> None:
    args = parse_args()
    D = load_data()
    c = SH.Ctx(D)
    L.load_label_atlas()
    A.reset_scene()
    t0 = time.time()
    objs: dict[str, bpy.types.Object] = {}
    stats: dict = {}
    for name, build in builders(c):
        if args["only"] and name not in args["only"]:
            continue
        t = time.time()
        obj = build(name)
        objs[name] = obj
        stats[name] = A.stats(obj)
        print(f"  {name}: {stats[name]['tris']} tris, {len(stats[name]['materials'])} slots, {time.time() - t:.1f}s")
    print("built", len(objs), "meshes in", round(time.time() - t0, 1), "s; tris", sum(r["tris"] for r in stats.values()))

    checks = run_checks(D, c)
    for pr in checks["problems"]:
        print("  LAYOUT PROBLEM:", pr)
    for r in checks["routes"]:
        print(f"  route {r['route']}: clearance {r['min_clearance_m']} m (nearest {r['nearest']}) {'ok' if r['ok'] else 'TOO TIGHT'}")

    if args["export"]:
        out_dir = args["out_dir"]
        os.makedirs(out_dir, exist_ok=True)
        for name, obj in objs.items():
            A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        if not args["only"]:
            man = build_manifest(D, c, objs, stats, checks)
            with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(man, fh, indent=1)
            print("manifest:", json.dumps(man["budget"]), "materials", json.dumps(man["materials"]["counts"]))
        print("BRIDGE3_OK", out_dir)

    if args["preview"] or args["save_blend"]:
        preview_scene(D, c, objs, args, (args["views"] or ["overview"]) if args["preview"] else [])
        if args["save_blend"]:
            bpy.ops.wm.save_as_mainfile(filepath=args["save_blend"])


# ------------------------------------------------------------------------------------------------------------------ preview
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
    if os.environ.get("BRG3_NOCEILING"):
        for o in out:
            if o.name in ("Bridge_Ceiling",):
                o.hide_render = True
    return out


VIEWS = {
    # name: (eye layout xyz, yaw, pitch, fov)
    "overview": ((-7.5, -7.0, 9.0), 40.0, -32.0, 75.0),
    "top": ((0.0, 0.0, 22.0), 0.0, -90.0, 60.0),
    "top_open": ((1.0, 0.0, 19.0), 0.0, -90.0, 70.0),
    "seated": ((0.08, 0.0, 1.38), 0.0, -6.0, 90.0),
    "standing": ((-4.6, 0.0, 1.72), 0.0, -3.0, 90.0),
    "helm_back": ((5.4, -3.6, 1.1), 146.0, -4.0, 90.0),
    "crew_chair": ((7.3, -1.1, 0.75), 205.0, -6.0, 60.0),
    "helm_holo_back": ((8.4, -2.2, 0.85), 180.0, 0.0, 70.0),
    "helm_holo_front": ((4.8, -2.2, 0.75), 0.0, 6.0, 70.0),
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
    "eng_close": ((-0.9, 4.9, 1.6), 62.0, -15.0, 60.0),
    "label_check": ((4.07, 5.52, 1.6), 97.0, 29.0, 60.0),
    "stairs": ((0.6, 3.2, 1.6), 30.0, -24.0, 65.0),
    "chair_a": ((7.4, -3.5, 0.62), 135.0, -6.0, 42.0),
    "chair_b": ((6.0, -4.1, 0.5), 90.0, -3.0, 42.0),
    "chair_c": ((4.6, -2.2, 0.65), 0.0, -4.0, 42.0),
    "screen_top": ((3.0, 0.0, 1.5), 0.0, 18.0, 70.0),
    "master": ((-4.5, 0.0, 1.6), 180.0, 2.0, 60.0),
    "window_side": ((0.5, 6.0, 1.5), 40.0, 4.0, 75.0),
    "helm_console": ((3.6, -2.2, 1.3), 0.0, -12.0, 65.0),
    "tactical_close": ((-1.0, 1.4, 1.5), -140.0, -8.0, 62.0),
}


def preview_scene(D, c, objs, args, views) -> None:
    assemble(D, objs)
    PV.set_world((0.0, 0.0, 0.0), 0.0)
    PV.sky_dome(yaw_deg=float(os.environ.get("BRG3_SKYYAW", "0")))
    PV.make_materials(D.get("screens", {}))
    PV.configure_render(1600, 900, args["samples"], exposure=float(os.environ.get("BRG3_EXPOSURE", "0")))
    PV.json_lights(D, LAY, PV.GAIN)
    if os.environ.get("BRG3_VIEWSCREEN") == "on":
        PV.viewscreen_placeholder(True)
    if os.environ.get("BRG3_HOLO"):
        PV.holo_plot(D)
    for v in views:
        eye, yaw, pitch, fov = VIEWS[v]
        cam = PV.add_camera(v, eye, yaw, pitch, fov)
        PV.render(cam, os.path.join(args["preview"], f"{v}.jpg"))
        print("rendered", v)


if __name__ == "__main__":
    main()
