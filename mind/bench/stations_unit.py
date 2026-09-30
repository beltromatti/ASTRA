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
import time
import unittest
from dataclasses import dataclass, field
from typing import Any

from astra_mind import initiative, models, router, stations as S
from astra_mind.agent import BridgeAgent, is_bare_ack, _tighten
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
        state["stations"]["helm"]["modes"] = ["hold", "intercept"]
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
        lane = c.ship.lane("helm", "nav")
        self.assertEqual((lane["mode"], lane["params"]["target"], lane["set_by"]), ("intercept", "T-23", "helm"))
        self.assertEqual(lane["until"], "target_lost")
        self.assertEqual([t for _, t in c.said], ["Intercetto il Cocytus, tengo sei chilometri."])
        self.assertTrue(turn.actions[0][2]["ok"])
        # the history keeps the call and its result in the native format (the model must know what was set)
        self.assertTrue(any(m.get("tool_calls") and m["tool_calls"][0]["function"]["name"] == "station" for m in c.agent.history))

    async def test_a_bad_station_call_is_refused_and_the_officer_says_why(self) -> None:
        c = Crew(Script([station("helm", "intercept")]),                                        # no target
                 Script([speak("Non ho un bersaglio, Capitano: quale contatto?")]))          # the follow-up
        turn = await c.agent.handle("intercettalo", "it")
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertEqual(c.ship.lane("helm", "nav")["mode"], "hold")                          # nothing changed
        self.assertEqual(len(c.llm.requests), 2)                                              # the follow-up ran
        self.assertIn("FAILED", json.dumps(c.llm.requests[1]["messages"]))
        self.assertEqual(len(c.said), 1)

    async def test_a_bare_aye_is_never_voiced_the_readback_takes_its_place(self) -> None:
        c = Crew(Script([speak("Agli ordini, Capitano.", "tactical"), station("tactical", "engage", targets=["T-23"])]),
                 Script([speak("Fuoco continuo sul Cocytus fino a distruzione.", "tactical")]))
        turn = await c.agent.handle("fuoco sul cocytus", "it")
        self.assertEqual([t for _, t in c.said], ["Fuoco continuo sul Cocytus fino a distruzione."])
        self.assertEqual(turn.dropped, ["Agli ordini, Capitano."])
        # and the history does not teach the model to say it
        self.assertNotIn("Agli ordini", json.dumps(c.agent.history))

    async def test_a_plain_yes_to_a_question_is_kept(self) -> None:
        c = Crew(Script([speak("Sì, Capitano.", "tactical")]))
        await c.agent.handle("siamo in raggio?", "it")
        self.assertEqual([t for _, t in c.said], ["Sì, Capitano."])

    async def test_a_fight_full_of_checks_does_not_push_the_captains_orders_out_of_the_history(self) -> None:
        c = Crew(*[Script([speak(f"Ordine {i} eseguito, Capitano.", "helm")]) for i in range(3)], *[Script([speak(f"Controllo {i}.", "tactical")]) for i in range(20)])
        for i in range(3):
            await c.agent.handle(f"ordine {i}", "it")
        for i in range(20):
            await c.agent.handle_event(f"tactical: something {i}", "it")
        said = [m["content"] for m in c.agent.history if m["role"] == "user"]
        self.assertEqual(sum(1 for m in said if m.startswith("Captain:")), 3)                      # all three orders are still there
        self.assertLessEqual(sum(1 for m in said if not m.startswith("Captain:")), 6)             # the checks are capped

    async def test_a_mode_name_in_a_line_is_spoken_as_plain_words(self) -> None:
        c = Crew(Script([speak("Propongo keep_on_bow su T-24 e scan_focus su T-31.", "helm")]))
        await c.agent.handle("consigli?", "it")
        self.assertEqual(c.said[0][1], "Propongo prua sul bersaglio su T-24 e scansione mirata su T-31.")

    async def test_runaway_lines_are_cut(self) -> None:
        long = "Capitano, la situazione è la seguente. " + " ".join(["parola"] * 80) + ". Poi ancora altro."
        self.assertLessEqual(len(_tighten(long).split()), 70)
        c = Crew(Script([speak(long, "xo")]))
        await c.agent.handle("rapporto", "it")
        self.assertLessEqual(len(c.said[0][1].split()), 70)

    def test_bare_acks_in_five_languages(self) -> None:
        for line in ("Aye aye, Captain.", "Agli ordini, Capitano.", "Ricevuto.", "Sì, signore.", "A sus órdenes, Capitán.", "Reçu.",
                     "À vos ordres, Capitaine.", "Zu Befehl, Kapitän.", "Understood.", "Eseguo."):
            self.assertTrue(is_bare_ack(line), line)
        for line in ("Intercetto il Cocytus, tengo sei chilometri.", "Scudi a prua, novanta per cento.", "Aye, Captain: shields fore.",
                     "Sì, Capitano: siamo a nove chilometri."):
            self.assertFalse(is_bare_ack(line), line)

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
        self.assertEqual((lane["mode"], lane["set_by"]), ("engage", "tactical"))

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

    async def test_preempted_captain_turn_keeps_what_had_gone_out(self) -> None:
        # the helm call went out, the model was still writing the read-back when the Captain spoke again
        c = Crew(Script([station("helm", "keep_on_bow", target="T-23"), speak("Prua sul Cocytus.", "helm")], between=0.4))
        task = asyncio.create_task(c.agent.handle("tienilo di prua", "it"))
        await asyncio.sleep(0.15)
        c.agent.preempt()
        turn = await task
        self.assertTrue(turn.cancelled)
        self.assertEqual(c.ship.lane("helm", "nav")["mode"], "keep_on_bow")                 # it was done
        self.assertEqual(c.said, [])                                                       # nothing was said
        self.assertTrue(any(m.get("tool_calls") for m in c.agent.history))                   # and the crew remembers doing it
        self.assertFalse(c.agent.busy())

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

    async def test_chatter_only_talks_and_is_capped_at_two_lines(self) -> None:
        c = Crew(Script([speak("Bel cielo stasera, Marco.", "sensors"), speak("Bugiardo: piove polvere.", "helm"),
                         speak("Una terza battuta.", "xo"), station("helm", "hold")]), fight=False)
        system = __import__("astra_mind.initiative", fromlist=["x"]).chatter_system("it", "steady", "", "", "", [], [])
        await c.agent.handle_event("bridge: a quiet moment on watch", "it", ask="chat", role="chatter", system=system,
                                   history_turns=2, max_lines=2, speak_only=True)
        self.assertEqual([t for _, t in c.said], ["Bel cielo stasera, Marco.", "Bugiardo: piove polvere."])
        self.assertEqual({t["function"]["name"] for t in c.llm.requests[0]["tools"]}, {"speak"})
        self.assertEqual(c.ship.lane("helm", "nav")["set_by"], "auto")                     # the stray station call did nothing
        self.assertLess(len(c.llm.requests[0]["messages"][0]["content"]) // 4, 1600)      # a compact prompt of its own

    async def test_an_older_game_build_still_works(self) -> None:
        c = Crew(Script([("intercept", {"contact_id": "T-23", "standoff_km": 6}), speak("Intercetto il Cocytus a sei chilometri.")]),
                 stations=False)
        turn = await c.agent.handle("intercettalo", "it")
        self.assertTrue(turn.actions[0][2]["ok"])
        self.assertIn("intercepting", c.ship.snapshot().get("helm", ""))
        # and the prompt it was given has no console board
        self.assertNotIn("Consoles now", c.llm.requests[0]["messages"][0]["content"])

    async def test_the_prompt_carries_the_board_and_the_room(self) -> None:
        c = Crew(Script([speak("Sì.", "xo")]))
        ctx = Context(place="mess", facing="mess3", channel=Channel(party="T-23", name="Ferryman Vael", muted=True))
        await c.agent.handle("come va", "it", ctx=ctx)
        sysmsg = c.llm.requests[0]["messages"][0]["content"]
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


class RouterTest(unittest.TestCase):
    def ctx(self, **kw: Any) -> Context:
        return Context(channel=Channel(party="T-23", name="Ferryman Irina Vael (the Cocytus)", **kw))

    def test_the_two_playtest_misroutes(self) -> None:
        for text in ("rapporto armamenti", "ci sono navi nemiche", "sparate con tutto"):
            r = router.quick(text, self.ctx())
            self.assertIsNotNone(r, text)
            self.assertEqual((r.dest, r.external), ("crew", ""), text)

    def test_words_to_the_party_go_out(self) -> None:
        r = router.quick("qui il capitano dell'aquila, fermatevi o verrete annientati", self.ctx())
        self.assertEqual(r.dest, "external")
        self.assertEqual(r.party, "T-23")

    def test_a_mixed_utterance_is_split(self) -> None:
        r = router.quick("Ferryman, avete un minuto per arrendervi. Tattico, missili pronti sul Cocytus.", self.ctx())
        self.assertEqual(r.dest, "both")
        self.assertIn("minuto", r.external)
        self.assertIn("missili", r.crew)
        self.assertEqual(r.addressed, ("tactical",))

    def test_no_channel_or_muted_everything_stays_aboard(self) -> None:
        self.assertEqual(router.quick("Cocytus, arrendetevi", Context()).dest, "crew")
        self.assertEqual(router.quick("Cocytus, arrendetevi", self.ctx(muted=True)).dest, "crew")
        self.assertTrue(router.quick("Ferryman, ritiratevi subito", self.ctx(muted=True)).unsure)

    def test_facing_an_officer_names_who_answers_first(self) -> None:
        r = router.quick("portaci piu vicini", Context(facing="helm"))
        self.assertEqual(r.addressed, ("helm",))

    def test_a_reply_in_an_exchange_goes_to_the_party(self) -> None:
        self.assertEqual(router.quick("no", self.ctx(heard_s=5.0)).dest, "external")
        self.assertEqual(router.quick("scudi a poppa", self.ctx(heard_s=5.0)).dest, "crew")

    def test_what_the_rules_cannot_tell_is_left_to_the_model_not_guessed(self) -> None:
        self.assertIsNone(router.quick("ascolta cocytus non deve finire cosi", self.ctx()))

    def test_the_rules_are_fast(self) -> None:
        t0 = time.perf_counter()
        for _ in range(500):
            router.quick("Ferryman, avete un minuto per arrendervi. Tattico, missili pronti sul Cocytus.", self.ctx())
        self.assertLess((time.perf_counter() - t0) / 500 * 1000, 2.0)



class RouterModelTest(unittest.IsolatedAsyncioTestCase):
    def ctx(self) -> Context:
        return Context(channel=Channel(party="T-23", name="Ferryman Irina Vael (the Cocytus)"))

    async def test_when_the_model_does_not_answer_the_words_stay_aboard(self) -> None:
        llm = FakeLLM(Script(error="HTTP 500"), Script(error="HTTP 500"))
        r = await router.route(llm, "ascolta cocytus non deve finire cosi", self.ctx())
        self.assertEqual((r.dest, r.how), ("crew", "fallback"))
        self.assertTrue(r.unsure)

    async def test_the_model_settles_the_open_case(self) -> None:
        llm = FakeLLM(Script(content="party"))
        r = await router.route(llm, "ascolta cocytus non deve finire cosi", self.ctx())
        self.assertEqual((r.dest, r.how, r.party), ("external", "llm", "T-23"))

    async def test_mixed_takes_a_second_small_call_to_split(self) -> None:
        llm = FakeLLM(Script(content="mixed"), Script(content='{"crew": "missili pronti", "party": "un momento"}'))
        r = await router.route(llm, "ascolta un momento missili pronti", self.ctx())
        self.assertEqual((r.dest, r.crew, r.external), ("both", "missili pronti", "un momento"))


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
        for st, lane, default in (("helm", "nav", "hold"), ("tactical", "engagement", "return_fire"), ("ops", "viewscreen", "viewscreen_auto")):
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

    async def test_the_selectors_follow_the_tactical_target(self) -> None:
        ship = LocalShip(fight=True)
        await ship.execute("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-24"]}}, "tactical")
        res = await ship.execute("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "tactical_target"}}, "helm")
        self.assertTrue(res["ok"], res)
        before = abs(((ship.heading - ship.range_bearing(ship.contacts["T-24"])[1]) + 540) % 360 - 180)
        ship.advance(30)                                          # (the Phlegethon circles at about the ship's turn rate)
        after = abs(((ship.heading - ship.range_bearing(ship.contacts["T-24"])[1]) + 540) % 360 - 180)
        self.assertLess(after, before)
        self.assertLess(after, 40)
        self.assertIn("bow on T-24", ship.snapshot()["stations"]["helm"]["lanes"]["nav"]["status"])

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


if __name__ == "__main__":
    unittest.main()
