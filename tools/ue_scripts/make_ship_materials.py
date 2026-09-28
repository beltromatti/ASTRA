"""Hull material instances per faction (MI_HULL_<A|M|G>_<Part>) and FX materials (M_FX_Glow, M_FX_Shell).
Then imports art/export/ships into /Game/ASTRA/Ships (Nanite) with the faction instances assigned."""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
log = []


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def mi(name, parent, scalars=None, vectors=None, textures=None):
    p = f"{MI}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(
        name, MI, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(f"{TEX}/{v}"))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    return inst


hard = eal.load_asset(f"{MAT}/M_ASTRA_Hard")
emi = eal.load_asset(f"{MAT}/M_ASTRA_Emissive")
PAINT = {"BaseColorMap": "T_PanelPaint_BC", "NormalMap": "T_PanelPaint_N", "ORMMap": "T_PanelPaint_ORM"}
GUN = {"BaseColorMap": "T_Gunmetal_BC", "NormalMap": "T_Gunmetal_N", "ORMMap": "T_Gunmetal_ORM"}
BRUSH = {"BaseColorMap": "T_Brushed_BC", "NormalMap": "T_Brushed_N", "ORMMap": "T_Brushed_ORM"}
# UV unit = 8 m on hulls: textures tile 4x per unit so plating reads at ship scale; strong macro variation
HULL = {"UVScale": 4.0, "MacroScale": 0.6, "MacroBrightness": 0.16, "RoughnessVariation": 0.18}
FACTIONS = {
    "A": dict(plate=("#E6E1D6", PAINT, 0.0, 0.3, 0.55), frame=("#4A4F55", GUN, 0.0, 0.3, 0.6), livery=("#1F3A6B", PAINT, 0.0, 0.3, 0.5),
              glow=(0.55, 0.78, 1.0, 90.0), lights=(1.0, 0.9, 0.75, 40.0), radiator=("#2A2D31", GUN, 0.0, 0.4, 0.7, None)),
    "M": dict(plate=("#5E5852", GUN, 0.0, 0.35, 0.7), frame=("#1A1B1E", GUN, 0.0, 0.3, 0.6), livery=("#8C5A2B", BRUSH, 0.85, 0.3, 0.55),
              glow=(1.0, 0.42, 0.28, 90.0), lights=(1.0, 0.68, 0.25, 40.0), radiator=("#2A1A10", GUN, 0.0, 0.4, 0.7, (1.0, 0.33, 0.07, 14.0))),
    "G": dict(plate=("#B8AE95", PAINT, 0.0, 0.4, 0.75), frame=("#44484C", GUN, 0.0, 0.3, 0.7), livery=("#B8651E", PAINT, 0.0, 0.4, 0.7),
              glow=(0.9, 0.9, 1.0, 60.0), lights=(1.0, 0.95, 0.85, 30.0), radiator=("#303236", GUN, 0.0, 0.4, 0.7, None)),
}
for f, d in FACTIONS.items():
    for part in ("plate", "frame", "livery"):
        col, tex, metal, rmin, rmax = d[part]
        mi(f"MI_HULL_{f}_{part.capitalize()}", hard, scalars=dict(HULL, MetallicFromMap=0.0, MetallicBias=metal,
           RoughnessMin=rmin, RoughnessMax=rmax, BaseColorMapInfluence=0.5), vectors={"Tint": lin(col)}, textures=tex)
    mi(f"MI_HULL_{f}_Engine", hard, scalars=dict(HULL, MetallicFromMap=1.0, RoughnessMin=0.3, RoughnessMax=0.5),
       vectors={"Tint": [0.35, 0.35, 0.37]}, textures=BRUSH)
    r, g, b, i = d["glow"]
    mi(f"MI_HULL_{f}_Glow", emi, scalars={"Intensity": i, "AlertColorWeight": 0.0, "LightDimWeight": 0.0}, vectors={"EmissiveColor": [r, g, b]})
    r, g, b, i = d["lights"]
    mi(f"MI_HULL_{f}_Lights", emi, scalars={"Intensity": i, "AlertColorWeight": 0.0, "LightDimWeight": 0.0}, vectors={"EmissiveColor": [r, g, b]})
    col, tex, metal, rmin, rmax, glow = d["radiator"]
    if glow:
        r, g, b, i = glow
        mi(f"MI_HULL_{f}_Radiator", emi, scalars={"Intensity": i, "AlertColorWeight": 0.0, "LightDimWeight": 0.0, "Roughness": 0.6},
           vectors={"EmissiveColor": [r, g, b], "BaseColor": lin(col)})
    else:
        mi(f"MI_HULL_{f}_Radiator", hard, scalars=dict(HULL, MetallicFromMap=0.0, RoughnessMin=rmin, RoughnessMax=rmax),
           vectors={"Tint": lin(col)}, textures=tex)
log.append("hull instances ok")


# --- FX materials: additive unlit glow (tracers, beams, flashes) and fresnel shell (shields, blast shells)
def fx_material(name, fresnel):
    p = f"{MAT}/{name}"
    if eal.does_asset_exist(p):
        m = eal.load_asset(p)
        mel.delete_all_material_expressions(m)
    else:
        m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)

    def E(cls, x, y, **pp):
        e = mel.create_material_expression(m, cls, x, y)
        for k, v in pp.items():
            e.set_editor_property(k, v)
        return e
    col = E(unreal.MaterialExpressionVectorParameter, -900, 0, parameter_name="Color", default_value=unreal.LinearColor(1, 0.6, 0.3, 1))
    inten = E(unreal.MaterialExpressionScalarParameter, -900, 150, parameter_name="Intensity", default_value=20.0)
    fade = E(unreal.MaterialExpressionScalarParameter, -900, 230, parameter_name="Fade", default_value=1.0)
    a = E(unreal.MaterialExpressionMultiply, -650, 50)
    mel.connect_material_expressions(col, "RGB", a, "A")
    mel.connect_material_expressions(inten, "", a, "B")
    b = E(unreal.MaterialExpressionMultiply, -500, 100)
    mel.connect_material_expressions(a, "", b, "A")
    mel.connect_material_expressions(fade, "", b, "B")
    out = b
    if fresnel:
        fr = E(unreal.MaterialExpressionFresnel, -650, 300)
        fr.set_editor_property("exponent", 3.0)
        c = E(unreal.MaterialExpressionMultiply, -350, 200)
        mel.connect_material_expressions(b, "", c, "A")
        mel.connect_material_expressions(fr, "", c, "B")
        out = c
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    return m


fx_material("M_FX_Glow", False)
fx_material("M_FX_Shell", True)
log.append("fx materials ok")
print(json.dumps(log))
