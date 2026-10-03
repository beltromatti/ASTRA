"""ASTRA ships: what makes a class plan more than a layout (FLOTTA-VIVA): the boarding hatches on the skin (`docks`), the systems the rooms
carry, the objectives a boarding party goes for, the crew's roster (the garrison at action stations, the routine, the billets of the officers
who matter), the damage-control parties, and the plan's dict. A mixin of ship_class_build.Builder. Pure Python."""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from ship_class_engine import KINDS, r2  # noqa: E402

FRAME = ("The hull mesh's own frame (the hull_m box of data/war/classes.json): X to the bow, Y to starboard, Z up, metres; the origin is the mesh's origin, "
         "so a point on the hull skin is a point of the plan (origin_in_hull is zero). Yaw in degrees turns +X towards +Y.")

# the groups the crew is divided into at action stations: group -> the rooms that take it (by role, else by kind)
GROUP_ROOMS = {
    "bridge": dict(roles=("bridge",)),
    "control": dict(kinds=("cic", "comms", "weapons_control")),
    "gunnery": dict(kinds=("weapons",)),
    "magazine": dict(kinds=("magazine",)),
    "engineering": dict(kinds=("engineering", "engines", "power", "coolant")),
    "damage_control": dict(kinds=("damage_control",)),
    "medical": dict(kinds=("medbay", "surgery")),
    "flight": dict(kinds=("hangar", "flight_ops")),
    "sensors": dict(kinds=("sensors", "computer")),
}
RESERVE_KINDS = ("berthing", "cabins", "mess", "lounge", "gym", "chapel", "wardroom", "galley")


def allocate(rooms, n: int):
    """n people over the rooms in proportion to their crew slots (their area where none has any), whole numbers that add up."""
    if n <= 0 or not rooms:
        return []
    w = [max(0.0, float(r.get("crew_slots", 0))) for r in rooms]
    if sum(w) <= 0:
        w = [max(1.0, (r["bounds"][2] - r["bounds"][0]) * (r["bounds"][3] - r["bounds"][1])) for r in rooms]
    tot = sum(w)
    raw = [n * x / tot for x in w]
    base = [int(v) for v in raw]
    left = n - sum(base)
    order = sorted(range(len(rooms)), key=lambda i: raw[i] - base[i], reverse=True)
    for i in order[:left]:
        base[i] += 1
    return [(r, b) for r, b in zip(rooms, base) if b > 0]


class Finish:
    # --------------------------------------------------------------------------------------------------------------- docks
    def make_docks(self):
        out = []
        for dk in self.dock_specs:
            if dk.get("kind", "hatch") == "hatch":
                comp = self.by_id[dk["comp"]]
                d = self.deck[comp["deck"]]
                side = dk["side"]
                zmid = d.z + 1.4
                xu = dk.get("x_used", dk["x"])
                skin = self.hull.side_skin(xu, zmid, side)
                if skin < 1.0:
                    skin = d.hw(xu) + self.wall
                face = "starboard" if side > 0 else "port"
                out.append({"id": dk["id"], "comp": comp["id"], "face": face, "pos": [r2(xu), r2(side * skin), r2(zmid)], "normal": [0.0, float(side), 0.0],
                            "deck": d.id, "kind": "hatch", "width": 2.0, "height": 2.2})
            else:
                hall = next(h for h in self.halls if h["id"] == dk["hall"])
                comp = self.by_id[hall["comp"]]
                face = dk["face"]
                hb = self.hull.bounds
                if "pos" in dk:
                    pos = list(dk["pos"])
                    normal = {"bow": [1.0, 0.0, 0.0], "stern": [-1.0, 0.0, 0.0], "starboard": [0.0, 1.0, 0.0], "port": [0.0, -1.0, 0.0], "dorsal": [0.0, 0.0, 1.0],
                              "ventral": [0.0, 0.0, -1.0]}[face]
                    out.append({"id": dk["id"], "comp": comp["id"], "face": face, "pos": [r2(v) for v in pos], "normal": normal,
                                "deck": comp["deck"], "kind": dk["kind"], "width": dk.get("width", 8.0), "height": dk.get("height", 5.0)})
                    continue
                if face in ("starboard", "port"):
                    side = 1 if face == "starboard" else -1
                    pos, normal = [dk["x"], side * self.hull.side_skin(dk["x"], dk["z"], side), dk["z"]], [0.0, float(side), 0.0]
                elif face == "bow":
                    pos, normal = [hb["max"][0], 0.0, dk["z"]], [1.0, 0.0, 0.0]
                elif face == "stern":
                    pos, normal = [hb["min"][0], 0.0, dk["z"]], [-1.0, 0.0, 0.0]
                else:
                    pos, normal = [dk["x"], 0.0, hb["min"][2] if face == "ventral" else hb["max"][2]], [0.0, 0.0, -1.0 if face == "ventral" else 1.0]
                out.append({"id": dk["id"], "comp": comp["id"], "face": face, "pos": [r2(v) for v in pos], "normal": normal,
                            "deck": comp["deck"], "kind": dk["kind"], "width": dk.get("width", 8.0), "height": dk.get("height", 5.0)})
        self.docks = out

    # --------------------------------------------------------------------------------------------------------------- systems and objectives
    def make_systems(self):
        names = {"reactor": "Reactor", "coolant": "Coolant", "weapons": "Weapons", "ordnance": "Ordnance", "sensors": "Sensors", "data_trunk": "Data trunk",
                 "life_support": "Life support", "catapults": "Launch systems", "power_bus": "Power bus", "engines": "Engines", "damage_control": "Damage control",
                 "command": "Command", "comms": "Communications", "food_service": "Food service", "compressed_air": "Compressed air"}
        out = {}
        for c in self.comps:
            for s in c["systems"]:
                out.setdefault(s, {"name": names.get(s, s.title()), "compartments": []})["compartments"].append(c["id"])
        return out

    def make_objectives(self):
        roles = {}
        for c in self.comps:
            r = c.get("role")
            if r and r not in ("spine", "passage", "cross") and r not in roles:
                roles[r] = c["id"]
        want = ("bridge", "engineering", "captain", "armory", "medbay", "brig", "comms", "hangar")
        obj = {k: roles.get(k) for k in want}
        for k, v in roles.items():
            if k not in obj:
                obj[k] = v
        return obj

    # --------------------------------------------------------------------------------------------------------------- the crew
    def rooms_of(self, group: str):
        spec = GROUP_ROOMS[group]
        out = [c for c in self.comps if (c.get("role") in spec.get("roles", ())) or (c["kind"] in spec.get("kinds", ()) and c.get("role") not in ("spine", "passage", "cross"))]
        return out

    def make_crew(self):
        cs = self.spec["crew"]
        total, marines = cs["complement"], cs.get("marines", 0)
        shares = cs["shares"]
        garrison, left = [], total - marines
        for g, share in shares.items():
            rooms = self.rooms_of(g)
            n = min(left, int(round(share * total)))
            if not rooms or n <= 0:
                continue
            for r, k in allocate(rooms, n):
                garrison.append({"comp": r["id"], "n": k, "role": g})
            left -= n
        # the guards at the points a boarding party goes for: the armoury, the bridge, the reactor hall, and the vestibules of the hatches
        if marines:
            targets = []
            def pick(role=None, kinds=()):
                return [c for c in self.comps if (role and c.get("role") == role) or (c["kind"] in kinds)]
            share = [("armory", pick("armory", ("armory",)), 0.30), ("bridge", pick("bridge"), 0.20), ("engineering", pick("reactor", ("engineering",)), 0.20),
                     ("boarding_defence", [c for c in self.comps if c["kind"] == "vestibule"] or [c for c in self.comps if c["kind"] == "airlock"], 0.30)]
            used = 0
            for i, (g, rooms, f) in enumerate(share):
                n = int(round(marines * f)) if i < len(share) - 1 else marines - used
                if not rooms:
                    n = 0
                used += n
                for r, k in allocate(rooms[:6] if g == "boarding_defence" else rooms[:1], n):
                    garrison.append({"comp": r["id"], "n": k, "role": "marines" if g != "boarding_defence" else "marines_dock"})
            if used < marines:
                left += marines - used
        # whoever is left is the reserve: standing by in the quarters, the mess and the lounges
        reserve = [c for c in self.comps if c["kind"] in RESERVE_KINDS]
        for r, k in allocate(reserve, left):
            garrison.append({"comp": r["id"], "n": k, "role": "reserve"})
        merged = {}
        for g in garrison:
            key = (g["comp"], g["role"])
            merged[key] = merged.get(key, 0) + g["n"]
        self.garrison = [{"comp": k[0], "n": n, "role": k[1]} for k, n in merged.items()]
        # the billets of the officers who matter, in the order the command passes
        billets = []
        for i, b in enumerate(cs["billets"], 1):
            rooms = [c for c in self.comps if c.get("role") == b["at"]]
            if not rooms:
                self.notes.append(f"billet {b['role']}: no room with the role {b['at']}")
                continue
            r = rooms[0]
            x0, y0, x1, y1 = r["bounds"]
            billets.append({"role": b["role"], "rank": b.get("rank") or cs["ranks"].get(b["role"], "Officer"), "line": b.get("line", i), "post": r["id"],
                            "stands": [r2(x0 + (x1 - x0) * b.get("fx", 0.5)), r2(0.5 * (y0 + y1)), r2(r["z"][0])]})
        # the routine: a third of the control crews on watch, the rest off duty in the quarters
        on_watch = []
        for g in self.garrison:
            if g["role"] in ("bridge", "control", "engineering", "damage_control", "sensors", "flight", "medical"):
                on_watch.append({"comp": g["comp"], "n": max(1, -(-g["n"] // cs.get("watches", 3))), "role": g["role"]})
        onw = sum(w["n"] for w in on_watch)
        homes = []
        quarters = [c for c in self.comps if c["kind"] in ("berthing", "cabins", "quarters")] or reserve
        for r, k in allocate(quarters, max(0, total - onw)):
            homes.append({"comp": r["id"], "n": k})
        self.crew_rec = {"complement": total, "marines": marines, "watches": cs.get("watches", 3), "ranks": cs["ranks"], "billets": billets,
                         "routine": {"on_watch": on_watch, "off_duty": homes},
                         "officers": cs.get("officers", max(4, total // 14)), "shares": {k: v for k, v in shares.items()}}

    def make_parties(self):
        dc = self.spec.get("dc", {"parties": 3, "size": 4})
        rooms = sorted([c for c in self.comps if c["kind"] == "damage_control"], key=lambda c: -(c["bounds"][0] + c["bounds"][2]))
        parties = []
        if rooms:
            k = min(dc["parties"], len(rooms))
            picks = [rooms[int(round(i * (len(rooms) - 1) / max(1, k - 1)))] for i in range(k)] if k > 1 else [rooms[0]]
            seen = set()
            uniq = []
            for p in picks:
                if p["id"] not in seen:
                    uniq.append(p)
                    seen.add(p["id"])
            for i in range(dc["parties"]):
                home = uniq[i % len(uniq)]
                parties.append({"id": i, "home": home["id"], "size": dc["size"]})
        central = next((c["id"] for c in self.comps if c.get("role") == "dc_central"), rooms[0]["id"] if rooms else None)
        self.parties = {"parties": parties, "central": central, "work": dc.get("work", 1.0)}

    # --------------------------------------------------------------------------------------------------------------- the plan
    def assemble(self) -> dict:
        self.make_docks()
        classes = json.load(open(os.path.join(ROOT, "data", "war", "classes.json"), encoding="utf-8"))["classes"]
        cls = next((c for c in classes if c["key"] == self.key), {})
        for c in self.comps:                                   # (the private notes of the builder do not go out)
            for k in [k for k in c if k.startswith("_")]:
                del c[k]
        hb = self.hull.bounds
        # the war's weapon mounts (data/war/classes.json) and the rooms that serve them: a room wrecked or without power takes its mount with it
        mounts = []
        cm, roles = cls.get("mounts", []), self.spec.get("mounts", [])
        if len(cm) != len(roles):
            self.notes.append(f"PROBLEM mounts: the class has {len(cm)}, the spec names {len(roles)}")
        for i, (m, role) in enumerate(zip(cm, roles)):
            comp = next((c for c in self.comps if c.get("role") == role), None)
            mounts.append({"i": i, "kind": m["kind"], "dir": m["dir"], "section": m.get("section", 1), "role": role, "comp": comp["id"] if comp else None})
        plan = {
            "id": f"{self.key}_plan", "class": self.key, "version": 1, "generator": "art/blender/ship_class_plans.py", "style": self.spec.get("style", "astra"),
            "label": self.spec.get("label", self.key), "frame": FRAME, "origin_in_hull": [0.0, 0.0, 0.0],
            "hull": {"mesh": self.hull.mesh, "x": [r2(hb["min"][0]), r2(hb["max"][0])], "y": [r2(hb["min"][1]), r2(hb["max"][1])], "z": [r2(hb["min"][2]), r2(hb["max"][2])],
                     "cuts_x": cls.get("cuts_x_m", [0, 0]), "box": cls.get("hull_m", {})},
            "decks": [d.record() for d in self.decks],
            "compartments": self.comps, "doors": self.doors, "vertical": self.vertical, "transit": [],
            "graph": {"nodes": self.nodes, "edges": self.edges},
            "systems": self.make_systems(), "placements": {},
            "docks": self.docks, "mounts": mounts, "objectives": self.make_objectives(), "garrison": self.garrison, "crew": self.crew_rec["complement"], "roster": self.crew_rec, "damage_control": self.parties,
            "notes": self.notes + list(self.spec.get("notes", [])),
        }
        return plan
