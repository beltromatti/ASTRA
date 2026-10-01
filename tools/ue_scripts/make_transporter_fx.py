"""The materials of the transporter's visual effects (Source/ASTRA/AstraTransportFx.cpp; what they are and why: docs/TELETRASPORTO.md §7).

Run in the editor, with no game or PIE running (the masters are rebuilt in place):
  tools/ue.py pyfile tools/ue_scripts/make_transporter_fx.py

Makes, in /Game/ASTRA/Materials (all unlit and additive: they draw light, never a surface):
  M_XPORT_Sparkle   instanced   a point of light that twinkles and fades (a small engine sphere read as a soft disc): the glitter of a beam, the glow over the dais
  M_XPORT_Column    instanced   the shimmering cylinder round a subject, with a bright front that sweeps it from the feet to the head
  M_XPORT_Ring      instanced   a pad's ring on the floor: its colour and its motion say what the lock is doing
  M_XPORT_Ghost     skeletal    the figure of light that stands in for a body while it is carried: the body's own mesh, eaten from the feet up (or formed from the feet up);
                                parameters per body (FeetZ, Height, Prog, Dir, Gain, Col) set by the game
The per-instance custom data the three instanced materials read is in AstraTransportFx.h (AstraXportFx::Stride): 0-2 colour, 3 intensity, 4 progress or age, 5 direction or
mode, 6 fade, 7 seed. The shaders are in tools/ue_scripts/transporter_fx_hlsl.py (compiled by tools/art/transporter_fx_check.py with the engine's DXC). The brightness of
all of it is the console variable astra.xport.gain: an interior exposure that wants more or less light does not need new materials.
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
import transporter_fx_hlsl as H  # noqa: E402
importlib.reload(H)

MAT = "/Game/ASTRA/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
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


def scalar(mat, name, value, x, y, group="Transporter"):
    return E(mat, unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=value, group=group)


def vector(mat, name, rgba, x, y, group="Transporter"):
    return E(mat, unreal.MaterialExpressionVectorParameter, x, y, parameter_name=name, default_value=unreal.LinearColor(*rgba), group=group)


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


def fresh(name, instanced=True, skeletal=False):
    """The material, emptied (or made): unlit, additive, for instanced static meshes or a skeletal one."""
    path = f"{MAT}/{name}"
    if eal.does_asset_exist(path):
        m = eal.load_asset(path)
        mel.delete_all_material_expressions(m)
        for e in mel.get_material_expressions(m):          # what delete_all leaves behind
            mel.delete_material_expression(m, e)
    else:
        m = tools.create_asset(name, MAT, unreal.Material, unreal.MaterialFactoryNew())
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("two_sided", False)
    if instanced:
        m.set_editor_property("used_with_instanced_static_meshes", True)
    if skeletal:
        m.set_editor_property("used_with_skeletal_mesh", True)
    return m


def finish(m):
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)
    log.append(f"{m.get_name()} ok ({mel.get_num_material_expressions(m)} nodes)")


def fresnel(mat, x, y):
    return E(mat, unreal.MaterialExpressionFresnel, x, y, exponent=1.0, base_reflect_fraction=0.0)


def local_position(mat, x, y):
    return E(mat, unreal.MaterialExpressionLocalPosition, x, y, included_offsets=unreal.PositionIncludedOffsets.EXCLUDE_OFFSETS)


# ------------------------------------------------------------------------------------------------------------------------ the materials
def make_sparkle():
    m = fresh("M_XPORT_Sparkle")
    fr = fresnel(m, -900, -200)
    col = cd3(m, 0, -900, -60)
    inten = cd(m, 3, -900, 40)
    age = cd(m, 4, -900, 120)
    seed = cd(m, 7, -900, 200)
    tm = E(m, unreal.MaterialExpressionTime, -900, 280)
    c = custom(m, H.SPARKLE, [("Fr", (fr, "")), ("Col", (col, "")), ("Inten", (inten, "")), ("Age", (age, "")), ("Seed", (seed, "")), ("Tm", (tm, ""))], -400, 0)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def make_column():
    m = fresh("M_XPORT_Column")
    fr = fresnel(m, -900, -260)
    lp = local_position(m, -900, -140)
    lz = mask(m, lp, "", -700, -140, b=True)
    col = cd3(m, 0, -900, -20)
    inten = cd(m, 3, -900, 60)
    prog = cd(m, 4, -900, 140)
    dirn = cd(m, 5, -900, 220)
    fade = cd(m, 6, -900, 300)
    seed = cd(m, 7, -900, 380)
    tm = E(m, unreal.MaterialExpressionTime, -900, 460)
    c = custom(m, H.COLUMN, [("Fr", (fr, "")), ("LZ", (lz, "")), ("Col", (col, "")), ("Inten", (inten, "")), ("Prog", (prog, "")), ("Dir", (dirn, "")), ("Fade", (fade, "")),
                             ("Seed", (seed, "")), ("Tm", (tm, ""))], -400, 80)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def make_ring():
    m = fresh("M_XPORT_Ring")
    lp = local_position(m, -900, -120)
    col = cd3(m, 0, -900, 0)
    inten = cd(m, 3, -900, 80)
    mode = cd(m, 5, -900, 160)
    seed = cd(m, 7, -900, 240)
    tm = E(m, unreal.MaterialExpressionTime, -900, 320)
    c = custom(m, H.RING, [("LP", (lp, "")), ("Col", (col, "")), ("Inten", (inten, "")), ("Mode", (mode, "")), ("Seed", (seed, "")), ("Tm", (tm, ""))], -400, 60)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


def make_ghost():
    m = fresh("M_XPORT_Ghost", instanced=False, skeletal=True)
    wp = E(m, unreal.MaterialExpressionWorldPosition, -900, -260)
    fr = fresnel(m, -900, -120)
    feet = scalar(m, "FeetZ", 0.0, -900, 0)
    height = scalar(m, "Height", 195.0, -900, 70)
    prog = scalar(m, "Prog", 0.0, -900, 140)
    dirn = scalar(m, "Dir", 1.0, -900, 210)
    gain = scalar(m, "Gain", 1.0, -900, 280)
    col = vector(m, "Col", (1.0, 0.78, 0.38, 1.0), -900, 350)
    tm = E(m, unreal.MaterialExpressionTime, -900, 430)
    c = custom(m, H.GHOST, [("WP", (wp, "")), ("Fr", (fr, "")), ("FeetZ", (feet, "")), ("Height", (height, "")), ("Prog", (prog, "")), ("Dir", (dirn, "")), ("Gain", (gain, "")),
                            ("Col", (col, "RGB")), ("Tm", (tm, ""))], -400, 60)
    mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    finish(m)


for fn in (make_sparkle, make_column, make_ring, make_ghost):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        failed.append(fn.__name__)
        log.append(f"{fn.__name__} FAILED: {exc}")
        traceback.print_exc()

print(json.dumps({"made": log, "failed": failed}, indent=1))
