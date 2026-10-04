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

    def screen(self, matrix, mat: str, u_range=(0.0, 1.0), v_range=(0.0, 1.0)) -> None:
        """Unit cube transformed by `matrix` (local X = thickness/normal, Y = width, Z = height) with UVs mapped
        from its local (y, z) to u_range x v_range, so a UI texture fills the screen exactly."""
        import bmesh as _bm
        custom = self._custom_uv_layer()          # create layers first: adding a layer invalidates element refs
        uv = self.bm.loops.layers.uv.verify()
        geom = _bm.ops.create_cube(self.bm, size=1.0, matrix=matrix)
        idx = self.mi(mat)
        inv = matrix.inverted()
        faces = list({f for v in geom["verts"] for f in v.link_faces})
        _bm.ops.recalc_face_normals(self.bm, faces=faces)      # negative scales (mirrored UVs) invert the winding
        for f in faces:
            f.material_index = idx
            for loop in f.loops:
                lc = inv @ loop.vert.co
                u = u_range[0] + (lc.y + 0.5) * (u_range[1] - u_range[0])
                v = v_range[0] + (lc.z + 0.5) * (v_range[1] - v_range[0])
                loop[uv].uv = (u, v)
            f[custom] = 1

    def _custom_uv_layer(self):
        lay = self.bm.faces.layers.int.get("custom_uv")
        if lay is None:
            lay = self.bm.faces.layers.int.new("custom_uv")
        return lay

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
    custom = bm.faces.layers.int.get("custom_uv")
    for face in bm.faces:
        if custom is not None and face[custom]:
            continue
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


# The same mesh must make the same FBX file: the importers hash the files to re-import only what changed (build_ship_interior.py's
# stamp), and every export re-imported all 446 meshes of the kit (3 Oct). The exporter stamps each file with the time of writing and
# numbers its objects with Python's hash() of their names, which changes from one Blender process to the next: a fixed time and a
# stable hash, inside the exporter only.
class _FixedClock:
    class datetime:
        @staticmethod
        def now():
            import datetime as dt
            return dt.datetime(2026, 1, 1)


def _stable_hash(key) -> int:
    import hashlib
    return int.from_bytes(hashlib.blake2b(repr(key).encode("utf-8"), digest_size=8).digest(), "little", signed=True)


def geometry_signature(obj: bpy.types.Object) -> str:
    """An order-free fingerprint of what obj's FBX holds: its triangles with their positions (0.1 mm), UVs, normals and material slot names,
    each triangle started at the same corner, all of them sorted. The room generators lay their vertices and faces down in a different order
    from one run to the next with the same shapes, so the FBX files' bytes always differ: this is what says whether a mesh changed."""
    import hashlib
    import numpy as np
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        n = len(me.loop_triangles)
        if n == 0:
            return "empty"
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        tv = np.empty(n * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tv)
        tv = tv.reshape(n, 3)
        tl = np.empty(n * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("loops", tl)
        tl = tl.reshape(n, 3)
        mi = np.empty(n, dtype=np.int64)
        me.loop_triangles.foreach_get("material_index", mi)
        corners = [np.round(co.reshape(-1, 3)[tv] * 1e4)]                                   # (n, 3 corners, xyz)
        if me.uv_layers.active:
            uv = np.empty(len(me.loops) * 2)
            me.uv_layers.active.data.foreach_get("uv", uv)
            corners.append(np.round(uv.reshape(-1, 2)[tl] * 1e4))
        nr = np.empty(len(me.loops) * 3)
        me.corner_normals.foreach_get("vector", nr)
        corners.append(np.round(nr.reshape(-1, 3)[tl] * 10.0))           # (a tenth: the hundredths flipped between two runs of the same mesh)
        c = np.concatenate(corners, axis=2).astype(np.int64)                                # (n, 3, k)
        # each triangle from its corner of least position (the winding kept): a mix of x, y, z that only a degenerate triangle ties
        key = c[:, :, 0] * 73856093 ^ c[:, :, 1] * 19349663 ^ c[:, :, 2] * 83492791
        first = np.argmin(key, axis=1)
        rot = (first[:, None] + np.arange(3)[None, :]) % 3
        c = np.take_along_axis(c, rot[:, :, None], axis=1).reshape(n, -1)
        names = [s.material.name if s.material else s.name for s in obj.material_slots] or [""]
        ids = np.array([int.from_bytes(hashlib.blake2b(nm.encode("utf-8"), digest_size=8).digest(), "little", signed=True) for nm in names])
        rows = np.concatenate([ids[np.clip(mi, 0, len(ids) - 1)][:, None], c], axis=1)
        rows = rows[np.lexsort(rows.T[::-1])]
        return hashlib.blake2b(rows.tobytes(), digest_size=12).hexdigest()
    finally:
        ev.to_mesh_clear()


def export_fbx(obj: bpy.types.Object, path: str) -> None:
    from io_scene_fbx import export_fbx_bin, fbx_utils
    export_fbx_bin.datetime = _FixedClock
    fbx_utils.hash = _stable_hash
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    # n-gons (bevels leave them) are triangulated here, not by the FBX importer: its triangulation of polygons with
    # collinear vertices drops triangles (holes at the corners); custom normals are kept, tangents can be exported
    tri = obj.modifiers.new("ExportTriangulate", "TRIANGULATE") if obj.type == "MESH" else None
    if tri:
        tri.min_vertices = 5
        tri.quad_method = "BEAUTY"
        tri.ngon_method = "BEAUTY"
        tri.keep_custom_normals = True
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Z", axis_up="Y", mesh_smooth_type="FACE", use_tspace=True,
        use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode="STRIP")
    if tri:
        obj.modifiers.remove(tri)


def stats(obj: bpy.types.Object) -> dict:
    me = obj.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    dims = obj.dimensions
    return {"name": obj.name, "tris": tris, "materials": [m.name for m in me.materials],
            "size_m": [round(dims.x, 3), round(dims.y, 3), round(dims.z, 3)]}


def subsurf(obj: bpy.types.Object, levels: int = 2, crease_edges: Iterable | None = None) -> None:
    """Subdivision surface on a cage (smooth sculpted shapes for chairs/consoles), applied."""
    mod = obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = levels
    mod.render_levels = levels
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def render_preview(objects: Sequence[bpy.types.Object], path: str, size: int = 900,
                   view: tuple[float, float] = (35.0, 25.0), dist_mul: float = 1.6) -> str:
    """Quick Workbench render framing the given objects (azimuth, elevation in degrees). For visual QA."""
    scene = bpy.context.scene
    mins = Vector((1e9, 1e9, 1e9))
    maxs = Vector((-1e9, -1e9, -1e9))
    for o in objects:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mins = Vector((min(mins.x, w.x), min(mins.y, w.y), min(mins.z, w.z)))
            maxs = Vector((max(maxs.x, w.x), max(maxs.y, w.y), max(maxs.z, w.z)))
    center = (mins + maxs) / 2
    radius = (maxs - mins).length / 2
    az, el = math.radians(view[0]), math.radians(view[1])
    direction = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = center + direction * radius * dist_mul * 2.2
    cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
    cam_data.clip_end = 10000
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "BOTH"
    scene.display.shading.show_shadows = True
    scene.render.resolution_x = size
    scene.render.resolution_y = int(size * 0.66)
    scene.render.film_transparent = False
    scene.render.filepath = path
    palette = {MAT_PANEL: (0.78, 0.74, 0.66, 1), MAT_STRUCTURE: (0.08, 0.085, 0.095, 1), MAT_FLOOR: (0.2, 0.2, 0.21, 1),
               MAT_GRATE: (0.3, 0.3, 0.32, 1), MAT_TRIM: (0.45, 0.46, 0.48, 1), MAT_LIGHT: (1, 1, 0.95, 1),
               MAT_ACCENT: (0.1, 0.3, 1, 1), MAT_GUIDE: (0.7, 0.9, 1, 1), MAT_SCREEN: (0.05, 0.2, 0.45, 1),
               MAT_GLASS: (0.5, 0.7, 0.8, 1), MAT_RUBBER: (0.03, 0.03, 0.03, 1),
               "MI_HULL_Plate": (0.78, 0.76, 0.7, 1), "MI_HULL_Frame": (0.12, 0.13, 0.14, 1),
               "MI_HULL_Livery": (0.08, 0.15, 0.35, 1), "MI_HULL_Engine": (0.3, 0.3, 0.32, 1),
               "MI_HULL_Glow": (0.5, 0.8, 1.0, 1), "MI_HULL_Lights": (1.0, 0.9, 0.6, 1),
               "MI_HULL_Radiator": (0.35, 0.2, 0.1, 1)}
    for m in bpy.data.materials:
        m.diffuse_color = palette.get(m.name, (0.6, 0.6, 0.6, 1))
    bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(cam, do_unlink=True)
    return path


MAT_FLOOR_BRIDGE = "MI_ASTRA_FloorBridge"   # dark bridge deck
MAT_LEATHER = "MI_ASTRA_Leather"            # seat upholstery


def rounded_box(name: str, center, size, radius: float, mat: str, segments: int = 4,
                cuts: tuple[int, int, int] = (0, 0, 0)) -> bpy.types.Object:
    """Box with all edges rounded (radius), optionally pre-subdivided (cuts per axis) so it can be bent."""
    b = Builder()
    import bmesh as _bm
    geom = _bm.ops.create_cube(b.bm, size=1.0, matrix=Matrix.Diagonal((*size, 1.0)))
    b._assign(geom["verts"], mat)
    for axis, n in enumerate(cuts):
        if n <= 0:
            continue
        edges = [e for e in b.bm.edges
                 if abs((e.verts[0].co - e.verts[1].co)[axis]) > 1e-6
                 and all(abs((e.verts[0].co - e.verts[1].co)[k]) < 1e-6 for k in range(3) if k != axis)]
        _bm.ops.subdivide_edges(b.bm, edges=edges, cuts=n, use_grid_fill=True)
    obj = b.to_object(name)
    bev = obj.modifiers.new("Round", "BEVEL")
    bev.width = radius
    bev.segments = segments
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(30)
    bev.use_clamp_overlap = True
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bev.name)
    obj.location = center
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return obj


def bend(obj: bpy.types.Object, angle_deg: float, axis: str = "Z", origin=(0.0, 0.0, 0.0)) -> None:
    """Bend an object with SimpleDeform around `axis` through `origin`."""
    empty = bpy.data.objects.new("bend_origin", None)
    bpy.context.scene.collection.objects.link(empty)
    empty.location = origin
    mod = obj.modifiers.new("Bend", "SIMPLE_DEFORM")
    mod.deform_method = "BEND"
    mod.deform_axis = axis
    mod.angle = math.radians(angle_deg)
    mod.origin = empty
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(empty, do_unlink=True)


def transform(obj: bpy.types.Object, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    """Apply a rotation (degrees, XYZ Euler) then a translation to the mesh data."""
    from mathutils import Euler
    m = Matrix.Translation(loc) @ Euler(tuple(math.radians(a) for a in rot_deg), "XYZ").to_matrix().to_4x4()
    obj.data.transform(m)
    obj.data.update()
    return obj


def arc_slab(name: str, width: float, height: float, thickness: float, curvature_radius: float, mat: str,
             segments: int = 12, round_radius: float = 0.012) -> bpy.types.Object:
    """Curved slab (backrests, wall screens): cross-section is an arc in the XY plane, concave towards +X
    (centre of curvature at +X), centred on the origin, extruded along Z from 0 to `height`."""
    import bmesh as _bm
    b = Builder()
    idx = b.mi(mat)
    R = curvature_radius
    phi = (width / 2) / R
    inner, outer = [], []
    for i in range(segments + 1):
        a = -phi + 2 * phi * i / segments
        for (lst, r) in ((inner, R), (outer, R + thickness)):
            x = R - r * math.cos(a)
            y = r * math.sin(a)
            lst.append((x, y))
    ring = inner + list(reversed(outer))
    lo = [b.bm.verts.new((x, y, 0.0)) for x, y in ring]
    hi = [b.bm.verts.new((x, y, height)) for x, y in ring]
    faces = [b.bm.faces.new(list(reversed(lo))), b.bm.faces.new(hi)]
    n = len(ring)
    for i in range(n):
        j = (i + 1) % n
        faces.append(b.bm.faces.new((lo[i], lo[j], hi[j], hi[i])))
    for f in faces:
        f.material_index = idx
    _bm.ops.recalc_face_normals(b.bm, faces=faces)
    obj = b.to_object(name)
    if round_radius > 0:
        bev = obj.modifiers.new("Round", "BEVEL")
        bev.width = round_radius
        bev.segments = 3
        bev.limit_method = "ANGLE"
        bev.angle_limit = math.radians(40)
        bev.use_clamp_overlap = True
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=bev.name)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
    return obj
