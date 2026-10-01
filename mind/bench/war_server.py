"""The war minds in the mind's server, against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.war_server -v

A fake game connects to the real `Mind` and sends ship states that carry the battle groups (`_mandate`, `_astra_groups`), the Captain's words, and
answers the mind's `command` messages. What is checked: the Mandate's admiral orders the strike group by `group_order` as the contract says; the
allied captain of the picket thinks, orders and speaks on the fleet net (a radio voice with its own name); the comms officer's `fleet_request` no
longer goes to the ships but to their captain, who answers for it; the XO's `group_order` is the Captain's direct order and is refused when a
flag officer is present; the Captain's words on the fleet net reach the captains and Rourke is silent when they were not for him; the crew's
prompt carries the fleet board."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import models, war_minds
from astra_mind.local_ship import LocalShip
from bench.stations_server import FakeGame, FakeTTS, Model as BaseModel
from bench.war_minds_unit import astra_state, foe, group, mandate_state, member
from bench.war_mock import MockLLM, ScriptPolicy, null_policy

models.LEDGER.write_file = False


class Model(BaseModel):
    """The stations' scripted model, plus the war minds' (their calls carry `no_change`): a scripted policy answers those."""

    def __init__(self) -> None:
        super().__init__()
        self.war = MockLLM(null_policy, latency=0.0)
        self.rourke: list[tuple[str, dict[str, Any]]] = []
        self.rourke_calls: list[str] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = {t["function"]["name"] for t in (tools or [])}
        if "no_change" in names:
            return await self.war.chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)
        if names == {"transmit", "grant"}:                                            # Rourke on the fleet net
            from astra_mind.openrouter import Completion, ToolCall
            self.rourke_calls.append(str(messages[-1].get("content", "")))
            out = Completion(model=model, provider="fake", cost=0.0004)
            for i, (name, args) in enumerate(self.rourke):
                tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"r{len(self.rourke_calls)}_{i}")
                out.tool_calls.append(tc)
                if on_tool_call is not None:
                    r = on_tool_call(tc)
                    if hasattr(r, "__await__"):
                        await r
            return out
        return await super().chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)


def picket(**kw: Any) -> dict[str, Any]:
    return group("7th Fleet picket", 1, [member("T-01", "praetorian", missiles=24), member("T-02", "vigilant", missiles=12)], leader="T-01", **kw)


def battle_state(order: str = "auto", enemies: list | None = None, events: list | None = None, mandate: bool = True) -> dict[str, Any]:
    """What the game's snapshot carries in a fight on the Aquila's picket: the crew's state plus both sides' group views, all of one battle (the
    Praetorian and the Vigilant with the Aquila, the Acheron and two Styx closing from 240)."""
    st = json.loads(json.dumps(LocalShip(stations=True, fight=True).snapshot()))
    foes = enemies if enemies is not None else [foe("group of T-21", [{"id": "T-21", "class": "acheron", "hull_pct": 90, "shields_pct": 86},
                                                                       {"id": "T-22", "class": "styx", "hull_pct": 100, "shields_pct": 100},
                                                                       {"id": "T-23", "class": "styx", "hull_pct": 100, "shields_pct": 100}], 24.0)]
    contacts = [{"id": "T-01", "name": "ASN Praetorian", "class": "praetorian", "status": "friendly", "range_km": 4.5, "bearing_deg": 25, "hull_pct": 100},
                {"id": "T-02", "name": "ASN Vigilant", "class": "vigilant", "status": "friendly", "range_km": 3.0, "bearing_deg": 70, "hull_pct": 100},
                {"id": "T-21", "name": "Acheron", "class": "acheron", "status": "hostile", "range_km": 24.0, "bearing_deg": 240, "hull_pct": 90, "shields_pct": 86},
                {"id": "T-22", "name": "Styx", "class": "styx", "status": "hostile", "range_km": 26.0, "bearing_deg": 238, "hull_pct": 100, "shields_pct": 100},
                {"id": "T-23", "name": "Cocytus", "class": "styx", "status": "hostile", "range_km": 27.0, "bearing_deg": 242, "hull_pct": 100, "shields_pct": 100}]
    st.update(astra_state([picket(order=order) if order != "auto" else picket()], foes, events, speed_mps=0, heading_deg=45, contacts=contacts))
    if mandate:
        strike = group("Strike Group Varek Solm", 2, [member("T-21", "acheron", missiles=32), member("T-22"), member("T-23")], leader="T-21")
        st.update(mandate_state([strike], [{"label": "group of T-01", "ships": [{"id": "T-01", "class": "praetorian", "hull_pct": 100, "shields_pct": 100},
                                                                               {"id": "T-02", "class": "vigilant", "hull_pct": 100, "shields_pct": 100},
                                                                               {"id": "AQUILA", "class": "aquila"}], "range_km": 24.0,
                                                  "nearest_ship_km": 22.0, "bearing_deg": 60}], boss="T-21"))
    return st


class WarServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.mind.lang_file = self.mind.lang_file.parent / "captain_lang_test.txt"
        self.mind.npcs.talk.clear()
        self.game = FakeGame()
        self.tasks = [asyncio.create_task(self.mind.handle_client(self.game)), asyncio.create_task(self.mind.turn_worker()),
                      asyncio.create_task(self.mind.voice.run())]
        await asyncio.sleep(0.05)
        self.patch = mock.patch.object(war_minds.random, "uniform", lambda a, b: 1.0)
        self.patch.start()

    async def asyncTearDown(self) -> None:
        self.patch.stop()
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def state(self, st: dict[str, Any], wait: float = 0.05) -> None:
        await self.game.push(type="ship_state", state=st)
        await asyncio.sleep(wait)

    def at(self, seconds: float) -> None:
        """The war minds' clock moves (the cadence is in battle seconds: the tests do not wait for them)."""
        self.mind.war.clock = lambda t=self.mind.war.clock() + seconds: t

    def war_calls(self, side: str) -> list[dict[str, Any]]:
        return [c for c in self.model.war.calls if side in (c["seat"] or "")]

    async def test_the_mandate_admiral_orders_the_strike_group_through_the_contract(self) -> None:
        self.model.war.policy = ScriptPolicy([("group_order", {"group": "Strike Group Varek Solm", "order": "attack", "target": "T-01", "range_km": 3.5,
                                                               "reason": "kill the Praetorian first"})])
        await self.state(battle_state())
        self.at(10)
        await self.state(battle_state(), 0.2)
        cmds = [m for m in self.game.commands if m["name"] == "group_order" and m["args"].get("side") == "mandate"]
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0]["args"], {"group": "Strike Group Varek Solm", "order": "attack", "target": "T-01", "range_km": 3.5, "side": "mandate", "by": "admiral"})
        self.assertEqual(cmds[0]["by"], "admiral")
        self.assertNotIn("reason", cmds[0]["args"])
        self.assertEqual(self.war_calls("mandate")[0]["model"], models.role("admiral").model)

    async def test_the_picket_commander_orders_and_speaks_with_her_own_voice(self) -> None:
        self.model.war.policy = ScriptPolicy([("group_order", {"group": "7th Fleet picket", "order": "screen", "target": "AQUILA", "reason": "cover the carrier"}),
                                              ("say", {"to": "aquila", "text": "Aquila, Praetorian: contacts bearing zero-seven-zero, we are closing on your bow.", "tone": "focused"})])
        await self.state(battle_state(mandate=False))
        self.at(10)
        await self.state(battle_state(mandate=False), 0.3)
        orders = [m for m in self.game.commands if m["name"] == "group_order"]
        self.assertEqual([(m["args"]["by"], m["args"]["side"], m["by"]) for m in orders], [("commander", "astra", "commander")])
        line = next(m for m in self.game.sent if m.get("type") == "line")
        self.assertEqual(line["speaker"], "castellan")
        self.assertEqual(line["name"], "Captain Rhea Castellan (the battleship ASN Praetorian)")
        self.assertTrue(line["channel"])                                               # a radio voice, not an officer of the bridge
        self.assertIn("over the radio, Captain Rhea Castellan", " ".join(self.mind.game.events))

    async def test_a_fleet_request_goes_to_the_captain_not_to_the_ships(self) -> None:
        self.model.war.policy = ScriptPolicy([("no_change", {"reason": "first look"})], [
            ("group_order", {"group": "7th Fleet picket", "order": "attack", "target": "T-21", "reason": "the Captain asks"}),
            ("say", {"to": "aquila", "text": "Aye, Captain: all guns on the Acheron.", "tone": "focused"})])
        await self.state(battle_state(mandate=False))
        self.at(10)
        await self.state(battle_state(mandate=False), 0.2)
        self.game.commands.clear()
        self.model.crew = [("fleet_request", {"ship": "T-01", "request": "focus_fire", "target": "T-21"}),
                           ("speak", {"speaker": "comms", "text": "Praetorian, fuoco concentrato sull'Acheron.", "tone": "focused"})]
        await self.game.push(type="player_text", text="Praetorian, concentra il fuoco sull'Acheron")
        await asyncio.sleep(0.5)
        names = [(m["name"], m["args"].get("request")) for m in self.game.commands]
        self.assertNotIn(("fleet_request", "focus_fire"), names)                       # the ships were not told directly
        self.assertIn("group_order", [m["name"] for m in self.game.commands])          # the captain gave the order, by his own judgement
        self.assertIn(("castellan", "Aye, Captain: all guns on the Acheron."), self.game.lines())
        self.assertIn(("comms", "Praetorian, fuoco concentrato sull'Acheron."), self.game.lines())
        self.assertIn("concentrate your fire on the target", self.war_calls("astra")[-1]["user"])

    async def test_a_fleet_request_to_a_ship_nobody_commands_goes_the_old_way(self) -> None:
        await self.state(battle_state(mandate=False))
        self.model.crew = [("fleet_request", {"ship": "T-77", "request": "stand_off"}),
                           ("speak", {"speaker": "comms", "text": "T-77, mantenga la distanza.", "tone": "calm"})]
        await self.game.push(type="player_text", text="T-77, stand off")
        await asyncio.sleep(0.4)
        self.assertEqual([(m["args"]["ship"], m["args"]["request"]) for m in self.game.commands if m["name"] == "fleet_request"], [("T-77", "stand_off")])

    async def test_the_xo_gives_a_direct_order_when_the_captain_is_the_senior_officer(self) -> None:
        await self.state(battle_state(mandate=False))
        self.model.crew = [("group_order", {"group": "7th Fleet picket", "order": "attack", "target": "T-21", "range_km": 4}),
                           ("speak", {"speaker": "xo", "text": "Il gruppo attacca l'Acheron, Capitano.", "tone": "focused"})]
        await self.game.push(type="player_text", text="Gruppo, attacca l'Acheron, è un ordine")
        await asyncio.sleep(0.4)
        sent = [m for m in self.game.commands if m["name"] == "group_order"]
        self.assertEqual(len(sent), 1)
        self.assertEqual((sent[0]["args"]["side"], sent[0]["args"]["by"], sent[0]["by"]), ("astra", "captain", "captain"))
        self.assertIn("direct order", self.mind.war.recall("astra"))
        crew = [c for c in self.model.calls if c["kind"] == "crew"][0]
        self.assertIn("group_order", crew["tools"])
        self.assertIn("The fleet: our battle groups", crew["prompt"])                       # the board changes with every state: it rides with the turn's last message...
        self.assertIn("Captain Rhea Castellan", crew["prompt"])
        self.assertNotIn("The fleet: our battle groups", crew["system"])                    # ...and never in the system prompt (the provider's cache covers that)
        self.assertNotIn("Captain Rhea Castellan", crew["system"])

    async def test_the_xo_may_not_order_the_groups_of_a_flag_officer(self) -> None:
        await self.state(battle_state(mandate=False))
        self.mind.war.register_ally("T-02", {"name": "Rear Admiral Odile Fraser", "rank": "Rear Admiral", "ship": "the Vigilant", "bio": "", "voice": "anna", "precedence": 1})
        self.model.crew = [("group_order", {"group": "7th Fleet picket", "order": "hold"})]
        await self.game.push(type="player_text", text="gruppo, tieni la posizione")
        await asyncio.sleep(0.4)
        self.assertEqual([m for m in self.game.commands if m["name"] == "group_order"], [])

    async def test_the_captain_on_the_fleet_net_reaches_the_captains_and_rourke_may_stay_silent(self) -> None:
        self.model.war.policy = ScriptPolicy([("no_change", {"reason": "first look"})], [("say", {"to": "aquila", "text": "Tre navi in linea, Capitano.", "tone": "calm"})])
        await self.state(battle_state(mandate=False))
        self.at(10)
        await self.state(battle_state(mandate=False), 0.2)
        self.model.rourke = []                                                           # the words were for the Praetorian: Fleet command says nothing
        self.model.router_says = {"Praetorian": "party"}
        ctx = {"place": "bridge", "channel": {"party": "fleet", "open": True, "muted": False, "kind": "fleet"}}
        await self.game.push(type="player_text", text="Praetorian, rapporto sulla tua posizione", context=ctx)
        await asyncio.sleep(0.6)
        self.assertIn(("castellan", "Tre navi in linea, Capitano."), self.game.lines())
        self.assertNotIn("admiral", [s for s, _ in self.game.lines()])
        self.assertEqual(len(self.model.rourke_calls), 1)                                # (he was asked: he judged it was not for him)
        self.assertIn("Castellan", self.model.rourke_calls[0] + self.mind.director._allies_line())

    async def test_the_mandate_commander_who_talks_is_the_one_who_commands_and_shares_his_memory(self) -> None:
        self.model.war.policy = ScriptPolicy([("group_order", {"group": "Strike Group Varek Solm", "order": "attack", "target": "T-01", "range_km": 4.5,
                                                               "reason": "hold them at four and a half kilometres"})])
        await self.state(battle_state())
        self.at(10)
        await self.state(battle_state(), 0.2)                                             # the admiral ordered (and wrote it in the common log)
        self.mind.enemy.open_channel("T-21")
        self.model.enemy_says = "Capitano, resa o morte."
        ctx = {"place": "bridge", "channel": {"party": "T-21", "open": True, "muted": False}}
        self.model.router_says = {"arrendetevi": "party"}
        self.model.crew = []
        await self.game.push(type="player_text", text="arrendetevi o sarete distrutti", context=ctx)
        await asyncio.sleep(0.8)
        enemy = [c for c in self.model.calls if c["kind"] == "enemy"][-1]
        self.assertIn("Your log of this fight", enemy["system"])
        self.assertIn("ordered Strike Group Varek Solm: attack on T-01 at 4.5 km", enemy["system"])      # what he decided, he remembers when he speaks
        self.assertIn("YOUR GROUPS", enemy["system"])                                      # the same picture the commander reads
        self.assertIn(("solm", "Capitano, resa o morte."), self.game.lines())
        self.assertIn("said to the Captain over the channel: Capitano, resa o morte.", self.mind.war.recall("mandate"))      # and what he said, the commander remembers

    async def test_a_defect_in_the_war_minds_never_cuts_the_crew_off_from_the_ship(self) -> None:
        with mock.patch.object(self.mind.war, "feed", side_effect=RuntimeError("a bug in the war minds")):
            await self.state(battle_state())
            self.assertEqual(self.mind.game.state.get("alert"), "red")                      # the state still arrived
        await self.state(battle_state(), 0.1)                                              # and the connection is still being served
        self.assertIn("_fleet_board", self.mind.game.state)
        self.assertFalse(self.tasks[0].done())

    async def test_hello_forgets_the_last_fight(self) -> None:
        self.model.war.policy = ScriptPolicy([("no_change", {"reason": "x"})])
        await self.state(battle_state())
        self.at(10)
        await self.state(battle_state(), 0.2)
        self.assertTrue(self.mind.war.minds)
        await self.game.push(type="hello", client="test")
        await asyncio.sleep(0.2)
        self.assertEqual(self.mind.war.minds, {})
        self.assertEqual(self.mind.war.recall("astra"), " (nothing yet: the fight has just begun)")


if __name__ == "__main__":
    unittest.main()
