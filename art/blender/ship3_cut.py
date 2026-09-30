"""ASTRA ships v3 — section pieces: the burnt cut faces.

A capital ship is exported whole and also in three pieces (bow, mid, stern) that share its frame: the whole mesh is swapped for its
pieces when the ship breaks apart. The cuts are planes at `g.cuts` (x, bow first); plates never straddle them (ship3_loft), so each
piece is the ship's own geometry between two planes. What this module adds are the *cap* chunks that exist only in the pieces: at
each cut, on both sides, a torn armour band, an inner liner going in, a back bulkhead, decks and frames of a burnt interior (some
with emergency strips still lit), girders and peeled plates sticking out into the gap.
"""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_loft as LF
from ship3_kit import Ctx

M_DENSE = 56


def resample(poly: np.ndarray, m: int) -> np.ndarray:
    """m points uniformly along the perimeter of a closed polygon (n,2)."""
    p = np.asarray(poly, np.float64)
    q = np.vstack([p, p[:1]])
    seg = np.linalg.norm(np.diff(q, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    t = np.linspace(0.0, cum[-1], m, endpoint=False)
    idx = np.clip(np.searchsorted(cum, t, side="right") - 1, 0, len(seg) - 1)
    f = (t - cum[idx]) / np.maximum(seg[idx], 1e-9)
    return q[idx] + (q[idx + 1] - q[idx]) * f[:, None]


def slice_extent(poly: np.ndarray, axis: int, lo: float, hi: float):
    """The extent along the other axis of a convex polygon clipped to lo <= coordinate[axis] <= hi, or None."""
    q = H.clip_poly(poly, axis, lo, True)
    if len(q) < 3:
        return None
    q = H.clip_poly(q, axis, hi, False)
    if len(q) < 3:
        return None
    o = 1 - axis
    return float(q[:, o].min()), float(q[:, o].max())


def _orient(V: np.ndarray, F: np.ndarray, want) -> np.ndarray:
    """Flip triangles whose normal disagrees with want(centres) (n,3)."""
    a, b, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c_ - a)
    w = want((a + b + c_) / 3.0)
    flip = np.sum(n * w, axis=1) < 0
    F = F.copy()
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


def make_cut(c: Ctx, poly_yz: np.ndarray, xc: float, s: int, sec: int, depth: float = 28.0, armour: float = 2.4, pitch: float = 3.6,
             extras=(), scale: float = 1.0) -> dict:
    """One side of one cut. poly_yz: the hull section (y, z) at xc; s = +1 when the piece lies at x > xc (its aft end is the cut),
    -1 when it lies at x < xc. Everything lands in the caps of section `sec`. Returns the cut face's description for the manifest."""
    g, rng, m = c.g, c.rng, c.m
    depth = depth * scale
    with g.capture(sec):
        outer = resample(poly_yz, M_DENSE)
        cen = outer.mean(axis=0)
        inward = cen[None] - outer
        L = np.linalg.norm(inward, axis=1, keepdims=True)
        u_in = inward / np.maximum(L, 1e-6)
        # jagged armour thickness and recess along the tear (smooth noise from a few random harmonics)
        ph = rng.uniform(0, 2 * math.pi, 4)
        k = np.arange(M_DENSE) / M_DENSE * 2 * math.pi
        noise = sum(np.sin(h * k + ph[h - 1]) / h for h in range(1, 5))
        thick = np.clip(armour * scale * (1.0 + 0.55 * noise / 2.0), 0.6 * armour * scale, 3.0 * armour * scale)
        rec = np.clip((0.5 + 0.5 * noise / 2.0) * 5.0 * scale + rng.uniform(0, 1.5, M_DENSE), 0.0, 9.0 * scale)
        inner = outer + u_in * thick[:, None]
        xo, xi = xc, xc + s * rec
        # (a) the torn band: outer edge on the skin's end, inner edge recessed and jagged
        V = np.concatenate([np.column_stack([np.full(M_DENSE, xo), outer]), np.column_stack([xi, inner])])
        F = G.quads_to_tris(G.strip_quads(M_DENSE, 0, M_DENSE, True))
        F = _orient(V, F, lambda cc: np.tile([-s, 0.0, 0.0], (len(cc), 1)))
        g.add(V, F, m("Cut"), a1=np.column_stack([np.full(2 * M_DENSE, 0.5), np.full(2 * M_DENSE, 0.9)]), a2=(0.66, 1.0), kind="cut")
        # (b) the liner: the section inset, going in `depth`, faces the axis; and the back bulkhead
        liner = outer + u_in * (1.4 * scale)
        nseg = 3
        rings = [np.column_stack([np.full(M_DENSE, xc + s * depth * i / nseg), liner]) for i in range(nseg + 1)]
        V = np.concatenate(rings)
        Q = np.concatenate([G.strip_quads(M_DENSE, i * M_DENSE, (i + 1) * M_DENSE, True) for i in range(nseg)])
        F = G.quads_to_tris(Q)
        F = _orient(V, F, lambda cc: np.column_stack([np.zeros(len(cc)), cen[0] - cc[:, 1], cen[1] - cc[:, 2]]))
        g.add(V, F, m("Cut"), a1=(0.2, 1.0), a2=(0.40, 1.0), kind="cut")
        Vb = np.vstack([np.column_stack([np.full(M_DENSE, xc + s * depth), liner]), [xc + s * depth, cen[0], cen[1]]])
        Fb = np.stack([np.arange(M_DENSE), (np.arange(M_DENSE) + 1) % M_DENSE, np.full(M_DENSE, M_DENSE)], axis=1)
        Fb = _orient(Vb, Fb, lambda cc: np.tile([-s, 0.0, 0.0], (len(cc), 1)))
        g.add(Vb, Fb, m("Cut"), a1=(0.0, 1.0), a2=(0.16, 1.0), kind="cut")
        # (c) decks and frames of the burnt interior
        inner_poly = LF._inset_quad(np.asarray(poly_yz, np.float64), 1.6 * scale, 1.0)
        z0, z1 = float(inner_poly[:, 1].min()), float(inner_poly[:, 1].max())
        y0, y1 = float(inner_poly[:, 0].min()), float(inner_poly[:, 0].max())
        n_dk = max(2, int((z1 - z0) / pitch))
        zs = np.linspace(z0 + 1.0, z1 - 1.0, n_dk)
        pieces_b, pieces_l = [], []
        for zk in zs:
            ex = slice_extent(inner_poly, 1, zk - 0.2, zk + 0.2)
            if ex is None:
                continue
            ya, yb = ex
            nseg_d = int(rng.integers(1, 4))
            cuts_y = np.sort(rng.uniform(ya, yb, nseg_d - 1)) if nseg_d > 1 else np.zeros(0)
            edges = np.concatenate([[ya], cuts_y, [yb]])
            for i in range(len(edges) - 1):
                a, b = edges[i] + 0.15, edges[i + 1] - 0.15
                if b - a < 1.5 or rng.random() < 0.18:
                    continue
                r = rng.uniform(0.6, 15.0) * scale
                ln = depth - 0.6 - r
                if ln < 3.0:
                    continue
                pieces_b.append(((xc + s * (r + ln / 2), 0.5 * (a + b), zk), (ln, b - a, 0.30)))
                if rng.random() < 0.28:                                       # an emergency strip still lit
                    pieces_l.append(((xc + s * (r + ln * 0.5), 0.5 * (a + b), zk + 0.2), (ln * 0.7, 0.18, 0.06)))
        for i, yv in enumerate(np.arange(y0 + 5.0, y1 - 4.0, 8.5 * scale)):
            for zk0, zk1 in zip(zs[:-1], zs[1:]):
                if rng.random() < 0.55:
                    continue
                ex = slice_extent(inner_poly, 0, yv - 0.2, yv + 0.2)
                if ex is None or ex[0] > zk0 + 0.5 or ex[1] < zk1 - 0.5:
                    continue
                r = rng.uniform(1.0, 17.0) * scale
                ln = depth - 0.6 - r
                if ln < 3.0:
                    continue
                pieces_b.append(((xc + s * (r + ln / 2), yv, 0.5 * (zk0 + zk1)), (ln, 0.25, zk1 - zk0 - 0.3)))
        if pieces_b:
            cs = np.array([p[0] for p in pieces_b])
            sz = np.array([p[1] for p in pieces_b])
            g.boxes(cs, sz / 2.0, m("Cut"), chamfer=0.0, kind="cut", wear=0.2, grime=1.0, aux=1.0, tone=0.80)
        if pieces_l:
            g.boxes(np.array([p[0] for p in pieces_l]), np.array([p[1] for p in pieces_l]) / 2.0, m("Lights"), chamfer=0.0, kind="cut",
                    aux=rng.uniform(0.0, 0.6, len(pieces_l)))
        # (d) girders sticking out into the gap
        for _ in range(int(14 * scale ** 0.5) + 6):
            i = int(rng.integers(0, M_DENSE))
            p0 = np.array([xc + s * 1.0, *(outer[i] + u_in[i] * rng.uniform(1.5, 5.0) * scale)])
            ln = rng.uniform(3.0, 15.0) * scale
            d = np.array([-s, rng.uniform(-0.28, 0.28), rng.uniform(-0.28, 0.28)])
            g.box_between(p0, p0 + G.norm(d) * ln, 0.55 * scale, 1.0 * scale, m("Cut"), chamfer=0.04, kind="cut", wear=0.3, grime=1.0, aux=1.0, tone=0.92)
        # (e) peeled armour plates: hinged on the rim, curling out into the gap
        for _ in range(int(8 * scale ** 0.5) + 3):
            i = int(rng.integers(0, M_DENSE))
            t = outer[(i + 1) % M_DENSE] - outer[i - 1]
            t = t / max(np.linalg.norm(t), 1e-9)
            nout = -u_in[i]
            th = math.radians(rng.uniform(20, 75))
            Lp, Wp = rng.uniform(4.0, 9.0) * scale, rng.uniform(2.5, 5.0) * scale
            dirv = G.norm(np.array([-s * math.cos(th), nout[0] * math.sin(th), nout[1] * math.sin(th)]))
            hinge = np.array([xc, *(outer[i] + u_in[i] * 0.3)])
            tang = np.array([0.0, t[0], t[1]])
            fr = G.frame_x(dirv, np.cross(dirv, tang))                      # x along the plate, y along the rim, z its thin axis
            g.box(hinge + dirv * Lp / 2, (Lp, Wp, 0.5 * scale), m("Plate"), frame=fr, chamfer=0.06, wear=0.9, grime=0.5, kind="cut")
        # (f) the parts of other structures that cross this cut (the upper deck above the hull, the keel below): flat burnt caps
        for poly2, side, zlim in extras:
            q = H.clip_poly(np.asarray(poly2, np.float64), 1, zlim, side > 0)
            if len(q) < 3:
                continue
            cq = q.mean(axis=0)
            Vq = np.vstack([np.column_stack([np.full(len(q), xc + s * 1.5), q]), [xc + s * 1.5, cq[0], cq[1]]])
            Fq = np.stack([np.arange(len(q)), (np.arange(len(q)) + 1) % len(q), np.full(len(q), len(q))], axis=1)
            Fq = _orient(Vq, Fq, lambda cc: np.tile([-s, 0.0, 0.0], (len(cc), 1)))
            g.add(Vq, Fq, m("Cut"), a1=(0.3, 1.0), a2=(0.58, 1.0), kind="cut")
    return {"x": float(xc), "normal": [float(-s), 0.0, 0.0], "center": [float(xc), float(cen[0]), float(cen[1])],
            "y": [float(outer[:, 0].min()), float(outer[:, 0].max())], "z": [float(outer[:, 1].min()), float(outer[:, 1].max())], "section": sec}


def make_all_cuts(c: Ctx, loft: LF.Loft, cuts, extras_fn=None, scale: float = 1.0, depth: float = 28.0) -> list[dict]:
    """The caps of every cut of a ship: for cut i (x descending) section i is forward of it and section i+1 aft of it."""
    faces = []
    for i, xc in enumerate(cuts):
        ring = loft.ring_at(xc)
        poly = ring[:, 1:3]
        ex = extras_fn(xc) if extras_fn else ()
        faces.append(make_cut(c, poly, xc, +1, i, depth=depth, scale=scale, extras=ex))
        faces.append(make_cut(c, poly, xc, -1, i + 1, depth=depth, scale=scale, extras=ex))
    return faces
