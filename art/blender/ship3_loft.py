"""ASTRA ships v3 — lofted hulls, zones, armour plates and panels.

A `Loft` is a set of rings (the same number of points each) at stations along an axis. Each edge of the ring, followed along the
loft, is a `Zone`: a ruled surface P(a, w) with `a` the coordinate along the loft (metres along X for hulls) and `w` 0..1 across
the zone. Plates are slabs laid on a zone (rectangles, parallelograms or trapezoids in (a, w)): a wall going down into the skin,
a chamfer, a rim and a top face; the vertex data (wear, grime, tone) is written by construction, so edges chip and seams darken
exactly where the geometry says (ship3_geo). Panels are thin slabs laid on a plate's top: the seams between them are the panel
lines. Everything is numpy; a ship's plating is a few thousand calls.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

import ship3_geo as G

F32 = np.float32
I32 = np.int32


# ------------------------------------------------------------------------------------------------------------ sections
def chamfer_rect(w: float, h: float, c: float = 0.25, top: float = 1.0, bottom: float = 1.0) -> list[tuple[float, float]]:
    """An octagon (y, z) from a w x h rectangle (half sizes) with corners cut by c (fraction); top/bottom narrow the upper /
    lower halves. Counter-clockwise, starting bottom-left (the v2 section, kept for the Aquila's envelope)."""
    cw, ch = c * w, c * h
    return [(-w * bottom + cw, -h), (w * bottom - cw, -h), (w, -h + ch), (w, h - ch), (w * top - cw, h), (-w * top + cw, h),
            (-w, h - ch), (-w, -h + ch)]


def blade(w: float, h: float, skew: float = 0.0) -> list[tuple[float, float]]:
    """The Mandate's faceted armour section: a low keel and a ridge pushed to one side (8 points)."""
    return [(-0.4 * w, -h), (0.45 * w, -h), (w, -0.3 * h), (w * 0.92, 0.35 * h), (0.3 * w + skew * w, h),
            (-0.35 * w + skew * w, 0.9 * h), (-w * 0.95, 0.3 * h), (-w, -0.35 * h)]


def profile(t: float, pts) -> float:
    """Piecewise-linear profile: pts = [(t, value), ...] ascending."""
    if t <= pts[0][0]:
        return pts[0][1]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


# ---------------------------------------------------------------------------------------------------------------- loft
class Loft:
    """Rings (n points each) at stations `a` (metres along the loft axis, ascending). Section polygons are given as (y, z) lists
    and lifted to 3D at x = a for lofts along X; 3D rings can be given directly."""

    def __init__(self, a, rings):
        self.a = np.asarray(a, np.float64)
        self.R = np.asarray(rings, np.float64)                         # (ns, n, 3)
        self.ns, self.n, _ = self.R.shape
        self.C = self.R.mean(axis=1)                                   # ring centroids (ns, 3)

    @staticmethod
    def along_x(stations):
        """stations: [(x, [(y, z), ...], z_offset), ...] -> Loft with rings at x."""
        xs, rings = [], []
        for x, sec, zo in stations:
            sec = np.asarray(sec, np.float64)
            xs.append(x)
            rings.append(np.column_stack([np.full(len(sec), x), sec[:, 0], sec[:, 1] + zo]))
        return Loft(xs, rings)

    def with_stations(self, extra) -> "Loft":
        """A copy with stations inserted at the given a values (interpolated rings): the skin then breaks exactly there."""
        xs = list(self.a)
        for e in extra:
            if self.a[0] < e < self.a[-1] and np.min(np.abs(self.a - e)) > 1e-6 and e not in xs:
                xs.append(float(e))
        xs = np.array(sorted(xs))
        rings = np.stack([self.ring_at(x) for x in xs])
        return Loft(xs, rings)

    def _idx(self, a):
        a = np.asarray(a, np.float64)
        i = np.clip(np.searchsorted(self.a, a, side="right") - 1, 0, self.ns - 2)
        t = (a - self.a[i]) / (self.a[i + 1] - self.a[i])
        return i, t

    def ring_at(self, a: float) -> np.ndarray:
        i, t = self._idx(np.array([a]))
        return self.R[i[0]] * (1 - t[0]) + self.R[i[0] + 1] * t[0]

    def centroid_at(self, a):
        i, t = self._idx(a)
        return self.C[i] * (1 - t)[:, None] + self.C[i + 1] * t[:, None]

    def zone(self, k: int) -> "Zone":
        return Zone(self, k % self.n)

    def zones(self):
        return [Zone(self, k) for k in range(self.n)]


class Zone:
    """The ruled surface between ring vertices k and k+1 along the loft: P(a, w) = (1-w) R_k(a) + w R_k+1(a)."""

    def __init__(self, loft: Loft, k: int):
        self.loft = loft
        self.k = k
        self.k1 = (k + 1) % loft.n

    @property
    def a0(self):
        return float(self.loft.a[0])

    @property
    def a1(self):
        return float(self.loft.a[-1])

    def _rv(self, a):
        L = self.loft
        i, t = L._idx(a)
        t = t[:, None]
        return (L.R[i, self.k] * (1 - t) + L.R[i + 1, self.k] * t, L.R[i, self.k1] * (1 - t) + L.R[i + 1, self.k1] * t, i)

    def pts(self, a, w) -> np.ndarray:
        a = np.atleast_1d(np.asarray(a, np.float64))
        w = np.broadcast_to(np.asarray(w, np.float64), a.shape)[:, None]
        r0, r1, _ = self._rv(a)
        return r0 * (1 - w) + r1 * w

    def _normal_interval(self, i, w):
        L = self.loft
        da = L.a[i + 1] - L.a[i]
        d0 = (L.R[i + 1, self.k] - L.R[i, self.k]) / da[:, None]
        d1 = (L.R[i + 1, self.k1] - L.R[i, self.k1]) / da[:, None]
        dpda = d0 * (1 - w) + d1 * w
        # dP/dw at the middle of the interval (ruled: differs a little along the interval; the average is fine)
        dpdw = 0.5 * (L.R[i, self.k1] - L.R[i, self.k] + L.R[i + 1, self.k1] - L.R[i + 1, self.k])
        return dpda, dpdw

    def frame(self, a, w):
        """(P, N, T): points, unit outward normals and unit tangents along +a at (a, w) (arrays)."""
        L = self.loft
        a = np.atleast_1d(np.asarray(a, np.float64))
        w = np.broadcast_to(np.asarray(w, np.float64), a.shape)
        r0, r1, i = self._rv(a)
        wc = w[:, None]
        P = r0 * (1 - wc) + r1 * wc
        # at an exact station average the two neighbouring intervals
        i_l = np.clip(i - 1, 0, L.ns - 2)
        at_st = np.abs(a - L.a[i]) < 1e-7
        dpda_r, dpdw_r = self._normal_interval(i, wc)
        dpda_l, dpdw_l = self._normal_interval(i_l, wc)
        use_l = at_st & (i > 0)
        dpda = np.where(use_l[:, None], 0.5 * (dpda_r + dpda_l), dpda_r)
        dpdw = np.where(use_l[:, None], 0.5 * (dpdw_r + dpdw_l), dpdw_r)
        N = G.norm(np.cross(dpda, dpdw))
        c = L.centroid_at(a)
        flip = np.sum(N * (P - c), axis=1) < 0
        N[flip] = -N[flip]
        return P, N, G.norm(dpda)

    def sw(self, a: float) -> float:
        """Metres per unit w at a."""
        r0, r1, _ = self._rv(np.array([a]))
        return float(np.linalg.norm(r1[0] - r0[0]))

    def stations_in(self, a0: float, a1: float) -> np.ndarray:
        A = self.loft.a
        return A[(A > a0 + 1e-6) & (A < a1 - 1e-6)]

    def skin(self, g: G.Geo, mat, a0=None, a1=None, w0=0.0, w1=1.0, grime: float = 0.85, tone: float = G.TONE0, kind: str = "skin") -> None:
        """The base surface: one quad per station interval, flat shaded, dark in the gaps between plates."""
        a0 = self.a0 if a0 is None else a0
        a1 = self.a1 if a1 is None else a1
        A = np.concatenate([[a0], self.stations_in(a0, a1), [a1]])
        P0 = self.pts(A, w0)
        P1 = self.pts(A, w1)
        n = len(A)
        V = np.concatenate([P0, P1])
        Q = np.stack([np.arange(n - 1), np.arange(1, n), np.arange(1, n) + n, np.arange(n - 1) + n], axis=1)
        F = G.quads_to_tris(Q)
        # orient outward
        _, N, _ = self.frame(A[:-1] * 0.5 + A[1:] * 0.5, 0.5 * (w0 + w1))
        a_, b_, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        nn = np.cross(b_ - a_, c_ - a_)
        Nf = np.concatenate([N, N])
        flip = np.sum(nn * Nf, axis=1) < 0
        F[flip] = F[flip][:, [0, 2, 1]]
        g.add(V, F, mat, a1=(0.0, grime), a2=(tone, 0.0), kind=kind)


class PlanarZone:
    """A flat rectangle presented as a zone, so plates and panels can be laid on any flat face of any part (a turret's cheek, a
    tower's side, a hangar wall): P(a, w) = origin + ea * a + ew * (w * width), a in [0, length], w in [0, 1]."""

    def __init__(self, origin, ea, ew, length: float, width: float, normal=None):
        self.o = np.asarray(origin, np.float64)
        self.ea = G.norm(ea)
        self.ew = G.norm(ew)
        self.length = float(length)
        self.width = float(width)
        self.n = G.norm(np.cross(self.ea, self.ew)) if normal is None else G.norm(normal)
        self.a0 = 0.0
        self.a1 = float(length)

    def pts(self, a, w):
        a = np.atleast_1d(np.asarray(a, np.float64))
        w = np.broadcast_to(np.asarray(w, np.float64), a.shape)
        return self.o + self.ea * a[:, None] + self.ew * (w * self.width)[:, None]

    def frame(self, a, w):
        P = self.pts(a, w)
        return P, np.broadcast_to(self.n, P.shape).copy(), np.broadcast_to(self.ea, P.shape).copy()

    def sw(self, a: float) -> float:
        return self.width

    def stations_in(self, a0: float, a1: float) -> np.ndarray:
        return np.zeros(0)


# ---------------------------------------------------------------------------------------------------------------- plate
@dataclass
class Plate:
    """A laid plate: where it is and how thick, for the panel and greeble passes."""
    zone: Zone
    a0: float
    a1: float
    w0: float
    w1: float
    t0: float
    t1: float
    mat: str
    tone: float
    outline: np.ndarray = None       # (4,2) corners in (a, w): c0 (a0,w0) c1 (a1,w0) c2 (a1',w1) c3 (a0',w1)
    panels: list = field(default_factory=list)
    used: float = 0.0

    def thick(self, a):
        a = np.asarray(a, np.float64)
        return self.t0 + (self.t1 - self.t0) * np.clip((a - self.a0) / max(1e-9, self.a1 - self.a0), 0.0, 1.0)

    def center(self):
        return self.outline.mean(axis=0)

    def size_m(self):
        """(length along a, width across) in metres, at the middle."""
        am = 0.5 * (self.a0 + self.a1)
        return (self.a1 - self.a0), (self.w1 - self.w0) * self.zone.sw(am)

    def top(self, a, w, lift: float = 0.0):
        """(P, N, T) on the plate's top at (a, w), `lift` above it (panels stand on top)."""
        P, N, T = self.zone.frame(np.atleast_1d(a), np.atleast_1d(w))
        h = self.thick(np.atleast_1d(a)) + lift
        return P + N * h[:, None], N, T


def _inset_quad(c: np.ndarray, d: float, sw: float) -> np.ndarray:
    """Inset a convex quad (4,2) in (a, w) by d metres (w scaled by sw metres per unit) -> new corners."""
    if d == 0.0:
        return c
    m = c * np.array([1.0, sw])
    e = np.roll(m, -1, axis=0) - m                                   # edge i: m[i] -> m[i+1]
    L = np.maximum(np.linalg.norm(e, axis=1, keepdims=True), 1e-9)
    dirs = e / L
    nrm = np.stack([-dirs[:, 1], dirs[:, 0]], axis=1)                # left normal: inward for a counter-clockwise polygon
    p2 = m + nrm * d                                                  # a point on each offset line
    p1, d1 = np.roll(p2, 1, axis=0), np.roll(dirs, 1, axis=0)         # the previous edge's line
    den = d1[:, 0] * dirs[:, 1] - d1[:, 1] * dirs[:, 0]
    den = np.where(np.abs(den) < 1e-9, 1e-9, den)
    t = ((p2[:, 0] - p1[:, 0]) * dirs[:, 1] - (p2[:, 1] - p1[:, 1]) * dirs[:, 0]) / den
    out = p1 + d1 * t[:, None]
    return out / np.array([1.0, sw])


def slab(g: G.Geo, zone: Zone, outline: np.ndarray, mat, base, height0: float, height1: float, chamfer: float, rim: float,
         embed: float, tone: float = G.TONE0, aux: float = 0.0, wear: float = 1.0, wall_wear: float = 0.45, wall_grime: float = 0.3,
         kind: str = "plate", stations: bool = True, with_top: bool = True) -> bool:
    """One slab on a zone. outline: (4,2) corners in (a, w), counter-clockwise (c0 -> c1 along a at w0; c2, c3 on the w1 side).
    base(a) -> height of the surface the slab stands on (0 for a plate on the skin); the slab's top is base + height0 at the start
    (a of c0/c3) growing linearly to base + height1 at its end. Layers: the wall (embedded foot, dark; the top of the wall), the
    chamfer (chipped), a rim (the chip fades out over `rim` metres), then the flat top. Returns False if too small to build."""
    am = float(outline[:, 0].mean())
    sw = zone.sw(am)
    span_a = min(outline[1, 0] - outline[0, 0], outline[2, 0] - outline[3, 0])
    span_w = (outline[3, 1] - outline[0, 1]) * sw
    if span_a < 2.0 * chamfer + 0.06 or span_w < 2.0 * chamfer + 0.06:
        return False
    c = min(chamfer, 0.45 * min(span_a, span_w), (0.45 * height0 + 0.02) if height0 > 0 else chamfer)
    rim = max(0.0, min(rim, 0.5 * (min(span_a, span_w) - 2.0 * c) - 0.01))
    polys = [outline, outline, _inset_quad(outline, c, sw)]
    if rim > 1e-3:
        polys.append(_inset_quad(outline, c + rim, sw))
    inner = polys[-1]
    sb = zone.stations_in(min(inner[0, 0], inner[1, 0]), max(inner[0, 0], inner[1, 0])) if stations else np.zeros(0)
    st = zone.stations_in(min(inner[3, 0], inner[2, 0]), max(inner[3, 0], inner[2, 0])) if stations else np.zeros(0)

    def loop(poly):
        pts = [poly[0]]
        pts += [_edge_at(poly[0], poly[1], s) for s in sb]
        pts += [poly[1], poly[2]]
        pts += [_edge_at(poly[3], poly[2], s) for s in st[::-1]]
        pts.append(poly[3])
        return np.array(pts)

    loops = [loop(p) for p in polys]
    n = len(loops[0])
    nl = len(loops)
    a_len = max(1e-6, float(outline[1, 0] - outline[0, 0]))
    ctr = inner.mean(axis=0)
    AW = np.concatenate(loops + [ctr[None]])
    P, N, _ = zone.frame(AW[:, 0], AW[:, 1])
    b = base(AW[:, 0])
    top = b + height0 + (height1 - height0) * np.clip((AW[:, 0] - outline[0, 0]) / a_len, 0.0, 1.0)
    h = np.empty(len(AW))
    A1 = np.zeros((len(AW), 2), F32)
    h[:n], A1[:n] = b[:n] - embed, (0.0, 1.0)                        # the embedded foot: dark
    h[n:2 * n], A1[n:2 * n] = top[n:2 * n] - c, (wall_wear, wall_grime)
    h[2 * n:3 * n], A1[2 * n:3 * n] = top[2 * n:3 * n], (wear, 0.0)  # the chamfer's ridge: most chipped
    if nl == 4:
        h[3 * n:4 * n], A1[3 * n:4 * n] = top[3 * n:4 * n], (0.0, 0.0)
    h[-1], A1[-1] = top[-1], (0.0, 0.0)
    V = P + N * h[:, None]
    F = G.quads_to_tris(np.concatenate([G.strip_quads(n, i * n, (i + 1) * n, True) for i in range(nl - 1)]))
    if with_top:
        ci = nl * n
        tl = (nl - 1) * n
        fan = np.stack([np.arange(n) + tl, (np.arange(n) + 1) % n + tl, np.full(n, ci)], axis=1).astype(I32)
        F = np.concatenate([F, fan])
    # every face was written counter-clockwise in (a, w): all of them face along dP/da x dP/dw; flip the lot if that is inward
    a_, b_, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    top_ids = np.arange(len(F) - n, len(F)) if with_top else np.arange(max(0, len(F) - 4), len(F))
    nn = np.cross(b_[top_ids] - a_[top_ids], c_[top_ids] - a_[top_ids])
    if np.sum(nn @ N[-1]) < 0:
        F = F[:, [0, 2, 1]]
    g.add(V, F, mat, A1, (tone, aux), kind=kind)
    return True


def strip_quads(n, off_a, off_b):
    return G.strip_quads(n, off_a, off_b, True)


def _edge_at(p, q, a):
    """The point of the edge p->q (in (a, w)) at coordinate a."""
    t = (a - p[0]) / (q[0] - p[0]) if abs(q[0] - p[0]) > 1e-9 else 0.0
    return p + (q - p) * t


# ---------------------------------------------------------------------------------------------------------- plating
@dataclass
class Scheme:
    """How a zone is plated. Lengths in metres."""
    row_w: tuple = (3.0, 6.5)             # width of a row of plates
    plate_len: tuple = (10.0, 40.0)
    gap_a: tuple = (0.25, 0.55)           # seam between plates in a row
    gap_w: tuple = (0.3, 0.7)             # seam between rows
    levels: tuple = (0.5, 0.75, 1.0)      # plate thickness levels (metres)
    level_weights: tuple = (0.45, 0.35, 0.2)
    wedge: float = 0.0                    # extra thickness at the plate's end (layered look)
    shear: tuple = (0.0, 0.0)             # top-edge shift of the plate corners (parallelograms, trapezoids), metres
    chamfer: float = 0.10
    rim: float = 0.28
    embed: float = 0.35
    tone_sigma: float = 0.13              # spread of the plates' tones
    mats: tuple = (("Plate", 1.0),)
    min_len: float = 4.0
    min_w: float = 0.6                    # narrowest row of plates worth laying (metres)


def _pick(rng, options):
    r = rng.random() * sum(w for _, w in options)
    acc = 0.0
    for m, w in options:
        acc += w
        if r <= acc:
            return m
    return options[-1][0]


def _intervals(a_lo: float, a_hi: float, voids) -> list:
    """[a_lo, a_hi] minus the void intervals, as a list of (start, end)."""
    out, a = [], a_lo
    for v0, v1 in sorted(voids):
        if v1 <= a or v0 >= a_hi:
            continue
        if v0 > a:
            out.append((a, min(v0, a_hi)))
        a = max(a, v1)
    if a < a_hi:
        out.append((a, a_hi))
    return out


def plate_zone(g: G.Geo, zone, rng: np.random.Generator, sch: Scheme, prefix: str, a_lo: float | None = None, a_hi: float | None = None,
               w_lo: float = 0.0, w_hi: float = 1.0, skip=None, mat_fn=None, tone_fn=None, voids=()) -> list[Plate]:
    """Lay plates over a stretch of a zone: rows across, plates staggered along. skip(a0,a1,w0,w1) -> True leaves a hole;
    mat_fn(row_index, a_mid, w_mid) -> slot name or None; tone_fn(a_mid, w_mid) -> offset added to the random tone; voids: (a0, a1)
    intervals with no plates at all (ribs, a mount). A plate never straddles a section cut (g.cuts). Returns the plates laid."""
    a_lo = zone.a0 if a_lo is None else a_lo
    a_hi = zone.a1 if a_hi is None else a_hi
    swz = zone.sw(0.5 * (a_lo + a_hi))
    plates: list[Plate] = []
    cuts = sorted(g.cuts) if g.cuts else []
    n_rows = max(1, int(round((w_hi - w_lo) * swz / (0.5 * (sch.row_w[0] + sch.row_w[1])))))
    u = rng.uniform(0.6, 1.4, n_rows)
    edges = w_lo + (w_hi - w_lo) * np.concatenate([[0.0], np.cumsum(u) / u.sum()])
    spans = _intervals(a_lo, a_hi, voids)
    for ri in range(n_rows):
        w0, w1 = edges[ri], edges[ri + 1]
        gw = rng.uniform(*sch.gap_w) / swz
        pw0, pw1 = w0 + gw * 0.5, w1 - gw * 0.5
        if pw1 - pw0 < sch.min_w / swz:
            continue
        for s_lo, s_hi in spans:
            a = s_lo
            first = True
            while a < s_hi - 0.5 * sch.min_len:
                L = rng.uniform(*sch.plate_len) * (rng.uniform(0.25, 1.0) if first else 1.0)   # staggered rows
                first = False
                e = min(a + L, s_hi)
                for xc in cuts:
                    if a < xc < e:
                        e = xc                                   # a plate never straddles a section cut
                if s_hi - e < sch.min_len and not any(e < xc < s_hi for xc in cuts):
                    e = s_hi
                ga = rng.uniform(*sch.gap_a)
                pa0, pa1 = a + ga * 0.5, e - ga * 0.5
                a_next = e
                if pa1 - pa0 < 0.5 * sch.min_len or (skip is not None and skip(pa0, pa1, pw0, pw1)):
                    a = a_next
                    continue
                lw = np.array(sch.level_weights, float) if len(sch.level_weights) == len(sch.levels) else np.ones(len(sch.levels))
                level = int(rng.choice(len(sch.levels), p=lw / lw.sum()))
                t0 = sch.levels[level] * rng.uniform(0.9, 1.1)
                t1 = t0 + sch.wedge
                s0 = rng.uniform(-1.0, 1.0) * sch.shear[0]
                s1 = s0 + rng.uniform(-1.0, 1.0) * sch.shear[1]
                outline = np.array([[pa0, pw0], [pa1, pw0], [pa1 + s1, pw1], [pa0 + s0, pw1]])
                mid_a, mid_w = 0.5 * (pa0 + pa1), 0.5 * (pw0 + pw1)
                mat = (mat_fn(ri, mid_a, mid_w) if mat_fn else None) or _pick(rng, sch.mats)
                tone = float(np.clip(G.TONE0 + rng.normal(0.0, sch.tone_sigma) + (tone_fn(mid_a, mid_w) if tone_fn else 0.0), 0.02, 0.98))
                if slab(g, zone, outline, prefix + mat, lambda x: np.zeros_like(x), t0, t1, sch.chamfer, sch.rim, sch.embed, tone=tone):
                    plates.append(Plate(zone, pa0, pa1, pw0, pw1, t0, t1, prefix + mat, tone, outline))
                a = a_next
    return plates


def plate_tower(g: G.Geo, zone, rng: np.random.Generator, sch: Scheme, prefix: str, a_lo: float | None = None, a_hi: float | None = None,
                w_lo: float = 0.0, w_hi: float = 1.0, skip=None, mat_fn=None, tone_fn=None) -> list[Plate]:
    """Plating for a tower-like zone whose `a` runs up: rows are horizontal courses stacked along a (row_w is their height),
    plates lie along w with lengths plate_len (metres). Same interface as plate_zone otherwise."""
    a_lo = zone.a0 if a_lo is None else a_lo
    a_hi = zone.a1 if a_hi is None else a_hi
    swz = zone.sw(0.5 * (a_lo + a_hi))
    wm = (w_hi - w_lo) * swz
    plates: list[Plate] = []
    n_rows = max(1, int(round((a_hi - a_lo) / (0.5 * (sch.row_w[0] + sch.row_w[1])))))
    u = rng.uniform(0.6, 1.4, n_rows)
    edges = a_lo + (a_hi - a_lo) * np.concatenate([[0.0], np.cumsum(u) / u.sum()])
    for ri in range(n_rows):
        r0, r1 = edges[ri], edges[ri + 1]
        gr = rng.uniform(*sch.gap_w)
        pa0, pa1 = r0 + gr * 0.5, r1 - gr * 0.5
        if pa1 - pa0 < sch.min_w:
            continue
        x = 0.0
        first = True
        while x < wm - 0.5 * sch.min_len:
            L = rng.uniform(*sch.plate_len) * (rng.uniform(0.25, 1.0) if first else 1.0)
            first = False
            e = min(x + L, wm)
            if wm - e < sch.min_len:
                e = wm
            ga = rng.uniform(*sch.gap_a)
            q0, q1 = w_lo + (x + ga * 0.5) / swz, w_lo + (e - ga * 0.5) / swz
            x_next = e
            if (q1 - q0) * swz < 0.5 * sch.min_len or (skip is not None and skip(pa0, pa1, q0, q1)):
                x = x_next
                continue
            lw = np.array(sch.level_weights, float) if len(sch.level_weights) == len(sch.levels) else np.ones(len(sch.levels))
            t0 = sch.levels[int(rng.choice(len(sch.levels), p=lw / lw.sum()))] * rng.uniform(0.9, 1.1)
            outline = np.array([[pa0, q0], [pa1, q0], [pa1, q1], [pa0, q1]])
            mid_a, mid_w = 0.5 * (pa0 + pa1), 0.5 * (q0 + q1)
            mat = (mat_fn(ri, mid_a, mid_w) if mat_fn else None) or _pick(rng, sch.mats)
            tone = float(np.clip(G.TONE0 + rng.normal(0.0, sch.tone_sigma) + (tone_fn(mid_a, mid_w) if tone_fn else 0.0), 0.02, 0.98))
            if slab(g, zone, outline, prefix + mat, lambda t: np.zeros_like(t), t0, t0, sch.chamfer, sch.rim, sch.embed, tone=tone):
                plates.append(Plate(zone, pa0, pa1, q0, q1, t0, t0, prefix + mat, tone, outline))
            x = x_next
    return plates
