"""Builds the Mess Hall (Deck 4 · Section B) into the bridge level, from data/ship/aquila_mess.json: the menu board and
the placeholder faces of the two big screens (drawn live by AstraScreensSubsystem: the fleet's news, the memorial), the
materials, the kit (art/export/messhall, art/blender/messhall.py), twelve off-duty diners on the benches (the ship
gives them names and faces from the roster) with their trays, the galley's cook, the lights (tagged ASTRA.Zone.Mess: on
only while the Captain is there), the lift's doors and sign and its fifth landing; the lift signs on the other decks
now list Deck 4. Idempotent: the "Mess" folder is replaced. Not during PIE, after the C++ module is built:
  tools/ue.py pyfile tools/ue_scripts/build_messhall.py
(then tools/ue_scripts/place_walkers.py for the two crew walking between the counter and the tables)
"""
import json
import os
import random

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Mess"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
UI_TEX = "/Game/ASTRA/UI/Textures"
SIGN_TEX = "/Game/ASTRA/UI/Signage"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_mess.json")))
OX, OY, OZ = D["world_origin"]
ZONE = "ASTRA.Zone.Mess"
T_ = D["tables"]
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


import_png(os.path.join(ROOT, "art", "_cache", "ui"), ["T_UI_Mess_Menu", "T_UI_Mess_News", "T_UI_Mess_Memorial"], UI_TEX)
import_png(os.path.join(ROOT, "art", "_cache", "signage"), ["T_SIGN_Room_Mess", "T_SIGN_Lift_Bridge", "T_SIGN_Lift_Hangar"], SIGN_TEX)
log.append("textures")


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
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"


def cloth(set_name):
    return {"BaseColorMap": f"{TEX}/T_{set_name}_BC", "NormalMap": f"{TEX}/T_{set_name}_N", "ORMMap": f"{TEX}/T_{set_name}_ORM"}


def hard(name, tint, rough, tex="PanelPaint", uv=1.0, normal=0.4, influence=0.3, macro=0.05):
    mi(name, HARD, {"RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                    "BaseColorMapInfluence": influence, "NormalStrength": normal, "UVScale": uv, "MacroBrightness": macro,
                    "ScratchRoughness": 0.02, "RoughnessVariation": 0.06}, {"Tint": tint}, cloth(tex))


# a warship's mess, made homely: warm grey deck, blue-grey wainscot under warm pale panels, sand laminate tables, navy
# vinyl benches; real food on the counter and the trays; greens under their grow light
hard("MI_MESS_Floor", (0.2, 0.19, 0.18), (0.32, 0.5), normal=0.3, macro=0.08)
hard("MI_MESS_Wall", (0.66, 0.63, 0.58), (0.4, 0.55))
hard("MI_MESS_Panel", (0.16, 0.21, 0.27), (0.3, 0.45))
hard("MI_MESS_Table", (0.6, 0.52, 0.41), (0.22, 0.36), normal=0.15, influence=0.2)
hard("MI_MESS_Seat", (0.05, 0.08, 0.15), (0.35, 0.5), tex="Linen", uv=3.0, normal=0.35, influence=0.25)
hard("MI_MESS_Tray", (0.3, 0.36, 0.42), (0.3, 0.42), normal=0.1)
hard("MI_MESS_Plate", (0.84, 0.84, 0.82), (0.12, 0.2), normal=0.05, influence=0.1)
hard("MI_MESS_Cup", (0.08, 0.17, 0.4), (0.18, 0.3), normal=0.05, influence=0.1)
hard("MI_MESS_Food1", (0.19, 0.08, 0.035), (0.3, 0.5), tex="Linen", uv=6.0, normal=0.9, influence=0.4)
hard("MI_MESS_Food2", (0.62, 0.48, 0.2), (0.45, 0.6), tex="Linen", uv=8.0, normal=0.9, influence=0.5)
hard("MI_MESS_Food3", (0.09, 0.27, 0.05), (0.4, 0.55), tex="Linen", uv=6.0, normal=0.9, influence=0.5)
hard("MI_MESS_Leaf", (0.06, 0.26, 0.05), (0.45, 0.6), tex="Linen", uv=4.0, normal=0.8, influence=0.5, macro=0.1)
hard("MI_MESS_Board", (0.42, 0.27, 0.14), (0.8, 0.95), tex="Linen", uv=5.0, normal=0.9, influence=0.6)
hard("MI_MESS_Note", (0.85, 0.84, 0.78), (0.8, 0.9), normal=0.1, influence=0.1)
hard("MI_MESS_Oven", (0.07, 0.075, 0.08), (0.25, 0.4), normal=0.2)
mi("MI_UI_Mess_Menu", SCREEN, {"Intensity": 10.0, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, None,
   {"ScreenTexture": f"{UI_TEX}/T_UI_Mess_Menu"})
for name in ("News", "Memorial"):
    mi(f"MI_UI_Mess_{name}", SCREEN, {"Intensity": 12.0, "Roughness": 0.3, "FlipU": 0.0, "FlipV": 0.0}, None,
       {"ScreenTexture": f"{UI_TEX}/T_UI_Mess_{name}"})
mi("MI_SIGN_Room_Mess", SCREEN, {"Intensity": 8.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, None,
   {"ScreenTexture": f"{SIGN_TEX}/T_SIGN_Room_Mess"})
log.append("materials")

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Mess"):
        eas.destroy_actor(a)
for path in eal.list_assets(KIT, recursive=False, include_folder=False):
    if not eal.delete_asset(path):
        log.append(f"could not delete {path}")

SRC = os.path.join(ROOT, "art", "export", "messhall")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def place(path, x, y, z, yaw=0.0, label=None, folder="Mess"):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    return a


place(f"{KIT}/SM_MESS_Hall", 0, 0, 0, label="Mess_Hall")
g = place(f"{KIT}/SM_MESS_Glass", 0, 0, 0, label="Mess_Glass")
g.static_mesh_component.set_editor_property("cast_shadow", False)

# ---- the diners: seated on the benches facing their table, hands at their trays (the ship names them from the roster)
rng = random.Random(7)
for d in D["diners"]:
    i, j = d["table"]
    x = T_["x_centres"][i] + d["dx"]
    yt = T_["y_centres"][j]
    side = d["side"]                      # -1: on the bench on the table's port side, facing starboard
    yb = yt + side * T_["bench_offset"]
    yaw = 90.0 if side < 0 else -90.0
    a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x, yb, 0.0), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_editor_property("posture", unreal.AstraCrewPosture.SEATED_CONSOLE)
    a.set_editor_property("station_id", d["station"])
    a.set_editor_property("seat_hip_height", 52.0)
    a.set_actor_label(f"Mess_{d['station']}")
    a.set_folder_path("Mess/Diners")
    place(f"{KIT}/SM_MESS_Tray", x, yt - side * 0.24, T_["height"], yaw, label=f"Mess_Tray_{d['station']}", folder="Mess/Trays")
# a few trays left where others have eaten and gone
for k in range(6):
    i, j = rng.randrange(3), rng.randrange(4)
    side = rng.choice((-1, 1))
    x = T_["x_centres"][i] + rng.uniform(-3.0, 3.0)
    place(f"{KIT}/SM_MESS_Tray", x, T_["y_centres"][j] - side * 0.24, T_["height"], 90.0 if side < 0 else -90.0,
          label=f"Mess_Tray_Left{k}", folder="Mess/Trays")
c = D["cook"]
a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(c["x"], c["y"], 0.0), unreal.Rotator(roll=0, pitch=0, yaw=c["yaw"] - 90.0))
a.set_editor_property("posture", unreal.AstraCrewPosture.STANDING)
a.set_editor_property("station_id", c["station"])
a.set_editor_property("female_body", bool(c.get("female")))
a.set_editor_property("display_name", "Petty Officer Tomas Wren")
a.set_actor_label("Mess_Cook")
a.set_folder_path("Mess/Crew")
log.append(f"{len(D['diners'])} diners, a cook")


# ---- the light: warm white troffers over the tables, the counter's bright field, the kitchen, the screens' picture
#      lights, the greens' grow light; all off until the Captain comes down
# ARTE-INTERNI (2 Oct tour: "the Mess Hall is almost black"): these lights are actors, so the ship's astra.lamps.gain (x6 on the plan's lamps) does not reach them; a corridor
# lamp is ~106 plan lumens per m2 (x6 in the game), the hall's lights gave 100 in all: LIGHT_GAIN brings them to the 90 plan lm/m2 x 6 that the rooms of the plan are tuned to
# (art/blender/ship_spec.retune_lights: a canteen)
LIGHT_GAIN = 5.0


def light(cls, x, y, z, label, intensity, color, radius, shadows=False, pitch=-90.0, yaw=0.0, size=None):
    a = eas.spawn_actor_from_class(cls, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    lc = a.get_component_by_class(unreal.LocalLightComponent)
    lc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    lc.set_editor_property("intensity", intensity * LIGHT_GAIN)
    lc.set_editor_property("attenuation_radius", radius)
    lc.set_editor_property("light_color", unreal.Color(r=color[0], g=color[1], b=color[2], a=255))
    lc.set_editor_property("cast_shadows", shadows)
    if size and isinstance(lc, unreal.RectLightComponent):
        lc.set_editor_property("source_width", size[0] * M)
        lc.set_editor_property("source_height", size[1] * M)
    a.set_actor_label(label)
    a.set_folder_path("Mess/Lighting")
    a.tags = [ZONE]
    return a


H = D["height"]
WARM = (255, 238, 214)
# few, long sources (the Medbay's lesson: 8 table lights cost 3 ms): one per row of tables, the whole length; one of
# them (the inner port row) casts the soft shadows under the tables and the people
for yc in T_["y_centres"]:
    light(unreal.RectLight, -23.4, yc, H - 0.08, f"Mess_Tables_{'P' if yc < 0 else 'S'}{abs(yc):.0f}", 15000, WARM, 1300,
          shadows=(yc == T_["y_centres"][1]), size=(27.0, 0.6))
g_ = D["galley"]
light(unreal.RectLight, (g_["x0"] + g_["x1"]) / 2, -7.6, H - 0.08, "Mess_Counter", 7000, (255, 244, 228), 800, size=(7.0, 1.2))
light(unreal.RectLight, -5.5, 5.5, H - 0.08, "Mess_Forward", 6000, WARM, 900, size=(6.0, 6.0))
light(unreal.PointLight, (g_["x0"] + g_["x1"]) / 2, -11.4, H - 0.4, "Mess_Kitchen", 3000, (255, 240, 220), 600)
light(unreal.RectLight, -37.4, 0.0, 3.5, "Mess_Screens", 1500, WARM, 700, pitch=-30.0, yaw=180.0, size=(17.0, 0.3))
light(unreal.RectLight, -23.5, 9.5, 2.0, "Mess_GrowLight", 1800, (235, 255, 225), 500, size=(7.0, 0.4))
log.append("lights")

# ---- the lift: doors and sign on the forward wall; the landing on the lift network
leaf = eal.load_asset("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf")
plate = eal.load_asset("/Game/ASTRA/Kit/Signage/SM_SIGN_Plate")
for n, sy in ((0, 1.0), (1, -1.0)):
    a = eas.spawn_actor_from_object(leaf, V(0.12, D["lift"]["y"], 0.0), unreal.Rotator())
    a.set_actor_scale3d(unreal.Vector(1.0, sy, 1.05))
    a.set_actor_label(f"Lift_Mess_Leaf{n}")
    a.set_folder_path("Mess/Lift")
s = eas.spawn_actor_from_object(plate, V(-0.3, D["lift"]["y"], D["lift"]["height"] + 0.35), unreal.Rotator(roll=0, pitch=0, yaw=180.0))
s.set_actor_scale3d(unreal.Vector(1.0, 2.2, 0.55))
smc = s.get_component_by_class(unreal.StaticMeshComponent)
for i, sm in enumerate(plate.get_editor_property("static_materials")):
    if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
        smc.set_material(i, eal.load_asset(f"{MI_DIR}/MI_SIGN_Room_Mess"))
smc.set_editor_property("cast_shadow", False)
s.set_actor_label("Mess_Sign")
s.set_folder_path("Mess/Lift")
for h in eas.get_all_level_actors():
    if isinstance(h, unreal.AstraHangar):
        h.set_editor_property("mess_landing", V(-2.6, D["lift"]["y"], 0.0))
        log.append("lift landing set")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
