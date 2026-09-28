"""The grounds of the other worlds (AAstraWorldSurface): M_ASTRA_Terrain's five layers re-dressed for each kind of world
— sand and red rock (desert), snow and blue ice (ice), grey rock and dust (barren), black basalt and ash (lava); ocean
worlds keep New Ravenna's dress (the lava is tools/ue_scripts/make_lava_material.py).
  tools/ue.py pyfile tools/ue_scripts/make_world_materials.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MI = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
TERRAIN = eal.load_asset("/Game/ASTRA/Materials/M_ASTRA_Terrain")
NR = eal.load_asset(f"{MI}/MI_NR_Terrain")
made = []


def mi(name, parent):
    p = f"{MI}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, parent)
    return inst


def world(kind, layers, tints, snow_line, shore=0.0, strata=0.0):
    """layers: the texture set each layer wears (Rock, Grass, Meadow, Sand, Snow -> a set name); shore: beach and wet sand
    at z = 0 (only where a sea or a frozen sea lies there)."""
    inst = mi(f"MI_W_Terrain_{kind}", TERRAIN)
    # start from New Ravenna's dress, then change what differs
    for p in NR.get_editor_property("scalar_parameter_values"):
        mel.set_material_instance_scalar_parameter_value(inst, str(p.parameter_info.name), p.parameter_value)
    mel.set_material_instance_scalar_parameter_value(inst, "Shore", shore)
    mel.set_material_instance_scalar_parameter_value(inst, "Strata", strata)
    tints = dict({"RockTint": (1.0, 1.0, 1.0)}, **tints)
    for layer, tex_set in layers.items():
        for k in ("BC", "N", "ORM"):
            mel.set_material_instance_texture_parameter_value(inst, f"{layer}{k}", eal.load_asset(f"{TEX}/T_{tex_set}_{k}"))
        if layer == "Rock":
            for side in ("RockBC_XZ", "RockBC_YZ"):
                mel.set_material_instance_texture_parameter_value(inst, side, eal.load_asset(f"{TEX}/T_{tex_set}_BC"))
    for k, v in tints.items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    mel.set_material_instance_scalar_parameter_value(inst, "SnowLine", snow_line)
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    made.append(inst.get_name())


world("Ocean", {}, {}, 1450.0, shore=1.0)
# red sandstone walls in strata, over sand
world("Desert", {"Rock": "RockRed", "Grass": "Sand", "Meadow": "Sand", "Snow": "Sand"},
      {"GrassTint": (0.95, 0.66, 0.44), "MeadowTint": (1.0, 0.8, 0.6), "Tint": (1.0, 0.84, 0.7), "RockTint": (1.25, 1.05, 0.95)}, 99999.0,
      strata=1.0)
# snow, and pale rock gone blue-grey; the sea ice at z = 0 keeps the glazed shore look
world("Ice", {"Rock": "RockLight", "Grass": "Snow", "Meadow": "Snow", "Sand": "Snow"},
      {"GrassTint": (0.86, 0.92, 1.0), "MeadowTint": (0.76, 0.86, 1.0), "Tint": (0.94, 0.97, 1.0), "RockTint": (0.42, 0.47, 0.55)}, -50.0, shore=1.0)
# grey regolith, barely varied, over pale grey rock
world("Barren", {"Rock": "RockLight", "Grass": "Sand", "Meadow": "Sand", "Snow": "Rock"},
      {"GrassTint": (0.62, 0.6, 0.58), "MeadowTint": (0.52, 0.5, 0.48), "Tint": (0.8, 0.78, 0.76), "RockTint": (0.55, 0.54, 0.52)}, 99999.0)
# black basalt, ash on the flats
world("Lava", {"Grass": "Sand", "Meadow": "Rock", "Sand": "Rock", "Snow": "Rock"},
      {"GrassTint": (0.2, 0.19, 0.19), "MeadowTint": (0.34, 0.31, 0.3), "Tint": (0.6, 0.56, 0.54), "RockTint": (0.9, 0.85, 0.82)}, 99999.0)

# the lava itself (MI_W_Lava) is M_ASTRA_Lava: tools/ue_scripts/make_lava_material.py
print(json.dumps(made))
