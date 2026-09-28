"""Where each ship's navigation lights go, read from its own hull: the widest points amidships (port red, starboard
green), the highest point (the white strobe), the lowest (the red belly strobe), the stern and the bow. Mesh space,
centimetres, +X the bow, +Y starboard. Writes data/ship/nav_lights.json (the game loads it: UAstraNavLights).
  tools/ue.py pyfile tools/ue_scripts/extract_nav_lights.py
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
eal = unreal.EditorAssetLibrary
out = {}
for path in eal.list_assets("/Game/ASTRA/Ships", recursive=False):
    name = path.split("/")[-1].split(".")[0]
    if not (name.startswith("SM_SHIP_") or name.startswith("SM_CRAFT_") or name.startswith("SM_STATION_")):
        continue
    sm = eal.load_asset(path)
    desc = sm.get_static_mesh_description(0)
    n = desc.get_vertex_count()
    pts = []
    step = max(1, n // 60000)          # enough samples on the big hulls
    for i in range(0, n, step):
        p = desc.get_vertex_position(unreal.VertexID(i))
        pts.append((p.x, p.y, p.z))
    if not pts:
        continue
    xs = [p[0] for p in pts]
    x0, x1 = min(xs), max(xs)
    L = x1 - x0
    mid = [p for p in pts if abs(p[0] - (x0 + x1) / 2) < 0.3 * L] or pts
    centre = [p for p in pts if abs(p[1]) < 0.12 * (max(q[1] for q in pts) - min(q[1] for q in pts)) + 1] or pts
    port = min(mid, key=lambda p: p[1])
    star = max(mid, key=lambda p: p[1])
    top = max(pts, key=lambda p: p[2])
    belly = min(mid, key=lambda p: p[2])
    stern = min(centre, key=lambda p: p[0])
    bow = max(centre, key=lambda p: p[0])
    r = lambda p: [round(p[0], 1), round(p[1], 1), round(p[2], 1)]
    out[name] = {"port": r(port), "starboard": r(star), "top": r(top), "belly": r(belly), "stern": r(stern), "bow": r(bow),
                 "length_m": round(L / 100.0, 1)}
os.makedirs(f"{ROOT}/data/ship", exist_ok=True)
with open(f"{ROOT}/data/ship/nav_lights.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
print(json.dumps({k: v["length_m"] for k, v in out.items()}))
