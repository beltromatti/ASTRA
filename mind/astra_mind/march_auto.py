"""The reflexes of a side's fleets: what they do when no admiral has told them otherwise (docs/GUERRA.md §10).

Not a mind: a doctrine in code, with a few numbers, the way the groups of a battle have reflexes (docs/GUERRA.md §5) and a ship has a point-defence routine.
It reads what the side's high command may read (`March.view`: its own fleets, the tracks of the enemy's, the news) and gives the same orders the admirals give
(`March.order`), marked `by: "auto"`, so a mind's order stands over it and the minds see in their picture what the reflexes did.

Two levels:
  - "full": what a side's fleets do when nobody commands them — answer a threatened system with the fleets that can reach it in time, keep the capital's guard and
    send the rest of its fleet out, gather an army and take the weakest valuable system it can beat with the margin its doctrine asks, scout the unknown, repair what
    is battered, offer peace when the people are tired. It plays a whole war: the bench's admirals, the war that goes on while the Captain is lost or away
    (`fast_forward`), and the fallback when a mind fails;
  - "safety": only what keeps ships alive when a mind has not yet looked: a fleet too battered to fight goes to a depot, small fleets that share a place join.

The same code serves both sides; only the doctrine's numbers differ (the margin of strength wanted before an attack, how much of the capital's fleet stays
home): the symmetry is in the code, and the bench shows it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .march import Fleet, March, SideView, other
from .march_data import CAPITALS, CLASSES, SYSTEMS


@dataclass
class Doctrine:
    """What a side's reflexes are like. `margin`: the strength an army wants over what it knows of the target (and its defences) before it goes; `stage_s`: how long
    it waits for its fleets to gather; `bold`: the stance it attacks with; `home`: the worth of ships the capital keeps whatever happens; `recon_s`: how often it
    sends a fleet to look at what it cannot see; `min_army`: the smallest army it sends out."""
    margin: float = 1.35
    stage_s: float = 420.0
    bold: str = "bold"
    home: float = 8.0
    recon_s: float = 900.0
    min_army: float = 8.0
    start_s: float = 1500.0                          # offence and scouting begin this long after the war does (the opening is fought first)


DOCTRINE = {"astra": Doctrine(margin=1.45, stage_s=480.0, bold="steady", home=8.0, recon_s=900.0, min_army=8.0),
            "mandate": Doctrine(margin=1.30, stage_s=360.0, bold="bold", home=7.0, recon_s=700.0, min_army=8.0)}
ORDER_GAP_S = 420.0                                  # a fleet the reflexes ordered is left alone this long (no changing of mind every minute)


class AutoAdmiral:
    def __init__(self, march: March, side: str, level: str = "full", doctrine: Doctrine | None = None) -> None:
        self.m = march
        self.side = side
        self.level = level
        self.d = doctrine or DOCTRINE[side]
        self.op: dict[str, Any] | None = None             # the operation in hand: {target, stage, fleets, t0, phase}
        self.last_recon = -1e9
        self.log: list[str] = []
        self.seen_max: dict[str, tuple[float, float]] = {}   # system -> (the most enemy strength ever tracked there, when): a commander remembers what stood in his way
        self.ordered: dict[str, float] = {}               # fleet id -> when the reflexes last ordered it

    # ------------------------------------------------------------------------------------------- reading
    def idle(self, f: Fleet) -> bool:
        """A fleet the reflexes may move: nobody has given it an order (or only the reflexes did), it is not fighting, going through a Gate or in the game's hands."""
        return (f.status == "ready" and f.order.by in ("default", "auto") and f.order.kind in ("hold", "defend", "refit", "move") and f.pending is None
                and not f.in_gate and f.where != "" and f.tactical_command == "")

    def margin(self) -> float:
        """The margin of strength the doctrine wants before an attack, worn down by the pressure of a war that is not being won (a government wants results)."""
        age = max(0.0, self.m.t - 7200.0)
        return self.d.margin * (1.0 - min(0.28, age / 20000.0))

    def available(self, f: Fleet) -> bool:
        return self.idle(f) and self.m.t - self.ordered.get(f.id, -1e9) >= ORDER_GAP_S

    def _say(self, text: str) -> None:
        self.log.append(f"{self.m.clock()}: {text}")
        del self.log[:-60]

    def threat(self, v: SideView, system: str) -> float:
        """What the side knows of enemy strength at a system or on its way to it (an estimate from its tracks, with the age they have)."""
        m = self.m
        t = sum(m.track_power(x) for x in v.enemy_at(system, 600.0))
        for tr in v.tracks.values():
            if tr.moving_to == system and m.t - tr.seen_t < 420.0 and tr.system != system:
                t += m.track_power(tr)
        return t

    def _order(self, f: Fleet, kind: str, target: str, why: str, stance: str = "steady", **kw: Any) -> bool:
        ok, detail = self.m.order(self.side, f.id, kind, target, stance=stance, reason=why, by="auto", **kw)
        if ok:
            self.ordered[f.id] = self.m.t
            self._say(f"{f.name}: {kind} {target} ({why})")
        return ok

    # ------------------------------------------------------------------------------------------- the reflexes
    def think(self) -> None:
        if self.m.over:
            return
        self._peace()
        v = self.m.view(self.side)
        for tr in v.tracks.values():
            p = self.m.track_power(tr)
            if p > self.seen_max.get(tr.system, (0.0, 0.0))[0] or self.m.t - self.seen_max.get(tr.system, (0.0, 0.0))[1] > 5400.0:
                self.seen_max[tr.system] = (p, self.m.t)
        self._maintenance(v)
        if self.level == "full":
            self._release_home(v)
            self._defence(v)
            if self.m.t >= self.d.start_s:
                self._offence(v)
                self._recon(v)

    def _peace(self) -> None:
        """A government that has had enough wants the war ended: its high command offers peace, and takes the other side's offer when its own people are tired."""
        m = self.m
        w = m.will[self.side]
        mine = m.proposals.get(self.side)
        theirs = m.proposals.get(other(self.side))
        if theirs and m.t - theirs["t"] < 1200.0 and w < m.pace["peace_will"] + 0.18:
            m.accept(self.side)
            self._say("accepted the other side's offer of peace")
        elif w < m.pace["peace_will"] and (not mine or m.t - mine["t"] > 1200.0):
            m.propose(self.side, "peace", "the people are tired of the war")
            self._say("offered peace")

    def _maintenance(self, v: SideView) -> None:
        m = self.m
        for f in v.own:
            if f.status != "ready" or f.pending is not None or f.in_gate or f.tactical_command or not f.where:
                continue
            if f.order.by in ("admiral", "captain", "story"):
                continue                                              # (a mind's order stands over the reflexes, battered or not)
            depot_here = SYSTEMS[f.where]["depot"] and m.owner(f.where) == self.side
            if f.hull < 0.5 and f.order.kind != "refit" and not (depot_here and f.order.kind == "hold"):
                dest = m.nearest_depot(self.side, f.where, avoid=m.hostile_systems(self.side)) or m.nearest_depot(self.side, f.where)
                if dest:
                    self._order(f, "refit", dest, f"hull {int(100 * f.hull)}%: to a depot", "cautious")
        # small fleets that share a place join the biggest idle fleet there
        by_place: dict[tuple[str, str], list[Fleet]] = {}
        for f in v.own:
            if self.idle(f) and f.order.kind in ("hold", "defend"):
                by_place.setdefault((f.where, f.zone), []).append(f)
        for fl in by_place.values():
            if len(fl) < 2:
                continue
            fl.sort(key=lambda x: -x.n)
            big = fl[0]
            for small in fl[1:]:
                if small.n <= 4 and big.n + small.n <= 28 and small.id in m.fleets and big.id in m.fleets:
                    m.merge(self.side, big.id, small.id)

    def _release_home(self, v: SideView) -> None:
        """The capital keeps a guard (`home` worth of ships and its defences); what the yards have added beyond it goes into the field."""
        m = self.m
        cap = CAPITALS[self.side]
        here = [f for f in v.own_at(cap) if f.status == "ready" and f.order.by in ("default", "auto") and f.tactical_command == ""]
        if not here:
            return
        total = sum(f.power for f in here)
        spare = total - self.d.home - 0.6 * self.threat(v, cap)
        if spare < 3.0:
            return
        big = max(here, key=lambda f: f.power)
        if big.n < 3 or big.status != "ready" or big.pending is not None:
            return
        # detach the lighter ships of the fleet, up to the spare worth, into a fleet for the field
        pick: dict[str, int] = {}
        got = 0.0
        for s in sorted(big.ships, key=lambda s: (CLASSES[s.cls]["worth"] > 2.0, -s.hull)):
            w = CLASSES[s.cls]["worth"]
            if got + w > spare + 0.5 or sum(pick.values()) >= big.n - 1:
                continue
            pick[s.cls] = pick.get(s.cls, 0) + 1
            got += w
        if got >= 2.5 and sum(pick.values()) < big.n:
            before = set(m.fleets)
            ok, d = m.split(self.side, big.id, pick, name=f"{cap} Field Fleet", reason="the capital's spare ships go into the field")
            if ok:
                self._say(d)
                for fid in set(m.fleets) - before:
                    m.fleets[fid].zone = "gate"
                    m.fleets[fid].order.position = "gate"

    def _threatened(self, v: SideView) -> list[tuple[float, str, float, float]]:
        out = []
        for name in self.m.sys:
            if self.m.owner(name) != self.side:
                continue
            t = self.threat(v, name)
            if t < 0.8:
                continue
            d = v.own_power(name) + sum(f.power for f in v.own if f.route and f.route[-1] == name and f.where != name)
            out.append((SYSTEMS[name]["value"] * t, name, t, d))
        out.sort(reverse=True)
        return out

    def _defence(self, v: SideView) -> None:
        m = self.m
        for _, name, t, d in self._threatened(v):
            if d >= 1.25 * t:
                continue
            need = 1.3 * t - d
            cands = [f for f in v.own if self.available(f) and f.where != name and (m.eta(f, name) or 1e9) < 1200.0
                     and not (f.where == CAPITALS[self.side] and name != CAPITALS[self.side])]
            cands.sort(key=lambda f: m.eta(f, name) or 1e9)
            cands = [f for f in cands if self.threat(v, f.where) <= 0.5 * f.power]          # (a fleet is needed where it stands if the enemy is there)
            if d + sum(f.power for f in cands) < 0.85 * t and SYSTEMS[name]["value"] < 9:
                continue                                              # (it cannot be held: the fleets are kept for where they can win, not fed in one by one)
            for f in cands:
                if need <= 0:
                    break
                if self._order(f, "defend", name, f"{name} is threatened (about {t:.0f} against {d:.0f})", "steady", position="gate" if SYSTEMS[name]["value"] < 9 else "world"):
                    need -= f.power
            # a fleet that stands alone where the enemy already is, outmatched and with no help coming, breaks off rather than die for nothing
            now = [x for x in v.enemy_at(name, 200.0) if x.system == name]
            here = [f for f in v.own_at(name) if self.available(f)]
            if now and here and name != CAPITALS[self.side] and SYSTEMS[name]["value"] < 9 and sum(f.power for f in here) < 0.5 * t and need > 0.6 * t:
                for f in here:
                    dest = m.nearest_depot(self.side, name, avoid={name} | m.hostile_systems(self.side))
                    if dest:
                        self._order(f, "withdraw", dest, f"outnumbered at {name} ({sum(x.power for x in here):.0f} against about {t:.0f})", "cautious")

    def _offence(self, v: SideView) -> None:
        m = self.m
        d = self.d
        if self.op is not None:
            self._continue_op(v)
            return
        if any(t >= 1.0 and SYSTEMS[n]["value"] >= 4 and dd < 1.2 * t for _, n, t, dd in self._threatened(v)):
            return                                                    # (the home ground first)
        army = [f for f in v.own if self.available(f) and f.hull > 0.8 and f.supply > 0.6]
        power = sum(f.power for f in army)
        if power < d.min_army:
            return
        best: tuple[float, str] | None = None
        mine = {n for n in m.sys if m.owner(n) == self.side}
        for name in m.sys:
            if m.owner(name) == self.side or m.neutral(name):
                continue
            if not any(nb in mine for nb in m.links(name)):
                continue                                              # (a war is taken a system at a time: only what borders ground it holds)
            etas = [m.eta(f, name) for f in army]
            if any(e is None for e in etas) or max(etas) > 1500.0:
                continue
            known = v.enemy_power(name, 1500.0)
            prior = 0.0
            if not v.enemy_at(name, 1500.0):
                prior = 3.0 if m.owner(name) in ("astra", "mandate") else 1.0
                if SYSTEMS[name]["yard"] > 0:
                    prior += 1.5                                      # (a yard keeps a reserve)
                seen = self.seen_max.get(name)
                if seen and m.t - seen[1] < 5400.0:
                    prior = max(prior, 0.9 * seen[0])                 # (what stood there before still may)
            opposing = known + prior + (0.5 * SYSTEMS[name]["fort"] if m.owner(name) != "silent" else 0.0)
            if power < self.margin() * opposing:
                continue
            score = SYSTEMS[name]["value"] / (1.0 + opposing / max(1.0, power)) - 0.0004 * max(etas)
            if best is None or score > best[0]:
                best = (score, name)
        if best is None:
            return
        target = best[1]
        near = sorted(army, key=lambda f: m.eta(f, target) or 1e9)
        stage = near[0].where
        chosen: list[Fleet] = []
        for f in near:
            chosen.append(f)
            if sum(x.power for x in chosen) >= self.margin() * (v.enemy_power(target, 1500.0) + 3.0) + 2.0:
                break
        self.op = {"target": target, "stage": stage, "fleets": [f.id for f in chosen], "t0": m.t, "phase": "stage"}
        for f in chosen:
            if f.where != stage:
                self._order(f, "move", stage, f"gather at {stage} for {target}", "steady")
            else:
                self.ordered[f.id] = m.t
        self._say(f"operation against {target}: gathering {len(chosen)} fleets ({sum(f.power for f in chosen):.0f}) at {stage}")

    def _continue_op(self, v: SideView) -> None:
        m = self.m
        d = self.d
        op = self.op
        assert op is not None
        fleets = [m.fleets[i] for i in op["fleets"] if i in m.fleets and m.fleets[i].side == self.side]
        if not fleets or m.owner(op["target"]) == self.side:
            self.op = None
            return
        if op["phase"] == "stage":
            gathered = all(f.where == op["stage"] and not f.in_gate and f.status == "ready" for f in fleets)
            if gathered or m.t - op["t0"] > d.stage_s + 600.0:
                known = v.enemy_power(op["target"], 1500.0) + 2.0
                if sum(f.power for f in fleets if not f.in_gate) < self.margin() * known * 0.9:
                    self._say(f"operation against {op['target']} called off: the enemy there is about {known:.0f}")
                    self.op = None
                    return
                op["phase"] = "go"
                for f in fleets:
                    if not f.in_gate:
                        self._order(f, "assault", op["target"], f"attack {op['target']} with the army gathered", d.bold)
        elif op["phase"] == "go":
            if m.t - op["t0"] > d.stage_s + 2400.0 or all(f.order.kind != "assault" or (f.where == op["target"] and f.status == "ready") for f in fleets):
                self.op = None

    def _recon(self, v: SideView) -> None:
        m = self.m
        if m.t - self.last_recon < self.d.recon_s:
            return
        spare = sorted([f for f in v.own if self.available(f) and f.n <= 3 and f.supply > 0.5], key=lambda f: f.power)
        if not spare:
            return
        f = spare[0]
        targets = []
        for name in m.sys:
            if m.owner(name) == self.side or (m.neutral(name) and name != "Veyra"):
                continue
            if v.enemy_at(name, 1200.0):
                continue
            h = m.hops(f.where, name, self.side)
            if h <= 2:
                targets.append((SYSTEMS[name]["value"] / (1 + h), name))
        if not targets:
            return
        targets.sort(reverse=True)
        self.last_recon = m.t
        self._order(f, "recon", targets[0][1], f"look at {targets[0][1]}: nothing is known of it", "cautious", dark=True)


# ------------------------------------------------------------------------------------------------ the war that goes on
def fast_forward(march: March, seconds: float, autos: dict[str, AutoAdmiral] | None = None, think_s: float = 90.0) -> list[str]:
    """Let the war run on its own for `seconds` of war time (both sides on their reflexes): what happens while the Captain is away or the ship is lost. Returns what
    the war's record says of it (the weighty events, oldest first)."""
    autos = autos or {s: AutoAdmiral(march, s) for s in ("astra", "mandate")}
    n0 = march.event_n
    end = march.t + seconds
    while march.t < end and not march.over:
        march.advance(min(end, march.t + think_s))
        for a in autos.values():
            a.think()
    return [f"{e.system + ': ' if e.system else ''}{e.text.get('astra') or e.text.get('mandate')}" for e in march.events if e.n > n0 and e.weight >= 2]
