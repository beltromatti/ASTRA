"""M_ASTRA_Hull: the capital ships' hard-surface master. M_ASTRA_Hard's layers (tinted detail maps at UVScale, macro
variation, scratches) plus the hull plating at ship scale (tools/art/hull_panels.py, a 32 m tile at PanelScale):
the tone of each plate, the dark seams and grime (cavity), the relief of seams, rivets, hatches and grilles blended
over the detail normal. The interiors keep M_ASTRA_Hard. Rebuilds in place (the instances keep their parent).
Run in the editor: tools/ue.py pyfile tools/ue_scripts/make_hull_material.py"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
TEX_SRC = ROOT + "/art/_cache/textures"
TEX = "/Game/ASTRA/Materials/Textures"
MAT = "/Game/ASTRA/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ST = unreal.MaterialSamplerType
log = []

# ---- the plating textures (replaced on every run: they are generated)
tasks = []
for name in ("T_HullPanels_N", "T_HullPanels_MSK"):
    t = unreal.AssetImportTask()
    t.filename = os.path.join(TEX_SRC, name + ".png")
    t.destination_path = TEX
    t.automated = True
    t.replace_existing = True
    t.save = False
    tasks.append(t)
tools.import_asset_tasks(tasks)
for name in ("T_HullPanels_N", "T_HullPanels_MSK"):
    tx = eal.load_asset(f"{TEX}/{name}")
    tx.set_editor_property("srgb", False)
    if name.endswith("_N"):
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    else:
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    eal.save_loaded_asset(tx, only_if_is_dirty=False)
log.append("textures")


def tex(name):
    return eal.load_asset(f"{TEX}/{name}")


# ---- graph helpers (as in make_materials.py)
def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def scalar(mat, name, value, x, y, group="ASTRA"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="ASTRA"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group=group)


def texparam(mat, name, texture, sampler, x, y, group="Textures"):
    return E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=texture, sampler_type=sampler, group=group)


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


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


def signed(mat, src, out, amount, x, y):
    """(src - 0.5) * 2 * amount"""
    s = binop(mat, unreal.MaterialExpressionSubtract, src, out, const(mat, 0.5, x - 150, y + 60), "", x, y)
    s2 = binop(mat, unreal.MaterialExpressionMultiply, s, "", const(mat, 2.0, x - 150, y + 120), "", x + 150, y)
    return binop(mat, unreal.MaterialExpressionMultiply, s2, "", amount, "", x + 300, y)


M = unreal.MaterialExpressionMultiply
A = unreal.MaterialExpressionAdd
LERP = unreal.MaterialExpressionLinearInterpolate

path = f"{MAT}/M_ASTRA_Hull"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)
    mel.delete_all_material_expressions(m)
    for e in mel.get_material_expressions(m):   # what delete_all leaves behind (custom nodes, parameters)
        mel.delete_material_expression(m, e)
else:
    m = tools.create_asset("M_ASTRA_Hull", MAT, unreal.Material, unreal.MaterialFactoryNew())

uv = E(m, unreal.MaterialExpressionTextureCoordinate, -2200, 0)
uvt = binop(m, M, uv, "", scalar(m, "UVScale", 4.0, -2200, 120, "UV"), "", -2000, 40)
puv = binop(m, M, uv, "", scalar(m, "PanelScale", 0.25, -2200, 1700, "Plating"), "", -2000, 1640)

# detail layer (the same parameters as M_ASTRA_Hard)
bc = texparam(m, "BaseColorMap", tex("T_PanelPaint_BC"), ST.SAMPLERTYPE_COLOR, -1700, -400)
nm = texparam(m, "NormalMap", tex("T_PanelPaint_N"), ST.SAMPLERTYPE_NORMAL, -1700, 300)
orm = texparam(m, "ORMMap", tex("T_PanelPaint_ORM"), ST.SAMPLERTYPE_MASKS, -1700, 0)
for t in (bc, nm, orm):
    link(uvt, "", t, "UVs")
# plating layer
pn = texparam(m, "PanelNormal", tex("T_HullPanels_N"), ST.SAMPLERTYPE_NORMAL, -1700, 1700, "Plating")
pm = texparam(m, "PanelMasks", tex("T_HullPanels_MSK"), ST.SAMPLERTYPE_MASKS, -1700, 2000, "Plating")
for t in (pn, pm):
    link(puv, "", t, "UVs")

# macro variation (shifted per object) and scratches
muv0 = binop(m, M, uv, "", scalar(m, "MacroScale", 0.6, -2200, 700, "Variation"), "", -2000, 640)
objm = mask(m, E(m, unreal.MaterialExpressionObjectPositionWS, -2200, 820), "", -2050, 820, r=True, g=True)
objoff = binop(m, M, objm, "", const(m, 0.00173, -2050, 900), "", -1900, 840)
muv = binop(m, A, muv0, "", objoff, "", -1800, 700)
macro = texparam(m, "MacroNoise", tex("T_ASTRA_MacroNoise"), ST.SAMPLERTYPE_MASKS, -1700, 700, "Variation")
link(muv, "", macro, "UVs")
suv = binop(m, M, uv, "", scalar(m, "ScratchScale", 0.5, -2200, 1100, "Variation"), "", -2000, 1100)
scr = texparam(m, "ScratchMask", tex("T_ASTRA_Scratches_M"), ST.SAMPLERTYPE_LINEAR_GRAYSCALE, -1700, 1100, "Variation")
link(suv, "", scr, "UVs")

# base colour = Tint * lerp(1, map, influence) * macro * plate tone * lerp(1, cavity, amount)
one = const(m, 1.0, -1300, -420)
lerpbc = E(m, LERP, -1100, -450)
link(one, "", lerpbc, "A"); link(bc, "RGB", lerpbc, "B")
link(scalar(m, "BaseColorMapInfluence", 0.5, -1300, -480, "Color"), "", lerpbc, "Alpha")
tinted = binop(m, M, lerpbc, "", vector(m, "Tint", (1, 1, 1, 1), -1300, -600, "Color"), "RGB", -900, -500)
mfac = binop(m, A, signed(m, macro, "R", scalar(m, "MacroBrightness", 0.16, -1300, 560, "Variation"), -1250, 500), "", one, "", -700, 520)
tfac = binop(m, A, signed(m, pm, "B", scalar(m, "PanelTone", 0.14, -1300, 1900, "Plating"), -1250, 1840), "", one, "", -700, 1860)
cav = E(m, LERP, -900, 2050)
link(one, "", cav, "A"); link(pm, "R", cav, "B"); link(scalar(m, "PanelCavity", 0.85, -1300, 2100, "Plating"), "", cav, "Alpha")
c1 = binop(m, M, tinted, "", mfac, "", -500, -450)
c2 = binop(m, M, c1, "", tfac, "", -350, -400)
c3 = binop(m, M, c2, "", cav, "", -200, -350)
mel.connect_material_property(c3, "", unreal.MaterialProperty.MP_BASE_COLOR)

# roughness = lerp(min, max, map) + macro var + scratches + plate offset
rl = E(m, LERP, -1100, 20)
link(scalar(m, "RoughnessMin", 0.3, -1300, 0, "Surface"), "", rl, "A")
link(scalar(m, "RoughnessMax", 0.6, -1300, 60, "Surface"), "", rl, "B")
link(orm, "G", rl, "Alpha")
half = const(m, 0.5, -1300, 820)
mg = binop(m, M, binop(m, unreal.MaterialExpressionSubtract, macro, "G", half, "", -1150, 760), "",
           scalar(m, "RoughnessVariation", 0.18, -1300, 760, "Variation"), "", -1000, 760)
sc2 = binop(m, M, scr, "R", scalar(m, "ScratchRoughness", 0.18, -1300, 1180, "Variation"), "", -1000, 1120)
pr = signed(m, pm, "G", scalar(m, "PanelRoughness", 0.1, -1300, 2250, "Plating"), -1250, 2200)
r1 = binop(m, A, rl, "", mg, "", -700, 100)
r2 = binop(m, A, r1, "", sc2, "", -550, 140)
r3 = binop(m, A, r2, "", pr, "", -400, 180)
rs = E(m, unreal.MaterialExpressionSaturate, -250, 180)
link(r3, "", rs, "")
mel.connect_material_property(rs, "", unreal.MaterialProperty.MP_ROUGHNESS)

# metallic = map * scale + bias
mm = binop(m, M, orm, "B", scalar(m, "MetallicFromMap", 0.0, -1300, 240, "Surface"), "", -1100, 240)
ma = binop(m, A, mm, "", scalar(m, "MetallicBias", 0.0, -1300, 300, "Surface"), "", -950, 260)
ms = E(m, unreal.MaterialExpressionSaturate, -800, 260)
link(ma, "", ms, "")
mel.connect_material_property(ms, "", unreal.MaterialProperty.MP_METALLIC)

# ambient occlusion: the detail map's and the plating's cavity
ao = binop(m, M, orm, "R", cav, "", -600, 320)
mel.connect_material_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

# normal: the plating's relief under the detail (whiteout blend: xy added, z multiplied)
flat = E(m, unreal.MaterialExpressionConstant3Vector, -1300, 360, constant=unreal.LinearColor(0, 0, 1, 1))
dn = E(m, LERP, -1000, 380)
link(flat, "", dn, "A"); link(nm, "RGB", dn, "B"); link(scalar(m, "NormalStrength", 1.0, -1300, 420, "Surface"), "", dn, "Alpha")
pnl = E(m, LERP, -1000, 1500)
link(flat, "", pnl, "A"); link(pn, "RGB", pnl, "B"); link(scalar(m, "PanelNormalStrength", 1.0, -1300, 1560, "Plating"), "", pnl, "Alpha")
xy = binop(m, A, mask(m, pnl, "", -850, 1500, r=True, g=True), "", mask(m, dn, "", -850, 380, r=True, g=True), "", -700, 900)
z = binop(m, M, mask(m, pnl, "", -850, 1580, b=True), "", mask(m, dn, "", -850, 460, b=True), "", -700, 1000)
ap = binop(m, unreal.MaterialExpressionAppendVector, xy, "", z, "", -550, 950)
nn = E(m, unreal.MaterialExpressionNormalize, -400, 950)
link(ap, "", nn, "")
mel.connect_material_property(nn, "", unreal.MaterialProperty.MP_NORMAL)

m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append(f"M_ASTRA_Hull ok ({mel.get_num_material_expressions(m)} nodes)")
print(json.dumps(log))
