"""The war of the March in the mind's server, against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.march_server -v

A fake game connects to the real `Mind` and chooses a campaign; ship states, the game's events and the Captain's words go in as the game sends them. What is checked: a campaign
starts the March (the director is its omniscient showrunner, the war map follows it, the holo table gets the fleets), the March's clock follows the game's state, a fleet of the
Mandate that comes to the Aquila's system reaches the game as a `director_beat` of the ships it has, Vice Admiral Rourke answers the Captain on the fleet net with the war in front
of him, a major battle ends a chapter of the story, the director cannot conjure forces (and what it may do, `reveal` and `pressure`, is true), the bridge reads the front, and with
the March off (ASTRA_MARCH=0) the war is played as before."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from typing import Any
from unittest import mock

from astra_mind import models
from astra_mind.march import Fleet, Order, Ship
from astra_mind.openrouter import Completion, ToolCall
from bench.stations_server import FakeGame, FakeTTS, Model as BaseModel

models.LEDGER.write_file = False


class Clock:
    t = 5000.0

    def __call__(self) -> float:
        return self.t


class Model(BaseModel):
    """The stations' scripted model, plus the March's: the strategic minds' calls (`fleet_order`...) and the director's (`start_beat`) are answered by scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.strategy: dict[str, list[tuple[str, dict[str, Any]]]] = {"astra": [("no_change", {"reason": "nothing to change"})], "mandate": [("no_change", {"reason": "nothing"})]}
        self.strategy_calls: list[dict[str, Any]] = []
        self.director: list[tuple[str, dict[str, Any]]] = [("start_beat", {"type": "none", "why": "the war runs", "crew_mood": "steady"})]
        self.director_calls: list[dict[str, Any]] = []
        self.finale_calls = 0

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = {t["function"]["name"] for t in (tools or [])}
        if "fleet_order" in names:
            side = "astra" if "Vice Admiral Adrian Rourke" in str(messages[0].get("content", "")) else "mandate"
            self.strategy_calls.append({"side": side, "tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[1].get("content", ""))})
            script = self.strategy[side]
        elif "start_beat" in names:
            self.director_calls.append({"tools": names, "system": str(messages[0].get("content", ""))})
            script = self.director
        else:
            return await super().chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)
        out = Completion(model=model, provider="fake", cost=0.0015, prompt_tokens=3000, completion_tokens=150)
        for i, (name, args) in enumerate(script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"s{len(self.strategy_calls)}{len(self.director_calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out


class Game(FakeGame):
    """The fake game, answering a `director_beat` with the contact ids it would give (the March maps its ships to them)."""
    next_id = 40

    async def send(self, data: Any) -> None:
        if isinstance(data, bytes):
            return
        msg = json.loads(data)
        self.sent.append(msg)
        if msg.get("type") == "command":
            self.commands.append(msg)
            detail = "done"
            if msg["name"] == "director_beat" and msg["args"]["beat"].get("groups"):
                beat = msg["args"]["beat"]
                n = sum(len(g["ships"]) for g in beat["groups"])
                ids = [f"T-{self.next_id + i}" for i in range(n)]
                self.next_id += n
                detail = f"{beat['type']} scheduled in {beat.get('delay_s', 30)} s; contact ids {', '.join(ids)}; the first is the group's leader"
            await self.inbox.put(json.dumps({"type": "command_result", "id": msg["id"], "ok": True, "detail": detail}))


def ship_state(**kw: Any) -> dict[str, Any]:
    st = {"hull_pct": 100, "alert": "green", "contacts": [], "janus_gate": "Janus Gate: bearing 087 mark 3, 52.3 km, bound to Cassia, Thule", "location": "Aurelia System",
          "captain": "on the bridge", "_astra_groups": {"your_groups": []}, "_mandate": {"your_ships": [], "your_groups": []}}
    st.update(kw)
    return st


class MarchServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"ASTRA_MARCH": "1", "ASTRA_STRATEGY_MINDS": "1"})
        self.env.start()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.mind.lang_file = self.mind.lang_file.parent / "captain_lang_test.txt"
        self.mind.director.war.save_path = os.path.join(self.tmp.name, "war.json")     # (no file of the real campaign is touched)
        self.mind.director.war.persist = False
        self.mind.marines.path = lambda: None
        self.mind.flight.path = lambda: None
        self.mind.npcs.talk.clear()
        self.game = Game()
        self.tasks = [asyncio.create_task(self.mind.handle_client(self.game)), asyncio.create_task(self.mind.turn_worker()),
                      asyncio.create_task(self.mind.voice.run())]
        await asyncio.sleep(0.05)
        self.clock = Clock()

    async def asyncTearDown(self) -> None:
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.mind.enemy.reset()
        self.env.stop()
        self.tmp.cleanup()

    async def campaign(self, mode: str = "new") -> None:
        await self.game.push(type="hello")
        await asyncio.sleep(0.05)
        await self.game.push(type="campaign", mode=mode)
        await asyncio.sleep(0.15)
        if self.mind.march_glue is not None:
            self.mind.march_glue.clock = self.clock
            self.mind.march_glue._last = None
            self.mind.march.save_path = None                                       # (and the March writes nothing either)

    async def state(self, st: dict[str, Any] | None = None, seconds: float = 0.0, wait: float = 0.03) -> None:
        self.clock.t += seconds
        await self.game.push(type="ship_state", state=st or ship_state())
        await asyncio.sleep(wait)

    async def play(self, seconds: int, st: dict[str, Any] | None = None) -> None:
        for _ in range(seconds):
            await self.state(st, 1.0, 0.004)
        await asyncio.sleep(0.05)

    def beats(self) -> list[dict[str, Any]]:
        return [m["args"]["beat"] for m in self.game.commands if m["name"] == "director_beat"]

    # -- the campaign
    async def test_a_new_campaign_starts_the_march(self) -> None:
        self.assertIsNone(self.mind.march_glue)                                       # (nothing before the Captain chooses)
        await self.campaign("new")
        g = self.mind.march_glue
        self.assertTrue(g is not None and g.active)
        self.assertIs(self.mind.director.march, g)
        self.assertIs(self.mind.director.war.authority, self.mind.march)
        self.assertIsNotNone(self.mind.director.rourke)
        self.assertIsNotNone(self.mind.war.strategic)
        sector = [m for m in self.game.commands if m["name"] == "sector"]
        self.assertTrue(sector)
        march = sector[-1]["args"]["march"]                                           # the holo table gets the fleets (ASTRA's own, the enemy's as its eyes hold them)
        self.assertTrue(any(f["id"] == "F-A1" for f in march["fleets"]))
        self.assertFalse(any(f["id"] == "F-M4" for f in march["fleets"]))

    async def test_the_march_follows_the_games_state_and_the_clock(self) -> None:
        await self.campaign("new")
        t0 = self.mind.march.t
        await self.play(30)
        self.assertGreaterEqual(self.mind.march.t - t0, 25)
        self.assertLessEqual(self.mind.march.t - t0, 31)
        self.clock.t += 600.0                                                          # (the game was paused: that is not war time)
        await self.state()
        self.assertLess(self.mind.march.t - t0, 40)

    async def test_hello_stops_the_march_until_the_captain_chooses(self) -> None:
        await self.campaign("new")
        await self.game.push(type="hello")
        await asyncio.sleep(0.1)
        self.assertFalse(self.mind.march_glue.active)

    async def test_with_the_march_off_the_war_is_played_as_before(self) -> None:
        with mock.patch.dict(os.environ, {"ASTRA_MARCH": "0"}):
            await self.campaign("new")
        self.assertIsNone(self.mind.march_glue)
        self.assertIsNone(self.mind.director.march)
        self.assertIsNone(self.mind.director.war.authority)

    # -- the war reaches the Aquila
    async def test_a_mandate_fleet_that_comes_to_the_aquilas_system_reaches_the_game_as_its_ships(self) -> None:
        await self.campaign("new")
        m = self.mind.march
        for f in list(m.fleets.values()):
            if f.status != "real":
                f.where = "Erebus" if f.side == "mandate" else f.where
        m.fleets.clear()
        raid = Fleet("F-M9", "mandate", "Test Raid", [Ship("acheron", "Hecate"), Ship("styx", "Mormo"), Ship("styx", "Empusa")], "Thule", 1.0, 0.8,
                     Order("assault", "Aurelia", "bold", False, "admiral", "test", 0.0), status="ready", arrived_t=m.t, origin="Thule",
                     commander={"name": "Warden Corvin Tarsk", "rank": "Warden (group commander)", "bio": "x", "voice": "charles", "gender": "m"})
        m.fleets["F-M9"] = raid
        m.order("mandate", "F-M9", "assault", "Aurelia", by="admiral", reason="take the Gate")
        await self.play(260)
        beats = self.beats()
        self.assertEqual(len(beats), 1)
        self.assertEqual(beats[0]["type"], "raid")
        self.assertEqual(sorted(sp["name"] for g in beats[0]["groups"] for sp in g["ships"]), ["Empusa", "Hecate", "Mormo"])
        self.assertEqual(raid.status, "real")
        from astra_mind.enemy import COMMANDERS
        self.assertTrue(any(c.get("name") == "Warden Corvin Tarsk" for c in COMMANDERS.values()))       # (the new commander has a mind and a voice)

    # -- Rourke
    async def test_rourke_answers_the_captain_on_the_fleet_net_with_the_war_in_front_of_him(self) -> None:
        await self.campaign("new")
        self.model.strategy["astra"] = [("tell_captain", {"text": "Il grosso è a Cassia, Capitano: due Gate.", "tone": "measured"})]
        await self.state()
        await self.mind._to_party("fleet", "Ammiraglio, dov'è il grosso della flotta?", "it")
        await asyncio.sleep(0.4)
        self.assertIn(("admiral", "Il grosso è a Cassia, Capitano: due Gate."), self.game.lines())
        call = [c for c in self.model.strategy_calls if c["side"] == "astra"][-1]
        self.assertIn("Ammiraglio, dov'è il grosso della flotta?", call["user"])
        self.assertIn("F-A1", call["user"])                                            # (the whole picture: the main body, where it is, what it was told)
        self.assertEqual([c for c in self.model.director_calls], [])                   # (the old admiral prompt did not answer: Rourke is the March's mind now)
        reply = next(m for m in self.game.sent if m.get("type") == "line" and m["speaker"] == "admiral")
        self.assertTrue(reply["answer"])
        self.assertIn("Rourke to the Aquila: Il grosso è a Cassia, Capitano: due Gate.", self.mind.director.campaign)

    # -- the story
    async def test_a_major_battle_ends_a_chapter_of_the_story(self) -> None:
        await self.campaign("new")
        ended: list[str] = []

        async def end_arc(result: str, lang: str, state: dict[str, Any]) -> None:
            ended.append(result)
        self.mind.director._end_arc = end_arc
        m = self.mind.march
        m.real_t0 = m.t - 600
        m.real_tally["mandate"] = {"lost": 9, "names": ["a", "b"], "points": 12.0, "capital": True}
        await self.game.push(type="event", text="director: engagement over — victory: no hostile ship left; Aquila hull 62%, 12 missiles; our fleet: ASN Valiant in action", report=True)
        await asyncio.sleep(0.4)
        self.assertEqual(len(ended), 1)
        self.assertIn("engagement over", ended[0])
        self.assertTrue(any(e.kind == "battle_end" for e in m.events))

    # -- the director
    async def test_the_director_conjures_no_force_and_what_it_may_do_is_true(self) -> None:
        await self.campaign("new")
        m = self.mind.march
        self.model.director = [("start_beat", {"type": "raid", "why": "the war needs a fight", "crew_mood": "tense",
                                               "ships": [{"class": "styx", "name": "Phantom"}]}),
                               ("reveal", {"side": "astra", "fleet": "F-M4", "how": "a defector from Erebus"}),
                               ("pressure", {"side": "mandate", "text": "The Hall wants Aurelia before the harvest.", "minutes": 45})]
        self.mind.game = self.mind.game
        await self.state()
        await self.mind.director._next_beat("it", self.mind._battle_state())
        self.assertEqual(self.beats(), [])                                              # (no raid: the war's forces are the March's)
        self.assertIn("F-M4", m.tracks["astra"])                                        # the fleet is really there: ASTRA's intelligence has a track on it
        self.assertEqual(m.tracks["astra"]["F-M4"].system, "Erebus")
        self.assertIn("Hall wants Aurelia", m.home_orders["mandate"]["text"])
        call = self.model.director_calls[-1]
        self.assertEqual(call["tools"], {"start_beat", "war_news", "reveal", "pressure"})   # (no `transmit`: Rourke is nobody's puppet)
        self.assertIn("THE WAR, AS IT TRULY IS", call["system"])
        self.assertIn("F-M4", call["system"])                                           # the omniscient director sees both sides' fleets
        self.assertTrue(any("was not played" in c for c in self.mind.director.campaign))

    async def test_the_director_cannot_move_a_system_by_telling(self) -> None:
        await self.campaign("new")
        self.model.director = [("start_beat", {"type": "none", "why": "x", "crew_mood": "steady"}),
                               ("war_news", {"text": "Cassia has fallen.", "system": "Cassia", "owner": "mandate", "threat": 3})]
        await self.state()
        await self.mind.director._next_beat("en", self.mind._battle_state())
        self.assertEqual(self.mind.director.war.systems["Cassia"]["owner"], "astra")      # (the war decides who holds what)

    # -- the bridge
    async def test_the_bridge_reads_the_front(self) -> None:
        await self.campaign("new")
        from astra_mind.crew import bridge_now
        await self.play(3)
        text = bridge_now(self.mind.game.state, [], "")
        self.assertIn("The front, as Fleet knows it", text)
        self.assertIn("7th Fleet Main Body", text)
        self.assertNotIn("Interdiction Fleet Main Body", text)                           # (nothing the enemy's that its eyes do not hold)


if __name__ == "__main__":
    unittest.main()
