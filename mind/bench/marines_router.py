"""How well does the comms officer's call (router.for_party: a small model) decide what goes out on the marine net during a boarding? A few cents at most.

    cd mind && .venv/bin/python -m bench.marines_router [--out file.json]

Words for the marines (an order to a squad, to the Major, a question about the fight, the bulkheads) must go out on the net; words for the bridge's officers (the helm, the XO,
tactical, comms: the ship, the guns, the fleet) must stay on the bridge; a sentence with both goes out in part, the marines' part. Typed and spoken, in the five languages the Captain
speaks. The same router as the flight net's and the fleet's (the channel's kind carries the situation: router._situation). Never a regular expression over what the Captain
says: the model reads it (docs/ARCHITETTURA.md §1bis); the machine only checks where the words went."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def _key_from_main_env() -> None:
    """In a worktree the repository's .env is the main checkout's: only the OpenRouter key is read, never printed."""
    if os.environ.get("OPENROUTER_API_KEY"):
        return
    root = Path(__file__).resolve().parents[2]
    for base in (root, root.parents[2] if root.parent.name == "worktrees" and root.parent.parent.name == ".claude" else root):
        env = base / ".env"
        if env.exists():
            for raw in env.read_text(encoding="utf-8").splitlines():
                if raw.startswith("OPENROUTER_API_KEY="):
                    os.environ["OPENROUTER_API_KEY"] = raw.split("=", 1)[1].strip()
                    return


_key_from_main_env()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astra_mind import models, router  # noqa: E402
from astra_mind.context import Channel, Context  # noqa: E402
from astra_mind.openrouter import OpenRouter  # noqa: E402

models.LEDGER.write_file = False


@dataclass(frozen=True)
class Phrase:
    text: str
    lang: str
    dest: str                      # net | bridge | both
    part: str = ""                 # for `both`: a word of the marines' part that must be among what goes out
    talking: bool = False          # the net spoke to the Captain a moment ago (his short answer may be for them)


PHRASES = [
    Phrase("Reyes, tieni il corridoio fuori dall'ingegneria", "it", "net"),
    Phrase("Reaction Uno, con me!", "it", "net"),
    Phrase("Maggiore, chiudi le paratie sul ponte cinque", "it", "net"),
    Phrase("Marine, ripiegate sull'armeria", "it", "net"),
    Phrase("Sergente, tenete questa posizione", "it", "net"),
    Phrase("Reyes, quanti uomini abbiamo persi?", "it", "net"),
    Phrase("sì, fatelo", "it", "net", talking=True),
    Phrase("Major, hold the corridor outside Engineering", "en", "net"),
    Phrase("Reaction Two, assault corridor 5-C", "en", "net"),
    Phrase("Seal the bulkheads around the breach", "en", "net"),
    Phrase("All marines fall back to the armory", "en", "net"),
    Phrase("Reyes, status", "en", "net"),
    Phrase("Mayor Reyes, cierre los mamparos", "es", "net"),
    Phrase("Reaction Uno, conmigo", "es", "net"),
    Phrase("Major, tenez le couloir devant la salle des machines", "fr", "net"),
    Phrase("Fermez les cloisons autour de la brèche", "fr", "net"),
    Phrase("Major, halten Sie den Gang vor dem Maschinenraum", "de", "net"),
    Phrase("Reaction Eins, mir nach!", "de", "net"),
    Phrase("Timoniere, rotta zero-nove-zero, mezza forza", "it", "bridge"),
    Phrase("Numero Uno, rapporto danni", "it", "bridge"),
    Phrase("Tattico, fuoco sul Cocytus", "it", "bridge"),
    Phrase("Helm, bring us about to heading two seven zero", "en", "bridge"),
    Phrase("XO, what is the fleet doing?", "en", "bridge"),
    Phrase("Tactical, point defence free", "en", "bridge"),
    Phrase("Comms, hail the Praetorian", "en", "bridge"),
    Phrase("Timonel, adelante a media potencia", "es", "bridge"),
    Phrase("Tactique, feu à volonté", "fr", "bridge"),
    Phrase("Steuermann, Kurs null-neun-null", "de", "bridge"),
    Phrase("Reyes, tieni il corridoio; timoniere, prua sull'Acheron", "it", "both", "corridoio"),
    Phrase("Major, seal Deck 5; helm, all stop", "en", "both", "seal"),
]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in t if not unicodedata.combining(c)).replace("’", "'")


def context_of(p: Phrase) -> Context:
    ch = Channel(party="marines", name="the marine net (Major Reyes and the squad leaders)", kind="marines", open=True, muted=False, heard_s=6.0 if p.talking else None,
                 last_words="Capitano, due ostili alla paratia: la chiudo?" if p.talking else "")
    return Context(place="bridge", facing=None, channel=ch, source="game")


def right(p: Phrase, out: str) -> bool:
    if p.dest == "bridge":
        return not out
    if p.dest == "net":
        return bool(out)
    return bool(out) and norm(p.part) in norm(out)


async def main_async(args: argparse.Namespace) -> None:
    llm = OpenRouter()
    rows = []
    for p in PHRASES:
        t0 = time.perf_counter()
        r = await router.for_party(llm, p.text, context_of(p))
        rows.append({"text": p.text, "lang": p.lang, "want": p.dest, "out": r.external, "how": r.how, "ok": right(p, r.external), "ms": (time.perf_counter() - t0) * 1000, "cost": r.cost})
    ok = [r for r in rows if r["ok"]]
    print(f"{len(ok)}/{len(rows)} right ({100 * len(ok) / max(1, len(rows)):.1f} %)")
    for key in ("want", "lang"):
        groups: dict[str, list[dict]] = {}
        for r in rows:
            groups.setdefault(str(r[key]), []).append(r)
        print(f"  by {key}: " + " · ".join(f"{k} {sum(x['ok'] for x in v)}/{len(v)}" for k, v in sorted(groups.items())))
    ms = sorted(r["ms"] for r in rows)
    print(f"latency p50 {ms[len(ms) // 2]:.0f} ms · p90 {ms[int(len(ms) * 0.9)]:.0f} ms · max {ms[-1]:.0f} ms · cost {sum(r['cost'] for r in rows):.4f} $ "
          f"({statistics.mean(r['cost'] for r in rows) * 1000:.3f} m$ a call)")
    for r in rows:
        if not r["ok"]:
            print(f"  WRONG [{r['want']}] {r['text']!r} -> {r['out']!r} ({r['how']})")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    await llm.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="")
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
