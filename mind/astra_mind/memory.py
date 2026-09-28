"""What each officer remembers of the Captain.

Every few exchanges the memory keeper reads what was said aboard (the Captain's words, the officers' answers) and keeps
what an officer would still remember weeks later: something personal the Captain shared (a family, a home, a past, a
fear), a promise the Captain made — or broke —, a confidence an officer made and how the Captain took it, a moment that
marked them (a kindness, a humiliation, a joke that stuck). Routine orders and reports are never kept. The memories are
saved with the story; the crew's prompt carries them, so an officer can bring up the Captain's sister a month later, or
remind the Captain of a promise. Promises also reach the story (the director weighs them, the finale remembers them)."""
from __future__ import annotations

import logging
from typing import Any, Callable

from .crew import CREW
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.memory")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
PER_OFFICER = 14
EVERY = 8                 # lines heard between two readings

REMEMBER = {"type": "function", "function": {"name": "remember", "description": "One lasting memory an officer keeps.",
            "parameters": {"type": "object", "properties": {
                "officer": {"type": "string", "enum": list(CREW)},
                "kind": {"type": "string", "enum": ["personal", "promise", "confidence", "moment"]},
                "memory": {"type": "string", "description": "in English, in the third person about the officer, one short "
                                                           "sentence (under 35 words), the Captain named each time: 'Ferri "
                                                           "knows the Captain's brother flies Falcons with the Third Fleet; the "
                                                           "Captain thinks of him at every launch'"}},
                "required": ["officer", "kind", "memory"]}}}
NOTHING = {"type": "function", "function": {"name": "nothing", "description": "Nothing said here is worth remembering.",
           "parameters": {"type": "object", "properties": {}}}}

PROMPT = """You keep the memories of the officers of the ASN Aquila. Below is what was just said aboard: the Captain's words
and the officers' (ids: {ids}).

What they remember already (do not repeat it):
{known}

What was said:
{said}

Keep only what an officer would still remember weeks from now, about the Captain and their bond: something personal the
Captain shared (family, home, past, beliefs, fears), a promise the Captain made to them or to the crew (or broke), a
confidence the officer made and how the Captain received it, a moment that marked them (a kindness, a harsh word, a joke
that stuck, being trusted or overruled on something that mattered to them). Never routine orders, reports or numbers.
A memory belongs to the officer who lived it (the one spoken to, or present and affected). One `remember` call per
memory; if nothing lasting was said, call `nothing`. Write it in the third person about the officer, so nobody can
mistake whose it is: the Captain's gender is not known, so name the Captain every time and never use "their" for the
Captain's people or things ("Ferri knows the Captain's brother flies Falcons with the Third Fleet", not "their
brother", not "my brother")."""


class MemoryKeeper:
    def __init__(self, llm: OpenRouter, store: dict[str, list[dict[str, str]]], note: Callable[[str], None]) -> None:
        self.llm = llm
        self.store = store               # officer id -> [{kind, memory}] (the director saves it with the story)
        self.note = note                 # promises reach the story
        self.heard: list[str] = []
        self.busy = False

    def hear(self, who: str, text: str) -> None:
        t = (text or "").strip()
        if t:
            self.heard = (self.heard + [f"{who}: {t}"])[-40:]

    def lines(self) -> str:
        """For the crew's prompt: what each officer remembers."""
        out = []
        for oid, mems in self.store.items():
            if oid in CREW and mems:
                out.append(f"- {CREW[oid].name} ({oid}): " + " / ".join(m["memory"] for m in mems[-8:]))
        return "\n".join(out)

    async def maybe_read(self, force: bool = False) -> None:
        if self.busy or (len(self.heard) < EVERY and not (force and self.heard)):
            return
        if not any(line.startswith("Captain:") for line in self.heard):
            self.heard.clear()            # the officers talked among themselves: nothing of the Captain's to keep
            return
        self.busy = True
        said, self.heard = self.heard, []
        try:
            await self._read(said)
        except Exception:  # noqa: BLE001
            log.exception("memory reading failed")
        finally:
            self.busy = False

    async def _read(self, said: list[str]) -> None:
        known = "\n".join(f"- {oid}: " + " / ".join(m["memory"] for m in mems) for oid, mems in self.store.items() if mems) or "(nothing yet)"
        kept: list[dict[str, Any]] = []

        async def on_call(call: ToolCall) -> None:
            if call.name == "remember":
                a = call.arguments() or {}
                if a.get("officer") in CREW and (a.get("memory") or "").strip():
                    kept.append(a)

        await self.llm.chat(model=MODEL, messages=[
            {"role": "system", "content": PROMPT.format(ids=", ".join(f"{k} = {o.title}" for k, o in CREW.items()), known=known,
                                                        said="\n".join(said))},
            {"role": "user", "content": "Keep what lasts."}],
            tools=[REMEMBER, NOTHING], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=500,
            temperature=0.3, on_tool_call=on_call, allow_fallbacks=True)
        for a in kept[:6]:
            oid, kind, mem = a["officer"], a.get("kind", "moment"), a["memory"].strip()[:400]
            mems = self.store.setdefault(oid, [])
            if any(m["memory"].lower() == mem.lower() for m in mems):
                continue
            mems.append({"kind": kind, "memory": mem})
            # the oldest go first, but a promise is kept until it is the only kind left
            while len(mems) > PER_OFFICER:
                drop = next((i for i, m in enumerate(mems) if m["kind"] != "promise"), 0)
                mems.pop(drop)
            log.info("memory %s (%s): %s", oid, kind, mem)
            if kind == "promise":
                self.note(f"promise: {mem} ({CREW[oid].name})")
