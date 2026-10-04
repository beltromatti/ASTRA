"""The materials of the war's visual effects (Source/ASTRA/AstraWarFX*.cpp; how it is made and why: docs/VFX.md).

Run in the editor, with no game or PIE running (the masters are rebuilt in place):
  uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_textures.py     # the flipbooks, once
  tools/ue.py pyfile tools/ue_scripts/make_war_fx.py

Makes, in /Game/ASTRA/Materials (all unlit, for instanced static meshes: the game draws every shot, spark, flash, fireball, puff of smoke and drive
plume as an instance of an engine sphere or cylinder, one component per material):
  M_WAR_Dart     additive   a stretched sphere: a slug, a spark, a bead of a missile's trail
  M_WAR_Tube     additive   a cylinder: a laser beam, a stream of tracers
  M_WAR_Glow     additive   a sphere drawn as a screen-facing disc: flashes, flares, hot spots, a drive's glare, the limb of a blast wave
  M_WAR_Fire     additive   a sphere drawn as a disc with a flipbook of fire (T_WAR_Fire)
  M_WAR_Smoke    translucent  the same with a flipbook of smoke (T_WAR_Smoke)
  M_WAR_Plume    additive   a cylinder narrowing to a tip: a drive's exhaust
  M_WAR_Shield   additive, two-sided   a ship's shield shell (an ellipsoid): hexagons lit round each blow; MID parameters per ship
  M_WAR_Debris   lit, opaque   chunks of metal (a cube): its side's colour and an ember glow while hot, per instance
  M_WAR_DamageDecal + Instances/MI_WAR_Damage_<Burn|Hole|Torn|Impact|Strafe|Melt|Gouge|Blast>   deferred decals from the damage atlas
Textures: T_WAR_Fire, T_WAR_Smoke (art/_cache/fx, from tools/art/war_fx_textures.py).
The per-instance custom data every instanced material reads is in AstraWarFX.h (AstraFx::Fill): 0-2 colour, 3 intensity, 4 age, 5-6 parameters,
7 seed, 8 width, 9 length (metres). The shaders are in tools/ue_scripts/war_fx_hlsl.py (and previewed by tools/art/war_fx_shader_preview.py).
Every material has its own try/except: one that fails does not stop the others, and the log at the end says which are done.
"""
import importlib
import json
import os
import sys
import traceback

import unreal

ROOT = os.environ.get("ASTRA_ROOT", "/Users/beltromatti/Desktop/ASTRA")
sys.path.insert(0, ROOT + "/tools/ue_scripts")
import war_fx_hlsl as H  # noqa: E402
importlib.reload(H)

TEX_SRC = ROOT + "/art/_cache/fx"
TEX = "/Game/ASTRA/Materials/Textures"
MAT = "/Game/ASTRA/Materials"
MI = "/Game/ASTRA/Materials/Instances"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ST = unreal.MaterialSamplerType
FLOAT = unreal.CustomMaterialOutputType
log = []
failed = []


# ------------------------------------------------------------------------------------------------------------------------ graph helpers
def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out!r} -> {b.get_name()}.{b_in!r}")


def scalar(mat, name, value, x, y, group="War"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="War"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group=group)


def const(mat, v, x, y):
    return E(mat, unreal.MaterialExpressionConstant, x, y, r=v)


def mask(mat, src, out, x, y, r=False, g=False, b=False, a=False):
    e = E(mat, unreal.MaterialExpressionComponentMask, x, y, r=r, g=g, b=b, a=a)
    link(src, out, e, "")
    return e


def custom(mat, code, inputs, x, y, out=FLOAT.CMOT_FLOAT3):
    """A Custom node: inputs = [(name, (source node, source output pin)), ...]."""
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


def cd(mat, index, x, y):
    """One float of the instance's custom data."""
    return E(mat, unreal.MaterialExpressionPerInstanceCustomData, x, y, data_index=index, const_default_value=0.0)


def cd3(mat, index, x, y):
    return E(mat, unreal.MaterialExpressionPerInstanceCustomData3Vector, x, y, data_index=index, const_default_value=unreal.LinearColor(0, 0, 0, 0))


def fresh(name, blend, two_sided=False, instanced=True, unlit=True):
    """The material, emptied (or made): unlit, for instanced static meshes."""
    path = f"{MAT}/{name}"
    if eal.does_asset_exist(path):
        m = eal.load_asset(path)
        for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
        for e in mel.get_material_expressions(m):          # what delete_all leaves behind
            mel.delete_material_expression(m, e)
    else:
        m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    if unlit:
        m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", blend)
    m.set_editor_property("two_sided", two_sided)
    if instanced:
        m.set_editor_property("used_with_instanced_static_meshes", True)
    return m


def finish(m):
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    log.append(f"{m.get_name()} ok ({mel.get_num_material_expressions(m)} nodes)")


def local_position(mat, x, y):
    return E(mat, unreal.MaterialExpressionLocalPosition, x, y, included_offsets=unreal.PositionIncludedOffsets.EXCLUDE_OFFSETS)


def view_property(mat, prop, x, y):
    return E(mat, unreal.MaterialExpressionViewProperty, x, y, property_=prop)


def instance_to_world(mat, src, x, y):
    t = E(mat, unreal.MaterialExpressionTransform, x, y)
    t.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_INSTANCE)
    t.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_WORLD)
    link(src, "", t, "")
    return t


def world_to_view(mat, src, x, y):
    t = E(mat, unreal.MaterialExpressionTransform, x, y)
    t.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
    t.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_VIEW)
    link(src, "", t, "")
    return t


def min_size(mat, spherical, min_px, code=None, with_lz=False):
    """The vertex shader that keeps a thing a few pixels wide however far and however zoomed: its radial direction in world units, its distance
    from the view's own field of view and size (war_fx_hlsl.MINSIZE)."""
    lp = local_position(mat, -2600, 1500)
    if spherical:
        radial = lp
        radial_out = ""
    else:
        rg = mask(mat, lp, "", -2400, 1500, r=True, g=True)
        zero = const(mat, 0.0, -2400, 1580)
        ap = E(mat, unreal.MaterialExpressionAppendVector, -2200, 1520)
        link(rg, "", ap, "A")
        link(zero, "", ap, "B")
        radial, radial_out = ap, ""
    rad = instance_to_world(mat, radial, -2000, 1500)
    wp = E(mat, unreal.MaterialExpressionWorldPosition, -2000, 1650, world_position_shader_offset=unreal.WorldPositionIncludedOffsets.WPT_CAMERA_RELATIVE_NO_OFFSETS)
    tanh = view_property(mat, unreal.MaterialExposedViewProperty.MEVP_TAN_HALF_FIELD_OF_VIEW, -2000, 1750)
    vsz = view_property(mat, unreal.MaterialExposedViewProperty.MEVP_VIEW_SIZE, -2000, 1850)
    mp = scalar(mat, "MinPx", min_px, -2000, 1950)
    ins = [("RadW", (rad, "")), ("WPrel", (wp, "")), ("TanHalf", (tanh, "")), ("ViewSz", (vsz, "")), ("MinPx", (mp, ""))]
    if with_lz:
        ins.append(("LZ", (mask(mat, local_position(mat, -2600, 2050), "", -2400, 2050, b=True), "")))
    c = custom(mat, code or H.MINSIZE, ins, -1600, 1700)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    return c


# ------------------------------------------------------------------------------------------------------------------------ textures
def import_flipbook(name):
    src = os.path.join(TEX_SRC, name + ".png")
    if not os.path.exists(src):
        raise RuntimeError(f"{src} missing: run tools/art/war_fx_textures.py first")
    t = unreal.AssetImportTask()
    t.filename = src
    t.destination_path = TEX
    t.automated = True
    t.replace_existing = True
    t.save = False
    tools.import_asset_tasks([t])
    tx = eal.load_asset(f"{TEX}/{name}")
    tx.set_editor_property("srgb", False)                                   # data, not colour
    tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_BC7)
    tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    tx.set_editor_property("never_stream", True)                            # an effect's first frame must not wait for a mip to arrive
    tx.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    tx.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    eal.save_loaded_asset(tx, only_if_is_dirty=False)
    return tx


# ------------------------------------------------------------------------------------------------------------------------ the materials
def build_dart():
    m = fresh("M_WAR_Dart", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("enable_responsive_aa", True)                     # sharp small moving things under the temporal upscaler
    fr = E(m, unreal.MaterialExpressionFresnel, -1400, -200, exponent=1.0, base_reflect_fraction=0.0)
    lz = mask(m, local_position(m, -1600, -100), "", -1400, -100, b=True)
    tm = E(m, unreal.MaterialExpressionTime, -1400, 300)
    ins = [("Fr", (fr, "")), ("LZ", (lz, "")), ("Col", (cd3(m, 0, -1400, 0), "")), ("Inten", (cd(m, 3, -1400, 80), "")), ("Age", (cd(m, 4, -1400, 140), "")),
           ("Style", (cd(m, 5, -1400, 200), "")), ("P2", (cd(m, 6, -1400, 240), "")), ("Seed", (cd(m, 7, -1400, 280), "")), ("Tm", (tm, ""))]
    c = custom(m, H.DART, ins, -900, 0)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    min_size(m, False, 2.4)
    finish(m)


def build_tube():
    m = fresh("M_WAR_Tube", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("enable_responsive_aa", True)
    lp = local_position(m, -1800, -200)
    rg = mask(m, lp, "", -1600, -300, r=True, g=True)
    ap = E(m, unreal.MaterialExpressionAppendVector, -1400, -280)
    link(rg, "", ap, "A")
    link(const(m, 0.0, -1600, -220), "", ap, "B")
    nw = instance_to_world(m, ap, -1200, -280)
    camv = E(m, unreal.MaterialExpressionCameraVectorWS, -1200, -120)
    tm = E(m, unreal.MaterialExpressionTime, -1200, 380)
    ins = [("NW", (nw, "")), ("CamV", (camv, "")), ("LP", (lp, "")), ("LenM", (cd(m, 9, -1200, 0), "")), ("Col", (cd3(m, 0, -1200, 40), "")),
           ("Inten", (cd(m, 3, -1200, 120), "")), ("Age", (cd(m, 4, -1200, 160), "")), ("Style", (cd(m, 5, -1200, 200), "")), ("P2", (cd(m, 6, -1200, 240), "")),
           ("Seed", (cd(m, 7, -1200, 280), "")), ("Tm", (tm, ""))]
    c = custom(m, H.TUBE, ins, -800, 0)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    min_size(m, False, 2.0)
    finish(m)


def screen_normal(m, x, y):
    """The pixel's normal in view space: where on the screen-facing disc it is."""
    pn = E(m, unreal.MaterialExpressionPixelNormalWS, x, y)
    return world_to_view(m, pn, x + 200, y)


def soft_depth(m, size_node, x, y):
    """How far the scene behind the pixel is, as a fade (a fireball is not cut hard where it meets a hull)."""
    sd = E(m, unreal.MaterialExpressionSceneDepth, x, y)
    pd = E(m, unreal.MaterialExpressionPixelDepth, x, y + 80)
    return custom(m, """
float fadeCm = max(SizeM * 100.0 * 0.22, 100.0);
return saturate((SD - PD) / fadeCm);
""", [("SD", (sd, "")), ("PD", (pd, "")), ("SizeM", (size_node, ""))], x + 300, y, FLOAT.CMOT_FLOAT1)


def build_glow():
    m = fresh("M_WAR_Glow", unreal.BlendMode.BLEND_ADDITIVE)
    fr = E(m, unreal.MaterialExpressionFresnel, -1400, -250, exponent=1.0, base_reflect_fraction=0.0)
    vn = screen_normal(m, -1600, -80)
    tm = E(m, unreal.MaterialExpressionTime, -1400, 380)
    ins = [("Fr", (fr, "")), ("VN", (vn, "")), ("Col", (cd3(m, 0, -1400, 0), "")), ("Inten", (cd(m, 3, -1400, 80), "")), ("Age", (cd(m, 4, -1400, 120), "")),
           ("Kind", (cd(m, 5, -1400, 160), "")), ("Seed", (cd(m, 7, -1400, 240), "")), ("Tm", (tm, ""))]
    c = custom(m, H.GLOW, ins, -900, 0)
    df = soft_depth(m, cd(m, 8, -1400, 300), -1400, 500)
    out = E(m, unreal.MaterialExpressionMultiply, -500, 0)
    link(c, "", out, "A")
    link(df, "", out, "B")
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    min_size(m, True, 3.0)
    finish(m)


def flipbook_nodes(m, tex, vn, uv_code=None):
    """The two frames of a flipbook (their UVs from the age), sampled, and the blend between them."""
    age, seed = cd(m, 4, -1900, 700), cd(m, 7, -1900, 760)
    uvs = custom(m, H.FIRE_UV, [("VN", (vn, "")), ("Age", (age, "")), ("Seed", (seed, ""))], -1500, 700, FLOAT.CMOT_FLOAT4)
    uva = E(m, unreal.MaterialExpressionAppendVector, -1250, 700)       # (x, y) of the first frame
    link(mask(m, uvs, "", -1400, 680, r=True), "", uva, "A")
    link(mask(m, uvs, "", -1400, 740, g=True), "", uva, "B")
    uvb = E(m, unreal.MaterialExpressionAppendVector, -1250, 820)       # (z, w): the second
    link(mask(m, uvs, "", -1400, 800, b=True), "", uvb, "A")
    link(mask(m, uvs, "", -1400, 860, a=True), "", uvb, "B")
    ta = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -1000, 700, parameter_name="Flipbook", texture=tex, sampler_type=ST.SAMPLERTYPE_LINEAR_COLOR)
    tb = E(m, unreal.MaterialExpressionTextureSample, -1000, 860, texture=tex, sampler_type=ST.SAMPLERTYPE_LINEAR_COLOR)
    link(uva, "", ta, "UVs")
    link(uvb, "", tb, "UVs")
    w = custom(m, H.FIRE_W, [("Age", (age, ""))], -1500, 960, FLOAT.CMOT_FLOAT1)
    return ta, tb, w


def build_fire(tex):
    m = fresh("M_WAR_Fire", unreal.BlendMode.BLEND_ADDITIVE)
    vn = screen_normal(m, -2200, 560)
    ta, tb, w = flipbook_nodes(m, tex, vn)
    ins = [("TA", (ta, "RGB")), ("TB", (tb, "RGB")), ("W", (w, "")), ("VN", (vn, "")), ("Col", (cd3(m, 0, -1000, 1100), "")), ("Inten", (cd(m, 3, -1000, 1180), ""))]
    c = custom(m, H.FIRE_SHADE, ins, -500, 800)
    df = soft_depth(m, cd(m, 8, -1000, 1260), -1000, 1400)
    out = E(m, unreal.MaterialExpressionMultiply, -150, 800)
    link(c, "", out, "A")
    link(df, "", out, "B")
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def build_smoke(tex):
    m = fresh("M_WAR_Smoke", unreal.BlendMode.BLEND_TRANSLUCENT)
    vn = screen_normal(m, -2200, 560)
    ta, tb, w = flipbook_nodes(m, tex, vn)
    ins = [("TA", (ta, "RGB")), ("TB", (tb, "RGB")), ("W", (w, "")), ("VN", (vn, "")), ("Col", (cd3(m, 0, -1000, 1100), "")), ("Inten", (cd(m, 3, -1000, 1180), "")),
           ("Age", (cd(m, 4, -1000, 1240), "")), ("Dark", (cd(m, 6, -1000, 1300), "")), ("Glow", (cd(m, 9, -1000, 1360), ""))]
    c = custom(m, H.SMOKE_SHADE, ins, -500, 800, FLOAT.CMOT_FLOAT4)
    df = soft_depth(m, cd(m, 8, -1000, 1420), -1000, 1560)
    rgb = mask(m, c, "", -250, 760, r=True, g=True, b=True)
    alpha = mask(m, c, "", -250, 860, a=True)
    op = E(m, unreal.MaterialExpressionMultiply, 0, 860)
    link(alpha, "", op, "A")
    link(df, "", op, "B")
    mel.connect_material_property(rgb, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(op, "", unreal.MaterialProperty.MP_OPACITY)
    finish(m)


def build_plume():
    m = fresh("M_WAR_Plume", unreal.BlendMode.BLEND_ADDITIVE)
    lp = local_position(m, -1800, -200)
    rg = mask(m, lp, "", -1600, -300, r=True, g=True)
    ap = E(m, unreal.MaterialExpressionAppendVector, -1400, -280)
    link(rg, "", ap, "A")
    link(const(m, 0.0, -1600, -220), "", ap, "B")
    nw = instance_to_world(m, ap, -1200, -280)
    camv = E(m, unreal.MaterialExpressionCameraVectorWS, -1200, -120)
    tm = E(m, unreal.MaterialExpressionTime, -1200, 380)
    ins = [("NW", (nw, "")), ("CamV", (camv, "")), ("LP", (lp, "")), ("LenM", (cd(m, 9, -1200, 0), "")), ("Inten", (cd(m, 3, -1200, 120), "")),
           ("Faction", (cd(m, 5, -1200, 200), "")), ("Sputter", (cd(m, 6, -1200, 240), "")), ("Seed", (cd(m, 7, -1200, 280), "")), ("Tm", (tm, ""))]
    c = custom(m, H.PLUME, ins, -800, 0)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    min_size(m, False, 2.0, code=H.MINSIZE_PLUME, with_lz=True)
    finish(m)


def build_shield():
    m = fresh("M_WAR_Shield", unreal.BlendMode.BLEND_ADDITIVE, two_sided=True)
    lp = local_position(m, -1800, 0)
    tm = E(m, unreal.MaterialExpressionTime, -1800, 200)
    ins = [("LP", (lp, "")), ("Tm", (tm, "")),
           ("Axes", (vector(m, "Axes", (400, 100, 80, 0), -1800, 300), "RGBA")),
           ("Col", (vector(m, "Color", (0.28, 0.6, 1.0, 1), -1800, 380), "RGBA")),
           ("HexSize", (scalar(m, "HexSize", 12.0, -1800, 460), "")),
           ("Gain", (scalar(m, "Gain", 1.0, -1800, 520), "")),
           ("Collapse", (vector(m, "Collapse", (1, 0, 0, 0), -1800, 580), "RGBA"))]
    for i in range(6):
        ins.append((f"Hit{i}", (vector(m, f"Hit{i}", (0, 0, 1, 0), -1800, 700 + 80 * i), "RGBA")))
    for i in range(6):
        ins.append((f"Info{i}", (vector(m, f"Info{i}", (10, 1, 0, 0), -1800, 1200 + 80 * i), "RGBA")))
    c = custom(m, H.SHIELD, ins, -1000, 600)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def build_debris():
    """Chunks of metal thrown off a hull: lit by the star, the colour of its side and an ember glow while it is hot, both per instance."""
    m = fresh("M_WAR_Debris", unreal.BlendMode.BLEND_OPAQUE, unlit=False)
    col = cd3(m, 0, -700, 0)
    heat = cd(m, 3, -700, 200)
    ember = E(m, unreal.MaterialExpressionConstant3Vector, -700, 120, constant=unreal.LinearColor(1.0, 0.38, 0.10, 1))
    em = E(m, unreal.MaterialExpressionMultiply, -400, 150)
    link(ember, "", em, "A")
    link(heat, "", em, "B")
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(const(m, 0.5, -400, 280), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(const(m, 0.45, -400, 340), "", unreal.MaterialProperty.MP_METALLIC)
    mel.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def build_decal():
    """The damage decal: the atlas T_ShipDamage_A/N (ARTE-NAVI), the cell chosen by AtlasRect (x, y, w, h). The older M_ASTRA_DamageDecal connects the
    parameter's RGB pin and then masks its alpha, which a float3 does not have; this one takes the RGBA pin."""
    atlas_tex = eal.load_asset(f"{TEX}/T_ShipDamage_A")
    norm_tex = eal.load_asset(f"{TEX}/T_ShipDamage_N")
    if not atlas_tex or not norm_tex:
        raise RuntimeError("T_ShipDamage_A / T_ShipDamage_N missing: run make_ship_materials_v3.py first")
    m = fresh("M_WAR_DamageDecal", unreal.BlendMode.BLEND_TRANSLUCENT, instanced=False, unlit=False)
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_DEFERRED_DECAL)
    uv = E(m, unreal.MaterialExpressionTextureCoordinate, -1600, 0)
    rect = vector(m, "AtlasRect", (0.0, 0.0, 0.25, 0.5), -1600, 100, "Atlas")
    scale = E(m, unreal.MaterialExpressionMultiply, -1200, 0)
    link(uv, "", scale, "A")
    link(mask(m, rect, "RGBA", -1400, 100, b=True, a=True), "", scale, "B")
    auv = E(m, unreal.MaterialExpressionAdd, -1000, 60)
    link(scale, "", auv, "A")
    link(mask(m, rect, "RGBA", -1400, 200, r=True, g=True), "", auv, "B")
    atlas = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -800, 0, parameter_name="Damage", texture=atlas_tex, sampler_type=ST.SAMPLERTYPE_LINEAR_COLOR)
    dn = E(m, unreal.MaterialExpressionTextureSampleParameter2D, -800, 300, parameter_name="DamageNormal", texture=norm_tex, sampler_type=ST.SAMPLERTYPE_NORMAL)
    link(auv, "", atlas, "UVs")
    link(auv, "", dn, "UVs")
    heat = scalar(m, "Heat", 1.0, -800, 500)
    breach = scalar(m, "Breach", 0.0, -800, 560)
    fade = scalar(m, "Fade", 1.0, -800, 620)
    ember = vector(m, "EmberColor", (1.0, 0.33, 0.07, 1), -800, 700)
    base = custom(m, """
float3 soot_hi = float3(0.005, 0.0045, 0.004);
float3 soot_lo = float3(0.035, 0.03, 0.026);
float3 col = lerp(soot_lo, soot_hi, A.r);
col = lerp(col, float3(0.0, 0.0, 0.0), A.b * Breach);
return col;
""", [("A", (atlas, "RGB")), ("Breach", (breach, ""))], -400, 0)
    glow = custom(m, """
float g = saturate(A.g + A.b * Breach * 1.5) * Heat * Heat;
return g;
""", [("A", (atlas, "RGB")), ("Breach", (breach, "")), ("Heat", (heat, ""))], -400, 300, FLOAT.CMOT_FLOAT1)
    op = E(m, unreal.MaterialExpressionMultiply, -400, 500)
    link(atlas, "A", op, "A")
    link(fade, "", op, "B")
    op2 = E(m, unreal.MaterialExpressionMultiply, -200, 500)
    link(op, "", op2, "A")
    link(const(m, 1.6, -400, 560), "", op2, "B")
    sat = E(m, unreal.MaterialExpressionSaturate, 0, 500)
    link(op2, "", sat, "")
    em = E(m, unreal.MaterialExpressionMultiply, 200, 400)
    link(ember, "RGB", em, "A")
    gk = E(m, unreal.MaterialExpressionMultiply, 0, 400)
    link(glow, "", gk, "A")
    link(const(m, 30.0, -100, 420), "", gk, "B")
    link(gk, "", em, "B")
    mel.connect_material_property(base, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(const(m, 0.9, -100, 100), "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(dn, "RGB", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(sat, "", unreal.MaterialProperty.MP_OPACITY)
    finish(m)
    # the eight instances, one per cell of the atlas
    names = ("Burn", "Hole", "Torn", "Impact", "Strafe", "Melt", "Gouge", "Blast")
    for i, n in enumerate(names):
        p = f"{MI}/MI_WAR_Damage_{n}"
        inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(f"MI_WAR_Damage_{n}", MI, unreal.MaterialInstanceConstant,
                                                                                    unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(inst, m)
        mel.set_material_instance_vector_parameter_value(inst, "AtlasRect", unreal.LinearColor((i % 4) * 0.25, (i // 4) * 0.5, 0.25, 0.5))
        mel.set_material_instance_scalar_parameter_value(inst, "Heat", 1.0)
        mel.set_material_instance_scalar_parameter_value(inst, "Breach", 1.0 if n in ("Hole", "Torn") else 0.0)
        mel.set_material_instance_scalar_parameter_value(inst, "Fade", 1.0)
        mel.update_material_instance(inst)
        eal.save_loaded_asset(inst, only_if_is_dirty=False)
    log.append("MI_WAR_Damage_* ok (8)")


def attempt(name, fn, *args):
    try:
        fn(*args)
    except Exception as ex:                                                  # one failing must not lose the others
        failed.append(name)
        log.append(f"{name} FAILED: {ex!r}")
        print(traceback.format_exc())


fire_tex = smoke_tex = None
try:
    fire_tex = import_flipbook("T_WAR_Fire")
    smoke_tex = import_flipbook("T_WAR_Smoke")
    log.append("textures ok")
except Exception as ex:
    failed.append("textures")
    log.append(f"textures FAILED: {ex!r}")
    print(traceback.format_exc())

attempt("M_WAR_Dart", build_dart)
attempt("M_WAR_Tube", build_tube)
attempt("M_WAR_Glow", build_glow)
attempt("M_WAR_Plume", build_plume)
attempt("M_WAR_Shield", build_shield)
attempt("M_WAR_Debris", build_debris)
if fire_tex:
    attempt("M_WAR_Fire", build_fire, fire_tex)
if smoke_tex:
    attempt("M_WAR_Smoke", build_smoke, smoke_tex)
attempt("M_WAR_DamageDecal", build_decal)
print(json.dumps({"log": log, "failed": failed}, indent=1))
print("WAR_FX_MATERIALS_" + ("OK" if not failed else "PARTIAL"))
