"""M_ASTRA_HullDecalRT: the hull marking decal for names drawn at run time (UAstraHullName): white text on black in a
render target, so the mask is the red channel (a canvas does not write alpha reliably); Color paints it.
  tools/ue.py pyfile tools/ue_scripts/make_hull_decal_rt.py
"""
import unreal

MAT = "/Game/ASTRA/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
path = f"{MAT}/M_ASTRA_HullDecalRT"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    mel.delete_all_material_expressions(m)
else:
    m = tools.create_asset("M_ASTRA_HullDecalRT", MAT, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)


def E(cls, x, y, **pp):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in pp.items():
        e.set_editor_property(k, v)
    return e


tex = E(unreal.MaterialExpressionTextureSampleParameter2D, -700, 0, parameter_name="Marking",
        texture=eal.load_asset("/Game/ASTRA/Materials/Textures/T_HULL_Name_Aquila"))
col = E(unreal.MaterialExpressionVectorParameter, -700, -200, parameter_name="Color", default_value=unreal.LinearColor(0.004, 0.009, 0.035, 1))
op = E(unreal.MaterialExpressionScalarParameter, -700, 250, parameter_name="Opacity", default_value=0.95)
mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
opm = E(unreal.MaterialExpressionMultiply, -400, 150)
mel.connect_material_expressions(tex, "R", opm, "A")
mel.connect_material_expressions(op, "", opm, "B")
mel.connect_material_property(opm, "", unreal.MaterialProperty.MP_OPACITY)
rough = E(unreal.MaterialExpressionConstant, -400, 300, r=0.5)
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
print("HULL_DECAL_RT_OK")
