"""ASN Aquila — generator of data/ship/aquila_plan.json (the ship's plan, "the ship's DNA"). Pure Python (no bpy):

  python3 art/blender/ship_plan_gen.py [--out data/ship/aquila_plan.json] [--check]

It registers the existing rooms where they are, lays out Deck 4 (the first complete deck: passages, rooms, doors, signs, plates, lights
and the walk graph, ship_deck4.py) and gives every other deck a coarse but real plan (ship_decks.py): sections A-H, a spine, typed
compartments with bounds and doors, vertical links, the walk graph. The schema is described in docs/NAVE.md.
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_plan as P  # noqa: E402
import ship_spec as SP  # noqa: E402
from ship_layout import Builder, rnd  # noqa: E402

FRAME = ("Unreal convention: X forward (towards the bow), Y starboard, Z up; metres; the origin is the bridge floor point under the "
         "Captain's chair (Unreal: cm, same axes); yaw in degrees turns +X towards +Y; the hull mesh SM_SHIP_ASTRA_Aquila is placed at "
         "world (-172, 0, -62): hull frame = world + (172, 0, 62)")


def _stations_mess(D: dict, ox: float, oy: float, oz: float, cid: str) -> list[dict]:
    T = D["tables"]
    out = []
    for d in D["diners"]:
        i, j = d["table"]
        x = ox + T["x_centres"][i] + d["dx"]
        y = oy + T["y_centres"][j] + d["side"] * T["bench_offset"]
        out.append({"id": f"{cid}.{d['station']}", "role": "crew", "kind": "eat", "pos": [rnd(x), rnd(y), rnd(oz)],
                    "yaw": 90.0 if d["side"] < 0 else -90.0, "dept": "services", "station": d["station"]})
    c = D["cook"]
    out.append({"id": f"{cid}.mess_cook", "role": "cook", "kind": "work", "pos": [rnd(ox + c["x"]), rnd(oy + c["y"]), rnd(oz)], "yaw": c["yaw"],
                "dept": "services", "station": c["station"]})
    return out


def existing(B: Builder) -> None:
    """The rooms that already exist, registered where they are (their data files are the truth for their interiors)."""
    ex = {r["id"]: r for r in P.existing_rooms(0.0)}
    bridge = P._j("aquila_bridge.json")
    mess, berth, med, eng, hang = (P._j("aquila_mess.json"), P._j("aquila_berths.json"), P._j("aquila_medbay.json"), P._j("aquila_engineering.json"),
                                   P._j("aquila_hangar.json"))

    def add(rid, name, deck, plane, section, kind, bounds, z, entrance, dept, systems, stations, **kw):
        B.comp(rid, deck, kind, name, bounds, z, section=section, dept=dept, status="existing", systems=systems, stations=stations, plane=plane,
               entrance=entrance, prefab=None, existing=True, **kw)

    # ---- Deck 1: the bridge complex (levels of aquila_bridge.json: upper 0, well -0.6, dais +0.2)
    bst = []
    for st in bridge["stations"]:
        x, y = st["pos"]
        bst.append({"id": f"bridge.{st['id']}", "role": st["role"], "kind": "sit" if "seated" in st.get("seat", {}).get("posture", "") else "stand",
                    "pos": [rnd(x), rnd(y), rnd(bridge["levels"][st["level"]])], "yaw": float(st["yaw"]), "dept": "command", "station": st["id"]})
    add("bridge", "Bridge", 1, 1, "A", "bridge", [-8.5, -7.4, 10.4, 7.4], (-0.9, 4.9), None, "command", ["command", "sensors", "comms", "helm", "tactical"],
        bst, data="aquila_bridge.json")
    for side, y in (("port", -3.9), ("starboard", 3.9)):
        add(f"corridor_1a_{side}", f"Corridor 1-A ({side})", 1, 1, "A", "corridor", [-20.8, y - 1.6, -8.5, y + 1.6], (0.0, 3.0), None, "command",
            ["power_bus", "life_support"], [], data="aquila_bridge.json")
    add("lift_housing_bridge", "Bridge lift housing", 1, 1, "A", "lift", [-25.8, -8.2, -21.0, -1.0], (0.0, 3.2), None, "command", ["lift"], [],
        data="aquila_quarters.json")
    q = ex["quarters"]
    add("quarters", "Captain's Quarters", 1, 1, "A", "quarters", [q["box"][0], q["box"][1], q["box"][2], q["box"][3]], (q["box"][4], q["box"][5]),
        q["entrance"], "command", ["power_bus", "life_support"], [], data="aquila_quarters.json")
    B.comp("ready_room", 1, "ready_room", "Ready Room", [-20.2, -2.0, -9.0, 2.0], (0.0, 3.0), section="A", dept="command", status="planned",
           systems=["power_bus"], stations=[], prefab=None, note="the Captain's ready room: the block between the two corridors of Deck 1 (canon, docs/BIBBIA.md "
           "§6); its door will be cut in the port corridor's inner wall (SM_COR panel) when Deck 1 is finished", plane=1)
    # ---- Deck 3 label / Deck 4 plane: Crew Berthing
    e = ex["berths"]
    aw = [{"id": f"berths.{a['station']}", "role": "crew", "kind": "sit", "pos": [rnd(e["box"][2] - 0.3 + a["seat"][0]), rnd(a["seat"][1]), rnd(-46.0)],
           "yaw": a["yaw"], "dept": "services", "station": a["station"]} for a in berth["awake"]]
    add("berths", "Crew Berthing", 4, 4, "C", "berthing", e["box"][:4], (e["box"][4], e["box"][5]), e["entrance"], "services",
        ["power_bus", "life_support"], aw, label_deck=3, data="aquila_berths.json", capacity=84,
        note="its signage says DECK 3; it stands on the Deck 4 plane (z -46, like the Mess): the Deck 3 plane (z -42) is under the hull's inner skin here")
    # ---- Deck 4: Mess Hall
    e = ex["mess"]
    add("mess", "Mess Hall", 4, 4, "B", "mess", e["box"][:4], (e["box"][4], e["box"][5]), e["entrance"], "services", ["food_service", "power_bus", "life_support"],
        _stations_mess(mess, *mess["world_origin"], "mess"), data="aquila_mess.json", annex=e["annex"], capacity=48)
    # ---- Deck 6: Medbay
    e = ex["medbay"]
    ox, oy, oz = med["world_origin"]
    mst = [{"id": f"medbay.{c['station']}", "role": c["station"], "kind": "work", "pos": [rnd(ox + c["x"]), rnd(oy + c["y"]), rnd(oz)], "yaw": c["yaw"],
            "dept": "medical", "station": c["station"]} for c in med["crew"]]
    b = med["beds"]
    for side in (-1, 1):
        for k, bx in enumerate(b["x"]):
            mst.append({"id": f"medbay.bed{(0 if side < 0 else 6) + k + 1}", "role": "patient", "kind": "sleep", "pos": [rnd(ox + bx - 0.5), rnd(oy + side * b["y"]), rnd(oz)],
                        "yaw": 90.0 if side < 0 else -90.0, "dept": "medical"})
    add("medbay", "Medbay", 6, 6, "C", "medbay", e["box"][:4], (e["box"][4], e["box"][5]), e["entrance"], "medical", ["medical", "power_bus", "life_support"],
        mst, data="aquila_medbay.json", capacity=12)
    # ---- Deck 7: Main Engineering
    e = ex["engineering"]
    ox, oy, oz = eng["world_origin"]
    est = [{"id": f"engineering.{c['station']}", "role": c["station"], "kind": "work", "pos": [rnd(ox + c["x"]), rnd(oy + c["y"]), rnd(oz)], "yaw": c["yaw"],
            "dept": "engineering", "station": c["station"]} for c in eng["crew"]]
    add("engineering", "Main Engineering", 7, 7, "F", "engineering", e["box"][:4], (e["box"][4], e["box"][5]), e["entrance"], "engineering",
        ["reactor", "power_bus", "coolant", "engines"], est, data="aquila_engineering.json", capacity=16,
        note="a 14 m tall hall: its volume also occupies the Deck 4-6 planes at x -372..-330, |y| < 15 (keep-out for those decks)")
    # ---- Deck 9: Flight Deck
    e = ex["flight_deck"]
    add("flight_deck", "Flight Deck", 9, 9, "B", "hangar", e["box"][:4], (e["box"][4], e["box"][5]), e["entrance"], "flight",
        ["launch_tubes", "catapults", "power_bus", "life_support"], [], data="aquila_hangar.json", capacity=60, spans_decks=[6, 7, 8, 9, 10, 11],
        note="floor z -72.8 (the launch tubes open into the bow mouths); the volume 20 m tall crosses the planes of Decks 6-11 at x 60..218, |y| < 29")


BUILT_DECKS = (4, 6)    # the decks with meshes: Deck 4 by hand (ship_deck4.py), the others from their programme (ship_decks.plan_deck(coarse=False))

PROGRAMME = {   # docs/BIBBIA.md §6: the twelve decks
    1: "Bridge, Captain's quarters, ready room, command corridors",
    2: "CIC (combat information centre), briefing room, department offices, communications",
    3: "Crew Berthing, officers' quarters, gym",
    4: "Mess Hall, galley, lounge, observation deck",
    5: "science labs, Transporter Room (six pads), sensor archive",
    6: "Medbay, surgery, quarantine, pharmacy",
    7: "Main Engineering, reactor, power control, radiators",
    8: "Armory, Marine Barracks, firing range, assault-shuttle bay (two Kestrel shuttles)",
    9: "Flight Deck: launch tubes, bays, aircraft workshop, control booth",
    10: "holds, munitions magazines, stores",
    11: "workshops, fabrication, repairs, damage-control teams",
    12: "keel: tanks, reaction mass, maintenance crawlways",
}


def deck_record(d: int) -> dict:
    z0, z1 = P.deck_z(d)
    info = P.DECKS[d]
    env = P.envelope(d) if d >= 2 else {"x_fwd": 14.0, "x_aft": -31.0, "half_width": []}
    hw = env["half_width"][::2]
    return {"id": d, "name": info["name"], "programme": PROGRAMME[d], "z": z0, "clear": info["clear"], "ceiling": rnd(z1), "structure": P.STRUCT,
            "pitch": 4.0, "volume": info["volume"],
            "envelope": {"x_fwd": env["x_fwd"], "x_aft": env["x_aft"], "half_width": hw},
            "sections": [{"id": l, "x": [xmin, xmax]} for (l, xmin, xmax) in P.sections(d)]}


# ------------------------------------------------------------------------------------------------- the graph of the existing rooms
LANDINGS = {   # the lift network of AstraHangar: current landings (world, metres) inside the rooms; the bridge's is the corridor's
    "bridge": ("corridor_1a_port", (-18.6, -3.9, 0.2)),
    "flight_deck": ("flight_deck", None), "engineering": ("engineering", None), "medbay": ("medbay", None), "mess": ("mess", None),
    "berths": ("berths", None),
}


def existing_graph(B: Builder, decks: dict) -> None:
    """Hub and station nodes of the existing rooms, their entrances (a door record and a node just inside), and the joints with the
    corridors of their decks: Deck 4's are made by ship_deck4 (concourse, lobby); the others join the nearest corridor of their deck."""
    ex = {r["id"]: r for r in P.existing_rooms(0.0)}
    for cid in ("mess", "berths", "medbay", "engineering", "flight_deck"):
        rec = B.comps[cid]
        r = ex[cid]
        e = r["entrance"]
        plane = rec["plane"]
        z = rec["z"][0]
        b = rec["bounds"]
        # the landing of the lift, 2.5 m inside the entrance
        lx, ly, lz = r["landing"]
        nin = f"{cid}.in"
        B.node(nin, plane, lx, ly, lz, "door_in", cid)
        B.node(f"{cid}.hub", plane, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, z, "room", cid)
        B.link(nin, f"{cid}.hub", "walk", width=2.0)
        for st in rec["stations"]:
            B.node(st["id"], plane, st["pos"][0], st["pos"][1], st["pos"][2], "station", cid, role=st["role"], act=st["kind"], yaw=st["yaw"])
            B.link(f"{cid}.hub", st["id"], "walk", width=1.0)
        note = "the lift alcove of the room's builder: two static leaves (Mess/Lift etc.) close it; the plan treats it as the room's door"
        did = f"{cid}_entrance"
        B.door(did, plane, (e["x"] + (0.15 if e["wall"] == "fwd" else -0.15), e["y"], e.get("z", z)), 0.0, e["w"], e["h"], cid, None, kind="gate", wall=e["wall"],
               locked=False, existing=True, note=note)
        rec["entrance_door"] = did
    # the Mess and the Berthing open on the concourse and the lobby of Deck 4
    for cid, lobby in (("mess", "d4_concourse"), ("berths", "d4_berth_lobby")):
        rec = B.doors[f"{cid}_entrance"]
        rec["b"] = lobby
        B.comps[lobby]["doors"].append(rec["id"])
        B.comps[cid]["doors"].append(rec["id"])
        B.link(f"{lobby}.hub", f"{cid}.in", "door", door=rec["id"], width=rec["width"])
    # the others: a small lobby between the door and the end of the nearest corridor of their deck (within 16 m)
    for cid in ("medbay", "engineering", "flight_deck"):
        rec = B.comps[cid]
        door = B.doors[f"{cid}_entrance"]
        deck = rec["plane"]
        best, bd = None, 1e9
        for n in B.nodes.values():
            if n["deck"] == deck and n["kind"] == "corridor":
                dd = math.dist(n["p"][:2], door["pos"][:2])
                if dd < bd:
                    best, bd = n, dd
        if best is None or bd > 16.0:
            B.notes.append(f"{cid}: no corridor of Deck {deck} reaches its entrance (nearest {bd:.1f} m): the deck's plan must lead a passage to it")
            continue
        seg = B.comps[best["comp"]]
        sb = seg["bounds"]
        wall_x = rec["bounds"][2] if rec["entrance"]["wall"] == "fwd" else rec["bounds"][0]     # the outer face of the room's wall
        if seg["status"] == "built" and min(abs(wall_x - sb[0]), abs(wall_x - sb[2])) < 0.6:     # a built passage that runs right up to the door: no lobby
            B.link(best["id"], f"{cid}.in", "door", door=door["id"], width=door["width"])
            door["b"] = best["comp"]
            for c_ in (best["comp"], cid):
                if door["id"] not in B.comps[c_]["doors"]:
                    B.comps[c_]["doors"].append(door["id"])
            continue
        lo, hi = (wall_x, sb[0]) if wall_x < sb[0] else (sb[2], wall_x)
        lid = f"{cid}_lobby"
        B.comp(lid, deck, "vestibule", f"{rec['name']} lobby", [lo, -1.55, hi, 1.55], (seg["z"][0], seg["z"][1]), status="planned",
               dept=rec["dept"], systems=["power_bus", "life_support"], note="the corridor's end and the room's door meet here: the passage's last bay, "
               "finished with the room's deck")
        B.node(f"{lid}.hub", deck, (lo + hi) / 2, 0.0, seg["z"][0], "corridor", lid)
        B.link(best["id"], f"{lid}.hub", "walk", width=3.1)
        B.link(f"{lid}.hub", f"{cid}.in", "door", door=door["id"], width=door["width"])
        door["b"] = lid
        B.comps[lid]["doors"].append(door["id"])
        B.comps[cid]["doors"].append(door["id"])


def deck1_graph(B: Builder) -> None:
    """The bridge complex: bridge, its two corridors, the lift housing, the Captain's quarters, the ready room (planned)."""
    bridge = B.comps["bridge"]
    B.node("bridge.hub", 1, 0.0, 0.0, 0.0, "room", "bridge")
    for st in bridge["stations"]:
        B.node(st["id"], 1, st["pos"][0], st["pos"][1], st["pos"][2], "station", "bridge", role=st["role"], act=st["kind"], yaw=st["yaw"])
        B.link("bridge.hub", st["id"], "walk", width=1.0)
    data = P._j("aquila_bridge.json")
    for side, cid in ((-1, "corridor_1a_port"), (1, "corridor_1a_starboard")):
        d = next(x for x in data["doors"] if x["pos"][1] * side > 0)
        did = f"bridge_{d['id']}"
        B.door(did, 1, (d["pos"][0], d["pos"][1], 0.0), 0.0, d["width"], d["height"], "bridge", cid, kind="sliding", existing=True)
        B.comps["bridge"]["doors"].append(did)
        B.comps[cid]["doors"].append(did)
        B.node(f"{cid}.n0", 1, -10.0, d["pos"][1], 0.0, "corridor", cid)
        B.node(f"{cid}.n1", 1, -18.0, d["pos"][1], 0.0, "corridor", cid)
        B.link("bridge.hub", f"{cid}.n0", "door", door=did, width=d["width"])
        B.link(f"{cid}.n0", f"{cid}.n1", "walk", width=3.2)
    B.node("lift.bridge", 1, -18.6, -3.9, 0.2, "lift", "lift_housing_bridge")
    B.link("corridor_1a_port.n1", "lift.bridge", "walk", width=3.2)
    # the lift housing at the port corridor's end
    B.comps["lift_housing_bridge"]["doors"].append("bridge_door_port")
    q = B.comps["quarters"]
    qd = P._j("aquila_quarters.json")
    B.door("quarters_door", 1, (qd["world_origin"][0] + 0.15, qd["world_origin"][1], 0.0), 0.0, qd["door"]["width"], qd["door"]["height"], "corridor_1a_starboard",
           "quarters", kind="sliding", existing=True)
    q["doors"].append("quarters_door")
    B.comps["corridor_1a_starboard"]["doors"].append("quarters_door")
    B.node("quarters.in", 1, qd["world_origin"][0] - 1.5, qd["world_origin"][1], 0.0, "door_in", "quarters")
    B.node("quarters.hub", 1, qd["world_origin"][0] - 4.3, qd["world_origin"][1], 0.0, "room", "quarters")
    B.link("corridor_1a_starboard.n1", "quarters.in", "door", door="quarters_door", width=qd["door"]["width"])
    B.link("quarters.in", "quarters.hub", "walk", width=2.0)
    B.node("ready_room.in", 1, -14.6, -1.5, 0.0, "door_in", "ready_room")
    B.node("ready_room.hub", 1, -14.6, 0.0, 0.0, "room", "ready_room")
    B.door("ready_room_door", 1, (-14.6, -2.3, 0.0), 90.0, 1.6, 2.4, "corridor_1a_port", "ready_room", kind="sliding", planned=True)
    B.comps["ready_room"]["doors"].append("ready_room_door")
    B.comps["corridor_1a_port"]["doors"].append("ready_room_door")
    B.link("corridor_1a_port.n0", "ready_room.in", "door", door="ready_room_door", width=1.6)
    B.link("ready_room.in", "ready_room.hub", "walk", width=1.5)


def lift_network(B: Builder) -> dict:
    """The turbolift: every landing a node, a virtual core node joining them (a ride: fade, hum, the other deck)."""
    landings = []
    B.node("lift.core", 0, 0.0, 0.0, -30.0, "lift_core", None)
    names = {"bridge": ("corridor_1a_port", 1, (-18.6, -3.9, 0.2)), "flight_deck": ("flight_deck", 9, None), "engineering": ("engineering", 7, None),
             "medbay": ("medbay", 6, None), "mess": ("mess", 4, None), "berths": ("berths", 4, None)}
    B.link("lift.bridge", "lift.core", "lift", cost=10.0)
    landings.append({"deck": 1, "room": "corridor_1a_port", "pos": [-18.6, -3.9, 0.2], "node": "lift.bridge", "existing": True})
    for lid in ("berths", "mess", "medbay", "engineering", "flight_deck"):
        n = B.nodes[f"{lid}.in"]
        B.node(f"lift.{lid}", n["deck"], n["p"][0], n["p"][1], n["p"][2], "lift", lid)
        B.link(f"lift.{lid}", f"{lid}.in", "walk", width=1.0)
        B.link(f"lift.{lid}", "lift.core", "lift", cost=10.0)
        landings.append({"deck": B.comps[lid]["deck"], "plane": n["deck"], "room": lid, "pos": n["p"], "node": f"lift.{lid}", "existing": True})
    # the planned landing on Deck 4: in the concourse, at the lift bank on its aft wall
    B.node("lift.d4_concourse", 4, -119.1, 9.0, -46.0, "lift", "d4_concourse")
    B.link("lift.d4_concourse", "d4_concourse.hub", "walk", width=2.0)
    B.link("lift.d4_concourse", "lift.core", "lift", cost=10.0)
    landings.append({"deck": 4, "plane": 4, "room": "d4_concourse", "pos": [-119.1, 9.0, -46.0], "node": "lift.d4_concourse", "existing": False,
                     "note": "the lift bank of the concourse (its doors are part of SM_SHIP_Concourse): set AstraHangar MessLanding to this point once "
                             "the Mess's own lift leaves are removed"})
    return {"id": "lift_main", "kind": "turbolift", "name": "Turbolift", "decks": [1, 3, 4, 6, 7, 9], "landings": landings,
            "ride": {"fade_s": 0.4, "note": "a teleport between landings (AstraHangar::RideLift); not a shaft"}}


def stair_columns(B: Builder, decks: dict) -> list:
    """One vertical link per stair column: the tower compartment of every deck that has it, joined by stairs to the decks above and below
    (Deck 4's are the modelled ones: two switchback flights per deck, 4 m rise; Deck 2 to Deck 3 climbs 5.3 m through the armour deck)."""
    import ship_deck4 as D4
    out = []
    for (tx, side) in D4.STAIR_COLUMNS:
        col = {"id": f"stair_{int(abs(tx))}{'n' if tx < 0 else 'p'}", "kind": "stair", "x_min": tx, "side": side, "nodes": {}, "towers": {}, "decks": []}
        prev = None
        for n in range(2, 13):
            cid = D4.tower_id(n, tx)
            if cid not in B.comps:
                prev = None
                continue
            c = B.comps[cid]
            b = c["bounds"]
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            z = c["z"][0]
            nid = f"{cid}.stair"
            B.node(nid, n, cx, cy, z, "stair", cid)
            B.link(f"{cid}.hub", nid, "walk", width=1.5)
            if prev is not None:
                pdeck, pnid, pz = prev
                B.link(pnid, nid, "stair", cost=14.0 if abs(pz - z) < 4.5 else 24.0)
            prev = (n, nid, z)
            col["nodes"][str(n)] = nid
            col["towers"][str(n)] = cid
            col["decks"].append(n)
            col["pos"] = [rnd(cx), rnd(cy)]
        out.append(col)
    return out


def d4_open_ends(B: Builder, d4: Deck) -> None:
    """The Spine's open ends: aft into the concourse (through the blast door of the Section A/B boundary), forward into the bow observation deck."""
    ps = d4.passages["SPF"]
    B.link("d4.SPF.000", "d4_concourse.hub", "door", door=d4._blast(ps, 0, -104.0), width=2.0, blast=True)
    B.link(f"d4.SPF.{ps.n - 1:03d}", "d4_bow_obs.hub", "walk", width=3.1)


def systems_table(B: Builder) -> dict:
    """Which compartments hold which ship systems (corridors carry the buses and are not listed one by one)."""
    names = {"reactor": "Reactor and power core", "power_bus": "Power distribution", "coolant": "Coolant loops and heat exchangers",
             "radiators": "Radiator wings", "engines": "Main engines", "sensors": "Sensor arrays", "comms": "Communications",
             "weapons": "Weapons (railguns, lasers, point defence)", "ordnance": "Munitions handling", "launch_tubes": "Launch tubes and catapults",
             "life_support": "Atmosphere and life support", "potable_water": "Water", "food_service": "Galley and food stores", "supply": "Stores",
             "medical": "Medical", "damage_control": "Damage control", "transporter": "Lattice transport (transporter)", "data_trunk": "Data trunks",
             "compressed_air": "Compressed air", "fuel": "Fuel and coolant tanks", "reaction_mass": "Reaction mass", "entertainment": "Recreation",
             "command": "Command", "helm": "Helm", "tactical": "Tactical", "lift": "Lift", "waste": "Waste and recycling", "cold_chain": "Cold storage",
             "dumbwaiter": "Dumbwaiter", "catapults": "Catapults"}
    hosts: dict[str, list] = {}
    for c in B.comps.values():
        if c["kind"] == "corridor":
            continue
        for s in c.get("systems", []):
            hosts.setdefault(s, []).append(c["id"])
    return {k: {"name": names.get(k, k), "compartments": v} for k, v in sorted(hosts.items())}


def spine_shuttle() -> dict:
    """The Spine's internal shuttle (docs/BIBBIA.md §6: "the central corridor along the ship with the internal shuttle"): reserved on Deck 5
    (Science & Transport), a car on the centre line of the Spine from the forward end of the deck to the stern with a stop in every section.
    Planned only: the plan's Deck 5 is a coarse deck; the car and its rails are not built."""
    d = 5
    env = P.envelope(d)
    stops = [{"section": letter, "x": rnd((x0 + x1) / 2)} for (letter, x0, x1) in P.sections(d)]
    return {"id": "spine_shuttle", "kind": "shuttle", "name": "Spine Shuttle", "deck": d, "y": 0.0, "z": P.deck_z(d)[0],
            "x_fwd": env["x_fwd"], "x_aft": env["x_aft"], "stops": stops, "status": "planned",
            "note": "a car on the centre line of Deck 5's Spine; the crew boards it at a section stop (route-finder: a 'shuttle' edge between stops, not modelled yet)"}


def build_plan(only_decks: bool = False) -> dict:
    B = Builder()
    existing(B)
    import ship_deck4 as D4
    import ship_decks as DK
    d4 = D4.build(B)
    d4.emit()
    d4.finish_doors()
    d4_open_ends(B, d4)
    decks = {4: d4}
    for n in (2, 3, 5, 6, 7, 8, 9, 10, 11, 12):
        dk = DK.plan_deck(B, n, D4.STAIR_COLUMNS, coarse=n not in BUILT_DECKS)
        dk.emit()
        dk.finish_doors()
        decks[n] = dk
    deck1_graph(B)
    existing_graph(B, decks)
    stairs = stair_columns(B, decks)
    lift = lift_network(B)
    plan = {"id": "ASN_Aquila_Plan", "version": 1, "generator": "art/blender/ship_plan_gen.py", "frame": FRAME}
    plan["decks"] = [deck_record(d) for d in range(1, 13)]
    for c in B.comps.values():                                  # a door that two builders both added once
        c["doors"] = list(dict.fromkeys(c.get("doors", [])))
    plan["compartments"] = list(B.comps.values())
    plan["doors"] = list(B.doors.values())
    plan["vertical"] = [lift] + stairs
    plan["transit"] = [spine_shuttle()]
    plan["graph"] = {"nodes": list(B.nodes.values()), "edges": B.edges}
    plan["systems"] = systems_table(B)
    plan["placements"] = {str(d): v for d, v in B.placements.items() if v}
    plan["notes"] = B.notes
    return plan


def main() -> None:
    argv = sys.argv[1:]
    out = P.PLAN_PATH
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    plan = build_plan()
    print("compartments", len(plan["compartments"]), "doors", len(plan["doors"]), "nodes", len(plan["graph"]["nodes"]), "edges", len(plan["graph"]["edges"]),
          "placements", {k: len(v) for k, v in plan["placements"].items()})
    P.save(plan, out)
    print("wrote", out)


if __name__ == "__main__":
    main()
