"""Import the Falcon's cockpit (art/blender/cockpit.py, export in art/export/cockpit) over the old one: /Game/ASTRA/Ships/Cockpit/SM_CRAFT_ASTRA_Falcon_Cockpit
(the path AstraFighterPawn loads), Nanite on, materials assigned by slot name from /Game/ASTRA/Materials/Instances, then a check of what came through.

The interior slots are the bridge v3's instances (MI_ASTRA_Structure / Trim / Rubber, MI_BRG3_Composite / DeckPlate / DarkGlass / Ivory / Leather / LampsDim / Lamps / Brass /
Decor: tools/ue_scripts/make_bridge_v3_materials.py), the outside is the Falcon's own hull (MI_HULL_A_Plate / Frame / Livery: make_ship_materials_v3.py). Run those first.
  tools/ue.py pyfile tools/ue_scripts/import_cockpit.py
It stops with an error, before touching anything, when an instance is missing.
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = globals().get("SRC", ROOT + "/art/export/cockpit")
DST = "/Game/ASTRA/Ships/Cockpit"
NANITE = True                                                       # (read by import_kit.py: opaque materials only, so the mesh is a Nanite mesh)
NAME = "SM_CRAFT_ASTRA_Falcon_Cockpit"
MI = "/Game/ASTRA/Materials/Instances"
EXPECTED = ["MI_ASTRA_Structure", "MI_ASTRA_Trim", "MI_ASTRA_Rubber", "MI_BRG3_Composite", "MI_BRG3_DeckPlate", "MI_BRG3_DarkGlass", "MI_BRG3_Ivory", "MI_BRG3_Leather",
            "MI_BRG3_LampsDim", "MI_BRG3_Lamps", "MI_BRG3_Brass", "MI_BRG3_Decor", "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Livery"]

eal = unreal.EditorAssetLibrary
if not os.path.exists(f"{SRC}/{NAME}.fbx"):
    raise RuntimeError(f"{SRC}/{NAME}.fbx is missing: blender -b --factory-startup --python-exit-code 1 -P art/blender/cockpit.py -- art/export/cockpit")
missing = [m for m in EXPECTED if not eal.does_asset_exist(f"{MI}/{m}")]
if missing:
    raise RuntimeError("material instances missing (run make_bridge_v3_materials.py and make_ship_materials_v3.py first): " + ", ".join(missing))

# the generic kit import does the work (import, Nanite, slots -> instances, collision); it leaves the other assets of the folder alone
exec(compile(open(ROOT + "/tools/ue_scripts/import_kit.py", encoding="utf-8").read(), "import_kit.py", "exec"), globals())

mesh = eal.load_asset(f"{DST}/{NAME}")
slots = [str(m.get_editor_property("material_slot_name")) for m in mesh.get_editor_property("static_materials")]
unknown = [s for s in slots if s not in EXPECTED]
bb = mesh.get_bounding_box()
print(json.dumps({"mesh": NAME, "slots": slots, "slots_not_in_the_expected_list": unknown, "nanite": mesh.get_editor_property("nanite_settings").enabled,
                  "bounds_cm": [[round(bb.min.x), round(bb.min.y), round(bb.min.z)], [round(bb.max.x), round(bb.max.y), round(bb.max.z)]]}, indent=1))
