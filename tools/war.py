#!/usr/bin/env python3
"""Run the war headless and read what happened (Source/ASTRA/AstraWarSimCommandlet.*): no rendering, no GPU, faster than
real time. For the lead and the war module's support agents (in their own worktree, with their own build).

  tools/war.py run [--seconds 900] [--jump 170] [--exec "astra.battle.spawn styx 12 30"] [--out Saved/War/run.json]
  tools/war.py report Saved/War/run.json      the story of the battle: arrivals, kills, damage, withdrawals, the outcome
  tools/war.py ship Saved/War/run.json T-21   one ship through the battle (position, hull, shields, mode, target)

`run` needs the editor target built for this checkout (tools/ricompila.sh --no-launch, or Build.sh ASTRAEditor) and uses
-nullrhi: it never opens a window or touches the GPU, so it can run while the game or the editor is open.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")


def cmd_run(a: argparse.Namespace) -> None:
    out = (ROOT / a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={a.seconds}", f"-step={a.step}",
            f"-every={a.every}", f"-out={out}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout",
            "-FullStdOutLogOutput"]
    if a.jump >= 0:
        args.append(f"-jump={a.jump}")
    args.append(f"-seed={a.seed}")
    if a.exec:
        args.append(f'-exec={a.exec}')
    t0 = time.time()
    log = ROOT / "Saved" / "War" / "last_run.log"
    with open(log, "w") as f:
        # a crash can leave the engine hanging in its crash handler: never wait for ever
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=max(180.0, a.seconds / 5.0))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f"   the war bench did not finish in time: killed (log {log})")
        r = p
    if getattr(a, "quiet", False):
        if r.returncode != 0:
            print(f"   exit {r.returncode} (log {log})")
        return
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[WarSim]" in l or "Error" in l]
    for l in lines[-12:]:
        print(l[l.find("[WarSim]"):] if "[WarSim]" in l else l)
    print(f"exit {r.returncode} in {time.time() - t0:.0f} s; log {log}")
    if out.exists():
        report(out)


def outcome(path: Path) -> dict:
    d = load(str(path))
    fin = d["final"]["ships"]
    o = {}
    for side in ("astra", "mandate"):
        caps = [s for s in fin if s["side"] == side and not s["craft"]]
        craft = [s for s in fin if s["side"] == side and s["craft"]]
        o[side] = (sum(1 for s in caps if s["alive"]), len(caps), sum(1 for s in craft if s["alive"]), len(craft))
    aq = next((s for s in fin if s["c"] == "AQUILA"), None)
    o["aquila"] = f"{aq.get('hull', 0):.0f}%" if aq and aq["alive"] else "LOST"
    return o


def cmd_ab(a: argparse.Namespace) -> None:
    for name, ex in (("A", a.a), ("B", a.b)):
        print(f"== variant {name}: {ex or '(as is)'}")
        for seed in range(1, a.seeds + 1):
            out = ROOT / "Saved" / "War" / f"ab_{name}_{seed}.json"
            ns = argparse.Namespace(seconds=a.seconds, jump=a.jump, step=0.1, every=10, exec=ex, out=str(out.relative_to(ROOT)),
                                    seed=seed, quiet=True)
            cmd_run(ns)
            o = outcome(out)
            print(f"   seed {seed}: Aquila {o['aquila']:5}  ASTRA warships {o['astra'][0]}/{o['astra'][1]} craft {o['astra'][2]}/{o['astra'][3]}"
                  f"  ·  Mandate warships {o['mandate'][0]}/{o['mandate'][1]} craft {o['mandate'][2]}/{o['mandate'][3]}")


def load(path: str) -> dict:
    raw = Path(path).read_bytes()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return json.loads(raw.decode(enc))


def report(path: Path | str) -> None:
    d = load(str(path))
    print(f"\n== {path}: {d['battle_seconds']:.0f} s of battle in {d['wall_seconds']:.1f} s")
    first = {}
    for f in d["frames"]:
        for s in f["ships"]:
            first.setdefault(s["id"], (f["t"], s))
    deaths = []
    alive_prev = {}
    for f in d["frames"]:
        for s in f["ships"]:
            if alive_prev.get(s["id"], True) and not s["alive"]:
                deaths.append((f["t"], s))
            alive_prev[s["id"]] = s["alive"]
    print("-- arrivals (first seen in the record)")
    for sid, (t, s) in sorted(first.items(), key=lambda x: x[1][0]):
        if t > 0 and not s["craft"]:
            print(f"  {t:7.1f}  {s['c']:6} {s['name'][:28]:28} {s['side']}")
    print("-- losses")
    for t, s in deaths:
        print(f"  {t:7.1f}  {s['c']:6} {s['name'][:28]:28} {s['side']}{' (craft)' if s['craft'] else ''}")
    fin = d["final"]["ships"]
    for side in ("astra", "mandate", "neutral"):
        caps = [s for s in fin if s["side"] == side and not s["craft"]]
        craft = [s for s in fin if s["side"] == side and s["craft"]]
        alive = [s for s in caps if s["alive"]]
        print(f"-- {side}: warships {len(alive)}/{len(caps)} alive, craft {sum(1 for s in craft if s['alive'])}/{len(craft)}")
        for s in alive:
            print(f"     {s['c']:6} {s['name'][:24]:24} hull {s.get('hull', 0):3.0f}% shields {s.get('shield', 0):3.0f}%"
                  f" {'FLEEING' if s.get('fleeing') else ''}")
    reports = [e for e in d["events"] if e["report"]]
    print(f"-- {len(d['events'])} events, {len(reports)} reports; the last reports:")
    for e in reports[-8:]:
        print(f"  {e['t']:7.1f}  {e['text'][:150]}")


def cmd_report(a: argparse.Namespace) -> None:
    report(a.path)


def cmd_ship(a: argparse.Namespace) -> None:
    d = load(a.path)
    for f in d["frames"]:
        for s in f["ships"]:
            if s["c"].upper() == a.contact.upper() or s["name"].lower() == a.contact.lower():
                if not s["alive"]:
                    print(f"{f['t']:7.1f}  destroyed")
                    return
                km = s["km"]
                print(f"{f['t']:7.1f}  ({km[0]:7.1f},{km[1]:7.1f},{km[2]:6.1f}) km  {s['v']:5.0f} m/s  hull {s['hull']:3.0f}%"
                      f"  sh {s['shield']:3.0f}%  mode {s['mode']}  target {s['target']}  stance {s['stance']}"
                      f"{'  FLEEING' if s['fleeing'] else ''}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="war.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run")
    p.add_argument("--seconds", type=float, default=900)
    p.add_argument("--jump", type=float, default=-1)
    p.add_argument("--step", type=float, default=0.1)
    p.add_argument("--every", type=float, default=5)
    p.add_argument("--exec", default="")
    p.add_argument("--out", default="Saved/War/run.json")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("ab", help="compare: the same scenario over several seeds, with and without an --exec change")
    p.add_argument("--seconds", type=float, default=900)
    p.add_argument("--jump", type=float, default=160)
    p.add_argument("--seeds", type=int, default=4)
    p.add_argument("--a", default="", help="exec for variant A")
    p.add_argument("--b", default="", help="exec for variant B")
    p.set_defaults(fn=cmd_ab)
    p = sub.add_parser("report")
    p.add_argument("path")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("ship")
    p.add_argument("path")
    p.add_argument("contact")
    p.set_defaults(fn=cmd_ship)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
