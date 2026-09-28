"""New Ravenna's ground and sea materials.

M_ASTRA_Terrain (+ MI_NR_Terrain): five ground layers blended by what the ground is — sand at the waterline, rock on
steep slopes (projected on three planes so cliffs do not smear), snow high up, grass and drier meadow in patches — with
a macro variation that breaks the tiling from the air. The height is measured from the terrain's own origin (sea level).
M_NR_Ocean (+ MI_NR_Ocean): an opaque sea, two panning wave normals at different scales, deep colour, low roughness
(the sky and the sun do the rest).
Rebuilds in place. Run in the editor: tools/ue.py pyfile tools/ue_scripts/make_planet_materials.py"""
import json
import os

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

LAYERS = ("Rock", "Grass", "Meadow", "Sand", "Snow")
EXTRA = ("RockRed", "RockLight")   # rock for other worlds' walls (MI_W_Terrain_*, tools/ue_scripts/make_world_materials.py)
names = [f"T_{L}_{k}" for L in LAYERS + EXTRA for k in ("BC", "N", "ORM")] + ["T_Water_N"]
tasks = []
for n in names:
    if eal.does_asset_exist(f"{TEX}/{n}"):
        continue
    t = unreal.AssetImportTask()
    t.filename = os.path.join(TEX_SRC, n + ".png")
    t.destination_path = TEX
    t.automated = True
    t.replace_existing = True
    t.save = False
    tasks.append(t)
if tasks:
    tools.import_asset_tasks(tasks)
for n in names:
    tx = eal.load_asset(f"{TEX}/{n}")
    if n.endswith("_N"):
        tx.set_editor_property("srgb", False)
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    elif n.endswith("_BC"):
        tx.set_editor_property("srgb", True)
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    else:
        tx.set_editor_property("srgb", False)
        tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    eal.save_loaded_asset(tx, only_if_is_dirty=False)
log.append(f"textures ({len(tasks)} imported)")


def tex(name):
    return eal.load_asset(f"{TEX}/{name}")


def E(mat, cls, x, y, **props):
    e = mel.create_material_expression(mat, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, a_out, b, b_in):
    if not mel.connect_material_expressions(a, a_out, b, b_in):
        raise RuntimeError(f"link failed: {a.get_name()}.{a_out} -> {b.get_name()}.{b_in}")


def scalar(mat, name, value, x, y, group="Terrain"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="Terrain"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group=group)


def sample(mat, name, texture, sampler, uv, x, y, group="Layers"):
    s = E(mat, unreal.MaterialExpressionTextureSampleParameter2D, x, y, parameter_name=name, texture=texture, sampler_type=sampler, group=group)
    s.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
    link(uv, "", s, "UVs")
    return s


def binop(mat, cls, a, a_out, b, b_out, x, y):
    e = E(mat, cls, x, y)
    link(a, a_out, e, "A")
    link(b, b_out, e, "B")
    return e


def const(mat, v, x, y):
    return E(mat, unreal.MaterialExpressionConstant, x, y, r=v)


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
        for e in mel.get_material_expressions(m):   # what delete_all leaves behind (custom nodes, parameters)
            mel.delete_material_expression(m, e)
        return m
    return tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())


M = unreal.MaterialExpressionMultiply
ADD = unreal.MaterialExpressionAdd
LERP = unreal.MaterialExpressionLinearInterpolate

# =========================================================================================== the ground
m = fresh("M_ASTRA_Terrain")
wp = E(m, unreal.MaterialExpressionWorldPosition, -2600, 0)
op = E(m, unreal.MaterialExpressionActorPositionWS, -2600, 120)          # the zone's origin (sea level): every tile shares it
local = binop(m, unreal.MaterialExpressionSubtract, wp, "", op, "", -2450, 60)
loc_m = binop(m, M, local, "", const(m, 0.01, -2450, 160), "", -2300, 60)          # metres, terrain frame
nrm = E(m, unreal.MaterialExpressionVertexNormalWS, -2600, 300)
macro_uv = E(m, unreal.MaterialExpressionComponentMask, -2150, 700, r=True, g=True)
link(binop(m, M, loc_m, "", const(m, 1.0 / 900.0, -2300, 760), "", -2200, 700), "", macro_uv, "")
macro1 = sample(m, "MacroNoise", tex("T_ASTRA_MacroNoise"), ST.SAMPLERTYPE_MASKS, macro_uv, -2000, 700, "Variation")
# a second sampling, broader and turned, breaks the first one's 900 m repeat (it shows as a grid from the air)
macro_uv2 = custom(m, "return float2(P.x * 0.8 - P.y * 0.6, P.x * 0.6 + P.y * 0.8) / 3700.0 + float2(0.37, 0.61);",
                   [("P", (loc_m, ""))], -2150, 860, unreal.CustomMaterialOutputType.CMOT_FLOAT2)
macro2 = sample(m, "MacroNoise2", tex("T_ASTRA_MacroNoise"), ST.SAMPLERTYPE_MASKS, macro_uv2, -2000, 860, "Variation")
macro = custom(m, "return saturate(0.5 + 0.72 * ((A - 0.5) + (B - 0.5)));", [("A", (macro1, "RGB")), ("B", (macro2, "RGB"))],
               -1850, 780, unreal.CustomMaterialOutputType.CMOT_FLOAT3)

# a shore (beach sand, wet at the waterline) only where there is a sea at z = 0: 0 on dry worlds, whose low ground is dry
shore = scalar(m, "Shore", 1.0, -2000, 1050)
# the blend: rock on the steep, sand at the waterline, snow up high, meadow in patches, grass elsewhere
weights = custom(m, """
float z = P.z;
float up = N.z;
float rock = smoothstep(0.83, 0.66, up + (Mc.g - 0.5) * 0.08);
float sand = (1.0 - smoothstep(1.2, 3.5, z + (Mc.r - 0.5) * 2.0)) * smoothstep(0.7, 0.85, up) * Shore;
float snow = smoothstep(SnowLine, SnowLine + 260.0, z + (Mc.g - 0.5) * 380.0) * smoothstep(0.55, 0.75, up);
float meadow = smoothstep(0.5, 0.72, Mc.r * 0.7 + Mc.b * 0.3) * 0.8 * (1.0 - smoothstep(600.0, 1200.0, z));
float r = 1.0 - rock;
snow *= r; sand *= r * (1.0 - snow); meadow *= r * (1.0 - snow) * (1.0 - sand);
return float4(rock, sand, snow, meadow);
""", [("P", (loc_m, "")), ("N", (nrm, "")), ("Mc", (macro, "")), ("SnowLine", (scalar(m, "SnowLine", 1450.0, -2000, 950), "")),
      ("Shore", (shore, ""))], -1700, 500)

# texture coordinates (metres -> tiles): top-down for every layer, two side projections for the rock
def plane_uv(axes, scale, x, y):
    msk = E(m, unreal.MaterialExpressionComponentMask, x, y, r="x" in axes, g="y" in axes, b="z" in axes)
    link(loc_m, "", msk, "")
    return binop(m, M, msk, "", scalar(m, f"Scale{axes}{int(scale * 100)}", scale, x - 150, y + 60, "Tiling"), "", x + 150, y)


uv = {L: plane_uv("xy", s, -1900, 1300 + i * 160) for i, (L, s) in enumerate((("Rock", 1 / 6.0), ("Grass", 1 / 3.0), ("Meadow", 1 / 4.0), ("Sand", 1 / 4.0), ("Snow", 1 / 5.0)))}
uv_xz = plane_uv("xz", 1 / 6.0, -1900, 2200)
uv_yz = plane_uv("yz", 1 / 6.5, -1900, 2360)
S = {}
for i, L in enumerate(LAYERS):
    S[L] = {k: sample(m, f"{L}{k}", tex(f"T_{L}_{k}"), {"BC": ST.SAMPLERTYPE_COLOR, "N": ST.SAMPLERTYPE_NORMAL, "ORM": ST.SAMPLERTYPE_MASKS}[k],
                      uv[L], -1400, 1100 + i * 420 + j * 130) for j, k in enumerate(("BC", "N", "ORM"))}
rock_xz = sample(m, "RockBC_XZ", tex("T_Rock_BC"), ST.SAMPLERTYPE_COLOR, uv_xz, -1400, 3300)
rock_yz = sample(m, "RockBC_YZ", tex("T_Rock_BC"), ST.SAMPLERTYPE_COLOR, uv_yz, -1400, 3430)

# the colour: rock blended over three planes by the normal; the layers by the weights; macro tone on top
shade = custom(m, """
float3 an = pow(abs(N), 4.0);
an /= (an.x + an.y + an.z + 1e-4);
float3 rock = (RockXY * an.z + RockXZ * an.y + RockYZ * an.x) * RockTint;
// sedimentary strata (desert walls): bands every ~9 m and ~23 m, wavering with the macro noise
float band = sin(P.z * 0.698 + Mc.g * 6.0) * 0.5 + 0.5;
float band2 = sin(P.z * 0.273 + 1.7 + Mc.b * 3.0) * 0.5 + 0.5;
rock *= lerp(1.0, lerp(0.74, 1.14, band) * lerp(0.86, 1.1, band2), Strata);
float4 w = W;
float grass = saturate(1.0 - w.x - w.y - w.z - w.w);
float3 c = rock * w.x + Sand * w.y + Snow * w.z + Meadow * MeadowTint * w.w + Grass * GrassTint * grass;
float tone = lerp(0.82, 1.14, Mc.b) * lerp(0.95, 1.05, Mc.r);
// wet sand and dark shingle right at the waterline
float wet = (1.0 - smoothstep(-0.5, 1.8, P.z)) * Shore;
return c * tone * lerp(1.0, 0.55, wet);
""", [("N", (nrm, "")), ("RockXY", (S["Rock"]["BC"], "RGB")), ("RockXZ", (rock_xz, "RGB")), ("RockYZ", (rock_yz, "RGB")),
      ("Sand", (S["Sand"]["BC"], "RGB")), ("Snow", (S["Snow"]["BC"], "RGB")), ("Meadow", (S["Meadow"]["BC"], "RGB")),
      ("Grass", (S["Grass"]["BC"], "RGB")), ("W", (weights, "")), ("Mc", (macro, "")), ("P", (loc_m, "")),
      ("GrassTint", (vector(m, "GrassTint", (0.5, 0.66, 0.4, 1), -1000, 600), "RGB")),
      ("MeadowTint", (vector(m, "MeadowTint", (0.7, 0.78, 0.58, 1), -1000, 700), "RGB")),
      ("RockTint", (vector(m, "RockTint", (1, 1, 1, 1), -1000, 500), "RGB")), ("Shore", (shore, "")),
      ("Strata", (scalar(m, "Strata", 0.0, -1000, 400), ""))], -700, 900,
      unreal.CustomMaterialOutputType.CMOT_FLOAT3)
tint = binop(m, M, shade, "", vector(m, "Tint", (1, 1, 1, 1), -700, 800), "RGB", -450, 900)
mel.connect_material_property(tint, "", unreal.MaterialProperty.MP_BASE_COLOR)

surf = custom(m, """
float4 w = W;
float grass = saturate(1.0 - w.x - w.y - w.z - w.w);
float r = Rock.g * w.x + Sand.g * w.y + Snow.g * w.z + Meadow.g * w.w + Grass.g * grass;
float ao = Rock.r * w.x + Sand.r * w.y + Snow.r * w.z + Meadow.r * w.w + Grass.r * grass;
float wet = (1.0 - smoothstep(-0.5, 1.8, P.z)) * Shore;
return float4(lerp(saturate(0.4 + 0.6 * r), 0.2, wet), ao, 0, 0);
""", [("Shore", (shore, "")), ("W", (weights, "")), ("Rock", (S["Rock"]["ORM"], "RGB")), ("Sand", (S["Sand"]["ORM"], "RGB")), ("Snow", (S["Snow"]["ORM"], "RGB")),
      ("Meadow", (S["Meadow"]["ORM"], "RGB")), ("Grass", (S["Grass"]["ORM"], "RGB")), ("P", (loc_m, ""))], -700, 1500)
rough = E(m, unreal.MaterialExpressionComponentMask, -450, 1500, r=True)
link(surf, "", rough, "")
mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
ao = E(m, unreal.MaterialExpressionComponentMask, -450, 1600, g=True)
link(surf, "", ao, "")
mel.connect_material_property(ao, "", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)

normal = custom(m, """
float4 w = W;
float grass = saturate(1.0 - w.x - w.y - w.z - w.w);
float3 n = Rock * w.x + Sand * w.y + Snow * w.z + Meadow * w.w + Grass * grass;
n.xy *= Strength * saturate(Up.z * 2.0 - 0.6);   // the maps are laid from above: they smear on the walls, so fade there
return normalize(n);
""", [("Up", (nrm, "")), ("W", (weights, "")), ("Rock", (S["Rock"]["N"], "RGB")), ("Sand", (S["Sand"]["N"], "RGB")), ("Snow", (S["Snow"]["N"], "RGB")),
      ("Meadow", (S["Meadow"]["N"], "RGB")), ("Grass", (S["Grass"]["N"], "RGB")), ("Strength", (scalar(m, "NormalStrength", 0.9, -900, 2000), ""))],
      -700, 1900, unreal.CustomMaterialOutputType.CMOT_FLOAT3)
mel.connect_material_property(normal, "", unreal.MaterialProperty.MP_NORMAL)
m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append(f"M_ASTRA_Terrain ({mel.get_num_material_expressions(m)} nodes)")

# =========================================================================================== the sea
o = fresh("M_NR_Ocean")
wp2 = E(o, unreal.MaterialExpressionWorldPosition, -1600, 0)
xy = E(o, unreal.MaterialExpressionComponentMask, -1450, 0, r=True, g=True)
link(binop(o, M, wp2, "", const(o, 0.01, -1600, 100), "", -1500, 0), "", xy, "")      # metres
t = E(o, unreal.MaterialExpressionTime, -1600, 300)


def wave_uv(scale, vx, vy, x, y):
    a = binop(o, M, xy, "", const(o, scale, x - 150, y + 60), "", x, y)
    v = E(o, unreal.MaterialExpressionConstant2Vector, x - 150, y + 140, r=vx * scale, g=vy * scale)
    drift = binop(o, M, t, "", v, "", x, y + 120)
    return binop(o, ADD, a, "", drift, "", x + 150, y + 60)


n1 = E(o, unreal.MaterialExpressionTextureSampleParameter2D, -900, 0, parameter_name="WavesA", texture=tex("T_Water_N"),
       sampler_type=ST.SAMPLERTYPE_NORMAL, group="Sea")
link(wave_uv(1 / 38.0, 1.1, 0.35, -1300, 0), "", n1, "UVs")
n2 = E(o, unreal.MaterialExpressionTextureSampleParameter2D, -900, 300, parameter_name="WavesB", texture=tex("T_Water_N"),
       sampler_type=ST.SAMPLERTYPE_NORMAL, group="Sea")
link(wave_uv(1 / 9.0, -0.6, 0.9, -1300, 300), "", n2, "UVs")
dist = E(o, unreal.MaterialExpressionPixelDepth, -900, 600)
wn = custom(o, """
float3 a = A; float3 b = B;
// the small waves fade with distance (they would only shimmer); the swell stays
float far = saturate(D / 250000.0);
float3 n = float3(a.xy * Strength + b.xy * Strength * 0.6 * (1.0 - far), 1.0);
return normalize(n);
""", [("A", (n1, "RGB")), ("B", (n2, "RGB")), ("D", (dist, "")), ("Strength", (scalar(o, "WaveStrength", 3.0, -900, 750, "Sea"), ""))],
          -500, 200, unreal.CustomMaterialOutputType.CMOT_FLOAT3)
mel.connect_material_property(wn, "", unreal.MaterialProperty.MP_NORMAL)
fr = E(o, unreal.MaterialExpressionFresnel, -700, -300)
col = E(o, LERP, -400, -300)
link(vector(o, "Deep", (0.004, 0.018, 0.03, 1), -700, -500, "Sea"), "RGB", col, "A")
link(vector(o, "Shallow", (0.012, 0.05, 0.06, 1), -700, -400, "Sea"), "RGB", col, "B")
link(fr, "", col, "Alpha")
mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(scalar(o, "Roughness", 0.06, -400, -100, "Sea"), "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(scalar(o, "Specular", 0.5, -400, -20, "Sea"), "", unreal.MaterialProperty.MP_SPECULAR)
o.set_editor_property("blend_mode", unreal.BlendMode.BLEND_OPAQUE)
mel.recompile_material(o)
eal.save_loaded_asset(o, only_if_is_dirty=False)
log.append(f"M_NR_Ocean ({mel.get_num_material_expressions(o)} nodes)")


def mi(name, parent):
    p = f"{MI}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, parent)
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)
    return inst


mi("MI_NR_Terrain", m)
mi("MI_NR_Ocean", o)


def mi_params(name, parent, scalars=None, vectors=None):
    inst = mi(name, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)


# Port Aurelius: concrete, painted markings, curtain-wall glass, building panels
hard = eal.load_asset(f"{MAT}/M_ASTRA_Hard")
hull = eal.load_asset(f"{MAT}/M_ASTRA_Hull")
mi_params("MI_NR_Concrete", hard, {"RoughnessMin": 0.7, "RoughnessMax": 0.92, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.6,
                                   "MacroBrightness": 0.12, "UVScale": 3.0, "NormalStrength": 0.5}, {"Tint": (0.36, 0.35, 0.33)})
mi_params("MI_NR_Paint", hard, {"RoughnessMin": 0.5, "RoughnessMax": 0.7, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.3,
                                "NormalStrength": 0.3}, {"Tint": (0.75, 0.52, 0.04)})
mi_params("MI_NR_Glass", hard, {"RoughnessMin": 0.03, "RoughnessMax": 0.08, "MetallicFromMap": 0.0, "MetallicBias": 0.7,
                                "BaseColorMapInfluence": 0.0, "NormalStrength": 0.0, "MacroBrightness": 0.05}, {"Tint": (0.08, 0.12, 0.16)})
mi_params("MI_NR_Dark", hard, {"RoughnessMin": 0.6, "RoughnessMax": 0.8, "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.2},
          {"Tint": (0.03, 0.03, 0.035)})
mi_params("MI_NR_Facade", hull, {"PanelTone": 0.12, "PanelCavity": 0.8, "PanelRoughness": 0.1, "RoughnessMin": 0.45, "RoughnessMax": 0.7,
                                 "MetallicFromMap": 0.0, "BaseColorMapInfluence": 0.4, "UVScale": 2.0, "PanelScale": 0.6},
          {"Tint": (0.55, 0.53, 0.5)})
log.append("instances")
print(json.dumps(log))
