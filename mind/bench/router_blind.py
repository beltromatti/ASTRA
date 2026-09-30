"""The whole router (rules, then the small model for what the rules leave open) on a labelled set, with the real model.

    cd mind && .venv/bin/python -m bench.router_blind [--set dev|playtest|test|test2|test3|test4|all] [-v]

The model is asked only about the words the rules cannot settle (about a fifth of unseen words, about 0.035 m$ per call), so a
whole set of ~150 utterances costs a tenth of a cent. Prints the accuracy of the pipeline as the mind runs it (rules, else model,
else the crew), the accuracy of the rules alone (unsettled -> crew), what the model alone would have scored on the same words,
its latency, and every mistake. Nothing here is tuned: use it on words the rules have never seen."""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

from astra_mind import models, router
from astra_mind.openrouter import OpenRouter

from .router_eval import make_ctx
from .router_set import ALL, DEV, PLAYTEST, Item
from .router_test2_set import TEST2
from .router_test3_set import TEST3
from .router_test4_set import TEST4
from .router_test_set import TEST


async def one(llm: OpenRouter, it: Item) -> tuple[str, str, float, str | None]:
    """(destination, how, model seconds, the model's own label); how = rules | model | fallback."""
    ctx = make_ctx(it)
    r = router.quick(it.text, ctx)
    if r is not None:
        return r.dest, "rules", 0.0, None
    t0 = time.perf_counter()
    label, _, _ = await router.classify(llm, it.text, ctx)
    dt = time.perf_counter() - t0
    if label is None:
        return "crew", "fallback", dt, None
    dest = {"crew": "crew", "party": "external", "mixed": "both"}[label]
    return dest, "model", dt, label


async def main_async(args: argparse.Namespace) -> None:
    from .router_eval import predicted
    sets = {"dev": DEV, "playtest": PLAYTEST, "test": TEST, "test2": TEST2, "test3": TEST3, "test4": TEST4, "all": ALL + TEST + TEST2 + TEST3 + TEST4}
    items = sets[args.set]
    models.LEDGER.cap = 0.385
    llm = OpenRouter()
    try:
        results = [await one(llm, it) for it in items]           # (one at a time: the latency figures are the router's own)
    finally:
        await llm.close()
    n = len(items)
    pipe = sum(1 for it, r in zip(items, results) if r[0] == it.dest)
    rules_only = sum(1 for it in items if ("crew" if predicted(it)[0] == "unsure" else predicted(it)[0]) == it.dest)
    settled = [(it, r) for it, r in zip(items, results) if r[1] == "rules"]
    modelled = [(it, r) for it, r in zip(items, results) if r[1] != "rules"]
    print(f"=== {args.set}: {n} utterances")
    print(f"    rules alone (unsettled -> crew): {rules_only}/{n} ({100 * rules_only / n:.1f}%)")
    print(f"    settled by the rules: {len(settled)}/{n} ({100 * len(settled) / n:.0f}%), right: {sum(1 for it, r in settled if r[0] == it.dest)}/{len(settled)}")
    if modelled:
        ok_m = sum(1 for it, r in modelled if r[0] == it.dest)
        lat = sorted(r[2] for _, r in modelled if r[1] == "model")
        print(f"    left to the model: {len(modelled)}, right: {ok_m}/{len(modelled)}"
              + (f"; latency p50 {statistics.median(lat) * 1000:.0f} ms, max {lat[-1] * 1000:.0f} ms" if lat else ""))
    print(f"    the whole pipeline: {pipe}/{n} ({100 * pipe / n:.1f}%)")
    crew_to_party = [it for it, r in zip(items, results) if it.dest == "crew" and r[0] in ("external", "both")]
    print(f"    crew words sent to the party (the costly mistake): {len(crew_to_party)}")
    for it, r in zip(items, results):
        if r[0] != it.dest:
            print(f"    WRONG [{it.lang}/{it.style}/{it.chan}{'/hard' if it.hard else ''}] {it.text!r}: wanted {it.dest}, got {r[0]} ({r[1]})")
        elif args.verbose and r[1] != "rules":
            print(f"    model ok [{it.lang}/{it.chan}] {it.text!r} -> {r[3]}")
    print("    " + models.LEDGER.summary())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="test3", choices=["dev", "playtest", "test", "test2", "test3", "test4", "all"])
    ap.add_argument("-v", "--verbose", action="store_true")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
