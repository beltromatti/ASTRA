"""Builds the Medbay (Deck 6 · Section C) into the bridge level, from data/ship/aquila_medbay.json: the cloth textures and
the medical screens, the materials, the kit (art/export/medbay, art/blender/medbay.py), the ward and its twelve beds,
a patient actor in every bed (AAstraPatient: the ship fills them from the roster), Dr. Lindqvist and two medics, the
lights (tagged ASTRA.Zone.Medbay: on only while the Captain is there), the lift's doors and sign, and the lift's
fourth landing. Also gives Main Engineering its own room sign. Idempotent: the "Medbay" folder is replaced. Not during
PIE, after the C++ module that has AAstraPatient is built:
  tools/ue.py pyfile tools/ue_scripts/build_medbay.py
"""
import json
import os
import sys

import unreal

# the actors go into L_Bridge's own persistent level, whatever level the editor had current: after build_ship_interior.py it was a deck's streamed
# sub-level, and the five existing rooms were saved into L_Deck12, which the game never loads around them (3 Oct: the Mess Hall was not there)
if unreal.EditorLevelLibrary.get_editor_world().get_outermost().get_name() != "/Game/ASTRA/Maps/L_Bridge":
    unreal.EditorLoadingAndSavingUtils.load_map("/Game/ASTRA/Maps/L_Bridge")
if not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).set_current_level_by_name("L_Bridge"):
    raise RuntimeError("L_Bridge cannot be made the current level")

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Medbay"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
UI_TEX = "/Game/ASTRA/UI/Textures"
SIGN_TEX = "/Game/ASTRA/UI/Signage"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_medbay.json")))
OX, OY, OZ = D["world_origin"]
ZONE = "ASTRA.Zone.Medbay"
BEDS = D["beds"]
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
        if n.endswith("_N"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
        elif n.endswith("_ORM"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        else:
            tx.set_editor_property("srgb", True)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tx, only_if_is_dirty=False)


# ---- textures: the cloth (ambientCG, tools/art/pack_textures.py), the screens (tools/art/ui_screens.py med), the signs
import_png(os.path.join(ROOT, "art", "_cache", "textures"), [f"T_{s}_{k}" for s in ("Linen", "Cotton") for k in ("BC", "N", "ORM")], TEX)
import_png(os.path.join(ROOT, "art", "_cache", "ui"), ["T_UI_Med_Vitals", "T_UI_Med_VitalsCritical", "T_UI_Med_Standby", "T_UI_Med_Ward",
                                                       "T_UI_Med_Scan"], UI_TEX)
import_png(os.path.join(ROOT, "art", "_cache", "signage"), ["T_SIGN_Room_Medbay", "T_SIGN_Room_Engineering", "T_SIGN_Lift_Bridge",
                                                             "T_SIGN_Lift_Hangar"], SIGN_TEX)
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


# a clean, pale clinic inside a warship: soft white panels, a satin blue-grey deck, white linen, navy-blue blankets,
# sea-green curtains; the medical cross glows green
hard("MI_MED_Wall", (0.66, 0.7, 0.72), (0.32, 0.46))
hard("MI_MED_Floor", (0.25, 0.3, 0.33), (0.2, 0.36), normal=0.25, macro=0.1)
hard("MI_MED_Plastic", (0.75, 0.77, 0.78), (0.28, 0.4), normal=0.2)
hard("MI_MED_Red", (0.42, 0.03, 0.025), (0.3, 0.42), normal=0.2)
hard("MI_MED_Linen", (0.8, 0.82, 0.84), (0.72, 0.9), tex="Cotton", uv=3.0, normal=0.7, influence=0.4, macro=0.03)
hard("MI_MED_Blanket", (0.1, 0.16, 0.27), (0.8, 0.95), tex="Linen", uv=2.5, normal=0.9, influence=0.5, macro=0.04)
hard("MI_MED_Curtain", (0.26, 0.45, 0.44), (0.75, 0.9), tex="Linen", uv=4.0, normal=0.6, influence=0.4, macro=0.04)
mi("MI_MED_Cross", "/Game/ASTRA/Materials/M_ASTRA_Emissive", {"Intensity": 9.0, "PulseSpeed": 0.0, "PulseAmount": 0.0,
                                                               "AlertColorWeight": 0.0, "LightDimWeight": 0.0}, {"EmissiveColor": (0.1, 0.95, 0.6)})
for name, tex, inten in (("MI_MED_ScreenStandby", "T_UI_Med_Standby", 6.0), ("MI_MED_Vitals", "T_UI_Med_Vitals", 18.0),
                         ("MI_MED_VitalsCritical", "T_UI_Med_VitalsCritical", 18.0), ("MI_MED_Ward", "T_UI_Med_Ward", 16.0),
                         ("MI_MED_Scan", "T_UI_Med_Scan", 16.0)):
    mi(name, SCREEN, {"Intensity": inten, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, None, {"ScreenTexture": f"{UI_TEX}/{tex}"})
for name in ("Room_Medbay", "Room_Engineering"):
    mi(f"MI_SIGN_{name}", SCREEN, {"Intensity": 8.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, None,
       {"ScreenTexture": f"{SIGN_TEX}/T_SIGN_{name}"})
log.append("materials")

# materials assigned at run time to Nanite meshes (a patient's monitor turning critical) need the Nanite usage
for base in ("M_ASTRA_Screen", "M_ASTRA_Hard", "M_ASTRA_Emissive"):
    m = eal.load_asset(f"/Game/ASTRA/Materials/{base}")
    if not m.get_editor_property("used_with_nanite"):
        mel.set_material_usage(m, unreal.MaterialUsage.MATUSAGE_NANITE)
        eal.save_loaded_asset(m, only_if_is_dirty=False)
        log.append(f"{base}: Nanite usage")

# the finishes of the rooms (the ward of ARTE-INTERNI uses them: tile, plaster, steel, the swatch palette): created when they are missing
if ROOT + "/tools/ue_scripts" not in sys.path:
    sys.path.insert(0, ROOT + "/tools/ue_scripts")
import ship_room_materials as RM
RM.build(log)

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Medbay"):
        eas.destroy_actor(a)
# a fresh import (a reimport keeps material slots the new FBX no longer has: a stale translucent slot makes Nanite
# refuse the whole mesh and draw its coarse fallback)
for path in eal.list_assets(KIT, recursive=False, include_folder=False):
    if not eal.delete_asset(path):
        log.append(f"could not delete {path}")

SRC = os.path.join(ROOT, "art", "export", "medbay")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def place(path, x, y, z, yaw=0.0, label=None, folder="Medbay"):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    return a


place(f"{KIT}/SM_MED_Ward", 0, 0, 0, label="Medbay_Ward")
g = place(f"{KIT}/SM_MED_Glass", 0, 0, 0, label="Medbay_Glass")
g.static_mesh_component.set_editor_property("cast_shadow", False)

# ---- the beds and their patients: bed k (1-12), the port row forward to aft, then the starboard row; +X to the wall
k = 0
for side in (-1, 1):
    for x in BEDS["x"]:
        k += 1
        yaw = 90.0 * side
        place(f"{KIT}/SM_MED_Bed", x, side * BEDS["hinge_y"], 0.0, yaw, label=f"Medbay_Bed{k:02d}", folder="Medbay/Beds")
        p = eas.spawn_actor_from_class(unreal.AstraPatient, V(x, side * BEDS["hinge_y"], BEDS["mattress_top"]),
                                       unreal.Rotator(roll=0, pitch=0, yaw=yaw))
        p.set_editor_property("station_id", f"patient{k}")
        p.set_editor_property("posture", unreal.AstraCrewPosture.LYING)
        p.set_editor_property("recline_deg", BEDS["recline_deg"])
        p.set_actor_label(f"Medbay_Patient{k:02d}")
        p.set_folder_path("Medbay/Patients")
log.append(f"{k} beds")

# ---- the medical staff on watch
for c in D["crew"]:
    a = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(c["x"], c["y"], 0.0), unreal.Rotator(roll=0, pitch=0, yaw=c["yaw"] - 90.0))
    a.set_editor_property("posture", unreal.AstraCrewPosture.STANDING)
    a.set_editor_property("station_id", c["station"])
    a.set_editor_property("display_name", c.get("name", ""))
    a.set_editor_property("female_body", bool(c.get("female")))
    a.set_actor_label(f"Medbay_{c['station']}")
    a.set_folder_path("Medbay/Crew")
log.append("staff")


# ---- light: clean clinical white over the beds and the aisle, the theatre's bright field and its lamp; all off until
#      the Captain comes down
def light(cls, x, y, z, label, intensity, color, radius, shadows=False, pitch=-90.0, yaw=0.0, size=None, cone=None):
    a = eas.spawn_actor_from_class(cls, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    c = a.get_component_by_class(unreal.LocalLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", intensity)
    c.set_editor_property("attenuation_radius", radius)
    c.set_editor_property("light_color", unreal.Color(r=color[0], g=color[1], b=color[2], a=255))
    c.set_editor_property("cast_shadows", shadows)
    if size and isinstance(c, unreal.RectLightComponent):
        c.set_editor_property("source_width", size[0] * M)
        c.set_editor_property("source_height", size[1] * M)
    if cone and isinstance(c, unreal.SpotLightComponent):
        c.set_editor_property("outer_cone_angle", cone[0])
        c.set_editor_property("inner_cone_angle", cone[1])
    a.set_actor_label(label)
    a.set_folder_path("Medbay/Lighting")
    a.tags = [ZONE]
    return a


H = D["height"]
WHITE = (242, 246, 255)
# few, long sources (a rect light per three beds, per half of each aisle row): measured in the game at 1080p the ward's
# light cost fell from ~11 ms (32 lights, 10 with shadows) to budget; three cast shadows
bx = BEDS["x"]
for side in (-1, 1):
    for i, group in enumerate((bx[:3], bx[3:])):
        cx = sum(group) / 3.0
        light(unreal.RectLight, cx, side * 7.3, H - 0.06, f"Medbay_BedLights_{'P' if side < 0 else 'S'}{i + 1}", 7800, WHITE, 900,
              size=(7.2, 0.9))
for i, (x0, x1) in enumerate(((-0.8, -11.2), (-11.2, -23.3))):
    for yy in (-3.2, 3.2):
        shadowed = (i == 0) == (yy < 0)            # one per row, alternating: soft shadows under the beds and people
        light(unreal.RectLight, (x0 + x1) / 2, yy, H - 0.06, f"Medbay_Aisle_{i}_{'P' if yy < 0 else 'S'}", 8800, WHITE, 1100,
              shadows=shadowed, size=(abs(x1 - x0) - 1.0, 0.6))
tx, ty = D["surgery"]["table"]
light(unreal.RectLight, tx, ty, H - 0.08, "Medbay_TheatreField", 9000, (248, 250, 255), 900, size=(2.8, 3.2))
light(unreal.SpotLight, tx + 0.1, ty + 0.05, 2.0, "Medbay_TheatreLamp", 9000, (255, 250, 240), 500, shadows=True, cone=(28.0, 14.0))
light(unreal.PointLight, -0.8, 5.0, 2.2, "Medbay_BoardGlow", 600, (120, 200, 255), 500)
log.append("lights")

# ---- the lift: doors and sign on the forward wall; the landing on the lift network
leaf = eal.load_asset("/Game/ASTRA/Kit/Interior/Corridor/SM_COR_DoorLeaf")
plate = eal.load_asset("/Game/ASTRA/Kit/Signage/SM_SIGN_Plate")
for n, sy in ((0, 1.0), (1, -1.0)):
    a = eas.spawn_actor_from_object(leaf, V(0.12, D["lift"]["y"], 0.0), unreal.Rotator())
    a.set_actor_scale3d(unreal.Vector(1.0, sy, 1.05))
    a.set_actor_label(f"Lift_Medbay_Leaf{n}")
    a.set_folder_path("Medbay/Lift")


def room_sign(x, y, z, label, folder, mat):
    s = eas.spawn_actor_from_object(plate, V(x, y, z), unreal.Rotator(roll=0, pitch=0, yaw=180.0))
    s.set_actor_scale3d(unreal.Vector(1.0, 2.2, 0.55))
    smc = s.get_component_by_class(unreal.StaticMeshComponent)
    for i, sm in enumerate(plate.get_editor_property("static_materials")):
        if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
            smc.set_material(i, eal.load_asset(f"{MI_DIR}/{mat}"))
    smc.set_editor_property("cast_shadow", False)
    s.set_actor_label(label)
    s.set_folder_path(folder)
    return s


room_sign(-0.3, D["lift"]["y"], D["lift"]["height"] + 0.9, "Medbay_Sign", "Medbay/Lift", "MI_SIGN_Room_Medbay")
for a in eas.get_all_level_actors():
    if a.get_actor_label() == "Engineering_Sign":   # Main Engineering's own name over its door (it borrowed a bridge plate)
        smc = a.get_component_by_class(unreal.StaticMeshComponent)
        for i, sm in enumerate(plate.get_editor_property("static_materials")):
            if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
                smc.set_material(i, eal.load_asset(f"{MI_DIR}/MI_SIGN_Room_Engineering"))
        log.append("engineering sign")
for h in eas.get_all_level_actors():
    if isinstance(h, unreal.AstraHangar):
        h.set_editor_property("medbay_landing", V(-2.6, D["lift"]["y"], 0.0))
        log.append("lift landing set")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
