"""The March joined to the real simulation, against a stand-in for the game (no network, no cost, no engine): docs/GUERRA.md §10.

    cd mind && .venv/bin/python -m unittest bench.march_glue_unit -v

`FakeWorld` plays the game's simulation as the glue sees it: it takes `director_beat` (contact ids, an arrival time), spawns the ships, lets the test hurt, kill and jump them,
and gives the views the real game gives (`_astra_groups`, `_mandate`, `contacts`, the Gate's status). What is checked: a fleet of the March that comes to the Aquila's system
reaches the game as exactly the ships it has, as damaged as they are, with its people and its place at the Gate's mouth; the game's own fleets (the opening) are adopted by
their contact ids and not sent twice; what the game says of hulls, losses and jumps comes back into the fleets, the scores and the people's will; a Gate lane gives the
fleets back to the map and an arrival takes the new system's fleets in; the game's sky is never overfilled; a refusal sends the fleet back; Fleet's orders to the Aquila
set the Gate (and are tried again while an engagement refuses them); the bridge hears the war beyond her sky; the war goes on without her; and the saved campaign."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from typing import Any

from astra_mind import march_glue as mg
from astra_mind import models
from astra_mind.march import SIDES, STRAGGLERS, Fleet, Order, Ship
from astra_mind.march_data import CLASSES
from astra_mind.strategy import StrategicMinds
from bench.march_mock import StrategyMock
from bench.march_unit import clear, put, world

models.LEDGER.write_file = False


class Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


class FakeWorld:
    """The game's simulation, as the glue sees it."""

    def __init__(self, now) -> None:
        self.now = now
        self.ships: dict[str, dict[str, Any]] = {}
        self.pending: list[tuple[float, dict[str, Any], list[str]]] = []
        self.beats: list[dict[str, Any]] = []
        self.next_id = 40
        self.refuse = ""
        self.engaged = False
        self.gate = (87.0, 52.3)
        self.lane = ""
        self.tuned = ""

    async def command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        beat = args["beat"]
        self.beats.append(beat)
        if self.refuse:
            return {"ok": False, "detail": self.refuse}
        if beat["type"] == "transit":
            if self.engaged:
                return {"ok": False, "detail": "the Aquila is in the middle of an engagement"}
            self.tuned = beat["system_name"]
            return {"ok": True, "detail": f"Fleet orders the Aquila to the {self.tuned} system"}
        if beat["type"] == "resupply":
            return {"ok": True, "detail": "resupply under way"}
        n = sum(min(10, len(g["ships"])) for g in beat["groups"])
        ids = [f"T-{self.next_id + i}" for i in range(n)]
        self.next_id += n
        self.pending.append((self.now() + float(beat.get("delay_s", 30)), beat, ids))
        return {"ok": True, "detail": f"{beat['type']} scheduled in {beat.get('delay_s', 30)} s; contact ids {', '.join(ids)}; the first is the group's leader"}

    def tick(self) -> None:
        for item in list(self.pending):
            when, beat, ids = item
            if when > self.now():
                continue
            self.pending.remove(item)
            k = 0
            for g in beat["groups"]:
                for sp in g["ships"][:10]:
                    side = "mandate" if sp["class"] in ("acheron", "styx", "lethe") else "astra"
                    self.add(ids[k], side, sp["class"], sp["name"], sp.get("hull_pct", 100), sp.get("missiles"))
                    k += 1

    def add(self, cid: str, side: str, cls: str, name: str, hull: float = 100, missiles: int | None = None) -> None:
        self.ships[cid] = {"id": cid, "side": side, "class": cls, "name": name, "hull_pct": hull, "shields_pct": 100, "missiles": missiles if missiles is not None else 12,
                           "state": "attacking" if side == "mandate" else "formation"}

    def hurt(self, cid: str, hull: float) -> None:
        self.ships[cid]["hull_pct"] = hull

    def kill(self, cid: str) -> None:
        self.ships[cid]["state"] = "destroyed with all hands"

    def jump(self, cid: str) -> None:
        self.ships[cid]["state"] = "jumped out of the system"

    def state(self) -> dict[str, Any]:
        astra = [{"id": s["id"], "class": s["class"], "hull_pct": s["hull_pct"], "shields_pct": s["shields_pct"], "missiles": s["missiles"]}
                 for s in self.ships.values() if s["side"] == "astra" and s["state"] not in ("destroyed with all hands", "jumped out of the system")]
        mandate = [dict(s) for s in self.ships.values() if s["side"] == "mandate"]
        contacts = [{"id": s["id"], "status": "hostile" if s["side"] == "mandate" else "friendly", "hull_pct": s["hull_pct"], "class": s["class"]}
                    for s in self.ships.values() if s["state"] not in ("destroyed with all hands", "jumped out of the system")]
        gate = f"Janus Gate: bearing {self.gate[0]:03.0f} mark 3, {self.gate[1]:.1f} km, bound to Cassia, Thule"
        if self.lane:
            gate += f"; in the gate's lane to the {self.lane} system: helm locked, transit in 14 s"
        return {"_astra_groups": {"your_groups": [{"name": "7th Fleet", "members": astra}] if astra else []},
                "_mandate": {"your_ships": mandate, "your_groups": []}, "contacts": contacts, "janus_gate": gate, "location": "Aurelia System"}


class Fixture(unittest.IsolatedAsyncioTestCase):
    opening = False                                    # the order of battle as it is (the opening's own ships), or a stage with the fleets a test puts

    async def asyncSetUp(self) -> None:
        self.m = world()
        if not self.opening:
            clear(self.m)
        self.clock = Clock()
        self.world = FakeWorld(lambda: self.m.t)
        self.groups: list[tuple[Any, ...]] = []
        self.said: list[str] = []
        self.sectors = 0
        self.m.live_scripts = True

        async def announce(text: str) -> None:
            self.said.append(text)

        async def sector() -> None:
            self.sectors += 1

        def register(ids, groups, kind, cmd, why) -> None:
            self.groups.append((list(ids), groups, kind, cmd, why))
        self.minds = StrategicMinds(StrategyMock(), self.m, self._say)
        self.glue = mg.MarchGlue(self.m, self.minds, command=self.world.command, register_groups=register, announce=announce, send_sector=sector,
                                 clock=self.clock)
        self.glue.minds.sides = ()                      # (no mind looks: the join is what is tested; the reflexes alone)
        self.glue.active = True
        self.m.aquila_arrived("Aurelia")
        self.glue._last = None

    async def _say(self, *a: Any, **k: Any) -> None:
        pass

    async def step(self, n: int = 1) -> None:
        """The game's seconds: the March advances with the clock, the stand-in world spawns what is due, the glue reads the state, the tasks it started run."""
        for _ in range(int(n)):
            self.clock.t += 1.0
            self.world.tick()
            self.glue.feed(self.world.state())
            for _ in range(3):
                await asyncio.sleep(0)

    def fleet(self, name: str) -> Fleet:
        return next(f for f in self.m.fleets.values() if f.name == name)


class BringInTest(Fixture):
    async def test_a_fleet_coming_through_the_gate_reaches_the_game_as_its_ships_damaged_as_they_are(self) -> None:
        f = put(self.m, "mandate", "Thule", [("acheron", 1), ("styx", 3)], name="Vanguard Test")
        f.ships[1].hull = 0.55
        f.ships[0].fighters, f.ships[0].bombers = 8, 4
        f.supply = 0.6
        f.commander = {"name": "Warden Corvin Tarsk", "rank": "Warden (group commander)", "bio": "x", "voice": "charles", "gender": "m"}
        ok, _ = self.m.order("mandate", f.id, "assault", "Aurelia", by="admiral", reason="take the Gate")
        self.assertTrue(ok)
        while not f.in_gate and self.m.t < 300:
            await self.step(1)
        await self.step(10)
        self.assertTrue(f.in_gate and f.arrive_at - self.m.t > mg.LEAD_S)
        self.assertFalse(self.world.beats)                                           # (it is in the Gate, not yet near its end: nothing is sent)
        while f.status != "real" and self.m.t < 600:
            await self.step(1)
        self.assertEqual(f.status, "real")
        self.assertEqual(len(self.world.beats), 1)
        beat = self.world.beats[0]
        self.assertEqual((beat["type"], beat["granted"], beat["hail"]), ("raid", True, False))
        self.assertLessEqual(beat["delay_s"], mg.LEAD_S + 1)
        self.assertEqual((beat["bearing_deg"], beat["range_km"]), (87.0, 48.3))        # the Gate's mouth: 4 km before the Gate, on its bearing
        ships = [sp for g in beat["groups"] for sp in g["ships"]]
        self.assertEqual(sorted(s["name"] for s in ships), sorted(s.name for s in f.ships))
        hurt = next(s for s in ships if s["name"] == f.ships[1].name)
        self.assertEqual(hurt["hull_pct"], 55)
        self.assertTrue(all("missiles" in s for s in ships))                          # (a fleet short of supply carries fewer missiles)
        self.assertLess(ships[0]["missiles"], CLASSES[ships[0]["class"]]["missiles"])
        wings = [w for g in beat["groups"] for w in g["wings"]]
        self.assertTrue(wings and all(w["mission"] == "strike" for w in wings))
        self.assertEqual(beat["groups"][0]["commander"]["name"], "Warden Corvin Tarsk")
        self.assertEqual(beat["groups"][0]["goes_for"], "aquila")
        await self.step(30)
        ids = {s.cid for s in f.ships}
        self.assertEqual(len(ids), 4)
        self.assertTrue(all(c.startswith("T-") for c in ids))
        self.assertEqual({c for c in self.world.ships}, ids)                          # the game has them, and nobody else
        self.assertEqual(len(self.groups), 1)                                         # (the new commanders were given to the director to register)
        self.assertEqual(self.groups[0][2], "raid")

    async def test_an_astra_fleet_standing_there_when_the_aquila_arrives_comes_in_as_reinforcements(self) -> None:
        f = put(self.m, "astra", "Cassia", [("praetorian", 1), ("vigilant", 2)], name="Cassia Squadron")
        self.m.aquila_arrived("Cassia")
        await self.step(mg.PRESENT_DELAY_S + 30)
        beat = self.world.beats[0]
        self.assertEqual(beat["type"], "reinforcements")
        self.assertNotIn("goes_for", beat["groups"][0])
        self.assertTrue(all("captain" in sp for sp in beat["groups"][0]["ships"]))      # (every ASTRA ship has its captain: the war minds give it a mind)
        self.assertEqual(f.status, "real")
        self.assertEqual({s.cid for s in f.ships}, set(self.world.ships))
        names = [s.captain for s in f.ships]
        self.assertEqual(len(set(names)), len(names))                                  # (nobody captains two ships)
        # the same ship has the same captain when it comes again
        again = self.glue.person(f, f.ships[0])
        self.assertEqual(again["name"], f.ships[0].captain)

    async def test_a_big_fleet_goes_in_as_several_groups_with_every_ship_once(self) -> None:
        f = put(self.m, "mandate", "Thule", [("acheron", 3), ("styx", 8), ("lethe", 4)], name="Main Body Test")
        self.m.aquila_arrived("Thule")
        await self.step(40)
        self.assertEqual(f.status, "real")
        names = [sp["name"] for b in self.world.beats for g in b["groups"] for sp in g["ships"]]
        self.assertEqual(sorted(names), sorted(s.name for s in f.ships))
        self.assertTrue(all(len(g["ships"]) <= 10 for b in self.world.beats for g in b["groups"]))
        leaders = [g["ships"][0]["class"] for b in self.world.beats for g in b["groups"]]
        self.assertTrue(all(c == "acheron" for c in leaders[:3]), leaders)              # (the carriers lead the groups)
        await self.step(10)
        self.assertEqual({s.cid for s in f.ships}, set(self.world.ships))

    async def test_the_games_sky_is_never_overfilled(self) -> None:
        a = put(self.m, "astra", "Aurelia", [("vigilant", 20)], name="Big One")
        b = put(self.m, "astra", "Aurelia", [("vigilant", 20)], name="Big Two")
        await self.step(mg.PRESENT_DELAY_S + 20)
        real = [f for f in (a, b) if f.status == "real"]
        self.assertEqual(len(real), 1)
        other = b if real[0] is a else a
        self.assertNotEqual(other.status, "real")                                       # it waits in the Gate for a while ...
        self.assertTrue(other.in_gate)
        self.assertEqual(sum(1 for s in self.world.ships.values()), 20)

    async def test_a_refusal_sends_the_fleet_back_the_way_it_came(self) -> None:
        self.world.refuse = "no beat"
        f = put(self.m, "mandate", "Thule", [("styx", 2)], name="Refused")
        self.m.aquila_arrived("Thule")
        await self.step(40)
        self.assertNotEqual(f.status, "real")
        self.assertEqual(f.order.kind, "withdraw")                                      # (it goes back; the war goes on)
        self.assertEqual(self.glue.stats["refused"], 1)
        self.assertEqual(len(self.world.beats), 1)                                      # (and is not sent again while it leaves)

    async def test_a_fleet_is_sent_once(self) -> None:
        put(self.m, "astra", "Aurelia", [("vigilant", 2)], name="Once")
        await self.step(60)
        self.assertEqual(len(self.world.beats), 1)


class OpeningTest(Fixture):
    opening = True

    async def test_the_games_own_fleets_are_adopted_by_their_contact_ids_and_not_sent_twice(self) -> None:
        self.glue.reset_real(keep_opening=True)
        self.assertIn("F-A2", self.glue.opening)
        await self.step(30)
        self.assertEqual(self.world.beats, [])                                          # (the picket and the lethe are the game's: nothing is sent for them)
        self.world.add("T-01", "astra", "praetorian", "ASN Praetorian")
        self.world.add("T-02", "astra", "vigilant", "ASN Vigilant")
        self.world.add("T-11", "mandate", "lethe", "Lethe")
        await self.step(3)
        self.assertEqual(self.fleet("Aurelia Picket").status, "real")
        self.assertEqual(self.fleet("Lethe Hale").status, "real")
        self.assertEqual(self.world.beats, [])
        self.assertNotIn("F-A2", self.glue.opening)
        # the scripted fleets come when the game brings them
        self.assertEqual(self.m.fleets["F-M1"].status, "scripted")
        for i, (cls, name) in enumerate([("acheron", "Acheron"), ("styx", "Styx"), ("styx", "Cocytus"), ("styx", "Phlegethon")]):
            self.world.add(f"T-{21 + i}", "mandate", cls, name)
        await self.step(2)
        self.assertEqual(self.m.fleets["F-M1"].status, "real")
        self.assertEqual(self.world.beats, [])
        self.assertTrue(any(e.kind == "arrival" and "F-M1" in e.fleets for e in self.m.events))

    async def test_a_fleet_the_game_never_brings_is_the_maps_after_the_grace(self) -> None:
        self.glue.reset_real(keep_opening=True)
        self.m.t = mg.GRACE_S + 500
        await self.step(40)
        self.assertTrue(self.world.beats)                                               # (the picket the game did not bring is sent like any fleet)


class BackTest(Fixture):
    async def arrived(self, side: str, ships: list[tuple[str, int]], where: str = "Aurelia") -> Fleet:
        f = put(self.m, side, where, ships, name=f"{side} test")
        await self.step(mg.PRESENT_DELAY_S + 20)
        assert f.status == "real"
        return f

    async def test_hulls_come_back_into_the_fleet(self) -> None:
        f = await self.arrived("astra", [("praetorian", 1), ("vigilant", 2)])
        cid = f.ships[1].cid
        self.world.hurt(cid, 37)
        await self.step(2)
        self.assertAlmostEqual(f.ships[1].hull, 0.37)

    async def test_a_mandate_ship_destroyed_is_lost_and_counts_in_the_war(self) -> None:
        a = await self.arrived("astra", [("vigilant", 2)])
        m = await self.arrived("mandate", [("styx", 3)])
        will = dict(self.m.will)
        victim = m.ships[0]
        self.world.kill(victim.cid)
        await self.step(2)
        self.assertEqual(m.n, 2)
        self.assertNotIn(victim, m.ships)
        self.assertEqual(self.m.score["mandate"]["ships_lost"], 1)
        self.assertEqual(self.m.score["astra"]["ships_killed"], 1)
        self.assertLess(self.m.will["mandate"], will["mandate"])
        self.assertGreater(self.m.will["astra"], will["astra"])
        self.assertEqual(self.m.real_tally["mandate"]["lost"], 1)
        self.assertEqual(a.n, 2)

    async def test_an_astra_ship_that_vanishes_after_it_was_seen_is_lost_unless_the_game_said_it_jumped(self) -> None:
        f = await self.arrived("astra", [("vigilant", 3)])
        await self.step(3)
        lost, jumped = f.ships[0], f.ships[1]
        self.world.ships[lost.cid]["state"] = "destroyed with all hands"
        self.world.ships[jumped.cid]["state"] = "jumped out of the system"
        self.glue.on_event(f"sensors: {jumped.name} ({jumped.cid}) has left sensor range")
        await self.step(2)
        self.assertEqual(f.n, 1)
        self.assertEqual(self.m.score["astra"]["ships_lost"], 1)                         # (one destroyed, one jumped out: it lives)
        survivors = [x for x in self.m.fleets.values() if x.note == f"{STRAGGLERS}{f.id}"]
        self.assertEqual(len(survivors), 1)
        self.assertEqual(survivors[0].ships, [jumped])
        self.assertIn(survivors[0].order.kind, ("withdraw", "move"))

    async def test_a_mandate_ship_that_jumped_out_goes_on_as_a_small_fleet_that_falls_back(self) -> None:
        f = await self.arrived("mandate", [("styx", 3)])
        self.world.jump(f.ships[0].cid)
        self.world.jump(f.ships[1].cid)
        await self.step(2)
        self.assertEqual(f.n, 1)
        small = [x for x in self.m.fleets.values() if x.note == f"{STRAGGLERS}{f.id}"]
        self.assertEqual(len(small), 1)                                                  # (they jumped together: one fleet)
        self.assertEqual(small[0].n, 2)
        self.assertEqual(self.m.score["mandate"]["ships_lost"], 0)

    async def test_a_ship_the_game_never_showed_is_left_out_and_nothing_is_lost(self) -> None:
        f = put(self.m, "astra", "Aurelia", [("vigilant", 3)], name="Odd")
        self.world.refuse = ""
        await self.step(3)
        ghost = f.ships[2]
        self.world.pending[0][1]["groups"][0]["ships"].pop(2)                              # (the game leaves one out)
        self.world.pending[0] = (self.world.pending[0][0], self.world.pending[0][1], self.world.pending[0][2][:2] + ["T-99"])
        await self.step(mg.PRESENT_DELAY_S + 200)
        self.assertNotIn(ghost, f.ships)
        self.assertEqual(self.m.score["astra"]["ships_lost"], 0)

    async def test_a_fight_is_joined_and_over_and_the_war_is_told(self) -> None:
        await self.arrived("astra", [("vigilant", 2)])
        m = await self.arrived("mandate", [("styx", 2)])
        self.assertTrue(self.m.real_fight)
        for s in list(m.ships):
            self.world.kill(s.cid)
        await self.step(3)
        weight = self.m.real_over("Aurelia")
        self.assertIn(weight, (2, 3))
        news = [e for e in self.m.events if e.kind == "battle_end" and e.system == "Aurelia"]
        self.assertTrue(news and "We lost 0 ships" in news[-1].text["astra"] and "the enemy lost about 2" in news[-1].text["astra"])
        self.assertFalse(self.m.real_fight)

    async def test_a_major_battle_ends_a_chapter_but_not_twice_in_a_short_while(self) -> None:
        a = await self.arrived("astra", [("praetorian", 1), ("vigilant", 4)])
        m = await self.arrived("mandate", [("acheron", 1), ("styx", 8)])
        for s in list(m.ships):
            self.world.kill(s.cid)
        await self.step(3)
        self.assertTrue(self.glue.on_event("director: engagement over — victory: no hostile ship left; Aquila hull 80%"))
        self.assertFalse(self.glue.on_event("director: engagement over — victory: again"))     # (a chapter a long while apart)
        self.assertEqual(a.n, 5)

    async def test_a_fight_the_game_did_not_announce_over_is_over_after_a_while(self) -> None:
        await self.arrived("astra", [("vigilant", 2)])
        m = await self.arrived("mandate", [("styx", 1)])
        self.assertTrue(self.m.real_fight)
        self.world.kill(m.ships[0].cid)
        await self.step(100)
        self.assertFalse(self.m.real_fight)
        self.assertTrue(any(e.kind == "battle_end" for e in self.m.events))


class PlaceTest(Fixture):
    async def test_a_gate_lane_gives_the_fleets_back_to_the_map_and_an_arrival_takes_the_new_systems_in(self) -> None:
        a = put(self.m, "astra", "Aurelia", [("vigilant", 3)], name="Picket")
        c = put(self.m, "astra", "Cassia", [("vigilant", 2)], name="Cassia Squadron")
        await self.step(mg.PRESENT_DELAY_S + 20)
        self.assertEqual(a.status, "real")
        self.world.hurt(a.ships[0].cid, 40)
        await self.step(2)
        self.world.lane = "Cassia"
        await self.step(2)
        self.assertEqual(self.m.aquila["lane"], "Cassia")
        self.assertEqual((a.status, a.where), ("ready", "Aurelia"))                      # (where it stands, with the hull it has)
        self.assertAlmostEqual(a.ships[0].hull, 0.4, delta=0.02)
        self.assertEqual(self.m.real_system, "")
        # the game's sky is cleared by the transit; the Aquila is through into Cassia
        self.world.ships.clear()
        self.world.lane = ""
        self.world.beats.clear()
        self.m.war.arrived("Cassia")
        await self.step(mg.PRESENT_DELAY_S + 20)
        self.assertEqual((self.m.aquila["where"], self.m.aquila["lane"], self.m.real_system), ("Cassia", "", "Cassia"))
        self.assertEqual(c.status, "real")
        self.assertEqual(len(self.world.beats), 1)
        self.assertEqual(a.status, "ready")

    async def test_the_march_follows_the_war_map_when_the_story_says_the_aquila_arrived(self) -> None:
        self.m.war.arrived("Meridian")
        self.assertEqual((self.m.aquila["where"], self.m.real_system), ("Meridian", "Meridian"))


class OrdersToTheAquilaTest(Fixture):
    async def test_fleets_order_tunes_the_gate_for_the_first_jump_and_is_tried_again_while_an_engagement_refuses_it(self) -> None:
        self.world.engaged = True
        res = await self.glue._task_aquila("Cassia", "relieve the yards")
        self.assertFalse(res["ok"])
        self.assertIn("try again", res["detail"])
        self.world.engaged = False
        await self.step(30)
        self.assertEqual(self.world.tuned, "Cassia")                                      # (Fleet tried again: the Gate is tuned)
        n = len([b for b in self.world.beats if b["type"] == "transit" and b["system_name"] == "Cassia"])
        await self.step(60)
        self.assertEqual(len([b for b in self.world.beats if b["type"] == "transit" and b["system_name"] == "Cassia"]), n)     # (once tuned, not again)

    async def test_a_far_system_is_reached_one_gate_at_a_time(self) -> None:
        res = await self.glue._task_aquila("Veyra", "a look at the Guilds")
        self.assertTrue(res["ok"])
        self.assertIn(self.world.tuned, ("Cassia", "Meridian"))                            # (two Gates away: Aurelia > Cassia or Meridian > Veyra)
        self.assertIn("first jump", res["detail"])

    async def test_a_tender_is_a_resupply_beat(self) -> None:
        res = await self.glue._tender()
        self.assertTrue(res["ok"])
        self.assertEqual(self.world.beats[-1]["type"], "resupply")


class StoryTest(Fixture):
    async def test_the_bridge_hears_the_war_beyond_her_sky_and_the_gates_warning_but_not_what_she_sees(self) -> None:
        self.m.say("system_taken", "Cassia", "Cassia has fallen to the Mandate.", ("astra",), 3)
        self.m.say("battle_end", "Aurelia", "The battle at Aurelia is over.", ("astra",), 3)         # (her own sky: she sees it)
        self.m.say("wake", "Aurelia", "The Gate at Aurelia is cycling: a force of about 6 ships is coming through in about 1 min.", ("astra",), 2)
        self.m.say("battle_update", "Thule", "The battle at Thule goes on.", ("astra",), 1)
        await self.step(45)
        self.assertEqual(len(self.said), 2)                                             # (the Gate's warning reaches her first, the fall of Cassia a few seconds after)
        self.assertIn("The Gate at Aurelia is cycling", self.said[0])
        self.assertIn("Cassia has fallen", self.said[1])
        self.assertFalse(any("The battle at Aurelia is over" in t or "Thule" in t for t in self.said))

    async def test_bulletins_come_at_most_so_often(self) -> None:
        self.m.say("system_taken", "Cassia", "one", ("astra",), 3)
        await self.step(5)
        self.m.say("system_taken", "Thule", "two", ("astra",), 3)
        await self.step(25)
        self.assertEqual(len(self.said), 1)
        await self.step(10)
        self.assertEqual(len(self.said), 1)                                              # (the second waits for the fleet net's quiet)
        await self.step(mg.BULLETIN_GAP_S)
        self.assertEqual(len(self.said), 2)

    async def test_the_holo_table_is_drawn_again_every_so_often(self) -> None:
        await self.step(int(mg.HOLO_EVERY_S * 3) + 2)
        self.assertGreaterEqual(self.sectors, 3)

    async def test_the_bridge_reads_the_front(self) -> None:
        put(self.m, "astra", "Aurelia", [("vigilant", 2)], name="Picket Board")
        await self.step(2)
        state = self.world.state()
        self.glue.feed(state)
        self.assertIn("Picket Board", state["_march_board"])


class FastForwardTest(Fixture):
    opening = True

    async def test_the_war_goes_on_without_the_aquila(self) -> None:
        self.glue.reset_real(keep_opening=True)
        self.world.add("T-01", "astra", "praetorian", "ASN Praetorian")
        await self.step(3)
        t0 = self.m.t
        await self.glue.fast_forward(0.5)
        self.assertGreaterEqual(self.m.t, t0 + 1800)
        self.assertFalse(self.glue.ff)
        self.assertEqual(self.m.real_system, self.m.aquila["where"])
        self.assertTrue(all(s.cid == "" for f in self.m.fleets.values() for s in f.ships))
        self.assertTrue(all(f.status != "real" for f in self.m.fleets.values()))


class SaveTest(Fixture):
    async def test_the_campaign_and_the_high_commands_log_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.m.war.save_path = os.path.join(d, "war.json")
            self.m.save_path = os.path.join(d, "march.json")
            self.minds.journal("astra", "ordered F-A1: move Aurelia — home => ok")
            self.minds.seats["astra"].thinks = 3
            put(self.m, "astra", "Cassia", [("vigilant", 2)], name="Saved Squadron")
            self.glue.save()
            self.assertTrue(os.path.exists(os.path.join(d, "march.json")))
            self.assertTrue(os.path.exists(os.path.join(d, "strategy.json")))
            m2 = world()
            m2.war.save_path = os.path.join(d, "war.json")
            m2.save_path = os.path.join(d, "march.json")
            minds2 = StrategicMinds(StrategyMock(), m2, self._say)
            g2 = mg.MarchGlue(m2, minds2, command=self.world.command, clock=self.clock)
            self.assertTrue(g2.load())
            self.assertTrue(any(f.name == "Saved Squadron" for f in m2.fleets.values()))
            self.assertIn("ordered F-A1: move Aurelia", minds2.recall("astra"))
            self.assertEqual(minds2.seats["astra"].thinks, 3)


if __name__ == "__main__":
    unittest.main()
