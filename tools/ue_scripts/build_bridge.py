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
    path = mesh if mesh.startswith("/Game/") else f"{KIT}/{mesh}"
    asset = eal.load_asset(path)
    if asset is None:
        raise RuntimeError(f"missing asset {path}")
    a = eas.spawn_actor_from_object(asset, V(x * M, y * M, z * M), R(yaw=yaw))
    a.set_actor_label(label or mesh)
    a.set_folder_path(folder)
    return a


level_z = DATA["levels"]
place("SM_BRG_Shell", 0, 0, label="Bridge_Shell")
place("SM_BRG_WindowGlass", 0, 0, label="Bridge_WindowGlass")
place("SM_BRG_Railing", 0, 0, label="Bridge_Railings")
ht = DATA["holo_table"]
place("SM_BRG_HoloTable", ht["pos"][0], ht["pos"][1], 0.0, label="HoloTable")
# the live tactical plot above the table (AAstraHoloTable, C++): origin on the table top, +X towards the bow
plot = eas.spawn_actor_from_class(unreal.AstraHoloTable, V(ht["pos"][0] * M, ht["pos"][1] * M, (ht["height"] + 0.01) * M), R())
plot.set_actor_label("HoloTable_Plot")
plot.set_folder_path("Bridge")
# sliding pressure doors in the back wall (AAstraDoor: they open when you come near, into the wall)
for d in DATA["doors"]:
    dx, dy = d["pos"]
    door = eas.spawn_actor_from_class(unreal.AstraDoor, V((dx - 0.15) * M, dy * M, 0.0), R())
    door.set_editor_property("width", d["width"] * M)
    door.set_editor_property("height", d["height"] * M)
    door.set_actor_label(f"Door_{d['id']}")
    door.set_folder_path("Bridge/Doors")

# --- corridors behind the doors: 12 m runs of the corridor kit going aft, a window module on the hull side
import random  # noqa: E402

CK = "/Game/ASTRA/Kit/Interior/Corridor"
WALL_T = 0.3                      # bridge back wall thickness (art/blender/bridge.py)
X_END = DATA["walls"]["back_x"] - WALL_T
BAYS = ((0.14, 1.86), (2.14, 3.86))
LOW = [("SM_COR_PanelLow_Plain", 0.6), ("SM_COR_PanelLow_Access", 0.2), ("SM_COR_PanelLow_Vent", 0.2)]
UP = [("SM_COR_PanelUp_Plain", 0.55), ("SM_COR_PanelUp_Screen", 0.25), ("SM_COR_PanelUp_Vent", 0.2)]
crng = random.Random(11)


def pick(options):
    r, acc = crng.random(), 0.0
    for name, w in options:
        acc += w
        if r <= acc:
            return name
    return options[-1][0]


def corridor_panels(xm, yc, window_side, tag):
    for side in (-1, 1):
        for bi, (b0, b1) in enumerate(BAYS):
            items = [("SM_COR_PanelLowShort_Plain", 0.22)] if window_side == side else [(pick(LOW), 0.22), (pick(UP), 1.32)]
            for name, z in items:
                if side == -1:
                    place(f"{CK}/{name}", xm + b0, yc - 1.6, z, 0.0, label=f"{tag}_{bi}_{name[7:]}_L", folder="Corridors/Panels")
                else:
                    place(f"{CK}/{name}", xm + b1, yc + 1.6, z, 180.0, label=f"{tag}_{bi}_{name[7:]}_R", folder="Corridors/Panels")


for d in DATA["doors"]:
    yc = d["pos"][1]
    outer = -1 if yc < 0 else 1           # the hull side of this corridor (windows)
    tag = "Port" if yc < 0 else "Stbd"
    mods = [X_END - 12.0, X_END - 8.0, X_END - 4.0]
    for i, xm in enumerate(mods):
        if i == 1:
            # window module: the kit's window is on its -Y side; rotated for the starboard corridor
            if outer < 0:
                place(f"{CK}/SM_COR_ShellWindow_4m", xm, yc, 0.0, 0.0, label=f"Corr{tag}_Window", folder="Corridors")
                place(f"{CK}/SM_COR_WindowGlass", xm, yc, 0.0, 0.0, label=f"Corr{tag}_Glass", folder="Corridors")
            else:
                place(f"{CK}/SM_COR_ShellWindow_4m", xm + 4.0, yc, 0.0, 180.0, label=f"Corr{tag}_Window", folder="Corridors")
                place(f"{CK}/SM_COR_WindowGlass", xm + 4.0, yc, 0.0, 180.0, label=f"Corr{tag}_Glass", folder="Corridors")
            corridor_panels(xm, yc, outer, f"Corr{tag}{i}")
        else:
            place(f"{CK}/SM_COR_Shell_4m", xm, yc, 0.0, 0.0, label=f"Corr{tag}_Shell{i}", folder="Corridors")
            corridor_panels(xm, yc, None, f"Corr{tag}{i}")
        lt = eas.spawn_actor_from_class(unreal.RectLight, V((xm + 2.0) * M, yc * M, 2.9 * M), R(pitch=-90.0))
        lc = lt.get_component_by_class(unreal.RectLightComponent)
        lc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
        lc.set_editor_property("intensity", 3500.0)
        lc.set_editor_property("source_width", 340.0)
        lc.set_editor_property("source_height", 14.0)
        lc.set_editor_property("attenuation_radius", 800.0)
        lc.set_editor_property("use_temperature", True)
        lc.set_editor_property("temperature", 4800.0)
        lc.set_editor_property("cast_shadows", False)
        lt.set_actor_rotation(R(pitch=-90.0, yaw=0.0, roll=90.0), False)
        lt.set_actor_label(f"Corr{tag}_Light{i}")
        lt.set_folder_path("Lighting")
        lt.tags = [unreal.Name("ASTRA.ShipLight")]
    if yc > 0:
        # the starboard corridor ends at the Captain's quarters: a bulkhead and a door (tools/ue_scripts/build_quarters.py
        # builds the cabin and places them again)
        place(f"{CK}/SM_COR_Bulkhead", mods[0], yc, 0.0, 180.0, label="Quarters_Bulkhead", folder="Quarters/Door")
        qd = eas.spawn_actor_from_class(unreal.AstraDoor, V((mods[0] - 0.25) * M, yc * M, 0.0), R())
        qd.set_editor_property("width", 140.0)
        qd.set_editor_property("height", 230.0)
        qd.set_actor_label("Door_Quarters")
        qd.set_folder_path("Quarters/Door")
    else:
        place(f"{CK}/SM_COR_EndCap", mods[0], yc, 0.0, 180.0, label=f"Corr{tag}_EndCap", folder="Corridors")
# the Aquila herself around the bridge: the hull frame's origin is 172 m aft and 62 m below the bridge floor
# (BridgeOffset in AstraBattleSubsystem.h); no shadows (a 780 m hull would shade the bridge unpredictably)
hull = place("/Game/ASTRA/Ships/SM_SHIP_ASTRA_Aquila", -172.0, 0.0, -62.0, 0.0, label="Aquila_Hull", folder="Ship")
hc = hull.get_component_by_class(unreal.StaticMeshComponent)
hc.set_editor_property("cast_shadow", False)
hc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
hc.set_editor_property("affect_distance_field_lighting", False)   # its coarse distance field would leak into the bridge
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
        con = place("SM_BRG_ConsoleSeated", x, y, z, yaw, label=f"Station_{lab}_Console", folder="Bridge/Stations")
        prefix = {"helm": "Helm", "ops": "Ops", "comms": "Comms", "sensors": "Sensors", "engineering": "Eng", "flight": "Flight"}[lab]
        smc_c = con.get_component_by_class(unreal.StaticMeshComponent)
        for slot in ("A", "B", "C", "Touch"):
            smc_c.set_material_by_name(f"MI_ASTRA_Screen{slot}", eal.load_asset(f"/Game/ASTRA/UI/Materials/MI_UI_{prefix}_{slot}"))
        place("SM_BRG_ChairCrew", x, y, z, yaw, label=f"Station_{lab}_Chair", folder="Bridge/Stations")

# --- bridge crew (placeholder bodies until the MetaHuman crew); the station id is the mind's `speaker`
CREW = {"xo": "Cmdr. Elena Serra", "helm": "Lt. Marco Ferri", "ops": "Lt. Yuki Tanaka", "tactical": "Lt. Cmdr. Sara Voss",
        "comms": "Ens. Leo Martin", "sensors": "Lt. Priya Nair", "engineering": "Lt. (j.g.) Kofi Mensah", "flight": "Lt. Jonah Price"}
for st in DATA["stations"]:
    sid = st["id"]
    if sid not in CREW:
        continue
    x, y = st["pos"]
    z = level_z[st["level"]]
    yaw = st["yaw"]
    if st["kind"] == "tactical_rail":
        # standing at the rail (idle animation): the mannequin faces its +Y, hence yaw - 90
        c = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x * M, y * M, z * M), R(yaw=yaw - 90.0))
        c.set_editor_property("posture", unreal.AstraCrewPosture.STANDING)
    else:
        # seated on the station's chair (procedural pose, faces the actor's +X)
        c = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x * M, y * M, z * M), R(yaw=yaw))
        c.set_editor_property("posture", unreal.AstraCrewPosture.SEATED_CONSOLE if st["kind"] == "console_seated"
                              else unreal.AstraCrewPosture.SEATED_ARMCHAIR)
    c.set_editor_property("station_id", sid)
    c.set_editor_property("display_name", CREW[sid])
    c.set_actor_label(f"Crew_{sid}")
    c.set_folder_path("Bridge/Crew")

# --- lights: dome downlight + rect lights along the ceiling beams + holo glow (no shadows) + station spots
def rect(x, y, z, w, h, lumens, temp, label, shadows=True, pitch=-90.0, yaw=0.0, radius=1500.0):
    a = eas.spawn_actor_from_class(unreal.RectLight, V(x * M, y * M, z * M), R(pitch=pitch, yaw=yaw))
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
    a.set_folder_path("Lighting")
    a.set_editor_property("tags", ["ASTRA.ShipLight"])
    return a


dc = DATA["ceiling"]["dome_center"]
rect(dc[0], dc[1], DATA["ceiling"]["dome_height"] - 0.05, 2.0, 2.0, 9000, 5200, "Dome_Downlight", shadows=False)  # perf: behind the Captain
for i, (x, y) in enumerate(((0.0, 0.0), (5.6, 0.0), (0.5, -5.8), (0.5, 5.8), (-3.0, -5.6), (-3.0, 5.6))):
    rect(x, y, DATA["ceiling"]["height"] - 0.36, 1.6, 0.4, 3500, 4800, f"Ceiling_{i}", shadows=(i < 2), radius=1500.0 if i < 2 else 1000.0)

pl = eas.spawn_actor_from_class(unreal.PointLight, V(ht["pos"][0] * M, ht["pos"][1] * M, (ht["height"] + 0.35) * M), R())
plc = pl.get_component_by_class(unreal.PointLightComponent)
plc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
plc.set_editor_property("intensity", 350.0)      # the plot itself glows; a strong light only made a hot spot on the top
plc.set_editor_property("light_color", unreal.Color(r=110, g=190, b=255, a=255))
plc.set_editor_property("attenuation_radius", 450.0)
plc.set_editor_property("cast_shadows", False)
plc.set_editor_property("specular_scale", 0.0)   # glow on the room, no hot spot mirrored in the table top
pl.set_actor_label("HoloTable_Glow")
pl.set_folder_path("Lighting")

# --- space: Aurelia sun ahead-left of the bow, stars
fwd = V(-0.5, -0.6, -0.45)          # light travels from the star (ahead, starboard, high) into the ship
yaw = math.degrees(math.atan2(fwd.y, fwd.x))
pitch = math.degrees(math.asin(fwd.z / math.sqrt(fwd.x ** 2 + fwd.y ** 2 + fwd.z ** 2)))
sun = eas.spawn_actor_from_class(unreal.DirectionalLight, V(0, 0, 1500), R(pitch=pitch, yaw=yaw))
sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
sc.set_editor_property("intensity", 1200.0)
sc.set_editor_property("use_temperature", True)
sc.set_editor_property("temperature", 4300.0)
sc.set_editor_property("light_source_angle", 0.35)
sun.set_actor_label("Sun_Aurelia")
sun.set_folder_path("Lighting")
sun.set_editor_property("tags", ["ASTRA.Sun"])

sky = eas.spawn_actor_from_object(eal.load_asset("/Engine/EngineSky/SM_SkySphere") or eal.load_asset("/Engine/BasicShapes/Sphere"), V(0, 0, 0), R())
sky.set_actor_scale3d(V(12000, 12000, 12000))   # ~490 km: the sphere is opaque, anything beyond it would be hidden
smc = sky.get_component_by_class(unreal.StaticMeshComponent)
smc.set_material(0, eal.load_asset("/Game/ASTRA/Space/M_ASTRA_SpaceSky"))
smc.set_editor_property("cast_shadow", False)
smc.set_editor_property("affect_distance_field_lighting", False)
smc.set_editor_property("affect_dynamic_indirect_lighting", False)
smc.set_editor_property("bounds_scale", 100.0)      # the material recentres the sphere on the camera: never cull it
smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
sky.set_actor_label("SpaceSky")
sky.set_folder_path("Space")
sky.set_editor_property("tags", ["ASTRA.Sky"])

# ambient light of space (stars, Milky Way, the Teal Veil): keeps the unlit sides of ships readable
skyl = eas.spawn_actor_from_class(unreal.SkyLight, V(0, 0, 800), R())
slc = skyl.get_component_by_class(unreal.SkyLightComponent)
slc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
slc.set_editor_property("cubemap", eal.load_asset("/Game/ASTRA/Space/T_Sky_Aurelia_8k"))
slc.set_editor_property("intensity", 4.0)
skyl.set_actor_label("SkyLight_Space")
skyl.set_folder_path("Space")

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

ps = eas.spawn_actor_from_class(unreal.PlayerStart, V(0.35 * M, 0.95 * M, 1.35 * M), R())   # on the dais, beside the chair
ps.set_folder_path("Gameplay")
unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).set_level_viewport_camera_info(
    V(-7.2 * M, -1.2 * M, 1.75 * M), R(pitch=-4.0, yaw=4.0))
import importlib  # noqa: E402
import astra_editor  # noqa: E402
importlib.reload(astra_editor)
log.append(astra_editor.setup_space(84.0))
les.save_current_level()
log.append(f"actors: {len(eas.get_all_level_actors())}")
print(json.dumps(log))
