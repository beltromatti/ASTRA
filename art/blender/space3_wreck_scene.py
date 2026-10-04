"""SPAZIO-VIVO — a wreck site as the game's records place it, rendered (docs/SPAZIO.md).

The bench writes the site (the console's astra.space.wrecks.dump: the pieces of the broken hull, the chunks of her field of debris, her lifepods, all relative to her middle, in the Unreal frame,
metres, a given number of seconds after she went). This builds the meshes the game imports (the ship generator's three sections of that ship, the debris, the pods) and puts them where the
records say, dark (the windows out, the running lights out, the torn ends cooling), and renders what the Captain would see.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/space3_wreck_scene.py -- <scene.json> <out_dir> [--views close,wide,pieces] [--tag name] [--samples 32] [--size 1600x900]
                                                                                            [--debris-scale 1.0] [--cam az,el]
Views: close   the pieces and the debris round them, from a few hundred metres;
       wide    the whole field and the beacons, from a few kilometres (the debris is a speck at that range: --debris-scale makes it show, and the picture says so);
       pieces  each section on its own, three-quarter view.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

import ship3_build as B  # noqa: E402
import ship3_preview as PV  # noqa: E402
import shipgen3 as SG  # noqa: E402
import spacegen3 as SP  # noqa: E402

MIRROR = Matrix.Diagonal((1.0, -1.0, 1.0)).to_4x4()                      # the Unreal frame is the Blender one with y mirrored (the FBX export does it too)
FAC = {0: "A", 1: "M", 2: "G"}
CHUNK = {0: "Plate", 1: "Girder", 2: "Chunk"}


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"scene": None, "out": None, "views": ["close", "wide"], "tag": "", "samples": 32, "size": (1600, 900), "debris_scale": 1.0, "cam": None}
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--views":
            out["views"] = argv[i + 1].split(",")
            i += 1
        elif a == "--tag":
            out["tag"] = argv[i + 1]
            i += 1
        elif a == "--samples":
            out["samples"] = int(argv[i + 1])
            i += 1
        elif a == "--size":
            out["size"] = tuple(int(x) for x in argv[i + 1].split("x"))
            i += 1
        elif a == "--debris-scale":
            out["debris_scale"] = float(argv[i + 1])
            i += 1
        elif a == "--cam":
            out["cam"] = [float(x) for x in argv[i + 1].split(",")]
            i += 1
        elif not a.startswith("--"):
            pos.append(a)
        i += 1
    out["scene"], out["out"] = pos[0], pos[1]
    return out


def bl_matrix(pos, quat_xyzw, scale: float = 1.0) -> Matrix:
    """An Unreal-frame pose (position in metres, quaternion x y z w) as a Blender-frame matrix."""
    q = Quaternion((quat_xyzw[3], quat_xyzw[0], quat_xyzw[1], quat_xyzw[2]))
    r = MIRROR @ q.to_matrix().to_4x4() @ MIRROR
    s = Matrix.Diagonal((scale, scale, scale, 1.0))
    return Matrix.Translation(Vector((pos[0], -pos[1], pos[2]))) @ r @ s


def build_sections(hull_mesh: str) -> dict:
    """The ship generator's own pieces of that ship (the meshes the game imports as <hull>_SecBow/Mid/Stern)."""
    reg = SG.registry()
    spec = reg[hull_mesh]
    res = SG.build_ship(hull_mesh, spec, {"seed": 0, "detail": 1.0})
    g, info = res["g"], res["info"]
    cuts = list(info.get("cuts") or [])
    section_of = lambda x, cu=cuts: np.where(x > cu[0], 0, np.where(x > cu[1], 1, 2)) if len(cu) == 2 else np.where(x > cu[0], 0, 1)  # noqa: E731
    out = {}
    for k in range(len(cuts) + 1):
        pname = f"{hull_mesh}_Sec{SG.SEC_NAMES[k] if len(cuts) == 2 else ('Bow', 'Stern')[k]}"
        pa = g.assemble(sections={k}, include_caps=True, section_of=section_of)
        if pa is None:
            continue
        pa, pm = SG.compact(pa, g.mats)
        obj = B.build_object(pname, pa, pm)
        obj.hide_render = True
        out[SG.SEC_NAMES[k] if len(cuts) == 2 else ("Bow", "Stern")[k]] = obj
    return out


def build_prop(name: str):
    reg = SP.registry()
    spec = reg[name]
    res = SP.build_mesh(name, spec, {"seed": 0, "detail": 1.0})
    asm = res["g"].assemble()
    asm, mats = SG.compact(asm, res["g"].mats)
    obj = B.build_object(name, asm, mats)
    obj.hide_render = True
    return obj, res["info"]


def dead_materials(fac: str, hot: float) -> None:
    """The hull's preview materials as a wreck has them: the windows and the running lights out, the cut faces as hot as they still are."""
    PV.make_materials(fac)
    PV.light_material(f"MI_HULL_{fac}_Lights", fac, lit_fraction=0.0)
    PV.glow_material(f"MI_HULL_{fac}_Glow", fac, 0.0)
    PV.nav_material(f"MI_HULL_{fac}_Nav", 0.0)
    PV.cut_material(f"MI_HULL_{fac}_Cut", heat=hot)


def mesh_points(mesh, mat: Matrix, step: int) -> np.ndarray:
    """Every `step`th vertex of a mesh through a matrix (N x 3), without a Python loop over hundreds of thousands of vertices."""
    n = len(mesh.vertices)
    co = np.empty(n * 3, np.float64)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)[::step]
    m = np.array(mat)
    return co @ m[:3, :3].T + m[:3, 3]


def link_copy(src, name: str, mat: Matrix):
    o = bpy.data.objects.new(name, src.data)
    o.matrix_world = mat
    bpy.context.scene.collection.objects.link(o)
    return o


def beacon_sphere(name: str, at: Vector, radius: float, strength: float):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=radius, subdivisions=2, location=at)
    o = bpy.context.active_object
    o.name = name
    mat = bpy.data.materials.new(name + "_mat")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    o.data.materials.append(mat)
    return o


def main() -> None:
    a = parse_args()
    scene = json.load(open(a["scene"], encoding="utf-8"))
    site = scene["site"]
    hull = site["hull_mesh"]
    fac = FAC.get(site["faction"], "G")
    age = float(site["age_s"])
    os.makedirs(a["out"], exist_ok=True)
    SP.A.reset_scene() if hasattr(SP, "A") else None
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    # the meshes
    SP.preview_materials(fac)                                              # (it rebuilds the faction's materials: the dead look goes on top)
    dead_materials(fac, hot=max(0.0, 1.0 - age / 60.0) ** 1.3 * 0.9)
    sections = build_sections(hull)
    props = {}
    for shape in range(3):
        props[shape], _ = build_prop(f"SM_DEBRIS_{fac}_{CHUNK[shape]}")
    pod, pod_info = build_prop(f"SM_POD_{fac}")
    # the records, as placed
    placed, pts = [], []
    names = ["Bow", "Mid", "Stern"]
    for p in scene["pieces"]:
        key = names[p["section"]] if p["section"] < 3 else None
        src = sections.get(key)
        if src is None:
            continue
        m = bl_matrix(p["origin"], p["quat"])
        o = link_copy(src, f"{hull}_{key}", m)
        placed.append(o)
        pts.append(mesh_points(src.data, m, 7))
    centre = np.mean([np.array(m_.matrix_world.translation) for m_ in placed], axis=0) if placed else np.zeros(3)
    ds = a["debris_scale"]
    for i, c in enumerate(scene["chunks"]):
        src = props[c["shape"]]
        link_copy(src, f"chunk{i}", bl_matrix(c["pos"], c["quat"], c["size"] * ds))
    nbeacon = 0
    for i, p in enumerate(scene["pods"]):
        if p["state"] == 1:
            continue
        m = bl_matrix(p["pos"], p["quat"], max(1.0, ds * 0.6))
        link_copy(pod, f"pod{i}", m)
        if p["beacon"]:
            at = m @ Vector((0.2, 0.0, 3.0))
            beacon_sphere(f"beacon{i}", at, 1.1 * max(1.0, ds ** 0.5), 120.0)
            nbeacon += 1
    pts = np.concatenate(pts, axis=0) if pts else np.zeros((1, 3))
    R = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))) / 2
    w, h = a["size"]
    PV.configure(w, h, a["samples"], exposure=0.0)
    tag = a["tag"]
    print(f"[wreck scene] {site['name']} {age:.0f} s after she went: {len(placed)} pieces, {len(scene['chunks'])} chunks, {len(scene['pods'])} lifepods ({nbeacon} calling); spread of the pieces {2 * R:.0f} m")
    for view in a["views"]:
        if view == "close":
            az, el = (a["cam"] or [-35.0, 18.0])[:2]
            d = Vector((math.cos(math.radians(el)) * math.cos(math.radians(az)), math.cos(math.radians(el)) * math.sin(math.radians(az)), math.sin(math.radians(el))))
            cam, tgt = PV.fit_camera("cam", pts, np.array(d), lens=42.0, aspect=w / h, margin=0.12, clip_end=200000.0)
            PV.rig(cam.location, tgt, key_az=62.0, key_el=26.0, key=5.0, fill=0.9, rim=0.8)
            PV.render(cam, os.path.join(a["out"], f"wreck_close{tag}.jpg"))
            bpy.data.objects.remove(cam, do_unlink=True)
        elif view == "wide":
            fr = float(scene["field_radius"])
            span = max(fr * 1.05, R * 2.0)
            az, el = (a["cam"] or [-48.0, 22.0])[:2]
            d = Vector((math.cos(math.radians(el)) * math.cos(math.radians(az)), math.cos(math.radians(el)) * math.sin(math.radians(az)), math.sin(math.radians(el))))
            tgt = Vector((0.0, 0.0, 0.0))
            dist = span * 1.9
            loc = tgt + d * dist
            cam = PV.camera("cam", tuple(loc), tuple(tgt), lens=PV.close_up_lens(dist, span * 2.0), clip_end=max(200000.0, dist * 6))
            PV.rig(cam.location, tgt, key_az=62.0, key_el=26.0, key=5.0, fill=0.9, rim=0.8)
            PV.render(cam, os.path.join(a["out"], f"wreck_wide{tag}.jpg"))
            bpy.data.objects.remove(cam, do_unlink=True)
        elif view == "pieces":
            for k, src in sections.items():
                src.hide_render = False
                for o in placed:
                    o.hide_render = True
                for o in bpy.data.objects:
                    if o.name.startswith(("chunk", "pod", "beacon")):
                        o.hide_render = True
                v = mesh_points(src.data, Matrix.Identity(4), 5)
                cam, tgt = PV.fit_camera("cam", v, np.array((-0.7, 0.55, 0.45)), lens=50.0, aspect=w / h, margin=0.08, clip_end=200000.0)
                PV.rig(cam.location, tgt, key_az=60.0, key_el=28.0, key=5.0, fill=0.9)
                PV.render(cam, os.path.join(a["out"], f"wreck_{k.lower()}{tag}.jpg"))
                bpy.data.objects.remove(cam, do_unlink=True)
                src.hide_render = True
                for o in placed:
                    o.hide_render = False
                for o in bpy.data.objects:
                    if o.name.startswith(("chunk", "pod", "beacon")):
                        o.hide_render = False
    print("WRECKSCENE_OK")


if __name__ == "__main__":
    main()
