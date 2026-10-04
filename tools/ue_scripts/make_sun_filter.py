"""M_ASTRA_SunFilter: the light function of the star (the main directional light, UAstraShipSubsystem sets it at begin play).
The bridge's great window is electrochromic: inside the bridge the star's light is Transmit of what it is outside, so the
consoles' screens, the lamps and the shadows hold the room, and a sunlit patch on the deck is a warm pool, not a white-out
(at the bridge's fixed exposure, EV100 6.6, a white console in full sun was ~25 times brighter than a screen). Outside the
bridge (the hull, the other ships, the view through the window) the star is untouched.

The bridge, in world centimetres (data/ship/aquila_bridge.json: origin under the Captain's chair, the window an arc of
radius 10 m from -60 to +60 degrees, the back wall at x -8.5 m, the ceiling dome up to 5.6 m): inside the window's arc,
in front of the back wall, between the side walls, from below the well's floor to the top of the dome. Soft edges (Edge cm).

  tools/ue.py pyfile tools/ue_scripts/make_sun_filter.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
PATH = "/Game/ASTRA/Materials/M_ASTRA_SunFilter"
log = []

if eal.does_asset_exist(PATH):
    m = eal.load_asset(PATH)
    for _e in list(mel.get_material_expressions(m)): mel.delete_material_expression(m, _e)   # (from a copy of the list)
else:
    m = tools.create_asset("M_ASTRA_SunFilter", "/Game/ASTRA/Materials", unreal.Material, unreal.MaterialFactoryNew())
m.set_editor_property("material_domain", unreal.MaterialDomain.MD_LIGHT_FUNCTION)


def E(cls, x, y, **p):
    e = mel.create_material_expression(m, cls, x, y)
    for k, v in p.items():
        e.set_editor_property(k, v)
    return e


def S(name, v, x, y):
    return E(unreal.MaterialExpressionScalarParameter, x, y, parameter_name=name, default_value=v, group="Bridge")


wp = E(unreal.MaterialExpressionWorldPosition, -900, 0)
c = E(unreal.MaterialExpressionCustom, -500, 0)
c.set_editor_property("code", """
float r = length(P.xy);
float e = max(Edge, 1.0);
float inside = smoothstep(Radius, Radius - e, r)             // inside the window's arc
             * smoothstep(BackX - e, BackX, P.x)              // in front of the back wall
             * smoothstep(HalfY, HalfY - e, abs(P.y))         // between the side walls
             * smoothstep(ZMin - e, ZMin, P.z) * smoothstep(ZMax, ZMax - e, P.z);
return lerp(1.0, Transmit, inside).xxx;
""")
c.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
pins = []
for name in ("P", "Transmit", "Radius", "BackX", "HalfY", "ZMin", "ZMax", "Edge"):
    ci = unreal.CustomInput()
    ci.set_editor_property("input_name", name)
    pins.append(ci)
c.set_editor_property("inputs", pins)
mel.connect_material_expressions(wp, "", c, "P")
for k, (name, v) in enumerate((("Transmit", 0.1), ("Radius", 995.0), ("BackX", -860.0), ("HalfY", 760.0), ("ZMin", -90.0),
                               ("ZMax", 590.0), ("Edge", 40.0))):
    mel.connect_material_expressions(S(name, v, -900, 120 + k * 70), "", c, name)
mel.connect_material_property(c, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m)
eal.save_loaded_asset(m, only_if_is_dirty=False)
log.append("M_ASTRA_SunFilter")
print(json.dumps(log))
