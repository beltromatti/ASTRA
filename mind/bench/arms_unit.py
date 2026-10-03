"""Offline tests of the Captain's weapons in the crew's hands: the armourer's tool, the rule that says where the weapons are, against a scripted model and a scripted ship (no network, no cost).

    cd mind && .venv/bin/python -m unittest bench.arms_unit -v

The Captain asks the bridge for a weapon; the XO sends the armourer with a real tool (`issue_weapon`: the game's UAstraBoardSubsystem::IssueWeapon takes the weapon off the Marine
Armory's rack and puts it in his hands after the time of the way). What is checked is the plumbing the behaviour stands on: the tool exists only in a game that reports `arms` (the ship
state's account of where the weapons are, what he carries, what is on its way), it is the XO's, it takes one of three kinds and the Captain, the crew's prompt tells them where the weapons
are and how to answer, a call reaches the ship as the game's own command, and a refusal of the game is read back. Nothing in the code reads the Captain's words (docs/ARCHITETTURA.md §1bis):
whether "portatemi un'arma" means a sidearm or a rifle is the model's judgement."""
from __future__ import annotations

import json
import unittest
from typing import Any

from astra_mind import models
from astra_mind.agent import BridgeAgent
from astra_mind.context import parse as parse_context
from astra_mind.crew import system_prompt
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.tools import SHIP_TOOL_NAMES, owner_of, tools_for

models.LEDGER.write_file = False

ARMS = {"captain_carries": "nothing", "kept": [{"where": "the Marine Armory on Deck 8 (port side, forward): the rack in the aisle in front of the armourer's issue counter",
                                                 "holds": "an AR-181 service rifle and an M27S sidearm"},
                                                {"where": "the Captain's Ready Room on Deck 1 (behind the bridge): a small locker on the port wall, by the door to the corridor",
                                                 "holds": "an M27S sidearm"}],
        "armourer": "Petty Officer Dara Okafor (Marine Armory)"}


class ArmsShip(LocalShip):
    """The local ship plus the Captain's weapons: `issue_weapon` is the game's (UAstraBoardSubsystem::IssueWeapon); here it answers like the game does and keeps what it was asked."""

    def __init__(self, with_arms: bool = True) -> None:
        super().__init__(stations=True, fight=False)
        self.with_arms = with_arms
        self.calls: list[tuple[str, dict[str, Any], str]] = []
        self.carries: set[str] = set()

    def snapshot(self) -> dict[str, Any]:
        s = super().snapshot()
        if self.with_arms:
            s["arms"] = dict(ARMS, captain_carries=", ".join(sorted(self.carries)) or "nothing")
        return s

    def _execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        if name == "issue_weapon":
            self.calls.append((name, dict(a), by))
            kind = a.get("kind")
            if kind not in ("pistol", "rifle", "kit"):
                return {"ok": False, "detail": f"the armoury has a rifle (AR-181) and a sidearm (M27S): kind is rifle, pistol or kit, not '{kind}'"}
            if kind in self.carries:
                return {"ok": False, "detail": "the Captain already carries it"}
            self.carries.add(kind)
            word = {"pistol": "the sidearm", "rifle": "the rifle", "kit": "the rifle and the sidearm"}[kind]
            return {"ok": True, "detail": f"Petty Officer Dara Okafor is bringing {word} from the Marine Armory on Deck 8: about 64 s, and it will be put in the Captain's hands where he stands"}
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
    def __init__(self, *scripts: list[tuple[str, dict[str, Any]]], with_arms: bool = True) -> None:
        self.ship = ArmsShip(with_arms)
        self.llm = FakeLLM(*scripts)
        self.said: list[tuple[str, str]] = []

        async def say(speaker: str, text: str, lang: str, tone: str) -> None:
            self.said.append((speaker, text))
        self.agent = BridgeAgent(self.llm, self.ship, say)


class ToolTest(unittest.TestCase):
    def test_the_tool_exists_only_in_a_game_that_reports_the_weapons(self) -> None:
        with_arms = tools_for(ArmsShip(True).snapshot())
        without = tools_for(ArmsShip(False).snapshot())
        self.assertIn("issue_weapon", with_arms.names)
        self.assertNotIn("issue_weapon", without.names)                          # (an older build: nobody to send)
        self.assertIn("issue_weapon", SHIP_TOOL_NAMES)

    def test_it_is_the_xos_and_takes_the_captain_and_three_kinds(self) -> None:
        self.assertEqual(owner_of("issue_weapon"), "xo")
        tool = next(t for t in tools_for(ArmsShip(True).snapshot()).tools if t["function"]["name"] == "issue_weapon")["function"]
        props = tool["parameters"]["properties"]
        self.assertEqual(props["kind"]["enum"], ["pistol", "rifle", "kit"])
        self.assertEqual(props["who"]["enum"], ["captain"])
        self.assertEqual(tool["parameters"]["required"], ["kind"])
        self.assertFalse(tool["parameters"]["additionalProperties"])

    def test_the_legacy_consoles_keep_their_tools(self) -> None:
        legacy = ArmsShip(True).snapshot()
        legacy.pop("stations", None)
        ts = tools_for(legacy)
        self.assertIn("issue_weapon", ts.names)
        self.assertIn("intercept", ts.names)


class PromptTest(unittest.TestCase):
    def test_the_crew_is_told_where_the_weapons_are_and_what_to_do(self) -> None:
        text = system_prompt("it", ArmsShip(True).snapshot(), [])
        for want in ("Marine Armory", "Deck 8", "Ready Room", "locker", "issue_weapon", "pistol, rifle or kit", "E at the rack", "Never say a weapon is on its way unless"):
            self.assertIn(want, text)

    def test_no_weapons_no_rule(self) -> None:
        self.assertNotIn("issue_weapon", system_prompt("en", ArmsShip(False).snapshot(), []))


class AgentTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_sidearm_is_ordered_for_the_captain(self) -> None:
        crew = Crew([("issue_weapon", {"kind": "pistol", "who": "captain"}), speak("Armourer Okafor is bringing you a sidearm, about a minute.")])
        turn = await crew.agent.handle("portatemi un'arma", "it", parse_context(None, crew.ship.snapshot()))
        self.assertEqual(crew.ship.calls, [("issue_weapon", {"kind": "pistol", "who": "captain"}, "xo")])
        self.assertTrue(turn.actions[0][2]["ok"])
        self.assertIn("Okafor", turn.actions[0][2]["detail"])
        self.assertEqual(crew.said[0][0], "xo")
        tools = {t["function"]["name"] for t in crew.llm.requests[0]["tools"]}
        self.assertIn("issue_weapon", tools)
        # the model read where the weapons are in the ship state of its last message
        last = str(crew.llm.requests[0]["messages"][-1]["content"])
        self.assertIn("Marine Armory", last)
        self.assertIn("Ready Room", last)

    async def test_a_refusal_of_the_game_is_read_back(self) -> None:
        crew = Crew([("issue_weapon", {"kind": "pistol"})], [("issue_weapon", {"kind": "pistol"})], [speak("You carry the sidearm already, Captain.")])
        crew.ship.carries.add("pistol")
        turn = await crew.agent.handle("another sidearm", "en", parse_context(None, crew.ship.snapshot()))
        self.assertFalse(turn.actions[0][2]["ok"])
        self.assertIn("already carries", turn.actions[0][2]["detail"])

    async def test_a_game_without_weapons_refuses_the_call_and_sends_nothing(self) -> None:
        crew = Crew([("issue_weapon", {"kind": "pistol"}), speak("Nothing aboard can do that.")], with_arms=False)
        turn = await crew.agent.handle("a weapon", "en", parse_context(None, crew.ship.snapshot()))
        self.assertEqual(crew.ship.calls, [])
        self.assertFalse(turn.actions[0][2]["ok"])
        tools = {t["function"]["name"] for t in crew.llm.requests[0]["tools"]}
        self.assertNotIn("issue_weapon", tools)


if __name__ == "__main__":
    unittest.main()
