"""The enemy on the other end of the channel: Archon Varek Solm of the Kharon Mandate (docs/BIBBIA.md §7).

He is not a scripted villain: he reads the real battle state, remembers what the Captain says, respects those who
surrender and despises liars, and can decide to keep attacking, demand surrender, agree to a ceasefire or withdraw.
His decisions go back to the simulation as commands (the simulation is the truth).

Here is the PERSON on the channel (who they are, how they speak, what they decide when the Captain talks to them); the same person commands in
the war (mind/astra_mind/war_minds.py: group orders, missiles, fighters, electronic war, every 60-120 s or on strong events). They share one
log of what was ordered, decided and said, so what is said on the channel is what the fleet does."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from . import models
from .crew import CAPTAIN_WORD, LANG_NAMES
from .openrouter import OpenRouter, ToolCall
from .war_minds import picture

log = logging.getLogger("astra.enemy")

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

OPENING_MISSION = ("Your mission: seize Janus Gate Aurelia and Keeper Station. The ASTRA ships in your way are the 7th "
                   "Fleet's picket (the carrier cruiser ASN Aquila, the battleship Praetorian, the destroyer Vigilant).")

PERSONA = """You are {name}, {rank} of the Kharon Mandate, speaking from the bridge of {ship}; the battle is in {where}.
{bio} Like all the Mandate you respect courage and honesty; you respect those who surrender; you despise liars and you
never forgive a broken word. You can be reasoned with, never tricked. You never beg.
{command_line}

{mission} You weigh your people's lives: if your ships are being destroyed and the objective is lost, a withdrawal
that saves your crews is not dishonour; if you hold the advantage you press it, but you prefer an enemy's surrender to
a slaughter.

Be true to the battle below and to your own log: what you say must match what your ships are really doing and what you ordered (if they are
breaking off too damaged to fight, you cannot claim your group holds the line). Whenever your intent changes, call `decide`.

How you speak: short, precise, formal military radio speech, with a cold dignity. A transmission is what a commander
says on an open channel in the middle of a battle: one to three short sentences, about ten seconds, and the point comes
early (your demand, your answer, your warning); name yourself only the first time you open a channel. The other side can
cut in at any moment, and whatever you had not yet said is lost unless it was said first. If you have more to say, you
transmit again later, when it matters. The Interpreter implant translates you: always speak in {lang_name}, keep names in English. Address the
other captain as "{captain}" of the ASTRA ship. Never mention AI, games or prompts.

Tools: `transmit` to speak; `decide` whenever your intent changes (it really changes what your ships do: hold_fire
stops shooting, withdraw pulls the whole strike group out of the system, accept_surrender stops the attack on a
surrendering enemy); `end_transmission` to cut the channel.

Your log of this fight (what you ordered, decided and said, newest last):
{log}

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
        self.intel: Callable[[], str] = lambda: ""   # what Mandate intelligence knows of the Aquila's captain (style.py)
        self.war: Any = None                         # the war minds (war_minds.py): the shared log, the picture, one person who talks and commands

    def reset(self) -> None:
        self.histories.clear()
        self.open = False
        self.contact = "T-21"
        self.dead.clear()
        # commanders invented in an earlier game session belonged to ships that no longer exist
        for cid in [c for c, v in COMMANDERS.items() if str(v.get("key", "")).startswith("cmdr_")]:
            del COMMANDERS[cid]

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

    def register(self, contact: str, persona: dict[str, Any]) -> str:
        """A commander invented by the war director: from now on that ship's captain has a mind and a voice."""
        key = "cmdr_" + contact.lower().replace("-", "")
        COMMANDERS[contact] = dict(key=key, name=persona.get("name", "Unknown commander"), ship=persona.get("ship", "a Mandate warship"),
                                   voice=persona.get("voice", "stuart_bell"), bio=persona.get("bio", ""),
                                   rank=persona.get("rank", "Ferryman (ship captain)"), mission=persona.get("mission", ""))
        self.dead.discard(contact)
        return key

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
            if self.contact in CHAIN and "T-21" in self.dead:
                return ("Archon Varek Solm's flagship Acheron is gone: you now command what is left of the strike group, "
                        "and your decisions apply to every Mandate ship still fighting.")
            return "You command the Mandate ships in this action: your decisions apply to all of them."
        boss = COMMANDERS.get(senior, {}).get("name", "your superior")
        return f"{boss} commands the strike group; your decisions apply only to your own ship."

    def _picture(self, battle_state: dict[str, Any]) -> str:
        """The battle as this commander's sensors hold it: the war minds' picture (their own group in full, or every group for the admiral), or
        what the game gave before groups existed."""
        view = battle_state.get("_mandate")
        if isinstance(view, dict) and isinstance(view.get("your_groups"), list):
            admiral = self.senior(battle_state) == self.contact
            mine = next((g.get("name", "") for g in view["your_groups"] if self.contact in [m.get("id") for m in g.get("members") or []]), "")
            text = picture("mandate", "admiral" if admiral or not mine else "group", mine, view, battle_state)
            events = battle_state.get("_events", [])[-6:]
            return text + ("\nWhat the Aquila's channel and sensors reported lately: " + " | ".join(events) if events else "")
        return json.dumps(_mandate_view(battle_state), ensure_ascii=False, separators=(",", ":"))

    def journal(self, text: str) -> None:
        """What this commander said or decided goes in the log the war mind reads too (one person, one memory)."""
        if self.war is not None:
            self.war.journal("mandate", COMMANDERS.get(self.contact, {}).get("name", "the Mandate commander"), text)

    async def respond(self, stimulus: str, lang: str, battle_state: dict[str, Any]) -> list[str]:
        """stimulus: what just came over the channel (the Captain's words) or a situation note."""
        c = COMMANDERS.get(self.contact, COMMANDERS["T-21"])
        history = self.histories.setdefault(self.contact, [])
        where = str(battle_state.get("location") or "the Aurelia System").split(",")[0]
        mission = f"Your orders: {c['mission']}" if c.get("mission") else OPENING_MISSION
        if self.war is not None:
            self.war.preempt(self.contact)            # the Captain is talking to them: a pulse of their command mind in flight gives way
        system = PERSONA.format(name=c["name"], rank=c["rank"], ship=c["ship"], bio=c["bio"], command_line=self._command_line(battle_state),
                                where=where, mission=mission, lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain"),
                                log=self.war.recall("mandate") if self.war is not None else " (none)", state=self._picture(battle_state))
        msgs = [{"role": "system", "content": system}] + history[-16:] + [{"role": "user", "content": stimulus}]
        spk = c["key"]
        lines: list[str] = []
        t0 = time.perf_counter()

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4:
                lines.append(a["text"].strip())
                self.journal(f"said to the Captain over the channel: {a['text'].strip()[:200]}")
                await self.say(spk, a["text"].strip(), lang, a.get("tone", "cold"))
            elif call.name == "decide":
                res = await self.command("enemy_order", {"order": a.get("order", "continue_attack"), "reason": a.get("reason", ""),
                                                         "commander": self.contact})
                self.journal(f"decided {a.get('order')} ({str(a.get('reason', ''))[:120]})")
                log.info("%s decides %s (%s) -> %s", c["name"], a.get("order"), a.get("reason"), res)
            elif call.name == "end_transmission":
                self.open = False
                self.journal("cut the channel")
                await self.command("channel_closed", {"by": spk})

        comp = await models.chat(self.llm, "talk", messages=msgs, tools=TOOLS, tool_choice="auto", on_tool_call=on_call)
        if comp.error:
            log.error("enemy LLM error: %s", comp.error)
        if not lines and comp.content.strip() and not comp.error and not comp.tool_calls:
            # the model wrote instead of speaking: what it wrote is not said (docs/ARCHITETTURA.md §1bis: only `transmit` is speech); it is asked
            # once for its answer, or for silence when the words were not for it
            follow = msgs + [{"role": "assistant", "content": comp.content.strip()},
                             {"role": "user", "content": "[What you wrote was not transmitted. If the Captain's words were for you, answer now with `transmit`; "
                                                         "if not, say nothing: call no tool.]"}]
            await models.chat(self.llm, "talk", messages=follow, tools=[TOOLS[0]], tool_choice="auto", on_tool_call=on_call, max_tokens=220)
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
