"""ASN Aquila interior kit (ARTE-INTERNI): third-party models (Poly Haven, CC0) built into the room meshes.

tools/art/polyhaven_models.py downloads a model's glTF (art/_downloads/polyhaven/<id>/) and packs its textures as T_PH_<Name>_{BC,N,ORM} (art/_cache/textures);
this module imports the glTF in Blender, picks the objects wanted (a variant of a plant, the plant without its pot), remaps the glTF materials to MI_SHIP_PH_* slots
(data/ship/room_materials.json: `uv_mode: mesh`, the model's own UVs), optionally decimates, and returns plain arrays (cached per process and on disk in art/_cache/ship/assets).
`add(fb, asset, pos, yaw, scale)` then pours the geometry into one of the groups of an SParts at a local position: the builder's box projection leaves the UVs alone
(the faces carry the custom-UV flag). Leaves are single surfaces in the source: their materials are two-sided in the engine (`two_sided` in room_materials.json), so no geometry is doubled; `back=True` adds a back skin 0.8 mm behind
(for a use where the material is not two-sided).

Models are registered in ASSETS below: name -> (poly haven id, which objects, material map, decimation, pot). Every model used is listed in docs/licenze.csv.
"""
from __future__ import annotations

import json
import math
import os
import pickle
import re
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402

ROOT = L.ROOT
PH_DIR = os.path.join(ROOT, "art", "_downloads", "polyhaven")
MAIN_PH_DIR = os.path.join("/Users/beltromatti/Desktop/ASTRA", "art", "_downloads", "polyhaven")
CACHE_DIR = os.path.join(ROOT, "art", "_cache", "ship", "assets")

# name -> dict(id, pick (object-name prefixes or None = all), mats {gltf material -> slot}, decimate, two_sided {gltf materials that are single leaf surfaces})
ASSETS: dict[str, dict] = {}
_MEMO: dict[str, dict] = {}


def register(name: str, asset_id: str, mats: dict, pick=None, decimate: float = 1.0, two_sided=(), drop=()) -> None:
    ASSETS[name] = dict(id=asset_id, pick=pick, mats=mats, decimate=decimate, two_sided=set(two_sided), drop=set(drop))


def _gltf_path(asset_id: str) -> str:
    for d in (PH_DIR, MAIN_PH_DIR):
        p = os.path.join(d, asset_id, f"{asset_id}_1k.gltf")
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{asset_id}: run  uv run --python /opt/homebrew/bin/python3.13 python tools/art/polyhaven_models.py {asset_id}")


def probe(asset_id: str) -> list[dict]:
    """Objects of a model: name, materials, triangles, bounds (metres, Z up, as imported). For choosing `pick` and `drop`."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=_gltf_path(asset_id))
    new = [o for o in bpy.data.objects if o not in before]
    out = []
    for o in new:
        if o.type != "MESH":
            continue
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        lo = [min(p[i] for p in pts) for i in range(3)]
        hi = [max(p[i] for p in pts) for i in range(3)]
        out.append({"name": o.name, "mats": [m.name for m in o.data.materials], "tris": sum(len(p.vertices) - 2 for p in o.data.polygons),
                    "lo": [round(v, 3) for v in lo], "hi": [round(v, 3) for v in hi]})
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    return out


def _extract(name: str) -> dict:
    cfg = ASSETS[name]
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=_gltf_path(cfg["id"]))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    sel = [o for o in meshes if (cfg["pick"] is None or any(o.name.startswith(p) for p in cfg["pick"]))]
    sel = [o for o in sel if not any(re.sub(r"\.\d{3}$", "", m.name) in cfg["drop"] for m in o.data.materials)] if cfg["drop"] else sel
    # world-space copy of each selected object (the glTF root transform turns Y-up into Z-up)
    verts, tris, uvs, mats, flags = [], [], [], [], []
    mat_index: dict[str, int] = {}
    for o in sel:
        if cfg["decimate"] < 0.999:
            mod = o.modifiers.new("dec", "DECIMATE")
            mod.ratio = cfg["decimate"]
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()
        me = o.evaluated_get(dg).to_mesh()
        me.transform(o.matrix_world)
        me.calc_loop_triangles()
        uv = me.uv_layers.active.data if me.uv_layers.active else None
        base = len(verts)
        verts += [tuple(v.co) for v in me.vertices]
        for tri in me.loop_triangles:
            mname = re.sub(r"\.\d{3}$", "", o.data.materials[me.polygons[tri.polygon_index].material_index].name) if o.data.materials else ""
            slot = cfg["mats"].get(mname)
            if slot is None:
                continue
            if slot not in mat_index:
                mat_index[slot] = len(mat_index)
            tris.append(((base + tri.vertices[0], base + tri.vertices[1], base + tri.vertices[2]), mat_index[slot], mname in cfg["two_sided"]))
            uvs.append(tuple(tuple(uv[li].uv) for li in tri.loops) if uv else ((0, 0), (0, 0), (0, 0)))
        o.evaluated_get(dg).to_mesh_clear()
    # ground the model: x, y centred on the bounds' middle, z = 0 at the lowest vertex
    used = {i for t in tris for i in t[0]}
    xs = [verts[i][0] for i in used]
    ys = [verts[i][1] for i in used]
    zs = [verts[i][2] for i in used]
    cx, cy, z0 = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for mt in list(bpy.data.materials):
        if mt.users == 0:
            bpy.data.materials.remove(mt)
    return {"verts": [(x - cx, y - cy, z - z0) for x, y, z in verts], "tris": tris, "uvs": uvs, "slots": [s for s, _i in sorted(mat_index.items(), key=lambda kv: kv[1])],
            "size": (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))}


def get(name: str) -> dict:
    """The model's arrays (cached)."""
    if name in _MEMO:
        return _MEMO[name]
    cfg = ASSETS[name]
    os.makedirs(CACHE_DIR, exist_ok=True)
    key = f"{name}_{cfg['id']}_{cfg['decimate']}_{sorted(cfg['mats'].items())}_{cfg['pick']}_{sorted(cfg['drop'])}".replace(" ", "")
    path = os.path.join(CACHE_DIR, f"{name}.pkl")
    data = None
    if os.path.exists(path):
        try:
            with open(path, "rb") as fh:
                stored = pickle.load(fh)
            if stored.get("key") == key:
                data = stored["data"]
        except Exception:
            data = None
    if data is None:
        data = _extract(name)
        with open(path, "wb") as fh:
            pickle.dump({"key": key, "data": data}, fh)
    _MEMO[name] = data
    return data


def add(fb, name: str, pos=(0.0, 0.0, 0.0), yaw: float = 0.0, scale: float = 1.0, tilt: tuple = (0.0, 0.0), thick: float = 0.0008, back: bool = False):
    """Pour model `name` into the builder group `fb` (an FB / SFB: b.soft, b.fine, ...) at local `pos` turned by `yaw` degrees, scaled, tipped by tilt = (pitch, roll) degrees.
    Returns the number of triangles added."""
    data = get(name)
    verts = data["verts"]
    m = Matrix.Translation(pos) @ Matrix.Rotation(math.radians(yaw), 4, "Z") @ Matrix.Rotation(math.radians(tilt[0]), 4, "Y") @ Matrix.Rotation(math.radians(tilt[1]), 4, "X") \
        @ Matrix.Diagonal((scale, scale, scale, 1.0))
    top: dict[int, object] = {}
    bot: dict[int, object] = {}
    normals: dict[int, Vector] = {}
    # per-vertex normals for the back skin (area-weighted from the triangles that use the vertex)
    for (tri, _mi, ts) in data["tris"]:
        if not (ts and back):
            continue
        a, b, c = (Vector(verts[i]) for i in tri)
        n = (b - a).cross(c - a)
        for i in tri:
            normals[i] = normals.get(i, Vector()) + n
    slot_ids = [fb.mi(s) for s in data["slots"]]
    mirrored = fb.frame.determinant() < 0
    uv_layer = fb.uv
    count = 0
    for (tri, mi, ts), uv in zip(data["tris"], data["uvs"]):
        for side in ((0, 1) if (ts and back) else (0,)):
            vs = []
            for i in tri:
                cache = top if side == 0 else bot
                if i not in cache:
                    p = Vector(verts[i])
                    if side == 1:
                        nn = normals.get(i, Vector((0, 0, 1)))
                        nn = nn.normalized() if nn.length > 1e-9 else Vector((0, 0, 1))
                        p = p - nn * (thick / max(scale, 1e-6))
                    cache[i] = fb.bm.verts.new(fb.P(m @ p))
                vs.append(cache[i])
            order = [0, 1, 2]
            front_out = (side == 0)
            # the source's winding is counter-clockwise seen from the front; the frame may mirror
            if front_out == mirrored:
                order = [0, 2, 1]
            try:
                f = fb.bm.faces.new([vs[k] for k in order])
            except ValueError:
                continue
            f.material_index = slot_ids[mi]
            f[fb.cu] = 1
            for loop, k in zip(f.loops, order):
                loop[uv_layer].uv = uv[k]
            count += 1
    return count
