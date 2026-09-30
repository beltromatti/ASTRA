"""Builds Crew Berthing (Deck 4 · Section C) into the bridge level, from data/ship/aquila_berths.json: the signs, the
materials, the kit (art/export/berths, art/blender/berths.py), the racks and locker columns along the aisle, the Red
watch asleep in some of the racks (flat, under their blankets), two ratings who cannot sleep at the table aft, the night
lighting (tagged ASTRA.Zone.Berths: on only while the Captain is there), the lift's doors and sign and its sixth landing;
the lift signs on the other decks now list it (Deck 4 · Section C). Idempotent: the "Berths" folder is replaced. Not during PIE, after
the C++ module is built (AAstraHangar::BerthLanding):
  tools/ue.py pyfile tools/ue_scripts/build_berths.py
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Berths"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
SIGN_TEX = "/Game/ASTRA/UI/Signage"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_berths.json")))
OX, OY, OZ = D["world_origin"]
ST = D["stacks"]
RW, RL, YF, LW = ST["rack_width"], ST["rack_length"], ST["y_foot"], ST["locker_width"]
ZONE = "ASTRA.Zone.Berths"
log = []


def import_png(src_dir, names, dst):
    tasks = []
    for n in names:
        t = unreal.AssetImportTask()
        t.filename = os.path.join(src_dir, n + ".png")
        t.destination_path = dst
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    for n in names:
        tx = eal.load_asset(f"{dst}/{n}")
        tx.set_editor_property("srgb", True)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tx, only_if_is_dirty=False)


import_png(os.path.join(ROOT, "art", "_cache", "signage"), ["T_SIGN_Berth_3C", "T_SIGN_Head", "T_SIGN_Lift_Bridge", "T_SIGN_Lift_Hangar"], SIGN_TEX)
log.append("textures")
# the new sounds (tools/art/ship_sounds.py): the compartment's night, the datapad, the jammers' rasp
ONLY = ["SW_Berth_Ambience", "SW_Pad_Up", "SW_Pad_Down", "SW_Jam_Static"]
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_audio.py")).read())
log.append("sounds")


def mi(name, parent_path, scalars=None, vectors=None, textures=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, eal.load_asset(parent_path))
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(v))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)


HARD = "/Game/ASTRA/Materials/M_ASTRA_Hard"
EMI = "/Game/ASTRA/Materials/M_ASTRA_Emissive"
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"
# the lockers and the racks' drawers: a muted blue-grey enamel, worn at the edges; the night lights red and dim; the
# reading lights a warm glow
mi("MI_BERTH_Locker", HARD, {"RoughnessMin": 0.3, "RoughnessMax": 0.5, "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                             "BaseColorMapInfluence": 0.3, "NormalStrength": 0.4, "UVScale": 1.0, "MacroBrightness": 0.06,
                             "ScratchRoughness": 0.05, "RoughnessVariation": 0.08},
   {"Tint": (0.2, 0.25, 0.28)},
   {"BaseColorMap": f"{TEX}/T_PanelPaint_BC", "NormalMap": f"{TEX}/T_PanelPaint_N", "ORMMap": f"{TEX}/T_PanelPaint_ORM"})
mi("MI_BERTH_NightLight", EMI, {"Intensity": 6.0, "AlertColorWeight": 0.0, "LightDimWeight": 0.0},
   {"EmissiveColor": (1.0, 0.06, 0.03), "BaseColor": (0.05, 0.01, 0.01)})
mi("MI_BERTH_Reading", EMI, {"Intensity": 4.0, "AlertColorWeight": 0.0, "LightDimWeight": 0.0},
   {"EmissiveColor": (1.0, 0.72, 0.42), "BaseColor": (0.3, 0.25, 0.2)})
for name in ("Berth_3C", "Head"):
    mi(f"MI_SIGN_{name}", SCREEN, {"Intensity": 5.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, None,
       {"ScreenTexture": f"{SIGN_TEX}/T_SIGN_{name}"})
log.append("materials")

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Berths"):
        eas.destroy_actor(a)
if eal.does_directory_exist(KIT):
    for path in eal.list_assets(KIT, recursive=False, include_folder=False):
        if not eal.delete_asset(path):
            log.append(f"could not delete {path}")

SRC = os.path.join(ROOT, "art", "export", "berths")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def place(path, x, y, z, yaw=0.0, label=None, folder="Berths"):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    return a


place(f"{KIT}/SM_BERTH_Room", 0, 0, 0, label="Berths_Room")


def layout():
    """(mesh, x, y, yaw) for every stack and locker column: the same as art/blender/berths.py's layout()."""
    out = []
    for g in range(ST["groups"]):
        xg = ST["x_start"] - g * (2 * RW + LW)
        v = ST["variants"][g % len(ST["variants"])]
        for side in (1, -1):
            for k in range(2):
                vv = v if (k + (side > 0)) % 2 else "ABC"[("ABC".index(v) + 1) % 3]
                out.append((f"SM_BERTH_Stack_{vv}", xg - RW / 2 - k * RW, side * YF, 0.0 if side > 0 else 180.0))
            out.append(("SM_BERTH_Lockers", xg - 2 * RW - LW / 2, side * YF, 0.0 if side > 0 else 180.0))
    return out


for n, (mesh, x, y, yaw) in enumerate(layout()):
    place(f"{KIT}/{mesh}", x, y, 0.0, yaw, label=f"Berths_{mesh[10:]}_{n:02d}", folder="Berths/Racks")
log.append(f"{len(layout())} racks and lockers")

# ---- the Red watch asleep: flat on their backs under the blankets, heads at the outboard wall
LEVELS = ST["rack_heights"]
for k, s in enumerate(D["sleepers"]):
    xg = ST["x_start"] - s["group"] * (2 * RW + LW)
    x = xg - RW / 2 - s["stack"] * RW
    side = s["side"]
    y = side * (YF + RL * 0.52)
    z = LEVELS[s["level"]] + 0.04 + 0.16
    a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=90.0 * side))
    a.set_editor_property("posture", unreal.AstraCrewPosture.LYING)
    a.set_editor_property("recline_deg", 0.0)
    a.set_editor_property("station_id", f"sleeper{k + 1}")
    a.set_actor_label(f"Berths_Sleeper{k + 1}")
    a.set_folder_path("Berths/Crew")
# ---- two who cannot sleep, at the table aft
for w in D["awake"]:
    sx, sy = w["seat"]
    a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(sx, sy, 0.0), unreal.Rotator(roll=0, pitch=0, yaw=w["yaw"]))
    a.set_editor_property("posture", unreal.AstraCrewPosture.SEATED_CONSOLE)
    a.set_editor_property("station_id", w["station"])
    a.set_editor_property("seat_hip_height", 50.0)
    a.set_actor_label(f"Berths_{w['station']}")
    a.set_folder_path("Berths/Crew")
log.append(f"{len(D['sleepers'])} asleep, {len(D['awake'])} awake")


# ---- the night: dimmed warm aisle lights, red at the skirting, a few reading lights in the racks, the lounge warmer
def light(cls, x, y, z, label, intensity, color, radius, shadows=False, pitch=-90.0, yaw=0.0, size=None):
    a = eas.spawn_actor_from_class(cls, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    lc = a.get_component_by_class(unreal.LocalLightComponent)
    lc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    lc.set_editor_property("intensity", intensity)
    lc.set_editor_property("attenuation_radius", radius)
    lc.set_editor_property("light_color", unreal.Color(r=color[0], g=color[1], b=color[2], a=255))
    lc.set_editor_property("cast_shadows", shadows)
    if size and isinstance(lc, unreal.RectLightComponent):
        lc.set_editor_property("source_width", size[0] * M)
        lc.set_editor_property("source_height", size[1] * M)
    a.set_actor_label(label)
    a.set_folder_path("Berths/Lighting")
    a.tags = [ZONE]
    return a


H = D["height"]
LEN = D["length"]
# (a dim room, but the Captain must see the racks and who sleeps in them: about a third of the Mess's light)
light(unreal.RectLight, -10.0, -0.07, H - 0.05, "Berths_Aisle", 14000, (255, 214, 170), 1100, shadows=True, size=(18.0, 0.3))
for x in (-4.0, -10.0, -16.0):
    light(unreal.PointLight, x, 0.0, 0.25, f"Berths_Night_{-int(x)}", 600, (255, 40, 25), 550)
for k, (g, stk, side, lvl) in enumerate(((0, 1, -1, 0), (1, 0, 1, 1), (2, 1, -1, 2), (3, 1, -1, 2), (4, 0, 1, 0), (5, 0, 1, 0), (6, 1, -1, 1))):
    xg = ST["x_start"] - g * (2 * RW + LW)
    x = xg - RW / 2 - stk * RW
    z = (ST["rack_heights"][lvl + 1] if lvl + 1 < 3 else ST["rack_heights"][2] + 0.85) - 0.1
    light(unreal.PointLight, x, side * (YF + RL - 0.35), z, f"Berths_Reading{k + 1}", 450, (255, 190, 120), 260)
lo = D["lounge"]
light(unreal.RectLight, lo["table"]["x"], lo["table"]["y"], H - 0.06, "Berths_Lounge", 5000, (255, 225, 190), 700, shadows=True,
      size=(2.0, 1.2))
light(unreal.RectLight, -LEN + 0.6, -0.7, 2.7, "Berths_News", 500, (190, 215, 255), 400, pitch=-35.0, yaw=180.0, size=(3.0, 0.2))
log.append("lights")

# ---- the compartment's own sound at night: air handlers, the reactor faint through the deck, a creak (heard only in it)
sw = eal.load_asset("/Game/ASTRA/Audio/SW_Berth_Ambience")
if sw:
    amb = eas.spawn_actor_from_class(unreal.AmbientSound, V(-12.0, 0.0, 2.0), unreal.Rotator())
    ac = amb.get_component_by_class(unreal.AudioComponent)
    ac.set_editor_property("sound", sw)
    ac.set_editor_property("volume_multiplier", 0.6)
    ac.set_editor_property("override_attenuation", True)
    att = ac.get_editor_property("attenuation_overrides")
    att.set_editor_property("attenuation_shape", unreal.AttenuationShape.BOX)
    att.set_editor_property("attenuation_shape_extents", unreal.Vector(1300.0, 450.0, 250.0))
    att.set_editor_property("falloff_distance", 400.0)
    ac.set_editor_property("attenuation_overrides", att)
    amb.set_actor_label("Berths_Ambience")
    amb.set_folder_path("Berths")
    log.append("ambience")

# ---- the lift: doors and the landing on the lift network (the compartment's sign is on its forward wall)
leaf = eal.load_asset("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf")
for n, sy in ((0, 1.0), (1, -1.0)):
    a = eas.spawn_actor_from_object(leaf, V(0.12, D["lift"]["y"], 0.0), unreal.Rotator())
    a.set_actor_scale3d(unreal.Vector(1.0, sy, 1.0))
    a.set_actor_label(f"Lift_Berths_Leaf{n}")
    a.set_folder_path("Berths/Lift")
for h in eas.get_all_level_actors():
    if isinstance(h, unreal.AstraHangar):
        h.set_editor_property("berth_landing", V(-2.0, D["lift"]["y"], 0.0))
        log.append("lift landing set")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
