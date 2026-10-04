"""Ship alert look & sound: MPC_ASTRA_Ship (driven by UAstraShipSubsystem), M_ASTRA_Emissive rebuilt in place with
alert response (AlertColorWeight: strips turn to the alert colour and pulse; LightDimWeight: lights dim), alarm sounds."""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
MAT = "/Game/ASTRA/Materials"
log = []

# --- material parameter collection
mpc_path = f"{MAT}/MPC_ASTRA_Ship"
if eal.does_asset_exist(mpc_path):
    mpc = eal.load_asset(mpc_path)
else:
    mpc = tools.create_asset("MPC_ASTRA_Ship", MAT, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
scalars = mpc.get_editor_property("scalar_parameters")
have = {str(scalars[i].get_editor_property("parameter_name")): i for i in range(len(scalars))}
for name, v in (("AlertMix", 0.0), ("AlertPulse", 0.0), ("LightLevel", 1.0), ("AlertRed", 1.0)):
    if name in have:
        p = scalars[have[name]]
        p.set_editor_property("default_value", v)
        scalars[have[name]] = p
    else:
        p = unreal.CollectionScalarParameter()
        p.set_editor_property("parameter_name", name)
        p.set_editor_property("default_value", v)
        scalars.append(p)
mpc.set_editor_property("scalar_parameters", scalars)
vecs = mpc.get_editor_property("vector_parameters")
if not any(str(v.get_editor_property("parameter_name")) == "AlertColor" for v in vecs):
    vec = unreal.CollectionVectorParameter()
    vec.set_editor_property("parameter_name", "AlertColor")
    vec.set_editor_property("default_value", unreal.LinearColor(1.0, 0.04, 0.02, 1.0))
    vecs.append(vec)
    mpc.set_editor_property("vector_parameters", vecs)
eal.save_loaded_asset(mpc, only_if_is_dirty=False)
log.append("MPC ok")

# --- emissive master with alert response
m = eal.load_asset(f"{MAT}/M_ASTRA_Emissive")
for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list. NB: the materials of meshes C++ constructors load - lifepods, doors - are rooted, and rebuilding them here crashes the editor)


def E(cls, x, y, **p):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in p.items():
        e.set_editor_property(k, v)
    return e


def L(a, ao, b, bi):
    if not mel.connect_material_expressions(a, ao, b, bi):
        raise RuntimeError(f"{a.get_name()}.{ao} -> {b.get_name()}.{bi}")


def S(n, v, x, y, g="Light"):
    return E(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=n, default_value=v, group=g)


def C(n, x, y):
    return E(unreal.MaterialExpressionCollectionParameter, x, y, collection=mpc, parameter_name=n)


def op(cls, a, ao, b, bo, x, y):
    e = E(cls, x, y)
    L(a, ao, e, "A")
    L(b, bo, e, "B")
    return e


col = E(unreal.MaterialExpressionVectorParameter, -1400, -200, parameter_name="EmissiveColor",
        default_value=unreal.LinearColor(1.0, 0.93, 0.85, 1), group="Light")
inten = S("Intensity", 30.0, -1400, -60)
acw = S("AlertColorWeight", 0.0, -1400, 60, "Alert")
ldw = S("LightDimWeight", 1.0, -1400, 140, "Alert")
mix_w = op(unreal.MaterialExpressionMultiply, C("AlertMix", -1400, 240), "", acw, "", -1150, 180)
# alert colour from scalars only (amber for yellow, red for red): the collection's vector parameter read back as zero
amber = E(unreal.MaterialExpressionConstant3Vector, -1400, 300, constant=unreal.LinearColor(1.0, 0.62, 0.1, 1))
red = E(unreal.MaterialExpressionConstant3Vector, -1400, 360, constant=unreal.LinearColor(1.0, 0.04, 0.02, 1))
acol = E(unreal.MaterialExpressionLinearInterpolate, -1150, 330)
L(amber, "", acol, "A")
L(red, "", acol, "B")
L(C("AlertRed", -1400, 440), "", acol, "Alpha")
lerpc = E(unreal.MaterialExpressionLinearInterpolate, -950, -150)
L(col, "RGB", lerpc, "A")
L(acol, "", lerpc, "B")
L(mix_w, "", lerpc, "Alpha")
one = E(unreal.MaterialExpressionConstant, -1150, 420, r=1.0)
dim = E(unreal.MaterialExpressionLinearInterpolate, -950, 380)
L(one, "", dim, "A")
L(C("LightLevel", -1400, 420), "", dim, "B")
L(ldw, "", dim, "Alpha")
# pulse: 1 - amount * (0.5 + 0.5 sin(t * speed)), amount = max(PulseAmount, AlertPulse * AlertColorWeight * 0.6)
t = E(unreal.MaterialExpressionTime, -1400, 560)
ts = op(unreal.MaterialExpressionMultiply, t, "", S("PulseSpeed", 3.0, -1400, 640), "", -1250, 580)
sn = E(unreal.MaterialExpressionSine, -1100, 580, period=6.2831853)
L(ts, "", sn, "")
s01 = E(unreal.MaterialExpressionMultiplyAdd if hasattr(unreal, "MaterialExpressionMultiplyAdd") else unreal.MaterialExpressionMultiply, -980, 580)
half = E(unreal.MaterialExpressionConstant, -1100, 660, r=0.5)
if isinstance(s01, unreal.MaterialExpressionMultiply):
    L(sn, "", s01, "A"); L(half, "", s01, "B")
    s01 = op(unreal.MaterialExpressionAdd, s01, "", half, "", -900, 600)
else:
    L(sn, "", s01, "A"); L(half, "", s01, "B"); L(half, "", s01, "C")
ap = op(unreal.MaterialExpressionMultiply, C("AlertPulse", -1400, 740), "", acw, "", -1150, 740)
ap6 = op(unreal.MaterialExpressionMultiply, ap, "", E(unreal.MaterialExpressionConstant, -1150, 820, r=0.6), "", -1000, 760)
amt = op(unreal.MaterialExpressionMax, S("PulseAmount", 0.0, -1000, 860), "", ap6, "", -850, 780)
pa = op(unreal.MaterialExpressionMultiply, s01, "", amt, "", -750, 640)
pf = op(unreal.MaterialExpressionSubtract, one, "", pa, "", -620, 600)
e1 = op(unreal.MaterialExpressionMultiply, lerpc, "", inten, "", -700, -100)
e2 = op(unreal.MaterialExpressionMultiply, e1, "", dim, "", -500, 0)
e3 = op(unreal.MaterialExpressionMultiply, e2, "", pf, "", -350, 100)
mel.connect_material_property(e3, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
base = E(unreal.MaterialExpressionVectorParameter, -700, -400, parameter_name="BaseColor",
         default_value=unreal.LinearColor(0.8, 0.8, 0.8, 1), group="Surface")
mel.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(S("Roughness", 0.35, -700, -300, "Surface"), "", unreal.MaterialProperty.MP_ROUGHNESS)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append("M_ASTRA_Emissive rebuilt with alert response")

# --- per-instance alert response
MI = "/Game/ASTRA/Materials/Instances"
for name, cw, dw in (("MI_ASTRA_Accent", 1.0, 0.0), ("MI_ASTRA_Light", 0.85, 1.0), ("MI_ASTRA_Guide", 0.6, 0.0)):
    mi = eal.load_asset(f"{MI}/{name}")
    mel.set_material_instance_scalar_parameter_value(mi, "AlertColorWeight", cw)
    mel.set_material_instance_scalar_parameter_value(mi, "LightDimWeight", dw)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
log.append("instances ok")

# --- alarm sounds
SRC = "/Users/beltromatti/Desktop/ASTRA/art/_cache/audio"
tasks = []
for f in sorted(os.listdir(SRC)):
    if f.endswith(".wav"):
        tk = unreal.AssetImportTask()
        tk.filename = os.path.join(SRC, f)
        tk.destination_path = "/Game/ASTRA/Audio"
        tk.automated = True
        tk.replace_existing = True
        tk.save = True
        tasks.append(tk)
tools.import_asset_tasks(tasks)
log.append(f"sounds: {[a.split('.')[-1] for a in eal.list_assets('/Game/ASTRA/Audio', recursive=False, include_folder=False)]}")
print(json.dumps(log))
