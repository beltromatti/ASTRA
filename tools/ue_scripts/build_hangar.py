"""Builds the Aquila's flight deck into the current level (L_Bridge), from data/ship/aquila_hangar.json: imports the hall
(art/export/hangar), places it where the Aquila's bow tubes are, lights it (tagged ASTRA.Zone.Hangar: they are on only
while the Captain is down there), parks the flight groups in their bays (tagged per squadron for AAstraHangar) and posts
the deck crew. Idempotent: actors in the "Hangar" folder are replaced. Run in the editor, not during PIE:
  tools/ue.py pyfile tools/ue_scripts/build_hangar.py
"""
import json
import math
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Hangar"
M = 100.0
eal = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_hangar.json")))
OX, OY, OZ = D["world_origin"]
log = []

# the finishes of the rooms (the detail uses the ship's steel, trim and crates): created when they are missing
import sys
if ROOT + "/tools/ue_scripts" not in sys.path:
    sys.path.insert(0, ROOT + "/tools/ue_scripts")
import ship_room_materials as RM
RM.build(log)

# ---- import (Nanite on the hall, the glass stays translucent)
SRC = os.path.join(ROOT, "art", "export", "hangar")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())

# ---- clear the previous build
for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Hangar"):
        eas.destroy_actor(a)


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def place(path, x, y, z, yaw=0.0, label=None, folder="Hangar", tags=()):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    if tags:
        a.tags = list(tags)
    return a


place(f"{KIT}/SM_HGR_Deck", 0, 0, 0, label="Hangar_Deck")
place(f"{KIT}/SM_HGR_Detail", 0, 0, 0, label="Hangar_Detail")      # ARTE-INTERNI: markings, ground equipment, wall bays, crane (art/blender/ship_hangar.py)
place(f"{KIT}/SM_HGR_Glass", 0, 0, 0, label="Hangar_BoothGlass")

# ---- lights: big fixtures over the deck, the tubes, the booth; all off until the Captain comes down
ZONE = "ASTRA.Zone.Hangar"


def rect(x, y, z, w, h, lumens, temp, label, shadows=False, pitch=-90.0, yaw=0.0, radius=4200.0):
    a = eas.spawn_actor_from_class(unreal.RectLight, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    c = a.get_component_by_class(unreal.RectLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", lumens)
    c.set_editor_property("source_width", w * M)
    c.set_editor_property("source_height", h * M)
    c.set_editor_property("attenuation_radius", radius)
    c.set_editor_property("use_temperature", True)
    c.set_editor_property("temperature", temp)
    c.set_editor_property("cast_shadows", shadows)
    a.set_actor_label(label)
    a.set_folder_path("Hangar/Lighting")
    a.tags = [ZONE]
    return a


HGT, LEN = D["height"], D["length"]
# (ARTE-INTERNI: the deck read as a grey warehouse with the lights off — 468000 lm over 8120 m2, 58 lm/m2 twenty metres up; the big fixtures are 2.3 times stronger and a row of wall washers
# hangs at the catwalk's height on each side)
for k in range(6):
    x = 12 + k * 22.0
    for j, yy in enumerate((-16.0, 0.0, 16.0)):
        rect(x, yy, HGT - 1.9, 6.0, 2.4, 60000, 5600, f"Hangar_Light_{k}_{j}", shadows=(j == 1 and k % 2 == 0))
for k in range(9):
    x = 10.0 + k * 16.0
    for sy in (-1, 1):
        rect(x, sy * (D["half_width"] - 3.0), D["catwalk"]["z"] - 0.4, 6.0, 1.0, 18000, 5200, f"Hangar_WallWash_{k}_{'P' if sy < 0 else 'S'}", radius=2600.0)
for tb in D["tubes"]:
    rect(LEN + tb["length"] / 2, tb["y"], tb["height"] - 0.6, tb["length"] - 1, tb["width"] - 2, 9000, 6500, f"Hangar_TubeLight_{tb['y']:+.0f}")
bo = D["booth"]
rect(-bo["depth"] / 2, 0, bo["window_top"] + 1.1, bo["depth"] - 1, 2 * bo["half_width"] - 2, 5000, 4200, "Hangar_BoothLight", radius=1500)
log.append("lights")

# ---- the flight groups in their bays (AAstraHangar shows/hides them as the squadrons launch and land)
bays = D["bays"]
for sq in ("alpha", "bravo"):
    b = bays[sq]
    for k in range(b["count"]):
        x = b["x0"] + k * b["pitch"]
        place(f"/Game/ASTRA/Ships/{b['craft']}", x, b["y"], 1.4 if sq == "alpha" else 2.3, b["yaw"], label=f"Hangar_{sq}_{k + 1}",
              folder="Hangar/Craft", tags=("ASTRA.Hangar.Craft", f"ASTRA.Hangar.{sq}"))
dr = bays["drones"]
for r in range(dr["rows"]):
    for k in range(dr["count"] // dr["rows"]):
        place(f"/Game/ASTRA/Ships/{dr['craft']}", dr["x"], dr["y0"] + k * dr["pitch"], 1.0 + r * dr["row_height"], 0.0,
              label=f"Hangar_drone_{r * (dr['count'] // dr['rows']) + k + 1}", folder="Hangar/Craft", tags=("ASTRA.Hangar.Craft", "ASTRA.Hangar.drones"))
# drone racks (simple shelves)
for r in range(dr["rows"]):
    a = place("/Engine/BasicShapes/Cube", dr["x"], dr["y0"] + (dr["count"] // dr["rows"] - 1) * dr["pitch"] / 2, 0.2 + r * dr["row_height"],
              label=f"Hangar_DroneRack_{r}", folder="Hangar/Props")
    a.set_actor_scale3d(unreal.Vector(0.09, (dr["count"] // dr["rows"]) * dr["pitch"] / 100.0 * 100.0 / 100.0, 0.004))
    a.get_component_by_class(unreal.StaticMeshComponent).set_material(0, eal.load_asset("/Game/ASTRA/Materials/Instances/MI_ASTRA_Structure"))
log.append("craft parked")

# ---- the AAstraHangar actor (launch animations, zone lights, the lift) at the hangar origin
h = eas.spawn_actor_from_class(unreal.AstraHangar, V(0, 0, 0), unreal.Rotator())
h.set_actor_label("Hangar_Controller")
h.set_folder_path("Hangar")
BRIDGE_LIFT = (-20.55, -3.9)          # the end of the bridge's port corridor (the end cap is at x -20.8 m)
h.set_editor_property("bridge_landing", unreal.Vector((BRIDGE_LIFT[0] + 1.3) * M, BRIDGE_LIFT[1] * M, 0.0))
h.set_editor_property("hangar_landing", unreal.Vector(2.6 * M, D["lift"]["y"] * M, 0.0))

# ---- the lift doors (closed: the car comes when called) and their signs, on both decks; the flight deck's name
leaf = eal.load_asset("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf")
plate = eal.load_asset("/Game/ASTRA/Kit/Signage/SM_SIGN_Plate")


def doors(wx, wy, wz, label, folder):
    for k, sy in ((0, 1.0), (1, -1.0)):
        a = eas.spawn_actor_from_object(leaf, unreal.Vector(wx * M, wy * M, wz * M), unreal.Rotator())
        a.set_actor_scale3d(unreal.Vector(1.0, sy * 1.0, 1.05))
        a.set_actor_label(f"{label}_Leaf{k}")
        a.set_folder_path(folder)


def sign(name, wx, wy, wz, w, hh, label, folder, yaw=0.0):
    a = eas.spawn_actor_from_object(plate, unreal.Vector(wx * M, wy * M, wz * M), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(1.0, w, hh))
    smc = a.get_component_by_class(unreal.StaticMeshComponent)
    for i, sm in enumerate(plate.get_editor_property("static_materials")):
        if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
            smc.set_material(i, eal.load_asset(f"/Game/ASTRA/Materials/Instances/MI_SIGN_{name}"))
    smc.set_editor_property("cast_shadow", False)
    a.set_actor_label(label)
    a.set_folder_path(folder)


doors(BRIDGE_LIFT[0], BRIDGE_LIFT[1], 0.0, "Lift_Bridge", "Hangar/Lift")
sign("Lift_Bridge", BRIDGE_LIFT[0] + 0.06, BRIDGE_LIFT[1], 2.62, 1.1, 0.275, "Lift_Bridge_Sign", "Hangar/Lift")
doors(OX + 0.12, OY + D["lift"]["y"], OZ, "Lift_Hangar", "Hangar/Lift")
sign("Lift_Hangar", OX + 0.3, OY + D["lift"]["y"], OZ + D["lift"]["height"] + 0.45, 1.4, 0.35, "Lift_Hangar_Sign", "Hangar/Lift")
sign("FlightDeck", OX + 0.3, OY + 14.0, OZ + 5.5, 6.0, 1.5, "Hangar_Sign_FlightDeck", "Hangar/Lift")

# ---- containment fields at the tube ends: the air stays in, the craft go through
field_mat = eal.load_asset("/Game/ASTRA/Materials/Instances/MI_FX_ContainmentField")
if field_mat is None:
    fm = tools.create_asset("MI_FX_ContainmentField", "/Game/ASTRA/Materials/Instances", unreal.MaterialInstanceConstant,
                            unreal.MaterialInstanceConstantFactoryNew())
    unreal.MaterialEditingLibrary.set_material_instance_parent(fm, eal.load_asset("/Game/ASTRA/Materials/M_FX_Glow"))
    unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(fm, "Color", unreal.LinearColor(0.3, 0.6, 1.0, 1.0))
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(fm, "Intensity", 0.9)
    eal.save_loaded_asset(fm, only_if_is_dirty=False)
    field_mat = fm
cube = eal.load_asset("/Engine/BasicShapes/Cube")
for tb in D["tubes"]:
    a = eas.spawn_actor_from_object(cube, V(LEN + tb["length"] - 0.8, tb["y"], tb["height"] / 2), unreal.Rotator())
    a.set_actor_scale3d(unreal.Vector(0.02, tb["width"] / 100.0 * 100.0 / 100.0 * 1.0, tb["height"] / 100.0 * 100.0 / 100.0))
    a.set_actor_scale3d(unreal.Vector(0.02, tb["width"], tb["height"]))
    smc = a.get_component_by_class(unreal.StaticMeshComponent)
    smc.set_material(0, field_mat)
    smc.set_editor_property("cast_shadow", False)
    smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    a.set_actor_label(f"Hangar_Field_{tb['y']:+.0f}")
    a.set_folder_path("Hangar/Props")

# ---- deck crew in flight-deck gear, standing by the craft
posts = [(30, -12, 200), (56, -13, 160), (82, -12, 220), (40, 11, -20), (72, 12, 10), (104, 12, -30), (120, -6, 90), (8, 3, 180)]
for i, (x, y, yaw) in enumerate(posts):
    c = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x, y, 0.0), unreal.Rotator(roll=0, pitch=0, yaw=yaw - 90.0))
    c.set_editor_property("posture", unreal.AstraCrewPosture.STANDING)
    c.set_editor_property("station_id", f"deck{i + 1}")
    c.set_editor_property("display_name", "")
    c.set_actor_label(f"Hangar_DeckCrew_{i + 1}")
    c.set_folder_path("Hangar/Crew")
log.append("deck crew")
unreal.EditorLevelLibrary.save_current_level()
print(log)
