"""The ASN Aquila's interior from the ship's plan (NAVE, phase F4.1): materials, kit import, the built decks placed in L_Bridge, doors, zone lights,
and the plan itself copied where the game reads it. Idempotent; run in the editor (not during PIE), in this order:

  1. uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py       (art/_cache/ship: label atlas)
  2. python3 art/blender/ship_plan_gen.py                                                                           (data/ship/aquila_plan.json)
  3. /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py   (art/export/ship: FBX + manifest)
  4. tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py                                                     (this script)

Set globals before running to change the defaults:
  DECKS = [4, 6]              the decks to (re)place from the plan's "placements" (their folders Interior/Deck<NN>/... are emptied first, nothing else is)
  REBUILD_KIT = True          delete /Game/ASTRA/Kit/Ship and import the FBX files again (a reimport keeps slots the new FBX no longer has)
  LOCK_STAIRS = True          the stair-tower doors of a deck stay locked while the deck above or below is not built (nothing there yet)
  REMOVE_LIFT_LEAVES = False  open the entrances of the existing rooms that a built deck now runs up to: destroy the static lift leaves that close their alcoves
                              (folders "Mess/Lift", "Berths/Lift" on Deck 4, "Medbay/Lift" on Deck 6) and put a sliding door (AAstraDoor) in the opening; only once
                              AstraHangar's landings point to the new lift banks (docs/NAVE.md, "Lift"), because the lift's own doors go with the leaves
  SAVE_LEVEL = True

What it does:
  materials   MI_SHIP_* in /Game/ASTRA/Materials/Instances (parent M_ASTRA_Hard with the packed sets of the project; MI_SHIP_Labels = M_ASTRA_Screen with
              T_SHIP_Labels), named like the mesh slots so import_kit's assign_materials_by_slot finds them
  kit         art/export/ship/*.fbx -> /Game/ASTRA/Kit/Ship: Nanite on (off for the glass ones), complex collision as simple
  plan        data/ship/aquila_plan.json -> Content/ASTRA/Data/aquila_plan.json (UAstraShipPlan reads it there, staged loose in the package)
  level       L_Bridge, folders Interior/Deck<NN>/{Passages,Rooms/<section>,Signs,Plates,Doors,Lights}: a static mesh actor per placement (module, room,
              sign, plate), an AAstraDoor per door of the plan (width/height/yaw of the record), the zone lights of the compartments (RectLight /
              PointLight, lumens, temperature, no shadows, tagged ASTRA.ZoneLight.<compartment>)
Unreal convention = plan convention (X forward, Y starboard, Z up); plan in metres, Unreal in cm.
"""
import json
import math
import os
import shutil

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = ROOT + "/art/export/ship"
CACHE = ROOT + "/art/_cache/ship"
PLAN = ROOT + "/data/ship/aquila_plan.json"
LEVEL = "/Game/ASTRA/Maps/L_Bridge"
KIT = "/Game/ASTRA/Kit/Ship"
MAT_DST = "/Game/ASTRA/Materials"
TEX_DST = MAT_DST + "/Textures"
MI_DIR = MAT_DST + "/Instances"
DATA_DIR = unreal.Paths.project_content_dir() + "ASTRA/Data"

DECKS = globals().get("DECKS", [4, 6])
REBUILD_KIT = globals().get("REBUILD_KIT", True)
LOCK_STAIRS = globals().get("LOCK_STAIRS", True)
REMOVE_LIFT_LEAVES = globals().get("REMOVE_LIFT_LEAVES", False)
SAVE_LEVEL = globals().get("SAVE_LEVEL", True)

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
V = unreal.Vector
M = 100.0
log = []


def R(pitch=0.0, yaw=0.0, roll=0.0):
    return unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)


for p in (PLAN, SRC + "/manifest.json", CACHE + "/T_SHIP_Labels.png"):
    if not os.path.exists(p):
        raise RuntimeError(f"{p} missing: see the order of the steps in the docstring")
PLAN_DATA = json.load(open(PLAN, encoding="utf-8"))
MANIFEST = json.load(open(SRC + "/manifest.json", encoding="utf-8"))
for need in ("M_ASTRA_Hard", "M_ASTRA_Screen"):
    if not eal.does_asset_exist(f"{MAT_DST}/{need}"):
        raise RuntimeError(f"{need} missing: run make_materials.py and make_ui_materials.py first")
for need in MANIFEST.get("shared_slots", []):                    # the instances of the project that the kit's meshes use as they are
    if not eal.does_asset_exist(f"{MI_DIR}/{need}"):
        raise RuntimeError(f"{need} missing: run make_materials.py and make_bridge_v3_materials.py first")


# ------------------------------------------------------------------------------------------------------------------ materials
def make_mi(folder, name, parent, scalars=None, vectors=None, textures=None):
    path = f"{folder}/{name}"
    if eal.does_asset_exist(path):
        mi = eal.load_asset(path)
    else:
        mi = tools.create_asset(name, folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    if mi.get_editor_property("parent") != parent:
        mel.set_material_instance_parent(mi, parent)
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(mi, k, v)
    mel.update_material_instance(mi)
    eal.save_loaded_asset(mi, only_if_is_dirty=False)
    return mi


def import_labels():
    t = unreal.AssetImportTask()
    t.filename = CACHE + "/T_SHIP_Labels.png"
    t.destination_path = TEX_DST
    t.automated = True
    t.replace_existing = True
    t.save = False
    tools.import_asset_tasks([t])
    tex = eal.load_asset(f"{TEX_DST}/T_SHIP_Labels")
    tex.set_editor_property("srgb", True)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
    tex.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
    eal.save_loaded_asset(tex, only_if_is_dirty=False)
    return tex


def tex(name):
    t = eal.load_asset(f"{TEX_DST}/{name}")
    if t is None:
        raise RuntimeError(f"texture {name} missing")
    return t


# name, packed set, tint (linear), UVScale, roughness (min, max), MetallicFromMap, BaseColorMapInfluence, NormalStrength: the values of the Blender previews
SHIP_MI = [
    ("MI_SHIP_Laminate", "PanelPaint", (0.42, 0.46, 0.50), 1.0, (0.28, 0.42), 0.0, 0.25, 0.3),
    ("MI_SHIP_Steel", "Brushed", (0.62, 0.64, 0.66), 1.0, (0.20, 0.36), 1.0, 0.5, 0.6),
    ("MI_SHIP_FabricNavy", "Linen", (0.030, 0.050, 0.11), 3.0, (0.55, 0.8), 0.0, 0.5, 0.7),
    ("MI_SHIP_FabricRust", "Linen", (0.22, 0.075, 0.04), 3.0, (0.55, 0.8), 0.0, 0.5, 0.7),
    ("MI_SHIP_FabricGrey", "Linen", (0.12, 0.125, 0.13), 3.0, (0.55, 0.8), 0.0, 0.5, 0.7),
    ("MI_SHIP_FabricSand", "Linen", (0.36, 0.30, 0.20), 3.0, (0.55, 0.8), 0.0, 0.5, 0.7),
    ("MI_SHIP_Bedding", "Cotton", (0.62, 0.64, 0.66), 3.0, (0.6, 0.85), 0.0, 0.5, 0.6),
    ("MI_SHIP_Wood", "WoodDark", (0.20, 0.11, 0.06), 1.0, (0.28, 0.5), 0.0, 0.7, 0.8),
    ("MI_SHIP_CrateOlive", "PanelPaint", (0.10, 0.13, 0.055), 1.0, (0.5, 0.7), 0.0, 0.25, 0.3),
    ("MI_SHIP_CrateOrange", "PanelPaint", (0.55, 0.20, 0.03), 1.0, (0.5, 0.7), 0.0, 0.25, 0.3),
    ("MI_SHIP_CrateBlue", "PanelPaint", (0.045, 0.09, 0.20), 1.0, (0.5, 0.7), 0.0, 0.25, 0.3),
    ("MI_SHIP_CrateGrey", "PanelPaint", (0.22, 0.23, 0.24), 1.0, (0.5, 0.7), 0.0, 0.25, 0.3),
    ("MI_SHIP_Leaf", "Linen", (0.045, 0.20, 0.04), 4.0, (0.45, 0.65), 0.0, 0.5, 0.6),
    ("MI_SHIP_Tile", "PanelPaint", (0.62, 0.64, 0.62), 1.0, (0.12, 0.25), 0.0, 0.2, 0.3),
    ("MI_SHIP_PaintRed", "PanelPaint", (0.46, 0.035, 0.025), 1.0, (0.3, 0.5), 0.0, 0.2, 0.3),
    ("MI_SHIP_Soil", "Linen", (0.035, 0.022, 0.014), 4.0, (0.7, 0.9), 0.0, 0.5, 0.8),
]


def build_materials():
    hard = eal.load_asset(f"{MAT_DST}/M_ASTRA_Hard")
    screen = eal.load_asset(f"{MAT_DST}/M_ASTRA_Screen")
    labels = import_labels()
    made = []
    for (name, tset, tint, uvs, rough, metal_map, influence, normal) in SHIP_MI:
        make_mi(MI_DIR, name, hard,
                scalars={"UVScale": uvs, "RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": metal_map, "MetallicBias": 0.0,
                         "BaseColorMapInfluence": influence, "NormalStrength": normal, "MacroBrightness": 0.05, "ScratchRoughness": 0.05,
                         "RoughnessVariation": 0.08},
                vectors={"Tint": tint},
                textures={"BaseColorMap": tex(f"T_{tset}_BC"), "NormalMap": tex(f"T_{tset}_N"), "ORMMap": tex(f"T_{tset}_ORM")})
        made.append(name)
    make_mi(MI_DIR, "MI_SHIP_Labels", screen, {"Intensity": 4.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, textures={"ScreenTexture": labels})
    made.append("MI_SHIP_Labels")
    have = set(made)
    for slot in MANIFEST.get("new_slots", []):
        if slot not in have:
            raise RuntimeError(f"the kit uses {slot} and this script does not make it: add it to SHIP_MI")
    log.append(f"{len(made)} MI_SHIP_* instances")


# -------------------------------------------------------------------------------------------------------------------- the kit
def import_kit():
    if REBUILD_KIT and eal.does_directory_exist(KIT):
        for path in eal.list_assets(KIT, recursive=False, include_folder=False):
            if not eal.delete_asset(path):
                log.append(f"could not delete {path}")
    g = {"SRC": SRC, "DST": KIT, "NANITE": True, "__name__": "__main__"}
    exec(open(ROOT + "/tools/ue_scripts/import_kit.py").read(), g)          # Nanite on (the glass ones stay classic), complex-as-simple collision
    return g


def check_bounds():
    """The imported meshes against the manifest (cm; the plan's frame): a mesh that came out scaled or mirrored is reported."""
    bad = []
    for name, info in MANIFEST["meshes"].items():
        asset = eal.load_asset(f"{KIT}/{name}")
        if asset is None:
            bad.append(f"{name}: not imported")
            continue
        bb = asset.get_bounding_box()
        lo, hi = info["bounds_m"]["min"], info["bounds_m"]["max"]
        got_lo, got_hi = (bb.min.x, bb.min.y, bb.min.z), (bb.max.x, bb.max.y, bb.max.z)
        for i in range(3):
            if abs(got_lo[i] - lo[i] * M) > 6.0 or abs(got_hi[i] - hi[i] * M) > 6.0:
                bad.append(f"{name}: bounds {[round(v) for v in got_lo]}..{[round(v) for v in got_hi]} cm, expected {[round(v * M) for v in lo]}..{[round(v * M) for v in hi]}")
                break
    return bad


# --------------------------------------------------------------------------------------------------------------------- the plan
def copy_plan():
    os.makedirs(DATA_DIR, exist_ok=True)
    dst = DATA_DIR + "/aquila_plan.json"
    shutil.copyfile(PLAN, dst)
    log.append(f"plan copied to {dst}")


# -------------------------------------------------------------------------------------------------------------------- the level
def folder_of(deck, pl):
    return pl["folder"]


def clear_deck_folders(decks):
    prefixes = tuple(f"Interior/Deck{d:02d}" for d in decks)
    n = 0
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith(prefixes):
            eas.destroy_actor(a)
            n += 1
    return n


def place_meshes(deck):
    count = {}
    missing = set()
    for pl in PLAN_DATA["placements"].get(str(deck), []):
        asset = eal.load_asset(f"{KIT}/{pl['mesh']}")
        if asset is None:
            missing.add(pl["mesh"])
            continue
        x, y, z = pl["pos"]
        a = eas.spawn_actor_from_object(asset, V(x * M, y * M, z * M), R(yaw=pl["yaw"]))
        a.set_actor_label(pl["label"])
        a.set_folder_path(pl["folder"])
        count[pl["cls"]] = count.get(pl["cls"], 0) + 1
    if missing:
        raise RuntimeError(f"deck {deck}: meshes missing in {KIT}: {sorted(missing)}")
    return count


def built_decks():
    """The decks that have placements in the plan (their stairs can be used)."""
    return {int(d) for d, v in PLAN_DATA["placements"].items() if v}


def place_doors(deck):
    comps = {c["id"]: c for c in PLAN_DATA["compartments"]}
    built = built_decks() | set(DECKS)
    n, locked = 0, 0
    for d in PLAN_DATA["doors"]:
        if d["deck"] != deck or d.get("existing") or d.get("planned"):
            continue
        ends = [comps.get(d.get("a")), comps.get(d.get("b"))]
        if any(c is not None and c.get("status") == "planned" and c.get("prefab") is None and c.get("kind") not in ("corridor", "vestibule") for c in ends):
            continue                                            # a door into a room that is not built
        x, y, z = d["pos"]
        door = eas.spawn_actor_from_class(unreal.AstraDoor, V(x * M, y * M, z * M), R(yaw=d.get("yaw", 0.0)))
        door.set_editor_property("width", float(d["width"]) * M)
        door.set_editor_property("height", float(d["height"]) * M)
        lock = bool(d.get("locked"))
        if LOCK_STAIRS and any(c is not None and c.get("kind") == "stairs" for c in ends):
            above, below = (deck - 1) in built, (deck + 1) in built
            lock = lock or not (above and below)
        if lock:
            try:
                door.set_editor_property("locked", True)
                locked += 1
            except Exception as ex:
                log.append(f"door {d['id']}: could not lock ({ex})")
        door.set_actor_label(f"Door_{d['id']}")
        door.set_folder_path(f"Interior/Deck{deck:02d}/Doors")
        n += 1
    return n, locked


def add_light(cid, ld, deck):
    pos = V(ld["pos"][0] * M, ld["pos"][1] * M, ld["pos"][2] * M)
    if ld.get("type", "rect") == "rect":
        rot = unreal.MathLibrary.make_rot_from_xy(V(0, 0, -1), V(1, 0, 0))              # faces down, the width along +X, the height along Y
        a = eas.spawn_actor_from_class(unreal.RectLight, pos, rot)
        c = a.get_component_by_class(unreal.RectLightComponent)
        c.set_editor_property("source_width", float(ld["size"][0]) * M)
        c.set_editor_property("source_height", float(ld["size"][1]) * M)
    else:
        a = eas.spawn_actor_from_class(unreal.PointLight, pos, R())
        c = a.get_component_by_class(unreal.PointLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", float(ld["lumens"]))
    c.set_editor_property("attenuation_radius", float(ld.get("radius", 1000.0)))
    c.set_editor_property("use_temperature", True)
    c.set_editor_property("temperature", float(ld.get("temperature", 5000.0)))
    c.set_editor_property("cast_shadows", bool(ld.get("shadows", False)))
    a.set_actor_label(ld["id"])
    a.set_folder_path(f"Interior/Deck{deck:02d}/Lights")
    a.tags = [unreal.Name(f"ASTRA.ZoneLight.{cid}")]
    return a


def place_lights(deck):
    n = 0
    for c in PLAN_DATA["compartments"]:
        if c["deck"] != deck or c.get("status") != "built":
            continue
        for ld in c.get("lights", []):
            add_light(c["id"], ld, deck)
            n += 1
    return n


LIFT_LEAVES = {"mess": "Mess/Lift", "berths": "Berths/Lift", "medbay": "Medbay/Lift"}      # the existing rooms whose alcove a built deck of ours reaches


def open_existing_entrances():
    """The entrance of an existing room is the lift alcove of its own builder, closed by two static leaves: where a built deck's corridor now runs up to it,
    destroy the leaves (and the room's lift sign, in the same folder) and put a sliding door in the opening (the plan's `<room>_entrance`)."""
    opened = []
    for cid, folder in LIFT_LEAVES.items():
        door = next((d for d in PLAN_DATA["doors"] if d["id"] == f"{cid}_entrance"), None)
        if door is None or door["deck"] not in DECKS or not door.get("b"):
            continue
        n = 0
        for a in eas.get_all_level_actors():
            if str(a.get_folder_path()) == folder:
                eas.destroy_actor(a)
                n += 1
        x, y, z = door["pos"]
        a = eas.spawn_actor_from_class(unreal.AstraDoor, V(x * M, y * M, z * M), R(yaw=door.get("yaw", 0.0)))
        a.set_editor_property("width", float(door["width"]) * M)
        a.set_editor_property("height", float(door["height"]) * M)
        a.set_actor_label(f"Door_{door['id']}")
        a.set_folder_path(f"Interior/Deck{door['deck']:02d}/Doors")
        opened.append(f"{cid}: {n} leaves removed, door placed")
    log.append(f"existing entrances opened: {opened}")


# ------------------------------------------------------------------------------------------------------------------------ run
# the level first: the old actors of the decks go before their meshes are deleted and imported again
if not eal.does_asset_exist(LEVEL):
    raise RuntimeError(f"{LEVEL} missing: build the bridge level first (build_bridge.py)")
les.load_level(LEVEL)
cleared = clear_deck_folders(DECKS)
log.append(f"{cleared} old actors of the decks {DECKS} removed")
build_materials()
import_kit()
bad = check_bounds()
log.append(f"kit: {len(MANIFEST['meshes'])} meshes imported; {len(bad)} bounds problems")
copy_plan()
report = {}
for d in DECKS:
    counts = place_meshes(d)
    doors, locked = place_doors(d)
    lights = place_lights(d)
    expect = len(PLAN_DATA["placements"].get(str(d), []))
    report[d] = {"meshes": counts, "expected": expect, "doors": doors, "locked": locked, "zone_lights": lights}
if REMOVE_LIFT_LEAVES:
    open_existing_entrances()
if SAVE_LEVEL:
    les.save_current_level()
print(json.dumps({"log": log, "bounds_problems": bad, "decks": report}, indent=1))
