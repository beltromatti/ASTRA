"""The March and the real simulation: where the Aquila is, the war is played ship by ship; everywhere else the March plays it (docs/GUERRA.md §10).

The Aquila's system is the game's own simulation (the war bench's ships, the tactical commanders, the Captain). The rest of the Aurelia March is the abstract world of
march.py, calibrated on that simulation. This module is the join between them, and nothing else:

  - the Aquila's place: from the game's Gate status (she is in a Gate's lane, or through into a system) the March knows where the real simulation is; the fleets it was
    playing go back to the map where they stand when she leaves;
  - IN: a fleet of the March that comes to her system (through the Gate, or standing there when she arrives) is sent to the game as the ships it really has, damaged as
    they are, led by the people it has (a `director_beat`); the fleets the game's own script brings (the opening: the picket, the strike group, the relief, the
    vanguard) are adopted by the contact ids the game gives them;
  - OUT: every second the game's views of the ships (the ASTRA groups, the Mandate's view, the contacts) say what became of the ships the March sent: hulls, losses, the ones
    that jumped out; the war's scores, the people's will and the fleets follow;
  - the story: the war's news reaches the bridge as the fleet net's bulletins (comms relays them), a major battle ends a chapter of the story, the war goes on while the
    Captain is lost (`fast_forward`).

It judges nothing: the minds (strategy.py and war_minds.py) decide; this carries facts both ways."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from typing import Any, Awaitable, Callable

from .march import STRAGGLERS, Fleet, March, SIDES, Ship
from .march_auto import AutoAdmiral
from .march_data import ASTRA_PEOPLE, CARRIERS, CLASSES, MANDATE_PEOPLE
from .strategy import StrategicMinds

log = logging.getLogger("astra.march_glue")

LEAD_S = 20.0                   # a fleet coming through the Gate into her system is sent to the game this long before it arrives (the beat's own delay)
PRESENT_DELAY_S = 12.0          # a fleet that is there when she arrives comes into the game this long after (the new sky settles first)
MAX_REAL_SHIPS = 36             # warships the game plays at once (docs/SCALA.md: 30 capital ships and 150 craft hold 60 fps); a fleet that would overflow waits in the Gate
GATE_WAIT_S = 90.0              # ... for this long, and then tries again
GROUP_SHIPS = 8                 # ships in one battle group when the fleet has none of its own
MAX_GROUPS = 4                  # battle groups in one beat (the game takes 40 ships, ten a group)
GRACE_S = 1800.0                # a fleet the game's script was to bring that has not come this long after its time is the map's
RETRIES = 3
LANE_TIMEOUT_S = 90.0           # a Gate lane lasts well under this: past it, with no lane in the game's Gate status, the Aquila has arrived
BULLETIN_GAP_S = 25.0           # the fleet net does not report more often than this
HOLO_EVERY_S = 10.0
SAVE_EVERY_S = 60.0
MAX_DT_S = 5.0                  # a gap in the game's state (paused, loading) is not war time
ARC_GAP_S = 2400.0              # a major battle ends a chapter of the story at most this often
FF_HOURS = 3.0                  # the war that goes on while the Captain is lost: this many hours of war time (the weeks the story skips)

GATE_RE = re.compile(r"Janus Gate: bearing (\d+) mark (-?\d+), ([\d.]+) km")
LANE_RE = re.compile(r"in the gate's lane to the (.+?) system")
IDS_RE = re.compile(r"T-\d+")
FATE_RE = re.compile(r"\((T-\d+)[,)]")

# the kinds of news the bridge hears about the war elsewhere (what happens in the Aquila's own system she sees for herself, except the Gate's warning)
BULLETIN_KINDS = ("wake", "system_taken", "siege", "siege_broken", "war_over", "truce", "truce_over", "proposal", "intel", "orders_from_home", "passage", "post_lost")
OWN_SKY_KINDS = ("battle_start", "battle_end", "battle_update", "arrival", "fleet_formed", "responding", "battle_join", "fleet_ready", "production", "supply")


def parse_gate(text: str) -> tuple[float, float] | None:
    """(bearing, km) of the Janus Gate from the Aquila, from the game's Gate status."""
    m = GATE_RE.search(text or "")
    return (float(m.group(1)), float(m.group(3))) if m else None


def ships_of(state: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """What the game says of the ships it plays: the live ones (contact id -> its row: hull, shields, missiles) and the ones that are gone (id -> "destroyed" | "fled")."""
    alive: dict[str, dict[str, Any]] = {}
    gone: dict[str, str] = {}
    for g in (state.get("_astra_groups") or {}).get("your_groups") or []:
        for mm in g.get("members") or []:
            if mm.get("id"):
                alive[str(mm["id"])] = mm
    for s in (state.get("_mandate") or {}).get("your_ships") or []:
        cid = str(s.get("id") or "")
        if not cid:
            continue
        st = str(s.get("state", ""))
        if st.startswith("destroyed"):
            gone[cid] = "destroyed"
        elif st.startswith("jumped"):
            gone[cid] = "fled"
        else:
            alive[cid] = s
    for c in state.get("contacts") or []:
        cid = str(c.get("id") or "")
        if cid and cid not in alive and cid not in gone and "destroyed" not in str(c.get("status", "")) and c.get("hull_pct") is not None:
            alive[cid] = c
    return alive, gone


class MarchGlue:
    def __init__(self, march: March, minds: StrategicMinds | None, *, command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 register_groups: Callable[[list[str], list[dict[str, Any]], str, dict[str, Any], str], None] | None = None,
                 announce: Callable[[str], Awaitable[None]] | None = None, note: Callable[[str], None] | None = None,
                 send_sector: Callable[[], Awaitable[None]] | None = None, lang: Callable[[], str] = lambda: "en", clock: Callable[[], float] = time.monotonic) -> None:
        self.m = march
        self.minds = minds
        self.command = command                          # (name, args) -> the game's result: `director_beat`
        self.register_groups = register_groups          # (ids, groups, kind, force commander, why): the new commanders get a mind and a voice (director.py)
        self.announce = announce                        # (text): the fleet net reports it on the bridge
        self.note = note or (lambda text: None)         # the campaign log
        self.send_sector = send_sector                  # (): the holo table is drawn again
        self.lang = lang
        self.clock = clock
        self.active = False
        self.disabled_reflexes = False
        self.gate: tuple[float, float] | None = None
        self.state: dict[str, Any] = {}
        self.seen: set[str] = set()                     # the contact ids of the March's ships that the game has shown alive
        self.fate: dict[str, str] = {}                  # contact id -> destroyed | fled (what the game's events said)
        self.tries: dict[str, int] = {}
        self.sending: set[str] = set()
        self.reserve: dict[str, float] = {}             # fleet -> when it may try the Gate again (the game's sky was full)
        self.opening: set[str] = set()                  # the fleets the game's opening brings in itself: the map leaves them to it until they show (or the grace is out)
        self.due: dict[str, float] = {}                 # contact id -> when the ship should have shown in the game's views by (a ship that never came is dropped)
        self.ff = False                                 # the war is being run without the Aquila: the game's state does not move it
        self.on_war_over: Callable[[str], None] | None = None   # (text): the war has ended (a capital fell, a people's will is gone, an armistice): the story tells its end
        self._over_told = False
        self._pending: list[tuple[str, str]] = []       # bulletins for the bridge (kind, text), waiting for the fleet net's quiet
        self._last: float | None = None
        self._bul_seen = 0
        self._bul_t = -1e9
        self._holo_t = -1e9
        self._save_t = self.clock()
        self._arc_t = -1e9
        self._fight_off_t: float | None = None
        self._transit: dict[str, Any] | None = None
        self.stats = {"sent": 0, "refused": 0, "lost": 0, "fled": 0, "bulletins": 0, "adopted": 0, "errors": 0}
        self._err_t = -1e9
        if minds is not None:
            minds.on_aquila_task = self._task_aquila
            minds.on_tender = self._tender

    # ------------------------------------------------------------------------------------------------ the campaign
    def start(self, new: bool) -> None:
        """A campaign begins (a new war, or the saved one): the March is the war's authority from now on."""
        m = self.m
        m.live_scripts = True                           # (the game brings its own fleets in: the clock of the bench does not)
        m.save_path = m.default_path()
        if new:
            m.reset(random.randrange(1, 10 ** 6))
            if self.minds is not None:
                self.minds.reset()
        else:
            self.load()
        m.aquila_arrived(m.war.current if m.war.current in m.sys else "Aurelia")
        self.reset_real(keep_opening=True, present_only=not new)       # (the game builds the opening's picket whenever it starts: in a saved war too, if the Aquila is at Aurelia)
        self._over_told = bool(m.over)                  # (a war that ended before is not told again)
        self.active = True
        self._last = None
        self._bul_seen = m.rcv["astra"]

    def reset_real(self, keep_opening: bool = False, present_only: bool = False) -> None:
        """The game's simulation starts afresh (a new session, a saved campaign): none of the ships the March knew there are there any more, except the ones the opening
        brings (the order of battle gave them their contact ids: when they show, the fleets are the game's): all of them in a new war, only the ones that stand in the Aquila's
        system in a saved one (the game builds its picket whenever it starts)."""
        self.seen.clear()
        self.fate.clear()
        self.tries.clear()
        self.sending.clear()
        self.reserve.clear()
        self.due.clear()
        self.opening.clear()
        self._fight_off_t = None
        self._transit = None
        for f in self.m.fleets.values():
            if keep_opening and any(s.cid for s in f.ships) and f.status != "real" and (not present_only or (f.where == self.m.real_system and f.status != "scripted")):
                self.opening.add(f.id)
                continue
            for s in f.ships:
                s.cid = ""
            if f.status == "real":
                f.status = "ready"
        self.m.real_fight = False

    def stop(self) -> None:
        self.active = False

    # ------------------------------------------------------------------------------------------------ the clock
    def feed(self, state: dict[str, Any]) -> None:
        """About once a second, with the ship state: the war goes on, the real simulation and the map are joined, the minds look."""
        if not self.active or not state or self.ff:
            return
        now = self.clock()
        dt = 0.0 if self._last is None else min(MAX_DT_S, max(0.0, now - self._last))
        self._last = now
        m = self.m
        self.state = state
        try:
            self._place(state)
            self._adopt(state)
            if dt > 0.0:
                m.run(dt)
            if m.over and not self._over_told:
                self._over_told = True
                self._tell_the_end()
            self._bring_in()
            self._read_back(state)
            self._transit_again(now)
            if self.minds is not None:
                self.minds.feed(state)
            self._bulletins(now)
            state["_march_board"] = m.board("astra")
            self._holo(now)
            self._save(now)
        except Exception:  # noqa: BLE001
            self.stats["errors"] += 1
            if self.clock() - self._err_t > 60.0:                    # (a defect that comes every second is told once a minute)
                self._err_t = self.clock()
                log.exception("the March could not follow the game's state (%d times so far)", self.stats["errors"])

    # ------------------------------------------------------------------------------------------------ the Aquila
    def _place(self, state: dict[str, Any]) -> None:
        text = str(state.get("janus_gate") or "")
        g = parse_gate(text)
        if g:
            self.gate = g
        lane = LANE_RE.search(text)
        if lane:
            dest = self.m.war.find(lane.group(1))
            if dest and self.m.aquila["lane"] != dest:
                log.info("the Aquila is in the Gate's lane to %s: the real simulation's fleets are the map's again", dest)
                self.m.aquila_lane(dest)
        elif self.m.aquila["lane"] and self.m.t - self.m.aquila["since"] > LANE_TIMEOUT_S:
            self.m.war.arrived(self.m.aquila["lane"])             # (the lane is over and nobody said she arrived: she did)
        elif not self.m.real_system and not self.m.aquila["lane"]:
            self.m.aquila_arrived(self.m.war.current if self.m.war.current in self.m.sys else "Aurelia")

    # ------------------------------------------------------------------------------------------------ the game's own fleets
    def _adopt(self, state: dict[str, Any]) -> None:
        """The fleets the game brings in itself (the opening's picket, strike group, relief, vanguard) carry contact ids the March knows from its order of battle: when one
        of them shows in the game's views the fleet is the real simulation's."""
        m, rs = self.m, self.m.real_system
        if not rs:
            return
        alive, gone = ships_of(state)
        here = set(alive) | set(gone)
        for f in list(m.fleets.values()):
            if f.status == "real":
                continue
            if not any(s.cid and s.cid in here for s in f.ships):
                if f.status == "scripted" and f.scripted_at and m.t > f.scripted_at + GRACE_S:
                    m.release_script(f.id)                     # it never came: the map plays it
                continue
            if f.status != "scripted" and f.where != rs:
                continue
            m.real_adopt(f, rs)
            self.opening.discard(f.id)
            self.stats["adopted"] += 1
            log.info("the game plays %s (%d ships)", f.name, f.n)

    # ------------------------------------------------------------------------------------------------ in: the map's fleets come into the game
    def _bring_in(self) -> None:
        m, rs = self.m, self.m.real_system
        if not rs or m.aquila["lane"]:
            return
        now = self.clock()
        if rs in m.battles:
            m.cut_battle(rs)                                    # (a battle the map was fighting where she has come: the game takes it over, with the fleets as they stand)
        for f in list(m.fleets.values()):
            if f.status in ("real", "scripted", "engaged") or f.id in self.sending:
                continue
            if f.id in self.opening:
                if m.t < GRACE_S:
                    continue
                self.opening.discard(f.id)                      # (the game never brought it: the map sends it)
            coming = f.in_gate and f.route and f.route[0] == rs and f.arrive_at - m.t <= LEAD_S
            if not (f.where == rs or coming) or f.note.startswith(STRAGGLERS):
                continue                                         # (the ships that jumped out of her sky are leaving it, not coming in)
            if self._passing(f):
                continue
            if now < self.reserve.get(f.id, 0.0):
                continue
            real_n = sum(x.n for x in m.fleets.values() if x.status == "real")
            if real_n > 0 and real_n + f.n > MAX_REAL_SHIPS:
                self._hold_in_gate(f, now)
                continue
            delay = max(5.0, f.arrive_at - m.t) if coming else PRESENT_DELAY_S
            at_gate = bool(coming or f.zone == "gate")
            m.real_adopt(f, rs)
            self.sending.add(f.id)
            asyncio.ensure_future(self._send(f, delay, at_gate))

    def _passing(self, f: Fleet) -> bool:
        """An ASTRA fleet that only passes through her system on its way (its route goes on) is not in the game: it is among friends and nothing is to be played. The
        Mandate's is always in it: whoever comes through the Gate meets her."""
        rs = self.m.real_system
        ahead = f.route[1:] if (f.in_gate and f.route and f.route[0] == rs) else (f.route if f.where == rs else [])
        return f.side == "astra" and bool(ahead)

    def _hold_in_gate(self, f: Fleet, now: float) -> None:
        """The game's sky is full: the fleet waits in the Gate for a while (the March's way of saying the Gate is busy)."""
        m = self.m
        if f.in_gate:
            f.arrive_at = m.t + GATE_WAIT_S
        else:
            f.hop_from, f.where, f.route = f.where, "", [f.where]
            f.arrive_at, f.depart_at, f.status = m.t + GATE_WAIT_S, m.t, "moving"
        self.reserve[f.id] = now + GATE_WAIT_S

    def _bounce(self, f: Fleet) -> None:
        """The game would not take the fleet: it goes back the way it came (and the war goes on)."""
        m = self.m
        f.status = "ready"
        where = f.where or m.real_system
        log.warning("%s could not enter the game's system: it falls back", f.name)
        self.reserve[f.id] = self.clock() + 120.0                  # (and does not try again while it leaves)
        if f.id in m.fleets:
            m._retreat(f, where)

    async def _send(self, f: Fleet, delay: float, at_gate: bool) -> None:
        """The fleet's ships go to the game as beats (one for each four battle groups), each ship as damaged as it is."""
        try:
            groups_all = self.groups_for(f)
            kind = "raid" if f.side == "mandate" else "reinforcements"
            ok_any = False
            for i in range(0, len(groups_all), MAX_GROUPS):
                chunk = groups_all[i:i + MAX_GROUPS]
                groups, order = self.beat_groups(f, chunk, i == 0)
                beat = {"type": kind, "granted": True, "hail": False, "delay_s": round(delay + 2.0 * (i // MAX_GROUPS), 1), "groups": groups, "why": f"{f.name} comes to the Aquila's system"}
                beat.update(self.where_beat(f, at_gate))
                res = await self.command("director_beat", {"beat": {k: v for k, v in beat.items() if k not in ("why", "commander")}})
                if not res.get("ok"):
                    log.warning("the game refused %s: %s", f.name, res.get("detail"))
                    break
                ok_any = True
                ids = IDS_RE.findall(str(res.get("detail", "")))
                for idx, cid in zip(order, ids):
                    if 0 <= idx < len(f.ships):
                        f.ships[idx].cid = cid
                        self.due[cid] = self.m.t + delay + 90.0
                if self.register_groups is not None:
                    try:
                        self.register_groups(ids, groups, kind, groups[0].get("commander") or {}, beat["why"])
                    except Exception:  # noqa: BLE001
                        log.exception("the new commanders of %s could not be registered", f.name)
                self.stats["sent"] += 1
            if not ok_any:
                self.stats["refused"] += 1
                self.tries[f.id] = self.tries.get(f.id, 0) + 1
                if f.id in self.m.fleets:
                    self._bounce(f)
        except Exception:  # noqa: BLE001
            log.exception("%s could not be sent to the game", f.name)
            if f.id in self.m.fleets:
                self._bounce(f)
        finally:
            self.sending.discard(f.id)

    # ---- what a fleet is in the game: groups, ships, people
    @staticmethod
    def groups_for(f: Fleet) -> list[list[int]]:
        """The fleet's ships in battle groups (indexes into `f.ships`): the ones it has when they still fit, else carriers first and the rest behind, a few ships each."""
        n = len(f.ships)
        if f.groups and sorted(i for g in f.groups for i in g[2]) == list(range(n)) and all(len(g[2]) <= 10 for g in f.groups):
            return [list(g[2]) for g in f.groups]
        order = sorted(range(n), key=lambda i: (f.ships[i].cls not in CARRIERS, -CLASSES[f.ships[i].cls]["worth"], i))
        k = max(1, -(-n // GROUP_SHIPS))
        out: list[list[int]] = [[] for _ in range(k)]
        for j, i in enumerate(order):
            out[j % k].append(i)                                     # (each group gets its share of the capital ships and of the screen)
        return [g for g in out if g]

    def beat_groups(self, f: Fleet, chunk: list[list[int]], first: bool) -> tuple[list[dict[str, Any]], list[int]]:
        """The beat's groups for these groups of the fleet, and the fleet's ship index of each ship in the order the game will number them."""
        order: list[int] = []
        groups: list[dict[str, Any]] = []
        names = f.groups if f.groups and len(f.groups) == len(chunk) else None
        for gi, idxs in enumerate(chunk):
            ships = []
            wings = []
            for k, i in enumerate(idxs):
                s = f.ships[i]
                spec: dict[str, Any] = {"class": s.cls, "name": s.name}
                if s.hull < 0.97:
                    spec["hull_pct"] = max(5, int(round(100.0 * s.hull)))
                if f.supply < 0.85:
                    spec["missiles"] = max(0, int(CLASSES[s.cls]["missiles"] * min(1.0, 0.1 + f.supply)))
                if f.side == "astra":
                    cap = self.person(f, s)
                    if cap:
                        spec["captain"] = cap
                ships.append(spec)
                order.append(i)
                for kind, n, mission in (("fighter", s.fighters, "strike" if f.side == "mandate" else "cap"), ("bomber", s.bombers, "strike"), ("drone", s.drones, "cap")):
                    if n >= 1 and s.cls in CARRIERS:
                        wings.append({"carrier": k, "kind": kind, "n": int(round(n)), "mission": mission})
            name = names[gi][0] if names else (f.name if len(chunk) == 1 else f"{f.name} {gi + 1}")
            g: dict[str, Any] = {"name": name, "formation": (names[gi][1] if names else ("wedge" if f.side == "mandate" else "line")), "ships": ships, "wings": wings,
                                 "offset_km": [[0, 0], [2, -6], [2, 6], [-4, 0]][gi % 4]}
            if f.side == "mandate":
                g["goes_for"] = self.goes_for(f, gi if first else gi + 1)
                lead = self.leader(f, gi if first else gi + 1)
                if lead:
                    g["commander"] = {**lead, "orders": f.order.reason or f"{f.order.kind} {f.order.target}".strip()}
            groups.append(g)
        return groups, order

    @staticmethod
    def goes_for(f: Fleet, gi: int) -> str:
        """Where a Mandate group points when it comes in: a fleet that stands to hold its ground goes for the Gate, one that attacks goes for the Aquila and its screen for her
        consorts (the commanders in the field decide the rest, with their plan in front of them)."""
        if f.order.kind in ("defend", "hold", "blockade", "refit", "withdraw"):
            return "gate"
        return "aquila" if gi == 0 else "escorts"

    def leader(self, f: Fleet, gi: int) -> dict[str, Any]:
        """The person who leads a Mandate group: the fleet's commander for the first, the next free person of the pool for the others."""
        if gi == 0 and f.commander.get("name"):
            c = f.commander
            return {"name": c["name"], "rank": c.get("rank", "Ferryman (ship captain)"), "bio": c.get("bio", ""), "voice": c.get("voice", ""), "gender": c.get("gender", "m")}
        used = {g.commander.get("name") for g in self.m.fleets.values() if g.commander.get("name")}
        free = [p for p in MANDATE_PEOPLE if p["name"] not in used]
        if not free:
            return {}
        p = free[(sum(map(ord, f.id)) + gi) % len(free)]
        return {"name": p["name"], "rank": p["rank"], "bio": p["bio"], "voice": p.get("voice", ""), "gender": p.get("gender", "m")}

    def person(self, f: Fleet, ship: Ship) -> dict[str, Any]:
        """An ASTRA ship's captain: the one it has had (the same ship, the same person), else the next free one of the pool; none when the pool is out (the war minds draw)."""
        pool = {p["name"]: p for p in ASTRA_PEOPLE}
        name = ship.captain if ship.captain in pool else ""
        if not name:
            taken = {s.captain for g in self.m.fleets.values() if g.side == "astra" for s in g.ships if s.captain}
            free = [p["name"] for p in ASTRA_PEOPLE if p["name"] not in taken]
            if not free:
                return {}
            name = free[sum(map(ord, ship.name)) % len(free)]
            ship.captain = name
        p = pool[name]
        return {"name": p["name"], "rank": p["rank"], "bio": p["bio"], "gender": p.get("gender", "m"), "voice": p.get("voice", "")}

    def where_beat(self, f: Fleet, at_gate: bool) -> dict[str, Any]:
        """Where in the game's sky the fleet appears: at the Gate's mouth when it comes through (or stands there), on the far side over the world otherwise."""
        if self.gate:
            bearing, km = self.gate
            if at_gate:
                return {"bearing_deg": round(bearing, 1), "range_km": round(max(8.0, km - 4.0), 1)}
            return {"bearing_deg": round((bearing + 180.0) % 360.0, 1), "range_km": 30.0}
        return {"bearing_deg": float(sum(map(ord, f.id)) * 37 % 360), "range_km": 40.0 if f.side == "mandate" else 20.0}

    # ------------------------------------------------------------------------------------------------ out: what became of the ships
    def _read_back(self, state: dict[str, Any]) -> None:
        m, rs = self.m, self.m.real_system
        if not rs:
            return
        alive, gone = ships_of(state)
        for f in list(m.fleets.values()):
            if f.status != "real":
                continue
            for ship in list(f.ships):
                cid = ship.cid
                if not cid:
                    continue
                row = alive.get(cid)
                if row is not None:
                    self.seen.add(cid)
                    if row.get("hull_pct") is not None:
                        m.real_hull(ship, float(row["hull_pct"]) / 100.0)
                    continue
                how = gone.get(cid) or (self.fate.get(cid, "destroyed") if cid in self.seen else "")
                if not how and m.t > self.due.get(cid, 1e18):
                    f.ships.remove(ship)                              # (it never came: the game left it out; nothing was lost)
                    log.warning("%s never showed in the game (%s): left out", ship.name, cid)
                    if not f.ships:
                        m._remove_fleet(f)
                    continue
                if how:
                    m.real_lost(f, ship, "fled" if how == "fled" else "destroyed")
                    self.stats["fled" if how == "fled" else "lost"] += 1
        fight = self._fight(state, alive)
        now = self.clock()
        if fight and not m.real_fight:
            m.real_fight, m.real_t0 = True, m.t
            self._fight_off_t = None
            m.say("battle_start", rs, {s: f"The Aquila's fight at {rs} is joined." for s in SIDES}, SIDES, 1)
        elif not fight and m.real_fight:
            self._fight_off_t = self._fight_off_t or now
            if now - self._fight_off_t > 90.0:                            # (the game did not say it is over: it is)
                m.real_over(rs, "")
                self._fight_off_t = None
        elif fight:
            self._fight_off_t = None

    @staticmethod
    def _fight(state: dict[str, Any], alive: dict[str, dict[str, Any]]) -> bool:
        """Is there a fight in the game's system: a hostile ship under way that is not breaking off."""
        for c in state.get("contacts") or []:
            st = str(c.get("status", ""))
            if st.startswith("hostile") and "retreating" not in st and "disabled" not in st:
                return True
        for s in (state.get("_mandate") or {}).get("your_ships") or []:
            if str(s.get("state", "")) == "attacking":
                return True
        return False

    def on_event(self, text: str) -> bool:
        """Every event the game sends (the server hands them over): what the game says of its ships' fates, and the end of the fight. True: a major battle was just fought
        and the story may end a chapter with it."""
        if not self.active:
            return False
        mt = FATE_RE.search(text)
        if mt:
            if "left sensor range" in text:
                self.fate[mt.group(1)] = "fled"
            elif "destroyed" in text:
                self.fate[mt.group(1)] = "destroyed"
        if text.startswith("director:") and "engagement over" in text and self.m.real_system:
            result = text.split("—", 1)[-1].split(";")[0].strip()
            weight = self.m.real_over(self.m.real_system, result)
            self._fight_off_t = None
            if weight >= 3 and self.m.t - self._arc_t >= ARC_GAP_S:
                self._arc_t = self.m.t
                return True
        return False

    def _tell_the_end(self) -> None:
        """The war of the March has ended: the story ends its last chapter with it (the finale is told from what really happened)."""
        over = self.m.over
        winner = {"astra": "ASTRA has won", "mandate": "the Mandate has won"}.get(over.get("winner", ""), "an armistice: neither side has won")
        text = f"engagement over — the war of the Aurelia March is over: {over.get('why', '')} ({over.get('how', '')}; {winner})"
        log.info("the war is over: %s", over)
        self.note(f"THE WAR IS OVER: {over.get('why', '')}")
        if self.on_war_over is not None:
            try:
                self.on_war_over(text)
            except Exception:  # noqa: BLE001
                log.exception("the end of the war could not be told")

    # ------------------------------------------------------------------------------------------------ Fleet's orders to the Aquila
    async def _task_aquila(self, system: str, mission: str) -> dict[str, Any]:
        """Fleet orders the Aquila to a system: Keeper Station tunes the Gate for the first jump of her way (the game takes one Gate at a time)."""
        m = self.m
        here = m.aquila["where"]
        if m.aquila["lane"] or system == here:
            return {"ok": True, "detail": "she is there or on her way"}
        path = m.path(here, system, "astra") or []
        hop = path[0] if path else system
        self._transit = {"dest": system, "t": m.t, "next": 0.0, "tuned": ""}
        res = await self._transit_beat(hop)
        return {"ok": bool(res.get("ok")), "detail": ("the Gate is tuned for her" + (f" (first jump: {hop})" if hop != system else "")) if res.get("ok")
                else f"the Gate cannot be tuned yet: {str(res.get('detail', ''))[:90]} (Fleet will try again)"}

    async def _transit_beat(self, hop: str) -> dict[str, Any]:
        s = self.m.war.systems.get(hop) or {}
        res = await self.command("director_beat", {"beat": {"type": "transit", "system_name": hop, "star_class": s.get("star", ""), "planet_type": s.get("planet", ""),
                                                           "planet_name": s.get("world", "")}})
        if res.get("ok") and self._transit is not None:
            self._transit["tuned"] = hop
        return res

    def _transit_again(self, now: float) -> None:
        """Fleet's order to the Aquila stands: while she has not gone and the Gate was not tuned (an engagement under way refuses it), Fleet tries again."""
        t = self._transit
        if not t or self.m.t < t["next"]:
            return
        t["next"] = self.m.t + 20.0
        if self.m.aquila["lane"] or self.m.aquila["where"] == t["dest"] or self.m.t - t["t"] > 900.0:
            self._transit = None
            return
        hop = (self.m.path(self.m.aquila["where"], t["dest"], "astra") or [t["dest"]])[0]
        if t["tuned"] != hop:
            asyncio.ensure_future(self._transit_beat(hop))

    async def _tender(self) -> dict[str, Any]:
        res = await self.command("director_beat", {"beat": {"type": "resupply", "hull_pct": 85, "missiles": 24, "duration_s": 150, "delay_s": 45, "granted": True}})
        return {"ok": bool(res.get("ok")), "detail": "a tender is on its way to her" if res.get("ok") else str(res.get("detail", ""))[:100]}

    # ------------------------------------------------------------------------------------------------ the story: bulletins, the holo table, saving
    def _bulletins(self, now: float) -> None:
        """What reaches ASTRA's high command of the war goes to the bridge, not all of it: the war beyond the Aquila's sky, and the Gate's warning of what is coming."""
        m = self.m
        news = m.news("astra", self._bul_seen)
        self._bul_seen = m.rcv["astra"]
        said = [e for e in news if self._worth_saying(e)]
        if said:
            self._pending = (self._pending + [(e.kind, e.text["astra"]) for e in said])[-4:]
        # while the guns are firing the bridge hears only what cannot wait: a Gate cycling, a fall, the end of the war; the rest waits for the lull
        urgent = any(k in ("wake", "system_taken", "war_over", "truce") for k, _ in self._pending)
        if self._pending and now - self._bul_t >= BULLETIN_GAP_S and self.announce is not None and (urgent or not self.m.real_fight):
            text, self._pending = " / ".join(t for _, t in self._pending), []
            self._bul_t = now
            self.stats["bulletins"] += 1
            asyncio.ensure_future(self.announce(text))

    def _worth_saying(self, e: Any) -> bool:
        if not e.text.get("astra"):
            return False
        if e.system == self.m.real_system and e.kind in OWN_SKY_KINDS:
            return False
        return e.weight >= 3 or (e.weight >= 2 and e.kind in BULLETIN_KINDS)

    def _holo(self, now: float) -> None:
        if self.send_sector is not None and now - self._holo_t >= HOLO_EVERY_S:
            self._holo_t = now
            asyncio.ensure_future(self.send_sector())

    def _save(self, now: float) -> None:
        if now - self._save_t >= SAVE_EVERY_S:
            self._save_t = now
            self.save()

    def save(self) -> None:
        """The war and its high commands' memory go to the campaign's folder (the March saves itself when it changes; the minds' log with it)."""
        m = self.m
        m.save()
        if self.minds is None:
            return
        path = os.path.join(os.path.dirname(m.default_path()), "strategy.json")
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.minds.save_state(), f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
        except OSError:
            log.exception("could not save the high commands' log")

    def load(self) -> bool:
        m = self.m
        ok = m.load()
        if self.minds is not None:
            path = os.path.join(os.path.dirname(m.default_path()), "strategy.json")
            try:
                with open(path, encoding="utf-8") as f:
                    self.minds.load_state(json.load(f))
            except (OSError, ValueError):
                pass
        return ok

    # ------------------------------------------------------------------------------------------------ the war goes on without her
    async def fast_forward(self, hours: float = FF_HOURS) -> None:
        """The Aquila is lost and the Captain is away (the weeks the story skips): the war goes on, both sides on their reflexes in full, a few seconds of work for the
        hours of war time; the new Aquila then finds the March as it has become."""
        m = self.m
        self.ff = True
        try:
            m.release_real()
            autos = dict(self.minds.autos) if self.minds is not None else {}
            if not autos:
                autos = {s: AutoAdmiral(m, s, "full") for s in SIDES}
            end = m.t + hours * 3600.0
            n = 0
            while m.t < end and not m.over:
                m.run(30.0)
                for a in autos.values():
                    a.level = "full"
                    if n % 3 == 0:
                        a.think()
                n += 1
                if n % 4 == 0:
                    await asyncio.sleep(0)
            self.reset_real()
            m.real_system = m.aquila["where"]
            m.real_fight = False
            log.info("the war went on for %.1f hours without the Aquila: %s", hours, m.clock())
        finally:
            self.ff = False

    # ------------------------------------------------------------------------------------------------ for Rourke on the fleet net
    async def rourke_reply(self, words: str, lang: str = "") -> list[str]:
        if self.minds is None:
            return []
        return await self.minds.rourke_reply(words, lang)

    def summary(self) -> dict[str, Any]:
        out = {"glue": dict(self.stats), "march": {"t": round(self.m.t), "will": {s: round(self.m.will[s], 2) for s in SIDES}, "score": self.m.score,
                                                   "over": self.m.over.get("why", "")}}
        if self.minds is not None:
            out["strategy"] = self.minds.summary()
        return out
