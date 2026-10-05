#!/usr/bin/env python3
"""Run the war headless and read what happened (Source/ASTRA/AstraWarSimCommandlet.*): no rendering, no GPU, faster than
real time. For the lead and the war module's support agents (in their own worktree, with their own build).

  tools/war.py run [--seconds 900] [--jump 170] [--exec "astra.battle.spawn styx 12 30"] [--scenario name] [--out Saved/War/run.json]
                   [--aquila | --aquila-opts "at=-34,0,0;speed=0"] [--holo-at 60,260]   the Aquila in the scenario (where, how); the holo table's plan (docs/SCALA.md)
  tools/war.py report Saved/War/run.json      the story of the battle: arrivals, kills, damage, withdrawals, the outcome, the books
  tools/war.py ship Saved/War/run.json T-21   one ship through the battle (position, hull, shields, mode, target)
  tools/war.py ab --a "..." --b "..." --seeds 6 [--scenario name] [--jobs 3]
                                              the same scenario over seeds, variant A (an --exec) against B, side by side
  tools/war.py batch --seeds 12 [--tag t] [--scenario name] [--exec "..."]
                                              N seeds of one scenario (in parallel), one line per seed and the mean
  tools/war.py compare tagA tagB              two saved batches (Saved/War/<tag>_<seed>.json) side by side
  tools/war.py sweep --scenario sym_small --seeds 96 --features flank=1,focus,saturate,rotate,retreat_ratio
                                              what each behaviour is worth: switched off (or set: name=value) for the ASTRA side alone in
                                              a symmetric scenario, against the control where both sides have it (astra.war.tune <name>_a)
  tools/war.py groups Saved/War/run.json     the battle groups through a record (state, order, focus, guide, axis, ships)
  tools/war.py views Saved/War/run.json      what the minds are given of the groups (record made with run --views), its size and the events
  tools/war.py mind --scenario sym_small --seeds 1-8 --minds mandate --model live --budget 0.1
                                              the minds in the loop (docs/GUERRA.md §8): the battle stops every half second of battle time, hands the
                                              minds what the game hands them and runs the commands they give; see mind/bench/war_arena.py (all its options)
  tools/war.py duel --shooter acheron --target praetorian --range 5
                                              static shooters against a passive dummy from each face: the damage model on a bench
  tools/war.py embed                          after a change in data/war/classes.json: rewrite the table compiled into the game
  tools/war.py suite [--seeds 8] [--only duel] [--tag base] [--exec "astra.war.tune ..."]
                                              the battle suite of BATTAGLIA-3 (duels, small fleets, the opening, the fleet battle) over seeds: one line each, before and
                                              after a change (tools/war.py SUITE)
  tools/war.py chase [--seeds 6] [--order-at 150]
                                              the helm on a retreat (BATTAGLIA-3): the Mandate raiders break off, the Aquila's helm goes after them five ways
  tools/war.py fight Saved/War/run.json | --tag batch [--vs other]
                                              what a battle was like to watch: the fire second by second, silences, engagements, the accuracy at each
                                              range, who killed whom, the retreats, the Aquila's heat and fires (tools/war_fight.py; BATTAGLIA-3)
  tools/war.py classes --small cd=0.85,regen=0.5 --scen ss,st,op --seeds 8 [--mandate-small ...] [--acheron ...] [--missiles acheron=48] [--salvo acheron=8]
                                              the class table under the bench: a variant of data/war/classes.json (written to Saved/War, the real file untouched) over a
                                              few scenarios, one summary each: the Aquila's hull and losses, the kills, the Mandate's missiles (tools/war_classes.py)

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses
-nullrhi: it never opens a window or touches the GPU, so it can run while the game or the editor is open. It never starts more than two
engine processes at once (each is ~1.5 GB and the machine is shared: MAX_PROCESSES).
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from war_fight import cmd_fight  # noqa: E402  (the fight log's reader, BATTAGLIA-3)
from war_classes import SCENARIOS, cmd_classes  # noqa: E402  (the class table under the bench, BATTAGLIA-3)

# The Captain's orders for the bench (the Aquila's stations take them as the officers would: `station` commands at battle times), by name:
#   engage   the tactical officer fires on every hostile warship as it comes, engineering moves to combat power (BATTAGLIA-3's duels)
#   standoff engage, plus the helm holds the range of the action (keep_on_bow with a standoff, in km, after the colon: standoff:20)
#   bow      engage, plus the helm keeps the bow on the action
#   intercept engage, plus the helm closes on the action on a lead course and holds the standoff (intercept:<km>)
#   aim      engage with the gunners on a system of the target (aim:engines | sensors | weapons | hangar | bridge | reactor | bow | midships | stern)
CAPTAIN_SCRIPTS = {
    "engage": ["1=astra.cmd station {'station':'tactical','mode':'engage','params':{'targets':['hostiles']}}",
               "1=astra.cmd station {'station':'engineering','mode':'combat'}"],
}


def captain_script(name: str) -> list[str]:
    """The `--at` items of a named script of the Captain's (see CAPTAIN_SCRIPTS). Parts join with `+`: `intercept:15+aim:engines` closes on the action to 15 km and has the gunners aim at its engines."""
    if not name:
        return []
    engage, aim, helm = False, "", []
    for part in name.split("+"):
        base, _, arg = part.partition(":")
        engage = engage or base in ("engage", "standoff", "bow", "intercept", "aim")
        if base == "aim":
            aim = arg or "engines"
        elif base == "standoff":
            helm.append("1=astra.cmd station {'station':'helm','mode':'keep_on_bow','params':{'target':'action','standoff_km':%s}}" % (arg or "20"))
        elif base == "bow":
            helm.append("1=astra.cmd station {'station':'helm','mode':'keep_on_bow','params':{'target':'action'}}")
        elif base == "intercept":
            helm.append("1=astra.cmd station {'station':'helm','mode':'intercept','params':{'target':'action','standoff_km':%s}}" % (arg or "20"))
    items = []
    if engage:
        params = "{'targets':['hostiles']" + (",'aim':'%s'" % aim if aim else "") + "}"
        items = ["1=astra.cmd station {'station':'tactical','mode':'engage','params':%s}" % params,
                 "1=astra.cmd station {'station':'engineering','mode':'combat'}"]
    return items + helm


def join_at(*parts: str) -> str:
    """The timed commands of several `--at` strings as one, in the order of their times: the bench runs them in the order given (a command due at 1 s waits behind one due at 380 s that
    came before it), so an `--at` of a scenario and a Captain's script (`--script`, orders at 1 s) have to be merged by time. Stable: those of the same second keep their order."""
    items = [it for part in parts for it in (part or "").split("|") if it.strip()]

    def when(it: str) -> float:
        try:
            return float(it.split("=", 1)[0])
        except ValueError:
            return 0.0
    return "|".join(sorted(items, key=when))


ROOT = Path(__file__).resolve().parent.parent
MAX_PROCESSES = 2                                             # AstraWarSim processes at once, whatever --jobs says
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")
WAR = ROOT / "Saved" / "War"


def build_args(a: argparse.Namespace, out: Path) -> list[str]:
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={a.seconds}", f"-step={a.step}",
            f"-every={a.every}", f"-out={out}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout",
            "-FullStdOutLogOutput"]
    if a.jump is not None and a.jump >= 0 and not getattr(a, "scenario", ""):
        args.append(f"-jump={a.jump}")               # (the opening's clock: a scenario has none)
    args.append(f"-seed={a.seed}")
    if getattr(a, "nseeds", 1) > 1:
        args.append(f"-seeds={a.nseeds}")                 # several battles in one process: the start-up is most of a run
    if getattr(a, "scenario", ""):
        args.append(f"-scenario={a.scenario}")
    if a.exec:
        args.append(f'-exec={a.exec}')
    if getattr(a, "at", ""):
        args.append(f'-at={a.at}')
    if getattr(a, "views", False):
        args.append("-views")                              # each frame also carries what the two minds are given of their groups
    if getattr(a, "aquila", False):
        args.append("-aquila")                             # the Aquila stays in the scenario (at the origin, with the ASTRA side)
    if getattr(a, "aquila_opts", ""):
        args.append(f"-aquila_opts={a.aquila_opts}")       # where she is and how she goes: at=-34,0,0;speed=0;heading=0 (astra.war.scenario <name> aquila ...)
    if getattr(a, "holo_at", ""):
        args.append(f"-holo_at={a.holo_at}")               # the holo table's plan at those battle times (docs/SCALA.md)
        args.append(f"-holo_out={ROOT / 'Saved' / 'War' / 'holo'}")
    if getattr(a, "classes", ""):
        args.append(f"-warclasses={Path(a.classes).resolve()}")      # a class table of its own for this run (an experiment): the real data/war/classes.json is left alone
    return args


def run_once(a: argparse.Namespace, out: Path, log: Path) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    limit = 180.0 + getattr(a, "nseeds", 1) * (6.0 + a.seconds / 40.0)
    with open(log, "w") as f:
        p = subprocess.Popen(build_args(a, out), stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        t0 = time.time()
        while p.poll() is None:
            time.sleep(0.5)
            # a crash leaves the engine hanging in its crash handler: read the log for it and never wait for ever
            crashed = False
            try:
                with open(log, "rb") as r:
                    r.seek(max(0, log.stat().st_size - 40000))
                    tail = r.read().decode(errors="replace")
                crashed = "Critical error" in tail or "Assertion failed" in tail
            except OSError:
                pass
            if crashed or time.time() - t0 > limit:
                time.sleep(2.0 if crashed else 0.0)                       # let the stack trace land in the log
                p.kill()
                p.wait()
                why = "crashed" if crashed else "did not finish in time"
                print(f"   the war bench {why}: killed (log {log})")
                if crashed:
                    lines = log.read_text(errors="replace").splitlines()
                    for i, l in enumerate(lines):
                        if "Critical error" in l or "Assertion failed" in l:
                            print("   " + "\n   ".join(x.strip() for x in lines[i:i + 8]))
                            break
                break
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
                   "gone": sum(1 for s in caps if fate_of(s) == "gone"),
                   "dark": sum(1 for s in caps if fate_of(s) == "disabled")}
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
    n = max(1, min(jobs, MAX_PROCESSES, len(seeds)))              # (the machine is shared: two engines at most, each is ~1.5 GB)
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
    return (f"{s['alive']}/{s['n']} alive {s['destroyed']} lost {s['gone']} left {s['dark']} dark"
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
        edge = [(r["astra"]["alive"] + r["astra"]["gone"]) - (r["mandate"]["alive"] + r["mandate"]["gone"]) for r in rows]
        cedge = [r["mandate"]["craft"]["lost"] - r["astra"]["craft"]["lost"] for r in rows]
        wa, wm = sum(1 for e in edge if e > 0), sum(1 for e in edge if e < 0)
        se = lambda v: (statistics.pstdev(v) / math.sqrt(len(v))) if len(v) > 1 else 0.0
        print(f"  outcome over {len(rows)} battles: ASTRA ahead {wa}, Mandate ahead {wm}, level {len(rows) - wa - wm};"
              f" survivors edge {statistics.mean(edge):+.2f}±{se(edge):.2f} warships, craft edge {statistics.mean(cedge):+.1f}±{se(cedge):.1f} (ASTRA's minus the Mandate's)")
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
    if getattr(a, "fight", False):
        from war_fight import fight_of, print_rows
        have = [p for p in paths if p.exists()]
        print_rows([fight_of(load(p)) for p in have], [p.stem.split("_")[-1] for p in have], detail=False)


def cmd_ab(a: argparse.Namespace) -> None:
    seeds = list(range(1, a.seeds + 1))
    for name, ex in (("A", a.a), ("B", a.b)):
        t0 = time.time()
        paths = seeds_run(a, f"ab_{name}", ex, seeds, a.jobs)
        print(f"== variant {name}: {ex or '(as is)'} ({time.time() - t0:.0f} s)")
        print_batch(f"ab_{name}", paths)


def cmd_sweep(a: argparse.Namespace) -> None:
    """What each behaviour is worth: the same symmetric scenario with the behaviour switched off for the ASTRA side alone
    (astra.war.tune <feature>_a 0), against the control where both sides have it."""
    seeds = list(range(1, a.seeds + 1))
    variants = [("control", "")]
    for f in a.features.split(","):
        # "flank" switches the behaviour off for ASTRA; "flank=1" sets it to a value (for the ones that are off by default, or a mode)
        n, _, v = f.partition("=")
        variants.append((f"{n} {'off' if not v else '=' + v} for ASTRA", f"astra.war.tune {n}_a {v or 0}"))
    for name, ex in variants:
        tag = "sw_" + name.split()[0]
        t0 = time.time()
        paths = seeds_run(a, tag, ex, seeds, a.jobs)
        print(f"== {name}  ({time.time() - t0:.0f} s)")
        rows = [metrics(p) for p in paths if p.exists()]
        edge = [(r["astra"]["alive"] + r["astra"]["gone"]) - (r["mandate"]["alive"] + r["mandate"]["gone"]) for r in rows]
        cedge = [r["mandate"]["craft"]["lost"] - r["astra"]["craft"]["lost"] for r in rows]
        wa, wm = sum(1 for e in edge if e > 0), sum(1 for e in edge if e < 0)
        se = lambda v: (statistics.pstdev(v) / math.sqrt(len(v))) if len(v) > 1 else 0.0
        print(f"   ASTRA ahead {wa}, Mandate ahead {wm}, level {len(rows) - wa - wm};"
              f" survivors edge {statistics.mean(edge):+.2f}±{se(edge):.2f} warships; craft edge {statistics.mean(cedge):+.1f}±{se(cedge):.1f}"
              f"; ASTRA alive {statistics.mean(r['astra']['alive'] + r['astra']['gone'] for r in rows):.2f}, Mandate alive {statistics.mean(r['mandate']['alive'] + r['mandate']['gone'] for r in rows):.2f}")


# The battle suite (BATTAGLIA-3): what a battle is like to watch, in the situations the user plays. (name, scenario, seconds, jump, script, exec)
SUITE = [
    ("duel Aquila-Styx", "duel_aq_styx", 600, -1, "engage", ""),
    ("duel Aquila-Acheron", "duel_aq_acheron", 900, -1, "engage", ""),
    ("Aquila v the strike group", "duel_aq_strike", 900, -1, "engage", ""),
    ("... helm at 24 km (the wheel)", "duel_aq_strike", 900, -1, "standoff:24", ""),
    ("Styx v Styx", "duel_styx_styx", 600, -1, "", ""),
    ("cruiser+destroyer a side", "duel_cruisers", 900, -1, "", ""),
    ("sym_small 3 v 3", "sym_small", 900, -1, "", ""),
    ("sym_medium 6 v 6", "sym_medium", 1200, -1, "", ""),
    ("the opening", "", 900, 160, "engage", ""),
    ("the opening, as the March plays it", "", 1100, 160, "engage", "", SCENARIOS["o13"][4]),   # (Solm's group, then the vanguard, then the relief: tools/war_classes.py)
    ("fleet_battle", "fleet_battle", 1200, -1, "engage", ""),
]


def cmd_suite(a: argparse.Namespace) -> None:
    """Every battle of SUITE over the seeds, and one line each: how long the fire went on, how continuous it was, who killed whom, who left."""
    from war_fight import fight_of
    seeds = list(range(1, a.seeds + 1))
    print(f"{'battle':<28} {'len':>5} {'action':>6} {'fire%':>5} {'sil':>4} {'eng':>4} {'maxeng':>6} | kills A/M (aq, craft) | {'shots/kill':>10} | {'ret':>4} | alive A/M | Aquila hull  heat")
    for name, scenario, seconds, jump, script, ex, *more in SUITE:
        if a.only and a.only.lower() not in name.lower() and a.only.lower() not in scenario.lower():
            continue
        ns = argparse.Namespace(**vars(a))
        ns.scenario, ns.seconds, ns.jump, ns.every = scenario, seconds, jump, 5
        ns.at = join_at(a.at, *more, *captain_script(script))
        ns.views, ns.aquila, ns.aquila_opts, ns.holo_at = False, False, "", ""
        tag = f"{a.tag}_{(scenario or ('opening13' if more else 'opening'))}"
        paths = seeds_run(ns, tag, "; ".join([x for x in [ex, a.exec] if x]), seeds, a.jobs)
        recs = [p for p in paths if p.exists()]
        if not recs:
            print(f"{name:<28} (no records)")
            continue
        rows = []
        for p in recs:
            d = load(p)
            f = fight_of(d)
            fin = d["final"]["ships"]
            aq = next((x for x in fin if x["c"] == "AQUILA"), None)
            alive = {side: sum(1 for x in fin if x["side"] == side and not x["craft"] and x["c"] != "AQUILA" and fate_of(x) in ("alive", "gone")) for side in ("astra", "mandate")}
            rows.append((f, alive, aq))
        mean = lambda xs: statistics.mean(xs) if xs else float("nan")
        ok = [r for r in rows if r[0].get("has_log")]
        if not ok:
            print(f"{name:<28} (no fight log)")
            continue
        def k(f, side, cat=""):
            return sum(v for key, v in f["kills_by"].items() if key.startswith(("mandate lost" if side == "astra" else "astra lost")) and (not cat or key.endswith(cat)))
        ka = mean([k(r[0], "astra") for r in ok]); km = mean([k(r[0], "mandate") for r in ok])
        kaq = mean([k(r[0], "astra", "to aquila") for r in ok])
        kcraft = mean([k(r[0], "astra", "to astra_craft") for r in ok])
        spk = [r[0]["shots_per_kill_astra"] for r in ok if r[0]["shots_per_kill_astra"]]
        heat = [r[0].get("heat_max") for r in ok if r[0].get("heat_max") is not None]
        ah = [r[2].get("hull", 0) if r[2] and r[2]["alive"] else 0 for r in ok if r[2]]
        print(f"{name:<28} {mean([r[0]['t'] for r in ok]):5.0f} {mean([r[0]['action_s'] for r in ok]):6.0f} {mean([100 * r[0]['fire_share'] for r in ok]):5.0f} "
              f"{mean([r[0]['longest_silence'] for r in ok]):4.0f} {mean([len(r[0]['engagements']) for r in ok]):4.1f} {mean([r[0]['longest_engagement'] for r in ok]):6.0f} | "
              f"{ka:4.1f}/{km:<4.1f} ({kaq:.1f}, {kcraft:.1f})       | {mean(spk) if spk else float('nan'):10.0f} | {mean([len(r[0]['retreats']) for r in ok]):4.1f} | "
              f"{mean([r[1]['astra'] for r in ok]):4.1f}/{mean([r[1]['mandate'] for r in ok]):<4.1f} | {mean(ah) if ah else float('nan'):5.0f}%  {mean(heat) if heat else float('nan'):4.0f}")
        sys.stdout.flush()


def chase_of(d: dict, t0: float) -> dict:
    """What the Aquila's helm made of a retreat: after the order at t0, how much of the time the nearest enemy was in her rails' reach, how far off it was, how much
    hull the enemy lost and how many ships were put out of action (from the record's frames: positions are km from the Aquila)."""
    frames = [f for f in d["frames"] if f["t"] >= t0]
    if not frames:
        return {}
    rail_km = 45.0
    in_reach, rng, hull0, hull1 = 0, [], None, None
    speeds, engines = [], []                                  # the raiders' speed and engines in the four minutes after the order: what the Aquila's guns did to their drives
    for f in frames:
        ships = [s for s in f["ships"] if s["side"] == "mandate" and not s["craft"] and s["alive"] and s.get("km")]
        if not ships:
            continue
        if f["t"] <= t0 + 240.0:
            speeds.extend(s["v"] for s in ships)
            engines.extend(s["systems"][0] for s in ships if s.get("systems"))
        near = min(math.sqrt(sum(c * c for c in s["km"])) for s in ships)
        rng.append(near)
        in_reach += 1 if near <= rail_km else 0
        hull = sum(s["hull"] for s in ships)
        hull0 = hull if hull0 is None else hull0
        hull1 = hull
    fin = d["final"]["ships"]
    dead = sum(1 for s in fin if s["side"] == "mandate" and not s["craft"] and fate_of(s) in ("destroyed", "disabled"))
    aq = next((s for s in fin if s["c"] == "AQUILA"), None)
    return {"in_reach": in_reach / max(1, len(rng)), "range_end": rng[-1] if rng else float("nan"), "range_mean": statistics.mean(rng) if rng else float("nan"),
            "hull_lost": (hull0 - hull1) if hull0 is not None else 0.0, "out": dead, "aquila": aq.get("hull", 0) if aq and aq["alive"] else 0,
            "speed": statistics.mean(speeds) if speeds else float("nan"), "engines": statistics.mean(engines) if engines else float("nan")}


def cmd_chase(a: argparse.Namespace) -> None:
    """The helm on a retreat (BATTAGLIA-3): the Mandate raiders are ordered to break off at --order-at; the same Captain's orders each time except the helm's."""
    seeds = list(range(1, a.seeds + 1))
    withdraw = f"{a.order_at}=astra.cmd group_order {{'side':'mandate','group':'all','order':'withdraw','by':'admiral'}}"
    variants = [("hold (the default: bow to the action)", "engage"), ("keep the bow on it", "bow"), ("hold 25 km (bow, throttle)", "standoff:25"),
                ("intercept, 25 km", "intercept:25"), ("intercept, 15 km", "intercept:15"),
                ("intercept, 15 km, aim at the engines", "intercept:15+aim:engines")]
    print(f"{'helm':<40} {'in reach%':>9} {'range now':>9} {'mean':>6} {'hull lost':>9} {'out':>4} {'Aquila':>7} {'speed':>6} {'engines':>8}")
    for name, script in variants:
        if a.only and a.only.lower() not in name.lower() and a.only.lower() not in script.lower():
            continue
        ns = argparse.Namespace(**vars(a))
        ns.scenario, ns.jump, ns.every, ns.views, ns.aquila, ns.aquila_opts, ns.holo_at = "chase_retreat", -1, 5, False, False, "", ""
        ns.at = join_at(withdraw, *captain_script(script))
        tag = f"{a.tag}_{script.replace(':', '')}"
        paths = seeds_run(ns, tag, a.exec, seeds, a.jobs)
        rows = [chase_of(load(p), a.order_at) for p in paths if p.exists()]
        rows = [r for r in rows if r]
        if not rows:
            print(f"{name:<40} (no records)")
            continue
        m = lambda k: statistics.mean(r[k] for r in rows)
        print(f"{name:<40} {100 * m('in_reach'):8.0f}% {m('range_end'):8.1f}k {m('range_mean'):5.1f}k {m('hull_lost'):8.0f}% {m('out'):4.1f} {m('aquila'):6.0f}% {m('speed'):5.0f}m {m('engines'):7.0f}%")
        sys.stdout.flush()


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
    with ThreadPoolExecutor(max(1, min(a.jobs, MAX_PROCESSES))) as pool:
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


def mind_python() -> str:
    """The Python of the mind's environment (mind/.venv): in this checkout, or in the main checkout when this is a worktree (the venv lives there)."""
    here = ROOT / "mind" / ".venv" / "bin" / "python"
    if here.exists():
        return str(here)
    for parent in ROOT.parents:                       # .../ASTRA/.claude/worktrees/<name>: the main checkout is the one with a mind/.venv above
        cand = parent / "mind" / ".venv" / "bin" / "python"
        if cand.exists():
            return str(cand)
    return sys.executable


def cmd_mind(a: argparse.Namespace) -> None:
    """The minds in the loop: mind/bench/war_arena.py in the mind's own environment (it launches the commandlet itself, at most two at once)."""
    rc = subprocess.call([mind_python(), "-m", "bench.war_arena", *a.rest], cwd=str(ROOT / "mind"))
    sys.exit(rc)


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


def cmd_groups(a: argparse.Namespace) -> None:
    """The battle groups through a record: state, order, formation, focus, range, strengths, and the ships' hull and shields."""
    d = load(a.path)
    names = {s["id"]: s["c"] for f in d["frames"] for s in f["ships"]}
    for i, f in enumerate(d["frames"]):
        if i % a.every:
            continue
        print(f"t={f['t']:6.1f}")
        for g in f.get("groups", []):
            foc = names.get(g["focus"], "-") if g["focus"] >= 0 else "-"
            print(f"   {g['side'][:3]} {g['name'][:24]:24} {g['state']:8} {g['order']:8} {g['formation']:6} {g['ships']} ships  focus {foc:8}"
                  f" range {g['range_m'] / 1000:4.1f} km  str {g['strength']:.2f} vs {g['enemy_strength']:.2f}  morale {g.get('morale', 0):.2f}"
                  + (f"  guide ({g['guide_km'][0]:6.1f},{g['guide_km'][1]:6.1f}) axis ({g['axis'][0]:5.2f},{g['axis'][1]:5.2f})" if "guide_km" in g else ""))
        for s in f["ships"]:
            if not s["craft"] and s["alive"] and s["side"] in ("astra", "mandate"):
                sh = " ".join(f"{v:3.0f}" for v in s.get("shields", []))
                print(f"        {s['c']:7} hull {s['hull']:3.0f}% sh [{sh}] mode {s['mode']} tgt {names.get(s['target'], '-'):8}"
                      f" ({s['km'][0]:6.1f},{s['km'][1]:6.1f}) {s['v']:4.0f} m/s{' FLEE' if s.get('fleeing') else ''}")


def cmd_views(a: argparse.Namespace) -> None:
    """What the minds are given of the groups (docs/GUERRA.md): one frame of a record made with --views, and the size of each side's part."""
    d = load(a.path)
    frames = [f for f in d["frames"] if "views" in f]
    if not frames:
        print("no views in this record: run with --views")
        return
    f = frames[min(len(frames) - 1, a.frame)] if a.frame >= 0 else frames[-1]
    for side in ("astra", "mandate"):
        v = f["views"][side]
        text = json.dumps(v, separators=(",", ":"))
        print(f"== t={f['t']:.0f}  {side}: {len(text)} bytes, {len(v['your_groups'])} own groups, {len(v['enemy_groups'])} enemy groups seen, {len(v['group_events'])} events")
        if a.full:
            print(json.dumps(v, indent=1))
    peak = max((len(json.dumps(fr["views"][s], separators=(",", ":"))), s, fr["t"]) for fr in frames for s in ("astra", "mandate"))
    print(f"largest view in the record: {peak[0]} bytes ({peak[1]}, t={peak[2]:.0f})")
    print("-- every group event in the record")
    seen = set()
    for fr in frames:
        for side in ("astra", "mandate"):
            for e in fr["views"][side]["group_events"]:
                key = (side, e["n"])
                if key not in seen:
                    seen.add(key)
                    print(f"  {fr['t'] - e['ago_s']:7.0f}  {side:8} #{e['n']:<3} {e['text']}")


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
    if len(sys.argv) > 1 and sys.argv[1] == "mind":
        cmd_mind(argparse.Namespace(rest=sys.argv[2:]))        # (the arena has options of its own: they go through untouched, `--help` included)
    ap = argparse.ArgumentParser(prog="war.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p: argparse.ArgumentParser, seconds: float = 900, jump: float | None = -1) -> None:
        p.add_argument("--seconds", type=float, default=seconds)
        p.add_argument("--jump", type=float, default=jump)
        p.add_argument("--step", type=float, default=0.1)
        p.add_argument("--every", type=float, default=10)
        p.add_argument("--scenario", default="")
        p.add_argument("--at", default="", help='commands at battle times: "200=astra.cmd ...|300=..."')
        p.add_argument("--script", default="", help="the Captain's orders for the Aquila, by name: engage | standoff:<km> | bow (tools/war.py CAPTAIN_SCRIPTS)")
        p.add_argument("--views", action="store_true", help="record the side views (your_groups, enemy_groups, group_events) in every frame")
        p.add_argument("--aquila", action="store_true", help="keep the Aquila in the scenario (at the origin, with the ASTRA side): the game's scale test from the bridge")
        p.add_argument("--aquila-opts", default="", help='the Aquila in the scenario, where and how ("at=-34,0,0;speed=0;heading=0": km, m/s, degrees; implies --aquila)')
        p.add_argument("--holo-at", default="", help='the holo table\'s plan at these battle times ("60,120"): Saved/War/holo_<t>.json, drawn by tools/art/holo_plan_preview.py')
        p.add_argument("--classes", default="", help="a class table (a copy of data/war/classes.json with other numbers) for this run, instead of the real one: tools/war.py classes writes the variants")

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
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--a", default="", help="exec for variant A")
    p.add_argument("--b", default="", help="exec for variant B")
    p.set_defaults(fn=cmd_ab)
    p = sub.add_parser("batch", help="one scenario over N seeds in parallel: a line per seed and the mean")
    common(p, 900, 160)
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--tag", default="batch")
    p.add_argument("--exec", default="")
    p.add_argument("--fight", action="store_true", help="after the batch, the fight log's measures (tools/war_fight.py)")
    p.set_defaults(fn=cmd_batch)
    p = sub.add_parser("sweep", help="what each behaviour is worth: switched off for the ASTRA side alone, in a symmetric scenario")
    common(p, 900, -1)
    p.add_argument("--seeds", type=int, default=48)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--features", default="flank,saturate,rotate,focus,retreat_ratio,wall")
    p.set_defaults(fn=cmd_sweep, exec="")
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
    p.add_argument("--jobs", type=int, default=2)
    p.set_defaults(fn=cmd_duel)
    p = sub.add_parser("mind", help="the minds in the loop: a battle in which the commanders' minds read what the game gives them and give orders (all options: mind/bench/war_arena.py --help)")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_mind)
    p = sub.add_parser("embed", help="write the ship class table compiled into the game from data/war/classes.json")
    p.set_defaults(fn=cmd_embed)
    p = sub.add_parser("report")
    p.add_argument("path")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("groups", help="the battle groups through a record")
    p.add_argument("path")
    p.add_argument("--every", type=int, default=3, help="every Nth frame")
    p.set_defaults(fn=cmd_groups)
    p = sub.add_parser("views", help="what the minds are given of the groups, from a record made with --views")
    p.add_argument("path")
    p.add_argument("--frame", type=int, default=-1)
    p.add_argument("--full", action="store_true")
    p.set_defaults(fn=cmd_views)
    p = sub.add_parser("ship")
    p.add_argument("path")
    p.add_argument("contact")
    p.set_defaults(fn=cmd_ship)
    p = sub.add_parser("suite", help="the battle suite of BATTAGLIA-3: duels, small fleets, the opening, the fleet battle: one line each over seeds")
    common(p, 900, -1)
    p.add_argument("--seeds", type=int, default=8)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--tag", default="suite")
    p.add_argument("--only", default="", help="a part of a battle's name or scenario")
    p.add_argument("--exec", default="")
    p.set_defaults(fn=cmd_suite)
    p = sub.add_parser("chase", help="the helm on a retreat: six ways of steering and aiming the Aquila after a Mandate force that is ordered to break off")
    common(p, 600, -1)
    p.add_argument("--seeds", type=int, default=6)
    p.add_argument("--jobs", type=int, default=2)
    p.add_argument("--tag", default="chase")
    p.add_argument("--order-at", dest="order_at", type=float, default=150.0, help="when the Mandate admiral orders the withdrawal (battle seconds)")
    p.add_argument("--only", default="")
    p.add_argument("--exec", default="")
    p.set_defaults(fn=cmd_chase)
    p = sub.add_parser("fight", help="what a battle was like to watch: continuity of the fire, accuracy by range, who killed whom, retreats, heat")
    p.add_argument("path", nargs="*")
    p.add_argument("--tag", default="batch")
    p.add_argument("--vs", default="")
    p.add_argument("--brief", action="store_true")
    p.set_defaults(fn=cmd_fight)
    p = sub.add_parser("classes", help="the class table under the bench: a variant of data/war/classes.json over a few scenarios (tools/war_classes.py)")
    p.add_argument("--small", default="", help="multipliers for vigilant, styx and lethe: cd, dmg, laser, mcd, hull, shield, regen (cd=0.85,regen=0.5)")
    p.add_argument("--mandate-small", dest="mandate_small", default="", help="the same for styx and lethe alone")
    p.add_argument("--acheron", default="", help="the same for the Acheron")
    p.add_argument("--aquila", default="", help="the same for the Aquila")
    p.add_argument("--missiles", default="", help="the cells of a class: acheron=48,styx=24")
    p.add_argument("--salvo", default="", help="the cells a class empties together in a massed salvo: acheron=8,styx=4")
    p.add_argument("--o13", default="", help="the battle times at which the vanguard, Constance and the 7th Fleet's main body arrive in o13: 230,350,440")
    p.add_argument("--scen", default="ss,st,op", help="ss (Styx v Styx) | sm (sym_small) | st (the Aquila v the strike group) | op (the opening) | o13 (the opening with the vanguard and the relief) | mb1 mb2 mb3 (the main body: the Aquila 8, 14, 20 km behind the line)")
    p.add_argument("--seeds", type=int, default=8)
    p.add_argument("--exec", default="", help="console commands for every run (astra.war.tune name value;...)")
    p.add_argument("--tag", default="cls")
    p.set_defaults(fn=cmd_classes)
    a = ap.parse_args()
    if getattr(a, "script", ""):
        a.at = join_at(getattr(a, "at", ""), *captain_script(a.script))
    a.fn(a)


if __name__ == "__main__":
    main()
