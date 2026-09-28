"""Level L_Bridge: the ASN Aquila bridge assembled from data/ship/aquila_bridge.json (single source of truth).
Unreal convention = data convention (X forward, Y starboard, Z up); data in metres, Unreal in cm."""
import json
import math

import unreal

LEVEL = "/Game/ASTRA/Maps/L_Bridge"
KIT = "/Game/ASTRA/Kit/Bridge"
DATA = json.load(open("/Users/beltromatti/Desktop/ASTRA/data/ship/aquila_bridge.json", encoding="utf-8"))
eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V = unreal.Vector
M = 100.0
log = []


def R(pitch=0.0, yaw=0.0, roll=0.0):
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


if eal.does_asset_exist(LEVEL):
    les.load_level(LEVEL)
    for a in eas.get_all_level_actors():
        eas.destroy_actor(a)
else:
    les.new_level(LEVEL)


def place(mesh, x, y, z=0.0, yaw=0.0, label=None, folder="Bridge"):
    a = eas.spawn_actor_from_object(eal.load_asset(f"{KIT}/{mesh}"), V(x * M, y * M, z * M), R(yaw=yaw))
    a.set_actor_label(label or mesh)
    a.set_folder_path(folder)
    return a


level_z = DATA["levels"]
place("SM_BRG_Shell", 0, 0, label="Bridge_Shell")
place("SM_BRG_WindowGlass", 0, 0, label="Bridge_WindowGlass")
place("SM_BRG_Railing", 0, 0, label="Bridge_Railings")
ht = DATA["holo_table"]
place("SM_BRG_HoloTable", ht["pos"][0], ht["pos"][1], 0.0, label="HoloTable")
md = DATA["master_display"]
place("SM_BRG_MasterDisplay", md["pos"][0], md["pos"][1], 0.0, label="MasterDisplay")

for st in DATA["stations"]:
    x, y = st["pos"]
    z = level_z[st["level"]]
    yaw = st["yaw"]
    kind = st["kind"]
    lab = st["id"]
    if kind == "captain_chair":
        place("SM_BRG_ChairCaptain", x, y, z, yaw, label=f"Station_{lab}_Chair", folder="Bridge/Stations")
    elif kind == "xo_chair":
        place("SM_BRG_ChairCrew", x, y, z, yaw, label=f"Station_{lab}_Chair", folder="Bridge/Stations")
    elif kind == "tactical_rail":
        place("SM_BRG_TacticalRail", x, y, z, yaw, label=f"Station_{lab}_Rail", folder="Bridge/Stations")
    elif kind == "console_seated":
        place("SM_BRG_ConsoleSeated", x, y, z, yaw, label=f"Station_{lab}_Console", folder="Bridge/Stations")
        place("SM_BRG_ChairCrew", x, y, z, yaw, label=f"Station_{lab}_Chair", folder="Bridge/Stations")

# --- lights: dome downlight + rect lights along the ceiling beams + holo glow (no shadows) + station spots
def rect(x, y, z, w, h, lumens, temp, label, shadows=True, pitch=-90.0, yaw=0.0):
    a = eas.spawn_actor_from_class(unreal.RectLight, V(x * M, y * M, z * M), R(pitch=pitch, yaw=yaw))
    c = a.get_component_by_class(unreal.RectLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", lumens)
    c.set_editor_property("source_width", w * M)
    c.set_editor_property("source_height", h * M)
    c.set_editor_property("attenuation_radius", 1500.0)
    c.set_editor_property("use_temperature", True)
    c.set_editor_property("temperature", temp)
    c.set_editor_property("cast_shadows", shadows)
    a.set_actor_label(label)
    a.set_folder_path("Lighting")
    return a


dc = DATA["ceiling"]["dome_center"]
rect(dc[0], dc[1], DATA["ceiling"]["dome_height"] - 0.05, 2.0, 2.0, 9000, 5200, "Dome_Downlight")
for i, (x, y) in enumerate(((0.0, 0.0), (5.6, 0.0), (0.5, -5.8), (0.5, 5.8), (-3.0, -5.6), (-3.0, 5.6))):
    rect(x, y, DATA["ceiling"]["height"] - 0.36, 1.6, 0.4, 3500, 4800, f"Ceiling_{i}", shadows=(i < 2))

pl = eas.spawn_actor_from_class(unreal.PointLight, V(ht["pos"][0] * M, ht["pos"][1] * M, (ht["height"] + 0.35) * M), R())
plc = pl.get_component_by_class(unreal.PointLightComponent)
plc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
plc.set_editor_property("intensity", 1200.0)
plc.set_editor_property("light_color", unreal.Color(r=110, g=190, b=255, a=255))
plc.set_editor_property("attenuation_radius", 450.0)
plc.set_editor_property("cast_shadows", False)
pl.set_actor_label("HoloTable_Glow")
pl.set_folder_path("Lighting")

# --- space: Aurelia sun ahead-left of the bow, stars
fwd = V(-0.55, 0.35, -0.25)
yaw = math.degrees(math.atan2(fwd.y, fwd.x))
pitch = math.degrees(math.asin(fwd.z / math.sqrt(fwd.x ** 2 + fwd.y ** 2 + fwd.z ** 2)))
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 1500), R(pitch=pitch, yaw=yaw))
sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
sc.set_editor_property("intensity", 2500.0)
sc.set_editor_property("use_temperature", True)
sc.set_editor_property("temperature", 4300.0)
sc.set_editor_property("light_source_angle", 0.35)
sun.set_actor_label("Sun_Aurelia")
sun.set_folder_path("Lighting")

sky = eas.spawn_actor_from_object(eal.load_asset("/Engine/EngineSky/SM_SkySphere") or eal.load_asset("/Engine/BasicShapes/Sphere"), V(0, 0, 0), R())
sky.set_actor_scale3d(V(400, 400, 400))
smc = sky.get_component_by_class(unreal.StaticMeshComponent)
smc.set_material(0, eal.load_asset("/Game/ASTRA/Space/M_ASTRA_SpaceSky"))
smc.set_editor_property("cast_shadow", False)
smc.set_editor_property("affect_distance_field_lighting", False)
smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
sky.set_actor_label("SpaceSky")
sky.set_folder_path("Space")

pp = eas.spawn_actor_from_class(unreal.PostProcessVolume, V(0, 0, 0), R())
pp.set_editor_property("unbound", True)
s = pp.get_editor_property("settings")
for k, v in {"auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM,
             "auto_exposure_min_brightness": 6.6, "auto_exposure_max_brightness": 6.6,
             "bloom_intensity": 0.4, "vignette_intensity": 0.3, "film_grain_intensity": 0.0}.items():
    s.set_editor_property("override_" + k, True)
    s.set_editor_property(k, v)
pp.set_editor_property("settings", s)
pp.set_actor_label("PostProcess_Bridge")
pp.set_folder_path("Lighting")

ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(-1.0 * M, 0.9 * M, 1.0 * M), R())
ps.set_folder_path("Gameplay")
unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
    V(-7.2 * M, -1.2 * M, 1.75 * M), R(pitch=-4.0, yaw=4.0))
les.save_current_level()
log.append(f"actors: {len(eas.get_all_level_actors())}")
print(json.dumps(log))
