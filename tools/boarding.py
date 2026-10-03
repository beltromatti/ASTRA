#!/usr/bin/env python3
"""ABBORDAGGI, fighting inside the ASN Aquila (Source/ASTRA/AstraBoard*.cpp, docs/ABBORDAGGI.md): the headless bench.

  tools/boarding.py run [--scenario all|map|rules|duel|squad|flank|board|orders|fps|plans|attack] [--seed 1] [--seeds 20] [--boarders 10] [--set "MandateSkill=0.8,HoldS=60"]
                                       the commandlet AstraBoardSim: the plan as the soldiers see it (portals, corners, lines of sight, routes), duels and
                                       squad fights in a corridor (who wins, how fast, with corners and without, with the flank and without), and whole
                                       boardings of the real ship (a Mandate boarding party through a breach, the marines on watch and the reaction
                                       team: who holds, at what cost, how long); checks the invariants and prints the verdict.
                                       --scenario plans (on request): the plan of every class (data/ship/plans, else the stopgap's): it loads, every dock has a way to the bridge, the
                                       engineering hall and the commander's suite; --scenario attack [--class acheron]: the marines go aboard a Mandate ship by two Kestrels (24 men)
                                       and the same plan with the roles turned (who wins, how fast, at what cost)
                                       --scenario fps (on request, no plan needed): the Captain's arms on the weapons against the mannequin's own
                                       animations (the sight on its place, the hands on the grips, what the picture holds at 16:9 and 16:10);
                                       --fpsposes FILE writes the engine's poses for the offline preview
  tools/boarding.py craft [--setup out|shield|pd|pd2|cap|all] [--seeds 8]
                                       the assault craft in the battle (the war bench, AstraWarSim, no window): our Kestrels from a ship to a hulk, a shield that holds them off the hull, the
                                       Mandate's skiffs through the point defence of a ship whose shield is down (how many dock, in how long), and the same with fighters on cap;
                                       the events are the craft's own ([Boarding] lines of the log)
  tools/boarding.py report Saved/Boarding/run.json   the record of a run

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi -unattended -nopause: it
never opens a window or touches the GPU, so it can run while the game or the editor is open (if the engine crashes, its crash reporter is closed by the script).
It uses no mind and spends nothing (no AI calls).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("/Users/Shared/Epic Games/UE_5.8" if sys.platform == "darwin" else "C:/Program Files/Epic Games/UE_5.8")
ENGINE = _UE / ("Engine/Binaries/Mac/UnrealEditor-Cmd" if sys.platform == "darwin" else "Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
OUT = ROOT / "Saved" / "Boarding"


def cmd_run(a: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out = (ROOT / a.out).resolve()
    log = OUT / "last_run.log"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraBoardSim", f"-scenario={a.scenario}", f"-seed={a.seed}", f"-seeds={a.seeds}", f"-boarders={a.boarders}",
            f"-out={out}", "-nullrhi", "-unattended", "-nopause", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    if a.set:
        args.append(f"-set={a.set}")
    if a.trace:
        args.append("-trace")
    if a.klass:
        args.append(f"-class={a.klass}")
    if a.fpsset:
        args.append(f"-fpsset={a.fpsset}")
    if a.fpsposes:
        args.append(f"-fpsposes={(ROOT / a.fpsposes).resolve()}")
    if a.setup >= 0:
        args.append(f"-setup={a.setup}")
    t0 = time.time()
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f"   the boarding bench did not finish in {a.timeout} s: killed (log {log})")
    # a crashed engine leaves its crash reporter running (a window spinning at 100% of a core): the ones of this run's process are closed here
    if sys.platform != "win32":
        subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    else:
        subprocess.run(["taskkill", "/F", "/IM", "CrashReportClient.exe"], check=False, capture_output=True)
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[Board]" in l]
    for l in lines[-200:]:
        print(l[l.find("[Board]"):])
    print(f"exit {p.returncode} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


# ---------------------------------------------------------------------------------------------------------------- the craft in the battle
_SPAWN_A = "astra.war.spawn praetorian astra -3 0 0 0 id=A1 name=Carrier static hold passive"
_SPAWN_M = "astra.war.spawn acheron mandate 3 0 0 90 id=M1 name=Hulk static hold passive"
_SPAWN_MS = "astra.war.spawn acheron mandate -3 0 0 0 id=M1 name=Raider static hold passive"
_SPAWN_AT = "astra.war.spawn praetorian astra 3 0 0 90 id=A1 name=Picket static hold passive"
CRAFT_SETUPS = {
    # our Kestrels from a Praetorian to an Acheron that has lost its power: they fly across, dock, and after a while let go and come home
    "out": dict(doc="two Kestrels from the Praetorian to a hulk: launched, docked at the port hatches, let go, home", seconds=330,
                exec=f"astra.war.sandbox;{_SPAWN_A};{_SPAWN_M}",
                at="2=astra.board.disable M1|3=astra.board.craft A1 M1 2 port|140=astra.board.depart 9000", expect=dict(launched=2, docked=2, destroyed=0, recovered=2)),
    # the same target with her shields up (and no point defence): the craft cannot dock through them, wait off the hull, turn back and come home
    "shield": dict(doc="the target's shield holds: the craft wait, turn back, come home (no point defence on her)", seconds=240,
                   exec=f"astra.war.sandbox;{_SPAWN_A};{_SPAWN_M}",
                   at="2=astra.board.pd M1 0|3=astra.board.craft A1 M1 2 port", expect=dict(launched=2, docked=0, aborted=2, recovered=2)),
    # four of the Mandate's skiffs at a Praetorian whose shield is down: her four point-defence channels shoot them on the way in
    "pd": dict(doc="four skiffs from an Acheron at a Praetorian with her shields down and her point defence working: how many dock", seconds=200,
               exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
               at="2=astra.board.strip A1|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
    "pd2": dict(doc="the same with two channels (a destroyer's)", seconds=200,
                exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
                at="2=astra.board.strip A1|2=astra.board.pd A1 2|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
    "cap": dict(doc="the same four skiffs against a Praetorian whose Falcons fly cover (a flight of fighters on cap)", seconds=200,
                exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
                at="2=astra.board.strip A1|2=astra.war.wing A1 fighter 4 cap|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
}


def _craft_run(a, name: str, setup: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"craft_{name}.log"
    out = OUT / f"craft_{name}.json"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={setup['seconds']}", "-step=0.1", "-every=5", f"-out={out}", f"-seed={a.seed}", f"-seeds={a.seeds}",
            f"-exec={setup['exec']}", f"-at={setup['at']}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    if sys.platform != "win32":
        subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    runs, cur = [], None
    for l in log.read_text(errors="replace").splitlines():
        if "[WarSim]" in l and "seed " in l and "battle in" in l:
            if cur is not None:
                runs.append(cur)
            cur = None
            continue
        if "[Boarding]" not in l:
            continue
        s = l[l.find("[Boarding]") + 10:].strip()
        if cur is None:
            cur = []
        cur.append(s)
    if cur:
        runs.append(cur)
    return {"log": log, "runs": runs, "code": p.returncode}


def _count(lines: list[str], kind: str) -> int:
    return sum(1 for l in lines if len(l.split()) > 1 and l.split()[1] == kind)


def cmd_craft(a: argparse.Namespace) -> int:
    names = list(CRAFT_SETUPS) if a.setup == "all" else [a.setup]
    bad = 0
    for name in names:
        setup = CRAFT_SETUPS[name]
        r = _craft_run(a, name, setup)
        print(f"== {name}: {setup['doc']}  (log {r['log']})")
        ev = ("launched", "docked", "destroyed", "aborted", "departed", "recovered", "lost")
        tot = {k: 0 for k in ev}
        times = []
        for lines in r["runs"] or [[]]:
            for k in ev:
                tot[k] += _count(lines, k)
            t0 = next((float(l.split()[0]) for l in lines if len(l.split()) > 1 and l.split()[1] == "launched"), None)
            for l in lines:
                w = l.split()
                if len(w) > 1 and w[1] == "docked" and t0 is not None:
                    times.append(float(w[0]) - t0)
        n = max(1, len(r["runs"]))
        print("   " + ", ".join(f"{k} {tot[k]}" for k in ev) + f"  ({n} run{'s' if n > 1 else ''})" + (f"; docked after {min(times):.0f}-{max(times):.0f} s (mean {sum(times) / len(times):.0f})" if times else ""))
        if a.trace and r["runs"]:
            for l in r["runs"][0]:
                print("     " + l)
        for k, v in setup["expect"].items():
            want = v * n
            ok = tot[k] == want
            print(f"   {'ok  ' if ok else 'FAIL'} {k}: {tot[k]} (expected {want})")
            bad += 0 if ok else 1
        if name.startswith("pd") or name == "cap":
            launched = max(1, tot["launched"])
            print(f"   {tot['docked']} of {tot['launched']} skiffs docked ({100.0 * tot['docked'] / launched:.0f}%), {tot['destroyed']} destroyed")
    print("CRAFT VERDICT:", "PASS" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


def cmd_report(a: argparse.Namespace) -> int:
    d = json.loads(Path(a.path).read_bytes().decode("utf-8-sig"))
    print(json.dumps(d, indent=1)[:12000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | map | rules | duel | squad | flank | board | orders (the marines' orders, on request only) | fps (the Captain's arms, on request only) | plans | attack (other ships' plans and the marines aboard one, on request only)")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--seeds", type=int, default=20, help="how many fights of each kind (seeds seed .. seed+seeds-1)")
    r.add_argument("--boarders", type=int, default=0, help="board: the size of the boarding party of the first setup (default 10, one skiff)")
    r.add_argument("--set", default="", help='tuning, "MandateSkill=0.8,HoldS=60,bFlank=0"')
    r.add_argument("--setup", type=int, default=-1, help="board: run only this setup (0..5)")
    r.add_argument("--trace", action="store_true", help="print the fights' events and a line a squad every five seconds (use with --seeds 1)")
    r.add_argument("--out", default="Saved/Boarding/run.json")
    r.add_argument("--class", dest="klass", default="", help="plans/attack: the ship's class (acheron, styx, lethe, praetorian, vigilant)")
    r.add_argument("--fpsset", default="", help="fps: try other places and anchors without touching the table, \"rifle.hip=84,17,-10;rifle.hipturn=-3,-13,0;rifle.shoulder_l=62,-20,-42\" (keys: rifle./pistol. hip hipturn ads low lowturn gripl fov shoulder_r shoulder_l; pole_r pole_l for both)")
    r.add_argument("--fpsposes", default="", help="fps: write the engine's poses (idle, draw, reload, dry fire) to this JSON file, for the offline preview")
    r.add_argument("--timeout", type=int, default=1500)
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("craft")
    c.add_argument("--setup", default="all", choices=list(CRAFT_SETUPS) + ["all"])
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--seeds", type=int, default=6)
    c.add_argument("--trace", action="store_true", help="print the first run's events")
    c.add_argument("--timeout", type=int, default=900)
    c.set_defaults(fn=cmd_craft)
    p = sub.add_parser("report")
    p.add_argument("path", nargs="?", default="Saved/Boarding/run.json")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
