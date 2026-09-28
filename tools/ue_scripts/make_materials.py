"""ASTRA material library: imports packed textures, builds master materials and instances,
assigns them to the interior kit. Idempotent. Run: tools/ue.py pyfile tools/ue_scripts/make_materials.py"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
TEX_SRC = ROOT + "/art/_cache/textures"
TEX_DST = "/Game/ASTRA/Materials/Textures"
MAT_DST = "/Game/ASTRA/Materials"
MI_DST = "/Game/ASTRA/Materials/Instances"
KIT = globals().get("KIT", "/Game/ASTRA/Kit/Bridge")

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
log = []


# ---------------------------------------------------------------- textures
def import_textures():
    tasks = []
    for f in sorted(os.listdir(TEX_SRC)):
        if not f.endswith(".png"):
            continue
        name = f[:-4]
        if eal.does_asset_exist(f"{TEX_DST}/{name}"):
            continue
        t = unreal.AssetImportTask()
        t.filename = os.path.join(TEX_SRC, f)
        t.destination_path = TEX_DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    if tasks:
        tools.import_asset_tasks(tasks)
    for path in eal.list_assets(TEX_DST, recursive=False, include_folder=False):
        tex = eal.load_asset(path)
        if not isinstance(tex, unreal.Texture2D):
            continue
        n = tex.get_name()
        if n.endswith("_N"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
        elif n.endswith("_BC"):
            tex.set_editor_property("srgb", True)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        elif n.endswith("_OP") or n.endswith("_M"):
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        else:  # ORM, MacroNoise
            tex.set_editor_property("srgb", False)
            tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tex)
    log.append(f"textures: {len(eal.list_assets(TEX_DST, recursive=False, include_folder=False))}")


def tex(name):
    return eal.load_asset(f"{TEX_DST}/{name}")


# ---------------------------------------------------------------- helpers
REBUILD_MASTERS = globals().get("REBUILD_MASTERS", False)


class _Existing(Exception):
    pass


def new_material(name, folder=MAT_DST):
    path = f"{folder}/{name}"
    if eal.does_asset_exist(path):
        if not REBUILD_MASTERS:
            raise _Existing(path)
        eal.delete_asset(path)
    return tools.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(mat, name, value, x, y, group="ASTRA"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="ASTRA"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
             default_value=unreal.LinearColor(*rgba), group=group)


def texparam(mat, name, texture, sampler, x, y, group="Textures"):
    return E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name,
             texture=texture, sampler_type=sampler, group=group)


def link(a, a_out, b, b_in):
    ok = mel.connect_material_expressions(a, a_out, b, b_in)
    if not ok:
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


def binop(mat, cls, a, a_out, b, b_out, x, y):
    e = E(mat, cls, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    return e


def const(mat, v, x, y):
    return E(mat, unreal.MaterialExpressionConstant, x, y, r=v)


ST = unreal.MaterialSamplerType


# ---------------------------------------------------------------- M_ASTRA_Hard
def build_hard():
    m = new_material("M_ASTRA_Hard")
    uv = E(m, unreal.MaterialExpressionTextureCoordinate, -1800, 0)
    uvs = scalar(m, "UVScale", 1.0, -1800, 120, "UV")
    uvt = binop(m, unreal.MaterialExpressionMultiply, uv, "", uvs, "", -1600, 40)

    bc = texparam(m, "BaseColorMap", tex("T_PanelPaint_BC"), ST.SAMPLERTYPE_COLOR, -1300, -400)
    nm = texparam(m, "NormalMap", tex("T_PanelPaint_N"), ST.SAMPLERTYPE_NORMAL, -1300, 300)
    orm = texparam(m, "ORMMap", tex("T_PanelPaint_ORM"), ST.SAMPLERTYPE_MASKS, -1300, 0)
    for t in (bc, nm, orm):
        link(uvt, "", t, "UVs")

    # macro variation (world-independent, shifted per object so modules don't repeat)
    mscale = scalar(m, "MacroScale", 0.23, -1800, 700, "Variation")
    muv0 = binop(m, unreal.MaterialExpressionMultiply, uv, "", mscale, "", -1600, 640)
    objpos = E(m, unreal.MaterialExpressionObjectPositionWS, -1800, 820)
    objmask = E(m, unreal.MaterialExpressionComponentMask, -1650, 820, r=True, g=True, b=False, a=False)
    link(objpos, "", objmask, "")
    objk = const(m, 0.00173, -1650, 900)
    objoff = binop(m, unreal.MaterialExpressionMultiply, objmask, "", objk, "", -1500, 840)
    muv = binop(m, unreal.MaterialExpressionAdd, muv0, "", objoff, "", -1400, 700)
    macro = texparam(m, "MacroNoise", tex("T_ASTRA_MacroNoise"), ST.SAMPLERTYPE_MASKS, -1300, 700, "Variation")
    link(muv, "", macro, "UVs")

    sscale = scalar(m, "ScratchScale", 0.5, -1800, 1100, "Variation")
    suv = binop(m, unreal.MaterialExpressionMultiply, uv, "", sscale, "", -1600, 1100)
    scr = texparam(m, "ScratchMask", tex("T_ASTRA_Scratches_M"), ST.SAMPLERTYPE_LINEAR_GRAYSCALE, -1300, 1100, "Variation")
    link(suv, "", scr, "UVs")

    # base color = Tint * lerp(1, map, influence) * macro brightness
    tint = vector(m, "Tint", (1, 1, 1, 1), -900, -600, "Color")
    infl = scalar(m, "BaseColorMapInfluence", 1.0, -900, -480, "Color")
    one = const(m, 1.0, -900, -420)
    lerpbc = E(m, unreal.MaterialExpressionLinearInterpolate, -700, -450)
    link(one, "", lerpbc, "A"); link(bc, "RGB", lerpbc, "B"); link(infl, "", lerpbc, "Alpha")
    tinted = binop(m, unreal.MaterialExpressionMultiply, lerpbc, "", tint, "RGB", -500, -500)
    mbright = scalar(m, "MacroBrightness", 0.10, -900, 560, "Variation")
    half = const(m, 0.5, -900, 620)
    mr = binop(m, unreal.MaterialExpressionSubtract, macro, "R", half, "", -750, 580)
    mr2 = binop(m, unreal.MaterialExpressionMultiply, mr, "", mbright, "", -600, 580)
    mr3 = binop(m, unreal.MaterialExpressionMultiply, mr2, "", const(m, 2.0, -750, 660), "", -450, 580)
    bfac = binop(m, unreal.MaterialExpressionAdd, mr3, "", const(m, 1.0, -600, 660), "", -300, 580)
    basecol = binop(m, unreal.MaterialExpressionMultiply, tinted, "", bfac, "", -200, -450)
    mel.connect_material_property(basecol, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # roughness = lerp(min, max, map) + macro * var + scratches * amount
    rmin = scalar(m, "RoughnessMin", 0.25, -900, 0, "Surface")
    rmax = scalar(m, "RoughnessMax", 0.55, -900, 60, "Surface")
    rl = E(m, unreal.MaterialExpressionLinearInterpolate, -700, 20)
    link(rmin, "", rl, "A"); link(rmax, "", rl, "B"); link(orm, "G", rl, "Alpha")
    rvar = scalar(m, "RoughnessVariation", 0.12, -900, 760, "Variation")
    mg = binop(m, unreal.MaterialExpressionSubtract, macro, "G", half, "", -750, 760)
    mg2 = binop(m, unreal.MaterialExpressionMultiply, mg, "", rvar, "", -600, 760)
    samt = scalar(m, "ScratchRoughness", 0.18, -900, 1180, "Variation")
    sc2 = binop(m, unreal.MaterialExpressionMultiply, scr, "R", samt, "", -600, 1120)
    r1 = binop(m, unreal.MaterialExpressionAdd, rl, "", mg2, "", -450, 100)
    r2 = binop(m, unreal.MaterialExpressionAdd, r1, "", sc2, "", -300, 140)
    rs = E(m, unreal.MaterialExpressionSaturate, -150, 140)
    link(r2, "", rs, "")
    mel.connect_material_property(rs, "", unreal.MaterialProperty.MP_ROUGHNESS)

    # metallic = map * scale + bias
    mscale2 = scalar(m, "MetallicFromMap", 1.0, -900, 240, "Surface")
    mbias = scalar(m, "MetallicBias", 0.0, -900, 300, "Surface")
    mm = binop(m, unreal.MaterialExpressionMultiply, orm, "B", mscale2, "", -700, 240)
    ma = binop(m, unreal.MaterialExpressionAdd, mm, "", mbias, "", -550, 260)
    ms = E(m, unreal.MaterialExpressionSaturate, -400, 260)
    link(ma, "", ms, "")
    mel.connect_material_property(ms, "", unreal.MaterialProperty.MP_METALLIC)

    # ambient occlusion
    mel.connect_material_property(orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

    # normal = lerp(flat, map, strength)
    nstr = scalar(m, "NormalStrength", 1.0, -900, 420, "Surface")
    flat = E(m, unreal.MaterialExpressionConstant3Vector, -900, 360, constant=unreal.LinearColor(0, 0, 1, 1))
    nl = E(m, unreal.MaterialExpressionLinearInterpolate, -600, 380)
    link(flat, "", nl, "A"); link(nm, "RGB", nl, "B"); link(nstr, "", nl, "Alpha")
    mel.connect_material_property(nl, "", unreal.MaterialProperty.MP_NORMAL)

    # optional opacity mask (grates): static switch, used by instances that override blend mode to Masked
    op = texparam(m, "OpacityMap", tex("T_Walkway_OP"), ST.SAMPLERTYPE_LINEAR_GRAYSCALE, -1300, 1400)
    link(uvt, "", op, "UVs")
    sw = E(m, unreal.MaterialExpressionStaticSwitchParameter, -700, 1400, parameter_name="UseOpacityMask",
           default_value=False, group="Surface")
    link(op, "R", sw, "True"); link(const(m, 1.0, -900, 1480), "", sw, "False")
    mel.connect_material_property(sw, "", unreal.MaterialProperty.MP_OPACITY_MASK)

    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    log.append("M_ASTRA_Hard ok")
    return m


# ---------------------------------------------------------------- M_ASTRA_Emissive
def build_emissive():
    m = new_material("M_ASTRA_Emissive")
    col = vector(m, "EmissiveColor", (1.0, 0.93, 0.85, 1), -900, -100, "Light")
    inten = scalar(m, "Intensity", 30.0, -900, 20, "Light")
    e1 = binop(m, unreal.MaterialExpressionMultiply, col, "RGB", inten, "", -650, -60)
    # pulse for alert states: 1 - amount * (0.5 + 0.5 sin(t * speed))
    t = E(m, unreal.MaterialExpressionTime, -1100, 200)
    speed = scalar(m, "PulseSpeed", 3.0, -1100, 280, "Light")
    ts = binop(m, unreal.MaterialExpressionMultiply, t, "", speed, "", -950, 220)
    s = E(m, unreal.MaterialExpressionSine, -820, 220, period=6.2831853)
    link(ts, "", s, "")
    s01 = binop(m, unreal.MaterialExpressionMultiply, s, "", const(m, 0.5, -820, 300), "", -700, 240)
    s02 = binop(m, unreal.MaterialExpressionAdd, s01, "", const(m, 0.5, -700, 320), "", -580, 260)
    amt = scalar(m, "PulseAmount", 0.0, -700, 400, "Light")
    pa = binop(m, unreal.MaterialExpressionMultiply, s02, "", amt, "", -460, 300)
    pf = binop(m, unreal.MaterialExpressionSubtract, const(m, 1.0, -460, 220), "", pa, "", -330, 260)
    e2 = binop(m, unreal.MaterialExpressionMultiply, e1, "", pf, "", -200, 0)
    mel.connect_material_property(e2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    base = vector(m, "BaseColor", (0.8, 0.8, 0.8, 1), -900, -300, "Surface")
    mel.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.35, -900, -220, "Surface"), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    log.append("M_ASTRA_Emissive ok")
    return m


# ---------------------------------------------------------------- M_ASTRA_Glass
def build_glass():
    m = new_material("M_ASTRA_Glass")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    m.set_editor_property("two_sided", True)
    mel.connect_material_property(vector(m, "Tint", (0.02, 0.03, 0.035, 1), -600, -200, "Glass"), "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(scalar(m, "Roughness", 0.04, -600, -80, "Glass"), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(scalar(m, "Specular", 0.6, -600, 0, "Glass"), "", unreal.MaterialProperty.MP_SPECULAR)
    mel.connect_material_property(scalar(m, "Opacity", 0.10, -600, 80, "Glass"), "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(m)
    eal.save_loaded_asset(m)
    log.append("M_ASTRA_Glass ok")
    return m


# ---------------------------------------------------------------- instances
def srgb_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def make_mi(name, parent, scalars=None, vectors=None, textures=None, switches=None, masked=False):
    path = f"{MI_DST}/{name}"
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = tools.create_asset(name, MI_DST, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi.get_editor_property("parent") != parent:
        mel.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(mi, k, tex(v))
    for k, v in (switches or {}).items():
        mel.set_material_instance_static_switch_parameter_value(mi, k, v)
    if masked:
        ov = mi.get_editor_property("base_property_overrides")
        ov.set_editor_property("override_blend_mode", True)
        ov.set_editor_property("blend_mode", unreal.BlendMode.BLEND_MASKED)
        mi.set_editor_property("base_property_overrides", ov)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi


def build_instances(hard, emi, glass):
    ivory = srgb_to_linear("#E6E1D6")
    gunmetal = srgb_to_linear("#4A4F55")
    mis = {}
    mis["MI_ASTRA_Panel"] = make_mi("MI_ASTRA_Panel", hard,
        scalars={"RoughnessMin": 0.30, "RoughnessMax": 0.52, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.35,
                 "MacroBrightness": 0.06, "RoughnessVariation": 0.10, "ScratchRoughness": 0.12, "NormalStrength": 0.6},
        vectors={"Tint": ivory},
        textures={"BaseColorMap": "T_PanelPaint_BC", "NormalMap": "T_PanelPaint_N", "ORMMap": "T_PanelPaint_ORM"})
    mis["MI_ASTRA_Structure"] = make_mi("MI_ASTRA_Structure", hard,
        scalars={"RoughnessMin": 0.28, "RoughnessMax": 0.62, "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                 "BaseColorMapInfluence": 0.5, "MacroBrightness": 0.10, "RoughnessVariation": 0.14,
                 "ScratchRoughness": 0.2, "NormalStrength": 0.8},
        vectors={"Tint": [c * 1.05 for c in gunmetal]},
        textures={"BaseColorMap": "T_Gunmetal_BC", "NormalMap": "T_Gunmetal_N", "ORMMap": "T_Gunmetal_ORM"})
    mis["MI_ASTRA_Floor"] = make_mi("MI_ASTRA_Floor", hard,
        scalars={"RoughnessMin": 0.55, "RoughnessMax": 0.85, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.8,
                 "MacroBrightness": 0.12, "RoughnessVariation": 0.12, "ScratchRoughness": -0.15, "NormalStrength": 1.0},
        vectors={"Tint": [0.55, 0.57, 0.6]},
        textures={"BaseColorMap": "T_DeckRubber_BC", "NormalMap": "T_DeckRubber_N", "ORMMap": "T_DeckRubber_ORM"})
    mis["MI_ASTRA_Grate"] = make_mi("MI_ASTRA_Grate", hard,
        scalars={"RoughnessMin": 0.3, "RoughnessMax": 0.6, "MetallicFromMap": 0.0, "MetallicBias": 0.85,
                 "BaseColorMapInfluence": 0.7, "UVScale": 1.0, "NormalStrength": 1.0},
        vectors={"Tint": [0.55, 0.56, 0.58]},
        textures={"BaseColorMap": "T_Walkway_BC", "NormalMap": "T_Walkway_N", "ORMMap": "T_Walkway_ORM",
                  "OpacityMap": "T_Walkway_OP"},
        switches={"UseOpacityMask": True}, masked=True)
    mis["MI_ASTRA_Trim"] = make_mi("MI_ASTRA_Trim", hard,
        scalars={"RoughnessMin": 0.22, "RoughnessMax": 0.45, "MetallicFromMap": 1.0, "BaseColorMapInfluence": 0.6,
                 "MacroBrightness": 0.05, "RoughnessVariation": 0.08, "ScratchRoughness": 0.15, "NormalStrength": 0.7},
        vectors={"Tint": [0.62, 0.64, 0.67]},
        textures={"BaseColorMap": "T_Brushed_BC", "NormalMap": "T_Brushed_N", "ORMMap": "T_Brushed_ORM"})
    mis["MI_ASTRA_Light"] = make_mi("MI_ASTRA_Light", emi,
        scalars={"Intensity": 40.0}, vectors={"EmissiveColor": [1.0, 0.95, 0.88]})
    mis["MI_ASTRA_Glass"] = make_mi("MI_ASTRA_Glass", glass)
    mis["MI_ASTRA_Rubber"] = make_mi("MI_ASTRA_Rubber", hard,
        scalars={"RoughnessMin": 0.55, "RoughnessMax": 0.8, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.5,
                 "MacroBrightness": 0.08, "NormalStrength": 0.5, "ScratchRoughness": 0.0},
        vectors={"Tint": [0.045, 0.047, 0.05]},
        textures={"BaseColorMap": "T_DeckRubber_BC", "NormalMap": "T_DeckRubber_N", "ORMMap": "T_DeckRubber_ORM"})
    mis["MI_ASTRA_FloorBridge"] = make_mi("MI_ASTRA_FloorBridge", hard,
        scalars={"RoughnessMin": 0.26, "RoughnessMax": 0.6, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.7,
                 "MacroBrightness": 0.08, "RoughnessVariation": 0.12, "ScratchRoughness": 0.12, "NormalStrength": 0.7},
        vectors={"Tint": [0.07, 0.078, 0.095]},
        textures={"BaseColorMap": "T_DeckRubber_BC", "NormalMap": "T_DeckRubber_N", "ORMMap": "T_DeckRubber_ORM"})
    mis["MI_ASTRA_Leather"] = make_mi("MI_ASTRA_Leather", hard,
        scalars={"RoughnessMin": 0.34, "RoughnessMax": 0.52, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.3,
                 "MacroBrightness": 0.06, "RoughnessVariation": 0.1, "ScratchRoughness": 0.05, "NormalStrength": 0.35,
                 "UVScale": 3.0},
        vectors={"Tint": [0.035, 0.042, 0.055]},
        textures={"BaseColorMap": "T_DeckRubber_BC", "NormalMap": "T_DeckRubber_N", "ORMMap": "T_DeckRubber_ORM"})
    command_blue = srgb_to_linear("#3E7BFA")
    mis["MI_ASTRA_Accent"] = make_mi("MI_ASTRA_Accent", emi,
        scalars={"Intensity": 25.0}, vectors={"EmissiveColor": command_blue, "BaseColor": [0.05, 0.05, 0.06]})
    mis["MI_ASTRA_Guide"] = make_mi("MI_ASTRA_Guide", emi,
        scalars={"Intensity": 6.0}, vectors={"EmissiveColor": [0.75, 0.9, 1.0], "BaseColor": [0.05, 0.05, 0.06]})
    mis["MI_ASTRA_Screen"] = make_mi("MI_ASTRA_Screen", emi,
        scalars={"Intensity": 3.0, "Roughness": 0.15}, vectors={"EmissiveColor": [0.18, 0.42, 0.85], "BaseColor": [0.01, 0.012, 0.015]})
    log.append("instances: " + ", ".join(mis))
    return mis


def assign(_mis):
    import importlib
    import astra_editor
    importlib.reload(astra_editor)
    log.append("assigned: " + str(astra_editor.assign_materials_by_slot(KIT)))


import_textures()


def master(builder, name):
    try:
        return builder()
    except _Existing:
        log.append(f"{name} kept")
        return eal.load_asset(f"{MAT_DST}/{name}")


hard = master(build_hard, "M_ASTRA_Hard")
emi = master(build_emissive, "M_ASTRA_Emissive")
glass = master(build_glass, "M_ASTRA_Glass")
assign(build_instances(hard, emi, glass))
print(json.dumps(log, indent=1))
