"""Who is the Captain talking to while a channel with an enemy commander is open: the bridge crew, the enemy, or both?

Clear cases are decided instantly by name/role heuristics (several languages); ambiguous ones by one small LLM call
that also splits a mixed utterance ("Archon, you have one minute. Tactical, lock missiles on the Acheron")."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

from .openrouter import OpenRouter

log = logging.getLogger("astra.router")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]

# bridge officers by name or role, and ship-order vocabulary (it/en/es/fr/de)
_CREW = re.compile(
    r"\b(serra|ferri|tanaka|voss|martin|nair|mensah|price|okonkwo|numero uno|primo ufficiale|number one|xo|"
    r"timon\w*|helm\w*|tattic\w*|tactical|operazion\w*|operations|ops|comunicazion\w*|comms?|sensor\w*|scienz\w*|"
    r"ingegner\w*|engineering|volo|flight|plancia|bridge|t[aá]ctic\w*|timonel\w*|navigat\w*|steuer\w*|taktik\w*)\b", re.I)
_ORDER = re.compile(
    r"\b(allarme|alert|alerte|alarma|alarm|rotta|course|rumbo|cap|kurs|virare|vira|turn|throttle|avanti tutta|"
    r"fuoco|fire|feu|fuego|feuer|missil\w*|railgun\w*|laser\w*|scudi|shields?|boucliers|escudos|schilde|intercett\w*|"
    r"intercept\w*|potenza|power|energ\w*|squadr\w*|squadron|lanci\w*|launch|scansion\w*|scan|damage control|"
    r"controllo danni|chiud\w* (il )?canale|close (the )?channel|end transmission|fine trasmissione)\b", re.I)
_ENEMY = re.compile(r"\b(archon|solm|kade|vael|quill|hale|ferryman|warden|mandate|mandato|kharon)\b", re.I)
_START_CREW = re.compile(r"^\W*(" + _CREW.pattern[3:-3] + r")", re.I)


@dataclass
class Route:
    crew: str = ""       # what the crew should act on / hear ("" = nothing)
    enemy: str = ""      # what goes over the channel ("" = nothing)
    how: str = ""        # heuristic | llm | fallback


def heuristic(text: str) -> Route | None:
    crewish = bool(_CREW.search(text)) or bool(_ORDER.search(text))
    enemyish = bool(_ENEMY.search(text))
    if _START_CREW.match(text) and not enemyish:
        return Route(crew=text, how="heuristic")
    if crewish and not enemyish:
        return Route(crew=text, how="heuristic")
    if enemyish and not crewish:
        return Route(enemy=text, how="heuristic")
    return None


PROMPT = """On the bridge of a warship, the Captain is speaking while a radio channel with the enemy commander {enemy}
is open. Decide whom each part of the Captain's words is addressed to: the bridge crew (orders, questions to officers)
or the enemy commander over the channel (negotiation, threats, answers to him). Reply with JSON only:
{{"crew": "<the words meant for the crew, verbatim, or empty>", "enemy": "<the words meant for the enemy, verbatim, or empty>"}}"""


async def route(llm: OpenRouter, text: str, enemy_name: str) -> Route:
    quick = heuristic(text)
    if quick is not None:
        return quick
    t0 = time.perf_counter()
    comp = await llm.chat(model=MODEL, providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=200, temperature=0.0,
                          messages=[{"role": "system", "content": PROMPT.format(enemy=enemy_name)},
                                    {"role": "user", "content": text}], allow_fallbacks=True)
    try:
        m = re.search(r"\{.*\}", comp.content, re.S)
        data = json.loads(m.group(0)) if m else {}
        r = Route(crew=str(data.get("crew") or "").strip(), enemy=str(data.get("enemy") or "").strip(), how="llm")
        if not r.crew and not r.enemy:
            r = Route(enemy=text, how="fallback")
    except (ValueError, AttributeError):
        r = Route(enemy=text, how="fallback")
    log.info("route %.2fs (%s): crew=%r enemy=%r", time.perf_counter() - t0, r.how, r.crew[:80], r.enemy[:80])
    return r
