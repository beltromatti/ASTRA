"""The war director and the voice of the fleet.

The director reads the campaign so far after every engagement (and after every quiet stretch) and decides what happens
next as a concrete beat the simulation can play (raid, distress call, reinforcements, resupply, calm), inventing the new
enemy commanders it needs (they get a mind and a voice on the channel). Vice Admiral Adrian Rourke, commander of the
7th Fleet, delivers the orders over the fleet net and answers when the Aquila calls; he can grant reinforcements or a
resupply when the war allows it. The simulation stays the truth: every beat goes through the game and its result comes
back before anyone talks about it."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable

from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.director")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
ADMIRAL = dict(key="admiral", name="Vice Admiral Adrian Rourke", ship="7th Fleet command", voice="george",
               bio="Commander of the 7th Fleet. Sixty-one, a veteran of the last Gate campaigns before the Silence ended; "
                   "calm, dry, fiercely protective of his captains, allergic to heroics that waste ships. He trusts the "
                   "Aquila's captain and says so rarely.")
COMMANDER_VOICES = ["stuart_bell", "michael", "juergen", "lola", "anna", "paul", "marius"]


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


SHIP = {"type": "object", "properties": {
    "class": {"type": "string", "enum": ["acheron", "styx", "lethe", "vigilant", "praetorian"]},
    "name": {"type": "string", "description": "The ship's name, in English (Mandate ships: rivers and places of the "
                                              "underworld or of the Outer Worlds; ASTRA ships: virtues, eagles, old navy names)"}},
    "required": ["class", "name"]}
COMMANDER = {"type": "object", "properties": {
    "name": {"type": "string"}, "rank": {"type": "string", "description": "e.g. Ferryman (ship captain), Warden, Archon"},
    "bio": {"type": "string", "description": "two sentences: who they are, what drives them, how they talk"}},
    "required": ["name", "rank", "bio"]}

BEAT_TOOL = _fn("start_beat", "The next beat of the war, played by the simulation.", {
    "type": {"type": "string", "enum": ["raid", "distress", "reinforcements", "resupply", "calm"]},
    "delay_s": {"type": "number", "description": "seconds before it happens (raids and distress: 60-300; calm: 90-240)"},
    "bearing_deg": {"type": "number", "description": "true bearing from the Aquila where they appear (0-359)"},
    "range_km": {"type": "number", "description": "distance from the Aquila (raid 20-40, distress 25-45, reinforcements 15-30)"},
    "ships": {"type": "array", "items": SHIP, "description": "raid: the Mandate ships (first = leader); reinforcements: ASTRA ships"},
    "attackers": {"type": "array", "items": SHIP, "description": "distress: the Mandate raiders (styx or lethe)"},
    "ship": {"type": "object", "properties": {"name": {"type": "string"}, "class": {"type": "string"}},
             "description": "distress: the ship calling for help (a Free Guilds freighter)"},
    "hail": {"type": "boolean", "description": "raid: whether the leader opens a channel to the Aquila on arrival"},
    "commander": COMMANDER,
    "hull_pct": {"type": "number", "description": "resupply: hull integrity restored up to this percent"},
    "missiles": {"type": "integer", "description": "resupply: missiles brought aboard"},
    "duration_s": {"type": "number", "description": "resupply: how long it takes (60-300)"},
    "why": {"type": "string", "description": "the story reason, one sentence (for the campaign log)"}},
    ["type", "why"])
TRANSMIT = _fn("transmit", "Vice Admiral Rourke speaks to the Aquila over the fleet net.", {
    "text": {"type": "string", "description": "what he says, in the Captain's language, names in English; 1-3 sentences"}},
    ["text"])

DIRECTOR_PROMPT = """You are the director of a war story that the player lives as the Captain of the ASN Aquila. Decide
the next beat of the war now, like a great showrunner: consequences follow from what happened, tension rises and falls,
and the player's choices matter (spared enemies may come back, negotiated terms may hold or be broken, losses hurt).

{world}

Rules
- Call `start_beat` exactly once, then `transmit` once: Vice Admiral Adrian Rourke (7th Fleet commander) briefs the
  Aquila in {lang_name} about what is coming or what to do now — in character, concrete, without game terms.
- Pacing: after a hard fight (hull below 50% or ships lost) prefer resupply or calm; escalate step by step; a raid is
  1-4 Mandate ships sized to what the Aquila and her escorts can fight; distress calls are Free Guilds freighters hunted
  by 1-2 raiders; reinforcements are 1-2 ASTRA destroyers (vigilant), rarely a battleship.
- A raid or distress MUST include `commander` for its leader: invent a person (English name, rank, a bio with a reason
  to fight and a way of speaking). Recurring characters are welcome when the story justifies it.
- Never reuse the name of a ship that is still on the plot (see contacts) for a new ship.
- Keep the whole thing coherent with the campaign log below and with the live state.

Campaign log (oldest first)
{campaign}

Live state of the Aquila and the battlefield
{state}"""

ADMIRAL_PROMPT = """You are {name}, commander of the ASTRA Navy's 7th Fleet, defending the Aurelia System. {bio}
You are talking with the captain of the ASN Aquila over the fleet net.

{world}

How you speak: short, calm, dry naval radio speech, 1-3 sentences; always in {lang_name}, names in English. Address
the other as "{captain}". Never mention AI, games or prompts.
Tools: `transmit` to speak. If the captain asks for help and the war allows it, you may `grant` reinforcements (one or
two destroyers) or a resupply (a tender that repairs and rearms the Aquila); grant at most once per engagement and say
honestly when you cannot.

Campaign log
{campaign}

Live state
{state}"""

GRANT = _fn("grant", "Send help to the Aquila (the simulation makes it happen).", {
    "kind": {"type": "string", "enum": ["reinforcements", "resupply"]},
    "ships": {"type": "array", "items": SHIP, "description": "reinforcements: 1-2 ASTRA ships"},
    "delay_s": {"type": "number", "description": "arrival in seconds (reinforcements 90-300)"}}, ["kind"])


class Director:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 register: Callable[[str, dict[str, Any]], None]) -> None:
        self.llm = llm
        self.say = say                  # (speaker, text, lang, tone)
        self.command = command          # (name, args) -> result from the game
        self.register = register        # (contact_id, persona) -> the enemy minds learn a new commander
        self.campaign: list[str] = []
        self.busy = False
        self.granted = False
        self.voice_i = 0
        self.admiral_history: list[dict[str, Any]] = []

    def reset(self) -> None:
        self.campaign.clear()
        self.busy = False
        self.granted = False
        self.admiral_history.clear()

    def note(self, text: str) -> None:
        self.campaign.append(text)
        del self.campaign[:-30]

    # ------------------------------------------------------------------------------------------------ the beats
    async def on_event(self, text: str, lang: str, state: dict[str, Any]) -> None:
        """text: 'director: engagement over — ...' or 'director: beat complete — ...' from the game."""
        self.note(text.split(":", 1)[1].strip())
        if "engagement over" in text:
            self.granted = False
        if self.busy:
            return
        self.busy = True
        try:
            await asyncio.sleep(14.0)   # the bridge reports the outcome first
            await self._next_beat(lang, state)
        except Exception:  # noqa: BLE001
            log.exception("director failed")
        finally:
            self.busy = False

    async def _next_beat(self, lang: str, state: dict[str, Any]) -> None:
        t0 = time.perf_counter()
        prompt = DIRECTOR_PROMPT.format(world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                        campaign="\n".join(f"- {c}" for c in self.campaign) or "- (the war has just begun)",
                                        state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":")))
        beat: dict[str, Any] = {}
        speech: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "start_beat" and not beat:
                beat.update(a)
            elif call.name == "transmit" and a.get("text"):
                speech.append(a["text"].strip())

        comp = await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt},
                                                          {"role": "user", "content": "Decide the next beat now."}],
                                   tools=[BEAT_TOOL, TRANSMIT], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=900, temperature=0.8, on_tool_call=on_call,
                                   allow_fallbacks=True)
        if comp.error or not beat:
            log.error("director produced no beat: %s %r", comp.error, comp.content[:200])
            return
        res = await self.command("director_beat", {"beat": {k: v for k, v in beat.items() if k not in ("why", "commander")}})
        log.info("director %.2fs: %s -> %s", time.perf_counter() - t0, json.dumps(beat, ensure_ascii=False)[:400], res)
        if not res.get("ok"):
            self.note(f"(a planned {beat.get('type')} could not happen: {res.get('detail')})")
            return
        self.note(f"beat: {beat.get('type')} — {beat.get('why', '')} ({res.get('detail', '')})")
        # the leader of a raid or of the raiders gets a mind and a voice
        cmd = beat.get("commander") or {}
        ids = _ids(res.get("detail", ""))
        if ids and cmd.get("name") and beat.get("type") in ("raid", "distress"):
            first = (beat.get("ships") or beat.get("attackers") or [{}])[0]
            leader_id = ids[1] if beat.get("type") == "distress" and len(ids) > 1 else ids[0]
            self.register(leader_id, {"name": cmd["name"], "rank": cmd.get("rank", "Ferryman (ship captain)"),
                                      "bio": cmd.get("bio", ""), "ship": f"the {first.get('class', 'warship')} {first.get('name', '')}".strip(),
                                      "voice": COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)]})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads it, aboard {first.get('name', '?')} ({leader_id})")
        for line in speech[:2]:
            await self.say("admiral", line, lang, "measured")
            self.note(f"Rourke to the Aquila: {line}")

    # ------------------------------------------------------------------------------------------- the fleet net
    async def admiral_reply(self, message: str, lang: str, state: dict[str, Any]) -> list[str]:
        """The Aquila hailed the fleet: Rourke answers (and may send help)."""
        prompt = ADMIRAL_PROMPT.format(name=ADMIRAL["name"], bio=ADMIRAL["bio"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                       captain=CAPTAIN_WORD.get(lang, "Captain"),
                                       campaign="\n".join(f"- {c}" for c in self.campaign[-12:]) or "- (the war has just begun)",
                                       state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":")))
        msgs = [{"role": "system", "content": prompt}] + self.admiral_history[-10:] + [
            {"role": "user", "content": f"[The Aquila on the fleet net]: {message}"}]
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4:
                lines.append(a["text"].strip())
                await self.say("admiral", a["text"].strip(), lang, "measured")
            elif call.name == "grant" and not self.granted:
                self.granted = True
                kind = a.get("kind", "resupply")
                beat = {"type": kind, "delay_s": a.get("delay_s", 150), "granted": True}
                if kind == "reinforcements":
                    ships = a.get("ships") or [{"class": "vigilant", "name": "ASN Resolute"}]
                    beat.update(ships=ships[:2], bearing_deg=(state.get("heading_deg", 0) + 180) % 360, range_km=20)
                else:
                    beat.update(hull_pct=85, missiles=24, duration_s=150)
                res = await self.command("director_beat", {"beat": beat})
                self.note(f"Rourke granted {kind}: {res.get('detail', '')}")
                log.info("admiral grants %s -> %s", kind, res)

        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=[TRANSMIT, GRANT], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=400, temperature=0.6, on_tool_call=on_call,
                                   allow_fallbacks=True)
        if not lines and comp.content.strip() and not comp.error:
            lines.append(comp.content.strip())
            await self.say("admiral", lines[0], lang, "measured")
        self.admiral_history += [{"role": "user", "content": f"[The Aquila on the fleet net]: {message}"},
                                 {"role": "assistant", "content": " ".join(lines) or "(no answer)"}]
        for line in lines:
            self.note(f"Rourke to the Aquila: {line}")
        return lines


def _ids(detail: str) -> list[str]:
    import re
    return re.findall(r"T-\d+", detail)


def _brief(state: dict[str, Any]) -> dict[str, Any]:
    """What the director and the admiral need of the live state (compact)."""
    keep = ("alert", "hull_pct", "shields", "weapons", "squadrons", "damage_control", "heading_deg", "speed_mps")
    out = {k: state.get(k) for k in keep if k in state}
    out["contacts"] = [{k: c.get(k) for k in ("id", "name", "class", "status", "range_km", "bearing_deg", "hull_pct")}
                       for c in state.get("contacts", []) or []]
    out["recent_events"] = state.get("_events", [])[-8:]
    return out
