"""The Captain's datapad (art/blender/datapad.py): its two materials (the graphite shell; the screen, which the game
paints live — AAstraPlayerController::TickPad) and the mesh (/Game/ASTRA/Kit/Props/SM_PROP_Datapad, classic: it is
held in front of the camera). Idempotent. tools/ue.py pyfile tools/ue_scripts/build_datapad.py
"""
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
HARD = "/Game/ASTRA/Materials/M_ASTRA_Hard"
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def mi(name, parent_path, scalars=None, vectors=None, textures=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, eal.load_asset(parent_path))
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(v))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)


# the shell: graphite composite, a little worn at the edges
mi("MI_PAD_Body", HARD, {"RoughnessMin": 0.42, "RoughnessMax": 0.62, "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                         "BaseColorMapInfluence": 0.25, "NormalStrength": 0.35, "UVScale": 4.0, "MacroBrightness": 0.04,
                         "ScratchRoughness": 0.08, "RoughnessVariation": 0.1},
   {"Tint": (0.028, 0.03, 0.034)},
   {"BaseColorMap": f"{TEX}/T_PanelPaint_BC", "NormalMap": f"{TEX}/T_PanelPaint_N", "ORMMap": f"{TEX}/T_PanelPaint_ORM"})
# the screen: the game sets its ScreenTexture to the live page
mi("MI_PAD_Screen", SCREEN, {"Intensity": 2.2, "Roughness": 0.18, "FlipU": 0.0, "FlipV": 0.0})

SRC = os.path.join(ROOT, "art", "export", "datapad")
DST = "/Game/ASTRA/Kit/Props"
NANITE = False
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())
print("DATAPAD_IMPORT_OK")
