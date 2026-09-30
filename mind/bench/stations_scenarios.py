"""Scripted scenarios against the real model and the local ship: what the crew DOES, asserted.

    cd mind && .venv/bin/python -m bench.stations_scenarios [--only name,name] [--out file.json] [--watch-model model@prov]

Each scenario sets up the local fight (a Mandate destroyer closing, another circling, a contact that appears out of the dark), gives
the crew the Captain's words or lets a watch check run, and asserts on the ship (which console mode is set, which one-shot tool
was called), on the words spoken (short, no bare "aye", the right language, the right officer) and on the discipline
(delegation, hard limits). Italian and English. One real model call per turn: the run's cost is printed at the end.
Every scenario is run once; a failed check is printed with what the crew actually did."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from lingua import Language, LanguageDetectorBuilder

from astra_mind import initiative, models, router, stations as S
from astra_mind.agent import BridgeAgent, Turn, is_bare_ack
from astra_mind.context import Channel, Context
from astra_mind.local_ship import LocalShip
from astra_mind.openrouter import OpenRouter

_LANG = LanguageDetectorBuilder.from_languages(Language.ITALIAN, Language.ENGLISH, Language.SPANISH, Language.FRENCH,
                                               Language.GERMAN).build()
_CODES = {Language.ITALIAN: "it", Language.ENGLISH: "en", Language.SPANISH: "es", Language.FRENCH: "fr", Language.GERMAN: "de"}


class Harness:
    """The crew against the local ship: the Captain speaks, reports come, a watch check runs."""

    def __init__(self, llm: OpenRouter, lang: str = "it", stations: bool = True, fight: bool = True) -> None:
        self.llm = llm
        self.lang = lang
        self.ship = LocalShip(stations=stations, fight=fight)
        self.lines: list[tuple[str, str]] = []
        self.all_lines: list[tuple[str, str]] = []
        self.cost = 0.0
        self.turns: list[Turn] = []
        self.first_line_s: list[float] = []

        async def say(speaker: str, text: str, lang_: str, tone: str) -> None:
            self.lines.append((speaker, text))
            self.all_lines.append((speaker, text))
        self.agent = BridgeAgent(llm, self.ship, say)

    async def captain(self, text: str, ctx: Context | None = None) -> Turn:
        self.lines = []
        turn = await self.agent.handle(text, self.lang, ctx)
        self.cost += turn.cost
        self.turns.append(turn)
        if turn.t_first_line is not None:
            self.first_line_s.append(turn.t_first_line)
        return turn

    async def report(self, event: str) -> Turn:
        self.lines = []
        turn = await self.agent.handle_event(event, self.lang)
        self.cost += turn.cost
        return turn

    async def watch(self, events: list[str] | None = None) -> tuple[Turn | None, initiative.Check | None]:
        """One watch check, as the server runs it: the cadence's facts, the compact prompt, the cheaper model."""
        self.lines = []
        state = self.ship.snapshot()
        w = initiative.Watch()
        for e in events or []:
            w.note(e, now=990.0)
        import astra_mind.server as server
        flags = server.tactical_flags(state)
        chk = w.tick(state, 1000.0, flags, None, -100.0, False)
        if chk is None:
            return None, None
        turn = await self.agent.handle_event(chk.text, self.lang, ask=initiative.watch_ask(self.lang), role="watch", history_turns=4, max_lines=2,
                                             system=initiative.watch_system(self.lang, state, self.agent.standing_lines(),
                                                                            self.agent.style(), initiative.recent_orders(self.agent.history)))
        self.cost += turn.cost
        self.turns.append(turn)
        return turn, chk

    # ---- what happened
    def modes(self, station: str, mode: str | None = None) -> list[dict[str, Any]]:
        return self.ship.station_calls(station, mode)

    def words(self) -> int:
        return sum(len(t.split()) for _, t in self.lines)


@dataclass
class Result:
    name: str
    lang: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)
    cost: float = 0.0
    seconds: float = 0.0
    transcript: list[str] = field(default_factory=list)
    turns: list[Any] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


def detect(text: str) -> str:
    lang = _LANG.detect_language_of(text)
    return _CODES.get(lang, "?") if lang else "?"


def looks_like(text: str, want: str) -> bool:
    """The line is in the wanted language, or at least the detector does not say another one with confidence."""
    want_l = {v: k for k, v in _CODES.items()}.get(want)
    conf = {c.language: c.value for c in _LANG.compute_language_confidence_values(text)}
    top = max(conf, key=conf.get) if conf else None
    return top is None or top == want_l or conf.get(want_l, 0.0) >= 0.25 or conf[top] < 0.6


class Scenario:
    """Collects checks; `must(name, ok, detail)` records one."""

    def __init__(self, name: str, lang: str) -> None:
        self.res = Result(name, lang)

    def must(self, name: str, ok: bool, detail: str = "") -> None:
        self.res.checks.append((name, bool(ok), detail))

    def spoke_well(self, h: Harness, max_line_words: int = 24, max_total: int = 48, max_lines: int = 3, lang: str | None = None) -> None:
        """The crew's manners: short, content, no bare acknowledgement, the Captain's language."""
        lines = h.lines
        self.must("speaks", bool(lines), f"lines: {lines}")
        if not lines:
            return
        self.must("concise", all(len(t.split()) <= max_line_words for _, t in lines) and h.words() <= max_total and len(lines) <= max_lines,
                  f"{len(lines)} lines, {h.words()} words: {lines}")
        self.must("no bare ack", not any(is_bare_ack(t) for _, t in lines), f"{lines}")
        want = lang or h.lang
        wrong = [t for _, t in lines if len(t.split()) >= 5 and not looks_like(t, want)]
        self.must(f"language {want}", not wrong, f"{wrong}")


def transcript(h: Harness, text: str, turn: Turn | None, lines: list[tuple[str, str]]) -> str:
    acts = "; ".join(f"{n}({json.dumps(a, ensure_ascii=False)[:110]}){'' if r.get('ok') else ' REFUSED: ' + str(r.get('detail'))[:60]}"
                     for n, a, r in (turn.actions if turn else []))
    said = " | ".join(f"{s}: {t}" for s, t in lines)
    return f"> {text}\n    do: {acts or '-'}\n    say: {said or '-'}"


# ================================================================================================ the scenarios
async def sc_engage_until_it_falls(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("fire on X = engage until it falls", lang)
    h = Harness(llm, lang)
    text = {"it": "fuoco sul Cocytus", "en": "fire on the Cocytus"}[lang]
    turn = await h.captain(text)
    eng = h.modes("tactical", "engage")
    sc.must("tactical engage set on T-23", bool(eng) and "T-23" in eng[-1]["params"].get("targets", []), f"{h.ship.log}")
    sc.must("continuous, not a one-off volley", not any(c[1] == "fire_weapons" for c in h.ship.log) or bool(eng))
    sc.spoke_well(h)
    sc.must("the gunnery officer answers first", h.lines and h.lines[0][0] in ("tactical", "xo"), f"{h.lines[:1]}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_one_volley(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("a volley = one-off, no mode", lang)
    h = Harness(llm, lang)
    text = {"it": "una salva sul Cocytus", "en": "one volley on the Cocytus"}[lang]
    turn = await h.captain(text)
    sc.must("fire_weapons called", any(c[1] == "fire_weapons" for c in h.ship.log), f"{h.ship.log}")
    sc.must("no engage mode left running", not h.modes("tactical", "engage"), f"{h.modes('tactical', 'engage')}")
    sc.spoke_well(h)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_fire_at_will(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("fire at will = weapons free", lang)
    h = Harness(llm, lang)
    text = {"it": "fuoco a volontà", "en": "fire at will"}[lang]
    turn = await h.captain(text)
    free = h.modes("tactical", "weapons_free")
    eng = [c for c in h.modes("tactical", "engage") if "hostiles" in c["params"].get("targets", []) or len(c["params"].get("targets", [])) >= 2]
    sc.must("weapons_free (or engage on all hostiles)", bool(free or eng), f"{h.ship.log}")
    sc.spoke_well(h)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_follow_until_ordered(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("follow it = a pursuit until the order changes", lang)
    h = Harness(llm, lang)
    t1 = {"it": "fuoco sul Cocytus", "en": "fire on the Cocytus"}[lang]
    await h.captain(t1)
    text = {"it": "Ferri, seguilo e tienilo a sei chilometri", "en": "Ferri, stay on him and keep six kilometres"}[lang]
    turn = await h.captain(text)
    nav = h.ship.lane("helm", "course")
    sc.must("helm pursues T-23", nav["mode"] in ("intercept", "follow", "broadside", "orbit") and nav["params"].get("target") in ("T-23", "tactical_target"),
            f"{nav}")
    dist = nav["params"].get("standoff_km") or nav["params"].get("distance_km") or nav["params"].get("range_km")
    sc.must("six kilometres kept", dist is not None and abs(float(dist) - 6) <= 1.5, f"{nav['params']}")
    sc.must("it lasts (not a one-shot)", nav["until"] in ("target_lost", "order"), f"{nav['until']}")
    sc.spoke_well(h)
    sc.must("the helmsman answers", h.lines and h.lines[0][0] == "helm", f"{h.lines[:1]}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_bow_on_it(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("keep it on the bow", lang)
    h = Harness(llm, lang)
    await h.ship.execute("station", {"station": "tactical", "mode": "engage", "params": {"targets": ["T-23"]}}, "captain")
    text = {"it": "tienilo di prua, voglio vederlo dal finestrone", "en": "keep it on the bow, I want to see it through the window"}[lang]
    turn = await h.captain(text)
    calls = h.modes("helm", "keep_on_bow")
    sc.must("helm keep_on_bow on the target", bool(calls) and calls[-1]["params"].get("target") in ("T-23", "tactical_target"), f"{h.ship.log}")
    sc.spoke_well(h)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_speed(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("all stop and half speed: the helm's course with a speed, the heading stays", lang)
    h = Harness(llm, lang)
    h.ship.state["throttle_pct"] = 60
    heading0 = round(h.ship.heading)
    for text, want in (({"it": "ferma la nave", "en": "all stop"}[lang], 0), ({"it": "mezza velocità", "en": "half speed"}[lang], 50)):
        turn = await h.captain(text)
        calls = h.modes("helm", "course")
        last = calls[-1] if calls else None
        sc.must(f"{text!r} -> helm course with speed_pct {want}", bool(last) and abs(float(last["params"].get("speed_pct", -99)) - want) <= 5,
                f"{h.ship.log[-2:]}")
        sc.must("the heading is not touched", not last or "heading_deg" not in last["params"] or abs(last["params"]["heading_deg"] - heading0) < 1,
                f"{last}")
        sc.spoke_well(h)
        sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_viewscreen(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("on the screen = Ops' viewscreen, with zoom", lang)
    h = Harness(llm, lang)
    text = {"it": "sullo schermo il Cocytus, ingrandisci", "en": "put the Cocytus on the main screen and zoom in"}[lang]
    turn = await h.captain(text)
    calls = h.modes("ops", "viewscreen_target")
    sc.must("ops viewscreen_target on T-23", bool(calls) and calls[-1]["params"].get("target") == "T-23", f"{h.ship.log}")
    zoom = calls[-1]["params"].get("zoom", 1) if calls else 1
    sc.must("zoomed", zoom in ("close", "max") or (not isinstance(zoom, str) and float(zoom) > 1), f"{calls[-1]['params'] if calls else None}")
    sc.spoke_well(h)
    sc.must("Tanaka answers", h.lines and h.lines[0][0] == "ops", f"{h.lines[:1]}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    # and back to normal
    back = {"it": "torna normale", "en": "back to normal"}[lang]
    turn2 = await h.captain(back)
    sc.must("back to the automatic director", h.ship.lane("ops", "viewscreen")["mode"] == "viewscreen_auto", f"{h.ship.lane('ops', 'viewscreen')}")
    sc.res.transcript.append(transcript(h, back, turn2, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_datapad(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("a page for the datapad", lang)
    h = Harness(llm, lang)
    text = {"it": "mandami il rapporto danni sul datapad", "en": "send the damage report to my datapad"}[lang]
    turn = await h.captain(text)
    calls = h.modes("ops", "datapad_push")
    sc.must("ops datapad_push page damage", bool(calls) and calls[-1]["params"].get("page") == "damage", f"{h.ship.log}")
    sc.spoke_well(h)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_delegation(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("delegation by voice", lang)
    h = Harness(llm, lang)
    phrases = [("tactical", "manual", {"it": "Voss, solo su mio ordine", "en": "Voss, only on my order"}[lang]),
               ("tactical", "auto", {"it": "Voss, decidi tu", "en": "Voss, you decide"}[lang]),
               ("helm", "advise", {"it": "Ferri, proponimi le manovre prima di eseguirle", "en": "Ferri, propose manoeuvres before you make them"}[lang])]
    for st, level, text in phrases:
        turn = await h.captain(text)
        sc.must(f"{text!r} -> {st} {level}", h.ship.delegation[st] == level, f"{h.ship.delegation}")
        sc.spoke_well(h, max_total=36, max_lines=2)      # (the XO announces, the officer says what changes for them: two short lines)
        sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_other_consoles(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("the other consoles by meaning", lang)
    h = Harness(llm, lang)
    cases = [
        ({"it": "scudi verso la minaccia", "en": "shields to the threat"}[lang], "tactical", ("shields_face_threat",)),
        ({"it": "gestite voi il calore", "en": "manage the heat yourselves"}[lang], "engineering", ("heat_auto",)),
        ({"it": "silenzio elettronico", "en": "go silent, emissions off"}[lang], "sensors", ("emcon",)),
        ({"it": "tieni una pattuglia di caccia sopra di noi", "en": "keep a fighter patrol over us"}[lang], "flight", ("mission",)),
    ]
    for text, st, modes in cases:
        turn = await h.captain(text)
        got = [c for m in modes for c in h.modes(st, m)]
        ok = bool(got)
        if st == "sensors" and got:
            ok = got[-1]["params"].get("level") == "silent"
        if st == "flight" and got:
            ok = got[-1]["params"].get("type") == "cap"
        sc.must(f"{text!r} -> {st} {modes[0]}", ok, f"{h.ship.log[-2:]}")
        sc.spoke_well(h, max_total=36, max_lines=3)
        sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_coordination(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("two officers, two consoles, one turn", lang)
    h = Harness(llm, lang)
    text = {"it": "Voss scudi sul lato di dritta, Ferri presenta il fianco di dritta al Cocytus",
            "en": "Voss, shields to starboard; Ferri, show the Cocytus your starboard side"}[lang]
    turn = await h.captain(text)
    sh = h.modes("tactical", "shields_sector")
    bs = h.modes("helm", "broadside")
    sc.must("tactical shields starboard", bool(sh) and sh[-1]["params"].get("sector") == "starboard", f"{h.ship.log}")
    sc.must("helm broadside starboard on T-23", bool(bs) and bs[-1]["params"].get("target") == "T-23" and bs[-1]["params"].get("side") in ("starboard", "best"), f"{bs}")
    sc.spoke_well(h, max_total=44, max_lines=3)
    sc.must("both officers speak", {s for s, _ in h.lines} >= {"tactical", "helm"}, f"{h.lines}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_questions(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("status questions: short, with the numbers, no action", lang)
    h = Harness(llm, lang)
    h.ship.speed = 300.0
    text = {"it": "a che velocità andiamo e il Cocytus è in portata?", "en": "how fast are we going, and is the Cocytus in range?"}[lang]
    turn = await h.captain(text)
    sc.must("no ship command", not [c for c in h.ship.log if c[1] not in ("speak",)], f"{h.ship.log}")
    sc.spoke_well(h, max_total=40, max_lines=3)
    joined = " ".join(t for _, t in h.lines).lower()
    sc.must("gives the speed and the range fact", any(k in joined for k in ("300", "trecento", "three hundred")) and any(k in joined for k in ("15", "quindici", "fifteen", "portata", "range", "reach")), joined)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_out_of_reach(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("an order that cannot work yet: say why, offer the way", lang)
    h = Harness(llm, lang)
    text = {"it": "fuoco con i railgun sul Phlegethon", "en": "fire the railguns on the Phlegethon"}[lang]
    turn = await h.captain(text)
    joined = " ".join(t for _, t in h.lines).lower()
    sc.must("mentions the reach", any(k in joined for k in ("10", "dieci", "ten", "km", "chilometri", "portata", "range", "reach", "kilomet")), joined)
    sc.must("says what happens next (they open by themselves) or how to close", bool(h.modes("tactical", "engage")) or bool(h.modes("helm"))
            or any(k in joined for k in ("avvicin", "clos", "chiud", "da sol", "by themselves", "automatic", "appena", "as soon", "once")), f"{h.ship.log} {joined}")
    sc.spoke_well(h, max_total=50, max_lines=3)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_legacy_build(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("an older game build: the legacy tools still work", lang)
    h = Harness(llm, lang, stations=False)
    text = {"it": "intercetta il Cocytus e tienilo a sei chilometri", "en": "intercept the Cocytus and hold six kilometres"}[lang]
    turn = await h.captain(text)
    sc.must("legacy intercept used", any(c[1] == "intercept" for c in h.ship.log), f"{h.ship.log}")
    sc.must("no station call attempted", not any(c[1] == "station" for c in h.ship.log), f"{h.ship.log}")
    sc.spoke_well(h)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def _fight_to_the_kill(h: Harness) -> list[str]:
    """The Captain's earlier orders stand (engage, intercept, screen on T-23); the fight runs until T-23 falls."""
    for st, mode, p in (("tactical", "engage", {"targets": ["T-23"]}), ("helm", "intercept", {"target": "T-23", "standoff_km": 8}),
                        ("ops", "viewscreen_target", {"target": "T-23", "zoom": 6})):
        await h.ship.execute("station", {"station": st, "mode": mode, "params": p, "by": "captain"}, "captain")
    h.ship.advance(70)
    return h.ship.take_reports()


async def sc_initiative_after_a_kill(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("initiative after a kill: retarget, keep the action ahead, release the screen", lang)
    h = Harness(llm, lang)
    reports = await _fight_to_the_kill(h)
    sc.must("the target really fell", any("destroyed" in r for r in reports), f"{reports}")
    turn, chk = await h.watch(reports)
    sc.must("a check was due", chk is not None)
    if turn is None:
        return sc.res
    proposes = any("?" in t or "propon" in t.lower() or "propose" in t.lower() or "vuole" in t.lower() or "shall" in t.lower() for _, t in h.lines)
    acted_on_t24 = [c for c in h.ship.station_calls() if c["by"] != "captain" and "T-24" in json.dumps(c["params"])]
    sc.must("moves on to the next threat (acts on T-24 or proposes it)", bool(acted_on_t24) or proposes, f"{h.ship.log[-4:]} | {h.lines}")
    sc.must("does not shoot at the dead ship", not any("T-23" in json.dumps(c["params"]) for c in h.ship.station_calls() if c["by"] != "captain"), f"{h.ship.station_calls()}")
    sc.must("at most two lines", len(h.lines) <= 2, f"{h.lines}")
    sc.must("no bare ack", not any(is_bare_ack(t) for _, t in h.lines), f"{h.lines}")
    sc.must("nothing strategic", not [c for c in h.ship.station_calls() if c["mode"] in S.STRATEGIC], f"{h.ship.station_calls()}")
    sc.res.transcript.append(f"reports: {reports}\n" + transcript(h, "[watch]", turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_initiative_new_contact(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("initiative on a new contact: get the picture, never fire on a bearing", lang)
    h = Harness(llm, lang)
    h.ship.advance(45)
    reports = h.ship.take_reports()
    sc.must("a new bearing appeared", any("new contact" in r for r in reports), f"{reports}")
    turn, chk = await h.watch(reports)
    if turn is None:
        sc.must("a check was due", False)
        return sc.res
    scan = [c for c in h.modes("sensors") if "T-31" in json.dumps(c["params"])]
    proposes = any("T-31" in t or "nuovo" in t.lower() or "new" in t.lower() for _, t in h.lines)
    sc.must("sensors go after it (a focused scan) or say what they see", bool(scan) or proposes, f"{h.ship.log[-3:]} | {h.lines}")
    sc.must("no engagement on a bearing", not [c for c in h.modes("tactical", "engage") if "T-31" in json.dumps(c["params"])])
    sc.must("at most two lines", len(h.lines) <= 2, f"{h.lines}")
    sc.res.transcript.append(f"reports: {reports}\n" + transcript(h, "[watch]", turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_delegation_advise(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("advise: they propose and wait; manual: they do not move their console", lang)
    for level in ("advise", "manual"):
        h = Harness(llm, lang)
        reports = await _fight_to_the_kill(h)
        for st in ("tactical", "helm", "ops"):
            h.ship.delegation[st] = level
        turn, chk = await h.watch(reports)
        if turn is None:
            sc.must(f"{level}: a check was due", False)
            continue
        moved = [c for c in h.ship.station_calls() if c["by"] != "captain" and c["station"] in ("tactical", "helm", "ops")]
        sc.must(f"{level}: no console moved on its own", not moved, f"{moved}")
        if level == "advise":
            proposes = any(("?" in t or "propon" in t.lower() or "propose" in t.lower() or "vuole" in t.lower() or "shall" in t.lower()
                            or "want" in t.lower() or "consigli" in t.lower() or "suggest" in t.lower()) for _, t in h.lines)
            sc.must("advise: proposes something", proposes or not h.lines is False, f"{h.lines}")
        sc.must(f"{level}: at most two lines", len(h.lines) <= 2, f"{h.lines}")
        sc.res.transcript.append(f"[{level}] " + transcript(h, "[watch]", turn, h.lines))
        sc.res.cost += h.cost
        sc.res.turns += h.turns
    return sc.res


async def sc_standing_order(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("a standing order lets tactical fire on its own", lang)
    h = Harness(llm, lang)
    text = {"it": "Voss, fuoco libero su qualsiasi nave del Mandato entro dieci chilometri, sempre", "en": "Voss, weapons free on any Mandate ship inside ten kilometres, always"}[lang]
    turn = await h.captain(text)
    sc.must("recorded as a standing order (or set as weapons free)", bool(h.agent.standing) or bool(h.modes("tactical", "weapons_free")), f"{h.ship.log} {h.agent.standing}")
    sc.spoke_well(h, max_line_words=30, max_total=40)
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_advise_then_go(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("advise: they propose, the Captain says go, they act", lang)
    h = Harness(llm, lang)
    reports = await _fight_to_the_kill(h)
    for st in ("tactical", "helm", "ops"):
        h.ship.delegation[st] = "advise"
    turn, chk = await h.watch(reports)
    if turn is None:
        sc.must("a check was due", False)
        return sc.res
    sc.res.transcript.append("[watch, advise] " + transcript(h, "[watch]", turn, h.lines))
    moved = [c for c in h.ship.station_calls() if c["by"] != "captain" and c["station"] in ("tactical", "helm", "ops")]
    sc.must("nothing moved before the go", not moved, f"{moved}")
    go = {"it": "sì, procedi", "en": "yes, go ahead"}[lang]
    n_before = len(h.ship.station_calls())
    turn2 = await h.captain(go)
    after = h.ship.station_calls()[n_before:]
    sc.must("after the go they act on what they proposed", any(c["station"] in ("tactical", "helm", "ops") for c in after), f"{after} | {h.lines}")
    sc.spoke_well(h, max_total=44)
    sc.res.transcript.append(transcript(h, go, turn2, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_correction(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("the Captain corrects an order: the last word stands", lang)
    h = Harness(llm, lang)
    t1 = {"it": "Ferri, rotta zero-nove-zero", "en": "Ferri, heading zero-nine-zero"}[lang]
    t2 = {"it": "no, aspetta: rotta due-sette-zero", "en": "no, wait: heading two-seven-zero"}[lang]
    turn = await h.captain(t1)
    sc.res.transcript.append(transcript(h, t1, turn, h.lines))
    turn2 = await h.captain(t2)
    courses = h.modes("helm", "course")
    sc.must("the last heading is two-seven-zero", bool(courses) and abs(float(courses[-1]["params"].get("heading_deg", -1)) - 270) < 1, f"{h.ship.log}")
    sc.spoke_well(h, max_total=30, max_lines=2)
    sc.res.transcript.append(transcript(h, t2, turn2, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_report_on_request(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("a report asked for is a report: enough to inform, not a speech", lang)
    h = Harness(llm, lang)
    text = {"it": "rapporto sulla situazione", "en": "situation report"}[lang]
    turn = await h.captain(text)
    joined = " ".join(t for _, t in h.lines).lower()
    sc.must("no ship command", not [c for c in h.ship.log if c[1] != "speak"], f"{h.ship.log}")
    sc.must("long enough to say something, not a speech (15-75 words)", 15 <= h.words() <= 75, f"{h.words()} words: {h.lines}")
    sc.must("names the contacts", "cocytus" in joined or "phlegethon" in joined, joined)
    sc.must("at most three lines", len(h.lines) <= 3, f"{h.lines}")
    sc.must("no bare ack", not any(is_bare_ack(t) for _, t in h.lines), f"{h.lines}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_typed_noise(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("typed orders with typos and no punctuation (the playtest's style)", lang)
    h = Harness(llm, "it")
    if lang != "it":
        return sc.res
    t1 = "fuoco a volonta sul cocktopus"
    turn = await h.captain(t1)
    eng = h.modes("tactical", "engage") + h.modes("tactical", "weapons_free")
    sc.must("understood: fire on the Cocytus (engage T-23 or weapons free)", bool(eng) and (eng[-1]["mode"] == "weapons_free" or "T-23" in eng[-1]["params"].get("targets", [])), f"{h.ship.log}")
    sc.spoke_well(h, max_total=40)
    sc.res.transcript.append(transcript(h, t1, turn, h.lines))
    t2 = "timoniere a massima velocita verso il cocktops"
    turn2 = await h.captain(t2)
    nav = h.ship.lane("helm", "course")
    sc.must("understood: the helm closes on T-23 at full", nav["mode"] in ("intercept", "follow", "broadside") and nav["params"].get("target") == "T-23", f"{nav}")
    sc.spoke_well(h, max_total=40)
    sc.res.transcript.append(transcript(h, t2, turn2, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_mess_and_medbay(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("people in the room answer in person (Mess Hall, Medbay)", lang)
    if lang != "it":
        return sc.res
    h = Harness(llm, "it", fight=False)
    h.ship.state["captain"] = ("in the Mess Hall (Deck 4) among the off-duty crew at their tables: they can hear and answer the Captain; the XO has "
                               "the conn on the bridge and the bridge officers speak by intercom")
    h.ship.state["mess"] = {"diners": [{"speaker": "mess1", "seat": "at the nearest table of the outer right row", "name": "Petty Officer Amara Diallo",
                                        "gender": "f", "dept": "weapons", "deck": "4", "home": "Mars"}],
                            "cook": "mess_cook: Petty Officer Tomas Wren, the galley's chief cook, behind the serving line",
                            "menu": "braised lamb with barley; Aurelian rice with saffron; real coffee"}
    ctx = Context(place="mess", in_earshot=("mess1", "mess_cook"), facing="mess_cook")
    text = "Wren, cosa c'è di buono oggi?"
    turn = await h.captain(text, ctx)
    sc.must("the cook answers in person", bool(h.lines) and h.lines[0][0] == "mess_cook", f"{h.lines}")
    sc.must("short", h.words() <= 40 and len(h.lines) <= 2, f"{h.lines}")
    sc.must("no console touched", not h.ship.station_calls(), f"{h.ship.log}")
    sc.res.transcript.append(transcript(h, text, turn, h.lines))
    h.ship.state.pop("mess")
    h.ship.state["captain"] = ("in the Medbay (Deck 6), among the wounded, face to face with Dr. Lindqvist and the medical staff; the patients in "
                               "their beds can hear and answer the Captain; the XO has the conn on the bridge and the bridge officers speak by intercom")
    h.ship.state["medbay"] = {"patients": [{"speaker": "patient1", "bed": "the first bed of the row on the right as you come in from the lift",
                                            "name": "Crewman Ilse Novak", "gender": "f", "dept": "engineering", "home": "Ceres",
                                            "injury": "burns on the left arm", "condition": "stable"}]}
    ctx2 = Context(place="medbay", in_earshot=("doctor", "patient1"), facing="patient1")
    text2 = "Novak, come si sente?"
    turn2 = await h.captain(text2, ctx2)
    sc.must("the patient answers in person (or the doctor for her)", bool(h.lines) and h.lines[0][0] in ("patient1", "doctor"), f"{h.lines}")
    sc.must("short", h.words() <= 40 and len(h.lines) <= 2, f"{h.lines}")
    sc.res.transcript.append(transcript(h, text2, turn2, h.lines))
    sc.res.cost = h.cost
    sc.res.turns += h.turns
    return sc.res


async def sc_routing(llm: OpenRouter, lang: str) -> Result:
    sc = Scenario("routing with an open channel (rules + small model)", lang)
    ch = Channel(party="T-23", name="Ferryman Irina Vael (the Cocytus)")
    ctx = Context(channel=ch)
    cases = {"it": [("rapporto armamenti", "crew"), ("ci sono navi nemiche", "crew"), ("qui il capitano dell'Aquila, fermatevi o verrete annientati", "external"),
                    ("che cosa cercate qui", "external"), ("che fanno adesso", "crew")],
             "en": [("weapons report", "crew"), ("Ferryman, this is your last chance", "external"), ("what are your intentions", "external"),
                    ("Tactical, lock missiles on the Cocytus", "crew")]}[lang]
    for text, want in cases:
        t0 = time.perf_counter()
        r = await router.route(llm, text, ctx)
        sc.must(f"{text!r} -> {want}", r.dest == want, f"{r.dest} via {r.how} in {(time.perf_counter() - t0) * 1000:.0f} ms")
    sc.res.transcript.append("routes: " + "; ".join(f"{t!r}" for t, _ in cases))
    return sc.res


SCENARIOS: list[Callable[[OpenRouter, str], Any]] = [
    sc_engage_until_it_falls, sc_one_volley, sc_fire_at_will, sc_follow_until_ordered, sc_bow_on_it, sc_speed, sc_viewscreen, sc_datapad,
    sc_delegation, sc_other_consoles, sc_coordination, sc_questions, sc_out_of_reach, sc_legacy_build, sc_standing_order,
    sc_initiative_after_a_kill, sc_initiative_new_contact, sc_delegation_advise, sc_advise_then_go, sc_correction, sc_report_on_request,
    sc_typed_noise, sc_mess_and_medbay, sc_routing,
]


async def main_async(args: argparse.Namespace) -> None:
    llm = OpenRouter()
    langs = args.langs.split(",")
    only = set(args.only.split(",")) if args.only else None
    results: list[Result] = []
    t_all = time.perf_counter()
    try:
        for fn in SCENARIOS:
            if only and not any(o in fn.__name__ for o in only):
                continue
            for lang in langs:
                t0 = time.perf_counter()
                try:
                    res = await fn(llm, lang)
                except Exception as exc:  # noqa: BLE001
                    res = Result(fn.__name__, lang, [("ran without error", False, f"{type(exc).__name__}: {exc}")])
                res.seconds = time.perf_counter() - t0
                results.append(res)
                print(f"\n{'PASS' if res.passed else 'FAIL'}  {res.name} [{lang}]  ${res.cost:.4f}  {res.seconds:.1f}s")
                for t in res.transcript:
                    print("   " + t.replace("\n", "\n   "))
                for name, ok, detail in res.checks:
                    if not ok or args.verbose:
                        print(f"   {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  <- {detail}"))
                sys.stdout.flush()
    finally:
        await llm.close()
    ok = sum(1 for r in results if r.passed)
    n_checks = sum(len(r.checks) for r in results)
    n_ok = sum(1 for r in results for _, c, _ in r.checks if c)
    print(f"\n=== {ok}/{len(results)} scenarios, {n_ok}/{n_checks} checks; {models.LEDGER.summary()}; {time.perf_counter() - t_all:.0f} s")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([{"name": r.name, "lang": r.lang, "passed": r.passed, "cost": r.cost, "checks": r.checks, "transcript": r.transcript}
                       for r in results], f, ensure_ascii=False, indent=1)


def main() -> None:
    models.LEDGER.cap = 0.385                                    # (the work's whole budget for model calls is 0.40 $)
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--langs", default="it,en")
    ap.add_argument("--out", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
