"""ASTRA ships v3 — from the numpy geometry (ship3_geo.Geo) to a Blender object, and out to FBX.

The mesh has three UV sets: UVMap (metric box projection, the textures), UVMap_D1 (wear, grime) and UVMap_D2 (tone, aux); see
ship3_geo. Sharp edges come from smooth-by-angle, so Unreal gets one normal per corner exactly as Blender shades it.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship3_geo as G  # noqa: E402

UV_NAMES = ("UVMap", "UVMap_D1", "UVMap_D2")


def build_object(name: str, asm: dict, mats: list[str], smooth_deg: float = 40.0, link: bool = True):
    """asm: Geo.assemble() output. Returns the Blender object (mesh with 3 UV sets and one material slot per name)."""
    import bpy

    V, F, M = asm["V"], asm["F"], asm["M"]
    nt = len(F)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(nt * 3)
    me.loops.foreach_set("vertex_index", F.astype(np.int32).ravel())
    me.polygons.add(nt)
    me.polygons.foreach_set("loop_start", (np.arange(nt, dtype=np.int32) * 3))
    me.polygons.foreach_set("loop_total", np.full(nt, 3, np.int32))
    me.polygons.foreach_set("material_index", M.astype(np.int32))
    me.update(calc_edges=True)
    # UVs: box projection for everything, explicit UVs where a chunk brought its own
    uv0 = G.box_uv(V, F)
    for pos, cuv in asm["uv_over"]:
        uv0[pos:pos + len(cuv)] = cuv
    layers = []
    for nm in UV_NAMES:
        layers.append(me.uv_layers.new(name=nm))
    layers[0].data.foreach_set("uv", uv0.astype(np.float32).reshape(-1))
    layers[1].data.foreach_set("uv", asm["A1"][F].astype(np.float32).reshape(-1))
    layers[2].data.foreach_set("uv", asm["A2"][F].astype(np.float32).reshape(-1))
    for m in mats:
        mat = bpy.data.materials.get(m) or bpy.data.materials.new(m)
        me.materials.append(mat)
    obj = bpy.data.objects.new(name, me)
    if link:
        bpy.context.scene.collection.objects.link(obj)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth_deg))
    return obj


def stats(obj) -> dict:
    me = obj.data
    dims = obj.dimensions
    return {"name": obj.name, "tris": len(me.polygons), "materials": [m.name for m in me.materials],
            "size_m": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)], "verts": len(me.vertices)}
