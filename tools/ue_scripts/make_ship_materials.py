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
FX_ONLY = globals().get("FX_ONLY", False)      # True: only the FX materials are rebuilt (the hull instances and the ships are left as they are)
log = []

# the vertex shader that keeps a glow a few pixels wide in whatever view draws it, however far and however zoomed (war_fx_hlsl.MINSIZE): the
# view's own field of view and size, not one eye's distance worked out on the CPU (through the main viewscreen's x35 zoom a battleship's
# running lights, sized for the bridge's eye, were red discs 70 m across, 4 Oct)
MINSIZE = """
float d = max(length(WPrel), 1.0);
float pxCm = d * 2.0 * TanHalf.x / max(ViewSz.x, 1.0);
float curR = length(RadW);
float minR = 0.5 * MinPx * pxCm;
float extra = max(0.0, minR - curR);
return (curR > 0.001) ? (RadW / curR) * extra : float3(0.0, 0.0, 0.0);
"""


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


hard = eal.load_asset(f"{MAT}/M_ASTRA_Hull")      # the hull master (make_hull_material.py): the plating at ship scale
emi = eal.load_asset(f"{MAT}/M_ASTRA_Emissive")
PAINT = {"BaseColorMap": "T_PanelPaint_BC", "NormalMap": "T_PanelPaint_N", "ORMMap": "T_PanelPaint_ORM"}
GUN = {"BaseColorMap": "T_Gunmetal_BC", "NormalMap": "T_Gunmetal_N", "ORMMap": "T_Gunmetal_ORM"}
BRUSH = {"BaseColorMap": "T_Brushed_BC", "NormalMap": "T_Brushed_N", "ORMMap": "T_Brushed_ORM"}
# Paints stay out of the white in full sun (fixed exposure EV100 6.6, stars of 650-2200 lux): plates at ~0.5 albedo at
# most, so the tone of each plate and the seams still read. UV unit = 8 m on hulls: detail textures tile 4x per unit (2 m), the plating tile every 4 units (32 m); strong macro
# variation. Each part weathers differently: painted plates show their tone, bare frames and engines less so.
HULL = {"UVScale": 4.0, "MacroScale": 0.6, "MacroBrightness": 0.16, "RoughnessVariation": 0.18, "PanelScale": 0.25}
PLATING = {"plate": dict(PanelTone=0.3, PanelCavity=1.0, PanelRoughness=0.3, PanelNormalStrength=1.0),
           "frame": dict(PanelTone=0.08, PanelCavity=0.6, PanelRoughness=0.1, PanelNormalStrength=0.6),
           "livery": dict(PanelTone=0.18, PanelCavity=0.9, PanelRoughness=0.2, PanelNormalStrength=1.0),
           "engine": dict(PanelTone=0.04, PanelCavity=0.5, PanelRoughness=0.06, PanelNormalStrength=0.4),
           "radiator": dict(PanelTone=0.05, PanelCavity=0.7, PanelRoughness=0.06, PanelNormalStrength=0.8)}
FACTIONS = {
    "A": dict(plate=("#BCBAB4", PAINT, 0.0, 0.18, 0.5), frame=("#4A4F55", GUN, 0.0, 0.3, 0.6), livery=("#1F3A6B", PAINT, 0.0, 0.3, 0.5),
              glow=(0.55, 0.78, 1.0, 90.0), lights=(1.0, 0.9, 0.75, 40.0), radiator=("#2A2D31", GUN, 0.0, 0.4, 0.7, None)),
    "M": dict(plate=("#5E5852", GUN, 0.0, 0.35, 0.7), frame=("#1A1B1E", GUN, 0.0, 0.3, 0.6), livery=("#8C5A2B", BRUSH, 0.85, 0.3, 0.55),
              glow=(1.0, 0.42, 0.28, 90.0), lights=(1.0, 0.68, 0.25, 40.0), radiator=("#2A1A10", GUN, 0.0, 0.4, 0.7, (1.0, 0.33, 0.07, 14.0))),
    "G": dict(plate=("#938A74", PAINT, 0.0, 0.35, 0.75), frame=("#44484C", GUN, 0.0, 0.3, 0.7), livery=("#A2561B", PAINT, 0.0, 0.4, 0.7),
              glow=(0.9, 0.9, 1.0, 60.0), lights=(1.0, 0.95, 0.85, 30.0), radiator=("#303236", GUN, 0.0, 0.4, 0.7, None)),
}
for f, d in ({} if FX_ONLY else FACTIONS).items():
    for part in ("plate", "frame", "livery"):
        col, tex, metal, rmin, rmax = d[part]
        mi(f"MI_HULL_{f}_{part.capitalize()}", hard, scalars=dict(HULL, **PLATING[part], MetallicFromMap=0.0, MetallicBias=metal,
           RoughnessMin=rmin, RoughnessMax=rmax, BaseColorMapInfluence=0.5), vectors={"Tint": lin(col)}, textures=tex)
    mi(f"MI_HULL_{f}_Engine", hard, scalars=dict(HULL, **PLATING["engine"], MetallicFromMap=1.0, RoughnessMin=0.3, RoughnessMax=0.5),
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
        mi(f"MI_HULL_{f}_Radiator", hard, scalars=dict(HULL, **PLATING["radiator"], MetallicFromMap=0.0, RoughnessMin=rmin, RoughnessMax=rmax),
           vectors={"Tint": lin(col)}, textures=tex)
log.append("hull instances ok")


# --- FX materials: additive unlit glow (tracers, beams, flashes) and fresnel shell (shields, blast shells)
def fx_material(name, fresnel, soft=False, min_px=0.0):
    """fresnel: bright at the rim (shields, blast shells); soft: bright at the core and fading to nothing at the rim
    (a glow ball that never shows the sphere's edge: drive flares); min_px: never smaller than this many pixels in any view (MINSIZE)."""
    p = f"{MAT}/{name}"
    if eal.does_asset_exist(p):
        m = eal.load_asset(p)
        for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy: UE 5.8's delete_all walks the list it removes from, and crashed the editor)
        for e in mel.get_material_expressions(m):   # what delete_all leaves behind
            mel.delete_material_expression(m, e)
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
    if soft:
        fr = E(unreal.MaterialExpressionFresnel, -650, 300)
        fr.set_editor_property("exponent", 1.0)
        fr.set_editor_property("base_reflect_fraction", 0.0)
        core = E(unreal.MaterialExpressionOneMinus, -500, 300)
        mel.connect_material_expressions(fr, "", core, "")
        pw = E(unreal.MaterialExpressionPower, -380, 300)
        mel.connect_material_expressions(core, "", pw, "Base")
        ex = E(unreal.MaterialExpressionScalarParameter, -500, 400, parameter_name="Falloff", default_value=3.0)
        mel.connect_material_expressions(ex, "", pw, "Exp")
        c = E(unreal.MaterialExpressionMultiply, -250, 200)
        mel.connect_material_expressions(b, "", c, "A")
        mel.connect_material_expressions(pw, "", c, "B")
        out = c
    if fresnel:
        fr = E(unreal.MaterialExpressionFresnel, -650, 300)
        fr.set_editor_property("exponent", 3.0)
        c = E(unreal.MaterialExpressionMultiply, -350, 200)
        mel.connect_material_expressions(b, "", c, "A")
        mel.connect_material_expressions(fr, "", c, "B")
        out = c
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    if min_px > 0.0:
        lp = E(unreal.MaterialExpressionLocalPosition, -1300, 600)
        rad = E(unreal.MaterialExpressionTransform, -1100, 600)
        rad.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_INSTANCE)
        rad.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
        mel.connect_material_expressions(lp, "", rad, "")
        wp = E(unreal.MaterialExpressionWorldPosition, -1100, 720, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_CAMERA_RELATIVE_NO_OFFSETS)
        tanh = E(unreal.MaterialExpressionViewProperty, -1100, 820, property_=unreal.MaterialExposedViewProperty.MEVP_TAN_HALF_FIELD_OF_VIEW)
        vsz = E(unreal.MaterialExpressionViewProperty, -1100, 920, property_=unreal.MaterialExposedViewProperty.MEVP_VIEW_SIZE)
        mp = E(unreal.MaterialExpressionScalarParameter, -1100, 1020, parameter_name="MinPx", default_value=min_px)
        c = E(unreal.MaterialExpressionCustom, -800, 750)
        c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
        c.set_editor_property("code", MINSIZE)
        ins = []
        for nm in ("RadW", "WPrel", "TanHalf", "ViewSz", "MinPx"):
            ci = unreal.CustomInput()
            ci.set_editor_property("input_name", nm)
            ins.append(ci)
        c.set_editor_property("inputs", ins)
        for i, src in enumerate((rad, wp, tanh, vsz, mp)):
            mel.connect_material_expressions(src, "", c, ("RadW", "WPrel", "TanHalf", "ViewSz", "MinPx")[i])
        mel.connect_material_property(c, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    return m


fx_material("M_FX_Glow", False)
fx_material("M_FX_Shell", True)
fx_material("M_FX_Flare", False, soft=True, min_px=2.0)   # running lights and drive flares: their own size up close, two pixels far off
log.append("fx materials ok")
print(json.dumps(log))
