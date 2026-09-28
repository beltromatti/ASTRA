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
import os
import re as _re
import time
from typing import Any, Awaitable, Callable

from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall
from .war import OWNERS, WarMap

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
    "bio": {"type": "string", "description": "two sentences: who they are, what drives them, how they talk"},
    "orders": {"type": "string", "description": "their mission here, as the Mandate gave it to them (one sentence)"}},
    "required": ["name", "rank", "bio", "orders"]}

POI = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["listening_post", "derelict_warship", "derelict_freighter"]},
    "name": {"type": "string", "description": "e.g. Thule Watch, the freighter Silver Kestrel, ASN Resolve"}}, "required": ["kind", "name"]}
BEAT_TOOL = _fn("start_beat", "The next beat of the war, played by the simulation.", {
    "type": {"type": "string", "enum": ["raid", "distress", "reinforcements", "resupply", "calm", "transit", "investigate", "decisive"]},
    "act": {"type": "integer", "minimum": 1, "maximum": 3, "description": "the act of the arc this beat belongs to: the current "
            "one, or the next when this beat is the story's turning point into it"},
    "allies": {"type": "array", "items": SHIP, "description": "decisive: the ASTRA ships that join the Aquila for it (1-3)"},
    "poi": {**POI, "description": "investigate: the place to search (on the plot at once, dark and tumbling)"},
    "findings": {"type": "array", "items": {"type": "string"}, "description": "investigate: what the crew learns there, in "
                 "order — 1) the active scan, 2) a flight group reaches it or the Aquila closes in, 3) alongside. Concrete "
                 "facts in English (what happened, who, a clue that moves the story), 1-3 items"},
    "ambush": {"type": "array", "items": SHIP, "description": "investigate (optional): Mandate ships lying cold near it, "
               "waking when the Aquila comes within ambush_km"},
    "ambush_km": {"type": "number", "description": "investigate: how close the Aquila must come before the ambush springs"},
    "delay_s": {"type": "number", "description": "seconds before it happens (raids and distress: 60-300; calm: 90-240)"},
    "bearing_deg": {"type": "number", "description": "true bearing from the Aquila where they appear (0-359)"},
    "range_km": {"type": "number", "description": "distance from the Aquila (raid 20-40, distress 25-45, reinforcements 15-30)"},
    "ships": {"type": "array", "items": SHIP, "description": "raid: the Mandate ships (first = leader); reinforcements: ASTRA ships; "
              "decisive: the Mandate's main fleet (4-8 ships, the leader first, an acheron among them)"},
    "attackers": {"type": "array", "items": SHIP, "description": "distress: the Mandate raiders (styx or lethe)"},
    "ship": {"type": "object", "properties": {"name": {"type": "string"}, "class": {"type": "string"}},
             "description": "distress: the ship calling for help (a Free Guilds freighter)"},
    "hail": {"type": "boolean", "description": "raid: whether the leader opens a channel to the Aquila on arrival"},
    "commander": COMMANDER,
    "hull_pct": {"type": "number", "description": "resupply: hull integrity restored up to this percent"},
    "missiles": {"type": "integer", "description": "resupply: missiles brought aboard"},
    "duration_s": {"type": "number", "description": "resupply: how long it takes (60-300)"},
    "system_name": {"type": "string", "description": "transit: the system Fleet sends the Aquila to — one the gate here reaches"},
    "why": {"type": "string", "description": "the story reason, one sentence (for the campaign log)"},
    "officers": {"type": "object", "additionalProperties": {"type": "string"},
                 "description": "only for officers whose bond with the Captain changed because of what happened (keys: "
                 "xo Serra she, helm Ferri he, ops Tanaka she, tactical Voss she, comms Martin he, sensors Nair she, "
                 "engineering Mensah he, chief Okonkwo he, doctor Lindqvist she, flight Price he): one sentence in English — "
                 "how they now see the Captain and why (trust earned or lost, loyalty, doubt about an order, resentment, "
                 "admiration, a debt), and what they carry. Omit everyone else: their bond carries over"},
    "crew_mood": {"type": "string", "description": "how the Aquila's bridge crew feels now and why, in English, 1-2 "
                  "sentences naming officers where it matters (Serra XO she, Ferri helm he, Tanaka ops she, Voss tactical "
                  "she, Martin comms he, Nair sensors she, Mensah engineering he, Price flight he, Chief Okonkwo he, Dr. "
                  "Lindqvist she): grief for the fallen, pride, fatigue, anger, "
                  "doubt about an order, hope. It colours how they speak until the next beat"}},
    ["type", "why", "crew_mood"])
WAR_NEWS = _fn("war_news", "Something happens elsewhere in the March, and the fleet net reports it (the crew hears it). "
                           "It may change who holds a system or how threatened it is. Use it to keep the war alive "
                           "beyond the Aquila: consequences of her victories and failures, the enemy's moves, the "
                           "other fleets. At most one per beat.", {
    "text": {"type": "string", "description": "the news as the fleet net says it, in English, one or two sentences"},
    "system": {"type": "string", "description": "the system concerned (a name from the March)"},
    "owner": {"type": "string", "enum": list(OWNERS), "description": "who holds it now, if that changed"},
    "threat": {"type": "integer", "minimum": 0, "maximum": 3, "description": "0 quiet, 1 raids, 2 under attack, 3 front line"}},
    ["text", "system"])
TRANSMIT = _fn("transmit", "Vice Admiral Rourke speaks to the Aquila over the fleet net.", {
    "text": {"type": "string", "description": "what he says, in the Captain's language, names in English; 1-3 sentences"}},
    ["text"])

DIRECTOR_PROMPT = """You are the director of a war story that the player lives as the Captain of the ASN Aquila. Decide
the next beat of the war now, like a great showrunner: consequences follow from what happened, tension rises and falls,
and the player's choices matter (spared enemies may come back, negotiated terms may hold or be broken, losses hurt).

{world}

Rules
- Call `start_beat` exactly once, `war_news` at most once, and ALWAYS `transmit` once: Vice Admiral Adrian Rourke
  (7th Fleet commander) briefs the Aquila in {lang_name} about what is coming or what to do now — in character,
  concrete, without game terms.
- Pacing: after a hard fight (hull below 50% or ships lost) prefer resupply or calm; escalate step by step; a raid is
  1-4 Mandate ships sized to what the Aquila and her escorts can fight; distress calls are Free Guilds freighters hunted
  by 1-2 raiders; reinforcements are 1-2 ASTRA destroyers (vigilant), rarely a battleship.
- decisive: the battle this arc was building to (Act III only, once the forces are gathered): the Mandate's main
  fleet in `ships` (4-8, an acheron leading) against the Aquila and the `allies` that join her (1-3 ASTRA ships), where
  the Aquila is and where the arc says it must be fought (the Mandate's assault on Aurelia, or the 7th Fleet's strike
  at Erebus Anchorage...). It MUST include `commander`. Its outcome ends the arc.
- A raid or distress MUST include `commander` for its leader: invent a person (English name, rank, a bio with a reason
  to fight and a way of speaking). Recurring characters are welcome when the story justifies it.
- Never reuse the name of a ship that is still on the plot (see contacts) for a new ship.
- transit: Fleet orders the Aquila through the Janus Gate to another system of the March (Keeper Station tunes the
  gate; the Captain decides when to go, and the war goes on wherever the Aquila is). Only a system the gate here
  reaches (see the map). The right beat when the story moves elsewhere: the enemy regroups beyond the gate, another
  front needs her, a system calls for help. Not right after arriving. The Captain may also take the ship through the
  gate on their own: the log says so, and the story follows them.
- Raids, distress calls and reinforcements happen where the Aquila is, and must make sense there (who holds the
  system, who could reach it through its gates).
- investigate: a place to search where the Aquila is — a silent station, a drifting warship, a dead freighter. Its
  findings are the story: what happened there, who did it, a clue that leads on (logs, survivors, a Mandate code, a
  course). An ambush lying cold around it is possible, not mandatory. A raid or distress there must include `commander`;
  for an ambush, give `commander` for its first ship.
- The war is bigger than the Aquila: `war_news` moves it elsewhere (systems fall or are retaken, fronts shift) as a
  consequence of what happened and of the enemy's plans. Mandate ships never appear deep in ASTRA space without a
  reason (a gate they hold, a breakthrough reported first).
- If the Captain has not acted on Fleet's orders for a long while, Rourke may press them, or the war may come to them.
- `crew_mood`: the people aboard live this war. Losses (the casualties in the live state), close calls, victories,
  the Captain's choices (mercy, ruthlessness, retreats, promises kept or broken) and long waits change how the crew
  feels; carry it from beat to beat and let it evolve (the mood before this beat: {mood}).
- `officers`: each officer has a bond with the Captain (below). The Captain's choices move it — an order that cost
  lives, mercy or ruthlessness, trusting an officer's advice or overruling it, visiting the wounded in the Medbay or
  going down to Main Engineering, keeping or breaking a promise. Change a bond only when something happened that would
  change it, and keep it human and specific (Voss knows the Mandate: overruling her about them stings; Okonkwo
  respects a captain who asks before pushing his reactor; Lindqvist judges by how the Captain treats the wounded).
  Where each officer stands now: {bonds}
- The Captain's own log entries ("captain's log: …" in the campaign log) are the player telling you what they
  think, fear and want: let the story answer them (a suspicion confirmed or proven wrong, a hope rewarded or tested).
- Keep the whole thing coherent with the map, the campaign log below and the live state.

The shape of the story (arc {arc} of the war)
{arc_text}

The Aurelia March (the sector at war; each system's Janus Gate is bound to the ones in brackets)
{war}

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

The Aurelia March
{war}

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
                 register: Callable[[str, dict[str, Any]], None],
                 news: Callable[[str], Awaitable[None]] | None = None, war: WarMap | None = None) -> None:
        self.llm = llm
        self.war = war or WarMap()
        self.announce = news              # (text) -> the fleet net reports it on the bridge
        self.say = say                  # (speaker, text, lang, tone)
        self.command = command          # (name, args) -> result from the game
        self.register = register        # (contact_id, persona) -> the enemy minds learn a new commander
        self.campaign: list[str] = []
        self.busy = False
        self.granted = False
        self.voice_i = 0
        self.admiral_history: list[dict[str, Any]] = []
        self.last_event_t = time.monotonic()   # the last time the story moved (a director event or a beat)
        self.mood = ""                          # how the bridge crew feels (the director's latest word on it)
        self.bonds: dict[str, str] = {}          # officer id -> how they stand with the Captain (the director keeps it)
        self.arc = 1                             # the arcs of the war: three acts each, ending in a decisive battle
        self.act = 1
        self.act_beats = 0
        self.decisive = False                    # the decisive battle is being fought
        self.finale = None                       # the arc's ending (finale.Finale, set by the server)
        self.standing: list[dict[str, str]] = []   # the Captain's standing orders (shared with the bridge agent)

    def reset(self) -> None:
        """A new campaign: the war begins again at Aurelia."""
        self.war.reset()
        self.war.save()
        self.campaign.clear()
        self.mood = ""
        self.bonds = {}
        self.standing.clear()
        self.arc, self.act, self.act_beats, self.decisive = 1, 1, 0, False
        self.busy = False
        self.granted = False
        self.admiral_history.clear()
        self.last_event_t = time.monotonic()
        self.save()

    def load(self, note: str = "") -> bool:
        """Continue the saved campaign: the war map and the story so far (note: what happened meanwhile)."""
        ok = self.war.load()
        try:
            with open(self._story_path(), encoding="utf-8") as f:
                d = json.load(f)
            self.campaign[:] = d.get("campaign", [])[-30:]
            self.voice_i = int(d.get("voice_i", 0))
            self.mood = str(d.get("mood", ""))
            self.bonds = {str(k): str(v) for k, v in (d.get("bonds") or {}).items()}
            self.standing[:] = [o for o in (d.get("standing") or []) if isinstance(o, dict) and o.get("department") and o.get("order")]
            self.arc, self.act = int(d.get("arc", 1)), int(d.get("act", 1))
            self.act_beats, self.decisive = int(d.get("act_beats", 0)), bool(d.get("decisive", False))
        except (OSError, ValueError):
            self.campaign.clear()
            self.mood = ""
            self.bonds = {}
        self.busy = False
        self.granted = False
        self.admiral_history.clear()
        self.last_event_t = time.monotonic()
        self.note(note or "the Captain returned to the bridge after a watch change; the war went on")
        return ok

    def _story_path(self) -> str:
        return os.path.join(os.path.dirname(self.war.save_path), "story.json")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._story_path()), exist_ok=True)
            tmp = self._story_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"campaign": self.campaign, "voice_i": self.voice_i, "mood": self.mood, "bonds": self.bonds,
                           "standing": self.standing, "arc": self.arc, "act": self.act, "act_beats": self.act_beats,
                           "decisive": self.decisive}, f,
                          ensure_ascii=False, indent=1)
            os.replace(tmp, self._story_path())
        except OSError:
            log.exception("could not save the story")

    ACTS = {1: "Act I — the storm gathers: the Mandate tests the March (raids, a silence to investigate, a distress call); "
               "the enemy's plan shows itself piece by piece; the Captain earns the crew. About 4-6 beats, then a turning "
               "point opens Act II (a system falls, a plan is uncovered, a blow lands).",
            2: "Act II — the March burns: the offensive in the open; systems change hands on the fleet net; the Aquila goes "
               "where she is needed (gates), meets again the commanders she spared or wronged; losses and choices pile up. "
               "About 6-10 beats, then a turning point opens Act III.",
            3: "Act III — the gate: both sides gather for the decisive battle (the Mandate's assault on Aurelia, or the 7th "
               "Fleet's strike at Erebus Anchorage: whichever the war map and the Captain's choices make right). Two or three "
               "beats of gathering (reinforcements, resupply, a last intelligence), then the `decisive` beat. Its outcome "
               "ends the arc."}

    def arc_text(self) -> str:
        return (f"{self.ACTS[1]}\n{self.ACTS[2]}\n{self.ACTS[3]}\nNOW: Act {self.act}, {self.act_beats} beat(s) into it"
                + (" — the decisive battle is being fought" if self.decisive else "")
                + (f". (This is arc {self.arc}: the war went on after the earlier arcs, see the campaign log.)" if self.arc > 1 else "."))

    def note(self, text: str) -> None:
        self.campaign.append(text)
        del self.campaign[:-30]
        self.save()

    def bonds_lines(self) -> list[str]:
        """Where each officer stands with the Captain (for the crew and the director)."""
        from .crew import CREW
        return [f"{CREW[k].name} ({k}): {v}" for k, v in self.bonds.items() if k in CREW]

    # ------------------------------------------------------------------------------------------------ the beats
    async def on_event(self, text: str, lang: str, state: dict[str, Any]) -> None:
        """text: 'director: engagement over — ...', 'director: beat complete — ...' (the game) or 'director: story stalled — ...'."""
        self.last_event_t = time.monotonic()
        self.note(text.split(":", 1)[1].strip())
        arrived = _re.search(r"transit from .+? into the (.+?) system", text)
        if arrived:
            self.war.arrived(arrived.group(1))
        if "engagement over" in text:
            self.granted = False
            if self.decisive and self.finale is not None:
                self.decisive = False
                self.save()
                asyncio.create_task(self._end_arc(text, lang, state))
                return
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
        prompt = DIRECTOR_PROMPT.format(world=WORLD, lang_name=LANG_NAMES.get(lang, lang), war=self.war.brief(),
                                        arc=self.arc, arc_text=self.arc_text(),
                                        mood=self.mood or "not yet set: the patrol has just begun",
                                        bonds="; ".join(self.bonds_lines()) or "(nothing yet: a new ship, a new crew, a new captain)",
                                        campaign="\n".join(f"- {c}" for c in self.campaign) or "- (the war has just begun)",
                                        state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":")))
        beat: dict[str, Any] = {}
        speech: list[str] = []
        news: list[dict[str, Any]] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "start_beat" and not beat:
                beat.update(a)
            elif call.name == "transmit" and a.get("text"):
                speech.append(a["text"].strip())
            elif call.name == "war_news" and a.get("text") and not news:
                news.append(a)

        comp = await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt},
                                                          {"role": "user", "content": "Decide the next beat now."}],
                                   tools=[BEAT_TOOL, WAR_NEWS, TRANSMIT], tool_choice="auto", providers=PROVIDERS,
                                   reasoning={"enabled": False}, max_tokens=900, temperature=0.8, on_tool_call=on_call,
                                   allow_fallbacks=True)
        for n in news:   # the war elsewhere moves first: the beat may follow from it
            changed = self.war.update(n.get("system", ""), n.get("owner"), n.get("threat"), n["text"])
            self.war.add_news(n["text"])
            self.note(f"war news: {n['text']} ({changed})")
            if self.announce:
                await self.announce(n["text"])
        if comp.error or not beat:
            log.error("director produced no beat: %s %r", comp.error, comp.content[:200])
            return
        bonds = beat.pop("officers", None) or {}
        if isinstance(bonds, dict) and bonds:
            from .crew import CREW
            for k, v in bonds.items():
                if k in CREW and isinstance(v, str) and v.strip():
                    self.bonds[k] = v.strip()[:300]
                    log.info("bond %s: %s", k, self.bonds[k])
            self.save()
        mood = (beat.pop("crew_mood", "") or "").strip()
        if mood:
            self.mood = mood[:400]
            log.info("crew mood: %s", self.mood)
            self.save()
        try:
            act = int(beat.pop("act", self.act) or self.act)
        except (TypeError, ValueError):
            act = self.act
        if act > self.act and act <= 3:
            self.act, self.act_beats = act, 0
            self.note(f"ACT {'I' * act if act < 3 else 'III'} of arc {self.arc} begins: {beat.get('why', '')}")
            log.info("act %d begins", act)
        self.act_beats += 1
        if beat.get("type") == "decisive":
            return await self._decisive(beat, lang, state, t0)
        if beat.get("type") == "transit":
            dest = self.war.find(beat.get("system_name", ""))
            if not dest or not self.war.linked(self.war.current, dest):
                self.note(f"(a transit to {beat.get('system_name')} was impossible: the gate in {self.war.current} "
                          f"reaches only {', '.join(self.war.links.get(self.war.current, []))})")
                log.warning("director asked for an unreachable transit: %s", beat.get("system_name"))
                return
            s = self.war.systems[dest]
            beat.update(system_name=dest, star_class=s["star"], planet_type=s["planet"], planet_name=s["world"])
        res = await self.command("director_beat", {"beat": {k: v for k, v in beat.items() if k not in ("why", "commander")}})
        log.info("director %.2fs: %s -> %s", time.perf_counter() - t0, json.dumps(beat, ensure_ascii=False)[:400], res)
        if not res.get("ok"):
            self.note(f"(a planned {beat.get('type')} could not happen: {res.get('detail')})")
            return
        self.note(f"beat: {beat.get('type')} — {beat.get('why', '')} ({res.get('detail', '')})")
        # the leader of a raid or of the raiders gets a mind and a voice
        cmd = beat.get("commander") or {}
        ids = _ids(res.get("detail", ""))
        if ids and cmd.get("name") and beat.get("type") in ("raid", "distress", "investigate") and (beat.get("type") != "investigate" or len(ids) > 1):
            first = (beat.get("ships") or beat.get("attackers") or beat.get("ambush") or [{}])[0]
            leader_id = ids[1] if beat.get("type") in ("distress", "investigate") and len(ids) > 1 else ids[0]
            self.register(leader_id, {"name": cmd["name"], "rank": cmd.get("rank", "Ferryman (ship captain)"),
                                      "bio": cmd.get("bio", ""), "ship": f"the {first.get('class', 'warship')} {first.get('name', '')}".strip(),
                                      "voice": COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)],
                                      "mission": cmd.get("orders") or beat.get("why", "")})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads it, aboard {first.get('name', '?')} ({leader_id})")
        if not speech and beat.get("type") in ("transit", "raid", "distress", "reinforcements", "investigate"):
            speech = await self._brief_line(beat, res.get("detail", ""), lang, state)
        for line in speech[:2]:
            await self.say("admiral", line, lang, "measured")
            self.note(f"Rourke to the Aquila: {line}")

    async def _decisive(self, beat: dict[str, Any], lang: str, state: dict[str, Any], t0: float) -> None:
        """The battle the arc was building to: the allies join the Aquila, then the Mandate's main fleet comes."""
        on_plot = {str(c.get("name") or "").lower() for c in (state or {}).get("contacts", []) or []}
        allies = [a for a in (beat.get("allies") or []) if not any(str(a.get("name", "")).lower() in n for n in on_plot if n)]
        if allies:
            res = await self.command("director_beat", {"beat": {"type": "reinforcements", "ships": allies[:3], "granted": True,
                                                                 "bearing_deg": (float(beat.get("bearing_deg", 90)) + 180) % 360,
                                                                 "range_km": 12, "why": "the fleet gathers for the decisive battle"}})
            log.info("decisive: allies -> %s", res)
        raid = {k: v for k, v in beat.items() if k not in ("why", "commander", "allies")}
        try:
            rng = float(beat.get("range_km", 40))
        except (TypeError, ValueError):
            rng = 40.0
        raid.update(type="raid", ships=(beat.get("ships") or [])[:8], hail=True, range_km=min(max(rng, 25.0), 50.0))
        res = await self.command("director_beat", {"beat": raid})
        log.info("director %.2fs: DECISIVE %s -> %s", time.perf_counter() - t0, json.dumps(beat, ensure_ascii=False)[:400], res)
        if not res.get("ok"):
            self.note(f"(the decisive battle could not begin: {res.get('detail')})")
            return
        self.decisive = True
        self.note(f"THE DECISIVE BATTLE of arc {self.arc}: {beat.get('why', '')} ({res.get('detail', '')})")
        cmd = beat.get("commander") or {}
        ids = _ids(res.get("detail", ""))
        if ids and cmd.get("name"):
            first = (beat.get("ships") or [{}])[0]
            self.register(ids[0], {"name": cmd["name"], "rank": cmd.get("rank", "Archon"), "bio": cmd.get("bio", ""),
                                   "ship": f"the {first.get('class', 'warship')} {first.get('name', '')}".strip(),
                                   "voice": COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)],
                                   "mission": cmd.get("orders") or beat.get("why", "")})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads the Mandate's fleet, aboard {first.get('name', '?')} ({ids[0]})")
        for line in (await self._brief_line(beat, res.get("detail", ""), lang, state))[:2]:
            await self.say("admiral", line, lang, "measured")
            self.note(f"Rourke to the Aquila: {line}")

    async def _end_arc(self, result: str, lang: str, state: dict[str, Any]) -> None:
        """The decisive battle is over: the arc's ending is told, then a new arc begins."""
        self.busy = True
        try:
            await asyncio.sleep(16.0)                   # the bridge reports the outcome first
            await self.finale.run(self, result.split(":", 1)[-1].strip(), lang)
            self.arc, self.act, self.act_beats = self.arc + 1, 1, 0
            self.save()
            await asyncio.sleep(20.0)
            await self._next_beat(lang, state)
        except Exception:  # noqa: BLE001
            log.exception("the arc's ending failed")
        finally:
            self.busy = False

    async def _brief_line(self, beat: dict[str, Any], detail: str, lang: str, state: dict[str, Any]) -> list[str]:
        """The director forgot Rourke's briefing: he gives it now (one short transmission)."""
        prompt = ADMIRAL_PROMPT.format(name=ADMIRAL["name"], bio=ADMIRAL["bio"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                       captain=CAPTAIN_WORD.get(lang, "Captain"), war=self.war.brief(detail=False),
                                       campaign="\n".join(f"- {c}" for c in self.campaign[-8:]),
                                       state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":")))
        ask = (f"You are calling the Aquila now to brief her captain on this: {beat.get('type')} — {beat.get('why', '')} "
               f"({detail}). One short transmission with `transmit`.")
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4 and not lines:
                lines.append(a["text"].strip())

        comp = await self.llm.chat(model=MODEL, messages=[{"role": "system", "content": prompt}, {"role": "user", "content": ask}],
                                   tools=[TRANSMIT], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False},
                                   max_tokens=300, temperature=0.6, on_tool_call=on_call, allow_fallbacks=True)
        if not lines and comp.content.strip() and not comp.error:
            lines.append(comp.content.strip())
        return lines

    # ------------------------------------------------------------------------------------------- the fleet net
    async def admiral_reply(self, message: str, lang: str, state: dict[str, Any]) -> list[str]:
        """The Aquila hailed the fleet: Rourke answers (and may send help)."""
        prompt = ADMIRAL_PROMPT.format(name=ADMIRAL["name"], bio=ADMIRAL["bio"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                       captain=CAPTAIN_WORD.get(lang, "Captain"), war=self.war.brief(detail=False),
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
    return _re.findall(r"T-\d+", detail)


def _brief(state: dict[str, Any]) -> dict[str, Any]:
    """What the director and the admiral need of the live state (compact)."""
    keep = ("location", "janus_gate", "alert", "hull_pct", "shields", "weapons", "squadrons", "damage_control", "heading_deg",
            "speed_mps", "casualties", "captain")
    out = {k: state.get(k) for k in keep if k in state}
    out["contacts"] = [{k: c.get(k) for k in ("id", "name", "class", "status", "range_km", "bearing_deg", "hull_pct")}
                       for c in state.get("contacts", []) or []]
    out["recent_events"] = state.get("_events", [])[-8:]
    return out
