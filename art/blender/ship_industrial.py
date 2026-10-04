"""ASN Aquila interior kit (ARTE-INTERNI-2): the connective tissue of the working rooms. The machines of the plants, shops and technical spaces stood alone on a bare deck, three metres apart;
this joins them: pipes routed round the room between two machines with their service colours, flanges, clamps, valves with hand wheels and pressure gauges; grated walkways with rails, toe plates and
ladders; floor trunking over the cables; painted lanes, drains and warning plates; a hose reel and an eyewash. Every function builds into the room's own SParts in the ROOM frame (x along the
corridor, y into the room, z up; the caller is the room builder, not `place`), in the soft group where it can (no bevel: a pipe is round, not chamfered), so that a run of ten metres costs a few
hundred triangles.

  pipe_route(b, pts, r, service)        a pipe through the points (any directions), elbows, flanges at the ends, colour bands, clamps to the floor / a wall / the deck above, valves and gauges where asked
  valve(b, p, axis, r, kind)            a gate valve with its hand wheel (a globe valve for kind="globe"), on a pipe along `axis` at p
  gauge(b, p, facing, r)                a pressure gauge: a bezel, a dial, a needle
  walkway(b, x0, x1, y0, y1, z, ...)    a raised platform of diamond plate on posts, rails on the open sides, toe plates, a ladder
  trunking(b, p0, p1, w)                a floor cable cover with ramped ends
  lane(b, x0, x1, y0, y1, w, cell)      a lit painted rectangle on the floor (the edge of an aisle, a keep-clear zone)
  drain(b, x, y)                        a floor drain with its grate
  hose_reel / eyewash                   wall equipment of a working room (a wall piece: origin on the wall's face, facing +x, placed with ship_rooms.place like the pieces of ship_walls)
"""
from __future__ import annotations

import math

from mathutils import Vector

from ship_lib import LAMP_DIM, PERF, RUBBER, STEEL, STRUCT, SWATCH, TREAD, TRIM, SParts

SERVICE = {"water": "blue", "air": "grey5", "fuel": "orange", "coolant": "green", "steam": "red", "waste": "tan", "power": "yellow", "vacuum": "purple", "fire": "red"}


def _v(p) -> Vector:
    return p if isinstance(p, Vector) else Vector(p)


# ---------------------------------------------------------------------------------------------------------------------------------------------------- pipes
def pipe_route(b: SParts, pts, r: float = 0.05, service: str | None = None, mat: str = TRIM, support: tuple | None = None, flanges: bool = True, clamp: float = 1.8, valves=(),
               gauges=(), band_every: float = 3.0) -> None:
    """A pipe of radius `r` through the room-frame points `pts`. Round elbows, flanges at the two ends, a colour band every `band_every` m in the service's colour (SERVICE), clamps every `clamp` m:
    `support` = ("floor",) a post to the deck, ("ceil", z) a rod to the deck above, ("wall", "x"|"y", coordinate) an arm to the wall. `valves` = [(distance along the route, kind)];
    `gauges` = [(distance, facing)] a pressure gauge on a short stub."""
    P = [_v(p) for p in pts]
    seg = max(8, min(12, int(r * 220)))
    k_clamp = r * 1.25
    total = 0.0
    cuts = []
    for a, c in zip(P[:-1], P[1:]):
        length = (c - a).length
        cuts.append((total, total + length, a, c))
        total += length
    for k, (s0, s1, a, c) in enumerate(cuts):
        b.soft.cyl(a, c, r, mat, seg=seg, caps=False)
        d = (c - a).normalized()
        if flanges and (k == 0 or k == len(cuts) - 1):
            e, n = (a, d) if k == 0 else (c, -d)
            b.soft.cyl(e, e + n * 0.035, r * 1.55, mat, seg=seg)
        if k > 0:
            b.soft.sphere(a, r * 1.04, mat, seg=seg, rings=6)
        if service:                                                                               # bands in the service colour
            col = SERVICE.get(service, service)
            n_b = max(1, int((s1 - s0) / band_every))
            for j in range(n_b):
                t = (j + 0.5) * (s1 - s0) / n_b
                q = a + d * t
                b.soft.paint(b.soft.cyl(q - d * 0.05, q + d * 0.05, r * 1.1, SWATCH, seg=seg), col)
        if support:                                                                               # clamps and their posts, rods or arms
            n_c = max(1, int((s1 - s0) / clamp))
            for j in range(n_c):
                q = a + d * ((j + 0.5) * (s1 - s0) / n_c)
                b.fine.box(q - Vector((k_clamp,) * 3), q + Vector((k_clamp,) * 3), STRUCT)
                if support[0] == "floor" and q.z > 0.12:
                    b.fine.box((q.x - 0.03, q.y - 0.03, 0.0), (q.x + 0.03, q.y + 0.03, q.z - k_clamp), STRUCT)
                elif support[0] == "ceil" and support[1] - q.z > 0.12:
                    b.fine.cyl((q.x, q.y, q.z + k_clamp), (q.x, q.y, support[1]), 0.012, STRUCT, seg=6)
                elif support[0] == "wall":
                    axis, coord = support[1], support[2]
                    if axis == "x" and abs(q.x - coord) > 0.1:
                        b.fine.cyl((q.x, q.y, q.z), (coord, q.y, q.z), 0.015, STRUCT, seg=6)
                    elif axis == "y" and abs(q.y - coord) > 0.1:
                        b.fine.cyl((q.x, q.y, q.z), (q.x, coord, q.z), 0.015, STRUCT, seg=6)

    def at(dist: float):
        dist = max(0.0, min(total, dist))
        for (s0, s1, a, c) in cuts:
            if dist <= s1 + 1e-6:
                return a + (c - a).normalized() * (dist - s0), (c - a).normalized()
        a, c = cuts[-1][2], cuts[-1][3]
        return c, (c - a).normalized()
    for dist, kind in valves:
        q, d = at(dist)
        valve(b, q, d, r, kind)
    for dist, facing in gauges:
        q, d = at(dist)
        f = _v(facing).normalized()
        b.soft.cyl(q, q + f * (r + 0.07), 0.012, STEEL, seg=6, caps=False)
        gauge(b, q + f * (r + 0.07), f, 0.06)


def valve(b: SParts, p, axis, r: float = 0.05, kind: str = "gate") -> None:
    """A valve on a pipe along `axis` at p: a fat body with flanges and a stem up (across the pipe, vertical unless the pipe is) ending in a hand wheel painted red; a globe valve has a
    round body."""
    p, ax = _v(p), _v(axis).normalized()
    up = Vector((0.0, 0.0, 1.0)) if abs(ax.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    if kind == "globe":
        b.soft.sphere(p, r * 1.9, STEEL, seg=12, rings=8)
    else:
        b.soft.cyl(p - ax * 0.12, p + ax * 0.12, r * 1.6, STEEL, seg=10)
    for s in (-1, 1):
        b.soft.cyl(p + ax * 0.12 * s, p + ax * 0.15 * s, r * 1.8, STEEL, seg=10)
    top = p + up * (r * 1.8 + 0.2)
    b.soft.cyl(p + up * r, top, 0.014, STEEL, seg=6, caps=False)
    side = ax.cross(up).normalized()
    b.soft.paint(b.soft.cyl(top, top + up * 0.018, 0.1, SWATCH, seg=14), "red")                      # the hand wheel: a disc and two spokes across it
    for sgn in (-1, 1):
        b.soft.paint(b.soft.cyl(top - side * 0.1 * sgn, top + side * 0.1 * sgn, 0.008, SWATCH, seg=5, caps=False), "red")


def gauge(b: SParts, p, facing, r: float = 0.07) -> None:
    """A pressure gauge on a stub: a steel bezel, a pale dial with a needle, looking along `facing` from p."""
    p, f = _v(p), _v(facing).normalized()
    b.soft.cyl(p, p + f * 0.04, r, STEEL, seg=14)
    b.soft.paint(b.soft.cyl(p + f * 0.04, p + f * 0.044, r * 0.86, SWATCH, seg=14), "paper")
    up = Vector((0.0, 0.0, 1.0)) if abs(f.z) < 0.9 else Vector((1.0, 0.0, 0.0))
    side = f.cross(up).normalized()
    n0 = p + f * 0.047
    n1 = n0 + (up * math.cos(0.7) + side * math.sin(0.7)) * r * 0.7
    b.soft.paint(b.soft.cyl(n0, n1, 0.004, SWATCH, seg=4, caps=False), "charcoal")


# ---------------------------------------------------------------------------------------------------------------------------------------------------- walkways
def walkway(b: SParts, x0: float, x1: float, y0: float, y1: float, z: float, rails=("x0", "x1", "y0", "y1"), ladder: tuple | None = None, post: float = 1.8) -> None:
    """A raised walkway: a deck of diamond plate on a frame, posts every `post` m to the floor, a double rail and a toe plate on each open side in `rails` (x0 | x1 | y0 | y1), and a
    ladder (x, y, side) = a vertical ladder at that point on the edge of the platform, `side` the way it faces (x0 | x1 | y0 | y1)."""
    b.body.box((x0, y0, z - 0.06), (x1, y1, z - 0.02), STRUCT)
    b.soft.box((x0 + 0.01, y0 + 0.01, z - 0.02), (x1 - 0.01, y1 - 0.01, z), TREAD)
    b.body.box((x0, y0, z - 0.12), (x1, y0 + 0.05, z - 0.06), TRIM)
    b.body.box((x0, y1 - 0.05, z - 0.12), (x1, y1, z - 0.06), TRIM)
    nx = max(2, int((x1 - x0) / post) + 1)
    for i in range(nx):                                                                           # the legs, along the two long edges
        x = x0 + 0.05 + i * (x1 - x0 - 0.1) / (nx - 1)
        for y in (y0 + 0.05, y1 - 0.05):
            b.soft.cyl((x, y, 0.0), (x, y, z - 0.12), 0.03, STRUCT, seg=8, caps=False)
    ins = 0.03
    sides = {"y0": ((x0 + ins, y0 + ins), (x1 - ins, y0 + ins)), "y1": ((x0 + ins, y1 - ins), (x1 - ins, y1 - ins)),
             "x0": ((x0 + ins, y0 + ins), (x0 + ins, y1 - ins)), "x1": ((x1 - ins, y0 + ins), (x1 - ins, y1 - ins))}
    for name in rails:
        (ax, ay), (cx, cy) = sides[name]
        for h in (0.55, 1.05):
            b.soft.cyl((ax, ay, z + h), (cx, cy, z + h), 0.02, TRIM, seg=8, caps=False)
        b.soft.box((min(ax, cx) - 0.01, min(ay, cy) - 0.01, z), (max(ax, cx) + 0.01, max(ay, cy) + 0.01, z + 0.1), TRIM)                # the toe plate
        n = max(2, int(math.hypot(cx - ax, cy - ay) / 1.2) + 1)
        for k in range(n):                                                                        # the rail posts
            t = k / (n - 1)
            px, py = ax + (cx - ax) * t, ay + (cy - ay) * t
            b.soft.cyl((px, py, z), (px, py, z + 1.05), 0.02, TRIM, seg=6, caps=False)
    if ladder:
        lx, ly, side = ladder
        dx, dy = {"x0": (-1, 0), "x1": (1, 0), "y0": (0, -1), "y1": (0, 1)}[side]
        qx, qy = -dy, dx                                                                          # across the ladder
        for s in (-1, 1):
            b.soft.cyl((lx + dx * 0.12 + qx * 0.2 * s, ly + dy * 0.12 + qy * 0.2 * s, 0.0), (lx + dx * 0.12 + qx * 0.2 * s, ly + dy * 0.12 + qy * 0.2 * s, z + 0.9), 0.02, TRIM, seg=6, caps=False)
        for k in range(int(z / 0.3)):
            zz = 0.25 + k * 0.3
            b.soft.cyl((lx + dx * 0.12 - qx * 0.2, ly + dy * 0.12 - qy * 0.2, zz), (lx + dx * 0.12 + qx * 0.2, ly + dy * 0.12 + qy * 0.2, zz), 0.012, TRIM, seg=5, caps=False)


# ---------------------------------------------------------------------------------------------------------------------------------------------------- floor
def trunking(b: SParts, p0, p1, w: float = 0.3) -> None:
    """A floor cable cover between two points (axis-aligned): a rubber ramp up to a flat top with yellow edges (the covers a trolley can cross)."""
    (x0, y0), (x1, y1) = (p0[0], p0[1]), (p1[0], p1[1])
    along_x = abs(x1 - x0) >= abs(y1 - y0)
    lo, hi = ((min(x0, x1), y0 - w / 2), (max(x0, x1), y0 + w / 2)) if along_x else ((x0 - w / 2, min(y0, y1)), (x0 + w / 2, max(y0, y1)))
    b.body.box((lo[0], lo[1], 0.0), (hi[0], hi[1], 0.045), RUBBER)
    b.soft.paint(b.soft.box((lo[0] + 0.02, lo[1] + 0.02, 0.045), (hi[0] - 0.02, hi[1] - 0.02, 0.05), SWATCH), "grey2")
    if along_x:
        edges = ((lo[0], lo[1], hi[0], lo[1] + 0.02), (lo[0], hi[1] - 0.02, hi[0], hi[1]))
    else:
        edges = ((lo[0], lo[1], lo[0] + 0.02, hi[1]), (hi[0] - 0.02, lo[1], hi[0], hi[1]))
    for (ex0, ey0, ex1, ey1) in edges:
        b.soft.paint(b.soft.box((ex0, ey0, 0.0455), (ex1, ey1, 0.05), SWATCH), "yellow")


def lane(b: SParts, x0: float, x1: float, y0: float, y1: float, w: float = 0.08, cell: str = "amber_dim", dash: float = 0.0) -> None:
    """A painted rectangle on the floor read by its own faint glow (the edge of an aisle, a keep-clear zone round a machine); `dash` > 0 breaks it into dashes of that length."""
    def line(ax: float, ay: float, bx: float, by: float) -> None:
        horizontal = ay == by
        length = abs(bx - ax) if horizontal else abs(by - ay)
        n = 1 if dash <= 0 else max(1, int(length / (dash * 2)))
        for k in range(n):
            t0, t1 = (0.0, 1.0) if dash <= 0 else ((k * 2 * dash) / length, (k * 2 * dash + dash) / length)
            sx, sy = ax + (bx - ax) * t0, ay + (by - ay) * t0
            ex, ey = ax + (bx - ax) * t1, ay + (by - ay) * t1
            b.emit.lamp_box((min(sx, ex), min(sy, ey), 0.0), (max(sx, ex) + (0.0 if horizontal else w), max(sy, ey) + (w if horizontal else 0.0), 0.004), cell, LAMP_DIM)
    line(x0, y0, x1, y0)
    line(x0, y1 - w, x1, y1 - w)
    line(x0, y0, x0, y1)
    line(x1 - w, y0, x1 - w, y1)


def drain(b: SParts, x: float, y: float, w: float = 0.5) -> None:
    """A floor drain: a steel frame flush with the deck, a slotted grate."""
    b.body.box((x - w / 2, y - w / 2, 0.0), (x + w / 2, y + w / 2, 0.012), STRUCT)
    b.soft.box((x - w / 2 + 0.03, y - w / 2 + 0.03, 0.012), (x + w / 2 - 0.03, y + w / 2 - 0.03, 0.016), PERF)


# ---------------------------------------------------------------------------------------------------------------------------------------------------- wall equipment
def hose_reel(b: SParts, r: float = 0.32, service: str = "water") -> None:
    """A hose reel on the wall (origin on the wall's face, z = 0 at the floor, the piece facing +x): a drum on a steel frame wound with hose in the service's colour, a nozzle on a hook, the
    supply pipe up the wall."""
    zc = 1.05
    col = SERVICE.get(service, service)
    b.body.box((0.0, -r - 0.06, zc - r - 0.06), (0.05, r + 0.06, zc + r + 0.06), STRUCT)
    b.soft.paint(b.soft.cyl((0.05, 0.0, zc), (0.2, 0.0, zc), r, SWATCH, seg=20), col)
    b.soft.cyl((0.05, 0.0, zc), (0.2, 0.0, zc), r * 0.35, STEEL, seg=12)
    b.soft.cyl((0.2, 0.0, zc), (0.26, 0.0, zc), 0.04, STEEL, seg=8)
    for sy in (r * 0.6, -r * 0.6 - 0.04):
        b.fine.box((0.05, sy, zc - r - 0.06), (0.2, sy + 0.04, zc + r + 0.06), TRIM)
    b.soft.cyl((0.0, 0.0, zc + r + 0.06), (0.0, 0.0, 2.3), 0.025, STEEL, seg=8, caps=False)
    b.soft.paint(b.soft.cyl((0.02, r + 0.1, zc - 0.1), (0.16, r + 0.1, zc - 0.1), 0.025, SWATCH, seg=8), "brass")


def eyewash(b: SParts) -> None:
    """An emergency eyewash and shower station on the wall (origin on the wall's face, facing +x): a green plate with two bowls and a pull handle, the shower head above on its pipe."""
    b.body.box((0.0, -0.22, 0.95), (0.04, 0.22, 1.5), STRUCT)
    b.soft.paint(b.soft.box((0.04, -0.2, 1.0), (0.045, 0.2, 1.45), SWATCH), "green")
    for sy in (-0.1, 0.1):
        b.soft.cyl((0.05, sy, 1.1), (0.2, sy, 1.18), 0.07, STEEL, seg=12)
    b.soft.paint(b.soft.box((0.05, -0.02, 1.38), (0.08, 0.02, 1.42), SWATCH), "white")
    b.soft.cyl((0.0, 0.0, 1.5), (0.0, 0.0, 2.35), 0.02, STEEL, seg=6, caps=False)
    b.soft.cyl((0.0, 0.0, 2.35), (0.3, 0.0, 2.35), 0.02, STEEL, seg=6, caps=False)
    b.soft.cyl((0.3, 0.0, 2.35), (0.3, 0.0, 2.3), 0.12, STEEL, seg=12, r2=0.04)
    b.emit.label((0.047, 0.0, 1.33), 0.32, 0.08, (1, 0, 0), "icon_aid")
