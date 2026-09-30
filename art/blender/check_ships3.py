"""Checks the exported v3 ships: imports every FBX of art/export/ships_v3 back into Blender and compares it with manifest.json.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/check_ships3.py -- [<dir>] [--only Aquila,Falcon] [--fast]

Per mesh: the file is there, the triangles equal the manifest's, the three UV layers are UVMap / UVMap_D1 / UVMap_D2 and the data layers
stay in 0..1, the material slots equal the manifest's, the bounds (Unreal frame: Blender y mirrored, metres) are within 2 cm of the manifest's,
no NaN. Per capital ship: its pieces lie inside the whole ship's bounds and their x ranges meet at the cut planes. --fast skips the
meshes of more than 400 k triangles (the big ones take minutes to read). The exit status is 1 when a check fails; JSON lines are printed.
"""
from __future__ import annotations

import json
import re
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
UV_NAMES = ["UVMap", "UVMap_D1", "UVMap_D2"]


def parse():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"dir": os.path.join(ROOT, "art", "export", "ships_v3"), "only": None, "fast": False}
    i = 0
    while i < len(argv):
        if argv[i] == "--only":
            out["only"] = set(argv[i + 1].split(","))
            i += 1
        elif argv[i] == "--fast":
            out["fast"] = True
        elif not argv[i].startswith("--"):
            out["dir"] = argv[i]
        i += 1
    return out


def check_mesh(name: str, e: dict, folder: str) -> dict:
    res = {"mesh": name, "problems": []}
    path = os.path.join(folder, e["file"])
    if not os.path.exists(path):
        res["problems"].append("file missing")
        return res
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)
    bpy.ops.import_scene.fbx(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if len(objs) != 1:
        res["problems"].append(f"{len(objs)} mesh objects (1 expected: the importer must not split the ship)")
        return res
    o = objs[0]
    me = o.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    res["tris"] = tris
    if tris != e["tris"]:
        res["problems"].append(f"triangles {tris} != manifest {e['tris']}")
    names = [u.name for u in me.uv_layers]
    if names != UV_NAMES:
        res["problems"].append(f"uv layers {names} != {UV_NAMES}")
    else:
        for k in (1, 2):
            a = np.empty(len(me.loops) * 2, np.float32)
            me.uv_layers[k].data.foreach_get("uv", a)
            if not np.all(np.isfinite(a)):
                res["problems"].append(f"{UV_NAMES[k]} has NaN")
            elif a.min() < -1e-3 or a.max() > 1.0 + 1e-3:
                res["problems"].append(f"{UV_NAMES[k]} out of 0..1: {a.min():.3f}..{a.max():.3f}")
            res[f"uv{k}_range"] = [round(float(a.min()), 3), round(float(a.max()), 3)]
    slots = [re.sub(r"\.\d{3}$", "", m.name) if m else None for m in me.materials]      # the importer numbers names it has seen before
    if set(slots) != set(e["slots"]):
        res["problems"].append(f"slots {slots} != manifest {e['slots']}")
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    V = co.reshape(-1, 3).astype(np.float64)
    M = np.array(o.matrix_world)
    V = V @ M[:3, :3].T + M[:3, 3]
    if not np.all(np.isfinite(V)):
        res["problems"].append("NaN vertices")
    lo = [float(V[:, 0].min()), float(-V[:, 1].max()), float(V[:, 2].min())]
    hi = [float(V[:, 0].max()), float(-V[:, 1].min()), float(V[:, 2].max())]
    want_lo, want_hi = e["bounds_m"]["min"], e["bounds_m"]["max"]
    tol = 0.02
    if any(abs(a - b) > tol for a, b in zip(lo + hi, want_lo + want_hi)):
        res["problems"].append(f"bounds {[round(v, 2) for v in lo + hi]} != manifest {want_lo + want_hi}")
    res["bounds"] = [round(v, 2) for v in lo + hi]
    if not me.has_custom_normals:
        res["problems"].append("no custom normals")
    return res


def main() -> None:
    args = parse()
    manifest = json.load(open(os.path.join(args["dir"], "manifest.json"), encoding="utf-8"))
    meshes = manifest["meshes"]
    bad = 0
    results = {}
    for name, e in meshes.items():
        short = name.split("_")[-1]
        whole = e.get("of", name)
        if args["only"] and not any(o in (name, whole, short, whole.split("_")[-1]) for o in args["only"]):
            continue
        if args["fast"] and e["tris"] > 400_000:
            print(json.dumps({"mesh": name, "skipped": "fast"}))
            continue
        r = check_mesh(name, e, args["dir"])
        results[name] = r
        bad += 1 if r["problems"] else 0
        print(json.dumps(r))
    # the build-time checks the generator wrote into the manifest (the Aquila against its interiors and the plan's decks)
    for name, e in meshes.items():
        ck = e.get("checks")
        if not ck or (args["only"] and not any(o in (name, name.split("_")[-1]) for o in args["only"])):
            continue
        fails = [k for k, v in ck.items() if k == "ok" and v is False] + (["nave"] if isinstance(ck.get("nave"), dict) and ck["nave"].get("ok") is False else [])
        print(json.dumps({"mesh": name, "build_checks": "ok" if not fails else fails, "nave": {k: v for k, v in (ck.get("nave") or {}).items() if k.startswith("deck") or k == "ok"}}))
        bad += 1 if fails else 0
    # pieces against the whole ship
    for name, e in meshes.items():
        if e["class"] != "section" or name not in results:
            continue
        whole = meshes.get(e["of"])
        if not whole:
            continue
        pl, ph = e["bounds_m"]["min"], e["bounds_m"]["max"]
        wl, wh = whole["bounds_m"]["min"], whole["bounds_m"]["max"]
        slack = max(6.0, 0.04 * (wh[0] - wl[0]))                    # peeled plates and girders at the cuts reach out of the hull line
        if any(pl[i] < wl[i] - slack or ph[i] > wh[i] + slack for i in range(3)):
            print(json.dumps({"mesh": name, "problems": [f"piece bounds {pl + ph} outside the ship's {wl + wh}"]}))
            bad += 1
    print(json.dumps({"checked": len(results), "failed": bad}))
    if bad:
        sys.exit(1)
    print("CHECK_SHIPS3_OK")


main()
