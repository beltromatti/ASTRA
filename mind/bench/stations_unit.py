"""Offline tests of the crew's mind against a scripted model and the local ship (no network, no cost).

    cd mind && .venv/bin/python -m unittest bench.stations_unit -v

They check the plumbing the behaviours stand on: which tools the crew is given for which game build, that a `station` call is
validated and reaches the console, that an officer's initiative obeys the delegation and the hard limits, that a bare "aye" is
never voiced, that the Captain preempts whatever the crew was doing and a router that says "not for the crew" stops a turn
that had already started, that a failed call is retried, and that the watch keeps its cadence. The model's own judgement
(one-off or continuous, brevity...) is measured by bench/stations_scenarios.py against the real model."""
from __future__ import annotations

import asyncio
import json
import pathlib
import tempfile
import time
import unittest
import unittest.mock
from dataclasses import dataclass, field
from typing import Any

from astra_mind import initiative, models, router, stations as S
from astra_mind.agent import BridgeAgent
from astra_mind.context import Channel, Context
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tools import initiative_names, tools_for

models.LEDGER.write_file = False


@dataclass
class Script:
    """What the fake model does in one call."""
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    content: str = ""
    before: float = 0.0            # seconds before the first tool call
    between: float = 0.0           # seconds after each tool call
    error: str = ""


class FakeLLM:
    def __init__(self, *scripts: Script) -> None:
        self.scripts = list(scripts)
        self.requests: list[dict[str, Any]] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500,
                   temperature=0.3, extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None,
                   first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools, providers=providers, max_price=max_price))
        sc = self.scripts.pop(0) if self.scripts else Script()
        out = Completion(model=model, provider="fake", cost=0.001)
        if sc.before:
            await asyncio.sleep(sc.before)
        if sc.error:
            out.error = sc.error
            return out
        for i, (name, args) in enumerate(sc.calls):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"call_{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
            if sc.between:
                await asyncio.sleep(sc.between)
        out.content = sc.content
        return out


def speak(text: str, who: str = "helm", tone: str = "focused") -> tuple[str, dict[str, Any]]:
    return "speak", {"speaker": who, "text": text, "tone": tone}


def station(st: str, mode: str, **params: Any) -> tuple[str, dict[str, Any]]:
    return "station", {"station": st, "mode": mode, "params": params}


class Crew:
    """An agent with a scripted model, the local ship and a recorder of what is voiced."""

    def __init__(self, *scripts: Script, stations: bool = True, fight: bool = True) -> None:
        self.ship = LocalShip(stations=stations, fight=fight)
        self.llm = FakeLLM(*scripts)
        self.said: list[tuple[str, str]] = []

        async def say(speaker: str, text: str, lang: str, tone: str) -> None:
            self.said.append((speaker, text))
        self.agent = BridgeAgent(self.llm, self.ship, say)


class ToolsTest(unittest.TestCase):
    def test_older_build_keeps_legacy_tools(self) -> None:
        ts = tools_for(LocalShip(stations=False, fight=True).snapshot())
        self.assertFalse(ts.stations)
        self.assertIn("intercept", ts.names)
        self.assertIn("set_shields", ts.names)
        self.assertNotIn("station", ts.names)

    def test_consoles_replace_the_legacy_tools_they_supersede(self) -> None:
        ts = tools_for(LocalShip(stations=True, fight=True).snapshot())
        self.assertTrue(ts.stations)
        self.assertIn("station", ts.names)
        for gone in ("intercept", "set_course", "set_shields", "set_emcon", "holo_display", "set_radiators", "launch_squadron"):
            self.assertNotIn(gone, ts.names, gone)
        for kept in ("fire_weapons", "launch_decoys", "hail", "active_scan", "dispatch_damage_control", "cease_fire", "speak"):
            self.assertIn(kept, ts.names, kept)
        fire = next(t for t in ts.tools if t["function"]["name"] == "fire_weapons")
        self.assertIn("ONE-OFF", fire["function"]["description"])

    def test_a_build_with_only_some_consoles_keeps_the_rest_legacy(self) -> None:
        state = LocalShip(stations=True, fight=True).snapshot()
        state["stations"] = {k: v for k, v in state["stations"].items() if k in ("helm", "tactical")}
        ts = tools_for(state)
        self.assertNotIn("intercept", ts.names)             # the helm console is on line
        self.assertIn("set_emcon", ts.names)                # sensors is not: the old tool stays
        self.assertIn("launch_squadron", ts.names)
        self.assertEqual(set(ts.available), {"helm", "tactical"})

    def test_schema_lists_only_the_modes_a_build_reports(self) -> None:
        state = LocalShip(stations=True, fight=True).snapshot()
        state["stations"]["helm"]["supports"] = ["hold", "intercept"]
        ts = tools_for(state)
        station_tool = next(t for t in ts.tools if t["function"]["name"] == "station")
        modes = station_tool["function"]["parameters"]["properties"]["mode"]["enum"]
        self.assertIn("intercept", modes)
        self.assertNotIn("orbit", modes)
        self.assertIn("engage", modes)

    def test_normalize_errors_are_words_an_officer_can_use(self) -> None:
        cmd, err = S.normalize({"station": "helm", "mode": "intercept", "params": {}})
        self.assertIsNone(cmd)
        self.assertIn("target", err)
        cmd, err = S.normalize({"station": "helm", "mode": "intercept", "params": {"target": "T-23", "standoff_km": 900}})
        self.assertEqual(cmd["params"]["standoff_km"], 40)               # clamped
        cmd, err = S.normalize({"station": "tactical", "mode": "engagement.engage", "params": {"targets": "T-23"}})
        self.assertEqual(cmd["mode"], "engage")
        self.assertEqual(cmd["params"]["targets"], ["T-23"])


class CrewTest(unittest.IsolatedAsyncioTestCase):
    async def test_station_call_reaches_the_console_and_is_read_back(self) -> None:
        c = Crew(Script([station("helm", "intercept", target="T-23", standoff_km=6),
                         speak("Intercetto il Cocytus, tengo sei chilometri.")]))
        turn = await c.agent.handle("seguilo", "it")
        lane = c.ship.lane("helm", "course")
        self.assertEqual((lane["mode"], lane["params"]["target"], lane["set_by"]), ("intercept", "T-23", "captain"))
        self.assertEqual(lane["until"], "target_lost")
        sent = next(a for _, n, a, _ in c.ship.log if n == "station")                    # what the game received: its own words
        self.assertEqual((sent["station"], sent["aspect"], sent["mode"], sent["by"]), ("helm", "course", "intercept", "captain"))
        self.assertEqual(sent["params"], {"target": "T-23", "standoff_km": 6})
        self.assertEqual([t for _, t in c.said], ["Intercetto il Cocytus, tengo sei chilometri."])
        self.assertTrue(turn.actions[0][2]["ok"])
        # the history keeps the call and its result in the native format (the model must know what was set)
        self.assertTrue(any(m.get("tool_calls") and m["tool_calls"][0]["function"]["name"] == "station" for m in c.agent.history))

    async def test_the_warm_up_asks_for_one_token_and_leaves_no_trace(self) -> None:
        c = Crew(Script(content="ok"))
        dt = await c.agent.warm_up("it")
        self.assertGreaterEqual(dt, 0.0)
        self.assertEqual(len(c.llm.requests), 1)
        req = c.llm.requests[0]
        self.assertIn("station", {t["function"]["name"] for t in req["tools"]})               # (the crew's own tools: the cached head is the real one)
        self.assertTrue(req["messages"][-1]["content"].startswith("[the bridge is manned"))
        self.assertEqual((c.said, c.agent.history), ([], []))                                 # nothing said, nothing remembered

    async def test_a_bad_station_call_is_refused_and_the_officer_says_why(self) -> None:
        c = Crew(Script([station("helm", "intercept")]),                                        # no target
                 Script([speak("Non ho un bersaglio, Capitano: quale contatto?")]))          # the follow-up
        turn = await c.agent.handle("intercettalo", "it")
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertEqual(c.ship.lane("helm", "course")["mode"], "hold")                          # nothing changed
        self.assertEqual(len(c.llm.requests), 2)                                              # the follow-up ran
        self.assertIn("FAILED", json.dumps(c.llm.requests[1]["messages"]))
        self.assertEqual(len(c.said), 1)

    async def test_a_line_is_voiced_as_the_officer_said_it(self) -> None:
        # (no code rewrites, trims or holds back what an officer says: the prompt asks for plain, short, content-bearing lines)
        c = Crew(Script([speak("Agli ordini, Capitano: fuoco continuo sul Cocytus.", "tactical"), station("tactical", "engage", targets=["T-23"])]))
        await c.agent.handle("fuoco sul cocytus", "it")
        self.assertEqual([t for _, t in c.said], ["Agli ordini, Capitano: fuoco continuo sul Cocytus."])
        self.assertEqual(len(c.llm.requests), 1)                                              # it spoke and acted: no second call

    async def test_no_answer_and_nothing_done_asks_the_officers_to_answer(self) -> None:
        # the model wrote prose instead of speaking: it is not voiced; the officers are asked for their answer, with speak
        c = Crew(Script([], content="The helm should confirm the heading."), Script([speak("Prua uno-due-zero, Capitano.", "helm")]))
        await c.agent.handle("dove siamo diretti?", "it")
        self.assertEqual([t for _, t in c.said], ["Prua uno-due-zero, Capitano."])
        self.assertEqual(len(c.llm.requests), 2)
        self.assertIn("The helm should confirm the heading.", json.dumps(c.llm.requests[1]["messages"]))

    async def test_a_plain_yes_to_a_question_is_kept(self) -> None:
        c = Crew(Script([speak("Sì, Capitano.", "tactical")]))
        await c.agent.handle("siamo in raggio?", "it")
        self.assertEqual([t for _, t in c.said], ["Sì, Capitano."])

    async def test_a_fight_full_of_checks_does_not_push_the_captains_orders_out_of_the_history(self) -> None:
        c = Crew(*[Script([speak(f"Ordine {i} eseguito, Capitano.", "helm")]) for i in range(3)], *[Script([speak(f"Controllo {i}.", "tactical")]) for i in range(40)])
        for i in range(3):
            await c.agent.handle(f"ordine {i}", "it")
        prefixes = []
        for i in range(40):
            await c.agent.handle_event(f"tactical: something {i}", "it")
            prefixes.append(json.dumps(c.agent.history, ensure_ascii=False))
        # the history is append-only between cuts, and a cut only takes the oldest turns (the provider's cache keeps the unchanged prefix)
        cuts = 0
        for a, b in zip(prefixes, prefixes[1:]):
            if not b.startswith(a[:-1]):
                cuts += 1
        self.assertLessEqual(cuts, 3)
        turns = sum(1 for m in c.agent.history if m["role"] == "user")
        self.assertLessEqual(turns, 2 * (c.agent.history_turns + 6))                                # capped
        # the Captain's orders cut from the history are still known: they head the bridge now
        now = c.agent._now(c.ship.snapshot())
        for i in range(3):
            self.assertIn(f"ordine {i}", now)

    async def test_initiative_needs_auto_delegation(self) -> None:
        c = Crew(Script([station("tactical", "engage", targets=["T-24"]), speak("Cocytus giù: passo al Phlegethon.", "tactical")]))
        c.ship.delegation["tactical"] = "advise"
        turn = await c.agent.handle_event("tactical: T-23 (Cocytus) destroyed", "it")
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertIn("advise", turn.actions[0][2]["detail"])
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "return_fire")

    async def test_initiative_under_auto_sets_the_mode(self) -> None:
        c = Crew(Script([station("tactical", "engage", targets=["T-24"]), speak("Cocytus giù: passo al Phlegethon.", "tactical")]))
        turn = await c.agent.handle_event("tactical: T-23 (Cocytus) destroyed", "it")
        self.assertTrue(turn.actions[0][2]["ok"])
        lane = c.ship.lane("tactical", "engagement")
        self.assertEqual((lane["mode"], lane["set_by"]), ("engage", "officer"))

    async def test_the_hard_limits_hold_whatever_the_delegation(self) -> None:
        for st, mode, params in (("helm", "transit", {"system": "Cassia"}), ("helm", "retreat", {}), ("xo", "delegation", {"station": "tactical", "level": "auto"})):
            c = Crew(Script([station(st, mode, **params)]), Script())
            turn = await c.agent.handle_event("something happened", "it")
            self.assertFalse(turn.actions[0][2]["ok"], mode)

    async def test_a_standing_order_widens_what_a_department_may_do(self) -> None:
        c = Crew(Script([station("tactical", "weapons_free", range_km=10), speak("Fuoco libero entro dieci chilometri.", "tactical")]))
        c.agent.standing.append({"department": "tactical", "order": "Weapons free on hostiles inside 10 km"})
        turn = await c.agent.handle_event("tactical: T-24 closing to 9 km", "it")
        self.assertTrue(turn.actions[0][2]["ok"])
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "weapons_free")
        # without the order the same call needs the Captain's word ("captain" authority)
        c2 = Crew(Script([station("tactical", "weapons_free", range_km=10)]), Script())
        turn2 = await c2.agent.handle_event("tactical: T-24 closing to 9 km", "it")
        self.assertFalse(turn2.actions[0][2]["ok"])

    async def test_what_the_captain_orders_is_always_allowed(self) -> None:
        c = Crew(Script([station("helm", "retreat", toward="gate"), speak("Ritirata verso il Gate.", "helm")]))
        turn = await c.agent.handle("ritirata!", "it")
        self.assertTrue(turn.actions[0][2]["ok"])

    def test_initiative_names_by_build(self) -> None:
        old = LocalShip(stations=False, fight=True).snapshot()
        new = LocalShip(stations=True, fight=True).snapshot()
        self.assertIn("set_shields", initiative_names(old, []))
        self.assertNotIn("station", initiative_names(old, []))
        self.assertEqual(initiative_names(new, []), {"station", "launch_decoys", "dispatch_damage_control"})

    async def test_the_captain_preempts_an_event_turn(self) -> None:
        c = Crew(Script([station("ops", "viewscreen_target", target="T-23"), speak("Cocytus a schermo.", "ops")], before=5.0))
        task = asyncio.create_task(c.agent.handle_event("tactical: T-23 opens fire", "it"))
        await asyncio.sleep(0.05)
        t0 = time.perf_counter()
        self.assertEqual(c.agent.preempt(), 1)
        turn = await task
        self.assertLess(time.perf_counter() - t0, 0.5)
        self.assertTrue(turn.cancelled)
        self.assertEqual(c.said, [])
        self.assertEqual(c.ship.lane("ops", "viewscreen")["mode"], "viewscreen_auto")

    async def test_the_captain_speaking_again_keeps_his_own_order(self) -> None:
        # the helm call went out, the model was still writing the read-back when the Captain pressed the key again: his order stands
        c = Crew(Script([station("helm", "keep_on_bow", target="T-23"), speak("Prua sul Cocytus.", "helm")], between=0.4))
        task = asyncio.create_task(c.agent.handle("tienilo di prua", "it"))
        await asyncio.sleep(0.15)
        self.assertEqual(c.agent.preempt(), 0)
        turn = await task
        self.assertFalse(turn.cancelled)
        self.assertEqual(c.ship.lane("helm", "course")["mode"], "keep_on_bow")                 # it was done
        self.assertEqual(c.said, [("helm", "Prua sul Cocytus.")])                            # and read back
        self.assertFalse(c.agent.busy())

    async def test_an_order_not_yet_sent_survives_a_second_press(self) -> None:
        # 2 Oct, the user's game: "Timoniere ritirata, subito ritirata" and, two seconds later, a press that said nothing; the model had not
        # called any tool yet, the press cancelled the turn and the retreat never reached the helm
        c = Crew(Script([station("helm", "retreat", toward="gate"), speak("Ritirata verso il Gate.", "helm")], before=0.5))
        task = asyncio.create_task(c.agent.handle("timoniere ritirata, subito", "it"))
        await asyncio.sleep(0.1)
        c.agent.preempt()                                                                  # the second press
        turn = await task
        self.assertFalse(turn.cancelled)
        self.assertTrue(turn.actions and turn.actions[0][2]["ok"])
        self.assertEqual(c.ship.lane("helm", "course")["mode"], "retreat")

    async def test_the_router_says_not_for_the_crew_and_the_started_turn_does_nothing(self) -> None:
        c = Crew(Script([station("tactical", "engage", targets=["T-23"]), speak("Fuoco sul Cocytus.", "tactical")], before=0.05))
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(c.agent.handle("Cocytus, arrendetevi!", "it", gate=gate))
        await asyncio.sleep(0.2)                       # the model has answered; the words are held at the gate
        self.assertEqual(c.said, [])
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "return_fire")
        gate.set_result(False)
        turn = await task
        self.assertTrue(turn.cancelled)
        self.assertEqual(c.said, [])
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "return_fire")
        self.assertEqual(c.agent.history, [])

    async def test_the_router_says_crew_and_the_held_turn_goes_through(self) -> None:
        c = Crew(Script([station("tactical", "engage", targets=["T-23"]), speak("Fuoco continuo sul Cocytus.", "tactical")]))
        gate: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        task = asyncio.create_task(c.agent.handle("fuoco sul cocytus", "it", gate=gate))
        await asyncio.sleep(0.05)
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "return_fire")     # held
        gate.set_result(True)
        turn = await task
        self.assertEqual(c.ship.lane("tactical", "engagement")["mode"], "engage")
        self.assertEqual(len(c.said), 1)
        self.assertFalse(turn.cancelled)

    async def test_chatter_only_talks(self) -> None:
        c = Crew(Script([speak("Bel cielo stasera, Marco.", "sensors"), speak("Bugiardo: piove polvere.", "helm"),
                         station("helm", "hold")]), fight=False)
        system = __import__("astra_mind.initiative", fromlist=["x"]).chatter_system("it", "steady", "", "", "", [], [])
        await c.agent.handle_event("bridge: a quiet moment on watch", "it", ask="chat", role="chatter", system=system,
                                   history_turns=2, speak_only=True)
        self.assertEqual([t for _, t in c.said], ["Bel cielo stasera, Marco.", "Bugiardo: piove polvere."])
        self.assertEqual({t["function"]["name"] for t in c.llm.requests[0]["tools"]}, {"speak"})
        self.assertEqual(c.ship.lane("helm", "course")["set_by"], "default")                  # the stray station call did nothing
        self.assertLess(len(c.llm.requests[0]["messages"][0]["content"]) // 4, 1600)      # a compact prompt of its own

    async def test_an_older_game_build_still_works(self) -> None:
        c = Crew(Script([("intercept", {"contact_id": "T-23", "standoff_km": 6}), speak("Intercetto il Cocytus a sei chilometri.")]),
                 stations=False)
        turn = await c.agent.handle("intercettalo", "it")
        self.assertTrue(turn.actions[0][2]["ok"])
        self.assertIn("intercepting", c.ship.snapshot().get("helm", ""))
        # and the prompt it was given has no console board
        self.assertNotIn("Consoles now", " ".join(str(m.get("content", "")) for m in c.llm.requests[0]["messages"]))

    async def test_the_prompt_carries_the_board_and_the_room(self) -> None:
        c = Crew(Script([speak("Sì.", "xo")]))
        ctx = Context(place="mess", facing="mess3", channel=Channel(party="T-23", name="Ferryman Vael", muted=True))
        await c.agent.handle("come va", "it", ctx=ctx)
        sysmsg = " ".join(str(m.get("content", "")) for m in c.llm.requests[0]["messages"])     # (the board and the room come in the last message)
        self.assertNotIn("Consoles now", c.llm.requests[0]["messages"][0]["content"])           # ... not in the system prompt the cache covers
        self.assertIn("Consoles now", sysmsg)
        self.assertIn("[engagement] return_fire", sysmsg)
        self.assertIn("MUTED", sysmsg)
        self.assertIn("not on the bridge", sysmsg)


class ModelsTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_failed_call_is_tried_again_and_only_once_when_nothing_was_done(self) -> None:
        llm = FakeLLM(Script(error="HTTP 502"), Script([speak("Sì.")]))
        got: list[str] = []

        async def on_call(call: ToolCall) -> None:
            got.append(call.name)
        comp = await models.chat(llm, "crew", messages=[{"role": "user", "content": "x"}], on_tool_call=on_call)
        self.assertEqual(got, ["speak"])
        self.assertEqual(len(llm.requests), 2)
        self.assertFalse(comp.error)

    async def test_no_second_attempt_after_something_was_done(self) -> None:
        llm = FakeLLM(Script([station("helm", "hold")], error=""), Script([speak("no")]))

        async def on_call(call: ToolCall) -> None:
            pass
        await models.chat(llm, "crew", messages=[], on_tool_call=on_call)
        self.assertEqual(len(llm.requests), 1)

    async def test_a_role_whose_model_cannot_answer_hands_over_to_its_fallback(self) -> None:
        llm = FakeLLM(Script(error="HTTP 502"), Script(error="HTTP 502"), Script([speak("Capitano, i Falcon dormono.", "flight")]))
        got: list[str] = []

        async def on_call(call: ToolCall) -> None:
            got.append(call.name)
        comp = await models.chat(llm, "chatter", messages=[], on_tool_call=on_call)
        self.assertFalse(comp.error)
        self.assertEqual(got, ["speak"])
        self.assertEqual([r["model"] for r in llm.requests], [models.role("chatter").model] * 2 + [models.role("crew").model])

    async def test_every_role_carries_the_price_ceiling(self) -> None:
        llm = FakeLLM(Script([speak("Sì.")]))
        await models.chat(llm, "router", messages=[])
        self.assertEqual(llm.requests[0]["max_price"], models.CEILING)
        self.assertLessEqual(models.CEILING[0], 0.31)
        for name in models.ROLES:
            self.assertEqual(models.role(name).max_price, models.CEILING)


class RouterModelTest(unittest.IsolatedAsyncioTestCase):
    """What goes out on an open channel is the comms officer's call, made by a small model (router.for_party)."""
    def ctx(self, **kw) -> Context:
        return Context(channel=Channel(party="T-23", name="Ferryman Irina Vael (the Cocytus)", **kw))

    async def test_the_model_says_which_words_go_out(self) -> None:
        llm = FakeLLM(Script(content='{"to_party": "che cosa cercate qui"}'))
        r = await router.for_party(llm, "che cosa cercate qui", self.ctx())
        self.assertEqual((r.external, r.party, r.how), ("che cosa cercate qui", "T-23", "model"))

    async def test_a_part_or_nothing(self) -> None:
        llm = FakeLLM(Script(content='{"to_party": "un momento"}'), Script(content='{"to_party": ""}'))
        self.assertEqual((await router.for_party(llm, "ascolta un momento. Voss, missili pronti", self.ctx())).external, "un momento")
        self.assertEqual((await router.for_party(llm, "rapporto armamenti", self.ctx())).external, "")

    async def test_when_the_model_does_not_answer_nothing_goes_out(self) -> None:
        llm = FakeLLM(Script(error="HTTP 500"))
        r = await router.for_party(llm, "che cosa cercate qui", self.ctx())
        self.assertEqual(r.external, "")                                                  # (nothing goes out)

    async def test_no_channel_or_muted_no_call(self) -> None:
        llm = FakeLLM()
        self.assertEqual((await router.for_party(llm, "Cocytus, arrendetevi", Context())).how, "no_channel")
        self.assertEqual((await router.for_party(llm, "Cocytus, arrendetevi", self.ctx(muted=True))).how, "no_channel")
        self.assertEqual(llm.requests, [])


class WatchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ship = LocalShip(stations=True, fight=True)
        self.w = initiative.Watch()

    def tick(self, now: float, flags: list[str] | None = None, captain_t: float = -100.0, busy: bool = False) -> initiative.Check | None:
        return self.w.tick(self.ship.snapshot(), now, flags or [], None, captain_t, busy)

    def test_a_fight_starts_a_check_and_the_check_is_then_spaced(self) -> None:
        c = self.tick(100.0)
        self.assertIsNotNone(c)
        self.assertIn("Hostiles:", c.text)
        self.w.ran(c, True, 100.0)
        self.assertIsNone(self.tick(103.0))                       # too soon
        self.assertIsNone(self.tick(125.0))                       # nothing changed since: skipped
        self.assertGreaterEqual(self.w.skipped, 1)

    def test_a_change_of_picture_brings_the_next_check(self) -> None:
        c = self.tick(100.0)
        self.w.ran(c, True, 100.0)
        self.ship.advance(30)                                    # ranges close, the Phlegethon starts circling
        self.ship.take_reports()
        self.assertIsNotNone(self.tick(140.0))

    def test_a_significant_event_brings_one_sooner(self) -> None:
        c = self.tick(100.0)
        self.w.ran(c, False, 100.0)
        self.w.note("tactical: T-23 (Cocytus) destroyed", now=104.0)
        self.assertIsNone(self.tick(104.5))                       # the burst has not settled yet
        first = self.tick(108.0)                                  # settled (1.6 s) and past the minimum gap
        self.assertIsNotNone(first)
        self.assertTrue(first.urgent)
        self.assertIn("destroyed", first.text)

    def test_never_while_the_captain_is_speaking(self) -> None:
        self.assertIsNone(self.tick(100.0, captain_t=97.0))       # the Captain spoke 3 s ago
        self.assertIsNone(self.tick(100.0, busy=True))            # or his words are being answered
        self.assertIsNotNone(self.tick(100.0, captain_t=80.0))

    def test_no_check_in_peace(self) -> None:
        peace = LocalShip(stations=True)
        self.assertIsNone(self.w.tick(peace.snapshot(), 100.0, [], None, -100.0, False))

    def test_no_check_on_an_older_build(self) -> None:
        old = LocalShip(stations=False, fight=True)
        self.assertIsNone(self.w.tick(old.snapshot(), 100.0, [], None, -100.0, False))

    def test_the_advisor_flags_ride_in_the_same_check(self) -> None:
        c = self.tick(100.0, flags=["out of reach: the railguns wait for T-23"])
        self.assertIn("Problems the plot found", c.text)

    def test_silent_checks_relax_the_cadence(self) -> None:
        now = 100.0
        gaps = []
        for _ in range(4):
            c = self.tick(now)
            if c is None:
                now += 1
                continue
            self.w.ran(c, False, now)
            self.ship.advance(40)
            self.ship.take_reports()
            t = now
            while self.tick(t) is None and t < now + 200:
                t += 1
            gaps.append(t - now)
            now = t
        self.assertGreater(len(gaps), 1)
        self.assertGreaterEqual(gaps[-1], gaps[0])

    def test_the_watch_prompt_is_compact(self) -> None:
        state = self.ship.snapshot()
        p = initiative.watch_system("it", state, "- none", "", "")
        self.assertLess(len(p) // 4, 4200)
        self.assertIn("Consoles now", p)
        self.assertIn("[engagement]", p)


class LocalShipTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_scripted_fight_the_target_falls_and_the_modes_release_themselves(self) -> None:
        ship = LocalShip(fight=True)
        for st, mode, p in (("helm", "intercept", {"target": "T-23", "standoff_km": 8}), ("tactical", "engage", {"targets": ["T-23"]}),
                            ("ops", "viewscreen_target", {"target": "T-23", "zoom": 6})):
            res = await ship.execute("station", {"station": st, "mode": mode, "params": p}, st)
            self.assertTrue(res["ok"], res)
        ship.advance(70)
        reports = ship.take_reports()
        self.assertTrue(any("destroyed" in r for r in reports), reports)
        self.assertTrue(any(r.startswith("helm:") and "ended" in r for r in reports), reports)
        self.assertTrue(any(r.startswith("ops: viewscreen released") for r in reports), reports)
        for st, lane, default in (("helm", "course", "hold"), ("tactical", "engagement", "return_fire"), ("ops", "viewscreen", "viewscreen_auto")):
            self.assertEqual(ship.lane(st, lane)["mode"], default)

    async def test_a_new_contact_appears_as_a_bearing_and_cannot_be_engaged_until_tracked(self) -> None:
        ship = LocalShip(fight=True)
        ship.advance(45)
        self.assertTrue(any("new contact T-31" in r for r in ship.take_reports()))
        res = await ship.execute("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-31"]}}, "tactical")
        self.assertFalse(res["ok"])
        self.assertIn("bearing only", res["detail"])
        ok = await ship.execute("station", {"station": "sensors", "mode": "scan_focus", "params": {"target": "T-31"}}, "sensors")
        self.assertTrue(ok["ok"])
        ship.advance(8)
        self.assertTrue(any("T-31 identified" in r for r in ship.take_reports()))

    async def test_the_bow_follows_its_target(self) -> None:
        ship = LocalShip(fight=True)
        await ship.execute("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-24"]}}, "tactical")
        res = await ship.execute("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-24"}}, "helm")
        self.assertTrue(res["ok"], res)
        before = abs(((ship.heading - ship.range_bearing(ship.contacts["T-24"])[1]) + 540) % 360 - 180)
        ship.advance(30)                                          # (the Phlegethon circles at about the ship's turn rate)
        after = abs(((ship.heading - ship.range_bearing(ship.contacts["T-24"])[1]) + 540) % 360 - 180)
        self.assertLess(after, before)
        self.assertLess(after, 40)
        self.assertIn("bow on T-24", ship.snapshot()["stations"]["helm"]["status"])

    async def test_delegation_is_stored(self) -> None:
        ship = LocalShip(fight=True)
        res = await ship.execute("station", {"station": "xo", "mode": "delegation", "params": {"station": "tactical", "level": "advise"}}, "xo")
        self.assertTrue(res["ok"])
        self.assertEqual(ship.snapshot()["stations"]["tactical"]["delegation"], "advise")

    async def test_the_old_build_does_not_know_the_command(self) -> None:
        ship = LocalShip(stations=False, fight=True)
        res = await ship.execute("station", {"station": "helm", "mode": "hold"}, "helm")
        self.assertFalse(res["ok"])
        self.assertNotIn("stations", ship.snapshot())


# ================================================================================================ the game's own words
# What UAstraStationsSubsystem takes and reports, copied from Source/ASTRA/AstraStations.cpp as of main (Defaults(), ModeTable(),
# ModeChoices(), Enter() and the executors' reads): the aspects each station has, the modes each aspect takes, the parameters
# the code reads. If the game changes, this fixture and stations.py change together — the test below is the alarm.
GAME_ASPECTS = {
    "helm": ("course",), "tactical": ("engagement", "shields", "point_defense", "missiles"), "sensors": ("emcon", "scan"),
    "ops": ("viewscreen", "holo", "damage_control", "datapad"), "engineering": ("power", "heat", "reactor"),
    "comms": ("channel", "listen"), "flight": ("alpha", "bravo", "drones"), "xo": ("delegation",),
}
GAME_MODES = {
    "course": {"hold", "course", "intercept", "keep_on_bow", "follow", "orbit", "broadside", "evade", "retreat", "formation", "transit"},
    "engagement": {"hold_fire", "return_fire", "weapons_free", "engage"},
    "shields": {"balanced", "face_threat", "sector", "forward", "aft", "port", "starboard", "dorsal", "ventral", "shields_off"},
    "point_defense": {"protect", "pd_auto", "pd_off"}, "missiles": {"conserve", "normal", "saturate"},
    "emcon": {"silent", "restricted", "limited", "full"}, "scan": {"passive", "sweep", "focus"},
    "viewscreen": {"auto", "forward", "target", "tactical", "fleet", "comms", "damage", "sector", "off"},
    "holo": {"tactical", "sector", "ship"}, "datapad": {"push"}, "damage_control": {"auto", "priority"},
    "power": {"balanced", "combat", "evasive", "silent", "shields", "weapons", "engines", "custom"},
    "heat": {"auto", "extended", "retracted", "radiators_extended", "radiators_retracted"}, "reactor": {"normal", "battle_short"},
    "channel": {"open", "close", "mute", "unmute"}, "listen": {"all", "enemy", "fleet"},
    "alpha": {"hold", "cap", "escort", "strike", "ew", "recon", "sar", "recall"}, "bravo": {"hold", "cap", "escort", "strike", "ew", "recon", "sar", "recall"},
    "drones": {"hold", "cap", "escort", "strike", "ew", "recon", "sar", "recall"}, "delegation": {"delegation"},
}
GAME_PARAM_KEYS = {"target", "contact_id", "targets", "weapons", "fire", "standoff_km", "speed_pct", "heading_deg", "mark_deg",
                   "distance_km", "side", "slot", "radius_km", "direction", "range_km", "every_s", "zoom", "party", "page", "focus",
                   "what", "sector", "system", "squadron", "mission", "station", "delegation", "level", "face_action", "shields",
                   "weapons", "engines", "sensors", "life_support", "flight_deck"}
# a contact list and a station as the game writes them (UAstraStationsSubsystem::StationsJson)
GAME_STATIONS = {
    "helm": {"officer": "helm", "delegation": "auto", "status": "INTERCEPT T-23 at 14.2 km · heading 122 mark 0 · 310 m/s (throttle 64%)",
             "modes": {"course": {"mode": "intercept", "params": {"target": "T-23", "standoff_km": 6}, "until": "target_lost",
                                  "set_by": "captain", "for_s": 84}},
             "recent": ["course intercept: intercepting T-23"]},
    "tactical": {"officer": "tactical", "delegation": "advise", "status": "ENGAGE T-23 at 14.2 km · rails 3 · lasers 0 · VLS 96",
                 "modes": {"engagement": {"mode": "engage", "params": {"targets": ["T-23"], "fire": "sustained"}, "until": "target_lost",
                                          "set_by": "captain", "for_s": 30},
                           "shields": {"mode": "face_threat", "until": "order", "set_by": "default", "for_s": 300},
                           "point_defense": {"mode": "pd_auto", "until": "order", "set_by": "default", "for_s": 300},
                           "missiles": {"mode": "normal", "until": "order", "set_by": "default", "for_s": 300}}, "recent": []},
    "ops": {"officer": "ops", "delegation": "auto", "status": "screen target · holo tactical · damage control auto",
            "modes": {"viewscreen": {"mode": "target", "params": {"target": "T-23", "zoom": "close"}, "until": "target_lost",
                                     "set_by": "captain", "for_s": 20},
                      "holo": {"mode": "tactical", "until": "order", "set_by": "default", "for_s": 300},
                      "damage_control": {"mode": "auto", "until": "order", "set_by": "default", "for_s": 300},
                      "datapad": {"mode": "push", "until": "order", "set_by": "default", "for_s": 300}}, "recent": []},
    "comms": {"officer": "comms", "delegation": "auto", "status": "channel close · listening fleet",
              "modes": {"channel": {"mode": "close", "until": "order", "set_by": "default", "for_s": 300},
                        "listen": {"mode": "fleet", "until": "order", "set_by": "default", "for_s": 300}}, "recent": []},
    "flight": {"officer": "flight", "delegation": "auto", "status": "",
               "modes": {"alpha": {"mode": "cap", "until": "order", "set_by": "officer", "for_s": 40},
                         "bravo": {"mode": "hold", "until": "order", "set_by": "default", "for_s": 300},
                         "drones": {"mode": "hold", "until": "order", "set_by": "default", "for_s": 300}}, "recent": []},
    "engineering": {"officer": "engineering", "delegation": "auto", "status": "",
                    "modes": {"power": {"mode": "combat", "until": "order", "set_by": "captain", "for_s": 5},
                              "heat": {"mode": "auto", "until": "order", "set_by": "default", "for_s": 300},
                              "reactor": {"mode": "normal", "until": "order", "set_by": "default", "for_s": 300}}, "recent": []},
    "sensors": {"officer": "sensors", "delegation": "auto", "status": "",
                "modes": {"emcon": {"mode": "restricted", "until": "order", "set_by": "default", "for_s": 300},
                          "scan": {"mode": "focus", "params": {"target": "T-31"}, "until": "target_lost", "set_by": "officer", "for_s": 9}},
                "recent": []},
    "xo": {"officer": "xo", "delegation": "auto", "status": "", "modes": {}, "recent": []},
}


def sample_command(md: S.Mode) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for q in md.params:
        if q.required:
            params[q.name] = (q.enum[0] if q.enum else ["T-23"] if q.kind == "strings" else 10 if q.kind in ("number", "integer") else "T-23")
    if md.name == "course":
        params = {"heading_deg": 90}
    return {"station": md.station, "mode": md.name, "params": params}


class WireTest(unittest.IsolatedAsyncioTestCase):
    """The crew's commands leave in the game's words and the game's state is read in the crew's words."""

    def test_every_mode_leaves_in_words_the_game_knows(self) -> None:
        for name, md in S.MODE_INDEX.items():
            cmd, err = S.normalize(sample_command(md))
            self.assertIsNotNone(cmd, (name, err))
            w = S.to_wire(cmd, "captain")
            self.assertIn(w["aspect"], GAME_ASPECTS[w["station"]], name)
            self.assertIn(w["mode"], GAME_MODES[w["aspect"]], name)
            self.assertLessEqual(set(w["params"]), GAME_PARAM_KEYS, name)
            self.assertEqual(w["by"], "captain")

    def test_what_the_game_does_not_have_is_not_offered(self) -> None:
        for gone in ("ew_jam", "ew_off", "sigint_on", "sigint_off", "holo_fleet", "listen_off"):
            self.assertNotIn(gone, S.MODE_INDEX)
        self.assertNotIn("weapons", S.MODE_INDEX["datapad_push"].param("page").enum)
        self.assertEqual(set(S.MODE_INDEX["datapad_push"].param("page").enum), {"overview", "contact", "damage", "fleet", "orders", "log"})   # (the log: the bridge's log page, VOCI-3)

    def test_the_wire_round_trips(self) -> None:
        for name, md in S.MODE_INDEX.items():
            cmd, _ = S.normalize(sample_command(md))
            back, why = S.from_wire(S.to_wire(cmd, "officer"))
            self.assertIsNotNone(back, (name, why))
            self.assertEqual((back["mode"], back["params"]), (cmd["mode"], cmd["params"]), name)

    def test_examples_as_the_game_takes_them(self) -> None:
        def wire(st_id, mode, /, **params):
            cmd, err = S.normalize({"station": st_id, "mode": mode, "params": params})
            self.assertIsNotNone(cmd, err)
            return S.to_wire(cmd)

        w = wire("tactical", "shields_face_threat")
        self.assertEqual((w["aspect"], w["mode"]), ("shields", "face_threat"))
        w = wire("ops", "viewscreen_target", target="T-23", zoom="close")
        self.assertEqual((w["station"], w["aspect"], w["mode"], w["params"], w["until"]),
                         ("ops", "viewscreen", "target", {"target": "T-23", "zoom": "close"}, "target_lost"))
        w = wire("flight", "mission", squadron="alpha", type="strike", target="T-23")
        self.assertEqual((w["aspect"], w["mode"], w["params"]["target"]), ("alpha", "strike", "T-23"))
        w = wire("xo", "delegation", station="tactical", level="advise")
        self.assertEqual((w["station"], w["mode"], w["params"]), ("xo", "delegation", {"station": "tactical", "delegation": "advise"}))
        w = wire("engineering", "power_profile", profile="combat")
        self.assertEqual((w["aspect"], w["mode"]), ("power", "combat"))
        w = wire("engineering", "power_custom", shields_pct=130, weapons_pct=110)
        self.assertEqual((w["mode"], w["params"]), ("custom", {"shields": 130, "weapons": 110}))
        w = wire("engineering", "heat_radiators", state="extended")
        self.assertEqual((w["aspect"], w["mode"]), ("heat", "extended"))
        w = wire("sensors", "emcon", level="silent")
        self.assertEqual((w["aspect"], w["mode"]), ("emcon", "silent"))
        w = wire("tactical", "shields_sector", sector="fore")                   # ("fore" is what a sailor says: forward)
        self.assertEqual((w["aspect"], w["mode"]), ("shields", "forward"))
        w = wire("helm", "broadside", target="T-23", side="best")
        self.assertEqual(w["params"]["side"], "auto")                          # (the game's word for "the side that is nearer")
        w = wire("helm", "course", speed_pct=0)                                # all stop: the heading is the present one
        self.assertEqual((w["mode"], w["params"]), ("course", {"speed_pct": 0}))

    def test_a_course_needs_something_to_steer_or_a_speed(self) -> None:
        cmd, err = S.normalize({"station": "helm", "mode": "course", "params": {}})
        self.assertIsNone(cmd)

    def test_hostiles_and_action_go_through_as_words_the_game_keeps(self) -> None:
        cmd, _ = S.normalize({"station": "tactical", "mode": "engage", "params": {"targets": ["Hostiles"]}})
        self.assertEqual(S.to_wire(cmd)["params"]["targets"], ["hostiles"])                            # (a standing order: the game expands it every tick)
        cmd, _ = S.normalize({"station": "tactical", "mode": "engage", "params": {"targets": ["T-24", "hostiles"]}})
        self.assertEqual(S.to_wire(cmd)["params"]["targets"], ["T-24", "hostiles"])
        for st_id, mode in (("helm", "keep_on_bow"), ("ops", "viewscreen_target"), ("sensors", "scan_focus")):
            cmd, err = S.normalize({"station": st_id, "mode": mode, "params": {"target": "ACTION"}})
            self.assertEqual(cmd["params"]["target"], "action", (mode, err))
            self.assertEqual(S.to_wire(cmd)["params"]["target"], "action")
        text = S.tool_description()
        self.assertIn("`action`", text)
        self.assertIn("keep_on_bow(target=id|action, speed_pct?, standoff_km?)", text)
        self.assertIn("800%", S.MODE_INDEX["reactor_battle_short"].summary)

    def test_what_the_game_would_refuse_is_refused_the_same_way(self) -> None:
        for args in ({"station": "sensors", "aspect": "ew", "mode": "jam", "params": {"target": "T-23"}},
                     {"station": "ops", "aspect": "holo", "mode": "fleet"},
                     {"station": "warp", "mode": "hold"}, {"station": "helm", "mode": ""}):
            cmd, why = S.from_wire(args)
            self.assertIsNone(cmd, args)
            self.assertTrue(why)

    def test_a_mode_without_its_aspect_goes_where_the_games_table_puts_it(self) -> None:
        for station, mode, aspect in (("tactical", "engage", "engagement"), ("tactical", "face_threat", "shields"), ("ops", "auto", "viewscreen"),
                                      ("engineering", "auto", "heat"), ("engineering", "silent", "power"), ("sensors", "silent", "emcon"),
                                      ("comms", "mute", "channel")):
            self.assertEqual(S._aspect_for(station, mode), aspect, (station, mode))

    def test_the_games_state_is_read_in_the_crews_words(self) -> None:
        state = {"stations": GAME_STATIONS, "sim_time_s": 900.0, "viewscreen": "target: ordered, T-23 (Cocytus), zoom x8"}
        lanes = S.lanes_of(GAME_STATIONS["helm"])
        self.assertEqual((lanes["course"]["mode"], lanes["course"]["params"]["target"], lanes["course"]["set_by"]), ("intercept", "T-23", "captain"))
        self.assertEqual(S.lanes_of(GAME_STATIONS["tactical"])["shields"]["mode"], "shields_face_threat")
        self.assertEqual(S.lanes_of(GAME_STATIONS["ops"])["viewscreen"]["mode"], "viewscreen_target")
        self.assertEqual(S.lanes_of(GAME_STATIONS["flight"])["alpha"]["params"], {"squadron": "alpha", "type": "cap"})
        self.assertEqual(S.lanes_of(GAME_STATIONS["engineering"])["power"]["params"], {"profile": "combat"})
        self.assertEqual(S.lanes_of(GAME_STATIONS["sensors"])["emcon"]["params"], {"level": "restricted"})
        self.assertEqual(S.lanes_of(GAME_STATIONS["comms"])["channel"]["mode"], "close")            # (a word of the game's, kept as it is)
        self.assertEqual(S.delegation_of(state, "tactical"), "advise")
        self.assertEqual(S.available_from_state(state)["helm"], None)                                # (no list of modes: all of them)
        board = S.board(state)
        for needle in ("[course] intercept(target=T-23,standoff_km=6) until target_lost by captain, 84 s ago",
                       "delegation advise", "[viewscreen] viewscreen_target(target=T-23,zoom=close)", "[alpha] mission(squadron=alpha,type=cap)",
                       "main screen now: target: ordered, T-23", "INTERCEPT T-23 at 14.2 km"):
            self.assertIn(needle, board)
        self.assertNotIn("[datapad]", board)                                                          # (nothing pushed yet)

    def test_a_mode_of_a_newer_build_is_shown_under_the_games_name(self) -> None:
        st = {"modes": {"course": {"mode": "warp_jump", "params": {"x": 1}, "until": "order", "set_by": "captain", "for_s": 3}}}
        lane = S.lanes_of(st)["course"]
        self.assertEqual((lane["mode"], lane["params"]), ("warp_jump", {"x": 1}))
        self.assertIn("warp_jump", S.board({"stations": {"helm": st}}))

    def test_the_call_that_reaches_the_spend_cap_is_still_recorded(self) -> None:
        led = models.Ledger()
        led.write_file, led.cap = False, 0.0
        led.prior = lambda: 0.0                                                   # type: ignore[method-assign]
        comp = Completion(model="m", provider="p", cost=0.002)
        led.write_file = True
        with unittest.mock.patch.object(models, "CACHE", pathlib.Path(tempfile.mkdtemp())):
            with self.assertRaises(models.SpendCapReached):
                led.add("router", "m", comp)
            self.assertEqual((led.calls, round(led.total, 4)), (1, 0.002))                  # billed: written down, then stopped

    def test_comms_mute_mode_makes_the_channel_muted_for_the_router(self) -> None:
        from astra_mind.context import parse
        raw = {"place": "bridge", "channel": {"party": "T-23", "open": True, "muted": False}}      # (the game's own flag is always false)
        state = {"stations": {"comms": {"modes": {"channel": {"mode": "mute"}}}}}
        self.assertTrue(parse(raw, state).channel.muted)
        state["stations"]["comms"]["modes"]["channel"]["mode"] = "unmute"
        self.assertFalse(parse(raw, state).channel.muted)
        self.assertFalse(parse(raw, {}).channel.muted)

    async def test_the_local_ship_speaks_the_games_language(self) -> None:
        ship = LocalShip(fight=True)
        state = ship.snapshot()
        for sid, ss in state["stations"].items():
            self.assertEqual(set(ss), {"officer", "delegation", "status", "modes", "recent"}, sid)
            self.assertLessEqual(set(ss["modes"]), set(GAME_ASPECTS[sid]), sid)
            for aspect, m in ss["modes"].items():
                self.assertIn(m["mode"], GAME_MODES[aspect], (sid, aspect))
                self.assertLessEqual(set(m), {"mode", "params", "until", "set_by", "for_s"})
        res = await ship.execute("station", {"station": "tactical", "aspect": "shields", "mode": "forward", "params": {"sector": "forward"}, "by": "captain"}, "tactical")
        self.assertTrue(res["ok"], res)
        sh = ship.snapshot()["stations"]["tactical"]["modes"]["shields"]
        self.assertEqual((sh["mode"], sh["set_by"]), ("forward", "captain"))
        bad = await ship.execute("station", {"station": "sensors", "aspect": "ew", "mode": "jam", "params": {"target": "T-23"}}, "sensors")
        self.assertFalse(bad["ok"])

    async def test_the_helm_turns_the_bow_to_the_action_by_itself(self) -> None:
        ship = LocalShip(fight=True)
        self.assertEqual(ship.snapshot()["stations"]["helm"]["modes"]["course"]["mode"], "hold")
        ship.advance(40)
        want = ship.range_bearing(ship.contacts["T-23"])[1]
        self.assertLess(abs(((ship.heading - want) + 540) % 360 - 180), 40)

    # ---- what main's game side does since 333cb1e: "action", hostiles as a standing order, a time limit for any aspect, battle short
    async def test_the_bow_on_the_action_waits_without_a_fight_and_follows_the_fight_with_one(self) -> None:
        calm = LocalShip(fight=False)
        res = await calm.execute("station", {"station": "helm", "aspect": "course", "mode": "keep_on_bow", "params": {"target": "action"},
                                             "until": "target_lost", "by": "captain"}, "helm")
        self.assertTrue(res["ok"], res)                                                   # accepted with no fight on
        calm.advance(10)
        self.assertEqual(calm.snapshot()["stations"]["helm"]["modes"]["course"]["mode"], "keep_on_bow")         # it waits, it does not expire
        self.assertEqual(calm.snapshot()["action_target"], "")
        ship = LocalShip(fight=True)
        await ship.execute("station", {"station": "helm", "aspect": "course", "mode": "keep_on_bow", "params": {"target": "action"}, "by": "captain"}, "helm")
        self.assertEqual(ship.snapshot()["action_target"], "T-23")                       # the nearest hostile
        ship.advance(40)
        off = lambda cid: abs(((ship.heading - ship.range_bearing(ship.contacts[cid])[1]) + 540) % 360 - 180)      # noqa: E731
        self.assertLess(off("T-23"), 25)
        await ship.execute("station", {"station": "tactical", "aspect": "engagement", "mode": "engage", "params": {"targets": ["T-24"]}, "by": "captain"}, "tactical")
        ship.advance(1)
        self.assertEqual(ship.snapshot()["action_target"], "T-24")                       # tactical's target is what the fight is about
        before = off("T-24")
        ship.advance(60)
        self.assertLess(off("T-24"), before)                                             # the bow is coming round to the new target
        self.assertLess(off("T-24"), 45)

    async def test_the_screen_and_the_scan_on_the_action_follow_it_too(self) -> None:
        ship = LocalShip(fight=True)
        for st_id, aspect, mode in (("ops", "viewscreen", "target"), ("sensors", "scan", "focus")):
            res = await ship.execute("station", {"station": st_id, "aspect": aspect, "mode": mode, "params": {"target": "action"}, "by": "captain"}, st_id)
            self.assertTrue(res["ok"], res)
        self.assertIn("T-23", ship.snapshot()["viewscreen"])
        ship.advance(80)                                                                  # T-23 falls: the screen is not released, it moves on
        st = ship.snapshot()["stations"]
        self.assertEqual(st["ops"]["modes"]["viewscreen"]["mode"], "target")
        self.assertEqual(st["sensors"]["modes"]["scan"]["mode"], "focus")
        self.assertFalse(any(r.startswith("ops: viewscreen released") for r in ship.take_reports()))

    async def test_engage_hostiles_is_a_standing_order_that_outlives_the_targets(self) -> None:
        ship = LocalShip(fight=True)
        res = await ship.execute("station", {"station": "tactical", "aspect": "engagement", "mode": "engage", "params": {"targets": ["hostiles"]},
                                             "until": "target_lost", "by": "captain"}, "tactical")
        self.assertTrue(res["ok"], res)
        ship.advance(120)
        self.assertFalse(ship.contacts["T-23"].alive)                                     # the first one fell (the second circles out of reach)
        reports = ship.take_reports()
        self.assertTrue(any("engaging" in r and "was T-23" in r for r in reports), reports)         # it moved on to the next by itself
        self.assertFalse(any("ended" in r and r.startswith("tactical:") for r in reports), reports)  # and the order still stands
        self.assertEqual(ship.snapshot()["stations"]["tactical"]["modes"]["engagement"]["mode"], "engage")
        empty = LocalShip(fight=False)                                                    # nothing hostile on the plot: it waits, it is accepted
        res = await empty.execute("station", {"station": "tactical", "aspect": "engagement", "mode": "engage", "params": {"targets": ["hostiles"]}}, "tactical")
        self.assertTrue(res["ok"], res)

    async def test_a_time_limit_sends_any_aspect_back_to_its_default(self) -> None:
        ship = LocalShip(fight=True)
        await ship.execute("station", {"station": "tactical", "aspect": "shields", "mode": "forward", "params": {"sector": "forward"}, "until": "time:5"}, "tactical")
        await ship.execute("station", {"station": "engineering", "aspect": "power", "mode": "combat", "until": "time:5"}, "engineering")
        await ship.execute("station", {"station": "sensors", "aspect": "emcon", "mode": "silent", "until": "time:5"}, "sensors")
        self.assertEqual(ship.state["power_pct"]["shields"], 150)
        ship.advance(7)
        st = ship.snapshot()["stations"]
        self.assertEqual(st["tactical"]["modes"]["shields"]["mode"], "face_threat")
        self.assertEqual(st["engineering"]["modes"]["power"]["mode"], "balanced")
        self.assertEqual(st["sensors"]["modes"]["emcon"]["mode"], "restricted")
        self.assertEqual((ship.state["power_pct"]["shields"], ship.state["emcon"]), (100, "restricted"))     # the ship followed the console
        reports = ship.take_reports()
        self.assertIn("tactical: shields sector ended (the time set for it is up): back to shields face threat", reports)

    async def test_battle_short_is_800_percent_and_heat_and_normal_scales_it_back(self) -> None:
        ship = LocalShip(fight=False)
        for system, pct in (("shields", 150), ("weapons", 150)):
            self.assertTrue((await ship.execute("route_power", {"system": system, "percent": pct}, "ops"))["ok"])       # 700% of 700%
        refused = await ship.execute("route_power", {"system": "engines", "percent": 150}, "ops")
        self.assertFalse(refused["ok"])
        self.assertIn("budget exceeded", refused["detail"])
        res = await ship.execute("station", {"station": "engineering", "aspect": "reactor", "mode": "battle_short", "by": "captain"}, "engineering")
        self.assertTrue(res["ok"], res)
        self.assertIn("of 800%", ship.snapshot()["power_budget"])
        self.assertTrue((await ship.execute("route_power", {"system": "engines", "percent": 150}, "ops"))["ok"])       # 750% of 800%
        heat0 = ship.snapshot()["thermal"]["heat_pct"]
        ship.advance(60)
        self.assertGreaterEqual(ship.snapshot()["thermal"]["heat_pct"], heat0 + 17)                                  # +0.3 %/s
        await ship.execute("station", {"station": "engineering", "aspect": "reactor", "mode": "normal"}, "engineering")
        snap = ship.snapshot()
        self.assertIn("of 700%", snap["power_budget"])
        self.assertLessEqual(sum(snap["power_pct"].values()), 700.5)                                                 # the over-nominal comes down
        self.assertGreater(snap["power_pct"]["shields"], 100)
        self.assertTrue(any("back inside its limits" in e for e in ship.events))

    def test_the_watch_does_not_list_hostiles_a_standing_order_already_covers(self) -> None:
        ship = LocalShip(fight=True)
        state = ship.snapshot()
        state["stations"]["tactical"]["modes"]["engagement"] = {"mode": "engage", "params": {"targets": ["HOSTILES"]}, "until": "target_lost",
                                                                "set_by": "captain", "for_s": 5}           # (the game stores the words in capitals)
        self.assertFalse(any("no fire assigned" in d for d in initiative.Watch.due(state)))
        state["stations"]["tactical"]["modes"]["engagement"] = {"mode": "return_fire", "until": "order", "set_by": "default", "for_s": 5}
        self.assertTrue(any("no fire assigned" in d for d in initiative.Watch.due(state)))

    def test_the_board_says_what_the_action_is_now(self) -> None:
        state = LocalShip(fight=True).snapshot()
        self.assertEqual(state["action_target"], "T-23")
        self.assertIn("the action now (target `action`): T-23 (Cocytus)", S.board(state))
        calm = LocalShip(fight=False).snapshot()
        calm["stations"]["helm"]["modes"]["course"] = {"mode": "keep_on_bow", "params": {"target": "action"}, "until": "target_lost", "set_by": "captain", "for_s": 3}
        self.assertIn("none — no fight", S.board(calm))
        lane = S.lanes_of(calm["stations"]["helm"])["course"]
        self.assertEqual((lane["mode"], lane["params"]), ("keep_on_bow", {"target": "action"}))
        self.assertEqual(S.lanes_of({"modes": {"engagement": {"mode": "engage", "params": {"targets": ["HOSTILES"]}}}})["engagement"]["params"],
                         {"targets": ["hostiles"]})

    async def test_expiries_are_reported_in_the_games_words(self) -> None:
        ship = LocalShip(fight=True)
        await ship.execute("station", {"station": "helm", "aspect": "course", "mode": "keep_on_bow", "params": {"target": "T-23"}, "until": "target_lost"}, "helm")
        await ship.execute("station", {"station": "tactical", "aspect": "engagement", "mode": "engage", "params": {"targets": ["T-23"]}, "until": "target_lost"}, "tactical")
        ship.advance(80)
        reports = ship.take_reports()
        self.assertIn("helm: keep on bow ended (T-23 is no longer on the plot): back to hold", reports)
        self.assertIn("tactical: engage ended (the targets are down or gone): back to return fire", reports)


if __name__ == "__main__":
    unittest.main()
