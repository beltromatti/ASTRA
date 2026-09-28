"""Crew uniforms for the placeholder bodies (until the MetaHuman crew): matte navy trousers, a jacket in the
department colour (docs/STILE.md §3: command blue, security red, science violet, engineering amber, flight yellow).
tools/ue.py pyfile tools/ue_scripts/make_crew_materials.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DIR = "/Game/ASTRA/Crew/Materials"
HARD = eal.load_asset("/Game/ASTRA/Materials/M_ASTRA_Hard")
TEX = "/Game/ASTRA/Materials/Textures"


def mi(name, tint, rough=(0.62, 0.82)):
    p = f"{DIR}/{name}"
    m = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, DIR, unreal.MaterialInstanceConstant,
                                                                            unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(m, HARD)
    mel.set_material_instance_vector_parameter_value(m, "Tint", unreal.LinearColor(*tint, 1.0))
    for k, v in (("RoughnessMin", rough[0]), ("RoughnessMax", rough[1]), ("MetallicFromMap", 0.0), ("MetallicBias", 0.0),
                 ("BaseColorMapInfluence", 0.25), ("MacroBrightness", 0.04), ("NormalStrength", 0.35), ("ScratchRoughness", 0.0),
                 ("UVScale", 4.0)):
        mel.set_material_instance_scalar_parameter_value(m, k, v)
    for k, t in (("BaseColorMap", "T_DeckRubber_BC"), ("NormalMap", "T_DeckRubber_N"), ("ORMMap", "T_DeckRubber_ORM")):
        tex = eal.load_asset(f"{TEX}/{t}")
        if tex:
            mel.set_material_instance_texture_parameter_value(m, k, tex)
    mel.update_material_instance(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    return name


made = [mi("MI_Crew_Uniform", (0.016, 0.02, 0.034)),
        mi("MI_Crew_Dept_Command", (0.028, 0.06, 0.2)),
        mi("MI_Crew_Dept_Security", (0.16, 0.022, 0.024)),
        mi("MI_Crew_Dept_Science", (0.075, 0.035, 0.15)),
        mi("MI_Crew_Dept_Engineering", (0.2, 0.09, 0.012)),
        mi("MI_Crew_Dept_Flight", (0.2, 0.15, 0.01))]
print(json.dumps(made))
