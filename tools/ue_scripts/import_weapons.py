"""ABBORDAGGI: the Aquila's small arms into Unreal. Reads what art/blender/weapons.py wrote (art/export/weapons: FBX, textures, weapons.json) and makes
/Game/ASTRA/Weapons: the textures (colour sRGB, ORM and normal linear, normal DirectX), the master material M_Weapon and one instance per part
(MI_AR181_Body, MI_AR181_Add, MI_AR181_Scope, MI_M27S_Frame, MI_M27S_Slide), the static meshes SM_AR181, SM_AR181_Mag and SM_M27S (no collision, no Nanite: they are
first-person primitives) with their sockets (Muzzle, Sight, SightFront, GripL, MagWell, Eject) and their materials. Idempotent.

Run in the editor: tools/ue.py pyfile tools/ue_scripts/import_weapons.py   (set ROOT first to import from another checkout)
"""
import json
import os

import unreal

ROOT = globals().get("ROOT", "/Users/beltromatti/Desktop/ASTRA")
SRC = ROOT + "/art/export/weapons"
DST = "/Game/ASTRA/Weapons"
TEX_DST = DST + "/Textures"
MAT_DST = DST + "/Materials"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ST = unreal.MaterialSamplerType
log = []


def save(asset):
    return eal.save_loaded_asset(asset, only_if_is_dirty=False)


# ---------------------------------------------------------------- textures
def import_textures():
    tasks = []
    for f in sorted(os.listdir(SRC + "/tex")):
        if not f.endswith(".png"):
            continue
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, "tex", f)
        t.destination_path = TEX_DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    n = 0
    for path in eal.list_assets(TEX_DST, recursive=False, include_folder=False):
        tex = eal.load_asset(path)
        if not isinstance(tex, unreal.Texture2D):
            continue
        name = tex.get_name()
        if name.endswith("_N"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("flip_green_channel", False)
        elif name.endswith("_ORM"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        else:                                   # _BC, _E
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        save(tex)
        n += 1
    log.append(f"textures: {n}")


def tex(name):
    return eal.load_asset(f"{TEX_DST}/{name}")


# ---------------------------------------------------------------- the master material
def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


def build_master():
    path = MAT_DST + "/M_Weapon"
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    m = tools.create_asset("M_Weapon", MAT_DST, unreal.Material, unreal.MaterialFactoryNew())
    default_bc, default_orm, default_n = tex("T_AR181_Body_BC"), tex("T_AR181_Body_ORM"), tex("T_AR181_Body_N")
    bc = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -1000, -300, parameter_name="BaseColorMap", texture=default_bc, sampler_type=ST.SAMPLERTYPE_COLOR, group="Textures")
    orm = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -1000, 0, parameter_name="ORMMap", texture=default_orm, sampler_type=ST.SAMPLERTYPE_MASKS, group="Textures")
    nm = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -1000, 300, parameter_name="NormalMap", texture=default_n, sampler_type=ST.SAMPLERTYPE_NORMAL, group="Textures")
    em = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -1000, 600, parameter_name="EmissiveMap", texture=default_bc, sampler_type=ST.SAMPLERTYPE_COLOR, group="Textures")
    tint = E(m, unreal.MaterialExpressionVectorParameter, -700, -450, parameter_name="Tint", default_value=unreal.LinearColor(1, 1, 1, 1), group="Color")
    base = E(m, unreal.MaterialExpressionMultiply, -450, -350)
    link(bc, "RGB", base, "A")
    link(tint, "RGB", base, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    rs = E(m, unreal.MaterialExpressionScalarParameter, -700, -60, parameter_name="RoughnessScale", default_value=1.0, group="Surface")
    rm = E(m, unreal.MaterialExpressionMultiply, -450, -60)
    link(orm, "G", rm, "A")
    link(rs, "", rm, "B")
    rsat = E(m, unreal.MaterialExpressionSaturate, -250, -60)
    link(rm, "", rsat, "")
    mel.connect_material_property(rsat, "", unreal.MaterialProperty.MP_ROUGHNESS)
    ms = E(m, unreal.MaterialExpressionScalarParameter, -700, 60, parameter_name="MetallicScale", default_value=1.0, group="Surface")
    mm = E(m, unreal.MaterialExpressionMultiply, -450, 60)
    link(orm, "B", mm, "A")
    link(ms, "", mm, "B")
    msat = E(m, unreal.MaterialExpressionSaturate, -250, 60)
    link(mm, "", msat, "")
    mel.connect_material_property(msat, "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(nm, "RGB", unreal.MaterialProperty.MP_NORMAL)
    es = E(m, unreal.MaterialExpressionScalarParameter, -700, 700, parameter_name="EmissiveStrength", default_value=0.0, group="Emissive")
    ee = E(m, unreal.MaterialExpressionMultiply, -450, 640)
    link(em, "RGB", ee, "A")
    link(es, "", ee, "B")
    mel.connect_material_property(ee, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    save(m)
    log.append("master: M_Weapon")
    return m


def build_instances(master, info):
    made = []
    for part, names in info.items():
        for mi_name, t in names.items():
            path = f"{MAT_DST}/{mi_name}"
            mi = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(mi_name, MAT_DST, unreal.MaterialInstanceConstant,
                                                                                         unreal.MaterialInstanceConstantFactoryNew())
            mel.set_material_instance_parent(mi, master)
            for param, key in (("BaseColorMap", "base"), ("ORMMap", "orm"), ("NormalMap", "normal"), ("EmissiveMap", "emissive")):
                if key in t:
                    mel.set_material_instance_texture_parameter_value(mi, param, tex(os.path.splitext(t[key])[0]))
            if "emissive" in t:
                mel.set_material_instance_scalar_parameter_value(mi, "EmissiveStrength", 6.0)
            mel.update_material_instance(mi)
            save(mi)
            made.append(mi_name)
    log.append(f"instances: {made}")


# ---------------------------------------------------------------- the meshes
def import_meshes():
    tasks = []
    for f in sorted(os.listdir(SRC)):
        if not f.lower().endswith(".fbx"):
            continue
        ui = unreal.FbxImportUI()
        ui.set_editor_property("import_mesh", True)
        ui.set_editor_property("import_as_skeletal", False)
        ui.set_editor_property("import_materials", False)
        ui.set_editor_property("import_textures", False)
        ui.set_editor_property("import_animations", False)
        ui.set_editor_property("automated_import_should_detect_type", False)
        ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        d = ui.static_mesh_import_data
        d.set_editor_property("combine_meshes", True)
        d.set_editor_property("auto_generate_collision", False)
        d.set_editor_property("generate_lightmap_u_vs", False)
        d.set_editor_property("build_nanite", False)
        d.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS_AND_TANGENTS)
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, f)
        t.destination_path = DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        t.options = ui
        tasks.append(t)
    tools.import_asset_tasks(tasks)


def dress_meshes(info):
    out = []
    for key, w in info.items():
        for mesh_name in w["meshes"]:
            mesh = eal.load_asset(f"{DST}/{mesh_name}")
            if not mesh:
                out.append({"mesh": mesh_name, "error": "not imported"})
                continue
            unreal.EditorStaticMeshLibrary.remove_collisions(mesh)
            mesh.modify()
            # the slot named X gets the instance of that name
            for i, sm in enumerate(mesh.get_editor_property("static_materials")):
                slot = str(sm.get_editor_property("material_slot_name"))
                target = f"{MAT_DST}/{slot}"
                if eal.does_asset_exist(target):
                    mesh.set_material(i, eal.load_asset(target))
            # the sockets are the weapon's own (the palm origin): the gun's, not the magazine's
            have = []
            if not mesh_name.endswith("_Mag"):
                for name, p in w["sockets_cm"].items():
                    old = mesh.find_socket(name)
                    if old:
                        mesh.remove_socket(old)
                    s = unreal.new_object(unreal.StaticMeshSocket, outer=mesh)
                    s.set_editor_property("socket_name", name)
                    s.set_editor_property("relative_location", unreal.Vector(*p))
                    mesh.add_socket(s)
                    have.append(name)
            save(mesh)
            bb = mesh.get_bounding_box()
            out.append({"mesh": mesh_name, "min": [round(bb.min.x, 1), round(bb.min.y, 1), round(bb.min.z, 1)], "max": [round(bb.max.x, 1), round(bb.max.y, 1), round(bb.max.z, 1)],
                        "slots": [str(sm.get_editor_property("material_slot_name")) for sm in mesh.get_editor_property("static_materials")],
                        "materials": [sm.get_editor_property("material_interface").get_name() if sm.get_editor_property("material_interface") else None
                                      for sm in mesh.get_editor_property("static_materials")],
                        "sockets": [n for n in have if mesh.find_socket(n)]})
    return out


with open(SRC + "/weapons.json") as f:
    WEAPONS = json.load(f)
import_textures()
master = build_master()
build_instances(master, {k: v["textures"] for k, v in WEAPONS.items()})
import_meshes()
meshes = dress_meshes(WEAPONS)
print(json.dumps({"log": log, "meshes": meshes}, indent=1))
