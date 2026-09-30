"""The mind's server glue for the ship's people against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.npc_server -v

A fake game connects to the real `Mind` and sends the Captain's words with the game's `context.people` (the crew within earshot, from
the life simulation). What is checked: someone near is asked (one small-model call) and, when they answer, the line is voiced as the
answer to the Captain and the bridge's own turn stays silent; when nobody answers the officers take the words as before; with nobody
near there is no call at all; the officers are told the Captain is among the crew; and the Captain speaking again cuts the crew
member off."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from astra_mind import models
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from bench.stations_server import FakeGame, FakeTTS, Model as BaseModel
from bench.npc_unit import ENGINEER, STEWARD

models.LEDGER.write_file = False


class Model(BaseModel):
    """The scripted model of the stations' server test, plus the ship's people: a call with only `say` is theirs."""

    def __init__(self) -> None:
        super().__init__()
        self.npc: list[tuple[str, dict[str, Any]]] = []
        self.npc_delay = 0.0

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = {t["function"]["name"] for t in (tools or [])}
        if names == {"say"}:
            self.calls.append({"kind": "npc", "model": model, "user": str(messages[-1].get("content", ""))[:400], "tools": names, "watch": False,
                               "system": str(messages[0].get("content", ""))})
            out = Completion(model=model, provider="fake", cost=0.0002)
            if self.npc_delay:
                await asyncio.sleep(self.npc_delay)
            for i, (name, args) in enumerate(self.npc):
                tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"n{len(self.calls)}_{i}")
                out.tool_calls.append(tc)
                if on_tool_call is not None:
                    r = on_tool_call(tc)
                    if hasattr(r, "__await__"):
                        await r
            return out
        return await super().chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.tmp = tempfile.TemporaryDirectory()
        self.mind.npcs.store = Path(self.tmp.name) / "talk.json"
        self.mind.npcs.talk.clear()
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
        self.tmp.cleanup()

    async def say(self, text: str, people: list[dict[str, Any]] | None, wait: float = 0.8, **ctx: Any) -> None:
        context = {"place": "corridors", "place_name": "DECK 7 · MACHINERY", "pawn": "on_foot", "in_earshot": [p["id"] for p in people or []],
                   "facing": next((p["id"] for p in people or [] if p.get("facing")), None), "channel": None, **ctx}
        if people is not None:
            context["people"] = people
        await self.game.push(type="player_text", text=text, context=context)
        await asyncio.sleep(wait)

    def calls(self, kind: str) -> list[dict[str, Any]]:
        return [c for c in self.model.calls if c["kind"] == kind]

    async def test_the_one_the_captain_looks_at_answers_and_the_bridge_stays_out(self) -> None:
        self.model.npc = [("say", {"speaker": "npc17", "text": "Un condotto ha ceduto, Capitano; il fuoco è spento.", "tone": "tense"})]
        self.model.crew = [("speak", {"speaker": "xo", "text": "Capitano, sta parlando con la squadra macchine.", "tone": "calm"})]
        await self.say("cos'è successo qui?", [ENGINEER, STEWARD])
        lines = self.game.lines()
        self.assertIn(("npc17", "Un condotto ha ceduto, Capitano; il fuoco è spento."), lines)
        self.assertEqual([s for s, _ in lines], ["npc17"])                      # the officers said nothing: the words were for the crew member
        self.assertEqual(len(self.calls("npc")), 1)
        line = next(m for m in self.game.sent if m.get("type") == "line")
        self.assertEqual(line["name"], "Petty Officer Amara Diallo")             # the roster's name, the voice stage knows the speaker
        self.assertEqual(self.game.commands, [])

    async def test_words_for_the_bridge_are_not_taken_by_the_crew_nearby(self) -> None:
        self.model.npc = []                                                      # the crew member says nothing: not meant for them
        self.model.crew = [("speak", {"speaker": "helm", "text": "Rotta zero-nove-zero, Capitano.", "tone": "focused"})]
        await self.say("Timoniere, rotta zero-nove-zero", [ENGINEER], wait=1.0)
        self.assertEqual(len(self.calls("npc")), 1)                              # they were asked
        self.assertIn(("helm", "Rotta zero-nove-zero, Capitano."), self.game.lines())    # and the bridge answered, as before

    async def test_nobody_near_nobody_asked(self) -> None:
        self.model.crew = [("speak", {"speaker": "xo", "text": "Agli ordini.", "tone": "calm"})]
        await self.say("XO, rapporto", None, wait=0.6)
        await self.say("XO, rapporto", [dict(ENGINEER, dist_m=20.0, facing=False)], wait=0.6)     # too far to be spoken to
        self.assertEqual(self.calls("npc"), [])
        self.assertEqual(len(self.calls("crew")), 2)

    async def test_the_officers_are_told_the_captain_is_among_the_crew(self) -> None:
        self.model.npc = []
        await self.say("come va?", [ENGINEER], wait=0.8)
        crew = self.calls("crew")[0]["user"]
        self.assertIn("face to face with crew members", crew)
        self.assertIn("Petty Officer Amara Diallo", crew)
        room = self.calls("crew")[0]["system"]
        self.assertNotIn("npc17", room)                                          # the officers' room does not name the life's ids

    async def test_the_captain_speaking_again_cuts_the_crew_member_off(self) -> None:
        self.model.npc_delay = 0.6
        self.model.npc = [("say", {"speaker": "npc17", "text": "Tutto bene, Capitano.", "tone": "calm"})]
        self.model.crew = [("speak", {"speaker": "xo", "text": "Sì, Capitano.", "tone": "calm"})]
        await self.say("come va?", [ENGINEER], wait=0.15)
        self.model.npc_delay = 0.0
        self.model.npc = []
        await self.say("XO, rapporto", None, wait=0.9)
        said = [t for _, t in self.game.lines()]
        self.assertNotIn("Tutto bene, Capitano.", said)                          # cut off before they could speak
        self.assertIn("Sì, Capitano.", said)

    async def test_a_new_campaign_is_a_crew_that_does_not_know_the_captain(self) -> None:
        self.model.npc = [("say", {"speaker": "npc17", "text": "Buongiorno, Capitano.", "tone": "calm"})]
        await self.say("buongiorno", [ENGINEER], wait=0.6)
        self.assertTrue(self.mind.npcs.talk)
        await self.game.push(type="campaign", mode="new")
        await asyncio.sleep(0.2)
        self.assertEqual(self.mind.npcs.talk, {})


if __name__ == "__main__":
    unittest.main()
