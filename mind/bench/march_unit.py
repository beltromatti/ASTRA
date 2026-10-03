"""The March's rules and the battle model, offline (no network, no cost): movement and its times, the fog of war, battles and what they leave, zones, sieges and
claims, yards and repairs, the war's end, saving, the battle model against the war bench's own results, the reflexes.

    cd mind && .venv/bin/python -m unittest bench.march_unit -v"""
from __future__ import annotations

import json
import random
import statistics
import tempfile
import unittest
from pathlib import Path

from astra_mind import march as mr
from astra_mind import march_auto as ma
from astra_mind import march_battle as mb
from astra_mind.march import Fleet, Order, SIDES, Ship
from astra_mind.war import WarMap

ROOT = Path(__file__).resolve().parents[2]


def world(seed: int = 1) -> mr.March:
    wm = WarMap()
    wm.persist = False
    return mr.March(wm, seed=seed)


def clear(m: mr.March) -> None:
    """An empty stage: no fleets (the tests put what they need)."""
    m.fleets.clear()
    m.battles.clear()
    m.tracks = {s: {} for s in SIDES}


def put(m: mr.March, side: str, where: str, ships: list[tuple[str, int]], name: str = "", order: Order | None = None, zone: str = "gate", **kw) -> Fleet:
    fid = m.new_fleet_id(side)
    lst: list[Ship] = []
    for cls, n in ships:
        for _ in range(n):
            lst.append(Ship(cls, m.ship_name(cls)))
    f = Fleet(fid, side, name or f"{side} {fid}", lst, where, 1.0, 0.8, order or Order("hold", where, "steady", False, "default", "", 0.0), status="ready", arrived_t=m.t, origin=where, zone=zone, **kw)
    m.fleets[fid] = f
    return f


class BattleModelTest(unittest.TestCase):
    def fights(self, a: list[tuple[str, int]], b: list[tuple[str, int]], runs: int = 120, seed: int = 3) -> tuple[float, float, float]:
        rng = random.Random(seed)
        wa = wb = 0
        lost_a = 0.0
        for _ in range(runs):
            ua, ub = mb.units(0, a), mb.units(1, b)
            e = mb.fight(ua, ub, rng)
            wa += e.winner == 0
            wb += e.winner == 1
            lost_a += sum(1 for u in ua if not u.alive)
        return wa / runs, wb / runs, lost_a / runs

    def test_equals_are_a_coin_and_the_stronger_wins(self) -> None:
        wa, wb, _ = self.fights([("styx", 4)], [("styx", 4)], 200)
        self.assertGreater(wa, 0.3)
        self.assertGreater(wb, 0.3)                                       # neither side wins always
        wa, wb, lost = self.fights([("styx", 6)], [("styx", 4)])
        self.assertGreater(wa, 0.95)                                      # the square law: a third more ships wins, and loses few
        self.assertLess(lost, 2.0)

    def test_deterministic_by_seed(self) -> None:
        a = self.fights([("vigilant", 5), ("praetorian", 1)], [("styx", 6), ("acheron", 1)], 20, seed=9)
        b = self.fights([("vigilant", 5), ("praetorian", 1)], [("styx", 6), ("acheron", 1)], 20, seed=9)
        self.assertEqual(a, b)

    def test_a_beaten_fleet_breaks_off_and_the_slow_are_caught(self) -> None:
        """A fleet far outmatched breaks off and mostly gets away; against an overwhelming one some are caught while they turn (the slow longest); the time to turn is the class's."""
        rng = random.Random(5)
        gone = dead = 0
        for _ in range(60):
            ua, ub = mb.units(0, [("vigilant", 3)], stance="cautious", fid="a"), mb.units(1, [("styx", 12)], fid="b")
            mb.fight(ua, ub, rng)
            gone += sum(1 for u in ua if u.alive and u.gone)
            dead += sum(1 for u in ua if not u.alive)
        self.assertGreater(gone, 0)                                       # some got away
        self.assertGreater(dead, 0)                                       # and some did not
        need = {c: mb.units(0, [(c, 1)])[0].flee_need for c in ("praetorian", "vigilant", "lethe")}
        self.assertGreater(need["praetorian"], need["vigilant"])          # a battleship needs more than half a minute to turn her back on the enemy: longer under fire
        self.assertGreater(need["vigilant"], need["lethe"])
        ua, ub = mb.units(0, [("praetorian", 1), ("vigilant", 3)], stance="cautious", fid="a"), mb.units(1, [("acheron", 3), ("styx", 6)], fid="b")
        mb.fight(ua, ub, rng)
        self.assertTrue(all(u.gone or not u.alive for u in ua))           # (nobody of the beaten fleet is left on the field)

    def test_the_battle_ends_and_ships_end_as_they_began_or_less(self) -> None:
        rng = random.Random(2)
        for _ in range(30):
            ua, ub = mb.units(0, [("praetorian", 2), ("vigilant", 4)], (14, 5, 0)), mb.units(1, [("acheron", 2), ("styx", 4)], (16, 5, 0))
            e = mb.fight(ua, ub, rng)
            self.assertTrue(e.over)
            self.assertLess(e.t, 2400.0)
            for u in ua + ub:
                self.assertLessEqual(u.hull, u.hull_max + 1e-6)
                self.assertGreaterEqual(u.hull, 0.0)
                self.assertTrue(u.alive or u.hull == 0.0)

    def test_a_fort_is_a_defender_that_cannot_run(self) -> None:
        rng = random.Random(4)
        u = mb.units(0, [("styx", 3)], stance="bold")
        fort = mb.Unit(mb.FORT_CLASS, 1, "fort", "defences", fort=5.0)
        e = mb.fight(u, [fort], rng)
        self.assertEqual(e.winner, 1)                                      # three destroyers do not take a level-5 fort
        self.assertIn(fort, e.alive(1))

    def test_the_model_matches_the_war_bench(self) -> None:
        """The abstract battle against what the commandlet gave (data/march/cal_cpp.json), within what 24 battles can say: the distance to the bench (ships left per class, the margin,
        who wins, how long, the craft) averages under 4 an experiment (the fit reaches about 2.6), and where the bench is clear about the winner the model gives it the field more
        often than not, with at most two exceptions (the known weak spots: a mixed battle of 6 against 8 that the bench always loses for ASTRA's capital ships, and duels of capital
        ships, which the bench leaves unfinished a third of the time and the model does not)."""
        path = ROOT / "data" / "march" / "cal_cpp.json"
        if not path.exists():
            self.skipTest("no calibration data in this checkout")
        import importlib.util
        spec = importlib.util.spec_from_file_location("march_calibrate", ROOT / "tools" / "march_calibrate.py")
        cal = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cal)
        data = json.loads(path.read_text())
        params = mb.Params.load()
        worst, total, n = 0.0, 0.0, 0
        wrong: list[str] = []
        for name, row in data.items():
            if name not in cal.EXPERIMENTS:
                continue
            mod = cal.pool(cal.run_model(cal.EXPERIMENTS[name], 80, params))
            err = cal.loss_of(row, mod)
            total += err
            n += 1
            worst = max(worst, err)
            if row["astra_wins"] >= 0.9 and mod["astra_wins"] <= 0.5:
                wrong.append(f"{name}: the bench has ASTRA winning {row['astra_wins']:.2f}, the model {mod['astra_wins']:.2f}")
            if row["mandate_wins"] >= 0.9 and mod["mandate_wins"] <= 0.5:
                wrong.append(f"{name}: the bench has the Mandate winning {row['mandate_wins']:.2f}, the model {mod['mandate_wins']:.2f}")
        self.assertGreater(n, 10)
        self.assertLessEqual(len(wrong), 2, wrong)
        self.assertLess(total / n, 4.0, f"the model is too far from the bench (mean loss {total / n:.2f}, worst {worst:.2f})")


class MovementTest(unittest.TestCase):
    def test_the_gates_and_the_guilds(self) -> None:
        m = world()
        self.assertEqual(m.path("Aurelia", "Concordia"), ["Meridian", "Concordia"])
        self.assertEqual(m.path("Aurelia", "Ophir"), ["Thule", "Ophir"])
        self.assertEqual(m.path("Nemet", "Meridian", "mandate"), ["Erebus", "Thule", "Aurelia", "Meridian"])      # not through Veyra: closed to warships
        self.assertEqual(m.path("Nemet", "Meridian"), ["Veyra", "Meridian"])                                       # for a courier it is the short way
        m.grant_passage("mandate", 600.0, "a deal at the Guildhall")
        self.assertEqual(m.path("Nemet", "Meridian", "mandate"), ["Veyra", "Meridian"])
        m.run(700.0)
        self.assertEqual(m.path("Nemet", "Meridian", "mandate")[0], "Erebus")

    def test_a_fleet_goes_through_the_gates_with_the_time_they_cost(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Aurelia", [("vigilant", 4)])
        ok, detail = m.order("astra", f.id, "move", "Cassia", instant=True)
        self.assertTrue(ok, detail)
        self.assertIn("Aurelia > Cassia", detail)
        m.run(10.0)
        self.assertEqual(f.where, "Aurelia")                               # it forms up first
        m.run(60.0)
        self.assertTrue(f.in_gate)
        self.assertEqual(f.route, ["Cassia"])
        m.run(300.0)
        self.assertEqual(f.where, "Cassia")
        self.assertEqual(f.order.kind, "hold")                             # arrived: it holds there
        self.assertEqual(f.zone, "gate")

    def test_an_order_takes_the_gates_to_reach_a_far_fleet(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Concordia", [("vigilant", 2)])
        ok, detail = m.order("astra", f.id, "move", "Meridian")
        self.assertTrue(ok)
        self.assertIsNotNone(f.pending)
        self.assertEqual(f.order.kind, "hold")
        m.run(10.0)
        self.assertEqual(f.order.kind, "hold")                             # (two Gates from the high command: not yet)
        m.run(60.0)
        self.assertEqual(f.order.kind, "move")

    def test_nobody_orders_what_is_not_theirs_or_cannot_be(self) -> None:
        m = world()
        ok, d = m.order("astra", "F-M4", "move", "Aurelia")
        self.assertFalse(ok)
        ok, d = m.order("astra", "F-A1", "dance", "Aurelia")
        self.assertFalse(ok)
        ok, d = m.order("astra", "F-A1", "move", "Nowhere")
        self.assertFalse(ok)
        ok, d = m.order("astra", "F-A1", "assault", "Veyra")
        self.assertFalse(ok)
        self.assertIn("neutral", d)
        ok, d = m.order("astra", "F-A3", "move", "Cassia")                 # the game's script has it
        self.assertFalse(ok)

    def test_a_fleet_that_does_not_run_dark_is_seen_coming_and_one_that_does_is_not(self) -> None:
        m = world()
        clear(m)
        f = put(m, "mandate", "Thule", [("styx", 6)])
        m.order("mandate", f.id, "move", "Aurelia", instant=True)
        m.run(400.0)
        wakes = [e for e in m.events if e.kind == "wake"]
        self.assertTrue(wakes)
        self.assertIn("astra", wakes[0].sides)                             # Aurelia's post hears the Gate cycling a minute ahead
        m2 = world()
        clear(m2)
        g = put(m2, "mandate", "Thule", [("styx", 6)])
        m2.order("mandate", g.id, "move", "Aurelia", dark=True, instant=True)
        m2.run(400.0)
        self.assertFalse([e for e in m2.events if e.kind == "wake"])

    def test_a_fleet_stopped_by_a_battle_takes_its_way_up_again(self) -> None:
        m = world()
        clear(m)
        a = put(m, "astra", "Thule", [("vigilant", 8)])
        put(m, "mandate", "Ophir", [("lethe", 1)], zone="gate")
        m.sys["Ophir"].fort_hp = 0.0                                       # (no defences: just the one frigate)
        m.war.systems["Ophir"]["owner"] = "silent"
        m.order("astra", a.id, "move", "Niflheim", instant=True)
        m.run(1800.0)
        self.assertIn(a.where, ("Niflheim", "Ophir"))
        self.assertTrue(a.where == "Niflheim" or a.route == ["Niflheim"] or a.in_gate)


class FogTest(unittest.TestCase):
    def test_nobody_sees_a_fleet_they_have_no_eyes_on(self) -> None:
        m = world()
        m.run(60.0)
        pic = m.picture("astra")
        self.assertNotIn("F-M4", pic)                                      # the Mandate's main body at Erebus is not on ASTRA's plot
        self.assertNotIn("Interdiction Fleet", pic)
        self.assertNotIn("F-M4", m.tracks["astra"])
        self.assertIn("F-A1", m.picture("astra"))                          # its own fleets are known exactly
        pm = m.picture("mandate")
        self.assertNotIn("7th Fleet Main Body", pm)

    def test_a_working_post_sees_the_fleets_in_its_system_and_a_silent_one_does_not(self) -> None:
        m = world()
        clear(m)
        enemy = put(m, "mandate", "Cassia", [("styx", 5), ("lethe", 3)])
        m.run(30.0)
        self.assertIn(enemy.id, m.tracks["astra"])
        tr = m.tracks["astra"][enemy.id]
        self.assertEqual(tr.level, 3)                                      # a post in an ASTRA system: identified
        m.sys["Cassia"].post["astra"] = False
        m.tracks["astra"].clear()
        m.run(30.0)
        self.assertEqual(m.tracks["astra"][enemy.id].level, 2)             # without the post, still its own system's eyes: classified
        m.war.systems["Cassia"]["owner"] = "mandate"
        m.tracks["astra"].clear()
        m.run(30.0)
        self.assertEqual(m.tracks["astra"][enemy.id].level, 1)             # not its system any more: only the drives its post next door hears through the Gate

    def test_an_estimate_is_not_the_truth_at_a_distance_and_it_ages(self) -> None:
        m = world()
        clear(m)
        enemy = put(m, "mandate", "Cassia", [("styx", 9)])
        m.sys["Cassia"].post["astra"] = False
        m.war.systems["Cassia"]["owner"] = "silent"
        put(m, "astra", "Aurelia", [("vigilant", 2)])
        m.run(30.0)
        tr = m.tracks["astra"].get(enemy.id)
        self.assertIsNotNone(tr)                                           # Aurelia's post hears the drives next door: a contact
        self.assertEqual(tr.level, 1)
        self.assertIsNone(tr.classes)
        self.assertNotEqual(tr.n, 0)
        m.fleets.pop(enemy.id)
        m.run(2000.0)
        self.assertNotIn(enemy.id, m.tracks["astra"])                      # the contact is lost with time

    def test_orders_and_news_take_the_gates(self) -> None:
        m = world()
        clear(m)
        put(m, "astra", "Concordia", [("vigilant", 2)])
        m.say("battle_end", "Concordia", "something happened at Concordia", ("astra",), 2)
        self.assertEqual(m.news("astra"), [])                              # the news is on its way
        m.run(60.0)
        self.assertEqual(len(m.news("astra")), 1)


class BattleWorldTest(unittest.TestCase):
    def test_two_fleets_meet_fight_and_what_is_lost_stays_lost(self) -> None:
        m = world()
        clear(m)
        m.war.systems["Thule"]["owner"] = "silent"
        a = put(m, "astra", "Thule", [("vigilant", 6)], order=Order("assault", "Thule", "steady", False, "default", "", 0.0))
        put(m, "mandate", "Thule", [("styx", 3)], order=Order("assault", "Thule", "bold", False, "default", "", 0.0))
        m.run(900.0)
        self.assertEqual(m.battles, {})
        self.assertGreater(m.score["mandate"]["ships_lost"], 0)
        self.assertEqual(m.score["astra"]["ships_killed"], m.score["mandate"]["ships_lost"])
        ends = [e for e in m.events if e.kind == "battle_end"]
        self.assertTrue(ends)
        self.assertEqual(ends[0].data["winner"], "astra")
        self.assertEqual(len(a.ships) + m.score["astra"]["ships_lost"], 6)
        survivors = [f for f in m.fleets.values() if f.side == "mandate"]
        self.assertTrue(all(f.where != "Thule" or f.untouchable_until > 0 or f.in_gate or f.route for f in survivors))     # what ran has gone

    def test_no_endless_skirmish_with_a_fleet_that_ran(self) -> None:
        """A frigate caught by a whole fleet breaks off once and leaves: it does not start a battle every fifteen seconds (the first bug the bench found)."""
        m = world()
        clear(m)
        put(m, "astra", "Aurelia", [("praetorian", 2), ("vigilant", 6)], order=Order("defend", "Aurelia", "steady", False, "default", "", 0.0))
        put(m, "mandate", "Aurelia", [("lethe", 1)], order=Order("recon", "Aurelia", "cautious", False, "default", "", 0.0), dark=True)
        m.run(1200.0)
        self.assertLessEqual(sum(1 for e in m.events if e.kind == "battle_start"), 2)

    def test_the_fleet_over_the_world_comes_to_the_gate_after_a_while(self) -> None:
        m = world()
        clear(m)
        picket = put(m, "astra", "Aurelia", [("vigilant", 2)], order=Order("defend", "Aurelia", "steady", False, "default", "", 0.0, None, "gate"), zone="gate")
        world_f = put(m, "astra", "Aurelia", [("praetorian", 2)], order=Order("defend", "Aurelia", "steady", False, "default", "", 0.0, None, "world"), zone="world")
        put(m, "mandate", "Aurelia", [("styx", 4)], order=Order("assault", "Aurelia", "bold", False, "default", "", 0.0))
        m.run(20.0)
        self.assertIn("Aurelia", m.battles)
        in_battle = {fid for s in SIDES for fid in m.battles["Aurelia"].fleets[s]}
        self.assertIn(picket.id, in_battle)
        self.assertNotIn(world_f.id, in_battle)                            # not yet: it is over the planet
        m.run(150.0)
        self.assertTrue(world_f.status == "engaged" or "Aurelia" not in m.battles)
        self.assertTrue([e for e in m.events if e.kind in ("responding", "battle_join") and world_f.id in e.fleets])

    def test_the_gates_defences_fire_on_whoever_comes_to_take_it(self) -> None:
        m = world()
        clear(m)
        m.war.systems["Cassia"]["owner"] = "astra"
        put(m, "mandate", "Cassia", [("styx", 2)], order=Order("assault", "Cassia", "bold", False, "default", "", 0.0))
        m.run(30.0)
        self.assertIn("Cassia", m.battles)
        self.assertGreater(m.battles["Cassia"].fort_side, -1)


class SiegeTest(unittest.TestCase):
    def test_a_system_with_nothing_left_to_defend_it_falls_after_its_time(self) -> None:
        m = world()
        clear(m)
        m.sys["Cassia"].fort_hp = 0.0
        f = put(m, "mandate", "Cassia", [("styx", 5)], order=Order("assault", "Cassia", "bold", False, "default", "", 0.0), zone="world")
        m.run(300.0)
        self.assertEqual(m.owner("Cassia"), "astra")
        self.assertEqual(m.sys["Cassia"].siege_by, "mandate")
        m.run(m.siege_time("Cassia") + 120.0)
        self.assertEqual(m.owner("Cassia"), "mandate")
        taken = [e for e in m.events if e.kind == "system_taken"]
        self.assertTrue(taken)
        self.assertEqual(m.score["mandate"]["systems_taken"], 1)
        self.assertEqual(f.order.kind, "defend")                           # and it holds what it took

    def test_the_war_map_follows_and_the_story_cannot_move_it(self) -> None:
        m = world()
        m.war.update("Cassia", owner="mandate", threat=3, note="a rumour")
        self.assertEqual(m.war.systems["Cassia"]["owner"], "astra")        # the telling does not take a system
        self.assertIn("a rumour", m.war.systems["Cassia"]["notes"])        # but it can say what is said of it
        m.sys["Cassia"].fort_hp = 0.0
        clear(m)
        put(m, "mandate", "Cassia", [("styx", 5)], order=Order("assault", "Cassia", "bold", False, "default", "", 0.0), zone="world")
        m.run(m.siege_time("Cassia") + 400.0)
        self.assertEqual(m.war.systems["Cassia"]["owner"], "mandate")      # taking it does

    def test_a_system_nobody_holds_is_claimed_by_whoever_stands_there(self) -> None:
        m = world()
        clear(m)
        self.assertEqual(m.owner("Thule"), "silent")
        put(m, "astra", "Thule", [("vigilant", 3)], order=Order("hold", "Thule", "steady", False, "default", "", 0.0))
        m.run(m.pace["claim_s"] + 60.0)
        self.assertEqual(m.owner("Thule"), "astra")
        self.assertTrue(m.sys["Thule"].post["astra"])                      # Thule Watch is listening again

    def test_the_capital_falling_ends_the_war(self) -> None:
        m = world()
        clear(m)
        m.sys["Concordia"].fort_hp = 0.0
        put(m, "mandate", "Concordia", [("acheron", 3)], order=Order("assault", "Concordia", "bold", False, "default", "", 0.0), zone="world")
        m.run(m.siege_time("Concordia") + 400.0)
        self.assertTrue(m.over)
        self.assertEqual(m.over["winner"], "mandate")
        ok, d = m.order("astra", "F-A1", "move", "Aurelia") if "F-A1" in m.fleets else (False, "the war is over")
        self.assertFalse(ok)


class EconomyTest(unittest.TestCase):
    def test_a_yard_builds_ships_by_its_points(self) -> None:
        m = world()
        clear(m)
        before = sum(f.n for f in m.fleets.values())
        m.run(3600.0)
        built = [e for e in m.events if e.kind == "production" and "Aurelia" in e.system]
        self.assertGreaterEqual(len(built), 2)                             # Aurelia: 3.4 points an hour, a destroyer a point
        self.assertGreater(sum(f.n for f in m.fleets.values()), before)

    def test_what_a_yard_builds_is_the_admirals_choice(self) -> None:
        m = world()
        ok, d = m.set_build("astra", "Aurelia", "praetorian")
        self.assertTrue(ok, d)
        self.assertEqual(m.sys["Aurelia"].build, "praetorian")
        ok, d = m.set_build("astra", "Aurelia", "styx")
        self.assertFalse(ok)                                               # not a class of theirs
        ok, d = m.set_build("astra", "Erebus", "vigilant")
        self.assertFalse(ok)                                               # not their yard

    def test_a_blockaded_yard_builds_nothing(self) -> None:
        m = world()
        clear(m)
        m.sys["Aurelia"].fort_hp = 0.0
        put(m, "mandate", "Aurelia", [("styx", 4)], order=Order("assault", "Aurelia", "bold", False, "default", "", 0.0), zone="world")
        m.run(1200.0)
        self.assertEqual(m.sys["Aurelia"].blockaded_by, "mandate")
        built = [e for e in m.events if e.kind == "production" and e.system == "Aurelia"]
        self.assertEqual(built, [])

    def test_a_depot_repairs_and_resupplies_and_a_fleet_out_of_supply_falls_back(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Aurelia", [("vigilant", 3)])
        for s in f.ships:
            s.hull = 0.4
        f.supply = 0.3
        m.run(900.0)
        self.assertGreater(f.hull, 0.8)
        self.assertGreater(f.supply, 0.9)
        g = put(m, "astra", "Thule", [("vigilant", 3)], order=Order("hold", "Thule", "steady", False, "default", "", 0.0))
        g.supply = 0.05
        m.run(60.0)
        self.assertEqual(g.order.kind, "withdraw")
        self.assertTrue([e for e in m.events if e.kind == "supply"])

    def test_splitting_and_merging_keep_every_ship(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Aurelia", [("praetorian", 2), ("vigilant", 6)])
        ok, d = m.split("astra", f.id, {"vigilant": 3}, "Picket Two", ("defend", "Cassia"), "guard Cassia")
        self.assertTrue(ok, d)
        self.assertEqual(f.n, 5)
        new = m.find_fleet("astra", "Picket Two")
        self.assertEqual(new.n, 3)
        ok, d = m.split("astra", f.id, {"vigilant": 9})
        self.assertFalse(ok)
        far = put(m, "astra", "Cassia", [("vigilant", 2)])
        ok, d = m.merge("astra", f.id, far.id)
        self.assertFalse(ok)                                               # not in the same place
        ok, d = m.merge("astra", f.id, new.id)
        self.assertTrue(ok, d)
        self.assertEqual(f.n, 8)
        self.assertNotIn(new.id, m.fleets)


class WarCourseTest(unittest.TestCase):
    def test_peace_needs_both_and_a_truce_stops_the_fighting(self) -> None:
        m = world()
        ok, d = m.propose("astra", "truce", "to bury the dead")
        self.assertTrue(ok)
        self.assertFalse(m.truce)
        ok, d = m.accept("mandate")
        self.assertTrue(ok, d)
        self.assertTrue(m.truce)
        clear(m)
        m.war.systems["Thule"]["owner"] = "silent"
        put(m, "astra", "Thule", [("vigilant", 4)])
        put(m, "mandate", "Thule", [("styx", 4)])
        m.run(200.0)
        self.assertEqual(m.battles, {})                                    # nobody shoots under a truce
        m.run(2000.0)
        self.assertFalse(m.truce)
        m2 = world()
        m2.propose("astra", "peace")
        m2.propose("mandate", "peace")
        self.assertTrue(m2.over)
        self.assertEqual(m2.over["how"], "armistice")

    def test_a_people_that_is_beaten_down_gives_up(self) -> None:
        m = world()
        m.will["astra"] = 0.03
        m.run(30.0)
        self.assertTrue(m.over)
        self.assertEqual(m.over["winner"], "mandate")

    def test_saving_and_loading_keep_the_war(self) -> None:
        m = world(4)
        a = ma.AutoAdmiral(m, "astra")
        b = ma.AutoAdmiral(m, "mandate")
        for _ in range(60):
            m.advance(m.t + 90)
            a.think()
            b.think()
        with tempfile.TemporaryDirectory() as tmp:
            path = f"{tmp}/march.json"
            m.save(path)
            m2 = world(4)
            self.assertTrue(m2.load(path))
        self.assertEqual({k: f.n for k, f in m.fleets.items()}, {k: f.n for k, f in m2.fleets.items()})
        self.assertEqual({k: (f.where, f.order.kind, f.order.target) for k, f in m.fleets.items()}, {k: (f.where, f.order.kind, f.order.target) for k, f in m2.fleets.items()})
        self.assertEqual(m.will, m2.will)
        self.assertEqual(m.picture("astra").split("\n", 1)[1], m2.picture("astra").split("\n", 1)[1])
        m2.advance(m2.t + 600)                                              # and it goes on
        self.assertGreater(m2.t, m.t)

    def test_the_game_script_brings_fleets_in_at_its_own_time(self) -> None:
        m = world()
        self.assertEqual(m.fleets["F-M1"].status, "scripted")
        m.live_scripts = True
        m.run(600.0)
        self.assertEqual(m.fleets["F-M1"].status, "scripted")             # the game has not brought it yet
        self.assertTrue(m.release_script("F-M1"))
        self.assertEqual(m.fleets["F-M1"].where, "Aurelia")
        self.assertEqual(m.fleets["F-M1"].status, "ready")


class HighCommandToolsTest(unittest.TestCase):
    """What the high commands, the director and the real simulation's join can do to the March besides ordering fleets: the staff's estimate, a fleet found by the story, the
    government's pressure, the tender, the Aquila's tasking, the picture the field commanders read."""

    def test_the_staff_estimate_is_as_uncertain_as_the_intelligence_and_forbids_nothing(self) -> None:
        m = world()
        clear(m)
        mine = put(m, "astra", "Aurelia", [("praetorian", 1), ("vigilant", 3)], name="Picket")
        put(m, "mandate", "Thule", [("styx", 5)], name="Foe")
        ok, text = m.assess("astra", [mine.id], "Thule")
        self.assertTrue(ok)
        self.assertIn("You hold no track on Thule", text)                                 # (nothing is known: it says so, and what finds out)
        self.assertIn("recon", text)
        m.run(5.0)
        post = m.sys["Aurelia"].post["astra"]
        self.assertTrue(post)
        ok, text = m.assess("astra", [mine.id], "Thule")                                   # (a post next door hears the drives through the Gate)
        self.assertTrue(ok and "Staff estimate" in text, text)
        self.assertIn("as many as the contact says", text)
        self.assertIn("a third more than it says", text)
        self.assertNotIn("Foe", text)                                                      # (the estimate names what is on the plot, never the truth's own name)
        self.assertEqual(m.assess("astra", ["F-A99"], "Thule")[0], False)
        self.assertEqual(m.assess("astra", [mine.id], "Atlantis")[0], False)

    def test_a_fleet_the_story_reveals_is_a_real_one_and_where_it_is(self) -> None:
        m = world()
        clear(m)
        foe = put(m, "mandate", "Erebus", [("acheron", 2), ("styx", 4)], name="Hidden Main Body")
        self.assertNotIn(foe.id, m.tracks["astra"])
        self.assertTrue(m.reveal("astra", foe.id, "a defector from the Anchorage"))
        tr = m.tracks["astra"][foe.id]
        self.assertEqual((tr.system, tr.level), ("Erebus", 2))
        self.assertTrue(any(e.kind == "intel" and "a defector from the Anchorage" in e.text["astra"] for e in m.events))
        self.assertFalse(m.reveal("astra", "F-M99", "nobody"))                             # (no invention: the fleet must be there)
        mine = put(m, "astra", "Aurelia", [("vigilant", 2)], name="Own")
        self.assertFalse(m.reveal("astra", mine.id, "it is ours"))                         # (and it is the other side's)
        self.assertFalse(m.reveal("mandate", foe.id, "ours"))

    def test_the_governments_pressure_is_read_not_obeyed_by_the_code(self) -> None:
        m = world()
        clear(m)
        f = put(m, "mandate", "Erebus", [("styx", 3)], name="Squadron")
        m.pressure("mandate", "The Hall wants Aurelia before the harvest.", 45)
        self.assertIn("ORDERS FROM HOME", m.picture("mandate"))
        self.assertNotIn("ORDERS FROM HOME", m.picture("astra"))
        m.run(30.0)
        self.assertEqual(f.order.kind, "hold")                                             # (nothing moved by itself: it is the high command's to answer)
        m.run(46 * 60.0)
        self.assertNotIn("ORDERS FROM HOME", m.picture("mandate"))                         # (it runs out)

    def test_the_tender_is_busy_after_it_is_used(self) -> None:
        m = world()
        self.assertEqual(m.use_tender("astra"), (True, 0.0))
        ok, wait = m.use_tender("astra")
        self.assertFalse(ok)
        self.assertGreater(wait, 800.0)
        m.run(901.0)
        self.assertTrue(m.use_tender("astra")[0])

    def test_the_aquila_is_tasked_to_go_not_to_stay(self) -> None:
        m = world()
        ok, detail = m.task_aquila("Aurelia", "hold")
        self.assertFalse(ok)
        self.assertIn("tell the Captain", detail)
        ok, detail = m.task_aquila("Cassia", "relieve the yards", "they are open")
        self.assertTrue(ok)
        self.assertEqual(m.aquila_task["system"], "Cassia")
        self.assertIn("FLEET'S STANDING ORDER TO THE AQUILA", m.picture("astra"))
        self.assertNotIn("FLEET'S STANDING ORDER TO THE AQUILA", m.picture("mandate"))
        self.assertFalse(m.task_aquila("Atlantis", "x")[0])

    def test_the_field_commanders_read_their_own_sides_plan_and_orders(self) -> None:
        m = world()
        m.set_plan("mandate", "Take the Gate; the main body comes when the picket's strength is known.")
        text = m.field_brief("mandate", "Aurelia")
        self.assertIn("Take the Gate", text)
        self.assertNotIn("ASTRA's", text)
        self.assertNotIn("Aurelia Picket", text)                                          # (the enemy's own fleets are not in a side's brief)

    def test_a_fleet_may_be_named_the_way_the_picture_writes_it(self) -> None:
        m = world()
        f = m.find_fleet("astra", "F-A1 7th Fleet Main Body")
        self.assertIsNotNone(f)
        self.assertEqual(f.id, "F-A1")
        self.assertIsNone(m.find_fleet("mandate", "F-A1 7th Fleet Main Body"))               # (never a fleet of the other side)

    def test_an_order_to_a_fleet_the_game_plays_is_an_intent_on_its_record_not_a_move(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Aurelia", [("vigilant", 3)], name="With the Aquila")
        m.real_adopt(f, "Aurelia")
        ok, detail = m.order("astra", f.id, "move", "Cassia", by="admiral", reason="the yards need it")
        self.assertTrue(ok)
        self.assertIn("with the Aquila", detail)
        self.assertIn("the Captain", detail)
        self.assertEqual((f.status, f.where, f.route), ("real", "Aurelia", []))              # (nothing moved: the game has it)
        self.assertEqual((f.order.kind, f.order.target, f.order.by), ("move", "Cassia", "admiral"))
        self.assertIn("Fleet orders for With the Aquila: move Cassia", m.field_brief("astra", "Aurelia"))
        m.run(600.0)
        self.assertEqual((f.status, f.where), ("real", "Aurelia"))
        foe = put(m, "mandate", "Aurelia", [("styx", 2)], name="Foe in the game")
        m.real_adopt(foe, "Aurelia")
        ok, detail = m.order("mandate", foe.id, "withdraw", "Thule", by="admiral")
        self.assertTrue(ok and "on the spot" in detail)

    def test_the_real_simulation_scores_what_it_loses_like_a_battle_of_the_map(self) -> None:
        m = world()
        clear(m)
        f = put(m, "mandate", "Aurelia", [("acheron", 1), ("styx", 2)], name="In the game")
        m.real_adopt(f, "Aurelia")
        will = m.will["mandate"]
        m.real_lost(f, f.ships[1], "destroyed")
        self.assertEqual(f.n, 2)
        self.assertEqual((m.score["mandate"]["ships_lost"], m.score["astra"]["ships_killed"]), (1, 1))
        self.assertLess(m.will["mandate"], will)
        m.real_lost(f, f.ships[0], "destroyed")                                             # (the carrier: a capital ship)
        m.real_lost(f, f.ships[0], "destroyed")
        self.assertNotIn(f.id, m.fleets)
        self.assertTrue(m.real_tally["mandate"].get("capital"))
        m.real_t0 = m.t - 400
        self.assertEqual(m.real_over("Aurelia"), 3)                                         # (a capital ship was lost: a major battle)
        self.assertEqual(m.real_tally["mandate"]["lost"], 0)                                # (the tally starts again)


class ReflexTest(unittest.TestCase):
    def test_a_threatened_system_is_answered_by_the_fleets_that_can_reach_it(self) -> None:
        m = world()
        clear(m)
        helper = put(m, "astra", "Meridian", [("praetorian", 1), ("vigilant", 4)], order=Order("hold", "Meridian", "steady", False, "default", "", 0.0))
        put(m, "mandate", "Cassia", [("styx", 4)], order=Order("hold", "Cassia", "steady", False, "default", "", 0.0))
        m.sys["Cassia"].fort_hp = 0.0
        m.run(30.0)
        auto = ma.AutoAdmiral(m, "astra", "full")
        auto.think()
        self.assertEqual(helper.pending.kind if helper.pending else helper.order.kind, "defend")

    def test_the_capitals_spare_ships_go_into_the_field_and_its_guard_stays(self) -> None:
        m = world()
        clear(m)
        put(m, "astra", "Concordia", [("praetorian", 3), ("vigilant", 8)], name="Home Fleet", zone="world")
        auto = ma.AutoAdmiral(m, "astra", "full")
        auto.think()
        names = [f.name for f in m.side_fleets("astra")]
        self.assertIn("Concordia Field Fleet", names)
        self.assertGreaterEqual(m.find_fleet("astra", "Home Fleet").power, auto.d.home - 1.5)

    def test_a_battered_fleet_goes_to_a_depot_and_a_minds_order_stands_over_the_reflexes(self) -> None:
        m = world()
        clear(m)
        f = put(m, "astra", "Thule", [("vigilant", 3)])
        for s in f.ships:
            s.hull = 0.3
        auto = ma.AutoAdmiral(m, "astra", "safety")
        auto.think()
        self.assertEqual((f.pending or f.order).kind, "refit")
        g = put(m, "astra", "Thule", [("vigilant", 3)])
        for s in g.ships:
            s.hull = 0.3
        g.order = Order("hold", "Thule", "steady", False, "admiral", "hold Thule whatever it costs", 0.0)
        auto.think()
        self.assertIsNone(g.pending)

    def test_both_sides_have_the_same_rules_in_a_mirrored_world(self) -> None:
        """Not a statistical test of the bench (bench/march_sim.py --world sym does that over hundreds of wars): a smoke test that a mirrored world plays out and is fair
        on a handful of seeds."""
        from bench import march_sim
        diffs = []
        for seed in range(1, 17):
            row = march_sim.run_war(seed, 6, "none", 1.0, "sym", False)
            diffs.append(row["held"]["astra"] - row["held"]["mandate"])
        # a side that was favoured would show as a mean far from zero in the units of its own spread (2.6 sigma: a one in a hundred chance for a fair world)
        spread = statistics.pstdev(diffs) / (len(diffs) ** 0.5)
        self.assertLess(abs(statistics.mean(diffs)), max(0.5, 2.6 * spread), diffs)


if __name__ == "__main__":
    unittest.main()
