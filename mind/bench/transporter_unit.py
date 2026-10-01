"""Offline tests of the Transporter Room's Chief (astra_mind/transporter.py) and of how she joins the ship (tools, crew rules, context, server), against a scripted model:
no network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.transporter_unit -v

What is checked is the plumbing the behaviour stands on, not the model's judgement (whether her words are in character, in the Captain's language, never invent a number
is for the real model, by ear and by bench/transporter_live.py): that an order the bridge relays is handed to her at once and that she acts with the console's own commands;
that a refusal is read back to her and told to the Captain, and that it stands (the console never overrides a Chief who said no); that a model that fails or stalls leaves the
bridge's order to the console, as typed, and the bridge is told; that the Captain's words in her room are hers to judge and the bridge's gate follows her verdict; that the room's
news is read together after a moment, danger (as the world marks it) first, within a budget, and is cut off when the Captain speaks unless it is the answer to him; that what she
and the Captain said is remembered; and that the bridge's relay tool, the crew's rule, the one-line view of the room and the speaker's identity are in place."""
from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from astra_mind import context as context_mod
from astra_mind import crew, models, server, tools, transporter
from astra_mind.openrouter import Completion, ToolCall

models.LEDGER.write_file = False
FIXTURES = Path(__file__).parent / "fixtures" / "transporter"

CARD = {
    "room": {"state": "ready", "power_pct": 100, "wreck_pct": 0, "reach_km": 30000, "cycle_s": 8, "energy_mw_for_one": 40, "pads": 6,
             "emergency_pads": "ready, reach 400 km", "reactor": "on"},
    "on_pads": [],
    "aquila": {"shields": "up", "face_charge_pct": {"bow": 100, "stern": 100, "port": 100, "starboard": 100, "dorsal": 100, "ventral": 100},
               "accel_mps2": 0, "turn_deg_s": 0, "in_gate_lane": False, "sensors_power_pct": 100},
    "transports": [],
    "away": [],
    "options": [
        {"to": "surface", "place": "New Ravenna · Port Aurelius Field", "answer": "cannot be done now", "range_km": 1200, "lock_s": 5.7, "lock_quality_pct": 100,
         "in_the_way": ["our shields are up on the ventral face, the one the beam leaves through (100%)"],
         "what_clears_it": "a shield window (Tactical holds our shields down for the cycle) clears it"},
        {"to": "T-02", "place": "ASN Vigilant (allied), 3 km", "answer": "can be done now", "range_km": 3, "lock_s": 3.5, "lock_quality_pct": 100},
    ],
    "aboard": "any room of the Aquila, from where they stand: about 1.5 s of lock, no shield matters",
}
STATE = {"captain": "in the Transporter Room (Deck 5)", "location": "Aurelia System, home of the 7th Fleet", "alert": "green", "hull_pct": 100,
         "shields": {"strength_pct": 100, "state": "up"}, "heading_deg": 90, "speed_mps": 0, "power_pct": {"sensors": 100},
         "contacts": [{"id": "T-02", "name": "ASN Vigilant (CVC-02)", "status": "friendly", "range_km": 3.1}],
         "surface": {"world": "New Ravenna", "kind": "ocean world", "field": "Port Aurelius Field", "captain_here": False}, "transporter": CARD}


class FakeVoice:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str, str, dict[str, Any]]] = []

    async def __call__(self, speaker: str, text: str, lang: str, tone: str, **kw: Any) -> int:
        self.lines.append((speaker, text, lang, tone, kw))
        return len(self.lines)


class FakeLLM:
    """A model that answers each request with the next script in the queue (a list of (tool name, arguments)); an empty queue answers with nothing."""

    def __init__(self) -> None:
        self.queue: list[list[tuple[str, dict[str, Any]]]] = []
        self.requests: list[dict[str, Any]] = []
        self.error = ""
        self.delay = 0.0

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3,
                   extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools, max_tokens=max_tokens))
        out = Completion(model=model, provider="fake", cost=0.0003)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            out.error = self.error
            return out
        script = self.queue.pop(0) if self.queue else []
        for i, (name, args) in enumerate(script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out

    async def close(self) -> None:
        pass

    def user_of(self, i: int = 0) -> str:
        return str(self.requests[i]["messages"][-1]["content"])


class Room:
    """A Chief at her console with a scripted model, a voice that records, and a game that answers the commands."""

    def __init__(self, tmp: str, state: dict[str, Any] | None = None) -> None:
        self.llm = FakeLLM()
        self.voice = FakeVoice()
        self.state = state if state is not None else STATE
        self.calls: list[tuple[str, dict[str, Any], str]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.relayed: list[str] = []
        self.now = 1000.0
        self.traces: list[dict[str, Any]] = []
        self.chief = transporter.TransporterRoom(self.llm, self.voice, self.execute, state=lambda: self.state, lang=lambda: "en", clock=lambda: self.now,
                                                 store=Path(tmp) / "journal.json", relay=self.relay)
        self.chief.trace = self.traces.append

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.calls.append((name, args, by))
        return self.results.get(name, {"ok": True, "detail": f"{name} accepted"})

    async def relay(self, text: str) -> None:
        self.relayed.append(text)

    async def settle(self) -> None:
        """Lets every task the Chief started run to its end."""
        for _ in range(60):
            await asyncio.sleep(0)
            pending = [t for t in list(self.chief._tasks) + ([self.chief._task] if self.chief._task else []) if t is not None and not t.done()]
            if not pending:
                return
            await asyncio.gather(*pending, return_exceptions=True)


class NewsAndBrief(unittest.TestCase):
    def test_the_rooms_news_is_told_with_its_own_prefix(self) -> None:
        self.assertTrue(transporter.is_news("transporter: X3 done: the Captain is at pad 1"))
        self.assertTrue(transporter.is_news("  Transporter: X3 done"))
        self.assertFalse(transporter.is_news("flight: Alpha Lead is down"))
        self.assertFalse(transporter.is_news(""))

    def test_the_world_marks_danger_the_code_does_not_guess_it(self) -> None:
        body, urgent = transporter.split_news("transporter: URGENT: X3: the lock is lost with the Captain in the buffer")
        self.assertTrue(urgent)
        self.assertTrue(body.startswith("X3: the lock is lost"))
        body, urgent = transporter.split_news("transporter: X3 done: the Captain is at pad 1 (the lock lost nothing, nobody was in the buffer)")
        self.assertFalse(urgent)                                              # the words 'lost' and 'buffer' do not make it danger: only the world's mark does
        self.assertIn("lost nothing", body)

    def test_the_bridge_sees_the_room_in_a_line(self) -> None:
        card = json.loads(json.dumps(CARD))
        card["transports"] = [{"id": "X3", "who": "the Captain", "to": "pad 2", "state": "locking"}, {"id": "X2", "who": "Lt Sato", "to": "surface", "state": "done"}]
        card["away"] = [{"who": f"Private {n} (npc{n})", "where": "on the surface of New Ravenna, at Port Aurelius Field", "since_s": 40} for n in range(6)]
        card["last"] = "X2 done: Lt Sato is at New Ravenna"
        line = transporter.brief(card)
        self.assertIn("room ready (100% power, reach 30000 km)", line)
        self.assertIn("X3 the Captain to pad 2 (locking)", line)
        self.assertNotIn("X2 Lt Sato", line)                                  # a finished transport is not under way
        self.assertIn("and 2 more", line)                                     # six away: four named
        self.assertIn("last: X2 done", line)
        self.assertEqual(transporter.brief(None), "the Transporter Room does not answer")

    def test_the_bridges_telemetry_carries_the_line_not_the_console(self) -> None:
        text = crew.bridge_now(STATE, ["comms: nothing"], "")
        self.assertIn("room ready", text)
        self.assertNotIn("energy_mw_for_one", text)                           # the whole card is the Chief's
        self.assertNotIn("face_charge_pct", text)


class WhatSheReads(unittest.TestCase):
    def test_the_prompt_is_hers_and_in_the_captains_language(self) -> None:
        for lang, word in (("en", "Captain"), ("it", "Capitano"), ("de", "Kapitän")):
            p = transporter.system_prompt(lang)
            self.assertIn("Rhea Ostrander", p)
            self.assertIn(word, p)
            self.assertIn({"en": "English", "it": "Italian", "de": "German"}[lang], p)
        p = transporter.system_prompt("en")
        self.assertIn("`options`", p)                                         # she is told to read the card before she acts
        self.assertIn("Never invent", p)

    def test_the_board_shows_the_plot_the_captain_and_her_console(self) -> None:
        text = transporter.board(STATE)
        self.assertIn("Where the Captain is: in the Transporter Room", text)
        self.assertIn("T-02", text)
        self.assertIn("YOUR CONSOLE", text)
        self.assertIn("\"shields\":\"up\"", text)
        self.assertIn("the Captain is aboard", text)
        self.assertIn("the console is not answering", transporter.board({"captain": "on the bridge"}))

    def test_her_tools(self) -> None:
        names = [t["function"]["name"] for t in (transporter.SAY, transporter.TRANSPORT, transporter.ENERGIZE, transporter.ABORT, transporter.LOCATE, transporter.PASS)]
        self.assertEqual(names, ["say", "transport", "energize", "abort", "locate", "pass"])
        self.assertEqual(transporter.ACTION_TOOLS, {"transport": "transport", "energize": "transport_energize", "abort": "transport_abort"})
        self.assertEqual(transporter.TRANSPORT["function"]["parameters"]["required"], ["who", "to"])


class Turns(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Room(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_an_order_from_the_bridge_is_handed_over_at_once_and_acted_on(self) -> None:
        r = self.r
        r.llm.queue = [[("transport", {"who": ["captain"], "to": "surface", "shield_window": True}),
                        ("say", {"text": "Pad lock in five seconds, Captain. Shields down for the cycle; I'm energizing now.", "tone": "focused"})]]
        res = await r.chief.order({"action": "beam", "who": ["captain"], "to": "surface"}, "ops")
        self.assertTrue(res["ok"])
        self.assertIn("Chief Ostrander", res["detail"])                       # the officer is told only that she has it
        await r.settle()
        self.assertEqual(len(r.calls), 1)
        name, args, by = r.calls[0]
        self.assertEqual((name, by), ("transport", "chief"))
        self.assertEqual(args["who"], ["captain"])
        self.assertEqual(args["by"], "chief")                                 # the console's log says who gave the order
        self.assertTrue(args["shield_window"])
        speaker, text, lang, tone, kw = r.voice.lines[0]
        self.assertEqual((speaker, lang), ("xfer_chief", "en"))
        self.assertTrue(kw.get("answer"))                                     # she answers the Captain's order: first in the voice's queue
        self.assertEqual(r.chief.journal.record["sent"], 1)
        self.assertEqual(r.chief.journal.record["captain"], 1)
        self.assertEqual(len(r.llm.requests), 1)                              # nothing was refused: one call, no second look
        self.assertIn("relays over the intercom, with the Captain's authority", r.llm.user_of())
        self.assertIn("Lieutenant Tanaka (Operations)", r.llm.user_of())
        self.assertIn("YOUR CONSOLE", r.llm.user_of())                        # she read the card before she acted

    async def test_she_answers_in_the_captains_language_the_bridge_heard(self) -> None:
        r = self.r
        r.chief.captain_said("portami giù sul pianeta", "it")
        r.llm.queue = [[("say", {"text": "Subito, Capitano.", "tone": "calm"})]]
        await r.chief.order({"action": "ask", "question": "can we reach the surface?"}, "xo")
        await r.settle()
        self.assertEqual(r.voice.lines[0][2], "it")
        self.assertIn("portami giù sul pianeta", r.llm.user_of())             # the Captain's own words go with the relay

    async def test_a_refusal_is_read_back_and_told_straight(self) -> None:
        r = self.r
        r.results["transport"] = {"ok": False, "detail": "refused: [shields_own] our shields are up on the ventral face, the one the beam leaves through (100%) (to clear it: a shield window)"}
        r.llm.queue = [[("transport", {"who": ["captain"], "to": "surface"}), ("say", {"text": "Sending you down now.", "tone": "calm"})],
                       [("say", {"text": "Can't, Captain: our shields are up on the ventral face. A shield window clears it, on your word.", "tone": "dry"})]]
        await r.chief.order({"action": "beam", "who": ["captain"], "to": "surface"}, "ops")
        await r.settle()
        self.assertEqual(len(r.llm.requests), 2)
        follow = r.llm.user_of(1)
        self.assertIn("[Console results]", follow)
        self.assertIn("REFUSED", follow)
        self.assertIn("shields_own", follow)
        self.assertIn("if what you said before was not true, put it right", follow)
        self.assertEqual([l[1] for l in r.voice.lines][-1].startswith("Can't, Captain"), True)
        self.assertEqual(r.chief.journal.record["refused"], 1)
        self.assertEqual(len(r.calls), 1)                                     # the console did not carry it out behind her back

    async def test_a_chief_who_failed_leaves_the_order_to_the_console_and_the_bridge_is_told(self) -> None:
        r = self.r
        r.llm.error = "the model is down"
        await r.chief.order({"action": "beam", "who": ["Lieutenant Sato"], "to": "Main Engineering"}, "xo")
        await r.settle()
        self.assertEqual([c[0] for c in r.calls], ["transport"])
        name, args, by = r.calls[0]
        self.assertEqual(by, "xo")
        self.assertEqual(args["who"], ["Lieutenant Sato"])
        self.assertNotIn("action", args)                                      # the console's own command, as typed on the bridge
        self.assertEqual(len(r.relayed), 1)
        self.assertIn("carried out the bridge's order by itself", r.relayed[0])
        self.assertEqual(r.chief.stats["fallbacks"], 1)

    async def test_a_chief_who_said_no_is_not_overridden(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "Not with the Gate this close, Captain. Twenty kilometres more and I'll have them across.", "tone": "dry"})]]
        await r.chief.order({"action": "beam", "who": ["captain"], "to": "T-02"}, "ops")
        await r.settle()
        self.assertEqual(r.calls, [])                                         # a refusal is a decision of hers: it stands
        self.assertEqual(r.relayed, [])
        self.assertEqual(len(r.voice.lines), 1)

    async def test_she_looks_a_person_up_and_reads_what_the_locator_found(self) -> None:
        r = self.r
        r.results["crew_locate"] = {"ok": True, "detail": "Lieutenant Tomasz Sato (weapons) is in Deck 8, Kit Room."}
        r.llm.queue = [[("locate", {"who": "Sato"})], [("say", {"text": "Lieutenant Sato is in the Kit Room on Deck 8.", "tone": "calm"})]]
        await r.chief.order({"action": "ask", "question": "where is Sato?"}, "ops")
        await r.settle()
        self.assertEqual(r.calls, [("crew_locate", {"who": "Sato"}, "chief")])
        self.assertIn("Kit Room", r.llm.user_of(1))                           # what the lookup found came back to her
        self.assertEqual(r.voice.lines[-1][1], "Lieutenant Sato is in the Kit Room on Deck 8.")

    async def test_the_captain_in_her_room_is_hers_to_answer(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "Pad two is clear. Where to, Captain?", "tone": "calm"})]]
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        spoke = await r.chief.hear("Chief, ho bisogno di scendere sul pianeta", "it", gate, "in the Transporter Room")
        self.assertEqual(spoke, ["Pad two is clear. Where to, Captain?"])
        self.assertFalse(gate.result())                                       # she answered: the bridge's officers stay out
        self.assertTrue(r.voice.lines[0][4].get("answer"))
        self.assertIn("The Captain is in the Transporter Room, face to face", r.llm.user_of())
        self.assertIn("Chief, ho bisogno di scendere", r.llm.user_of())
        tools_sent = [t["function"]["name"] for t in r.llm.requests[0]["tools"]]
        self.assertIn("pass", tools_sent)                                     # "not for me" is a call of its own, offered only when the Captain spoke

    async def test_words_for_the_bridge_are_passed_and_the_gate_opens(self) -> None:
        r = self.r
        r.llm.queue = [[("pass", {"for_whom": "the XO"})]]
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        spoke = await r.chief.hear("XO, status report", "en", gate)
        self.assertEqual(spoke, [])
        self.assertTrue(gate.result())
        self.assertEqual(r.voice.lines, [])
        self.assertEqual(len(r.chief.journal.talk), 0)                        # and nothing is remembered as said

    async def test_a_chief_who_does_not_answer_in_time_leaves_the_words_to_the_bridge(self) -> None:
        r = self.r
        r.llm.delay = 8.0
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        with self.assertLogs("astra.transporter", level="WARNING"):
            spoke = await r.chief.hear("Chief, one to beam up", "en", gate)
        self.assertEqual(spoke, [])
        self.assertTrue(gate.result())

    async def test_what_was_said_is_remembered_between_conversations(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "Aye, Captain: pad three.", "tone": "calm"})]]
        await r.chief.hear("Chief, use pad three for my people", "en", None)
        again = Room(self.tmp.name)                                           # the next session, the same journal
        self.assertEqual(len(again.chief.journal.talk), 1)
        words, said, _when = again.chief.journal.talk[0]
        self.assertIn("pad three", words)
        self.assertIn("Aye, Captain", said)
        again.llm.queue = [[("say", {"text": "Pad three, as before.", "tone": "calm"})]]
        await again.chief.hear("same as before", "en", None)
        self.assertIn("Chief, use pad three for my people", again.llm.user_of())    # she reads what they said last
        again.chief.new_campaign()
        self.assertEqual(len(again.chief.journal.talk), 0)                    # a new campaign forgets

    async def test_her_record_is_kept(self) -> None:
        r = self.r
        r.results["transport_abort"] = {"ok": True, "detail": "X1 cancelled"}
        r.llm.queue = [[("transport", {"who": ["captain"], "to": "pad 2"}), ("say", {"text": "Pad two.", "tone": "calm"})],
                       [("abort", {}), ("say", {"text": "Cancelled.", "tone": "calm"})]]
        await r.chief.order({"action": "beam", "who": ["captain"], "to": "pad 2"}, "ops")
        await r.settle()
        await r.chief.order({"action": "abort"}, "ops")
        await r.settle()
        self.assertEqual((r.chief.journal.record["sent"], r.chief.journal.record["aborted"]), (1, 1))
        self.assertIn("1 transports carried out", r.chief.journal.text())


class TheRoomsNews(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.r = Room(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_routine_news_is_read_together_after_a_moment(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "They're through, Captain: pad two, all intact.", "tone": "calm"})]]
        self.assertTrue(r.chief.on_event("transporter: X3 done: Lieutenant Sato is at pad 2, a clean arrival"))
        await asyncio.sleep(0)
        self.assertEqual(r.llm.requests, [])                                  # not at once: more of the same burst may follow
        r.now += transporter.SETTLE_S + 0.1
        r.chief.kick()
        await r.settle()
        self.assertEqual(len(r.llm.requests), 1)
        self.assertIn("X3 done", r.llm.user_of())
        self.assertIn("[Room events, just now]", r.llm.user_of())
        self.assertEqual(r.voice.lines[0][4].get("answer"), False)           # news is not an answer: it waits its turn in the voice's queue

    async def test_danger_the_world_marked_is_read_at_once_and_is_urgent_to_say(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "Lock lost with the Captain in the buffer: rebuilding it.", "tone": "urgent", "urgent": True})]]
        r.chief.on_event("transporter: URGENT: X4: the lock is lost with the Captain in the buffer (jamming 70%)")
        r.now += 0.35
        r.chief.kick()
        await r.settle()
        self.assertEqual(len(r.llm.requests), 1)
        self.assertTrue(r.voice.lines[0][4].get("priority_urgent"))

    async def test_news_that_is_not_hers_is_not_taken(self) -> None:
        self.assertFalse(self.r.chief.on_event("flight: Alpha Lead has landed"))
        self.assertEqual(self.r.chief._events, [])

    async def test_routine_news_leaves_the_console_to_speak_when_the_budget_is_spent(self) -> None:
        r = self.r
        r.chief._spent.append((r.now, transporter.BUDGET_USD + 0.01))
        r.chief.on_event("transporter: X5 done: the Captain is at pad 2, a clean arrival")
        r.now += transporter.SETTLE_S + 0.1
        r.chief.kick()
        await r.settle()
        self.assertEqual(r.llm.requests, [])                                  # the wall display shows it; no model call for it
        r.chief.on_event("transporter: URGENT: X6: pattern lost")
        r.now += 0.4
        r.chief.kick()
        await r.settle()
        self.assertEqual(len(r.llm.requests), 1)                              # danger is never a matter of budget

    async def test_the_captain_speaking_cuts_off_the_news_but_not_the_answer_to_him(self) -> None:
        r = self.r
        r.llm.delay = 0.5
        r.llm.queue = [[("say", {"text": "News line.", "tone": "calm"})]]
        r.chief.on_event("transporter: X3 done: the Captain is at pad 2")
        r.now += transporter.SETTLE_S + 0.1
        r.chief.kick()
        await asyncio.sleep(0.05)
        self.assertEqual(r.chief.preempt(), 1)                                # the Captain speaks: the news turn stops
        await r.settle()
        self.assertEqual(r.voice.lines, [])
        self.assertEqual(len(r.chief._events), 1)                             # ... and the news is read again after him
        # an order carried out is not cut off
        r.llm.queue = [[("transport", {"who": ["captain"], "to": "pad 2"}), ("say", {"text": "Pad two.", "tone": "calm"})]]
        await r.chief.order({"action": "beam", "who": ["captain"], "to": "pad 2"}, "ops")
        await asyncio.sleep(0.05)
        self.assertEqual(r.chief.preempt(), 0)
        await r.settle()
        self.assertEqual(len(r.calls), 1)

    async def test_a_line_that_waited_is_thought_again_by_her_and_by_no_one_else(self) -> None:
        r = self.r
        r.llm.queue = [[("say", {"text": "They are home, pad two.", "tone": "calm"})]]
        out = await r.chief.rethink("xfer_chief", "Lock held, energizing.", 30.0, "", "en")
        self.assertEqual(out, "They are home, pad two.")
        self.assertIn("30 seconds ago", r.llm.user_of())
        self.assertIsNone(await r.chief.rethink("flight", "something", 10.0, "", "en"))


class JoiningTheShip(unittest.IsolatedAsyncioTestCase):
    def test_the_bridge_has_the_relay_only_when_the_game_has_the_room(self) -> None:
        with_room = [t["function"]["name"] for t in tools.tools_for(STATE).tools]
        without = [t["function"]["name"] for t in tools.tools_for({"captain": "on the bridge"}).tools]
        self.assertIn("transporter", with_room)
        self.assertNotIn("transporter", without)
        self.assertIn("transporter", tools.SHIP_TOOL_NAMES)
        self.assertEqual(tools.owner_of("transporter"), "ops")
        # never on an officer's own initiative: every transport is the Captain's order
        self.assertNotIn("transporter", tools.initiative_names(STATE, [{"department": "ops", "order": "keep the heat down"}]))
        schema = next(t for t in tools.tools_for(STATE).tools if t["function"]["name"] == "transporter")["function"]["parameters"]
        self.assertEqual(schema["required"], ["action"])
        self.assertEqual(schema["properties"]["action"]["enum"], ["beam", "energize", "abort", "ask"])
        self.assertEqual(schema["properties"]["override"]["items"]["enum"], ["hazard", "weak_lock"])

    def test_the_crew_is_told_who_she_is_and_what_needs_the_captains_word(self) -> None:
        prompt = crew.system_prompt("en", STATE, [])
        self.assertIn("Rhea Ostrander", prompt)
        self.assertIn("NOT yours", prompt)
        self.assertIn("no officer beams anyone on their own initiative", prompt)
        self.assertIn("`shield_window`", prompt)
        self.assertNotIn("Rhea Ostrander", crew.system_prompt("en", {"captain": "on the bridge"}, []))    # a game without the room has no rule for it

    def test_the_game_lists_her_among_those_who_can_hear(self) -> None:
        self.assertEqual(context_mod.known_speakers(["helm", "xfer_chief", "deck1", "npc4"]), ("helm", "xfer_chief"))
        ctx = context_mod.parse({"place": "transporter_room", "in_earshot": ["xfer_chief"], "facing": "xfer_chief"}, STATE)
        self.assertEqual((ctx.place, ctx.in_earshot, ctx.facing), ("transporter_room", ("xfer_chief",), "xfer_chief"))
        self.assertTrue(transporter.TransporterRoom(FakeLLM(), FakeVoice(), None).in_earshot({"in_earshot": ["helm", "xfer_chief"]}))     # type: ignore[arg-type]
        self.assertFalse(transporter.TransporterRoom(FakeLLM(), FakeVoice(), None).in_earshot({"in_earshot": ["helm"]}))                   # type: ignore[arg-type]

    def test_the_voice_stage_knows_her(self) -> None:
        name, voice = server.EXTERNAL_SPEAKERS["xfer_chief"]
        self.assertIn("Rhea Ostrander", name)
        self.assertEqual(voice, transporter.VOICE)
        self.assertEqual(server.speaker_identity("xfer_chief")[2], False)         # (a voice of the room, not a bridge console)
        self.assertIn("transporter", models.ROLES)

    async def test_the_bridges_tool_goes_to_the_chief_not_to_the_game(self) -> None:
        sent: list[dict[str, Any]] = []

        async def send(m: dict[str, Any]) -> None:
            sent.append(m)

        async def hook(args: dict[str, Any], by: str) -> dict[str, Any]:
            return {"ok": True, "detail": f"handed over by {by}: {args['action']}"}
        ship = server.GameShip(send, intercept={"transporter": hook})
        res = await ship.execute("transporter", {"action": "beam", "who": ["captain"], "to": "surface"}, "ops")
        self.assertEqual(res, {"ok": True, "detail": "handed over by ops: beam"})
        self.assertEqual(sent, [])                                            # the game never saw the bridge's tool: only the Chief's own commands
        await asyncio.wait_for(asyncio.sleep(0), 1.0)

    async def test_two_listeners_one_verdict(self) -> None:
        loop = asyncio.get_running_loop()
        a, b = loop.create_future(), loop.create_future()
        both = server._both(a, b)
        a.set_result(True)
        await asyncio.sleep(0)
        self.assertFalse(both.done())                                         # the bridge waits for the second listener
        b.set_result(True)
        await asyncio.sleep(0)
        self.assertTrue(both.result())                                        # nobody answered: the words were for the bridge
        a2, b2 = loop.create_future(), loop.create_future()
        both2 = server._both(a2, b2)
        a2.set_result(False)                                                  # an NPC answered
        b2.set_result(True)
        await asyncio.sleep(0)
        self.assertFalse(both2.result())


@unittest.skipUnless((FIXTURES / "card_battle.json").exists(), "the world bench's cards are not in the repository yet")
class TheRealCard(unittest.TestCase):
    """Cards exactly as the game wrote them (tools/transport.py run --scenario world writes them to Saved/Transport/fixtures; the ones here were copied from it)."""

    def cards(self) -> dict[str, dict[str, Any]]:
        return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("card_*.json"))}

    def test_every_card_reads_and_the_chief_gets_it_whole(self) -> None:
        for name, card in self.cards().items():
            st = dict(STATE, transporter=card)
            board = transporter.board(st)
            self.assertIn("YOUR CONSOLE", board, name)
            self.assertIn(json.dumps(card["room"], separators=(",", ":"), ensure_ascii=False), board, name)
            self.assertTrue(transporter.brief(card).startswith("room "), name)
            self.assertLess(len(json.dumps(card)), 6000, name)                # the card is the prompt's biggest part: it stays small

    def test_the_battles_card_says_what_clears_what_and_what_cannot_be_aimed(self) -> None:
        card = self.cards()["card_battle"]
        opts = {o["to"]: o for o in card["options"]}
        self.assertTrue(any(o["answer"].startswith("can") or "window" in o.get("what_clears_it", "") for o in opts.values()))
        for o in opts.values():
            if o["answer"] != "can be done now":
                self.assertTrue(o.get("in_the_way"), o["to"])                 # a no always says why


if __name__ == "__main__":
    unittest.main()
