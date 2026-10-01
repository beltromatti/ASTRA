"""The war bench with the minds in the loop (docs/GUERRA.md §8): the headless battle (commandlet AstraWarSim, no graphics) stops every second of
battle time and hands the minds what the game would hand them; the commands they give run in the battle with the game's own `ApplyCommand`,
their results come back, and the battle goes on — as fast as it can while nobody is thinking, at the pace of the game while a model is (the
world does not wait for a model that takes seconds).

    cd mind && .venv/bin/python -m bench.war_arena --scenario sym_small --seed 1 --seconds 420 --minds mandate --model close
    cd mind && .venv/bin/python -m bench.war_arena --scenario sym_medium --seeds 1-8 --minds astra --model live --budget 0.15
    cd mind && .venv/bin/python -m bench.war_arena --opening --jump 160 --seconds 600 --minds both --model live     (the Aurelia opening)

--minds  which side(s) have minds (`mandate`, `astra`, `both`, `none`: the other side runs on its reflexes);
--model  `null` (a mind that never orders), `close` (a plain scripted commander: the orders interface used sensibly), `live` (the real model,
         through OpenRouter: costs money, `--budget` stops the bench at a spend);
Output: Saved/War/<tag>_<seed>.json (the commandlet's record), <tag>_<seed>.mind.json (the pulses with prompts and replies, the orders and their
results, the allied captains' lines, the costs and latencies)."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind import models, war_minds  # noqa: E402
from astra_mind.enemy import COMMANDERS  # noqa: E402

ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")
WAR = ROOT / "Saved" / "War"
MAX_PROCESSES = 2                                       # engine processes at once (each is ~1.5 GB; the machine is shared)
log = logging.getLogger("astra.arena")


class Done(Exception):
    """The battle is over (or the commandlet is gone)."""


def _war_tool():
    """tools/war.py (the bench's reader of records): imported by path, it is not a package."""
    spec = importlib.util.spec_from_file_location("astra_war_tool", ROOT / "tools" / "war.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Link:
    """The game as the minds see it: commands queue until the next exchange; their results come back with a later state."""

    def __init__(self) -> None:
        self.n = 0
        self.out: list[dict[str, Any]] = []
        self.waiting: dict[str, asyncio.Future] = {}
        self.orders: list[dict[str, Any]] = []         # every command with its result (the bench's evidence)
        self.t = 0.0

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.n += 1
        cid = f"m{self.n}"
        fut = asyncio.get_running_loop().create_future()
        self.waiting[cid] = fut
        self.out.append({"id": cid, "name": name, "args": args, "by": by})
        rec = {"t": round(self.t, 1), "name": name, "args": args, "by": by}
        self.orders.append(rec)
        try:
            res = await asyncio.wait_for(fut, timeout=30.0)
        except asyncio.TimeoutError:
            res = {"ok": False, "detail": "no answer from the battle"}
        rec.update(ok=res["ok"], detail=res["detail"], answered_at=round(self.t, 1))
        return res

    def resolve(self, results: list[dict[str, Any]]) -> None:
        for r in results:
            fut = self.waiting.pop(r.get("id", ""), None)
            if fut is not None and not fut.done():
                fut.set_result({"ok": bool(r.get("ok")), "detail": str(r.get("detail", ""))})


def mandate_persona(first: list[str]):
    """The bench's Mandate captains: the first ship the admiral's seat sees is Archon Solm's, the others generic."""
    def lookup(contact: str) -> dict[str, Any] | None:
        if not first:
            first.append(contact)
        if contact == first[0]:
            return {**COMMANDERS["T-21"], "ship": "the Mandate flagship"}
        return None
    return lookup


def build_llm(model: str, latency: float, live_budget: float | None):
    models.LEDGER.write_file = model == "live"
    if model == "live":
        from astra_mind.openrouter import OpenRouter
        models.LEDGER.cap = live_budget
        return OpenRouter()
    sys.path.insert(0, str(ROOT / "mind"))
    from bench import war_mock
    return war_mock.MockLLM(war_mock.close_policy() if model == "close" else war_mock.null_policy, latency=latency)


async def run_battle(a: argparse.Namespace, seed: int, tag: str) -> dict[str, Any]:
    WAR.mkdir(parents=True, exist_ok=True)
    mdir = WAR / f"{tag}_{seed}_mind"
    if mdir.exists():
        for f in mdir.glob("*"):
            f.unlink()
    mdir.mkdir(parents=True, exist_ok=True)
    out = WAR / f"{tag}_{seed}.json"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={a.seconds}", "-step=0.1", f"-every={a.every}", f"-out={out}",
            "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput", f"-seed={seed}",
            f"-mind={mdir}", f"-mind_dt={a.dt}", f"-mind_speed={a.speed}", "-mind_timeout=120"]
    if a.scenario and not a.opening:
        args.append(f"-scenario={a.scenario}")
    if a.opening and a.jump is not None:
        args.append(f"-jump={a.jump}")
    if a.exec:
        args.append(f"-exec={a.exec}")
    logf = open(WAR / f"{tag}_{seed}.log", "w")
    proc = await asyncio.create_subprocess_exec(*args, stdout=logf, stderr=subprocess.STDOUT, cwd=str(ROOT))
    link = Link()
    sides = ("mandate", "astra") if a.minds == "both" else (() if a.minds == "none" else (a.minds,))
    llm = build_llm(a.model, a.latency, a.budget)
    lines: list[dict[str, Any]] = []
    pulses: list[dict[str, Any]] = []
    clock = {"t": 0.0}
    first: list[str] = []

    async def say(speaker: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        lines.append({"t": round(clock["t"], 1), "speaker": speaker, "text": text, "tone": tone, **{k: v for k, v in kw.items() if k in ("urgent", "answer", "topic")}})

    minds = war_minds.WarMinds(llm, say, link.execute, clock=lambda: clock["t"], mandate_persona=mandate_persona(first), sides=sides,
                               astra_admiral=a.astra_admiral and not a.opening, trace=pulses.append)
    k, t0, decided_at = 0, time.time(), None
    final_counts: dict[str, Any] = {}
    try:
        while True:
            path = mdir / f"s_{k}.json"
            while not path.exists():
                if proc.returncode is not None or time.time() - t0 > a.wall_limit:
                    raise Done()
                await asyncio.sleep(0.002)
            try:
                data = json.loads(path.read_text())
            except ValueError:
                await asyncio.sleep(0.01)
                continue
            path.unlink()
            clock["t"] = link.t = float(data["t"])
            link.resolve(data.get("results") or [])
            final_counts = data.get("counts", {})
            minds.feed(data["state"])
            await asyncio.sleep(0)
            busy = any(m.busy for m in minds.minds.values())
            stop = False
            c = final_counts
            if c and (c["astra"]["warships"] == 0 or c["mandate"]["warships"] == 0):
                decided_at = decided_at if decided_at is not None else clock["t"]
                stop = clock["t"] - decided_at > 3.0 and not busy
            cmds, link.out = link.out, []
            tmp = mdir / f"r_{k}.json.tmp"
            tmp.write_text(json.dumps({"commands": cmds, "thinking": busy or bool(cmds), "stop": stop}))
            tmp.rename(mdir / f"r_{k}.json")
            k += 1
            if stop:
                break
    except Done:
        pass
    finally:
        for m in minds.minds.values():
            if m.busy:
                m.task.cancel()
        await asyncio.sleep(0.05)
        try:
            await asyncio.wait_for(proc.wait(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
        logf.close()
        if hasattr(llm, "close"):
            await llm.close()
    war = _war_tool()
    result: dict[str, Any] = {"seed": seed, "counts": final_counts, "exchanges": k, "wall_s": round(time.time() - t0, 1)}
    if out.exists():
        m = war.metrics(out)
        result.update(battle_s=m["t"], astra=m["astra"], mandate=m["mandate"],
                      edge=(m["astra"]["alive"] + m["astra"]["gone"]) - (m["mandate"]["alive"] + m["mandate"]["gone"]), aquila=m["aquila"])
    result["minds"] = minds.summary()
    (WAR / f"{tag}_{seed}.mind.json").write_text(json.dumps({"result": result, "pulses": pulses, "orders": link.orders, "lines": lines}, indent=1, default=str))
    return result


def parse_seeds(text: str) -> list[int]:
    if "-" in text:
        lo, hi = text.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in text.split(",")]


async def main_async(a: argparse.Namespace) -> None:
    seeds = parse_seeds(a.seeds)
    tag = a.tag or f"mind_{a.scenario if not a.opening else 'opening'}_{a.minds}_{a.model}"
    sem = asyncio.Semaphore(MAX_PROCESSES)
    rows: list[dict[str, Any]] = []

    async def one(seed: int) -> None:
        async with sem:
            r = await run_battle(a, seed, tag)
            rows.append(r)
            ms = r["minds"]
            print(f"  seed {seed:>3}  edge {r.get('edge', '?'):>+}  astra {r.get('astra', {}).get('alive', '?')}/{r.get('astra', {}).get('n', '?')}  "
                  f"mandate {r.get('mandate', {}).get('alive', '?')}/{r.get('mandate', {}).get('n', '?')}  battle {r.get('battle_s', 0):.0f} s in {r['wall_s']} s  "
                  f"pulses {ms['pulses']} (errors {ms['errors']}) ${ms['cost']:.4f}  orders ok/failed {ms['orders_ok']}/{ms['orders_failed']}  "
                  f"latency median {ms['latency_median']:.1f} s", flush=True)

    await asyncio.gather(*(one(s) for s in seeds))
    rows.sort(key=lambda r: r["seed"])
    edges = [r["edge"] for r in rows if "edge" in r]
    if edges:
        se = statistics.pstdev(edges) / (len(edges) ** 0.5) if len(edges) > 1 else 0.0
        print(f"== {tag}: ASTRA ahead {sum(e > 0 for e in edges)}, Mandate ahead {sum(e < 0 for e in edges)}, level {sum(e == 0 for e in edges)}; "
              f"survivors edge (ASTRA minus Mandate) {statistics.mean(edges):+.2f} ± {se:.2f}; spent ${sum(r['minds']['cost'] for r in rows):.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="war_arena", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="sym_small")
    ap.add_argument("--opening", action="store_true", help="the Aurelia opening (Aquila, Praetorian, Vigilant against the strike group) instead of a scenario")
    ap.add_argument("--jump", type=float, default=160.0, help="opening: the battle clock to start from (the strike group arrives at 170)")
    ap.add_argument("--seeds", default="1")
    ap.add_argument("--seconds", type=float, default=420.0)
    ap.add_argument("--every", type=float, default=10.0)
    ap.add_argument("--minds", choices=("mandate", "astra", "both", "none"), default="mandate")
    ap.add_argument("--astra-admiral", action="store_true", help="ASTRA's mind is an admiral over all its groups (the Captain's fleet command), as the Mandate's is")
    ap.add_argument("--model", choices=("null", "close", "live"), default="close")
    ap.add_argument("--latency", type=float, default=0.3, help="scripted models: seconds each call takes")
    ap.add_argument("--budget", type=float, default=0.3, help="live: stop spending at this many dollars (all the log holds plus this run)")
    ap.add_argument("--dt", type=float, default=0.5, help="battle seconds between exchanges")
    ap.add_argument("--speed", type=float, default=1.0, help="pace of the battle while a mind thinks (1 = the game's)")
    ap.add_argument("--wall-limit", type=float, default=3600.0)
    ap.add_argument("--exec", default="")
    ap.add_argument("--tag", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(asctime)s %(name)s %(message)s")
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
