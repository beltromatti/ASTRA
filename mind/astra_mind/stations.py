"""The bridge stations as the crew sees them: live consoles with persistent modes (docs/ARCHITETTURA.md §4).

This module is the single description of the `station` command — which stations exist, their lanes (independent
persistent modes), the modes with their parameters and defaults, and how far an officer may go on their own
initiative. Everything else derives from it: the JSON schema and the text of the `station` tool (tools.py), the
validation of the arguments before they reach the ship, the console board in the crew's prompt (crew.py), the
offline ship (local_ship.py) and the contract proposal for the game side (docs/contratto_postazioni.md).

Reading of the game's `ship_state.state.stations` (all optional, the mind adapts to what it finds):
    {"helm": {"officer": "helm", "delegation": "auto", "modes": ["hold", ...],          # `modes`: what this build supports
              "lanes": {"nav": {"mode": "intercept", "params": {...}, "until": "target_lost", "set_by": "captain",
                                "since": 812.4, "status": "closing on T-23 at 310 m/s, 14.2 km, ETA 1:10"}},
              "last_actions": ["..."]}, ...}
A station of the ARCHITETTURA shape (mode/params/until/status at the top level, no `lanes`) is read as one lane.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ------------------------------------------------------------------------------------------------ parameter kinds
NUM, INT, STR, BOOL, STRS = "number", "integer", "string", "boolean", "strings"

# what a target may be: a contact id from the plot, or a selector the executor re-evaluates every tick
SELECTORS = ("tactical_target", "nearest_hostile", "biggest_threat")
UNTIL_WORDS = ("done", "target_lost", "order")           # and "time:<seconds>"
DELEGATIONS = ("manual", "advise", "auto")
SIDES_SHIP = ("port", "starboard")
SQUADRONS = ("alpha", "bravo", "drones")
WEAPON_GROUPS = ("railguns", "lasers", "missiles", "torpedoes")
SECTORS = ("fore", "aft", "port", "starboard", "dorsal", "ventral")


@dataclass(frozen=True)
class P:
    """A mode parameter."""
    name: str
    kind: str
    desc: str = ""
    enum: tuple[str, ...] | None = None
    required: bool = False
    lo: float | None = None
    hi: float | None = None
    default: Any = None


@dataclass(frozen=True)
class Mode:
    name: str
    station: str
    lane: str
    params: tuple[P, ...] = ()
    until: str = "order"                     # default end condition
    summary: str = ""
    authority: str = "free"                  # free | engaged | captain — see `may_on_initiative`

    def param(self, name: str) -> P | None:
        return next((p for p in self.params if p.name == name), None)


@dataclass(frozen=True)
class Station:
    id: str
    lanes: tuple[str, ...]
    modes: dict[str, Mode] = field(default_factory=dict)
    summary: str = ""


def _target(required: bool = True, desc: str = "contact id (T-23) or a selector") -> P:
    return P("target", STR, desc, required=required)


def _speed() -> P:
    return P("speed_pct", NUM, "cap on the throttle, percent (0-100)", lo=0, hi=100)


def _mk(station: str, lane: str, name: str, summary: str, params: tuple[P, ...] = (), until: str = "order",
        authority: str = "free") -> Mode:
    return Mode(name, station, lane, params, until, summary, authority)


def _build() -> dict[str, Station]:
    m = _mk
    helm = [
        m("helm", "nav", "hold", "cancel any pursuit, keep the present heading; speed as given (0 = all stop), else unchanged",
          (_speed(),), "order"),
        m("helm", "nav", "course", "steer to a fixed heading and mark, then hold it",
          (P("heading_deg", NUM, "true bearing in the system plane, 0-359.99", required=True, lo=0, hi=359.99),
           P("mark_deg", NUM, "pitch, -90..90", lo=-90, hi=90, default=0), _speed()), "done", "captain"),
        m("helm", "nav", "intercept", "close on a contact and hold the standoff range, broadside inside it; the course follows the target",
          (_target(), P("standoff_km", NUM, "range to hold: railguns reach 10 km, lasers 4 km", lo=0.5, hi=40, default=6), _speed()),
          "target_lost", "engaged"),
        m("helm", "nav", "keep_on_bow", "keep the bow on the target (attitude only, speed unchanged): the Captain sees it through the window",
          (_target(),), "target_lost"),
        m("helm", "nav", "follow", "shadow a ship at a distance and on a side of it",
          (_target(), P("distance_km", NUM, "distance to keep", lo=0.3, hi=40, default=3),
           P("side", STR, "which side of the ship to keep", enum=("astern", "ahead", "port", "starboard"), default="astern")), "order", "engaged"),
        m("helm", "nav", "orbit", "circle a contact at a radius",
          (_target(), P("radius_km", NUM, "orbit radius", lo=0.5, hi=40, default=6)), "order", "engaged"),
        m("helm", "nav", "broadside", "present a broadside to the target (all turrets bear) and keep the range",
          (_target(), P("side", STR, "which side to present", enum=("port", "starboard", "best"), default="best"),
           P("range_km", NUM, "range to keep", lo=0.5, hi=40, default=6)), "target_lost", "engaged"),
        m("helm", "nav", "evade", "evasive manoeuvres against incoming fire; runs 30 s unless told otherwise",
          (P("pattern", STR, "how to evade", enum=("jink", "spiral", "away"), default="jink"),), "time:30"),
        m("helm", "nav", "retreat", "break off and run",
          (P("toward", STR, "gate | fleet | a contact id | away (from the nearest threat)", default="away"), _speed()), "order",
          "captain"),
        m("helm", "nav", "formation", "hold a slot on a friendly ship",
          (P("leader", STR, "contact id of the friendly ship", required=True),
           P("slot", STR, "the slot on the leader", enum=("ahead", "astern", "port", "starboard", "port_quarter", "starboard_quarter"),
             default="port_quarter")), "order", "captain"),
        m("helm", "nav", "transit", "fly to the Janus Gate's approach lane and go through (no turning back once in the lane)",
          (P("system", STR, "destination system, one the gate is tuned to", required=True),), "done", "captain"),
    ]
    tactical = [
        m("tactical", "engagement", "hold_fire", "no fire unless ordered", (), "order", "captain"),
        m("tactical", "engagement", "return_fire", "fire only at ships that fire on us (the default posture)", (), "order"),
        m("tactical", "engagement", "weapons_free", "engage any tracked hostile inside range at will, until told otherwise",
          (P("range_km", NUM, "only inside this range (default: each weapon's own)", lo=1, hi=40),), "order", "captain"),
        m("tactical", "engagement", "engage",
          "fire on the listed targets until they fall: assigns the weapons, keeps the cadence, retargets inside the list",
          (P("targets", STRS, "contact ids or selectors, in order of priority; 'hostiles' = every tracked hostile", required=True),
           P("weapons", STRS, "subset of railguns, lasers, missiles, torpedoes (default: all that reach)"),
           P("fire", STR, "sustained = keep firing; volley = one salvo per group then hold; conserve = only sure hits",
             enum=("sustained", "volley", "conserve"), default="sustained"),
           P("priority", STR, "which listed target first", enum=("ordered", "nearest", "weakest", "biggest_threat"), default="ordered")),
          "target_lost", "engaged"),
        m("tactical", "shields", "shields_balanced", "shields even on every sector", (), "order"),
        m("tactical", "shields", "shields_face_threat", "turn the strongest sector towards the incoming fire, continuously", (), "order"),
        m("tactical", "shields", "shields_sector", "fix the reinforced sector",
          (P("sector", STR, "fore | aft | port | starboard | dorsal | ventral", enum=SECTORS, required=True),), "order"),
        m("tactical", "shields", "shields_off", "shields down", (), "order", "captain"),
        m("tactical", "point_defense", "pd_auto", "point defence on automatic", (), "order"),
        m("tactical", "point_defense", "pd_protect", "point defence covers a friendly ship first",
          (P("target", STR, "contact id of the friendly ship", required=True),), "order"),
        m("tactical", "point_defense", "pd_off", "point defence off", (), "order", "captain"),
        m("tactical", "missiles", "missiles_normal", "missiles as the fire order says", (), "order"),
        m("tactical", "missiles", "missiles_conserve", "spare the magazines: only sure hits", (), "order"),
        m("tactical", "missiles", "missiles_saturate", "empty the cells in one salvo to saturate their point defence", (), "order", "captain"),
    ]
    sensors = [
        m("sensors", "emcon", "emcon", "emission control: silent = passive only, restricted, full = active sensors out (bigger signature)",
          (P("level", STR, "silent | restricted | full", enum=("silent", "restricted", "full"), required=True),), "order", "captain"),
        m("sensors", "scan", "scan_passive", "passive sensors only, keep the picture", (), "order"),
        m("sensors", "scan", "scan_sweep", "an active ping every so often (everyone hears it)",
          (P("every_s", NUM, "seconds between pings", lo=5, hi=300, default=30),), "order", "captain"),
        m("sensors", "scan", "scan_focus", "keep a focused scan on a contact until it is identified or lost",
          (_target(),), "done"),
        m("sensors", "ew", "ew_off", "no jamming", (), "order"),
        m("sensors", "ew", "ew_jam", "jam a contact's fire control",
          (_target(),), "target_lost", "captain"),
        m("sensors", "sigint", "sigint_on", "listen in on their datalinks and traffic", (), "order"),
        m("sensors", "sigint", "sigint_off", "stop listening in", (), "order"),
    ]
    ops = [
        m("ops", "viewscreen", "viewscreen_auto", "the director picks the subject: the fight, the threat, the strongest event", (), "order"),
        m("ops", "viewscreen", "viewscreen_forward", "the forward optical view",
          (P("zoom", NUM, "magnification, 1-40", lo=1, hi=40, default=1),), "order"),
        m("ops", "viewscreen", "viewscreen_target", "the camera on a contact, with the zoom; released when it is lost",
          (_target(), P("zoom", NUM, "magnification, 1-40 (default: fits the range)", lo=1, hi=40)), "target_lost"),
        m("ops", "viewscreen", "viewscreen_tactical", "the tactical plot on the main screen", (), "order"),
        m("ops", "viewscreen", "viewscreen_fleet", "the fleet: friendly ships and their status", (), "order"),
        m("ops", "viewscreen", "viewscreen_comms", "the open channel's party on screen",
          (P("party", STR, "contact id or 'fleet' (default: the open channel)"),), "order"),
        m("ops", "viewscreen", "viewscreen_damage", "the damage board", (), "order"),
        m("ops", "viewscreen", "viewscreen_sector", "the sector map", (), "order"),
        m("ops", "viewscreen", "viewscreen_off", "screen off: the true window", (), "order"),
        m("ops", "holo", "holo_tactical", "the holo table shows the battle around the Aquila",
          (P("range_km", NUM, "plot radius (default: fits the contacts)", lo=2, hi=200),), "order"),
        m("ops", "holo", "holo_sector", "the holo table shows the sector map", (), "order"),
        m("ops", "holo", "holo_ship", "the holo table shows one ship in detail", (_target(desc="contact id"),), "order"),
        m("ops", "holo", "holo_fleet", "the holo table shows the fleet", (), "order"),
        m("ops", "datapad", "datapad_push", "put a page on the Captain's datapad",
          (P("page", STR, "status | contacts | weapons | damage | flight | orders | comms | ship", required=True,
             enum=("status", "contacts", "weapons", "damage", "flight", "orders", "comms", "ship")),
           P("focus", STR, "a contact id for page 'ship' or 'contacts'")), "done"),
        m("ops", "damage_control", "dc_auto", "the four damage-control teams go where the worst is: fires, breaches, weapons, reactor", (), "order"),
        m("ops", "damage_control", "dc_priority", "steer the damage-control teams towards one thing first",
          (P("what", STR, "reactor | weapons | shields | sensors | engines | life_support | flight_deck | fires | breaches | casualties",
             required=True, enum=("reactor", "weapons", "shields", "sensors", "engines", "life_support", "flight_deck",
                                  "fires", "breaches", "casualties")),), "order"),
    ]
    engineering = [
        m("engineering", "power", "power_profile", "set the reactor's distribution by profile",
          (P("profile", STR, "balanced | offense (weapons up) | defense (shields up) | engines | sensors | flight_ops",
             required=True, enum=("balanced", "offense", "defense", "engines", "sensors", "flight_ops")),), "order"),
        m("engineering", "power", "power_custom", "set several systems' power at once (percent of nominal, budget 700%: raising one needs a cut elsewhere)",
          (P("shields_pct", NUM, "", lo=0, hi=150), P("weapons_pct", NUM, "", lo=0, hi=150), P("engines_pct", NUM, "", lo=0, hi=150),
           P("sensors_pct", NUM, "", lo=0, hi=150), P("life_support_pct", NUM, "", lo=0, hi=150),
           P("flight_deck_pct", NUM, "", lo=0, hi=150)), "order"),
        m("engineering", "heat", "heat_auto", "manage the heat by themselves: radiators out or in, cadence throttled to keep under the limit",
          (P("limit_pct", NUM, "heat ceiling", lo=30, hi=95, default=70),), "order"),
        m("engineering", "heat", "heat_radiators", "radiators fixed",
          (P("state", STR, "extended | retracted", enum=("extended", "retracted"), required=True),), "order"),
        m("engineering", "reactor", "reactor_normal", "the reactor at its normal rating", (), "order"),
        m("engineering", "reactor", "reactor_battle_short", "battle short: safeties bypassed for more output, for a limited time, at a risk",
          (), "time:120", "captain"),
    ]
    comms = [
        m("comms", "channel", "channel_mute", "the Captain's voice no longer goes out on the open channel", (), "order"),
        m("comms", "channel", "channel_unmute", "the Captain's voice goes out on the open channel again", (), "order"),
        m("comms", "listen", "listen_off", "no monitoring", (), "order"),
        m("comms", "listen", "listen_fleet", "monitor the fleet net and report", (), "order"),
        m("comms", "listen", "listen_enemy", "monitor and translate the enemy's channels", (), "order"),
        m("comms", "listen", "listen_all", "monitor everything", (), "order"),
    ]
    flight = [
        m("flight", "mission", "mission", "launch a flight group on a mission, or re-task it if airborne; it runs until it ends",
          (P("squadron", STR, "alpha (8 Falcon) | bravo (7 Hammer, torpedoes) | drones (12 Wasp)", enum=SQUADRONS, required=True),
           P("type", STR, "cap (close patrol, within 3 km) | escort | strike | recon | ew | sar | hold (stay on deck) | recall",
             enum=("cap", "escort", "strike", "recon", "ew", "sar", "hold", "recall"), required=True),
           P("target", STR, "contact id for strike/escort/recon/ew"),
           P("formation", STR, "wedge | line | screen | trail (optional)", enum=("wedge", "line", "screen", "trail")),
           P("rtb_when", STR, "come home when: mauled | winchester (out of weapons) | target_dead | never",
             enum=("mauled", "winchester", "target_dead", "never"))), "done"),
    ]
    xo = [
        m("xo", "delegation", "delegation", "how far an officer may act on their own: manual = only on orders, advise = proposes and "
          "waits for a go, auto = acts within orders and standing orders and informs",
          (P("station", STR, "helm | tactical | sensors | ops | engineering | comms | flight", required=True,
             enum=("helm", "tactical", "sensors", "ops", "engineering", "comms", "flight")),
           P("level", STR, "manual | advise | auto", enum=DELEGATIONS, required=True)), "order"),
    ]
    out: dict[str, Station] = {}
    for sid, modes, summary in (
            ("helm", helm, "course, speed, pursuit, formation, evasion"),
            ("tactical", tactical, "weapons, targets, shields, point defence, missile doctrine"),
            ("sensors", sensors, "emissions, scans, jamming, signals intelligence"),
            ("ops", ops, "the main viewscreen, the holo table, the Captain's datapad, damage control"),
            ("engineering", engineering, "power, heat, reactor"),
            ("comms", comms, "the channel and what is listened to"),
            ("flight", flight, "the flight groups' missions"),
            ("xo", xo, "delegation: how far each officer may act on their own")):
        lanes = tuple(dict.fromkeys(md.lane for md in modes))
        out[sid] = Station(sid, lanes, {md.name: md for md in modes}, summary)
    return out


STATIONS: dict[str, Station] = _build()
OFFICER_OF = {sid: sid for sid in STATIONS}          # the station id is the officer id (xo, helm, ops, ...)
MODE_INDEX: dict[str, Mode] = {name: md for st in STATIONS.values() for name, md in st.modes.items()}
STRATEGIC = {"transit", "retreat"}                   # never on an officer's own initiative, whatever the delegation

# parameters as one flat set (the schema the model sees): name -> (kind, description)
FLAT_PARAMS: dict[str, P] = {}
for _md in MODE_INDEX.values():
    for _p in _md.params:
        _old = FLAT_PARAMS.get(_p.name)
        if _old is None or (not _old.desc and _p.desc):
            FLAT_PARAMS[_p.name] = _p


# ------------------------------------------------------------------------------------------------ the tool
def _kind_schema(p: P) -> dict[str, Any]:
    if p.kind == STRS:
        return {"type": "array", "items": {"type": "string"}}
    return {"type": p.kind}


def params_schema() -> dict[str, Any]:
    """The `params` object: the union of every mode's parameters, all optional (the mode says which apply)."""
    props: dict[str, Any] = {}
    for name, p in FLAT_PARAMS.items():
        props[name] = _kind_schema(p)
    return {"type": "object", "properties": props, "additionalProperties": False}


def _param_text(p: P) -> str:
    """One parameter as the officer reads it: name, ? if optional, the choices or the default."""
    txt = p.name + ("" if p.required else "?")
    if p.enum is not None:
        txt += "=" + "|".join(p.enum)
    elif p.default is not None:
        txt += f"={p.default}"
    return txt


def _mode_line(md: Mode) -> str:
    args = ", ".join(_param_text(p) for p in md.params)
    return f"{md.name}({args})" if args else md.name


def describe(available: dict[str, Iterable[str] | None] | None = None) -> str:
    """The compact table of stations, lanes and modes (the tool's description and the crew's prompt use it).
    available: station id -> the modes this build supports (None = every mode of the station)."""
    lines = []
    for sid, st in STATIONS.items():
        if available is not None and sid not in available:
            continue
        modes = st.modes
        only = available.get(sid) if available else None
        by_lane: dict[str, list[str]] = {}
        for md in modes.values():
            if only is not None and md.name not in only:
                continue
            by_lane.setdefault(md.lane, []).append(_mode_line(md))
        if not by_lane:
            continue
        lanes = "; ".join(f"[{lane}] " + " | ".join(ms) for lane, ms in by_lane.items())
        lines.append(f"{sid} ({st.summary}): {lanes}")
    return "\n".join(lines)


def param_help(available: dict[str, Iterable[str] | None] | None = None) -> str:
    """Notes on the parameters that are not obvious from their names and choices (each once)."""
    seen: dict[str, str] = {}
    for st in STATIONS.values():
        if available is not None and st.id not in available:
            continue
        for md in st.modes.values():
            for p in md.params:
                if p.desc and p.enum is None and p.name not in seen and not p.name.endswith("_pct"):
                    seen[p.name] = p.desc
    return "; ".join(f"{k}: {v}" for k, v in seen.items())


def tool_description(available: dict[str, Iterable[str] | None] | None = None) -> str:
    return ("Set a console's PERSISTENT MODE: the ship's code then keeps doing it every tick until it ends or you change it "
            "(hold the bow on a ship, follow it, engage it until it falls, keep the viewscreen on it, shields facing the "
            "threat...). Use it for anything that should KEEP happening, and pick the mode by the meaning of the Captain's "
            "words. A single act (one salvo, decoys, a hail, one scan ping, a damage-control dispatch) is a one-shot tool "
            "instead. A new mode replaces the old one in the same [lane]; other lanes keep running. `until`: done | "
            "target_lost | order (until the order changes) | time:<seconds>; leave it out for the mode's default. A target is "
            "a contact id (T-23) or a selector: tactical_target | nearest_hostile | biggest_threat.\n"
            + describe(available) + "\nParameters: " + param_help(available))


def tool_schema(available: dict[str, Iterable[str] | None] | None = None) -> dict[str, Any]:
    stations = [s for s in STATIONS if available is None or s in available]
    modes = [md for s in stations for md in STATIONS[s].modes
             if available is None or available.get(s) is None or md in (available.get(s) or ())]
    return {"type": "function", "function": {
        "name": "station", "description": tool_description(available), "parameters": {
            "type": "object", "properties": {
                "station": {"type": "string", "enum": stations},
                "mode": {"type": "string", "enum": modes},
                "params": params_schema(),
                "until": {"type": "string", "description": "done | target_lost | order | time:<seconds> (default: the mode's own)"},
                "note": {"type": "string", "description": "why, in a few words (shown on the console log)"}},
            "required": ["station", "mode"], "additionalProperties": False}}}


# ------------------------------------------------------------------------------------------------ validation
def _num(v: Any) -> float | None:
    try:
        if isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize(args: dict[str, Any], available: dict[str, Iterable[str] | None] | None = None) -> tuple[dict[str, Any] | None, str]:
    """Check a `station` call. Returns (the command args to send, "") or (None, why not — in words the officer can use).
    Numbers are coerced and clamped to the mode's range; unknown parameters are dropped; a missing required one is an error."""
    st_id = str(args.get("station", "")).strip().lower()
    mode = str(args.get("mode", "")).strip().lower().replace("-", "_").replace(" ", "_")
    st = STATIONS.get(st_id)
    if st is None:
        return None, f"no such station '{st_id}' (stations: {', '.join(STATIONS)})"
    if available is not None and st_id not in available:
        return None, f"the {st_id} console is not on line in this build"
    md = st.modes.get(mode)
    if md is None:
        # the model often writes the lane first ("engagement.engage", "damage_control.auto") or drops the prefix ("balanced")
        lane, _, tail = mode.rpartition(".")
        found = [x for x in st.modes.values() if (not lane or x.lane == lane) and (x.name == tail or x.name.endswith("_" + tail))]
        md = found[0] if len(found) == 1 else None
        if md is None:
            return None, f"{st_id} has no mode '{mode}' (modes: {', '.join(st.modes)})"
    only = (available or {}).get(st_id)
    if only is not None and md.name not in only:
        return None, f"this build's {st_id} console does not have mode '{md.name}'"
    raw = args.get("params")
    raw = raw if isinstance(raw, dict) else {}
    out: dict[str, Any] = {}
    for p in md.params:
        v = raw.get(p.name)
        if v is None or v == "":
            if p.required:
                return None, f"{st_id} {md.name} needs '{p.name}'" + (f" ({p.desc})" if p.desc else "")
            continue
        if p.kind in (NUM, INT):
            x = _num(v)
            if x is None:
                return None, f"'{p.name}' must be a number, got {v!r}"
            if p.lo is not None:
                x = max(p.lo, x)
            if p.hi is not None:
                x = min(p.hi, x)
            out[p.name] = int(round(x)) if p.kind == INT else round(x, 2)
        elif p.kind == STRS:
            items = [str(i).strip() for i in (v if isinstance(v, list) else [v]) if str(i).strip()]
            if not items and p.required:
                return None, f"{st_id} {md.name} needs at least one '{p.name}'"
            if p.name == "weapons":
                bad = [i for i in items if i.lower() not in WEAPON_GROUPS]
                if bad:
                    return None, f"unknown weapon group {bad[0]!r} (railguns, lasers, missiles, torpedoes)"
                items = [i.lower() for i in items]
            out[p.name] = items
        else:
            s = str(v).strip()
            if p.enum is not None and s.lower() not in p.enum:
                return None, f"'{p.name}' must be one of {', '.join(p.enum)}, got {s!r}"
            out[p.name] = s.lower() if p.enum is not None else s
    until = str(args.get("until") or md.until).strip().lower()
    if not (until in UNTIL_WORDS or (until.startswith("time:") and _num(until[5:]) is not None)):
        until = md.until
    res: dict[str, Any] = {"station": st_id, "mode": md.name, "params": out, "until": until}
    if args.get("note"):
        res["note"] = str(args["note"]).strip()[:160]
    return res, ""


def may_on_initiative(cmd: dict[str, Any], delegation: str, standing_for: set[str]) -> tuple[bool, str]:
    """May an officer set this mode WITHOUT the Captain's order? (the officer's own initiative: a watch turn, an event)
    `standing_for`: the stations a standing order of the Captain's covers (they may do what the order is about).
    Hard limits only — what is wise beyond that is the officer's judgement, from the prompt."""
    st, mode = cmd["station"], cmd["mode"]
    if st == "xo":
        return False, "delegation is the Captain's to give"
    if mode in STRATEGIC:
        return False, f"{mode} is the Captain's decision"
    if st in standing_for:
        return True, ""
    if delegation == "manual":
        return False, f"{st} is on manual: only on the Captain's orders"
    if delegation == "advise":
        return False, f"{st} is on advise: propose it and wait for the go"
    md = MODE_INDEX.get(mode)
    if md is not None and md.authority == "captain":
        return False, f"{mode} needs the Captain's order (or a standing order)"
    return True, ""


# ------------------------------------------------------------------------------------------------ reading the state
def lanes_of(station_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The lanes of a station as the game reports them (or the ARCHITETTURA flat shape as one lane)."""
    if not isinstance(station_state, dict):
        return {}
    lanes = station_state.get("lanes")
    if isinstance(lanes, dict) and lanes:
        return {str(k): v for k, v in lanes.items() if isinstance(v, dict)}
    if station_state.get("mode"):
        md = MODE_INDEX.get(str(station_state["mode"]))
        return {md.lane if md else "main": {k: station_state.get(k) for k in
                                            ("mode", "params", "until", "set_by", "since", "status") if k in station_state}}
    return {}


def available_from_state(state: dict[str, Any] | None) -> dict[str, list[str] | None] | None:
    """Which stations (and modes) this game build has, from `stations` in the state; None: an older build without stations."""
    stations = (state or {}).get("stations")
    if not isinstance(stations, dict) or not stations:
        return None
    out: dict[str, list[str] | None] = {}
    for sid, ss in stations.items():
        if sid in STATIONS and isinstance(ss, dict):
            modes = ss.get("modes")
            out[sid] = [str(x) for x in modes] if isinstance(modes, list) and modes else None
    return out or None


def delegation_of(state: dict[str, Any] | None, station: str) -> str:
    ss = ((state or {}).get("stations") or {}).get(station)
    d = str((ss or {}).get("delegation") or "auto").lower()
    return d if d in DELEGATIONS else "auto"


def board(state: dict[str, Any] | None, titles: dict[str, str] | None = None) -> str:
    """The consoles as a human-readable board for the prompt: who runs what, since when, how it is going."""
    stations = (state or {}).get("stations")
    if not isinstance(stations, dict) or not stations:
        return ""
    now = _num((state or {}).get("sim_time_s"))
    lines = []
    for sid in STATIONS:
        ss = stations.get(sid)
        if not isinstance(ss, dict):
            continue
        who = (titles or {}).get(sid, sid)
        head = f"- {sid} ({who}), delegation {delegation_of(state, sid)}"
        lanes = lanes_of(ss)
        if not lanes:
            lines.append(head + ": idle")
            continue
        parts = []
        for lane, ls in lanes.items():
            mode = ls.get("mode") or "idle"
            par = ls.get("params") or {}
            ptxt = ",".join(f"{k}={v if not isinstance(v, list) else '/'.join(map(str, v))}" for k, v in par.items()) if isinstance(par, dict) else ""
            since = ""
            t0 = _num(ls.get("since"))
            if now is not None and t0 is not None and now >= t0:
                since = f", {int(now - t0)} s ago"
            by = f" by {ls['set_by']}" if ls.get("set_by") else ""
            until = f" until {ls['until']}" if ls.get("until") and ls.get("until") != "order" else ""
            status = f" — {ls['status']}" if ls.get("status") else ""
            parts.append(f"[{lane}] {mode}{'(' + ptxt + ')' if ptxt else ''}{until}{by}{since}{status}")
        acts = ss.get("last_actions")
        tail = f" | last: {'; '.join(map(str, acts[-2:]))}" if isinstance(acts, list) and acts else ""
        lines.append(head + ": " + " ; ".join(parts) + tail)
    return "\n".join(lines)
