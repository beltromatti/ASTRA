"""Live check of the `transporter` role (the Transporter Room's Chief) against a real model on OpenRouter. It costs well under a cent.

    cd mind && ASTRA_HOME=/path/to/the/main/checkout .venv/bin/python -m bench.transporter_live          # the role's own model, all scenes
    cd mind && ... -m bench.transporter_live --only relay_surface --debug --cap 0.02

Every scene is what the game sends the Chief (an order relayed from the bridge, the Captain's words in her room, or the room's own news) with her console's card exactly as the
game wrote it (bench/fixtures/transporter, from tools/transport.py run --scenario world), and a console that answers her commands from that same card the way the game does (a
transport the card says cannot be done is refused with the reason; one that can is accepted). The bench calls the same code the server does (astra_mind.transporter) and prints
what she did and said. What a machine can check is checked (she acts with her tools or says why not, a refusal is told to the Captain, silence when the words were not for her, the
Captain's language, the length, the cost); whether the lines are in character and never invent a number is read by ear, from the printout.
The key is read from the environment or the repository's .env (never printed); the spend is capped (--cap, dollars)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from astra_mind import models, transporter
from astra_mind.openrouter import Completion, OpenRouter
from astra_mind.server import detect_lang

models.LEDGER.write_file = False
FIX = Path(__file__).parent / "fixtures" / "transporter"
STATE = {"captain": "in the Transporter Room (Deck 5)", "location": "Aurelia System, home of the 7th Fleet", "alert": "green", "hull_pct": 100, "heading_deg": 90, "speed_mps": 0,
         "shields": {"strength_pct": 100, "state": "up"}, "power_pct": {"sensors": 100},
         "contacts": [{"id": "T-02", "name": "ASN Vigilant (CVC-02)", "status": "friendly", "range_km": 3.1}, {"id": "T-01", "name": "ASN Praetorian", "status": "friendly", "range_km": 4.2}],
         "surface": {"world": "New Ravenna", "kind": "ocean world", "field": "Port Aurelius Field", "captain_here": False}}


def card(name: str) -> dict[str, Any]:
    return json.loads((FIX / f"card_{name}.json").read_text(encoding="utf-8"))


# name, kind (order | captain | news), card, the order or words or news, language, expectations: tools she must / must not call, a pattern the speech must / must not hold
SCENES: list[dict[str, Any]] = [
    dict(name="relay_surface", kind="order", card="idle", by="ops", lang="it", words="Capo, portami giù sul pianeta.",
         order={"action": "beam", "who": ["captain"], "to": "surface"}, must_say=True, lang_is="it"),
    dict(name="aboard_en", kind="captain", card="idle", lang="en", words="Chief, send Lieutenant Sato to Main Engineering.", calls=["transport"], call_has="engineering", must_say=True),
    dict(name="boarding_refused", kind="order", card="battle", by="xo", lang="en", words="Marines to the Acheron, now.", order={"action": "beam", "who": ["marines 4"], "to": "M-01"},
         must_say=True, say_has=r"shield|face|sector"),
    dict(name="ask_reach", kind="order", card="idle", by="ops", lang="en", words="Can we put someone aboard the Vigilant?", order={"action": "ask", "question": "can we send someone aboard the Vigilant (T-02) now, and if not what clears it?"},
         must_say=True, say_has=r"shield|window"),
    dict(name="bring_back", kind="order", card="away", by="ops", lang="en", words="Bring the away team home.", order={"action": "beam", "who": ["away team"], "to": "pad 5"},
         calls=["transport"], call_has="away", must_say=True),
    dict(name="for_the_xo", kind="captain", card="idle", lang="en", words="Number One, give me a damage report.", silent=True),
    dict(name="news_done", kind="news", card="idle", lang="en", news=["X3 done: Lieutenant Sato is at pad 2, a clean arrival, lock quality 100% at worst, 8.0 s cycle"], max_words=30),
    dict(name="news_urgent", kind="news", card="idle", lang="en", news=["URGENT: X4: the lock is lost with the Captain in the buffer (jamming 70%): the console is building it again; the buffer holds 85 s, or the pattern can be called back to its origin"],
         must_say=True),
]


class Spy:
    """The real client, keeping every completion it returns (tokens, times, cost) for the report."""

    def __init__(self, inner: OpenRouter) -> None:
        self.inner = inner
        self.done: list[Completion] = []

    async def chat(self, **kw: Any) -> Completion:
        c = await self.inner.chat(**kw)
        self.done.append(c)
        return c

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def console(card_: dict[str, Any]):
    """The console as the game answers: from the card's own options."""
    async def execute(name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        if name == "crew_locate":
            return {"ok": True, "detail": f"Lieutenant Tomasz Sato (weapons) is in Deck 8 · Section A · Armoury, on duty."}
        if name in ("transport_energize", "transport_abort"):
            return {"ok": True, "detail": f"{name} accepted"}
        to = str(args.get("to", "")).lower()
        window = bool(args.get("shield_window"))
        for o in card_.get("options", []):
            if o["to"].lower() == to or to and to in (o["place"] or "").lower():
                if o["answer"].startswith("can be done"):
                    return {"ok": True, "detail": f"X1 accepted: lock in about {o.get('lock_s', 3)} s"}
                if window and "shield window" in o.get("what_clears_it", "") and "unknown" not in o["answer"]:
                    return {"ok": True, "detail": f"X1 accepted with a shield window: lock in about {o.get('lock_s', 3)} s"}
                return {"ok": False, "detail": "refused: " + " | ".join(o.get("in_the_way", [])) + (f" (to clear it: {o['what_clears_it']})" if o.get("what_clears_it") else "")}
        if re.search(r"pad|engineering|medbay|bridge|deck|armory|galley|hangar|room", to):
            return {"ok": True, "detail": f"X1 accepted: lock in about 1.5 s"}
        return {"ok": False, "detail": f"refused: no room, ship or place called \"{args.get('to')}\""}
    return execute


async def run(cap: float, only: list[str], debug: bool) -> int:
    llm = Spy(OpenRouter())
    tmp = tempfile.mkdtemp(prefix="xfer_live_")
    total = 0.0
    bad = 0
    print(f"=== {models.role('transporter').model}")
    for sc in SCENES:
        if only and sc["name"] not in only:
            continue
        if total >= cap:
            print(f"   the cap of {cap:.3f} $ is reached: stopping")
            break
        st = dict(STATE, transporter=card(sc["card"]))
        lines: list[tuple[float, str, bool, bool]] = []
        calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        t0 = time.perf_counter()
        ex = console(st["transporter"])

        async def say(speaker: str, text: str, lang: str, tone: str, *, priority_urgent: bool = False, answer: bool = False) -> int:
            lines.append((time.perf_counter() - t0, text, priority_urgent, answer))
            return len(lines)

        async def execute(name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
            r = await ex(name, args, by)
            calls.append((name, args, r))
            return r

        chief = transporter.TransporterRoom(llm, say, execute, state=lambda s=st: s, lang=lambda l=sc["lang"]: l, store=Path(tmp) / f"{sc['name']}.json")
        before = len(llm.done)
        if sc.get("words"):
            chief.captain_said(sc["words"], sc["lang"])
        try:
            if sc["kind"] == "order":
                await chief.order(sc["order"], sc["by"])
                for t in list(chief._tasks):
                    await asyncio.wait_for(asyncio.shield(t), 25.0)
            elif sc["kind"] == "captain":
                await chief.hear(sc["words"], sc["lang"], None, "in the Transporter Room")
            else:
                for n in sc["news"]:
                    chief.on_event("transporter: " + n)
                chief._events[:] = [e.__class__(e.t - 10.0, e.text, e.urgent) for e in chief._events]      # (the burst has settled)
                chief.kick()
                while chief._task is not None and not chief._task.done():
                    await asyncio.sleep(0.05)
        except Exception as e:  # noqa: BLE001
            print(f"   {sc['name']:<18} ERROR {type(e).__name__}: {e}")
            bad += 1
            continue
        t_end = time.perf_counter() - t0
        comps = llm.done[before:]
        cost = sum(c.cost for c in comps)
        total += cost
        said = " ".join(t for _, t, _, _ in lines)
        problems: list[str] = []
        if sc.get("silent") and lines:
            problems.append("should have said nothing")
        if sc.get("must_say") and not lines:
            problems.append("said nothing")
        for want in sc.get("calls", []):
            if not any(c[0] == want for c in calls):
                problems.append(f"did not call {want}")
        if sc.get("call_has") and calls and not any(sc["call_has"] in json.dumps(c[1]).lower() for c in calls):
            problems.append(f"no call mentions {sc['call_has']}")
        if sc.get("say_has") and lines and not re.search(sc["say_has"], said, re.I):
            problems.append(f"missing /{sc['say_has']}/")
        if sc.get("lang_is") and lines and detect_lang(said, "en") != sc["lang_is"]:
            problems.append(f"not in {sc['lang_is']}")
        if any(len(t.split()) > sc.get("max_words", 45) for _, t, _, _ in lines):
            problems.append("a line too long")
        if lines and lines[0][0] > 8.0:
            problems.append(f"first line after {lines[0][0]:.1f}s")
        refused = [c for c in calls if not c[2].get("ok")]
        bad += 1 if problems else 0
        err = "; ".join(c.error[:80] for c in comps if c.error)
        print(f"   {sc['name']:<18} {t_end:4.1f}s  {sum(c.prompt_tokens for c in comps):>5} in {sum(c.completion_tokens for c in comps):>4} out  {cost * 1000:5.2f} m$  "
              f"{'OK ' if not problems else 'BAD'} {'; '.join(problems)}{' [' + err + ']' if err else ''}")
        for name, args, r in calls:
            print(f"        > {name}({json.dumps(args, ensure_ascii=False)[:110]}) -> {'ok' if r.get('ok') else 'REFUSED'}: {r.get('detail', '')[:90]}")
        for t, text, urgent, answer in lines:
            print(f"        {'!' if urgent else ' '}{'<' if answer else ' '} {text}")
        if refused and not lines:
            print("        (refused and said nothing)")
        if debug:
            for c in comps:
                print(f"        [{c.provider}] content={c.content[:160]!r} calls={[(t.name, t.arguments_raw[:90]) for t in c.tool_calls]} error={c.error[:160]!r}")
    print(f"\n--- spent {total:.5f} $ ({len(llm.done)} calls); {bad} scene(s) to look at")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=0.03, help="stop when this many dollars are spent")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(run(a.cap, a.only, a.debug))


if __name__ == "__main__":
    sys.exit(main())
