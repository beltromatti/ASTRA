"""Which model for which role: the crew (the Captain's turns), the watch (the officers' initiative) and the chatter (quiet moments).

    cd mind && .venv/bin/python -m bench.stations_models --role watch|chatter|crew [--only name,name] [--out file.json]

Each candidate serves ONE role at a time and is measured on the scenarios of bench/stations_scenarios.py that belong to it
(the watch: after a kill, a new contact, advise/manual; the crew: the order scenarios; the chatter: three quiet moments judged on
the language, the length and the speakers). Reports per candidate: checks passed, the time of the model's turn (median and worst),
the cost of a turn, errors. Every candidate is held to the project's rule: never above DeepSeek V4.1 Flash's price (the price ceiling
is sent with every request), one provider per request. The spend is in the ledger; the run stops at the work's spend cap."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, replace
from typing import Any

from astra_mind import initiative, models
from astra_mind.openrouter import OpenRouter, credits

from . import stations_scenarios as sc


@dataclass
class Cand:
    name: str
    model: str
    providers: tuple[str, ...] | None
    reasoning: tuple[tuple[str, Any], ...] | None = (("enabled", False),)
    max_tokens: int | None = None
    note: str = ""


CANDS = [
    Cand("deepseek-v4.1-flash@together", "deepseek/deepseek-v4.1-flash", ("together", "modal")),
    Cand("deepseek-v4.1-flash@wafer", "deepseek/deepseek-v4.1-flash", ("wafer",), note="same model, $0.08/0.44"),
    Cand("mistral-small-3.2@mistral", "mistralai/mistral-small-3.2-24b-instruct", ("mistral",), None),
    Cand("qwen3-30b-a3b-instruct@alibaba", "qwen/qwen3-30b-a3b-instruct-2507", ("alibaba",), None),
    Cand("gpt-oss-120b@crusoe", "openai/gpt-oss-120b", ("crusoe",), (("effort", "low"),), 700),
    Cand("ministral-8b@mistral", "mistralai/ministral-8b-2512", ("mistral",), None),
    Cand("gemma-3-12b@deepinfra", "google/gemma-3-12b-it", ("deepinfra",), None),
    Cand("ling-3.0-flash@novita", "inclusionai/ling-3.0-flash", ("novita",), None),
    Cand("qwen3.7-flash@alibaba", "qwen/qwen3.7-flash", ("alibaba",)),
]

WATCH_SCENARIOS = [sc.sc_initiative_after_a_kill, sc.sc_initiative_new_contact, sc.sc_delegation_advise]
CREW_SCENARIOS = [sc.sc_engage_until_it_falls, sc.sc_one_volley, sc.sc_follow_until_ordered, sc.sc_viewscreen, sc.sc_questions,
                  sc.sc_coordination]


def patch(role: str, cand: Cand) -> None:
    base = models.ROLES[role]
    models.ROLES[role] = replace(base, model=cand.model, providers=cand.providers, reasoning=cand.reasoning,
                                 max_tokens=cand.max_tokens or base.max_tokens, first_token_s=10.0)


async def quiet_moments(llm: OpenRouter) -> tuple[list[dict[str, Any]], float]:
    """Three quiet moments as the server asks for them, on a compact chatter prompt: (per moment: lines, checks), cost."""
    h = sc.Harness(llm, "it", fight=False)
    asks = [
        ("pair", "A quiet moment: helm and sensors exchange one or two short, natural lines about the Teal Veil outside the window, in "
                 "character, knowing the Captain can hear. No orders, no reports, no tools except speak; at most two lines in total."),
        ("personal", "A quiet moment. tactical turns to the Captain, off the record, with one short personal line: something that officer "
                     "has been meaning to say or ask, from how they stand with the Captain or from what the ship has lived through. "
                     "One line, human and specific, never a report; it invites an answer. Only speak, only that officer."),
        ("home", "A quiet moment. flight turns to the Captain, off the record: news from home has reached them (their sister on New "
                 "Ravenna is expecting a child). In one or two short human lines, in character, they tell the Captain. Only speak."),
    ]
    out, cost = [], 0.0
    for kind, ask in asks:
        system = initiative.chatter_system("it", "steady, a little tired after the last fight", "- Price knows the Captain's brother flies "
                                           "Falcons with the Third Fleet", "- Voss trusts the Captain since the Captain listened to her story",
                                           "- Price's sister on New Ravenna is expecting a child", ["the Aquila beat off a raid at Aurelia"],
                                           ["engagement over: Mandate raiders withdrew"])
        turn = await h.agent.handle_event("bridge: a quiet moment on watch", "it", ask=ask, role="chatter", system=system,
                                          history_turns=2, speak_only=True)
        cost += turn.cost
        lines = [(s, t) for s, t in turn.lines]
        ok = {"speaks": bool(lines), "short": all(len(t.split()) <= 30 for _, t in lines), "italian": all(sc.looks_like(t, "it") for _, t in lines if len(t.split()) >= 5),
              "no bare ack": not any(sc.is_bare_ack(t) for _, t in lines),
              "right speakers": (all(s in ("helm", "sensors") for s, _ in lines) if kind == "pair" else all(s == ("tactical" if kind == "personal" else "flight") for s, _ in lines)),
              "no action": not turn.actions}
        out.append({"kind": kind, "lines": lines, "checks": ok, "t": turn.t_end})
    return out, cost


async def run(role: str, cand: Cand, llm: OpenRouter) -> dict[str, Any]:
    saved = dict(models.ROLES)
    patch(role, cand)
    t0 = time.perf_counter()
    res: dict[str, Any] = {"cand": cand.name, "role": role}
    try:
        if role == "chatter":
            moments, cost = await quiet_moments(llm)
            checks = [ok for m in moments for ok in m["checks"].values()]
            res.update(checks_ok=sum(checks), checks=len(checks), cost=cost, turns=len(moments), moments=moments,
                       times=[m["t"] for m in moments])
        else:
            scenarios = WATCH_SCENARIOS if role == "watch" else CREW_SCENARIOS
            results = []
            for fn in scenarios:
                results.append(await fn(llm, "it"))
            turns = [t for r in results for t in r.turns if (t.kind == "event") == (role == "watch")]
            checks = [ok for r in results for _, ok, _ in r.checks]
            res.update(checks_ok=sum(checks), checks=len(checks), scenarios_ok=sum(1 for r in results if r.passed), scenarios=len(results),
                       cost=sum(r.cost for r in results), turns=len(turns), times=[t.t_end for t in turns],
                       first=[t.t_first_line for t in turns if t.t_first_line is not None],
                       failed=[(r.name, n, d[:160]) for r in results for n, ok, d in r.checks if not ok])
    except models.SpendCapReached:
        raise
    except Exception as exc:  # noqa: BLE001
        res.update(error=f"{type(exc).__name__}: {str(exc)[:160]}")
    finally:
        models.ROLES.update(saved)
    res["seconds"] = time.perf_counter() - t0
    return res


def fmt(res: dict[str, Any]) -> str:
    if "error" in res:
        return f"{res['cand']:36s} ERROR {res['error']}"
    ts = sorted(res.get("times") or [0])
    med = statistics.median(ts) * 1000
    cost = res["cost"] / max(1, res["turns"]) * 1000
    extra = f", scenarios {res['scenarios_ok']}/{res['scenarios']}" if "scenarios" in res else ""
    return (f"{res['cand']:36s} checks {res['checks_ok']}/{res['checks']}{extra}  turn p50 {med:5.0f} ms  max {ts[-1] * 1000:5.0f} ms  "
            f"{cost:6.3f} m$/turn  ({res['turns']} turns)")


async def main_async(args: argparse.Namespace) -> None:
    models.LEDGER.cap = 0.385
    before = await credits()
    llm = OpenRouter()
    results = []
    try:
        for cand in CANDS:
            if args.only and cand.name not in args.only.split(","):
                continue
            try:
                res = await run(args.role, cand, llm)
            except models.SpendCapReached as exc:
                print("STOP:", exc)
                break
            results.append(res)
            print(fmt(res), flush=True)
            for name, n, d in (res.get("failed") or [])[:6]:
                print(f"      x {name[:38]:38s} {n}: {d}")
            if args.role == "chatter":
                for m in res.get("moments", []):
                    bad = [k for k, v in m["checks"].items() if not v]
                    print(f"      {m['kind']:8s} {'ok ' if not bad else 'BAD ' + ','.join(bad)} " + " | ".join(f"{s}: {t}" for s, t in m["lines"]))
    finally:
        await llm.close()
    after = await credits()
    print(f"ledger: {models.LEDGER.summary()}; account delta {after['used'] - before['used']:.5f} $")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1, default=str)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True, choices=["watch", "chatter", "crew"])
    ap.add_argument("--only", default="")
    ap.add_argument("--out", default="")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
