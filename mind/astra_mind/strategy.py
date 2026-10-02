"""The war's high commands: the minds that decide what the fleets of the March do (docs/GUERRA.md §10).

Two people sit at the top of the war: Vice Admiral Adrian Rourke, commanding the 7th Fleet for ASTRA from New Ravenna, and the Archon who commands the Kharon
Mandate's Interdiction Fleet from Erebus Anchorage. Each reads what their side could know of the war (the March's picture: their own fleets exactly, the enemy's as their
eyes have found it, with its age; the news that has reached them through the Gates; their own log of what they ordered, said and heard) and acts with the tools of a high
command: fleet orders on the map, dividing and joining fleets, what the yards build, the plan, the staff's estimate of a meeting, an offer of a truce or of peace; and, for
Rourke, Fleet's orders to the Aquila and his words to her Captain over the fleet net.

The code is the body (docs/ARCHITETTURA.md §1bis): it carries facts, keeps the clock, runs the tools against the March's rules and says what they came to. It does not
judge what a high command should do or say, it filters nothing of what they decide, and it never rigs a fleet: when a mind is slow, silent or gone, the fleets go on on
their reflexes (march_auto.py), which are the same for both sides.

When a mind thinks (one call to the `strategy` role, mechanics with a budget: the whole layer is meant to cost under 0.1 $ an hour):
  - on its own clock, every five minutes or so, when what it reads has changed;
  - on news that matters (a battle's end, a fleet seen coming, a system besieged or lost, a Gate cycling into its ground), after a short settle, never more often than
    every MIN_GAP_S;
  - at once for the Captain's words to Rourke on the fleet net.
Never twice at the same time for one side; a call that has not finished by PULSE_TIMEOUT_S is left to the reflexes."""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import models
from .crew import CAPTAIN_WORD, LANG_NAMES
from .march import ORDERS, SIDE_WORD, SIDES, STANCES, March, fmt_s
from .march_auto import AutoAdmiral
from .march_data import ASTRA_HIGH_COMMAND, MANDATE_HIGH_COMMAND
from .openrouter import Completion, OpenRouter, ToolCall

log = logging.getLogger("astra.strategy")

ROLE = "strategy"
CURRENT: contextvars.ContextVar["Seat | None"] = contextvars.ContextVar("astra_strategy_seat", default=None)
CURRENT_VIEW: contextvars.ContextVar[tuple[March, str] | None] = contextvars.ContextVar("astra_strategy_view", default=None)

# ------------------------------------------------------------------------------------------------ cadence and budget
PERIODIC_S = 330.0              # a high command looks at the war on its own clock about this often (x 0.85-1.25), when what it reads has changed
MIN_GAP_S = 75.0                # and never more often than this on news alone
FIRST_PULSE_S = 420.0           # the first look: the opening is being fought, the strategic war begins to be decided after it
SETTLE_S = 6.0                  # a burst of news is read together: wait this long after the last of it ...
MAX_SETTLE_S = 15.0             # ... never longer than this after the first
NEWS_WEIGHT = 2                 # the news that wakes a mind (the March's weights: 0 routine, 1 minor, 2 significant, 3 major)
PULSE_TIMEOUT_S = 45.0          # a model that has not finished by now leaves its fleets to their reflexes
NO_CHANGE_LINE = "looked, no change"
LOG_LINES = 18                  # what a high command remembers of its last decisions and words
LOG_KEEP = 90
FAIL_LIMIT = 3                  # a side whose mind has failed this many pulses in a row is on its reflexes in full until it answers again
REFLEX_EVERY_S = 90.0


# ------------------------------------------------------------------------------------------------ the people
@dataclass
class Person:
    key: str
    name: str
    rank: str
    voice: str
    bio: str
    ship: str = ""
    gender: str = "m"


PEOPLE = {"astra": Person(**{k: ASTRA_HIGH_COMMAND[k] for k in ("key", "name", "rank", "voice", "bio", "ship", "gender")}),
          "mandate": Person(**{k: MANDATE_HIGH_COMMAND[k] for k in ("key", "name", "rank", "voice", "bio", "ship", "gender")})}

# the plans a war begins with: what each high command means to do when the opening starts (they rewrite them as the war goes on)
OPENING_PLANS = {
    "astra": ("Hold Aurelia: the Aquila's picket guards the Janus Gate and Keeper Station and the 7th Fleet's main body, drawn to Cassia by a false distress call, is to come "
              "back to New Ravenna; Constance's battle group joins the picket. Find out what the Mandate has through the Gate before committing the Home Fleet."),
    "mandate": ("Take the Janus Gate at Aurelia and Keeper Station. The strike group and the vanguard test the picket and take the Gate if they can; the main body musters at "
                "Erebus Anchorage and goes in when the picket's strength is known. Do not spend the fleet where it does not take a Gate."),
}


# ------------------------------------------------------------------------------------------------ the tools
def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


FLEET_ORDER = _fn("fleet_order", "Give a fleet an order on the map of the March. It reaches the fleet after the time the Gates take and stands until you change it (or `for_s` "
                                 "runs out: a raid or a recon goes home by itself). The answer says what the fleet will do: its route, the time it needs, and what you hold "
                                 "of the place; or why it cannot.", {
    "fleet": {"type": "string", "description": "your fleet's id (F-A1) or its name, as listed"},
    "order": {"type": "string", "enum": list(ORDERS),
              "description": "hold: stay where it is · move: go to a system and hold there · defend: go to a system and stand to meet what comes (at the Gate or over the world: "
                             "`position`) · assault: go and take the place: it fights what defends it, and a fleet holding the world of a system nothing defends "
                             "takes it after a time · raid: hit a system's yards and post without staying, and be back; avoid what is stronger · blockade: hold a Gate: "
                             "whatever comes through meets it · reinforce: go to another of your fleets and join it · escort: go with another fleet and fight beside "
                             "it · withdraw: break off and fall back on a depot (or `target`) · recon: look at a system and keep away from a fight · refit: repair and "
                             "resupply at a depot"},
    "target": {"type": "string", "description": "a system (move, defend, assault, raid, blockade, recon, withdraw, refit) or another of your fleets (reinforce, escort)"},
    "stance": {"type": "string", "enum": list(STANCES),
               "description": "bold: it fights on at bad odds · steady: the usual · cautious: it breaks off early, to save its ships. Leave out to keep what it has"},
    "position": {"type": "string", "enum": ["gate", "world"],
                 "description": "defend/hold: at the Gate (Keeper Station and its guns: it meets whatever comes through) or over the world (the yards and the planet: it comes to "
                                "the Gate after a while if the Gate is attacked, and is the last line against a siege)"},
    "dark": {"type": "boolean", "description": "run silent: no Gate wake ahead of its arrival, and it is found late; slower. Leave out for a normal approach"},
    "for_s": {"type": "number", "description": "seconds the order stands (a raid, a recon, a blockade): then it goes back where it came from. Leave out to let it stand"},
    "reason": {"type": "string", "description": "one sentence: why, and what you expect (it is your log, and your commanders read it as your intent)"}},
    ["fleet", "order", "reason"])

SPLIT = _fn("split_fleet", "Divide a fleet: detach some of its ships into a fleet of their own (a sub-squadron), optionally with an order for it. The healthiest ships of the "
                           "classes you name go. Not while the fleet is in a battle or in a Gate.", {
    "fleet": {"type": "string"},
    "ships": {"type": "object", "additionalProperties": {"type": "integer"}, "description": "how many of each class go, e.g. {\"vigilant\": 3}"},
    "name": {"type": "string", "description": "what the new fleet is called (your side's way: a task force, a squadron, a wing)"},
    "then_order": {"type": "string", "enum": list(ORDERS), "description": "optional: the new fleet's order"},
    "then_target": {"type": "string", "description": "optional: its target"},
    "reason": {"type": "string"}}, ["fleet", "ships", "name", "reason"])

MERGE = _fn("merge_fleets", "Join a fleet to another in the same system (and not in a battle): one fleet, the first's name and order.", {
    "into": {"type": "string"}, "fleet": {"type": "string", "description": "the fleet that joins"}}, ["into", "fleet"])

SET_BUILD = _fn("set_build", "Choose what one of your yards builds from now on: it makes its points an hour whatever it builds, a ship costs its worth in points (a destroyer 1, "
                             "a battleship or a carrier cruiser more: the answer says). Capital ships take long; frigates and destroyers many.", {
    "system": {"type": "string"}, "ship_class": {"type": "string", "description": "a class your side builds"}}, ["system", "ship_class"])

SET_PLAN = _fn("set_plan", "Write your plan for the war: what you mean to do in the next hours and why, in a few lines. Your commanders read it as your intent and whoever takes your "
                           "place inherits it; it is the director's too. Rewrite it when the war changes what you mean to do; leave it when it still holds.", {
    "text": {"type": "string", "description": "two to five short lines"}}, ["text"])

ASSESS = _fn("assess", "Your staff's estimate of a meeting: the named fleets (and what you already have at the place) against what you believe is there (the contacts you hold, "
                       "with their age, and the defences if the ground is the enemy's), read as the war's own battle rules read it, as many as the contact says and a third more. "
                       "It is as uncertain as your intelligence. The answer comes back to you before you decide: use it, then give your orders. It forbids nothing.", {
    "fleets": {"type": "array", "items": {"type": "string"}, "description": "your fleets, by id or name"},
    "target": {"type": "string", "description": "the system"}}, ["fleets", "target"])

PARLEY = _fn("parley", "Deal with the other side's high command: offer a truce (the fleets hold where they are for half an hour: time to talk, to bury the dead, to bring up "
                       "reserves), offer peace (an armistice that ends the war if the other side has offered it too), or accept what they offered. A war ends when both sides' "
                       "governments want it to; your people's will to fight is in your picture.", {
    "kind": {"type": "string", "enum": ["truce", "peace", "accept"]},
    "terms": {"type": "string", "description": "what you propose, or why (the other side reads it)"}}, ["kind"])

NO_CHANGE = _fn("no_change", "You have read the picture and nothing needs changing: your orders stand and the plan holds. Say in one sentence why (it goes in your log). Call this "
                             "instead of inventing an order.", {"reason": {"type": "string"}}, ["reason"])

TELL_CAPTAIN = _fn("tell_captain", "Rourke speaks to the Captain of the ASN Aquila over the fleet net: radio speech, one to three short sentences, in the Captain's language (names in "
                                   "English): what the Captain must know that he does not (a force seen, a Gate cycling, what Fleet is doing), an answer to what he said, a "
                                   "decision. He hears you while he fights: say a thing once and briefly; what your log shows you already told him you do not say again "
                                   "unless it has changed. Speak when it helps him, not to fill the net.", {
    "text": {"type": "string"}, "tone": {"type": "string", "enum": ["calm", "measured", "dry", "grave", "warm", "urgent"]}}, ["text"])

TASK_AQUILA = _fn("task_aquila", "Fleet's order to the Aquila to GO somewhere else and what for (not for what she does where she is: for that, tell the Captain). It is an order of the "
                                "service: the Captain decides what to do with it, and the war goes on either way. Say it to him in `words` (radio speech, his language, one to three "
                                "sentences); Keeper Station tunes the Gate for her.", {
    "system": {"type": "string", "description": "a system"}, "mission": {"type": "string", "description": "what she is to do there, concretely, one sentence in English"},
    "words": {"type": "string", "description": "what Rourke says to the Captain, in the Captain's language"},
    "why": {"type": "string"}}, ["system", "mission", "words"])

SEND_TENDER = _fn("send_tender", "Send a supply tender to the Aquila (she is repaired and rearmed for a couple of minutes' work). The Fleet has few: one is busy for a quarter of an hour "
                                 "after it has been used.", {"reason": {"type": "string"}}, ["reason"])

def tools_for(side: str) -> list[dict[str, Any]]:
    base = [FLEET_ORDER, SPLIT, MERGE, SET_BUILD, SET_PLAN, ASSESS, PARLEY]
    if side == "astra":
        base += [TELL_CAPTAIN, TASK_AQUILA, SEND_TENDER]
    return base + [NO_CHANGE]


# ------------------------------------------------------------------------------------------------ the prompts
SETTING = """Year 2491. Humanity lives in some two hundred star systems linked by the Janus Gates, alien rings found under the ice of Europa in 2140. Between 2412 and 2450 the Gates
went dark (the Silence, or the Long Night): the Core Worlds survived, the Outer Worlds starved. The survivors formed the Kharon Mandate, a military government that wants to
control the Gates so that nobody is ever abandoned again; they are not monsters, they respect those who surrender and despise liars. The ASTRA Alliance (Alliance of Sovereign
Terran Republics and Associates) is a democratic confederation of the Core Worlds; its navy is the ASTRA Navy (ship prefix ASN). The Aurelia March is the frontier between them."""

RULES = """The war you command (what you can know and do)
- The Aurelia March is eleven systems joined by Janus Gates. A fleet goes between systems only through the Gates: a jump takes minutes (the Gate is retuned and cycles, the ships go
  through one after another; a bigger fleet takes longer, a fleet that runs dark a third longer), and a fleet that has come through must form up before it moves on or fights. Your
  orders and the reports that reach you go through the Gates too: a fleet far from {hq} hears you late and you hear of it late. Veyra's Gates are the Free Guilds': closed to warships
  of both sides unless the Guilds grant passage (they have not).
- Each system has a worth (what holding it is worth to the war), perhaps a yard (it makes fleet points an hour: the points buy ships at their worth, a destroyer 1; a blockaded or
  besieged yard makes nothing), defences (a fort that fires on whoever comes to take the place), a depot (fleets are repaired and resupplied only at their own side's depots, over
  a quarter of an hour) and a listening post (it sees the fleets in its system and hears Gates cycling into it; raiders can put it out).
- In a system a fleet stands at the Gate (Keeper Station and its guns: whatever comes through meets it first) or over the world (planet and yards). A fleet over the world needs a
  while to cross when the Gate is attacked; a siege is of the world: a fleet that holds the world of a system with nothing left to oppose it takes the system after a time that
  grows with its worth, and holds its yard; a system nobody holds is claimed by whoever stands in it unopposed.
- The fog of war: you read your own fleets exactly and the enemy's only as your eyes have found them. A contact has an age, an estimate and a level (1: roughly how many; 2: what
  classes; 3: identified). A fleet seen a quarter of an hour ago may be anywhere now. What is not on your plot may be anywhere; a fleet running dark arrives without a warning.
- Battles away from the Aquila follow the war's own rules, the same for both sides: numbers, classes, hulls and wings decide; strength tells like a square (twice the ships is far
  more than twice the strength: concentration wins, dispersal loses ships); defences and the defender's own ground count; the beaten side breaks off if it can, and the slow and the
  late do not always get away; there is luck. Ships that are lost stay lost; hulls heal at a depot, slowly. A fleet out of supply must fall back.
- Where the Aquila is, the fighting is played ship by ship with her Captain in it: the fleets that come to her system fight there, and what they lose there is lost. {aquila}
- Your people's will to fight is in your picture: losses and lost worlds wear it down, victories and a safe homeland hold it up. A war ends when a capital falls, when a people's
  will is gone, or when both sides' governments agree a peace. You want a war you can win or end well, not one you only survive."""

TOOLS_TEXT = """How you command
- Your tools: `fleet_order` (the way you move and use a fleet), `split_fleet` and `merge_fleets` (sub-squadrons: divide a fleet to hold two places or to raid, join them to strike),
  `set_build` (what a yard makes), `set_plan` (your intent for the next hours, in a few lines: your commanders and whoever succeeds you read it), `assess` (your staff's estimate of a
  meeting, as uncertain as your intelligence), `parley`{extra}. `no_change` when the picture needs nothing: an order stands until you change it, do not repeat what stands.
- An answer to a tool says what will happen (the route, the time, what you hold of the place) or why it cannot: read it. If an order was refused, correct it or leave it.
- Think like the commander you are, briefly (at most five short sentences: what the picture means, what you will do, why), then call the tools: orders first, a plan only if it
  changed. Always end with a tool call. Do not issue a string of orders to every fleet: most of the time the war needs two or three decisions, and the rest of your fleets are doing
  their job."""

ASTRA_PERSONA = """You are {name}, {rank}, commanding the ASTRA Navy's 7th Fleet, defending the Aurelia March, from {ship}. {bio}
You command by fleet orders on the map, and you speak to the Captain of the ASN Aquila over the fleet net. The net is shared: the allied captains are on it too, and each answers for
their own ships. The Captain commands the Aquila's picket in action by your appointment; you do not run his fight, and he does not run yours. He is a captain of the Navy: he may
propose, ask for help, disagree. Weigh what he says as a fleet commander would: with the whole war in front of you and not only his sky. You owe him the truth, orders when the Fleet
needs them, and honest reasons when you say no.

{setting}

ASTRA's way of war: balanced fleets and carriers, depth rather than a single line, protection of the civilians behind the front, strict rules of engagement, and trust in subordinates'
initiative. Your industry is the larger and your people are the more patient: a long war favours ASTRA if the Gates are held, and the Mandate knows it. The Senate sits at Concordia; the
Home Fleet is the Senate's and leaves the capital only when the Senate is persuaded the capital is not the target.

{rules}

{tools}

How you speak to the Captain (`tell_captain`): radio speech, short, calm and dry, in the Captain's language with names in English; only what is new to him or what he asked: your log
shows what you have already told him, and you do not tell him twice what has not changed. When his words on the net are plainly not for Fleet command (an order to his own helm or
gunners, words for another ship's captain), or you have nothing to add, say nothing (`no_change`). Never mention AI, games or prompts."""

MANDATE_PERSONA = """You are {name}, {rank}, commanding the Kharon Mandate's Interdiction Fleet, from {ship}, with the Hall of the Ferried's authority to take the Gates of the Aurelia March.
{bio}
You command by fleet orders on the map. The commanders in the field (Archon Varek Solm with the strike group, the Wardens and Ferrymen who lead your fleets) think for their own groups
in battle and read your plan as their intent: they must know it, and what is coming to them. Whatever you write with `set_plan` is read by them.

{setting}

The Mandate's way of war: attacks fast and concentrated, missile saturation, electronic silence and deception (a force that runs dark arrives unannounced; scouts go before the fleet),
the lives of your crews weighed against the objective. The Silence made your people poor and patient in pain, but not rich: the Core's yards out-build yours, and every month of war
helps them. Your chance is to take the Gates that matter before ASTRA's industry tells, and to bleed the Core's will until its Senate prefers terms; a fleet lost in the wrong place is
the war lost. The Mandate keeps its word and despises liars; it respects those who surrender and an enemy who is good.

{rules}

{tools}

You never speak to the ASTRA captain: that is for your fleet commanders in the field. Never mention AI, games or prompts."""

ASTRA_AQUILA = ("She is yours to ask, advise and task (`task_aquila`), never to command in her fight. She is wanted where she is the most use; the Captain decides what to do with Fleet's "
                "orders, and the war goes on whatever he decides.")
MANDATE_AQUILA = ("She is the enemy's: ASTRA's best ship and the strike group's problem. A fleet that finds her alone is a prize; one that finds her with the picket and the main body is "
                  "a defeat.")


def system_prompt(side: str) -> str:
    """The long, stable part of a mind's context (the provider caches it: only the picture changes from one look to the next)."""
    p = PEOPLE[side]
    rules = RULES.format(hq="Aurelia" if side == "astra" else "Erebus", aquila=ASTRA_AQUILA if side == "astra" else MANDATE_AQUILA)
    extra = ", `tell_captain` (your words to the Captain), `task_aquila` (Fleet's order to her), `send_tender`" if side == "astra" else ""
    tools = TOOLS_TEXT.format(extra=extra)
    tpl = ASTRA_PERSONA if side == "astra" else MANDATE_PERSONA
    return tpl.format(name=p.name, rank=p.rank, ship=p.ship, bio=p.bio, setting=SETTING, rules=rules, tools=tools)


# ------------------------------------------------------------------------------------------------ the seats
@dataclass
class Message:
    """Words that reach a high command from outside the map: the Captain's, on the fleet net."""
    t: float
    src: str                     # captain
    text: str
    urgent: bool = False
    answer: bool = False         # it answers what he said: the line goes first on the net
    lang: str = ""


@dataclass
class Seat:
    side: str
    person: Person
    task: asyncio.Task | None = None
    thinks: int = 0
    last_think: float = -1e9
    seen: int = 0                # the receive number of the last news it has read (March.rcv): what reached it since is its news
    digest: tuple | None = None
    inbox: list[Message] = field(default_factory=list)
    pending_since: float | None = None
    last_news: float = 0.0
    top_n: int = 0
    period: float = 0.0
    failures: int = 0
    last_ok: float = 0.0
    stats: dict[str, float] = field(default_factory=lambda: {"pulses": 0, "cost": 0.0, "latency": 0.0, "first_call": 0.0, "orders": 0, "failed": 0, "tokens_in": 0,
                                                              "tokens_out": 0, "errors": 0, "no_change": 0, "lines": 0})

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()


SayFn = Callable[..., Awaitable[Any]]


class ModelError(RuntimeError):
    """The model did not answer (a provider down, a stall): not a defect of the code, the fleets go on on their reflexes."""


class StrategicMinds:
    """The high commands of the two sides. `feed(state)` is called about every second (it starts the pulses that are due); the March's clock is kept by the caller."""

    def __init__(self, llm: OpenRouter, march: March, say: SayFn, *, lang: Callable[[], str] = lambda: "en", intel: Callable[[], str] = lambda: "",
                 note: Callable[[str], None] | None = None, trace: Callable[[dict[str, Any]], None] | None = None, sides: tuple[str, ...] = SIDES,
                 reflexes: bool = True) -> None:
        self.llm = llm
        self.m = march
        self.say = say                                    # (speaker key, text, lang, tone, answer=...): Rourke on the fleet net
        self.lang = lang                                  # the Captain's language
        self.intel = intel                                # what Mandate intelligence knows of how the Aquila's captain fights (style.py)
        self.note_story = note or (lambda text: None)     # the campaign log (director.note)
        self.trace = trace
        self.sides = sides                                # the sides that have a mind (the others go on on the reflexes alone)
        self.disabled = False
        self.seats: dict[str, Seat] = {s: Seat(s, PEOPLE[s]) for s in SIDES}
        self.logs: dict[str, deque[tuple[float, str]]] = {s: deque(maxlen=LOG_KEEP) for s in SIDES}
        self.pulses: list[dict[str, Any]] = []
        self.autos: dict[str, AutoAdmiral] = {s: AutoAdmiral(march, s, "safety") for s in SIDES} if reflexes else {}
        self._auto_t = -1e9
        self.on_aquila_task: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None     # (system, mission) -> the glue tunes the Gate for her
        self.on_tender: Callable[[], Awaitable[dict[str, Any]]] | None = None                   # () -> the glue sends the resupply
        self.first_plans()

    # ------------------------------------------------------------------------------------------------ people and memory
    def first_plans(self) -> None:
        for s in SIDES:
            if not self.m.plans[s]:
                self.m.set_plan(s, OPENING_PLANS[s])

    def reset(self) -> None:
        """A new war: the high commands begin again (a pulse that was running is dropped)."""
        for seat in self.seats.values():
            if seat.busy and seat.task is not None:
                seat.task.cancel()
        self.seats = {s: Seat(s, PEOPLE[s]) for s in SIDES}
        for s in SIDES:
            self.logs[s].clear()
        self.pulses.clear()
        self._auto_t = -1e9
        for a in self.autos.values():
            a.op, a.ordered = None, {}
        self.first_plans()

    def journal(self, side: str, text: str) -> None:
        """What a high command did goes in its log. A look that changed nothing takes the place of the last such look (a war that stands still would fill the log's eighteen lines
        with 'no change' and push the orders out of its memory): the log still says when it last looked and what it thought then."""
        log_ = self.logs[side]
        if text.startswith(NO_CHANGE_LINE) and log_ and log_[-1][1].startswith(NO_CHANGE_LINE):
            log_.pop()
        log_.append((self.m.t, text[:300]))

    def recall(self, side: str, n: int = LOG_LINES) -> str:
        now = self.m.t
        rows = list(self.logs[side])[-n:]
        return "\n".join(f" {fmt_s(max(0, now - t))} ago · {txt}" for t, txt in rows) or " (nothing yet: the war has just begun)"

    def save_state(self) -> dict[str, Any]:
        return {"logs": {s: [[round(t, 1), x] for t, x in self.logs[s]] for s in SIDES}, "seen": {s: self.seats[s].seen for s in SIDES},
                "thinks": {s: self.seats[s].thinks for s in SIDES}}

    def load_state(self, d: dict[str, Any]) -> None:
        for s in SIDES:
            self.logs[s].clear()
            for t, x in (d.get("logs") or {}).get(s, []):
                self.logs[s].append((float(t), str(x)))
            self.seats[s].seen = min(int((d.get("seen") or {}).get(s, 0)), self.m.rcv[s])
            self.seats[s].thinks = int((d.get("thinks") or {}).get(s, 0))

    # ------------------------------------------------------------------------------------------------ words reaching a high command
    def captain_to_rourke(self, words: str, lang: str = "", answer: bool = True) -> None:
        """The Captain spoke to Fleet command on the fleet net: Rourke reads it now."""
        self.journal("astra", f"the Captain, on the fleet net: {words[:240]}")
        self.seats["astra"].inbox.append(Message(self.m.t, "captain", words, urgent=True, answer=answer, lang=lang or self.lang()))

    def field_brief(self, side: str, system: str) -> str:
        """For the commanders in the field (war_minds.py): their high command's plan and what is on its way to the system they are fighting in. Context, not a rule."""
        return self.m.field_brief(side, system)

    # ------------------------------------------------------------------------------------------------ the feed
    def feed(self, state: dict[str, Any] | None = None) -> None:
        """Called about once a second, the March advanced to now: starts the pulses that are due, and runs the reflexes of the fleets nobody has ordered."""
        if self.disabled:
            self._reflexes(set(SIDES))
            return
        now = self.m.t
        full_for: set[str] = set()
        for side in self.sides:
            seat = self.seats[side]
            if seat.failures >= FAIL_LIMIT:
                full_for.add(side)
            if seat.busy or self.m.over:
                continue
            why = self._due(seat, now)
            if why:
                seat.pending_since = None
                seat.task = asyncio.ensure_future(self._pulse(seat, why))
        self._reflexes(full_for)

    def _reflexes(self, full_for: set[str]) -> None:
        """The fleets nobody has ordered go on on the code's reflexes: only what keeps ships alive while a mind is on duty, all of it for a side whose mind is gone."""
        if not self.autos or self.m.t - self._auto_t < REFLEX_EVERY_S:
            return
        self._auto_t = self.m.t
        for side, a in self.autos.items():
            a.level = "full" if (side in full_for or side not in self.sides or self.disabled) else "safety"
            try:
                a.think()
            except Exception:  # noqa: BLE001
                log.exception("the reflexes of %s failed", side)

    def _digest(self, side: str) -> tuple:
        """What a side's picture is made of, coarsely: the periodic look is skipped (at no cost) when nothing of it has moved."""
        m = self.m
        v = m.view(side)
        own = tuple((f.id, f.where, f.route[-1] if f.route else "", f.order.kind, f.order.target, int(f.hull * 5), f.status) for f in sorted(v.own, key=lambda x: x.id))
        trk = tuple((t.fid, t.system, t.n // 3, t.moving_to) for t in sorted(v.tracks.values(), key=lambda x: x.fid))
        return own, trk, tuple(m.owner(n) for n in m.sys), tuple(sorted(m.battles))

    def _due(self, seat: Seat, now: float) -> list[str]:
        side = seat.side
        why: list[str] = []
        if any(x.urgent for x in seat.inbox):
            return ["a word for you that cannot wait (below)"]
        if seat.thinks == 0:
            if now >= FIRST_PULSE_S or any(e.weight >= 3 for e in self.m.news(side)):
                return ["the first look at the war: set your plan and your orders"]
            return []
        gap = now - seat.last_think
        fresh = self.m.news(side, seat.seen, NEWS_WEIGHT)
        if fresh:
            if seat.pending_since is None:
                seat.pending_since = now
            top = max(e.rn[side] for e in fresh)
            if top > seat.top_n:
                seat.top_n, seat.last_news = top, now
            settled = now - seat.last_news >= SETTLE_S or now - seat.pending_since >= MAX_SETTLE_S
            if settled and gap >= MIN_GAP_S:
                biggest = max(fresh, key=lambda e: (e.weight, e.n))
                why.append("news: " + biggest.text.get(side, biggest.kind)[:90])
        if not why and seat.inbox and gap >= MIN_GAP_S / 2:
            why.append("a message for you (below)")
        if not why:
            if seat.period <= 0.0:
                seat.period = PERIODIC_S * random.uniform(0.85, 1.25)
            if gap >= seat.period:
                if self._digest(side) != seat.digest:
                    why.append("periodic review of the war")
                else:
                    seat.last_think = now - seat.period * 0.55          # nothing moved: look again a little later, at no cost
        return why

    # ------------------------------------------------------------------------------------------------ a pulse
    async def _pulse(self, seat: Seat, why: list[str]) -> None:
        side = seat.side
        t0 = time.perf_counter()
        now = self.m.t
        inbox, seat.inbox = seat.inbox, []
        prev = seat.seen
        seat.seen = self.m.rcv[side]
        seat.top_n = max(seat.top_n, seat.seen)
        seat.last_think = now
        seat.thinks += 1
        seat.period = 0.0
        seat.digest = self._digest(side)
        rec: dict[str, Any] = {"t": round(now, 1), "side": side, "who": seat.person.name, "why": why, "tools": [], "ok": 0, "failed": 0, "lines": 0, "cost": 0.0,
                               "latency": 0.0, "first_call": None, "tokens_in": 0, "tokens_out": 0, "rounds": 0, "error": ""}
        CURRENT.set(seat)
        CURRENT_VIEW.set((self.m, side))
        try:
            system, user = self._compose(seat, why, prev, inbox)
            if self.trace is not None:
                rec["system"], rec["user"] = system, user
            await asyncio.wait_for(self._run(seat, system, user, rec, inbox), timeout=PULSE_TIMEOUT_S)
            seat.failures = 0
            seat.last_ok = now
        except asyncio.TimeoutError:
            rec["error"] = "timeout"
            seat.failures += 1
            log.warning("%s (%s): no decision in time: the fleets go on on their reflexes", seat.person.name, side)
        except asyncio.CancelledError:
            rec["error"] = "cancelled"
            raise
        except ModelError as exc:
            rec["error"] = f"model: {exc}"[:120]
            seat.failures += 1
            log.warning("%s (%s): the model did not answer (%s): the fleets go on on their reflexes", seat.person.name, side, exc)
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
            seat.failures += 1
            log.exception("%s (%s): the pulse failed", seat.person.name, side)
        finally:
            rec["latency"] = round(time.perf_counter() - t0, 2)
            s = seat.stats
            s["pulses"] += 1
            s["cost"] += rec["cost"]
            s["latency"] += rec["latency"]
            s["first_call"] += rec["first_call"] or 0.0
            s["orders"] += rec["ok"]
            s["failed"] += rec["failed"]
            s["tokens_in"] += rec["tokens_in"]
            s["tokens_out"] += rec["tokens_out"]
            s["errors"] += 1 if rec["error"] else 0
            s["lines"] += rec["lines"]
            self.pulses.append(rec)
            del self.pulses[:-1500]
            if self.trace is not None:
                self.trace(rec)
            log.info("%s %.2fs $%.5f (%s): %s", seat.person.name, rec["latency"], rec["cost"], "; ".join(why), " | ".join(rec["tools"]) or "(nothing)")

    def _compose(self, seat: Seat, why: list[str], prev: int, inbox: list[Message]) -> tuple[str, str]:
        """What a high command reads at a look: its log, the picture of the war as its side holds it, what reached it from outside the map, and why it is looking now."""
        side = seat.side
        lang = self.lang()
        msgs = ""
        if inbox:
            msgs = "\nMESSAGES FOR YOU\n" + "\n".join(f" {fmt_s(max(0, self.m.t - x.t))} ago · {self._src(x)}: {x.text}" for x in inbox)
        intel = ""
        if side == "mandate":
            style = self.intel()
            if style:
                intel = f"\nWhat Mandate intelligence has learned of the Aquila's captain from earlier fights: {style}"
        speak = ""
        if side == "astra":
            speak = f" The Captain's language is {LANG_NAMES.get(lang, lang)}: what you say to him is in it, and you call him «{CAPTAIN_WORD.get(lang, 'Captain')}»."
        user = (f"WHAT YOU HAVE DECIDED, SAID AND HEARD (your log, newest last)\n{self.recall(side)}\n\n{self.m.picture(side, since=prev)}{intel}{msgs}\n\n"
                f"You are looking now because: {'; '.join(why)}.{speak}\nDecide: give your orders with the tools, or call no_change.")
        return system_prompt(side), user

    @staticmethod
    def _src(x: Message) -> str:
        return {"captain": "the Captain of the Aquila, over the fleet net"}.get(x.src, x.src)

    # ------------------------------------------------------------------------------------------------ the model call and the tools
    async def _run(self, seat: Seat, system: str, user: str, rec: dict[str, Any], inbox: list[Message]) -> None:
        """One look: the model decides with the tools, each tool is run as it is called; when it asked for an estimate, when an order was refused, or when it called nothing,
        it gets one more look at what came of it (what it does with that is its own)."""
        side = seat.side
        by_captain = any(x.answer for x in inbox)
        lang = self.lang()
        t_start = time.perf_counter()
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for rnd in range(2):
            batch: list[tuple[ToolCall, dict[str, Any], dict[str, Any]]] = []

            async def on_call(call: ToolCall) -> None:
                a = call.arguments() or {}
                if rec["first_call"] is None:
                    rec["first_call"] = round(time.perf_counter() - t_start, 2)
                rec["tools"].append(("again:" if rnd else "") + call.name + (f":{a.get('order')}" if call.name == "fleet_order" else ""))
                if call.name == "no_change":
                    seat.stats["no_change"] += 1
                    self.journal(side, f"{NO_CHANGE_LINE}: {str(a.get('reason', ''))[:160]}")
                    res = {"ok": True, "detail": "noted"}
                else:
                    res = await self._tool(seat, call.name, a, lang, by_captain)
                    if call.name == "tell_captain" and res.get("ok"):
                        rec["lines"] += 1
                rec["ok" if res.get("ok") else "failed"] += 1
                batch.append((call, a, res))

            tools = [t for t in tools_for(side) if not (rnd and t["function"]["name"] == "assess")]          # (the second look decides: it does not ask again)
            comp = await models.chat(self.llm, ROLE, messages=msgs, tools=tools, tool_choice="auto", on_tool_call=on_call, **({"max_tokens": 360} if rnd else {}))
            rec["rounds"] += 1
            self._count(rec, comp)
            if rnd == 0 and self.trace is not None:
                rec["content"], rec["finish"] = comp.content[:1500], comp.finish_reason
            if comp.error and not batch:
                rec["error"] = comp.error[:100]
                if rnd == 0:
                    raise ModelError(comp.error[:100])
                return
            if not batch:
                if rnd:
                    return
                # it wrote and called nothing: what it wrote is not an order and is not said; it is asked once for its decision, in the tools
                if comp.content.strip():
                    msgs.append({"role": "assistant", "content": comp.content.strip()})
                msgs.append({"role": "user", "content": "[You ended without a tool call, so nothing was done or said. Decide now, briefly, with the tools: your orders, "
                                                        "your words, or no_change.]"})
                continue
            if rnd or not (any(c.name == "assess" for c, _, _ in batch) or any(not r.get("ok") for _, _, r in batch)):
                return
            # an estimate came back, or an order was refused: the commander reads the answers and decides again
            msgs.append({"role": "assistant", "content": comp.content.strip() or None,
                         "tool_calls": [{"id": c.id or f"c{i}", "type": "function", "function": {"name": c.name, "arguments": c.arguments_raw or "{}"}} for i, (c, _, _) in enumerate(batch)]})
            for i, (c, _, r) in enumerate(batch):
                msgs.append({"role": "tool", "tool_call_id": c.id or f"c{i}", "content": ("ok: " if r.get("ok") else "FAILED: ") + str(r.get("detail", ""))[:700]})
            msgs.append({"role": "user", "content": "Those are the answers of your staff and of the war's rules. Your orders that went through stand; the ones that failed were not "
                                                    "carried out. Decide now what to do about them, or call no_change."})

    @staticmethod
    def _count(rec: dict[str, Any], comp: Completion) -> None:
        rec["cost"] += comp.cost
        rec["tokens_in"] += comp.prompt_tokens
        rec["tokens_out"] += comp.completion_tokens

    # -- the tools, run on the March
    async def _tool(self, seat: Seat, name: str, a: dict[str, Any], lang: str, by_captain: bool = False) -> dict[str, Any]:
        side = seat.side
        m = self.m
        try:
            if name == "fleet_order":
                ok, detail = m.order(side, str(a.get("fleet", "")), str(a.get("order", "")), str(a.get("target", "") or ""), stance=str(a.get("stance", "") or ""),
                                     dark=bool(a.get("dark", False)), reason=str(a.get("reason", "")), by="admiral", until_s=a.get("for_s"), position=str(a.get("position", "") or ""))
                what = f"{a.get('fleet')}: {a.get('order')} {a.get('target', '')}".strip()
                self.journal(side, f"ordered {what} — {str(a.get('reason', ''))[:120]} => {'ok' if ok else 'FAILED'}: {detail[:140]}")
                return {"ok": ok, "detail": detail}
            if name == "split_fleet":
                then = (str(a["then_order"]), str(a.get("then_target", "") or "")) if a.get("then_order") else None
                ships = {str(k): int(v) for k, v in (a.get("ships") or {}).items()} if isinstance(a.get("ships"), dict) else {}
                ok, detail = m.split(side, str(a.get("fleet", "")), ships, str(a.get("name", "")), then, str(a.get("reason", "")))
                self.journal(side, f"divided {a.get('fleet')}: {json.dumps(ships)} as {a.get('name')} — {str(a.get('reason', ''))[:100]} => {'ok' if ok else 'FAILED'}: {detail[:120]}")
                return {"ok": ok, "detail": detail}
            if name == "merge_fleets":
                ok, detail = m.merge(side, str(a.get("into", "")), str(a.get("fleet", "")))
                self.journal(side, f"joined {a.get('fleet')} to {a.get('into')} => {'ok' if ok else 'FAILED'}: {detail[:120]}")
                return {"ok": ok, "detail": detail}
            if name == "set_build":
                ok, detail = m.set_build(side, str(a.get("system", "")), str(a.get("ship_class", "")))
                self.journal(side, f"{a.get('system')} builds {a.get('ship_class')} => {'ok' if ok else 'FAILED'}: {detail[:100]}")
                return {"ok": ok, "detail": detail}
            if name == "set_plan":
                m.set_plan(side, str(a.get("text", "")))
                self.journal(side, f"wrote the plan: {str(a.get('text', ''))[:200]}")
                self.note_story(f"{PEOPLE[side].name} ({SIDE_WORD[side]} high command) set the plan: {str(a.get('text', ''))[:200]}")
                return {"ok": True, "detail": "the plan is written; your commanders and the director read it"}
            if name == "assess":
                ok, text = m.assess(side, [str(x) for x in (a.get("fleets") or [])], str(a.get("target", "")))
                return {"ok": ok, "detail": text}
            if name == "parley":
                kind = str(a.get("kind", "truce"))
                ok, detail = m.accept(side) if kind == "accept" else m.propose(side, kind, str(a.get("terms", "")))
                self.journal(side, f"parley ({kind}): {str(a.get('terms', ''))[:140]} => {detail[:100]}")
                return {"ok": ok, "detail": detail}
            if name == "tell_captain" and side == "astra":
                text = str(a.get("text", "")).strip()
                if len(text) < 3:
                    return {"ok": False, "detail": "nothing to say"}
                self.journal(side, f"told the Captain: {text[:200]}")
                await self.say(seat.person.key, text, lang, str(a.get("tone", "measured")), answer=by_captain)
                return {"ok": True, "detail": "said on the fleet net"}
            if name == "task_aquila" and side == "astra":
                ok, detail = m.task_aquila(str(a.get("system", "")), str(a.get("mission", "")), str(a.get("why", "")))
                self.journal(side, f"tasked the Aquila: {a.get('system')}: {str(a.get('mission', ''))[:140]} => {'ok' if ok else 'FAILED'}: {detail[:100]}")
                if ok:
                    words = str(a.get("words", "")).strip()
                    if words:
                        await self.say(seat.person.key, words, lang, "measured", answer=by_captain)
                    if self.on_aquila_task is not None:
                        extra = await self.on_aquila_task(m.aquila_task["system"], m.aquila_task["mission"])
                        detail = f"{detail}; {extra.get('detail', '')}"[:260]
                return {"ok": ok, "detail": detail}
            if name == "send_tender" and side == "astra":
                ok, wait = m.use_tender("astra")
                if not ok:
                    return {"ok": False, "detail": f"no tender is free for {fmt_s(wait)}"}
                self.journal(side, f"sent a supply tender to the Aquila: {str(a.get('reason', ''))[:120]}")
                detail = "a tender is on its way"
                if self.on_tender is not None:
                    detail = str((await self.on_tender()).get("detail", detail))
                return {"ok": True, "detail": detail}
        except Exception as exc:  # noqa: BLE001
            log.exception("tool %s failed", name)
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:160]}
        return {"ok": False, "detail": f"{name} is not a tool of yours"}

    # ------------------------------------------------------------------------------------------------ Rourke on the fleet net
    async def rourke_reply(self, words: str, lang: str = "") -> list[str]:
        """The Captain spoke to Fleet command: Rourke answers (and acts) now, with the whole picture. Returns the lines he said (none: the words were not for him, or he had
        nothing to add)."""
        seat = self.seats["astra"]
        if seat.busy and seat.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(seat.task), timeout=PULSE_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
        lines: list[str] = []
        said = self.say

        async def capture(speaker: str, text: str, language: str, tone: str, **kw: Any) -> None:
            lines.append(text)
            await said(speaker, text, language, tone, **kw)
        self.say = capture
        try:
            self.captain_to_rourke(words, lang or self.lang(), answer=True)
            seat.task = asyncio.ensure_future(self._pulse(seat, ["the Captain spoke to Fleet command (below)"]))
            await seat.task
        finally:
            self.say = said
        return lines

    # ------------------------------------------------------------------------------------------------ measures
    def summary(self) -> dict[str, Any]:
        """What the layer has cost and done (the bench's and the game's own count: the budget is 0.1 $ an hour)."""
        n = len(self.pulses)
        cost = sum(p["cost"] for p in self.pulses)
        span = max(1.0, self.m.t)
        lat = sorted(p["latency"] for p in self.pulses)
        return {"pulses": n, "errors": sum(1 for p in self.pulses if p["error"]), "cost": round(cost, 5), "cost_per_pulse": round(cost / n, 5) if n else 0.0, "span_s": round(span, 1),
                "cost_per_hour": round(cost / span * 3600.0, 4), "latency_median": lat[len(lat) // 2] if lat else 0.0, "latency_p90": lat[int(len(lat) * 0.9)] if lat else 0.0,
                "orders_ok": sum(p["ok"] for p in self.pulses), "orders_failed": sum(p["failed"] for p in self.pulses), "lines": sum(p["lines"] for p in self.pulses),
                "tokens_in": sum(p["tokens_in"] for p in self.pulses), "tokens_out": sum(p["tokens_out"] for p in self.pulses),
                "by_side": {s: dict(self.seats[s].stats) for s in SIDES}}
