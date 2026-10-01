"""ASN Aquila — the wayfinding of the plan (NAVE-3). Pure Python; run by ship_plan_gen.build_plan once the walk graph is complete.

A ship this big is read from its signs. Four kinds, all placed as `sign` instances of the plan (the signs of NAVE-2, the section signs on the blast doors' frames, stay):

  blade signs   SM_SHIP_WayBlade_<n> (the frame) with SM_SHIP_WayRow_<dest><arrow> on it for every row, hung from the ceiling across the Spine and the passages at their junctions, at the lobbies' gates and at most every 48 m between: a pair back to
                back, one face for each way of walking. A row is a pictogram, a destination and an arrow; the arrows are not drawn by hand: for every sign and every destination the
                walk graph is searched (Dijkstra, from the destinations backwards) and the first stretch of the shortest path says where it lies for the one who reads the sign: ahead, to
                the left, to the right (what lies behind is on the other face). Destinations: the turbolifts, the stairs, the Medbay, the lifepods, and by deck the bridge, the Mess
                Hall, Engineering, the Flight Deck, the Spine shuttle, the brig. Three rows at most, in the deck's order of importance.
  frame plates  SM_SHIP_Frame_<n>: "FR 134", the ship's ordinates (one frame per 4 m from the bow: frame 0 at x = +216), under the section signs of the blast doors' frames and at
                the lobbies.
  directories   SM_SHIP_Directory_<deck>: the screen with the deck's main places by section, on the wall of every turbolift lobby over the bench.

A blade is a frame of one to three rows and a mesh for each row (`SM_SHIP_WayRow_liftA`: the lifts are ahead; `podsL`: the lifepods to the left): thirty small meshes say everything, and the
kit builds exactly those the plan needs."""
from __future__ import annotations

import heapq
import math

import ship_plan as P
from ship_catalog import CLEAR_H, MOD, WAY_FRAME_PAD, WAY_HANGER, WAY_ROW_H

FRAME_X0 = 216.0                     # the bow: frame 0
BLADE_GAP = 48.0                     # no stretch of a passage longer than this without a blade
BLADE_MIN = 20.0                     # two blades of a passage are at least this far apart
BLADE_Z_SKIP = 1                     # modules either side of a bulkhead's module where no blade hangs (the section sign is there)
HEAD = 5.0                           # how far along the shortest path the direction is read (m)
ROWS = 3
OFF = 0.03                           # the two faces of a pair stand this far from the axis

DEST_ORDER = {2: ["lift", "bridge", "med", "pods", "stairs"], 3: ["lift", "bridge", "med", "pods", "stairs"], 4: ["lift", "mess", "med", "pods", "stairs"],
              5: ["lift", "shuttle", "med", "pods", "stairs"], 6: ["lift", "med", "stairs", "pods"], 7: ["lift", "engineering", "pods", "med", "stairs"],
              8: ["lift", "brig", "pods", "med", "stairs"], 9: ["lift", "flight", "pods", "med", "stairs"], 10: ["lift", "pods", "stairs", "med"],
              11: ["lift", "pods", "stairs", "med"], 12: ["lift", "pods", "stairs", "med"]}
DIR_LOBBY = {"SM_SHIP_LiftBank", "SM_SHIP_LiftBankO"}
DIR_LOCAL = (7.75, 8.0)              # the directory's place on a lobby's right wall, over the bench (the lobby's frame: ship_rooms_lifts.py)
HUBS = {"med": ["medbay.hub"], "bridge": ["bridge.hub"], "mess": ["mess.hub"], "engineering": ["engineering.hub"], "flight": ["flight_deck.hub"]}


def frame_no(x: float) -> int:
    return int(round((FRAME_X0 - x) / MOD))


# ------------------------------------------------------------------------------------------------------------------------------------------------ the graph
def _adjacency(B) -> dict:
    """The walk graph without the shuttle (the shuttle has its own destination); a lift or a stair costs what the plan says, never less than 10 m of walking."""
    adj: dict[str, list] = {n: [] for n in B.nodes}
    for e in B.edges:
        if e["kind"] == "shuttle":
            continue
        c = e.get("cost", e["len"])
        if e["kind"] in ("lift", "stair", "ladder"):
            c = max(c, 10.0)
        adj[e["a"]].append((e["b"], c))
        adj[e["b"]].append((e["a"], c))
    return adj


def _targets(B) -> dict:
    t: dict[str, list] = {"lift": [], "stairs": [], "pods": [], "brig": [], "shuttle": []}
    for n in B.nodes.values():
        if n["kind"] == "lift":
            t["lift"].append(n["id"])
        elif n["kind"] == "stair":
            t["stairs"].append(n["id"])
        elif n["kind"] == "platform":
            t["shuttle"].append(n["id"])
    for c in B.comps.values():
        if c.get("prefab") == "pod_bay" and f"{c['id']}.hub" in B.nodes:
            t["pods"].append(f"{c['id']}.hub")
        elif c.get("prefab") == "brig" and f"{c['id']}.hub" in B.nodes:
            t["brig"].append(f"{c['id']}.hub")
    for k, ids in HUBS.items():
        t[k] = [i for i in ids if i in B.nodes]
    return {k: v for k, v in t.items() if v}


def _search(adj: dict, sources: list) -> dict:
    """Dijkstra from the destinations: {node: the next node on the shortest path to the nearest destination}."""
    dist = {s: 0.0 for s in sources}
    nxt: dict[str, str] = {}
    heap = [(0.0, s) for s in sources]
    heapq.heapify(heap)
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                nxt[v] = u
                heapq.heappush(heap, (nd, v))
    return nxt


def _bearing(B, nxt: dict, node: str, heading: tuple) -> str | None:
    """Where the nearest destination lies for someone at `node` facing `heading`: 'A' ahead, 'L' left, 'R' right, None if behind (or here). Read on the first HEAD metres of the path."""
    p0 = B.nodes[node]["p"]
    cur, v = node, None
    for _ in range(16):
        cur = nxt.get(cur)
        if cur is None:
            return None
        p = B.nodes[cur]["p"]
        if abs(p[2] - p0[2]) > 1.2:                                  # the path leaves the deck: the stretch up to here is the direction
            break
        v = (p[0] - p0[0], p[1] - p0[1])
        if math.hypot(*v) >= HEAD:
            break
    if v is None or math.hypot(*v) < 1.5:
        return None
    a = v[0] * heading[0] + v[1] * heading[1]                        # along the heading
    r = -v[0] * heading[1] + v[1] * heading[0]                       # to the right of it (X forward, Y starboard)
    ang = math.degrees(math.atan2(r, a))
    if abs(ang) <= 50.0:
        return "A"
    if 50.0 < ang < 130.0:
        return "R"
    if -130.0 < ang < -50.0:
        return "L"
    return None


# ------------------------------------------------------------------------------------------------------------------------------------------------ where the blades hang
def _candidates(B, deck_obj) -> dict:
    """Per passage (the walking corridors, tones S and P): the module indices that are junctions: a cross passage or the gate of a lobby or a stair tower leaves there."""
    out: dict[str, set] = {pid: set() for pid, ps in deck_obj.passages.items() if ps.tone in ("S", "P")}
    for e in B.edges:
        if e["kind"] not in ("walk", "door"):
            continue
        for a, b in ((e["a"], e["b"]), (e["b"], e["a"])):
            na, nb = B.nodes[a], B.nodes[b]
            if na["kind"] != "corridor" or na["deck"] != deck_obj.deck or na.get("passage") not in out:
                continue
            if (nb["kind"] == "corridor" and nb.get("passage") != na["passage"]) or \
                    (nb["kind"] == "door_in" and B.comps.get(nb.get("comp"), {}).get("kind") in ("lobby", "stairs")):
                out[na["passage"]].add(int(a.rsplit(".", 1)[1]))
    return out


def _blade_modules(deck_obj, cand: dict) -> dict:
    """The modules of each passage that get a blade: the junctions (no two closer than BLADE_MIN) and the ones that keep the gaps under BLADE_GAP."""
    chosen: dict[str, list] = {}
    for pid, ps in deck_obj.passages.items():
        if pid not in cand:
            continue
        bulks = {i for i, e in ps.ev.items() if e.get("bulk")}
        skip = {i + d for i in bulks for d in range(-BLADE_Z_SKIP, BLADE_Z_SKIP + 1)}
        ok = [i for i in range(1, ps.n - 1) if i not in skip]
        picked: list[int] = []
        for i in sorted(cand[pid]):
            if i in ok and all(abs(i - j) * MOD >= BLADE_MIN for j in picked):
                picked.append(i)
        for i in ok:                                                 # the gaps: walk along the passage, a blade wherever the nearest one is too far
            if all(abs(i - j) * MOD > BLADE_GAP for j in picked):
                picked.append(i)
        chosen[pid] = sorted(picked)
    return chosen


# ------------------------------------------------------------------------------------------------------------------------------------------------ the plan
def plan(B, decks: dict) -> dict:
    """Place the blade signs, the frame plates and the directories; returns the counts. `decks` is {deck: ship_layout.Deck} as built by ship_design.build_all."""
    adj = _adjacency(B)
    nxt = {k: _search(adj, v) for k, v in _targets(B).items()}
    stats = {"blades": 0, "faces": 0, "frame_plates": 0, "directories": 0, "codes": {}}
    for d, dk in sorted(decks.items()):
        if d not in DEST_ORDER:
            continue
        order = [k for k in DEST_ORDER[d] if k in nxt]
        cand = _candidates(B, dk)
        z = dk.z0 + CLEAR_H
        folder = f"Interior/Deck{d:02d}/Way"
        codes: set[str] = set()
        for pid, mods in _blade_modules(dk, cand).items():
            ps = dk.passages[pid]
            for i in mods:
                nid = ps.node_id(dk.tag, i, False)
                if nid not in B.nodes:
                    continue
                a = ps.a0 + i * MOD + MOD / 2
                x, y = (a, ps.pos) if ps.along == "x" else (ps.pos, a)
                faces = []
                for sgn in (1, -1):
                    normal = (sgn, 0) if ps.along == "x" else (0, sgn)
                    heading = (-normal[0], -normal[1])
                    rows = []
                    for dest in order:
                        arrow = _bearing(B, nxt[dest], nid, heading)
                        if arrow:
                            rows.append(f"{dest}{arrow}")
                        if len(rows) == ROWS:
                            break
                    if rows:
                        faces.append((sgn, normal, rows))
                frame = max((len(r) for _, _, r in faces), default=0)               # (the two faces of a pair share a frame: the shorter one has a blank row or two)
                for sgn, normal, rows in faces:
                    yaw = {(1, 0): 0.0, (-1, 0): 180.0, (0, 1): 90.0, (0, -1): -90.0}[normal]
                    px, py = x + normal[0] * OFF, y + normal[1] * OFF
                    label = f"d{d}_way_{pid.lower()}_{i:03d}_{'p' if sgn > 0 else 'n'}"
                    B.place(d, f"SM_SHIP_WayBlade_{frame}", (px, py, z), yaw, folder, label, "sign")                          # the frame, and a mesh for every row on it
                    for k, row in enumerate(rows):
                        B.place(d, f"SM_SHIP_WayRow_{row}", (px, py, z - WAY_HANGER - WAY_FRAME_PAD - (k + 0.5) * WAY_ROW_H), yaw, folder, f"{label}_r{k}", "sign")
                    codes.add("_".join(rows))
                placed = len(faces)
                stats["blades"] += 1 if placed else 0
                stats["faces"] += placed
        stats["codes"][d] = len(codes)
        # frame plates under the section signs of the blast doors' frames (the signs sit 0.045 m forward of the frame or 0.673 m aft of it, the face of the sign towards the corridor)
        for pl in list(B.placements[d]):
            if pl["cls"] != "sign" or not pl["mesh"].startswith("SM_SHIP_Sign_"):
                continue
            x, y, zs = pl["pos"]
            yaw = (pl["yaw"] + 180.0) % 360.0
            n = frame_no(round(x / MOD) * MOD)
            nx, ny = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            B.place(d, f"SM_SHIP_Frame_{n}", (x + nx * 0.06, y + ny * 0.06, zs - 0.30), yaw, folder.replace("/Way", "/Signs"), pl["label"].replace("_sign_", "_frame_"), "sign")
            stats["frame_plates"] += 1
        # the directory and the frame plate on the wall of every turbolift lobby
        for pl in list(B.placements[d]):
            if pl["cls"] != "room" or pl["mesh"] not in DIR_LOBBY:
                continue
            yaw = math.radians(pl["yaw"])
            c, s = math.cos(yaw), math.sin(yaw)
            lx, ly = DIR_LOCAL
            wx, wy = pl["pos"][0] + c * lx - s * ly, pl["pos"][1] + s * lx + c * ly
            fy = (pl["yaw"] + 180.0) % 360.0
            B.place(d, f"SM_SHIP_Directory_{d}", (wx, wy, pl["pos"][2]), fy, f"Interior/Deck{d:02d}/Signs", f"{pl['label']}_directory", "sign")
            B.place(d, f"SM_SHIP_Frame_{frame_no(wx)}", (wx, wy, pl["pos"][2] + 1.0), fy, f"Interior/Deck{d:02d}/Signs", f"{pl['label']}_frame", "sign")
            stats["directories"] += 1
            stats["frame_plates"] += 1
    return stats
