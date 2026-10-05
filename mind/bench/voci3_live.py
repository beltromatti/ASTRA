"""VOCI-3 on the real models: what the officers DO with the new doctrine, judged by their tool calls and by counts, never by a pattern on what they say.

    (OPENROUTER_API_KEY in the environment)   cd mind && .venv/bin/python -m bench.voci3_live [--only wheel,nets] [--runs 1] [--langs it] [--cap 0.28] [-v]

Each case is one crew turn, run as the server runs it, on the local ship in a fight (a Mandate destroyer closing, another circling):
  wheel   an order the Captain gave from his command wheel, without a word (`bridge: the Captain gave an order from his command wheel, ...`): `Mind._wheel_turn`'s turn
          (WHEEL_ASK, only `speak`). Facts asked of it: the officer of that station speaks, once, in a word or a few, and nobody else; for an order that failed, one short line.
  nets    traffic on a radio net that the Captain has not heard (the text is the one `Nets` makes for the listener): the listener's turn (NET_ASK, `speak` and
          `console_log`). Facts asked of it: routine goes on the console's log with no voice at all; what is urgent, a call to the Captain, a squadron leader down, a marine down,
          is told in a line by the officer who has the watch on that net (Communications the fleet net, Flight Control the flight net, the XO the marines).
What the officers say is printed for the person reading the run (a count of the words is the only thing measured on it). The spend cap stops the run (the ledger of this checkout)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from astra_mind import models
from astra_mind.agent import WHEEL_ASK, Turn, net_ask
from astra_mind.crew import WHEEL_EVENT
from astra_mind.nets import NET_EVENT, Nets
from astra_mind.openrouter import OpenRouter

from .stations_scenarios import Harness

WHEEL = WHEEL_EVENT + ", without a word: "


# ------------------------------------------------------------------------------------------------ the cases
@dataclass
class Wheel:
    name: str
    event: str                    # what the wheel's order was and what the console said of it
    who: set[str]                 # the officers whose acknowledgement it may be
    words: int                    # the most words an acknowledgement of it has (a measure of brevity, not of what is said)
    lines: int = 1                # the most lines he hears


WHEEL_CASES = [
    Wheel("helm course", "Helm: course set to heading 090 (steady on 090)", {"helm"}, 8),
    Wheel("tactical weapons free", "Tactical: weapons free on T-23 (fire control: free to engage T-23)", {"tactical"}, 9),
    Wheel("alert red", "the alert: red alert (alert level set to red)", {"xo"}, 8),
    Wheel("flight launch", "Flight: launch Alpha squadron (Alpha squadron: launching, 6 Falcons)", {"flight"}, 10),
    Wheel("ops power", "Operations: power to the engines 70 percent (route_power: engines 70)", {"ops", "engineering"}, 10),
    Wheel("tactical refused", "Tactical: fire on T-99 (REFUSED: no such contact on the plot)", {"tactical", "xo"}, 30, lines=2),
]


@dataclass
class Net:
    name: str
    net: str                                                # fleet | flight | marines
    rows: list[tuple[str, str, str, dict[str, bool]]]       # (speaker key, name, text, flags: urgent / addressed)
    voice: str                                              # none: all on the log · line: told by the listener (a line or two)


NET_CASES = [
    Net("fleet routine", "fleet", [("castellan", "Captain Castellan", "Aquila, Praetorian: holding at 4.5 km off your port quarter.", {}),
                                   ("okoro", "Captain Okoro", "Praetorian, Vigilant: screen formed, six kilometres.", {}),
                                   ("castellan", "Captain Castellan", "Acheron still at 41 km, bearing 270, no change.", {})], "none"),
    Net("fleet urgent", "fleet", [("okoro", "Captain Okoro", "Aquila, Vigilant: two Mandate cruisers jumped us, we are taking fire, we need support now!",
                                   {"urgent": True, "addressed": True})], "line"),
    Net("fleet call", "fleet", [("rourke", "Vice Admiral Rourke", "Aquila, Fleet command: hold the Janus Gate until relieved, and report when the Mandate screen breaks.",
                                 {"addressed": True})], "line"),
    Net("flight routine", "flight", [("kovac", "Lt. Cmdr. Kovac", "Alpha rearmed, eight ready on the deck.", {}),
                                     ("deck", "Chief of the Deck", "Bravo reports two minutes to rearm.", {})], "none"),
    Net("flight pilot down", "flight", [("kovac", "Lt. Cmdr. Kovac", "Alpha two is down, ejected, I have the beacon, Wasp drones are looking for the pod.", {"urgent": True})], "line"),
    Net("marines routine", "marines", [("reyes", "Major Reyes", "Squad two in position, deck 9 section C.", {}),
                                       ("reyes", "Major Reyes", "Bulkhead 14 sealed, pressure holding.", {})], "none"),
    Net("marine down", "marines", [("reyes", "Major Reyes", "Marine down on deck 9, Corporal Hale, medic on the way, squad three is pulling back.", {"urgent": True})], "line"),
]
LISTENER = {"fleet": ("comms", "comms"), "flight": ("flight", "flight"), "marines": ("xo", "xo")}     # (the officer who tells him, the console whose log it is)


# ------------------------------------------------------------------------------------------------ running
@dataclass
class Out:
    name: str
    kind: str
    lines: list[tuple[str, str]] = field(default_factory=list)
    logs: list[tuple[str, str]] = field(default_factory=list)
    other: list[str] = field(default_factory=list)
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    cost: float = 0.0
    seconds: float = 0.0
    first_line_s: float | None = None

    def must(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, bool(ok), detail))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def facts(turn: Turn, out: Out) -> None:
    out.lines = list(turn.lines)
    out.logs = [(str(a.get("station")), str(a.get("text"))) for n, a, _ in turn.actions if n == "console_log"]
    out.other = [n for n, _, _ in turn.actions if n not in ("console_log", "speak")]
    out.cost = turn.cost
    out.first_line_s = turn.t_first_line


async def run_wheel(llm: OpenRouter, case: Wheel, lang: str) -> Out:
    out = Out(case.name, "wheel")
    h = Harness(llm, lang)
    t0 = time.perf_counter()
    turn = await h.agent.handle_event(WHEEL + case.event, lang, ask=WHEEL_ASK, speak_only=True)          # (as Mind._wheel_turn runs it)
    out.seconds = time.perf_counter() - t0
    facts(turn, out)
    out.must("it speaks", bool(out.lines), f"{out.lines}")
    out.must("only the officer(s) of that station", all(s in case.who for s, _ in out.lines), f"{[s for s, _ in out.lines]} not in {sorted(case.who)}")
    out.must(f"at most {case.lines} line(s)", len(out.lines) <= case.lines, f"{len(out.lines)}")
    out.must(f"at most {case.words} words in all", sum(len(t.split()) for _, t in out.lines) <= case.words, f"{sum(len(t.split()) for _, t in out.lines)} words")
    out.must("no tool but speak", not out.other and not out.logs, f"{out.other} {out.logs}")
    return out


async def run_net(llm: OpenRouter, case: Net, lang: str) -> Out:
    out = Out(case.name, "nets")
    h = Harness(llm, lang)
    clock = [0.0]
    heard: list[str] = []

    async def send(msg: dict[str, Any]) -> None:
        return None

    async def listen(net: str, text: str, urgent: bool, lg: str) -> None:
        heard.append(text)
    nets = Nets(send, listen, clock=lambda: clock[0])
    h.agent.nets = nets
    for key, who, text, flags in case.rows:
        async def aloud() -> None:
            return None
        await nets.post(case.net, key, who, text, lang, urgent=bool(flags.get("urgent")), addressed=bool(flags.get("addressed")), aloud=aloud)
        clock[0] += 3.0
    nets.flush_now()
    await asyncio.sleep(0.05)
    out.must("the net's listener was given the traffic", len(heard) == 1, f"{len(heard)} batches")
    if len(heard) != 1:
        return out
    t0 = time.perf_counter()
    event = NET_EVENT + heard[0]                                                                          # (as Mind._net_listen queues it)
    turn = await h.agent.handle_event(event, lang, ask=net_ask([event]))                                  # (and as the turn worker asks for it)
    out.seconds = time.perf_counter() - t0
    facts(turn, out)
    who, console = LISTENER[case.net]
    if case.voice == "none":
        out.must("nothing said aloud", not out.lines, f"{out.lines}")
        out.must(f"on the {console} console's log", any(s == console for s, _ in out.logs), f"{out.logs}")
    else:
        out.must("the Captain is told", bool(out.lines), f"lines {out.lines}, log {out.logs}")
        out.must(f"by {who}, who has the watch", all(s == who for s, _ in out.lines), f"{[s for s, _ in out.lines]}")
        out.must("in a line or two", len(out.lines) <= 2 and sum(len(t.split()) for _, t in out.lines) <= 40, f"{sum(len(t.split()) for _, t in out.lines)} words")
    out.must("no other tool", not out.other, f"{out.other}")
    return out


async def main_async(args: argparse.Namespace) -> int:
    llm = OpenRouter()
    only = set(args.only.split(",")) if args.only else {"wheel", "nets"}
    cases = [c for c in args.case.split(",") if c]
    outs: list[tuple[str, Out]] = []
    t_all = time.perf_counter()
    try:
        for lang in args.langs.split(","):
            for run in range(args.runs):
                if "wheel" in only:
                    for c in WHEEL_CASES:
                        if not cases or any(k in c.name for k in cases):
                            outs.append((lang, await _guard(run_wheel(llm, c, lang), c.name, "wheel")))
                if "nets" in only:
                    for n in NET_CASES:
                        if not cases or any(k in n.name for k in cases):
                            outs.append((lang, await _guard(run_net(llm, n, lang), n.name, "nets")))
    finally:
        await llm.close()
    for lang, o in outs:
        print(f"\n{'PASS' if o.passed else 'FAIL'}  {o.kind}: {o.name} [{lang}]  ${o.cost:.4f}  {o.seconds:.1f}s" + (f"  first line {o.first_line_s:.2f}s" if o.first_line_s else ""))
        for s, t in o.lines:
            print(f"   say  {s}: {t}")
        for s, t in o.logs:
            print(f"   log  {s}: {t}")
        for name, ok, detail in o.checks:
            if not ok or args.verbose:
                print(f"   {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  <- {detail}"))
        sys.stdout.flush()
    ok = sum(1 for _, o in outs if o.passed)
    print(f"\n=== {ok}/{len(outs)} cases pass; {models.LEDGER.summary()}; {time.perf_counter() - t_all:.0f} s")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([{"lang": lg, "name": o.name, "kind": o.kind, "passed": o.passed, "cost": o.cost, "lines": o.lines, "logs": o.logs, "checks": o.checks}
                       for lg, o in outs], f, ensure_ascii=False, indent=1)
    return 0 if ok == len(outs) else 1


async def _guard(coro, name: str, kind: str) -> Out:  # noqa: ANN001
    try:
        return await coro
    except models.SpendCapReached:
        raise
    except Exception as exc:  # noqa: BLE001
        o = Out(name, kind)
        o.must("ran without error", False, f"{type(exc).__name__}: {exc}")
        return o


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--case", default="", help="only the cases whose name has one of these words in it (comma-separated)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--langs", default="it")
    ap.add_argument("--cap", type=float, default=0.28)
    ap.add_argument("--out", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    models.LEDGER.cap = args.cap                                  # (this checkout's ledger: the run stops when the log reaches it)
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
