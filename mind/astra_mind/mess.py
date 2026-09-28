"""The Mess Hall's talk: what the Captain overhears among the off-duty crew at their tables.

While the Captain is in the Mess Hall (Deck 4), every half minute or so two or three people at one table talk among
themselves — about the last fight, a friend in the Medbay or on the memorial wall, the food, home, the war on the fleet
net, the Captain's decisions — in their own voices, from their own places. Nothing is scripted: each exchange is
written from who they are (department, deck, home) and from what the ship has just lived through (the events, the
casualties, the campaign, the crew's mood and the officers' bonds with the Captain). When the Captain walks in, the
first ones to notice say so. The Captain can join in at any time: then the crew agent answers as them."""
from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable

from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.mess")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]

SAY = {"type": "function", "function": {
    "name": "say", "description": "One line of the conversation, spoken aloud at the table (one call per line, in order).",
    "parameters": {"type": "object", "properties": {
        "speaker": {"type": "string", "description": "the speaker id of one of the people at this table"},
        "text": {"type": "string", "description": "what they say, in the Captain's language, max ~22 words"}},
        "required": ["speaker", "text"]}}}

PROMPT = """You write what the Captain of the ASN Aquila overhears in the ship's Mess Hall (Deck 4): off-duty crew
talking among themselves at one table. They are real people of this crew; the Captain is somewhere in the hall.

{world}

At this table:
{people}

What the ship has lived through lately (most recent last):
{events}

The campaign so far:
{campaign}

The crew's mood: {mood}
How the officers stand with the Captain: {bonds}
The war on the fleet net: {war}
Casualties: {casualties}

{situation}

Write one short exchange: {lines} lines, each with `say` (speaker id and text), alternating between people at this
table. Every line in {lang_name}; proper names in English (ASN Aquila, Kharon Mandate, Alpha Squadron...), but the
Captain is "{captain}" (never the English word in another language). Spoken and
natural, off duty: tired, dry, joking, worried, proud — people with jobs, friends and homes, talking about something
specific (their work on their deck, someone they know, what just happened, the food, the war, home, the Captain's
last decisions as they understood them). Never invent battles, casualties or facts the ship has not lived; rumours
must be plausible and hedged. Never mention AI, games or prompts. No narration: only what they say."""

FIRST = ("The Captain has just walked into the Mess Hall. The first line: one of them notices the Captain and says so "
         "quietly to the others (not to the Captain); then they go on with their conversation, a little more carefully.")
LATER = ("They have not noticed the Captain listening, or have got used to the Captain's presence. They talk about what "
         "is on their minds.")


class MessTalk:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]]) -> None:
        self.llm = llm
        self.say = say
        self.next_t = 0.0
        self.in_mess = False
        self.greeted = False
        self.topics: list[str] = []      # what was said lately (not to repeat it)
        self.busy = False

    def left(self) -> None:
        self.in_mess = False
        self.greeted = False

    async def tick(self, state: dict[str, Any], lang: str, context: dict[str, Any], quiet_s: float, voice_busy_s: float) -> None:
        """Called every few seconds by the server: speaks up when the Captain is in the Mess Hall and all is quiet."""
        mess = (state or {}).get("mess") or {}
        diners = mess.get("diners") or []
        if not diners:
            if self.in_mess:
                self.left()
            return
        now = time.monotonic()
        if not self.in_mess:
            self.in_mess = True
            self.next_t = now + 3.0          # a moment to take the room in
        if self.busy or now < self.next_t or voice_busy_s > 0.5 or quiet_s < 8.0:
            return
        self.busy = True
        try:
            await self._exchange(diners, lang, context, first=not self.greeted)
            self.greeted = True
        except Exception:  # noqa: BLE001
            log.exception("mess talk failed")
        finally:
            self.busy = False
            self.next_t = time.monotonic() + random.uniform(35.0, 70.0)

    async def _exchange(self, diners: list[dict[str, Any]], lang: str, ctx: dict[str, Any], first: bool) -> None:
        # a table with at least two people (seats name the table: "at the middle table of the inner left row")
        tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for d in diners:
            tables[d.get("seat", "")].append(d)
        groups = [g for g in tables.values() if len(g) >= 2] or [diners[:2]]
        group = random.choice(groups)[:3]
        menu = (ctx.get("menu") or "").strip()
        people = "\n".join(f"- {d['speaker']}: {d.get('name', '?')} ({'woman' if d.get('gender') == 'f' else 'man'}), "
                           f"{d.get('dept', '')}, deck {d.get('deck', '?')}, from {d.get('home', '?')}; {d.get('seat', '')}"
                           for d in group)
        situation = (FIRST if first else LATER) + (f" Today's food: {menu}." if menu else "")
        if self.topics:
            situation += " Lately overheard at the tables (do not repeat it): " + " / ".join(self.topics[-4:])
        prompt = PROMPT.format(world=WORLD, people=people, events="\n".join(f"- {e}" for e in ctx.get("events", [])[-8:]) or "- (quiet)",
                               campaign="\n".join(f"- {c}" for c in ctx.get("campaign", [])[-6:]) or "- (the patrol has just begun)",
                               mood=ctx.get("mood") or "(steady)", bonds=ctx.get("bonds") or "(nothing particular)",
                               war=ctx.get("war") or "(no news)", casualties=ctx.get("casualties") or "none",
                               situation=situation, lines="3 or 4" if not first else "3", lang_name=LANG_NAMES.get(lang, lang),
                               captain=CAPTAIN_WORD.get(lang, "Captain"))
        ids = {d["speaker"] for d in group}
        spoken: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            who, text = a.get("speaker", ""), (a.get("text") or "").strip()
            if call.name == "say" and who in ids and len(text) >= 4 and len(spoken) < 4:
                spoken.append(f"{who}: {text}")
                await self.say(who, text, lang, "warm")

        t0 = time.perf_counter()
        comp = await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt},
                                                          {"role": "user", "content": "(the conversation at the table)"}],
                                   tools=[SAY], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False},
                                   max_tokens=420, temperature=0.9, on_tool_call=on_call, allow_fallbacks=True)
        if spoken:
            self.topics = (self.topics + [" | ".join(s.split(": ", 1)[1] for s in spoken)[:220]])[-8:]
        log.info("mess talk %.2fs (%s): %s", time.perf_counter() - t0, "greeting" if first else "table",
                 " | ".join(spoken) or f"(nothing: {comp.error or comp.content[:80]})")

