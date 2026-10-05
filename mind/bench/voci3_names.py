"""The names the speech recogniser got wrong in the Captain's real games, and what the glossary does to ordinary words (docs/protocollo_voce.md §9).

    cd mind && .venv/bin/python -m unittest bench.voci3_names -v
    cd mind && .venv/bin/python -m bench.voci3_names --audit [--scene]

On 5 October the Captain said 116 sentences by voice (bench/data/games_2026-10-05: the text the crew read, after the glossary of that day). About half of the war's names in them were
spelled by ear: «Toul» and «Tool» for Thule, «Renis» and «Lerinis» (l'Erinys) for Erinys, «plegeton», «Taratus», «solmo», «Chestrel», «Rourg». The crew's models read nearly all of them
right from the ship's state (the helm took «la lettera» for the Lethe, the tactical officer «le Renis» for the Erinys); the glossary (voice_glossary.py) is what puts the right spelling in the
subtitle and in the words the router and the allied captains read. Its rule: a wrong correction puts a name in the Captain's mouth that he never said, a missed one costs nothing, so a
name is fixed by an explicit alias (a spelling the recogniser really wrote, never an ordinary word) or, for a long distinctive name, by a close phonetic match.

`--audit` puts every word of three lexicons (the vocabulary of Whisper's multilingual tokenizer, the project's own docs, an English dictionary) through the glossary, in the middle of a
sentence, and lists the ones it rewrites. `--scene` asks the question the lead put on 5 October: would a glossary that knows the names in play (the ships and people on the map now) and
matches them more loosely correct more than it breaks? It measures what a looser match takes from the ordinary words of the languages: no, so the glossary stays as it is."""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import unittest
from collections import defaultdict
from pathlib import Path

from astra_mind.voice_glossary import GLOSSARY, _fold, _sim, phon
from astra_mind.voice_stt_backends import VOICE_MODELS

DATA = Path(__file__).resolve().parent / "data" / "games_2026-10-05"
TOKENIZER = VOICE_MODELS / "models" / "openai" / "whisper-large-v3" / "tokenizer.json"

# what the recogniser wrote on 5 October for a name, and the name: the ones a spelling alias fixes, and the ones nothing safe can (a real word: «tool», «Ruth», «lettera»)
FIXED = [("plegeton", "Phlegethon"), ("Taratus", "Tartarus"), ("Renis", "Erinys"), ("Lerinis", "Erinys"), ("solmo", "Solm"), ("Chestrel", "Kestrel"), ("Keglex", "Kestrel"),
         ("Kellex", "Kestrel"), ("Rourg", "Rourke"), ("Toul", "Thule")]
NOT_FIXABLE = [("Tool", "Thule"), ("Ruth", "Rourke"), ("lettera", "Lethe")]

# what the glossary may rewrite among the words of the languages: spellings it was given on purpose, from the recognisers' real mistakes
ON_PURPOSE = {"acron", "foss", "sticks", "tule", "vos"}


def real_sentences() -> list[str]:
    out = []
    for game in ("s2", "s3"):
        out += [c["text"] for c in json.loads((DATA / f"{game}.json").read_text(encoding="utf-8"))["captain"] if c.get("how") == "voice"]
    return out


def whisper_words() -> set[str]:
    """The words of Whisper's multilingual vocabulary (about 24 thousand, the common ones of ninety-nine languages)."""
    tok = json.loads(TOKENIZER.read_text(encoding="utf-8"))
    return {t[1:].lower() for t in tok["model"]["vocab"] if t.startswith("Ġ") and re.fullmatch(r"[^\W\d_]{3,}", t[1:], re.U)}


def docs_words() -> set[str]:
    root = Path(__file__).resolve().parents[2] / "docs"
    out: set[str] = set()
    for p in glob.glob(str(root / "*.md")) + glob.glob(str(root / "*" / "*.md")):
        out |= {w.lower() for w in re.findall(r"[^\W\d_]{3,}", Path(p).read_text(encoding="utf-8"), re.U)}
    return out


def english_words() -> set[str]:
    p = Path("/usr/share/dict/words")
    return {w.lower() for w in p.read_text(encoding="latin-1").split() if re.fullmatch(r"[A-Za-z]{3,}", w)} if p.exists() else set()


def rewritten(words: set[str]) -> list[tuple[str, str]]:
    """The words the glossary changes (in the middle of a sentence: the first or the last word of an order is read as an officer's name on purpose)."""
    out = []
    for w in sorted(words):
        said = f"e poi {w} subito"
        fixed, fixes = GLOSSARY.correct(said)
        if fixes and _fold(fixed) != _fold(said) and fixed.startswith("e poi ") and fixed.endswith(" subito"):
            out.append((w, fixed[len("e poi "):-len(" subito")]))
    return out


class TestTheNamesOfTheRealGames(unittest.TestCase):
    def test_the_spellings_of_5_october_come_out_as_the_names(self) -> None:
        for heard, name in FIXED:
            self.assertEqual(GLOSSARY.correct(f"Timoniere, portaci su {heard} adesso.")[0], f"Timoniere, portaci su {name} adesso.", heard)

    def test_a_real_word_is_never_given_a_name(self) -> None:
        for heard, _ in NOT_FIXABLE:
            self.assertEqual(GLOSSARY.correct(f"Timoniere, portaci su {heard} adesso.")[1], [], heard)
        for word in ("constante", "costanza", "velocità costante", "tool", "casa", "solo", "sole", "late", "cannone", "mensa", "caccia"):
            self.assertEqual(GLOSSARY.correct(f"mantenete {word} per favore")[1], [], word)

    def test_the_real_sentences_lose_no_word_and_gain_only_names(self) -> None:
        edits = [e for s in real_sentences() for e in GLOSSARY.correct(s)[1]]
        self.assertEqual(sorted(edits), sorted([("solmo", "Solm"), ("plegeton", "Phlegethon"), ("plegeton", "Phlegethon"), ("Rourg", "Rourke"), ("Chestrel", "Kestrel"),
                                                ("Keglex", "Kestrel"), ("Kellex", "Kestrel"), ("Taratus", "Tartarus"), ("Renis", "Erinys"), ("Lerinis", "Erinys")]
                                               + [("Toul", "Thule")] * 5), edits)

    @unittest.skipUnless(TOKENIZER.exists(), "Whisper's tokenizer is not on this machine (voice/models)")
    def test_the_words_of_the_languages_are_left_alone(self) -> None:
        changed = {w for w, _ in rewritten(whisper_words())}
        self.assertEqual(changed - ON_PURPOSE, set(), "the glossary rewrites ordinary words now: an alias or a fuzzy name must be narrowed")


# ---------------------------------------------------------------------------------------------------------------- the experiment: the names in play, matched more loosely
_LABIAL = str.maketrans({"b": "v", "f": "v", "w": "v", "p": "v"})


def _loose(heard_key: str, name_key: str, sim_min: float, min_len: int) -> bool:
    """Would a word with this phonetic key be taken for the name, if the name is one in play? Looser than the glossary: shorter names, the first sound in the same labial class
    (Phlegethon, Plegeton), the name with one vowel more (Solm, solmo), a lost first vowel."""
    k, n = heard_key, name_key
    if len(k) < min_len or len(n) < min_len or abs(len(k) - len(n)) > 2:
        return False
    if n[0] in "aeiou" and k == n[1:]:
        return True
    if k[0].translate(_LABIAL) != n[0].translate(_LABIAL):
        return False
    if k.startswith(n) and len(k) - len(n) == 1 and k[-1] in "aeiou":
        return True
    return _sim(k, n) >= sim_min


IN_PLAY = ["Acheron", "Styx", "Cocytus", "Phlegethon", "Lethe", "Nyx", "Tartarus", "Hypnos", "Thanatos", "Erinys", "Moros", "Keres", "Charon", "Persephone", "Erebus", "Niflheim",
           "Thule", "Aurelia", "Cassia", "Ophir", "Nemet", "Solm", "Rourke", "Skarn", "Hale", "Kestrel", "Marchetti", "Dalca", "Alexiou", "Adeyemi", "Kessler", "Marchand", "Volkov",
           "Pereira", "Haddad", "Lindgren", "Nwosu", "Vega", "Sato", "Menon", "Castellan", "Aldana", "Lindqvist", "Okonkwo", "Mensah"]


def scene_experiment(sim_min: float, min_len: int, lexicon: set[str]) -> tuple[int, int, list[str]]:
    """(real mistakes recovered of FIXED + NOT_FIXABLE, ordinary words of the lexicon taken for a name in play, a few examples)."""
    names = {n: phon(n) for n in IN_PLAY}
    got = sum(_loose(phon(h), phon(n), sim_min, min_len) for h, n in FIXED + NOT_FIXABLE)
    by_len: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for w in lexicon:
        k = phon(w)
        if len(k) >= 4:
            by_len[len(k)].append((w, k))
    taken: list[tuple[str, str]] = []
    for name, nk in names.items():
        for length in range(max(len(nk) - 2, 3), len(nk) + 3):
            for w, k in by_len.get(length, ()):
                if _fold(w) != _fold(name) and _loose(k, nk, sim_min, min_len):
                    taken.append((w, name))
    return got, len(taken), [f"{w} -> {n}" for w, n in sorted(taken)[:: max(1, len(taken) // 8)][:8]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true", help="what the glossary does to the words of the languages")
    ap.add_argument("--scene", action="store_true", help="what a looser match for the names in play would take from them")
    args = ap.parse_args()
    lex = {"whisper": whisper_words() if TOKENIZER.exists() else set(), "docs": docs_words(), "english": english_words()}
    lex = {k: v for k, v in lex.items() if v}
    if args.audit:
        for name, words in lex.items():
            r = rewritten(words)
            print(f"[{name}] {len(words)} words, {len(r)} rewritten: " + ", ".join(f"{w} -> {n}" for w, n in r[:40]))
    if args.scene:
        real = len(FIXED) + len(NOT_FIXABLE)
        for sim_min, min_len in ((0.80, 5), (0.75, 4), (0.70, 4)):
            print(f"\nlooser match for the {len(IN_PLAY)} names in play: similarity >= {sim_min}, keys of {min_len}+ letters")
            for name, words in lex.items():
                got, taken, ex = scene_experiment(sim_min, min_len, words)
                print(f"  [{name}] real mistakes recovered {got}/{real}; ordinary words taken for a name: {taken}  e.g. {'; '.join(ex)}")
    return 0


if __name__ == "__main__":
    if any(a in ("--audit", "--scene") for a in sys.argv[1:]):
        sys.exit(main())
    unittest.main()
