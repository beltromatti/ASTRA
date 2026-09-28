"""Space backdrop: imports the NASA starmap as a TextureCube and builds M_ASTRA_SpaceSky (IsSky, unlit)."""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DST = "/Game/ASTRA/Space"
SRC = "/Users/beltromatti/Desktop/ASTRA/art/_cache/sky/T_Starmap_NASA_8k.hdr"
log = []

if not eal.does_asset_exist(f"{DST}/T_Starmap_NASA_8k"):
    t = unreal.AssetImportTask()
    t.filename = SRC
    t.destination_path = DST
    t.automated = True
    t.replace_existing = True
    tools.import_asset_tasks([t])
cube = eal.load_asset(f"{DST}/T_Starmap_NASA_8k")
log.append(f"starmap class: {cube.get_class().get_name()}")
if isinstance(cube, unreal.TextureCube):
    cube.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_SKYBOX)
    eal.save_loaded_asset(cube)

path = f"{DST}/M_ASTRA_SpaceSky"
if eal.does_asset_exist(path):
    eal.delete_asset(path)
m = tools.create_asset("M_ASTRA_SpaceSky", DST, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
m.set_editor_property("is_sky", True)
m.set_editor_property("two_sided", True)

def E(cls, x, y, **p):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in p.items():
        e.set_editor_property(k, v)
    return e

# direction from the camera to the pixel, in world space, rotated by the sky yaw/pitch (sim orientation later)
cam = E(unreal.MaterialExpressionCameraVectorWS, -1200, 0)
neg = E(unreal.MaterialExpressionMultiply, -1000, 0)
mel.connect_material_expressions(cam, "", neg, "A")
c = E(unreal.MaterialExpressionConstant, -1200, 100, r=-1.0)
mel.connect_material_expressions(c, "", neg, "B")
# galactic-plane tilt so the Milky Way crosses the sky diagonally (art direction), via a fixed rotation
rot = E(unreal.MaterialExpressionRotateAboutAxis, -800, 0)
axis = E(unreal.MaterialExpressionConstant3Vector, -1000, 200, constant=unreal.LinearColor(0.577, 0.577, 0.577, 1))
ang = E(unreal.MaterialExpressionScalarParameter, -1000, 300, parameter_name="SkyRotation", default_value=0.18, group="Sky")
zero = E(unreal.MaterialExpressionConstant3Vector, -1000, 400, constant=unreal.LinearColor(0, 0, 0, 1))
mel.connect_material_expressions(axis, "", rot, "NormalizedRotationAxis")
mel.connect_material_expressions(ang, "", rot, "RotationAngle")
mel.connect_material_expressions(zero, "", rot, "PivotPoint")
mel.connect_material_expressions(neg, "", rot, "Position")
dirv = E(unreal.MaterialExpressionAdd, -600, 0)
mel.connect_material_expressions(rot, "", dirv, "A")
mel.connect_material_expressions(neg, "", dirv, "B")
samp = E(unreal.MaterialExpressionTextureSampleParameterCube, -400, 0, parameter_name="Starmap", texture=cube, group="Sky")
mel.connect_material_expressions(dirv, "", samp, "UVs")
bright = E(unreal.MaterialExpressionScalarParameter, -400, 250, parameter_name="StarBrightness", default_value=0.25, group="Sky")
mul = E(unreal.MaterialExpressionMultiply, -150, 50)
mel.connect_material_expressions(samp, "RGB", mul, "A")
mel.connect_material_expressions(bright, "", mul, "B")
# exposure compensation: the sky keeps (most of) its perceived brightness whatever the eye adaptation,
# so stars and nebulae stay visible from lit interiors and in sunlit exterior views alike (art direction, not physics)
eai = E(unreal.MaterialExpressionEyeAdaptationInverse, 50, 50)
comp = E(unreal.MaterialExpressionScalarParameter, -150, 250, parameter_name="ExposureCompensation", default_value=0.85, group="Sky")
mel.connect_material_expressions(mul, "", eai, "LightValueInput")
mel.connect_material_expressions(comp, "", eai, "AlphaInput")
mel.connect_material_property(eai, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_loaded_asset(m)
log.append("M_ASTRA_SpaceSky ok")
print(json.dumps(log))
