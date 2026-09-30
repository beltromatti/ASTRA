"""Level L_Bridge, version 3: the ASN Aquila bridge assembled from data/ship/aquila_bridge.json (single source of truth) and the
meshes of art/blender/bridge_v3.py (art/export/bridge_v3). Called by build_bridge.py; run in the editor, not during PIE:

  1. blender -b --factory-startup --python-exit-code 1 -P art/blender/bridge_v3.py        (FBX + manifest.json)
  2. tools/ue.py pyfile tools/ue_scripts/make_bridge_v3_materials.py                     (textures, masters, instances)
  3. tools/ue.py pyfile tools/ue_scripts/build_bridge.py                                 (this script: import, place, light)

Unreal convention = data convention (X forward, Y starboard, Z up); data in metres, Unreal in cm. Everything the v2 script
built (corridors, doors, the Aquila's hull, the space, the crew) is kept; what changes is the bridge itself: 30 meshes
placed from bridge3_layout.placements(), the live screens bound to the MI_UI_* pages, the table's plot at the new table top,
the lights of the data file, and the officers seated from the stations' `seat` data.
"""
import importlib
import json
import math
import os
import random
import sys

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
sys.path.insert(0, ROOT + "/tools/ue_scripts")
import bridge3_layout as LAY  # noqa: E402

importlib.reload(LAY)

LEVEL = "/Game/ASTRA/Maps/L_Bridge"
KIT = "/Game/ASTRA/Kit/Bridge3"
MI_DIR = "/Game/ASTRA/Materials/Instances"
UI_MI = "/Game/ASTRA/UI/Materials"
HOLO_UI = KIT + "/HoloUI"
SRC = ROOT + "/art/export/bridge_v3"
DATA = LAY.load(ROOT + "/data/ship/aquila_bridge.json")
eal = unreal.EditorAssetLibrary
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V = unreal.Vector
M = 100.0
log = []


def R(pitch=0.0, yaw=0.0, roll=0.0):
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


if DATA.get("version", 2) < 3:
    raise RuntimeError("data/ship/aquila_bridge.json is not version 3")
for need in ("MI_BRG3_Composite", "MI_BRG3_Lamps", "SCREEN_helm_1", "SCREEN_viewscreen_1"):
    if not eal.does_asset_exist(f"{MI_DIR}/{need}"):
        raise RuntimeError(f"{need} missing: run tools/ue_scripts/make_bridge_v3_materials.py first")
if not os.path.exists(SRC + "/manifest.json"):
    raise RuntimeError(f"{SRC}/manifest.json missing: run art/blender/bridge_v3.py first (see the docstring)")
MANIFEST = json.load(open(SRC + "/manifest.json", encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------- import the meshes
# a fresh import (a reimport keeps material slots the new FBX no longer has: a stale translucent slot makes Nanite refuse
# the whole mesh and draw its coarse fallback); the hover UI twins in KIT/HoloUI are not touched
for path in eal.list_assets(KIT, recursive=False, include_folder=False):
    if not eal.delete_asset(path):
        log.append(f"could not delete {path}")
DST = KIT
NANITE = True
exec(open(ROOT + "/tools/ue_scripts/import_kit.py").read())      # Nanite on, complex-as-simple collision; glass/translucent stay classic

# only what this script builds again: the level also holds the flight deck, engineering, the medbay, the mess, the berths,
# the quarters, the lifepods, New Ravenna, the walkers and the signage, each built by its own script
OWNED = {"Bridge", "Bridge/Crew", "Bridge/Doors", "Bridge/Stations", "Bridge/Props", "Corridors", "Corridors/Panels",
         "Lighting", "Space", "Gameplay", "Ship", "Quarters/Door"}
if eal.does_asset_exist(LEVEL):
    les.load_level(LEVEL)
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()) in OWNED:
            eas.destroy_actor(a)
else:
    les.new_level(LEVEL)


# ------------------------------------------------------------------------------------------------------------------ helpers
def place(mesh, x, y, z=0.0, yaw=0.0, label=None, folder="Bridge"):
    path = mesh if mesh.startswith("/Game/") else f"{KIT}/{mesh}"
    asset = eal.load_asset(path)
    if asset is None:
        raise RuntimeError(f"missing asset {path}")
    a = eas.spawn_actor_from_object(asset, V(x * M, y * M, z * M), R(yaw=yaw))
    a.set_actor_label(label or mesh)
    a.set_folder_path(folder)
    return a


def screen_material(slot):
    """The material a SCREEN_ slot gets on its component: the live-page instance the screens subsystem binds by name
    (MI_UI_<Page> for the opaque screens, its translucent twin for the hover panels), else the slot's own default."""
    info = DATA["screens"].get(slot, {})
    if info.get("instance"):
        return eal.load_asset(f"{MI_DIR}/{info['instance']}")
    page = info.get("page")
    if page and info.get("surface") == "hover":
        m = eal.load_asset(f"{HOLO_UI}/MI_UI_{page}")
        if m:
            return m
    if page and info.get("surface") in ("glass", "wall", "armrest"):
        m = eal.load_asset(f"{UI_MI}/MI_UI_{page}")
        if m:
            return m
    return eal.load_asset(f"{MI_DIR}/{slot}")


# ---------------------------------------------------------------------------------------------- the bridge (meshes by layout)
level_z = DATA["levels"]
placed = {}
for pl in LAY.placements(DATA):
    x, y, z = pl["pos"]
    a = place(pl["mesh"], x, y, z, pl["yaw"], label=pl["label"], folder=pl["folder"])
    smc = a.get_component_by_class(unreal.StaticMeshComponent)
    mesh = smc.static_mesh
    for sm in mesh.get_editor_property("static_materials"):
        slot = str(sm.get_editor_property("material_slot_name"))
        if slot.startswith("SCREEN_"):
            mat = screen_material(slot)
            if mat:
                smc.set_material_by_name(slot, mat)
    if LAY.is_translucent(pl["mesh"]):
        # (SM_BRG3_ViewscreenImage stays invisible - MI opacity 0 - while AAstraViewscreen (C++) draws its own flat 7.2 x 3.0 m quad
        # at (900, 0, 120) cm: the same rectangle; bind the feed to this slot instead once the C++ quad is retired)
        smc.set_editor_property("cast_shadow", False)
        if "Glass" not in pl["mesh"]:
            smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)       # holograms and the image plane: nothing to bump into
    placed[pl["label"]] = a
log.append(f"{len(placed)} bridge meshes")

# the live tactical plot above the table (AAstraHoloTable, C++): origin on the table top, +X towards the bow
ht = DATA["holo_table"]
top_z = LAY.level_z(DATA, ht.get("level", "well")) + ht["height"]
plot = eas.spawn_actor_from_class(unreal.AstraHoloTable, V(ht["pos"][0] * M, ht["pos"][1] * M, (top_z + 0.01) * M), R())
plot.set_actor_label("HoloTable_Plot")
plot.set_folder_path("Bridge")
try:
    plot.set_editor_property("plot_radius", ht.get("plot_radius", ht["radius"] - 0.15) * M)
except Exception as ex:
    log.append(f"plot_radius not set ({ex})")

# sliding pressure doors in the back wall (AAstraDoor: they open when you come near, into the wall)
for d in DATA["doors"]:
    dx, dy = d["pos"]
    door = eas.spawn_actor_from_class(unreal.AstraDoor, V((dx - 0.15) * M, dy * M, 0.0), R())
    door.set_editor_property("width", d["width"] * M)
    door.set_editor_property("height", d["height"] * M)
    door.set_actor_label(f"Door_{d['id']}")
    door.set_folder_path("Bridge/Doors")

# --- corridors behind the doors: 12 m runs of the corridor kit going aft, a window module on the hull side
CK = "/Game/ASTRA/Kit/Interior/Corridor"
WALL_T = 0.3                      # bridge back wall thickness (the core: art/blender/bridge3_frame.py, plus a 4 cm skin)
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

# --- bridge crew (placeholder bodies until the MetaHuman crew); the station id is the mind's `speaker`. Seated from the
# stations' `seat` data: posture, hip height; the tactical officer stands at the lectern (the mannequin faces its +Y: yaw - 90)
CREW = {"xo": "Cmdr. Elena Serra", "helm": "Lt. Marco Ferri", "ops": "Lt. Yuki Tanaka", "tactical": "Lt. Cmdr. Sara Voss",
        "comms": "Ens. Leo Martin", "sensors": "Lt. Priya Nair", "engineering": "Lt. (j.g.) Kofi Mensah", "flight": "Lt. Jonah Price"}
POSTURE = {"seated_console": unreal.AstraCrewPosture.SEATED_CONSOLE, "seated_armchair": unreal.AstraCrewPosture.SEATED_ARMCHAIR,
           "standing": unreal.AstraCrewPosture.STANDING}
for st in DATA["stations"]:
    sid = st["id"]
    if sid not in CREW:
        continue
    x, y = st["pos"]
    z = level_z[st["level"]]
    seat = st.get("seat", {})
    posture = POSTURE[seat.get("posture", "seated_console")]
    yaw = st["yaw"] - (90.0 if posture == unreal.AstraCrewPosture.STANDING else 0.0)
    c = eas.spawn_actor_from_class(unreal.AstraCrewMember, V(x * M, y * M, z * M), R(yaw=yaw))
    c.set_editor_property("posture", posture)
    if "hip_height" in seat:
        try:
            c.set_editor_property("seat_hip_height", seat["hip_height"] * M)
        except Exception as ex:
            log.append(f"seat_hip_height not set ({ex})")
    c.set_editor_property("station_id", sid)
    c.set_editor_property("display_name", CREW[sid])
    c.set_actor_label(f"Crew_{sid}")
    c.set_folder_path("Bridge/Crew")


# ---------------------------------------------------------------------------------------------------------------- lights
def add_light(ld):
    """A light of the data file: rect / spot / point in lumens, tagged ASTRA.ShipLight (the alert scales them)."""
    pos = V(ld["pos"][0] * M, ld["pos"][1] * M, ld["pos"][2] * M)
    d = V(*ld["dir"]) if "dir" in ld else V(0, 0, -1)
    if ld["type"] == "rect":
        along = V(*ld["along"]) if "along" in ld else None
        if along is not None:
            rot = unreal.MathLibrary.make_rot_from_xy(d, along)
        else:
            rot = unreal.MathLibrary.make_rot_from_x(d)
        a = eas.spawn_actor_from_class(unreal.RectLight, pos, rot)
        c = a.get_component_by_class(unreal.RectLightComponent)
        c.set_editor_property("source_width", ld["size"][0] * M)
        c.set_editor_property("source_height", ld["size"][1] * M)
    elif ld["type"] == "spot":
        a = eas.spawn_actor_from_class(unreal.SpotLight, pos, unreal.MathLibrary.make_rot_from_x(d))
        c = a.get_component_by_class(unreal.SpotLightComponent)
        c.set_editor_property("inner_cone_angle", ld.get("inner", 20.0))
        c.set_editor_property("outer_cone_angle", ld.get("outer", 50.0))
        c.set_editor_property("source_radius", 6.0)
    else:
        a = eas.spawn_actor_from_class(unreal.PointLight, pos, R())
        c = a.get_component_by_class(unreal.PointLightComponent)
        c.set_editor_property("specular_scale", ld.get("specular", 1.0))
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", float(ld["lumens"]) * float(DATA.get("light_gain", 1.0)))       # one knob to retune the whole room
    c.set_editor_property("attenuation_radius", float(ld.get("radius", 1000.0)))
    if "color" in ld:
        r, g, b = ld["color"]
        c.set_editor_property("light_color", unreal.Color(r=r, g=g, b=b, a=255))       # by name: positional Color is B, G, R, A
    else:
        c.set_editor_property("use_temperature", True)
        c.set_editor_property("temperature", float(ld.get("temperature", 5600.0)))
    c.set_editor_property("cast_shadows", bool(ld.get("shadows", False)))
    a.set_actor_label(ld["id"])
    a.set_folder_path("Lighting")
    a.tags = [unreal.Name("ASTRA.ShipLight")]
    return a


for ld in DATA["lights"]:
    add_light(ld)
log.append(f"{len(DATA['lights'])} lights")

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
import astra_editor  # noqa: E402

importlib.reload(astra_editor)
log.append(astra_editor.setup_space(84.0))
les.save_current_level()
log.append(f"actors: {len(eas.get_all_level_actors())}")
print(json.dumps(log))
