"""The bridge crew agent: one model call per Captain's utterance, streamed; each `speak` goes to the voice queue and
each ship tool goes to the simulation the moment its arguments are complete. Failed actions trigger a short
follow-up so the responsible officer reports what went wrong (closed loop: the ship state is the truth).

v2 (docs/contratto_postazioni.md): with live consoles the officers set persistent modes (`station`) instead of repeating
orders, keep them alive on their own within their delegation (events and the initiative watch, `handle_event`), and
speak briefly and to the point. The Captain has priority over everything: `preempt()` drops whatever the crew was
in the middle of when the Captain speaks. A game build without consoles keeps the legacy tools (tools.tools_for)."""
from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from . import context as context_model
from . import models
from . import stations as station_model
from .crew import CREW, bridge_now, crew_context, system_prompt
from .nets import NET_EVENT
from .openrouter import Completion, OpenRouter, ToolCall
from .tools import CONSOLE_LOG, DEPT_TOOLS, LOOKUPS, SHIP_TOOL_NAMES, SILENT_TOOLS, SPEAK, initiative_names, owner_of, tools_for

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
        # what the room heard aloud lately (the speech floor's record: speech.Voice.heard_since, set by the server): (seconds ago, who, words, said to the end)
        self.heard: Callable[[float], list[tuple[float, str, str, bool]]] = lambda seconds: []
        # what is queued on the speech floor and not said yet (speech.Voice.waiting, set by the server): (who, words, how urgent)
        self.waiting: Callable[[], list[tuple[str, str, str]]] = lambda: []
        # the radio nets and the consoles' logs (nets.Nets, set by the server): `console_log` writes there, `net_speaker` puts a net on the speaker, `digest` is what the
        # officers see of both at the head of a turn (what the nets said that the Captain has not heard, what the consoles logged)
        self.nets: Any = None
        self.titles = {k: v.title for k, v in CREW.items()}
        self.orders: deque[tuple[float, str]] = deque(maxlen=12)   # the Captain's last words to the bridge (they outlive the history's cuts)
        self._active: set[Turn] = set()  # turns being worked on (what preempt() reaches)

    # ------------------------------------------------------------------------------------------------ priority
    def preempt(self) -> int:
        """The Captain speaks: whatever the crew was doing on its own stops now — the model calls in flight for a report, a watch check or
        a chat are dropped and nothing more is voiced for those turns (what was already sent to the ship stays done). A turn that is
        carrying out the Captain's own words goes on: his next words come after it, and a second press of the key (or one that said
        nothing) cancelled an order before any of it had reached the ship ("Timoniere, ritirata" lost to an empty press, 2 Oct). Returns how
        many turns were cut off."""
        n = 0
        for turn in list(self._active):
            if turn.kind == "captain":
                continue
            turn.cancelled = True
            if turn.task and not turn.task.done():
                turn.task.cancel()
            n += 1
        return n

    def busy(self) -> bool:
        return bool(self._active)

    # ------------------------------------------------------------------------------------------------ prompts
    def _trim_history(self) -> None:
        """The conversation stays append-only between cuts and is cut only from the front, in one go: the provider caches a prompt's unchanged
        prefix, and a history edited in the middle (the old reports dropped between the Captain's orders) broke that prefix at almost every call
        of a battle (3 Oct: 55 % cached, the same 13k-token boundary call after call). When it passes twice its size, the oldest turns go, back to
        `history_turns` + 6 turns. The Captain's orders older than that are not lost: they stay in their own list (`orders`, in the bridge now)."""
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        limit = self.history_turns + 6
        if len(starts) <= 2 * limit:
            return
        self.history = self.history[starts[-limit]:]

    def _last_turns(self, n: int) -> list[dict[str, Any]]:
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        return self.history[starts[-n]:] if len(starts) > n else list(self.history)

    def _system(self, lang: str, state: dict[str, Any], ctx: context_model.Context | None = None) -> dict[str, str]:
        # only what does not change from turn to turn: the provider caches it and the conversation after it (crew_context goes last)
        return {"role": "system", "content": system_prompt(lang, state, [])}

    def _context(self) -> str:
        """What the crew carries (the war, the mood, standing orders, memories, the Captain's ways, the officers' lives and bonds): the head of the
        last message (crew.crew_context)."""
        return crew_context(self.campaign(), self.war(), self.mood(), self.bonds(), self.standing_lines(), self.memories(), self.style(), self.home())

    def _now(self, state: dict[str, Any], ctx: context_model.Context | None = None, news: bool = False) -> str:
        """The bridge this moment (crew.bridge_now), for the head of a turn's last message. `news`: it is the head of a report turn."""
        hearing = context_model.describe(ctx, self.titles) if ctx else ""
        return bridge_now(state, self.ship.recent_events(), hearing, self._said_aloud(), self._waiting(), self._context(), self._orders(),
                          where=context_model.where_now(ctx, state), logs=self._logs(), news=news)

    def _logs(self) -> str:
        """What the nets said that the Captain has not heard, and what the consoles' logs hold (nets.Nets.digest): the officers' sense of what the bridge knows and has not said."""
        return self.nets.digest() if self.nets is not None else ""

    def _waiting(self) -> str:
        """The lines queued on the floor behind whoever is speaking: the officers see the backlog (a crisis made fifty urgent lines in four minutes, 2 Oct,
        and most were dropped unsaid)."""
        return "\n".join(f"- {who} ({how}): «{words}»" for who, words, how in self.waiting())

    def _said_aloud(self) -> str:
        """What the Captain has heard on the bridge in the last minute, as it was said (a line thought again is here in its new words, one
        cut off as far as it went, one never said is not here): the officers' sense of what is already known."""
        return "\n".join(f"- {ago:.0f} s ago, {who}: «{words}»" + ("" if full else " (cut off there)")
                         for ago, who, words, full in self.heard(HEARD_WINDOW_S))

    def _messages(self, text: str, lang: str, state: dict[str, Any], ctx: context_model.Context | None = None,
                  note: str = "") -> list[dict[str, Any]]:
        # the system prompt and the history are the same from call to call (the prompt cache covers them); what changes comes last
        msgs: list[dict[str, Any]] = [self._system(lang, state, ctx)]
        msgs += self.history
        msgs.append({"role": "user", "content": self._now(state, ctx) + f"\n\nCaptain: {text}" + (f"\n[{note}]" if note else "")})
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

    async def _console_log(self, args: dict[str, Any]) -> dict[str, Any]:
        """An officer writes a line on a console's log, silently (nets.Nets.console_log)."""
        if self.nets is None:
            return {"ok": True, "detail": "(no console to write on in this build)"}
        return self.nets.console_log(str(args.get("station") or ""), str(args.get("text") or ""), kind=str(args.get("kind") or "routine"),
                                     by=str(args.get("station") or ""))

    async def _net_speaker(self, args: dict[str, Any]) -> dict[str, Any]:
        """A radio net goes on the bridge's speaker, or off it, because the Captain asked."""
        if self.nets is None:
            return {"ok": False, "detail": "the nets cannot be put on the speaker in this build"}
        return self.nets.set_speaker(str(args.get("net") or "").lower(), bool(args.get("on", True)))

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
        ts = tools_for(state, ctx)                                   # (inside a lift car: the ship's computer has `lift_go`)
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
            acted = [a for a in turn.actions if a[0] not in SILENT_TOOLS]          # (a line written on a console's log is no order to read back)
            failures = [a for a in acted if not a[2].get("ok", False)]
            looked_up = any(n in LOOKUPS for n, _, _ in turn.actions)
            if not turn.cancelled:
                if acted and not comp.error and (not turn.lines or looked_up):
                    await self._follow_up(turn, msgs, lang, readback=True, ts=ts)      # orders carried out in silence, or a file read: say what
                elif failures:
                    await self._follow_up(turn, msgs, lang, readback=False, ts=ts)
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
        now = "" if system else self._now(state, news=True) + "\n\n"            # (a role with a prompt of its own carries its own view of the ship)
        msgs.append({"role": "user", "content": now + user + "\n" + (ask or EVENT_ASK) + (STANDING_ASK if self.standing and not speak_only else "")})   # (a turn that can only speak carries nothing out)
        on_call = self._on_call(turn, lang, t0, pending, ts, state, fired, captain=False, allowed=allowed)
        tools = [t for t in ts.tools if t["function"]["name"] in (allowed | {"speak"} | (set() if speak_only else {"console_log"}))]   # (the log is silent: nobody's authority is needed)
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
            if any(a[0] not in SILENT_TOOLS for a in turn.actions) and not turn.lines and not comp.error and not turn.cancelled:
                await self._follow_up(turn, msgs, lang, readback=True)   # acted on initiative in silence: say so (what was only written on a log is not an action)
            if turn.lines or any(a[0] not in SILENT_TOOLS for a in turn.actions):       # (a turn that only wrote the console logs is on the logs, not in the talk: the cache and the history stay short)
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
               "since (the state above is now), and the bridge has heard what «Said aloud» lists. If it still matters to the Captain, they "
               "say it now as it stands — updated, short, in character — with speak. If it no longer matters, or the Captain has already "
               "heard it (from them or from anyone, in other words too) and nothing has changed since that he must act on, they say "
               "nothing: do not call speak; what is only routine they may write on their console's log (console_log) instead of letting it vanish. "
               "A line that answers an order of the Captain's (what was done about it, what the other ship or "
               "console said) still matters unless it has been said already: the Captain is waiting for it — say it, updated if things "
               "changed, and add only what is new and pressing.")
        msgs = [self._system(lang, state)] + self._last_turns(4) + [{"role": "user", "content": self._now(state) + "\n\n" + ask}]
        said: list[str] = []
        logged: list[str] = []

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            if call.name == "speak":
                line = str(args.get("text") or "").strip()
                if line:
                    said.append(line)
            elif call.name == "console_log":
                res = await self._console_log(args)
                if res.get("ok"):
                    logged.append(str(args.get("text") or ""))

        comp = await models.chat(self.llm, "crew", messages=msgs, tools=[SPEAK, CONSOLE_LOG], tool_choice="auto", on_tool_call=on_call, max_tokens=160)
        self.spent += comp.cost
        if comp.error and not said and not logged:
            raise RuntimeError(f"the model did not answer: {comp.error[:100]}")           # (the speech floor tells a model that failed from an officer who chose silence)
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
                if speaker == "computer" and ts.lift:
                    pass                                            # the ship's computer, in a lift car
                elif speaker not in CREW and speaker not in _patients(st_) and speaker not in _diners(st_):
                    speaker = "doctor" if str(speaker).startswith("patient") else "xo"   # (a voice must belong to someone aboard)
                line = (args.get("text") or "").strip()
                if not line:
                    return
                await self._voice(turn, t0, speaker, line, lang, args.get("tone", "calm"))
            elif call.name == "standing_order" and captain:
                pending.append((call, asyncio.create_task(self._standing_order(args))))     # the mind's own, not the ship's
            elif call.name == "console_log":
                pending.append((call, asyncio.create_task(self._console_log(args))))        # silent, nobody's authority is needed (the mind's own, like the standing order)
            elif call.name == "net_speaker" and captain:
                pending.append((call, asyncio.create_task(self._net_speaker(args))))        # the Captain asked for a net on the speaker (or off it)
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
        by = "captain" if captain else "officer"
        if cmd["mode"] == "delegation" and cmd["params"].get("station") == "all":
            # «fate da soli»: every console in one call (the game takes one console at a time, and seven calls and a spoken line do not fit a turn's tokens)
            level = cmd["params"]["level"]
            done, refused = [], []
            for sid in station_model.DELEGABLE:
                one = {**cmd, "params": {"station": sid, "level": level}}
                res = await _safe_execute(self.ship, "station", station_model.to_wire(one, by=by), owner_of("station", one))
                (done if res.get("ok") else refused).append(sid)
            return {"ok": not refused, "detail": f"every console on {level}" if not refused else f"{', '.join(done) or 'none'} on {level}; refused: {', '.join(refused)}"}
        # to the game in its own words: the aspect, the game's mode name, and who decided (the console log and the board show it)
        wire = station_model.to_wire(cmd, by=by)
        return await _safe_execute(self.ship, "station", wire, owner_of("station", cmd))

    async def _collect(self, pending: list, turn: Turn) -> dict[int, dict[str, Any]]:
        """Results of the actions (the simulation is the truth)."""
        results: dict[int, dict[str, Any]] = {}
        for call, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=7.0)
            except asyncio.TimeoutError:
                res = dict(NO_ANSWER)
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
                res = await asyncio.wait_for(task, timeout=7.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                res = dict(NO_ANSWER)
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

    async def _follow_up(self, turn: Turn, msgs, lang: str, readback: bool, ts: Any = None) -> None:
        notes = "\n".join(f"- {n}({json.dumps(a, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"
                          for n, a, r in turn.actions if readback or not r.get("ok", False))
        lookup = readback and any(n in LOOKUPS for n, _, _ in turn.actions)
        ask = ("The officer who looked it up now reports to the Captain what the personnel file and the locator say about the people "
               "asked for: a report ABOUT them, in the third person (they are other members of the crew, not the officer speaking), "
               "who they are, where they are and what they are doing, in one or two short lines; nothing the file does not say. Then, "
               "one short line each, any other officer who acted says what was done." if lookup else
               "The officers who acted now say to the Captain, one short line each and in speaking order, WHAT was done in a few words, "
               "with the value that matters (never a bare 'aye', and nothing around it); for anything that FAILED, why, and an alternative." if readback else
               "The responsible officer now tells the Captain briefly what failed and why, and proposes an alternative "
               "if there is one — unless the line above already said it: then call no tool, nothing is said twice.")
        follow = msgs + [
            {"role": "assistant", "content": " ".join(f"[{s}] {t}" for s, t in turn.lines) or "(orders executed)"},
            {"role": "user", "content": f"[Ship systems report]\n{notes}\n{ask} Use speak."}]
        t0 = time.perf_counter()
        state = self.ship.snapshot()
        comp = await self._llm(turn, "crew", follow, [SPEAK],
                               self._on_call(turn, lang, t0, [], ts or tools_for(state), state, [], captain=True), max_tokens=260)   # (the turn's own tools: in a lift car the computer may speak)
        turn.cost += comp.cost

    def _orders(self) -> str:
        """The Captain's last words to the bridge, newest last, with how long ago (the conversation above may have been cut before them)."""
        now = time.monotonic()
        return "\n".join(f"- {max(0.0, now - t) / 60:.0f} min ago: «{w}»" for t, w in self.orders)

    def _record(self, user: str, calls: list[ToolCall], results: dict[int, dict[str, Any]], turn: Turn, main_lines: int) -> None:
        """History in the native tool-calling format: the model keeps answering through tools (a text summary of past
        turns made it drift into prose after a few turns). Lines voiced outside tool calls become synthetic speak calls."""
        self.history.append({"role": "user", "content": user})
        if user.startswith("Captain: "):
            self.orders.append((time.monotonic(), user[len("Captain: "):].splitlines()[0][:240]))
        calls = [c for c in calls if c.name]
        extra = turn.lines[main_lines:] if calls else turn.lines
        if calls:
            self._append_calls([(c.id or f"call_{i}", c.name, c.arguments_raw or "{}",
                                 "spoken" if c.name == "speak" else (("ok: " if results.get(id(c), {}).get("ok")
                                                                      else "NOT CONFIRMED YET: " if results.get(id(c), {}).get("ok", False) is None else "FAILED: ")
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


HEARD_WINDOW_S = 60.0       # how far back the officers' «Said aloud» goes

EVENT_ASK = ("NEWS (the events above, several joined by |): it happened while the Captain was busy, and the default of a news turn is SILENCE: most of them say nothing, or only "
             "write on a log. The test: would the Captain act differently, or be worse off, if nobody said this aloud? If not, it is not said. "
             "SAY IT with one short `speak` line (in the Captain's language): from the XO, who is the voice of the picture and of advice — what changed, what it means, what he might "
             "do, in one sentence of ten to twenty words — or from the officer who owns it ONLY for danger he can act on right now in their field (a salvo inbound, a breach, the reactor "
             "or the heat at a limit, a squadron lost), a decision in their field that is his to make, or a call that needs his answer. When several things happened at once ONE line "
             "covers them, the most dangerous first. "
             "LOG IT with `console_log` on the console it belongs to — one telegraphic line in English, and NO `speak` — when it is routine: a range or a shield percentage that moved, a "
             "rearm or a repair done, a fire out, a contact that faded or was lost, point defence splashing a missile, a target retargeted inside the orders. "
             "SAY NOTHING when the Captain has already heard it («Said aloud» in the bridge now: from anyone, in any words), when it is already waiting to be said («Waiting to be said»), "
             "when it is the same picture again (the same fight, the next salvo, the next range of the same target), when it is his own order coming back, or when it is news that grew old "
             "while the bridge was busy ([happened N s ago]) and no longer matters as it stands. Before you speak, read «Said aloud»: if what you are about to say is already there in "
             "substance — in other words, with the same figures, from another officer, or beginning with the same words — say nothing, the same picture again is the worst noise on a "
             "bridge; say only what is NEW since the last line: a new contact, a loss, a number that crossed a line that matters. A good bridge in a crisis is a few clear voices, not "
             "every voice at once: when lines are already waiting to be said, a new one is worth adding only if it matters more than all of them. "
             "A vessel's distress call, convoy and traffic news and a port's call are Communications' alone. The first is one line (who, how far, what is after them); the ones that follow "
             "while the Captain has not answered are logged on the comms console (`console_log`) or, if together they change the picture, told in ONE grouped line («two more merchants "
             "are calling, on the log»). In a fight the Captain hears of such a call only when the Aquila can really do something about it now (in reach, in time); otherwise it is for the "
             "log. "
             "A voice over the radio that the Captain heard himself (an enemy commander on his channel, the admiral or a captain answering him, a net he asked to hear: it is in «Said aloud» "
             "and in the recent events as «over the radio») is nobody's to repeat or sum up; an officer speaks after it only to add what the bridge knows and it did not say. Net traffic he "
             "did not hear (the «net:» events) is its listener's: see the nets. A hail and a channel are Communications' (Martin): he alone says who is calling, if the Captain did not "
             "hear it, and keeps the channel; no other officer relays a call or offers to answer it for the Captain. Within their own authority an officer may also act at once: with live "
             "consoles, set a mode on their own console when their delegation is auto and it keeps the Captain's intent alive; on an older build, damage control, shield facing, point "
             "defense and the radiators. To act, CALL the tool in this same turn — saying it without the tool call does nothing and misleads the Captain — and say what was done in one line "
             "when it changes the fight (a launch, a new target for the guns, a squadron recalled); keeping a console alive inside the orders is the log's. What needs the Captain's word "
             "(course changes on your own, a new offensive, leaving, breaking off, a channel with the enemy) is proposed instead — unless a standing order in force covers it.")
NET_ASK = ("NET TRAFFIC (the «net:» event above): radio on a net that the Captain has NOT heard — it is not on the bridge's speaker; he reads the consoles' logs and the datapad. The "
           "officer who has the watch on that net decides, line by line, between two things. "
           "TELL HIM — one short `speak` line of their own (never the sender's words read back), and the log as well if they like — when: the event says [URGENT]; a line calls the "
           "Captain or needs his answer; it is an order from Fleet; a ship, a squadron, a pilot or a marine is lost or down; or it is a warning he has not had (an attack coming, a ship "
           "under fire). "
           "LOG IT — `console_log`, one telegraphic line in English, and NO `speak` — when it is routine: a position, a range, a bearing, a formation held, a «ready», a rearm done, a team "
           "in place, a bulkhead sealed, an ally holding. A turn of routine traffic has no `speak` call at all. "
           "What the Captain has already heard («Said aloud», in any words), what his own order just produced, and what the boards show are never told again; when lines are already "
           "waiting to be said, only what outweighs them is worth adding.")


SYSTEM_CALLS = ("comms: distress call", "comms: fleet net news")       # (what the game and the March send to Communications: a vessel calling for help, the fleet net's news of the war)
SYSTEM_CALL_ASK = ("SYSTEM CALL (the «comms:» event above): a vessel's call for help, or the fleet net's news of the war. It is Communications' (Martin) and it is NOT an alarm: a "
                   "bridge that says every call aloud is a switchboard. Read «Said aloud» and the recent events first. "
                   "THE FIRST of its kind (nothing like it was said in the last few minutes): ONE `speak` line from Communications — who, how far from us, what is after them — and the "
                   "comms log as well if he likes. "
                   "ANY LATER ONE while the Captain has not answered the first: `console_log` on the comms console (one telegraphic line in English) and NO `speak` — at most ONE grouped line "
                   "(«two more merchants are calling, toward the Arsenal: they are on the log») when together they change what the Aquila should do. "
                   "In a fight the Captain hears of a call only when the Aquila can really do something about it now (in reach, in time); otherwise it is for the log. "
                   "Nobody else says it: the XO does not repeat Communications' line.")


def system_calls_only(events: list[str]) -> bool:
    """The news is only calls of the system to Communications (a distress call, the fleet net's news): they are asked by their own doctrine, alone."""
    return bool(events) and all(e.startswith(SYSTEM_CALLS) for e in events)


def net_ask(events: list[str]) -> str:
    """The ask of a report turn that has net traffic among its news: the listener's doctrine alone when the news is only traffic (the general ask says «report it», and the officers
    follow the first thing they are told), with the general ask when other news is there too."""
    return NET_ASK if all(e.startswith(NET_EVENT) for e in events) else EVENT_ASK + " " + NET_ASK
WHEEL_ASK = ("THE COMMAND WHEEL: the event above is an order the Captain gave WITHOUT A WORD, from his command wheel. It is HIS ORDER, exactly as if he had spoken it, and the console has "
             "already carried it out (you only have `speak`: do not carry it out again). "
             "WHO: ONE officer answers, the one whose station it is — Helm for course and speed; Tactical for targets, weapons, missiles, shields and decoys; Flight Control for the flight "
             "deck and the squadrons; Operations for power, damage control, the transporter and the main screen; the XO for the alert level. An order that spans two stations (engage: guns "
             "and bow) is answered once, by Tactical. Nobody else says anything, the XO included. "
             "HOW: two to five words, in the Captain's language and in character — «Aye, helm.» «Weapons free.» «Red alert.» «Falcons launching.» «Screen on the target.» Not a sentence: no "
             "what-it-means («all hands to battle stations»), no range, target or heading read back, nothing about what happens next, no «Captain, …» preamble, no question about whether he "
             "meant it. "
             "UNLESS the detail in brackets shows that something did not go through (refused, failed, not possible, no lane free), or the order will hurt the ship in a way the Captain "
             "cannot see on the wheel (it turns her broadside to a missile salvo, it drops the shields with a torpedo in the water): then one short line says what did not happen or "
             "what is wrong, instead of the acknowledgement.")
STANDING_ASK = (" Standing orders in force (see them in the rules) are the Captain's orders given in advance: when this "
                "event is what one is about, that officer carries it out now, fully (weapons free means firing: fire_weapons or "
                "an engage mode, not just a target), with the tool calls in this same turn, and says what was done.")
INITIATIVE = {"dispatch_damage_control", "set_shields", "set_point_defense", "set_radiators", "launch_decoys"}


NO_ANSWER = {"ok": None, "detail": "sent to the console, no confirmation yet: the ship's systems were busy for a moment (a force coming into the plot loads for a "
                                    "few seconds). It is most likely in force: the console will show it on the next turn. Do not tell the Captain it failed"}


async def _safe_execute(ship: ShipLink, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
    try:
        return await ship.execute(name, args, by)
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "detail": f"invalid arguments for {name}: {exc}"}
    except asyncio.TimeoutError:
        return dict(NO_ANSWER)          # (5 Oct: the order was in force and the officer told the Captain «the command did not answer»)


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
