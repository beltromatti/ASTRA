"""ASN Aquila interior: the budget of every built deck, from the plan and the kit's triangle counts (NAVE-2). Pure Python, no Blender, no Unreal:

  python3 art/blender/ship_budget.py [--stats <file>] [--plan <file>] [--chunk 160] [--json <file>]

`--stats` is what `ship_kit.py --stats <file>` writes (or the manifest.json of a kit export: its "meshes" carry the same counts); without it the last manifest in
art/export/ship is used. What it counts, per deck (the numbers the Unreal script prints too, so the two can be compared):

  placements   the modules, rooms, signs and plates of the plan, by class; the instances they become (one per placement)
  meshes       the distinct meshes the deck uses and their triangles (what a deck costs in memory and on disk once; Nanite clusters them)
  tris         the triangles of every instance if all were in view (the ceiling of the render cost; what is in front of the Captain is a small part)
  components   instanced-mesh components: one per distinct mesh per run of `--chunk` metres along the ship (a component culls and registers as a whole)
  sections     the draw-call ceiling without Nanite: the components' material slots (Nanite draws every opaque mesh in a few passes whatever the count)
  lamps, doors the plan's lamps (data; AstraLampPool lights the nearest few with a pool of real lights) and the doors that become actors of the deck's map
  resident     with the Captain on this deck: the deck and the decks its stairs reach (AstraDeckStreaming keeps those loaded): tris, components, doors, lamps

The limits it flags are the module's own (docs/NAVE.md): a mesh of 150 k triangles at most, a deck of 40 k lamps... see LIMITS. They are proxies for what only the game can
measure (frame time, memory, the load of a deck): the lead's runs decide.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_plan as P  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIMITS = {"mesh_tris": 150_000, "resident_components": 1500, "resident_doors": 400, "resident_lamps": 12000}


def load_stats(path: str | None) -> dict:
    """{mesh: {"tris": n, "slots": [...]}} from a --stats file or a kit manifest."""
    cands = [path] if path else [os.path.join(ROOT, "art", "_cache", "ship_stats.json"), os.path.join(ROOT, "art", "export", "ship", "manifest.json")]
    for p in cands:
        if p and os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh)
            meshes = d.get("meshes", d)
            return {n: {"tris": int(m["tris"]), "slots": m.get("slots") or m.get("materials") or []} for n, m in meshes.items()}
    raise SystemExit("no triangle counts: run  blender -b --factory-startup -P art/blender/ship_kit.py -- --no-export --stats art/_cache/ship_stats.json  first (or export the kit)")


def deck_budget(plan: dict, deck: int, stats: dict, chunk: float) -> dict:
    pls = plan["placements"].get(str(deck), [])
    meshes: dict[str, int] = {}
    by_class: dict[str, int] = {}
    comps: set = set()
    missing: set = set()
    tris = sections = 0
    for p in pls:
        st = stats.get(p["mesh"])
        if st is None:
            missing.add(p["mesh"])
            continue
        meshes[p["mesh"]] = meshes.get(p["mesh"], 0) + 1
        by_class[p["cls"]] = by_class.get(p["cls"], 0) + 1
        tris += st["tris"]
        key = (p["mesh"], int(p["pos"][0] // chunk))
        if key not in comps:
            comps.add(key)
            sections += max(1, len(st["slots"]))
    lamps = sum(len(c.get("lights", [])) for c in plan["compartments"] if c["deck"] == deck)
    doors = sum(1 for d in plan["doors"] if d["deck"] == deck and not d.get("existing") and not d.get("planned"))
    rooms = sum(1 for c in plan["compartments"] if c["deck"] == deck and c.get("status") == "built" and c.get("prefab"))
    top = sorted(meshes, key=lambda m: -stats[m]["tris"] * meshes[m])[:3]
    return {"deck": deck, "name": next((d["name"] for d in plan["decks"] if d["id"] == deck), ""), "placements": len(pls), "by_class": by_class, "meshes": len(meshes),
            "mesh_tris": sum(stats[m]["tris"] for m in meshes), "tris": tris, "components": len(comps), "sections": sections, "lamps": lamps, "doors": doors, "rooms": rooms,
            "missing": sorted(missing), "heaviest": [(m[len("SM_SHIP_"):], stats[m]["tris"], meshes[m]) for m in top],
            "tallest_mesh": max((stats[m]["tris"] for m in meshes), default=0)}


def neighbours(plan: dict, deck: int) -> list[int]:
    """The decks AstraDeckStreaming keeps with the Captain on `deck` (outside a hall): the deck and the decks the stair columns join it to."""
    out = {deck}
    for v in plan.get("vertical", []):
        if v.get("kind") != "stair":
            continue
        ds = sorted(int(d) for d in v.get("nodes", {}))
        for a, b in zip(ds, ds[1:]):
            if deck in (a, b):
                out.update((a, b))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stats")
    ap.add_argument("--plan", default=P.PLAN_PATH)
    ap.add_argument("--chunk", type=float, default=160.0)
    ap.add_argument("--json")
    args = ap.parse_args()
    plan = P.load(args.plan)
    stats = load_stats(args.stats)
    decks = sorted(int(d) for d, v in plan["placements"].items() if v)
    rows = {d: deck_budget(plan, d, stats, args.chunk) for d in decks}
    print(f"{'deck':>4} {'name':<28} {'place':>6} {'meshes':>6} {'mesh tris':>10} {'inst tris':>11} {'comps':>6} {'sects':>6} {'lamps':>6} {'doors':>6} {'rooms':>6}")
    for d in decks:
        r = rows[d]
        print(f"{d:>4} {r['name'][:28]:<28} {r['placements']:>6} {r['meshes']:>6} {r['mesh_tris']:>10,} {r['tris']:>11,} {r['components']:>6} {r['sections']:>6} {r['lamps']:>6} {r['doors']:>6} {r['rooms']:>6}")
    tot = {k: sum(r[k] for r in rows.values()) for k in ("placements", "tris", "components", "sections", "lamps", "doors", "rooms")}
    print(f"{'all':>4} {'':<28} {tot['placements']:>6} {len(stats):>6} {sum(s['tris'] for s in stats.values()):>10,} {tot['tris']:>11,} {tot['components']:>6} {tot['sections']:>6} {tot['lamps']:>6} {tot['doors']:>6} {tot['rooms']:>6}")
    print("\nresident sets (the Captain on a deck: its deck and the decks of its stairs):")
    res = {}
    flagged = []
    for d in decks:
        ds = [x for x in neighbours(plan, d) if x in rows]
        r = {k: sum(rows[x][k] for x in ds) for k in ("tris", "components", "sections", "lamps", "doors")}
        res[d] = dict(r, decks=ds)
        mark = []
        if r["components"] > LIMITS["resident_components"]:
            mark.append(f"components > {LIMITS['resident_components']}")
        if r["doors"] > LIMITS["resident_doors"]:
            mark.append(f"doors > {LIMITS['resident_doors']}")
        if r["lamps"] > LIMITS["resident_lamps"]:
            mark.append(f"lamps > {LIMITS['resident_lamps']}")
        flagged += [f"deck {d}: {m}" for m in mark]
        print(f"  deck {d:>2}: decks {ds}  {r['tris']:>11,} tris  {r['components']:>5} components  {r['sections']:>5} sections  {r['doors']:>4} doors  {r['lamps']:>5} lamps" + ("   !! " + "; ".join(mark) if mark else ""))
    worst = max(rows.values(), key=lambda r: r["tallest_mesh"])
    print(f"\nthe heaviest mesh: {worst['tallest_mesh']:,} tris (limit {LIMITS['mesh_tris']:,}); the heaviest of each deck:")
    for d in decks:
        print(f"  deck {d:>2}: " + ", ".join(f"{n} {t:,} x{k}" for n, t, k in rows[d]["heaviest"]))
    for d in decks:
        if rows[d]["missing"]:
            print(f"  deck {d}: meshes without counts (kit not rebuilt?): {rows[d]['missing'][:6]}")
            flagged.append(f"deck {d}: meshes without counts")
    if worst["tallest_mesh"] > LIMITS["mesh_tris"]:
        flagged.append(f"a mesh over {LIMITS['mesh_tris']:,} tris")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"decks": rows, "resident": res, "totals": tot, "limits": LIMITS}, fh, indent=1)
    print("\n" + ("BUDGET FLAGS: " + "; ".join(flagged) if flagged else "BUDGET OK"))
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
