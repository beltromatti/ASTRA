"""ASN Aquila — the layout engine of a built deck (pure Python): passages made of 4 m modules, rooms in lanes along them,
cross-links, doors, signs, plates, lights and the walk graph, all on the 4 m grid of the ship (docs/NAVE.md).

A deck is made of
  * passages: straight runs of corridor modules, along x (at y = `pos`) or, for cross-links, along y (at x = `pos`). Module i of a
    passage covers [a0 + 4 i, a0 + 4 i + 4] along its axis (the aft / port end first). Events (a door or a gate on a side, a
    branch, a section bulkhead, an end wall) are set by the rooms and links that attach to it and decide each module's mesh
    (SM_SHIP_<tone>_<suffix>, ship_catalog);
  * lanes: rows of room prefabs (ship_spec) packed from `x_start` towards the stern along a passage's wall, with explicit gaps and
    cross-link slots; a room's near door lands on a module centre;
  * specials placed by hand (the existing rooms, the concourse, stair towers...), which bring their own doors and graph nodes.
`Builder` collects the compartments, doors, placements, graph nodes and edges of the whole plan.
"""
from __future__ import annotations

import math

import ship_plan as P
import ship_spec as SP
from ship_catalog import BLAST_H, BLAST_W, CLEAR_H, DOOR_H, DOOR_W, GATE_H, GATE_W, HW, MOD, SLOT_HW, WALL_T, module_mesh

SEG_MODULES = 4                 # a corridor compartment (and its zone light) is 4 modules = 16 m long


def rnd(v: float, n: int = 3) -> float:
    return round(v + 0.0, n)


class Builder:
    """The plan under construction."""

    def __init__(self) -> None:
        self.comps: dict[str, dict] = {}
        self.doors: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.placements: dict[int, list] = {d: [] for d in range(1, 13)}
        self.vertical: list[dict] = []
        self.notes: list[str] = []

    def comp(self, cid: str, deck: int, kind: str, name: str, bounds, z=None, section: str | None = None, **kw) -> dict:
        if cid in self.comps:
            raise ValueError(f"duplicate compartment {cid}")
        z0, z1 = P.deck_z(deck) if z is None else z
        xc = (bounds[0] + bounds[2]) / 2
        rec = {"id": cid, "deck": deck, "section": section or P.section_of(deck, xc), "kind": kind, "name": name,
               "bounds": [rnd(v) for v in bounds], "z": [rnd(z0), rnd(z1)], "status": "planned", "doors": []}
        rec.update({k: v for k, v in kw.items() if v is not None})
        self.comps[cid] = rec
        return rec

    def door(self, did: str, deck: int, pos, yaw: float, width: float, height: float, a: str | None, b: str | None, kind: str = "sliding",
             **kw) -> dict:
        if did in self.doors:
            raise ValueError(f"duplicate door {did}")
        rec = {"id": did, "deck": deck, "pos": [rnd(v) for v in pos], "yaw": rnd(yaw, 1), "width": rnd(width), "height": rnd(height),
               "kind": kind, "a": a, "b": b, "locked": False}
        rec.update(kw)
        self.doors[did] = rec
        for c in (a, b):
            if c and c in self.comps and did not in self.comps[c]["doors"]:
                self.comps[c]["doors"].append(did)
        return rec

    def node(self, nid: str, deck: int, x: float, y: float, z: float, kind: str, comp: str | None = None, **kw) -> dict:
        if nid in self.nodes:
            raise ValueError(f"duplicate node {nid}")
        rec = {"id": nid, "deck": deck, "p": [rnd(x), rnd(y), rnd(z)], "kind": kind, "comp": comp}
        rec.update(kw)
        self.nodes[nid] = rec
        return rec

    def link(self, a: str, b: str, kind: str = "walk", door: str | None = None, width: float | None = None, blast: bool = False,
             cost: float | None = None) -> dict:
        na, nb = self.nodes[a], self.nodes[b]
        e = {"a": a, "b": b, "len": rnd(math.dist(na["p"], nb["p"]), 2), "kind": kind}
        if door:
            e["door"] = door
        if width is not None:
            e["w"] = rnd(width, 2)
        if blast:
            e["blast"] = True
        if cost is not None:
            e["cost"] = rnd(cost, 2)
        self.edges.append(e)
        return e

    def place(self, deck: int, mesh: str, pos, yaw: float, folder: str, label: str, cls: str, **kw) -> dict:
        rec = {"mesh": mesh, "pos": [rnd(v) for v in pos], "yaw": rnd(yaw, 1), "folder": folder, "label": label, "cls": cls}
        rec.update(kw)
        self.placements[deck].append(rec)
        return rec


class Passage:
    """A straight run of modules (see the module docstring)."""

    def __init__(self, pid: str, deck: int, tone: str, along: str, pos: float, a0: float, a1: float, name: str = "") -> None:
        self.pid, self.deck, self.tone, self.along, self.pos = pid, deck, tone, along, float(pos)
        self.a0, self.a1 = float(a0), float(a1)
        n = (self.a1 - self.a0) / MOD
        assert abs(n - round(n)) < 1e-6, f"{pid}: length {self.a1 - self.a0} is not a multiple of 4"
        self.n = int(round(n))
        self.ev: dict[int, dict] = {}
        self.name = name or pid
        self.link_of = None
        self.chunk_node: dict[int, str] = {}     # coarse decks: module index -> the graph node of its 16 m corridor compartment

    def node_id(self, tag: str, i: int, coarse: bool) -> str:
        return self.chunk_node[i] if coarse else f"{tag}.{self.pid}.{i:03d}"

    def center_index(self, a: float) -> int:
        i = (a - 2.0 - self.a0) / MOD
        if abs(i - round(i)) > 1e-6:
            raise ValueError(f"{self.pid}: {a} is not a module centre (a0 {self.a0})")
        i = int(round(i))
        if not 0 <= i < self.n:
            raise ValueError(f"{self.pid}: {a} is outside the passage [{self.a0}, {self.a1}]")
        return i

    def side(self, i: int, side: str, what: str) -> None:
        e = self.ev.setdefault(i, {})
        if side in e and e[side] != what:
            raise ValueError(f"{self.pid} module {i}: side {side} is {e[side]}, wanted {what}")
        e[side] = what

    def mark(self, i: int, **kw) -> None:
        self.ev.setdefault(i, {}).update(kw)

    def suffix(self, i: int) -> str:
        e = self.ev.get(i, {})
        if e.get("end"):
            if "L" in e or "R" in e:
                raise ValueError(f"{self.pid} module {i} (x/y {self.centre(i)}): an end wall cannot carry a side opening")
            return "End"
        if e.get("bulk"):
            if "L" in e or "R" in e:
                raise ValueError(f"{self.pid} module {i}: a bulkhead cannot carry a side opening")
            return "Bulkhead"
        L, R = e.get("L", "wall"), e.get("R", "wall")
        v = "A" if i % 2 == 0 else "B"
        table = {("wall", "wall"): "Straight_" + "ABC"[i % 3], ("door", "wall"): f"Door_L_{v}", ("wall", "door"): f"Door_R_{v}",
                 ("door", "door"): "Door_LR", ("gate", "wall"): "Gate_L", ("wall", "gate"): "Gate_R", ("gate", "gate"): "Gate_LR",
                 ("branch", "wall"): "T_L", ("wall", "branch"): "T_R", ("branch", "branch"): "X"}
        if (L, R) not in table:
            raise ValueError(f"{self.pid} module {i} (x/y {self.centre(i)}): unsupported sides {L}/{R}")
        return table[(L, R)]

    def centre(self, i: int):
        a = self.a0 + i * MOD + 2.0
        return (a, self.pos) if self.along == "x" else (self.pos, a)


class Deck:
    """The layout of one built deck. Declare passages, lanes and specials, then call `emit()`."""

    def __init__(self, B: Builder, deck: int, tag: str, coarse: bool = False) -> None:
        self.B, self.deck, self.tag, self.coarse = B, deck, tag, coarse
        self.z0, self.z1 = P.deck_z(deck)
        self.passages: dict[str, Passage] = {}
        self.rooms: list[dict] = []
        self.links: list[dict] = []
        self.specials_doors: list[dict] = []
        self.count: dict[str, int] = {}
        self.env = P.envelope(deck)

    # ------------------------------------------------------------------------------------------------------ declaration
    def passage(self, pid: str, tone: str, along: str, pos: float, a0: float, a1: float, name: str = "") -> Passage:
        p = Passage(pid, self.deck, tone, along, pos, a0, a1, name)
        self.passages[pid] = p
        return p

    def wall_plane(self, pid: str, side: int) -> float:
        return self.passages[pid].pos + side * SLOT_HW

    def lane(self, pid: str, side: int, x_start: float, items: list, lane: str) -> None:
        """Pack items from x_start towards the stern along passage `pid`'s wall on `side` (+1 right = +y, -1 left).
        items: ("key",) | ("key", {opts}) | ("gap", L) | ("link", partner)"""
        assert self.passages[pid].along == "x"
        x = float(x_start)
        yn = self.wall_plane(pid, side)
        for it in items:
            if it[0] == "gap":
                x -= float(it[1])
                continue
            if it[0] == "link":
                self.links.append({"a": pid, "b": it[1], "x": x - MOD / 2})
                x -= MOD
                continue
            key, opt = it[0], (it[1] if len(it) > 1 else {})
            spec = SP.PREFABS[key]
            L = spec["L"]
            yaw = 0.0 if side > 0 else 180.0
            origin = (x - L if side > 0 else x, yn)
            self.rooms.append(dict(key=key, spec=spec, pid=pid, side=side, origin=origin, yaw=yaw, x_min=x - L, x_max=x, y_near=yn, opt=opt,
                                   lane=lane))
            x -= L

    def special(self, cid: str, key: str, origin, yaw: float, bounds, folder_section: str, name: str | None = None, plate: str | None = None) -> dict:
        """A hand-placed prefab (concourse, lobby, bow observation deck): its compartment, placement and graph hooks. Returns the room record."""
        B = self.B
        spec = SP.PREFABS[key]
        o3 = (origin[0], origin[1], self.z0)
        stations = []
        for i, s in enumerate(spec["spots"]):
            w = P.place_local(o3, yaw, s["x"], s["y"])
            stations.append({"id": f"{cid}.s{i}", "role": s["role"], "kind": s["kind"], "pos": [rnd(w[0]), rnd(w[1]), rnd(self.z0)],
                             "yaw": rnd((s["yaw"] + yaw) % 360.0, 1), "dept": s["dept"]})
        lights = []
        for i, l in enumerate(spec["lights"]):
            w = P.place_local(o3, yaw, l["pos"][0], l["pos"][1], l["pos"][2])
            ld = dict(l)
            ld["pos"] = [rnd(w[0]), rnd(w[1]), rnd(w[2])]
            ld["id"] = f"{cid}.l{i}"
            lights.append(ld)
        B.comp(cid, self.deck, spec["kind"], name or spec["name"], bounds, (self.z0, self.zt(spec["h"])), dept=spec["dept"], prefab=key,
               mesh=spec.get("mesh"), pos=[rnd(o3[0]), rnd(o3[1]), rnd(o3[2])], yaw=yaw, systems=list(spec["systems"]), stations=stations, lights=lights,
               plate=plate, status=("planned" if self.coarse else "built"), lane="special", size=[spec["L"], spec["D"], spec["h"]])
        if not self.coarse:
            B.place(self.deck, spec["mesh"], o3, yaw, f"Interior/Deck{self.deck:02d}/Rooms/{folder_section}", cid, "room", comp=cid)
        r = dict(done=True, cid=cid, spec=dict(spec, plate=None), key=key, doors=[])
        self.rooms.append(r)
        return r

    def gate(self, r: dict, did: str, pid: str, xw: float, room_side: int, w: float, h: float, wall: str = "special") -> None:
        """A door / gate between the special room `r` and passage `pid` at x = xw; the room lies on `room_side` of the passage."""
        ps = self.passages[pid]
        self._room_door(r, r["cid"], {"wall": wall, "w": w, "h": h, "id": did}, xw, ps.pos + room_side * SLOT_HW, pid, room_side)

    def section_bulkheads(self, pids=None) -> None:
        """A bulkhead on every passage along x at every section boundary it spans (the module aft of the boundary)."""
        secs = P.sections(self.deck)
        for pid, ps in self.passages.items():
            if ps.along != "x" or (pids and pid not in pids):
                continue
            for letter, xmin, xmax in secs[:-1]:
                b = xmin                                      # the boundary between this section and the next one aft
                if ps.a0 < b < ps.a1:
                    i = int(round((b - 4.0 - ps.a0) / MOD))
                    ps.mark(i, bulk=True, bulk_x=b)
                    if abs((ps.a0 + i * MOD + MOD) - b) > 1e-6:
                        raise ValueError(f"{pid}: boundary {b} is not on the grid")
            # a passage that starts or ends exactly at a boundary: the frame at its aft end (rotated module)
            for letter, xmin, xmax in secs:
                if abs(ps.a0 - xmax) < 1e-6 and xmax != secs[0][2]:
                    ps.mark(0, bulk=True, bulk_x=xmax, bulk_aft=True)

    def ends(self, pid: str, fwd: str | None = None, aft: str | None = None) -> None:
        """Close a passage's ends ('wall' -> an End module); leave None where it opens into a hall."""
        ps = self.passages[pid]
        if fwd == "wall":
            ps.mark(ps.n - 1, end="fwd")
        if aft == "wall":
            ps.mark(0, end="aft")

    # ----------------------------------------------------------------------------------------------------------------- emit
    def emit(self) -> None:
        for r in self.rooms:
            if not r.get("done"):
                self._room(r)
        for lk in self.links:
            self._link(lk)
        self.section_bulkheads()
        for ps in self.passages.values():
            self._passage(ps)
        for sd in self.specials_doors:
            self._special_door(sd)

    def zt(self, h: float) -> float:
        """Top of a room of clear height h (its ceiling structure): shared with the deck above beyond the deck pitch, except on Deck 2 (the block's
        roof is far above)."""
        return self.z0 + (h + 0.3 if self.deck == 2 else min(h + 0.3, 4.0))

    def _sec(self, x: float) -> str:
        return P.section_of(self.deck, x)

    def _cid(self, key: str, x: float) -> str:
        sec = self._sec(x)
        k = f"{key}_{sec}"
        self.count[k] = self.count.get(k, 0) + 1
        return f"{self.tag}_{key}_{sec}{self.count[k]}"

    def local(self, r: dict, lx: float, ly: float, lz: float = 0.0):
        return P.place_local((r["origin"][0], r["origin"][1], self.z0), r["yaw"], lx, ly, lz)

    # --------------------------------------------------------------------------------------------------------------- rooms
    def _room(self, r: dict) -> None:
        B = self.B
        spec = r["spec"]
        key = spec["key"]
        cid = r["opt"].get("id") or self._cid(key, (r["x_min"] + r["x_max"]) / 2)
        L, D = spec["L"], spec["D"]
        a, b = self.local(r, 0, 0), self.local(r, L, D)
        bounds = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        stations = []
        for i, s in enumerate(spec["spots"]):
            w = self.local(r, s["x"], s["y"])
            stations.append({"id": f"{cid}.s{i}", "role": s["role"], "kind": s["kind"], "pos": [rnd(w[0]), rnd(w[1]), rnd(self.z0)],
                             "yaw": rnd((s["yaw"] + r["yaw"]) % 360.0, 1), "dept": s["dept"]})
        lights = []
        for i, l in enumerate(spec["lights"]):
            w = self.local(r, l["pos"][0], l["pos"][1], l["pos"][2])
            ld = dict(l)
            ld["pos"] = [rnd(w[0]), rnd(w[1]), rnd(w[2])]
            if l.get("size") and (r["yaw"] % 180.0) != 0.0:
                ld["size"] = [l["size"][1], l["size"][0]]
            ld["id"] = f"{cid}.l{i}"
            lights.append(ld)
        slots = len(stations)
        if self.coarse:                                  # a planned room: the number of crew places, not their positions (yet)
            stations = []
            lights = lights[:1]
        built = (not self.coarse) and spec.get("mesh") is not None
        rec = B.comp(cid, self.deck, spec["kind"], r["opt"].get("name") or spec["name"], bounds, (self.z0, self.zt(spec["h"])), dept=spec["dept"],
                     prefab=key, mesh=spec.get("mesh"), pos=[rnd(r["origin"][0]), rnd(r["origin"][1]), rnd(self.z0)], yaw=r["yaw"],
                     systems=list(spec["systems"]), stations=stations, lights=lights, plate=spec.get("plate"), status="built" if built else "planned",
                     lane=r["lane"], size=[L, D, spec["h"]], crew_slots=slots)
        r["cid"], r["bounds"] = cid, bounds
        if built:
            B.place(self.deck, spec["mesh"], (r["origin"][0], r["origin"][1], self.z0), r["yaw"],
                    f"Interior/Deck{self.deck:02d}/Rooms/{rec['section']}", cid, "room", comp=cid)
        for d in spec["doors"]:
            dx = r["opt"].get("door_x", d["x"]) if d["wall"] == "near" else r["opt"].get("far_door_x", d["x"])
            xw = r["origin"][0] + (dx if r["yaw"] == 0.0 else -dx)
            if d["wall"] == "near":
                self._room_door(r, cid, d, xw, r["y_near"], r["pid"], r["side"])
            elif d["wall"] == "far":
                yf = r["y_near"] + r["side"] * D
                other = next((p for p in self.passages.values() if p.along == "x" and abs(abs(yf - p.pos) - SLOT_HW) < 1e-6), None)
                if other is not None:
                    self._room_door(r, cid, d, xw, yf, other.pid, -r["side"])

    def _room_door(self, r: dict, cid: str, d: dict, xw: float, y_wall: float, pid: str, room_side: int) -> None:
        """A door of the room on the wall plane y_wall of passage `pid`; the room lies on `room_side` (+1 = +y) of that passage."""
        ps = self.passages[pid]
        i = ps.center_index(xw)
        kind = "gate" if d["w"] > 2.0 else "door"
        ps.side(i, "R" if room_side > 0 else "L", kind)
        did = d.get("id") or (f"{self.tag}_door_{cid[len(self.tag) + 1:]}" + ("_far" if d["wall"] == "far" else ""))
        pos = (xw, y_wall - room_side * WALL_T / 2, self.z0)
        r.setdefault("doors", []).append(dict(id=did, pos=pos, w=d["w"], h=d["h"], pid=pid, i=i, side=room_side, kind=kind, wall=d["wall"], xw=xw,
                                               y_wall=y_wall))
        self.B.door(did, self.deck, pos, 90.0, d["w"], d["h"], cid, None, kind=kind, wall=d["wall"], passage=pid,
                    plate=r["spec"].get("plate") if d["wall"] == "near" else None, side=room_side)
        # the passage-side compartment is filled in by finish_doors, once the corridor segments exist

    # --------------------------------------------------------------------------------------------------------------- links
    def _link(self, lk: dict) -> None:
        pa, pb = self.passages[lk["a"]], self.passages[lk["b"]]
        xc = lk["x"]
        s = 1 if pb.pos > pa.pos else -1
        ia, ib = pa.center_index(xc), pb.center_index(xc)
        pa.side(ia, "R" if s > 0 else "L", "branch")
        pb.side(ib, "L" if s > 0 else "R", "branch")
        ya, yb = pa.pos + s * SLOT_HW, pb.pos - s * SLOT_HW
        n = abs(yb - ya) / MOD
        assert abs(n - round(n)) < 1e-6, f"link {pa.pid}-{pb.pid}: {abs(yb - ya)} m is not a multiple of 4"
        lid = f"{pa.pid}{pb.pid}{int(round(abs(xc)))}{'n' if xc < 0 else 'p'}"
        lp = Passage(lid, self.deck, "P", "y", xc, min(ya, yb), max(ya, yb), name=f"{pa.pid}-{pb.pid} link")
        lp.link_of = (pa.pid, ia, pb.pid, ib, s, ya, yb)
        self.passages[lid] = lp

    # ----------------------------------------------------------------------------------------------------------- passages
    def _passage(self, ps: Passage) -> None:
        B = self.B
        prefix = f"{self.tag}.{ps.pid}"
        folder = f"Interior/Deck{self.deck:02d}/Passages"
        secs = P.sections(self.deck)
        seg_ids: dict[int, str] = {}
        seg_counter: dict[str, int] = {}
        # -- corridor compartments (16 m each, per section) and their zone lights
        chunk_start: dict[str, float] = {}
        for i in range(ps.n):
            cx, cy = ps.centre(i)
            a = ps.a0 + i * MOD
            key_sec = self._sec(cx if ps.along == "x" else cx)
            if ps.along == "x":
                sec_end = next((sx1 for (l, sx0, sx1) in secs if l == key_sec), a + MOD)
                idx = int(math.floor((sec_end - (a + MOD)) / (MOD * SEG_MODULES) + 1e-6))
            else:
                idx = i // SEG_MODULES
            ck = f"{key_sec}{idx}"
            seg_ids[i] = ck
        by_seg: dict[str, list[int]] = {}
        for i, ck in seg_ids.items():
            by_seg.setdefault(ck, []).append(i)
        lname = ps.name
        for ck, idxs in by_seg.items():
            lo, hi = min(idxs), max(idxs)
            if ps.along == "x":
                bounds = [ps.a0 + lo * MOD, ps.pos - SLOT_HW, ps.a0 + (hi + 1) * MOD, ps.pos + SLOT_HW]
                sec = self._sec((bounds[0] + bounds[2]) / 2)
            else:
                bounds = [ps.pos - SLOT_HW, ps.a0 + lo * MOD, ps.pos + SLOT_HW, ps.a0 + (hi + 1) * MOD]
                sec = self._sec(ps.pos)
            cid = f"{self.tag}_{ps.pid.lower()}_{ck}"
            xc, yc = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
            along_len = (hi - lo + 1) * MOD
            size = [along_len - 0.6, 0.6] if ps.along == "x" else [0.6, along_len - 0.6]
            temp = 5600.0 if ps.tone == "S" else 3900.0
            extra = {} if self.coarse else dict(
                systems=["power_bus", "life_support", "data_trunk"] if ps.tone == "S" else ["power_bus", "life_support"],
                lights=[{"id": f"{cid}.l0", "type": "rect", "pos": [rnd(xc), rnd(yc), rnd(self.z0 + 3.28)], "lumens": 3400, "temperature": temp,
                         "size": size, "radius": 1000.0, "shadows": False}])
            B.comp(cid, self.deck, "corridor", f"{lname} · Section {sec}", bounds, section=sec, status="planned" if self.coarse else "built",
                   passage=ps.pid, modules=[lo, hi], tone=ps.tone, **extra)
            for i in idxs:
                seg_ids[i] = cid
        if self.coarse:
            self._passage_coarse(ps, by_seg, seg_ids)
            return
        # -- modules and graph nodes
        prev = None
        for i in range(ps.n):
            suffix = ps.suffix(i)
            e = ps.ev.get(i, {})
            cx, cy = ps.centre(i)
            a = ps.a0 + i * MOD
            if ps.along == "x":
                pos, yaw = (a, ps.pos, self.z0), 0.0
                if suffix == "Bulkhead" and e.get("bulk_aft"):
                    pos, yaw = (a + MOD, ps.pos, self.z0), 180.0
                if suffix == "End" and e.get("end") == "aft":
                    pos, yaw = (a + MOD, ps.pos, self.z0), 180.0
            else:
                pos, yaw = (ps.pos, a, self.z0), 90.0
                if suffix == "End" and e.get("end") == "aft":
                    pos, yaw = (ps.pos, a + MOD, self.z0), -90.0
            mesh = module_mesh(ps.tone, suffix)
            B.place(self.deck, mesh, pos, yaw, f"{folder}/{ps.pid}", f"{prefix}.{i:03d}", "module", passage=ps.pid, index=i, suffix=suffix)
            nid = f"{prefix}.{i:03d}"
            B.node(nid, self.deck, cx, cy, self.z0, "corridor", seg_ids[i], passage=ps.pid)
            if prev is not None:
                pe = ps.ev.get(i - 1, {})
                if pe.get("bulk") and not pe.get("bulk_aft"):
                    B.link(prev, nid, "door", door=self._blast(ps, i - 1, pe["bulk_x"]), width=BLAST_W, blast=True)
                elif e.get("bulk") and e.get("bulk_aft"):
                    B.link(prev, nid, "door", door=self._blast(ps, i, e["bulk_x"]), width=BLAST_W, blast=True)
                else:
                    B.link(prev, nid, "walk", width=3.1)
            prev = nid
            if e.get("bulk") and not e.get("bulk_aft") and ps.along == "x":
                # section signs on both faces of the frame (placed once here, meshes SM_SHIP_Sign_<deck><section>)
                self._signs(ps, i, e["bulk_x"])
        # cross-link ends join the through passages at the junction modules
        if ps.link_of:
            pa_id, ia, pb_id, ib, s, ya, yb = ps.link_of
            first, last = f"{prefix}.{0:03d}", f"{prefix}.{ps.n - 1:03d}"
            lo_end_pid, lo_i = (pa_id, ia) if ya < yb else (pb_id, ib)
            hi_end_pid, hi_i = (pb_id, ib) if ya < yb else (pa_id, ia)
            B.link(first, f"{self.tag}.{lo_end_pid}.{lo_i:03d}", "walk", width=3.1)
            B.link(last, f"{self.tag}.{hi_end_pid}.{hi_i:03d}", "walk", width=3.1)

    def _passage_coarse(self, ps: Passage, by_seg: dict, seg_ids: dict) -> None:
        """A planned (not yet modelled) passage: one graph node per 16 m corridor compartment, blast doors at the section bulkheads."""
        B = self.B
        prefix = f"{self.tag}.{ps.pid}"
        chunks = sorted(by_seg.items(), key=lambda kv: min(kv[1]))
        prev, prev_idxs = None, None
        for ck, idxs in chunks:
            cid = seg_ids[idxs[0]]
            lo, hi = min(idxs), max(idxs)
            if ps.along == "x":
                cx, cy = ps.a0 + (lo + hi + 1) * MOD / 2, ps.pos
            else:
                cx, cy = ps.pos, ps.a0 + (lo + hi + 1) * MOD / 2
            nid = f"{prefix}.{ck}"
            B.node(nid, self.deck, cx, cy, self.z0, "corridor", cid, passage=ps.pid)
            for i in idxs:
                ps.chunk_node[i] = nid
            if prev is not None:
                pe = ps.ev.get(max(prev_idxs), {})
                if pe.get("bulk") and not pe.get("bulk_aft"):
                    B.link(prev, nid, "door", door=self._blast(ps, max(prev_idxs), pe["bulk_x"]), width=BLAST_W, blast=True)
                else:
                    B.link(prev, nid, "walk", width=3.1)
            prev, prev_idxs = nid, idxs
        if ps.link_of:
            pa_id, ia, pb_id, ib, s, ya, yb = ps.link_of
            first, last = f"{prefix}.{chunks[0][0]}", f"{prefix}.{chunks[-1][0]}"
            lo_end_pid, lo_i = (pa_id, ia) if ya < yb else (pb_id, ib)
            hi_end_pid, hi_i = (pb_id, ib) if ya < yb else (pa_id, ia)
            B.link(first, self.passages[lo_end_pid].chunk_node[lo_i], "walk", width=3.1)
            B.link(last, self.passages[hi_end_pid].chunk_node[hi_i], "walk", width=3.1)

    def _blast(self, ps: Passage, i: int, bx: float) -> str:
        did = f"{self.tag}_bulk_{ps.pid.lower()}_{int(round(abs(bx)))}{'n' if bx < 0 else 'p'}"
        if did not in self.B.doors:
            secs = P.sections(self.deck)
            fwd = next((l for (l, x0, x1) in secs if abs(x0 - bx) < 1e-6), None)
            aft = next((l for (l, x0, x1) in secs if abs(x1 - bx) < 1e-6), None)
            self.B.door(did, self.deck, (bx - 0.3, ps.pos, self.z0), 0.0, BLAST_W, BLAST_H, None, None, kind="blast", blast=True,
                        passage=ps.pid, boundary=[aft, fwd], locked=False)
        return did

    def _signs(self, ps: Passage, i: int, bx: float) -> None:
        secs = P.sections(self.deck)
        fwd = next((l for (l, x0, x1) in secs if abs(x0 - bx) < 1e-6), None)     # the section whose aft edge is bx
        aft = next((l for (l, x0, x1) in secs if abs(x1 - bx) < 1e-6), None)     # the section that starts at bx and runs aft
        z = self.z0 + 2.98
        folder = f"Interior/Deck{self.deck:02d}/Signs"
        if aft:                                                                    # seen when walking aft: on the frame's forward face
            self.B.place(self.deck, f"SM_SHIP_Sign_{self.deck}{aft}", (bx + 0.03, ps.pos, z), 180.0, folder,
                         f"{self.tag}_sign_{ps.pid.lower()}_{aft}_fwdface", "sign")
        if fwd:                                                                    # seen when walking forward: on the aft face
            self.B.place(self.deck, f"SM_SHIP_Sign_{self.deck}{fwd}", (bx - 0.6 - 0.10 - 0.07, ps.pos, z), 0.0, folder,
                         f"{self.tag}_sign_{ps.pid.lower()}_{fwd}_aftface", "sign")

    # ------------------------------------------------------------------------------------------------------------- doors
    def _special_door(self, sd: dict) -> None:
        pass

    def finish_doors(self) -> None:
        """Fill in each room door's passage-side compartment, put the plates over the doors and join the rooms to the graph."""
        B = self.B
        for r in self.rooms:
            r["door_nodes"] = []
            for k, d in enumerate(r.get("doors", [])):
                ps = self.passages[d["pid"]]
                mod_node = ps.node_id(self.tag, d["i"], self.coarse)
                seg = B.nodes[mod_node]["comp"]
                rec = B.doors[d["id"]]
                rec["b"] = seg
                if seg in B.comps and rec["id"] not in B.comps[seg]["doors"]:
                    B.comps[seg]["doors"].append(rec["id"])
                if not self.coarse and d["wall"] == "near" and r["spec"].get("plate"):        # the plate over the door, on the corridor face
                    y = ps.pos + d["side"] * (HW - 0.06)
                    z = self.z0 + (2.72 if d["kind"] == "door" else 3.05)
                    yaw = -90.0 if d["side"] > 0 else 90.0
                    B.place(self.deck, f"SM_SHIP_Plate_{r['spec']['plate']}", (d["xw"], y, z), yaw, f"Interior/Deck{self.deck:02d}/Plates",
                            f"{self.tag}_plate_{r['cid'][len(self.tag) + 1:]}", "plate")
                nid = f"{r['cid']}.in{k}"                                 # a node just inside the room, behind the door
                B.node(nid, self.deck, d["xw"], d["y_wall"] + d["side"] * 1.2, self.z0, "door_in", r["cid"])
                B.link(mod_node, nid, "door", door=d["id"], width=d["w"])
                r["door_nodes"].append(nid)
            self._room_graph(r)

    def _room_graph(self, r: dict) -> None:
        """A hub node in the middle of the room joined to the door nodes, and every station of the room joined to the hub."""
        B = self.B
        cid = r["cid"]
        rec = B.comps[cid]
        b = rec["bounds"]
        hub = f"{cid}.hub"
        B.node(hub, self.deck, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, self.z0, "room", cid)
        for nid in r["door_nodes"]:
            B.link(nid, hub, "walk", width=1.5)
        for st in rec["stations"]:
            B.node(st["id"], self.deck, st["pos"][0], st["pos"][1], self.z0, "station", cid, role=st["role"], act=st["kind"], yaw=st["yaw"])
            B.link(hub, st["id"], "walk", width=1.0)
