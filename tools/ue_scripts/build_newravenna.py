"""New Ravenna's surface around Port Aurelius, built into the bridge level far below the Aquila's space (the same world:
the war goes on up there while the Captain flies down here). Everything is tagged ASTRA.Planet.NewRavenna and starts
hidden; the game shows it when the Captain comes down through the atmosphere (UAstraShipSubsystem::SetPlanetside).

  terrain   16 Nanite core tiles (12 km) + the far terrain (64 km), art/export/newravenna (art/blender/terrain.py)
  sea       a 400 km opaque ocean at sea level
  sky       SkyAtmosphere (the planet's top at the zone origin, radius 6000 km), volumetric clouds, height fog, a
            real-time sky light for the day-lit ground
Idempotent: the "NewRavenna" folder is replaced. Run in the editor (not during PIE):
  tools/ue.py pyfile tools/ue_scripts/build_newravenna.py
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Planet/NewRavenna"
ZONE = unreal.Vector(0.0, 0.0, -1.0e8)          # the planet's surface zone: 1000 km below the bridge
TAG = "ASTRA.Planet.NewRavenna"
eal = unreal.EditorAssetLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
log = []

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("NewRavenna"):
        eas.destroy_actor(a)


def tagged(a, label, folder):
    a.set_actor_label(label)
    a.set_folder_path(folder)
    a.tags = [TAG]
    a.set_actor_hidden_in_game(True)
    return a


# ---- terrain
for path in eal.list_assets(KIT, recursive=False, include_folder=False):
    mesh = eal.load_asset(path)
    if not isinstance(mesh, unreal.StaticMesh) or not mesh.get_name().startswith("SM_NR_"):
        continue
    a = eas.spawn_actor_from_object(mesh, ZONE, unreal.Rotator())
    smc = a.static_mesh_component
    smc.set_editor_property("cast_shadow", mesh.get_name() != "SM_NR_Far")
    smc.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY if mesh.get_name().startswith("SM_NR_Core") else unreal.CollisionEnabled.NO_COLLISION)
    tagged(a, mesh.get_name().replace("SM_NR_", "NR_Terrain_"), "NewRavenna/Terrain")
log.append("terrain")

# ---- the sea
plane = eal.load_asset("/Engine/BasicShapes/Plane")
sea = eas.spawn_actor_from_object(plane, ZONE, unreal.Rotator())
sea.set_actor_scale3d(unreal.Vector(400000.0, 400000.0, 1.0))      # the engine plane is 1 m: 400 km
sea.static_mesh_component.set_material(0, eal.load_asset("/Game/ASTRA/Materials/Instances/MI_NR_Ocean"))
sea.static_mesh_component.set_editor_property("cast_shadow", False)
sea.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
tagged(sea, "NR_Sea", "NewRavenna")
log.append("sea")

# ---- the sky of a living world
atm = eas.spawn_actor_from_class(unreal.SkyAtmosphere, ZONE, unreal.Rotator())
ac = atm.get_component_by_class(unreal.SkyAtmosphereComponent)
ac.set_editor_property("transform_mode", unreal.SkyAtmosphereTransformMode.PLANET_TOP_AT_COMPONENT_TRANSFORM)
ac.set_editor_property("bottom_radius", 6000.0)                   # km
ac.set_editor_property("atmosphere_height", 100.0)
ac.set_editor_property("aerial_pespective_view_distance_scale", 1.0)
ac.set_visibility(False)
tagged(atm, "NR_SkyAtmosphere", "NewRavenna/Sky")

cloud = eas.spawn_actor_from_class(unreal.VolumetricCloud, ZONE, unreal.Rotator())
cc = cloud.get_component_by_class(unreal.VolumetricCloudComponent)
cc.set_editor_property("layer_bottom_altitude", 1.8)             # km
cc.set_editor_property("layer_height", 6.0)
for k in ("view_sample_count_scale", "shadow_view_sample_count_scale", "reflection_view_sample_count_scale_value"):
    cc.set_editor_property(k, 0.5)                                 # half the samples: TSR smooths the rest (~3 ms saved)
cm = eal.load_asset("/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst")
if cm:
    cc.set_editor_property("material", cm)
cc.set_visibility(False)
tagged(cloud, "NR_Clouds", "NewRavenna/Sky")

fog = eas.spawn_actor_from_class(unreal.ExponentialHeightFog, ZONE + unreal.Vector(0, 0, 0), unreal.Rotator())
fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
fc.set_editor_property("fog_density", 0.0012)
fc.set_editor_property("fog_height_falloff", 0.12)
fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.35, 0.5, 0.75, 1.0))
fc.set_visibility(False)
tagged(fog, "NR_HeightFog", "NewRavenna/Sky")

sky = eas.spawn_actor_from_class(unreal.SkyLight, ZONE + unreal.Vector(0, 0, 50000.0), unreal.Rotator())
sc = sky.get_component_by_class(unreal.SkyLightComponent)
sc.set_editor_property("mobility", unreal.ComponentMobility.MOVABLE)
sc.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_CAPTURED_SCENE)
sc.set_editor_property("real_time_capture", True)
sc.set_editor_property("intensity", 1.0)
sc.set_visibility(False)
tagged(sky, "NR_SkyLight", "NewRavenna/Sky")
log.append("sky")

sites = json.load(open(os.path.join(ROOT, "art", "export", "newravenna", "nr_sites.json")))
port = json.load(open(os.path.join(ROOT, "art", "export", "newravenna_port", "nr_port.json")))
PORT = KIT + "/Port"


def ue(x, y, z):
    """The generators' frame (Blender, +y north) to the zone's (the FBX import mirrors y)."""
    return V(x, -y, z)


def V(x, y, z):
    return unreal.Vector(ZONE.x + x * 100.0, ZONE.y + y * 100.0, ZONE.z + z * 100.0)


def piece(mesh_name, pos, yaw=0.0, scale=(1.0, 1.0, 1.0), label="", folder="NewRavenna/Port"):
    mesh = eal.load_asset(f"{PORT}/{mesh_name}")
    a = eas.spawn_actor_from_object(mesh, pos, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.QUERY_ONLY)
    return tagged(a, label or mesh_name, folder)


# ---- Port Aurelius Field: the apron, the pads, the tower, the hangars, the terminal
f = sites["field"]
for k, (dx, dy, dz) in enumerate(port["apron"]):
    piece("SM_NR_Apron", ue(f["x"] + dx, f["y"] + dy, f["z"] + dz), label=f"NR_Apron_{k}")
for k, (dx, dy, dz) in enumerate(port["pads"]):
    piece("SM_NR_Pad", ue(f["x"] + dx, f["y"] + dy, f["z"] + dz), label=f"NR_Pad_{k + 1}")
for k, (dx, dy, dz) in enumerate(port["tower"]):
    piece("SM_NR_Tower", ue(f["x"] + dx, f["y"] + dy, f["z"] + dz), yaw=-90.0, label="NR_Tower")
for k, (dx, dy, dz) in enumerate(port["hangars"]):
    piece("SM_NR_Hangar", ue(f["x"] + dx, f["y"] + dy, f["z"] + dz), yaw=90.0, label=f"NR_Hangar_{k + 1}")
for k, (dx, dy, dz) in enumerate(port["terminal"]):
    piece("SM_NR_Terminal", ue(f["x"] + dx, f["y"] + dy, f["z"] + dz), label="NR_Terminal")
log.append(f"port: {len(port['pads'])} pads")

# ---- the city of Port Aurelius (the blocks the terrain generator found room for)
VARIANTS = {"A": (120.0, 30.0, 30.0), "B": (40.0, 44.0, 22.0), "C": (70.0, 32.0, 32.0)}
for k, blk in enumerate(sites["city"]):
    v = "A" if blk["h"] >= 90 else ("C" if blk["h"] >= 45 else "B")
    H, W, D = VARIANTS[v]
    piece(f"SM_NR_Bldg_{v}", ue(blk["x"], blk["y"], blk["z"] - 1.0), yaw=-blk["yaw"],
          scale=(blk["w"] / W, blk["d"] / D, blk["h"] / H), label=f"NR_City_{k:03d}", folder="NewRavenna/City")
log.append(f"city: {len(sites['city'])} blocks")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
