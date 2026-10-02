"""ASN Aquila bridge v3: the shared context of the bridge (Ctx: the layout from data/ship/aquila_bridge.json, the walls, the plan
helpers). The deck lives in bridge3_floor.py, the walls, ceiling, window and rails in their own modules; builders return Blender
objects, origin = bridge origin."""
from __future__ import annotations

import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Rz, polar, lerp  # noqa: E402


# --------------------------------------------------------------------------------------------------------------- context
class Wall:
    """A side wall in layout coordinates: p0 (aft end) -> p1 (front end); s along, t outward (0 = inner face), z up."""

    def __init__(self, p0, p1, side: int, n_out=None) -> None:
        self.p0 = Vector((p0[0], p0[1]))
        self.p1 = Vector((p1[0], p1[1]))
        d = self.p1 - self.p0
        self.L = d.length
        self.dir = d / self.L
        # outward normal: away from the centre line (or given: the back wall)
        n = Vector((-self.dir.y, self.dir.x))
        if n_out is not None:
            self.n_out = Vector(n_out).normalized()
        else:
            self.n_out = n if n.y * side > 0 else -n
        self.side = side
        self.yaw = math.degrees(math.atan2(self.dir.y, self.dir.x))

    def pt(self, s: float, t: float = 0.0, z: float = 0.0):
        p = self.p0 + self.dir * s + self.n_out * t
        return (p.x, p.y, z)

    def xy(self, s: float, t: float = 0.0):
        p = self.p0 + self.dir * s + self.n_out * t
        return (p.x, p.y)

    def facing_in(self):
        return (-self.n_out.x, -self.n_out.y, 0.0)

    def matrix(self) -> Matrix:
        """Local frame (s along, t outward, z up) in layout coordinates; a reflection on the port wall (text and screens are
        oriented in Blender space by FB, so this is safe)."""
        m = Matrix.Identity(4)
        m[0][0], m[1][0] = self.dir.x, self.dir.y
        m[0][1], m[1][1] = self.n_out.x, self.n_out.y
        m[0][3], m[1][3] = self.p0.x, self.p0.y
        return m

    def s_of(self, x: float, y: float) -> float:
        return (Vector((x, y)) - self.p0).dot(self.dir)

    def t_of(self, x: float, y: float) -> float:
        return (Vector((x, y)) - self.p0).dot(self.n_out)


class Ctx:
    def __init__(self, D: dict) -> None:
        self.D = D
        lv = D["levels"]
        self.UPPER, self.WELL, self.DAIS = lv["upper"], lv["well"], lv["dais"]
        self.CEIL = D["ceiling"]["height"]
        W = D["window"]
        self.R = W["radius"]
        self.ANGD = list(W["angles_deg"])
        self.ANG = [math.radians(a) for a in self.ANGD]
        self.SILL, self.HEAD = W["sill"], W["head"]
        self.BACK_X, self.BACK_HW = D["walls"]["back_x"], D["walls"]["back_half_width"]
        self.WELL_X, self.WELL_HW = D["well"]["edge_x"], D["well"]["half_width"]
        self.STAIR_Y = D["well"]["stairs_y"]
        self.STAIR_W = D["well"]["stair_width"]
        self.FLOOR_BOTTOM = -0.9
        self.front_p = self.arc(self.ANG[0])
        self.front_s = self.arc(self.ANG[-1])
        self.walls = {1: Wall((self.BACK_X, self.BACK_HW), (self.front_s[0], abs(self.front_s[1])), 1),
                      -1: Wall((self.BACK_X, -self.BACK_HW), (self.front_p[0], -abs(self.front_p[1])), -1)}
        a20, a40 = self.arc(self.ANG[4]), self.arc(self.ANG[5])
        t = (self.WELL_HW - a20[1]) / (a40[1] - a20[1])
        self.xe = a20[0] + t * (a40[0] - a20[0])            # where the well edge line meets the window facet
        self.dais_hx, self.dais_hy = D["dais"]["half_x"], D["dais"]["half_y"]
        ht = D["holo_table"]
        self.table = (ht["pos"][0], ht["pos"][1])
        self.table_r = ht["radius"]
        self.table_h = ht["height"]

    def arc(self, a: float, r: float | None = None):
        r = self.R if r is None else r
        return (r * math.cos(a), r * math.sin(a))

    def side_wall_y(self, x: float, side: int) -> float:
        w = self.walls[side]
        s = (x - w.p0.x) / w.dir.x
        return (w.p0 + w.dir * s).y

    def level_z(self, name: str) -> float:
        return self.D["levels"][name]


# -------------------------------------------------------------------------------------------------------------- helpers
def inside_poly(poly, p, margin: float = 0.0) -> bool:
    """Point-in-convex-polygon test (either winding), shrunk by `margin` metres."""
    n = len(poly)
    sign = 0
    for i in range(n):
        (ax, ay), (bx, by) = poly[i], poly[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        ln = math.hypot(ex, ey)
        c = (ex * (p[1] - ay) - ey * (p[0] - ax)) / ln
        if abs(c) < 1e-12:
            continue
        s = 1 if c > 0 else -1
        if sign == 0:
            sign = s
        if s != sign or abs(c) < margin:
            return False
    return True


def ellipse_poly(cx: float, cy: float, hx: float, hy: float, n: int = 32, grow: float = 0.0):
    return [(cx + (hx + grow) * math.cos(2 * math.pi * k / n), cy + (hy + grow) * math.sin(2 * math.pi * k / n)) for k in range(n)]


def line_lamp(fb: FB, p0, p1, z: float, w: float, h: float, cell: str, mat: str = L.LAMP_DIM, frame_w: float = 0.0, frame_h: float = 0.004):
    """A thin lamp strip from p0 to p1 (layout xy) lying on a surface at height z: an inlaid light channel, optionally with a
    dark frame around it."""
    (x0, y0), (x1, y1) = p0, p1
    ln = math.hypot(x1 - x0, y1 - y0)
    if ln < 1e-4:
        return
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rot = Rz(ang)
    if frame_w > 0:
        fb.cbox((cx, cy, z + frame_h / 2), (ln + frame_w, w + frame_w, frame_h), L.STRUCT, rot)
    fb.lamp_cbox((cx, cy, z + frame_h + h / 2), (ln, w, h), cell, mat, rot)


def polyline_lamp(fb: FB, pts, z, w, h, cell, mat=L.LAMP_DIM, frame_w=0.0):
    for a, b in zip(pts[:-1], pts[1:]):
        line_lamp(fb, a, b, z, w, h, cell, mat, frame_w)


def arc_pts(cx, cy, r, a0, a1, n=None):
    n = n or max(2, int(abs(a1 - a0) / 5))
    return [polar(cx, cy, r, lerp(a0, a1, k / n)) for k in range(n + 1)]


def plate_uv(fb: FB, faces, rng: random.Random, scale: float = 1.0) -> None:
    """Per-plate UV offsets so the fine grain of the deck never lines up from plate to plate (box projection, metres)."""
    ou, ov = rng.random() * 8.0, rng.random() * 8.0
    for f in faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        f[fb.cu] = 1
        for loop in f.loops:
            co = loop.vert.co
            u, v = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            loop[fb.uv].uv = (u / scale + ou, v / scale + ov)



def poly_area(poly) -> float:
    a = 0.0
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2


def clip_convex(subject, clip, margin: float = 0.0):
    """Sutherland-Hodgman: `subject` polygon clipped by the convex polygon `clip` shrunk by `margin` (any winding)."""
    n = len(clip)
    area2 = sum(clip[i][0] * clip[(i + 1) % n][1] - clip[(i + 1) % n][0] * clip[i][1] for i in range(n))
    sgn = 1.0 if area2 > 0 else -1.0          # counter-clockwise polygons keep the left side
    out = list(subject)
    for i in range(n):
        (ax, ay), (bx, by) = clip[i], clip[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        ln = math.hypot(ex, ey)
        nx, ny = -ey / ln * sgn, ex / ln * sgn          # inward normal
        ax2, ay2 = ax + nx * margin, ay + ny * margin

        def d(p):
            return (p[0] - ax2) * nx + (p[1] - ay2) * ny

        if not out:
            break
        inp, out = out, []
        for k in range(len(inp)):
            p, q = inp[k], inp[(k + 1) % len(inp)]
            dp, dq = d(p), d(q)
            if dp >= 0:
                out.append(p)
            if (dp >= 0) != (dq >= 0):
                t = dp / (dp - dq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out
