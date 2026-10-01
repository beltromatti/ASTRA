"""The flight net in the mind's server, against a scripted game and a scripted model (no network, no cost, no voices).

    cd mind && .venv/bin/python -m unittest bench.flight_server -v

A fake game connects to the real `Mind` (its turn worker, router glue, event queue, voice stage with a fake synthesiser) and sends ship states, squadron news and the
Captain's words. What is checked: the flight net's people tell the squadron news (a radio voice with their own name) and the crew's report turn does not get it, while
everything that is not theirs (a tactical report, the Captain's own Falcon) still goes to the crew; with the net off Price reports as before; Comms opens the net with
`hail flight` (the mind keeps that channel: nothing goes to the game), the router decides what of the Captain's words goes out on it and the flight net answers and gives
the order to the console as the game's own `station` command, while the crew hears everything and is told the net is live; the net is live in a cockpit and not on the
bridge; a Captain's reply to a call on the net reaches it; Price's lines are heard by the net; a net that cannot answer hands the Captain's words to Price; and a defect in
the net never cuts the crew off from the ship."""
from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any
from unittest import mock

from astra_mind import flight_minds as fm
from astra_mind import models
from astra_mind.openrouter import Completion, ToolCall
from bench.flight_unit import FLYING, LOSS, RECOVERED, WING, ship_state
from bench.stations_server import FakeGame, FakeTTS, Model as BaseModel

models.LEDGER.write_file = False


class Model(BaseModel):
    """The stations' scripted model, plus the flight net's: its calls carry `say` and `mission` (and `stay_quiet`, except in a look that holds news to be called), and a script answers them."""

    def __init__(self) -> None:
        super().__init__()
        self.flight: list[list[tuple[str, dict[str, Any]]]] = [[("stay_quiet", {"reason": "x"})]]
        self.flight_calls: list[dict[str, Any]] = []
        self.flight_error = ""
        self.router_part: tuple[str, str] | None = None          # (a phrase in the words, the part of them that goes out): comms lets out only that

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", on_tool_call=None, **kw):
        names = {t["function"]["name"] for t in (tools or [])}
        if not names and self.router_part and self.router_part[0] in str(messages[-1].get("content", "")):
            self.calls.append({"kind": "router", "model": model, "user": str(messages[-1].get("content", ""))[:160], "tools": names, "watch": False,
                               "system": str(messages[0].get("content", "")), "prompt": " ".join(str(m.get("content", "")) for m in messages)})
            out = Completion(model=model, provider="fake", cost=0.0001)
            out.content = json.dumps({"to_party": self.router_part[1]})
            return out
        if not {"say", "mission"} <= names:
            return await super().chat(model=model, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call, **kw)
        self.flight_calls.append({"model": model, "tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[-1].get("content", ""))})
        out = Completion(model=model, provider="fake", cost=0.0004)
        if self.flight_error:
            out.error = self.flight_error
            return out
        script = self.flight.pop(0) if len(self.flight) > 1 else self.flight[0]
        for i, (name, args) in enumerate(script):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"f{len(self.flight_calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out


class FlightServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        import astra_mind.server as server
        self.server = server
        self.model = Model()
        with mock.patch.object(server, "OpenRouter", lambda: self.model), mock.patch.object(server, "TTSEngine", FakeTTS):
            self.mind = server.Mind()
        self.mind.lang_file = self.mind.lang_file.parent / "captain_lang_test.txt"
        self.mind.flight.path = lambda: None                                         # (no file of the real campaign is touched)
        self.mind.npcs.talk.clear()
        self.game = FakeGame()
        self.tasks = [asyncio.create_task(self.mind.handle_client(self.game)), asyncio.create_task(self.mind.turn_worker()),
                      asyncio.create_task(self.mind.voice.run())]
        await asyncio.sleep(0.05)

    async def asyncTearDown(self) -> None:
        await self.game.inbox.put(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def state(self, st: dict[str, Any] | None = None, wait: float = 0.05) -> None:
        await self.game.push(type="ship_state", state=st or ship_state())
        await asyncio.sleep(wait)

    def later(self, seconds: float) -> None:
        """The net's clock moves (its cadence is in seconds of play: the tests do not wait for them)."""
        moved = self.mind.flight.clock() + seconds
        self.mind.flight.clock = lambda: moved

    def crew_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.model.calls if c["kind"] == "crew"]

    async def event(self, text: str, report: bool = True, st: dict[str, Any] | None = None) -> None:
        await self.state(st)
        await self.game.push(type="event", text=text, report=report)
        await asyncio.sleep(0.05)
        self.later(fm.SETTLE_S + 0.5)
        await self.state(st, 0.3)

    # -- the squadron news
    async def test_the_leader_tells_the_losses_and_price_does_not_echo_them(self) -> None:
        self.model.flight = [[("say", {"speaker": "alpha_lead", "text": "Due Falcon a terra, Wick e Moth. Alpha tiene la pattuglia, quattro in volo.", "tone": "grim"})]]
        self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha ha perso due Falcon, Capitano.", "tone": "grim"})]
        await self.event(LOSS)
        await asyncio.sleep(0.3)
        line = next(m for m in self.game.sent if m.get("type") == "line")
        self.assertEqual((line["speaker"], line["name"]), ("alpha_lead", "Alpha Lead (Lieutenant Elias Calder)"))
        self.assertTrue(line["channel"])                                               # a radio voice, not an officer of the bridge
        self.assertEqual(self.crew_calls(), [])                                        # the crew's report turn never got the event
        self.assertEqual(len(self.model.flight_calls), 1)
        self.assertIn("over the radio, Alpha Lead (Lieutenant Elias Calder): Due Falcon a terra", " ".join(self.mind.game.events))
        self.assertIn(LOSS, self.mind.game.events)                                      # (it is in the crew's events all the same: it reads it, it does not say it)

    async def test_what_is_not_the_nets_still_goes_to_the_crew(self) -> None:
        self.model.crew = [("speak", {"speaker": "tactical", "text": "Tre missili in arrivo.", "tone": "urgent"})]
        await self.event("tactical: three missiles incoming")
        self.assertEqual(len(self.crew_calls()), 1)
        self.assertEqual(self.model.flight_calls, [])
        self.model.calls.clear()
        self.model.crew = [("speak", {"speaker": "flight", "text": "Eagle è a terra, Capitano: un Wasp va a prendere la capsula.", "tone": "urgent"})]
        await self.event("flight: Eagle is down — the Captain's Falcon was destroyed, the Captain ejected; a Wasp is going out for the pod")
        self.assertEqual(len(self.crew_calls()), 1)                                    # the Captain's own Falcon: Price and the XO
        self.assertEqual(self.model.flight_calls, [])                                  # (no wing, nobody to hear it on the net)

    async def test_with_the_net_off_price_reports_as_before(self) -> None:
        self.mind.flight.disabled = True
        self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha ha perso due Falcon.", "tone": "grim"})]
        await self.event(LOSS)
        self.assertEqual(len(self.crew_calls()), 1)
        self.assertEqual(self.model.flight_calls, [])
        self.assertIn(("flight", "Alpha ha perso due Falcon."), self.game.lines())

    async def test_the_recovery_is_the_chiefs_and_the_gap_keeps_the_net_from_chattering(self) -> None:
        self.model.flight = [[("say", {"speaker": "deck_chief", "text": "Alpha a bordo, sei su otto. Riarmo in sessanta secondi.", "tone": "calm"})]]
        await self.event(RECOVERED)
        self.assertEqual([s for s, _ in self.game.lines()], ["deck_chief"])
        await self.event("flight: bravo squadron rearmed, 7 Hammers ready on the flight deck")        # seconds later: too soon for another look
        self.assertEqual(len(self.model.flight_calls), 1)
        self.later(fm.MIN_GAP_S)
        await self.state(None, 0.3)
        self.assertEqual(len(self.model.flight_calls), 2)

    async def test_price_is_heard_on_the_net(self) -> None:
        self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha, pattuglia attorno all'Aquila.", "tone": "focused"})]
        await self.state()
        await self.game.push(type="player_text", text="Price, Alpha in pattuglia")
        await asyncio.sleep(0.6)
        self.assertIn("Price (Flight Control): Alpha, pattuglia attorno all'Aquila.", self.mind.flight._recall())

    # -- the Captain talks to them
    async def test_comms_opens_the_net_and_the_captain_is_answered_and_obeyed(self) -> None:
        self.model.crew = [("hail", {"contact_id": "flight", "intent": "report", "message": "Alpha Lead, this is Aquila: cover the Vigilant."}),
                           ("speak", {"speaker": "comms", "text": "Canale di volo aperto, Capitano.", "tone": "calm"})]
        self.model.flight = [[("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "escort", "target": "T-02", "reason": "cover the Vigilant"}),
                              ("say", {"speaker": "alpha_lead", "text": "Copiato, Alpha scorta il Vigilant.", "tone": "focused"})]]
        await self.state()
        await self.game.push(type="player_text", text="Martin, apri il canale di volo e dì ad Alpha Lead di coprire il Vigilant")
        await asyncio.sleep(0.9)
        self.assertTrue(self.mind.flight.net_open)
        self.assertEqual([m["name"] for m in self.game.commands if m["name"] == "hail"], [])      # the net is the mind's channel: the game never heard of it
        orders = [m for m in self.game.commands if m["name"] == "station"]
        self.assertEqual(len(orders), 1)
        self.assertEqual((orders[0]["args"]["aspect"], orders[0]["args"]["mode"], orders[0]["args"]["params"], orders[0]["args"]["by"]),
                         ("alpha", "escort", {"squadron": "alpha", "target": "T-02"}, "captain"))
        self.assertIn(("alpha_lead", "Copiato, Alpha scorta il Vigilant."), self.game.lines())
        self.assertIn(("comms", "Canale di volo aperto, Capitano."), self.game.lines())
        reply = next(m for m in self.game.sent if m.get("type") == "line" and m["speaker"] == "alpha_lead")
        self.assertTrue(reply["answer"])                                              # an answer to the Captain: first on the stage

    async def test_words_that_went_out_on_the_net_whole_need_no_turn_for_the_bridge(self) -> None:
        self.mind.flight.open_net()
        self.model.router_says = {"Alpha Lead": "party", "Helm": "crew"}
        self.model.crew = [("speak", {"speaker": "flight", "text": "Non dovrei parlare.", "tone": "calm"})]
        self.model.flight = [[("mission", {"by": "alpha_lead", "squadron": "alpha", "type": "cap", "reason": "back on patrol"}),
                              ("say", {"speaker": "alpha_lead", "text": "Alpha torna in pattuglia.", "tone": "calm"})]]
        await self.state()
        await self.game.push(type="player_text", text="Alpha Lead, torna in pattuglia attorno all'Aquila")
        await asyncio.sleep(0.9)
        self.assertEqual(len([c for c in self.model.calls if c["kind"] == "router"]), 1)      # comms decided first (a call of a fraction of a second)
        self.assertEqual(self.crew_calls(), [])                                                # every word went out: nothing is left for the bridge, no model call to say nothing
        self.assertIn(("alpha_lead", "Alpha torna in pattuglia."), self.game.lines())
        self.assertNotIn(("flight", "Non dovrei parlare."), self.game.lines())
        self.assertEqual([m["args"]["mode"] for m in self.game.commands if m["name"] == "station"], ["cap"])
        self.assertEqual(self.mind.flight.stats["captain"], 1)

    async def test_what_is_left_for_the_bridge_is_told_what_went_out(self) -> None:
        self.mind.flight.open_net()
        words = "Alpha Lead, torna in pattuglia; timoniere, prua sull'Acheron"
        self.model.router_part = ("Alpha Lead, torna in pattuglia", "Alpha Lead, torna in pattuglia")
        self.model.crew = [("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-21"}}),
                           ("speak", {"speaker": "helm", "text": "Prua sull'Acheron.", "tone": "focused"})]
        self.model.flight = [[("say", {"speaker": "alpha_lead", "text": "Alpha torna in pattuglia.", "tone": "calm"})]]
        await self.state()
        await self.game.push(type="player_text", text=words)
        await asyncio.sleep(0.9)
        self.assertEqual(len(self.crew_calls()), 1)                                    # the helm's part is the bridge's
        prompt = self.crew_calls()[0]["prompt"]
        self.assertIn("The flight net is live", prompt)
        self.assertIn("«Alpha Lead, torna in pattuglia» went out on the flight net", prompt)        # the officers are told what went out, so nobody says it again
        self.assertIn(("helm", "Prua sull'Acheron."), self.game.lines())
        self.assertIn(("alpha_lead", "Alpha torna in pattuglia."), self.game.lines())

    async def test_words_for_the_bridge_stay_on_the_bridge_with_the_net_open(self) -> None:
        self.mind.flight.open_net()
        self.model.router_says = {"Helm": "crew"}
        await self.state()
        self.game.commands.clear()
        self.model.flight_calls.clear()
        self.model.crew = [("station", {"station": "helm", "mode": "keep_on_bow", "params": {"target": "T-21"}}),
                           ("speak", {"speaker": "helm", "text": "Prua sull'Acheron.", "tone": "focused"})]
        await self.game.push(type="player_text", text="Helm, prua sull'Acheron")
        await asyncio.sleep(0.8)
        self.assertEqual(self.model.flight_calls, [])
        self.assertIn(("helm", "Prua sull'Acheron."), self.game.lines())
        self.assertNotIn("went out on the flight net", self.crew_calls()[-1]["prompt"])      # nothing went out: the crew is told nothing

    async def test_with_the_net_closed_the_captains_words_stay_with_the_crew(self) -> None:
        self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha è in pattuglia, Capitano.", "tone": "calm"})]
        await self.state()
        await self.game.push(type="player_text", text="Alpha Lead, come va?")
        await asyncio.sleep(0.8)
        self.assertEqual(self.model.flight_calls, [])
        self.assertEqual([c for c in self.model.calls if c["kind"] == "router"], [])    # no channel, no call
        self.assertNotIn("The flight net is live", self.crew_calls()[0]["prompt"])

    async def test_in_a_cockpit_the_net_is_live_and_the_wing_talks(self) -> None:
        st = ship_state(captain=FLYING)
        self.model.router_says = {"Eagle 2": "party"}
        self.model.flight = [[("say", {"speaker": "alpha_2", "text": "Eagle, qui Eagle 2: sono sulla tua ala.", "tone": "calm"})],
                             [("say", {"speaker": "alpha_2", "text": "Ricevuto, resto con te, Eagle.", "tone": "focused"})]]
        self.model.crew = []
        await self.event(WING, st=st)
        await asyncio.sleep(0.3)
        line = next(m for m in self.game.sent if m.get("type") == "line" and m["speaker"] == "alpha_2")
        self.assertEqual(line["name"], "Eagle 2 (Ensign Mina Takeda)")                  # on his wing she is Eagle 2
        self.assertEqual(self.crew_calls(), [])                                          # the wing's news is the net's
        self.game.sent.clear()
        await self.game.push(type="player_text", text="Eagle 2, resta con me", context={"place": "falcon", "pawn": "falcon", "channel": None})
        await asyncio.sleep(0.9)
        self.assertEqual([c["kind"] for c in self.model.calls if c["kind"] == "router"], ["router"])       # the Captain's words in a Falcon are judged for the net
        self.assertIn(("alpha_2", "Ricevuto, resto con te, Eagle."), self.game.lines())

    async def test_a_reply_to_a_call_on_the_net_reaches_it(self) -> None:
        self.model.flight = [[("say", {"speaker": "cag", "text": "Capitano, Alpha è a metà: la richiamo?", "tone": "tense"})],
                             [("say", {"speaker": "cag", "text": "Alpha rientra.", "tone": "calm"}), ("mission", {"by": "cag", "squadron": "alpha", "type": "recall"})]]
        self.model.router_says = {"sì": "party"}
        self.model.crew = []
        await self.event(LOSS)
        self.assertIn(("cag", "Capitano, alpha è a metà: la richiamo?".replace("alpha", "Alpha")), self.game.lines())
        await self.game.push(type="player_text", text="sì, richiamali")
        await asyncio.sleep(0.9)
        self.assertEqual([m["args"]["mode"] for m in self.game.commands if m["name"] == "station"], ["recall"])
        self.assertIn(("cag", "Alpha rientra."), self.game.lines())

    async def test_a_net_that_cannot_answer_hands_the_words_to_price(self) -> None:
        self.mind.flight.open_net()
        self.model.flight_error = "provider down"
        self.model.router_says = {"Alpha Lead": "party"}
        self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha Lead non risponde, Capitano: gli passo io l'ordine.", "tone": "calm"})]
        await self.state()
        await self.game.push(type="player_text", text="Alpha Lead, rientra subito")
        await asyncio.sleep(2.0)
        self.assertTrue(any("the Captain called the flight net and nobody there answered" in c["prompt"] for c in self.crew_calls()))
        self.assertIn(("flight", "Alpha Lead non risponde, Capitano: gli passo io l'ordine."), self.game.lines())

    async def test_end_transmission_closes_the_flight_net(self) -> None:
        self.mind.flight.open_net()
        self.model.router_says = {"chiudi": "crew"}
        self.model.crew = [("end_transmission", {}), ("speak", {"speaker": "comms", "text": "Canale chiuso.", "tone": "calm"})]
        await self.state()
        await self.game.push(type="player_text", text="Martin, chiudi il canale")
        await asyncio.sleep(0.8)
        self.assertFalse(self.mind.flight.net_open)

    # -- the session and its defects
    async def test_a_defect_in_the_net_never_cuts_the_crew_off_from_the_ship(self) -> None:
        with mock.patch.object(self.mind.flight, "feed", side_effect=RuntimeError("a bug in the flight net")):
            await self.state(ship_state(alert="red"))
            self.assertEqual(self.mind.game.state.get("alert"), "red")                  # the state still arrived
        await self.state(ship_state(), 0.1)
        self.assertFalse(self.tasks[0].done())
        with mock.patch.object(self.mind.flight, "on_event", side_effect=RuntimeError("a bug in the flight net")):
            self.model.crew = [("speak", {"speaker": "flight", "text": "Alpha è in volo.", "tone": "calm"})]
            await self.game.push(type="event", text="flight: alpha squadron airborne, 8 Falcons on CAP", report=True)
            await asyncio.sleep(0.6)
        self.assertEqual(len(self.crew_calls()), 1)                                     # the crew has the event, as before

    async def test_hello_forgets_the_last_fight(self) -> None:
        self.mind.flight.open_net()
        self.mind.flight.heard("Price (Flight Control)", "Alpha, in pattuglia.")
        await self.game.push(type="hello", client="test")
        await asyncio.sleep(0.2)
        self.assertEqual((self.mind.flight.net_open, list(self.mind.flight.log)), (False, []))

    async def test_the_aftermath_has_the_floor(self) -> None:
        self.mind.aftermath.muted = True
        self.model.crew = []
        await self.event(LOSS)
        self.assertEqual((self.model.flight_calls, self.crew_calls()), ([], []))


if __name__ == "__main__":
    unittest.main()
