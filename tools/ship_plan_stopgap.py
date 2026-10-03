#!/usr/bin/env python3
"""STOPGAP (docs/brief/ABBORDAGGI-2.md): a minimal plan for a ship's class, until FLOTTA-VIVA's real one lands.

FLOTTA-VIVA owns the per-class plans (data/ship/plans/<class>.json, the format of data/ship/aquila_plan.json). The boarding code loads <class>.json when it exists and falls back to
the file this writes (data/ship/plans/stopgap/<class>.json, "stopgap": true) when it does not, so the fights can be built and tried before the real plans are there. Delete this
script and the stopgap directory when every class has its plan. It is deliberately small: a spine corridor with cross corridors and two ring passages (so a flank has a way round),
rooms in two bands, stairs, pressure bulkheads between sections, the halls that matter to a boarding (bridge, engineering, boat bay), the commander's suite, an armoury, a medbay, a brig,
and boarding locks along the skin with their docks. Hull frame: X forward, Y starboard, Z up, metres, origin at the mesh origin, deck 1 on top.

    python3 tools/ship_plan_stopgap.py [class ...]      # writes the stopgap plans (default: every class)
    python3 tools/ship_plan_stopgap.py --check          # builds and validates only
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ship" / "plans" / "stopgap"
PITCH, CLEAR, CW = 4.0, 3.4, 4.0          # floor to floor, floor to ceiling, a corridor's width

# hull_x and width are the war's (data/war/classes.json); core: where the habitable decks stand; hb: the half beam of the rooms; bridge/engineering/hangar: halls (x range, deck)
CLASSES = {
    "acheron": dict(label="Kharon Mandate cruiser, Acheron class", side="mandate", hull_x=(-323, 264), width=105, decks=10, core=(-250, 215), hb=36, cross=90, crew=320,
                    bridge=((150, 200), 1), engineering=((-248, -196), 8, 3), hangar=((-52, 52), 5, 2), dock_deck=5),
    "styx": dict(label="Kharon Mandate destroyer, Styx class", side="mandate", hull_x=(-212, 175), width=81, decks=7, core=(-165, 140), hb=28, cross=80, crew=140,
                 bridge=((95, 138), 1), engineering=((-163, -118), 6, 2), hangar=((-40, 40), 4, 2), dock_deck=4),
    "lethe": dict(label="Kharon Mandate frigate, Lethe class", side="mandate", hull_x=(-127, 113), width=61, decks=5, core=(-100, 90), hb=21, cross=70, crew=60,
                  bridge=((58, 88), 1), engineering=((-98, -62), 4, 2), hangar=((-30, 28), 3, 1), dock_deck=3),
    "praetorian": dict(label="ASTRA battleship (7th Fleet flagship)", side="astra", hull_x=(-579, 550), width=184, decks=10, core=(-460, 420), hb=52, cross=110, crew=900,
                       bridge=((330, 394), 1), engineering=((-458, -392), 8, 3), hangar=((-80, 80), 5, 2), dock_deck=5),
    "vigilant": dict(label="ASTRA destroyer", side="astra", hull_x=(-156, 150), width=54, decks=6, core=(-120, 115), hb=20, cross=75, crew=110,
                     bridge=((78, 112), 1), engineering=((-118, -80), 5, 2), hangar=((-30, 30), 3, 2), dock_deck=3),
}
# the rooms of each deck, in order (a bay's rooms cycle through them)
THEMES = ["offices quarters comms storage", "cabins cabins wardroom heads", "mess galley lab storage", "berthing berthing berthing heads", "workshop storage damage_control heads",
          "storage tank magazine storage", "machinery power machinery workshop", "machinery tank machinery damage_control", "storage storage tank storage", "storage storage storage tank"]
NAMES = {"offices": "Office", "quarters": "Officer's Cabin", "comms": "Comms Room", "storage": "Stores", "cabins": "Cabins", "wardroom": "Wardroom", "heads": "Heads", "mess": "Mess Hall",
         "galley": "Galley", "lab": "Laboratory", "berthing": "Crew Berthing", "workshop": "Workshop", "damage_control": "Damage Control", "tank": "Tank", "magazine": "Magazine",
         "machinery": "Machinery Space", "power": "Power Room", "armory": "Armoury", "medbay": "Medbay", "brig": "Brig", "airlock": "Boarding Lock"}


def r2(v: float) -> float:
    return round(v + 0.0, 3)


class Builder:
    def __init__(self, key: str, p: dict):
        self.key, self.p = key, p
        self.comps, self.doors, self.nodes, self.edges, self.docks = [], [], [], [], []
        self.objectives: dict[str, str] = {}
        self.byid: dict[str, dict] = {}
        self.z = {d: -PITCH * (d - 1) for d in range(1, p["decks"] + 1)}
        xa, xf = p["core"]
        n = max(2, round((xf - xa) / p["cross"]))
        self.edges_x = [xa + (xf - xa) * i / n for i in range(n + 1)]            # the bays' edges; the crosses stand on the inner ones
        self.hb = p["hb"]
        self.towers: dict[int, dict[int, str]] = {}

    def section(self, x: float) -> str:
        return chr(ord("A") + max(0, min(int((self.p["core"][1] - x) // 100), 25)))

    def comp(self, cid, deck, kind, name, x0, y0, x1, y1, z0=None, z1=None, **extra):
        z0 = self.z[deck] if z0 is None else z0
        c = {"id": cid, "deck": deck, "section": self.section(0.5 * (x0 + x1)), "kind": kind, "name": name, "bounds": [r2(x0), r2(y0), r2(x1), r2(y1)], "z": [r2(z0), r2(z0 + CLEAR if z1 is None else z1)],
             "status": "built", "doors": [], "dept": extra.pop("dept", "neutral"), "systems": extra.pop("systems", []), **extra}
        self.comps.append(c)
        self.byid[cid] = c
        self.nodes.append({"id": cid + ".n", "deck": deck, "p": [r2(0.5 * (x0 + x1)), r2(0.5 * (y0 + y1)), r2(z0)], "kind": kind, "comp": cid})
        return c

    def link(self, a, b, kind="walk", w=3.1, door=None, blast=False, **extra):
        e = {"a": a + ".n", "b": b + ".n", "len": 4.0, "kind": "door" if door else kind, "w": w, **extra}
        if door:
            e["door"] = door
            e["blast"] = blast
        self.edges.append(e)

    def door(self, did, deck, x, y, yaw, a, b, w=1.6, h=2.4, blast=False, boundary=None):
        d = {"id": did, "deck": deck, "pos": [r2(x), r2(y), r2(self.z[deck])], "yaw": yaw, "width": w, "height": h, "kind": "blast" if blast else "door", "a": a, "b": b, "locked": False}
        if blast:
            d.update(blast=True, boundary=boundary)
        self.doors.append(d)
        for cid in (a, b):
            self.byid[cid]["doors"].append(did)
        self.link(a, b, door=did, blast=blast, w=w)

    def corridor_run(self, deck, tag, y0, y1, pieces, crosses, name):
        """Corridor comps along [pieces], split at the crosses (a junction 4 m wide at each): returns the list in x order."""
        out = []
        for a, b in pieces:
            cs = [x for x in crosses if a + 3 < x < b - 3]
            pts = [a] + [v for x in cs for v in (x - 2, x + 2)] + [b]
            prev = None
            for k in range(len(pts) - 1):
                x0, x1 = pts[k], pts[k + 1]
                junction = k % 2 == 1
                n = 1 if junction else max(1, math.ceil((x1 - x0) / 60))
                for j in range(n):
                    w = (x1 - x0) / n
                    c = self.comp(f"d{deck}_{tag}_{int(a)}_{k}_{j}", deck, "corridor", name, x0 + w * j, y0, x0 + w * (j + 1), y1, systems=["power_bus", "life_support"], junction=junction)
                    if prev is not None:
                        sa, sb = prev["section"], c["section"]
                        if sa != sb:
                            self.door(f"d{deck}_bulk_{tag}_{int(a)}_{k}_{j}", deck, c["bounds"][0], 0.5 * (y0 + y1), 0.0, prev["id"], c["id"], 2.0, 2.5, True, [sb, sa])
                        else:
                            self.link(prev["id"], c["id"], w=CW)
                    prev = c
                    out.append(c)
        return out

    def at(self, run, x):
        return next((c for c in run if c["bounds"][0] - 0.01 <= x <= c["bounds"][2] + 0.01), None)

    def build(self) -> dict:
        p = self.p
        xa, xf = p["core"]
        crosses = self.edges_x[1:-1]
        halls = {}
        (bx, bd) = p["bridge"]
        halls[bd] = halls.get(bd, []) + [dict(id="bridge", kind="bridge", name="Bridge", x=bx, y=(-14, 14), dept="command", systems=["command", "sensors", "comms", "helm", "tactical"])]
        ex, ed, en = p["engineering"]
        hx, hd, hn = p["hangar"]
        for k, (x, d0, nd, hid, kind, name, sys_) in enumerate([(ex, ed, en, "engineering", "engineering", "Main Engineering", ["reactor", "power_bus", "coolant", "engines"]),
                                                                 (hx, hd, hn, "hangar", "hangar", "Boat Bay", ["launch_tubes", "power_bus", "life_support"])]):
            for d in range(d0, d0 + nd):
                bottom = d == d0 + nd - 1
                halls.setdefault(d, []).append(dict(id=hid if bottom else f"d{d}_{hid}_void", kind=kind if bottom else None, name=name, x=x, y=(-20 if hid == "engineering" else -26, 20 if hid == "engineering" else 26),
                                                    spans=list(range(d0, d0 + nd)) if bottom else None, z1=self.z[d0] + CLEAR if bottom else None, dept="engineering" if hid == "engineering" else "flight", systems=sys_))
        runs = {}
        for deck in range(1, p["decks"] + 1):
            xs = max(xa, p["bridge"][0][0] - 130) if deck == 1 else xa
            xe = xf
            cuts = sorted((h["x"][0], h["x"][1]) for h in halls.get(deck, []))
            pieces, cur = [], xs
            for a, b in cuts:
                if a - cur > 6:
                    pieces.append((cur, a))
                cur = max(cur, b)
            if xe - cur > 6:
                pieces.append((cur, xe))
            spine = self.corridor_run(deck, "sp", -CW / 2, CW / 2, pieces, crosses, "Spine")
            rpieces = [(a, b) for a, b in pieces if any(a + 3 < x < b - 3 for x in crosses)]          # a ring needs a cross to be reached by
            ringS = self.corridor_run(deck, "rs", 14, 18, rpieces, crosses, "Starboard Passage")
            ringP = self.corridor_run(deck, "rp", -18, -14, rpieces, crosses, "Port Passage")
            # the crosses: an arm from the spine's junction to the ring's, each side
            for c in spine:
                if c.get("junction"):
                    xc = 0.5 * (c["bounds"][0] + c["bounds"][2])
                    for side, y0, y1, ring in (("s", 2, 14, ringS), ("p", -14, -2, ringP)):
                        arm = self.comp(f"d{deck}_cr{int(xc)}{side}", deck, "corridor", "Cross Corridor", xc - 2, y0, xc + 2, y1, systems=["power_bus", "life_support"])
                        self.link(c["id"], arm["id"], w=CW)
                        rj = self.at([r for r in ring if r.get("junction")], xc)
                        if rj:
                            self.link(arm["id"], rj["id"], w=CW)
                        if side == "s":
                            # the stair tower stands against the arm, in the inner band; the same place on every deck, so the decks' towers meet
                            tw = self.comp(f"d{deck}_stair{int(xc)}", deck, "stairs", "Stair Tower", xc + 2, 2, xc + 8, 8, systems=["power_bus"])
                            self.door(f"d{deck}_door_stair{int(xc)}", deck, xc + 2, 5, 0.0, tw["id"], arm["id"])
                            self.towers.setdefault(int(xc), {})[deck] = tw["id"]
            # the rooms: each bay's two bands, a fixed number to a bay so the stairs line up from deck to deck
            theme = THEMES[(deck - 1) % len(THEMES)].split()
            for i in range(len(self.edges_x) - 1):
                a, b = self.edges_x[i] + (2 if i > 0 else 0), self.edges_x[i + 1] - (2 if i + 1 < len(self.edges_x) - 1 else 0)
                if not any(pa - 0.01 <= a and b <= pb + 0.01 for pa, pb in pieces):
                    continue
                n = max(2, round((b - a) / (13 + 0.06 * (xf - xa) / 10)))
                for side, sg in (("S", 1), ("P", -1)):
                    for band, d0, d1, host in (("in", 2, 14, spine), ("out", 18, self.hb, ringS if sg > 0 else ringP)):
                        a1 = a + (6 if (band == "in" and sg > 0 and i > 0) else 0)            # (the stair tower stands there)
                        for k in range(n):
                            x0, x1 = a1 + (b - a1) * k / n, a1 + (b - a1) * (k + 1) / n
                            kind = theme[(k + i + (0 if band == "in" else 2)) % len(theme)]
                            y0, y1 = (d0, d1) if sg > 0 else (-d1, -d0)
                            rid = f"d{deck}_{kind}_{band}{side}_{i}_{k}"
                            hc = self.at(host, 0.5 * (x0 + x1))
                            if not hc:
                                continue
                            self.comp(rid, deck, kind, NAMES.get(kind, kind.title()), x0, y0, x1, y1, crew_slots=2, systems=["power_bus"], bay=i, slot=k, band=band, side=side)
                            self.door(f"d{deck}_door_{rid}", deck, 0.5 * (x0 + x1), sg * d0, 90.0, rid, hc["id"])
            # the halls: entered by a door at floor level from the spine piece that meets their wall
            for h in halls.get(deck, []):
                if h["kind"] is None:
                    continue
                hall = self.comp(h["id"], h["spans"][-1] if h.get("spans") else deck, h["kind"], h["name"], h["x"][0], h["y"][0], h["x"][1], h["y"][1], z0=self.z[deck] if not h.get("spans") else self.z[h["spans"][-1]],
                                 z1=h.get("z1"), dept=h["dept"], systems=h["systems"], crew_slots=12, **({"spans_decks": h["spans"]} if h.get("spans") else {}))
                for sp in spine:
                    if abs(sp["bounds"][2] - h["x"][0]) < 0.6 or abs(sp["bounds"][0] - h["x"][1]) < 0.6:
                        wall = h["x"][0] if abs(sp["bounds"][2] - h["x"][0]) < 0.6 else h["x"][1]
                        self.door(f"d{deck}_door_{h['id']}_{int(wall)}", deck, wall, 0.0, 0.0, h["id"], sp["id"], 3.0, 3.2)
        self.stairs_docks_objectives()
        return self.finish()

    def stairs_docks_objectives(self):
        p = self.p
        rooms = [c for c in self.comps if "bay" in c]
        # stairs: the towers of consecutive decks at the same cross are joined
        for xc, by_deck in self.towers.items():
            for d, tid in by_deck.items():
                if d + 1 in by_deck:
                    self.link(tid, by_deck[d + 1], kind="stair", cost=22.0)
        # boarding locks: the outer rooms of the dock deck, every third bay, both sides, with their docks on the skin
        dd = p["dock_deck"]
        for c in rooms:
            if c["deck"] == dd and c["band"] == "out" and c["slot"] == 0 and c["bay"] % 2 == 0 and c["kind"] != "stairs":
                c.update(kind="airlock", name="Boarding Lock", dept="security", systems=["life_support", "power_bus"])
                side = "starboard" if c["side"] == "S" else "port"
                x = 0.5 * (c["bounds"][0] + c["bounds"][2])
                self.docks.append({"id": c["id"] + ".dock", "comp": c["id"], "face": side, "pos": [r2(x), r2(self.hb if side == "starboard" else -self.hb), r2(self.z[dd] + 1.6)],
                                   "normal": [0.0, 1.0 if side == "starboard" else -1.0, 0.0], "deck": dd})
        # the rooms that matter: the commander's suite beside the bridge, an armoury, a medbay, a brig and the comms room
        def pick(deck, band, side, near, kinds=None):
            cand = [c for c in rooms if c["deck"] == deck and c["band"] == band and c["side"] == side and c["kind"] not in ("stairs", "airlock") and (kinds is None or c["kind"] in kinds)]
            cand.sort(key=lambda c: abs(0.5 * (c["bounds"][0] + c["bounds"][2]) - near))
            return cand[0] if cand else None
        bx = self.p["bridge"][0]
        want = [("captain", pick(1, "in", "S", bx[0] - 25), "quarters", "Archon's Suite" if p["side"] == "mandate" else "Captain's Quarters"),
                ("comms", pick(1, "in", "P", bx[0] - 25), "comms", "Comms Room"),
                ("armory", pick(dd, "in", "P", 0), "armory", NAMES["armory"]), ("medbay", pick(dd - 1 if dd > 2 else dd, "in", "S", 0), "medbay", "Medbay"), ("brig", pick(dd, "in", "S", -60), "brig", "Brig")]
        for name, c, kind, label in want:
            if c:
                c.update(kind=kind, name=label)
                self.objectives[name] = c["id"]
        self.objectives.update(bridge="bridge", engineering="engineering", hangar="hangar")

    def finish(self) -> dict:
        p = self.p
        xa, xf = p["core"]
        decks = [{"id": d, "name": f"Deck {d}", "z": self.z[d], "clear": CLEAR, "ceiling": r2(self.z[d] + CLEAR), "structure": 0.3, "pitch": PITCH,
                  "envelope": {"x_fwd": xf, "x_aft": xa, "half_width": [[xf, self.hb * 0.6], [xf - 20, self.hb], [xa + 20, self.hb], [xa, self.hb * 0.6]]}, "sections": []} for d in range(1, p["decks"] + 1)]
        n = p["crew"]
        garrison = [{"comp": "bridge", "n": max(4, n // 40), "role": "bridge crew"}, {"comp": "engineering", "n": max(4, n // 35), "role": "engineering watch"},
                    {"comp": "hangar", "n": max(2, n // 80), "role": "boat crews"}]
        for name, role, k in (("armory", "armoury guard", 2), ("captain", "the commander's guard", 3), ("medbay", "medical staff", 2), ("comms", "comms watch", 2)):
            if name in self.objectives:
                garrison.append({"comp": self.objectives[name], "n": k, "role": role})
        return {"id": f"{self.key}_stopgap", "version": 1, "stopgap": True, "generator": "tools/ship_plan_stopgap.py", "class": self.key, "label": p["label"], "side": p["side"],
                "frame": "hull frame: X forward, Y starboard, Z up; metres; origin at the mesh origin; deck 1 on top", "origin_in_hull": [0.0, 0.0, 0.0], "hull_x": list(p["hull_x"]), "width": p["width"], "decks": decks,
                "compartments": self.comps, "doors": self.doors, "vertical": [], "transit": [], "graph": {"nodes": self.nodes, "edges": self.edges}, "systems": {}, "placements": [],
                "docks": self.docks, "garrison": garrison, "objectives": self.objectives, "crew": n,
                "notes": ["STOPGAP: replaced by FLOTTA-VIVA's data/ship/plans/<class>.json when it exists"]}


def validate(plan: dict) -> list[str]:
    errs = []
    ids = {c["id"] for c in plan["compartments"]}
    if len(ids) != len(plan["compartments"]):
        errs.append("duplicate ids")
    node = {n["id"]: n["comp"] for n in plan["graph"]["nodes"]}
    adj = {i: set() for i in ids}
    for e in plan["graph"]["edges"]:
        a, b = node.get(e["a"]), node.get(e["b"])
        if a is None or b is None:
            errs.append(f"bad edge {e}")
            continue
        adj[a].add(b)
        adj[b].add(a)
    if not plan["docks"]:
        return errs + ["no docks"]
    seen, stack = {plan["docks"][0]["comp"]}, [plan["docks"][0]["comp"]]
    while stack:
        for w in adj[stack.pop()]:
            if w not in seen:
                seen.add(w)
                stack.append(w)
    if ids - seen:
        errs.append(f"{len(ids - seen)} compartments unreachable: {sorted(ids - seen)[:6]}")
    by = {c["id"]: c for c in plan["compartments"]}
    for d in plan["doors"]:
        ok = any(by[c]["bounds"][0] - 0.1 <= d["pos"][0] <= by[c]["bounds"][2] + 0.1 and by[c]["bounds"][1] - 0.1 <= d["pos"][1] <= by[c]["bounds"][3] + 0.1 for c in (d["a"], d["b"]))
        if not ok:
            errs.append(f"door {d['id']} off its walls")
    for k in ("bridge", "engineering", "captain"):
        if k not in plan["objectives"]:
            errs.append(f"no {k}")
    return errs


def main() -> int:
    keys = [a for a in sys.argv[1:] if not a.startswith("-")] or list(CLASSES)
    OUT.mkdir(parents=True, exist_ok=True)
    bad = 0
    for k in keys:
        plan = Builder(k, CLASSES[k]).build()
        errs = validate(plan)
        print(f"{k}: {len(plan['compartments'])} compartments, {len(plan['doors'])} doors, {len(plan['graph']['edges'])} links, {len(plan['docks'])} docks" + (f"  ERRORS: {errs[:4]}" if errs else ""))
        bad += bool(errs)
        if "--check" not in sys.argv:
            (OUT / f"{k}.json").write_text(json.dumps(plan, separators=(",", ":")))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
