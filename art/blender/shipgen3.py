"""ASTRA ships v3 — build, export and preview.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen3.py -- [<out_dir>] [options]

  <out_dir>          FBX files + manifest.json (default art/export/ships_v3, not in git)
Options:
  --only a,b         build only these ships (short names: Aquila, Praetorian, Vigilant, Acheron, Styx, Lethe, Freighter, Watch,
                     Falcon, Hammer, Wasp, Harpy; or full asset names)
  --detail 0.6       thin out the scattered details (1.0 = full); the triangle counts follow
  --seed N           add N to every ship's seed (other dice, same designs)
  --no-export        build (and preview) without writing FBX files
  --no-pieces        skip the section pieces of the capital ships
  --preview <dir>    render the previews of each ship into <dir> (Eevee): three-quarter view, a "x300 zoom" patch of hull, the
                     pieces pulled apart; --views three_quarter,closeup,pieces to choose; --samples N; --hdr uses the 8K Aurelia sky
  --report           print the budget table at the end

Exported meshes (origin = the ship's origin, x forward, the FBX export mirrors y as usual; opaque, Nanite in Unreal):
  SM_SHIP_<FACTION>_<Name>               the whole ship (slots MI_HULL_<A|M|G>_<Part>)
  SM_SHIP_<FACTION>_<Name>_Sec<Bow|Mid|Stern>   the pieces of a capital ship, in the same frame, with burnt cut faces
  SM_CRAFT_*, SM_STATION_*               craft and the station
manifest.json lists per mesh: triangles, size, bounds, slots, and for the pieces the cut planes, cut faces, section limits, pivots.
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
import ship3_preview as PV  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))
SEC_NAMES = ("Bow", "Mid", "Stern")
BUDGET_CAPITAL, BUDGET_CRAFT = 3_000_000, 150_000

FACTION_SLOTS = {
    "A": ["Plate", "Frame", "Livery", "Trim", "Marking", "Engine", "Glow", "Lights", "Nav", "Radiator", "Cut", "Glass"],
    "M": ["Plate", "Frame", "Livery", "Trim", "Marking", "Engine", "Glow", "Lights", "Nav", "Radiator", "Cut", "Glass"],
    "G": ["Plate", "Frame", "Livery", "Trim", "Marking", "Engine", "Glow", "Lights", "Nav", "Radiator", "Cut", "Blue", "Green"],
}


# ------------------------------------------------------------------------------------------------------------ registry
def registry() -> dict:
    """name -> spec. Each builder takes (Ctx) and returns a dict with the loft/cuts information (see ship3_astra.Aquila)."""
    import ship3_astra as AS
    reg = {
        "SM_SHIP_ASTRA_Aquila": dict(fac="A", seed=1, cls="capital", build=AS.build_aquila, sections=True),
    }
    try:
        import ship3_astra2 as AS2
        reg.update({
            "SM_SHIP_ASTRA_Praetorian": dict(fac="A", seed=7, cls="capital", build=AS2.build_praetorian, sections=True),
            "SM_SHIP_ASTRA_Vigilant": dict(fac="A", seed=3, cls="capital", build=AS2.build_vigilant, sections=True),
        })
    except ImportError:
        pass
    try:
        import ship3_mandate as MD
        reg.update({
            "SM_SHIP_MANDATE_Acheron": dict(fac="M", seed=11, cls="capital", build=MD.build_acheron, sections=True),
            "SM_SHIP_MANDATE_Styx": dict(fac="M", seed=13, cls="capital", build=MD.build_styx, sections=True),
            "SM_SHIP_MANDATE_Lethe": dict(fac="M", seed=17, cls="capital", build=MD.build_lethe, sections=True),
        })
    except ImportError:
        pass
    try:
        import ship3_misc as MS
        reg.update({
            "SM_SHIP_GUILD_Freighter": dict(fac="G", seed=5, cls="capital", build=MS.build_freighter, sections=True),
            "SM_STATION_ASTRA_Watch": dict(fac="A", seed=31, cls="station", build=MS.build_watch, sections=False),
        })
    except ImportError:
        pass
    try:
        import ship3_craft as CR
        reg.update({
            "SM_CRAFT_ASTRA_Falcon": dict(fac="A", seed=21, cls="craft", build=CR.build_falcon, sections=False),
            "SM_CRAFT_ASTRA_Hammer": dict(fac="A", seed=23, cls="craft", build=CR.build_hammer, sections=False),
            "SM_CRAFT_ASTRA_Wasp": dict(fac="A", seed=25, cls="craft", build=CR.build_wasp, sections=False),
            "SM_CRAFT_MANDATE_Harpy": dict(fac="M", seed=27, cls="craft", build=CR.build_harpy, sections=False),
        })
    except ImportError:
        pass
    return reg


def short(name: str) -> str:
    return name.split("_")[-1]


# ------------------------------------------------------------------------------------------------------------------ cli
def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out_dir": os.path.join(ROOT, "art", "export", "ships_v3"), "only": None, "detail": 1.0, "seed": 0, "export": True, "pieces": True,
           "preview": None, "views": ["three_quarter", "closeup", "pieces"], "samples": 40, "hdr": False, "report": False, "size": (1600, 900)}
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
        elif a == "--no-pieces":
            out["pieces"] = False
        elif a == "--preview":
            out["preview"] = argv[i + 1]
            i += 1
        elif a == "--views":
            out["views"] = argv[i + 1].split(",")
            i += 1
        elif a == "--samples":
            out["samples"] = int(argv[i + 1])
            i += 1
        elif a == "--hdr":
            out["hdr"] = True
        elif a == "--report":
            out["report"] = True
        elif not a.startswith("--"):
            out["out_dir"] = a
        i += 1
    return out


# ---------------------------------------------------------------------------------------------------------------- build
def compact(asm: dict, mats: list[str]):
    """Keep only the material slots the faces use (the whole ship has no cut-face slot)."""
    used = np.unique(asm["M"])
    remap = np.full(len(mats), -1, np.int16)
    remap[used] = np.arange(len(used), dtype=np.int16)
    asm = dict(asm)
    asm["M"] = remap[asm["M"]]
    return asm, [mats[i] for i in used]


def unreal_bounds(V: np.ndarray) -> dict:
    """Bounding box in the Unreal frame (metres): Blender +Y is Unreal -Y."""
    lo = [float(V[:, 0].min()), float(-V[:, 1].max()), float(V[:, 2].min())]
    hi = [float(V[:, 0].max()), float(-V[:, 1].min()), float(V[:, 2].max())]
    return {"min": [round(x, 3) for x in lo], "max": [round(x, 3) for x in hi]}


def build_ship(name: str, spec: dict, args: dict) -> dict:
    fac = spec["fac"]
    g = G.Geo([f"MI_HULL_{fac}_{p}" for p in FACTION_SLOTS[fac]])
    c = K.Ctx(g, np.random.default_rng(spec["seed"] + args["seed"]), f"MI_HULL_{fac}_", detail=args["detail"])
    t0 = time.time()
    info = spec["build"](c)
    info["build_s"] = round(time.time() - t0, 1)
    return {"g": g, "c": c, "info": info}


def export_mesh(obj, out_dir: str, args: dict) -> None:
    if args["export"]:
        A.export_fbx(obj, os.path.join(out_dir, obj.name + ".fbx"))


def main() -> None:
    args = parse_args()
    reg = registry()
    names = [n for n in reg if not args["only"] or n in args["only"] or short(n) in args["only"]]
    out_dir = args["out_dir"]
    if args["export"]:
        os.makedirs(out_dir, exist_ok=True)
    A.reset_scene()
    manifest: dict = {"version": 3, "generator": "art/blender/shipgen3.py", "frame": "Blender frame in the FBX (x forward, z up, y mirrored on "
                      "import: Unreal +Y is Blender -Y); bounds below are in the Unreal frame, metres", "meshes": {}, "budget": {}}
    previews = []
    for name in names:
        spec = reg[name]
        t0 = time.time()
        res = build_ship(name, spec, args)
        g, info = res["g"], res["info"]
        cuts = info.get("cuts") or []
        # ------------------------------------------------------------------------------------------- the whole ship
        asm = g.assemble()
        asm, mats = compact(asm, g.mats)
        obj = B.build_object(name, asm, mats)
        st = B.stats(obj)
        export_mesh(obj, out_dir, args)
        entry = {"file": name + ".fbx", "tris": st["tris"], "verts": st["verts"], "size_m": st["size_m"], "bounds_m": unreal_bounds(asm["V"]),
                 "slots": mats, "nanite": True, "class": spec["cls"], "detail_kinds": g.stats(), "build_s": info.get("build_s")}
        for k in ("length_m", "notes", "checks"):
            if k in info:
                entry[k] = info[k]
        manifest["meshes"][name] = entry
        cap_tris = g.triangles(cap=True)
        print(f"{name}: {st['tris']:,} tris, {len(mats)} slots, {st['size_m']} m, {time.time() - t0:.1f}s")
        # ---------------------------------------------------------------------------------- the section pieces
        pieces = {}
        if spec["sections"] and cuts and args["pieces"]:
            section_of = lambda x, cu=list(cuts): np.where(x > cu[0], 0, np.where(x > cu[1], 1, 2)) if len(cu) == 2 else np.where(x > cu[0], 0, 1)  # noqa: E731
            secs = range(len(cuts) + 1)
            piece_objs = []
            for k in secs:
                pname = f"{name}_Sec{SEC_NAMES[k] if len(cuts) == 2 else ('Bow', 'Stern')[k]}"
                pa = g.assemble(sections={k}, include_caps=True, section_of=section_of)
                if pa is None:
                    continue
                pa, pm = compact(pa, g.mats)
                po = B.build_object(pname, pa, pm)
                ps = B.stats(po)
                export_mesh(po, out_dir, args)
                V = pa["V"]
                cen = V.mean(axis=0)
                manifest["meshes"][pname] = {
                    "file": pname + ".fbx", "tris": ps["tris"], "verts": ps["verts"], "size_m": ps["size_m"], "bounds_m": unreal_bounds(V),
                    "slots": pm, "nanite": True, "class": "section", "of": name, "section": SEC_NAMES[k] if len(cuts) == 2 else ("Bow", "Stern")[k],
                    "pivot_m": [round(float(cen[0]), 3), round(float(-cen[1]), 3), round(float(cen[2]), 3)],
                    "x_range_m": [round(float(V[:, 0].min()), 3), round(float(V[:, 0].max()), 3)],
                    "note": "same frame as the whole ship; pivot_m is the vertex centroid (Unreal frame) for rotating the piece about itself"}
                pieces[pname] = ps["tris"]
                piece_objs.append(po)
            entry["cuts_x_m"] = [float(x) for x in cuts]
            entry["cut_faces"] = [dict(f, center=[f["center"][0], -f["center"][1], f["center"][2]], y=[-f["y"][1], -f["y"][0]]) for f in info.get("cut_faces", [])]
            xs = asm["V"][:, 0]
            cl = [float(x) for x in cuts]
            entry["sections"] = ({"Bow": [cl[0], float(xs.max())], "Mid": [cl[1], cl[0]], "Stern": [float(xs.min()), cl[1]]} if len(cl) == 2 else
                                 {"Bow": [cl[0], float(xs.max())], "Stern": [float(xs.min()), cl[0]]})
            entry["pieces"] = pieces
            entry["tris_pieces"] = sum(pieces.values())
            for po in piece_objs:
                po.hide_render = True
                po.hide_viewport = True
        obj.hide_render = args["preview"] is None
        previews.append((name, spec, obj, info))
        # ---------------------------------------------------------------------------------------------- previews
        if args["preview"]:
            render_previews(name, spec, res, obj, args)
        # free the scene for the next ship
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        for m in list(bpy.data.meshes):
            bpy.data.meshes.remove(m)
    if args["export"]:
        manifest["budget"] = {n: {"tris": e["tris"], "limit": (BUDGET_CRAFT if e["class"] == "craft" else BUDGET_CAPITAL), "ok": e["tris"] <= (BUDGET_CRAFT if e["class"] == "craft" else BUDGET_CAPITAL)}
                              for n, e in manifest["meshes"].items() if e["class"] in ("capital", "craft", "station")}
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=1)
        print("manifest:", os.path.join(out_dir, "manifest.json"))
    if args["report"]:
        for n, e in manifest["meshes"].items():
            print(f"  {n:40s} {e['tris']:>10,d} tris  {e['size_m']}")
    print("SHIPGEN3_OK")


# -------------------------------------------------------------------------------------------------------------- previews
def render_previews(name: str, spec: dict, res: dict, obj, args: dict) -> None:
    """Three-quarter view, a close-up patch and the pieces pulled apart, lit by the orange star with the teal fill."""
    g, info = res["g"], res["info"]
    fac = spec["fac"]
    w, h = args["size"]
    outd = args["preview"]
    os.makedirs(outd, exist_ok=True)
    PV.make_materials(fac)
    star = dict(sun_az=info.get("sun_az", -38.0), sun_el=info.get("sun_el", 30.0), sun=info.get("sun", 3.6), world=0.5)
    PV.aurelia_lighting(**star)
    if args["hdr"]:
        PV.use_hdr_world(0.35)
    PV.configure(w, h, args["samples"])
    V = np.array(obj.bound_box)
    lo, hi = V.min(axis=0), V.max(axis=0)
    cen = (lo + hi) / 2
    R = float(np.linalg.norm(hi - lo)) / 2
    sn = short(name)
    for view in args["views"]:
        if view == "three_quarter":
            az, el = math.radians(info.get("cam_az", -32.0)), math.radians(info.get("cam_el", 20.0))
            d = np.array([math.cos(el) * math.cos(az + math.pi / 2), math.cos(el) * math.sin(az + math.pi / 2) * -1, math.sin(el)])
            dist = R * info.get("cam_dist", 2.05)
            cam = PV.camera("cam", tuple(cen + d * dist), tuple(cen + np.array(info.get("cam_target_off", [0, 0, 0]))), 50.0)
            PV.render(cam, os.path.join(outd, f"{sn}_three_quarter.jpg"))
        elif view == "closeup":
            for i, cu in enumerate(info.get("closeups", [])):
                tgt = np.array(cu["target"], float)
                nrm = G.norm(np.array(cu["normal"], float))
                dist = cu.get("distance", 110.0)
                span = cu.get("span", 50.0)
                cam = PV.camera("cam", tuple(tgt + nrm * dist), tuple(tgt), PV.close_up_lens(dist, span, 36.0))
                PV.render(cam, os.path.join(outd, f"{sn}_closeup_{cu.get('name', i)}.jpg"))
    if "pieces" in args["views"] and info.get("cuts"):
        cuts = info["cuts"]
        section_of = lambda x, cu=list(cuts): np.where(x > cu[0], 0, np.where(x > cu[1], 1, 2)) if len(cu) == 2 else np.where(x > cu[0], 0, 1)  # noqa: E731
        obj.hide_render = True
        gap = info.get("pieces_gap", 0.12) * (hi[0] - lo[0])
        for k in range(len(cuts) + 1):
            pa = g.assemble(sections={k}, include_caps=True, section_of=section_of)
            if pa is None:
                continue
            pa, pm = compact(pa, g.mats)
            po = B.build_object(f"_prev_{k}", pa, pm)
            po.location.x = (len(cuts) / 2.0 - k) * gap
            po.location.y = ((k % 2) - 0.5) * gap * 0.18
            po.location.z = ((k - 1) * 0.35) * gap * 0.08
        cam_d = R * info.get("pieces_dist", 2.3)
        az = math.radians(info.get("pieces_az", 28.0))
        cam = PV.camera("cam", (cen[0] + math.sin(az) * cam_d * 0.6, cen[1] - math.cos(az) * cam_d, cen[2] + R * 0.55), tuple(cen), 50.0)
        PV.render(cam, os.path.join(outd, f"{sn}_pieces.jpg"))


if __name__ == "__main__":
    main()
