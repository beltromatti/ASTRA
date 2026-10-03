"""SPAZIO-VIVO — the places and civilian hulls of the Aurelia system: build, export and preview (docs/SPAZIO.md).

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/spacegen3.py -- [<out_dir>] [options]

  <out_dir>          FBX files + manifest.json (default art/export/space_v3, not in git)
Options:
  --only a,b         build only these meshes (full names or the part after the last underscore group: Keeper, Arsenal, Tanker_A, ...)
  --detail 0.6       thin out the scattered details (1.0 = full); the triangle counts follow
  --seed N           add N to every mesh's seed (other dice, same designs)
  --no-export        build (and preview) without writing FBX files
  --preview <dir>    render the previews of each mesh into <dir> (Eevee): the views its builder asks for (a three-quarter view, a close-up or two, the
                     silhouette from the side and from above); --views three_quarter,closeup,top,side,sil to choose; --samples N
  --report           print the budget table at the end

Meshes (origin = the mesh's own centre, x forward, the FBX export mirrors y as usual; opaque, Nanite in Unreal):
  SM_PLACE_*       Keeper Station (and its turning control ring), the Arsenal (and its cranes), the Tiberius refinery, the Ceres mining station
  SM_VESSEL_*      the civilian hulls of the traffic: tankers, liners, tugs, ore barges, Guild freighters
  SM_ROCK_*        the Ceres Belt's rocks;  SM_DEBRIS_*  what a wreck leaves;  SM_POD_*  escape pods;  SM_BUOY_*  lane buoys
manifest.json lists per mesh: triangles, size, bounds, slots, and what the game needs of it (lamps, drive bells, berths, waiting points, moving parts, a flare) in
the Unreal frame (tools/space.py meshes turns it into data/space/meshes.json).
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402

import astra_bpy as A  # noqa: E402
import ship3_build as B  # noqa: E402
import ship3_geo as G  # noqa: E402
import ship3_kit as K  # noqa: E402
import ship3_palette as PAL  # noqa: E402
import ship3_preview as PV  # noqa: E402
import ship3_render as R  # noqa: E402
import space3_common as SC  # noqa: E402
from shipgen3 import FACTION_SLOTS, compact, unreal_bounds  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
BUDGET = {"place": 2_500_000, "part": 800_000, "vessel": 500_000, "rock": 80_000, "prop": 40_000}

# the rocks and ores: not a faction, three slots of their own (instances made by tools/ue_scripts/import_space_v3.py)
ROCK_PRE = "MI_SPACE_"
ROCK_SLOTS = ["Rock", "Ore", "Ice", "Lights", "Glow", "Nav", "Frame", "Engine", "Plate"]
PAL.PAINT["R"] = {"Rock": ("#574F48", "#9A7A56", 0.0, 0.66, 0.94), "Ore": ("#6E5A48", "#B49060", 0.0, 0.40, 0.78), "Ice": ("#8FA6AE", "#D6E6EA", 0.0, 0.22, 0.55),
                  "Frame": ("#3B3E42", "#7B7F84", 0.30, 0.30, 0.70), "Engine": ("#6A6C70", "#8A8F96", 0.85, 0.35, 0.55), "Plate": ("#9C927C", "#7B7F84", 0.0, 0.35, 0.75)}
PAL.LIGHTS["R"] = PAL.LIGHTS["G"]
PAL.RADIATOR["R"] = PAL.RADIATOR["G"]
PAL.NAVS["R"] = PAL.NAVS["G"]


# ------------------------------------------------------------------------------------------------------------ registry
def registry() -> dict:
    """name -> spec. Each builder takes (Ctx) and returns a dict: `rec` (space3_common.Rec), `length_m`, and the preview's wishes (see render_views)."""
    reg: dict = {}
    for modname in ("space3_places", "space3_vessels", "space3_props"):
        try:
            mod = __import__(modname)
        except ImportError as ex:
            print(f"[spacegen3] {modname} not available: {ex}")
            continue
        reg.update(mod.REGISTRY)
    return reg


def short(name: str) -> str:
    parts = name.split("_")
    return "_".join(parts[2:]) if len(parts) > 2 else name


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out_dir": os.path.join(ROOT, "art", "export", "space_v3"), "only": None, "detail": 1.0, "seed": 0, "export": True, "preview": None,
           "views": ["three_quarter", "closeup", "top", "sil"], "samples": 36, "report": False, "size": (1600, 900), "tag": ""}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            out["only"] = set(argv[i + 1].split(","))
            i += 1
        elif a == "--detail":
            out["detail"] = float(argv[i + 1])
            i += 1
        elif a == "--seed":
            out["seed"] = int(argv[i + 1])
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
        elif a == "--size":
            out["size"] = tuple(int(x) for x in argv[i + 1].split("x"))
            i += 1
        elif a == "--tag":
            out["tag"] = argv[i + 1]
            i += 1
        elif a == "--report":
            out["report"] = True
        elif not a.startswith("--"):
            out["out_dir"] = a
        i += 1
    return out


def slots_for(fac: str) -> list:
    if fac == "R":
        return [ROCK_PRE + p for p in ROCK_SLOTS]
    if fac == "AG":                                      # a place built by the Navy for Guild trade: both palettes
        return [f"MI_HULL_A_{p}" for p in FACTION_SLOTS["A"]] + [f"MI_HULL_G_{p}" for p in FACTION_SLOTS["G"] if p not in FACTION_SLOTS["A"]] + ["MI_HULL_G_Lights"]
    return [f"MI_HULL_{fac}_{p}" for p in FACTION_SLOTS[fac]]


def prefix_for(fac: str) -> str:
    return ROCK_PRE if fac == "R" else ("MI_HULL_A_" if fac == "AG" else f"MI_HULL_{fac}_")


# ------------------------------------------------------------------------------------------------------------ previews
def preview_materials(fac: str) -> None:
    facs = ("A", "G") if fac == "AG" else (("G",) if fac == "R" else (fac,))
    for f in facs:
        PV.make_materials(f)
    for part in ("Rock", "Ore", "Ice"):                                  # the rocks of the belt show in any mesh (the ore in a hopper)
        PV.hull_material(ROCK_PRE + part, "R", part, tone_amount=0.5, grime_gain=0.6)
    if fac == "R":
        PV.light_material(ROCK_PRE + "Lights", "G")
        PV.glow_material(ROCK_PRE + "Glow", "G", PAL.LIGHTS["G"][3] * 0.6)
        PV.nav_material(ROCK_PRE + "Nav")
        for part in ("Frame", "Engine", "Plate"):
            PV.hull_material(ROCK_PRE + part, "R", part)


def silhouette(obj, pts, d, path, size, lens=50.0, margin=0.06):
    """The mesh as a black shape on a pale sky, orthographic-ish: how it reads at a distance (docs/ricerca/08 §7: a readable silhouette)."""
    sc = bpy.context.scene
    old_world = sc.world
    saved = [list(obj.data.materials)]
    mat = bpy.data.materials.new("sil")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.01, 0.01, 0.012, 1.0)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    w = bpy.data.worlds.new("silworld")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.78, 0.82, 0.86, 1.0)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sc.world = w
    for i in range(len(obj.data.materials)):
        obj.data.materials[i] = mat
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o, do_unlink=True)
    cam, tgt = PV.fit_camera("cam", pts, d, lens=lens, aspect=size[0] / size[1], margin=margin)
    PV.render(cam, path)
    for i, m in enumerate(saved[0]):
        obj.data.materials[i] = m
    sc.world = old_world
    bpy.data.objects.remove(cam, do_unlink=True)


def render_views(name: str, spec: dict, info: dict, obj, args: dict) -> None:
    outd = args["preview"]
    os.makedirs(outd, exist_ok=True)
    w, h = args["size"]
    sn = name[3:] if name.startswith("SM_") else name
    tag = args.get("tag", "")
    preview_materials(spec["fac"])
    PV.configure(w, h, args["samples"], exposure=info.get("exposure", 0.0))
    pts = R.verts_world(obj)
    side = info.get("light_side", 1.0)
    for view in args["views"]:
        if view == "three_quarter":
            cam = info.get("cam") or [-48.0, 18.0, 60.0]
            d = R.view_dir(cam[0], cam[1])
            R.shot("cam", pts, d, os.path.join(outd, f"{sn}_three_quarter{tag}.jpg"), (w, h), lens=cam[2] if len(cam) > 2 else 60.0, side=side,
                   key_el=cam[3] if len(cam) > 3 else 28.0, margin=info.get("margin", 0.05))
        elif view == "extra":
            for i, cam in enumerate(info.get("cams", [])):
                d = R.view_dir(cam[0], cam[1])
                R.shot("cam", pts, d, os.path.join(outd, f"{sn}_view{i}{tag}.jpg"), (w, h), lens=cam[2] if len(cam) > 2 else 60.0, side=side,
                       key_el=cam[3] if len(cam) > 3 else 28.0, margin=info.get("margin", 0.05))
        elif view in ("top", "side"):
            el, az = (84.0, -90.0) if view == "top" else (3.0, 0.0)
            d = R.view_dir(az, el)
            R.shot("cam", pts, d, os.path.join(outd, f"{sn}_{view}{tag}.jpg"), (w, h), lens=info.get("lens_flat", 80.0), side=side, key_el=40.0, margin=0.04)
        elif view == "closeup":
            for i, cu in enumerate(info.get("closeups", [])):
                tgt = np.array(cu["target"], float)
                nrm = G.norm(np.array(cu["normal"], float))
                dist = cu.get("distance", 110.0)
                span = cu.get("span", 50.0)
                cam = PV.camera("cam", tuple(tgt + nrm * dist), tuple(tgt), PV.close_up_lens(dist, span, 36.0), clip_end=max(60000.0, dist * 4))
                PV.rig(cam.location, tgt, key_az=cu.get("key_az", 70.0), key_el=cu.get("key_el", 36.0), side=cu.get("side", side))
                PV.render(cam, os.path.join(outd, f"{sn}_closeup_{cu.get('name', i)}{tag}.jpg"))
                bpy.data.objects.remove(cam, do_unlink=True)
        elif view == "sil":
            for az, el, nm in ((0.0, 2.0, "side"), (-90.0, 85.0, "top")):
                silhouette(obj, pts, R.view_dir(az, el), os.path.join(outd, f"{sn}_sil_{nm}{tag}.jpg"), (w, h), lens=info.get("lens_flat", 80.0))
            PV.rig((0, 0, 0), (1, 0, 0))                    # the lights are back for the next view


# ------------------------------------------------------------------------------------------------------------------ build
def build_mesh(name: str, spec: dict, args: dict) -> dict:
    fac = spec["fac"]
    g = G.Geo(slots_for(fac))
    c = K.Ctx(g, np.random.default_rng(spec["seed"] + args["seed"]), prefix_for(fac), detail=args["detail"] * spec.get("detail", 1.0))
    t0 = time.time()
    info = spec["build"](c)
    info["build_s"] = round(time.time() - t0, 1)
    return {"g": g, "c": c, "info": info}


def main() -> None:
    args = parse_args()
    reg = registry()
    names = [n for n in reg if not args["only"] or n in args["only"] or short(n) in args["only"]]
    out_dir = args["out_dir"]
    if args["export"]:
        os.makedirs(out_dir, exist_ok=True)
    A.reset_scene()
    manifest: dict = {"version": 1, "generator": "art/blender/spacegen3.py", "frame": "Blender frame in the FBX (x forward, z up, y mirrored on import: Unreal +Y is "
                      "Blender -Y); bounds, lamps, bells, docks, holds and parts below are in the Unreal frame, metres", "meshes": {}}
    if os.path.exists(os.path.join(out_dir, "manifest.json")) and args["only"]:       # a partial run keeps the others' entries
        try:
            manifest["meshes"] = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8")).get("meshes", {})
        except (OSError, ValueError):
            pass
    for name in names:
        spec = reg[name]
        t0 = time.time()
        res = build_mesh(name, spec, args)
        g, info = res["g"], res["info"]
        asm = g.assemble()
        asm, mats = compact(asm, g.mats)
        obj = B.build_object(name, asm, mats)
        st = B.stats(obj)
        if args["export"]:
            A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        V = asm["V"]
        ub = unreal_bounds(V)
        entry = {"file": name + ".fbx", "tris": st["tris"], "verts": st["verts"], "size_m": st["size_m"], "bounds_m": ub, "slots": mats, "nanite": True,
                 "class": spec["cls"], "detail_kinds": g.stats(), "build_s": info.get("build_s"), "min": ub["min"], "max": ub["max"],
                 "length": round(float(info.get("length_m", V[:, 0].max() - V[:, 0].min())), 1)}
        rec = info.get("rec")
        if rec is not None:
            entry.update(rec.to_json())
        for k in ("notes", "checks"):
            if k in info:
                entry[k] = info[k]
        manifest["meshes"][name] = entry
        budget = BUDGET.get(spec["cls"], 1_000_000)
        flag = "" if st["tris"] <= budget else f"  OVER BUDGET ({budget:,})"
        print(f"{name}: {st['tris']:,} tris, {len(mats)} slots, {st['size_m']} m, {time.time() - t0:.1f}s{flag}", flush=True)
        print("    " + ", ".join(f"{k} {v:,}" for k, v in list(g.stats().items())[:7]), flush=True)
        if args["preview"]:
            pobj = obj
            if spec.get("with"):                                         # a place and its moving parts, put together to be looked at (never exported)
                gp = G.Geo(list(g.mats))
                SC.stamp(gp, g)
                for pname, off in spec["with"]:
                    SC.stamp(gp, build_mesh(pname, reg[pname], args)["g"], origin=off)
                pasm, pmats = compact(gp.assemble(), gp.mats)
                pobj = B.build_object(name + "_all", pasm, pmats)
                obj.hide_render = True
            render_views(name, spec, info, pobj, args)
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in list(bpy.data.meshes):
            bpy.data.meshes.remove(m)
    if args["export"]:
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)
        print("manifest:", os.path.join(out_dir, "manifest.json"))
    if args["report"]:
        for n, e in manifest["meshes"].items():
            print(f"  {n:34s} {e['tris']:>10,d} tris  {e['size_m']}  lamps {len(e.get('lamps', []))} docks {len(e.get('docks', []))}")
    print("SPACEGEN3_OK")


if __name__ == "__main__":
    main()
