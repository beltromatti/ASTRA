"""Import the v3 ships (art/export/ships_v3, see art/blender/shipgen3.py) into /Game/ASTRA/Ships, replacing the v2 meshes in place
(same asset names, so the game keeps working) and the section pieces of the capital ships as new assets in /Game/ASTRA/Ships/Sections
(SM_SHIP_<Faction>_<Name>_Sec<Bow|Mid|Stern>). Nanite on, complex-as-simple collision, materials assigned by slot name from
/Game/ASTRA/Materials/Instances (run make_ship_materials_v3.py first), lightmap UV generation off (Nanite ships need none, and with
millions of tiny UV islands the packing would never finish).

It imports one mesh at a time (a 2-3 M triangle ship takes a few minutes to build its Nanite data) and checks what came through:
triangles, the three UV sets (UV1 = wear/grime, UV2 = tone/soot: the hull material reads them), bounds against the manifest, missing
material instances. Set ONLY = ["SM_SHIP_ASTRA_Aquila", ...] (names or short names) before running to do a few; NO_SECTIONS = True to
skip the pieces.
  tools/ue.py pyfile tools/ue_scripts/import_ships_v3.py
Afterwards: tools/ue.py pyfile tools/ue_scripts/extract_nav_lights.py (the running lights follow the new hulls).
"""
import json
import os
import time

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = globals().get("SRC", ROOT + "/art/export/ships_v3")
DST = "/Game/ASTRA/Ships"
SEC = DST + "/Sections"
MI = "/Game/ASTRA/Materials/Instances"
ONLY = globals().get("ONLY")
NO_SECTIONS = globals().get("NO_SECTIONS", False)

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
manifest = json.load(open(SRC + "/manifest.json", encoding="utf-8"))
report = {"imported": [], "problems": [], "notes": []}


def wanted(name, entry):
    if NO_SECTIONS and entry["class"] == "section":
        return False
    if not ONLY:
        return True
    of = entry.get("of", name)
    return any(o in (name, of, name.split("_")[-1], of.split("_")[-1]) for o in ONLY)


# ------------------------------------------------------------------------------------------------------ preflight
missing = set()
for name, e in manifest["meshes"].items():
    if not wanted(name, e):
        continue
    for slot in e["slots"]:
        if not eal.does_asset_exist(f"{MI}/{slot}"):
            missing.add(slot)
if missing:
    raise RuntimeError("material instances missing (run make_ship_materials_v3.py first): " + ", ".join(sorted(missing)))


def fbx_options():
    """Legacy FBX options: static mesh, no materials or textures, no lightmap UVs, Nanite. Returns (options or None, notes)."""
    notes = []
    try:
        ui = unreal.FbxImportUI()
        for k, v in (("import_mesh", True), ("import_textures", False), ("import_materials", False), ("import_as_skeletal", False),
                     ("automated_import_should_detect_type", False)):
            try:
                ui.set_editor_property(k, v)
            except Exception as ex:
                notes.append(f"FbxImportUI.{k}: {ex}")
        try:
            ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
        except Exception as ex:
            notes.append(f"mesh_type_to_import: {ex}")
        data = ui.get_editor_property("static_mesh_import_data")
        for k, v in (("combine_meshes", True), ("generate_lightmap_u_vs", False), ("auto_generate_collision", False), ("build_nanite", True),
                     ("remove_degenerates", False), ("one_convex_hull_per_ucx", False),
                     ("normal_import_method", getattr(getattr(unreal, "FBXNormalImportMethod", None), "FBXNIM_IMPORT_NORMALS", None))):   # keep the smooth shading of domes and bells
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

# ------------------------------------------------------------------------------------------------------------ import
order = sorted([n for n, e in manifest["meshes"].items() if wanted(n, e)], key=lambda n: (manifest["meshes"][n]["class"] == "section", n))
for name in order:
    e = manifest["meshes"][name]
    dest = SEC if e["class"] == "section" else DST
    t0 = time.time()
    task = unreal.AssetImportTask()
    task.filename = os.path.join(SRC, e["file"])
    task.destination_path = dest
    task.automated = True
    task.replace_existing = True
    task.replace_existing_settings = True
    task.save = False
    if OPTIONS is not None:
        task.options = OPTIONS
    tools.import_asset_tasks([task])
    path = f"{dest}/{name}"
    if not eal.does_asset_exist(path):
        report["problems"].append(f"{name}: not imported")
        continue
    report["imported"].append({"mesh": name, "s": round(time.time() - t0, 1), "tris_manifest": e["tris"]})
    print(f"imported {name} ({e['tris']:,} tris) in {time.time() - t0:.0f}s", flush=True)

# ---------------------------------------------------------------------------------------------------- post-process
import importlib  # noqa: E402
import astra_editor  # noqa: E402
importlib.reload(astra_editor)
subsystem = None
try:
    subsystem = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
except Exception as ex:
    report["notes"].append(f"StaticMeshEditorSubsystem unavailable: {ex}")

for folder in (DST, SEC):
    if eal.does_directory_exist(folder):
        astra_editor.assign_materials_by_slot(folder)

for row in report["imported"]:
    name = row["mesh"]
    e = manifest["meshes"][name]
    path = f"{SEC if e['class'] == 'section' else DST}/{name}"
    asset = eal.load_asset(path)
    if not isinstance(asset, unreal.StaticMesh):
        report["problems"].append(f"{name}: not a static mesh")
        continue
    ns = asset.get_editor_property("nanite_settings")
    ns.enabled = True
    asset.set_editor_property("nanite_settings", ns)
    body = asset.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    slots = [str(m.get_editor_property("material_slot_name")) for m in asset.get_editor_property("static_materials")]
    row["slots"] = slots
    if set(slots) != set(e["slots"]):
        report["problems"].append(f"{name}: slots {slots} differ from the manifest {e['slots']}")
    bb = asset.get_bounding_box()
    lo, hi = e["bounds_m"]["min"], e["bounds_m"]["max"]
    got = [bb.min.x / 100, bb.min.y / 100, bb.min.z / 100, bb.max.x / 100, bb.max.y / 100, bb.max.z / 100]
    want = lo + hi
    tol = 0.02 * max(abs(v) for v in want) + 0.5
    if any(abs(a - b) > tol for a, b in zip(got, want)):
        report["problems"].append(f"{name}: bounds {[round(v, 1) for v in got]} differ from the manifest {want}")
    row["bounds_m"] = [round(v, 2) for v in got]
    try:
        desc = asset.get_static_mesh_description(0)
        row["tris"] = desc.get_triangle_count()
        n_uv = desc.get_num_uv_channels() if hasattr(desc, "get_num_uv_channels") else None
        row["uv_channels"] = n_uv
        if n_uv is not None and n_uv != 3:
            report["problems"].append(f"{name}: {n_uv} UV channels (3 expected: box UV, wear/grime, tone/soot); 4 means Unreal generated lightmap UVs")
        # the data channels must carry values: sample a few thousand vertex instances
        vi_count = desc.get_vertex_instance_count()
        step = max(1, vi_count // 4000)
        seen = [0.0, 0.0, 0.0, 0.0]
        for i in range(0, vi_count, step):
            u1 = desc.get_vertex_instance_uv(unreal.VertexInstanceID(i), 1)
            u2 = desc.get_vertex_instance_uv(unreal.VertexInstanceID(i), 2)
            seen[0] = max(seen[0], u1.x)
            seen[1] = max(seen[1], u1.y)
            seen[2] = max(seen[2], u2.x)
            seen[3] = max(seen[3], u2.y)
        row["data_channels_max"] = [round(v, 3) for v in seen]
        if seen[0] <= 0.0 and seen[2] <= 0.0 and e["class"] != "craft":
            report["problems"].append(f"{name}: UV1/UV2 are empty: the wear and tone data did not come through")
    except Exception as ex:
        report["notes"].append(f"{name}: description checks skipped ({ex})")
    astra_editor.save(asset)

print(json.dumps(report, indent=1))
