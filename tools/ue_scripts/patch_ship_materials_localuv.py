"""Ship materials v3, in place: the wear map sampled as Linear Color (it is BC7: as Masks the masters never compiled), and it and the macro variation sampled from a box projection in the ship's own space
instead of UV0 (which is anchored per triangle on an 8 m lattice: whole-unit jumps between triangles, invisible to the detail
textures that tile at integer scales, but a fractional scale of it — WearScale 0.5, MacroScale 0.6, the cut faces' 0.9 — jumps
at every diagonal: the hulls came out checkered in the game).

A patch, not a rebuild: make_ship_materials_v3.py rebuilds its masters by deleting their expressions, which asserts once the
materials are loaded and in use (the level's ships); here the Multiply nodes fed by UV0 and a WearScale / MacroScale parameter
get the local projection on their A input, and nothing is deleted. Idempotent (a node already fed by the projection is left).
  tools/ue.py pyfile tools/ue_scripts/patch_ship_materials_localuv.py
"""
import json

import unreal

MAT = "/Game/ASTRA/Materials"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
log = []

CODE = """
float3 n = abs(N);
float2 q = (n.x >= n.y && n.x >= n.z) ? P.yz : ((n.y >= n.z) ? P.xz : P.xy);
return q / 800.0;
"""


def local_box_uv(m, x, y):
    lp = mel.create_material_expression(m, unreal.MaterialExpressionLocalPosition, x - 400, y)
    nw = mel.create_material_expression(m, unreal.MaterialExpressionVertexNormalWS, x - 600, y + 100)
    nl = mel.create_material_expression(m, unreal.MaterialExpressionTransform, x - 400, y + 100)
    nl.set_editor_property("transform_source_type", unreal.MaterialVectorCoordTransformSource.TRANSFORMSOURCE_WORLD)
    nl.set_editor_property("transform_type", unreal.MaterialVectorCoordTransform.TRANSFORM_LOCAL)
    mel.connect_material_expressions(nw, "", nl, "")
    c = mel.create_material_expression(m, unreal.MaterialExpressionCustom, x - 200, y)
    c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT2)
    c.set_editor_property("code", CODE)
    c.set_editor_property("description", "LocalBoxUV")
    ins = []
    for nm in ("P", "N"):
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", nm)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    mel.connect_material_expressions(lp, "", c, "P")
    mel.connect_material_expressions(nl, "", c, "N")
    return c


def param_name(e):
    try:
        return str(e.get_editor_property("parameter_name"))
    except Exception:
        return ""


def fix_samplers(m, name):
    """T_ShipWear_M is BC7 without sRGB: its sampler must be Linear Color. As Masks the material never compiled and the ships
    drew with the engine's default material (grey grid, tan under Aurelia's orange sun)."""
    n = 0
    for e in mel.get_material_expressions(m):
        if isinstance(e, unreal.MaterialExpressionTextureSampleParameter2D) and param_name(e) == "ShipWear" \
                and e.get_editor_property("sampler_type") != unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR:
            e.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
            n += 1
    if n:
        log.append(f"{name}: ShipWear sampler -> Linear Color")
    return n


def patch(name, params):
    m = eal.load_asset(f"{MAT}/{name}")
    if not m:
        log.append(f"{name}: missing")
        return
    fixed = fix_samplers(m, name)
    targets = []
    for e in mel.get_material_expressions(m):
        if not isinstance(e, unreal.MaterialExpressionMultiply):
            continue
        ins = mel.get_inputs_for_material_expression(m, e)
        if len(ins) < 2 or not ins[1] or param_name(ins[1]) not in params:
            continue
        a = ins[0]
        if isinstance(a, unreal.MaterialExpressionCustom) and str(a.get_editor_property("description")) == "LocalBoxUV":
            log.append(f"{name}: {param_name(ins[1])} already local")
            continue
        if isinstance(a, unreal.MaterialExpressionTextureCoordinate) and a.get_editor_property("coordinate_index") == 0:
            targets.append((e, param_name(ins[1])))
    if not targets:
        log.append(f"{name}: projection already local")
        if fixed:
            mel.recompile_material(m)
            eal.save_loaded_asset(m, only_if_is_dirty=False)
        return
    x = min(t[0].get_editor_property("material_expression_editor_x") for t in targets) - 600
    y = max(t[0].get_editor_property("material_expression_editor_y") for t in targets) + 700
    uv = local_box_uv(m, x, y)
    for e, pn in targets:
        mel.connect_material_expressions(uv, "", e, "A")
        log.append(f"{name}: {pn} from the local projection")
    mel.recompile_material(m)
    eal.save_loaded_asset(m, only_if_is_dirty=False)


patch("M_ASTRA_HullV3", ("WearScale", "MacroScale"))
patch("M_ASTRA_ShipCut", ("WearScale",))
print(json.dumps(log, indent=1))
