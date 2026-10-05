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
        seen.append(kw)
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


class TestListenerAsk(unittest.TestCase):
    """The first live runs (voci3_live): with the general ask first («report it») the listeners read routine traffic aloud in half the runs; with the listener's doctrine alone
    they log it every time, and tell what is urgent, what calls the Captain, a pilot or a marine down. So a turn of net traffic alone is asked by the doctrine alone."""

    TRAFFIC = nets_mod.NET_EVENT + "traffic on the flight net — 1 line the Captain has NOT heard. Price has the watch on this net:\n - 1 s ago · Hex: «Alpha rearmed.»"

    def test_traffic_alone_is_asked_by_the_listeners_doctrine_alone(self) -> None:
        ask = agent_mod.net_ask([self.TRAFFIC])
        self.assertEqual(ask, agent_mod.NET_ASK)
        self.assertNotIn("The Captain should hear this", ask)
        for needle in ("TELL HIM", "LOG IT", "console_log", "NO `speak`", "[URGENT]"):
            self.assertIn(needle, ask)

    def test_traffic_with_other_news_has_the_general_ask_too(self) -> None:
        ask = agent_mod.net_ask([self.TRAFFIC, "sensors: second contact detected"])
        self.assertTrue(ask.startswith(agent_mod.EVENT_ASK))
        self.assertTrue(ask.endswith(agent_mod.NET_ASK))

    def test_the_turn_worker_asks_a_listener_that_way(self) -> None:
        async def go() -> None:
            async with Replay() as r:
                seen = wheel_model(r, {})
                await r.mind.turns.put(("\x00event:" + self.TRAFFIC, "it"))
                await r.settle(3.0)
                asked = [str(k["messages"][-1]["content"]) for k in seen if "[Ship systems event" in str(k["messages"][-1]["content"])]
                self.assertEqual(len(asked), 1)
                self.assertIn("NET TRAFFIC (the «net:» event above)", asked[0])
                self.assertNotIn("The Captain should hear this", asked[0])
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
