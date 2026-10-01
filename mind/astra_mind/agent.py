"""The bridge crew agent: one model call per Captain's utterance, streamed; each `speak` goes to the voice queue and
each ship tool goes to the simulation the moment its arguments are complete. Failed actions trigger a short
follow-up so the responsible officer reports what went wrong (closed loop: the ship state is the truth).

v2 (docs/contratto_postazioni.md): with live consoles the officers set persistent modes (`station`) instead of repeating
orders, keep them alive on their own within their delegation (events and the initiative watch, `handle_event`), and
speak briefly and to the point. The Captain has priority over everything: `preempt()` drops whatever the crew was
in the middle of when the Captain speaks. A game build without consoles keeps the legacy tools (tools.tools_for)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from . import context as context_model
from . import models
from . import stations as station_model
from .crew import CREW, system_prompt
from .openrouter import Completion, OpenRouter, ToolCall
from .tools import DEPT_TOOLS, LOOKUPS, SHIP_TOOL_NAMES, SPEAK, initiative_names, owner_of, tools_for

log = logging.getLogger("astra.agent")


class ShipLink(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def recent_events(self) -> list[str]: ...
    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]: ...


SayFn = Callable[[str, str, str, str], Awaitable[None]]   # (speaker, text, lang, tone)


@dataclass(eq=False)
class Turn:
    text: str
    lang: str
    kind: str = "captain"                 # captain | event
    lines: list[tuple[str, str]] = field(default_factory=list)
    actions: list[tuple[str, dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    t_first_line: float | None = None
    t_end: float = 0.0
    cost: float = 0.0
    error: str = ""
    cancelled: bool = False               # the Captain spoke over it (or the words were for someone else): no more is said or done
    task: asyncio.Task | None = None      # the model call in flight (what preempt() cancels)


class BridgeAgent:
    def __init__(self, llm: OpenRouter, ship: ShipLink, say: SayFn, history_turns: int = 10) -> None:
        self.llm = llm
        self.ship = ship
        self.say = say
        self.history: list[dict[str, str]] = []
        self.history_turns = history_turns
        self.spent = 0.0
        self._ev = 0                     # ids for event-report tool calls in the history
        self.campaign = lambda: []       # the war director's log (set by the server)
        self.war = lambda: ""            # the sector as the fleet knows it (set by the server)
        self.mood = lambda: ""           # how the crew feels (the director's word, set by the server)
        self.bonds = lambda: ""          # how each officer stands with the Captain (the director's, set by the server)
        self.standing: list[dict[str, str]] = []   # the Captain's standing orders (the director saves them with the story)
        self.style: Callable[[], str] = lambda: ""   # the XO's read of how the Captain commands (style.py)
        self.home: Callable[[], str] = lambda: ""    # the officers' own lives: news from home (the director)
        self.memories = lambda: ""       # what each officer remembers of the Captain (memory.py, set by the server)
        self.titles = {k: v.title for k, v in CREW.items()}
        self._active: set[Turn] = set()  # turns being worked on (what preempt() reaches)

    # ------------------------------------------------------------------------------------------------ priority
    def preempt(self) -> int:
        """The Captain speaks: whatever the crew was doing stops now — the model calls in flight are dropped and nothing more is
        voiced for those turns (what was already sent to the ship stays done). Returns how many turns were cut off."""
        n = 0
        for turn in list(self._active):
            turn.cancelled = True
            if turn.task and not turn.task.done():
                turn.task.cancel()
            n += 1
        return n

    def busy(self) -> bool:
        return bool(self._active)

    # ------------------------------------------------------------------------------------------------ prompts
    def _trim_history(self) -> None:
        """Keep the last `history_turns` of the Captain's turns (a turn starts at a user message), and of the crew's own (reports,
        watch checks, chatter: at most the last six since then) — a fight full of checks must not push the Captain's orders out."""
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        captain = [i for i in starts if str(self.history[i].get("content", "")).startswith("Captain:")]
        if len(starts) <= self.history_turns and len(captain) <= self.history_turns:
            return
        first = captain[-self.history_turns] if len(captain) > self.history_turns else (captain[0] if captain else starts[0])
        keep = [i for i in starts if i >= first]
        events = [i for i in keep if i not in captain]
        drop_events = set(events[:-6]) if len(events) > 6 else set()
        ends = {s: (starts[k + 1] if k + 1 < len(starts) else len(self.history)) for k, s in enumerate(starts)}
        kept: list[dict[str, Any]] = []
        for i in keep:
            if i not in drop_events:
                kept += self.history[i:ends[i]]
        self.history = kept

    def _last_turns(self, n: int) -> list[dict[str, Any]]:
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        return self.history[starts[-n]:] if len(starts) > n else list(self.history)

    def _system(self, lang: str, state: dict[str, Any], ctx: context_model.Context | None = None) -> dict[str, str]:
        hearing = context_model.describe(ctx, self.titles) if ctx else ""
        return {"role": "system", "content": system_prompt(lang, state, self.ship.recent_events(), self.campaign(), self.war(),
                                                          self.mood(), self.bonds(), self.standing_lines(), self.memories(),
                                                          self.style(), self.home(), hearing)}

    def _messages(self, text: str, lang: str, state: dict[str, Any], ctx: context_model.Context | None = None,
                  note: str = "") -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = [self._system(lang, state, ctx)]
        msgs += self.history
        msgs.append({"role": "user", "content": f"Captain: {text}" + (f"\n[{note}]" if note else "")})
        return msgs

    def standing_lines(self) -> str:
        return "\n".join(f"- {o['department']}: {o['order']}" for o in self.standing)

    async def warm_up(self, lang: str) -> float:
        """The first crew turn of a session should not pay for a cold connection and a cold prompt cache: one request goes out
        while the game is still starting, with the crew's own tools and system prompt, asking for a single token. Nothing is
        said, done or remembered. Returns the seconds it took."""
        t0 = time.perf_counter()
        state = self.ship.snapshot()
        msgs = [self._system(lang, state), {"role": "user", "content": "[the bridge is manned: stand by]"}]
        await models.chat(self.llm, "crew", messages=msgs, tools=tools_for(state).tools, max_tokens=1, retry=False, first_token_s=20.0)
        return time.perf_counter() - t0

    async def _standing_order(self, args: dict[str, Any]) -> dict[str, Any]:
        """The Captain's orders that last: recorded, or withdrawn (a department's, or all of them)."""
        dept, order = str(args.get("department", "")).lower(), str(args.get("order", "")).strip()
        if args.get("action") == "cancel":
            before = len(self.standing)
            self.standing[:] = [o for o in self.standing if dept not in ("all", o["department"])]
            log.info("standing orders cancelled (%s): %d left", dept, len(self.standing))
            return {"ok": True, "detail": f"{before - len(self.standing)} standing order(s) withdrawn"}
        if dept not in DEPT_TOOLS or not order:
            return {"ok": False, "detail": "a standing order needs a department and the order"}
        self.standing[:] = [o for o in self.standing if o["department"] != dept or o["order"].lower() != order.lower()][-11:]
        self.standing.append({"department": dept, "order": order[:300]})
        log.info("standing order for %s: %s", dept, order)
        return {"ok": True, "detail": f"standing order recorded for {dept}"}

    def initiative(self) -> set[str]:
        """What the crew may do by itself at an event: the usual (damage control, shields, point defence, radiators) and
        whatever the standing orders put in a department's hands; with live consoles, `station` (each call is then checked)."""
        return initiative_names(self.ship.snapshot(), self.standing)

    # ------------------------------------------------------------------------------------------------ the turns
    async def handle(self, text: str, lang: str, ctx: context_model.Context | None = None, note: str = "",
                     gate: "asyncio.Future[bool] | None" = None) -> Turn:
        """The Captain's words. `gate`: a future the router resolves — while it is open nothing is said or done (the model
        is already working on the words); False drops the turn (the words were for someone else)."""
        turn = Turn(text=text, lang=lang, kind="captain")
        t0 = time.perf_counter()
        state = self.ship.snapshot()
        ts = tools_for(state)
        pending: list[tuple[ToolCall, asyncio.Task]] = []
        fired: list[ToolCall] = []
        on_call = self._on_call(turn, lang, t0, pending, ts, state, fired, captain=True, gate=gate)
        msgs = self._messages(text, lang, state, ctx, note)
        user = f"Captain: {text}"
        self._active.add(turn)
        try:
            comp = await self._llm(turn, "crew", msgs, ts.tools, on_call)
            if gate is not None and not gate.done() and not turn.cancelled:
                await asyncio.shield(gate)                           # nothing is voiced before the router has said whom it is for
            if gate is not None and gate.done() and not gate.result():
                turn.cancelled = True                                # the words were for someone else: no trace in the crew's talk
                await self._settle(pending, turn)
                turn.t_end = time.perf_counter() - t0
                return turn
            if turn.cancelled:
                await self._finish_interrupted(user, fired, pending, turn)
                turn.t_end = time.perf_counter() - t0
                return turn
            turn.cost += comp.cost
            log.info("llm: provider=%s finish=%s calls=%s content=%r error=%s", comp.provider, comp.finish_reason,
                     [(c.name, c.arguments_raw[:120]) for c in comp.tool_calls], comp.content[:200], comp.error)
            if not comp.error and not turn.lines and not pending and not turn.cancelled and comp.content.strip():
                # the model wrote instead of speaking (silence alone is a choice: the words may have been for someone on the
                # channel): the officers are asked for their answer, with speak — what they wrote is shown back as their notes,
                # never voiced as it is
                log.warning("wrote instead of speaking (%r): asking for the answer", comp.content[:200])
                await self._speak_now(msgs, turn, lang, ts, draft=comp.content)
            if comp.error:
                turn.error = comp.error
                log.error("LLM error: %s", comp.error)
                await self.say("xo", _fallback_line(lang), lang, "calm")
            results = await self._collect(pending, turn)
            main_lines = len(turn.lines)
            failures = [a for a in turn.actions if not a[2].get("ok", False)]
            looked_up = any(n in LOOKUPS for n, _, _ in turn.actions)
            if not turn.cancelled:
                if turn.actions and not comp.error and (not turn.lines or looked_up):
                    await self._follow_up(turn, msgs, lang, readback=True)      # orders carried out in silence, or a file read: say what
                elif failures:
                    await self._follow_up(turn, msgs, lang, readback=False)
            self._record(user, comp.tool_calls, results, turn, main_lines)
            turn.t_end = time.perf_counter() - t0
            self.spent += turn.cost
            return turn
        finally:
            self._active.discard(turn)

    async def handle_event(self, event: str, lang: str, ask: str | None = None, *, role: str = "crew", system: str | None = None,
                           history_turns: int | None = None, speak_only: bool = False) -> Turn:
        """A ship event (not the Captain): the responsible officer reports it, and may act within their own authority.
        role: the model role ('crew', or 'watch' for the initiative watch); system: a prompt of its own (the watch's compact one)."""
        turn = Turn(text=f"[event] {event}", lang=lang, kind="event")
        t0 = time.perf_counter()
        state = self.ship.snapshot()
        ts = tools_for(state)
        allowed = set() if speak_only else self.initiative()         # (chatter only talks)
        pending: list[tuple[ToolCall, asyncio.Task]] = []
        fired: list[ToolCall] = []
        user = f"[Ship systems event, not the Captain speaking] {event}"
        hist = self.history if history_turns is None else self._last_turns(history_turns)
        sysmsg = {"role": "system", "content": system} if system else self._system(lang, state)
        msgs: list[dict[str, Any]] = [sysmsg] + hist
        msgs.append({"role": "user", "content": user + "\n" + (ask or EVENT_ASK) + (STANDING_ASK if self.standing else "")})
        on_call = self._on_call(turn, lang, t0, pending, ts, state, fired, captain=False, allowed=allowed)
        tools = [t for t in ts.tools if t["function"]["name"] in (allowed | {"speak"})]
        self._active.add(turn)
        try:
            comp = await self._llm(turn, role, msgs, tools, on_call, **({"max_tokens": 360} if role == "crew" else {}))   # (the other roles carry their own)
            if turn.cancelled:
                await self._finish_interrupted(user, fired, pending, turn)
                turn.t_end = time.perf_counter() - t0
                return turn
            turn.cost += comp.cost
            if not turn.lines and comp.content.strip():
                log.info("event turn: no speak call (content not voiced): %s", comp.content[:160])
            results = await self._collect(pending, turn)
            main_lines = len(turn.lines)
            if turn.actions and not turn.lines and not comp.error and not turn.cancelled:
                await self._follow_up(turn, msgs, lang, readback=True)   # acted on initiative in silence: say so
            if turn.lines or turn.actions:
                self._record(user, comp.tool_calls, results, turn, main_lines)
            turn.t_end = time.perf_counter() - t0
            self.spent += turn.cost
            return turn
        finally:
            self._active.discard(turn)

    async def rethink(self, speaker: str, text: str, waited_s: float, cut_after: str, lang: str) -> str | None:
        """An officer thinks again about a line that waited (or was cut off) before it is said: what they say now, or None. The
        speech floor calls it when the line's turn comes (docs/ARCHITETTURA.md §1bis: the agents re-think, the code does not
        drop or shorten what they say)."""
        state = self.ship.snapshot()
        who = self.titles.get(speaker, speaker)
        cut = f" They had said only «{cut_after}» when the Captain spoke over them." if cut_after else ""
        ask = (f"[Before speaking] {waited_s:.0f} seconds ago {who} was about to tell the Captain: «{text}».{cut} The ship has moved on "
               "since (the state above is now). If it still matters to the Captain, they say it now as it stands — updated, short, "
               "in character — with speak. If it no longer matters, they say nothing: do not call speak.")
        msgs = [self._system(lang, state)] + self._last_turns(4) + [{"role": "user", "content": ask}]
        said: list[str] = []

        async def on_call(call: ToolCall) -> None:
            if call.name == "speak":
                line = str((call.arguments() or {}).get("text") or "").strip()
                if line:
                    said.append(line)

        comp = await models.chat(self.llm, "crew", messages=msgs, tools=[SPEAK], tool_choice="auto", on_tool_call=on_call, max_tokens=160)
        self.spent += comp.cost
        return " ".join(said) if said else None

    # ------------------------------------------------------------------------------------------------ internals
    async def _llm(self, turn: Turn, role: str, msgs: list[dict[str, Any]], tools: list[dict[str, Any]], on_call: Any,
                   **kw: Any) -> Completion:
        """One model call for the turn, as a task the Captain can cancel (preempt). A cancelled call returns an empty
        completion (the turn is marked cancelled); a real cancellation of the caller propagates."""
        if turn.cancelled:
            return Completion()
        task = asyncio.ensure_future(models.chat(self.llm, role, messages=msgs, tools=tools, tool_choice="auto",
                                                 on_tool_call=on_call, **kw))
        turn.task = task
        try:
            return await task
        except asyncio.CancelledError:
            me = asyncio.current_task()
            if turn.cancelled and not (me is not None and me.cancelling()):
                return Completion()
            raise
        finally:
            turn.task = None

    async def _finish_interrupted(self, user: str, fired: list[ToolCall], pending: list, turn: Turn) -> None:
        """The turn was cut off by the Captain: what was already sent to the ship finishes and goes into the history (the next
        turn must know the ship changed); what the crew had begun to say does not (nobody heard it)."""
        results = await self._settle(pending, turn)
        acts = [c for c in fired if c.name != "speak"]
        if acts or turn.kind == "captain":
            self._record(user, acts, results, turn, 0)          # (the Captain's words stay in the talk even if nobody answered yet)
        log.info("turn interrupted by the Captain: %d call(s) had gone out", len(acts))

    def _on_call(self, turn: Turn, lang: str, t0: float, pending: list, ts: Any, state: dict[str, Any], fired: list[ToolCall],
                 captain: bool, allowed: set[str] | None = None, gate: "asyncio.Future[bool] | None" = None):
        standing_for = {o["department"] for o in self.standing}

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            fired.append(call)
            if gate is not None and not gate.done():
                await asyncio.shield(gate)                           # the router has not said yet whom the words are for
            if turn.cancelled or (gate is not None and gate.done() and not gate.result()):
                return
            if call.name == "speak":
                speaker = args.get("speaker", "xo")
                st_ = self.ship.snapshot()
                if speaker not in CREW and speaker not in _patients(st_) and speaker not in _diners(st_):
                    speaker = "doctor" if str(speaker).startswith("patient") else "xo"   # (a voice must belong to someone aboard)
                line = (args.get("text") or "").strip()
                if not line:
                    return
                await self._voice(turn, t0, speaker, line, lang, args.get("tone", "calm"))
            elif call.name == "standing_order" and captain:
                pending.append((call, asyncio.create_task(self._standing_order(args))))     # the mind's own, not the ship's
            elif call.name == "station" and (captain or (allowed is not None and "station" in allowed)):
                pending.append((call, asyncio.create_task(self._station(args, ts, state, captain, standing_for))))
            elif call.name in ts.names and (captain or (allowed is not None and call.name in allowed)) and call.name in SHIP_TOOL_NAMES:
                pending.append((call, asyncio.create_task(_safe_execute(self.ship, call.name, args, owner_of(call.name, args)))))
            else:
                log.warning("tool %s not allowed here", call.name)
                pending.append((call, asyncio.create_task(_refuse(f"{call.name} is not for an officer to do on their own"))))
        return on_call

    async def _voice(self, turn: Turn, t0: float, speaker: str, line: str, lang: str, tone: str) -> None:
        if turn.t_first_line is None:
            turn.t_first_line = time.perf_counter() - t0
        turn.lines.append((speaker, line))
        await self.say(speaker, line, lang, tone)

    async def _station(self, args: dict[str, Any], ts: Any, state: dict[str, Any], captain: bool, standing_for: set[str]) -> dict[str, Any]:
        """A `station` call: checked (the mode exists, its parameters make sense, an officer on their own initiative has the
        delegation and the authority), then sent to the ship as the console's own command."""
        cmd, err = station_model.normalize(args, ts.available)
        if cmd is None:
            return {"ok": False, "detail": err}
        if not captain:
            ok, why = station_model.may_on_initiative(cmd, station_model.delegation_of(state, cmd["station"]), standing_for)
            if not ok:
                return {"ok": False, "detail": why}
        # to the game in its own words: the aspect, the game's mode name, and who decided (the console log and the board show it)
        wire = station_model.to_wire(cmd, by="captain" if captain else "officer")
        return await _safe_execute(self.ship, "station", wire, owner_of("station", cmd))

    async def _collect(self, pending: list, turn: Turn) -> dict[int, dict[str, Any]]:
        """Results of the actions (the simulation is the truth)."""
        results: dict[int, dict[str, Any]] = {}
        for call, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=3.0)
            except asyncio.TimeoutError:
                res = {"ok": False, "detail": "no response from ship systems"}
            except asyncio.CancelledError:
                res = {"ok": False, "detail": "cancelled"}
            turn.actions.append((call.name, call.arguments() or {}, res))
            results[id(call)] = res
        return results

    async def _settle(self, pending: list, turn: Turn) -> dict[int, dict[str, Any]]:
        """A turn that was cut off: let what was already sent to the ship finish, and keep its results."""
        results: dict[int, dict[str, Any]] = {}
        for call, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                res = {"ok": False, "detail": "no response from ship systems"}
            turn.actions.append((call.name, call.arguments() or {}, res))
            results[id(call)] = res
        return results

    async def _speak_now(self, msgs, turn: Turn, lang: str, ts: Any, draft: str = "") -> None:
        """The model wrote instead of speaking: the officers are asked for their answer, spoken (what they wrote is shown back to
        them as their own notes), or for silence when the words were not for them."""
        follow = list(msgs)
        if draft.strip():
            follow.append({"role": "assistant", "content": draft.strip()})
        follow.append({"role": "user", "content": f"[What you wrote was not said aloud. If the Captain's words were for the bridge, the "
                                                  f"officer concerned answers now, in {lang}, in character, with speak; if they were not "
                                                  "for you, say nothing.]"})
        t0 = time.perf_counter()
        comp = await self._llm(turn, "crew", follow, [SPEAK], self._on_call(turn, lang, t0, [], ts, {}, [], captain=True),
                               max_tokens=200)
        turn.cost += comp.cost

    async def _follow_up(self, turn: Turn, msgs, lang: str, readback: bool) -> None:
        notes = "\n".join(f"- {n}({json.dumps(a, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"
                          for n, a, r in turn.actions if readback or not r.get("ok", False))
        lookup = readback and any(n in LOOKUPS for n, _, _ in turn.actions)
        ask = ("The officer who looked it up now reports to the Captain what the personnel file and the locator say about the people "
               "asked for: a report ABOUT them, in the third person (they are other members of the crew, not the officer speaking), "
               "who they are, where they are and what they are doing, in one or two short lines; nothing the file does not say. Then, "
               "one short line each, any other officer who acted says what was done." if lookup else
               "The officers who acted now say to the Captain, one short line each and in speaking order, WHAT was done, with the "
               "exact values (never a bare 'aye'); for anything that FAILED, why, and an alternative." if readback else
               "The responsible officer now tells the Captain briefly what failed and why, and proposes an alternative "
               "if there is one.")
        follow = msgs + [
            {"role": "assistant", "content": " ".join(f"[{s}] {t}" for s, t in turn.lines) or "(orders executed)"},
            {"role": "user", "content": f"[Ship systems report]\n{notes}\n{ask} Use speak."}]
        t0 = time.perf_counter()
        state = self.ship.snapshot()
        comp = await self._llm(turn, "crew", follow, [SPEAK],
                               self._on_call(turn, lang, t0, [], tools_for(state), state, [], captain=True), max_tokens=260)
        turn.cost += comp.cost

    def _record(self, user: str, calls: list[ToolCall], results: dict[int, dict[str, Any]], turn: Turn, main_lines: int) -> None:
        """History in the native tool-calling format: the model keeps answering through tools (a text summary of past
        turns made it drift into prose after a few turns). Lines voiced outside tool calls become synthetic speak calls."""
        self.history.append({"role": "user", "content": user})
        calls = [c for c in calls if c.name]
        extra = turn.lines[main_lines:] if calls else turn.lines
        if calls:
            self._append_calls([(c.id or f"call_{i}", c.name, c.arguments_raw or "{}",
                                 "spoken" if c.name == "speak" else (("ok: " if results.get(id(c), {}).get("ok") else "FAILED: ")
                                                                     + str(results.get(id(c), {}).get("detail", ""))))
                                for i, c in enumerate(calls)])
        if extra:
            self._ev += 1
            self._append_calls([(f"syn{self._ev}_{i}", "speak", json.dumps({"speaker": spk, "text": line, "tone": "focused"},
                                                                          ensure_ascii=False), "spoken")
                                for i, (spk, line) in enumerate(extra)])
        if not calls and not extra:
            self.history.append({"role": "assistant", "content": "(no reply)"})
        self._trim_history()

    def _append_calls(self, items: list[tuple[str, str, str, str]]) -> None:
        self.history.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": cid, "type": "function", "function": {"name": name, "arguments": args}} for cid, name, args, _ in items]})
        for cid, _, _, result in items:
            self.history.append({"role": "tool", "tool_call_id": cid, "content": result})


EVENT_ASK = ("The Captain should hear this: the responsible officer reports it now, in one short line with speak (in the "
             "Captain's language), unless it merely repeats what was reported in the last few seconds, or it is news that has "
             "grown old while the bridge was busy ([happened N s ago]) and no longer matters as it stands — then say nothing, or "
             "say what it means now. When several things happened at once (they are joined by |), the officers report the one or "
             "two that matter most to the Captain right now, the most dangerous first, one short line each: the rest stays on "
             "the boards and the datapad, where the Captain can ask for it; in a battle the Captain hears many voices, and a "
             "report that changes nothing the Captain must decide is better left unsaid. Within "
             "their own authority an officer may also act at once: with live consoles, set a mode on their own console when their "
             "delegation is auto and it keeps the Captain's intent alive; on an older build, damage control, shield facing, point "
             "defense and the radiators. To act, CALL the tool in this same turn, then say what was done — saying it without the "
             "tool call does nothing and misleads the Captain. What needs the Captain's word (course changes on your own, a "
             "new offensive, leaving, breaking off, a channel with the enemy) is proposed instead — unless a standing order in "
             "force covers it.")
STANDING_ASK = (" Standing orders in force (see them in the rules) are the Captain's orders given in advance: when this "
                "event is what one is about, that officer carries it out now, fully (weapons free means firing: fire_weapons or "
                "an engage mode, not just a target), with the tool calls in this same turn, and says what was done.")
INITIATIVE = {"dispatch_damage_control", "set_shields", "set_point_defense", "set_radiators", "launch_decoys"}


async def _safe_execute(ship: ShipLink, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
    try:
        return await ship.execute(name, args, by)
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "detail": f"invalid arguments for {name}: {exc}"}
    except asyncio.TimeoutError:
        return {"ok": False, "detail": "no response from ship systems"}


async def _refuse(why: str) -> dict[str, Any]:
    return {"ok": False, "detail": why}


def _patients(state: dict[str, Any]) -> set[str]:
    """The Medbay's occupied beds (their speaker ids)."""
    return {p.get("speaker", "") for p in ((state or {}).get("medbay") or {}).get("patients", [])}


def _diners(state: dict[str, Any]) -> set[str]:
    """The Mess Hall's people while the Captain is there: the diners at their places and the cook (speaker ids)."""
    mess = (state or {}).get("mess") or {}
    return {d.get("speaker", "") for d in mess.get("diners", [])} | ({"mess_cook"} if mess else set())


def _owner(tool: str) -> str:                          # (kept for callers of the old name)
    return owner_of(tool)


def _fallback_line(lang: str) -> str:
    return {"it": "Capitano, ho perso un attimo il collegamento con i sistemi. Può ripetere?",
            "es": "Capitán, hemos perdido un momento la conexión con los sistemas. ¿Puede repetir?",
            "de": "Captain, kurze Störung in den Systemen. Bitte wiederholen.",
            "fr": "Capitaine, petite coupure des systèmes. Pouvez-vous répéter ?"}.get(lang, "Captain, we lost the systems link for a moment. Say again?")
