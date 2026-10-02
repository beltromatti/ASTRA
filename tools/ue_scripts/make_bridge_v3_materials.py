"""Materials of the bridge v3 (ARTE-PLANCIA). Idempotent. Run in the editor (not during PIE), after
`uv run --with pillow --with numpy python tools/art/bridge3_textures.py`:
  tools/ue.py pyfile tools/ue_scripts/make_bridge_v3_materials.py

Creates:
  textures    T_Carbon_*, T_LeatherBlack_*, T_BRG3_DeckGrain_* (packed PBR sets), T_BRG3_Lamps (palette: RGB colour, A alert
              weight; nearest, no mips), T_BRG3_Labels (label atlas, 2048 x 4096), T_BRG3_Decor (the decor atlas: static display pages,
              soft glows, the consoles' silkscreen; 2048 x 4096)
  masters     M_BRG3_Lamps        emissive lamps: colour from the palette by UV cell, alert response like M_ASTRA_Emissive
              M_BRG3_ScreenHolo   additive hover panel: ScreenTexture x Intensity, dim on its back side (BackGain)
              M_BRG3_Viewscreen   translucent image plane of the main viewscreen: ScreenTexture, Intensity, Opacity (0 = off)
  instances   in /Game/ASTRA/Materials/Instances, named exactly like the mesh slots so import_kit's assign_materials_by_slot finds
              them: MI_BRG3_Composite / Ivory / Brass / Navy / DeckPlate / DarkGlass / Leather / Lamps / LampsDim / LampsHot / Labels / Decor and one
              SCREEN_<station>_<n> per live screen (a static page until the game binds a live one)
  hover UI    /Game/ASTRA/Kit/Bridge3/HoloUI/MI_UI_<Page>: the translucent twins of the MI_UI_* instances (same object names,
              so UAstraScreensSubsystem, which binds pages by material name, drives them like the opaque ones)
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
DATA = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_bridge.json"), encoding="utf-8"))
TEX_SRC = ROOT + "/art/_cache/textures"
B3_SRC = ROOT + "/art/_cache/bridge3"
TEX_DST = "/Game/ASTRA/Materials/Textures"
MAT_DST = "/Game/ASTRA/Materials"
MI_DST = "/Game/ASTRA/Materials/Instances"
UI_TEX = "/Game/ASTRA/UI/Textures"
HOLO_UI = "/Game/ASTRA/Kit/Bridge3/HoloUI"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
ST = unreal.MaterialSamplerType
log = []


def srgb_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


# ---------------------------------------------------------------------------------------------------------------- textures
def import_files(folder, names, dst):
    tasks = []
    for n in names:
        path = os.path.join(folder, n)
        if not os.path.exists(path):
            raise RuntimeError(f"missing {path}: run uv run --with pillow --with numpy python tools/art/bridge3_textures.py")
        t = unreal.AssetImportTask()
        t.filename = path
        t.destination_path = dst
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)


def set_tex(name, kind):
    tex = eal.load_asset(f"{TEX_DST}/{name}")
    if kind == "N":
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
    elif kind == "BC":
        tex.set_editor_property("srgb", True)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    elif kind == "ORM":
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    elif kind == "PALETTE":       # 8 x 8 cells of 8 x 8 px: exact colours, exact alpha, no blending between cells
        tex.set_editor_property("srgb", True)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_EDITOR_ICON)
        tex.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
        tex.set_editor_property("filter", unreal.TextureFilter.TF_NEAREST)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    elif kind == "ATLAS":
        tex.set_editor_property("srgb", True)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
        tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    eal.save_loaded_asset(tex, only_if_is_dirty=False)


def import_textures():
    sets = [f"T_{s}_{k}.png" for s in ("Carbon", "LeatherBlack", "BRG3_DeckGrain") for k in ("BC", "N", "ORM")]
    import_files(TEX_SRC, sets, TEX_DST)
    for fn in sets:
        name = fn[:-4]
        set_tex(name, name.rsplit("_", 1)[1])
    import_files(B3_SRC, ["T_BRG3_Lamps.png", "T_BRG3_Labels.png", "T_BRG3_Decor.png"], TEX_DST)
    set_tex("T_BRG3_Lamps", "PALETTE")
    set_tex("T_BRG3_Labels", "ATLAS")
    set_tex("T_BRG3_Decor", "ATLAS")
    log.append("textures imported")


def tex(name, folder=TEX_DST):
    return eal.load_asset(f"{folder}/{name}")


# ------------------------------------------------------------------------------------------------------------ graph helpers
class Graph:
    """A material being rebuilt in place: E creates an expression, L links, S/V parameters, op a binary operation."""

    def __init__(self, name):
        p = f"{MAT_DST}/{name}"
        if eal.does_asset_exist(p):
            self.m = eal.load_asset(p)
            mel.delete_all_material_expressions(self.m)
        else:
            self.m = tools.create_asset(name, MAT_DST, unreal.Material, unreal.MaterialFactoryNew())
        self.name = name

    def E(self, cls, x, y, **p):
        e = mel.create_material_expression(self.m, cls, x, y)
        for k, v in p.items():
            e.set_editor_property(k, v)
        return e

    def L(self, a, ao, b, bi):
        if not mel.connect_material_expressions(a, ao, b, bi):
            raise RuntimeError(f"{self.name}: link {a.get_name()}.{ao} -> {b.get_name()}.{bi}")

    def S(self, n, v, x, y, g="ASTRA"):
        return self.E(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=n, default_value=v, group=g)

    def V(self, n, rgba, x, y, g="ASTRA"):
        return self.E(unreal.MaterialExpressionVectorParameter, x, y, parameter_name=n, default_value=unreal.LinearColor(*rgba), group=g)

    def K(self, v, x, y):
        return self.E(unreal.MaterialExpressionConstant, x, y, r=v)

    def op(self, cls, a, ao, b, bo, x, y):
        e = self.E(cls, x, y)
        self.L(a, ao, e, "A")
        self.L(b, bo, e, "B")
        return e

    def finish(self):
        mel.recompile_material(self.m)
        eal.save_loaded_asset(self.m, only_if_is_dirty=False)
        return self.m


def build_lamps():
    g = Graph("M_BRG3_Lamps")
    m = g.m
    mpc = eal.load_asset(f"{MAT_DST}/MPC_ASTRA_Ship")
    if mpc is None:
        raise RuntimeError("run make_alert_system.py first (MPC_ASTRA_Ship missing)")

    def C(n, x, y):
        return g.E(unreal.MaterialExpressionCollectionParameter, x, y, collection=mpc, parameter_name=n)

    uv = g.E(unreal.MaterialExpressionTextureCoordinate, -1500, 0)
    pal = g.E(unreal.MaterialExpressionTextureSampleParameter2D, -1250, 0, parameter_name="PaletteMap", texture=tex("T_BRG3_Lamps"),
              sampler_type=ST.SAMPLERTYPE_COLOR, group="Lamps")
    g.L(uv, "", pal, "UVs")
    inten = g.S("Intensity", 20.0, -1250, -200, "Light")
    acw = g.S("AlertColorWeight", 1.0, -1250, 250, "Alert")
    ldw = g.S("LightDimWeight", 0.0, -1250, 330, "Alert")
    # alert: the palette's alpha says which colours follow the alert; amber for yellow, red for red (from scalars: the
    # collection's vector parameter reads back as zero in a material)
    alertw = g.op(unreal.MaterialExpressionMultiply, pal, "A", acw, "", -1000, 200)
    mixw = g.op(unreal.MaterialExpressionMultiply, C("AlertMix", -1250, 420), "", alertw, "", -800, 260)
    amber = g.E(unreal.MaterialExpressionConstant3Vector, -1250, 500, constant=unreal.LinearColor(1.0, 0.62, 0.1, 1))
    red = g.E(unreal.MaterialExpressionConstant3Vector, -1250, 560, constant=unreal.LinearColor(1.0, 0.04, 0.02, 1))
    acol = g.E(unreal.MaterialExpressionLinearInterpolate, -1000, 520)
    g.L(amber, "", acol, "A")
    g.L(red, "", acol, "B")
    g.L(C("AlertRed", -1250, 640), "", acol, "Alpha")
    col = g.E(unreal.MaterialExpressionLinearInterpolate, -600, 100)
    g.L(pal, "RGB", col, "A")
    g.L(acol, "", col, "B")
    g.L(mixw, "", col, "Alpha")
    one = g.K(1.0, -1000, 700)
    dim = g.E(unreal.MaterialExpressionLinearInterpolate, -800, 720)
    g.L(one, "", dim, "A")
    g.L(C("LightLevel", -1250, 720), "", dim, "B")
    g.L(ldw, "", dim, "Alpha")
    # pulse in the alerts: 1 - amount * (0.5 + 0.5 sin(t * speed)), amount = max(PulseAmount, AlertPulse * alertW * 0.6)
    t = g.E(unreal.MaterialExpressionTime, -1250, 820)
    ts = g.op(unreal.MaterialExpressionMultiply, t, "", g.S("PulseSpeed", 3.0, -1250, 900, "Light"), "", -1050, 850)
    sn = g.E(unreal.MaterialExpressionSine, -900, 850, period=6.2831853)
    g.L(ts, "", sn, "")
    s01 = g.op(unreal.MaterialExpressionMultiply, sn, "", g.K(0.5, -900, 920), "", -750, 860)
    s02 = g.op(unreal.MaterialExpressionAdd, s01, "", g.K(0.5, -750, 930), "", -620, 870)
    ap = g.op(unreal.MaterialExpressionMultiply, C("AlertPulse", -1250, 980), "", alertw, "", -900, 990)
    ap6 = g.op(unreal.MaterialExpressionMultiply, ap, "", g.K(0.6, -900, 1050), "", -760, 1000)
    amt = g.op(unreal.MaterialExpressionMax, g.S("PulseAmount", 0.0, -900, 1110, "Light"), "", ap6, "", -620, 1040)
    pa = g.op(unreal.MaterialExpressionMultiply, s02, "", amt, "", -480, 940)
    pf = g.op(unreal.MaterialExpressionSubtract, one, "", pa, "", -350, 900)
    e1 = g.op(unreal.MaterialExpressionMultiply, col, "", inten, "", -400, 0)
    e2 = g.op(unreal.MaterialExpressionMultiply, e1, "", dim, "", -250, 60)
    e3 = g.op(unreal.MaterialExpressionMultiply, e2, "", pf, "", -120, 120)
    mel.connect_material_property(e3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(g.V("BaseColor", (0.02, 0.02, 0.022, 1), -400, -300, "Surface"), "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(g.S("Roughness", 0.4, -400, -220, "Surface"), "", unreal.MaterialProperty.MP_ROUGHNESS)
    g.finish()
    mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_NANITE)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    log.append("M_BRG3_Lamps")
    return m


def flip_uv(g, x=-1500, y=0):
    """The screen materials' FlipU / FlipV (same interface as M_ASTRA_Screen) on the first texture coordinate."""
    uv = g.E(unreal.MaterialExpressionTextureCoordinate, x, y)
    flip = g.E(unreal.MaterialExpressionAppendVector, x + 150, y + 150)
    g.L(g.S("FlipU", 0.0, x, y + 120, "Screen"), "", flip, "A")
    g.L(g.S("FlipV", 0.0, x, y + 200, "Screen"), "", flip, "B")
    one2 = g.E(unreal.MaterialExpressionConstant2Vector, x, y + 300, r=1.0, g=1.0)
    inv = g.E(unreal.MaterialExpressionSubtract, x + 250, y + 250)
    g.L(one2, "", inv, "A")
    g.L(uv, "", inv, "B")
    lerp = g.E(unreal.MaterialExpressionLinearInterpolate, x + 450, y + 100)
    g.L(uv, "", lerp, "A")
    g.L(inv, "", lerp, "B")
    g.L(flip, "", lerp, "Alpha")
    return lerp


def build_screen_holo():
    g = Graph("M_BRG3_ScreenHolo")
    m = g.m
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", True)
    uv = flip_uv(g)
    t = g.E(unreal.MaterialExpressionTextureSampleParameter2D, -700, 100, parameter_name="ScreenTexture",
            texture=tex("T_UI_Helm_A", UI_TEX), sampler_type=ST.SAMPLERTYPE_COLOR, group="Screen")
    g.L(uv, "", t, "UVs")
    inten = g.S("Intensity", 10.0, -700, 350, "Screen")
    e1 = g.op(unreal.MaterialExpressionMultiply, t, "RGB", inten, "", -400, 100)
    out = e1
    try:   # seen from behind the panel is much dimmer (the text would read mirrored and bright)
        sign = g.E(unreal.MaterialExpressionTwoSidedSign, -700, 500)
        facing = g.E(unreal.MaterialExpressionSaturate, -520, 500)
        g.L(sign, "", facing, "")
        gain = g.E(unreal.MaterialExpressionLinearInterpolate, -340, 460)
        g.L(g.S("BackGain", 0.15, -700, 580, "Screen"), "", gain, "A")
        g.L(g.K(1.0, -520, 620), "", gain, "B")
        g.L(facing, "", gain, "Alpha")
        out = g.op(unreal.MaterialExpressionMultiply, e1, "", gain, "", -200, 200)
    except Exception as ex:      # the material still works without the back-side dimming
        log.append(f"M_BRG3_ScreenHolo: no back dimming ({ex})")
    mel.connect_material_property(out, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    g.finish()
    log.append("M_BRG3_ScreenHolo")
    return m


def build_viewscreen():
    g = Graph("M_BRG3_Viewscreen")
    m = g.m
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("two_sided", False)
    uv = flip_uv(g)
    t = g.E(unreal.MaterialExpressionTextureSampleParameter2D, -700, 100, parameter_name="ScreenTexture",
            texture=tex("T_UI_Master", UI_TEX), sampler_type=ST.SAMPLERTYPE_COLOR, group="Screen")
    g.L(uv, "", t, "UVs")
    tint = g.V("Tint", (1.0, 1.0, 1.0, 1), -700, 350, "Screen")
    inten = g.S("Intensity", 1.0, -700, 450, "Screen")
    e1 = g.op(unreal.MaterialExpressionMultiply, t, "RGB", tint, "RGB", -450, 150)
    e2 = g.op(unreal.MaterialExpressionMultiply, e1, "", inten, "", -280, 200)
    mel.connect_material_property(e2, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(g.S("Opacity", 0.0, -450, 420, "Screen"), "", unreal.MaterialProperty.MP_OPACITY)
    g.finish()
    log.append("M_BRG3_Viewscreen")
    return m


# ------------------------------------------------------------------------------------------------------------------ instances
def make_mi(folder, name, parent, scalars=None, vectors=None, textures=None, switches=None):
    path = f"{folder}/{name}"
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        if not eal.does_directory_exist(folder):
            eal.make_directory(folder)
        mi = tools.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi.get_editor_property("parent") != parent:
        mel.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(mi, k, v)
    for k, v in (switches or {}).items():
        mel.set_material_instance_static_switch_parameter_value(mi, k, v)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi


def build_instances(hard, lamps, screen, holo, viewscreen):
    def pbr(name, tset, tint, uvs, rough, metal_map, influence, normal, macro=0.05, scratch=0.05, bias=0.0):
        make_mi(MI_DST, name, hard,
                scalars={"UVScale": uvs, "RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": metal_map, "MetallicBias": bias,
                         "BaseColorMapInfluence": influence, "NormalStrength": normal, "MacroBrightness": macro, "ScratchRoughness": scratch,
                         "RoughnessVariation": 0.08},
                vectors={"Tint": tint},
                textures={"BaseColorMap": tex(f"T_{tset}_BC"), "NormalMap": tex(f"T_{tset}_N"), "ORMMap": tex(f"T_{tset}_ORM")})

    # the dark composite of the walls and the console interiors: carbon twill under a clear coat
    pbr("MI_BRG3_Composite", "Carbon", (0.05, 0.056, 0.07), 4.0, (0.22, 0.42), 0.3, 0.35, 0.5)
    # glossy ivory ceramic composite of the shells: a light grey-ivory, never beige
    pbr("MI_BRG3_Ivory", "PanelPaint", srgb_to_linear("#A9AAA8"), 1.0, (0.16, 0.30), 0.0, 0.3, 0.3, macro=0.04)
    # gunmetal deck plating with a fine anti-slip knurl
    pbr("MI_BRG3_DeckPlate", "BRG3_DeckGrain", (0.11, 0.115, 0.13), 2.5, (0.34, 0.62), 0.9, 0.85, 1.0, macro=0.10, scratch=0.10)   # gunmetal: the sun through the window washed a lighter plate out
    # opaque black glass: lenses and the work surfaces around the live screens (satin: roughness 0.3-0.38, no texture influence)
    pbr("MI_BRG3_DarkGlass", "PanelPaint", (0.003, 0.004, 0.006), 1.0, (0.30, 0.38), 0.0, 0.0, 0.0, macro=0.0, scratch=0.0)
    # the seats: black leather
    pbr("MI_BRG3_Leather", "LeatherBlack", (0.05, 0.055, 0.075), 2.0, (0.30, 0.50), 0.0, 0.9, 0.7, macro=0.06)
    # brushed brass: the warm line of the command deck (a thin accent, never a big surface): metal, a hint of the brushed grain
    pbr("MI_BRG3_Brass", "Brushed", srgb_to_linear("#B89A4E"), 1.0, (0.24, 0.42), 0.0, 0.15, 0.5, macro=0.03, scratch=0.04, bias=1.0)
    # navy paint (the ASTRA Navy livery): stripes and markings on the Falcons and the flight deck; a satin paint, not a metal
    pbr("MI_BRG3_Navy", "PanelPaint", srgb_to_linear("#1F3A6B"), 1.0, (0.28, 0.45), 0.0, 0.3, 0.3)
    pal = tex("T_BRG3_Lamps")
    make_mi(MI_DST, "MI_BRG3_Lamps", lamps, {"Intensity": 20.0, "LightDimWeight": 0.0}, textures={"PaletteMap": pal})
    make_mi(MI_DST, "MI_BRG3_LampsDim", lamps, {"Intensity": 6.0, "LightDimWeight": 0.0}, textures={"PaletteMap": pal})
    make_mi(MI_DST, "MI_BRG3_LampsHot", lamps, {"Intensity": 55.0, "LightDimWeight": 1.0}, textures={"PaletteMap": pal})
    make_mi(MI_DST, "MI_BRG3_Labels", screen, {"Intensity": 4.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": tex("T_BRG3_Labels")})
    # the decor atlas: static display pages and soft glows, dimmer than the live pages (their Intensity is 22, the hover panels' 10)
    make_mi(MI_DST, "MI_BRG3_Decor", screen, {"Intensity": 8.0, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": tex("T_BRG3_Decor")})
    log.append("shared instances")

    # one default instance per live screen: a static page until the game binds a live one; the surface decides the parent
    made = []
    for slot, info in DATA["screens"].items():
        surface = info.get("surface")
        page = info.get("page")
        if surface == "viewscreen":
            make_mi(MI_DST, slot, viewscreen, {"Intensity": 1.0, "Opacity": 0.0}, {"Tint": (1.0, 1.0, 1.0)})
            made.append(slot)
            continue
        page_tex = "Helm_Touch" if page == "Touch" else page
        t = eal.load_asset(f"{UI_TEX}/T_UI_{page_tex}")
        if t is None:
            log.append(f"{slot}: page texture T_UI_{page_tex} missing (make_ui_materials.py) - left on the default")
        if surface == "hover":
            make_mi(MI_DST, slot, holo, {"Intensity": 10.0, "BackGain": 0.15, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": t} if t else None)
        else:
            inten = 8.0 if "Touch" in str(page) else 22.0
            make_mi(MI_DST, slot, screen, {"Intensity": inten, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": t} if t else None)
        made.append(slot)
    log.append(f"{len(made)} SCREEN_* instances")

    # the translucent twins of the live pages, for the hover panels: same object names as /Game/ASTRA/UI/Materials/MI_UI_*
    pages = sorted({info["page"] for info in DATA["screens"].values() if info.get("surface") == "hover" and info.get("page") and not info.get("instance")})
    for page in pages:
        t = eal.load_asset(f"{UI_TEX}/T_UI_{page}")
        make_mi(HOLO_UI, f"MI_UI_{page}", holo, {"Intensity": 10.0, "BackGain": 0.15, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": t} if t else None)
    log.append(f"hover UI twins: {pages}")


import_textures()
hard = eal.load_asset(f"{MAT_DST}/M_ASTRA_Hard")
screen = eal.load_asset(f"{MAT_DST}/M_ASTRA_Screen")
if hard is None or screen is None:
    raise RuntimeError("run make_materials.py and make_ui_materials.py first (M_ASTRA_Hard / M_ASTRA_Screen missing)")
lamps = build_lamps()
holo = build_screen_holo()
viewscreen = build_viewscreen()
build_instances(hard, lamps, screen, holo, viewscreen)
# materials assigned at run time to Nanite meshes need the Nanite usage flag (the live screens on the opaque consoles)
for base in ("M_ASTRA_Screen", "M_ASTRA_Hard", "M_ASTRA_Emissive"):
    mm = eal.load_asset(f"{MAT_DST}/{base}")
    if not mm.get_editor_property("used_with_nanite"):
        mel.set_material_usage(mm, unreal.MaterialUsage.MATUSAGE_NANITE)
        eal.save_loaded_asset(mm, only_if_is_dirty=False)
        log.append(f"{base}: Nanite usage")
print(json.dumps(log, indent=1))
