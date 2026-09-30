"""A minimal ship model used when the game is not connected (tests, the text console) — the game's
UAstraShipSubsystem is the real, authoritative implementation of the same tools.

With `stations=True` (the default) it also has live consoles that speak the game's language (UAstraStationsSubsystem: the
`station` command takes `{station, aspect, mode, params, until, note, by}`, the state has `stations.<id>.modes.<aspect>`):
every station keeps one mode per aspect, the modes have plausible simple effects (the helm turns and closes, tactical fires
and kills, the viewscreen follows its target and is released when the target is lost...) and `advance(seconds)` runs a
small fight — contacts that manoeuvre, a new contact that appears, targets that are destroyed — reporting what the
executors would report (`ship.reports`, in the game's words: "helm: intercept ended (T-23 is no longer on the plot): back
to hold"). With `stations=False` it is the old build: no `stations` in the state and the `station` command unknown, so the
mind's fallback to the legacy tools can be tested."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
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

# the aspect each station starts in (the game's own defaults: UAstraStationsSubsystem::Defaults)
DEFAULT_LANES: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {
    "helm": {"course": ("hold", {})},
    "tactical": {"engagement": ("return_fire", {}), "shields": ("shields_face_threat", {}), "point_defense": ("pd_auto", {}),
                 "missiles": ("missiles_normal", {})},
    "sensors": {"emcon": ("emcon", {"level": "restricted"}), "scan": ("scan_passive", {})},
    "ops": {"viewscreen": ("viewscreen_auto", {}), "holo": ("holo_tactical", {}), "damage_control": ("dc_auto", {}),
            "datapad": ("datapad_push", {})},
    "engineering": {"power": ("power_profile", {"profile": "balanced"}), "heat": ("heat_auto", {}), "reactor": ("reactor_normal", {})},
    "comms": {"channel": ("close", {}), "listen": ("listen_fleet", {})},          # ("close": the game's word for no channel open)
    "flight": {"alpha": ("mission", {"squadron": "alpha", "type": "hold"}), "bravo": ("mission", {"squadron": "bravo", "type": "hold"}),
               "drones": ("mission", {"squadron": "drones", "type": "hold"})},
    "xo": {},
}
LANE_OF_MODE = {name: md.lane for name, md in station_model.MODE_INDEX.items()}
TARGET_MODES = ("intercept", "keep_on_bow", "follow", "broadside", "orbit", "formation")     # the helm modes about a ship
RAIL_KM, LASER_KM, RAIL_PCT_S, LASER_PCT_S = 10.0, 4.0, 2.4, 1.6      # a railgun volley every 7 s is ~2.4 %/s on average here
# the game's power profiles (UAstraShipSubsystem / AstraStations.cpp `Profile`): shields weapons engines sensors life_support flight_deck
PROFILES = {"balanced": (100, 100, 100, 100, 100, 100), "combat": (150, 150, 100, 110, 80, 100), "evasive": (130, 90, 150, 100, 80, 90),
            "silent": (80, 60, 40, 60, 80, 60), "shields": (150, 110, 100, 100, 80, 90), "weapons": (120, 150, 100, 100, 80, 90),
            "engines": (110, 100, 150, 100, 80, 80)}
SYSTEMS = ("shields", "weapons", "engines", "sensors", "life_support", "flight_deck")


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
        self.engaged_id = ""                  # the contact tactical is firing on now (what `action` means first)
        self.battle_short = False             # the reactor past its limits: 800% to allocate, +0.3 %/s of heat
        self.power_budget = 700.0
        self.heat = float(self.state["thermal"]["heat_pct"])
        for sid, lanes in DEFAULT_LANES.items():
            self.lanes[sid] = {lane: {"mode": m, "params": dict(p), "until": "order", "set_by": "default", "since": 0.0, "status": ""}
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

    def action_target(self) -> Contact | None:
        """What the fight is about now (the game's ActionTargetId): tactical's target, else the nearest hostile inside 90 km."""
        cur = self._contact(self.engaged_id) if self.engaged_id else None
        if cur:
            return cur
        near = sorted((c for c in self.contacts.values() if c.alive and c.status.startswith("hostile")),
                      key=lambda c: self.range_bearing(c)[0])
        return next((c for c in near if not c.classified or self.range_bearing(c)[0] < 90.0), None)

    def _resolve(self, ref: Any) -> Contact | None:
        """A target reference: a contact id, `action` (what the fight is about now), or one of the mind-side selectors the
        offline tests use."""
        r = str(ref or "").strip()
        if r.lower() == "action":
            return self.action_target()
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
        s["thermal"]["heat_pct"] = round(self.heat)
        s["power_budget"] = f"{sum(s['power_pct'].values()):.0f}% of {self.power_budget:.0f}% allocated (six systems at 100% = 600%)"
        self._sync_legacy()
        if self.stations_on:
            s["sim_time_s"] = round(self.t, 1)
            s["stations"] = self._stations_json()
            s["viewscreen"] = self._viewscreen_line()
            a = self.action_target()
            s["action_target"] = a.id if a else ""                      # (top level, next to `stations`: what "action" means now)
        return s

    def _viewscreen_line(self) -> str:
        """What is on the main screen, in the one line the game writes ("auto: target, T-24 (Phlegethon), zoom x49")."""
        vs = self.lanes["ops"]["viewscreen"]
        m, p = vs["mode"], vs["params"]
        tgt = self._resolve(p.get("target")) if p.get("target") else None
        zoom = p.get("zoom", "")
        z = f", zoom x{zoom}" if zoom not in ("", None) else ""
        if m == "viewscreen_target" and tgt:
            return f"target: ordered, {tgt.id} ({tgt.name}){z or ', zoom x8'}"
        if m == "viewscreen_target" and str(p.get("target", "")).lower() == "action":
            return "target: waiting for the action (no fight), forward view"
        if m == "viewscreen_auto":
            pick = self._resolve("tactical_target") or self._resolve("nearest_hostile")
            return f"auto: target, {pick.id} ({pick.name}), zoom x8" if pick else "auto: forward view"
        if m == "viewscreen_off":
            return "off (the bare window)"
        if m == "viewscreen_comms":
            return f"comms: {p.get('party') or (self.channel or {}).get('party', '')}"
        return m.replace("viewscreen_", "") + z

    def recent_events(self) -> list[str]:
        return self.events[-8:]

    # ------------------------------------------------------------------------------------------------ the consoles
    def _set_lane(self, station: str, mode: str, params: dict[str, Any], until: str, by: str) -> str:
        lane = LANE_OF_MODE.get(mode, "main")
        if station == "flight":
            lane = str(params.get("squadron", "alpha"))
        self.lanes[station][lane] = {"mode": mode, "params": dict(params), "until": until, "set_by": by or "officer",
                                     "since": round(self.t, 1), "status": ""}
        self._act(station, f"{lane} {mode}" + (f" {params}" if params else ""))
        return lane

    def _act(self, station: str, text: str) -> None:
        self.last_actions[station] = (self.last_actions[station] + [text])[-3:]

    def _reset_lane(self, station: str, lane: str) -> None:
        if lane in DEFAULT_LANES[station]:
            m, p = DEFAULT_LANES[station][lane]
            self.lanes[station][lane] = {"mode": m, "params": dict(p), "until": "order", "set_by": "auto", "since": round(self.t, 1),
                                         "status": ""}

    def _expire(self, station: str, lane: str, why: str) -> None:
        """A mode that ran out (the game's Expire): the aspect falls back to its default, and the officer reports it."""
        was = self.lanes[station][lane]["mode"]
        m, _ = DEFAULT_LANES[station][lane]
        self._reset_lane(station, lane)
        self._emit(f"{station}: {was.replace('_', ' ')} ended ({why}): back to {m.replace('_', ' ')}")

    def _lane_status(self, station: str, lane: str, ls: dict[str, Any]) -> str:
        m, p = ls["mode"], ls["params"]
        if station == "helm":
            tgt = self._resolve(p.get("target"))
            if m in TARGET_MODES and tgt:
                rng, brg = self.range_bearing(tgt)
                if m == "keep_on_bow":
                    return f"bow on {tgt.id} (bearing {brg:03.0f}, {rng:.1f} km), speed {self.speed:.0f} m/s"
                return f"{m} {tgt.id} at {rng:.1f} km, {self.speed:.0f} m/s" + (
                    f", ETA {int(max(0, rng - float(p.get('standoff_km', 6))) * 1000 / max(self.speed, 1))} s" if m == "intercept" else "")
            if m == "course":
                return f"heading {self.heading:03.0f}, ordered {p.get('heading_deg', self.heading):03.0f}"
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

    def _station_status(self, sid: str) -> str:
        """The one status line of a console (the game writes one per station)."""
        lanes = self.lanes[sid]
        if sid == "helm":
            return self._lane_status("helm", "course", lanes["course"])
        if sid == "tactical":
            eng = self._lane_status("tactical", "engagement", lanes["engagement"])
            return f"{eng} · shields {lanes['shields']['mode'].replace('shields_', '')} · PD {lanes['point_defense']['mode'].replace('pd_', '')}"
        if sid == "sensors":
            return f"EMCON {lanes['emcon']['params'].get('level', '')} · scan {lanes['scan']['mode'].replace('scan_', '')}"
        if sid == "ops":
            return f"screen {lanes['viewscreen']['mode'].replace('viewscreen_', '')} · holo {lanes['holo']['mode'].replace('holo_', '')}"
        return ""

    def _native(self, sid: str, lane: str, ls: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        """One aspect in the game's words: (aspect, mode, params)."""
        if ls["mode"] not in station_model.MODE_INDEX:                        # (the game's own word: "close")
            return lane, ls["mode"], dict(ls["params"])
        w = station_model.to_wire({"station": sid, "mode": ls["mode"], "params": ls["params"], "until": ls["until"]})
        params = dict(w["params"])
        if ls["mode"] == "hold":
            params.setdefault("face_action", True)
        return w["aspect"], w["mode"], params

    def _stations_json(self) -> dict[str, Any]:
        """ship_state.state.stations as the game writes it: {officer, delegation, status, modes: {aspect: {...}}, recent}."""
        out: dict[str, Any] = {}
        for sid, lanes in self.lanes.items():
            modes: dict[str, Any] = {}
            for lane, ls in lanes.items():
                aspect, native, params = self._native(sid, lane, ls)
                o: dict[str, Any] = {"mode": native, "until": ls["until"], "set_by": ls["set_by"], "for_s": max(0, round(self.t - ls["since"]))}
                if params:
                    o["params"] = params
                modes[aspect] = o
            out[sid] = {"officer": sid, "delegation": self.delegation.get(sid, "auto"), "status": self._station_status(sid),
                        "modes": modes, "recent": list(self.last_actions.get(sid, []))[-3:]}
        return out

    def _sync_legacy(self) -> None:
        """The old flat fields the crew and the tactical advisor read (as the game writes them)."""
        s = self.state
        h = self.lanes["helm"]["course"]
        tgt = self._resolve(h["params"].get("target")) if h["mode"] in TARGET_MODES else None
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
        s["shields"]["mode"] = {"shields_balanced": "balanced", "shields_face_threat": "face_threat", "shields_sector": str(sh["params"].get("sector", "forward")),
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
        if self.battle_short:
            self.heat = min(100.0, self.heat + 0.3 * dt)                    # (the reactor runs hot)
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
        h = self.lanes["helm"]["course"]
        m, p = h["mode"], h["params"]
        want_h, want_speed = None, None
        tgt = self._resolve(p.get("target")) if m in TARGET_MODES else None
        if m == "intercept" and tgt:
            rng, brg = self.range_bearing(tgt)
            st = float(p.get("standoff_km", 6))
            want_h = brg if rng > st else _wrap(brg + 90)
            want_speed = 480.0 * float(p.get("speed_pct", 100)) / 100 if rng > st + 0.5 else 0.0
        elif m == "keep_on_bow" and tgt:
            want_h = self.range_bearing(tgt)[1]
        elif m in ("follow", "orbit", "broadside", "formation") and tgt:
            rng, brg = self.range_bearing(tgt)
            want_h = brg if rng > float(p.get("distance_km", p.get("range_km", p.get("radius_km", 6)))) else _wrap(brg + 90)
            want_speed = 300.0
        elif m == "course":
            want_h = float(p.get("heading_deg", self.heading))
            want_speed = 480.0 * float(p["speed_pct"]) / 100 if "speed_pct" in p else None
        elif m == "retreat":
            hostile = self._resolve("nearest_hostile")
            want_h = _wrap(self.range_bearing(hostile)[1] + 180) if hostile else self.heading
            want_speed = 480.0
        elif m == "evade":
            want_h = _wrap(self.heading + 30 * math.sin(self.t / 2))
            want_speed = 480.0
        elif m == "hold" and p.get("face_action", True):
            hostile = self._resolve("nearest_hostile")                 # in a fight the bow comes round to the action, by itself
            want_h = self.range_bearing(hostile)[1] if hostile else None
        if want_h is not None:
            self.heading = _wrap(self.heading + max(-1.5 * dt, min(1.5 * dt, _delta(self.heading, want_h))))
        if want_speed is not None:
            self.speed += max(-40 * dt, min(40 * dt, want_speed - self.speed))
        self.x += math.sin(math.radians(self.heading)) * self.speed * dt / 1000.0
        self.y += math.cos(math.radians(self.heading)) * self.speed * dt / 1000.0



    def _pick_target(self) -> Contact | None:
        """Who tactical fires on now: the first live target of an engage list; `hostiles` = the best hostile warship in reach (stay on
        the one being fought while it is inside 25 km, else whoever fires on us first inside 30 km, else the nearest; never a chase);
        weapons free / return fire = the nearest that qualifies."""
        eng = self.lanes["tactical"]["engagement"]
        m, p = eng["mode"], eng["params"]
        hostile = sorted((c for c in self.contacts.values() if c.alive and c.status.startswith("hostile") and c.classified),
                         key=lambda c: self.range_bearing(c)[0])
        if m == "engage":
            for t in p.get("targets", []):
                if str(t).lower() == "hostiles":
                    cur = self._contact(self.engaged_id)
                    if cur and cur in hostile and self.range_bearing(cur)[0] < 25.0:
                        return cur
                    best = None
                    for c in hostile:
                        if best is None or (c.firing and not best.firing and self.range_bearing(c)[0] < 30.0):
                            best = c
                    if best:
                        return best
                    continue
                c = self._resolve(t)
                if c:
                    return c
            return None
        if m == "weapons_free":
            cap = float(p.get("range_km", 25.0))
            return next((c for c in hostile if self.range_bearing(c)[0] <= cap), None)
        if m == "return_fire":
            return next((c for c in hostile if c.firing), None)
        return None

    def _tick_fire(self, dt: float) -> None:
        c = self._pick_target()
        eng = self.lanes["tactical"]["engagement"]
        new = c.id if c else ""
        if new != self.engaged_id and c is not None and self.engaged_id:
            self._emit(f"tactical: engaging {c.name or c.id} (was {self.engaged_id})")
        self.engaged_id = new
        if c is None or eng["mode"] == "hold_fire" or self.state["power_pct"]["weapons"] < 5:
            return
        rng = self.range_bearing(c)[0]
        rate = (RAIL_PCT_S if rng <= RAIL_KM else 0.0) + (LASER_PCT_S if rng <= LASER_KM else 0.0)
        if rate:
            c.hull -= rate * dt * self.state["power_pct"]["weapons"] / 100
            if c.hull <= 0:
                c.alive = False
                self._emit(f"tactical: {c.id} ({c.name}) destroyed")

    def _tick_release(self) -> None:
        """The modes that end: the console returns to its default and reports it (the game's Expire)."""
        h = self.lanes["helm"]["course"]
        if (h["mode"] in TARGET_MODES and h["params"].get("target") and str(h["params"]["target"]).lower() != "action"
                and not self._resolve(h["params"].get("target"))):
            self._expire("helm", "course", f"{h['params'].get('target')} is no longer on the plot")
        for sid, lanes in self.lanes.items():                    # a time limit sends ANY aspect back to its default mode
            for lane, ls in list(lanes.items()):
                if ls["until"].startswith("time:") and self.t - ls["since"] >= float(ls["until"][5:]):
                    dm, dp = DEFAULT_LANES[sid].get(lane, (ls["mode"], ls["params"]))
                    # (the game compares the modes by ITS name: `combat` is not `balanced`, though both are a power profile)
                    same = self._native(sid, lane, ls)[1] == self._native(sid, lane, {"mode": dm, "params": dp, "until": "order"})[1]
                    if same:
                        ls["until"] = "order"
                    else:
                        if lane == "reactor" and self.battle_short:
                            self._set_battle_short(False)        # (back inside its limits: the ship follows the console)
                        elif lane == "power":
                            self._apply_power(dict(zip(SYSTEMS, map(float, PROFILES["balanced"]))))
                        elif lane == "emcon":
                            self.state["emcon"] = str(dp.get("level", "restricted"))
                        self._expire(sid, lane, "the time set for it is up")
        eng = self.lanes["tactical"]["engagement"]
        if eng["mode"] == "engage" and not any(str(t).lower() == "hostiles" for t in eng["params"].get("targets", [])) \
                and not any(self._resolve(t) for t in eng["params"].get("targets", [])):
            self._expire("tactical", "engagement", "the targets are down or gone")
        vs = self.lanes["ops"]["viewscreen"]
        if vs["mode"] == "viewscreen_target" and str(vs["params"].get("target", "")).lower() != "action" \
                and not self._resolve(vs["params"].get("target")):
            self._emit(f"ops: viewscreen released — {vs['params'].get('target')} lost, back to auto")
            self._reset_lane("ops", "viewscreen")
        sc = self.lanes["sensors"]["scan"]
        if sc["mode"] == "scan_focus":
            raw = str(sc["params"].get("target"))
            c = self._resolve(raw) if raw.lower() == "action" else self._contact(raw)
            if raw.lower() != "action" or c:
                t0 = self._focus_t.setdefault(c.id if c else raw, self.t)
                if c and self.t - t0 >= 6 and not c.classified:
                    c.classified = True
                    self._emit(f"sensors: {c.id} identified — {c.cls} {c.name}, {self.range_bearing(c)[0]:.0f} km, bearing {self.range_bearing(c)[1]:03.0f}")
                elif not c:
                    self._expire("sensors", "scan", f"{raw} is gone")

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
            self._reset_lane("helm", "course")                    # a set_course cancels an intercept
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
            self._set_lane("tactical", mode, {"sector": a["mode"]} if mode == "shields_sector" else {}, "order", "officer")
            if a["mode"] == "off":
                s["shields"]["state"] = "down"
            else:
                s["shields"].update(state="up", mode=a["mode"])
            return self._ok(f"shields {a['mode']}")
        if name == "route_power":
            total = sum(a["percent"] if k == a["system"] else v for k, v in s["power_pct"].items())
            if total > self.power_budget + 0.5:
                return {"ok": False, "detail": f"reactor budget exceeded: that would allocate {total:.0f}% of the {self.power_budget:.0f}% available — "
                                               "cut another system first (now: " + ", ".join(f"{k} {v:.0f}" for k, v in s["power_pct"].items()) + ")"}
            s["power_pct"][a["system"]] = a["percent"]
            return self._ok(f"{a['system']} at {a['percent']}%, {total:.0f}% of the {self.power_budget:.0f}% budget allocated")
        if name == "intercept":
            c = self._contact(a.get("contact_id"))
            if c is None:
                return {"ok": False, "detail": f"no contact {a.get('contact_id')} to intercept"}
            self.helm_note = ""
            self._set_lane("helm", "intercept", {"target": c.id, "standoff_km": a.get("standoff_km", 6)}, "target_lost", "officer")
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
            self._set_lane("sensors", "emcon", {"level": a["level"]}, "order", "officer")
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
            self.heat = float(t["heat_pct"])
            return self._ok(f"coolant vented: heat {t['heat_pct']}%, {t['coolant_vents']} charges left")
        return {"ok": False, "detail": f"unknown tool {name}"}

    @staticmethod
    def parse(a: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """A `station` command's arguments -> the crew's checked command. The game's form (an `aspect` given) is read as the game
        reads it; the crew's own names are accepted too (the tests call the ship with them)."""
        if "aspect" in a:
            return station_model.from_wire(a)
        cmd, err = station_model.normalize(a)
        if cmd is None:
            cmd2, err2 = station_model.from_wire(a)
            return (cmd2, "") if cmd2 is not None else (None, err)
        return cmd, ""

    def _station(self, a: dict[str, Any], by: str) -> dict[str, Any]:
        if not self.stations_on:
            return {"ok": False, "detail": "unknown command station"}
        cmd, err = self.parse(a)
        if cmd is None:
            return {"ok": False, "detail": err}
        st, mode, p, until = cmd["station"], cmd["mode"], cmd["params"], cmd["until"]
        set_by = str(a.get("by") or "officer")                       # who decided: captain | officer | xo (the game: args.by)
        if st == "xo":
            self.delegation[p["station"]] = p["level"]
            self._act("xo", f"delegation: {p['station']} now on {p['level']}")
            return self._ok(f"{p['station']} now on {p['level']}")
        # targets must exist (an intercept of nothing is a mistake the console would refuse); `action` may wait for a fight
        tgt = str(p.get("target", ""))
        if tgt and tgt.lower() != "action" and not self._resolve(tgt):
            return {"ok": False, "detail": f"no contact {tgt} on the plot"}
        if mode in ("follow", "orbit", "broadside", "formation") and tgt and self._resolve(tgt) is not None and not self._resolve(tgt).classified:
            return {"ok": False, "detail": f"{tgt} is only a bearing (no range): the helm can steer down it, not hold a distance"}
        if mode == "engage" and any(str(t).lower() == "hostiles" for t in p["targets"]):
            pass                                           # a standing order: the best hostile in reach, new contacts included; it waits when there is none
        elif mode == "engage":
            if not p["targets"]:
                return {"ok": False, "detail": "engage needs a target"}
            bad = [t for t in p["targets"] if not self._resolve(t)]
            if bad:
                return {"ok": False, "detail": f"no contact {bad[0]} on the plot"}
            friendly = [t for t in p["targets"] if not self._resolve(t).status.startswith("hostile")]
            if friendly:
                return {"ok": False, "detail": f"weapons interlock: {friendly[0]} is not hostile"}
            blind = [t for t in p["targets"] if not self._resolve(t).classified]
            if blind:
                return {"ok": False, "detail": f"{blind[0]} is a bearing only: no firing solution yet"}
        if mode == "power_profile":
            row = PROFILES[p["profile"]]
            err = self._apply_power(dict(zip(SYSTEMS, map(float, row))))
            if err:
                return {"ok": False, "detail": err}
        elif mode == "power_custom":
            err = self._apply_power({k[:-4]: float(v) for k, v in p.items() if k.endswith("_pct")})
            if err:
                return {"ok": False, "detail": err}
        elif mode == "reactor_battle_short":
            self._set_battle_short(True)
        elif mode == "reactor_normal":
            self._set_battle_short(False)
        lane = self._set_lane(st, mode, p, until, set_by)
        if st == "helm":
            self.helm_note = ""
            if mode == "course" and "speed_pct" in p:
                self.state["throttle_pct"] = p["speed_pct"]
        if mode == "scan_focus":
            self._focus_t[str(p.get("target"))] = self.t
            r = self._resolve(p.get("target"))
            if r:
                self._focus_t[r.id] = self.t
        if st == "flight":
            sq, kind = p["squadron"], p["type"]
            self.state["squadrons"][sq] = ("on deck, ready" if kind == "hold" else "recovering" if kind == "recall"
                                           else f"launched: {kind}" + (f" ({p['target']})" if p.get("target") else ""))
        self._sync_legacy()
        status = self._lane_status(st, lane, self.lanes[st][lane])
        return self._ok(f"{st}: {mode}{' ' + str(p) if p else ''} until {until}" + (f" — {status}" if status else ""))

    def _set_battle_short(self, on: bool) -> None:
        """Engineering's battle short (the game's UAstraShipSubsystem::SetBattleShort): 800% of power to allocate instead of 700%
        and +0.3 %/s of heat; back to normal, every allocation above nominal comes down in proportion to fit the old budget."""
        if on == self.battle_short:
            return
        self.battle_short = on
        self.power_budget = 800.0 if on else 700.0
        if not on:
            pw = self.state["power_pct"]
            total, over = sum(pw.values()), sum(max(0.0, v - 100.0) for v in pw.values())
            if total > self.power_budget and over > 0:
                k = max(0.0, min(1.0, 1.0 - (total - self.power_budget) / over))
                for key, v in pw.items():
                    if v > 100.0:
                        pw[key] = 100.0 + (v - 100.0) * k
        self._emit("engineering: battle short — the reactor's limits are overridden: 800% of power to allocate, and she runs hot" if on
                   else "engineering: the reactor is back inside its limits (700%)", report=False)

    def _apply_power(self, want: dict[str, float]) -> str | None:
        """Set several systems at once, inside the budget (the game's engineering power modes); an error text or None."""
        pw = self.state["power_pct"]
        total = sum(want.get(k, v) for k, v in pw.items())
        if total > self.power_budget + 0.5:
            return f"that profile needs {total:.0f}% of a {self.power_budget:.0f}% budget"
        pw.update(want)
        return None

    def _ok(self, detail: str) -> dict[str, Any]:
        self.events.append(detail)
        return {"ok": True, "detail": detail}

    # ------------------------------------------------------------------------------------------------ test helpers
    def lane(self, station: str, lane: str) -> dict[str, Any]:
        return self.lanes[station][lane]

    def calls(self, name: str | None = None) -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
        return [c for c in self.log if name is None or c[1] == name]

    def station_calls(self, station: str | None = None, mode: str | None = None) -> list[dict[str, Any]]:
        """The `station` commands that were accepted, in the crew's names ({station, mode, params, until, by, set_by})."""
        out = []
        for by, name, args, res in self.log:
            if name != "station" or not res.get("ok"):
                continue
            cmd, _ = self.parse(args)
            if cmd and (station is None or cmd["station"] == station) and (mode is None or cmd["mode"] == mode):
                out.append({**cmd, "by": by, "set_by": str(args.get("by") or "officer")})
        return out

