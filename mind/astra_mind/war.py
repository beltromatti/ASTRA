"""The war map: the Aurelia March, the frontier sector where the ASTRA Core Worlds meet the Outer Worlds of the Kharon
Mandate (docs/BIBBIA.md). Star systems joined by the Janus Network (each Gate is bound to a few others and Keeper
Station tunes it to one of them), who holds each system, what matters there, and how the war moves.

The director reads it before every beat and changes it (systems fall, fronts move, news reaches the fleet net); the
crew knows it; the game draws it on the holo table and uses it to route the gates. It is saved as the war goes on
(Saved/Campaign/war.json), so the consequences last."""
from __future__ import annotations

import copy
import json
import logging
import os
import time
from typing import Any

log = logging.getLogger("astra.war")

SAVE_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "Saved", "Campaign"))

OWNERS = ("astra", "mandate", "guilds", "contested", "silent")

# x, y: light-years on the sector plot (the Core to the west, the Outer Worlds to the east)
SECTOR: list[dict[str, Any]] = [
    dict(name="Concordia", star="yellow", planet="ocean", world="Concord", owner="astra", x=-34, y=2, pop=920,
         about="the ASTRA capital, seat of the Senate and the Admiralty; far behind the front"),
    dict(name="Meridian", star="yellow", planet="ocean", world="Halcyon", owner="astra", x=-19, y=9, pop=12,
         about="the breadbasket of the March: its grain feeds New Ravenna and the fleets"),
    dict(name="Aurelia", star="orange", planet="ocean", world="New Ravenna", owner="astra", x=0, y=4, pop=30,
         about="home of the 7th Fleet: New Ravenna and Port Aurelius, the Aurelia Arsenal shipyards, the deuterium "
               "refineries on Tiberius; its Gate and Keeper Station are the Mandate's first objective"),
    dict(name="Cassia", star="blue_white", planet="ice", world="Cassia Prime", owner="astra", x=7, y=-10, pop=2,
         about="ice mines and deuterium, the small Cassia Yards; lightly defended"),
    dict(name="Veyra", star="orange", planet="desert", world="Sabel", owner="guilds", x=-7, y=-17, pop=5,
         about="the Guildhall of the March: Free Guilds trade hub, neutral ground, markets, spies and smugglers"),
    dict(name="Thule", star="red_dwarf", planet="barren", world="Hollow", owner="silent", x=17, y=3, pop=0.02,
         about="the frontier: Thule Watch, the ASTRA listening post, went silent two days ago; the Mandate strike "
               "group came through here"),
    dict(name="Ophir", star="red_dwarf", planet="desert", world="Ophir", owner="mandate", x=29, y=12, pop=3,
         about="a famine world of the Long Night, the Mandate's recruiting ground; bitter, loyal"),
    dict(name="Erebus", star="red_dwarf", planet="lava", world="Pyre", owner="mandate", x=27, y=-9, pop=0.4,
         about="Erebus Anchorage, the Mandate forward base where the strike fleets muster and refit"),
    dict(name="Nemet", star="orange", planet="ocean", world="Nemet", owner="mandate", x=14, y=-22, pop=8,
         about="drowned cities and fishing fleets; restless under Mandate rule, trades quietly with Veyra"),
    dict(name="Niflheim", star="orange", planet="ice", world="Niflheim", owner="mandate", x=41, y=-1, pop=1,
         about="ice colonies and the Mandate's shipbreakers, who turn wrecks into warships"),
    dict(name="Kharon", star="red_dwarf", planet="barren", world="Asphodel", owner="mandate", x=47, y=11, pop=40,
         about="the Mandate capital, seat of the Archons, the Hall of the Ferried where the dead of the Silence are named"),
]
LINKS = [("Concordia", "Meridian"), ("Meridian", "Aurelia"), ("Meridian", "Veyra"), ("Aurelia", "Cassia"),
         ("Aurelia", "Thule"), ("Cassia", "Veyra"), ("Cassia", "Thule"), ("Veyra", "Nemet"), ("Thule", "Ophir"),
         ("Thule", "Erebus"), ("Ophir", "Niflheim"), ("Ophir", "Kharon"), ("Erebus", "Nemet"), ("Erebus", "Kharon"),
         ("Nemet", "Niflheim"), ("Niflheim", "Kharon")]

OWNER_WORDS = {"astra": "ASTRA", "mandate": "Kharon Mandate", "guilds": "Free Guilds (neutral)",
               "contested": "contested", "silent": "silent (no contact)"}


class WarMap:
    def __init__(self, save_path: str | None = None) -> None:
        self.save_path = save_path or os.path.join(SAVE_DIR, "war.json")
        self.reset()

    # ------------------------------------------------------------------------------------------------- state
    def reset(self) -> None:
        self.systems: dict[str, dict[str, Any]] = {s["name"]: dict(copy.deepcopy(s), threat=0, notes=[]) for s in SECTOR}
        self.systems["Thule"]["threat"] = 2
        self.systems["Aurelia"]["threat"] = 1
        self.links: dict[str, list[str]] = {s["name"]: [] for s in SECTOR}
        for a, b in LINKS:
            self.links[a].append(b)
            self.links[b].append(a)
        self.current = "Aurelia"
        self.news: list[str] = []
        self.day = 1

    def find(self, name: str) -> str | None:
        n = (name or "").strip().lower()
        for k in self.systems:
            if k.lower() == n or n.startswith(k.lower()):
                return k
        return None

    def linked(self, a: str, b: str) -> bool:
        return b in self.links.get(a, [])

    def arrived(self, name: str) -> None:
        k = self.find(name)
        if k:
            self.current = k
            self.save()

    def update(self, system: str, owner: str | None = None, threat: int | None = None, note: str | None = None) -> str:
        """The director moves the war. Returns what changed (for the campaign log)."""
        k = self.find(system)
        if not k:
            return f"(no system {system} in the March)"
        s = self.systems[k]
        changed = []
        if owner in OWNERS and owner != s["owner"]:
            changed.append(f"{k} now {OWNER_WORDS[owner]} (was {OWNER_WORDS[s['owner']]})")
            s["owner"] = owner
        if threat is not None and 0 <= int(threat) <= 3 and int(threat) != s["threat"]:
            s["threat"] = int(threat)
            changed.append(f"{k} threat {int(threat)}")
        if note:
            s["notes"] = (s["notes"] + [note.strip()])[-3:]
            changed.append(f"{k}: {note.strip()}")
        self.save()
        return "; ".join(changed) or f"{k} unchanged"

    def add_news(self, text: str) -> None:
        self.news = (self.news + [text.strip()])[-8:]
        self.save()

    # -------------------------------------------------------------------------------------------- the views
    def brief(self, detail: bool = True) -> str:
        """The March in a few lines, for the director, the admiral and the crew."""
        lines = []
        for k, s in self.systems.items():
            here = "  <- the Aquila is here" if k == self.current else ""
            threat = ["quiet", "raids", "under attack", "front line"][s["threat"]]
            line = f"- {k} [gates: {', '.join(self.links[k])}] {OWNER_WORDS[s['owner']]}, {threat}; {s['star'].replace('_', '-')} star, " \
                   f"{s['planet'].replace('_', ' ')} world {s['world']}"
            if detail:
                line += f"; {s['about']}"
                if s["notes"]:
                    line += " | now: " + " / ".join(s["notes"])
            lines.append(line + here)
        return "\n".join(lines)

    def crew_view(self) -> str:
        """Compact, for the crew: where we are, where the gate leads, who holds what, the latest news."""
        k = self.current
        by_owner: dict[str, list[str]] = {}
        for n, x in self.systems.items():
            by_owner.setdefault(OWNER_WORDS[x["owner"]], []).append(n)
        out = [f"The Aquila is in the {k} system; its Janus Gate reaches {', '.join(self.links.get(k, []))}.",
               "Holdings: " + "; ".join(f"{o}: {', '.join(v)}" for o, v in by_owner.items()) + "."]
        notes = [f"{n}: {x['notes'][-1]}" for n, x in self.systems.items() if x["notes"]]
        if notes:
            out.append("Situation: " + " / ".join(notes[-5:]) + ".")
        if self.news:
            out.append("Latest fleet news: " + " / ".join(self.news[-3:]))
        return " ".join(out)

    def game_payload(self) -> dict[str, Any]:
        """What the game needs: looks for the gates, links for routing, the plot for the holo table."""
        return {"current": self.current, "systems": [
            {"name": k, "star_class": s["star"], "planet_type": s["planet"], "planet_name": s["world"], "owner": s["owner"],
             "threat": s["threat"], "x": s["x"], "y": s["y"], "links": self.links[k], "pop": s.get("pop", 0)}
            for k, s in self.systems.items()]}

    # ---------------------------------------------------------------------------------------------- saving
    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.save_path), exist_ok=True)
            tmp = self.save_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"saved": time.time(), "current": self.current, "day": self.day, "news": self.news,
                           "systems": {k: {x: s[x] for x in ("owner", "threat", "notes")} for k, s in self.systems.items()}},
                          f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.save_path)
        except OSError:
            log.exception("could not save the war map")

    def load(self) -> bool:
        try:
            with open(self.save_path, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        self.reset()
        for k, v in (d.get("systems") or {}).items():
            if k in self.systems:
                self.systems[k].update({x: v[x] for x in ("owner", "threat", "notes") if x in v})
        self.current = d.get("current", self.current) if d.get("current") in self.systems else self.current
        self.news = d.get("news", [])
        self.day = d.get("day", 1)
        return True
