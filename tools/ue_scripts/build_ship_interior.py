"""The ASN Aquila's interior from the ship's plan (NAVE, NAVE-2): materials, kit import, one sub-level per built deck (instanced modules and rooms, doors),
the decks wired into L_Bridge as streaming levels, and the plan itself copied where the game reads it. Idempotent; run in the editor (not during PIE), in
this order:

  1. uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py       (art/_cache/ship: label atlas)
  2. python3 art/blender/ship_plan_gen.py                                                                           (data/ship/aquila_plan.json)
  3. /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py   (art/export/ship: FBX + manifest)
  4. tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py                                                     (this script)

Set globals before running to change the defaults:
  DECKS = None                the decks to (re)build: None = every deck that has placements in the plan; or a list, e.g. [5, 8]
  REBUILD_KIT = "changed"     "changed": import the FBX files that are new or differ from the last import (Saved/Ship/kit_stamp.json); "all": delete
                              /Game/ASTRA/Kit/Ship and import everything; "none": use the meshes as they are
  CHUNK_M = 160.0             the instanced meshes of a deck are split into runs of this many metres along the ship (a component culls and registers
                              as a whole)
  LOCK_STAIRS = True          the stair-tower doors of a deck stay locked while the deck above or below is not built (the well would drop into nothing)
  REMOVE_LIFT_LEAVES = True   open the entrances of the existing rooms that a built deck now runs up to: destroy the static lift leaves that close their alcoves
                              (folders "Mess/Lift", "Berths/Lift" on Deck 4, "Medbay/Lift" on Deck 6) and put a sliding door (AAstraDoor) in the opening; only once
                              AstraHangar's landings point to the new lift banks (docs/NAVE.md, "Lift"), because the lift's own doors go with the leaves
  OPEN_READY_ROOM = True      the Captain's ready room (Deck 1) opens on the bridge's port corridor: the window module the bridge builder placed there (label "CorrPort_Window") and
                              the two panels of its first inner-wall bay ("CorrPort1_0_*_R") are destroyed in L_Bridge; the deck's map holds SM_SHIP_BridgeCorridorDoor in their place.
                              Run this script after build_bridge_v3.py (which would place them again)
  SAVE_LEVEL = True
  ROOT, LEVEL, DECK_DIR       the checkout, the persistent level and the folder of the decks' sub-levels (the tests of the support agents point them at a copy)

What it does:
  materials   MI_SHIP_* in /Game/ASTRA/Materials/Instances (parent M_ASTRA_Hard with the packed sets of the project; MI_SHIP_Labels = M_ASTRA_Screen with
              T_SHIP_Labels), named like the mesh slots so import_kit's assign_materials_by_slot finds them
  kit         art/export/ship/*.fbx -> /Game/ASTRA/Kit/Ship: Nanite on (off for the glass ones), complex collision as simple
  plan        data/ship/aquila_plan.json -> Content/ASTRA/Data/aquila_plan.json, without the placements and the notes (the game reads the compartments, doors
              and graph; the placements are this script's)
  decks       one map per deck, /Game/ASTRA/Maps/Decks/L_Deck<NN>: one AstraDeckShell actor holding every placement (module, room, sign, plate) as instanced
              static meshes, an AstraDoor per door of the plan (width/height/yaw of the record; locked as the plan says, and the stair-tower doors while a neighbouring
              deck is missing). No lights: the plan's lamps are data and AstraLampPool lights the few near the Captain.
  level       L_Bridge gets the deck maps as LevelStreamingDynamic (initially unloaded and hidden: AstraDeckStreaming loads the Captain's deck and its
              neighbours); in the editor they are all loaded so the whole ship can be looked at. The older decks' actors in L_Bridge (folders Interior/Deck<NN>,
              the zone lights among them) are removed.
Unreal convention = plan convention (X forward, Y starboard, Z up); plan in metres, Unreal in cm. The report (printed as JSON) lists, per deck, the placements,
instances, components, distinct meshes, triangles, doors and locked doors.
"""
import hashlib
import json
import math
import os
import shutil
import sys
import time

import unreal

ROOT = globals().get("ROOT", os.environ.get("ASTRA_ROOT", "/Users/beltromatti/Desktop/ASTRA"))
SRC = ROOT + "/art/export/ship"
CACHE = ROOT + "/art/_cache/ship"
PLAN = ROOT + "/data/ship/aquila_plan.json"
LEVEL = globals().get("LEVEL", "/Game/ASTRA/Maps/L_Bridge")
DECK_DIR = globals().get("DECK_DIR", "/Game/ASTRA/Maps/Decks")
KIT = "/Game/ASTRA/Kit/Ship"
MAT_DST = "/Game/ASTRA/Materials"
TEX_DST = MAT_DST + "/Textures"
MI_DIR = MAT_DST + "/Instances"
DATA_DIR = unreal.Paths.project_content_dir() + "ASTRA/Data"
STAMP = unreal.Paths.project_saved_dir() + "Ship/kit_stamp.json"
if ROOT + "/tools/ue_scripts" not in sys.path:
    sys.path.insert(0, ROOT + "/tools/ue_scripts")

DECKS = globals().get("DECKS", None)
REBUILD_KIT = globals().get("REBUILD_KIT", "changed")
CHUNK_M = float(globals().get("CHUNK_M", 160.0))
LOCK_STAIRS = globals().get("LOCK_STAIRS", True)
REMOVE_LIFT_LEAVES = globals().get("REMOVE_LIFT_LEAVES", True)
OPEN_READY_ROOM = globals().get("OPEN_READY_ROOM", True)
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
if DECKS is None:
    DECKS = sorted(int(d) for d, v in PLAN_DATA["placements"].items() if v)
DECKS = [int(d) for d in DECKS]


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
def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def import_kit():
    """Imports the FBX files that are new or changed since the last import (the stamp), or all of them. Returns the names imported."""
    fbx = {os.path.splitext(f)[0]: os.path.join(SRC, f) for f in sorted(os.listdir(SRC)) if f.lower().endswith(".fbx")}
    stamp = {}
    if REBUILD_KIT == "changed" and os.path.exists(STAMP):
        stamp = json.load(open(STAMP, encoding="utf-8"))
    if REBUILD_KIT == "all" and eal.does_directory_exist(KIT):
        for path in eal.list_assets(KIT, recursive=False, include_folder=False):
            if not eal.delete_asset(path):
                log.append(f"could not delete {path}")
    hashes = {n: _md5(p) for n, p in fbx.items()}
    if REBUILD_KIT == "none":
        todo = []
    else:
        todo = [n for n in fbx if stamp.get(n) != hashes[n] or not eal.does_asset_exist(f"{KIT}/{n}")]
    stage = unreal.Paths.project_saved_dir() + "Ship/kit_changed"
    if os.path.isdir(stage):
        shutil.rmtree(stage)
    if todo:
        os.makedirs(stage)
        for n in todo:
            shutil.copyfile(fbx[n], os.path.join(stage, n + ".fbx"))
        g = {"SRC": stage, "DST": KIT, "NANITE": True, "__name__": "__main__"}
        exec(open(ROOT + "/tools/ue_scripts/import_kit.py").read(), g)       # Nanite on (the glass ones stay classic), complex-as-simple collision
        stamp.update({n: hashes[n] for n in todo})
        os.makedirs(os.path.dirname(STAMP), exist_ok=True)
        json.dump(stamp, open(STAMP, "w", encoding="utf-8"), indent=0)
    log.append(f"kit: {len(todo)} of {len(fbx)} meshes imported ({REBUILD_KIT})")
    return todo


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
    """The game's copy of the plan: the compartments (with their lamps), doors, graph, decks, stairs and lift; not the placements (this script's) nor the notes."""
    os.makedirs(DATA_DIR, exist_ok=True)
    slim = {k: v for k, v in PLAN_DATA.items() if k not in ("placements", "notes", "systems")}
    dst = DATA_DIR + "/aquila_plan.json"
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(slim, fh, separators=(",", ":"), ensure_ascii=False)
    log.append(f"plan copied to {dst} ({os.path.getsize(dst) // 1024} KB)")


# -------------------------------------------------------------------------------------------------------------------- the decks
def built_decks():
    """The decks that have placements in the plan (their stairs can be used)."""
    return {int(d) for d, v in PLAN_DATA["placements"].items() if v}


def deck_path(deck):
    return f"{DECK_DIR}/L_Deck{deck:02d}"


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
            above, below = (deck - 1) in built or deck == 2, (deck + 1) in built or deck == 12
            lock = lock or not (above and below)
        if lock:
            try:
                door.set_editor_property("locked", True)
                locked += 1
            except Exception as ex:
                log.append(f"door {d['id']}: could not lock ({ex})")
        door.set_actor_label(f"Door_{d['id']}")
        door.set_folder_path("Interior/Doors")
        n += 1
    return n, locked


def place_shell(deck):
    """The deck's placements as instances of their meshes in one AstraDeckShell (the current level)."""
    shell = eas.spawn_actor_from_class(unreal.AstraDeckShell, V(0, 0, 0), R())
    shell.set_editor_property("deck", deck)
    shell.set_actor_label(f"DeckShell_{deck:02d}")
    shell.set_folder_path("Interior")
    groups = {}
    for pl in PLAN_DATA["placements"].get(str(deck), []):
        groups.setdefault(pl["mesh"], []).append(pl)
    missing, classes = set(), {}
    for mesh_name, pls in sorted(groups.items()):
        asset = eal.load_asset(f"{KIT}/{mesh_name}")
        if asset is None:
            missing.add(mesh_name)
            continue
        transforms = [unreal.Transform(V(p["pos"][0] * M, p["pos"][1] * M, p["pos"][2] * M), R(yaw=p["yaw"]), V(1, 1, 1)) for p in pls]
        shell.add_instances_chunked(asset, transforms, CHUNK_M * M)
        for p in pls:
            classes[p["cls"]] = classes.get(p["cls"], 0) + 1
    if missing:
        raise RuntimeError(f"deck {deck}: meshes missing in {KIT}: {sorted(missing)}")
    return shell, classes


def build_deck_map(deck):
    """A map of its own for the deck: shell, doors; saved as L_Deck<NN>."""
    t0 = time.time()
    world = unreal.EditorLoadingAndSavingUtils.new_blank_map(False)
    shell, classes = place_shell(deck)
    doors, locked = place_doors(deck)
    row = {"placements": sum(classes.values()), "by_class": classes, "instances": shell.num_instances(), "components": shell.num_instance_components(),
           "distinct_meshes": shell.num_distinct_meshes(), "triangles": int(shell.count_triangles()), "doors": doors, "locked": locked}
    expect = len(PLAN_DATA["placements"].get(str(deck), []))
    if row["instances"] != expect:
        raise RuntimeError(f"deck {deck}: {row['instances']} instances for {expect} placements")
    path = deck_path(deck)
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, path):
        raise RuntimeError(f"could not save {path}")
    row["seconds"] = round(time.time() - t0, 1)
    return row


# -------------------------------------------------------------------------------------------------------------------- the level
def clear_deck_folders(world, decks):
    """The static actors and lights an older run put straight into the persistent level."""
    prefixes = tuple(f"Interior/Deck{d:02d}" for d in decks)
    n = 0
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith(prefixes):
            eas.destroy_actor(a)
            n += 1
    return n


def wire_streaming(world, decks):
    """The decks' maps as streaming levels of the persistent level (initially unloaded and hidden in the game; loaded in the editor)."""
    removed = 0
    for lv in unreal.EditorLevelUtils.get_levels(world):
        name = lv.get_outermost().get_name()
        if name.startswith(DECK_DIR + "/L_Deck") and any(name.endswith(f"L_Deck{d:02d}") for d in decks):
            if unreal.EditorLevelUtils.remove_level_from_world(lv):
                removed += 1
    added = []
    for d in decks:
        ls = unreal.EditorLevelUtils.add_level_to_world(world, deck_path(d), unreal.LevelStreamingDynamic)
        if ls is None:
            raise RuntimeError(f"could not add {deck_path(d)} to {LEVEL}")
        ls.set_editor_property("initially_loaded", False)
        ls.set_editor_property("initially_visible", False)
        added.append(d)
    log.append(f"streaming levels: {removed} old removed, decks {added} added (initially unloaded)")


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


def open_ready_room_wall():
    """The ready room's door is cut in the inner wall of the bridge's port corridor, whose modules the bridge builder (build_bridge_v3.py) placed as actors of L_Bridge: the
    window module and the two wall panels of its first bay (the door's) are removed; the deck's map has the module with the opening (SM_SHIP_BridgeCorridorDoor, ship_rooms_bridge.py)."""
    door = next((d for d in PLAN_DATA["doors"] if d["id"] == "ready_room_door"), None)
    if door is None or door.get("planned") or 1 not in DECKS:
        log.append("ready room: no door in the plan or Deck 1 not built here: the corridor is left as it is")
        return
    gone = []
    for a in eas.get_all_level_actors():
        label = a.get_actor_label()
        if label == "CorrPort_Window" or (label.startswith("CorrPort1_0_") and label.endswith("_R")):
            gone.append(label)
            eas.destroy_actor(a)
    log.append(f"ready room: {len(gone)} actors of the port corridor removed {sorted(gone)}" + ("" if gone else " (already open, or the corridor was built differently)"))


# ------------------------------------------------------------------------------------------------------------------------ run
if not eal.does_asset_exist(LEVEL):
    raise RuntimeError(f"{LEVEL} missing: build the bridge level first (build_bridge.py)")
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)         # nothing the editor holds is lost when the maps are swapped below
build_materials()
imported = import_kit()
bad = check_bounds()
log.append(f"kit: {len(MANIFEST['meshes'])} meshes in the manifest; {len(bad)} bounds problems")
copy_plan()
report = {}
for d in DECKS:                                                            # the decks' maps first (each one replaces the editor's map)
    report[d] = build_deck_map(d)
    log.append(f"deck {d}: {report[d]['instances']} instances in {report[d]['components']} components, {report[d]['doors']} doors ({report[d]['seconds']} s)")
world = unreal.EditorLoadingAndSavingUtils.load_map(LEVEL)
cleared = clear_deck_folders(world, DECKS)
log.append(f"{cleared} old actors of the decks {DECKS} removed from {LEVEL}")
if REMOVE_LIFT_LEAVES:
    open_existing_entrances()
if OPEN_READY_ROOM:
    open_ready_room_wall()
if 4 in DECKS:
    # the lift's Deck 4 stop is now the Mess Concourse's lift bank (the Mess Hall is reached from the concourse, not from its old alcove): the hangar's lift
    # sends the Captain there
    node = next((n for n in PLAN_DATA["graph"]["nodes"] if n["id"] == "lift.d4_concourse"), None)
    hangars = [a for a in eas.get_all_level_actors() if a.get_class().get_name() == "AstraHangar"]
    if node and hangars:
        for h in hangars:
            h.set_editor_property("mess_landing", V(node["p"][0] * M, node["p"][1] * M, node["p"][2] * M))
        log.append(f"mess landing -> lift.d4_concourse {node['p']}")
wire_streaming(world, DECKS)                                               # last: the persistent level is still the current level for the actors above
if SAVE_LEVEL:
    saved = unreal.EditorLoadingAndSavingUtils.save_map(world, LEVEL)
    saved_rest = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)     # the actors' own files (one file per actor) and the assets
    log.append(f"{LEVEL} saved: {saved}; the rest: {saved_rest}")
print(json.dumps({"log": log, "bounds_problems": bad, "decks": report,
                  "totals": {"instances": sum(r["instances"] for r in report.values()), "components": sum(r["components"] for r in report.values()),
                             "doors": sum(r["doors"] for r in report.values()), "triangles": sum(r["triangles"] for r in report.values())}}, indent=1))
