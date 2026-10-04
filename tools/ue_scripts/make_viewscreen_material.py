"""The main viewscreen's material (AAstraViewscreen, docs/ARCHITETTURA.md §5). Idempotent: rebuilt in place.

  M_ASTRA_Viewscreen  translucent unlit, two-sided: the optical feed (Feed, a scene capture) under the tactical overlay
                      (Overlay, a canvas cleared to alpha 1: the canvas leaves 1 - coverage in alpha, so the image is
                      feed * a + rgb); Fade switches it on from the centre line outwards and off to the bare window;
                      soft edges, a slow refresh sweep. Intensity, Opacity, Gamma (feed correction).

tools/ue.py pyfile tools/ue_scripts/make_viewscreen_material.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DIR = "/Game/ASTRA/UI/Materials"
NAME = "M_ASTRA_Viewscreen"
log = []

p = f"{DIR}/{NAME}"
if eal.does_asset_exist(p):
    m = eal.load_asset(p)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
else:
    m = tools.create_asset(NAME, DIR, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
m.set_editor_property("two_sided", True)
for prop, val in (("use_translucency_vertex_fog", False), ("enable_responsive_aa", True)):
    try:
        m.set_editor_property(prop, val)
    except Exception as e:  # noqa: BLE001 (a renamed property must not stop the build)
        log.append(f"{prop}: {e}")


def expr(cls, x, y, **props):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"{a.get_name()}.{ao} -> {b.get_name()}.{bi}")


def scalar(name, v, x, y):
    return expr(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v, group="Viewscreen")


black = eal.load_asset("/Engine/EngineResources/Black")
uv = expr(unreal.MaterialExpressionTextureCoordinate, -1200, 0)
feed = expr(unreal.MaterialExpressionTextureSampleParameter2D, -900, -200, parameter_name="Feed", texture=black, group="Viewscreen")
ov = expr(unreal.MaterialExpressionTextureSampleParameter2D, -900, 100, parameter_name="Overlay", texture=black, group="Viewscreen")
link(uv, "", feed, "UVs")
link(uv, "", ov, "UVs")
time = expr(unreal.MaterialExpressionTime, -900, 400)

code = """
float band = abs(UV.y - 0.5) * 2.0;                        // 0 on the centre line, 1 at the top and bottom
float reveal = saturate((Fade * 1.12 - band) * 14.0);      // switching on opens from the centre line
float edge = saturate(min(UV.x, 1.0 - UV.x) * 90.0) * saturate(min(UV.y, 1.0 - UV.y) * 40.0);
float p = frac(Time * 0.11) * 1.5 - 0.25;                  // a slow refresh sweep, top to bottom
float sweep = 1.0 + 0.045 * exp(-(UV.y - p) * (UV.y - p) * 260.0);
float3 f = pow(max(FeedRGB, 0.0), Gamma);
float3 c = (f * saturate(Ov.a) + Ov.rgb * 1.25) * sweep;
return float4(c * Intensity * reveal, reveal * edge * Opacity);
"""
c = expr(unreal.MaterialExpressionCustom, -500, 0)
c.set_editor_property("code", code)
c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT4)
ins = []
for n in ("UV", "FeedRGB", "Ov", "Fade", "Intensity", "Opacity", "Gamma", "Time"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", n)
    ins.append(ci)
c.set_editor_property("inputs", ins)
link(uv, "", c, "UV")
link(feed, "RGB", c, "FeedRGB")
link(ov, "RGBA", c, "Ov")
link(scalar("Fade", 1.0, -900, 250), "", c, "Fade")
link(scalar("Intensity", 16.0, -900, 320), "", c, "Intensity")
link(scalar("Opacity", 0.985, -900, 470), "", c, "Opacity")
link(scalar("Gamma", 1.0, -900, 540), "", c, "Gamma")
link(time, "", c, "Time")
rgb = expr(unreal.MaterialExpressionComponentMask, -250, -50, r=True, g=True, b=True, a=False)
alpha = expr(unreal.MaterialExpressionComponentMask, -250, 100, r=False, g=False, b=False, a=True)
link(c, "", rgb, "")
link(c, "", alpha, "")
mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.connect_material_property(alpha, "", unreal.MaterialProperty.MP_OPACITY)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append(f"{NAME} ok")
print(json.dumps(log))
