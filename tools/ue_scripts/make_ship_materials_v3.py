"""Ship materials v3: layered paint over metal, worn where the geometry says, lit windows and lights, burnt cut faces, damage decals.

Masters (rebuilt in place, /Game/ASTRA/Materials):
  M_ASTRA_HullV3      opaque, Nanite. Paint over bare metal. The mesh carries the data (UV sets 2 and 3, see art/blender/ship3_geo.py):
                        UV1 = (wear, grime): 1 = chipped to bare metal (plate rims, chamfers), 1 = deep recess (seams, wall bases)
                        UV2 = (tone, soot): 0.5 = the paint's own tone, each plate painted a little lighter or darker; exhaust soot
                      The chips are broken up by a wear texture (T_ShipWear_M), scratches, grime blotches and soot streaks come from it too;
                      the paint keeps the palette (docs/STILE.md §3). Detail textures tile every 2 m (UV0 = metres / 8).
  M_ASTRA_ShipLight   opaque emissive: Mode 0 windows and light strips (UV2.y = each window's id: lit or dark, an odd blink), 1 running
                      lights (UV1.x = colour code 0 red / .5 green / 1 white, UV2.y > .5 pulses), 2 drive glow, 3 panels (radiators: the game
                      raises `Intensity` with the ship's heat, as before).
  M_ASTRA_ShipCut     the burnt inside of a broken ship: scorched carbon with streaks and glowing embers (`Heat` 0..1: the game cools it).
  M_ASTRA_ShipGlass   opaque dark glass for canopies (Nanite draws only opaque and masked materials).
  M_ASTRA_DamageDecal deferred decal from the damage atlas (T_ShipDamage_A/N): soot, embers, breach, opacity; AtlasRect picks the cell.
Instances (/Game/ASTRA/Materials/Instances): MI_HULL_<A|M|G>_<Plate|Frame|Livery|Trim|Marking|Engine|Glow|Lights|Nav|Radiator|Cut|Glass>
(+ Blue, Green for the Guilds) replace the v2 ones in place; MI_ShipDamage_<Burn|Hole|Torn|Impact|Strafe|Melt|Gouge|Blast> are the decals.
Run first: uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/ship3_textures.py
Then in the editor: tools/ue.py pyfile tools/ue_scripts/make_ship_materials_v3.py
"""
import json
import os
import sys

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
TEX_SRC = ROOT + "/art/_cache/textures"
TEX = "/Game/ASTRA/Materials/Textures"
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ST = unreal.MaterialSamplerType
log = []


# ------------------------------------------------------------------------------------------------------------ textures
def import_textures():
    names = ("T_ShipWear_M", "T_ShipDamage_A", "T_ShipDamage_N")
    tasks = []
    for n in names:
        src = os.path.join(TEX_SRC, n + ".png")
        if not os.path.exists(src):
            raise RuntimeError(f"{src} missing: run tools/art/ship3_textures.py first")
        t = unreal.AssetImportTask()
        t.filename = src
        t.destination_path = TEX
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    for n in names:
        tx = eal.load_asset(f"{TEX}/{n}")
        tx.set_editor_property("srgb", False)
        if n.endswith("_N"):
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
        else:
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        if n.startswith("T_ShipDamage"):
            tx.set_editor_property("never_stream", True)               # decals made at run time get no streaming
        eal.save_loaded_asset(tx, only_if_is_dirty=False)
    log.append("textures")


def tex(name):
    return eal.load_asset(f"{TEX}/{name}")


# -------------------------------------------------------------------------------------------------------- graph helpers
def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


def scalar(mat, name, value, x, y, group="Ship"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="Ship"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group=group)


def texparam(mat, name, texture, sampler, x, y, group="Textures"):
    return E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=texture, sampler_type=sampler, group=group)


def binop(mat, cls, a, a_out, b, b_out, x, y):
    e = E(mat, cls, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    return e


def const(mat, v, x, y):
    return E(mat, unreal.MaterialExpressionConstant, x, y, r=v)


def mask(mat, src, out, x, y, r=False, g=False, b=False, a=False):
    e = E(mat, unreal.MaterialExpressionComponentMask, x, y, r=r, g=g, b=b, a=a)
    link(src, out, e, "")
    return e


def custom(mat, code, inputs, x, y, out=unreal.CustomMaterialOutputType.CMOT_FLOAT4):
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


def fresh(name):
    path = f"{MAT}/{name}"
    if eal.does_asset_exist(path):
        m = eal.load_asset(path)
        mel.delete_all_material_expressions(m)
        for e in mel.get_material_expressions(m):
            mel.delete_material_expression(m, e)
        return m
    return tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())


def finish(m, nanite=True):
    if nanite:
        try:
            m.set_editor_property("used_with_nanite", True)
        except Exception as ex:                                     # older builds: the flag is set when the material meets a Nanite mesh
            log.append(f"used_with_nanite not settable on {m.get_name()}: {ex}")
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    log.append(f"{m.get_name()} ok ({mel.get_num_material_expressions(m)} nodes)")


def uvset(m, index, x, y):
    return E(m, unreal.MaterialExpressionTextureCoordinate, x, y, coordinate_index=index)


# =========================================================================================================== M_ASTRA_HullV3
def build_hull():
    m = fresh("M_ASTRA_HullV3")
    uv0 = uvset(m, 0, -2600, 0)
    uv1 = uvset(m, 1, -2600, 300)
    uv2 = uvset(m, 2, -2600, 450)
    uvt = binop(m, unreal.MaterialExpressionMultiply, uv0, "", scalar(m, "UVScale", 4.0, -2600, 120, "UV"), "", -2400, 40)
    wuv = binop(m, unreal.MaterialExpressionMultiply, uv0, "", scalar(m, "WearScale", 0.5, -2600, 620, "UV"), "", -2400, 560)
    bc = texparam(m, "BaseColorMap", tex("T_PanelPaint_BC"), ST.SAMPLERTYPE_COLOR, -2100, -400)
    nm = texparam(m, "NormalMap", tex("T_PanelPaint_N"), ST.SAMPLERTYPE_NORMAL, -2100, 300)
    orm = texparam(m, "ORMMap", tex("T_PanelPaint_ORM"), ST.SAMPLERTYPE_MASKS, -2100, 0)
    for t in (bc, nm, orm):
        link(uvt, "", t, "UVs")
    wear = texparam(m, "ShipWear", tex("T_ShipWear_M"), ST.SAMPLERTYPE_MASKS, -2100, 700, "Wear")
    link(wuv, "", wear, "UVs")
    # the macro variation, shifted per object so two ships never repeat each other
    muv0 = binop(m, unreal.MaterialExpressionMultiply, uv0, "", scalar(m, "MacroScale", 0.6, -2600, 800, "UV"), "", -2400, 760)
    objm = mask(m, E(m, unreal.MaterialExpressionObjectPositionWS, -2600, 920), "", -2450, 920, r=True, g=True)
    objoff = binop(m, unreal.MaterialExpressionMultiply, objm, "", const(m, 0.00173, -2450, 1000), "", -2300, 940)
    muv = binop(m, unreal.MaterialExpressionAdd, muv0, "", objoff, "", -2200, 800)
    macro = texparam(m, "MacroNoise", tex("T_ASTRA_MacroNoise"), ST.SAMPLERTYPE_MASKS, -2100, 900, "Variation")
    link(muv, "", macro, "UVs")

    P = {}
    defs = (("BCInfluence", 0.4), ("ToneAmount", 0.20), ("MacroBrightness", 0.10), ("GrimeGain", 1.0), ("GrimeDarken", 0.55), ("SootDarken", 0.6),
            ("WearGain", 1.0), ("WearThreshold", 0.52), ("WearSoftness", 0.10), ("WearBreakup", 0.9), ("ScratchAmount", 0.35), ("DirtBlotch", 0.22),
            ("StreakAmount", 0.12))
    for i, (n, v) in enumerate(defs):
        P[n] = scalar(m, n, v, -1800, -900 + 60 * i, "Paint")
    tint = vector(m, "Tint", (0.5, 0.5, 0.5, 1), -1800, -1100, "Paint")
    bare = vector(m, "BareTint", (0.55, 0.57, 0.6, 1), -1800, -1040, "Paint")

    base_code = """
float wear = D1.x;
float grime = D1.y;
float tone = D2.x;
float soot = D2.y;
if (D2.x == 0.0 && D2.y == 0.0) { tone = 0.5; }
float3 paint = Tint * lerp(float3(1.0, 1.0, 1.0), BC, BCInfluence);
paint *= 1.0 + (MN.r - 0.5) * 2.0 * MacroBrightness;
paint *= 1.0 + (tone - 0.5) * 2.0 * ToneAmount;
float g = saturate(grime * GrimeGain * (0.6 + 0.8 * WMrgb.b));
paint *= (1.0 - g * GrimeDarken) * (1.0 - soot * SootDarken * (0.5 + 0.5 * WMa));
paint *= (1.0 - DirtBlotch * pow(max(WMrgb.b, 0.0), 1.3)) * (1.0 - StreakAmount * WMa);
float chip = saturate((wear * WearGain + (WMrgb.r - 0.5) * WearBreakup - WearThreshold) / max(WearSoftness, 0.001));
float scr = smoothstep(0.86, 0.97, WMrgb.g) * ScratchAmount;
float isbare = saturate(max(chip, scr));
float3 metal = BareTint * (0.8 + 0.4 * WMrgb.g);
return float4(lerp(paint, metal, isbare), isbare);
"""
    ins = [("BC", (bc, "RGB")), ("MN", (macro, "RGB")), ("WMrgb", (wear, "RGB")), ("WMa", (wear, "A")), ("D1", (uv1, "")), ("D2", (uv2, "")),
           ("Tint", (tint, "RGB")), ("BareTint", (bare, "RGB"))] + [(n, (P[n], "")) for n in ("BCInfluence", "ToneAmount", "MacroBrightness", "GrimeGain", "GrimeDarken", "SootDarken", "WearGain", "WearThreshold", "WearSoftness", "WearBreakup", "ScratchAmount", "DirtBlotch", "StreakAmount")]
    base = custom(m, base_code, ins, -1200, -300)
    for i, nme in enumerate(("RoughMin", "RoughMax", "RoughVar", "GrimeRough", "BareRoughness", "BareMetallic", "MetallicBias", "MetallicFromMap", "CavityAO")):
        P[nme] = scalar(m, nme, {"RoughMin": 0.3, "RoughMax": 0.6, "RoughVar": 0.18, "GrimeRough": 0.25, "BareRoughness": 0.42, "BareMetallic": 0.75,
                                 "MetallicBias": 0.0, "MetallicFromMap": 0.0, "CavityAO": 0.8}[nme], -1800, -300 + 60 * i, "Surface")
    surf_code = """
float isbare = A.a;
float g = saturate(D1.y * GrimeGain * (0.6 + 0.8 * WMrgb.b));
float rp = lerp(RoughMin, RoughMax, ORM.g) + g * GrimeRough + (MN.g - 0.5) * RoughVar;
float rough = saturate(lerp(rp, BareRoughness, isbare));
float metal = saturate(MetallicBias * (1.0 - isbare) + isbare * BareMetallic + ORM.b * MetallicFromMap);
float ao = ORM.r * lerp(1.0, 1.0 - D1.y, CavityAO);
return float4(rough, metal, ao, g);
"""
    ins2 = [("A", (base, "")), ("ORM", (orm, "RGB")), ("MN", (macro, "RGB")), ("WMrgb", (wear, "RGB")), ("D1", (uv1, "")), ("GrimeGain", (P["GrimeGain"], ""))] + \
           [(n, (P[n], "")) for n in ("RoughMin", "RoughMax", "RoughVar", "GrimeRough", "BareRoughness", "BareMetallic", "MetallicBias", "MetallicFromMap", "CavityAO")]
    surf = custom(m, surf_code, ins2, -1200, 300)
    mel.connect_material_property(mask(m, base, "", -900, -300, r=True, g=True, b=True), "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(mask(m, surf, "", -900, 200, r=True), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(mask(m, surf, "", -900, 280, g=True), "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(mask(m, surf, "", -900, 360, b=True), "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    flat = E(m, unreal.MaterialExpressionConstant3Vector, -1500, 900, constant=unreal.LinearColor(0, 0, 1, 1))
    nl = E(m, unreal.MaterialExpressionLinearInterpolate, -1200, 900)
    link(flat, "", nl, "A")
    link(nm, "RGB", nl, "B")
    link(scalar(m, "NormalStrength", 1.0, -1500, 1000, "Surface"), "", nl, "Alpha")
    nn = E(m, unreal.MaterialExpressionNormalize, -1000, 900)
    link(nl, "", nn, "")
    mel.connect_material_property(nn, "", unreal.MaterialProperty.MP_NORMAL)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    finish(m)
    return m


# ======================================================================================================= M_ASTRA_ShipLight
def build_light():
    m = fresh("M_ASTRA_ShipLight")
    uv1 = uvset(m, 1, -1800, 0)
    uv2 = uvset(m, 2, -1800, 100)
    t = E(m, unreal.MaterialExpressionTime, -1800, 200)
    op = E(m, unreal.MaterialExpressionObjectPositionWS, -1800, 300)
    col = vector(m, "EmissiveColor", (1.0, 0.9, 0.75, 1), -1800, 420, "Light")
    P = {}
    for i, (n, v) in enumerate((("Intensity", 40.0), ("Mode", 0.0), ("LitFraction", 0.65), ("FlickerAmount", 1.0), ("FlickerRate", 0.7), ("PulseSpeed", 2.2),
                                ("PulseAmount", 0.0), ("Roughness", 0.2), ("Metallic", 0.0))):
        P[n] = scalar(m, n, v, -1800, 520 + 60 * i, "Light")
    nav = [vector(m, n, v, -1500, 420 + 60 * i, "Light") for i, (n, v) in enumerate((("NavRed", (1.0, 0.05, 0.03, 1)), ("NavGreen", (0.1, 1.0, 0.2, 1)), ("NavWhite", (1.0, 0.95, 0.9, 1))))]
    base = vector(m, "BaseColor", (0.006, 0.01, 0.016, 1), -1500, 640, "Surface")
    code = """
float seed = frac(sin(dot(ObjPos.xy, float2(12.9898, 78.233))) * 43758.5453);
float3 col = EmissiveColor;
float k = 1.0;
if (Mode < 0.5)
{
    float id = D2.y;
    float lit = step(id, LitFraction);
    float ph = frac(id * 917.13 + seed * 5.0);
    float blink = step(0.985, frac(sin(floor(Tm * FlickerRate) * 12.9898 + ph * 78.233) * 43758.5453));
    k = lit * (1.0 - FlickerAmount * blink);
}
else if (Mode < 1.5)
{
    col = (D1.x < 0.25) ? NavRed : ((D1.x < 0.75) ? NavGreen : NavWhite);
    float pulse = 0.5 + 0.5 * sin(Tm * PulseSpeed + seed * 6.2831);
    k = (D2.y > 0.5) ? lerp(1.0 - PulseAmount, 1.0, pulse) : 1.0;
}
else if (Mode < 2.5)
{
    k = 1.0 - PulseAmount * (0.5 + 0.5 * sin(Tm * PulseSpeed + seed * 6.2831));
}
return float4(col * Intensity * k, k);
"""
    ins = [("ObjPos", (op, "")), ("EmissiveColor", (col, "RGB")), ("D1", (uv1, "")), ("D2", (uv2, "")), ("Tm", (t, "")),
           ("NavRed", (nav[0], "RGB")), ("NavGreen", (nav[1], "RGB")), ("NavWhite", (nav[2], "RGB"))] + \
          [(n, (P[n], "")) for n in ("Intensity", "Mode", "LitFraction", "FlickerAmount", "FlickerRate", "PulseSpeed", "PulseAmount")]
    c = custom(m, code, ins, -1000, 300)
    mel.connect_material_property(mask(m, c, "", -700, 300, r=True, g=True, b=True), "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(P["Roughness"], "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(P["Metallic"], "", unreal.MaterialProperty.MP_METALLIC)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    finish(m)
    return m


# ========================================================================================================= M_ASTRA_ShipCut
def build_cut():
    m = fresh("M_ASTRA_ShipCut")
    uv0 = uvset(m, 0, -2000, 0)
    uv1 = uvset(m, 1, -2000, 200)
    uv2 = uvset(m, 2, -2000, 300)
    uvt = binop(m, unreal.MaterialExpressionMultiply, uv0, "", scalar(m, "WearScale", 0.9, -2000, 100, "UV"), "", -1800, 40)
    wear = texparam(m, "ShipWear", tex("T_ShipWear_M"), ST.SAMPLERTYPE_MASKS, -1600, 0, "Wear")
    link(uvt, "", wear, "UVs")
    tint = vector(m, "Tint", (0.05, 0.045, 0.04, 1), -1600, 300, "Burnt")
    ember = vector(m, "EmberColor", (1.0, 0.33, 0.07, 1), -1600, 380, "Burnt")
    heat = scalar(m, "Heat", 0.0, -1600, 460, "Burnt")
    ember_i = scalar(m, "EmberIntensity", 26.0, -1600, 520, "Burnt")
    code = """
float tone = (D2.x == 0.0 && D2.y == 0.0) ? 0.5 : D2.x;
float3 col = Tint * (0.55 + 1.1 * WM.b) * (1.0 - 0.4 * WMa) * (1.0 + 0.6 * D1.x) * (0.4 + 1.6 * tone);
float e = smoothstep(0.70, 0.84, WM.r + 0.22 * WM.g) * Heat;
return float4(col, e);
"""
    c = custom(m, code, [("WM", (wear, "RGB")), ("WMa", (wear, "A")), ("D1", (uv1, "")), ("D2", (uv2, "")), ("Tint", (tint, "RGB")), ("Heat", (heat, ""))], -1200, 200)
    mel.connect_material_property(mask(m, c, "", -900, 200, r=True, g=True, b=True), "", unreal.MaterialProperty.MP_BASE_COLOR)
    em = binop(m, unreal.MaterialExpressionMultiply, ember, "RGB", binop(m, unreal.MaterialExpressionMultiply, mask(m, c, "", -900, 300, a=True), "", ember_i, "", -700, 300), "", -500, 300)
    mel.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.85, -900, 420, "Burnt"), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Metallic", 0.25, -900, 480, "Burnt"), "", unreal.MaterialProperty.MP_METALLIC)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    finish(m)
    return m


def build_glass():
    m = fresh("M_ASTRA_ShipGlass")
    mel.connect_material_property(vector(m, "BaseColor", (0.004, 0.006, 0.010, 1), -600, 0, "Glass"), "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.06, -600, 100, "Glass"), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Specular", 0.9, -600, 160, "Glass"), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(vector(m, "Tint", (0.0, 0.02, 0.05, 1), -600, 220, "Glass"), "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    finish(m)
    return m


# ===================================================================================================== M_ASTRA_DamageDecal
def build_decal():
    m = fresh("M_ASTRA_DamageDecal")
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    uv = E(m, unreal.MaterialExpressionTextureCoordinate, -1600, 0)
    rect = vector(m, "AtlasRect", (0.0, 0.0, 0.25, 0.5), -1600, 100, "Atlas")
    scaled = binop(m, unreal.MaterialExpressionMultiply, uv, "", mask(m, rect, "", -1400, 100, b=True, a=True), "", -1200, 0)
    auv = binop(m, unreal.MaterialExpressionAdd, scaled, "", mask(m, rect, "", -1400, 200, r=True, g=True), "", -1000, 60)
    atlas = texparam(m, "Damage", tex("T_ShipDamage_A"), ST.SAMPLERTYPE_LINEAR_COLOR, -800, 0, "Atlas")
    dn = texparam(m, "DamageNormal", tex("T_ShipDamage_N"), ST.SAMPLERTYPE_NORMAL, -800, 300, "Atlas")
    link(auv, "", atlas, "UVs")
    link(auv, "", dn, "UVs")
    heat = scalar(m, "Heat", 1.0, -800, 500)
    breach_p = scalar(m, "Breach", 0.0, -800, 560)
    fade = scalar(m, "Fade", 1.0, -800, 620)
    ember = vector(m, "EmberColor", (1.0, 0.33, 0.07, 1), -800, 700)
    code = """
float3 soot_hi = float3(0.005, 0.0045, 0.004);
float3 soot_lo = float3(0.035, 0.03, 0.026);
float3 col = lerp(soot_lo, soot_hi, A.r);
col = lerp(col, float3(0.0, 0.0, 0.0), A.b * Breach);
return col;
"""
    c = custom(m, code, [("A", (atlas, "RGB")), ("Breach", (breach_p, ""))], -400, 0, unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    code2 = """
float glow = saturate(A.g + A.b * Breach * 1.5) * Heat * Heat;
return glow;
"""
    g = custom(m, code2, [("A", (atlas, "RGB")), ("Breach", (breach_p, "")), ("Heat", (heat, ""))], -400, 300, unreal.CustomMaterialOutputType.CMOT_FLOAT1)
    op = binop(m, unreal.MaterialExpressionMultiply, binop(m, unreal.MaterialExpressionMultiply, atlas, "A", fade, "", -400, 500), "", const(m, 1.6, -400, 560), "", -200, 500)
    sat = E(m, unreal.MaterialExpressionSaturate, 0, 500)
    link(op, "", sat, "")
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(const(m, 0.9, -100, 100), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(dn, "RGB", unreal.MaterialProperty.MP_NORMAL)
    emi = binop(m, unreal.MaterialExpressionMultiply, ember, "RGB", binop(m, unreal.MaterialExpressionMultiply, g, "", const(m, 30.0, -100, 420), "", 0, 400), "", 200, 400)
    mel.connect_material_property(emi, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(sat, "", unreal.MaterialProperty.MP_OPACITY)
    finish(m, nanite=False)
    return m


# ==================================================================================================================== instances
def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def mi(name, parent, scalars=None, vectors=None, textures=None):
    p = f"{MI}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0) if len(v) == 3 else unreal.LinearColor(*v))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(f"{TEX}/{v}"))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    return inst


sys.path.insert(0, ROOT + "/art/blender")
import ship3_palette as PAL  # noqa: E402  (one palette for these instances and the Blender previews)

PAINT, LIGHTS, RADIATOR, NAVS = PAL.PAINT, PAL.LIGHTS, PAL.RADIATOR, PAL.NAVS


def instances(hull, light, cut, glass):
    out = []
    for f, parts in PAINT.items():
        for part, (col, bare, metal, rmin, rmax) in parts.items():
            mi(f"MI_HULL_{f}_{part}", hull, scalars=dict(RoughMin=rmin, RoughMax=rmax, MetallicBias=metal, ToneAmount=0.20 if f != "M" else 0.26,
                                                          WearThreshold=0.52, GrimeGain=1.0 if f != "M" else 1.3, BCInfluence=0.0),
               vectors={"Tint": lin(col), "BareTint": lin(bare)})
            out.append(f"MI_HULL_{f}_{part}")
        lc, li, gc, gi, lit = LIGHTS[f]
        mi(f"MI_HULL_{f}_Lights", light, scalars=dict(Intensity=li, Mode=0.0, LitFraction=lit, FlickerAmount=1.0), vectors={"EmissiveColor": lc})
        mi(f"MI_HULL_{f}_Glow", light, scalars=dict(Intensity=gi, Mode=2.0, PulseSpeed=3.0, PulseAmount=0.06), vectors={"EmissiveColor": gc})
        nr, ng, nw = NAVS[f]
        mi(f"MI_HULL_{f}_Nav", light, scalars=dict(Intensity=160.0, Mode=1.0, PulseSpeed=2.4, PulseAmount=0.85), vectors={"NavRed": nr, "NavGreen": ng, "NavWhite": nw})
        rcol, rem, rint = RADIATOR[f]
        # the radiators keep the parameter the game drives: Intensity (the Aquila's heat glow, TickHeat)
        mi(f"MI_HULL_{f}_Radiator", light, scalars=dict(Intensity=rint, Mode=3.0, Roughness=0.55, Metallic=0.4), vectors={"BaseColor": lin(rcol), "EmissiveColor": rem})
        mi(f"MI_HULL_{f}_Cut", cut, scalars=dict(Heat=0.0), vectors={"Tint": [0.05, 0.045, 0.04]})
        mi(f"MI_HULL_{f}_Glass", glass)
        out += [f"MI_HULL_{f}_{n}" for n in ("Lights", "Glow", "Nav", "Radiator", "Cut", "Glass")]
    return out


def damage_instances(decal):
    names = ("Burn", "Hole", "Torn", "Impact", "Strafe", "Melt", "Gouge", "Blast")
    for i, n in enumerate(names):
        mi(f"MI_ShipDamage_{n}", decal, vectors={"AtlasRect": [(i % 4) * 0.25, (i // 4) * 0.5, 0.25, 0.5]},
           scalars=dict(Heat=1.0, Breach=1.0 if n in ("Hole", "Torn") else 0.0, Fade=1.0))
    return [f"MI_ShipDamage_{n}" for n in names]


import_textures()
hull = build_hull()
light = build_light()
cut = build_cut()
glass = build_glass()
decal = build_decal()
made = instances(hull, light, cut, glass) + damage_instances(decal)
log.append(f"{len(made)} instances")
print(json.dumps(log))
