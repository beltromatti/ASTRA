"""The bridge crew agent: one model call per Captain's utterance, streamed; each `speak` goes to the voice queue and
each ship tool goes to the simulation the moment its arguments are complete. Failed actions trigger a short
follow-up so the responsible officer reports what went wrong (closed loop: the ship state is the truth)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from .crew import CREW, system_prompt
from .openrouter import OpenRouter, ToolCall
from .tools import ALL_TOOLS, DEPT_TOOLS, SHIP_TOOL_NAMES, SHIP_TOOLS, SPEAK

log = logging.getLogger("astra.agent")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]   # 2026-09-28: Modal returns empty arguments with tool_choice=required


class ShipLink(Protocol):
    def snapshot(self) -> dict[str, Any]: ...
    def recent_events(self) -> list[str]: ...
    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]: ...


SayFn = Callable[[str, str, str, str], Awaitable[None]]   # (speaker, text, lang, tone)


@dataclass
class Turn:
    text: str
    lang: str
    lines: list[tuple[str, str]] = field(default_factory=list)
    actions: list[tuple[str, dict[str, Any], dict[str, Any]]] = field(default_factory=list)
    t_first_line: float | None = None
    t_end: float = 0.0
    cost: float = 0.0
    error: str = ""


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
        self.memories = lambda: ""       # what each officer remembers of the Captain (memory.py, set by the server)

    def _trim_history(self) -> None:
        """Keep the last `history_turns` turns (a turn starts at a user message)."""
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(starts) > self.history_turns:
            self.history = self.history[starts[-self.history_turns]:]

    def _messages(self, text: str, lang: str) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(lang, self.ship.snapshot(), self.ship.recent_events(), self.campaign(), self.war(), self.mood(), self.bonds(), self.standing_lines(), self.memories())}]
        msgs += self.history
        msgs.append({"role": "user", "content": f"Captain: {text}"})
        return msgs

    def standing_lines(self) -> str:
        return "\n".join(f"- {o['department']}: {o['order']}" for o in self.standing)

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
        """What the crew may do by itself at an event: the usual (damage control, shields, point defence, radiators)
        and whatever the standing orders put in a department's hands."""
        allowed = set(INITIATIVE)
        for o in self.standing:
            allowed |= DEPT_TOOLS.get(o["department"], set())
        return allowed

    async def handle(self, text: str, lang: str) -> Turn:
        turn = Turn(text=text, lang=lang)
        t0 = time.perf_counter()
        pending: list[tuple[ToolCall, asyncio.Task]] = []
        on_call = self._on_call(turn, lang, t0, pending, allowed=SHIP_TOOL_NAMES)
        msgs = self._messages(text, lang)
        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=ALL_TOOLS, tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=450, temperature=0.4, on_tool_call=on_call,
                                   allow_fallbacks=True)
        turn.cost += comp.cost
        log.info("llm: provider=%s finish=%s calls=%s content=%r error=%s", comp.provider, comp.finish_reason,
                 [(c.name, c.arguments_raw[:120]) for c in comp.tool_calls], comp.content[:200], comp.error)
        if not comp.error and not turn.lines and comp.content.strip():
            # the model answered in prose instead of calling speak: salvage it as the XO's (or tagged officer's) line
            log.warning("no speak call, salvaging content: %s", comp.content[:200])
            await self._salvage(comp.content, turn, lang, max_lines=3)
        if comp.error:
            turn.error = comp.error
            log.error("LLM error: %s", comp.error)
            await self.say("xo", _fallback_line(lang), lang, "calm")
        results = await self._collect(pending, turn)
        main_lines = len(turn.lines)
        failures = [a for a in turn.actions if not a[2].get("ok", False)]
        if turn.actions and not turn.lines and not comp.error:
            await self._follow_up(msgs, turn, lang, readback=True)      # orders carried out in silence: read them back
        elif failures:
            await self._follow_up(msgs, turn, lang, readback=False)
        self._record(f"Captain: {text}", comp.tool_calls, results, turn, main_lines)
        turn.t_end = time.perf_counter() - t0
        self.spent += turn.cost
        return turn

    async def handle_event(self, event: str, lang: str, ask: str | None = None) -> Turn:
        """A ship event (not the Captain): the responsible officer reports it, and may act within their own authority."""
        turn = Turn(text=f"[event] {event}", lang=lang)
        t0 = time.perf_counter()
        pending: list[tuple[ToolCall, asyncio.Task]] = []
        user = f"[Ship systems event, not the Captain speaking] {event}"
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(lang, self.ship.snapshot(), self.ship.recent_events(), self.campaign(), self.war(), self.mood(), self.bonds(), self.standing_lines(), self.memories())}]
        msgs += self.history
        msgs.append({"role": "user", "content": user + "\n" + (ask or EVENT_ASK) + (STANDING_ASK if self.standing else "")})
        allowed = self.initiative()
        on_call = self._on_call(turn, lang, t0, pending, allowed=allowed)
        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=[SPEAK] + [t for t in SHIP_TOOLS if t["function"]["name"] in allowed], tool_choice="auto",
                                   providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=360, temperature=0.4,
                                   on_tool_call=on_call, allow_fallbacks=True)
        turn.cost += comp.cost
        if not turn.lines and not comp.error and comp.content.strip() and not comp.content.strip().upper().startswith("SILENT"):
            # the report came back as prose ("sensors: ...") instead of a speak call: voice it anyway, officer by officer
            log.info("event report salvaged from prose: %s", comp.content[:160])
            await self._salvage(comp.content, turn, lang, max_lines=2)
        results = await self._collect(pending, turn)
        main_lines = len(turn.lines)
        if turn.actions and not turn.lines and not comp.error:
            await self._follow_up(msgs, turn, lang, readback=True)   # acted on initiative in silence: say so
        if turn.lines or turn.actions:
            self._record(user, comp.tool_calls, results, turn, main_lines)
        turn.t_end = time.perf_counter() - t0
        self.spent += turn.cost
        return turn

    # ------------------------------------------------------------------------------------------------ internals
    def _on_call(self, turn: Turn, lang: str, t0: float, pending: list, allowed: set[str]):
        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            if call.name == "speak":
                speaker = args.get("speaker", "xo")
                st_ = self.ship.snapshot()
                if speaker not in CREW and speaker not in _patients(st_) and speaker not in _diners(st_):
                    speaker = "doctor" if str(speaker).startswith("patient") else "xo"
                line = (args.get("text") or "").strip()
                if _looks_like_tool(line):
                    log.warning("speak contained a tool invocation, not voiced: %s", line)
                    line = ""
                if len(line) >= 4:                               # never voice fragments of a cut-off reply
                    if turn.t_first_line is None:
                        turn.t_first_line = time.perf_counter() - t0
                    turn.lines.append((speaker, line))
                    await self.say(speaker, line, lang, args.get("tone", "calm"))
            elif call.name == "standing_order" and allowed is SHIP_TOOL_NAMES:
                pending.append((call, asyncio.create_task(self._standing_order(args))))     # the mind's own, not the ship's
            elif call.name in allowed:
                pending.append((call, asyncio.create_task(_safe_execute(self.ship, call.name, args, _owner(call.name)))))
            else:
                log.warning("tool %s not allowed here", call.name)
        return on_call

    async def _salvage(self, content: str, turn: Turn, lang: str, max_lines: int) -> None:
        for raw in [l for l in content.strip().splitlines() if l.strip()][:max_lines]:
            spk, line = _parse_prose(raw)
            if len(line) >= 4 and not _looks_like_tool(line):
                turn.lines.append((spk, line))
                await self.say(spk, line, lang, "focused")

    async def _collect(self, pending: list, turn: Turn) -> dict[int, dict[str, Any]]:
        """Results of the actions (the simulation is the truth)."""
        results: dict[int, dict[str, Any]] = {}
        for call, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=3.0)
            except asyncio.TimeoutError:
                res = {"ok": False, "detail": "no response from ship systems"}
            turn.actions.append((call.name, call.arguments() or {}, res))
            results[id(call)] = res
        return results

    async def _follow_up(self, msgs, turn: Turn, lang: str, readback: bool) -> None:
        notes = "\n".join(f"- {n}({json.dumps(a, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"
                          for n, a, r in turn.actions if readback or not r.get("ok", False))
        ask = ("The officers who acted now report to the Captain in speaking order, one short line each: what was done, "
               "with the exact values; for anything that FAILED, why, and an alternative." if readback else
               "The responsible officer now tells the Captain briefly what failed and why, and proposes an alternative "
               "if there is one.")
        follow = msgs + [
            {"role": "assistant", "content": " ".join(f"[{s}] {t}" for s, t in turn.lines) or "(orders executed)"},
            {"role": "user", "content": f"[Ship systems report]\n{notes}\n{ask} Use speak."}]
        t0 = time.perf_counter()
        comp = await self.llm.chat(model=MODEL, messages=follow, tools=[SPEAK], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=320, temperature=0.4,
                                   on_tool_call=self._on_call(turn, lang, t0, [], allowed=set()), allow_fallbacks=True)
        turn.cost += comp.cost
        if not comp.error and comp.content.strip() and not any(True for _ in comp.tool_calls):
            await self._salvage(comp.content, turn, lang, max_lines=3)

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
             "Captain's language). Within their own authority an officer may also act at once (Operations: damage-control "
             "teams; Tactical: shield facing, point defense and decoys against incoming missiles; Engineering: the radiators): to act, CALL the tool in this "
             "same turn, then say what was done — saying it without the tool call does nothing and misleads the Captain. "
             "Anything else (course, weapons, alert, power, venting coolant) waits for the Captain's order — propose it "
             "instead — unless a standing order in force covers it. Call no tool only if this merely repeats what was "
             "reported in the last few seconds.")
STANDING_ASK = (" Standing orders in force (see them in the rules) are the Captain's orders given in advance: when this "
                "event is what one is about, that officer carries it out now, fully (weapons free means firing: fire_weapons, "
                "not just a target), with the tool calls in this same turn, and says what was done.")
INITIATIVE = {"dispatch_damage_control", "set_shields", "set_point_defense", "set_radiators", "launch_decoys"}
INITIATIVE_TOOLS = [t for t in SHIP_TOOLS if t["function"]["name"] in INITIATIVE]


_TOOLISH = None


def _looks_like_tool(text: str) -> bool:
    """A 'speak' whose text is a tool invocation (e.g. "set_alert red") must never be voiced."""
    global _TOOLISH
    if _TOOLISH is None:
        import re
        from .tools import SHIP_TOOL_NAMES
        _TOOLISH = re.compile(r"^\s*\[?(%s)\b" % "|".join(sorted(SHIP_TOOL_NAMES)))
    return bool(_TOOLISH.match(text))


async def _safe_execute(ship: ShipLink, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
    try:
        return await ship.execute(name, args, by)
    except (KeyError, TypeError, ValueError) as exc:
        return {"ok": False, "detail": f"invalid arguments for {name}: {exc}"}
    except asyncio.TimeoutError:
        return {"ok": False, "detail": "no response from ship systems"}


def _parse_prose(content: str) -> tuple[str, str]:
    import re
    c = content.strip()
    m = re.search(r'speaker\s*=\s*"?(\w+)"?[^\]]*\]\s*(.+?)(?:</speak>|$)', c, re.S)
    if m and m.group(1).lower() in CREW:
        return m.group(1).lower(), m.group(2).strip().strip('"«»')
    m = re.match(r"\s*\[(\w+)\]\s*[:\-]?\s*(.+)", c, re.S) or re.match(r"\s*(\w+)\s*:\s*(.+)", c, re.S)
    if m and m.group(1).lower() in CREW:
        return m.group(1).lower(), m.group(2).strip().strip('"«»')
    return "xo", c.strip('"«»')


def _patients(state: dict[str, Any]) -> set[str]:
    """The Medbay's occupied beds (their speaker ids)."""
    return {p.get("speaker", "") for p in ((state or {}).get("medbay") or {}).get("patients", [])}


def _diners(state: dict[str, Any]) -> set[str]:
    """The Mess Hall's people while the Captain is there: the diners at their places and the cook (speaker ids)."""
    mess = (state or {}).get("mess") or {}
    return {d.get("speaker", "") for d in mess.get("diners", [])} | ({"mess_cook"} if mess else set())


def _owner(tool: str) -> str:
    return {"set_course": "helm", "set_throttle": "helm", "intercept": "helm", "transit_gate": "helm", "set_alert": "xo", "set_shields": "tactical",
            "route_power": "ops", "set_target": "tactical", "fire_weapons": "tactical", "set_point_defense": "tactical",
            "launch_squadron": "flight", "recall_squadron": "flight", "dispatch_damage_control": "ops", "hail": "comms",
            "set_emcon": "sensors", "active_scan": "sensors", "launch_decoys": "tactical", "holo_display": "sensors", "end_transmission": "comms", "cease_fire": "tactical",
            "fleet_request": "comms", "set_radiators": "engineering", "vent_heat": "engineering",
            "dismiss_visitor": "captain", "abandon_ship": "xo"}.get(tool, "xo")


def _fallback_line(lang: str) -> str:
    return {"it": "Capitano, ho perso un attimo il collegamento con i sistemi. Può ripetere?",
            "es": "Capitán, hemos perdido un momento la conexión con los sistemas. ¿Puede repetir?",
            "de": "Captain, kurze Störung in den Systemen. Bitte wiederholen.",
            "fr": "Capitaine, petite coupure des systèmes. Pouvez-vous répéter ?"}.get(lang, "Captain, we lost the systems link for a moment. Say again?")
