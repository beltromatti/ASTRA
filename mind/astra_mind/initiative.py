"""The initiative watch: the officers keep playing when the Captain is not talking.

While the ship is in a fight or under a threat, a cheap periodic check lets each officer adjust their own console within their
delegation and the Captain's standing orders — the helm keeps the bow on the action, tactical retargets when a target dies,
sensors re-scans a lost contact, flight recalls a mauled squadron, ops puts the viewscreen on what matters — or propose it
(delegation advise), in at most one or two short lines and only when it means something. It replaces nothing the code does at
every tick (the executors run the modes); it is the mind's part: intentions.

It is a cadence and a filter, not a model: `Watch.tick()` looks at the ship state and decides whether a check is due (adaptive
10-20 s, sooner on a significant event, skipped when the picture did not change since the last one, never while the Captain
is speaking or being answered) and returns the check to run; the server puts it in the crew's event queue, where it is
answered by one model call (the `watch` role) with a compact prompt of its own. The problems found by the tactical advisor
(server.tactical_flags / picture_flag) ride in the same check: one turn, one voice, no duplicate advice."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from . import stations as station_model
from .crew import CAPTAIN_WORD, CREW, DUTIES_V2, LANG_NAMES

log = logging.getLogger("astra.watch")

# an event that may change what the officers should do (matched in the executors' own words: docs/contratto_postazioni.md §6)
SIGNIFICANT = re.compile(r"destroyed|ended|is gone|lost|released|new contact|appears|identified|opens fire|incoming|missile|mauled|"
                         r"critical|breach|jamming|retreat|fleeing|bingo|winchester|no target|out of reach|complete", re.I)


@dataclass
class Check:
    """A due check: the facts for the crew's turn."""
    text: str                    # the event text the server queues ("bridge: watch — ...")
    digest: str
    urgent: bool = False


@dataclass
class Watch:
    base_s: float = 16.0                     # seconds between checks when the picture keeps changing (10-20, by intensity)
    settle_s: float = 1.6                    # after a significant event, wait this long for the rest of the burst
    quiet_s: float = 7.0                     # never within this many seconds of the Captain's last words
    min_gap_s: float = 4.0
    last_run: float = 0.0
    last_digest: str = ""
    quiet_runs: int = 0                      # consecutive checks that changed nothing: the cadence relaxes
    _events: list[str] = field(default_factory=list)
    _event_t: float = 0.0                    # when the first unhandled significant event arrived
    _board: str = ""                         # the consoles as they were at the last check (to say what changed)
    runs: int = 0
    skipped: int = 0

    # ------------------------------------------------------------------------------------------------ input
    def note(self, text: str, now: float | None = None) -> None:
        """A ship event (any): kept for the next check when it may change what the officers should do."""
        if SIGNIFICANT.search(text) and not text.startswith(("director:", "story:", "medbay:", "flight: controller")):
            self._events = (self._events + [text.strip()[:220]])[-8:]
            self._event_t = self._event_t or (now if now is not None else time.monotonic())

    def reset(self) -> None:
        self._events.clear()
        self._event_t = 0.0
        self.last_digest = ""
        self.quiet_runs = 0

    # ------------------------------------------------------------------------------------------------ the picture
    @staticmethod
    def contacts(state: dict[str, Any]) -> tuple[list[dict], list[dict], list[dict]]:
        cs = state.get("contacts", []) or []
        hostile = [c for c in cs if str(c.get("status", "")).startswith("hostile") and isinstance(c.get("range_km"), (int, float))]
        blind = [c for c in cs if str(c.get("status", "")).startswith(("bearing only", "JAMMING"))]
        friends = [c for c in cs if str(c.get("status", "")) in ("friendly",)]
        return hostile, blind, friends

    def active(self, state: dict[str, Any], flags: list[str]) -> bool:
        """A fight or a threat: hostiles on the plot, blind contacts, red alert, a problem the advisor found."""
        hostile, blind, _ = self.contacts(state)
        return bool(hostile or blind or flags or state.get("alert") == "red")

    def digest(self, state: dict[str, Any], flags: list[str]) -> str:
        """What matters, coarsely: two checks with the same digest have nothing new to decide."""
        hostile, blind, friends = self.contacts(state)
        lanes = []
        for sid, ss in (state.get("stations") or {}).items():
            if not isinstance(ss, dict):
                continue
            for lane, ls in station_model.lanes_of(ss).items():
                par = ls.get("params") or {}
                lanes.append((sid, lane, ls.get("mode"), par.get("target") or par.get("targets"), ss.get("delegation")))
        sh = (state.get("shields") or {}).get("strength_pct")
        parts = {
            "h": sorted((str(c.get("id")), int((c.get("range_km") or 0) // 2), int((c.get("hull_pct") or 0) // 25)) for c in hostile),
            "b": sorted(str(c.get("id")) for c in blind),
            "f": sorted((str(c.get("id")), int((c.get("hull_pct") or 100) // 25)) for c in friends),
            "l": lanes, "hull": int((state.get("hull_pct") or 100) // 10), "sh": int((sh if isinstance(sh, (int, float)) else 100) // 10),
            "heat": int(((state.get("thermal") or {}).get("heat_pct") or 0) // 10), "alert": state.get("alert"),
            "sq": sorted((k, str(v)[:24]) for k, v in (state.get("squadrons") or {}).items()),
            "flags": sorted(f.split(":", 1)[0] for f in flags),
        }
        return json.dumps(parts, sort_keys=True, default=str)

    # ------------------------------------------------------------------------------------------------ the cadence
    def tick(self, state: dict[str, Any], now: float, flags: list[str], picture: str | None, captain_t: float, busy: bool,
             held_back: bool = False) -> Check | None:
        """Called every couple of seconds. A `Check` when one is due; None otherwise.
        busy: the Captain's words are queued or being answered, or the crew is mid-turn, or the voice is far behind.
        held_back: the story forbids it now (abandoning, a board of inquiry)."""
        if held_back or busy or now - captain_t < self.quiet_s or not state.get("stations"):
            return None
        if not self.active(state, flags):
            if self._events:
                self._events.clear()
                self._event_t = 0.0
            self.quiet_runs = 0
            return None
        if now - self.last_run < self.min_gap_s:
            return None
        hostile, blind, _ = self.contacts(state)
        hull = state.get("hull_pct")
        intense = len(hostile) >= 3 or (isinstance(hull, (int, float)) and hull < 50) or any("incoming" in e or "missile" in e for e in self._events)
        interval = (self.base_s * 0.65 if intense else self.base_s) * (1.0 + min(self.quiet_runs, 3) * 0.35)
        digest = self.digest(state, flags + ([picture] if picture else []))
        event_due = bool(self._events) and now - (self._event_t or now) >= self.settle_s
        periodic_due = now - self.last_run >= interval
        if not event_due and not (periodic_due and digest != self.last_digest):
            if periodic_due:
                self.skipped += 1
            return None
        text = self._facts(state, flags, picture)
        return Check(text=text, digest=digest, urgent=event_due)

    def ran(self, check: Check, spoke_or_acted: bool, now: float | None = None) -> None:
        """A check has been answered."""
        self.last_run = now or time.monotonic()
        self.last_digest = check.digest
        self._events.clear()
        self._event_t = 0.0
        self.runs += 1
        self.quiet_runs = 0 if spoke_or_acted else self.quiet_runs + 1

    # ------------------------------------------------------------------------------------------------ the facts
    def _facts(self, state: dict[str, Any], flags: list[str], picture: str | None) -> str:
        hostile, blind, friends = self.contacts(state)
        lines = []
        if hostile:
            lines.append("Hostiles: " + "; ".join(
                f"{c.get('id')} {c.get('name') or c.get('class')} {c.get('range_km')} km brg {int(c.get('bearing_deg', 0)):03d} "
                f"hull {c.get('hull_pct', '?')}% shields {c.get('shields_pct', '?')}%" for c in hostile[:6]))
        if blind:
            lines.append("Bearings only (no range): " + ", ".join(f"{c.get('id')} brg {int(c.get('bearing_deg', 0)):03d}"
                                                                 f"{' jamming' if str(c.get('status', '')).startswith('JAM') else ''}" for c in blind[:5]))
        if friends:
            lines.append("Friends: " + "; ".join(f"{c.get('id')} {c.get('name')} {c.get('range_km')} km hull {c.get('hull_pct', '?')}%"
                                                  for c in friends[:4]))
        sh = (state.get("shields") or {})
        w = state.get("weapons") or {}
        lines.append(f"Ours: hull {state.get('hull_pct', '?')}%, shields {sh.get('strength_pct', '?')}% ({sh.get('mode', '')}), heat "
                     f"{(state.get('thermal') or {}).get('heat_pct', '?')}%, missiles: {str(w.get('missiles', ''))[:60]}, squadrons: "
                     + "; ".join(f"{k} {str(v)[:40]}" for k, v in (state.get('squadrons') or {}).items()))
        if self._events:
            lines.append("Since the last check: " + " | ".join(self._events[-6:]))
        board = station_model.board(state)
        if board != self._board and self._board:
            lines.append("(the consoles changed since the last check)")
        self._board = board
        if flags or picture:
            lines.append("Problems the plot found: " + "; ".join(flags + ([picture] if picture else [])))
        return "bridge: watch — " + " || ".join(lines)


# ================================================================================================ the crew's side of a check
WATCH_ASK = ("A routine WATCH CHECK of the fight: the Captain has not spoken. Look at the consoles and the facts above. For each "
             "console that needs something, its officer either (a) sets a mode on their own console — a `station` call, allowed only "
             "where the delegation is auto and inside the Captain's intent and standing orders — and says what they did in one short "
             "line, or (b) where the delegation is advise, or the step is the Captain's to take, PROPOSES it in one short sentence; "
             "or (c) does nothing. Most checks need nothing at all: then call no tool and say nothing (reply SILENT). Never repeat "
             "what an officer said in the last minute, never report what the Captain can see, never more than two lines in all. "
             "Typical good moves: retarget when a target has fallen and another hostile is inside reach; keep the bow on the action "
             "when the ship is idle in a fight; face the shields to the threat; scan a bearing-only contact or a lost track; put the "
             "viewscreen on the target the Captain cares about (and release it when it is lost); recall a mauled squadron; set the "
             "repair teams on what matters; take the radiators out when heat climbs. If two officers must act together, one short "
             "line each in the same turn.")

_WATCH_SYSTEM = """You are the bridge crew of the ASN Aquila, keeping watch in a fight. The player is the ship's Captain; you voice every
officer, each the live operator of a console. You know only what the consoles and the facts below say.

Speech: in {lang_name}, {captain} at most once, SHORT — one sentence of 6-16 words per officer, and never more than two lines in all.
Every line says what was set or proposed and on what; never a bare "aye". Proper names stay in English.

Consoles (`station` sets a persistent mode the ship's code then runs every tick; a new mode replaces the old in its [lane]):
{table}
Delegation: auto = act on your own within the Captain's intent and standing orders, then say what you did; advise = propose in one
sentence and wait for the Captain's go; manual = only on the Captain's orders. NEVER on your own: leave the system, retreat, abandon
ship, open or close a channel with an enemy, open fire where no order or standing order covers it (weapons free), start a new offensive.
Owners: helm = course and pursuit; tactical = weapons, shields, point defence; sensors = scans, emissions; ops = main viewscreen, holo
table, datapad, damage control; engineering = power, heat, reactor; comms = channels; flight = the flight groups; xo = coordination.

Officers (ids for `speak`):
{roster}

Standing orders from the Captain:
{standing}
How this Captain commands (the XO's read): {style}
The Captain's last orders: {orders}

Consoles now
{board}

Ship state
{state}"""


def watch_system(lang: str, state: dict[str, Any], standing: str, style: str, orders: str) -> str:
    roster = "\n".join(f"- {o.id}: {o.title} — {DUTIES_V2.get(o.id, o.duties)}. {o.personality}." for o in CREW.values() if o.id in DUTIES_V2)
    trimmed = {k: v for k, v in state.items() if not k.startswith("_") and k not in ("stations", "sim_time_s", "contacts", "bearing_convention",
                                                                                    "known_systems", "casualties", "medbay", "mess")}
    return _WATCH_SYSTEM.format(
        lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain"), table=station_model.describe(station_model.available_from_state(state)),
        roster=roster, standing=standing or "- none", style=style or "- unknown yet", orders=orders or "- none yet",
        board=station_model.board(state, {k: v.title for k, v in CREW.items()}) or "(no consoles)",
        state=json.dumps(trimmed, separators=(",", ":"), ensure_ascii=False))


def recent_orders(history: list[dict[str, Any]], n: int = 3) -> str:
    """The Captain's last few orders, from the crew's history (their words only)."""
    said = [m["content"][len("Captain: "):] for m in history if m.get("role") == "user" and str(m.get("content", "")).startswith("Captain: ")]
    return "; ".join(f'"{s.splitlines()[0][:100]}"' for s in said[-n:])
