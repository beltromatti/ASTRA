"""Offline tests of the boats' boardings in the crew's hands: the XO's tool and the rule that says how to answer, against a scripted model and a scripted ship (no network, no cost).

    cd mind && .venv/bin/python -m unittest bench.assault_unit -v

The Captain orders the Aquila's marines to board an enemy ship; the XO sends them with a real tool (`board_ship`: the game's UAstraBoardSubsystem::StartAssault flies the Kestrels from the
Deck 8 bay to a hatch on the target's hull, where the marines cut in). What is checked is the plumbing the behaviour stands on: the tool exists only in a game that reports `boarding_boats`
(the boats free and the marines fit to go), it is the XO's and takes a target, boats, a face, an objective and a number of marines, the crew's prompt says how to answer and what is the Mandate's
doing to the Aquila, a call reaches the ship as the game's own command (read from the C++ source: the game takes the name and the arguments), and a refusal of the game is read back. Nothing
in the code reads the Captain's words (docs/ARCHITETTURA.md §1bis): which ship, how many boats and what for is the model's judgement, on the facts the game gives (`boarding_options`)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from astra_mind import models
from astra_mind.agent import BridgeAgent
from astra_mind.context import parse as parse_context
from astra_mind.crew import system_prompt
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tools import SHIP_TOOL_NAMES, owner_of, tools_for

models.LEDGER.write_file = False

SRC = Path(__file__).resolve().parents[2] / "Source" / "ASTRA"
BOATS = {"kestrels_free": 2, "kestrels_in_all": 2, "marines_in_a_kestrel": 12, "bay": "the assault-shuttle bay on Deck 8 (port side)", "marines_fit_to_go": 71}
OPTIONS = {"carriers": [{"ship": "the Aquila", "id": "aquila", "boat": "kestrel", "boats_free": 2, "men_per_boat": 12}],
           "boardable_now": [{"ship": "Charon", "id": "T-30", "class": "Kharon Mandate cruiser, Acheron class", "no_power": True, "faces_open": "all (no power)", "hull_pct": 31,
                              "point_defence_channels": 0, "her_craft_about_her": 0, "distance_km": 4.1}],
           "other_enemy_ships_shielded": 1}


class BoardShip(LocalShip):
    """The local ship plus the boats: `board_ship` is the game's; here it answers like the game does and keeps what it was asked."""

    def __init__(self, with_boats: bool = True, options: bool = True) -> None:
        super().__init__(stations=True, fight=False)
        self.with_boats, self.options = with_boats, options
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def snapshot(self) -> dict[str, Any]:
        s = super().snapshot()
        if self.with_boats:
            s["boarding_boats"] = dict(BOATS)
            if self.options:
                s["boarding_options"] = json.loads(json.dumps(OPTIONS))
        return s

    def _execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        if name == "board_ship":
            self.calls.append((name, dict(a), by))
            if a.get("action") == "call_off":
                return {"ok": True, "detail": "the boarding is called off: the boats turn back or let go"}
            if not a.get("target"):
                return {"ok": False, "detail": "name the ship to board (target: her contact id or name)"}
            if str(a["target"]) != "T-30":
                return {"ok": False, "detail": f"{a['target']} cannot be boarded: she is too far for a boat"}
            return {"ok": True, "detail": "order 1: the Aquila launches 2 Kestrels (24 marines) at Charon, hatches hatch_s2 (deck 2 section C (Boarding Lock)), hatch_p2b (deck 2 section C (Boarding Lock)); "
                                          "first at the hull in about 52 s."}
        return super()._execute(name, a, by)


class FakeLLM:
    def __init__(self, *scripts: list[tuple[str, dict[str, Any]]]) -> None:
        self.scripts = list(scripts)
        self.requests: list[dict[str, Any]] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3, extra=None,
                   on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None) -> Completion:
        self.requests.append(dict(model=model, messages=messages, tools=tools))
        out = Completion(model=model, provider="fake", cost=0.0005)
        for i, (name, args) in enumerate(self.scripts.pop(0) if self.scripts else []):
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"c{len(self.requests)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        return out


def speak(text: str, who: str = "xo") -> tuple[str, dict[str, Any]]:
    return "speak", {"speaker": who, "text": text, "tone": "calm"}


class Crew:
    def __init__(self, *scripts: list[tuple[str, dict[str, Any]]], with_boats: bool = True, options: bool = True) -> None:
        self.ship = BoardShip(with_boats, options)
        self.llm = FakeLLM(*scripts)
        self.said: list[tuple[str, str]] = []

        async def say(speaker: str, text: str, lang: str, tone: str) -> None:
            self.said.append((speaker, text))
        self.agent = BridgeAgent(self.llm, self.ship, say)


class ToolTest(unittest.TestCase):
    def test_the_tool_exists_only_in_a_game_that_reports_the_boats(self) -> None:
        self.assertIn("board_ship", tools_for(BoardShip(True).snapshot()).names)
        self.assertNotIn("board_ship", tools_for(BoardShip(False).snapshot()).names)           # (an older build: no boats to send)
        self.assertIn("board_ship", tools_for(BoardShip(True, options=False).snapshot()).names)  # (the tool does not come and go with what is boardable: the game says why not)
        self.assertIn("board_ship", SHIP_TOOL_NAMES)

    def test_it_is_the_xos_and_takes_the_orders_arguments(self) -> None:
        self.assertEqual(owner_of("board_ship"), "xo")
        tool = next(t for t in tools_for(BoardShip(True).snapshot()).tools if t["function"]["name"] == "board_ship")["function"]
        props = tool["parameters"]["properties"]
        self.assertEqual(set(props), {"action", "target", "boats", "face", "objective", "marines", "captain"})
        self.assertEqual(props["captain"]["type"], "boolean")
        self.assertEqual(props["action"]["enum"], ["launch", "call_off"])
        self.assertEqual(props["face"]["enum"], ["port", "starboard", "dorsal", "ventral", "bow", "stern"])
        self.assertIn("engineering", props["objective"]["enum"])
        self.assertEqual(props["boats"]["maximum"], 2)                                         # (the Aquila has two Kestrels)
        self.assertEqual(tool["parameters"]["required"], [])
        self.assertFalse(tool["parameters"]["additionalProperties"])

    def test_the_game_takes_what_the_tool_sends(self) -> None:
        mind = (SRC / "AstraBoardMind.cpp").read_text(encoding="utf-8")
        ship = (SRC / "AstraShipSubsystem.cpp").read_text(encoding="utf-8")
        self.assertIn('Name == TEXT("board_ship")', mind)
        self.assertIn('Name == TEXT("board_ship")', ship)                                      # (forwarded to the board subsystem)
        for field in ("target", "boats", "craft", "face", "objective", "marines", "boarders", "action", "call_off", "direction"):
            self.assertIn(f'TEXT("{field}")', mind, field)
        self.assertIn('SetObjectField(TEXT("boarding_boats")', ship)                           # the marker the tool and the rule stand on
        self.assertIn('SetObjectField(TEXT("boarding_options")', ship)

    def test_the_ship_state_the_game_writes_has_what_the_rule_reads(self) -> None:
        src = (SRC / "AstraBoardAssault.cpp").read_text(encoding="utf-8")
        for field in ("kestrels_free", "marines_fit_to_go", "boardable_now", "carriers", "faces_open", "point_defence_channels", "her_craft_about_her", "no_power", "boats_free"):
            self.assertIn(f'TEXT("{field}")', src, field)


class PromptTest(unittest.TestCase):
    def test_the_crew_is_told_how_the_marines_board_and_how_to_answer(self) -> None:
        text = system_prompt("it", BoardShip(True).snapshot(), [])
        for want in ("`board_ship`", "Kestrels, twelve marines each", "shuttle bay on Deck 8", "cannot dock through a shield", "ONE short line", "call_off", "Never say a boarding is on its way unless",
                     "The Mandate does the same to the Aquila", "`boarding_options`", "`captain: true`", "if that boat is shot down he is in it"):
            self.assertIn(want, text)

    def test_no_boats_no_rule(self) -> None:
        self.assertNotIn("board_ship", system_prompt("en", BoardShip(False).snapshot(), []))


class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_marines_are_sent_at_a_ship_the_boats_could_dock_at(self) -> None:
        crew = Crew([("board_ship", {"target": "T-30", "boats": 2, "objective": "captain"}), speak("Two Kestrels away for the Charon, twenty-four marines, about fifty seconds, Captain.")])
        turn = await crew.agent.handle("mandiamo i marine sull'Acheron", "it", parse_context(None, crew.ship.snapshot()))
        self.assertEqual(crew.ship.calls, [("board_ship", {"target": "T-30", "boats": 2, "objective": "captain"}, "xo")])
        self.assertTrue(turn.actions[0][2]["ok"])
        self.assertIn("2 Kestrels", turn.actions[0][2]["detail"])
        tools = {t["function"]["name"] for t in crew.llm.requests[0]["tools"]}
        self.assertIn("board_ship", tools)
        last = str(crew.llm.requests[0]["messages"][-1]["content"])                            # the model read what could be boarded in the ship state of its last message
        self.assertIn("boardable_now", last)
        self.assertIn("faces_open", last)
        self.assertIn("kestrels_free", last)

    async def test_a_refusal_of_the_game_is_read_back(self) -> None:
        crew = Crew([("board_ship", {"target": "T-12"})], [("board_ship", {"target": "T-12"})], [speak("The T-12 is too far for a boat, Captain.")])
        turn = await crew.agent.handle("board the T-12", "en", parse_context(None, crew.ship.snapshot()))
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertIn("too far", turn.actions[0][2]["detail"])

    async def test_the_boats_are_called_off(self) -> None:
        crew = Crew([("board_ship", {"action": "call_off"}), speak("Boats recalled, marines coming out.")])
        turn = await crew.agent.handle("richiamali", "it", parse_context(None, crew.ship.snapshot()))
        self.assertEqual(crew.ship.calls[0][1], {"action": "call_off"})
        self.assertTrue(turn.actions[0][2]["ok"])

    async def test_a_game_without_boats_refuses_the_call_and_sends_nothing(self) -> None:
        crew = Crew([("board_ship", {"target": "T-30"}), speak("We have no boats for that.")], with_boats=False)
        turn = await crew.agent.handle("board it", "en", parse_context(None, crew.ship.snapshot()))
        self.assertEqual(crew.ship.calls, [])
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertNotIn("board_ship", {t["function"]["name"] for t in crew.llm.requests[0]["tools"]})


if __name__ == "__main__":
    unittest.main()
