"""ASN Aquila interior kit (ARTE-INTERNI): the shapes that boxes and cylinders cannot make — rounded boxes, plump cushions, turned (lathe) pieces, leaves, rolled
edges. Every function builds into an FB / SFB (one of the groups of an SParts: `b.soft` for cushions and leaves, `b.body` for hard parts) in the CURRENT local frame of
that builder, so it composes with `place(...)` and `b.at(frame(...))` like the older primitives. Sizes in metres.

  rbox(fb, lo, hi, r, mat, seg)      a box with every edge rounded to radius r (a cushion, a table top, a rolled arm)
  puff(fb, c, half, mat, e)          a superellipsoid: a plump pillow / seat pad / bean (e 1 = ellipsoid, 0.3 = nearly a box)
  lathe(fb, profile, c, mat, seg)    a solid turned about the vertical axis through c: profile = [(radius, z) ...] from the bottom up
  leaf(fb, base, d, up, ...)         one leaf blade of real geometry (two-sided, a folded midrib, a droop), with the UVs of a leaf-atlas tile
  rod(fb, p0, p1, r0, r1, mat)       a tapered round rod (legs, stems)
  stitch_line(...)                   a thin seam line on a cushion (a dark groove)
"""
from __future__ import annotations

import math
import random

from mathutils import Matrix, Vector

from bridge3_lib import FB


def sgnpow(x: float, p: float) -> float:
    return math.copysign(abs(x) ** p, x) if x else 0.0


# ------------------------------------------------------------------------------------------------------------------- stacked rings
def stack(fb: FB, rings, mat: str, cap_bottom: bool = True, cap_top: bool = True, closed: bool = True):
    """Faces between consecutive rings of local points (every ring lists its points counter-clockwise seen from above, the rings go upwards): outward-facing quads, flat caps. The
    winding is set here (reversed when the builder's frame mirrors), so no normal recalculation is needed. Returns the faces."""
    vr = [[fb.bm.verts.new(fb.P(p)) for p in ring] for ring in rings]
    idx = fb.mi(mat)
    flip = fb.frame.determinant() < 0
    faces = []

    def face(vs):
        vs = list(reversed(vs)) if flip else vs
        try:
            f = fb.bm.faces.new(vs)
        except ValueError:
            return
        f.material_index = idx
        faces.append(f)
    n = len(rings[0])
    span = n if closed else n - 1
    for k in range(len(vr) - 1):
        for i in range(span):
            j = (i + 1) % n
            face((vr[k][i], vr[k][j], vr[k + 1][j], vr[k + 1][i]))
    if cap_bottom:
        face(list(reversed(vr[0])))
    if cap_top:
        face(list(vr[-1]))
    return faces


# ------------------------------------------------------------------------------------------------------------------- rounded box
def _rounded_rect(hx: float, hy: float, rho: float, seg: int, cx: float = 0.0, cy: float = 0.0):
    """Points of a rounded rectangle (half-sizes hx, hy, corner radius rho, seg + 1 points per corner), counter-clockwise from the +x side, centred at (cx, cy)."""
    rho = max(min(rho, hx - 1e-5, hy - 1e-5), 1e-5)
    pts = []
    for (sx, sy, a0) in ((1, 1, 0.0), (-1, 1, 90.0), (-1, -1, 180.0), (1, -1, 270.0)):
        ccx, ccy = sx * (hx - rho), sy * (hy - rho)
        for k in range(seg + 1):
            a = math.radians(a0 + 90.0 * k / seg)
            pts.append((cx + ccx + rho * math.cos(a), cy + ccy + rho * math.sin(a)))
    return pts


def rbox(fb: FB, lo, hi, r: float, mat: str, seg: int = 3, rot: Matrix | None = None):
    """A box lo..hi with all twelve edges rounded to radius `r` (clamped to a third of the shortest side), `seg` segments per edge: rings of rounded rectangles stepped up the
    sides (the Minkowski sum of a smaller box and a sphere). A closed solid. `rot` turns it about its own centre."""
    size = [abs(b - a) for a, b in zip(lo, hi)]
    r = max(0.0005, min(r, min(size) / 2.2))
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    th_max = math.radians(84.0)
    rings = []
    angles = [th_max * k / seg for k in range(seg, -1, -1)]               # bottom arc: from the cap upwards to the equator
    for sgn in (-1, 1):
        for th in (angles if sgn < 0 else list(reversed(angles))):
            e = r * math.cos(th)
            ring = _rounded_rect(hx - r + e, hy - r + e, e if e > 1e-4 else 1e-4, seg)
            z = sgn * (hz - r + r * math.sin(th) / math.sin(th_max))
            rings.append((ring, z))
    rot3 = rot if rot is not None else Matrix.Identity(4)
    pts = []
    for ring, z in rings:
        q = []
        for (x, y) in ring:
            p = rot3 @ Vector((x, y, z))
            q.append((c[0] + p.x, c[1] + p.y, c[2] + p.z))
        pts.append(q)
    return stack(fb, pts, mat)


def cbox_r(fb: FB, center, size, r: float, mat: str, seg: int = 3, rot: Matrix | None = None):
    """rbox by centre and size."""
    lo = [c - s / 2 for c, s in zip(center, size)]
    hi = [c + s / 2 for c, s in zip(center, size)]
    return rbox(fb, lo, hi, r, mat, seg, rot)


# --------------------------------------------------------------------------------------------------------------------------- puff
def puff(fb: FB, center, half, mat: str, e: float = 0.45, nu: int = 16, nv: int = 9, rot: Matrix | None = None, flat_bottom: float = 0.0):
    """A superellipsoid centred at `center` with half-extents `half` = (hx, hy, hz): the shape of a seat pad, a pillow, a bean bag. `e` is the exponent of the roundness
    (1 = ellipsoid, small = box-like with rounded edges). `flat_bottom` (0..1) flattens the underside (a cushion that sits on something). A closed solid."""
    hx, hy, hz = half
    rings = []
    rot3 = rot if rot is not None else Matrix.Identity(4)
    for k in range(1, nv):
        v = -math.pi / 2 + math.pi * k / nv
        zz = sgnpow(math.sin(v), e) * hz
        if flat_bottom > 0.0 and zz < 0.0:
            zz *= (1.0 - flat_bottom)
        rr = abs(math.cos(v)) ** e
        ring = []
        for j in range(nu):
            u = 2 * math.pi * j / nu
            p = rot3 @ Vector((sgnpow(math.cos(u), e) * rr * hx, sgnpow(math.sin(u), e) * rr * hy, zz))
            ring.append((center[0] + p.x, center[1] + p.y, center[2] + p.z))
        rings.append(ring)
    return stack(fb, rings, mat)


# ---------------------------------------------------------------------------------------------------------------------- lathe
def lathe(fb: FB, profile, center, mat: str, seg: int = 18, caps: bool = True, scale=(1.0, 1.0)):
    """A solid of revolution about the vertical axis through `center` (x, y, z0): `profile` = [(radius, z above z0)] from the bottom up (the first and last radius > 0 close with a
    flat cap). `scale` = (sx, sy) squashes the section (an oval pot)."""
    rings = []
    cx, cy, cz = center
    for (r, z) in profile:
        rings.append([(cx + math.cos(2 * math.pi * j / seg) * r * scale[0], cy + math.sin(2 * math.pi * j / seg) * r * scale[1], cz + z) for j in range(seg)])
    return stack(fb, rings, mat, caps, caps)


# ----------------------------------------------------------------------------------------------------------------------- rods
def rod(fb: FB, p0, p1, r0: float, r1: float, mat: str, seg: int = 8):
    """A tapered round rod from p0 (radius r0) to p1 (radius r1)."""
    return fb.cyl(p0, p1, r0, mat, seg=seg, r2=r1)


# ------------------------------------------------------------------------------------------------------------------------ leaves
def leaf(fb: FB, base, d, up, length: float, width: float, mat: str, tile: int = 0, droop: float = 0.25, fold: float = 0.12, cup: float = 0.0,
         nu: int = 5, nv: int = 3, twist: float = 0.0, shape: float = 0.85, tip: float = 0.0, thick: float = 0.0006, wave: float = 0.0, seed: int = 0,
         backface: bool = False):
    """A leaf blade of real geometry, two-sided (a top and a bottom skin 1.2 mm apart), from `base` (local) growing along the unit direction `d`; `up` is the blade's upper side at the
    base. The outline is a pointed oval (`shape` = how full it is: 0.5 narrow, 1 round), the midrib folds the two halves up by `fold` (V section), `droop` bends the blade down
    along its length (a fraction of its length at the tip), `cup` rolls the margins up, `twist` turns it about its own axis (degrees over its length), `wave` ruffles the margin
    (lettuce). `backface=True` adds the lower skin (the plants' leaf materials are two-sided in the engine: no need). `tile` picks the leaf kind in the 2 x 2 atlas T_LeafAtlas (0 broadleaf, 1 lettuce / herb, 2 grass / leek, 3 tomato). `nu` x `nv`: samples along / across the half
    blade. Returns (the top faces).
    The UVs are the tile's: u across the blade, v along it; the faces carry the custom-UV flag, so the builder's box projection leaves them alone."""
    rng = random.Random(seed)
    b = Vector(base)
    d = Vector(d).normalized()
    up = (Vector(up) - d * Vector(up).dot(d))
    if up.length < 1e-6:
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    up.normalize()
    w = d.cross(up).normalized()
    pts_top, pts_bot, uvs = [], [], []
    nvf = 2 * nv + 1
    for i in range(nu + 1):
        s = i / nu
        hw = 0.5 * width * (math.sin(math.pi * min(1.0, s ** shape * (1.0 if tip == 0.0 else 1.0))) ** 0.8) * (1.0 - 0.2 * s) if s < 1.0 else 0.0
        if s < 0.04:
            hw = max(hw, 0.5 * width * 0.05)
        row_t, row_b = [], []
        ang = math.radians(twist) * s
        ca, sa = math.cos(ang), math.sin(ang)
        for j in range(nvf):
            t = -1.0 + 2.0 * j / (nvf - 1)
            lateral = t * hw
            lift = fold * abs(lateral) + cup * lateral * lateral / max(width, 1e-3)
            if wave:
                lift += wave * math.sin(s * 11.0 + t * 3.0 + seed) * abs(t) * hw
            drop = -droop * length * s * s
            # the blade's local frame: forward d, across w, up `up`; the twist turns w/up about d
            wx = w * ca + up * sa
            uy = up * ca - w * sa
            p = b + d * (length * s) + wx * lateral + uy * (lift + drop)
            tilt = uy
            row_t.append(p + tilt * (thick / 2))
            row_b.append(p - tilt * (thick / 2))
            u0 = 0.5 + t * 0.5 * (hw / max(0.5 * width, 1e-6))
            uvs.append((u0, s))
        pts_top.append(row_t)
        pts_bot.append(row_b)
    # tile UV offsets: tile k at column k % 2, row k // 2 (image rows count from the top)
    col, row = tile % 2, tile // 2
    uoff, voff = 0.5 * col, 1.0 - 0.5 * (row + 1)
    verts_t = [[fb.bm.verts.new(fb.P(p)) for p in r] for r in pts_top]
    verts_b = [[fb.bm.verts.new(fb.P(p)) for p in r] for r in pts_bot]
    idx = fb.mi(mat)
    faces = []
    uv_layer = fb.uv
    mirrored = fb.frame.determinant() < 0
    for i in range(nu):
        for j in range(nvf - 1):
            for side, verts in (((0, verts_t), (1, verts_b)) if backface else ((0, verts_t),)):
                quad = [verts[i][j], verts[i][j + 1], verts[i + 1][j + 1], verts[i + 1][j]]
                uv = [uvs[i * nvf + j], uvs[i * nvf + j + 1], uvs[(i + 1) * nvf + j + 1], uvs[(i + 1) * nvf + j]]
                # the last row collapses to the tip: drop the degenerate quad edge
                if i == nu - 1:
                    quad = [quad[0], quad[1], quad[2]] if j >= 0 else quad
                    uv = [uv[0], uv[1], uv[2]]
                top_front = (side == 0) != mirrored            # the top skin's front faces `up`; the frame mirrors y: flip
                order = list(range(len(quad))) if top_front else list(reversed(range(len(quad))))
                try:
                    f = fb.bm.faces.new([quad[k] for k in order])
                except ValueError:
                    continue
                f.material_index = idx
                f[fb.cu] = 1
                for loop, k in zip(f.loops, order):
                    u, v = uv[k]
                    loop[uv_layer].uv = (uoff + 0.5 * u, voff + 0.5 * v)
                if side == 0:
                    faces.append(f)
    return faces


def stitch_line(fb: FB, p0, p1, mat: str, r: float = 0.0035):
    """A thin dark groove line on a soft surface (a cushion's seam): a flat round rod just proud of the surface."""
    return fb.cyl(p0, p1, r, mat, seg=5)
