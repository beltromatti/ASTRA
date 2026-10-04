"""ASN Aquila interior kit (ARTE-INTERNI-2): what a mesh costs, measured, before and after a change. Run inside Blender:

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_measure.py -- --json <out.json> [--only A,B,Sign_*] [--rooms]

For every mesh it builds (the same registry and builders as ship_kit.py: `--only` takes the same names, `--rooms` builds only the room prefabs) it writes the triangles, the triangles
of every material slot, the size and the geometry signature (`astra_bpy.geometry_signature`, the one the kit manifest carries as "sig": two builds with the same signature are
the same FBX for the importer). `ship_cost.py` (pure Python) turns two of these files into the per-deck table (triangles, slots, texture MB) and lists the meshes whose signature changed
(= what the lead has to re-import). No FBX is written.
"""
from __future__ import annotations

import json
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_kit as K  # noqa: E402
import ship_lib as SL  # noqa: E402


def slot_tris(obj) -> dict[str, int]:
    """Triangles per material slot name (a polygon of n corners is n - 2 triangles, as the FBX export triangulates it)."""
    me = obj.data
    names = [m.name if m else "" for m in me.materials]
    out: dict[str, int] = {n: 0 for n in names}
    for p in me.polygons:
        i = p.material_index
        out[names[i] if i < len(names) else ""] = out.get(names[i] if i < len(names) else "", 0) + len(p.vertices) - 2
    return out


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_path, only, rooms_only = None, None, False
    i = 0
    while i < len(argv):
        if argv[i] == "--json":
            out_path = argv[i + 1]
            i += 1
        elif argv[i] == "--only":
            only = argv[i + 1].split(",")
            i += 1
        elif argv[i] == "--rooms":
            rooms_only = True
        i += 1
    plan = K.load_plan(None)
    A.reset_scene()
    SL.load_labels()
    reg = K.registry(K.needed_meshes(plan))
    names = K.select(reg, only)
    if rooms_only:
        names = [n for n in names if reg[n][0] == "room"]
    res: dict[str, dict] = {}
    objs = {}
    t0 = time.time()
    for n in names:                                         # (ship_kit.py builds every mesh first and takes the signatures at the end, after the exports: a mesh's signature depends on the
        obj = K.build_mesh(n, reg[n])                       # meshes built after it, so the signatures are taken here the same way, once everything exists)
        objs[n] = obj
        st = A.stats(obj)
        res[n] = {"kind": reg[n][0], "tris": st["tris"], "size_m": st["size_m"], "slots": slot_tris(obj)}
        if reg[n][0] == "room":
            res[n]["prefab"] = reg[n][1]
    for n in names:
        res[n]["sig"] = A.geometry_signature(objs[n])
    print(f"measured {len(res)} meshes in {time.time() - t0:.1f}s")
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"meshes": res}, fh, indent=0, sort_keys=True)
        print("wrote", out_path)


if __name__ == "__main__":
    main()
