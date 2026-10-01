#!/usr/bin/env python3
"""ABBORDAGGI, fighting inside the ASN Aquila (Source/ASTRA/AstraBoard*.cpp, docs/ABBORDAGGI.md): the headless bench.

  tools/boarding.py run [--scenario all|map|rules|duel|squad|flank|board] [--seed 1] [--seeds 20] [--boarders 10] [--set "MandateSkill=0.8,HoldS=60"]
                                       the commandlet AstraBoardSim: the plan as the soldiers see it (portals, corners, lines of sight, routes), duels and
                                       squad fights in a corridor (who wins, how fast, with corners and without, with the flank and without), and whole
                                       boardings of the real ship (a Mandate boarding party through a breach, the marines on watch and the reaction
                                       team: who holds, at what cost, how long); checks the invariants and prints the verdict
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
    subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[Board]" in l]
    for l in lines[-200:]:
        print(l[l.find("[Board]"):])
    print(f"exit {p.returncode} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


def cmd_report(a: argparse.Namespace) -> int:
    d = json.loads(Path(a.path).read_bytes().decode("utf-8-sig"))
    print(json.dumps(d, indent=1)[:12000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | map | rules | duel | squad | flank | board")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--seeds", type=int, default=20, help="how many fights of each kind (seeds seed .. seed+seeds-1)")
    r.add_argument("--boarders", type=int, default=0, help="board: the size of the boarding party of the first setup (default 10, one skiff)")
    r.add_argument("--set", default="", help='tuning, "MandateSkill=0.8,HoldS=60,bFlank=0"')
    r.add_argument("--setup", type=int, default=-1, help="board: run only this setup (0..5)")
    r.add_argument("--trace", action="store_true", help="print the fights' events and a line a squad every five seconds (use with --seeds 1)")
    r.add_argument("--out", default="Saved/Boarding/run.json")
    r.add_argument("--timeout", type=int, default=1500)
    r.set_defaults(fn=cmd_run)
    p = sub.add_parser("report")
    p.add_argument("path", nargs="?", default="Saved/Boarding/run.json")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
