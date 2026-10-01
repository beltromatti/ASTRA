"""Which model serves which role, and what every call costs.

Rule of the project (docs/PIANO.md §4.1): DeepSeek V4.1 Flash is the ceiling of cost; each role gets the smallest, fastest
model that keeps the quality the role needs (measured: docs/bench/menti_2026-09-30.md); one request goes to ONE provider
(a fallback is tried only after an error or a stall, never in parallel, so nothing is paid twice); reasoning is off
wherever it does not help. A role's model can be swapped without touching code: `ASTRA_MODEL_<ROLE>=model@prov1,prov2`
in the environment or the .env (e.g. ASTRA_MODEL_ROUTER=openai/gpt-oss-20b@coreweave).

Every call made through `chat()` is written to the ledger (and to mind/.cache/spend.jsonl), so a session's spend by role
and model can be read back exactly."""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any

from .env import CACHE, load_env
from .openrouter import Completion, OpenRouter

log = logging.getLogger("astra.models")

DEEPSEEK = "deepseek/deepseek-v4.1-flash"
CEILING = (0.31, 1.25)          # $ per million tokens in / out: DeepSeek V4.1 Flash (0.30 / 1.20) plus rounding, the ceiling for every role


@dataclass(frozen=True)
class Role:
    name: str
    model: str
    providers: tuple[str, ...] | None = None
    reasoning: tuple[tuple[str, Any], ...] | None = (("enabled", False),)
    max_tokens: int = 400
    temperature: float | None = 0.3
    first_token_s: float | None = None                  # a request silent for this long is dropped and retried on the fallback
    max_price: tuple[float, float] | None = CEILING     # whatever OpenRouter falls back to must not cost more than this
    fallback: str | None = None                         # the role that answers if this one's model cannot (after a retry)
    note: str = ""

    def reasoning_arg(self) -> dict[str, Any] | None:
        return dict(self.reasoning) if self.reasoning is not None else None


# The registry. Provider order matters: the first one that answers serves. Together was the fastest DeepSeek endpoint in
# every measurement (median first token ~0.37 s), Modal the steady second (docs/bench/llm_2026-09-28_0227.md).
_DS = ("together", "modal")
ROLES: dict[str, Role] = {r.name: r for r in (
    Role("crew", DEEPSEEK, _DS, max_tokens=450, temperature=0.4, first_token_s=3.0,
         note="the Captain's turns and the officers' reports: quality and Italian first"),
    Role("watch", DEEPSEEK, _DS, max_tokens=300, temperature=0.4, first_token_s=5.0,
         note="the initiative watch: adjust the consoles, at most two short lines"),
    Role("router", DEEPSEEK, _DS, max_tokens=16, temperature=0.0, first_token_s=1.2,
         note="who is the Captain talking to (only the cases the rules cannot settle)"),
    Role("chatter", "openai/gpt-oss-120b", ("crusoe",), (("effort", "low"),), max_tokens=700, temperature=0.7,
         first_token_s=6.0, fallback="crew", note="quiet moments and low-stakes talk (bench/stations_models.py: 5x cheaper, faster, same checks)"),
    Role("admiral", DEEPSEEK, _DS, max_tokens=650, temperature=0.4, first_token_s=5.0,
         note="the Mandate's admiral (and the bench's ASTRA fleet commander): group orders, missiles, fighters and electronic war every 60-120 s or on "
              "strong events (war_minds.py); the prompt is long and stable, the picture short"),
    Role("commander", DEEPSEEK, _DS, max_tokens=550, temperature=0.5, first_token_s=5.0,
         note="a group commander of the Mandate or an allied captain of ASTRA: orders for one group, and an allied captain's few words on the fleet net "
              "(war_minds.py)"),
    Role("talk", DEEPSEEK, _DS, max_tokens=350, temperature=0.6, first_token_s=4.0,
         note="a Mandate commander on the open channel with the Captain (enemy.py): the same person as the admiral who commands, a few sentences"),
    Role("director", DEEPSEEK, _DS, max_tokens=900, temperature=0.8, first_token_s=8.0,
         note="the war director's beats and Rourke on the fleet net (director.py)"),
    Role("npc", DEEPSEEK, _DS, max_tokens=320, temperature=0.8, first_token_s=3.0, fallback="chatter",
         note="the ship's ordinary people when the Captain talks to them (npc.py): one or two lines in character, or a pass; one call per Captain "
              "utterance with someone in earshot (bench/npc_live.py: 16/16 as expected, first line 0.4 s, 0.4 m$ a call; gpt-oss-120b@crusoe 15/16, 0.7 s, 0.12 m$)"),
)}


def role(name: str) -> Role:
    """The role's configuration with the environment's override applied (`ASTRA_MODEL_<ROLE>`)."""
    base = ROLES[name]
    spec = load_env().get(f"ASTRA_MODEL_{name.upper()}", "").strip()
    if not spec:
        return base
    model, _, provs = spec.partition("@")
    return replace(base, model=model.strip() or base.model,
                   providers=tuple(p.strip() for p in provs.split(",") if p.strip()) or None)


# ------------------------------------------------------------------------------------------------ the ledger
class SpendCapReached(RuntimeError):
    """A bench has spent what it was allowed to."""


class Ledger:
    """What the session has spent, by role and by model (the cost OpenRouter reports for each call)."""

    def __init__(self) -> None:
        self.calls = 0
        self.total = 0.0
        self.by_role: dict[str, float] = defaultdict(float)
        self.by_model: dict[str, float] = defaultdict(float)
        self.n_role: dict[str, int] = defaultdict(int)
        self.write_file = True
        self.cap: float | None = None            # a ceiling (dollars) over everything the log holds plus this run: a bench stops there

    def prior(self) -> float:
        """What earlier runs spent (the sum of the log)."""
        try:
            return sum(json.loads(l).get("cost", 0.0) for l in (CACHE / "spend.jsonl").read_text().splitlines() if l.strip())
        except (OSError, ValueError):
            return 0.0

    def add(self, role_name: str, model: str, comp: Completion) -> None:
        """Record a call (it has been made and billed already: it is written down even when it is the one that reaches the cap,
        and only then the bench is stopped)."""
        over = self.cap is not None and self.write_file and self.prior() + comp.cost > self.cap
        self._record(role_name, model, comp)
        if over:
            raise SpendCapReached(f"the spend cap of {self.cap:.3f} $ is reached ({self.prior():.4f} $ in the log)")

    def _record(self, role_name: str, model: str, comp: Completion) -> None:
        self.calls += 1
        self.total += comp.cost
        self.by_role[role_name] += comp.cost
        self.by_model[model] += comp.cost
        self.n_role[role_name] += 1
        if self.write_file:
            try:
                CACHE.mkdir(parents=True, exist_ok=True)
                with (CACHE / "spend.jsonl").open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"t": round(time.time(), 1), "role": role_name, "model": model, "provider": comp.provider,
                                        "cost": comp.cost, "in": comp.prompt_tokens, "out": comp.completion_tokens,
                                        "cached": comp.cached_tokens, "reasoning": comp.reasoning_tokens,
                                        "first": comp.t_first_tool_name or comp.t_first_token, "end": comp.t_end,
                                        "error": comp.error[:80]}) + "\n")
            except OSError:
                pass

    def summary(self) -> str:
        parts = ", ".join(f"{r} {c:.5f} $ ({self.n_role[r]} calls)" for r, c in sorted(self.by_role.items()))
        return f"{self.calls} calls, {self.total:.5f} $ — {parts or 'nothing yet'}"


LEDGER = Ledger()


# ------------------------------------------------------------------------------------------------ calling
async def chat(llm: OpenRouter, role_name: str, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
               tool_choice: Any = "auto", on_tool_call: Any = None, retry: bool = True, **over: Any) -> Completion:
    """One request for a role: the role's model, providers, reasoning and price ceiling, streamed, recorded in the ledger.
    `over` may override max_tokens / temperature / model / providers / reasoning / first_token_s. If the request errors or
    stalls before anything was said or done, it is tried once more on the same providers with the fallbacks open (an
    error has cost nothing: this is not the same request sent twice)."""
    r = role(role_name)
    kw: dict[str, Any] = dict(model=over.pop("model", r.model), providers=list(over.pop("providers", None) or r.providers or []) or None,
                              reasoning=over.pop("reasoning", r.reasoning_arg()), max_tokens=over.pop("max_tokens", r.max_tokens),
                              temperature=over.pop("temperature", r.temperature), max_price=over.pop("max_price", r.max_price),
                              first_token_timeout=over.pop("first_token_s", r.first_token_s), allow_fallbacks=True)
    kw.update(over)
    fired = []

    async def watched(call: Any) -> None:
        fired.append(call.name)
        if on_tool_call is not None:
            res = on_tool_call(call)
            if hasattr(res, "__await__"):
                await res

    comp = await llm.chat(messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=watched, **kw)
    LEDGER.add(role_name, kw["model"], comp)
    if comp.error and retry and not fired and not comp.content.strip():
        log.warning("%s: %s — trying again", role_name, comp.error[:120])
        kw["first_token_timeout"] = (kw["first_token_timeout"] or 3.0) * 2
        comp = await llm.chat(messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=watched, **kw)
        LEDGER.add(role_name, kw["model"], comp)
    if comp.error and r.fallback and not fired and not comp.content.strip():
        log.warning("%s: still %s — the %s role answers", role_name, comp.error[:100], r.fallback)
        return await chat(llm, r.fallback, messages=messages, tools=tools, tool_choice=tool_choice, on_tool_call=on_tool_call)
    return comp
