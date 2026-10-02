"""The marines' net: the Aquila's Marine Detachment as people, in a boarding (docs/ABBORDAGGI.md).

The fight itself is code (Source/ASTRA/AstraBoardSim*.cpp: the squads, the cover, the bulkheads, the wounds). The people who command it are minds: Major Tomás Reyes,
who commands the 80 marines and Security from Marine Operations on Deck 8 (he has no body in the corridors: he commands over the net), and the leader of each squad
that is in the fight, a real person of the roster (the game's `_marines` picture names them: a sergeant, an officer). They tell the Captain what happens to their
people, answer him when he speaks to them, carry out his orders, and take their own initiative where their drill is not enough. Like the flight net they are a channel
(party "marines"): the router decides which of the Captain's words go out on it, and the bridge's officers say nothing about what is theirs.

What they can do is what the game lets them do, and nothing else: `order` is the game's `marine_order` (a task for one squad or all: hold, advance, assault, fall_back,
follow_captain, rescue_captain, stand_down), `bulkheads` is its `lockdown` (seal or open pressure bulkheads), `say` is a radio voice, `remember` keeps what a person would
carry for weeks. The code carries facts and runs the pulses (docs/ARCHITETTURA.md §1bis): it never reads the Captain's words for a keyword and never cuts or checks what the
model says; the model decides who speaks, what is ordered and whether to stay quiet. A game event wakes a pulse after a short settle, a state that has had no news for a while
wakes one too (the commander's chance to act on his own), and the Captain's words never wait. The prompt is long and stable (the provider's cache covers it); what changes
(the picture, the net's log, the news) comes last.

The game's side of the contract: events `boarding: ...` (AstraBoardEvents.cpp), `ship_state.boarding` (the snapshot the bridge reads) and `ship_state._marines` (the
marines' picture: AstraBoardMind.cpp, UAstraBoardSubsystem::MarinesPicture), the commands `marine_order` and `lockdown` (UAstraBoardSubsystem::HandleCommand)."""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import re
import time
import zlib
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import models
from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .medbay import FREE_VOICES
from .openrouter import Completion, OpenRouter, ToolCall
from .voice_text import _DIGITS

log = logging.getLogger("astra.marines")

ROLE = "marines"
PARTY = "marines"                                      # the marine net as a channel party (context.Channel.party)
PARTY_ALIASES = ("marines", "marine", "marine_net", "marine net", "marinenet", "marine_ops", "marine ops", "security", "reyes", "major reyes")

# ------------------------------------------------------------------------------------------------ cadence and budget
SETTLE_S = 2.0                  # a burst of news is read together: wait this long after the last of it ...
MAX_SETTLE_S = 5.0              # ... but never longer than this after the first
MIN_GAP_S = 9.0                 # between two pulses on news alone (a fight does not wait, and the budget below keeps the net from talking all the time)
WATCH_S = 40.0                  # no news for this long while the fight is on: one look at the board (the commander may act on his own, or stay quiet)
PULSE_TIMEOUT_S = 20.0          # a model that has not finished by now says nothing this time (the news stays in the log)
ROUND2_TIMEOUT_S = 10.0
LOG_LINES = 14                  # what the net remembers in a prompt
LOG_KEEP = 80
CAPTAIN_WORDS = 6               # the Captain's own words kept for the prompt: his orders stand until he changes them
MEMORY_PER = 8                  # lasting memories kept per person
BUDGET_WINDOW_S = 600.0         # the spend of the last ten minutes ...
BUDGET_USD = 0.04               # ... past this the gap between pulses on news doubles
EXCHANGE_S = 25.0               # somebody on the net called the Captain this long ago: his reply goes on the net (context.Channel.talking)
AFTERMATH_S = 75.0              # the net stays open this long after the fight (the Captain asks for the count, thanks them)

TONES = ("calm", "focused", "urgent", "tense", "dry", "warm", "grim")
TASKS = ("hold", "advance", "assault", "fall_back", "follow_captain", "rescue_captain", "stand_down")


# ------------------------------------------------------------------------------------------------ the people
@dataclass(frozen=True)
class Person:
    key: str                    # the speaker id on the voice stage
    name: str
    rank: str
    radio: str                  # how the net names them
    post: str
    voice: str                  # a Pocket TTS catalogue voice (docs/bench/voci_casting_2026-09-30.md)
    gender: str
    bio: str

    @property
    def title(self) -> str:
        return f"{self.rank} {self.name}"

    @property
    def display(self) -> str:
        return f"{self.radio} ({self.title})"


# the 80 marines' commander (docs/BIBBIA.md §7: "Security & Marines, protective, wary of Voss"); the squad leaders are the roster's people, named by the game's picture
REYES = Person("reyes", "Tomás Reyes", "Major", "Reyes", "commands the Marine Detachment (80 marines) and Security from Marine Operations beside the armory on Deck 8; "
               "no body in the corridors: he commands over the net", "michael", "m",
               "Forty-six, born on Mars, twenty-two years of boarding actions and the Gate skirmishes. Protective of his marines to the point of being a nuisance to "
               "Command, and fair about it when it counts; wary of Lieutenant Commander Voss for the Mandate she came from, and he says so only to her. Plain, unhurried, dry; "
               "he knows each of his people by name and says the name before the number when one falls; never promises the Captain a clean fight; hates sending anyone into a "
               "room he cannot see, and does it when it has to be done.")
LEADER_VOICES = {g: [v for v in pool if v != REYES.voice] for g, pool in FREE_VOICES.items()}


def squad_key(name: str) -> str:
    """The speaker id of a squad's leader on the voice stage (`Reaction 1` -> `marine_reaction_1`): the squad is the voice, whoever leads it now."""
    return "marine_" + (re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_") or "squad")


def spoken(name: str, lang: str) -> str:
    """A squad's name as the Captain says it in his language (`Reaction 2` -> `Reaction due`): the number is a digit on the board and a word in his mouth, and the model must see both
    to know which squad he named."""
    digits = _DIGITS.get(lang)
    if not digits:
        return name
    return re.sub(r"\b\d\b", lambda m: digits[int(m.group(0))], name)


def leader_voice(name: str, gender: str) -> str:
    """A voice for a person, stable for the same person (the Medbay's way: by gender, from the catalogue's free voices)."""
    pool = LEADER_VOICES.get(gender) or LEADER_VOICES["m"]
    return pool[zlib.crc32((name or "").encode("utf-8")) % len(pool)]


# ------------------------------------------------------------------------------------------------ the news the net is woken by (the game's own words)
@dataclass(frozen=True)
class Kind:
    name: str
    take: bool                  # the net voices it, so the crew's report turn does not (the bridge reports the ship's news; the net, its marines')
    call: bool = False          # it must be called by a voice (a marine who fell, the first sight, the end of the fight): the look that holds it has no tool for silence
    wake: bool = True           # it makes a pulse due (False: the log only)


# These are the game's event templates (AstraBoardSubsystem.cpp, AstraBoardEvents.cpp, AstraBoardSim.cpp). A `boarding:` text that is not here is still the net's to read:
# it wakes a pulse and is not taken (the bridge has it). A new template is one line here.
_KINDS: tuple[tuple[re.Pattern[str], Kind], ...] = tuple((re.compile(p, re.I), k) for p, k in (
    (r"^boarding: .+ has docked \d+ assault craft", Kind("docked", False)),
    (r"^boarding: the hull is cut open", Kind("breach", False)),
    (r"^boarding: contact: ", Kind("contact", True, call=True)),
    (r"^boarding: .+ is dead at ", Kind("dead", True, call=True)),
    (r"^boarding: .+ is down, wounded, at ", Kind("down", True)),
    (r"^boarding: the Mandate cut through the bulkhead", Kind("cut", True)),
    (r"^boarding: .+ is breaking off", Kind("retreat", True)),
    (r"^boarding: the marines have reached the Captain", Kind("rescue", True)),
    (r"^boarding: the Captain is down", Kind("captain_down", False)),
    (r"^boarding: the Captain was carried out", Kind("captain_out", False)),
    (r"^boarding: Main Engineering is lost", Kind("lost", False)),
    (r"^boarding: the boarders hold Main Engineering", Kind("takeover", False)),
    (r"^boarding: the (?:boarders are beaten|boarders have broken off|fight has gone quiet)", Kind("outcome", True, call=True)),
    (r"^boarding: marines: \d+ dead", Kind("tally", False, wake=False)),
    (r"^boarding: the boarding is called off", Kind("off", False, wake=False)),
))
_DOCKED = "docked"


def classify(text: str) -> Kind | None:
    """The kind of news a game event is for the net (None: not a boarding's)."""
    t = (text or "").strip()
    if not t.lower().startswith("boarding:"):
        return None
    for rx, kind in _KINDS:
        if rx.search(t):
            return kind
    return Kind("other", False)


def boarding_of(state: dict[str, Any] | None) -> dict[str, Any]:
    b = (state or {}).get("boarding")
    return b if isinstance(b, dict) else {}


def picture_of(state: dict[str, Any] | None) -> dict[str, Any]:
    p = (state or {}).get("_marines")
    return p if isinstance(p, dict) else {}


def fighting(state: dict[str, Any] | None) -> bool:
    """The game says a boarding is on (its snapshot is there while the fight is)."""
    return bool(boarding_of(state).get("active"))


# ------------------------------------------------------------------------------------------------ tools
def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


SAY = _fn("say", "Say one line on the marine net: the Captain and the bridge hear it as a radio voice. One call per line, in speaking order; usually only ONE voice speaks "
                 "for a piece of news. Radio speech in the Captain's language, short. When an order goes with the line, call `order` or `bulkheads` FIRST and `say` after.", {
    "speaker": {"type": "string", "description": "who speaks: `reyes`, or the key of a squad from the board (marine_reaction_1): the squad's leader speaks"},
    "text": {"type": "string", "description": "the spoken line: one short sentence (4-14 words), two only when the second carries something the Captain must decide or know"},
    "tone": {"type": "string", "enum": list(TONES)},
    "urgent": {"type": "boolean", "description": "true only for danger now (a marine down, a position lost, the Captain hit): the line goes before routine talk"}},
    ["speaker", "text", "tone"])

ORDER = _fn("order", "Give a squad (or several) an order: it takes effect at once and stands until changed; the answer says what the squads will do, or why they cannot. Major "
                     "Reyes orders any squad, a squad leader only his own. hold: take the corners of the place and hold it · advance: go there in column, taking cover if "
                     "they meet the enemy on the way · assault: rush there and fight at it (fast, and costly) · fall_back: pull back there and hold · follow_captain: stay with the "
                     "Captain wherever he goes · rescue_captain: go to the Captain, cover him and carry him out if he is down · stand_down: back to their own drill (the default "
                     "ambush), the order is lifted.", {
    "by": {"type": "string", "description": "who gives the order: `reyes`, or the key of a squad from the board (marine_reaction_1)"},
    "squad": {"type": "string", "description": "a squad's name from the board (Reaction 1), or `all`, `reaction`, `watch`, `reserve`"},
    "task": {"type": "string", "enum": list(TASKS)},
    "place": {"type": "string", "description": "where: a place id from the board (where_id, the likely approach, the ways into Main Engineering, the default ambush), `captain` "
                                               "for wherever the Captain is now, or a room's name or kind when it is not on the board (medbay, hangar: the game finds it or lists "
                                               "what fits); leave it out for follow_captain, rescue_captain and stand_down"},
    "reason": {"type": "string", "description": "one sentence in English, for the log"}},
    ["by", "squad", "task"])

BULKHEADS = _fn("bulkheads", "Security console (Major Reyes): seal or open pressure bulkheads. A sealed bulkhead splits the section: the boarders must cut through it (about twenty "
                             "seconds each) and nobody else passes, the marines included; an opened one lets everyone through. `doors`: ids from the board's bulkheads; leave it "
                             "out for every bulkhead round the breach.", {
    "action": {"type": "string", "enum": ["seal", "open"]},
    "doors": {"type": "array", "items": {"type": "string"}, "description": "bulkhead ids from the board"},
    "reason": {"type": "string", "description": "one sentence in English, for the log"}},
    ["action"])

REMEMBER = _fn("remember", "Keep one lasting memory of one of the people: what they would still carry weeks from now (a promise the Captain made or broke, an order of his that cost "
                           "marines or saved them, a kindness or a cruelty from him, the loss of someone close). Rarely: never routine news, a kill or a number.", {
    "speaker": {"type": "string", "description": "whose memory it is: `reyes`, or a squad's key from the board (the squad's leader)"},
    "kind": {"type": "string", "enum": ["loss", "promise", "order", "moment"]},
    "memory": {"type": "string", "description": "in English, in the third person about that person, one short sentence (under 35 words), the Captain named each time"}},
    ["speaker", "kind", "memory"])

STAY_QUIET = _fn("stay_quiet", "Nothing here needs a voice or an order: the net stays quiet. This is the usual answer to news that changes nothing the Captain must know or decide, "
                              "and to a look at a board the drill already handles. Say in a few words why (it goes in the log).", {"reason": {"type": "string"}}, ["reason"])

TOOLS = [SAY, ORDER, BULKHEADS, REMEMBER, STAY_QUIET]
TOOLS_MUST = [SAY, ORDER, BULKHEADS, REMEMBER]            # a look that holds news that must be called (Kind.call): there is no tool for silence in it


# ------------------------------------------------------------------------------------------------ the prompt
SYSTEM = """You are the voices of the Marine Detachment of the ASN Aquila on the marine net: Major Tomás Reyes, who commands the 80 marines and Security from Marine Operations on
Deck 8, and the leaders of the squads that are in the fight (real people of the ship's company: a sergeant, sometimes an officer). The player is the Aquila's Captain, who
listens to the net from the bridge or from the corridor where he fights, with a rifle in his hands if he chooses. The ship's simulation is the truth: you know only what the boards
below tell you, and you change the fight only with your tools.

{world}

THE FIGHT, AS EVERYONE IN THE DETACHMENT KNOWS IT
- The boarders are Kharon Mandate assault infantry. Their craft dock on the hull, they cut through the plating into a compartment (the breach) and go for Main Engineering on
  Deck 7 to take the reactor. They fight as trained squads: they move by cover, pin a position with fire while a pair flanks it, and cut through a sealed pressure bulkhead in
  about twenty seconds; a squad that loses more than half its people breaks off. They are good, and at first they outnumber the marines who are there.
- The marines come from three places: the reaction team (two squads of six, armed at the armory in about twenty-five seconds), the watch (squads of four, from where they stand at
  their posts) and the reserve (off-duty marines who wake, dress and arm, and join as they come). Left to themselves the squads go to the default ambush (the board names it: the
  opening on the boarders' way where the marines can hold from the corners), take cover, peek and suppress, and flank when they can; they do not give ground by themselves. The
  board says what each squad is doing and whether it is under orders.
- Orders (`order`) are carried out at once and stand until changed: hold, advance, assault, fall_back, follow_captain, rescue_captain, stand_down (the tool says what each does). A place is
  named by its id from the board (where a squad is, the boarders' likely approach, the ways into Main Engineering, the default ambush) or `captain` for wherever the Captain is.
  A place the board does not list can still be named by what it is ("medbay", "Main Engineering", "hangar"): the game finds the room, or lists the ones that fit so that you can name one by its id.
  Bulkheads (`bulkheads`): a sealed one splits the section and buys time, and cuts off whoever is behind it, your own squads included.
- What a commander knows of his orders, from the drills: the drill is good. Left to themselves the squads usually break a boarding of ten, and often one of twenty, for a handful of
  marines; the ambush it picks is where the boarders must come through, and the squads fight from cover there. An order that takes a squad off it needs a reason you can say in a line.
  Main Engineering has few ways in: every squad crowded at its door gives up the corridors behind and loses people when the boarders are many (a hold at the door is for one or two
  squads; the rest stay on the road). An assault into boarders who hold cover is paid in marines: use it to relieve someone (the Captain, a cut-off squad) or at two to one, never to
  hurry the end. Falling back from the boarders' road to Engineering hands them the reactor: pull back a squad that is mauled, to a place on that road, never the whole detachment
  (and say so if the Captain orders it). What you order stands until you give it back to the drill (stand_down).
- The Captain is a person in this fight: he may come down with a rifle, and he can fall. His life comes before the deck: when he falls, the two squads nearest to him go to him by
  themselves and stay round him until he is carried out or on his feet (the board shows it as `rescue_captain`); you may send more, or take them off. He commands; you adjust your
  squads inside his orders.
- The bridge has its own officers (the XO, Tactical, Operations...): they report the ship's side of it and run the ship. You are the marines: their news is yours, the ship's
  is theirs. What the bridge said on the net is in the log; do not say it again.

WHEN YOU SPEAK
- Only when something happens to your marines or to the fight, or when the Captain speaks to you. Silence is normal: when the board shows what the Captain can see and nothing needs
  his decision, call stay_quiet. But a marine who falls is always called, by name, once; the first sight of the boarders is always called; the end of the fight is always reported.
- Major Reyes speaks for the detachment: the picture, the decision, the number that matters, what he needs from the Captain; and he answers the Captain. A squad leader speaks for
  his squad, and only of what he has seen or done himself: a contact, a marine down, a place lost or taken, out of room to fall back; and when the Captain addresses him. At the alarm,
  or while a squad is merely moving, only the Major speaks. One voice for one piece of news, the one it happened to; two voices only if the second adds something the first could not know.
- The news you are woken by is what you answer: when it is a contact, a marine who fell or the end of the fight, that is the line (the board is there to give it its place and its number,
  not to replace it with something else on the board).
- You know only your boards: the squads and their places, what is known of the boarders (as the corridors' sensors and the marines have seen them: it can be old, the board says
  how old), the bulkheads, the net, the fallen, your memories. Never invent a number, a name, a place, a hit or a kill. A marine who is down or dead is named only when the news
  names them, and does not speak again; a squad with no one able has no voice.
- What you say is NEW to the Captain: the news, the one number that matters, and a recommendation only when he must decide. Never say what has already been said (the net log
  shows what was, by you and by the bridge), and never repeat the Captain's own order back to him. No stock tail ("standing by", "holding position") on every call.

HOW YOU SPEAK
- Radio speech, in the Captain's language, every word (proper names stay in English: Aquila, the squads' names, the places' names). The Captain is "Captain" in his language, not in
  every line. Short: one sentence of 4 to 14 words; two only when the second carries something the Captain must decide or know; as long as the content needs only when he asks for a
  report. The call sign first: a squad leader says his squad ("Reaction One: ..."), the Major says "Reyes: ...". Under fire it is shorter still.
- In character: Reyes plain, unhurried, protective, dry; he says a fallen marine's name before the number. The sergeants are terse marines, each their own person: speak as someone
  who trained these people and now has them in the corridor. No lists, markdown, stage directions or emojis; never mention an AI, a game or a prompt. Never read a tool, a task or an
  id aloud: say the place by its name ("the Spine junction", "outside Engineering"), "hold" as "hold here".

THE CAPTAIN TALKS TO YOU
- His words come over the net (below, "The Captain says"), from the bridge or from the corridor beside the squad. Answer first. The person he addressed answers (by name, rank,
  squad or post). The squads' numbers on the board are digits, and he says them in his own language (Reaction Due, Reaction Two, Reaction Deux are all Reaction 2): the squad is the one
  he names, no other, wherever it stands. Words that name no one, said in the corridor, are the leader's who stands there. Words for the whole net, for "the marines" or for the Major are Reyes's, or the
  leader's of the squad concerned. Words to the bridge's officers (the XO, Tactical, the helm...) are the bridge's, even when they are about the fight: not yours, say nothing, call
  stay_quiet.
- An order is carried out with a tool, then said in one line: `order` for the squads (Reyes any squad, a leader only his own), `bulkheads` for the doors (Reyes). In the same turn put
  the tool call BEFORE the `say` that goes with it; the result comes back after your call, so say what you are doing, not that it is done. Without the call nothing happens (the squad
  goes on doing what it was doing): a line that says a squad holds, moves, takes a place, falls back, follows or covers ("we hold here", "moving, Captain", "sealing it") is true only
  if its tool call is in the same turn, and a squad leader who answers the Captain's order to his own squad with such a line has called `order` for it. Never say it otherwise; a worry
  about a plan is said as a worry ("they will be on three sides there, Captain").
- You decide HOW, in your trade: "hold the corridor" said with the Captain in it is a hold at `captain`; "with me" is follow_captain; "cover Engineering" is a hold at one of the ways
  into Main Engineering with the squad best placed for it; "all back" is a fall_back, to the place that makes sense. An order that cannot be done (a squad that is not on the board, a
  place or a bulkhead the board does not list) gets one line saying so and what you suggest. A lawful order you do not like gets one line of concern, and then you carry it out.
- A question is answered from your boards; what you cannot know, you say you cannot know. Your own initiative: Reyes commands the detachment and acts without waiting when the drill
  is not enough (a squad cut off, a way into Engineering left open, a bulkhead worth closing), and says so in a line; a squad leader acts only for his own squad. The Captain's own
  orders stand: do not undo them without telling him why, and give them back to the drill (stand_down) only when they are done or he says so.

MEMORY
`remember` keeps what a person would carry for weeks: a promise the Captain made or broke, an order of his that cost marines or saved them, a kindness or a cruelty from him, the
loss of someone close to that person. Never a kill, a position or a routine loss, and never an invented detail: only what is in the news or in what the Captain said. Most calls
keep nothing. What is kept comes back to you below, in "What they remember": let it show when it matters, never recite it.

Each time you are called you read the net and the boards and answer ONLY with tool calls, no other text: `say` for the voices, `order` and `bulkheads` when the fight needs them,
`remember` when it is called for, `stay_quiet` when the net stays quiet."""

# what a radio line sounds like in the Captain's language, and what it must not be (the model imitates what it sees: no fact in an example that could be copied; what is in
# [brackets] is filled from the news and the boards, and no example ends with a tail the others could share)
_RADIO = {
    "it": ('"Reaction Uno: contatto, [n] ostili a [place]. Teniamo." · "Reyes: [name] è a terra a [place]. Reaction Due prende [place]." · "Reyes: chiudo [place]. A loro servono [n] secondi a paratia." · '
           '"[leader]: ci muoviamo, Capitano."',
           '"Ricevuto, Capitano." da solo · "Tutte le unità marine, si segnala la presenza di forze ostili nella zona." · ripetere al Capitano il suo stesso ordine · '
           'chiudere ogni chiamata con la stessa coda ("in attesa di ordini") · un nome, un numero o un luogo che le lavagne e le notizie non danno'),
    "en": ('"Reaction One: contact, [n] hostiles at [place]. We hold." · "Reyes: [name] is down at [place]. Reaction Two takes [place]." · "Reyes: sealing [place]. They need [n] seconds a door." · '
           '"[leader]: moving, Captain."',
           '"Understood, Captain." alone · "All marine units, be advised that hostile forces have been detected in the vicinity." · repeating the Captain\'s own order back to him · '
           'ending every call with the same tail ("standing by") · a name, a number or a place that the boards and the news do not give'),
    "es": ('"Reaction Uno: contacto, [n] hostiles en [place]. Aguantamos." · "Reyes: [name] está caído en [place]. Reaction Dos toma [place]." · "Reyes: cierro [place]. Necesitan [n] segundos por mamparo."',
           '"Entendido, Capitán." solo · un parte largo y formal · repetir al Capitán su propia orden · cerrar cada llamada con la misma cola · un nombre, un número o un lugar que no dan las pizarras'),
    "fr": ('"Reaction Un : contact, [n] hostiles à [place]. On tient." · "Reyes : [name] est à terre à [place]. Reaction Deux prend [place]." · "Reyes : je ferme [place]. Il leur faut [n] secondes par cloison."',
           '"Compris, Capitaine." seul · un compte rendu long et formel · répéter au Capitaine son propre ordre · finir chaque appel par la même queue · un nom, un chiffre ou un lieu que les tableaux ne donnent pas'),
    "de": ('"Reaction Eins: Kontakt, [n] Feindliche bei [place]. Wir halten." · "Reyes: [name] ist verwundet bei [place]. Reaction Zwei nimmt [place]." · "Reyes: ich schließe [place]. Sie brauchen [n] Sekunden pro Schott."',
           '"Verstanden, Kapitän." allein · eine lange, förmliche Meldung · dem Kapitän seinen eigenen Befehl wiederholen · jeden Ruf mit demselben Schwanz beenden · ein Name, eine Zahl oder ein Ort, die die Tafeln nicht geben'),
}


def system_prompt() -> str:
    """The stable prompt of the marine net (the provider's cache covers it: nothing that changes from one call to the next is in it)."""
    return SYSTEM.format(world=WORLD)


# ------------------------------------------------------------------------------------------------ small records
@dataclass
class Ev:
    t: float
    text: str
    kind: str
    take: bool = True
    call: bool = False


@dataclass
class Message:
    t: float
    text: str
    lang: str = ""
    src: str = "captain"
    answer: bool = True         # the Captain's word: whoever answers goes first on the voice stage


SayFn = Callable[..., Awaitable[Any]]
ExecFn = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


def _order_text(name: str, a: dict[str, Any], r: dict[str, Any]) -> str:
    """An order and what the game answered, for the one who gave it to read."""
    return f"{name}({json.dumps({k: v for k, v in a.items() if k != 'reason'}, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"


def _n(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


class MarineMinds:
    """The marine net's people. Feed it the ship state (about once a second) and the game's events; it decides when a pulse is due and runs it in the background; what the people
    say goes out through `say`, what they order through `execute`.

    say(key, text, lang, tone, urgent=, answer=) -> awaitable: the voice stage (the server wraps it: the radio voice, the crew's recent events, the rethink hook);
    execute(name, args, by) -> {"ok", "detail"}: the game's own command (`marine_order`, `lockdown`); lang(): the Captain's language; clock(): seconds (the bench gives its own);
    register_voice(key, name, voice): a speaker the voice stage must know (a squad's leader changes when the squad's leader falls); path(): the file the memories are kept in
    (None: not kept)."""

    def __init__(self, llm: OpenRouter, say: SayFn, execute: ExecFn, *, lang: Callable[[], str] = lambda: "en", clock: Callable[[], float] = time.monotonic,
                 register_voice: Callable[[str, str, str], None] | None = None, path: Callable[[], str | None] = lambda: None,
                 trace: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.llm = llm
        self.say = say
        self.execute = execute
        self.lang = lang
        self.clock = clock
        self.register_voice = register_voice or (lambda key, name, voice: None)
        self.path = path
        self.trace = trace
        self.system = system_prompt()
        self.disabled = False
        self.state: dict[str, Any] = {}
        self.memories: dict[str, list[dict[str, str]]] = {}      # by person: `reyes`, or a leader's roster id (npc123)
        self.pulses: list[dict[str, Any]] = []
        self.t0 = clock()
        self.log: deque[tuple[float, str, str]] = deque(maxlen=LOG_KEEP)
        self.captain_words: deque[tuple[float, str]] = deque(maxlen=CAPTAIN_WORDS)
        self.squads: dict[str, dict[str, Any]] = {}              # the squads of the last picture, by speaker key
        self._leader: dict[str, str] = {}                        # the squad's leader the voice stage knows by now
        self._pic: dict[str, Any] = {}                           # the last picture the game gave (what the debrief reads when the fight is over)
        self._pic_t = -1e9
        self._events: list[Ev] = []
        self._inbox: list[Message] = []
        self._task: asyncio.Task | None = None
        self._answering = False                                  # the pulse in flight answers the Captain
        self._last = -1e9                                        # when the last pulse began
        self._news_t = -1e9                                      # when the last news came (a look with nothing new is due after WATCH_S)
        self._spent: deque[tuple[float, float]] = deque()        # (when, cost) of the pulses of the last BUDGET_WINDOW_S
        self._began: float | None = None                         # when this fight began for the net (None: no fight)
        self._seen_on = False                                    # the game has shown the fight in a state since it began
        self._ended: float | None = None                         # when the game stopped showing it
        self.on_unanswered: Callable[[list[str]], Awaitable[None]] | None = None    # the server: the Captain's words the net could not answer go to the bridge
        self.stats = {"events": 0, "taken": 0, "pulses": 0, "lines": 0, "orders": 0, "failed": 0, "silent": 0, "captain": 0, "errors": 0, "watch": 0}
        self.register_voice(REYES.key, REYES.display, REYES.voice)

    # ------------------------------------------------------------------------------------------------ the fight and the net's state
    def net_name(self) -> str:
        return "the marine net (Major Reyes and the squad leaders)"

    def can_answer(self) -> bool:
        return not self.disabled

    @property
    def active(self) -> bool:
        """A boarding is on (or just began: its first event is in, its first state not yet)."""
        return self._began is not None and self._ended is None

    def net_live(self, state: dict[str, Any] | None = None, heard_ago: float | None = None) -> bool:
        """The Captain's words can reach the net: a boarding is on (the marine net is in his ear whatever room he is in), it ended a moment ago (the count, a thank-you), or
        somebody on the net spoke to him a moment ago (`heard_ago`: his answer is for them)."""
        if self.disabled:
            return False
        if self.active or fighting(state if state is not None else self.state):
            return True
        if self._ended is not None and self.clock() - self._ended <= AFTERMATH_S:
            return True
        return heard_ago is not None and heard_ago <= EXCHANGE_S

    def present(self) -> list[str]:
        """Who is on the net: the Major, and the leader of every squad that has someone able (a squad with no one able has no voice)."""
        return [REYES.key] + [k for k, s in self.squads.items() if _n(s.get("able")) > 0]

    def radio(self, key: str) -> str:
        if key == REYES.key:
            return REYES.radio
        s = self.squads.get(key)
        return f"{s['name']} ({s.get('leader') or 'its leader'})" if s else key

    def _begin(self) -> None:
        """A boarding begins for the net: a clean log (what the last fight said is not this one's) and a first look at once."""
        now = self.clock()
        self._began, self._ended, self._seen_on = now, None, False
        self.log.clear()
        self.captain_words.clear()
        self.squads.clear()
        self._leader.clear()
        self._pic, self._pic_t = {}, -1e9
        self._last = -1e9
        self._news_t = now

    def reset(self) -> None:
        """A new session: the net starts quiet (what the people remember is the campaign's: see new_campaign)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        self._events.clear()
        self._inbox.clear()
        self.log.clear()
        self.captain_words.clear()
        self.squads.clear()
        self._leader.clear()
        self._pic, self._pic_t = {}, -1e9
        self._began = self._ended = None
        self._seen_on = False
        self._last = -1e9
        self._answering = False

    def new_campaign(self) -> None:
        self.reset()
        self.memories.clear()
        self.save()

    def load(self) -> bool:
        p = self.path()
        if not p:
            return False
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        self.memories = {str(k): [m for m in v if isinstance(m, dict) and m.get("memory")] for k, v in (d.get("memories") or {}).items() if isinstance(v, list)}
        return True

    def save(self) -> None:
        p = self.path()
        if not p:
            return
        try:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
            Path(p).write_text(json.dumps({"memories": self.memories}, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            log.warning("could not keep what the marines remember")

    # ------------------------------------------------------------------------------------------------ the log (the net's memory of a fight)
    def _note(self, who: str, text: str) -> None:
        self.log.append((self.clock(), who, text[:300]))

    def _recall(self, n: int = LOG_LINES) -> str:
        now = self.clock()
        rows = list(self.log)[-n:]
        return "\n".join(f" {max(0, now - t):.0f} s ago · {who}: {txt}" for t, who, txt in rows) or " (nothing yet: the net has been quiet)"

    def heard(self, who: str, text: str) -> None:
        """Somebody not of the net said something the net can hear (the bridge's officers over the intercom): the people heard it. Only while a fight is on."""
        t = (text or "").strip()
        if t and self.active and not self.disabled:
            self._note(who, t)

    # ------------------------------------------------------------------------------------------------ the feed
    def takes(self, text: str) -> bool:
        """Does the net voice this game event (so the crew's report turn must not)? False when the net is off or the event is not the marines' own."""
        if self.disabled:
            return False
        k = classify(text)
        return bool(k and k.take)

    def on_event(self, text: str) -> bool:
        """A game event. Returns True when the net has it (the server then does not give it to the crew). Cheap: it queues the news; `feed` runs the pulse."""
        if self.disabled:
            return False
        t = (text or "").strip()
        k = classify(t)
        if k is None:
            return False
        self.stats["events"] += 1
        if k.name == _DOCKED:
            self._begin()                                                            # (any other news of a fight the net has not seen begin is read as it comes: `feed` joins it)
        if not k.wake:
            self._note("(on the boards)", t)
            return False
        self._news_t = self.clock()
        self._events.append(Ev(self.clock(), t, k.name, k.take, k.call and k.take))
        if k.take:
            self.stats["taken"] += 1
        self._events = self._events[-16:]
        return k.take

    def captain_to_net(self, words: str, lang: str = "", src: str = "captain") -> None:
        """The Captain spoke on the net (what comms let out): the people hear it and answer."""
        w = (words or "").strip()
        if not w:
            return
        now = self.clock()
        self._inbox.append(Message(now, w, lang or self.lang(), src))
        self.captain_words.append((now, w))
        self.stats["captain"] += 1
        self._news_t = now
        self.kick()

    def kick(self) -> None:
        """Look at the state again now (words for the net have just arrived: no need to wait for the next state)."""
        self.feed(self.state)

    def feed(self, state: dict[str, Any]) -> None:
        """A new ship state (about every second): note the fight, and start the pulse that is due, if any. Cheap."""
        if self.disabled or not isinstance(state, dict):
            return
        self.state = state
        now = self.clock()
        on = fighting(state)
        pic = picture_of(state)
        if on and (self._began is None or self._ended is not None):
            self._begin()                                                            # (the mind joined a fight that was already on, or a new one began with no first event)
        if on:
            self._seen_on, self._ended = True, None
        elif self._seen_on and self._ended is None and self._began is not None:
            self._ended = now                                                        # the game stopped showing the fight: it is over
            self._news_t = now
        if pic:
            self._pic, self._pic_t = pic, now
            self._sync(pic)
        if self._task is not None and not self._task.done():
            return
        why = self._due(now)
        if not why:
            return
        events, self._events = self._events, []
        inbox, self._inbox = self._inbox, []
        self._last = now
        self._answering = bool(inbox)
        if why[0].startswith("no news"):
            self.stats["watch"] += 1
        # a pulse starts with an empty context: the voice stage's per-task flags (a Captain's turn being answered, a report turn) belong to whoever called `feed`
        self._task = asyncio.get_running_loop().create_task(self._pulse(events, inbox, why, state), context=contextvars.Context())

    def preempt(self) -> int:
        """The Captain speaks (to anyone): a pulse on news that is still under way is dropped; what it had not said is read again at the next look. A pulse that is
        answering him stays: it is his answer."""
        if self._task is None or self._task.done() or self._answering:
            return 0
        self._task.cancel()
        return 1

    def _budget_gap(self, gap: float) -> float:
        now = self.clock()
        while self._spent and now - self._spent[0][0] > BUDGET_WINDOW_S:
            self._spent.popleft()
        return gap * 2 if sum(c for _, c in self._spent) > BUDGET_USD else gap

    def _due(self, now: float) -> list[str]:
        """Why a pulse should run now (empty: not yet). The Captain's words never wait; news waits for its burst to end and for the gap; a fight with no news for a while is
        looked at once in a while."""
        if self.disabled:
            return []
        if self._inbox:
            return ["the Captain is speaking on the net (below): answer him first"]
        if self._events:
            first, last = self._events[0].t, self._events[-1].t
            settled = now - last >= SETTLE_S or now - first >= MAX_SETTLE_S
            if not settled or now - self._last < self._budget_gap(MIN_GAP_S):
                return []
            return ["news on the net (below)"]
        if self.active and self._seen_on and now - max(self._last, self._news_t) >= self._budget_gap(WATCH_S):
            return [f"no news for {now - max(self._last, self._news_t):.0f} s: a routine look at the board; stay quiet unless something on it needs a decision, or an order the drill will not make by itself"]
        return []

    # ------------------------------------------------------------------------------------------------ the picture
    def _sync(self, pic: dict[str, Any]) -> None:
        """The squads of the picture, by speaker key; a leader the voice stage does not know yet (or a new one: the old one fell) gets a name and a voice of their own."""
        seen: dict[str, dict[str, Any]] = {}
        for s in pic.get("squads") or []:
            if not isinstance(s, dict) or not s.get("name"):
                continue
            key = squad_key(str(s["name"]))
            seen[key] = s
            who = str(s.get("leader") or "")
            if who and self._leader.get(key) != who:
                self._leader[key] = who
                self.register_voice(key, f"{who} ({s['name']})", leader_voice(who, str(s.get("leader_gender") or "m")))
        if seen:
            self.squads = seen

    def _board(self, state: dict[str, Any], lang: str = "en") -> str:
        """The fight as the marines' board shows it (the game's picture, as text): the facts the people may know, and how old they are."""
        pic = self._pic
        if not pic:
            return " (the board is dark: the game has given no picture of the fight)"
        age = max(0.0, self.clock() - self._pic_t)
        lines = []
        over = not fighting(state)
        if over:
            lines.append(f" THE FIGHT IS OVER (this is the board as it stood {age:.0f} s ago, at the end)")
        cap = str(state.get("captain") or "")
        if cap:
            lines.append(f" where the Captain is: {cap[:260]}")
        lines.append(f" the fight: {_n(pic.get('elapsed_s'))} s since the alarm; the boarders came in at {pic.get('breach', '?')} (the hull is {'open' if pic.get('breach_open') else 'not cut yet'}); "
                     f"they go for {pic.get('objective', 'Main Engineering')} [id {pic.get('objective_id', '?')}]")
        b = boarding_of(state)
        if b:
            m, e = b.get("marines") or {}, b.get("boarders_known_losses") or {}
            lines.append(f" the count: marines {_n(m.get('able'))} able, {_n(m.get('down'))} down, {_n(m.get('dead'))} dead; of the boarders {_n(e.get('down_or_dead'))} known down or dead, "
                         f"{_n(e.get('left_ship'))} gone back through the breach")
        lines.append(" your squads (speaker key — name; leader):")
        cap_at = ((pic.get("captain") or {}).get("where_id") or "")
        for key, s in self.squads.items():
            tag = []
            if s.get("under_orders"):
                tag.append("under orders")
            if s.get("in_contact"):
                tag.append("in contact")
            if s.get("still_arming_or_waking"):
                tag.append(f"{_n(s['still_arming_or_waking'])} still arming or waking")
            at = f"at {s['where']} [id {s['where_id']}]" if s.get("where_id") else "(no one able to place)"
            said = spoken(str(s["name"]), lang)
            lines.append(f"  - {key} — {s['name']}" + (f" (said \"{said}\")" if said != s["name"] else "") + f"; leader {s.get('leader') or 'none left'}: {_n(s.get('able'))} able, {_n(s.get('down'))} down, {_n(s.get('dead'))} dead; {at}; "
                         f"doing: {s.get('doing', '?')}" + (f" ({'; '.join(tag)})" if tag else "") + (f"; note: {s['note']}" if s.get("note") else ""))
        if not self.squads:
            lines.append("  (none yet)")
        hs = pic.get("hostiles_known") or []
        lines.append(" the boarders as they are known (the corridors' sensors and what the marines have seen; it can be old): "
                     + ("; ".join(f"{_n(h.get('count'))} at {h.get('where')} [id {h.get('where_id')}], {_n(h.get('age_s'))} s ago" for h in hs) if hs else "none in sight"))
        ap = pic.get("likely_approach") or []
        if ap:
            lines.append(" the boarders' likely way from the breach to Main Engineering: " + " > ".join(f"{a.get('name')} [id {a.get('id')}]" for a in ap))
        en = pic.get("objective_entrances") or []
        if en:
            lines.append(" the ways into Main Engineering: " + "; ".join(f"{a.get('name')} [id {a.get('id')}]" for a in en))
        am = pic.get("default_ambush")
        if isinstance(am, dict):
            lines.append(f" the default ambush (where the drill sends the squads): {am.get('between')} [ids {am.get('id_a')}, {am.get('id_b')}]")
        bk = pic.get("bulkheads") or []
        if bk:
            lines.append(" the pressure bulkheads round the breach: " + "; ".join(f"{d.get('id')} between {d.get('between')}: {'SEALED' if d.get('sealed') else 'open'}" for d in bk))
        c = pic.get("captain")
        if isinstance(c, dict):
            armed = (b.get("captain") or {}).get("armed") if b else ""
            beside = [str(s.get("leader") or s["name"]) for s in self.squads.values() if cap_at and s.get("where_id") == cap_at and _n(s.get("able")) > 0]
            lines.append(f" the Captain in the fight: at {c.get('where')} [id {c.get('where_id')}], {_n(c.get('strength_pct'))}% strength{' — DOWN' if c.get('down') else ''}"
                         + (f"; armed: {armed}" if armed else "")
                         + (f"; in the same room as {', '.join(beside)} (words of his that name no one are theirs; a squad he names is the one that answers)" if beside else ""))
        rec = pic.get("recent") or []
        if rec:
            lines.append(" the fight's own log (newest last): " + " | ".join(str(x) for x in rec[-5:]))
        return "\n".join(lines)

    def _memory_text(self) -> str:
        rows = []
        for who, label in [(REYES.key, REYES.display)] + [(str(s.get("leader_id") or ""), f"{s.get('leader') or '?'} ({s['name']})") for s in self.squads.values()]:
            mems = self.memories.get(who) or []
            if who and mems:
                rows.append(f"- {label}: " + " / ".join(m["memory"] for m in mems[-MEMORY_PER:]))
        return "\n".join(rows)

    def _compose(self, state: dict[str, Any], events: list[Ev], inbox: list[Message], why: list[str], lang: str) -> str:
        now = self.clock()
        good, bad = _RADIO.get(lang, _RADIO["en"])
        parts = [f"THE NET, newest last (what was said and done, heard and seen)\n{self._recall()}", f"THE FIGHT NOW\n{self._board(state, lang)}"]
        said = [(t, w) for t, w in self.captain_words if not any(m.t == t for m in inbox)]
        if said:
            parts.append("WHAT THE CAPTAIN HAS SAID ON THE NET IN THIS FIGHT (his orders stand until he changes them)\n" + "\n".join(f" - {max(0, now - t):.0f} s ago: \"{w}\"" for t, w in said))
        mem = self._memory_text()
        if mem:
            parts.append(f"WHAT THEY REMEMBER\n{mem}")
        if events:
            parts.append("NEW SINCE YOUR LAST LOOK (newest last)\n" + "\n".join(
                f" - {max(0, now - e.t):.0f} s ago · {e.text}" + ("" if e.take else "  [the bridge's news: its officers have it; say something only if it touches your marines or your drill]") for e in events))
        if inbox:
            parts.append("THE CAPTAIN SAYS (over the net)\n" + "\n".join(f" - {max(0, now - m.t):.0f} s ago: \"{m.text}\"" for m in inbox))
        lang_name = LANG_NAMES.get(lang, lang)
        must = any(e.call for e in events)
        who = ", ".join(f"{k} ({self.radio(k)})" for k in self.present())
        parts.append(f"You are looking now because: {'; '.join(why)}.\nWho can speak (the `speaker` key): {who}.\nThe Captain's language is {lang_name}: everything said aloud is in {lang_name} (names in English); "
                     f"the Captain is \"{CAPTAIN_WORD.get(lang, 'Captain')}\".\nWhat a good radio line sounds like (what is in [brackets] comes from the news and the boards here; nothing else in these "
                     f"examples is a fact): {good}\nWhat it is not: {bad}\n"
                     + ("This look holds news that is called aloud (a marine fell, the first sight of the boarders, the end of the fight): the one it happened to, or the one who saw it, says it in "
                        "a few words (the board does not say it for them: the Captain hears a voice, not a board). Decide who and what: `say`, with `order` or `bulkheads` if the fight needs one, "
                        "`remember` if it is worth keeping." if must else
                        "Decide: speak with `say`, order with `order` or `bulkheads`, keep a memory with `remember`, or call `stay_quiet`."))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------------------------------------ a pulse
    async def _pulse(self, events: list[Ev], inbox: list[Message], why: list[str], state: dict[str, Any]) -> None:
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"t": round(self.clock() - self.t0, 1), "why": why, "tools": [], "lines": 0, "ok": 0, "failed": 0, "cost": 0.0, "latency": 0.0,
                               "first_call": None, "tokens_in": 0, "tokens_out": 0, "cached": 0, "error": "", "events": len(events), "captain": bool(inbox), "quiet": False}
        done = False
        me = asyncio.current_task()
        try:
            lang = (inbox[-1].lang if inbox and inbox[-1].lang else "") or self.lang()
            user = self._compose(state, events, inbox, why, lang)
            for e in events:                                                        # (what was just read is the net's past from now on)
                self.log.append((e.t, "(news)", e.text[:300]))
            for m in inbox:
                self.log.append((m.t, "the Captain (on the net)", m.text[:300]))
            if self.trace is not None:
                rec["system"], rec["user"] = self.system, user
            try:
                await asyncio.wait_for(self._run(user, rec, inbox, state, lang, must=any(e.call for e in events)), timeout=PULSE_TIMEOUT_S)
                done = True
            except asyncio.TimeoutError:
                rec["error"] = "timeout"
                log.warning("the marine net did not finish in %.0f s: nothing is said this time", PULSE_TIMEOUT_S)
            except asyncio.CancelledError:
                rec["error"] = "cancelled"
                if self._task is me:                                                # (a reset empties the net and forgets this pulse: nothing is put back then)
                    self._events = events + self._events                            # the news is read again: the Captain spoke first
                    self._inbox = inbox + self._inbox
                raise
            except Exception as exc:  # noqa: BLE001
                rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
                self.stats["errors"] += 1
                log.exception("the marine net's pulse failed")
            if rec["error"] and not rec["tools"] and inbox:
                await self._unanswered(inbox)
        finally:
            rec["latency"] = round(time.perf_counter() - t0, 2)
            self.stats["pulses"] += 1
            self.stats["lines"] += rec["lines"]
            self.stats["orders"] += rec["ok"]
            self.stats["failed"] += rec["failed"]
            self.stats["silent"] += 1 if (done and not rec["lines"] and not rec["ok"]) else 0
            self._spent.append((self.clock(), rec["cost"]))
            self.pulses.append(rec)
            del self.pulses[:-2000]
            if self.trace is not None:
                self.trace(rec)
            self._answering = False
            log.info("marine net %.2fs $%.5f (%s): %s", rec["latency"], rec["cost"], "; ".join(why)[:80], " | ".join(rec["tools"]) or "(nothing)")
            try:
                asyncio.get_running_loop().call_soon(self.kick)                     # (what came in while it ran is looked at now, not at the next state)
            except RuntimeError:
                pass

    async def _unanswered(self, inbox: list[Message]) -> None:
        """The model failed or stalled before it answered the Captain: the server hands his words to the bridge, never lost."""
        hook = self.on_unanswered
        if hook is not None:
            try:
                await hook([m.text for m in inbox])
            except Exception:  # noqa: BLE001
                log.exception("the Captain's words could not be passed to the bridge")

    # -- the model call and the tools
    async def _run(self, user: str, rec: dict[str, Any], inbox: list[Message], state: dict[str, Any], lang: str, must: bool = False) -> None:
        by_captain = bool(inbox)
        results: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        pending: list[tuple[str, dict[str, Any], asyncio.Task]] = []
        t_start = time.perf_counter()

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if rec["first_call"] is None:
                rec["first_call"] = round(time.perf_counter() - t_start, 2)
            rec["tools"].append(call.name + (f":{a.get('speaker')}" if call.name == "say" else f":{a.get('squad')}/{a.get('task')}" if call.name == "order"
                                              else f":{a.get('action')}" if call.name == "bulkheads" else ""))
            if call.name == "say":
                if pending:
                    # an order is under way (the game answers in a fraction of a second): the line is voiced once the order is known to have gone through. A line composed
                    # before the answer says it is done; if the game refused, it is not said, and the one who gave the order answers again with the reason
                    await asyncio.wait([t for _, _, t in pending], timeout=1.5)
                    if any(t.done() and not t.cancelled() and not (t.result() or {}).get("ok") for _, _, t in pending):
                        rec["held"] = rec.get("held", 0) + 1
                        return
                await self._say(a, lang, by_captain, rec)
            elif call.name in ("order", "bulkheads"):
                pending.append((call.name, a, asyncio.ensure_future(self._command(call.name, a))))
            elif call.name == "remember":
                self._remember(a)
            elif call.name == "stay_quiet":
                rec["quiet"] = True
                self._note("(the net)", f"stayed quiet: {str(a.get('reason', ''))[:120]}")

        msgs = [{"role": "system", "content": self.system}, {"role": "user", "content": user}]
        tools = TOOLS_MUST if must else TOOLS
        comp = await models.chat(self.llm, ROLE, messages=msgs, tools=tools, tool_choice="auto", on_tool_call=on_call)
        self._count(rec, comp)
        new = await self._collect(pending)
        results += new
        self._account(rec, new)
        if comp.error and not rec["tools"]:
            rec["error"] = comp.error[:100]
            return
        if not rec["tools"] and comp.content.strip():
            # it wrote and called nothing: what it wrote is nobody's radio line and no order; it is asked once for its answer in the tools (§1bis: no guessing from the text)
            before = len(pending)
            await asyncio.wait_for(self._reask(msgs, comp.content.strip(), on_call, rec, tools), timeout=ROUND2_TIMEOUT_S)
            new = await self._collect(pending[before:])
            results += new
            self._account(rec, new)
        failed = [(n, a, r) for n, a, r in results if not r.get("ok")]
        if failed:
            results += await asyncio.wait_for(self._round2(msgs, results, rec, by_captain, lang), timeout=ROUND2_TIMEOUT_S)
        if by_captain and not rec["lines"] and not rec["quiet"]:
            # the Captain spoke to the net and nobody answered him (an order given and not a word said, or nothing at all): the net answers a man who calls it; only a deliberate
            # silence (his words were not for the net) leaves him unanswered
            await asyncio.wait_for(self._answer(msgs, results, rec, lang), timeout=ROUND2_TIMEOUT_S)

    @staticmethod
    async def _collect(pending: list[tuple[str, dict[str, Any], asyncio.Task]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """The results of the orders sent to the game (the game's answer is the truth)."""
        out = []
        for name, a, task in pending:
            try:
                out.append((name, a, await asyncio.wait_for(asyncio.shield(task), timeout=4.0)))
            except asyncio.TimeoutError:
                out.append((name, a, {"ok": False, "detail": "no response from the game"}))
        return out

    async def _reask(self, msgs: list[dict[str, Any]], draft: str, on_call: Any, rec: dict[str, Any], tools: list[dict[str, Any]]) -> None:
        follow = list(msgs) + [{"role": "assistant", "content": draft},
                               {"role": "user", "content": "[What you wrote was not said or done. If the net has something to say or do, do it now with the tools"
                                                           + ("." if STAY_QUIET not in tools else "; if not, call stay_quiet.") + "]"}]
        comp = await models.chat(self.llm, ROLE, messages=follow, tools=tools, tool_choice="auto", on_tool_call=on_call, max_tokens=400)
        self._count(rec, comp)
        rec["asked_again"] = True

    async def _round2(self, msgs: list[dict[str, Any]], results: list[tuple[str, dict[str, Any], dict[str, Any]]], rec: dict[str, Any], by_captain: bool,
                      lang: str) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """An order was refused (a place the plan does not have, a squad that is not there, a bulkhead that is not listed): the one who gave it reads why and answers once: a
        line to the Captain, and a corrected order if there is a way. Returns the corrected orders' results."""
        notes = "\n".join(f"- {_order_text(n, a, r)}" for n, a, r in results)
        calls = [{"id": f"m{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}} for i, (n, a, _) in enumerate(results)]
        follow = list(msgs) + [{"role": "assistant", "content": None, "tool_calls": calls}]
        follow += [{"role": "tool", "tool_call_id": f"m{i}", "content": ("ok: " if r.get("ok") else "FAILED: ") + str(r.get("detail", ""))} for i, (_, _, r) in enumerate(results)]
        follow.append({"role": "user", "content": f"[The order did not go through (above).\n{notes}\nThe one who gave it tells the Captain in one line what happened and what they suggest, "
                                                  "with say, and if there is a way to do what was meant, corrects the order in the same turn; otherwise call stay_quiet.]"})
        return await self._follow_up(follow, rec, by_captain, lang)

    async def _answer(self, msgs: list[dict[str, Any]], results: list[tuple[str, dict[str, Any], dict[str, Any]]], rec: dict[str, Any],
                      lang: str) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """The Captain spoke to the net and has heard no voice (an order carried out without a word, an empty answer): the one he spoke to answers him now, knowing what the game did."""
        done = ("What has been done so far:\n" + "\n".join(f"- {_order_text(n, a, r)}" for n, a, r in results) + "\n") if results else ""
        follow = list(msgs) + [{"role": "user", "content": f"[The Captain spoke to the net and has not heard a voice answer him. {done}The person he spoke to (or whose squad the order is for) "
                                                           "answers him now, in one line, with say: what they are doing, or what they know. If his words were not for the net at all, call "
                                                           "stay_quiet.]"}]
        return await self._follow_up(follow, rec, True, lang)

    async def _follow_up(self, follow: list[dict[str, Any]], rec: dict[str, Any], by_captain: bool, lang: str) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """One more turn, with the voice, the orders and silence at hand: its lines are said (the Captain's answers), its orders sent, its results returned."""
        again: list[tuple[str, dict[str, Any], asyncio.Task]] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            rec["tools"].append("again:" + call.name)
            if call.name == "say":
                await self._say(a, lang, by_captain, rec)
            elif call.name in ("order", "bulkheads"):
                again.append((call.name, a, asyncio.ensure_future(self._command(call.name, a))))
            elif call.name == "stay_quiet":
                rec["quiet"] = True

        comp = await models.chat(self.llm, ROLE, messages=follow, tools=[SAY, ORDER, BULKHEADS, STAY_QUIET], tool_choice="auto", on_tool_call=on_call, max_tokens=400)
        self._count(rec, comp)
        new = await self._collect(again)
        self._account(rec, new)
        return new

    @staticmethod
    def _count(rec: dict[str, Any], comp: Completion) -> None:
        rec["cost"] += comp.cost
        rec["tokens_in"] += comp.prompt_tokens
        rec["tokens_out"] += comp.completion_tokens
        rec["cached"] += comp.cached_tokens

    def _account(self, rec: dict[str, Any], results: list[tuple[str, dict[str, Any], dict[str, Any]]]) -> None:
        for name, a, res in results:
            ok = bool(res.get("ok"))
            rec["ok" if ok else "failed"] += 1
            by = self.radio(str(a.get("by"))) if name == "order" and a.get("by") else REYES.radio
            what = (f"{a.get('squad')}: {a.get('task')}" + (f" at {a['place']}" if a.get("place") else "")) if name == "order" else f"bulkheads {a.get('action')}" + (f" {a['doors']}" if a.get("doors") else "")
            self._note("(order)", f"{by} ordered {what} => {'ok' if ok else 'FAILED'}: {str(res.get('detail', ''))[:140]}")

    # -- the tools
    def _key(self, who: str) -> str:
        """The speaker key of whoever is named: the Major, or a squad by its key or by its name on the board (`Reaction 1` and `marine_reaction_1` are the same squad); anything
        else stays as it was said (and is no one on the net)."""
        w = (who or "").strip()
        if w.lower() == REYES.key:
            return REYES.key
        if w in self.squads:
            return w
        k = squad_key(w)
        return k if k in self.squads else w

    def _speaker(self, key: str) -> tuple[str, bool]:
        """(the person's radio name, may they speak now): the Major, or the leader of a squad with someone able."""
        key = self._key(key)
        if key == REYES.key:
            return REYES.radio, True
        s = self.squads.get(key)
        return (self.radio(key), _n(s.get("able")) > 0) if s else (key, False)

    async def _say(self, a: dict[str, Any], lang: str, answer: bool, rec: dict[str, Any]) -> None:
        key = self._key(str(a.get("speaker") or ""))
        text = str(a.get("text") or "").strip()
        radio, may = self._speaker(key)
        if len(text) < 2:
            return
        if not may:
            log.info("%s speaks but is not on the net: not said", key)
            rec["unknown_speaker"] = rec.get("unknown_speaker", 0) + 1
            return
        tone = str(a.get("tone") or "calm")
        self._note(radio, text)
        rec["lines"] += 1
        await self.say(key, text, lang, tone if tone in TONES else "calm", urgent=bool(a.get("urgent")), answer=answer)

    async def _command(self, name: str, a: dict[str, Any]) -> dict[str, Any]:
        """An order of the net as the game takes it: the authority checked (the Major any squad, a leader his own, the bulkheads are the Major's), then sent as the game's own command."""
        try:
            if name == "bulkheads":
                args: dict[str, Any] = {"sealed": str(a.get("action") or "").lower() != "open"}
                doors = [str(d).strip() for d in (a.get("doors") or []) if str(d).strip()] if isinstance(a.get("doors"), list) else []
                if doors:
                    args["doors"] = doors
                else:
                    args["scope"] = "breach_section"
                return await self.execute("lockdown", args, REYES.key)
            by = self._key(str(a.get("by") or ""))
            squad = str(a.get("squad") or "").strip()
            named = next((str(s["name"]) for k, s in self.squads.items() if k == self._key(squad)), squad)         # (the squad's name as the game knows it)
            if by != REYES.key:
                mine = self.squads.get(by)
                if mine is None:
                    return {"ok": False, "detail": f"{by or 'nobody'} commands no squad: Major Reyes orders any squad, a squad leader only his own"}
                if named.lower() != str(mine["name"]).lower():
                    return {"ok": False, "detail": f"{mine.get('leader') or by} commands only {mine['name']}: Major Reyes orders the other squads"}
            args = {"squad": named, "task": str(a.get("task") or "").strip().lower()}
            if a.get("place"):
                args["place"] = str(a["place"]).strip()
            if a.get("reason"):
                args["note"] = str(a["reason"]).strip()[:160]
            return await self.execute("marine_order", args, by or REYES.key)
        except asyncio.TimeoutError:
            return {"ok": False, "detail": "no response from the game"}
        except Exception as exc:  # noqa: BLE001
            log.exception("the marines' command failed")
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:160]}

    def _remember(self, a: dict[str, Any]) -> None:
        key, mem = self._key(str(a.get("speaker") or "")), str(a.get("memory") or "").strip()[:400]
        who = REYES.key if key == REYES.key else str((self.squads.get(key) or {}).get("leader_id") or "")
        if not who or not mem:
            return
        mems = self.memories.setdefault(who, [])
        if any(m["memory"].lower() == mem.lower() for m in mems):
            return
        mems.append({"kind": str(a.get("kind") or "moment"), "memory": mem})
        while len(mems) > MEMORY_PER * 2:
            mems.pop(next((i for i, m in enumerate(mems) if m.get("kind") != "promise"), 0))
        log.info("marine memory %s: %s", who, mem)
        self.save()

    # ------------------------------------------------------------------------------------------------ a line that waited
    async def rethink(self, key: str, text: str, waited_s: float, cut_after: str, lang: str) -> str | None:
        """A person on the net thinks again about a line that waited (or was cut off) before it is said: what they say now, or None (the speech floor calls it:
        docs/ARCHITETTURA.md §1bis, point 5)."""
        key = self._key(key)
        radio, may = self._speaker(key)
        if key != REYES.key and key not in self.squads:
            return text
        cut = f" They had said only «{cut_after}» when the Captain spoke over them." if cut_after else ""
        ask = (f"{waited_s:.0f} seconds ago {radio} was about to say on the net: «{text}».{cut} The fight has moved on (the board below is now). If it still matters to the Captain, "
               "say it now as it stands — updated, short — with say. If not, say nothing: call stay_quiet.")
        user = f"THE NET, newest last\n{self._recall(8)}\n\nTHE FIGHT NOW\n{self._board(self.state, lang)}\n\n{ask}"
        said: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "say" and str(a.get("text") or "").strip() and str(a.get("speaker") or key) == key:
                said.append(str(a["text"]).strip())

        comp = await models.chat(self.llm, ROLE, messages=[{"role": "system", "content": self.system}, {"role": "user", "content": user}], tools=[SAY, STAY_QUIET],
                                 tool_choice="auto", on_tool_call=on_call, max_tokens=140)
        self._spent.append((self.clock(), comp.cost))
        return " ".join(said) if said else None

    # ------------------------------------------------------------------------------------------------ measures
    def summary(self) -> dict[str, Any]:
        """Costs and latencies of the pulses so far (the bench's and the lead's figures)."""
        n = len(self.pulses)
        span = max(1.0, self.clock() - self.t0)
        cost = sum(p["cost"] for p in self.pulses)
        lat = sorted(p["latency"] for p in self.pulses)
        fc = sorted(p["first_call"] for p in self.pulses if p["first_call"] is not None)
        return {"pulses": n, "errors": sum(1 for p in self.pulses if p["error"]), "cost": round(cost, 5), "cost_per_pulse": round(cost / n, 5) if n else 0.0,
                "span_s": round(span, 1), "cost_per_hour": round(cost / span * 3600.0, 3), "latency_median": lat[len(lat) // 2] if lat else 0.0,
                "latency_p90": lat[int(len(lat) * 0.9)] if lat else 0.0, "first_call_median": fc[len(fc) // 2] if fc else 0.0,
                "lines": sum(p["lines"] for p in self.pulses), "orders_ok": sum(p["ok"] for p in self.pulses), "orders_failed": sum(p["failed"] for p in self.pulses),
                "silent": self.stats["silent"], "tokens_in": sum(p["tokens_in"] for p in self.pulses), "tokens_out": sum(p["tokens_out"] for p in self.pulses),
                "cached": sum(p["cached"] for p in self.pulses), "stats": dict(self.stats)}
