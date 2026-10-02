"""The fleet battle of the March: how a clash between fleets far from the Aquila is resolved (docs/GUERRA.md §10).

Where the Aquila is, battles are the real simulation. Everywhere else the war goes on with this model, which has to give what the simulation gives: it is
fitted against the war bench's own battles (tools/march_calibrate.py: eighteen experiments of the commandlet, both orders of creation, 24 battles each;
the constants it was fitted to are in march_calibration.json, next to this file). It is a small, deterministic-by-seed model of what the bench shows:

  - the ships of both sides fire at their enemies' guns every few seconds: rails and lasers by their damage per second, missiles in salvos against the
    point defence that is there to meet them, carriers' wings as craft that wear down;
  - a side concentrates its fire on one target at a time, picked by the class's value and how battered it is (the simulation's own choice), and what a
    kill does not need is wasted;
  - shields take the first of the damage and regenerate; the hull is what remains and is what a ship carries out of the battle;
  - a fleet breaks off when its side's strength falls under what its stance allows (a bold fleet fights on, a cautious one leaves early), runs for a
    short while under fire and is out;
  - luck: each side has a draw for the whole battle and a smaller one at every step, which is what makes a battle of equals a coin and a battle of
    unequals nearly certain, as in the bench.

Nothing here is a number picked for the story: the constants are the fit, and the war bench is the judge (`tools/march_calibrate.py model`)."""
from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any

from .march_data import CLASSES

CAL_FILE = Path(__file__).with_name("march_calibration.json")


@dataclass
class Params:
    """The model's constants. The defaults are the fit to the war bench (march_calibration.json overrides them when it exists)."""
    k_rail: float = 0.80                 # share of a ship's rail damage per second that reaches its target
    k_laser: float = 0.45                # ... of its lasers (short reach: only inside 4 km)
    hull_w: float = 1.80                 # a hull point in the model's currency (the simulation's structure scale)
    shield_w: float = 1.50               # ... a shield point
    shield_leak: float = 0.09            # the share of a hit that reaches the hull while the shield holds
    msl_cd: float = 30.0                 # seconds between a ship's missile salvos
    msl_frac: float = 0.34               # the share of a ship's stock it fires in a salvo
    msl_dmg: float = 105.0               # damage of a missile that reaches its target
    msl_leak: float = 0.30               # ... the share of it that goes through a shield
    pd_per_channel: float = 1.9          # missiles one point-defence channel stops in a salvo cycle
    ow: float = 0.14                     # damage wasted in a kill (the overkill and the retargeting)
    approach0: float = 45.0              # seconds of closing before the first shots, for a small fleet ...
    approach_per_ship: float = 1.3       # ... and for each ship more
    sigma_battle: float = 0.16           # the luck of a side for the whole battle (log-normal spread)
    sigma_step: float = 0.12             # the luck of a step
    ret_bold: float = 0.10               # a fleet breaks off when its side's strength share is under this ...
    ret_steady: float = 0.26
    ret_cautious: float = 0.40
    ret_hold_s: float = 14.0             # ... for this long
    flee_base_s: float = 10.0            # a ship that breaks off is under fire this long before it is out of reach, besides the time it takes to turn ...
    flee_turn: float = 0.5               # ... (this share of the time to turn her back on the enemy: 180 degrees at the class's turn rate)
    flee_exposure: float = 0.55          # ... and its ships count this much as targets while they run
    flee_hull: float = 0.27              # a ship under this share of its hull breaks off by itself (the simulation's own rule: its captain's reflex, a quarter of the plating)
    ramp_s: float = 110.0                # the fire builds up over this long once the fleets are in range (they close and settle at their ranges first)
    f_dps: float = 1.6                   # a fighter's damage per second against ships
    b_dps: float = 7.5                   # a bomber's, as torpedo runs averaged
    air_kill: float = 0.010              # craft a fighter kills per second
    air_pd: float = 0.0035               # craft a point-defence channel kills per second
    hold_target: float = 0.6             # a side keeps its target while it scores this much of the best
    focus_group: float = 7.0             # ships that fire together on one target: a bigger side fights as several groups, each with a target of its own
    defend_bonus: float = 1.10           # the defender's edge at a depot system with a post, in damage
    surprise: float = 1.12               # the edge of a force that arrives unseen, in its first minute
    step_s: float = 5.0
    # what the class table does not say: how much more (or less) than its numbers a class gives in the bench's fights (its guns bear less well, its
    # plating takes shots better ...): a multiplier on its damage (`p_`) and on what it takes to kill it (`h_`); 1 is the table
    p_praetorian: float = 1.0
    p_vigilant: float = 1.0
    p_acheron: float = 1.0
    p_styx: float = 1.0
    p_lethe: float = 1.0
    h_praetorian: float = 1.0
    h_vigilant: float = 1.0
    h_acheron: float = 1.0
    h_styx: float = 1.0
    h_lethe: float = 1.0

    @staticmethod
    def load(path: Path = CAL_FILE) -> "Params":
        base = Params()
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return base
        names = {f.name for f in fields(Params)}
        return replace(base, **{k: float(v) for k, v in (data.get("params") or {}).items() if k in names})


DEFAULT = Params.load()

FORT_CLASS = "fort"


class Unit:
    """One ship in a battle: the numbers of its class and its state. `ref` is whatever the caller wants back (a Ship of a fleet)."""
    __slots__ = ("cls", "name", "side", "fid", "hull", "hull_max", "shield", "shield_max", "regen", "p", "missiles", "msl_max", "pd", "value", "tier", "f", "b", "d",
                 "alive", "gone", "flee_t", "flee_need", "kills", "ref", "stance", "fixed")

    def __init__(self, cls: str, side: int, fid: str = "", name: str = "", hull_frac: float = 1.0, supply: float = 1.0, wing: tuple[int, int, int] = (0, 0, 0),
                 ref: Any = None, stance: str = "steady", params: Params = DEFAULT, fort: float = 0.0) -> None:
        c = CLASSES[cls] if cls != FORT_CLASS else CLASSES["vigilant"]
        mult = fort if cls == FORT_CLASS else 1.0                       # a fort is `fort` destroyers' worth of guns and plating that cannot move
        pk = getattr(params, "p_" + cls, 1.0)
        hk = getattr(params, "h_" + cls, 1.0)
        self.cls, self.side, self.fid, self.name = cls, side, fid, name or cls
        self.hull_max = c["hull"] * params.hull_w * mult * hk
        self.shield_max = c["shield"] * params.shield_w * mult * hk
        self.hull = self.hull_max * max(0.02, min(1.0, hull_frac))
        self.shield = self.shield_max
        self.regen = c["regen"] * params.shield_w * mult * hk
        self.p = (params.k_rail * c["rail"] + params.k_laser * c["laser"]) * mult * pk * (0.55 + 0.45 * min(1.0, supply * 1.3))
        self.msl_max = c["missiles"] * mult * min(1.0, 0.1 + supply)
        self.missiles = self.msl_max
        self.pd = c["pd"] * mult
        self.value = c["value"] * (mult ** 0.5 if cls == FORT_CLASS else 1.0)
        self.tier = c["tier"]
        self.f, self.b, self.d = wing
        self.alive, self.gone, self.flee_t, self.kills = True, False, -1.0, 0
        self.flee_need = params.flee_base_s + params.flee_turn * 180.0 / max(0.5, float(c.get("turn", 4.0)))
        self.ref, self.stance = ref, stance
        self.fixed = cls == FORT_CLASS

    @property
    def frac(self) -> float:
        return (self.hull + self.shield) / (self.hull_max + self.shield_max)

    @property
    def hull_frac(self) -> float:
        return max(0.0, self.hull / self.hull_max)

    @property
    def fighting(self) -> bool:
        return self.alive and not self.gone and self.flee_t < 0.0


class Engagement:
    """A battle in progress between two sides (index 0 and 1): `step(dt)` advances it, `over` says when it is decided. The units are the callers': their hulls,
    wings and missiles are changed in place, so what a ship carries out of the battle is simply what it has when it ends."""

    def __init__(self, sides: tuple[list[Unit], list[Unit]], rng: random.Random, params: Params = DEFAULT, *, defender: int = -1, surprise: int = -1,
                 approach_s: float | None = None) -> None:
        self.sides = sides
        self.rng = rng
        self.p = params
        self.t = 0.0
        n = max(len(sides[0]), len(sides[1]))
        self.approach_s = params.approach0 + params.approach_per_ship * n if approach_s is None else approach_s
        self.luck = [math.exp(rng.gauss(0.0, params.sigma_battle)) for _ in (0, 1)]
        self.defender, self.surprise = defender, surprise
        self.target: list[list[Unit | None]] = [[], []]                  # side -> the target of each of its fire groups
        self.low_for: dict[str, float] = {}                              # fleet id -> how long its side's strength has been under its stance's line
        self.msl_t = [self.approach_s - 12.0, self.approach_s - 12.0]
        self.events: list[tuple[float, str, Unit]] = []                  # (t, "lost" | "broke off" | "out", unit)
        self.broke: set[str] = set()
        self.over = False
        self.winner = -1
        self.damage_dealt = [0.0, 0.0]

    # ------------------------------------------------------------------------------------------- reading
    def alive(self, s: int) -> list[Unit]:
        return [u for u in self.sides[s] if u.alive and not u.gone]

    def engaged(self, s: int) -> list[Unit]:
        return [u for u in self.sides[s] if u.fighting]

    def strength(self, s: int) -> float:
        return sum(u.value * (0.35 + 0.65 * u.frac) for u in self.sides[s] if u.fighting and not u.fixed) + \
            sum(u.value * (0.35 + 0.65 * u.frac) for u in self.sides[s] if u.fighting and u.fixed) * 0.8

    def craft(self, s: int) -> tuple[float, float]:
        f = sum(u.f for u in self.sides[s] if u.alive and not u.gone)
        b = sum(u.b for u in self.sides[s] if u.alive and not u.gone)
        return f, b

    # ------------------------------------------------------------------------------------------- orders
    def break_off(self, fid: str) -> int:
        """A fleet leaves the battle (its admiral ordered it, or its stance says it is beaten): its ships turn and run, and are out when each has turned and
        got out of reach (`Unit.flee_need`); until then they are targets."""
        n = 0
        for s in (0, 1):
            for u in self.sides[s]:
                if u.fid == fid and u.fighting and not u.fixed:
                    u.flee_t = 0.0
                    n += 1
                    self.events.append((self.t, "broke off", u))
        if n:
            self.broke.add(fid)
        return n

    # ------------------------------------------------------------------------------------------- the step
    def step(self, dt: float | None = None) -> None:
        if self.over:
            return
        p = self.p
        dt = dt or p.step_s
        self.t += dt
        # running ships are out when they have run long enough
        for s in (0, 1):
            for u in self.sides[s]:
                if u.alive and not u.gone and u.flee_t >= 0.0:
                    u.flee_t += dt
                    if u.flee_t >= u.flee_need:
                        u.gone = True
                        self.events.append((self.t, "out", u))
        # shields come back
        for s in (0, 1):
            for u in self.sides[s]:
                if u.alive and not u.gone and u.shield < u.shield_max:
                    u.shield = min(u.shield_max, u.shield + u.regen * dt)
        if self.t >= self.approach_s - 20.0:
            dmg = [self._fire(0, dt), self._fire(1, dt)]                 # (both from the state at the start of the step)
            self._apply(1, dmg[0])
            self._apply(0, dmg[1])
            self.damage_dealt[0] += dmg[0][0] + dmg[0][1]
            self.damage_dealt[1] += dmg[1][0] + dmg[1][1]
            self._air(dt)
            for s in (0, 1):                                              # a ship too hurt to fight turns away on its own, whatever the fleet does
                for u in self.sides[s]:
                    if u.fighting and not u.fixed and u.hull_frac < p.flee_hull:
                        u.flee_t = 0.0
                        self.events.append((self.t, "broke off", u))
        self._morale(dt)
        # it is decided when one side has nothing left on the field: no ship fighting and none still running (the ones that run stay targets until they are out)
        pa, pb = self.alive(0), self.alive(1)
        if not pa or not pb:
            self.over = True
            self.winner = 1 if (not pa and pb) else 0 if (not pb and pa) else -1
        elif self.t >= self.approach_s + 1500.0:
            self.over = True

    def _fire(self, s: int, dt: float) -> tuple[float, float]:
        """What side `s` throws this step: (direct damage, missile damage)."""
        p = self.p
        mine = [u for u in self.sides[s] if u.alive and not u.gone]
        direct = 0.0
        for u in mine:
            if u.flee_t >= 0.0:
                continue                                              # a ship that is running does not fire
            direct += u.p
        f, b = self.craft(s)
        air = f * p.f_dps + b * p.b_dps
        edge = 1.0
        if s == self.defender:
            edge *= p.defend_bonus
        if s == self.surprise and self.t < self.approach_s + 60.0:
            edge *= p.surprise
        jitter = max(0.3, self.rng.gauss(1.0, p.sigma_step))
        ramp = min(1.0, 0.15 + 0.85 * max(0.0, self.t - self.approach_s) / p.ramp_s)
        d_direct = (direct + air) * dt * self.luck[s] * jitter * edge * ramp
        # missiles: a salvo every cycle, shot down by the other side's point defence
        d_msl = 0.0
        if self.t >= self.msl_t[s]:
            self.msl_t[s] = self.t + p.msl_cd
            salvo = 0.0
            for u in mine:
                if u.flee_t < 0.0 and u.missiles > 0:
                    n = min(u.missiles, max(1.0, u.msl_max * p.msl_frac))
                    u.missiles -= n
                    salvo += n
            pd = sum(u.pd for u in self.sides[1 - s] if u.alive and not u.gone and u.flee_t < 0.0) * p.pd_per_channel
            hits = max(0.0, salvo - min(salvo * 0.85, pd))
            d_msl = hits * p.msl_dmg * self.luck[s] * edge
        return d_direct, d_msl

    def _score(self, u: Unit) -> float:
        expo = self.p.flee_exposure if u.flee_t >= 0.0 else 1.0
        return u.value * (0.5 + (1.0 - u.frac)) * expo

    def _groups(self, s: int) -> int:
        """How many fire groups side `s` fights as: a big fleet is several groups (the simulation's battle groups think and aim for themselves), a small one is one."""
        n = sum(1 for u in self.sides[s] if u.fighting and not u.fixed)
        return max(1, int(math.ceil(n / max(1.0, self.p.focus_group) - 0.25)))

    def _pick(self, s: int, i: int = 0) -> Unit | None:
        """Fire group `i` of side `s` chooses what it fires on: the enemy's most valuable and most battered ship it can still reach (the next group takes the next one,
        so that a fleet's groups do not all spend themselves on the same ship), and keeps it while it stays near the best."""
        foes = [u for u in self.sides[1 - s] if u.alive and not u.gone]
        if not foes:
            return None
        ranked = sorted(foes, key=self._score, reverse=True)
        best = ranked[i % len(ranked)]
        tg = self.target[s]
        while len(tg) <= i:
            tg.append(None)
        cur = tg[i]
        if cur is not None and cur.alive and not cur.gone and self._score(cur) >= self.p.hold_target * self._score(best):
            return cur
        return best

    def _apply(self, victim: int, dmg: tuple[float, float]) -> None:
        """Damage from the other side lands on side `victim`: direct damage and missile damage, shared among the shooter's fire groups, each on the target it chose."""
        shooter = 1 - victim
        k = self._groups(shooter)
        for amount, leak in ((dmg[0], self.p.shield_leak), (dmg[1], self.p.msl_leak)):
            for i in range(k):
                left = amount / k
                guard = 0
                while left > 1e-6 and guard < 80:
                    guard += 1
                    t = self._pick(shooter, i)
                    if t is None:
                        return
                    self.target[shooter][i] = t
                    left -= self._hit(t, left, leak, shooter)
                    if not t.alive:
                        self.target[shooter][i] = None

    def _hit(self, t: Unit, dmg: float, leak: float, shooter: int) -> float:
        """Raw damage `dmg` on `t`: the shield takes all but `leak` of it until it is down, then the hull. Returns the damage used (a kill wastes some)."""
        used = 0.0
        if t.shield > 0.0:
            cap = t.shield / (1.0 - leak)                              # the raw damage that brings the shield down
            part = min(dmg, cap)
            t.shield -= part * (1.0 - leak)
            t.hull -= part * leak
            used += part
            dmg -= part
            if t.hull <= 0.0:
                return self._kill(t, used, shooter)
        if dmg > 0.0:
            if dmg >= t.hull:
                used += t.hull * (1.0 + self.p.ow)
                t.hull = 0.0
                return self._kill(t, used, shooter)
            t.hull -= dmg
            used += dmg
        return used

    def _kill(self, t: Unit, used: float, shooter: int) -> float:
        t.alive = False
        t.hull = 0.0
        t.shield = 0.0
        self.events.append((self.t, "lost", t))
        return used

    def _air(self, dt: float) -> None:
        """The craft wear down: by the other side's fighters and by point defence (bombers and fighters alike in proportion to what flies)."""
        p = self.p
        f = [self.craft(0)[0], self.craft(1)[0]]
        pdc = [sum(u.pd for u in self.sides[s] if u.alive and not u.gone and u.flee_t < 0.0) for s in (0, 1)]
        for s in (0, 1):
            fl, bo = self.craft(s)
            n = fl + bo
            if n <= 0:
                continue
            loss = (p.air_kill * f[1 - s] + p.air_pd * pdc[1 - s]) * dt * self.rng.uniform(0.7, 1.3)
            frac = min(1.0, loss / n)
            for u in self.sides[s]:
                if u.alive and not u.gone and (u.f or u.b):
                    u.f = max(0.0, u.f * (1.0 - frac))
                    u.b = max(0.0, u.b * (1.0 - frac))

    def _morale(self, dt: float) -> None:
        """A fleet whose side's strength share is under its stance's line for a while breaks off."""
        st = [self.strength(0), self.strength(1)]
        for s in (0, 1):
            tot = st[0] + st[1]
            share = st[s] / tot if tot > 0 else 0.0
            for fid in {u.fid for u in self.sides[s] if u.fighting and not u.fixed}:
                stance = next((u.stance for u in self.sides[s] if u.fid == fid), "steady")
                line = {"bold": self.p.ret_bold, "cautious": self.p.ret_cautious}.get(stance, self.p.ret_steady)
                if share < line:
                    self.low_for[fid] = self.low_for.get(fid, 0.0) + dt
                    if self.low_for[fid] >= self.p.ret_hold_s:
                        self.break_off(fid)
                else:
                    self.low_for[fid] = 0.0


def fight(a: list[Unit], b: list[Unit], rng: random.Random, params: Params = DEFAULT, **kw: Any) -> Engagement:
    """A whole battle between two lists of units, run to its end (the calibration and the forecasts)."""
    e = Engagement((a, b), rng, params, **kw)
    while not e.over:
        e.step()
    return e


def units(side: int, fleet: list[tuple[str, int]], wings: tuple[int, int, int] | None = None, stance: str = "steady", params: Params = DEFAULT,
          fid: str = "") -> list[Unit]:
    """A fleet from (class, number) pairs; the wings go to the first carrier."""
    out: list[Unit] = []
    for cls, n in fleet:
        for _ in range(n):
            out.append(Unit(cls, side, fid or f"s{side}", f"{cls} {len(out) + 1}", stance=stance, params=params))
    if wings:
        for u in out:
            if u.cls in ("acheron", "praetorian", "aquila"):
                u.f, u.b, u.d = wings
                break
    return out


def left(e: Engagement, s: int) -> int:
    """Ships of side `s` that are not destroyed (the ones that left the battle alive count: the bench counts them too)."""
    return sum(1 for u in e.sides[s] if u.alive)


def forecast(a: list[Unit], b: list[Unit], runs: int = 24, seed: int = 0, params: Params = DEFAULT, **kw: Any) -> dict[str, Any]:
    """What a battle between copies of these units would come to: the chance each side holds the field and the ships each loses, in the mean. It reads the
    units as they are (hulls, wings) and leaves them untouched."""
    import copy
    rng = random.Random(seed)
    wins = [0, 0, 0]
    lost = [0.0, 0.0]
    for _ in range(runs):
        ua, ub = [copy.copy(u) for u in a], [copy.copy(u) for u in b]
        e = fight(ua, ub, rng, params, **kw)
        wins[e.winner if e.winner >= 0 else 2] += 1
        lost[0] += sum(1 for u in ua if not u.alive)
        lost[1] += sum(1 for u in ub if not u.alive)
    return {"win": [wins[0] / runs, wins[1] / runs], "draw": wins[2] / runs, "lost": [lost[0] / runs, lost[1] / runs], "runs": runs}
