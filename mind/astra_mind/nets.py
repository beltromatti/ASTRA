"""The radio nets, the people who listen to them, and the consoles' silent log (docs/brief/VOCI-3.md, docs/protocollo_voce.md §5ter).

The fleet net (Fleet command and the allied captains), the flight net (the CAG, the squadron leaders, the Chief of the Deck) and the marine net (Major Reyes and the squad
leaders) are the radio of other people. On a real bridge the Captain does not hear them all day: the officer who has the watch on a net does (Communications the fleet net,
Flight Control the flight net, the XO the marines), tells him in a line what he must know or decide now, and the rest is on the consoles' logs and the datapad, where he reads it
when he wants. On 5 October every one of those people spoke on the one speaker of the bridge: ~480 lines in 70 minutes, a third never said, the allies giving their position at
every kilometre, the same news from three mouths, and the Captain's own orders lost behind them.

What this module does is mechanics (docs/ARCHITETTURA.md §1bis): it carries the traffic where it belongs, and decides nothing about what anybody says or what matters.

  - A line a net's person says is NET TRAFFIC. It is recorded (what the consoles and the datapad show: the `net_traffic` message) and handed to the net's listener, an officer of
    the crew, who judges what the Captain must hear (the crew's turn reads it as an event, with its own doctrine) and writes the rest on the console's log with `console_log`.
    Urgent traffic (the sender says danger now) and traffic addressed to the Captain reach the listener at once; routine traffic is read together, a few seconds later.
  - What reaches the speaker of the bridge by itself is what is the Captain's own: an ANSWER to his words (the admiral answering him, a captain answering his request), a DIRECT
    call to him in the sender's own voice (Fleet's order to the Aquila), and everything on a net the Captain asked to hear (`net_speaker`: «put the flight net on the speaker»,
    until he says to take it off), and the flight net while he sits in a cockpit or stands on the flight deck (it is his own radio there).
  - `console_log` is the officers' silent tool: a line on their console's log and on the datapad, which nobody hears. The routine of a console goes there.

`Nets(enabled=False)` (ASTRA_NETS=0) is the old way: everything goes to the speaker, nothing to the listeners.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .crew import CREW

log = logging.getLogger("astra.nets")

ROUTINE_BATCH_S = 12.0        # routine traffic is read by the listener together, this long after the first of it (or sooner, with anything addressed or urgent)
ADDRESSED_BATCH_S = 1.2       # a sender calling the Captain: the listener has it at once (a moment for what comes with it)
URGENT_BATCH_S = 0.0          # the sender says danger now
TRAFFIC_KEEP = 80             # lines of traffic remembered per net
LOG_KEEP = 40                 # lines remembered per console log
DIGEST_WINDOW_S = 150.0       # what the officers see of the logs and the traffic: the last two and a half minutes ...
DIGEST_LINES = 12             # ... and at most this many lines (the rest is on the consoles)
LOG_MAX_CHARS = 500           # (a sanity bound for the protocol: a console line is a short note; the screen wraps it)

CONSOLES = ("xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight")
NET_EVENT = "net: "           # what the events of a listener's turn begin with (the server's turn worker reads it)
URGENT_MARK = "[URGENT]"      # in that event: the sender said it is danger now (the server's urgent-event test looks for it)


@dataclass(frozen=True)
class Net:
    key: str            # fleet | flight | marines
    name: str           # what the officers call it
    title: str          # what the consoles show
    listener: str       # the officer who has the watch on it (a crew id)
    console: str        # the console whose log shows its traffic


NETS: dict[str, Net] = {n.key: n for n in (
    Net("fleet", "the fleet net", "FLEET NET", "comms", "comms"),
    Net("flight", "the flight net", "FLIGHT NET", "flight", "flight"),
    Net("marines", "the marine net", "MARINE NET", "xo", "xo"))}


@dataclass
class Traffic:
    t: float
    net: str
    key: str                  # the speaker's id on the voice stage
    who: str                  # the name the consoles show
    text: str
    lang: str = ""
    urgent: bool = False      # the sender says danger now
    addressed: bool = False   # it is meant for the Captain (a call to him, or an answer to him)
    aloud: bool = False       # it went to the bridge's speaker


@dataclass
class LogLine:
    t: float
    station: str
    text: str
    kind: str = "routine"     # routine | notice
    by: str = ""


SendFn = Callable[[dict[str, Any]], Awaitable[None]]
ListenFn = Callable[[str, str, bool, str], Awaitable[None]]       # (net key, the event text for the listener, urgent, language)


def _now() -> float:
    try:
        return asyncio.get_running_loop().time()
    except RuntimeError:
        return time.monotonic()


class Nets:
    """Where net traffic goes, and the consoles' logs. `send(msg)` puts a protocol message to the game; `listen(net, text, urgent, lang)` gives the net's listener its traffic to
    read (the server queues it as an event of the crew's turn)."""

    def __init__(self, send: SendFn, listen: ListenFn, *, enabled: bool = True, clock: Callable[[], float] = _now) -> None:
        self.send = send
        self.listen = listen
        self.enabled = enabled
        self.clock = clock
        self.speaker: dict[str, bool] = {}                       # the Captain asked to hear this net
        self.presence: dict[str, Callable[[], bool]] = {}         # a net the Captain is on by being where he is (the flight net in a cockpit or on the flight deck)
        self.traffic: dict[str, deque[Traffic]] = {k: deque(maxlen=TRAFFIC_KEEP) for k in NETS}
        self.logs: dict[str, deque[LogLine]] = {c: deque(maxlen=LOG_KEEP) for c in CONSOLES}
        self._pending: dict[str, list[Traffic]] = {k: [] for k in NETS}
        self._due: dict[str, float] = {}                         # net -> the time its pending traffic goes to the listener
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self.stats = {"traffic": 0, "aloud": 0, "relayed": 0, "batches": 0, "logged": 0}

    # ------------------------------------------------------------------------------------------------ the speaker
    def on_speaker(self, net: str) -> bool:
        """The Captain hears this net's voices himself: he asked for it, or he is on it by where he is."""
        if self.speaker.get(net):
            return True
        p = self.presence.get(net)
        try:
            return bool(p and p())
        except Exception:  # noqa: BLE001
            log.exception("the presence of the Captain on the %s could not be read", net)
            return False

    def set_speaker(self, net: str, on: bool) -> dict[str, Any]:
        """The Captain asked for a net on the speaker (or to take it off): `net_speaker`, an officer's tool in his turn."""
        n = NETS.get(net)
        if n is None:
            return {"ok": False, "detail": f"no such net '{net}' (nets: {', '.join(NETS)})"}
        was = self.speaker.get(net, False)
        self.speaker[net] = bool(on)
        if on:
            self._cancel(net)                                    # (what was waiting for its listener is on the log; from now on he hears them himself)
        self._emit({"type": "net_speaker", "net": net, "on": bool(on)})
        who = CREW[n.listener].title if n.listener in CREW else n.listener
        how = (f"{n.name} is on the bridge's speaker: its voices are heard as they speak, until the Captain says to take it off" if on else
               f"{n.name} is off the speaker: {who} has the watch on it again and tells the Captain what he must know")
        if bool(on) == was:
            how += " (it already was)"
        return {"ok": True, "detail": how}

    # ------------------------------------------------------------------------------------------------ traffic
    async def post(self, net: str, key: str, who: str, text: str, lang: str, *, urgent: bool = False, answer: bool = False, addressed: bool = False,
                   direct: bool = False, quiet: bool = False, aloud: Callable[[], Awaitable[Any]]) -> bool:
        """Somebody on a net said something. `answer`: it answers the Captain's words; `direct`: a call to him that comes in the sender's own voice (Fleet's order to the
        Aquila); `addressed`: the sender is calling him, and his listener tells him; `urgent`: danger now; `quiet`: it is for the others on the net (a captain to another): on
        the log and nothing more, nobody is woken for it. `aloud()` is what puts the line on the bridge's speaker (the server's: the voice stage with its hooks). Returns True
        when it went to the speaker."""
        text = (text or "").strip()
        if not text:
            return False
        n = NETS.get(net)
        heard = (not self.enabled) or n is None or answer or direct or self.on_speaker(net)
        tr = Traffic(self.clock(), net, key, who, text, lang, urgent=urgent, addressed=addressed or answer or direct, aloud=heard)
        self.stats["traffic"] += 1
        if n is not None:
            self.traffic[net].append(tr)
            self._emit({"type": "net_traffic", "net": net, "console": n.console, "speaker": key, "name": who, "text": text, "lang": lang, "urgent": urgent,
                        "addressed": tr.addressed, "aloud": heard, "answer": answer})
        if heard:
            self.stats["aloud"] += 1
            await aloud()
            return True
        if quiet:
            return False
        self._pending[net].append(tr)
        self._schedule(net, URGENT_BATCH_S if urgent else ADDRESSED_BATCH_S if addressed else ROUTINE_BATCH_S)
        return False

    def _schedule(self, net: str, delay: float) -> None:
        """The pending traffic of a net goes to its listener `delay` seconds from now, or sooner if it was already due sooner."""
        loop = asyncio.get_running_loop()
        due = self.clock() + delay
        if net in self._due and self._due[net] <= due:
            return
        self._cancel_timer(net)
        self._due[net] = due
        self._timers[net] = loop.call_later(delay, lambda: asyncio.ensure_future(self._flush(net)))

    def _cancel_timer(self, net: str) -> None:
        old = self._timers.pop(net, None)
        if old is not None:
            old.cancel()
        self._due.pop(net, None)

    def _cancel(self, net: str) -> None:
        self._cancel_timer(net)
        self._pending[net].clear()

    async def _flush(self, net: str) -> None:
        self._timers.pop(net, None)
        self._due.pop(net, None)
        rows, self._pending[net] = self._pending[net], []
        if not rows:
            return
        n = NETS[net]
        now = self.clock()
        urgent = any(r.urgent for r in rows)
        lines = []
        for r in rows:
            call = " and calls the Captain" if r.addressed else ""
            lines.append(f" - {max(0.0, now - r.t):.0f} s ago · {r.who}{call}: «{r.text}»" + (" [the sender says: danger now]" if r.urgent else ""))
        who = CREW[n.listener].title if n.listener in CREW else n.listener
        text = (f"traffic on {n.name}{(' ' + URGENT_MARK) if urgent else ''} — {len(rows)} line{'s' if len(rows) != 1 else ''} the Captain has NOT heard (not on the bridge's "
                f"speaker: he reads them on the {n.console} console's log and the datapad). {who} has the watch on this net:\n" + "\n".join(lines))
        self.stats["batches"] += 1
        self.stats["relayed"] += len(rows)
        lang = next((r.lang for r in reversed(rows) if r.lang), "")
        try:
            await self.listen(net, text, urgent, lang)
        except Exception:  # noqa: BLE001
            log.exception("the %s's traffic could not be given to its listener", net)

    def flush_now(self) -> list[str]:
        """Every net's pending traffic goes to its listener at once. Returns the nets that had some (the bench's end of a scenario)."""
        out = []
        for net in list(self._pending):
            if self._pending[net]:
                out.append(net)
                self._cancel_timer(net)
                asyncio.ensure_future(self._flush(net))
        return out

    # ------------------------------------------------------------------------------------------------ the consoles' logs
    def console_log(self, station: str, text: str, *, kind: str = "routine", by: str = "") -> dict[str, Any]:
        """An officer writes a line on a console's log, silently (the `console_log` tool): it shows on that console and on the Captain's datapad. Nobody hears it."""
        st = (station or "").strip().lower()
        if st not in CONSOLES:
            return {"ok": False, "detail": f"no console '{station}' (consoles: {', '.join(CONSOLES)})"}
        body = " ".join((text or "").split())[:LOG_MAX_CHARS]
        if not body:
            return {"ok": False, "detail": "nothing to write"}
        k = "notice" if str(kind).lower() == "notice" else "routine"
        self.logs[st].append(LogLine(self.clock(), st, body, k, by))
        self.stats["logged"] += 1
        self._emit({"type": "console_log", "station": st, "text": body, "kind": k, "by": by})
        return {"ok": True, "detail": f"written on the {st} console's log (and the datapad)"}

    # ------------------------------------------------------------------------------------------------ what the officers see
    def digest(self, now: float | None = None, window_s: float = DIGEST_WINDOW_S, limit: int = DIGEST_LINES) -> str:
        """The last lines of the nets' traffic the Captain has NOT heard and of the consoles' logs, newest last, for the head of a crew turn: what the bridge knows and has not
        said aloud (a net's silence is not that nothing happened). The nets on the speaker come first."""
        t = self.clock() if now is None else now
        rows: list[tuple[float, str]] = []
        for net, dq in self.traffic.items():
            for r in dq:
                if not r.aloud and t - r.t <= window_s:
                    rows.append((r.t, f"{NETS[net].title.lower()} · {r.who}: «{r.text}»"))
        for st, dq in self.logs.items():
            for r in dq:
                if t - r.t <= window_s:
                    rows.append((r.t, f"{st} log{' (notice)' if r.kind == 'notice' else ''}: {r.text}"))
        rows.sort(key=lambda x: x[0])
        on = [NETS[k].name for k in NETS if self.on_speaker(k)]
        head = f"On the Captain's speaker now: {', '.join(on)}.\n" if on else ""
        if not rows:
            return head.strip()
        shown = rows[-limit:]
        more = f"({len(rows) - len(shown)} older line(s) on the consoles)\n" if len(rows) > len(shown) else ""
        return head + more + "\n".join(f" - {max(0.0, t - ts):.0f} s ago · {txt}" for ts, txt in shown)

    # ------------------------------------------------------------------------------------------------ plumbing
    def _emit(self, msg: dict[str, Any]) -> None:
        try:
            asyncio.get_running_loop().create_task(self.send(msg))
        except RuntimeError:
            pass

    def reset(self) -> None:
        """A new session: no net on the speaker, no traffic, empty logs."""
        for net in list(self._timers):
            self._cancel_timer(net)
        for rows in self._pending.values():
            rows.clear()
        for dq in self.traffic.values():
            dq.clear()
        for dq in self.logs.values():
            dq.clear()
        self.speaker.clear()
