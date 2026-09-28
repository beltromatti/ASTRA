"""Libreria di modellazione procedurale di ASTRA per Blender 5.2 (headless).

Convenzioni (docs/STILE.md, docs/ricerca/08):
- unità in metri (Unreal importa l'FBX in centimetri automaticamente);
- asse X = avanti, Z = alto; pivot nell'angolo/origine del modulo sulla griglia da 0,5 m;
- slot di materiale con nomi stabili (MI_ASTRA_*), sostituiti in Unreal dalle istanze vere;
- smussi reali + normali pesate: niente smussi "cotti" nelle normal map.
"""
from __future__ import annotations

import math
import os
from typing import Iterable, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector

# Slot di materiale standard dei kit ASTRA
MAT_PANNELLO = "MI_ASTRA_Panel"      # pannelli verniciati chiari
MAT_STRUTTURA = "MI_ASTRA_Structure"    # struttura canna di fucile
MAT_PAVIMENTO = "MI_ASTRA_Floor"    # pavimento antiscivolo
MAT_GRIGLIA = "MI_ASTRA_Grate"        # grigliato a pavimento
MAT_FINITURA = "MI_ASTRA_Trim"      # gomma/metallo scuro, tubi, corrimano
MAT_LUCE = "MI_ASTRA_Light"              # strisce emissive
MAT_VETRO = "MI_ASTRA_Glass"            # vetri


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    return mat


def new_object(name: str, bm: bmesh.types.BMesh, mats: Sequence[str]) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in mats:
        mesh.materials.append(material(m))
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mat_index(obj: bpy.types.Object, name: str) -> int:
    for i, m in enumerate(obj.data.materials):
        if m and m.name == name:
            return i
    obj.data.materials.append(material(name))
    return len(obj.data.materials) - 1


def join(objects: Iterable[bpy.types.Object], name: str) -> bpy.types.Object:
    objs = [o for o in objects if o is not None]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    result = bpy.context.view_layer.objects.active
    result.name = name
    result.data.name = name
    return result


def bevel_and_normals(obj: bpy.types.Object, width: float = 0.012, segments: int = 2,
                      angle_deg: float = 35.0) -> None:
    """Smusso reale sugli spigoli vivi + normali pesate (look "hard surface" pulito)."""
    bev = obj.modifiers.new("Smusso", "BEVEL")
    bev.width = width
    bev.segments = segments
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(angle_deg)
    bev.harden_normals = True
    bev.miter_outer = "MITER_ARC"
    wn = obj.modifiers.new("NormaliPesate", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))
    for mod in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def box_uv(obj: bpy.types.Object, texel_m: float = 1.0) -> None:
    """UV a proiezione cubica in scala mondo (1 unità UV = texel_m metri)."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    uv = bm.loops.layers.uv.verify()
    for face in bm.faces:
        n = face.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in face.loops:
            co = loop.vert.co
            if ax == 0:
                u, v = co.y, co.z
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            loop[uv].uv = (u / texel_m, v / texel_m)
    bm.to_mesh(obj.data)
    bm.free()


def add_cylinder_x(bm: bmesh.types.BMesh, y: float, z: float, x0: float, x1: float, radius: float,
                   segments: int = 16, mat: int = 0) -> None:
    """Cilindro lungo l'asse X (tubi, corrimano)."""
    geom = bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                                 radius1=radius, radius2=radius, depth=(x1 - x0),
                                 matrix=Matrix.Translation(((x0 + x1) / 2, y, z)) @ Matrix.Rotation(math.radians(90), 4, "Y"))
    for f in {f for v in geom["verts"] for f in v.link_faces}:
        f.material_index = mat


def add_box(bm: bmesh.types.BMesh, center: Sequence[float], size: Sequence[float], mat: int = 0) -> None:
    geom = bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1.0)))
    for f in {f for v in geom["verts"] for f in v.link_faces}:
        f.material_index = mat


def export_fbx(obj: bpy.types.Object, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Z", axis_up="Y", mesh_smooth_type="FACE", use_tspace=True,
        use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode="STRIP")


def stats(obj: bpy.types.Object) -> dict:
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dims = obj.dimensions
    return {"nome": obj.name, "triangoli": tris, "materiali": [m.name for m in me.materials],
            "dimensioni_m": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)]}
