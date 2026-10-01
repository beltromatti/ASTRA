"""ASN Aquila interior kit (NAVE, phase F4.1) — the generator: builds every mesh of the ship's interior kit, exports the FBX files and a manifest.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py -- [<output_dir>] [options]

  <output_dir>        FBX files + manifest.json (default art/export/ship, not in git)
Options:
  --only A,B          build only these meshes (names without the SM_SHIP_ prefix are accepted; a glob such as Sign_* works; no manifest is written)
  --plan <file>       the plan JSON that says which signs and plates are needed (default data/ship/aquila_plan.json)
  --no-export         build (and check) without writing FBX files
  --no-checks         skip the mesh checks and the route ray casts
  --preview <dir>     render previews into <dir> (Eevee, headless): --views rooms,modules,d4   (default: none); --samples N; --room-views door,corner_a,far
  --save-blend <f>    write the built meshes as a .blend

Everything is in the ship's layout frame (X forward, Y starboard, Z up, metres; FB mirrors Y on the way out, so the FBX meshes land on the plan in
Unreal). The corridor modules (SM_SHIP_<S|P>_<name>, 4 x 4 m, origin on the floor at the aft end of the centre line) and the room prefabs (origin on
the floor at the corridor-side corner, x along the corridor, y into the room) are placed by the plan (data/ship/aquila_plan.json, "placements") with
tools/ue_scripts/build_ship_interior.py. Opaque meshes are Nanite in Unreal; the ones with a glass slot (observation rooms) stay classic meshes.
"""
from __future__ import annotations

import fnmatch
import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as BL  # noqa: E402
import ship_catalog as CAT  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_plan as P  # noqa: E402
import ship_spec as SPEC  # noqa: E402

ROOT = SL.ROOT
DEFAULT_OUT = os.path.join(ROOT, "art", "export", "ship")
TRI_BUDGET = 150_000                       # per mesh (Nanite: the disk and the import time, not the frame time)

# prefab key -> (module, function) of the room builders
ROOMS = {
    "galley": ("ship_rooms_service", "galley"), "galley_pass": ("ship_rooms_service", "galley_pass"),
    "store_dry": ("ship_rooms_service", "store_dry"), "store_cold": ("ship_rooms_service", "store_cold"), "hold": ("ship_rooms_service", "hold"),
    "heads": ("ship_rooms_service", "heads"), "laundry": ("ship_rooms_service", "laundry"), "hydro": ("ship_rooms_service", "hydro"),
    "lounge": ("ship_rooms_social", "lounge"), "games": ("ship_rooms_social", "games"), "library": ("ship_rooms_social", "library"),
    "quiet": ("ship_rooms_social", "quiet"), "observation": ("ship_rooms_social", "observation"), "bow_obs": ("ship_rooms_social", "bow_obs"),
    "concourse": ("ship_rooms_hub", "concourse"), "berth_lobby": ("ship_rooms_hub", "berth_lobby"), "stair_tower": ("ship_rooms_hub", "stair_tower"),
    "observation_d14": ("ship_rooms_social", "observation_d14"), "store_dry_d10": ("ship_rooms_service", "store_dry_d10"),
    "surgery": ("ship_rooms_med", "surgery"), "quarantine": ("ship_rooms_med", "quarantine"), "pharmacy": ("ship_rooms_med", "pharmacy"),
    "lab": ("ship_rooms_work", "lab"), "workshop": ("ship_rooms_work", "workshop"), "armory": ("ship_rooms_work", "armory"),
    "cabins": ("ship_rooms_work", "cabins"),
    # NAVE-2
    "transporter": ("ship_rooms_science", "transporter"),
    "sensor_archive": ("ship_rooms_science2", "sensor_archive"), "sensor_room": ("ship_rooms_science2", "sensor_room"),
    "lab_bio": ("ship_rooms_science2", "lab_bio"), "lab_astro": ("ship_rooms_science2", "lab_astro"), "lab_phys": ("ship_rooms_science2", "lab_phys"),
    "radiator_pumps": ("ship_rooms_engineering", "radiator_pumps"), "machinery": ("ship_rooms_engineering", "machinery"), "machinery_b": ("ship_rooms_engineering", "machinery_b"),
    "dc_locker": ("ship_rooms_engineering", "dc_locker"), "power_control": ("ship_rooms_engineering", "power_control"),
}
EXTRA = {"SM_SHIP_StairTowerTop": ("ship_rooms_hub", "stair_tower_top"), "SM_SHIP_StairTowerBottom": ("ship_rooms_hub", "stair_tower_bottom"),
         "SM_SHIP_LadderTrunk": ("ship_rooms_hub", "ladder_trunk")}

# the material slots the Unreal side knows (shared bridge v3 instances + the ship's new ones)
KNOWN_SLOTS = set(BL.SHARED_SLOTS) | set(SL.NEW_SLOTS) | {SL.LABEL}
TRANSLUCENT_SLOTS = {BL.GLASS}


# ------------------------------------------------------------------------------------------------------------- registry
def load_plan(path: str | None):
    path = path or P.PLAN_PATH
    if os.path.exists(path):
        return P.load(path)
    return None


def needed_meshes(plan) -> set[str]:
    out: set[str] = set()
    if plan:
        for pl in plan.get("placements", {}).values():
            out.update(p["mesh"] for p in pl)
    else:                                                     # no plan yet: the signs and plates of Deck 4
        for sec in "ABCDEFGH":
            out.add(f"SM_SHIP_Sign_4{sec}")
        for spec in SPEC.PREFABS.values():
            if spec.get("plate") and spec.get("mesh"):
                out.add(f"SM_SHIP_Plate_{spec['plate']}")
    return out


def registry(needed: set[str]) -> dict[str, tuple]:
    reg: dict[str, tuple] = {}
    for tone in CAT.TONES:
        for suf in CAT.TONE_FAMILY:
            reg[CAT.module_mesh(tone, suf)] = ("module", tone, suf)
    for key, (mod, fn) in ROOMS.items():
        reg[SPEC.PREFABS[key]["mesh"]] = ("room", key, mod, fn)
    for name, (mod, fn) in EXTRA.items():
        reg[name] = ("vertical", None, mod, fn)
    for m in sorted(needed):
        if m.startswith("SM_SHIP_Sign_"):
            body = m[len("SM_SHIP_Sign_"):]
            if body[:-1].isdigit() and body[-1].isalpha():
                reg[m] = ("sign", int(body[:-1]), body[-1])
        elif m.startswith("SM_SHIP_Plate_"):
            reg[m] = ("plate", m[len("SM_SHIP_Plate_"):])
    return reg


def build_mesh(name: str, item: tuple):
    import importlib
    kind = item[0]
    if kind == "module":
        import ship_corridor as SC
        return SC.build_module(name, item[1], item[2])
    if kind in ("room", "vertical"):
        mod = importlib.import_module(item[2])
        return getattr(mod, item[3])(name)
    if kind == "sign":
        import ship_signs as SS
        return SS.sign(name, item[1], item[2])
    if kind == "plate":
        import ship_signs as SS
        return SS.plate(name, item[1])
    raise ValueError(item)


# ---------------------------------------------------------------------------------------------------------------- stats
def layout_bounds(obj) -> dict:
    """The mesh's bounds in the layout frame (Blender's Y is mirrored)."""
    pts = [Vector(c) for c in obj.bound_box]
    xs, ys, zs = [p.x for p in pts], [-p.y for p in pts], [p.z for p in pts]
    return {"min": [round(min(xs), 3), round(min(ys), 3), round(min(zs), 3)], "max": [round(max(xs), 3), round(max(ys), 3), round(max(zs), 3)]}


def uv_problems(obj) -> list[str]:
    me = obj.data
    if not me.uv_layers:
        return ["no UV map"]
    uv = me.uv_layers.active.data
    bad = 0
    big = 0
    for loop in uv:
        u, v = loop.uv
        if not (math.isfinite(u) and math.isfinite(v)):
            bad += 1
        elif abs(u) > 400.0 or abs(v) > 400.0:
            big += 1
    out = []
    if bad:
        out.append(f"{bad} UV corners are not finite")
    if big:
        out.append(f"{big} UV corners are beyond +-400 tiles")
    return out


def mesh_checks(name: str, item: tuple, obj, st: dict) -> list[str]:
    problems = []
    if st["tris"] > TRI_BUDGET:
        problems.append(f"{name}: {st['tris']} tris (budget {TRI_BUDGET})")
    for s in st["materials"]:
        if s not in KNOWN_SLOTS:
            problems.append(f"{name}: unknown material slot {s}")
    problems += [f"{name}: {p}" for p in uv_problems(obj)]
    if item[0] == "room":
        spec = SPEC.PREFABS[item[1]]
        bb = layout_bounds(obj)
        L, D, H = spec["L"], spec["D"], spec["h"]
        lo, hi = bb["min"], bb["max"]
        tol = 0.02
        if item[1] == "berth_lobby":
            xlo = -0.45                                                   # the reveal between the lobby and the Berthing
        else:
            xlo = -tol
        if lo[0] < xlo or hi[0] > L + tol or lo[1] < -0.25 - tol or hi[1] > D + 0.25 + tol:
            problems.append(f"{name}: bounds {lo} .. {hi} leave the footprint 0..{L} x 0..{D}")
        if hi[2] > 4.0 + tol and item[1] not in ("stair_tower",):
            problems.append(f"{name}: top at {hi[2]:.2f} m is above the deck pitch (4.0)")
    if item[0] == "module":
        bb = layout_bounds(obj)
        lo, hi = bb["min"], bb["max"]
        if lo[0] < -0.14 or hi[0] > CAT.MOD + 0.03 or abs(lo[1]) > CAT.SLOT_HW + 0.03 or hi[1] > CAT.SLOT_HW + 0.03:      # (the frame rib at the aft end reaches 13 cm back)
            problems.append(f"{name}: bounds {lo} .. {hi} leave the 4 x 4 slot")
    return problems


def manifest_entry(name: str, item: tuple, obj, st: dict) -> dict:
    slots = st["materials"]
    e = {"kind": item[0], "tris": st["tris"], "size_m": st["size_m"], "bounds_m": layout_bounds(obj), "slots": slots,
         "nanite": not any(s in TRANSLUCENT_SLOTS for s in slots)}
    if item[0] == "room":
        spec = SPEC.PREFABS[item[1]]
        e["prefab"] = item[1]
        e["footprint_m"] = [spec["L"], spec["D"], spec["h"]]
    return e


# ------------------------------------------------------------------------------------------------------------ route checks
class RouteChecker:
    """Ray casts along the plan's walk edges through the built meshes of a deck: the corridor centre lines and the doors must be free."""

    def __init__(self, plan: dict, objs: dict) -> None:
        self.plan = plan
        self.objs = objs
        self.bvh: dict[str, BVHTree] = {}
        self.aabb: dict[str, tuple] = {}
        dg = bpy.context.evaluated_depsgraph_get()
        for n, o in objs.items():
            ev = o.evaluated_get(dg)
            self.bvh[n] = BVHTree.FromObject(o, dg)
            pts = [Vector(c) for c in o.bound_box]
            self.aabb[n] = (min(p.x for p in pts), min(-p.y for p in pts), min(p.z for p in pts), max(p.x for p in pts), max(-p.y for p in pts), max(p.z for p in pts))

    @staticmethod
    def _inv(pos, yaw) -> Matrix:
        return (Matrix.Translation((pos[0], -pos[1], pos[2])) @ Matrix.Rotation(-math.radians(yaw), 4, "Z")).inverted()

    def hit(self, place: dict, a: tuple, b: tuple) -> float | None:
        """First hit distance along a -> b (layout coordinates, world) against a placed mesh, or None."""
        n = place["mesh"]
        if n not in self.bvh:
            return None
        inv = self._inv(place["pos"], place["yaw"])
        pa = inv @ Vector((a[0], -a[1], a[2]))
        pb = inv @ Vector((b[0], -b[1], b[2]))
        d = pb - pa
        ln = d.length
        if ln < 1e-6:
            return None
        r = self.bvh[n].ray_cast(pa, d / ln, ln)
        return r[3] if r[0] is not None else None

    def _world_aabb(self, place: dict):
        x0, y0, z0, x1, y1, z1 = self.aabb[place["mesh"]]
        yaw = place["yaw"] % 360.0
        pts = []
        for (x, y) in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
            pts.append((place["pos"][0] + x * c - y * s, place["pos"][1] + x * s + y * c))
        return (min(p[0] for p in pts), min(p[1] for p in pts), place["pos"][2] + z0, max(p[0] for p in pts), max(p[1] for p in pts), place["pos"][2] + z1)

    def check_deck(self, deck: int) -> dict:
        plan = self.plan
        places = [p for p in plan["placements"].get(str(deck), []) if p["mesh"] in self.bvh]
        boxes = [(p, self._world_aabb(p)) for p in places]
        nodes = {n["id"]: n for n in plan["graph"]["nodes"] if n["deck"] == deck}
        doors = {d["id"]: d for d in plan["doors"]}
        blocked, checked, hub_blocked, hub_checked, blank = [], 0, 0, 0, 0
        for e in plan["graph"]["edges"]:
            na, nb = nodes.get(e["a"]), nodes.get(e["b"])
            if na is None or nb is None or e["kind"] not in ("walk", "door"):
                continue
            if e.get("door") and doors.get(e["door"], {}).get("planned"):       # the door of a room not modelled yet: a plain wall, locked
                blank += 1
                continue
            hub = na["kind"] in ("room", "station") or nb["kind"] in ("room", "station")
            for h in (0.35, 1.0, 1.75):
                a = (na["p"][0], na["p"][1], na["p"][2] + h)
                b = (nb["p"][0], nb["p"][1], nb["p"][2] + h)
                x0, x1 = min(a[0], b[0]) - 0.05, max(a[0], b[0]) + 0.05
                y0, y1 = min(a[1], b[1]) - 0.05, max(a[1], b[1]) + 0.05
                first = None
                for p, bx in boxes:
                    if bx[3] < x0 or bx[0] > x1 or bx[4] < y0 or bx[1] > y1 or bx[5] < a[2] or bx[2] > a[2]:
                        continue
                    d = self.hit(p, a, b)
                    if d is not None and (first is None or d < first[0]):
                        first = (d, p["label"])
                if hub:
                    hub_checked += 1
                    hub_blocked += 1 if first else 0
                else:
                    checked += 1
                    if first:
                        blocked.append(f"{e['a']} -> {e['b']} at {h} m: blocked by {first[1]} after {first[0]:.2f} m")
        return {"deck": deck, "walk_rays": checked, "blocked": blocked, "hub_rays": hub_checked, "hub_blocked": hub_blocked, "blank_doors": blank}


    def check_spots(self, deck: int) -> dict:
        """The places where people stand, work, sit and eat (the compartments' stations: VITA puts a body there) against the room meshes: a person standing needs
        a clear column (22 cm round, knee to head), a sitter a clear torso above the seat (12 cm round), and there must be a floor under them (the platform of a pad
        counts: the ray starts half a metre above the place). A place in the way comes with the nearest clear one in the room's own frame (`try`), to put in ship_spec."""
        plan = self.plan
        comps = {c["id"]: c for c in plan["compartments"]}
        bad: list[str] = []
        tries: dict[str, str] = {}
        n = 0
        for p in plan["placements"].get(str(deck), []):
            if p["cls"] != "room" or p["mesh"] not in self.bvh or p.get("comp") not in comps:
                continue
            inv = self._inv(p["pos"], p["yaw"])
            tree = self.bvh[p["mesh"]]
            yaw = math.radians(p["yaw"])

            def why_not(x: float, y: float, z: float, kind: str):
                hs, r = ((1.0, 1.3), 0.12) if kind in ("sit", "eat") else ((0.4, 0.9, 1.4, 1.75), 0.22)
                for h in hs:
                    hit = tree.find_nearest(inv @ Vector((x, -y, z + h)), r)
                    if hit[0] is not None:
                        return f"{h} m: geometry {hit[3]:.2f} m away"
                ray = tree.ray_cast(inv @ Vector((x, -y, z + 0.5)), Vector((0.0, 0.0, -1.0)), 0.7)
                return "no floor under it" if ray[0] is None else None

            for i, st in enumerate(comps[p["comp"]].get("stations", [])):
                kind = st["kind"]
                if kind == "sleep":
                    continue
                x, y, z = st["pos"]
                n += 1
                why = why_not(x, y, z, kind)
                if why:
                    bad.append(f"{st['id']} ({kind} {st.get('role', '')}) at ({x:.1f}, {y:.1f}, {z:.2f}): {why}")
                    spec_key = comps[p["comp"]].get("prefab")
                    found = None
                    for rr in (0.15, 0.3, 0.45, 0.6, 0.8, 1.0, 1.3):
                        for k in range(16):
                            a = 2 * math.pi * k / 16
                            if why_not(x + rr * math.cos(a), y + rr * math.sin(a), z, kind) is None:
                                found = (x + rr * math.cos(a), y + rr * math.sin(a))
                                break
                        if found:
                            break
                    # to the room's own frame: undo the placement (translate, then turn back by the yaw)
                    def local(wx, wy):
                        dx, dy = wx - p["pos"][0], wy - p["pos"][1]
                        return (round(dx * math.cos(yaw) + dy * math.sin(yaw), 2), round(-dx * math.sin(yaw) + dy * math.cos(yaw), 2))
                    here = local(x, y)
                    tries.setdefault(f"{spec_key} s{i}", f"({here[0]}, {here[1]}) -> " + (f"try {local(*found)}" if found else "nothing clear within 1.3 m"))
        return {"deck": deck, "spots": n, "blocked": bad, "tries": tries}


# ------------------------------------------------------------------------------------------------------------------ main
def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = {"out_dir": DEFAULT_OUT, "only": None, "plan": None, "export": True, "checks": True, "preview": None, "views": ["rooms"], "samples": 24,
           "room_views": None, "save_blend": None, "spots": False}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--only":
            out["only"] = argv[i + 1].split(",")
            i += 1
        elif a == "--plan":
            out["plan"] = argv[i + 1]
            i += 1
        elif a == "--no-export":
            out["export"] = False
        elif a == "--spots":                                    # with --only: run the places check on the rooms that were built (the routes need the whole kit)
            out["spots"] = True
        elif a == "--no-checks":
            out["checks"] = False
        elif a == "--preview":
            out["preview"] = argv[i + 1]
            i += 1
        elif a == "--views":
            out["views"] = argv[i + 1].split(",")
            i += 1
        elif a == "--room-views":
            out["room_views"] = argv[i + 1].split(",")
            i += 1
        elif a == "--samples":
            out["samples"] = int(argv[i + 1])
            i += 1
        elif a == "--save-blend":
            out["save_blend"] = argv[i + 1]
            i += 1
        elif not a.startswith("--"):
            out["out_dir"] = a
        i += 1
    return out


def select(reg: dict, only: list[str] | None) -> list[str]:
    names = sorted(reg)
    if not only:
        return names
    pats = [x if x.startswith("SM_SHIP_") else "SM_SHIP_" + x for x in only]
    return [n for n in names if any(fnmatch.fnmatch(n, p) for p in pats)]


def main() -> None:
    args = parse_args()
    plan = load_plan(args["plan"])
    A.reset_scene()
    SL.load_labels()
    reg = registry(needed_meshes(plan))
    names = select(reg, args["only"])
    t0 = time.time()
    objs, stats, problems = {}, {}, []
    for name in names:
        t = time.time()
        obj = build_mesh(name, reg[name])
        objs[name] = obj
        stats[name] = A.stats(obj)
        pr = mesh_checks(name, reg[name], obj, stats[name]) if args["checks"] else []
        problems += pr
        print(f"  {name}: {stats[name]['tris']} tris, {len(stats[name]['materials'])} slots, {time.time() - t:.1f}s" + ("  !! " + "; ".join(pr) if pr else ""))
    total = sum(s["tris"] for s in stats.values())
    print("built", len(objs), "meshes in", round(time.time() - t0, 1), "s; tris", total)
    for pr in problems:
        print("  MESH PROBLEM:", pr)

    route = None
    if args["checks"] and plan and (not args["only"] or args["spots"]):
        rc = RouteChecker(plan, objs)
        route = [] if args["only"] else [rc.check_deck(int(d)) for d in plan.get("placements", {}) if plan["placements"][d]]
        for r in route:
            print(f"  deck {r['deck']} routes: {r['walk_rays']} corridor/door rays, {len(r['blocked'])} blocked ({r['blank_doors']} doors of rooms not modelled yet left out);"
                  f" inside rooms {r['hub_blocked']} of {r['hub_rays']} hub rays meet furniture (expected)")
            for s in r["blocked"][:20]:
                print("    BLOCKED", s)
            problems += [f"deck {r['deck']} route {s}" for s in r["blocked"]]
        spots = [rc.check_spots(int(d)) for d in plan.get("placements", {}) if plan["placements"][d]]
        for r in spots:
            print(f"  deck {r['deck']} places: {r['spots']} checked (standing, working, sitting, eating), {len(r['blocked'])} in the way of furniture")
            for t in r["blocked"][:12]:
                print("    IN THE WAY", t)
            for k, t in sorted(r["tries"].items()):
                print("    SPEC", k, t)
            problems += [f"deck {r['deck']} place {t}" for t in r["blocked"]]

    if args["export"]:
        out_dir = args["out_dir"]
        os.makedirs(out_dir, exist_ok=True)
        for name, obj in objs.items():
            A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        if not args["only"]:
            man = {"id": "ASN_Aquila_Ship_Kit", "generator": "art/blender/ship_kit.py", "frame": "layout: X forward, Y starboard, Z up, metres (FBX: cm)",
                   "meshes": {n: manifest_entry(n, reg[n], objs[n], stats[n]) for n in sorted(objs)},
                   "budget": {"meshes": len(objs), "tris_total": total, "tris_max": max(s["tris"] for s in stats.values()),
                              "tris_max_mesh": max(stats, key=lambda k: stats[k]["tris"])},
                   "new_slots": sorted({s for st in stats.values() for s in st["materials"] if s in set(SL.NEW_SLOTS)}),
                   "shared_slots": sorted({s for st in stats.values() for s in st["materials"] if s not in set(SL.NEW_SLOTS)}),
                   "translucent_meshes": sorted(n for n in objs if any(s in TRANSLUCENT_SLOTS for s in stats[n]["materials"])),
                   "problems": problems, "routes": route}
            with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
                json.dump(man, fh, indent=1)
            print("manifest:", json.dumps(man["budget"]), "new slots", man["new_slots"])
        print("SHIP_KIT_OK", out_dir)

    if args["preview"]:
        import ship_kit_preview as KP
        KP.run(args, plan, reg, objs)
    if args["save_blend"]:
        bpy.ops.wm.save_as_mainfile(filepath=args["save_blend"])
    if problems:
        print(f"{len(problems)} problems")


if __name__ == "__main__":
    main()
