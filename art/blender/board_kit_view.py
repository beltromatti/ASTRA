"""ABBORDAGGI-3 — the boarding kit seen: contact sheets of the pieces and assembled views (Eevee, headless). Preview only: nothing here is exported.

The assembled views place LINKED instances of the built meshes (layout coordinates: X forward, Y to starboard; Blender's space mirrors Y: what ship_preview.instance does for the Aquila's kit) with the
rules the game's dressing follows (Source/ASTRA/AstraBoardDress.cpp): the walls in bays, the ceiling in runs, the floor in plates, frames at the openings, lamps, props. The lights are the lamps' own.
A view of the C++ dressing itself (the bench's dump of a real plan) is `board_kit_view.py --dump file.json` (see tools/boarding.py run --scenario dress).
"""
from __future__ import annotations

import json
import math
import os

import bpy
from mathutils import Matrix, Vector

import board_kit_defs as D
import bridge3_preview as PV
import ship_lib as SL

WORLD = (0.004, 0.004, 0.005)

# the preview's look of the Mandate's materials (the engine instances are made by tools/ue_scripts/make_board_materials.py from the same numbers)
MATS = {
    D.PLATE: ("#4A4540", "Gunmetal", 1.0, (0.45, 0.8), 0.0, 0.5),
    D.FRAME: ("#2A2C30", "Gunmetal", 1.0, (0.3, 0.6), 0.35, 0.5),
    D.IRON: ("#1A1B1E", "Gunmetal", 1.0, (0.35, 0.7), 0.5, 0.5),
    D.COPPER: ("#8C5A2B", "Brushed", 1.0, (0.3, 0.55), 1.0, 0.0),
    D.VERD: ("#5F7F6B", "Brushed", 1.0, (0.4, 0.7), 0.6, 0.0),
    D.DECK: ("#3B3A3C", "DiamondPlate", 1.0, (0.4, 0.75), 0.6, 0.0),
    D.HAZARD: ("#B07816", "PanelPaint", 1.0, (0.5, 0.8), 0.0, 0.0),
    D.SOOT: ("#09090A", "PanelPaint", 1.0, (0.8, 0.95), 0.0, 0.0),
    D.STENCIL: ("#B78A55", "PanelPaint", 1.0, (0.6, 0.85), 0.0, 0.0),
    D.CLOTH: ("#6B2E1E", "FabricWoven", 2.0, (0.8, 0.95), 0.0, 0.0),
    D.UNIFORM: ("#2A2823", "FabricWoven", 3.0, (0.85, 0.95), 0.0, 0.0),
}


def materials() -> None:
    SL.make_preview_materials()                       # the Aquila's instances the kit shares (the lamps' palette, the rubber) and the neutral grey for the unknown
    for slot, (hexc, tex, uv, rough, metal, mmap) in MATS.items():
        PV.pbr(slot, PV.srgb_to_linear(hexc), tex, uv, rough, metal, mmap, 0.5, 0.6)
    PV.pbr(D.SCREEN, (0.004, 0.004, 0.005), None, 1.0, (0.2, 0.3), 0.0, 0.0, 0.0, 0.0, emission=((1.0, 0.45, 0.06), 0.15))
    PV.pbr("StageMat", (0.05, 0.05, 0.052), None, 1.0, (0.5, 0.7), 0.0, 0.0, 0.0, 0.0)


_INSTANCES: list = []


def prepare(built: dict) -> None:
    """The built meshes are masters: they stay out of the pictures (the instances are what is seen)."""
    for r in built.values():
        r["obj"].hide_render = True
        r["obj"].hide_viewport = True


def instance(obj, pos, yaw: float = 0.0, scale=(1.0, 1.0, 1.0)):
    """A linked duplicate of `obj` at layout `pos` (x, y, z), turned by layout `yaw` (degrees, +x towards +y), scaled in the piece's own axes."""
    inst = bpy.data.objects.new(obj.name + ".i", obj.data)
    bpy.context.scene.collection.objects.link(inst)
    _INSTANCES.append(inst)
    inst.matrix_world = Matrix.Translation((pos[0], -pos[1], pos[2])) @ Matrix.Rotation(-math.radians(yaw), 4, "Z") @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0))
    return inst


def light(name: str, pos, energy: float, color, size: float = 0.12, shadow: bool = True, kind: str = "POINT"):
    return PV.add_light(kind, name, pos, energy, color, size=(size, size), shadow=shadow)


def start(w: int = 1600, h: int = 900, samples: int = 40, exposure: float = 0.0) -> None:
    PV.clear_scene_lights_and_cameras()
    PV.set_world(WORLD, 1.0)
    PV.configure_render(w, h, samples, exposure=exposure)


def camera(name: str, eye, target, fov: float = 80.0):
    dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    return PV.add_camera(name, eye, math.degrees(math.atan2(dy, dx)), math.degrees(math.atan2(dz, math.hypot(dx, dy))), fov)


def render(cam, path: str) -> str:
    return PV.render(cam, path + ".jpg" if not path.endswith(".jpg") else path)


# ================================================================================================================================ a contact sheet
def _group_keys(built: dict) -> list[tuple[str, str, list[str]]]:
    by = {}
    for key in built:
        by.setdefault(D.PIECES[key][1], []).append(key)
    walls = by.get("wall", [])
    out = []
    half = (len(walls) + 1) // 2
    out.append(("walls_1", "wall", walls[:half]))
    if walls[half:]:
        out.append(("walls_2", "wall", walls[half:]))
    for fr, nm in (("ceiling", "ceiling"), ("floor", "floor"), ("opening", "opening"), ("prop", "props"), ("body", "bodies")):
        keys = by.get(fr, [])
        if not keys:
            continue
        if fr == "prop" and len(keys) > 4:
            for i in range(0, len(keys), 4):
                out.append((f"props_{i // 4 + 1}", fr, keys[i:i + 4]))
        else:
            out.append((nm, fr, keys))
    return out


def _clear_instances() -> None:
    for o in list(_INSTANCES):
        if o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    _INSTANCES.clear()
    for o in list(bpy.context.scene.objects):
        if o.type in {"LIGHT", "CAMERA"} or o.name.startswith("Stage"):
            bpy.data.objects.remove(o, do_unlink=True)


def sheet(built: dict, base: str) -> None:
    """Each group of pieces on its own in front of a plain dark wall: walls upright on the wall, ceiling pieces hung from a ceiling slab, floor pieces and props laid out on the floor, lit from the front."""
    materials()
    prepare(built)
    start(1800, 1000, 48, 0.7)
    for name, frame, keys in _group_keys(built):
        _clear_instances()
        gap = {"wall": 0.3, "ceiling": 0.5, "floor": 0.4, "opening": 0.9, "prop": 0.7, "body": 0.7}[frame]
        total = sum((built[k]["max_cm"][0] - built[k]["min_cm"][0]) / 100.0 + gap for k in keys)
        if frame in ("opening", "prop", "body"):
            total = sum(max(built[k]["max_cm"][0] - built[k]["min_cm"][0], built[k]["max_cm"][1] - built[k]["min_cm"][1]) / 100.0 + gap for k in keys)
        span_h = max((built[k]["max_cm"][2] for k in keys), default=100.0) / 100.0
        x = -total / 2
        wall = bpy.data.objects.new("StageWall", None)
        # the stage: a floor, a back wall, a ceiling slab
        def slab(c, sc):
            bpy.ops.mesh.primitive_cube_add(size=1.0)
            o = bpy.context.active_object
            o.name = "Stage" + o.name
            o.scale = sc
            o.location = (c[0], -c[1], c[2])
            return o
        fl = slab((0.0, 2.0, -0.05), (total + 8.0, 12.0, 0.1))
        fl.data.materials.append(bpy.data.materials["StageMat"])
        bw = slab((0.0, -0.06, 2.0), (total + 8.0, 0.1, 4.0))
        bw.data.materials.append(bpy.data.materials["StageMat"])
        if frame == "ceiling":
            cl = slab((0.0, 2.0, 3.05), (total + 8.0, 12.0, 0.1))
            cl.data.materials.append(bpy.data.materials["StageMat"])
        for key in keys:
            o = built[key]["obj"]
            lo, hi = built[key]["min_cm"], built[key]["max_cm"]
            w = (hi[0] - lo[0]) / 100.0
            if frame == "wall":
                instance(o, (x - lo[0] / 100.0, 0.0, 0.0), 0.0)
            elif frame == "ceiling":
                instance(o, (x - lo[0] / 100.0, 1.2, 3.0), 0.0)
            elif frame == "floor":
                instance(o, (x - lo[0] / 100.0, 1.2, 0.0), 0.0)
            elif frame == "opening":
                w = max(w, (hi[1] - lo[1]) / 100.0)
                instance(o, (x + w / 2, 1.5, 0.0), 0.0)
            else:                                    # props and bodies: the footprint's middle at x, their front (+x) turned to the camera
                w = max(w, (hi[1] - lo[1]) / 100.0, (hi[0] - lo[0]) / 100.0)
                instance(o, (x + w / 2, 1.8, 0.0), 90.0 if frame == "prop" else 0.0)
            x += w + gap
        span = max(total, 6.0)
        dist = max(5.0, span * 0.9) if frame != "ceiling" else max(5.0, span * 0.8)
        if frame == "wall":
            light("key", (-span * 0.2, dist * 0.5, 3.3), 2600, (1.0, 0.75, 0.45), size=1.0, shadow=True)
            light("key2", (span * 0.25, dist * 0.5, 2.0), 1400, (1.0, 0.5, 0.25), size=1.0, shadow=True)
            cam = camera("c", (0.0, dist, 1.45), (0.0, 0.0, 1.35), 58)
        elif frame == "ceiling":
            light("key", (0.0, 3.5, 1.6), 1800, (1.0, 0.75, 0.45), size=0.6, shadow=True)
            cam = camera("c", (0.0, 1.2 + dist, 0.9), (0.0, 1.2, 2.7), 58)
        elif frame == "floor":
            light("key", (0.0, 3.5, 3.0), 2200, (1.0, 0.75, 0.45), size=0.8, shadow=True)
            cam = camera("c", (0.0, dist * 0.8, 3.6), (0.0, 1.2, 0.0), 62)
        else:
            light("key", (-span * 0.15, 1.8 + span * 0.5, 3.6), 2600, (1.0, 0.75, 0.45), size=1.0, shadow=True)
            light("fill", (span * 0.3, 1.8 + span * 0.4, 2.0), 1100, (1.0, 0.45, 0.2), size=1.0, shadow=False)
            cam = camera("c", (0.0, 1.8 + span * 0.7 + 1.0, 1.9 + span * 0.05), (0.0, 1.8, 0.8), 62)
        render(cam, f"{base}_{name}")


# ================================================================================================================================ an assembled corridor and doors
def _wall_line(built, y_wall: float, n_y: float, x0: float, x1: float, z_ceiling: float, keys: list[str], rng_seed: int, gaps=()):
    """Bays along a wall from x0 to x1 (layout X) on the wall at y_wall whose inward normal is (0, n_y): with ribs at the ends and between every two bays. gaps: (x_from, x_to) with no bays."""
    import random
    rng = random.Random(rng_seed)
    bw = D.BAY_W
    L = x1 - x0
    n = max(1, int(round(L / bw)))
    wc = L / n
    sx = wc / bw
    for i in range(n):
        xa, xb = x0 + i * wc, x0 + (i + 1) * wc
        if any(g[0] < (xa + xb) / 2 < g[1] for g in gaps):
            continue
        key = rng.choice(keys)
        o = built[key]["obj"]
        if n_y > 0:       # inward normal +Y: viewer's right is +X, the piece starts at its left end (the smaller X)
            instance(o, (xa, y_wall + 0.005, 0.0), 0.0, (sx, 1.0, 1.0))
        else:             # inward normal -Y: the viewer's right is -X, the piece starts at its left end (the larger X)
            instance(o, (xb, y_wall - 0.005, 0.0), 180.0, (sx, 1.0, 1.0))
    ribs = [x0 + i * wc for i in range(0, n + 1, 2)] + ([x1] if n % 2 else [])
    for xr in sorted(set(ribs)):
        o = built["rib"]["obj"]
        rw = D.RIB_W
        if n_y > 0:
            instance(o, (xr - rw / 2, y_wall + 0.005, 0.0), 0.0, (1.0, 1.0, z_ceiling / D.RIB_H))
        else:
            instance(o, (xr + rw / 2, y_wall - 0.005, 0.0), 180.0, (1.0, 1.0, z_ceiling / D.RIB_H))


def corridor(built: dict, base: str) -> None:
    """A spine-like corridor: 3.0 m between the walls, 3.2 m high, 18 m long, a pressure bulkhead across it at x = 9, a door in each wall."""
    materials()
    prepare(built)
    start(1600, 900, 56, 0.9)
    W, H, L = 3.0, 3.2, 18.0
    hw = W / 2
    wall_t = 0.12
    # the structure the game keeps (the collision boxes): floor, ceiling, walls, as plain cubes of the Structure's colour
    def cube(c, s, mat):
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        o = bpy.context.active_object
        o.scale = s
        o.location = (c[0], -c[1], c[2])
        o.data.materials.append(bpy.data.materials[mat])
        return o
    cube((L / 2, 0, -0.11), (L, W + 0.5, 0.22), D.FRAME)
    cube((L / 2, 0, H + 0.1), (L, W + 0.5, 0.2), D.FRAME)
    cube((L / 2, -hw - wall_t / 2, H / 2), (L, wall_t, H), D.FRAME)
    cube((L / 2, hw + wall_t / 2, H / 2), (L, wall_t, H), D.FRAME)
    cube((-0.05, 0, H / 2), (0.1, W, H), D.IRON)
    cube((L + 0.05, 0, H / 2), (0.1, W, H), D.IRON)
    # walls: bays on both sides; a door in each wall at x = 4.5 and 13.5 (the bays leave a gap of the opening's width)
    keys = ["wall_a", "wall_b", "wall_c", "wall_a", "wall_e", "wall_hold", "wall_motto", "wall_d"]
    gaps_l = [(4.5 - 0.95, 4.5 + 0.95), (9.0 - 0.3, 9.0 + 0.3)]
    gaps_r = [(13.5 - 0.95, 13.5 + 0.95), (9.0 - 0.3, 9.0 + 0.3)]
    _wall_line(built, -hw, +1, 0.0, L, H, keys, 3, gaps_l)
    _wall_line(built, +hw, -1, 0.0, L, H, keys, 4, gaps_r)
    # door frames
    for (x, y, nrm) in ((4.5, -hw - wall_t, 1), (13.5, hw + wall_t, -1)):
        for sx in (-1, 1):
            instance(built["jamb"]["obj"], (x + sx * (D.DOOR_W / 2 + 0.1), y + (wall_t if nrm > 0 else -wall_t) / 1.0 * 0.0, 0.0), 90.0 if nrm > 0 else 90.0)
        instance(built["door_header"]["obj"], (x, y, D.DOOR_H), 90.0, (1.0, 1.0, 1.0))
    # the pressure bulkhead at x = 9: jambs, header, leaf (shut)
    bj, bh, bl = built["blast_jamb"]["obj"], built["blast_header"]["obj"], built["blast_leaf"]["obj"]
    for sy in (-1, 1):
        instance(bj, (9.0, sy * (D.BLAST_W / 2 + 0.17), 0.0), 90.0)
    instance(bh, (9.0, 0.0, D.BLAST_H), 90.0, (1.0, 1.0, 1.0))
    instance(bl, (9.0, 0.0, 0.0), 90.0, (1.0, 1.0, 1.0))
    # the ceiling: pipes along both sides, a tray down the middle with the lamps, a vent
    for xi in range(int(L / D.RUN_L)):
        x = xi * D.RUN_L
        instance(built["pipes"]["obj"], (x, -hw + 0.35, H), 0.0)
        instance(built["pipes"]["obj"], (x, hw - 0.35, H), 0.0)
        instance(built["tray"]["obj"], (x, 0.0, H), 0.0)
    for xl in range(1, int(L / 3.0)):
        x = xl * 3.0
        instance(built["lamp"]["obj"] if xl % 2 else built["lamp_red"]["obj"], (x, 0.0, H), 0.0)
        light(f"lamp{xl}", (x, 0.0, H - 0.3), 160.0 if xl % 2 else 90.0, (1.0, 0.62, 0.25) if xl % 2 else (1.0, 0.12, 0.05), size=0.2, shadow=True)
    instance(built["vent"]["obj"], (6.0, 0.0, H), 0.0)
    instance(built["cables"]["obj"], (12.0, 0.4, H), 0.0)
    # the floor: plates over the width, thresholds at the doors, guide lights along the walls
    for xi in range(int(L / D.PLATE_M)):
        instance(built["floor"]["obj"], (xi * D.PLATE_M, -hw, 0.0), 0.0)
        instance(built["floor"]["obj"], (xi * D.PLATE_M, 0.0, 0.0), 0.0)     # (the plates overlap the width a little: the preview does not care)
        instance(built["guide"]["obj"], (xi * D.PLATE_M, -hw + 0.1, 0.0), 0.0)
        instance(built["guide"]["obj"], (xi * D.PLATE_M, hw - 0.1, 0.0), 0.0)
    instance(built["threshold"]["obj"], (4.5, -hw + 0.4, 0.0), 90.0)
    instance(built["threshold"]["obj"], (13.5, hw - 0.4, 0.0), 90.0)
    instance(built["debris"]["obj"], (15.5, 0.3, 0.0), 20.0)
    instance(built["threshold"]["obj"], (9.0, 0.0, 0.0), 90.0)
    # the lamp on the Captain's rifle
    cam1 = camera("down", (0.4, 0.0, 1.62), (17.0, 0.0, 1.5), 84)
    sp = PV.add_light("SPOT", "torch", (0.5, 0.0, 1.5), 1500.0, (0.92, 0.96, 1.0), spot_angle=40.0, target=(17.0, 0.0, 1.4), shadow=False)
    render(cam1, base + "_a")
    bpy.data.objects.remove(sp, do_unlink=True)
    cam2 = camera("back", (17.6, -0.3, 1.62), (1.0, 0.0, 1.5), 84)
    sp = PV.add_light("SPOT", "torch", (17.5, -0.3, 1.5), 1500.0, (0.92, 0.96, 1.0), spot_angle=40.0, target=(1.0, 0.0, 1.4), shadow=False)
    render(cam2, base + "_b")
    bpy.data.objects.remove(sp, do_unlink=True)
    cam3 = camera("door", (6.4, 0.2, 1.62), (9.0, 0.0, 1.4), 70)
    sp = PV.add_light("SPOT", "torch", (6.5, 0.2, 1.5), 1800.0, (0.92, 0.96, 1.0), spot_angle=45.0, target=(9.0, 0.0, 1.3), shadow=False)
    render(cam3, base + "_c")


def _cube(c, s, mat: str):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    o = bpy.context.active_object
    o.scale = s
    o.location = (c[0], -c[1], c[2])
    o.data.materials.append(bpy.data.materials[mat])
    return o


def dump_view(built: dict, dump_path: str, base: str, cams: list[tuple]) -> None:
    """The C++ dressing itself, as the bench's `dress` scenario dumped it (tools/boarding.py run --scenario dress --dump <dir>): every placement of the rooms round a place made with the kit's meshes, the structure
    under it as plain boxes, the lamps that are lit as lights; one picture for each camera (x, y, z cm, yaw degrees[, pitch]: what a Captain would see)."""
    data = json.load(open(dump_path))
    materials()
    prepare(built)
    start(1600, 900, 40, 0.9)
    for kind, cx, cy, cz, hx, hy, hz in data["slabs"]:
        if kind in (3, 4, 5, 6):                      # (the dressing hides the frames and the leaves, draws no strip of light)
            continue
        _cube((cx / 100.0, cy / 100.0, cz / 100.0), (2 * hx / 100.0, 2 * hy / 100.0, 2 * hz / 100.0), D.FRAME if kind == 0 else D.DECK)
    lamps = []
    missing = set()
    for room in data["rooms"]:
        for row in room["pieces"]:
            key = row[0]
            if key not in built:
                missing.add(key)
                continue
            x, y, z, pitch, yaw, roll, sx, sy, sz = row[1:]
            instance(built[key]["obj"], (x / 100.0, y / 100.0, z / 100.0), yaw, (sx, sy, sz))
        lamps += room["lamps"]
    if missing:
        print(f"[board_kit_view] pieces in the dump that were not built: {sorted(missing)}")
    for n, cam in enumerate(cams):
        cx, cy, cz, yaw = cam[:4]
        pitch = cam[4] if len(cam) > 4 else 0.0
        near = sorted((l for l in lamps if l[3] < 2 and math.hypot(l[0] - cx, l[1] - cy) < 2200.0 and abs(l[2] - cz) < 400.0), key=lambda l: math.hypot(l[0] - cx, l[1] - cy))[:14]
        lights = []
        for i, (lx, ly, lz, st) in enumerate(near):
            if st == 0:
                lights.append(light(f"lamp{i}", (lx / 100.0, ly / 100.0, lz / 100.0), 190.0, (1.0, 0.7, 0.36), size=0.2, shadow=True))
            else:
                lights.append(light(f"lamp{i}", (lx / 100.0, ly / 100.0, lz / 100.0), 70.0, (1.0, 0.12, 0.05), size=0.2, shadow=True))
        eye = (cx / 100.0, cy / 100.0, cz / 100.0)
        cam_obj = camera(f"cam{n}", eye, (eye[0] + math.cos(math.radians(yaw)) * 10.0, eye[1] + math.sin(math.radians(yaw)) * 10.0, eye[2] + math.tan(math.radians(pitch)) * 10.0), 84)
        tgt = (eye[0] + math.cos(math.radians(yaw)) * 12.0, eye[1] + math.sin(math.radians(yaw)) * 12.0, eye[2] - 0.2)
        sp = PV.add_light("SPOT", "torch", (eye[0], eye[1], eye[2] - 0.1), 1500.0, (0.92, 0.96, 1.0), spot_angle=42.0, target=tgt, shadow=False)
        render(cam_obj, f"{base}_{chr(ord('a') + n)}")
        for o in lights + [sp]:
            bpy.data.objects.remove(o, do_unlink=True)


def render_view(built: dict, name: str, base: str) -> None:
    if name == "corridor":
        corridor(built, base)
    else:
        raise SystemExit(f"no view called {name}")
