"""ABBORDAGGI: the Aquila's small arms, prepared for Unreal from free third-party models (Blender 5.2, headless).

    blender -b --factory-startup -P art/blender/weapons.py [-- --only AR181|M27S] [-- --preview]

Sources (art/_downloads/weapons/, not in git; licences in docs/LICENZE.md):
  - ar181_frostoise.glb     "Frostoise AR-181"      Sketchfab, CC BY 4.0 (the service rifle)
  - m27s_tuuttipingu.glb    "Tuuttipingu M27S 9mm"  Sketchfab, CC BY 4.0 (the sidearm)

What it does, per weapon:
  - applies every part's transform, turns the model so the barrel points to Blender -Y (the FBX export flips the handedness: it comes out as +Y in
    Unreal, which is where the mannequin's HandGrip_R socket looks) and the top is +Z;
  - scales it to a real weapon's size and puts the origin in the middle of the pistol grip (the palm), so that attached to the hand's socket with no
    offset the weapon sits in the hand;
  - joins the parts into one mesh (the rifle's magazine stays a mesh of its own, same origin, so a reload can move it);
  - exports FBX (art/export/weapons/) with stable material slot names MI_<weapon>_<part>, the textures (art/export/weapons/tex/: base colour, a packed
    "ORM" map (R 1, G roughness, B metallic: glTF's), a normal map turned to Unreal's convention, emission) cut to a size a handheld object needs,
    and weapons.json: the sockets (muzzle, sight, support hand, magazine, ejection port) and the sizes, in Unreal's frame and centimetres, which the
    game's weapon table (Source/ASTRA/AstraWeapon.cpp) and tools/ue_scripts/import_weapons.py read.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
import mathutils
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import astra_bpy  # noqa: E402

SRC = os.path.join(ROOT, "art", "_downloads", "weapons")
OUT = os.path.join(ROOT, "art", "export", "weapons")
TEX = os.path.join(OUT, "tex")

# Per weapon: the source, the turn that points its barrel to -Y with the top up, the real length (m), where the palm sits and the sockets, in the
# model's own units after the turn (found with art/blender/ tools: the picture of each part is in docs/ABBORDAGGI.md)
WEAPONS = {
    "AR181": {
        "glb": "ar181_frostoise.glb",
        "turn_z_deg": 0.0,                      # the model already has its barrel to -Y and the magazine below
        "length_m": 0.94,                       # muzzle (the suppressor's end) to the end of the stock
        "palm": (0.0, 1.25, -0.37),             # the middle of the pistol grip
        "muzzle": (0.0, None, 0.49),            # None: the end of the model on the barrel's side
        "sight": (0.0, 0.69, 0.98),             # the rear sight's aperture (the sight line goes through it and the front post)
        "sight_front": (0.0, -2.11, 0.93),
        "support": (0.0, -1.50, 0.02),          # where the left hand takes the handguard
        "mag_well": (0.0, -0.07, 0.10),         # the top of the magazine, where it goes into the receiver
        "eject": (0.27, 0.30, 0.30),
        "mag_part": "clip_lo",
        "slots": {"Material": "Body", "material": "Add", "Scope": "Scope"},
        "tex_size": {"Material": 2048, "material": 1024, "Scope": 1024},
    },
    "M27S": {
        "glb": "m27s_tuuttipingu.glb",
        "turn_z_deg": 90.0,                     # the model has its barrel to -X: a quarter turn puts it to -Y
        "length_m": 0.205,
        "palm": (0.0, 1.65, -1.0),              # (the table is in the turned frame: the barrel to -Y)
        "muzzle": (0.0, None, 0.50),
        "sight": (0.0, 1.95, 0.97),
        "sight_front": (0.0, -2.55, 0.97),
        "support": (0.0, 0.5, -2.0),
        "mag_well": (0.0, 1.9, -0.2),
        "eject": (-0.28, 0.4, 0.55),
        "mag_part": None,
        "slots": {"frame": "Frame", "slide1": "Slide"},
        "tex_size": {"frame": 2048, "slide1": 2048},
    },
}


def log(*a):
    print("[weapons]", *a, flush=True)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_parts(glb: str) -> list:
    """The glb's meshes, unparented, with their transforms applied (world space as the file puts them)."""
    bpy.ops.import_scene.gltf(filepath=os.path.join(SRC, glb))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in meshes:
        mw = o.matrix_world.copy()
        o.parent = None
        o.matrix_world = mw
    for o in [o for o in bpy.context.scene.objects if o.type != "MESH"]:
        bpy.data.objects.remove(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return meshes


def bounds(objs) -> tuple[Vector, Vector]:
    """The box of the objects' vertices in world space (read from the mesh data: an object's bound_box is stale until the scene updates)."""
    import numpy as np

    mn = np.array([1e9, 1e9, 1e9])
    mx = np.array([-1e9, -1e9, -1e9])
    for o in objs:
        me = o.data
        a = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", a)
        a = a.reshape(-1, 3)
        m = np.array(o.matrix_world)
        w = a @ m[:3, :3].T + m[:3, 3]
        mn = np.minimum(mn, w.min(axis=0))
        mx = np.maximum(mx, w.max(axis=0))
    return Vector(mn), Vector(mx)


def transform_all(objs, m: Matrix) -> None:
    for o in objs:
        o.data.transform(m)
        o.matrix_world = Matrix.Identity(4)
        o.data.update()


def export_fbx(obj, path: str) -> None:
    """The project's export (astra_bpy.export_fbx: metres in, centimetres out, the handedness flipped, Blender +Y becomes Unreal -Y) with the mesh's own
    normals kept (the models carry smooth normals that their normal maps were baked for), not rebuilt from smoothing groups."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    tri = obj.modifiers.new("ExportTriangulate", "TRIANGULATE")
    tri.min_vertices = 4
    tri.quad_method = "BEAUTY"
    tri.keep_custom_normals = True
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, apply_unit_scale=True, apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Z", axis_up="Y", mesh_smooth_type="OFF", use_tspace=True,
        use_mesh_modifiers=True, add_leaf_bones=False, bake_anim=False, path_mode="STRIP")
    obj.modifiers.remove(tri)


def pixels(im) -> "numpy.ndarray":
    import numpy as np

    a = np.empty(im.size[0] * im.size[1] * 4, dtype=np.float32)
    im.pixels.foreach_get(a)
    return a.reshape(im.size[1], im.size[0], 4)


def save_image(im, path: str, size: int, edit=None) -> None:
    """Writes the image datablock as a PNG cut to at most size x size, the pixels untouched except for what `edit` (a function of the HxWx4 array) does.
    The datablock itself is worked on (a copy made with images.new loses its pixels when its colour space is set: Blender regenerates a generated
    image), so the numbers go out as they came in."""
    if edit:
        a = pixels(im).copy()
        edit(a)
        im.pixels.foreach_set(a.reshape(-1))
    if max(im.size) > size:
        im.scale(size, size)
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()


def export_textures(wname: str, slot_names: dict, tex_size: dict) -> dict:
    """For each material: base colour, ORM (glTF's metallic-roughness: G roughness, B metallic; R 1), normal (green turned: Unreal reads DirectX
    normals, glTF carries OpenGL's), emission when there is one. Returns {material: {role: filename}}."""
    os.makedirs(TEX, exist_ok=True)
    out = {}
    for m in bpy.data.materials:
        if m.name not in slot_names or not m.node_tree:
            continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not bsdf:
            continue

        def image_of(sock):
            seen = 0
            while sock.is_linked and seen < 6:
                n = sock.links[0].from_node
                if n.type == "TEX_IMAGE":
                    return n.image
                ins = [i for i in n.inputs if i.is_linked]
                if not ins:
                    return None
                sock = ins[0]
                seen += 1
            return None

        def no_ao(a):
            a[..., 0] = 1.0                                  # no ambient occlusion in the file
            a[..., 3] = 1.0

        def to_directx(a):
            a[..., 1] = 1.0 - a[..., 1]                      # OpenGL -> DirectX
            a[..., 3] = 1.0

        size = tex_size.get(m.name, 1024)
        part = slot_names[m.name]
        files = {}
        im = image_of(bsdf.inputs["Base Color"])
        if im:
            save_image(im, os.path.join(TEX, f"T_{wname}_{part}_BC.png"), size)
            files["base"] = f"T_{wname}_{part}_BC.png"
        im = image_of(bsdf.inputs["Roughness"]) or image_of(bsdf.inputs["Metallic"])
        if im:
            save_image(im, os.path.join(TEX, f"T_{wname}_{part}_ORM.png"), size, no_ao)
            files["orm"] = f"T_{wname}_{part}_ORM.png"
        im = image_of(bsdf.inputs["Normal"])
        if im:
            save_image(im, os.path.join(TEX, f"T_{wname}_{part}_N.png"), size, to_directx)
            files["normal"] = f"T_{wname}_{part}_N.png"
        emi = bsdf.inputs["Emission Color"]
        if emi.is_linked and bsdf.inputs["Emission Strength"].default_value > 0.0:
            im = image_of(emi)
            if im:
                save_image(im, os.path.join(TEX, f"T_{wname}_{part}_E.png"), min(size, 1024))
                files["emissive"] = f"T_{wname}_{part}_E.png"
        out[m.name] = files
        log("textures", wname, m.name, files)
    return out


def build(name: str, cfg: dict, preview: bool) -> dict:
    reset()
    parts = import_parts(cfg["glb"])
    if cfg["turn_z_deg"]:
        transform_all(parts, Matrix.Rotation(math.radians(cfg["turn_z_deg"]), 4, "Z"))
    mn, mx = bounds(parts)
    length = mx.y - mn.y
    scale = cfg["length_m"] / length
    log(name, "parts", len(parts), "model length", round(length, 3), "-> scale", round(scale, 5), "bounds", tuple(round(v, 2) for v in mn), tuple(round(v, 2) for v in mx))
    palm = Vector(cfg["palm"])
    # origin in the palm, then to metres
    transform_all(parts, Matrix.Scale(scale, 4) @ Matrix.Translation(-palm))

    def pt(p):
        """A point of the table (model units, the model's own origin) in the weapon's frame (metres, palm origin); None coordinates come from the end."""
        v = Vector(p[i] if p[i] is not None else 0.0 for i in range(3))
        v = (v - palm) * scale
        return v

    muzzle = Vector(cfg["muzzle"][i] if cfg["muzzle"][i] is not None else 0.0 for i in range(3))
    muzzle = (muzzle - palm) * scale
    # the muzzle's y is the end of the model on the barrel's side: min y (after the palm shift and scale)
    mn2, mx2 = bounds(parts)
    muzzle.y = mn2.y
    sockets = {
        "Muzzle": muzzle,
        "Sight": pt(cfg["sight"]),
        "SightFront": pt(cfg["sight_front"]),
        "GripL": pt(cfg["support"]),
        "MagWell": pt(cfg["mag_well"]),
        "Eject": pt(cfg["eject"]),
    }
    # materials: stable slot names for the project's importer
    slot_names = cfg["slots"]
    for o in parts:
        for i, mt in enumerate(o.data.materials):
            if mt and mt.name in slot_names:
                pass
    textures = export_textures(name, slot_names, cfg["tex_size"])
    # now rename the materials in the slots: MI_<weapon>_<part>
    for mt in list(bpy.data.materials):
        if mt.name in slot_names:
            mt.name = f"MI_{name}_{slot_names[mt.name]}"
    # join: the body, and the magazine apart
    body_parts = [o for o in parts if not (cfg["mag_part"] and o.name.startswith(cfg["mag_part"]))]
    mag_parts = [o for o in parts if cfg["mag_part"] and o.name.startswith(cfg["mag_part"])]
    objs = {}

    def join(group, oname):
        if not group:
            return None
        bpy.ops.object.select_all(action="DESELECT")
        for o in group:
            o.select_set(True)
        bpy.context.view_layer.objects.active = group[0]
        if len(group) > 1:
            bpy.ops.object.join()
        j = bpy.context.view_layer.objects.active
        j.name = oname
        j.data.name = oname
        # a single UV map named like the importer's first; normals as they come (custom split normals kept)
        return j

    objs["body"] = join(body_parts, f"SM_{name}")
    objs["mag"] = join(mag_parts, f"SM_{name}_Mag")
    # a material slot appears once per material even after joining: merge the duplicates
    for o in objs.values():
        if o is None:
            continue
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.material_slot_remove_unused()
    os.makedirs(OUT, exist_ok=True)
    stats = {}
    for key, o in objs.items():
        if o is None:
            continue
        export_fbx(o, os.path.join(OUT, f"{o.name}.fbx"))
        st = astra_bpy.stats(o)
        stats[o.name] = st
        log("exported", o.name, st)

    def ue(v: Vector) -> list:
        """Blender metres (barrel -Y) -> Unreal centimetres (barrel +Y): the export flips y."""
        return [round(v.x * 100.0, 2), round(-v.y * 100.0, 2), round(v.z * 100.0, 2)]

    all_mn, all_mx = bounds([o for o in objs.values() if o])
    info = {
        "length_cm": round((all_mx.y - all_mn.y) * 100.0, 1),
        "height_cm": round((all_mx.z - all_mn.z) * 100.0, 1),
        "width_cm": round((all_mx.x - all_mn.x) * 100.0, 1),
        "sockets_cm": {k: ue(v) for k, v in sockets.items()},
        "bounds_cm": {"min": [min(a, b) for a, b in zip(ue(all_mn), ue(all_mx))], "max": [max(a, b) for a, b in zip(ue(all_mn), ue(all_mx))]},
        "meshes": stats,
        "textures": {f"MI_{name}_{slot_names[k]}": v for k, v in textures.items()},
        "materials": [f"MI_{name}_{v}" for v in slot_names.values()],
    }
    if preview:
        render_preview(name, objs, sockets)
    return info


def render_preview(name: str, objs: dict, sockets: dict) -> None:
    """Side and top pictures with the sockets as little spheres: palm origin (white), muzzle (red), sight (green), support hand (blue), magazine (yellow)."""
    scn = bpy.context.scene
    try:
        scn.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scn.render.engine = "BLENDER_EEVEE"
    scn.render.resolution_x, scn.render.resolution_y = 1400, 700
    w = bpy.data.worlds.new("w")
    scn.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.37, 0.42, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.2
    colours = {"Muzzle": (1, 0, 0, 1), "Sight": (0, 1, 0, 1), "SightFront": (0, 0.6, 0, 1), "GripL": (0.2, 0.4, 1, 1), "MagWell": (1, 0.9, 0, 1), "Eject": (1, 0.4, 0, 1)}
    marks = []
    for k, v in list(sockets.items()) + [("Palm", Vector((0, 0, 0)))]:
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.006, location=v)
        s = bpy.context.object
        mt = bpy.data.materials.new("m" + k)
        mt.use_nodes = True
        nt = mt.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs[0].default_value = colours.get(k, (1, 1, 1, 1))
        em.inputs[1].default_value = 3.0
        outn = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs[0], outn.inputs[0])
        s.data.materials.append(mt)
        marks.append(s)
    body = [o for o in objs.values() if o]
    mn, mx = bounds(body)
    c = (mn + mx) / 2
    size = max(mx - mn)
    for ld_loc, e in (((1.0, -1.0, 2.0), 600.0), ((-1.5, 1.0, 1.0), 250.0)):
        ld = bpy.data.lights.new("l", "AREA")
        ld.energy = e
        ld.size = 1.0
        lo = bpy.data.objects.new("l", ld)
        scn.collection.objects.link(lo)
        lo.location = c + Vector(ld_loc)
        lo.rotation_euler = (c - lo.location).to_track_quat("-Z", "Y").to_euler()
    for view, off in (("side", (1.0, 0.0, 0.0)), ("top", (0.0, 0.0, 1.0)), ("back", (0.0, 1.0, 0.0))):
        for ob in [x for x in bpy.data.objects if x.type == "CAMERA"]:
            bpy.data.objects.remove(ob)
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        scn.collection.objects.link(cam)
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = size * 1.2
        cam.location = c + Vector(off) * 3.0
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        scn.camera = cam
        scn.render.filepath = os.path.join(OUT, f"preview_{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        log("preview", scn.render.filepath)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    preview = "--preview" in argv
    info = {}
    for name, cfg in WEAPONS.items():
        if only and name != only:
            continue
        info[name] = build(name, cfg, preview)
    # the table the game and the importer read (merged with what an earlier run of the other weapon wrote)
    path = os.path.join(OUT, "weapons.json")
    old = {}
    if os.path.exists(path):
        with open(path) as f:
            old = json.load(f)
    old.update(info)
    with open(path, "w") as f:
        json.dump(old, f, indent=1)
    log("wrote", path)


main()
