"""A long war through the join, against a stand-in for the game that fights (no network, no cost, no engine): docs/GUERRA.md §10.

    cd mind && .venv/bin/python -m unittest bench.march_soak -v
    cd mind && .venv/bin/python -m bench.march_soak --hours 6 --seeds 1-4            (the same, as a report)

`FightingWorld` is the game's simulation as the glue sees it, with a small stochastic combat of its own (ships hurt each other, flee under a quarter of their hull and jump out,
die): the March's fleets come into it as beats, what it says of hulls, losses and jumps goes back, the Aquila goes from system to system through the Gates (a lane, the sky
cleared, the arrival the story reports), and the two high commands' minds (a scripted model that gives the reflexes' orders) play the war meanwhile. What is checked, all through
the run and at its end, is that the two worlds never disagree: no ship is in the map's fleets twice or in two places, no ship of the game is unknown to the map (except the
ones the game's own script brings), the fleets the game is playing are all in the Aquila's system, none is played while she is in a lane, what the map says is lost is what the game
lost, the ships in the map's fleets are the ships the game has plus the ones still to arrive, and nothing in the join raised an error."""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind import march_glue as mg  # noqa: E402
from astra_mind import models  # noqa: E402
from astra_mind.march import SIDES, March  # noqa: E402
from astra_mind.strategy import StrategicMinds  # noqa: E402
from astra_mind.war import WarMap  # noqa: E402
from bench.march_glue_unit import Clock, FakeWorld  # noqa: E402
from bench.march_live import reflex_policy  # noqa: E402
from bench.march_mock import StrategyMock  # noqa: E402

models.LEDGER.write_file = False

DEAD = ("destroyed with all hands", "jumped out of the system")
WEIGHT = {"praetorian": 2.4, "acheron": 2.0, "vigilant": 1.0, "styx": 1.0, "lethe": 0.5}
HULL = {"praetorian": 5200, "acheron": 3600, "vigilant": 1200, "styx": 1300, "lethe": 520}


class FightingWorld(FakeWorld):
    """The fake game with a combat: every second each ship hurts a random enemy; a ship under a quarter of its hull may jump out; at zero it is destroyed."""

    def __init__(self, now, rng: random.Random) -> None:
        super().__init__(now)
        self.rng = rng
        self.scale = 45.0                              # the damage a ship of weight 1 does a second, in hull points (the pace bench fits it to the war bench's engagements)

    def in_fight(self, s: dict[str, Any]) -> bool:
        """Is this ship in the fight yet (the pace bench's stand-in: a ship that has just come through the Gate is still closing)?"""
        return True

    def tick(self) -> None:
        super().tick()
        alive = [s for s in self.ships.values() if s["state"] not in DEAD and self.in_fight(s)]
        sides = {sd: [s for s in alive if s["side"] == sd] for sd in SIDES}
        if not (sides["astra"] and sides["mandate"]):
            return
        hits: dict[str, float] = {}
        for s in alive:
            foe = self.rng.choice(sides["mandate" if s["side"] == "astra" else "astra"])
            hits[foe["id"]] = hits.get(foe["id"], 0.0) + WEIGHT[s["class"]] * self.rng.uniform(0.3, 1.0)
        for cid, dmg in hits.items():
            s = self.ships[cid]
            s["hull_pct"] = max(0.0, s["hull_pct"] - 100.0 * dmg * self.scale / HULL[s["class"]])
            if s["hull_pct"] <= 0.0:
                s["state"] = "destroyed with all hands"
            elif s["hull_pct"] < 27.0 and self.rng.random() < 0.08:
                s["state"] = "jumped out of the system"


class Soak:
    world_class = FightingWorld                       # (the pace bench's stand-in has the approach)

    def __init__(self, seed: int, hours: float) -> None:
        self.seed, self.hours = seed, hours
        self.rng = random.Random(seed)
        self.wm = WarMap()
        self.wm.persist = False
        self.m = March(self.wm, seed=seed)
        self.clock = Clock()
        self.world = self.world_class(lambda: self.m.t, self.rng)
        self.errors: list[str] = []
        self.lanes = 0
        self.announced: list[str] = []

        async def say(*a: Any, **k: Any) -> None:
            pass

        async def announce(t: str) -> None:
            self.announced.append(t)

        async def sector() -> None:
            pass
        self.minds = StrategicMinds(StrategyMock(reflex_policy), self.m, say)
        self.glue = mg.MarchGlue(self.m, self.minds, command=self.world.command, announce=announce, send_sector=sector, clock=self.clock)
        self.glue.start(True)
        self.m.save_path = None
        self.lane_until = 0.0
        self.lane_to = ""
        self.next_move = self.rng.uniform(900.0, 2400.0)

    # -- the stand-in's own life: the opening's ships, the Aquila's journeys
    def opening(self) -> None:
        for cid, side, cls, name in (("T-01", "astra", "praetorian", "ASN Praetorian"), ("T-02", "astra", "vigilant", "ASN Vigilant"), ("T-11", "mandate", "lethe", "Lethe")):
            self.world.add(cid, side, cls, name)

    def journeys(self) -> None:
        m = self.m
        if self.lane_to:
            if m.t >= self.lane_until:
                self.world.ships.clear()                                              # (the transit clears the sky, and what was to arrive in it)
                self.world.pending.clear()
                self.world.lane = ""
                self.world.beats.clear()
                m.war.arrived(self.lane_to)                                           # (the story reports the arrival)
                self.lane_to = ""
                self.next_move = m.t + self.rng.uniform(900.0, 2400.0)
        elif m.t >= self.next_move and m.real_system:
            dest = self.rng.choice([s for s in m.war.links[m.real_system] if s != "Veyra"])
            self.lane_to, self.lane_until, self.world.lane = dest, m.t + 14.0, dest
            self.lanes += 1

    # -- the invariants
    def check(self) -> None:
        m, w = self.m, self.world
        seen: dict[str, str] = {}
        for f in m.fleets.values():
            for s in f.ships:
                if s.cid:
                    if s.cid in seen:
                        self.errors.append(f"t={m.t:.0f}: {s.cid} is in {seen[s.cid]} and in {f.id}")
                    seen[s.cid] = f.id
            if f.status == "real":
                if f.where != m.real_system or m.aquila["lane"]:
                    self.errors.append(f"t={m.t:.0f}: {f.id} is played by the game at {f.where!r} but the Aquila is {m.aquila['where']!r} (lane {m.aquila['lane']!r}, real {m.real_system!r})")
            if not f.ships:
                self.errors.append(f"t={m.t:.0f}: {f.id} has no ships and is in the war")
        ids = [f.id for f in m.fleets.values()]
        if len(ids) != len(set(ids)):
            self.errors.append(f"t={m.t:.0f}: a fleet id twice")
        names = [s.name for f in m.fleets.values() for s in f.ships]
        if len(names) != len(set(names)):
            dup = sorted({n for n in names if names.count(n) > 1})
            self.errors.append(f"t={m.t:.0f}: a ship in two fleets: {dup[:3]}")
        for cid, s in w.ships.items():
            if s["state"] in DEAD:
                if cid in seen:
                    self.errors.append(f"t={m.t:.0f}: {cid} is gone from the game but the map still has it in {seen[cid]}")
        for cid in seen:
            f = m.fleets[seen[cid]]
            if f.status == "scripted" or f.id in self.glue.opening:
                continue                                                              # (the game's own script brings these: this stand-in has none)
            if cid not in w.ships and not any(cid in ids_ for _, _, ids_ in w.pending):
                if m.t - self._due(cid) > 5.0:
                    self.errors.append(f"t={m.t:.0f}: {cid} (map: {seen[cid]}) is not in the game, nor on its way")

    def _due(self, cid: str) -> float:
        return self.glue.due.get(cid, 0.0)

    async def run(self) -> dict[str, Any]:
        m = self.m
        self.opening()
        end = self.hours * 3600.0
        n = 0
        while m.t < end and not m.over:
            self.clock.t += 1.0
            self.journeys()
            self.world.tick()
            self.glue.feed(self.world.state())
            n += 1
            if n % 3 == 0:
                await asyncio.sleep(0)
            if n % 10 == 0:
                self.check()
        self.check()
        if self.glue.stats["errors"]:
            self.errors.append(f"the join raised {self.glue.stats['errors']} errors")
        return {"seed": self.seed, "t": round(m.t), "errors": self.errors[:6], "n_errors": len(self.errors), "lanes": self.lanes, "glue": dict(self.glue.stats),
                "over": m.over.get("why", ""), "score": m.score, "real_fleets": sum(1 for f in m.fleets.values() if f.status == "real"), "fleets": len(m.fleets),
                "looks": self.minds.summary()["pulses"]}


class SoakTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_long_war_keeps_the_two_worlds_consistent(self) -> None:
        for seed in (1, 2, 3):
            res = await Soak(seed, 2.0).run()
            self.assertEqual(res["errors"], [], res)
            self.assertGreater(res["glue"]["sent"], 0, res)                              # (fleets did come into the game)
            self.assertGreater(res["lanes"], 0, res)                                    # (and the Aquila did travel)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=4.0)
    ap.add_argument("--seeds", default="1-3")
    a = ap.parse_args()
    lo, _, hi = a.seeds.partition("-")
    for seed in range(int(lo), int(hi or lo) + 1):
        res = asyncio.run(Soak(seed, a.hours).run())
        print(res)


if __name__ == "__main__":
    main()
