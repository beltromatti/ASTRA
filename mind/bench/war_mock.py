"""Scripted stand-ins for the war minds' model (no network, no cost): the tests' and the arena's fixtures.

`MockLLM.chat` has the signature of `OpenRouter.chat` and answers with tool calls, as a model would; WHAT it calls comes from a policy.
  - `NullPolicy`      always `no_change` (the plumbing: cadence, prompts, tools run, nothing ordered);
  - `ScriptPolicy`    a list of canned replies (the unit tests: each call pops the next);
  - `ClosePolicy`     a plain heuristic commander: attack the most valuable battered enemy at a range of 3.2 km, keep the order while it serves,
                      withdraw a group that is lost. It stands for "an order interface used sensibly" (what the interface can do), not for a model.
The policies read the structured view of the pulse being answered (`astra_mind.war_minds.CURRENT`), never the prompt's text."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from astra_mind import war_minds
from astra_mind.openrouter import Completion, ToolCall

VALUE = {"aquila": 1.7, "praetorian": 1.3, "acheron": 1.25, "vigilant": 0.85, "styx": 0.85, "lethe": 0.7}


Reply = list[tuple[str, dict[str, Any]]]
Policy = Callable[[Any, dict[str, Any], dict[str, Any], list[str]], Reply]


def null_policy(mind: Any, view: dict[str, Any], state: dict[str, Any], tools: list[str]) -> Reply:
    return [("no_change", {"reason": "nothing to change"})]


class ScriptPolicy:
    """Canned replies, in order (the last one repeats unless `loop` is False)."""

    def __init__(self, *replies: Reply, loop: bool = True) -> None:
        self.replies = list(replies)
        self.loop = loop
        self.seen: list[tuple[str, list[str]]] = []

    def __call__(self, mind: Any, view: dict[str, Any], state: dict[str, Any], tools: list[str]) -> Reply:
        self.seen.append((mind.seat.id, tools))
        if not self.replies:
            return []
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0] if self.loop else self.replies.pop(0)


def _enemy_ships(view: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for g in view.get("enemy_groups") or []:
        for s in g.get("ships") or []:
            out.append({**s, "range_km": g.get("range_km", 99)})
    return out


def close_policy(range_km: float = 3.2, formation: str = "", reissue: bool = False) -> Policy:
    """`reissue`: the commander gives its order again at every look even when the one in force still serves (an order that is only repeated: the
    bench asks what that costs a group)."""
    def policy(mind: Any, view: dict[str, Any], state: dict[str, Any], tools: list[str]) -> Reply:
        foes = _enemy_ships(view)
        if not foes:
            return [("no_change", {"reason": "no enemy on the plot"})]
        seat = mind.seat

        def score(s: dict[str, Any]) -> float:
            hull = s.get("hull_pct")
            hull = 100.0 if hull is None else float(hull)
            return VALUE.get(str(s.get("class")), 1.0) * (1.6 - hull / 100.0) - 0.02 * float(s.get("range_km") or 0)
        ids = {s["id"] for s in foes}
        best = max(foes, key=score)
        calls: Reply = []
        for g in view.get("your_groups") or []:
            if seat.kind == "group" and g.get("name") != seat.group:
                continue
            strength, enemy = float(g.get("your_strength") or 0), float(g.get("enemy_strength_near") or 0) + 1e-6
            if float(g.get("morale") or 1) < 0.2 and strength < 0.35 * enemy and g.get("order_in_force") != "withdraw":
                calls.append(("group_order", {"group": g["name"], "order": "withdraw", "reason": "the group is lost: save the ships"}))
                continue
            if g.get("order_in_force") == "withdraw":
                continue
            cur = g.get("order_target") or g.get("focus_fire_on")
            if not reissue and g.get("order_in_force") == "attack" and cur in ids and g.get("order_by") in ("admiral", "commander", "captain"):
                continue
            order = {"group": g["name"], "order": "attack", "target": best["id"], "range_km": range_km,
                     "reason": f"concentrate on {best['id']} ({best.get('class')}) and hold {range_km} km"}
            if formation and g.get("formation") != formation:
                order["formation"] = formation
            calls.append(("group_order", order))
        return calls or [("no_change", {"reason": "the orders that stand serve"})]
    return policy


class MockLLM:
    """Answers `chat` with the policy's tool calls (streamed through `on_tool_call`, like the real client). `latency`: seconds each call takes
    (the arena runs the battle in real time meanwhile); `calls` keeps what was asked, for the tests."""

    def __init__(self, policy: Policy = null_policy, latency: float = 0.05, cost: float = 0.0011) -> None:
        self.policy = policy
        self.latency = latency
        self.cost = cost
        self.calls: list[dict[str, Any]] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500,
                   temperature=0.3, extra=None, on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None):
        names = [t["function"]["name"] for t in (tools or [])]
        mind = war_minds.CURRENT.get()
        view, state = war_minds.CURRENT_VIEW.get() or ({}, {})
        self.calls.append({"model": model, "tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[-1].get("content", "")),
                           "messages": messages, "seat": mind.seat.id if mind else None})
        out = Completion(model=model, provider="mock", cost=self.cost, prompt_tokens=3000, completion_tokens=120)
        if self.latency:
            await asyncio.sleep(self.latency)
        if mind is None:
            return out
        reply = self.policy(mind, view, state, names)
        for i, (name, args) in enumerate(reply):
            if name not in names:
                continue
            tc = ToolCall(name=name, arguments_raw=json.dumps(args), id=f"m{len(self.calls)}_{i}")
            out.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        out.t_first_tool_name = self.latency
        out.t_end = self.latency
        return out

    async def close(self) -> None:
        pass
