"""ASCENSORI (docs/ASCENSORI.md): puts the lift kit into the project. Idempotent; not during PIE, after the C++ module is built:

  tools/ue.py pyfile tools/ue_scripts/build_lifts.py                              the kit, its materials and its sounds
  tools/ue.py py "TEST=True; exec(open('tools/ue_scripts/build_lifts.py').read())"   the same, and the proving ground /Game/ASTRA/Maps/L_LiftTest

What it does, in order:
  1. the sounds (tools/art/lift_sounds.py -> art/_cache/audio): SW_Lift_Hum (a loop), SW_Lift_Thump, SW_Lift_Chime, into /Game/ASTRA/Audio (the doors use SW_Door_Open / SW_Door_Close, which are there)
  2. the materials the kit's slots name: MI_LIFT_Screen (the car's screen: an instance of M_ASTRA_Screen; the game paints its texture), MI_LIFT_Lamp (the call lamp), MI_LIFT_Ring
     (the shaft's rings of light: they follow the ship's alert and dimming like the other light strips), in /Game/ASTRA/Materials/Instances
  3. the meshes (art/blender/ship_lift.py -> art/export/ship_lift): imported into /Game/ASTRA/Kit/Lift (Nanite, the glass as a plain mesh), their slots given the project's instances
  4. a report: every mesh the C++ asks for is there, its size against the kit's nominal one (FAstraLiftSpec scales a mesh to the plan's measures, so a difference is not an error, but a mesh
     that is missing or tiny is)
  With TEST: the proving ground, a level with an AAstraLiftTestRig (floors and walls round the lobbies of data/ship/test/lifts_fixture.json, the plan's lifts built in them), light, a
  PlayerStart in the lobby of Deck 1 in front of the first turbolift. Play it with the game as it is: E at a panel calls the car, E inside opens the list, W/S and the mouse choose.

The shafts, cars and landings of the ship are not placed here: UAstraLiftSubsystem builds them at the start of play from the plan (`vertical[]`, `transit[]`: docs/brief/NAVE-3.md), into the
persistent level (a line a frame, the nearest the Captain first), so that they follow the plan and cannot be left out of date in the level.
"""
import json
import math
import os

import unreal

ROOT = globals().get("ROOT", "/Users/beltromatti/Desktop/ASTRA")
TEST = globals().get("TEST", False)
KIT = "/Game/ASTRA/Kit/Lift"
MI_DIR = "/Game/ASTRA/Materials/Instances"
AUDIO = "/Game/ASTRA/Audio"
LEVEL = "/Game/ASTRA/Maps/L_LiftTest"
EXPORT = os.path.join(ROOT, "art", "export", "ship_lift")
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
log = []


def require(path, what):
    if not eal.does_asset_exist(path):
        raise RuntimeError(f"{what} is missing: {path} (run the project's material scripts first: make_materials.py, make_ui_materials.py)")


# ------------------------------------------------------------------------------------------------------------------------------------ 1. sounds
SOUNDS = ["SW_Lift_Hum", "SW_Lift_Thump", "SW_Lift_Chime"]
src_audio = os.path.join(ROOT, "art", "_cache", "audio")
missing = [n for n in SOUNDS if not os.path.exists(os.path.join(src_audio, n + ".wav"))]
if missing:
    raise RuntimeError(f"{missing} not made yet: uv run --with numpy --with soundfile --with scipy python tools/art/lift_sounds.py")
ONLY = SOUNDS
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_audio.py")).read())
hum = unreal.load_asset(f"{AUDIO}/SW_Lift_Hum")
if hum:
    hum.set_editor_property("looping", True)                      # (import_audio.py flags the project's loops by name; this one is ours)
    eal.save_loaded_asset(hum, only_if_is_dirty=False)
log.append("sounds: " + ", ".join(f"{n} {'ok' if eal.does_asset_exist(f'{AUDIO}/{n}') else 'MISSING'}" for n in SOUNDS))


# ---------------------------------------------------------------------------------------------------------------------------------- 2. materials
def mi(name, parent_path, scalars=None, vectors=None, textures=None):
    path = f"{MI_DIR}/{name}"
    inst = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant,
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


EMISSIVE = "/Game/ASTRA/Materials/M_ASTRA_Emissive"
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"
require(EMISSIVE, "the emissive master")
require(SCREEN, "the screen master")
mi("MI_LIFT_Screen", SCREEN, {"Intensity": 4.0, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0})
mi("MI_LIFT_Lamp", EMISSIVE, {"Intensity": 9.0, "AlertColorWeight": 0.0, "LightDimWeight": 0.0}, {"EmissiveColor": (1.0, 0.62, 0.18), "BaseColor": (0.3, 0.2, 0.1)})
mi("MI_LIFT_Ring", EMISSIVE, {"Intensity": 4.5, "AlertColorWeight": 1.0, "LightDimWeight": 0.5}, {"EmissiveColor": (0.45, 0.8, 1.0), "BaseColor": (0.05, 0.08, 0.12)})
for slot in ("MI_ASTRA_Panel", "MI_ASTRA_Structure", "MI_ASTRA_Floor", "MI_ASTRA_Trim", "MI_ASTRA_Light", "MI_ASTRA_Accent", "MI_ASTRA_Guide", "MI_ASTRA_Glass", "MI_ASTRA_Rubber"):
    require(f"{MI_DIR}/{slot}", "a standard material instance of the kits")
log.append("materials: MI_LIFT_Screen, MI_LIFT_Lamp, MI_LIFT_Ring")

# -------------------------------------------------------------------------------------------------------------------------------------- 3. meshes
report_path = os.path.join(EXPORT, "report.json")
if not os.path.exists(report_path):
    raise RuntimeError("the kit is not exported yet: blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_lift.py -- art/export/ship_lift")
kit = json.load(open(report_path))
SRC = EXPORT
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())

# ---------------------------------------------------------------------------------------------------------------------------------- 4. the report
problems = []
for m in kit["meshes"]:
    path = f"{KIT}/{m['name']}"
    if not eal.does_asset_exist(path):
        problems.append(f"{m['name']} did not import")
        continue
    asset = eal.load_asset(path)
    bb = asset.get_bounding_box()
    size = [round((bb.max.x - bb.min.x)) / 100.0, round((bb.max.y - bb.min.y)) / 100.0, round((bb.max.z - bb.min.z)) / 100.0]
    want = m["size_m"]
    if any(abs(a - b) > 0.06 for a, b in zip(size, want)):
        problems.append(f"{m['name']}: {size} m in the project, {want} m as Blender made it (units or axes went wrong)")
    for sm in asset.get_editor_property("static_materials"):
        mi_ = sm.get_editor_property("material_interface")
        if mi_ is None or not mi_.get_path_name().startswith(MI_DIR):
            problems.append(f"{m['name']}: slot {sm.get_editor_property('material_slot_name')} has no project instance")
log.append(f"meshes: {len(kit['meshes'])} in the kit, {len(problems)} problem(s)")
log.extend(problems)

# ----------------------------------------------------------------------------------------------------------------------------------- the test
if TEST:
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    V = unreal.Vector
    R = lambda pitch=0.0, yaw=0.0, roll=0.0: unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)
    plan = json.load(open(os.path.join(ROOT, "data", "ship", "test", "lifts_fixture.json")))
    first = next(v for v in plan["vertical"] if v.get("shaft") and v["landings"])
    shaft = first["shaft"]
    top = max(first["landings"], key=lambda l: l["z"])                                  # the highest landing (Deck 1)
    nx, ny = top["door"][0] - shaft["x"], top["door"][1] - shaft["y"]
    n = math.hypot(nx, ny) or 1.0
    nx, ny = nx / n, ny / n                                                             # from the shaft's middle to its doors: the lobby side
    if eal.does_asset_exist(LEVEL):
        les.load_level(LEVEL)
        for a in eas.get_all_level_actors():
            eas.destroy_actor(a)
    else:
        les.new_level(LEVEL)
    rig = eas.spawn_actor_from_class(unreal.AstraLiftTestRig, V(0, 0, 0), R())
    rig.set_editor_property("plan_path", "data/ship/test/lifts_fixture.json")
    rig.set_editor_property("visible", True)
    rig.set_actor_label("LiftTestRig")
    # light, a first approximation to be tuned by eye: the arena has no ceiling, so a dim sun (about 110 lux: a mid-grey floor at the corridor test's fixed exposure) reaches every lobby,
    # the project's star map fills the shadows, and the exposure is fixed so that the lobbies and the cars read the same each run
    sun = eas.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 1000), R(pitch=-52.0, yaw=35.0))
    sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    sc.set_editor_property("intensity", 110.0)
    sc.set_editor_property("use_temperature", True)
    sc.set_editor_property("temperature", 5200.0)
    sun.set_actor_label("Sun_Test")
    skyl = eas.spawn_actor_from_class(unreal.SkyLight, V(0, 0, 500), R())
    slc = skyl.get_component_by_class(unreal.SkyLightComponent)
    slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
    slc.set_editor_property("cubemap", eal.load_asset("/Game/ASTRA/Space/T_Starmap_NASA_8k"))
    slc.set_editor_property("intensity", 1.0)
    skyl.set_actor_label("SkyLight_Test")
    pp = eas.spawn_actor_from_class(unreal.PostProcessVolume, V(0, 0, 0), R())
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    for k, v in {"auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM, "auto_exposure_min_brightness": 7.2, "auto_exposure_max_brightness": 7.2,
                 "auto_exposure_bias": 0.0, "bloom_intensity": 0.35, "vignette_intensity": 0.2}.items():
        s.set_editor_property("override_" + k, True)
        s.set_editor_property(k, v)
    pp.set_editor_property("settings", s)
    pp.set_actor_label("PostProcess_Test")
    # the Captain: two and a half metres in front of the doors, looking at them
    px, py, pz = top["door"][0] + nx * 2.5, top["door"][1] + ny * 2.5, top["door"][2] + 0.12
    yaw = math.degrees(math.atan2(-ny, -nx))
    ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(px * 100, py * 100, pz * 100), R(yaw=yaw))
    ps.set_actor_label("PlayerStart_Deck1")
    ues.set_level_viewport_camera_info(V(px * 100, py * 100, (pz + 1.7) * 100), R(pitch=-4.0, yaw=yaw))
    les.save_current_level()
    log.append(f"{LEVEL}: the rig, the light and a PlayerStart at ({px:.1f}, {py:.1f}, {pz:.2f}) m facing {yaw:.0f} degrees; play it, then astra.lifts.info in the console")

print(json.dumps(log, indent=1))
