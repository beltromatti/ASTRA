#!/usr/bin/env python3
"""ABBORDAGGI, fighting inside the ASN Aquila (Source/ASTRA/AstraBoard*.cpp, docs/ABBORDAGGI.md): the headless bench.

  tools/boarding.py run [--scenario all|map|rules|duel|squad|flank|board|orders|fps|plans|attack] [--seed 1] [--seeds 20] [--boarders 10] [--set "MandateSkill=0.8,HoldS=60"]
                                       the commandlet AstraBoardSim: the plan as the soldiers see it (portals, corners, lines of sight, routes), duels and
                                       squad fights in a corridor (who wins, how fast, with corners and without, with the flank and without), and whole
                                       boardings of the real ship (a Mandate boarding party through a breach, the marines on watch and the reaction
                                       team: who holds, at what cost, how long); checks the invariants and prints the verdict.
                                       --scenario plans (on request): the plan of every class (data/ship/plans, FLOTTA-VIVA's): it loads, every dock has a way to the bridge, the
                                       engineering hall and the commander's suite; --scenario attack [--class acheron]: the marines go aboard a Mandate ship by two Kestrels (24 men)
                                       and the same plan with the roles turned (who wins, how fast, at what cost)
                                       --scenario war [--class acheron] (on request): FLOTTA-VIVA's inside of a class's ship is shot at (none, a few, many, a great many blows) and the marines go
                                       aboard with the people the war left (the host's own way: AstraBoardScene with the snapshot): who holds her, who lies hurt, what it costs the marines
                                       --scenario fps (on request, no plan needed): the Captain's arms on the weapons against the mannequin's own
                                       animations (the sight on its place, the hands on the grips, what the picture holds at 16:9 and 16:10);
                                       --fpsposes FILE writes the engine's poses for the offline preview
  tools/boarding.py craft [--setup out|shield|pd|pd2|cap|all] [--seeds 8]
                                       the assault craft in the battle (the war bench, AstraWarSim, no window): our Kestrels from a ship to a hulk, a shield that holds them off the hull, the
                                       Mandate's skiffs through the point defence of a ship whose shield is down (how many dock, in how long), and the same with fighters on cap;
                                       the events are the craft's own ([Boarding] lines of the log)
  tools/boarding.py report Saved/Boarding/run.json   the record of a run

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi -unattended -nopause: it
never opens a window or touches the GPU, so it can run while the game or the editor is open (if the engine crashes, its crash reporter is closed by the script).
It uses no mind and spends nothing (no AI calls).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("/Users/Shared/Epic Games/UE_5.8" if sys.platform == "darwin" else "C:/Program Files/Epic Games/UE_5.8")
ENGINE = _UE / ("Engine/Binaries/Mac/UnrealEditor-Cmd" if sys.platform == "darwin" else "Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
OUT = ROOT / "Saved" / "Boarding"


def cmd_run(a: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out = (ROOT / a.out).resolve()
    log = OUT / "last_run.log"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraBoardSim", f"-scenario={a.scenario}", f"-seed={a.seed}", f"-seeds={a.seeds}", f"-boarders={a.boarders}",
            f"-out={out}", "-nullrhi", "-unattended", "-nopause", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    if a.set:
        args.append(f"-set={a.set}")
    if a.trace:
        args.append("-trace")
    if a.klass:
        args.append(f"-class={a.klass}")
    if a.fpsset:
        args.append(f"-fpsset={a.fpsset}")
    if a.fpsposes:
        args.append(f"-fpsposes={(ROOT / a.fpsposes).resolve()}")
    if a.setup >= 0:
        args.append(f"-setup={a.setup}")
    if getattr(a, "dump", ""):
        args.append(f"-dump={(ROOT / a.dump).resolve()}")
    if getattr(a, "focus", ""):
        args.append(f"-focus={a.focus}")
    if getattr(a, "hurt", False):
        args.append("-hurt")
    t0 = time.time()
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            print(f"   the boarding bench did not finish in {a.timeout} s: killed (log {log})")
    # a crashed engine leaves its crash reporter running (a window spinning at 100% of a core): the ones of this run's process are closed here
    if sys.platform != "win32":
        subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    else:
        subprocess.run(["taskkill", "/F", "/IM", "CrashReportClient.exe"], check=False, capture_output=True)
    lines = [l for l in log.read_text(errors="replace").splitlines() if "[Board]" in l]
    for l in lines[-200:]:
        print(l[l.find("[Board]"):])
    print(f"exit {p.returncode} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


# ---------------------------------------------------------------------------------------------------------------- the craft in the battle
_SPAWN_A = "astra.war.spawn praetorian astra -3 0 0 0 id=A1 name=Carrier static hold passive"
_SPAWN_M = "astra.war.spawn acheron mandate 3 0 0 90 id=M1 name=Hulk static hold passive"
_SPAWN_MS = "astra.war.spawn acheron mandate -3 0 0 0 id=M1 name=Raider static hold passive"
_SPAWN_AT = "astra.war.spawn praetorian astra 3 0 0 90 id=A1 name=Picket static hold passive"
CRAFT_SETUPS = {
    # our Kestrels from a Praetorian to an Acheron that has lost its power: they fly across, dock, and after a while let go and come home
    "out": dict(doc="two Kestrels from the Praetorian to a hulk: launched, docked at the port hatches, let go, home", seconds=330,
                exec=f"astra.war.sandbox;{_SPAWN_A};{_SPAWN_M}",
                at="2=astra.board.disable M1|3=astra.board.craft A1 M1 2 port|140=astra.board.depart 9000", expect=dict(launched=2, docked=2, destroyed=0, recovered=2)),
    # the same target with her shields up (and no point defence): the craft cannot dock through them, wait off the hull, turn back and come home
    "shield": dict(doc="the target's shield holds: the craft wait, turn back, come home (no point defence on her)", seconds=240,
                   exec=f"astra.war.sandbox;{_SPAWN_A};{_SPAWN_M}",
                   at="2=astra.board.pd M1 0|3=astra.board.craft A1 M1 2 port", expect=dict(launched=2, docked=0, aborted=2, recovered=2)),
    # four of the Mandate's skiffs at a Praetorian whose shield is down: her four point-defence channels shoot them on the way in
    "pd": dict(doc="four skiffs from an Acheron at a Praetorian with her shields down and her point defence working: how many dock", seconds=200,
               exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
               at="2=astra.board.strip A1|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
    "pd2": dict(doc="the same with two channels (a destroyer's)", seconds=200,
                exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
                at="2=astra.board.strip A1|2=astra.board.pd A1 2|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
    "cap": dict(doc="the same four skiffs against a Praetorian whose Falcons fly cover (a flight of fighters on cap)", seconds=200,
                exec=f"astra.war.sandbox;{_SPAWN_AT};{_SPAWN_MS}",
                at="2=astra.board.strip A1|2=astra.war.wing A1 fighter 4 cap|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4)),
}


def _at_distance(km: int):
    """The pair of the `out` and `pd` setups at a battle distance: our carrier at -km/2, the target at +km/2 (positions in km)."""
    h = km / 2.0
    ours = f"astra.war.spawn praetorian astra {-h} 0 0 0 id=A1 name=Carrier static hold passive"
    hulk = f"astra.war.spawn acheron mandate {h} 0 0 90 id=M1 name=Hulk static hold passive"
    pick = f"astra.war.spawn praetorian astra {h} 0 0 90 id=A1 name=Picket static hold passive"
    raid = f"astra.war.spawn acheron mandate {-h} 0 0 0 id=M1 name=Raider static hold passive"
    return ours, hulk, pick, raid


# the pace (ABBORDAGGI-4): from a boat leaving its bay to the way in being cut open, and home again, at the distances a battle is fought at (10, 20, 40 and 80 km), with the target's point
# defence down (a hulk) and up (a Praetorian, shields stripped: the boats cross her four channels), the boats' own clock (the minds are told it) against what the flight does
for _km in (10, 20, 40, 80):
    _o, _h, _p, _r = _at_distance(_km)
    CRAFT_SETUPS[f"d{_km}"] = dict(doc=f"two Kestrels from the Praetorian to a hulk {_km} km away: docked, let go, home (no point defence on her)", seconds=420 + 5 * _km,
                                   exec=f"astra.war.sandbox;{_o};{_h}",
                                   at=f"2=astra.board.disable M1|3=astra.board.craft A1 M1 2 port|{150 + 2 * _km}=astra.board.depart 9000", expect=dict(launched=2, docked=2, destroyed=0, recovered=2))
    CRAFT_SETUPS[f"pd{_km}"] = dict(doc=f"four skiffs from an Acheron at a Praetorian {_km} km away with her shields down and her four point-defence channels working: how many dock", seconds=120 + 6 * _km,
                                    exec=f"astra.war.sandbox;{_p};{_r}",
                                    at="2=astra.board.strip A1|3=astra.board.craft M1 A1 4 starboard", expect=dict(launched=4))
CRAFT_SETUPS["kpd20"] = dict(doc="two Kestrels from the Praetorian at an Acheron 20 km away whose shields are down and whose point defence (two channels) works: how many dock", seconds=240,
                             exec=f"astra.war.sandbox;{_at_distance(20)[0]};{_at_distance(20)[1]}",
                             at="2=astra.board.strip M1|3=astra.board.craft A1 M1 2 port", expect=dict(launched=2))


def _craft_run(a, name: str, setup: dict) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"craft_{name}.log"
    out = OUT / f"craft_{name}.json"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={setup['seconds']}", "-step=0.1", "-every=5", f"-out={out}", f"-seed={a.seed}", f"-seeds={a.seeds}",
            f"-exec={setup['exec']}", f"-at={setup['at']}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    if sys.platform != "win32":
        subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    runs, cur = [], None
    for l in log.read_text(errors="replace").splitlines():
        if "[WarSim]" in l and "seed " in l and "battle in" in l:
            if cur is not None:
                runs.append(cur)
            cur = None
            continue
        if "[Boarding]" not in l:
            continue
        s = l[l.find("[Boarding]") + 10:].strip()
        if cur is None:
            cur = []
        cur.append(s)
    if cur:
        runs.append(cur)
    return {"log": log, "runs": runs, "code": p.returncode}


def _count(lines: list[str], kind: str) -> int:
    return sum(1 for l in lines if len(l.split()) > 1 and l.split()[1] == kind)


def cmd_craft(a: argparse.Namespace) -> int:
    names = list(CRAFT_SETUPS) if a.setup == "all" else [a.setup]
    bad = 0
    for name in names:
        setup = CRAFT_SETUPS[name]
        r = _craft_run(a, name, setup)
        print(f"== {name}: {setup['doc']}  (log {r['log']})")
        ev = ("launched", "docked", "destroyed", "aborted", "departed", "recovered", "lost")
        tot = {k: 0 for k in ev}
        times = []
        for lines in r["runs"] or [[]]:
            for k in ev:
                tot[k] += _count(lines, k)
            t0 = next((float(l.split()[0]) for l in lines if len(l.split()) > 1 and l.split()[1] == "launched"), None)
            for l in lines:
                w = l.split()
                if len(w) > 1 and w[1] == "docked" and t0 is not None:
                    times.append(float(w[0]) - t0)
        n = max(1, len(r["runs"]))
        print("   " + ", ".join(f"{k} {tot[k]}" for k in ev) + f"  ({n} run{'s' if n > 1 else ''})" + (f"; docked after {min(times):.0f}-{max(times):.0f} s (mean {sum(times) / len(times):.0f})" if times else ""))
        # the boats' own clock (what the minds are told: AstraBoardCraft::FlightEtaS) against what the first boat of each run did: from leaving the bay to the way in being cut open
        import re as _re
        errs = []
        for lines in r["runs"]:
            est = next((float(m.group(1)) for l in lines for m in [_re.search(r"the first flies ~(\d+) s", l)] if m), None)
            t0 = next((float(l.split()[0]) for l in lines if len(l.split()) > 2 and l.split()[1] == "launched" and l.split()[2] in ("Skiff", "Kestrel") and l.split()[3] == "1"), None)
            t1 = next((float(l.split()[0]) for l in lines if len(l.split()) > 2 and l.split()[1] == "docked" and l.split()[3] == "1"), None)
            if est is not None and t0 is not None and t1 is not None:
                errs.append((est - 3.0, t1 - t0))
        if errs:
            print(f"   the boats' clock said {sum(e for e, _ in errs) / len(errs):.0f} s from the bay to the cut in, the flight took {sum(g for _, g in errs) / len(errs):.0f} s (worst difference {max(abs(e - g) for e, g in errs):.0f} s over {len(errs)} runs)")
        if a.trace and r["runs"]:
            for l in r["runs"][0]:
                print("     " + l)
        for k, v in setup["expect"].items():
            want = v * n
            ok = tot[k] == want
            print(f"   {'ok  ' if ok else 'FAIL'} {k}: {tot[k]} (expected {want})")
            bad += 0 if ok else 1
        if name.startswith("pd") or name.startswith("kpd") or name == "cap":
            launched = max(1, tot["launched"])
            print(f"   {tot['docked']} of {tot['launched']} skiffs docked ({100.0 * tot['docked'] / launched:.0f}%), {tot['destroyed']} destroyed")
    print("CRAFT VERDICT:", "PASS" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------------------------------------------------------- the assaults: boats, scenes and what becomes of the men (the host's side)
# The war bench's world has the battle and the board host but no life aboard (no roster marines: the boarders' enemies are nameless men, the Aquila's marines of an outbound assault are
# nameless too) and runs the game's clock about two thousand times too fast for the plans the host reads on a worker: the commands are given late (11 000 s), when they are read.
_AQ = "astra.war.scenario aquila_only aquila"
_NOFATE = "astra.board.takeover_fatal 0"
ASSAULT_SETUPS = {
    # the Mandate's two skiffs from a raider at the Aquila's port beam (shields down, point defence off): the scene begins when the first boat is out, each hatch cuts open as its boat latches
    "in": dict(doc="two skiffs from a raider at the Aquila: the alarm, the hatches (her airlocks), the boarders in", seconds=11600,
               exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;{_NOFATE}",
               at="11000=astra.cmd set_shields {'mode':'off'}|11000=astra.board.pd aquila 0|11001=astra.board.assault in M1 - 2 port",
               expect=[r"order \d+: Raider launches 2 Skiffs", r"launched Skiff 1", r"has launched 2 assault craft at the Aquila", r"docked Skiff 1", r"the hull is cut open at", r"Boarding Alpha|Ferry Guard Alpha|boarders hold|boarders are beaten"]),
    # the operation as the Mandate's admiral reads it while it is under way, and his recall with its reason as the bridge hears it (the first in-game test: an admiral recalled a launch his staff had made, with nothing said)
    "in_recall": dict(doc="a launch from the console is the Mandate's own operation (who sent it, what the boats met) and a recall says who recalled the boats and why", seconds=11300,
                      exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;{_NOFATE}",
                      at="11000=astra.cmd set_shields {'mode':'off'}|11000=astra.board.pd aquila 0|11001=astra.board.assault in M1 - 2 port|11012=astra.board.options 1|"
                         "11014=astra.board.recall Archon_Varek_Solm the Aquila's marines are at the breach and I will not feed them skiffs",
                      expect=[r"order \d+: Raider launches 2 Skiffs", r"options: .*\"ordered_by\":\"the Mandate's command staff\"", r"\"met_at_launch\":\{[^}]*\"her_shield_on_that_face_pct\":0[^}]*\"her_point_defence_channels\":0",
                              r"Raider recalls her boats: the Aquila's marines are at the breach and I will not feed them skiffs", r"not one boarder reached the ship|the boats of order 1 are told to go home"]),
    # the Captain's drill (ABBORDAGGI-3): in play every boat is stopped (the Falcons, the Praetorian's point defence, the shield the crew raises again: all correct); the drill holds those off for the length of
    # one assault so that the boats can be watched latching and the fight in the corridors. `in_play` is the same war with no drill: the boats are stopped.
    "in_drill": dict(doc="the Captain's drill: her shield up on the port beam, a Praetorian with point defence and four fighters on cap beside her, the crew's orders as they are — and both skiffs latch", seconds=11700,
                     exec=f"{_AQ};astra.war.spawn praetorian astra -0.3 -1.6 0 0 id=A1 name=Picket static hold passive;astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;astra.war.wing A1 fighter 4 cap;{_NOFATE}",
                     at="11000=astra.board.drill port 2 M1 2|11040=astra.cmd set_shields {'mode':'balanced'}",
                     expect=[r"drill: on", r"drill ordered: drill:", r"order \d+: Raider launches 2 Skiffs", r"launched Skiff 1", r"launched Skiff 2", r"docked Skiff 1", r"docked Skiff 2", r"the hull is cut open at"]),
    "in_play": dict(doc="the same war with no drill: the shield holds the boats off the hull (and the Praetorian's point defence and the fighters have their say): the boats are stopped, as they should be", seconds=11500,
                    exec=f"{_AQ};astra.war.spawn praetorian astra -0.3 -1.6 0 0 id=A1 name=Picket static hold passive;astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;astra.war.wing A1 fighter 4 cap;{_NOFATE}",
                    at="11000=astra.board.assault in M1 - 2 port",
                    expect=[r"launched Skiff 1", r"(aborted|destroyed) Skiff", r"not one boarder reached the ship"]),
    # the same, one boat: a lone skiff against a shield that is up on that face: it holds off and turns back; nobody comes aboard
    "in_shield": dict(doc="a skiff at a shield that holds: it turns back, no boarder comes", seconds=11400,
                      exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;{_NOFATE}",
                      at="11000=astra.board.pd aquila 0|11001=astra.board.assault in M1 - 1 port",
                      expect=[r"order \d+: Raider launches 1 Skiff", r"aborted Skiff 1", r"not one boarder reached the ship"]),
    # our marines (nameless, in a world without life) in two Kestrels from the Aquila at a Mandate hulk: the scene is the hulk's own plan, run by the simulation alone
    "out": dict(doc="two Kestrels from the Aquila at a hulk of the Mandate: the marines cut in, the fight on her decks, the boats home", seconds=11800,
                exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                at="11000=astra.board.disable M1|11001=astra.board.assault out M1 - 2 port",
                expect=[r"order \d+: the Aquila launches 2 Kestrels", r"docked Kestrel 1", r"has latched to Hulk", r"has cut in at", r"Hulk is ours|boarding of Hulk has failed|have broken off|has gone quiet"]),
    # the same, with the Captain in the first Kestrel (a test Captain with no pawn: the ride, the other ship's decks made solid round him, the way home)
    "out_ride": dict(doc="the Captain rides with the marines: the troop bay, the lock of the hulk, her decks made solid, the boat home, the bay of Deck 8", seconds=12000,
                     exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                     at="11000=astra.board.disable M1|11000=astra.board.testcaptain 0 0 0|11001=astra.board.assault out M1 - 2 port - ride",
                     expect=[r"the Captain rides with the marines in Kestrel 1", r"the Captain is aboard Hulk with the marines", r"Hulk is ours|boarding of Hulk has failed|have broken off|has gone quiet",
                             r"the Captain is called back to the boat", r"the Captain is back aboard the Aquila"]),
    # a ship the war has shot at (FLOTTA-VIVA's inside, made by the blows that get through): the scene starts from the state it left her in, and the Captain rides along into her dark and burning rooms
    "out_war": dict(doc="the marines (and the Captain) aboard a ship the war has shot up: her people alive where they are, the bulkheads she shut, her rooms without power and on fire", seconds=12000,
                    exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Wreck static hold passive;{_NOFATE}",
                    at="2=astra.board.strip M1|3=astra.war.fleet pound M1 port 70 12 kinetic|60=astra.war.fleet pound M1 port 70 10 explosive|11000=astra.board.disable M1|11000=astra.board.testcaptain 0 0 0|11001=astra.board.assault out M1 - 2 port - ride",
                    expect=[r"the war has left her \d+ of her people under arms", r"the Captain is aboard Wreck with the marines", r"Wreck is ours|boarding of Wreck has failed|have broken off|has gone quiet", r"the Captain is back aboard the Aquila"]),
    # the decks dressed (ABBORDAGGI-3): in a headless run the content has none of the kit's meshes, so every piece is the engine's cube (astra.board.dress 3) and everything the dressing makes in the world is made
    # and counted all the same: the instances of each kind, the boxes of the props, the lamps (and the lights that follow the Captain), the door signs, the fallen, the flames and sparks of the rooms the war burnt.
    # (The Captain is aboard from about 11 220 s, or from about 11 600 s when the worker that reads the plan is slow: `astra.board.info` is asked all along, one of the answers is in the fight.)
    "out_dress": dict(doc="the Captain aboard a ship the war has shot up with her decks dressed (the kit's pieces as cubes): what the dressing made, counted by the boarding's info", seconds=12000,
                      exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Wreck static hold passive;{_NOFATE};astra.board.dress 3",
                      at="2=astra.board.strip M1|3=astra.war.fleet pound M1 port 70 12 kinetic|60=astra.war.fleet pound M1 port 70 10 explosive|11000=astra.board.disable M1|11000=astra.board.testcaptain 0 0 0|"
                         "11001=astra.board.assault out M1 - 2 port - ride|11230=astra.board.info|11250=astra.board.info|11270=astra.board.info|11290=astra.board.info|11630=astra.board.info|11650=astra.board.info|11670=astra.board.info|11690=astra.board.info|11710=astra.board.info|11730=astra.board.info",
                      expect=[r"the Captain is aboard Wreck with the marines", r"decks dressed: \d+ rooms, \d+ kit instances \(\d+ wall, \d+ ceiling, \d+ floor, \d+ opening, \d+ prop, \d+ fallen\), \d+ lamps", r"the Captain is back aboard the Aquila"]),
    # a station is a place of the system (SPAZIO-VIVO's fixtures: Keeper Station, the Arsenal, a refinery, a mine), not a ship of this war: no boat is flown at it and none from it
    # (the war bench has no living space to make one: a ship is made a fixture, as the war sees them)
    "fixture": dict(doc="boats at a place of the system and from it: refused with the reason, nothing flies", seconds=11200,
                    exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Keeper static hold passive;{_NOFATE}",
                    at="2=astra.board.fixture M1|11001=astra.board.assault out M1 - 2 port|11002=astra.board.assault in M1 - 1|11003=astra.board.assess aquila M1|11004=astra.board.assess M1 aquila",
                    expect=[r"assault refused: Keeper is a place of the system \(a station\)", r"target Keeper cannot be boarded: she is a place of the system", r"carrier [^;]*cannot: there is no such carrier"]),
    # an Acheron with her power and her point defence up: the marines' boats are shot at on the way in
    "out_pd": dict(doc="the marines' boats against a ship that shoots back: how many get through", seconds=11600,
                   exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Raider static hold passive;{_NOFATE}",
                   at="11000=astra.board.strip M1|11001=astra.board.assault out M1 - 2 port",
                   expect=[r"order \d+: the Aquila launches 2 Kestrels"]),
}
# ABBORDAGGI-4: the Captain who decides to go after the order was given (`board_ship join`, the XO's), and the recall with the marines on her decks (they come out by their hatches, the boats let go
# when they are aboard). The times are the bench's: the plan is read on a worker, so the boats leave a little after the order; a join before they leave is a ride, one after is refused with the way left to him.
ASSAULT_SETUPS["out_join"] = dict(doc="the Captain says he comes after the order, before the boats leave the bay: he rides in the first Kestrel (a test Captain with no pawn)", seconds=12000,
                                  exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                                  at="11000=astra.board.disable M1|11000=astra.board.testcaptain 0 0 0|11001=astra.board.assault out M1 - 2 port|11002=astra.board.join",
                                  expect=[r"join ok: the Captain goes with the marines: he rides in the first Kestrel", r"the Captain rides with the marines in Kestrel 1", r"the Captain is aboard Hulk with the marines",
                                          r"Hulk is ours|boarding of Hulk has failed|have broken off|has gone quiet", r"the Captain is back aboard the Aquila"])
ASSAULT_SETUPS["out_join_late"] = dict(doc="the Captain says he comes when the boats are out of the bay: no boat takes a man in flight, he is told when they are at her hull and that the Chief can beam him then", seconds=11900,
                                       exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                                       at="11000=astra.board.disable M1|11000=astra.board.testcaptain 0 0 0|11001=astra.board.assault out M1 - 2 port|11200=astra.board.join|11400=astra.board.join",
                                       expect=[r"join refused: the Kestrels are already out of the bay.*no boat takes the Captain in flight\. When they are latched at her hatches the Chief can beam him aboard"])
ASSAULT_SETUPS["out_recall"] = dict(doc="the boarding is called off with the marines on her decks: they come out by their hatches, then the boats let go and fly home with them", seconds=12000,
                                    exec=f"{_AQ};astra.war.spawn acheron mandate 0 -3 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                                    at="11000=astra.board.disable M1|11001=astra.board.assault out M1 - 2 port|11215=astra.board.recall the_Captain called_off|11235=astra.board.info",
                                    expect=[r"ok: the marines are called out of her decks: \d+ squads", r"the marines are called out of her decks: back to the boats by their hatches",
                                            r"the marines have broken off and are back in their boats|Hulk is ours", r"departed Kestrel 1", r"recovered Kestrel 1", r"is back in the boat bay: \d+ marines aboard"])
# the pace of the whole operation at the distances a battle is fought at (ABBORDAGGI-4): the order, the muster, the flight, the cut in, the fight, the flight home
for _km in (10, 20, 40, 80):
    ASSAULT_SETUPS[f"out_{_km}"] = dict(doc=f"the marines in two Kestrels at a hulk {_km} km away: how long from the order to the cut in, and the boats home", seconds=11900 + 4 * _km,
                                        exec=f"{_AQ};astra.war.spawn acheron mandate 0 -{_km} 0 90 id=M1 name=Hulk static hold passive;{_NOFATE}",
                                        at="11000=astra.board.disable M1|11001=astra.board.assault out M1 - 2 port",
                                        expect=[r"order \d+: the Aquila launches 2 Kestrels", r"docked Kestrel 1", r"has cut in at", r"Hulk is ours|boarding of Hulk has failed|have broken off|has gone quiet", r"recovered Kestrel 1"])


def _assault_run(a, name: str, setup: dict) -> dict:
    import re
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / f"assault_{name}.log"
    out = OUT / f"assault_{name}.json"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraWarSim", f"-seconds={setup['seconds']}", "-step=0.1", "-every=50", f"-out={out}", f"-seed={a.seed}", f"-seeds=1",
            f"-exec={setup['exec']}", f"-at={setup['at']}", "-nullrhi", "-unattended", "-nosound", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        try:
            p.wait(timeout=a.timeout)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    if sys.platform != "win32":
        subprocess.run(["pkill", "-f", f"CrashReportClient.*pid-{p.pid}"], check=False)
    lines = []
    for l in log.read_text(errors="replace").splitlines():
        for tag in ("[Boarding]", "[Board]"):
            if tag in l:
                lines.append(l[l.find(tag):].strip())
                break
    return {"log": log, "lines": lines, "code": p.returncode, "re": re}


def cmd_assault(a: argparse.Namespace) -> int:
    names = list(ASSAULT_SETUPS) if a.setup == "all" else [a.setup]
    bad = 0
    for name in names:
        setup = ASSAULT_SETUPS[name]
        r = _assault_run(a, name, setup)
        print(f"== {name}: {setup['doc']}  (log {r['log']}, exit {r['code']})")
        keep = [l for l in r["lines"] if not any(w in l for w in ("[Board] ready", "plan of the", "corner slots", "the Aquila's hatches", "bench: pd", "bench: strip"))]
        for l in keep[-(a.lines):]:
            print("   " + l[:230])
        text = "\n".join(r["lines"])
        # the pace: the boats' own times against what the order said (the minds are told the same words)
        re = r["re"]
        def _t(kind: str, who: str = "1"):
            m = re.search(rf"\[Boarding\]\s+([\d.]+) {kind} (?:Kestrel|Skiff) {who} ", text)
            return float(m.group(1)) if m else None
        t_l, t_d, t_dep, t_rec = _t("launched"), _t("docked"), _t("departed"), _t("recovered")
        span = r"(\d+ min(?: \d+ s)?|\d+ s)"
        said = re.search(rf"the boats leave the bay in {span} and the first is at her hull and cutting in {span} from this order", text)
        if t_l is not None and t_d is not None:
            print(f"   pace: bay -> way in cut open {t_d - t_l:.0f} s" + (f"; home {t_rec - t_dep:.0f} s after letting go" if t_dep is not None and t_rec is not None else "")
                  + (f"; the order said: leave in {said.group(1)}, cut in {said.group(2)} from the order" if said else ""))
        for rx in setup["expect"]:
            ok = bool(re.search(rx, text))
            print(f"   {'ok  ' if ok else 'FAIL'} /{rx}/")
            bad += 0 if ok else 1
    print("ASSAULT VERDICT:", "PASS" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


def cmd_report(a: argparse.Namespace) -> int:
    d = json.loads(Path(a.path).read_bytes().decode("utf-8-sig"))
    print(json.dumps(d, indent=1)[:12000])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | map | rules | duel | squad | flank | board | orders (the marines' orders, on request only) | fps (the Captain's arms, on request only) | plans | attack (other ships' plans and the marines aboard one, on request only) | interior (every class's plan made solid and the simulation's routes walked through it, on request only) | war (a ship the war has shot at, boarded, on request only) | dress (every class's decks dressed: instances and triangles for the ship, each deck and the ring round a Captain against the plain boxes, the soldiers' ways clear of the props, the doors, no one placed in a prop; on request only)")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--seeds", type=int, default=20, help="how many fights of each kind (seeds seed .. seed+seeds-1)")
    r.add_argument("--boarders", type=int, default=0, help="board: the size of the boarding party of the first setup (default 10, one skiff)")
    r.add_argument("--set", default="", help='tuning, "MandateSkill=0.8,HoldS=60,bFlank=0"')
    r.add_argument("--setup", type=int, default=-1, help="board: run only this setup (0..5)")
    r.add_argument("--trace", action="store_true", help="print the fights' events and a line a squad every five seconds (use with --seeds 1)")
    r.add_argument("--out", default="Saved/Boarding/run.json")
    r.add_argument("--class", dest="klass", default="", help="plans/attack: the ship's class (acheron, styx, lethe, praetorian, vigilant)")
    r.add_argument("--fpsset", default="", help="fps: try other places and anchors without touching the table, \"rifle.hip=84,17,-10;rifle.hipturn=-3,-13,0;rifle.shoulder_l=62,-20,-42\" (keys: rifle./pistol. hip hipturn ads low lowturn gripl fov shoulder_r shoulder_l; pole_r pole_l for both)")
    r.add_argument("--fpsposes", default="", help="fps: write the engine's poses (idle, draw, reload, dry fire) to this JSON file, for the offline preview")
    r.add_argument("--dump", default="", help="interior: write the solids of each class's plan (JSON, for the offline view) into this directory; dress: the dressing of the rooms round --focus (art/blender/board_kit.py --dump renders it)")
    r.add_argument("--focus", default="", help="dress --dump: the place the dumped rooms are round, \"x,y,z\" in cm (default: where the first boat docks)")
    r.add_argument("--hurt", action="store_true", help="dress --dump: dump the rooms as the war would leave them (dark, burning, gutted) instead of as built")
    r.add_argument("--timeout", type=int, default=1500)
    r.set_defaults(fn=cmd_run)
    c = sub.add_parser("craft")
    c.add_argument("--setup", default="all", choices=list(CRAFT_SETUPS) + ["all"])
    c.add_argument("--seed", type=int, default=1)
    c.add_argument("--seeds", type=int, default=6)
    c.add_argument("--trace", action="store_true", help="print the first run's events")
    c.add_argument("--timeout", type=int, default=900)
    c.set_defaults(fn=cmd_craft)
    s = sub.add_parser("assault", help="the boats' boardings in the war bench (the host's side: the order, the scene, the outcome)")
    s.add_argument("--setup", default="all", choices=list(ASSAULT_SETUPS) + ["all"])
    s.add_argument("--seed", type=int, default=1)
    s.add_argument("--lines", type=int, default=60, help="how many of the last log lines to print")
    s.add_argument("--timeout", type=int, default=900)
    s.set_defaults(fn=cmd_assault)
    p = sub.add_parser("report")
    p.add_argument("path", nargs="?", default="Saved/Boarding/run.json")
    p.set_defaults(fn=cmd_report)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
