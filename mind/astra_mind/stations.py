"""The bridge stations as the crew sees them: live consoles with persistent modes (docs/ARCHITETTURA.md §4).

This module is the single description of the `station` command on the mind's side. It has two faces:

* the CREW's vocabulary — one flat, self-describing name per mode (`shields_face_threat`, `viewscreen_target`, `scan_focus`), so
  that a model picks the right one from the meaning of the Captain's words; the JSON schema and the text of the `station` tool
  (tools.py), the validation of the arguments, the console board of the crew's prompt (crew.py), the initiative watch and the
  offline ship (local_ship.py) all derive from it;
* the GAME's vocabulary — what UAstraStationsSubsystem (Source/ASTRA/AstraStations.cpp) really takes and reports: a command
  `{station, aspect, mode, params, until, note, by}` (an ASPECT is one independent persistent mode of a station: "course",
  "engagement", "shields"...; the flight station has one per squadron) and a state
  `stations.<id> = {officer, delegation, status, modes: {aspect: {mode, params, until, set_by, for_s}}, recent: [...]}`.
  `to_wire` turns a checked crew command into the first, `from_wire` reads one back (the offline ship speaks the game's
  language), `lanes_of` reads the second into the crew's names. The table `_build()` is the ONLY place that knows both.

A lane of this module is a game aspect. What the game does not have (yet) is not in the table: electronic warfare and SIGINT
modes, a squadron `formation`, a fleet holo, datapad pages other than the game's five."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ------------------------------------------------------------------------------------------------ parameter kinds
NUM, INT, STR, BOOL, STRS, ZOOM = "number", "integer", "string", "boolean", "strings", "zoom"
ZOOM_WORDS = ("close", "wide", "max")             # (a zoom is a factor on the natural framing, 0.25-8, or a word: close = 2, max = 4, wide = 0.4)

UNTIL_WORDS = ("done", "target_lost", "order")           # and "time:<seconds>"
DELEGATIONS = ("manual", "advise", "auto")
SQUADRONS = ("alpha", "bravo", "drones")
WEAPON_GROUPS = ("railguns", "lasers", "missiles", "torpedoes")
SECTORS = ("forward", "aft", "port", "starboard", "dorsal", "ventral")
POWER_PROFILES = ("balanced", "combat", "evasive", "silent", "shields", "weapons", "engines")
DATAPAD_PAGES = ("overview", "contact", "damage", "fleet", "orders")
POWER_SYSTEMS = ("shields", "weapons", "engines", "sensors", "life_support", "flight_deck")


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
    alt: tuple[str, ...] = ()                # words that stand in for the value (a target may be `action`): shown, never enforced


@dataclass(frozen=True)
class Mode:
    name: str                                # the crew's name for the mode: unique across the ship
    station: str
    lane: str                                # the game's aspect it belongs to
    params: tuple[P, ...] = ()
    until: str = "order"                     # default end condition (what the game does with it)
    summary: str = ""
    authority: str = "free"                  # free | engaged | captain — see `may_on_initiative`
    native: str = ""                         # the game's name for the mode when it differs from `name` ("" = the same)

    def param(self, name: str) -> P | None:
        return next((p for p in self.params if p.name == name), None)

    @property
    def game_mode(self) -> str:
        return self.native or self.name


@dataclass(frozen=True)
class Station:
    id: str
    lanes: tuple[str, ...]
    modes: dict[str, Mode] = field(default_factory=dict)
    summary: str = ""


def _target(required: bool = True, desc: str = "contact id from the plot (T-23)") -> P:
    return P("target", STR, desc, required=required)


def _action_target() -> P:
    """A target that may also be `action`: whatever the fight is about now (tactical's target, else the nearest hostile), read again
    on every tick by the game: the console follows the fight from one target to the next, and waits when there is no fight."""
    return P("target", STR, "contact id from the plot (T-23), or `action`: whatever the fight is about now", required=True, alt=("action",))


def _speed() -> P:
    return P("speed_pct", NUM, "throttle, percent (0-100)", lo=0, hi=100)


def _mk(station: str, lane: str, name: str, summary: str, params: tuple[P, ...] = (), until: str = "order",
        authority: str = "free", native: str = "") -> Mode:
    return Mode(name, station, lane, params, until, summary, authority, native)


def _build() -> dict[str, Station]:
    m = _mk
    helm = [
        m("helm", "course", "hold", "cancel any pursuit and keep the present heading; in a fight the bow comes round to the action "
          "by itself unless face_action is false", (P("face_action", BOOL, "false: keep the heading even in a fight", default=True),)),
        m("helm", "course", "course", "steer to a heading and mark (default: the present ones) and/or set the speed; 'all stop' is "
          "speed_pct 0", (P("heading_deg", NUM, "true bearing in the system plane, 0-359.99", lo=0, hi=359.99),
                          P("mark_deg", NUM, "pitch, -90..90", lo=-90, hi=90), _speed()), "order", "captain"),
        m("helm", "course", "intercept", "close on a contact and hold the standoff range, broadside inside it; the course follows the target",
          (_target(), P("standoff_km", NUM, "range to hold: railguns reach 10 km, lasers 4 km", lo=0.5, hi=40, default=6), _speed()),
          "target_lost", "engaged"),
        m("helm", "course", "keep_on_bow", "keep the bow on the target (attitude only, speed unchanged): the Captain sees it through the window; "
          "with target `action` the bow follows the fight from one target to the next by itself, and waits when there is none",
          (_action_target(),), "target_lost"),
        m("helm", "course", "follow", "shadow a ship at a distance and on a side of it",
          (_target(), P("distance_km", NUM, "distance to keep", lo=0.3, hi=40, default=2),
           P("side", STR, "which side of the ship to keep", enum=("astern", "port", "starboard", "above", "below"), default="astern")),
          "target_lost", "engaged"),
        m("helm", "course", "orbit", "circle a contact at a radius",
          (_target(), P("radius_km", NUM, "orbit radius", lo=0.5, hi=40, default=8),
           P("direction", STR, "counter-clockwise or clockwise", enum=("ccw", "cw"), default="ccw")), "target_lost", "engaged"),
        m("helm", "course", "broadside", "present a broadside to the target (all turrets bear) and keep the range",
          (_target(), P("side", STR, "which side to present", enum=("port", "starboard", "best"), default="best"),
           P("range_km", NUM, "range to keep", lo=0.5, hi=40, default=8)), "target_lost", "engaged"),
        m("helm", "course", "evade", "evasive manoeuvres against incoming fire (jinks every few seconds), full ahead; runs 45 s unless told otherwise",
          (), "time:45"),
        m("helm", "course", "retreat", "break off and run: full ahead away from the threats", (), "order", "captain"),
        m("helm", "course", "formation", "hold a slot on a friendly ship (default: the fleet's flagship)",
          (P("target", STR, "contact id of the friendly ship to keep station on (default: the flagship)"),
           P("slot", STR, "the slot on it", enum=("astern", "port", "starboard", "above", "below"), default="astern"),
           P("distance_km", NUM, "distance to keep", lo=0.3, hi=40, default=3)), "target_lost", "captain"),
        m("helm", "course", "transit", "fly to the Janus Gate's approach lane and go through (no turning back once in the lane)",
          (P("system", STR, "destination system, one the gate is tuned to", required=True),), "order", "captain"),
    ]
    tactical = [
        m("tactical", "engagement", "hold_fire", "no fire unless ordered", (), "order", "captain"),
        m("tactical", "engagement", "return_fire", "fire only at ships that fire on us (the default posture)", (), "order"),
        m("tactical", "engagement", "weapons_free", "engage any tracked hostile inside range at will, until told otherwise",
          (P("range_km", NUM, "only inside this range (default 25 km)", lo=1, hi=40),), "order", "captain"),
        m("tactical", "engagement", "engage",
          "fire on the listed targets until they fall: assigns the weapons, keeps the cadence, moves on to the next in the list",
          (P("targets", STRS, "contact ids, in order of priority; 'hostiles' = every hostile warship, as a standing order: the best one "
             "in reach (whoever fires on us first, else the nearest), new contacts included, it waits when there is none", required=True),
           P("weapons", STRS, "subset of railguns, lasers, missiles, torpedoes (default: railguns, lasers, missiles)"),
           P("fire", STR, "sustained = keep firing; volley = one missile salvo then hold; conserve = fewer missiles, only sure hits",
             enum=("sustained", "volley", "conserve"), default="sustained")),
          "target_lost", "engaged"),
        m("tactical", "shields", "shields_balanced", "shields even on every sector", (), "order", native="balanced"),
        m("tactical", "shields", "shields_face_threat", "turn the strongest sector towards the incoming fire, continuously (the default)",
          (), "order", native="face_threat"),
        m("tactical", "shields", "shields_sector", "fix the reinforced sector",
          (P("sector", STR, "forward | aft | port | starboard | dorsal | ventral", enum=SECTORS, required=True),), "order",
          native="sector"),
        m("tactical", "shields", "shields_off", "shields down", (), "order", "captain"),
        m("tactical", "point_defense", "pd_auto", "point defence on automatic", (), "order"),
        m("tactical", "point_defense", "pd_protect", "point defence covers a friendly ship first",
          (P("target", STR, "contact id of the friendly ship", required=True),), "order", native="protect"),
        m("tactical", "point_defense", "pd_off", "point defence off", (), "order", "captain"),
        m("tactical", "missiles", "missiles_normal", "missiles as the fire order says", (), "order", native="normal"),
        m("tactical", "missiles", "missiles_conserve", "spare the magazines: fewer missiles, only sure hits", (), "order", native="conserve"),
        m("tactical", "missiles", "missiles_saturate", "empty the cells in salvos of eight to saturate their point defence", (), "order",
          "captain", native="saturate"),
    ]
    sensors = [
        m("sensors", "emcon", "emcon", "emission control: silent = passive only, restricted = the normal state, full = active sensors "
          "out (a bigger signature)",
          (P("level", STR, "silent | restricted | full", enum=("silent", "restricted", "full"), required=True),), "order", "captain"),
        m("sensors", "scan", "scan_passive", "passive sensors only, keep the picture", (), "order", native="passive"),
        m("sensors", "scan", "scan_sweep", "an active ping every so often (everyone hears it)",
          (P("every_s", NUM, "seconds between pings (at least 15)", lo=15, hi=300, default=60),), "order", "captain", native="sweep"),
        m("sensors", "scan", "scan_focus", "keep a focused scan on a contact until it is tracked or lost; with target `action` the scan "
          "follows the fight", (_action_target(),), "target_lost", native="focus"),
    ]
    ops = [
        m("ops", "viewscreen", "viewscreen_auto", "the director picks the subject: the fight, the threat, the strongest event", (), "order",
          native="auto"),
        m("ops", "viewscreen", "viewscreen_forward", "the forward optical view",
          (P("zoom", ZOOM, "close | max | wide, or a factor 0.25-8 on the natural framing (2 = twice as tight)", lo=0.25, hi=8),),
          "order", native="forward"),
        m("ops", "viewscreen", "viewscreen_target", "the camera on a contact, with the zoom; released when it is lost; with target `action` "
          "the screen follows the fight from one target to the next by itself",
          (_action_target(), P("zoom", ZOOM, "close | max | wide, or a factor 0.25-8 on the natural framing (default 1: the subject fills the frame)",
                        lo=0.25, hi=8)), "target_lost", native="target"),
        m("ops", "viewscreen", "viewscreen_tactical", "the tactical plot on the main screen", (), "order", native="tactical"),
        m("ops", "viewscreen", "viewscreen_fleet", "the fleet: friendly ships and their status", (), "order", native="fleet"),
        m("ops", "viewscreen", "viewscreen_comms", "the open channel's party on screen",
          (P("party", STR, "contact id or 'fleet' (default: the open channel)"),), "order", native="comms"),
        m("ops", "viewscreen", "viewscreen_damage", "the damage board", (), "order", native="damage"),
        m("ops", "viewscreen", "viewscreen_sector", "the sector map", (), "order", native="sector"),
        m("ops", "viewscreen", "viewscreen_off", "screen off: the true window", (), "order", native="off"),
        m("ops", "holo", "holo_tactical", "the holo table shows the battle around the Aquila", (), "order", native="tactical"),
        m("ops", "holo", "holo_sector", "the holo table shows the sector map", (), "order", native="sector"),
        m("ops", "holo", "holo_ship", "the holo table shows the Aquila herself: a cutaway deck by deck, sections A-H, the damage where "
          "it is (fires, breaches, damaged conduits), the damage-control teams on their way or at work, where the Captain is", (), "order",
          native="ship"),
        m("ops", "datapad", "datapad_push", "put a page on the Captain's datapad (Tab shows it)",
          (P("page", STR, "overview | contact (a dossier: give focus) | damage | fleet | orders", required=True, enum=DATAPAD_PAGES),
           P("focus", STR, "a contact id, for the page 'contact'")), "order", native="push"),
        m("ops", "damage_control", "dc_auto", "the damage-control teams go where the worst is: breaches, fires, then what a fight needs",
          (), "order", native="auto"),
        m("ops", "damage_control", "dc_priority", "steer the damage-control teams towards one thing first",
          (P("what", STR, "what first: breaches | fires | reactor | weapons | shields | engines | a deck", required=True),), "order",
          native="priority"),
    ]
    engineering = [
        m("engineering", "power", "power_profile", "set the reactor's distribution by profile: balanced (all nominal), combat "
          "(shields and weapons up), evasive (engines and shields up), silent (everything low, hard to detect), shields | weapons | "
          "engines (that system up)",
          (P("profile", STR, " | ".join(POWER_PROFILES), required=True, enum=POWER_PROFILES),), "order"),
        m("engineering", "power", "power_custom", "set several systems' power at once (percent of nominal; the reactor's budget is "
          "700%: raising one needs a cut elsewhere)",
          tuple(P(f"{s}_pct", NUM, "", lo=0, hi=150) for s in POWER_SYSTEMS), "order", native="custom"),
        m("engineering", "heat", "heat_auto", "manage the heat by themselves: radiators out when it climbs, in when it is low, coolant "
          "vent in an emergency", (), "order", native="auto"),
        m("engineering", "heat", "heat_radiators", "radiators fixed",
          (P("state", STR, "extended | retracted", enum=("extended", "retracted"), required=True),), "order"),
        m("engineering", "reactor", "reactor_normal", "the reactor at its normal rating", (), "order", native="normal"),
        m("engineering", "reactor", "reactor_battle_short", "battle short: the reactor past its safety limits — 800% of power to allocate "
          "instead of 700%, but +0.3%/s of heat, until `reactor_normal` (allocations above nominal are then scaled down)",
          (), "order", "captain", native="battle_short"),
    ]
    comms = [
        m("comms", "channel", "channel_mute", "the Captain's voice no longer goes out on the open channel", (), "order", native="mute"),
        m("comms", "channel", "channel_unmute", "the Captain's voice goes out on the open channel again", (), "order", native="unmute"),
        m("comms", "listen", "listen_fleet", "monitor the fleet net and report", (), "order", native="fleet"),
        m("comms", "listen", "listen_enemy", "monitor and translate the enemy's channels", (), "order", native="enemy"),
        m("comms", "listen", "listen_all", "monitor everything", (), "order", native="all"),
    ]
    flight = [
        m("flight", "mission", "mission", "launch a flight group on a mission, or re-task it if airborne; a strike or an escort that "
          "loses its target goes back on patrol by itself",
          (P("squadron", STR, "alpha (8 Falcon) | bravo (7 Hammer, torpedoes) | drones (12 Wasp)", enum=SQUADRONS, required=True),
           P("type", STR, "cap (close patrol, within 3 km) | escort | strike | ew | recon | sar | hold (stay on deck) | recall",
             enum=("cap", "escort", "strike", "ew", "recon", "sar", "hold", "recall"), required=True),
           P("target", STR, "contact id for strike, escort, ew and recon")), "order"),
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
            ("sensors", sensors, "emissions and scans"),
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
    if p.kind == ZOOM:
        return {"type": ["number", "string"]}
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
    if p.kind == ZOOM:
        return txt + "=close|max|wide|0.25-8"
    if p.enum is not None:
        txt += "=" + "|".join(p.enum)
    elif p.default is not None:
        txt += f"={p.default}"
    elif p.alt:
        txt += "=id|" + "|".join(p.alt)
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
            "target_lost | order (until the order changes) | time:<seconds> (the console goes back to its default mode); leave it "
            "out for the mode's default. A target is a contact id from the plot (T-23); for keep_on_bow, viewscreen_target and "
            "scan_focus it may also be `action` = whatever the fight is about now (tactical's target, else the nearest hostile): "
            "it follows the fight by itself.\n"
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
    """Check a `station` call. Returns (the crew's command, "") or (None, why not — in words the officer can use).
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
        if p.kind == ZOOM:
            if isinstance(v, str) and v.strip().lower() in ZOOM_WORDS:
                out[p.name] = v.strip().lower()
                continue
            x = _num(str(v).lower().lstrip("x")) if isinstance(v, str) else _num(v)
            if x is None:
                return None, f"'zoom' must be a number or one of {', '.join(ZOOM_WORDS)}, got {v!r}"
            out[p.name] = round(min(max(x, p.lo if p.lo is not None else 1), p.hi if p.hi is not None else 8), 2)
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
        elif p.kind == BOOL:
            out[p.name] = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "yes", "1")
        elif p.kind == STRS:
            items = [str(i).strip() for i in (v if isinstance(v, list) else [v]) if str(i).strip()]
            if not items and p.required:
                return None, f"{st_id} {md.name} needs at least one '{p.name}'"
            if p.name == "weapons":
                bad = [i for i in items if i.lower() not in WEAPON_GROUPS]
                if bad:
                    return None, f"unknown weapon group {bad[0]!r} (railguns, lasers, missiles, torpedoes)"
                items = [i.lower() for i in items]
            out[p.name] = ["hostiles" if i.lower() == "hostiles" else i for i in items]
        else:
            s = str(v).strip()
            if p.enum is not None:
                s = {"fore": "forward", "front": "forward", "rear": "aft", "left": "port", "right": "starboard"}.get(s.lower(), s.lower()) \
                    if p.name == "sector" else s.lower()
                if s not in p.enum:
                    return None, f"'{p.name}' must be one of {', '.join(p.enum)}, got {str(v).strip()!r}"
            elif p.name == "target" and s.lower() == "action":
                s = "action"
            out[p.name] = s
    if md.name == "course" and not ({"heading_deg", "mark_deg", "speed_pct"} & set(out)):
        return None, "course needs a heading, a mark or a speed"
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


# ================================================================================================ the game's vocabulary
_NATIVE_TO_MODE: dict[tuple[str, str], Mode] = {}
for _md in MODE_INDEX.values():
    if _md.station not in ("flight", "xo") and _md.name not in ("shields_sector", "emcon", "power_profile", "heat_radiators"):
        _NATIVE_TO_MODE[(_md.lane, _md.game_mode)] = _md
# the modes whose game name carries a parameter, and the game's own aliases
_EMCON = {"silent": "silent", "restricted": "restricted", "limited": "restricted", "full": "full"}
_RADIATORS = {"extended": "extended", "radiators_extended": "extended", "retracted": "retracted", "radiators_retracted": "retracted"}


def to_wire(cmd: dict[str, Any], by: str = "") -> dict[str, Any]:
    """A checked command (from `normalize`) as the game's `station` command takes it:
    {station, aspect, mode, params, until, note, by}. `by`: "captain" | "officer" (who decided; the game records it as set_by).
    Targets go as they are: contact ids, `action`, and `hostiles` in an engage (the game keeps that one as a standing order)."""
    md = MODE_INDEX[cmd["mode"]]
    p = dict(cmd.get("params") or {})
    st = cmd["station"]
    out: dict[str, Any] = {"station": st, "aspect": md.lane, "mode": md.game_mode, "until": cmd.get("until") or md.until}
    if md.name == "delegation":
        out["params"] = {"station": p["station"], "delegation": p["level"]}
    elif md.name == "mission":
        out["aspect"], out["mode"] = p["squadron"], p["type"]
        out["params"] = {"squadron": p["squadron"], **({"target": p["target"]} if p.get("target") else {})}
    elif md.name == "emcon":
        out["mode"], out["params"] = p["level"], {}
    elif md.name == "power_profile":
        out["mode"], out["params"] = p["profile"], {}
    elif md.name == "power_custom":
        out["params"] = {k[:-4]: v for k, v in p.items() if k.endswith("_pct")}
    elif md.name == "heat_radiators":
        out["mode"], out["params"] = p["state"], {}
    elif md.name == "shields_sector":
        out["mode"], out["params"] = p["sector"], {"sector": p["sector"]}
    else:
        if md.name == "broadside" and p.get("side") == "best":
            p["side"] = "auto"
        out["params"] = p
    if cmd.get("note"):
        out["note"] = cmd["note"]
    if by:
        out["by"] = by
    return out


def internal_of(aspect: str, native: str, params: dict[str, Any] | None = None) -> tuple[Mode | None, dict[str, Any]]:
    """What the game calls (aspect, mode, params) in the crew's words: (the Mode, its params), or (None, {}) for a mode this
    module does not know (a newer build)."""
    p = dict(params or {})
    aspect, native = str(aspect).lower(), str(native).lower()
    if aspect in SQUADRONS:
        t = p.get("target")
        return MODE_INDEX["mission"], {"squadron": aspect, "type": native, **({"target": t} if t else {})}
    if aspect == "emcon" and native in _EMCON:
        return MODE_INDEX["emcon"], {"level": _EMCON[native]}
    if aspect == "power" and native in POWER_PROFILES:
        return MODE_INDEX["power_profile"], {"profile": native}
    if aspect == "heat" and native in _RADIATORS:
        return MODE_INDEX["heat_radiators"], {"state": _RADIATORS[native]}
    if aspect == "shields" and (native in SECTORS or native == "sector"):
        sec = str(p.get("sector") or native)
        return MODE_INDEX["shields_sector"], {"sector": sec if sec in SECTORS else "forward"}
    md = _NATIVE_TO_MODE.get((aspect, native))
    if md is None:
        return None, {}
    if md.name == "broadside" and p.get("side") == "auto":
        p["side"] = "best"
    if md.name == "engage" and isinstance(p.get("targets"), list):
        p["targets"] = ["hostiles" if str(t).lower() == "hostiles" else t for t in p["targets"]]      # (the game stores ids in capitals)
    if isinstance(p.get("target"), str) and p["target"].lower() == "action":
        p["target"] = "action"
    if md.name == "power_custom":
        p = {f"{k}_pct": v for k, v in p.items()}
    return md, p


def from_wire(args: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """The reverse of `to_wire`: a `station` command as the game receives it -> the crew's command (checked like `normalize`).
    (None, why) when the game would refuse it: an unknown station, aspect or mode."""
    st_id = str(args.get("station", "")).strip().lower()
    st = STATIONS.get(st_id)
    if st is None:
        return None, f"no station '{st_id}' ({', '.join(STATIONS)})"
    raw = args.get("params") if isinstance(args.get("params"), dict) else {}
    mode = str(args.get("mode", "")).strip().lower()
    aspect = str(args.get("aspect", "")).strip().lower()
    if st_id == "xo":
        crew = {"station": "xo", "mode": "delegation", "params": {"station": raw.get("station", ""),
                                                                 "level": raw.get("delegation") or raw.get("level", "")}}
        return normalize(crew)
    if st_id == "flight":
        aspect = aspect or str(raw.get("squadron", "")).lower()
        mode = mode or str(raw.get("mission", "")).lower()
        if aspect not in SQUADRONS:
            return None, "flight: say which squadron (alpha, bravo, drones)"
        md, params = internal_of(aspect, mode, raw)
        if md is None:
            return None, f"flight has no mission '{mode}' for {aspect}"
        return normalize({"station": st_id, "mode": md.name, "params": params, "until": args.get("until"), "note": args.get("note")})
    if not mode:
        return None, f"{st_id}: which mode?"
    if not aspect:
        aspect = _aspect_for(st_id, mode)
    md, params = internal_of(aspect, mode, raw)
    if md is None or md.station != st_id:
        return None, f"{st_id} has no mode '{mode}'" + (f" for {aspect}" if aspect else "")
    return normalize({"station": st_id, "mode": md.name, "params": params, "until": args.get("until"), "note": args.get("note")})


_ASPECT_STATION = {md.lane: md.station for md in MODE_INDEX.values()}


def _aspect_for(station: str, native: str) -> str:
    """Which aspect a game mode name belongs to when the command does not say (the game's own table: a name shared by several
    aspects goes to the station's main one)."""
    hits = [lane for (lane, n), md in _NATIVE_TO_MODE.items() if n == native and md.station == station]
    for names, aspect in ((_EMCON, "emcon"), (POWER_PROFILES, "power"), (_RADIATORS, "heat"), (SECTORS, "shields")):
        if native in names and _ASPECT_STATION.get(aspect) == station:
            hits.append(aspect)
    if station == "ops" and "viewscreen" in hits:
        return "viewscreen"
    return hits[0] if hits else ""


# ------------------------------------------------------------------------------------------------ reading the state
def lanes_of(station_state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """The lanes of a station as the game reports them (`modes: {aspect: {mode, params, until, set_by, for_s}}`), each with the
    mode in the crew's name (and `native`, the game's). A mode this module does not know is kept under the game's name."""
    if not isinstance(station_state, dict):
        return {}
    modes = station_state.get("modes")
    if isinstance(modes, dict) and modes:
        out: dict[str, dict[str, Any]] = {}
        for aspect, ls in modes.items():
            if not isinstance(ls, dict):
                continue
            md, params = internal_of(aspect, ls.get("mode", ""), ls.get("params") if isinstance(ls.get("params"), dict) else None)
            params = params if md else dict(ls.get("params") or {})
            if params.get("face_action") is True:
                params.pop("face_action")                            # (the default: nothing to say)
            out[str(aspect)] = {**{k: v for k, v in ls.items() if k not in ("mode", "params")},
                                "mode": md.name if md else ls.get("mode"), "native": ls.get("mode"), "params": params}
        return out
    if station_state.get("mode"):                                    # the flat shape of the first sketch (one mode per station)
        md = MODE_INDEX.get(str(station_state["mode"]))
        return {md.lane if md else "main": {k: station_state.get(k) for k in
                                            ("mode", "params", "until", "set_by", "since", "status") if k in station_state}}
    return {}


def available_from_state(state: dict[str, Any] | None) -> dict[str, list[str] | None] | None:
    """Which stations this game build has, from `stations` in the state (None: an older build without stations). A build may also
    list the modes it supports (`supports: [...]`); the game as of now does not, and then every mode of the station is offered."""
    stations = (state or {}).get("stations")
    if not isinstance(stations, dict) or not stations:
        return None
    out: dict[str, list[str] | None] = {}
    for sid, ss in stations.items():
        if sid in STATIONS and isinstance(ss, dict):
            modes = ss.get("supports")
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
            if lane == "datapad" and not par:
                continue                                             # (nothing pushed yet)
            ptxt = ",".join(f"{k}={v if not isinstance(v, list) else '/'.join(map(str, v))}" for k, v in par.items()) if isinstance(par, dict) else ""
            ago = ""
            for_s, t0 = _num(ls.get("for_s")), _num(ls.get("since"))
            if for_s is not None:
                ago = f", {int(for_s)} s ago"
            elif now is not None and t0 is not None and now >= t0:
                ago = f", {int(now - t0)} s ago"
            by = f" by {ls['set_by']}" if ls.get("set_by") else ""
            until = f" until {ls['until']}" if ls.get("until") and ls.get("until") != "order" else ""
            status = f" — {ls['status']}" if ls.get("status") else ""
            parts.append(f"[{lane}] {mode}{'(' + ptxt + ')' if ptxt else ''}{until}{by}{ago}{status}")
        acts = ss.get("recent") or ss.get("last_actions")
        tail = f" | last: {'; '.join(map(str, acts[-2:]))}" if isinstance(acts, list) and acts else ""
        status = f" || {ss['status']}" if ss.get("status") else ""
        lines.append(head + ": " + " ; ".join(parts) + status + tail)
    if (state or {}).get("viewscreen"):
        lines.append(f"- main screen now: {state['viewscreen']}")
    action = str((state or {}).get("action_target") or "")
    if action:
        who = next((c.get("name") for c in (state or {}).get("contacts", []) or [] if str(c.get("id")) == action and c.get("name")), "")
        lines.append(f"- the action now (target `action`): {action}" + (f" ({who})" if who else ""))
    elif any("action" in str((ls.get("params") or {}).get("target", "")) for ss in stations.values() if isinstance(ss, dict)
             for ls in lanes_of(ss).values()):
        lines.append("- the action now (target `action`): none — no fight, the consoles on `action` are waiting")
    return "\n".join(lines)
