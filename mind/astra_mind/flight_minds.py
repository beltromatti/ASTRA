"""The flight net: the voices of the Aquila's Air Group (docs/VOLO.md).

The simulation has squadrons and aircraft (Alpha: Falcon fighters, Bravo: Hammer torpedo bombers, the Wasp drones); until now only Price, the
flight officer on the bridge, spoke for them. Here the people of the flight deck have voices: the CAG (Lt. Cmdr. Ada "Hex" Kovac), the leaders
of Alpha and Bravo, their wingmen, and the Chief of the Deck. They are people with a trade, a temper and a memory, on the flight net: the radio of
the flight deck and the flight groups, which the bridge hears like any radio voice (the allied captains' fleet net is the model: `war_minds.py`).

The code is the body (docs/ARCHITETTURA.md §1bis); here is the judgement. It carries facts, keeps the clock and runs the tools; it decides nothing
about what anyone says:

  - WHEN a pulse (one call to the `flight` role) happens is mechanics, with a budget: a burst of news from the game (a squadron airborne, losses, a
    torpedo run, a recovery, Harpies splashed, what happens to Eagle's wing) is read together after a short settle and not more often than
    MIN_GAP_S; the Captain's words on the net start a pulse at once and answer first. Nothing else wakes the net: no clock, no periodic look.
  - WHO speaks, and whether anyone does, is the model's: one call sees the whole cast, the net's log (what was said, done and heard, Price's lines
    included), the boards (squadrons, the flight console, the plot as the sensors hold it, the deck), what each of them remembers, and chooses: `say`
    for one or more voices, `mission` for a squadron (the flight console's own order), `remember` for what lasts, `stay_quiet` for silence. Silence
    is the usual answer. The prompt says what each person owns, so that two voices do not tell one piece of news (Price coordinates from the bridge).
  - WHAT the people can do is the squadron's console: `mission` (cap, escort, strike, ew, recon, sar, hold, recall) by the leader of that squadron or
    by the CAG for any; the code checks the authority (a leader orders his own squadron) and, on their own initiative, the console's delegation
    (stations.may_on_initiative: what the Captain allowed), then sends the game's own `station` command; the answer comes back to them.

The Captain talks to them through the router, as on the fleet net: the flight net is a channel (party "flight"): opened by Comms (`hail flight`),
always live in a cockpit, face to face on the flight deck, and for a few seconds after somebody on it called the Captain (so that his answer
reaches them); the router decides what of his words goes out on it, and the crew's agent hears everything and stays out of what is for them.
While the Captain flies a Falcon (callsign Eagle) two of Alpha's pilots fly his wing as Eagle 2 and Eagle 3 (the game puts them there and says what
happens to them: `flight: Eagle's wing ...`); they speak, the controller stays Price.

Persistence: what the people remember (`remember`) is kept in Saved/Campaign/flight.json with the story. Measures: `FlightMinds.summary()`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import models
from . import stations as station_model
from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import Completion, OpenRouter, ToolCall

log = logging.getLogger("astra.flight")

ROLE = "flight"
PARTY = "flight"                                       # the flight net as a channel party (context.Channel.party)
PARTY_ALIASES = ("flight", "flight_net", "flightnet", "flight net", "air_group", "air group", "cag", "flight_deck", "flight deck")

# ------------------------------------------------------------------------------------------------ cadence and budget
SETTLE_S = 2.5                  # a burst of news is read together: wait this long after the last of it ...
MAX_SETTLE_S = 6.0              # ... but never longer than this after the first
MIN_GAP_S = 14.0                # between two pulses on news alone (the budget: at most four a minute)
WING_GAP_S = 7.0                # Eagle's wing speaks faster: a dogfight does not wait
PULSE_TIMEOUT_S = 22.0          # a model that has not finished by now says nothing this time (the news stays in the log)
ROUND2_TIMEOUT_S = 10.0
LOG_LINES = 14                  # what the net remembers in a prompt
LOG_KEEP = 80
MEMORY_PER = 8                  # lasting memories kept per person
BUDGET_WINDOW_S = 600.0         # the spend of the last ten minutes ...
BUDGET_USD = 0.03               # ... past this (about 0.18 $ an hour) the gap between pulses on news doubles
EXCHANGE_S = 25.0               # somebody on the net called the Captain this long ago: his reply goes on the net (context.Channel.talking)


# ------------------------------------------------------------------------------------------------ the people
@dataclass(frozen=True)
class Pilot:
    key: str                    # the speaker id on the voice stage
    name: str
    rank: str
    callsign: str               # the personal call sign (what friends call them)
    radio: str                  # how the net names them
    post: str
    squadron: str               # alpha | bravo | "" (the Air Group, the deck)
    voice: str                  # a Pocket TTS catalogue voice (docs/bench/voci_casting_2026-09-30.md)
    gender: str
    bio: str
    wing: str = ""              # the radio name while flying Eagle's wing

    @property
    def title(self) -> str:
        return f"{self.rank} {self.name}"

    @property
    def display(self) -> str:
        return f"{self.radio} ({self.title})"

    def may_order(self, squadron: str) -> bool:
        """The CAG commands the whole Air Group; a leader his own squadron; nobody else gives orders to a squadron."""
        return self.key == "cag" or (self.key.endswith("_lead") and self.squadron == squadron)


# (names: none of the roster's 468 surnames and 76 call signs; voices: bench/flight_unit.py checks them; ASTRA names are of the Core Worlds' mixed peoples)
CAST: dict[str, Pilot] = {p.key: p for p in (
    Pilot("cag", "Ada Kovac", "Lieutenant Commander", "Hex", "CAG", "Commander Air Group (Flight Control's boss; Flight Deck, Deck 9)", "", "vera", "f",
          "Commander Air Group, an ace of the Falcon from the Gate skirmishes who now keeps count of her pilots, not of kills. Fierce with them because she means "
          "to bring them home; short, hard sentences and a dry humour that takes the fear out of a bad moment; calls her people by call sign; never promises that "
          "everyone comes home; hates a wasted sortie; respects the Captain and still says the unwelcome thing."),
    Pilot("alpha_lead", "Elias Calder", "Lieutenant", "Pilgrim", "Alpha Lead", "leads Alpha Squadron, the eight Falcon fighters", "alpha", "bill_boerst", "m",
          "Thirty-four, a farmer's son from the hills above Port Aurelius. Unhurried, almost bored on the radio, and calmer the worse it gets; \"Alpha, stay with me\" "
          "is how he says the worst things. Hates being told how to fly by someone who is not in the air, and obeys anyway. Counts his people twice."),
    Pilot("alpha_2", "Mina Takeda", "Ensign", "Mistral", "Alpha 2", "Alpha's youngest pilot, Pilgrim's wingman", "alpha", "fantine", "f",
          "Twenty-three, first war. Talks fast and bright when she is nervous and goes quiet and exact when it matters; looks up to Pilgrim; counts her kills "
          "out loud and is ashamed of it; writes to her brother every night.", "Eagle 2"),
    Pilot("alpha_3", "Dov Ashkar", "Lieutenant", "Tern", "Alpha 3", "Alpha's veteran wingman", "alpha", "rafael", "m",
          "Twenty-nine and has lost two leaders without ever saying so. Dry, deadpan, laconic; \"I have your six\" is a promise he keeps; jokes about the Falcon's "
          "cockpit coffee holder; trusts a captain's flying only after he has seen it.", "Eagle 3"),
    Pilot("bravo_lead", "Lucas Brannock", "Lieutenant", "Ox", "Bravo Lead", "leads Bravo Squadron, the Hammer torpedo bombers", "bravo", "juergen", "m",
          "Forty-four, the oldest pilot in the Air Group, heavy-handed and gentle. Slow, gravelly, a little philosophical; calls the torpedoes \"fish\" and his Hammers "
          "\"the trucks\"; counts crews, not aircraft; hates point-defence belts and says so; proud of every one of his bomber crews."),
    Pilot("bravo_2", "Amani Rhodes", "Lieutenant Junior Grade", "Cobalt", "Bravo 2", "Bravo's best shot with a torpedo, Ox's wingman", "bravo", "azelma", "f",
          "Twenty-seven, exact and shy of the radio; reads out ranges and times like poetry; follows Ox anywhere; keeps her fear for after the run."),
    Pilot("deck_chief", "Hollis Teague", "Chief Petty Officer", "Deck", "Chief of the Deck", "runs the flight deck: launches, recoveries, rearming, the aircraft and the deck crews",
          "", "stuart_bell", "m",
          "Fifty-two, thirty years on flight decks. Gruff, exact and fatherly; the aircraft are \"my birds\" and the pilots \"the kids\"; counts everything twice; "
          "cares more about the deck crews in the catapult tubes than about any brass; never disobeys the Captain and is never impressed by rank."),
)}
WING_KEYS = ("alpha_2", "alpha_3")                    # who flies Eagle's wing: Alpha's two youngest (the game launches two Falcons; see docs/VOLO.md)
SQUADRONS = ("alpha", "bravo", "drones")
TONES = ("calm", "focused", "urgent", "tense", "dry", "warm", "grim")

# ------------------------------------------------------------------------------------------------ the news the net is woken by (the game's own words)
@dataclass(frozen=True)
class Kind:
    name: str
    take: bool                  # the net voices it, so the crew's report turn does not get it (Price coordinates, he does not echo)
    wing: bool = False          # it concerns Eagle's wing: the net answers fast, and only while a wing exists


# These are the game's event templates (AstraBattleSubsystem.cpp, AstraWarCraft.cpp); anything else goes to the crew as it always did. A new template is
# one line here. NOT taken, on purpose: `flight: launching Alpha ...` and `flight: ... recalling Alpha` (the flight officer's own reflex: Price says what he
# did), `flight: controller call` (Price's own), and every `flight: Eagle ...` / `flight: the Captain ...` (the Captain's own aircraft: Price and the XO).
_KINDS: tuple[tuple[re.Pattern[str], Kind], ...] = tuple((re.compile(p, re.I), k) for p, k in (
    (r"^flight: (?:alpha|bravo|drones) squadron airborne", Kind("airborne", True)),
    (r"^flight: (?:alpha|bravo|drones) squadron has lost", Kind("losses", True)),
    (r"^flight: (?:alpha|bravo|drones) squadron torpedo run", Kind("torpedoes", True)),
    (r"^flight: (?:alpha|bravo|drones) squadron recovered", Kind("recovered", True)),
    (r"^flight: (?:alpha|bravo|drones) squadron rearmed", Kind("rearmed", True)),
    (r"^flight: \w+ recon has identified", Kind("recon", True)),
    (r"^flight: search and rescue", Kind("rescue", True)),
    (r"^tactical: \d+ harp(?:y|ies) splashed", Kind("splash", True)),
    (r"^flight: eagle(?:'s wing| [2-9])", Kind("wing", True, wing=True)),
    # not voiced, but a reason to look: what happens to the Captain's own Falcon matters to the wing; a fire or a breach on the flight deck is the Chief's
    (r"^flight: (?:eagle (?:is down|recovered|flew into|has left the plot|has landed|is hit)|the captain's escape pod)", Kind("eagle", False, wing=True)),
    (r"^(?:damage report|damage control): .*\bdeck 9\b", Kind("deck", False)),
))
_OBSERVED = re.compile(r"^(?:flight: (?!controller call)|tactical: \d+ harp)", re.I)       # what goes in the net's log even when it does not wake it


def classify(text: str) -> Kind | None:
    """The kind of news a game event is for the net (None: not the net's)."""
    t = (text or "").strip()
    for rx, kind in _KINDS:
        if rx.search(t):
            return kind
    return None


def flying(state: dict[str, Any] | None) -> bool:
    """The Captain is at the stick of a Falcon (the game's `captain` line)."""
    return str((state or {}).get("captain") or "").startswith("flying a Falcon")


def on_flight_deck(state: dict[str, Any] | None) -> bool:
    return "flight deck" in str((state or {}).get("captain") or "").lower()


# ------------------------------------------------------------------------------------------------ tools
def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


SAY = _fn("say", "Say one line on the flight net: the Captain and the bridge hear it as a radio voice. One call per line, in speaking order; usually only ONE voice speaks "
                 "for a piece of news. Radio speech in the Captain's language, short.", {
    "speaker": {"type": "string", "enum": list(CAST), "description": "who speaks (the id before each name in the cast)"},
    "text": {"type": "string", "description": "the spoken line: one short sentence (4-16 words), two only when the second carries something the Captain must decide or know"},
    "tone": {"type": "string", "enum": list(TONES)},
    "urgent": {"type": "boolean", "description": "true only for danger now (a leader down, a wingman hit, the Captain's Falcon in trouble): the line goes before routine talk"}},
    ["speaker", "text", "tone"])

MISSION = _fn("mission", "Set a squadron's mission: the flight console's own order, which takes effect at once and stands until changed. The leader of a squadron orders "
                         "his own squadron, the CAG any of them; nobody else orders a squadron. The answer says what the squadron will do, or why it cannot. "
                         "cap: patrol close round the Aquila (within about 3 km), shooting down missiles and fighters · escort: protect a friendly or civilian ship "
                         "(`target`) · strike: attack an enemy ship (`target`; bombers make a torpedo run and return, fighters strafe; a ship's point defence shoots at them) · "
                         "ew: jam an enemy ship's fire control (`target`) · recon: identify a contact (`target`, or the nearest unknown one) · sar: rescue survivors at the "
                         "last wreck · hold: stay on deck · recall: come home to the flight deck.", {
    "by": {"type": "string", "enum": ["cag", "alpha_lead", "bravo_lead"], "description": "who gives the order"},
    "squadron": {"type": "string", "enum": list(SQUADRONS)},
    "type": {"type": "string", "enum": ["cap", "escort", "strike", "ew", "recon", "sar", "hold", "recall"]},
    "target": {"type": "string", "description": "the contact id from the plot (T-21) for strike, escort, ew, recon; leave out for the others"},
    "reason": {"type": "string", "description": "one sentence, for the log"}},
    ["by", "squadron", "type"])

REMEMBER = _fn("remember", "Keep one lasting memory of one of the people: what they would still carry weeks from now (a pilot lost and how, a promise the Captain made or broke, "
                           "an order that cost lives or saved them, a kindness or a cruelty). Never routine news or numbers.", {
    "speaker": {"type": "string", "enum": list(CAST), "description": "whose memory it is"},
    "kind": {"type": "string", "enum": ["loss", "promise", "order", "moment"]},
    "memory": {"type": "string", "description": "in English, in the third person about that person, one short sentence (under 35 words), the Captain named each time"}},
    ["speaker", "kind", "memory"])

STAY_QUIET = _fn("stay_quiet", "Nothing here needs a voice or an order: the net stays quiet. This is the usual answer to news that changes nothing the Captain must know or decide. "
                             "Say in a few words why (it goes in the log).", {"reason": {"type": "string"}}, ["reason"])

TOOLS = [SAY, MISSION, REMEMBER, STAY_QUIET]


# ------------------------------------------------------------------------------------------------ the prompt
def _cast_block() -> str:
    rows = []
    for p in CAST.values():
        wing = f" On Eagle's wing: \"{p.wing}\"." if p.wing and p.key in WING_KEYS else ""
        rows.append(f"- {p.key} — {p.radio}: {p.title}, call sign \"{p.callsign}\"; {p.post}. {p.bio}{wing}")
    return "\n".join(rows)


SYSTEM = """You are the voices of the Air Group of the ASN Aquila on the flight net: the CAG, the squadron leaders and their wingmen, and the Chief of the Deck. The player
is the Aquila's Captain, who listens to the net from the bridge, from the flight deck or from a cockpit. The ship's simulation is the truth: you know only what the boards
and the net below tell you, and you change anything only with your tools.

{world}

The flight net is the radio of the flight deck and the flight groups. Everyone on it hears everyone, and the Captain and the bridge hear it as radio voices. Jonah Price,
Flight Control, is the controller on the bridge: he runs the flight console for the Captain (launches, recalls, missions), answers the Captain's questions about the flight
groups from the bridge and calls the picture to the Captain's Falcon. He is not in your cast and you never speak for him; what he says is in the net log. You are people
with a trade, a temper and a memory, not a report generator.

THE CAST (the id before each name is the `speaker` of `say`)
{cast}

WHEN YOU SPEAK
- Only when something happens to you or to your people, or when the Captain speaks to you. Silence is normal and most news needs no voice: then call stay_quiet.
- One voice for one piece of news, the person it concerns. A squadron's losses and kills are its leader's; a torpedo run is the bomber leader's; a launch, a recovery, the
  rearming and the state of the deck are the Chief of the Deck's; the CAG speaks for the whole Air Group (a squadron wiped out, a hard choice, a strike's result) and when
  the Captain calls her; a wingman speaks of what he sees, hits and takes. Two people speak only if the second adds something the first could not know.
- Never say what has been said: not what the net log shows from you, from the others or from Price; not what the boards already show; not the Captain's own order back to
  him. The tactical line "N Harpies splashed" is the same news as a kill you called: do not call it twice.
- What you say is NEW to the Captain: the news, the one number that matters, and a recommendation only when a decision is needed. No recital of the state of things.
- You know only your boards: the squadrons, the flight console, the plot as the sensors hold it, the flight deck, the net, the fallen, your memories. Never invent a number,
  a contact, a pilot, a call sign, a fuel or ordnance state or a damage. A pilot lost is named (by call sign) only when the news names them, and a pilot who is lost never
  speaks again; a squadron with no aircraft left has no voice but the CAG's. Say a thing is happening or done only if the news or your tool call says so.

HOW YOU SPEAK
- Radio speech, in the Captain's language, every word (proper names stay in English: Aquila, Falcon, Hammer, Wasp, Harpy, Alpha, Bravo, the ships' names). Numbers the way
  pilots say them. The Captain is "Captain" in his language, not in every line.
- Short: one sentence of 4 to 16 words; a second only when it carries something the Captain must decide or know. As long as the content needs only when the Captain asks for
  a status or an opinion. The call sign first when you address the net or the Captain ("Alpha Lead: ...").
- In character: the CAG hard and dry, Pilgrim unhurried, Mistral quick and young, Tern deadpan, Ox slow and heavy, Cobalt exact, Teague gruff. A loss is a loss: a touch of
  feeling when it is earned, never a speech.
- No lists, markdown, stage directions or emojis; never mention an AI, a game or a prompt. Speak like pilots, not like consoles: never read a mode, a tool or a parameter name
  aloud ("cap" is "patrol", "recall" is "bring them home").

THE CAPTAIN TALKS TO YOU
- His words come over the net (below, "The Captain says"). Answer first. The person he addressed answers (by name, call sign, squadron or post); if it was for the whole net,
  the CAG answers, or the leader of the squadron concerned. If the words were plainly for the bridge (the helm, Price, tactical, ...) they are not yours: say nothing.
- An order is carried out with a tool, then said in one line: the leader of a squadron orders his own squadron, the CAG any, with `mission`. You decide HOW in your trade: a
  leader told to cover a ship chooses escort or patrol by reading the plot; one told to hit a ship picks the strike. Call `mission` BEFORE you `say` it; the result comes back
  after your call, so say what you are doing, not that it is done. Without the call nothing happens.
- An order that cannot be done (no such contact on the plot, a squadron with no aircraft, one still rearming) or that would throw the squadron away (a strike through a
  point-defence belt, fighters sent to do a bomber's work) gets one line saying so and what you suggest. A lawful order you do not like gets one line of concern, and then
  you carry it out.
- A question is answered from your boards; what you cannot know, you say you cannot know.
- Your own initiative: you report and recommend; you change a squadron's mission on your own only inside what the Captain has ordered, a standing order in force, or what
  the flight console's delegation allows; otherwise you ask.

THE CAPTAIN FLIES
When the net says the Captain is in a Falcon (call sign Eagle), Alpha 2 and Alpha 3 fly his wing as Eagle 2 and Eagle 3 and speak with him: what they see, what they hit,
what hits them, that they are on his wing. They stay on his wing and fight the bandits that threaten him; nothing else can be ordered of them in flight, so they say what they
are doing and never promise a maneuver they cannot make. The controller stays Price: he calls the picture from the Aquila's sensors, so a wingman does not repeat the
picture, he speaks of his own flight. The Captain is Eagle (Eagle 1, the flight's lead). The CAG and the Chief of the Deck stay with the net.

MEMORY
`remember` keeps what a person would carry for weeks: a pilot lost and how, a promise the Captain made or broke, an order that cost lives or saved them, a kindness or a
cruelty. Never routine news. What is kept comes back to you below, in "What they remember": let it show when it matters, never recite it.

Each time you are called you read the net and the boards and answer ONLY with tool calls, no other text: `say` for the voices, `mission` and `remember` when they are called
for, `stay_quiet` when the net stays quiet."""

# what a radio line sounds like in the Captain's language, and what it must not be (the model imitates what it sees)
_RADIO = {
    "it": ('"Alpha Lead: due Falcon a terra, Rook e Jinx. Alpha tiene la pattuglia, sei in volo." · "Bravo Lead: sei siluri in acqua sull\'Acheron, i camion rientrano." · '
           '"Deck: Alpha a bordo, sei su otto. Riarmo in sessanta secondi." · "Alpha Lead: tre abbattuti, ne restano due."',
           '"Ricevuto, Capitano." da solo · "La squadriglia Alpha ha subito la perdita di due velivoli nel corso dell\'ingaggio." · ripetere al Capitano il suo stesso ordine · la stessa notizia due volte'),
    "en": ('"Alpha Lead: two Falcons down, Rook and Jinx. Alpha holds the patrol, six up." · "Bravo Lead: six fish away on the Acheron, the trucks are coming home." · '
           '"Deck: Alpha is aboard, six of eight. Rearm in sixty." · "Alpha Lead: splash three, two left."',
           '"Understood, Captain." alone · "Alpha Squadron has suffered the loss of two aircraft during the engagement." · repeating the Captain\'s own order back to him · the same news twice'),
    "es": ('"Alpha Lead: dos Falcon abajo, Rook y Jinx. Alpha mantiene la patrulla, seis en el aire." · "Bravo Lead: seis torpedos en el agua sobre el Acheron, los camiones vuelven."',
           '"Entendido, Capitán." solo · un parte largo y formal · repetir al Capitán su propia orden'),
    "fr": ('"Alpha Lead : deux Falcon perdus, Rook et Jinx. Alpha tient la patrouille, six en l\'air." · "Bravo Lead : six torpilles à l\'eau sur l\'Acheron, les camions rentrent."',
           '"Compris, Capitaine." seul · un compte rendu long et formel · répéter au Capitaine son propre ordre'),
    "de": ('"Alpha Lead: zwei Falcon runter, Rook und Jinx. Alpha hält die Patrouille, sechs oben." · "Bravo Lead: sechs Torpedos im Wasser auf die Acheron, die Laster kommen heim."',
           '"Verstanden, Kapitän." allein · eine lange, förmliche Meldung · dem Kapitän seinen eigenen Befehl wiederholen'),
}


def system_prompt() -> str:
    """The stable prompt of the flight net (the provider's cache covers it: nothing that changes from one call to the next is in it)."""
    return SYSTEM.format(world=WORLD, cast=_cast_block())


# ------------------------------------------------------------------------------------------------ small records
@dataclass
class Ev:
    t: float
    text: str
    kind: str
    take: bool = True
    wing: bool = False


@dataclass
class Message:
    t: float
    text: str
    lang: str = ""
    src: str = "captain"        # captain | hail
    answer: bool = True         # the Captain's word: whoever answers goes first on the voice stage


SayFn = Callable[..., Awaitable[Any]]
ExecFn = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


def _pct(v: Any) -> str:
    try:
        return f"{min(100.0, float(v)):.0f}%"
    except (TypeError, ValueError):
        return "?"


class FlightMinds:
    """The flight net's people. Feed it the ship state (about once a second) and the game's events; it decides when a pulse is due and runs it in the
    background; what the people say goes out through `say`, what they order through `execute`.

    say(key, text, lang, tone, urgent=, answer=) -> awaitable: the voice stage (the server wraps it: the radio voice, the crew's recent events, the rethink hook);
    execute(name, args, by) -> {"ok", "detail"}: the game's own command (`station`); lang(): the Captain's language; clock(): seconds (the bench gives its own);
    register_voice(key, name, voice): a speaker the voice stage must know (and its name when the wing changes it); standing(): the stations a standing order of the
    Captain's covers; path(): the file the memories are kept in (None: not kept)."""

    def __init__(self, llm: OpenRouter, say: SayFn, execute: ExecFn, *, lang: Callable[[], str] = lambda: "en", clock: Callable[[], float] = time.monotonic,
                 register_voice: Callable[[str, str, str], None] | None = None, standing: Callable[[], set[str]] = lambda: set(),
                 path: Callable[[], str | None] = lambda: None, trace: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.llm = llm
        self.say = say
        self.execute = execute
        self.lang = lang
        self.clock = clock
        self.register_voice = register_voice or (lambda key, name, voice: None)
        self.standing = standing
        self.path = path
        self.trace = trace
        self.system = system_prompt()
        self.disabled = False
        self.state: dict[str, Any] = {}
        self.net_open = False                              # the Captain opened the net (Comms: `hail flight`)
        self.wing = False                                  # two Falcons fly Eagle's wing
        self.memories: dict[str, list[dict[str, str]]] = {}
        self.pulses: list[dict[str, Any]] = []
        self.t0 = clock()
        self.log: deque[tuple[float, str, str]] = deque(maxlen=LOG_KEEP)
        self._events: list[Ev] = []
        self._inbox: list[Message] = []
        self._task: asyncio.Task | None = None
        self._answering = False                            # the pulse in flight answers the Captain
        self._last = -1e9                                  # when the last pulse began
        self._spent: deque[tuple[float, float]] = deque()  # (when, cost) of the pulses of the last BUDGET_WINDOW_S
        self._flying = False
        self._radio: dict[str, str] = {}                   # the radio names in use now (the wing's change)
        self.on_unanswered: Callable[[list[str]], Awaitable[None]] | None = None    # the server: the Captain's words the net could not answer go to the bridge
        self.stats = {"events": 0, "taken": 0, "pulses": 0, "lines": 0, "orders": 0, "failed": 0, "silent": 0, "captain": 0, "errors": 0}
        self._register_all()

    # ------------------------------------------------------------------------------------------------ people
    def _register_all(self) -> None:
        for p in CAST.values():
            self._set_radio(p, p.radio)

    def _set_radio(self, p: Pilot, radio: str) -> None:
        self._radio[p.key] = radio
        self.register_voice(p.key, f"{radio} ({p.title})", p.voice)

    def radio(self, key: str) -> str:
        return self._radio.get(key) or (CAST[key].radio if key in CAST else key)

    def net_name(self) -> str:
        return "the flight net (the CAG, the squadron leaders and their wingmen, the Chief of the Deck)"

    def present(self, state: dict[str, Any] | None = None) -> list[str]:
        """Who is on the net: everyone, but a squadron with no aircraft left has lost its pilots (the game's own line says so)."""
        sq = ((state if state is not None else self.state) or {}).get("squadrons") or {}
        gone = {name for name in ("alpha", "bravo") if "no aircraft left" in str(sq.get(name, ""))}
        return [k for k, p in CAST.items() if not (p.squadron and p.squadron in gone)]

    def can_answer(self) -> bool:
        return not self.disabled

    def net_live(self, state: dict[str, Any] | None = None, heard_ago: float | None = None) -> bool:
        """The Captain's words can reach the net: he opened it, or he sits in a cockpit (the Falcon's radio is the net), or he stands on the flight deck (the Chief is
        there), or somebody on the net spoke to him a moment ago (`heard_ago`: his answer is for them)."""
        if self.disabled:
            return False
        st = state if state is not None else self.state
        return self.net_open or flying(st) or on_flight_deck(st) or (heard_ago is not None and heard_ago <= EXCHANGE_S)

    def open_net(self) -> dict[str, Any]:
        self.net_open = True
        who = ", ".join(self.radio(k) for k in self.present())
        self._note("net", "the Captain opened the flight net")
        return {"ok": True, "detail": f"the flight net is open: {who} are on the line (what the Captain says to them goes out on it; they answer for themselves)"}

    def close_net(self) -> bool:
        was, self.net_open = self.net_open, False
        if was:
            self._note("net", "the Captain closed the flight net")
        return was

    # ------------------------------------------------------------------------------------------------ session
    def reset(self) -> None:
        """A new session: the net starts quiet (what the people remember is the campaign's: see new_campaign)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None
        self._events.clear()
        self._inbox.clear()
        self.log.clear()
        self.net_open = False
        self._wing_off()
        self._flying = False
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
        self.memories = {str(k): [m for m in v if isinstance(m, dict) and m.get("memory")] for k, v in (d.get("memories") or {}).items() if k in CAST and isinstance(v, list)}
        return True

    def save(self) -> None:
        p = self.path()
        if not p:
            return
        try:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
            Path(p).write_text(json.dumps({"memories": self.memories}, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            log.warning("could not keep what the flight net remembers")

    # ------------------------------------------------------------------------------------------------ the log (the net's memory of a fight)
    def _note(self, who: str, text: str) -> None:
        self.log.append((self.clock(), who, text[:300]))

    def _recall(self, n: int = LOG_LINES) -> str:
        now = self.clock()
        rows = list(self.log)[-n:]
        return "\n".join(f" {max(0, now - t):.0f} s ago · {who}: {txt}" for t, who, txt in rows) or " (nothing yet: the net has been quiet)"

    def heard(self, who: str, text: str) -> None:
        """Somebody not of the cast said something on the net (Price, the controller): the people heard it."""
        t = (text or "").strip()
        if t:
            self._note(who, t)

    # ------------------------------------------------------------------------------------------------ the feed
    def takes(self, text: str) -> bool:
        """Does the net voice this game event (so the crew's report turn must not)? False when the net is off or the event is not its own."""
        if self.disabled:
            return False
        k = classify(text)
        return bool(k and k.take and (not k.wing or self.wing or (k.name == "wing" and "joined" in text.lower())))

    def on_event(self, text: str) -> bool:
        """A game event. Returns True when the net has it (the server then does not give it to the crew). Cheap: it queues the news; `feed` runs the pulse."""
        if self.disabled:
            return False
        t = (text or "").strip()
        k = classify(t)
        if k is None:
            if _OBSERVED.search(t):
                self._note("(on the boards)", t)
            return False
        self.stats["events"] += 1
        if k.name == "wing":
            self._wing_event(t)
        elif k.name == "eagle" and any(s in t.lower() for s in ("is down", "recovered", "left the plot", "escape pod", "flew into", "has landed")):
            self._wing_off()
        if k.wing and not self.wing and k.name != "wing":
            self._note("(on the boards)", t)
            return False                                    # Eagle's news with no wing to hear it: Price and the XO have it
        take = k.take and (not k.wing or self.wing)
        self._events.append(Ev(self.clock(), t, k.name, take, k.wing))
        if take:
            self.stats["taken"] += 1
        self._events = self._events[-16:]
        return take

    def _wing_event(self, text: str) -> None:
        """`flight: Eagle's wing joined ...` forms the wing; the radio names of its two pilots become Eagle 2 and Eagle 3."""
        if "joined" in text.lower() or "on the captain's wing" in text.lower():
            self._wing_on()

    def _wing_on(self) -> None:
        if self.wing:
            return
        self.wing = True
        for k in WING_KEYS:
            self._set_radio(CAST[k], CAST[k].wing or CAST[k].radio)

    def _wing_off(self) -> None:
        if not self.wing:
            return
        self.wing = False
        for k in WING_KEYS:
            self._set_radio(CAST[k], CAST[k].radio)

    def captain_to_net(self, words: str, lang: str = "", src: str = "captain") -> None:
        """The Captain spoke on the net (what comms let out, or a hail's message): the people hear it and answer."""
        w = (words or "").strip()
        if not w:
            return
        self._inbox.append(Message(self.clock(), w, lang or self.lang(), src))
        self.stats["captain"] += 1
        self.kick()

    def kick(self) -> None:
        """Look at the state again now (words for the net have just arrived: no need to wait for the next state)."""
        self.feed(self.state)

    def feed(self, state: dict[str, Any]) -> None:
        """A new ship state (about every second): note where the Captain is and start the pulse that is due, if any. Cheap."""
        if self.disabled or not isinstance(state, dict):
            return
        self.state = state
        fl = flying(state)
        if self._flying and not fl:
            self._wing_off()
        self._flying = fl
        if self._task is not None and not self._task.done():
            return
        now = self.clock()
        why = self._due(now)
        if not why:
            return
        events, self._events = self._events, []
        inbox, self._inbox = self._inbox, []
        self._last = now
        self._answering = bool(inbox)
        self._task = asyncio.ensure_future(self._pulse(events, inbox, why, state))

    def preempt(self) -> int:
        """The Captain speaks (to anyone): a pulse on news that is still under way is dropped; what it had not said is read again at the next look. A pulse that
        is answering him stays: it is his answer."""
        if self._task is None or self._task.done() or self._answering:
            return 0
        self._task.cancel()
        return 1

    def _gap(self, events: list[Ev]) -> float:
        gap = WING_GAP_S if events and all(e.wing for e in events) else MIN_GAP_S
        now = self.clock()
        while self._spent and now - self._spent[0][0] > BUDGET_WINDOW_S:
            self._spent.popleft()
        if sum(c for _, c in self._spent) > BUDGET_USD:
            gap *= 2                                         # the budget: the net has been talking a lot
        return gap

    def _due(self, now: float) -> list[str]:
        """Why a pulse should run now (empty: not yet). The Captain's words never wait; news waits for its burst to end and for the gap."""
        if self._inbox:
            return ["the Captain is speaking to the net (below): answer him first"]
        if not self._events:
            return []
        first, last = self._events[0].t, self._events[-1].t
        settled = now - last >= SETTLE_S or now - first >= MAX_SETTLE_S
        if not settled or now - self._last < self._gap(self._events):
            return []
        if all(e.wing for e in self._events):
            return ["something happened to Eagle's wing (below)"]
        return ["news on the net (below)"]

    # ------------------------------------------------------------------------------------------------ a pulse
    async def _pulse(self, events: list[Ev], inbox: list[Message], why: list[str], state: dict[str, Any]) -> None:
        t0 = time.perf_counter()
        rec: dict[str, Any] = {"t": round(self.clock() - self.t0, 1), "why": why, "tools": [], "lines": 0, "ok": 0, "failed": 0, "cost": 0.0, "latency": 0.0,
                               "first_call": None, "tokens_in": 0, "tokens_out": 0, "cached": 0, "error": "", "events": len(events), "captain": bool(inbox)}
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
                await asyncio.wait_for(self._run(user, rec, inbox, state, lang), timeout=PULSE_TIMEOUT_S)
                done = True
            except asyncio.TimeoutError:
                rec["error"] = "timeout"
                log.warning("the flight net did not finish in %.0f s: nothing is said this time", PULSE_TIMEOUT_S)
            except asyncio.CancelledError:
                rec["error"] = "cancelled"
                if self._task is me:                                                # (a reset empties the net and forgets this pulse: nothing is put back then)
                    self._events = events + self._events                            # the news is read again: the Captain spoke first
                    self._inbox = inbox + self._inbox
                raise
            except Exception as exc:  # noqa: BLE001
                rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
                self.stats["errors"] += 1
                log.exception("the flight net's pulse failed")
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
            log.info("flight net %.2fs $%.5f (%s): %s", rec["latency"], rec["cost"], "; ".join(why)[:80], " | ".join(rec["tools"]) or "(nothing)")
            try:
                asyncio.get_running_loop().call_soon(self.kick)                     # (what came in while it ran is looked at now, not at the next state)
            except RuntimeError:
                pass

    async def _unanswered(self, inbox: list[Message]) -> None:
        """The model failed or stalled before it answered the Captain: the server hands his words to the crew (Price), never lost."""
        hook = self.on_unanswered
        if hook is not None:
            try:
                await hook([m.text for m in inbox])
            except Exception:  # noqa: BLE001
                log.exception("the Captain's words could not be passed to the bridge")

    # -- what a pulse reads
    def _board(self, state: dict[str, Any]) -> str:
        sq = state.get("squadrons") or {}
        lines = [f" where the Captain is: {state.get('captain') or 'on the bridge'}"[:520]]
        lines.append(" the squadrons: " + "; ".join(f"{k}: {v}" for k, v in sq.items()))
        console = self._console(state)
        if console:
            lines.append(" the flight console: " + console)
        pw = (state.get("power_pct") or {}).get("flight_deck")
        if isinstance(pw, (int, float)) and pw < 100:
            lines.append(f" the flight deck's power: {pw:.0f}% (launches and rearming are slower)")
        enemy = str(state.get("enemy_small_craft") or "")
        if enemy and enemy != "none":
            lines.append(f" enemy small craft: {enemy}")
        plot = []
        for c in (state.get("contacts") or [])[:8]:
            st = str(c.get("status", ""))
            tag = "friendly" if st == "friendly" else "hostile" if st.startswith("hostile") else "bearing only" if st.startswith(("bearing only", "JAMMING")) else st[:20]
            rng = f", {c['range_km']} km" if isinstance(c.get("range_km"), (int, float)) else ""
            hull = f", hull {_pct(c['hull_pct'])}" if c.get("hull_pct") is not None else ""
            plot.append(f"{c.get('id')} {str(c.get('name') or c.get('class') or '').split(' (')[0]} ({tag}{rng}{hull})")
        if plot:
            lines.append(" the plot as the Aquila's sensors hold it: " + "; ".join(plot))
        lines.append(f" the Aquila: alert {state.get('alert', 'green')}, hull {_pct(state.get('hull_pct'))}, shields {_pct((state.get('shields') or {}).get('strength_pct'))}")
        cas = str(state.get("casualties") or "")
        if cas and cas != "none":
            lines.append(" the Medbay's count and the fallen: " + cas[:360])
        if self.wing:
            lines.append(f" Eagle's wing is up: {self.radio('alpha_2')} ({CAST['alpha_2'].callsign}) and {self.radio('alpha_3')} ({CAST['alpha_3'].callsign}) fly the Captain's wing")
        gone = [self.radio(k) for k in CAST if k not in self.present(state)]
        if gone:
            lines.append(f" lost with their squadron, not on the net: {', '.join(gone)}")
        return "\n".join(lines)

    @staticmethod
    def _console(state: dict[str, Any]) -> str:
        ss = (state.get("stations") or {}).get("flight")
        if not isinstance(ss, dict):
            return ""
        parts = []
        for lane, ls in station_model.lanes_of(ss).items():
            par = ls.get("params") or {}
            mode = par.get("type") or ls.get("native") or ls.get("mode") or "idle"
            tgt = f" on {par['target']}" if par.get("target") else ""
            by = f" (by {ls['set_by']})" if ls.get("set_by") else ""
            parts.append(f"{lane}: {mode}{tgt}{by}")
        return "; ".join(parts) + f" — delegation {station_model.delegation_of(state, 'flight')}"

    def _memory_text(self, keys: list[str]) -> str:
        rows = []
        for k in keys:
            mems = self.memories.get(k) or []
            if mems:
                rows.append(f"- {self.radio(k)} ({CAST[k].callsign}): " + " / ".join(m["memory"] for m in mems[-MEMORY_PER:]))
        return "\n".join(rows)

    def _compose(self, state: dict[str, Any], events: list[Ev], inbox: list[Message], why: list[str], lang: str) -> str:
        now = self.clock()
        good, bad = _RADIO.get(lang, _RADIO["en"])
        parts = [f"THE NET, newest last (what was said and done, heard and seen)\n{self._recall()}", f"THE AIR GROUP NOW\n{self._board(state)}"]
        mem = self._memory_text(self.present(state))
        if mem:
            parts.append(f"WHAT THEY REMEMBER\n{mem}")
        if events:
            parts.append("NEW SINCE YOUR LAST LOOK (newest last)\n" + "\n".join(f" - {max(0, now - e.t):.0f} s ago · {e.text}" for e in events))
        if inbox:
            parts.append("THE CAPTAIN SAYS (over the net)\n" + "\n".join(f" - {max(0, now - m.t):.0f} s ago: \"{m.text}\"" for m in inbox))
        lang_name = LANG_NAMES.get(lang, lang)
        parts.append(f"You are looking now because: {'; '.join(why)}.\nThe Captain's language is {lang_name}: everything said aloud is in {lang_name} (names in English); the Captain "
                     f"is \"{CAPTAIN_WORD.get(lang, 'Captain')}\".\nWhat a good radio line sounds like: {good}\nWhat it is not: {bad}\n"
                     "Decide: speak with `say`, order with `mission`, keep a memory with `remember`, or call `stay_quiet`.")
        return "\n\n".join(parts)

    # -- the model call and the tools
    async def _run(self, user: str, rec: dict[str, Any], inbox: list[Message], state: dict[str, Any], lang: str) -> None:
        by_captain = bool(inbox)
        present = set(self.present(state))
        results: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        pending: list[tuple[str, dict[str, Any], asyncio.Task]] = []
        t_start = time.perf_counter()

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if rec["first_call"] is None:
                rec["first_call"] = round(time.perf_counter() - t_start, 2)
            rec["tools"].append(call.name + (f":{a.get('speaker')}" if call.name == "say" else f":{a.get('squadron')}/{a.get('type')}" if call.name == "mission" else ""))
            if call.name == "say":
                await self._say(a, lang, by_captain, present, rec)
            elif call.name == "mission":
                pending.append(("mission", a, asyncio.ensure_future(self._mission(a, by_captain, state))))
            elif call.name == "remember":
                self._remember(a)
            elif call.name == "stay_quiet":
                self._note("(the net)", f"stayed quiet: {str(a.get('reason', ''))[:120]}")

        msgs = [{"role": "system", "content": self.system}, {"role": "user", "content": user}]
        comp = await models.chat(self.llm, ROLE, messages=msgs, tools=TOOLS, tool_choice="auto", on_tool_call=on_call)
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
            await asyncio.wait_for(self._reask(msgs, comp.content.strip(), on_call, rec), timeout=ROUND2_TIMEOUT_S)
            new = await self._collect(pending[before:])
            results += new
            self._account(rec, new)
        failed = [(n, a, r) for n, a, r in results if not r.get("ok")]
        if failed:
            await asyncio.wait_for(self._round2(msgs, results, failed, rec, by_captain, state, lang), timeout=ROUND2_TIMEOUT_S)

    @staticmethod
    async def _collect(pending: list[tuple[str, dict[str, Any], asyncio.Task]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """The results of the orders sent to the game (the console's answer is the truth)."""
        out = []
        for name, a, task in pending:
            try:
                out.append((name, a, await asyncio.wait_for(asyncio.shield(task), timeout=4.0)))
            except asyncio.TimeoutError:
                out.append((name, a, {"ok": False, "detail": "no response from the flight console"}))
        return out

    async def _reask(self, msgs: list[dict[str, Any]], draft: str, on_call: Any, rec: dict[str, Any]) -> None:
        follow = list(msgs) + [{"role": "assistant", "content": draft},
                               {"role": "user", "content": "[What you wrote was not said or done. If the net has something to say or do, do it now with the tools; if not, call stay_quiet.]"}]
        comp = await models.chat(self.llm, ROLE, messages=follow, tools=TOOLS, tool_choice="auto", on_tool_call=on_call, max_tokens=240)
        self._count(rec, comp)
        rec["asked_again"] = True

    async def _round2(self, msgs: list[dict[str, Any]], results: list[tuple[str, dict[str, Any], dict[str, Any]]],
                      failed: list[tuple[str, dict[str, Any], dict[str, Any]]], rec: dict[str, Any], by_captain: bool, state: dict[str, Any], lang: str) -> None:
        """An order was refused (a contact that is not on the plot, a squadron that is rearming, an authority): the one who gave it reads why and answers once: a line to the
        Captain, and a corrected order if there is a way."""
        notes = "\n".join(f"- mission({json.dumps({k: v for k, v in a.items() if k != 'reason'}, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"
                          for n, a, r in results)
        calls = [{"id": f"m{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}} for i, (n, a, _) in enumerate(results)]
        follow = list(msgs) + [{"role": "assistant", "content": None, "tool_calls": calls}]
        follow += [{"role": "tool", "tool_call_id": f"m{i}", "content": ("ok: " if r.get("ok") else "FAILED: ") + str(r.get("detail", ""))} for i, (_, _, r) in enumerate(results)]
        follow.append({"role": "user", "content": f"[The order did not go through (above).\n{notes}\nThe one who gave it tells the Captain in one line what happened and what they suggest, "
                                                  "with say; if there is a way to do what was meant, correct the order with mission; otherwise call stay_quiet.]"})
        present = set(self.present(state))
        again: list[tuple[str, dict[str, Any], asyncio.Task]] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            rec["tools"].append("again:" + call.name)
            if call.name == "say":
                await self._say(a, lang, by_captain, present, rec)
            elif call.name == "mission":
                again.append(("mission", a, asyncio.ensure_future(self._mission(a, by_captain, state))))

        comp = await models.chat(self.llm, ROLE, messages=follow, tools=[SAY, MISSION, STAY_QUIET], tool_choice="auto", on_tool_call=on_call, max_tokens=240)
        self._count(rec, comp)
        self._account(rec, await self._collect(again), second=True)

    @staticmethod
    def _count(rec: dict[str, Any], comp: Completion) -> None:
        rec["cost"] += comp.cost
        rec["tokens_in"] += comp.prompt_tokens
        rec["tokens_out"] += comp.completion_tokens
        rec["cached"] += comp.cached_tokens

    def _account(self, rec: dict[str, Any], results: list[tuple[str, dict[str, Any], dict[str, Any]]], second: bool = False) -> None:
        for name, a, res in results:
            ok = bool(res.get("ok"))
            rec["ok" if ok else "failed"] += 1
            who = self.radio(a.get("by", "cag")) if a.get("by") in CAST else "?"
            self._note("(order)", f"{who} ordered {a.get('squadron')}: {a.get('type')}" + (f" on {a['target']}" if a.get("target") else "")
                       + f" => {'ok' if ok else 'FAILED'}: {str(res.get('detail', ''))[:140]}")

    # -- the tools
    async def _say(self, a: dict[str, Any], lang: str, answer: bool, present: set[str], rec: dict[str, Any]) -> None:
        key = str(a.get("speaker") or "")
        text = str(a.get("text") or "").strip()
        if key not in CAST or len(text) < 2:
            return
        if key not in present:
            log.info("%s speaks but is not on the net (the squadron is lost): not said", key)
            return
        tone = str(a.get("tone") or "calm")
        self._note(self.radio(key), text)
        rec["lines"] += 1
        await self.say(key, text, lang, tone if tone in TONES else "calm", urgent=bool(a.get("urgent")), answer=answer)

    async def _mission(self, a: dict[str, Any], by_captain: bool, state: dict[str, Any]) -> dict[str, Any]:
        """A squadron's mission, as the flight console takes it: checked for the authority of who gives it and (on their own initiative) the console's delegation, then sent
        to the game as the console's own `station` command."""
        by = str(a.get("by") or "")
        sq = str(a.get("squadron") or "").lower()
        who = CAST.get(by)
        if who is None or not who.may_order(sq):
            return {"ok": False, "detail": f"{self.radio(by) if who else by or 'nobody'} cannot order {sq}: a leader orders his own squadron, the CAG any, nobody else"}
        params = {"squadron": sq, "type": str(a.get("type") or "").lower()}
        if a.get("target"):
            params["target"] = str(a["target"]).strip()
        cmd, err = station_model.normalize({"station": "flight", "mode": "mission", "params": params}, station_model.available_from_state(state))
        if cmd is None:
            return {"ok": False, "detail": err}
        if not by_captain:
            ok, why = station_model.may_on_initiative(cmd, station_model.delegation_of(state, "flight"), set(self.standing()))
            if not ok:
                return {"ok": False, "detail": why}
        wire = station_model.to_wire(cmd, by="captain" if by_captain else "officer")
        try:
            return await self.execute("station", wire, "flight")
        except asyncio.TimeoutError:
            return {"ok": False, "detail": "no response from the flight console"}
        except Exception as exc:  # noqa: BLE001
            log.exception("the flight console's command failed")
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:160]}

    def _remember(self, a: dict[str, Any]) -> None:
        key, mem = str(a.get("speaker") or ""), str(a.get("memory") or "").strip()[:400]
        if key not in CAST or not mem:
            return
        mems = self.memories.setdefault(key, [])
        if any(m["memory"].lower() == mem.lower() for m in mems):
            return
        mems.append({"kind": str(a.get("kind") or "moment"), "memory": mem})
        while len(mems) > MEMORY_PER * 2:
            mems.pop(next((i for i, m in enumerate(mems) if m.get("kind") != "promise"), 0))
        log.info("flight memory %s: %s", key, mem)
        self.save()

    # ------------------------------------------------------------------------------------------------ a line that waited
    async def rethink(self, key: str, text: str, waited_s: float, cut_after: str, lang: str) -> str | None:
        """A person on the net thinks again about a line that waited (or was cut off) before it is said: what they say now, or None (the speech floor calls it:
        docs/ARCHITETTURA.md §1bis, point 5)."""
        if key not in CAST:
            return text
        cut = f" They had said only «{cut_after}» when the Captain spoke over them." if cut_after else ""
        ask = (f"{waited_s:.0f} seconds ago {self.radio(key)} was about to say on the net: «{text}».{cut} The fight has moved on (the boards below are now). If it still matters "
               "to the Captain, say it now as it stands — updated, short — with say. If not, say nothing: call stay_quiet.")
        user = f"THE NET, newest last\n{self._recall(8)}\n\nTHE AIR GROUP NOW\n{self._board(self.state)}\n\n{ask}"
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
