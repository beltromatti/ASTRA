#!/usr/bin/env python3
"""Run the war headless and read what happened (Source/ASTRA/AstraWarSimCommandlet.*): no rendering, no GPU, faster than
real time. For the lead and the war module's support agents (in their own worktree, with their own build).

  tools/war.py run [--seconds 900] [--jump 170] [--exec "astra.battle.spawn styx 12 30"] [--scenario name] [--out Saved/War/run.json]
  tools/war.py report Saved/War/run.json      the story of the battle: arrivals, kills, damage, withdrawals, the outcome, the books
  tools/war.py ship Saved/War/run.json T-21   one ship through the battle (position, hull, shields, mode, target)
  tools/war.py ab --a "..." --b "..." --seeds 6 [--scenario name] [--jobs 3]
                                              the same scenario over seeds, variant A (an --exec) against B, side by side
  tools/war.py batch --seeds 12 [--tag t] [--scenario name] [--exec "..."]
                                              N seeds of one scenario (in parallel), one line per seed and the mean
  tools/war.py compare tagA tagB              two saved batches (Saved/War/<tag>_<seed>.json) side by side

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses
-nullrhi: it never opens a window or touches the GPU, so it can run while the game or the editor is open.
The scenarios are data/war/scenarios/*.json (see docs/GUERRA.md); without --scenario the opening (Aurelia patrol) is played.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")
WAR = ROOT / "Saved" / "War"


def build_args(a: argparse.Namespace, out: Path) -> list[str]:
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={a.seconds}", f"-step={a.step}",
            f"-every={a.every}", f"-out={out}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout",
            "-FullStdOutLogOutput"]
    if a.jump is not None and a.jump >= 0:
        args.append(f"-jump={a.jump}")
    args.append(f"-seed={a.seed}")
    if getattr(a, "nseeds", 1) > 1:
        args.append(f"-seeds={a.nseeds}")                 # several battles in one process: the start-up is most of a run
    if getattr(a, "scenario", ""):
        args.append(f"-scenario={a.scenario}")
    if a.exec:
        args.append(f'-exec={a.exec}')
    return args


def run_once(a: argparse.Namespace, out: Path, log: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as f:
        # a crash can leave the engine hanging in its crash handler: never wait for ever
        p = subprocess.Popen(build_args(a, out), stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=180.0 + getattr(a, "nseeds", 1) * (6.0 + a.seconds / 40.0))
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f"   the war bench did not finish in time: killed (log {log})")
        return p.returncode


def cmd_run(a: argparse.Namespace) -> None:
    out = (ROOT / a.out).resolve()
    log = WAR / "last_run.log"
    t0 = time.time()
    rc = run_once(a, out, log)
    if getattr(a, "quiet", False):
        if rc != 0:
            print(f"   exit {rc} (log {log})")
        return
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[WarSim]" in l or "Error" in l]
    for l in lines[-12:]:
        print(l[l.find("[WarSim]"):] if "[WarSim]" in l else l)
    print(f"exit {rc} in {time.time() - t0:.0f} s; log {log}")
    if out.exists():
        report(out)


# ------------------------------------------------------------------------------------------------ reading a record
def load(path: str | Path) -> dict:
    raw = Path(path).read_bytes()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return json.loads(raw.decode(enc))


def fate_of(s: dict) -> str:
    """alive | destroyed | gone (left the theatre, or a craft that landed) — older records only have `alive`."""
    if "fate" in s:
        return s["fate"]
    return "alive" if s.get("alive") else "gone"


def focus_from_frames(d: dict, side: str) -> float:
    """The share of a side's warships that aim at the same target (the modal one), averaged over the frames where at least
    two of them have a target: works on any record, old or new."""
    vals = []
    for f in d["frames"]:
        ids = {s["id"]: s for s in f["ships"]}
        tg = [s["target"] for s in f["ships"] if s["side"] == side and not s["craft"] and s["alive"] and s.get("target", -1) >= 0
              and ids.get(s["target"], {}).get("alive")]
        if len(tg) >= 2:
            vals.append(max(tg.count(t) for t in set(tg)) / len(tg))
    return statistics.mean(vals) if vals else -1.0


def metrics(path: Path | str) -> dict:
    d = load(path)
    fin = d["final"]["ships"]
    st = d.get("stats", {})
    m: dict = {"t": d["battle_seconds"]}
    for side in ("astra", "mandate"):
        caps = [s for s in fin if s["side"] == side and not s["craft"] and s["c"] != "AQUILA" and not s["c"].startswith("EAGLE")]
        m[side] = {"n": len(caps), "alive": sum(1 for s in caps if fate_of(s) == "alive"),
                   "destroyed": sum(1 for s in caps if fate_of(s) == "destroyed"),
                   "gone": sum(1 for s in caps if fate_of(s) == "gone")}
        c = st.get("craft", {}).get(side, {})
        m[side]["craft"] = {"launched": c.get("launched", 0), "lost": c.get("lost", 0), "recovered": c.get("recovered", 0),
                            "pd": c.get("lost_point_defence", 0), "guns": c.get("lost_craft_guns", 0), "msl": c.get("lost_missiles", 0)}
        m[side]["focus"] = st.get("focus", {}).get(side, focus_from_frames(d, side))
        m[side]["ships"] = st.get("ships", {}).get(side, {})
        m[side]["missiles"] = st.get("missiles", {}).get(side, {})
    aq = next((s for s in fin if s["c"] == "AQUILA"), None)
    if aq is None:
        m["aquila"] = "-"
    elif aq["alive"]:
        m["aquila"] = f"{aq.get('hull', 0):.0f}%"
    else:
        m["aquila"] = "LOST" if aq.get("fate", "destroyed") == "destroyed" else "-"      # a sandbox scenario has no Aquila in it
    m["aquila_hull"] = aq.get("hull", 0) if aq and aq["alive"] else 0
    ev = [e for e in d["events"] if e["report"] and "engagement over" in e["text"]]
    m["over_at"] = ev[0]["t"] if ev else None
    m["perf"] = st.get("perf", {})
    m["world_tick"] = st.get("world_tick", {})
    m["damage"] = st.get("damage", {})
    return m


def outcome(path: Path) -> dict:
    """The old summary: (alive, total, craft alive, craft total) per side."""
    d = load(path)
    fin = d["final"]["ships"]
    o = {}
    for side in ("astra", "mandate"):
        caps = [s for s in fin if s["side"] == side and not s["craft"]]
        craft = [s for s in fin if s["side"] == side and s["craft"]]
        o[side] = (sum(1 for s in caps if s["alive"]), len(caps), sum(1 for s in craft if s["alive"]), len(craft))
    aq = next((s for s in fin if s["c"] == "AQUILA"), None)
    o["aquila"] = f"{aq.get('hull', 0):.0f}%" if aq and aq["alive"] else "LOST"
    return o


# ------------------------------------------------------------------------------------------------ batches
def seeds_run(a: argparse.Namespace, tag: str, ex: str, seeds: list[int], jobs: int) -> list[Path]:
    WAR.mkdir(parents=True, exist_ok=True)

    # the seeds go to the processes in runs of consecutive seeds: each process fights its battles one after the other
    n = max(1, min(jobs, len(seeds)))
    chunks, k = [], 0
    for i in range(n):
        size = len(seeds) // n + (1 if i < len(seeds) % n else 0)
        chunks.append(seeds[k:k + size])
        k += size

    def one(chunk: list[int]) -> None:
        ns = argparse.Namespace(**vars(a))
        ns.exec = ex
        ns.seed = chunk[0]
        ns.nseeds = len(chunk)
        out = WAR / (tag + "_{seed}.json")
        rc = run_once(ns, out, WAR / f"{tag}_{chunk[0]}.log")
        for sd in chunk:
            if not (WAR / f"{tag}_{sd}.json").exists():
                print(f"   {tag} seed {sd}: no record (exit {rc}, log {WAR / f'{tag}_{chunk[0]}.log'})")

    with ThreadPoolExecutor(n) as pool:
        list(pool.map(one, chunks))
    return [WAR / f"{tag}_{sd}.json" for sd in seeds]


def fmt_side(m: dict, side: str) -> str:
    s = m[side]
    c = s["craft"]
    return (f"{s['alive']}/{s['n']} alive {s['destroyed']} lost {s['gone']} left"
            f"  craft {c['launched']:3d} out {c['lost']:3d} lost (PD {c['pd']}, guns {c['guns']}, msl {c['msl']}) {c['recovered']:3d} home")


def print_batch(tag: str, paths: list[Path]) -> list[dict]:
    rows = []
    for p in paths:
        if not p.exists():
            continue
        m = metrics(p)
        rows.append(m)
        seed = p.stem.split("_")[-1]
        ww = m["world_tick"].get("ms_avg", 0)
        print(f"  seed {seed:>3}  Aquila {m['aquila']:>5}  ASTRA {fmt_side(m, 'astra')}  |  MANDATE {fmt_side(m, 'mandate')}"
              f"  focus {m['astra']['focus']:.2f}/{m['mandate']['focus']:.2f}  ms/tick {m['perf'].get('ms_avg', 0):.3f} (world {ww:.3f})")
    if rows:
        def mean(f):
            v = [f(r) for r in rows]
            return statistics.mean(v), (statistics.pstdev(v) if len(v) > 1 else 0.0)
        for side in ("astra", "mandate"):
            a, sa = mean(lambda r: r[side]["alive"])
            n = rows[0][side]["n"]
            cl, scl = mean(lambda r: r[side]["craft"]["lost"])
            pd, spd = mean(lambda r: r[side]["craft"]["pd"])
            fo, sfo = mean(lambda r: max(r[side]["focus"], 0.0))
            print(f"  mean {side:8}: warships alive {a:4.1f}±{sa:3.1f} of {n}   craft lost {cl:5.1f}±{scl:4.1f} (to PD {pd:4.1f}±{spd:3.1f})"
                  f"   focus of fire {fo:.2f}±{sfo:.2f}")
        ah, sah = mean(lambda r: r["aquila_hull"])
        ms, sms = mean(lambda r: r["perf"].get("ms_avg", 0))
        p95, _ = mean(lambda r: r["perf"].get("ms_p95", 0))
        print(f"  mean Aquila hull {ah:5.1f}%±{sah:4.1f}   battle-subsystem tick {ms:.3f}±{sms:.3f} ms (p95 {p95:.3f})")
    return rows


def cmd_batch(a: argparse.Namespace) -> None:
    seeds = list(range(1, a.seeds + 1))
    t0 = time.time()
    paths = seeds_run(a, a.tag, a.exec, seeds, a.jobs)
    print(f"== {a.tag}: {a.scenario or 'opening'} {a.exec or ''} ({time.time() - t0:.0f} s)")
    print_batch(a.tag, paths)


def cmd_ab(a: argparse.Namespace) -> None:
    seeds = list(range(1, a.seeds + 1))
    for name, ex in (("A", a.a), ("B", a.b)):
        t0 = time.time()
        paths = seeds_run(a, f"ab_{name}", ex, seeds, a.jobs)
        print(f"== variant {name}: {ex or '(as is)'} ({time.time() - t0:.0f} s)")
        print_batch(f"ab_{name}", paths)


def cmd_compare(a: argparse.Namespace) -> None:
    for tag in (a.a, a.b):
        paths = sorted(WAR.glob(f"{tag}_*.json"), key=lambda p: int(p.stem.split("_")[-1]))
        print(f"== {tag}")
        print_batch(tag, paths)


# ------------------------------------------------------------------------------------------------ reading one record
def report(path: Path | str) -> None:
    d = load(str(path))
    print(f"\n== {path}: {d['battle_seconds']:.0f} s of battle in {d['wall_seconds']:.1f} s")
    first = {}
    for f in d["frames"]:
        for s in f["ships"]:
            first.setdefault(s["id"], (f["t"], s))
    deaths = []
    prev = {}
    for f in d["frames"]:
        for s in f["ships"]:
            if prev.get(s["id"], True) and not s["alive"]:
                deaths.append((f["t"], s))
            prev[s["id"]] = s["alive"]
    print("-- arrivals (first seen in the record)")
    for sid, (t, s) in sorted(first.items(), key=lambda x: x[1][0]):
        if t > 0 and not s["craft"]:
            print(f"  {t:7.1f}  {s['c']:6} {s['name'][:28]:28} {s['side']}")
    print("-- losses (a craft that landed is not a loss)")
    fin = {s["id"]: s for s in d["final"]["ships"]}
    for t, s in deaths:
        f = fate_of(fin.get(s["id"], s))
        if s["craft"] and f == "gone":
            continue
        print(f"  {t:7.1f}  {s['c']:6} {s['name'][:28]:28} {s['side']}{' (craft)' if s['craft'] else ''}"
              f"{'  [left the theatre]' if f == 'gone' and not s['craft'] else ''}")
    fin_l = d["final"]["ships"]
    for side in ("astra", "mandate", "neutral"):
        caps = [s for s in fin_l if s["side"] == side and not s["craft"]]
        craft = [s for s in fin_l if s["side"] == side and s["craft"]]
        alive = [s for s in caps if s["alive"]]
        print(f"-- {side}: warships {len(alive)}/{len(caps)} alive, craft {sum(1 for s in craft if s['alive'])}/{len(craft)} flying at the end")
        for s in alive:
            print(f"     {s['c']:6} {s['name'][:24]:24} hull {s.get('hull', 0):3.0f}% shields {s.get('shield', 0):3.0f}%"
                  f" {'FLEEING' if s.get('fleeing') else ''}")
    st = d.get("stats")
    if st:
        print_stats(st)
    reports = [e for e in d["events"] if e["report"]]
    print(f"-- {len(d['events'])} events, {len(reports)} reports; the last reports:")
    for e in reports[-8:]:
        print(f"  {e['t']:7.1f}  {e['text'][:150]}")


def print_stats(st: dict) -> None:
    print("-- the books")
    dm = st.get("damage", {})
    for t in ("kinetic", "energy", "explosive"):
        x = dm.get(t)
        if not x or not x["hits"]:
            continue
        fac = x["by_facing"]
        tot = max(x["in"], 1e-9)
        print(f"  {t:9} {x['hits']:5d} hits {x['in']:8.0f} dmg: shields {100 * x['shield'] / tot:3.0f}%  armour {100 * x.get('plate', 0) / tot:3.0f}%"
              f"  structure {100 * x['structure'] / tot:3.0f}%   by facing "
              + " ".join(f"{k[:2]} {100 * v / tot:2.0f}%" for k, v in fac.items()))
    if "sectors_collapsed" in dm:
        print(f"  shield sectors taken down: {dm['sectors_collapsed']}")
    for side in ("astra", "mandate"):
        c = st.get("craft", {}).get(side, {})
        sh = st.get("ships", {}).get(side, {})
        ms = st.get("missiles", {}).get(side, {})
        print(f"  {side:8} craft: {c.get('launched', 0)} out, {c.get('lost', 0)} lost (PD {c.get('lost_point_defence', 0)}, craft guns "
              f"{c.get('lost_craft_guns', 0)}, missiles {c.get('lost_missiles', 0)}, other {c.get('lost_other', 0)}), {c.get('recovered', 0)} recovered"
              f" | warships: {', '.join(f'{k} {v}' for k, v in sh.items() if v)}"
              f" | missiles: {ms.get('fired', 0)} fired, {ms.get('shot_down', 0)} shot down, {ms.get('decoyed', 0)} decoyed")
    fo = st.get("focus", {})
    print(f"  focus of fire (share of a side's damage on its most-hit target, 10 s windows): ASTRA {fo.get('astra', -1)} ({fo.get('astra_windows', 0)} windows),"
          f" Mandate {fo.get('mandate', -1)} ({fo.get('mandate_windows', 0)})")
    p = st.get("perf", {})
    if p:
        print(f"  the battle's tick: {p.get('ms_avg', 0):.3f} ms avg, p95 {p.get('ms_p95', 0):.3f}, p99 {p.get('ms_p99', 0):.3f}, max {p.get('ms_max', 0):.3f}"
              f" ({p.get('ticks', 0)} ticks; peak {p.get('peak_ships', 0)} warships, {p.get('peak_craft', 0)} craft, {p.get('peak_projectiles', 0)} projectiles)")
    w = st.get("world_tick")
    if w:
        print(f"  the whole world tick: {w['ms_avg']:.3f} ms avg, p95 {w['ms_p95']:.3f}, max {w['ms_max']:.3f}")


def cmd_duel(a: argparse.Namespace) -> None:
    """Static shooters against a passive dummy, a run per face of the dummy and per seed: how long the sector holds, when a
    section is gutted, how much damage it takes to put the ship out of action, and where the damage went. Shooters and
    dummy stay exactly on their marks."""
    facings = {"bow": (1, 0, 0), "stern": (-1, 0, 0), "port": (0, -1, 0), "starboard": (0, 1, 0), "dorsal": (0, 0, 1), "ventral": (0, 0, -1)}
    names = a.facings.split(",") if a.facings else list(facings)

    def one(face: str) -> tuple[str, list[dict]]:
        vx, vy, vz = facings[face]
        perp = (0, 1, 0) if face in ("bow", "stern", "dorsal", "ventral") else (1, 0, 0)
        cmds = [f"astra.war.tune {kv.split('=')[0]} {kv.split('=')[1]}" for kv in a.tune.split(",") if "=" in kv]
        cmds += ["astra.war.sandbox", f"astra.war.spawn {a.target} mandate 0 0 0 0 id=TGT static passive"]
        for i in range(a.n):
            lat = (i - (a.n - 1) / 2) * 0.35
            x, y, z = vx * a.range + perp[0] * lat, vy * a.range + perp[1] * lat, vz * a.range + perp[2] * lat
            heading = math.degrees(math.atan2(-y, -x))
            mark = math.degrees(math.atan2(-z, math.hypot(x, y)))
            opts = f" missiles={a.missiles}" if a.missiles >= 0 else ""
            cmds.append(f"astra.war.spawn {a.shooter} astra {x:.3f} {y:.3f} {z:.3f} {heading:.2f} mark={mark:.2f} id=S{i} static{opts}")
        ns = argparse.Namespace(seconds=a.seconds, jump=-1, step=0.1, every=2, scenario="", exec=";".join(cmds), seed=1, nseeds=a.seeds)
        base = f"duel_{a.target}_{a.shooter}_{face}"
        run_once(ns, WAR / (base + "_{seed}.json"), WAR / f"{base}.log")
        return face, [load(WAR / f"{base}_{sd}.json") for sd in range(1, a.seeds + 1) if (WAR / f"{base}_{sd}.json").exists()]

    res: dict[str, list[dict]] = {f: [] for f in names}
    with ThreadPoolExecutor(max(1, a.jobs)) as pool:
        for face, runs in pool.map(one, names):
            res[face] = runs
    print(f"== {a.n} x {a.shooter} (static, {a.range} km) against a {a.target} dummy, {a.seconds:.0f} s, {a.seeds} seed(s)"
          f"{'' if a.missiles < 0 else f', {a.missiles} missiles'}{'  tune ' + a.tune if a.tune else ''}")
    print(f"  {'face':9} {'damage taken to be out':>22} {'time out':>9} {'sector down':>11} {'fates (dead/dark/alive)':>24}   shield / plate / structure share")
    for face in names:
        runs = res[face]
        if not runs:
            print(f"  {face:9} (no record)")
            continue
        idx = {"bow": 0, "stern": 1, "port": 2, "starboard": 3, "dorsal": 4, "ventral": 5}[face]
        tot, tout, tsec, fates = [], [], [], {"destroyed": 0, "disabled": 0, "alive": 0}
        sh = pl = st = 0.0
        for d in runs:
            dm = d["stats"]["damage"]
            kinds = [k for k in dm if isinstance(dm[k], dict)]
            tot.append(sum(dm[k]["in"] for k in kinds))
            sh += sum(dm[k]["shield"] for k in kinds)
            pl += sum(dm[k]["plate"] for k in kinds)
            st += sum(dm[k]["structure"] for k in kinds)
            t_out = t_sec = None
            for f in d["frames"]:
                s = next((x for x in f["ships"] if x["c"] == "TGT"), None)
                if s is None:
                    continue
                if t_sec is None and s["alive"] and "shields" in s and s["shields"][idx] <= 5:
                    t_sec = f["t"]
                if t_out is None and (not s["alive"] or s.get("fate") == "disabled"):
                    t_out = f["t"]
            fin = next((x for x in d["final"]["ships"] if x["c"] == "TGT"), {})
            fates[fin.get("fate", "alive") if fin.get("fate") in fates else "destroyed" if not fin.get("alive", True) else "alive"] += 1
            if t_out is not None:
                tout.append(t_out)
            if t_sec is not None:
                tsec.append(t_sec)
        allv = max(sh + pl + st, 1e-9)
        mean = lambda v: (statistics.mean(v) if v else float("nan"))
        print(f"  {face:9} {mean(tot):14.0f} ±{(statistics.pstdev(tot) if len(tot) > 1 else 0):5.0f} {mean(tout):8.0f}s {mean(tsec):10.0f}s"
              f" {fates['destroyed']:>10}/{fates['disabled']}/{fates['alive']}      {100 * sh / allv:3.0f}% / {100 * pl / allv:3.0f}% / {100 * st / allv:3.0f}%")


def cmd_embed(a: argparse.Namespace) -> None:
    """data/war/classes.json -> Source/ASTRA/AstraWarClassesData.inl (the table compiled in: the game runs without the file)."""
    src = ROOT / "data" / "war" / "classes.json"
    text = src.read_text()
    json.loads(text)                                   # it must parse
    chunks, cur = [], ""
    for line in text.splitlines(keepends=True):        # raw literals stay well under the 16 KB limit of some compilers
        if len(cur) + len(line) > 6000:
            chunks.append(cur)
            cur = ""
        cur += line
    chunks.append(cur)
    out = ROOT / "Source" / "ASTRA" / "AstraWarClassesData.inl"
    body = ",\n".join('R"json(' + c + ')json"' for c in chunks)
    out.write_text("// generated by `tools/war.py embed` from data/war/classes.json: do not edit here\n"
                   f"const char* const GAstraWarClassesJson[] = {{\n{body}\n}};\n")
    print(f"{out.relative_to(ROOT)}: {len(chunks)} chunk(s), {len(text)} bytes")


def cmd_report(a: argparse.Namespace) -> None:
    report(a.path)


def cmd_ship(a: argparse.Namespace) -> None:
    d = load(a.path)
    for f in d["frames"]:
        for s in f["ships"]:
            if s["c"].upper() == a.contact.upper() or s["name"].lower() == a.contact.lower():
                if not s["alive"]:
                    print(f"{f['t']:7.1f}  {fate_of(s)}")
                    return
                km = s["km"]
                extra = ""
                if "shields" in s:
                    extra = "  sectors " + "/".join(f"{v:.0f}" for v in s["shields"])
                print(f"{f['t']:7.1f}  ({km[0]:7.1f},{km[1]:7.1f},{km[2]:6.1f}) km  {s['v']:5.0f} m/s  hull {s['hull']:3.0f}%"
                      f"  sh {s['shield']:3.0f}%  mode {s['mode']}  target {s['target']}  stance {s['stance']}"
                      f"{'  FLEEING' if s['fleeing'] else ''}{extra}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="war.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser, seconds: float = 900, jump: float | None = -1) -> None:
        p.add_argument("--seconds", type=float, default=seconds)
        p.add_argument("--jump", type=float, default=jump)
        p.add_argument("--step", type=float, default=0.1)
        p.add_argument("--every", type=float, default=10)
        p.add_argument("--scenario", default="")

    p = sub.add_parser("run")
    common(p, 900, -1)
    p.add_argument("--exec", default="")
    p.add_argument("--out", default="Saved/War/run.json")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("ab", help="compare: the same scenario over several seeds, with and without an --exec change")
    common(p, 900, 160)
    p.add_argument("--seeds", type=int, default=4)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--a", default="", help="exec for variant A")
    p.add_argument("--b", default="", help="exec for variant B")
    p.set_defaults(fn=cmd_ab)
    p = sub.add_parser("batch", help="one scenario over N seeds in parallel: a line per seed and the mean")
    common(p, 900, 160)
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--tag", default="batch")
    p.add_argument("--exec", default="")
    p.set_defaults(fn=cmd_batch)
    p = sub.add_parser("compare", help="two saved batches side by side")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(fn=cmd_compare)
    p = sub.add_parser("duel", help="static shooters against a passive dummy from each face: the damage model on a bench")
    p.add_argument("--target", default="praetorian")
    p.add_argument("--shooter", default="acheron")
    p.add_argument("--n", type=int, default=2)
    p.add_argument("--range", type=float, default=5.0, help="km")
    p.add_argument("--seconds", type=float, default=240)
    p.add_argument("--facings", default="")
    p.add_argument("--missiles", type=int, default=-1, help="the shooters' missiles (-1: the class's)")
    p.add_argument("--tune", default="", help="tuning constants, name=value,name=value (astra.war.tune)")
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--jobs", type=int, default=4)
    p.set_defaults(fn=cmd_duel)
    p = sub.add_parser("embed", help="write the ship class table compiled into the game from data/war/classes.json")
    p.set_defaults(fn=cmd_embed)
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
