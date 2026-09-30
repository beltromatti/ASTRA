#!/usr/bin/env python3
"""VITA, the life aboard the ASN Aquila (Source/ASTRA/AstraLife*.cpp, data/ship/aquila_life.json): the tools around it.

  tools/life.py check                  does the life file resolve on the ship's plan? rooms and slots of every department's duty and
                                       battle stations, homes, the tables of the day (no engine needed)
  tools/life.py bake                   writes into the life file what the plan does not list: the Crew Berthing's 84 racks
                                       (data/ship/aquila_berths.json) and the Mess Hall's extra seats (aquila_mess.json)
  tools/life.py stage                  copies the life file next to the plan for the packaged game (Content/ASTRA/Data)
  tools/life.py run [--hours 24] ...   the headless day (commandlet AstraLifeSim): a day of ship time, an alarm, three incidents, casualties;
                                       checks the invariants and prints the verdict. Needs the editor target built for this checkout
  tools/life.py report Saved/Life/run.json   the record of a run

`run` uses -nullrhi: it never opens a window or touches the GPU, so it can run while the game or the editor is open.
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ship"
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")

# the roster's departments and their sizes (Source/ASTRA/AstraCrewRoster.cpp)
ROSTER = {"command staff": 14, "communications": 10, "sensors": 12, "damage control": 40, "stewards and galley": 28, "flight deck": 96,
          "Air Group pilots": 60, "medbay": 18, "weapons": 76, "engineering": 118, "logistics": 8, "marines": 80}


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


# ------------------------------------------------------------------------------------------------------------------ check
def _match(c: dict, sel: dict) -> bool:
    if c["kind"] not in sel["kinds"]:
        return False
    if "dept" in sel and c.get("dept") != sel["dept"]:
        return False
    if "deck" in sel and c["deck"] not in sel["deck"]:
        return False
    return True


def _walled(c: dict, doors: dict) -> bool:
    ds = [doors[i] for i in c.get("doors", []) if i in doors]
    return bool(ds) and all(d.get("locked") for d in ds)


def cmd_check(_: argparse.Namespace) -> int:
    plan, life = load("aquila_plan.json"), load("aquila_life.json")
    comps = plan["compartments"]
    doors = {d["id"]: d for d in plan["doors"]}
    bad = 0

    def slots(c: dict) -> int:
        return c.get("crew_slots") or c.get("capacity") or 1

    print(f"{len(comps)} rooms; {sum(1 for c in comps if _walled(c, doors))} walled off (every door locked)")
    missing = [d for d in life["departments"] if d not in ROSTER] + [d for d in ROSTER if d not in life["departments"]]
    if missing:
        print("departments that do not match the roster:", missing)
        bad += 1
    print(f"{'department':22} {'list':6} {'per watch':>9} {'rooms':>6} {'slots':>6}  kinds")
    for dept, spec in life["departments"].items():
        per_watch = ROSTER.get(dept, 0) / len(life["watches"])
        for what in ("duty", "battle"):
            tot, rooms = collections.Counter(), 0
            for sel in spec[what]:
                for c in comps:
                    if _match(c, sel) and not _walled(c, doors):
                        tot[sel["kinds"][0]] += slots(c)
                        rooms += 1
            dead = [sel["kinds"] for sel in spec[what] if not any(_match(c, sel) and not _walled(c, doors) for c in comps)]
            print(f"{dept:22} {what:6} {per_watch:9.1f} {rooms:6d} {sum(tot.values()):6d}  {dict(tot)}" + (f"   NO ROOM FOR {dead}" if dead else ""))
            bad += 1 if dead else 0
    for cls, sels in life["homes"].items():
        if cls == "note":
            continue
        n = sum((84 if c["kind"] == "berthing" else slots(c)) for sel in sels for c in comps if _match(c, sel) and not _walled(c, doors))
        need = sum(ROSTER[d] for d, s in life["departments"].items() if s["class"] == cls)
        print(f"home {cls:8} bunks {n:4d} for {need:3d} people (shared by up to two watches: {2 * n})" + ("  NOT ENOUGH" if 2 * n < need else ""))
        bad += 1 if 2 * n < need else 0
    for lz in life["leisure"]["kinds"]:
        n = sum(1 for c in comps if c["kind"] in lz["kinds"] and not _walled(c, doors))
        print(f"leisure {lz['id']:12} {n:3d} rooms" + ("" if n or lz["kinds"] == ["__home"] else "  NONE"))
    print("OK" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


# ------------------------------------------------------------------------------------------------------------------ bake
def cmd_bake(_: argparse.Namespace) -> int:
    life = load("aquila_life.json")
    berths, mess = load("aquila_berths.json"), load("aquila_mess.json")
    # --- the Crew Berthing's racks: the same layout as tools/ue_scripts/build_berths.py (seven groups of two stacks of three racks a side)
    ox, oy, oz = berths["world_origin"]
    st = berths["stacks"]
    rw, rl, yf, lw = st["rack_width"], st["rack_length"], st["y_foot"], st["locker_width"]
    levels = st["rack_heights"]
    kept = {(s["group"], s["stack"], s["side"], s["level"]): f"sleeper{k + 1}" for k, s in enumerate(berths["sleepers"])}
    racks = []
    for g in range(st["groups"]):
        xg = st["x_start"] - g * (2 * rw + lw)
        for stack in (0, 1):
            x = xg - rw / 2 - stack * rw
            for side in (1, -1):
                for level in range(3):
                    r = {"id": f"berths.rack{len(racks) + 1}", "x": round(ox + x, 3), "y": round(oy + side * (yf + rl * 0.52), 3), "z": round(oz, 3),
                         "yaw": 90.0 * side, "height_cm": round((levels[level] + 0.2) * 100.0, 1)}
                    key = (g, stack, side, level)
                    if key in kept:
                        r["external"] = kept[key]              # the actor the level already has there (a sleeper of the Red watch)
                    racks.append(r)
    # --- the Mess Hall's seats beyond the twelve the level keeps: three a side along every table, clear of the diners already there
    mx, my, mz = mess["world_origin"]
    t = mess["tables"]
    taken = {(d["table"][0], d["table"][1], d["side"]): [] for d in mess["diners"]}
    for d in mess["diners"]:
        taken[(d["table"][0], d["table"][1], d["side"])].append(d["dx"])
    seats = []
    for i, tx in enumerate(t["x_centres"]):
        for j, ty in enumerate(t["y_centres"]):
            for side in (-1, 1):
                for dx in (-2.3, 0.0, 2.3):
                    if any(abs(dx - o) < 0.9 for o in taken.get((i, j, side), [])):
                        continue
                    seats.append({"id": f"mess.seat{len(seats) + 1}", "x": round(mx + tx + dx, 3), "y": round(my + ty + side * t["bench_offset"], 3),
                                  "z": round(mz, 3), "yaw": 90.0 if side < 0 else -90.0, "height_cm": 52.0})
    life.setdefault("extras", {})
    life["extras"]["racks"] = racks
    life["extras"]["mess_seats"] = seats
    life["extras"]["note"] = "baked by tools/life.py bake from aquila_berths.json and aquila_mess.json: the berthing's 84 racks (a rack the level keeps a sleeper on has `external`) and the Mess Hall's seats beyond the twelve the plan lists"
    (DATA / "aquila_life.json").write_text(json.dumps(life, indent=2) + "\n")
    print(f"baked {len(racks)} racks ({len(kept)} kept by the level's sleepers) and {len(seats)} Mess seats into data/ship/aquila_life.json")
    return 0


def cmd_stage(_: argparse.Namespace) -> int:
    dst = ROOT / "Content" / "ASTRA" / "Data"
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DATA / "aquila_life.json", dst / "aquila_life.json")
    print(f"staged {dst / 'aquila_life.json'} (the game reads Content/ASTRA/Data first, then data/ship)")
    return 0


# ------------------------------------------------------------------------------------------------------------------ run
def cmd_run(a: argparse.Namespace) -> int:
    out = (ROOT / a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    log = ROOT / "Saved" / "Life" / "last_run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraLifeSim", f"-hours={a.hours}", f"-hour={a.hour}", f"-seed={a.seed}", f"-step={a.step}",
            f"-out={out}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    if a.scenario:
        args.append(f"-scenario={a.scenario}")
    t0 = time.time()
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f"   the life bench did not finish in {a.timeout} s: killed (log {log})")
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[Life]" in l]
    for l in lines[-80:]:
        print(l[l.find("[Life]"):])
    print(f"exit {p.returncode} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


def cmd_report(a: argparse.Namespace) -> int:
    d = json.loads(Path(a.path).read_bytes().decode("utf-8-sig"))
    print(json.dumps(d.get("summary", d), indent=2)[:6000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("bake").set_defaults(fn=cmd_bake)
    sub.add_parser("stage").set_defaults(fn=cmd_stage)
    r = sub.add_parser("run")
    r.add_argument("--hours", type=float, default=24.0, help="ship hours to simulate")
    r.add_argument("--hour", type=float, default=0.0, help="the hour the run starts at")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--step", type=float, default=0.25, help="game seconds per tick")
    r.add_argument("--scenario", default="day", help="day | quiet")
    r.add_argument("--out", default="Saved/Life/run.json")
    r.add_argument("--timeout", type=int, default=900)
    r.set_defaults(fn=cmd_run)
    rp = sub.add_parser("report")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
