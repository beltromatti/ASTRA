"""Live check of the `npc` role (the ship's people answering the Captain) against a real model on OpenRouter. It costs about a cent.

    cd mind && .venv/bin/python -m bench.npc_live                                    # the role's own model
    cd mind && .venv/bin/python -m bench.npc_live --model deepseek/deepseek-v4.1-flash@together,modal --model openai/gpt-oss-120b@crusoe

Every scenario is what the game sends with the Captain's words (people within earshot, as the simulation describes them, and what the
ship knows); the bench calls the same code the server does (astra_mind.npc.Npcs) and prints what each person said. What a machine can
check is checked (silence when the words were not for them, an answer when they were, the right speaker, the length, a fact they must
know, a fact they must not know); whether a line is in character and in the Captain's language is read by ear, from the printout.
The key is read from the environment or the repository's .env (never printed); the spend is capped (--cap, dollars)."""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from astra_mind import models, npc
from astra_mind.openrouter import Completion, OpenRouter
from bench.npc_unit import ENGINEER, SENSOR, STATE, STEWARD

models.LEDGER.write_file = False

WORLD = {"state": STATE, "war": "The 7th Fleet holds Aurelia; a Mandate raiding group was turned back at the Janus Gate two days ago, and the crews talk of little else.",
         "mood": "Tense but steady: the crew trusts the Captain and is proud of the Gate, and tired of the alarms.", "clock": "day 1 14:32"}


def _at(row: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return dict(row, **kw)


MARINE = {"id": "npc455", "name": "Marine Corporal Elena Vasquez", "rank": "Corporal", "gender": "f", "dept": "marines", "home": "Nueva Castilla", "job": "rifleman",
          "watch": "Gold", "doing": "on duty, at the armoury door (Deck 4 · Section F · Armoury)", "place": "Deck 4 · Section F · Armoury", "dist_m": 2.4,
          "angle_deg": 6, "facing": True, "memory": ["General quarters sounded at 08:10: everyone to battle stations (yesterday, ship time 08:10)"], "friends": []}

# name, what the Captain says, language, the people (rows as PersonJson makes them), what is expected: "answer" / "silence",
# who must speak (id, or None), a pattern the line must contain (any), a pattern it must not
SCENARIOS: list[dict[str, Any]] = [
    dict(name="menu", text="Com'è il pranzo oggi?", lang="it", where="in the Main Galley", people=[_at(STEWARD, facing=True, dist_m=2.0, angle_deg=3)],
         expect="answer", who="npc301", must=r"agnell|orzo|riso|caff|verdur", forbid=r""),
    dict(name="fire_memory", text="Cos'è successo qui poco fa?", lang="it", where="in Machinery Space", people=[ENGINEER],
         expect="answer", who="npc17", must=r"fuoc|incendi|fiamm|C\b", forbid=r""),
    dict(name="medbay_en", text="Where is the nearest medical bay?", lang="en", where="in the Main Galley", people=[_at(STEWARD, facing=True, dist_m=2.0, angle_deg=3)],
         expect="answer", who="npc301", must=r"deck 6|sixth|medbay", forbid=r""),
    dict(name="helm_order", text="Timoniere, rotta zero-nove-zero.", lang="it", where="in a corridor", people=[_at(SENSOR, dist_m=4.0, facing=False)],
         expect="silence", who=None, must=r"", forbid=r""),
    dict(name="aloud", text="Hmm... gli scudi sono ancora bassi.", lang="it", where="in a corridor", people=[_at(SENSOR, dist_m=3.5), _at(STEWARD, dist_m=4.2, facing=False)],
         expect="silence", who=None, must=r"", forbid=r""),
    dict(name="plot_probe", text="How many hostile ships are out there, and how far?", lang="en", where="in the Main Galley", people=[_at(STEWARD, facing=True, dist_m=2.0, angle_deg=3)],
         expect="answer", who="npc301", must=r"", forbid=r"22\.4|Cocytus|T-23"),
    dict(name="sensor_board", text="Cosa c'è sul tuo schermo?", lang="it", where="in the Sensor Array Room", people=[_at(SENSOR, facing=True, dist_m=2.2, angle_deg=5)],
         expect="answer", who="npc90", must=r"Cocytus|ostile|22", forbid=r""),
    dict(name="coffee_de", text="Bringen Sie mir bitte einen Kaffee.", lang="de", where="in the Main Galley", people=[_at(STEWARD, facing=True, dist_m=1.8, angle_deg=3)],
         expect="answer", who="npc301", must=r"", forbid=r""),
    dict(name="engine_es", text="¿Cómo está la máquina? Necesito saberlo.", lang="es", where="in Machinery Space", people=[ENGINEER, _at(STEWARD, dist_m=4.0, facing=False)],
         expect="answer", who="npc17", must=r"78|reactor|fuego|incendio", forbid=r""),
    dict(name="greeting_fr", text="Bonsoir, comment allez-vous ?", lang="fr", where="in the Main Galley", people=[_at(STEWARD, facing=True, dist_m=2.0, angle_deg=3)],
         expect="answer", who="npc301", must=r"", forbid=r""),
    dict(name="secret", text="Qual è il piano segreto del comandante nemico?", lang="it", where="in Machinery Space", people=[ENGINEER],
         expect="answer", who="npc17", must=r"", forbid=r"fianc|flank|aggir"),
    dict(name="computer", text="Computer, rapporto di stato della nave.", lang="it", where="in a corridor", people=[_at(SENSOR, dist_m=3.0, facing=False), _at(STEWARD, dist_m=4.0, facing=False)],
         expect="silence", who=None, must=r"", forbid=r""),
    dict(name="xo_report", text="Number One, give me a damage report.", lang="en", where="in Machinery Space", people=[_at(ENGINEER, facing=False, dist_m=3.0, angle_deg=40)],
         expect="silence", who=None, must=r"", forbid=r""),
    dict(name="radio_call", text="Falcon Leader, this is Aquila: engage the contact at your discretion.", lang="en", where="in a corridor", people=[_at(STEWARD, dist_m=2.5, facing=False)],
         expect="silence", who=None, must=r"", forbid=r""),
    dict(name="by_name", text="Petty Officer Diallo, a word, please.", lang="en", where="in Machinery Space", people=[_at(ENGINEER, facing=False, dist_m=3.0, angle_deg=35), _at(STEWARD, dist_m=2.0, facing=True, angle_deg=5)],
         expect="answer", who="npc17", must=r"", forbid=r""),
    dict(name="morale", text="Com'è il morale dei marines?", lang="it", where="at the armoury", people=[MARINE],
         expect="answer", who="npc455", must=r"", forbid=r""),
    # a name called across a busy concourse: the one named answers, ten metres away and not looked at (the game says he can hear)
    dict(name="name_far", text="Kowalski, com'è il rancio oggi?", lang="it", where="in the Mess Concourse (Deck 4, section B)",
         people=[_at(SENSOR, dist_m=2.5, facing=False, angle_deg=60), _at(ENGINEER, dist_m=3.4, facing=False, angle_deg=80),
                 _at(STEWARD, dist_m=9.5, facing=False, angle_deg=40, doing="on the way to a meal", place="Deck 4 · Section B · Mess Concourse")],
         expect="answer", who="npc301", must=r"", forbid=r""),
    # the Captain looks at a crewman while calling the bridge on the intercom: the words are the bridge's all the same
    dict(name="bridge_facing", text="Ponte, qui il Capitano: chi è il cuoco di turno adesso, e dov'è?", lang="it",
         where="in the Mess Concourse (Deck 4, section B)",
         people=[_at(SENSOR, dist_m=4.0, facing=True, angle_deg=8), _at(MARINE, dist_m=9.0, facing=False, angle_deg=70)],
         expect="silence", who=None, must=r"", forbid=r""),
    # the same crowd, and words for the bridge over the intercom: nobody of them answers
    dict(name="crowd_bridge", text="Ponte, qui il Capitano: allarme giallo, e mandatemi il rapporto dei danni.", lang="it",
         where="in the Mess Concourse (Deck 4, section B)",
         people=[_at(SENSOR, dist_m=2.5, facing=False, angle_deg=60), _at(ENGINEER, dist_m=3.4, facing=False, angle_deg=80),
                 _at(STEWARD, dist_m=9.5, facing=False, angle_deg=40), _at(MARINE, dist_m=12.0, facing=False, angle_deg=120)],
         expect="silence", who=None, must=r"", forbid=r""),
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


def _words(s: str) -> int:
    return len(s.split())


async def run(specs: list[str], cap: float, names: list[str], debug: bool = False) -> int:
    base = models.ROLES["npc"]
    llm = Spy(OpenRouter())
    tmp = tempfile.mkdtemp(prefix="npc_live_")
    models.LEDGER.cap = None
    total = 0.0
    failures = 0
    summary: list[str] = []
    for spec in specs:
        if spec:
            model, _, provs = spec.partition("@")
            models.ROLES["npc"] = replace(base, model=model, providers=tuple(p for p in provs.split(",") if p) or None,
                                          reasoning=(("effort", "low"),) if "gpt-oss" in model else base.reasoning if model == base.model else (("enabled", False),))
        label = spec or f"{base.model}@{','.join(base.providers or ())}"
        print(f"\n=== {label}")
        lat, cost, toks, ok = [], 0.0, 0, 0
        todo = [s for s in SCENARIOS if not names or s["name"] in names]
        for sc in todo:
            if total >= cap:
                print(f"   the cap of {cap:.3f} $ is reached: stopping")
                break
            lines: list[tuple[float, str, str]] = []
            t0 = time.perf_counter()

            async def say(who: str, text: str, lang: str, tone: str, **kw: Any) -> int:
                lines.append((time.perf_counter() - t0, who, text))
                return len(lines)

            n = npc.Npcs(llm, say, store=Path(tmp) / "talk.json")
            people = npc.pick(npc.parse_people({"people": sc["people"]}, None))
            before = len(llm.done)
            try:
                spoke = await n._ask(sc["text"], sc["lang"], people, WORLD, sc["where"])
            except Exception as e:  # noqa: BLE001
                print(f"   {sc['name']:<12} ERROR {type(e).__name__}: {e}")
                failures += 1
                continue
            t_end = time.perf_counter() - t0
            comps = llm.done[before:]
            c = sum(x.cost for x in comps)
            tok_in = sum(x.prompt_tokens for x in comps)
            tok_out = sum(x.completion_tokens for x in comps)
            total += c
            cost += c
            toks += tok_in + tok_out
            problems: list[str] = []
            if sc["expect"] == "silence" and spoke:
                problems.append("should have said nothing")
            if sc["expect"] == "answer" and not spoke:
                problems.append("did not answer")
            if spoke and sc["who"] and spoke[0][0] != sc["who"]:
                problems.append(f"{spoke[0][0]} answered, not {sc['who']}")
            said = " ".join(t for _, t in spoke)
            if sc["must"] and spoke and not re.search(sc["must"], said, re.I):
                problems.append(f"missing /{sc['must']}/")
            if sc["forbid"] and re.search(sc["forbid"], said, re.I):
                problems.append(f"says /{sc['forbid']}/")
            if any(_words(t) > 45 for _, t in spoke):
                problems.append("a line over 45 words")
            if len(spoke) > npc.MAX_LINES:
                problems.append("too many lines")
            first = lines[0][0] if lines else t_end
            if first > npc.WAIT_S:
                problems.append(f"first line after {first:.1f}s (the game waits {npc.WAIT_S:.0f}s)")
            lat.append(first)
            ok += 0 if problems else 1
            failures += 1 if problems else 0
            err = "; ".join(x.error[:80] for x in comps if x.error)
            print(f"   {sc['name']:<12} {first:4.1f}s (end {t_end:4.1f}s) {tok_in:>5} in {tok_out:>4} out  {c*1000:5.2f} m$  "
                  f"{'OK ' if not problems else 'BAD'} {'; '.join(problems)}{' [' + err + ']' if err else ''}")
            for (t, who, text) in lines:
                print(f"        {who}: {text}")
            if debug:
                for x in comps:
                    print(f"        [{x.provider}] content={x.content[:160]!r} calls={[(t.name, t.arguments_raw[:90]) for t in x.tool_calls]} error={x.error[:160]!r}")
        if lat:
            summary.append(f"{label}: {ok}/{len(lat)} as expected, first line median {statistics.median(lat):.1f}s (max {max(lat):.1f}s), "
                           f"{cost / len(lat) * 1000:.2f} m$ a call, {toks // len(lat)} tokens a call")
    print("\n--- summary")
    for s in summary:
        print("  " + s)
    print(f"  spent {total:.5f} $")
    return 1 if failures else 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="   (%(name)s: %(message)s)")
    logging.getLogger("astra.npc").setLevel(logging.INFO)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", default=[], help="model@provider,provider (repeatable); the role's own when none")
    ap.add_argument("--cap", type=float, default=0.05, help="stop after spending this many dollars")
    ap.add_argument("--only", action="append", default=[], help="scenario names to run")
    ap.add_argument("--debug", action="store_true", help="print what the model returned")
    a = ap.parse_args()
    return asyncio.run(run(a.model or [""], a.cap, a.only, a.debug))


if __name__ == "__main__":
    sys.exit(main())
