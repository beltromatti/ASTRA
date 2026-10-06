"""How this Captain commands, as the XO has learned it — and what the Mandate's intelligence makes of it.

During a fight the keeper notes the Captain's orders (the words and what the ship did). When the engagement is over it
reads them against what it already knew and rewrites two short files: the XO's read of how this Captain fights (range,
patience, missiles, fighters, sensors and emissions, mercy, the risks taken, what they reach for first and what they
never do) and the same habits as the enemy sees them from outside. The crew's prompt carries the first (the XO
anticipates: has ready what the Captain usually wants, warns when a habit is dangerous against what they face); the
director reads it (the story tests the Captain's habits); and once the Mandate has fought the Aquila a few times, its
commanders get their intelligence's read of her captain — and try to exploit it."""
from __future__ import annotations

import logging
from typing import Any

from .openrouter import OpenRouter, ToolCall
from .prompt_layout import cached_prompt

log = logging.getLogger("astra.style")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
MIN_ORDERS = 2            # a fight with fewer orders than this teaches nothing about the Captain

PROFILE = {"type": "function", "function": {"name": "profile", "description": "The updated files on the Captain.",
           "parameters": {"type": "object", "properties": {
               "xo_read": {"type": "string", "description": "the XO's read, third person, at most 90 words"},
               "mandate_read": {"type": "string", "description": "the Mandate intelligence read, at most 60 words"}},
               "required": ["xo_read", "mandate_read"]}}}

PROMPT = """You keep two files on the Captain of the ASN Aquila, a carrier cruiser of the ASTRA Navy.

1. The XO's read, for the bridge crew: how this Captain commands in battle, from what they actually did — range and
   patience (close in or stand off, wait or strike first), weapons (railgun volleys, missile salvos or sparing),
   fighters (early or late, which missions), sensors and emissions (active pings, EMCON, running quiet), shields and
   damage control, talk and mercy (hails, surrenders), the risks taken, what they reach for first and what they never
   do. Third person ("the Captain ..."), concrete, at most 90 words, no praise or blame. Keep what still holds, correct
   what this fight contradicted, drop what no longer matters.
2. The Mandate's intelligence read, for the enemy commanders who will face the Aquila: the same habits as an enemy
   sees them from outside — only what could be observed (her manoeuvres, emissions and pings, fire, fighters, how she
   answers a hail) — and how a Mandate commander could exploit them. At most 60 words.

What you knew before (fights recorded: {n}):
- XO: {xo}
- Mandate: {mandate}

This fight: {outcome}

The Captain's orders, in order (their words, and what the ship did with them):
{orders}

Call `profile` once."""


class StyleKeeper:
    def __init__(self, llm: OpenRouter, store: dict[str, Any]) -> None:
        self.llm = llm
        self.store = store               # {"xo": str, "mandate": str, "battles": int}: the director saves it with the story
        self.orders: list[str] = []
        self.busy = False

    def captain_order(self, text: str, actions: list) -> None:
        """A Captain's turn: the words, and the ship tools it set off (speech is not an order)."""
        acts = []
        for name, args, res in actions or []:
            if name in ("speak", "standing_order"):
                continue
            a = ", ".join(f"{k}={v}" for k, v in (args or {}).items() if k not in ("message", "reason"))[:120]
            acts.append(f"{name}({a}){'' if (res or {}).get('ok') else ' refused'}")
        if not acts:
            return
        self.orders = (self.orders + [f'- "{(text or "").strip()[:200]}" => {"; ".join(acts)[:400]}'])[-40:]

    def xo_line(self) -> str:
        return str(self.store.get("xo") or "")

    def mandate_line(self) -> str:
        """The enemy learns the Aquila only after fighting her a few times."""
        return str(self.store.get("mandate") or "") if int(self.store.get("battles", 0) or 0) >= 2 else ""

    def reset(self) -> None:
        self.orders.clear()

    async def after_battle(self, outcome: str) -> None:
        orders, self.orders = self.orders, []
        if self.busy or len(orders) < MIN_ORDERS:
            return
        self.busy = True
        try:
            got: dict[str, str] = {}

            async def on_call(call: ToolCall) -> None:
                if call.name == "profile" and not got:
                    a = call.arguments() or {}
                    got.update({k: str(a.get(k) or "").strip() for k in ("xo_read", "mandate_read")})

            system, current_context = cached_prompt(PROMPT, dict(n=int(self.store.get("battles", 0) or 0),
                xo=self.store.get("xo") or "(nothing yet)", mandate=self.store.get("mandate") or "(nothing yet)",
                outcome=outcome[:400], orders="\n".join(orders)), ("n", "xo", "mandate", "outcome", "orders"))
            comp = await self.llm.chat(model=MODEL, messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": current_context + "\n\nUpdate the files."}],
                tools=[PROFILE], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=500,
                temperature=0.3, on_tool_call=on_call, allow_fallbacks=True)
            if comp.error:
                log.error("style LLM error: %s", comp.error)
            if got.get("xo_read"):
                self.store["xo"] = got["xo_read"][:800]
                self.store["mandate"] = (got.get("mandate_read") or self.store.get("mandate") or "")[:600]
                self.store["battles"] = int(self.store.get("battles", 0) or 0) + 1
                log.info("the XO's read of the Captain (%d fights): %s", self.store["battles"], self.store["xo"])
                log.info("the Mandate's read: %s", self.store["mandate"])
        except Exception:  # noqa: BLE001
            log.exception("style update failed")
        finally:
            self.busy = False
