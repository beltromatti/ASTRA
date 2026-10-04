"""Hull markings as decals: M_ASTRA_HullDecal (a deferred decal: paint = Color x the texture, where its alpha says) and
one instance per ship name (MI_HULL_Name_<Ship>, textures from tools/art/hull_markings.py).
  tools/ue.py pyfile tools/ue_scripts/make_hull_decals.py
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = ROOT + "/art/_cache/signage"
TEX = "/Game/ASTRA/Materials/Textures"
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
log = []

# the textures
tasks = []
for f in sorted(os.listdir(SRC)):
    if f.startswith("T_HULL_") and f.endswith(".png"):
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, f)
        t.destination_path = TEX
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
tools.import_asset_tasks(tasks)
names = [os.path.splitext(os.path.basename(t.filename))[0] for t in tasks]
for n in names:
    tx = eal.load_asset(f"{TEX}/{n}")
    tx.set_editor_property("srgb", True)
    tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    tx.set_editor_property("never_stream", True)   # decals made at run time get no streaming: whole, always
    eal.save_loaded_asset(tx, only_if_is_dirty=False)
log.append(f"textures {names}")

# the material
path = f"{MAT}/M_ASTRA_HullDecal"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
else:
    m = tools.create_asset("M_ASTRA_HullDecal", MAT, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)


def E(cls, x, y, **pp):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in pp.items():
        e.set_editor_property(k, v)
    return e


tex = E(unreal.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name="Marking",
        texture=eal.load_asset(f"{TEX}/{names[0]}"))
col = E(unreal.MaterialExpressionVectorParameter, -700, -200, parameter_name="Color", default_value=unreal.LinearColor(0.004, 0.009, 0.035, 1))
op = E(unreal.MaterialExpressionScalarParameter, -700, 250, parameter_name="Opacity", default_value=1.0)
mul = E(unreal.MaterialExpressionMultiply, -400, -100)
mel.connect_material_expressions(col, "", mul, "A")
mel.connect_material_expressions(tex, "RGB", mul, "B")
mel.connect_material_property(mul, "", unreal.MaterialProperty.MP_BASE_COLOR)
opm = E(unreal.MaterialExpressionMultiply, -400, 150)
mel.connect_material_expressions(tex, "A", opm, "A")
mel.connect_material_expressions(op, "", opm, "B")
mel.connect_material_property(opm, "", unreal.MaterialProperty.MP_OPACITY)
rough = E(unreal.MaterialExpressionConstant, -400, 300, r=0.5)
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)

# an instance per name
for n in names:
    ship = n.replace("T_HULL_Name_", "")
    p = f"{MI}/MI_HULL_Name_{ship}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(f"MI_HULL_Name_{ship}", MI, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, m)
    mel.set_material_instance_texture_parameter_value(inst, "Marking", eal.load_asset(f"{TEX}/{n}"))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    log.append(f"MI_HULL_Name_{ship}")
print(json.dumps(log))
