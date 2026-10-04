"""Import the boarding kit (ABBORDAGGI-3: the pieces a boarded ship's decks are dressed with) into /Game/ASTRA/Kit/Board. Run in the editor, after make_board_materials.py:
  blender -b --factory-startup -P art/blender/board_kit.py        (builds the FBX files in art/export/board and writes data/ship/board_kit.json)
  tools/ue.py pyfile tools/ue_scripts/make_board_materials.py     (once)
  tools/ue.py pyfile tools/ue_scripts/import_board_kit.py

Nanite on (the pieces are small, opaque and instanced by the hundred), no collision of their own (the game gives the solid ones a box: AstraBoardDress), lightmap UV generation off, the materials assigned by
slot name from /Game/ASTRA/Materials/Instances. What came through is checked against data/ship/board_kit.json (the generator's own account: triangles, bounds in cm, slots) and the report lists the
differences. Set ONLY = ["SM_BRD_Crate", ...] before running to do a few.
"""
import json
import os
import time

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = globals().get("SRC", ROOT + "/art/export/board")
DST = "/Game/ASTRA/Kit/Board"
MI = "/Game/ASTRA/Materials/Instances"
ONLY = globals().get("ONLY")

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
kit = json.load(open(ROOT + "/data/ship/board_kit.json", encoding="utf-8"))
pieces = {p["mesh"]: p for p in kit["pieces"].values()}
report = {"imported": [], "problems": [], "notes": []}


def wanted(name):
    return not ONLY or name in ONLY


# ------------------------------------------------------------------------------------------------------------------------------ preflight
missing_files = [n for n in pieces if wanted(n) and not os.path.exists(os.path.join(SRC, n + ".fbx"))]
if missing_files:
    raise RuntimeError("FBX files missing in " + SRC + " (run art/blender/board_kit.py): " + ", ".join(missing_files))
missing_mi = set()
for name, p in pieces.items():
    if wanted(name):
        for slot in p["slots"]:
            if not eal.does_asset_exist(f"{MI}/{slot}"):
                missing_mi.add(slot)
if missing_mi:
    raise RuntimeError("material instances missing (run make_board_materials.py, make_bridge_v3_materials.py): " + ", ".join(sorted(missing_mi)))


def fbx_options():
    """Legacy FBX options: static mesh, no materials or textures, no lightmap UVs, Nanite, no generated collision. Returns (options or None, notes)."""
    notes = []
    try:
        ui = unreal.FbxImportUI()
        for k, v in (("import_mesh", True), ("import_textures", False), ("import_materials", False), ("import_as_skeletal", False), ("automated_import_should_detect_type", False)):
            try:
                ui.set_editor_property(k, v)
            except Exception as ex:
                notes.append(f"FbxImportUI.{k}: {ex}")
        try:
            ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        except Exception as ex:
            notes.append(f"mesh_type_to_import: {ex}")
        data = ui.get_editor_property("static_mesh_import_data")
        for k, v in (("combine_meshes", True), ("generate_lightmap_u_vs", False), ("auto_generate_collision", False), ("build_nanite", True), ("remove_degenerates", False),
                     ("normal_import_method", getattr(getattr(unreal, "FBXNormalImportMethod", None), "FBXNIM_IMPORT_NORMALS", None))):
            if v is None:
                continue
            try:
                data.set_editor_property(k, v)
            except Exception as ex:
                notes.append(f"static_mesh_import_data.{k}: {ex}")
        return ui, notes
    except Exception as ex:
        return None, [f"FbxImportUI unavailable ({ex}): default options"]


OPTIONS, NOTES = fbx_options()
report["notes"] += NOTES

# ------------------------------------------------------------------------------------------------------------------------------ import
for name in sorted(n for n in pieces if wanted(n)):
    t0 = time.time()
    task = unreal.AssetImportTask()
    task.filename = os.path.join(SRC, name + ".fbx")
    task.destination_path = DST
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    if OPTIONS is not None:
        task.options = OPTIONS
    tools.import_asset_tasks([task])
    if not eal.does_asset_exist(f"{DST}/{name}"):
        report["problems"].append(f"{name}: not imported")
        continue
    report["imported"].append({"mesh": name, "s": round(time.time() - t0, 1)})

# ------------------------------------------------------------------------------------------------------------------------------ post-process
import importlib  # noqa: E402
import astra_editor  # noqa: E402
importlib.reload(astra_editor)
astra_editor.assign_materials_by_slot(DST)

for row in report["imported"]:
    name = row["mesh"]
    p = pieces[name]
    asset = eal.load_asset(f"{DST}/{name}")
    if not isinstance(asset, unreal.StaticMesh):
        report["problems"].append(f"{name}: not a static mesh")
        continue
    ns = asset.get_editor_property("nanite_settings")
    ns.enabled = True
    asset.set_editor_property("nanite_settings", ns)
    slots = [str(m.get_editor_property("material_slot_name")) for m in asset.get_editor_property("static_materials")]
    row["slots"] = slots
    if set(slots) != set(p["slots"]):
        report["problems"].append(f"{name}: slots {slots} differ from the kit's {p['slots']}")
    bb = asset.get_bounding_box()
    got = [bb.min.x, bb.min.y, bb.min.z, bb.max.x, bb.max.y, bb.max.z]
    want = p["min_cm"] + p["max_cm"]
    if any(abs(a - b) > 1.5 for a, b in zip(got, want)):
        report["problems"].append(f"{name}: bounds {[round(v, 1) for v in got]} differ from the kit's {want} (the importer's axes?)")
    row["bounds_cm"] = [round(v, 1) for v in got]
    try:
        row["tris"] = asset.get_static_mesh_description(0).get_triangle_count()
        if abs(row["tris"] - p["tris"]) > max(8, p["tris"] // 20):
            report["problems"].append(f"{name}: {row['tris']} triangles, the kit says {p['tris']}")
    except Exception as ex:
        report["notes"].append(f"{name}: triangle count skipped ({ex})")
    astra_editor.save(asset)

print(json.dumps(report, indent=1))
