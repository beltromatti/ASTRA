"""The war's high commands against a scripted model (no network, no cost, no engine): docs/GUERRA.md §10.

    cd mind && .venv/bin/python -m unittest bench.strategy_unit -v

What is checked: when a high command looks at the war (the opening is fought first; its own clock, only when its picture moved; news after a settle, never more often than the
gap; at once for the Captain), what it reads (its own side's picture, never the enemy's truth; its plan; its log; the Captain's words, in his language), what it can do (the
tools, run on the March as the war's rules say, the answers kept in its log; an order that was refused or an estimate that came back is read once more), what it cannot (the
Mandate has no Aquila), what happens when the model fails or is slow (the fleets go on on their reflexes, the same code for both sides), Rourke on the fleet net, the cost."""
from __future__ import annotations

import asyncio
import unittest
from typing import Any
from unittest import mock

from astra_mind import models, strategy
from astra_mind.march import SIDES
from astra_mind.strategy import FAIL_LIMIT, FIRST_PULSE_S, MIN_GAP_S, PERIODIC_S, StrategicMinds
from bench.march_mock import ScriptPolicy, StrategyMock, null_policy
from bench.march_unit import clear, put, world

models.LEDGER.write_file = False


class Fixture(unittest.IsolatedAsyncioTestCase):
    quiet = False                                       # a stage with two static fleets, nothing going on (no news): the cadence's own

    async def asyncSetUp(self) -> None:
        self.m = world()
        if self.quiet:
            clear(self.m)
            self.astra = put(self.m, "astra", "Aurelia", [("vigilant", 3)], name="Aurelia Picket")
            self.mandate = put(self.m, "mandate", "Erebus", [("styx", 3)], name="Erebus Squadron")
        self.said: list[tuple[Any, ...]] = []
        self.tasks: list[tuple[str, str]] = []
        self.tender: list[int] = []

        async def say(speaker: str, text: str, lang: str, tone: str, **kw: Any) -> None:
            self.said.append((speaker, text, lang, tone, kw.get("answer", False)))

        async def aquila_task(system: str, mission: str) -> dict[str, Any]:
            self.tasks.append((system, mission))
            return {"ok": True, "detail": "the Gate is tuned"}

        async def tender() -> dict[str, Any]:
            self.tender.append(1)
            return {"ok": True, "detail": "the tender is under way"}
        self.llm = StrategyMock(null_policy)
        self.sm = StrategicMinds(self.llm, self.m, say, lang=lambda: "it")
        self.sm.on_aquila_task = aquila_task
        self.sm.on_tender = tender
        p = mock.patch.object(strategy.random, "uniform", lambda a, b: 1.0)
        p.start()
        self.addCleanup(p.stop)

    async def settle(self) -> None:
        for seat in self.sm.seats.values():
            if seat.task is not None:
                await seat.task

    def run_to(self, seconds: float) -> None:
        """The war runs `seconds` (the minds' second by second), the minds that are due start thinking."""
        end = self.m.t + seconds
        while self.m.t < end - 1e-6:
            self.m.run(min(5.0, end - self.m.t))
            self.sm.feed({})

    async def tick(self, seconds: float) -> None:
        """The same, with the minds' tasks given the floor between the seconds (as the server's loop does)."""
        end = self.m.t + seconds
        while self.m.t < end - 1e-6:
            self.m.run(min(5.0, end - self.m.t))
            self.sm.feed({})
            for _ in range(3):
                await asyncio.sleep(0)
        await self.settle()

    def looks(self, side: str | None = None) -> list[dict[str, Any]]:
        return [c for c in self.llm.calls if side is None or c["side"] == side]

    def pulses(self, side: str | None = None) -> list[dict[str, Any]]:
        return [p for p in self.sm.pulses if side is None or p["side"] == side]

    def prompt(self, side: str, n: int = -1) -> str:
        return self.looks(side)[n]["user"]


class CadenceTest(Fixture):
    quiet = True

    async def test_the_opening_is_fought_first_then_each_high_command_looks_once(self) -> None:
        await self.tick(FIRST_PULSE_S - 30)
        self.assertEqual(len(self.looks()), 0)                                     # (the strike group and the picket are the game's, not the map's)
        await self.tick(60)
        self.assertEqual(sorted(c["side"] for c in self.looks()), ["astra", "mandate"])
        self.assertEqual({p["why"][0] for p in self.pulses()}, {"the first look at the war: set your plan and your orders"})

    async def test_a_major_event_brings_the_first_look_forward(self) -> None:
        await self.tick(100)
        self.m.say("battle_end", "Aurelia", "The Gate has been attacked.", ("astra",), 3)
        await self.tick(30)
        self.assertEqual(len(self.looks("astra")), 1)
        self.assertEqual(len(self.looks("mandate")), 0)                            # (it did not hear of it)

    async def test_a_gate_cycling_towards_the_aquilas_system_brings_the_first_look_forward(self) -> None:
        self.m.aquila_arrived("Aurelia")
        await self.tick(100)
        self.m.say("wake", "Cassia", "The Gate at Cassia is cycling: a force is coming through.", ("astra",), 2)
        await self.tick(30)
        self.assertEqual(len(self.looks("astra")), 0)                              # (a force at another system waits for the first look's hour)
        self.m.say("wake", "Aurelia", "The Gate at Aurelia is cycling: a force is coming through.", ("astra",), 2)
        await self.tick(30)
        self.assertEqual(len(self.looks("astra")), 1)                              # (one that comes to the Aquila's sky does not)
        self.assertEqual(len(self.looks("mandate")), 0)

    async def test_the_periodic_look_comes_only_when_the_picture_moved(self) -> None:
        self.sm.quiet_s = lambda: 0.0                                              # (a war that is fighting somewhere: the quiet look is another test)
        await self.tick(FIRST_PULSE_S + 10)
        n = len(self.looks())
        self.assertEqual(n, 2)
        await self.tick(PERIODIC_S + 60)
        self.assertEqual(len(self.looks()), n)                                     # nothing moved: no look, and no cost
        ok, _ = self.m.order("astra", self.astra.id, "move", "Cassia", by="auto")
        self.assertTrue(ok)
        await self.tick(PERIODIC_S + 30)
        later = [c["side"] for c in self.looks()[n:]]
        self.assertTrue(later and set(later) == {"astra"}, later)                  # her picture moved; the Mandate's did not (it does not see her)

    async def test_a_war_quiet_for_minutes_is_looked_at_even_when_the_map_stands_still(self) -> None:
        await self.tick(FIRST_PULSE_S + 10)
        n = len(self.looks())
        self.assertEqual(n, 2)
        await self.tick(PERIODIC_S + 60)                                           # nothing moved, and no battle anywhere for minutes
        quiet = self.pulses()[n:]
        self.assertEqual(sorted(p["side"] for p in quiet), ["astra", "mandate"])
        self.assertTrue(all("the war has been quiet for" in p["why"][0] for p in quiet))
        self.assertIn("TEMPO: no battle anywhere in the March for", self.prompt("mandate"))

    async def test_news_wakes_a_mind_after_a_settle_and_never_more_often_than_the_gap(self) -> None:
        await self.tick(FIRST_PULSE_S + 10)
        n = len(self.looks("astra"))
        self.m.say("battle_end", "Aurelia", "The picket held the Gate at Aurelia.", ("astra",), 3)
        await self.tick(MIN_GAP_S / 2)
        self.assertEqual(len(self.looks("astra")), n)                              # (too soon after its last look)
        await self.tick(MIN_GAP_S)
        self.assertEqual(len(self.looks("astra")), n + 1)
        self.assertIn("news: The picket held the Gate", self.pulses("astra")[-1]["why"][0])
        self.m.say("battle_end", "Aurelia", "Another battle.", ("astra",), 1)       # (minor news does not wake it)
        await self.tick(MIN_GAP_S * 2)
        self.assertEqual(len(self.looks("astra")), n + 1)

    async def test_far_news_that_arrives_late_is_still_read(self) -> None:
        """The Gates deliver out of order: news of a far battle comes after nearer news that happened later. Nobody loses it."""
        await self.tick(FIRST_PULSE_S + MIN_GAP_S + 10)
        self.m.say("system_taken", "Kharon", "Kharon has fallen (far).", ("astra",), 3)         # happened first, takes long to arrive
        self.m.say("battle_end", "Aurelia", "A fight at Aurelia.", ("astra",), 3)               # happened second, arrives at once
        await self.tick(30)
        self.assertIn("A fight at Aurelia", self.prompt("astra"))
        self.assertNotIn("Kharon has fallen", self.prompt("astra"))                            # (it is on its way through the Gates)
        await self.tick(MIN_GAP_S + 90)
        self.assertIn("Kharon has fallen", self.prompt("astra"))                               # ... and read when it came, though it is the older news

    async def test_the_captain_is_answered_at_once(self) -> None:
        self.llm.policy = ScriptPolicy([("tell_captain", {"text": "Sposto il grosso a Cassia, Capitano.", "tone": "measured"})], only="astra")
        await self.tick(20)
        lines = await self.sm.rourke_reply("Ammiraglio, ho bisogno di rinforzi", "it")
        self.assertEqual(lines, ["Sposto il grosso a Cassia, Capitano."])
        self.assertEqual(self.said[-1][0], "admiral")
        self.assertEqual(self.said[-1][2:], ("it", "measured", True))               # (a line that answers the Captain goes first)
        user = self.prompt("astra")
        self.assertIn("Ammiraglio, ho bisogno di rinforzi", user)
        self.assertIn("Italian", user)
        self.assertIn("Capitano", user)
        self.assertEqual(len(self.looks("mandate")), 0)

    async def test_the_captain_does_not_wait_for_a_look_that_is_under_way(self) -> None:
        self.llm.latency = 0.3
        self.run_to(FIRST_PULSE_S + 5)
        await asyncio.sleep(0.05)
        self.assertTrue(self.sm.seats["astra"].busy)                                       # (Rourke is in the middle of a look)
        self.llm.policy = ScriptPolicy([("tell_captain", {"text": "Ti ascolto, Capitano.", "tone": "calm"})], only="astra")
        self.llm.latency = 0.0
        lines = await self.sm.rourke_reply("Ammiraglio, mi sente?", "it")
        self.assertEqual(lines, ["Ti ascolto, Capitano."])
        self.assertEqual(self.pulses("astra")[0]["error"], "cancelled")                    # (the look that was running was dropped, not waited for)
        self.assertIn("Ammiraglio, mi sente?", self.prompt("astra"))

    async def test_no_two_looks_at_once_for_a_side(self) -> None:
        self.llm.latency = 0.2
        self.run_to(FIRST_PULSE_S + 5)
        self.assertTrue(self.sm.seats["astra"].busy)
        self.sm.feed({})
        self.sm.feed({})
        await self.settle()
        self.assertEqual(len(self.looks()), 2)                                     # (one look each, not three)


class ReadingTest(Fixture):
    async def test_a_side_reads_its_own_picture_and_never_the_enemys_truth(self) -> None:
        await self.tick(FIRST_PULSE_S + 10)
        astra, mandate = self.prompt("astra"), self.prompt("mandate")
        self.assertIn("YOUR FLEETS", astra)
        self.assertIn("F-A1", astra)
        self.assertIn("F-A5", astra)
        self.assertNotIn("F-M4", astra)                                            # (the Mandate's main body at Erebus is not on ASTRA's plot)
        self.assertIn("F-M4", mandate)
        self.assertNotIn("F-A5", mandate)                                          # (the Home Fleet at Concordia is not on the Mandate's)
        self.assertIn("YOUR PLAN: ", astra)
        self.assertIn(strategy.OPENING_PLANS["astra"][:60], astra)
        self.assertIn(strategy.OPENING_PLANS["mandate"][:60], mandate)
        self.assertNotIn(strategy.OPENING_PLANS["mandate"][:60], astra)

    async def test_what_a_high_command_decided_is_in_its_log(self) -> None:
        self.llm.policy = ScriptPolicy([("fleet_order", {"fleet": "F-A1", "order": "move", "target": "Aurelia", "reason": "bring the main body home"})],
                                       [("no_change", {"reason": "the orders stand"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        self.assertIn("ordered F-A1: move Aurelia — bring the main body home => ok", self.sm.recall("astra"))
        self.m.say("battle_end", "Aurelia", "A fight.", ("astra",), 3)
        await self.tick(MIN_GAP_S * 2)
        self.assertIn("bring the main body home", self.prompt("astra"))              # (it reads what it said last time)
        self.assertNotIn("bring the main body home", self.prompt("mandate"))

    async def test_a_war_that_stands_still_does_not_push_the_orders_out_of_the_log(self) -> None:
        self.sm.journal("astra", "ordered F-A1: move Aurelia — home => ok")
        for i in range(30):
            self.m.t += 60.0
            self.sm.journal("astra", f"looked, no change: nothing moved ({i})")
        text = self.sm.recall("astra")
        self.assertIn("ordered F-A1: move Aurelia", text)                                  # (the order is still in its memory)
        self.assertEqual(text.count("looked, no change"), 1)                               # (and the last look is there, with when it was and what it thought)
        self.assertIn("nothing moved (29)", text)

    async def test_the_mandate_reads_what_intelligence_learned_of_the_captain(self) -> None:
        self.sm.intel = lambda: "He holds the Gate and spends missiles early."
        await self.tick(FIRST_PULSE_S + 10)
        self.assertIn("spends missiles early", self.prompt("mandate"))
        self.assertNotIn("spends missiles early", self.prompt("astra"))

    async def test_the_prompts_are_long_stable_and_the_picture_short(self) -> None:
        await self.tick(FIRST_PULSE_S + 10)
        sysp = [c["system"] for c in self.looks()]
        self.assertEqual(len(set(sysp)), 2)                                        # one stable system prompt a side
        self.assertTrue(all(len(s) > 4000 for s in sysp))
        self.assertTrue(all(len(c["user"]) < 9000 for c in self.looks()), [len(c["user"]) for c in self.looks()])

    async def test_the_field_brief_tells_the_commanders_the_plan_and_what_is_coming(self) -> None:
        clear(self.m)
        put(self.m, "astra", "Aurelia", [("vigilant", 2)], name="Aurelia Picket")
        main = put(self.m, "astra", "Cassia", [("praetorian", 1), ("vigilant", 3)], name="Main Body")
        put(self.m, "mandate", "Erebus", [("styx", 4)])
        self.m.set_plan("astra", "Hold Aurelia and bring the main body back.")
        ok, _ = self.m.order("astra", main.id, "move", "Aurelia", reason="to the picket", by="admiral")
        self.assertTrue(ok)
        self.m.run(60.0)
        text = self.sm.field_brief("astra", "Aurelia")
        self.assertIn("Hold Aurelia and bring the main body back.", text)
        self.assertIn("Main Body", text)
        self.assertIn("is on its way to you", text)
        self.assertNotIn("styx", text)                                             # (nothing of the enemy that its eyes do not hold)


class ToolsTest(Fixture):
    quiet = True

    async def test_an_order_goes_through_the_march_by_the_admirals_hand(self) -> None:
        self.llm.policy = ScriptPolicy([("fleet_order", {"fleet": self.astra.id, "order": "move", "target": "Cassia", "stance": "cautious", "reason": "home"}),
                                        ("set_plan", {"text": "Bring the picket to Cassia."}),
                                        ("set_build", {"system": "Cassia", "ship_class": "vigilant"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        o = self.astra.pending or self.astra.order
        self.assertEqual((o.kind, o.target, o.stance, o.by), ("move", "Cassia", "cautious", "admiral"))
        self.assertEqual(self.m.plans["astra"], "Bring the picket to Cassia.")
        self.assertEqual(self.m.sys["Cassia"].build, "vigilant")
        self.assertEqual(self.pulses("astra")[0]["ok"], 3)

    async def test_split_and_merge(self) -> None:
        self.llm.policy = ScriptPolicy([("split_fleet", {"fleet": self.astra.id, "ships": {"vigilant": 2}, "name": "Task Force Kestrel", "then_order": "move", "then_target": "Cassia",
                                                         "reason": "a screen for the yards"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        kes = next(f for f in self.m.side_fleets("astra") if f.name == "Task Force Kestrel")
        self.assertEqual((self.astra.n, kes.n), (1, 2))
        self.llm.policy = ScriptPolicy([("merge_fleets", {"into": self.astra.id, "fleet": kes.id})], only="astra")
        self.m.say("battle_end", "Aurelia", "A fight.", ("astra",), 3)
        self.m.fleets[kes.id].order.kind, self.m.fleets[kes.id].route = "hold", []
        self.m.fleets[kes.id].pending = None
        self.m.fleets[kes.id].where = "Aurelia"
        await self.tick(MIN_GAP_S * 2)
        self.assertEqual(self.astra.n, 3)
        self.assertNotIn(kes.id, self.m.fleets)

    async def test_a_refused_order_is_read_with_its_answer_and_corrected_once(self) -> None:
        self.llm.policy = ScriptPolicy([("fleet_order", {"fleet": "F-A99", "order": "move", "target": "Cassia", "reason": "typo"})],
                                       [("fleet_order", {"fleet": self.astra.id, "order": "move", "target": "Cassia", "reason": "corrected"})], loop=False, only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        astra = self.looks("astra")
        self.assertEqual(len(astra), 2)                                            # one look at the answer, no more
        tool_msgs = [m for m in astra[1]["messages"] if m.get("role") == "tool"]
        self.assertTrue(tool_msgs and tool_msgs[0]["content"].startswith("FAILED: no fleet 'F-A99' of yours"))
        self.assertIn("(yours:", tool_msgs[0]["content"])                          # (it is told what it has)
        self.assertEqual((self.astra.pending or self.astra.order).target, "Cassia")
        rec = self.pulses("astra")[0]
        self.assertEqual((rec["ok"], rec["failed"], rec["rounds"]), (1, 1, 2))

    async def test_an_estimate_comes_back_before_the_decision(self) -> None:
        self.llm.policy = ScriptPolicy([("assess", {"fleets": [self.astra.id], "target": "Thule"})],
                                       [("no_change", {"reason": "the estimate says wait"})], loop=False, only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        astra = self.looks("astra")
        self.assertEqual(len(astra), 2)
        tool = [m for m in astra[1]["messages"] if m.get("role") == "tool"][0]["content"]
        self.assertTrue(tool.startswith("ok: "))
        self.assertTrue("Staff estimate" in tool or "You hold no track" in tool, tool)

    async def test_a_mind_that_calls_nothing_is_asked_once_and_what_it_wrote_is_not_said(self) -> None:
        self.llm.policy = ScriptPolicy([], [("no_change", {"reason": "on second thought"})], loop=False, only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        astra = self.looks("astra")
        self.assertEqual(len(astra), 2)
        self.assertIn("You ended without a tool call", astra[1]["messages"][-1]["content"])
        self.assertEqual(self.said, [])

    async def test_only_rourke_has_the_aquila_tools(self) -> None:
        await self.tick(FIRST_PULSE_S + 10)
        tools = {c["side"]: set(c["tools"]) for c in self.looks()}
        self.assertTrue({"tell_captain", "task_aquila", "send_tender"} <= tools["astra"])
        self.assertTrue(not ({"tell_captain", "task_aquila", "send_tender"} & tools["mandate"]))
        self.assertTrue({"fleet_order", "split_fleet", "merge_fleets", "set_build", "set_plan", "assess", "parley", "no_change"} <= tools["mandate"])
        res = await self.sm._tool(self.sm.seats["mandate"], "tell_captain", {"text": "hello"}, "en")
        self.assertFalse(res["ok"])

    async def test_fleet_tasks_the_aquila_and_sends_a_tender(self) -> None:
        self.llm.policy = ScriptPolicy([("task_aquila", {"system": "Cassia", "mission": "relieve the yards", "words": "Capitano, ti voglio a Cassia.", "why": "the yards are open"}),
                                        ("send_tender", {"reason": "she is battered"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        self.assertEqual(self.tasks[0][0], "Cassia")
        self.assertEqual(self.m.aquila_task["system"], "Cassia")
        self.assertEqual(self.said[0][1], "Capitano, ti voglio a Cassia.")
        self.assertEqual(self.tender, [1])
        self.assertGreater(self.m.tender_free_at["astra"], self.m.t)
        res = await self.sm._tool(self.sm.seats["astra"], "send_tender", {"reason": "again"}, "en")
        self.assertFalse(res["ok"])                                                # (the Fleet has few)
        self.assertIn("no tender is free", res["detail"])

    async def test_a_proposal_of_peace_reaches_the_other_side(self) -> None:
        self.llm.policy = ScriptPolicy([("parley", {"kind": "peace", "terms": "an armistice on the old lines"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        self.assertEqual(self.m.proposals["astra"]["kind"], "peace")
        self.m.run(120.0)
        self.assertIn("offers a peace", " ".join(e.text["mandate"] for e in self.m.log["mandate"]))


class FailureTest(Fixture):
    quiet = True

    async def test_a_model_that_fails_leaves_the_fleets_to_the_reflexes_until_it_answers(self) -> None:
        self.llm.fail = 99
        await self.tick(FIRST_PULSE_S + 10)
        for _ in range(FAIL_LIMIT):
            self.m.say("battle_end", "Aurelia", "x", SIDES, 3)
            await self.tick(MIN_GAP_S + 60)
        seat = self.sm.seats["astra"]
        self.assertGreaterEqual(seat.failures, FAIL_LIMIT)
        self.sm._auto_t = -1e9
        self.sm.feed({})
        self.assertEqual(self.sm.autos["astra"].level, "full")
        self.llm.fail = 0
        self.m.say("battle_end", "Aurelia", "y", SIDES, 3)
        await self.tick(MIN_GAP_S + 60)
        self.assertEqual(seat.failures, 0)                                         # it answered: it is on duty again
        self.sm._auto_t = -1e9
        self.sm.feed({})
        self.assertEqual(self.sm.autos["astra"].level, "safety")

    async def test_a_slow_model_is_left_behind(self) -> None:
        self.llm.latency = 0.5
        with mock.patch.object(strategy, "PULSE_TIMEOUT_S", 0.05):
            await self.tick(FIRST_PULSE_S + 10)
        self.assertTrue(self.pulses() and all(p["error"] == "timeout" for p in self.pulses()))
        self.assertGreaterEqual(self.sm.seats["astra"].failures, 1)

    async def test_the_reflexes_serve_a_mind_on_duty_only_for_safety(self) -> None:
        for s in self.astra.ships:
            s.hull = 0.3
        await self.tick(FIRST_PULSE_S + 10)
        self.assertEqual(self.sm.autos["astra"].level, "safety")
        self.sm.sides = ()                                                         # (no mind on duty at all: the reflexes play the whole war)
        self.sm._auto_t = -1e9
        self.sm.feed({})
        self.assertEqual({a.level for a in self.sm.autos.values()}, {"full"})

    async def test_a_disabled_layer_runs_the_reflexes_only(self) -> None:
        self.sm.disabled = True
        await self.tick(FIRST_PULSE_S + 200)
        self.assertEqual(len(self.looks()), 0)
        self.assertEqual({a.level for a in self.sm.autos.values()}, {"full"})


class BudgetTest(Fixture):
    quiet = True

    async def test_the_cost_is_counted_by_role_and_by_hour(self) -> None:
        before = models.LEDGER.by_role.get("strategy", 0.0)
        await self.tick(FIRST_PULSE_S + 10)
        for _ in range(4):
            self.m.say("battle_end", "Aurelia", "news", SIDES, 3)
            await self.tick(MIN_GAP_S + 60)
        s = self.sm.summary()
        self.assertGreater(s["pulses"], 4)
        self.assertAlmostEqual(models.LEDGER.by_role["strategy"] - before, s["cost"], places=5)
        self.assertEqual(s["errors"], 0)
        self.assertEqual(set(s["by_side"]), set(SIDES))
        # a look a minute and a half per side all the same is a budget of its own: what a quiet war costs an hour is under a tenth of a dollar
        per_hour = (3600.0 / PERIODIC_S) * 2 * 0.0016
        self.assertLess(per_hour, 0.1)

    async def test_save_and_load_keep_what_a_high_command_remembers(self) -> None:
        self.llm.policy = ScriptPolicy([("fleet_order", {"fleet": self.astra.id, "order": "move", "target": "Cassia", "reason": "home"})], only="astra")
        await self.tick(FIRST_PULSE_S + 10)
        d = self.sm.save_state()
        other = StrategicMinds(StrategyMock(), self.m, self.sm.say)
        other.load_state(d)
        self.assertEqual(other.recall("astra"), self.sm.recall("astra"))
        self.assertEqual(other.seats["astra"].thinks, 1)
        other.reset()
        self.assertEqual(other.recall("astra").strip(), "(nothing yet: the war has just begun)")


if __name__ == "__main__":
    unittest.main()
