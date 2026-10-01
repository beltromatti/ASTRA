"""The flight net and the bridge crew together, against the real models and a scripted game (a few tenths of a cent a turn; `--budget` stops it).

    cd mind && .venv/bin/python -m bench.flight_crew_live [--budget 0.06] [--only open_cover]

A fake game connects to the real `Mind` (the real crew, router, flight net and voice stage with a fake synthesiser). The ship state is the crew's with the flight groups; the
Captain's words are scripted, with the net open or closed, on the bridge or in a Falcon. What is printed is who spoke (the net's people, the bridge's officers), what reached the
flight console, and the cost by role: the point is that the right ones answer and nobody says it twice (Price does not echo a pilot, the pilots stay out of what is for the
bridge). The key is read like the other live benches do (the environment, the repository's .env, in a worktree the main checkout's), never printed."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flight_live import _key_from_main_env  # noqa: E402,F401  (reads the key before the client is made)
from astra_mind import models  # noqa: E402
from bench.flight_unit import FLYING, LOSS, WING, ship_state  # noqa: E402
from bench.stations_server import FakeGame, FakeTTS  # noqa: E402

CTX_OPEN = {"place": "bridge", "channel": None}
CTX_FALCON = {"place": "falcon", "pawn": "falcon", "channel": None}

# name, the net open?, the state, the Captain's words (None: a squadron event instead), the context the game sends
SCENES = [
    ("open_cover", True, {}, "Alpha Lead, copri il Vigilant.", CTX_OPEN),
    ("open_to_price", True, {}, "Price, lancia Bravo sull'Acheron.", CTX_OPEN),
    ("open_to_cag", True, {}, "CAG, com'è la situazione dei tuoi squadroni?", CTX_OPEN),
    ("open_to_helm", True, {}, "Timoniere, prua sull'Acheron.", CTX_OPEN),
    ("closed_to_pilot", False, {}, "Alpha Lead, copri il Vigilant.", CTX_OPEN),
    ("closed_open_it", False, {}, "Martin, apri il canale di volo.", CTX_OPEN),
    ("event_loss", False, {}, None, CTX_OPEN),
    ("cockpit_wing", False, {"captain": FLYING}, "Eagle 2, resta con me.", CTX_FALCON),
    ("cockpit_to_price", False, {"captain": FLYING}, "Price, dove sono i bandito più vicino?", CTX_FALCON),
]


async def main_async(a: argparse.Namespace) -> None:
    import astra_mind.server as server
    models.LEDGER.write_file = False
    models.LEDGER.cap = a.budget
    with mock.patch.object(server, "TTSEngine", FakeTTS):
        mind = server.Mind()
    mind.lang_file = mind.lang_file.parent / "captain_lang_test.txt"
    mind.flight.path = lambda: None
    game = FakeGame()
    tasks = [asyncio.create_task(mind.handle_client(game)), asyncio.create_task(mind.turn_worker()), asyncio.create_task(mind.voice.run())]
    await asyncio.sleep(0.1)
    try:
        for name, net, over, words, ctx in SCENES:
            if a.only and name not in a.only:
                continue
            mind.flight.reset()
            mind.flight.net_open = net
            mind.agent.history.clear()
            mind.exchange.reset()
            mind.flight.clock = lambda: 5000.0 + len(mind.flight.pulses) * 30.0           # (no gap between the scenes)
            st = ship_state(**over)
            await game.push(type="ship_state", state=st)
            await asyncio.sleep(0.3)
            if over.get("captain") == FLYING:
                await game.push(type="event", text=WING, report=True)
                await asyncio.sleep(0.2)
            game.sent.clear()
            game.commands.clear()
            before = models.LEDGER.total
            by_role_before = dict(models.LEDGER.by_role)
            if words is None:
                await game.push(type="event", text=LOSS, report=True)
                await asyncio.sleep(0.3)
                mind.flight.clock = lambda: 5000.0 + len(mind.flight.pulses) * 30.0 + 10.0
                await game.push(type="ship_state", state=st)
            else:
                await game.push(type="player_text", text=words, lang="it", context=ctx)
            await asyncio.sleep(a.wait)
            print(f"\n=== {name}: " + (f"Captain: {words}" if words else f"event: {LOSS[:70]}...") + f"   [net {'open' if net else 'closed'}{', in a Falcon' if over.get('captain') else ''}]")
            for m in game.commands:
                args = {k: v for k, v in m["args"].items() if k not in ("until",)}
                print(f"   command {m['name']} by {m['by']}: {json.dumps(args, ensure_ascii=False)}")
            for m in game.sent:
                if m.get("type") == "line":
                    print(f"   {m['speaker']:<11} {'(radio)' if m.get('channel') else '       '} {m['text']}")
            spent = {r: round(c - by_role_before.get(r, 0.0), 5) for r, c in models.LEDGER.by_role.items() if c - by_role_before.get(r, 0.0) > 0}
            print(f"   (spent ${models.LEDGER.total - before:.4f}: {spent})")
        print(f"\ntotal spend ${models.LEDGER.total:.4f}: {models.LEDGER.summary()}")
    finally:
        await game.inbox.put(None)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await mind.llm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=0.06)
    ap.add_argument("--wait", type=float, default=8.0, help="seconds each scene is given")
    ap.add_argument("--only", action="append", default=[])
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
