"""SPAZIO-VIVO — where the capital ships' manoeuvring jets are (docs/SPAZIO.md): data/space/thrusters.json, and previews of the sites on the real hulls.

The game draws a short burst of light at a nozzle when a capital ship turns, brakes or slides sideways (AstraSpaceLifeMotion.*). This says where the nozzles are, per class, in the ship's own
frame the game uses (x forward, y starboard, z up, metres from the mesh's origin):

  * the ship generators' own thruster quads where a ship has them (the ASTRA ships' stern corners: the nozzles are the ones the generators build, recorded as they are placed, so a jet comes out of
    a bell you can see on the hull);
  * a standard pack of jets for the rest, found on the hull itself: rays are cast at the generated mesh from outside and the nozzle sits on the first surface they meet, on a patch that is flat
    (a slab's edge or a gun's barrel would put the jet in the air): yaw jets on the flanks (bow and stern), pitch and roll jets on the deck and the keel (bow and stern, off the centreline so they
    roll as well), and braking jets on the bow's shoulders, canted outward so the burst clears the hull.

Also the drive's centre and width (where an engine wake starts and how wide it is), the hull's length and the middle it turns about. The same thruster allocation the game uses (a nozzle fires when
the push it gives, and the torque, is along what the ship's motion asks for) is checked here: every direction a ship can ask for must have jets that give it.

Usage (headless Blender; the generators need bpy, the rest is numpy):
  blender -b --factory-startup --python-exit-code 1 -P art/blender/space3_thrusters.py -- [--out data/space/thrusters.json] [--only aquila,styx] [--detail 0.02]
                                                                                           [--preview docs/progressi/spazio] [--size 1500x850] [--samples 24] [--no-jets]
Then  tools/space.py sync  stages the file for the game.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import ship3_build as B  # noqa: E402
import ship3_kit2 as K2  # noqa: E402
import ship3_preview as PV  # noqa: E402
import shipgen3 as SG  # noqa: E402

CLASS_OF = {
    "SM_SHIP_ASTRA_Aquila": "aquila", "SM_SHIP_ASTRA_Praetorian": "praetorian", "SM_SHIP_ASTRA_Vigilant": "vigilant",
    "SM_SHIP_MANDATE_Acheron": "acheron", "SM_SHIP_MANDATE_Styx": "styx", "SM_SHIP_MANDATE_Lethe": "lethe", "SM_SHIP_GUILD_Freighter": "freighter",
    # the craft (round two): the fighters, the bomber, the drones and the Mandate's strike fighter turn and brake on jets too
    "SM_CRAFT_ASTRA_Falcon": "falcon", "SM_CRAFT_ASTRA_Hammer": "hammer", "SM_CRAFT_ASTRA_Wasp": "wasp", "SM_CRAFT_MANDATE_Harpy": "harpy",
}
SMALL_M = 40.0                                                  # a hull shorter than this is a craft: its nozzles, its flat patches and its stand-off from the skin are a few centimetres, not metres
KIND_COL = {"quad": (1.0, 1.0, 1.0), "yaw": (0.2, 0.9, 1.0), "pitch": (0.3, 1.0, 0.35), "brake": (1.0, 0.55, 0.12)}
BELL_LIP = 2.14
EPS = 1e-9
PLATING = {"Plate", "Frame", "Livery", "Trim", "Blue", "Green"}           # the slots that are the ship's own skin (not radiators, windows, lights, glow, engine parts, marks)


# ------------------------------------------------------------------------------------------------------------------------ rays at a mesh
class Hull:
    """A triangle mesh in the Unreal frame (x forward, y starboard, z up) that rays are cast at along an axis (the sites are found from outside, along +-y and +-z)."""

    def __init__(self, V: np.ndarray, F: np.ndarray, plating: np.ndarray | None = None):
        """plating: per triangle, True where the surface is the ship's plating (not a radiator, a window, a light, an engine part): a jet is only put on plating."""
        T = np.asarray(V, np.float64)[np.asarray(F, np.int64)]
        self.plating = np.ones(len(T), bool) if plating is None else np.asarray(plating, bool)
        self.A = T[:, 0]
        self.E1 = T[:, 1] - T[:, 0]
        self.E2 = T[:, 2] - T[:, 0]
        self.lo = T.min(axis=1)
        self.hi = T.max(axis=1)
        n = np.cross(self.E1, self.E2)
        self.N = n / (np.linalg.norm(n, axis=1)[:, None] + 1e-12)
        self.min = T.reshape(-1, 3).min(axis=0)
        self.max = T.reshape(-1, 3).max(axis=0)

    def cast(self, o: np.ndarray, d: np.ndarray):
        """The first surface along d (an axis direction) from o: (distance, point, normal facing the ray's origin, whether it is plating), or None."""
        ax = int(np.argmax(np.abs(d)))
        a, b = [i for i in range(3) if i != ax]
        m = (self.lo[:, a] <= o[a]) & (self.hi[:, a] >= o[a]) & (self.lo[:, b] <= o[b]) & (self.hi[:, b] >= o[b])
        idx = np.nonzero(m)[0]
        if idx.size == 0:
            return None
        A, E1, E2 = self.A[idx], self.E1[idx], self.E2[idx]
        pv = np.cross(d, E2)
        det = np.einsum("ij,ij->i", E1, pv)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        tv = o - A
        u = np.einsum("ij,ij->i", tv, pv) * inv
        qv = np.cross(tv, E1)
        v = (qv @ d) * inv
        t = np.einsum("ij,ij->i", E2, qv) * inv
        hit = ok & (u >= -EPS) & (v >= -EPS) & (u + v <= 1.0 + EPS) & (t > 1e-6)
        if not hit.any():
            return None
        j = int(np.argmin(np.where(hit, t, np.inf)))
        n = self.N[idx[j]].copy()
        if float(n @ d) > 0.0:
            n = -n
        return float(t[j]), o + d * float(t[j]), n, bool(self.plating[idx[j]])


def find_site(hull: Hull, axis: int, sgn: int, x_nom: float, lat_nom: float, lat_span: float, length: float, bounds_far: float, x_span: float = 0.03) -> dict | None:
    """The nozzle's place on the hull near (x_nom, lat_nom): a ray along -sgn on `axis` (1 a flank, 2 the deck or the keel) from outside, on the flattest patch near the nominal point
    (within x_span of the length along the ship and lat_span across). The lateral coordinate is the other of y and z."""
    lt = 2 if axis == 1 else 1
    flat = float(np.clip(0.012 * length, 2.5 if length >= SMALL_M else 0.25, 10.0))
    best = None
    for dx in (np.linspace(-x_span, x_span, 5) if x_span > 0 else np.zeros(1)) * length:
        for dl in (np.linspace(-1.0, 1.0, 9) * lat_span if lat_span > 0 else np.zeros(1)):
            x, lat = x_nom + dx, lat_nom + dl
            o = np.zeros(3)
            o[0], o[lt], o[axis] = x, lat, sgn * bounds_far
            d = np.zeros(3)
            d[axis] = -sgn
            r = hull.cast(o, d)
            if r is None:
                continue
            t0, p, n, plating = r
            ts = [t0]
            miss = 0
            for ox, ol in ((flat, 0.0), (-flat, 0.0), (0.0, flat), (0.0, -flat)):
                o2 = o.copy()
                o2[0] += ox
                o2[lt] += ol
                r2 = hull.cast(o2, d)
                if r2 is None:
                    miss += 1
                else:
                    ts.append(r2[0])
            spread = max(ts) - min(ts)
            align = float(-(n @ d))
            score = spread * 3.0 + miss * 25.0 + (1.0 - align) * 40.0 + (60.0 if align < 0.75 else 0.0) + 6.0 * abs(dl) / max(lat_span, 1e-6) + 20.0 * abs(dx) / length + (0.0 if plating else 400.0)
            if best is None or score < best["score"]:
                best = {"score": score, "p": p, "n": n, "out": -d, "spread": spread, "align": align, "plating": plating}
    return best


def find_pair(hull: Hull, axis: int, sgn: int, x_nom: float, lat_nom: float, lat_span: float, length: float, far: float) -> list[dict]:
    """A site on the starboard side (a flank: the +y one; the deck or the keel: the half with y > 0) and its mirror on the other side where the hull is as good there, else the best found
    independently: a ship's jets come in pairs, and a pair that is not the same on both sides would make one side of a turn look unlike the other."""
    flat = float(np.clip(0.012 * length, 2.5 if length >= SMALL_M else 0.25, 10.0))
    if axis == 1:
        a = find_site(hull, 1, +1, x_nom, lat_nom, lat_span, length, far)
        if a is None:
            b = find_site(hull, 1, -1, x_nom, lat_nom, lat_span, length, far)
            return [b] if b else []
        m = find_site(hull, 1, -1, float(a["p"][0]), float(a["p"][2]), 0.0, length, far, x_span=0.0)
    else:
        a = find_site(hull, 2, sgn, x_nom, abs(lat_nom), lat_span, length, far)
        if a is None:
            return []
        m = find_site(hull, 2, sgn, float(a["p"][0]), -float(a["p"][1]), 0.0, length, far, x_span=0.0)
    if m is None or not m["plating"] or m["spread"] > 3 * flat:
        m = find_site(hull, 1, -1, x_nom, lat_nom, lat_span, length, far) if axis == 1 else find_site(hull, 2, sgn, x_nom, -abs(lat_nom), lat_span, length, far)
    return [a] + ([m] if m else [])


# ------------------------------------------------------------------------------------------------------------------------ the nozzles
def site_set(hull: Hull, with_stern: bool) -> list[dict]:
    """The standard pack: yaw jets on the flanks, pitch and roll jets on the deck and the keel, braking jets on the bow's shoulders. Unit vectors in the ship frame."""
    lo, hi = hull.min, hull.max
    L = float(hi[0] - lo[0])
    hh = float(hi[2] - lo[2]) / 2
    hw = float(hi[1] - lo[1]) / 2
    zc = float(lo[2] + hi[2]) / 2
    far = max(hw, hh) * 3 + 50.0
    small = L < SMALL_M
    r = float(np.clip(0.004 * L, 0.05, 0.2)) if small else float(np.clip(0.0016 * L, 0.35, 1.6))
    out: list[dict] = []

    def add(kind: str, site: dict | None, exhaust: np.ndarray | None = None) -> None:
        if site is None:
            return
        n = site["n"]
        d = (n * 0.5 + site["out"] * 0.5) if exhaust is None else exhaust          # (a jet leaves along the way out of the hull; the slab's slope tilts it a little, not a lot)
        d = d / max(np.linalg.norm(d), 1e-9)
        out.append({"k": kind, "p": site["p"] + n * (0.05 if small else 0.4), "d": d, "r": r, "q": round(site["spread"], 2)})

    def width_at(x: float) -> float:
        """Half the hull's width at a station (the farthest vertices on either side within a band of the length)."""
        m = np.abs(hull.A[:, 0] - x) < 0.012 * L
        return float(np.abs(hull.A[m, 1]).max()) if m.any() else 0.0

    def station(u: float, toward: float) -> float:
        """The station nearest u (moving toward `toward`) where the hull is at least half as wide as it is at its widest: a spear's tip is no place for a nozzle pair."""
        step = 0.02 if toward > u else -0.02
        while abs(u - toward) > 1e-6 and width_at(lo[0] + u * L) < 0.5 * hw:
            u += step
        return u

    # (a ship with thruster blocks of her own at the stern has their yaw and roll jets and a pitch one way (they look up the deck); the other way she is given by jets on the keel there)
    ends = [("bow", station(0.86, 0.5)), ("stern", station(0.14, 0.5))]
    for name, u in ends:
        x = float(lo[0] + u * L)
        for s in (find_pair(hull, 1, +1, x, zc, 0.35 * hh, L, far) if (name == "bow" or with_stern) else []):
            add("yaw", s)
        for sz in (+1, -1):
            if name == "stern" and sz > 0 and not with_stern:
                continue
            for s in find_pair(hull, 2, sz, x, 0.45 * hw, 0.28 * hw, L, far):
                add("pitch", s)
    xb = float(lo[0] + min(0.80, station(0.80, 0.5) + 0.0) * L)
    fwd = np.array([1.0, 0.0, 0.0])
    for dz in (+0.28, -0.28):
        for s in find_pair(hull, 1, +1, xb, zc + dz * hh, 0.12 * hh, L, far):
            add("brake", s, exhaust=s["n"] * 0.5 + fwd * 0.87)
    return out


def allocation_check(nozzles: list[dict], com: np.ndarray) -> list[str]:
    """Every push and every turn a ship can ask for must have jets that give it: for each of the eleven directions (the push ahead is the main drive's, not checked) the nozzles whose push or torque
    is along it. Returns what is missing."""
    missing = []
    F = [-np.array(n["d"]) for n in nozzles]
    T = np.array([np.cross(np.array(n["p"]) - com, f) for n, f in zip(nozzles, F)])
    tmax = np.abs(T).max(axis=0)                                # (each axis against its own best nozzle: a ship rolls with a short lever, it pitches and yaws with its length)
    tmax = np.where(tmax > 1e-9, tmax, 1.0)
    want = {"push -x (brake)": np.array([-1.0, 0, 0]), "push +y": np.array([0, 1.0, 0]), "push -y": np.array([0, -1.0, 0]), "push +z": np.array([0, 0, 1.0]), "push -z": np.array([0, 0, -1.0])}
    for k, ax in want.items():
        if not any(float(a @ ax) > 0.25 for a in F):
            missing.append(k)
    for k, ax in (("roll +", [1, 0, 0]), ("roll -", [-1, 0, 0]), ("pitch +", [0, 1, 0]), ("pitch -", [0, -1, 0]), ("yaw +", [0, 0, 1]), ("yaw -", [0, 0, -1])):
        a = np.array(ax, float)
        if not any(float((t / tmax) @ a) > 0.25 for t in T):
            missing.append(k)
    return missing


# ------------------------------------------------------------------------------------------------------------------------ one ship
records: list[dict] = []
REAL_NOZZLE = K2.engine_nozzle


def spy(c, xf, R, style="astra", detail=1):
    """Stands in for ship3_kit2.engine_nozzle: notes the bell, builds nothing (the hull then has the thruster blocks but not the little bells that would be in the rays' way)."""
    o = np.asarray(xf.o, np.float64)
    d = np.asarray(xf.R, np.float64)[2]
    d = d / max(np.linalg.norm(d), 1e-9)
    r = float(R) * float(xf.s)
    records.append({"pos": [float(o[0]), float(-o[1]), float(o[2])], "dir": [float(d[0]), float(-d[1]), float(d[2])], "r": r, "lip": BELL_LIP * r, "detail": int(detail)})


def round_list(v, n=2):
    return [round(float(x), n) for x in v]


def process(name: str, spec: dict, args: dict) -> tuple[dict, Hull, dict]:
    records.clear()
    t0 = time.time()
    res = SG.build_ship(name, spec, {"seed": 0, "detail": args["detail"], "export": False, "pieces": False})
    g = res["g"]
    asm = g.assemble()
    V = np.asarray(asm["V"], np.float64) * np.array([1.0, -1.0, 1.0])            # the Unreal frame
    slot_ok = np.array([m.split("_")[-1] in PLATING for m in g.mats], bool)
    hull = Hull(V, asm["F"], slot_ok[np.asarray(asm["M"], np.int64)])
    bells = [dict(r) for r in records]
    main = [b for b in bells if b["dir"][0] < -0.5 and b["detail"] > 0] or [b for b in bells if b["dir"][0] < -0.5]
    quads = [b for b in bells if b not in main]
    lo, hi = hull.min, hull.max
    L = float(hi[0] - lo[0])
    com = np.array([(lo[0] + hi[0]) / 2, 0.0, (lo[2] + hi[2]) / 2])
    pack = site_set(hull, with_stern=not quads)
    nozzles = []
    for q in quads:
        nozzles.append({"k": "quad", "p": np.array(q["pos"]), "d": np.array(q["dir"]), "r": q["r"]})
    nozzles += pack
    miss = allocation_check(nozzles, com)
    if main:
        P = np.array([b["pos"] for b in main])
        c = P.mean(axis=0)
        span = float(max(P[:, 1].max() - P[:, 1].min(), P[:, 2].max() - P[:, 2].min()))
        rmax = max(b["r"] for b in main)
        drive = {"p": round_list(c), "w": round(span + 2 * rmax, 1), "r": round(rmax, 2), "n": len(main)}
    else:
        drive = {"p": round_list([lo[0], 0, 0]), "w": round(0.2 * float(hi[1] - lo[1]), 1), "r": 3.0, "n": 0}
    cls = CLASS_OF[name]
    rec = {
        "mesh": name, "len": round(L, 1), "x": [round(float(lo[0]), 1), round(float(hi[0]), 1)], "com": round_list(com),
        "box": round_list([(hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2]),
        "drive": drive,
        "nozzles": [{"k": n["k"], "p": round_list(n["p"]), "d": round_list(n["d"], 3), "r": round(float(n["r"]), 2)} for n in nozzles],
    }
    kinds = {}
    for n in nozzles:
        kinds[n["k"]] = kinds.get(n["k"], 0) + 1
    print(f"{cls}: {len(V):,} vertices, {len(asm['F']):,} triangles, {L:.0f} m long; {len(main)} drive bells, {len(nozzles)} jets {kinds}; {time.time() - t0:.1f} s"
          + (f"  MISSING {miss}" if miss else "  (every push and turn has jets)"))
    for n in pack:
        if n["q"] > 6.0:
            print(f"    note: {n['k']} jet at {round_list(n['p'], 1)} sits on a patch {n['q']:.1f} m out of flat")
    return rec, hull, {"nozzles": nozzles, "main": main}


# ------------------------------------------------------------------------------------------------------------------------ previews
def jet_object(name: str, base: np.ndarray, d: np.ndarray, length: float, radius: float, col, strength: float):
    """A thin emissive cone from the nozzle along its exhaust (Blender frame: y mirrored)."""
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=radius, radius2=radius * 0.15, depth=length)
    o = bpy.context.active_object
    o.name = name
    dv = Vector((d[0], -d[1], d[2])).normalized()
    o.rotation_euler = dv.to_track_quat("Z", "Y").to_euler()
    o.location = Vector((base[0], -base[1], base[2])) + dv * (length / 2)
    mat = bpy.data.materials.new(name + "_m")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (col[0], col[1], col[2], 1.0)
    em.inputs["Strength"].default_value = strength
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    o.data.materials.append(mat)
    return o


def preview(name: str, spec: dict, rec: dict, outdir: str, args: dict) -> None:
    cls = CLASS_OF[name]
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    PV.make_materials(spec["fac"])
    K2.engine_nozzle = REAL_NOZZLE                              # (the preview's hull has its real bells)
    try:
        res = SG.build_ship(name, spec, {"seed": 0, "detail": args["detail"], "export": False, "pieces": False})
    finally:
        K2.engine_nozzle = spy
    g = res["g"]
    asm = g.assemble()
    asm, mats = SG.compact(asm, g.mats)
    hullobj = B.build_object(name, asm, mats)
    L = rec["len"]
    nozzles = rec["nozzles"]
    for i, n in enumerate(nozzles if args.get("jets", True) else []):
        col = KIND_COL.get(n["k"], (1, 1, 1))
        jet_object(f"jet{i}", np.array(n["p"]), np.array(n["d"]), L * 0.03, L * 0.0032, col, 7.0)
    w, h = args["size"]
    PV.configure(w, h, args["samples"], exposure=0.0)
    V = np.array([v.co[:] for v in hullobj.data.vertices])
    V = V * np.array([1.0, 1.0, 1.0])
    x0, x1 = float(V[:, 0].min()), float(V[:, 0].max())
    views = {
        "stern": (V[V[:, 0] < x0 + 0.34 * L], (-0.8, 0.62, 0.42)),
        "bow": (V[V[:, 0] > x1 - 0.34 * L], (0.8, 0.62, 0.42)),
    }
    quads = [n for n in nozzles if n["k"] == "quad"]
    if quads:
        # a thruster block close up: the hull's vertices within a few block-widths of the first quad, seen from outside and a little aft
        c0 = np.array(quads[0]["p"])
        cb = np.array([c0[0], -c0[1], c0[2]])
        near = V[np.linalg.norm(V - cb, axis=1) < max(9.0 * float(quads[0]["r"]) * 3.0, 12.0)]
        if len(near) > 20:
            views["quad"] = (near, (-0.45, -0.85 * float(np.sign(c0[1]) or 1.0), 0.32))
    for tag, (pts, direction) in views.items():
        cam, tgt = PV.fit_camera("cam", pts, np.array(direction), lens=40.0 if tag != "quad" else 55.0, aspect=w / h, margin=0.08 if tag != "quad" else 0.2, clip_end=200000.0)
        PV.rig(cam.location, tgt, key_az=62.0, key_el=26.0, key=5.0, fill=0.9, rim=0.8)
        PV.render(cam, os.path.join(outdir, f"thrusters_{cls}_{tag}{'' if args.get('jets', True) else '_bare'}.jpg"))
        bpy.data.objects.remove(cam, do_unlink=True)


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"out": os.path.join(ROOT, "data", "space", "thrusters.json"), "only": [], "detail": 0.02, "preview": None, "size": (1500, 850), "samples": 24}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--out":
            a["out"] = argv[i + 1]
            i += 1
        elif k == "--only":
            a["only"] = argv[i + 1].split(",")
            i += 1
        elif k == "--detail":
            a["detail"] = float(argv[i + 1])
            i += 1
        elif k == "--preview":
            a["preview"] = argv[i + 1]
            i += 1
        elif k == "--size":
            a["size"] = tuple(int(x) for x in argv[i + 1].split("x"))
            i += 1
        elif k == "--samples":
            a["samples"] = int(argv[i + 1])
            i += 1
        elif k == "--no-jets":
            a["jets"] = False                                    # the preview of the hull with its nozzles, without the cones that mark the jets
        i += 1
    return a


def main() -> None:
    a = parse_args()
    K2.engine_nozzle = spy                                      # engine_bank and the craft builders call it through the module
    reg = SG.registry()
    names = [n for n in CLASS_OF if n in reg and (not a["only"] or CLASS_OF[n] in a["only"])]
    out = {"_doc": "Manoeuvring jets of the capital ships, ship frame (x forward, y starboard, z up), metres from the mesh's origin; art/blender/space3_thrusters.py. "
                   "k: quad (the generator's own thruster blocks) | yaw | pitch | brake (the standard pack, on the hull's surface). d: the exhaust's direction (unit); the ship is pushed the other way. "
                   "drive: the main drive's centre, width and bell radius (where a wake starts, how wide); com: the middle a ship turns about; box: the hull's half sizes.",
           "version": 1, "classes": {}}
    kept = {}
    if os.path.exists(a["out"]) and a["only"]:
        kept = json.load(open(a["out"], encoding="utf-8")).get("classes", {})
    out["classes"].update(kept)
    for n in names:
        rec, hull, extra = process(n, reg[n], a)
        out["classes"][CLASS_OF[n]] = rec
        if a["preview"]:
            preview(n, reg[n], rec, a["preview"], a)
    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    with open(a["out"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("written", a["out"])
    print("THRUSTERS_OK")


if __name__ == "__main__":
    main()
