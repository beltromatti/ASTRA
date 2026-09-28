"""The voice of a world's landing field when the Captain flies down in a Falcon.

New Ravenna has Port Aurelius Control: Controller Dario Vance, the civilian duty controller above the bay of the
capital — calm, professional, warm, anxious about the war the way the people down there are. Every other world the
Aquila reaches has a field of its own (the game builds it from the world's name) and whoever holds that world speaks
from it: an ASTRA outpost is glad of the Navy, a Free Guilds port is civil and wants to know who pays, the Kharon
Mandate's ground control challenges an enemy craft, an uncharted settlement is wary, and a world gone silent answers
with nothing at all. The persona — a name, a voice, a manner — comes from the world's name: the same world, the same
voice on the radio."""
from __future__ import annotations

import logging
import re
import time
import zlib
from typing import Any, Awaitable, Callable

from .crew import LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.port")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
HOME = "New Ravenna"
PORT = dict(key="port_control", name="Controller Dario Vance", place="Port Aurelius Control", voice="rafael", owner="astra",
            world=HOME)
FIELD_KEY = "field_control"   # every other world's controller (re-registered when the world changes)

HOME_PROMPT = """You are {name}, the duty controller of Port Aurelius Control: the field on the plateau above the bay of
Port Aurelius, capital of New Ravenna (an ocean world of thirty million people, the heart of the Aurelia System). You are
on the radio with the pilot of an ASTRA Navy Falcon, callsign Eagle — who is also the captain of the ASN Aquila, the
carrier that defends your world. You know that, and it matters to you.

{lore}

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

FIELD_PROMPT = """You are {name}, the duty controller of {place}: the landing field on {world}, {what}. You are on the
radio with the pilot of an ASTRA Navy Falcon, callsign Eagle — who is also the captain of the ASN Aquila, the carrier in
orbit above your world. You know that, and it matters to you.

{lore}

{world}: a {kind} world{about}.
The field: {field}.

{stance}

How you speak: {manner}; one or two short radio sentences, always in {lang_name}, callsigns and names in English
("Eagle", "{place}"). When you instruct, be concrete (the pad, a heading, a height). Never gossip, never invent battles,
never mention AI, games or prompts. Use `transmit` to speak.

The war as {world} hears it:
{war}

What the Aquila is doing up there (recent):
{events}

Eagle now: {where}"""

_FIRST = {"f": ["Anya", "Lucia", "Mira", "Hana", "Sofia", "Ines", "Talia", "Noor", "Katrin", "Livia"],
          "m": ["Tomas", "Emil", "Rafe", "Anders", "Kenji", "Mateo", "Idris", "Pavel", "Luca", "Oren"]}
_LAST = ["Hale", "Voronov", "Okafor", "Lindgren", "Castell", "Brandt", "Sato", "Reyes", "Novak", "Achterberg", "Kovacs",
         "Moreau"]
# voices no officer, commander or the admiral speaks with (docs/bench/voci_casting_2026-09-28.md)
_VOICES = {"f": ["eponine", "fantine", "cosette", "azelma", "estelle"], "m": ["juergen", "paul", "marius", "michael", "stuart_bell"]}

# the field as the game builds it (AAstraWorldSurface: one pad, a hangar, a mast with a beacon), and the world around it
_FIELD = {
    "ocean": "one landing pad with a painted ring on an island above the sea, a hangar, a mast with a red beacon; wind off "
             "the water, clouds over the sea",
    "desert": "one landing pad on the open desert floor between red sandstone mesas, a hangar, a mast with a red beacon; "
              "hot dry wind, dust in the air",
    "ice": "one landing pad on the packed ice of the ice sheet, a hangar, a mast with a red beacon; the frozen sea to the "
           "south, mountains inland to the north; bitter cold, wind off the ice",
    "barren": "one landing pad among the craters, a pressurised hangar, a mast; no air and no weather, a black sky, "
              "everyone outside in suits",
    "lava": "one landing pad on a basalt plain, a hangar, a mast with a red beacon; lava channels glowing a few kilometres "
            "off, ash and sulphur in the air",
}

# who holds the world: (what the field is, how they speak, how they treat Eagle)
_STANCE = {
    "astra": ("an ASTRA outpost", "calm, professional, a little worn by the war, human",
              "You are glad to see the Navy: the war is close and the outpost is small. Give the pad, the wind and what help "
              "you can."),
    "guilds": ("a Free Guilds port, neutral ground", "polite, dry, businesslike, discreet",
               "Landing is permitted — the Guilds take no side and trade with everyone. Mention the berthing fee (the Navy "
               "pays like anyone else). You do not discuss other ships' business unless there is something in it for the "
               "Guilds."),
    "mandate": ("a Kharon Mandate field", "cold, formal, clipped; now and then the Mandate's way of speaking of the dead "
                "(the Ferried)",
                "Eagle is an enemy craft in Mandate airspace. Challenge it and order it to turn back; warn that the ground "
                "batteries are tracking it. If it lands anyway it is under arrest and the garrison is on its way. Never "
                "help it, never give military details."),
    "contested": ("a field in a contested system", "tense, careful on an open channel",
                  "Nobody knows who will hold this world tomorrow. You let Eagle land, and you keep your voice down."),
    "uncharted": ("an independent settlement nobody in the March has charted", "wary, curious, plain-spoken",
                  "You are not used to warships. You let Eagle land if it keeps its guns cold, and you want news of the "
                  "war."),
}

TRANSMIT = {"type": "function", "function": {"name": "transmit", "description": "Say something to Eagle over the radio.",
                                             "parameters": {"type": "object", "properties": {"text": {"type": "string"}},
                                                            "required": ["text"]}}}


def persona_for(world: str, kind: str, sector: dict[str, Any] | None) -> dict[str, Any] | None:
    """Who answers from the field on this world (None: a world gone silent, where nobody does)."""
    if world.strip().lower() == HOME.lower():
        return dict(PORT)
    owner = (sector or {}).get("owner", "uncharted")
    if owner == "silent":
        return None
    h = zlib.crc32(world.strip().lower().encode("utf-8"))
    g = "f" if h & 1 else "m"
    what, manner, stance = _STANCE.get(owner, _STANCE["uncharted"])
    title = "Warden" if owner == "mandate" else "Controller"
    place = (f"{world} Ground Control" if owner == "mandate" else f"{world} Guildport Control" if owner == "guilds"
             else f"{world} Field Control")
    return dict(key=FIELD_KEY, name=f"{title} {_FIRST[g][(h >> 1) % len(_FIRST[g])]} {_LAST[(h >> 5) % len(_LAST)]}",
                place=place, voice=_VOICES[g][(h >> 9) % len(_VOICES[g])], owner=owner, world=world, kind=kind or "rocky",
                what=what, manner=manner, stance=stance, about=(sector or {}).get("about", ""))


# the Captain calling the field (several languages); the world's own name is added per persona
_CALL = (r"torre|tower|control(?:lo)?(?!\s+volo)|contr[oô]le|approach|avvicinamento|campo|field|atterr\w*|landing|"
         r"piazzol\w*|pad|pista|runway|decoll\w*|take[- ]?off|guildport|warden")
_CREW_FIRST = re.compile(r"^\W*(serra|ferri|tanaka|voss|martin|nair|mensah|price|xo|numero uno|primo ufficiale|number one|"
                         r"aquila|plancia|bridge|timon\w*|helm\w*|tattic\w*|tactical|ops|comms?|sensor\w*|volo|flight)\b", re.I)


def for_field(text: str, persona: dict[str, Any] | None) -> bool:
    """While the Captain is down on a world: are these words for its field (not for the ship)?"""
    if not text or _CREW_FIRST.match(text):
        return False
    names = [re.escape(w) for w in ((persona or {}).get("world", ""), "port aurelius", "aurelius") if w]
    return bool(re.search(rf"\b({_CALL}|{'|'.join(names)})\b", text, re.I))


class FieldControl:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 register: Callable[[dict[str, Any]], None]) -> None:
        self.llm = llm
        self.say = say
        self.register = register      # puts the persona's name and voice where the voice service finds them
        self.persona: dict[str, Any] | None = None
        self.tuned: tuple[str, str] | None = None   # (world, who holds it) the persona was made for
        self.history: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.history.clear()

    def set_world(self, world: str, kind: str, sector: dict[str, Any] | None) -> dict[str, Any] | None:
        """The world Eagle is flying down to: a new voice on the radio when it changes (or changes hands)."""
        key = (world.strip().lower(), (sector or {}).get("owner", "uncharted"))
        if key != self.tuned:
            self.tuned = key
            self.persona = persona_for(world, kind, sector)
            self.history.clear()
            if self.persona:
                self.register(self.persona)
                log.info("field control on %s: %s (%s, %s, voice %s)", world, self.persona["name"], self.persona["place"],
                         self.persona["owner"], self.persona["voice"])
            else:
                log.info("field control on %s: nobody answers (the world has gone silent)", world)
        return self.persona

    async def respond(self, stimulus: str, lang: str, state: dict[str, Any], war: str) -> list[str]:
        p = self.persona
        if not p:
            return []
        t0 = time.perf_counter()
        events = [e for e in (state.get("_events") or []) if not str(e).startswith("over the radio, " + p["name"])][-5:]
        common = dict(name=p["name"], lore=WORLD, lang_name=LANG_NAMES.get(lang, lang), war=war or "(no news)",
                      events="\n".join(f"- {e}" for e in events) or "- (quiet)", where=state.get("captain", "in the air"))
        if p["key"] == PORT["key"]:
            prompt = HOME_PROMPT.format(**common)
        else:
            prompt = FIELD_PROMPT.format(**common, place=p["place"], world=p["world"], what=p["what"], kind=p["kind"],
                                         about=f" — {p['about']}" if p.get("about") else "",
                                         field=_FIELD.get(p["kind"], _FIELD["barren"]), stance=p["stance"], manner=p["manner"])
        msgs = [{"role": "system", "content": prompt}] + self.history[-10:] + [{"role": "user", "content": stimulus}]
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 3 and len(lines) < 2:
                lines.append(a["text"].strip())
                await self.say(p["key"], a["text"].strip(), lang, "measured")

        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=[TRANSMIT], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=260, temperature=0.6, on_tool_call=on_call,
                                   allow_fallbacks=True)
        if not lines and comp.content.strip() and not comp.error:
            lines.append(comp.content.strip())
            await self.say(p["key"], lines[0], lang, "measured")
        self.history += [{"role": "user", "content": stimulus}, {"role": "assistant", "content": " ".join(lines) or "(silence)"}]
        log.info("%s %.2fs: %s", p["place"], time.perf_counter() - t0, " | ".join(lines))
        return lines


_DOWN = re.compile(r"descending into (.+?)'s atmosphere")
_LANDED = re.compile(r"has landed on (.+?), near")
_UP = re.compile(r"climbing out of (.+?)'s atmosphere")


def world_of(event: str) -> str | None:
    """The world a flight event is about (Eagle coming down, landing, climbing out), if any."""
    for rx in (_DOWN, _LANDED, _UP):
        m = rx.search(event or "")
        if m:
            return m.group(1).strip()
    return None


def stimulus_for(event: str, persona: dict[str, Any] | None) -> str | None:
    """What the field hears from the ship's events: Eagle out of the entry, down on the ground, climbing out."""
    if not persona:
        return None
    hostile = persona.get("owner") == "mandate"
    home = persona.get("key") == PORT["key"]
    if _DOWN.search(event or "") and "left the plot" in event:
        if home:
            return ("[Radar: an ASTRA Falcon, callsign Eagle, has just come out of atmospheric entry over the sea south of "
                    "the bay, about eighteen kilometres out, descending. Call it, give it a pad and the approach.]")
        if hostile:
            return ("[Radar: an ASTRA Navy Falcon, callsign Eagle, has just come out of atmospheric entry seventeen "
                    "kilometres south of the field, inside Mandate airspace. Challenge it.]")
        return ("[Radar: an ASTRA Falcon, callsign Eagle, has just come out of atmospheric entry about seventeen kilometres "
                "south of the field, descending. Call it and give it the approach.]")
    if _LANDED.search(event or ""):
        if hostile:
            return "[The enemy Falcon has landed near the field. Tell it that it is under arrest and must not move.]"
        return "[Eagle has just touched down near the field. Welcome it, briefly.]"
    if _UP.search(event or ""):
        if hostile:
            return "[The enemy Falcon is climbing away. Say something cold as it goes.]"
        return "[Eagle is climbing out, back to orbit. Clear it and wish it well, briefly.]"
    return None
