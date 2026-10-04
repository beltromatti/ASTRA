"""ABBORDAGGI-3 — the boarding kit (what the decks of a boarded ship are dressed with): the generator. Builds every piece of board_kit_defs.PIECES, checks it, exports the FBX files and
writes data/ship/board_kit.json (the sizes and the triangle counts the game's dressing places by and the bench measures with).

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/board_kit.py -- [<output_dir>] [options]

  <output_dir>        FBX files (default art/export/board, not in git)
Options:
  --only A,B          build only these pieces (keys of board_kit_defs.PIECES; a glob such as wall_* works); the JSON is not written
  --json <file>       where to write the kit's data file (default data/ship/board_kit.json; "-" writes none)
  --no-export         build and check, write no FBX
  --sheet <dir>       render a contact sheet of the pieces into <dir> (Eevee, headless)
  --view <name>       render an assembled view (corridor | room | door) into --sheet's directory (board_kit_view.py)
  --dump <file>       render the C++ dressing itself: the placements the bench's `dress` scenario dumped (tools/boarding.py run --scenario dress --dump <dir>), with --cam x,y,z,yaw[,pitch] (cm: where a Captain
                      stands, which way he looks; as many as wanted) into --sheet's directory (or the FBX directory)

Everything is in the layout frame of the Aquila's kit (X forward, Y to starboard, Z up, metres; the Y mirror of Blender is bridge3_lib's, as for the Aquila's kit). The frames of the pieces
are board_kit_defs.py's.
"""
from __future__ import annotations

import fnmatch
import json
import math
import os
import sys
import time

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as B3  # noqa: E402
import board_kit_defs as D  # noqa: E402
import board_kit_parts as P  # noqa: E402

ROOT = B3.ROOT
DEFAULT_OUT = os.path.join(ROOT, "art", "export", "board")
DEFAULT_JSON = os.path.join(ROOT, "data", "ship", "board_kit.json")
UE_DIR = "/Game/ASTRA/Kit/Board"
TRI_BUDGET = {"wall": 1500, "ceiling": 900, "floor": 400, "opening": 900, "prop": 2400, "body": 1100}      # per piece: what the instances of a deck can afford


def _coarse_text_proto(text: str) -> dict:
    """bridge3_lib.text_proto with the curves at resolution 1: the lettering of a wall is read from metres away, and every glyph costs half the triangles."""
    if text in B3._TEXT_CACHE:
        return B3._TEXT_CACHE[text]
    fc = bpy.data.curves.new("brd_txt", "FONT")
    fc.body = text
    for pth in B3.FONT_CANDIDATES:
        if os.path.exists(pth):
            fc.font = bpy.data.fonts.load(pth)
            break
    fc.size = 1.0
    fc.extrude = 0.0
    fc.resolution_u = 1
    fc.align_x = "CENTER"
    fc.align_y = "CENTER"
    ob = bpy.data.objects.new("brd_txt", fc)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.calc_loop_triangles()
    V = [(v.co.x, v.co.y, v.co.z) for v in me.vertices]
    F = [tuple(t.vertices) for t in me.loop_triangles]
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(fc)
    bpy.data.meshes.remove(me)
    if not V:
        raise RuntimeError(f"text {text!r} produced no geometry")
    xs = [v[0] for v in V]
    ys = [v[1] for v in V]
    proto = {"V": V, "F": F, "width": max(xs) - min(xs), "height": max(ys) - min(ys), "cap": 0.70, "x0": min(xs), "x1": max(xs)}
    B3._TEXT_CACHE[text] = proto
    return proto


B3.text_proto = _coarse_text_proto


def parts() -> B3.Parts:
    b = B3.Parts(bevel=0.005, fine_bevel=0.0)
    b.bevel_segments = 1
    return b


def finish(b: B3.Parts, name: str):
    return b.build(name, uv_meter=1.0, small_uv_meter=0.5)


# the builders: key -> function(Parts)
def _builders() -> dict:
    import board_kit_props as PR
    return {
        "wall_a": lambda b: P.wall_a(b),
        "wall_b": P.wall_b, "wall_c": P.wall_c, "wall_d": P.wall_d, "wall_e": P.wall_e, "wall_f": P.wall_f,
        "wall_motto": lambda b: P.wall_a(b, text=[D.MOTTO]),
        "wall_hold": lambda b: P.wall_a(b, text=["HOLD FAST"]),
        "wall_plain": P.wall_plain, "rib": P.rib, "cornice": P.cornice, "header": P.header,
        "pipes": P.pipes, "tray": P.tray, "lamp": P.lamp, "lamp_dead": P.lamp_dead, "lamp_red": P.lamp_red, "vent": P.vent, "cables": P.cables,
        "floor": P.floor, "threshold": P.threshold, "guide": P.guide, "debris": P.debris,
        "jamb": P.jamb, "door_header": P.door_header, "blast_jamb": P.blast_jamb, "blast_header": P.blast_header, "blast_leaf": P.blast_leaf,
        **PR.builders(),
    }


def tri_count(obj) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def layout_bbox(obj) -> tuple[list[float], list[float]]:
    """The mesh's bounding box in the layout frame, centimetres (Blender's Y is the layout's mirrored)."""
    xs, ys, zs = [], [], []
    for v in obj.data.vertices:
        xs.append(v.co.x)
        ys.append(-v.co.y)
        zs.append(v.co.z)
    return [round(min(xs) * 100, 1), round(min(ys) * 100, 1), round(min(zs) * 100, 1)], [round(max(xs) * 100, 1), round(max(ys) * 100, 1), round(max(zs) * 100, 1)]


def build(only: list[str] | None = None) -> dict:
    """Builds the pieces: key -> {"obj", "tris", "min_cm", "max_cm", "slots", "ms"}. Reports pieces over their budget."""
    A.reset_scene()
    out = {}
    builders = _builders()
    keys = [k for k in D.PIECES if k in builders and (not only or any(fnmatch.fnmatch(k, pat) for pat in only))]
    missing = [k for k in D.PIECES if k not in builders]
    if missing and not only:
        print(f"[board_kit] (not built yet: {', '.join(missing)})")
    for key in keys:
        name, kind, collide, doc = D.PIECES[key]
        t0 = time.time()
        b = parts()
        builders[key](b)
        obj = finish(b, name)
        tris = tri_count(obj)
        lo, hi = layout_bbox(obj)
        out[key] = {"obj": obj, "tris": tris, "min_cm": lo, "max_cm": hi, "slots": [m.name for m in obj.data.materials], "ms": (time.time() - t0) * 1000}
        budget = TRI_BUDGET.get(kind, 2000)
        flag = "" if tris <= budget else f"   OVER BUDGET ({budget})"
        print(f"[board_kit] {name:22s} {kind:8s} {tris:6d} tris  {lo} .. {hi}  slots {out[key]['slots']}{flag}")
    return out


def write_json(built: dict, path: str) -> None:
    """data/ship/board_kit.json: what the game's dressing reads. Only the pieces that were built (a partial build keeps the others' entries)."""
    prev = {}
    if os.path.exists(path):
        try:
            prev = json.load(open(path, encoding="utf-8")).get("pieces", {})
        except (OSError, ValueError):
            prev = {}
    pieces = dict(prev)
    for key, r in built.items():
        name, kind, collide, doc = D.PIECES[key]
        pieces[key] = {"mesh": name, "path": f"{UE_DIR}/{name}.{name}", "frame": kind, "collide": collide, "doc": doc, "tris": r["tris"], "min_cm": r["min_cm"], "max_cm": r["max_cm"], "slots": r["slots"]}
    data = {"version": 1, "generator": "art/blender/board_kit.py", "unreal_dir": UE_DIR, "bay_m": D.BAY_W, "bay_h_m": D.BAY_H, "rib": [D.RIB_W, D.RIB_D, D.RIB_H], "run_m": D.RUN_L, "plate_m": D.PLATE_M,
            "pieces": dict(sorted(pieces.items()))}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")
    print(f"[board_kit] wrote {path}: {len(pieces)} pieces")


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = DEFAULT_OUT
    only = None
    json_path = DEFAULT_JSON
    export = True
    sheet = None
    views: list[str] = []
    dump = None
    cams: list[tuple] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            only = argv[i + 1].split(",")
            json_path = "-" if json_path == DEFAULT_JSON and False else json_path
            i += 1
        elif a == "--json":
            json_path = argv[i + 1]
            i += 1
        elif a == "--no-export":
            export = False
        elif a == "--sheet":
            sheet = argv[i + 1]
            i += 1
        elif a == "--view":
            views.append(argv[i + 1])
            i += 1
        elif a == "--dump":
            dump = argv[i + 1]
            i += 1
        elif a == "--cam":
            cams.append(tuple(float(v) for v in argv[i + 1].split(",")))
            i += 1
        elif not a.startswith("--"):
            out_dir = a
        i += 1
    built = build(only)
    if not built:
        print("[board_kit] nothing built")
        return 1
    if export:
        for key, r in built.items():
            A.export_fbx(r["obj"], os.path.join(out_dir, D.PIECES[key][0] + ".fbx"))
        print(f"[board_kit] exported {len(built)} FBX files to {out_dir}")
    if json_path != "-":
        write_json(built, json_path)
    if sheet or views or dump:
        import board_kit_view as V
        os.makedirs(sheet or out_dir, exist_ok=True)
        if sheet:
            V.sheet(built, os.path.join(sheet, "sheet"))
        for v in views:
            V.render_view(built, v, os.path.join(sheet or out_dir, f"view_{v}"))
        if dump:
            V.dump_view(built, dump, os.path.join(sheet or out_dir, "dress"), cams or [(0.0, 0.0, 165.0, 0.0)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
