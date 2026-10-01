"""The flight net against the real model on OpenRouter: do the people speak when they should, stay quiet when they should not, answer the Captain and act? It costs
a few cents (`--cap` stops it).

    cd mind && .venv/bin/python -m bench.flight_live                       # the scenes
    cd mind && .venv/bin/python -m bench.flight_live --battle              # and a compressed battle: pulses, lines and the cost an hour
    cd mind && .venv/bin/python -m bench.flight_live --only loss_alpha --debug

Every scene is what the game sends the mind (the ship state, a squadron's news, the Captain's words on the net, what the net remembers of the last minutes); the bench
calls the same code the server does (astra_mind.flight_minds.FlightMinds) with a stage that records and a console that answers like the game's (a mission needs a live
contact on the plot). What a machine can check is checked: whether anybody spoke, who, how many lines and how long, which tool was called with what target and its result.
Whether a line is in character, in the Captain's language and true to the news is read from the printout (docs/ARCHITETTURA.md §1bis: never a regular expression over what
they say). The key is read from the environment or the repository's .env (in a worktree: the main checkout's), never printed."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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

from astra_mind import flight_minds as fm  # noqa: E402
from astra_mind import models  # noqa: E402
from astra_mind.openrouter import Completion, OpenRouter  # noqa: E402
from bench.flight_unit import AIRBORNE, FLYING, LOSS, RECOVERED, SPLASH, TORPEDO, WING, Clock, ship_state  # noqa: E402

models.LEDGER.write_file = False

PLOT = {"T-01", "T-02", "T-21", "T-22", "T-23"}


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
    state: dict[str, Any] = field(default_factory=dict)
    wing: bool = False
    open_net: bool = False
    expect: str = "speak"                 # speak | quiet | either
    who: set[str] | None = None           # who may speak first
    order: tuple[str, str, set[str], str | None] | None = None        # (by, squadron, mission types, target): the order that must reach the console
    max_lines: int = 2
    note: str = ""
    memories: dict[str, list[str]] = field(default_factory=dict)       # what the people remember (from earlier in the campaign)


def SQ(**squads: str) -> dict[str, Any]:
    """The flight groups' boards, as the game words them (the others as in the default state)."""
    base = {"alpha": "airborne: 6 Falcons airborne, mission cap; 2 lost", "bravo": "on deck, ready (7 Hammers)", "drones": "ready (12 Wasps)"}
    return {"squadrons": {**base, **squads}}


HARPIES1 = {"enemy_small_craft": "1 Harpy strike fighters airborne (rockets and guns), the nearest 14.0 km from us"}

SCENES = [
    Scene("loss_alpha", events=[LOSS], who={"alpha_lead", "cag"}, note="a leader tells his losses, by call sign"),
    Scene("airborne_alpha", events=[AIRBORNE], state=SQ(alpha="airborne: 8 Falcons airborne, mission cap"), expect="either", max_lines=1, note="a launch: the Chief's, or nothing"),
    Scene("engaged_alpha", events=["flight: alpha squadron engaged a Harpy at 6.2 km"], state={**SQ(alpha="airborne: 8 Falcons airborne, mission cap"),
                                                                                             "enemy_small_craft": "4 Harpy strike fighters airborne (rockets and guns), the nearest 6.2 km from us"},
          expect="either", who={"alpha_lead", "cag"}, max_lines=1, note="the first contact: the fighters' leader may call it in two words, or not"),
    Scene("torpedo_bravo", events=[TORPEDO], state=SQ(bravo="returning: 7 Hammers airborne, mission recall"), who={"bravo_lead", "cag"}, max_lines=1, note="the bomber leader's"),
    Scene("recovered_alpha", events=[RECOVERED], state=SQ(alpha="on deck, rearming: ready in 60 s (6 Falcons); 2 lost"), who={"deck_chief", "alpha_lead"}, max_lines=1,
          note="the Chief's: aboard, the rearm"),
    Scene("splash_three", events=[SPLASH], state=HARPIES1, who={"alpha_lead", "cag"}, max_lines=1, note="the kills are the fighters' leader's: called now, nobody else reports them"),
    Scene("loss_new", events=["flight: alpha squadron has lost 1 Falcon to enemy fire, 5 left — Lieutenant Tove Kimura (call sign Echo) killed"],
          state=SQ(alpha="airborne: 5 Falcons airborne, mission cap; 3 lost"), who={"alpha_lead", "cag"},
          net=[("Alpha Lead", "Due Falcon a terra, Wick e Moth. Alpha tiene la pattuglia, sei in volo."), ("(news)", LOSS)],
          note="a second loss minutes later: new, told by name"),
    Scene("splash_after_wing_call", events=["tactical: 1 Harpy splashed, 3 of the enemy strike fighters left"], wing=True, expect="either", max_lines=1,
          state={"captain": FLYING, "enemy_small_craft": "3 Harpy strike fighters airborne (rockets and guns), the nearest 4.0 km from us"},
          net=[("Eagle 2", "Eagle 2: Harpy abbattuto, ne restano tre."), ("(news)", "flight: Eagle 2 splashed a Harpy")], note="the wingman called it: the tactical line is the same news"),
    Scene("rearmed_chief", events=["flight: bravo squadron rearmed, 7 Hammers ready on the flight deck"], who={"deck_chief"}, max_lines=1, note="the Chief's: ready again, his cue to launch"),
    Scene("deck_fire", events=["damage report: the unattended fire at deck 9 section C has spread to section D"], expect="either", note="the Chief's deck; ops has the repair"),
    Scene("rescue_wasp", events=["flight: search and rescue at the wreck of the Brightwater: lifeboats found, 41 survivors picked up"], expect="either",
          note="a Wasp rescue flight's result: the CAG's, or nothing"),
    Scene("captain_cover", captain="Alpha Lead, copri il Vigilant", open_net=True, who={"alpha_lead"}, order=("alpha_lead", "alpha", {"escort", "cap"}, "T-02"),
          note="an order to a leader: he acts and answers"),
    Scene("captain_strike", captain="Bravo Lead, attacca l'Acheron con tutti i siluri", open_net=True, who={"bravo_lead"}, order=("bravo_lead", "bravo", {"strike"}, "T-21"),
          note="a strike on a ship on the plot"),
    Scene("captain_recall", captain="CAG, richiama tutti i velivoli", open_net=True, who={"cag"}, order=("cag", "alpha", {"recall"}, None), max_lines=3,
          note="the CAG commands the whole Air Group"),
    Scene("captain_status", captain="CAG, com'è la situazione dei tuoi squadroni?", open_net=True, who={"cag"}, max_lines=3, note="a question: answered from the boards, no order"),
    Scene("captain_deck", captain="Capo del ponte, quanto ci mette Bravo a essere pronto?", open_net=True, who={"deck_chief"},
          state={"squadrons": {"alpha": "airborne: 6 Falcons airborne, mission cap; 2 lost", "bravo": "on deck, rearming: ready in 45 s (7 Hammers)", "drones": "ready (12 Wasps)"}},
          note="the Chief knows the rearm time from the board"),
    Scene("captain_to_helm", captain="Timoniere, rotta zero-nove-zero, mezza forza.", open_net=True, expect="quiet", note="words for the bridge on an open flight net"),
    Scene("captain_to_price", captain="Price, lancia Bravo sull'Acheron.", open_net=True, expect="quiet", note="Price is the bridge's: the net stays out"),
    Scene("captain_launch_rearming", captain="CAG, lancia Bravo sull'Acheron.", open_net=True, who={"cag", "bravo_lead"}, max_lines=2,
          state=SQ(bravo="on deck, rearming: ready in 45 s (7 Hammers)"), note="the console refuses (rearming): they say when it will be ready, and do not claim a launch"),
    Scene("memory_promise", events=["flight: alpha squadron has lost 2 Falcons to enemy fire, 4 left — Lieutenant Tove Kimura (call sign Echo) killed; Ensign Jin Park (call sign Boots) killed"],
          state=SQ(alpha="airborne: 4 Falcons airborne, mission strike on T-21; 4 lost"), who={"alpha_lead", "cag"}, max_lines=2,
          memories={"alpha_lead": ["The Captain promised Pilgrim that Alpha would never again fly a strike through a point-defence belt without Bravo's cover."]},
          note="a loss in the very situation a promise was about: it may show, never recited"),
    Scene("captain_unknown_target", captain="Alpha Lead, attacca il T-77.", open_net=True, who={"alpha_lead"}, max_lines=2, note="no such contact: the order is refused or not given; he says so"),
    Scene("captain_to_wrong_squadron", captain="Alpha Lead, manda Bravo ad attaccare l'Acheron.", open_net=True, max_lines=3,
          note="a leader does not order the other squadron: he says whose it is, or the CAG does it"),
    Scene("eagle_joined", lang="it", events=[WING], wing=True, state={"captain": FLYING}, who={"alpha_2", "alpha_3"}, note="the wing joins the Captain's Falcon"),
    Scene("eagle_hit", events=["flight: Eagle 3 is hit — hull 38%"], wing=True, state={"captain": FLYING}, who={"alpha_3", "alpha_2"}, max_lines=2, note="a wingman is hit"),
    Scene("eagle_splash", events=["flight: Eagle 2 splashed a Harpy"], wing=True, state={"captain": FLYING}, who={"alpha_2", "alpha_3"}, note="a wingman's kill"),
    Scene("eagle_down", events=["flight: Eagle is down — the Captain's Falcon was destroyed, the Captain ejected; a Wasp is going out for the pod"], wing=True,
          state={"captain": "the Captain ejected from a destroyed Falcon; the pod is being recovered"}, who={"alpha_2", "alpha_3"}, max_lines=2, note="the Captain's Falcon is lost"),
    Scene("captain_to_wingman", captain="Eagle 2, copri il mio sei.", wing=True, state={"captain": FLYING}, who={"alpha_2"}, max_lines=2,
          note="in the cockpit: the wingman answers truthfully (he is on his wing)"),
    Scene("captain_to_wing_maneuver", captain="Eagle 3, rompi a sinistra e prendi quel bandito alle due.", wing=True, state={"captain": FLYING}, who={"alpha_3", "alpha_2"}, max_lines=2,
          note="a maneuver the wing cannot be ordered to make: he says what he does, never what he cannot"),
    Scene("loss_en", lang="en", events=[LOSS], who={"alpha_lead", "cag"}, note="English"),
    Scene("torpedo_es", lang="es", events=[TORPEDO], who={"bravo_lead", "cag"}, note="Spanish"),
    Scene("recovered_fr", lang="fr", events=[RECOVERED], state=SQ(alpha="on deck, rearming: ready in 60 s (6 Falcons); 2 lost"), who={"deck_chief", "alpha_lead"}, note="French"),
    Scene("captain_de", lang="de", captain="Alpha Lead, Statusbericht bitte.", open_net=True, who={"alpha_lead"}, note="German"),
]


class Game:
    """The flight console as the game answers it: a mission needs a live contact on the plot (UAstraBattleSubsystem::LaunchSquadron)."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.commands: list[dict[str, Any]] = []
        self.state = state or {}

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.commands.append({"name": name, "args": args, "by": by})
        p = args.get("params") or {}
        board = str((self.state.get("squadrons") or {}).get(p.get("squadron", ""), ""))
        if args.get("mode") not in ("recall", "hold") and "rearming" in board and "airborne" not in board.split("rearming")[0]:
            return {"ok": False, "detail": f"{p.get('squadron')} squadron is rearming on the flight deck, " + board.split("rearming:", 1)[-1].split("(")[0].strip()}
        if args.get("mode") in ("strike", "escort", "ew") and p.get("target") not in PLOT:
            return {"ok": False, "detail": f"mission {args['mode']} needs a live contact (got '{p.get('target', '')}')"}
        if args.get("mode") == "escort" and p.get("target") in ("T-21", "T-22", "T-23"):
            return {"ok": False, "detail": "escort is for friendly or civilian ships"}
        return {"ok": True, "detail": f"{p.get('squadron')} squadron: mission {args.get('mode')}" + (f" on {p['target']}" if p.get("target") else "")}


def words(s: str) -> int:
    return len(s.split())


async def run_scene(sc: Scene, llm: Spy, debug: bool) -> tuple[list[str], dict[str, Any]]:
    clock = Clock()
    lines: list[tuple[float, str, str, dict[str, Any]]] = []
    game = Game(ship_state(**sc.state))
    t0 = time.perf_counter()

    async def say(key: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        lines.append((time.perf_counter() - t0, key, text, {"tone": tone, **kw}))

    f = fm.FlightMinds(llm, say, game.execute, lang=lambda: sc.lang, clock=clock)
    st = ship_state(**sc.state)
    if sc.wing:
        f.on_event(WING)
        f._events.clear()
    f.net_open = sc.open_net
    for key, mems in sc.memories.items():
        for m in mems:
            f._remember({"speaker": key, "kind": "promise", "memory": m})
    for who, text in sc.net:
        f._note(who, text)
        clock.t += 4.0
    clock.t += 3.0
    f.feed(st)
    for ev in sc.events:
        f.on_event(ev)
    if sc.captain:
        f.captain_to_net(sc.captain, sc.lang)
    f.feed(st)
    clock.t += fm.SETTLE_S + 0.5
    f.feed(st)
    for _ in range(300):
        await asyncio.sleep(0.1)
        if f._task is not None and f._task.done():
            break
    pulse = f.pulses[-1] if f.pulses else {"cost": 0.0, "tools": [], "latency": 0.0, "error": "no pulse"}
    problems: list[str] = []
    spoke = [l for l in lines]
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
    if sc.captain and spoke and not spoke[0][3].get("answer"):
        problems.append("the answer to the Captain is not marked as an answer")
    if sc.order:
        by, sq, types, target = sc.order
        got = [c for c in game.commands if c["args"].get("aspect") == sq and c["args"].get("mode") in types]
        if not got:
            problems.append(f"no {sq} {sorted(types)} order reached the console")
        elif target and got[-1]["args"].get("params", {}).get("target") != target:
            problems.append(f"target {got[-1]['args'].get('params', {}).get('target')} not {target}")
        if got and got[-1]["args"].get("by") != "captain":
            problems.append("the order is not recorded as the Captain's")
    if pulse.get("error"):
        problems.append(f"error: {pulse['error']}")
    detail = {"pulse": pulse, "game": game.commands, "problems": problems, "lines": spoke}
    out = [f"{round(t, 1):>4}s {key:<11} [{kw.get('tone')}{', urgent' if kw.get('urgent') else ''}{', answer' if kw.get('answer') else ''}] {text}" for t, key, text, kw in spoke]
    for c in game.commands:
        p = c["args"].get("params") or {}
        out.append(f"        -> console: {c['args'].get('aspect')} {c['args'].get('mode')}{' on ' + str(p['target']) if p.get('target') else ''} (by {c['args'].get('by')})")
    if debug:
        out.append(f"        [tools {pulse.get('tools')}] tokens in/out/cached {pulse.get('tokens_in')}/{pulse.get('tokens_out')}/{pulse.get('cached')}")
    return out, detail


async def battle(llm: Spy, cap_dollars: float, spent: float) -> None:
    """A compressed battle of the kind the sim produces (docs/GUERRA.md §7.6, Saved/War records and the mind's log of 28/9): launches, the Harpies, losses, a torpedo run, recoveries
    and rearming over twelve minutes of play, run at the clock's speed (a second of battle for each pass); the pulses, the lines and what an hour of such battle would cost."""
    def E(n: int, km: float) -> dict[str, Any]:
        return {"enemy_small_craft": (f"{n} Harpy strike fighters airborne (rockets and guns), the nearest {km} km from us" if n else "none")}

    air = "airborne: {n} Falcons airborne, mission cap{lost}"
    # (time in play seconds, the game's event, what the boards show from then on)
    script: list[tuple[int, str, dict[str, Any]]] = [
        (0, "flight: alpha squadron airborne, 8 Falcons on CAP", {**SQ(alpha=air.format(n=8, lost="")), **E(6, 14.0)}),
        (14, "flight: bravo squadron airborne, 7 Hammers on STRIKE", SQ(alpha=air.format(n=8, lost=""), bravo="airborne: 7 Hammers airborne, mission strike on T-21")),
        (62, "tactical: 1 Harpy splashed, 5 of the enemy strike fighters left", E(5, 9.0)),
        (74, "tactical: 1 Harpy splashed, 4 of the enemy strike fighters left", E(4, 7.5)),
        (80, "flight: alpha squadron has lost 1 Falcon to enemy fire, 7 left — Lieutenant Anil Rao (call sign Wick) killed",
         SQ(alpha=air.format(n=7, lost="; 1 lost"), bravo="airborne: 7 Hammers airborne, mission strike on T-21")),
        (86, "tactical: 3 Harpies splashed, 1 of the enemy strike fighters left", E(1, 6.0)),
        (98, "tactical: 1 Harpy splashed, 0 of the enemy strike fighters left", E(0, 0)),
        (118, "flight: bravo squadron torpedo run on T-21: 7 torpedoes away, bombers returning",
         SQ(alpha=air.format(n=7, lost="; 1 lost"), bravo="returning: 7 Hammers airborne, mission recall")),
        (131, "flight: bravo squadron has lost 2 Hammers to enemy fire, 5 left — Lieutenant Mara Okeke (call sign Moth) ejected, recovered wounded by search and rescue; "
              "Petty Officer Jin Park (call sign Dagger) killed", SQ(alpha=air.format(n=7, lost="; 1 lost"), bravo="returning: 5 Hammers airborne, mission recall; 2 lost")),
        (180, "flight: bravo squadron recovered, 5 of 5 Hammers aboard, rearming (120 s)",
         SQ(alpha=air.format(n=7, lost="; 1 lost"), bravo="on deck, rearming: ready in 120 s (5 Hammers); 2 lost")),
        (214, "flight: alpha squadron recovered, 7 of 7 Falcons aboard, rearming (60 s)",
         SQ(alpha="on deck, rearming: ready in 60 s (7 Falcons); 1 lost", bravo="on deck, rearming: ready in 86 s (5 Hammers); 2 lost")),
        (244, "flight: alpha squadron rearmed, 7 Falcons ready on the flight deck", SQ(alpha="on deck, ready (7 Falcons); 1 lost", bravo="on deck, rearming: ready in 56 s (5 Hammers); 2 lost")),
        (300, "flight: bravo squadron rearmed, 5 Hammers ready on the flight deck", SQ(alpha="on deck, ready (7 Falcons); 1 lost", bravo="on deck, ready (5 Hammers); 2 lost")),
        (330, "sensors: Cocytus has launched strike fighters — 6 Harpies inbound on the Aquila",
         {**SQ(alpha="on deck, ready (7 Falcons); 1 lost", bravo="on deck, ready (5 Hammers); 2 lost"), **E(6, 21.0)}),
        (352, "flight: alpha squadron airborne, 7 Falcons on CAP", {**SQ(alpha=air.format(n=7, lost="; 1 lost"), bravo="on deck, ready (5 Hammers); 2 lost"), **E(6, 12.0)}),
        (396, "tactical: 2 Harpies splashed, 4 of the enemy strike fighters left", E(4, 8.0)),
        (408, "tactical: 2 Harpies splashed, 2 of the enemy strike fighters left", E(2, 6.0)),
        (419, "flight: alpha squadron has lost 3 Falcons to enemy fire, 4 left — Ensign Jin Park (call sign Boots) killed; Lieutenant Tove Kimura (call sign Echo) killed; "
              "Lieutenant Aziz Sato (call sign Ace) ejected, recovered wounded by search and rescue",
         SQ(alpha=air.format(n=4, lost="; 4 lost"), bravo="on deck, ready (5 Hammers); 2 lost")),
        (430, "tactical: 2 Harpies splashed, 0 of the enemy strike fighters left", E(0, 0)),
        (452, "flight: Falcon recon has identified T-22: Styx-class destroyer, Phlegethon", {}),
        (520, "flight: alpha squadron recovered, 4 of 4 Falcons aboard, rearming (60 s)",
         SQ(alpha="on deck, rearming: ready in 60 s (4 Falcons); 4 lost", bravo="on deck, ready (5 Hammers); 2 lost")),
        (584, "flight: alpha squadron rearmed, 4 Falcons ready on the flight deck", SQ(alpha="on deck, ready (4 Falcons); 4 lost", bravo="on deck, ready (5 Hammers); 2 lost")),
        (640, "flight: search and rescue at the wreck of the Brightwater: lifeboats found, 41 survivors picked up", {}),
    ]
    clock = Clock()
    lines: list[tuple[float, str, str]] = []

    async def say(key: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        lines.append((clock.t - 1000.0, key, text))

    f = fm.FlightMinds(llm, say, Game().execute, lang=lambda: "it", clock=clock)
    f.t0 = clock.t
    st = ship_state(**SQ(alpha="on deck, ready (8 Falcons)"), **E(0, 0))
    i = 0
    t_end = 700
    while clock.t - 1000.0 < t_end:
        now = clock.t - 1000.0
        while i < len(script) and script[i][0] <= now:
            st = {**st, **script[i][2]}                       # the boards move with the news
            f.on_event(script[i][1])
            i += 1
        f.feed(st)
        if f._task is not None and not f._task.done():
            await asyncio.wait_for(f._task, timeout=40)        # (the battle waits for the model: a second of play, a call's real seconds: the cadence is in play seconds)
        clock.t += 1.0
        if models.LEDGER.total + spent > cap_dollars:
            print("   the cap is reached: stopping the battle")
            break
    s = f.summary()
    print(f"\n=== a compressed battle ({len(script)} events in {clock.t - 1000.0:.0f} s of play)")
    for t, key, text in lines:
        print(f"   {t:5.0f}s {key:<11} {text}")
    per_hour = s["cost"] / max(1.0, clock.t - 1000.0) * 3600.0
    print(f"   {s['pulses']} pulses ({s['silent']} silent), {s['lines']} lines, {s['orders_ok']} orders; {s['cost']:.5f} $ ({s['cost_per_pulse'] * 1000:.2f} m$ a pulse), "
          f"latency median {s['latency_median']:.1f} s (p90 {s['latency_p90']:.1f}), first call {s['first_call_median']:.1f} s")
    print(f"   tokens in {s['tokens_in']} (cached {s['cached']}) out {s['tokens_out']}; an hour of this battle would cost {per_hour:.3f} $ "
          f"(a battle of 12 minutes in a game hour: {s['cost'] * 5:.3f} $)")


async def main_async(a: argparse.Namespace) -> int:
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
    ap.add_argument("--battle", action="store_true", help="also run the compressed battle (the cost an hour)")
    ap.add_argument("--debug", action="store_true", help="print what the model returned")
    ap.add_argument("--repeat", type=int, default=1, help="run every scene this many times (the model is not deterministic): the rate of runs as expected is printed")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
