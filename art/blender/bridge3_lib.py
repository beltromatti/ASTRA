"""ASN Aquila bridge v3: geometry toolkit for Blender (headless). Used by bridge_v3.py.

Conventions (docs/STILE.md §11, art/blender/astra_bpy.py):
- every builder works in LAYOUT coordinates: the local frame of a prop is (x forward, y right/starboard, z up), metres,
  exactly the Unreal frame of data/ship/aquila_bridge.json. The base frame of every FB mirrors y on the way out
  (layout -> Blender), so the FBX export lands on the data in Unreal (the same U() convention as bridge.py v2);
- the *front* of an open face is decided by an explicit `facing` vector (local coordinates), closed solids are oriented
  by Blender (recalc_face_normals): no winding bookkeeping in the modelling code;
- material slots are the names of the Unreal instances (MI_ASTRA_*, MI_BRG3_*) or SCREEN_<station>_<n> for live screens;
- emissive details (light strips, buttons, indicators) share ONE slot (MI_BRG3_Lamps*) and pick their colour from a small
  palette texture by UV cell (T_BRG3_Lamps, made by tools/art/bridge3_textures.py); labels share the label atlas.
"""
from __future__ import annotations

import json
import math
import os
import random
import sys
from contextlib import contextmanager

import bmesh
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "art", "_cache", "bridge3")

# ---------------------------------------------------------------------------------------------------------- materials
STRUCT = A.MAT_STRUCTURE            # gunmetal structure
TRIM = A.MAT_TRIM                   # brushed metal
RUBBER = A.MAT_RUBBER               # dark rubber / cable jackets
LEATHER = "MI_BRG3_Leather"         # seat upholstery: black leather (T_LeatherBlack)
GLASS = A.MAT_GLASS                 # translucent window / rail glass (classic meshes only)
COMPOSITE = "MI_BRG3_Composite"     # dark composite wall/ceiling panels
IVORY = "MI_BRG3_Ivory"             # glossy ivory ceramic composite (console shells, chair shells)
DECK = "MI_BRG3_DeckPlate"          # gunmetal deck plating with a fine anti-slip grain
DGLASS = "MI_BRG3_DarkGlass"        # opaque black glass (lenses, the work surfaces around the live screens)
LAMP = "MI_BRG3_Lamps"              # emissive palette lamps (normal)
LAMP_DIM = "MI_BRG3_LampsDim"       # ... dim (floor channels, rails)
LAMP_HOT = "MI_BRG3_LampsHot"       # ... bright (cove strips, big light bars)
LABEL = "MI_BRG3_Labels"            # backlit label atlas
BRASS = "MI_BRG3_Brass"             # brushed brass: the warm accent line of the command deck (console rims, floor inlays, rails)  [ARTE-PLANCIA-2]
DECOR = "MI_BRG3_Decor"             # static display pages and soft glows (T_BRG3_Decor, tools/art/bridge3_decor.py)               [ARTE-PLANCIA-2]

SHARED_SLOTS = [STRUCT, TRIM, RUBBER, LEATHER, GLASS, COMPOSITE, IVORY, DECK, DGLASS, LAMP, LAMP_DIM, LAMP_HOT, LABEL, BRASS, DECOR]

# palette cells of T_BRG3_Lamps (8 x 8 cells of 8 x 8 px; image rows count from the top): name -> (col, row, sRGB, alert weight)
PALETTE = [
    # row 0: department accents, they turn to the alert colour and pulse in condition yellow / red
    ("command", "#3E7BFA", 1.0), ("engineering", "#FF9F1C", 1.0), ("flight", "#FFD60A", 1.0), ("science", "#9B5DE5", 1.0),
    ("security", "#E63946", 1.0), ("medical", "#2EC4B6", 1.0), ("white_cool", "#EAF4FF", 0.85), ("white_warm", "#FFE2B4", 0.85),
    # row 1: fixed indicators (they never change with the alert)
    ("green", "#50DC96", 0.0), ("amber", "#FFB347", 0.0), ("red", "#FF4A2E", 0.0), ("cyan", "#6FC3FF", 0.0),
    ("blue", "#3E7BFA", 0.0), ("white", "#FFFFFF", 0.0), ("ice", "#BFD9EA", 0.0), ("violet", "#B57BFF", 0.0),
    # row 2: guide lights (respond a little to the alert)
    ("guide", "#BFE6FF", 0.6), ("guide_warm", "#FFC680", 0.6), ("cool_dim", "#7FB6E6", 0.6), ("warm_dim", "#C98A45", 0.6),
    ("command_dim", "#2A57B5", 1.0), ("engineering_dim", "#B8701A", 1.0), ("flight_dim", "#B89A08", 1.0), ("science_dim", "#6E40A6", 1.0),
    # row 3: dim variants
    ("security_dim", "#9C2530", 1.0), ("medical_dim", "#1F8177", 1.0), ("red_dim", "#A8301F", 0.0), ("green_dim", "#2E9968", 0.0),
    ("amber_dim", "#B87E2D", 0.0), ("cyan_dim", "#4A8CB8", 0.0), ("white_dim", "#9AA6B0", 0.0), ("ice_dim", "#7F97AA", 0.0),
]
PAL_INDEX = {name: i for i, (name, _c, _a) in enumerate(PALETTE)}


def cell_uv(name: str) -> tuple[float, float]:
    i = PAL_INDEX[name]
    col, row = i % 8, i // 8
    return ((col + 0.5) / 8.0, 1.0 - (row + 0.5) / 8.0)


DEPT_CELL = {"command": "command", "engineering": "engineering", "flight": "flight", "science": "science",
             "security": "security", "medical": "medical"}


# ---------------------------------------------------------------------------------------------------- frames / matrices
MIRROR = Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))


def T(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> Matrix:
    return Matrix.Translation((x, y, z))


def Rz(deg: float) -> Matrix:
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def Ry(deg: float) -> Matrix:
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def Rx(deg: float) -> Matrix:
    return Matrix.Rotation(math.radians(deg), 4, "X")


def frame(x: float = 0.0, y: float = 0.0, z: float = 0.0, yaw: float = 0.0, pitch: float = 0.0, roll: float = 0.0) -> Matrix:
    """Local frame at (x, y, z): yaw turns +x towards +y (starboard); pitch > 0 tips +x up; roll turns +y towards +z."""
    return T(x, y, z) @ Rz(yaw) @ Ry(-pitch) @ Rx(roll)


def V3(p) -> Vector:
    return p if isinstance(p, Vector) else Vector(p)


def lerp(a, b, t):
    return a + (b - a) * t


def polar(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    a = math.radians(deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


# ------------------------------------------------------------------------------------------------------- frame builder
class FB:
    """Frame builder: geometry described in layout coordinates inside a stack of local frames, emitted mirrored (Blender)."""

    def __init__(self) -> None:
        self.bm = bmesh.new()
        self.mats: list[str] = []
        self.uv = self.bm.loops.layers.uv.verify()
        self.cu = self.bm.faces.layers.int.new("custom_uv")
        self.frame = MIRROR.copy()
        self._stack: list[Matrix] = []
        self.rng = random.Random(7)

    # -- bookkeeping ----------------------------------------------------------------------------------------------
    def mi(self, name: str) -> int:
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    @contextmanager
    def at(self, m: Matrix):
        self._stack.append(self.frame)
        self.frame = self.frame @ m
        try:
            yield self
        finally:
            self.frame = self._stack.pop()

    def P(self, p) -> Vector:
        """Local point -> Blender space."""
        return self.frame @ V3(p)

    def N(self, d) -> Vector:
        """Local direction -> Blender space."""
        return (self.frame.to_3x3() @ V3(d)).normalized()

    def _faces_of(self, verts):
        return list({f for v in verts for f in v.link_faces})

    def _tag(self, faces, mat: str, solid: bool = True) -> list:
        idx = self.mi(mat)
        for f in faces:
            f.material_index = idx
        if solid:
            bmesh.ops.recalc_face_normals(self.bm, faces=faces)
        elif self.frame.determinant() < 0:
            bmesh.ops.reverse_faces(self.bm, faces=faces)      # open primitives keep their authored (outward) winding
        return faces

    # -- solids -----------------------------------------------------------------------------------------------------
    def cbox(self, center, size, mat: str, rot: Matrix | None = None):
        m = self.frame @ T(*center) @ (rot if rot is not None else Matrix.Identity(4)) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
        geom = bmesh.ops.create_cube(self.bm, size=1.0, matrix=m)
        return self._tag(self._faces_of(geom["verts"]), mat)

    def box(self, lo, hi, mat: str, rot: Matrix | None = None):
        c = [(a + b) / 2 for a, b in zip(lo, hi)]
        s = [abs(b - a) for a, b in zip(lo, hi)]
        return self.cbox(c, s, mat, rot)

    def cyl(self, p0, p1, r: float, mat: str, seg: int = 16, r2: float | None = None, caps: bool = True):
        a, b = V3(p0), V3(p1)
        d = b - a
        if d.length < 1e-9:
            return []
        rot = Vector((0.0, 0.0, 1.0)).rotation_difference(d.normalized()).to_matrix().to_4x4()
        m = self.frame @ T(*((a + b) / 2)) @ rot
        geom = bmesh.ops.create_cone(self.bm, cap_ends=caps, cap_tris=False, segments=seg, radius1=r,
                                     radius2=r if r2 is None else r2, depth=d.length, matrix=m)
        return self._tag(self._faces_of(geom["verts"]), mat, solid=caps)

    def sphere(self, center, r: float, mat: str, seg: int = 16, rings: int = 10, squash=(1.0, 1.0, 1.0)):
        m = self.frame @ T(*center) @ Matrix.Diagonal((r * squash[0], r * squash[1], r * squash[2], 1.0))
        geom = bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=rings, radius=1.0, matrix=m)
        return self._tag(self._faces_of(geom["verts"]), mat)

    def prism(self, poly, z0: float, z1: float, mat: str):
        """Vertical prism from a convex polygon [(x, y)] in the local frame."""
        lo = [self.bm.verts.new(self.P((x, y, z0))) for x, y in poly]
        hi = [self.bm.verts.new(self.P((x, y, z1))) for x, y in poly]
        faces = [self.bm.faces.new(lo), self.bm.faces.new(hi)]
        n = len(poly)
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
        return self._tag(faces, mat)

    def extrude_x(self, prof_yz, x0: float, x1: float, mat: str):
        """Convex or star-shaped (y, z) profile extruded along local x."""
        a = [self.bm.verts.new(self.P((x0, y, z))) for y, z in prof_yz]
        b = [self.bm.verts.new(self.P((x1, y, z))) for y, z in prof_yz]
        faces = [self.bm.faces.new(a), self.bm.faces.new(b)]
        n = len(prof_yz)
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((a[i], a[j], b[j], b[i])))
        return self._tag(faces, mat)

    def extrude_y(self, prof_xz, y0: float, y1: float, mat: str):
        """(x, z) side profile extruded across local y (console cross-sections)."""
        a = [self.bm.verts.new(self.P((x, y0, z))) for x, z in prof_xz]
        b = [self.bm.verts.new(self.P((x, y1, z))) for x, z in prof_xz]
        faces = [self.bm.faces.new(a), self.bm.faces.new(b)]
        n = len(prof_xz)
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((a[i], a[j], b[j], b[i])))
        return self._tag(faces, mat)

    def loft(self, rings, mat: str, caps: bool = True, closed: bool = True, loop: bool = False):
        """Rings of local points (equal counts) joined by quads; capped ends make a closed solid. `loop` joins the last ring
        to the first (a torus-like band, no caps); `closed=False` leaves the ring itself open (a strip)."""
        vr = [[self.bm.verts.new(self.P(p)) for p in ring] for ring in rings]
        faces = []
        n = len(rings[0])
        span = n if closed else n - 1
        nr = len(vr) if loop else len(vr) - 1
        for k in range(nr):
            k2 = (k + 1) % len(vr)
            for i in range(span):
                j = (i + 1) % n
                try:
                    faces.append(self.bm.faces.new((vr[k][i], vr[k][j], vr[k2][j], vr[k2][i])))
                except ValueError:
                    pass
        if caps and closed and not loop:
            for ring in (vr[0], vr[-1]):
                try:
                    faces.append(self.bm.faces.new(list(ring)))
                except ValueError:
                    pass
        return self._tag(faces, mat, solid=(closed and (caps or loop)))

    def arc_sweep(self, profile, cx: float, cy: float, radius: float, a0: float, a1: float, mat: str, seg: int = 12,
                  caps: bool = True, z0: float = 0.0, loop: bool = False):
        """(dr, z) profile swept about the vertical axis through (cx, cy): angles a0..a1 (degrees, from +x towards +y).
        `loop` closes a full circle (a0..a0+360) without caps."""
        rings = []
        n = seg if loop else seg + 1
        for k in range(n):
            a = math.radians(lerp(a0, a1, k / seg))
            ca, sa = math.cos(a), math.sin(a)
            rings.append([(cx + (radius + dr) * ca, cy + (radius + dr) * sa, z0 + z) for dr, z in profile])
        return self.loft(rings, mat, caps=caps, closed=True, loop=loop)

    def tube(self, pts, r: float, mat: str, seg: int = 8, caps: bool = True):
        """Circular tube along a polyline (cables, conduits); parallel-transported frame, mitred at the corners."""
        pts = [V3(p) for p in pts]
        if len(pts) < 2:
            return []
        tang = []
        for i in range(len(pts)):
            if i == 0:
                t = pts[1] - pts[0]
            elif i == len(pts) - 1:
                t = pts[-1] - pts[-2]
            else:
                t = (pts[i + 1] - pts[i]).normalized() + (pts[i] - pts[i - 1]).normalized()
            tang.append(t.normalized())
        ref = Vector((0, 0, 1)) if abs(tang[0].z) < 0.95 else Vector((1, 0, 0))
        u = tang[0].cross(ref).normalized()
        rings = []
        for i, p in enumerate(pts):
            v = tang[i].cross(u).normalized()
            u = v.cross(tang[i]).normalized()
            ring = []
            for k in range(seg):
                a = 2 * math.pi * k / seg
                ring.append(p + (u * math.cos(a) + v * math.sin(a)) * r)
            rings.append(ring)
        return self.loft(rings, mat, caps=caps)

    # -- open surfaces ------------------------------------------------------------------------------------------------
    def _orient(self, verts_b: list[Vector], facing) -> bool:
        """True when the polygon (Blender-space points, given order) already faces the local direction `facing`."""
        n = Vector()
        for i in range(len(verts_b)):
            a, b = verts_b[i], verts_b[(i + 1) % len(verts_b)]
            n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        return n.dot(self.N(facing)) >= 0.0

    def face(self, pts, mat: str, facing, uvs=None, flag: bool = False):
        """One polygon of local points; `facing` = local direction the front side must look towards."""
        vb = [self.P(p) for p in pts]
        order = list(range(len(pts)))
        if not self._orient(vb, facing):
            order.reverse()
        verts = [self.bm.verts.new(vb[i]) for i in order]
        f = self.bm.faces.new(verts)
        f.material_index = self.mi(mat)
        if uvs is not None:
            for loop, i in zip(f.loops, order):
                loop[self.uv].uv = uvs[i]
        if flag:
            f[self.cu] = 1
        return f

    def _basis_b(self, facing, up=(0, 0, 1)):
        """Viewer basis in Blender space for a surface facing the local direction `facing`: (front, right, up). The right vector
        is derived in Blender space (right-handed: right = look x up), so it is correct under any frame, mirrored ones included."""
        f = self.N(facing)
        u = self.N(up)
        u = (u - f * u.dot(f))
        if u.length < 1e-6:
            u = Vector((0, 0, 1)) if abs(f.z) < 0.9 else Vector((0, 1, 0))
        u.normalize()
        r = (-f).cross(u).normalized()
        return f, r, u

    def screen(self, center, w: float, h: float, slot: str, facing, up=(0, 0, 1), u_range=(0.0, 1.0), v_range=(0.0, 1.0),
               flag: bool = True):
        """A flat live screen / label: w x h centred at `center` (local), front side towards `facing`; `up` is the image's up
        direction; UVs run u = left -> right, v = bottom -> top as the viewer sees it."""
        f, r, u = self._basis_b(facing, up)
        c = self.P(center)
        bl, br = c - r * (w / 2) - u * (h / 2), c + r * (w / 2) - u * (h / 2)
        tr, tl = c + r * (w / 2) + u * (h / 2), c - r * (w / 2) + u * (h / 2)
        return self._quad_b([bl, br, tr, tl], slot, f, [(u_range[0], v_range[0]), (u_range[1], v_range[0]),
                                                        (u_range[1], v_range[1]), (u_range[0], v_range[1])], flag)

    def _quad_b(self, pts_b, mat: str, front_b, uvs, flag: bool = True):
        order = list(range(len(pts_b)))
        n = Vector()
        for i in range(len(pts_b)):
            a, b = pts_b[i], pts_b[(i + 1) % len(pts_b)]
            n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
        if n.dot(front_b) < 0:
            order.reverse()
        verts = [self.bm.verts.new(pts_b[i]) for i in order]
        f = self.bm.faces.new(verts)
        f.material_index = self.mi(mat)
        for loop, i in zip(f.loops, order):
            loop[self.uv].uv = uvs[i]
        if flag:
            f[self.cu] = 1
        return f

    def screen_seg(self, pa, pb, z0: float, z1: float, slot: str, facing, u_range=(0.0, 1.0), v_range=(0.0, 1.0)):
        """A vertical strip between two local points (x, y) from z0 to z1 (one segment of a curved screen); the end that is on
        the viewer's left gets u_range[0]."""
        f, r, u = self._basis_b(facing, (0, 0, 1))
        a0, b0 = self.P((pa[0], pa[1], z0)), self.P((pb[0], pb[1], z0))
        a1, b1 = self.P((pa[0], pa[1], z1)), self.P((pb[0], pb[1], z1))
        if (b0 - a0).dot(r) < 0:
            a0, b0, a1, b1 = b0, a0, b1, a1
        return self._quad_b([a0, b0, b1, a1], slot, f, [(u_range[0], v_range[0]), (u_range[1], v_range[0]),
                                                        (u_range[1], v_range[1]), (u_range[0], v_range[1])])

    def screen_arc(self, cx: float, cy: float, radius: float, a0: float, a1: float, z0: float, z1: float, slot: str,
                   inward: bool = True, seg: int = 24):
        """Curved live screen: a cylinder segment about the vertical axis through (cx, cy) between the angles a0 and a1
        (degrees, from +x towards +y, local frame); the picture faces the axis when `inward` (concave screens). The image's
        left edge is whichever end is on the viewer's left (decided from the facing), u runs left -> right, v bottom -> top."""
        pts = [polar(cx, cy, radius, lerp(a0, a1, k / seg)) for k in range(seg + 1)]
        mid = polar(cx, cy, radius, (a0 + a1) / 2)
        facing = (cx - mid[0], cy - mid[1], 0.0) if inward else (mid[0] - cx, mid[1] - cy, 0.0)
        _f, r, _u = self._basis_b(facing)
        flip = (self.P((*pts[-1], z0)) - self.P((*pts[0], z0))).dot(r) < 0     # a1 is on the viewer's left
        faces = []
        for k in range(seg):
            t0, t1 = k / seg, (k + 1) / seg
            u0, u1 = (1.0 - t0, 1.0 - t1) if flip else (t0, t1)
            pa, pb = pts[k], pts[k + 1]
            n_local = (cx - (pa[0] + pb[0]) / 2, cy - (pa[1] + pb[1]) / 2, 0.0)
            if not inward:
                n_local = (-n_local[0], -n_local[1], 0.0)
            quad = [self.P((*pa, z0)), self.P((*pb, z0)), self.P((*pb, z1)), self.P((*pa, z1))]
            faces.append(self._quad_b(quad, slot, self.N(n_local), [(u0, 0.0), (u1, 0.0), (u1, 1.0), (u0, 1.0)]))
        return faces

    # -- palette lamps and labels ---------------------------------------------------------------------------------------
    def _paint(self, faces, uvpair) -> None:
        for f in faces:
            f[self.cu] = 1
            for loop in f.loops:
                loop[self.uv].uv = uvpair

    def lamp_box(self, lo, hi, cell: str, mat: str = LAMP):
        faces = self.box(lo, hi, mat)
        self._paint(faces, cell_uv(cell))
        return faces

    def lamp_cbox(self, center, size, cell: str, mat: str = LAMP, rot=None):
        faces = self.cbox(center, size, mat, rot)
        self._paint(faces, cell_uv(cell))
        return faces

    def lamp_cyl(self, p0, p1, r: float, cell: str, mat: str = LAMP, seg: int = 12, r2: float | None = None):
        faces = self.cyl(p0, p1, r, mat, seg=seg, r2=r2)
        self._paint(faces, cell_uv(cell))
        return faces

    def lamp_face(self, pts, cell: str, facing, mat: str = LAMP):
        f = self.face(pts, mat, facing, flag=True)
        self._paint([f], cell_uv(cell))
        return f

    def lamp_arc(self, profile, cx, cy, radius, a0, a1, cell: str, mat: str = LAMP, seg: int = 12, z0: float = 0.0,
                 loop: bool = False):
        faces = self.arc_sweep(profile, cx, cy, radius, a0, a1, mat, seg=seg, z0=z0, loop=loop)
        self._paint(faces, cell_uv(cell))
        return faces

    def label(self, center, w: float, h: float, facing, cell: str, up=(0, 0, 1), atlas=None):
        """A decal-ready label plate (one quad) centred at `center`, w x h, front side towards `facing`; it uses the atlas rect
        of `cell` (u right, v up as the viewer sees it). `up` orients the image on floors and ceilings."""
        atlas = atlas if atlas is not None else LABELS
        cell = LABEL_TEXT.get(cell, cell)
        r = atlas.get(cell)
        if r is None:
            raise KeyError(f"label {cell!r} is not in the atlas")
        u0, v0, u1, v1 = r
        return self.screen(center, w, h, LABEL, facing, up=up, u_range=(u0, u1), v_range=(v0, v1))

    def decor(self, center, w: float, h: float, facing, page: str, up=(0, 0, 1)):
        """A quad showing one tile of the decor atlas (a static display page or a soft glow), w x h centred at `center`, front towards
        `facing`. The UV rect is pulled in by a texel so a neighbour's pixels never bleed in."""
        r = DECOR_RECTS.get(page)
        if r is None:
            raise KeyError(f"decor tile {page!r} is not in the atlas (tools/art/bridge3_decor.py)")
        u0, v0, u1, v1 = r
        du, dv = 0.75 / DECOR_SIZE[0], 0.75 / DECOR_SIZE[1]
        return self.screen(center, w, h, DECOR, facing, up=up, u_range=(u0 + du, u1 - du), v_range=(v0 + dv, v1 - dv))

    def decor_polar(self, F, page: str, r0: float, r1: float, a0: float, a1: float, lift: float = 0.0012, seg: int = 26, tile_a: float = 58.0,
                    tile_r=(0.50, 1.08)):
        """The silkscreen of a fan console's glass top: the polar tile `page` (tools/art/bridge3_decor.Polar: u = the angle from -tile_a to +tile_a,
        v = the radius from tile_r[0] to tile_r[1]) laid on the cone of the fan F between the radii r0..r1 and the angles a0..a1, `lift` m above it."""
        R = DECOR_RECTS[page]
        du0, dv0 = 0.75 / DECOR_SIZE[0], 0.75 / DECOR_SIZE[1]
        ua, ub, va, vb = R[0] + du0, R[2] - du0, R[1] + dv0, R[3] - dv0

        def uv(th, r):
            return (ua + (th + tile_a) / (2 * tile_a) * (ub - ua), va + (r - tile_r[0]) / (tile_r[1] - tile_r[0]) * (vb - va))

        faces = []
        front = self.N((0, 0, 1))
        for k in range(seg):
            t0, t1 = lerp(a0, a1, k / seg), lerp(a0, a1, (k + 1) / seg)
            pts = [self.P(F.pos(r0, t0, lift)), self.P(F.pos(r0, t1, lift)), self.P(F.pos(r1, t1, lift)), self.P(F.pos(r1, t0, lift))]
            faces.append(self._quad_b(pts, DECOR, front, [uv(t0, r0), uv(t1, r0), uv(t1, r1), uv(t0, r1)]))
        return faces

    def decor_strip(self, A, B, a0: float, a1: float, page: str, seg: int = 20, up_hint=(0, 0, 1), lift_out: float = 0.0):
        """A decor tile on a band that follows an arc: A and B are polar anchors (r, z) of the band's bottom and top edge, the band runs from the
        angle a0 to a1 (about the local vertical axis), its normal pointing at the axis side (towards the officer). The tile is stretched over the
        whole band, u left -> right as the officer sees it."""
        R = DECOR_RECTS[page]
        du, dv = 0.75 / DECOR_SIZE[0], 0.75 / DECOR_SIZE[1]
        ua, ub, va, vb = R[0] + du, R[2] - du, R[1] + dv, R[3] - dv
        faces = []
        for k in range(seg):
            t0, t1 = lerp(a0, a1, k / seg), lerp(a0, a1, (k + 1) / seg)
            c0, s0, c1, s1 = math.cos(math.radians(t0)), math.sin(math.radians(t0)), math.cos(math.radians(t1)), math.sin(math.radians(t1))
            ra, za, rb, zb = A[0] - lift_out, A[1], B[0] - lift_out, B[1]
            pts = [self.P((ra * c0, ra * s0, za)), self.P((ra * c1, ra * s1, za)), self.P((rb * c1, rb * s1, zb)), self.P((rb * c0, rb * s0, zb))]
            dr, dz = rb - ra, zb - za
            n_local = (-dz * math.cos(math.radians((t0 + t1) / 2)), -dz * math.sin(math.radians((t0 + t1) / 2)), dr)
            if n_local[0] * math.cos(math.radians((t0 + t1) / 2)) + n_local[1] * math.sin(math.radians((t0 + t1) / 2)) > 0:
                n_local = (-n_local[0], -n_local[1], -n_local[2])           # the face looks at the axis (the officer), whichever way A -> B runs
            faces.append(self._quad_b(pts, DECOR, self.N(n_local), [(ua + (ub - ua) * k / seg, va), (ua + (ub - ua) * (k + 1) / seg, va),
                                                                      (ua + (ub - ua) * (k + 1) / seg, vb), (ua + (ub - ua) * k / seg, vb)]))
        return faces

    def decor_fit(self, center, w: float, facing, page: str, up=(0, 0, 1)):
        """A decor tile of width w with its own aspect ratio (height = w / aspect)."""
        return self.decor(center, w, w / DECOR_ASPECT[page], facing, page, up=up)

    def text(self, text: str, center, height: float, facing, mat: str, up=(0, 0, 1), cell: str | None = None, tracking: float = 0.0,
             lift: float = 0.0, align: str = "center"):
        """Lettering as crisp flat geometry (Barlow Condensed turned into a mesh by Blender's own text object, cached per string): `height`
        is the cap height in metres, `center` the middle of the text (local frame), the letters face `facing` and read left to right as the
        viewer sees them (`up` is their up direction). With `cell` the faces are painted as a lamp (palette cell). Returns the width."""
        proto = text_proto(text)
        sc = height / proto["cap"]
        w = proto["width"] * sc + tracking * max(0, len(text) - 1)
        f, r, u = self._basis_b(facing, up)
        c = self.P(center) + f * lift
        if align == "left":
            c = c + r * (w / 2)
        elif align == "right":
            c = c - r * (w / 2)
        idx = self.mi(mat)
        faces = []
        # glyph positions: the proto is one string; tracking spreads the letters by shifting each vertex proportionally to its x
        x0, x1 = proto["x0"], proto["x1"]
        span = max(1e-6, x1 - x0)
        verts = []
        for (vx, vy, _vz) in proto["V"]:
            spread = tracking * (vx - x0) / span * max(0, len(text) - 1) if tracking else 0.0
            px = (vx - (x0 + x1) / 2) * sc + spread - (tracking * max(0, len(text) - 1)) / 2
            py = vy * sc
            verts.append(self.bm.verts.new(c + r * px + u * py))
        for a, b, d in proto["F"]:
            tri = [verts[a], verts[b], verts[d]]
            n = (tri[1].co - tri[0].co).cross(tri[2].co - tri[0].co)
            if n.dot(f) < 0:
                tri = [tri[0], tri[2], tri[1]]
            try:
                fc = self.bm.faces.new(tri)
            except ValueError:
                continue
            fc.material_index = idx
            faces.append(fc)
        if cell:
            self._paint(faces, cell_uv(cell))
        return w

    # -- output --------------------------------------------------------------------------------------------------------
    def to_object(self, name: str) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(mesh)
        self.bm.free()
        for m in self.mats:
            mesh.materials.append(A.material(m))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


LABELS: dict[str, tuple[float, float, float, float]] = {}
LABEL_TEXT: dict[str, str] = {}


def load_label_atlas() -> dict:
    """Label rects (u0, v0, u1, v1) from art/_cache/bridge3/labels.json (tools/art/bridge3_textures.py); a label can be asked
    for by its cell name (tag_03) or by its text ("COOLANT · LOOP 2")."""
    path = os.path.join(CACHE, "labels.json")
    LABELS.clear()
    LABEL_TEXT.clear()
    if not os.path.exists(path):
        raise RuntimeError(f"{path} missing: run  uv run --with pillow --with numpy python tools/art/bridge3_textures.py")
    data = json.load(open(path, encoding="utf-8"))
    for k, v in data["rects"].items():
        LABELS[k] = tuple(v)
    for group in ("tags", "small"):
        for cell, text in data.get(group, {}).items():
            LABEL_TEXT[text] = cell
    return LABELS


FONT_CANDIDATES = [os.path.join(ROOT, "art", "_downloads", "fonts", "BarlowCondensed-SemiBold.ttf"),
                   "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts/BarlowCondensed-SemiBold.ttf"]
_TEXT_CACHE: dict = {}


def text_proto(text: str) -> dict:
    """The mesh of a string in Barlow Condensed SemiBold (cap height ~0.7 of the font size; flat, one side): vertices (x right, y up, z 0),
    triangles, the width of the string in 'font size' units and the cap height of the font. Cached."""
    if text in _TEXT_CACHE:
        return _TEXT_CACHE[text]
    fc = bpy.data.curves.new("b3_txt", "FONT")
    fc.body = text
    for pth in FONT_CANDIDATES:
        if os.path.exists(pth):
            fc.font = bpy.data.fonts.load(pth)
            break
    fc.size = 1.0
    fc.extrude = 0.0
    fc.resolution_u = 3
    fc.align_x = "CENTER"
    fc.align_y = "CENTER"
    ob = bpy.data.objects.new("b3_txt", fc)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    me.calc_loop_triangles()
    V = [(v.co.x, v.co.y, v.co.z) for v in me.vertices]
    F = [tuple(t.vertices) for t in me.loop_triangles]
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(fc)
    bpy.data.meshes.remove(me)
    if not V:
        raise RuntimeError(f"text {text!r} produced no geometry")
    xs = [v[0] for v in V]
    ys = [v[1] for v in V]
    proto = {"V": V, "F": F, "width": max(xs) - min(xs), "height": max(ys) - min(ys), "cap": 0.70, "x0": min(xs), "x1": max(xs)}
    _TEXT_CACHE[text] = proto
    return proto


DECOR_RECTS: dict[str, tuple[float, float, float, float]] = {}
DECOR_ASPECT: dict[str, float] = {}
DECOR_SIZE = [2048.0, 4096.0]


def load_decor_atlas() -> dict:
    """Decor tile rects (u0, v0, u1, v1) from art/_cache/bridge3/decor.json (tools/art/bridge3_decor.py)."""
    path = os.path.join(CACHE, "decor.json")
    DECOR_RECTS.clear()
    DECOR_ASPECT.clear()
    if not os.path.exists(path):
        raise RuntimeError(f"{path} missing: run  uv run --with pillow --with numpy python tools/art/bridge3_textures.py --atlas-only")
    data = json.load(open(path, encoding="utf-8"))
    for k, v in data["rects"].items():
        DECOR_RECTS[k] = tuple(v)
    DECOR_ASPECT.update(data["aspect"])
    DECOR_SIZE[:] = [float(v) for v in data["size"]]
    return DECOR_RECTS


# ------------------------------------------------------------------------------------------------------ finishing helpers
class Parts:
    """A mesh made of several finishing groups (hard-surface body, fine detail, emissive/screens, soft parts).
    b = Parts(); b.body.box(...); b.emit.lamp_box(...); obj = b.build('SM_X')."""

    def __init__(self, bevel: float = 0.008, fine_bevel: float = 0.003, angle: float = 35.0) -> None:
        self.angle = angle
        self.body = FB()
        self.fine = FB()
        self.emit = FB()
        self.soft = FB()
        self.bevel = bevel
        self.fine_bevel = fine_bevel
        self.soft_bevel = 0.0
        self.bevel_segments = 2

    @contextmanager
    def at(self, m: Matrix):
        """Enter the local frame `m` in every group at once (bodies, fine detail, soft parts, emissive parts)."""
        with self.body.at(m), self.fine.at(m), self.soft.at(m), self.emit.at(m):
            yield self

    def build(self, name: str, uv_meter: float = 1.0, small_uv_meter: float | None = None) -> bpy.types.Object:
        """Bevel and shade each group, box-project the UVs (1 UV unit = `uv_meter` metres: 1.0 walls, 0.5 consoles, 0.25 seats; the `fine` and `soft`
        groups, the small hardware, use `small_uv_meter` when it is given: the materials' grain is then finer on small parts), join. Faces with their own UVs
        (lamps, labels, screens) are left alone."""
        objs = []
        for tag, fb, bev in (("body", self.body, self.bevel), ("fine", self.fine, self.fine_bevel), ("soft", self.soft, self.soft_bevel),
                             ("emit", self.emit, 0.0)):
            if len(fb.bm.faces) == 0:
                fb.bm.free()
                continue
            n_faces = len(fb.bm.faces)
            o = fb.to_object(f"{name}_{tag}")
            if bev > 0:
                A.bevel_and_normals(o, width=bev, segments=self.bevel_segments, angle_deg=self.angle)
            if os.environ.get("BRG3_DEBUG_TRIS"):
                print(f"    [{name}_{tag}] {n_faces} faces authored -> {tri_count(o)} tris after finishing")
            A.box_uv(o, texel_m=small_uv_meter if (small_uv_meter and tag in ("fine", "soft")) else uv_meter)
            if tag == "soft":                                      # cushions and other organic parts: smooth shading
                bpy.ops.object.select_all(action="DESELECT")
                o.select_set(True)
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
            objs.append(o)
        if not objs:
            raise RuntimeError(f"{name}: empty mesh")
        return A.join(objs, name)


def apply_subsurf(obj: bpy.types.Object, levels: int = 2) -> None:
    A.subsurf(obj, levels)


def tri_count(obj) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)
