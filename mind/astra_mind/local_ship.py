"""A minimal ship model used when the game is not connected (tests, the text console) — the game's
UAstraShipSubsystem is the real, authoritative implementation of the same tools.

With `stations=True` (the default) it also has live consoles like the ones of docs/contratto_postazioni.md: every
station keeps its modes per lane, the modes have plausible simple effects (the helm turns and closes, tactical fires
and kills, the viewscreen follows its target and is released when the target is lost...) and `advance(seconds)` runs a
small fight — contacts that manoeuvre, a new contact that appears, targets that are destroyed — reporting what the
executors would report (`ship.reports`). With `stations=False` it is the old build: no `stations` in the state and
the `station` command unknown, so the mind's fallback to the legacy tools can be tested."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Any

from . import stations as station_model

INITIAL: dict[str, Any] = {
    "ship": "ASN Aquila", "location": "Aurelia System, 180,000 km from New Ravenna, en route to high orbit",
    "alert": "green", "heading_deg": 45, "mark_deg": 0, "throttle_pct": 60, "speed_mps": 412,
    "reactor_pct": 78,
    "power_pct": {"shields": 100, "weapons": 100, "engines": 100, "sensors": 100, "life_support": 100, "flight_deck": 100},
    "shields": {"state": "up", "mode": "balanced", "fore": 100, "aft": 100, "port": 100, "starboard": 100, "dorsal": 100, "ventral": 100},
    "weapons": {"railguns": "ready (4 twin turrets)", "lasers": "ready (12 batteries)", "missiles": "ready (96 in VLS)",
                "torpedoes": "ready (2 loaded)", "point_defense": "auto"},
    "target": None, "emcon": "restricted",
    "thermal": {"heat_pct": 12, "trend": "steady", "radiators": "retracted", "coolant_vents": 3, "status": "nominal"},
    "squadrons": {"alpha": "on deck, ready (8 Falcons)", "bravo": "on deck, ready (7 of 8 Hammers)", "drones": "ready (12 Wasps)"},
    "damage": [],
    "contacts": [
        {"id": "T-01", "class": "ASTRA battleship", "name": "ASN Praetorian (7th Fleet flagship)", "range_km": 12, "bearing_deg": 20, "status": "friendly"},
        {"id": "T-02", "class": "ASTRA destroyer", "name": "ASN Vigilant", "range_km": 18, "bearing_deg": 80, "status": "friendly"},
        {"id": "T-07", "class": "freighter", "name": "Free Guilds hauler Brightwater", "range_km": 67, "bearing_deg": 310, "status": "neutral"},
        {"id": "T-11", "class": "unknown", "name": None, "range_km": 50, "bearing_deg": 200, "status": "unidentified, cold drive, drifting"},
    ],
}

# the lane each station starts in
DEFAULT_LANES: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
    "helm": {"nav": ("hold", {})},
    "tactical": {"engagement": ("return_fire", {}), "shields": ("shields_balanced", {}), "point_defense": ("pd_auto", {}),
                 "missiles": ("missiles_normal", {})},
    "sensors": {"emcon": ("emcon", {"level": "restricted"}), "scan": ("scan_passive", {}), "ew": ("ew_off", {}),
                "sigint": ("sigint_off", {})},
    "ops": {"viewscreen": ("viewscreen_auto", {}), "holo": ("holo_tactical", {}), "damage_control": ("dc_auto", {})},
    "engineering": {"power": ("power_profile", {"profile": "balanced"}), "heat": ("heat_auto", {"limit_pct": 70}),
                    "reactor": ("reactor_normal", {})},
    "comms": {"channel": ("channel_unmute", {}), "listen": ("listen_off", {})},
    "flight": {"alpha": ("mission", {"squadron": "alpha", "type": "hold"}), "bravo": ("mission", {"squadron": "bravo", "type": "hold"}),
               "drones": ("mission", {"squadron": "drones", "type": "hold"})},
    "xo": {},
}
LANE_OF_MODE = {name: md.lane for name, md in station_model.MODE_INDEX.items()}
RAIL_KM, LASER_KM, RAIL_PCT_S, LASER_PCT_S = 10.0, 4.0, 2.4, 1.6      # a railgun volley every 7 s is ~2.4 %/s on average here


@dataclass
class Contact:
    id: str
    name: str | None
    cls: str
    status: str                       # friendly | neutral | hostile | unidentified, cold drive, drifting | bearing only
    x: float                          # km, east
    y: float                          # km, north
    speed: float = 0.0                # m/s
    heading: float = 0.0              # true bearing the contact moves along
    hull: float = 100.0
    shields: float = 100.0
    behaviour: str = "hold"           # hold | approach | circle | flee
    standoff: float = 8.0
    firing: bool = False              # it is shooting at us
    classified: bool = True           # False: only a bearing (no range in the plot)
    alive: bool = True
    cruise: float = 0.0               # its nominal speed (m/s), for the behaviours that move it

    def __post_init__(self) -> None:
        if not self.cruise:
            self.cruise = self.speed

    def as_json(self, ship: "LocalShip") -> dict[str, Any]:
        rng, brg = ship.range_bearing(self)
        d: dict[str, Any] = {"id": self.id, "class": self.cls if self.classified else "unknown", "bearing_deg": round(brg),
                             "mark_deg": 0}
        if self.name and self.classified:
            d["name"] = self.name
        if not self.classified:
            d["status"] = ("bearing only (passive, faint drive emissions): no range, no firing solution — an active scan, "
                           "EMCON full, a recon flight or closing in would give a track")
            return d
        d["status"] = self.status
        d["range_km"] = round(rng, 1)
        if "cold" not in self.status:
            d["speed_mps"] = round(self.speed)
            d["shields_pct"] = round(self.shields)
            d["hull_pct"] = round(self.hull)
        return d


def _wrap(a: float) -> float:
    return a % 360.0


def _delta(a: float, b: float) -> float:
    """Signed shortest turn from a to b."""
    return (b - a + 540.0) % 360.0 - 180.0


class LocalShip:
    def __init__(self, stations: bool = True, fight: bool = False) -> None:
        self.state = copy.deepcopy(INITIAL)
        self.events: list[str] = []
        self.reports: list[str] = []          # what the executors would report to the mind (event report=True)
        self.stations_on = stations
        self.t = 0.0
        self.x = self.y = 0.0
        self.heading = float(self.state["heading_deg"])
        self.speed = float(self.state["speed_mps"])
        self.contacts: dict[str, Contact] = {}
        self.channel: dict[str, Any] | None = None     # {party, open} — the mind's view (the game keeps it in comms)
        self.log: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []     # (by, command, args, result) — for the tests
        self.lanes: dict[str, dict[str, dict[str, Any]]] = {}
        self.delegation: dict[str, str] = {s: "auto" for s in station_model.STATIONS if s != "xo"}
        self.last_actions: dict[str, list[str]] = {s: [] for s in station_model.STATIONS}
        self._script: list[tuple[float, str, Any]] = []
        self._focus_t: dict[str, float] = {}
        self.helm_note = ""                   # the helm's own line when a legacy command (a gate transit) has it
        for sid, lanes in DEFAULT_LANES.items():
            self.lanes[sid] = {lane: {"mode": m, "params": dict(p), "until": "order", "set_by": "auto", "since": 0.0, "status": ""}
                               for lane, (m, p) in lanes.items()}
        if fight:
            self.setup_fight()
        else:
            for c in self.state["contacts"]:
                rng, brg = c["range_km"], math.radians(c["bearing_deg"])
                self.contacts[c["id"]] = Contact(c["id"], c.get("name"), c["class"], c["status"], rng * math.sin(brg), rng * math.cos(brg),
                                                 classified=True)

    # ------------------------------------------------------------------------------------------------ the fight
    def setup_fight(self) -> None:
        """A raid on the picket: two Mandate destroyers closing (one will manoeuvre), our escorts, and — later — a third
        contact that appears out of the dark. The timeline is in `_script` and runs with advance()."""
        self.state.update(alert="red", throttle_pct=0, speed_mps=0, heading_deg=45)
        self.speed = 0.0
        self.contacts.clear()

        def add(c: Contact) -> None:
            self.contacts[c.id] = c

        def polar(rng: float, brg: float) -> tuple[float, float]:
            return rng * math.sin(math.radians(brg)), rng * math.cos(math.radians(brg))

        add(Contact("T-01", "ASN Praetorian (7th Fleet flagship)", "ASTRA battleship", "friendly", *polar(12, 20), behaviour="hold"))
        add(Contact("T-02", "ASN Vigilant", "ASTRA destroyer", "friendly", *polar(18, 80), behaviour="hold"))
        add(Contact("T-23", "Cocytus", "Mandate destroyer", "hostile", *polar(15, 70), speed=300, behaviour="approach",
                    standoff=8.0, firing=True))
        add(Contact("T-24", "Phlegethon", "Mandate destroyer", "hostile", *polar(20, 100), speed=280, behaviour="approach",
                    standoff=9.0))
        # (time s, kind, payload): the timeline
        self._script = [
            (18.0, "circle", "T-24"),                                   # the Phlegethon starts circling: a bearing that moves
            (40.0, "appear", Contact("T-31", "Avernus", "Mandate cruiser", "hostile", *polar(34, 335), speed=260,
                                     behaviour="approach", standoff=12.0, classified=False)),
            (75.0, "fire", "T-24"),
        ]
        self._sync_legacy()

    def add_contact(self, c: Contact) -> None:
        self.contacts[c.id] = c

    # ------------------------------------------------------------------------------------------------ geometry
    def range_bearing(self, c: Contact) -> tuple[float, float]:
        dx, dy = c.x - self.x, c.y - self.y
        return math.hypot(dx, dy), _wrap(math.degrees(math.atan2(dx, dy)))

    def _contact(self, cid: Any) -> Contact | None:
        s = str(cid or "").lower()
        return next((c for c in self.contacts.values() if c.alive and c.id.lower() == s), None)

    def _resolve(self, ref: Any) -> Contact | None:
        """A target reference: a contact id or a selector."""
        r = str(ref or "").strip()
        hostile = [c for c in self.contacts.values() if c.alive and c.status.startswith("hostile") and c.classified]
        if r == "nearest_hostile":
            return min(hostile, key=lambda c: self.range_bearing(c)[0], default=None)
        if r == "biggest_threat":
            return next((c for c in hostile if c.firing), min(hostile, key=lambda c: self.range_bearing(c)[0], default=None))
        if r == "tactical_target":
            eng = self.lanes["tactical"]["engagement"]
            for t in (eng["params"].get("targets") or []) if eng["mode"] == "engage" else []:
                c = self._contact(t)
                if c:
                    return c
            return None
        return self._contact(r)

    # ------------------------------------------------------------------------------------------------ events
    def _emit(self, text: str, report: bool = True) -> None:
        self.events.append(text)
        if report:
            self.reports.append(text)

    def take_reports(self) -> list[str]:
        out, self.reports = self.reports, []
        return out

    def snapshot(self) -> dict[str, Any]:
        s = self.state
        s["heading_deg"], s["speed_mps"] = round(self.heading) % 360, round(self.speed)
        if self.contacts:
            s["contacts"] = [c.as_json(self) for c in self.contacts.values() if c.alive]
        self._sync_legacy()
        if self.stations_on:
            s["sim_time_s"] = round(self.t, 1)
            s["stations"] = self._stations_json()
        return s

    def recent_events(self) -> list[str]:
        return self.events[-8:]

    # ------------------------------------------------------------------------------------------------ the consoles
    def _set_lane(self, station: str, mode: str, params: dict[str, Any], until: str, by: str) -> str:
        lane = LANE_OF_MODE.get(mode, "main")
        if station == "flight":
            lane = str(params.get("squadron", "alpha"))
        self.lanes[station][lane] = {"mode": mode, "params": dict(params), "until": until, "set_by": by, "since": round(self.t, 1),
                                     "status": ""}
        note = f"{mode}" + (f" {params}" if params else "")
        self.last_actions[station] = (self.last_actions[station] + [f"{by}: {note}"])[-4:]
        return lane

    def _reset_lane(self, station: str, lane: str) -> None:
        if lane in DEFAULT_LANES[station]:
            m, p = DEFAULT_LANES[station][lane]
            self.lanes[station][lane] = {"mode": m, "params": dict(p), "until": "order", "set_by": "auto", "since": round(self.t, 1),
                                         "status": ""}

    def _lane_status(self, station: str, lane: str, ls: dict[str, Any]) -> str:
        m, p = ls["mode"], ls["params"]
        if station == "helm":
            tgt = self._resolve(p.get("target"))
            if m in ("intercept", "keep_on_bow", "follow", "broadside", "orbit") and tgt:
                rng, brg = self.range_bearing(tgt)
                if m == "keep_on_bow":
                    return f"bow on {tgt.id} (bearing {brg:03.0f}, {rng:.1f} km), speed {self.speed:.0f} m/s"
                return f"{m} {tgt.id} at {rng:.1f} km, {self.speed:.0f} m/s" + (
                    f", ETA {int(max(0, rng - float(p.get('standoff_km', 6))) * 1000 / max(self.speed, 1))} s" if m == "intercept" else "")
            if m == "course":
                return f"heading {self.heading:03.0f}, ordered {p.get('heading_deg', 0):03.0f}"
            return f"steady on {self.heading:03.0f} at {self.speed:.0f} m/s"
        if station == "tactical" and lane == "engagement":
            if m == "engage":
                tg = [t for t in (p.get("targets") or []) if self._resolve(t)]
                if not tg:
                    return "no target left"
                c = self._resolve(tg[0])
                rng = self.range_bearing(c)[0]
                return f"engaging {c.id} at {rng:.1f} km ({'in range' if rng <= RAIL_KM else 'waiting: out of railgun reach'}), its hull {c.hull:.0f}%"
            return m.replace("_", " ")
        if station == "ops" and lane == "viewscreen":
            return m.replace("viewscreen_", "") + (f" on {p.get('target')}" if p.get("target") else "")
        if station == "sensors" and lane == "scan" and m == "scan_focus":
            return f"focused on {p.get('target')}"
        return ""

    def _stations_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for sid, lanes in self.lanes.items():
            ls_out = {}
            for lane, ls in lanes.items():
                ls_out[lane] = {**ls, "status": self._lane_status(sid, lane, ls)}
            out[sid] = {"officer": sid, "delegation": self.delegation.get(sid, "auto"), "lanes": ls_out,
                        "last_actions": list(self.last_actions.get(sid, []))}
        return out

    def _sync_legacy(self) -> None:
        """The old flat fields the crew and the tactical advisor read (as the game writes them)."""
        s = self.state
        h = self.lanes["helm"]["nav"]
        tgt = self._resolve(h["params"].get("target")) if h["mode"] in ("intercept", "keep_on_bow", "follow", "broadside", "orbit") else None
        if tgt and h["mode"] == "intercept":
            rng, _ = self.range_bearing(tgt)
            s["helm"] = (f"intercepting {tgt.id}, range {rng:.1f} km, {'broadside, holding the range' if rng < float(h['params'].get('standoff_km', 6)) else 'closing'}"
                         f" (standoff {h['params'].get('standoff_km', 6)} km); course follows the target")
        elif self.helm_note:
            s["helm"] = self.helm_note
        else:
            s.pop("helm", None)
        eng = self.lanes["tactical"]["engagement"]
        w = s["weapons"]
        w["railguns"] = "ready, 4 twin turrets, range 10 km, one volley every 7 s"
        if eng["mode"] == "engage":
            c = next((self._resolve(t) for t in eng["params"].get("targets", []) if self._resolve(t)), None)
            if c:
                rng = self.range_bearing(c)[0]
                w["railguns"] = (f"engaging {c.id}, 12 volleys left, next in 3 s" if rng <= RAIL_KM else
                                 f"assigned to {c.id}, waiting for it to close inside 10 km (now {rng:.0f} km), 12 volleys queued")
        s["target"] = self.state.get("target")
        sh = self.lanes["tactical"]["shields"]
        s["shields"]["mode"] = {"shields_balanced": "balanced", "shields_face_threat": "face_threat", "shields_sector": str(sh["params"].get("sector", "fore")),
                                "shields_off": "off"}.get(sh["mode"], s["shields"]["mode"])
        s["weapons"]["point_defense"] = {"pd_auto": "auto", "pd_protect": "auto", "pd_off": "hold"}.get(self.lanes["tactical"]["point_defense"]["mode"], "auto")
        s["emcon"] = str(self.lanes["sensors"]["emcon"]["params"].get("level", s["emcon"]))

    # ------------------------------------------------------------------------------------------------ the simulation
    def advance(self, seconds: float, step: float = 1.0) -> None:
        """Run the fight forward. Reports for the mind pile up in `reports`."""
        left = seconds
        while left > 1e-9:
            dt = min(step, left)
            left -= dt
            self._tick(dt)

    def _tick(self, dt: float) -> None:
        self.t += dt
        # the timeline
        for item in [i for i in self._script if i[0] <= self.t]:
            self._script.remove(item)
            _, kind, payload = item
            if kind == "appear":
                self.contacts[payload.id] = payload
                self._emit(f"sensors: new contact {payload.id}, bearing {self.range_bearing(payload)[1]:03.0f}, faint drive emissions (bearing only)")
            elif kind == "circle" and self._contact(payload):
                self._contact(payload).behaviour = "circle"
            elif kind == "fire" and self._contact(payload):
                self._contact(payload).firing = True
                self._emit(f"tactical: {payload} opens fire on the Aquila")
        # the contacts
        for c in list(self.contacts.values()):
            if not c.alive:
                continue
            rng, brg = self.range_bearing(c)
            if c.behaviour == "approach":
                c.heading, c.speed = _wrap(brg + 180), (c.cruise if rng > c.standoff else 0.0)
            elif c.behaviour == "circle":
                c.heading, c.speed = _wrap(brg + 90), c.cruise
            elif c.behaviour == "flee":
                c.heading, c.speed = brg, c.cruise
            else:
                c.speed = 0.0
            c.x += math.sin(math.radians(c.heading)) * c.speed * dt / 1000.0
            c.y += math.cos(math.radians(c.heading)) * c.speed * dt / 1000.0
        # the helm
        self._tick_helm(dt)
        # tactical fire
        self._tick_fire(dt)
        # the ends of the modes
        self._tick_release()

    def _tick_helm(self, dt: float) -> None:
        h = self.lanes["helm"]["nav"]
        m, p = h["mode"], h["params"]
        want_h, want_speed = None, None
        tgt = self._resolve(p.get("target")) if m in ("intercept", "keep_on_bow", "follow", "broadside", "orbit") else None
        if m == "intercept" and tgt:
            rng, brg = self.range_bearing(tgt)
            st = float(p.get("standoff_km", 6))
            want_h = brg if rng > st else _wrap(brg + 90)
            want_speed = 480.0 * float(p.get("speed_pct", 100)) / 100 if rng > st + 0.5 else 0.0
        elif m == "keep_on_bow" and tgt:
            want_h = self.range_bearing(tgt)[1]
        elif m in ("follow", "orbit", "broadside") and tgt:
            rng, brg = self.range_bearing(tgt)
            want_h = brg if rng > float(p.get("distance_km", p.get("range_km", p.get("radius_km", 6)))) else _wrap(brg + 90)
            want_speed = 300.0
        elif m == "course":
            want_h = float(p.get("heading_deg", self.heading))
            want_speed = 480.0 * float(p["speed_pct"]) / 100 if "speed_pct" in p else None
            if abs(_delta(self.heading, want_h)) < 0.1:
                self._set_hold_after_course()
        elif m == "retreat":
            hostile = self._resolve("nearest_hostile")
            want_h = _wrap(self.range_bearing(hostile)[1] + 180) if hostile else self.heading
            want_speed = 480.0
        elif m == "evade":
            want_h = _wrap(self.heading + 30 * math.sin(self.t / 2))
        elif m == "hold" and "speed_pct" in p:
            want_speed = 480.0 * float(p["speed_pct"]) / 100
        if want_h is not None:
            self.heading = _wrap(self.heading + max(-1.5 * dt, min(1.5 * dt, _delta(self.heading, want_h))))
        if want_speed is not None:
            self.speed += max(-40 * dt, min(40 * dt, want_speed - self.speed))
        self.x += math.sin(math.radians(self.heading)) * self.speed * dt / 1000.0
        self.y += math.cos(math.radians(self.heading)) * self.speed * dt / 1000.0

    def _set_hold_after_course(self) -> None:
        h = self.lanes["helm"]["nav"]
        if h["mode"] == "course" and h.get("until") == "done":
            self._emit(f"helm: turn complete, steady on course {self.heading:03.0f}")
            self._reset_lane("helm", "nav")

    def _tick_fire(self, dt: float) -> None:
        eng = self.lanes["tactical"]["engagement"]
        shooters: list[Contact] = []
        if eng["mode"] == "engage":
            for t in eng["params"].get("targets", []):
                if t == "hostiles":
                    shooters = [c for c in self.contacts.values() if c.alive and c.status.startswith("hostile") and c.classified]
                else:
                    c = self._resolve(t)
                    if c:
                        shooters.append(c)
                if shooters:
                    break
        elif eng["mode"] == "weapons_free":
            rng_cap = float(eng["params"].get("range_km", RAIL_KM))
            shooters = [c for c in self.contacts.values() if c.alive and c.status.startswith("hostile") and c.classified
                        and self.range_bearing(c)[0] <= rng_cap]
        elif eng["mode"] == "return_fire":
            shooters = [c for c in self.contacts.values() if c.alive and c.firing and c.classified]
        if not shooters or self.state["power_pct"]["weapons"] < 5:
            return
        c = min(shooters, key=lambda x: self.range_bearing(x)[0]) if eng["params"].get("priority") == "nearest" else shooters[0]
        rng = self.range_bearing(c)[0]
        rate = (RAIL_PCT_S if rng <= RAIL_KM else 0.0) + (LASER_PCT_S if rng <= LASER_KM else 0.0)
        if rate:
            c.hull -= rate * dt * self.state["power_pct"]["weapons"] / 100
            if c.hull <= 0:
                c.alive = False
                self._emit(f"tactical: {c.id} ({c.name}) destroyed")

    def _tick_release(self) -> None:
        """The modes that end with their target: the console returns to its default and reports."""
        h = self.lanes["helm"]["nav"]
        if h["mode"] in ("intercept", "keep_on_bow", "follow", "broadside", "orbit") and h.get("until") == "target_lost" \
                and not self._resolve(h["params"].get("target")):
            self._emit(f"helm: {h['mode']} of {h['params'].get('target')} ended, the contact is gone — holding course {self.heading:03.0f}")
            self._reset_lane("helm", "nav")
        eng = self.lanes["tactical"]["engagement"]
        if eng["mode"] == "engage" and not any(self._resolve(t) for t in eng["params"].get("targets", [])) and \
                "hostiles" not in eng["params"].get("targets", []):
            self._emit(f"tactical: engage complete — {', '.join(eng['params'].get('targets', []))} destroyed or lost, back to return fire")
            self._reset_lane("tactical", "engagement")
        vs = self.lanes["ops"]["viewscreen"]
        if vs["mode"] == "viewscreen_target" and not self._resolve(vs["params"].get("target")):
            self._emit(f"ops: viewscreen released — {vs['params'].get('target')} lost, back to auto")
            self._reset_lane("ops", "viewscreen")
        sc = self.lanes["sensors"]["scan"]
        if sc["mode"] == "scan_focus":
            c = self._contact(sc["params"].get("target"))
            t0 = self._focus_t.setdefault(str(sc["params"].get("target")), self.t)
            if c and self.t - t0 >= 6 and not c.classified:
                c.classified = True
                self._emit(f"sensors: {c.id} identified — {c.cls} {c.name}, {self.range_bearing(c)[0]:.0f} km, bearing {self.range_bearing(c)[1]:03.0f}")
                self._reset_lane("sensors", "scan")
            elif not c:
                self._reset_lane("sensors", "scan")

    # ------------------------------------------------------------------------------------------------ commands
    async def execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        res = self._execute(name, a, by)
        self.log.append((by, name, dict(a), res))
        return res

    def _execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        s = self.state
        if name == "station":
            return self._station(a, by)
        if name == "set_course":
            s["heading_deg"], s["mark_deg"] = round(a["heading_deg"]) % 360, round(a["mark_deg"])
            self.heading = float(s["heading_deg"])              # (the old build turned instantly for the tests)
            self.helm_note = ""
            self._reset_lane("helm", "nav")                       # a set_course cancels an intercept
            return self._ok(f"coming to {s['heading_deg']:03d} mark {s['mark_deg']}")
        if name == "set_throttle":
            s["throttle_pct"] = a["percent"]
            self.speed = 4.8 * float(a["percent"])
            return self._ok(f"throttle {a['percent']}%")
        if name == "set_alert":
            s["alert"] = a["level"]
            return self._ok(f"condition {a['level']}")
        if name == "set_shields":
            mode = {"balanced": "shields_balanced", "off": "shields_off"}.get(a["mode"], "shields_sector")
            self._set_lane("tactical", mode, {"sector": a["mode"]} if mode == "shields_sector" else {}, "order", by)
            if a["mode"] == "off":
                s["shields"]["state"] = "down"
            else:
                s["shields"].update(state="up", mode=a["mode"])
            return self._ok(f"shields {a['mode']}")
        if name == "route_power":
            s["power_pct"][a["system"]] = a["percent"]
            return self._ok(f"{a['system']} at {a['percent']}%")
        if name == "intercept":
            c = self._contact(a.get("contact_id"))
            if c is None:
                return {"ok": False, "detail": f"no contact {a.get('contact_id')} to intercept"}
            self.helm_note = ""
            self._set_lane("helm", "intercept", {"target": c.id, "standoff_km": a.get("standoff_km", 6)}, "target_lost", by)
            rng, brg = self.range_bearing(c)
            return self._ok(f"intercepting {c.id}: bearing {brg:03.0f}, range {rng:.1f} km")
        if name == "cease_fire":
            if self.lanes["tactical"]["engagement"]["mode"] == "engage":
                self._reset_lane("tactical", "engagement")
            return self._ok("all offensive fire stopped; point defense stays on")
        if name == "holo_display":
            s["holo_table"] = a.get("mode", "tactical")
            return self._ok(f"holo table: {s['holo_table']}")
        if name == "transit_gate":
            dest = (a.get("system_name") or "").strip()
            if not dest:
                return {"ok": False, "detail": "which system? Keeper Station needs a destination"}
            self.helm_note = f"Janus approach to the {dest} system under way"
            return self._ok(f"course laid in for the Janus Gate; the gate is tuned to the {dest} system, transit in about 3 min")
        if name in ("set_target", "fire_weapons"):
            c = self._contact(a.get("contact_id"))
            if c is None:
                return {"ok": False, "detail": f"no contact {a.get('contact_id')}"}
            if name == "set_target":
                s["target"] = c.id
                return self._ok(f"target {c.id}")
            if c.status == "friendly":
                return {"ok": False, "detail": "weapons interlock: target is friendly"}
            if not c.classified:
                return {"ok": False, "detail": f"{c.id} is a bearing only: no firing solution"}
            rng = self.range_bearing(c)[0]
            if a["weapon"] in ("railguns", "lasers") and rng > (RAIL_KM if a["weapon"] == "railguns" else LASER_KM):
                return self._ok(f"{a['weapon']} assigned to {c.id}, waiting for it to close (now {rng:.0f} km)")
            c.hull -= {"railguns": 6.0, "lasers": 2.0, "missiles": 4.0, "torpedoes": 20.0}[a["weapon"]] * min(int(a["salvo"]), 4)
            if c.hull <= 0:
                c.alive = False
                self._emit(f"tactical: {c.id} ({c.name}) destroyed")
            return self._ok(f"{a['weapon']} salvo x{a['salvo']} on {c.id}")
        if name == "launch_decoys":
            return self._ok("decoys out: 6 s of chaff and flares")
        if name == "set_point_defense":
            s["weapons"]["point_defense"] = a["mode"]
            return self._ok(f"point defense {a['mode']}")
        if name == "launch_squadron":
            if "ready" not in s["squadrons"][a["squadron"]]:
                return {"ok": False, "detail": f"{a['squadron']} not ready"}
            s["squadrons"][a["squadron"]] = f"launched: {a['mission']}" + (f" ({a['contact_id']})" if a.get("contact_id") else "")
            return self._ok(f"{a['squadron']} launching")
        if name == "recall_squadron":
            s["squadrons"][a["squadron"]] = "recovering"
            return self._ok("recall")
        if name == "dispatch_damage_control":
            return self._ok(f"team to deck {a['deck']} {a['section']}")
        if name == "fleet_request":
            return {"ok": True, "detail": f"{a.get('ship', 'all')} acknowledges: {a.get('request')} {a.get('target', '')}".strip()}
        if name == "hail":
            c = self._contact(a["contact_id"]) if a["contact_id"] != "fleet" else {"id": "fleet"}
            if c is None:
                return {"ok": False, "detail": f"no contact {a['contact_id']}"}
            cid = c["id"] if isinstance(c, dict) else c.id
            self.channel = {"party": cid, "open": True}
            return self._ok(f"channel open to {cid}")
        if name == "end_transmission":
            self.channel = None
            return self._ok("channel closed")
        if name == "set_emcon":
            s["emcon"] = a["level"]
            self._set_lane("sensors", "emcon", {"level": a["level"]}, "order", by)
            return self._ok(f"emcon {a['level']}")
        if name == "active_scan":
            return self._ok("scan running")
        if name == "set_radiators":
            s["thermal"]["radiators"] = a["state"]
            return self._ok(f"radiators {a['state']}")
        if name == "vent_heat":
            t = s["thermal"]
            if t["coolant_vents"] <= 0:
                return {"ok": False, "detail": "no coolant charges left"}
            t["coolant_vents"] -= 1
            t["heat_pct"] = max(0, int(t["heat_pct"] * 0.65))
            return self._ok(f"coolant vented: heat {t['heat_pct']}%, {t['coolant_vents']} charges left")
        return {"ok": False, "detail": f"unknown tool {name}"}

    def _station(self, a: dict[str, Any], by: str) -> dict[str, Any]:
        if not self.stations_on:
            return {"ok": False, "detail": "unknown command station"}
        cmd, err = station_model.normalize(a)
        if cmd is None:
            return {"ok": False, "detail": err}
        st, mode, p, until = cmd["station"], cmd["mode"], cmd["params"], cmd["until"]
        if st == "xo":
            self.delegation[p["station"]] = p["level"]
            self.last_actions["xo"] = (self.last_actions["xo"] + [f"{by}: delegation {p['station']} {p['level']}"])[-4:]
            return self._ok(f"{p['station']} is on {p['level']}")
        # targets must exist (an intercept of nothing is a mistake the console would refuse)
        for key in ("target", "leader"):
            if key in p and not self._resolve(p[key]) and p[key] not in ("fleet", "gate", "away"):
                return {"ok": False, "detail": f"no contact {p[key]} on the plot"}
        if mode == "engage":
            bad = [t for t in p["targets"] if t != "hostiles" and not self._resolve(t)]
            if bad:
                return {"ok": False, "detail": f"no contact {bad[0]} on the plot"}
            friendly = [t for t in p["targets"] if self._resolve(t) and not self._resolve(t).status.startswith("hostile")]
            if friendly:
                return {"ok": False, "detail": f"weapons interlock: {friendly[0]} is not hostile"}
            blind = [t for t in p["targets"] if self._resolve(t) and not self._resolve(t).classified]
            if blind:
                return {"ok": False, "detail": f"{blind[0]} is a bearing only: no firing solution yet"}
        lane = self._set_lane(st, mode, p, until, by)
        if st == "helm":
            self.helm_note = ""
        if mode == "scan_focus":
            self._focus_t[str(p.get("target"))] = self.t
        if st == "helm" and mode == "hold" and "speed_pct" in p:
            self.state["throttle_pct"] = p["speed_pct"]
        if st == "flight":
            sq, kind = p["squadron"], p["type"]
            self.state["squadrons"][sq] = ("on deck, ready" if kind == "hold" else "recovering" if kind == "recall"
                                           else f"launched: {kind}" + (f" ({p['target']})" if p.get("target") else ""))
        self._sync_legacy()
        status = self._lane_status(st, lane, self.lanes[st][lane])
        return self._ok(f"{st}: {mode}{' ' + str(p) if p else ''} until {until}" + (f" — {status}" if status else ""))

    def _ok(self, detail: str) -> dict[str, Any]:
        self.events.append(detail)
        return {"ok": True, "detail": detail}

    # ------------------------------------------------------------------------------------------------ test helpers
    def lane(self, station: str, lane: str) -> dict[str, Any]:
        return self.lanes[station][lane]

    def calls(self, name: str | None = None) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
        return [c for c in self.log if name is None or c[1] == name]

    def station_calls(self, station: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        out = []
        for by, name, args, res in self.log:
            if name != "station" or not res.get("ok"):
                continue
            cmd, _ = station_model.normalize(args)
            if cmd and (station is None or cmd["station"] == station) and (mode is None or cmd["mode"] == mode):
                out.append({**cmd, "by": by})
        return out
