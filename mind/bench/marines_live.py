"""The marine net against the real model on OpenRouter: do the people speak when they should, stay quiet when they should not, answer the Captain and give the right orders?
It costs a few cents (`--cap` stops it).

    cd mind && .venv/bin/python -m bench.marines_live                       # the scenes
    cd mind && .venv/bin/python -m bench.marines_live --battle              # and a compressed boarding: pulses, lines and the cost of a fight
    cd mind && .venv/bin/python -m bench.marines_live --only captain_hold --debug

Every scene is what the game sends the mind (the ship state with the boarding's snapshot and the marines' picture, a boarding's news, the Captain's words on the net, what the
net remembers of the last minutes); the bench calls the same code the server does (astra_mind.marines.MarineMinds) with a stage that records and a game that answers like the
C++ (`marine_order` and `lockdown`: a squad that is not ours, an unknown task, a place the plan does not have, a bulkhead that is not listed are refused with the game's own words).
What a machine can check is checked: whether anybody spoke, who, how many lines and how long, which command was sent with what and its result. Whether a line is in character, in
the Captain's language and true to the news is read from the printout (docs/ARCHITETTURA.md §1bis: never a regular expression over what they say). The key is read from the
environment or the repository's .env (in a worktree: the main checkout's), never printed."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


def _key_from_main_env() -> None:
    """In a worktree the repository's .env is the main checkout's (docs/ARCHITETTURA.md §6): only the OpenRouter key is read, never printed."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return
    root = Path(__file__).resolve().parents[2]
    for base in (root, root.parents[2] if root.parent.name == "worktrees" and root.parent.parent.name == ".claude" else root):
        env = base / ".env"
        if env.exists():
            for raw in env.read_text(encoding="utf-8").splitlines():
                if raw.startswith("OPENROUTER_API_KEY="):
                    os.environ["OPENROUTER_API_KEY"] = raw.split("=", 1)[1].strip()
                    return


_key_from_main_env()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astra_mind import marines as mm  # noqa: E402
from astra_mind import models  # noqa: E402
from astra_mind.openrouter import Completion, OpenRouter  # noqa: E402
from bench.flight_unit import Clock  # noqa: E402
from bench.marines_unit import BEATEN, BREACH, CAPTAIN_DOWN, CONTACT, CUT, DEAD, DOCKED, DOWN, PLACE, RESCUE, RETREAT, TAKEOVER, TALLY, ship_state  # noqa: E402

models.LEDGER.write_file = False

KNOWN_PLACES = {"engineering", "bridge", "medbay"}                  # ids the plan has that the picture does not list (a room's kind is an id too: the C++ resolves it)
ALL = ("all", "everyone", "reaction", "watch", "reserve")


class Spy:
    """The real client, keeping every completion it returns (tokens, times, cost) for the report."""

    def __init__(self, inner: OpenRouter) -> None:
        self.inner = inner
        self.done: list[Completion] = []

    async def chat(self, **kw: Any) -> Completion:
        c = await self.inner.chat(**kw)
        self.done.append(c)
        return c

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


@dataclass
class Scene:
    name: str
    lang: str = "it"
    events: list[str] = field(default_factory=list)
    captain: str = ""
    net: list[tuple[str, str]] = field(default_factory=list)          # what the net heard in the last minutes (who, text)
    mod: Callable[[dict[str, Any]], None] | None = None                # edits the state (the picture) in place
    over: bool = False                                                # the fight is over: the game no longer shows it
    expect: str = "speak"                 # speak | quiet | either
    who: set[str] | None = None           # who may speak first
    order: tuple[str, set[str], set[str] | None] | None = None        # (command, tasks (or `seal`/`open`), places): the command that must reach the game
    max_lines: int = 2
    note: str = ""
    memories: dict[str, list[str]] = field(default_factory=dict)       # what the people remember (from earlier in the campaign)
    silent_squads: set[str] = field(default_factory=set)               # speakers that must not be the first (no one of that squad is able)


def captain_in_corridor(st: dict[str, Any]) -> None:
    st["captain"] = "in a corridor on deck 5 section C, with an AR-181 rifle"
    st["_marines"]["captain"] = {"where": PLACE, "where_id": "corridor_5c_s", "down": False, "strength_pct": 90}
    st["_marines"]["squads"][1].update(doing="advance", under_orders=False, in_contact=False)           # (Reaction 2 has just come up beside him)
    st["_marines"]["squads"][1].pop("note", None)
    st["_marines"]["recent"] = ["61s: Mandate Squad One is cutting the bulkhead"]
    st["boarding"]["captain"] = {"strength_pct": 90, "down": False, "armed": "AR-181 rifle, 24/30, 4 spare magazines"}


def captain_down(st: dict[str, Any]) -> None:
    captain_in_corridor(st)
    st["_marines"]["captain"].update(down=True, strength_pct=8)
    st["boarding"]["captain"].update(down=True, strength_pct=8)
    st["_marines"]["squads"][0].update(doing="rescue_captain")


def alarm(st: dict[str, Any]) -> None:
    """The first seconds: nobody is in contact, the squads are still arming or on their way, no boarder is known."""
    pic = st["_marines"]
    pic.update(elapsed_s=3, hostiles_known=[], recent=[])
    for s in pic["squads"]:
        s.update(doing="advance", under_orders=False, in_contact=False, down=0, dead=0, able=min(int(s["able"]), 6))
        s["still_arming_or_waking"] = 4 if s["name"].startswith("Reaction") else 0
    st["boarding"].update(elapsed_s=3, hostiles="no hostile contact on the internal sensors", marines={"able": 20, "down": 0, "dead": 0},
                          boarders_known_losses={"down_or_dead": 0, "left_ship": 0})
    for b in pic["bulkheads"]:
        b["sealed"] = True
    pic["captain"] = {"where": "deck 1 section A (Bridge)", "where_id": "bridge", "down": False, "strength_pct": 100}


def early_contact(st: dict[str, Any]) -> None:
    """Forty seconds in: nobody has been hurt, Reaction 1 has just seen the boarders in the breach corridor, the others are still moving."""
    pic = st["_marines"]
    pic.update(elapsed_s=41, recent=["38s: the marines go: Reaction 1 and 2 to the default ambush"])
    for s in pic["squads"]:
        s.update(doing="advance", under_orders=False, in_contact=False, down=0, dead=0, still_arming_or_waking=0)
        s.pop("note", None)
    pic["squads"][0].update(able=6, where=PLACE, where_id="corridor_5c_s", doing="hold", in_contact=True)
    pic["squads"][1].update(able=6, where="deck 6 section C (Corridor 6-C)", where_id="corridor_6c")
    pic["squads"][2].update(able=4, where="deck 5 section B (Corridor 5-B)", where_id="corridor_5b")
    pic["squads"][3].update(able=5, where="deck 8 section C (Armory)", where_id="d8_armory_C1")
    pic["hostiles_known"] = [{"where": PLACE, "where_id": "corridor_5c_s", "count": 6, "age_s": 2}]
    st["boarding"].update(elapsed_s=41, marines={"able": 21, "down": 0, "dead": 0}, boarders_known_losses={"down_or_dead": 0, "left_ship": 0})


def bulkhead_cut(st: dict[str, Any]) -> None:
    st["_marines"]["bulkheads"][0]["sealed"] = False
    st["_marines"]["recent"] = ["61s: Mandate Squad One is cutting the bulkhead", "74s: the Mandate cut through the bulkhead at deck 5 section B"]


def quiet_fight(st: dict[str, Any]) -> None:
    """A standoff: the squads hold the ambush at full strength, the boarders are known to be cutting a bulkhead, nothing has happened for a while."""
    early_contact(st)
    pic = st["_marines"]
    pic.update(elapsed_s=96, recent=["88s: Mandate Squad One is cutting the bulkhead"])
    for s in pic["squads"]:
        s.update(doing="hold", in_contact=False, under_orders=False, where="deck 5 section B (Corridor 5-B)", where_id="corridor_5b")
    pic["hostiles_known"] = [{"where": PLACE, "where_id": "corridor_5c_s", "count": 5, "age_s": 22}]
    st["boarding"].update(elapsed_s=96)


class Game:
    """The game as the C++ answers the marines' commands (UAstraBoardSubsystem::HandleCommand): the same refusals in the same words."""

    def __init__(self, state: dict[str, Any]) -> None:
        self.state = state
        self.commands: list[dict[str, Any]] = []

    def ids(self) -> set[str]:
        p = self.state.get("_marines") or {}
        out = set(KNOWN_PLACES) | {p.get("objective_id", "")}
        for s in p.get("squads", []):
            out.add(s.get("where_id", ""))
        for k in ("hostiles_known", "likely_approach", "objective_entrances"):
            for r in p.get(k, []):
                out.add(r.get("where_id") or r.get("id", ""))
        am = p.get("default_ambush") or {}
        out |= {am.get("id_a", ""), am.get("id_b", "")}
        out.add((p.get("captain") or {}).get("where_id", ""))
        return out - {""}

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.commands.append({"name": name, "args": args, "by": by})
        p = self.state.get("_marines") or {}
        if name == "lockdown":
            doors = {d["id"] for d in p.get("bulkheads", [])}
            sealed = bool(args.get("sealed", True))
            asked = args.get("doors")
            if asked is None:
                return {"ok": True, "detail": f"{len(doors)} pressure bulkheads {'sealed' if sealed else 'opened'}"}
            good = [d for d in asked if d in doors]
            bad = [d for d in asked if d not in doors]
            detail = f"{len(good)} pressure bulkheads {'sealed' if sealed else 'opened'}" + (f"; no bulkhead is called {', '.join(bad)} (the picture's bulkheads list the ids)" if bad else "")
            return {"ok": bool(good), "detail": detail}
        who = str(args.get("squad", "")).lower()
        names = [s["name"] for s in p.get("squads", [])]
        hit = [n for n in names if who in ALL and (who in ("all", "everyone") or n.lower().startswith(who)) or n.lower() == who]
        if not hit:
            return {"ok": False, "detail": f"no squad of ours is called '{args.get('squad')}'"}
        if args.get("task") not in mm.TASKS:
            return {"ok": False, "detail": f"unknown task '{args.get('task')}' (hold, advance, assault, fall_back, follow_captain, rescue_captain, stand_down)"}
        place = str(args.get("place") or "")
        if place and place.lower() not in ("captain", "here"):
            if place.lower() in ("armory", "corridor"):
                return {"ok": False, "detail": f"'{place}' fits 6 places (d8_armory_C1 [deck 8 section C (Armory)]; d8_armory_C2 [deck 8 section C (Armory)]; ...): name one by its id"}
            if place.lower() == "hangar":
                return {"ok": False, "detail": "'hangar' fits 2 places (hangar_port [deck 9 section D (Port Hangar)]; hangar_starboard [deck 9 section D (Starboard Hangar)]): name one by its id"}
            if place.lower() == "mess":
                return {"ok": True, "detail": f"{', '.join(hit)}: {args.get('task')} at deck 4 section B (Mess Hall)"}
            if place not in self.ids() and place not in ("hangar_port", "hangar_starboard"):
                return {"ok": False, "detail": f"the plan has no place '{place}' (use an id from the picture: where_id, likely_approach, objective_entrances)"}
        return {"ok": True, "detail": f"{', '.join(hit)}: {args.get('task')}" + (f" at {place}" if place else "")}


SCENES = [
    Scene("alarm", events=[DOCKED, BREACH], mod=alarm, who={"reyes"}, max_lines=2, note="the alarm: the Major's first look; the bridge reports the ship's side"),
    Scene("first_contact", events=[CONTACT], mod=early_contact, who={"marine_reaction_1", "reyes"}, max_lines=2, note="the first sight, called by the one who saw it (Castillo) or the Major"),
    Scene("a_marine_is_dead", events=[DEAD], who={"reyes", "marine_reaction_1", "marine_reaction_2", "marine_reserve_1"}, max_lines=2,
          note="a marine who falls is called by name; Watch 1 has no one on his feet, so another voice calls it"),
    Scene("a_leader_is_down", events=[DOWN], expect="either", max_lines=2, note="a leader down and wounded: the squad or the Major may call it"),
    Scene("a_bulkhead_is_cut", events=[CUT], mod=bulkhead_cut, expect="either", max_lines=2, note="the boarders are through a bulkhead: the Major may warn, move a squad, or seal another"),
    Scene("a_quiet_fight", mod=quiet_fight, expect="either", max_lines=1, note="no news for 41 s while the drill holds: the look at the board; staying quiet is right"),
    Scene("they_retreat", events=[RETREAT], expect="either", max_lines=1, note="a Mandate squad breaks off: worth a word, never a victory lap"),
    Scene("captain_hold", captain="Reyes, tieni il corridoio fuori dall'ingegneria", who={"reyes"}, order=("marine_order", {"hold"}, {"d7_corridor_B1", "d7_stair_44p", "engineering"}),
          note="a hold at one of the ways into Main Engineering: an id from the board"),
    Scene("captain_with_me", captain="Reaction Uno, con me!", mod=captain_in_corridor, who={"marine_reaction_1", "reyes"}, order=("marine_order", {"follow_captain"}, None),
          note="'with me' is follow_captain for Reaction 1"),
    Scene("captain_seal", captain="Maggiore, chiudi le paratie", who={"reyes"}, order=("lockdown", {"seal"}, None), note="the Security console: the open bulkhead on the board, or all of them"),
    Scene("captain_open_door", captain="Maggiore, riapri la paratia sul ponte cinque verso la Spine: devo passare", who={"reyes"}, order=("lockdown", {"open"}, None),
          note="open a bulkhead: the one between corridor 5-B and the Spine is open already; the sealed one is between 5-C and 5-B"),
    Scene("captain_all_back", captain="Tutti indietro, ripiegate sull'armeria", who={"reyes"}, order=("marine_order", {"fall_back"}, {"d8_armory_C1"}), max_lines=2,
          note="'armory' is ambiguous in the plan: the id from the board (Reserve 1 stands in d8_armory_C1), or the game's answer corrects it"),
    Scene("captain_assault", captain="Reaction Due, all'attacco nel corridoio cinque-C!", who={"reyes", "marine_reaction_2"}, order=("marine_order", {"assault"}, {"corridor_5c_s"}),
          note="an assault ordered: carried out, with a word of concern at most"),
    Scene("captain_status", captain="Maggiore, com'è la situazione?", who={"reyes"}, max_lines=3, note="a question: answered from the board, no order"),
    Scene("captain_to_helm", captain="Timoniere, rotta zero-nove-zero, mezza forza.", expect="quiet", note="words for the bridge on the marine net: staying out"),
    Scene("captain_to_xo", captain="Numero Uno, rapporto danni.", expect="quiet", note="words for the XO: staying out"),
    Scene("face_to_face", captain="Sergente, tenete questa posizione!", mod=captain_in_corridor, who={"marine_reaction_2"}, order=("marine_order", {"hold"}, {"captain", "corridor_5c_s"}),
          note="in the corridor with Reaction 2: its sergeant answers and holds"),
    Scene("captain_hangar", captain="Reaction Uno, tenete l'hangar", max_lines=2, order=("marine_order", {"hold", "advance"}, {"hangar", "hangar_port", "hangar_starboard"}),
          note="a place the board does not list but the plan has twice: the order names it, the game lists the two, the order picks one or the Captain is asked"),
    Scene("captain_unknown_place", captain="Reaction Uno, tenete la piscina", max_lines=2, note="no such place anywhere: refused by the game, said once, no false 'done'"),
    Scene("captain_unknown_squad", captain="Reaction Quattro, avanzate!", max_lines=2, note="no such squad: the game refuses; the Major says so"),
    Scene("the_captain_falls", events=[CAPTAIN_DOWN], mod=captain_down, expect="speak", who={"reyes", "marine_reaction_1", "marine_reaction_2"}, max_lines=2,
          note="the Captain is down in the corridor: the marines go to him"),
    Scene("the_fight_is_won", events=[BEATEN], over=True, who={"reyes"}, max_lines=3, note="the end of the fight: the Major's report, the count"),
    Scene("the_reactor_is_lost", events=[TAKEOVER], expect="either", max_lines=2, note="Engineering taken: the bridge's emergency; the Major may speak for his marines"),
    Scene("thanks_after_the_fight", captain="Ottimo lavoro, Maggiore. Ringrazia i tuoi.", over=True, who={"reyes"}, max_lines=2,
          net=[("Reyes", "Il ponte è nostro, Capitano. Due morti, tre feriti."), ("(news)", BEATEN)], note="after the fight, within the window: the Major answers"),
    Scene("memory_promise", events=[DEAD], who={"reyes", "marine_reaction_1", "marine_reaction_2", "marine_reserve_1"}, max_lines=2,
          memories={"reyes": ["The Captain promised Reyes that no marine would ever again hold a bulkhead alone."]}, note="a marine dead in the very situation a promise was about: it may show, never recited"),
    Scene("contact_en", lang="en", events=[CONTACT], mod=early_contact, who={"marine_reaction_1", "reyes"}, note="English"),
    Scene("dead_es", lang="es", events=[DEAD], who={"reyes", "marine_reaction_1", "marine_reaction_2", "marine_reserve_1"}, note="Spanish"),
    Scene("captain_hold_fr", lang="fr", captain="Reyes, tenez le couloir devant la salle des machines", who={"reyes"}, order=("marine_order", {"hold"}, {"d7_corridor_B1", "d7_stair_44p", "engineering"}),
          note="French"),
    Scene("captain_status_de", lang="de", captain="Major, wie ist die Lage?", who={"reyes"}, max_lines=3, note="German"),
]


def words(s: str) -> int:
    return len(s.split())


def build_state(sc: Scene) -> dict[str, Any]:
    st = ship_state(fight=not sc.over)
    if sc.over:
        st["_marines"] = json.loads(json.dumps(__import__("bench.marines_unit", fromlist=["PICTURE"]).PICTURE))
    if sc.mod:
        sc.mod(st)
    return st


async def run_scene(sc: Scene, llm: Spy, debug: bool) -> tuple[list[str], dict[str, Any]]:
    clock = Clock()
    lines: list[tuple[float, str, str, dict[str, Any]]] = []
    st = build_state(sc)
    game = Game(st)
    t0 = time.perf_counter()

    async def say(key: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        lines.append((time.perf_counter() - t0, key, text, {"tone": tone, **kw}))

    m = mm.MarineMinds(llm, say, game.execute, lang=lambda: sc.lang, clock=clock)
    # the fight as the net has seen it so far: the picture is in (the voices are known) and the log holds the last minutes
    m._began, m._seen_on = clock.t, True
    m._news_t, m._last = clock.t, clock.t - 120.0                          # (nothing is due before the scene's own news: no look at the board of its own accord; the last pulse was long ago)
    if not sc.over:
        m.feed(st)
    else:
        m._sync(st["_marines"])
        m._pic, m._pic_t = st["_marines"], clock.t
        m._ended = clock.t + 0.0
    for key, mems in sc.memories.items():
        for text in mems:
            m._remember({"speaker": key, "kind": "promise", "memory": text})
    for who, text in sc.net:
        m._note(who, text)
        clock.t += 4.0
    clock.t += 3.0
    m._news_t = clock.t - 10.0
    for ev in sc.events:
        m.on_event(ev)
    if sc.captain:
        m.captain_to_net(sc.captain, sc.lang)
    m.feed(st)
    clock.t += mm.SETTLE_S + 0.5
    m.feed(st)
    if not sc.events and not sc.captain:
        clock.t += mm.WATCH_S + 1.0                                      # (a quiet fight: the look at the board)
        m.feed(st)
    for _ in range(300):
        await asyncio.sleep(0.1)
        if m._task is not None and m._task.done():
            break
    pulse = m.pulses[-1] if m.pulses else {"cost": 0.0, "tools": [], "latency": 0.0, "error": "no pulse"}
    problems: list[str] = []
    spoke = list(lines)
    if sc.expect == "speak" and not spoke:
        problems.append("nobody spoke")
    if sc.expect == "quiet" and spoke:
        problems.append("should have stayed quiet")
    if spoke and sc.who and spoke[0][1] not in sc.who:
        problems.append(f"{spoke[0][1]} spoke first, not {sorted(sc.who)}")
    if len(spoke) > sc.max_lines:
        problems.append(f"{len(spoke)} lines")
    if any(words(l[2]) > 40 for l in spoke):
        problems.append("a line over 40 words")
    if any(l[1] == "marine_watch_1" for l in spoke):
        problems.append("Watch 1 spoke, and nobody of it is on his feet")
    if sc.captain and spoke and not spoke[0][3].get("answer"):
        problems.append("the answer to the Captain is not marked as an answer")
    if sc.order:
        name, tasks, places = sc.order
        got = [c for c in game.commands if c["name"] == name and (c["args"].get("task") in tasks or (name == "lockdown" and ("seal" if c["args"].get("sealed") else "open") in tasks))]
        if not got:
            problems.append(f"no {name} {sorted(tasks)} reached the game")
        elif places and not any(c["args"].get("place") in places for c in got):
            problems.append(f"place {got[-1]['args'].get('place')} not in {sorted(places)}")
    if pulse.get("error"):
        problems.append(f"error: {pulse['error']}")
    detail = {"pulse": pulse, "game": game.commands, "problems": problems, "lines": spoke}
    out = [f"{round(t, 1):>4}s {key:<18} [{kw.get('tone')}{', urgent' if kw.get('urgent') else ''}{', answer' if kw.get('answer') else ''}] {text}" for t, key, text, kw in spoke]
    for c in game.commands:
        out.append(f"        -> game: {c['name']} {json.dumps(c['args'], ensure_ascii=False)} (by {c['by']})")
    if debug:
        out.append(f"        [tools {pulse.get('tools')}] tokens in/out/cached {pulse.get('tokens_in')}/{pulse.get('tokens_out')}/{pulse.get('cached')}")
    return out, detail


def squad(s: dict[str, Any], **kw: Any) -> dict[str, Any]:
    return {**s, **kw}


async def battle(llm: Spy, cap_dollars: float, spent: float) -> None:
    """A compressed boarding of the kind the sim produces (tools/boarding.py: about three minutes from the alarm to the end), run at the clock's speed: the pulses, the lines and what
    a boarding costs. The pictures move with the news: squads arming, in contact, hurt, a bulkhead cut, the Captain's own orders in the middle."""
    base = ship_state()
    steps: list[tuple[int, str | None, str | None, Callable[[dict[str, Any]], None]]] = [
        # (play second, the game's event, the Captain's words, what the boards show from then on)
        (0, DOCKED, None, alarm),
        (2, BREACH, None, lambda s: None),
        (24, None, None, lambda s: (s["_marines"].update(elapsed_s=24), [x.update(doing="advance", still_arming_or_waking=0) for x in s["_marines"]["squads"]])),
        (41, CONTACT, None, lambda s: (s["_marines"].update(elapsed_s=41), s["_marines"]["squads"][0].update(in_contact=True), s["_marines"]["squads"][1].update(in_contact=True))),
        (52, DOWN, None, lambda s: s["_marines"]["squads"][1].update(down=1, able=4)),
        (58, TALLY, None, lambda s: None),
        (66, None, "Reyes, tieni il corridoio fuori dall'ingegneria", lambda s: s["_marines"]["squads"][0].update(under_orders=True, doing="hold", note="hold the way into Main Engineering")),
        (74, CUT, None, lambda s: s["_marines"]["bulkheads"][0].update(sealed=False)),
        (93, DEAD, None, lambda s: s["_marines"]["squads"][2].update(able=0, dead=3, down=0)),
        (108, RETREAT, None, lambda s: s["_marines"]["hostiles_known"].clear()),
        (131, None, "Maggiore, rapporto", lambda s: None),
        (176, BEATEN, None, lambda s: None),
    ]
    clock = Clock()
    lines: list[tuple[float, str, str]] = []

    async def say(key: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        lines.append((clock.t - 1000.0, key, text))

    st = json.loads(json.dumps(base))
    game = Game(st)
    m = mm.MarineMinds(llm, say, game.execute, lang=lambda: "it", clock=clock)
    m.t0 = clock.t
    i = 0
    t_end = 215
    while clock.t - 1000.0 < t_end:
        now = clock.t - 1000.0
        while i < len(steps) and steps[i][0] <= now:
            _, ev, words_, patch = steps[i]
            patch(st)
            if ev:
                m.on_event(ev)
            if words_:
                m.captain_to_net(words_, "it")
            i += 1
        if now >= 176:
            st = ship_state(fight=False)
            st["_marines"] = {}
        m.feed(st)
        if m._task is not None and not m._task.done():
            await asyncio.wait_for(m._task, timeout=40)          # (the fight waits for the model: a second of play, a call's real seconds: the cadence is in play seconds)
        clock.t += 1.0
        if models.LEDGER.total + spent > cap_dollars:
            print("   the cap is reached: stopping the battle")
            break
    s = m.summary()
    print(f"\n=== a compressed boarding ({len(steps)} steps in {clock.t - 1000.0:.0f} s of play)")
    for t, key, text in lines:
        print(f"   {t:5.0f}s {key:<18} {text}")
    for c in game.commands:
        print(f"        -> game: {c['name']} {json.dumps(c['args'], ensure_ascii=False)} (by {c['by']})")
    print(f"   {s['pulses']} pulses ({s['silent']} silent, {m.stats['watch']} watch looks), {s['lines']} lines, {s['orders_ok']} orders ok / {s['orders_failed']} refused; {s['cost']:.5f} $ "
          f"({s['cost_per_pulse'] * 1000:.2f} m$ a pulse), latency median {s['latency_median']:.1f} s (p90 {s['latency_p90']:.1f}), first call {s['first_call_median']:.1f} s")
    print(f"   tokens in {s['tokens_in']} (cached {s['cached']}) out {s['tokens_out']}; a boarding of this length costs {s['cost']:.4f} $")


async def main_async(a: argparse.Namespace) -> int:
    if a.temp is not None:
        from dataclasses import replace
        models.ROLES["marines"] = replace(models.ROLES["marines"], temperature=a.temp)
    llm = Spy(OpenRouter())
    models.LEDGER.cap = None
    todo = [s for s in SCENES if not a.only or s.name in a.only]
    total, bad, runs = 0.0, 0, 0
    lat: list[float] = []
    rates: list[tuple[str, int, int]] = []
    for sc in todo:
        if total >= a.cap:
            print(f"the cap of {a.cap:.3f} $ is reached: stopping")
            break
        passed, shown_bad, cost_sc = 0, False, 0.0
        for rep in range(a.repeat):
            before = len(llm.done)
            out, d = await run_scene(sc, llm, a.debug)
            comps = llm.done[before:]
            c = sum(x.cost for x in comps)
            total += c
            cost_sc += c
            runs += 1
            lat.append(d["pulse"].get("latency", 0.0))
            ok = not d["problems"]
            passed += 1 if ok else 0
            bad += 0 if ok else 1
            first = d["lines"][0][0] if d["lines"] else d["pulse"].get("latency", 0.0)
            if rep == 0 or (not ok and not shown_bad):
                shown_bad = shown_bad or not ok
                print(f"\n=== {sc.name} ({sc.lang}){f' [run {rep + 1}]' if a.repeat > 1 else ''} — {sc.note}\n    {'OK ' if ok else 'BAD'} {'; '.join(d['problems'])}  first line {first:.1f}s, "
                      f"{sum(x.prompt_tokens for x in comps)} in / {sum(x.completion_tokens for x in comps)} out, {c * 1000:.2f} m$")
                for line in out:
                    print("    " + line)
                if a.debug:
                    for x in comps:
                        print(f"        [{x.provider}] content={x.content[:160]!r} calls={[(t.name, t.arguments_raw[:400]) for t in x.tool_calls]} error={x.error[:120]!r}")
        rates.append((sc.name, passed, a.repeat))
        if a.repeat > 1:
            print(f"    -> {sc.name}: {passed}/{a.repeat} as expected, {cost_sc / a.repeat * 1000:.2f} m$ a pulse")
    if lat:
        print(f"\n--- {runs - bad}/{runs} runs as expected ({', '.join(f'{n} {p}/{r}' for n, p, r in rates if p < r) or 'every scene every time'}), "
              f"pulse latency median {statistics.median(lat):.1f}s (max {max(lat):.1f}s), spent {total:.5f} $")
    if a.battle:
        await battle(llm, a.cap, total)
        print(f"\n--- total spent {models.LEDGER.total:.5f} $ ({models.LEDGER.summary()})")
    await llm.inner.close()
    return 1 if bad else 0


def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="   (%(name)s: %(message)s)")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", action="append", default=[], help="scene names to run")
    ap.add_argument("--cap", type=float, default=0.08, help="stop after spending this many dollars")
    ap.add_argument("--battle", action="store_true", help="also run the compressed boarding (the cost of a fight)")
    ap.add_argument("--debug", action="store_true", help="print what the model returned")
    ap.add_argument("--temp", type=float, default=None, help="the marines' temperature for this run (the role's default otherwise)")
    ap.add_argument("--repeat", type=int, default=1, help="run every scene this many times (the model is not deterministic): the rate of runs as expected is printed")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
