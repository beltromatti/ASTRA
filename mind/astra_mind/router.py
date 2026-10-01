"""What the Captain's words let out on an open channel.

On the bridge everyone hears the Captain, as in a real room: the crew's agent gets every word, and each officer judges whether
the words were for them (their prompt says a channel is open and with whom: context.describe). What is left to decide is what goes
out on an open channel — the comms officer's call: the words the Captain says TO the party there (an enemy commander, the admiral,
an allied ship), all of them, a part, or none. It is judgment, so a model makes it (the `router` role: small and fast), with what a
comms officer knows: who is on the channel, whether they have just spoken, whom the Captain is looking at. It runs while the crew's
turn is already under way; only the party waits for it (its own reply takes seconds anyway). When no answer comes in time, nothing
goes out: a comms officer would rather have the Captain repeat himself than put his words on an enemy channel by mistake.

(docs/ARCHITETTURA.md §1bis: no rules over the words. The old router's phrasebook — regular expressions for vocatives, demands and
the ship's vocabulary in five languages — is gone; its test sets, bench/router_*set.py, now grade this model.)
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass

from .context import Context
from .crew import CREW
from .models import chat as role_chat
from .openrouter import OpenRouter

log = logging.getLogger("astra.router")


@dataclass
class Route:
    external: str = ""                   # the Captain's words that go out on the channel, verbatim ("" = nothing)
    party: str = ""                      # the channel's party
    how: str = "no_channel"              # no_channel | model | timeout | error
    ms: float = 0.0
    cost: float = 0.0


PROMPT = """You are the communications officer of a starship. The Captain is speaking aloud on the bridge, and a channel with {party} ({kind})
is open: whatever you let through goes out to {party}. Decide which of the Captain's words were said TO {party}.

Said to them: a demand, a threat, an offer, a question or a reply put to them; calling them by name, ship or rank; "you" aimed at them;
a statement of the Captain's position that only makes sense said to them. When they have just spoken, the Captain's short answers —
a refusal, a promise, a yes or a no, "stop", "enough", "answer me" — are most likely said to them. On a fleet channel, orders and
requests the Captain puts to the admiral or to allied ships are what the channel is for: they go out. When the Captain tells you to pass
something on, pass the message itself.
Staying on the bridge: orders and questions for our own crew ({crew}), talk about {party} in the third person, thinking aloud.
When one sentence is for {party} and another for the crew, let out only the part for {party}, word for word.

The words may be typed fast with slips or come from speech recognition: read them for what they mean, in any language. {situation}
Reply with JSON only: {{"to_party": "<the words for {party}, or an empty string>"}}"""


# the bridge officers as comms knows them: surname and post, the way the Captain calls them in any language
_CREW_LINE = ", ".join(f"{o.name.split()[-1]} the {o.role.lower()}" for o in CREW.values())


def _situation(ctx: Context) -> str:
    ch = ctx.channel
    out = []
    if ch and ch.kind == "fleet":
        out.append("This channel reaches the admiral and the allied ships: an order or a request put to any of them is for the channel.")
    if ch and ch.kind == "flight":
        out.append("This channel is the flight net: the CAG, the squadron leaders (Alpha Lead, Bravo Lead), their wingmen and the Chief of the Deck. A call, an order, a question "
                   "or a request the Captain puts to a pilot, a squadron, the CAG or the deck chief is for the channel, whatever the call sign or the post it uses. Price is Flight "
                   "Control on the bridge, one of our own crew: words to him stay on the bridge.")
    if ch and ch.kind == "marines":
        out.append("This channel is the marine net while boarders are aboard: Major Reyes (Security & Marines, on Deck 8) and the squad leaders in the fight (Reaction 1, Watch 2, "
                   "their sergeants). A call, an order, a question or a request the Captain puts to the marines, a squad or its sergeant, the Major, or about the boarders, the "
                   "bulkheads and doors, the lockdown or the fight inside the hull is for the channel, whatever the name or the post it uses. The bridge's officers (the XO, "
                   "Tactical, the helm...) are our own crew on the bridge: words to them, and orders about the ship, the guns and the fleet, stay on the bridge.")
    if ch and ch.talking:
        said = f': "{ch.last_words}"' if ch.last_words else ""
        out.append(f"{ch.name or ch.party} spoke to the Captain {ch.heard_s:.0f} seconds ago{said} — a short reply may well be for them.")
    elif ch:
        out.append(f"{ch.name or ch.party} has been silent for a while.")
    if ctx.facing:
        out.append(f"The Captain is looking at: {ctx.facing}.")
    return " ".join(out)


def parse(content: str) -> str:
    """The words to let out, from the model's JSON reply ("" when it gave none)."""
    m = re.search(r"\{.*\}", content or "", re.S)
    if not m:
        return ""
    try:
        return str(json.loads(m.group(0)).get("to_party") or "").strip()
    except (ValueError, AttributeError):
        return ""


async def for_party(llm: OpenRouter, text: str, ctx: Context, wait_s: float = 2.5) -> Route:
    """What of the Captain's words goes out on the open channel (nothing when there is no live channel)."""
    ch = ctx.channel
    if not ch or not ch.live:
        return Route()
    t0 = time.perf_counter()
    system = PROMPT.format(party=ch.name or ch.party, kind=ch.kind or "radio", situation=_situation(ctx), crew=_CREW_LINE)
    try:
        comp = await asyncio.wait_for(role_chat(llm, "router", messages=[{"role": "system", "content": system},
                                                                        {"role": "user", "content": text}], max_tokens=200),
                                      timeout=wait_s)
    except asyncio.TimeoutError:
        log.warning("comms: no decision in %.1f s, nothing goes out to %s", wait_s, ch.party)
        return Route(party=ch.party, how="timeout", ms=(time.perf_counter() - t0) * 1000)
    except Exception:  # noqa: BLE001
        log.exception("comms: the router model failed")
        return Route(party=ch.party, how="error", ms=(time.perf_counter() - t0) * 1000)
    ms = (time.perf_counter() - t0) * 1000
    if comp.error:
        log.warning("comms: router model error: %s", comp.error[:120])
        return Route(party=ch.party, how="error", ms=ms, cost=comp.cost)
    return Route(external=parse(comp.content), party=ch.party, how="model", ms=ms, cost=comp.cost)
