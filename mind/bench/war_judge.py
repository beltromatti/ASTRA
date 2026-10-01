"""A model judges the allied captains' words (docs/ARCHITETTURA.md §1bis: the quality of speech is judged by playing, or by a judge model, never by
patterns over the text). Reads an arena record (Saved/War/<tag>_<seed>.mind.json) and, for every line an allied captain said over the fleet net, gives the
judge what the captain was looking at when they spoke and the line itself.

    cd mind && .venv/bin/python -m bench.war_judge live4 1 [--limit 12]     (a few tenths of a cent a line, live)

Scores 1-5: useful (the Captain needs it or can act on it), brief (a clipped radio line), true (it agrees with the picture), character (it is who
they are), timely (the right moment: not a repeat, not a lecture). `silent`: a good captain would have said nothing here. Also reported: lines per
minute of battle (few is the point)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mind"))

from astra_mind import models  # noqa: E402
from astra_mind.openrouter import OpenRouter  # noqa: E402

WAR = ROOT / "Saved" / "War"
JUDGE_ROLE = "chatter"            # a model of another family than the captains' (they run on DeepSeek): a judge that is the same model flatters it

SYSTEM = """You judge the radio talk of a ship's captain in a military space-war game (the ASTRA Navy against the Kharon Mandate). You are given what the captain
was looking at when they spoke — their persona, their log, the picture of the battle, the words that had reached them — and ONE line they said over the
fleet net to the Captain of the carrier Aquila (the player). Judge the line strictly, as a demanding naval officer and a screenwriter would. The fleet net is
not a chat: a good captain speaks rarely, briefly, and only when it helps; a bad one narrates the picture, repeats himself, speaks to be heard, invents
facts, or breaks character.

Score each from 1 to 5:
- useful: the Captain needs it or can act on it (a warning he may have missed, a request that needs an answer, an answer to what he asked, a loss, what the
  captain is doing that concerns the Aquila). 1 = noise; 5 = essential.
- brief: a clipped radio line of one or two short sentences. 1 = rambling; 5 = perfect.
- true: every fact in it agrees with the picture and the log (ships, numbers, positions, what was ordered). 1 = invented or contradicted; 5 = checks out.
- character: it sounds like the person in the persona. 1 = generic or out of character; 5 = unmistakably them.
- timely: right moment, not a repeat of what was just said, not a lecture. 1 = wrong time; 5 = exactly now.
`silent`: true if a good captain in this situation would have said nothing at all.
Reply with JSON only: {"useful": n, "brief": n, "true": n, "character": n, "timely": n, "silent": true|false, "note": "one short sentence"}"""


async def judge(llm: OpenRouter, ctx: str, speaker: str, line: str, tone: str) -> dict[str, Any]:
    comp = await models.chat(llm, JUDGE_ROLE, messages=[{"role": "system", "content": SYSTEM},
                                                         {"role": "user", "content": f"{ctx}\n\nTHE LINE (spoken by {speaker}, tone {tone}):\n\"{line}\""}],
                             max_tokens=220, temperature=0.0)
    m = re.search(r"\{.*\}", comp.content or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


async def main_async(a: argparse.Namespace) -> None:
    d = json.loads((WAR / f"{a.tag}_{a.seed}.mind.json").read_text())
    lines = [l for l in d.get("lines", []) if l["speaker"] not in ("solm",)]
    pulses = [p for p in d["pulses"] if p["seat"].startswith("astra")]
    span = max(1.0, d["result"].get("battle_s", 0.0) - (pulses[0]["t"] if pulses else 0.0))
    print(f"{len(lines)} line(s) from the allied captains in {span / 60:.1f} min of battle: {len(lines) / (span / 60):.1f} per minute ({len(lines) / (span / 3600):.0f} per hour)")
    if not lines:
        return
    llm = OpenRouter()
    rows = []
    try:
        for ln in lines[: a.limit]:
            p = max((p for p in pulses if p["t"] <= ln["t"] + 0.5), key=lambda p: p["t"], default=None)
            if p is None or not p.get("user"):
                continue
            ctx = f"THE CAPTAIN'S SEAT (persona and orders):\n{p['system'].split('How a fleet fights')[0].strip()[:1400]}\n\nWHAT THEY WERE LOOKING AT:\n{p['user']}"
            r = await judge(llm, ctx, ln["speaker"], ln["text"], ln["tone"])
            rows.append((ln, r))
            print(f"\n[{ln['t']:6.1f}] {ln['speaker']} ({ln['tone']}{', answer' if ln.get('answer') else ''}): {ln['text']}\n         -> {json.dumps(r)}")
    finally:
        await llm.close()
    ok = [r for _, r in rows if r]
    if ok:
        keys = ("useful", "brief", "true", "character", "timely")
        print("\nmeans over %d lines: " % len(ok) + ", ".join(f"{k} {statistics.mean(float(r.get(k, 0)) for r in ok):.2f}" for k in keys)
              + f"; a good captain would have stayed silent in {sum(1 for r in ok if r.get('silent'))} of them; judge spend ${models.LEDGER.total:.4f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("seed", type=int, nargs="?", default=1)
    ap.add_argument("--limit", type=int, default=12)
    a = ap.parse_args()
    models.LEDGER.write_file = True
    models.LEDGER.cap = float(os.environ.get("ARENA_CAP", "0.8"))
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
