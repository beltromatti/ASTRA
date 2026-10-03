"""Builds Main Engineering (Deck 7) into the bridge level, from data/ship/aquila_engineering.json: imports the hall and
the reactor core (art/export/engineering), makes their materials (the core's plasma pulses), lights it (tagged
ASTRA.Zone.Engineering: on only while the Captain is down there), posts the Chief Engineer and three technicians, and
puts the lift's doors and sign on the forward wall. Idempotent: the "Engineering" folder is replaced. Not during PIE:
  tools/ue.py pyfile tools/ue_scripts/build_engineering.py
"""
import json
import math
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Engineering"
MI_DIR = "/Game/ASTRA/Materials/Instances"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_engineering.json")))
OX, OY, OZ = D["world_origin"]
ZONE = "ASTRA.Zone.Engineering"
log = []


def mi(name, parent_path, scalars=None, vectors=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, eal.load_asset(parent_path))
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)


# the plasma: blue-white, breathing slowly; the coolant lines: navy blue paint
mi("MI_ENG_Plasma", "/Game/ASTRA/Materials/M_ASTRA_Emissive", {"Intensity": 55.0, "PulseSpeed": 1.1, "PulseAmount": 0.3,
                                                                "AlertColorWeight": 0.0, "LightDimWeight": 0.0}, {"EmissiveColor": (0.16, 0.5, 1.0)})
mi("MI_ENG_Coolant", "/Game/ASTRA/Materials/M_ASTRA_Hard", {"RoughnessMin": 0.35, "RoughnessMax": 0.55, "MetallicFromMap": 0.0,
                                                             "BaseColorMapInfluence": 0.3}, {"Tint": (0.03, 0.09, 0.28)})
log.append("materials")

# the finishes of the rooms (the detail uses the ship's steel, trim and crates): created when they are missing
import sys
if ROOT + "/tools/ue_scripts" not in sys.path:
    sys.path.insert(0, ROOT + "/tools/ue_scripts")
import ship_room_materials as RM
RM.build(log)

SRC = os.path.join(ROOT, "art", "export", "engineering")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Engineering"):
        eas.destroy_actor(a)


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def place(path, x, y, z, yaw=0.0, label=None, folder="Engineering"):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    return a


place(f"{KIT}/SM_ENG_Hall", 0, 0, 0, label="Engineering_Hall")
place(f"{KIT}/SM_ENG_Detail", 0, 0, 0, label="Engineering_Detail")             # ARTE-INTERNI: machines, wall bays, crane, luminaires (art/blender/ship_engineering.py)
R = D["reactor"]
place(f"{KIT}/SM_ENG_Core", R["x"], R["y"], 0, label="Engineering_Core")


# ---- light: the core's blue glow, cool overheads, all off until the Captain comes down
def light(cls, x, y, z, label, intensity, color, radius, shadows=False, pitch=-90.0, size=None):
    a = eas.spawn_actor_from_class(cls, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=0))
    c = a.get_component_by_class(unreal.LocalLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", intensity)
    c.set_editor_property("attenuation_radius", radius)
    c.set_editor_property("light_color", unreal.Color(r=color[0], g=color[1], b=color[2], a=255))
    c.set_editor_property("cast_shadows", shadows)
    if size and isinstance(c, unreal.RectLightComponent):
        c.set_editor_property("source_width", size[0] * M)
        c.set_editor_property("source_height", size[1] * M)
    a.set_actor_label(label)
    a.set_folder_path("Engineering/Lighting")
    a.tags = [ZONE]
    return a


for k in range(4):
    ang = 2 * math.pi * (k + 0.25) / 4
    light(unreal.PointLight, R["x"] + math.cos(ang) * (R["radius"] + 2.2), R["y"] + math.sin(ang) * (R["radius"] + 2.2), 4.0 + 4 * (k % 2),
          f"Engineering_CoreGlow_{k}", 30000, (60, 140, 255), 2800, shadows=(k == 0))
# (ARTE-INTERNI: the hall was black, twelve lamps of 5200 lm twelve metres over a deck of 1176 m2: the high-bay luminaires hung from the trusses (the meshes of SM_ENG_Detail) carry the light now,
# the old ceiling lamps stay as a soft top light, and a row of work lights hangs under each gallery)
for k in range(6):
    x = -3 - k * 6.5
    for yy in (-8.0, 8.0):
        light(unreal.RectLight, x, yy, D["height"] - 1.5, f"Engineering_Lamp_{k}_{yy:+.0f}", 6000, (235, 242, 255), 1800, size=(3.4, 1.4))
        light(unreal.RectLight, x, yy, D["height"] - 4.3, f"Engineering_HighBay_{k}_{yy:+.0f}", 18000, (235, 242, 255), 2400, size=(1.4, 1.4))
for k in range(8):
    x = -9.0 - k * 4.0
    for yy in (-11.2, 11.2):
        light(unreal.RectLight, x, yy, D["gallery"]["z"] - 0.7, f"Engineering_GalleryLamp_{k}_{yy:+.0f}", 7000, (255, 232, 200), 1100, size=(3.0, 0.4))
mc = D["master_console"]
light(unreal.PointLight, mc["x"], mc["y"], 3.2, "Engineering_ConsoleGlow", 3500, (120, 200, 255), 900)
log.append("lights")

# ---- the Chief and the watch
for c in D["crew"]:
    a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(c["x"], c["y"], 0.0), unreal.Rotator(roll=0, pitch=0, yaw=c["yaw"] - 90.0))
    a.set_editor_property("posture", unreal.AstraCrewPosture.STANDING)
    a.set_editor_property("station_id", c["station"])
    a.set_editor_property("display_name", c.get("name", ""))
    a.set_actor_label(f"Engineering_{c['station']}")
    a.set_folder_path("Engineering/Crew")
log.append("crew")

# ---- the lift's doors on the forward wall and the sign above them
leaf = eal.load_asset("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf")
plate = eal.load_asset("/Game/ASTRA/Kit/Signage/SM_SIGN_Plate")
for k, sy in ((0, 1.0), (1, -1.0)):
    a = eas.spawn_actor_from_object(leaf, V(0.12, D["lift"]["y"], 0.0), unreal.Rotator())
    a.set_actor_scale3d(unreal.Vector(1.0, sy, 1.05))
    a.set_actor_label(f"Lift_Engineering_Leaf{k}")
    a.set_folder_path("Engineering/Lift")
s = eas.spawn_actor_from_object(plate, V(-0.3, D["lift"]["y"], D["lift"]["height"] + 0.9), unreal.Rotator(roll=0, pitch=0, yaw=180.0))
s.set_actor_scale3d(unreal.Vector(1.0, 2.2, 0.55))
smc = s.get_component_by_class(unreal.StaticMeshComponent)
for i, sm in enumerate(plate.get_editor_property("static_materials")):
    if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
        smc.set_material(i, eal.load_asset(f"{MI_DIR}/MI_SIGN_Room_Engineering"))
smc.set_editor_property("cast_shadow", False)
s.set_actor_label("Engineering_Sign")
s.set_folder_path("Engineering/Lift")

# ---- the lift's third landing: the hangar controller carries the network
for h in eas.get_all_level_actors():
    if isinstance(h, unreal.AstraHangar):
        h.set_editor_property("engineering_landing", V(-2.6, D["lift"]["y"], 0.0))
        log.append("lift landing set")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
