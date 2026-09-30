"""ASN Aquila interior kit: the previews of ship_kit.py (Eevee, headless): every room from three or four viewpoints with its zone lights, contact
views of the corridor modules, and Deck 4 assembled from the plan (linked instances of the built meshes at the plan's placements, the plan's
zone lights, cameras chosen from the plan). Preview only: nothing here is exported."""
from __future__ import annotations

import math
import os

import bpy

import ship_catalog as CAT
import ship_lib as SL
import ship_plan as P
import ship_preview as SP                      # (puts tools/ue_scripts on the path: bridge3_layout)
import ship_spec as SPEC
import bridge3_layout as LAY

WORLD = (0.05, 0.052, 0.058)

# custom viewpoints (room frame: eye, target, fov) for the specials and the vertical pieces
ROOM_VIEWS = {
    "concourse": {"spine": ((17.0, 18.0, 1.7), (0.0, 24.0, 1.5), 84), "mess": ((1.0, 10.0, 1.7), (17.7, 22.0, 1.5), 80),
                  "lift": ((9.0, 20.0, 1.7), (0.0, 27.0, 1.6), 62)},
    "berth_lobby": {"entrance": ((13.5, 18.0, 1.7), (0.0, 18.0, 1.6), 84), "back": ((1.0, 6.0, 1.7), (14.6, 24.0, 1.6), 84)},
    "bow_obs": {"aft": ((1.0, 16.0, 1.7), (20.0, 16.0, 1.5), 84), "window": ((6.0, 4.0, 1.7), (20.0, 20.0, 1.5), 84),
                "corner": ((1.0, 1.0, 1.7), (12.0, 22.0, 1.3), 84)},
    "stair_tower": {"hall": ((6.6, 1.0, 1.7), (1.5, 6.0, 1.6), 84), "well": ((7.4, 7.4, 1.7), (1.5, 4.5, 1.8), 84), "up": ((0.8, 2.0, 1.6), (1.5, 7.0, 3.2), 80),
                    "trunk": ((7.4, 3.9, 1.7), (5.5, 7.5, 1.6), 80)},
    "cabins": {"hall": ((10.0, 1.0, 1.6), (10.0, 16.0, 1.3), 84), "far": ((10.0, 15.0, 1.6), (10.0, 0.0, 1.3), 84)},
}


def _kelvin(k: float):
    return LAY.kelvin_to_rgb(k)


# the best view(s) of each room for the progress images (--room-views best)
BEST = {"galley": ["corner_b"], "galley_pass": ["corner_a"], "store_dry": ["door"], "store_cold": ["corner_a"], "hold": ["door"], "heads": ["door"],
        "laundry": ["door"], "hydro": ["corner_a"], "lounge": ["corner_a"], "games": ["corner_b"], "library": ["corner_a"], "quiet": ["corner_a"],
        "observation": ["corner_a"], "bow_obs": ["corner"], "concourse": ["spine", "lift"], "berth_lobby": ["back"], "stair_tower": ["hall", "well"],
        "lab": ["corner_a"], "workshop": ["corner_a"], "armory": ["corner_b"], "cabins": ["far"], "surgery": ["corner_a"], "quarantine": ["corner_b"],
        "pharmacy": ["corner_a"]}
SKIP_BEST = {"observation_d14", "store_dry_d10"}


def room_views(key: str, spec: dict, names: list[str] | None) -> dict:
    L, D = spec["L"], spec["D"]
    door_x = spec["doors"][0]["x"] if spec["doors"] else L / 2
    views = {
        "door": ((door_x, 1.2, 1.6), (door_x, D, 1.2), 78),
        "corner_a": ((1.0, 1.0, 1.7), (L * 0.6, D * 0.6, 1.0), 82),
        "corner_b": ((L - 1.0, 1.0, 1.7), (L * 0.35, D * 0.6, 1.0), 82),
        "far": ((L * 0.5, D - 1.0, 1.7), (L * 0.5, 0.0, 1.2), 84),
    }
    if key in ROOM_VIEWS:
        views = dict(ROOM_VIEWS[key]) if not names else {**views, **ROOM_VIEWS[key]}
    if names:
        views = {n: v for n, v in views.items() if n in names}
    return views


def render_room(key: str, obj, out: str, samples: int, names: list[str] | None = None, plan_view: bool = True) -> list[str]:
    spec = SPEC.PREFABS[key]
    L, D, H = spec["L"], spec["D"], spec["h"]
    SP.setup(1280, 720, samples, exposure=0.0, world=WORLD)
    SP.instance(obj, (0, 0, 0), 0, f"inst_{key}")
    obj.hide_render = True
    lights = SP.spec_lights(spec, gain=1.5)
    done = []
    for name, (eye, tgt, fov) in room_views(key, spec, names).items():
        cam = SP.look_camera(name, eye, tgt, fov)
        path = os.path.join(out, f"room_{key}_{name}.jpg")
        SP.render(cam, path)
        done.append(path)
    if plan_view:
        SP.flat_light(0.5)
        cam = SP.plan_camera("plan", 0, L, 0, D, H * 0.72)
        cam.location = (L / 2, -D / 2, H * 0.72)
        path = os.path.join(out, f"room_{key}_plan.jpg")
        SP.render(cam, path)
        done.append(path)
    return done


def rooms(args: dict, plan, reg: dict, objs: dict) -> list[str]:
    out = args["preview"]
    done = []
    for name, item in reg.items():
        if name not in objs or item[0] not in ("room",):
            continue
        key = item[1]
        rv = args["room_views"]
        best = bool(rv) and rv == ["best"]
        if best and key in SKIP_BEST:
            continue
        _remove_instances()
        done += render_room(key, objs[name], out, args["samples"], BEST.get(key, ["corner_a"]) if best else rv, plan_view=not best)
    if "SM_SHIP_StairTowerTop" in objs:
        pass
    return done


KEEP: set[str] = set()


def _remove_instances() -> None:
    """Drop the lights, cameras and instances of the previous preview (keeps the built meshes)."""
    sc = bpy.context.scene
    for o in list(sc.objects):
        if o.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(o, do_unlink=True)
        elif o.type == "MESH" and o.name not in KEEP:
            bpy.data.objects.remove(o, do_unlink=True)
    for o in bpy.data.objects:
        if o.name in KEEP:
            o.hide_render = True


# ---------------------------------------------------------------------------------------------------------------- deck views
def assemble(plan: dict, deck: int, center: tuple, radius: float, objs: dict) -> int:
    n = 0
    for p in plan["placements"].get(str(deck), []):
        o = objs.get(p["mesh"])
        if o is None:
            continue
        reach = radius + (24.0 if p["cls"] == "room" else 4.0)
        if math.hypot(p["pos"][0] - center[0], p["pos"][1] - center[1]) > reach:
            continue
        SP.instance(o, p["pos"], p["yaw"], p["label"])
        n += 1
    for o in objs.values():
        o.hide_render = True
    return n


def deck_lights(plan: dict, deck: int, center: tuple, radius: float, gain: float = 1.0, bounce: float = 0.9) -> int:
    n = 0
    for c in plan["compartments"]:
        if c["deck"] != deck or c.get("status") not in ("built", "existing"):
            continue
        b = c["bounds"]
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        if math.hypot(cx - center[0], cy - center[1]) > radius + max(b[2] - b[0], b[3] - b[1]) / 2:
            continue
        for l in c.get("lights", []):
            sx, sy = l["size"]
            energy = l["lumens"] * 0.03 * gain * (1.0 + 0.4 * math.log10(1 + sx * sy))
            SP.rect_light(l["id"], l["pos"], (max(0.2, sx), max(0.2, sy)), energy, _kelvin(l.get("temperature", 4500)), False)
            n += 1
        if bounce > 0 and c["kind"] not in ("stairs",):
            w, d = b[2] - b[0], b[3] - b[1]
            SP.rect_light(f"{c['id']}.bounce", (cx, cy, c["z"][1] - 0.6), (w * 0.9, d * 0.9), bounce * w * d * (0.6 if c["kind"] == "corridor" else 1.0),
                          (1.0, 0.96, 0.9), False, direction=(0, 0, 1))
            n += 1
    return n


def _find(plan: dict, pred, key=None):
    items = [c for c in plan["compartments"] if pred(c)]
    return sorted(items, key=key or (lambda c: c["id"]))[0] if items else None


def d4_views(plan: dict) -> dict:
    """Camera set for Deck 4, from the plan: name -> (eye, target, fov, radius)."""
    z0 = P.deck_z(4)[0]
    eye_z = z0 + 1.65
    views = {}
    # the Spine's fore part seen from the concourse's opening
    views["spine_fwd"] = ((-100.5, 0.0, eye_z), (-30.0, 0.0, z0 + 1.55), 80, 70)
    # the lounge's door on the Spine, from across the corridor
    lg = _find(plan, lambda c: c["deck"] == 4 and c.get("prefab") == "lounge")
    if lg:
        for did in lg["doors"]:
            dd = next(x for x in plan["doors"] if x["id"] == did)
            if dd.get("wall") == "near":
                dx, dy = dd["pos"][0], dd["pos"][1]
                side = dd.get("side", 1)
                views["lounge_door"] = ((dx + 4.5, dy - side * 1.775, eye_z), (dx, dy, z0 + 1.6), 66, 40)
                break
    # a section blast door frame with its sign, on the Starboard Passage
    bl = [d for d in plan["doors"] if d["deck"] == 4 and d.get("kind") == "blast" and d.get("passage") == "SBP"]
    if bl:
        bl.sort(key=lambda d: d["pos"][0])
        bx = bl[len(bl) // 2]
        views["section_frame"] = ((bx["pos"][0] + 9.0, bx["pos"][1] - 0.3, eye_z), (bx["pos"][0], bx["pos"][1], z0 + 1.7), 70, 40)
    # the concourse's gate onto the Port Passage
    gates = [d for d in plan["doors"] if d["deck"] == 4 and d.get("kind") == "gate" and "gate_conc_pp" in d["id"]]
    if gates:
        gt = gates[0]
        views["gate"] = ((gt["pos"][0] - 6.0, gt["pos"][1] - 1.775 * gt.get("side", 1), eye_z), (gt["pos"][0], gt["pos"][1], z0 + 1.6), 74, 45)
    # a junction of the Spine: an X or a T module
    xs = [p for p in plan["placements"]["4"] if p["mesh"] in ("SM_SHIP_S_X", "SM_SHIP_S_T_L", "SM_SHIP_S_T_R")]
    if xs:
        xs.sort(key=lambda p: -p["pos"][0])
        j = xs[0]
        views["junction"] = ((j["pos"][0] - 9.0, j["pos"][1], eye_z), (j["pos"][0] + 4.0, j["pos"][1], z0 + 1.5), 82, 45)
    # a stair tower's door, from the Spine
    tw = _find(plan, lambda c: c["deck"] == 4 and c.get("prefab") == "stair_tower", key=lambda c: -c["bounds"][0])
    if tw:
        did = tw["doors"][0]
        dd = next(x for x in plan["doors"] if x["id"] == did)
        side = dd.get("side", 1)
        views["stairs_door"] = ((dd["pos"][0] - 6.0, dd["pos"][1] - side * 1.775, eye_z), (dd["pos"][0], dd["pos"][1], z0 + 1.5), 70, 40)
    # the side passage's long view
    views["passage"] = ((-120.0, 20.0, eye_z), (-40.0, 20.0, z0 + 1.6), 78, 60)
    return views


def d4_cuts(plan: dict) -> dict:
    """Plan-cut views (ceilings removed): name -> (x0, x1, y0, y1, radius)."""
    return {"cut_hub": (-200.0, -90.0, -34.0, 34.0, 80.0), "cut_fore": (-100.0, 108.0, -48.0, 48.0, 130.0), "cut_aft": (-330.0, -200.0, -34.0, 34.0, 90.0)}


def deck(args: dict, plan: dict, reg: dict, objs: dict, dk: int = 4) -> list[str]:
    out = args["preview"]
    done = []
    z0 = P.deck_z(dk)[0]
    SP.setup(1280, 720, args["samples"], exposure=0.0, world=WORLD)
    views = d4_views(plan) if dk == 4 else {}
    for name, (eye, tgt, fov, radius) in views.items():
        _remove_instances()
        SP.setup(1280, 720, args["samples"], exposure=0.0, world=WORLD)
        n = assemble(plan, dk, eye, radius, objs)
        m = deck_lights(plan, dk, eye, radius)
        cam = SP.look_camera(name, eye, tgt, fov)
        path = os.path.join(out, f"d{dk}_{name}.jpg")
        SP.render(cam, path)
        print(f"  {path}: {n} placements, {m} lights")
        done.append(path)
    for name, (x0, x1, y0, y1, radius) in (d4_cuts(plan).items() if dk == 4 else []):
        _remove_instances()
        SP.setup(1280, 720, max(8, args["samples"] // 2), exposure=0.0, world=WORLD)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        n = assemble(plan, dk, (cx, cy), radius, objs)
        SP.flat_light(1.0)
        cam = SP.plan_camera(name, x0, x1, y0, y1, z0 + 3.0)
        cam.location = (cx, -cy, z0 + 3.0)
        path = os.path.join(out, f"d{dk}_{name}.jpg")
        SP.render(cam, path)
        print(f"  {path}: {n} placements")
        done.append(path)
    return done


# ------------------------------------------------------------------------------------------------------------- module sheets
def modules(args: dict, plan, reg: dict, objs: dict) -> list[str]:
    """Contact views of the corridor family, in place: a run of the Spine (tone S) and of a passage (tone P) with doors, gates, a junction, a blast frame and an end."""
    out = args["preview"]
    _remove_instances()
    SP.setup(1280, 720, args["samples"], exposure=0.0, world=WORLD)

    def M(tone, suf):
        return objs.get(CAT.module_mesh(tone, suf))
    spine = ["Straight_A", "Door_L_A", "Straight_B", "Door_R_B", "Door_LR", "Straight_C", "Gate_R", "Straight_A", "T_L", "X", "Straight_B", "Bulkhead", "Straight_A"]
    for i, suf in enumerate(spine):
        o = M("S", suf)
        if o is not None:
            SP.instance(o, (4.0 * i, 0.0, 0.0), 0.0)
    pas = ["Straight_B", "Door_L_B", "Straight_A", "Door_R_A", "Gate_LR", "Straight_C", "T_R", "Straight_B", "End"]
    for i, suf in enumerate(pas):
        o = M("P", suf)
        if o is not None:
            SP.instance(o, (4.0 * i, 20.0, 0.0), 0.0)
    # a cross link from the T of the Spine (module 8) and the T of the passage (module 6)
    for k in range(3):
        o = M("P", "Straight_A")
        if o is not None:
            SP.instance(o, (4.0 * 8 + 2.0, 2.0 + 4.0 * k, 0.0), 90.0)
    for o in objs.values():
        o.hide_render = True
    for i in range(len(spine)):
        SP.rect_light(f"S{i}", (4.0 * i + 2.0, 0, 3.30), (3.4, 0.5), 200, (0.85, 0.92, 1.0))
    for i in range(len(pas)):
        SP.rect_light(f"P{i}", (4.0 * i + 2.0, 20.0, 3.30), (3.4, 0.5), 170, (1.0, 0.9, 0.75))
    SP.rect_light("fill", (26.0, 10.0, 3.6), (50.0, 24.0), 120.0, (1.0, 0.96, 0.9), direction=(0, 0, 1))
    done = []
    for name, (eye, tgt, fov) in {
        "modules_spine_a": ((-1.5, 0.3, 1.65), (30.0, -0.5, 1.5), 80),
        "modules_spine_b": ((22.0, 0.0, 1.65), (50.0, 0.0, 1.5), 80),
        "modules_frame": ((36.0, -0.4, 1.7), (46.5, 0.0, 1.9), 62),
        "modules_passage": ((-1.5, 20.3, 1.65), (30.0, 19.5, 1.5), 80),
        "modules_junction": ((30.0, 0.0, 1.65), (34.0, 5.0, 1.4), 92),
    }.items():
        cam = SP.look_camera(name, eye, tgt, fov)
        path = os.path.join(out, f"{name}.jpg")
        SP.render(cam, path)
        done.append(path)
    return done


def run(args: dict, plan, reg: dict, objs: dict) -> None:
    os.makedirs(args["preview"], exist_ok=True)
    KEEP.clear()
    KEEP.update(o.name for o in objs.values())
    done = []
    for v in args["views"]:
        if v == "rooms":
            done += rooms(args, plan, reg, objs)
        elif v == "modules":
            done += modules(args, plan, reg, objs)
        elif v == "d4" and plan:
            done += deck(args, plan, reg, objs, 4)
    print("previews:", len(done))
