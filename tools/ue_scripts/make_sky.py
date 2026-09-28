"""Space backdrop for the Aurelia system.
- imports art/_cache/sky/T_Sky_Aurelia_8k.hdr (NASA stars + the Teal Veil, art/blender/sky_aurelia.py) as a TextureCube;
- builds M_ASTRA_SpaceSky (unlit, IsSky): cubemap sampled along the view direction expressed in the sky frame
  (SkyAxisX/Y/Z = the sky's basis in world space; the ship's attitude will drive them at runtime), plus the star
  Aurelia (disk + corona) towards SunDirection (world space, pointing to the star), with partial exposure compensation;
- makes MI_ASTRA_SpaceSky_Aurelia. Run: tools/ue.py pyfile tools/ue_scripts/make_sky.py"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DST = "/Game/ASTRA/Space"
SRC = "/Users/beltromatti/Desktop/ASTRA/art/_cache/sky/T_Sky_Aurelia_8k.hdr"
log = []

if not eal.does_asset_exist(f"{DST}/T_Sky_Aurelia_8k"):
    t = unreal.AssetImportTask()
    t.filename = SRC
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    tools.import_asset_tasks([t])
cube = eal.load_asset(f"{DST}/T_Sky_Aurelia_8k")
cube.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_SKYBOX)
eal.save_loaded_asset(cube, only_if_is_dirty=False)
log.append(f"sky cubemap: {cube.get_class().get_name()}")

path = f"{DST}/M_ASTRA_SpaceSky"
if eal.does_asset_exist(path):
    m = eal.load_asset(path)                # rebuilt in place: levels keep their references
    mel.delete_all_material_expressions(m)
else:
    m = tools.create_asset("M_ASTRA_SpaceSky", DST, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
m.set_editor_property("is_sky", True)
m.set_editor_property("two_sided", True)


def E(cls, x, y, **p):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in p.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"link {a.get_name()}.{ao} -> {b.get_name()}.{bi}")


def vparam(name, rgba, x, y, group="Sky"):
    return E(unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name,
             default_value=unreal.LinearColor(*rgba), group=group)


def sparam(name, v, x, y, group="Sky"):
    return E(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v, group=group)


def mask3(src, x, y):
    c = E(unreal.MaterialExpressionComponentMask, x, y, r=True, g=True, b=True, a=False)
    link(src, "", c, "")
    return c


# view direction (world): -CameraVector
cam = E(unreal.MaterialExpressionCameraVectorWS, -1800, 0)
neg = E(unreal.MaterialExpressionMultiply, -1600, 0)
link(cam, "", neg, "A")
link(E(unreal.MaterialExpressionConstant, -1800, 100, r=-1.0), "", neg, "B")

# sky-frame direction: (dot(d, AxisX), dot(d, AxisY), dot(d, AxisZ))
axes = []
for i, (nm, v) in enumerate((("SkyAxisX", (1, 0, 0, 0)), ("SkyAxisY", (0, 1, 0, 0)), ("SkyAxisZ", (0, 0, 1, 0)))):
    p = vparam(nm, v, -1600, 200 + 150 * i)
    d = E(unreal.MaterialExpressionDotProduct, -1350, 200 + 150 * i)
    link(neg, "", d, "A")
    link(mask3(p, -1450, 200 + 150 * i), "", d, "B")
    axes.append(d)
ap1 = E(unreal.MaterialExpressionAppendVector, -1150, 250)
link(axes[0], "", ap1, "A")
link(axes[1], "", ap1, "B")
ap2 = E(unreal.MaterialExpressionAppendVector, -1000, 300)
link(ap1, "", ap2, "A")
link(axes[2], "", ap2, "B")

samp = E(unreal.MaterialExpressionTextureSampleParameterCube, -800, 250, parameter_name="SkyCubemap", texture=cube, group="Sky")
link(ap2, "", samp, "UVs")
bright = sparam("SkyBrightness", 0.25, -800, 480)
sky = E(unreal.MaterialExpressionMultiply, -550, 300)
link(samp, "RGB", sky, "A")
link(bright, "", sky, "B")

# the star: disk + corona around SunDirection (world)
sund = vparam("SunDirection", (-0.55, 0.35, 0.25, 0), -1600, 700, "Star")
sun_n = E(unreal.MaterialExpressionNormalize, -1400, 700)
link(mask3(sund, -1500, 700), "", sun_n, "")
cosang = E(unreal.MaterialExpressionDotProduct, -1200, 650)
link(neg, "", cosang, "A")
link(sun_n, "", cosang, "B")
sat = E(unreal.MaterialExpressionSaturate, -1050, 650)
link(cosang, "", sat, "")
# disk: smoothstep between cos(r*1.25) and cos(r) using the angular radius parameter (radians)
rad = sparam("StarAngularRadius", 0.0075, -1200, 800, "Star")
cos_r = E(unreal.MaterialExpressionCosine, -1050, 800, period=6.2831853)
link(rad, "", cos_r, "")
rad2 = E(unreal.MaterialExpressionMultiply, -1050, 900)
link(rad, "", rad2, "A")
link(E(unreal.MaterialExpressionConstant, -1200, 950, r=1.35), "", rad2, "B")
cos_r2 = E(unreal.MaterialExpressionCosine, -900, 900, period=6.2831853)
link(rad2, "", cos_r2, "")
ss = E(unreal.MaterialExpressionSmoothStep, -700, 750)
link(cos_r2, "", ss, "Min")
link(cos_r, "", ss, "Max")
link(sat, "", ss, "Value")
disk_i = sparam("StarDiskIntensity", 4000.0, -700, 900, "Star")
disk = E(unreal.MaterialExpressionMultiply, -500, 780)
link(ss, "", disk, "A")
link(disk_i, "", disk, "B")
# corona: two lobes pow(cos, 900) and pow(cos, 40)
def lobe(k, gain, y):
    pw = E(unreal.MaterialExpressionPower, -850, y)
    link(sat, "", pw, "Base")
    link(E(unreal.MaterialExpressionConstant, -1000, y + 60, r=k), "", pw, "Exp")
    g = E(unreal.MaterialExpressionMultiply, -650, y)
    link(pw, "", g, "A")
    link(sparam(f"StarCorona{int(k)}", gain, -850, y + 90, "Star"), "", g, "B")
    return g
c1 = lobe(900.0, 20.0, 1050)
c2 = lobe(40.0, 0.35, 1250)
cor = E(unreal.MaterialExpressionAdd, -450, 1100)
link(c1, "", cor, "A")
link(c2, "", cor, "B")
star_s = E(unreal.MaterialExpressionAdd, -330, 900)
link(disk, "", star_s, "A")
link(cor, "", star_s, "B")
star_col = vparam("StarColor", (1.0, 0.6, 0.3, 1), -450, 1350, "Star")
star = E(unreal.MaterialExpressionMultiply, -200, 950)
link(star_s, "", star, "A")
link(star_col, "RGB", star, "B")

total = E(unreal.MaterialExpressionAdd, -100, 400)
link(sky, "", total, "A")
link(star, "", total, "B")
eai = E(unreal.MaterialExpressionEyeAdaptationInverse, 100, 400)
link(total, "", eai, "LightValueInput")
link(sparam("ExposureCompensation", 0.85, -100, 600), "", eai, "AlphaInput")
mel.connect_material_property(eai, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append("M_ASTRA_SpaceSky ok")

mi_path = f"{DST}/MI_ASTRA_SpaceSky_Aurelia"
if eal.does_asset_exist(mi_path):
    mi = eal.load_asset(mi_path)
else:
    mi = tools.create_asset("MI_ASTRA_SpaceSky_Aurelia", DST, unreal.MaterialInstanceConstant,
                            unreal.MaterialInstanceConstantFactoryNew())
mel.set_material_instance_parent(mi, m)
mel.update_material_instance(mi)
eal.save_loaded_asset(mi, only_if_is_dirty=False)
log.append("MI_ASTRA_SpaceSky_Aurelia ok")
print(json.dumps(log))
