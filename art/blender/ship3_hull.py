"""ASTRA ships v3 — plating a whole loft with a style, structural ribs, and the detail scatter that puts hatches, vents, blisters,
lamps, cables and stencils on the panels. The ship recipes (ship3_astra, ship3_mandate, ...) are made of these calls plus the parts
of ship3_kit / ship3_kit2."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

import ship3_geo as G
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_panels as PN
from ship3_kit import Ctx


@dataclass
class HullStyle:
    """Everything that makes a hull look like one faction's: how plates are laid, how they are panelled, what gets scattered."""
    scheme: LF.Scheme = field(default_factory=LF.Scheme)
    panels: PN.PanelStyle = field(default_factory=PN.PanelStyle)
    p_panels: float = 0.4                 # share of plates that get panelled
    detail_density: float = 0.35          # scattered details per panel (on the panelled plates)
    weights: dict = field(default_factory=lambda: {"hatch": 3, "vent": 2, "blister": 1, "lamp": 1, "cable": 2, "stencil": 0.5})
    labels: tuple = ("ACCESS 4C-12", "COOLANT", "NO STEP", "DECK 4 · SECTION C", "AUTHORIZED PERSONNEL ONLY", "FUEL", "O2 SUPPLY")
    stencil_height: float = 0.32
    alt_mats: tuple = ("Frame",)


def plate_loft(c: Ctx, loft: LF.Loft, style: HullStyle, zones=None, skip_fn=None, mat_fn=None, tone_fn=None, a_range=None,
               scheme_for=None, skin_mat: str = "Frame", voids=(), skin: bool = True) -> list[LF.Plate]:
    """Skin and plate every zone of a loft (or the listed ones). skip_fn(zone, a0, a1, w0, w1) -> True leaves a hole;
    mat_fn(zone, row, a, w) -> a slot name or None; tone_fn(zone, a, w) -> tone offset; scheme_for(zone) -> a Scheme override;
    voids: (a0, a1) intervals left free of plates (ribs). Returns the plates."""
    g = c.g
    plates: list[LF.Plate] = []
    zs = loft.zones() if zones is None else [loft.zone(k) for k in zones]
    for z in zs:
        if skin:
            z.skin(g, c.m(skin_mat), *(a_range or (None, None)))
        sch = scheme_for(z) if scheme_for else style.scheme
        skip = (lambda a0, a1, w0, w1, z=z: skip_fn(z, a0, a1, w0, w1)) if skip_fn else None
        mf = (lambda r, a, w, z=z: mat_fn(z, r, a, w)) if mat_fn else None
        tf = (lambda a, w, z=z: tone_fn(z, a, w)) if tone_fn else None
        plates += LF.plate_zone(g, z, c.rng, sch, c.pre, a_lo=None if a_range is None else a_range[0], a_hi=None if a_range is None else a_range[1],
                                skip=skip, mat_fn=mf, tone_fn=tf, voids=voids)
    return plates


def ribs(c: Ctx, loft: LF.Loft, xs, width: float, height: float, mat: str = "Frame", zones=None, skip_fn=None, tone: float = 0.4) -> None:
    """Structural ribs: a raised band across the zones at each a in xs (the hull's frame stations)."""
    zs = loft.zones() if zones is None else [loft.zone(k) for k in zones]
    for x in xs:
        for z in zs:
            if not (z.a0 + width < x < z.a1 - width):
                continue
            if skip_fn and skip_fn(z, x - width / 2, x + width / 2, 0.0, 1.0):
                continue
            outline = np.array([[x - width / 2, 0.02], [x + width / 2, 0.02], [x + width / 2, 0.98], [x - width / 2, 0.98]])
            LF.slab(c.g, z, outline, c.m(mat), lambda a: np.zeros_like(a), height, height, 0.12, 0.22, 0.4, tone=tone, kind="rib")


def scatter_details(c: Ctx, plates, style: HullStyle, up=(0.0, 0.0, 1.0), density: float | None = None, stencil_up=None) -> int:
    """Panels of the given plates get hatches, vents, blisters, lamps, cables and stencils, by weight."""
    rng = c.rng
    dens = style.detail_density if density is None else density
    kinds = list(style.weights.keys())
    w = np.array([style.weights[k] for k in kinds], float)
    w /= w.sum()
    n = 0
    cuts = list(c.g.cuts or [])
    for p in plates:
        for pn in p.panels:
            if rng.random() > dens * c.detail:
                continue
            if cuts or c.g.keepouts:
                P0, _, _ = pn.pts([[0.5, 0.5]])
                if c.g.blocked(P0[0] - 1.5, P0[0] + 1.5):
                    continue
            kind = kinds[int(rng.choice(len(kinds), p=w))]
            u, v = rng.uniform(0.3, 0.7), rng.uniform(0.35, 0.65)
            if kind == "hatch":
                K2.hatch(c, pn, u, v, rng, size=(rng.uniform(0.7, 1.4), rng.uniform(0.6, 1.1)))
            elif kind == "vent":
                K2.vent(c, pn, u, v, rng, size=(rng.uniform(1.0, 2.2), rng.uniform(0.6, 1.2)))
            elif kind == "blister":
                K2.blister(c, pn, u, v, rng, r=rng.uniform(0.35, 0.9))
            elif kind == "lamp":
                K2.lamp(c, pn, u, v, rng, size=rng.uniform(0.35, 0.6))
            elif kind == "cable":
                K2.cable_run(c, pn, rng, count=int(rng.integers(1, 4)))
            elif kind == "stencil":
                la, lw = pn.size_m()
                if la > 2.5 and lw > 0.8:
                    K2.stencil(c, pn, 0.5, 0.5, str(rng.choice(style.labels)), min(style.stencil_height, lw * 0.35), up=stencil_up or up)
            n += 1
    return n


def panelize_plates(c: Ctx, plates, style: HullStyle, p: float | None = None, only=None) -> None:
    pp = style.p_panels if p is None else p
    for pl in plates:
        if only is not None and not only(pl):
            continue
        if c.rng.random() < pp:
            PN.panelize(c.g, pl, c.rng, style.panels, c.pre, alt_mats=style.alt_mats)


# ------------------------------------------------------------------------------------------------------------- end faces
def clip_poly(poly: np.ndarray, axis: int, value: float, keep_greater: bool) -> np.ndarray:
    """Sutherland-Hodgman: a convex polygon (n,2) clipped by the line coordinate[axis] = value."""
    out = []
    n = len(poly)
    inside = (lambda q: q[axis] >= value - 1e-9) if keep_greater else (lambda q: q[axis] <= value + 1e-9)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        ia, ib = inside(a), inside(b)
        if ia:
            out.append(a)
        if ia != ib:
            t = (value - a[axis]) / (b[axis] - a[axis])
            out.append(a + (b - a) * t)
    return np.array(out) if len(out) >= 3 else np.zeros((0, 2))


def _poly_area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def face_pieces(poly: np.ndarray, holes) -> list[np.ndarray]:
    """A convex polygon (y, z) minus axis-aligned rectangles holes = [(y0, y1, z0, z1)] as a list of convex pieces."""
    zs = sorted({h[2] for h in holes} | {h[3] for h in holes})
    bands = []
    lo = -1e9
    for z in zs + [1e9]:
        b = poly
        if lo > -1e8:
            b = clip_poly(b, 1, lo, True)
        if z < 1e8 and len(b):
            b = clip_poly(b, 1, z, False)
        if len(b) >= 3:
            bands.append((lo, z, b))
        lo = z
    pieces = []
    for lo, hi, b in bands:
        mid = 0.5 * (max(lo, -1e6) + min(hi, 1e6)) if lo > -1e8 and hi < 1e8 else (hi - 1.0 if lo < -1e8 else lo + 1.0)
        cuts = sorted([(h[0], h[1]) for h in holes if h[2] <= mid <= h[3]])
        y = -1e9
        for (y0, y1) in cuts + [(1e9, 1e9)]:
            piece = b
            if y > -1e8:
                piece = clip_poly(piece, 0, y, True)
            if y0 < 1e8 and len(piece):
                piece = clip_poly(piece, 0, y0, False)
            if len(piece) >= 3 and abs(_poly_area(piece)) > 1e-3:
                pieces.append(piece)
            y = y1
    return pieces


def end_face(c: Ctx, ring_yz: np.ndarray, x: float, normal_x: float, style: HullStyle, holes=(), zo: float = 0.0, plate: bool = True) -> None:
    """The flat bow or stern face of a hull at x: the skin as convex pieces (holes left open), then plates on the rectangles that
    fit inside each piece. ring_yz: the section polygon (n,2) as (y, z); normal_x = +1 (bow) or -1 (stern)."""
    g, rng = c.g, c.rng
    poly = np.asarray(ring_yz, np.float64).copy()
    poly[:, 1] += zo
    for piece in face_pieces(poly, holes):
        cen = piece.mean(axis=0)
        V = np.column_stack([np.full(len(piece) + 1, x), np.vstack([piece, cen])])
        k = len(piece)
        F = np.stack([np.arange(k), (np.arange(k) + 1) % k, np.full(k, k)], axis=1)
        # orient to face along normal_x
        a_, b_, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        nx = np.cross(b_ - a_, c_ - a_)[:, 0]
        if np.sum(nx) * normal_x < 0:
            F = F[:, [0, 2, 1]]
        g.add(V, F, c.m("Frame"), a1=(0.0, 0.85), kind="skin")
        if not plate:
            continue
        # plates: a grid of rectangles that fit inside the piece (inset by a metre)
        y0, z0 = piece.min(axis=0)
        y1, z1 = piece.max(axis=0)
        if y1 - y0 < 4 or z1 - z0 < 3:
            continue
        zone = LF.PlanarZone((x, y0, z0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), y1 - y0, z1 - z0, normal=(normal_x, 0.0, 0.0))
        sch = LF.Scheme(row_w=(3.0, 6.0), plate_len=(6.0, 20.0), gap_a=(0.3, 0.5), gap_w=(0.3, 0.5), levels=(0.35, 0.55), level_weights=(0.6, 0.4),
                        chamfer=0.1, rim=0.25, embed=0.35, tone_sigma=style.scheme.tone_sigma, mats=style.scheme.mats, min_len=2.5)

        def inside(a0, a1, w0, w1, y0=y0, z0=z0, piece=piece, zone=zone):
            ys = [y0 + a0 - 0.8, y0 + a1 + 0.8]
            zs_ = [z0 + w0 * zone.width - 0.8, z0 + w1 * zone.width + 0.8]
            for yy in ys:
                for zz in zs_:
                    if not _point_in_convex(piece, yy, zz):
                        return True
            return False
        LF.plate_zone(g, zone, rng, sch, c.pre, skip=inside)


def _point_in_convex(poly: np.ndarray, y: float, z: float) -> bool:
    n = len(poly)
    sign = 0.0
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        cr = (b[0] - a[0]) * (z - a[1]) - (b[1] - a[1]) * (y - a[0])
        if abs(cr) < 1e-9:
            continue
        if sign == 0.0:
            sign = cr
        elif cr * sign < 0:
            return False
    return True
