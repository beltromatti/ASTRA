"""Holographic materials for the tactical table (AAstraHoloTable). Idempotent: rebuilt in place.

  M_ASTRA_Holo      additive unlit: Color, Intensity, Fade; fresnel edges, scanlines in world Z, faint flicker
  MI_ASTRA_Holo     default instance (slot name of the SM_HOLO_* meshes)
  M_ASTRA_HoloGrid  projection disc: range rings, bearing spokes, rotating sweep, bright rim (planar UVs)
  M_ASTRA_HoloText  text for UTextRenderComponent: distance-field font (parameter "Font"), colour from the text colour

tools/ue.py pyfile tools/ue_scripts/make_holo_materials.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DIR = "/Game/ASTRA/Materials"
INST = "/Game/ASTRA/Materials/Instances"
log = []


def material(name, blend=unreal.BlendMode.BLEND_ADDITIVE):
    p = f"{DIR}/{name}"
    if eal.does_asset_exist(p):
        m = eal.load_asset(p)
        for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
    else:
        m = tools.create_asset(name, DIR, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", True)
    return m


def expr(m, cls, x, y, **props):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def custom(m, x, y, code, inputs, out_type=unreal.CustomMaterialOutputType.CMOT_FLOAT3):
    c = expr(m, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("code", code)
    c.set_editor_property("output_type", out_type)
    ins = []
    for name in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", name)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    return c


def finish(m):
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)


# ------------------------------------------------------------------------------------------ M_ASTRA_Holo
m = material("M_ASTRA_Holo")
col = expr(m, unreal.MaterialExpressionVectorParameter, -900, -100, parameter_name="Color", default_value=unreal.LinearColor(0.3, 0.8, 1.0, 1))
inten = expr(m, unreal.MaterialExpressionScalarParameter, -900, 50, parameter_name="Intensity", default_value=30.0)
fade = expr(m, unreal.MaterialExpressionScalarParameter, -900, 130, parameter_name="Fade", default_value=1.0)
edges = expr(m, unreal.MaterialExpressionScalarParameter, -900, 210, parameter_name="EdgeMix", default_value=0.55)
wp = expr(m, unreal.MaterialExpressionWorldPosition, -900, 290)
t = expr(m, unreal.MaterialExpressionTime, -900, 370)
fr = expr(m, unreal.MaterialExpressionFresnel, -900, 450)
fr.set_editor_property("exponent", 2.0)
fr.set_editor_property("base_reflect_fraction", 0.08)
c = custom(m, -500, 100, """
float scan = 0.78 + 0.22 * sin(WP.z * 0.9 + T * 3.0);
float flick = 0.94 + 0.06 * sin(T * 37.0) * sin(T * 23.0 + 1.3);
return Col * I * Fade * lerp(1.0, 0.25 + 1.5 * Fr, EdgeMix) * scan * flick;
""", ["Col", "I", "Fade", "EdgeMix", "WP", "T", "Fr"])
for src, pin in ((col, "Col"), (inten, "I"), (fade, "Fade"), (edges, "EdgeMix"), (wp, "WP"), (t, "T"), (fr, "Fr")):
    mel.connect_material_expressions(src, "RGB" if src is col else "", c, pin)
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
finish(m)
log.append("M_ASTRA_Holo")

mi_path = f"{INST}/MI_ASTRA_Holo"
mi = eal.load_asset(mi_path) if eal.does_asset_exist(mi_path) else tools.create_asset(
    "MI_ASTRA_Holo", INST, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(mi, m)
eal.save_loaded_asset(mi, only_if_is_dirty=False)
log.append("MI_ASTRA_Holo")

# ------------------------------------------------------------------------------------------ M_ASTRA_HoloGrid
g = material("M_ASTRA_HoloGrid")
col = expr(g, unreal.MaterialExpressionVectorParameter, -900, -100, parameter_name="Color", default_value=unreal.LinearColor(0.25, 0.7, 1.0, 1))
inten = expr(g, unreal.MaterialExpressionScalarParameter, -900, 50, parameter_name="Intensity", default_value=14.0)
rings = expr(g, unreal.MaterialExpressionScalarParameter, -900, 130, parameter_name="RingCount", default_value=4.0)
uv = expr(g, unreal.MaterialExpressionTextureCoordinate, -900, 210)
t = expr(g, unreal.MaterialExpressionTime, -900, 290)
c = custom(g, -500, 100, """
float2 p = UV * 2.0 - 1.0;
float d = length(p);
if (d > 1.0) return float3(0, 0, 0);
float rl = pow(saturate(1.0 - abs(frac(d * N) - 0.5) * 2.0), 48.0) * step(0.02, d);
float a = atan2(p.y, p.x);
float sp = pow(saturate(1.0 - abs(frac(a / 6.2831853 * 12.0) - 0.5) * 2.0), 90.0) * saturate(d * 5.0 - 0.3);
float sw = pow(frac(a / 6.2831853 - T * 0.07), 14.0);
float rim = pow(saturate(1.0 - abs(d - 0.985) * 70.0), 2.0);
float edge = smoothstep(1.0, 0.96, d);
return Col * I * (0.035 + 0.22 * rl + 0.12 * sp + 0.22 * sw * edge + 0.7 * rim) * edge;
""", ["UV", "Col", "I", "N", "T"])
for src, pin in ((uv, "UV"), (col, "Col"), (inten, "I"), (rings, "N"), (t, "T")):
    mel.connect_material_expressions(src, "RGB" if src is col else "", c, pin)
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
finish(g)
log.append("M_ASTRA_HoloGrid")

# ------------------------------------------------------------------------------------------ M_ASTRA_HoloText
tx = material("M_ASTRA_HoloText")
font = unreal.load_object(None, "/Engine/EngineFonts/RobotoDistanceField.RobotoDistanceField")
fs = expr(tx, unreal.MaterialExpressionFontSampleParameter, -900, 0, parameter_name="Font")
fs.set_editor_property("font", font)
vc = expr(tx, unreal.MaterialExpressionVertexColor, -900, 200)
inten = expr(tx, unreal.MaterialExpressionScalarParameter, -900, 320, parameter_name="Intensity", default_value=12.0)
c = custom(tx, -500, 100, """
float m = smoothstep(0.44, 0.56, F);
return VC.rgb * I * m;
""", ["F", "VC", "I"])
ok = mel.connect_material_expressions(fs, "A", c, "F")
log.append(f"font alpha connected: {ok}")
ok2 = mel.connect_material_expressions(vc, "", c, "VC")
ok3 = mel.connect_material_expressions(inten, "", c, "I")
log.append(f"vertex colour connected: {ok2}, intensity: {ok3}")
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
finish(tx)
log.append("M_ASTRA_HoloText")
print(json.dumps(log))
