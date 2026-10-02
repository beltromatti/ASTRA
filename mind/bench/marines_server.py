"""The marine net in the mind's server, against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.marines_server -v

A fake game connects to the real `Mind` (its turn worker, router glue, event queue, voice stage with a fake synthesiser) and sends ship states with a boarding in them, the
boarding's news and the Captain's words. What is checked: the marines tell their own news (a radio voice with the squad leader's own name) and the crew's report turn does not get
it, while the ship's side of the boarding (the alarm, the Captain down) still goes to the crew and the net looks at it too; with the net off the crew reports as before; during a
boarding the marine net is the channel the Captain's words are judged for, the router decides what of them goes out and the net answers and gives its orders to the game as the
game's own `marine_order` and `lockdown`, while the crew hears everything and is told what went out; with no boarding there is no channel and no router call; a Captain in a Falcon
keeps the flight net; the bridge's lines are heard by the marines; a net that cannot answer hands the Captain's words to the XO; and a defect in the net never cuts the crew off from
the ship."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import marines as mm
from astra_mind import models
from astra_mind.openrouter import Completion, ToolCall
from bench.flight_unit import FLYING
from bench.marines_unit import BEATEN, CONTACT, CUT, DEAD, DOCKED, ship_state
from bench.stations_server import FakeGame, FakeTTS, Model as BaseModel

models.LEDGER.write_file = False


class Model(BaseModel):
    """The stations' scripted model, plus the marine net's: its calls carry `say` and `order`, and a script answers them."""

    def __init__(self) -> None:
        super().__init__()
        self.marines: list[list[tuple[str, dict[str, Any]]]] = [[("stay_quiet", {"reason": "x"})]]
        self.marine_calls: list[dict[str, Any]] = []
        self.marine_error = ""
        self.router_part: tuple[str, str] | None = None          # (a phrase in the words, the part of them that goes out): comms lets out only that

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = {t["function"]["name"] for t in (tools or [])}
        if not names and self.router_part and self.router_part[0] in str(messages[-1].get("content", "")):
            self.calls.append({"kind": "router", "model": model, "user": str(messages[-1].get("content", ""))[:160], "tools": names, "watch": False,
                               "system": str(messages[0].get("content", "")), "prompt": " ".join(str(m.get("content", "")) for m in messages)})
            out = Completion(model=model, provider="fake", cost=0.0001)
            out.content = json.dumps({"to_party": self.router_part[1]})
            return out
        if not {"say", "order"} <= names:
            return await super().chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)
        self.marine_calls.append({"model": model, "tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[-1].get("content", ""))})
        out = Completion(model=model, provider="fake", cost=0.0004)
        if self.marine_error:
            out.error = self.marine_error
            return out
        script = self.marines.pop(0) if len(self.marines) > 1 else self.marines[0]
        for i, (name, args) in enumerate(script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"m{len(self.marine_calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out


class MarineServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.mind.lang_file = self.mind.lang_file.parent / "captain_lang_test.txt"
        self.mind.marines.path = lambda: None                                          # (no file of the real campaign is touched)
        self.mind.flight.path = lambda: None
        self.mind.npcs.talk.clear()
        self.game = FakeGame()
        self.tasks = [asyncio.create_task(self.mind.handle_client(self.game)), asyncio.create_task(self.mind.turn_worker()),
                      asyncio.create_task(self.mind.voice.run())]
        await asyncio.sleep(0.05)

    async def asyncTearDown(self) -> None:
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def state(self, st: dict[str, Any] | None = None, wait: float = 0.05) -> None:
        await self.game.push(type="ship_state", state=st or ship_state())
        await asyncio.sleep(wait)

    def later(self, seconds: float) -> None:
        """The net's clock moves (its cadence is in seconds of play: the tests do not wait for them)."""
        moved = self.mind.marines.clock() + seconds
        self.mind.marines.clock = lambda: moved

    def crew_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.model.calls if c["kind"] == "crew"]

    async def event(self, text: str, report: bool = True, st: dict[str, Any] | None = None) -> None:
        await self.state(st)
        await self.game.push(type="event", text=text, report=report)
        await asyncio.sleep(0.05)
        self.later(mm.SETTLE_S + 0.5)
        await self.state(st, 0.3)

    # -- the news
    async def test_the_marines_tell_their_own_news_and_the_crew_does_not(self) -> None:
        self.model.marines = [[("say", {"speaker": "marine_reaction_2", "text": "Contatto, sei ostili. Teniamo.", "tone": "tense", "urgent": True})]]
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Non dovrei parlare.", "tone": "calm"})]
        await self.event(CONTACT)
        await asyncio.sleep(0.3)
        line = next(m for m in self.game.sent if m.get("type") == "line")
        self.assertEqual((line["speaker"], line["name"]), ("marine_reaction_2", "Sergeant Jonas Weber (Reaction 2)"))
        self.assertTrue(line["channel"])                                               # a radio voice, not an officer of the bridge
        self.assertEqual(self.crew_calls(), [])                                        # the crew's report turn never got the event
        self.assertEqual(len(self.model.marine_calls), 1)
        self.assertIn("over the radio, Sergeant Jonas Weber (Reaction 2): Contatto, sei ostili", " ".join(self.mind.game.events))
        self.assertIn(CONTACT, self.mind.game.events)                                   # (it is in the crew's events all the same: it reads it, it does not say it)

    async def test_the_ships_side_of_the_alarm_goes_to_the_crew_and_the_net_looks_at_it_too(self) -> None:
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Abbordaggio al ponte cinque, Capitano.", "tone": "urgent"})]
        self.model.marines = [[("say", {"speaker": "reyes", "text": "Reaction in venticinque secondi, Capitano.", "tone": "focused"})]]
        await self.event(DOCKED)
        await asyncio.sleep(0.3)
        self.assertEqual(len(self.crew_calls()), 1)                                    # the bridge reports the ship's news
        self.assertEqual(len(self.model.marine_calls), 1)                              # and the Major has his own first look
        self.assertEqual({s for s, _ in self.game.lines()}, {"tactical", "reyes"})

    async def test_what_is_not_a_boarding_stays_with_the_crew(self) -> None:
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Tre missili in arrivo.", "tone": "urgent"})]
        await self.event("tactical: three missiles incoming")
        self.assertEqual(len(self.crew_calls()), 1)
        self.assertEqual(self.model.marine_calls, [])

    async def test_with_the_net_off_the_crew_reports_as_before(self) -> None:
        self.mind.marines.disabled = True
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Il sergente Hassan è caduto.", "tone": "grim"})]
        await self.event(DEAD)
        self.assertEqual(len(self.crew_calls()), 1)
        self.assertEqual(self.model.marine_calls, [])
        self.assertIn(("tactical", "Il sergente Hassan è caduto."), self.game.lines())

    async def test_the_aftermath_has_the_floor(self) -> None:
        self.mind.aftermath.muted = True
        self.model.crew = []
        await self.event(BEATEN)
        self.assertEqual((self.model.marine_calls, self.crew_calls()), ([], []))

    async def test_the_bridges_lines_are_heard_by_the_marines(self) -> None:
        self.model.crew = [("speak", {"speaker": "xo", "text": "Marine, tenete il ponte cinque.", "tone": "focused"})]
        await self.event(DOCKED)
        await self.game.push(type="player_text", text="Numero Uno, rapporto")
        await asyncio.sleep(0.6)
        self.assertIn("the bridge: Commander Elena Serra (Executive Officer): Marine, tenete il ponte cinque.", self.mind.marines._recall())

    # -- the Captain talks to them
    async def test_in_a_boarding_the_marine_net_is_the_channel_and_the_captain_is_answered_and_obeyed(self) -> None:
        self.model.router_says = {"Reyes": "party"}
        self.model.marines = [[("order", {"by": "reyes", "squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "reason": "the way into Engineering"}),
                               ("say", {"speaker": "reyes", "text": "Reaction Uno tiene l'ingresso dell'ingegneria.", "tone": "focused"})]]
        self.model.crew = [("speak", {"speaker": "xo", "text": "Non dovrei parlare.", "tone": "calm"})]
        await self.state()
        await self.game.push(type="player_text", text="Reyes, Reaction Uno tenga l'ingresso dell'ingegneria", context={"place": "bridge", "channel": None})
        await asyncio.sleep(0.9)
        self.assertEqual(len([c for c in self.model.calls if c["kind"] == "router"]), 1)         # comms decided first
        orders = [m for m in self.game.commands if m["name"] == "marine_order"]
        self.assertEqual(len(orders), 1)
        self.assertEqual((orders[0]["args"], orders[0]["by"]), ({"squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "note": "the way into Engineering"}, "reyes"))
        self.assertIn(("reyes", "Reaction Uno tiene l'ingresso dell'ingegneria."), self.game.lines())
        reply = next(m for m in self.game.sent if m.get("type") == "line" and m["speaker"] == "reyes")
        self.assertTrue(reply["answer"])                                                # an answer to the Captain: first on the stage
        self.assertEqual(self.crew_calls(), [])                                         # every word went out: nothing is left for the bridge
        self.assertEqual(self.mind.marines.stats["captain"], 1)

    async def test_the_bulkheads_are_the_majors_and_go_to_the_game_as_lockdown(self) -> None:
        self.model.router_says = {"paratie": "party"}
        self.model.marines = [[("bulkheads", {"action": "seal", "doors": ["BLK-D5-14"]}), ("say", {"speaker": "reyes", "text": "Chiudo la paratia.", "tone": "focused"})]]
        await self.state()
        await self.game.push(type="player_text", text="Maggiore, chiuda le paratie sul ponte cinque")
        await asyncio.sleep(0.9)
        self.assertEqual([(m["name"], m["args"], m["by"]) for m in self.game.commands if m["name"] == "lockdown"], [("lockdown", {"sealed": True, "doors": ["BLK-D5-14"]}, "reyes")])

    async def test_what_is_left_for_the_bridge_is_told_what_went_out(self) -> None:
        words = "Reyes, tieni il corridoio; timoniere, prua sull'Acheron"
        self.model.router_part = ("Reyes, tieni il corridoio", "Reyes, tieni il corridoio")
        self.model.crew = [("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-21"}}),
                           ("speak", {"speaker": "helm", "text": "Prua sull'Acheron.", "tone": "focused"})]
        self.model.marines = [[("say", {"speaker": "reyes", "text": "Tengo il corridoio.", "tone": "calm"})]]
        await self.state()
        await self.game.push(type="player_text", text=words)
        await asyncio.sleep(0.9)
        self.assertEqual(len(self.crew_calls()), 1)                                    # the helm's part is the bridge's
        prompt = self.crew_calls()[0]["prompt"]
        self.assertIn("The marine net is live", prompt)
        self.assertIn("«Reyes, tieni il corridoio» went out on the marine net", prompt)           # the officers are told what went out, so nobody says it again
        self.assertIn("Major Reyes and the squad leaders answer them", prompt)
        self.assertIn(("helm", "Prua sull'Acheron."), self.game.lines())
        self.assertIn(("reyes", "Tengo il corridoio."), self.game.lines())

    async def test_words_for_the_bridge_stay_on_the_bridge_in_a_boarding(self) -> None:
        self.model.router_says = {"Helm": "crew"}
        await self.state()
        self.game.commands.clear()
        self.model.crew = [("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-21"}}),
                           ("speak", {"speaker": "helm", "text": "Prua sull'Acheron.", "tone": "focused"})]
        await self.game.push(type="player_text", text="Helm, prua sull'Acheron")
        await asyncio.sleep(0.8)
        self.assertEqual(self.model.marine_calls, [])
        self.assertIn(("helm", "Prua sull'Acheron."), self.game.lines())
        self.assertNotIn("went out on the marine net", self.crew_calls()[-1]["prompt"])           # nothing went out: the crew is told nothing

    async def test_with_no_boarding_there_is_no_channel_and_no_router_call(self) -> None:
        self.model.crew = [("speak", {"speaker": "xo", "text": "I marine sono in caserma, Capitano.", "tone": "calm"})]
        await self.state(ship_state(fight=False))
        await self.game.push(type="player_text", text="Reyes, come vanno i marine?")
        await asyncio.sleep(0.8)
        self.assertEqual(self.model.marine_calls, [])
        self.assertEqual([c for c in self.model.calls if c["kind"] == "router"], [])
        self.assertNotIn("The marine net is live", self.crew_calls()[0]["prompt"])

    async def test_a_captain_in_a_falcon_keeps_the_flight_net(self) -> None:
        self.model.router_says = {"Eagle 2": "party"}
        self.model.crew = []
        st = ship_state(captain=FLYING)
        await self.state(st)
        await self.game.push(type="player_text", text="Eagle 2, resta con me", context={"place": "falcon", "pawn": "falcon", "channel": None})
        await asyncio.sleep(0.9)
        routed = [c for c in self.model.calls if c["kind"] == "router"]
        self.assertEqual(len(routed), 1)
        self.assertIn("This channel is the flight net", routed[0]["system"])
        self.assertNotIn("This channel is the marine net", routed[0]["system"])

    async def test_the_router_is_told_what_the_marine_net_is(self) -> None:
        self.model.router_says = {"Reyes": "party"}
        await self.state()
        await self.game.push(type="player_text", text="Reyes, rapporto")
        await asyncio.sleep(0.6)
        routed = [c for c in self.model.calls if c["kind"] == "router"]
        self.assertEqual(len(routed), 1)
        self.assertIn("This channel is the marine net while boarders are aboard", routed[0]["system"])
        self.assertIn("the marine net (Major Reyes and the squad leaders)", routed[0]["system"])

    async def test_a_reply_to_a_call_on_the_net_reaches_it_after_the_fight(self) -> None:
        self.model.marines = [[("say", {"speaker": "reyes", "text": "Il ponte è nostro, Capitano. Due morti, tre feriti.", "tone": "grim"})],
                              [("say", {"speaker": "reyes", "text": "Grazie, Capitano. Lo dirò ai miei.", "tone": "warm"})]]
        self.model.router_says = {"Grazie": "party"}
        self.model.crew = []
        await self.event(BEATEN)
        self.assertIn(("reyes", "Il ponte è nostro, Capitano. Due morti, tre feriti."), self.game.lines())
        await self.state(ship_state(fight=False), 0.1)                                  # the fight is over
        await self.game.push(type="player_text", text="Grazie, Maggiore. Ottimo lavoro")
        await asyncio.sleep(0.9)
        self.assertIn(("reyes", "Grazie, Capitano. Lo dirò ai miei."), self.game.lines())

    async def test_a_net_that_cannot_answer_hands_the_words_to_the_xo(self) -> None:
        self.model.marine_error = "provider down"
        self.model.router_says = {"Reyes": "party"}
        self.model.crew = [("speak", {"speaker": "xo", "text": "Il Maggiore non risponde, Capitano: ci penso io.", "tone": "calm"})]
        await self.state()
        await self.game.push(type="player_text", text="Reyes, rientrate subito")
        await asyncio.sleep(2.0)
        self.assertTrue(any("the Captain called the marine net and nobody there answered" in c["prompt"] for c in self.crew_calls()))
        self.assertIn(("xo", "Il Maggiore non risponde, Capitano: ci penso io."), self.game.lines())

    # -- the session and its defects
    async def test_a_defect_in_the_net_never_cuts_the_crew_off_from_the_ship(self) -> None:
        with mock.patch.object(self.mind.marines, "feed", side_effect=RuntimeError("a bug in the marine net")):
            await self.state(ship_state(alert="red"))
            self.assertEqual(self.mind.game.state.get("alert"), "red")                  # the state still arrived
        await self.state(ship_state(), 0.1)
        self.assertFalse(self.tasks[0].done())
        with mock.patch.object(self.mind.marines, "on_event", side_effect=RuntimeError("a bug in the marine net")):
            self.model.crew = [("speak", {"speaker": "tactical", "text": "I Mandate sono a bordo.", "tone": "urgent"})]
            await self.game.push(type="event", text=CUT, report=True)
            await asyncio.sleep(0.6)
        self.assertEqual(len(self.crew_calls()), 1)                                     # the crew has the event, as before

    async def test_hello_forgets_the_last_fight(self) -> None:
        await self.event(DOCKED)
        self.assertTrue(self.mind.marines.active)
        await self.game.push(type="hello", client="test")
        await asyncio.sleep(0.2)
        self.assertEqual((self.mind.marines.active, list(self.mind.marines.log), self.mind.marines.squads), (False, [], {}))

    async def test_the_marine_net_is_a_party_the_server_can_answer_on(self) -> None:
        self.assertTrue(self.mind._can_answer("marines"))
        self.assertEqual(self.mind._party_names()["marines"], "the marine net (Major Reyes and the squad leaders)")
        self.mind.marines.disabled = True
        self.assertFalse(self.mind._can_answer("marines"))

    async def test_the_voices_are_known_to_the_stage(self) -> None:
        self.assertEqual(self.server.speaker_identity("reyes"), ("Reyes (Major Tomás Reyes)", "michael", False))
        await self.state()
        name, voice, aboard = self.server.speaker_identity("marine_reaction_1")
        self.assertEqual((name, aboard), ("Sergeant Priya Castillo (Reaction 1)", False))
        self.assertEqual(voice, mm.leader_voice("Sergeant Priya Castillo", "f"))


if __name__ == "__main__":
    unittest.main()
