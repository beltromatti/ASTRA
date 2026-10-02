#!/usr/bin/env python3
"""ASCENSORI, the ship's lifts (Source/ASTRA/AstraLift*.cpp, docs/ASCENSORI.md): the tools around them.

  tools/lift.py fixture                    writes data/ship/test/lifts_fixture.json: a test plan with the lift contract of docs/brief/NAVE-3.md (three shafts, one a
                                           pair of the first, and the Spine shuttle), used while the ship's own plan has no real shafts
  tools/lift.py check [plan.json]          does a plan's `vertical[]` / `transit[]` (version 2) hold the contract? Every landing's door on its shaft's wall, the car
                                           fits, every door on the same side, the stops along the line, the graph nodes there (no engine needed)
  tools/lift.py run [--scenario all|...]   the headless bench (commandlet AstraLiftSim): the motion, the dispatch, a rush hour of riders, a character riding a car
                                           from Deck 1 to Deck 9, the crew's riders in the real cars (plan, motion, brain, rush, ride, doors, riders, voice, stream,
                                           shuttle, perf), the cost per frame. Needs the editor target built for this checkout.

`run` uses -nullrhi: it never opens a window or touches the GPU, so it can run while the game or the editor is open.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "data" / "ship" / "aquila_plan.json"
FIXTURE = ROOT / "data" / "ship" / "test" / "lifts_fixture.json"
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("/Users/Shared/Epic Games/UE_5.8" if sys.platform == "darwin" else "C:/Program Files/Epic Games/UE_5.8")
ENGINE = _UE / ("Engine/Binaries/Mac/UnrealEditor-Cmd" if sys.platform == "darwin" else "Engine/Binaries/Win64/UnrealEditor-Cmd.exe")

# the plan's decks (z of the floor, m): the same the ship has
DECKS = [(1, "Command", 0.0), (2, "CIC & Communications", -36.7), (3, "Crew Country", -42.0), (4, "Crew Services", -46.0), (5, "Science & Transport", -50.0),
         (6, "Medical", -54.0), (7, "Engineering & Power", -58.0), (8, "Marines & Armory", -62.0), (9, "Flight", -66.0), (10, "Holds & Munitions", -70.0),
         (11, "Workshops & Damage Control", -74.0), (12, "Keel", -78.0)]
Z = {d: z for d, _, z in DECKS}
SECTIONS = [("A", 104, -12), ("B", -12, -104.0), ("C", -104, -160), ("D", -160, -248), ("E", -248, -320), ("F", -320, -384), ("G", -384, -440), ("H", -440, -524)]


# ------------------------------------------------------------------------------------------------------------------ fixture
def cmd_fixture(_: argparse.Namespace) -> int:
    decks = []
    for d, n, z in DECKS:
        e = {"id": d, "name": n, "z": z}
        if d == 5:
            e["sections"] = [{"id": s, "x": [a, b]} for s, a, b in SECTIONS]
        decks.append(e)

    def room(i, deck, kind, name, x0, y0, x1, y1, status="built"):
        return {"id": i, "deck": deck, "kind": kind, "name": name, "status": status, "bounds": [x0, y0, x1, y1], "z": [Z[deck], Z[deck] + 3.4]}

    comps = [
        room("bridge", 1, "bridge", "Bridge", -8.5, -7.4, 10.4, 7.4, "existing"),
        room("ready_room", 1, "ready_room", "Captain's Ready Room", -20.8, -2.1, -8.8, 2.1),
        room("cic", 2, "cic", "Combat Information Centre", -80, -8, -48, 8),
        room("wardroom", 3, "wardroom", "Wardroom", -75, -16, -51, 0),
        room("mess", 4, "mess", "Mess Hall", -160.3, -10.3, -121.7, 10.3, "existing"),
        room("berthing", 4, "berthing", "Crew Berthing", -200.3, -3.9, -175.7, 3.9, "existing"),
        room("lounge", 4, "lounge", "Crew Lounge", -70, -20, -50, -4),
        room("transporter", 5, "transporter", "Transporter Room", -30, -16, -6, 0),
        room("lab_astro", 5, "lab", "Astrometrics", -250, -16, -226, 0),
        room("medbay", 6, "medbay", "Medbay", -262.3, -9.3, -231.7, 9.3, "existing"),
        room("engineering", 7, "engineering", "Main Engineering", -372.5, -14.5, -329.5, 14.5, "existing"),
        room("power", 7, "power", "Power Control", -310, -16, -286, 0),
        room("armory", 8, "armory", "Armory", -90, -16, -66, 0),
        room("range", 8, "range", "Firing Range", -40, -16, 0, 0),
        room("flight_deck", 9, "hangar", "Flight Deck", 59.5, -28.5, 218.0, 28.5, "existing"),
        room("flight_ops", 9, "flight_ops", "Flight Operations", 20, -16, 44, 0),
    ]
    nodes = []

    def node(i, p):
        nodes.append({"id": i, "deck": 0, "p": [round(v, 3) for v in p], "kind": "lift"})
        return i

    def shaft_entry(sid, name, kind, cx, cy, w, d, normal, served, car, speed, accel, yaw):
        """normal: the unit vector from the shaft's middle to the side of its doors."""
        landings = []
        for dk in served:
            door = [cx + normal[0] * d / 2, cy + normal[1] * d / 2, Z[dk]]
            wait = [door[0] + normal[0] * 1.2, door[1] + normal[1] * 1.2, Z[dk]]
            nid = node(f"lift.{sid}.d{dk}", wait)
            landings.append({"deck": dk, "z": Z[dk], "door": [round(v, 3) for v in door], "yaw": yaw, "lobby": f"fx_{sid}_d{dk}", "node": nid})
        zs = [Z[dk] for dk in served]
        return {"id": sid, "kind": kind, "name": name, "shaft": {"x": cx, "y": cy, "w": w, "d": d, "z": [min(zs), max(zs)]}, "car": car,
                "landings": landings, "speed": speed, "accel": accel}

    vertical = [
        # the older lift of the plan (a teleport between rooms) and a stair column: no shaft, the loader leaves them out
        {"id": "lift_main", "kind": "turbolift", "name": "Turbolift", "decks": [1, 4, 6, 7, 9],
         "landings": [{"deck": 1, "room": "corridor_1a_port", "pos": [-18.6, -3.9, 0.2], "node": "lift.bridge", "existing": True}], "ride": {"fade_s": 0.4}},
        {"id": "stair_92n", "nodes": [], "towers": {}},
        shaft_entry("tl_a", "Turbolift 1", "bridge", -60.0, 6.0, 2.8, 2.8, (0, -1), list(range(9, 0, -1)), {"w": 2.4, "d": 2.4, "h": 2.6}, 8.0, 2.5, 90),
        shaft_entry("tl_a2", "Turbolift 2", "turbolift", -64.0, 6.0, 2.8, 2.8, (0, -1), list(range(9, 0, -1)), {"w": 2.4, "d": 2.4, "h": 2.6}, 8.0, 2.5, 90),
        shaft_entry("sv_b", "Service Lift 3", "service", -150.0, 14.0, 3.2, 2.8, (1, 0), list(range(12, 3, -1)), {"w": 2.8, "d": 2.4, "h": 2.8}, 5.0, 1.5, 0),
    ]
    stops = []
    for sec, x in [("A", 100.0), ("B", -12.0), ("C", -96.0), ("D", -216.0), ("E", -292.0), ("G", -428.0), ("H", -492.0)]:
        nid = node(f"fx_shuttle_{sec}", [x, 35.4, -50.0])
        stops.append({"id": f"stop_{sec}", "section": sec, "x": x, "door": [x, 38.6, -50.0], "yaw": 90, "room": f"d5_shuttle_stop_{sec}1", "node": nid})
    transit = [{"id": "spine_shuttle", "kind": "shuttle", "name": "Spine Shuttle", "deck": 5, "path": [[100.0, 40.0, -50.0], [-492.0, 40.0, -50.0]], "stops": stops,
                "car": {"mesh": "SpineCar", "length": 14.0, "w": 2.8, "h": 2.9, "floor": 0.16}, "speed": 16.0, "accel": 2.2}]
    plan = {"id": "ASN_Aquila_Lifts_Fixture", "version": 2,
            "generator": "tools/lift.py fixture (docs/ASCENSORI.md): a test plan with the lift contract of docs/brief/NAVE-3.md, not the ship",
            "frame": "X forward, Y starboard, Z up, metres; the plan's own decks and heights",
            "decks": decks, "compartments": comps, "vertical": vertical, "transit": transit, "graph": {"nodes": nodes, "edges": []}}
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(plan, indent=1) + "\n")
    print(f"{FIXTURE.relative_to(ROOT)}: {len(vertical) - 2} shafts, {len(transit)} shuttle line, {len(nodes)} nodes")
    return 0


# --------------------------------------------------------------------------------------------------------------------- check
def check_plan(plan: dict) -> tuple[list[str], list[str]]:
    """(problems, notes) of the lifts of a plan against the contract (the same checks as FAstraLiftNetwork::Load, in Python)."""
    problems: list[str] = []
    notes: list[str] = []
    nodes = {n["id"]: n for n in plan.get("graph", {}).get("nodes", [])}
    n_shafts = 0
    for v in plan.get("vertical", []):
        sh = v.get("shaft")
        if not sh or v.get("kind") == "trunk":         # the stairs and the Jefferies trunks (ladders) are not lifts
            continue
        n_shafts += 1
        who = f"lift {v['id']}"
        car = v.get("car", {})
        w, d = sh.get("w", 2.8), sh.get("d", 2.8)
        cw, cd = car.get("w", 2.4), car.get("d", 2.4)
        if cw > w - 0.08 or cd > d - 0.08:
            problems.append(f"{who}: the car ({cw} x {cd}) does not fit the shaft ({w} x {d})")
        outs = set()
        decks = []
        for ld in v.get("landings", []):
            door = ld.get("door")
            if not door:
                problems.append(f"{who}: a landing without a door")
                continue
            yaw = ld.get("yaw", 0.0)
            along_x = abs(math.cos(math.radians(yaw))) > 0.5
            delta = (door[0] - sh["x"]) if along_x else (door[1] - sh["y"])
            outs.add(("x" if along_x else "y", delta < 0))
            wall = abs(delta) - d / 2                    # the door's plane: the shaft's inside face, or out of it through the lobby's wall (up to 0.6 m)
            if wall < -0.15 or wall > 0.6:
                problems.append(f"{who}, deck {ld['deck']}: the door is {abs(delta):.2f} m from the shaft's middle, its inside face is {d / 2:.2f} m")
            if not sh["z"][0] - 0.05 <= ld["z"] <= sh["z"][1] + 0.05:
                problems.append(f"{who}, deck {ld['deck']}: the landing (z {ld['z']}) is outside the shaft {sh['z']}")
            if ld.get("node") and ld["node"] not in nodes:
                problems.append(f"{who}, deck {ld['deck']}: the graph has no node {ld['node']}")
            decks.append(ld["deck"])
        if len(outs) > 1:
            problems.append(f"{who}: its doors are on different sides of the shaft")
        if len(set(decks)) != len(decks):
            problems.append(f"{who}: a deck is listed twice")
        if len(decks) < 2:
            problems.append(f"{who}: a lift needs two landings")
        notes.append(f"{v['id']} ({v.get('kind', 'turbolift')}): decks {sorted(decks)}")
    for t in plan.get("transit", []):
        if not t.get("path"):
            continue
        who = f"line {t['id']}"
        if len(t.get("stops", [])) < 2:
            problems.append(f"{who}: a line needs two stops")
        for s in t.get("stops", []):
            if not s.get("door"):
                problems.append(f"{who}: a stop without a door")
            if s.get("node") and s["node"] not in nodes:
                problems.append(f"{who}: the graph has no node {s['node']}")
        notes.append(f"{t['id']} (shuttle): {len(t.get('stops', []))} stops, {len(t['path'])} path points")
    if not n_shafts and not any(t.get("path") for t in plan.get("transit", [])):
        notes.append("no shafts of the second version of the plan: the lifts wait for NAVE-3's plan")
    return problems, notes


def cmd_check(a: argparse.Namespace) -> int:
    path = Path(a.plan) if a.plan else PLAN
    plan = json.loads(path.read_text())
    problems, notes = check_plan(plan)
    print(f"{path}: version {plan.get('version')}")
    for n in notes:
        print("  " + n)
    for p in problems:
        print("  PROBLEM", p)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


# ------------------------------------------------------------------------------------------------------------------------ run
def cmd_run(a: argparse.Namespace) -> int:
    if not ENGINE.exists():
        print(f"no engine at {ENGINE} (set UE_ROOT)")
        return 2
    cmd = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraLiftSim", f"-scenario={a.scenario}", f"-plan={a.plan or FIXTURE}", "-nullrhi", "-unattended", "-nosound", "-nopause",
           "-stdout", "-FullStdOutLogOutput", "-NoSplash"]
    if a.seed is not None:
        cmd.append(f"-seed={a.seed}")
    if a.riders is not None:
        cmd.append(f"-riders={a.riders}")
    if a.trace:
        cmd.append("-trace")
    print(" ".join(cmd))
    out = ROOT / "Saved" / "Logs" / "lift_sim.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        p = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
    text = out.read_text()
    if "Critical error" in text or p.returncode < 0:
        # a crashed engine leaves its crash reporter spinning on the machine: it is closed here (the callstack is in the log)
        subprocess.run(["pkill", "-f", "CrashReportClient"], check=False)
        print("THE ENGINE CRASHED: " + next((ln for ln in text.splitlines() if "Critical error" in ln or "SIG" in ln), "see the log"))
    keep = [ln for ln in text.splitlines() if "[Lift]" in ln]
    print("\n".join(ln.split("LogASTRA: ", 1)[-1] for ln in keep))
    # the engine's own exit code also counts the assets of the other modules that a checkout without its LFS files cannot load: the bench's own verdict decides
    verdict = [ln for ln in keep if " checks, " in ln and "failed" in ln]
    failed = int(verdict[-1].split(" checks, ")[1].split(" ")[0]) if verdict else -1
    print(f"engine exit {p.returncode}; the bench: {'no verdict (it did not finish)' if failed < 0 else f'{failed} failed'} (log: {out})")
    return 0 if failed == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fixture").set_defaults(fn=cmd_fixture)
    c = sub.add_parser("check")
    c.add_argument("plan", nargs="?")
    c.set_defaults(fn=cmd_check)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all")
    r.add_argument("--plan")
    r.add_argument("--seed", type=int)
    r.add_argument("--riders", type=int)
    r.add_argument("--trace", action="store_true", help="every event of the cars in the rush-hour simulation")
    r.set_defaults(fn=cmd_run)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
