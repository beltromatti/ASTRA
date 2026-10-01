"""The director v2 against the real model on scripted situations (a few tenths of a cent a beat): what does it decide when the Captain is battered and
tired, when he is crushing the enemy and rested, when a long fight is looked in on, when the war has just begun?

    cd mind && .venv/bin/python -m bench.war_director_live [--only tired,strong,battle,fresh]

Nothing is sent to a game: every command the director would send is printed with its result (as the game answers a beat: ok and the ids)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astra_mind import director as dr  # noqa: E402
from astra_mind import models  # noqa: E402
from astra_mind.openrouter import OpenRouter  # noqa: E402
from astra_mind.war import WarMap  # noqa: E402
from astra_mind.war_minds import WarMinds  # noqa: E402


class Clock:
    t = 5000.0

    def __call__(self) -> float:
        return self.t


def contacts(hostile: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    out = [{"id": "T-01", "name": "ASN Praetorian", "class": "praetorian", "status": "friendly", "range_km": 4.0, "bearing_deg": 20, "hull_pct": 70},
           {"id": "T-02", "name": "ASN Vigilant", "class": "vigilant", "status": "friendly", "range_km": 6.0, "bearing_deg": 80, "hull_pct": 95}]
    for cid, cls, rng in hostile:
        out.append({"id": cid, "name": cid, "class": cls, "status": "hostile", "range_km": rng, "bearing_deg": 240, "hull_pct": 80})
    return out


SCENES = {
    "tired": dict(
        state={"hull_pct": 34, "shields": {"strength_pct": 20}, "weapons": {"missiles": "18 in the VLS"}, "casualties": "17 killed, 31 wounded (the fallen: Petty Officer Amara Diallo)",
               "alert": "red", "contacts": contacts([]), "thermal": {"heat_pct": 71}, "damage": ["Deck 7 B: fire — unattended", "Deck 9 C: breach"], "_events": ["tactical: the last Styx has broken off"]},
        past=[("fight", 1500), ("peace", 40)], runs=3,
        campaign=["engagement over — victory: the surviving enemy ships broke off and withdrew",
                  "beat: raid — Mandate patrol probes the picket (T-31, T-32)", "beat: raid — a second group under Ferryman Doran Kade tests the Aquila's shields (T-41, T-42)",
                  "Rourke granted resupply: hull to 85 %", "the Captain's log: I don't like what these fights are costing us"]),
    "strong": dict(
        state={"hull_pct": 96, "shields": {"strength_pct": 100}, "weapons": {"missiles": "88 in the VLS"}, "casualties": "none", "alert": "green", "contacts": contacts([]),
               "thermal": {"heat_pct": 12}, "damage": [], "_events": ["director: engagement over — victory: no hostile ship left"]},
        past=[("fight", 420), ("peace", 600)], runs=1,
        campaign=["beat: raid — three Styx probe the picket", "engagement over — victory: no hostile ship left; the Aquila untouched, two Mandate ships destroyed",
                  "the Captain spared the Cocytus's captain (Ferryman Irina Vael), who surrendered", "beat: calm — a quiet watch"]),
    "battle": dict(
        state={"hull_pct": 58, "shields": {"strength_pct": 45}, "weapons": {"missiles": "30 in the VLS"}, "casualties": "4 killed", "alert": "red",
               "contacts": contacts([("T-21", "acheron", 9.0), ("T-22", "styx", 11.0), ("T-23", "styx", 12.0)]), "thermal": {"heat_pct": 64}, "damage": ["Deck 3 A: fire"],
               "_events": ["sensors: the Acheron's shields are collapsing on the port side"]},
        past=[("peace", 400), ("fight", 330)], runs=1, battle=True,
        campaign=["beat: raid — the Mandate strike group arrives (Archon Varek Solm)"]),
    "fresh": dict(
        state={"hull_pct": 100, "shields": {"strength_pct": 100}, "weapons": {"missiles": "96 in the VLS"}, "casualties": "none", "alert": "green", "contacts": contacts([]),
               "thermal": {"heat_pct": 5}, "damage": [], "_events": []},
        past=[("peace", 200)], runs=0, campaign=[]),
}


async def run(name: str, scene: dict[str, Any], llm: OpenRouter, tmp: str) -> None:
    clock = Clock()
    commands: list[tuple[str, dict[str, Any]]] = []
    said: list[str] = []

    async def say(speaker: str, text: str, lang: str, tone: str) -> None:
        said.append(f"{speaker}: {text}")

    async def command(cmd: str, args: dict[str, Any]) -> dict[str, Any]:
        commands.append((cmd, args))
        return {"ok": True, "detail": f"{args.get('beat', {}).get('type', cmd)} scheduled in {args.get('beat', {}).get('delay_s', 60)} s; contact ids T-51, T-52, T-53; the first is the group's leader"}

    async def negotiate(contact: str, terms: str) -> bool:
        print(f"   -> negotiation: {contact} calls the Aquila: {terms}")
        return True

    d = dr.Director(llm, say, command, lambda c, p: print(f"   -> a Mandate commander for {c}: {p.get('name')} ({p.get('rank')}) — {p.get('bio', '')[:100]}"),
                    war=WarMap(f"{tmp}/{name}_war.json"))
    d.clock = clock
    d.negotiate = negotiate
    d.war_minds = WarMinds(llm, say, command)
    d.t0 = d._last_obs = d.last_pulse_t = clock() - 1800
    d.peace_since = clock() - 1800
    d.campaign[:] = scene["campaign"]
    state = scene["state"]
    quiet = {**state, "contacts": contacts([])}
    fight = {**state, "contacts": contacts([("T-21", "acheron", 12.0)])}
    for kind, secs in scene["past"]:
        for _ in range(int(secs)):
            clock.t += 1.0
            d.observe(fight if kind == "fight" else quiet)
    d.in_a_row = scene["runs"] or d.in_a_row
    print(f"\n=== {name}\n{d.pulse_facts(state)}")
    before = models.LEDGER.total
    await d._next_beat("en", state, in_battle=bool(scene.get("battle")))
    for cmd, args in commands:
        beat = args.get("beat", {})
        short = {k: v for k, v in beat.items() if k in ("type", "delay_s", "range_km", "bearing_deg", "ships", "attackers", "hull_pct", "missiles", "system_name", "allies")}
        print(f"   beat: {json.dumps(short, ensure_ascii=False)[:420]}")
    for line in said:
        print(f"   {line}")
    print(f"   why: {d.campaign[-1][:240]}")
    print(f"   mood: {d.mood}")
    print(f"   threads: {d.threads}")
    print(f"   (spent ${models.LEDGER.total - before:.4f})")


async def main_async(a: argparse.Namespace) -> None:
    models.LEDGER.write_file = False
    llm = OpenRouter()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for name in a.only.split(","):
                await run(name, SCENES[name], llm, tmp)
        print(f"\ntotal ${models.LEDGER.total:.4f}")
    finally:
        await llm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="tired,strong,battle,fresh")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
