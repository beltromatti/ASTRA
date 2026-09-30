"""Which small model should settle what the router's rules leave open (and how good is a model on its own)?

    cd mind && .venv/bin/python -m bench.router_models [--only name,name] [--sample N] [--full] [--out file.json]

For every candidate model: the words the rules cannot settle (all sets) plus a stratified sample of the ones they settle (the
model's own accuracy where the rules are sure), asked one by one, timed, costed. Prints per model: accuracy on the open part and
on the sample, the whole pipeline's accuracy (rules where sure, model where not; a model that errors leaves the words with the
crew), latency p50/p90/max and the cost of a call. `--full` runs the model over every utterance (the model alone, no rules).
The spend is added to the ledger (mind/.cache/spend.jsonl) and printed at the end."""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
from dataclasses import dataclass

from astra_mind import models, router
from astra_mind.openrouter import OpenRouter, credits

from .router_eval import make_ctx
from .router_set import ALL, Item
from .router_test2_set import TEST2
from .router_test_set import TEST


@dataclass
class Cand:
    name: str
    model: str
    providers: tuple[str, ...] | None
    reasoning: tuple[tuple[str, object], ...] | None = (("enabled", False),)
    max_tokens: int = 12
    note: str = ""


CANDS = [
    Cand("deepseek-v4.1-flash@together", "deepseek/deepseek-v4.1-flash", ("together",)),
    Cand("gpt-oss-20b@coreweave", "openai/gpt-oss-20b", ("coreweave",), (("effort", "low"),), 220),
    Cand("gpt-oss-120b@crusoe", "openai/gpt-oss-120b", ("crusoe",), (("effort", "low"),), 220),
    Cand("llama-3.1-8b@groq", "meta-llama/llama-3.1-8b-instruct", ("groq",), None),
    Cand("ministral-8b@mistral", "mistralai/ministral-8b-2512", ("mistral",), None),
    Cand("qwen3-30b-a3b-instruct@alibaba", "qwen/qwen3-30b-a3b-instruct-2507", ("alibaba",), None),
    Cand("gemini-2.5-flash-lite@aistudio", "google/gemini-2.5-flash-lite", ("google-ai-studio",), (("enabled", False),)),
    Cand("nova-micro@bedrock", "amazon/nova-micro-v1", ("amazon-bedrock",), None),
    Cand("mistral-small-3.2@mistral", "mistralai/mistral-small-3.2-24b-instruct", ("mistral",), None),
    Cand("gpt-4.1-nano@openai", "openai/gpt-4.1-nano", ("openai",), None),
    Cand("nemotron-3.5-lightning@coreweave", "nvidia/nemotron-3.5-lightning", ("coreweave",), (("enabled", False),)),
    Cand("gemma-3-12b@deepinfra", "google/gemma-3-12b-it", ("deepinfra",), None),
]


def gold_label(it: Item) -> str:
    return {"crew": "crew", "external": "party", "both": "mixed"}[it.dest]


def as_dest(label: str | None) -> str:
    return {"crew": "crew", "party": "external", "mixed": "both"}.get(label or "", "crew")


async def run(cand: Cand, items: list[Item], llm: OpenRouter) -> dict:
    over = dict(model=cand.model, providers=list(cand.providers) if cand.providers else None,
                reasoning=dict(cand.reasoning) if cand.reasoning else None, max_tokens=cand.max_tokens, first_token_s=6.0)
    rows = []
    # warm-up (the connection and the provider's cache), not counted
    await router.classify(llm, "fuoco a volonta", make_ctx(items[0]), **over)
    for it in items:
        label, dt, cost = await router.classify(llm, it.text, make_ctx(it), **over)
        rows.append({"text": it.text, "lang": it.lang, "chan": it.chan, "gold": gold_label(it), "label": label, "s": dt, "cost": cost,
                     "hard": it.hard})
    return {"cand": cand.name, "rows": rows}


def summarise(res: dict, open_texts: set[tuple[str, str]], rules_ok: dict[tuple[str, str], bool], n_all: int, n_rules_ok: int) -> str:
    rows = res["rows"]
    open_rows = [r for r in rows if (r["text"], r["chan"]) in open_texts]
    samp_rows = [r for r in rows if (r["text"], r["chan"]) not in open_texts]

    def acc(rs: list[dict]) -> str:
        if not rs:
            return "—"
        ok = sum(1 for r in rs if r["label"] == r["gold"])
        return f"{ok}/{len(rs)} ({100 * ok / len(rs):.0f}%)"

    lat = sorted(r["s"] for r in rows if r["label"] is not None)
    errs = sum(1 for r in rows if r["label"] is None)
    p = lambda q: lat[min(len(lat) - 1, int(q * (len(lat) - 1) + 0.5))] * 1000 if lat else float("nan")   # noqa: E731
    open_ok = sum(1 for r in open_rows if r["label"] == r["gold"])
    pipeline = (n_rules_ok + open_ok) / n_all
    cost = sum(r["cost"] for r in rows) / max(1, len(rows))
    return (f"{res['cand']:36s} open {acc(open_rows):14s} sample {acc(samp_rows):14s} pipeline {100 * pipeline:5.1f}%  "
            f"p50 {p(0.5):5.0f} ms  p90 {p(0.9):5.0f} ms  max {lat[-1] * 1000 if lat else float('nan'):5.0f} ms  "
            f"errors {errs}  {cost * 1e6:6.1f} u$/call")


async def main_async(args: argparse.Namespace) -> None:
    items_all = ALL + TEST + TEST2
    open_items, settled = [], []
    rules_ok: dict[tuple[str, str], bool] = {}
    n_rules_ok = 0
    for it in items_all:
        r = router.quick(it.text, make_ctx(it))
        if r is None:
            open_items.append(it)
        else:
            settled.append(it)
            rules_ok[(it.text, it.chan)] = r.dest == it.dest
            n_rules_ok += r.dest == it.dest
    rng = random.Random(7)
    # a sample of what the rules settle: mostly the hard side (words for the party), and crew orders, with a channel open
    ext_pool = [i for i in settled if i.dest != "crew" and i.chan in ("enemy", "live", "fleet", "fleet_live")]
    crew_pool = [i for i in settled if i.dest == "crew" and i.chan in ("enemy", "live", "fleet", "fleet_live")]
    sample = rng.sample(ext_pool, min(len(ext_pool), args.sample // 2)) + rng.sample(crew_pool, min(len(crew_pool), args.sample // 2))
    items = items_all if args.full else open_items + sample
    open_keys = {(i.text, i.chan) for i in open_items}
    print(f"{len(items_all)} utterances: rules settle {len(settled)} ({n_rules_ok} right), leave {len(open_items)} open; "
          f"asking each model about {len(items)}")
    before = await credits()
    llm = OpenRouter()
    results = []
    try:
        for cand in CANDS:
            if args.only and cand.name not in args.only.split(","):
                continue
            t0 = time.perf_counter()
            try:
                res = await run(cand, items, llm)
            except Exception as exc:  # noqa: BLE001
                print(f"{cand.name:36s} FAILED: {type(exc).__name__}: {str(exc)[:100]}")
                continue
            results.append(res)
            print(summarise(res, open_keys, rules_ok, len(items_all), n_rules_ok), f" [{time.perf_counter() - t0:.0f} s]", flush=True)
            if args.errors:
                for r in res["rows"]:
                    if r["label"] != r["gold"]:
                        print(f"      wrong: {r['text']!r} [{r['chan']}] wanted {r['gold']}, said {r['label']}")
    finally:
        await llm.close()
    after = await credits()
    print(f"ledger: {models.LEDGER.summary()}; account delta {after['used'] - before['used']:.5f} $")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--sample", type=int, default=30)
    ap.add_argument("--full", action="store_true", help="every utterance, the model alone")
    ap.add_argument("--out", default="")
    ap.add_argument("--errors", action="store_true", help="list each model's mistakes")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
