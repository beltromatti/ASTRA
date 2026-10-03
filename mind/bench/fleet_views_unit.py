"""FLOTTA-VIVA, the war minds' side: what a commander is told of the inside of a ship (no network, no cost, no engine).

    cd mind && .venv/bin/python -m unittest bench.fleet_views_unit -v

The game gives each ship that has been hit through its plating an inside (Source/ASTRA/AstraFleetInterior.*, docs/FLOTTA-VIVA.md), and says what it can of it:
`aboard` under a ship of the commander's own side (what her captain knows: the hands lost, who has the conn, what burns and vents, the power the guns and the drive
still have, the damage parties), `seen_aboard` under any other ship (what the eye and the sensors make of her from outside, by how well they know her).
What is checked here: that the render functions put what the game says into the picture, in words, and nothing where the game says nothing (a ship that has not
been hit costs no tokens); that nothing else of the picture moved; and that the doctrine tells the minds how to read the lines."""
from __future__ import annotations

import unittest
from typing import Any

from astra_mind import models, war_minds
from astra_mind.war_minds import aboard_line, render_astra_extras, render_enemy, render_groups, seen_line
from bench.war_minds_unit import Fixture, astra_state, ev, foe, group, mandate_state
from bench.war_minds_unit import member

models.LEDGER.write_file = False

# What FleetBriefInto writes under one's own ship (AstraFleetViews.cpp, BriefJson): the keys only where there is something to say.
HURT = {
    "crew": {"fit": 182, "wounded": 31, "killed": 17, "of": 230},
    "command": "Commander Idris Haldane is dead; Lieutenant Commander Noor Brandt (tactical officer) has the conn",
    "fires": 2, "breaches": 1, "rooms_without_power": 5,
    "power_pct": {"weapons": 62, "engines": 80},
    "pressure_bulkheads_shut": 3,
    "worst": ["fire in the magazine B (the ordnance feed is cut): a party on its way, 14 s", "breach in the cargo bay: no party free"],
    "damage_parties": "2 of 3 at work",
    "rooms": {"bridge": "damaged", "medbay": "lost"},
}

# What it writes under another's (SeenJson): by how well the observer knows her.
SEEN_EYE = {"breaches_venting": 2, "windows_dark_in": "bow, mid"}
SEEN_TRACK = {**SEEN_EYE, "fires_aboard": 3, "life_signs_pct": 65, "power_pct": {"weapons": 30, "engines": 50}}


def mine(i: str, **kw: Any) -> dict[str, Any]:
    return {"id": i, "class": "acheron", "hull_pct": 64, "shields_pct": 12, "missiles": 8, **kw}


class AboardLine(unittest.TestCase):
    def test_says_nothing_when_the_game_does(self) -> None:
        for empty in (None, {}, [], "", 0):
            self.assertEqual(aboard_line(empty), "")
            self.assertEqual(seen_line(empty), "")

    def test_a_hurt_ship_in_words(self) -> None:
        text = aboard_line(HURT)
        for must in ("crew 182 fit, 31 wounded, 17 killed of 230", "is dead", "has the conn", "2 fires", "1 breach venting", "5 rooms without power",
                     "3 pressure bulkheads shut", "power left: weapons 62%, engines 80%", "rooms: bridge damaged, medbay lost", "damage parties 2 of 3 at work",
                     "fire in the magazine B", "breach in the cargo bay"):
            self.assertIn(must, text)
        self.assertNotIn("\n", text)

    def test_singulars(self) -> None:
        text = aboard_line({"fires": 1, "breaches": 1, "rooms_without_power": 1, "pressure_bulkheads_shut": 1})
        self.assertEqual(text, "1 fire, 1 breach venting, 1 room without power, 1 pressure bulkhead shut")

    def test_only_what_is_there(self) -> None:
        self.assertEqual(aboard_line({"fires": 4}), "4 fires")
        self.assertEqual(aboard_line({"power_pct": {"flight_deck": 40}}), "power left: flight deck 40%")
        self.assertEqual(aboard_line({"crew": {"fit": 10, "wounded": 0, "killed": 0, "of": 10}}), "crew 10 fit, 0 wounded, 0 killed of 10")

    def test_the_worst_are_two(self) -> None:
        text = aboard_line({"worst": ["a", "b", "c"]})
        self.assertIn("a | b", text)
        self.assertNotIn("c", text.replace("on their hands", ""))

    def test_the_eye_and_the_track(self) -> None:
        eye = seen_line(SEEN_EYE)
        self.assertEqual(eye, "2 breaches venting atmosphere, windows dark in the bow, mid")
        track = seen_line(SEEN_TRACK)
        self.assertIn("3 hot spots", track)
        self.assertIn("life signs about 65%", track)
        self.assertIn("power weapons about 30%, engines about 50%", track)

    def test_a_malformed_view_does_not_break_the_picture(self) -> None:
        for odd in ({"crew": "many", "fires": "x", "power_pct": [1, 2], "worst": "nope", "rooms": 3}, {"crew": {"fit": None}, "fires": "x", "breaches": None}):
            self.assertIsInstance(aboard_line(odd), str)
        self.assertIsInstance(seen_line({"life_signs_pct": None, "breaches_venting": "?", "power_pct": "x"}), str)


class Pictures(unittest.TestCase):
    def view(self, members: list[dict[str, Any]], ships: list[dict[str, Any]]) -> dict[str, Any]:
        return {"your_groups": [{"id": 1, "name": "Line", "state": "engaged", "formation": "wedge", "order_in_force": "auto", "leader": members[0]["id"],
                                 "engagement_range_km": 4.0, "your_strength": 3.0, "enemy_strength_near": 3.0, "morale": 0.8, "members": members}],
                "enemy_groups": [{"label": "group of M-01", "ships": ships, "range_km": 22.0, "nearest_ship_km": 20.5, "bearing_deg": 240}]}

    def test_own_ship_line(self) -> None:
        text = render_groups(self.view([mine("A-01", aboard=HURT), mine("A-02")], []))
        a01, a02 = [ln for ln in text.splitlines() if ln.strip().startswith(("A-01", "A-02"))]
        self.assertIn("aboard: crew 182 fit", a01)
        self.assertNotIn("aboard", a02)
        self.assertTrue(a01.startswith("   A-01 acheron hull 64% shields 12%"))

    def test_a_ship_not_hit_is_as_it_was(self) -> None:
        with_key = render_groups(self.view([mine("A-01", aboard={})], []))
        without = render_groups(self.view([mine("A-01")], []))
        self.assertEqual(with_key, without)

    def test_the_enemy_as_seen(self) -> None:
        text = render_enemy(self.view([mine("A-01")], [{"id": "M-01", "class": "acheron", "hull_pct": 51, "shields_pct": 0, "seen_aboard": SEEN_TRACK},
                                                         {"id": "M-02", "class": "styx", "hull_pct": 100, "shields_pct": 100}]))
        self.assertIn("M-01 acheron hull 51% shields 0% [seen aboard: 2 breaches venting atmosphere", text)
        self.assertIn("M-02 styx hull 100% shields 100%", text)
        self.assertEqual(text.count("seen aboard"), 1)

    def test_the_aquila_captain_reads_friends_and_foes(self) -> None:
        state = {"hull_pct": 100, "contacts": [
            {"id": "A-02", "status": "friendly", "name": "ASN Tarn (Styx)", "range_km": 6.0, "bearing_deg": 30, "hull_pct": 55, "aboard": {"fires": 2, "crew": {"fit": 90, "wounded": 20, "killed": 30, "of": 140}}},
            {"id": "A-03", "status": "friendly", "name": "ASN Ness (Styx)", "range_km": 7.0, "bearing_deg": 40, "hull_pct": 100},
            {"id": "M-01", "status": "hostile", "class": "acheron", "range_km": 5.0, "hull_pct": 40, "seen_aboard": SEEN_EYE}]}
        text = render_astra_extras(state)
        self.assertIn("(aboard: crew 90 fit, 20 wounded, 30 killed of 140; 2 fires)", text)
        self.assertIn("M-01 acheron 5.0 km (hull 40%; seen aboard: 2 breaches venting atmosphere, windows dark in the bow, mid)", text)
        a03 = [p for p in text.split("; ") if p.startswith("A-03") or "A-03" in p][0]
        self.assertNotIn("aboard", a03)

    def test_the_mandate_admiral_reads_the_astra_ships_it_holds(self) -> None:
        view = {"your_ships": [{"id": "M-01", "ew_officer": "x"}], "astra_ships": [{"id": "A-01", "hull_pct": 70, "shields_pct": 20, "seen_aboard": SEEN_EYE},
                                                                                  {"id": "A-02", "hull_pct": 90, "shields_pct": 90}],
                "enemy_groups": [{"ships": [{"id": "A-01"}, {"id": "A-02"}]}]}
        text, _ = war_minds.mandate_extras(view)
        self.assertIn("A-01 hull 70% shields 20% [seen aboard: 2 breaches venting atmosphere, windows dark in the bow, mid]", text)
        self.assertNotIn("A-02 hull 90% shields 90% [", text)


class InThePrompt(Fixture):
    """The whole path: a view as the game sends it, a pulse of a mind, the prompt the model is given."""
    sides = ("mandate", "astra")

    async def test_the_mandate_admiral_is_given_the_insides_of_its_ships_and_the_enemys_hull(self) -> None:
        vanguard = group("Vanguard", 2, [member("M-01", "acheron", missiles=32, aboard=HURT), member("M-02"), member("M-03")])
        enemies = [foe("group of A-01", [{"id": "A-01", "class": "acheron", "hull_pct": 51, "shields_pct": 0, "seen_aboard": SEEN_TRACK},
                                         {"id": "A-02", "class": "styx", "hull_pct": 100, "shields_pct": 100}])]
        st = mandate_state([vanguard], enemies)
        await self.feed(st)
        await self.feed(st, 9)
        call = self.calls("mandate/admiral")[0]
        self.assertIn("aboard: crew 182 fit, 31 wounded, 17 killed of 230", call["user"])
        self.assertIn("fire in the magazine B", call["user"])
        self.assertIn("A-01 acheron hull 51% shields 0% [seen aboard: 2 breaches venting atmosphere, windows dark in the bow, mid, 3 hot spots, life signs about 65%", call["user"])
        self.assertNotIn("seen aboard", call["user"].split("A-02")[1].split("\n")[0])
        self.assertIn("`aboard`", call["system"])                           # and the doctrine that says how to read it

    async def test_a_group_commander_of_astra_reads_its_own_members_only_in_full(self) -> None:
        vig = group("Vanguard", 2, [member("A-01", "acheron", aboard=HURT), member("A-02")])
        pick = group("Picket", 3, [member("A-03", "styx", aboard={"fires": 1})])
        st = astra_state([vig, pick], [foe("group of M-01", [{"id": "M-01", "class": "acheron", "hull_pct": 70, "shields_pct": 40, "seen_aboard": SEEN_EYE}])],
                         [ev(1, "Vanguard: A-01 crew down to 75% (17 killed, 31 wounded of 230)")])
        await self.feed(st)
        await self.feed(st, 9)
        calls = self.calls("astra/group/Vanguard")
        self.assertTrue(calls)
        user = calls[0]["user"]
        self.assertIn("aboard: crew 182 fit", user)
        self.assertIn("[seen aboard: 2 breaches venting atmosphere", user)
        self.assertNotIn("1 fire", user)                                     # the other group's ship is a line, not in full


class Doctrine(unittest.TestCase):
    def test_the_minds_are_told_how_to_read_the_lines(self) -> None:
        for d in (war_minds.doctrine(False), war_minds.doctrine(True), war_minds.DOCTRINE):
            self.assertIn("`aboard`", d)
            self.assertIn("`seen aboard`", d)
            self.assertIn("magazine", d)

    def test_the_lines_are_short_enough_to_pay_for(self) -> None:
        # a tick of a ship in the worst state the model draws is a line of a few hundred characters, not a page
        self.assertLess(len(aboard_line(HURT)), 700)
        self.assertLess(len(seen_line(SEEN_TRACK)), 200)


if __name__ == "__main__":
    unittest.main()
