"""Offline tests of the flight net (astra_mind/flight_minds.py) against a scripted model: no network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.flight_unit -v

What is checked is the plumbing the behaviour stands on: which game events are the net's (and which stay with Price and the XO); that a burst of news makes one
pulse after a short settle and not more than the budget allows, and that the Captain's words never wait and answer first; that the prompt carries the facts the
people may know (the squadrons, the console, the plot, the net's log with Price's lines) and none they may not (the Mandate's view), with the language in the user
message so that the stable system prompt stays cacheable; that a voice reaches the stage with the right speaker, priority and answer flag and a dead squadron's pilots
never speak; that `mission` goes to the game as the flight console's own `station` command with the authority checked (a leader orders his own squadron, the CAG any,
nobody else; on their own initiative the console's delegation decides), that a refused order comes back to the one who gave it for one correction, and that a model
that fails or stalls on the Captain's words hands them to the bridge; that Eagle's wing is formed and dissolved by the game's events and renames its two pilots; and
that memories are kept, loaded and forgotten with the campaign. Whether a line is in character, in the Captain's language and short is for the real model, by ear
(bench/flight_live.py)."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any

from astra_mind import flight_minds as fm
from astra_mind import models, stations as station_model
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tts import GENDER, VOICES

models.LEDGER.write_file = False

REPO = Path(__file__).resolve().parents[2]


def ship_state(**over: Any) -> dict[str, Any]:
    """What the game's snapshot carries in a fight (the crew's state), with the flight groups as the game words them, and the Mandate's own view (which the net must never read)."""
    st = json.loads(json.dumps(LocalShip(stations=True, fight=True).snapshot()))
    st["squadrons"] = {"alpha": "airborne: 6 Falcons airborne, mission cap; 2 lost", "bravo": "on deck, ready (7 Hammers)", "drones": "ready (12 Wasps)"}
    st["enemy_small_craft"] = "4 Harpy strike fighters airborne (rockets and guns), the nearest 11.2 km from us"
    st["contacts"] = [{"id": "T-02", "name": "ASN Vigilant", "class": "vigilant", "status": "friendly", "range_km": 3.0, "bearing_deg": 70, "hull_pct": 100},
                      {"id": "T-21", "name": "Acheron", "class": "acheron", "status": "hostile", "range_km": 24.0, "bearing_deg": 240, "hull_pct": 90}]
    st["captain"] = "on the bridge"
    st["casualties"] = "1 killed — the fallen: Lieutenant Anil Rao (call sign Wick)"
    st["_mandate"] = {"your_ships": [{"id": "T-21", "secret_plan": "flank the Aquila at 04:12"}]}
    st.update(over)
    return st


LOSS = ("flight: alpha squadron has lost 2 Falcons to enemy fire, 6 left — Lieutenant Anil Rao (call sign Wick) killed; Ensign Jin Park (call sign Moth) ejected, "
        "recovered wounded by search and rescue")
AIRBORNE = "flight: alpha squadron airborne, 8 Falcons on CAP"
TORPEDO = "flight: bravo squadron torpedo run on T-21: 5 torpedoes away, bombers returning"
RECOVERED = "flight: alpha squadron recovered, 6 of 8 Falcons aboard, rearming (60 s)"
SPLASH = "tactical: 3 Harpies splashed, 1 of the enemy strike fighters left"
WING = "flight: Eagle's wing joined — Eagle 2 and Eagle 3, two Falcons of Alpha, are on the Captain's wing"
FLYING = ("flying a Falcon of Alpha (callsign Eagle), 3.4 km from the Aquila (she is at 7 o'clock level), hull 100%, 4 missiles; around the Falcon: a Harpy (Mandate strike "
          "fighter) at 2 o'clock high, 3.1 km, closing; the XO has the conn and the Captain talks to the bridge by radio (Price is the Captain's flight controller)")


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class ScriptedLLM:
    """The model: each call pops the next reply (a list of tool calls); the last one repeats. `requests` keeps what was asked."""

    def __init__(self) -> None:
        self.replies: list[list[tuple[str, dict[str, Any]]]] = []
        self.requests: list[dict[str, Any]] = []
        self.delay = 0.0
        self.error = ""
        self.content = ""

    def say(self, *calls: tuple[str, dict[str, Any]]) -> "ScriptedLLM":
        self.replies.append(list(calls))
        return self

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3,
                   extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools, max_tokens=max_tokens))
        out = Completion(model=model, provider="fake", cost=0.0004, prompt_tokens=2500, completion_tokens=90, cached_tokens=2000)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            out.error = self.error
            return out
        reply = (self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]) if self.replies else []
        out.content = self.content if not reply else ""
        for i, (name, args) in enumerate(reply):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out

    async def close(self) -> None:
        pass


class Bed:
    """A flight net with its stage, its game and its clock, all scripted."""

    def __init__(self, tmp: str, standing: set[str] | None = None) -> None:
        self.llm = ScriptedLLM()
        self.clock = Clock()
        self.lines: list[dict[str, Any]] = []
        self.commands: list[tuple[str, dict[str, Any], str]] = []
        self.result: dict[str, Any] = {"ok": True, "detail": "alpha squadron: 6 airborne re-tasked, mission escort on ASN Vigilant (T-02)"}
        self.voices: dict[str, tuple[str, str]] = {}
        self.unanswered: list[list[str]] = []
        self.flight = fm.FlightMinds(self.llm, self._say, self._execute, lang=lambda: "it", clock=self.clock,
                                     register_voice=lambda k, n, v: self.voices.__setitem__(k, (n, v)), standing=lambda: standing or set(),
                                     path=lambda: str(Path(tmp) / "flight.json"))
        self.flight.on_unanswered = self._unanswered

    async def _say(self, key: str, text: str, lang: str, tone: str, *, urgent: bool = False, answer: bool = False) -> None:
        self.lines.append({"speaker": key, "text": text, "lang": lang, "tone": tone, "urgent": urgent, "answer": answer})

    async def _execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.commands.append((name, args, by))
        return dict(self.result)

    async def _unanswered(self, words: list[str]) -> None:
        self.unanswered.append(words)

    def at(self, dt: float) -> None:
        self.clock.t += dt

    async def settle(self, wait: float = 0.15) -> None:
        for _ in range(60):
            t = self.flight._task
            if t is None or t.done():
                break
            await asyncio.sleep(wait / 6)
        await asyncio.sleep(0.02)


def roster_names() -> tuple[set[str], set[str]]:
    """The game's roster pools (Source/ASTRA/AstraCrewRoster.cpp): surnames and call signs the cast must not collide with."""
    src = (REPO / "Source" / "ASTRA" / "AstraCrewRoster.cpp").read_text(encoding="utf-8")

    def arr(name: str) -> set[str]:
        m = re.search(name + r"\[\] = \{(.*?)\};", src, re.S)
        return set(re.findall(r'TEXT\("([^"]+)"\)', m.group(1))) if m else set()
    return arr("LastNames"), arr("CallSigns")


class Classification(unittest.TestCase):
    def test_the_squadron_news_is_the_nets(self) -> None:
        for text, kind in ((AIRBORNE, "airborne"), (LOSS, "losses"), (TORPEDO, "torpedoes"), (RECOVERED, "recovered"), (SPLASH, "splash"),
                           ("flight: bravo squadron rearmed, 7 Hammers ready on the flight deck", "rearmed"),
                           ("flight: search and rescue at the wreck of the Brightwater: lifeboats found, 41 survivors picked up", "rescue")):
            k = fm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertEqual((k.name, k.take), (kind, True), text)

    def test_what_must_be_called_aloud(self) -> None:
        called = {fm.classify(t).name for t in (LOSS, TORPEDO, RECOVERED, "flight: bravo squadron rearmed, 7 Hammers ready on the flight deck") if fm.classify(t).call}
        self.assertEqual(called, {"losses", "torpedoes", "recovered", "rearmed"})
        for t in (AIRBORNE, SPLASH, WING, "flight: search and rescue at the wreck of the Brightwater: lifeboats found, 41 survivors picked up"):
            self.assertFalse(fm.classify(t).call, t)

    def test_what_belongs_to_price_and_the_xo_stays_with_them(self) -> None:
        for text in ("flight: launching Alpha on combat air patrol over the Aquila", "flight: the sky is quiet: recalling Alpha to rearm",
                     "flight: Falcon recon has identified T-21: Acheron-class cruiser, Cocytus",
                     "flight: controller call — the Captain is flying a Falcon", "flight: the Captain is off the catapult in a Falcon of Alpha, callsign Eagle — the XO has the conn",
                     "flight: Eagle has landed on New Ravenna, near Port Aurelius", "tactical: three missiles incoming", "sensors: Nair has a new contact",
                     "damage report: we've been hit — hull breach at deck 6 section B; shields 70%, hull 85%"):
            k = fm.classify(text)
            self.assertTrue(k is None or not k.take, text)

    def test_the_wings_news_is_the_nets_only_with_a_wing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            self.assertFalse(bed.flight.takes("flight: Eagle 2 splashed a Harpy"))
            self.assertTrue(bed.flight.takes(WING))
            self.assertFalse(bed.flight.on_event("flight: Eagle 2 splashed a Harpy"))        # no wing yet: the crew has it
            self.assertTrue(bed.flight.on_event(WING))
            self.assertTrue(bed.flight.wing)
            self.assertTrue(bed.flight.takes("flight: Eagle 2 splashed a Harpy"))
            self.assertTrue(bed.flight.on_event("flight: Eagle 2 splashed a Harpy"))

    def test_a_fire_on_the_flight_deck_wakes_the_net_and_stays_with_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            k = fm.classify("damage report: the unattended fire at deck 9 section C has spread to section D")
            self.assertEqual((k.name, k.take), ("deck", False))
            self.assertFalse(bed.flight.on_event("damage report: the unattended fire at deck 9 section C has spread to section D"))
            self.assertEqual(len(bed.flight._events), 1)

    def test_the_net_off_takes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.flight.disabled = True
            self.assertFalse(bed.flight.on_event(LOSS))
            self.assertFalse(bed.flight.takes(LOSS))
            self.assertEqual(bed.flight._events, [])


class Cast(unittest.TestCase):
    def test_everyone_has_a_voice_a_name_and_a_place_on_the_net(self) -> None:
        self.assertEqual(set(fm.CAST), {"cag", "alpha_lead", "alpha_2", "alpha_3", "bravo_lead", "bravo_2", "deck_chief"})
        voices = [p.voice for p in fm.CAST.values()]
        self.assertEqual(len(voices), len(set(voices)))                                # a voice for each of them
        for p in fm.CAST.values():
            self.assertIn(p.voice, VOICES, p.key)
            self.assertEqual(GENDER[p.voice], p.gender, p.key)                          # a woman has a woman's voice
            self.assertTrue(p.bio and p.post and p.radio and p.callsign)
        self.assertEqual(fm.CAST["cag"].callsign, "Hex")                                # the lore's CAG (docs/BIBBIA.md)
        self.assertEqual(fm.CAST["cag"].title, "Lieutenant Commander Ada Kovac")

    def test_no_name_collides_with_the_ships_roster(self) -> None:
        last, calls = roster_names()
        if not last:
            self.skipTest("the roster's source is not in this checkout")
        for p in fm.CAST.values():
            self.assertNotIn(p.name.split()[-1], last, p.name)                          # (the roster's 468 surnames: crew_locate must not find two of them)
            self.assertNotIn(p.callsign, calls, p.callsign)

    def test_who_may_order_a_squadron(self) -> None:
        self.assertTrue(fm.CAST["cag"].may_order("alpha") and fm.CAST["cag"].may_order("drones"))
        self.assertTrue(fm.CAST["alpha_lead"].may_order("alpha"))
        self.assertFalse(fm.CAST["alpha_lead"].may_order("bravo"))
        self.assertFalse(fm.CAST["alpha_2"].may_order("alpha"))
        self.assertFalse(fm.CAST["deck_chief"].may_order("alpha"))

    def test_the_wing_is_two_of_alphas_pilots(self) -> None:
        for k in fm.WING_KEYS:
            self.assertEqual(fm.CAST[k].squadron, "alpha")
            self.assertTrue(fm.CAST[k].wing.startswith("Eagle "))

    def test_the_voices_are_registered_for_the_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            self.assertEqual(bed.voices["cag"], ("CAG (Lieutenant Commander Ada Kovac)", "vera"))
            self.assertEqual(bed.voices["deck_chief"][0], "Chief of the Deck (Chief Petty Officer Hollis Teague)")
            import astra_mind.server as server                                          # and by the server's own table, before any Mind exists
            self.assertEqual(server.speaker_identity("alpha_lead"), ("Alpha Lead (Lieutenant Elias Calder)", "bill_boerst", False))


class Prompts(unittest.TestCase):
    def test_the_system_prompt_is_stable_and_complete(self) -> None:
        a, b = fm.system_prompt(), fm.system_prompt()
        self.assertEqual(a, b)
        for p in fm.CAST.values():
            self.assertIn(p.key, a)
            self.assertIn(p.callsign, a)
        for needle in ("Jonah Price", "flight net", "stay_quiet", "mission", "remember", "Eagle 2", "ONLY with tool calls"):
            self.assertIn(needle, a)
        self.assertNotIn("Italian", a)                                                   # the language rides with the user message: the cache survives a change of language

    def test_the_user_message_carries_what_the_people_may_know(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.flight.heard("Price (Flight Control)", "Alpha, pattuglia attorno all'Aquila.")
            bed.flight.on_event(LOSS)
            user = bed.flight._compose(ship_state(), bed.flight._events, [], ["news on the net (below)"], "it")
            for needle in ("Price (Flight Control): Alpha, pattuglia", "Anil Rao (call sign Wick) killed", "alpha: airborne: 6 Falcons airborne", "bravo: on deck, ready (7 Hammers)",
                           "4 Harpy strike fighters airborne", "T-21 Acheron (hostile, 24.0 km, hull 90%)", "T-02 ASN Vigilant (friendly", "the flight console: alpha: hold (by default)",
                           "delegation auto", "Italian", "Capitano"):
                self.assertIn(needle, user)
            self.assertNotIn("secret_plan", user)                                        # the Mandate's own view is nobody's here (docs/ARCHITETTURA.md §1bis, point 2)
            self.assertNotIn("flank the Aquila", user)
            self.assertNotIn("_mandate", user)

    def test_the_captains_words_and_the_language_are_in_the_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            msg = fm.Message(bed.clock.t - 2, "Alpha Lead, copri il Vigilant", "it")
            user = bed.flight._compose(ship_state(), [], [msg], ["the Captain is speaking to the net (below): answer him first"], "it")
            self.assertIn('THE CAPTAIN SAYS (over the net)', user)
            self.assertIn("Alpha Lead, copri il Vigilant", user)
            en = bed.flight._compose(ship_state(), [], [], ["x"], "en")
            self.assertIn("English", en)
            self.assertIn("two Falcons down", en)                                        # the register in the Captain's language

    def test_a_lost_squadron_has_no_pilots_on_the_net(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state(squadrons={"alpha": "lost: no aircraft left", "bravo": "on deck, ready (7 Hammers)", "drones": "ready (12 Wasps)"})
            who = bed.flight.present(st)
            self.assertEqual(set(who), {"cag", "bravo_lead", "bravo_2", "deck_chief"})
            self.assertIn("lost with their squadron", bed.flight._board(st))
            self.assertNotIn("lost with their squadron", bed.flight._board(ship_state()))

    def test_what_a_pilot_remembers_comes_back_to_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.flight._remember({"speaker": "alpha_lead", "kind": "loss", "memory": "Pilgrim lost Wick at the Acheron and the Captain called him by name afterwards."})
            user = bed.flight._compose(ship_state(), [], [], ["x"], "en")
            self.assertIn("WHAT THEY REMEMBER", user)
            self.assertIn("Pilgrim lost Wick", user)
            self.assertNotIn("WHAT THEY REMEMBER", Bed(tmp + "/other").flight._compose(ship_state(), [], [], ["x"], "en"))


class Pulses(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.f = self.bed.flight
        self.st = ship_state()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def news(self, *texts: str, wait_s: float = fm.SETTLE_S + 0.5) -> None:
        for t in texts:
            self.assertTrue(self.f.on_event(t), t)
        self.f.feed(self.st)
        self.bed.at(wait_s)
        self.f.feed(self.st)
        await self.bed.settle()

    # -- cadence
    async def test_a_burst_of_news_is_one_pulse_after_the_settle(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due Falcon a terra, Wick e Moth. Alpha tiene la pattuglia.", "tone": "grim"}))
        self.assertTrue(self.f.on_event(LOSS))
        self.assertTrue(self.f.on_event(SPLASH))
        self.f.feed(self.st)
        self.assertEqual(len(self.bed.llm.requests), 0)                                  # not yet: more of it may come
        self.bed.at(1.0)
        self.f.feed(self.st)
        self.assertEqual(len(self.bed.llm.requests), 0)
        self.bed.at(2.0)
        self.f.feed(self.st)                                                              # the burst is over
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)                                   # one call for both pieces of news
        user = self.bed.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("lost 2 Falcons", user)
        self.assertIn("3 Harpies splashed", user)
        self.assertEqual(self.f._events, [])

    async def test_news_waits_for_the_gap_between_pulses(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "nothing new"}))
        await self.news(AIRBORNE)
        self.assertEqual(len(self.bed.llm.requests), 1)
        await self.news(RECOVERED, wait_s=4.0)                                            # four seconds after the first pulse: too soon
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.assertEqual(len(self.f._events), 1)                                          # (kept, not lost)
        self.bed.at(fm.MIN_GAP_S)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)

    async def test_the_wings_news_does_not_wait_as_long(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "x"}))
        self.f.on_event(WING)
        await self.news("flight: Eagle 2 engaged a Harpy at 2.4 km")
        self.assertEqual(len(self.bed.llm.requests), 1)
        await self.news("flight: Eagle 3 splashed a Harpy", wait_s=fm.WING_GAP_S + 0.1)
        self.assertEqual(len(self.bed.llm.requests), 2)

    async def test_a_budget_spent_doubles_the_gap(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "x"}))
        for _ in range(3):
            self.f._spent.append((self.bed.clock.t, 0.02))                                # 0.06 $ in the last ten minutes: past the budget
        await self.news(AIRBORNE)
        self.assertEqual(len(self.bed.llm.requests), 1)
        await self.news(RECOVERED, wait_s=fm.MIN_GAP_S + 1.0)                             # the normal gap is not enough now
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.bed.at(fm.MIN_GAP_S)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)

    async def test_nothing_wakes_the_net_but_news_and_the_captain(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "x"}))
        for _ in range(30):
            self.bed.at(10.0)
            self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(self.bed.llm.requests, [])                                       # no clock, no periodic look

    # -- voices
    async def test_a_line_reaches_the_stage_with_its_speaker_and_priority(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due Falcon a terra, Wick e Moth. Alpha tiene la pattuglia, quattro in volo.", "tone": "grim"}),
                         ("say", {"speaker": "cag", "text": "Alpha, riportateli a casa.", "tone": "focused", "urgent": True}))
        await self.news(LOSS)
        self.assertEqual([(l["speaker"], l["tone"], l["urgent"], l["answer"], l["lang"]) for l in self.bed.lines],
                         [("alpha_lead", "grim", False, False, "it"), ("cag", "focused", True, False, "it")])
        self.assertIn("Alpha Lead: Due Falcon a terra", self.f._recall())                 # what was said is the net's log from then on
        self.assertIn("(news): flight: alpha squadron has lost 2 Falcons", self.f._recall())

    async def test_a_pulse_does_not_inherit_the_callers_voice_flags(self) -> None:
        """`feed` is called from the Captain's own turn (`captain_to_net`): the voice stage's per-task flags (an answer being given) must not follow into the pulse."""
        import contextvars
        flag = contextvars.ContextVar("flag", default="clean")
        seen: list[str] = []

        async def say(key: str, text: str, lang: str, tone: str, **kw: Any) -> None:
            seen.append(flag.get())
        self.f.say = say
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due a terra.", "tone": "grim"}))
        flag.set("the Captain's turn")
        self.f.on_event(LOSS)
        self.f.feed(self.st)
        self.bed.at(fm.SETTLE_S + 0.5)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(seen, ["clean"])

    async def test_silence_is_an_answer(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "the launch needs no voice"}))
        await self.news(AIRBORNE)
        self.assertEqual(self.bed.lines, [])
        self.assertEqual(self.f.stats["silent"], 1)
        self.assertIn("stayed quiet: the launch needs no voice", self.f._recall())

    async def test_news_that_is_called_aloud_leaves_no_way_to_stay_quiet(self) -> None:
        """A loss, a torpedo run, a recovery, a rearm, a wingman down: the look that holds one has no tool for silence (tool design, not a filter on the words); the
        other looks keep it."""
        def tools(i: int) -> set[str]:
            return {t["function"]["name"] for t in self.bed.llm.requests[i]["tools"]}
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due Falcon a terra.", "tone": "grim"}))
        await self.news(LOSS)
        self.assertEqual(tools(0), {"say", "mission", "remember"})
        user = self.bed.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("holds news that is called aloud", user)
        self.assertNotIn("call `stay_quiet`", user)
        for k, text in enumerate((TORPEDO, RECOVERED, "flight: bravo squadron rearmed, 7 Hammers ready on the flight deck"), start=1):
            self.bed.at(fm.MIN_GAP_S)
            await self.news(text)
            self.assertEqual(tools(k), {"say", "mission", "remember"}, text)
        self.bed.at(fm.MIN_GAP_S)
        await self.news(AIRBORNE)                                                         # a launch may go without a voice
        self.assertEqual(tools(4), {"say", "mission", "remember", "stay_quiet"})
        self.assertNotIn("holds news that is called aloud", self.bed.llm.requests[4]["messages"][-1]["content"])
        self.assertIn("call `stay_quiet`", self.bed.llm.requests[4]["messages"][-1]["content"])

    async def test_the_kills_are_called_on_the_bridge_and_left_to_the_wingman_with_a_wing(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Splash tre, ne resta uno.", "tone": "focused"}))
        await self.news(SPLASH)
        self.assertEqual({t["function"]["name"] for t in self.bed.llm.requests[0]["tools"]}, {"say", "mission", "remember"})        # nobody else could have called them
        self.bed.at(fm.MIN_GAP_S)
        await self.news(WING)                                                              # the wing checks in (called aloud: they say they are there)
        self.assertEqual({t["function"]["name"] for t in self.bed.llm.requests[1]["tools"]}, {"say", "mission", "remember"})
        self.bed.at(fm.MIN_GAP_S)
        await self.news(SPLASH)                                                            # in a cockpit the wingman's own "splash one" may have said it already
        self.assertIn("stay_quiet", {t["function"]["name"] for t in self.bed.llm.requests[2]["tools"]})

    async def test_a_wingman_down_is_called_and_the_wings_other_news_is_not(self) -> None:
        self.f.on_event(WING)
        self.bed.llm.say(("say", {"speaker": "alpha_3", "text": "Eagle 2 è a terra, la capsula è fuori.", "tone": "urgent"}))
        await self.news("flight: Eagle 2 is down — the pilot ejected, search and rescue is on the way")
        self.assertEqual({t["function"]["name"] for t in self.bed.llm.requests[0]["tools"]}, {"say", "mission", "remember"})
        await self.news("flight: Eagle 3 engaged a Harpy at 2.4 km", wait_s=fm.WING_GAP_S + 0.1)
        self.assertIn("stay_quiet", {t["function"]["name"] for t in self.bed.llm.requests[1]["tools"]})

    async def test_an_invented_tone_and_a_speaker_outside_the_cast_are_harmless(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Ricevuto.", "tone": "bubbly"}), ("say", {"speaker": "price", "text": "No.", "tone": "calm"}),
                         ("say", {"speaker": "cag", "text": "", "tone": "calm"}))
        await self.news(AIRBORNE)
        self.assertEqual([(l["speaker"], l["tone"]) for l in self.bed.lines], [("alpha_lead", "calm")])

    async def test_a_dead_squadrons_pilots_do_not_speak(self) -> None:
        self.st = ship_state(squadrons={"alpha": "lost: no aircraft left", "bravo": "on deck, ready (7 Hammers)", "drones": "ready (12 Wasps)"})
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Siamo ancora qui.", "tone": "calm"}), ("say", {"speaker": "cag", "text": "Alpha è perso, Capitano.", "tone": "grim"}))
        await self.news("flight: alpha squadron has lost 1 Falcon to enemy fire, 0 left")
        self.assertEqual([l["speaker"] for l in self.bed.lines], ["cag"])

    async def test_the_model_that_writes_instead_of_calling_is_asked_once(self) -> None:
        self.bed.llm.content = "Alpha Lead says two Falcons are down."
        self.bed.llm.replies = [[], [("say", {"speaker": "alpha_lead", "text": "Due Falcon a terra.", "tone": "grim"})]]
        await self.news(LOSS)
        self.assertEqual(len(self.bed.llm.requests), 2)
        again = self.bed.llm.requests[1]
        self.assertIn("was not said or done", again["messages"][-1]["content"])
        self.assertNotIn("stay_quiet", again["messages"][-1]["content"])                  # (news that is called aloud: no way out through silence)
        self.assertNotIn("stay_quiet", {t["function"]["name"] for t in again["tools"]})
        self.assertEqual([l["text"] for l in self.bed.lines], ["Due Falcon a terra."])

    async def test_the_model_that_writes_about_news_that_may_go_unsaid_may_still_stay_quiet(self) -> None:
        self.bed.llm.content = "Alpha is on patrol."
        self.bed.llm.replies = [[], [("stay_quiet", {"reason": "a launch"})]]
        await self.news(AIRBORNE)
        self.assertEqual(len(self.bed.llm.requests), 2)
        again = self.bed.llm.requests[1]
        self.assertIn("call stay_quiet", again["messages"][-1]["content"])
        self.assertIn("stay_quiet", {t["function"]["name"] for t in again["tools"]})
        self.assertEqual(self.bed.lines, [])

    async def test_a_model_with_nothing_to_write_or_call_is_silence_not_a_second_call(self) -> None:
        self.bed.llm.replies = [[]]
        await self.news(LOSS)
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.assertEqual(self.bed.lines, [])

    async def test_a_rethought_line_is_said_updated_or_dropped(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Quattro in volo, ora cinque.", "tone": "calm"}))
        self.f.state = self.st
        out = await self.f.rethink("alpha_lead", "Quattro in volo.", 20.0, "", "it")
        self.assertEqual(out, "Quattro in volo, ora cinque.")
        self.assertIn("20 seconds ago Alpha Lead was about to say", self.bed.llm.requests[0]["messages"][-1]["content"])
        self.bed.llm.replies = [[("stay_quiet", {"reason": "old news"})]]
        self.assertIsNone(await self.f.rethink("alpha_lead", "Quattro in volo.", 40.0, "", "it"))

    # -- the Captain
    async def test_the_captain_never_waits_and_is_answered_first(self) -> None:
        self.bed.llm.say(("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "escort", "target": "T-02", "reason": "cover the Vigilant"}),
                         ("say", {"speaker": "alpha_lead", "text": "Copiato: Alpha scorta il Vigilant.", "tone": "focused"}))
        self.f.captain_to_net("Alpha Lead, copri il Vigilant", "it")
        self.f.feed(self.st)                                                              # (kick fed the empty state: this is the next one a second later)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("alpha_lead", True)])      # a reply to the Captain: first on the voice stage
        user = self.bed.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("Alpha Lead, copri il Vigilant", user)
        self.assertIn("answer him first", user)

    async def test_the_captain_is_not_held_by_the_gap(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "x"}))
        await self.news(AIRBORNE)
        self.bed.llm.replies = [[("say", {"speaker": "cag", "text": "Bravo è pronto, Capitano.", "tone": "calm"})]]
        self.f.captain_to_net("CAG, come sta Bravo?", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)                                    # one second after a pulse: he is answered all the same
        self.assertEqual(self.bed.lines[-1]["speaker"], "cag")

    async def test_the_news_the_captain_interrupted_is_read_again(self) -> None:
        self.bed.llm.delay = 0.4
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due a terra.", "tone": "grim"}))
        self.f.on_event(LOSS)
        self.bed.at(3.0)
        self.f.feed(self.st)                                                               # the pulse on the loss is under way (the model is slow)
        await asyncio.sleep(0.05)
        self.assertEqual(self.f.preempt(), 1)                                              # the Captain speaks (to anyone): this pulse is dropped
        await asyncio.sleep(0.1)
        self.assertEqual([e.text for e in self.f._events], [LOSS])                         # ... and the news waits to be read again
        self.assertEqual(self.bed.lines, [])

    async def test_a_pulse_that_answers_the_captain_is_not_dropped(self) -> None:
        self.bed.llm.delay = 0.3
        self.bed.llm.say(("say", {"speaker": "cag", "text": "Sì, Capitano.", "tone": "calm"}))
        self.f.captain_to_net("CAG, mi senti?", "it")
        self.f.feed(self.st)
        await asyncio.sleep(0.05)
        self.assertEqual(self.f.preempt(), 0)
        await self.bed.settle(0.6)
        self.assertEqual([l["speaker"] for l in self.bed.lines], ["cag"])

    async def test_a_model_that_fails_hands_the_captains_words_to_the_bridge(self) -> None:
        self.bed.llm.error = "provider down"
        self.f.captain_to_net("Alpha Lead, rientra", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(self.bed.unanswered, [["Alpha Lead, rientra"]])
        self.assertEqual(self.bed.lines, [])

    async def test_a_model_that_stalls_hands_them_over_too(self) -> None:
        self.bed.llm.delay = 5.0
        old = fm.PULSE_TIMEOUT_S
        fm.PULSE_TIMEOUT_S = 0.2
        try:
            self.f.captain_to_net("Bravo Lead, attacca l'Acheron", "it")
            self.f.feed(self.st)
            await self.bed.settle(2.0)
        finally:
            fm.PULSE_TIMEOUT_S = old
        self.assertEqual(self.bed.unanswered, [["Bravo Lead, attacca l'Acheron"]])

    async def test_news_the_model_fails_on_is_lost_quietly(self) -> None:
        self.bed.llm.error = "provider down"
        await self.news(LOSS)
        self.assertEqual((self.bed.lines, self.bed.unanswered), ([], []))                  # (the boards still have it; nobody asked)
        self.assertEqual(self.f.pulses[-1]["error"], "provider down")

    # -- orders
    async def test_a_leader_orders_his_squadron_through_the_flight_console(self) -> None:
        self.bed.llm.say(("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "escort", "target": "T-02", "reason": "cover the Vigilant"}),
                         ("say", {"speaker": "alpha_lead", "text": "Alpha scorta il Vigilant.", "tone": "focused"}))
        self.f.captain_to_net("Alpha Lead, copri il Vigilant", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.commands), 1)
        name, args, by = self.bed.commands[0]
        self.assertEqual((name, by), ("station", "flight"))
        self.assertEqual(args, {"station": "flight", "aspect": "alpha", "mode": "escort", "until": "order", "params": {"squadron": "alpha", "target": "T-02"}, "by": "captain"})
        self.assertIn("Alpha Lead ordered alpha: escort on T-02 => ok", self.f._recall())
        self.assertEqual((self.f.pulses[-1]["ok"], self.f.pulses[-1]["failed"]), (1, 0))

    async def test_a_leader_cannot_order_another_squadron_but_the_cag_can(self) -> None:
        self.bed.llm.say(("mission", {"by": "alpha_lead", "squadron": "bravo", "type": "strike", "target": "T-21"}), ("say", {"speaker": "alpha_lead", "text": "Non sono io.", "tone": "dry"}))
        self.f.captain_to_net("Bravo, attacco sull'Acheron", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(self.bed.commands, [])                                            # refused here: nothing went to the game
        self.assertIn("cannot order bravo", self.f._recall())
        self.bed.at(1.0)
        self.bed.llm.replies = [[("mission", {"by": "cag", "squadron": "bravo", "type": "strike", "target": "T-21"}),
                                 ("say", {"speaker": "cag", "text": "Bravo, attacco sull'Acheron.", "tone": "focused"})]]
        self.f.captain_to_net("CAG, Bravo attacchi l'Acheron", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual([(c[1]["aspect"], c[1]["mode"], c[1]["params"].get("target")) for c in self.bed.commands], [("bravo", "strike", "T-21")])

    async def test_nobody_else_gives_orders_to_a_squadron(self) -> None:
        self.bed.llm.say(("mission", {"by": "alpha_2", "squadron": "alpha", "type": "recall"}))
        self.f.captain_to_net("Alpha 2, rientrate", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual([c for c in self.bed.commands], [])

    async def test_on_their_own_the_consoles_delegation_decides(self) -> None:
        self.st["stations"]["flight"]["delegation"] = "manual"
        self.bed.llm.say(("mission", {"by": "cag", "squadron": "alpha", "type": "recall", "reason": "mauled"}), ("stay_quiet", {"reason": "x"}))
        await self.news(LOSS)
        self.assertEqual(self.bed.commands, [])                                            # manual: only on the Captain's orders
        self.assertIn("flight is on manual", self.f._recall())
        self.bed.at(fm.MIN_GAP_S)
        self.st["stations"]["flight"]["delegation"] = "auto"
        self.bed.llm.replies = [[("mission", {"by": "cag", "squadron": "alpha", "type": "recall", "reason": "mauled"})]]
        await self.news(RECOVERED, wait_s=fm.SETTLE_S + 0.5)
        self.assertEqual(len(self.bed.commands), 1)
        self.assertEqual(self.bed.commands[0][1]["by"], "officer")                         # on their own: the console records it as an officer's, not the Captain's

    async def test_a_standing_order_lets_them_act(self) -> None:
        self.tmp2 = tempfile.TemporaryDirectory()
        bed = Bed(self.tmp2.name, standing={"flight"})
        self.st["stations"]["flight"]["delegation"] = "advise"
        bed.llm.say(("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "cap"}))
        bed.flight.on_event(AIRBORNE)
        bed.flight.feed(self.st)
        bed.at(3.0)
        bed.flight.feed(self.st)
        await bed.settle()
        self.assertEqual(len(bed.commands), 1)
        self.tmp2.cleanup()

    async def test_an_order_the_game_refuses_is_read_by_the_one_who_gave_it(self) -> None:
        self.bed.result = {"ok": False, "detail": "mission escort needs a live contact (got 'T-77')"}
        self.bed.llm.replies = [[("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "escort", "target": "T-77"}),
                                 ("say", {"speaker": "alpha_lead", "text": "Scorto il T-77.", "tone": "focused"})],
                                [("say", {"speaker": "alpha_lead", "text": "Capitano, il T-77 non è sul piano: scorto il Vigilant?", "tone": "calm"})]]
        self.f.captain_to_net("Alpha, scorta il T-77", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)                                    # one correction, no more
        second = self.bed.llm.requests[1]["messages"]
        self.assertTrue(any(m.get("role") == "tool" and "needs a live contact" in m["content"] for m in second))
        self.assertEqual({t["function"]["name"] for t in self.bed.llm.requests[1]["tools"]}, {"say", "mission", "stay_quiet"})
        self.assertEqual([l["text"] for l in self.bed.lines], ["Capitano, il T-77 non è sul piano: scorto il Vigilant?"])    # the line composed before the answer ("Scorto il T-77") is never said
        self.assertEqual(self.f.pulses[-1]["failed"], 1)
        self.assertEqual(self.f.pulses[-1]["held"], 1)

    async def test_a_captain_who_gave_an_order_and_heard_nothing_is_answered(self) -> None:
        """The order went through and nobody said a word: he spoke to the net, the net answers (once more asked, with what the console said)."""
        self.bed.llm.replies = [[("mission", {"by": "bravo_lead", "squadron": "bravo", "type": "strike", "target": "T-21"})],
                                [("say", {"speaker": "bravo_lead", "text": "Bravo va sull'Acheron, Capitano.", "tone": "focused"})]]
        self.f.captain_to_net("Bravo Lead, attacca l'Acheron", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        second = self.bed.llm.requests[1]
        self.assertIn("has not heard a voice answer him", second["messages"][-1]["content"])
        self.assertIn("What has been done so far", second["messages"][-1]["content"])
        self.assertIn('"squadron": "bravo", "type": "strike"', second["messages"][-1]["content"])           # what the console did, in the one who gave it
        self.assertIn(" ok: ", second["messages"][-1]["content"])
        self.assertEqual({t["function"]["name"] for t in second["tools"]}, {"say", "mission", "stay_quiet"})
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("bravo_lead", True)])
        self.assertEqual(len(self.bed.commands), 1)                                        # (the order is not given twice)

    async def test_a_refused_order_corrected_without_a_word_still_gets_its_answer(self) -> None:
        self.bed.llm.replies = [[("mission", {"by": "alpha_lead", "squadron": "bravo", "type": "strike", "target": "T-21"})],           # (not his squadron: refused)
                                [("mission", {"by": "cag", "squadron": "bravo", "type": "strike", "target": "T-21"})],                  # the correction, and no word
                                [("say", {"speaker": "cag", "text": "Bravo in attacco sull'Acheron, Capitano.", "tone": "focused"})]]
        self.f.captain_to_net("Bravo, attacco sull'Acheron", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 3)
        last = self.bed.llm.requests[2]["messages"][-1]["content"]
        self.assertIn("cannot order bravo", last)
        self.assertIn(" ok: ", last)
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("cag", True)])
        self.assertEqual([(c[1]["aspect"], c[1]["mode"]) for c in self.bed.commands], [("bravo", "strike")])

    async def test_a_captain_the_net_chose_not_to_answer_is_not_asked_about_again(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "his words are for Price"}))
        self.f.captain_to_net("Timoniere, rotta zero-nove-zero", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.assertEqual(self.bed.lines, [])

    async def test_a_model_that_says_nothing_to_the_captain_is_asked_once_more(self) -> None:
        self.bed.llm.replies = [[], [("say", {"speaker": "cag", "text": "CAG in ascolto, Capitano.", "tone": "calm"})]]
        self.f.captain_to_net("CAG, mi senti?", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.assertEqual([l["speaker"] for l in self.bed.lines], ["cag"])
        self.assertNotIn("tool", [m.get("role") for m in self.bed.llm.requests[1]["messages"]])      # (nothing was called: nothing to show of it)
        self.bed.llm.replies = [[]]
        self.bed.at(1.0)
        self.f.captain_to_net("CAG?", "it")
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 4)                                      # asked once more, not forever

    async def test_the_console_that_does_not_answer_is_a_failed_order_not_a_hang(self) -> None:
        async def hang(name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
            await asyncio.sleep(30)
            return {"ok": True, "detail": ""}
        self.f.execute = hang
        self.bed.llm.replies = [[("mission", {"by": "cag", "squadron": "alpha", "type": "recall"})], [("say", {"speaker": "cag", "text": "Non risponde.", "tone": "calm"})]]
        self.f.captain_to_net("CAG, richiama Alpha", "it")
        self.f.feed(self.st)
        await self.bed.settle(8.0)
        self.assertIn("no response from the flight console", self.f._recall())

    # -- the wing
    async def test_the_wing_renames_its_pilots_while_it_flies(self) -> None:
        self.assertEqual(self.f.radio("alpha_2"), "Alpha 2")
        self.f.on_event(WING)
        self.assertEqual((self.f.radio("alpha_2"), self.f.radio("alpha_3")), ("Eagle 2", "Eagle 3"))
        self.assertEqual(self.bed.voices["alpha_2"][0], "Eagle 2 (Ensign Mina Takeda)")    # the stage's subtitle follows
        self.assertIn("Eagle's wing is up", self.f._board(self.st))
        self.bed.llm.say(("stay_quiet", {"reason": "x"}))
        self.f.on_event("flight: Eagle recovered through the port tube, the Captain is back aboard")
        self.assertTrue(self.f.wing)                                                       # (read first: the wing says its word as Eagle 2 and 3)
        self.f.feed(self.st)
        self.bed.at(fm.SETTLE_S + 0.5)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertFalse(self.f.wing)
        self.assertEqual(self.f.radio("alpha_2"), "Alpha 2")
        self.assertEqual(self.bed.voices["alpha_2"][0], "Alpha 2 (Ensign Mina Takeda)")

    async def test_the_wing_dissolves_when_the_captain_is_no_longer_in_a_falcon(self) -> None:
        self.st = ship_state(captain=FLYING)
        self.f.feed(self.st)
        self.f.on_event(WING)
        self.assertTrue(self.f.wing)
        self.f.feed(ship_state(captain="on the bridge"))
        self.assertFalse(self.f.wing)

    async def test_a_wingman_shot_down_is_off_the_net_until_the_flight_is_over(self) -> None:
        self.f.on_event(WING)
        self.assertTrue(self.f.on_event("flight: Eagle 2 is down — the pilot ejected, search and rescue is on the way"))
        self.assertNotIn("alpha_2", self.f.present(self.st))
        self.assertIn("alpha_3", self.f.present(self.st))
        self.assertIn("shot down on Eagle's wing", self.f._board(self.st))
        self.assertIn("Eagle 2", self.f._board(self.st))
        self.bed.llm.say(("say", {"speaker": "alpha_2", "text": "Sono ancora qui.", "tone": "calm"}), ("say", {"speaker": "alpha_3", "text": "Eagle 2 è giù, vedo il paracadute.", "tone": "urgent"}))
        self.f.feed(self.st)
        self.bed.at(fm.SETTLE_S + 0.5)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual([l["speaker"] for l in self.bed.lines], ["alpha_3"])               # the one who ejected does not speak
        self.f._wing_off()
        self.assertIn("alpha_2", self.f.present(self.st))

    async def test_eagles_news_wakes_the_wing_and_stays_with_price(self) -> None:
        self.bed.llm.say(("say", {"speaker": "alpha_2", "text": "Eagle è a terra! Vedo un paracadute!", "tone": "urgent", "urgent": True}))
        self.st = ship_state(captain="the Captain ejected from a destroyed Falcon; the pod is being recovered")
        self.f.on_event(WING)
        self.assertFalse(self.f.on_event("flight: Eagle is down — the Captain's Falcon was destroyed, the Captain ejected; a Wasp is going out for the pod"))   # (Price has it too)
        self.assertEqual(len(self.f._events), 2)
        self.assertTrue(self.f.wing)                                                       # the wing still speaks as Eagle 2 and 3 for this one look ...
        self.f.feed(self.st)
        self.bed.at(fm.SETTLE_S + 0.5)
        self.f.feed(self.st)
        await self.bed.settle()
        self.assertEqual([(l["speaker"], l["urgent"]) for l in self.bed.lines], [("alpha_2", True)])
        self.assertIn("Eagle 2", self.bed.llm.requests[0]["messages"][-1]["content"])
        self.assertFalse(self.f.wing)                                                      # ... and then the wing is over

    # -- memory
    async def test_what_is_kept_is_kept_with_the_campaign(self) -> None:
        self.bed.llm.say(("remember", {"speaker": "alpha_lead", "kind": "loss", "memory": "Pilgrim lost Wick to the Harpies; the Captain asked his name afterwards."}),
                         ("say", {"speaker": "alpha_lead", "text": "Wick, Capitano. Anil Rao.", "tone": "grim"}))
        await self.news(LOSS)
        saved = json.loads((Path(self.tmp.name) / "flight.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["memories"]["alpha_lead"][0]["kind"], "loss")
        other = Bed(self.tmp.name).flight                                                  # a new session of the same campaign
        self.assertTrue(other.load())
        self.assertIn("Pilgrim lost Wick", other.memories["alpha_lead"][0]["memory"])
        other.new_campaign()
        self.assertEqual(other.memories, {})
        self.assertEqual(json.loads((Path(self.tmp.name) / "flight.json").read_text(encoding="utf-8"))["memories"], {})

    async def test_memories_are_for_the_cast_only_and_not_repeated(self) -> None:
        self.f._remember({"speaker": "price", "kind": "moment", "memory": "Price was sad."})
        self.f._remember({"speaker": "cag", "kind": "moment", "memory": "Hex counted her pilots."})
        self.f._remember({"speaker": "cag", "kind": "moment", "memory": "hex counted her pilots."})
        self.assertEqual(list(self.f.memories), ["cag"])
        self.assertEqual(len(self.f.memories["cag"]), 1)

    # -- the session
    async def test_a_new_session_starts_quiet_and_a_cancelled_pulse_leaves_nothing_behind(self) -> None:
        self.bed.llm.delay = 0.5
        self.bed.llm.say(("say", {"speaker": "alpha_lead", "text": "Due a terra.", "tone": "grim"}))
        self.f.on_event(LOSS)
        self.bed.at(3.0)
        self.f.feed(self.st)
        await asyncio.sleep(0.05)
        self.f.net_open = True
        self.f.reset()
        await asyncio.sleep(0.2)
        self.assertEqual((self.f._events, self.f._inbox, self.f.net_open, list(self.f.log)), ([], [], False, []))
        self.assertEqual(self.bed.lines, [])

    async def test_the_net_opens_closes_and_is_live_where_the_captain_is(self) -> None:
        self.assertFalse(self.f.net_live(ship_state()))
        res = self.f.open_net()
        self.assertTrue(res["ok"])
        self.assertIn("CAG", res["detail"])
        self.assertTrue(self.f.net_live(ship_state()))
        self.assertTrue(self.f.close_net())
        self.assertFalse(self.f.net_live(ship_state()))
        self.assertTrue(self.f.net_live(ship_state(captain=FLYING)))                       # in a cockpit the radio is the net
        self.assertTrue(self.f.net_live(ship_state(captain="on the flight deck")))         # on the deck the Chief is there
        self.assertTrue(self.f.net_live(ship_state(), heard_ago=8.0))                      # somebody on it called him a moment ago
        self.assertFalse(self.f.net_live(ship_state(), heard_ago=60.0))
        self.f.disabled = True
        self.assertFalse(self.f.net_live(ship_state(captain=FLYING)))

    async def test_the_measures(self) -> None:
        self.bed.llm.say(("say", {"speaker": "deck_chief", "text": "Alpha a bordo, sei su otto.", "tone": "calm"}))
        await self.news(RECOVERED)
        s = self.f.summary()
        self.assertEqual((s["pulses"], s["lines"], s["errors"]), (1, 1, 0))
        self.assertAlmostEqual(s["cost"], 0.0004)
        self.assertEqual(s["tokens_in"], 2500)


class StationsAreUntouched(unittest.TestCase):
    def test_the_mission_wire_is_what_the_game_already_takes(self) -> None:
        """The net sends the flight console's own command: the same one the crew's `station` tool makes for Price (stations.to_wire)."""
        cmd, err = station_model.normalize({"station": "flight", "mode": "mission", "params": {"squadron": "bravo", "type": "strike", "target": "T-21"}})
        self.assertEqual(err, "")
        wire = station_model.to_wire(cmd, by="captain")
        self.assertEqual(wire, {"station": "flight", "aspect": "bravo", "mode": "strike", "until": "order", "params": {"squadron": "bravo", "target": "T-21"}, "by": "captain"})


if __name__ == "__main__":
    unittest.main()
