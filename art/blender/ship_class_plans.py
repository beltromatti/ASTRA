#!/usr/bin/env python3
"""ASTRA ships: the plan of every class (FLOTTA-VIVA, docs/FLOTTA-VIVA.md): data/ship/plans/<class>.json, in the format of data/ship/aquila_plan.json
(decks, compartments with bounds and kinds, doors, the walk graph, systems) and a superset of it: docks, objectives, garrison, crew, damage-control
parties. One per class of data/war/classes.json (the Aquila's own is data/ship/aquila_plan.json; plans/aquila.json points at it).

Every ship of the war has an interior: this is its DNA. The damage model (Source/ASTRA/AstraDamageModel.*) runs on it as it runs on the Aquila's,
the boarding maps (ABBORDAGGI) are built from it, the roster stands in its rooms. A class plan is coarser than the Aquila's (a few decks, a few
hundred compartments: rooms are bays of a section, not single cabins) and lies inside the real hull of the class (the probe of the exported mesh,
ship_hull_probe.py, read by ship_class_hull.py). Frame: the mesh's own (the hull_m box of data/war/classes.json); `origin_in_hull` is [0, 0, 0].

  python3 art/blender/ship_class_plans.py [--only lethe,styx] [--no-check] [--no-stage]

Writes data/ship/plans/<class>.json and the staged copy Content/ASTRA/Data/plans/<class>.json (the game and the boarding maps read that one first:
it is packaged as a loose file with the rest of Content/ASTRA/Data). The specs are in ship_class_specs.py, the layout rules in ship_class_engine.py,
the checks in ship_class_checks.py (they run after every build: 0 problems expected).
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ship_class_build as B  # noqa: E402
import ship_class_specs as S  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "ship", "plans")
STAGE_DIR = os.path.join(ROOT, "Content", "ASTRA", "Data", "plans")


def dump(plan: dict, path: str) -> int:
    """One top-level key to a line (a plan is read by eye and diffed), the records compact."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    keys = list(plan)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n")
        for i, k in enumerate(keys):
            f.write(json.dumps(k) + ": " + json.dumps(plan[k], separators=(",", ":"), ensure_ascii=False) + (",\n" if i < len(keys) - 1 else "\n"))
        f.write("}\n")
    return os.path.getsize(path)


def build_class(key: str, stage: bool = True, check: bool = True) -> dict:
    t0 = time.time()
    plan = B.Builder(S.SPECS[key]).build()
    size = dump(plan, os.path.join(OUT_DIR, key + ".json"))
    if stage:
        dump(plan, os.path.join(STAGE_DIR, key + ".json"))
    docks, nodes = len(plan["docks"]), len(plan["graph"]["nodes"])
    print(f"[plans] {key}: {len(plan['decks'])} decks, {len(plan['compartments'])} compartments, {len(plan['doors'])} doors, {nodes} nodes, "
          f"{len(plan['graph']['edges'])} edges, {docks} docks, crew {plan['crew']['complement']} -> {size // 1024} KB ({time.time() - t0:.1f} s)")
    for n in plan["notes"]:
        print(f"   note: {n}")
    if check:
        import ship_class_checks as C
        problems = C.check(plan, S.SPECS[key])
        for p in problems:
            print(f"   PROBLEM: {p}")
        print(f"   checks: {'0 problems' if not problems else str(len(problems)) + ' problems'}")
    return plan


def report_decks(key: str):
    """The decks a spec makes, before any room is laid: where each one extends, how wide, where its passages run (for writing a spec)."""
    import ship_class_engine as E
    spec = S.SPECS[key]
    hull = E.HULL.Hull(key)
    print(f"== {key}: hull x {hull.x_range()[0]:.0f}..{hull.x_range()[1]:.0f}, sections " + " ".join(f"{l}[{xf:.0f}..{xa:.0f}]" for l, xf, xa in spec["sections"]))
    for ds in spec["decks"]:
        try:
            d = E.Deck(ds, hull, spec.get("wall", 2.5))
        except ValueError as e:
            print(f"   deck {ds['id']:2d}: {e}")
            continue
        d.choose_passages()
        print(f"   deck {d.id:2d} {d.name:22s} z {d.z:6.1f}..{d.z + d.clear:6.1f}  x {d.xa:7.1f}..{d.xf:7.1f}  hw max {max(d.ehw):5.1f} at 0.25/0.5/0.75: "
              f"{[round(d.hw(d.xa + (d.xf - d.xa) * f), 1) for f in (0.25, 0.5, 0.75)]}  passages " + (f"y {d.YP:.1f} x {d.pass_x[0]:.0f}..{d.pass_x[1]:.0f}" if d.pass_x else "none"))


def main():
    argv = sys.argv[1:]
    only = []
    if "--only" in argv:
        only = argv[argv.index("--only") + 1].split(",")
    if "--decks" in argv:
        for k in [k for k in S.SPECS if not only or k in only]:
            report_decks(k)
        return
    keys = [k for k in S.SPECS if not only or k in only]
    for k in keys:
        build_class(k, stage="--no-stage" not in argv, check="--no-check" not in argv)


if __name__ == "__main__":
    main()
