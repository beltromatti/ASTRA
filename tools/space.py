#!/usr/bin/env python3
"""Run a system's living space headless and read what it did (Source/ASTRA/AstraSpaceLifeSimCommandlet.*, docs/SPAZIO.md): the civilian traffic's routes, berths, the
Gate's queue, the reactions to a war and what a tick costs, with the checks of the invariants. For the lead and for the module's support agents (in their own worktree,
with their own build).

  tools/space.py run [--seconds 3600] [--system Aurelia] [--seed 1] [--every 10] [--at "600=astra.space.alert 25|900=astra.space.alert 0"] [--exec "..."]
                     [--selftest] [--out Saved/Space/run.json]        the traffic for that long; --selftest ends with SPACE_SELFTEST_OK or the failures
  tools/space.py report Saved/Space/run.json                         the layout, the flow, the queue, the reactions, the cost
  tools/space.py test                                                the module's own tests: peace for an hour, a hostile on the lanes, the Gate closed, a busy system, determinism
  tools/space.py sync                                                data/space/*.json -> Content/ASTRA/Data/space (the copy the game stages), after a change in the data
  tools/space.py meshes <manifest.json>                              art/export/space_v3/manifest.json -> data/space/meshes.json (lamps, bells, berths of each mesh), then sync

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi: it never opens a window or touches the
GPU, so it can run while the game or the editor is open. One engine process at a time (each is ~1.5 GB and the machine is shared).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")
SPACE = ROOT / "Saved" / "Space"
DATA = ROOT / "data" / "space"
STAGED = ROOT / "Content" / "ASTRA" / "Data" / "space"


def build_args(a: argparse.Namespace, out: Path) -> list[str]:
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraSpaceSim", f"-seconds={a.seconds}", f"-step={a.step}", f"-every={a.every}", f"-out={out}", f"-seed={a.seed}",
            f"-system={a.system}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    if a.exec:
        args.append(f"-exec={a.exec}")
    if a.at:
        args.append(f"-at={a.at}")
    if a.selftest:
        args.append("-selftest")
    if getattr(a, "free", False):
        args.append("-free")
    if getattr(a, "verbose", False):
        args.append("-LogCmds=LogASTRA Verbose")
    return args


def run_once(a: argparse.Namespace, out: Path, log: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    limit = 240.0 + a.seconds / 8.0
    with open(log, "w") as f:
        p = subprocess.Popen(build_args(a, out), stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
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
            if crashed or time.time() - t0 > limit:
                time.sleep(2.0 if crashed else 0.0)
                p.kill()
                p.wait()
                print(f"   the space bench {'crashed' if crashed else 'did not finish in time'}: killed (log {log})")
                if crashed:
                    lines = log.read_text(errors="replace").splitlines()
                    for i, l in enumerate(lines):
                        if "Critical error" in l or "Assertion failed" in l:
                            print("   " + "\n   ".join(x.strip() for x in lines[i:i + 8]))
                            break
                break
        return p.returncode


def run_wrecktest(log: Path) -> bool:
    """The records of what the war leaves, on their own (no world; AstraWrecksTest.cpp): a second or two of engine start and the checks."""
    log.parent.mkdir(parents=True, exist_ok=True)
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraSpaceSim", "-wrecktest", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    with open(log, "w") as f:
        try:
            subprocess.run(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT), timeout=240)
        except subprocess.TimeoutExpired:
            print("   the wreck tests did not finish in time")
            return False
    text = log.read_text(errors="replace")
    fails = 0
    for l in text.splitlines():
        if "[WreckTest]" in l or "WRECKS_SELFTEST" in l:
            if "FAIL" in l:
                fails += 1
                if fails > 12:
                    continue                                    # (a broken rule fails for every site: the first dozen say it)
            print("   " + l.split("]", 1)[-1].strip() if "LogASTRA" in l else "   " + l)
    return "WRECKS_SELFTEST_OK" in text


def cmd_wrecktest(a: argparse.Namespace) -> int:
    return 0 if run_wrecktest(SPACE / "wrecktest.log") else 1


def cmd_run(a: argparse.Namespace) -> int:
    out = (ROOT / a.out).resolve()
    log = SPACE / "last_run.log"
    t0 = time.time()
    rc = run_once(a, out, log)
    lines = log.read_text(errors="replace").splitlines()
    for l in lines:
        if "[SpaceSim]" in l and ("FAIL" in l or "seconds of" in l or " s of " in l) or "SPACE_SELFTEST" in l or "[Space]" in l and "data from" in l:
            print(l.split("]", 1)[-1].strip() if "LogASTRA" in l else l)
    print(f"   {time.time() - t0:.0f} s wall, exit {rc} (log {log})")
    if out.exists() and not a.quiet:
        report(out)
    return rc


def load(path: str) -> dict:
    return json.loads(Path(path).read_text())


def report(path: Path) -> None:
    d = load(str(path))
    fin = d["final"]
    print(f"-- {d['system']}: {d['battle_seconds']:.0f} s in {d['wall_seconds']:.1f} s of wall (x{d['battle_seconds'] / max(d['wall_seconds'], 1e-3):.0f}), seed {d['seed']}")
    lay = d["layout"]
    print("-- places")
    for n in lay["nodes"]:
        x, y, z = n["km"]
        rng = math.sqrt(x * x + y * y + z * z)
        print(f"   {n['id']:10s} {n['kind']:9s} {n['name']:24s} {rng:6.1f} km from the origin, {n['slots']} berths, {n['holds']} waiting points")
    print("-- lanes")
    for l in lay["lanes"]:
        print(f"   {l['id']:18s} {l['length_km']:6.1f} km, {l['buoys']} buoys")
    print(f"   rocks {lay['rocks']}")
    print("-- the flow")
    print(f"   vessels {fin['vessels']}: {fin['docked']} docked, {fin['in_flight']} under way, {fin['away']} beyond the Gate, queue at the Gate {fin['gate_queue']} (max {fin['max_gate_queue']:.0f})")
    print(f"   through the ring: {fin['gate_out']} out, {fin['gate_in']} in; berths: {fin['dockings']} dockings, {fin['departures']} departures; maydays {fin['maydays']}")
    frames = d["frames"]
    if frames:
        q = [f["gate_queue"] for f in frames]
        alert = [f["alert_level"] for f in frames]
        inflight = [f["in_flight"] for f in frames]
        print(f"   in flight: mean {statistics.mean(inflight):.1f} (min {min(inflight)}, max {max(inflight)}); gate queue mean {statistics.mean(q):.2f} max {max(q)}; alert frames {sum(1 for x in alert if x)} of {len(alert)}")
        if "near30" in frames[0]:
            n30, n60, n100 = ([f[k] for f in frames] for k in ("near30", "near60", "near100"))
            print(f"   to look at from the window: within 30 km mean {statistics.mean(n30):.1f} (max {max(n30)}), 60 km mean {statistics.mean(n60):.1f} (max {max(n60)}), 100 km mean {statistics.mean(n100):.1f} (max {max(n100)})")
    print("-- cost")
    print(f"   traffic {fin['traffic_ms_avg'] * 1000:.1f} us a tick (max {fin['traffic_ms_max']:.3f} ms); the whole of the living space {fin['space_ms_avg'] * 1000:.1f} us a tick (max {fin['space_ms_max']:.3f} ms); "
          f"lamps peak {fin['lamps_peak']}, hulls peak {fin['hulls_peak']}")
    if "world_tick" in d:
        w = d["world_tick"]
        print(f"   the whole world's tick: {w['ms_avg']:.3f} ms avg, p95 {w['ms_p95']:.3f}, max {w['ms_max']:.2f}")
    print(f"   invariants: {d['checks_run']} checks, {len(d['failures'])} failures; hulls through each other: max {d['overlap_max']}, mean {d['overlap_avg']:.2f}")
    for f in d["failures"][:10]:
        print(f"   FAIL {f['check']}: {f['detail']}")
    ev = d["events"]
    print(f"-- {len(ev)} events")
    for e in ev[:30]:
        print(f"   {e['t']:7.1f} {'REPORT ' if e['report'] else ''}{e['text'][:200]}")


def cmd_report(a: argparse.Namespace) -> int:
    report(Path(a.path))
    return 0


def selftest_ok(log: Path) -> bool:
    """The engine's exit code is no verdict here (a checkout without its imported content logs errors for the assets it cannot find): the bench says it itself."""
    try:
        return "SPACE_SELFTEST_OK" in log.read_text(errors="replace")
    except OSError:
        return False


def expect(name: str, ok: bool, detail: str, results: list[tuple[str, bool, str]]) -> None:
    results.append((name, ok, detail))
    print(f"   {'PASS' if ok else 'FAIL'} {name}: {detail}")


def cmd_test(a: argparse.Namespace) -> int:
    results: list[tuple[str, bool, str]] = []
    # peace: the traffic ignores the opening's war (the strike group at 170 s, the Lethe that wakes at 80); the war test below switches reactions on again
    quiet = "astra.space.reactions 0"
    base = argparse.Namespace(seconds=3600, step=0.1, every=10, seed=1, system="Aurelia", exec=quiet, at="", selftest=True, out="Saved/Space/test_peace.json", quiet=True)
    print("-- peace for an hour (Aurelia, seed 1)")
    rc = run_once(base, ROOT / base.out, SPACE / "test_peace.log")
    expect("selftest", selftest_ok(SPACE / "test_peace.log"), "the invariants held (SPACE_SELFTEST_OK)", results)
    if (ROOT / base.out).exists():
        d = load(base.out if Path(base.out).is_absolute() else str(ROOT / base.out))
        fin = d["final"]
        expect("vessels exist", fin["vessels"] >= 20, f"{fin['vessels']} vessels", results)
        expect("the Gate is used both ways", fin["gate_out"] >= 5 and fin["gate_in"] >= 5, f"{fin['gate_out']} out, {fin['gate_in']} in", results)
        expect("berths are used", fin["dockings"] >= 40 and fin["departures"] >= 40, f"{fin['dockings']} dockings, {fin['departures']} departures", results)
        expect("no alert in peace", fin["maydays"] == 0 and all(f["alert_level"] == 0 for f in d["frames"]), f"{fin['maydays']} maydays", results)
        expect("cheap", fin["traffic_ms_avg"] < 0.08 and fin["space_ms_avg"] < 0.15, f"traffic {fin['traffic_ms_avg'] * 1000:.0f} us, all {fin['space_ms_avg'] * 1000:.0f} us a tick", results)
        expect("hulls keep apart", d["overlap_avg"] < 0.2, f"{d['overlap_avg']:.2f} on average, max {d['overlap_max']}", results)
        flight = [f["in_flight"] for f in d["frames"]]
        expect("the lanes are busy", statistics.mean(flight) >= 8, f"{statistics.mean(flight):.1f} vessels under way on average", results)
        q = max(f["gate_queue"] for f in d["frames"])
        expect("the Gate does not jam", q <= 6, f"longest queue {q}", results)
    print("-- a hostile 9 km from the vessel nearest the Aquila (from 20 minutes to 30)")
    war = argparse.Namespace(**{**vars(base), "seconds": 2400, "exec": "astra.space.reactions 2", "at": "1200=astra.space.alert vessel|1800=astra.space.alert 0",
                                "out": "Saved/Space/test_war.json"})
    rc = run_once(war, ROOT / war.out, SPACE / "test_war.log")
    expect("selftest in war", selftest_ok(SPACE / "test_war.log"), "the invariants held in a war too", results)
    if (ROOT / war.out).exists():
        d = load(str(ROOT / war.out))
        alerted = [f for f in d["frames"] if 1200 <= f["t"] <= 1800 and f["alerted"] > 0]
        expect("vessels react", len(alerted) >= 3, f"{max((f['alerted'] for f in d['frames']), default=0)} alerted at the most", results)
        calls = [e for e in d["events"] if "distress call" in e["text"]]
        expect("someone calls for help", len(calls) >= 1, f"{len(calls)} distress calls", results)
        later = [f for f in d["frames"] if f["t"] >= 2300]
        expect("the traffic calms down again", bool(later) and all(f["alerted"] == 0 for f in later), f"alerted at the end: {later[-1]['alerted'] if later else '?'}", results)
        resumed = [e for e in d["events"] if "resuming its routes" in e["text"]]
        expect("the resumption is told", len(resumed) >= 1, f"{len(resumed)} reports", results)
    print("-- determinism (the same seed twice)")
    d1 = argparse.Namespace(**{**vars(base), "seconds": 900, "out": "Saved/Space/det_a.json"})
    d2 = argparse.Namespace(**{**vars(base), "seconds": 900, "out": "Saved/Space/det_b.json"})
    run_once(d1, ROOT / d1.out, SPACE / "det_a.log")
    run_once(d2, ROOT / d2.out, SPACE / "det_b.log")
    try:
        fa, fb = load(str(ROOT / d1.out))["frames"], load(str(ROOT / d2.out))["frames"]
        same = len(fa) == len(fb) and all(x["v"] == y["v"] and x["p"] == y["p"] for x, y in zip(fa, fb))
        expect("same seed, same traffic", same, f"{len(fa)} frames compared", results)
    except Exception as ex:  # noqa: BLE001
        expect("same seed, same traffic", False, str(ex), results)
    bad = [r for r in results if not r[1]]
    print(f"== {len(results) - len(bad)} of {len(results)} passed")
    return 1 if bad else 0


def cmd_sync(a: argparse.Namespace) -> int:
    STAGED.mkdir(parents=True, exist_ok=True)
    for f in sorted(DATA.glob("*.json")):
        shutil.copy2(f, STAGED / f.name)
        print(f"   {f.relative_to(ROOT)} -> {(STAGED / f.name).relative_to(ROOT)}")
    return 0


def cmd_meshes(a: argparse.Namespace) -> int:
    """The generator's manifest -> the game's table of each mesh's lamps, drive bells and berths (the game reads it at run time: no mesh needs to be opened)."""
    m = json.loads(Path(a.manifest).read_text())
    out = {"version": 1, "meshes": {}}
    for name, e in m["meshes"].items():
        keep = {k: e[k] for k in ("min", "max", "length", "lamps", "bells", "docks", "holds", "parts", "flare", "flare_len") if k in e}
        if keep:
            out["meshes"][name] = keep
    (DATA / "meshes.json").write_text(json.dumps(out, separators=(",", ":")))
    print(f"   {len(out['meshes'])} meshes -> data/space/meshes.json")
    return cmd_sync(a)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--seconds", type=float, default=3600)
    r.add_argument("--step", type=float, default=0.1)
    r.add_argument("--every", type=float, default=10)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--system", default="Aurelia")
    r.add_argument("--exec", default="")
    r.add_argument("--at", default="")
    r.add_argument("--selftest", action="store_true")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--verbose", action="store_true")
    r.add_argument("--free", action="store_true", help="the Aquila keeps her default course (by default she is parked where she comes in)")
    r.add_argument("--out", default="Saved/Space/run.json")
    r.set_defaults(fn=cmd_run)
    rp = sub.add_parser("report")
    rp.add_argument("path")
    rp.set_defaults(fn=cmd_report)
    t = sub.add_parser("test")
    t.set_defaults(fn=cmd_test)
    wt = sub.add_parser("wrecktest")
    wt.set_defaults(fn=cmd_wrecktest)
    s = sub.add_parser("sync")
    s.set_defaults(fn=cmd_sync)
    m = sub.add_parser("meshes")
    m.add_argument("manifest")
    m.set_defaults(fn=cmd_meshes)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
