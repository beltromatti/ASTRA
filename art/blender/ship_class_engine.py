"""ASTRA ships: the primitives of a class plan (FLOTTA-VIVA, docs/FLOTTA-VIVA.md): the constants of the layout, the table of room kinds, and the
Deck (one floor of the stack, the footprint it lies in, where its passages run). The builder is ship_class_build.py, the specs
ship_class_specs.py, the command line ship_class_plans.py, the checks ship_class_checks.py. Pure Python.

The layout, the same on every class (a ship is read the same way): per deck a SPINE corridor along the keel line (y = 0), two PASSAGES along
the flanks where the hull is wide enough (a second way round, so a flank exists), CROSS corridors joining them at the fore end of each section,
ROWS of rooms between (inner rows between spine and passage, outer rows between passage and skin), HALLS that take the width of the inner rows
over several decks (reactor, hangar, magazine), STAIR columns, AIRLOCKS in a strip along the skin on the decks where a boarding hatch is, and
PRESSURE BULKHEADS (door kind `blast`, with `boundary`) across every lane at each section boundary.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import ship_class_hull as HULL  # noqa: E402

WALL = 0.3            # the wall between two boxes (a door stands in it)
SPINE_HW = 1.6        # the spine is 3.2 m wide
PASS_HW = 1.2         # a passage is 2.4 m wide
CORR_H = 3.2          # a corridor's clear height (a room can be as tall as its deck)
STRIP = 3.4           # the strip along the skin of a dock deck, where the airlocks are
MIN_DEPTH = 4.5       # a room shallower than this is not a room
MIN_LEN = 6.0         # nor one shorter
CROSS_W = 3.0         # a cross corridor's length along the ship
STAIR_SIZE = 6.0      # a stair tower is 6 x 6 m
DOOR_W, DOOR_H = 1.6, 2.4
BLAST_W, BLAST_H = 2.0, 2.5
GATE_W, GATE_H = 3.2, 3.0


def r2(v: float) -> float:
    return round(float(v) + 0.0, 2)


def clamp(v, a, b):
    return max(a, min(b, v))


# ======================================================================================================================== kinds
# kind -> (default name, dept, systems, crew slots per 100 m2). The kinds are the ones the damage map knows (AstraDamageMap.cpp) where there
# is one, so each takes the profile of what it is (how it burns, how hard it is, how thick its conduits run); the rest (airlock, brig, cic,
# vestibule...) are named for what they are and the map takes them as a room of no special sort.
KINDS = {
    "corridor": ("Corridor", "neutral", ["power_bus", "life_support"], 0),
    "vestibule": ("Boarding Vestibule", "security", ["power_bus", "life_support"], 0),
    "stairs": ("Stair Tower", "neutral", ["power_bus"], 0),
    "airlock": ("EVA Airlock", "engineering", ["power_bus", "life_support"], 0),
    "bridge": ("Bridge", "command", ["command", "comms", "data_trunk", "power_bus", "life_support"], 6),
    "cic": ("Combat Information Centre", "command", ["command", "comms", "data_trunk", "sensors", "power_bus", "life_support"], 5),
    "comms": ("Communications Centre", "command", ["comms", "data_trunk", "power_bus", "life_support"], 4),
    "sensors": ("Sensor Array Room", "science", ["sensors", "data_trunk", "power_bus", "life_support"], 3),
    "computer": ("Computer Core", "science", ["data_trunk", "power_bus"], 1),
    "weapons_control": ("Fire Control", "security", ["weapons", "data_trunk", "power_bus", "life_support"], 4),
    "weapons": ("Railgun Barbette", "security", ["weapons", "power_bus"], 3),
    "magazine": ("Munitions Magazine", "security", ["ordnance", "weapons", "power_bus"], 1),
    "armory": ("Armoury", "security", ["ordnance", "power_bus", "life_support"], 2),
    "brig": ("Brig", "security", ["power_bus", "life_support"], 1),
    "quarters": ("Captain's Quarters", "command", ["power_bus", "life_support"], 1),
    "wardroom": ("Wardroom", "services", ["power_bus", "life_support"], 2),
    "cabins": ("Crew Cabins", "services", ["power_bus", "life_support"], 1),
    "berthing": ("Crew Berthing", "services", ["power_bus", "life_support"], 1),
    "mess": ("Mess Hall", "services", ["food_service", "power_bus", "life_support"], 3),
    "galley": ("Galley", "services", ["food_service", "power_bus", "life_support"], 3),
    "lounge": ("Crew Lounge", "services", ["power_bus", "life_support"], 0),
    "gym": ("Gymnasium", "services", ["power_bus", "life_support"], 0),
    "chapel": ("Chapel", "services", ["power_bus", "life_support"], 0),
    "heads": ("Heads & Showers", "services", ["power_bus", "life_support"], 0),
    "laundry": ("Laundry", "services", ["power_bus", "life_support"], 1),
    "offices": ("Department Offices", "command", ["power_bus", "life_support", "data_trunk"], 3),
    "briefing": ("Briefing Room", "command", ["power_bus", "life_support"], 2),
    "storage": ("Section Stores", "logistics", ["power_bus"], 0),
    "cargo": ("Cargo Hold", "logistics", ["power_bus"], 0),
    "damage_control": ("Damage-Control Station", "engineering", ["damage_control", "power_bus", "life_support"], 4),
    "machinery": ("Machinery Space", "engineering", ["power_bus", "life_support", "compressed_air"], 2),
    "power": ("Power Control", "engineering", ["power_bus", "reactor", "data_trunk"], 3),
    "engineering": ("Main Engineering", "engineering", ["reactor", "coolant", "power_bus", "engines", "life_support"], 2),
    "engines": ("Engine Room", "engineering", ["engines", "coolant", "power_bus", "life_support"], 2),
    "coolant": ("Coolant Plant", "engineering", ["coolant", "power_bus"], 1),
    "air_plant": ("Atmosphere Plant", "engineering", ["life_support", "power_bus"], 1),
    "workshop": ("Machine Shop", "engineering", ["power_bus", "life_support"], 2),
    "tank": ("Reaction-Mass Tank", "engineering", ["coolant"], 0),
    "hangar": ("Hangar", "flight", ["catapults", "power_bus", "life_support"], 3),
    "flight_ops": ("Flight Control", "flight", ["comms", "power_bus", "life_support"], 4),
    "medbay": ("Medbay", "medical", ["power_bus", "life_support"], 3),
    "surgery": ("Surgery", "medical", ["power_bus", "life_support"], 2),
    "lab": ("Laboratory", "science", ["power_bus", "life_support"], 2),
    "crawlway": ("Maintenance Crawlway", "engineering", ["power_bus"], 0),
}


# ======================================================================================================================== the deck
class Deck:
    """One floor of the plan: its place in the stack, the footprint it lies in (the hull body's skin, or a box for a tower or a block) and where
    its passages run."""

    def __init__(self, spec: dict, hull: HULL.Hull, wall: float):
        self.id = spec["id"]
        self.name = spec.get("name", f"Deck {self.id}")
        self.programme = spec.get("programme", "")
        self.z = spec["z"]
        self.clear = spec["clear"]
        self.pitch = spec.get("pitch", self.clear + 2 * 0.3)
        self.body = spec.get("body", True)
        self.strip = bool(spec.get("strip", False))          # a dock deck: airlocks along the skin
        self.layout = spec.get("layout", "full")           # full (spine, passages, rows) | spine (a spine and rows)
        self.volume = spec.get("volume", "lower hull" if self.body else "superstructure")
        self.hw_cap = spec.get("hw_cap")                     # a cap on the half width (a hull whose skin is not where its habitable part is)
        self.pass_range = spec.get("pass_range")             # where passages may run at all (a freighter's are in its two blocks, not along its truss)
        step = 2.0
        foot = spec.get("foot")
        if foot:
            # an explicit footprint (a tower, a block, a drum): a box, or a list of (x, half width)
            pts = sorted(foot["pts"]) if "pts" in foot else [(foot["x"][0], foot["hw"]), (foot["x"][1], foot["hw"])]
            xa, xb = pts[0][0], pts[-1][0]
            n = max(1, int(round((xb - xa) / step)))
            self.ex = [xa + (xb - xa) * i / n for i in range(n + 1)]
            self.ehw = [self._interp(pts, x) for x in self.ex]
        else:
            hx0, hx1 = hull.x_range()
            xa, xb = spec.get("x", (hx0, hx1))
            xa, xb = max(xa, hx0), min(xb, hx1)
            n = max(1, int(round((xb - xa) / step)))
            self.ex = [xa + (xb - xa) * i / n for i in range(n + 1)]
            raw = [max(0.0, hull.half_width(x, self.z, self.z + self.clear) - wall) for x in self.ex]
            self.ehw = self._tidy(raw)
        if self.hw_cap:
            self.ehw = [min(h, self.hw_cap) for h in self.ehw]
        # where there is a body at all: a spine and a room
        ok = [i for i, h in enumerate(self.ehw) if h >= SPINE_HW + WALL + MIN_DEPTH]
        if not ok:
            raise ValueError(f"deck {self.id} ({self.name}): no body at z {self.z}..{self.z + self.clear} (widest {max(self.ehw):.1f} m)")
        i0, i1 = ok[0], ok[-1]
        self.ex, self.ehw = self.ex[i0:i1 + 1], self.ehw[i0:i1 + 1]
        self.xa, self.xf = self.ex[0], self.ex[-1]
        self.YP = None
        self.pass_x = None
        self.sections = []

    @staticmethod
    def _interp(pts, x):
        if x <= pts[0][0]:
            return pts[0][1]
        for (xa, ha), (xb, hb) in zip(pts, pts[1:]):
            if xa <= x <= xb:
                return ha + (hb - ha) * (x - xa) / max(1e-9, xb - xa)
        return pts[-1][1]

    @staticmethod
    def _tidy(v):
        """Smooth the inscribed half widths: a closing over +-5 stations (a recess of the plating is not a place where the hull ends), an opening over
        +-3 (a boss that sticks out is not a place where it widens), then a running mean over +-2 (the lines of a hull do not zigzag)."""
        n = len(v)

        def run(a, w, f):
            return [f(a[max(0, i - w): i + w + 1]) for i in range(n)]
        a = run(run(v, 5, max), 5, min)
        a = run(run(a, 3, min), 3, max)
        return run(a, 2, lambda s: sum(s) / len(s))

    def hw(self, x: float) -> float:
        if x < self.ex[0] - 1e-6 or x > self.ex[-1] + 1e-6:
            return 0.0
        if len(self.ex) == 1:
            return self.ehw[0]
        step = (self.ex[-1] - self.ex[0]) / (len(self.ex) - 1)
        i = max(0, min(len(self.ex) - 2, int((x - self.ex[0]) / step)))
        t = (x - self.ex[i]) / step
        return self.ehw[i] + (self.ehw[i + 1] - self.ehw[i]) * t

    def hw_min(self, a: float, b: float) -> float:
        """The least half width over x in [a, b]."""
        lo, hi = min(a, b), max(a, b)
        m = min(self.hw(lo), self.hw(hi))
        for x, h in zip(self.ex, self.ehw):
            if lo <= x <= hi:
                m = min(m, h)
        return m

    def lim_out(self) -> float:
        """How far inside the skin a room stops: the strip of the airlocks on a dock deck, else a hand's breadth."""
        return STRIP + WALL if self.strip else 0.3

    def choose_passages(self):
        """Where the passages run and at which y: the second lane of the walk graph on both flanks, as far as the hull is wide enough for it."""
        if self.layout != "full":
            return
        s = sorted(self.ehw)
        lo = self.lim_out()
        if s[int(0.5 * (len(s) - 1))] >= 28.0:
            yp = clamp(0.5 * s[int(0.6 * (len(s) - 1))], 9.0, 34.0)               # wide: rows on both sides of it
        else:
            ref = s[int(0.35 * (len(s) - 1))]
            yp = ref - lo - PASS_HW                                               # not wide: it hugs the skin and the inner rows take the width
        yp = round(yp * 2.0) / 2.0
        if yp < SPINE_HW + WALL + PASS_HW + 2.5 + MIN_DEPTH:
            return
        need = yp + PASS_HW + lo
        best, cur = None, None
        for x, h in zip(self.ex, self.ehw):
            if self.pass_range and not (self.pass_range[0] <= x <= self.pass_range[1]):
                h = 0.0
            if h >= need - 1e-6:
                cur = (cur[0], x) if cur else (x, x)
            else:
                if cur and (best is None or cur[1] - cur[0] > best[1] - best[0]):
                    best = cur
                cur = None
        if cur and (best is None or cur[1] - cur[0] > best[1] - best[0]):
            best = cur
        if best and best[1] - best[0] >= 24.0:
            self.YP, self.pass_x = yp, best

    def has_passage(self, x: float) -> bool:
        return bool(self.pass_x) and self.pass_x[0] - 1e-6 <= x <= self.pass_x[1] + 1e-6

    def inner_limit(self, x: float) -> float:
        """The outer edge of the inner rows at x: the passage's inner wall where there is a passage, else the skin."""
        if self.has_passage(x):
            return self.YP - PASS_HW - WALL
        return self.hw(x) - self.lim_out()

    def outer_limit(self, x: float) -> float:
        return self.hw(x) - self.lim_out()

    def record(self) -> dict:
        pts, x = [], self.xf
        while x >= self.xa - 1e-6:
            pts.append([r2(x), r2(self.hw(x))])
            x -= 4.0
        if pts[-1][0] > self.xa + 0.5:
            pts.append([r2(self.xa), r2(self.hw(self.xa))])
        return {"id": self.id, "name": self.name, "programme": self.programme, "z": r2(self.z), "clear": r2(self.clear), "ceiling": r2(self.z + self.clear),
                "structure": 0.3, "pitch": r2(self.pitch), "volume": self.volume, "body": self.body,
                "envelope": {"x_fwd": r2(self.xf), "x_aft": r2(self.xa), "half_width": pts}, "sections": self.sections}
