"""How far each console's officer may act on their own: the Captain's word, kept (docs/brief/VOCI-3.md, 4).

Every console has a delegation (`manual`: only on the Captain's orders · `advise`: the officer proposes in one line and waits for his go · `auto`: they act inside his intent and
his standing orders, and say so). The game holds it (`stations.<id>.delegation`, the XO's `delegation` mode sets it) and starts every launch with `auto` everywhere, which on
5 October meant squadrons launched and a pursuit begun that nobody had asked for. Two things follow, and both are the mind's, because the game forgets and the Captain does not:

  - what COMMITS the ship starts on `advise` in a new campaign (the flight deck's launches and the helm's pursuits: the officer proposes, the Captain says go), and
  - what the Captain says («nessuno lancia senza il mio ordine», "Voss, decidi tu", «da qui in poi fate da soli») is kept with the campaign and put back in the game each time it is
    launched, so that he has to say it once.

This module is the memory and the arithmetic (what the game lacks of it); the server speaks to the game (`Mind.delegation_sync`) and listens to the XO's tool calls in the Captain's
own turns (`note_call`). Nothing here judges what an officer may do inside a level: that is `stations.may_on_initiative` and the officers' doctrine."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import stations as station_model

log = logging.getLogger("astra.delegation")

LEVELS = ("manual", "advise", "auto")
# what commits the ship waits for the Captain's go in a new campaign; the consoles that keep the ship alive (defence, repairs, power, the picture, the channels) act inside his intent
DEFAULTS = {"flight": "advise", "helm": "advise"}
CONSOLES = tuple(s for s in station_model.STATIONS if s != "xo")


class Delegation:
    """The Captain's levels for the consoles, by station id. `path` is a function (the campaign's folder moves with the saved game)."""

    def __init__(self, path: Any = None) -> None:
        self._path = path
        self.levels: dict[str, str] = dict(DEFAULTS)
        self.active = False                     # no campaign chosen yet (the title menu): nothing is put in the game
        self.sent: dict[str, str] = {}          # what was last asked of the game (a level it refuses is not asked again until it changes)

    # ------------------------------------------------------------------------------------------------ the campaign
    def begin(self, new: bool) -> None:
        """The Captain chose a campaign: a new one starts from the defaults, the saved one from what he had set."""
        self.levels = dict(DEFAULTS)
        if new:
            self._write()                       # (a campaign that starts over does not inherit the last one's levels when it is continued)
        else:
            self.levels.update(self._read())
        self.sent.clear()
        self.active = True
        log.info("delegation (%s campaign): %s", "new" if new else "saved", ", ".join(f"{k} {v}" for k, v in sorted(self.levels.items())) or "none")

    def stop(self) -> None:
        self.active = False

    def set(self, station: str, level: str) -> bool:
        """The Captain set a console's level (the XO's call in his turn succeeded): kept. False when it is not a console or a level."""
        st, lv = str(station).strip().lower(), str(level).strip().lower()
        if st not in CONSOLES or lv not in LEVELS:
            return False
        self.levels[st] = lv
        self.sent.pop(st, None)
        self._write()
        return True

    def note_call(self, name: str, args: dict[str, Any], result: dict[str, Any]) -> bool:
        """A tool call of the Captain's turn: when it is the XO's `delegation` mode and it worked, keep it. Returns True when something was kept."""
        if name != "station" or not result.get("ok"):
            return False
        if str(args.get("station", "")).lower() != "xo" or str(args.get("mode", "")).lower() != "delegation":
            return False
        p = args.get("params") or {}
        return self.set(str(p.get("station") or ""), str(p.get("level") or p.get("delegation") or ""))

    # ------------------------------------------------------------------------------------------------ what the game lacks
    def pending(self, state: dict[str, Any] | None) -> list[tuple[str, str]]:
        """The (console, level) pairs the game does not have yet, from its state. Nothing before a campaign is chosen, or while the game has no consoles to ask."""
        if not self.active or not (state or {}).get("stations"):
            return []
        out = []
        for st, lv in self.levels.items():
            if st in (state or {}).get("stations", {}) and station_model.delegation_of(state, st) != lv and self.sent.get(st) != lv:
                out.append((st, lv))
        return out

    def wire(self, station: str, level: str) -> dict[str, Any]:
        """The game's own command for it (the XO's console, the `delegation` mode)."""
        cmd, err = station_model.normalize({"station": "xo", "mode": "delegation", "params": {"station": station, "level": level}}, None)
        if cmd is None:
            raise ValueError(err)
        return station_model.to_wire(cmd, by="captain")

    def asked(self, station: str, level: str) -> None:
        self.sent[station] = level

    # ------------------------------------------------------------------------------------------------ the file
    def _file(self) -> str | None:
        try:
            return self._path() if callable(self._path) else self._path
        except Exception:  # noqa: BLE001
            return None

    def _read(self) -> dict[str, str]:
        p = self._file()
        if not p or not os.path.exists(p):
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
            return {k: v for k, v in raw.items() if k in CONSOLES and v in LEVELS}
        except (OSError, ValueError):
            log.warning("the saved delegation could not be read: %s", p)
            return {}

    def _write(self) -> None:
        p = self._file()
        if not p:
            return
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.levels, f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except OSError:
            log.warning("the delegation could not be saved: %s", p)
