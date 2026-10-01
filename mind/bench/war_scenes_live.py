"""Two scenes against the real model (a few tenths of a cent each): what do the minds do when the picture says what the doctrine is about?

    cd mind && .venv/bin/python -m bench.war_scenes_live [--only aquila_fire,formation] [--runs 1]

  aquila_fire  the Aquila's shields and hull have gone down fast since the picket captain's last look, with the Mandate's cruiser and a destroyer inside
               laser reach of her and the picket six kilometres away: what does the captain order, and what does she say?
  formation    the Mandate's admiral at the first look of an equal fight of three ships against three, with the doctrine that also teaches the formation
               lever (`WarMinds.formation_doctrine`): does he order the line and the range it names?

Nothing goes to a game: every command the minds give is printed with the result the stub answers."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astra_mind import models  # noqa: E402
from astra_mind.openrouter import OpenRouter  # noqa: E402
from astra_mind.war_minds import WarMinds  # noqa: E402
from bench.war_minds_unit import ENEMIES, VANGUARD, astra_state, foe, group, mandate_state, member  # noqa: E402


class Clock:
    t = 100.0

    def __call__(self) -> float:
        return self.t


def contacts(hull: float, shield: float, hostile: list[tuple[str, str, float]]) -> dict[str, Any]:
    cs = [{"id": "T-01", "name": "ASN Praetorian", "status": "friendly", "range_km": 6.0, "bearing_deg": 25, "hull_pct": 100},
          {"id": "T-02", "name": "ASN Vigilant", "status": "friendly", "range_km": 6.5, "bearing_deg": 30, "hull_pct": 100}]
    for cid, cls, km in hostile:
        cs.append({"id": cid, "name": cls, "class": cls, "status": "hostile", "range_km": km, "bearing_deg": 240, "hull_pct": 90})
    return {"contacts": cs, "hull_pct": hull, "shields": {"strength_pct": shield}, "speed_mps": 120, "heading_deg": 45, "alert": "red"}


async def run_scene(name: str, llm: OpenRouter) -> None:
    clock = Clock()
    cmds: list[tuple[str, dict[str, Any]]] = []
    said: list[str] = []

    async def execute(n: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        cmds.append((n, {k: v for k, v in args.items() if k not in ("side", "by")}))
        return {"ok": True, "detail": f"{args.get('group', n)}: done"}

    async def say(speaker: str, text: str, lang: str, tone: str, **kw: Any) -> None:
        said.append(f"{speaker} ({tone}): {text}")

    before = models.LEDGER.total
    if name == "aquila_fire":
        w = WarMinds(llm, say, execute, lang=lambda: "en", clock=clock, sides=("astra",))
        picket = group("7th Fleet picket", 1, [member("T-01", "praetorian", missiles=24), member("T-02", "vigilant", missiles=12)], leader="T-01")
        enemies = [foe("group of T-21", [{"id": "T-21", "class": "acheron", "hull_pct": 90, "shields_pct": 86}, {"id": "T-22", "class": "styx", "hull_pct": 100,
                                                                                                                   "shields_pct": 100}], 6.0)]
        calm = astra_state([picket], enemies, None, **contacts(100, 100, [("T-21", "acheron", 14.0), ("T-22", "styx", 15.0)]))
        burning = astra_state([picket], enemies, None, **contacts(61, 8, [("T-21", "acheron", 2.4), ("T-22", "styx", 3.1), ("T-23", "styx", 5.0)]))
        w.feed(calm)
        clock.t += 9
        w.feed(calm)                                       # the first look
        await _settle(w)
        cmds.clear()
        said.clear()
        clock.t += 35
        w.feed(burning)
        await _settle(w)
        why = w.pulses[-1]["why"] if w.pulses else []
        print(f"\n=== aquila_fire: the Aquila went from 100% / 100% to 61% / 8% in 35 s, T-21 at 2.4 km and T-22 at 3.1 km from her, the picket 6 km away\n   woken by: {why}")
    else:
        w = WarMinds(llm, say, execute, lang=lambda: "en", clock=clock, sides=("mandate",), ops=False)
        w.formation_doctrine = True
        st = mandate_state([VANGUARD()], ENEMIES())
        w.feed(st)
        clock.t += 9
        w.feed(st)
        await _settle(w)
        print("\n=== formation: the Mandate's admiral at the first look of three ships against three (the doctrine with the formation lever)")
    for c in cmds:
        print(f"   order: {json.dumps(c[1], ensure_ascii=False)}")
    for line in said:
        print(f"   says:  {line}")
    if w.pulses:
        print(f"   log:   {w.recall('astra' if name == 'aquila_fire' else 'mandate')[-700:]}")
    print(f"   (spent ${models.LEDGER.total - before:.4f})")


async def _settle(w: WarMinds) -> None:
    for _ in range(200):
        await asyncio.sleep(0.1)
        if w.minds and not any(m.busy for m in w.minds.values()) and w.pulses:
            return


async def main_async(a: argparse.Namespace) -> None:
    models.LEDGER.write_file = True
    models.LEDGER.cap = a.cap
    llm = OpenRouter()
    try:
        for name in a.only.split(","):
            for _ in range(a.runs):
                await run_scene(name, llm)
        print(f"\ntotal this run ${models.LEDGER.total:.4f} (the log holds it all)")
    finally:
        await llm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="aquila_fire,formation")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--cap", type=float, default=0.75, help="stop spending at this many dollars (everything the log holds plus this run)")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
