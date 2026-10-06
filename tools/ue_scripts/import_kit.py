"""Import an ASTRA kit (FBX folder) into Unreal: Nanite on, complex-as-simple collision, report bounds/slots.
Run inside the editor: tools/ue.py pyfile tools/ue_scripts/import_kit.py  (edit SRC/DST below or set globals first)."""
import json
import os

import unreal

SRC = globals().get("SRC", "/Users/beltromatti/Desktop/ASTRA/art/export/kit_corridor")
DST = globals().get("DST", "/Game/ASTRA/Kit/Interior/Corridor")
NANITE = globals().get("NANITE", True)   # off for translucent/additive props (holograms)

tasks = []
imported = {os.path.splitext(f)[0] for f in os.listdir(SRC) if f.lower().endswith(".fbx")}   # only these are touched below
for f in sorted(os.listdir(SRC)):
    if f.lower().endswith(".fbx"):
        t = unreal.AssetImportTask()
        t.filename = os.path.join(SRC, f)
        t.destination_path = DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)

import importlib  # noqa: E402
import astra_editor  # noqa: E402
importlib.reload(astra_editor)
materials = astra_editor.assign_materials_by_slot(DST, asset_paths=[f"{DST}/{name}" for name in sorted(imported)])

report = []
eal = unreal.EditorAssetLibrary
for path in eal.list_assets(DST, recursive=False, include_folder=False):
    asset = eal.load_asset(path)
    if not isinstance(asset, unreal.StaticMesh) or asset.get_name() not in imported:
        continue
    ns = asset.get_editor_property("nanite_settings")
    # Nanite draws only opaque and masked materials: a mesh with a translucent slot (glass) stays a classic mesh (as a
    # Nanite mesh it would be drawn from its coarse fallback)
    slots_mi = [m.get_editor_property("material_interface") for m in asset.get_editor_property("static_materials")]
    translucent = any(mi and mi.get_base_material().get_editor_property("blend_mode") not in
                      (unreal.BlendMode.BLEND_OPAQUE, unreal.BlendMode.BLEND_MASKED) for mi in slots_mi)
    is_glass = "Glass" in asset.get_name() or translucent
    ns.enabled = NANITE and not is_glass
    asset.set_editor_property("nanite_settings", ns)
    body = asset.get_editor_property("body_setup")
    if body:
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    bb = asset.get_bounding_box()
    slots = [str(m.get_editor_property("material_slot_name")) for m in asset.get_editor_property("static_materials")]
    astra_editor.save(asset)
    report.append({"mesh": asset.get_name(), "nanite": ns.enabled,
                   "min": [round(bb.min.x), round(bb.min.y), round(bb.min.z)],
                   "max": [round(bb.max.x), round(bb.max.y), round(bb.max.z)], "slots": slots})
others = [p for p in eal.list_assets(DST, recursive=False, include_folder=False)
          if not isinstance(eal.load_asset(p), unreal.StaticMesh)]
print(json.dumps({"meshes": report, "materials": materials, "other_assets": others}, indent=1))
