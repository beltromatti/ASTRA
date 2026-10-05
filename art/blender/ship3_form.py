"""ASTRA ships v4 — sculpted hull forms (PREPARATORY: no ship in the game uses this module yet; see docs/brief/ARTE-SCAFI.md, "Stato").

v3 lofted every hull from an eight-point chamfered rectangle: a plank. This module builds the smooth, intentional shapes of the ASTRA
design language (docs/STILE.md §12): a station table (x, half-width, deck, keel, ...) turned into rings of 44 points whose topology
never changes along the ship, so a point index is a line of the hull (the keel, the bilge, the beam, the shoulder, the deck's edge,
the crown) and a run of ring edges is a *band* that plates, window strips and the navy livery follow.

  curve(points)          a smooth (monotone cubic) curve through (x, value) pairs: the ship's plan form, profile and section parameters
  half_section / ring_of the section family: flat belly, bilge, beam, leaning flank, shoulder, cambered deck, four rounded corners
  FormHull               the station table -> a `ship3_loft.Loft` (`.loft`), `.band(k0, k1)`, `.edges(k)`
  BandZone               a run of ring edges as one surface P(a, w), with the interface of `ship3_loft.Zone` (pts, frame, sw, stations_in)

Tested offline (numpy only): the curve reproduces its nodes and stays monotone, every ring is convex and counter-clockwise, a band's points
at the ring vertices are the ring vertices, its normals point out, and a one-edge band equals the one-edge `Zone`.
NOT DONE YET: `ship3_loft.slab` does not read `BandZone.w_breaks`, so a plate laid on a band is flat across its width (a chord of the
curved surface). Lay plates on one-edge zones (`FormHull.edges(k)`) or bands of two edges until the slab follows the ring vertices inside
a plate (the loop of the plate's outline gets a point at each break on its two cross edges; see the notes in docs/brief/ARTE-SCAFI.md).

Ring (y, z), counter-clockwise (+y is Blender's port), index 0 on the keel's centreline, NS = 2 * HALF - 2 = 44 points:
  keel  belly  belly edge   lower side  lower chine  flank   upper chine  shoulder  deck's edge  deck    crown
  0     1      2-4 (round)  5           6-8 (round)  9-11    12-14 (round) 15       16-18 (round) 19-21   22
and the mirror image for the other side (index NS - k mirrors k).
"""
from __future__ import annotations

import numpy as np

import ship3_geo as G
import ship3_loft as LF

F32 = np.float32


# ------------------------------------------------------------------------------------------------------------------ curves
def curve(points, kind: str = "pchip"):
    """A function of x (array in, array out) through the (x, value) pairs: a monotone cubic Hermite (Fritsch-Carlson), so a hull
    has no overshoot between two control stations. kind "linear" gives the straight segments."""
    P = sorted((float(x), float(v)) for x, v in points)
    x = np.array([p[0] for p in P])
    y = np.array([p[1] for p in P])
    if len(x) == 1:
        return lambda t: np.full(np.shape(t), y[0])
    if kind == "linear":
        return lambda t: np.interp(t, x, y)
    h = np.diff(x)
    d = np.diff(y) / h
    m = np.zeros_like(y)
    if len(x) == 2:
        m[:] = d[0]
    else:
        same = d[:-1] * d[1:] > 0
        w1 = 2 * h[1:] + h[:-1]
        w2 = h[1:] + 2 * h[:-1]
        with np.errstate(all="ignore"):
            hm = (w1 + w2) / (w1 / np.where(d[:-1] == 0, 1, d[:-1]) + w2 / np.where(d[1:] == 0, 1, d[1:]))
        m[1:-1] = np.where(same, hm, 0.0)

        def end(h0, h1, d0, d1):
            e = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
            if np.sign(e) != np.sign(d0):
                return 0.0
            if np.sign(d0) != np.sign(d1) and abs(e) > 3 * abs(d0):
                return 3 * d0
            return e
        m[0] = end(h[0], h[1], d[0], d[1])
        m[-1] = end(h[-1], h[-2], d[-1], d[-2])

    def f(t):
        t = np.asarray(t, np.float64)
        i = np.clip(np.searchsorted(x, t, side="right") - 1, 0, len(x) - 2)
        s = np.clip((t - x[i]) / h[i], 0.0, 1.0)
        s2, s3 = s * s, s * s * s
        return (2 * s3 - 3 * s2 + 1) * y[i] + (s3 - 2 * s2 + s) * h[i] * m[i] + (-2 * s3 + 3 * s2) * y[i + 1] + (s3 - s2) * h[i] * m[i + 1]
    return f


# ----------------------------------------------------------------------------------------------------------------- sections
FILLET = 3                                   # points of a rounded corner (the two ends and one between)
SEG = (1, 1, 3, 1, 3)                        # interior points of: belly, bilge side, flank, shoulder, deck
HALF = 2 + sum(SEG) + 4 * FILLET             # ring points from the keel (index 0) to the crown (index HALF - 1)
NS = 2 * HALF - 2                            # ring points all round
CROWN = HALF - 1


def _fillet(prev: np.ndarray, corner: np.ndarray, nxt: np.ndarray, r: float, m: int = FILLET):
    """A quadratic Bezier of m points rounding `corner` between the segments to `prev` and `nxt`, at most `r` metres from the corner."""
    d0, d1 = prev - corner, nxt - corner
    l0, l1 = float(np.linalg.norm(d0)), float(np.linalg.norm(d1))
    rr = min(r, 0.45 * l0, 0.45 * l1)
    a = corner + d0 / max(l0, 1e-9) * rr
    b = corner + d1 / max(l1, 1e-9) * rr
    t = np.linspace(0.0, 1.0, m)[:, None]
    return (1 - t) ** 2 * a + 2 * (1 - t) * t * corner + t ** 2 * b


def half_section(hw: float, zt: float, zb: float, belly: float = 0.5, fb: float = 0.30, ft: float = 0.72, tumble: float = 0.05,
                 deck: float = 0.82, crown: float = 0.5, keel: float = 0.0, rb: float = 2.0, rw: float = 3.0, rw2: float = 3.0, rs: float = 2.2) -> np.ndarray:
    """The right half (y >= 0) of a section from the keel's centreline to the crown, HALF points (y, z).
    hw       half-width at the beam (the widest, at the lower chine);  zt, zb  the deck's edge and the keel;
    belly    half-width of the flat belly (fraction of hw);  fb, ft  where the lower and the upper chine are (fractions of the height);
    tumble   how far the upper flank leans in (fraction of hw);  deck  the half-width of the flat deck at its edge (fraction of hw);
    crown    the deck's camber (metres above zt at the centreline);  keel  the keel's V (metres below zb at the centreline);
    rb, rw, rw2, rs   the radii (metres) of the four rounded corners: belly edge, lower chine, upper chine, deck's edge."""
    H = zt - zb
    pts = [np.array([0.0, zb - keel]), np.array([belly * hw, zb]), np.array([hw, zb + fb * H]), np.array([hw * (1.0 - tumble), zb + ft * H]),
           np.array([deck * hw, zt]), np.array([0.0, zt + crown])]
    out = [pts[0]]
    radii = (rb, rw, rw2, rs)
    prev_end = pts[0]
    segs = list(SEG)
    for i in range(1, 5):                                    # the corner i (points 1..4) between segment i-1 and i
        f = _fillet(pts[i - 1], pts[i], pts[i + 1], radii[i - 1])
        k = segs[i - 1]
        for j in range(1, k + 1):                           # the interior points of the straight run before this corner
            out.append(prev_end + (f[0] - prev_end) * j / (k + 1))
        out.extend(list(f))
        prev_end = f[-1]
    k = segs[4]
    for j in range(1, k + 1):                               # the deck's run to the crown
        out.append(prev_end + (pts[5] - prev_end) * j / (k + 1))
    out.append(pts[5])
    h = np.array(out)
    assert len(h) == HALF, (len(h), HALF)
    return h


def ring_of(half: np.ndarray) -> np.ndarray:
    """The full ring (NS, 2) counter-clockwise from the keel: up the +y side, over the crown, down the -y side."""
    left = half[1:-1][::-1] * np.array([-1.0, 1.0])
    return np.vstack([half, left])


# ---------------------------------------------------------------------------------------------------------------------- hull
SECTION_KEYS = ("hw", "zt", "zb", "belly", "fb", "ft", "tumble", "deck", "crown", "keel", "rb", "rw", "rw2", "rs")
SECTION_DEFAULTS = dict(belly=0.5, fb=0.30, ft=0.72, tumble=0.05, deck=0.82, crown=0.5, keel=0.0, rb=2.0, rw=3.0, rw2=3.0, rs=2.2)


class FormHull:
    """A hull from a station table. `curves` maps a section parameter (SECTION_KEYS; hw, zt and zb are required) to control points
    [(x, value), ...]; `xs` are the stations (a ring at each; add more where the shape changes fast). The Loft is `.loft`."""

    def __init__(self, xs, curves: dict, kind: str = "pchip", extra_stations=()):
        xs = sorted({round(float(x), 6) for x in list(xs) + list(extra_stations)})
        self.xs = np.array(xs)
        self.fn = {}
        for k in SECTION_KEYS:
            if k in curves:
                self.fn[k] = curve(curves[k], kind)
            elif k in SECTION_DEFAULTS:
                v = SECTION_DEFAULTS[k]
                self.fn[k] = (lambda t, v=v: np.full(np.shape(t), v))
            else:
                raise KeyError(f"the hull has no curve for {k}")
        rings = np.stack([self.ring_at_x(x) for x in self.xs])
        self.loft = LF.Loft(self.xs, rings)

    def params(self, x: float) -> dict:
        return {k: float(self.fn[k](np.array([x]))[0]) for k in self.fn}

    def section(self, x: float) -> np.ndarray:
        """The ring (NS, 2) as (y, z) at x."""
        p = self.params(x)
        return ring_of(half_section(**p))

    def ring_at_x(self, x: float) -> np.ndarray:
        s = self.section(x)
        return np.column_stack([np.full(len(s), x), s])

    # ------------------------------------------------------------------------------------------------------------ bands
    def band(self, k0: int, k1: int) -> "BandZone":
        """The surface over the ring vertices k0..k1 (cyclic, k1 reached going up from k0), as one zone."""
        m = (k1 - k0) % NS
        return BandZone(self.loft, k0 % NS, m)

    def edges(self, k: int) -> LF.Zone:
        return LF.Zone(self.loft, k % NS)


class BandZone:
    """The ruled surface over `m` consecutive ring edges starting at ring vertex `k0`: P(a, w) with w in [0, 1] spread evenly over the
    edges (w = j / m at the ring vertices). Everything a `ship3_loft.Zone` offers to plates, panels and the detail passes, plus
    `w_breaks` (the w of the ring vertices inside the band: what the slab will have to follow, see the module's note)."""

    def __init__(self, loft: LF.Loft, k0: int, m: int):
        self.loft, self.k0, self.m = loft, k0, m
        self.idx = [(k0 + i) % loft.n for i in range(m + 1)]
        self.k = k0                                         # (like Zone.k, for code that keys on the zone number)
        self.w_breaks = [j / m for j in range(1, m)]

    @property
    def a0(self):
        return float(self.loft.a[0])

    @property
    def a1(self):
        return float(self.loft.a[-1])

    def _rings(self, a):
        """The m + 1 ring vertices of the band at each a: (n, m + 1, 3), and the interval index and fraction."""
        L = self.loft
        i, t = L._idx(a)
        R = L.R[:, self.idx, :]
        return R[i] * (1 - t)[:, None, None] + R[i + 1] * t[:, None, None], i, t

    def pts(self, a, w) -> np.ndarray:
        a = np.atleast_1d(np.asarray(a, np.float64))
        w = np.broadcast_to(np.asarray(w, np.float64), a.shape)
        r, _, _ = self._rings(a)
        u = np.clip(w * self.m, 0.0, self.m - 1e-9)
        j = u.astype(np.int64)
        s = (u - j)[:, None]
        rows = np.arange(len(a))
        return r[rows, j] * (1 - s) + r[rows, j + 1] * s

    def frame(self, a, w):
        """(P, N, T): points, unit outward normals and unit tangents along +a at (a, w)."""
        L = self.loft
        a = np.atleast_1d(np.asarray(a, np.float64))
        w = np.broadcast_to(np.asarray(w, np.float64), a.shape)
        u = np.clip(w * self.m, 0.0, self.m - 1e-9)
        j = u.astype(np.int64)
        s = (u - j)[:, None]
        r, i, t = self._rings(a)
        rows = np.arange(len(a))
        P = r[rows, j] * (1 - s) + r[rows, j + 1] * s
        R = L.R[:, self.idx, :]

        def interval(ii):
            da = (L.a[ii + 1] - L.a[ii])[:, None]
            d0 = (R[ii + 1, j] - R[ii, j]) / da
            d1 = (R[ii + 1, j + 1] - R[ii, j + 1]) / da
            dpda = d0 * (1 - s) + d1 * s
            dpdw = 0.5 * (R[ii, j + 1] - R[ii, j] + R[ii + 1, j + 1] - R[ii + 1, j])
            return dpda, dpdw
        i_l = np.clip(i - 1, 0, L.ns - 2)
        at_st = (np.abs(a - L.a[i]) < 1e-7) & (i > 0)
        dpda_r, dpdw_r = interval(i)
        dpda_l, dpdw_l = interval(i_l)
        dpda = np.where(at_st[:, None], 0.5 * (dpda_r + dpda_l), dpda_r)
        dpdw = np.where(at_st[:, None], 0.5 * (dpdw_r + dpdw_l), dpdw_r)
        N = G.norm(np.cross(dpda, dpdw))
        c = L.centroid_at(a)
        flip = np.sum(N * (P - c), axis=1) < 0
        N[flip] = -N[flip]
        return P, N, G.norm(dpda)

    def sw(self, a: float) -> float:
        """Metres per unit w at a: the length of the band's polyline there."""
        r, _, _ = self._rings(np.array([a]))
        return float(np.sum(np.linalg.norm(np.diff(r[0], axis=0), axis=1)))

    def stations_in(self, a0: float, a1: float) -> np.ndarray:
        A = self.loft.a
        return A[(A > a0 + 1e-6) & (A < a1 - 1e-6)]

    def skin(self, *a, **kw) -> None:                        # (the base skin is laid by the ring's single-edge zones)
        raise NotImplementedError("lay the skin with FormHull.edges(k)")
