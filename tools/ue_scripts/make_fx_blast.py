"""M_FX_Blast: explosion fireball for the battle (additive, unlit). A bright core that fades to nothing at the
silhouette (no hard sphere edge), billowing animated turbulence, same parameters as M_FX_Glow (Color, Intensity, Fade)
so the battle code can swap it in. Idempotent.

tools/ue.py pyfile tools/ue_scripts/make_fx_blast.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DIR = "/Game/ASTRA/Materials"
NAME = "M_FX_Blast"

p = f"{DIR}/{NAME}"
if eal.does_asset_exist(p):
    m = eal.load_asset(p)
    mel.delete_all_material_expressions(m)
else:
    m = tools.create_asset(NAME, DIR, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
m.set_editor_property("two_sided", False)


def E(cls, x, y, **pp):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in pp.items():
        e.set_editor_property(k, v)
    return e


col = E(unreal.MaterialExpressionVectorParameter, -1000, -200, parameter_name="Color", default_value=unreal.LinearColor(1, 0.6, 0.3, 1))
inten = E(unreal.MaterialExpressionScalarParameter, -1000, -50, parameter_name="Intensity", default_value=100.0)
fade = E(unreal.MaterialExpressionScalarParameter, -1000, 30, parameter_name="Fade", default_value=1.0)
wp = E(unreal.MaterialExpressionWorldPosition, -1000, 110)
op = E(unreal.MaterialExpressionObjectPositionWS, -1000, 190)
radius = E(unreal.MaterialExpressionObjectRadius, -1000, 270)
fr = E(unreal.MaterialExpressionFresnel, -1000, 350)
fr.set_editor_property("exponent", 1.0)
fr.set_editor_property("base_reflect_fraction", 0.0)
t = E(unreal.MaterialExpressionTime, -1000, 430)
c = E(unreal.MaterialExpressionCustom, -550, 100)
c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
c.set_editor_property("code", """
// value noise in the object's own frame (the pattern grows with the blast), three octaves, drifting outwards
float3 p = (WP - OP) / max(R, 1.0) * 3.0;
float3 q = p * 1.0 + float3(0, 0, -T * 0.35);
float n = 0.0, a = 0.55;
for (int o = 0; o < 3; o++)
{
    float3 i = floor(q), f = frac(q);
    f = f * f * (3.0 - 2.0 * f);
    float h000 = frac(sin(dot(i + float3(0,0,0), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h100 = frac(sin(dot(i + float3(1,0,0), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h010 = frac(sin(dot(i + float3(0,1,0), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h110 = frac(sin(dot(i + float3(1,1,0), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h001 = frac(sin(dot(i + float3(0,0,1), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h101 = frac(sin(dot(i + float3(1,0,1), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h011 = frac(sin(dot(i + float3(0,1,1), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float h111 = frac(sin(dot(i + float3(1,1,1), float3(127.1, 311.7, 74.7))) * 43758.5453);
    float v = lerp(lerp(lerp(h000, h100, f.x), lerp(h010, h110, f.x), f.y), lerp(lerp(h001, h101, f.x), lerp(h011, h111, f.x), f.y), f.z);
    n += v * a;
    a *= 0.5;
    q *= 2.03;
}
float core = pow(saturate(1.0 - Fr), 1.6);          // 1 facing the eye, 0 at the silhouette
float billow = saturate(n * 2.2 - 0.35);
float hot = core * core;                              // the centre burns whiter
float3 c = lerp(Col * float3(1.0, 0.75, 0.6), float3(1.0, 0.95, 0.85), saturate(hot * Fade * 1.5));
return c * I * Fade * core * billow;
""")
ins = []
for n in ("Col", "I", "Fade", "WP", "OP", "R", "Fr", "T"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", n)
    ins.append(ci)
c.set_editor_property("inputs", ins)
log = []
for src, pin, out in ((col, "Col", "RGB"), (inten, "I", ""), (fade, "Fade", ""), (wp, "WP", ""), (op, "OP", ""), (radius, "R", ""),
                      (fr, "Fr", ""), (t, "T", "")):
    log.append(bool(mel.connect_material_expressions(src, out, c, pin)))
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
print(json.dumps({"connected": log}))
