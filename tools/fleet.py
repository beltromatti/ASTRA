#!/usr/bin/env python3
"""FLOTTA-VIVA's bench: the insides of the other ships (Source/ASTRA/AstraFleet*.cpp, docs/FLOTTA-VIVA.md), headless, through the war bench (tools/war.py: -nullrhi,
no window, no GPU, no AI calls: it spends nothing). Needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex).

  tools/fleet.py trace  [--class acheron] [--side mandate] [--faces bow,port,dorsal] [--damage 400] [--kind rail]
                                  a shot traced into a ship: where it entered, the rooms it crossed, who was in them, what burned and what was lost, face by face
  tools/fleet.py breaks [--class acheron] [--face bow] [--damage 150] [--blows 6] [--rounds 5] [--every 4] [--seconds 60] [--seeds 3]
                                  a ship pounded on one face until she breaks: where the structure gave way (the war's section that was gutted and the hull broke at) against
                                  the rooms the inside lost in each section: they must be the same place
  tools/fleet.py cost   [--scenario scale_30x150] [--seconds 120] [--seeds 1]
                                  what the insides cost for a big battle: ships with one, blows, ms per second of battle and per ship, the worst call; against the same battle without
  tools/fleet.py ab     [--scenarios sym_small,sym_medium,sym_two,asym_2to1] [--seeds 12]
                                  the war with the insides against the war without them (as before FLOTTA-VIVA): survivors, edge, losses of people, the cost
  tools/fleet.py plans  [--only acheron,styx]
                                  the class plans, regenerated from the hull probes and checked (art/blender/ship_class_plans.py --no-stage: nothing staged)
"""
from __future__ import annotations

import argparse
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import war  # noqa: E402  (the war bench: the runner and the readers of a record)

ROOT = war.ROOT
WAR = war.WAR
FACES = ("bow", "stern", "port", "starboard", "dorsal", "ventral")


def log_lines(log: Path, key: str) -> list[str]:
    out = []
    for ln in log.read_text(errors="replace").splitlines():
        if key in ln:
            out.append(ln[ln.find(key):])
    return out


def run_exec(cmds: list[str], seconds: float, seed: int, tag: str, step: float = 0.1, at: str = "") -> tuple[Path, Path]:
    ns = argparse.Namespace(seconds=seconds, jump=-1, step=step, every=5, scenario="", exec=";".join(cmds), seed=seed, nseeds=1, at=at)
    out, log = WAR / f"{tag}.json", WAR / f"{tag}.log"
    war.run_once(ns, out, log)
    return out, log


# ------------------------------------------------------------------------------------------------ a shot traced
def cmd_trace(a: argparse.Namespace) -> None:
    cmds = ["astra.war.sandbox", f"astra.war.spawn {a.cls} {a.side} 0 0 0 0 id=TGT static passive"]
    for f in a.faces.split(","):
        cmds.append(f"astra.war.fleet hit TGT {f} {a.damage} {a.kind}")
    cmds.append("astra.war.fleet info TGT")
    cmds.append("astra.war.fleet snapshot TGT")
    _, log = run_exec(cmds, 3.0, a.seed, "fleet_trace")
    lines = log_lines(log, "[Fleet]")
    print(f"== {a.cls} ({a.side}), a {a.kind} blow of {a.damage} on each of: {a.faces}")
    for ln in lines:
        if "the plan of the" in ln:
            continue
        # [Fleet] acheron TGT: a blow of 400 at the hull (port face, mid section, 101 m from the plan's origin) entered at <room> and spent itself in N rooms: <path> | k killed, w wounded, ... | what
        m = re.match(r"\[Fleet\] (?:Display: )?(.*?): a blow of ([\d.]+) at the hull \((\w+) face, (\w+) section, struck at ([^)]*) m\) entered at (.*?) \(([^)]*) m\) and spent itself in (\d+) rooms: (.*?) \| (.*?) \| ?(.*)$", ln)
        if not m:
            print("  " + ln)
            continue
        _, dmg, face, sec, struck, entry, at, n, path, people, what = m.groups()
        print(f"  {face:9} ({sec} section) struck at {struck} m, enters at {entry} ({at} m)")
        print(f"            crosses {n} room(s): {path}")
        print(f"            {people}")
        if what.strip():
            print(f"            {what.strip()}")


# ------------------------------------------------------------------------------------------------ a ship that breaks
def cmd_breaks(a: argparse.Namespace) -> None:
    cmds = [f"astra.war.tune {kv.split('=')[0]} {kv.split('=')[1]}" for kv in a.tune.split(",") if "=" in kv]
    cmds += ["astra.war.sandbox", f"astra.war.spawn {a.cls} {a.side} 0 0 0 0 id=TGT static passive"]
    # rounds of blows, one every few seconds: the war's own model works between them (a section that is gutted, the hull breaking up, the fires)
    at = "|".join(f"{3 + i * a.every:g}=astra.war.fleet pound TGT {a.face} {a.damage} {a.blows} {a.kind}" for i in range(a.rounds))
    want = {"bow": 0, "stern": 2}.get(a.face)
    print(f"== {a.rounds} rounds of {a.blows} x {a.kind} blows of {a.damage}, one every {a.every:g} s, on the {a.face} of a {a.side} {a.cls}; {a.seconds:.0f} s, {a.seeds} seed(s)")
    ok = 0
    for seed in range(1, a.seeds + 1):
        out, log = run_exec(cmds, a.seconds, seed, f"fleet_breaks_{seed}", at=at)
        if not out.exists():
            print(f"  seed {seed}: no record")
            continue
        d = war.load(out)
        tgt = next((s for s in d["final"]["ships"] if s["c"] == "TGT"), {})
        books = tgt.get("interior") or {}
        evs = [e for e in d["events"] if "TGT" in e["text"] and e.get("report")]
        broke = next((re.search(r"broke apart at the (\w+)", e["text"]).group(1) for e in evs if re.search(r"broke apart at the (\w+)", e["text"])), None)
        gutted = [re.search(r"the (\w+) section is gutted", e["text"]).group(1) for e in evs if re.search(r"the (\w+) section is gutted", e["text"])]
        rounds = log_lines(log, "blows of")
        pound = f"{len(rounds)} rounds struck; the last: " + (rounds[-1][:120] if rounds else "")
        lost, total = books.get("rooms_lost_by_section", [0, 0, 0]), books.get("rooms_by_section", [1, 1, 1])
        share = [100.0 * l / max(1, t) for l, t in zip(lost, total)]
        names = ("bow", "mid", "stern")
        print(f"  seed {seed}: {pound[:170]}")
        for e in evs[:6]:
            print(f"      {e['t']:6.1f} s  {e['text'].replace('tactical: ', '')[:150]}")
        print(f"      fate {tgt.get('fate', '?')}; rooms lost bow {lost[0]}/{total[0]} ({share[0]:.0f}%), mid {lost[1]}/{total[1]} ({share[1]:.0f}%), stern {lost[2]}/{total[2]} ({share[2]:.0f}%); "
              f"crew {books.get('crew', 0)}: {books.get('killed', 0)} killed, {books.get('wounded', 0)} wounded, {books.get('lost_with_ship', 0)} lost with the ship; "
              f"{books.get('fires', 0)} fires, {books.get('holes', 0)} holes, {books.get('wrecks', 0)} rooms wrecked")
        worst = max(range(3), key=lambda i: share[i])
        verdict = "no break"
        if broke:
            same = names[worst] == broke and (not gutted or broke in gutted)
            verdict = f"broke at the {broke}: the inside lost most in the {names[worst]} ({share[worst]:.0f}%) " + ("PASS" if same else "FAIL")
            ok += 1 if same else 0
        elif gutted:
            verdict = f"a section gutted ({', '.join(gutted)}), no break yet in {a.seconds:.0f} s"
        print(f"      {verdict}")
    if want is not None or a.seeds:
        print(f"  verdict: {ok} of {a.seeds} ran to a break where the inside lost its rooms" + (" PASS" if ok == a.seeds else ""))


# ------------------------------------------------------------------------------------------------ the cost, N ships
def fleet_of(path: Path) -> dict:
    d = war.load(path)
    st = d.get("stats", {})
    fl = st.get("fleet", {})
    secs = max(1.0, d.get("battle_seconds", 1.0))
    perf = st.get("perf", {})
    ships = [s for s in d["final"]["ships"] if not s.get("craft") and s["c"] != "AQUILA"]
    return {"secs": secs, "fleet": fl, "perf": perf, "world": st.get("world_tick", {}), "ships": ships, "n": len(ships)}


def cmd_cost(a: argparse.Namespace) -> None:
    print(f"== {a.scenario}: {a.seconds:.0f} s of battle, {a.seeds} seed(s) (the commandlet ticks at 0.1 s: the insides step their physics every 0.5 s of it)")
    rows = {}
    for name, ex in (("without", "astra.fleet.interior 0"), ("with", "astra.fleet.interior 1")):
        ns = argparse.Namespace(seconds=a.seconds, jump=-1, step=0.1, every=10, scenario=a.scenario, exec=ex, seed=1, nseeds=a.seeds, views=False)
        paths = war.seeds_run(ns, f"fleet_cost_{name}", ex, list(range(1, a.seeds + 1)), 1)
        rows[name] = [fleet_of(p) for p in paths if p.exists()]
    for name, rs in rows.items():
        for i, r in enumerate(rs):
            fl, pf = r["fleet"], r["perf"]
            with_i = fl.get("ships_with_interior_astra", 0) + fl.get("ships_with_interior_mandate", 0)
            per_s = fl.get("ms_total", 0) / r["secs"]
            line = (f"  {name:8} seed {i + 1}: {r['n']} warships, {with_i} with an inside at the end, {fl.get('blows', 0)} blows, {fl.get('ticks', 0)} ship-ticks; "
                    f"the battle's tick {pf.get('ms_avg', 0):.3f} ms avg / {pf.get('ms_p95', 0):.3f} p95 / {pf.get('ms_max', 0):.2f} max")
            if name == "with":
                line += (f"; insides {fl.get('ms_total', 0):.0f} ms in all = {per_s:.2f} ms per second of battle"
                         f" ({per_s / max(1, with_i):.3f} per ship with an inside), worst call {fl.get('ms_worst_call', 0):.2f} ms")
            print(line)
    if rows["with"] and rows["without"]:
        w, wo = rows["with"][0], rows["without"][0]
        d_ms = w["perf"].get("ms_avg", 0) - wo["perf"].get("ms_avg", 0)
        per_s = d_ms * 10.0                                  # (the commandlet's tick is 0.1 s of battle)
        print(f"  the battle's tick (0.1 s) costs {d_ms:+.3f} ms on average with the insides ({100 * d_ms / max(1e-9, wo['perf'].get('ms_avg', 1e-9)):+.0f}%): "
              f"{per_s:.2f} ms of every second of battle, {per_s / 60:.3f} ms of a frame at 60 fps on average ({per_s / 1000 * 100:.2f}% of a core)")


# ------------------------------------------------------------------------------------------------ the war with and without
def crew_books(paths: list[Path]) -> dict:
    tot = {"crew": 0, "killed": 0, "wounded": 0, "lost": 0, "ships": 0, "fires": 0, "holes": 0}
    for p in paths:
        if not p.exists():
            continue
        d = war.load(p)
        for s in d["final"]["ships"]:
            b = s.get("interior")
            if not b or s.get("craft"):
                continue
            tot["ships"] += 1
            tot["crew"] += b.get("crew", 0)
            tot["killed"] += b.get("killed", 0)
            tot["wounded"] += b.get("wounded", 0)
            tot["lost"] += b.get("lost_with_ship", 0)
            tot["fires"] += b.get("fires", 0)
            tot["holes"] += b.get("holes", 0)
    return tot


def cmd_ab(a: argparse.Namespace) -> None:
    seeds = list(range(1, a.seeds + 1))
    for sc in a.scenarios.split(","):
        print(f"== {sc}: {a.seeds} seeds, {a.seconds:.0f} s")
        res = {}
        for name, ex in (("without", "astra.fleet.interior 0"), ("with", "astra.fleet.interior 1")):
            ns = argparse.Namespace(seconds=a.seconds, jump=-1, step=0.1, every=10, scenario=sc, exec=ex, seed=1, nseeds=1, views=False)
            paths = war.seeds_run(ns, f"fleet_ab_{sc}_{name}", ex, seeds, 2)
            ms = [war.metrics(p) for p in paths if p.exists()]
            edge = [(m["astra"]["alive"] + m["astra"]["gone"]) - (m["mandate"]["alive"] + m["mandate"]["gone"]) for m in ms]
            se = (statistics.pstdev(edge) / math.sqrt(len(edge))) if len(edge) > 1 else 0.0
            res[name] = (ms, edge, se, crew_books(paths))
        for name, (ms, edge, se, cb) in res.items():
            if not ms:
                print(f"  {name:8} no records")
                continue
            n_a, n_m = ms[0]["astra"]["n"], ms[0]["mandate"]["n"]
            alive_a = statistics.mean(m["astra"]["alive"] + m["astra"]["gone"] for m in ms)
            alive_m = statistics.mean(m["mandate"]["alive"] + m["mandate"]["gone"] for m in ms)
            tick = statistics.mean(m["perf"].get("ms_avg", 0) for m in ms)
            p95 = statistics.mean(m["perf"].get("ms_p95", 0) for m in ms)
            line = (f"  {name:8} survivors ASTRA {alive_a:.1f}/{n_a}, Mandate {alive_m:.1f}/{n_m}; edge {statistics.mean(edge):+.2f}±{se:.2f}; "
                    f"tick {tick:.3f} ms (p95 {p95:.3f})")
            if name == "with" and cb["ships"]:
                k = len(ms)
                line += (f"; per battle: {cb['ships'] / k:.1f} ships with an inside, {cb['killed'] / k:.0f} killed and {cb['wounded'] / k:.0f} wounded by the blows "
                         f"of {cb['crew'] / k:.0f} aboard, {cb['lost'] / k:.0f} lost with their ships, {cb['fires'] / k:.0f} fires, {cb['holes'] / k:.0f} holes")
            print(line)
        if "with" in res and "without" in res and res["with"][0] and res["without"][0]:
            e1, e0 = res["with"][1], res["without"][1]
            d = statistics.mean(e1) - statistics.mean(e0)
            sd = math.hypot(res["with"][2], res["without"][2])
            print(f"  the insides move the survivors edge by {d:+.2f} ± {sd:.2f} warships ({'inside the noise' if abs(d) < 2 * max(sd, 1e-9) else 'a real change'})")


# ------------------------------------------------------------------------------------------------ the plans
def cmd_plans(a: argparse.Namespace) -> None:
    cmd = [sys.executable, str(ROOT / "art" / "blender" / "ship_class_plans.py"), "--no-stage"]
    if a.only:
        cmd += ["--only", a.only]
    sys.exit(subprocess.call(cmd, cwd=str(ROOT)))


def main() -> None:
    ap = argparse.ArgumentParser(prog="fleet.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("trace")
    p.add_argument("--class", dest="cls", default="acheron")
    p.add_argument("--side", default="mandate")
    p.add_argument("--faces", default="bow,port,dorsal")
    p.add_argument("--damage", type=float, default=400)
    p.add_argument("--kind", default="rail")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(fn=cmd_trace)
    p = sub.add_parser("breaks")
    p.add_argument("--class", dest="cls", default="acheron")
    p.add_argument("--side", default="mandate")
    p.add_argument("--face", default="bow", choices=FACES)
    p.add_argument("--damage", type=float, default=150)
    p.add_argument("--blows", type=int, default=6, help="blows in a round")
    p.add_argument("--rounds", type=int, default=5)
    p.add_argument("--every", type=float, default=4.0, help="seconds between rounds")
    p.add_argument("--kind", default="rail")
    p.add_argument("--seconds", type=float, default=60)
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--tune", default="breakup_p1=1", help="the war's tuning (astra.war.tune): by default the first section gutted is where the hull breaks, which the war leaves to chance (25%%)")
    p.set_defaults(fn=cmd_breaks)
    p = sub.add_parser("cost")
    p.add_argument("--scenario", default="scale_30x150")
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--seeds", type=int, default=1)
    p.set_defaults(fn=cmd_cost)
    p = sub.add_parser("ab")
    p.add_argument("--scenarios", default="sym_small,sym_medium,sym_two,asym_2to1")
    p.add_argument("--seeds", type=int, default=12)
    p.add_argument("--seconds", type=float, default=900)
    p.set_defaults(fn=cmd_ab)
    p = sub.add_parser("plans")
    p.add_argument("--only", default="")
    p.set_defaults(fn=cmd_plans)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
