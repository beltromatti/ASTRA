"""What the router adds to the wait for the Captain's first answer, measured with the real model.

    cd mind && .venv/bin/python -m bench.router_latency

For words the rules settle the router costs ~0.05 ms. For the rare open case (a small model must decide) two ways are compared on
the same words: SEQUENTIAL (the router answers, then the crew starts: what the old code did) and GATED (the crew starts at once on the
words and nothing is said or done until the router has answered: what the mind does now). The time that counts is from the Captain's
words to the first line spoken. Each pair is run in turn, on a warm connection; the crew's answers are the same size in both."""
from __future__ import annotations

import asyncio
import statistics
import time

from astra_mind import models, router
from astra_mind.context import Channel, Context

from .stations_scenarios import Harness
from astra_mind.openrouter import OpenRouter

OPEN_CASES = [
    "che fanno adesso i nemici",
    "sarà una battaglia dura ma ce la faremo",
    "voglio sapere quanti sono",
    "ehi mi ricevete",
    "ritiriamoci con calma",
]


async def one(llm: OpenRouter, text: str, gated: bool) -> tuple[float, float]:
    """(seconds to the first line, the router's own seconds)."""
    h = Harness(llm, "it")
    ctx = Context(channel=Channel(party="T-23", name="Ferryman Irina Vael (the Cocytus)"))
    t0 = time.perf_counter()
    if gated:
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        turn_task = asyncio.create_task(h.agent.handle(text, "it", ctx, "", gate))
        r = await router.route_llm(llm, text, ctx)
        r_s = time.perf_counter() - t0
        gate.set_result(r is None or r.dest == "crew")
        turn = await turn_task
    else:
        r = await router.route_llm(llm, text, ctx)
        r_s = time.perf_counter() - t0
        turn = await h.agent.handle(text, "it", ctx)
    # t_first_line counts from the start of handle(): add what came before it (the router, when sequential)
    return ((r_s if not gated else 0.0) + (turn.t_first_line or turn.t_end), r_s) if not gated else (max(r_s, turn.t_first_line or turn.t_end), r_s)


async def main() -> None:
    models.LEDGER.cap = 0.385
    llm = OpenRouter()
    try:
        await one(llm, "warm up", True)
        seq, gat, rs = [], [], []
        for text in OPEN_CASES:
            a, r_s = await one(llm, text, False)
            b, _ = await one(llm, text, True)
            seq.append(a)
            gat.append(b)
            rs.append(r_s)
            print(f"{text!r:48s} sequential {a * 1000:5.0f} ms   gated {b * 1000:5.0f} ms   (router {r_s * 1000:4.0f} ms)")
        print(f"first line, median: sequential {statistics.median(seq) * 1000:.0f} ms, gated {statistics.median(gat) * 1000:.0f} ms; "
              f"router alone {statistics.median(rs) * 1000:.0f} ms — the gate hides {100 * (1 - statistics.median(gat) / statistics.median(seq)):.0f}% of the wait")
        print(models.LEDGER.summary())
    finally:
        await llm.close()


if __name__ == "__main__":
    asyncio.run(main())
