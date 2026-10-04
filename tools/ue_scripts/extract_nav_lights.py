"""Where each ship's navigation lights go, read from its own hull: the widest points amidships (port red, starboard
green), the highest point (the white strobe), the lowest amidships (the red belly strobe), the stern and the bow. Mesh
space, centimetres, +X the bow, +Y starboard. Writes data/ship/nav_lights.json (the game loads it: UAstraNavLights).

The points are made by the ship generator (art/blender/shipgen3.py: each exported mesh's manifest entry carries a `nav`
record, worked out from the mesh's own vertices in the Unreal frame) and only gathered here: **no asset is opened, so none
is dirtied or saved** (this script used to load every ship mesh into the editor and read its mesh description, which
marked all of them modified). Run it after shipgen3.py, with or without the editor:
  python3 tools/ue_scripts/extract_nav_lights.py [path/to/manifest.json]
  tools/ue.py pyfile tools/ue_scripts/extract_nav_lights.py              (the same, inside the editor's Python)
Only the ships in the manifest and carrying a `nav` record are written; the others keep the entry they had.
"""
import json
import os
import sys

try:
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:                                                       # (run from a string, as the editor's remote execution does)
    ROOT = "/Users/beltromatti/Desktop/ASTRA"
if not os.path.isdir(os.path.join(ROOT, "data", "ship")):
    ROOT = "/Users/beltromatti/Desktop/ASTRA"

MANIFEST = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".json") else os.path.join(ROOT, "art", "export", "ships_v3", "manifest.json")
TARGETS = (os.path.join(ROOT, "data", "ship", "nav_lights.json"), os.path.join(ROOT, "Content", "ASTRA", "Data", "nav_lights.json"))   # the source, and the game's copy


def main() -> int:
    if not os.path.exists(MANIFEST):
        print(f"no manifest at {MANIFEST}: run art/blender/shipgen3.py first (blender -b --factory-startup -P art/blender/shipgen3.py -- art/export/ships_v3)")
        return 1
    meshes = json.load(open(MANIFEST, encoding="utf-8")).get("meshes", {})
    fresh = {n: e["nav"] for n, e in meshes.items() if "nav" in e and e.get("class") in ("capital", "craft", "station")}
    if not fresh:
        print(f"the manifest {MANIFEST} has no `nav` records: it was made by a shipgen3.py from before they existed. Run shipgen3.py again (all ships, or --only the ones that changed): "
              "nothing was written.")
        return 1
    out = {}
    if os.path.exists(TARGETS[0]):
        out = json.load(open(TARGETS[0], encoding="utf-8"))
    changed = [n for n, v in fresh.items() if out.get(n) != v]
    out.update(fresh)
    os.makedirs(os.path.dirname(TARGETS[0]), exist_ok=True)
    for path in TARGETS:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    kept = [n for n in out if n not in fresh]
    print(f"nav lights of {len(fresh)} ships from the manifest ({len(changed)} changed: {', '.join(sorted(changed)) or 'none'}); kept as they were: {', '.join(sorted(kept)) or 'none'}")
    print(json.dumps({k: v["length_m"] for k, v in out.items()}))
    return 0


if __name__ == "__main__" and "unreal" not in sys.modules:
    sys.exit(main())                                                    # (from a terminal: the exit code says whether something was written)
else:
    main()                                                              # (in the editor's Python: no SystemExit to be taken for a failure)
