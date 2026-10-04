"""Flags the base materials of what the living space draws as instances "Used with Instanced Static Meshes" (docs/SPAZIO.md), once, in the editor:
  tools/ue.py pyfile tools/ue_scripts/make_space_materials.py

What the war leaves (Source/ASTRA/AstraWrecks.h, AstraSpaceLifeWrecks.cpp) is drawn as instances of meshes: the three sections of each broken capital ship (/Game/ASTRA/Ships/Sections:
SM_SHIP_<faction>_<name>_Sec<Bow|Mid|Stern>), the whole hulls of ships the war could not break into sections, the chunks of debris and the lifepods (/Game/ASTRA/Space: SM_DEBRIS_*, SM_POD_*),
as well as the civilian hulls, the rocks and the buoys. An instance of a
Nanite mesh is shaded with its material only if the material is flagged for instanced meshes; in a game the engine cannot set the flag (only an editor that is not playing does, on first use),
and an unflagged material is drawn as the default grey. The game checks it (GetUsageByFlag) and leaves out what it cannot shade, saying so in the log:
  [Space] SM_...: its materials (...) are not flagged 'Used with Instanced Static Meshes' (tools/ue_scripts/make_scala_materials.py): ...

The base material of each slot of each mesh is the one that gets it (M_ASTRA_HullV3, M_ASTRA_ShipLight, M_ASTRA_ShipGlass, the cut faces' and the windows' materials...); the flag is saved with the
asset. Safe to run again (it says what it changed and changes nothing that is already set). After it: restart the game (the instanced shader permutations compile once; the first run after it
hitches while they do).
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

# the folders of meshes the living space draws as instances (every static mesh in them, whatever their number: a new class's sections are covered without a change here). /Game/ASTRA/Ships holds
# the whole hulls too (what the war's older explosion leaves of a ship that did not break into sections is her whole hull, burnt dark) and, in Sections, the three pieces of each
FOLDERS = ["/Game/ASTRA/Ships", "/Game/ASTRA/Space"]
# meshes that are places (a few hundred thousand triangles each, one of a kind: they are actors, not instances) need nothing, but flagging them is harmless
report = {"meshes": 0, "changed": [], "already": [], "unreadable": [], "no_materials": []}
seen = set()


def base_of(mi):
    """The material an instance chain ends in."""
    if hasattr(mi, "get_base_material"):
        try:
            return mi.get_base_material()
        except Exception:
            pass
    while isinstance(mi, unreal.MaterialInstance):
        mi = mi.get_editor_property("parent")
    return mi


for folder in FOLDERS:
    if not eal.does_directory_exist(folder):
        report["unreadable"].append(f"{folder} (not there yet: the meshes are imported by import_space_v3.py, and the sections by the ship scripts)")
        continue
    for path in eal.list_assets(folder, recursive=True, include_folder=False):
        mesh = eal.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            continue
        report["meshes"] += 1
        slots = mesh.get_editor_property("static_materials")
        if not slots:
            report["no_materials"].append(mesh.get_name())
            continue
        for sm in slots:
            mi = sm.get_editor_property("material_interface")
            base = base_of(mi) if mi else None
            if base is None or base.get_path_name() in seen:
                continue
            seen.add(base.get_path_name())
            if base.get_editor_property("used_with_instanced_static_meshes"):
                report["already"].append(base.get_name())
                continue
            base.set_editor_property("used_with_instanced_static_meshes", True)
            mel.recompile_material(base)
            eal.save_loaded_asset(base, only_if_is_dirty=False)
            report["changed"].append(base.get_name())

print(json.dumps(report, indent=1))
print("SPACE_MATERIALS_" + ("OK" if report["meshes"] > 0 and not report["no_materials"] else "CHECK"))
