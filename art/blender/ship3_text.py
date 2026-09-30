"""ASTRA ships v3 — lettering and emblems as real geometry (hull numbers, names, stencils, the ASTRA Navy star, the Mandate's
ferry mark). Barlow Condensed (OFL, docs/licenze.csv) is turned into meshes by Blender's own text object once per string, cached,
and placed with the same instancing as everything else, so lettering stays crisp at any zoom. Nothing here is a texture.

Frames: text runs along the local +x, its up is +y, and it stands out of the surface along +z (`text_frame` builds that from a
surface normal). Prototypes are centred on x and y with their back on z = 0.
"""
from __future__ import annotations

import math
import os

import numpy as np

import ship3_geo as G

FONT_CANDIDATES = [
    "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts/BarlowCondensed-SemiBold.ttf",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_downloads", "fonts", "BarlowCondensed-SemiBold.ttf"),
]
_CACHE: dict = {}


def text_frame(normal, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    """Rows (x = reading direction, y = up on the surface, z = the normal), so the text reads left to right from outside."""
    n = G.norm(normal)
    u = np.asarray(up, np.float64)
    ey = u - n * float(np.dot(u, n))
    if np.linalg.norm(ey) < 1e-6:
        ey = np.array([1.0, 0.0, 0.0]) - n * n[0]
    ey = G.norm(ey)
    ex = np.cross(ey, n)
    return np.stack([ex, ey, n])


def _font_path() -> str | None:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def text_proto(text: str, depth: float = 0.03, res: int = 2) -> dict:
    """{"V","F"} of the text 1 m tall (cap height ~0.7), centred, back at z = 0, front at z = depth. Needs Blender."""
    key = (text, round(depth, 4), res)
    if key in _CACHE:
        return _CACHE[key]
    import bpy

    fc = bpy.data.curves.new("ship3_txt", "FONT")
    fc.body = text
    fp = _font_path()
    if fp:
        fc.font = bpy.data.fonts.load(fp)
    fc.size = 1.0
    fc.extrude = depth / 2.0
    fc.resolution_u = res
    fc.bevel_resolution = 0
    fc.align_x = "CENTER"
    fc.align_y = "CENTER"
    ob = bpy.data.objects.new("ship3_txt", fc)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    n = len(me.vertices)
    co = np.empty(n * 3, np.float32)
    me.vertices.foreach_get("co", co)
    V = co.reshape(-1, 3).astype(np.float64)
    me.calc_loop_triangles()
    nt = len(me.loop_triangles)
    tri = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tri)
    F = tri.reshape(-1, 3)
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(fc)
    bpy.data.meshes.remove(me)
    V[:, 2] += depth / 2.0
    # drop the back faces (they sit on the hull): triangles lying flat at z = 0
    zmax = V[:, 2].max()
    flat_back = np.all(V[F][:, :, 2] < 1e-6, axis=1)
    F = F[~flat_back]
    proto = {"V": V, "F": F, "mat": "Marking", "a1": np.tile([0.3, 0.0], (len(V), 1)), "a2": np.tile([G.TONE0, 0.0], (len(V), 1)),
             "width": float(V[:, 0].max() - V[:, 0].min()), "height": float(V[:, 1].max() - V[:, 1].min())}
    _CACHE[key] = proto
    return proto


def place_text(g: G.Geo, text: str, origin, normal, height: float, mat: str, up=(0.0, 0.0, 1.0), depth: float = 0.03, lift: float = 0.0,
               kind: str = "text") -> float:
    """Letters of `height` metres standing on the surface at `origin` (the middle of the text). Returns the width in metres."""
    pr = text_proto(text, depth=depth / max(height, 1e-6))
    n = G.norm(normal)
    g.instance(pr, [np.asarray(origin, np.float64) + n * lift], text_frame(normal, up), scales=height, mat=mat, kind=kind)
    return pr["width"] * height


def astra_emblem(g: G.Geo, origin, normal, diameter: float, mat: str, up=(0.0, 0.0, 1.0), lift: float = 0.0, depth: float = 0.05) -> None:
    """The ASTRA Navy emblem in relief: an eight-pointed compass star (long points N/E/S/W, short ones between) in a double ring
    (proportions of tools/art/signage.py)."""
    fr = text_frame(normal, up)
    o = np.asarray(origin, np.float64) + G.norm(normal) * lift
    r = diameter / 2.0
    for ri, ro in ((0.90 * r, 0.97 * r), (0.58 * r, 0.63 * r)):
        g.revolve([(ri, 0.0), (ro, 0.0), (ro, depth), (ri, depth), (ri, 0.0)], mat, origin=o, frame=fr, seg=48, wear=0.3, kind="emblem")
    radii = {0: 0.72 * r, 2: 0.40 * r}
    pts = [(radii.get(k % 4, 0.11 * r) * math.sin(2 * math.pi * k / 16), radii.get(k % 4, 0.11 * r) * math.cos(2 * math.pi * k / 16))
           for k in range(16)]
    g.prism(np.array(pts), depth, mat, origin=o, frame=fr, chamfer=0.0, wear=0.3, kind="emblem", cap_bottom=False)


def mandate_mark(g: G.Geo, origin, normal, diameter: float, mat: str, up=(0.0, 0.0, 1.0), lift: float = 0.0, depth: float = 0.06) -> None:
    """The Kharon Mandate's mark: the ferryman's coin, a ring with a diagonal oar (shaft and leaf blade) over two lines of waves."""
    fr = text_frame(normal, up)
    o = np.asarray(origin, np.float64) + G.norm(normal) * lift
    r = diameter / 2.0
    g.revolve([(0.84 * r, 0.0), (r, 0.0), (r, depth), (0.84 * r, depth), (0.84 * r, 0.0)], mat, origin=o, frame=fr, seg=40, wear=0.5, kind="emblem")

    def bar(p, q, w):
        p, q = np.asarray(p, np.float64) * r, np.asarray(q, np.float64) * r
        d = q - p
        L = float(np.linalg.norm(d))
        th = math.atan2(d[1], d[0])
        cs, sn = math.cos(th), math.sin(th)
        frame = np.stack([cs * fr[0] + sn * fr[1], -sn * fr[0] + cs * fr[1], fr[2]])
        mid = o + fr[0] * (p[0] + q[0]) / 2 + fr[1] * (p[1] + q[1]) / 2 + fr[2] * depth / 2
        g.box(mid, (L, w * r, depth), mat, frame=frame, chamfer=0.0, wear=0.5, kind="emblem")

    p0, p1, p2 = np.array([-0.52, 0.52]), np.array([0.36, -0.30]), np.array([0.64, -0.56])
    bar(p0, p1, 0.085)                                                                   # the oar's shaft
    ax = (p2 - p1) / np.linalg.norm(p2 - p1)
    nx = np.array([-ax[1], ax[0]])                                                       # the leaf blade: a kite round the axis
    kite = np.array([p1 + nx * 0.07, p1 + (p2 - p1) * 0.40 + nx * 0.19, p2, p1 + (p2 - p1) * 0.40 - nx * 0.19, p1 - nx * 0.07]) * r
    g.prism(kite, depth, mat, origin=o, frame=fr, chamfer=0.0, wear=0.5, kind="emblem", cap_bottom=False)
    for y0 in (-0.30, -0.52):                                                            # two lines of waves
        pts = [(-0.64 + 0.16 * k, y0 + (0.11 if k % 2 else 0.0)) for k in range(5)]
        for a, b in zip(pts[:-1], pts[1:]):
            bar(a, b, 0.065)
