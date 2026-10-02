"""The March bench: hours of war in seconds (docs/GUERRA.md §10).

The strategic layer's rules (march.py) play whole campaigns with the code's own reflexes for both sides (march_auto.py: the same code, a doctrine's numbers apart),
and the bench reads what the war comes to: who wins and how, how long it lasts, what it costs, how the ground is held at the end, whether the sides are
fairly matched, and whether what the Captain does counts.

    cd mind && .venv/bin/python -m bench.march_sim --seeds 1-200 --hours 12                         the real March, the Captain not in it
    cd mind && .venv/bin/python -m bench.march_sim --seeds 1-200 --captain none,idle,fleet,defender,hunter --skill 1.25
    cd mind && .venv/bin/python -m bench.march_sim --seeds 1-200 --world sym                         a mirrored world: the rules must give 50/50
    cd mind && .venv/bin/python -m bench.march_sim --seeds 1-200 --swap                              each side with the other's doctrine

The Captain is a stand-in (`ScriptedCaptain`): the Aquila is a ship of the picket's fleet with her class's numbers, `--skill` says how much better than the reflexes
he fights the fleet he commands (the real game has the real simulation and the real Captain there: this is only what the bench can say), and the policies are the
decisions a player has at this level: stay (idle), be a fleet of the Fleet's (fleet), rush to what is threatened (defender), go and hit what he can beat (hunter).

Everything is deterministic by seed; two runs give the same numbers."""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind import march, march_auto, march_data, war  # noqa: E402
from astra_mind.march import SIDES, March, other  # noqa: E402

CAPTAINS = ("none", "idle", "fleet", "defender", "hunter")


# ------------------------------------------------------------------------------------------------ a mirrored world (the rules must treat both sides alike)
def sym_world() -> dict[str, Any]:
    """Two homelands that are each other's mirror, a hub between them nobody holds: the same systems, forts, yards, fleets and classes for both. If the rules (or the
    reflexes, which are the same code for both sides) favoured a side, here is where it would show."""
    sec, systems, links, orbat = [], {}, [], []
    names = {"astra": ("A-Capital", "A-Front", "A-Rear"), "mandate": ("B-Capital", "B-Front", "B-Rear")}
    y = {"astra": -30, "mandate": 30}
    for side in SIDES:
        cap, front, rear = names[side]
        for n, (val, yard, fort, siege, x) in {cap: (10, 3.0, 8, 2400, -40), front: (6, 1.5, 4, 1200, -15), rear: (4, 1.0, 2, 600, -28)}.items():
            sec.append(dict(name=n, star="yellow", planet="ocean", world=n, owner=side, x=x, y=y[side] + (6 if n == rear else 0), pop=1, about="a homeland system"))
            systems[n] = dict(value=val, yard=yard, depot=True, fort=fort, siege_s=siege, post=(side,), home=side if n == cap else "", crossing_s=150, note="")
        links += [(cap, front), (cap, rear), (rear, front)]
    sec.append(dict(name="Hub", star="red_dwarf", planet="barren", world="Hub", owner="silent", x=0, y=0, pop=0, about="the crossroads"))
    systems["Hub"] = dict(value=3, yard=0.0, depot=False, fort=0, siege_s=420, post=(), home="", crossing_s=150, note="")
    links += [("A-Front", "Hub"), ("B-Front", "Hub")]
    n = 0
    for side, pre in (("astra", "F-A"), ("mandate", "F-M")):
        cap, front, rear = names[side]
        def ships(spec: list[tuple[str, int]], tag: str) -> list[tuple[str, str]]:
            nonlocal n
            out = []
            for cls, k in spec:
                for _ in range(k):
                    n += 1
                    out.append((cls, f"{tag} {n}"))
            return out
        orbat += [
            dict(id=f"{pre}1", side=side, name=f"{side} main body", where=front, supply=1.0, morale=0.8, ships=ships([("acheron", 2), ("styx", 6)], "Main"),
                 wings=[(0, "fighter", 16), (0, "bomber", 5), (1, "fighter", 16), (1, "bomber", 5)], order=dict(kind="defend", target=front, stance="steady", reason="hold the front")),
            dict(id=f"{pre}2", side=side, name=f"{side} home fleet", where=cap, supply=1.0, morale=0.8, ships=ships([("acheron", 2), ("styx", 4)], "Home"),
                 wings=[(0, "fighter", 16), (1, "fighter", 16)], order=dict(kind="defend", target=cap, stance="cautious", reason="the capital's guard", position="world")),
            dict(id=f"{pre}3", side=side, name=f"{side} garrison", where=rear, supply=1.0, morale=0.75, ships=ships([("styx", 3)], "Garr"), wings=[],
                 order=dict(kind="defend", target=rear, stance="steady", reason="the rear", position="world")),
            dict(id=f"{pre}4", side=side, name=f"{side} raiders", where=front, supply=1.0, morale=0.8, ships=ships([("lethe", 4)], "Raid"), wings=[],
                 order=dict(kind="hold", target=front, stance="steady", reason="raiders on the front")),
        ]
    return dict(SECTOR=sec, LINKS=links, SYSTEMS=systems, ORBAT=orbat, CAPITALS={"astra": "A-Capital", "mandate": "B-Capital"}, HQ={"astra": "A-Front", "mandate": "B-Front"},
                YARD_DEFAULT={"A-Capital": "acheron", "A-Front": "styx", "A-Rear": "styx", "B-Capital": "acheron", "B-Front": "styx", "B-Rear": "styx"})


@contextlib.contextmanager
def patched(world: dict[str, Any] | None) -> Iterator[None]:
    """Swap the module-level map and order of battle for a world's own, and put them back."""
    if world is None:
        yield
        return
    targets = [(march, ("SYSTEMS", "ORBAT", "CAPITALS", "HQ", "YARD_DEFAULT")), (march_auto, ("SYSTEMS", "CAPITALS")), (march_data, ("SYSTEMS", "ORBAT", "CAPITALS", "HQ", "YARD_DEFAULT")),
               (war, ("SECTOR", "LINKS"))]
    saved = []
    for mod, names in targets:
        for nm in names:
            if hasattr(mod, nm):
                saved.append((mod, nm, getattr(mod, nm)))
                setattr(mod, nm, world[nm])
    try:
        yield
    finally:
        for mod, nm, old in saved:
            setattr(mod, nm, old)


# ------------------------------------------------------------------------------------------------ the Captain, as far as a bench can have him
class ScriptedCaptain:
    """The Captain at the level of the March: where he takes the Aquila and what he does with the fleet she is in. Orders are given on the spot (he is aboard)."""

    def __init__(self, m: March, policy: str, think_s: float = 120.0) -> None:
        self.m, self.policy, self.think_s = m, policy, think_s
        self.next_t = 400.0
        self.moves = 0

    def tick(self) -> None:
        m = self.m
        if self.policy in ("none", "idle", "fleet") or m.t < self.next_t:
            return
        self.next_t = m.t + self.think_s
        f = m.fleets.get(m.aquila_fleet)
        if f is None or f.status != "ready" or f.in_gate or f.pending is not None or not f.where:
            return
        v = m.view("astra")
        auto = march_auto.AutoAdmiral(m, "astra")
        if f.hull < 0.45 and f.order.kind != "refit":
            dest = m.nearest_depot("astra", f.where, avoid=m.hostile_systems("astra")) or m.nearest_depot("astra", f.where)
            if dest:
                m.order("astra", f.id, "refit", dest, stance="cautious", reason="the Captain takes her to a depot", by="captain", instant=True)
                self.moves += 1
            return
        if f.order.kind == "refit" and f.hull < 0.95:
            return
        mine = {n for n in m.sys if m.owner(n) == "astra"}
        if self.policy == "defender":
            best: tuple[float, str] | None = None
            for name in mine:
                t = auto.threat(v, name)
                if t < 0.8:
                    continue
                here = v.own_power(name) - (f.power if f.where == name else 0.0)
                if here + f.power * m.captain_skill < 0.75 * t:
                    continue                                          # (he does not throw her into a battle he cannot win)
                score = SYSTEMS_VALUE(name) * t
                if best is None or score > best[0]:
                    best = (score, name)
            target = best[1] if best else "Aurelia"
            if f.order.kind == "defend" and f.order.target == target and f.order.by == "captain":
                return
            ok, _ = m.order("astra", f.id, "defend", target, stance="steady", reason="the Captain goes where the Mandate is coming", by="captain", instant=True, position="gate")
            self.moves += 1 if ok else 0
        elif self.policy == "hunter":
            best_t: tuple[float, str] | None = None
            for tr in v.tracks.values():
                if m.t - tr.seen_t > 600.0:
                    continue
                h = m.hops(f.where, tr.system, "astra")
                if h > 2:
                    continue
                p = m.track_power(tr) + (SYSTEMS_FORT(tr.system, "mandate", m) if m.owner(tr.system) == "mandate" else 0.0)
                if p > 0.8 * (f.power * m.captain_skill):
                    continue
                score = SYSTEMS_VALUE(tr.system) * (1.0 + 0.3 * p) / (1 + h)
                if best_t is None or score > best_t[0]:
                    best_t = (score, tr.system)
            if best_t is not None:
                if f.order.kind == "assault" and f.order.target == best_t[1] and f.order.by == "captain":
                    return
                ok, _ = m.order("astra", f.id, "assault", best_t[1], stance="steady", reason="the Captain hits what he can beat", by="captain", instant=True)
                self.moves += 1 if ok else 0
            elif f.where != "Aurelia" and f.order.by == "captain":
                m.order("astra", f.id, "defend", "Aurelia", stance="steady", reason="the Captain returns to the picket's post", by="captain", instant=True, position="gate")
                self.moves += 1


def SYSTEMS_VALUE(name: str) -> float:
    return float(march.SYSTEMS.get(name, {}).get("value", 3))


def SYSTEMS_FORT(name: str, owner: str, m: March) -> float:
    return float(march.SYSTEMS.get(name, {}).get("fort", 0)) * m.sys[name].fort_hp * 0.9


# ------------------------------------------------------------------------------------------------ one war
def run_war(seed: int, hours: float = 12.0, captain: str = "none", skill: float = 1.25, world: str = "march", swap: bool = False, think_s: float = 90.0,
            tune: dict[str, float] | None = None) -> dict[str, Any]:
    w = sym_world() if world == "sym" else None
    with patched(w):
        wm = war.WarMap()
        wm.persist = False
        m = March(wm, seed=seed)
        for k, v in (tune or {}).items():
            m.pace[k] = v
        if world == "sym":
            m.free_classes = True
            m.pace["will_start"] = {"astra": 0.8, "mandate": 0.8}
            m.will = dict(m.pace["will_start"])
        elif captain != "none":
            m.add_aquila(skill)
        if captain in ("none", "fleet"):
            m.fleets["F-A2"].tactical_command = ""                          # (no Captain, or a Captain who lends his picket to the Fleet: the reflexes may use it)
        doctrine = {s: march_auto.DOCTRINE[other(s) if swap else s] for s in SIDES}
        if world == "sym":
            doctrine = {s: march_auto.Doctrine(margin=1.35, stage_s=420.0, bold="steady", start_s=600.0) for s in SIDES}
        autos = {s: march_auto.AutoAdmiral(m, s, "full", doctrine[s]) for s in SIDES}
        cap = ScriptedCaptain(m, captain)
        end = hours * 3600.0
        aq_dead = False
        battles = 0
        while m.t < end and not m.over:
            m.advance(min(end, m.t + think_s))
            for a in autos.values():
                a.think()
            cap.tick()
            if m.aquila_fleet and not aq_dead and not any(s.cls == "aquila" for f in m.fleets.values() for s in f.ships):
                aq_dead = True
        owners = {k: m.owner(k) for k in m.sys}
        battles = sum(1 for e in m.events if e.kind == "battle_end")
        battles = max(battles, m.event_n and sum(1 for e in m.events if e.kind == "battle_end"))
        held = {s: sum(1 for k, o in owners.items() if o == s) for s in SIDES}
        row = {"seed": seed, "t": m.t, "winner": m.over.get("winner", "") if m.over else "", "how": m.over.get("how", "") if m.over else "", "over": bool(m.over),
               "held": held, "will": {s: round(m.will[s], 3) for s in SIDES}, "score": m.score, "aquila_lost": aq_dead, "moves": cap.moves, "owners": owners,
               "n_events": m.event_n, "systems_flips": m.score["astra"]["systems_taken"] + m.score["mandate"]["systems_taken"]}
        if world == "sym":
            row["owners"] = {k: o for k, o in owners.items()}
        return row


def _job(args: tuple) -> dict[str, Any]:
    return run_war(*args)


# ------------------------------------------------------------------------------------------------ many wars
def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        if "-" in part:
            lo, hi = part.split("-")
            out += list(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return out


def summarize(label: str, rows: list[dict[str, Any]], hours: float) -> dict[str, Any]:
    n = len(rows)
    wa = sum(1 for r in rows if r["winner"] == "astra")
    wm = sum(1 for r in rows if r["winner"] == "mandate")
    peace = sum(1 for r in rows if r["over"] and not r["winner"])
    open_ = sum(1 for r in rows if not r["over"])
    done = sorted(r["t"] / 3600.0 for r in rows if r["over"])

    def pct(p: float) -> float:
        return done[min(len(done) - 1, int(p * len(done)))] if done else float("nan")
    se = math.sqrt(0.25 / max(1, wa + wm)) if wa + wm else 0.0
    out = {"label": label, "n": n, "astra": wa, "mandate": wm, "armistice": peace, "open": open_,
           "astra_share": (wa / (wa + wm)) if wa + wm else float("nan"), "share_se": se,
           "t_median_h": pct(0.5), "t_p10_h": pct(0.1), "t_p90_h": pct(0.9),
           "held_astra": statistics.mean(r["held"]["astra"] for r in rows), "held_mandate": statistics.mean(r["held"]["mandate"] for r in rows),
           "lost_astra": statistics.mean(r["score"]["astra"]["ships_lost"] for r in rows), "lost_mandate": statistics.mean(r["score"]["mandate"]["ships_lost"] for r in rows),
           "flips": statistics.mean(r["systems_flips"] for r in rows), "will_astra": statistics.mean(r["will"]["astra"] for r in rows),
           "will_mandate": statistics.mean(r["will"]["mandate"] for r in rows), "aquila_lost": sum(1 for r in rows if r.get("aquila_lost")),
           "moves": statistics.mean(r.get("moves", 0) for r in rows)}
    return out


def line(s: dict[str, Any], hours: float) -> str:
    sh = s["astra_share"]
    return (f"{s['label']:28} n {s['n']:4}  ASTRA {s['astra']:3} / Mandate {s['mandate']:3} / armistice {s['armistice']:2} / open at {hours:.0f} h {s['open']:3}  "
            f"ASTRA share of decided {sh * 100:5.1f}% ±{s['share_se'] * 100:4.1f}  ends at {s['t_median_h']:.1f} h (p10 {s['t_p10_h']:.1f}, p90 {s['t_p90_h']:.1f})  "
            f"holds {s['held_astra']:.1f}/{s['held_mandate']:.1f}  ships lost {s['lost_astra']:.0f}/{s['lost_mandate']:.0f}  flips {s['flips']:.1f}"
            + (f"  Aquila lost {s['aquila_lost']}" if s["aquila_lost"] else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", default="1-60")
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--captain", default="none", help="comma separated: " + ", ".join(CAPTAINS))
    ap.add_argument("--skill", type=float, default=1.25, help="how much better than the reflexes the Captain fights the fleet he commands (the bench's stand-in)")
    ap.add_argument("--world", default="march", choices=("march", "sym"))
    ap.add_argument("--swap", action="store_true", help="each side with the other's doctrine")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--tune", default="", help='pace values: "siege_scale=1.5,repair_per_s=0.002"')
    ap.add_argument("--out", default="", help="write the rows to this json")
    a = ap.parse_args()
    seeds = parse_seeds(a.seeds)
    tune = {k: float(v) for k, v in (kv.split("=") for kv in a.tune.split(",") if kv)}
    allrows: dict[str, list[dict[str, Any]]] = {}
    t0 = time.time()
    for captain in [c for c in a.captain.split(",") if c]:
        jobs = [(s, a.hours, captain, a.skill, a.world, a.swap, 90.0, tune) for s in seeds]
        if a.jobs > 1 and len(jobs) > 4:
            with ProcessPoolExecutor(a.jobs) as pool:
                rows = list(pool.map(_job, jobs, chunksize=4))
        else:
            rows = [_job(j) for j in jobs]
        allrows[captain] = rows
        label = f"{a.world} captain={captain}" + (" swap" if a.swap else "")
        print(line(summarize(label, rows, a.hours), a.hours), flush=True)
    print(f"({len(seeds) * len(allrows)} wars of up to {a.hours:.0f} h in {time.time() - t0:.0f} s)")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(allrows, indent=1, default=str))


if __name__ == "__main__":
    main()
