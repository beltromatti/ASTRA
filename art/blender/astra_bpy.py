"""ASTRA procedural modelling library for Blender 5.2 (headless).

Conventions (docs/STILE.md, docs/ricerca/08):
- units in metres (Unreal imports the FBX in centimetres automatically);
- X = forward/along the module, Z = up; pivots on module corners/origins on a 0.5 m grid;
- stable material slot names (MI_ASTRA_*): Unreal maps each slot to the real instance of the same name;
- real bevels + weighted normals: no bevels baked into normal maps.
Note: the FBX export flips the handedness, so Blender +Y becomes Unreal -Y.
"""
from __future__ import annotations

import math
import os
from typing import Iterable, Sequence

import bmesh
import bpy
from mathutils import Matrix, Vector

# Standard material slots of the ASTRA kits (see tools/ue_scripts/make_materials.py)
MAT_PANEL = "MI_ASTRA_Panel"          # light painted panels (ivory)
MAT_STRUCTURE = "MI_ASTRA_Structure"  # gunmetal structure
MAT_FLOOR = "MI_ASTRA_Floor"          # non-skid deck
MAT_GRATE = "MI_ASTRA_Grate"          # perforated walkway grate (masked)
MAT_TRIM = "MI_ASTRA_Trim"            # brushed metal: pipes, handrails, frames
MAT_LIGHT = "MI_ASTRA_Light"          # white light strips
MAT_ACCENT = "MI_ASTRA_Accent"        # department colour strip (changes with alert state)
MAT_GUIDE = "MI_ASTRA_Guide"          # floor guide lights
MAT_SCREEN = "MI_ASTRA_Screen"        # console / wall screens
MAT_GLASS = "MI_ASTRA_Glass"          # windows
MAT_RUBBER = "MI_ASTRA_Rubber"        # dark rubber/plastic: seals, handles, cable jackets


def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def clear_objects() -> None:
    for o in list(bpy.context.scene.objects):
        bpy.data.objects.remove(o, do_unlink=True)


def material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    return mat


class Builder:
    """A bmesh plus a material table: `b.box(center, size, MAT_PANEL)` adds geometry with the right slot."""

    def __init__(self) -> None:
        self.bm = bmesh.new()
        self.mats: list[str] = []

    def mi(self, name: str) -> int:
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def _assign(self, geom_verts, mat: str) -> None:
        idx = self.mi(mat)
        for f in {f for v in geom_verts for f in v.link_faces}:
            f.material_index = idx

    def box(self, center: Sequence[float], size: Sequence[float], mat: str) -> None:
        geom = bmesh.ops.create_cube(self.bm, size=1.0,
                                     matrix=Matrix.Translation(center) @ Matrix.Diagonal((*size, 1.0)))
        self._assign(geom["verts"], mat)

    def box_minmax(self, lo: Sequence[float], hi: Sequence[float], mat: str) -> None:
        c = [(a + b) / 2 for a, b in zip(lo, hi)]
        s = [abs(b - a) for a, b in zip(lo, hi)]
        self.box(c, s, mat)

    def cylinder(self, p0: Sequence[float], p1: Sequence[float], radius: float, mat: str,
                 segments: int = 16, radius2: float | None = None) -> None:
        """Cylinder (or cone frustum) between two points."""
        a, b = Vector(p0), Vector(p1)
        d = b - a
        length = d.length
        rot = d.normalized().to_track_quat("Z", "Y").to_matrix().to_4x4()
        m = Matrix.Translation((a + b) / 2) @ rot
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=segments,
                                     radius1=radius, radius2=radius if radius2 is None else radius2,
                                     depth=length, matrix=m)
        self._assign(geom["verts"], mat)

    def prism(self, profile_yz: Sequence[tuple[float, float]], x0: float, x1: float, mat: str) -> None:
        """Extrude a convex or concave (y, z) polygon along X (profile in counter-clockwise order)."""
        vf = [self.bm.verts.new((x0, y, z)) for y, z in profile_yz]
        vb = [self.bm.verts.new((x1, y, z)) for y, z in profile_yz]
        faces = [self.bm.faces.new(list(reversed(vf))), self.bm.faces.new(vb)]
        n = len(profile_yz)
        for i in range(n):
            j = (i + 1) % n
            faces.append(self.bm.faces.new((vf[i], vf[j], vb[j], vb[i])))
        idx = self.mi(mat)
        for f in faces:
            f.material_index = idx
        bmesh.ops.recalc_face_normals(self.bm, faces=faces)

    def to_object(self, name: str) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(mesh)
        self.bm.free()
        for m in self.mats:
            mesh.materials.append(material(m))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        return obj


def boolean(obj: bpy.types.Object, cutter: bpy.types.Object, op: str = "DIFFERENCE") -> None:
    """Manifold boolean; the cutter object is deleted afterwards."""
    mod = obj.modifiers.new("Bool", "BOOLEAN")
    mod.operation = op
    mod.solver = "MANIFOLD"
    mod.object = cutter
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


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
    """Real bevel on sharp edges + weighted normals (clean hard-surface look)."""
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = width
    bev.segments = segments
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(angle_deg)
    bev.harden_normals = True
    bev.miter_outer = "MITER_ARC"
    bev.use_clamp_overlap = True
    wn = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.keep_sharp = True
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle_deg))
    for mod in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)


def box_uv(obj: bpy.types.Object, texel_m: float = 1.0) -> None:
    """World-scale box projection UVs (1 UV unit = texel_m metres)."""
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


def finish(obj: bpy.types.Object, bevel: float = 0.008, segments: int = 2) -> bpy.types.Object:
    if bevel > 0:
        bevel_and_normals(obj, width=bevel, segments=segments)
    box_uv(obj)
    return obj


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
    return {"name": obj.name, "tris": tris, "materials": [m.name for m in me.materials],
            "size_m": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)]}
