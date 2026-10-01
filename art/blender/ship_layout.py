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
from ship_catalog import BLAST_H, BLAST_W, CLEAR_H, DOOR_H, DOOR_W, GATE_H, GATE_W, HW, MOD, SLOT_HW, TONE_DIMS, TONE_WALK_W, WALL_T, module_mesh

SEG_MODULES = 4                 # a corridor compartment (and its zone light) is 4 modules = 16 m long
MID_LINK_SECTION = 84.0         # a section longer than this (aft of the first 4 m, the bulkhead) gets a second cross link near its middle
FILL_LONG_RUN = 40.0            # a free stretch of at least this length (what the schedule left) takes two filler cells, a shorter one takes one


def rnd(v: float, n: int = 3) -> float:
    return round(v + 0.0, n)


class DesignError(Exception):
    """The schedule of a deck cannot be laid out (a room that does not fit, an overlap, an opening that clashes): a mistake in the design, reported with where it is."""


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
        self.arm_of = None                       # a Jefferies arm (NAVE-3): {parent, i, side, y_wall, trunk_idx, hatch}
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
        if e.get("trunk"):                                                    # a Jefferies trunk cell (K tone): the vertical shaft in the arm's first module
            return e["trunk"]                                                 # Trunk | TrunkTop | TrunkBottom
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
        straight = "Straight_" + ("AB"[i % 2] if self.tone == "T" else "ABC"[i % 3])                  # (the tunnel has two straight cells, the corridors three)
        table = {("wall", "wall"): straight, ("door", "wall"): f"Door_L_{v}", ("wall", "door"): f"Door_R_{v}",
                 ("door", "door"): "Door_LR", ("gate", "wall"): "Gate_L", ("wall", "gate"): "Gate_R", ("gate", "gate"): "Gate_LR",
                 ("branch", "wall"): "T_L", ("wall", "branch"): "T_R", ("branch", "branch"): "X"}
        if (L, R) not in table:
            raise ValueError(f"{self.pid} module {i} (x/y {self.centre(i)}): unsupported sides {L}/{R}")
        return table[(L, R)]

    def centre(self, i: int):
        a = self.a0 + i * MOD + 2.0
        return (a, self.pos) if self.along == "x" else (self.pos, a)


# the stair towers' variants by deck: the top of the column (Deck 2: the hall, the well and the roof), the 5.3 m climb of Deck 3 to Deck 2 (the armour deck lies between), the
# bottom of the column (Deck 12: the well has a floor)
TOWER_MESH = {2: "SM_SHIP_StairTowerCap", 3: "SM_SHIP_StairTower53", 12: "SM_SHIP_StairTowerBottom"}


class Deck:
    """The layout of one built deck. Declare passages, lanes and specials, then call `emit()`."""

    def __init__(self, B: Builder, deck: int, tag: str, coarse: bool = False) -> None:
        self.B, self.deck, self.tag, self.coarse = B, deck, tag, coarse
        self.z0, self.z1 = P.deck_z(deck)
        self.passages: dict[str, Passage] = {}
        self.rooms: list[dict] = []
        self.links: list[dict] = []
        self.arms: list[dict] = []                         # Jefferies arms (NAVE-3): dead-end passages along y that leave a passage's wall: a trunk cell and a crawlway
        self.specials_doors: list[dict] = []
        self.count: dict[str, int] = {}
        self.env = P.envelope(deck)
        self.anchors: dict[tuple[str, int], list[dict]] = {}      # (passage, side) -> the fixed items of a lane (banks, towers, links, arms), by forward edge
        self.partner: dict[tuple[str, int], str] = {}             # (passage, side) -> the passage across the lane (cross links go there)
        self.occ: dict[tuple[str, int], dict] = {}                # (passage, module) -> {"L": kind, "R": kind, "closed": bool}: what the corridor modules carry (a module with a
                                                                  # branch on one side cannot have a door on the other)
        self.lane_log: dict[tuple[str, int], list] = {}           # (passage, side) -> [(x forward, x aft, what)]: the table of the lane, for the programme report
        self.back: list[dict] = []                                # rooms behind a shallow fixed item (a stair tower), from the passage across the lane
        self.rects: list[tuple] = []                              # (x0, y0, x1, y1, what) of everything laid on the deck: two rooms may not share a floor
        self.last: dict[tuple[str, int], str] = {}                # (passage, side) -> the key of the room laid last there (the fillers do not repeat it)
        self.fill_count: dict[str, int] = {}                      # a filler's uses on this deck: the least used goes first

    # ------------------------------------------------------------------------------------------------------ declaration
    def passage(self, pid: str, tone: str, along: str, pos: float, a0: float, a1: float, name: str = "") -> Passage:
        p = Passage(pid, self.deck, tone, along, pos, a0, a1, name)
        self.passages[pid] = p
        return p

    def set_extent(self, pid: str, a0: float | None = None, a1: float | None = None) -> None:
        """Shorten (or lengthen) a passage along x before anything is laid on it (a hall of a special room takes over its end)."""
        ps = self.passages[pid]
        ps.a0 = ps.a0 if a0 is None else float(a0)
        ps.a1 = ps.a1 if a1 is None else float(a1)
        n = (ps.a1 - ps.a0) / MOD
        assert abs(n - round(n)) < 1e-6, f"{pid}: length {ps.a1 - ps.a0} is not a multiple of 4"
        ps.n = int(round(n))
        ps.ev.clear()                                                  # the bulkhead marks are by module index: do them again
        self.section_bulkheads([pid])

    def wall_plane(self, pid: str, side: int) -> float:
        return self.passages[pid].pos + side * SLOT_HW

    def lane(self, pid: str, side: int, x_start: float, items: list, lane: str) -> None:
        """Pack items from x_start towards the stern along passage `pid`'s wall on `side` (+1 right = +y, -1 left).
        items: ("key",) | ("key", {opts}) | ("gap", L) | ("link", partner[, tone]) | ("arm", n_modules, tone, {opts})"""
        assert self.passages[pid].along == "x"
        x = float(x_start)
        for it in items:
            if it[0] == "gap":
                x -= float(it[1])
                continue
            if it[0] == "link":
                self._add_link(pid, it[1], x - MOD / 2, it[2] if len(it) > 2 else "P")
                x -= MOD
                continue
            if it[0] == "arm":
                self._add_arm(pid, side, x - MOD / 2, it[1], it[2] if len(it) > 2 else "K", it[3] if len(it) > 3 else {})
                x -= MOD
                continue
            key, opt = it[0], (it[1] if len(it) > 1 else {})
            L = SP.PREFABS[key]["L"]
            self._add_room(pid, side, key, opt, x, lane)
            x -= L

    def rect_clash(self, x0: float, y0: float, x1: float, y1: float) -> str | None:
        for (a0, b0, a1, b1, what) in self.rects:
            if min(x1, a1) - max(x0, a0) > 0.05 and min(y1, b1) - max(y0, b0) > 0.05:
                return what
        return None

    def _room_rect(self, pid: str, side: int, key: str, x_fwd: float) -> tuple:
        spec = SP.PREFABS[key]
        yn = self.wall_plane(pid, side)
        ya, yb = yn, yn + side * spec["D"]
        return (x_fwd - spec["L"], min(ya, yb), x_fwd, max(ya, yb))

    def _add_room(self, pid: str, side: int, key: str, opt: dict, x_fwd: float, lane: str) -> dict:
        spec = SP.PREFABS[key]
        L = spec["L"]
        yaw = 0.0 if side > 0 else 180.0
        yn = self.wall_plane(pid, side)
        origin = (x_fwd - L if side > 0 else x_fwd, yn)
        r = dict(key=key, spec=spec, pid=pid, side=side, origin=origin, yaw=yaw, x_min=x_fwd - L, x_max=x_fwd, y_near=yn, opt=opt, lane=lane)
        self.rooms.append(r)
        rc = self._room_rect(pid, side, key, x_fwd)
        self.rects.append((*rc, f"{key} {pid}{side:+d} {x_fwd - L:.0f}..{x_fwd:.0f}"))
        for (opid, xw, rs, kind) in self.room_openings(r):
            self._occ_add(opid, xw, "R" if rs > 0 else "L", kind)
        self.lane_log.setdefault((pid, side), []).append((x_fwd, x_fwd - L, key))
        self.last[(pid, side)] = key
        return r

    def _add_link(self, a: str, b: str, xc: float, tone: str = "P") -> None:
        self.links.append({"a": a, "b": b, "x": xc, "tone": tone})
        pa, pb = self.passages[a], self.passages[b]
        s = 1 if pb.pos > pa.pos else -1
        self._occ_add(a, xc, "R" if s > 0 else "L", "branch")
        self._occ_add(b, xc, "L" if s > 0 else "R", "branch")
        self.lane_log.setdefault((a, s), []).append((xc + MOD / 2, xc - MOD / 2, f"link {tone} {a}-{b}"))

    def _add_arm(self, pid: str, side: int, xc: float, n: int, tone: str, opt: dict) -> None:
        """A Jefferies arm (the K crawlway that leaves the lane's passage across the lane at x = xc, n modules long; the first module is a trunk cell when opt['trunk'])."""
        self.arms.append(dict(pid=pid, side=side, x=xc, n=int(n), tone=tone, opt=opt))
        self._occ_add(pid, xc, "R" if side > 0 else "L", "door")
        self.lane_log.setdefault((pid, side), []).append((xc + MOD / 2, xc - MOD / 2, f"arm {tone}x{n}" + (" trunk" if opt.get("trunk") else "")))

    # ------------------------------------------------------------------------------------------- what the corridor modules carry
    def _occ_add(self, pid: str, xw: float, side_letter: str, kind: str) -> None:
        ps = self.passages.get(pid)
        if ps is None or ps.along != "x":
            return
        try:
            i = ps.center_index(xw)
        except ValueError:
            return
        o = self.occ.setdefault((pid, i), {})
        o.setdefault(side_letter, set()).add(kind)

    def _occ_conflict(self, openings: list, extra_closed: tuple = ()) -> str | None:
        """Would these openings (passage, x, room side, kind) clash with what the modules already carry? Returns what clashes, or None."""
        add: dict[tuple[str, int], dict] = {}
        for (pid, xw, rs, kind) in openings:
            ps = self.passages.get(pid)
            if ps is None or ps.along != "x":
                continue
            try:
                i = ps.center_index(xw)
            except ValueError:
                continue
            e = ps.ev.get(i, {})
            if e.get("bulk") or e.get("end"):
                return f"{pid} module {i} is a bulkhead or an end"
            sd = add.setdefault((pid, i), {})
            sd.setdefault("R" if rs > 0 else "L", set()).add(kind)
        for (pid, i), sd in add.items():
            cur = self.occ.get((pid, i), {})
            merged = {k: set(cur.get(k, set())) | set(sd.get(k, set())) for k in ("L", "R")}
            if any(len(v) > 1 for v in merged.values()):
                return f"{pid} module {i}: two kinds on one side {merged}"
            l = next(iter(merged["L"])) if merged["L"] else "wall"
            r = next(iter(merged["R"])) if merged["R"] else "wall"
            if (l, r) not in self.SUPPORTED:
                return f"{pid} module {i}: {l}/{r}"
        return None

    def reserve_bulkheads(self) -> None:
        """Mark the bulkhead modules (and nothing else) so that the packer never puts an opening on one."""
        self.section_bulkheads()

    # --------------------------------------------------------------------------------------------------------------- the packer
    @staticmethod
    def item_len(item: tuple) -> float:
        if item[0] == "gap":
            return float(item[1])
        if item[0] in ("link", "arm"):
            return MOD
        return SP.PREFABS[item[0]]["L"]

    def anchor(self, pid: str, side: int, x_fwd: float, item: tuple, back: str | None = None) -> float:
        """A fixed item of a lane at its forward edge `x_fwd`: a lift bank, a stair tower, a pinned room, a cross link, a Jefferies arm. It is placed now (the packer
        flows the other rooms of the lane around it). `back`: a prefab put behind a shallow item, from the passage across the lane (the 8 m left between a tower and
        the passage). Returns the aft edge. A clash with what the neighbouring modules already carry is a design error."""
        L = self.item_len(item)
        x_fwd = float(x_fwd)
        for o in self.anchors.get((pid, side), []):
            if min(o["x1"], x_fwd) - max(o["x0"], x_fwd - L) > 1e-6:
                raise DesignError(f"deck {self.deck} lane {pid}{side:+d}: {item[0]} at {x_fwd - L}..{x_fwd} overlaps {o['item'][0]} at {o['x0']}..{o['x1']}")
        a = dict(x1=x_fwd, x0=x_fwd - L, item=item, back=back)
        self.anchors.setdefault((pid, side), []).append(a)
        self._place_item(pid, side, x_fwd, item, "anchor", strict=True)
        if back:
            partner = self.passages.get(self.partner.get((pid, side), ""))
            if partner is not None and partner.a0 <= x_fwd - L + 1e-6 and partner.a1 >= x_fwd - 1e-6:         # (the passage across the lane may not reach here: the hull is narrow)
                self.back.append(dict(pid=pid, side=side, x1=x_fwd, key=back, L=L))
        return x_fwd - L

    def _openings_of(self, pid: str, side: int, x_fwd: float, item: tuple) -> list:
        """The openings an item would cut in the corridors' walls: [(passage, x, room side, kind)]."""
        if item[0] == "gap":
            return []
        if item[0] == "link":
            pa, pb = self.passages[pid], self.passages[item[1]]
            s = 1 if pb.pos > pa.pos else -1
            xc = x_fwd - MOD / 2
            return [(pid, xc, s, "branch"), (item[1], xc, -s, "branch")]
        if item[0] == "arm":
            return [(pid, x_fwd - MOD / 2, side, "door")]
        spec = SP.PREFABS[item[0]]
        r = dict(key=item[0], spec=spec, pid=pid, side=side, origin=(x_fwd - spec["L"] if side > 0 else x_fwd, self.wall_plane(pid, side)), yaw=0.0 if side > 0 else 180.0,
                 x_min=x_fwd - spec["L"], x_max=x_fwd, y_near=self.wall_plane(pid, side), opt=item[1] if len(item) > 1 else {})
        return self.room_openings(r)

    def _item_problem(self, pid: str, side: int, x_fwd: float, item: tuple) -> str | None:
        """Why this item cannot stand in the lane at x_fwd (an opening that clashes with the other side of the corridor, another room's floor, the hull), or None."""
        bad = self._occ_conflict(self._openings_of(pid, side, x_fwd, item))
        if not bad and item[0] not in ("gap", "link", "arm"):
            rc = self._room_rect(pid, side, item[0], x_fwd)
            clash = self.rect_clash(*rc)
            if clash:
                bad = f"the floor is taken by {clash}"
            else:                                                       # inside the hull: the envelope is already the hull less the wall
                far = max(abs(rc[1]), abs(rc[3]))
                hw = min(P.half_width_at(self.env, rc[0]) or 0.0, P.half_width_at(self.env, rc[2]) or 0.0, P.half_width_at(self.env, (rc[0] + rc[2]) / 2) or 0.0)
                if far > hw + 1e-6:
                    bad = f"the hull is {hw:.1f} m wide here, the room wants {far:.1f}"
        return bad

    def _place_item(self, pid: str, side: int, x_fwd: float, item: tuple, lane: str, strict: bool = False) -> bool:
        """Put an item in the lane at x_fwd (the packer's step). With strict a clash raises; otherwise it returns False and puts nothing."""
        bad = self._item_problem(pid, side, x_fwd, item)
        if bad:
            if strict:
                raise DesignError(f"deck {self.deck} lane {pid}{side:+d}: {item[0]} at {x_fwd - self.item_len(item)}..{x_fwd}: {bad}")
            return False
        if item[0] == "gap":
            self.lane_log.setdefault((pid, side), []).append((x_fwd, x_fwd - item[1], "gap"))
        elif item[0] == "link":
            self._add_link(pid, item[1], x_fwd - MOD / 2, item[2] if len(item) > 2 else "P")
        elif item[0] == "arm":
            self._add_arm(pid, side, x_fwd - MOD / 2, item[1], item[2] if len(item) > 2 else "K", item[3] if len(item) > 3 else {})
        else:
            self._add_room(pid, side, item[0], item[1] if len(item) > 1 else {}, x_fwd, lane)
        return True

    def flow(self, pid: str, side: int, sched: dict | list, fill: dict | list | None = None, lane: str | None = None, partner: str | None = None,
             a1: float | None = None, links: bool = True) -> None:
        """Fill a lane (a passage's wall on one side) with the rooms of a schedule, section by section from the forward end: `sched` is {section letter: [items]} (or a flat
        list for the whole lane), an item is a prefab key, (key, {opts}), ("gap", L), or ("link", partner[, tone]); the packer lays them in order, flows them round the lane's
        fixed items (`anchor`), stops each section at its bulkhead (the first 4 m of a section aft of its forward edge are the bulkhead's, then a cross link), and fills what is
        left of a section with the fillers `fill` ({letter: [keys]} or a list: the first that fits the run, an exact fit first). A room whose door would meet an opening on the
        other side of the corridor (a branch against a door, a gate against a door) is put a little later or swapped with one of the next three; a room that does not fit is
        an error (the schedule is wrong, not the engine)."""
        ps = self.passages[pid]
        assert ps.along == "x"
        secs = P.sections(self.deck)
        hi_lane = ps.a1 if a1 is None else a1
        lane = lane or f"{pid}{'+' if side > 0 else '-'}"
        link_to = partner or self.partner.get((pid, side))
        flat = sched if isinstance(sched, list) else None
        sched = {} if flat is not None else sched
        fills = fill if isinstance(fill, dict) else {"*": fill or []}
        anchors = sorted(self.anchors.get((pid, side), []), key=lambda a: -a["x1"])
        used_secs = [(l, xmin, xmax) for (l, xmin, xmax) in secs if min(xmax, hi_lane) - max(xmin, ps.a0) >= 4.0 - 1e-6]
        own_boundary = any(k_ > 0 and ps.a0 + 2 * MOD <= xmax_ <= hi_lane + 1e-6 for k_, (l_, xmin_, xmax_) in enumerate(secs))     # a section's boundary (so its bulkhead and cross link) lies on this piece
        if flat is not None:
            sched = {used_secs[0][0]: flat} if used_secs else {}
        for k, (letter, xmin, xmax) in enumerate(secs):
            lo, hi = max(xmin, ps.a0), min(xmax, hi_lane)
            if hi - lo < 4.0 - 1e-6:
                continue
            obstacles = [(a["x0"], a["x1"]) for a in anchors if a["x1"] > lo + 1e-6 and a["x0"] < hi - 1e-6]
            # the bulkhead's slot at the section's forward edge (not the first section's, not where the lane starts inside the section), and the cross link after it
            if k > 0 and abs(hi - xmax) < 1e-6:
                obstacles.append((hi - MOD, hi))
                if links and link_to:
                    placed_link = False
                    for off in (MOD, 2 * MOD, 3 * MOD, 4 * MOD, 5 * MOD, 6 * MOD):
                        xl = hi - off
                        if xl - MOD < lo - 1e-6 or any(min(o1, xl) - max(o0, xl - MOD) > 1e-6 for (o0, o1) in obstacles):
                            continue
                        pa, pb = self.passages[pid], self.passages[link_to]
                        if pb.a0 > xl - MOD + 1e-6 or pb.a1 < xl - 1e-6:
                            continue
                        if self._place_item(pid, side, xl, ("link", link_to, "P"), lane):
                            obstacles.append((xl - MOD, xl))
                            placed_link = True
                            break
            elif links and link_to and abs(hi - hi_lane) < 1e-6 and xmax - hi > MOD - 1e-6 and not own_boundary:
                # the lane starts inside the section (a piece of the Spine between two halls): a cross link near its forward end, so that the passage beside it is not cut off from it
                for off in (MOD, 2 * MOD, 3 * MOD, 4 * MOD, 5 * MOD, 6 * MOD):
                    xl = hi - off
                    if xl - MOD < lo - 1e-6 or any(min(o1, xl) - max(o0, xl - MOD) > 1e-6 for (o0, o1) in obstacles):
                        continue
                    pa, pb = self.passages[pid], self.passages[link_to]
                    if pb.a0 > xl - MOD + 1e-6 or pb.a1 < xl - 1e-6:
                        continue
                    if self._place_item(pid, side, xl, ("link", link_to, "P"), lane):
                        obstacles.append((xl - MOD, xl))
                        break
            # a long section gets a second cross link near its middle (a rider of the outer lane is never more than ~50 m from a way to the Spine and its lifts)
            if links and link_to and hi - lo > MID_LINK_SECTION:
                x_mid = lo + round((hi - lo) / 2.0 / MOD) * MOD
                for d_ in (0, MOD, -MOD, 2 * MOD, -2 * MOD, 3 * MOD, -3 * MOD, 4 * MOD, -4 * MOD):
                    xl = x_mid + d_
                    if xl - MOD < lo + MOD - 1e-6 or xl > hi - 4 * MOD + 1e-6 or any(min(o1, xl) - max(o0, xl - MOD) > 1e-6 for (o0, o1) in obstacles):
                        continue
                    pa, pb = self.passages[pid], self.passages[link_to]
                    if pb.a0 > xl - MOD + 1e-6 or pb.a1 < xl - 1e-6:
                        continue
                    if self._place_item(pid, side, xl, ("link", link_to, "P"), lane):
                        obstacles.append((xl - MOD, xl))
                        break
            obstacles.sort(key=lambda o: -o[1])
            runs: list[list[float]] = []                 # [forward edge, aft edge] of the free stretches, forward first
            cur = hi
            for (o0, o1) in obstacles:
                if o1 < cur - 1e-6:
                    runs.append([cur, max(o1, lo)]) if cur - max(o1, lo) > 1e-6 else None
                cur = min(cur, o0)
            if cur - lo > 1e-6:
                runs.append([cur, lo])
            items = [it if isinstance(it, tuple) else (it,) for it in sched.get(letter, [])]
            pool = bool(items) and items[0] == ("pool",)              # a pool: the items are laid wherever they fit best (an industrial zone), not in the order given
            if pool:
                items = items[1:]
            fillers = fills.get(letter, fills.get("*", []))
            self._pack_section(pid, side, letter, runs, items, fillers, lane, pool)

    def _pack_section(self, pid: str, side: int, letter: str, runs: list, items: list, fillers: list, lane: str, pool: bool = False) -> None:
        pending = list(items)
        rot = 0
        small = min([self.item_len((f,)) for f in fillers] + [self.item_len(it) for it in pending if it[0] != "gap"] + [8.0]) if (pool or fillers) else 8.0
        for run in runs:
            x = run[0]
            while True:
                room = x - run[1]
                if room < 1e-6:
                    break
                placed = False
                if pending:
                    look = list(range(min(4, len(pending))))
                    exact = [j for j in look if abs(self.item_len(pending[j]) - room) < 1e-6 and pending[j][0] != "gap"]
                    order = exact + [k for k in look if k not in exact]
                    if pool:                                              # the best fit among all: an exact one; then the largest that leaves no remainder too short for anything
                        look = list(range(len(pending)))
                        def score(j):
                            L = self.item_len(pending[j])
                            rem = room - L
                            return (0 if rem < 1e-6 else 1 if rem >= small - 1e-6 else 2, -L, j)
                        order = sorted([j for j in look if self.item_len(pending[j]) <= room + 1e-6], key=score)
                    for j in order:
                        it = pending[j]
                        L = self.item_len(it)
                        if L > room + 1e-6:
                            continue
                        if it[0] == "gap":
                            pending.pop(j)
                            x -= L
                            placed = True
                            break
                        if self._place_item(pid, side, x, it, lane):
                            pending.pop(j)
                            x -= L
                            placed = True
                            break
                    if not placed:
                        # nothing of the next four fits here: a gap of one to three modules (a chase) may clear a door against a branch, a longer one (the hull is too narrow here)
                        # carries the run to where a room fits; otherwise the rest of the run is filled / left
                        cands = [j for j in look if pending[j][0] != "gap"]
                        hull = bool(cands) and all("the hull is" in (self._item_problem(pid, side, x, pending[j]) or "") for j in cands)
                        kmax = int((room - min([self.item_len(pending[j]) for j in cands] + [1e9])) / MOD + 1e-6) if cands else 0
                        for kk in range(1, (kmax if hull else min(3, kmax)) + 1):
                            xs = x - kk * MOD
                            if any(self.item_len(pending[j]) <= xs - run[1] + 1e-6 and self._item_problem(pid, side, xs, pending[j]) is None for j in cands):
                                self.lane_log.setdefault((pid, side), []).append((x, xs, "gap"))
                                x = xs
                                placed = True
                                break
                if not placed:
                    # the remainder of this run: fillers
                    fl = self._fill_run(pid, side, x, run[1], fillers, lane, rot)
                    rot += 1
                    x = fl
                    if x - run[1] > 1e-6:
                        self.lane_log.setdefault((pid, side), []).append((x, run[1], "gap"))
                    break
        if pending:
            left = [f"{it[0]} ({self.item_len(it)} m)" for it in pending if it[0] != "gap" and not pool and not (len(it) > 1 and isinstance(it[-1], dict) and it[-1].get("optional"))]
            if left:
                raise DesignError(f"deck {self.deck} lane {pid}{side:+d} section {letter}: the schedule does not fit: {left} left over (runs {[(round(a, 1), round(b, 1)) for a, b in runs]})")

    def _shift_ok(self, pid: str, side: int, x_fwd: float, cands: list) -> bool:
        """Can one of these items stand at x_fwd (4 m further aft than the pointer) without a clash?"""
        for it in cands:
            if it[0] == "gap":
                continue
            if not self._occ_conflict(self._openings_of(pid, side, x_fwd, it)):
                return True
        return False

    def _fill_run(self, pid: str, side: int, x_hi: float, x_lo: float, fillers: list, lane: str, rot: int) -> float:
        """Fill [x_lo, x_hi] with fillers; returns where the filling stopped (x_lo, or higher when no filler fits). An exact fit goes first, then a filler that is not the room
        laid just before, then the least used on this deck, then the larger."""
        x = x_hi
        guard = 0
        cap = 1 if x_hi - x_lo < FILL_LONG_RUN else 2          # a leftover stretch gets a cell or two, not a row of them: the rest of it is a void (a reserve volume, a chase, a cofferdam: nothing to build)
        while x - x_lo >= 4.0 - 1e-6 and fillers and guard < cap:
            guard += 1
            room = x - x_lo
            last = self.last.get((pid, side))
            order = sorted(range(len(fillers)), key=lambda j: (0 if abs(self.item_len((fillers[j],)) - room) < 1e-6 else 1, 1 if fillers[j] == last else 0,
                                                              self.fill_count.get(fillers[j], 0), -self.item_len((fillers[j],)), (j + rot) % len(fillers)))
            ok = False
            for j in order:
                L = self.item_len((fillers[j],))
                if L > room + 1e-6:
                    continue
                if self._place_item(pid, side, x, (fillers[j],), lane):
                    self.fill_count[fillers[j]] = self.fill_count.get(fillers[j], 0) + 1
                    self.rooms[-1]["filler"] = True                       # (the programme report counts the rooms nobody asked for apart)
                    x -= L
                    ok = True
                    break
            if not ok:
                break
        return x

    def special(self, cid: str, key: str, origin, yaw: float, bounds, folder_section: str, name: str | None = None, plate: str | None = None) -> dict:
        """A hand-placed prefab (concourse, lobby, bow observation deck): its compartment, placement and graph hooks. Returns the room record."""
        B = self.B
        spec = SP.PREFABS[key]
        o3 = (origin[0], origin[1], self.z0)
        stations = []
        for i, s in enumerate(spec["spots"]):
            w = P.place_local(o3, yaw, s["x"], s["y"])
            stations.append({"id": f"{cid}.s{i}", "role": s["role"], "kind": s["kind"], "pos": [rnd(w[0]), rnd(w[1]), rnd(self.z0 + s.get("dz", 0.0))],
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
        self.rects.append((bounds[0], bounds[1], bounds[2], bounds[3], f"{key} (special {cid})"))
        return r

    def gate(self, r: dict, did: str, pid: str, xw: float, room_side: int, w: float, h: float, wall: str = "special") -> None:
        """A door / gate between the special room `r` and passage `pid` at x = xw; the room lies on `room_side` of the passage."""
        ps = self.passages[pid]
        self._room_door(r, r["cid"], {"wall": wall, "w": w, "h": h, "id": did}, xw, ps.pos + room_side * SLOT_HW, pid, room_side)
        self._occ_add(pid, xw, "R" if room_side > 0 else "L", "gate" if w > 2.0 else "door")           # (the lanes' rooms leave the opposite wall of this module alone)

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

    # ---------------------------------------------------------------------------------------------------------- conflicts
    SUPPORTED = {("wall", "wall"), ("door", "wall"), ("wall", "door"), ("door", "door"), ("gate", "wall"), ("wall", "gate"), ("gate", "gate"),
                 ("branch", "wall"), ("wall", "branch"), ("branch", "branch")}

    def room_openings(self, r: dict) -> list[tuple[str, float, int, str]]:
        """(passage id, x of the door, room side, kind) of every door of a room that cuts an opening in a corridor wall (none for a room not modelled yet on
        a built deck: its wall stays plain)."""
        if r.get("done"):
            return []
        spec = r["spec"]
        if (not self.coarse) and spec.get("mesh") is None and not r["opt"].get("built"):
            return []
        out = []
        for d in spec["doors"]:
            dx = r["opt"].get("door_x", d["x"]) if d["wall"] == "near" else r["opt"].get("far_door_x", d["x"])
            xw = r["origin"][0] + (dx if r["yaw"] == 0.0 else -dx)
            kind = "gate" if d["w"] > 2.0 else "door"
            if d["wall"] == "near":
                out.append((r["pid"], xw, r["side"], kind))
            elif d["wall"] == "far":
                yf = r["y_near"] + r["side"] * spec["D"]
                other = next((p for p in self.passages.values() if p.along == "x" and p.tone != "V" and abs(abs(yf - p.pos) - SLOT_HW) < 1e-6), None)       # (a far door opens on a main passage, never on a hull gallery)
                if other is not None:
                    out.append((other.pid, xw, -r["side"], kind))
        return out

    def resolve_conflicts(self) -> list[str]:
        """A corridor module cannot carry a branch on one side and a door (or a gate) on the other, nor an opening on a bulkhead or an end wall. Drop the rooms of the
        lanes whose doors would meet such a neighbour (the layout of a built deck made from a programme does not look at the other side of the corridor); returns the
        ids of the rooms dropped."""
        self.section_bulkheads()
        dropped: list[str] = []
        for _ in range(400):
            sides: dict[tuple[str, int], dict[str, list]] = {}
            for lk in self.links:
                pa, pb = self.passages[lk["a"]], self.passages[lk["b"]]
                s_ = 1 if pb.pos > pa.pos else -1
                for ps, sd in ((pa, "R" if s_ > 0 else "L"), (pb, "L" if s_ > 0 else "R")):
                    try:
                        i = ps.center_index(lk["x"])
                    except ValueError:
                        continue
                    sides.setdefault((ps.pid, i), {}).setdefault(sd, []).append(("branch", lk))
            for r in self.rooms:
                for (pid, xw, rs, kind) in self.room_openings(r):
                    try:
                        i = self.passages[pid].center_index(xw)
                    except ValueError:
                        continue
                    sides.setdefault((pid, i), {}).setdefault("R" if rs > 0 else "L", []).append((kind, r))
            victim = None
            for (pid, i), sd in sides.items():
                e = self.passages[pid].ev.get(i, {})
                closed = bool(e.get("bulk") or e.get("end"))
                kinds = {k: {c[0] for c in v} for k, v in sd.items()}
                multi = any(len(v) > 1 for v in kinds.values())                     # two different kinds on one side of a module
                lk_ = next(iter(kinds["L"])) if len(kinds.get("L", ())) == 1 else "wall"
                rk_ = next(iter(kinds["R"])) if len(kinds.get("R", ())) == 1 else "wall"
                bad = closed or multi or (lk_, rk_) not in self.SUPPORTED
                if not bad:
                    continue
                owners = [c[1] for v in sd.values() for c in v if c[1] is not None]
                if owners:
                    # a room goes before a cross link, a cross link before a stair tower
                    owners.sort(key=lambda o: (2 if "spec" in o and o["spec"]["key"] == "stair_tower" else 1 if "spec" not in o else 0))
                    victim = owners[0]
                    break
            if victim is None:
                return dropped
            if "spec" in victim:
                self.rooms.remove(victim)
                dropped.append(victim["spec"]["key"])
            else:
                self.links.remove(victim)
                dropped.append(f"link {victim['a']}-{victim['b']}")
        raise RuntimeError("resolve_conflicts: no end to it")

    def ends(self, pid: str, fwd: str | None = None, aft: str | None = None) -> None:
        """Close a passage's ends ('wall' -> an End module); leave None where it opens into a hall."""
        ps = self.passages[pid]
        if fwd == "wall":
            ps.mark(ps.n - 1, end="fwd")
        if aft == "wall":
            ps.mark(0, end="aft")

    # ----------------------------------------------------------------------------------------------------------------- emit
    def place_backs(self) -> None:
        """The rooms behind a shallow fixed item (a tower's 8 m of depth): from the passage across the lane, side by side with the item."""
        for bk in self.back:
            spec = SP.PREFABS[bk["key"]]
            partner = self.partner.get((bk["pid"], bk["side"]))
            if partner is None:
                raise DesignError(f"deck {self.deck}: a room behind the {bk['L']} m item at {bk['x1']} needs the passage across the lane ({bk['pid']}{bk['side']:+d} has none)")
            if abs(spec["L"] - bk["L"]) > 1e-6:
                raise DesignError(f"deck {self.deck}: the back room {bk['key']} ({spec['L']} m) does not match the item it stands behind ({bk['L']} m)")
            if not self._place_item(partner, -bk["side"], bk["x1"], (bk["key"], bk.get("opt", {})), "back"):
                raise DesignError(f"deck {self.deck}: the back room {bk['key']} at {bk['x1'] - bk['L']}..{bk['x1']} on {partner} clashes with an opening opposite")
        self.back = []

    def emit(self) -> None:
        self.place_backs()
        self.rooms.sort(key=lambda r: (-(r.get("x_max", 0.0)), r.get("pid", ""), r.get("side", 0)))      # the ids count from the bow
        for r in self.rooms:
            if not r.get("done"):
                self._room(r)
        for lk in self.links:
            self._link(lk)
        for ar in self.arms:
            self._arm(ar)
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
        lx0, ly0, lx1, ly1 = spec.get("lobby") or (0.0, 0.0, L, D)          # a lift bank's compartment is the lobby: the shafts' strip along its x = 0 wall is not part of it
        a, b = self.local(r, lx0, ly0), self.local(r, lx1, ly1)
        bounds = [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])]
        stations = []
        for i, s in enumerate(spec["spots"]):
            w = self.local(r, s["x"], s["y"])
            stations.append({"id": f"{cid}.s{i}", "role": s["role"], "kind": s["kind"], "pos": [rnd(w[0]), rnd(w[1]), rnd(self.z0 + s.get("dz", 0.0))],
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
        r["plate"] = r["opt"].get("plate") or spec.get("plate")
        extra = {k: r["opt"][k] for k in ("bank",) if k in r["opt"]}
        rec = B.comp(cid, self.deck, spec["kind"], r["opt"].get("name") or spec["name"], bounds, (self.z0, self.zt(spec["h"])), dept=spec["dept"],
                     prefab=key, mesh=spec.get("mesh"), pos=[rnd(r["origin"][0]), rnd(r["origin"][1]), rnd(self.z0)], yaw=r["yaw"],
                     systems=list(spec["systems"]), stations=stations, lights=lights, plate=r["plate"], status="built" if built else "planned",
                     lane=r["lane"], size=[L, D, spec["h"]], crew_slots=slots, **extra)
        r["cid"], r["bounds"] = cid, bounds
        if built:
            mesh = TOWER_MESH.get(self.deck, spec["mesh"]) if key == "stair_tower" else spec["mesh"]
            B.place(self.deck, mesh, (r["origin"][0], r["origin"][1], self.z0), r["yaw"],
                    f"Interior/Deck{self.deck:02d}/Rooms/{rec['section']}", cid, "room", comp=cid)
        for d in spec["doors"]:
            dx = r["opt"].get("door_x", d["x"]) if d["wall"] == "near" else r["opt"].get("far_door_x", d["x"])
            xw = r["origin"][0] + (dx if r["yaw"] == 0.0 else -dx)
            if d["wall"] == "near":
                self._room_door(r, cid, d, xw, r["y_near"], r["pid"], r["side"])
            elif d["wall"] == "far":
                yf = r["y_near"] + r["side"] * D
                other = next((p for p in self.passages.values() if p.along == "x" and p.tone != "V" and abs(abs(yf - p.pos) - SLOT_HW) < 1e-6), None)       # (a far door opens on a main passage, never on a hull gallery)
                if other is not None:
                    self._room_door(r, cid, d, xw, yf, other.pid, -r["side"])

    def _room_door(self, r: dict, cid: str, d: dict, xw: float, y_wall: float, pid: str, room_side: int) -> None:
        """A door of the room on the wall plane y_wall of passage `pid`; the room lies on `room_side` (+1 = +y) of that passage."""
        ps = self.passages[pid]
        i = ps.center_index(xw)
        kind = "gate" if d["w"] > 2.0 else "door"
        blank = (not self.coarse) and r["spec"].get("mesh") is None and not r["opt"].get("built")     # a room not modelled yet on a built deck
        if not blank:
            ps.side(i, "R" if room_side > 0 else "L", kind)
        did = d.get("id") or (f"{self.tag}_door_{cid[len(self.tag) + 1:]}" + ("_far" if d["wall"] == "far" else ""))
        if not d.get("id"):                                                  # a room with two doors on one wall (the shuttle bay's): the second is `_2`, the third `_3`
            base, n = did, 2
            while did in self.B.doors:
                did, n = f"{base}_{n}", n + 1
        pos = (xw, y_wall - room_side * WALL_T / 2, self.z0)
        r.setdefault("doors", []).append(dict(id=did, pos=pos, w=d["w"], h=d["h"], pid=pid, i=i, side=room_side, kind=kind, wall=d["wall"], xw=xw,
                                               y_wall=y_wall))
        extra = {"planned": True, "locked": True} if blank else {}
        self.B.door(did, self.deck, pos, 90.0, d["w"], d["h"], cid, None, kind=kind, wall=d["wall"], passage=pid,
                    plate=(r.get("plate") or r["spec"].get("plate")) if d["wall"] == "near" else None, side=room_side, **extra)
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
        tone = lk.get("tone", "P")
        lp = Passage(lid, self.deck, tone, "y", xc, min(ya, yb), max(ya, yb), name=lk.get("name") or (f"{pa.pid}-{pb.pid} link" if tone == "P" else f"Service link {pa.pid}-{pb.pid}"))
        lp.link_of = (pa.pid, ia, pb.pid, ib, s, ya, yb)
        self.passages[lid] = lp

    def _arm(self, ar: dict) -> None:
        """A Jefferies arm: a K crawlway along y that leaves the lane's passage by a hatch in its wall; its first module is the trunk cell (the vertical ladder shaft)."""
        ps = self.passages[ar["pid"]]
        side, xc, n, opt = ar["side"], ar["x"], ar["n"], ar["opt"]
        i = ps.center_index(xc)
        ps.side(i, "R" if side > 0 else "L", "door")
        ya = ps.pos + side * SLOT_HW
        yb = ya + side * MOD * n
        aid = f"{ps.pid}J{int(round(abs(xc)))}{'n' if xc < 0 else 'p'}"
        ap = Passage(aid, self.deck, ar["tone"], "y", xc, min(ya, yb), max(ya, yb), name=opt.get("name") or "Jefferies Tube")
        t_idx = 0 if side > 0 else n - 1                      # the module next to the parent passage
        if opt.get("trunk"):
            ap.mark(t_idx, trunk=opt["trunk"])
        if opt.get("end", "wall") == "wall":
            ap.mark(n - 1 if side > 0 else 0, end="fwd" if side > 0 else "aft")
        ap.arm_of = dict(parent=ps.pid, i=i, side=side, y_wall=ya, trunk_idx=t_idx if opt.get("trunk") else None, hatch=f"{self.tag}_hatch_{aid}", gallery=opt.get("gallery"))
        self.passages[aid] = ap
        self.B.door(ap.arm_of["hatch"], self.deck, (xc, ya - side * WALL_T / 2, self.z0), 90.0, DOOR_W, DOOR_H, None, None, kind="door", wall="arm", passage=ps.pid,
                    side=side, hatch=True)

    # ----------------------------------------------------------------------------------------------------------- passages
    def _passage(self, ps: Passage) -> None:
        B = self.B
        prefix = f"{self.tag}.{ps.pid}"
        folder = f"Interior/Deck{self.deck:02d}/Passages"
        secs = P.sections(self.deck)
        seg_ids: dict[int, str] = {}
        seg_counter: dict[str, int] = {}
        # -- corridor compartments (16 m each, per section) and their zone lights; the trunk cell of a Jefferies arm is a compartment of its own
        chunk_start: dict[str, float] = {}
        trunk_i = ps.arm_of["trunk_idx"] if ps.arm_of else None
        for i in range(ps.n):
            cx, cy = ps.centre(i)
            a = ps.a0 + i * MOD
            key_sec = self._sec(cx if ps.along == "x" else cx)
            if i == trunk_i:
                seg_ids[i] = f"{key_sec}T"
                continue
            if ps.along == "x":
                sec_end = next((sx1 for (l, sx0, sx1) in secs if l == key_sec), a + MOD)
                idx = int(math.floor((sec_end - (a + MOD)) / (MOD * SEG_MODULES) + 1e-6))
            else:
                idx = (i - (1 if trunk_i is not None and i > trunk_i else 0)) // SEG_MODULES
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
            temp = {"S": 5600.0, "V": 3000.0, "T": 5000.0}.get(ps.tone, 3900.0)
            clear = TONE_DIMS[ps.tone][1]
            narrow = ps.tone in ("K", "V")
            lumens = {"K": 1500, "V": 1800, "T": 3000}.get(ps.tone, 3400)
            is_trunk = ps.arm_of is not None and idxs == [trunk_i]
            kind = "trunk" if is_trunk else "tunnel" if ps.tone == "T" else "corridor"
            systems = (["life_support"] if is_trunk else ["transit", "power_bus"] if ps.tone == "T" else
                       ["power_bus", "life_support", "data_trunk"] if ps.tone == "S" else ["power_bus", "life_support"])
            extra = {} if self.coarse else dict(
                systems=systems,
                lights=[{"id": f"{cid}.l0", "type": "rect", "pos": [rnd(xc), rnd(yc), rnd(self.z0 + clear - 0.12)], "lumens": lumens, "temperature": temp,
                         "size": size if not narrow else [size[0], 0.3] if ps.along == "x" else [0.3, size[1]], "radius": 1000.0 if not narrow else 600.0, "shadows": False}])
            cname = (f"Jefferies Trunk · Deck {self.deck}" if is_trunk else f"{lname} · Section {sec}")
            B.comp(cid, self.deck, kind, cname, bounds, section=sec, status="planned" if self.coarse else "built",
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
            if ps.tone == "T":                                    # the shuttle's tunnel is not walked: its nodes and its `shuttle` edges are the plan's (ship_design_shuttle.plan)
                if suffix == "Bulkhead" and not e.get("bulk_aft"):         # the tunnel's blast gate at a section's frame (the car passes through it; no graph node: the record is for the damage model)
                    rec = B.doors[self._blast(ps, i, e["bulk_x"])]
                    rec["a"], rec["b"] = seg_ids[i], seg_ids[min(i + 1, ps.n - 1)]
                    rec["width"], rec["height"] = rnd(2 * TONE_DIMS["T"][0]), TONE_DIMS["T"][1]
                    for c_ in (rec["a"], rec["b"]):
                        if rec["id"] not in B.comps[c_]["doors"]:
                            B.comps[c_]["doors"].append(rec["id"])
                continue
            nid = f"{prefix}.{i:03d}"
            B.node(nid, self.deck, cx, cy, self.z0, "trunk" if ps.arm_of and i == ps.arm_of["trunk_idx"] else "corridor", seg_ids[i], passage=ps.pid)
            w = TONE_WALK_W[ps.tone]
            if prev is not None:
                pe = ps.ev.get(i - 1, {})
                if pe.get("bulk") and not pe.get("bulk_aft"):
                    B.link(prev, nid, "door", door=self._blast(ps, i - 1, pe["bulk_x"]), width=BLAST_W, blast=True)
                elif e.get("bulk") and e.get("bulk_aft"):
                    B.link(prev, nid, "door", door=self._blast(ps, i, e["bulk_x"]), width=BLAST_W, blast=True)
                else:
                    B.link(prev, nid, "walk", width=w)
            prev = nid
            if e.get("bulk") and not e.get("bulk_aft") and ps.along == "x":
                # section signs on both faces of the frame (placed once here, meshes SM_SHIP_Sign_<deck><section>)
                self._signs(ps, i, e["bulk_x"])
        # cross-link ends join the through passages at the junction modules
        if ps.link_of and ps.tone != "T":
            pa_id, ia, pb_id, ib, s, ya, yb = ps.link_of
            first, last = f"{prefix}.{0:03d}", f"{prefix}.{ps.n - 1:03d}"
            lo_end_pid, lo_i = (pa_id, ia) if ya < yb else (pb_id, ib)
            hi_end_pid, hi_i = (pb_id, ib) if ya < yb else (pa_id, ia)
            B.link(first, f"{self.tag}.{lo_end_pid}.{lo_i:03d}", "walk", width=TONE_WALK_W[ps.tone])
            B.link(last, f"{self.tag}.{hi_end_pid}.{hi_i:03d}", "walk", width=TONE_WALK_W[ps.tone])
        # a Jefferies arm joins its parent passage by the hatch in the wall
        if ps.arm_of:
            ar = ps.arm_of
            near = f"{prefix}.{ar['trunk_idx'] if ar['trunk_idx'] is not None else (0 if ar['side'] > 0 else ps.n - 1):03d}"
            B.link(near, f"{self.tag}.{ar['parent']}.{ar['i']:03d}", "door", door=ar["hatch"], width=DOOR_W)

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
        if ps.tone in ("K", "V", "T"):                                              # a crawlway has no room for a hanging sign: the section is on the plates of the rooms
            return
        secs = P.sections(self.deck)
        fwd = next((l for (l, x0, x1) in secs if abs(x0 - bx) < 1e-6), None)     # the section whose aft edge is bx
        aft = next((l for (l, x0, x1) in secs if abs(x1 - bx) < 1e-6), None)     # the section that starts at bx and runs aft
        z = self.z0 + 2.98
        folder = f"Interior/Deck{self.deck:02d}/Signs"
        if aft:                                                                    # seen when walking aft: on the frame's forward face
            self.B.place(self.deck, f"SM_SHIP_Sign_{self.deck}{aft}", (bx + 0.045, ps.pos, z), 180.0, folder,
                         f"{self.tag}_sign_{ps.pid.lower()}_{aft}_fwdface", "sign")
        if fwd:                                                                    # seen when walking forward: on the aft face
            self.B.place(self.deck, f"SM_SHIP_Sign_{self.deck}{fwd}", (bx - 0.673, ps.pos, z), 0.0, folder,
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
                if not self.coarse and d["wall"] == "near" and (r.get("plate") or r["spec"].get("plate")):        # the plate over the door, on the corridor face
                    hw_c, clear_c = TONE_DIMS[ps.tone]
                    y = ps.pos + d["side"] * (hw_c - 0.06)
                    z = self.z0 + (2.72 if d["kind"] == "door" else 3.05)
                    xp = d["xw"]
                    if ps.tone in ("K", "V"):                                   # a crawlway has no height over its hatches: the plate hangs beside the hatch, on the wall
                        z, xp = self.z0 + 1.75, d["xw"] + (1.2 if ps.along == "x" else 0.0)
                    yaw = -90.0 if d["side"] > 0 else 90.0
                    plate = r.get("plate") or r["spec"]["plate"]
                    if plate == "stairs":                                   # the plate says where the flights go from this deck
                        plate = f"stairs_{self.deck}"
                    B.place(self.deck, f"SM_SHIP_Plate_{plate}", (xp, y, z), yaw, f"Interior/Deck{self.deck:02d}/Plates",
                            f"{self.tag}_plate_{r['cid'][len(self.tag) + 1:]}" + (f"_{k + 1}" if k else ""), "plate")
                nid = f"{r['cid']}.in{k}"                                 # a node just inside the room, behind the door
                B.node(nid, self.deck, d["xw"], d["y_wall"] + d["side"] * 1.2, self.z0, "door_in", r["cid"])
                B.link(mod_node, nid, "door", door=d["id"], width=d["w"])
                r["door_nodes"].append(nid)
            self._room_graph(r)
        # the hatches of the Jefferies arms: the parent passage's segment on one side, the arm's first compartment (the trunk cell) on the other
        for ps in self.passages.values():
            if not ps.arm_of:
                continue
            ar = ps.arm_of
            rec = B.doors[ar["hatch"]]
            parent_seg = B.nodes[f"{self.tag}.{ar['parent']}.{ar['i']:03d}"]["comp"]
            first = ar["trunk_idx"] if ar["trunk_idx"] is not None else (0 if ar["side"] > 0 else ps.n - 1)
            arm_seg = B.nodes[f"{self.tag}.{ps.pid}.{first:03d}"]["comp"]
            rec["a"], rec["b"] = parent_seg, arm_seg
            for c_ in (parent_seg, arm_seg):
                if c_ in B.comps and rec["id"] not in B.comps[c_]["doors"]:
                    B.comps[c_]["doors"].append(rec["id"])
            if ar.get("gallery"):                                   # the arm's far end opens on the junction of its hull gallery (a cell of the same slot: no door)
                gid, gi = ar["gallery"]
                far = ps.n - 1 if ar["side"] > 0 else 0
                B.link(f"{self.tag}.{ps.pid}.{far:03d}", f"{self.tag}.{gid}.{gi:03d}", "walk", width=TONE_WALK_W["K"])

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
            B.node(st["id"], self.deck, st["pos"][0], st["pos"][1], st["pos"][2], "station", cid, role=st["role"], act=st["kind"], yaw=st["yaw"])
            B.link(hub, st["id"], "walk", width=1.0)
