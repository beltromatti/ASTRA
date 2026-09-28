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
# not "IsSky": sky-pass meshes did not render in the game view (only in the editor). A plain unlit sphere that the
# material recentres on the camera (world position offset) is robust everywhere; the look only depends on the view
# direction, so the sphere's size and position do not matter.
m.set_editor_property("is_sky", False)
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
axis_vecs = []
for i, (nm, v) in enumerate((("SkyAxisX", (1, 0, 0, 0)), ("SkyAxisY", (0, 1, 0, 0)), ("SkyAxisZ", (0, 0, 1, 0)))):
    p = vparam(nm, v, -1600, 200 + 150 * i)
    d = E(unreal.MaterialExpressionDotProduct, -1350, 200 + 150 * i)
    link(neg, "", d, "A")
    mk = mask3(p, -1450, 200 + 150 * i)
    link(mk, "", d, "B")
    axes.append(d)
    axis_vecs.append(mk)
ap1 = E(unreal.MaterialExpressionAppendVector, -1150, 250)
link(axes[0], "", ap1, "A")
link(axes[1], "", ap1, "B")
ap2 = E(unreal.MaterialExpressionAppendVector, -1000, 300)
link(ap1, "", ap2, "A")
link(axes[2], "", ap2, "B")

samp = E(unreal.MaterialExpressionTextureSampleParameterCube, -800, 250, parameter_name="SkyCubemap", texture=cube, group="Sky")
link(ap2, "", samp, "UVs")
bright = sparam("SkyBrightness", 3.0, -800, 480)
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

# --- the planet (New Ravenna): an analytic sphere in the sky frame, drawn over the stars and the nebula
sun_sky = []
for i, mk in enumerate(axis_vecs):
    dd = E(unreal.MaterialExpressionDotProduct, -300, 1700 + 80 * i)
    link(sun_n, "", dd, "A")
    link(mk, "", dd, "B")
    sun_sky.append(dd)
s1 = E(unreal.MaterialExpressionAppendVector, -150, 1720)
link(sun_sky[0], "", s1, "A")
link(sun_sky[1], "", s1, "B")
s2 = E(unreal.MaterialExpressionAppendVector, -50, 1760)
link(s1, "", s2, "A")
link(sun_sky[2], "", s2, "B")
planet = E(unreal.MaterialExpressionCustom, 60, 500)
planet.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
planet.set_editor_property("code", """
struct PlanetFn
{
    float h(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
    float n(float3 p)
    {
        float3 i = floor(p), f = frac(p);
        f = f * f * (3.0 - 2.0 * f);
        return lerp(lerp(lerp(h(i), h(i + float3(1,0,0)), f.x), lerp(h(i + float3(0,1,0)), h(i + float3(1,1,0)), f.x), f.y),
                    lerp(lerp(h(i + float3(0,0,1)), h(i + float3(1,0,1)), f.x), lerp(h(i + float3(0,1,1)), h(i + float3(1,1,1)), f.x), f.y), f.z);
    }
    float fbm(float3 p)
    {
        float v = 0.0, a = 0.5;
        for (int o = 0; o < 6; o++) { v += a * n(p); p = p * 2.03 + float3(1.7, 9.2, 3.1); a *= 0.5; }
        return v;
    }
};
PlanetFn F;
float3 d = normalize(D);
float3 c = normalize(P.xyz);
float3 s = normalize(S);
float sr = sin(R);
float b = dot(d, c);
float disc = b * b - (1.0 - sr * sr);
float3 atm = float3(0.32, 0.58, 1.0);
if (disc < 0.0)
{
    // thin blue halo of the atmosphere just outside the limb, brighter towards the sun
    float ang = acos(clamp(b, -1.0, 1.0));
    float halo = pow(saturate(1.0 - (ang - R) / (R * 0.05)), 4.0);
    float3 limbN = normalize(d - c * b);
    return Base + atm * halo * saturate(dot(limbN, s) * 0.9 + 0.25) * Bright * 0.6;
}
float t = b - sqrt(disc);
float3 nrm = normalize(d * t - c);
// planet-fixed frame: a slow spin about the planet's axis (sky Z)
float sp = T * 0.003;
float3 q = float3(nrm.x * cos(sp) - nrm.y * sin(sp), nrm.x * sin(sp) + nrm.y * cos(sp), nrm.z);
float cont = F.fbm(q * 2.2 + 11.0);
float land = smoothstep(0.515, 0.535, cont);
float coast = smoothstep(0.47, 0.515, cont) * (1.0 - land);
float biome = F.fbm(q * 4.0 + 3.0);
float lat = abs(q.z);
float ice = smoothstep(0.80, 0.86, lat + (F.n(q * 9.0) - 0.5) * 0.08);
float3 ocean = lerp(float3(0.006, 0.03, 0.09), float3(0.02, 0.11, 0.17), coast);
float3 ground = lerp(float3(0.06, 0.13, 0.05), float3(0.26, 0.22, 0.13), smoothstep(0.45, 0.62, biome));
ground = lerp(ground, float3(0.38, 0.33, 0.22), smoothstep(0.62, 0.72, biome) * (1.0 - lat));
float3 albedo = lerp(ocean, ground, land);
albedo = lerp(albedo, float3(0.8, 0.84, 0.88), ice);
float cl = F.fbm(q * 4.6 + float3(T * 0.0012, 0.0, T * 0.0005) + F.n(q * 11.0) * 0.35);
float clouds = smoothstep(0.54, 0.74, cl) * 0.95;
albedo = lerp(albedo, float3(0.92, 0.93, 0.95), clouds);
float ndl = dot(nrm, s);
float day = smoothstep(-0.06, 0.25, ndl) * saturate(ndl + 0.15);
float3 lit = albedo * day * Bright;
// sun glint on open water
float3 rr = reflect(-s, nrm);
lit += pow(saturate(dot(rr, -d)), 80.0) * (1.0 - land) * (1.0 - clouds) * (1.0 - ice) * Bright * 0.6;
// city lights on the night side
float night = smoothstep(0.02, -0.12, ndl);
float city = step(0.965, F.n(q * 140.0)) * step(0.5, F.n(q * 18.0 + 5.0)) * land * (1.0 - ice) * (1.0 - clouds * 0.8);
lit += float3(1.0, 0.68, 0.32) * city * night * Bright * 0.35;
// atmosphere: rim haze, lit side stronger
float rim = pow(1.0 - saturate(dot(nrm, -d)), 3.0);
lit += atm * rim * (saturate(ndl + 0.3)) * Bright * 0.55;
return lit;
""")
ins = []
for nm in ("D", "S", "P", "R", "T", "Base", "Bright"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", nm)
    ins.append(ci)
planet.set_editor_property("inputs", ins)
link(ap2, "", planet, "D")
link(s2, "", planet, "S")
link(mask3(vparam("PlanetDirection", (0.75, -0.55, -0.3, 0), -300, 1950, "Planet"), -150, 1950), "", planet, "P")
link(sparam("PlanetAngularRadius", 0.28, -300, 2050, "Planet"), "", planet, "R")
link(E(unreal.MaterialExpressionTime, -300, 2130), "", planet, "T")
link(total, "", planet, "Base")
link(sparam("PlanetBrightness", 6.0, -300, 2210, "Planet"), "", planet, "Bright")
eai = E(unreal.MaterialExpressionEyeAdaptationInverse, 300, 400)
link(planet, "", eai, "LightValueInput")
link(sparam("ExposureCompensation", 0.85, -100, 600), "", eai, "AlphaInput")
mel.connect_material_property(eai, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
# world position offset: move every vertex by (camera - object position) so the sphere is always centred on the eye
campos = E(unreal.MaterialExpressionCameraPositionWS, -600, 1500)
objpos = E(unreal.MaterialExpressionObjectPositionWS, -600, 1600)
wpo = E(unreal.MaterialExpressionSubtract, -400, 1550)
link(campos, "", wpo, "A")
link(objpos, "", wpo, "B")
mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
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
