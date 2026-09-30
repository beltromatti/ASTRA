"""Level L_Bridge: the ASN Aquila bridge assembled from data/ship/aquila_bridge.json (single source of truth).
Unreal convention = data convention (X forward, Y starboard, Z up); data in metres, Unreal in cm.

Version 3 of the data (the futuristic bridge of art/blender/bridge_v3.py) is built by build_bridge_v3.py; this script only
dispatches, so the command the notes know stays the same:  tools/ue.py pyfile tools/ue_scripts/build_bridge.py
(before it: art/blender/bridge_v3.py and tools/ue_scripts/make_bridge_v3_materials.py, see build_bridge_v3.py).
The version 2 build (art/blender/bridge.py meshes) is in git history: git show 046211b:tools/ue_scripts/build_bridge.py
"""
import json
import os

ROOT = "/Users/beltromatti/Desktop/ASTRA"
_data = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_bridge.json"), encoding="utf-8"))
if _data.get("version", 2) < 3:
    raise RuntimeError("data/ship/aquila_bridge.json is version 2: use git show 046211b:tools/ue_scripts/build_bridge.py")
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "build_bridge_v3.py")).read())
