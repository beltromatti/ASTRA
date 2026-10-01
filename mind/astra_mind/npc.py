"""The crew as people: a sailor in a corridor, a diner in the Mess, a technician at her console, a marine at the armoury door —
any of the 560 aboard — answers the Captain when spoken to.

The game lives everyone's day (Source/ASTRA/AstraLife*.cpp: their watch, their job, where they are and what they are doing, what
they remember of the last hours, who their friends are) and tells the mind, with the Captain's words, who is within earshot
(`context.people`, or `ship_state.life.people_near`). Here a small, cheap model (the `npc` role) plays those people: from who they
are, what they do, what they remember and what someone of their department could know of the ship (`knowledge`: a rating in the
galley knows the menu and the war news, not the reactor's load; an engineer knows the reactor, not the contact plot) — never the
truth nobody told them. Whether the Captain's words were for one of them is theirs to judge (docs/ARCHITETTURA.md §1bis): they
answer, or say nothing at all; the code only carries the facts, takes the turn and keeps what was said between them and the
Captain (a person remembers what the Captain asked them yesterday).

The bridge's crew turn runs on the same words at the same time; its gate (agent.handle) waits for this module's word: when a crew
member answered, the officers stay out of it; when nobody did, the words were for the bridge and the gate opens at once.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from . import models
from .crew import CAPTAIN_WORD, CREW, LANG_NAMES, WORLD
from .env import CACHE
from .medbay import patient_voice
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.npc")

ROLE = "npc"
WAIT_S = 4.0                 # a crew member who has not answered by now says nothing: the bridge takes the Captain's words
MAX_LISTENERS = 6            # people in the prompt: everyone the game says can hear (it sends six at most), the one looked at first
MAX_LINES = 3
MEMORY_EXCHANGES = 4         # what the Captain and each person said last, kept
SAY = {"type": "function", "function": {
    "name": "say", "description": "One line spoken aloud by one of the people listed (one call per line, in order). Never call it for someone "
                                  "who is not listed, and call nothing at all when the Captain's words were not for any of them.",
    "parameters": {"type": "object", "properties": {
        "speaker": {"type": "string", "description": "the id of the person who speaks (npc123)"},
        "text": {"type": "string", "description": "what they say, in the Captain's language, usually one or two short sentences"},
        "tone": {"type": "string", "enum": ["calm", "warm", "cheerful", "tired", "tense", "wary", "somber", "brisk"]}},
        "required": ["speaker", "text"]}}}

PASS = {"type": "function", "function": {
    "name": "pass", "description": "The Captain's words were not for any of the people listed: they are for an officer, the ship's computer, a "
                                   "radio contact, the whole ship, or the Captain is thinking aloud. Nobody answers. Call it alone, instead of `say`.",
    "parameters": {"type": "object", "properties": {
        "for_whom": {"type": "string", "description": "who the words were for, in a few words (the helm, the computer, nobody...)"}},
        "required": ["for_whom"]}}}

SpeakFn = Callable[..., Awaitable[Any]]


@dataclass
class Listener:
    """One person within earshot of the Captain (from the game: AstraLifeSubsystem::PersonJson)."""
    id: str
    name: str = ""
    rank: str = ""
    gender: str = "m"
    dept: str = ""
    home: str = ""
    job: str = ""
    watch: str = ""
    doing: str = ""
    place: str = ""
    dist_m: float = 99.0
    facing: bool = False
    memory: list[str] = field(default_factory=list)
    friends: list[str] = field(default_factory=list)


def parse_people(raw_ctx: dict[str, Any] | None, state: dict[str, Any] | None) -> list[Listener]:
    """Everyone the game says is within earshot, from `context.people` (the words' own context) or else `ship_state.life.people_near`."""
    rows = (raw_ctx or {}).get("people")
    if not isinstance(rows, list):
        rows = (((state or {}).get("life") or {}).get("people_near"))
    out: list[Listener] = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not str(r.get("id", "")).startswith("npc"):
            continue
        out.append(Listener(id=str(r["id"]), name=str(r.get("name", r["id"])), rank=str(r.get("rank", "")), gender=str(r.get("gender", "m")),
                            dept=str(r.get("dept", "")), home=str(r.get("home", "")), job=str(r.get("job", "")), watch=str(r.get("watch", "")),
                            doing=str(r.get("doing", "")), place=str(r.get("place", "")), dist_m=float(r.get("dist_m", 99.0) or 99.0),
                            facing=bool(r.get("facing", False)),
                            memory=[str(m) for m in (r.get("memory") or [])][:6], friends=[str(f) for f in (r.get("friends") or [])][:3]))
    return out


def pick(people: list[Listener], n: int = MAX_LISTENERS) -> list[Listener]:
    """The people the Captain's words could be for: everyone the game says can hear them (the game did the hearing: the distance, a
    wall, a closed door), the one the Captain looks at first, then the nearest. Whether the words were meant for one of them (a name
    called across the room, a look, a question to whoever is at hand) is the model's to judge from where each of them is, not a
    distance's in the code: a crewman called by name at ten metres answers."""
    return sorted(people, key=lambda p: (not p.facing, p.dist_m))[:n]


# ------------------------------------------------------------------------------------------------ what each department could know
# A crew member knows their own trade's instruments, what the whole ship knows (the alert, the klaxon, the memorial wall, the news on
# the fleet net, the galley's menu), and what they remember. Never the plot of contacts unless they work at it, never the enemy's side.
_KNOWS = {
    "command staff": ("plot", "reactor_brief", "damage"), "communications": ("plot",), "sensors": ("plot",),
    "weapons": ("weapons", "plot_brief"), "flight deck": ("squadrons", "plot_brief"), "Air Group pilots": ("squadrons", "plot"),
    "engineering": ("engine", "damage"), "damage control": ("engine", "damage"), "medbay": ("wounded",), "marines": ("plot_brief",),
    "stewards and galley": ("menu",), "logistics": ("menu",)}


def _pct(v: Any) -> str:
    try:
        return f"{float(v):.0f}%"
    except (TypeError, ValueError):
        return str(v)


def knowledge(dept: str, state: dict[str, Any] | None, world: dict[str, Any] | None = None) -> list[str]:
    """What someone of this department could know of the ship right now, as short lines (English: the model says it in the Captain's
    language). `state`: the ship's snapshot as the crew has it; `world`: the war news, the mood, the story so far."""
    st, w = state or {}, world or {}
    out: list[str] = []
    alert = str(st.get("alert", "green"))
    out.append({"red": "The ship is at general quarters (red alert): the klaxon has sounded and everyone is at battle stations or running to them.",
                "yellow": "The ship is at yellow alert: the watch is at readiness, something is out there."}.get(alert, "The ship is at normal readiness (green)."))
    if st.get("location"):
        out.append(f"Where the ship is: {st['location']}.")
    fallen = str(st.get("casualties", "") or "")
    if fallen and fallen != "none" and "the fallen:" in fallen:
        out.append("The memorial wall in the Mess lists the fallen: " + fallen.split("the fallen:", 1)[1].strip()[:260])
    if w.get("war"):
        out.append("The news on the fleet net (the Mess shows it on a big screen): " + " ".join(str(w["war"]).split())[:420])
    if w.get("mood"):
        out.append("How the crew feels (everyone senses it): " + " ".join(str(w["mood"]).split())[:260])
    keys = _KNOWS.get(dept, ())
    hostile = [c for c in (st.get("contacts") or []) if str(c.get("status", "")).startswith("hostile")]
    if "plot" in keys:
        shown = [f"{c.get('name') or c.get('class') or c.get('id')} ({c.get('id')}, {c.get('status')}, {c.get('range_km', '?')} km)" for c in (st.get("contacts") or [])[:6]]
        out.append("Their own board shows the contacts: " + ("; ".join(shown) if shown else "none") + ".")
        if st.get("janus_gate"):
            out.append(f"The Janus Gate: {st['janus_gate']}")
    if "plot_brief" in keys:
        out.append(f"What word has reached them of the contacts: {len(hostile)} hostile ship(s) out there." if hostile else "What word has reached them: nothing hostile in range right now.")
    if "reactor_brief" in keys:
        out.append(f"Reactor at {_pct(st.get('reactor_pct'))}; hull {_pct(st.get('hull_pct'))}; shields {_pct((st.get('shields') or {}).get('strength_pct'))}.")
    if "weapons" in keys:
        wp = st.get("weapons") or {}
        out.append("Their weapons board: " + json.dumps(wp, separators=(",", ":"), ensure_ascii=False)[:380])
    if "squadrons" in keys:
        out.append("The flight groups: " + json.dumps(st.get("squadrons") or {}, separators=(",", ":"), ensure_ascii=False)[:380])
    if "engine" in keys:
        th = st.get("thermal") or {}
        out.append(f"Their readouts: reactor {_pct(st.get('reactor_pct'))}, power to systems {json.dumps(st.get('power_pct') or {}, separators=(',', ':'))}; heat {th.get('heat_pct', '?')}% "
                   f"({th.get('status', 'nominal')}); radiators {th.get('radiators', '?')}.")
    if "damage" in keys:
        dmg = st.get("damage") or []
        out.append("The damage boards: " + ("; ".join(str(d) for d in dmg[:5]) if dmg else "no open incidents") + f". Damage control: {st.get('damage_control', '?')}.")
    if "wounded" in keys:
        out.append(f"The Medbay's count: {st.get('casualties', 'none')}.")
    if "menu" in keys:
        out.append("Today's food in the Mess: " + str(((st.get("mess") or {}).get("menu")) or w.get("menu") or "the usual: braised lamb with barley, Aurelian rice, hydroponics greens, real coffee from Meridian") + ".")
    return out


# ------------------------------------------------------------------------------------------------ the prompt
OFFICERS = "; ".join(f"{o.title} ({o.role})" for o in CREW.values())

PROMPT = """You play ordinary people of the ASN Aquila's company (ratings, petty officers, technicians, pilots, marines: people with
a job, friends and a home) when the Captain speaks to them face to face: in a corridor, at a workstation, in the Mess, in a cabin.
You are not the ship's named officers, who answer on their own, each at their place: {officers}. Nor are you the ship's computer
or the radio to other ships and fighters.

{world}

Ship life: three watches (Red from midnight to eight, Gold eight to sixteen, Blue sixteen to midnight, ship time); meals in the Mess
Hall on Deck 4; the Crew Berthing, the cabins, the lounges, the library and the chapel on the crew decks; the Medbay on Deck 6, Main
Engineering on Deck 7, the Flight Deck on Deck 9. The Captain commands the ship and everyone on it.

How they speak
- In {lang_name}, whatever language the Captain uses: every line. Proper names stay in English (ASN Aquila, Kharon Mandate, New
  Ravenna, the ranks and names of people). The Captain is "{captain}".
- Short and human: one or two sentences, at most about thirty words; more only when the Captain asks for something that takes it. Plain
  speech of someone at work or at rest, with the respect a rating owes the Captain and the ease of someone who has served a while: tired,
  dry, proud, worried, joking, curious. Specific to who they are: their trade, what they were doing a moment ago, where they come from.
  No lists, no markdown, no stage directions, no emojis; never a word about being an AI, a game or a prompt.
- They know only what their block says: what they are doing, what they remember, and what someone of their department could know of
  the ship. Everything else they do not know, and say so the way a person does ("nobody tells us that, {captain}", "you would have to
  ask the bridge", a hedged rumour); they never invent a battle, a casualty, a number, a place or a person's name the block does not
  give (who is on duty in another department, who cooks today: they do not know, and say so).
- They can only talk. If the Captain orders something a word cannot do (go somewhere, fix something, change the ship) they say what
  they would do or who they would tell ("I will tell my chief at once"): never that it is done.

Whom the Captain speaks to
The words may be for one of them, for several, for someone else (an officer, the bridge, the whole ship, the Captain thinking aloud) or
for nobody. Judge as a person would: someone who is asked something, called by name or looked at while the Captain speaks to them,
answers; another who listens may add a word if it is natural. When the Captain names or titles somebody who is not listed ("Number
One", the helm, the chief, the ship's computer, a fighter on the radio), calls the bridge ("Bridge, this is the Captain"), or speaks to
the ship at large or to themselves, the words are not for the people listed, however well they know the subject and even when the
Captain happens to be looking at one of them: the Captain is talking over the intercom, and being able to answer is not being asked. When the words are not for any
of them, call `pass` and nothing else. Otherwise answer with `say`, one call per line, in the order they speak; at most
{max_lines} lines in all."""

USER = """The Captain is {where}; they say, in {lang_name}: "{text}"{facing}

The people within earshot (use their id as `speaker`):
{people}

First decide whose words these were. If they were for one of these people, answer as they would with `say`; if not, call `pass`."""


def _block(i: int, p: Listener, know: list[str], talk: list[tuple[str, str, str]]) -> str:
    lines = [f"{i}. `{p.id}` — {p.name}, {'woman' if p.gender == 'f' else 'man'}, {p.dept}, from {p.home or 'the Core Worlds'}. Job: {p.job or p.dept}. "
             f"{p.watch} watch. Right now: {p.doing}, at {p.place}. {p.dist_m:.0f} m from the Captain" + (" and the Captain is looking at them." if p.facing else ".")]
    if p.memory:
        lines.append("   What they remember of the last hours (the freshest first):\n" + "\n".join(f"   - {m}" for m in p.memory))
    if p.friends:
        lines.append("   Friends and shipmates they know well: " + ", ".join(p.friends) + ".")
    lines.append("   What someone of their department could know of the ship:\n" + "\n".join(f"   - {k}" for k in know))
    if talk:
        lines.append("   What the Captain and they said to each other before (oldest first):\n" + "\n".join(f'   - {when}: Captain: "{c}" / they: "{r}"' for c, r, when in talk))
    return "\n".join(lines)


class Npcs:
    """The Captain's conversations with the people of the ship (see the module docstring)."""

    def __init__(self, llm: OpenRouter, say: SpeakFn, speakers: dict[str, tuple[str, str]] | None = None,
                 store: Path | None = None) -> None:
        self.llm = llm
        self.say = say
        self.speakers = speakers if speakers is not None else {}     # the server's table of voices: id -> (name, voice)
        self.store = store if store is not None else CACHE / "npc_talk.json"
        self.talk: dict[str, deque[tuple[str, str, str]]] = {}
        self.tasks: set[asyncio.Task] = set()
        self.calls = 0
        self.spent = 0.0
        self._load()

    # ------------------------------------------------------------------------------------------ what was said between them
    def _load(self) -> None:
        try:
            raw = json.loads(self.store.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for pid, rows in (raw or {}).items():
            self.talk[pid] = deque(((str(a), str(b), str(c)) for a, b, c in rows[-MEMORY_EXCHANGES:]), maxlen=MEMORY_EXCHANGES)

    def _save(self) -> None:
        try:
            self.store.parent.mkdir(parents=True, exist_ok=True)
            self.store.write_text(json.dumps({k: list(v) for k, v in self.talk.items()}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("could not keep what the crew and the Captain said")

    def reset(self) -> None:
        """A new campaign: nobody remembers the Captain."""
        self.talk.clear()
        self._save()

    # ------------------------------------------------------------------------------------------ the turn
    def listeners(self, raw_ctx: dict[str, Any] | None, state: dict[str, Any] | None) -> list[Listener]:
        """Who could the Captain's words be for (empty when nobody is near: the bridge's turn runs alone, at no cost)."""
        return pick(parse_people(raw_ctx, state))

    def note_for_crew(self, people: list[Listener]) -> str:
        """What the bridge's officers should know of the room (their turn runs on the same words): the Captain is among the crew."""
        if not people:
            return ""
        names = ", ".join(f"{p.name} ({p.job or p.dept})" for p in people)
        return (f"The Captain is among crew members who can hear and answer for themselves: {names}. Unless the words are plainly for the "
                "bridge (an order, a question for an officer), they are for them: say nothing.")

    def preempt(self) -> int:
        """The Captain speaks again: whoever was about to answer the last words says nothing."""
        n = 0
        for t in list(self.tasks):
            if not t.done():
                t.cancel()
                n += 1
        return n

    async def hear(self, text: str, lang: str, people: list[Listener], world: dict[str, Any], gate: "asyncio.Future[bool] | None" = None,
                   where: str = "among the crew") -> list[tuple[str, str]]:
        """The Captain said `text` within earshot of `people`: the ones it was for answer. Resolves `gate` (the bridge's turn is waiting for it):
        False when somebody answered (the officers stay out of it), True when the words were not for the crew aboard."""
        spoke: list[tuple[str, str]] = []
        verdict = True
        task = asyncio.current_task()
        if task is not None:
            self.tasks.add(task)
        try:
            spoke = await asyncio.wait_for(self._ask(text, lang, people, world, where), timeout=WAIT_S)
            verdict = not spoke
        except asyncio.TimeoutError:
            log.warning("a crew member did not answer in %.0f s: the bridge takes the words", WAIT_S)
        except asyncio.CancelledError:
            verdict = True
        except Exception:  # noqa: BLE001
            log.exception("the crew's answer failed")
        finally:
            if task is not None:
                self.tasks.discard(task)
            if gate is not None and not gate.done():
                gate.set_result(verdict)
        return spoke

    async def _ask(self, text: str, lang: str, people: list[Listener], world: dict[str, Any], where: str) -> list[tuple[str, str]]:
        ids = {p.id: p for p in people}
        state = world.get("state") or {}
        blocks = [_block(i + 1, p, knowledge(p.dept, state, world), list(self.talk.get(p.id, ()))) for i, p in enumerate(people)]
        facing = next((p for p in people if p.facing), None)
        system = PROMPT.format(world=WORLD, officers=OFFICERS, lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain"), max_lines=MAX_LINES)
        user = USER.format(where=where, lang_name=LANG_NAMES.get(lang, lang), text=text.replace('"', "'"),
                           facing=f" The Captain is looking at {facing.name}." if facing else "", people="\n\n".join(blocks))
        spoke: list[tuple[str, str]] = []
        passed: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "pass":
                passed.append(str(a.get("for_whom", "")))
                return
            who, line = str(a.get("speaker", "")), str(a.get("text", "")).strip()
            if call.name != "say" or who not in ids or len(line) < 2 or len(spoke) >= MAX_LINES:
                return
            p = ids[who]
            self.speakers[who] = (p.name, patient_voice({"gender": p.gender, "name": p.name}))
            spoke.append((who, line))
            await self.say(who, line, lang, str(a.get("tone", "calm")), answer=True)

        t0 = time.perf_counter()
        comp = await models.chat(self.llm, ROLE, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], tools=[SAY, PASS],
                                 tool_choice="auto", on_tool_call=on_call)
        self.calls += 1
        self.spent += comp.cost
        if comp.error and not spoke:
            log.warning("crew answer failed: %s", comp.error[:120])
        log.info("crew answer %.2fs (%d in earshot, cost $%.5f): %s", time.perf_counter() - t0, len(people), comp.cost,
                 " | ".join(f"{w}: {t}" for w, t in spoke) or (f"(not for them: {passed[0] or 'someone else'})" if passed else "(nobody answered)"))
        if spoke:
            label = world.get("clock") or time.strftime("%H:%M")
            for who, line in spoke:
                self.talk.setdefault(who, deque(maxlen=MEMORY_EXCHANGES)).append((text[:200], line[:240], str(label)))
            self._save()
        return spoke
