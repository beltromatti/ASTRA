"""Import the living space's meshes (art/export/space_v3, see art/blender/spacegen3.py and docs/SPAZIO.md) into /Game/ASTRA/Space: the places (Keeper Station with its turning ring,
the Arsenal with its crane, the Tiberius refinery, the Ceres mining station), the civilian hulls of the traffic, the rocks of the belt, the debris, the escape pods, the lane buoy.

Nanite on, no collision of any kind (the game draws them as instances and the battle simulation does their collision: nothing is cooked from a 600 k triangle station), lightmap UV
generation off, materials assigned by slot name from /Game/ASTRA/Materials/Instances (the hull instances MI_HULL_<A|M|G>_*: run make_ship_materials_v3.py first). The rocks' three
instances (MI_SPACE_Rock, MI_SPACE_Ore, MI_SPACE_Ice: children of M_ASTRA_HullV3, their paint in the manifest) are made here.

It imports one mesh at a time and checks what came through: triangles, the three UV sets, the bounds against the manifest, the slots. Set ONLY = ["SM_PLACE_Keeper", ...] (full names, or
the part after the second underscore) before running to do a few.
  tools/ue.py pyfile tools/ue_scripts/import_space_v3.py
Afterwards: python3 tools/space.py meshes art/export/space_v3/manifest.json  (the table of lamps, bells and berths the game reads) -- already in the repo, only needed after a rebuild.
Then, once, tools/ue.py pyfile tools/ue_scripts/make_space_materials.py: flags the hulls' base materials for instancing (what the war leaves is drawn as instances: the sections of broken ships,
the debris, the lifepods, and the traffic's vessels and the belt's rocks).
"""
import json
import os
import time

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = globals().get("SRC", ROOT + "/art/export/space_v3")
DST = "/Game/ASTRA/Space"
MI = "/Game/ASTRA/Materials/Instances"
MAT = "/Game/ASTRA/Materials"
ONLY = globals().get("ONLY")

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
manifest = json.load(open(SRC + "/manifest.json", encoding="utf-8"))
report = {"imported": [], "problems": [], "notes": [], "materials": []}


def wanted(name):
    return not ONLY or any(o == name or name.endswith("_" + o) or name.split("_", 2)[-1] == o for o in ONLY)


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


# ------------------------------------------------------------------------------------------------------ the rocks' instances
def make_space_instances():
    parent = eal.load_asset(f"{MAT}/M_ASTRA_HullV3")
    if parent is None:
        raise RuntimeError("M_ASTRA_HullV3 is missing: run make_ship_materials_v3.py first")
    for name, spec in manifest.get("materials", {}).items():
        p = f"{MI}/{name}"
        inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mel.set_material_instance_parent(inst, parent)
        for k, v in dict(RoughMin=spec["rough_min"], RoughMax=spec["rough_max"], MetallicBias=spec["metallic"], ToneAmount=spec["tone"], WearThreshold=0.52,
                         GrimeGain=spec["grime"], BCInfluence=0.0).items():
            mel.set_material_instance_scalar_parameter_value(inst, k, v)
        mel.set_material_instance_vector_parameter_value(inst, "Tint", unreal.LinearColor(*lin(spec["tint"]), 1.0))
        mel.set_material_instance_vector_parameter_value(inst, "BareTint", unreal.LinearColor(*lin(spec["bare"]), 1.0))
        mel.update_material_instance(inst)
        eal.save_loaded_asset(inst, only_if_is_dirty=False)
        report["materials"].append(name)


make_space_instances()

# ------------------------------------------------------------------------------------------------------ preflight
missing = set()
for name, e in manifest["meshes"].items():
    if not wanted(name):
        continue
    for slot in e["slots"]:
        if not eal.does_asset_exist(f"{MI}/{slot}"):
            missing.add(slot)
if missing:
    raise RuntimeError("material instances missing (run make_ship_materials_v3.py first): " + ", ".join(sorted(missing)))


def fbx_options():
    """Legacy FBX options: static mesh, no materials or textures, no lightmap UVs, no collision, Nanite. Returns (options or None, notes)."""
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

# ------------------------------------------------------------------------------------------------------------ import
order = sorted([n for n in manifest["meshes"] if wanted(n)], key=lambda n: -manifest["meshes"][n]["tris"])
for name in order:
    e = manifest["meshes"][name]
    t0 = time.time()
    task = unreal.AssetImportTask()
    task.filename = os.path.join(SRC, e["file"])
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
    report["imported"].append({"mesh": name, "s": round(time.time() - t0, 1), "tris_manifest": e["tris"]})
    print(f"imported {name} ({e['tris']:,} tris) in {time.time() - t0:.0f}s", flush=True)

# ---------------------------------------------------------------------------------------------------- post-process
import importlib  # noqa: E402
import astra_editor  # noqa: E402
importlib.reload(astra_editor)
if eal.does_directory_exist(DST):
    astra_editor.assign_materials_by_slot(DST)

for row in report["imported"]:
    name = row["mesh"]
    e = manifest["meshes"][name]
    asset = eal.load_asset(f"{DST}/{name}")
    if not isinstance(asset, unreal.StaticMesh):
        report["problems"].append(f"{name}: not a static mesh")
        continue
    ns = asset.get_editor_property("nanite_settings")
    ns.enabled = True
    asset.set_editor_property("nanite_settings", ns)
    body = asset.get_editor_property("body_setup")
    if body:                                                                  # no collision shapes, and none cooked from the render mesh
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
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
            report["problems"].append(f"{name}: {n_uv} UV channels (3 expected: box UV, wear/grime, tone/aux); 4 means Unreal generated lightmap UVs")
    except Exception as ex:
        report["notes"].append(f"{name}: description checks skipped ({ex})")
    astra_editor.save(asset)

print(json.dumps(report, indent=1))
