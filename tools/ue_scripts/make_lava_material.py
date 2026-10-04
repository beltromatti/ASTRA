"""M_ASTRA_Lava (+ MI_W_Lava): the lava of the volcanic worlds (AAstraWorldSurface's sea on a lava world) — dark crust
plates drifting slowly over glowing cracks, the heat breathing, bright where the crust breaks. World-aligned (metres),
two samplings of the macro noise at different scales and drifts, no UVs needed.
  tools/ue.py pyfile tools/ue_scripts/make_lava_material.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
ST = unreal.MaterialSamplerType
OUT = unreal.CustomMaterialOutputType


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


def custom(mat, code, inputs, x, y, out=OUT.CMOT_FLOAT4):
    c = E(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("output_type", out)
    c.set_editor_property("code", code)
    ins = []
    for nm, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", nm)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    for nm, (src, src_out) in inputs:
        link(src, src_out, c, nm)
    return c


def scalar(mat, name, value, x, y):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group="Lava")


def vector(mat, name, rgba, x, y):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group="Lava")


path = f"{MAT}/M_ASTRA_Lava"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy: UE 5.8's delete_all walks the list it removes from, and crashed the editor)
    for e in mel.get_material_expressions(m):
        mel.delete_material_expression(m, e)
else:
    m = tools.create_asset("M_ASTRA_Lava", MAT, unreal.Material, unreal.MaterialFactoryNew())

noise = eal.load_asset("/Game/ASTRA/Materials/Textures/T_ASTRA_MacroNoise")
wp = E(m, unreal.MaterialExpressionWorldPosition, -1600, 0)
t = E(m, unreal.MaterialExpressionTime, -1600, 150)
uv1 = custom(m, "return W.xy * 0.01 / 520.0 + float2(T * 0.0002, T * 0.00012);", [("W", (wp, "")), ("T", (t, ""))], -1350, 0, OUT.CMOT_FLOAT2)
uv2 = custom(m, "float2 p = W.xy * 0.01; return float2(p.x * 0.6 - p.y * 0.8, p.x * 0.8 + p.y * 0.6) / 140.0 - float2(T * 0.0006, T * 0.0003);",
             [("W", (wp, "")), ("T", (t, ""))], -1350, 150, OUT.CMOT_FLOAT2)
s1 = E(m, unreal.MaterialExpressionTextureSample, -1100, 0, texture=noise, sampler_type=ST.SAMPLERTYPE_MASKS)
link(uv1, "", s1, "UVs")
s2 = E(m, unreal.MaterialExpressionTextureSample, -1100, 250, texture=noise, sampler_type=ST.SAMPLERTYPE_MASKS)
link(uv2, "", s2, "UVs")
look = custom(m, """
// crust plates where the two noises agree, glowing seams between them, a slow breathing of the heat
float n = A.r * 0.62 + B.g * 0.38;
float crust = smoothstep(Seam, Seam + 0.07, n) * smoothstep(1.0 - Seam * 0.3, 0.7 - Seam * 0.3, abs(A.b - 0.5) * 2.0 + 0.3);
// far off, the plates would repeat as a lattice: they fade into an even glow, broken only by the broad noise
float far = saturate((D * 0.01 - 1500.0) / 5000.0);
crust = lerp(crust, 0.58, far);
float hot = 1.0 - crust;
float breathe = lerp(0.8 + 0.2 * sin(T * 0.6 + A.g * 9.0), 0.9, far);
float3 emis = Hot * (hot * hot * breathe + 0.015 * B.r) * Intensity;
return float4(emis, crust);
""", [("A", (s1, "RGB")), ("B", (s2, "RGB")), ("T", (t, "")), ("D", (E(m, unreal.MaterialExpressionPixelDepth, -900, 350), "")), ("Hot", (vector(m, "HotColor", (1.0, 0.32, 0.06, 1), -900, 450), "RGB")),
      ("Intensity", (scalar(m, "Intensity", 700.0, -900, 650), "")), ("Seam", (scalar(m, "Seam", 0.44, -900, 750), ""))], -700, 200)
emis = E(m, unreal.MaterialExpressionComponentMask, -400, 150, r=True, g=True, b=True)
link(look, "", emis, "")
mel.connect_material_property(emis, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
crust = E(m, unreal.MaterialExpressionComponentMask, -400, 300, a=True)
link(look, "", crust, "")
base = custom(m, "return lerp(float3(0.6, 0.14, 0.02), C, K);", [("C", (vector(m, "CrustColor", (0.035, 0.028, 0.024, 1), -600, 450), "RGB")),
                                                                  ("K", (crust, ""))], -250, 350, OUT.CMOT_FLOAT3)
mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
rough = custom(m, "return lerp(0.45, 0.92, K);", [("K", (crust, ""))], -250, 450, OUT.CMOT_FLOAT1)
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)

mi_path = f"{MI}/MI_W_Lava"
inst = eal.load_asset(mi_path) if eal.does_asset_exist(mi_path) else tools.create_asset(
    "MI_W_Lava", MI, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(inst, m)
mel.set_material_instance_scalar_parameter_value(inst, "Intensity", 700.0)
mel.update_material_instance(inst)
eal.save_loaded_asset(inst, only_if_is_dirty=False)
print(json.dumps(["M_ASTRA_Lava", mel.get_num_material_expressions(m), "MI_W_Lava"]))
