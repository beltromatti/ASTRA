"""The end of an arc of the war: after the decisive battle, the outcome — computed from what really happened (the
battle's result, the war map, the losses, the Captain's choices and promises) — is told: Rourke's words to the Aquila, then
a few cards on a black screen read aloud by the narrator in the Captain's language (the battle's name and what it decided,
two or three lines of what became of the people, the war going on), the game holding still under them (story.py); the war
map is redrawn, and the war goes on: a new arc begins."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

from .crew import CREW, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall
from .story import tell
from .war import OWNERS

log = logging.getLogger("astra.finale")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]

FINALE = {"type": "function", "function": {"name": "finale", "description": "How this arc of the war ends.", "parameters": {
    "type": "object", "properties": {
        "outcome": {"type": "string", "enum": ["victory", "defeat", "stalemate", "armistice"]},
        "battle_name": {"type": "string", "description": "what history will call the decisive battle, in English (e.g. "
                                                        "\"The Battle of the Aurelia Gate\")"},
        "decided": {"type": "string", "description": "one short sentence, in the Captain's language, for the first card (the narrator reads it): what "
                                                    "the battle decided"},
        "admiral_words": {"type": "string", "description": "Vice Admiral Rourke to the Aquila over the fleet net, in the "
                                                          "Captain's language: the outcome and what it cost, 2-4 sentences"},
        "epilogue": {"type": "array", "items": {"type": "string"}, "description": "2 or 3 lines in the Captain's language, at most 20 "
                     "words each, for the epilogue cards the narrator reads: what became of the people (an officer by name, as their bond "
                     "with the Captain made them; the fallen remembered; an enemy commander the Captain faced)"},
        "closing": {"type": "string", "description": "one sentence of at most 10 words, in the Captain's language, for the last card: the war "
                                                    "goes on (where, or against what)"},
        "war": {"type": "array", "items": {"type": "object", "properties": {
            "system": {"type": "string"}, "owner": {"type": "string", "enum": list(OWNERS)},
            "threat": {"type": "integer", "minimum": 0, "maximum": 3}}, "required": ["system"]},
            "description": "the systems whose holder or threat the outcome changes"},
        "next_arc": {"type": "string", "description": "in English, for the story: where the war goes from here — the "
                                                     "seed of the next arc (one or two sentences)"}},
    "required": ["outcome", "battle_name", "decided", "admiral_words", "epilogue", "closing", "next_arc"]}}}

PROMPT = """You are the director of the war story of ASTRA. An arc of the war has reached its decisive battle, and it is
over:

{result}

{world}

The whole arc (oldest first; the Captain's own log entries are marked "captain's log"):
{campaign}

The crew's mood: {mood}
The officers and the Captain: {bonds}

The Aurelia March now:
{war}

Tell how this arc ends. The outcome must follow from the facts: the battle's result above first (who held the field,
what was lost), then the war map, then the Captain's choices (mercy shown, promises kept or broken, officers heeded or
overruled). victory: the Mandate's offensive is broken and ASTRA holds or retakes ground; defeat: the March buckles
(systems fall, the fleet falls back); stalemate: both sides bled and hold; armistice: only if the story earned it
(talks over the channel, promises kept on both sides). Epilogue lines are specific and human, never generic; the
Captain's gender is not known (say "the Captain"). The cards are few and short: they are read aloud over a black screen while the
game waits, and a player wants to be back on the bridge. Call `finale` once."""


class Finale:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 voice_busy: Callable[[], float]) -> None:
        self.llm = llm
        self.say = say
        self.command = command
        self.voice_busy = voice_busy
        self.running = False

    async def run(self, director: Any, result: str, lang: str) -> dict[str, Any]:
        """Decide and play the end of the arc. Returns the finale's arguments ({} if it failed)."""
        self.running = True
        try:
            return await self._run(director, result, lang)
        finally:
            self.running = False

    async def _run(self, director: Any, result: str, lang: str) -> dict[str, Any]:
        choice: dict[str, Any] = {}

        async def on_call(call: ToolCall) -> None:
            if call.name == "finale" and not choice:
                choice.update(call.arguments() or {})

        prompt = PROMPT.format(result=result, world=WORLD, campaign="\n".join(f"- {c}" for c in director.campaign[-30:]),
                               mood=director.mood or "(steady)", bonds="; ".join(director.bonds_lines()) or "(no bonds recorded)",
                               war=director.war.brief())
        await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt},
                                                   {"role": "user", "content": f"Tell it now. The Captain speaks {LANG_NAMES.get(lang, lang)}."}],
                            tools=[FINALE], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=1100,
                            temperature=0.75, on_tool_call=on_call, allow_fallbacks=True)
        if not choice.get("outcome"):
            log.error("finale: no decision")
            return {}
        log.info("finale: %s — %s", choice.get("outcome"), json.dumps(choice, ensure_ascii=False)[:600])
        # the war map takes the outcome
        changes = []
        for w in choice.get("war") or []:
            sysname = director.war.find(str(w.get("system", "")))
            if sysname:
                changes.append(director.war.update(sysname, w.get("owner"), w.get("threat"), choice.get("decided", "")))
        director.note(f"ARC {director.arc} ENDED — {choice.get('battle_name')}: {choice.get('outcome')} — {choice.get('decided')} "
                      f"({'; '.join(c for c in changes if c)})")
        for line in choice.get("epilogue") or []:
            director.note(f"epilogue: {line}")
        director.note(f"the war goes on: {choice.get('next_arc', '')}")
        # the telling: Rourke on the fleet net, then the cards in the dark
        await self._wait_voice(1.0)
        await self.say("admiral", str(choice.get("admiral_words", "")).strip(), lang, "measured")
        await self._wait_voice(2.0)
        cards = [(str(choice.get("battle_name", "THE BATTLE")).upper(), str(choice.get("decided", "")))]
        cards += [("", str(line)) for line in (choice.get("epilogue") or [])[:3]]
        cards.append(("THE AURELIA MARCH", str(choice.get("closing") or "")))
        await tell(self.command, self.say, self.voice_busy, cards, lang)
        fallen = sum(1 for c in director.campaign if c.startswith("fallen:"))
        if director.announce and changes:
            await director.announce(f"{choice.get('battle_name')}: {choice.get('decided')}")
        log.info("finale told (%d fallen notes)", fallen)
        return choice

    async def _card(self, title: str, sub: str, hold: float, black: bool) -> None:
        try:
            await self.command("story_card", {"title": title, "sub": sub, "hold": hold, "black": black})
        except Exception:  # noqa: BLE001
            log.warning("finale card failed")

    async def _wait_voice(self, extra: float) -> None:
        await asyncio.sleep(0.4)
        for _ in range(130):
            if self.voice_busy() <= 0.2:
                break
            await asyncio.sleep(0.3)
        await asyncio.sleep(extra)


def officers_line() -> str:
    return ", ".join(f"{o.title} ({o.id})" for o in CREW.values())
