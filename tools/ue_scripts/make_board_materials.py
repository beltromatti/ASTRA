"""Materials of the boarding kit (ABBORDAGGI-3): the finishes of the decks of a boarded ship. Idempotent. Run in the editor (not during PIE), once, before import_board_kit.py:
  tools/ue.py pyfile tools/ue_scripts/make_board_materials.py

Creates, in /Game/ASTRA/Materials/Instances and named exactly like the slots of the kit's meshes (art/blender/board_kit_defs.py), so that astra_editor.assign_materials_by_slot finds them:
  MI_BRD_Plating / Frame / Iron / Copper / Verdigris / Deck / Hazard / Soot / Stencil / Cloth / Uniform / Skin    M_ASTRA_Hard instances: the Kharon Mandate's basalt and graphite, black iron,
                                                                                                                 oxidised copper and verdigris, worn hazard paint, stencil bronze, rust-red
                                                                                                                 cloth (docs/STILE.md §3), the fallen's coverall and skin
  MI_BRD_Screen                                                                                                  M_ASTRA_Emissive: a dead console's glass, black with a trace of amber
The numbers are those of the contact sheets' preview (art/blender/board_kit_view.py MATS): what was judged there is what the game shows. The lamps of the kit are the bridge's palette lamps (MI_BRG3_Lamps /
LampsDim / LampsHot, from make_bridge_v3_materials.py) and the rubber is MI_ASTRA_Rubber: this script does not make them. The ships of the other sides are the same instances with another Tint, made as
dynamic instances by the game (AstraBoardDress), so nothing here is per side.
"""
import json

import unreal

MAT = "/Game/ASTRA/Materials"
MI_DIR = f"{MAT}/Instances"
TEX = f"{MAT}/Textures"
HARD = f"{MAT}/M_ASTRA_Hard"
EMISSIVE = f"{MAT}/M_ASTRA_Emissive"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
log = []


def srgb_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def mi(name, parent_path, scalars=None, vectors=None, textures=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, eal.load_asset(parent_path))
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(v))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    log.append(name)


for need in (HARD, EMISSIVE):
    if not eal.does_asset_exist(need):
        raise RuntimeError(f"{need} is missing: run make_materials.py first")


def maps(tex_set):
    out = {}
    for param, suffix in (("BaseColorMap", "BC"), ("NormalMap", "N"), ("ORMMap", "ORM")):
        path = f"{TEX}/T_{tex_set}_{suffix}"
        if not eal.does_asset_exist(path):
            raise RuntimeError(f"{path} is missing (the project's packed texture sets are made by make_materials.py)")
        out[param] = path
    return out


def hard(name, hex_color, tex_set, uv, rough, metal, metal_map, influence=0.5, normal=0.6, macro=0.08):
    """One finish of the kit: the numbers of board_kit_view.MATS (tint, texture set, UV scale, roughness range, metallic = bias + map * scale)."""
    mi(name, HARD,
       {"RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": metal_map, "MetallicBias": metal, "BaseColorMapInfluence": influence, "NormalStrength": normal, "UVScale": uv,
        "MacroBrightness": macro, "ScratchRoughness": 0.1, "RoughnessVariation": 0.1},
       {"Tint": srgb_to_linear(hex_color)}, maps(tex_set))


# the Mandate's finishes (docs/STILE.md §3: graphite and basalt, black iron, copper and verdigris, amber and red lights)
hard("MI_BRD_Plating", "#4A4540", "Gunmetal", 1.0, (0.45, 0.8), 0.0, 0.5)
hard("MI_BRD_Frame", "#2A2C30", "Gunmetal", 1.0, (0.3, 0.6), 0.35, 0.5)
hard("MI_BRD_Iron", "#1A1B1E", "Gunmetal", 1.0, (0.35, 0.7), 0.5, 0.5)
hard("MI_BRD_Copper", "#8C5A2B", "Brushed", 1.0, (0.3, 0.55), 1.0, 0.0)
hard("MI_BRD_Verdigris", "#5F7F6B", "Brushed", 1.0, (0.4, 0.7), 0.6, 0.0)
hard("MI_BRD_Deck", "#3B3A3C", "DiamondPlate", 1.0, (0.4, 0.75), 0.6, 0.0)
hard("MI_BRD_Hazard", "#B07816", "PanelPaint", 1.0, (0.5, 0.8), 0.0, 0.0)
hard("MI_BRD_Soot", "#09090A", "PanelPaint", 1.0, (0.8, 0.95), 0.0, 0.0)
hard("MI_BRD_Stencil", "#B78A55", "PanelPaint", 1.0, (0.6, 0.85), 0.0, 0.0)
hard("MI_BRD_Cloth", "#6B2E1E", "FabricWoven", 2.0, (0.8, 0.95), 0.0, 0.0)
hard("MI_BRD_Uniform", "#2A2823", "FabricWoven", 3.0, (0.85, 0.95), 0.0, 0.0)
hard("MI_BRD_Skin", "#7B5C49", "PanelPaint", 1.0, (0.55, 0.75), 0.0, 0.0, influence=0.0, normal=0.0)
mi("MI_BRD_Screen", EMISSIVE, {"Intensity": 0.15, "Roughness": 0.25, "PulseSpeed": 0.0, "PulseAmount": 0.0}, {"EmissiveColor": (1.0, 0.45, 0.06), "BaseColor": (0.004, 0.004, 0.005)})

# the lamps and the rubber the kit shares with the Aquila: they must exist (the kit's meshes use them)
for shared in ("MI_BRG3_Lamps", "MI_BRG3_LampsDim", "MI_BRG3_LampsHot", "MI_ASTRA_Rubber"):
    if not eal.does_asset_exist(f"{MI_DIR}/{shared}"):
        log.append(f"MISSING {shared} (run make_bridge_v3_materials.py / make_materials.py)")

print(json.dumps({"made": [n for n in log if not n.startswith("MISSING")], "problems": [n for n in log if n.startswith("MISSING")]}, indent=1))
