"""ASN Aquila interior (ARTE-INTERNI-2): the cost of the rooms per deck, before and after a change. Pure Python, no Blender, no Unreal:

  python3 art/blender/ship_cost.py <measure.json> [<after.json>] [--plan data/ship/aquila_plan.json] [--json out.json] [--changed]

The inputs are the files `ship_measure.py` writes (inside Blender: triangles, the triangles of every material slot and the geometry signature of every mesh) or a kit `manifest.json`
(no per-slot triangles then). With one file it prints, for every deck that has built rooms:

  rooms       the distinct room meshes the deck places, and their triangles (what the deck holds in memory and on disk once: Nanite clusters them)
  slots       the material slots of those meshes added up (what Nanite binds per mesh) and the most any one room has; "mats" = the distinct materials the deck's rooms use
  texture MB  the 1K sets behind those materials (data/ship/room_materials.json: a set = base colour BC1 0.5 B/px + normal BC5 1 B/px + ORM BC1 0.5 B/px, mips included = 2.67 MB),
              each counted once per deck: what the deck's rooms need resident (the shared bridge sets and the label atlas are the same on every deck and are not counted)
  placed      the triangles of every placed room instance if all were in view (the ceiling of the render cost)

With two files it prints both side by side, the deltas, and the meshes whose signature changed (what build_ship_interior.py re-imports: `--changed` lists them all).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_plan as P  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SET_MB = 1024 * 1024 * (0.5 + 1.0 + 0.5) * (4.0 / 3.0) / (1024 * 1024)     # one 1K set, mips included (a 2K set would be four times that)
MATERIALS = os.path.join(ROOT, "data", "ship", "room_materials.json")


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    out = {}
    for n, m in d.get("meshes", d).items():
        slots = m.get("slots", [])
        if isinstance(slots, list):
            slots = {s: 0 for s in slots}
        out[n] = {"kind": m.get("kind", ""), "tris": int(m["tris"]), "slots": slots, "sig": m.get("sig", ""), "prefab": m.get("prefab", "")}
    return out


def material_sets() -> dict[str, str]:
    with open(MATERIALS, encoding="utf-8") as fh:
        return {n: e["set"] for n, e in json.load(fh)["materials"].items()}


def deck_rows(plan: dict, meas: dict) -> dict:
    sets = material_sets()
    rows = {}
    for dk, pls in plan["placements"].items():
        rooms = {}
        placed_tris = 0
        for p in pls:
            if p["cls"] != "room" or p["mesh"] not in meas:
                continue
            rooms[p["mesh"]] = rooms.get(p["mesh"], 0) + 1
            placed_tris += meas[p["mesh"]]["tris"]
        if not rooms:
            continue
        mats = set()
        slot_sum = 0
        top = ("", 0)
        for m in rooms:
            sl = meas[m]["slots"]
            slot_sum += len(sl)
            mats.update(sl)
            if len(sl) > top[1]:
                top = (m[len("SM_SHIP_"):], len(sl))
        tex = {sets[s] for s in mats if s in sets}
        rows[int(dk)] = {"rooms": len(rooms), "tris": sum(meas[m]["tris"] for m in rooms), "slots": slot_sum, "max_slots": top, "mats": len(mats), "sets": len(tex),
                         "tex_mb": round(len(tex) * SET_MB, 1), "placed_tris": placed_tris, "set_names": sorted(tex)}
    return rows


def fmt_table(rows: dict, title: str) -> list[str]:
    out = [title, f"{'deck':>4} {'rooms':>5} {'tris':>10} {'slots':>6} {'mats':>5} {'sets':>5} {'tex MB':>7} {'most slots':>16} {'placed tris':>12}"]
    tot = {"rooms": 0, "tris": 0, "slots": 0}
    for dk in sorted(rows):
        r = rows[dk]
        out.append(f"{dk:>4} {r['rooms']:>5} {r['tris']:>10,} {r['slots']:>6} {r['mats']:>5} {r['sets']:>5} {r['tex_mb']:>7.1f} {r['max_slots'][0][:12] + ' ' + str(r['max_slots'][1]):>16} {r['placed_tris']:>12,}")
        for k in tot:
            tot[k] += r[k]
    out.append(f"{'all':>4} {tot['rooms']:>5} {tot['tris']:>10,} {tot['slots']:>6}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("before")
    ap.add_argument("after", nargs="?")
    ap.add_argument("--plan", default=P.PLAN_PATH)
    ap.add_argument("--json")
    ap.add_argument("--changed", action="store_true")
    args = ap.parse_args()
    plan = P.load(args.plan)
    a = load(args.before)
    ra = deck_rows(plan, a)
    print("\n".join(fmt_table(ra, f"BEFORE ({os.path.basename(args.before)}): {len(a)} meshes")))
    res = {"before": ra}
    if args.after:
        b = load(args.after)
        rb = deck_rows(plan, b)
        print()
        print("\n".join(fmt_table(rb, f"AFTER ({os.path.basename(args.after)}): {len(b)} meshes")))
        print("\ndeltas per deck (after - before):")
        print(f"{'deck':>4} {'tris':>10} {'slots':>7} {'mats':>6} {'tex MB':>8}")
        for dk in sorted(set(ra) | set(rb)):
            x, y = ra.get(dk, {}), rb.get(dk, {})
            print(f"{dk:>4} {y.get('tris', 0) - x.get('tris', 0):>+10,} {y.get('slots', 0) - x.get('slots', 0):>+7} {y.get('mats', 0) - x.get('mats', 0):>+6} {y.get('tex_mb', 0) - x.get('tex_mb', 0):>+8.1f}")
        changed = sorted(n for n in b if n in a and a[n]["sig"] != b[n]["sig"])
        added = sorted(n for n in b if n not in a)
        gone = sorted(n for n in a if n not in b)
        by_kind: dict[str, int] = {}
        for n in changed + added:
            by_kind[b[n]["kind"]] = by_kind.get(b[n]["kind"], 0) + 1
        print(f"\nmeshes with a different signature: {len(changed)} (+ {len(added)} new, {len(gone)} gone) of {len(b)}; by kind: {by_kind}")
        rooms_changed = [n for n in changed if b[n]["kind"] == "room"]
        print(f"room meshes changed: {len(rooms_changed)} of {sum(1 for n in b if b[n]['kind'] == 'room')}")
        if args.changed:
            for n in changed:
                x, y = a[n], b[n]
                print(f"  {n}: tris {x['tris']} -> {y['tris']}, slots {len(x['slots'])} -> {len(y['slots'])}")
            for n in added:
                print(f"  {n}: NEW {b[n]['tris']} tris, {len(b[n]['slots'])} slots")
            for n in gone:
                print(f"  {n}: GONE")
        res.update({"after": rb, "changed": changed, "added": added, "gone": gone})
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
