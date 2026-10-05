"""Offline tests of VOCI-3 (docs/brief/VOCI-3.md): a clear bridge and a Captain in control. No network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.voci3_unit -v

What is checked here is the mechanics the behaviour stands on (the minds' judgement is for the real models, by their tool calls and by ear): where the Captain is is the first
thing every crew turn reads, and the officers are told it beats anything remembered; the nets' traffic reaches the consoles and the listening officer and never the bridge's speaker
unless it is the Captain's own (an answer to him, a call to him, a net he asked to hear); the silent log is a real tool of the crew; what the officers see at the head of a turn
holds what the nets said and the consoles logged. The speech floor's guarantees (nothing addressed to the Captain is lost) are in `voci3_floor`, the 5 October games replayed
through the real server in `voci3_games`."""
from __future__ import annotations

import asyncio
import json
import re
import unittest

from astra_mind import agent as agent_mod
from astra_mind import context as context_model
from astra_mind import crew as crew_mod
from astra_mind import initiative as initiative_mod
from astra_mind import models
from astra_mind import nets as nets_mod
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tools import tools_for

from .stations_unit import Crew, Script, speak
from .voice_floor import LONG, run
from .voice_replay import Replay

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
        _, _, rest = now.partition("[The bridge now]\n")
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


class Rig:
    """A `Nets` with a fake game and a fake listener, on the virtual clock."""

    def __init__(self, **kw) -> None:  # noqa: ANN003
        self.sent: list[dict] = []
        self.heard: list[tuple[str, str, bool, str]] = []            # what the listeners were given
        self.aloud: list[str] = []

        async def send(msg: dict) -> None:
            self.sent.append(msg)

        async def listen(net: str, text: str, urgent: bool, lang: str) -> None:
            self.heard.append((net, text, urgent, lang))
        self.nets = nets_mod.Nets(send, listen, **kw)

    async def post(self, net: str, who: str, text: str, **kw) -> bool:  # noqa: ANN003
        async def aloud() -> None:
            self.aloud.append(text)
        return await self.nets.post(net, who.lower().replace(" ", "_"), who, text, kw.pop("lang", "it"), aloud=aloud, **kw)

    def types(self, t: str) -> list[dict]:
        return [m for m in self.sent if m.get("type") == t]


class TestNetsRouting(unittest.TestCase):
    """What reaches the bridge's speaker by itself is the Captain's own: an answer, a direct call, a net he asked for. The rest is traffic for the listener and the logs."""

    def test_an_answer_and_a_direct_call_are_heard_and_nothing_else_is(self) -> None:
        async def go() -> None:
            r = Rig()
            self.assertTrue(await r.post("fleet", "Rourke", "Captain, my answer.", answer=True))
            self.assertTrue(await r.post("fleet", "Rourke", "Aquila, Fleet's order.", direct=True, addressed=True))
            self.assertFalse(await r.post("fleet", "Castellan", "Aquila, Praetorian: screen confirmed at 4.5 km."))
            self.assertFalse(await r.post("flight", "Deck", "Alpha rearmed."))
            await asyncio.sleep(0.01)
            self.assertEqual(r.aloud, ["Captain, my answer.", "Aquila, Fleet's order."])
            msgs = r.types("net_traffic")
            self.assertEqual([(m["net"], m["aloud"]) for m in msgs], [("fleet", True), ("fleet", True), ("fleet", False), ("flight", False)])
            self.assertEqual(msgs[2]["console"], "comms")
            self.assertEqual(msgs[3]["console"], "flight")
        run(go())

    def test_routine_traffic_is_read_together_a_few_seconds_later(self) -> None:
        async def go() -> None:
            r = Rig()
            await r.post("fleet", "Castellan", "First position report.")
            await asyncio.sleep(5.0)
            await r.post("fleet", "Okoro", "Second one, from the Vigilant.")
            self.assertEqual(r.heard, [])
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S)
            self.assertEqual(len(r.heard), 1, r.heard)
            net, text, urgent, lang = r.heard[0]
            self.assertEqual((net, urgent, lang), ("fleet", False, "it"))
            self.assertIn("First position report.", text)
            self.assertIn("Second one, from the Vigilant.", text)
            self.assertIn("2 lines", text)
            self.assertIn("Martin", text)                          # (the listener is named: Ensign Leo Martin has the watch on the fleet net)
        run(go())

    def test_an_urgent_line_reaches_the_listener_at_once_and_takes_the_routine_with_it(self) -> None:
        async def go() -> None:
            r = Rig()
            await r.post("fleet", "Castellan", "A routine line waiting for its batch.")
            await r.post("fleet", "Okoro", "Vigilant: hit, losing power!", urgent=True)
            await asyncio.sleep(0.01)
            self.assertEqual(len(r.heard), 1)
            self.assertTrue(r.heard[0][2])
            self.assertIn(nets_mod.URGENT_MARK, r.heard[0][1])
            self.assertIn("routine line", r.heard[0][1])
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S + 1)
            self.assertEqual(len(r.heard), 1, "the routine line went twice")
        run(go())

    def test_a_call_to_the_captain_goes_to_the_listener_within_moments(self) -> None:
        async def go() -> None:
            r = Rig()
            await r.post("flight", "Alpha Lead", "Captain, permission to break off?", addressed=True)
            await asyncio.sleep(nets_mod.ADDRESSED_BATCH_S + 0.1)
            self.assertEqual(len(r.heard), 1)
            self.assertIn("and calls the Captain", r.heard[0][1])
            self.assertIn("Price", r.heard[0][1])
        run(go())

    def test_traffic_between_others_is_on_the_log_and_wakes_nobody(self) -> None:
        async def go() -> None:
            r = Rig()
            await r.post("fleet", "Castellan", "Vigilant, take the port side.", quiet=True)
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S + 1)
            self.assertEqual(r.heard, [])
            self.assertEqual(len(r.types("net_traffic")), 1)
            self.assertIn("take the port side", r.nets.digest())
        run(go())

    def test_a_net_on_the_speaker_is_heard_until_he_says_to_take_it_off(self) -> None:
        async def go() -> None:
            r = Rig()
            await r.post("flight", "Deck", "Alpha rearmed.")                    # (waiting for its listener)
            res = r.nets.set_speaker("flight", True)
            self.assertTrue(res["ok"])
            await asyncio.sleep(0.01)
            self.assertEqual(r.types("net_speaker")[-1], {"type": "net_speaker", "net": "flight", "on": True})
            self.assertTrue(await r.post("flight", "Bravo Lead", "Four fish away."))
            self.assertFalse(await r.post("fleet", "Castellan", "Still not on the speaker."))           # (another net)
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S + 1)
            self.assertEqual([h[0] for h in r.heard], ["fleet"], "what waited for the flight listener is on the log: he hears them himself now")
            self.assertIn("On the Captain's speaker now: the flight net", r.nets.digest())
            r.nets.set_speaker("flight", False)
            self.assertFalse(await r.post("flight", "Deck", "Alpha ready."))
            self.assertNotIn("On the Captain's speaker now", r.nets.digest())
            self.assertFalse(r.nets.set_speaker("galley", True)["ok"])
        run(go())

    def test_the_flight_net_is_his_own_radio_in_a_cockpit(self) -> None:
        async def go() -> None:
            r = Rig()
            where = {"cockpit": False}
            r.nets.presence["flight"] = lambda: where["cockpit"]
            self.assertFalse(await r.post("flight", "Alpha 2", "Tally, he is mine."))
            where["cockpit"] = True
            self.assertTrue(await r.post("flight", "Alpha 2", "Engaging."))
            self.assertFalse(await r.post("fleet", "Castellan", "Not his radio."))
        run(go())

    def test_with_the_nets_off_everything_goes_to_the_speaker_as_before(self) -> None:
        async def go() -> None:
            r = Rig(enabled=False)
            self.assertTrue(await r.post("fleet", "Castellan", "Position."))
            self.assertTrue(await r.post("flight", "Deck", "Rearmed."))
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S + 1)
            self.assertEqual(r.heard, [])
            self.assertEqual(len(r.aloud), 2)
        run(go())

    def test_a_broken_listener_loses_nothing(self) -> None:
        async def go() -> None:
            r = Rig()

            async def boom(net: str, text: str, urgent: bool, lang: str) -> None:
                raise RuntimeError("the turn queue is gone")
            r.nets.listen = boom
            await r.post("fleet", "Castellan", "Position.", urgent=True)
            await asyncio.sleep(0.1)
            self.assertIn("Position.", r.nets.digest())              # (it is on the log whatever happened to the listener)
        run(go())


class TestConsoleLog(unittest.TestCase):
    def test_a_line_on_a_console_log_goes_to_the_game_and_to_the_officers_view(self) -> None:
        async def go() -> None:
            r = Rig()
            res = r.nets.console_log("tactical", "T-11 range 49.5 km, opening", by="tactical")
            await asyncio.sleep(0.01)
            self.assertTrue(res["ok"])
            msg = r.types("console_log")[0]
            self.assertEqual((msg["station"], msg["text"], msg["kind"]), ("tactical", "T-11 range 49.5 km, opening", "routine"))
            self.assertIn("tactical log: T-11 range 49.5 km, opening", r.nets.digest())
            self.assertFalse(r.nets.console_log("galley", "x")["ok"])
            self.assertFalse(r.nets.console_log("helm", "   ")["ok"])
            self.assertTrue(r.nets.console_log("helm", "A notable one", kind="notice")["ok"])
            self.assertIn("helm log (notice): A notable one", r.nets.digest())
        run(go())

    def test_the_digest_keeps_the_last_minutes_and_the_last_lines(self) -> None:
        async def go() -> None:
            r = Rig()
            r.nets.console_log("ops", "An old line")
            await asyncio.sleep(nets_mod.DIGEST_WINDOW_S + 5)
            for i in range(nets_mod.DIGEST_LINES + 3):
                r.nets.console_log("ops", f"Line {i}")
                await asyncio.sleep(1.0)
            d = r.nets.digest()
            self.assertNotIn("An old line", d)
            self.assertIn(f"Line {nets_mod.DIGEST_LINES + 2}", d)
            self.assertNotIn("ops log: Line 0\n", d + "\n")
            self.assertIn("older line(s) on the consoles", d)
            self.assertEqual(d.count("\n - ") + d.startswith(" - "), nets_mod.DIGEST_LINES)
        run(go())

    def test_a_new_session_clears_everything(self) -> None:
        async def go() -> None:
            r = Rig()
            r.nets.set_speaker("fleet", True)
            r.nets.console_log("ops", "x")
            await r.post("flight", "Deck", "y")
            r.nets.reset()
            self.assertEqual(r.nets.digest(), "")
            await asyncio.sleep(nets_mod.ROUTINE_BATCH_S + 1)
            self.assertEqual(r.heard, [])
        run(go())


class TestCrewTools(unittest.TestCase):
    """`console_log` is a real tool of the crew: silent, in every turn, and never an action to read back; `net_speaker` is the Captain's."""

    def _crew(self, *scripts: Script) -> tuple[Crew, Rig]:
        c = Crew(*scripts)
        rig = Rig()
        c.agent.nets = rig.nets
        return c, rig

    def test_the_tool_is_on_every_crew_turns_list_and_taught(self) -> None:
        c, _ = self._crew()
        names = {t["function"]["name"] for t in tools_for(c.ship.snapshot()).tools}
        self.assertIn("console_log", names)
        self.assertIn("net_speaker", names)
        self.assertIn("console_log", {t["function"]["name"] for t in tools_for(LocalShip(stations=False, fight=True).snapshot()).tools})
        self.assertIn("console_log", crew_mod.system_prompt("en", c.ship.snapshot(), []))

    def test_a_turn_that_only_writes_the_log_says_nothing_and_asks_for_no_read_back(self) -> None:
        c, rig = self._crew(Script(calls=[("console_log", {"station": "tactical", "text": "T-11 range 49.5 km"})]))
        t = asyncio.run(c.agent.handle_event("net: traffic on the fleet net — 1 line", "en"))
        self.assertEqual(c.said, [])
        self.assertEqual(len(c.llm.requests), 1, "a second call was made to read back a line written on the log")
        self.assertEqual([(a[0], a[2]["ok"]) for a in t.actions], [("console_log", True)])
        self.assertIn("tactical log: T-11 range 49.5 km", rig.nets.digest())
        self.assertEqual(c.agent.history, [], "a log-only turn must not lengthen the conversation")

    def test_the_log_is_not_offered_to_the_chatter(self) -> None:
        c, _ = self._crew(Script())
        asyncio.run(c.agent.handle_event("a quiet moment", "en", speak_only=True))
        sent = {t["function"]["name"] for t in c.llm.requests[0]["tools"]}
        self.assertEqual(sent, {"speak"})

    def test_an_officer_may_log_and_speak_in_the_same_turn(self) -> None:
        c, rig = self._crew(Script(calls=[("console_log", {"station": "flight", "text": "Alpha rearmed, 8 ready"}),
                                          speak("Captain, Alpha is ready to launch again.", "flight")]))
        asyncio.run(c.agent.handle_event("net: traffic on the flight net — 1 line", "en"))
        self.assertEqual(c.said, [("flight", "Captain, Alpha is ready to launch again.")])
        self.assertEqual(len(c.llm.requests), 1)
        self.assertIn("flight log: Alpha rearmed, 8 ready", rig.nets.digest())

    def test_the_net_speaker_is_the_captains_to_give(self) -> None:
        c, rig = self._crew(Script(calls=[("net_speaker", {"net": "flight", "on": True}), speak("Flight net on the speaker, Captain.", "flight")]),
                            Script(calls=[("net_speaker", {"net": "fleet", "on": True})]), Script())
        asyncio.run(c.agent.handle("put the flight net on the speaker", "en"))
        self.assertTrue(rig.nets.on_speaker("flight"))
        self.assertEqual(c.said, [("flight", "Flight net on the speaker, Captain.")])
        asyncio.run(c.agent.handle_event("net: traffic on the fleet net", "en"))                # (an officer on their own initiative: refused)
        self.assertFalse(rig.nets.on_speaker("fleet"))

    def test_the_head_of_a_turn_shows_what_the_nets_said_and_the_logs_hold(self) -> None:
        c, rig = self._crew(Script(), Script())

        async def go() -> None:
            rig.nets.console_log("ops", "Fire out deck 6 C")
            await rig.post("fleet", "Castellan", "Aquila, Praetorian: holding at 4.5 km.")
            await c.agent.handle("how are the allies?", "en")
        asyncio.run(go())
        last = c.llm.requests[0]["messages"][-1]["content"]
        self.assertIn("On the nets and the consoles' logs, NOT said aloud", last)
        self.assertIn("ops log: Fire out deck 6 C", last)
        self.assertIn("fleet net · Castellan: «Aquila, Praetorian: holding at 4.5 km.»", last)


WHEEL = crew_mod.WHEEL_EVENT + ", without a word: "


def event_line(request: dict) -> str:
    """The news a crew turn was asked about (the line after «[Ship systems event, not the Captain speaking]» in its last message)."""
    m = re.search(r"\[Ship systems event, not the Captain speaking\] (.*)", str(request["messages"][-1]["content"]))
    return m.group(1) if m else ""


def wheel_model(r: Replay, acks: dict[str, tuple[float, str, str]]) -> list[dict]:
    """The replay's model with the command wheel's officers added: for an event of the wheel that has one of `acks`' markers in it the officer says the line after the delay; any
    other call goes to the replay's own script. Returns the requests the model was given."""
    seen: list[dict] = []
    chat = r._chat

    async def model(**kw):  # noqa: ANN003, ANN202
        seen.append({**kw, "_t": asyncio.get_running_loop().time()})
        event = event_line(kw)
        again = re.search(r"\[Before speaking\] \d+ seconds ago .*?«(.*?)»", str(kw["messages"][-1]["content"]), re.S)
        if again:                                                    # (an officer thinks again about a line that waited: the sensible one says it as it stands)
            await asyncio.sleep(0.4)
            comp = Completion(provider="script", model="script")
            call = ToolCall(name="speak", arguments_raw=json.dumps({"speaker": "xo", "text": again.group(1), "tone": "focused"}))
            comp.tool_calls.append(call)
            if kw.get("on_tool_call") is not None:
                res = kw["on_tool_call"](call)
                if hasattr(res, "__await__"):
                    await res
            return comp
        if event.startswith(crew_mod.WHEEL_EVENT):
            for marker, (delay, who, text) in acks.items():
                if marker in event:
                    await asyncio.sleep(delay)
                    comp = Completion(provider="script", model="script")
                    call = ToolCall(name="speak", arguments_raw=json.dumps({"speaker": who, "text": text, "tone": "focused"}))
                    comp.tool_calls.append(call)
                    if kw.get("on_tool_call") is not None:
                        res = kw["on_tool_call"](call)
                        if hasattr(res, "__await__"):
                            await res
                    return comp
        return await chat(**kw)
    r.mind.llm.chat = model
    return seen


class TestTheBridgeDoctrine(unittest.TestCase):
    """The doctrine of the talk (docs/brief/VOCI-3.md, 2 and 3): one voice for the picture, the others for their console in three cases, the routine on the log, an
    acknowledgement that is a few words, nothing said twice. What the models do with it is measured on the real ones (voci3_battle, voci3_live)."""

    PROMPT = crew_mod.system_prompt("it", {"stations": {}}, [])

    def test_the_xo_is_the_voice_of_the_picture_and_the_others_have_three_cases(self) -> None:
        for needle in ("ONE VOICE FOR THE PICTURE", "The XO (Serra) is the voice of the picture and of advice", "nobody else summarises",
                       "in three cases only", "danger in their field that he can act on", "a decision in their field", "console_log", "What has been said once is said"):
            self.assertIn(needle, self.PROMPT)

    def test_an_acknowledgement_is_a_few_words_and_no_example_carries_the_situation_around_it(self) -> None:
        self.assertIn("in as few words as carry it", self.PROMPT)
        self.assertNotIn("i railgun lo battono", self.PROMPT)
        self.assertNotIn("the railguns are on her", crew_mod.system_prompt("en", {"stations": {}}, []))

    def test_the_news_ask_decides_between_saying_logging_and_saying_nothing(self) -> None:
        ask = agent_mod.EVENT_ASK
        for needle in ("SAY IT", "from the XO, who is the voice of the picture", "LOG IT with `console_log`", "NO `speak`", "SAY NOTHING", "«Said aloud»", "«Waiting to be said»",
                       "the same picture again", "[happened N s ago]", "Before you speak, read «Said aloud»", "say only what is NEW", "distress call", "ONE grouped line",
                       "only when the Aquila can really do something about it now"):
            self.assertIn(needle, ask)
        for kept in ("A hail and a channel are Communications'", "set a mode on their own console when their delegation is auto", "is proposed instead"):
            self.assertIn(kept, ask)

    def test_a_report_turn_labels_the_recent_events_as_older_news_and_the_said_aloud_as_heard(self) -> None:
        now = crew_mod.bridge_now({"captain": "x"}, ["engineering: heat 90 %", "tactical: 23 missiles inbound"], said_aloud="- 4 s ago, xo: «x»", news=True)
        self.assertIn("the NEWS of this turn is the event at the end of this message", now)
        self.assertIn("never say them again, in other words or from another officer either", now)
        plain = crew_mod.bridge_now({"captain": "x"}, ["engineering: heat 90 %"])
        self.assertNotIn("the NEWS of this turn", plain)
        c = Crew(Script())
        asyncio.run(c.agent.handle_event("tactical: 23 missiles inbound", "en"))
        self.assertIn("the NEWS of this turn", c.llm.requests[0]["messages"][-1]["content"])
        c2 = Crew(Script())
        asyncio.run(c2.agent.handle("fire on the Cocytus", "en"))
        self.assertNotIn("the NEWS of this turn", c2.llm.requests[0]["messages"][-1]["content"])

    def test_a_follow_up_to_a_failure_does_not_say_again_what_was_said(self) -> None:
        c = Crew(Script(calls=[speak("Alpha is rearming, Captain: thirty-six seconds.", "flight"), ("station", {"station": "flight", "mode": "strike", "params": {"target": "T-99"}})]),
                 Script(calls=[]))
        asyncio.run(c.agent.handle("Alpha e Bravo subito fuori", "it"))
        follow = c.llm.requests[-1]["messages"][-1]["content"]
        self.assertIn("nothing is said twice", follow)

    def test_the_watch_logs_what_it_sets_inside_the_orders(self) -> None:
        self.assertIn("console_log", initiative_mod.WATCH_ASK)
        self.assertIn("only when it changes the fight", initiative_mod.WATCH_ASK)
        system = initiative_mod.watch_system("it", LocalShip(stations=True, fight=True).snapshot(), "", "", "")
        self.assertIn("goes on the console's log with `console_log` and nobody says it", system)


class TestThePicturesPace(unittest.TestCase):
    """5 October: 86 news items in three minutes of a battle, a report turn for each, ten lines a minute. The picture is now given at its own pace (server.PICTURE_GAP_S after a
    report that said something, REPORT_GAP_S after one that said nothing); the news that came meanwhile is read together; a warning of danger and a call do not wait."""

    @staticmethod
    def times(seen: list[dict], marker: str) -> list[float]:
        return [k["_t"] for k in seen if marker in event_line(k)]

    @staticmethod
    async def until(seen: list[dict], markers: list[str], limit: float = 60.0) -> None:
        """Wait (virtual time) until a report turn has been asked about each of the markers: the turn worker holds news back for a quiet bridge and the picture's pace."""
        t0 = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - t0 < limit and not all(any(m in event_line(k) for k in seen) for m in markers):
            await asyncio.sleep(0.2)
        await asyncio.sleep(1.0)

    def test_the_next_report_waits_for_the_picture_gap_after_one_that_was_said(self) -> None:
        from astra_mind.server import PICTURE_GAP_S

        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": "sensors: hostile contact T-22 detected, bearing 090, range 90 km", "report": True})
                await asyncio.sleep(3.0)
                r.game.push({"type": "event", "text": "engineering: reactor output at 80 percent, coolant loop two warm", "report": True})
                await self.until(seen, ["hostile contact T-22", "reactor output"])
                a, = self.times(seen, "hostile contact T-22")
                b, = self.times(seen, "reactor output")
                self.assertGreaterEqual(b - a, PICTURE_GAP_S, f"the second report turn was {b - a:.1f} s after the first, which said something")
                self.assertLess(b - a, PICTURE_GAP_S + 4.0, "and not much later than the gap")
        run(go())

    def test_after_a_report_that_said_nothing_the_gap_is_short(self) -> None:
        from astra_mind.server import REPORT_GAP_S

        async def go() -> None:
            async with Replay() as r:
                r.script["[silent]"] = (0.3, [])
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": "sensors: [silent] a contact faded", "report": True})
                await asyncio.sleep(1.0)
                r.game.push({"type": "event", "text": "engineering: reactor output at 80 percent, coolant loop two warm", "report": True})
                await self.until(seen, ["[silent]", "reactor output"])
                a, = self.times(seen, "[silent]")
                b, = self.times(seen, "reactor output")
                self.assertGreaterEqual(b - a, REPORT_GAP_S - 0.3)
                self.assertLess(b - a, REPORT_GAP_S + 2.0)
        run(go())

    def test_a_warning_of_danger_does_not_wait_and_takes_the_waiting_news_with_it(self) -> None:
        from astra_mind.server import PICTURE_GAP_S

        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": "sensors: hostile contact T-22 detected, bearing 090, range 90 km", "report": True})
                await asyncio.sleep(3.0)
                r.game.push({"type": "event", "text": "engineering: reactor output at 80 percent, coolant loop two warm", "report": True})
                await asyncio.sleep(2.0)
                r.game.push({"type": "event", "text": "tactical: missiles inbound, bearing 270", "report": True})
                await self.until(seen, ["hostile contact T-22", "missiles inbound"])
                a, = self.times(seen, "hostile contact T-22")
                w, = self.times(seen, "missiles inbound")
                self.assertLess(w - a, PICTURE_GAP_S - 3.0, f"the warning waited {w - a:.1f} s")
                joined = [event_line(k) for k in seen if "missiles inbound" in event_line(k)][0]
                self.assertIn("reactor output", joined, "what was waiting for the next picture goes with the warning")
        run(go())

    def test_a_second_warning_waits_a_moment_after_one_that_was_said(self) -> None:
        from astra_mind.server import URGENT_GAP_S

        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": "tactical: missiles inbound, bearing 270", "report": True})
                await asyncio.sleep(2.0)
                r.game.push({"type": "event", "text": "tactical: missiles inbound, bearing 090 [again]", "report": True})
                await self.until(seen, ["bearing 270", "bearing 090"])
                a, = self.times(seen, "bearing 270")
                b, = self.times(seen, "bearing 090")
                self.assertGreaterEqual(b - a, URGENT_GAP_S - 1.0, f"the second warning came {b - a:.1f} s after the first")
                self.assertLess(b - a, URGENT_GAP_S + 4.0)
        run(go())

    def test_a_call_to_the_captain_on_a_net_does_not_wait_either(self) -> None:
        from astra_mind.server import PICTURE_GAP_S

        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": "sensors: hostile contact T-22 detected, bearing 090, range 90 km", "report": True})
                await asyncio.sleep(3.0)
                await r.mind.turns.put(("\x00event:" + TestWhatTheCaptainsWordsDoNotLose.CALL, "it"))
                await self.until(seen, ["hostile contact T-22", "traffic on the fleet net"])
                a, = self.times(seen, "hostile contact T-22")
                c, = self.times(seen, "traffic on the fleet net")
                self.assertLess(c - a, PICTURE_GAP_S - 3.0, f"the call waited {c - a:.1f} s")
        run(go())


class TestDelegation(unittest.TestCase):
    """The game starts every launch with `auto` on every console and forgets what the Captain said. What commits the ship starts on `advise` in a new campaign (the lead agreed:
    flight; and the helm's pursuits), and what the Captain says is kept with the campaign and put back in the game (delegation.py, server.delegation_sync)."""

    STATE = {"stations": {s: {"delegation": "auto", "modes": {}} for s in ("helm", "ops", "tactical", "comms", "sensors", "engineering", "flight", "xo")}}

    def setUp(self) -> None:
        import os
        import tempfile
        self.dir = tempfile.mkdtemp(prefix="astra_delegation_")
        self.path = os.path.join(self.dir, "delegation.json")

    def test_a_new_campaign_starts_with_what_commits_the_ship_on_advise(self) -> None:
        from astra_mind import delegation as d
        dg = d.Delegation(self.path)
        self.assertEqual(dg.pending(self.STATE), [], "nothing before a campaign is chosen")
        dg.begin(new=True)
        self.assertEqual(sorted(dg.pending(self.STATE)), [("flight", "advise"), ("helm", "advise")])
        self.assertEqual(dg.pending({}), [], "nothing while the game has no consoles")

    def test_the_captains_word_is_kept_and_not_asked_of_the_game_twice(self) -> None:
        from astra_mind import delegation as d
        dg = d.Delegation(self.path)
        dg.begin(new=True)
        self.assertTrue(dg.note_call("station", {"station": "xo", "mode": "delegation", "params": {"station": "tactical", "level": "manual"}}, {"ok": True}))
        self.assertFalse(dg.note_call("station", {"station": "xo", "mode": "delegation", "params": {"station": "tactical", "level": "auto"}}, {"ok": False}), "a refused one is not kept")
        self.assertFalse(dg.note_call("station", {"station": "helm", "mode": "intercept", "params": {"target": "T-1"}}, {"ok": True}))
        self.assertFalse(dg.note_call("speak", {}, {"ok": True}))
        self.assertEqual(dg.levels["tactical"], "manual")
        pend = sorted(dg.pending(self.STATE))
        self.assertIn(("tactical", "manual"), pend)
        dg.asked("tactical", "manual")
        self.assertNotIn(("tactical", "manual"), dg.pending(self.STATE), "asked once: not again until it changes")
        self.assertTrue(dg.set("tactical", "auto"))
        self.assertEqual(dg.sent.get("tactical"), None)
        self.assertFalse(dg.set("xo", "auto"), "the XO's own console has no delegation")
        self.assertFalse(dg.set("helm", "whenever"))

    def test_it_stays_with_the_campaign(self) -> None:
        from astra_mind import delegation as d
        a = d.Delegation(self.path)
        a.begin(new=True)
        a.set("flight", "auto")                                              # («da qui in poi fate da soli»)
        a.set("tactical", "manual")
        b = d.Delegation(self.path)
        b.begin(new=False)                                                   # (the saved campaign, another launch)
        self.assertEqual((b.levels["flight"], b.levels["tactical"], b.levels["helm"]), ("auto", "manual", "advise"))
        c = d.Delegation(self.path)
        c.begin(new=True)                                                    # (a new war starts over: and a later «continue» does not bring the old levels back)
        c2 = d.Delegation(self.path)
        c2.begin(new=False)
        self.assertEqual((c2.levels["flight"], c2.levels.get("tactical")), ("advise", None))

    def test_the_wire_is_the_xos_delegation_command_in_the_games_words(self) -> None:
        from astra_mind import delegation as d
        w = d.Delegation(self.path).wire("flight", "advise")
        self.assertEqual((w["station"], w["mode"], w["params"]), ("xo", "delegation", {"station": "flight", "delegation": "advise"}))

    def test_the_server_puts_it_back_in_the_game_and_keeps_what_the_captain_says(self) -> None:
        from .voci3_battle import LiveGame

        async def go() -> None:
            rep = Replay()
            rep.game = LiveGame()
            async with rep as r:
                m = r.mind
                m.delegation._path = lambda: self.path
                asyncio.create_task(m.delegation_sync())
                r.game.push({"type": "ship_state", "state": self.STATE})
                await asyncio.sleep(0.3)
                self.assertEqual([c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"], [], "no campaign chosen yet: the game is left as it is")
                m.delegation.begin(new=True)
                await asyncio.sleep(5.0)
                cmds = [c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"]
                got = sorted((c["args"]["params"]["station"], c["args"]["params"]["delegation"]) for c in cmds if c["name"] == "station" and c["args"].get("station") == "xo")
                self.assertEqual(got, [("flight", "advise"), ("helm", "advise")])
                self.assertTrue(all(c["by"] == "xo" for c in cmds))
                # the game now has them: nothing more is asked
                st = {"stations": {k: {**v, "delegation": m.delegation.levels.get(k, "auto")} for k, v in self.STATE["stations"].items()}}
                r.game.push({"type": "ship_state", "state": st})
                await asyncio.sleep(6.0)
                self.assertEqual(len([1 for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"]), 2)
                # the Captain says it: the XO sets it, and it is kept
                chat = m.llm.chat

                async def model(**kw):  # noqa: ANN003, ANN202
                    if "Captain: Voss" in str(kw["messages"][-1]["content"]):
                        comp = Completion(provider="script", model="script")
                        for call in (ToolCall(name="station", arguments_raw=json.dumps({"station": "xo", "mode": "delegation", "params": {"station": "tactical", "level": "manual"}})),
                                     ToolCall(name="speak", arguments_raw=json.dumps({"speaker": "xo", "text": "Tattico solo su suo ordine, Capitano.", "tone": "focused"}))):
                            comp.tool_calls.append(call)
                            res = kw["on_tool_call"](call)
                            if hasattr(res, "__await__"):
                                await res
                        return comp
                    return await chat(**kw)
                m.llm.chat = model
                r.game.push({"type": "player_text", "text": "Voss, solo su mio ordine", "lang": "it"})
                await asyncio.sleep(3.0)
                self.assertEqual(m.delegation.levels["tactical"], "manual")
                with open(self.path, encoding="utf-8") as f:
                    self.assertEqual(json.load(f)["tactical"], "manual")
        run(go())



class _VirtualClock:
    """`time` as the server and the exchange see it, on the loop's virtual clock: the mind's own timers (monotonic) follow the virtual time of a test."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def monotonic(self) -> float:
        return self.loop.time()

    def __getattr__(self, name: str):  # noqa: ANN204
        import time
        return getattr(time, name)


class virtual_monotonic:
    """Inside the block the server's and the context's `time.monotonic()` read the running loop's (virtual) clock."""

    def __enter__(self) -> "virtual_monotonic":
        from astra_mind import context as ctx_mod
        from astra_mind import server as server_mod
        self.mods = (ctx_mod, server_mod)
        self.old = [m.time for m in self.mods]
        clock = _VirtualClock(asyncio.get_running_loop())
        for m in self.mods:
            m.time = clock
        return self

    def __exit__(self, *exc) -> None:  # noqa: ANN002
        for m, t in zip(self.mods, self.old):
            m.time = t

    async def __aenter__(self) -> "virtual_monotonic":
        return self.__enter__()

    async def __aexit__(self, *exc) -> None:  # noqa: ANN002
        self.__exit__(*exc)


class TestTheChannelClosesWithTheExchange(unittest.TestCase):
    """5 October: the fleet's channel stayed open for eighteen minutes after the admiral's answer, and what the Captain said to his own crew went out on it. A channel with the
    fleet, an ally or an enemy is open for an exchange: with nothing passed on it for CHANNEL_IDLE_S Communications closes it, and the Captain opens it again with a word."""

    STATE = TestDelegation.STATE

    def test_an_idle_channel_is_closed_silently_with_a_note_on_the_comms_log(self) -> None:
        from astra_mind.server import CHANNEL_IDLE_S
        from .voci3_battle import LiveGame

        async def go() -> None:
            rep = Replay()
            rep.game = LiveGame()
            async with rep as r, virtual_monotonic():
                m = r.mind
                asyncio.create_task(m.channel_watch())
                r.game.push({"type": "ship_state", "state": self.STATE})
                await asyncio.sleep(0.5)
                m._channel_opened("fleet")
                m._channel_opened("flight")                                  # (the flight net has its own rules)
                self.assertEqual(m._channel, "fleet")
                await asyncio.sleep(40.0)
                m.exchange.heard("fleet", "Aquila, Fleet command: copy.")      # (the admiral speaks: the exchange goes on)
                await asyncio.sleep(CHANNEL_IDLE_S - 5.0)
                self.assertEqual([c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"], [], "still an exchange: open")
                await asyncio.sleep(15.0)
                cmds = [c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"]
                self.assertEqual([(c["name"], c["by"]) for c in cmds], [("end_transmission", "comms")])
                notes = [c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "console_log"]
                self.assertEqual([(n["station"], n["kind"]) for n in notes], [("comms", "notice")])
                self.assertIn("closed", notes[0]["text"])
                self.assertEqual(m._channel, "")
                self.assertEqual(r.trace().order(), [], "silently: nobody says a word")
        run(go())

    def test_the_captain_speaking_to_them_or_a_new_call_keeps_it_open(self) -> None:
        from astra_mind.server import CHANNEL_IDLE_S
        from .voci3_battle import LiveGame

        async def go() -> None:
            rep = Replay()
            rep.game = LiveGame()
            async with rep as r, virtual_monotonic():
                m = r.mind
                asyncio.create_task(m.channel_watch())
                r.game.push({"type": "ship_state", "state": self.STATE})
                r.game.push({"type": "event", "text": "transmission: T-21 — the Archon calls the Aquila", "report": False})
                await asyncio.sleep(0.5)
                self.assertEqual(m._channel, "T-21")
                for _ in range(3):
                    await asyncio.sleep(CHANNEL_IDLE_S - 10.0)
                    m.exchange.said("T-21")                                  # (the Captain spoke to them: his words went out)
                self.assertEqual([c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"], [])
                r.game.push({"type": "event", "text": "comms: channel closed", "report": False})
                await asyncio.sleep(0.5)
                self.assertEqual(m._channel, "")
                await asyncio.sleep(CHANNEL_IDLE_S * 2)
                self.assertEqual([c for _, k, c in r.game.rec.events if k == "json" and c.get("type") == "command"], [], "closed already: nothing to close")
        run(go())

    def test_the_router_knows_what_is_ours_and_never_goes_out(self) -> None:
        from astra_mind import router
        for needle in ("the boats (the Kestrels)", "the marines and the Marine Detachment", "the transporter", "\"where can I find...\"", "never\nsaid to {party}"):
            self.assertIn(needle, router.PROMPT)

    def test_it_is_not_closed_while_the_captain_is_talking(self) -> None:
        from astra_mind.server import CHANNEL_IDLE_S
        from .voci3_battle import LiveGame

        async def go() -> None:
            rep = Replay()
            rep.game = LiveGame()
            async with rep as r, virtual_monotonic():
                m = r.mind
                asyncio.create_task(m.channel_watch())
                r.game.push({"type": "ship_state", "state": self.STATE})
                await asyncio.sleep(0.5)
                m._channel_opened("T-40")
                await asyncio.sleep(CHANNEL_IDLE_S + 2.0)
                m.captain_t = asyncio.get_running_loop().time()              # (he is speaking right now)
                await asyncio.sleep(6.0)
                self.assertEqual(m._channel, "T-40")
                await asyncio.sleep(8.0)
                self.assertEqual(m._channel, "")
        run(go())


class TestListenerAsk(unittest.TestCase):
    """The first live runs (voci3_live): with the general ask first («report it») the listeners read routine traffic aloud in half the runs; with the listener's doctrine alone
    they log it every time, and tell what is urgent, what calls the Captain, a pilot or a marine down. So a turn of net traffic alone is asked by the doctrine alone."""

    TRAFFIC = nets_mod.NET_EVENT + "traffic on the flight net — 1 line the Captain has NOT heard. Price has the watch on this net:\n - 1 s ago · Hex: «Alpha rearmed.»"

    def test_traffic_alone_is_asked_by_the_listeners_doctrine_alone(self) -> None:
        ask = agent_mod.net_ask([self.TRAFFIC])
        self.assertEqual(ask, agent_mod.NET_ASK)
        self.assertNotIn("NEWS (the events above", ask)
        for needle in ("TELL HIM", "LOG IT", "console_log", "NO `speak`", "[URGENT]"):
            self.assertIn(needle, ask)

    def test_traffic_with_other_news_has_the_general_ask_too(self) -> None:
        ask = agent_mod.net_ask([self.TRAFFIC, "sensors: second contact detected"])
        self.assertTrue(ask.startswith(agent_mod.EVENT_ASK))
        self.assertTrue(ask.endswith(agent_mod.NET_ASK))

    DISTRESS = "comms: distress call from the freighter Open Hand (Karst Haulage) — 2 hostile warships 11 km off her and closing; she is running blind. She is at 41 km from us"

    def test_calls_of_the_system_to_communications_have_their_own_ask_alone(self) -> None:
        self.assertTrue(agent_mod.system_calls_only([self.DISTRESS, "comms: fleet net news — a convoy is under way"]))
        self.assertFalse(agent_mod.system_calls_only([self.DISTRESS, "sensors: new contact"]))
        self.assertFalse(agent_mod.system_calls_only([]))
        for needle in ("THE FIRST of its kind", "ANY LATER ONE", "NO `speak`", "ONE grouped line", "NOT an alarm", "Nobody else says it"):
            self.assertIn(needle, agent_mod.SYSTEM_CALL_ASK)

    def test_the_turn_worker_asks_a_distress_call_that_way(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                r.game.push({"type": "event", "text": self.DISTRESS, "report": True})
                await r.settle(3.0)
                asked = [str(k["messages"][-1]["content"]) for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]
                self.assertEqual(len(asked), 1)
                self.assertIn("SYSTEM CALL (the «comms:» event above)", asked[0])
                self.assertNotIn("NEWS (the events above", asked[0])
        run(go())

    def test_the_turn_worker_asks_a_listener_that_way(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                await r.mind.turns.put(("\x00event:" + self.TRAFFIC, "it"))
                await r.settle(3.0)
                asked = [str(k["messages"][-1]["content"]) for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]
                self.assertEqual(len(asked), 1)
                self.assertIn("NET TRAFFIC (the «net:» event above)", asked[0])
                self.assertNotIn("NEWS (the events above", asked[0])
        run(go())


class TestWhatTheCaptainsWordsDoNotLose(unittest.TestCase):
    """When the Captain's words take the floor, the news waiting for a quiet bridge stays in the ship's state; a warning of danger, and a call to him on a net, are not lost to
    the gap between the news and the turn: they are told after his order (5 October: the 0.6 s to 3 s the turn worker waits for a warning to gather what comes with it)."""

    CALL = (f"{nets_mod.NET_EVENT}traffic on the fleet net — 1 line the Captain has NOT heard. Comms has the watch on this net:\n"
            f" - 1 s ago · Rourke{nets_mod.CALL_MARK}: «Aquila, report your status.»")
    ROUTINE = (f"{nets_mod.NET_EVENT}traffic on the flight net — 1 line the Captain has NOT heard. Price has the watch on this net:\n"
               " - 1 s ago · Hex: «Alpha rearmed.»")

    def test_a_call_to_him_on_a_net_and_a_warning_are_told_after_his_order_and_routine_news_is_not(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                m = r.mind
                await m.voice.say("engineering", LONG, "it", "calm")                           # (the bridge is busy: the news waits for it to fall quiet)
                await m.turns.put(("\x00event:" + self.CALL, "it"))
                await m.turns.put(("\x00event:" + self.ROUTINE, "it"))
                await m.turns.put(("\x00event:tactical: missiles inbound, bearing 270", "it"))
                await m.turns.put(("\x00event:sensors: second contact detected, bearing 180, range 60 km", "it"))
                await asyncio.sleep(0.5)
                r.game.push({"type": "player_text", "text": "Timoniere, prua sul Cocytus e tienila lì", "lang": "it"})
                await asyncio.sleep(0.3)
                await r.settle(3.0, limit=120.0)
                asked = [str(k["messages"][-1]["content"]) for k in seen]
                told = [a for a in asked if "Rourke and calls the Captain" in a]
                self.assertTrue(told, "the call to the Captain was lost to his order")
                self.assertTrue(any("missiles inbound" in a.split("[Ship systems event")[-1] for a in asked), "the warning of danger was lost to his order")
                self.assertFalse(any("Alpha rearmed" in a.split("[Ship systems event")[-1] for a in asked if "[Ship systems event" in a), "routine traffic is on the logs, not a turn")
                self.assertFalse(any("second contact" in a.split("[Ship systems event")[-1] for a in asked if "[Ship systems event" in a), "plain news stays in the state")
                tr = r.trace()
                ack = [i for i in tr.order() if tr.line[i]["priority"] == "answer"]
                self.assertTrue(ack, "the order was never answered")
                first = next(a for a in asked if "Captain: Timoniere" in a or "[Ship systems event" in a)
                self.assertIn("Captain: Timoniere", first, "his order is the first turn: the news waits behind it")
        run(go())


class TestCommandWheel(unittest.TestCase):
    """The lead's request (command wheel, hold G): an order the Captain gives without a word reaches the minds as a news item «bridge: the Captain gave an order from his command
    wheel, without a word: …». It IS his order: the officer at that station acknowledges it in a word or two, at once and first, nobody else speaks about it, and nobody carries it
    out again (the console did)."""

    def test_the_doctrine_teaches_it_in_the_rules_and_in_the_turns_ask(self) -> None:
        prompt = crew_mod.system_prompt("en", {"stations": {}}, [])
        self.assertIn("The command wheel", prompt)
        self.assertIn(crew_mod.WHEEL_EVENT.split(":", 1)[1].strip(), prompt)
        self.assertIn("ALREADY carried it out", prompt)
        self.assertIn("nobody else says anything about it", prompt)
        for needle in ("HIS ORDER", "WHO: ONE officer", "Nobody else says anything", "HOW: two to five words", "no question about whether he meant it", "UNLESS", "did not go through"):
            self.assertIn(needle, agent_mod.WHEEL_ASK)

    def test_the_turn_can_only_speak_and_carries_no_standing_orders(self) -> None:
        c = Crew(Script(calls=[speak("Aye, helm.", "helm")]))
        c.agent.standing = [{"department": "tactical", "order": "weapons free on hostiles inside 40 km"}]
        asyncio.run(c.agent.handle_event(WHEEL + "Helm: come to heading 090 (heading 090 set)", "en", ask=agent_mod.WHEEL_ASK, speak_only=True))
        req = c.llm.requests[0]
        self.assertEqual({t["function"]["name"] for t in req["tools"]}, {"speak"})
        ask = req["messages"][-1]["content"]
        self.assertIn("THE COMMAND WHEEL", ask)
        self.assertNotIn("Standing orders in force", ask)
        self.assertEqual(c.said, [("helm", "Aye, helm.")])

    def test_it_is_kept_in_the_talk_as_the_captains_own_order(self) -> None:
        c = Crew(Script(calls=[speak("Aye, helm.", "helm")]))
        asyncio.run(c.agent.handle_event(WHEEL + "Helm: come to heading 090 (heading 090 set)", "en", ask=agent_mod.WHEEL_ASK, speak_only=True))
        said = "; ".join(m["content"] for m in c.agent.history if m.get("role") == "user")
        self.assertIn("command wheel", said)
        self.assertEqual(initiative_mod.recent_orders(c.agent.history), '"(from his command wheel, no words) Helm: come to heading 090 (heading 090 set)"')
        self.assertEqual(initiative_mod.recent_orders([{"role": "user", "content": "Captain: fuoco sul Cocytus"}] + c.agent.history),
                         '"fuoco sul Cocytus"; "(from his command wheel, no words) Helm: come to heading 090 (heading 090 set)"')

    def test_the_watch_does_not_take_the_captains_own_order_for_news(self) -> None:
        w = initiative_mod.Watch()
        w.note(WHEEL + "Tactical: fire on T-22 (target lost, solution complete)")
        self.assertEqual(w._events, [])
        w.note("sensors: T-22 destroyed")
        self.assertEqual(len(w._events), 1)

    def test_the_other_nets_do_not_take_it_either(self) -> None:
        from astra_mind import flight_minds, marines, transporter
        text = WHEEL + "Flight: launch Alpha squadron (Alpha launching; marines and the Chief of the Deck standing by on the transporter pad)"
        self.assertIsNone(flight_minds.classify(text))
        self.assertIsNone(marines.classify(text))
        self.assertFalse(transporter.is_news(text))

    def test_an_order_from_the_wheel_is_acknowledged_first_and_alone_on_a_busy_bridge(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {"[A]": (0.9, "helm", "Timoniere: agli ordini.")})
                v = r.mind.voice
                await v.say("engineering", LONG + " " + LONG, "it", "calm")                  # (a long report is being said, and more waits behind it)
                await v.say("sensors", "Sensori: secondo rapporto, in coda.", "it", "calm")
                await asyncio.sleep(1.0)
                t_order = asyncio.get_running_loop().time()
                r.game.push({"type": "event", "text": WHEEL + "Helm: come to heading 090 (heading 090 set) [A]", "report": True})
                await r.settle(2.0)
                tr = r.trace()
                acks = [i for i in tr.order() if tr.line[i]["speaker"] == "helm"]
                self.assertEqual(len(acks), 1, "one acknowledgement, from the officer at the station")
                a = acks[0]
                self.assertEqual(tr.line[a]["priority"], "answer", "it is the answer to the Captain's order")
                self.assertLess(tr.begin[a] - t_order, 2.6, "heard within the model's time and a breath")
                self.assertTrue(all(tr.line[i]["speaker"] in ("engineering", "sensors", "helm") for i in tr.order()), [tr.line[i]["speaker"] for i in tr.order()])
                waited = [i for i in tr.order() if tr.line[i]["speaker"] == "sensors"]
                self.assertTrue(waited and tr.begin[waited[0]] > tr.begin[a], "what waited behind the busy bridge still comes after the acknowledgement")
                turns = [k for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]
                self.assertEqual(len(turns), 1, "no other turn was made for the Captain's own order")
                self.assertIn("THE COMMAND WHEEL", str(turns[0]["messages"][-1]["content"]))
                self.assertEqual({x["function"]["name"] for x in turns[0]["tools"]}, {"speak"})
        run(go())

    def test_it_does_not_wait_for_the_bridge_to_fall_quiet_or_join_the_news(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {"[A]": (0.9, "tactical", "Tattico: fuoco libero.")})
                v = r.mind.voice
                await v.say("engineering", "Captain, all decks report ready. Engineering confirms the reactor is holding at ninety percent.", "it", "calm")   # (six seconds of speech)
                r.game.push({"type": "event", "text": "sensors: hostile contact T-22 detected, bearing 090, range 90 km", "report": True})     # (the news waits for the bridge to fall quiet)
                await asyncio.sleep(2.0)
                t_order = asyncio.get_running_loop().time()
                r.game.push({"type": "event", "text": WHEEL + "Tactical: weapons free (free to engage T-22) [A]", "report": True})
                await r.settle(3.0, limit=120.0)
                tr = r.trace()
                tac = [i for i in tr.order() if tr.line[i]["speaker"] == "tactical"]
                sen = [i for i in tr.order() if tr.line[i]["speaker"] == "sensors"]
                self.assertTrue(tac, "the acknowledgement was never heard")
                self.assertLess(tr.begin[tac[0]] - t_order, 2.6)
                self.assertTrue(sen, "the news was lost behind the order")
                events = [event_line(k) for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]
                self.assertEqual(len(events), 2, events)
                self.assertTrue(any(e.startswith(crew_mod.WHEEL_EVENT) and "hostile contact" not in e and " | " not in e for e in events), "the order was joined to the news")
        run(go())

    def test_two_orders_in_a_moment_are_acknowledged_by_their_own_officers(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {"[A]": (0.8, "helm", "Timoniere: agli ordini."), "[B]": (0.9, "xo", "XO: allarme rosso.")})
                r.game.push({"type": "event", "text": WHEEL + "Helm: come to heading 090 [A]", "report": True})
                r.game.push({"type": "event", "text": WHEEL + "the alert: red [B]", "report": True})
                await asyncio.sleep(0.2)
                await r.settle(2.0)
                tr = r.trace()
                who = [tr.line[i]["speaker"] for i in tr.order()]
                self.assertEqual(sorted(who), ["helm", "xo"], who)
                self.assertTrue(all(tr.line[i]["priority"] == "answer" for i in tr.order()))
                self.assertEqual(len([k for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]), 2)
        run(go())

    def test_a_game_that_does_not_ask_for_a_report_gets_none(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {"[A]": (0.8, "helm", "Timoniere: agli ordini.")})
                r.game.push({"type": "event", "text": WHEEL + "Helm: come to heading 090 [A]", "report": False})
                await asyncio.sleep(0.2)
                await r.settle(2.0)
                self.assertEqual(r.trace().order(), [])
                self.assertEqual([k for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])], [])
        run(go())


if __name__ == "__main__":
    unittest.main()
