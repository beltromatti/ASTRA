"""Offline tests of the crew-as-people module (astra_mind/npc.py) against a scripted model: no network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.npc_unit -v

What is checked is the plumbing and the perception the behaviour stands on: who counts as within earshot and who the prompt is
written for; that what a person could know of the ship depends on their department (an engineer has the reactor and the damage
boards, a sensor technician the contacts, a steward the menu, and none of them the enemy's side or another department's
instruments); that a model's line reaches the voice as the answer to the Captain, for a person who was listed and nobody else; that
silence is an answer (the bridge's gate opens at once); that an error, a timeout or the Captain speaking again leave the bridge in
charge; and that what the Captain and each person said is kept and shown to them next time. The model's own judgement (whether a
line is in character, in the Captain's language, never invents a fact) is for the real model, by ear."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from typing import Any

from astra_mind import models, npc
from astra_mind.medbay import FREE_VOICES
from astra_mind.openrouter import Completion, ToolCall

models.LEDGER.write_file = False

ENGINEER = {"id": "npc17", "name": "Petty Officer Amara Diallo", "rank": "Petty Officer", "gender": "f", "dept": "engineering", "home": "Halcyon",
            "job": "machinist", "watch": "Gold", "doing": "on duty, working as machinist (Deck 7 · Section D · Machinery Space)",
            "place": "Deck 7 · Section D · Machinery Space", "dist_m": 2.1, "angle_deg": 4, "facing": True,
            "memory": ["A fire broke out in section C of deck 7 at 09:12, where I was (a few minutes ago, ship time 09:12)"], "friends": ["Crewman Jonas Berg"]}
STEWARD = {"id": "npc301", "name": "Crewman Tomasz Kowalski", "rank": "Crewman", "gender": "m", "dept": "stewards and galley", "home": "Earth", "job": "cook",
           "watch": "Red", "doing": "on duty, working as cook (Deck 4 · Section B · Main Galley)", "place": "Deck 4 · Section B · Main Galley", "dist_m": 3.6,
           "angle_deg": 30, "facing": False, "memory": [], "friends": []}
SENSOR = {"id": "npc90", "name": "Ensign Priya Iyer", "rank": "Ensign", "gender": "f", "dept": "sensors", "home": "Mars", "job": "sensor technician",
          "watch": "Blue", "doing": "on duty", "place": "Deck 2 · Section A · Sensor Array Room", "dist_m": 6.0, "angle_deg": 50, "facing": False,
          "memory": [], "friends": []}
FAR = {"id": "npc5", "name": "Crewman Far Away", "dept": "weapons", "dist_m": 14.0, "facing": False}

STATE = {"alert": "green", "location": "Aurelia System, home of the 7th Fleet", "reactor_pct": 78, "hull_pct": 97, "shields": {"strength_pct": 88},
         "power_pct": {"shields": 100, "weapons": 100, "engines": 100, "sensors": 100}, "thermal": {"heat_pct": 14, "status": "nominal", "radiators": "retracted"},
         "damage": ["deck 7 section C: fire — team 2 working, 40% done"], "damage_control": "4 teams, 3 free", "casualties": "none",
         "contacts": [{"id": "T-23", "name": "Cocytus", "status": "hostile", "range_km": 22.4}], "squadrons": {"alpha": "CAP, 8 Falcons"},
         "weapons": {"railgun": "ready"}, "janus_gate": "quiet", "mess": {"menu": "braised lamb with barley"},
         "_mandate": {"your_ships": [{"id": "T-23", "secret_plan": "flank the Aquila"}]}}


class FakeVoice:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str, str, dict[str, Any]]] = []

    async def __call__(self, speaker: str, text: str, lang: str, tone: str, **kw: Any) -> int:
        self.lines.append((speaker, text, lang, tone, kw))
        return len(self.lines)


class FakeLLM:
    def __init__(self) -> None:
        self.script: list[tuple[str, dict[str, Any]]] = []
        self.requests: list[dict[str, Any]] = []
        self.error = ""
        self.delay = 0.0

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3,
                   extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools, providers=providers, max_price=max_price))
        out = Completion(model=model, provider="fake", cost=0.0002)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            out.error = self.error
            return out
        for i, (name, args) in enumerate(self.script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out

    async def close(self) -> None:
        pass


class ParseAndPick(unittest.TestCase):
    def test_the_games_context_lists_who_is_there(self) -> None:
        ctx = {"place": "corridors", "people": [ENGINEER, STEWARD, {"id": "mess3", "name": "a diner"}, {"name": "nobody"}]}
        got = npc.parse_people(ctx, {})
        self.assertEqual([p.id for p in got], ["npc17", "npc301"])           # only the people of the life (npc ids)
        self.assertEqual(got[0].memory, ENGINEER["memory"])
        self.assertTrue(got[0].facing)

    def test_the_ship_state_carries_them_when_the_context_does_not(self) -> None:
        got = npc.parse_people({"place": "corridors"}, {"life": {"people_near": [SENSOR]}})
        self.assertEqual([p.id for p in got], ["npc90"])
        self.assertEqual(npc.parse_people(None, {}), [])

    def test_who_the_words_could_be_for(self) -> None:
        ps = npc.parse_people({"people": [SENSOR, STEWARD, ENGINEER, FAR]}, {})
        chosen = npc.pick(ps)
        self.assertEqual([p.id for p in chosen], ["npc17", "npc301"])        # the one looked at first, then the near; the far and the not-so-near not
        self.assertEqual(npc.pick(npc.parse_people({"people": [FAR]}, {})), [])
        many = npc.parse_people({"people": [dict(STEWARD, id=f"npc{i}", dist_m=1.0 + i * 0.3) for i in range(9)]}, {})
        self.assertEqual(len(npc.pick(many)), npc.MAX_LISTENERS)


class WhatTheyKnow(unittest.TestCase):
    def test_an_engineer_has_the_reactor_and_the_damage_boards(self) -> None:
        text = "\n".join(npc.knowledge("engineering", STATE))
        self.assertIn("reactor 78%", text)
        self.assertIn("fire", text)
        self.assertNotIn("Cocytus", text)                                   # the contact plot is not theirs
        self.assertNotIn("Falcons", text)

    def test_a_sensor_technician_has_the_plot_and_not_the_engine_room(self) -> None:
        text = "\n".join(npc.knowledge("sensors", STATE))
        self.assertIn("Cocytus", text)
        self.assertNotIn("power to systems", text)
        self.assertNotIn("team 2 working", text)

    def test_a_cook_has_the_menu_and_what_the_whole_ship_knows(self) -> None:
        text = "\n".join(npc.knowledge("stewards and galley", STATE, {"war": "Thule Watch is silent", "mood": "tired but proud"}))
        self.assertIn("braised lamb with barley", text)
        self.assertIn("Thule Watch is silent", text)                        # the fleet net's news is on the Mess wall
        self.assertIn("tired but proud", text)
        self.assertNotIn("Cocytus", text)
        self.assertNotIn("reactor", text.lower().replace("the reactor's", ""))

    def test_the_enemys_side_is_nobodys(self) -> None:
        for dept in ("command staff", "sensors", "weapons", "engineering", "marines", "Air Group pilots", "medbay", "unknown department"):
            text = "\n".join(npc.knowledge(dept, STATE))
            self.assertNotIn("secret_plan", text, dept)
            self.assertNotIn("your_ships", text, dept)

    def test_everyone_knows_the_alarm_and_the_memorial_wall(self) -> None:
        st = dict(STATE, alert="red", casualties="3 wounded in the medbay (0 critical, 1 serious, 2 stable), 1 killed — the fallen: Crewman Jonas Berg (engineering)")
        text = "\n".join(npc.knowledge("logistics", st))
        self.assertIn("general quarters", text)
        self.assertIn("Jonas Berg", text)


class Answering(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.llm = FakeLLM()
        self.voice = FakeVoice()
        self.table: dict[str, tuple[str, str]] = {}
        self.npcs = npc.Npcs(self.llm, self.voice, self.table, store=Path(self.tmp.name) / "talk.json")
        self.people = npc.pick(npc.parse_people({"people": [ENGINEER, STEWARD]}, {}))
        self.world = {"state": STATE, "war": "", "mood": "", "clock": "09:15"}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def gate(self) -> "asyncio.Future[bool]":
        return asyncio.get_running_loop().create_future()

    async def test_the_one_who_was_asked_answers_and_the_bridge_stays_out(self) -> None:
        self.llm.script = [("say", {"speaker": "npc17", "text": "Il condotto ha ceduto alle nove, Capitano: ho visto le scintille.", "tone": "tense"})]
        g = self.gate()
        spoke = await self.npcs.hear("cos'è successo qui sotto?", "it", self.people, self.world, g, "at DECK 7 · MACHINERY")
        self.assertEqual(spoke, [("npc17", "Il condotto ha ceduto alle nove, Capitano: ho visto le scintille.")])
        self.assertFalse(g.result())                                          # somebody answered: the officers do not
        speaker, text, lang, tone, kw = self.voice.lines[0]
        self.assertEqual((speaker, lang, tone), ("npc17", "it", "tense"))
        self.assertTrue(kw.get("answer"))                                     # a reply to the Captain: first in the voice's queue
        name, voice = self.table["npc17"]
        self.assertEqual(name, "Petty Officer Amara Diallo")                  # the game's roster name, registered for the voice stage
        self.assertIn(voice, FREE_VOICES["f"])                                # a voice of the free pool, a woman's

    async def test_silence_is_an_answer(self) -> None:
        self.llm.script = []
        g = self.gate()
        spoke = await self.npcs.hear("Timoniere, rotta zero-nove-zero", "it", self.people, self.world, g)
        self.assertEqual(spoke, [])
        self.assertTrue(g.result())                                           # the words were for the bridge
        self.assertEqual(self.voice.lines, [])

    async def test_a_line_for_someone_not_listed_is_never_said(self) -> None:
        self.llm.script = [("say", {"speaker": "npc90", "text": "Sono io, Capitano.", "tone": "calm"}),
                           ("say", {"speaker": "xo", "text": "Capitano?", "tone": "calm"}),
                           ("say", {"speaker": "npc301", "text": "Sì?", "tone": "warm"})]
        g = self.gate()
        spoke = await self.npcs.hear("ehi, tu", "it", self.people, self.world, g)
        self.assertEqual([w for w, _ in spoke], ["npc301"])
        self.assertEqual([l[0] for l in self.voice.lines], ["npc301"])

    async def test_at_most_a_few_lines(self) -> None:
        self.llm.script = [("say", {"speaker": "npc17", "text": f"Riga numero {i}.", "tone": "calm"}) for i in range(7)]
        await self.npcs.hear("parlate", "it", self.people, self.world, self.gate())
        self.assertEqual(len(self.voice.lines), npc.MAX_LINES)

    async def test_an_error_or_a_late_answer_leaves_the_bridge_in_charge(self) -> None:
        self.llm.error = "HTTP 500"
        g = self.gate()
        self.assertEqual(await self.npcs.hear("come va?", "it", self.people, self.world, g), [])
        self.assertTrue(g.result())
        self.llm.error = ""
        self.llm.delay = 0.5
        self.llm.script = [("say", {"speaker": "npc17", "text": "Tutto bene.", "tone": "calm"})]
        with unittest.mock.patch.object(npc, "WAIT_S", 0.1):
            g2 = self.gate()
            self.assertEqual(await self.npcs.hear("come va?", "it", self.people, self.world, g2), [])
        self.assertTrue(g2.result())
        self.assertEqual(self.voice.lines, [])

    async def test_the_captain_speaking_again_cuts_them_off(self) -> None:
        self.llm.delay = 0.5
        self.llm.script = [("say", {"speaker": "npc17", "text": "Tutto bene.", "tone": "calm"})]
        g = self.gate()
        task = asyncio.create_task(self.npcs.hear("come va?", "it", self.people, self.world, g))
        await asyncio.sleep(0.1)
        self.assertEqual(self.npcs.preempt(), 1)
        await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(g.done() and g.result())
        self.assertEqual(self.voice.lines, [])

    async def test_the_prompt_is_written_for_these_people_in_this_language(self) -> None:
        self.llm.script = []
        await self.npcs.hear("come va il lavoro?", "it", self.people, self.world, self.gate(), "at DECK 7 · MACHINERY")
        req = self.llm.requests[0]
        system, user = req["messages"][0]["content"], req["messages"][1]["content"]
        self.assertIn("Italian", system)
        self.assertIn('"Capitano"', system)
        self.assertEqual([t["function"]["name"] for t in req["tools"]], ["say"])
        self.assertIn("come va il lavoro?", user)
        self.assertIn("`npc17`", user)
        self.assertIn("Petty Officer Amara Diallo", user)
        self.assertIn("machinist", user)                                      # what they do
        self.assertIn("ship time 09:12", user)                                # what they remember
        self.assertIn("Crewman Jonas Berg", user)                             # their friends
        self.assertIn("the Captain is looking at them", user)
        self.assertIn("reactor 78%", user)                                    # an engineer's view of the ship...
        steward = user.split("`npc301`")[1]
        self.assertIn("braised lamb", steward)                                # ... and a cook's
        self.assertNotIn("reactor 78%", steward)
        self.assertNotIn("secret_plan", user)
        self.assertEqual(req["max_price"], models.CEILING)                    # never above DeepSeek V4.1 Flash's price
        self.assertEqual(req["model"], models.role("npc").model)

    async def test_what_was_said_is_kept_and_shown_next_time(self) -> None:
        self.llm.script = [("say", {"speaker": "npc17", "text": "Un condotto, Capitano.", "tone": "calm"})]
        await self.npcs.hear("cosa ti preoccupa?", "it", self.people, self.world, self.gate())
        self.llm.script = []
        await self.npcs.hear("e adesso?", "it", self.people, self.world, self.gate())
        user = self.llm.requests[1]["messages"][1]["content"]
        self.assertIn('Captain: "cosa ti preoccupa?" / they: "Un condotto, Capitano."', user)
        # and it survives a restart of the mind
        again = npc.Npcs(self.llm, self.voice, {}, store=Path(self.tmp.name) / "talk.json")
        self.assertEqual(list(again.talk["npc17"])[0][0], "cosa ti preoccupa?")
        again.reset()
        self.assertEqual(npc.Npcs(self.llm, self.voice, {}, store=Path(self.tmp.name) / "talk.json").talk, {})

    async def test_the_officers_are_told_the_captain_is_among_the_crew(self) -> None:
        note = self.npcs.note_for_crew(self.people)
        self.assertIn("Petty Officer Amara Diallo", note)
        self.assertIn("say nothing", note)
        self.assertEqual(self.npcs.note_for_crew([]), "")


class TheRole(unittest.TestCase):
    def test_a_small_cheap_model_under_the_ceiling(self) -> None:
        r = models.role("npc")
        self.assertEqual(r.max_price, models.CEILING)
        self.assertLessEqual(r.max_tokens, 400)
        self.assertEqual(r.fallback, "chatter")

    def test_it_can_be_swapped_without_touching_code(self) -> None:
        import os
        from astra_mind import env
        env.load_env.cache_clear()
        os.environ["ASTRA_MODEL_NPC"] = "mistralai/mistral-small-3.2-24b-instruct@mistral"
        try:
            r = models.role("npc")
            self.assertEqual((r.model, r.providers), ("mistralai/mistral-small-3.2-24b-instruct", ("mistral",)))
        finally:
            os.environ.pop("ASTRA_MODEL_NPC", None)
            env.load_env.cache_clear()


if __name__ == "__main__":
    unittest.main()
