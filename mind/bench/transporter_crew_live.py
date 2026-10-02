"""The bridge crew and the Transporter Room's Chief together, against the real models and a scripted game (a few tenths of a cent a turn; `--cap` stops it).

    cd mind && ASTRA_HOME=/path/to/the/main/checkout .venv/bin/python -m bench.transporter_crew_live [--cap 0.04] [--only ops_surface_window]

A fake game connects to the real `Mind` (the real crew, router, Chief and voice stage with a fake synthesiser). The ship state is the crew's with the Transporter Room's card exactly as the
game wrote it (bench/fixtures/transporter, from tools/transport.py run --scenario world); the Captain's words are scripted (on the bridge, or in the room with the Chief in earshot); the
game answers the Chief's console commands from that same card the way the real one does (bench.transporter_live.console: a transport the card says cannot be done is refused with the
reason, one that can is accepted). What is printed: who spoke (the bridge's officers, the Chief), the commands that reached the game with who gave them, and the cost by role. What a
machine can check is checked (the order reaches the Chief and the console, a refusal is told, the bridge stays out of what is the Chief's, nobody says it twice); whether the lines are
in character and never invent a number is read by ear, from the printout. The key is read like the other live benches do (the environment, the repository's .env, in a worktree the main
checkout's), never printed."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.flight_live import _key_from_main_env  # noqa: E402,F401  (reads the key before the client is made)
from astra_mind import models  # noqa: E402
from astra_mind.local_ship import LocalShip  # noqa: E402
from bench.stations_server import FakeGame, FakeTTS  # noqa: E402
from bench.transporter_live import card, console  # noqa: E402

CTX_BRIDGE = {"place": "bridge", "channel": None}
CTX_ROOM = {"place": "transporter room", "place_name": "Transporter Room", "channel": None, "in_earshot": ["xfer_chief"], "facing": "xfer_chief"}

SURFACE = {"world": "New Ravenna", "kind": "ocean world", "field": "Port Aurelius Field", "captain_here": False}
CONTACTS_PEACE = [{"id": "T-02", "name": "ASN Vigilant (CVC-02)", "class": "vigilant", "status": "friendly", "range_km": 3.1, "bearing_deg": 70, "hull_pct": 100},
                  {"id": "T-01", "name": "ASN Praetorian", "class": "praetorian", "status": "friendly", "range_km": 4.2, "bearing_deg": 120, "hull_pct": 100}]
CONTACTS_AWAY = [{"id": "A-01", "name": "Acheron (allied)", "class": "acheron", "status": "friendly", "range_km": 15.0, "bearing_deg": 250, "hull_pct": 100}]
CONTACTS_BATTLE = [{"id": "A-01", "name": "Acheron (allied)", "class": "acheron", "status": "friendly", "range_km": 15.0, "bearing_deg": 250, "hull_pct": 100},
                   {"id": "M-01", "name": "Acheron (Mandate)", "class": "acheron", "status": "hostile", "range_km": 15.0, "bearing_deg": 40, "hull_pct": 100}]

# name, the card the game writes, the contacts, the Captain's words, their language, the context the game sends, what is expected
SCENES: list[dict[str, Any]] = [
    dict(name="ops_surface_window", card="idle", contacts=CONTACTS_PEACE, words="Ops, portami sulla superficie del pianeta, con la finestra degli scudi.", lang="it", ctx=CTX_BRIDGE,
         commands=["transport"], arg_has="surface"),
    dict(name="ops_surface_plain", card="idle", contacts=CONTACTS_PEACE, words="Portami giù sul pianeta.", lang="it", ctx=CTX_BRIDGE, commands=[], arg_has=""),
    dict(name="battle_marines", card="battle", contacts=CONTACTS_BATTLE, words="XO, manda i marine sull'Acheron nemico, subito.", lang="it", ctx=CTX_BRIDGE, commands=[], arg_has="", nothing_accepted=True),
    dict(name="room_direct", card="idle", contacts=CONTACTS_PEACE, words="Chief, send me to Main Engineering.", lang="en", ctx=CTX_ROOM, commands=["transport"], arg_has="engineering"),
    dict(name="away_recall", card="away", contacts=CONTACTS_AWAY, words="Ops, bring the away team home.", lang="en", ctx=CTX_BRIDGE, commands=["transport"], arg_has="away"),
    dict(name="bridge_other", card="idle", contacts=CONTACTS_PEACE, words="Number One, give me a damage report.", lang="en", ctx=CTX_BRIDGE, commands=[], arg_has="", chief_silent=True),
]


class XportGame(FakeGame):
    """The game as the Chief's console meets it: the commands are answered from the card's options (the same answers the real room gives for what its card says)."""

    def __init__(self) -> None:
        super().__init__()
        self.answer = None
        self.results: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    async def send(self, data: Any) -> None:
        if isinstance(data, bytes):
            return
        msg = json.loads(data)
        self.sent.append(msg)
        if msg.get("type") == "command":
            self.commands.append(msg)
            if self.answer is not None and str(msg.get("name", "")).startswith(("transport", "crew_locate")):
                r = await self.answer(msg["name"], msg.get("args") or {}, str(msg.get("by", "")))
            else:
                r = {"ok": True, "detail": "done"}
            self.results.append((msg["name"], msg.get("args") or {}, r))
            await self.inbox.put(json.dumps({"type": "command_result", "id": msg["id"], "ok": bool(r.get("ok")), "detail": r.get("detail", "")}))


def state_for(sc: dict[str, Any]) -> dict[str, Any]:
    st = json.loads(json.dumps(LocalShip(stations=True, fight=sc["card"] == "battle").snapshot()))
    st["contacts"] = sc["contacts"]
    st["captain"] = "in the Transporter Room (Deck 5)" if sc["ctx"] is CTX_ROOM else "on the bridge"
    st["surface"] = SURFACE
    st["transporter"] = card(sc["card"])
    return st


async def main_async(a: argparse.Namespace) -> int:
    import astra_mind.server as server
    models.LEDGER.write_file = False
    models.LEDGER.cap = a.cap
    with mock.patch.object(server, "TTSEngine", FakeTTS):
        mind = server.Mind()
    mind.lang_file = mind.lang_file.parent / "captain_lang_test.txt"
    mind.xfer.store = Path(tempfile.mkdtemp(prefix="xfer_crew_live_")) / "journal.json"          # (the Chief's real journal is the campaign's: this run does not touch it)
    game = XportGame()
    tasks = [asyncio.create_task(mind.handle_client(game)), asyncio.create_task(mind.turn_worker()), asyncio.create_task(mind.voice.run())]
    await asyncio.sleep(0.1)
    bad = 0
    try:
        for sc in SCENES:
            if a.only and sc["name"] not in a.only:
                continue
            if models.LEDGER.total >= a.cap:
                print(f"\nthe cap of {a.cap:.3f} $ is reached: stopping")
                break
            mind.agent.history.clear()
            mind.exchange.reset()
            mind.xfer.reset()
            st = state_for(sc)
            game.answer = console(st["transporter"])
            await game.push(type="ship_state", state=st)
            await asyncio.sleep(0.3)
            game.sent.clear()
            game.commands.clear()
            game.results.clear()
            before = models.LEDGER.total
            by_role_before = dict(models.LEDGER.by_role)
            await game.push(type="player_text", text=sc["words"], lang=sc["lang"], context=sc["ctx"])
            await asyncio.sleep(a.wait)
            print(f"\n=== {sc['name']}: Captain ({sc['lang']}, {'in the room' if sc['ctx'] is CTX_ROOM else 'on the bridge'}): {sc['words']}")
            for name, args, r in game.results:
                by = next((m["by"] for m in game.commands if m["name"] == name and (m.get("args") or {}) == args), "?")
                print(f"   command {name} by {by}: {json.dumps(args, ensure_ascii=False)[:150]} -> {'ok' if r.get('ok') else 'REFUSED'}: {str(r.get('detail', ''))[:110]}")
            speakers: list[str] = []
            for m in game.sent:
                if m.get("type") == "line":
                    speakers.append(m["speaker"])
                    print(f"   {m['speaker']:<11} {m['text']}")
            spent = {r: round(c - by_role_before.get(r, 0.0), 5) for r, c in models.LEDGER.by_role.items() if c - by_role_before.get(r, 0.0) > 0}
            print(f"   (spent ${models.LEDGER.total - before:.4f}: {spent})")
            problems: list[str] = []
            transports = [c for c in game.results if c[0] == "transport"]
            for want in sc["commands"]:
                if not any(c[0] == want for c in game.results):
                    problems.append(f"no {want} command reached the game")
            if sc["arg_has"] and transports and not any(sc["arg_has"] in json.dumps(c[1]).lower() for c in transports):
                problems.append(f"no transport mentions {sc['arg_has']}")
            if sc.get("nothing_accepted") and any(c[2].get("ok") for c in transports):
                problems.append("a transport was accepted in a battle where the card said it could not be")
            if sc.get("chief_silent") and ("xfer_chief" in speakers or transports):
                problems.append("the Chief or the console took part in what was for the bridge")
            if not speakers:
                problems.append("nobody said anything")
            if len(transports) > 2:
                problems.append("the order was sent more than twice")
            if problems:
                bad += 1
                print("   PROBLEMS: " + "; ".join(problems))
        print(f"\ntotal spend ${models.LEDGER.total:.4f}: {models.LEDGER.summary()}")
    finally:
        await game.inbox.put(None)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await mind.llm.close()
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=float, default=0.04, help="stop when this many dollars are spent")
    ap.add_argument("--wait", type=float, default=14.0, help="seconds each scene is given")
    ap.add_argument("--only", action="append", default=[])
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
