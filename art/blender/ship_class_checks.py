#!/usr/bin/env python3
"""ASTRA ships: the checks of a class plan (FLOTTA-VIVA): what ABBORDAGGI, the damage model and the crew's roster rely on. Run by the generator after
every build (0 problems expected) and on its own:  python3 art/blender/ship_class_checks.py [class ...]   (reads data/ship/plans/<class>.json).

  structure      the keys of the format; unique ids; every door, node, edge, dock, objective and garrison entry points at something that exists
  the hull       every room's box is inside the deck's envelope and, with a little give, inside the skin the probe measured; no two boxes overlap
  the doors      each stands in the wall between the two compartments it names; every room has one; a door of kind `blast` names its two sections
  the graph      from every dock to every compartment by doors and stairs (no lifts); the spine's bulkheads can all be shut and the ship stays one:
                 a second way between the bridge, the reactor hall and the armoury (a flank exists)
  the people     the garrison adds up to the complement; the billets and the damage parties have rooms; the objectives are the right kind of room
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import ship_class_engine as E  # noqa: E402

REQUIRED = ("id", "version", "class", "origin_in_hull", "decks", "compartments", "doors", "graph", "systems", "docks", "objectives", "garrison", "crew", "damage_control")
OBJECTIVE_KINDS = {"bridge": ("bridge",), "engineering": ("engineering",), "armory": ("armory",), "medbay": ("medbay",), "brig": ("brig",), "comms": ("comms",),
                   "hangar": ("hangar",), "captain": ("quarters",)}


def overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


def check(plan: dict, spec: dict | None = None) -> list:
    out = []
    P = out.append
    for k in REQUIRED:
        if k not in plan:
            P(f"missing key {k}")
    if out:
        return out
    comps = plan["compartments"]
    by_id = {}
    for c in comps:
        if c["id"] in by_id:
            P(f"duplicate compartment id {c['id']}")
        by_id[c["id"]] = c
    doors = {}
    for d in plan["doors"]:
        if d["id"] in doors:
            P(f"duplicate door id {d['id']}")
        doors[d["id"]] = d
    nodes = {}
    for n in plan["graph"]["nodes"]:
        if n["id"] in nodes:
            P(f"duplicate node id {n['id']}")
        nodes[n["id"]] = n
        if n["comp"] not in by_id:
            P(f"node {n['id']}: no compartment {n['comp']}")
    decks = {d["id"]: d for d in plan["decks"]}
    if sorted(decks) != list(range(1, len(decks) + 1)):
        P(f"deck ids are not 1..N: {sorted(decks)}")
    # ---------------------------------------------------------------------------------------------------------- the hull
    hull = None
    try:
        hull = E.HULL.Hull(plan["class"])
    except OSError:
        P("no hull profile (data/ship/plans/hulls)")
    for c in comps:
        if c["deck"] not in decks:
            P(f"{c['id']}: no deck {c['deck']}")
            continue
        x0, y0, x1, y1 = c["bounds"]
        if not (x1 > x0 and y1 > y0):
            P(f"{c['id']}: empty box {c['bounds']}")
        d = decks[c["deck"]]
        env = d["envelope"]
        if x0 < env["x_aft"] - 0.6 or x1 > env["x_fwd"] + 0.6:
            P(f"{c['id']} ({c['kind']}): x {x0:.1f}..{x1:.1f} beyond its deck's x {env['x_aft']}..{env['x_fwd']}")
        hw = max(abs(y0), abs(y1))
        pts = env["half_width"]
        xs = [x0, 0.5 * (x0 + x1), x1]
        for x in xs:
            lim = None
            for (xa, ha), (xb, hb) in zip(pts, pts[1:]):
                lo, hi = min(xa, xb), max(xa, xb)
                if lo - 1e-6 <= x <= hi + 1e-6:
                    lim = ha + (hb - ha) * (x - xa) / (xb - xa) if xb != xa else ha
                    break
            if lim is not None and hw > lim + 0.8 and c["kind"] not in ("airlock",):
                P(f"{c['id']} ({c['kind']}): half width {hw:.1f} outside the deck's envelope {lim:.1f} at x {x:.0f}")
                break
        if hull and c["kind"] != "corridor":
            za, zb = c["z"]
            for x in xs:
                skin = hull.half_width(x, za + 0.2, zb - 0.2)
                if skin > 0 and hw > skin + (spec or {}).get("skin_slack", 3.2):                   # (the envelope fills the plating's recesses: it can stand proud of the median skin there)
                    P(f"{c['id']} ({c['kind']}): half width {hw:.1f} beyond the measured skin {skin:.1f} at x {x:.0f}")
                    break
    # no two boxes overlap
    for i, a in enumerate(comps):
        ax0, ay0, ax1, ay1 = a["bounds"]
        az0, az1 = a["z"]
        for b in comps[i + 1:]:
            bz0, bz1 = b["z"]
            if overlap(az0, az1, bz0, bz1) <= 0.3:
                continue
            bx0, by0, bx1, by1 = b["bounds"]
            ox, oy = overlap(ax0, ax1, bx0, bx1), overlap(ay0, ay1, by0, by1)
            if ox > 0.15 and oy > 0.15:
                P(f"overlap: {a['id']} ({a['kind']}) and {b['id']} ({b['kind']}) by {ox:.1f} x {oy:.1f} m")
    # ---------------------------------------------------------------------------------------------------------- the doors
    for d in plan["doors"]:
        a, b = by_id.get(d["a"]), by_id.get(d["b"])
        if not a or not b:
            P(f"door {d['id']}: {d['a']} / {d['b']} missing")
            continue
        for who in (a, b):
            if d["id"] not in who["doors"]:
                P(f"door {d['id']}: not in the doors of {who['id']}")
            x, y, z = d["pos"]
            bx0, by0, bx1, by1 = who["bounds"]
            dist = math.hypot(max(bx0 - x, 0, x - bx1), max(by0 - y, 0, y - by1))
            if dist > 0.75:
                P(f"door {d['id']}: {dist:.1f} m from {who['id']}'s wall")
        if d["kind"] == "blast":
            if len(d.get("boundary", [])) != 2 or d["boundary"][0] == d["boundary"][1]:
                P(f"blast door {d['id']}: no two sections in boundary")
    for c in comps:
        if c["kind"] != "corridor" and not c["doors"]:
            P(f"{c['id']} ({c['kind']}) has no door")
    # ---------------------------------------------------------------------------------------------------------- the graph
    adj = {}
    edge_kinds = set()
    for e in plan["graph"]["edges"]:
        edge_kinds.add(e["kind"])
        if e["a"] not in nodes or e["b"] not in nodes:
            P(f"edge {e['a']} - {e['b']}: a node is missing")
            continue
        adj.setdefault(e["a"], []).append((e["b"], e))
        adj.setdefault(e["b"], []).append((e["a"], e))
    if edge_kinds - {"walk", "door", "stair"}:
        P(f"edges of kinds soldiers cannot walk: {edge_kinds - {'walk', 'door', 'stair'}}")
    comp_nodes = {}
    for nid, n in nodes.items():
        comp_nodes.setdefault(n["comp"], []).append(nid)

    def reach(start_nodes, banned=lambda e: False):
        seen = set(start_nodes)
        q = deque(start_nodes)
        while q:
            u = q.popleft()
            for v, e in adj.get(u, ()):
                if v not in seen and not banned(e):
                    seen.add(v)
                    q.append(v)
        return seen

    docks = plan["docks"]
    if len(docks) < 4:
        P(f"{len(docks)} docks: at least 4")
    sides = {}
    for dk in docks:
        if dk["comp"] not in by_id:
            P(f"dock {dk['id']}: no compartment {dk['comp']}")
            continue
        sides.setdefault(dk["face"], set()).add(dk["deck"])
    if len(decks) >= 4:
        for f in ("port", "starboard"):
            if len(sides.get(f, ())) < 2:
                P(f"docks on the {f} side are on {len(sides.get(f, ()))} deck(s): at least 2, different")
    if docks:
        for dk in docks:
            seen = reach(comp_nodes.get(dk["comp"], []))
            missing = [c["id"] for c in comps if comp_nodes.get(c["id"]) and not any(n in seen for n in comp_nodes[c["id"]])]
            if missing:
                P(f"from dock {dk['id']} {len(missing)} compartments cannot be reached (e.g. {missing[:4]})")
                break
    for c in comps:
        if not comp_nodes.get(c["id"]):
            P(f"{c['id']} has no node in the walk graph")
    # a flank exists: with the spine's pressure bulkheads all shut, the objectives are still joined
    obj = plan["objectives"]
    start = comp_nodes.get(obj.get("bridge") or "", [])
    no_spine = lambda e: e.get("blast") and doors.get(e.get("door"), {}).get("passage") == "SP0"
    has_passages = any(cc.get("role") == "passage" for cc in comps)
    if start and has_passages:
        seen = reach(start, no_spine)
        for k in ("engineering", "armory"):
            tgt = obj.get(k)
            if tgt and not any(n in seen for n in comp_nodes.get(tgt, [])):
                P(f"with the spine's bulkheads shut the bridge cannot reach the {k}: no second way round")
    # every pair of neighbouring sections is joined by more than the spine on some deck
    blasts = [d for d in plan["doors"] if d["kind"] == "blast"]
    by_boundary = {}
    for d in blasts:
        by_boundary.setdefault(tuple(d["boundary"]), set()).add(d["passage"])
    for b, lanes in by_boundary.items():
        # a boundary where some deck has passages on both sides must have them cross it too (the ends of a narrow ship have only a spine)
        both = any(
            {c["section"] for c in comps if c.get("role") == "passage" and c["deck"] == d["id"]} >= {b[0], b[1]} for d in plan["decks"])
        if both and len(lanes) < 2:
            P(f"between sections {b[1]} and {b[0]} only the spine crosses the bulkhead")
    # ---------------------------------------------------------------------------------------------------------- the people
    total = sum(g["n"] for g in plan["garrison"])
    if total != plan["crew"]["complement"]:
        P(f"the garrison is {total}, the complement {plan['crew']['complement']}")
    for g in plan["garrison"]:
        if g["comp"] not in by_id:
            P(f"garrison: no compartment {g['comp']}")
    for b in plan["crew"]["billets"]:
        if b["post"] not in by_id:
            P(f"billet {b['role']}: no compartment {b['post']}")
    for p in plan["damage_control"]["parties"]:
        if p["home"] not in by_id:
            P(f"damage party {p['id']}: no compartment {p['home']}")
    if not plan["damage_control"]["parties"]:
        P("no damage-control parties")
    for k, kinds in OBJECTIVE_KINDS.items():
        v = obj.get(k)
        if not v:
            if plan["class"] not in ("freighter", "station") or k in ("bridge", "engineering"):
                P(f"objective {k} is missing")
            continue
        c = by_id.get(v)
        if not c:
            P(f"objective {k}: no compartment {v}")
        elif c["kind"] not in kinds:
            P(f"objective {k} is a {c['kind']} (expected {kinds})")
    for s in plan["systems"].values():
        for cid in s["compartments"]:
            if cid not in by_id:
                P(f"systems: no compartment {cid}")
    for m in plan.get("mounts", []):
        if not m.get("comp") or m["comp"] not in by_id:
            P(f"mount {m['i']} ({m['kind']}, role {m['role']}) has no room")
    if any("PROBLEM" in n for n in plan.get("notes", [])):
        P([n for n in plan["notes"] if "PROBLEM" in n][0])
    # the class's cuts are section boundaries (a gutted section of the war is whole sections here)
    cuts = plan["hull"].get("cuts_x", [])
    bounds = {x for d in plan["decks"] for s in d["sections"] for x in s["x"]}
    for cx in cuts:
        if cx and not any(abs(cx - b) < 3.0 for b in bounds):
            P(f"the class's cut at x {cx} is not within 3 m of a section boundary")
    unknown = {c["kind"] for c in comps} - set(E.KINDS) - {"vestibule"}
    if unknown:
        P(f"kinds not in the table: {sorted(unknown)}")
    return out


def main():
    keys = sys.argv[1:] or ["lethe", "styx", "acheron", "vigilant", "praetorian", "freighter", "station"]
    bad = 0
    for k in keys:
        path = os.path.join(ROOT, "data", "ship", "plans", k + ".json")
        if not os.path.isfile(path):
            continue
        plan = json.load(open(path, encoding="utf-8"))
        problems = check(plan)
        print(f"{k}: {len(problems)} problems")
        for p in problems[:40]:
            print("   " + p)
        bad += len(problems)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
