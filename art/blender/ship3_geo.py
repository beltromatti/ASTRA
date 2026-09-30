"""ASTRA ships v3 — the numpy geometry engine.

Everything the ship generators draw goes through `Geo`: chunks of triangles (vertices, faces, a material slot per face, two
per-vertex data pairs) accumulated in numpy and turned into one Blender mesh at the very end (ship3_build.py). Nothing here
needs bpy or bmesh, so a ship of two million triangles builds in seconds.

Frame: Blender's, metres, +X the bow, +Z up, +Y to port (the FBX export mirrors Y: Unreal's starboard is Blender's -Y).

Per-vertex data (exported as the mesh's 2nd and 3rd UV sets, read by the hull materials; zero is neutral):
  A1 = (wear, grime)   wear: 0..1, 1 = paint chipped down to bare metal (edges, rims, corners); grime: 0..1, 1 = a deep
                       recess (seam floors, wall bases): darkens and roughens.
  A2 = (tone, aux)     tone: 0..1, 0.5 = the paint's own tone (each plate is painted a little lighter or darker);
                       aux: soot (hull materials) | window id (light materials) | colour code (nav lights).
The first UV set is a metric box projection (1 unit = 8 m) anchored per face on an 8 m lattice: neighbours line up and the
values stay small (Unreal keeps UVs as half floats).

Chunks flagged `split` are cut triangle by triangle when a ship is split into sections; the others go whole to the section
that holds their centre. `cap` chunks exist only in the section pieces (the burnt cut faces), never in the whole ship.
"""
from __future__ import annotations

import math

import numpy as np

F32 = np.float32
I32 = np.int32
TONE0 = 0.5


# ------------------------------------------------------------------------------------------------- small linear algebra
def norm(v, eps: float = 1e-12) -> np.ndarray:
    v = np.asarray(v, np.float64)
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, eps)


def frame_x(ex, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Orthonormal right-handed frame (rows ex, ey, ez) with ex given; ez as close to `up` as possible."""
    ex = norm(ex)
    up = np.asarray(up, np.float64)
    if abs(float(np.dot(ex, up))) > 0.98:
        up = np.array([0.0, 1.0, 0.0]) if abs(ex[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    ey = norm(np.cross(up, ex))
    ez = np.cross(ex, ey)
    return np.stack([ex, ey, ez])


def frame_z(ez, ex_hint=(1.0, 0.0, 0.0)) -> np.ndarray:
    """Frame with ez given (a surface normal) and ex as close to `ex_hint` as possible."""
    ez = norm(ez)
    h = np.asarray(ex_hint, np.float64)
    ex = h - ez * float(np.dot(h, ez))
    if np.linalg.norm(ex) < 1e-6:
        h = np.array([0.0, 1.0, 0.0])
        ex = h - ez * float(np.dot(h, ez))
    ex = norm(ex)
    ey = np.cross(ez, ex)
    return np.stack([ex, ey, ez])


def frames_z(ez, ex_hint=(1.0, 0.0, 0.0)) -> np.ndarray:
    """Vectorised frame_z for (n,3) normals -> (n,3,3)."""
    ez = norm(np.atleast_2d(ez))
    h = np.broadcast_to(np.asarray(ex_hint, np.float64), ez.shape)
    ex = h - ez * np.sum(h * ez, axis=-1, keepdims=True)
    bad = np.linalg.norm(ex, axis=-1) < 1e-6
    if bad.any():
        h2 = np.array([0.0, 1.0, 0.0])
        ex[bad] = h2 - ez[bad] * np.sum(h2 * ez[bad], axis=-1, keepdims=True)
    ex = norm(ex)
    ey = np.cross(ez, ex)
    return np.stack([ex, ey, ez], axis=1)


def rot_z(ang: float) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])   # rows: images of the basis under a +ang turn about z ... (local @ R)


def rot_axis(axis, ang: float) -> np.ndarray:
    """Rotation about a unit axis as a row-basis matrix (use as `local @ R`): rows are the rotated x, y, z axes."""
    a = norm(axis)
    c, s = math.cos(ang), math.sin(ang)
    x, y, z = a
    m = np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
                  [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
                  [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)]])
    return m.T


def quads_to_tris(q) -> np.ndarray:
    q = np.asarray(q, I32).reshape(-1, 4)
    return np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]], axis=0) if len(q) else np.zeros((0, 3), I32)


def strip_quads(n: int, off_a: int, off_b: int, closed: bool = True) -> np.ndarray:
    """Quads (a_i, a_j, b_j, b_i) between two loops (or polylines) of n points starting at index offsets off_a and off_b."""
    i = np.arange(n if closed else n - 1)
    j = (i + 1) % n
    return np.stack([off_a + i, off_a + j, off_b + j, off_b + i], axis=1).astype(I32)


def orient_convex(V: np.ndarray, F: np.ndarray, center) -> np.ndarray:
    """Flip the triangles of a convex (star-shaped) solid so that all of them point away from `center`."""
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    n = np.cross(b - a, c - a)
    cen = (a + b + c) / 3.0 - np.asarray(center)
    flip = np.sum(n * cen, axis=1) < 0
    F = F.copy()
    F[flip] = F[flip][:, [0, 2, 1]]
    return F


# --------------------------------------------------------------------------------------------------------- chamfered box
def _box_template():
    """A chamfered box in sign space. Every template vertex is (sign triple S, inset flags I): the world position is
    centre + (S * (half - I * chamfer)) . frame. Faces first (24 vertices, 6 quads: x-, x+, y-, y+, z-, z+), then the twelve
    edge chamfer quads and the eight corner triangles. No vertex is shared between polygons: flat shading."""
    S, I, Q, T = [], [], [], []

    def vert(s, inset):
        S.append(s)
        I.append(inset)
        return len(S) - 1

    for a in range(3):
        b, c = [x for x in range(3) if x != a]
        for sa in (-1, 1):
            ids = []
            for sb, sc in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                s = [0, 0, 0]
                s[a], s[b], s[c] = sa, sb, sc
                inset = [0, 0, 0]
                inset[b] = inset[c] = 1
                ids.append(vert(s, inset))
            Q.append(ids)
    for a, b in ((0, 1), (0, 2), (1, 2)):
        c = 3 - a - b
        for sa in (-1, 1):
            for sb in (-1, 1):
                pa, pb = [], []
                for sc in (-1, 1):
                    s = [0, 0, 0]
                    s[a], s[b], s[c] = sa, sb, sc
                    ia = [0, 0, 0]
                    ia[b] = ia[c] = 1                     # a point on face a's edge (a full, b and c pulled in)
                    ib = [0, 0, 0]
                    ib[a] = ib[c] = 1                     # the matching point on face b's edge
                    pa.append(vert(s, ia))
                    pb.append(vert(s, ib))
                Q.append([pa[0], pa[1], pb[1], pb[0]])
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                ids = []
                for k in range(3):
                    inset = [1, 1, 1]
                    inset[k] = 0
                    ids.append(vert([sx, sy, sz], inset))
                T.append(ids)
    return np.array(S, np.float64), np.array(I, np.float64), np.array(Q, I32), np.array(T, I32)


_BOX_S, _BOX_I, _BOX_Q, _BOX_T = _box_template()
_BOX_NV = len(_BOX_S)
_BOX_UNIT = _BOX_S * (1.0 - _BOX_I * 0.2)
_BOX_TRIS = orient_convex(_BOX_UNIT, np.concatenate([quads_to_tris(_BOX_Q), _BOX_T], axis=0), np.zeros(3))   # 12 face, 24 chamfer, 8 corner tris
_BOX_PLAIN_TRIS = orient_convex(_BOX_UNIT, quads_to_tris(_BOX_Q[:6]), np.zeros(3))
_BOX_TRI_FACE = np.concatenate([np.repeat(np.arange(6), 2), np.full(len(_BOX_TRIS) - 12, -1)])
_BOX_ISFACE = np.arange(_BOX_NV) < 24


class Geo:
    """Accumulates triangle chunks; see the module docstring for the per-vertex data."""

    def __init__(self, mats: list[str]):
        self.mats = list(mats)
        self._mi = {m: i for i, m in enumerate(self.mats)}
        self.chunks: list[dict] = []
        self.cuts: list[float] | None = None          # x of the section cuts, bow first
        self.keepouts: list[tuple[np.ndarray, np.ndarray]] = []
        self.notes: dict = {}

    # ---------------------------------------------------------------------------------------------- bookkeeping
    def mi(self, name) -> int:
        if isinstance(name, (int, np.integer)):
            return int(name)
        if name not in self._mi:
            self._mi[name] = len(self.mats)
            self.mats.append(name)
        return self._mi[name]

    def keep_out(self, lo, hi) -> None:
        """A box where placed details must not go (the bridge footprint, an interior, the hangar mouths)."""
        self.keepouts.append((np.asarray(lo, np.float64), np.asarray(hi, np.float64)))

    def blocked(self, lo, hi, margin: float = 0.0) -> bool:
        lo = np.asarray(lo, np.float64) - margin
        hi = np.asarray(hi, np.float64) + margin
        for a, b in self.keepouts:
            if np.all(lo <= b) and np.all(hi >= a):
                return True
        if self.cuts:
            for xc in self.cuts:
                if lo[0] - 1.0 <= xc <= hi[0] + 1.0:
                    return True
        return False

    def add(self, V, F, mat, a1=(0.0, 0.0), a2=(TONE0, 0.0), uv=None, kind: str = "", split: bool = False,
            cap: bool = False) -> None:
        V = np.ascontiguousarray(V, F32)
        F = np.ascontiguousarray(F, I32)
        if len(F) == 0:
            return
        n = len(V)
        a1 = np.ascontiguousarray(np.broadcast_to(np.asarray(a1, F32), (n, 2)))
        a2 = np.ascontiguousarray(np.broadcast_to(np.asarray(a2, F32), (n, 2)))
        if np.ndim(mat) == 0:
            mat = np.full(len(F), self.mi(mat), np.int16)
        else:
            mat = np.asarray(mat, np.int16)
        self.chunks.append({"V": V, "F": F, "mat": mat, "a1": a1, "a2": a2, "uv": None if uv is None else np.ascontiguousarray(uv, F32),
                            "kind": kind, "split": split, "cap": cap})

    # ---------------------------------------------------------------------------------------------- boxes
    def boxes(self, centers, half, mat, frames=None, chamfer=0.04, wear=0.85, grime=0.0, tone=TONE0, aux=0.0, kind: str = "box",
              face_mats=None, cap: bool = False, a1_all=None) -> None:
        """Chamfered boxes, vectorised: centers (n,3), half sizes (n,3) or (3,), frames (n,3,3) or (3,3) (rows = axes).
        wear: on the chamfer bands (the faces are clean). face_mats: optional 6 materials for x-, x+, y-, y+, z-, z+;
        tone/aux may be arrays of length n."""
        centers = np.atleast_2d(np.asarray(centers, np.float64))
        n = len(centers)
        half = np.broadcast_to(np.asarray(half, np.float64), (n, 3))
        fr = np.broadcast_to(np.eye(3) if frames is None else np.asarray(frames, np.float64), (n, 3, 3))
        c = np.broadcast_to(np.asarray(chamfer, np.float64), (n,))
        c = np.minimum(c, 0.45 * half.min(axis=1))
        use_ch = bool(np.any(c > 1e-6))
        nv = _BOX_NV if use_ch else 24
        tris = _BOX_TRIS if use_ch else _BOX_PLAIN_TRIS
        S, I = _BOX_S[:nv], _BOX_I[:nv]
        loc = S[None] * (half[:, None, :] - I[None] * c[:, None, None])
        V = centers[:, None, :] + np.einsum("nvk,nkj->nvj", loc, fr)
        F = (tris[None] + (np.arange(n) * nv)[:, None, None]).reshape(-1, 3)
        if face_mats is not None:
            fm = np.array([self.mi(m) for m in face_mats], np.int16)
            base = self.mi(mat)
            per = np.where(_BOX_TRI_FACE[:len(tris)] >= 0, fm[np.maximum(_BOX_TRI_FACE[:len(tris)], 0)], base).astype(np.int16)
            M = np.tile(per, n)
        else:
            M = np.full(len(F), self.mi(mat), np.int16)
        a1 = np.zeros((nv, 2), F32)
        a1[:, 0] = np.where(_BOX_ISFACE[:nv], 0.0, wear)
        a1[:, 1] = grime
        A1 = np.tile(a1, (n, 1))
        if a1_all is not None:
            A1[:] = np.asarray(a1_all, F32)
        A2 = np.zeros((n, nv, 2), F32)
        A2[..., 0] = np.reshape(np.asarray(tone, F32), (-1, 1)) if np.ndim(tone) else tone
        A2[..., 1] = np.reshape(np.asarray(aux, F32), (-1, 1)) if np.ndim(aux) else aux
        self.add(V.reshape(-1, 3), F, M, A1, A2.reshape(-1, 2), kind=kind, cap=cap)

    def box(self, center, size, mat, frame=None, chamfer=0.04, **kw) -> None:
        """One chamfered box; size = full extents along the frame's axes."""
        self.boxes(np.asarray(center, np.float64)[None], np.asarray(size, np.float64) / 2.0, mat,
                   None if frame is None else np.asarray(frame)[None], chamfer, **kw)

    def box_between(self, p0, p1, width, height, mat, up=(0.0, 0.0, 1.0), chamfer=0.03, **kw) -> None:
        """A beam from p0 to p1 with a width x height section (girders, rails, struts)."""
        p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
        d = p1 - p0
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            return
        self.box((p0 + p1) / 2, (L, width, height), mat, frame=frame_x(d, up), chamfer=chamfer, **kw)

    # ---------------------------------------------------------------------------------------------- prisms, cylinders
    def prism(self, poly, height, mat, origin=(0.0, 0.0, 0.0), frame=None, chamfer=0.0, taper=1.0, wear=0.85, grime=0.0,
              tone=TONE0, aux=0.0, cap_bottom: bool = True, kind: str = "prism", cap: bool = False, a1_all=None) -> None:
        """A convex polygon (k,2) in the local xy plane extruded along local +z by `height`. The top is narrowed by `taper`
        (a frustum) and chamfered by `chamfer` (one more ring pulled in). Wall vertices are shared around: smooth by angle."""
        poly = np.asarray(poly, np.float64)
        k = len(poly)
        c0 = poly.mean(axis=0)
        rel = poly - c0
        ch = min(chamfer, height * 0.45, 0.45 * np.linalg.norm(rel, axis=1).min() * max(taper, 1e-3))
        rings = [(rel, 0.0, 0.0, grime)]
        if ch > 1e-6:
            top = rel * taper
            r = np.linalg.norm(top, axis=1, keepdims=True)
            rings.append((top, height - ch, wear * 0.9, 0.0))
            rings.append((top * np.maximum(0.0, 1.0 - ch / np.maximum(r, 1e-6)), height, wear, 0.0))
        else:
            rings.append((rel * taper, height, wear * 0.6, 0.0))
        Vs = [np.column_stack([ring + c0, np.full(k, z)]) for ring, z, _, _ in rings]
        A1 = [np.column_stack([np.full(k, w), np.full(k, g)]) for _, _, w, g in rings]
        F = [quads_to_tris(strip_quads(k, i * k, (i + 1) * k)) for i in range(len(rings) - 1)]
        ci = len(rings) * k
        Vs.append(np.array([[c0[0], c0[1], rings[-1][1]]]))
        A1.append(np.array([[0.0, 0.0]]))
        tl = (len(rings) - 1) * k
        F.append(np.stack([np.arange(k) + tl, (np.arange(k) + 1) % k + tl, np.full(k, ci)], axis=1).astype(I32))
        if cap_bottom:
            Vs.append(np.array([[c0[0], c0[1], 0.0]]))
            A1.append(np.array([[0.0, grime]]))
            F.append(np.stack([(np.arange(k) + 1) % k, np.arange(k), np.full(k, ci + 1)], axis=1).astype(I32))
        V = np.concatenate(Vs)
        F = np.concatenate(F)
        fr = np.eye(3) if frame is None else np.asarray(frame, np.float64)
        Vw = np.asarray(origin, np.float64) + V @ fr
        F = orient_convex(Vw, F, Vw.mean(axis=0))
        A1 = np.concatenate(A1)
        if a1_all is not None:
            A1[:] = np.asarray(a1_all, F32)
        self.add(Vw, F, mat, A1, np.array([tone, aux], F32), kind=kind, cap=cap)

    def cylinder(self, p0, p1, r0, r1, mat, seg: int = 16, chamfer: float = 0.0, cap_bottom: bool = True, wear: float = 0.8,
                 grime: float = 0.0, tone=TONE0, aux=0.0, kind: str = "cyl", cap: bool = False, rot: float = 0.0, a1_all=None) -> None:
        """A cylinder / cone between two points (radius r0 at p0, r1 at p1), optionally chamfered at the p1 end."""
        p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
        d = p1 - p0
        L = float(np.linalg.norm(d))
        if L < 1e-6 or r0 < 1e-6:
            return
        fr = frame_z(d / L, (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 * L else (0.0, 1.0, 0.0))
        a = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False) + rot
        poly = np.column_stack([np.cos(a), np.sin(a)]) * r0
        self.prism(poly, L, mat, origin=p0, frame=fr, chamfer=chamfer, taper=r1 / r0, wear=wear, grime=grime, tone=tone, aux=aux,
                   cap_bottom=cap_bottom, kind=kind, cap=cap, a1_all=a1_all)

    def cylinders(self, p0, p1, radius, mat, seg: int = 8, tone=TONE0, aux=0.0, wear=0.5, kind: str = "cyl", cap: bool = False) -> None:
        """Many plain cylinders at once (pipes, bolts, whips, struts): p0, p1 (n,3), radius (n,) or scalar. Capped both ends."""
        p0 = np.atleast_2d(np.asarray(p0, np.float64))
        p1 = np.atleast_2d(np.asarray(p1, np.float64))
        d = p1 - p0
        L = np.linalg.norm(d, axis=1)
        ok = L > 1e-6
        if not ok.any():
            return
        p0, p1, d, L = p0[ok], p1[ok], d[ok], L[ok]
        n = len(p0)
        rad = np.broadcast_to(np.asarray(radius, np.float64), (len(ok),))[ok]
        ez = d / L[:, None]
        hint = np.where(np.abs(ez[:, 2:3]) < 0.98, np.array([[0.0, 0.0, 1.0]]), np.array([[1.0, 0.0, 0.0]]))
        ex = norm(np.cross(hint, ez))
        ey = np.cross(ez, ex)
        a = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False)
        ring = np.stack([np.cos(a), np.sin(a)], axis=1)[None] * rad[:, None, None]          # (n,seg,2)
        off = ring[..., 0:1] * ex[:, None, :] + ring[..., 1:2] * ey[:, None, :]
        V = np.concatenate([p0[:, None, :] + off, p1[:, None, :] + off], axis=1)              # (n, 2seg, 3)
        wall = quads_to_tris(strip_quads(seg, 0, seg))
        fan = np.stack([np.zeros(seg - 2, I32), np.arange(1, seg - 1, dtype=I32), np.arange(2, seg, dtype=I32)], axis=1)
        one = np.concatenate([wall, fan[:, [0, 2, 1]], fan + seg])          # bottom cap faces -ez, top cap +ez (fan is ccw about +ez)
        Fl = (one[None] + (np.arange(n) * 2 * seg)[:, None, None]).reshape(-1, 3)
        Vf = V.reshape(-1, 3)
        cen = V.mean(axis=1)
        owner = Fl[:, 0] // (2 * seg)
        a_, b_, c_ = Vf[Fl[:, 0]], Vf[Fl[:, 1]], Vf[Fl[:, 2]]
        flip = np.sum(np.cross(b_ - a_, c_ - a_) * ((a_ + b_ + c_) / 3 - cen[owner]), axis=1) < 0
        Fl[flip] = Fl[flip][:, [0, 2, 1]]
        A1 = np.zeros((len(Vf), 2), F32)
        A1[:, 0] = wear
        self.add(Vf, Fl, mat, A1, np.array([tone, aux], F32), kind=kind, cap=cap)

    def revolve(self, profile, mat, origin=(0.0, 0.0, 0.0), frame=None, seg: int = 24, wear=0.6, grime=0.0, tone=TONE0, aux=0.0,
                kind: str = "rev", cap: bool = False, flip: bool = False, wear_profile=None, a1_all=None) -> None:
        """A surface of revolution about local z: profile = [(r, z), ...] from bottom to top (r = 0 on the axis is allowed at
        the ends). Wall vertices are shared around and between rings: sharp profile corners are found by smooth-by-angle."""
        prof = np.asarray(profile, np.float64)
        n = len(prof)
        a = np.linspace(0.0, 2.0 * math.pi, seg, endpoint=False)
        Vs = np.zeros((n, seg, 3))
        Vs[..., 0] = prof[:, 0:1] * np.cos(a)[None]
        Vs[..., 1] = prof[:, 0:1] * np.sin(a)[None]
        Vs[..., 2] = prof[:, 1:2]
        F = np.concatenate([quads_to_tris(strip_quads(seg, i * seg, (i + 1) * seg)) for i in range(n - 1)])
        fr = np.eye(3) if frame is None else np.asarray(frame, np.float64)
        Vw = np.asarray(origin, np.float64) + Vs.reshape(-1, 3) @ fr
        a_, b_, c_ = Vw[F[:, 0]], Vw[F[:, 1]], Vw[F[:, 2]]
        F = F[np.linalg.norm(np.cross(b_ - a_, c_ - a_), axis=1) > 1e-10]
        # orientation: the profile runs bottom to top; a face is outward when its normal has a positive component along the
        # outward normal of the profile edge it belongs to. For an increasing profile in z the outward normal in (r,z) is (dz,-dr)
        ring_of = F[:, 0] // seg
        ring_of = np.minimum(ring_of, n - 2)
        dr = prof[ring_of + 1, 0] - prof[ring_of, 0]
        dz = prof[ring_of + 1, 1] - prof[ring_of, 1]
        # world outward direction of that face: radial * dz - axis * dr (then the frame)
        a_, b_, c_ = Vw[F[:, 0]], Vw[F[:, 1]], Vw[F[:, 2]]
        cen = (a_ + b_ + c_) / 3.0
        rad = cen - (np.asarray(origin, np.float64) + fr[2] * np.sum((cen - np.asarray(origin, np.float64)) * fr[2], axis=1, keepdims=True))
        rad = norm(rad)
        want = rad * dz[:, None] - fr[2][None] * dr[:, None]
        bad = np.sum(np.cross(b_ - a_, c_ - a_) * want, axis=1) < 0
        if flip:
            bad = ~bad
        F[bad] = F[bad][:, [0, 2, 1]]
        wv = np.full(n, wear) if wear_profile is None else np.asarray(wear_profile, np.float64)
        A1 = np.zeros((n, seg, 2), F32)
        A1[..., 0] = wv[:, None]
        A1[..., 1] = grime
        if a1_all is not None:
            A1[:] = np.asarray(a1_all, F32)
        self.add(Vw, F, mat, A1.reshape(-1, 2), np.array([tone, aux], F32), kind=kind, cap=cap)

    def dome(self, center, radius, mat, frame=None, seg: int = 16, rings: int = 5, squash: float = 1.0, wear=0.4, tone=TONE0, aux=0.0,
             kind: str = "dome") -> None:
        """A hemisphere (local +z up) on a flat base at `center`."""
        t = np.linspace(0.0, 1.0, rings + 1) * (math.pi / 2)
        prof = [(radius * math.cos(x), radius * squash * math.sin(x)) for x in t]
        prof[-1] = (0.0, prof[-1][1])
        self.revolve(prof, mat, origin=center, frame=frame, seg=seg, wear=wear, tone=tone, aux=aux, kind=kind)

    def quad(self, P, mat, uv=None, a1=(0.0, 0.0), a2=(TONE0, 0.0), kind: str = "quad", both: bool = False) -> None:
        """A flat quad (4,3), counter-clockwise seen from the front, optionally with explicit UVs (4,2)."""
        F = quads_to_tris([[0, 1, 2, 3]])
        if both:
            F = np.concatenate([F, F[:, [0, 2, 1]]])
        self.add(np.asarray(P, np.float64), F, mat, a1, a2, uv=uv, kind=kind)

    def mesh(self, V, F, mat, **kw) -> None:
        self.add(V, F, mat, **kw)

    # ---------------------------------------------------------------------------------------------- instancing
    def instance(self, proto: dict, positions, frames=None, scales=None, mat=None, tone=None, aux=None, kind: str = "inst",
                 cap: bool = False) -> None:
        """Many copies of a prototype: positions (n,3), frames (n,3,3) or (3,3) with rows = the local axes, scales scalar or (n,)
        or (n,3). Prototype: {"V": (m,3), "F": (t,3), "mat": name or list of names per face, "a1": (m,2), "a2": (m,2)}.
        `mat` overrides every face's slot; tone/aux override the per-vertex values (scalar or per instance)."""
        P = np.atleast_2d(np.asarray(positions, np.float64))
        n = len(P)
        if n == 0:
            return
        V0 = np.asarray(proto["V"], np.float64)
        m = len(V0)
        R = np.broadcast_to(np.eye(3) if frames is None else np.asarray(frames, np.float64), (n, 3, 3))
        if scales is None:
            S = np.ones((n, 1, 3))
        else:
            s = np.asarray(scales, np.float64)
            S = np.broadcast_to(s.reshape(1, 1, 1), (n, 1, 3)) if s.ndim == 0 else (
                np.broadcast_to(s.reshape(-1, 1, 1), (n, 1, 3)) if s.ndim == 1 else s.reshape(n, 1, 3))
        V = P[:, None, :] + np.einsum("nvk,nkj->nvj", V0[None] * S, R)
        F0 = np.asarray(proto["F"], I32)
        F = (F0[None] + (np.arange(n) * m)[:, None, None]).reshape(-1, 3)
        matf = proto["mat"]
        if mat is not None:
            M = np.full(len(F), self.mi(mat), np.int16)
        elif isinstance(matf, str):
            M = np.full(len(F), self.mi(matf), np.int16)
        else:
            M = np.tile(np.array([self.mi(x) for x in matf], np.int16), n)
        A1 = np.tile(np.asarray(proto.get("a1", np.zeros((m, 2))), F32), (n, 1))
        a2p = np.asarray(proto.get("a2", np.tile([TONE0, 0.0], (m, 1))), F32)
        A2 = np.tile(a2p[None], (n, 1, 1)).copy()
        if tone is not None:
            A2[..., 0] = np.reshape(np.asarray(tone, F32), (-1, 1)) if np.ndim(tone) else tone
        if aux is not None:
            A2[..., 1] = np.reshape(np.asarray(aux, F32), (-1, 1)) if np.ndim(aux) else aux
        self.add(V.reshape(-1, 3), F, M, A1, A2.reshape(-1, 2), kind=kind, cap=cap)

    # ---------------------------------------------------------------------------------------------- statistics
    def triangles(self, cap: bool | None = None) -> int:
        return int(sum(len(c["F"]) for c in self.chunks if cap is None or c["cap"] == cap))

    def stats(self) -> dict:
        out: dict = {}
        for c in self.chunks:
            k = c["kind"] or "?"
            out[k] = out.get(k, 0) + len(c["F"])
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    def bounds(self):
        lo = np.min([c["V"].min(axis=0) for c in self.chunks if not c["cap"]], axis=0)
        hi = np.max([c["V"].max(axis=0) for c in self.chunks if not c["cap"]], axis=0)
        return lo, hi

    # ---------------------------------------------------------------------------------------------- assembly
    def assemble(self, sections=None, include_caps: bool = False, section_of=None):
        """Concatenate the chunks into flat arrays. sections: keep only the chunks whose section id is in the set; section_of
        maps an array of x to section ids (`split` chunks are decided per triangle, the others by their vertex centre).
        include_caps adds the pieces-only cap chunks (and, when `sections` is given, only those of the wanted sections)."""
        Vs, Fs, Ms, A1s, A2s = [], [], [], [], []
        uv_over = []                                   # (first triangle, per-corner UVs) of chunks with their own UVs
        off = 0
        tri_pos = 0
        wanted = None if sections is None else list(sections)
        for c in self.chunks:
            if c["cap"] and not include_caps:
                continue
            V, F, mat = c["V"], c["F"], c["mat"]
            if wanted is not None:
                if c["split"]:
                    tc = V[F].mean(axis=1)[:, 0]
                    keep = np.isin(section_of(tc), wanted)
                    F, mat = F[keep], mat[keep]
                    if len(F) == 0:
                        continue
                else:
                    sec = c.get("sec")
                    if sec is None:
                        sec = int(section_of(np.array([float(V[:, 0].mean())]))[0])
                    if sec not in wanted:
                        continue
            if c["uv"] is not None:
                uv_over.append((tri_pos, c["uv"][F]))
            Vs.append(V)
            Fs.append(F + off)
            Ms.append(mat)
            A1s.append(c["a1"])
            A2s.append(c["a2"])
            off += len(V)
            tri_pos += len(F)
        if not Vs:
            return None
        return {"V": np.concatenate(Vs), "F": np.concatenate(Fs), "M": np.concatenate(Ms), "A1": np.concatenate(A1s),
                "A2": np.concatenate(A2s), "uv_over": uv_over}


def box_uv(V: np.ndarray, F: np.ndarray, texel_m: float = 8.0, lattice: float = 8.0) -> np.ndarray:
    """Per-corner metric box-projection UVs, shape (len(F), 3, 2): the dominant axis of the face normal picks the plane;
    u and v are the two other coordinates relative to the face centre snapped down to a `lattice` grid, in units of texel_m."""
    a, b, c = V[F[:, 0]].astype(np.float64), V[F[:, 1]].astype(np.float64), V[F[:, 2]].astype(np.float64)
    n = np.cross(b - a, c - a)
    ax = np.argmax(np.abs(n), axis=1)
    origin = np.floor((a + b + c) / 3.0 / lattice) * lattice
    P = np.stack([a, b, c], axis=1) - origin[:, None, :]
    ua = np.array([1, 0, 0])[ax]
    va = np.array([2, 2, 1])[ax]
    rows = np.arange(len(F))[:, None]
    cols = np.arange(3)[None, :]
    return np.stack([P[rows, cols, ua[:, None]], P[rows, cols, va[:, None]]], axis=-1) / texel_m
