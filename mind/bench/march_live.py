"""A war of the March played by the two high commands' minds, the war's hours run in seconds (docs/GUERRA.md §10).

    cd mind && .venv/bin/python -m bench.march_live --hours 1.0 --seed 3 --cap 0.05            (live: the real model, its cost counted; needs the key in the environment)
    cd mind && .venv/bin/python -m bench.march_live --hours 4 --seed 3 --mock                    (offline: a scripted model that gives the reflexes' orders: the plumbing and the war)

The March runs in steps of a few seconds; whenever a mind is due it looks (the war waits while it thinks: a look takes seconds, the cadence is minutes), the orders go through the
tools, the fleets move. What is reported: every look (when, who, why, what it ordered, what it cost), at the end the cost by the hour (the budget of the layer is 0.1 $ an hour),
the latency of a look, the war's state, and what the minds' decisions did to it. `--trace FILE` keeps every look's prompts and answer for reading."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind import models  # noqa: E402
from astra_mind.march import SIDES, March, fmt_s  # noqa: E402
from astra_mind.march_auto import AutoAdmiral  # noqa: E402
from astra_mind.strategy import StrategicMinds  # noqa: E402
from astra_mind.war import WarMap  # noqa: E402

models.LEDGER.write_file = False


def reflex_policy(seat: Any, march: March, side: str, tools: list[str], messages: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """What the reflexes would do, given through the tools (a stand-in that exercises the plumbing and plays a war: it is not a model)."""
    a = AutoAdmiral(march, side, "full")
    before = {f.id: (f.order.kind, f.order.target, f.order.by) for f in march.side_fleets(side)}
    a.think()
    out: list[tuple[str, dict[str, Any]]] = []
    for f in march.side_fleets(side):
        now = (f.order.kind, f.order.target, f.order.by)
        if now != before.get(f.id) and f.order.by == "auto":
            out.append(("fleet_order", {"fleet": f.id, "order": f.order.kind, "target": f.order.target, "reason": f.order.reason or "the usual"}))
    return out or [("no_change", {"reason": "the orders stand"})]


async def play(hours: float, seed: int, mock: bool, cap: float, trace: Path | None, quiet: bool, journal: bool = False) -> dict[str, Any]:
    wm = WarMap()
    wm.persist = False
    m = March(wm, seed=seed)
    m.fleets["F-A2"].tactical_command = ""                       # (no game: the map plays the opening's fleets too, on the script's own clock)
    if mock:
        from bench.march_mock import StrategyMock
        llm: Any = StrategyMock(reflex_policy, latency=0.0, cost=0.0016)
    else:
        from astra_mind.openrouter import OpenRouter
        llm = OpenRouter()
    said: list[str] = []

    async def say(speaker: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        said.append(f"{speaker}: {text}")

    out_trace = trace.open("w", encoding="utf-8") if trace else None

    def keep(rec: dict[str, Any]) -> None:
        if not quiet:
            print(f"  {fmt_s(rec['t']):>10}  {rec['who'].split()[-1]:<9} {rec['latency']:5.1f}s ${rec['cost']:.4f}  [{'; '.join(rec['why'])[:48]}]  " + " | ".join(rec["tools"])[:150], flush=True)
        if out_trace is not None:
            out_trace.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_trace.flush()
    sm = StrategicMinds(llm, m, say, lang=lambda: "en", trace=keep)
    end = hours * 3600.0
    t0 = time.perf_counter()
    while m.t < end and not m.over:
        m.run(5.0)
        sm.feed({})
        busy = [s.task for s in sm.seats.values() if s.busy and s.task is not None]
        if busy:
            await asyncio.wait(busy)
        if sm.summary()["cost"] >= cap:
            print(f"the cost cap of {cap:.3f} $ is reached at {fmt_s(m.t)}: stopped", flush=True)
            break
    wall = time.perf_counter() - t0
    if out_trace is not None:
        out_trace.close()
    s = sm.summary()
    owners = {k: m.owner(k) for k in m.sys}
    held = {side: sorted(k for k, o in owners.items() if o == side) for side in SIDES}
    if journal:
        for side in SIDES:
            print(f"\n--- {side}'s log ---\n" + sm.recall(side, 60))
    return {"war_time": m.clock(), "wall_s": round(wall, 1), "over": m.over.get("why", "") if m.over else "", "held": held, "will": {x: round(m.will[x], 2) for x in SIDES},
            "score": m.score, "summary": s, "said": said[-5:], "plans": m.plans, "orders": {x: [e for e in sm.logs[x]][-12:] for x in SIDES}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=1.0)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--mock", action="store_true", help="a scripted model, no network and no cost")
    ap.add_argument("--cap", type=float, default=0.06, help="stop when the layer has cost this much ($)")
    ap.add_argument("--trace", default="", help="a file for every look's prompts and answer")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--journal", action="store_true", help="print each high command's log of what it decided at the end")
    a = ap.parse_args()
    res = asyncio.run(play(a.hours, a.seed, a.mock, a.cap, Path(a.trace) if a.trace else None, a.quiet, a.journal))
    s = res["summary"]
    print(f"\nthe war at {res['war_time']} ({res['wall_s']} s of work): {'OVER: ' + res['over'] if res['over'] else 'goes on'}")
    for side in SIDES:
        print(f"  {side:8} holds {', '.join(res['held'][side]) or '-'}; will {res['will'][side]}; lost {res['score'][side]['ships_lost']} ships, killed {res['score'][side]['ships_killed']}, "
              f"took {res['score'][side]['systems_taken']} systems")
    print(f"the layer: {s['pulses']} looks, {s['cost']:.4f} $ in {s['span_s'] / 3600:.2f} war-hours = {s['cost_per_hour']:.4f} $/h (budget 0.1), {s['cost_per_pulse']:.4f} $ a look; "
          f"latency median {s['latency_median']} s p90 {s['latency_p90']} s; orders {s['orders_ok']} ok {s['orders_failed']} refused; errors {s['errors']}; "
          f"tokens in {s['tokens_in']} out {s['tokens_out']}")
    for side in SIDES:
        st = s["by_side"][side]
        print(f"  {side:8} {int(st['pulses'])} looks, {int(st['no_change'])} of them 'no change', {int(st['orders'])} orders, plan: {res['plans'][side][:160]}")


if __name__ == "__main__":
    main()
