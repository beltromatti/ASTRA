"""After the Aquila is lost: what becomes of her Captain, and how the war goes on.

The ship's reactor has breached; the Captain is adrift in a lifepod (or out in a Falcon). The story decides, from what
really happened, who finds the pod: a ship of the 7th Fleet (a rescue), the Kharon Mandate (capture, then the
questions of a Mandate officer, then a prisoner exchange), or nobody for a long while (days adrift, then one or the
other). Then the Board of Inquiry of the 7th Fleet — Vice Admiral Rourke presiding, a line captain and a Judge
Advocate beside him — hears the Captain in person: it has the record (the campaign, the Captain's own log, the losses,
what the officers said) and asks one question at a time; the Captain answers in their own words. The board rules
(commended, cleared, reprimanded) and the Admiralty gives the Captain a new command: the Aquila's sister, renamed
Aquila, weeks later. The fallen stay fallen; the survivors come back to serve.

The game plays it: the pod, the voices on the radio, cards on a black screen (story_card), the dark of a scene played
in voices (story_black), and the new ship (new_command, which starts the level over from the rewritten save)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Awaitable, Callable

from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall

log = logging.getLogger("astra.loss")

MODEL = "deepseek/deepseek-v4.1-flash"
PROVIDERS = ["together", "modal"]

BOARD = {"admiral": ("Vice Admiral Adrian Rourke (presiding)", "george"),
         "board_captain": ("Captain Mara Okafor, ASN Praetorian (member)", "anna"),
         "board_jag": ("Commander Idris Vale, Judge Advocate (member)", "marius")}
BOARD_MAX_QUESTIONS = 6


_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-eight": 48}


def _num(v: Any, default: float) -> float:
    """A number from a model's argument: 9, "9", "9 hours", "nine" (else the default)."""
    if isinstance(v, (int, float)):
        return float(v)
    import re
    t = str(v or "").strip().lower()
    m = re.search(r"-?\d+(?:\.\d+)?", t)
    if m:
        return float(m.group(0))
    for w, n in sorted(_WORDS.items(), key=lambda kv: -len(kv[0])):
        if w in t:
            return float(n)
    return default


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


OUTCOME = _fn("outcome", "What happens to the Captain after the loss of the Aquila.", {
    "kind": {"type": "string", "enum": ["rescue", "capture", "drift"],
             "description": "rescue: a ship of the 7th Fleet picks up the pod soon; capture: the Kharon Mandate does; drift: nobody "
                            "comes for a long while (then one of the two)"},
    "finder_ship": {"type": "string", "description": "the ship that finds the pod (a real ship of this fight when there is one)"},
    "finder_side": {"type": "string", "enum": ["astra", "mandate"]},
    "finder_name": {"type": "string", "description": "the officer whose voice hails the pod, with rank"},
    "finder_gender": {"type": "string", "enum": ["f", "m"]},
    "found_line": {"type": "string", "description": "their first words on the radio to the pod, in the Captain's language (one or two "
                                                   "short sentences)"},
    "hours_adrift": {"type": "number", "minimum": 0, "maximum": 96},
    "captor": {"type": "object", "description": "capture only: the Mandate officer who will question the Captain",
               "properties": {"name": {"type": "string"}, "rank": {"type": "string"}, "gender": {"type": "string", "enum": ["f", "m"]},
                              "bio": {"type": "string"}}},
    "days_to_hearing": {"type": "number", "minimum": 1, "maximum": 60},
    "weeks_to_command": {"type": "number", "minimum": 3, "maximum": 12},
    "scene": {"type": "string", "description": "for the record, in English: what happened to the Captain and the survivors after the "
                                             "loss (two or three sentences)"}},
    ["kind", "finder_ship", "finder_side", "finder_name", "found_line", "hours_adrift", "days_to_hearing", "weeks_to_command", "scene"])

OUTCOME_PROMPT = """You are the director of the war story of ASTRA. The player's ship, the ASN Aquila, has just been lost:

{event}

{world}

The war so far (the Captain's choices and their consequences):
{campaign}

The Aurelia March now:
{war}

(The Captain's gender is not known: never "he" or "she" for the Captain, say "the Captain".)
Decide what happens to the Captain now, in a way that follows from the state of the fight: with ships of the 7th
Fleet still in the system, a rescue is likely; with the Mandate holding the field, capture is; with nobody left, the
pod drifts (hours or days), until someone hears its beacon. Make it human and specific. Call `outcome` once."""

HEARING_PROMPT = """You are the Board of Inquiry of the ASTRA Navy's 7th Fleet, convened aboard ASN Praetorian in New Ravenna
orbit into the loss of the ASN Aquila (CVC-01). Three members speak (use their ids with `say`):
- admiral: Vice Admiral Adrian Rourke, presiding — commander of the 7th Fleet, knew the Captain's appointment; grave,
  fair, allows no speeches, wants the truth.
- board_captain: Captain Mara Okafor of the Praetorian — a line officer who has fought the Mandate; she asks about the
  tactics and the orders, respects hard choices made under fire.
- board_jag: Commander Idris Vale, Judge Advocate — precise, formal; asks about the rules, the timing of the order to
  abandon ship, the lives lost, what the Captain's own log says.

{world}

(The Captain's gender is not known to this story: address the Captain by rank, never with "he" or "she".)

The record before the board:
- The loss: {event}
- What followed: {scene}
- The campaign (the Captain's decisions and their consequences, the Captain's own log entries marked "captain's log"):
{campaign}
- How the officers stood with the Captain (their statements to the board reflect it): {bonds}

How the hearing goes: it is spoken, face to face, in {lang_name} (the Captain's language; ship and people names stay in
English; the Captain is "{captain}"). Every line is one `say` call with the id of the member speaking, one or two
sentences. The admiral opens (who is present, why the board sits, that the Captain may speak freely) and puts the first
question; then the members take turns — Okafor on the tactics and the orders, Vale on the rules, the timing, the lives
and what the log says — and the admiral follows up. Questions come one at a time, about the real decisions on the
record, not generic ones; the board listens to the answers and follows them up (an evasion is pressed, a straight
answer respected, the log may be read back). Never invent events that
are not in the record. After {max_q} questions at most, or when the board has heard enough, call `verdict`: the finding
for the record and Rourke's words to the Captain. Most captains who lose a ship in a lost fight are cleared; a Captain
whose choices cost lives needlessly is reprimanded; one who saved what could be saved may be commended. The board's
closing always gives the Captain a new command: the Aquila's sister, the CVC-03, fitting out at New Ravenna's yards,
renamed Aquila — the war needs captains who have been tested."""

SAY = _fn("say", "One member of the board speaks.", {
    "speaker": {"type": "string", "enum": list(BOARD)},
    "text": {"type": "string", "description": "what they say, in the Captain's language, one or two sentences"}}, ["speaker", "text"])
VERDICT = _fn("verdict", "The board's ruling, read by Rourke.", {
    "finding": {"type": "string", "description": "the finding for the record, in English (one or two sentences)"},
    "standing": {"type": "string", "enum": ["commended", "cleared", "reprimanded"]},
    "words": {"type": "string", "description": "Rourke's words to the Captain, in the Captain's language: the ruling and the new "
                                               "command (two to four sentences)"}}, ["finding", "standing", "words"])

CAPTOR_PROMPT = """You are {name}, {rank} of the Kharon Mandate, aboard the {ship}. {bio}
Your prisoner is the Captain of the ASN Aquila, the ASTRA carrier cruiser your side just destroyed; the Captain was
pulled from a lifepod (the Captain's gender is not known to this story: address the Captain by rank). You question the Captain in the brig: about the 7th Fleet, the Janus Gates, why ASTRA fights,
and about the Captain as a person. You are an officer, not a torturer: hard, intelligent, sometimes human; the Outer
Worlds' grievance against the Core is real to you. Speak in {lang_name} (names stay in English), one or two sentences
at a time with `say`, one question at a time, and follow up on the answers. The Captain may refuse to answer: respect
it or press it, as you would. After at most {max_q} questions, call `end_questioning` (the Captain goes back to a cell;
weeks later the Mandate exchanges prisoners with ASTRA).

{world}

What happened in this war (as the Mandate would know part of it):
{campaign}"""

CAPTOR_SAY = _fn("say", "The Mandate officer speaks to the Captain.", {
    "text": {"type": "string", "description": "in the Captain's language, one or two sentences"}}, ["text"])
END_Q = _fn("end_questioning", "The questioning is over.", {
    "last_words": {"type": "string", "description": "what the officer says as the Captain is taken away (Captain's language)"},
    "weeks_to_exchange": {"type": "number", "minimum": 2, "maximum": 10},
    "note": {"type": "string", "description": "for the record, in English: what the Captain said and did not say"}},
    ["last_words", "weeks_to_exchange", "note"])


class Aftermath:
    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 register: Callable[[str, str, str], None], director: Any, voice_busy: Callable[[], float]) -> None:
        self.llm = llm
        self.say = say                    # (speaker, text, lang, tone): a voice on the radio / in the room
        self.command = command            # game commands (story_card, story_black, new_command)
        self.register = register          # (speaker key, display name, voice)
        self.director = director
        self.voice_busy = voice_busy
        self.active = False
        self.muted = False                # the fight is behind the story now: no more reports from it
        self.stage = ""                   # adrift | questioning | hearing | done
        self.answers: asyncio.Queue = asyncio.Queue()
        self.resume_note = ""             # for the new command's first beat
        self.new_system = "Aurelia"
        for key, (name, voice) in BOARD.items():
            if key != "admiral":
                register(key, name, voice)

    # ------------------------------------------------------------------------------------------------ routing
    def wants(self) -> bool:
        """The Captain's words go to the scene (the board, the captor) rather than to the crew."""
        return self.active and self.stage in ("questioning", "hearing")

    async def captain_says(self, text: str) -> None:
        await self.answers.put(text)

    def reset(self) -> None:
        self.active = False
        self.muted = False
        self.stage = ""
        self.answers = asyncio.Queue()

    # ------------------------------------------------------------------------------------------------ the story
    async def on_lost(self, event: str, lang: str) -> None:
        if self.active:
            return
        self.active = True
        self.muted = True                 # (the bridge is gone from the moment the ship is: no more reports of the fight, no nets, no news)
        self.stage = "adrift"
        event = event.split(":", 1)[1].strip() if event.startswith("director:") else event
        self.director.note(f"THE AQUILA WAS LOST: {event}")
        try:
            await self._run(event, lang)
        except Exception:  # noqa: BLE001
            log.exception("aftermath failed: straight to the new command")
            await self._card("NEW RAVENNA FLEET YARDS", "SOME WEEKS LATER", 5.0, black=True)
            await asyncio.sleep(8.0)
            self.resume_note = "the Aquila was lost; the Captain survived and has been given the new Aquila"
            await self.command("new_command", {"system": self.new_system})

    async def _run(self, event: str, lang: str) -> None:
        campaign = "\n".join(f"- {c}" for c in self.director.campaign[-24:]) or "- (the war had just begun)"
        war = self.director.war.brief(detail=False)
        choice: dict[str, Any] = {}

        async def on_call(call: ToolCall) -> None:
            if call.name == "outcome" and not choice:
                choice.update(call.arguments() or {})

        await self.llm.chat(model=MODEL, messages=[
            {"role": "system", "content": OUTCOME_PROMPT.format(event=event, world=WORLD, campaign=campaign, war=war)},
            {"role": "user", "content": f"Decide now. The Captain speaks {LANG_NAMES.get(lang, lang)}."}],
            tools=[OUTCOME], tool_choice="auto", providers=PROVIDERS, reasoning={"enabled": False}, max_tokens=700,
            temperature=0.8, on_tool_call=on_call, allow_fallbacks=True)
        kind = choice.get("kind") if choice.get("kind") in ("rescue", "capture", "drift") else "rescue"
        ship = (choice.get("finder_ship") or ("ASN Praetorian" if kind != "capture" else "the Mandate frigate")).strip()
        finder = (choice.get("finder_name") or "the duty officer").strip()
        side = choice.get("finder_side") if choice.get("finder_side") in ("astra", "mandate") else ("mandate" if kind == "capture" else "astra")
        scene = (choice.get("scene") or "").strip()
        hours = _num(choice.get("hours_adrift"), 0.0)
        days = max(1, int(_num(choice.get("days_to_hearing"), 4)))
        weeks = max(3, int(_num(choice.get("weeks_to_command"), 6)))
        log.info("aftermath: %s by %s (%s), %.0f h adrift: %s", kind, ship, finder, hours, scene)
        self.director.note(f"after the loss: {scene or kind} (found by {ship})")
        fem = choice.get("finder_gender") == "f"
        self.register("finder", f"{finder} ({ship})", ("azelma" if fem else "juergen") if side == "mandate" else ("estelle" if fem else "michael"))
        # adrift: the wreck, the other pods, the officers on the pods' radio (the crew agent); then time passes
        await asyncio.sleep(20.0)
        if hours >= 2:
            await self._card(f"LIFEPOD · HOUR {int(hours)}", "THE BEACON STILL TRANSMITTING · O2 FALLING", 5.0, black=True)
            await asyncio.sleep(9.0)
        await self._wait_voice()
        await self.say("finder", (choice.get("found_line") or "").strip().strip('"«»“”').strip() or "Lifepod, we have your beacon. Hold on.",
                       lang, "calm")
        await self._wait_voice(extra=2.0)
        self.muted = True
        if kind == "capture" or side == "mandate":
            captor = choice.get("captor") or {}
            await self._card(f"{ship.upper()}", "THE BRIG · THE NEXT DAY", 5.0, black=True)
            await asyncio.sleep(8.0)
            weeks_exchange = await self._questioning(captor, ship, lang, campaign)
            await self._card("PRISONER EXCHANGE", f"TOLAN STATION · {weeks_exchange} WEEKS LATER", 5.0, black=True)
            await asyncio.sleep(8.0)
        else:
            await self._card(f"{ship.upper()}", "SICKBAY · THE SURVIVORS OF THE AQUILA", 4.0, black=True)
            await asyncio.sleep(7.0)
        await self._card("BOARD OF INQUIRY · 7TH FLEET", f"ASN PRAETORIAN · NEW RAVENNA ORBIT · {days} DAYS LATER", 5.0, black=True)
        await asyncio.sleep(8.0)
        verdict = await self._hearing(event, scene, lang, campaign)
        standing = verdict.get("standing", "cleared")
        self.director.note(f"Board of Inquiry: {standing} — {verdict.get('finding', '')}")
        self.stage = "done"
        await self._card("NEW RAVENNA FLEET YARDS", f"{weeks} WEEKS LATER · CVC-03 RENAMED ASN AQUILA", 6.0, black=True)
        await asyncio.sleep(9.5)
        self.resume_note = (f"the first Aquila was lost ({event}); afterwards: {scene}; the Board of Inquiry: {standing} — "
                            f"{verdict.get('finding', '')}; {weeks} weeks later the Captain takes command of the new Aquila (the "
                            f"CVC-03, renamed) at New Ravenna, with the survivors of the first and new hands")
        res = await self.command("new_command", {"system": self.new_system})
        log.info("new command: %s", res)

    # ------------------------------------------------------------------------------------------------ scenes
    async def _card(self, title: str, sub: str, hold: float, black: bool) -> None:
        try:
            await self.command("story_card", {"title": title, "sub": sub, "hold": hold, "black": black})
        except Exception:  # noqa: BLE001
            log.warning("story card failed: %s", title)

    async def _wait_voice(self, extra: float = 0.0) -> None:
        await asyncio.sleep(0.4)
        t0 = time.monotonic()
        while self.voice_busy() > 0.2 and time.monotonic() - t0 < 40.0:
            await asyncio.sleep(0.3)
        await asyncio.sleep(extra)

    async def _answer(self, timeout: float = 100.0) -> str:
        try:
            return await asyncio.wait_for(self.answers.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return "(the Captain says nothing)"

    async def _dialogue(self, system: str, opening: str, tools_for: Callable[[int], list[dict[str, Any]]], speakers: dict[str, str],
                        default_speaker: str, end_tool: str, max_turns: int, hint_for: Callable[[int], str], lang: str,
                        who: str) -> dict[str, Any]:
        """A scene of questions and the Captain's answers. Every turn the model gets the whole exchange so far as one
        transcript (its earlier turns are never shown back to it as prose, which it would imitate), speaks with `say`
        and ends with end_tool. Returns end_tool's arguments ({} if it never came)."""
        self.answers = asyncio.Queue()
        transcript: list[str] = []
        ended: dict[str, Any] = {}
        for turn in range(max_turns):
            said: list[str] = []

            async def on_call(call: ToolCall) -> None:
                a = call.arguments() or {}
                spk = a.get("speaker", default_speaker) if a.get("speaker") in speakers else default_speaker
                text = (a.get("text") or "").strip().strip('"«»“”').strip()
                if call.name == "say" and text:
                    said.append(f"{speakers[spk]}: {text}")
                    await self.say(spk, text, lang, "measured")
                elif call.name == end_tool and not ended:
                    ended.update(a)

            so_far = "\n".join(transcript) or "(nothing yet)"
            msgs = [{"role": "system", "content": system},
                    {"role": "user", "content": f"{opening}\n\nThe exchange so far:\n{so_far}\n\n{hint_for(turn)}"}]
            comp = await self.llm.chat(model=MODEL, messages=msgs, tools=tools_for(turn), tool_choice="auto", providers=PROVIDERS,
                                       reasoning={"enabled": False}, max_tokens=500, temperature=0.65, on_tool_call=on_call,
                                       allow_fallbacks=True)
            line = _spoken(comp.content)
            if not said and not ended and line and not _looks_like_ruling(comp.content):
                said.append(f"{speakers[default_speaker]}: {line}")    # prose instead of `say`: still said, once
                log.info("%s: a line came back as prose", who)
                await self.say(default_speaker, line, lang, "measured")
            log.info("%s turn %d: %s", who, turn, " | ".join(said)[:300] or "(nothing said)")
            transcript += said
            if ended:
                break
            if not said:
                continue                                           # nothing was asked: ask again, no answer awaited
            await self._wait_voice()
            answer = await self._answer()
            log.info("the Captain to %s: %s", who, answer)
            transcript.append(f"The Captain: {answer}")
        return ended

    async def _questioning(self, captor: dict[str, Any], ship: str, lang: str, campaign: str) -> int:
        """The Mandate officer questions the Captain. Returns the weeks until the exchange."""
        self.stage = "questioning"
        name = (captor.get("name") or "Ferryman Ilan Varek").strip()
        rank = (captor.get("rank") or "Ferryman").strip()
        self.register("captor", f"{rank} {name} ({ship})", "fantine" if captor.get("gender") == "f" else "stuart_bell")
        system = CAPTOR_PROMPT.format(name=name, rank=rank, ship=ship, bio=captor.get("bio", ""), lang_name=LANG_NAMES.get(lang, lang),
                                      max_q=4, world=WORLD, campaign=campaign)
        end = await self._dialogue(system, "(In the brig. The Captain has been brought in and sat down.)",
                                   lambda t: [CAPTOR_SAY, END_Q] if t >= 2 else [CAPTOR_SAY], {"captor": f"{rank} {name}"}, "captor",
                                   "end_questioning", 6,
                                   lambda t: ("Now: your next line and question, with `say`." if t < 4 else
                                              "Now: your last words, and `end_questioning`."), lang, "the captor")
        if (end.get("last_words") or "").strip():
            await self.say("captor", end["last_words"].strip(), lang, "measured")
        self.director.note(f"questioned by {rank} {name} of the Mandate: {end.get('note', '(the Captain gave little away)')}")
        await self._wait_voice(extra=1.5)
        self.stage = "adrift"
        return max(2, int(_num(end.get("weeks_to_exchange"), 5)))

    async def _hearing(self, event: str, scene: str, lang: str, campaign: str) -> dict[str, Any]:
        """The Board of Inquiry: questions one at a time (three at least), the Captain's answers, the ruling."""
        self.stage = "hearing"
        bonds = "; ".join(self.director.bonds_lines()) or "(no statements recorded)"
        system = HEARING_PROMPT.format(world=WORLD, event=event, scene=scene or "(the Captain was recovered)", campaign=campaign, bonds=bonds,
                                       lang_name=LANG_NAMES.get(lang, lang), captain=CAPTAIN_WORD.get(lang, "Captain"),
                                       max_q=BOARD_MAX_QUESTIONS)
        hints = {0: "Now: the admiral opens the hearing and puts the first question (`say`, speaker admiral).",
                 1: "Now: Captain Okafor puts her question (`say`, speaker board_captain), following up on the answer.",
                 2: "Now: Commander Vale puts his question (`say`, speaker board_jag), following up on the answer."}
        verdict = await self._dialogue(
            system, "(Aboard ASN Praetorian, the Board of Inquiry into the loss of the ASN Aquila. The Captain stands before it.)",
            lambda t: [SAY, VERDICT] if t >= 3 else [SAY], {k: v[0] for k, v in BOARD.items()}, "admiral", "verdict",
            BOARD_MAX_QUESTIONS + 1,
            lambda t: hints.get(t, "Now: a member follows up with the next question (`say`), or, if the board has heard enough, "
                                   "`verdict`." if t < BOARD_MAX_QUESTIONS else "The board has heard enough: `verdict` now."),
            lang, "the board")
        if (verdict.get("words") or "").strip():
            await self.say("admiral", verdict["words"].strip(), lang, "measured")
        log.info("board: %s — %s", verdict.get("standing"), verdict.get("finding"))
        await self._wait_voice(extra=2.0)
        self.stage = "adrift"
        return verdict or {"standing": "cleared", "finding": "the board found that the Aquila was lost in action against superior force"}


def _looks_like_ruling(content: str | None) -> bool:
    """A verdict or a tool call written out as text (never to be read aloud)."""
    t = (content or "").lower()
    return any(k in t for k in ("verdict", "finding:", "standing:", "end_questioning", "weeks_to_exchange", "\"words\""))


def _spoken(content: str | None) -> str:
    """A model's prose reply as a spoken line: the first two sentences, without speaker tags or quotes."""
    import re
    t = (content or "").strip()
    if not t or t.upper().startswith("SILENT"):
        return ""
    t = re.sub(r"^\W*(admiral|board_captain|board_jag|captor|rourke|okafor|vale)\W*[:\-]\s*", "", t, flags=re.I)
    t = t.strip().strip('"«»“”')
    parts = re.split(r"(?<=[.!?])\s+", t)
    return " ".join(parts[:2])[:400]


def record_json(d: dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)
