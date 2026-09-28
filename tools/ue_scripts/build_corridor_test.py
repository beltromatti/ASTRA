"""Test level L_CorridorTest: a 24.5 m run of the Aquila corridor kit with bulkhead, window onto space,
ceiling rect lights, Aurelia sun, star sky, post-process. Rebuilt from scratch each run."""
import json
import math

import unreal

LEVEL = "/Game/ASTRA/Maps/L_CorridorTest"
KIT = "/Game/ASTRA/Kit/Interior/Corridor"
eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
log = []

if eal.does_asset_exist(LEVEL):
    les.load_level(LEVEL)
    for a in eas.get_all_level_actors():
        eas.destroy_actor(a)
else:
    les.new_level(LEVEL)

V = unreal.Vector
R = lambda pitch=0.0, yaw=0.0, roll=0.0: unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)
M = 100.0  # metres -> cm


def mesh(name):
    return eal.load_asset(f"{KIT}/{name}")


def place(name, x, y=0.0, z=0.0, yaw=0.0, label=None, scale=None, folder="Corridor"):
    a = eas.spawn_actor_from_object(mesh(name), V(x * M, y * M, z * M), R(yaw=yaw))
    if scale:
        a.set_actor_scale3d(V(*scale))
    a.set_actor_label(label or name)
    a.set_folder_path(folder)
    return a


# --- corridor run along +X (kit v2: structural shells + wall panels chosen per bay)
import random  # noqa: E402

rng = random.Random(7)
BAYS = ((0.14, 1.86), (2.14, 3.86))
LOW = [("SM_COR_PanelLow_Plain", 0.6), ("SM_COR_PanelLow_Access", 0.2), ("SM_COR_PanelLow_Vent", 0.2)]
UP = [("SM_COR_PanelUp_Plain", 0.55), ("SM_COR_PanelUp_Screen", 0.25), ("SM_COR_PanelUp_Vent", 0.2)]


def pick(options):
    r, acc = rng.random(), 0.0
    for name, w in options:
        acc += w
        if r <= acc:
            return name
    return options[-1][0]


def panels(xm, window=False, tag=""):
    """Wall panels for the module starting at xm (m). UE -Y wall: yaw 0; UE +Y wall: yaw 180 (origin at bay end)."""
    for side in (-1, 1):
        for bi, (b0, b1) in enumerate(BAYS):
            if window and side == -1:
                items = [("SM_COR_PanelLowShort_Plain", 0.22)]
            else:
                items = [(pick(LOW), 0.22), (pick(UP), 1.32)]
            for name, z in items:
                if side == -1:
                    place(name, xm + b0, y=-1.6, z=z, label=f"{tag}_P{bi}_{name[7:]}_{'L' if side < 0 else 'R'}", folder="Corridor/Panels")
                else:
                    place(name, xm + b1, y=1.6, z=z, yaw=180.0, label=f"{tag}_P{bi}_{name[7:]}_R", folder="Corridor/Panels")


place("SM_COR_EndCap", 0.0, yaw=180.0, label="EndCap_A")
for i, x in enumerate((0.0, 4.0, 8.0)):
    place("SM_COR_Shell_4m", x, label=f"Shell_{i}")
    panels(x, tag=f"M{i}")
place("SM_COR_Bulkhead", 12.0, label="Bulkhead_0")
place("SM_COR_DoorLeaf", 12.25, y=-0.66, label="DoorLeaf_L")            # open: slid into the wall
place("SM_COR_DoorLeaf", 12.25, y=0.66, label="DoorLeaf_R", scale=(1, -1, 1))
place("SM_COR_ShellWindow_4m", 12.5, label="ShellWindow_0")
panels(12.5, window=True, tag="W0")
place("SM_COR_WindowGlass", 12.5, label="WindowGlass_0")
for i, x in enumerate((16.5, 20.5)):
    place("SM_COR_Shell_4m", x, label=f"Shell_{i + 3}")
    panels(x, tag=f"M{i + 3}")
place("SM_COR_EndCap", 24.5, label="EndCap_B")

# --- ceiling lights: one rect light per 4 m module (two strips each), shadowed
light_x = [2.0, 6.0, 10.0, 14.5, 18.5, 22.5]
for i, x in enumerate(light_x):
    a = eas.spawn_actor_from_class(unreal.RectLight, V(x * M, 0, 2.90 * M), R(pitch=-90.0))
    c = a.get_component_by_class(unreal.RectLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", 5000.0)
    c.set_editor_property("source_width", 340.0)
    c.set_editor_property("source_height", 14.0)
    c.set_editor_property("barn_door_angle", 80.0)
    c.set_editor_property("barn_door_length", 6.0)
    c.set_editor_property("attenuation_radius", 900.0)
    c.set_editor_property("use_temperature", True)
    c.set_editor_property("temperature", 4800.0)
    c.set_editor_property("cast_shadows", True)
    a.set_actor_label(f"CeilingLight_{i}")
    a.set_folder_path("Lighting")
    # rect lights emit along +X of the actor; with pitch -90 they face down; rotate the long side along the corridor
    a.set_actor_rotation(R(pitch=-90.0, yaw=0.0, roll=90.0), False)

# --- Aurelia (K-type star) entering through the window on the -Y side
fwd = V(0.25, 0.80, -0.45)
yaw = math.degrees(math.atan2(fwd.y, fwd.x))
pitch = math.degrees(math.asin(fwd.z / math.sqrt(fwd.x ** 2 + fwd.y ** 2 + fwd.z ** 2)))
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 1000), R(pitch=pitch, yaw=yaw))
sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
sc.set_editor_property("intensity", 2500.0)
sc.set_editor_property("use_temperature", True)
sc.set_editor_property("temperature", 4300.0)
sc.set_editor_property("light_source_angle", 0.35)
sun.set_actor_label("Sun_Aurelia")
sun.set_folder_path("Lighting")

# --- star sky
sky_mesh = eal.load_asset("/Engine/EngineSky/SM_SkySphere") or eal.load_asset("/Engine/BasicShapes/Sphere")
sky = eas.spawn_actor_from_object(sky_mesh, V(0, 0, 0), R())
sky.set_actor_scale3d(V(400, 400, 400))
smc = sky.get_component_by_class(unreal.StaticMeshComponent)
smc.set_material(0, eal.load_asset("/Game/ASTRA/Space/M_ASTRA_SpaceSky"))
smc.set_editor_property("cast_shadow", False)
smc.set_editor_property("affect_distance_field_lighting", False)
smc.set_editor_property("affect_dynamic_indirect_lighting", False)
smc.set_editor_property("bounds_scale", 100.0)      # the material recentres the sphere on the camera: never cull it
smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
sky.set_actor_label("SpaceSky")
sky.set_folder_path("Space")

skyl = eas.spawn_actor_from_class(unreal.SkyLight, V(0, 0, 500), R())
slc = skyl.get_component_by_class(unreal.SkyLightComponent)
slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
slc.set_editor_property("cubemap", eal.load_asset("/Game/ASTRA/Space/T_Starmap_NASA_8k"))
slc.set_editor_property("intensity", 1.0)
skyl.set_actor_label("SkyLight_Space")
skyl.set_folder_path("Space")

# --- post process (unbound)
pp = eas.spawn_actor_from_class(unreal.PostProcessVolume, V(0, 0, 0), R())
pp.set_editor_property("unbound", True)
s = pp.get_editor_property("settings")
for k, v in {
    "auto_exposure_method": unreal.AutoExposureMethod.AEM_HISTOGRAM,
    "auto_exposure_min_brightness": 7.2,
    "auto_exposure_max_brightness": 7.2,
    "auto_exposure_bias": 0.0,
    "bloom_intensity": 0.35,
    "vignette_intensity": 0.25,
    "film_grain_intensity": 0.04,
    "scene_fringe_intensity": 0.0,
}.items():
    s.set_editor_property("override_" + k, True)
    s.set_editor_property(k, v)
pp.set_editor_property("settings", s)
pp.set_actor_label("PostProcess_Global")
pp.set_folder_path("Lighting")

ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(2.0 * M, 0, 1.0 * M), R())
ps.set_folder_path("Gameplay")

# viewport camera for captures: eye height 1.7 m, looking down the corridor towards the window
ues.set_level_viewport_camera_info(V(1.0 * M, 0.6 * M, 1.7 * M), R(pitch=-3.0, yaw=-4.0))
les.save_current_level()
log.append(f"actors: {len(eas.get_all_level_actors())}")
print(json.dumps(log))
