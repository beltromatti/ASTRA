"""Where the Captain is speaking, who can hear, whom they face, and whether a channel is open: the context of every
utterance (docs/ARCHITETTURA.md §3, `player_text.context`).

The game sends it with every word of the Captain's (`place`, `in_earshot`, `facing`, `channel{party, open, muted}`,
`pawn`). A build that does not send it yet gets the same picture inferred from what the mind already knows: the ship state
(`captain`, `medbay`, `mess`, `visitor`, `surface`) and the mind's own channel with the enemy commander. Nothing here decides
anything: it describes the room, and the router and the crew's prompt use it."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from .crew import CREW

BRIDGE = ("xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight")
PLACES = ("bridge", "quarters", "mess", "medbay", "engineering", "berthing", "flight_deck", "falcon", "planetside", "corridor")
# the slugs the game sends in `context.place` (the datapad's place) -> the names used here
PLACE_SLUGS = {"bridge": "bridge", "corridors": "corridor", "captains_quarters": "quarters", "main_engineering": "engineering",
               "mess_hall": "mess", "crew_berthing": "berthing", "medbay": "medbay", "flight_deck": "flight_deck",
               "in_a_falcon": "falcon", "planetside": "planetside"}

_PLACE_WORDS = (                                 # (text found in the ship state's `captain`, place)
    ("main engineering", "engineering"), ("mess hall", "mess"), ("crew berthing", "berthing"), ("medbay", "medbay"),
    ("flying a falcon", "falcon"), ("captain's quarters", "quarters"), ("flight deck", "flight_deck"), ("away from the bridge", "aboard"),
    ("on the bridge", "bridge"))


@dataclass
class Channel:
    """A radio or video channel the Captain has open with someone outside the room."""
    party: str = ""                     # contact id ("T-23"), "fleet", "flight" (the flight net), a port controller...
    name: str = ""                      # what the Captain would call them: "Ferryman Irina Vael (the Cocytus)"
    kind: str = "enemy"                 # enemy | fleet | flight | ally | port
    open: bool = True
    muted: bool = False                 # the Captain's voice does not go out
    heard_s: float | None = None        # seconds since the party last spoke to the Captain (None: not in this exchange)
    last_words: str = ""                # what the party last said on the channel (as comms heard it)
    said_s: float | None = None         # seconds since the Captain last spoke to the party
    screen: bool = False                # the party is on the main viewscreen

    @property
    def live(self) -> bool:
        """The Captain's words can reach the party."""
        return self.open and not self.muted

    @property
    def talking(self) -> bool:
        """An exchange is going on: the party spoke to the Captain a moment ago."""
        return self.heard_s is not None and self.heard_s <= 25.0


@dataclass
class Context:
    place: str = "bridge"
    in_earshot: tuple[str, ...] = ()
    facing: str | None = None           # an officer id, a person's speaker id, "viewscreen", "holo", None
    channel: Channel | None = None
    pawn: str = "seated"                # on_foot | seated | falcon | pod
    source: str = "inferred"            # game | inferred
    asleep: bool = False

    @property
    def on_bridge(self) -> bool:
        return self.place == "bridge"

    @property
    def channel_live(self) -> bool:
        return bool(self.channel and self.channel.live)


class Exchange:
    """The mind's memory of the talk with each party on the channel: who spoke last, when, and what they said."""

    def __init__(self) -> None:
        self._heard: dict[str, float] = {}
        self._said: dict[str, float] = {}
        self._words: dict[str, str] = {}

    def heard(self, party: str, words: str = "") -> None:
        self._heard[party] = time.monotonic()
        if words:
            self._words[party] = words

    def last_words(self, party: str) -> str:
        return self._words.get(party, "")

    def said(self, party: str) -> None:
        self._said[party] = time.monotonic()

    def ago(self, table: dict[str, float], party: str) -> float | None:
        t = table.get(party)
        return None if t is None else max(0.0, time.monotonic() - t)

    def reset(self) -> None:
        self._heard.clear()
        self._said.clear()
        self._words.clear()


def known_speakers(ids: Any) -> tuple[str, ...]:
    """The ids the game lists as within earshot, reduced to the ones the crew's mind knows: an officer, the doctor, the chief, a
    patient's bed, a place at a table in the Mess (the game also lists extras: "deck1", "sleeper3"...)."""
    out = []
    for x in ids or []:
        x = str(x)
        if x in CREW or x == "mess_cook" or re.fullmatch(r"(patient|mess)\d+", x):
            out.append(x)
    return tuple(out)


def place_from_state(state: dict[str, Any] | None) -> tuple[str, bool]:
    """(place, asleep) from the ship state's `captain` text (what the game already writes)."""
    st = state or {}
    surf = st.get("surface") or {}
    cap = str(st.get("captain") or "on the bridge").lower()
    if surf.get("captain_here") or "planetside" in cap or "over " in cap and "falcon" in cap and surf:
        return ("falcon" if "falcon" in cap else "planetside"), False
    asleep = cap.startswith("asleep")
    for word, place in _PLACE_WORDS:
        if word in cap:
            return place, asleep
    return "bridge", False


def earshot_from_state(place: str, state: dict[str, Any] | None) -> tuple[str, ...]:
    st = state or {}
    if place == "bridge":
        return BRIDGE
    if place == "mess":
        mess = st.get("mess") or {}
        return tuple(d.get("speaker", "") for d in mess.get("diners", [])) + ("mess_cook",)
    if place == "medbay":
        return ("doctor",) + tuple(p.get("speaker", "") for p in (st.get("medbay") or {}).get("patients", []))
    if place == "engineering":
        return ("chief",)
    if place == "quarters" and st.get("visitor"):
        return (str(st["visitor"]).split(" ", 1)[0],)
    return ()


def parse(raw: dict[str, Any] | None, state: dict[str, Any] | None, enemy: Any = None, names: dict[str, str] | None = None,
          exchange: Exchange | None = None, flight_net: bool = False, marine_net: bool = False) -> Context:
    """The context of one utterance. `raw`: the game's `context` (None or {} on a build that does not send it):
        {place: slug, place_name, pawn, in_earshot: [ids], facing: id|null, channel: {party, open, muted}|null};
    `enemy`: the mind's enemy agent (open, contact) — the channel the mind itself keeps; `names`: party id -> display name;
    `flight_net`: the mind's flight net is live (the Captain opened it, flies a Falcon, stands on the flight deck, or was just called on it): it is the channel when
    no other is open; `marine_net`: the marine net is live (boarders are aboard, or the fight has just ended: marines.py): the channel when no other is open, the flight net's
    included (the fight is where the Captain's words are most likely for the marines)."""
    ex = exchange or Exchange()
    if raw:
        ch = raw.get("channel") if isinstance(raw.get("channel"), dict) else None
        channel = None
        if ch and (ch.get("party") or ch.get("open")):
            party = str(ch.get("party") or "")
            channel = Channel(party=party, name=(names or {}).get(party, party), kind=str(ch.get("kind") or _kind(party, state)),
                              open=bool(ch.get("open", True)), muted=bool(ch.get("muted", False)) or _comms_muted(state),
                              heard_s=ex.ago(ex._heard, party), said_s=ex.ago(ex._said, party), last_words=ex.last_words(party),
                              screen=bool(ch.get("screen", False)) or _on_screen(state, party))
        if channel is None and (marine_net or flight_net):
            channel = _marines_channel(names, ex, state) if marine_net else _flight_channel(names, ex, state)
        slug = str(raw.get("place") or "bridge")
        place = PLACE_SLUGS.get(slug, slug)
        listed = known_speakers(raw.get("in_earshot")) if raw.get("in_earshot") is not None else earshot_from_state(place, state)
        return Context(place=place, in_earshot=listed or (BRIDGE if place == "bridge" else ()),
                       facing=(str(raw["facing"]) if raw.get("facing") else None), channel=channel,
                       pawn=str(raw.get("pawn") or "seated"), source="game", asleep=place_from_state(state)[1])
    place, asleep = place_from_state(state)
    channel = None
    if enemy is not None and getattr(enemy, "open", False):
        party = str(getattr(enemy, "contact", "") or "")
        channel = Channel(party=party, name=(names or {}).get(party, party), kind="enemy", open=True, muted=_comms_muted(state),
                          heard_s=ex.ago(ex._heard, party), said_s=ex.ago(ex._said, party), last_words=ex.last_words(party),
                          screen=_on_screen(state, party))
    if channel is None and (marine_net or flight_net):
        channel = _marines_channel(names, ex, state) if marine_net else _flight_channel(names, ex, state)
    return Context(place=place, in_earshot=earshot_from_state(place, state), facing=None, channel=channel,
                   pawn="falcon" if place == "falcon" else "seated", source="inferred", asleep=asleep)


def _flight_channel(names: dict[str, str] | None, ex: Exchange, state: dict[str, Any] | None) -> Channel:
    """The flight net as a channel (the mind keeps it: the game's own `channel` has no flight party)."""
    return Channel(party="flight", name=(names or {}).get("flight", "the flight net"), kind="flight", open=True, muted=_comms_muted(state),
                   heard_s=ex.ago(ex._heard, "flight"), said_s=ex.ago(ex._said, "flight"), last_words=ex.last_words("flight"))


def _marines_channel(names: dict[str, str] | None, ex: Exchange, state: dict[str, Any] | None) -> Channel:
    """The marine net as a channel (the mind keeps it, like the flight net's: the game's own `channel` has no marine party)."""
    return Channel(party="marines", name=(names or {}).get("marines", "the marine net"), kind="marines", open=True, muted=_comms_muted(state),
                   heard_s=ex.ago(ex._heard, "marines"), said_s=ex.ago(ex._said, "marines"), last_words=ex.last_words("marines"))


def _comms_muted(state: dict[str, Any] | None) -> bool:
    """Comms' channel mode is `mute`: the Captain's voice must not go out (the game keeps the mode; the mind is who enforces it —
    the game's own `context.channel.muted` is always false today)."""
    ch = (((state or {}).get("stations") or {}).get("comms") or {}).get("modes", {})
    ch = ch.get("channel") if isinstance(ch, dict) else None
    return isinstance(ch, dict) and str(ch.get("mode", "")).lower() == "mute"


def _on_screen(state: dict[str, Any] | None, party: str) -> bool:
    """The party is on the main screen: the game's one-line `viewscreen` says the mode is comms with them."""
    line = str((state or {}).get("viewscreen") or "").lower()
    return line.startswith(("comms", "auto: comms")) or ("comms" in line and party.lower() in line)


def _kind(party: str, state: dict[str, Any] | None = None) -> str:
    p = party.lower()
    if p in ("fleet", "admiral", "rourke"):
        return "fleet"
    if p in ("flight", "flight_net", "cag"):
        return "flight"
    if p in ("marines", "marine", "marine_net", "marine_ops", "security", "reyes"):
        return "marines"
    if p.startswith("port") or p in ("field", "control"):
        return "port"
    for c in (state or {}).get("contacts", []) or []:
        if str(c.get("id", "")).lower() == p and str(c.get("status", "")) == "friendly":
            return "ally"                                  # an allied ship on the channel: what is said to it is for it, like the fleet
    return "enemy"


def describe(ctx: Context, titles: dict[str, str] | None = None) -> str:
    """The room, in a sentence or two, for the crew's prompt (empty when it is the ordinary case: the bridge, no channel)."""
    t = titles or {}
    parts = []
    if ctx.place != "bridge":
        parts.append(f"The Captain is not on the bridge ({ctx.place.replace('_', ' ')}): the officers hear over the intercom and "
                     "answer when they are called or when it concerns their station.")
    if ctx.facing:
        parts.append(f"The Captain is looking at {t.get(ctx.facing, ctx.facing)}"
                     + (": unless the words are plainly for someone else, they are addressed to them." if ctx.facing in BRIDGE else "."))
    ch = ctx.channel
    if ch and ch.open:
        who = ch.name or ch.party
        if ch.muted:
            parts.append(f"A channel with {who} is open but MUTED: nothing the Captain says reaches them.")
        elif ch.kind == "flight":
            parts.append(f"The flight net is live ({who}; the bridge hears it, and so do you): what the Captain says TO a pilot, a squadron, the CAG or the Chief of the Deck goes "
                         "out on it (Martin lets it through) and they answer for themselves, and carry out the orders for their squadrons. Whatever is for them is theirs: you "
                         "hear every word and say nothing about it — Price too, unless the words are for him or for Flight Control. What is meant for the bridge is yours.")
        elif ch.kind == "marines":
            parts.append(f"The marine net is live ({who}; the bridge hears it, and so do you): what the Captain says TO Major Reyes, the marines, a squad or its sergeant, or about "
                         "the boarders, the bulkheads and the fight inside the hull, goes out on it (Martin lets it through) and they answer for themselves, and carry out the "
                         "orders for their squads and the doors. Whatever is for them is theirs: you hear every word and say nothing about it — Tactical and the XO included, unless "
                         "the words are for them. What is meant for the bridge (the ship, the guns, the helm) is yours.")
        else:
            parts.append(f"A channel with {who} is open: what the Captain says TO them goes out on it (Martin lets it through), "
                         f"and you hear every word as well. Words said to {who} are for {who} to answer, not for you: act and "
                         "speak on what is meant for the bridge (Martin may say in a few words that a message went out, if that helps).")
    return " ".join(parts)
