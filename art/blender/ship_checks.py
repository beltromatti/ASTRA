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
LIFT_KINDS = ("turbolift", "bridge", "service", "cargo")        # the contract's `kind` of a vertical[] record that is a lift (docs/brief/NAVE-3.md)
CREW = 560
SLEEP_QUOTA = int(math.ceil(CREW * 1.10))                       # every one of the crew has a berth, and a tenth over for the guests, the wounded and a relief
POD_SEATS = 20                                                  # a lifepod bay holds two pods of ten


def _sorted_pairs(boxes: list[tuple[str, list[float]]]):
    """Candidate pairs by an x sweep."""
    order = sorted(boxes, key=lambda b: b[1][0])
    active: list = []
    for cid, bx in order:
        active = [(c, b) for (c, b) in active if b[2] > bx[0] + TOL]
        for c, b in active:
            yield (c, b), (cid, bx)
        active.append((cid, bx))


EXISTING_RACKS = 84                                             # the Berths hall's racks (aquila_berths.json), a deck-4 existing room whose stations the plan does not list
# the programme of the redesign (docs/NAVE.md §3): the rooms a ship like this must have, by prefab, and how many at least
REQUIRED = {"dentist": 1, "morgue": 1, "counselling": 1, "pharmacy": 1, "surgery": 2, "quarantine": 1, "brig": 1, "security_office": 1, "armory": 1, "kit_room": 1, "barracks": 4,
            "computer_core": 2, "aux_reactor": 1, "air_plant": 2, "water_plant": 2, "waste_plant": 1, "dc_central": 3, "power_control": 1, "switchgear": 1, "capacitors": 1,
            "chapel": 1, "barber": 1, "bar": 1, "library": 1, "gym": 2, "sim_bay": 1, "observation": 1, "shop": 1, "wardroom": 1, "galley": 1, "transporter": 1,
            "airlock": 6, "pod_bay": 20, "suit_locker": 4, "shuttle_stop": 6, "berthing": 10}
REACH_P90 = 100.0                                               # a warning: more than this many metres of corridor to the nearest lift lobby for one corridor point in ten
REACH_P90_KEEL = 110.0                                          # (the keel's bow end is tanks and crawlways: nobody lives there)


def _check_programme(plan: dict, comps: dict, problems: list, warnings: list, stats: dict) -> None:
    """The programme of the redesign: the rooms that must exist (REQUIRED), the berths (every one of the crew and a tenth over), the lifepod seats, the two computer cores far apart."""
    built = [c for c in comps.values() if c.get("status") == "built" and c.get("prefab")]
    count: dict[str, int] = defaultdict(int)
    for c in built:
        count[c["prefab"]] += 1
    for key, n in REQUIRED.items():
        if count.get(key, 0) < n:
            problems.append(f"programme: {count.get(key, 0)} {key} in the plan, at least {n} wanted")
    sleep = sum(1 for c in comps.values() for s in c.get("stations", []) if s.get("kind") == "sleep") + EXISTING_RACKS
    stats["sleeping_places"] = sleep
    if sleep < SLEEP_QUOTA:
        problems.append(f"programme: {sleep} berths for a crew of {CREW} (and a tenth over: {SLEEP_QUOTA})")
    seats = count.get("pod_bay", 0) * POD_SEATS
    stats["lifepod_seats"] = seats
    if seats < CREW:
        problems.append(f"programme: {seats} lifepod seats for a crew of {CREW}")
    cores = [c for c in built if c["prefab"] == "computer_core"]
    if len(cores) >= 2:
        cx = [(c["bounds"][0] + c["bounds"][2]) / 2 for c in cores]
        if max(cx) - min(cx) < 250.0 or len({c["deck"] for c in cores}) < 2:
            problems.append(f"programme: the two computer cores are {max(cx) - min(cx):.0f} m apart on decks {sorted({c['deck'] for c in cores})}: a hit that takes one must not take both")
    stats["programme"] = {k: count[k] for k in sorted(count)}


def _check_vertical(plan: dict, comps: dict, nodes: dict, edges: list, seen: dict, main: int, problems: list, warnings: list, stats: dict) -> None:
    """The vertical network (the vertical[] / transit[] v2 contract with ASCENSORI): lifts that stop where they say, shafts and lobbies where the records put them, stairs and Jefferies
    trunks without a missing deck, the shuttle's halls joined by `shuttle` edges and a tunnel under its whole path."""
    ride = defaultdict(int)
    ladders = {(e["a"], e["b"]) for e in edges if e["kind"] == "stair" and e.get("ladder")}
    ladders |= {(b, a) for (a, b) in ladders}
    for e in edges:
        if e["kind"] == "lift" and e.get("shaft"):
            ride[e["shaft"]] += 1
    n_lifts = n_trunks = n_stairs = 0
    ids = set()
    for v in plan.get("vertical", []):
        if v["id"] in ids:
            problems.append(f"vertical {v['id']}: the id is used twice")
        ids.add(v["id"])
        ds = sorted(v["decks"])
        if ds != list(range(ds[0], ds[-1] + 1)):
            problems.append(f"{v['kind']} {v['id']}: the decks {ds} are not a continuous run (a column that skips a deck cannot be climbed)")
        if v["kind"] in LIFT_KINDS:
            n_lifts += 1
            n = len(ds)
            if n < 2:
                problems.append(f"lift {v['id']}: it serves one deck")
            if {l["deck"] for l in v["landings"]} != set(ds):
                problems.append(f"lift {v['id']}: the landings are not its decks {ds}")
            if ride.get(v["id"], 0) != n * (n - 1) // 2:
                problems.append(f"lift {v['id']}: {ride.get(v['id'], 0)} ride arcs, {n * (n - 1) // 2} wanted")
            sh = v["shaft"]
            if abs((sh["z"][1] - sh["z"][0]) - (P.deck_z(ds[0])[0] - P.deck_z(ds[-1])[0])) > 6.0:
                problems.append(f"lift {v['id']}: the shaft's z range {sh['z']} does not fit the decks {ds}")
            for l in v["landings"]:
                lobby = comps.get(l["lobby"])
                if lobby is None or lobby["deck"] != l["deck"]:
                    problems.append(f"lift {v['id']}: the lobby {l['lobby']} of deck {l['deck']} is missing")
                    continue
                if not (abs(l["door"][0] - sh["x"]) <= sh["w"] / 2 + 1.0 and abs(l["door"][1] - sh["y"]) <= sh["d"] / 2 + 1.0):
                    problems.append(f"lift {v['id']}: the landing door of deck {l['deck']} is {math.hypot(l['door'][0] - sh['x'], l['door'][1] - sh['y']):.1f} m from the shaft's axis")
                if abs(l["z"] - P.deck_z(l["deck"])[0]) > 0.01:
                    problems.append(f"lift {v['id']}: the landing of deck {l['deck']} is at z {l['z']}, the deck's floor is {P.deck_z(l['deck'])[0]}")
                # the waiting place (ASCENSORI: FindRide matches a rider's route ends against it, 90 cm): the landing's node, in the lobby 1.5 m in front of the door, reachable on foot
                nd = nodes.get(l.get("node"))
                if nd is None or seen.get(l.get("node")) != main:
                    problems.append(f"lift {v['id']}: the landing node {l.get('node')} of deck {l['deck']} is not a reachable graph node")
                else:
                    yaw = math.radians(l["yaw"])
                    wait = (l["door"][0] - 1.5 * math.cos(yaw), l["door"][1] - 1.5 * math.sin(yaw), l["z"])
                    off = math.dist(nd["p"][:2], wait[:2])
                    if off > 0.9 or abs(nd["p"][2] - wait[2]) > 0.9:
                        problems.append(f"lift {v['id']}: the landing node of deck {l['deck']} is {off:.2f} m from the waiting place in front of the door (90 cm at most)")
        elif v["kind"] == "trunk":
            n_trunks += 1
            for a, b in zip(ds, ds[1:]):
                if (v["nodes"][str(a)], v["nodes"][str(b)]) not in ladders:
                    problems.append(f"trunk {v['id']}: no ladder between decks {a} and {b}")
        elif v["kind"] == "stair":
            n_stairs += 1
    stats["lifts"], stats["trunks"], stats["stair_columns"] = n_lifts, n_trunks, n_stairs
    # the shuttle
    shuttle_edges = {(e["a"], e["b"]) for e in edges if e["kind"] == "shuttle"}
    for t in plan.get("transit", []):
        stops = t.get("stops", [])
        if len(stops) < 3:
            problems.append(f"transit {t['id']}: {len(stops)} stops")
        for s in stops:
            if s["room"] not in comps or s["node"] not in nodes or seen.get(s["node"]) != main:
                problems.append(f"transit {t['id']}: the stop {s['id']} has no room or no reachable node")
        for a, b in zip(stops, stops[1:]):
            if (a["node"], b["node"]) not in shuttle_edges and (b["node"], a["node"]) not in shuttle_edges:
                problems.append(f"transit {t['id']}: no `shuttle` edge between the stops {a['id']} and {b['id']}")
        halls = [c for c in comps.values() if c["deck"] == t["deck"] and c["kind"] in ("tunnel", "transit")]
        path = t["path"]
        for p0, p1 in zip(path, path[1:]):
            n = max(1, int(math.dist(p0[:2], p1[:2]) // 4.0))
            for i in range(n + 1):
                x = p0[0] + (p1[0] - p0[0]) * i / n
                y = p0[1] + (p1[1] - p0[1]) * i / n
                if not any(c["bounds"][0] - 0.01 <= x <= c["bounds"][2] + 0.01 and c["bounds"][1] - 0.01 <= y <= c["bounds"][3] + 0.01 for c in halls):
                    problems.append(f"transit {t['id']}: the path at ({x:.1f}, {y:.1f}) is in no tunnel or stop hall")
                    break
            else:
                continue
            break
        stats["shuttle_stops"] = len(stops)


def _check_reach(nodes: dict, edges: list, problems: list, warnings: list, stats: dict) -> None:
    """The walk from the corridors of a deck to the nearest turbolift lobby (docs/NAVE.md §4: from anywhere a lift within 60-80 m): median, p90, max per deck, in stats; a warning when
    the p90 is over REACH_P90, a problem when a deck of the body has no lift at all."""
    import heapq
    adj: dict[str, list] = defaultdict(list)
    for e in edges:
        if e["kind"] in ("walk", "door") and nodes[e["a"]]["deck"] == nodes[e["b"]]["deck"]:
            adj[e["a"]].append((e["b"], e["len"]))
            adj[e["b"]].append((e["a"], e["len"]))
    out = {}
    for deck in range(2, 13):
        src = [nid for nid, n in nodes.items() if n["deck"] == deck and n["kind"] == "lift"]
        if not src:
            problems.append(f"deck {deck}: no turbolift lobby")
            continue
        dist = {s: 0.0 for s in src}
        pq = [(0.0, s) for s in src]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist.get(u, 1e18):
                continue
            for v, w in adj[u]:
                if d + w < dist.get(v, 1e18):
                    dist[v] = d + w
                    heapq.heappush(pq, (d + w, v))
        cor = sorted(dist.get(nid, 1e9) for nid, n in nodes.items() if n["deck"] == deck and n["kind"] == "corridor" and n.get("passage", "")[:2] in ("SP", "SB", "PO"))
        if not cor:
            continue
        q = lambda f: cor[min(len(cor) - 1, int(f * len(cor)))]
        out[deck] = {"median": round(q(0.5), 1), "p90": round(q(0.9), 1), "max": round(cor[-1], 1)}
        lim = REACH_P90_KEEL if deck == 12 else REACH_P90
        if q(0.9) > lim:
            warnings.append(f"deck {deck}: one corridor point in ten is more than {lim:.0f} m of walk from a turbolift lobby (p90 {q(0.9):.0f} m)")
    stats["lift_walk_m"] = out


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
            # a corridor that runs up to the entrance of an existing room enters its wall (up to 0.6 m: the wall's thickness and the door's trim)
            pair = (comps[ca], comps[cb])
            corr = [c for c in pair if c["kind"] == "corridor" and c.get("status") == "built"]
            room = [c for c in pair if c.get("status") == "existing" and c.get("entrance")]
            if corr and room and min(ba[2], bb[2]) - max(ba[0], bb[0]) <= 0.6 + 1e-6:
                continue
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
        if c["id"] not in reach and c["kind"] != "tunnel":                   # (the shuttle's tunnel is not walked: the car runs in it, `shuttle` edges join the halls)
            problems.append(f"graph: compartment {c['id']} ({c['kind']}, deck {c['deck']}) has no node in the network")
    for v in plan.get("vertical", []):
        if v["kind"] == "stair":
            for deck, nid in v["nodes"].items():
                if nid not in nodes or seen[nid] != main:
                    problems.append(f"stairs {v['id']}: the landing of deck {deck} is not reachable")
        if v["kind"] in LIFT_KINDS:
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
    # ---- 8. the programme: every room of the kit stands somewhere, and what the generator could not place is a problem, not a note -------------------------
    import ship_spec as SP
    placed_keys = {c.get("prefab") for c in comps.values() if c.get("status") == "built" and c.get("prefab")}
    placed_meshes = {p["mesh"] for pl in plan.get("placements", {}).values() for p in pl}                    # (the Deck 1 lift housing: an existing compartment that has a mesh now)
    for key, spec in SP.PREFABS.items():
        if spec.get("mesh") and key not in placed_keys and spec["mesh"] not in placed_meshes:
            problems.append(f"programme: the room {key} of the kit stands nowhere in the plan (its programme or its fixed place does not fit)")
    for n in plan.get("notes", []):
        if " cannot stand at " in n:
            problems.append("programme: " + n)
    _check_programme(plan, comps, problems, warnings, stats)
    _check_vertical(plan, comps, nodes, edges, seen, main, problems, warnings, stats)
    _check_reach(nodes, edges, problems, warnings, stats)
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
