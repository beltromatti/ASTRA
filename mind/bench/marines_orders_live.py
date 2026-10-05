"""The marine net against the real model on the infantry orders (ABBORDAGGI-4): does the Captain's word become the right order, with what goes with it?
It costs a few cents (`--cap` stops it). The scenes are those of marines_live.py (the same state, the same stage and the same checks of who speaks and how much), with the game as the C++ answers the new orders
(`marine_order` with sweep, breach, take, ambush, escort_captain and fire / seal_behind / cover / sync / inside: AstraBoardMind.cpp) and the Captain's words that name them.

    cd mind && .venv/bin/python -m bench.marines_orders_live                       # every scene once
    cd mind && .venv/bin/python -m bench.marines_orders_live --repeat 3 --only captain_take

What a machine can check is checked (which command, which task, which place, which modifier reached the game); whether the line is in character and true to the order is read from the printout
(docs/ARCHITETTURA.md §1bis: never a regular expression over what they say)."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import statistics
import sys
from dataclasses import dataclass, field
from typing import Any

from bench import marines_live as ml
from bench.marines_unit import ATTACK_BOARDING, ATTACK_PICTURE, ship_state
from astra_mind import marines as mm
from astra_mind import models
from astra_mind.openrouter import OpenRouter

SECTION = re.compile(r"deck\s*\d+\s*(?:,\s*)?section\s*[a-z]", re.I)
NEEDS_PLACE = ("sweep", "breach", "take", "ambush")


class OrdersGame(ml.Game):
    """The game as the C++ answers the marines' orders now: a section (`deck 7 section D`) and a door's id (for a breach) are places, a room task without a place is refused, an escort needs the Captain in the fight."""

    def ids(self) -> set[str]:
        out = super().ids()
        p = self.state.get("_marines") or {}
        for d in p.get("objective_doors", []) + p.get("bulkheads", []):
            out.add(str(d.get("id", "")))
        return out - {""}

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        if name != "marine_order":
            return await super().execute(name, args, by)
        task, place = str(args.get("task") or ""), str(args.get("place") or "")
        p = self.state.get("_marines") or {}
        if task in NEEDS_PLACE and (not place or place.lower() in ("captain", "here")) and not p.get("captain"):
            self.commands.append({"name": name, "args": args, "by": by})
            return {"ok": False, "detail": f"{task} needs a place: a room's id from the board, a deck's section (deck 7 section D)" + (", or a door's id" if task == "breach" else "")}
        if task == "escort_captain" and not p.get("captain"):
            self.commands.append({"name": name, "args": args, "by": by})
            return {"ok": False, "detail": "the Captain is not in the fight with the marines: there is nobody to escort (follow_captain and rescue_captain are for the Captain on the same decks)"}
        if place and SECTION.search(place):
            args = {**args, "place": "engineering"}                      # (a section is a place the plan has: the game takes it; the stub stands it for a known id, and keeps the words)
            res = await super().execute(name, args, by)
            self.commands[-1]["args"]["place"] = place
            return res
        if place and place in self.ids() - {p.get("objective_id", "")} and place in {d.get("id") for d in p.get("objective_doors", [])}:
            res = await super().execute(name, {**args, "place": "engineering"}, by)
            self.commands[-1]["args"]["place"] = place
            return res
        return await super().execute(name, args, by)


def with_objective_doors(st: dict[str, Any]) -> None:
    st["_marines"]["objective_doors"] = [{"id": "d7_door_eng_1", "between": "deck 7 section F (Main Engineering lobby) | deck 7 section F (Main Engineering)", "sealed": True},
                                       {"id": "d7_door_eng_2", "between": "deck 7 section F (Spine) | deck 7 section F (Main Engineering)", "sealed": False}]


def attacking(st: dict[str, Any]) -> None:
    st["_marines"] = json.loads(json.dumps(ATTACK_PICTURE))
    st["boarding"] = json.loads(json.dumps(ATTACK_BOARDING))
    st["captain"] = "on the bridge"


def attacking_with_captain(st: dict[str, Any]) -> None:
    attacking(st)
    st["_marines"]["captain"] = {"where": "deck 4 section A (Stair Tower)", "where_id": "d4_stairs_A1", "down": False, "strength_pct": 100}
    st["boarding"]["captain"] = {"strength_pct": 100, "down": False, "armed": "AR-181 rifle, 30/30"}
    st["captain"] = "on another ship's decks, with the marines, with an AR-181 rifle"


@dataclass
class Case:
    scene: ml.Scene
    has: dict[str, Any] = field(default_factory=dict)             # what an order of the scene must carry (a modifier): key -> value
    hasnt: tuple[str, ...] = ()                                    # what it must not carry


CASES = [
    Case(ml.Scene("captain_take", captain="Reaction Uno e Reaction Due, prendete la sala macchine, insieme.", who={"reyes"}, order=("marine_order", {"take"}, {"engineering"}), max_lines=2,
                  note="'take': both squads, one room; the game puts them in sync by itself")),
    Case(ml.Scene("captain_ambush", captain="Reaction Due, imboscata al corridoio cinque-B: nessuno spara finché non sono dentro.", who={"reyes", "marine_reaction_2"}, order=("marine_order", {"ambush"}, {"corridor_5b"}), max_lines=2,
                  note="an ambush: the fire is held (the game holds it for an ambush by itself; the model may say it)")),
    Case(ml.Scene("captain_sweep", captain="Reaction Uno, rastrellate il ponte sette sezione D, una stanza alla volta.", who={"reyes", "marine_reaction_1"}, order=("marine_order", {"sweep"}, {"deck 7 section D"}), max_lines=2,
                  note="a sweep of a deck's section: said as «deck 7 section D»")),
    Case(ml.Scene("captain_fall_back_seal", captain="Reaction Uno, ripiegate sull'armeria e chiudete le paratie dietro di voi.", who={"reyes", "marine_reaction_1"}, order=("marine_order", {"fall_back", "withdraw"}, {"d8_armory_C1"}), max_lines=2,
                  note="a fall back that shuts the bulkheads behind the squad"), has={"seal_behind": True}),
    Case(ml.Scene("captain_escort", captain="Reaction Due, scortatemi.", mod=ml.captain_in_corridor, who={"marine_reaction_2", "reyes"}, order=("marine_order", {"escort_captain"}, None), max_lines=2,
                  note="'escort me', the Captain in the corridor: escort_captain")),
    Case(ml.Scene("captain_line", captain="Tenete la linea al corridoio cinque-C. Non spargetevi.", who={"reyes"}, order=("marine_order", {"hold", "ambush"}, {"corridor_5c_s"}), max_lines=2,
                  note="'hold the line' is a hold of the place the enemy must come to, the squads together (never a man at every door)")),
    Case(ml.Scene("captain_breach", captain="Reaction Uno, sfondate la porta dell'ingegneria e prendete la sala.", mod=with_objective_doors, who={"reyes", "marine_reaction_1"},
                  order=("marine_order", {"breach", "take"}, {"d7_door_eng_1", "d7_door_eng_2", "engineering"}), max_lines=2, note="a breach (a door's id from the board) or a take of the room beyond it")),
    Case(ml.Scene("attack_sweep", captain="Boarding Alpha, setacciate il ponte uno, sezione B, stanza per stanza.", mod=attacking, who={"reyes", "marine_boarding_alpha"}, order=("marine_order", {"sweep"}, {"deck 1 section B"}),
                  max_lines=2, note="the marines attacking a ship: a sweep of the section of the objective")),
    Case(ml.Scene("attack_escort", captain="Alpha, scortatemi fino alla suite.", mod=attacking_with_captain, who={"reyes", "marine_boarding_alpha"}, order=("marine_order", {"escort_captain", "follow_captain"}, None),
                  max_lines=2, note="the Captain with the marines on the other ship: an escort (or 'with me')")),
    Case(ml.Scene("captain_escort_refused", captain="Reaction Uno, scortatemi.", who={"reyes", "marine_reaction_1"}, max_lines=2,
                  note="the Captain is on the bridge: there is nobody to escort; the order is refused by the game and said once, no false 'done'")),
]


async def main_async(a: argparse.Namespace) -> int:
    ml.Game = OrdersGame                                           # (the stage runs the scenes with the game of this bench)
    llm = ml.Spy(OpenRouter())
    models.LEDGER.cap = None
    total, bad, runs = 0.0, 0, 0
    lat: list[float] = []
    rates: list[tuple[str, int, int]] = []
    for case in [c for c in CASES if not a.only or c.scene.name in a.only]:
        sc = case.scene
        if total >= a.cap:
            print(f"the cap of {a.cap:.3f} $ is reached: stopping")
            break
        passed, shown = 0, False
        for rep in range(a.repeat):
            before = len(llm.done)
            out, d = await ml.run_scene(sc, llm, a.debug)
            comps = llm.done[before:]
            total += sum(x.cost for x in comps)
            runs += 1
            lat.append(d["pulse"].get("latency", 0.0))
            sent = [c for c in d["game"] if c["name"] == "marine_order"]
            problems = list(d["problems"])
            if case.has and sent and not any(all(c["args"].get(k) == v for k, v in case.has.items()) for c in sent if c["args"].get("task") in sc.order[1]):
                problems.append(f"no order carried {case.has}")
            for k in case.hasnt:
                if any(c["args"].get(k) for c in sent):
                    problems.append(f"an order carried {k}")
            if sc.name == "captain_escort_refused" and not any(c["args"].get("task") == "escort_captain" for c in sent):
                problems.append("no escort_captain was tried (the game would have refused it: the model should still have tried, or said it cannot)")
            ok = not problems
            passed += ok
            bad += 0 if ok else 1
            if rep == 0 or (not ok and not shown):
                shown = shown or not ok
                print(f"\n=== {sc.name} — {sc.note}\n    {'OK ' if ok else 'BAD'} {'; '.join(problems)}")
                for line in out:
                    print("    " + line)
        rates.append((sc.name, passed, a.repeat))
    if lat:
        print(f"\n--- {runs - bad}/{runs} runs as expected ({', '.join(f'{n} {p}/{r}' for n, p, r in rates if p < r) or 'every scene every time'}), pulse latency median {statistics.median(lat):.1f}s, spent {total:.5f} $")
    await llm.inner.close()
    return 1 if bad else 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="   (%(name)s: %(message)s)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[], help="scene names to run")
    ap.add_argument("--cap", type=float, default=0.08, help="stop after spending this many dollars")
    ap.add_argument("--debug", action="store_true", help="print what the model returned")
    ap.add_argument("--repeat", type=int, default=1, help="run every scene this many times (the model is not deterministic)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
