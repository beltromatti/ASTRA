"""Screen materials: imports art/_cache/ui/T_UI_*.png, builds M_ASTRA_Screen (emissive UI behind glossy glass,
FlipU/FlipV), default slot instances MI_ASTRA_Screen{A,B,C,Touch,Tactical,Holo,Master} and per-station instances
MI_UI_<Station>_<Slot>. Idempotent."""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
SRC = "/Users/beltromatti/Desktop/ASTRA/art/_cache/ui"
TEX = "/Game/ASTRA/UI/Textures"
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
UI_MI = "/Game/ASTRA/UI/Materials"
log = []

tasks = []
for f in sorted(os.listdir(SRC)):
    if f.endswith(".png"):
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, f)
        t.destination_path = TEX
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
tools.import_asset_tasks(tasks)
for p in eal.list_assets(TEX, recursive=False, include_folder=False):
    tex = eal.load_asset(p)
    if isinstance(tex, unreal.Texture2D):
        tex.set_editor_property("srgb", True)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tex, only_if_is_dirty=False)
log.append(f"ui textures: {len(tasks)}")

path = f"{MAT}/M_ASTRA_Screen"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
else:
    m = tools.create_asset("M_ASTRA_Screen", MAT, unreal.Material, unreal.MaterialFactoryNew())


def E(cls, x, y, **p):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in p.items():
        e.set_editor_property(k, v)
    return e


def L(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"{a.get_name()}.{ao} -> {b.get_name()}.{bi}")


def S(name, v, x, y):
    return E(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v, group="Screen")


uv = E(unreal.MaterialExpressionTextureCoordinate, -1400, 0)
flip = E(unreal.MaterialExpressionAppendVector, -1250, 150)
L(S("FlipU", 0.0, -1400, 120), "", flip, "A")
L(S("FlipV", 0.0, -1400, 200), "", flip, "B")
one = E(unreal.MaterialExpressionConstant2Vector, -1400, 300, r=1.0, g=1.0)
inv = E(unreal.MaterialExpressionSubtract, -1150, 250)
L(one, "", inv, "A")
L(uv, "", inv, "B")
lerp = E(unreal.MaterialExpressionLinearInterpolate, -950, 100)
L(uv, "", lerp, "A")
L(inv, "", lerp, "B")
L(flip, "", lerp, "Alpha")
tex = E(unreal.MaterialExpressionTextureSampleParameter2D, -700, 100, parameter_name="ScreenTexture",
        texture=eal.load_asset(f"{TEX}/T_UI_Helm_A"), group="Screen")
L(lerp, "", tex, "UVs")
emis = E(unreal.MaterialExpressionMultiply, -400, 100)
L(tex, "RGB", emis, "A")
L(S("Intensity", 6.0, -700, 350), "", emis, "B")
mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
base = E(unreal.MaterialExpressionConstant3Vector, -400, -150, constant=unreal.LinearColor(0.01, 0.012, 0.015, 1))
mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(S("Roughness", 0.14, -400, 400), "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(S("Specular", 0.5, -400, 480), "", unreal.MaterialProperty.MP_SPECULAR)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append("M_ASTRA_Screen ok")


def mi(folder, name, texture, flip_u=0.0, flip_v=0.0, intensity=None):
    p = f"{folder}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(
        name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, m)
    mel.set_material_instance_texture_parameter_value(inst, "ScreenTexture", eal.load_asset(f"{TEX}/T_UI_{texture}"))
    mel.set_material_instance_scalar_parameter_value(inst, "FlipU", flip_u)
    mel.set_material_instance_scalar_parameter_value(inst, "FlipV", flip_v)
    if intensity is not None:
        mel.set_material_instance_scalar_parameter_value(inst, "Intensity", intensity)
    mel.set_material_instance_scalar_parameter_value(inst, "Roughness", 0.35)     # matte anti-glare coating
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    return inst


FLIP = globals().get("FLIP", {})   # {"Tactical": (1, 0), ...} orientation fixes found by visual checks
for slot, tex_name in (("A", "Helm_A"), ("B", "Helm_B"), ("C", "Helm_C"), ("Touch", "Helm_Touch"), ("Tactical", "Tactical"),
                       ("Holo", "Holo"), ("Master", "Master")):
    fu, fv = FLIP.get(slot, (0.0, 0.0))
    mi(MI, f"MI_ASTRA_Screen{slot}", tex_name, fu, fv, intensity=8.0 if slot == "Touch" else 22.0)
for st in ("Helm", "Ops", "Comms", "Sensors", "Eng", "Flight"):
    for slot in ("A", "B", "C", "Touch"):
        fu, fv = FLIP.get(slot, (0.0, 0.0))
        mi(UI_MI, f"MI_UI_{st}_{slot}", f"{st}_{slot}", fu, fv, intensity=8.0 if slot == "Touch" else 22.0)
log.append("screen instances ok")
print(json.dumps(log))
