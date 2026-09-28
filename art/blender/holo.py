"""Holographic tactical table props (AAstraHoloTable): icons, rings, disc, lines. Unit sizes, scaled at runtime.

  SM_HOLO_Ship     arrowhead ship icon, 1 m long along +X (bow), origin at its centre
  SM_HOLO_Unknown  octahedron for unidentified contacts, 1 m across
  SM_HOLO_Ring     range ring: torus, radius 1 m, tube 3 mm (scaled in X/Y only)
  SM_HOLO_Disc     projection disc, radius 1 m, planar UVs (0..1) for the grid material
  SM_HOLO_Line     unit line along +X from 0 to 1 m, 1 cm square section (velocity vectors, bearings)

blender -b --factory-startup --python-exit-code 1 -P art/blender/holo.py -- art/export/holo
"""
import math
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

MAT = "MI_ASTRA_Holo"


def new_object(name: str, bm: bmesh.types.BMesh) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(A.material(MAT))
    for p in obj.data.polygons:
        p.use_smooth = False
    return obj


def extrude_outline(bm, pts, z0, z1):
    """A closed XY outline extruded between z0 and z1 (caps + sides)."""
    bottom = [bm.verts.new((x, y, z0)) for x, y in pts]
    top = [bm.verts.new((x, y, z1)) for x, y in pts]
    bm.faces.new(list(reversed(bottom)))
    bm.faces.new(top)
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((bottom[i], bottom[j], top[j], top[i]))


def ship_icon():
    bm = bmesh.new()
    # arrowhead with a notched tail, plus a thin dorsal keel so the icon reads in 3D
    outline = [(0.5, 0.0), (-0.5, 0.26), (-0.28, 0.0), (-0.5, -0.26)]
    extrude_outline(bm, outline, -0.035, 0.035)
    keel = [(0.32, 0.0), (-0.34, 0.035), (-0.34, -0.035)]
    extrude_outline(bm, keel, 0.035, 0.11)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object("SM_HOLO_Ship", bm)


def unknown_icon():
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((0.5, 0, 0), (-0.5, 0, 0), (0, 0.5, 0), (0, -0.5, 0), (0, 0, 0.5), (0, 0, -0.5))]
    for a, b, c in ((0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)):
        bm.faces.new((v[a], v[b], v[c]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object("SM_HOLO_Unknown", bm)


def ring():
    bm = bmesh.new()      # torus by hand: 160 x 6
    n, m, R, r = 160, 6, 1.0, 0.003
    rows = []
    for i in range(n):
        a = 2 * math.pi * i / n
        ca, sa = math.cos(a), math.sin(a)
        row = []
        for j in range(m):
            b = 2 * math.pi * j / m
            rr = R + r * math.cos(b)
            row.append(bm.verts.new((rr * ca, rr * sa, r * math.sin(b))))
        rows.append(row)
    for i in range(n):
        for j in range(m):
            i2, j2 = (i + 1) % n, (j + 1) % m
            bm.faces.new((rows[i][j], rows[i2][j], rows[i2][j2], rows[i][j2]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object("SM_HOLO_Ring", bm)


def disc():
    bm = bmesh.new()
    n = 96
    centre = bm.verts.new((0, 0, 0))
    rim = [bm.verts.new((math.cos(2 * math.pi * k / n), math.sin(2 * math.pi * k / n), 0)) for k in range(n)]
    for k in range(n):
        bm.faces.new((centre, rim[k], rim[(k + 1) % n]))
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            x, y, _ = loop.vert.co
            loop[uv].uv = (x * 0.5 + 0.5, y * 0.5 + 0.5)
    return new_object("SM_HOLO_Disc", bm)


def line():
    bm = bmesh.new()
    h = 0.005
    extrude_outline(bm, [(0, -h), (1.0, -h), (1.0, h), (0, h)], -h, h)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return new_object("SM_HOLO_Line", bm)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/holo"
    A.reset_scene()
    for build in (ship_icon, unknown_icon, ring, disc, line):
        obj = build()
        A.export_fbx(obj, os.path.join(out_dir, f"{obj.name}.fbx"))
        print(obj.name, len(obj.data.vertices), "verts")


if __name__ == "__main__":
    main()
