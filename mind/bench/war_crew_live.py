"""The crew's choice between a REQUEST to an allied captain (comms' `fleet_request`) and the Captain's DIRECT ORDER (the XO's `group_order`), and what the
allied captain does with it, against the real models and a scripted game (a few tenths of a cent a turn; `--budget` stops it).

    cd mind && .venv/bin/python -m bench.war_crew_live [--budget 0.05]

A fake game connects to the real `Mind` (the real crew, the real war minds, the real voice stage with a fake synthesiser). The ship state carries the
battle groups; the Captain's words are scripted; what is printed is what the crew called, what the allied captain ordered and said, and the cost."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astra_mind import models  # noqa: E402
from bench.stations_server import FakeGame, FakeTTS  # noqa: E402
from bench.war_server import battle_state  # noqa: E402

SCENES = [
    ("a request in plain words", "Praetorian, concentrate your fire on the Acheron.", None),
    ("an explicit order", "Praetorian, that is an order: pull back to the Aquila's port quarter and cover us.", None),
    ("the whole fleet", "All ships, fire at will.", None),
    ("a request that cannot be done", "Vigilant, ram the Acheron.", None),
    ("words for the bridge", "Helm, bring the bow onto the strike group.", None),
]


async def main_async(a: argparse.Namespace) -> None:
    import astra_mind.server as server
    models.LEDGER.write_file = False
    models.LEDGER.cap = a.budget
    with mock.patch.object(server, "TTSEngine", FakeTTS):
        mind = server.Mind()
    mind.lang_file = mind.lang_file.parent / "captain_lang_test.txt"
    game = FakeGame()
    tasks = [asyncio.create_task(mind.handle_client(game)), asyncio.create_task(mind.turn_worker()), asyncio.create_task(mind.voice.run())]
    await asyncio.sleep(0.1)
    try:
        st = battle_state(mandate=True)
        st["captain"] = "on the bridge"
        await game.push(type="ship_state", state=st)
        await asyncio.sleep(0.3)
        mind.war.clock = lambda t=mind.war.clock() + 10: t                       # (the first look of the picket's captain: the battle is under way)
        await game.push(type="ship_state", state=st)
        await asyncio.sleep(4.0)
        for name, words, _ in SCENES:
            game.sent.clear()
            game.commands.clear()
            before = models.LEDGER.total
            await game.push(type="player_text", text=words)
            await asyncio.sleep(9.0)
            print(f"\n=== {name}: Captain: {words}")
            for m in game.commands:
                args = {k: v for k, v in m["args"].items() if k not in ("side",)}
                print(f"   command {m['name']} by {m['by']}: {json.dumps(args, ensure_ascii=False)}")
            for sp, tx in game.lines():
                print(f"   {sp}: {tx}")
            print(f"   (spent ${models.LEDGER.total - before:.4f})")
        print(f"\ntotal spend ${models.LEDGER.total:.4f}: {models.LEDGER.summary()}")
    finally:
        await game.inbox.put(None)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await mind.llm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=0.05)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
