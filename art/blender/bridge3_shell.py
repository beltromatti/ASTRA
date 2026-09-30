"""ASN Aquila bridge v3: the shell (deck, walls, ceiling, window, rails, viewscreen frame, master display).
All positions come from data/ship/aquila_bridge.json through Ctx; builders return Blender objects, origin = bridge origin."""
from __future__ import annotations

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Parts, T, Rz, Ry, Rx, frame, polar, lerp  # noqa: E402


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


# ================================================================================================================== deck
def build_deck(c: Ctx, name: str = "SM_BRG3_Deck"):
    b = Parts(bevel=0.006, fine_bevel=0.003)
    fb, em = b.body, b.emit
    rng = random.Random(3)
    yw = c.side_wall_y(c.WELL_X, 1)
    UP, WL, DS = c.UPPER, c.WELL, c.DAIS

    # ---- base slabs (the structural deck under the plates)
    upper = [(c.BACK_X, -c.BACK_HW), (c.WELL_X, -yw), (c.WELL_X, yw), (c.BACK_X, c.BACK_HW)]
    wings = []
    for s in (1, -1):
        wings.append([(c.WELL_X, s * c.WELL_HW), (c.xe, s * c.WELL_HW), c.arc(c.ANG[5] if s > 0 else -c.ANG[5]),
                      c.arc(c.ANG[-1] if s > 0 else -c.ANG[-1]), (c.WELL_X, s * yw)])
    a_m20, a_0, a_20 = c.arc(c.ANG[2]), c.arc(c.ANG[3]), c.arc(c.ANG[4])
    well = [(c.WELL_X, -c.WELL_HW), (c.xe, -c.WELL_HW), a_m20, a_0, a_20, (c.xe, c.WELL_HW), (c.WELL_X, c.WELL_HW)]
    for poly, z in [(upper, UP)] + [(w, UP) for w in wings] + [(well, WL)]:
        fb.prism(poly, c.FLOOR_BOTTOM, z - 0.012, L.STRUCT)

    # ---- plating: running-bond plates 1.8 x 0.9 m, per-plate UV offsets, clipped to each floor polygon
    dais_poly = ellipse_poly(0.0, 0.0, c.dais_hx, c.dais_hy, 40, grow=0.16)
    stair_boxes = [(c.WELL_X - 0.05, y - c.STAIR_W / 2 - 0.05, c.WELL_X + 0.85, y + c.STAIR_W / 2 + 0.05) for y in c.STAIR_Y]
    tx, ty = c.table
    hatches = []

    def in_stairs(cx, cy):
        return any(b0[0] - 0.2 <= cx <= b0[2] + 0.2 and b0[1] - 0.2 <= cy <= b0[3] + 0.2 for b0 in stair_boxes)

    def plates(poly, z, pw=1.8, ph=0.9, gap=0.016, skip=None):
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        j0 = int(math.floor(min(ys) / ph)) - 1
        j1 = int(math.ceil(max(ys) / ph)) + 1
        for j in range(j0, j1 + 1):
            off = (pw / 2) if j % 2 else 0.0
            i0 = int(math.floor((min(xs) - off) / pw)) - 1
            i1 = int(math.ceil((max(xs) - off) / pw)) + 1
            for i in range(i0, i1 + 1):
                x0, x1 = i * pw + off + gap / 2, (i + 1) * pw + off - gap / 2
                y0, y1 = j * ph + gap / 2, (j + 1) * ph - gap / 2
                rect = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
                clipped = clip_convex(rect, poly, 0.03)
                if len(clipped) < 3 or poly_area(clipped) < 0.02:
                    continue
                if skip and skip(clipped):
                    continue
                faces = fb.prism(clipped, z - 0.012, z, L.DECK)
                plate_uv(fb, faces, rng, 1.0)
                if rng.random() < 0.06 and poly_area(clipped) > 1.5:
                    cx = sum(q[0] for q in clipped) / len(clipped)
                    cy = sum(q[1] for q in clipped) / len(clipped)
                    hatches.append((cx, cy, z))

    def skip_upper(clipped):
        # under the dais the plates would only be hidden
        return all(inside_poly(dais_poly, q, 0.0) for q in clipped)

    def skip_well(clipped):
        return in_stairs_poly(clipped) or all(math.hypot(q[0] - tx, q[1] - ty) < c.table_r - 0.2 for q in clipped)

    def in_stairs_poly(clipped):
        return any(all(b0[0] <= q[0] <= b0[2] and b0[1] <= q[1] <= b0[3] for q in clipped) for b0 in stair_boxes)

    plates(upper, UP, skip=skip_upper)
    for w in wings:
        plates(w, UP, skip=None)
    plates(well, WL, skip=skip_well)

    # hatch plates: a groove, two flush pull rings
    for (hx, hy, hz) in hatches[:10]:
        fb.box((hx - 0.36, hy - 0.26, hz), (hx + 0.36, hy + 0.26, hz + 0.006), L.TRIM)
        fb.box((hx - 0.33, hy - 0.23, hz + 0.006), (hx + 0.33, hy + 0.23, hz + 0.01), L.DECK)
        for sx in (-0.2, 0.2):
            fb.cyl((hx + sx, hy, hz + 0.012), (hx + sx, hy, hz + 0.016), 0.035, L.TRIM, seg=14)
        for sx in (-0.3, 0.3):
            for sy in (-0.2, 0.2):
                fb.cyl((hx + sx, hy + sy, hz + 0.01), (hx + sx, hy + sy, hz + 0.014), 0.008, L.TRIM, seg=8)

    # ---- the command dais: a raised platform with a lit lip
    fb.prism(ellipse_poly(0, 0, c.dais_hx, c.dais_hy, 40), UP - 0.05, DS - 0.03, L.STRUCT)
    fb.prism(ellipse_poly(0, 0, c.dais_hx - 0.02, c.dais_hy - 0.02, 40), DS - 0.03, DS, L.DECK)
    ring_in = ellipse_poly(0, 0, c.dais_hx - 0.02, c.dais_hy - 0.02, 40)
    ring_out = ellipse_poly(0, 0, c.dais_hx + 0.05, c.dais_hy + 0.05, 40)
    n = len(ring_in)
    for k in range(n):
        kk = (k + 1) % n
        fb.prism([ring_in[k], ring_out[k], ring_out[kk], ring_in[kk]], DS - 0.05, DS + 0.012, L.TRIM)
    for k in range(n):                                      # the lit line under the lip, in the command colour
        kk = (k + 1) % n
        a = ellipse_poly(0, 0, c.dais_hx + 0.052, c.dais_hy + 0.052, 40)
        a2 = ellipse_poly(0, 0, c.dais_hx + 0.075, c.dais_hy + 0.075, 40)
    # lamp ring around the dais foot as an arc-swept strip (elliptical: polyline of boxes)
    pts = ellipse_poly(0, 0, c.dais_hx + 0.06, c.dais_hy + 0.06, 40)
    for k in range(len(pts)):
        line_lamp(em, pts[k], pts[(k + 1) % len(pts)], UP + 0.012, 0.03, 0.006, "command", L.LAMP)
    # inlaid rings on the dais top
    for rx, ry in ((c.dais_hx - 0.22, c.dais_hy - 0.22), (c.dais_hx - 0.5, c.dais_hy - 0.5)):
        pts = ellipse_poly(0, 0, rx, ry, 48)
        for k in range(len(pts)):
            line_lamp(em, pts[k], pts[(k + 1) % len(pts)], DS, 0.014, 0.003, "command_dim", L.LAMP_DIM)

    # ---- stairs into the well (three drops of 0.2 m), nosings with guide lights, side skirts
    sw = c.STAIR_W
    for yc in c.STAIR_Y:
        for k, (x0, x1, ztop) in enumerate(((c.WELL_X, c.WELL_X + 0.35, WL + 0.4), (c.WELL_X + 0.35, c.WELL_X + 0.7, WL + 0.2))):
            fb.box((x0, yc - sw / 2, WL), (x1, yc + sw / 2, ztop), L.STRUCT)
            fb.box((x0 + 0.01, yc - sw / 2 + 0.03, ztop - 0.012), (x1 - 0.005, yc + sw / 2 - 0.03, ztop), L.DECK)
            fb.box((x0 - 0.005, yc - sw / 2, ztop - 0.04), (x0 + 0.05, yc + sw / 2, ztop + 0.004), L.TRIM)              # nosing
            em.lamp_box((x0 - 0.008, yc - sw / 2 + 0.06, ztop - 0.03), (x0 - 0.004, yc + sw / 2 - 0.06, ztop - 0.012), "guide", L.LAMP_DIM)
        for s in (-1, 1):
            fb.box((c.WELL_X - 0.02, yc + s * (sw / 2) - 0.02 + (0.0 if s < 0 else 0.0), WL), (c.WELL_X + 0.75, yc + s * (sw / 2) + 0.02, WL + 0.5), L.TRIM)
    # the well edge: nosing, lamp line (the safety-stripe decal is laid over it by place_signage)
    y0, y1 = -c.WELL_HW + sw, c.WELL_HW - sw
    fb.box((c.WELL_X - 0.05, y0, UP - 0.045), (c.WELL_X + 0.03, y1, UP + 0.004), L.TRIM)
    em.lamp_box((c.WELL_X + 0.028, y0 + 0.05, UP - 0.035), (c.WELL_X + 0.034, y1 - 0.05, UP - 0.02), "command", L.LAMP)
    # the wing edges
    for s in (1, -1):
        xa, xb = c.WELL_X + 0.7 + 0.05, c.xe - 0.05
        ya, yb = sorted((s * c.WELL_HW - 0.05, s * c.WELL_HW + 0.03))
        fb.box((xa, ya, UP - 0.045), (xb, yb, UP + 0.004), L.TRIM)

    # ---- inlaid light channels: two rings round the dais, the ship's axis, rings round the table, the guides from the stairs
    def run_lamps(pts, keep, z, cell, w=0.02):
        for p0, p1 in zip(pts, pts[1:] + pts[:1]):
            if keep(p0) and keep(p1):
                line_lamp(em, p0, p1, z, w, 0.004, cell, L.LAMP_DIM, frame_w=0.05)

    on_upper = lambda p: p[0] < c.WELL_X - 0.2 and abs(p[1]) < c.side_wall_y(p[0], 1) - 0.5
    for grow in (0.38, 0.9):
        run_lamps(ellipse_poly(0, 0, c.dais_hx + grow, c.dais_hy + grow, 120), on_upper, UP, "command_dim")
    # the axis: from the master display forward, chevrons pointing at the dais; another set leads from the table to the bow
    line_lamp(em, (-7.75, 0.0), (-4.05, 0.0), UP, 0.03, 0.004, "command", L.LAMP_DIM, frame_w=0.06)
    for k in range(6):
        x = -7.2 + k * 0.6
        for sd in (-1, 1):
            line_lamp(em, (x - 0.16, sd * 0.2), (x, 0.0), UP, 0.03, 0.004, "command", L.LAMP_DIM)
    line_lamp(em, (-2.05, 0.0), (-1.62, 0.0), UP, 0.03, 0.004, "security", L.LAMP_DIM, frame_w=0.06)
    for k in range(4):
        x = tx + c.table_r + 0.8 + k * 0.45
        for sd in (-1, 1):
            line_lamp(em, (x - 0.14, sd * 0.2), (x, 0.0), WL, 0.03, 0.004, "command", L.LAMP_DIM)
    for r in (c.table_r + 0.22, c.table_r + 0.55):
        polyline_lamp(em, arc_pts(tx, ty, r, 0, 360, 72), WL, 0.02, 0.004, "command_dim", L.LAMP_DIM, frame_w=0.05)
    for yc in c.STAIR_Y:
        pts = [(c.WELL_X + 0.8, yc), (c.WELL_X + 1.6, yc * 0.85), (tx - 1.4 * math.cos(math.radians(40)), math.copysign(1.0, yc) * 1.2)]
        polyline_lamp(em, pts, WL, 0.02, 0.004, "command_dim", L.LAMP_DIM, frame_w=0.05)
    # legends on the deck: MIND THE STEP at the top of each stair, COMMAND DAIS on the dais front (readable from the well)
    for yc in c.STAIR_Y:
        b.body.label((c.WELL_X - 0.42, yc, UP + 0.0025), 0.9, 0.1125, (0, 0, 1), "deck_step", up=(1, 0, 0))
    b.body.label((c.dais_hx - 0.36, 0.0, DS + 0.0025), 0.9, 0.1125, (0, 0, 1), "deck_dais", up=(-1, 0, 0))
    return b.build(name)
