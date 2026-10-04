"""Offline tests of VOCI-3 (docs/brief/VOCI-3.md): a clear bridge and a Captain in control. No network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.voci3_unit -v

What is checked here is the mechanics the behaviour stands on (the minds' judgement is for the real models, by their tool calls and by ear): where the Captain is is the
first thing every crew turn reads, and the officers are told it beats anything remembered; (as the milestones land) the nets' traffic reaches the consoles and the listening
officer and never the bridge's speaker unless it is addressed to the Captain, a line addressed to him is never lost, the silent log is a real tool, and the 5 October games
replay through all of it."""
from __future__ import annotations

import unittest

from astra_mind import context as context_model
from astra_mind import crew as crew_mod
from astra_mind import models

models.LEDGER.write_file = False


class TestWhereTheCaptainIs(unittest.TestCase):
    """The lead's request after the 5 October games: «you are already in your quarters», said three times to a Captain on Deck 8, because the models trusted the memory of
    a transport over the game's live reading of him."""

    RAW = {"place": "assault-shuttle_bay", "place_name": "DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B", "deck": 8, "section": "B", "pawn": "on_foot", "in_earshot": [],
           "facing": None, "channel": None}
    STATE = {"captain": "in the Assault-Shuttle Bay (Deck 8 · Marines & Armory, section B), away from the bridge: the XO has the conn; the bridge officers speak by intercom"}

    def test_the_context_carries_the_badge(self) -> None:
        ctx = context_model.parse(self.RAW, self.STATE)
        self.assertEqual(ctx.place_name, "DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B")
        self.assertEqual((ctx.deck, ctx.section), (8, "B"))

    def test_the_badge_does_not_repeat_what_the_name_says(self) -> None:
        self.assertEqual(context_model.badge_of("DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B", "x", 8, "B"), "DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B")
        self.assertEqual(context_model.badge_of("MESS HALL", "mess", 4, "C"), "MESS HALL (deck 4, section C)")
        self.assertEqual(context_model.badge_of("", "captains_quarters", None, ""), "captains quarters")
        self.assertEqual(context_model.badge_of("", "", None, ""), "")

    def test_the_line_has_the_ships_sentence_and_the_badge(self) -> None:
        line = context_model.where_now(context_model.parse(self.RAW, self.STATE), self.STATE)
        self.assertIn("Assault-Shuttle Bay (Deck 8", line)
        self.assertIn("his badge reads: DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B", line)

    def test_an_event_turn_has_the_ships_sentence_alone(self) -> None:
        self.assertEqual(context_model.where_now(None, self.STATE), self.STATE["captain"])
        self.assertEqual(context_model.where_now(None, {}), "")

    def test_an_older_game_without_context_is_not_made_up(self) -> None:
        ctx = context_model.parse(None, {"captain": "on the bridge"})
        self.assertEqual(context_model.badge(ctx), "")
        self.assertEqual(context_model.where_now(ctx, {"captain": "on the bridge"}), "on the bridge")

    def test_raw_context_for_the_people_around_him(self) -> None:
        self.assertEqual(context_model.badge_of_raw(self.RAW), "DECK 8 · ASSAULT-SHUTTLE BAY · SECTION B")
        self.assertEqual(context_model.badge_of_raw(None), "")

    def test_it_is_the_first_thing_the_crew_reads(self) -> None:
        where = context_model.where_now(context_model.parse(self.RAW, self.STATE), self.STATE)
        now = crew_mod.bridge_now({"captain": "x"}, ["an event"], where=where)
        head, _, rest = now.partition("[The bridge now]\n")
        self.assertTrue(rest.startswith(crew_mod.WHERE_HEAD), rest[:120])
        self.assertLess(now.index("his badge reads"), now.index("Recent events"))
        self.assertIn("beats everything remembered", now)

    def test_without_a_reading_the_head_is_not_there(self) -> None:
        self.assertNotIn("Where the Captain is NOW", crew_mod.bridge_now({}, [], where=""))

    def test_the_doctrine_says_it_beats_the_memory_and_names_the_places_as_the_plan_does(self) -> None:
        prompt = crew_mod.system_prompt("it", {"transporter": {"room": {}}}, [])
        self.assertIn("it beats everything remembered", prompt)
        self.assertIn("Assault-Shuttle Bay", prompt)
        self.assertIn("Marine Armory", prompt)


if __name__ == "__main__":
    unittest.main()
