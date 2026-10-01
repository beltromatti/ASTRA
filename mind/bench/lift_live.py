"""The lifts' voice against the real crew model and a scripted game (a few tenths of a cent a scene; `--budget` stops it).

    cd mind && .venv/bin/python -m bench.lift_live [--budget 0.05] [--only deck_number] [--model deepseek/...]

A fake game connects to the real `Mind` (the real crew, router and voice stage with a fake synthesiser). The Captain's words are scripted, with the game's
`context.lift` of the car he is inside (the row the headless bench prints: `UnrealEditor-Cmd -run=AstraLiftSim -scenario=voice`), in the languages the game is played in.
The fake game answers `lift_go` like the game does (`UAstraLiftSubsystem::GoByVoice`): it accepts a stop of the car and refuses anything else. What a machine can check is
checked: the stop the Captain meant (a number, a place, a relative word, a section), no call when the car does not serve it or the words were for an officer, the speaker
(`computer`, never an officer), one short line and the Captain's language; whether the line reads well is for the ear, from the printout. The key is read like the other live
benches do (the environment, the repository's .env, in a worktree the main checkout's), never printed."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flight_live import _key_from_main_env  # noqa: E402,F401  (reads the key before the client is made)
from astra_mind import models  # noqa: E402
from astra_mind.local_ship import LocalShip  # noqa: E402
from bench.lift_unit import IN_CAR, LIFT  # noqa: E402
from bench.stations_server import FakeGame, FakeTTS  # noqa: E402

SHUTTLE = {"car": "spine_shuttle", "name": "Spine Shuttle", "kind": "shuttle", "at": "sec_a", "moving": False,
           "stops": [{"id": f"sec_{k}", "label": f"SECTION {k.upper()}", "places": p} for k, p in
                     (("a", ["Forward Stores"]), ("b", ["Starboard Lobby"]), ("c", ["Mess Hall Concourse"]), ("d", []), ("e", ["Medbay Concourse"]), ("f", []), ("g", []), ("h", ["Aft Stores", "Hangar Gate"]))]}


def at(stop: str, **kw: Any) -> dict[str, Any]:
    return {**IN_CAR, "lift": {**LIFT, "at": stop, **kw}}


# someone riding the car with the Captain, facing him (a body of the life simulation: what ListenersJson sends); the Captain's words to the ship's computer must not be taken for his
RIDER = {"id": "npc412", "name": "Crewman Elias Brandt", "rank": "Crewman", "gender": "m", "dept": "logistics", "home": "Earth", "job": "supply clerk", "watch": "Gold",
         "doing": "riding Turbolift 1 to Deck 4", "place": "Turbolift 1", "dist_m": 0.9, "angle_deg": 5, "facing": True, "memory": [], "friends": []}


def with_rider(stop: str) -> dict[str, Any]:
    return {**at(stop), "people": [RIDER], "in_earshot": [RIDER["id"]], "facing": RIDER["id"]}


# name, the Captain's words, language, the context, the stop expected (None: no call), who must speak ("computer", or an officer, or None), a pattern the line must hold (any language)
SCENES: list[tuple[str, str, str, dict[str, Any], str | None, str | None, str]] = [
    ("deck_number", "Deck seven.", "en", at("d1"), "d7", "computer", r""),
    ("place_it", "Portami in sala macchine.", "it", at("d1"), "d7", "computer", r"(?i)macchin|ponte sette|7|sette"),
    ("place_fr", "Emmène-moi à l'infirmerie.", "fr", at("d3"), "d6", "computer", r"(?i)infirmerie|pont|6|six"),
    ("one_up", "Eine Etage höher, bitte.", "de", at("d4"), "d3", "computer", r""),
    ("the_bridge", "Take me to the bridge.", "en", at("d7"), "d1", "computer", r"(?i)bridge|deck one|command"),
    ("hangar_it", "Al ponte di volo, grazie.", "it", at("d2"), "d9", "computer", r""),
    ("not_served", "Take me to Deck twelve.", "en", at("d1"), None, "computer", r"(?i)twelve|12|not|nine|serve"),
    ("for_the_xo", "Number One, status?", "en", at("d4"), None, None, r""),
    ("shuttle", "Section C, please.", "en", {**IN_CAR, "lift": SHUTTLE}, "sec_c", "computer", r""),
    # with someone aboard who faces him: the words for the computer are still the computer's, and the words for the rider are the rider's
    ("rider_deck", "Deck seven.", "en", with_rider("d1"), "d7", "computer", r""),
    ("rider_place_it", "Portami in sala macchine.", "it", with_rider("d1"), "d7", "computer", r""),
    ("rider_chat", "Da quanto sei a bordo, marinaio?", "it", with_rider("d1"), None, "npc412", r""),
]


class Game(FakeGame):
    """The fake game that answers the lift tool as the game does, and notes when the mind first moved."""

    def __init__(self, lift: dict[str, Any]) -> None:
        super().__init__()
        self.lift = lift
        self.t0 = time.perf_counter()
        self.t_command = 0.0
        self.t_line = 0.0

    async def send(self, data: Any) -> None:
        if isinstance(data, bytes):
            return
        msg = json.loads(data)
        now = time.perf_counter() - self.t0
        if msg.get("type") == "line" and not self.t_line:
            self.t_line = now
        if msg.get("type") == "command" and msg.get("name") == "lift_go":
            self.sent.append(msg)
            self.commands.append(msg)
            self.t_command = self.t_command or now
            stop = next((s for s in self.lift["stops"] if s["id"] == (msg.get("args") or {}).get("destination")), None)
            res = ({"ok": True, "detail": f"{self.lift['name']} is going to {stop['label']}" + (f" · {stop['deck_name'].upper()}" if stop.get("deck_name") else "") + " (about 12 s)"} if stop
                   else {"ok": False, "detail": f"{self.lift['name']} does not serve that: its stops are " + ", ".join(s["id"] for s in self.lift["stops"])})
            await self.inbox.put(json.dumps({"type": "command_result", "id": msg["id"], **res}))
            return
        await super().send(data)


async def main_async(a: argparse.Namespace) -> int:
    import astra_mind.server as server
    models.LEDGER.write_file = False
    if a.model:
        spec, _, provs = a.model.partition("@")
        models.ROLES["crew"] = replace(models.ROLES["crew"], model=spec, providers=tuple(p for p in provs.split(",") if p) or None)
    failures = 0
    ran = 0
    for name, words, lang, ctx, want_stop, want_speaker, must in SCENES:
        if a.only and name not in a.only:
            continue
        if models.LEDGER.total >= a.budget:
            print(f"\nthe budget of {a.budget:.3f} $ is reached: stopping before {name}")
            break
        with mock.patch.object(server, "TTSEngine", FakeTTS):
            mind = server.Mind()                                                    # (a mind of its own for each scene: nothing carries over, as in a new game)
        mind.lang_file = mind.lang_file.parent / "captain_lang_test.txt"
        game = Game(ctx["lift"])
        tasks = [asyncio.create_task(mind.handle_client(game)), asyncio.create_task(mind.turn_worker()), asyncio.create_task(mind.voice.run())]
        try:
            await asyncio.sleep(0.1)
            mind.agent.history.clear()
            await game.push(type="ship_state", state=json.loads(json.dumps(LocalShip(stations=True, fight=False).snapshot())))
            await asyncio.sleep(0.2)
            game.sent.clear()
            game.commands.clear()
            before = models.LEDGER.total
            game.t0 = time.perf_counter()
            await game.push(type="player_text", text=words, lang=lang, context=ctx)
            last, quiet = 0, 0.0
            deadline = time.perf_counter() + a.wait
            while time.perf_counter() < deadline:                                   # until something was said and then nothing new for a while
                await asyncio.sleep(0.2)
                n = len(game.sent)
                if n != last:
                    last, quiet = n, 0.0
                elif n:
                    quiet += 0.2
                    if quiet >= 1.6:
                        break
            lines = game.lines()
            gone = [(m["args"].get("destination"), m["by"]) for m in game.commands]
            problems = []
            if want_stop is None and gone:
                problems.append(f"it should not have moved the car (went to {gone})")
            if want_stop is not None and [g for g, _ in gone] != [want_stop]:
                problems.append(f"expected a ride to {want_stop}, got {gone}")
            if want_stop is not None and any(by != "computer" for _, by in gone):
                problems.append(f"the order was not the computer's: {gone}")
            if want_speaker == "computer" and not any(s == "computer" for s, _ in lines):
                problems.append("the ship's computer did not answer")
            if want_speaker not in ("computer",) and any(s == "computer" for s, _ in lines):
                problems.append("the computer answered words that were for an officer")
            if want_speaker == "computer" and any(s != "computer" for s, _ in lines):
                problems.append(f"an officer or a rider spoke in the lift: {[s for s, _ in lines if s != 'computer']}")
            if want_speaker not in (None, "computer") and not any(s == want_speaker for s, _ in lines):
                problems.append(f"{want_speaker} did not answer")
            if not lines:
                problems.append("nobody answered")
            if must and lines and not any(re.search(must, t) for _, t in lines):
                problems.append(f"the line should hold /{must}/")
            if any(len(t.split()) > 28 for _, t in lines):
                problems.append("a line is longer than one short sentence or two")
            ran += 1
            failures += bool(problems)
            print(f"\n=== {name}: [{lang}] {words}   (car at {ctx['lift'].get('at')}, {ctx['lift']['name']})   {'FAIL' if problems else 'ok'}")
            for m in game.commands:
                print(f"   command {m['name']} by {m['by']}: {json.dumps(m['args'], ensure_ascii=False)}   (at {game.t_command:.2f} s)")
            for spk, text in lines:
                print(f"   {spk:<9} {text}" + (f"   (at {game.t_line:.2f} s)" if text == lines[0][1] else ""))
            for p in problems:
                print(f"   !! {p}")
            print(f"   (spent ${models.LEDGER.total - before:.4f})")
        finally:
            await game.inbox.put(None)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await mind.llm.close()
    print(f"\n{ran - failures}/{ran} as expected; total spend ${models.LEDGER.total:.4f}: {models.LEDGER.summary()}")
    return 1 if failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=0.05)
    ap.add_argument("--wait", type=float, default=12.0, help="seconds each scene is given at most")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("-v", "--verbose", action="store_true", help="the mind's own log (what it does with each utterance)")
    ap.add_argument("--model", default="", help="a model (and providers: model@prov1,prov2) for the crew role, for a comparison")
    args = ap.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="      log %(name)s: %(message)s")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
