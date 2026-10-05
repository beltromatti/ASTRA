"""The war of the March: fleets of both sides on the map of the Janus Gates, the way they move, find each other, fight, besiege, repair, resupply, are built
and sapped; who knows what; how the war ends (docs/GUERRA.md §10).

The Aquila's system is the real simulation (the war bench's ships, the tactical commanders, the Captain). Everywhere else the war goes on here, and this
module is the world's rules for it — mechanics, never judgement:

  - FLEETS are lists of real ships (class, name, hull, a carrier's wings) with supply, morale, a place, a route through the Gates and an order. The orders
    are the admirals' (strategy.py; or the code's own reflexes, march_auto.py, for a fleet nobody has ordered): they say what a fleet is to do, and this code
    does it: hop by hop through the Gates with the times a Gate costs, meeting whoever is there.
  - A BATTLE between fleets away from the Aquila is march_battle.py (fitted on the war bench). It runs while the clock does: a battle lasts minutes, reinforcements
    arrive in it, an admiral can order a fleet to break off; at its end hulls, losses and retreats are in the fleets, and what is lost stays lost.
  - A SIEGE: a fleet that holds a system whose defenders are beaten takes it, after a time that grows with what it is worth; a fleet that stands unopposed in a
    system nobody holds claims it. A yard that is blockaded builds nothing; a fleet at a depot is repaired and resupplied; yards build ships by the points they
    make. The Mandate's shipbreakers turn some of what is lost on their ground into hulls.
  - THE FOG: each side knows its own fleets exactly and the enemy's as its eyes find them — a working listening post sees the fleets in its system and the Gates
    cycling into it, a fleet sees what is in its system, the Aquila sees where she is — as tracks with an age and an estimate, never the truth; a force running dark
    arrives without a warning. Orders and reports take the Gates to travel.
  - THE WAR'S COURSE: both sides have a will to fight that losses and lost systems wear down and victories feed; a capital taken or a will gone ends the war, and
    two wills spent make an armistice possible. Nothing here is rigged for anyone: the same rules for both sides, the same dice, the bench shows it.

`March.tick(dt)` is the world; everything the minds and the director read comes from `view(side)` (a side's knowledge), `director_view()` (everything) and the
events; everything they do goes through `order`, `split`, `merge`, `set_build`, `claim_*`. The LOD with the real simulation (a fleet that arrives where the
Aquila is, losses read back from it) is march_glue.py."""
from __future__ import annotations

import json
import logging
import math
import os
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from . import march_battle as mb
from .march_data import (ASTRA_PEOPLE, ASTRA_SHIPS, CAPITALS, CARRIERS, CLASSES, HQ, MANDATE_PEOPLE, MANDATE_SHIPS, MARCH_OPENING, ORBAT, PACE, SYSTEMS, YARD_DEFAULT)
from .war import WarMap

log = logging.getLogger("astra.march")

SIDES = ("astra", "mandate")
STANCES = ("bold", "steady", "cautious")
ORDERS = ("hold", "move", "defend", "assault", "raid", "blockade", "reinforce", "escort", "withdraw", "recon", "refit")
SIDE_WORD = {"astra": "ASTRA", "mandate": "Mandate"}
STEP_S = 5.0
STRAGGLERS = "stragglers of "                                   # the note of a small fleet made of ships that jumped out of the real simulation's system


def other(side: str) -> str:
    return "mandate" if side == "astra" else "astra"


# ------------------------------------------------------------------------------------------------ the things
@dataclass
class Ship:
    cls: str
    name: str
    hull: float = 1.0                                   # hull integrity 0..1: damage stays until a depot repairs it
    cid: str = ""                                       # the contact id it has in the real simulation (T-21), when it is there
    fighters: int = 0
    bombers: int = 0
    drones: int = 0
    captain: str = ""                                   # a person the story gave it (a key into the people the minds know)
    wmax: tuple[int, int, int] = (0, 0, 0)              # the wing it carries when it is rearmed at a depot (fighters, bombers, drones)

    def to_dict(self) -> dict[str, Any]:
        return {"cls": self.cls, "name": self.name, "hull": round(self.hull, 4), "cid": self.cid, "f": self.fighters, "b": self.bombers, "d": self.drones, "captain": self.captain,
                "wmax": list(self.wmax)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Ship":
        w = d.get("wmax") or [0, 0, 0]
        return Ship(d["cls"], d["name"], float(d.get("hull", 1.0)), d.get("cid", ""), int(d.get("f", 0)), int(d.get("b", 0)), int(d.get("d", 0)), d.get("captain", ""),
                    (int(w[0]), int(w[1]), int(w[2])))

    @property
    def value(self) -> float:
        """What it is worth in a fleet now: its class's worth, less what damage has taken."""
        return CLASSES[self.cls]["worth"] * (0.35 + 0.65 * self.hull)


@dataclass
class Order:
    kind: str = "hold"
    target: str = ""                                    # a system, or a fleet id (reinforce, escort)
    stance: str = "steady"
    dark: bool = False                                  # run silent: no Gate wake ahead of the arrival, slower
    by: str = "default"                                 # admiral | auto | captain | story | default
    reason: str = ""
    since: float = 0.0
    until: float | None = None                          # the time the order runs out (a raid, a recon); then the fleet goes back where it came from
    position: str = ""                                  # where in the system a defending fleet stands: "gate" (the Janus Gate and Keeper Station: whatever comes through
                                                        # meets it first) or "world" (over the planet and its yards: it comes to the Gate when the Gate is attacked)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "target": self.target, "stance": self.stance, "dark": self.dark, "by": self.by, "reason": self.reason, "since": round(self.since, 1),
                "until": None if self.until is None else round(self.until, 1), "position": self.position}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Order":
        return Order(d.get("kind", "hold"), d.get("target", ""), d.get("stance", "steady"), bool(d.get("dark", False)), d.get("by", "default"), d.get("reason", ""),
                     float(d.get("since", 0.0)), d.get("until"), d.get("position", ""))


@dataclass
class Fleet:
    id: str
    side: str
    name: str
    ships: list[Ship]
    where: str = ""                                     # the system it is in; "" while it is going through a Gate
    supply: float = 1.0
    morale: float = 0.8
    order: Order = field(default_factory=Order)
    pending: Order | None = None                        # an order given and on its way to the fleet (it takes the Gates to travel)
    pending_at: float = 0.0
    route: list[str] = field(default_factory=list)      # the systems still to go through, the next first
    hop_from: str = ""                                  # (in a Gate) where it left
    arrive_at: float = 0.0                              # when the hop ends
    depart_at: float = 0.0                              # when it jumps (it forms up first)
    wake_sent: bool = False
    commander: dict[str, Any] = field(default_factory=dict)      # the person who leads it: a name, a rank, a bio, a voice; or {"key": ...} for the ones the game knows
    status: str = "ready"                               # ready | moving | engaged | besieging | refitting | scripted | real
    scripted: str = ""                                  # the game's own script brings it in (the Aurelia opening): the March leaves it alone until it is released
    scripted_at: float = 0.0
    dark: bool = False
    hidden_until: float = 0.0                           # a force that arrived unseen stays so this long
    arrived_t: float = 0.0
    origin: str = ""                                    # where it came from (a raid goes back there)
    groups: list[list[Any]] = field(default_factory=list)       # battle groups when it is materialised: [name, formation, [ship indexes]]
    tactical_command: str = ""                          # who commands it in the real simulation: "captain" (the Aquila's picket) | ""
    note: str = ""
    zone: str = "gate"                                  # where in its system it is: "gate" (the Janus Gate) or "world" (over the planet): see Order.position
    crossing_until: float = 0.0                         # a fleet crossing the system from the Gate to the world is out of reach of both until then
    untouchable_until: float = 0.0                      # a fleet that broke off is out of contact for a while
    respond_at: float = 0.0                             # when a fleet over the world joins a fight at the Gate

    # --- reading
    @property
    def n(self) -> int:
        return len(self.ships)

    @property
    def power(self) -> float:
        return sum(s.value for s in self.ships)

    @property
    def hull(self) -> float:
        return sum(s.hull for s in self.ships) / len(self.ships) if self.ships else 0.0

    @property
    def classes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.ships:
            out[s.cls] = out.get(s.cls, 0) + 1
        return out

    @property
    def speed(self) -> float:
        return min((CLASSES[s.cls]["speed"] for s in self.ships), default=300.0)

    @property
    def in_gate(self) -> bool:
        return not self.where

    def composition(self) -> str:
        return composition(self.classes)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "side": self.side, "name": self.name, "ships": [s.to_dict() for s in self.ships], "where": self.where, "supply": round(self.supply, 4),
                "morale": round(self.morale, 4), "order": self.order.to_dict(), "pending": self.pending.to_dict() if self.pending else None, "pending_at": round(self.pending_at, 1),
                "route": self.route, "hop_from": self.hop_from, "arrive_at": round(self.arrive_at, 1), "depart_at": round(self.depart_at, 1), "wake_sent": self.wake_sent,
                "commander": self.commander, "status": self.status, "scripted": self.scripted, "scripted_at": self.scripted_at, "dark": self.dark,
                "hidden_until": round(self.hidden_until, 1), "arrived_t": round(self.arrived_t, 1), "origin": self.origin, "groups": self.groups,
                "tactical_command": self.tactical_command, "note": self.note, "zone": self.zone, "crossing_until": round(self.crossing_until, 1),
                "untouchable_until": round(self.untouchable_until, 1), "respond_at": round(self.respond_at, 1)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Fleet":
        f = Fleet(d["id"], d["side"], d["name"], [Ship.from_dict(s) for s in d.get("ships", [])], d.get("where", ""), float(d.get("supply", 1.0)), float(d.get("morale", 0.8)),
                  Order.from_dict(d.get("order") or {}), Order.from_dict(d["pending"]) if d.get("pending") else None, float(d.get("pending_at", 0.0)), list(d.get("route", [])),
                  d.get("hop_from", ""), float(d.get("arrive_at", 0.0)), float(d.get("depart_at", 0.0)), bool(d.get("wake_sent", False)), dict(d.get("commander") or {}),
                  d.get("status", "ready"), d.get("scripted", ""), float(d.get("scripted_at", 0.0)), bool(d.get("dark", False)), float(d.get("hidden_until", 0.0)),
                  float(d.get("arrived_t", 0.0)), d.get("origin", ""), list(d.get("groups") or []), d.get("tactical_command", ""), d.get("note", ""),
                  d.get("zone", "gate"), float(d.get("crossing_until", 0.0)), float(d.get("untouchable_until", 0.0)), float(d.get("respond_at", 0.0)))
        return f


def composition(classes: dict[str, int]) -> str:
    """"2 praetorian, 6 vigilant"."""
    order = ("praetorian", "acheron", "aquila", "vigilant", "styx", "lethe")
    return ", ".join(f"{classes[c]} {c}" for c in order if classes.get(c))


@dataclass
class Sys:
    """What the war adds to a system of the map: its works, its defences, who is besieging it."""
    name: str
    fort_level: float
    fort_hp: float = 1.0
    post: dict[str, bool] = field(default_factory=dict)          # side -> a working listening post (it sees the fleets here and the Gates cycling)
    yard: float = 0.0
    build: str = ""
    progress: float = 0.0                                        # points towards the next ship
    siege_by: str = ""                                           # the side that is taking it
    siege_s: float = 0.0
    claim_by: str = ""
    claim_s: float = 0.0
    blockaded_by: str = ""
    last_fight_t: float = -1e9
    raid_s: float = 0.0                                          # how long raiders have been at the yard and the post unopposed
    restore_s: float = 0.0                                       # how long the owner has had the place to itself since its post went silent

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "fort_hp": round(self.fort_hp, 3), "post": self.post, "build": self.build, "progress": round(self.progress, 6), "siege_by": self.siege_by,
                "siege_s": round(self.siege_s, 1), "claim_by": self.claim_by, "claim_s": round(self.claim_s, 1), "blockaded_by": self.blockaded_by,
                "last_fight_t": round(self.last_fight_t, 1), "raid_s": round(self.raid_s, 1), "restore_s": round(self.restore_s, 1)}


@dataclass
class Event:
    """A fact of the war. `text` is what each side that could know it would say of it (the fog: they do not say the same thing); `sides` are the ones who learn it,
    when they learn it is `t` plus the time the news takes (the Gates)."""
    n: int
    t: float
    kind: str
    system: str
    text: dict[str, str]
    sides: tuple[str, ...]
    weight: int = 1                                              # 0 routine, 1 minor, 2 significant, 3 major
    fleets: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)
    rn: dict[str, int] = field(default_factory=dict)             # side -> the number under which that side received it (the order it learnt things in: the Gates deliver out of order)

    def to_dict(self) -> dict[str, Any]:
        return {"n": self.n, "t": round(self.t, 1), "kind": self.kind, "system": self.system, "text": self.text, "sides": list(self.sides), "weight": self.weight,
                "fleets": list(self.fleets), "data": self.data, "rn": self.rn}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Event":
        return Event(int(d["n"]), float(d["t"]), d["kind"], d.get("system", ""), dict(d.get("text") or {}), tuple(d.get("sides") or ()), int(d.get("weight", 1)),
                     tuple(d.get("fleets") or ()), dict(d.get("data") or {}), {k: int(v) for k, v in (d.get("rn") or {}).items()})


@dataclass
class Track:
    """What a side knows of an enemy fleet: where it was seen, when, and an estimate of what it is (the truth is never here)."""
    fid: str
    system: str
    seen_t: float
    level: int                                                   # 1 contact (a count, roughly) · 2 classified (counts by class, give or take one) · 3 identified
    n: int
    classes: dict[str, int] | None
    hull: float | None
    moving_to: str = ""
    arrive_t: float = 0.0                                        # when it comes out at `moving_to`, as the Gate's cycling told it (0: not known)

    def to_dict(self) -> dict[str, Any]:
        return {"fid": self.fid, "system": self.system, "seen_t": round(self.seen_t, 1), "level": self.level, "n": self.n, "classes": self.classes, "hull": self.hull,
                "moving_to": self.moving_to, "arrive_t": round(self.arrive_t, 1)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Track":
        return Track(d["fid"], d["system"], float(d["seen_t"]), int(d["level"]), int(d["n"]), d.get("classes"), d.get("hull"), d.get("moving_to", ""),
                     float(d.get("arrive_t", 0.0)))


@dataclass
class Battle:
    system: str
    t0: float
    eng: mb.Engagement
    fleets: dict[str, list[str]]                                 # side -> the fleets in it
    units: dict[int, Any] = field(default_factory=dict)          # id(unit) -> (fleet id, ship index)
    started_by: str = ""
    last_news_t: float = 0.0
    lost_points: dict[str, float] = field(default_factory=lambda: {"astra": 0.0, "mandate": 0.0})
    lost_ships: dict[str, int] = field(default_factory=lambda: {"astra": 0, "mandate": 0})
    lost_names: dict[str, list[str]] = field(default_factory=lambda: {"astra": [], "mandate": []})
    capital_lost: bool = False
    settled: set[str] = field(default_factory=set)               # fleets whose part of the battle is already written back
    fled: list[str] = field(default_factory=list)
    fort_side: int = -1
    fort_unit: Any = None
    strengths0: tuple[float, float] = (0.0, 0.0)
    zone: str = "gate"


# ------------------------------------------------------------------------------------------------ the March
class March:
    def __init__(self, war: WarMap | None = None, *, seed: int = 1, path: str | None = None, params: mb.Params | None = None) -> None:
        self.war = war or WarMap()
        self.rng = random.Random(seed)
        self.seed = seed
        self.bp = params or mb.DEFAULT
        self.save_path = path
        self.pace = dict(PACE)
        self.t = 0.0
        self.fleets: dict[str, Fleet] = {}
        self.sys: dict[str, Sys] = {}
        self.battles: dict[str, Battle] = {}
        self.events: list[Event] = []
        self.event_n = 0
        self.inbox: dict[str, deque[tuple[float, Event]]] = {s: deque() for s in SIDES}
        self.log: dict[str, deque[Event]] = {s: deque(maxlen=60) for s in SIDES}
        self.rcv: dict[str, int] = {s: 0 for s in SIDES}                              # how many events each side has received (the cursor a mind reads its news by)
        self.tracks: dict[str, dict[str, Track]] = {s: {} for s in SIDES}
        self.will: dict[str, float] = dict(self.pace["will_start"])                  # type: ignore[arg-type]
        self.plans: dict[str, str] = {s: "" for s in SIDES}
        self.plan_t: dict[str, float] = {s: 0.0 for s in SIDES}
        self.score: dict[str, dict[str, float]] = {s: {"lost_points": 0.0, "killed_points": 0.0, "ships_lost": 0, "ships_killed": 0, "systems_taken": 0, "systems_lost": 0} for s in SIDES}
        self.over: dict[str, Any] = {}                                               # the war's end: {"outcome": ..., "winner": ..., "t": ..., "why": ...}
        self.guilds_open: dict[str, float] = {}                                      # side -> until when Veyra's Gates are open to its warships
        self.home_orders: dict[str, dict[str, Any]] = {}                             # side -> {"text", "until"}: what the government at home demands (the story's, for both)
        self.tender_free_at: dict[str, float] = {"astra": 0.0, "mandate": 0.0}       # a side's supply tenders are few: one at a time, and busy for a while
        self.aquila_task: dict[str, Any] = {}                                        # Fleet's standing order to the Aquila: {"system", "mission", "why", "t"}
        self.truce: dict[str, Any] = {}                                              # an armistice in force: {"until": t, "by": [..]}
        self.proposals: dict[str, dict[str, Any]] = {}                               # side -> a standing proposal for a truce or peace
        self.aquila: dict[str, Any] = {"where": HQ["astra"], "lane": "", "since": 0.0}  # the player's ship: where she is (the real simulation's system), or in a Gate lane
        self.real_system: str = ""                                                   # the system the real simulation runs (set by the glue): no abstract battle there
        self.real_fight: bool = False                                                # ... and whether a fight is on in it right now
        self.real_tally: dict[str, dict[str, Any]] = {s: {"lost": 0, "names": [], "points": 0.0} for s in SIDES}   # what the real fight has cost each side since it began
        self.real_t0: float = 0.0
        self.aquila_gate_km: float | None = None                                     # how far the Janus Gate is from the Aquila in the real simulation (the glue reads it from the game): the minutes a force needs
        self.opening_plan: list[dict[str, Any]] = []                                 # the scenario's first moves not yet made (the March-driven opening: `march_opening`)
        self.hail_fleets: set[str] = set()                                           # the fleets whose commander opens a channel to the Aquila when they come into her system (once)
        self.captain_skill: float = 1.0                                              # the bench's stand-in for how well the Captain fights the fleet he commands
        self.aquila_fleet: str = ""                                                  # (bench) the fleet the Aquila is in: the real game has her in the real simulation
        self.free_classes = False                                                    # (bench) a world where both sides build and field the same classes
        self.next_id = {"astra": 1, "mandate": 1}
        self.used_names: set[str] = set()
        self.listeners: list[Callable[[Event], None]] = []
        self.dirty = True
        self.last_save = 0.0
        self.war.authority = self
        if self._on_arrival not in self.war.observers:
            self.war.observers.append(self._on_arrival)                              # (the Aquila arrives in a system: the war map says so, the March follows her)
        self._init_world()

    # ------------------------------------------------------------------------------------------- the world at the start
    def _init_world(self) -> None:
        for name, d in SYSTEMS.items():
            if name not in self.war.systems:
                continue
            self.sys[name] = Sys(name, float(d["fort"]), 1.0, {s: True for s in d["post"]}, float(d["yard"]), YARD_DEFAULT.get(name, ""))
        for spec in ORBAT:
            self._add_fleet_from(spec)
        for f in self.fleets.values():
            self.next_id[f.side] = max(self.next_id[f.side], int(f.id.split("-")[1][1:]) + 1)
        self._sync_threat()

    def _add_fleet_from(self, spec: dict[str, Any]) -> Fleet:
        ships = []
        for cls, name in spec["ships"]:
            ships.append(Ship(cls, name))
            self.used_names.add(name)
        for i, (idx, kind, n) in enumerate(spec.get("wings") or []):
            if 0 <= idx < len(ships):
                s = ships[idx]
                if kind == "fighter":
                    s.fighters += n
                elif kind == "bomber":
                    s.bombers += n
                else:
                    s.drones += n
        for s in ships:
            s.wmax = (s.fighters, s.bombers, s.drones)
        for i, cid in enumerate(spec.get("contacts") or []):
            if i < len(ships):
                ships[i].cid = cid
        o = spec.get("order") or {}
        f = Fleet(spec["id"], spec["side"], spec["name"], ships, spec.get("where", ""), float(spec.get("supply", 1.0)), float(spec.get("morale", 0.8)),
                  Order(o.get("kind", "hold"), o.get("target", ""), o.get("stance", "steady"), False, "default", o.get("reason", ""), 0.0, None, o.get("position", "")),
                  commander=dict(spec.get("commander") or {}), scripted=spec.get("scripted", ""), scripted_at=float(spec.get("arrives_s", 0.0)), dark=bool(spec.get("dark", False)), groups=[list(g) for g in spec.get("groups") or []],
                  tactical_command=spec.get("tactical_command", ""), origin=spec.get("where", ""))
        if f.scripted:
            f.status = "scripted"                                  # (the game's script brings it in; see `release_script`)
        f.zone = "world" if f.order.position == "world" else "gate"
        self.fleets[f.id] = f
        return f

    # ------------------------------------------------------------------------------------------- the map
    def owner(self, system: str) -> str:
        return str(self.war.systems[system]["owner"])

    def neutral(self, system: str) -> bool:
        return bool(SYSTEMS.get(system, {}).get("neutral"))

    def value(self, system: str) -> float:
        return float(SYSTEMS.get(system, {}).get("value", 3))

    def links(self, system: str) -> list[str]:
        return self.war.links.get(system, [])

    def passable(self, system: str, side: str | None) -> bool:
        """May a war fleet of `side` go through this system's Gate? Veyra's is the Free Guilds': closed to warships unless they have granted a side passage."""
        if not self.neutral(system) or side is None:
            return True
        return self.guilds_open.get(side, 0.0) > self.t

    def grant_passage(self, side: str, seconds: float, why: str = "") -> None:
        """The Free Guilds open Veyra's Gates to the warships of one side for a while (a deal the story or the Captain made: the war's own rules do not)."""
        self.guilds_open[side] = max(self.guilds_open.get(side, 0.0), self.t + seconds)
        self.say("passage", "Veyra", {s: (f"The Free Guilds have opened Veyra's Gates to {SIDE_WORD[side]} warships for {fmt_s(seconds)}" + (f": {why}" if why else "") + ".") for s in SIDES},
                 SIDES, 3, side=side)
        self.dirty = True

    def path(self, a: str, b: str, side: str | None = None) -> list[str] | None:
        """The shortest way through the Gates from `a` to `b`, the systems after `a` (an empty list: already there); None when there is none. With a `side`,
        Veyra's closed Gates are not a way through for its warships."""
        if a == b:
            return []
        prev: dict[str, str] = {a: ""}
        q = deque([a])
        while q:
            x = q.popleft()
            for y in self.links(x):
                if y not in prev and (y == b or self.passable(y, side)):
                    prev[y] = x
                    if y == b:
                        out = [y]
                        while prev[out[-1]] != a:
                            out.append(prev[out[-1]])
                        return out[::-1]
                    q.append(y)
        return None

    def hops(self, a: str, b: str, side: str | None = None) -> int:
        p = self.path(a, b, side)
        return 99 if p is None else len(p)

    def hop_s(self, f: Fleet, dark: bool | None = None) -> float:
        base = self.pace["hop_base_s"] + self.pace["hop_per_ship_s"] * f.n
        return base * (1.3 if (f.dark if dark is None else dark) else 1.0) * self.rng.uniform(0.92, 1.08)

    def eta(self, f: Fleet, target: str) -> float | None:
        """Seconds a fleet needs to reach `target` from where it is (an expected figure: the Gates' tuning varies a little)."""
        start = f.where or (f.route[0] if f.route else "")
        remaining = max(0.0, f.arrive_at - self.t) if f.in_gate else 0.0
        p = self.path(start, target, f.side)
        if p is None:
            return None
        base = self.pace["hop_base_s"] + self.pace["hop_per_ship_s"] * f.n
        return remaining + len(p) * base * (1.3 if f.dark else 1.0) + (self.pace["exit_form_s"] * (len(p) + (1 if f.in_gate else 0)))

    def latency(self, side: str, system: str) -> float:
        """How long an order (or a report) takes between a side's high command and a system: the Gates."""
        h = self.hops(HQ[side], system) if system else 0                         # (orders and reports travel the Gates of the Guilds too: they are not warships)
        return self.pace["order_base_s"] + self.pace["order_hop_s"] * min(h, 8)

    # ------------------------------------------------------------------------------------------- fleets
    def fleets_at(self, system: str, side: str | None = None) -> list[Fleet]:
        return [f for f in self.fleets.values() if f.where == system and (side is None or f.side == side)]

    def side_fleets(self, side: str) -> list[Fleet]:
        return [f for f in self.fleets.values() if f.side == side]

    def find_fleet(self, side: str, ref: str) -> Fleet | None:
        """A fleet of `side` by id, or by name (exact, or a part of it that names one fleet only)."""
        ref = (ref or "").strip()
        if not ref:
            return None
        for f in self.fleets.values():
            if f.side == side and (f.id.lower() == ref.lower() or f.name.lower() == ref.lower()):
                return f
        head = ref.split()[0].strip(":,.;()").lower() if ref.split() else ""        # (the picture writes "F-M4 Interdiction Fleet Main Body": the id is the name's first word)
        for f in self.fleets.values():
            if f.side == side and f.id.lower() == head:
                return f
        hits = [f for f in self.fleets.values() if f.side == side and ref.lower() in f.name.lower()]
        return hits[0] if len(hits) == 1 else None

    def new_fleet_id(self, side: str) -> str:
        i = self.next_id[side]
        self.next_id[side] = i + 1
        return f"F-{'A' if side == 'astra' else 'M'}{i}"

    def ship_name(self, cls: str) -> str:
        pool = (ASTRA_SHIPS if CLASSES[cls]["side"] == "astra" else MANDATE_SHIPS).get(cls) or [cls.title()]
        prefix = "ASN " if CLASSES[cls]["side"] == "astra" else ""
        for n in pool:
            if prefix + n not in self.used_names:
                self.used_names.add(prefix + n)
                return prefix + n
        i = 2
        while f"{prefix}{pool[0]} {i}" in self.used_names:
            i += 1
        self.used_names.add(f"{prefix}{pool[0]} {i}")
        return f"{prefix}{pool[0]} {i}"

    def person_for(self, side: str) -> dict[str, Any]:
        """A leader from the pool for a fleet nobody has named one for (the pools are in march_data.py)."""
        pool = ASTRA_PEOPLE if side == "astra" else MANDATE_PEOPLE
        taken = {f.commander.get("name") for f in self.fleets.values() if f.side == side}
        free = [p for p in pool if p["name"] not in taken]
        return dict(self.rng.choice(free or pool))

    # ------------------------------------------------------------------------------------------- the owners and the fog
    def sees(self, side: str, system: str) -> int:
        """How well `side` sees the fleets in `system` right now: 0 not at all · 1 a contact · 2 classified · 3 identified."""
        lvl = 0
        s = self.sys.get(system)
        own = self.owner(system) == side
        if self.aquila["where"] == system and side == "astra" and not self.aquila["lane"]:
            lvl = 3
        if self.fleets_at(system, side):
            lvl = max(lvl, 2 if any(not f.dark for f in self.fleets_at(system, side)) else 1)
            if any(f.tactical_command for f in self.fleets_at(system, side)):
                lvl = max(lvl, 3)
        if s is not None and s.post.get(side) and own:
            lvl = max(lvl, 3)
        elif own:
            lvl = max(lvl, 2)
        if system == "Veyra":
            lvl = max(lvl, 2)                                      # the Guildhall's spies see every fleet that passes
        # a post next door hears the drives through the Gate
        if lvl == 0:
            for nb in self.links(system):
                s2 = self.sys.get(nb)
                if s2 is not None and s2.post.get(side) and self.owner(nb) == side:
                    lvl = 1
                    break
        return lvl

    def detects(self, side: str, f: Fleet) -> int:
        """The level at which `side` sees the fleet `f` (an enemy's, in a system), counting that a fleet running dark is hard to find."""
        if not f.where:
            return 0
        lvl = self.sees(side, f.where)
        if f.zone == "world" and self.owner(f.where) != side and not any(g.zone == "world" for g in self.fleets_at(f.where, side)) and not (self.aquila["where"] == f.where and side == "astra"):
            lvl = max(0, lvl - 1)                                  # (over the planet, out of sight of whoever stands at the Gate)
        if f.dark and lvl > 0:
            has_eyes = bool(self.fleets_at(f.where, side)) or (self.aquila["where"] == f.where and side == "astra")
            post = bool(self.sys.get(f.where) and self.sys[f.where].post.get(side) and self.owner(f.where) == side)
            lvl = lvl - (0 if (has_eyes or post) else 1)
            if self.t < f.hidden_until and not post:
                lvl = 0
        return max(0, lvl)

    # ------------------------------------------------------------------------------------------- events
    def say(self, kind: str, system: str, text: dict[str, str] | str, sides: tuple[str, ...], weight: int = 1, fleets: tuple[str, ...] = (), **data: Any) -> Event:
        """A fact of the war enters the record; each side that learns it gets its own text, after the time the news takes to come through the Gates."""
        if isinstance(text, str):
            text = {s: text for s in SIDES}
        self.event_n += 1
        ev = Event(self.event_n, self.t, kind, system, {s: text.get(s, "") for s in SIDES}, tuple(sides), weight, tuple(fleets), data)
        self.events.append(ev)
        del self.events[:-400]
        for s in ev.sides:
            if not ev.text.get(s):
                continue
            self.inbox[s].append((self.t + (0.0 if kind in ("captain",) else self.latency(s, system)), ev))
        self.dirty = True
        for fn in list(self.listeners):
            try:
                fn(ev)
            except Exception:  # noqa: BLE001
                log.exception("a listener of the March failed on %s", kind)
        return ev

    def _deliver(self) -> None:
        for s in SIDES:
            q = self.inbox[s]
            keep: list[tuple[float, Event]] = []
            for when, ev in q:
                if when <= self.t:
                    self.rcv[s] += 1
                    ev.rn[s] = self.rcv[s]
                    self.log[s].append(ev)
                else:
                    keep.append((when, ev))
            if len(keep) != len(q):
                self.inbox[s] = deque(keep)

    def news(self, side: str, since: int = 0, min_weight: int = 0) -> list[Event]:
        """What `side` has learnt, oldest first, after the receive number `since` (`rcv[side]` at the last look): what reaches a side is read once, in the order it
        reached it, whatever the order the events happened in."""
        return [e for e in self.log[side] if e.rn.get(side, 0) > since and e.weight >= min_weight]

    # ------------------------------------------------------------------------------------------- the clock
    def run(self, seconds: float) -> None:
        """Run the world for `seconds` of war time."""
        self.advance(self.t + seconds)

    def advance(self, to_t: float) -> None:
        """Run the world up to the (absolute) time `to_t` in steps."""
        while self.t < to_t - 1e-9:
            self.tick(min(STEP_S, to_t - self.t))

    def tick(self, dt: float) -> None:
        self.t += dt
        self._script(dt)
        self._opening(dt)
        self._orders()
        self._movement()
        self._contacts()
        self._battles(dt)
        self._sieges(dt)
        self._upkeep(dt)
        self._intel()
        self._deliver()
        self._courses(dt)
        self._more(dt)
        if self.t - getattr(self, "_threat_t", -99.0) > 15.0:
            self._threat_t = self.t
            self._sync_threat()
        if self.save_path and self.dirty and self.t - self.last_save > 30.0:
            self.save()

    # ------------------------------------------------------------------------------------------- the game's script (the Aurelia opening)
    live_scripts = False                                       # the game brings its scripted fleets in itself (the glue calls `release_script`); the bench's clock does it

    def _script(self, dt: float) -> None:
        if self.live_scripts:
            return
        for f in list(self.fleets.values()):
            if f.status == "scripted" and f.scripted_at and self.t >= f.scripted_at:
                self.release_script(f.id)

    def march_opening(self) -> list[str]:
        """The game has switched its opening script off: the strike group, the vanguard and the relief it was to bring are not coming by it. They are the war's own fleets from now,
        standing where MARCH_OPENING puts them (the order of battle's contact ids for them are void: the game builds none of these ships), and the Interdiction Fleet's first move is the
        scenario's own plan, made by the clock (`_opening`). Returns the fleets taken over."""
        taken: list[str] = []
        for fid, spec in MARCH_OPENING["fleets"].items():
            f = self.fleets.get(fid)
            if f is None or f.status != "scripted":
                continue
            for s in f.ships:
                s.cid = ""
            f.scripted, f.scripted_at, f.status = "", 0.0, "ready"
            f.where = f.origin = str(spec.get("where", f.where))
            f.zone, f.arrived_t, f.hidden_until = "gate", self.t - 600.0, 0.0          # (long since formed up, at the Gate)
            f.dark = bool(spec.get("dark", f.dark))
            o = spec.get("order")
            if o:
                f.order = Order(o.get("kind", "hold"), o.get("target", f.where), o.get("stance", "steady"), False, str(o.get("by", "default")), o.get("reason", ""), self.t, None, "gate")
            taken.append(fid)
        self.opening_plan = [dict(p) for p in MARCH_OPENING["plan"] if p["fleet"] in taken]
        self.hail_fleets = {fid for fid in taken if MARCH_OPENING["fleets"][fid].get("hail")}
        self.dirty = True
        return taken

    def _opening(self, dt: float) -> None:
        """The scenario's first moves (`march_opening`): each is an order of its side's own opening plan, given by the clock at its time; whatever has become of the fleet since,
        an order that cannot be given is dropped (the war has moved on)."""
        if not self.opening_plan:
            return
        due = [p for p in self.opening_plan if self.t >= float(p.get("at_s", 0.0))]
        for p in due:
            self.opening_plan.remove(p)
            ok, detail = self.order(p["side"], p["fleet"], p["kind"], p.get("target", ""), stance=p.get("stance", ""), dark=bool(p.get("dark", False)), reason=p.get("reason", ""),
                                    by="story", instant=True)
            log.info("the opening's move %s %s %s: %s", p["fleet"], p["kind"], p.get("target", ""), detail if ok else "dropped (" + detail + ")")

    def release_script(self, fid: str, system: str = "") -> bool:
        """A fleet the game's script brings in has come: from now on it is in the war's rules (a fleet in the Aquila's system is the real simulation's; the
        glue reads what happens to it)."""
        f = self.fleets.get(fid)
        if f is None or f.status != "scripted":
            return False
        target = system or (f.order.target if f.order.kind in ("assault", "defend", "reinforce", "raid", "recon") and f.order.target in self.sys else self.aquila["where"])
        if f.order.kind in ("reinforce", "escort") and f.order.target in self.fleets:
            target = self.fleets[f.order.target].where or target
        f.where, f.status, f.arrived_t, f.scripted = target, "ready", self.t, ""
        f.hidden_until = self.t + 40.0 if f.dark else 0.0
        self.say("arrival", target, {f.side: f"{f.name} has come through the Gate into {target}.",
                                     other(f.side): f"A force of about {f.n} ships has come through the Gate into {target}."}, SIDES, 2, (f.id,))
        return True

    # ------------------------------------------------------------------------------------------- orders
    def order(self, side: str, ref: str, kind: str, target: str = "", *, stance: str = "", dark: bool = False, reason: str = "", by: str = "admiral",
              until_s: float | None = None, instant: bool = False, position: str = "") -> tuple[bool, str]:
        """An order to a fleet. It reaches the fleet after the time the Gates take (`instant`: the person giving it is with the fleet). Returns (ok, what it will do):
        the facts of it — the route and the time, what is known of the place — never an opinion."""
        f = self.find_fleet(side, ref)
        if f is None:
            names = ", ".join(f"{x.id} {x.name}" for x in self.side_fleets(side))
            return False, f"no fleet '{ref}' of yours (yours: {names})"
        if f.status == "scripted":
            return False, f"{f.name} is not in the war's hands yet: the game's own script is bringing it in"
        kind = (kind or "").strip().lower()
        if kind not in ORDERS:
            return False, f"unknown order '{kind}': {', '.join(ORDERS)}"
        if self.over:
            return False, "the war is over"
        stance = stance if stance in STANCES else (f.order.stance if f.order.stance in STANCES else "steady")
        tgt = (target or "").strip()
        start = f.route[0] if f.in_gate and f.route else f.where
        if kind in ("reinforce", "escort"):
            tf = self.find_fleet(side, tgt)
            if tf is None or tf is f:
                return False, f"no other fleet of yours called '{tgt}'"
            tgt = tf.id
            dest = tf.where or (tf.route[-1] if tf.route else "")
        elif kind in ("hold",) and not tgt:
            dest = start
            tgt = start
        else:
            if not tgt and kind in ("withdraw", "refit"):
                dest = self.nearest_depot(side, start, avoid=self.hostile_systems(side)) or start
                tgt = dest
            else:
                dest = self.war.find(tgt) or ""
                if not dest:
                    return False, f"no system '{tgt}' in the March (systems: {', '.join(self.sys)})"
                tgt = dest
        if kind in ("assault", "blockade", "raid") and self.neutral(dest):
            return False, f"{dest} is neutral ground (the Free Guilds keep it: no side may fight there)"
        if f.status == "real":
            # a fleet the real simulation is playing (it is with the Aquila): the map does not move it. The order is on its record as its high command's intent, which its
            # commanders on the spot read (field_brief), and the Captain with them on the ASTRA side; what they do with it is theirs
            f.order = Order(kind, tgt, stance, dark, by, reason, self.t, None if until_s is None else self.t + float(until_s), position if position in ("gate", "world") else "")
            self.dirty = True
            who = ("the Captain, who commands there, and its captains" if side == "astra" else "its commanders on the spot")
            return True, (f"{f.id} {f.name} is with the Aquila, played ship by ship in {f.where}: it does not move on the map. Your order is on its record as your intent; "
                          f"{who} read it and decide what to do with it (tell the Captain if it cannot wait)" if side == "astra" else
                          f"{f.id} {f.name} is in the fighting at {f.where}, played ship by ship: it does not move on the map. Your order is on its record as your intent; {who} read it and decide")
        p = self.path(start, dest, side) if dest else []
        if p is None:
            why = " (Veyra's Gates are closed to warships: the Free Guilds keep them so unless they grant passage)" if self.neutral("Veyra") and self.path(start, dest) is not None else ""
            return False, f"no way through the Gates from {start} to {dest}{why}"
        lat = 0.0 if instant else self.latency(side, start)
        until = None if until_s is None else self.t + lat + float(until_s)       # (a raid or a recon with no time given runs out a while after it arrives: `_order_reached`)
        o = Order(kind, tgt, stance, dark, by, reason, self.t + lat, until, position if position in ("gate", "world") else "")
        f.pending, f.pending_at = o, self.t + lat
        self.dirty = True
        eta = self.eta(f, dest) if dest and dest != start else 0.0
        bits = [f"{f.id} {f.name}: {kind}" + (f" {tgt}" if tgt else "") + f" ({stance}{', running dark' if dark else ''})"]
        if dest and dest != start:
            bits.append(f"route {' > '.join([start] + (p or []))}, about {fmt_s(eta or 0)} to get there")
        if lat >= 1.0:
            bits.append(f"the order reaches the fleet in {fmt_s(lat)}")
        return True, "; ".join(bits)

    def _apply_order(self, f: Fleet, o: Order) -> None:
        f.order = o
        f.pending = None
        eng = self.battle_of(f)
        start = f.route[0] if f.in_gate and f.route else f.where
        dest = ""
        if o.kind in ("reinforce", "escort"):
            tf = self.fleets.get(o.target)
            dest = (tf.where or (tf.route[-1] if tf.route else "")) if tf else ""
        elif o.target in self.sys:
            dest = o.target
        if eng is not None and o.kind in ("move", "withdraw", "recon", "refit"):
            eng.eng.break_off(f.id)                              # an order to leave is a fleet breaking off
        # (a fleet in a Gate finishes its hop first: its route is that system, and then the way on from it)
        route: list[str] = [f.route[0]] if f.in_gate and f.route else []
        if dest and dest != start:
            route = route + (self.path(start, dest, f.side) or [])
        f.dark = o.dark
        if route and not f.in_gate:
            f.depart_at = self.t + self.pace["exit_form_s"] * (0.4 if f.arrived_t < self.t - 60 else 1.0)
        f.route = route
        if not f.in_gate:
            in_it = eng is not None and f.id in eng.fleets[f.side] and f.id not in eng.settled
            f.status = "engaged" if in_it else ("moving" if f.route else "ready")
        f.note = ""
        self.dirty = True

    def _orders(self) -> None:
        for f in self.fleets.values():
            if f.pending is not None and self.t >= f.pending_at:
                self._apply_order(f, f.pending)

    def nearest_depot(self, side: str, start: str, avoid: set[str] | None = None) -> str | None:
        best: tuple[int, str] | None = None
        for name, d in SYSTEMS.items():
            if not d["depot"] or self.owner(name) != side or (avoid and name in avoid):
                continue
            h = self.hops(start, name, side)
            if h < 99 and (best is None or (h, name) < best):
                best = (h, name)
        return best[1] if best else None

    def hostile_systems(self, side: str) -> set[str]:
        """The systems where an enemy fleet is known to `side` (or sitting on its ground: it sees what is in its own systems)."""
        return {t.system for t in self.tracks[side].values() if t.system}

    def split(self, side: str, ref: str, ships: dict[str, int] | list[int], name: str = "", order: tuple[str, str] | None = None, reason: str = "") -> tuple[bool, str]:
        """Detach ships from a fleet into a fleet of their own (a sub-squadron): `ships` is {class: number} (the healthiest go) or a list of ship positions."""
        f = self.find_fleet(side, ref)
        if f is None:
            return False, f"no fleet '{ref}' of yours"
        if f.status in ("scripted", "real") or f.in_gate:
            return False, f"{f.name} cannot be divided now ({'it is in a Gate' if f.in_gate else 'the real simulation has it'})"
        picked: list[Ship] = []
        if isinstance(ships, dict):
            for cls, n in ships.items():
                have = sorted([s for s in f.ships if s.cls == cls and s not in picked], key=lambda s: -s.hull)
                if len(have) < int(n):
                    return False, f"{f.name} has only {len(have)} {cls}"
                picked += have[:int(n)]
        else:
            idx = sorted({int(i) for i in ships})
            picked = [f.ships[i] for i in idx if 0 <= i < len(f.ships)]
        if not picked:
            return False, "no ships to detach"
        if len(picked) >= len(f.ships):
            return False, f"that is the whole of {f.name}: give it an order instead"
        if self.battle_of(f) is not None:
            return False, f"{f.name} is in a battle: ships cannot be detached from it now"
        nid = self.new_fleet_id(side)
        nf = Fleet(nid, side, name or f"{f.name} detachment", picked, f.where, f.supply, f.morale, Order("hold", f.where, "steady", False, "admiral", reason or "detached", self.t),
                   commander=self.person_for(side), status="ready", arrived_t=self.t, origin=f.where, dark=f.dark)
        for s in picked:
            f.ships.remove(s)
        f.groups = []
        self.fleets[nid] = nf
        self.say("fleet_formed", f.where, {side: f"{nf.name} ({composition(nf.classes)}) detached from {f.name} at {f.where}."}, (side,), 0, (nf.id, f.id))
        ok = True
        detail = f"{nid} {nf.name}: {nf.composition()} detached from {f.id} {f.name} at {f.where}"
        if order is not None:
            ok, d2 = self.order(side, nid, order[0], order[1], reason=reason, instant=True)
            detail += "; " + d2
        return ok, detail

    def merge(self, side: str, into_ref: str, from_ref: str) -> tuple[bool, str]:
        a, b = self.find_fleet(side, into_ref), self.find_fleet(side, from_ref)
        if a is None or b is None or a is b:
            return False, "two different fleets of yours are needed"
        if a.where != b.where or not a.where:
            return False, f"{a.name} is at {a.where or 'a Gate'} and {b.name} at {b.where or 'a Gate'}: they have to be in the same system"
        if self.battle_of(a) is not None or self.battle_of(b) is not None or "scripted" in (a.status, b.status):
            return False, "not while either is in a battle or in the game's hands"
        self._absorb(a, b)
        return True, f"{b.name} joined {a.name}: now {a.n} ships ({a.composition()})"

    def _absorb(self, a: Fleet, b: Fleet) -> None:
        n = a.n + b.n
        a.supply = (a.supply * a.n + b.supply * b.n) / max(1, n)
        a.morale = (a.morale * a.n + b.morale * b.n) / max(1, n)
        a.ships += b.ships
        a.groups = []
        self.fleets.pop(b.id, None)
        for s in SIDES:
            self.tracks[s].pop(b.id, None)
        self.dirty = True

    def set_build(self, side: str, system: str, cls: str) -> tuple[bool, str]:
        s = self.war.find(system)
        if not s or s not in self.sys or self.owner(s) != side or self.sys[s].yard <= 0:
            return False, f"{system} is not a yard of yours"
        if not self.buildable(side, cls):
            return False, f"{cls} is not something your yards build (yours: {', '.join(c for c, d in CLASSES.items() if d['side'] == side and d['cost'] > 0)})"
        st = self.sys[s]
        st.build = cls
        st.progress = min(st.progress, CLASSES[cls]["cost"] * 0.5)
        self.dirty = True
        return True, f"{s} builds {cls} from now on ({CLASSES[cls]['cost']:.1f} points each, {st.yard:.1f} points an hour: about {fmt_s(CLASSES[cls]['cost'] / max(0.1, st.yard) * 3600)} each)"

    def set_plan(self, side: str, text: str) -> None:
        self.plans[side] = (text or "").strip()[:700]
        self.plan_t[side] = self.t
        self.dirty = True

    # ------------------------------------------------------------------------------------------- movement
    def _movement(self) -> None:
        for f in list(self.fleets.values()):
            if f.status in ("scripted", "real") and not f.in_gate:
                continue
            if f.in_gate:
                if not f.wake_sent and not f.dark and f.route and self.t >= f.arrive_at - self.pace["warn_s"]:
                    f.wake_sent = True
                    self._wake(f, f.route[0])
                if self.t >= f.arrive_at:
                    self._arrive(f)
            elif f.route and f.status != "engaged" and self.t >= f.depart_at:
                self._depart(f)

    def _depart(self, f: Fleet) -> None:
        if self.truce and self.owner(f.route[0]) != f.side and f.order.kind in ("assault", "raid", "blockade"):
            return                                                  # (a truce keeps the fleets where they are)
        f.hop_from, f.where = f.where, ""
        dur = self.hop_s(f)
        f.arrive_at = self.t + dur
        f.wake_sent = False
        f.status = "moving"
        f.supply = max(0.0, f.supply - self.pace["supply_per_hop"])
        self.dirty = True

    def _arrive(self, f: Fleet) -> None:
        dest = f.route.pop(0)
        f.where, f.arrived_t, f.wake_sent, f.zone = dest, self.t, False, "gate"
        f.hidden_until = self.t + 90.0 if f.dark else 0.0
        f.status = "ready"
        f.depart_at = self.t + self.pace["exit_form_s"]
        if f.route:
            f.status = "moving"
        else:
            self._order_reached(f)
        side = f.side
        watchers = [s for s in SIDES if s != side and self.detects(s, f) > 0]
        txt = {side: f"{f.name} has come through the Gate into {dest}." if not f.route else f"{f.name} passed through {dest}."}
        for s in watchers:
            lvl = self.detects(s, f)
            txt[s] = f"A force of {self._estimate(s, f, lvl)} has come through the Gate into {dest}."
        self.say("arrival", dest, txt, tuple([side] + watchers), 1 if f.route else (2 if watchers else 1), (f.id,))
        self.dirty = True

    def _wake(self, f: Fleet, dest: str) -> None:
        """The Gate at `dest` is cycling for a fleet that does not run dark: whoever has eyes on it knows something is coming through, a minute before."""
        sides = [s for s in SIDES if s != f.side and self.sees(s, dest) >= 1 and not self.neutral(dest)]
        if not sides:
            return
        txt = {}
        for s in sides:
            lvl = max(1, self.sees(s, dest) - 1)
            txt[s] = (f"The Gate at {dest} is cycling: a force of {self._estimate(s, f, lvl)} is coming through in about {fmt_s(max(0.0, f.arrive_at - self.t))}"
                      + (self.reach_note(f) if (dest == self.real_system and s == "astra") else "") + ".")
            # what the watchers know is a track too: where it comes from, where and when it comes out (the holo tables and the main screen draw it; it was
            # only words, 5 Oct: «a force is coming through» and nothing on the plot)
            old = self.tracks[s].get(f.id)
            if old is None or old.system != dest:
                n, cls = self._noisy(s, f, lvl)
                self.tracks[s][f.id] = Track(f.id, f.hop_from or (old.system if old else ""), self.t, lvl, n, cls, None, dest, f.arrive_at)
        self.say("wake", dest, txt, tuple(sides), 2 if f.n >= 6 or self.value(dest) >= 6 else 1, (f.id,), eta=round(f.arrive_at - self.t, 1))

    def reach_note(self, f: Fleet) -> str:
        """What a force that comes through the Gate into the Aquila's system needs to reach her: the Gate's distance from her and the fleet's cruise speed (a fact of the real
        simulation's geometry: minutes, not seconds, when the Gate is far)."""
        km = self.aquila_gate_km
        if not km or km < 20.0:
            return ""
        return f"; the Gate is {km:.0f} km from the Aquila, and at {f.speed:.0f} m/s they need about {fmt_s(km * 1000.0 / max(100.0, f.speed))} after it to reach her"

    def _estimate(self, side: str, f: Fleet, lvl: int) -> str:
        """How `side` would describe the fleet `f` at detection level `lvl` ("about 8 ships", "about 12 ships: 3 acheron, 9 styx")."""
        r = random.Random(f"{side}|{f.id}|{int(self.t // 300)}|{self.seed}")
        if lvl <= 1:
            n = max(1, round(f.n * math.exp(r.gauss(0.0, 0.22))))
            return f"about {n} ship{'s' if n != 1 else ''}"
        cl = f.classes
        if lvl == 2:
            est = {c: max(0, k + r.choice((-1, 0, 0, 1))) for c, k in cl.items()}
            est = {c: k for c, k in est.items() if k} or dict(cl)
            return f"about {sum(est.values())} ships ({composition(est)})"
        return f"{f.n} ships ({f.composition()})"

    def _order_reached(self, f: Fleet) -> None:
        """A fleet has come to the end of its route: what it does now follows from its order."""
        o = f.order
        if o.kind == "move":
            f.order = Order("hold", f.where, o.stance, False, "auto", f"arrived at {f.where}", self.t)
        elif o.kind == "withdraw":
            f.order = Order("refit", f.where, "cautious", False, "auto", "repairing after the withdrawal", self.t)
        elif o.kind in ("raid", "recon") and o.until is None:
            o.until = self.t + (420.0 if o.kind == "raid" else 300.0)
        f.status = "ready"
        self._place(f)

    def _place(self, f: Fleet) -> None:
        """A fleet that has come to its post takes its place in the system: at the Gate, or over the world (it takes a while to cross)."""
        o = f.order
        if o.kind in ("defend", "hold", "refit", "escort", "reinforce"):
            want = o.position or ("world" if o.kind == "refit" else "gate")
        elif o.kind == "blockade":
            want = "gate"
        else:
            return
        if want != f.zone and f.where:
            f.zone = want
            f.untouchable_until = max(f.untouchable_until, self.t + SYSTEMS.get(f.where, {}).get("crossing_s", 150) * 0.6)

    # ------------------------------------------------------------------------------------------- the real simulation's side of things
    def battle_of(self, f: Fleet) -> Battle | None:
        return self.battles.get(f.where) if f.where else None

    # ------------------------------------------------------------------------------------------- contacts and battles
    @staticmethod
    def _willing(f: Fleet) -> bool:
        """Does the fleet fight what it meets? A fleet sent to look, or to get away, does not look for a fight (but is in one if it is caught)."""
        return f.order.kind not in ("recon", "withdraw") or f.status == "engaged"

    def _contacts(self) -> None:
        if self.truce:
            return
        for system, st in self.sys.items():
            if self.neutral(system) or (system == self.real_system):
                continue
            here = {s: [f for f in self.fleets_at(system, s) if f.status not in ("scripted", "real") and self.t >= f.untouchable_until] for s in SIDES}
            if not (here["astra"] or here["mandate"]):
                continue
            if system in self.battles:
                self._join(self.battles[system], here)
                continue
            owner = self.owner(system)
            fort_ok = owner in SIDES and st.fort_level > 0 and st.fort_hp > 0.12
            started, zone = "", "gate"
            for s in SIDES:
                mine, foes = here[s], here[other(s)]
                if not mine:
                    continue
                for z in ("gate", "world"):
                    mz, fz = [f for f in mine if f.zone == z], [f for f in foes if f.zone == z]
                    if mz and fz and any(self.detects(s, f) > 0 for f in fz) and any(self._willing(f) for f in mz):
                        started, zone = s, z
                        break
                if started:
                    break
                if fort_ok and owner == other(s):
                    attackers = [f for f in mine if f.order.kind in ("assault", "blockade", "raid")]
                    if attackers:
                        started, zone = s, attackers[0].zone                     # (the defences fire on whoever comes to take the place)
                        break
            if started:
                self._start_battle(system, here, started, zone)

    def _stance_of(self, f: Fleet) -> str:
        if f.morale < 0.3 and f.order.stance != "bold":
            return "cautious"
        return f.order.stance if f.order.stance in STANCES else "steady"

    def _unit(self, f: Fleet, ship: Ship, s_idx: int) -> mb.Unit:
        u = mb.Unit(ship.cls, s_idx, f.id, ship.name, hull_frac=ship.hull, supply=f.supply, wing=(ship.fighters, ship.bombers, ship.drones), ref=(f.id, ship),
                    stance=self._stance_of(f), params=self.bp)
        if f.id == self.aquila_fleet:
            u.p *= self.captain_skill                                  # (the Captain commands the fleet the Aquila is in)
        return u

    def add_aquila(self, skill: float = 1.0, fleet: str = "F-A2") -> bool:
        """(The bench) put the Aquila in a fleet of the March: the real game has her in the real simulation, where the Captain fights; here a stand-in with her
        class's numbers and a `skill` for how well he fights what he commands."""
        f = self.fleets.get(fleet)
        if f is None or any(s.cls == "aquila" for s in f.ships):
            return False
        w = CLASSES["aquila"]["wing"]
        f.ships.insert(0, Ship("aquila", "ASN Aquila", 1.0, "AQUILA", w[0], w[1], 0, "", (w[0], w[1], 0)))
        self.aquila_fleet, self.captain_skill = fleet, skill
        return True

    def buildable(self, side: str, cls: str) -> bool:
        return cls in CLASSES and CLASSES[cls]["cost"] > 0 and (self.free_classes or CLASSES[cls]["side"] == side)

    def _start_battle(self, system: str, here: dict[str, list[Fleet]], started_by: str, zone: str = "gate") -> None:
        st = self.sys[system]
        owner = self.owner(system)
        sides: tuple[list[mb.Unit], list[mb.Unit]] = ([], [])
        here = {s: [f for f in here[s] if f.zone == zone] for s in SIDES}                # (the fleets at the place of the contact; the others come when they can)
        for i, s in enumerate(SIDES):
            for f in here[s]:
                for ship in f.ships:
                    sides[i].append(self._unit(f, ship, i))
        fort_side = -1
        fort_unit = None
        if owner in SIDES and st.fort_level > 0 and st.fort_hp > 0.12:
            fort_side = SIDES.index(owner)
            fort_unit = mb.Unit(mb.FORT_CLASS, fort_side, "fort", f"the defences of {system}", hull_frac=st.fort_hp, fort=st.fort_level, params=self.bp)
            sides[fort_side].append(fort_unit)
        if not sides[0] or not sides[1]:
            return
        # who arrived unseen: a force running dark that the other side had not found when the shooting began
        surprise = -1
        for i, s in enumerate(SIDES):
            if any(f.dark and f.hidden_until > self.t for f in here[s]) and not any(self.detects(other(s), f) > 0 for f in here[s] if f.dark):
                surprise = i
        defender = SIDES.index(owner) if owner in SIDES and (SYSTEMS[system]["depot"] or st.post.get(owner)) else -1
        eng = mb.Engagement(sides, random.Random(self.rng.random()), self.bp, defender=defender, surprise=surprise)
        b = Battle(system, self.t, eng, {s: [f.id for f in here[s]] for s in SIDES}, started_by=started_by, last_news_t=self.t, fort_side=fort_side, fort_unit=fort_unit,
                   strengths0=(eng.strength(0), eng.strength(1)), zone=zone)
        self.battles[system] = b
        for s in SIDES:
            for f in here[s]:
                f.status = "engaged"
                f.route = [] if f.order.kind not in ("withdraw",) else f.route
        st.last_fight_t = self.t
        names = {s: ", ".join(f.name for f in here[s]) for s in SIDES}
        txt = {}
        for s in SIDES:
            foe = here[other(s)]
            if foe:
                est = self._estimate(s, foe[0], max(1, self.detects(s, foe[0]))) if len(foe) == 1 else f"about {sum(f.n for f in foe)} ships"
            else:
                est = f"the defences of {system}"
            txt[s] = f"Battle joined at {system}: {names[s] or 'our fleet'} against {est}."
        weight = 3 if (sum(len(here[s]) for s in SIDES) >= 3 or max(sum(f.n for f in here[s]) for s in SIDES) >= 10) else 2
        self.say("battle_start", system, txt, tuple(SIDES), weight, tuple(f.id for s in SIDES for f in here[s]))

    def _join(self, b: Battle, here: dict[str, list[Fleet]]) -> None:
        """A fleet that has come to a battle in progress is in it from now on: at once if it is where the fighting is, after the time it takes to cross the system
        if it is over the world (the fleet over the planet comes to the Gate when the Gate is attacked)."""
        respond_s = SYSTEMS.get(b.system, {}).get("crossing_s", 150) * 0.5
        for i, s in enumerate(SIDES):
            for f in here[s]:
                if f.id in b.fleets[s] or f.status == "engaged":
                    continue
                foe_here = any(g.side != s for g in self.fleets_at(b.system))
                if not (self._willing(f) and (foe_here or self.sees(s, b.system) >= 1)):
                    continue
                if f.zone != b.zone and f.status != "moving":
                    if f.respond_at <= 0.0:
                        f.respond_at = self.t + respond_s
                        self.say("responding", b.system, {s: f"{f.name} is coming to the fight at {b.system} (about {fmt_s(respond_s)} away)."}, (s,), 1, (f.id,))
                    if self.t < f.respond_at:
                        continue
                f.respond_at = 0.0
                for ship in f.ships:
                    b.eng.sides[i].append(self._unit(f, ship, i))
                b.fleets[s].append(f.id)
                f.status = "engaged"
                self.say("battle_join", b.system, {s: f"{f.name} has joined the battle at {b.system}."}, (s,), 1, (f.id,))

    def _battles(self, dt: float) -> None:
        for system, b in list(self.battles.items()):
            b.eng.step(dt)
            self._release(b)
            if self.t - b.last_news_t >= 150.0 and not b.eng.over:
                b.last_news_t = self.t
                self._battle_news(b, final=False)
            if b.eng.over or self.t - b.t0 > self.pace["battle_max_s"]:
                self._end_battle(b)

    def _battle_news(self, b: Battle, final: bool) -> None:
        e = b.eng
        txt = {}
        for i, s in enumerate(SIDES):
            mine = [u for u in e.sides[i] if u.fid != "fort"]
            lost = sum(1 for u in mine if not u.alive)
            foe_lost = sum(1 for u in e.sides[1 - i] if not u.alive and u.fid != "fort")
            txt[s] = (f"The battle at {b.system} goes on ({fmt_s(self.t - b.t0)} in): we have lost {lost} of {len(mine)} ships and the enemy about {foe_lost}; "
                      f"{sum(1 for u in mine if u.fighting)} of ours are still fighting.")
        self.say("battle_update", b.system, txt, tuple(SIDES), 1, tuple(f for s in SIDES for f in b.fleets[s]))

    def _units_of(self, b: Battle, fid: str) -> list[mb.Unit]:
        return [u for i in (0, 1) for u in b.eng.sides[i] if u.fid == fid]

    def _settle(self, b: Battle, f: Fleet, us: list[mb.Unit]) -> bool:
        """Write a fleet's part of the battle back into the fleet: hulls, wings, the ships that were lost (and what they were worth). False: nothing of it is left."""
        s = f.side
        keep: list[Ship] = []
        for u in us:
            _, ship = u.ref
            if not u.alive:
                b.lost_points[s] += CLASSES[ship.cls]["cost"] or 3.6
                b.lost_ships[s] += 1
                b.lost_names[s].append(f"{ship.name} ({ship.cls})")
                b.capital_lost = b.capital_lost or ship.cls in ("praetorian", "acheron", "aquila")
                continue
            ship.hull = max(0.02, u.hull_frac)
            ship.fighters, ship.bombers, ship.drones = int(round(u.f)), int(round(u.b)), int(round(u.d))
            keep.append(ship)
        f.ships = keep
        f.supply = max(0.0, f.supply - self.pace["supply_per_battle_s"] * (self.t - b.t0))
        f.respond_at = 0.0
        b.settled.add(f.id)
        if not keep:
            self._remove_fleet(f)
            return False
        return True

    def _release(self, b: Battle) -> None:
        """A fleet that broke off and has got out of reach leaves the battle now: it goes where its order says (or falls back), whatever the others are doing."""
        for s in SIDES:
            for fid in list(b.fleets[s]):
                f = self.fleets.get(fid)
                if f is None or fid in b.settled or fid not in b.eng.broke:
                    continue
                us = self._units_of(b, fid)
                if not all((not u.alive) or u.gone for u in us):
                    continue
                if self._settle(b, f, us):
                    f.morale = max(0.05, f.morale - 0.15)
                    f.status = "ready"
                    if f.order.kind in ("move", "withdraw", "recon", "refit") and f.route:
                        f.status, f.depart_at, f.untouchable_until = "moving", self.t + 2.0, self.t + 90.0
                    else:
                        self._retreat(f, b.system)
                    b.fled.append(f.id)

    def _end_battle(self, b: Battle) -> None:
        e = b.eng
        self.battles.pop(b.system, None)
        st = self.sys[b.system]
        st.last_fight_t = self.t
        held: dict[str, list[Fleet]] = {s: [] for s in SIDES}
        for i in (0, 1):
            for u in e.sides[i]:
                if u.fid == "fort":
                    st.fort_hp = max(0.0, u.hull_frac) if u.alive else 0.0
        for s in SIDES:
            for fid in list(b.fleets[s]):
                f = self.fleets.get(fid)
                if f is None or fid in b.settled:
                    continue
                if not self._settle(b, f, self._units_of(b, fid)):
                    continue
                if fid in e.broke:
                    f.morale = max(0.05, f.morale - 0.15)
                    f.status = "ready"
                    self._retreat(f, b.system)
                    b.fled.append(fid)
                else:
                    held[s].append(f)
        lost_points, lost_ships, lost_names = b.lost_points, b.lost_ships, b.lost_names
        for s in SIDES:
            self.score[s]["lost_points"] += lost_points[s]
            self.score[s]["ships_lost"] += lost_ships[s]
            self.score[other(s)]["killed_points"] += lost_points[s]
            self.score[other(s)]["ships_killed"] += lost_ships[s]
            self.will[s] = max(0.0, self.will[s] - 0.0040 * lost_points[s])
            self.will[other(s)] = min(1.0, self.will[other(s)] + 0.0015 * lost_points[s])
        # the Mandate's shipbreakers: wrecks on ground it holds come back as hulls
        m_ground = self.owner(b.system) == "mandate" or (held["mandate"] and not held["astra"])
        if m_ground:
            salv = self.pace["wreck_salvage"] * (lost_points["astra"] + lost_points["mandate"])
            nif = self.sys.get("Niflheim")
            if nif is not None and self.owner("Niflheim") == "mandate" and salv > 0:
                nif.progress += salv
        for s in SIDES:
            for f in held[s]:
                f.status = "ready"
                f.morale = min(1.0, f.morale + (0.08 if lost_points[other(s)] > lost_points[s] else -0.05))
        # the field: who holds it
        survivors = {s: bool(held[s]) for s in SIDES}
        winner = "astra" if survivors["astra"] and not survivors["mandate"] else "mandate" if survivors["mandate"] and not survivors["astra"] else ""
        fled_n = {s: sum(self.fleets[fid].n for fid in b.fled if fid in self.fleets and self.fleets[fid].side == s) for s in SIDES}
        txt = {}
        for s in SIDES:
            o = other(s)
            res = ("we hold the field" if winner == s else "the enemy holds the field" if winner == o else "both sides broke off")
            txt[s] = (f"The battle at {b.system} is over after {fmt_s(self.t - b.t0)}: {res}. We lost {lost_ships[s]} ships"
                      + (f" ({', '.join(lost_names[s][:6])}{'...' if len(lost_names[s]) > 6 else ''})" if lost_ships[s] else "")
                      + f"; the enemy lost about {lost_ships[o]}"
                      + (f"; {fled_n[s]} of ours broke off and are falling back" if fled_n[s] else "") + ".")
        weight = 3 if (b.capital_lost or lost_ships["astra"] + lost_ships["mandate"] >= 8 or self.value(b.system) >= 7) else 2
        self.say("battle_end", b.system, txt, tuple(SIDES), weight, tuple(f for s in SIDES for f in b.fleets[s]),
                 winner=winner, lost={s: lost_ships[s] for s in SIDES}, names=lost_names)
        self.dirty = True
        for s in SIDES:
            self.tracks[s] = {k: v for k, v in self.tracks[s].items() if k in self.fleets}

    def cut_battle(self, system: str) -> None:
        """The Aquila has come to a system where the map was fighting a battle: the real simulation takes it over. The fleets go on as they stand (what the battle has done
        to them so far is in their hulls and their losses, and counts in the scores and the people's will as it would have at the end), and the glue sends their ships to
        the game."""
        b = self.battles.pop(system, None)
        if b is None:
            return
        for s in SIDES:
            for fid in list(b.fleets[s]):
                f = self.fleets.get(fid)
                if f is None or fid in b.settled:
                    continue
                if self._settle(b, f, self._units_of(b, fid)):
                    f.status = "ready"
                    f.route = []
        for s in SIDES:
            self.score[s]["lost_points"] += b.lost_points[s]
            self.score[s]["ships_lost"] += b.lost_ships[s]
            self.score[other(s)]["killed_points"] += b.lost_points[s]
            self.score[other(s)]["ships_killed"] += b.lost_ships[s]
            self.will[s] = max(0.0, self.will[s] - 0.0040 * b.lost_points[s])
            self.will[other(s)] = min(1.0, self.will[other(s)] + 0.0015 * b.lost_points[s])
        self.dirty = True

    def _retreat(self, f: Fleet, from_system: str) -> None:
        """A fleet that broke off falls back to the nearest depot of its side away from the enemy (or where it came from)."""
        avoid = {from_system} | self.hostile_systems(f.side)
        dest = self.nearest_depot(f.side, from_system, avoid=avoid) or (f.origin if f.origin and f.origin != from_system else "") or self.nearest_depot(f.side, from_system) or from_system
        f.order = Order("withdraw", dest, "cautious", False, "auto", f"broke off at {from_system}", self.t)
        f.pending = None
        p = self.path(from_system, dest, f.side) or []
        f.route = p
        f.depart_at = self.t + 2.0
        f.untouchable_until = self.t + 90.0                              # (it ran: out of contact for a while)
        f.status = "moving" if p else "ready"
        if not p:
            self._order_reached(f)

    def _remove_fleet(self, f: Fleet) -> None:
        self.fleets.pop(f.id, None)
        for s in SIDES:
            self.tracks[s].pop(f.id, None)
        for g in self.fleets.values():
            if g.order.kind in ("reinforce", "escort") and g.order.target == f.id:
                g.order = Order("hold", g.where, g.order.stance, False, "auto", f"{f.name} is gone", self.t)
        self.dirty = True

    # ------------------------------------------------------------------------------------------- sieges and claims
    def siege_time(self, system: str) -> float:
        d = SYSTEMS.get(system, {})
        return float(d.get("siege_s") or self.pace["siege_base_s"] * (0.5 + self.value(system) / 10.0)) * self.pace.get("siege_scale", 1.0)

    def _sieges(self, dt: float) -> None:
        for name, st in self.sys.items():
            if self.neutral(name) or (name == self.real_system and self.real_fight):
                continue
            owner = self.owner(name)
            fl = {s: [f for f in self.fleets_at(name, s) if f.status not in ("scripted", "engaged", "real")] for s in SIDES}
            if name in self.battles:
                st.siege_s = max(0.0, st.siege_s - dt)
                continue
            if owner not in SIDES:
                st.blockaded_by = ""
                present = [s for s in SIDES if any(f.order.kind in ("hold", "defend", "assault", "blockade", "reinforce", "escort") for f in fl[s])]
                if len(present) == 1 and not fl[other(present[0])]:
                    st.claim_by = present[0]
                    st.claim_s += dt
                    if st.claim_s >= self.pace["claim_s"]:
                        self._take(name, present[0], claim=True)
                else:
                    st.claim_by, st.claim_s = "", max(0.0, st.claim_s - dt)
                continue
            foe = other(owner)
            attackers = [f for f in fl[foe] if f.order.kind in ("assault", "blockade", "raid") and f.zone == "world"]
            defenders = fl[owner]
            fort_up = st.fort_level > 0 and st.fort_hp > 0.12
            if attackers and not defenders and not fort_up:
                st.blockaded_by = foe
                if any(f.order.kind == "assault" for f in attackers):
                    if st.siege_by != foe:
                        st.siege_by, st.siege_s = foe, 0.0
                        self.say("siege", name, {owner: f"{name} is under siege: enemy ships hold the system and nothing of ours stands between them and the world.",
                                                 foe: f"{name} is ours to take: its defenders are beaten and the siege has begun."}, SIDES, 3, tuple(f.id for f in attackers))
                    st.siege_s += dt
                    for f in attackers:
                        f.status = "besieging"
                    if st.siege_s >= self.siege_time(name):
                        self._take(name, foe)
                elif any(f.order.kind == "raid" for f in attackers):
                    st.progress = max(0.0, st.progress - 0.8 * dt / 60.0)                 # raiders sack the yard's work
                    st.raid_s += dt
                    if st.raid_s >= 150.0 and st.post.get(owner):
                        st.post[owner] = False
                        self.say("post_lost", name, {owner: f"The listening post at {name} has gone silent: raiders are in the system.",
                                                     foe: f"The raiders have put the listening post at {name} out."}, SIDES, 2, tuple(f.id for f in attackers))
            else:
                if st.siege_by and st.siege_s > 0:
                    st.siege_s = max(0.0, st.siege_s - 2.0 * dt)
                    if st.siege_s == 0.0:
                        st.siege_by = ""
                        self.say("siege_broken", name, f"The siege of {name} is lifted.", SIDES, 2)
                st.blockaded_by = foe if (attackers and any(f.order.kind in ("blockade", "assault") for f in attackers)) else ""

    def _take(self, name: str, side: str, claim: bool = False) -> None:
        st = self.sys[name]
        old = self.owner(name)
        self.war.set_owner(name, side, f"{'claimed' if claim else 'taken'} by {SIDE_WORD[side]} fleets")
        st.siege_s, st.siege_by, st.claim_s, st.claim_by, st.blockaded_by = 0.0, "", 0.0, "", ""
        st.post[old] = False
        st.post[side] = True
        st.fort_hp = 0.4 if not claim else max(st.fort_hp, 0.0)
        st.progress = 0.0
        v = self.value(name)
        if old in SIDES:
            self.score[old]["systems_lost"] += 1
            self.will[old] = max(0.0, self.will[old] - 0.020 * v)
        self.score[side]["systems_taken"] += 1
        self.will[side] = min(1.0, self.will[side] + 0.008 * v)
        verb = "claimed" if claim else "taken"
        txt = {side: f"{name} is {verb}: it is ours.", other(side): f"{name} is {verb} by {SIDE_WORD[side]} forces: it is lost to us."}
        self.say("system_taken", name, txt, SIDES, 3 if v >= 4 else 2, (), owner=side, was=old)
        if old in SIDES and CAPITALS.get(old) == name:
            self._end_war(side, "capital", f"{name}, the capital of {SIDE_WORD[old]}, has fallen")
        self._sync_threat()

    # ------------------------------------------------------------------------------------------- upkeep: repair, supply, yards
    def _depot_ok(self, f: Fleet) -> bool:
        s = f.where
        if not s or f.status in ("engaged", "scripted"):
            return False
        d = SYSTEMS.get(s)
        st = self.sys.get(s)
        return bool(d and d["depot"] and self.owner(s) == f.side and s not in self.battles and st is not None and not (st.blockaded_by and st.blockaded_by != f.side) and not st.siege_by)

    def _upkeep(self, dt: float) -> None:
        p = self.pace
        for f in list(self.fleets.values()):
            if f.status == "scripted":
                continue
            if self._depot_ok(f):
                for ship in f.ships:
                    ship.hull = min(1.0, ship.hull + p["repair_per_s"] * dt)
                    if f.supply > 0.4 and (ship.fighters, ship.bombers, ship.drones) != ship.wmax and self.rng.random() < dt / 12.0:
                        w = [ship.fighters, ship.bombers, ship.drones]
                        for i in range(3):
                            if w[i] < ship.wmax[i]:
                                w[i] += 1
                                break
                        ship.fighters, ship.bombers, ship.drones = w
                f.supply = min(1.0, f.supply + p["resupply_per_s"] * dt)
            elif f.where and f.status != "engaged":
                f.supply = max(0.0, f.supply - p["supply_idle_per_s"] * dt)
            if f.status != "engaged":
                f.morale = min(0.85, f.morale + p["morale_recover_per_s"] * dt)
            o = f.order
            if o.kind == "refit" and f.where and self._depot_ok(f) and f.hull > 0.97 and f.supply > 0.92 and f.status != "moving":
                f.order = Order("hold", f.where, "steady", False, "auto", "repaired and resupplied", self.t)
                self.say("fleet_ready", f.where, {f.side: f"{f.name} is repaired and resupplied at {f.where} and ready for orders."}, (f.side,), 1, (f.id,))
            elif (f.where and f.supply < 0.12 and f.status in ("ready", "moving", "besieging") and o.kind not in ("withdraw", "refit") and not self._depot_ok(f)):
                dest = self.nearest_depot(f.side, f.where, avoid=self.hostile_systems(f.side)) or self.nearest_depot(f.side, f.where)
                if dest:
                    f.order = Order("withdraw", dest, "cautious", False, "auto", "out of supply", self.t)
                    f.route = self.path(f.where, dest, f.side) or []
                    f.depart_at = self.t + 10.0
                    f.status = "moving" if f.route else "ready"
                    self.say("supply", f.where, {f.side: f"{f.name} is out of supply at {f.where} and is falling back on {dest}."}, (f.side,), 2, (f.id,))
        for name, st in self.sys.items():
            owner = self.owner(name)
            foes = [f for f in self.fleets_at(name) if f.side != owner and f.status != "scripted"]
            if owner in SIDES and st.fort_hp < 1.0 and not foes:
                st.fort_hp = min(1.0, st.fort_hp + p["fort_regen_per_s"] * dt)
            if owner in SIDES and not st.post.get(owner) and not foes and self.fleets_at(name, owner) and self.t - st.last_fight_t > 240.0:
                st.restore_s += dt
                if st.restore_s >= 240.0:
                    st.post[owner], st.restore_s = True, 0.0
                    self.say("post_restored", name, {owner: f"The listening post at {name} is working again."}, (owner,), 1)
            if foes == [] and st.raid_s:
                st.raid_s = max(0.0, st.raid_s - dt)
            if st.yard > 0 and owner in SIDES and name not in self.battles and st.blockaded_by != other(owner) and not st.siege_by:           # (a scout in the system stops no yard: a blockade does)
                cls = st.build or YARD_DEFAULT.get(name) or ""
                if not cls or not self.buildable(owner, cls):
                    cls = {"astra": "vigilant", "mandate": "styx"}[owner] if not self.free_classes else "styx"
                st.progress += st.yard * dt / 3600.0
                if st.progress >= CLASSES[cls]["cost"]:
                    st.progress -= CLASSES[cls]["cost"]
                    self._commission(owner, name, cls)

    def _commission(self, side: str, system: str, cls: str) -> Ship:
        """A yard has finished a ship: it joins the garrison of the system (a fleet of its own is made if there is none)."""
        w = CLASSES[cls]["wing"]
        ship = Ship(cls, self.ship_name(cls), 1.0, "", w[0] if cls in CARRIERS else 0, w[1] if cls in CARRIERS else 0, 0, "", (w[0], w[1], 0) if cls in CARRIERS else (0, 0, 0))
        garrison = next((f for f in self.fleets_at(system, side) if f.status == "ready" and f.name.endswith("Reserve")), None)
        if garrison is None:
            garrison = next((f for f in self.fleets_at(system, side) if f.status == "ready" and f.order.kind in ("defend", "hold", "refit") and f.n < 12 and not f.in_gate), None)
        if garrison is None:
            fid = self.new_fleet_id(side)
            garrison = Fleet(fid, side, f"{system} Reserve", [], system, 1.0, 0.8, Order("defend", system, "steady", False, "default", "the yard's reserve guards the system", self.t,
                                                                                           None, "world"), commander=self.person_for(side), status="ready", arrived_t=self.t, origin=system,
                             zone="world")
            self.fleets[fid] = garrison
        garrison.ships.append(ship)
        garrison.groups = []
        self.say("production", system, {side: f"The yard at {system} has commissioned the {cls} {ship.name}; she joins {garrison.name}."}, (side,), 0, (garrison.id,))
        return ship

    # ------------------------------------------------------------------------------------------- intelligence
    def _noisy(self, side: str, f: Fleet, lvl: int) -> tuple[int, dict[str, int] | None]:
        r = random.Random(f"{side}|{f.id}|{int(self.t // 300)}|{self.seed}")
        if lvl <= 1:
            return max(1, round(f.n * math.exp(r.gauss(0.0, 0.22)))), None
        if lvl == 2:
            est = {c: max(0, k + r.choice((-1, 0, 0, 1))) for c, k in f.classes.items()}
            est = {c: k for c, k in est.items() if k} or dict(f.classes)
            return sum(est.values()), est
        return f.n, dict(f.classes)

    def _intel(self) -> None:
        for side in SIDES:
            tr = self.tracks[side]
            for f in self.fleets.values():
                if f.side == side or f.status == "scripted" or not f.where:
                    continue
                lvl = self.detects(side, f)
                if lvl <= 0:
                    continue
                old = tr.get(f.id)
                if old is not None and old.system == f.where and old.level >= lvl and self.t - old.seen_t < 20.0:
                    old.seen_t = self.t
                    continue
                n, cls = self._noisy(side, f, lvl)
                tr[f.id] = Track(f.id, f.where, self.t, lvl, n, cls, round(f.hull, 2) if lvl >= 3 else None, old.moving_to if old and old.system == f.where else "")
            for k in [k for k, v in tr.items() if self.t - v.seen_t > 1500.0]:
                del tr[k]
            # where was the Aquila last seen (the Mandate has no eyes on her unless it has them where she is)
            if side == "mandate" and self.aquila["where"] and not self.aquila["lane"] and self.sees("mandate", self.aquila["where"]) >= 2:
                self.aquila_seen = (self.aquila["where"], self.t)

    aquila_seen: tuple[str, float] = ("", 0.0)

    # ------------------------------------------------------------------------------------------- the courses of orders
    def _courses(self, dt: float) -> None:
        for f in list(self.fleets.values()):
            if f.status in ("scripted", "engaged"):
                continue
            o = f.order
            if o.kind in ("assault", "blockade", "raid") and f.where == o.target and f.status in ("ready", "besieging") and self.owner(o.target) == f.side:
                f.order = Order("defend", o.target, o.stance if o.stance != "bold" else "steady", False, "auto", f"{o.target} is ours: hold it", self.t, None, "world")
                f.status = "ready"
                self._place(f)
                continue
            if (o.kind in ("assault", "raid") and f.zone == "gate" and f.where == o.target and f.status == "ready" and f.where not in self.battles and not f.route
                    and not [g for g in self.fleets_at(f.where) if g.side != f.side and g.zone == "gate" and g.status not in ("scripted", "real")]):
                st = self.sys[f.where]
                if not (self.owner(f.where) == other(f.side) and st.fort_level > 0 and st.fort_hp > 0.12):
                    f.zone = "world"
                    f.untouchable_until = self.t + SYSTEMS.get(f.where, {}).get("crossing_s", 150)       # (crossing from the Gate to the world: out of reach of both)
                    continue
            if (f.where and not f.in_gate and f.status == "ready" and not f.route and o.target in self.sys and o.target != f.where
                    and o.kind in ("move", "assault", "raid", "defend", "blockade", "recon", "withdraw", "refit", "hold")):
                p = self.path(f.where, o.target, f.side)          # (a fleet that was stopped on its way — by a battle — takes its way up again)
                if p:
                    f.route, f.depart_at, f.status = p, self.t + self.pace["exit_form_s"], "moving"
            if o.kind in ("reinforce", "escort"):
                tf = self.fleets.get(o.target)
                if tf is None:
                    f.order = Order("hold", f.where, o.stance, False, "auto", "the fleet it was to join is gone", self.t)
                    continue
                dest = tf.where or (tf.route[-1] if tf.route else "")
                if f.where and dest and f.where != dest and not f.in_gate and (not f.route or f.route[-1] != dest):
                    f.route = self.path(f.where, dest, f.side) or []
                    f.depart_at = self.t + self.pace["exit_form_s"]
                    f.status = "moving" if f.route else f.status
                elif f.where and f.where == tf.where and tf.status not in ("engaged", "scripted") and o.kind == "reinforce" and not f.route:
                    self.say("fleet_formed", f.where, {f.side: f"{f.name} joined {tf.name} at {f.where}."}, (f.side,), 1, (tf.id,))
                    self._absorb(tf, f)
                    continue
            if o.until is not None and self.t >= o.until and o.kind in ("raid", "recon", "hold", "defend", "blockade", "assault"):
                home = f.origin if f.origin and f.origin != f.where else (self.nearest_depot(f.side, f.where) or f.where)
                f.order = Order("withdraw", home, "cautious", False, "auto", f"{o.kind} finished", self.t)
                f.route = self.path(f.where, home, f.side) if f.where else f.route
                f.route = f.route or []
                f.depart_at = self.t + self.pace["exit_form_s"]
                f.status = "moving" if f.route else "ready"
                if not f.route and f.where:
                    self._order_reached(f)

    # ------------------------------------------------------------------------------------------- the war's course
    def _sync_threat(self) -> None:
        for name in self.sys:
            owner = self.owner(name)
            here = [f for f in self.fleets.values() if (f.where == name or (f.in_gate and f.route and f.route[0] == name)) and f.status != "real"]
            foes = [f for f in here if f.side != owner] if owner in SIDES else [f for f in here]
            st = self.sys[name]
            if name in self.battles or st.siege_by:
                v = 3
            elif foes and any(f.where == name for f in foes):
                v = 2
            elif foes or any(f.side != owner and f.where in self.links(name) and f.order.target == name for f in self.fleets.values() if owner in SIDES):
                v = 1
            else:
                v = 0
            if owner not in SIDES and not foes:
                v = self.war.systems[name].get("threat", 0) if self.t == 0 else 0
            self.war.set_threat(name, v)

    def _will_course(self, dt: float) -> None:
        """The war wears a people down, and its homeland holds it up: a side that holds its worlds loses will slowly, one that is losing them loses it fast."""
        total = sum(self.value(n) for n in self.sys if not self.neutral(n)) or 1.0
        for s in SIDES:
            held = sum(self.value(n) for n in self.sys if self.owner(n) == s)
            home = self.pace["will_home_per_s"] * (held / total) * 2.0
            self.will[s] = max(0.0, min(1.0, self.will[s] - self.pace["will_decay_per_s"] * dt + home * dt))

    def _victory(self) -> None:
        if self.over:
            return
        for s in SIDES:
            if self.will[s] <= 0.04:
                self._end_war(other(s), "collapse", f"{SIDE_WORD[s]}'s will to fight is gone")
                return
        if self.truce and self.t >= self.truce["until"]:
            self.truce = {}
            self.say("truce_over", "", "The truce has run out: the war goes on.", SIDES, 3)

    def _end_war(self, winner: str, how: str, why: str) -> None:
        if self.over:
            return
        self.over = {"winner": winner, "how": how, "why": why, "t": self.t}
        txt = {}
        for s in SIDES:
            txt[s] = (f"THE WAR IS OVER: {why}. " + ("We have won." if winner == s else "We have lost." if winner and winner != s else "Both sides have laid down their arms."))
        self.say("war_over", "", txt, SIDES, 3, winner=winner, how=how)
        self.dirty = True

    def propose(self, side: str, kind: str, terms: str = "") -> tuple[bool, str]:
        """A side offers a truce (the fleets stop where they are for half an hour) or peace (an armistice that ends the war); if the other has offered the same,
        within twenty minutes, it is agreed. Nothing here judges whether it should be: that is for the admirals, and the people at home."""
        if self.over:
            return False, "the war is over"
        kind = kind if kind in ("truce", "peace") else "truce"
        self.proposals[side] = {"kind": kind, "t": self.t, "terms": terms[:240]}
        theirs = self.proposals.get(other(side))
        if theirs and theirs["kind"] == kind and self.t - theirs["t"] < 1200.0:
            self.proposals.clear()
            if kind == "peace":
                self._end_war("", "armistice", "both sides have agreed an armistice")
                return True, "agreed: an armistice ends the war"
            self.truce = {"until": self.t + 1800.0, "t": self.t}
            for b in list(self.battles.values()):
                for s in SIDES:
                    for fid in b.fleets[s]:
                        b.eng.break_off(fid)
            self.say("truce", "", "A truce is agreed: the fleets hold where they are for half an hour.", SIDES, 3)
            return True, "agreed: a truce for half an hour"
        self.say("proposal", "", {other(side): f"The {SIDE_WORD[side]} high command offers a {kind}" + (f": {terms}" if terms else "") + ".",
                                  side: f"Your offer of a {kind} has gone to the other side."}, SIDES, 2)
        return True, f"your offer of a {kind} stands for twenty minutes; the other side has not answered yet"

    def accept(self, side: str) -> tuple[bool, str]:
        theirs = self.proposals.get(other(side))
        if not theirs or self.t - theirs["t"] > 1200.0:
            return False, "the other side has no offer standing"
        return self.propose(side, theirs["kind"], "accepted")

    # ------------------------------------------------------------------------------------------- the Aquila
    def aquila_lane(self, dest: str) -> None:
        """The Aquila is in a Gate's lane towards `dest`: she is in no system for the war's rules, and what the real simulation was playing is the map's again."""
        if self.aquila["lane"] == dest:
            return
        self.release_real()
        self.aquila.update(lane=dest, since=self.t)
        self.dirty = True

    def aquila_arrived(self, system: str) -> None:
        """The Aquila is through the Gate into `system`: the real simulation is that system's from now on (the fleets there are the glue's to bring in)."""
        self.aquila.update(where=system, lane="", since=self.t)
        self.real_system, self.real_fight = system, False
        self.real_tally = {s: {"lost": 0, "names": [], "points": 0.0} for s in SIDES}
        self.dirty = True

    def _on_arrival(self, system: str) -> None:
        if system in self.sys and (self.aquila["where"] != system or self.aquila["lane"]):
            self.aquila_arrived(system)

    # ------------------------------------------------------------------------------------------- the real simulation's side of the war
    def real_adopt(self, f: Fleet, system: str) -> None:
        """A fleet is in the real simulation now (the game brought it in, or the glue sent its ships): the March leaves it alone, and reads what becomes of it."""
        if f.status == "scripted":
            self.release_script(f.id, system)
        f.where, f.status, f.route, f.pending, f.scripted, f.arrived_t = system, "real", [], None, "", self.t
        self.dirty = True

    def real_hull(self, ship: Ship, frac: float) -> None:
        ship.hull = max(0.02, min(1.0, float(frac)))

    def real_lost(self, f: Fleet, ship: Ship, how: str = "destroyed") -> None:
        """A ship of a real fleet is gone from the real simulation: destroyed (it is lost, it counts in the war's scores and wears the people's will, as in a battle of
        the map) or jumped out of the system (it lives: it goes on as a small fleet that falls back like any that broke off)."""
        if ship not in f.ships:
            return
        s = f.side
        f.ships.remove(ship)
        ship.cid = ""                                                       # (it is not in the real simulation any more, whatever became of it)
        if how == "destroyed":
            pts = CLASSES[ship.cls]["cost"] or 3.6
            self.score[s]["lost_points"] += pts
            self.score[s]["ships_lost"] += 1
            self.score[other(s)]["killed_points"] += pts
            self.score[other(s)]["ships_killed"] += 1
            self.will[s] = max(0.0, self.will[s] - 0.0040 * pts)
            self.will[other(s)] = min(1.0, self.will[other(s)] + 0.0015 * pts)
            tally = self.real_tally[s]
            tally["lost"] += 1
            tally["points"] += pts
            tally["names"].append(f"{ship.name} ({ship.cls})")
            if ship.cls in ("praetorian", "acheron", "aquila"):
                tally["capital"] = True
        else:
            where = f.where or self.real_system
            mine = [g for g in self.fleets_at(where, s) if g.note == f"{STRAGGLERS}{f.id}" and g.id != f.id and g.depart_at > self.t]
            if mine:
                mine[0].ships.append(ship)
            else:
                nf = Fleet(self.new_fleet_id(s), s, f"{f.name} (survivors)", [ship], where, f.supply, max(0.05, f.morale - 0.15), Order("hold", where, "cautious", False, "auto", "", self.t),
                           commander=dict(f.commander), status="ready", arrived_t=self.t, origin=f.origin, note=f"{STRAGGLERS}{f.id}")
                self.fleets[nf.id] = nf
                self._retreat(nf, where)
                nf.depart_at = self.t + 20.0                                 # (the others that jump out in the next moments join it)
        if not f.ships:
            self._remove_fleet(f)
        self.dirty = True

    def real_over(self, system: str, result: str = "") -> int:
        """The real fight is over: the war is told (what each side lost there, who holds the field) and the tally starts again. Returns how much it weighs (3: a major
        battle)."""
        tally, self.real_tally = self.real_tally, {s: {"lost": 0, "names": [], "points": 0.0} for s in SIDES}
        left = {s: sum(f.n for f in self.fleets_at(system, s) if f.status == "real") for s in SIDES}
        winner = "astra" if left["astra"] and not left["mandate"] else "mandate" if left["mandate"] and not left["astra"] else ""
        txt = {}
        for s in SIDES:
            o = other(s)
            res = result if (result and s == "astra") else ("we hold the field" if winner == s else "the enemy holds the field" if winner == o else "the fighting is over")
            names = tally[s]["names"]
            txt[s] = (f"The battle at {system} is over after {fmt_s(self.t - self.real_t0)}: {res}. We lost {tally[s]['lost']} ships"
                      + (f" ({', '.join(names[:6])}{'...' if len(names) > 6 else ''})" if names else "") + f"; the enemy lost about {tally[o]['lost']}.")
        # a major battle (it may close a chapter of the story) is one that was fought: many ships lost, or capital ships with others, or a costly fight for a system
        # that matters; a raid that turns away after a cruiser is lost is not one
        lost = tally["astra"]["lost"] + tally["mandate"]["lost"]
        capital = bool(tally["astra"].get("capital") or tally["mandate"].get("capital"))
        weight = 3 if (lost >= 8 or (capital and lost >= 3) or (self.value(system) >= 7 and lost >= 5)) else 2
        self.say("battle_end", system, txt, SIDES, weight, (), winner=winner, lost={s: tally[s]["lost"] for s in SIDES}, names={s: tally[s]["names"] for s in SIDES})
        self.real_fight = False
        return weight

    def release_real(self) -> None:
        """The Aquila leaves (or the real simulation is gone): the fleets it played are the map's again, where they stand, with the hulls they have."""
        for f in list(self.fleets.values()):
            if f.status == "real":
                f.status = "ready"
                f.where = f.where or self.real_system
                f.untouchable_until = self.t
                for ship in f.ships:
                    ship.cid = ""                                          # (they are not in the real simulation any more: its sky is cleared or is no longer the Aquila's)
                if f.order.kind in ("move", "withdraw", "refit") and f.order.target != f.where:
                    f.pending = None
        self.real_system, self.real_fight = "", False
        self.dirty = True

    # ------------------------------------------------------------------------------------------- the rest of the world's course
    def _more(self, dt: float) -> None:
        self._will_course(dt)
        self._victory()

    # ------------------------------------------------------------------------------------------- what a side knows
    @property
    def day(self) -> int:
        return 1 + int(self.t // DAY_S)

    def clock(self) -> str:
        h, m = divmod(int(self.t) // 60, 60)
        return f"T+{h}h{m:02d} (day {self.day})"

    def track_power(self, tr: Track) -> float:
        """What a track is worth in the units of `Fleet.power`, from what the viewer knows of it."""
        if tr.classes:
            return sum(CLASSES[c]["worth"] * k for c, k in tr.classes.items()) * (tr.hull if tr.hull else 0.9)
        return tr.n * 1.1 * 0.9

    def view(self, side: str, since: int = 0) -> "SideView":
        own = [f for f in self.fleets.values() if f.side == side]
        tracks = dict(self.tracks[side])
        return SideView(self, side, own, tracks, self.news(side, since))

    def known_threat(self, side: str, system: str) -> int:
        """0-3 as `side` would chart it: from the tracks it holds (an enemy fleet seen there lately), its own fleets there and the battle it can see."""
        owner = self.owner(system)
        v = 0
        for tr in self.tracks[side].values():
            if tr.system == system and self.t - tr.seen_t < 900.0:
                v = max(v, 3 if (system in self.battles or self.sys[system].siege_by) else 2)
        if system in self.battles and any(self.fleets[f].side == side for s in SIDES for f in self.battles[system].fleets[s] if f in self.fleets):
            v = 3
        for tr in self.tracks[side].values():
            if v < 1 and tr.moving_to == system and self.t - tr.seen_t < 600.0:
                v = 1
        if v == 0 and self.sys[system].siege_by and owner == side:
            v = 3
        return v

    def holo(self, side: str) -> dict[str, Any]:
        """What the holo table can draw for `side`: its own fleets, the enemy's tracks (older and vaguer), the battles it knows, the war's wills. No truth the
        side does not hold (docs/GUERRA.md §10: the bridge's data)."""
        fleets = []
        for f in self.fleets.values():
            if f.side != side or f.status == "scripted":
                continue
            fleets.append(self._fleet_row(f, own=True))
        for tr in self.tracks[side].values():
            f = self.fleets.get(tr.fid)
            if f is None:
                continue
            eta = (round(max(0.0, tr.arrive_t - self.t)) if tr.arrive_t else round(max(0.0, tr.seen_t + self.pace["hop_base_s"] + self.pace["hop_per_ship_s"] * tr.n - self.t))) \
                if tr.moving_to else None
            fleets.append({"id": tr.fid, "side": f.side, "name": f"enemy force {tr.fid}", "system": tr.system, "to": tr.moving_to, "next": tr.moving_to, "eta_s": eta, "ships": tr.n,
                           "classes": tr.classes or {}, "strength": round(self.track_power(tr), 1), "order": "", "state": "tracked", "known": False,
                           "age_s": round(self.t - tr.seen_t), "level": tr.level})
        battles = [{"system": b.system, "age_s": round(self.t - b.t0)} for b in self.battles.values() if self.known_threat(side, b.system) >= 2 or self.sees(side, b.system) >= 1]
        return {"fleets": fleets, "battles": battles, "will": {s: round(self.will[s], 2) for s in SIDES} if side == "astra" else {side: round(self.will[side], 2)},
                "systems": {n: {"threat": self.known_threat(side, n), "siege": bool(st.siege_by), "post": bool(st.post.get(side))} for n, st in self.sys.items()}, "t": round(self.t, 1)}

    def _fleet_row(self, f: Fleet, own: bool) -> dict[str, Any]:
        eta = round(max(0.0, f.arrive_at - self.t)) if f.in_gate else None
        to = f.route[-1] if f.route else ""
        nxt = f.route[0] if (f.in_gate and f.route) else ""             # the system it comes out in (eta_s is to there; `to` may lie hops beyond)
        return {"id": f.id, "side": f.side, "name": f.name, "system": f.where or f.hop_from, "to": to, "next": nxt, "eta_s": eta, "ships": f.n, "classes": f.classes,
                "strength": round(f.power, 1), "order": f"{f.order.kind} {f.order.target}".strip(), "state": f.status, "known": True, "hull": round(f.hull, 2),
                "supply": round(f.supply, 2), "morale": round(f.morale, 2), "commander": f.commander.get("name") or f.commander.get("key", "")}

    # ------------------------------------------------------------------------------------------- the pictures (text for the minds and the bridge)
    def will_word(self, w: float) -> str:
        return "firm" if w >= 0.65 else "steady" if w >= 0.45 else "wavering" if w >= 0.25 else "failing"

    def picture(self, side: str, since: int = 0, compact: bool = False) -> str:
        """The March as `side`'s high command reads it: its own fleets and yards exactly, the enemy's as its eyes have found them (with their age), the war's
        news since its last look, its plan. The fog of war is the rule: nothing here is a fact the side could not have."""
        v = self.view(side, since)
        me, foe = SIDE_WORD[side], SIDE_WORD[other(side)]
        out = [f"THE AURELIA MARCH, {self.clock()}. You hold the {me} command. Your will to fight is {self.will[side]:.2f} ({self.will_word(self.will[side])}); "
               f"{foe}'s, by your intelligence, looks {self.will_word(self.will[other(side)] + self.rng_guess(side))}."]
        if self.over:
            out.append(f"THE WAR IS OVER: {self.over['why']}.")
        if self.truce:
            out.append(f"A TRUCE is in force for {fmt_s(max(0.0, self.truce['until'] - self.t))}: the fleets hold where they are.")
        offer = self.proposals.get(other(side))
        if offer and self.t - offer["t"] < 1200.0:
            out.append(f"{foe} has offered a {offer['kind']} {fmt_s(self.t - offer['t'])} ago" + (f": {offer['terms']}" if offer.get("terms") else "") + " (you may accept).")
        mine = self.proposals.get(side)
        if mine and self.t - mine["t"] < 1200.0:
            out.append(f"Your offer of a {mine['kind']} stands ({fmt_s(self.t - mine['t'])} old).")
        home = self.home_orders.get(side)
        if home and home["until"] > self.t:
            out.append(f"ORDERS FROM HOME (the government, for the next {fmt_s(home['until'] - self.t)}): {home['text']}")
        if side == "astra" and self.aquila_task and self.t - self.aquila_task["t"] < 3600.0:
            out.append(f"FLEET'S STANDING ORDER TO THE AQUILA ({fmt_s(self.t - self.aquila_task['t'])} ago): to {self.aquila_task['system']}: {self.aquila_task['mission']}")
        if self.tender_free_at.get(side, 0.0) > self.t:
            out.append(f"Your supply tender is busy for {fmt_s(self.tender_free_at[side] - self.t)}.")
        out.append("YOUR PLAN: " + (self.plans[side] or "(you have not written one: set_plan)") + (f" (written {fmt_s(self.t - self.plan_t[side])} ago)" if self.plans[side] else ""))
        out.append("SYSTEMS")
        for name in SYSTEM_ORDER:
            if name not in self.sys:
                continue
            out.append(self._system_line(side, name, v))
        out.append("YOUR FLEETS")
        for f in sorted(v.own, key=lambda x: x.id):
            out.append("- " + self._fleet_line(f))
        if not v.own:
            out.append("- (none)")
        out.append("ENEMY, AS YOUR EYES HAVE FOUND THEM (an estimate, with its age: it may have moved)")
        tracks = sorted(v.tracks.values(), key=lambda t: -self.track_power(t))
        for tr in tracks:
            cls = f" ({composition(tr.classes)})" if tr.classes else ""
            hull = f", hull {int(100 * tr.hull)}%" if tr.hull is not None else ""
            mv = f", seen leaving for {tr.moving_to}" if tr.moving_to else ""
            out.append(f"- {tr.fid}: about {tr.n} ships{cls}{hull} at {tr.system}, seen {fmt_s(self.t - tr.seen_t)} ago{mv}")
        if not tracks:
            out.append("- (nothing on your plot)")
        bl = [b for b in self.battles.values() if self.sees(side, b.system) >= 1 or any(self.fleets[f].side == side for s in SIDES for f in b.fleets[s] if f in self.fleets)]
        fights = []
        if self.real_fight and self.real_system:
            fights.append(f"- {self.real_system}: the Aquila's fight, {fmt_s(self.t - self.real_t0)} in, played ship by ship with the Captain; so far we have lost "
                          f"{self.real_tally[side]['lost']} ships and the enemy about {self.real_tally[other(side)]['lost']}")
        for b in bl:
            e = b.eng
            mine = SIDES.index(side)
            fights.append(f"- {b.system}: {fmt_s(self.t - b.t0)} in; yours: {sum(1 for u in e.sides[mine] if u.fighting and u.fid != 'fort')} ships fighting, {sum(1 for u in e.sides[mine] if not u.alive and u.fid != 'fort')} lost; "
                          f"the enemy's: about {sum(1 for u in e.sides[1 - mine] if u.fighting and u.fid != 'fort')} fighting")
        if fights:
            out.append("BATTLES UNDER WAY")
            out.extend(fights)
        if side == "astra":
            out.append("THE AQUILA: " + (f"in the Gate's lane to {self.aquila['lane']}" if self.aquila["lane"] else f"at {self.aquila['where']}") + (f" (since {fmt_s(self.t - self.aquila['since'])})" if self.aquila["since"] else "")
                       + (f"; {self.aquila_gate_km:.0f} km from the Janus Gate there (a force that comes through needs minutes to reach her)" if (self.aquila_gate_km and self.aquila_gate_km >= 20.0 and self.real_system and not self.aquila["lane"]) else ""))
        else:
            if self.aquila_seen[0]:
                out.append(f"THE AQUILA (the ASTRA carrier cruiser, the Captain's ship): last seen at {self.aquila_seen[0]}, {fmt_s(self.t - self.aquila_seen[1])} ago.")
        if v.news:
            out.append("NEWS SINCE YOUR LAST LOOK (what has reached you, oldest first)")
            for e in v.news[-14:]:
                out.append(f"- {fmt_s(max(0, self.t - e.t))} ago · {e.system + ': ' if e.system else ''}{e.text[side]}")
        return "\n".join(out)

    def rng_guess(self, side: str) -> float:
        """How far off an intelligence estimate of the enemy's will is (it is a guess: a little noise, fixed for a stretch of time)."""
        r = random.Random(f"{side}|{int(self.t // 900)}|{self.seed}")
        return r.uniform(-0.1, 0.1)

    def _system_line(self, side: str, name: str, v: "SideView") -> str:
        d = SYSTEMS[name]
        st = self.sys[name]
        owner = self.owner(name)
        who = {"astra": "ASTRA", "mandate": "Mandate", "guilds": "neutral (Free Guilds)", "silent": "nobody holds it (no contact)", "contested": "contested"}.get(owner, owner)
        bits = [f"{name}: {who}, value {d['value']}"]
        if d.get("home"):
            bits.append("capital")
        if owner == side:
            if st.yard > 0:
                nxt = max(0.0, (CLASSES[st.build or YARD_DEFAULT.get(name, 'vigilant')]['cost'] - st.progress) / st.yard * 3600.0) if st.build or YARD_DEFAULT.get(name) else 0
                bits.append(f"yard {st.yard:.1f} pts/h building {st.build or YARD_DEFAULT.get(name)} (next in {fmt_s(nxt)})" + (", BLOCKADED" if st.blockaded_by else ""))
            bits.append(f"fort {d['fort']:g}" + (f" at {int(100 * st.fort_hp)}%" if st.fort_hp < 0.95 else ""))
            bits.append("post " + ("working" if st.post.get(side) else "SILENT"))
            if st.siege_by:
                bits.append(f"UNDER SIEGE ({int(100 * st.siege_s / self.siege_time(name))}% to falling)")
        elif owner in SIDES:
            bits.append("yard" if st.yard > 0 else "no yard")
        elif owner == "silent":
            bits.append("no post of anyone's")
        here = [f for f in v.own if f.where == name and f.status != "scripted"]
        trk = [t for t in v.tracks.values() if t.system == name]
        if here:
            bits.append("your fleets: " + ", ".join(f"{f.id} ({f.n})" for f in here))
        if trk:
            bits.append("enemy seen: " + ", ".join(f"{t.fid} (~{t.n}, {fmt_s(self.t - t.seen_t)} ago)" for t in trk))
        if name in self.battles and (self.sees(side, name) >= 1 or here):
            bits.append("BATTLE")
        bits.append("gates: " + ", ".join(self.links(name)))
        return "- " + "; ".join(bits)

    def _fleet_line(self, f: Fleet) -> str:
        o = f.order
        where = (f"in the Gate for {f.route[0]} (arrives in {fmt_s(max(0.0, f.arrive_at - self.t))})" if f.in_gate and f.route
                 else f"at {f.where}, about to jump for {f.order.target or 'its objective'}" if f.status == "scripted" and f.side == "mandate"
                 else f"at {f.where}, forming up to join" if f.status == "scripted" else f"at {f.where}")
        route = f"; route {' > '.join(f.route)}" if f.route and not f.in_gate else ""
        order = f"{o.kind}" + (f" {o.target}" if o.target else "") + f" ({o.stance}{', dark' if f.dark else ''})"
        if o.since and o.by != "default":
            order += f", by {o.by} {fmt_s(max(0, self.t - o.since))} ago" + (f": \"{o.reason[:90]}\"" if o.reason else "")
        elif o.reason:
            order += f": \"{o.reason[:90]}\""
        pend = f"; ORDER ON ITS WAY: {f.pending.kind} {f.pending.target} (reaches it in {fmt_s(max(0.0, f.pending_at - self.t))})" if f.pending else ""
        who = f.commander.get("name") or ""
        battle = ("; IN BATTLE" if f.status == "engaged" else "; besieging" if f.status == "besieging" else "; with the Aquila, in the Captain's hands" if f.status == "real"
                  else "; the game's own script is bringing it in: it takes no orders yet" if f.status == "scripted" else "")
        air = sum(s.fighters + s.bombers + s.drones for s in f.ships)
        return (f"{f.id} {f.name}: {f.composition()}{f' + {air} craft' if air else ''}; hull {int(100 * f.hull)}%, supply {int(100 * f.supply)}%, morale {f.morale:.2f}; {where}{route}; "
                f"order: {order}{battle}{pend}" + (f"; led by {who}" if who else ""))

    def director_view(self) -> str:
        """Everything, as the director (omniscient) reads it: both sides' fleets with what they are doing and what their admirals mean to do, the battles, the
        wills, who is taking what. It is the war's truth; the director shapes the pace of the story with it and never the strength of a fleet."""
        out = [f"THE MARCH AT WAR, {self.clock()}. Wills to fight: ASTRA {self.will['astra']:.2f}, Mandate {self.will['mandate']:.2f}."]
        if self.over:
            out.append(f"THE WAR IS OVER: {self.over['why']}.")
        if self.truce:
            out.append(f"A truce is in force for {fmt_s(max(0.0, self.truce['until'] - self.t))}.")
        for s in SIDES:
            out.append(f"{SIDE_WORD[s]} high command's plan: " + (self.plans[s] or "(none written yet)"))
        out.append("The Aquila: " + (f"in the lane to {self.aquila['lane']}" if self.aquila["lane"] else f"at {self.aquila['where']}") + ".")
        for s in SIDES:
            out.append(f"{SIDE_WORD[s].upper()} FLEETS")
            for f in sorted(self.side_fleets(s), key=lambda x: x.id):
                out.append("- " + self._fleet_line(f) + (f"; scripted ({f.scripted})" if f.status == "scripted" else ""))
        out.append("SYSTEMS")
        for name in SYSTEM_ORDER:
            if name not in self.sys:
                continue
            st, owner = self.sys[name], self.owner(name)
            bits = [f"{name}: {owner}, value {SYSTEMS[name]['value']}"]
            if st.yard > 0:
                bits.append(f"yard {st.yard:.1f}/h ({st.build or YARD_DEFAULT.get(name)})")
            if st.siege_by:
                bits.append(f"{st.siege_by} besieges it ({int(100 * st.siege_s / self.siege_time(name))}%)")
            if st.blockaded_by:
                bits.append(f"blockaded by {st.blockaded_by}")
            if name in self.battles:
                bits.append(f"BATTLE {fmt_s(self.t - self.battles[name].t0)} old")
            if SYSTEMS[name]["fort"]:
                bits.append(f"fort {int(100 * st.fort_hp)}%")
            posts = [s for s in SIDES if st.post.get(s)]
            bits.append("post: " + (", ".join(posts) if posts else "none"))
            out.append("- " + "; ".join(bits))
        recent = [e for e in self.events[-16:] if e.weight >= 1]
        if recent:
            out.append("THE WAR'S LATEST (all of it, true)")
            for e in recent:
                out.append(f"- {fmt_s(max(0, self.t - e.t))} ago · {e.system + ': ' if e.system else ''}{e.text.get('astra') or e.text.get('mandate')}")
        return "\n".join(out)

    def field_brief(self, side: str, system: str) -> str:
        """What the commanders in the field (the real simulation's: war_minds.py) read of their high command: its plan, the orders of the fleets in their system, what is
        on its way to them (their own side's fleets with their time of arrival, and what their side's eyes say of the enemy's), and the war elsewhere. Facts and intent
        from the side's own picture, no more than its fleets would have been told: what to do with them is the commander's."""
        v = self.view(side)
        out = []
        if self.plans[side]:
            out.append(f"Your high command's plan ({fmt_s(self.t - self.plan_t[side])} ago): {self.plans[side]}")
        home = self.home_orders.get(side)
        if home and home["until"] > self.t:
            out.append(f"Orders from home: {home['text']}")
        here = [f for f in v.own if f.where == system and f.status != "scripted"]
        for f in sorted(here, key=lambda x: x.id):
            o = f.order
            out.append(f"Fleet orders for {f.name}: {o.kind}{' ' + o.target if o.target else ''} ({o.stance}" + (f"; by {o.by}" if o.by not in ("default", "auto") else "") + ")"
                       + (f", reason: {o.reason[:100]}" if o.reason and o.by not in ("default", "auto") else ""))
        coming = []
        for f in v.own:
            if f.where == system or f.status in ("scripted",):
                continue
            dest = f.route[-1] if f.route else ""
            if f.order.kind in ("reinforce", "escort"):
                tf = self.fleets.get(f.order.target)
                dest = (tf.where or (tf.route[-1] if tf.route else "")) if tf else dest
            if dest == system or (f.in_gate and f.route and f.route[0] == system):
                eta = self.eta(f, system)
                if eta is not None:
                    coming.append((eta, f"{f.name} ({f.n} ships: {f.composition()}) is on its way to you: about {fmt_s(eta)}" + (self.reach_note(f).replace("; the Gate", " (the Gate", 1) + ")" if (system == self.real_system and self.reach_note(f)) else "")))
        for _, text in sorted(coming):
            out.append(text)
        for tr in sorted(v.tracks.values(), key=lambda t: -self.track_power(t)):
            if self.t - tr.seen_t < 900.0 and (tr.moving_to == system or (tr.system == system and not self.sees(side, system))):
                cls = f" ({composition(tr.classes)})" if tr.classes else ""
                out.append(f"Your side's eyes: about {tr.n} enemy ships{cls} seen {fmt_s(self.t - tr.seen_t)} ago at {tr.system}" + (f", heading for {tr.moving_to}" if tr.moving_to else ""))
        elsewhere = [e for e in v.news[-30:] if e.kind in ("system_taken", "siege", "siege_broken", "battle_end", "war_over", "truce", "truce_over") and e.system != system]
        for e in elsewhere[-3:]:
            out.append(f"Elsewhere, {fmt_s(max(0, self.t - e.t))} ago: {e.text[side]}")
        return "\n".join(out)

    def board(self, side: str = "astra", max_lines: int = 12) -> str:
        """The short board for the bridge (the XO, comms and ops read it with the fleet board): the front as the Fleet knows it."""
        v = self.view(side)
        lines = []
        for f in sorted(v.own, key=lambda x: -x.power)[:7]:
            o = f.order
            where = f"in the Gate for {f.route[0]}, {fmt_s(max(0.0, f.arrive_at - self.t))}" if f.in_gate and f.route else f"at {f.where}"
            lines.append(f"- {f.name} ({f.n} ships, hull {int(100 * f.hull)}%): {where}; {o.kind}{' ' + o.target if o.target else ''}" + ("; IN BATTLE" if f.status == "engaged" else ""))
        for tr in sorted(v.tracks.values(), key=lambda t: -self.track_power(t))[:5]:
            lines.append(f"- Mandate force {tr.fid}: about {tr.n} ships at {tr.system}, seen {fmt_s(self.t - tr.seen_t)} ago" + (f", heading for {tr.moving_to}" if tr.moving_to else ""))
        for b in self.battles.values():
            if self.sees(side, b.system) >= 1 or any(self.fleets[f].side == side for s in SIDES for f in b.fleets[s] if f in self.fleets):
                lines.append(f"- BATTLE at {b.system}, {fmt_s(self.t - b.t0)} in")
        return "\n".join(lines[:max_lines])

    # ------------------------------------------------------------------------------------------- what the minds and the director can do besides giving orders
    def assess(self, side: str, own_refs: list[str] | str, target: str, runs: int = 28) -> tuple[bool, str]:
        """The staff's estimate of a meeting: the named fleets of `side` (with what is already theirs at the place) against what the side believes is there — the
        tracks it holds, with their age, and the defences if the ground is the enemy's. It is the same battle model the war uses, read twice (as many as the contact
        says, and a third more), so that the answer is as uncertain as the intelligence is. Information: it forbids nothing."""
        refs = [own_refs] if isinstance(own_refs, str) else list(own_refs)
        mine = [self.find_fleet(side, r) for r in refs]
        if not mine or any(f is None for f in mine):
            return False, "name one or more of your fleets (by id or name)"
        dest = self.war.find(target) or ""
        if not dest:
            return False, f"no system '{target}'"
        fleets: list[Fleet] = [f for f in mine if f is not None]
        here_friends = [g for g in self.fleets_at(dest, side) if g not in fleets and g.status not in ("scripted", "real")]
        tracks = [t for t in self.tracks[side].values() if t.system == dest and self.t - t.seen_t <= 1200.0]
        ua: list[mb.Unit] = []
        for f in fleets + here_friends:
            for sh in f.ships:
                ua.append(mb.Unit(sh.cls, 0, f.id, sh.name, hull_frac=sh.hull, supply=f.supply, wing=(sh.fighters, sh.bombers, sh.drones), stance="steady", params=self.bp))

        def enemy(scale: float) -> list[mb.Unit]:
            out: list[mb.Unit] = []
            for tr in tracks:
                if tr.classes:
                    comp = list(tr.classes.items())
                else:
                    cls = "styx" if side == "astra" else "vigilant"
                    comp = [(cls, max(1, tr.n))]
                for cls, n in comp:
                    for _ in range(max(0, int(round(n * scale)))):
                        out.append(mb.Unit(cls, 1, tr.fid, cls, hull_frac=tr.hull or 0.9, params=self.bp))
            if self.owner(dest) == other(side) and SYSTEMS[dest]["fort"] > 0:
                out.append(mb.Unit(mb.FORT_CLASS, 1, "fort", "the defences", hull_frac=self.sys[dest].fort_hp, fort=SYSTEMS[dest]["fort"], params=self.bp))
            return out

        base = enemy(1.0)
        if not base:
            return True, (f"You hold no track on {dest}: nothing is known of what stands there. "
                          + (f"Its defences are the enemy's (fort {SYSTEMS[dest]['fort']:g}). " if self.owner(dest) == other(side) else "")
                          + "A recon (`recon` order, run dark) is what finds out.")
        lines = []
        for label, scale in (("as many as the contact says", 1.0), ("a third more than it says", 1.33)):
            foe = enemy(scale)
            r = mb.forecast(ua, foe, runs=runs, seed=int(self.t // 60) + len(dest), params=self.bp)
            lines.append(f"- if they are {label}: your side holds the field {int(100 * r['win'][0])}% of the time, they do {int(100 * r['win'][1])}%, neither {int(100 * r['draw'])}%; "
                         f"you lose about {r['lost'][0]:.1f} of your {len(ua)} ships, they lose about {r['lost'][1]:.1f} of {len(foe)}")
        age = min(self.t - t.seen_t for t in tracks)
        names = ", ".join(f"{t.fid} (about {t.n} ships, seen {fmt_s(self.t - t.seen_t)} ago, level {t.level})" for t in tracks)
        extra = f" Your fleets already at {dest} are counted on your side." if here_friends else ""
        return True, (f"Staff estimate for {', '.join(f.name for f in fleets)} at {dest} against {names}"
                + (" and its defences" if self.owner(dest) == other(side) and SYSTEMS[dest]["fort"] > 0 else "") + f":{extra}\n" + "\n".join(lines)
                + f"\n(The contact is {fmt_s(age)} old: they may have moved, or reinforced. Fleets that arrive piecemeal fight piecemeal; this reads them as one battle.)")

    def reveal(self, side: str, fid: str, how: str = "an agent's report") -> bool:
        """What the director may do for a side's intelligence: let it learn something TRUE — where a fleet of the other side is, as it is now — by some means of the
        story's (a defector, a Guild courier, an intercepted signal). The fleet is a real one: the fog is lifted on it for a moment, nothing is invented."""
        f = self.fleets.get(fid)
        if f is None or f.side == side or f.status == "scripted":
            return False
        where = f.where or (f.hop_from if f.in_gate else "")
        if not where:
            return False
        n, cls = self._noisy(side, f, 2)
        self.tracks[side][f.id] = Track(f.id, where, self.t, 2, n, cls, None, f.route[0] if f.in_gate and f.route else "")
        what = f"{f.id}: about {n} ships ({composition(cls or {})}) at {where}" + (f", heading for {f.route[0]}" if f.in_gate and f.route else "")
        self.say("intel", where, {side: f"Intelligence report, {what}. Source: {how}."}, (side,), 2, (f.id,))      # (the war says what is learnt; the story says only how)
        return True

    def pressure(self, side: str, text: str, minutes: float = 60.0) -> None:
        """What the government at home demands of a side's high command, for a while (the story's: the war's rules do not change)."""
        self.home_orders[side] = {"text": (text or "").strip()[:300], "until": self.t + minutes * 60.0}
        self.say("orders_from_home", "", {side: f"Orders from home: {text.strip()[:240]}"}, (side,), 2)

    def use_tender(self, side: str) -> tuple[bool, float]:
        """A supply tender for the Aquila: there are few, and one is busy for a quarter of an hour after it has been used. (ok, seconds to wait if not)"""
        wait = self.tender_free_at.get(side, 0.0) - self.t
        if wait > 0:
            return False, wait
        self.tender_free_at[side] = self.t + 900.0
        return True, 0.0

    def task_aquila(self, system: str, mission: str, why: str = "") -> tuple[bool, str]:
        """Fleet's order to the Aquila (Rourke's): where she is wanted and what for. It is an order of the service, not a rule of the world: the Captain decides what to
        do with it, and the war goes on either way."""
        dest = self.war.find(system) or ""
        if not dest:
            return False, f"no system '{system}' in the March"
        here = self.aquila["where"]
        if dest == here and not self.aquila["lane"]:
            return False, f"the Aquila is at {dest} already: if you need something of her there, tell the Captain (tell_captain); this order is for sending her somewhere"
        if dest != here and self.hops(here, dest, "astra") >= 99:
            return False, f"no way through the Gates from {here} to {dest}"
        self.aquila_task = {"system": dest, "mission": (mission or "").strip()[:240], "why": (why or "").strip()[:240], "t": self.t}
        bits = f"Fleet orders the Aquila to {dest}: {mission.strip()[:200]}"
        self.say("fleet_orders", dest, {"astra": bits}, ("astra",), 1, ())
        return True, f"the order to the Aquila stands: {dest}" + (f" ({self.hops(here, dest, 'astra')} Gate{'s' if self.hops(here, dest, 'astra') != 1 else ''} from {here})" if dest != here else " (she is there)")

    # ------------------------------------------------------------------------------------------- saving
    def default_path(self) -> str:
        return os.path.join(os.path.dirname(self.war.save_path), "march.json")

    def to_dict(self) -> dict[str, Any]:
        return {"t": round(self.t, 1), "seed": self.seed, "owners": {k: self.owner(k) for k in self.sys}, "fleets": [f.to_dict() for f in self.fleets.values()], "sys": {k: v.to_dict() for k, v in self.sys.items()},
                "events": [e.to_dict() for e in self.events[-120:]], "event_n": self.event_n, "will": self.will, "plans": self.plans, "plan_t": self.plan_t, "score": self.score,
                "over": self.over, "guilds_open": self.guilds_open, "home_orders": self.home_orders, "tender_free_at": self.tender_free_at, "aquila_task": self.aquila_task, "truce": self.truce, "proposals": self.proposals, "aquila": self.aquila, "aquila_seen": list(self.aquila_seen), "next_id": self.next_id,
                "used_names": sorted(self.used_names), "opening_plan": self.opening_plan, "hail_fleets": sorted(self.hail_fleets), "tracks": {s: {k: v.to_dict() for k, v in self.tracks[s].items()} for s in SIDES},
                "log": {s: [e.to_dict() for e in self.log[s]] for s in SIDES}, "rcv": self.rcv, "inbox": {s: [[round(w, 1), e.n] for w, e in self.inbox[s]] for s in SIDES}}

    def save(self, path: str | None = None) -> None:
        path = path or self.save_path or self.default_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            self.last_save, self.dirty = self.t, False
            if getattr(self.war, "_dirty", False):
                self.war.save()
        except OSError:
            log.exception("could not save the March")

    def load(self, path: str | None = None) -> bool:
        path = path or self.save_path or self.default_path()
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            self._from_dict(d)
            return True
        except (OSError, ValueError, KeyError, TypeError):
            log.exception("could not read the saved March") if os.path.exists(path) else None
            return False

    def _from_dict(self, d: dict[str, Any]) -> None:
        self.t = float(d.get("t", 0.0))
        self.seed = int(d.get("seed", self.seed))
        for k, o in (d.get("owners") or {}).items():
            if k in self.war.systems:
                self.war.systems[k]["owner"] = o                    # (the war's course decides who holds what: the saved war map follows it)
        self.fleets = {x["id"]: Fleet.from_dict(x) for x in d.get("fleets", [])}
        for k, v in (d.get("sys") or {}).items():
            if k in self.sys:
                s = self.sys[k]
                s.fort_hp = float(v.get("fort_hp", 1.0))
                s.post = {a: bool(b) for a, b in (v.get("post") or {}).items()}
                s.build, s.progress = v.get("build", s.build), float(v.get("progress", 0.0))
                s.siege_by, s.siege_s = v.get("siege_by", ""), float(v.get("siege_s", 0.0))
                s.claim_by, s.claim_s = v.get("claim_by", ""), float(v.get("claim_s", 0.0))
                s.blockaded_by, s.last_fight_t = v.get("blockaded_by", ""), float(v.get("last_fight_t", -1e9))
                s.raid_s, s.restore_s = float(v.get("raid_s", 0.0)), float(v.get("restore_s", 0.0))
        self.events = [Event.from_dict(e) for e in d.get("events", [])]
        self.event_n = int(d.get("event_n", len(self.events)))
        self.will = {s: float(d.get("will", {}).get(s, self.will[s])) for s in SIDES}
        self.plans = {s: str(d.get("plans", {}).get(s, "")) for s in SIDES}
        self.plan_t = {s: float(d.get("plan_t", {}).get(s, 0.0)) for s in SIDES}
        self.score = d.get("score") or self.score
        self.over, self.truce, self.proposals = d.get("over") or {}, d.get("truce") or {}, d.get("proposals") or {}
        self.guilds_open = {k: float(v) for k, v in (d.get("guilds_open") or {}).items()}
        self.home_orders = dict(d.get("home_orders") or {})
        self.tender_free_at = {s: float((d.get("tender_free_at") or {}).get(s, 0.0)) for s in SIDES}
        self.aquila_task = dict(d.get("aquila_task") or {})
        self.aquila = d.get("aquila") or self.aquila
        self.aquila_seen = tuple(d.get("aquila_seen") or ("", 0.0))                       # type: ignore[assignment]
        self.next_id = d.get("next_id") or self.next_id
        self.used_names = set(d.get("used_names") or [])
        self.opening_plan = [dict(p) for p in d.get("opening_plan") or []]
        self.hail_fleets = set(d.get("hail_fleets") or [])
        self.tracks = {s: {k: Track.from_dict(v) for k, v in (d.get("tracks", {}).get(s) or {}).items()} for s in SIDES}
        by_n = {e.n: e for e in self.events}
        self.log = {s: deque([Event.from_dict(e) for e in d.get("log", {}).get(s, [])], maxlen=60) for s in SIDES}
        self.rcv = {s: int((d.get("rcv") or {}).get(s, 0)) for s in SIDES}
        self.inbox = {s: deque((float(w), by_n[n]) for w, n in d.get("inbox", {}).get(s, []) if n in by_n) for s in SIDES}
        self.battles.clear()
        self.real_system, self.real_fight = "", False
        for f in self.fleets.values():
            if f.status in ("engaged", "real"):
                f.status = "ready"                                    # (a battle in progress is not kept, nor is the real simulation's: the fleets meet again at the next step)
        self.dirty = True

    def reset(self, seed: int | None = None) -> None:
        """A new war: the fleets of the order of battle, the map as it was."""
        self.war.reset()
        self.__init__(self.war, seed=self.seed if seed is None else seed, path=self.save_path, params=self.bp)         # type: ignore[misc]


DAY_S = 1800.0                                                    # a day of the war, for the news and the clock: half an hour of play
SYSTEM_ORDER = ["Concordia", "Meridian", "Aurelia", "Cassia", "Veyra", "Thule", "Ophir", "Erebus", "Nemet", "Niflheim", "Kharon"]


class SideView:
    """What a side's high command can read of the March: its own fleets (the objects: they are its own), the tracks of the enemy's it has found, the news that
    reached it. The minds' pictures and the code's reflexes both read this, and nothing else of the war."""

    def __init__(self, march: March, side: str, own: list[Fleet], tracks: dict[str, Track], news: list[Event]) -> None:
        self.march, self.side, self.own, self.tracks, self.news = march, side, own, tracks, news

    @property
    def t(self) -> float:
        return self.march.t

    def own_at(self, system: str) -> list[Fleet]:
        return [f for f in self.own if f.where == system]

    def enemy_at(self, system: str, max_age: float = 900.0) -> list[Track]:
        return [t for t in self.tracks.values() if t.system == system and self.march.t - t.seen_t <= max_age]

    def enemy_power(self, system: str, max_age: float = 900.0) -> float:
        m = self.march
        fort = SYSTEMS[system]["fort"] * m.sys[system].fort_hp * 0.9 if m.owner(system) == other(self.side) else 0.0
        return sum(m.track_power(t) for t in self.enemy_at(system, max_age)) + fort

    def own_power(self, system: str) -> float:
        fort = SYSTEMS[system]["fort"] * self.march.sys[system].fort_hp * 0.9 if self.march.owner(system) == self.side else 0.0
        return sum(f.power for f in self.own_at(system) if f.status != "scripted") + fort


def fmt_s(s: float) -> str:
    """Seconds as people say them: "40 s", "3 min 20 s", "1 h 05 min"."""
    s = max(0, int(round(s)))
    if s < 90:
        return f"{s} s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m} min" + (f" {sec:02d} s" if m < 10 and sec else "")
    h, m = divmod(m, 60)
    return f"{h} h {m:02d} min"
