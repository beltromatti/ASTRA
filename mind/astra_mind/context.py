"""Where the Captain is speaking, who can hear, whom they face, and whether a channel is open: the context of every
utterance (docs/ARCHITETTURA.md §3, `player_text.context`).

The game sends it with every word of the Captain's (`place`, `in_earshot`, `facing`, `channel{party, open, muted}`,
`pawn`). A build that does not send it yet gets the same picture inferred from what the mind already knows: the ship state
(`captain`, `medbay`, `mess`, `visitor`, `surface`) and the mind's own channel with the enemy commander. Nothing here decides
anything: it describes the room, and the router and the crew's prompt use it."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

BRIDGE = ("xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight")
PLACES = ("bridge", "quarters", "mess", "medbay", "engineering", "berthing", "flight_deck", "falcon", "planetside", "corridor")

_PLACE_WORDS = (                                 # (text found in the ship state's `captain`, place)
    ("main engineering", "engineering"), ("mess hall", "mess"), ("crew berthing", "berthing"), ("medbay", "medbay"),
    ("flying a falcon", "falcon"), ("captain's quarters", "quarters"), ("flight deck", "flight_deck"), ("on the bridge", "bridge"))


@dataclass
class Channel:
    """A radio or video channel the Captain has open with someone outside the room."""
    party: str = ""                     # contact id ("T-23"), "fleet", a port controller...
    name: str = ""                      # what the Captain would call them: "Ferryman Irina Vael (the Cocytus)"
    kind: str = "enemy"                 # enemy | fleet | ally | port
    open: bool = True
    muted: bool = False                 # the Captain's voice does not go out
    heard_s: float | None = None        # seconds since the party last spoke to the Captain (None: not in this exchange)
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
    """The mind's memory of the talk with each party on the channel: who spoke last, and when."""

    def __init__(self) -> None:
        self._heard: dict[str, float] = {}
        self._said: dict[str, float] = {}

    def heard(self, party: str) -> None:
        self._heard[party] = time.monotonic()

    def said(self, party: str) -> None:
        self._said[party] = time.monotonic()

    def ago(self, table: dict[str, float], party: str) -> float | None:
        t = table.get(party)
        return None if t is None else max(0.0, time.monotonic() - t)

    def reset(self) -> None:
        self._heard.clear()
        self._said.clear()


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
          exchange: Exchange | None = None) -> Context:
    """The context of one utterance. `raw`: the game's `context` (None or {} on a build that does not send it);
    `enemy`: the mind's enemy agent (open, contact) — the channel the mind itself keeps; `names`: party id -> display name."""
    ex = exchange or Exchange()
    if raw:
        ch = raw.get("channel") if isinstance(raw.get("channel"), dict) else None
        channel = None
        if ch and (ch.get("party") or ch.get("open")):
            party = str(ch.get("party") or "")
            channel = Channel(party=party, name=(names or {}).get(party, party), kind=str(ch.get("kind") or _kind(party)),
                              open=bool(ch.get("open", True)), muted=bool(ch.get("muted", False)),
                              heard_s=ex.ago(ex._heard, party), said_s=ex.ago(ex._said, party), screen=bool(ch.get("screen", False)))
        place = str(raw.get("place") or "bridge")
        return Context(place=place, in_earshot=tuple(str(x) for x in (raw.get("in_earshot") or earshot_from_state(place, state))),
                       facing=(str(raw["facing"]) if raw.get("facing") else None), channel=channel,
                       pawn=str(raw.get("pawn") or "seated"), source="game", asleep=place_from_state(state)[1])
    place, asleep = place_from_state(state)
    channel = None
    if enemy is not None and getattr(enemy, "open", False):
        party = str(getattr(enemy, "contact", "") or "")
        channel = Channel(party=party, name=(names or {}).get(party, party), kind="enemy", open=True, muted=False,
                          heard_s=ex.ago(ex._heard, party), said_s=ex.ago(ex._said, party))
    return Context(place=place, in_earshot=earshot_from_state(place, state), facing=None, channel=channel,
                   pawn="falcon" if place == "falcon" else "seated", source="inferred", asleep=asleep)


def _kind(party: str) -> str:
    p = party.lower()
    if p in ("fleet", "admiral", "rourke"):
        return "fleet"
    if p.startswith("port") or p in ("field", "control"):
        return "port"
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
        else:
            parts.append(f"A channel with {who} is open: only what the Captain clearly says TO them goes out on it (the router "
                         "has sorted this out); everything on this line is for the bridge.")
    return " ".join(parts)
