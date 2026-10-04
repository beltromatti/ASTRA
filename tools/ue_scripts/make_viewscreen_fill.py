"""The main viewscreen's sensor fill (AAstraViewscreen, docs/ARCHITETTURA.md §5). Idempotent: rebuilt in place.

  M_ASTRA_ViewscreenFill  a post-process material on the viewscreen's scene capture only: the sensors light the hull they
                          look at from the camera's side (the image a composite of the sensors, not a bare eye), so a ship
                          seen against the star is not a black cut-out. Before tonemapping (HDR, the capture's fixed gain
                          applies): scene + base colour * Fill * (0.35 + 0.65 * N.V), on geometry only (the sky sphere, far
                          away, keeps its stars). Fill is set by the game from the star's light (astra.viewscreen.fill).
                          Nanite ignores lighting channels, so a light seen only by the capture is not possible: this is.

tools/ue.py pyfile tools/ue_scripts/make_viewscreen_fill.py
"""
import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
DIR = "/Game/ASTRA/UI/Materials"
NAME = "M_ASTRA_ViewscreenFill"
log = []

p = f"{DIR}/{NAME}"
if eal.does_asset_exist(p):
    m = eal.load_asset(p)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)
else:
    m = tools.create_asset(NAME, DIR, unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
m.set_editor_property("blendable_location", unreal.BlendableLocation.BL_SCENE_COLOR_BEFORE_DOF)


def expr(cls, x, y, **props):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in props.items():
        e.set_editor_property(k, v)
    return e


def link(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"{a.get_name()}.{ao} -> {b.get_name()}.{bi}")


def scene(tex, y):
    return expr(unreal.MaterialExpressionSceneTexture, -900, y, scene_texture_id=tex)


sc = scene(unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0, -300)
base = scene(unreal.SceneTextureId.PPI_BASE_COLOR, -100)
nrm = scene(unreal.SceneTextureId.PPI_WORLD_NORMAL, 100)
dep = scene(unreal.SceneTextureId.PPI_SCENE_DEPTH, 300)
cam = expr(unreal.MaterialExpressionCameraVectorWS, -900, 500)
fill = expr(unreal.MaterialExpressionScalarParameter, -900, 650, parameter_name="Fill", default_value=0.0, group="Viewscreen")

code = """
float mask = Depth.r < 3.0e7 ? 1.0 : 0.0;                       // geometry, not the sky sphere (490 km out)
float lam = saturate(dot(normalize(N.rgb), V));
return Scene.rgb + Base.rgb * Fill * (0.35 + 0.65 * lam) * mask;
"""
c = expr(unreal.MaterialExpressionCustom, -400, 0)
c.set_editor_property("code", code)
c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
ins = []
for n in ("Scene", "Base", "N", "Depth", "V", "Fill"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", n)
    ins.append(ci)
c.set_editor_property("inputs", ins)
link(sc, "Color", c, "Scene")
link(base, "Color", c, "Base")
link(nrm, "Color", c, "N")
link(dep, "Color", c, "Depth")
link(cam, "", c, "V")
link(fill, "", c, "Fill")
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_asset(p, only_if_is_dirty=False)
print("VIEWSCREEN_FILL_OK", log)
