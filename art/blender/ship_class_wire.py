"""ASTRA ships: the doors and the walk graph of a class plan (FLOTTA-VIVA): the junctions of the cross corridors, a door from every room to the
corridor beside it, the pressure bulkheads across every lane at each section boundary, and the chains of nodes along the corridors and into
the rooms. A mixin of ship_class_build.Builder. Pure Python."""
from __future__ import annotations

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from ship_class_engine import BLAST_H, BLAST_W, PASS_HW, SPINE_HW, WALL, clamp, r2  # noqa: E402


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def shared_wall(a: dict, b: dict):
    """The wall two boxes share, as (facing, coordinate, lo, hi): facing 'y' for boxes side by side across y (a door in it faces y), 'x' for
    boxes one behind the other along x. None when they do not touch (a gap of a wall at most) over at least 1.2 m."""
    ax0, ay0, ax1, ay1 = a["bounds"]
    bx0, by0, bx1, by1 = b["bounds"]
    ox, oy = overlap(ax0, ax1, bx0, bx1), overlap(ay0, ay1, by0, by1)
    gap_y = max(by0 - ay1, ay0 - by1)
    gap_x = max(bx0 - ax1, ax0 - bx1)
    if ox >= 1.2 and -0.02 <= gap_y <= 0.5:
        edge = (ay1 + by0) / 2 if by0 >= ay1 - 0.02 else (by1 + ay0) / 2
        return ("y", edge, max(ax0, bx0), min(ax1, bx1))
    if oy >= 1.2 and -0.02 <= gap_x <= 0.5:
        edge = (ax1 + bx0) / 2 if bx0 >= ax1 - 0.02 else (bx1 + ax0) / 2
        return ("x", edge, max(ay0, by0), min(ay1, by1))
    return None


class Wiring:
    # --------------------------------------------------------------------------------------------------------------- doors
    def door_between(self, a: dict, b: dict, prefer: float | None = None, deck=None, kind: str = "door", **kw):
        w = shared_wall(a, b)
        if not w:
            return None
        facing, coord, lo, hi = w
        l2, h2 = lo + 0.9, hi - 0.9
        if h2 < l2:
            l2 = h2 = 0.5 * (lo + hi)
        if prefer is None:
            prefer = 0.5 * (lo + hi)
        t = clamp(prefer, l2, h2)
        z = deck.z if deck is not None else None
        if facing == "y":
            return self.door(a, b, t, coord, 90.0, kind=kind, z=z, **kw)
        return self.door(a, b, coord, t, 0.0, kind=kind, z=z, **kw)

    def wire_deck(self, d):
        L = self.L[d.id]
        # ---- the junctions of the cross corridors with the spine and the passage they join (no door: an open way)
        for c in L.cross:
            cx = 0.5 * (c["bounds"][0] + c["bounds"][2])
            side = 1 if c["bounds"][1] >= 0 else -1
            spine = next((s for s in L.spine if s["bounds"][0] - 0.05 <= cx <= s["bounds"][2] + 0.05), None)
            pas = next((p for p in L.passage[side] if p["bounds"][0] - 0.05 <= cx <= p["bounds"][2] + 0.05), None)
            ys, yp = side * SPINE_HW, side * (d.YP - PASS_HW)
            n_s = self.node(c, cx, ys + side * 0.4, "corridor", "s")
            n_p = self.node(c, cx, yp - side * 0.4, "corridor", "p")
            self.edge(n_s, n_p, abs(yp - ys) - 0.8, "walk", w=3.0)
            if spine:
                self.edge(self.node(spine, cx, 0.0, "corridor", "j"), n_s, SPINE_HW + 0.4, "walk", w=3.0)
            if pas:
                self.edge(self.node(pas, cx, side * d.YP, "corridor", "j"), n_p, PASS_HW + 0.4, "walk", w=3.0)
        # ---- a door from every room to the corridors beside it
        corridors = L.spine + L.passage[1] + L.passage[-1] + L.cross
        for r in L.rooms + L.stairs + L.airlocks + L.vestibules:
            self.wire_room(d, L, r, corridors)
        for h in L.halls:
            for i in h["spans_decks"]:
                dd = self.deck[i]
                LL = self.L.get(i)
                if LL is None:
                    continue
                for c in LL.spine + LL.passage[1] + LL.passage[-1]:
                    if shared_wall(h, c):
                        self.door_between(h, c, deck=dd, width=3.2, height=3.0)
        # ---- the pressure bulkheads across every lane at each section boundary
        present = {s[0] for s in self.sec_ranges(d)}
        for (la, xfa, xaa), (lb, xfb, xab) in zip(self.sections, self.sections[1:]):
            if la not in present or lb not in present:
                continue
            xb = xaa                                              # the boundary: the aft end of the fore section, the fore end of the aft one
            for lane, tag in ((L.spine, "SP0"), (L.passage[1], "SP1"), (L.passage[-1], "SP-1")):
                fore = next((c for c in lane if c["section"] == la and abs(c["bounds"][0] - (xb + 0.2)) < 0.05), None)
                aft = next((c for c in lane if c["section"] == lb and abs(c["bounds"][2] - (xb - 0.2)) < 0.05), None)
                if fore and aft:
                    y = 0.5 * (fore["bounds"][1] + fore["bounds"][3])
                    self.door(fore, aft, xb, y, 0.0, kind="blast", width=BLAST_W, height=BLAST_H, boundary=[lb, la], extra={"passage": tag})

    def wire_room(self, d, L, r: dict, corridors):
        x0, y0, x1, y1 = r["bounds"]
        cx = 0.5 * (x0 + x1)
        row = r.get("_row")
        side = r.get("_side", 0)
        kind = r["kind"]
        adj = [c for c in corridors if shared_wall(r, c)]
        spine = [c for c in adj if c.get("role") == "spine"]
        pas = [c for c in adj if c.get("role") == "passage"]
        cross = [c for c in adj if c.get("role") == "cross"]
        if kind == "airlock":
            ves = [v for v in L.vestibules if shared_wall(r, v)]
            tgts = ves[:1] or pas[:1]
            doors = [self.door_between(r, t, deck=d, extra={"airlock": True}) for t in tgts]
        elif kind == "vestibule":
            doors = [self.door_between(r, t, deck=d) for t in pas[:1]]
        elif row in ("IP", "IS"):
            first = spine or cross or pas
            doors = [self.door_between(r, t, prefer=cx, deck=d) for t in first[:1]]
            if pas and first is not pas and (x1 - x0) >= 14.0 and kind != "stairs":
                doors.append(self.door_between(r, pas[0], prefer=cx, deck=d))
        else:
            first = pas or cross or spine
            doors = [self.door_between(r, t, prefer=cx, deck=d) for t in first[:1]]
        if not any(doors):
            self.notes.append(f"room {r['id']} ({r['kind']}) has no door")

    # --------------------------------------------------------------------------------------------------------------- the chains of the walk graph
    def finish_graph(self):
        """Along every corridor the nodes (doors, junctions, ends) in a chain; in every room a hub that its door nodes lead to."""
        for c in self.comps:
            nodes = self.comp_nodes[c["id"]]
            x0, y0, x1, y1 = c["bounds"]
            if c["kind"] in ("corridor",):
                along_x = (x1 - x0) >= (y1 - y0)
                cy = 0.5 * (y0 + y1)
                cx = 0.5 * (x0 + x1)
                have = {round(n[1 if along_x else 2], 1) for n in nodes}
                ends = ((x0 + 0.4, cy), (x1 - 0.4, cy)) if along_x else ((cx, y0 + 0.4), (cx, y1 - 0.4))
                for ex, ey in ends:
                    key = round(ex if along_x else ey, 1)
                    if not any(abs(k - key) < 0.9 for k in have):
                        self.node(c, ex, ey, "corridor", "e")
                        have.add(key)
                nodes = sorted(self.comp_nodes[c["id"]], key=lambda n: n[1] if along_x else n[2])
                for (na, xa, ya, za), (nb, xb, yb, zb) in zip(nodes, nodes[1:]):
                    ln = math.hypot(xb - xa, yb - ya)
                    if ln > 0.05:
                        self.edge(na, nb, ln, "walk", w=3.1 if c.get("role") == "spine" else 2.4)
            elif c["kind"] == "stairs":
                hub = self.stair_node(c)
                for nid, nx, ny, nz in list(self.comp_nodes[c["id"]]):
                    if nid != hub:
                        self.edge(nid, hub, max(0.5, math.hypot(nx - 0.5 * (x0 + x1), ny - 0.5 * (y0 + y1))), "walk")
            else:
                hx, hy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
                hz = c["z"][0]
                hub = self.node(c, hx, hy, "room", "hub", z=hz)
                for nid, nx, ny, nz in list(self.comp_nodes[c["id"]]):
                    if nid != hub:
                        self.edge(nid, hub, max(0.5, math.sqrt((nx - hx) ** 2 + (ny - hy) ** 2 + (nz - hz) ** 2)), "walk")
