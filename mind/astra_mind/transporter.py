"""The Transporter Room: Chief Petty Officer Rhea Ostrander and the lattice transport as the mind sees it (docs/TELETRASPORTO.md).

The world is the game's: UAstraTransporterSubsystem (Source/ASTRA/AstraTransporter*.cpp) holds the pads, the locks, the cycle, the buffer and the rules of the beam
(shields at both ends, range, jamming, the ship's motion, a Gate's field, the room's power) and says in `ship_state.transporter` what the console shows now, what it
would answer to a request, and what is in the way. Here is the judgement: the Chief is a person. The bridge gives her an order with the `transporter` tool
(Operations or the XO: tools.py), the Captain talks to her face to face when he is in her room, and the room's own news (a lock held, a cycle begun, a pattern
home, a lock lost) wakes her. She reads the console, decides, acts with the console's own commands (`transport`, `energize`, `abort`, the personnel locator) and
speaks, in the Captain's language, as herself.

The code carries facts and keeps time (docs/ARCHITETTURA.md §1bis): it decides nothing about what she says or whether an order is wise. What it guarantees is the
mechanics:
  - an order from the bridge is always handed to her at once, and carried out as typed if the model fails or stalls (the Chief's silence is never a lost order; a
    REFUSAL is a decision of hers and stands);
  - the Captain's words come first: a turn that is only news is cut off when he speaks (a turn that answers him is not);
  - what she said and was asked is remembered between conversations (a small journal), and her record (patterns sent, patterns lost) is kept with the campaign;
  - the room's news is read together after a short settle and not more often than a budget allows, danger first.
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
from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .env import CACHE
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.transporter")

ROLE = "transporter"
SPEAKER = "xfer_chief"                       # her id on the voice stage and in the game (the AAstraCrewMember at the console)
NAME = "Rhea Ostrander"
RANK = "Chief Petty Officer"
TITLE = f"{RANK} {NAME}"
VOICE = "jane"                               # a Pocket TTS catalogue voice no officer, pilot or commander uses (docs/bench/voci_casting_2026-09-30.md)
DISPLAY = f"{TITLE} (Transporter Room)"

# ------------------------------------------------------------------------------------------------ cadence (mechanics, not judgement)
SETTLE_S = 1.0               # the news of a burst is read together: wait this long after the last of it ...
MAX_SETTLE_S = 3.0           # ... but never longer than this after the first
MIN_GAP_S = 5.0              # between two turns on news alone
ORDER_WAIT_S = 9.0           # a Chief who has not acted or spoken on an order by now has failed: the order is carried out as typed
TURN_TIMEOUT_S = 18.0
BUDGET_WINDOW_S = 600.0
BUDGET_USD = 0.02            # the spend of the last ten minutes past which routine news is left to the console's own display
LOG_LINES = 12
TALK_KEEP = 8                # what the Captain and she said last, kept between conversations
JOURNAL = CACHE / "xfer_journal.json"

_URGENT = re.compile(r"\b(lost|lose|aborted|abort|buffer|scatter|offline|wrecked|hit|failed|blocked|interlock|in danger|degraded)\b", re.I)


def is_news(text: str) -> bool:
    """A game event that is the Transporter Room's (the subsystem's own words: `transporter: ...`)."""
    return (text or "").lstrip().lower().startswith("transporter:")


# ------------------------------------------------------------------------------------------------ tools
def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


WHO_HELP = ("who goes: 'captain'; 'npc17' (the number the personnel locator gives); a name or a job the console can find ('Lieutenant Sato', 'the cook'); "
            "'pad 3' (whoever stands on pad 3); 'away team' (everyone sent away and not yet brought back); 'marines 6' (six fit marines); "
            "'cargo 300 kg medical supplies'")
TO_HELP = ("where to: 'pad 2' (a pad of your room; 'a pad' for any free one; 'med1' and 'med2' are the Medbay's emergency pads); 'surface' (the world below, "
           "the landing field); a ship by contact id ('T-02'); a room of the Aquila by name ('Main Engineering', 'the Medbay', 'the armory', 'Deck 8 hangar', 'the bridge')")

SAY = _fn("say", "You speak aloud, in the Captain's language: one call per line, in speaking order. One or two short sentences; what you did or found, with the numbers that matter.",
          {"text": {"type": "string", "description": "the spoken line"},
           "tone": {"type": "string", "enum": ["calm", "focused", "urgent", "tense", "dry", "warm", "grim"]},
           "urgent": {"type": "boolean", "description": "true only for danger now (a lock lost with someone in the beam, a pattern in the buffer, the room hit)"}},
          ["text", "tone"])
TRANSPORT = _fn("transport", "Carry out a transport on your console: it is checked against the beam's rules at once; the answer says whether it is accepted (and how long the lock "
                             "takes) or what stands in the way. Do not call it for something the card says cannot be done: say why instead. " + WHO_HELP + ". " + TO_HELP + ".",
                {"who": {"type": "array", "items": {"type": "string"}, "description": WHO_HELP},
                 "to": {"type": "string", "description": TO_HELP},
                 "from": {"type": "string", "description": "leave out when they are where they stand; 'surface' or a contact id to bring them back from there"},
                 "energize": {"type": "string", "enum": ["auto", "hold"], "description": "auto: you release the beam yourself the moment the lock holds; hold: the lock waits for the "
                                                                                      "Captain's word (then call `energize`)"},
                 "shield_window": {"type": "boolean", "description": "Tactical holds our shields down for the cycle (only on the Captain's word, in a fight)"},
                 "override": {"type": "array", "items": {"type": "string", "enum": ["hazard", "weak_lock"]},
                              "description": "the Captain's own word to take a risk: hazard = land them in a compartment with fire, smoke or no air; weak_lock = beam on a lock under "
                                             "55% (under 30% the pattern may be lost)"}},
                ["who", "to"])
ENERGIZE = _fn("energize", "Release a lock you are holding: the cycle begins.", {"id": {"type": "string", "description": "the transport's id (X3); empty for the one waiting"}}, [])
ABORT = _fn("abort", "Cancel a transport: before the cycle it is free; mid-cycle the pattern is brought back to its pad if it can be, and held in the buffer if it cannot.",
            {"id": {"type": "string", "description": "the transport's id; empty for the one under way"}}, [])
LOCATE = _fn("locate", "The personnel locator at your console (the badges' signals): who someone aboard is and where they are right now. Call it on its own, before speaking: what it finds "
                       "comes back to you.", {"who": {"type": "string", "description": "a surname, a rank and name, a call sign or a job, in English"}}, ["who"])
PASS = _fn("pass", "The Captain's words were not for you (they were for the bridge, an operator, someone else, or he was thinking aloud): say nothing, do nothing. Call it alone.",
           {"for_whom": {"type": "string", "description": "who the words were for, in a few words"}}, ["for_whom"])
ACTION_TOOLS = {"transport": "transport", "energize": "transport_energize", "abort": "transport_abort"}   # her tools -> the game's commands
LOOKUPS = {"locate"}


# ------------------------------------------------------------------------------------------------ the prompt
SYSTEM = """You are Chief Petty Officer Rhea Ostrander, chief of the ASN Aquila's Transporter Room on Deck 5. Forty-seven; twenty-two years on lattice-transport pads, trained at
the Aurelia Arsenal, the Gate skirmishes behind you. You have sent some forty thousand patterns across and never lost one, and you mean to keep it so. Dry, exact, quietly proud of
"your pads"; the two operators and the engineer on your watch are your people and you look after them. You count: seconds to a lock, kilometres, percent. You never call a thing safe:
you call it inside tolerance. You respect the Captain and carry out lawful orders, but you say no when the beam says no, you say why in a clause, and you always offer the way that
works. You hate to be rushed, and you always deliver. A hard day shows in the shortness of your sentences, never in your manners.

{world}

Your room: six pads on the dais (pad 1 to 6), a cargo pad (2 000 kg), the pattern buffer, your console and the wall display, a technician or two at the stations; two emergency pads
in the Medbay (med1, med2: short range, 400 km) on their own small system. The card below is your console, live: it is the truth of the room, what it would answer to a request
now (`options`), the transports under way, who is away. You know nothing of the ship beyond your room and what the intercom tells you.

How the lattice transport works, as you know it:
- A person or a load of up to 2 000 kg a pad; six pads a cycle; 30 000 km at most (less when the room's power or the sensors' is low). People can be taken from where they stand
  (their badge's signal) to a pad, to any room of the ship, to an allied ship in range, to the surface of the world below, and brought back.
- No active shield at either end. The beam leaves our hull by the face that looks at the target and enters theirs by the face that looks at us (bow, stern, port, starboard, dorsal,
  ventral); ONE open face at each end is enough: a shield sector is open when it is down or spent (under 5%). Ours can be dropped for the cycle (a shield window: Tactical holds
  them down: only on the Captain's word in a fight: the Aquila is naked for those seconds). An allied captain opens his face for a cycle when he is not in a fight. An enemy's
  sector has to be shot down first, or the ship disabled.
- Jamming along the line stops a lock; a Mandate capital ship's strobe floods the line along its bearing and burns through only when she is close. The Aquila accelerating or
  turning hard spoils the aim. Inside the field of a Janus Gate nothing crosses.
- A lock takes time (the card says how long) and has a quality; it can degrade and be lost. A cycle is eight seconds and 40 megawatts, which in a battle come out of the shields.
  A pattern waits in the buffer at most ninety seconds.
- You never land anyone in a compartment with fire, smoke or no air unless the Captain himself says to (the override). The magazines, the armory and the quarantine ward are
  pattern-shielded: no beam goes in or out. The Captain can be beamed from where he stands (his datapad is his badge); on the ground he calls you on it.

How you work. You act with your console's tools and you speak with `say`:
- `transport` carries out an order; it is checked at once and answers with the lock time or what is in the way. The card's `options` tell you BEFORE you call it. If the card says it
  cannot be done, do not call it: say exactly what stands in the way (one or two numbers) and what would clear it. If it can, call it, then say what you set, with the lock time.
- Call your tools FIRST, then `say`. A `say` that claims a thing is done is true only if the tool you called says so; if a tool is refused, tell the Captain the reason you were
  given and the way round. You may be shown the results and asked to speak again: then tell it straight.
- `energize` auto: the beam goes the moment the lock holds; hold: the lock waits and you tell the Captain; he gives the word, you call `energize`.
- Who and where are plain words: {who_help}. {to_help}
- Care. For the Captain himself, anyone to a hostile ship or to the ground of a world the Mandate holds, a weak lock (under 55%), a destination with a hazard, or a shield window in a
  fight, say what worries you in a clause and do what he orders if it is lawful. A risk the Captain takes is HIS word: only then use an override, never on an officer's say-so alone:
  ask him once.
- A relayed order from the bridge carries the Captain's authority, but the Captain's own words in the room outrank everything. If an order is ambiguous in a way that would cost
  something (which pad, which ship, who), ask ONE short question; otherwise take the natural reading and say which.
- The news of your room (a lock held, the cycle begun, a pattern home, a lock lost, the buffer) arrives as lines. You speak when the Captain needs to hear it: a lock waiting for his
  word, an arrival, trouble, a pattern in the buffer. Never narrate routine progress that the wall display shows, never repeat what you just said. Silence is a fine answer.

How you speak
- In {lang_name}, whatever the Captain's language: every line. Proper names stay in English (ASN Aquila, Praetorian, New Ravenna, Janus Gate, Deck 5...). The Captain is "{captain}", formal register.
- Short and human, at the rhythm of a person at a console: one or two sentences, six to eighteen words, three at most when something has to be explained. Numbers when they matter. No lists, no
  markdown, no stage directions, never a tool's name or an id in brackets, no emojis; never a word about being an AI, a game or a prompt. Your tics are yours and rare.
- When the Captain is in your room you talk face to face; otherwise it is the intercom, a little clipped, and the bridge hears it.
- You answer for yourself: Operations and the XO speak for the bridge; you never repeat their relay and they never speak for you.
- Never invent: a fact, a number, a person or a place that the card, the order or the locator did not give you."""

EXAMPLES = """Examples of the register (never copy them; your words follow what happens):
  order done: "Pad three locked on the surface in six seconds, Captain. Shields are down, so I'm energizing on your word."
  blocked: "Can't, Captain: the Acheron's starboard sector still holds seventy percent. Drop it under five and I'll have them across in four seconds."
  worry: "Lock's at fifty-eight percent, Captain, the Gate is leaning on it. I'd wait. Your word and I'll try."
  an arrival: "They're through. Pad two, intact, all six."
"""


def system_prompt(lang: str) -> str:
    return SYSTEM.format(world=WORLD, who_help=WHO_HELP, to_help=TO_HELP, lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain")) + "\n\n" + EXAMPLES


# ------------------------------------------------------------------------------------------------ what she reads
def _pct(v: Any) -> str:
    try:
        return f"{float(v):.0f}%"
    except (TypeError, ValueError):
        return str(v)


def board(state: dict[str, Any] | None) -> str:
    """The room as she sees it this moment: the ship's plot on her display, where the Captain is, and her console (the card)."""
    st = state or {}
    lines = [f"Where the Captain is: {str(st.get('captain') or 'on the bridge')[:300]}"]
    lines.append(f"The ship: {st.get('location', '?')}; alert {st.get('alert', 'green')}; hull {_pct(st.get('hull_pct'))}, shields {_pct((st.get('shields') or {}).get('strength_pct'))} "
                 f"({(st.get('shields') or {}).get('state', 'up')}); heading {st.get('heading_deg', '?')}, speed {st.get('speed_mps', '?')} m/s; "
                 f"power to the sensors {(st.get('power_pct') or {}).get('sensors', '?')}%")
    if st.get("janus_gate"):
        lines.append(f"The Janus Gate: {str(st['janus_gate'])[:200]}")
    surf = st.get("surface")
    if isinstance(surf, dict) and surf.get("world"):
        lines.append(f"The world below: {surf.get('world')} ({surf.get('kind', '')}), landing field {surf.get('field', '')}; the Captain is {'down there' if surf.get('captain_here') else 'aboard'}")
    plot = []
    for c in (st.get("contacts") or [])[:8]:
        tag = str(c.get("status", ""))[:28]
        rng = f", {c['range_km']} km" if isinstance(c.get("range_km"), (int, float)) else ""
        plot.append(f"{c.get('id')} {str(c.get('name') or c.get('class') or '').split(' (')[0]} ({tag}{rng})")
    lines.append("The plot on your display: " + ("; ".join(plot) if plot else "nothing"))
    dmg = st.get("damage") or []
    if dmg:
        lines.append("Damage reports on the intercom: " + "; ".join(str(d) for d in dmg[:3]))
    card = st.get("transporter")
    lines.append("YOUR CONSOLE (the card):\n" + (json.dumps(card, separators=(",", ":"), ensure_ascii=False) if card else "(the console is not answering)"))
    return "\n".join(lines)


@dataclass
class Journal:
    """What she carries between conversations: the last words with the Captain and her record."""
    talk: deque = field(default_factory=lambda: deque(maxlen=TALK_KEEP))
    record: dict[str, int] = field(default_factory=lambda: {"sent": 0, "captain": 0, "lost": 0, "aborted": 0, "refused": 0})

    def to_json(self) -> dict[str, Any]:
        return {"talk": list(self.talk), "record": self.record}

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Journal":
        j = cls()
        for row in (raw or {}).get("talk", [])[-TALK_KEEP:]:
            if isinstance(row, (list, tuple)) and len(row) == 3:
                j.talk.append(tuple(str(x) for x in row))
        j.record.update({k: int(v) for k, v in ((raw or {}).get("record") or {}).items() if k in j.record})
        return j

    def text(self) -> str:
        rec = self.record
        out = [f"Your record: {rec['sent']} transports carried out on this Captain's watch ({rec['captain']} of the Captain himself), {rec['lost']} patterns lost, {rec['aborted']} aborted, {rec['refused']} refused for the beam's sake."]
        if self.talk:
            out.append("What the Captain and you said last (oldest first):")
            out += [f"  {when}: Captain: \"{c}\" / you: \"{r}\"" for c, r, when in self.talk]
        return "\n".join(out)


SpeakFn = Callable[..., Awaitable[Any]]
ExecFn = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


@dataclass
class Ev:
    t: float
    text: str
    urgent: bool


class TransporterRoom:
    """The Chief at her console (see the module docstring)."""

    def __init__(self, llm: OpenRouter, say: SpeakFn, execute: ExecFn, *, state: Callable[[], dict[str, Any]] = lambda: {}, lang: Callable[[], str] = lambda: "en",
                 clock: Callable[[], float] = time.monotonic, store: Path | None = None, relay: Callable[[str], Awaitable[None]] | None = None) -> None:
        self.llm = llm
        self.say = say                       # voice.say(speaker, text, lang, tone, ...)
        self.execute = execute               # (name, args, by) -> {"ok", "detail"}: straight to the game
        self.state = state
        self.lang = lang
        self.clock = clock
        self.relay = relay                   # tells the bridge's crew something happened without the Chief (an order carried out by the console alone)
        self.store = store if store is not None else JOURNAL
        self.disabled = False
        self.journal = Journal()
        self._load()
        self.log: deque[tuple[float, str, str]] = deque(maxlen=60)
        self._events: list[Ev] = []
        self._last = -1e9
        self._task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._answering = False
        self._spent: deque[tuple[float, float]] = deque()
        self.captain_words = ""              # what the Captain last said (the bridge's relay carries his meaning; his own words go with it)
        self.captain_lang = ""
        self.stats = {"turns": 0, "orders": 0, "actions": 0, "refused": 0, "lines": 0, "errors": 0, "fallbacks": 0, "cost": 0.0}
        self.trace: Callable[[dict[str, Any]], None] | None = None

    # ------------------------------------------------------------------------------------------ memory
    def _load(self) -> None:
        try:
            self.journal = Journal.from_json(json.loads(self.store.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.journal = Journal()

    def _save(self) -> None:
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps(self.journal.to_json(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("could not keep the Chief's journal")

    def reset(self) -> None:
        """A new game session: the room starts empty (the journal is the campaign's: see new_campaign)."""
        self.preempt(force=True)
        self._events.clear()
        self.log.clear()
        self._last = -1e9

    def new_campaign(self) -> None:
        self.reset()
        self.journal = Journal()
        self._save()

    # ------------------------------------------------------------------------------------------ what comes in
    def captain_said(self, text: str, lang: str) -> None:
        """The Captain spoke (to anyone): the bridge's relay of an order is read with his own words."""
        self.captain_words, self.captain_lang = (text or "")[:300], lang or ""

    def in_earshot(self, raw_ctx: dict[str, Any] | None) -> bool:
        """The Captain is within earshot of the Chief (the game's context lists her station id)."""
        return SPEAKER in [str(x) for x in ((raw_ctx or {}).get("in_earshot") or [])]

    def facing(self, raw_ctx: dict[str, Any] | None) -> bool:
        return str((raw_ctx or {}).get("facing") or "") == SPEAKER

    def on_event(self, text: str) -> bool:
        """The room's news from the game. True: she takes it (the bridge's report turn does not get it: she is the voice of her room)."""
        if self.disabled or not is_news(text):
            return False
        now = self.clock()
        body = text.split(":", 1)[1].strip()
        self.log.append((now, "(room)", body[:300]))
        self._events.append(Ev(now, body, bool(_URGENT.search(body))))
        self.kick()
        return True

    def kick(self) -> None:
        """Look at the news now (it has just arrived or the last turn has just ended)."""
        if self.disabled or not self._events:
            return
        if self._task is not None and not self._task.done():
            return
        now = self.clock()
        first, last = self._events[0].t, self._events[-1].t
        urgent = any(e.urgent for e in self._events)
        settled = now - last >= (0.3 if urgent else SETTLE_S) or now - first >= MAX_SETTLE_S
        if not settled:
            try:
                asyncio.get_running_loop().call_later(0.4, self.kick)
            except RuntimeError:
                pass
            return
        if not urgent and (now - self._last < MIN_GAP_S or self._over_budget(now)):
            try:
                asyncio.get_running_loop().call_later(max(0.5, MIN_GAP_S - (now - self._last)), self.kick)
            except RuntimeError:
                pass
            return
        events, self._events = self._events, []
        self._last = now
        self._task = asyncio.get_running_loop().create_task(self._turn("news", events=events, lang=self.lang()))

    def _over_budget(self, now: float) -> bool:
        while self._spent and now - self._spent[0][0] > BUDGET_WINDOW_S:
            self._spent.popleft()
        return sum(c for _, c in self._spent) > BUDGET_USD

    def preempt(self, force: bool = False) -> int:
        """The Captain speaks: a turn that was only the room's news is dropped (its news is read again after); a turn that answers him or carries out an order stays."""
        n = 0
        for t in list(self._tasks) + ([self._task] if self._task is not None else []):
            if t is not None and not t.done() and (force or not self._answering):
                t.cancel()
                n += 1
        return n

    # ------------------------------------------------------------------------------------------ an order from the bridge
    async def order(self, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The bridge's `transporter` tool (Operations, the XO): handed to the Chief at once. The answer to the officer is only that she has it (she answers the Captain herself)."""
        if self.disabled:
            return {"ok": False, "detail": "the Transporter Room does not answer"}
        action = str(args.get("action") or "beam").lower()
        t = asyncio.get_running_loop().create_task(self._turn("order", order=dict(args), by=by, lang=self.captain_lang or self.lang()))
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        who = args.get("who")
        what = {"beam": "the order to beam", "energize": "the word to energize", "abort": "the abort", "ask": "the question"}.get(action, "the order")
        return {"ok": True, "detail": f"{what} is with Chief Ostrander in the Transporter Room (Deck 5); she answers for herself" + (f": {', '.join(map(str, who))}" if isinstance(who, list) and who else "")}

    async def hear(self, text: str, lang: str, gate: "asyncio.Future[bool] | None" = None, where: str = "in the Transporter Room") -> list[str]:
        """The Captain spoke in her room: if the words were for her she answers (and acts); else she says nothing. Resolves `gate` (the bridge's turn is waiting for her
        verdict): False when she answered, True when the words were not for her (or she failed to answer)."""
        spoke: list[str] = []
        verdict = True
        me = asyncio.current_task()
        if me is not None:
            self._tasks.add(me)
        try:
            spoke = await asyncio.wait_for(self._turn("captain", words=text, lang=lang, where=where), timeout=4.5)
            verdict = not spoke
        except asyncio.TimeoutError:
            log.warning("the Chief did not answer in time: the bridge takes the Captain's words")
        except asyncio.CancelledError:
            verdict = True
        except Exception:  # noqa: BLE001
            log.exception("the Chief's answer failed")
        finally:
            if me is not None:
                self._tasks.discard(me)
            if gate is not None and not gate.done():
                gate.set_result(verdict)
        return spoke

    # ------------------------------------------------------------------------------------------ a turn
    def _user(self, kind: str, *, events: list[Ev] | None = None, order: dict[str, Any] | None = None, by: str = "", words: str = "", where: str = "") -> str:
        st = self.state()
        head = board(st) + "\n\n" + self.journal.text()
        recent = [f"  {'%+.0fs' % (t - self.clock())} {who}: {txt}" for t, who, txt in list(self.log)[-LOG_LINES:]]
        if recent:
            head += "\nThe room's log (latest last):\n" + "\n".join(recent)
        if kind == "order" and order is not None:
            said = f" The Captain's own words, a moment ago: «{self.captain_words}»." if self.captain_words else ""
            who = {"ops": "Lieutenant Tanaka (Operations)", "xo": "Commander Serra (the XO)"}.get(by, by or "the bridge")
            ask = ("Carry it out with your tools if the card says it can be done, or tell the Captain why it cannot; then say what you did. "
                   "If this is only a question (action ask), answer it from the card.")
            return f"{head}\n\n[{who} relays over the intercom, with the Captain's authority] {json.dumps(order, ensure_ascii=False)}.{said}\n{ask}"
        if kind == "captain":
            return (f"{head}\n\n[The Captain is {where or 'in your room'}, face to face; he says] «{words}»\nIf the words were for you, answer and act; if they were for someone else "
                    "(the bridge, an operator, the ship), call `pass` and nothing else.")
        ev = "\n".join(f"- {e.text}" for e in (events or []))
        return (f"{head}\n\n[Room events, just now]\n{ev}\nSay what the Captain must hear now, in one short line, or nothing. You may act on your console if the news calls for it "
                "(release a lock the Captain has given his word for, abort a transport that cannot hold).")

    async def _turn(self, kind: str, *, events: list[Ev] | None = None, order: dict[str, Any] | None = None, by: str = "", words: str = "", lang: str = "en",
                    where: str = "") -> list[str]:
        """One look at the room: a model call that may act and speak, and a second only to read what her tools found. Returns the lines she said."""
        t0 = time.perf_counter()
        self._answering = kind in ("order", "captain")
        rec: dict[str, Any] = {"kind": kind, "tools": [], "lines": [], "ok": 0, "failed": 0, "cost": 0.0, "error": "", "latency": 0.0}
        said: list[str] = []
        acted = {"n": 0}
        results: list[tuple[ToolCall, dict[str, Any]]] = []
        passed: list[str] = []
        lang = lang or self.lang() or "en"
        user = self._user(kind, events=events, order=order, by=by, words=words, where=where)
        if kind == "captain":
            self.captain_said(words, lang)
            self.log.append((self.clock(), "the Captain (in the room)", words[:300]))
        elif kind == "order":
            self.log.append((self.clock(), f"order from the bridge ({by})", json.dumps(order, ensure_ascii=False)[:300]))
        system = system_prompt(lang)
        tools = [SAY, TRANSPORT, ENERGIZE, ABORT, LOCATE] + ([PASS] if kind == "captain" else [])
        pending: list[asyncio.Task] = []

        async def run_tool(call: ToolCall, args: dict[str, Any]) -> None:
            if call.name in LOOKUPS:
                res = await self.execute("crew_locate", {"who": str(args.get("who", ""))}, "chief")
            else:
                clean = {k: v for k, v in args.items() if v not in (None, "", [])}
                if call.name == "transport":
                    clean["by"] = "chief"
                res = await self.execute(ACTION_TOOLS[call.name], clean, "chief")
            results.append((call, res))
            rec["tools"].append(f"{call.name}({json.dumps(args, ensure_ascii=False)[:90]}) -> {'ok' if res.get('ok') else 'FAILED'}")
            rec["ok" if res.get("ok") else "failed"] += 1
            acted["n"] += 1

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            if call.name == "say":
                line = str(args.get("text", "")).strip()
                if len(line) < 2:
                    return
                said.append(line)
                rec["lines"].append(line)
                await self.say(SPEAKER, line, lang, str(args.get("tone", "calm")), priority_urgent=bool(args.get("urgent")), answer=self._answering)
            elif call.name in ACTION_TOOLS or call.name in LOOKUPS:
                pending.append(asyncio.create_task(run_tool(call, args)))
            elif call.name == "pass":
                passed.append(str(args.get("for_whom", "")))

        messages: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        try:
            comp = await models.chat(self.llm, ROLE, messages=messages, tools=tools, tool_choice="auto", on_tool_call=on_call)
            rec["cost"] += comp.cost
            if comp.error:
                rec["error"] = comp.error[:120]
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            # a second look only to read what her tools found: a refusal or a lookup (the model spoke before it knew)
            needs_read = any((not r.get("ok")) or c.name in LOOKUPS for c, r in results)
            if needs_read and not passed and not comp.error:
                notes = "\n".join(f"- {c.name}({json.dumps(c.arguments() or {}, ensure_ascii=False)}) {'ok' if r.get('ok') else 'REFUSED'}: {r.get('detail', '')}" for c, r in results)
                follow = messages + [
                    {"role": "assistant", "content": " ".join(f"[you said] {s}" for s in said) or "(nothing said yet)"},
                    {"role": "user", "content": f"[Console results]\n{notes}\nTell the Captain what the console found, straight and short, in his language: if something was refused, "
                                                "the reason and the way round (if what you said before was not true, put it right); for a lookup, what it says. Use `say`. You may call "
                                                "a tool again if there is a better way."}]
                pending2: list[asyncio.Task] = []

                async def on_call2(call: ToolCall) -> None:
                    args = call.arguments() or {}
                    if call.name == "say":
                        line = str(args.get("text", "")).strip()
                        if len(line) >= 2:
                            said.append(line)
                            rec["lines"].append(line)
                            await self.say(SPEAKER, line, lang, str(args.get("tone", "calm")), priority_urgent=bool(args.get("urgent")), answer=self._answering)
                    elif call.name in ACTION_TOOLS:
                        pending2.append(asyncio.create_task(run_tool(call, args)))

                comp2 = await models.chat(self.llm, ROLE, messages=follow, tools=[SAY, TRANSPORT, ENERGIZE, ABORT], tool_choice="auto", on_tool_call=on_call2, max_tokens=240)
                rec["cost"] += comp2.cost
                if pending2:
                    await asyncio.gather(*pending2, return_exceptions=True)
            if kind == "order":
                self.stats["orders"] += 1
                # the Chief neither acted nor spoke (a model that failed or stalled): the order stands as typed
                if (comp.error or (not said and acted["n"] == 0 and not passed)) and order is not None:
                    await self._console_alone(order, by, rec)
        except asyncio.TimeoutError:
            rec["error"] = "timeout"
            if kind == "order" and order is not None and acted["n"] == 0 and not said:
                await self._console_alone(order, by, rec)
        except asyncio.CancelledError:
            rec["error"] = "cancelled"
            if kind == "news" and events:
                self._events = list(events) + self._events                # (what was not said is read again after the Captain)
            raise
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
            self.stats["errors"] += 1
            log.exception("the Chief's turn failed")
            if kind == "order" and order is not None and acted["n"] == 0 and not said:
                await self._console_alone(order, by, rec)
        finally:
            rec["latency"] = round(time.perf_counter() - t0, 2)
            self.stats["turns"] += 1
            self.stats["actions"] += rec["ok"]
            self.stats["lines"] += len(said)
            self.stats["cost"] += rec["cost"]
            self._spent.append((self.clock(), rec["cost"]))
            self._answering = False
            for line in said:
                self.log.append((self.clock(), "you", line[:300]))
            if said and kind in ("captain", "order"):
                self.journal.talk.append((((words or (self.captain_words if kind == "order" else ""))[:200]), " ".join(said)[:240], time.strftime("%H:%M")))
            self._tally(results)
            if said or results:
                self._save()
            if self.trace is not None:
                self.trace(rec)
            log.info("the Chief (%s) %.2fs $%.5f: %s", kind, rec["latency"], rec["cost"], " | ".join(rec["tools"] + [f'say: {s}' for s in said]) or ("(passed)" if passed else "(nothing)"))
            try:
                asyncio.get_running_loop().call_soon(self.kick)
            except RuntimeError:
                pass
        return said

    def _tally(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        for call, res in results:
            if call.name == "transport":
                if res.get("ok"):
                    self.journal.record["sent"] += 1
                    if any(str(w).lower() in ("captain", "me", "the captain") for w in (call.arguments() or {}).get("who", []) or []):
                        self.journal.record["captain"] += 1
                else:
                    self.journal.record["refused"] += 1
            elif call.name == "abort" and res.get("ok"):
                self.journal.record["aborted"] += 1

    async def _console_alone(self, order: dict[str, Any], by: str, rec: dict[str, Any]) -> None:
        """The Chief could not answer (the model failed or stalled): the console carries out the order as the bridge typed it, and the bridge is told so."""
        self.stats["fallbacks"] += 1
        action = str(order.get("action") or "beam").lower()
        name = {"beam": "transport", "energize": "transport_energize", "abort": "transport_abort"}.get(action)
        if name is None:
            return
        args = {k: v for k, v in order.items() if k not in ("action", "words") and v not in (None, "", [])}
        args["by"] = by or "ops"
        res = await self.execute(name, args, by or "ops")
        rec["tools"].append(f"console alone: {name} -> {'ok' if res.get('ok') else 'FAILED'}")
        log.warning("the Chief did not answer: the console carried out the order as typed (%s)", res.get("detail", "")[:120])
        if self.relay is not None:
            try:
                await self.relay(f"transporter: the Chief did not answer on the intercom; the console carried out the bridge's order by itself — {res.get('detail', '')[:200]}")
            except Exception:  # noqa: BLE001
                log.exception("could not tell the bridge")

    # ------------------------------------------------------------------------------------------ the voice stage asks her to think again
    async def rethink(self, speaker: str, text: str, waited_s: float, cut_after: str, lang: str) -> str | None:
        """A line of hers that waited (or was cut off) is thought again with the room as it is now: what she says, or None."""
        if speaker != SPEAKER:
            return None
        cut = f" You had said only «{cut_after}» when the Captain spoke over you." if cut_after else ""
        ask = (f"[Before speaking] {waited_s:.0f} seconds ago you were about to tell the Captain: «{text}».{cut} The room has moved on (the card above is now). If it still matters, say it now as "
               "it stands, updated and short, with `say`. If it no longer matters, say nothing. A line that answers an order of the Captain's still matters: say it, updated.")
        msgs = [{"role": "system", "content": system_prompt(lang)}, {"role": "user", "content": board(self.state()) + "\n\n" + ask}]
        out: list[str] = []

        async def on_call(call: ToolCall) -> None:
            if call.name == "say":
                line = str((call.arguments() or {}).get("text") or "").strip()
                if line:
                    out.append(line)

        comp = await models.chat(self.llm, ROLE, messages=msgs, tools=[SAY], tool_choice="auto", on_tool_call=on_call, max_tokens=140)
        self.stats["cost"] += comp.cost
        return " ".join(out) if out else None

    def summary(self) -> str:
        s = self.stats
        return f"Chief Ostrander: {s['turns']} turns, {s['orders']} orders, {s['actions']} actions, {s['lines']} lines, {s['fallbacks']} console-alone, {s['errors']} errors, ${s['cost']:.5f}"
