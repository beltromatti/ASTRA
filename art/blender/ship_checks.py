"""ASN Aquila — layout checks of the ship's plan (pure Python): the plan inside the hull's envelope, no overlaps, every door on a wall of its
compartments, the walk graph connected (every compartment reachable, the stairs and the lift joined), clearances, sections and the
meshes the placements name.

  python3 art/blender/ship_checks.py [plan.json]      exit status 1 when a check fails
"""
from __future__ import annotations

import math
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_plan as P  # noqa: E402
from ship_catalog import MOD, SLOT_HW  # noqa: E402

TOL = 0.05


def _sorted_pairs(boxes: list[tuple[str, list[float]]]):
    """Candidate pairs by an x sweep."""
    order = sorted(boxes, key=lambda b: b[1][0])
    active: list = []
    for cid, bx in order:
        active = [(c, b) for (c, b) in active if b[2] > bx[0] + TOL]
        for c, b in active:
            yield (c, b), (cid, bx)
        active.append((cid, bx))


def check(plan: dict, verbose: bool = True) -> dict:
    problems: list[str] = []
    warnings: list[str] = []
    stats: dict = {}
    comps = {c["id"]: c for c in plan["compartments"]}
    doors = {d["id"]: d for d in plan["doors"]}
    decks = {d["id"]: d for d in plan["decks"]}
    nodes = {n["id"]: n for n in plan["graph"]["nodes"]}
    edges = plan["graph"]["edges"]

    # ---- 1. inside the hull's envelope --------------------------------------------------------------------------------
    for c in comps.values():
        b, z = c["bounds"], c["z"]
        d = c["deck"]
        if c.get("existing"):
            for (x, y) in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])):
                for zz in (z[0] + 0.1, z[1] - 0.1):
                    if d == 1:
                        continue
                    lim = P.lower_hull_half_width(x, zz)
                    if lim is None or abs(y) > lim - 0.2:
                        problems.append(f"{c['id']}: corner ({x:.1f}, {y:.1f}, z {zz:.1f}) is outside the lower hull (half width {lim})")
            continue
        env = decks[c["plane"] if c.get("plane") else d]["envelope"]
        if not env["half_width"]:
            continue
        for (x, y) in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])):
            hw = P.half_width_at({"half_width": env["half_width"]}, x)
            hw = hw if hw is not None else P.half_width_at(P.envelope(c["plane"] if c.get("plane") else d), x)
            if hw is None:
                problems.append(f"{c['id']} (deck {d}): corner x {x:.1f} is beyond the deck's x range [{env['x_aft']}, {env['x_fwd']}]")
                break
            if abs(y) > hw + 0.6:            # the plan's samples are every 8 m: allow the interpolation slack
                problems.append(f"{c['id']} (deck {d}): corner ({x:.1f}, {y:.1f}) is {abs(y) - hw:.2f} m outside the envelope (half width {hw:.1f})")
                break

    # ---- 2. no overlaps ------------------------------------------------------------------------------------------------
    n_pairs = 0
    boxes = [(c["id"], [c["bounds"][0], c["bounds"][1], c["bounds"][2], c["bounds"][3], c["z"][0], c["z"][1]]) for c in comps.values()]
    for (ca, ba), (cb, bb) in _sorted_pairs(boxes):
        if P.box_overlap(ba, bb, TOL):
            n_pairs += 1
            problems.append(f"overlap: {ca} {[round(v, 1) for v in ba]} and {cb} {[round(v, 1) for v in bb]}")
    stats["overlap_pairs"] = n_pairs

    # ---- 3. doors on walls ---------------------------------------------------------------------------------------------
    def on_boundary(p, bounds, tol) -> float:
        x0, y0, x1, y1 = bounds
        dx = max(x0 - p[0], 0.0, p[0] - x1)
        dy = max(y0 - p[1], 0.0, p[1] - y1)
        if dx > 0 or dy > 0:
            return math.hypot(dx, dy)                                # outside the rectangle: distance to it
        return min(p[0] - x0, x1 - p[0], p[1] - y0, y1 - p[1])      # inside: distance to the nearest side

    for d in doors.values():
        if d["width"] < 0.9 or d["height"] < 1.9:
            problems.append(f"door {d['id']}: {d['width']} x {d['height']} m is below the 0.9 x 1.9 m clearance")
        if d.get("kind") == "blast":
            continue
        for side in ("a", "b"):
            cid = d.get(side)
            if not cid:
                if not d.get("planned"):
                    problems.append(f"door {d['id']}: no compartment on side {side}")
                continue
            c = comps.get(cid)
            if c is None:
                problems.append(f"door {d['id']}: unknown compartment {cid}")
                continue
            dist = on_boundary(d["pos"], c["bounds"], 0.5)
            if dist > 0.65:
                problems.append(f"door {d['id']} ({d['pos'][0]:.1f}, {d['pos'][1]:.1f}) is {dist:.2f} m from the walls of {cid}")

    # ---- 4. the walk graph ---------------------------------------------------------------------------------------------
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["a"] not in nodes or e["b"] not in nodes:
            problems.append(f"edge {e['a']} - {e['b']}: unknown node")
            continue
        if e["a"] == e["b"]:
            problems.append(f"edge {e['a']}: a loop")
        if e.get("door") and e["door"] not in doors:
            problems.append(f"edge {e['a']} - {e['b']}: unknown door {e['door']}")
        if e["kind"] == "walk" and e.get("w", 3.0) < 0.9:
            problems.append(f"edge {e['a']} - {e['b']}: width {e.get('w')} m is below 0.9 m")
        adj[e["a"]].append(e["b"])
        adj[e["b"]].append(e["a"])
    seen: dict[str, int] = {}
    comp_sizes = []
    for nid in nodes:
        if nid in seen:
            continue
        idx = len(comp_sizes)
        stack, size = [nid], 0
        seen[nid] = idx
        while stack:
            u = stack.pop()
            size += 1
            for v in adj[u]:
                if v not in seen:
                    seen[v] = idx
                    stack.append(v)
        comp_sizes.append(size)
    main = max(range(len(comp_sizes)), key=lambda i: comp_sizes[i])
    stats["graph_components"] = len(comp_sizes)
    stats["graph_main_component"] = comp_sizes[main]
    for nid, n in nodes.items():
        if seen[nid] != main:
            problems.append(f"graph: node {nid} (deck {n['deck']}, {n['p']}) is not connected to the main network")
            if sum(1 for p in problems if p.startswith("graph: node")) > 12:
                problems.append("graph: ... (more unconnected nodes)")
                break
    reach = {n["comp"] for nid, n in nodes.items() if n.get("comp") and seen[nid] == main}
    for c in comps.values():
        if c["id"] not in reach:
            problems.append(f"graph: compartment {c['id']} ({c['kind']}, deck {c['deck']}) has no node in the network")
    for v in plan.get("vertical", []):
        if v["kind"] == "stair":
            for deck, nid in v["nodes"].items():
                if nid not in nodes or seen[nid] != main:
                    problems.append(f"stairs {v['id']}: the landing of deck {deck} is not reachable")
        if v["kind"] == "turbolift":
            for l in v["landings"]:
                if l["node"] not in nodes or seen[l["node"]] != main:
                    problems.append(f"lift landing {l['node']} is not reachable")

    # ---- 5. sections ---------------------------------------------------------------------------------------------------
    for c in comps.values():
        if c["deck"] == 1 or c.get("existing"):
            continue
        secs = [(l, a, b) for (l, a, b) in P.sections(c["deck"])]
        b = c["bounds"]
        s0 = P.section_of(c["deck"], b[0] + 0.01)
        s1 = P.section_of(c["deck"], b[2] - 0.01)
        if s0 != s1 and c["kind"] != "corridor":
            problems.append(f"{c['id']} (deck {c['deck']}) straddles the boundary of sections {s1}/{s0}: x {b[0]}..{b[2]}")
        if c["section"] != P.section_of(c["deck"], (b[0] + b[2]) / 2) and c["kind"] != "corridor":
            problems.append(f"{c['id']}: section {c['section']} does not match its position")

    # ---- 6. the fixed sections of the existing rooms ------------------------------------------------------------------------
    fixed = {"mess": ("B", 4), "berths": ("C", 4), "medbay": ("C", 6), "engineering": ("F", 7), "flight_deck": ("B", 9)}
    for cid, (sec, deck) in fixed.items():
        c = comps[cid]
        got = P.section_of(deck, (c["bounds"][0] + c["bounds"][2]) / 2)
        if got != sec:
            problems.append(f"{cid} should be in Deck {deck} Section {sec}, the plan puts it in {got}")

    # ---- 7. every deck and section has a place ----------------------------------------------------------------------------
    for d in range(2, 13):
        secs = P.sections(d)
        for letter, x0, x1 in secs:
            hits = [c for c in comps.values() if c["deck"] == d and c["section"] == letter and c["kind"] == "corridor"]
            allc = [c for c in comps.values() if c["deck"] == d and (c["section"] == letter or (c["bounds"][0] < x1 and c["bounds"][2] > x0 and c["kind"] != "corridor"))]
            env = decks[d]["envelope"]
            inside = P.half_width_at({"half_width": env["half_width"]}, (x0 + x1) / 2) is not None
            # a volume that crosses the deck (the Flight Deck's hangar) fills the sections it stands in
            spanned = any(c.get("spans_decks") and d in c["spans_decks"] and c["bounds"][0] < x1 and c["bounds"][2] > x0 for c in comps.values()
                          if c["deck"] != d)
            if not allc and inside and not spanned:
                warnings.append(f"deck {d} section {letter}: no compartment")
    stats["compartments"] = len(comps)
    stats["doors"] = len(doors)
    stats["nodes"] = len(nodes)
    stats["edges"] = len(edges)
    out = {"problems": problems, "warnings": warnings, "stats": stats}
    if verbose:
        for w in warnings[:40]:
            print("  warning:", w)
        for p in problems[:120]:
            print("  PROBLEM:", p)
        if len(problems) > 120:
            print(f"  ... {len(problems) - 120} more")
        print("  stats:", stats, "| problems:", len(problems), "| warnings:", len(warnings))
    return out


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else P.PLAN_PATH
    plan = P.load(path)
    res = check(plan)
    return 1 if res["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
