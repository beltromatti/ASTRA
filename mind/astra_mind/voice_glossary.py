"""The game's proper nouns for the speech recogniser: a prompt for the recognisers that take one (Whisper) and a
post-correction for the ones that do not (Parakeet), so "Pretoriano" comes out as "Praetorian" and "Flegetonte" as
"Phlegethon" whatever the backend.

The correction is deliberately conservative. Long, distinctive names are matched by a fuzzy phonetic key; short or
common-word names (Serra, Ferri, Price, Nair, Voss: "serra" is Italian for greenhouse, "price" English for cost) are only
fixed through an explicit alias list or when they differ from the canonical name by capitalisation alone. A wrong
"correction" would put a name in the Captain's mouth that he never said; a missed one costs nothing, the crew's
language model reads the roster anyway."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

log = logging.getLogger("astra.glossary")


@dataclass
class Term:
    text: str                                   # canonical spelling as the game writes it
    aliases: tuple[str, ...] = ()               # spellings a recogniser produces for it (any language)
    fuzzy: bool = True                          # allow phonetic near-matches (long distinctive names only)
    key: str = ""                               # phonetic key of the canonical text
    n_words: int = 1


# canonical term -> (aliases, fuzzy allowed). Aliases were collected from the recognisers' real mistakes on the game's
# own sentences (docs/bench/voce_2026-09-30.md) and from how the names are written in the supported languages.
_TERMS: list[tuple[str, tuple[str, ...], bool]] = [
    # ships
    ("Praetorian", ("pretoria", "pretoriano", "pretoriana", "pretorian", "praetoria", "pretorien", "pretoriaan", "praetorien",
                    "pretoriane", "pretorio", "pretori"), True),
    ("Vigilant", ("vigilante", "vigilent", "vigilanta", "vigilanz"), True),
    ("Acheron", ("acheronte", "achéron", "akeron", "acheronte", "acaron", "aqueronte", "acheronta"), True),
    ("Styx", ("stix", "stige", "sticks", "stics", "stics", "stigs", "stiks", "estige", "styxe"), False),
    ("Lethe", ("lete", "leti", "lethe", "letè", "lethé", "leth", "lithe", "letá"), False),
    ("Cocytus", ("cocito", "cocitus", "kokitus", "cocytos", "cocytus", "cocyte", "cócito", "kokytus", "cocidus"), True),
    ("Phlegethon", ("flegetonte", "flegeton", "phlegeton", "fleghetonte", "phlegethont", "flegetón", "flegeton", "flagiton",
                    "phlegetont"), True),
    ("Aquila", (), False),
    ("Charon", (), False),
    ("Persephone", ("persefone", "perséfone", "persefoon", "persefon"), True),
    ("Brightwater", ("bright water", "brightwoter", "braitwater"), True),
    ("Tenacity", (), False),
    # places and organisations
    ("Aurelia", ("aurelia", "aurelja"), False),
    ("New Ravenna", ("nuova ravenna", "new raven", "nueva ravenna", "nouvelle ravenne", "neue ravenna", "nova ravenna"), True),
    ("Port Aurelius", ("porto aurelius", "port aurelio", "porto aurelio", "puerto aurelius", "port aurélius"), True),
    ("Janus Gate", ("giano gate", "janus", "yanus gate", "porta di giano", "janus gait", "janus geit", "giano"), True),
    ("Keeper Station", ("kipper station", "stazione keeper"), True),
    ("Kharon Mandate", ("caron mandate", "charon mandate", "kharon mandato", "karon mandate"), True),
    ("Teal Veil", ("teal vail", "tiel veil"), True),
    ("Ceres Belt", ("cerere belt", "ceres belt", "cintura di cerere"), True),
    ("Tiberius", ("tiberio",), False),
    ("Vulcan", (), False),
    ("Cassia", (), False),
    ("Meridian", (), False),
    ("Concordia", (), False),
    ("Thule", ("tule", "tulle", "thoule"), False),
    ("Erebus", ("erebo", "erebus"), False),
    ("Niflheim", ("nifelheim", "niflheim", "niffleim"), True),
    ("Ophir", ("ofir", "ophir"), False),
    ("Asphodel", ("asfodelo", "asphodel", "asfodel"), True),
    ("Halcyon", ("alcione", "halcyon"), False),
    ("Sabel", (), False),
    ("Nemet", (), False),
    # people
    ("Okonkwo", ("okonko", "okonkwo", "okonkvo", "okonquo", "okonkuo", "okonco", "ocoyo", "okonkwa"), True),
    ("Lindqvist", ("lindquist", "lindkvist", "lindqvist", "lindkwist", "lindquest", "lindqvis", "lindquis"), True),
    ("Mensah", ("menza", "mensha", "menzah"), False),
    ("Tanaka", (), False),
    ("Voss", ("vos", "foss", "fos"), False),
    ("Nair", ("nayer", "naïr", "nayr"), False),
    ("Kovac", ("kovach", "kovacs", "kovak", "covac"), False),
    ("Rourke", ("rourk", "rork", "roark", "rurk", "rurke"), False),
    ("Varek Solm", ("varec solm", "varek sol", "varec sol", "warek solm"), True),
    ("Solm", ("salm", "sholm"), False),
    ("Marrow", (), False),
    ("Halvorsen", ("halvorson", "alvorsen"), True),
    ("Okafor", (), False),
    ("Vance", (), False),
    ("Wren", (), False),
    # the ships' vocabulary
    ("railgun", ("rail gun", "rail-gun", "railgan", "reilgan", "rail gan"), False),
    ("VLS", ("v l s", "v.l.s.", "vi elle esse"), False),
    ("EMCON", ("e m con", "e-mcon", "emcom", "e mcon", "em con", "emkon"), False),
    ("point defense", ("point defence",), False),
    ("Falcon", (), False),
    ("Hammer", (), False),
    ("Wasp", ("vasp", "vospe"), False),
    ("Harpy", (), False),
]

_PLAIN = re.compile(r"[^\W\d_]+", re.UNICODE)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def phon(s: str) -> str:
    """A rough cross-language sound key: accents off, look-alike spellings merged (ph/f, k/c/ck/q, w/v, y/i, z/s), h and
    doubled letters dropped. Good enough to tell a misheard name from a different word."""
    s = _fold(s)
    s = re.sub(r"[^a-z]", "", s)
    for a, b in (("ph", "f"), ("th", "t"), ("ch", "k"), ("kh", "k"), ("sch", "s"), ("qu", "k"), ("ck", "k"), ("x", "ks"),
                 ("gh", "g"), ("ae", "e"), ("oe", "e")):
        s = s.replace(a, b)
    s = s.translate(str.maketrans({"c": "k", "q": "k", "w": "v", "y": "i", "z": "s", "j": "i", "h": ""}))
    s = re.sub(r"(.)\1+", r"\1", s)
    return s


def _lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _sim(a: str, b: str) -> float:
    m = max(len(a), len(b))
    return 1.0 - _lev(a, b) / m if m else 1.0


class Glossary:
    """The names, the prompt and the correction."""

    def __init__(self) -> None:
        self.terms: list[Term] = []
        self._alias: dict[str, Term] = {}
        for text, aliases, fuzzy in _TERMS:
            self.add(text, aliases, fuzzy)
        self._load_game_names()

    # ------------------------------------------------------------------------------------------ building
    def add(self, text: str, aliases: tuple[str, ...] = (), fuzzy: bool = True) -> None:
        t = Term(text=text, aliases=tuple(aliases), fuzzy=fuzzy and len(phon(text)) >= 6, key=phon(text), n_words=len(text.split()))
        self.terms.append(t)
        self._alias[_fold(text)] = t
        for a in aliases:
            self._alias.setdefault(_fold(a), t)

    def _load_game_names(self) -> None:
        """Names the game already knows (crew, Mandate commanders, the sector map): kept in step with them."""
        have = {_fold(t.text) for t in self.terms}
        try:
            from .crew import CREW
            for o in CREW.values():
                if _fold(o.name.split()[-1]) not in have:
                    self.add(o.name.split()[-1], (), fuzzy=False)
                    have.add(_fold(o.name.split()[-1]))
        except Exception:  # noqa: BLE001
            pass
        try:
            from .enemy import COMMANDERS
            for c in COMMANDERS.values():
                surname = c["name"].split()[-1]
                if _fold(surname) not in have:
                    self.add(surname, (), fuzzy=False)
                    have.add(_fold(surname))
        except Exception:  # noqa: BLE001
            pass
        try:
            from .war import SECTOR
            for s in SECTOR:
                for n in (s["name"], s["world"]):
                    if _fold(n) not in have:
                        self.add(n, (), fuzzy=False)
                        have.add(_fold(n))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------------------------------ prompt
    def prompt(self, limit: int = 420) -> str:
        """A comma-separated list of the names, for recognisers that take a prompt (Whisper)."""
        out, n = [], 0
        for t in self.terms:
            if n + len(t.text) + 2 > limit:
                break
            out.append(t.text)
            n += len(t.text) + 2
        return ", ".join(out) + "."

    # ------------------------------------------------------------------------------------------ correction
    def correct(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """(corrected text, [(heard, replaced by)]). Windows of up to three words are tried longest first."""
        words = [(m.start(), m.end(), m.group()) for m in _PLAIN.finditer(text)]
        if not words:
            return text, []
        edits: list[tuple[int, int, str, str]] = []
        i = 0
        while i < len(words):
            done = False
            for n in (3, 2, 1):
                if i + n > len(words):
                    continue
                span = words[i:i + n]
                # words separated by anything but spaces (a comma, a full stop) are not one name
                if any(re.search(r"[^\s'’\-]", text[span[k][1]:span[k + 1][0]]) for k in range(n - 1)):
                    continue
                heard = text[span[0][0]:span[-1][1]]
                term = self._match(heard, n)
                if term is not None:
                    if heard != term.text:
                        edits.append((span[0][0], span[-1][1], heard, term.text))
                    i += n
                    done = True
                    break
            if not done:
                i += 1
        if not edits:
            return text, []
        out, last = [], 0
        for a, b, _, new in edits:
            out.append(text[last:a])
            out.append(new)
            last = b
        out.append(text[last:])
        return "".join(out), [(h, n) for _, _, h, n in edits]

    def _match(self, heard: str, n_words: int = 1) -> Term | None:
        f = _fold(heard)
        t = self._alias.get(f)
        if t is not None:
            # a common word that is also a short name ("serra", "price") is not capitalised: only a real mishearing is fixed
            if not t.fuzzy and t.n_words == 1 and f == _fold(t.text):
                return None
            return t
        f = re.sub(r"[\s'’\-]+", " ", f).strip()
        t = self._alias.get(f)
        if t is not None:
            return t
        k = phon(heard)
        if len(k) < 6:
            return None
        best, best_sim = None, 0.0
        for cand in self.terms:
            # a near-match must have as many words as the name (else "Janus gate to" would swallow the "to")
            if not cand.fuzzy or cand.n_words != n_words or abs(len(cand.key) - len(k)) > 2:
                continue
            s = _sim(k, cand.key)
            if s > best_sim:
                best, best_sim = cand, s
        # long names tolerate one slip in six letters or so; the first sound must agree
        if best is not None and best_sim >= 0.80 and best.key[0] == k[0]:
            return best
        return None


GLOSSARY = Glossary()
