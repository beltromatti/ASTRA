"""Offline tests of the lifts' voice against a scripted model and a scripted ship (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.lift_unit -v

The Captain inside a lift car says where to go: the mind knows it from the game's `context.lift` (which car, where it stands, the stops it serves with their decks and
notable places), the ship's computer takes him there with a real tool (`lift_go`, one of THIS car's stops) and says one short line in the Captain's language.
What is checked is the plumbing the behaviour stands on: the context row the game writes is read (the sample is what the headless bench prints), the tool exists only
inside a car and takes only that car's stops, the computer is a speaker only there, a call outside a car is refused, a model that picks no stop does nothing, the
room's paragraph tells the model what to do. Nothing in the code reads the Captain's words (docs/ARCHITETTURA.md §1bis): which deck "Main Engineering" or "una sopra"
means is the model's judgement, measured by bench/lift_live.py against the real model."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any

from astra_mind import context as context_model
from astra_mind import models
from astra_mind.agent import BridgeAgent
from astra_mind.context import parse as parse_context
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tools import SPEAK, lift_tool, owner_of, tools_for

models.LEDGER.write_file = False

# UAstraLiftSubsystem::ContextJson for Turbolift 1 of the test plan at Deck 1, as `UnrealEditor-Cmd -run=AstraLiftSim -scenario=voice` prints it
LIFT = json.loads('{"car":"tl_a","name":"Turbolift 1","kind":"turbolift","at":"d1","moving":false,"stops":[{"id":"d1","label":"DECK 1","deck_name":"Command","places":["Bridge","Captain\'s Ready Room"]},'
                  '{"id":"d2","label":"DECK 2","deck_name":"CIC & Communications","places":["Combat Information Centre"]},{"id":"d3","label":"DECK 3","deck_name":"Crew Country","places":["Wardroom"]},'
                  '{"id":"d4","label":"DECK 4","deck_name":"Crew Services","places":["Mess Hall","Crew Berthing","Crew Lounge"]},{"id":"d5","label":"DECK 5","deck_name":"Science & Transport","places":["Transporter Room","Astrometrics"]},'
                  '{"id":"d6","label":"DECK 6","deck_name":"Medical","places":["Medbay"]},{"id":"d7","label":"DECK 7","deck_name":"Engineering & Power","places":["Main Engineering","Power Control"]},'
                  '{"id":"d8","label":"DECK 8","deck_name":"Marines & Armory","places":["Armory","Firing Range"]},{"id":"d9","label":"DECK 9","deck_name":"Flight","places":["Flight Deck","Flight Operations"]}]}')
IN_CAR = {"place": "corridors", "pawn": "on_foot", "in_earshot": [], "facing": None, "lift": LIFT}
IN_CORRIDOR = {"place": "corridors", "pawn": "on_foot", "in_earshot": [], "facing": None}


class LiftShip(LocalShip):
    """The local ship plus the lifts: `lift_go` is the game's (UAstraLiftSubsystem::GoByVoice); here it answers like the game does and keeps what it was asked."""

    def __init__(self) -> None:
        super().__init__(stations=True, fight=False)
        self.lift_calls: list[tuple[str, dict[str, Any], str]] = []

    def _execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        if name == "lift_go":
            self.lift_calls.append((name, dict(a), by))
            stop = next((s for s in LIFT["stops"] if s["id"] == a.get("destination")), None)
            if stop is None:
                return {"ok": False, "detail": "Turbolift 1 does not serve that: its stops are " + ", ".join(s["id"] for s in LIFT["stops"])}
            return {"ok": True, "detail": f"Turbolift 1 is going to {stop['label']} · {stop['deck_name'].upper()} (about 12 s)"}
        return super()._execute(name, a, by)


class FakeLLM:
    def __init__(self, *scripts: list[tuple[str, dict[str, Any]]]) -> None:
        self.scripts = list(scripts)
        self.requests: list[dict[str, Any]] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3, extra=None,
                   on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools))
        out = Completion(model=model, provider="fake", cost=0.0005)
        for i, (name, args) in enumerate(self.scripts.pop(0) if self.scripts else []):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out


def speak(text: str, who: str = "computer") -> tuple[str, dict[str, Any]]:
    return "speak", {"speaker": who, "text": text, "tone": "calm"}


class Crew:
    def __init__(self, *scripts: list[tuple[str, dict[str, Any]]]) -> None:
        self.ship = LiftShip()
        self.llm = FakeLLM(*scripts)
        self.said: list[tuple[str, str]] = []

        async def say(speaker: str, text: str, lang: str, tone: str) -> None:
            self.said.append((speaker, text))
        self.agent = BridgeAgent(self.llm, self.ship, say)

    def ctx(self, raw: dict[str, Any] | None) -> context_model.Context:
        return parse_context(raw, self.ship.snapshot())


class ContextTest(unittest.TestCase):
    def test_the_row_the_game_writes_is_read(self) -> None:
        ctx = parse_context(IN_CAR, {})
        self.assertIsNotNone(ctx.lift)
        lift = ctx.lift
        self.assertEqual((lift.car, lift.name, lift.kind, lift.at, lift.moving), ("tl_a", "Turbolift 1", "turbolift", "d1", False))
        self.assertEqual(lift.ids, tuple(f"d{n}" for n in range(1, 10)))
        d7 = lift.stop("d7")
        self.assertEqual((d7.label, d7.deck_name, d7.places), ("DECK 7", "Engineering & Power", ("Main Engineering", "Power Control")))
        self.assertEqual(ctx.place, "corridor")

    def test_a_car_going_somewhere_says_where(self) -> None:
        row = dict(LIFT, moving=True, going_to="d7", at="d4")
        lift = parse_context({**IN_CAR, "lift": row}, {}).lift
        self.assertTrue(lift.moving)
        self.assertIn("moving towards DECK 7", context_model.describe_lift(lift))

    def test_no_car_no_lift(self) -> None:
        self.assertIsNone(parse_context(IN_CORRIDOR, {}).lift)
        self.assertIsNone(parse_context(None, {}).lift)
        for bad in (None, {}, {"stops": []}, {"stops": [{"label": "no id"}]}, {"stops": "nope"}, "lift"):
            self.assertIsNone(context_model.parse_lift(bad), bad)

    def test_the_room_tells_the_model_what_to_do(self) -> None:
        note = context_model.describe(parse_context(IN_CAR, {}))
        for want in ("Turbolift 1", "lift_go", "`computer`", "Main Engineering", "d7 = DECK 7, Engineering & Power", "any language", "never read an id aloud"):
            self.assertIn(want, note)
        self.assertNotIn("Turbolift", context_model.describe(parse_context(IN_CORRIDOR, {})))

    def test_the_shuttle_is_a_car_too(self) -> None:
        row = {"car": "spine_shuttle", "name": "Spine Shuttle", "kind": "shuttle", "at": "sec_b", "moving": False,
               "stops": [{"id": "sec_a", "label": "SECTION A", "places": []}, {"id": "sec_h", "label": "SECTION H", "places": ["Aft Stores"]}]}
        lift = parse_context({**IN_CAR, "lift": row}, {}).lift
        self.assertIn("shuttle car on the Spine line", context_model.describe_lift(lift))
        self.assertEqual(lift_tool(lift)["function"]["parameters"]["properties"]["destination"]["enum"], ["sec_a", "sec_h"])


class ToolsTest(unittest.TestCase):
    def test_the_tool_exists_only_inside_a_car(self) -> None:
        ship = LiftShip().snapshot()
        outside = tools_for(ship, parse_context(IN_CORRIDOR, ship))
        inside = tools_for(ship, parse_context(IN_CAR, ship))
        self.assertNotIn("lift_go", outside.names)
        self.assertFalse(outside.lift)
        self.assertIn("lift_go", inside.names)
        self.assertTrue(inside.lift)
        self.assertNotIn("lift_go", tools_for(ship).names)                      # (no context at all: the bridge as ever)
        self.assertEqual(len(inside.tools), len(outside.tools) + 1)

    def test_it_takes_one_of_the_cars_stops_and_nothing_else(self) -> None:
        tool = lift_tool(parse_context(IN_CAR, {}).lift)["function"]
        props = tool["parameters"]["properties"]["destination"]
        self.assertEqual(props["enum"], [f"d{n}" for n in range(1, 10)])
        self.assertEqual(tool["parameters"]["required"], ["destination"])
        self.assertIn("d6 = DECK 6, Medical (Medbay)", props["description"])
        self.assertIn("Main Engineering", props["description"])

    def test_the_computer_speaks_for_the_lift(self) -> None:
        self.assertIn("computer", SPEAK["function"]["parameters"]["properties"]["speaker"]["enum"])
        self.assertEqual(owner_of("lift_go"), "computer")

    def test_the_old_builds_keep_their_tools(self) -> None:
        legacy = LiftShip().snapshot()
        legacy.pop("stations", None)
        ts = tools_for(legacy, parse_context(IN_CAR, legacy))
        self.assertIn("lift_go", ts.names)
        self.assertIn("intercept", ts.names)                                    # the legacy tools stay beside it


class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_deck_by_its_number_is_taken(self) -> None:
        crew = Crew([("lift_go", {"destination": "d7"}), speak("Deck seven.")])
        turn = await crew.agent.handle("Deck seven", "en", crew.ctx(IN_CAR))
        self.assertEqual(crew.ship.lift_calls, [("lift_go", {"destination": "d7"}, "computer")])
        self.assertEqual(crew.said, [("computer", "Deck seven.")])
        self.assertTrue(turn.actions[0][2]["ok"])
        tools = {t["function"]["name"] for t in crew.llm.requests[0]["tools"]}
        self.assertIn("lift_go", tools)
        # the model was told where it is: the last message carries the car and its stops
        last = str(crew.llm.requests[0]["messages"][-1]["content"])
        self.assertIn("Turbolift 1", last)
        self.assertIn("d7 = DECK 7, Engineering & Power (Main Engineering, Power Control)", last)

    async def test_a_place_by_its_name_is_the_models_to_resolve(self) -> None:
        # the Captain says the place, in another language; what the code receives is a stop's id
        crew = Crew([("lift_go", {"destination": "d7"}), speak("Ingegneria principale, ponte sette.")])
        await crew.agent.handle("portami in sala macchine", "it", crew.ctx(IN_CAR))
        self.assertEqual(crew.ship.lift_calls[0][1], {"destination": "d7"})
        self.assertEqual(crew.said[0][0], "computer")

    async def test_the_computer_is_not_an_officer_outside_a_car(self) -> None:
        # a model that calls the lift where there is none: nothing goes to the ship, and the voice is an officer's (never a speaker that is nobody)
        crew = Crew([("lift_go", {"destination": "d7"}), speak("Deck seven.")])
        turn = await crew.agent.handle("Deck seven", "en", crew.ctx(IN_CORRIDOR))
        self.assertEqual(crew.ship.lift_calls, [])
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertEqual(crew.said, [("xo", "Deck seven.")])
        tools = {t["function"]["name"] for t in crew.llm.requests[0]["tools"]}
        self.assertNotIn("lift_go", tools)

    async def test_a_stop_the_car_does_not_serve_is_the_games_to_refuse_and_the_computer_says_so(self) -> None:
        # the model picks an id the car does not have (the schema should stop it; a provider that does not enforce it gets the game's refusal): the failure is read back
        crew = Crew([("lift_go", {"destination": "d12"})], [speak("This lift does not go to deck twelve; it serves decks one to nine.")])
        turn = await crew.agent.handle("Deck twelve", "en", crew.ctx(IN_CAR))
        self.assertEqual(crew.ship.lift_calls[0][1], {"destination": "d12"})
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertEqual(len(crew.llm.requests), 2)                              # the read-back turn
        self.assertEqual(crew.said[0][0], "computer")
        self.assertIn("does not serve that: its stops are d1", str(crew.llm.requests[1]["messages"][-1]["content"]))

    async def test_words_that_are_not_for_the_lift_leave_it_alone(self) -> None:
        # the Captain asks the XO something in the car: the officer answers, no stop is chosen, the computer is silent
        crew = Crew([speak("Contacts quiet, Captain.", "xo")])
        await crew.agent.handle("Number One, status?", "en", crew.ctx(IN_CAR))
        self.assertEqual(crew.ship.lift_calls, [])
        self.assertEqual(crew.said, [("xo", "Contacts quiet, Captain.")])

    async def test_the_lift_goes_into_the_history_like_any_order(self) -> None:
        crew = Crew([("lift_go", {"destination": "d4"}), speak("Deck four.")], [speak("Deck four.")])
        await crew.agent.handle("Deck four", "en", crew.ctx(IN_CAR))
        names = [c["function"]["name"] for m in crew.agent.history if m.get("tool_calls") for c in m["tool_calls"]]
        self.assertIn("lift_go", names)


if __name__ == "__main__":
    unittest.main()
