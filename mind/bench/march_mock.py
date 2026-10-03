"""Scripted stand-ins for the strategic minds' model (no network, no cost): the tests' and the bench's fixtures (docs/GUERRA.md §10).

`StrategyMock.chat` has the signature of `OpenRouter.chat` and answers with tool calls, as a model would; WHAT it calls comes from a policy.
  - `null_policy`     always `no_change` (the plumbing: cadence, prompts, tools run, nothing ordered);
  - `ScriptPolicy`    a list of canned replies (the unit tests: each call pops the next);
  - `reflex_policy`   what the reflexes would do (march_auto.py), given through the tools: it stands for "the tools used sensibly", not for a model.
The policies read the March and the side being answered (`astra_mind.strategy.CURRENT`, `CURRENT_VIEW`), never the prompt's text."""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from astra_mind import strategy
from astra_mind.openrouter import Completion, ToolCall

Reply = list[tuple[str, dict[str, Any]]]
Policy = Callable[[Any, Any, str, list[str], list[dict[str, Any]]], Reply]


def null_policy(seat: Any, march: Any, side: str, tools: list[str], messages: list[dict[str, Any]]) -> Reply:
    return [("no_change", {"reason": "nothing to change"})]


class ScriptPolicy:
    """Canned replies, in order (the last one repeats unless `loop` is False)."""

    def __init__(self, *replies: Reply, loop: bool = True, only: str | None = None) -> None:
        self.replies = list(replies)
        self.loop = loop
        self.only = only                                  # the side the script is for (the other one has no change to make)
        self.seen: list[tuple[str, list[str]]] = []

    def __call__(self, seat: Any, march: Any, side: str, tools: list[str], messages: list[dict[str, Any]]) -> Reply:
        self.seen.append((side, tools))
        if self.only and side != self.only:
            return [("no_change", {"reason": "not in the script"})]
        if not self.replies:
            return []
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0] if self.loop else self.replies.pop(0)


class StrategyMock:
    """Answers `chat` with the policy's tool calls (streamed through `on_tool_call`, like the real client). `latency`: seconds each call takes; `calls` keeps what was
    asked, for the tests."""

    def __init__(self, policy: Policy = null_policy, latency: float = 0.0, cost: float = 0.0016, fail: int = 0) -> None:
        self.policy = policy
        self.latency = latency
        self.cost = cost
        self.fail = fail                                  # the next `fail` calls end in an error (a provider down)
        self.calls: list[dict[str, Any]] = []

    async def chat(self, *, model, messages, tools=None, tool_choice="auto", providers=None, reasoning=None, max_tokens=500, temperature=0.3, extra=None,
                   on_tool_call=None, allow_fallbacks=False, max_price=None, first_token_timeout=None):
        names = [t["function"]["name"] for t in (tools or [])]
        seat = strategy.CURRENT.get()
        view = strategy.CURRENT_VIEW.get()
        self.calls.append({"model": model, "tools": names, "system": str(messages[0].get("content", "")), "user": str(messages[1].get("content", "")), "messages": messages,
                           "side": seat.side if seat else None, "max_tokens": max_tokens})
        out = Completion(model=model, provider="mock", cost=self.cost, prompt_tokens=3200, completion_tokens=180)
        if self.latency:
            await asyncio.sleep(self.latency)
        if self.fail > 0:
            self.fail -= 1
            out.error = "mock: provider down"
            out.cost = 0.0
            return out
        if seat is None or view is None:
            return out
        march, side = view
        reply = self.policy(seat, march, side, names, messages)
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
