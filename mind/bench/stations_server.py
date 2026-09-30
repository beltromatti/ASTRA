"""The mind's server glue against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.stations_server -v

A fake game connects to the real `Mind` (its turn worker, router glue, watch loop, event queue) over a fake websocket: it sends
the ship state (with or without consoles), the Captain's words with or without `context`, ship events, and answers the mind's
`command` messages like the game does. The model is a function that answers by what it is asked. What is checked: the
Captain's words with a channel open go to the crew or to the party as the router decides, the crew does not start speaking
before the router has answered, an old game build (no consoles, no context) works as before, a new Captain utterance cuts off
what the crew was doing, and a fight with live consoles brings the officers' watch check and its `station` commands."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import models
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall

models.LEDGER.write_file = False


class Model:
    """The scripted model: answers by what it is asked (which tools it was given, what the system prompt says)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.router_says: dict[str, str] = {}
        self.crew: list[tuple[str, dict[str, Any]]] = []          # what the next crew turn does
        self.watch: list[tuple[str, dict[str, Any]]] = []
        self.enemy_says = "Vous n'avez aucune chance, Capitaine."
        self.slow_crew = 0.0

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500,
                   temperature=0.3, extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None):
        names = {t["function"]["name"] for t in (tools or [])}
        user = str(messages[-1].get("content", ""))
        out = Completion(model=model, provider="fake", cost=0.0005)
        kind = "router" if not names else "enemy" if "transmit" in names else "crew"
        self.calls.append({"kind": kind, "model": model, "user": user[:160], "tools": names, "watch": "WATCH CHECK" in user})
        script: list[tuple[str, dict[str, Any]]] = []
        if kind == "router":
            out.content = next((v for k, v in self.router_says.items() if k in user), "crew")
            return out
        if kind == "enemy":
            script = [("transmit", {"text": self.enemy_says, "tone": "cold"})]
        elif "WATCH CHECK" in user:
            script = list(self.watch)
        else:
            if self.slow_crew:
                await asyncio.sleep(self.slow_crew)
            script = list(self.crew)
        for i, (name, args) in enumerate(script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out

    async def close(self) -> None:
        pass


class FakeGame:
    """A websocket the mind sees as the game: what it sends is read here, what the game sends comes from `push`."""

    def __init__(self) -> None:
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict[str, Any]] = []
        self.commands: list[dict[str, Any]] = []

    async def send(self, data: Any) -> None:
        if isinstance(data, bytes):
            return
        msg = json.loads(data)
        self.sent.append(msg)
        if msg.get("type") == "command":
            self.commands.append(msg)
            await self.inbox.put(json.dumps({"type": "command_result", "id": msg["id"], "ok": True, "detail": "done"}))

    async def push(self, **msg: Any) -> None:
        await self.inbox.put(json.dumps(msg))

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def lines(self) -> list[tuple[str, str]]:
        return [(m["speaker"], m["text"]) for m in self.sent if m.get("type") == "line"]


class FakeTTS:
    sample_rate = 24000

    def supported(self, lang: str) -> bool:
        return True

    def warm(self, *a: Any) -> None:
        pass

    async def stream(self, text: str, voice: str, lang: str):
        yield b"\x00\x00" * 240


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
                      asyncio.create_task(self.mind.voice.run()), asyncio.create_task(self.mind.tactical_watch())]
        await asyncio.sleep(0.05)

    async def asyncTearDown(self) -> None:
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def state(self, ship: LocalShip) -> None:
        await self.game.push(type="ship_state", state=json.loads(json.dumps(ship.snapshot())))
        await asyncio.sleep(0.05)

    async def say(self, text: str, context: dict[str, Any] | None = None, wait: float = 0.6) -> None:
        msg: dict[str, Any] = {"type": "player_text", "text": text}
        if context is not None:
            msg["context"] = context
        await self.game.push(**msg)
        await asyncio.sleep(wait)

    OPEN = {"place": "bridge", "channel": {"party": "T-23", "open": True, "muted": False}}

    async def test_an_older_game_build_works_as_before(self) -> None:
        ship = LocalShip(stations=False, fight=True)
        await self.state(ship)
        self.model.crew = [("intercept", {"contact_id": "T-23", "standoff_km": 6}),
                           ("speak", {"speaker": "helm", "text": "Intercetto il Cocytus, sei chilometri.", "tone": "focused"})]
        await self.say("intercettalo a sei chilometri")
        self.assertEqual([c["name"] for c in self.game.commands], ["intercept"])
        self.assertIn(("helm", "Intercetto il Cocytus, sei chilometri."), self.game.lines())
        crew_call = [c for c in self.model.calls if c["kind"] == "crew"][0]
        self.assertNotIn("station", crew_call["tools"])
        self.assertIn("intercept", crew_call["tools"])

    async def test_with_a_channel_open_orders_stay_aboard_and_words_to_the_party_go_out(self) -> None:
        await self.state(LocalShip(stations=True, fight=True))
        self.model.crew = [("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-23"]}}),
                           ("speak", {"speaker": "tactical", "text": "Fuoco continuo sul Cocytus.", "tone": "focused"})]
        await self.say("fuoco sul cocytus", self.OPEN)                            # an order, though the Cocytus's captain is on the line
        self.assertEqual([c["name"] for c in self.game.commands], ["station"])
        self.assertEqual([c for c in self.model.calls if c["kind"] == "enemy"], [])
        self.game.commands.clear()
        self.mind.enemy.open_channel("T-23")
        await self.say("qui il capitano dell'aquila, fermatevi o verrete annientati", self.OPEN, wait=0.8)
        self.assertEqual(self.game.commands, [])                                     # the crew never saw it
        self.assertEqual(len([c for c in self.model.calls if c["kind"] == "crew"]), 1)
        self.assertTrue(any(s == self.mind.enemy.speaker for s, _ in self.game.lines()))   # the enemy answered

    async def test_the_playtest_misroutes_now_reach_the_crew(self) -> None:
        await self.state(LocalShip(stations=True, fight=True))
        self.mind.enemy.open_channel("T-23")
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Railgun e laser pronti, otto missili in cella.", "tone": "calm"})]
        for text in ("rapporto armamenti", "ci sono navi nemiche"):
            await self.say(text, self.OPEN, wait=0.4)
        self.assertEqual(len([c for c in self.model.calls if c["kind"] == "crew"]), 2)
        self.assertEqual([c for c in self.model.calls if c["kind"] == "enemy"], [])

    async def test_an_open_case_starts_the_crew_at_once_and_holds_it_until_the_router_answers(self) -> None:
        await self.state(LocalShip(stations=True, fight=True))
        self.mind.enemy.open_channel("T-23")
        self.model.router_says = {"non deve finire": "party"}
        self.model.crew = [("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-23"]}})]
        await self.say("ascolta cocytus non deve finire cosi", self.OPEN, wait=1.0)
        self.assertEqual(self.game.commands, [])                                     # the held crew turn did nothing
        self.assertTrue(any(c["kind"] == "router" for c in self.model.calls))
        self.assertTrue(any(c["kind"] == "enemy" for c in self.model.calls))

    async def test_an_open_case_the_router_gives_to_the_crew(self) -> None:
        await self.state(LocalShip(stations=True, fight=True))
        self.mind.enemy.open_channel("T-23")
        self.model.router_says = {"che fanno adesso": "crew"}
        self.model.crew = [("speak", {"speaker": "sensors", "text": "Il Cocytus chiude a otto chilometri.", "tone": "calm"})]
        await self.say("che fanno adesso", self.OPEN, wait=1.0)
        self.assertIn(("sensors", "Il Cocytus chiude a otto chilometri."), self.game.lines())

    async def test_the_captain_cuts_off_a_report_in_progress(self) -> None:
        ship = LocalShip(stations=True, fight=True)
        await self.state(ship)
        self.model.slow_crew = 2.0
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Tre missili in arrivo.", "tone": "urgent"})]
        await self.game.push(type="event", text="tactical: three missiles incoming", report=True)
        await asyncio.sleep(0.6)                                                   # the report turn is in its (slow) model call
        self.model.slow_crew = 0.0
        self.model.crew = [("speak", {"speaker": "xo", "text": "Sì: scudi a prua.", "tone": "focused"})]
        await self.say("scudi", wait=0.6)
        said = [t for _, t in self.game.lines()]
        self.assertIn("Sì: scudi a prua.", said)
        self.assertNotIn("Tre missili in arrivo.", said)

    async def test_a_fight_with_consoles_brings_the_watch_and_its_commands(self) -> None:
        ship = LocalShip(stations=True, fight=True)
        self.mind.watch.quiet_s = 0.0
        self.mind.watch.settle_s = 0.1
        self.mind.watch.min_gap_s = 0.5
        self.model.watch = [("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-23"}}),
                            ("speak", {"speaker": "helm", "text": "Prua sul Cocytus.", "tone": "focused"})]
        await self.state(ship)
        await asyncio.sleep(3.5)                                                   # the loop ticks every 2 s
        watch_calls = [c for c in self.model.calls if c["watch"]]
        self.assertTrue(watch_calls, self.model.calls)
        self.assertEqual(watch_calls[0]["model"], models.role("watch").model)
        self.assertIn(("station", "helm"), [(c["name"], c["args"]["station"]) for c in self.game.commands])
        self.assertIn(("helm", "Prua sul Cocytus."), self.game.lines())

    async def test_no_watch_on_an_older_build(self) -> None:
        self.mind.watch.quiet_s = 0.0
        await self.state(LocalShip(stations=False, fight=True))
        await asyncio.sleep(2.5)
        self.assertEqual([c for c in self.model.calls if c["watch"]], [])


if __name__ == "__main__":
    unittest.main()
