"""Flags the craft's hull materials "Used with Instanced Static Meshes" (docs/SCALA.md), once, in the editor:  tools/ue.py pyfile tools/ue_scripts/make_scala_materials.py

The war draws its craft as instances of their meshes (Source/ASTRA/AstraWarDraw.cpp: one instanced component for each kind of hull, no actor for a craft).
An instance of a Nanite mesh is shaded with its material only if the material is flagged for instanced meshes; in a game the engine cannot set the flag (only an
editor that is not playing does, on first use), and an unflagged material is drawn as the default grey. So the flag is made here and saved with the asset: for each
slot of each craft mesh, the base material of the instance (M_ASTRA_HullV3, M_ASTRA_ShipLight, M_ASTRA_ShipGlass...) gets it.

Safe to run again (it says what it changed and changes nothing that is already set). Until it has been run the game keeps the craft as actors and says so in the log:
  [WarDraw] SM_CRAFT_...: its materials (...) are not flagged 'Used with Instanced Static Meshes', so its craft stay actors
After it: restart the game (the shaders for the instanced permutation compile once; the first run after it hitches for a minute while they do).
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary

# every mesh the war draws as instances (the craft); add a hull here to give it the same
MESHES = ["SM_CRAFT_ASTRA_Falcon", "SM_CRAFT_ASTRA_Hammer", "SM_CRAFT_ASTRA_Wasp", "SM_CRAFT_MANDATE_Harpy"]
# the war's own materials are made with the flag already (make_war_fx.py); named here only to be checked
WAR = ["M_WAR_Glow", "M_WAR_Tube", "M_WAR_Dart", "M_WAR_Fire", "M_WAR_Smoke", "M_WAR_Plume", "M_WAR_Debris"]

report = {"changed": [], "already": [], "missing": [], "war_unflagged": []}
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


for name in MESHES:
    mesh = eal.load_asset(f"/Game/ASTRA/Ships/{name}")
    if mesh is None:
        report["missing"].append(name)
        continue
    for sm in mesh.get_editor_property("static_materials"):
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

for name in WAR:
    m = eal.load_asset(f"/Game/ASTRA/Materials/{name}")
    if m is not None and not m.get_editor_property("used_with_instanced_static_meshes"):
        report["war_unflagged"].append(name)

print(json.dumps(report, indent=1))
print("SCALA_MATERIALS_" + ("OK" if not report["missing"] and not report["war_unflagged"] else "CHECK"))
