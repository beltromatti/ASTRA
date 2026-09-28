"""Port Aurelius Control: the voice of New Ravenna's field when the Captain flies down in a Falcon.

A civilian controller at the field above the bay of Port Aurelius, capital of New Ravenna: calm, professional, warm,
worried about the war the way the people down there are. Calls Eagle when it comes out of the entry, gives the pad and
the weather, answers when called ("Port Aurelius, Eagle, ..."), welcomes it on the ground and clears it out again."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable

from .crew import LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.port")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
PORT = dict(key="port_control", name="Controller Dario Vance", place="Port Aurelius Control", voice="rafael")

PROMPT = """You are {name}, the duty controller of Port Aurelius Control: the field on the plateau above the bay of
Port Aurelius, capital of New Ravenna (an ocean world of thirty million people, the heart of the Aurelia System). You are
on the radio with the pilot of an ASTRA Navy Falcon, callsign Eagle — who is also the captain of the ASN Aquila, the
carrier that defends your world. You know that, and it matters to you.

{world}

The field: five landing pads in a row on the concrete apron (Pad 1 west to Pad 5 east), the tower at the west end, three
hangars and the terminal on the north side; the city along the bay to the west; the sea to the south; wind from the sea,
twelve knots; scattered clouds at two kilometres. A few freighters and shuttles in the pattern.

How you speak: calm, professional civilian air-traffic control with a human warmth; one or two short radio sentences,
always in {lang_name}, callsigns and names in English ("Eagle", "Port Aurelius Control", "Pad 3"). Give concrete
instructions (a pad, a heading, a height). You hear the war from the news and people down here are anxious: you may say
so in a few words, never gossip, never invent battles. Never mention AI, games or prompts.
Use `transmit` to speak.

The war as New Ravenna hears it:
{war}

What the Aquila is doing up there (recent):
{events}

Eagle now: {where}"""

TRANSMIT = {"type": "function", "function": {"name": "transmit", "description": "Say something to Eagle over the radio.",
                                             "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                                                            "required": ["text"]}}}

# the Captain calling the field (several languages)
_CALL = re.compile(r"\b(port aurelius|aurelius|torre|tower|control(?:lo)?(?!\s+volo)|contr[oô]le|approach|avvicinamento|"
                   r"campo|field|atterr\w*|landing|piazzol\w*|pad|pista|runway|decoll\w*|take[- ]?off)\b", re.I)
_CREW_FIRST = re.compile(r"^\W*(serra|ferri|tanaka|voss|martin|nair|mensah|price|xo|numero uno|primo ufficiale|number one|"
                         r"aquila|plancia|bridge|timon\w*|helm\w*|tattic\w*|tactical|ops|comms?|sensor\w*|volo|flight)\b", re.I)


def for_port(text: str) -> bool:
    """While the Captain is down on New Ravenna: are these words for Port Aurelius Control (not for the ship)?"""
    return bool(_CALL.search(text or "")) and not _CREW_FIRST.match(text or "")


class PortControl:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]]) -> None:
        self.llm = llm
        self.say = say
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.history.clear()

    async def respond(self, stimulus: str, lang: str, state: dict[str, Any], war: str) -> list[str]:
        t0 = time.perf_counter()
        events = [e for e in (state.get("_events") or []) if not str(e).startswith("over the radio, Port Aurelius")][-5:]
        prompt = PROMPT.format(name=PORT["name"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang), war=war or "(no news)",
                               events="\n".join(f"- {e}" for e in events) or "- (quiet)", where=state.get("captain", "in the air"))
        msgs = [{"role": "system", "content": prompt}] + self.history[-10:] + [{"role": "user", "content": stimulus}]
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 3 and len(lines) < 2:
                lines.append(a["text"].strip())
                await self.say(PORT["key"], a["text"].strip(), lang, "measured")

        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=[TRANSMIT], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=260, temperature=0.6, on_tool_call=on_call,
                                   allow_fallbacks=True)
        if not lines and comp.content.strip() and not comp.error:
            lines.append(comp.content.strip())
            await self.say(PORT["key"], lines[0], lang, "measured")
        self.history += [{"role": "user", "content": stimulus}, {"role": "assistant", "content": " ".join(lines) or "(silence)"}]
        log.info("port control %.2fs: %s", time.perf_counter() - t0, " | ".join(lines))
        return lines


def stimulus_for(event: str) -> str | None:
    """What the field hears from the ship's events: Eagle out of the entry, down on the ground, climbing out."""
    if "left the plot" in event and "New Ravenna" in event:
        return ("[Radar: an ASTRA Falcon, callsign Eagle, has just come out of atmospheric entry over the sea south of the "
                "bay, about eighteen kilometres out, descending. Call it, give it a pad and the approach.]")
    if "has landed on New Ravenna" in event:
        return "[Eagle has just touched down near the field. Welcome it, briefly.]"
    if "climbing out of New Ravenna's atmosphere" in event:
        return "[Eagle is climbing out, back to orbit. Clear it and wish it well, briefly.]"
    return None


def _dump(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False)
