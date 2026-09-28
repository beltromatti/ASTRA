"""Landmarks of the Aurelia system seen from the Aquila (docs/BIBBIA.md): the Janus Gate, an alien ring found under
the ice of Europa's twin gates in 2140 — 16 km across, a dark segmented torus with twelve pylons and faint glyph lines.

  SM_JANUS_Gate      ring in the Y-Z plane (its axis along +X), radius 8 km, origin at the centre
  SM_JANUS_LaneRing  one marker of the gate's approach lane: a dashed hoop of light, radius 1.5 km, in the Y-Z plane
                     (drawn with the additive glow material at runtime: exported apart, imported without Nanite)

blender -b --factory-startup --python-exit-code 1 -P art/blender/landmarks.py -- art/export/landmarks
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

HULL = "MI_JANUS_Hull"
GLYPH = "MI_JANUS_Glyph"


def torus(bm, R, r, n, m, mat_index, z_scale=1.0):
    rows = []
    for i in range(n):
        a = 2 * math.pi * i / n
        row = []
        for j in range(m):
            b = 2 * math.pi * j / m
            rr = R + r * math.cos(b)
            # ring in the Y-Z plane: x is the ring's axis
            row.append(bm.verts.new((r * math.sin(b) * z_scale, rr * math.cos(a), rr * math.sin(a))))
        rows.append(row)
    for i in range(n):
        for j in range(m):
            f = bm.faces.new((rows[i][j], rows[(i + 1) % n][j], rows[(i + 1) % n][(j + 1) % m], rows[i][(j + 1) % m]))
            f.material_index = mat_index


def gate():
    b = A.Builder()
    bm = b.bm
    hull = b.mi(HULL)
    glyph = b.mi(GLYPH)
    R = 8000.0
    torus(bm, R, 420.0, 192, 12, hull, z_scale=1.6)          # the main ring, flattened along its axis
    torus(bm, R - 330.0, 60.0, 192, 6, glyph)                # inner glyph band (glows)
    torus(bm, R + 330.0, 45.0, 192, 6, glyph)                # outer glyph band
    # twelve pylons: massive wedges standing out of the ring
    for k in range(12):
        a = 2 * math.pi * k / 12
        m = (Matrix.Rotation(a, 4, "X") @ Matrix.Translation((0.0, R, 0.0)) @ Matrix.Diagonal((1400.0, 1500.0, 700.0, 1.0)))
        geom = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
        b._assign(geom["verts"], HULL)
        m2 = (Matrix.Rotation(a, 4, "X") @ Matrix.Translation((0.0, R - 700.0, 0.0)) @ Matrix.Diagonal((1500.0, 120.0, 520.0, 1.0)))
        geom = bmesh.ops.create_cube(bm, size=1.0, matrix=m2)
        b._assign(geom["verts"], GLYPH)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = b.to_object("SM_JANUS_Gate")
    for p in obj.data.polygons:
        p.use_smooth = True
    A.box_uv(obj, texel_m=400.0)
    return obj


def lane_ring():
    """36 arcs of a hoop (radius 1.5 km, a 14 m glowing tube): the lane's standing waves, the path into the ring."""
    b = A.Builder()
    bm = b.bm
    glyph = b.mi(GLYPH)
    R, r, dashes, fill, n_arc, m = 1500.0, 14.0, 36, 0.62, 10, 6
    for d in range(dashes):
        a0 = 2 * math.pi * d / dashes
        rows = []
        for i in range(n_arc + 1):
            a = a0 + 2 * math.pi / dashes * fill * i / n_arc
            row = []
            for j in range(m):
                t = 2 * math.pi * j / m
                rr = R + r * math.cos(t)
                row.append(bm.verts.new((r * math.sin(t), rr * math.cos(a), rr * math.sin(a))))
            rows.append(row)
        for i in range(n_arc):
            for j in range(m):
                f = bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][(j + 1) % m], rows[i][(j + 1) % m]))
                f.material_index = glyph
        for row, flip in ((rows[0], True), (rows[-1], False)):     # cap the dash ends
            f = bm.faces.new(list(reversed(row)) if flip else row)
            f.material_index = glyph
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = b.to_object("SM_JANUS_LaneRing")
    for p in obj.data.polygons:
        p.use_smooth = True
    A.box_uv(obj, texel_m=50.0)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/landmarks"
    A.reset_scene()
    obj = gate()
    A.export_fbx(obj, os.path.join(out, "SM_JANUS_Gate.fbx"))
    print("LANDMARKS_OK", A.stats(obj))
    A.reset_scene()
    ring = lane_ring()
    A.export_fbx(ring, os.path.join(out + "_fx", "SM_JANUS_LaneRing.fbx"))
    print("LANE_RING_OK", A.stats(ring))


if __name__ == "__main__":
    main()
