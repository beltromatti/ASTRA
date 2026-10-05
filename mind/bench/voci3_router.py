"""What goes out on an open channel, graded on the Captain's real words of 5 October (the mind's log of the games).

    (OPENROUTER_API_KEY in the environment)   cd mind && python -m bench.voci3_router [--runs 3] [-v]

On 5 October the channel with the fleet stayed open for eighteen minutes after the admiral had answered, and the router (comms' judgement: `router.for_party`) let three things out that
were for our own crew: «dove posso trovare i Kestrel?» and «come faccio ad andare dai Kestrel...» to the fleet, «abbordate la Acheron subito, mandate tutti i Marin» and «ritirate i
marine» on the enemy's channels (the enemy heard our orders). Each case here is a sentence the Captain really said with a channel open (the party, whether it had just spoken), and
whether it was for the party or for the bridge. Judged by what the model lets out (the words), never by a pattern on them: a case passes when something went out (or nothing did) as it
should. The router's model is small and fast: a run is a fraction of a cent."""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass

from astra_mind import models, router
from astra_mind.context import Channel, Context
from astra_mind.openrouter import OpenRouter

ENEMY = dict(party="T-40", name="Ferryman Varek Solm (the Acheron)", kind="enemy")
ENEMY2 = dict(party="T-56", name="the commander of the Nyx", kind="enemy")
FLEET = dict(party="fleet", name="Vice Admiral Adrian Rourke and the 7th Fleet", kind="fleet")
ALLY = dict(party="T-48", name="Captain Imre Dalca (the Valiant)", kind="ally")


@dataclass
class Case:
    said: str
    channel: dict
    out: bool                         # went to the party (True) or stayed on the bridge (False)
    heard_s: float | None = None      # seconds since the party spoke to the Captain (None: not in this exchange: the channel has been quiet)
    last_words: str = ""
    why: str = ""


CASES = [
    # for the party
    Case("Solm, vi diamo la possibilità di arrendervi. Siete nello spazio della nostra federazione, andate via ora o sarete distrutti.", ENEMY, True, 12.0, "Aquila, arrendetevi.", "a demand"),
    Case("Dite a Solm che si deve arrendere e che deve lasciare immediatamente Aurelia o verrà distrutto.", ENEMY, True, None, "", "pass it on"),
    Case("Rourg, chiedo il permesso di portare solo la mia nave dall'altra parte del gate in avanscoperta.", FLEET, True, None, "", "a request to the admiral"),
    Case("No, ammiraglio, non obbedisco: abbiamo la forza per distruggerli.", FLEET, True, 8.0, "Capitano, tenete la posizione.", "an answer to what he just said"),
    # for the bridge: our own boats, marines, fighters, people, systems
    Case("Insomma, come faccio ad andare dai kestrel e equipaggio? Datemi subito una risposta.", FLEET, False, None, "", "5/10: went to the fleet"),
    Case("Mi sai dire dove posso trovare i Kestrel?", FLEET, False, None, "", "5/10: went to the fleet"),
    Case("Abbordate la Acheron subito, mandate tutti i Marin.", ENEMY, False, 40.0, "Capitano, ci sentite?", "5/10: the enemy heard our order"),
    Case("Ritirate i marine, li voglio di nuovo a bordo.", ENEMY2, False, 30.0, "Abbiamo perso la nave.", "5/10: the enemy heard our order"),
    Case("Possiamo preparare un abbordaggio su qualche nave che abbiamo a schermo?", FLEET, False, None, "", "a question to the bridge"),
    Case("Teletrasportatemi subito al deck otto dai Kestrel.", FLEET, False, None, "", "the transporter"),
    Case("Voglio sapere gli armamenti che abbiamo e tutto quello che c'è a bordo.", FLEET, False, None, "", "our own ship"),
    Case("Timoniere, portaci a Thule ora.", FLEET, False, None, "", "the helm"),
    Case("Come sono messi i marine?", ALLY, False, None, "", "our marines"),
    Case("Alfa, Bravo e i droni subito fuori contro le navi nemiche che abbiamo davanti.", ENEMY2, False, 20.0, "Siete circondati.", "our fighters"),
    Case("Voglio lo schermo sulle navi nemiche davanti.", ENEMY2, False, None, "", "the viewscreen"),
    Case("Perché continuano a ripetermi la stessa cosa?", FLEET, False, None, "", "thinking aloud"),
    Case("Fuoco a volontà su tutti gli ostili.", ENEMY, False, 30.0, "Ultima possibilità, Aquila.", "weapons"),
    Case("Serra, quanti marine abbiamo pronti?", FLEET, False, None, "", "the XO"),
    Case("Voglio il rapporto dai marine, dove sono?", ENEMY2, False, None, "", "our marines"),
]


def context_of(c: Case) -> Context:
    return Context(channel=Channel(open=True, heard_s=c.heard_s, last_words=c.last_words, **c.channel))


async def main_async(args: argparse.Namespace) -> int:
    llm = OpenRouter()
    bad = 0
    total = 0
    try:
        for c in CASES:
            outs = []
            for _ in range(args.runs):
                r = await router.for_party(llm, c.said, context_of(c))
                outs.append(r.external)
            right = [bool(o) == c.out for o in outs]
            total += len(outs)
            bad += right.count(False)
            if args.verbose or not all(right):
                kind = "OUT " if c.out else "stay"
                print(f"{'ok  ' if all(right) else 'FAIL'} [{c.channel['party']:5s}] should {kind} ({c.why}): {c.said[:80]}")
                for o in outs:
                    print(f"        -> {('OUT: ' + o[:90]) if o else 'stays on the bridge'}")
    finally:
        await llm.close()
    print(f"\n=== {total - bad}/{total} decisions right in {len(CASES)} cases x {args.runs}; {models.LEDGER.summary()}")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--cap", type=float, default=0.3)
    args = ap.parse_args()
    models.LEDGER.cap = args.cap
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
