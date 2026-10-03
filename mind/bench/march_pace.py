"""The war's pace as the Captain lives it: how long she has between the first sign of a force and its guns, how long a fight lasts, what the war costs an hour, how often she has a
real choice (docs/GUERRA.md §10). No network, no cost, no engine.

    cd mind && .venv/bin/python -m unittest bench.march_pace -v
    cd mind && .venv/bin/python -m bench.march_pace --hours 3 --seeds 1-6                 (the report: the opening as the game's script plays it, and as the March does)
    cd mind && .venv/bin/python -m bench.march_pace --live --hours 0.7 --seeds 1 --cap 0.04   (the same with the real minds: the key in the environment, its cost counted)

The join runs against the soak's stand-in for the game (bench/march_soak.py) with the approach added: a ship that comes through the Gate arrives `range_km` out and closes at its
cruise speed, and is in the fight from the missiles' range (25 km: AstraBattleSubsystem.h `MissileRange`); the high commands' minds are the reflexes given through the tools, so what
is measured is the floor of the war's pace (a live mind makes more moves, never fewer than the reflexes). Two openings are played side by side:

  - `script`: the game's own opening as the C++ runs it (AstraBattleSubsystem.cpp `TickScenario`): the strike group appears at 25 km at 170 s, the Gate cycles at 500 s and the
    vanguard comes from the Gate's mouth 50 s later, the relief at 22 km after 170 s more; the March adopts them by their contact ids;
  - `march`: the game has switched its script off (the `opening` command): the same fleets are the war's, and they come the way the war's fleets come.

What is read: the time to the first contact (a fight with the strike group's ships in it), the warning before it (the Gate's cycling, heard on the bridge, to the first shot), the
fights' length and the ships they cost, the losses an hour of the whole war, and the decision points of the Captain: what puts a choice before her (a Gate cycling towards her
sky, a force arriving, an offer of peace, a siege, a system taken, the government's orders) and the longest stretch with none. Fights in the stand-in are its own crude combat, with its
damage fitted to the war bench's engagement lengths (data/march/cal_cpp.json: the game's engagements last 5 to 15 minutes): it is the Aquila's absence from them and the lack of
manoeuvre that make them a floor, not a forecast; the approach and the warnings are the join's own and exact."""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind.march import SIDES, Event  # noqa: E402
from astra_mind.march_data import CLASSES  # noqa: E402
from astra_mind.strategy import StrategicMinds  # noqa: E402
from bench.march_soak import DEAD, FightingWorld, Soak  # noqa: E402

ENGAGE_KM = 25.0                    # the missiles' range: a force that has closed to it is in the fight
DAMAGE_SCALE = 3.5                  # the stand-in's damage a second, fitted so that its fights last as long as the war bench's (3 to 6 destroyers a side: 300 to 650 s; the bench: 445 to 530 s)
OPENING_S = 1800.0                  # the opening is the first half hour
SCRIPT_FLEETS = ("F-M1", "F-M3", "F-A3")
# what puts a choice before the Captain, from the March's own record: the Gate cycling towards her sky is counted apart (it is the one she can act on first)
DECISION_KINDS = ("proposal", "orders_from_home", "siege", "system_taken", "post_lost", "passage", "truce", "truce_over", "war_over")
QUIET_GAP_S = 900.0                 # a stretch this long with no choice before her is a quiet one


class PaceWorld(FightingWorld):
    """The soak's stand-in, with the approach (a ship closes at its speed from where the beat puts it) and, when asked, the game's own opening script."""

    def __init__(self, now, rng) -> None:  # noqa: ANN001
        super().__init__(now, rng)
        self.scale = DAMAGE_SCALE
        self.contact: dict[str, float] = {}               # contact id -> when it is in the fight
        self.waves: list[dict[str, Any]] = []             # every beat the join sent: what, from how far, when it came through and when it was in the fight
        self.script = False                               # play the game's own opening script
        self.spec: dict[str, list[tuple[str, str, str, str]]] = {}      # the scripted fleets' ships: (contact id, side, class, name)
        self._stage = 0
        self.notices: list[float] = []                    # what the game itself said as a warning (the script's "the Gate is cycling")

    async def command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        n0 = len(self.pending)
        res = await super().command(name, args)
        if name == "director_beat" and res.get("ok") and len(self.pending) > n0:
            when, beat, ids = self.pending[-1]
            ships = [sp for g in beat["groups"] for sp in g["ships"][:10]]
            at = []
            for cid, sp in zip(ids, ships):
                km = float(beat.get("range_km", 20.0))
                self.contact[cid] = when + max(0.0, km - ENGAGE_KM) * 1000.0 / CLASSES[sp["class"]]["speed"]
                at.append(self.contact[cid])
            self.waves.append({"t_cmd": self.now(), "type": beat["type"], "n": len(ids), "range_km": float(beat.get("range_km", 0.0)), "arrives": when,
                               "in_fight": min(at) if at else when, "side": "mandate" if beat["type"] == "raid" else "astra"})
        return res

    def in_fight(self, s: dict[str, Any]) -> bool:
        return self.contact.get(s["id"], 0.0) <= self.now()

    def tick(self) -> None:
        if self.script:
            self.run_script()
        super().tick()

    def run_script(self) -> None:
        """The opening as the game's C++ plays it: three stages, by the clock (the lethe's waking at 80 s is the game's own too, at the picket's first sight)."""
        now = self.now()
        if self._stage == 0 and now >= 80.0:
            self._stage = 1
            self.contact["T-11"] = now                     # (the lethe lights its drive and goes for the freighter)
        if self._stage == 1 and now >= 170.0:
            self._stage = 2
            self.appear("F-M1", 25.0, 0.0)                 # the strike group, 25 km out
        if self._stage == 2 and now >= 170.0 + 330.0:
            self._stage = 3
            self.notices.append(now)                       # "sensors: the Janus Gate is cycling"
        if self._stage == 3 and now >= 170.0 + 330.0 + 50.0:
            self._stage = 4
            self.appear("F-M3", 106.0, 0.0)                # the vanguard at the Gate's mouth, 4 km before the Gate
        if self._stage == 4 and now >= 170.0 + 330.0 + 50.0 + 170.0:
            self._stage = 5
            self.appear("F-A3", 22.0, 0.0)                 # the relief, 22 km out

    def appear(self, fid: str, km: float, delay: float) -> None:
        for cid, side, cls, name in self.spec.get(fid, []):
            if cid not in self.ships:
                self.add(cid, side, cls, name)
                self.contact[cid] = self.now() + delay + max(0.0, km - ENGAGE_KM) * 1000.0 / CLASSES[cls]["speed"]
        if fid == "F-M1":
            self.waves.append({"t_cmd": self.now(), "type": "script", "n": len(self.spec[fid]), "range_km": km, "arrives": self.now(), "in_fight": self.now(), "side": "mandate"})
        elif fid == "F-M3":
            self.waves.append({"t_cmd": self.now(), "type": "script", "n": len(self.spec[fid]), "range_km": km, "arrives": self.now(),
                               "in_fight": self.now() + (km - ENGAGE_KM) * 1000.0 / CLASSES["styx"]["speed"], "side": "mandate"})


class PaceSoak(Soak):
    world_class = PaceWorld

    def __init__(self, seed: int, hours: float, opening: str = "march", live: bool = False, cap: float = 0.0) -> None:
        random.seed(seed * 7919)                                                     # (a campaign draws its war's seed and the minds' cadence from the global generator: the bench is repeatable)
        super().__init__(seed, hours)
        self.mode = opening
        self.live, self.cap = live, cap
        self.said: list[str] = []                                                    # what Rourke said on the fleet net (live runs)
        self.looks: list[dict[str, Any]] = []                                        # every look of the minds (live runs)
        if live:
            from astra_mind.openrouter import OpenRouter

            async def say(speaker: str, text: str, lang: str, tone: str, **kw: Any) -> None:
                self.said.append(f"{self.m.t:.0f}s {speaker}: {text}")
            self.minds = StrategicMinds(OpenRouter(), self.m, say, lang=lambda: "en", trace=self.looks.append)
            self.glue.minds = self.minds
            self.minds.on_aquila_task = self.glue._task_aquila
            self.minds.on_tender = self.glue._tender
        w: PaceWorld = self.world                                                   # type: ignore[assignment]
        w.script_off = opening == "march"                                           # (what the game answers to "switch the opening script off")
        w.script = opening == "script"
        w.gate = (200.0, 110.0)                                                     # (the opening's Gate: 110 km from the Aquila)
        self.glue.gate = w.gate
        w.spec = {fid: [(s.cid, f.side, s.cls, s.name) for s in f.ships] for fid, f in self.m.fleets.items() if fid in SCRIPT_FLEETS}
        self.heard: list[tuple[Event, str]] = []                                     # (the event, the system the Aquila was in when it happened)
        self.m.listeners.append(lambda e: self.heard.append((e, self.m.real_system)))
        self.next_move = self.rng.uniform(1900.0, 3400.0)                          # (the opening is fought where the campaign begins: she leaves Aurelia after it)
        self.fights: list[dict[str, Any]] = []
        self.cur: dict[str, Any] | None = None
        self.dead_seen: set[str] = set()
        self.first_big: float | None = None                                         # when the strike group's size of force (three ships) is first in the fight at Aurelia


    def opening(self) -> None:
        super().opening()
        self.world.contact["T-11"] = 80.0                                           # (the lethe wakes at 80 s: before that it is a cold drifting contact)

    def journeys(self) -> None:
        was = self.lane_to
        super().journeys()
        if self.lane_to and not was and self.cur is not None:
            self._end("she jumped")                                                  # (she left the system in the middle of it)

    # -- reading the war's pace
    def observe(self) -> None:
        m, w = self.m, self.world
        now = m.t
        eng = {sd: [s for s in w.ships.values() if s["side"] == sd and s["state"] not in DEAD and w.in_fight(s)] for sd in SIDES}
        new_dead = [c for c, s in w.ships.items() if s["state"] == "destroyed with all hands" and c not in self.dead_seen]
        self.dead_seen.update(new_dead)
        both = bool(eng["astra"] and eng["mandate"])
        if self.first_big is None and both and len(eng["mandate"]) >= 3 and m.real_system == "Aurelia":
            self.first_big = now
        if both and self.cur is None:
            self.cur = {"t0": now, "system": m.real_system, "lost": {"astra": 0, "mandate": 0}, "most": 0, "off": None}
        if self.cur is not None:
            for c in new_dead:
                self.cur["lost"][w.ships[c]["side"]] += 1
            self.cur["most"] = max(self.cur["most"], len(eng["mandate"]))
            if both:
                self.cur["off"] = None
            elif self.cur["off"] is None:
                self.cur["off"] = now
            elif now - self.cur["off"] >= 30.0:
                self._end("over", self.cur["off"])

    def _end(self, why: str, at: float | None = None) -> None:
        c = self.cur
        assert c is not None
        c.update(t1=at if at is not None else self.m.t, why=why)
        c["len"] = c["t1"] - c["t0"]
        self.fights.append(c)
        self.cur = None

    async def run(self) -> dict[str, Any]:                                          # type: ignore[override]
        m, w = self.m, self.world
        self.opening()
        end = self.hours * 3600.0
        n = 0
        while m.t < end and not m.over:
            self.clock.t += 1.0
            self.journeys()
            w.tick()
            self.glue.feed(w.state())
            self.observe()
            n += 1
            if self.live:                                                            # (the war waits while the minds think: a look takes seconds, the cadence is minutes)
                busy = [s.task for s in self.minds.seats.values() if s.busy and s.task is not None]
                if busy:
                    await asyncio.wait(busy)
                if self.minds.summary()["cost"] >= self.cap:
                    print(f"the cost cap of {self.cap:.3f} $ is reached at {m.t:.0f} s: stopped", flush=True)
                    break
            if n % 3 == 0:
                await asyncio.sleep(0)
            if n % 10 == 0:
                self.check()
        if self.cur is not None:
            self._end("run ended")
        self.check()
        if self.glue.stats["errors"]:
            self.errors.append(f"the join raised {self.glue.stats['errors']} errors")
        return self.report()

    def report(self) -> dict[str, Any]:
        m, w = self.m, self.world
        hours = max(m.t, 1.0) / 3600.0
        first = {"t0": self.first_big} if self.first_big is not None else None
        wakes = [e for e, rs in self.heard if e.kind == "wake" and e.system == rs]
        warn = [e.t for e in wakes] + list(w.notices)
        before = [t for t in warn if first is not None and t <= first["t0"]]                    # (a warning that comes after the guns is no warning of them)
        first_warn = min(before) if before else None
        # the Captain's decision points: what the war puts before her (the Gate's cycling towards her sky, a force coming into it, and the war's own news of the kinds that call for a choice)
        points: list[tuple[float, str]] = [(e.t, "gate") for e in wakes] + [(t, "gate") for t in w.notices]
        points += [(x["arrives"], "arrival") for x in w.waves if x["side"] == "mandate"]
        points += [(e.t, e.kind) for e, _ in self.heard if e.kind in DECISION_KINDS and (e.kind != "proposal" or e.data.get("by") != "astra")]
        points.sort()
        times = [t for t, _ in points]
        gaps = [b - a for a, b in zip(times, times[1:])] + ([m.t - times[-1]] if times else [m.t])
        by_kind: dict[str, int] = {}
        for _, k in points:
            by_kind[k] = by_kind.get(k, 0) + 1
        lens = [f["len"] for f in self.fights if f["len"] >= 5.0]
        lost = {s: m.score[s]["ships_lost"] for s in SIDES}
        opening_waves = [x for x in w.waves if x["t_cmd"] <= OPENING_S and x["side"] == "mandate"]
        return {"seed": self.seed, "mode": self.mode, "t": round(m.t), "errors": self.errors[:4], "n_errors": len(self.errors), "over": m.over.get("why", ""),
                "first_warning": first_warn, "first_contact": first["t0"] if first else None,
                "warning_to_contact": (first["t0"] - first_warn) if (first and first_warn is not None) else None,
                "waves": opening_waves, "min_range_km": min((x["range_km"] for x in w.waves if x["type"] != "script" and x["side"] == "mandate"), default=None),
                "fights": len(lens), "fight_mean_s": statistics.mean(lens) if lens else 0.0, "fight_max_s": max(lens) if lens else 0.0,
                "lost": lost, "lost_per_hour": sum(lost.values()) / hours, "decisions": len(points), "decisions_per_hour": len(points) / hours, "by_kind": by_kind,
                "gap_median_s": statistics.median(gaps) if gaps else m.t, "gap_max_s": max(gaps) if gaps else m.t, "quiet_gaps_per_hour": sum(1 for g in gaps if g >= QUIET_GAP_S) / hours,
                "arrivals_per_hour": sum(1 for x in w.waves if x["side"] == "mandate") / hours}


def fmt(x: float | None, unit: str = "s") -> str:
    if x is None:
        return "-"
    return f"{x:.0f} {unit}" if unit == "s" else f"{x:.1f} {unit}"


def aggregate(rs: list[dict[str, Any]], key: str) -> str:
    v = [r[key] for r in rs if r[key] is not None]
    return f"{statistics.mean(v):.0f}" if v else "-"


class PaceTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_march_opening_gives_a_warning_and_a_far_arrival_where_the_script_gave_neither(self) -> None:
        march = [await PaceSoak(s, 0.35, "march").run() for s in (1, 2, 3)]
        script = [await PaceSoak(s, 0.35, "script").run() for s in (1, 2, 3)]
        for r in march + script:
            self.assertEqual(r["errors"], [], r)
        for r in march:
            self.assertIsNotNone(r["first_contact"], r)
            self.assertIsNotNone(r["first_warning"], r)
            self.assertGreaterEqual(r["first_contact"], 360.0, r)                    # (the first guns are minutes away, not seconds)
            self.assertGreaterEqual(r["warning_to_contact"], 180.0, r)               # (the Gate's warning comes minutes before them)
            self.assertGreaterEqual(r["min_range_km"], 85.0, r)                      # (and nothing ever came from nearer than the far side of the system)
        for r in script:
            self.assertLessEqual(r["first_contact"], 200.0, r)                       # (the game's own script: the strike group at 25 km after 170 s)
            self.assertIsNone(r["first_warning"], r)                                 # (and no warning of it)

    async def test_the_long_war_goes_on_with_things_for_the_captain_to_decide(self) -> None:
        for seed in (1, 2):
            r = await PaceSoak(seed, 2.0, "march").run()
            self.assertEqual(r["errors"], [], r)
            self.assertGreaterEqual(r["decisions"], 4, r)                           # (the reflexes alone: the floor; the minds and the director add to it)
            self.assertGreaterEqual(r["arrivals_per_hour"], 0.5, r)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=3.0)
    ap.add_argument("--seeds", default="1-4")
    ap.add_argument("--modes", default="script,march")
    ap.add_argument("--live", action="store_true", help="the real minds (the key in the environment); the opening is the March's")
    ap.add_argument("--cap", type=float, default=0.04, help="a live run stops when the layer has cost this much ($)")
    a = ap.parse_args()
    lo, _, hi = a.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))
    if a.live:
        for s in seeds:
            soak = PaceSoak(s, a.hours, "march", live=True, cap=a.cap)
            r = asyncio.run(soak.run())
            sm = soak.minds.summary()
            print(f"\n=== live, seed {s}: war time {r['t']} s, first warning {fmt(r['first_warning'])}, first contact {fmt(r['first_contact'])}, warning to contact {fmt(r['warning_to_contact'])}, "
                  f"lost {r['lost']['astra']}/{r['lost']['mandate']}, decisions {r['decisions']} ({r['by_kind']}), errors {r['n_errors']}")
            print(f"    the layer: {sm['pulses']} looks, {sm['cost']:.4f} $ ({sm['cost_per_hour']:.4f} $/h), latency median {sm['latency_median']} s")
            for rec in soak.looks:
                print(f"    t={rec['t']:>6.0f}  {rec['who'].split()[-1]:<7} [{'; '.join(rec['why'])[:60]}]  " + " | ".join(rec['tools'])[:200])
            for line in soak.said:
                print("    said:", line[:260])
            for p in soak.world.waves:
                print(f"    wave: t={p['t_cmd']:.0f}s {p['side']} {p['type']} {p['n']} ships from {p['range_km']:.0f} km, arrives {p['arrives']:.0f}s, in the fight {p['in_fight']:.0f}s")
        return
    for mode in a.modes.split(","):
        rs = [asyncio.run(PaceSoak(s, a.hours, mode).run()) for s in seeds]
        print(f"\n=== opening: {mode}  ({len(seeds)} seeds x {a.hours} h) ===")
        for r in rs:
            print(f"  seed {r['seed']}: first warning {fmt(r['first_warning'])}, first contact {fmt(r['first_contact'])}, warning to contact {fmt(r['warning_to_contact'])}, "
                  f"fights {r['fights']} (mean {fmt(r['fight_mean_s'])}, longest {fmt(r['fight_max_s'])}), lost {r['lost']['astra']}/{r['lost']['mandate']} "
                  f"({r['lost_per_hour']:.1f}/h), decisions {r['decisions_per_hour']:.1f}/h, longest quiet {fmt(r['gap_max_s'])}, errors {r['n_errors']}")
        print(f"  mean: first warning {aggregate(rs, 'first_warning')} s, first contact {aggregate(rs, 'first_contact')} s, warning to contact {aggregate(rs, 'warning_to_contact')} s, "
              f"fights {aggregate(rs, 'fights')}, ships lost an hour {statistics.mean(r['lost_per_hour'] for r in rs):.1f}, "
              f"decisions an hour {statistics.mean(r['decisions_per_hour'] for r in rs):.1f}, longest quiet {aggregate(rs, 'gap_max_s')} s, "
              f"quiet stretches (>{QUIET_GAP_S / 60:.0f} min) an hour {statistics.mean(r['quiet_gaps_per_hour'] for r in rs):.2f}, "
              f"Mandate arrivals an hour {statistics.mean(r['arrivals_per_hour'] for r in rs):.1f}")
        waves = rs[0]["waves"]
        print("  the opening's waves (seed %d): " % rs[0]["seed"] + "; ".join(f"t={x['t_cmd']:.0f}s {x['type']} {x['n']} ships from {x['range_km']:.0f} km, in the fight at {x['in_fight']:.0f}s" for x in waves))


if __name__ == "__main__":
    main()
