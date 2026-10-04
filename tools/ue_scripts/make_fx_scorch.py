"""The battle scar decal (tools/art/scorch.py): M_FX_ScorchDecal, a deferred decal that burns the plating where a hit
lands — soot and bare metal (R), glowing cracks while it is hot (G x Heat), the torn centre of a heavy hit (B x Breach,
black with a molten rim while hot), all where A says; Fade takes it away. The game sets Heat, Breach and Fade per scar.
  tools/ue.py pyfile tools/ue_scripts/make_fx_scorch.py
"""
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
TEX = "/Game/ASTRA/Materials/Textures"
MAT = "/Game/ASTRA/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

t = unreal.AssetImportTask()
t.filename = os.path.join(ROOT, "art", "_cache", "fx", "T_FX_Scorch.png")
t.destination_path = TEX
t.automated = True
t.replace_existing = True
t.save = False
tools.import_asset_tasks([t])
tx = eal.load_asset(f"{TEX}/T_FX_Scorch")
tx.set_editor_property("srgb", False)                       # data, not colour
tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
tx.set_editor_property("never_stream", True)                # decals made at run time get no streaming
eal.save_loaded_asset(tx, only_if_is_dirty=False)

path = f"{MAT}/M_FX_ScorchDecal"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy: UE 5.8's delete_all walks the list it removes from, and crashed the editor)
else:
    m = tools.create_asset("M_FX_ScorchDecal", MAT, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)


def E(cls, x, y, **pp):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in pp.items():
        e.set_editor_property(k, v)
    return e


def L(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"{a.get_name()}.{ao} -> {b.get_name()}.{bi}")


tex = E(unreal.MaterialExpressionTextureSampleParameter2D, -1100, 0, parameter_name="Scar", texture=tx,
        sampler_type=unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
heat = E(unreal.MaterialExpressionScalarParameter, -1100, 300, parameter_name="Heat", default_value=1.0)
breach_p = E(unreal.MaterialExpressionScalarParameter, -1100, 400, parameter_name="Breach", default_value=0.0)
fade = E(unreal.MaterialExpressionScalarParameter, -1100, 500, parameter_name="Fade", default_value=1.0)
ember_col = E(unreal.MaterialExpressionVectorParameter, -1100, 600, parameter_name="EmberColor",
              default_value=unreal.LinearColor(1.0, 0.33, 0.07, 1))
# base colour: deep soot where burnt, a scorched grey where only licked; black in the breach
soot_dark = E(unreal.MaterialExpressionConstant3Vector, -800, -250, constant=unreal.LinearColor(0.005, 0.0045, 0.004, 1))
soot_light = E(unreal.MaterialExpressionConstant3Vector, -800, -150, constant=unreal.LinearColor(0.035, 0.03, 0.026, 1))
lerp_soot = E(unreal.MaterialExpressionLinearInterpolate, -550, -200)
L(soot_light, "", lerp_soot, "A")
L(soot_dark, "", lerp_soot, "B")
L(tex, "R", lerp_soot, "Alpha")
breach_mask = E(unreal.MaterialExpressionMultiply, -800, 380)
L(tex, "B", breach_mask, "A")
L(breach_p, "", breach_mask, "B")
black = E(unreal.MaterialExpressionConstant3Vector, -550, -50, constant=unreal.LinearColor(0.0, 0.0, 0.0, 1))
base = E(unreal.MaterialExpressionLinearInterpolate, -300, -150)
L(lerp_soot, "", base, "A")
L(black, "", base, "B")
L(breach_mask, "", base, "Alpha")
mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
rough = E(unreal.MaterialExpressionConstant, -300, 50, r=0.9)
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
# emissive: the cracks glow while hot (Heat^2: they dim fast at first), the breach's rim glows harder
heat2 = E(unreal.MaterialExpressionMultiply, -800, 250)
L(heat, "", heat2, "A")
L(heat, "", heat2, "B")
glow_mask = E(unreal.MaterialExpressionAdd, -550, 300)
L(tex, "G", glow_mask, "A")
rim = E(unreal.MaterialExpressionMultiply, -800, 480)
L(breach_mask, "", rim, "A")
rim_k = E(unreal.MaterialExpressionConstant, -1000, 700, r=1.5)
L(rim_k, "", rim, "B")
L(rim, "", glow_mask, "B")
glow = E(unreal.MaterialExpressionMultiply, -300, 250)
L(glow_mask, "", glow, "A")
L(heat2, "", glow, "B")
glow_col = E(unreal.MaterialExpressionMultiply, -150, 250)
L(glow, "", glow_col, "A")
L(ember_col, "", glow_col, "B")
glow_k = E(unreal.MaterialExpressionConstant, -300, 420, r=30.0)
emis = E(unreal.MaterialExpressionMultiply, 0, 250)
L(glow_col, "", emis, "A")
L(glow_k, "", emis, "B")
mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
op = E(unreal.MaterialExpressionMultiply, -300, 600)
L(tex, "A", op, "A")
L(fade, "", op, "B")
op_k = E(unreal.MaterialExpressionConstant, -300, 720, r=1.6)          # the burn reads on white paint
op2 = E(unreal.MaterialExpressionMultiply, -150, 600)
L(op, "", op2, "A")
L(op_k, "", op2, "B")
op_sat = E(unreal.MaterialExpressionSaturate, 0, 600)
L(op2, "", op_sat, "")
mel.connect_material_property(op_sat, "", unreal.MaterialProperty.MP_OPACITY)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
print("SCORCH_MATERIAL_OK")
