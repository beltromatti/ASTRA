"""ASTRA ships: the builder of a class plan (FLOTTA-VIVA): from a spec (ship_class_specs.py) and the measured hull (ship_class_hull.py) to the
plan's dict (decks, compartments, doors, the walk graph, systems, docks, objectives, garrison, crew, damage-control parties). The layout rules
are in ship_class_engine.py's docstring. Pure Python."""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ship_class_engine as E  # noqa: E402
from ship_class_finish import Finish  # noqa: E402
from ship_class_wire import Wiring  # noqa: E402
from ship_class_engine import (BLAST_H, BLAST_W, CORR_H, CROSS_W, DOOR_H, DOOR_W, KINDS, MIN_DEPTH, MIN_LEN, PASS_HW, SPINE_HW, STAIR_SIZE, STRIP, WALL,
                               Deck, clamp, r2)  # noqa: E402

ROWS = {"IP": (-1, "inner"), "IS": (1, "inner"), "OP": (-1, "outer"), "OS": (1, "outer")}


# ------------------------------------------------------------------------------------------------------------------ intervals
def iv_subtract(ivs, cuts):
    """The intervals of ivs with the cuts taken out (all (a, b) with a < b)."""
    out = []
    for a, b in ivs:
        parts = [(a, b)]
        for c0, c1 in cuts:
            nxt = []
            for p0, p1 in parts:
                if c1 <= p0 or c0 >= p1:
                    nxt.append((p0, p1))
                    continue
                if c0 > p0:
                    nxt.append((p0, c0))
                if c1 < p1:
                    nxt.append((c1, p1))
            parts = nxt
        out += [(p0, p1) for p0, p1 in parts if p1 - p0 > 1e-6]
    return sorted(out)


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


class Layout:
    """What one deck holds, by kind of thing (the doors and the stairs find their neighbours here)."""

    def __init__(self):
        self.spine, self.cross, self.rooms, self.halls = [], [], [], []
        self.passage = {1: [], -1: []}
        self.stairs, self.airlocks, self.vestibules = [], [], []


# ------------------------------------------------------------------------------------------------------------------ the builder
class Builder(Wiring, Finish):
    def __init__(self, spec: dict):
        self.spec = spec
        self.key = spec["key"]
        self.hull = E.HULL.Hull(self.key)
        self.wall = spec.get("wall", 2.5)
        self.sections = spec["sections"]                        # bow to stern: (letter, x_fwd, x_aft)
        self.decks = [Deck(d, self.hull, self.wall) for d in spec["decks"]]
        self.deck = {d.id: d for d in self.decks}
        self.comps, self.by_id = [], {}
        self.doors, self.nodes, self.edges = [], [], []
        self.node_ids = set()
        self.comp_nodes = {}                                    # comp id -> [(node id, x, y)]
        self.counter = {}
        self.L = {}
        self.fill_i = {}                                        # (deck, row) -> where the fill pattern has got to
        self.names = spec.get("names", {})
        self.room_scale = spec.get("room_scale", 1.0)
        self.vertical = []
        self.docks = []
        self.notes = []
        for d in self.decks:
            d.choose_passages()
            d.sections = [{"id": s[0], "x": [r2(s[2]), r2(s[1])]} for s in self.sec_ranges(d)]
        self.halls = [self._hall(h) for h in spec.get("halls", [])]
        self.keys = list(spec.get("keys", []))
        self.stair_specs = list(spec.get("stairs", []))
        self.dock_specs = list(spec.get("docks", []))

    # --------------------------------------------------------------------------------------------------------------- helpers
    def sec_ranges(self, d: Deck):
        out = []
        for letter, xf, xa in self.sections:
            a, f = max(xa, d.xa), min(xf, d.xf)
            if f - a >= 8.0:
                out.append((letter, a, f))
        return out

    def sec_of(self, x: float) -> str:
        for letter, xf, xa in self.sections:
            if xa - 1e-6 <= x <= xf + 1e-6:
                return letter
        return self.sections[0][0] if x > self.sections[0][1] else self.sections[-1][0]

    def sec_span(self, letter: str):
        for l, xf, xa in self.sections:
            if l == letter:
                return xa, xf
        raise KeyError(letter)

    def _next_id(self, deck: int, kind: str, sec: str) -> str:
        k = (deck, kind, sec)
        self.counter[k] = self.counter.get(k, 0) + 1
        return f"d{deck}_{kind}_{sec}{self.counter[k]}"

    # --------------------------------------------------------------------------------------------------------------- comps, nodes, doors
    def add_comp(self, deck: Deck, kind: str, x0: float, x1: float, y0: float, y1: float, sec=None, name=None, systems=None, z=None, crew=None,
                 role=None, side=0, spans=None, extra=None) -> dict:
        sec = sec or self.sec_of(0.5 * (x0 + x1))
        info = KINDS.get(kind) or KINDS["storage"]
        cid = self._next_id(deck.id, kind, sec)
        zf, zc = z if z else (deck.z, deck.z + (CORR_H if kind in ("corridor", "vestibule") else deck.clear))
        area = (x1 - x0) * (y1 - y0)
        label = name or self.names.get(kind) or info[0]
        c = {"id": cid, "deck": deck.id, "section": sec, "kind": kind, "name": label, "bounds": [r2(x0), r2(y0), r2(x1), r2(y1)], "z": [r2(zf), r2(zc)],
             "status": "planned", "doors": [], "dept": info[1], "systems": list(systems if systems is not None else info[2]),
             "crew_slots": crew if crew is not None else int(round(info[3] * area / 100.0))}
        if side:
            c["_side"] = side
        if spans:
            c["spans_decks"] = list(spans)
        if role:
            c["role"] = role
        if extra:
            c.update(extra)
        self.comps.append(c)
        self.by_id[cid] = c
        self.comp_nodes[cid] = []
        return c

    def node(self, comp: dict, x: float, y: float, kind: str, suffix: str, z=None, extra=None) -> str:
        nid = f"{comp['id']}.{suffix}"
        k = 0
        while nid in self.node_ids:
            k += 1
            nid = f"{comp['id']}.{suffix}{k}"
        self.node_ids.add(nid)
        zz = comp["z"][0] if z is None else z
        n = {"id": nid, "deck": comp["deck"], "p": [r2(x), r2(y), r2(zz)], "kind": kind, "comp": comp["id"]}
        if extra:
            n.update(extra)
        self.nodes.append(n)
        self.comp_nodes[comp["id"]].append((nid, x, y, zz))
        return nid

    def edge(self, a: str, b: str, length: float, kind: str = "walk", **kw):
        e = {"a": a, "b": b, "len": r2(length), "kind": kind}
        e.update(kw)
        self.edges.append(e)

    def door(self, a: dict, b: dict, x: float, y: float, yaw: float, kind: str = "door", width: float = DOOR_W, height: float = DOOR_H, z=None,
             boundary=None, extra=None) -> dict:
        """A door in the wall between two compartments: its record, the nodes on each side of it and the graph edge between them (a's side
        first). yaw 90: a wall that faces y (the door passes you along y); yaw 0: a wall that faces x."""
        deck = self.deck[a["deck"]] if a["deck"] in self.deck else self.deck[b["deck"]]
        zz = z if z is not None else deck.z
        did = f"door_{len(self.doors) + 1:04d}"
        rec = {"id": did, "deck": deck.id, "pos": [r2(x), r2(y), r2(zz)], "yaw": yaw, "width": width, "height": height, "kind": kind, "a": a["id"], "b": b["id"],
               "locked": False}
        if kind == "blast":
            rec["blast"] = True
            rec["boundary"] = list(boundary)
        if extra:
            rec.update(extra)
        self.doors.append(rec)
        a["doors"].append(did)
        b["doors"].append(did)
        dx, dy = (0.0, 0.8) if yaw == 90.0 else (0.8, 0.0)
        ca = (0.5 * (a["bounds"][0] + a["bounds"][2]), 0.5 * (a["bounds"][1] + a["bounds"][3]))
        sgn = 1.0 if (ca[0] - x) * dx + (ca[1] - y) * dy >= 0 else -1.0
        na = self.node(a, x + sgn * dx, y + sgn * dy, "corridor" if a["kind"] in ("corridor", "vestibule", "stairs") else "door_in", "d", z=zz, extra={"door": did})
        nb = self.node(b, x - sgn * dx, y - sgn * dy, "corridor" if b["kind"] in ("corridor", "vestibule", "stairs") else "door_in", "d", z=zz, extra={"door": did})
        kw = {"door": did, "w": width}
        if kind == "blast":
            kw["blast"] = True
        self.edge(na, nb, 1.6, "door", **kw)
        return rec

    # --------------------------------------------------------------------------------------------------------------- halls
    def _hall(self, h: dict) -> dict:
        h = dict(h)
        h["x0"], h["x1"] = h["x"]
        decks = [self.deck[i] for i in h["decks"]]
        lim = 1e9
        for d in decks:
            for x in (h["x0"], 0.5 * (h["x0"] + h["x1"]), h["x1"]):
                lim = min(lim, d.inner_limit(x))
            lim = min(lim, d.hw_min(h["x0"], h["x1"]) - 0.3)
        h["half"] = math.floor(lim * 2.0) / 2.0
        if h["half"] < 4.0:
            raise ValueError(f"hall {h['id']}: no room for it ({lim:.1f} m)")
        h["entry"] = h.get("entry", h["decks"][-1])
        return h

    # --------------------------------------------------------------------------------------------------------------- the rows' geometry
    def run_ivs(self, d: Deck, row: str, a: float, f: float):
        """The x intervals of [a, f] where the row has at least MIN_DEPTH of depth (and exists: an outer row only beside a passage)."""
        side, typ = ROWS[row]
        out, cur = [], None
        n = max(1, int(round((f - a) / 2.0)))
        for i in range(n + 1):
            x = a + (f - a) * i / n
            if typ == "inner":
                ok = d.inner_limit(x) - (SPINE_HW + WALL) >= MIN_DEPTH
            else:
                ok = d.has_passage(x) and d.outer_limit(x) - (d.YP + PASS_HW + WALL) >= MIN_DEPTH
            if ok:
                cur = (cur[0], x) if cur else (x, x)
            else:
                if cur:
                    out.append(cur)
                cur = None
        if cur:
            out.append(cur)
        return [(p0, p1) for p0, p1 in out if p1 - p0 >= MIN_LEN]

    def row_y(self, d: Deck, row: str, x0: float, x1: float):
        side, typ = ROWS[row]
        xs = [x0 + (x1 - x0) * i / max(1, int(round((x1 - x0) / 2.0))) for i in range(max(1, int(round((x1 - x0) / 2.0))) + 1)]
        if typ == "inner":
            ya, yb = SPINE_HW + WALL, min(d.inner_limit(x) for x in xs)
        else:
            ya, yb = d.YP + PASS_HW + WALL, min(d.outer_limit(x) for x in xs)
        return (ya, yb) if yb - ya >= MIN_DEPTH else None

    def room(self, d: Deck, row: str, x0: float, x1: float, kind: str, **kw):
        """A room in a row (None when the row is too shallow there)."""
        yy = self.row_y(d, row, x0, x1)
        if not yy:
            return None
        side = ROWS[row][0]
        y0, y1 = (yy[0], yy[1]) if side > 0 else (-yy[1], -yy[0])
        name = kw.pop("name", None)
        if name is None and not kw.get("plain_name"):
            name = self.names.get(kind) or KINDS[kind][0]
        kw.pop("plain_name", None)
        c = self.add_comp(d, kind, x0, x1, y0, y1, name=name, side=side, extra={"_row": row}, **kw)
        self.L[d.id].rooms.append(c)
        return c

    # --------------------------------------------------------------------------------------------------------------- one deck
    def layout_deck(self, d: Deck):
        L = self.L[d.id] = Layout()
        secs = self.sec_ranges(d)
        halls = [h for h in self.halls if d.id in h["decks"]]
        hall_cuts = [(h["x0"] - WALL, h["x1"] + WALL) for h in halls]
        # ---- the spine, a segment to each section, with the halls taken out
        for letter, a, f in secs:
            for p0, p1 in iv_subtract([(a + 0.2, f - 0.2)], hall_cuts):
                if p1 - p0 >= 3.0:
                    L.spine.append(self.add_comp(d, "corridor", p0, p1, -SPINE_HW, SPINE_HW, sec=letter, name="Spine", role="spine"))
        # ---- the passages, and a cross corridor at the fore end of every section's run (and at the aft end of the whole run: the ring closes)
        cross_x = []                                           # the x intervals a cross corridor takes (the inner rows stop short of them)
        if d.pass_x:
            pa_all, pf_all = d.pass_x
            for letter, a, f in secs:
                pa, pf = max(a + 0.2, pa_all), min(f - 0.2, pf_all)
                if pf - pa < 8.0:
                    continue
                for side in (1, -1):
                    y0, y1 = (d.YP - PASS_HW, d.YP + PASS_HW) if side > 0 else (-d.YP - PASS_HW, -d.YP + PASS_HW)
                    L.passage[side].append(self.add_comp(d, "corridor", pa, pf, y0, y1, sec=letter, name="Starboard Passage" if side > 0 else "Port Passage",
                                                         role="passage", side=side))
                cross_x.append((pf - CROSS_W, pf, letter))
            cross_x.append((pa_all + 0.2, pa_all + 0.2 + CROSS_W, self.sec_of(pa_all + 1.0)))
            # (a cross corridor does not run through a hall: a passage that ends beside one is joined to the hall's door instead)
            cross_x = [c for c in cross_x if not any(overlap(c[0], c[1], h0, h1) > 0 for h0, h1 in hall_cuts)]
            for cx0, cx1, letter in cross_x:
                for side in (1, -1):
                    y0, y1 = (SPINE_HW, d.YP - PASS_HW) if side > 0 else (-(d.YP - PASS_HW), -SPINE_HW)
                    if y1 - y0 >= 1.0:
                        L.cross.append(self.add_comp(d, "corridor", cx0, cx1, y0, y1, sec=letter, name="Cross Passage", role="cross", side=side))
        cross_cuts = [(x0 - WALL, x1 + WALL) for x0, x1, _ in cross_x]
        # ---- the halls that stand on this deck (the entry deck makes the compartment, the others only reserve the room)
        for h in halls:
            if d.id == h["entry"]:
                spans = [self.deck[i] for i in h["decks"]]
                zf = min(s.z for s in spans)
                zc = max(s.z + s.clear for s in spans)
                c = self.add_comp(d, h["kind"], h["x0"], h["x1"], -h["half"], h["half"], sec=h.get("sec"), name=h.get("name"), systems=h.get("systems"),
                                  z=(zf, zc), crew=h.get("crew"), role=h.get("role"), spans=sorted(h["decks"]), extra={"_hall": h["id"]})
                h["comp"] = c["id"]
                L.halls.append(c)
        # ---- the stair slots, the dock vestibules and airlocks
        slots = {"IP": [], "IS": [], "OP": [], "OS": []}
        for st in self.stair_specs:
            row = st["row"]
            x0, x1 = st["x"] - STAIR_SIZE / 2, st["x"] + STAIR_SIZE / 2
            if not self.stair_fits(d, row, x0, x1, hall_cuts, cross_cuts):
                continue
            yy = self.row_y(d, row, x0, x1)
            side = ROWS[row][0]
            depth = min(STAIR_SIZE, yy[1] - yy[0])
            y0, y1 = (yy[0], yy[0] + depth) if side > 0 else (-(yy[0] + depth), -yy[0])
            c = self.add_comp(d, "stairs", x0, x1, y0, y1, name="Stair Tower", side=side, extra={"_row": row, "_stair": st["id"]})
            L.stairs.append(c)
            slots[row].append((x0 - 0.0, x1 + 0.0))
        for dk in self.dock_specs:
            if dk.get("kind", "hatch") != "hatch" or dk["deck"] != d.id:
                continue
            self.make_dock_rooms(d, dk, L, slots)
        # ---- the rows: the key rooms, then the fill
        for row in ("IP", "IS", "OP", "OS"):
            side, typ = ROWS[row]
            ivs_by = {}
            for letter, a, f in secs:
                base = self.run_ivs(d, row, a + 0.2, f - 0.2)
                cuts = list(slots[row])
                if typ == "inner":
                    cuts += hall_cuts + cross_cuts
                ivs_by[letter] = iv_subtract(base, cuts)
            # the key rooms of this row first: each in the section its x is in (one that does not sit exactly where it was asked moves to the nearest
            # place in the row, and shrinks to fit)
            for k in self.keys:
                if k["deck"] != d.id or k["row"] != row:
                    continue
                order = sorted(ivs_by, key=lambda l: abs(self.sec_of(k["x"]) != l) * 1000 + min(abs(k["x"] - iv[0]) if k["x"] < iv[0] else (abs(k["x"] - iv[1]) if k["x"] > iv[1] else 0.0)
                                                                                                  for iv in ivs_by[l]) if ivs_by[l] else 1e9)
                placed = False
                for letter in order:
                    ivs = ivs_by[letter]
                    host = next(((p0, p1) for p0, p1 in ivs if p0 - 1e-6 <= k["x"] <= p1 + 1e-6), None)
                    if not host and ivs:
                        near = min(ivs, key=lambda iv: min(abs(k["x"] - iv[0]), abs(k["x"] - iv[1])))
                        host = near if min(abs(k["x"] - near[0]), abs(k["x"] - near[1])) < 14.0 else None
                    if not host:
                        continue
                    ln = min(k["len"], host[1] - host[0])
                    if ln < MIN_LEN:
                        continue
                    cx = clamp(k["x"], host[0] + ln / 2, host[1] - ln / 2)
                    kx0, kx1 = cx - ln / 2, cx + ln / 2
                    kw = {kk: k[kk] for kk in ("name", "systems", "crew", "role") if kk in k}
                    kw["sec"] = letter
                    c = self.room(d, row, kx0, kx1, k["kind"], **kw)
                    if c is None:
                        continue
                    if abs(cx - k["x"]) > 1.0 or ln < k["len"] - 0.5:
                        self.notes.append(f"key room {k['kind']} (deck {d.id} {row}) asked at x {k['x']:.0f} len {k['len']:.0f}: put at x {cx:.0f} len {ln:.0f}")
                    ivs_by[letter] = iv_subtract(ivs, [(kx0, kx1)])
                    placed = True
                    break
                if not placed:
                    self.notes.append(f"key room {k['kind']} (deck {d.id} {row}) at x {k['x']:.0f}: no place in the row")
            for letter, a, f in secs:
                for p0, p1 in ivs_by[letter]:
                    if p1 - p0 >= MIN_LEN:
                        self.fill(d, row, letter, p0, p1)

    def stair_fits(self, d: Deck, row: str, x0: float, x1: float, hall_cuts, cross_cuts) -> bool:
        if x0 < d.xa + 0.5 or x1 > d.xf - 0.5:
            return False
        if any(overlap(x0, x1, c0, c1) > 0 for c0, c1 in hall_cuts + cross_cuts):
            return False
        for letter, a, f in self.sec_ranges(d):                  # inside one section
            if a + 0.2 <= x0 and x1 <= f - 0.2:
                break
        else:
            return False
        yy = self.row_y(d, row, x0, x1)
        return bool(yy) and yy[1] - yy[0] >= MIN_DEPTH

    def make_dock_rooms(self, d: Deck, dk: dict, L: Layout, slots: dict):
        """The airlock in the strip along the skin at the dock's x and, between it and the passage, the vestibule (a boarding party's gangway); where
        there is hardly a gap the airlock reaches the passage itself."""
        side = dk["side"]
        x0, x1 = dk["x"] - 3.0, dk["x"] + 3.0
        if not d.has_passage(x0) or not d.has_passage(x1):
            raise ValueError(f"dock {dk['id']} at deck {d.id} x {dk['x']}: no passage there (the airlock needs one)")
        hw = d.hw_min(x0, x1)
        row = "OS" if side > 0 else "OP"
        pas_edge = d.YP + PASS_HW + WALL                       # where the passage's wall ends
        a_in = hw - STRIP
        gap = a_in - WALL - pas_edge
        if gap >= 1.8:
            vy0, vy1 = pas_edge, a_in - WALL
            v0, v1 = (vy0, vy1) if side > 0 else (-vy1, -vy0)
            v = self.add_comp(d, "vestibule", x0, x1, v0, v1, name="Boarding Vestibule", side=side, extra={"_row": row})
            L.vestibules.append(v)
            if gap >= MIN_DEPTH:
                slots[row].append((x0, x1))
        else:
            a_in = pas_edge - WALL                             # the airlock touches the passage
        ay0, ay1 = (a_in, hw - 0.2) if side > 0 else (-(hw - 0.2), -a_in)
        c = self.add_comp(d, "airlock", x0, x1, ay0, ay1, name="Boarding Airlock", side=side, extra={"_dock": dk["id"]})
        L.airlocks.append(c)
        dk["comp"] = c["id"]

    # --------------------------------------------------------------------------------------------------------------- the fill of a row
    def fill(self, d: Deck, row: str, letter: str, p0: float, p1: float):
        pat = self.pattern(d.id, letter, row)
        if not pat:
            return
        k = (d.id, row)
        x = p0
        length = p1 - p0
        guard = 0
        while x < p1 - 1e-6 and guard < 200:
            guard += 1
            tok = pat[self.fill_i.get(k, 0) % len(pat)]
            self.fill_i[k] = self.fill_i.get(k, 0) + 1
            kind, nominal = tok[0], tok[1] * self.room_scale
            name = tok[2] if len(tok) > 2 else None
            rest = p1 - x
            ln = rest if (rest < 1.6 * nominal) else nominal
            if rest - ln < 0.6 * nominal and rest - ln > 1e-6:
                ln = rest                                    # the remainder is too short to be a room: this one takes it
            ln = max(ln, 0.0)
            if ln < MIN_LEN:
                break
            if kind != "void":
                kw = {"sec": letter}
                if name:
                    kw["name"] = name
                self.room(d, row, x, x + ln, kind, **kw)
            x += ln

    def pattern(self, deck: int, letter: str, row: str):
        f = self.spec.get("fill", {})
        for key in ((deck, letter), deck, letter, "*"):
            if key in f and row in f[key]:
                return f[key][row]
        return None

    # --------------------------------------------------------------------------------------------------------------- stairs (columns)
    def link_stairs(self):
        cols = {}
        for d in self.decks:
            for c in self.L[d.id].stairs:
                cols.setdefault(c["_stair"], []).append((d, c))
        for sid, items in cols.items():
            items.sort(key=lambda t: t[0].z, reverse=True)       # the highest deck first
            for (d0, c0), (d1, c1) in zip(items, items[1:]):
                n0 = self.stair_node(c0)
                n1 = self.stair_node(c1)
                dz = abs(d0.z - d1.z)
                self.edge(n0, n1, math.hypot(dz, 4.0), "stair", cost=round(dz * 3.5, 1))
            rec = {"id": sid, "kind": "stair", "pos": [r2(0.5 * (items[0][1]["bounds"][0] + items[0][1]["bounds"][2])),
                                                      r2(0.5 * (items[0][1]["bounds"][1] + items[0][1]["bounds"][3]))],
                   "decks": [d.id for d, _ in items], "nodes": {str(d.id): self.stair_node(c) for d, c in items},
                   "towers": {str(d.id): c["id"] for d, c in items}}
            self.vertical.append(rec)

    def stair_node(self, c: dict) -> str:
        for nid, x, y, z in self.comp_nodes[c["id"]]:
            if nid.endswith(".stair"):
                return nid
        cx, cy = 0.5 * (c["bounds"][0] + c["bounds"][2]), 0.5 * (c["bounds"][1] + c["bounds"][3])
        return self.node(c, cx, cy, "stair", "stair")

    # --------------------------------------------------------------------------------------------------------------- the whole plan
    def build(self) -> dict:
        for d in self.decks:
            self.layout_deck(d)
        self.link_stairs()
        for d in self.decks:
            self.wire_deck(d)
        self.finish_graph()
        self.make_crew()
        self.make_parties()
        return self.assemble()
