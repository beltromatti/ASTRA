"""Officers who come to the Captain's quarters in person.

When the Captain goes into the quarters (Deck 1, behind the bridge), someone may have a reason to come by — not every
time, only when it matters: the doctor with a death she will not report over the intercom, the XO after a hard call,
the Chief with a complaint about how his engines were used, a pilot's commander after a loss in Alpha. The decision is
the story's: made from what the ship has lived through (events, casualties, the campaign, the crew's mood, how each
officer stands with the Captain). The game walks the officer from the bridge to the cabin; when they are inside the
door the crew speaks as them, face to face; the Captain lets them go (dismiss_visitor), or they go after a while."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .crew import CREW, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.visits")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
GAP_S = 12 * 60          # at most one visit in twelve minutes
ASK_GAP_S = 180.0        # the story asks again only after three minutes (in and out of the cabin is no new reason)
WAIT_S = 20.0            # the Captain settles in before anyone knocks

TOOLS = [
    {"type": "function", "function": {
        "name": "visit", "description": "One officer comes to the Captain's quarters in person, now.",
        "parameters": {"type": "object", "properties": {
            "officer": {"type": "string", "enum": [k for k in CREW]},
            "reason": {"type": "string", "description": "why they come, in one English sentence (what they want to say or "
                                                        "ask, and what is behind it)"}},
            "required": ["officer", "reason"]}}},
    {"type": "function", "function": {
        "name": "no_visit", "description": "Nobody comes: nothing that needs saying in person right now.",
        "parameters": {"type": "object", "properties": {}}}}]

PROMPT = """You are the story director of ASTRA. The Captain of the ASN Aquila has just gone into the Captain's quarters
(Deck 1, behind the bridge). Decide whether one of the officers would come to the cabin in person now.

{world}

The officers:
{officers}

Recently aboard (most recent last):
{events}

The campaign so far:
{campaign}

Casualties: {casualties}
The crew's mood: {mood}
How each officer stands with the Captain: {bonds}
Earlier visits: {earlier}

Someone comes only for something that matters and belongs face to face, never for routine reports (those go over the
intercom): a death or a grave wound told in person (usually the doctor), a hard decision to discuss or a doubt the XO
will not voice on the bridge, a department head's complaint or request after the way their people or systems were used,
a personal matter an officer has been carrying (their bond with the Captain), a thank-you after something the Captain
did for them. It must follow from what actually happened. If nothing like that is pending, call no_visit — most of the
time nobody comes. Never during a battle. Call exactly one tool."""


class VisitPlanner:
    def __init__(self, llm: OpenRouter, command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 note: Callable[[str], None]) -> None:
        self.llm = llm
        self.command = command           # sends a game command (visit)
        self.note = note                 # the story remembers the visit
        self.last_t = -1e9
        self.asked_t = -1e9
        self.history: list[str] = []     # who came and why (for the next decisions)
        self.pending: asyncio.Task | None = None

    def captain_entered(self, get_state: Callable[[], dict[str, Any]], get_ctx: Callable[[], dict[str, Any]]) -> None:
        if self.pending and not self.pending.done():
            return
        now = time.monotonic()
        if now - self.last_t < GAP_S or now - self.asked_t < ASK_GAP_S:
            return
        self.asked_t = now
        self.pending = asyncio.create_task(self._decide(get_state, get_ctx))

    async def _decide(self, get_state: Callable[[], dict[str, Any]], get_ctx: Callable[[], dict[str, Any]]) -> None:
        await asyncio.sleep(WAIT_S)
        st = get_state() or {}
        where = str(st.get("captain", ""))
        if "Captain's quarters" not in where or "asleep" in where or st.get("alert") == "red" or st.get("visitor"):
            return
        if any(str(c.get("status", "")).startswith("hostile") for c in st.get("contacts", []) or []):
            return
        ctx = get_ctx()
        officers = "\n".join(f"- {o.id}: {o.title}, {o.role}. {o.personality}" for o in CREW.values())
        prompt = PROMPT.format(world=WORLD, officers=officers,
                               events="\n".join(f"- {e}" for e in ctx.get("events", [])[-12:]) or "- (quiet)",
                               campaign="\n".join(f"- {c}" for c in ctx.get("campaign", [])[-10:]) or "- (the patrol has just begun)",
                               casualties=st.get("casualties", "none"), mood=ctx.get("mood") or "(steady)",
                               bonds=ctx.get("bonds") or "(nothing particular)", earlier="; ".join(self.history[-4:]) or "none")
        choice: dict[str, Any] = {}

        async def on_call(call: ToolCall) -> None:
            if call.name == "visit" and not choice:
                choice.update(call.arguments() or {})
            elif call.name == "no_visit" and not choice:
                choice["none"] = True

        t0 = time.perf_counter()
        await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt},
                                                   {"role": "user", "content": "(the Captain is in the quarters)"}],
                            tools=TOOLS, tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False},
                            max_tokens=260, temperature=0.5, on_tool_call=on_call, allow_fallbacks=True)
        officer, reason = choice.get("officer"), (choice.get("reason") or "").strip()
        log.info("visit decision %.2fs: %s", time.perf_counter() - t0, f"{officer}: {reason}" if officer else "nobody comes")
        if not officer or officer not in CREW or not reason:
            return
        res = await self.command("visit", {"officer": officer, "reason": reason})
        if res.get("ok"):
            self.last_t = time.monotonic()
            self.history.append(f"{officer}: {reason}")
            self.note(f"{CREW[officer].title} came to the Captain's quarters in person: {reason}")
            log.info("visit: %s is on the way (%s)", officer, res.get("detail", ""))
        else:
            log.info("visit refused by the game: %s", res.get("detail", res))
