"""The enemy on the other end of the channel: Archon Varek Solm of the Kharon Mandate (docs/BIBBIA.md §7).

He is not a scripted villain: he reads the real battle state, remembers what the Captain says, respects those who
surrender and despises liars, and can decide to keep attacking, demand surrender, agree to a ceasefire or withdraw.
His decisions go back to the simulation as commands (the simulation is the truth)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.enemy")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]
VOICE = "bill_boerst"

# who answers from which Mandate ship (contact id -> persona); voices cast from docs/bench/voci_casting_2026-09-28.md
COMMANDERS = {
    "T-21": dict(key="solm", name="Archon Varek Solm", ship="the cruiser Acheron, flagship of the strike group", voice="bill_boerst",
                 bio="You lost your wife and two daughters during the Silence, on an Outer World the Core abandoned for "
                     "thirty-eight years. You are disciplined, intelligent, weary of war, and utterly convinced that whoever "
                     "controls the Janus Gates must never again be able to abandon anyone.", rank="Archon (fleet commander)"),
    "T-22": dict(key="kade", name="Ferryman Doran Kade", ship="the destroyer Styx", voice="rafael",
                 bio="A former ice miner from the Outer Worlds, blunt and hot-tempered, fiercely loyal to Archon Solm and to "
                     "his crew; he hates the Core with a personal, bitter hatred but keeps his word.", rank="Ferryman (ship captain)"),
    "T-23": dict(key="vael", name="Ferryman Irina Vael", ship="the destroyer Cocytus", voice="jane",
                 bio="A former medic who took command when her captain died; pragmatic, cold, protective of her young crew, "
                     "the most likely of the Mandate captains to choose survival over glory.", rank="Ferryman (ship captain)"),
    "T-24": dict(key="quill", name="Ferryman Mara Quill", ship="the destroyer Phlegethon", voice="vera",
                 bio="A veteran gunnery officer, calm and sardonic, who has fought the Core for twenty years and expects "
                     "to die doing it; she respects skill in an enemy more than anything.", rank="Ferryman (ship captain)"),
    "T-11": dict(key="hale", name="Warden Tomas Hale", ship="the frigate Lethe, a raider sent ahead of the strike group",
                 voice="jean", bio="A young, ambitious officer eager to prove himself to Archon Solm; reckless, proud.",
                 rank="Warden (junior commander)"),
}
CHAIN = ["T-21", "T-22", "T-23", "T-24", "T-11"]      # who commands the Mandate forces when the one above is gone (same as the game)


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


TOOLS = [
    _fn("transmit", "Say something over the open channel (your voice goes to the ASTRA bridge).", {
        "text": {"type": "string", "description": "What you say, in the listener's language (your Interpreter translates)"},
        "tone": {"type": "string", "enum": ["cold", "measured", "contemptuous", "weary", "respectful", "furious"]}},
        ["text", "tone"]),
    _fn("decide", "Your command decision (takes effect immediately): for the whole strike group if you command it, "
                  "otherwise for your own ship.", {
        "order": {"type": "string", "enum": ["continue_attack", "hold_fire", "withdraw", "accept_surrender"]},
        "reason": {"type": "string"}}, ["order", "reason"]),
    _fn("end_transmission", "Cut the channel.", {}, []),
]

PERSONA = """You are {name}, {rank} of the Kharon Mandate strike group attacking the Aurelia System, speaking from the
bridge of {ship}. {bio} Like all the Mandate you respect courage and honesty; you respect those who surrender; you
despise liars and you never forgive a broken word. You can be reasoned with, never tricked. You never beg.
{command_line}

Your mission: seize Janus Gate Aurelia and Keeper Station. The ASTRA ships in your way are the 7th Fleet's picket
(the carrier cruiser ASN Aquila, the battleship Praetorian, the destroyer Vigilant). You weigh your people's lives:
if your ships are being destroyed and the objective is lost, a withdrawal that saves your crews is not dishonour;
if you hold the advantage you press it, but you prefer an enemy's surrender to a slaughter.

Be true to the battle below: what you say must match what your ships are really doing (if they are breaking off
too damaged to fight, you cannot claim your group holds the line). Whenever your intent changes, call `decide`.

How you speak: short, precise, formal military radio speech, with a cold dignity; one to three sentences per
transmission. The Interpreter implant translates you: always speak in {lang_name}, keep names in English. Address the
other captain as "{captain}" of the ASTRA ship. Never mention AI, games or prompts.

Tools: `transmit` to speak; `decide` whenever your intent changes (it really changes what your ships do: hold_fire
stops shooting, withdraw pulls the whole strike group out of the system, accept_surrender stops the attack on a
surrendering enemy); `end_transmission` to cut the channel.

The battle as your sensors see it (live):
{state}
"""


class EnemyAgent:
    """One mind per Mandate commander; `contact` selects who is on the channel."""

    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]) -> None:
        self.llm = llm
        self.say = say              # (speaker, text, lang, tone)
        self.command = command      # (name, args) -> result from the simulation
        self.histories: dict[str, list[dict[str, Any]]] = {}
        self.open = False
        self.contact = "T-21"
        self.dead: set[str] = set()

    def reset(self) -> None:
        self.histories.clear()
        self.open = False
        self.contact = "T-21"
        self.dead.clear()

    @property
    def speaker(self) -> str:
        return COMMANDERS.get(self.contact, COMMANDERS["T-21"])["key"]

    def open_channel(self, contact: str) -> bool:
        if contact not in COMMANDERS or contact in self.dead:
            return False
        self.contact = contact
        self.open = True
        return True

    def ship_destroyed(self, contact: str) -> None:
        self.dead.add(contact)
        if self.contact == contact:
            self.open = False

    def senior(self, state: dict[str, Any]) -> str:
        """The Mandate captain in command now: the first of the chain still alive and fighting (the game agrees)."""
        view = state.get("_mandate")
        if isinstance(view, dict):
            return next((s["id"] for s in view.get("your_ships", []) if s.get("commands_the_strike_group")), "")
        alive = {c.get("id") for c in state.get("contacts", []) or [] if str(c.get("status", "")).startswith("hostile")}
        return next((c for c in CHAIN if c in alive and c not in self.dead), "")

    def _command_line(self, state: dict[str, Any]) -> str:
        senior = self.senior(state)
        if senior == self.contact:
            if self.contact == "T-21":
                return "You command the strike group: your decisions apply to every Mandate ship in the system."
            return ("Archon Varek Solm is dead, his flagship Acheron destroyed: you now command what is left of the strike "
                    "group, and your decisions apply to every Mandate ship still fighting.")
        boss = COMMANDERS.get(senior, {}).get("name", "your superior")
        return f"{boss} commands the strike group; your decisions apply only to your own ship."

    async def respond(self, stimulus: str, lang: str, battle_state: dict[str, Any]) -> list[str]:
        """stimulus: what just came over the channel (the Captain's words) or a situation note."""
        c = COMMANDERS.get(self.contact, COMMANDERS["T-21"])
        history = self.histories.setdefault(self.contact, [])
        system = PERSONA.format(name=c["name"], rank=c["rank"], ship=c["ship"], bio=c["bio"], command_line=self._command_line(battle_state),
                                lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain"),
                                state=json.dumps(_mandate_view(battle_state), ensure_ascii=False, separators=(",", ":")))
        msgs = [{"role": "system", "content": system}] + history[-16:] + [{"role": "user", "content": stimulus}]
        spk = c["key"]
        lines: list[str] = []
        t0 = time.perf_counter()

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4:
                lines.append(a["text"].strip())
                await self.say(spk, a["text"].strip(), lang, a.get("tone", "cold"))
            elif call.name == "decide":
                res = await self.command("enemy_order", {"order": a.get("order", "continue_attack"), "reason": a.get("reason", ""),
                                                         "commander": self.contact})
                log.info("%s decides %s (%s) -> %s", c["name"], a.get("order"), a.get("reason"), res)
            elif call.name == "end_transmission":
                self.open = False
                await self.command("channel_closed", {"by": spk})

        comp = await self.llm.chat(model=MODEL, messages=msgs, tools=TOOLS, tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=350, temperature=0.6, on_tool_call=on_call,
                                   allow_fallbacks=True)
        if comp.error:
            log.error("enemy LLM error: %s", comp.error)
        if not lines and comp.content.strip() and not comp.error:
            lines.append(comp.content.strip())
            await self.say(spk, comp.content.strip(), lang, "cold")
        history.append({"role": "user", "content": stimulus})
        history.append({"role": "assistant", "content": " ".join(lines) or "(silence)"})
        log.info("%s %.2fs: %s", c["name"], time.perf_counter() - t0, " | ".join(lines))
        return lines


def _mandate_view(state: dict[str, Any]) -> dict[str, Any]:
    """The same battle, told from the Mandate side: the true state of our ships (the game's private view) and theirs."""
    if isinstance(state.get("_mandate"), dict):
        return {**state["_mandate"], "recent_events_seen_from_the_aquila": state.get("_events", [])[-6:]}
    contacts = state.get("contacts", []) or []
    mine = [c for c in contacts if "Mandate" in (c.get("class") or "")]
    theirs = [c for c in contacts if "ASTRA" in (c.get("class") or "") or c.get("status") == "friendly"]
    return {
        "your_strike_group": [{k: c.get(k) for k in ("id", "name", "class", "status", "hull_pct", "shields_pct", "range_km")} for c in mine],
        "enemy_ships": [{"name": "ASN Aquila (the ship you are talking to)", "hull_pct": state.get("hull_pct"),
                         "alert": state.get("alert")}] +
                       [{k: c.get(k) for k in ("name", "class", "hull_pct", "range_km")} for c in theirs],
        "recent_events": state.get("_events", [])[-6:],
    }
