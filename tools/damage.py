#!/usr/bin/env python3
"""DISTRUZIONE, the damage inside the ASN Aquila (Source/ASTRA/AstraDamage*.cpp, docs/DISTRUZIONE.md): the headless bench.

  tools/damage.py run [--scenario all|trace|air|fire|people|captain|survive] [--seed 1] [--seconds 600] [--set "astra.damage.hole=1.2,..."]
                                       the commandlet AstraDamageSim: hits scripted on the real plan and the real damage model (where blows go,
                                       the air that leaves and stops at the pressure bulkheads, fires that spread and burn out, teams that
                                       arrive, the people of VITA hurt where they stood, the Captain in a compartment that empties) and the whole
                                       Aquila under the strike group's fire; checks the invariants and prints the verdict
  tools/damage.py batch --seeds 8 [--scenario survive] [--set ...] [--tag t]
                                       N seeds of one scenario (two processes at a time): one line each and the mean
  tools/damage.py report Saved/Damage/run.json   the record of a run

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi: it never
opens a window or touches the GPU, so it can run while the game or the editor is open. At most two engine processes at once (each is ~1.5 GB).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_PROCESSES = 2
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("/Users/Shared/Epic Games/UE_5.8" if sys.platform == "darwin" else "C:/Program Files/Epic Games/UE_5.8")
ENGINE = _UE / ("Engine/Binaries/Mac/UnrealEditor-Cmd" if sys.platform == "darwin" else "Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
OUT = ROOT / "Saved" / "Damage"


def build_args(a: argparse.Namespace, seed: int, out: Path) -> list[str]:
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraDamageSim", f"-scenario={a.scenario}", f"-seed={seed}", f"-seconds={a.seconds}",
            f"-out={out}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    if a.set:
        args.append(f'-set={a.set}')
    return args


def run_once(a: argparse.Namespace, seed: int, out: Path, log: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as f:
        p = subprocess.Popen(build_args(a, seed, out), stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        t0 = time.time()
        while p.poll() is None:
            time.sleep(0.5)
            crashed = False
            try:
                with open(log, "rb") as r:
                    r.seek(max(0, log.stat().st_size - 40000))
                    tail = r.read().decode(errors="replace")
                crashed = "Critical error" in tail or "Assertion failed" in tail
            except OSError:
                pass
            if crashed or time.time() - t0 > a.timeout:
                time.sleep(2.0 if crashed else 0.0)
                p.kill()
                p.wait()
                print(f"   the damage bench {'crashed' if crashed else 'did not finish in time'}: killed (log {log})")
                if crashed:
                    lines = log.read_text(errors="replace").splitlines()
                    for i, l in enumerate(lines):
                        if "Critical error" in l or "Assertion failed" in l:
                            print("   " + "\n   ".join(x.strip() for x in lines[i:i + 10]))
                            break
                break
        return p.returncode


def cmd_run(a: argparse.Namespace) -> int:
    out = (ROOT / a.out).resolve()
    log = OUT / "last_run.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    rc = run_once(a, a.seed, out, log)
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[Damage]" in l and (a.verbose or not l.split("[Damage]", 1)[1].lstrip().startswith(tuple("0123456789")))]
    for l in lines[-(400 if a.verbose else 120):]:
        print(l[l.find("[Damage]"):])
    print(f"exit {rc} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


def cmd_batch(a: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    seeds = list(range(a.seed, a.seed + a.seeds))

    def one(s: int):
        out = OUT / f"{a.tag}_{s}.json"
        log = OUT / f"{a.tag}_{s}.log"
        run_once(a, s, out, log)
        return s, out

    rows = []
    with ThreadPoolExecutor(max_workers=min(MAX_PROCESSES, a.jobs)) as ex:
        for s, out in ex.map(one, seeds):
            if not out.exists():
                print(f"seed {s}: no record")
                continue
            d = json.loads(out.read_bytes().decode("utf-8-sig"))
            sv = d.get("survive")
            if sv:
                rows.append(sv)
                print(f"seed {s}: {json.dumps(sv)}")
            else:
                print(f"seed {s}: {d.get('verdict')}")
    if rows:
        for k in rows[0]:
            vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
            if vals:
                print(f"mean {k}: {statistics.mean(vals):.1f} (min {min(vals):.1f}, max {max(vals):.1f}, n {len(vals)})")
    return 0


def cmd_report(a: argparse.Namespace) -> int:
    d = json.loads(Path(a.path).read_bytes().decode("utf-8-sig"))
    print(json.dumps(d, indent=1)[:12000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | trace | air | fire | people | captain | survive")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--seconds", type=float, default=600.0, help="survive: battle seconds after the strike group's arrival")
    r.add_argument("--set", default="", help='console variables, "astra.damage.hole=1.2,astra.damage.fire=0.8"')
    r.add_argument("--out", default="Saved/Damage/run.json")
    r.add_argument("--timeout", type=int, default=1200)
    r.add_argument("--verbose", action="store_true", help="also print the report lines with their times")
    r.set_defaults(fn=cmd_run)
    b = sub.add_parser("batch")
    b.add_argument("--scenario", default="survive")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--seeds", type=int, default=6)
    b.add_argument("--seconds", type=float, default=600.0)
    b.add_argument("--set", default="")
    b.add_argument("--tag", default="batch")
    b.add_argument("--jobs", type=int, default=2)
    b.add_argument("--timeout", type=int, default=1200)
    b.set_defaults(fn=cmd_batch)
    rp = sub.add_parser("report")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
