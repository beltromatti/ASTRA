"""ASN Aquila interior kit (ARTE-INTERNI-2): where do a room's triangles go? Builds the rooms you name with every call of a kit builder counted (the furniture, decor, plant, surface and shell functions: any
function of a ship_* module whose first parameter is the builder `b`; the outermost call counts, the pieces inside it do not), then prints the rooms' cost by function: how many calls, the triangles
they added (the triangles of the four groups, scaled by what the bevel made of each group in the finished mesh), the share of the room. A prop that costs 5 000 triangles and stands six
times is the first thing to slim; a shell that costs a third of a room is a different conversation.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_profile.py -- Garden,Cabins [--top 25] [--json out.json] [--deep]
(names are meshes without the SM_SHIP_ prefix, or a glob; --deep also counts the calls nested inside another counted call, so the shares overlap). The estimate is within a few per cent of
ship_measure.py's real triangles for the room as a whole; per function it is good enough to rank.
"""
from __future__ import annotations

import fnmatch
import functools
import importlib
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_lib as SL  # noqa: E402

GROUPS = ("body", "fine", "soft", "emit")
PROF: dict = {}                                    # function name -> [calls, triangles per group (before the bevel)]
TOTAL = [0, 0, 0, 0]                               # the triangles of the four groups when the room is built (before the bevel)
_DEPTH = [0]
DEEP = [False]
# the modules whose functions are pieces of a room (importing any other ship_* module can run its probes and rewrite data files: the hull probes do)
PIECES = ("ship_rooms", "ship_shell", "ship_walls", "ship_furniture", "ship_furniture2", "ship_furniture3", "ship_furniture4", "ship_furniture5", "ship_furniture6", "ship_furniture7",
          "ship_furniture8", "ship_furniture9", "ship_furn2", "ship_furn3", "ship_furn4", "ship_decor", "ship_decor2", "ship_decor_salon", "ship_plants", "ship_surfaces", "ship_cabin",
          "ship_stock", "ship_suits", "ship_wet", "ship_med_bed")


def _faces(b) -> list[int]:
    return [len(getattr(b, g).bm.faces) if hasattr(b, g) else 0 for g in GROUPS]


def _tris(b, before: list[int], after: list[int]) -> list[int]:
    """The triangles (before the bevel) of the faces added between two face counts: a quad is two, a triangle of a scanned plant one."""
    out = []
    for i, g in enumerate(GROUPS):
        n = 0
        if hasattr(b, g) and after[i] > before[i]:
            faces = getattr(b, g).bm.faces
            faces.ensure_lookup_table()
            for k in range(before[i], after[i]):
                n += len(faces[k].verts) - 2
        out.append(n)
    return out


def _wrap(fn, label: str):
    @functools.wraps(fn)
    def wrapper(b, *args, **kw):
        if not hasattr(b, "body") or (_DEPTH[0] and not DEEP[0]):
            return fn(b, *args, **kw)
        before = _faces(b)
        _DEPTH[0] += 1
        try:
            return fn(b, *args, **kw)
        finally:
            _DEPTH[0] -= 1
            added = _tris(b, before, _faces(b))
            ent = PROF.setdefault(label, [0, [0, 0, 0, 0]])
            ent[0] += 1
            for i in range(4):
                ent[1][i] += added[i]
    wrapper._profiled = fn
    return wrapper


def _patch() -> None:
    """Wrap the builder functions of every ship_* module (not the infrastructure), and rebind the names other modules imported from them."""
    swapped: dict = {}
    for name in PIECES:
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        for attr, fn in list(vars(mod).items()):
            if not inspect.isfunction(fn) or fn.__module__ != name or attr.startswith("_") or hasattr(fn, "_profiled"):
                continue
            try:
                first = next(iter(inspect.signature(fn).parameters), "")
            except (TypeError, ValueError):
                continue
            if first not in ("b", "fb") or (name == "ship_rooms" and attr == "place"):          # `place` is not a piece: the function it places is
                continue
            w = _wrap(fn, f"{name[5:]}.{attr}")
            setattr(mod, attr, w)
            swapped[id(fn)] = (fn, w)
    # `from ship_x import fn` bindings made earlier: rebind them
    for m in list(sys.modules.values()):
        if m is None:
            continue
        for attr, val in list(getattr(m, "__dict__", {}).items()):
            hit = swapped.get(id(val)) if inspect.isfunction(val) else None
            if hit and hit[0] is val:
                try:
                    setattr(m, attr, hit[1])
                except Exception:
                    pass
    # the build step: how many faces the room holds when it is built
    orig = SL.SParts.build

    def build(self, name, uv_meter=1.0):
        TOTAL[:] = _tris(self, [0, 0, 0, 0], _faces(self))
        return orig(self, name, uv_meter)
    SL.SParts.build = build


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 25
    out = argv[argv.index("--json") + 1] if "--json" in argv else None
    DEEP[0] = "--deep" in argv
    names = [a for a in argv if not a.startswith("--") and not a.isdigit() and a != out]
    A.reset_scene()
    SL.load_labels()
    import ship_kit as K
    _patch()
    plan = K.load_plan(None)
    reg = K.registry(K.needed_meshes(plan))
    pats = [x if x.startswith("SM_SHIP_") else "SM_SHIP_" + x for n in names for x in n.split(",")]
    todo = [n for n in sorted(reg) if any(fnmatch.fnmatch(n, p) for p in pats)]
    report = {}
    for name in todo:
        PROF.clear()
        pre_groups: dict = {}
        joined = A.join

        def join(objs, nm, _pre=pre_groups):
            for o in objs:
                tag = o.name.rsplit("_", 1)[-1].split(".")[0]
                _pre[tag] = _pre.get(tag, 0) + A.stats(o)["tris"]
            return joined(objs, nm)
        A.join = join
        try:
            obj = K.build_mesh(name, reg[name])
        finally:
            A.join = joined
        tris = A.stats(obj)["tris"]
        # the group factors: finished triangles over the triangles that were put in (the bevel turns a box of 12 into ~45)
        factor = [(pre_groups.get(g, 0) / TOTAL[i]) if TOTAL[i] else 0.0 for i, g in enumerate(GROUPS)]
        print("  group factors (finished triangles per triangle put in):", {g: round(f, 2) for g, f in zip(GROUPS, factor)}, " put in:", TOTAL, " finished:", [pre_groups.get(g, 0) for g in GROUPS])
        rows = [(sum(f * v for f, v in zip(factor, d)), piece, cnt) for piece, (cnt, d) in PROF.items()]
        if not DEEP[0]:
            recorded = [sum(ent[1][i] for ent in PROF.values()) for i in range(4)]
            direct = sum(f * (TOTAL[i] - recorded[i]) for i, f in enumerate(factor))
            if direct > 0:
                rows.append((direct, "<the room's own boxes and cylinders>", 1))
        rows.sort(reverse=True)
        print(f"\n{name}: {tris} triangles")
        for est, piece, cnt in rows[:top]:
            print(f"  {int(est):7d}  {100.0 * est / max(1, tris):5.1f}%  x{cnt:<3d} {piece}  ({int(est / cnt)} each)")
        report[name] = {"tris": tris, "pieces": {p: {"calls": c, "tris": int(e)} for e, p, c in rows}}
        A.clear_objects()
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
