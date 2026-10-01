"""The war minds against scripted models and a scripted battle (no network, no cost, no engine).

    cd mind && .venv/bin/python -m unittest bench.war_minds_unit -v

What is checked: when a mind thinks (a fight begins, events of its own group, a new enemy, the clock, a word from the Captain — and when it does
not: nothing moved, other groups' news, a pulse already running), what it is given (the picture of its side only, its group's events, its log of
what it ordered and said), what it can do (the tools of its seat, run on the game as the contract says: side, by, group, with the reason kept out
of the command), what happens when an order is refused, the chain of command, the allied captains' words, the Captain's requests and their
fallback, succession, and the figures (cost, latency)."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import models, war_minds
from astra_mind.war_minds import Message, WarMinds
from bench.war_mock import MockLLM, ScriptPolicy, null_policy

models.LEDGER.write_file = False


# ------------------------------------------------------------------------------------------------ a scripted battle
def member(i: str, cls: str = "styx", hull: int = 100, shields: int = 100, missiles: int = 16, **kw: Any) -> dict[str, Any]:
    return {"id": i, "class": cls, "hull_pct": hull, "shields_pct": shields, "missiles": missiles, **kw}


def group(name: str, gid: int, members: list[dict[str, Any]], order: str = "auto", leader: str | None = None, **kw: Any) -> dict[str, Any]:
    g = {"id": gid, "name": name, "state": "engaged", "formation": "wedge", "order_in_force": order, "leader": leader or members[0]["id"],
         "engagement_range_km": 4.0, "your_strength": 3.6, "enemy_strength_near": 3.6, "allied_strength_near": 0, "morale": 0.82, "members": members}
    if order != "auto":
        g.update(order_by="admiral", order_seconds_left=60, order_target="A-01")
    g.update(kw)
    return g


def foe(label: str, ships: list[dict[str, Any]], range_km: float = 22.0) -> dict[str, Any]:
    return {"label": label, "ships": ships, "range_km": range_km, "nearest_ship_km": range_km - 1.5, "bearing_deg": 240}


def ev(n: int, text: str, ago: int = 2) -> dict[str, Any]:
    return {"n": n, "ago_s": ago, "text": text}


def mandate_state(groups: list[dict[str, Any]], enemies: list[dict[str, Any]], events: list[dict[str, Any]] | None = None, boss: str = "M-01") -> dict[str, Any]:
    ships = [{"id": m["id"], "name": m["id"], "class": m["class"], "state": "attacking" if enemies else "standing by", "hull_pct": m["hull_pct"],
              "shields_pct": m["shields_pct"],
              **({"commands_the_strike_group": True} if m["id"] == boss else {})} for g in groups for m in g["members"]]
    return {"_mandate": {"your_ships": ships, "astra_ships": [], "your_groups": groups, "enemy_groups": enemies, "group_events": events or [],
                         "your_strike_fighters_airborne": 0, "your_strike_fighters_still_aboard": 0}, "location": "Aurelia System, 180,000 km from New Ravenna"}


def astra_state(groups: list[dict[str, Any]], enemies: list[dict[str, Any]], events: list[dict[str, Any]] | None = None, **kw: Any) -> dict[str, Any]:
    return {"_astra_groups": {"your_groups": groups, "enemy_groups": enemies, "group_events": events or []}, "hull_pct": 100, "alert": "red",
            "location": "Aurelia System, 180,000 km from New Ravenna", "contacts": [], **kw}


class Clock:
    t = 100.0

    def __call__(self) -> float:
        return self.t


class Fixture(unittest.IsolatedAsyncioTestCase):
    sides: tuple[str, ...] = ("mandate", "astra")

    async def asyncSetUp(self) -> None:
        self.clock = Clock()
        self.cmds: list[tuple[str, dict[str, Any], str]] = []
        self.said: list[dict[str, Any]] = []
        self.refuse: set[str] = set()
        self.voices: dict[str, tuple[str, str]] = {}
        self.llm = MockLLM(null_policy, latency=0.0)
        self.minds = self.make()
        patcher = mock.patch.object(war_minds.random, "uniform", lambda a, b: 1.0)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make(self, **kw: Any) -> WarMinds:
        async def execute(name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
            self.cmds.append((name, args, by))
            if name == "group_order" and str(args.get("group")) in self.refuse:
                return {"ok": False, "detail": f"FAILED: no group '{args.get('group')}' (yours: Vanguard)"}
            return {"ok": True, "detail": f"{args.get('group', name)}: done"}

        async def say(speaker: str, text: str, lang: str, tone: str, **k: Any) -> None:
            self.said.append({"speaker": speaker, "text": text, "lang": lang, "tone": tone, **k})

        return WarMinds(self.llm, say, execute, lang=lambda: "it", clock=self.clock, sides=self.sides,
                        mandate_persona=lambda c: {"key": "solm", "name": "Archon Varek Solm", "rank": "Archon (fleet commander)", "ship": "the Acheron",
                                                    "bio": "Weary.", "voice": "bill_boerst"} if c == "M-01" else None,
                        register_voice=lambda k, n, v: self.voices.__setitem__(k, (n, v)), **kw)

    async def settle(self, n: int = 6) -> None:
        for _ in range(n):
            await asyncio.sleep(0)
        if self.llm.latency:
            await asyncio.sleep(self.llm.latency * 3)

    async def feed(self, state: dict[str, Any], advance: float = 0.0) -> None:
        self.clock.t += advance
        self.minds.feed(state)
        await self.settle()

    def calls(self, seat: str | None = None) -> list[dict[str, Any]]:
        return [c for c in self.llm.calls if seat is None or c["seat"] == seat]


VANGUARD = lambda **kw: group("Vanguard", 2, [member("M-01", "acheron", missiles=32), member("M-02"), member("M-03")], **kw)  # noqa: E731
ENEMIES = lambda: [foe("group of A-01", [{"id": "A-01", "class": "acheron", "hull_pct": 90, "shields_pct": 86},   # noqa: E731
                                          {"id": "A-02", "class": "styx", "hull_pct": 100, "shields_pct": 100}])]


class CadenceTests(Fixture):
    sides = ("mandate",)

    async def test_nothing_happens_without_a_fight(self) -> None:
        for _ in range(5):
            await self.feed(mandate_state([VANGUARD()], []), 20)
        self.assertEqual(self.llm.calls, [])

    async def test_the_first_look_comes_a_few_seconds_after_the_fight_begins(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 4)
        self.assertEqual(self.llm.calls, [])
        await self.feed(st, 5)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertEqual(self.llm.calls[0]["seat"], "mandate/admiral")

    async def test_it_thinks_on_the_clock_only_when_the_picture_moved(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)                                             # first contact
        self.assertEqual(len(self.llm.calls), 1)
        await self.feed(st, 60)                                            # a minute on, nothing moved: no call
        self.assertEqual(len(self.llm.calls), 1)
        moved = mandate_state([VANGUARD(order="attack")], ENEMIES())      # the group's order changed (the picture is not the same)
        await self.feed(moved, 30)
        self.assertEqual(len(self.llm.calls), 2)
        self.assertIn("periodic review", self.llm.calls[1]["user"])

    async def test_an_event_of_the_fleet_wakes_the_admiral_after_the_burst_settles(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        hit = mandate_state([VANGUARD()], ENEMIES(), [ev(1, "Vanguard: lost M-03 (styx), the reactor went; 2 of 3 ships left")])
        await self.feed(hit, 21)                                           # past the minimum gap: the burst has to settle first
        self.assertEqual(len(self.llm.calls), 1)
        await self.feed(hit, 4)
        self.assertEqual(len(self.llm.calls), 2)
        self.assertIn("lost M-03", self.llm.calls[1]["user"])
        self.assertIn("news of the fleet", self.llm.calls[1]["user"])

    async def test_the_same_news_is_not_read_twice(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES(), [ev(1, "Vanguard: lost M-03 (styx), the reactor went; 2 of 3 ships left")])
        await self.feed(st)
        await self.feed(st, 9)
        self.assertEqual(len(self.llm.calls), 1)
        await self.feed(st, 30)
        await self.feed(st, 5)
        self.assertEqual(len(self.llm.calls), 1)

    async def test_a_new_enemy_on_the_plot_wakes_it(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        more = mandate_state([VANGUARD()], ENEMIES() + [foe("group of A-07", [{"id": "A-07", "class": "unknown"}], 30)])
        await self.feed(more, 22)
        await self.feed(more, 4)
        self.assertEqual(len(self.llm.calls), 2)
        self.assertIn("A-07", self.llm.calls[1]["user"])

    async def test_never_twice_in_parallel_for_the_same_person(self) -> None:
        self.llm.latency = 0.3
        st = mandate_state([VANGUARD()], ENEMIES(), [ev(1, "Vanguard: lost M-03 (styx), the reactor went; 2 of 3 ships left")])
        await self.feed(st)
        self.clock.t += 9
        self.minds.feed(st)                                                # the first look begins (the model takes 0.3 s)
        await asyncio.sleep(0.05)
        self.assertTrue(self.minds.minds["mandate/admiral"].busy)
        for i in range(6):                                                 # news pours in while it thinks: no second pulse starts
            self.clock.t += 5
            self.minds.feed(mandate_state([VANGUARD()], ENEMIES(), [ev(1, "x"), ev(2 + i, "Vanguard: lost M-02 (styx), the hull broke apart; 1 of 3 ships left")]))
            await asyncio.sleep(0)
        self.assertEqual(len(self.llm.calls), 1)                          # the first is still thinking
        await asyncio.sleep(0.4)
        self.assertFalse(self.minds.minds["mandate/admiral"].busy)

    async def test_a_fight_that_stays_quiet_for_a_long_while_is_over(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        for _ in range(5):
            await self.feed(mandate_state([VANGUARD()], []), 20)
        m = self.minds.minds["mandate/admiral"]
        self.assertIsNone(m.engaged_since)
        self.assertEqual(self.minds.recall("mandate"), " (nothing yet: the fight has just begun)")


class MandateSeatsTests(Fixture):
    sides = ("mandate",)

    async def test_the_admiral_is_the_flagship_and_the_others_lead_their_groups(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        st = mandate_state([g1, g2], ENEMIES())
        await self.feed(st)
        self.assertEqual(sorted(self.minds.minds), ["mandate/admiral", "mandate/group/Interdiction Squadron"])
        self.assertEqual(self.minds.minds["mandate/admiral"].commander.name, "Archon Varek Solm")

    async def test_a_group_commander_wakes_only_for_their_own_groups_news_and_reads_only_their_group(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        st = mandate_state([g1, g2], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        both = {c["seat"] for c in self.llm.calls}
        self.assertEqual(both, {"mandate/admiral", "mandate/group/Interdiction Squadron"})            # the first look of each
        n0 = len(self.llm.calls)
        about_vanguard = mandate_state([g1, g2], ENEMIES(), [ev(1, "Vanguard: lost M-02 (styx), the reactor went; 1 of 2 ships left")])
        await self.feed(about_vanguard, 22)
        await self.feed(about_vanguard, 4)
        self.assertEqual([c["seat"] for c in self.llm.calls[n0:]], ["mandate/admiral"])                # the other group's commander sleeps
        about_squadron = mandate_state([g1, g2], ENEMIES(), [ev(1, "Vanguard: lost M-02 (styx), the reactor went; 1 of 2 ships left"),
                                                              ev(2, "Interdiction Squadron: morale is breaking (0.33), strength 3.0 against 7.5; with no order in force it will break off")])
        n1 = len(self.llm.calls)
        await self.feed(about_squadron, 22)
        await self.feed(about_squadron, 4)
        self.assertIn("mandate/group/Interdiction Squadron", [c["seat"] for c in self.llm.calls[n1:]])
        sub = next(c for c in self.llm.calls[n1:] if c["seat"] == "mandate/group/Interdiction Squadron")
        self.assertIn("morale is breaking", sub["user"])
        self.assertNotIn("lost M-02", sub["user"].split("EVENTS SINCE")[1])                             # it does not read the other group's news
        self.assertIn("Interdiction Squadron", sub["system"])
        self.assertNotIn("fleet_ops", sub["tools"])

    async def test_a_group_commander_does_not_think_on_the_clock(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        await self.feed(mandate_state([g1, g2], ENEMIES()))
        await self.feed(mandate_state([g1, g2], ENEMIES()), 9)
        n = len([c for c in self.llm.calls if "group/" in c["seat"]])
        for i in range(6):
            await self.feed(mandate_state([group("Vanguard", 2, [member("M-01", "acheron", hull=90 - 5 * i), member("M-02")]), g2], ENEMIES()), 40)
        self.assertEqual(len([c for c in self.llm.calls if "group/" in c["seat"]]), n)

    async def test_succession_passes_the_seat_and_the_memory(self) -> None:
        g = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02"), member("M-03")])
        await self.feed(mandate_state([g], ENEMIES()))
        await self.feed(mandate_state([g], ENEMIES()), 9)
        self.assertEqual(self.minds.minds["mandate/admiral"].commander.contact, "M-01")
        g2 = group("Vanguard", 2, [member("M-02"), member("M-03")])
        await self.feed(mandate_state([g2], ENEMIES(), [ev(1, "Vanguard: lost M-01 (acheron), the reactor went; 2 of 3 ships left")], boss="M-02"), 3)
        self.assertEqual(self.minds.minds["mandate/admiral"].commander.contact, "M-02")
        self.assertIn("passed from Archon Varek Solm", self.minds.recall("mandate"))
        await asyncio.sleep(0.01)
        last = self.llm.calls[-1]                                                      # the new commander looks at once, in those words
        self.assertIn("you have just taken command of the fleet from Archon Varek Solm", last["user"])
        self.assertIn("passed from Archon Varek Solm", last["user"])                    # and reads what the one before ordered and said

    async def test_the_admiral_may_speak_only_while_a_channel_is_open(self) -> None:
        st = mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        self.assertNotIn("transmit", self.llm.calls[0]["tools"])
        self.minds.channel = lambda contact: contact == "M-01"
        await self.feed(mandate_state([VANGUARD(order="attack")], ENEMIES()), 90)
        self.assertIn("transmit", self.llm.calls[1]["tools"])
        self.assertIn("A channel with the ASTRA captain is OPEN", self.llm.calls[1]["system"])


class ToolsTests(Fixture):
    sides = ("mandate", "astra")

    async def start(self, policy: Any, state: dict[str, Any] | None = None) -> None:
        self.llm.policy = policy
        st = state or mandate_state([VANGUARD()], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)

    async def test_the_admiral_orders_through_group_order_with_side_and_by_and_without_the_reason(self) -> None:
        await self.start(ScriptPolicy([("group_order", {"group": "all", "order": "attack", "target": "A-01", "range_km": 3.0, "for_s": 90,
                                                         "reason": "close on the Acheron"})]))
        self.assertEqual(self.cmds, [("group_order", {"group": "all", "order": "attack", "target": "A-01", "range_km": 3.0, "for_s": 90, "side": "mandate",
                                                       "by": "admiral"}, "admiral")])

    async def test_fleet_ops_go_as_mandate_tactics_and_decide_as_enemy_order(self) -> None:
        await self.start(ScriptPolicy([("fleet_ops", {"missiles": "salvo", "ew": "jam", "fighters": "launch", "reason": "now"}),
                                       ("decide", {"order": "withdraw", "reason": "lost"})]))
        self.assertEqual(self.cmds[0], ("mandate_tactics", {"missiles": "salvo", "ew": "jam", "fighters": "launch"}, "admiral"))
        self.assertEqual(self.cmds[1][0], "enemy_order")
        self.assertEqual(self.cmds[1][1]["commander"], "M-01")

    async def test_a_group_commander_gives_orders_only_to_their_own_group(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        asked = [0]

        def policy(mind: Any, view: dict[str, Any], state: dict[str, Any], tools: list[str]):
            if mind.seat.kind != "group":
                return [("no_change", {"reason": "ok"})]
            asked[0] += 1
            return ([("group_order", {"group": "Vanguard", "order": "hold", "reason": "not mine"}), ("group_order", {"group": "Interdiction Squadron", "order": "pin", "reason": "mine"}),
                     ("report", {"text": "the admiral's wedge is too far", "urgent": False})] if asked[0] == 1 else [])      # (the second call is the correction round)
        self.llm.policy = policy
        st = mandate_state([g1, g2], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        sent = [c for c in self.cmds if c[0] == "group_order"]
        self.assertEqual([(c[1]["group"], c[1]["by"], c[1]["side"]) for c in sent], [("Interdiction Squadron", "commander", "mandate")])
        self.assertIn("not your group", self.minds.recall("mandate"))
        self.assertIn("reported to the admiral", self.minds.recall("mandate"))

    async def test_an_urgent_report_wakes_the_admiral(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        self.llm.policy = lambda mind, view, state, tools: (
            [("report", {"text": "we are being flanked", "urgent": True})] if mind.seat.kind == "group" else [("no_change", {"reason": "ok"})])
        st = mandate_state([g1, g2], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        await self.feed(st, 1)
        adm = [c for c in self.llm.calls if c["seat"] == "mandate/admiral"]
        self.assertEqual(len(adm), 2)
        self.assertIn("we are being flanked", adm[1]["user"])

    async def test_a_refused_order_is_read_and_corrected_once(self) -> None:
        self.refuse = {"Vangard"}
        calls = [0]

        def policy(mind: Any, view: dict[str, Any], state: dict[str, Any], tools: list[str]):
            calls[0] += 1
            return [("group_order", {"group": "Vangard", "order": "attack", "reason": "typo"})] if calls[0] == 1 else [("group_order", {"group": "Vanguard", "order": "attack", "reason": "fixed"})]
        await self.start(policy)
        await asyncio.sleep(0.01)
        self.assertEqual([c[1]["group"] for c in self.cmds], ["Vangard", "Vanguard"])
        second = self.llm.calls[1]["messages"]
        self.assertTrue(any("FAILED" in str(m.get("content")) for m in second if m.get("role") == "tool"))
        self.assertIn("again:group_order:attack", self.minds.pulses[0]["tools"])

    async def test_what_was_ordered_is_remembered_at_the_next_look(self) -> None:
        await self.start(ScriptPolicy([("group_order", {"group": "Vanguard", "order": "attack", "target": "A-01", "reason": "kill the cruiser first"})],
                                      [("no_change", {"reason": "it stands"})]))
        moved = mandate_state([VANGUARD(order="attack")], ENEMIES())
        await self.feed(moved, 90)
        self.assertIn("ordered Vanguard: attack on A-01", self.llm.calls[1]["user"])
        self.assertIn("kill the cruiser first", self.llm.calls[1]["user"])

    async def test_no_change_is_logged_and_counted(self) -> None:
        await self.start(null_policy)
        self.assertIn("looked, no change", self.minds.recall("mandate"))
        self.assertEqual(self.minds.minds["mandate/admiral"].stats["no_change"], 1)

    async def test_subordinates_read_the_admirals_intent(self) -> None:
        g1 = group("Vanguard", 2, [member("M-01", "acheron"), member("M-02")])
        g2 = group("Interdiction Squadron", 3, [member("M-07"), member("M-08")])
        self.llm.policy = lambda mind, view, state, tools: (
            [("group_order", {"group": "Vanguard", "order": "pin", "reason": "hold them while the squadron comes round"})] if mind.seat.kind == "admiral" else [])
        st = mandate_state([g1, g2], ENEMIES())
        await self.feed(st)
        await self.feed(st, 9)
        await self.feed(st, 1)
        await asyncio.sleep(0.01)
        self.assertIn("hold them while the squadron comes round", self.minds.minds["mandate/admiral"].intent)
        n = len(self.llm.calls)
        hit = mandate_state([g1, g2], ENEMIES(), [ev(1, "Interdiction Squadron: lost M-08 (styx), the reactor went; 1 of 2 ships left")])
        await self.feed(hit, 25)
        await self.feed(hit, 4)
        sub = [c for c in self.llm.calls[n:] if "group/" in c["seat"]]
        self.assertTrue(sub)
        self.assertIn("hold them while the squadron comes round", sub[0]["user"])

    async def test_the_pulse_keeps_figures(self) -> None:
        await self.start(null_policy)
        s = self.minds.summary()
        self.assertEqual(s["pulses"], 1)
        self.assertAlmostEqual(s["cost"], 0.0011, places=5)
        self.assertIn("mandate/admiral", s["by_seat"])
        self.assertEqual(s["by_seat"]["mandate/admiral"]["pulses"], 1)


class AstraTests(Fixture):
    sides = ("astra",)

    def picket(self, **kw: Any) -> dict[str, Any]:
        return group("7th Fleet picket", 1, [member("T-01", "praetorian", missiles=24), member("T-02", "vigilant", missiles=12)], leader="T-01", **kw)

    def state(self, order: str = "auto", enemies: list[dict[str, Any]] | None = None, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return astra_state([self.picket(order=order, order_by="captain") if order != "auto" else self.picket()], enemies if enemies is not None else ENEMIES(), events,
                           contacts=[{"id": "T-01", "name": "ASN Praetorian", "status": "friendly", "range_km": 4.5, "bearing_deg": 25, "hull_pct": 100},
                                     {"id": "T-31", "status": "bearing only (passive)", "bearing_deg": 335}], speed_mps=288, heading_deg=45)

    async def test_the_picket_has_a_commander_with_a_voice_and_the_chain_of_command(self) -> None:
        self.llm.policy = ScriptPolicy([("say", {"to": "aquila", "text": "Aquila, Praetorian: contact bearing zero-seven-zero, closing.", "tone": "focused"}),
                                        ("group_order", {"group": "7th Fleet picket", "order": "screen", "target": "AQUILA", "reason": "cover the carrier"})])
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        c = self.llm.calls[0]
        self.assertEqual(c["seat"], "astra/group/7th Fleet picket")
        self.assertIn("Captain Rhea Castellan", c["system"])
        self.assertIn("Commander Daniel Okoro", c["system"])                              # one call voices the group's captains
        self.assertIn("Senior officer present: the Captain of the ASN Aquila", c["system"])
        self.assertIn("The ASN Aquila (the Captain's ship)", c["user"])
        self.assertIn("T-31 bearing 335", c["user"])                                      # a bearing with no range is told as such
        self.assertEqual(self.voices["castellan"][1], "estelle")
        self.assertEqual(self.said[0]["speaker"], "castellan")
        self.assertEqual(self.said[0]["lang"], "it")                                      # in the Captain's language
        self.assertEqual(self.cmds[0][2], "commander")
        self.assertEqual(self.cmds[0][1]["by"], "commander")
        self.assertEqual(self.cmds[0][1]["side"], "astra")

    async def test_another_captain_of_the_group_may_speak_but_an_unknown_one_is_the_commander(self) -> None:
        self.llm.policy = ScriptPolicy([("say", {"speaker": "okoro", "to": "castellan", "text": "Praetorian, Vigilant: our port shield is gone, falling in behind you.", "tone": "tense"}),
                                        ("say", {"speaker": "ghost", "text": "Hello.", "tone": "calm"})])
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.assertEqual([s["speaker"] for s in self.said], ["okoro", "castellan"])
        self.assertIn("Commander Daniel Okoro to castellan", self.minds.recall("astra"))

    async def test_the_captain_on_the_fleet_net_is_answered_at_once_even_before_any_fight(self) -> None:
        self.llm.policy = ScriptPolicy([("say", {"to": "aquila", "text": "Ricevuto, Capitano.", "tone": "calm"})])
        await self.feed(self.state(enemies=[]))
        self.assertEqual(self.llm.calls, [])
        n = self.minds.captain_to_fleet("Praetorian, report your state", "it")
        self.assertEqual(n, 1)
        await self.feed(self.state(enemies=[]), 1)
        self.assertEqual(len(self.llm.calls), 1)
        self.assertIn("MESSAGES FOR YOU", self.llm.calls[0]["user"])
        self.assertIn("the Captain, over the fleet net: Praetorian, report your state", self.llm.calls[0]["user"])
        self.assertTrue(self.said[0]["answer"])                                           # it is an answer: it goes first on the voice stage

    async def test_a_request_from_comms_reaches_the_ships_commander_and_not_the_ships_directly(self) -> None:
        self.llm.policy = ScriptPolicy([("group_order", {"group": "7th Fleet picket", "order": "attack", "target": "A-01", "reason": "the Captain asks"}),
                                        ("say", {"to": "aquila", "text": "Aye, Captain: all guns on the Acheron.", "tone": "focused"})])
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.cmds.clear()
        res = self.minds.captain_request({"ship": "T-01", "request": "focus_fire", "target": "A-01"})
        self.assertTrue(res["ok"])
        self.assertIn("Rhea Castellan", res["detail"])
        self.assertEqual(self.cmds, [])                                                    # nothing reached the ships yet
        await self.feed(self.state(), 1)
        self.assertIn("concentrate your fire on the target", self.llm.calls[-1]["user"])
        self.assertEqual([c[0] for c in self.cmds], ["group_order"])
        self.assertEqual(self.said[-1]["speaker"], "castellan")

    async def test_a_request_nobody_can_judge_is_not_taken(self) -> None:
        self.assertIsNone(self.minds.captain_request({"ship": "T-09", "request": "stand_off"}))

    async def test_when_the_commander_cannot_answer_the_request_goes_to_the_ships_the_old_way(self) -> None:
        async def broken(**kw: Any):
            raise RuntimeError("the model is down")
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.cmds.clear()
        with mock.patch.object(self.llm, "chat", broken):
            self.assertTrue(self.minds.captain_request({"ship": "T-01", "request": "stand_off"})["ok"])
            await self.feed(self.state(), 1)
            await asyncio.sleep(0.01)
        self.assertEqual([(c[0], c[1]["request"]) for c in self.cmds], [("fleet_request", "stand_off")])
        self.assertIn("did not answer", self.minds.recall("astra"))

    async def test_an_order_the_captain_gave_directly_stands_and_is_told_to_the_commander(self) -> None:
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.minds.captain_ordered("7th Fleet picket", "7th Fleet picket: attacking A-01 (acheron)")
        self.assertIn("direct order", self.minds.recall("astra"))
        await self.feed(self.state(order="attack"), 90)
        self.assertIn("The Captain ordered your group directly", self.llm.calls[-1]["user"])
        self.assertIn("by captain", self.llm.calls[-1]["user"])

    async def test_addressed_ally_is_woken_and_the_fleet_is_not(self) -> None:
        g2 = group("Resolute", 4, [member("T-43", "vigilant")], leader="T-43")
        st = astra_state([self.picket(), g2], ENEMIES(), contacts=[])
        self.llm.latency = 0.02                                                            # (both think at the same time: the word arrives while the other is reading)
        self.llm.policy = lambda mind, view, state, tools: (
            [("say", {"to": "ally_t43", "text": "Resolute, Praetorian: take our starboard quarter.", "tone": "calm"})] if mind.seat.group == "7th Fleet picket" else [])
        await self.feed(st)
        await self.feed(st, 9)
        seats = {c["seat"] for c in self.llm.calls}
        self.assertEqual(seats, {"astra/group/7th Fleet picket", "astra/group/Resolute"})
        n = len(self.llm.calls)
        await self.feed(st, 1)
        self.assertEqual(len(self.llm.calls), n + 1)                                       # the addressed ally thinks again, once
        self.assertEqual(self.llm.calls[-1]["seat"], "astra/group/Resolute")
        self.assertIn("take our starboard quarter", self.llm.calls[-1]["user"])

    async def test_weapons_posture_goes_ship_by_ship_through_the_fleet_request(self) -> None:
        self.llm.policy = ScriptPolicy([("weapons_posture", {"posture": "hold_fire", "reason": "the Captain is talking"})])
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.assertEqual([(c[0], c[1]["ship"], c[1]["request"]) for c in self.cmds], [("fleet_request", "T-01", "hold_fire"), ("fleet_request", "T-02", "hold_fire")])

    async def test_a_new_ship_gets_a_captain_from_the_pool_and_the_director_can_name_one(self) -> None:
        a = self.minds.persona_of("astra", "T-43", "vigilant")
        b = self.minds.persona_of("astra", "T-44", "vigilant")
        self.assertNotEqual(a.name, b.name)
        self.assertNotEqual(a.key, b.key)
        self.assertEqual(self.minds.persona_of("astra", "T-43").name, a.name)             # the same ship, the same captain
        c = self.minds.register_ally("T-50", {"name": "Captain Zhao Lin", "rank": "Captain", "ship": "the cruiser Resolve", "bio": "Calm.", "voice": "juergen"})
        self.assertEqual(self.minds.persona_of("astra", "T-50").name, "Captain Zhao Lin")
        self.assertEqual(self.voices[c.key][1], "juergen")

    async def test_a_line_that_waited_is_thought_again_by_the_captain_who_was_to_say_it(self) -> None:
        self.llm.policy = ScriptPolicy([("say", {"text": "Aquila, the Acheron is down to thirty percent.", "tone": "focused"})])
        await self.feed(self.state())
        await self.feed(self.state(), 9)
        self.llm.policy = ScriptPolicy([("say", {"text": "Aquila, the Acheron is dead.", "tone": "calm"})])
        new = await self.minds.rethink("castellan", "Aquila, the Acheron is down to thirty percent.", 12.0, "", "it")
        self.assertEqual(new, "Aquila, the Acheron is dead.")
        self.assertIn("12 seconds ago", self.llm.calls[-1]["user"])
        self.llm.policy = ScriptPolicy([("no_change", {"reason": "old news"})])
        self.assertIsNone(await self.minds.rethink("castellan", "x", 30.0, "Aquila, the", "it"))


class ChainOfCommandTests(Fixture):
    sides = ("astra",)

    async def test_the_captain_is_the_senior_officer_unless_a_flag_officer_is_present(self) -> None:
        picket = group("7th Fleet picket", 1, [member("T-01", "praetorian"), member("T-02", "vigilant")], leader="T-01")
        st = astra_state([picket], ENEMIES())
        await self.feed(st)
        self.assertTrue(self.minds.captain_is_senior(st["_astra_groups"]))
        self.assertIn("Senior officer present: the Captain", self.minds.chain_facts(st["_astra_groups"], st))
        self.minds.register_ally("T-60", {"name": "Rear Admiral Odile Fraser", "rank": "Rear Admiral", "ship": "the cruiser Concord", "bio": "", "voice": "anna", "precedence": 1})
        fleet = group("Relief Squadron", 5, [member("T-60", "acheron")], leader="T-60")
        st2 = astra_state([picket, fleet], ENEMIES())
        self.assertFalse(self.minds.captain_is_senior(st2["_astra_groups"]))
        facts = self.minds.chain_facts(st2["_astra_groups"], st2)
        self.assertIn("Senior officer present: Rear Admiral Odile Fraser", facts)
        board = self.minds.fleet_board(st2)
        self.assertIn("NOT the senior officer present", board)
        self.assertIn("Relief Squadron", board)

    async def test_the_fleet_board_for_the_crew(self) -> None:
        picket = group("7th Fleet picket", 1, [member("T-01", "praetorian"), member("T-02", "vigilant")], leader="T-01", order="screen", order_target="AQUILA", order_by="captain")
        st = astra_state([picket], ENEMIES())
        await self.feed(st)
        board = self.minds.fleet_board(st)
        self.assertIn("Captain Rhea Castellan", board)
        self.assertIn("order screen (by captain, on AQUILA)", board)
        self.assertIn("the Captain is the senior officer present", board)
        self.assertEqual(self.minds.fleet_board({}), "")


class BenchAdmiralTests(Fixture):
    sides = ("astra",)

    async def test_the_bench_gives_astra_an_admiral_over_all_its_groups_who_orders_as_the_captain(self) -> None:
        self.minds = self.make(astra_admiral=True)
        self.llm.policy = ScriptPolicy([("group_order", {"group": "all", "order": "attack", "target": "M-01", "reason": "go"})])
        g1 = group("Vanguard", 2, [member("A-01", "acheron"), member("A-02")])
        g2 = group("Second Line", 3, [member("A-07"), member("A-08")])
        st = astra_state([g1, g2], [foe("group of M-01", [{"id": "M-01", "class": "acheron"}])], alert="green")
        await self.feed(st)
        await self.feed(st, 9)
        self.assertEqual(sorted(self.minds.minds), ["astra/admiral"])
        self.assertEqual(self.cmds[0][2], "captain")
        self.assertEqual(self.cmds[0][1]["by"], "captain")
        self.assertIn("Rear Admiral Ione Marsh", self.llm.calls[0]["system"])


class RenderTests(unittest.TestCase):
    def test_the_picture_is_compact_and_complete(self) -> None:
        g = group("Vanguard", 2, [member("M-01", "acheron", hull=84, shields=62, missiles=20, shield_faces_pct=[29, 100, 100, 70, 100, 100]),
                                  member("M-02", status="flank")], order="attack")
        text = war_minds.render_groups({"your_groups": [g]})
        self.assertIn("Vanguard (id 2) — engaged, wedge formation, order in force: attack (by admiral, on A-01, 60 s left)", text)
        self.assertIn("M-01 acheron hull 84% shields 62% · faces bow 29 stern 100 port 100 stbd 70 dorsal 100 ventral 100 · 20 missiles", text)
        self.assertIn("M-02 styx hull 100% shields 100% · 16 missiles · flank", text)
        enemy = war_minds.render_enemy({"enemy_groups": [foe("group of A-01", [{"id": "A-01", "class": "acheron", "hull_pct": 90, "shields_pct": 86},
                                                                             {"id": "A-05", "class": "unknown", "status": "breaking off"}])]})
        self.assertIn("group of A-01 — 2 ship(s) at 22.0 km (nearest 20.5 km), bearing 240°: A-01 acheron hull 90% shields 86%; A-05 unknown (breaking off)", enemy)
        self.assertEqual(war_minds.render_events([ev(3, "Vanguard: lost M-03")]), " #3 · 2 s ago · Vanguard: lost M-03")

    def test_the_mandate_admiral_reads_only_the_astra_ships_on_its_plot(self) -> None:
        view = {"your_ships": [{"id": "M-01", "emissions": "jamming the ASTRA radar", "ew_orders": "jam", "decoys_aboard": 4, "ew_officer": "dark and outside their radar"}],
                "astra_ships": [{"id": "A-01", "hull_pct": 50, "shields_pct": 40, "shields": "reinforced forward (the other sectors weaker)"},
                                {"id": "A-09", "hull_pct": 100, "shields_pct": 100}, {"id": "AQUILA", "track": "LOST: she has gone quiet"}],
                "enemy_groups": [{"ships": [{"id": "A-01"}]}], "your_strike_fighters_airborne": 0, "your_strike_fighters_still_aboard": 6}
        text, ew = war_minds.mandate_extras(view)
        self.assertIn("A-01 hull 50% shields 40%, reinforced forward", text)
        self.assertNotIn("A-09", text)                                                    # not on its plot: the fog holds for the Mandate too
        self.assertIn("AQUILA: LOST", text)
        self.assertIn("6 still aboard", text)
        self.assertEqual(ew["M-01"]["decoys_aboard"], 4)

    def test_ranks_order_the_navy(self) -> None:
        self.assertLess(war_minds.rank_index("Rear Admiral"), war_minds.rank_index("Captain"))
        self.assertLess(war_minds.rank_index("Captain"), war_minds.rank_index("Commander"))
        self.assertLess(war_minds.rank_index("Commander"), war_minds.rank_index("Lieutenant Commander"))

    def test_the_digest_ignores_small_moves(self) -> None:
        a = {"your_groups": [group("V", 1, [member("A-01", hull=85)])], "enemy_groups": [foe("g", [{"id": "M-01"}], 21.0)]}
        b = {"your_groups": [group("V", 1, [member("A-01", hull=82)])], "enemy_groups": [foe("g", [{"id": "M-01"}], 20.2)]}
        c = {"your_groups": [group("V", 1, [member("A-01", hull=55)])], "enemy_groups": [foe("g", [{"id": "M-01"}], 20.2)]}
        self.assertEqual(war_minds.view_digest(a), war_minds.view_digest(b))
        self.assertNotEqual(war_minds.view_digest(a), war_minds.view_digest(c))


if __name__ == "__main__":
    unittest.main()
