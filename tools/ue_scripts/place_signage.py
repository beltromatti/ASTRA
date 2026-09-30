"""The bridge's signage (tools/art/signage.py textures, art/blender/signs.py plate): imports, materials, placement.
Idempotent: actors tagged ASTRA.Signage are replaced. Run in the editor (not during PIE):
  tools/ue.py pyfile tools/ue_scripts/place_signage.py
"""
import json
import math
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
TEX_DIR = "/Game/ASTRA/UI/Signage"
MESH_DIR = "/Game/ASTRA/Kit/Signage"
MI_DIR = "/Game/ASTRA/Materials/Instances"
MAT_DIR = "/Game/ASTRA/Materials"
TAG = "ASTRA.Signage"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
log = []


def import_files(src_dir, names, dst):
    tasks = []
    for n in names:
        t = unreal.AssetImportTask()
        t.filename = os.path.join(src_dir, n)
        t.destination_path = dst
        t.automated = True
        t.replace_existing = True
        t.save = True
        tasks.append(t)
    tools.import_asset_tasks(tasks)


# ---- textures and the plate
sig = os.path.join(ROOT, "art", "_cache", "signage")
pngs = sorted(f for f in os.listdir(sig) if f.endswith(".png"))
import_files(sig, pngs, TEX_DIR)
for f in pngs:
    t = eal.load_asset(f"{TEX_DIR}/{os.path.splitext(f)[0]}")
    t.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_FROM_TEXTURE_GROUP)
    t.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    eal.save_loaded_asset(t, only_if_is_dirty=False)
import_files(os.path.join(ROOT, "art", "export", "signs"), ["SM_SIGN_Plate.fbx"], MESH_DIR)
plate = eal.load_asset(f"{MESH_DIR}/SM_SIGN_Plate")
structure = eal.load_asset(f"{MI_DIR}/MI_ASTRA_Structure")
mats = plate.get_editor_property("static_materials")
for i, sm in enumerate(mats):
    if str(sm.get_editor_property("material_slot_name")).startswith("MI_ASTRA_Structure") and structure:
        plate.set_material(i, structure)
eal.save_loaded_asset(plate, only_if_is_dirty=False)
log.append(f"imported {len(pngs)} textures and the plate")


def mi(name, parent, scalars=None, vectors=None, textures=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(
        name, MI_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(f"{TEX_DIR}/{v}"))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    return inst


# ---- the decal material: a texture tinted, its alpha as the opacity, roughness/metallic parameters
dpath = f"{MAT_DIR}/M_ASTRA_Decal"
if not eal.does_asset_exist(dpath):
    dm = tools.create_asset("M_ASTRA_Decal", MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    dm.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    dm.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    tex = mel.create_material_expression(dm, unreal.MaterialExpressionTextureSampleParameter2D, -700, 0)
    tex.set_editor_property("parameter_name", "Texture")
    tint = mel.create_material_expression(dm, unreal.MaterialExpressionVectorParameter, -700, -250)
    tint.set_editor_property("parameter_name", "Tint")
    tint.set_editor_property("default_value", unreal.LinearColor(1, 1, 1, 1))
    mul = mel.create_material_expression(dm, unreal.MaterialExpressionMultiply, -350, -100)
    mel.connect_material_expressions(tex, "RGB", mul, "A")
    mel.connect_material_expressions(tint, "", mul, "B")
    mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
    op = mel.create_material_expression(dm, unreal.MaterialExpressionScalarParameter, -700, 250)
    op.set_editor_property("parameter_name", "Opacity")
    op.set_editor_property("default_value", 1.0)
    mo = mel.create_material_expression(dm, unreal.MaterialExpressionMultiply, -350, 200)
    mel.connect_material_expressions(tex, "A", mo, "A")
    mel.connect_material_expressions(op, "", mo, "B")
    mel.connect_material_property(mo, "", unreal.MaterialProperty.MP_OPACITY)
    for pname, prop, val, y in (("Roughness", unreal.MaterialProperty.MP_ROUGHNESS, 0.5, 400), ("Metallic", unreal.MaterialProperty.MP_METALLIC, 0.0, 500)):
        e = mel.create_material_expression(dm, unreal.MaterialExpressionScalarParameter, -350, y)
        e.set_editor_property("parameter_name", pname)
        e.set_editor_property("default_value", val)
        mel.connect_material_property(e, "", prop)
    mel.recompile_material(dm)
    eal.save_loaded_asset(dm, only_if_is_dirty=False)
decal_mat = eal.load_asset(dpath)
screen = eal.load_asset(f"{MAT_DIR}/M_ASTRA_Screen")
FLIP_U = globals().get("FLIP_U", 0.0)
FLIP_V = globals().get("FLIP_V", 0.0)
for f in pngs:
    n = os.path.splitext(f)[0]
    if n.startswith("T_SIGN_"):
        mi("MI_" + n[2:], screen, scalars={"Intensity": 8.0, "Roughness": 0.4, "FlipU": FLIP_U, "FlipV": FLIP_V}, textures={"ScreenTexture": n})
mi("MI_DECAL_Emblem", decal_mat, scalars={"Opacity": 0.9, "Roughness": 0.28, "Metallic": 0.85}, vectors={"Tint": (0.55, 0.58, 0.62)},
   textures={"Texture": "T_DECAL_Emblem"})
mi("MI_DECAL_Edge", decal_mat, scalars={"Opacity": 0.85, "Roughness": 0.6, "Metallic": 0.0}, vectors={"Tint": (1.0, 1.0, 1.0)},
   textures={"Texture": "T_DECAL_Edge"})
log.append("materials ok")

# ---- placement (bridge frame: metres, X to the bow, Y to starboard, origin under the captain's chair)
for a in eas.get_all_level_actors():
    if a.actor_has_tag(TAG):
        eas.destroy_actor(a)
data = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_bridge.json")))
levels = data["levels"]


def sign(name, x, y, z, yaw, w, h):
    a = eas.spawn_actor_from_object(plate, unreal.Vector(x * M, y * M, z * M), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(1.0, w, h))
    smc = a.get_component_by_class(unreal.StaticMeshComponent)
    for i, sm in enumerate(plate.get_editor_property("static_materials")):
        if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
            smc.set_material(i, eal.load_asset(f"{MI_DIR}/MI_SIGN_{name}"))
    smc.set_editor_property("cast_shadow", False)
    a.set_actor_label(f"Sign_{name}")
    a.set_folder_path("Bridge/Signage")
    a.tags = [TAG]
    return a


# the stations' names are part of the v3 consoles and chairs (art/blender/bridge3_*.py): no plates floating over them
md = data["master_display"]
back = data["walls"]["back_x"]
sign("Aquila", back + 0.06, 0.0, md["bottom"] + md["height"] + 0.27, 0.0, 2.6, 0.65)   # clear of the display's frame
for d in data["doors"]:
    dx, dy = d["pos"]
    sign("Door_Starboard" if dy > 0 else "Door_Port", dx + 0.07, dy, d["height"] + 0.16, 0.0, 1.0, 0.25)


def decal(name, x, y, z, ext_y, ext_z, mat, yaw=0.0):
    a = eas.spawn_actor_from_class(unreal.DecalActor, unreal.Vector(x * M, y * M, z * M), unreal.Rotator(roll=0, pitch=-90, yaw=yaw))
    dc = a.get_component_by_class(unreal.DecalComponent)
    dc.set_editor_property("decal_size", unreal.Vector(12.0, ext_y * M, ext_z * M))
    dc.set_decal_material(eal.load_asset(f"{MI_DIR}/{mat}"))
    a.set_actor_label(name)
    a.set_folder_path("Bridge/Signage")
    a.tags = [TAG]


well = data["well"]
decal("Decal_Emblem", 7.7, 0.0, levels["well"] + 0.02, 0.8, 0.8, "MI_DECAL_Emblem")
decal("Decal_WellEdge", well["edge_x"] - 0.1, 0.0, levels["upper"] + 0.02, well["half_width"], 0.06, "MI_DECAL_Edge")
unreal.EditorLevelLibrary.save_current_level()
log.append("placed")
print(log)
