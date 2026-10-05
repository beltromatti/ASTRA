"""The war director (v2: no acts, the pulse, both sides reinforce, negotiations, a look in on long fights) against a scripted model and a scripted game
(no network, no cost).

    cd mind && .venv/bin/python -m unittest bench.war_director_unit -v"""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from typing import Any

from astra_mind import director as dr
from astra_mind import models
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.war import WarMap
from astra_mind.war_minds import WarMinds
from bench.war_mock import MockLLM

models.LEDGER.write_file = False


class Model:
    """Answers the director's calls with the scripted tool calls (`script`: a list of (tool, args) in the order wanted); records what it was asked."""

    def __init__(self) -> None:
        self.script: list[tuple[str, dict[str, Any]]] = []
        self.calls: list[dict[str, Any]] = []
        self.prose = ""

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = [t["function"]["name"] for t in (tools or [])]
        self.calls.append({"tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[-1].get("content", "")), "messages": messages})
        out = Completion(model=model, provider="fake", cost=0.002)
        if self.prose and not self.script:
            out.content = self.prose
            return out
        for i, (name, args) in enumerate(self.script):
            if name not in names:
                continue
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"d{len(self.calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out

    async def close(self) -> None:
        pass


class Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


STATE = {"hull_pct": 80, "shields": {"strength_pct": 60}, "weapons": {"missiles": "40 in the VLS"}, "casualties": "2 killed", "alert": "red",
         "contacts": [{"id": "T-01", "name": "ASN Praetorian", "class": "praetorian", "status": "friendly", "range_km": 4.0},
                      {"id": "T-21", "name": "Acheron", "class": "acheron", "status": "hostile", "range_km": 12.0},
                      {"id": "T-22", "name": "Styx", "class": "styx", "status": "hostile", "range_km": 14.0}], "_events": ["x"]}
QUIET = {**STATE, "contacts": [STATE["contacts"][0]], "alert": "green"}


class DirectorTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.model = Model()
        self.said: list[tuple[str, str]] = []
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.registered: list[tuple[str, dict[str, Any]]] = []
        self.calls_negotiate: list[tuple[str, str]] = []

        async def say(speaker: str, text: str, lang: str, tone: str) -> None:
            self.said.append((speaker, text))

        async def command(name: str, args: dict[str, Any]) -> dict[str, Any]:
            self.commands.append((name, args))
            return {"ok": True, "detail": "reinforcements scheduled in 120 s; contact ids T-41, T-42; the first is the group's leader"}

        async def negotiate(contact: str, terms: str) -> bool:
            self.calls_negotiate.append((contact, terms))
            return contact == "T-21"

        self.clock = Clock()
        self.d = dr.Director(self.model, say, command, lambda c, p: self.registered.append((c, p)), war=WarMap(f"{self.tmp.name}/war.json"))
        self.d.clock = self.clock
        self.d.t0 = self.d._last_obs = self.d.last_pulse_t = self.clock()
        self.d.peace_since = self.clock()
        self.d.negotiate = negotiate
        self.voices: dict[str, tuple[str, str]] = {}
        self.minds = WarMinds(MockLLM(), say, command, register_voice=lambda k, n, v: self.voices.__setitem__(k, (n, v)))
        self.d.war_minds = self.minds

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def tick(self, state: dict[str, Any], seconds: float, step: float = 1.0) -> None:
        for _ in range(int(seconds / step)):
            self.clock.t += step
            self.d.observe(state)

    # ------------------------------------------------------------------------------------------------ the pulse
    async def test_the_pulse_counts_fight_and_peace_and_runs_of_engagements(self) -> None:
        self.tick(QUIET, 200)
        self.tick(STATE, 120)
        self.assertIsNotNone(self.d.fight_since)
        self.assertEqual(self.d.in_a_row, 1)
        self.tick(QUIET, 60)                                                  # a short breath: the next fight is the second of a run
        self.tick(STATE, 30)
        self.assertEqual(self.d.in_a_row, 2)
        self.tick(QUIET, 200)                                                 # a real peace ends the run
        self.tick(STATE, 10)
        self.assertEqual(self.d.in_a_row, 1)
        facts = self.d.pulse_facts(STATE)
        self.assertIn("A fight is in progress now", facts)
        self.assertIn("hull 80%", facts)
        self.assertIn("1 praetorian", facts)
        self.assertIn("2 (1 acheron, 1 styx)", facts)
        self.assertIn("The war's balance", facts)

    async def test_a_long_fight_is_looked_in_on_then_every_few_minutes(self) -> None:
        self.tick(QUIET, 300)                                                 # (a quiet spell since the last look at the story)
        self.tick(STATE, 100)
        self.assertFalse(self.d.battle_due())
        self.tick(STATE, 60)
        self.assertTrue(self.d.battle_due())
        self.model.script = [("start_beat", {"type": "none", "why": "the fight is evenly matched", "crew_mood": "focused"})]
        await self.d.battle_pulse("it", STATE)
        self.assertFalse(self.d.battle_due())
        self.tick(STATE, 250)
        self.assertTrue(self.d.battle_due())

    # ------------------------------------------------------------------------------------------------ beats
    async def test_the_prompt_has_no_acts_and_reads_the_pulse_and_the_threads(self) -> None:
        self.d.threads = ["the Mandate gathers a second wave at Erebus"]
        self.model.script = [("start_beat", {"type": "calm", "why": "breathe", "crew_mood": "tired", "delay_s": 120}), ("transmit", {"text": "Calma, Capitano."})]
        self.tick(QUIET, 30)
        await self.d._next_beat("it", QUIET)
        system = self.model.calls[0]["system"]
        self.assertNotIn("Act I", system)
        self.assertNotIn("act", self.model.calls[0]["tools"])
        self.assertIn("The pulse", system)
        self.assertIn("the Mandate gathers a second wave at Erebus", system)
        self.assertIn("NEVER rig a fight in progress", system)
        self.assertNotIn('"act"', json.dumps(dr.BEAT_TOOL))

    async def test_none_lets_the_war_run_and_keeps_the_threads_and_the_mood(self) -> None:
        self.model.script = [("start_beat", {"type": "none", "why": "the Mandate is regrouping", "crew_mood": "watchful",
                                             "threads": ["the Mandate regroups beyond the gate", "Thule Watch is silent"]})]
        await self.d._next_beat("it", QUIET)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.said, [])
        self.assertEqual(self.d.threads, ["the Mandate regroups beyond the gate", "Thule Watch is silent"])
        self.assertEqual(self.d.mood, "watchful")
        self.assertIn("the war ran on: the Mandate is regrouping", self.d.campaign[-1])
        d2 = dr.Director(self.model, lambda *a: None, lambda *a: None, lambda *a: None, war=WarMap(f"{self.tmp.name}/war.json"))
        d2.load()
        self.assertEqual(d2.threads, ["the Mandate regroups beyond the gate", "Thule Watch is silent"])

    async def test_reinforcements_arrive_with_captains_who_get_minds_and_voices(self) -> None:
        self.model.script = [("start_beat", {"type": "reinforcements", "why": "Fleet answers", "crew_mood": "hopeful", "delay_s": 150, "bearing_deg": 200, "range_km": 20,
                                             "ships": [{"class": "vigilant", "name": "ASN Resolute", "captain": {"name": "Commander Lena Okafor", "rank": "Commander",
                                                                                                         "bio": "Dry and fast.", "gender": "f"}},
                                                       {"class": "vigilant", "name": "ASN Tenacity", "captain": {"name": "Lieutenant Commander Piet Haas", "rank": "Lieutenant Commander",
                                                                                                          "bio": "Cautious.", "gender": "m"}}]}),
                            ("transmit", {"text": "Due cacciatorpediniere in arrivo."})]
        await self.d._next_beat("it", QUIET)
        self.assertEqual(self.commands[0][0], "director_beat")
        self.assertEqual(self.commands[0][1]["beat"]["type"], "reinforcements")
        self.assertIn("T-41", self.minds.allies)
        self.assertEqual(self.minds.allies["T-41"].name, "Commander Lena Okafor")
        self.assertEqual(self.minds.allies["T-42"].name, "Lieutenant Commander Piet Haas")
        self.assertIn(self.voices[self.minds.allies["T-41"].key][1], dr.ALLY_VOICES["f"])
        self.assertIn(self.voices[self.minds.allies["T-42"].key][1], dr.ALLY_VOICES["m"])
        self.assertEqual(self.minds.allies["T-41"].ship, "the Vigilant-class ASN Resolute")
        self.assertEqual(self.said[0], ("admiral", "Due cacciatorpediniere in arrivo."))

    async def test_a_mandate_commander_calls_to_talk_and_the_numbers_do_not_change(self) -> None:
        self.model.script = [("start_beat", {"type": "negotiation", "caller": "T-21", "terms": "he offers a ceasefire to recover his dead", "why": "Solm has lost a destroyer",
                                             "crew_mood": "wary"})]
        await self.d._next_beat("it", STATE)
        self.assertEqual(self.calls_negotiate, [("T-21", "he offers a ceasefire to recover his dead")])
        self.assertEqual(self.commands, [])                                   # nothing was sent to the simulation: no number moved
        self.assertIn("negotiation: T-21 calls the Aquila", self.d.campaign[-1])

    async def test_a_negotiation_with_nobody_there_is_not_played(self) -> None:
        self.model.script = [("start_beat", {"type": "negotiation", "caller": "T-99", "terms": "x", "why": "y", "crew_mood": "z"})]
        await self.d._next_beat("it", STATE)
        self.assertIn("could not begin", self.d.campaign[-1])

    async def test_in_a_fight_only_what_a_war_brings_is_played(self) -> None:
        self.tick(STATE, 200)
        self.model.script = [("start_beat", {"type": "transit", "system_name": "Meridian", "why": "move", "crew_mood": "x"})]
        await self.d._next_beat("it", STATE, in_battle=True)
        self.assertEqual(self.commands, [])
        self.assertIn("guns are firing", self.d.campaign[-1])
        self.assertIn("A FIGHT IS IN PROGRESS", self.model.calls[0]["user"])
        self.model.script = [("start_beat", {"type": "reinforcements", "why": "a relief on its way", "crew_mood": "x", "delay_s": 240, "ships": [{"class": "vigilant", "name": "ASN Faith"}]}),
                             ("transmit", {"text": "In arrivo."})]
        await self.d._next_beat("it", STATE, in_battle=True)
        self.assertEqual(self.commands[0][1]["beat"]["delay_s"], 240)

    async def test_a_mandate_second_wave_in_a_fight_is_a_raid_with_a_commander(self) -> None:
        self.tick(STATE, 200)
        self.model.script = [("start_beat", {"type": "raid", "why": "the second wave through the gate", "crew_mood": "tense", "delay_s": 200, "range_km": 40, "bearing_deg": 70,
                                             "ships": [{"class": "styx", "name": "Lethe's Daughter"}], "commander": {"name": "Ferryman Ilya Voss", "rank": "Ferryman", "bio": "Proud.",
                                                                                                              "orders": "relieve the strike group"}}),
                            ("transmit", {"text": "Contatti in arrivo da settanta."})]
        await self.d._next_beat("it", STATE, in_battle=True)
        self.assertEqual(self.commands[0][1]["beat"]["type"], "raid")
        self.assertEqual(self.registered[0][0], "T-41")
        self.assertEqual(self.registered[0][1]["name"], "Ferryman Ilya Voss")

    async def test_the_decisive_battle_registers_the_allies_captains_too(self) -> None:
        self.model.script = [("start_beat", {"type": "decisive", "why": "the war has gathered both sides", "crew_mood": "grim", "bearing_deg": 70, "range_km": 40,
                                             "allies": [{"class": "praetorian", "name": "ASN Valiant", "captain": {"name": "Captain Aiko Brandt", "rank": "Captain", "bio": "Steel.",
                                                                                                           "gender": "f"}}],
                                             "ships": [{"class": "acheron", "name": "Kharon"}], "commander": {"name": "Archon Teodor Vale", "rank": "Archon", "bio": "Old.",
                                                                                                      "orders": "take the gate"}}),
                            ("transmit", {"text": "È la battaglia decisiva."})]
        await self.d._next_beat("it", QUIET)
        self.assertTrue(self.d.decisive)
        self.assertEqual(self.minds.allies["T-41"].name, "Captain Aiko Brandt")
        self.assertEqual(self.registered[0][1]["name"], "Archon Teodor Vale")

    def ids_reply(self, n: int) -> None:
        """The game's answer to the next beats: n contact ids in the groups' order (T-41 ...)."""
        async def command(name: str, args: dict[str, Any]) -> dict[str, Any]:
            self.commands.append((name, args))
            ids = ", ".join(f"T-{41 + i}" for i in range(n))
            return {"ok": True, "detail": f"{args.get('beat', {}).get('type', 'beat')} scheduled in 120 s; contact ids {ids}; the first is the group's leader"}
        self.d.command = command

    async def test_a_mandate_force_in_groups_gives_each_group_its_commander(self) -> None:
        self.ids_reply(5)
        grp = lambda name, ships, who: {"name": name, "formation": "wedge", "ships": [{"class": c, "name": n} for c, n in ships],
                                         "commander": {"name": who, "rank": "Ferryman", "bio": "x", "orders": "y"}}
        self.model.script = [("start_beat", {"type": "raid", "why": "the Interdiction Fleet's first wave", "crew_mood": "tense", "delay_s": 200,
                                             "range_km": 45, "bearing_deg": 60,
                                             "groups": [grp("Third Carrier Group", [("acheron", "Nyx"), ("acheron", "Erebus")], "Archon Mira Kade"),
                                                        grp("Styx Line Dorn", [("styx", "Asphodel"), ("styx", "Tartarus"), ("styx", "Hypnos")], "Warden Ilse Dorn")]}),
                             ("transmit", {"text": "Una forza del Mandato attraversa il portale."})]
        await self.d._next_beat("it", QUIET)
        beat = self.commands[0][1]["beat"]
        self.assertEqual([g["name"] for g in beat["groups"]], ["Third Carrier Group", "Styx Line Dorn"])
        self.assertNotIn("commander", beat)                                  # (the people are the mind's; the game gets the ships)
        self.assertEqual([(c, p["name"]) for c, p in self.registered], [("T-41", "Archon Mira Kade"), ("T-43", "Warden Ilse Dorn")])
        self.assertEqual(self.registered[1][1]["ship"], "the Styx-class Asphodel")

    async def test_reinforcements_in_groups_register_every_captain(self) -> None:
        self.ids_reply(3)
        cap = lambda n, g: {"name": n, "rank": "Captain", "bio": "x", "gender": g}
        self.model.script = [("start_beat", {"type": "reinforcements", "why": "the 7th Fleet answers in strength", "crew_mood": "hopeful", "delay_s": 180,
                                             "groups": [{"name": "Battle Group Resolute", "ships": [
                                                            {"class": "praetorian", "name": "ASN Resolute", "captain": cap("Captain Mara Lind", "f")},
                                                            {"class": "vigilant", "name": "ASN Valour", "captain": cap("Commander Tom Reyes", "m")}],
                                                         "wings": [{"carrier": 0, "kind": "fighter", "n": 8, "mission": "cap"}]},
                                                        {"name": "Destroyer Squadron 9", "ships": [
                                                            {"class": "vigilant", "name": "ASN Kestrel", "captain": cap("Commander Ana Silva", "f")}]}]}),
                             ("transmit", {"text": "Arriva il gruppo della Resolute."})]
        await self.d._next_beat("it", QUIET)
        self.assertEqual([self.minds.allies[i].name for i in ("T-41", "T-42", "T-43")], ["Captain Mara Lind", "Commander Tom Reyes", "Commander Ana Silva"])

    async def test_the_decisive_battle_in_groups_is_a_force_not_eight_ships(self) -> None:
        self.ids_reply(4)
        self.model.script = [("start_beat", {"type": "decisive", "why": "the assault on Aurelia", "crew_mood": "grim", "bearing_deg": 60, "range_km": 50,
                                             "groups": [{"name": "Interdiction Fleet", "ships": [{"class": "acheron", "name": "Kharon"}, {"class": "acheron", "name": "Styx Regnant"}],
                                                         "commander": {"name": "Archon Teodor Vale", "rank": "Archon", "bio": "Old.", "orders": "take the gate"}},
                                                        {"name": "Raider Screen", "ships": [{"class": "lethe", "name": "Moros"}, {"class": "lethe", "name": "Keres"}]}]}),
                             ("transmit", {"text": "È l'assalto."})]
        await self.d._next_beat("it", QUIET)
        raid = [a["beat"] for n, a in self.commands if a["beat"]["type"] == "raid"][0]
        self.assertEqual(len(raid["groups"]), 2)
        self.assertNotIn("ships", raid)
        self.assertTrue(self.d.decisive)
        self.assertEqual([(c, p["name"]) for c, p in self.registered], [("T-41", "Archon Teodor Vale")])

    async def test_a_styx_line_called_reinforcements_is_still_the_mandates(self) -> None:
        self.ids_reply(2)
        self.model.script = [("start_beat", {"type": "reinforcements", "why": "a Styx line comes to press the Aquila", "crew_mood": "tense",
                                             "groups": [{"name": "Styx Line Kade", "goes_for": "escorts",
                                                         "ships": [{"class": "styx", "name": "Acheron's Wake"}, {"class": "styx", "name": "Lethe's Mouth"}],
                                                         "commander": {"name": "Ferryman Iva Kade", "rank": "Ferryman", "bio": "x", "orders": "y"}}]}),
                             ("transmit", {"text": "Il Gate sta ciclando."})]
        await self.d._next_beat("it", QUIET)
        self.assertEqual([(c, p["name"]) for c, p in self.registered], [("T-41", "Ferryman Iva Kade")])   # a Mandate commander, not two ASTRA captains
        self.assertNotIn("T-41", self.minds.allies)

    async def test_a_new_campaign_begins_with_the_war_gathering(self) -> None:
        self.d.reset()
        self.assertTrue(any("Interdiction Fleet" in t for t in self.d.threads))

    async def test_a_chapter_ends_with_the_decisive_battle_and_the_war_goes_on(self) -> None:
        self.assertEqual(self.d.arc, 1)

        class Finale:
            async def run(self, director: Any, result: str, lang: str) -> dict[str, Any]:
                return {}
        self.d.finale = Finale()
        self.d.decisive = True
        self.model.script = [("start_beat", {"type": "none", "why": "the dust settles", "crew_mood": "numb"})]
        orig = asyncio.sleep

        async def fast(t: float, *a: Any, **k: Any) -> None:
            await orig(0)
        dr.asyncio.sleep = fast
        try:
            await self.d._end_arc("engagement over: victory", "it", QUIET)
        finally:
            dr.asyncio.sleep = orig
        self.assertEqual(self.d.arc, 2)

    # ------------------------------------------------------------------------------------------------ Rourke
    async def test_rourke_stays_silent_when_the_words_were_for_a_ships_captain(self) -> None:
        self.model.script = []
        lines = await self.d.admiral_reply("Praetorian, concentrate on the Acheron", "it", STATE)
        self.assertEqual(lines, [])
        self.assertEqual(self.said, [])
        self.assertIn("answering for them", self.model.calls[0]["system"])

    async def test_rourke_answers_what_is_for_fleet_command_and_his_grant_names_captains(self) -> None:
        self.model.script = [("transmit", {"text": "Vi mando due cacciatorpediniere."}),
                             ("grant", {"kind": "reinforcements", "delay_s": 120, "ships": [{"class": "vigilant", "name": "ASN Courage",
                                                                                           "captain": {"name": "Commander Ines Marlow", "rank": "Commander", "bio": "Calm.", "gender": "f"}}]})]
        lines = await self.d.admiral_reply("Fleet, request reinforcements", "it", STATE)
        self.assertEqual(lines, ["Vi mando due cacciatorpediniere."])
        self.assertEqual(self.said, [("admiral", "Vi mando due cacciatorpediniere.")])
        self.assertIn("T-41", self.minds.allies)

    async def test_prose_instead_of_the_briefing_is_not_said_and_is_asked_for_again(self) -> None:
        self.model.prose = "I would tell the captain that two destroyers are coming."
        lines = await self.d._brief_line({"type": "reinforcements", "why": "x"}, "scheduled", "it", STATE)
        self.assertEqual(lines, [])
        self.assertEqual(len(self.model.calls), 2)                              # asked once more, with the tool
        self.assertIn("was not transmitted", self.model.calls[1]["user"])


if __name__ == "__main__":
    unittest.main()
