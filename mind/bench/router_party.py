"""How well does the comms officer's call (router.for_party: a small model) decide what goes out on an open channel?

    cd mind && .venv/bin/python -m bench.router_party [--sample N] [--seed S] [--out file.json]

The phrase sets (bench/router_set.py and bench/router_test*_set.py: typed and spoken, five languages, the playtest's words) carry
the right answer: for the crew only, for the party, or both. With a live channel each phrase goes to the model once; it is right
when words go out exactly when they should (and, for a mixed phrase, when the part for the party is among them). Prints accuracy by
kind and language, the wrong answers, latency (p50/p90/max) and cost; the spend goes to the ledger. With a muted channel or none,
nothing is asked: that is mechanics, not judgment."""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
import unicodedata

from astra_mind import router
from astra_mind.context import Channel, Context
from astra_mind.openrouter import OpenRouter, credits

from .router_set import ALL, Item
from .router_test2_set import TEST2
from .router_test3_set import TEST3
from .router_test4_set import TEST4
from .router_test_set import TEST

PARTY = {"enemy": ("T-23", "Ferryman Irina Vael (the Cocytus)", "enemy"), "fleet": ("fleet", "Vice Admiral Rourke and the 7th Fleet (ASN Praetorian, ASN Vigilant)", "fleet")}


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("’", "'")


def ctx_of(it: Item) -> Context:
    key = "fleet" if it.chan.startswith("fleet") else "enemy"
    party, name, kind = PARTY[key]
    ch = Channel(party=party, name=name, kind=kind, open=True, muted=False, heard_s=6.0 if it.chan in ("live", "fleet_live") else None,
                 screen=(it.facing == "viewscreen"))
    return Context(place="bridge", facing=it.facing, channel=ch, source="game")


def right(it: Item, out: str) -> bool:
    if it.dest == "crew":
        return not out
    if it.dest == "external":
        return bool(out)
    return bool(out) and (not it.ext or it.ext in norm(out))          # both: the party's part went out


async def main_async(args: argparse.Namespace) -> None:
    items = [it for it in ALL + TEST + TEST2 + TEST3 + TEST4 if it.chan not in ("none", "muted")]
    if args.sample and args.sample < len(items):
        items = random.Random(args.seed).sample(items, args.sample)
    llm = OpenRouter()
    before = await credits()
    rows = []
    for it in items:
        t0 = time.perf_counter()
        r = await router.for_party(llm, it.text, ctx_of(it))
        rows.append({"text": it.text, "lang": it.lang, "style": it.style, "want": it.dest, "out": r.external, "how": r.how,
                     "ok": right(it, r.external), "ms": (time.perf_counter() - t0) * 1000, "cost": r.cost, "hard": it.hard})
    ok = [r for r in rows if r["ok"]]
    print(f"{len(ok)}/{len(rows)} right ({100 * len(ok) / max(1, len(rows)):.1f} %)")
    for key in ("want", "lang", "style"):
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(str(r[key]), []).append(r)
        print(f"  by {key}: " + " · ".join(f"{k} {sum(x['ok'] for x in v)}/{len(v)}" for k, v in sorted(groups.items())))
    ms = sorted(r["ms"] for r in rows)
    print(f"latency p50 {ms[len(ms) // 2]:.0f} ms · p90 {ms[int(len(ms) * 0.9)]:.0f} ms · max {ms[-1]:.0f} ms · "
          f"cost {sum(r['cost'] for r in rows):.4f} $ ({statistics.mean(r['cost'] for r in rows) * 1000:.3f} m$ a call)")
    for r in rows:
        if not r["ok"]:
            print(f"  WRONG [{r['want']}] {r['text']!r} -> {r['out']!r} ({r['how']})")
    after = await credits()
    print(f"account delta {after['used'] - before['used']:.4f} $")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default="")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
