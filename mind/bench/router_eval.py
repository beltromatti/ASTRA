"""Measure the router's rules on the labelled sets (no model, no cost).

    cd mind && .venv/bin/python -m bench.router_eval [--set dev|playtest|test|all] [-v]

Reports, per set and per language / style / channel: how many of the words the rules settle by themselves, and how many of
those they settle correctly; and — counting the words left to the model as the safe default (the crew) — the accuracy of the
whole decision crew | external | both. The rules-only figure is the floor: the model only ever improves the unsettled part.
"""
from __future__ import annotations

import argparse
import collections
import time

from astra_mind import router
from astra_mind.context import Channel, Context

from .router_set import ALL, DEV, PLAYTEST, Item

PARTY = {"enemy": ("T-23", "Ferryman Irina Vael (the Cocytus)", "enemy"), "fleet": ("fleet", "Vice Admiral Adrian Rourke (7th Fleet)", "fleet")}


def make_ctx(it: Item) -> Context:
    ch = None
    if it.chan != "none":
        key = "fleet" if it.chan.startswith("fleet") else "enemy"
        party, name, kind = PARTY[key]
        ch = Channel(party=party, name=name, kind=kind, open=True, muted=(it.chan == "muted"),
                     heard_s=6.0 if it.chan in ("live", "fleet_live") else None, screen=(it.facing == "viewscreen"))
    return Context(place="bridge", facing=it.facing, channel=ch, source="game")


def predicted(it: Item) -> tuple[str, str, router.Route | None]:
    """(destination, how, route): the rules' answer, or 'unsure' when only a model can tell."""
    r = router.quick(it.text, make_ctx(it))
    if r is None:
        return "unsure", "model", None
    return r.dest, r.how, r


def split_ok(it: Item, r: router.Route) -> bool:
    if it.dest != "both":
        return True
    n = router.norm
    return (not it.ext or it.ext in n(r.external)) and (not it.crew or it.crew in n(r.crew))


def evaluate(items: list[Item], verbose: bool = False, title: str = "") -> dict:
    t0 = time.perf_counter()
    rows = []
    for it in items:
        dest, how, r = predicted(it)
        eff = "crew" if dest == "unsure" else dest
        ok = eff == it.dest and (r is None or split_ok(it, r))
        rows.append((it, dest, ok))
    dt = (time.perf_counter() - t0) / max(1, len(items)) * 1000
    n = len(rows)
    settled = [r for r in rows if r[1] != "unsure"]
    print(f"\n=== {title or 'set'}: {n} utterances, rules ~{dt:.3f} ms each")
    print(f"    settled by the rules: {len(settled)}/{n} ({100 * len(settled) / n:.0f}%), correct among them: "
          f"{sum(1 for r in settled if r[2])}/{len(settled)} ({100 * sum(1 for r in settled if r[2]) / max(1, len(settled)):.1f}%)")
    print(f"    whole decision, unsettled -> crew: {sum(1 for r in rows if r[2])}/{n} ({100 * sum(1 for r in rows if r[2]) / n:.1f}%)")
    facets: dict[str, collections.Counter] = {"lang": collections.Counter(), "style": collections.Counter(), "chan": collections.Counter(),
                                              "dest": collections.Counter(), "hard": collections.Counter()}
    facets_ok: dict[str, collections.Counter] = {k: collections.Counter() for k in facets}
    for it, dest, ok in rows:
        for k, v in (("lang", it.lang), ("style", it.style), ("chan", it.chan), ("dest", it.dest), ("hard", "hard" if it.hard else "clear")):
            facets[k][v] += 1
            facets_ok[k][v] += ok
    for k in facets:
        print("    " + k + ": " + ", ".join(f"{v} {facets_ok[k][v]}/{facets[k][v]}" for v in sorted(facets[k])))
    bad = [r for r in rows if not r[2]]
    unsettled = [r for r in rows if r[1] == "unsure"]
    if bad:
        print(f"  WRONG ({len(bad)}):")
        for it, dest, _ in bad:
            print(f"    [{it.lang}/{it.style}/{it.chan}{'/' + it.facing if it.facing else ''}] {it.text!r}: wanted {it.dest}, rules said {dest}")
    if verbose and unsettled:
        print(f"  LEFT TO THE MODEL ({len(unsettled)}):")
        for it, dest, ok in unsettled:
            print(f"    [{it.lang}/{it.chan}] {it.text!r} (wanted {it.dest})")
    return {"n": n, "settled": len(settled), "correct": sum(1 for r in rows if r[2]), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="all", choices=["dev", "playtest", "test", "test2", "all"])
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    from .router_test2_set import TEST2
    from .router_test_set import TEST
    sets = {"dev": DEV, "playtest": PLAYTEST, "test": TEST, "test2": TEST2, "all": ALL + TEST + TEST2}
    evaluate(sets[args.set], args.verbose, args.set)


if __name__ == "__main__":
    main()
