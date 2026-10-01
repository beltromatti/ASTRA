#!/usr/bin/env python3
"""TELETRASPORTO, the lattice transport of the ASN Aquila (Source/ASTRA/AstraTransport*.cpp, docs/TELETRASPORTO.md): the bench and the staging.

  tools/transport.py run [--scenario all|rules|world] [--seed 1] [--out Saved/Transport/run.json] [--verbose]
                                       the commandlet AstraTransport: the rules of the beam on scripted cases (the shields' faces at both ends, range, jamming
                                       along the line, the ship's motion, a Gate's field, the room's power and hazards, the lock's life, the arrival's rolls) and
                                       the whole subsystem in a headless world on the real plan and the real battle; prints each check and the verdict
  tools/transport.py check             does data/ship/aquila_transport.json still describe the room the plan and the kit build? (no engine: Python only)
  tools/transport.py stage             copies data/ship/aquila_transport.json to Content/ASTRA/Data (the game reads that copy first; `tools/life.py stage` does
                                       the same for the plan and the life tables)

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi: it never opens a window
or touches the GPU, so it can run while the game or the editor is open (one engine process of ~1.5 GB).
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
OUT = ROOT / "Saved" / "Transport"
DATA = ROOT / "data" / "ship" / "aquila_transport.json"
PLAN = ROOT / "data" / "ship" / "aquila_plan.json"


def cmd_run(a: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out = (ROOT / a.out).resolve()
    log = OUT / "last_run.log"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraTransport", f"-scenario={a.scenario}", f"-seed={a.seed}", f"-out={out}",
            "-nullrhi", "-unattended", "-nosound", "-nopause", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    t0 = time.time()
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        while p.poll() is None:
            time.sleep(0.5)
            try:
                with open(log, "rb") as r:
                    r.seek(max(0, log.stat().st_size - 40000))
                    tail = r.read().decode(errors="replace")
            except OSError:
                tail = ""
            crashed = "Critical error" in tail or "Assertion failed" in tail
            if crashed or time.time() - t0 > a.timeout:
                time.sleep(2.0 if crashed else 0.0)
                p.kill()
                p.wait()
                print(f"   the transport bench {'crashed' if crashed else 'did not finish in time'}: killed (log {log})")
                break
        rc = p.returncode
    subprocess.run(["pkill", "-f", "CrashReportClient"], check=False)           # (a crash leaves its reporter behind)
    text = log.read_text(errors="replace").splitlines()
    lines = [l[l.find("[Transport]"):] for l in text if "[Transport]" in l]
    for l in lines[-(600 if a.verbose else 200):]:
        print(l)
    print(f"exit {rc} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


def cmd_stage(_: argparse.Namespace) -> int:
    dst = ROOT / "Content" / "ASTRA" / "Data"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / DATA.name).write_bytes(DATA.read_bytes())
    print(f"{DATA.relative_to(ROOT)} -> {(dst / DATA.name).relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | rules | world")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", default="Saved/Transport/run.json")
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("stage").set_defaults(fn=cmd_stage)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
