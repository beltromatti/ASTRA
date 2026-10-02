"""The mind's server glue for the lifts against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.lift_server -v

A fake game connects to the real `Mind` and sends the Captain's words with the game's `context.lift` (the car he is inside, with the stops
it serves: UAstraLiftSubsystem::ContextJson). What is checked: inside a car the crew's model is given `lift_go` with that car's stops and a
paragraph that says what the ship's computer does, an order for a stop reaches the game as a `command` named `lift_go` carrying one of the
car's stop ids, and the computer's line is voiced as the ship's computer; outside a car there is no such tool and nothing is sent; an older
game build (no `lift` in the context) works as before; the car's stops are what the next car's turn sees (a shuttle is not a turbolift)."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import models
from astra_mind.local_ship import LocalShip
from bench.lift_unit import IN_CAR, IN_CORRIDOR, LIFT
from bench.npc_unit import STEWARD
from bench.npc_server import Model          # (the stations' scripted model, plus the ship's people: a call with only `say` and `pass` is theirs)
from bench.stations_server import FakeGame, FakeTTS

models.LEDGER.write_file = False


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.mind.lang_file = self.mind.lang_file.parent / "captain_lang_test.txt"
        self.game = FakeGame()
        self.tasks = [asyncio.create_task(self.mind.handle_client(self.game)), asyncio.create_task(self.mind.turn_worker()),
                      asyncio.create_task(self.mind.voice.run())]
        await asyncio.sleep(0.05)
        await self.game.push(type="ship_state", state=json.loads(json.dumps(LocalShip(stations=True, fight=False).snapshot())))
        await asyncio.sleep(0.05)

    async def asyncTearDown(self) -> None:
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def say(self, text: str, context: dict[str, Any] | None, wait: float = 0.8) -> None:
        msg: dict[str, Any] = {"type": "player_text", "text": text}
        if context is not None:
            msg["context"] = json.loads(json.dumps(context))
        await self.game.push(**msg)
        await asyncio.sleep(wait)

    def crew_calls(self) -> list[dict[str, Any]]:
        return self.calls("crew")

    async def test_the_computer_takes_the_captain_where_he_says(self) -> None:
        self.model.crew = [("lift_go", {"destination": "d7"}),
                           ("speak", {"speaker": "computer", "text": "Ingegneria principale, ponte sette.", "tone": "calm"})]
        await self.say("portami in sala macchine", IN_CAR)
        self.assertEqual([(c["name"], c["args"], c["by"]) for c in self.game.commands], [("lift_go", {"destination": "d7"}, "computer")])
        self.assertIn(("computer", "Ingegneria principale, ponte sette."), self.game.lines())
        line = next(m for m in self.game.sent if m.get("type") == "line")
        self.assertEqual(line["name"], "Ship's computer")
        call = self.crew_calls()[0]
        self.assertIn("lift_go", call["tools"])
        self.assertIn("Turbolift 1", call["prompt"])                              # the room: which car, and what it serves
        self.assertIn("d7 = DECK 7, Engineering & Power (Main Engineering, Power Control)", call["prompt"])

    async def test_the_tool_offers_this_cars_stops_and_no_others(self) -> None:
        shuttle = {"car": "spine_shuttle", "name": "Spine Shuttle", "kind": "shuttle", "at": "sec_a", "moving": False,
                   "stops": [{"id": "sec_a", "label": "SECTION A", "places": ["Forward Stores"]}, {"id": "sec_c", "label": "SECTION C", "places": []}]}
        sent: list[Any] = []
        original = self.model.chat

        async def spy(**kw: Any):
            sent.append(kw.get("tools"))
            return await original(**kw)
        self.model.chat = spy                                                      # type: ignore[method-assign]
        await self.say("Section C, please", {**IN_CAR, "lift": shuttle})
        crew_tools = [t for t in (sent[-1] or []) if t["function"]["name"] == "lift_go"]
        self.assertEqual(len(crew_tools), 1)
        self.assertEqual(crew_tools[0]["function"]["parameters"]["properties"]["destination"]["enum"], ["sec_a", "sec_c"])
        self.assertIn("shuttle car on the Spine line", self.crew_calls()[0]["prompt"])

    async def test_outside_a_car_there_is_no_lift_tool(self) -> None:
        self.model.crew = [("speak", {"speaker": "xo", "text": "Agli ordini.", "tone": "calm"})]
        await self.say("ponte sette", IN_CORRIDOR)
        self.assertNotIn("lift_go", self.crew_calls()[0]["tools"])
        self.assertNotIn("Turbolift", self.crew_calls()[0]["prompt"])
        self.assertEqual(self.game.commands, [])

    async def test_an_older_game_without_a_lift_in_its_context_works_as_before(self) -> None:
        self.model.crew = [("speak", {"speaker": "xo", "text": "Agli ordini.", "tone": "calm"})]
        await self.say("rapporto", None)
        await self.say("rapporto", {"place": "bridge", "pawn": "seated"})
        self.assertEqual(len(self.crew_calls()), 2)
        for call in self.crew_calls():
            self.assertNotIn("lift_go", call["tools"])
        self.assertIn(("xo", "Agli ordini."), self.game.lines())

    async def test_the_computer_voice_is_a_voice_of_its_own(self) -> None:
        name, voice, aboard = self.server.speaker_identity("computer")
        self.assertEqual((name, voice, aboard), ("Ship's computer", "estelle", False))

    def calls(self, kind: str) -> list[dict[str, Any]]:
        return [c for c in self.model.calls if c["kind"] == kind]

    async def test_the_people_aboard_are_told_a_ride_is_the_computers(self) -> None:
        # a rider in the car, facing him: the model that plays the rider is told the Captain is in a lift car and what asks for a ride is the computer's, so that it does not take the
        # words (their answer would silence the computer's turn); the computer takes him there
        rider = {**STEWARD, "id": "npc412", "name": "Crewman Elias Brandt", "doing": "riding Turbolift 1 to Deck 4", "place": "Turbolift 1", "dist_m": 0.9, "facing": True}
        self.model.npc = []                                                      # (the rider says nothing: it was not for them)
        self.model.crew = [("lift_go", {"destination": "d7"}), ("speak", {"speaker": "computer", "text": "Deck seven.", "tone": "calm"})]
        await self.say("Deck seven", {**IN_CAR, "people": [rider], "in_earshot": ["npc412"], "facing": "npc412"})
        asked = self.calls("npc")
        self.assertEqual(len(asked), 1)
        self.assertIn("inside Turbolift 1, a lift car", asked[0]["user"])
        self.assertIn("for the computer", asked[0]["user"])
        self.assertEqual([(c["name"], c["args"]) for c in self.game.commands], [("lift_go", {"destination": "d7"})])
        self.assertIn(("computer", "Deck seven."), self.game.lines())
        # outside a car the people are not told that
        self.model.calls.clear()
        self.game.commands.clear()
        await self.say("Deck seven", {**IN_CORRIDOR, "people": [rider], "in_earshot": ["npc412"]})
        self.assertNotIn("lift car", self.calls("npc")[0]["user"])

    async def test_a_car_that_is_already_moving_is_told_where(self) -> None:
        going = dict(LIFT, moving=True, going_to="d9", at="d4")
        self.model.crew = [("speak", {"speaker": "computer", "text": "Ponte nove.", "tone": "calm"})]
        await self.say("e adesso dove stiamo andando?", {**IN_CAR, "lift": going})
        self.assertIn("moving towards DECK 9", self.crew_calls()[0]["prompt"])
        self.assertEqual(self.game.commands, [])
        self.assertIn(("computer", "Ponte nove."), self.game.lines())


if __name__ == "__main__":
    unittest.main()
