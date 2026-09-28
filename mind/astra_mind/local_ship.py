"""A minimal ship model used when the game is not connected (tests, the text console) — the game's
UAstraShipSubsystem is the real, authoritative implementation of the same tools."""
from __future__ import annotations

import copy
from typing import Any

INITIAL: dict[str, Any] = {
    "ship": "ASN Aquila", "location": "Aurelia System, 180,000 km from New Ravenna, en route to high orbit",
    "alert": "green", "heading_deg": 45, "mark_deg": 0, "throttle_pct": 60, "speed_mps": 412,
    "reactor_pct": 78,
    "power_pct": {"shields": 100, "weapons": 100, "engines": 100, "sensors": 100, "life_support": 100, "flight_deck": 100},
    "shields": {"state": "up", "mode": "balanced", "fore": 100, "aft": 100, "port": 100, "starboard": 100, "dorsal": 100, "ventral": 100},
    "weapons": {"railguns": "ready (4 twin turrets)", "lasers": "ready (12 batteries)", "missiles": "ready (96 in VLS)",
                "torpedoes": "ready (2 loaded)", "point_defense": "auto"},
    "target": None, "emcon": "restricted",
    "squadrons": {"alpha": "on deck, ready (8 Falcons)", "bravo": "on deck, ready (7 of 8 Hammers)", "drones": "ready (12 Wasps)"},
    "damage": [],
    "contacts": [
        {"id": "T-01", "class": "ASTRA battleship", "name": "ASN Praetorian (7th Fleet flagship)", "range_km": 12, "bearing_deg": 20, "status": "friendly"},
        {"id": "T-02", "class": "ASTRA destroyer", "name": "ASN Vigilant", "range_km": 18, "bearing_deg": 80, "status": "friendly"},
        {"id": "T-07", "class": "freighter", "name": "Free Guilds hauler Brightwater", "range_km": 67, "bearing_deg": 310, "status": "neutral"},
        {"id": "T-11", "class": "unknown", "name": None, "range_km": 50, "bearing_deg": 200, "status": "unidentified, cold drive, drifting"},
    ],
}


class LocalShip:
    def __init__(self) -> None:
        self.state = copy.deepcopy(INITIAL)
        self.events: list[str] = []

    def snapshot(self) -> dict[str, Any]:
        return self.state

    def recent_events(self) -> list[str]:
        return self.events[-8:]

    def _contact(self, cid: str):
        return next((c for c in self.state["contacts"] if c["id"].lower() == str(cid).lower()), None)

    async def execute(self, name: str, a: dict[str, Any], by: str) -> dict[str, Any]:
        s = self.state
        if name == "set_course":
            s["heading_deg"], s["mark_deg"] = round(a["heading_deg"]) % 360, round(a["mark_deg"])
            return self._ok(f"coming to {s['heading_deg']:03d} mark {s['mark_deg']}")
        if name == "set_throttle":
            s["throttle_pct"] = a["percent"]
            return self._ok(f"throttle {a['percent']}%")
        if name == "set_alert":
            s["alert"] = a["level"]
            return self._ok(f"condition {a['level']}")
        if name == "set_shields":
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
            s["helm"] = f"intercepting {c['id']}, standoff {a.get('standoff_km', 6)} km"
            return self._ok(f"intercepting {c['id']}: bearing {c['bearing_deg']:03d}, range {c['range_km']} km")
        if name == "cease_fire":
            return self._ok("all offensive fire stopped; point defense stays on")
        if name in ("set_target", "fire_weapons"):
            c = self._contact(a.get("contact_id"))
            if c is None:
                return {"ok": False, "detail": f"no contact {a.get('contact_id')}"}
            if name == "set_target":
                s["target"] = c["id"]
                return self._ok(f"target {c['id']}")
            if c["status"] == "friendly":
                return {"ok": False, "detail": "weapons interlock: target is friendly"}
            return self._ok(f"{a['weapon']} salvo x{a['salvo']} on {c['id']}")
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
        if name == "hail":
            c = self._contact(a["contact_id"]) if a["contact_id"] != "fleet" else {"id": "fleet"}
            if c is None:
                return {"ok": False, "detail": f"no contact {a['contact_id']}"}
            return self._ok(f"channel open to {c['id']}")
        if name == "set_emcon":
            s["emcon"] = a["level"]
            return self._ok(f"emcon {a['level']}")
        if name == "active_scan":
            return self._ok("scan running")
        return {"ok": False, "detail": f"unknown tool {name}"}

    def _ok(self, detail: str) -> dict[str, Any]:
        self.events.append(detail)
        return {"ok": True, "detail": detail}
