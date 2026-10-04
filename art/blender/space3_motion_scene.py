"""SPAZIO-VIVO — what the capital ships' motion looks like (docs/SPAZIO.md): the jets that fire for a turn, a brake, a slide, and the wake of a ship that turns, on the real hulls.

The jets are those the game fires: the allocation is the game's (a nozzle fires when the push it gives and the torque it gives are along what is asked, past a dead band: AstraSpaceLifeMotion.cpp,
worked again here in numpy from data/space/thrusters.json), and each is drawn at the size the game draws it (a few per cent of the hull's length, the cone narrowing to its tip, a glow at the
nozzle). The wake is the ribbon of beads the game lays (notes every 0.75 s of a ship under way, joined into pieces, wider and dimmer as they age) along the arc of a ship holding a full-rate turn.
The look of the beads and the jets is the preview's approximation of the game's materials (soft rims, additive): the game's own are tuned in the engine.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/space3_motion_scene.py -- --class aquila --out <dir> [--scenes yaw,trim,stop,brake,slide,pitch] [--wake] [--samples 24] [--size 1500x850]
Writes <dir>/jets_<class>_<scene>_<stern|bow>.jpg (two views of each scene) and <dir>/wake_<class>.jpg; tools/art/motion_sheet.py puts them on a sheet with their captions.
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ship3_build as B  # noqa: E402
import ship3_preview as PV  # noqa: E402
import shipgen3 as SG  # noqa: E402

CLASS_MESH = {"aquila": "SM_SHIP_ASTRA_Aquila", "praetorian": "SM_SHIP_ASTRA_Praetorian", "vigilant": "SM_SHIP_ASTRA_Vigilant", "acheron": "SM_SHIP_MANDATE_Acheron", "styx": "SM_SHIP_MANDATE_Styx",
              "lethe": "SM_SHIP_MANDATE_Lethe", "freighter": "SM_SHIP_GUILD_Freighter"}
TRIM_K, DEAD = 0.42, 0.15
SCENES = {                                   # name -> (caption, turn (x roll, y pitch, z yaw), push)
    "yaw": ("a turn to starboard begins: the jets that start it, at full", (0, 0, 1.0), (0, 0, 0)),
    "trim": ("the turn is held: a faint trim, blinking", (0, 0, TRIM_K), (0, 0, 0)),
    "stop": ("the turn ends: the other jets stop it", (0, 0, -1.0), (0, 0, 0)),
    "brake": ("braking at full acceleration: the jets that face forward", (0, 0, 0), (-1.0, 0, 0)),
    "slide": ("sliding to starboard across her heading", (0, 0, 0), (0, 1.0, 0)),
    "pitch": ("the nose goes down", (0, 1.0, 0), (0, 0, 0)),
}
CAPTION_ORDER = ["yaw", "trim", "stop", "brake", "slide", "pitch"]


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"cls": "aquila", "out": os.path.join(ROOT, "Saved", "Space", "motion"), "scenes": CAPTION_ORDER, "wake": False, "samples": 24, "size": (1500, 850)}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--class":
            a["cls"] = argv[i + 1]
            i += 1
        elif k == "--out":
            a["out"] = argv[i + 1]
            i += 1
        elif k == "--scenes":
            a["scenes"] = [x for x in argv[i + 1].split(",") if x and x != "none"]
            i += 1
        elif k == "--wake":
            a["wake"] = True
        elif k == "--samples":
            a["samples"] = int(argv[i + 1])
            i += 1
        elif k == "--size":
            a["size"] = tuple(int(x) for x in argv[i + 1].split("x"))
            i += 1
        i += 1
    return a


def allocate(rec: dict, turn, push) -> list[float]:
    """AstraSpace::Allocate worked again: each jet's share of what is asked, past the dead band."""
    com = np.array(rec["com"])
    L = rec["len"]
    jets = rec["nozzles"]
    P = np.array([j["p"] for j in jets], float)
    D = np.array([j["d"] for j in jets], float)
    D /= np.linalg.norm(D, axis=1)[:, None]
    Push = -D
    T = np.cross(P - com, Push)
    tmax = np.maximum(np.abs(T).max(axis=0), 0.02 * L)
    S = T / tmax
    pu = np.array([min(push[0], 0.0), push[1], push[2]])
    u = S @ np.array(turn, float) + Push @ pu
    return [0.0 if x <= DEAD else min(1.0, (x - DEAD) / (1.0 - DEAD)) for x in u]


def emission_material(name: str, col, strength: float, rim: float = 0.0):
    """An emissive material; rim > 0 makes it a soft volume (more transparent toward its silhouette, as the game's sprites are)."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    try:
        mat.surface_render_method = "BLENDED"
    except Exception:
        pass
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (col[0], col[1], col[2], 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if rim > 0.0:
        lw = nt.nodes.new("ShaderNodeLayerWeight")
        lw.inputs["Blend"].default_value = 0.5
        pw = nt.nodes.new("ShaderNodeMath")
        pw.operation = "POWER"
        pw.inputs[1].default_value = rim
        nt.links.new(lw.outputs["Facing"], pw.inputs[0])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(pw.outputs["Value"], mix.inputs["Fac"])
        nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
        nt.links.new(em.outputs["Emission"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    else:
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def cone_object(name: str, base: np.ndarray, d: np.ndarray, length: float, width: float, mat):
    """The jet: a cone from the nozzle narrowing to its tip (Blender frame: y mirrored)."""
    bpy.ops.mesh.primitive_cone_add(vertices=14, radius1=width / 2, radius2=width / 2 * 0.16, depth=length)
    o = bpy.context.active_object
    o.name = name
    dv = Vector((d[0], -d[1], d[2])).normalized()
    o.rotation_euler = dv.to_track_quat("Z", "Y").to_euler()
    o.location = Vector((base[0], -base[1], base[2])) + dv * (length / 2)
    o.data.materials.append(mat)
    return o


def glow_object(name: str, at: np.ndarray, radius: float, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=radius, location=(at[0], -at[1], at[2]))
    o = bpy.context.active_object
    o.name = name
    o.data.materials.append(mat)
    return o


def build_hull(cls: str):
    reg = SG.registry()
    name = CLASS_MESH[cls]
    spec = reg[name]
    PV.make_materials(spec["fac"])
    res = SG.build_ship(name, spec, {"seed": 0, "detail": 0.3, "export": False, "pieces": False})
    g = res["g"]
    asm = g.assemble()
    asm, mats = SG.compact(asm, g.mats)
    obj = B.build_object(name, asm, mats)
    V = np.array([v.co[:] for v in obj.data.vertices])
    return obj, V, spec


def clear_extras(keep) -> None:
    for o in list(bpy.data.objects):
        if o not in keep and o.type in {"MESH"}:
            bpy.data.objects.remove(o, do_unlink=True)


def render_jets(a: dict, rec: dict, hull, V: np.ndarray, spec: dict) -> None:
    L = rec["len"]
    w, h = a["size"]
    PV.configure(w, h, a["samples"], exposure=0.0)
    amber = spec["fac"] != "A"
    core = (1.0, 0.62, 0.3) if amber else (0.78, 0.9, 1.0)
    x0, x1 = float(V[:, 0].min()), float(V[:, 0].max())
    views = {"stern": (V[V[:, 0] < x0 + 0.30 * L], np.array((-0.8, 0.62, 0.42))), "bow": (V[V[:, 0] > x1 - 0.34 * L], np.array((0.8, 0.62, 0.42)))}
    jets = rec["nozzles"]
    for scene in a["scenes"]:
        cap, turn, push = SCENES[scene]
        u = allocate(rec, turn, push)
        made = []
        lit = 0
        for j, level in zip(jets, u):
            if level < 0.05:
                continue
            lit += 1
            width = max(0.0062 * L, j["r"] * 2.0)
            jl = 0.032 * L * (0.45 + 0.55 * level)
            made.append(cone_object(f"jet_{lit}", np.array(j["p"]), np.array(j["d"]), jl, width, emission_material(f"jetm_{lit}", core, 4.5 * level, rim=0.0)))
            made.append(glow_object(f"glow_{lit}", np.array(j["p"]) + np.array(j["d"]) * jl * 0.12, 0.0105 * L * (0.55 + 0.45 * level) * 0.8, emission_material(f"glowm_{lit}", core, 12.0 * level, rim=1.4)))
        print(f"  {a['cls']} {scene}: {lit} of {len(jets)} jets burn")
        for tag, (pts, d) in views.items():
            cam, tgt = PV.fit_camera("cam", pts, d, lens=40.0, aspect=w / h, margin=0.08, clip_end=400000.0)
            PV.rig(cam.location, tgt, key_az=62.0, key_el=26.0, key=5.0, fill=0.9, rim=0.8)
            PV.render(cam, os.path.join(a["out"], f"jets_{a['cls']}_{scene}_{tag}.jpg"))
            bpy.data.objects.remove(cam, do_unlink=True)
        for o in made:
            bpy.data.objects.remove(o, do_unlink=True)


def render_wake(a: dict, rec: dict, hull, V: np.ndarray, spec: dict) -> None:
    """A ship holding a full-rate turn for a wake's life: the notes every 0.75 s along the arc, the pieces joined, the beads wider and dimmer as they age."""
    L = rec["len"]
    w, h = a["size"]
    PV.configure(w, h, a["samples"], exposure=0.0)
    speed, rate = 288.0, math.radians(3.0)
    life = float(np.clip(9.0 + 0.016 * L, 10.0, 24.0))
    step = 0.75
    n = int(life / step)
    # the ship's path in the Unreal frame (x forward, y starboard): now (t = 0) she is at the origin heading along +x, and she has been turning to starboard (towards +y) at `rate`: the heading
    # was -rate*t at t seconds ago, her place on the circle of radius speed/rate about (0, R); the note of that moment is where her drive burned then (her heading turns the drive's offset)
    R = speed / rate
    heads = []
    drive = np.array(rec["drive"]["p"])
    for k in range(n + 1):
        th = -rate * k * step
        pos = np.array([R * math.sin(th), R * (1.0 - math.cos(th)), 0.0])
        c, s_ = math.cos(th), math.sin(th)
        heads.append(pos + np.array([drive[0] * c - drive[1] * s_, drive[0] * s_ + drive[1] * c, drive[2]]))
    ship = hull
    ship.location = Vector((0, 0, 0))
    col = (0.45, 0.72, 1.0) if spec["fac"] == "A" else (1.0, 0.52, 0.26)
    width0 = float(np.clip(0.40 * rec["drive"]["w"], 3.0, 36.0))
    made = []
    for k in range(n):
        a_head, a_tail = k / n, (k + 1) / n
        A, Bp = heads[k], heads[k + 1]
        seg = A - Bp
        Ls = float(np.linalg.norm(seg))
        if Ls < 1.0:
            continue
        mid = (A + Bp) / 2
        wd = width0 * (1.0 + 1.9 * a_tail)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=14, radius=1.0)
        o = bpy.context.active_object
        o.name = f"bead{k}"
        dv = Vector((seg[0], -seg[1], seg[2])).normalized()
        o.rotation_euler = dv.to_track_quat("Z", "Y").to_euler()
        o.scale = (wd / 2, wd / 2, Ls * 1.7 / 2)
        o.location = Vector((mid[0], -mid[1], mid[2]))
        fade = (1.0 - 0.5 * (a_head + a_tail)) ** 1.3
        o.data.materials.append(emission_material(f"beadm{k}", col, 5.0 * fade, rim=1.2))
        made.append(o)
    hp = np.array([[p[0], -p[1], p[2]] for p in heads])
    # the whole wake from above and behind, and the first seconds of it close, from the side
    cam, tgt = PV.fit_camera("cam", np.vstack([V, hp]), np.array((0.15, -0.45, 0.88)), lens=30.0, aspect=w / h, margin=0.1, clip_end=800000.0)
    PV.rig(cam.location, tgt, key_az=62.0, key_el=26.0, key=5.0, fill=0.9, rim=0.8)
    PV.render(cam, os.path.join(a["out"], f"wake_{a['cls']}.jpg"))
    bpy.data.objects.remove(cam, do_unlink=True)
    print(f"  wake of {a['cls']}: {n} pieces over {life:.0f} s, {speed * life / 1000:.1f} km of path, beads {width0:.0f} m wide at the ship")
    for o in made:
        bpy.data.objects.remove(o, do_unlink=True)


def main() -> None:
    a = parse_args()
    os.makedirs(a["out"], exist_ok=True)
    data = json.load(open(os.path.join(ROOT, "data", "space", "thrusters.json"), encoding="utf-8"))["classes"]
    rec = data[a["cls"]]
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    hull, V, spec = build_hull(a["cls"])
    if a["scenes"]:
        render_jets(a, rec, hull, V, spec)
    if a["wake"]:
        render_wake(a, rec, hull, V, spec)
    print("MOTIONSCENE_OK")


if __name__ == "__main__":
    main()
