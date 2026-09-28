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
from .tools import ALL_TOOLS, SHIP_TOOL_NAMES, SPEAK

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

    def _trim_history(self) -> None:
        """Keep the last `history_turns` turns (a turn starts at a user message)."""
        starts = [i for i, m in enumerate(self.history) if m["role"] == "user"]
        if len(starts) > self.history_turns:
            self.history = self.history[starts[-self.history_turns]:]

    def _messages(self, text: str, lang: str) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(lang, self.ship.snapshot(), self.ship.recent_events())}]
        msgs += self.history
        msgs.append({"role": "user", "content": f"Captain: {text}"})
        return msgs

    async def handle(self, text: str, lang: str) -> Turn:
        turn = Turn(text=text, lang=lang)
        t0 = time.perf_counter()
        pending: list[tuple[ToolCall, asyncio.Task]] = []

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            if call.name == "speak":
                speaker = args.get("speaker", "xo")
                if speaker not in CREW:
                    speaker = "xo"
                line = (args.get("text") or "").strip()
                if _looks_like_tool(line):
                    log.warning("speak contained a tool invocation, not voiced: %s", line)
                    line = ""
                if len(line) >= 4:
                    if turn.t_first_line is None:
                        turn.t_first_line = time.perf_counter() - t0
                    turn.lines.append((speaker, line))
                    await self.say(speaker, line, lang, args.get("tone", "calm"))
            elif call.name in SHIP_TOOL_NAMES:
                by = _owner(call.name)
                pending.append((call, asyncio.create_task(_safe_execute(self.ship, call.name, args, by))))
            else:
                log.warning("unknown tool %s", call.name)

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
            spk, line = _parse_prose(comp.content)
            turn.lines.append((spk, line))
            await self.say(spk, line, lang, "calm")
        if comp.error:
            turn.error = comp.error
            log.error("LLM error: %s", comp.error)
            await self.say("xo", _fallback_line(lang), lang, "calm")
        # results of the actions (the simulation is the truth)
        failures = []
        for call, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=3.0)
            except asyncio.TimeoutError:
                res = {"ok": False, "detail": "no response from ship systems"}
            turn.actions.append((call.name, call.arguments() or {}, res))
            if not res.get("ok", False):
                failures.append((call, res))
        if failures:
            await self._report_failures(msgs, comp.tool_calls, failures, lang, turn)
        # history in the native tool-calling format: the model keeps answering through tools (a text summary of past
        # turns made it drift into prose after a few turns)
        results = {id(c): r for (c, _), (_, _, r) in zip(pending, turn.actions)}
        calls = [c for c in comp.tool_calls if c.name]
        self.history.append({"role": "user", "content": f"Captain: {text}"})
        if calls:
            self.history.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c.id or f"call_{i}", "type": "function", "function": {"name": c.name, "arguments": c.arguments_raw or "{}"}}
                for i, c in enumerate(calls)]})
            for i, c in enumerate(calls):
                r = results.get(id(c))
                content = "spoken" if c.name == "speak" else (
                    ("ok: " if r and r.get("ok") else "FAILED: ") + str((r or {}).get("detail", "")))
                self.history.append({"role": "tool", "tool_call_id": c.id or f"call_{i}", "content": content})
        else:
            self.history.append({"role": "assistant", "content": " ".join(t for _, t in turn.lines) or "(no reply)"})
        self._trim_history()
        turn.t_end = time.perf_counter() - t0
        self.spent += turn.cost
        return turn

    async def handle_event(self, event: str, lang: str) -> Turn:
        """A ship event (not the Captain): the responsible officer reports it if it is worth saying aloud."""
        turn = Turn(text=f"[event] {event}", lang=lang)
        t0 = time.perf_counter()
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt(lang, self.ship.snapshot(), self.ship.recent_events())}]
        msgs += self.history
        msgs.append({"role": "user", "content": f"[Ship systems event, not the Captain speaking] {event}\n"
                                                "If this deserves telling the Captain now, the responsible officer reports it "
                                                "in one short line with speak (in the Captain's language). Otherwise call no tool."})

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            text = (args.get("text") or "").strip()
            if call.name == "speak" and len(text) >= 4:          # never voice fragments of a cut-off reply
                spk = args.get("speaker") if args.get("speaker") in CREW else "xo"
                turn.lines.append((spk, text))
                if turn.t_first_line is None:
                    turn.t_first_line = time.perf_counter() - t0
                await self.say(spk, text, lang, args.get("tone", "focused"))

        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=[SPEAK], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=320, temperature=0.4, on_tool_call=on_call,
                                   allow_fallbacks=True)
        turn.cost += comp.cost
        if turn.lines:
            self.history.append({"role": "user", "content": f"[event] {event}"})
            self.history.append({"role": "assistant", "content": " ".join(f"{s}: {t}" for s, t in turn.lines)})
            self._trim_history()
        turn.t_end = time.perf_counter() - t0
        self.spent += turn.cost
        return turn

    async def _report_failures(self, msgs, calls, failures, lang, turn: Turn) -> None:
        notes = "\n".join(f"- {c.name}({c.arguments_raw}) FAILED: {r.get('detail', 'unknown')}" for c, r in failures)
        follow = msgs + [
            {"role": "assistant", "content": " ".join(f"[{s}] {t}" for s, t in turn.lines) or "(acknowledged)"},
            {"role": "user", "content": f"[Ship systems report]\n{notes}\nThe responsible officer now tells the Captain "
                                        f"briefly what failed and why, and proposes an alternative if there is one. Use speak."}]

        async def on_call(call: ToolCall) -> None:
            args = call.arguments() or {}
            if call.name == "speak" and args.get("text"):
                spk = args.get("speaker", "xo") if args.get("speaker") in CREW else "xo"
                turn.lines.append((spk, args["text"]))
                await self.say(spk, args["text"], lang, args.get("tone", "focused"))

        comp = await self.llm.chat(model=MODEL, messages=follow, tools=[SPEAK], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=200, temperature=0.4, on_tool_call=on_call,
                                   allow_fallbacks=True)
        turn.cost += comp.cost


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


def _owner(tool: str) -> str:
    return {"set_course": "helm", "set_throttle": "helm", "set_alert": "xo", "set_shields": "tactical",
            "route_power": "ops", "set_target": "tactical", "fire_weapons": "tactical", "set_point_defense": "tactical",
            "launch_squadron": "flight", "recall_squadron": "flight", "dispatch_damage_control": "ops", "hail": "comms",
            "set_emcon": "sensors", "active_scan": "sensors"}.get(tool, "xo")


def _fallback_line(lang: str) -> str:
    return {"it": "Capitano, ho perso un attimo il collegamento con i sistemi. Può ripetere?",
            "es": "Capitán, hemos perdido un momento la conexión con los sistemas. ¿Puede repetir?",
            "de": "Captain, kurze Störung in den Systemen. Bitte wiederholen.",
            "fr": "Capitaine, petite coupure des systèmes. Pouvez-vous répéter ?"}.get(lang, "Captain, we lost the systems link for a moment. Say again?")
