"""Whom is the Captain talking to?

On the bridge everyone hears the Captain, as they would in the room: the words go to the crew, and the crew's agent sorts out
who answers. What this module decides is the rare, costly case — the Captain has a channel open with someone outside
(an enemy commander, the admiral, an allied ship): which of his words go out on it? Only what is clearly meant for the party:
named or ranked, a demand, a threat, an offer, a question put to them, the reply in an exchange that is going on. Everything
else — orders, questions about the ship, a word to an officer — stays aboard, and when it is unclear it stays aboard too
(comms can offer to relay). The playtest's lesson: "rapporto armamenti" and "ci sono navi nemiche" went to the enemy captain.

The decision is layered, cheapest first, and meant to add no wait on the Captain:
  1. no live channel (none, closed, muted): nothing to decide, everything is for the bridge; an officer addressed by name or
     the person the Captain is facing is noted as the one to answer first (0 ms);
  2. rules over the words and the room (`decide`): vocatives, speech acts of a demand or an offer, the vocabulary of the ship's
     own systems, whom the Captain faces, whether the party has just spoken — in Italian, English, Spanish, French and German,
     typed with typos or spoken as the recogniser writes (~0.03 ms);
  3. only if the rules cannot settle it: one small model (`route_llm`), whose answer the server may wait for while the crew
     turn is already under way (nothing is said or done before the answer, so a wrong start costs nothing).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .context import BRIDGE, Context
from .models import chat as role_chat
from .openrouter import OpenRouter

log = logging.getLogger("astra.router")


# ================================================================================================ the result
@dataclass
class Route:
    crew: str = ""                       # the words for the bridge, verbatim ("" = nothing)
    external: str = ""                   # the words that go out on the channel ("" = nothing)
    party: str = ""                      # the channel party the external words are for
    addressed: tuple[str, ...] = ()      # officers addressed by name or role (or the one the Captain faces): they answer first
    npc: str = ""                        # a person in the room the Captain is talking to (speaker id)
    how: str = ""                        # no_channel | rules | llm | fallback
    unsure: bool = False                 # crew, but the party may have been meant: comms can offer to relay
    ms: float = 0.0

    @property
    def enemy(self) -> str:              # (the name the old server code used)
        return self.external

    @property
    def dest(self) -> str:
        return "both" if (self.crew and self.external) else "external" if self.external else "crew"


# ================================================================================================ the words
def norm(text: str) -> str:
    """Lower case, no accents, straight apostrophes: what the rules read (typed text has no accents anyway)."""
    t = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[’`´]", "'", t)


def _alt(*stems: str) -> str:
    return "|".join(stems)


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


# the bridge officers by name or role (it/en/es/fr/de)
_OFFICER_STEMS = {
    "xo": _alt("serra", "primo ufficiale", "numero uno", "number one", "xo", "executive officer", "primer oficial", "premier officier",
               "erster offizier", "commander serra", "comandante serra"),
    "helm": _alt("ferri", "timonier\\w*", "timone", "helm\\w*", "timonel", "steuermann", "steuer"),
    "ops": _alt("tanaka", "operazion\\w*", "ops", "operations", "operaciones", "operationsoffizier", "operationen"),
    "tactical": _alt("voss", "tattic\\w*", "tactical", "tactic\\w*", "tactique", "taktik\\w*", "weapons officer"),
    "comms": _alt("martin", "comunicazion\\w*", "comms?", "communications?", "comunicaciones", "transmissions", "kommunikation\\w*",
                  "funk\\w*"),
    "sensors": _alt("nair", "sensori", "sensors?", "sensores", "capteurs", "sensoren", "scienze", "science officer", "astrometri\\w*"),
    "engineering": _alt("mensah", "okonkwo", "ingegner\\w*", "macchine", "engineering", "engineer", "ingenieria", "ingeniero",
                        "ingenieur", "ingenierie", "maschinenraum", "chief"),
    "flight": _alt("price", "kovac", "controllo di volo", "flight control", "flight", "control de vuelo", "controle de vol",
                   "flugkontrolle", "cag"),
    "doctor": _alt("lindqvist", "dottor\\w*", "doctor", "doc", "medico", "docteur", "arzt", "doktor"),
}
_GROUP = _alt("plancia", "bridge", "puente", "passerelle", "bruecke", "equipaggio", "crew", "tripulacion", "equipage", "besatzung",
              "ufficiali", "officers", "secondo ufficiale", "all hands", "everyone", "everybody", "signori", "gentlemen", "ladies and gentlemen",
              "senores", "messieurs", "meine herren", "todos", "tous", "alle")
_OFFICER_RX = {k: _rx(r"\b(?:" + v + r")\b") for k, v in _OFFICER_STEMS.items()}
_OFFICER_ALL = "|".join(_OFFICER_STEMS.values()) + "|" + _GROUP
_TITLES = r"(?:mister |mr\.? |signor |signora |tenente |ufficiale |lieutenant |lt\.? |ensign |mister )?"
_OFFICER_VOC = _rx(r"(?:^|[,:;]\s*|[.!?]\s+)" + _TITLES + r"(?:" + _OFFICER_ALL + r")\b\s*[,:;]?")
# words that make a name an object ("on the Cocytus", "l'ammiraglio"), not a vocative
_OBJECT_BEFORE = {"il", "lo", "la", "l'", "i", "gli", "le", "al", "allo", "alla", "all'", "ai", "agli", "alle", "del", "dello", "della",
                  "dell'", "dei", "degli", "delle", "sul", "sullo", "sulla", "sull'", "sui", "sugli", "sulle", "dal", "dallo", "dalla",
                  "dall'", "col", "coi", "nel", "nello", "nella", "nell'", "da", "di", "a", "su", "per", "con", "contro", "verso", "tra",
                  "fra", "the", "to", "of", "on", "at", "for", "against", "toward", "towards", "from", "by", "near", "after", "el", "los",
                  "las", "al", "del", "sobre", "contra", "hacia", "para", "por", "au", "aux", "du", "des", "sur", "contre", "vers",
                  "der", "die", "das", "dem", "den", "des", "auf", "gegen", "zu", "zum", "zur", "von", "nach", "bei", "an", "l"}

# people and ships outside: the enemy's captains and ships, the fleet
_PERSONS = _alt("archon", "solm", "varek", "kade", "doran", "vael", "irina", "quill", "hale", "ferryman\\w*", "warden", "oarsman",
                "ammiragli\\w*", "admiral", "amiral", "almirante", "rourke")
_SHIPS = _alt("acheron", "styx", "lethe", "cocytus", "cocito", "phlegethon", "avernus", "praetorian", "vigilant", "brightwater", "resolve")
_RANKS = _alt("comandante", "commander", "commandant", "kommandant", "capitano nemico", "enemy commander", "comandante nemico",
              "comandante enemigo")
_PARTY_NAMES = _PERSONS + "|" + _SHIPS + "|kharon|fleet command|comando flotta|settima flotta|7th fleet"
_LEAD = (r"(?:il |la |l'|lo |the |le |el |der |die |das |ehi |hey |eh |oye |attenzione |attention |achtung |capitan\w* |capitaine |"
         r"kapitaen |captain |ferryman |commander |comandante |commandant |kommandant )?")
_PARTY_VOC = _rx(r"(?:^|[,:;]\s*|[.!?]\s+)" + _LEAD + r"(?:" + _PARTY_NAMES + "|" + _RANKS + r")\b\s*[,:;]?")
_TITLE_ANY = _rx(r"\b(?:ferryman|archon|warden|ammiragli\w*|admiral|amiral|almirante|comandante|commander|commandant|kommandant|"
                 r"capitano nemico|enemy commander)\b")
_PARTY_END = _rx(r"(?:^|\s)(?:" + _PERSONS + "|" + _RANKS + r")\s*[.!?]*$")
_RANKISH = _rx(r"^(?:l'|il|la|lo|the|le|el|der|die|das|mister|signor|capitano|captain|capitan|capitaine|kapitaen|comandante|commander|"
               r"ammiraglio|admiral|amiral|almirante|ferryman|archon|warden|vice|l'ammiraglio|l'archon|dell'ammiraglio)$")
_PARTY_ANY = _rx(r"\b(?:" + _PARTY_NAMES + r")\b")

# who the Captain says he is, when he speaks to someone outside
_SELF_ID = _rx(r"\b(?:qui (?:il capitano|l'aquila|aquila|e il capitano|e l'aquila)|sono il capitano|questo e il capitano|"
               r"this is (?:the )?(?:captain|aquila|asn aquila)|i am (?:the )?captain|i'm (?:the )?captain|"
               r"here is (?:the )?captain|aqui (?:el )?(?:capitan|aquila)|soy el capitan|habla el capitan|"
               r"ici (?:le )?(?:capitaine|aquila|l'aquila)|je suis le capitaine|"
               r"hier (?:ist|spricht) (?:der )?(?:kapitaen|kapitan|aquila)|ich bin der kapitaen|"
               r"(?:capitano|captain|capitan|capitaine|kapitaen|kapitan) (?:dell'|of the |of |de l'|del |der |de la |d')\s*(?:asn )?aquila)\b")

# what is said TO them, certainly: demands, threats, offers, questions put in the second person
_EXT_STRONG = _rx(r"\b(?:"
                  # Italian
                  r"arrend\w*|arrender\w*|la vostra resa|accetto la (?:vostra )?resa|ritirat(?:evi|e vi)|ritirarvi|fermatevi|fermarvi|"
                  r"abbassate le armi|deponete le armi|disattivate le armi|identificatevi|chi siete|chi vi ha|"
                  r"cosa volete|che cosa volete|che volete|che intenzioni avete|perche (?:ci )?attacc\w*|perche siete|dove siete diretti|"
                  r"(?:vi|ti) (?:do|offro|concedo|ordino|intimo|avverto|consiglio|conviene|distrugg\w*|annient\w*|affond\w*)|"
                  r"verrete|vi (?:distruggeremo|annienteremo|affonderemo)|o vi |altrimenti vi |"
                  r"avete (?:un|due|tre|cinque|dieci|venti|trenta|sessanta|\d+) (?:minut|second|or)\w*|"
                  r"lasciateci (?:passare|andare)|non siamo qui per|non voglio combattere|non vogliamo combattere|"
                  r"non ho intenzione di cedere|non cedero|non ci arrenderemo|"
                  r"trattare con|trattativa|negoziare|negoziamo|tregua|cessate il fuoco o|fermate il fuoco o|"
                  r"vostr[aeoi] (?:offerta|condizioni|richiest\w*|proposta|resa|nave|navi|flotta|comandante|equipaggi\w*|ritirata)|"
                  r"le vostre condizioni|ultimo avvertimento|ultima (?:possibilita|occasione|chance)|"
                  r"o (?:apro|apriamo|spariamo|sparo) |altrimenti (?:apro|apriamo|spar\w*)|chi sei|come ti chiami|"
                  r"prepar\w+ (?:all'|al |per l')abbordaggio|se vi (?:ritirate|arrendete|fermate|allontanate)|"
                  # English
                  r"last (?:warning|chance)|final (?:warning|chance)|walk away|prepare (?:to be|for) (?:boarded|boarding)|"
                  r"or (?:we|i) (?:open|fire|shoot)|if you (?:stand|withdraw|surrender|leave|retreat|turn|stop|lower|cut)|"
                  r"surrender|stand down|power down|lower your (?:weapons|shields)|drop your (?:weapons|shields)|"
                  r"withdraw from|withdraw immediately|withdraw now|withdraw\.?$|retreat now|identify yourselves?|who are you|who sent you|"
                  r"what do you want|why are you (?:attacking|here)|where are you (?:going|headed)|"
                  r"we will (?:destroy|kill|sink|open fire|fire on|annihilate)|or we will|or i will|will be destroyed|"
                  r"you have (?:\w+ )?(?:minutes?|seconds?|hours?)|i (?:offer|propose|demand|order you|warn you)|"
                  r"listen to me|hear me out|talk to me|i am willing to|i'm willing to|"
                  r"cease fire or|hold your fire or|"
                  r"(?:your|their) (?:offer|terms|conditions|demands?|proposal|crews?|commander)|"
                  r"tell me your (?:terms|name)|what.s your (?:name|position|intent)|"
                  # Spanish
                  r"rindan\w*|rendios|retiren\w*|retirense|bajen las armas|baje(?:n)? (?:las armas|los escudos)|identifiquen\w*|"
                  r"quienes son|que quieren|por que (?:nos )?atacan|"
                  r"tienen (?:un|dos|tres|cinco|diez|veinte|treinta|sesenta|\d+) (?:minutos?|segundos?)|"
                  r"les (?:ofrezco|ordeno|advierto)|no aceptamos|sus condiciones|su oferta|"
                  r"les (?:daremos|ofrecemos|damos|dejamos|doy|concedo|garantizo)|ultima (?:oportunidad|advertencia)|"
                  # French
                  r"rendez(?:-| )vous|retirez(?:-| )vous|baissez (?:vos armes|vos boucliers)|identifiez(?:-| )vous|qui etes(?:-| )vous|"
                  r"que voulez(?:-| )vous|pourquoi (?:nous )?attaquez|vous avez (?:une|deux|trois|cinq|dix|\d+) (?:minutes?|secondes?)|"
                  r"je vous (?:offre|ordonne|previens|donne)|nous n'acceptons|vos conditions|votre offre|"
                  r"nous vous (?:laissons|donnons|offrons|accordons|ordonnons|avertissons)|derniere (?:chance|sommation)|"
                  # German
                  r"ergebt euch|ergeben sie sich|zieht euch|ziehen sie sich|senkt (?:eure|die) (?:waffen|schilde)|identifiziert euch|"
                  r"wer seid ihr|was wollt ihr|warum greift ihr|ihr habt (?:eine|zwei|drei|\d+) (?:minuten?|sekunden?)|"
                  r"sie haben (?:eine|zwei|drei|\d+) (?:minuten?|sekunden?)|ich biete|ich befehle|"
                  r"wir akzeptieren (?:ihre|eure)|ihre bedingungen|eure bedingungen|ihr angebot|euer angebot|"
                  r"wir geben (?:euch|ihnen)|letzte (?:warnung|chance)"
                  r")")
# what points at them without settling it alone: do you hear me, my word, in the second person (a person or the crew could be meant)
_EXT_MED = _rx(r"(?:^|\s)(?:"
               r"(?:mi|ci) (?:ascolt\w*|sent\w*)|ci stia a sentire|mi ascolti|ascolta(?:te|mi)?|senti(?:te)?|la mia parola|ritirate|avete la|"
               r"\w+tevi|\w+(?:ar|er|ir|rr)vi|vi \w{3,}|non (?:vi|ci) credo|state (?:indietro|mentendo)|"
               r"pensaci|pensateci|rispondi(?:te)?|che garanzie|"
               r"do you (?:hear|copy|read) me|can you hear me|are you (?:still )?(?:receiving|there|listening|alive)|my word|negotiat\w*|pirate|ceasefire|cease-fire|truce|"
               r"you (?:will|are|have|must|can|should|cannot|can't|won't|would|do not|don't)|your (?:engines?|weapons?|shields?|ships?|fleet|"
               r"crews?|reactors?|drives?|guns|last|terms)|i can end|"
               r"me (?:escuchan|oyen|escucha|oye)|oigan|escuchen|mi palabra|deteng\w+|cesen (?:el )?fuego|no confio en|"
               r"ecoutez(?:-moi)?|vous nous (?:entendez|recevez)|ma parole|cessez le feu|je (?:ne )?vous (?:\w+ )?(?:pas )?(?:fais|dis|donne|offre)|"
               r"hoert (?:mir )?zu|hoeren sie|hoert ihr mich|hoeren sie mich|mein wort|ich vertraue (?:ihnen|euch)|stellen sie das feuer ein|"
               r"stellt das feuer ein"
               r")")
# a weak sign of a second person ("you", "voi"): a nudge only — the crew is addressed in the second person too
_EXT_WEAK = _rx(r"(?:^|\s)(?:voi|vi|ustedes|vosotros|vous|ihr|euch|you|your|yours|vostr\w*|vuestr\w*|votre|vos|eure\w*|ihre\w*)\b")
# a reply in a conversation (counts only while the party has just spoken)
_REPLY = _rx(r"^(?:no|si|mai|forse|va bene|ok|d'accordo|certo|come|cosa|perche|quando|dove|quanto tempo|ripeta|ripeti|aspetti|aspettate|"
             r"sentito|capito|chiaro|accetto|rifiuto|ho capito|"
             r"yes|yeah|sure|never|maybe|fine|all right|alright|agreed|why|what|when|where|how long|repeat that|wait|stand by|understood|"
             r"i accept|i agree|i refuse|i understand|go on|and if|"
             r"nunca|quiza|de acuerdo|por que|que|cuando|donde|acepto|entendido|oui|non|jamais|d'accord|pourquoi|quoi|quand|j'accepte|"
             r"je refuse|ja|nein|niemals|vielleicht|einverstanden|warum|was|wann|wo|ich akzeptiere|ich verstehe)\b")

# the vocabulary of the ship's own systems and of orders and questions to the bridge (stems, matched at word starts)
_CREW_STEMS = (
    # Italian
    "fuoc", "spar", "missil", "silur", "railgun", "cannon", "laser", "scud", "allarm", "rott", "virar", "virat", "vira", "timon", "veloc",
    "manett", "motor", "intercett", "insegu", "segui", "avvicin", "allontan", "distanz", "portata", "raggio", "bersagl", "contatt", "nave",
    "navi", "squadrigli", "cacci", "decoll", "lanci", "richiam", "dann", "ponte", "energi", "potenz", "calore", "radiator", "sensor",
    "scansion", "scan", "schermo", "olotavol", "tavolo", "datapad", "rapporto", "situazione", "stato", "armi", "arma", "armament", "munizion",
    "plancia", "flott", "alleat", "nemic", "hangar", "infermeria", "scafo", "reattor", "rotta", "scapp", "fuga", "ritirata",
    "pattuglia", "decoy", "esche", "chaff", "difesa", "puntament", "puntal", "punta", "mirino", "salva", "inquadr", "zoom", "ingrandi",
    "mostra", "codice", "sirena", "canale", "mercantil", "ricognizion", "droni", "drone", "torpedin", "bordata", "fianco", "gate", "transit",
    "orbita", "spegn", "accend", "alza", "abbassa", "attiva", "disattiva", "blocca", "sigilla", "evacua", "abbandon", "tienil", "tienici",
    "mantien", "teletrasport", "lontan", "portaci", "portami", "silenzio", "elettronic", "emcon", "vedere a schermo", "a schermo",
    "mand", "invia", "abbordagg", "impatto", "sweep", "brace", "impact",
    # English
    "fire", "shoot", "missile", "torpedo", "cannon", "shield", "alert", "course", "heading", "turn ", "come about", "speed", "throttle",
    "engine", "intercept", "chase", "follow", "close in", "range", "target", "contact", "ship", "vessel", "squadron", "fighter", "launch",
    "recall", "damage", "deck", "power", "heat", "sensor", "scan", "screen", "holo", "report", "status", "weapon", "ammo", "bridge",
    "fleet", "allied", "hostile", "enemy", "hangar", "sickbay", "hull", "reactor", "patrol", "point defen", "salvo", "volley", "show me",
    "how many", "how far", "how fast", "what's our", "whats our", "are we", "do we have", "can we", "left", "remaining", "hold fire",
    "weapons", "on screen", "on the screen", "evade", "pursue", "engage", "lock", "arm ", "cut the", "all stop", "full ahead", "full speed",
    "red alert", "yellow alert", "battle stations", "send a", "ping", "silent", "go dark",
    # Spanish
    "fuego", "dispar", "misil", "escudo", "alerta", "rumbo", "velocidad", "motores", "persig", "objetivo", "contacto", "nave", "cazas",
    "lanz", "informe", "estado", "armas", "puente", "flota", "aliad", "enemig", "casco", "cuant", "distancia", "muestr",
    "pantalla", "energia", "calor", "sensores", "escaner", "danos",
    # French
    "feu ", "feu a", "tirez", "torpille", "bouclier", "alerte", "cap ", "vitesse", "moteurs", "interceptez", "poursuiv", "cible", "navire",
    "chasseurs", "lancez", "rapport", "etat", "armes", "passerelle", "flotte", "alli", "ennemi", "coque", "reacteur", "combien",
    "distance", "montrez", "ecran", "energie", "chaleur", "capteurs", "degats",
    # German
    "feuer", "schiess", "rakete", "schild", "alarm", "kurs", "geschwindigkeit", "triebwerk", "abfang", "verfolg", "ziel", "kontakt",
    "schiff", "jaeger", "startet", "bericht", "waffen", "bruecke", "flotte", "verbuendet", "feind", "rumpf", "reaktor",
    "wie viele", "wie weit", "wie schnell", "entfernt", "zeigt", "bildschirm", "hitze", "sensoren", "schaden",
)
_CREW_RX = _rx(r"(?:^|\s)(?:" + "|".join(re.escape(s).replace(r"\ ", " ") for s in _CREW_STEMS) + r")")

# "mandate" is an order ("send") far more often than the Kharon Mandate: never a party by itself
_SPLIT_RX = re.compile(r"(?<=[.!?;])\s+|\n+")


# ================================================================================================ the rules
@dataclass
class Score:
    ext: float = 0.0                     # the evidence that the words are for the party ...
    soft: float = 0.0                    # ... of which this much only points that way ("do you hear me", "you") and settles nothing alone
    crew: float = 0.0
    officers: tuple[str, ...] = ()
    why: list[str] = field(default_factory=list)


def _officers_in(t: str, vocative_only: bool) -> tuple[str, ...]:
    found = []
    for oid, rx in _OFFICER_RX.items():
        for m in rx.finditer(t):
            if not vocative_only or _is_vocative(t, m.start(), m.end()):
                found.append(oid)
                break
    return tuple(dict.fromkeys(found))


def _is_vocative(t: str, start: int, end: int) -> bool:
    """A name is a vocative when it opens the words, closes them, or is set off by punctuation (and is not the object of
    a preposition or an article: "on the Cocytus")."""
    before = t[:start].rstrip()
    after = t[end:].lstrip()
    prev = before.split()[-1] if before.split() else ""
    if prev.rstrip(",:;") != prev:                   # a comma or colon right before
        return True
    if not before or before[-1] in ".!?":
        return True
    if prev in _OBJECT_BEFORE:
        return False
    if not after:                                    # the last word
        return len(before.split()) <= 8
    return after[0] in ",:;" and len(before.split()) <= 2


def _party_vocative(t: str) -> re.Match[str] | None:
    """The party named as one is named when spoken to: at the start of the words, or set off by punctuation; or a person or
    a rank as the last word ("we need support, admiral"). A ship after a verb or a preposition is a target, not a vocative."""
    m = _PARTY_VOC.search(t)
    if m:
        return m
    e = _PARTY_END.search(t)
    if e:
        before = t[:e.start()].split()
        while before and _RANKISH.match(before[-1]):      # "con l'ammiraglio Rourke": the title belongs to the name
            before.pop()
        if not before or before[-1] not in _OBJECT_BEFORE:
            return e
    return None


def score_segment(seg: str, ctx: Context, first: bool, prev_ext: bool = False, prev_crew: bool = False) -> Score:
    """The evidence in one sentence for the crew and for the party (both start at zero)."""
    s = Score()
    t = norm(seg).strip()
    if not t:
        return s
    ch = ctx.channel
    # the bridge: an officer by name or role, as a vocative — strong; anywhere else — a weak sign
    voc_officers = _officers_in(t, True)
    if voc_officers:
        s.crew += 4
        s.officers = voc_officers
        s.why.append("officer vocative " + "/".join(voc_officers))
    elif _officers_in(t, False):
        s.crew += 1
        s.officers = _officers_in(t, False)
    seen = {m.group(0).strip()[:4] for m in _CREW_RX.finditer(re.sub(r"['!?.,;:]", " ", t) + " ")}
    domain = len(seen)
    if domain:
        s.crew += min(3, domain)
        s.why.append(f"ship vocabulary x{domain}")
    if ctx.facing in BRIDGE:
        s.crew += 2
        s.officers = s.officers or (ctx.facing,)
        s.why.append("facing " + ctx.facing)
    if not ch or not ch.open:
        return s
    # the party
    strong = _EXT_STRONG.search(t)
    if strong:
        s.ext += 3
        s.why.append("speech act to them: " + strong.group(0)[:24])
    elif _EXT_MED.search(t):
        s.ext += 2
        s.soft += 2
        s.why.append("points at them")
    if _SELF_ID.search(t):
        s.ext += 3
        s.why.append("says who he is")
    voc = _party_vocative(t)
    if voc:
        # set off by a comma or a colon, or a title at the very start ("ammiraglio, ...", "Ferryman ..."): he is being spoken to;
        # a bare name at the start of typed words may be the subject of a sentence ("vael sta bluffando") and needs more evidence
        spoken_to = (bool(re.search(r"[,:;]\s*$", voc.group(0))) or bool(re.match(r"\s*[,:;]", voc.group(0)))
                     or bool(re.search(r"[,:;]\s*$", t[:voc.start()])) or bool(_TITLE_ANY.search(voc.group(0))))
        s.ext += (3 if spoken_to else 2) if domain < 3 else 2
        s.why.append("party vocative" + ("" if spoken_to else " (bare name)"))
    if _EXT_WEAK.search(t):
        s.ext += 1                                 # "you", "voi", "vos": the words may be for them; a lone ship word is not enough
        s.soft += 1
    if ch.talking and not voc_officers and not prev_crew:
        words = len(t.split())
        if _REPLY.match(t):
            s.ext += 3 if not domain else 2
            s.why.append("reply in the exchange")
        elif not domain and words <= 8:
            s.ext += 3
            s.why.append("short, and they just spoke")
        elif not domain and words <= 14:
            s.ext += 2
            s.why.append("conversational, they just spoke")
    if ctx.facing == "viewscreen" and ch.screen:
        s.ext += 2
    elif ctx.facing == "viewscreen" and ch.talking:
        s.ext += 1
    if prev_ext and not first and not voc_officers:
        s.ext += 3 if domain < 3 else 1
        s.why.append("continues what was said to them")
    elif prev_crew and not first and not strong and not voc and not _SELF_ID.search(t):
        s.crew += 2
        s.why.append("continues what was said to the bridge")
    return s


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for part in _SPLIT_RX.split(text.strip()):
        part = part.strip()
        if not part:
            continue
        # a comma before an officer's vocative starts a new destination ("Archon, you have a minute, tactical, missiles")
        # (only when the officer's name opens a clause with words of its own: a trailing "..., Martin?" is an address, not a split)
        pieces = re.split(r"(?<=,)\s+(?=(?:%s)\b\s*[,:;]?\s+\w+\s+\w+)" % _OFFICER_ALL, part, flags=re.I)
        out.extend(p.strip(" ,") for p in pieces if p.strip(" ,"))
    return out or [text.strip()]


@dataclass
class Decision:
    dest: str                            # crew | external | both | unsure
    crew: str = ""
    external: str = ""
    officers: tuple[str, ...] = ()
    unsure: bool = False
    why: str = ""


def decide(text: str, ctx: Context) -> Decision:
    """The rules (no model): whom the words are for. dest 'unsure' means the rules cannot tell: the model is asked."""
    ch = ctx.channel
    segs = _sentences(text)
    officers: list[str] = []
    dests: list[str] = []
    prev_ext = prev_crew = False
    why = []
    weak_ext = False
    for i, seg in enumerate(segs):
        sc = score_segment(seg, ctx, i == 0, prev_ext, prev_crew)
        officers += list(sc.officers)
        if not ch or not ch.live:
            d = "crew"
        elif sc.ext >= 3 and sc.ext >= sc.crew + 2 and sc.ext - sc.soft >= 2:
            d = "external"
        elif sc.crew >= 1 and sc.ext < 1:
            d = "crew"                               # something of the ship's own, nothing that points outside
        elif sc.crew >= sc.ext - sc.soft + 1.5 and sc.crew >= 3:
            d = "crew"                               # (an officer named, or several ship words: what merely points outside does not count)
        elif sc.crew >= sc.ext + 1.5:
            d = "crew"
        elif sc.ext >= 3 and sc.crew >= 3 and len(segs) == 1:
            d = "unsure"
        elif sc.ext >= 3 and sc.ext - sc.soft >= 2:
            d = "external" if sc.ext > sc.crew else "unsure"
        else:
            d = "unsure"                             # a pointer at the party, or no evidence at all: a model looks at it
            weak_ext = sc.ext >= 1
        dests.append(d)
        prev_ext = d == "external"
        prev_crew = d == "crew" and bool(sc.officers) and any("vocative" in w for w in sc.why)
        why.append(f"[{d}] " + ", ".join(sc.why))
    if "unsure" in dests:
        # a sentence the rules cannot place takes the side of its neighbours when they agree, else the model decides
        known = {d for d in dests if d != "unsure"}
        if len(known) == 1 and len(segs) > 1:
            dests = [next(iter(known)) if d == "unsure" else d for d in dests]
        else:
            return Decision("unsure", officers=tuple(dict.fromkeys(officers)), why=" | ".join(why))
    if len(segs) == 1:
        crew_txt, ext_txt = (text.strip(), "") if dests[0] == "crew" else ("", text.strip())
    else:
        crew_txt = " ".join(s for s, d in zip(segs, dests) if d == "crew")
        ext_txt = " ".join(s for s, d in zip(segs, dests) if d == "external")
    dest = "both" if crew_txt and ext_txt else "external" if ext_txt else "crew"
    return Decision(dest, crew_txt, ext_txt, tuple(dict.fromkeys(officers)), unsure=(dest == "crew" and weak_ext), why=" | ".join(why))


# ================================================================================================ the model, for what the rules leave open
LABEL_PROMPT = """The Captain of a starship is speaking aloud on the bridge and has a radio channel open with {party} ({kind}). Say whom
the Captain's words are for. Reply with ONE word:
crew  - for the bridge crew: orders (also shouted ones, whatever the language), questions about our own ship, weapons, sensors,
        contacts, talk ABOUT the party or "the enemy" in the third person, a word to an officer or to everyone aboard, thinking aloud;
party - for {party} on the channel: a demand, threat, offer, question or reply put TO them, calling them by name, ship or rank, or
        "you" aimed at them;
mixed - part for the crew and part for {party}.
Default to crew: answer party only when the words are plainly said to {party}. {situation}
Examples (in any language): "apri il fuoco a discrezione" crew; "rapporto sullo stato delle armi" crew; "ci sono ancora nemici in
zona?" crew; "Kade sta mentendo, Voss" crew; "Tir !" crew; "Ferri, portaci via. Ferryman, e la vostra ultima offerta" mixed; "voi,
fermatevi subito o apro il fuoco" party; "Ferryman Doran, qui il capitano dell'Aquila" party; "tell me what you want" party; "esto se
acaba aqui" party; "pouvez-vous m'entendre ?" party when they just spoke, else crew."""

SPLIT_PROMPT = """The Captain's words mix an order for the bridge crew and words for {party} on the channel. Split them, verbatim. Reply with
JSON only: {{"crew": "<the part for the crew>", "party": "<the part for {party}>"}}"""


def _situation(ctx: Context) -> str:
    ch = ctx.channel
    out = []
    if ch and ch.kind == "fleet":
        out.append("This channel reaches the admiral and the allied ships: an order or a request put to any of them is for the party.")
    if ch and ch.talking:
        out.append(f"{ch.name or ch.party} spoke to the Captain {ch.heard_s:.0f} seconds ago, so a short reply may be for them.")
    elif ch:
        out.append(f"{ch.name or ch.party} has been silent for a while.")
    if ctx.facing:
        out.append(f"The Captain is looking at: {ctx.facing}.")
    return " ".join(out)


def parse_label(content: str) -> str | None:
    """crew | party | mixed from a model's reply (the first of the three words in it)."""
    m = re.search(r"\b(crew|party|mixed)\b", content.strip().lower())
    return m.group(1) if m else None


async def classify(llm: OpenRouter, text: str, ctx: Context, **over: Any) -> tuple[str | None, float, float]:
    """(label, seconds, dollars): one word from the small model — crew | party | mixed (None: no usable answer)."""
    ch = ctx.channel
    t0 = time.perf_counter()
    system = LABEL_PROMPT.format(party=(ch.name or ch.party) if ch else "the party", kind=ch.kind if ch else "enemy",
                                 situation=_situation(ctx))
    try:
        comp = await role_chat(llm, "router", messages=[{"role": "system", "content": system}, {"role": "user", "content": text}], **over)
    except Exception:  # noqa: BLE001
        log.exception("router model failed")
        return None, time.perf_counter() - t0, 0.0
    if comp.error:
        log.warning("router model error: %s", comp.error[:120])
        return None, time.perf_counter() - t0, comp.cost
    return parse_label(comp.content), time.perf_counter() - t0, comp.cost


async def route_llm(llm: OpenRouter, text: str, ctx: Context, hint: str = "") -> Route | None:
    """One small, fast model call for the ambiguous middle. None: no answer (the caller keeps the words on the bridge)."""
    ch = ctx.channel
    if not ch:
        return None
    t0 = time.perf_counter()
    label, _, _ = await classify(llm, text, ctx)
    if label is None:
        return None
    if label == "crew":
        return Route(crew=text.strip(), how="llm", ms=(time.perf_counter() - t0) * 1000)
    if label == "party":
        return Route(external=text.strip(), party=ch.party, how="llm", ms=(time.perf_counter() - t0) * 1000)
    # mixed: the rare case, a second small call splits the words
    try:
        comp = await role_chat(llm, "router", messages=[{"role": "system", "content": SPLIT_PROMPT.format(party=ch.name or ch.party)},
                                                        {"role": "user", "content": text}], max_tokens=200)
        m = re.search(r"\{.*\}", comp.content, re.S)
        data = json.loads(m.group(0)) if m else {}
    except Exception:  # noqa: BLE001
        return None
    crew, ext = str(data.get("crew") or "").strip(), str(data.get("party") or "").strip()
    if not crew and not ext:
        return None
    return Route(crew=crew, external=ext, party=ch.party if ext else "", how="llm", ms=(time.perf_counter() - t0) * 1000)


# ================================================================================================ the entry points
def quick(text: str, ctx: Context) -> Route | None:
    """Everything the rules can settle (no model, no waiting); None when only a model can tell."""
    t0 = time.perf_counter()
    ch = ctx.channel
    text = text.strip()
    if not ch or not ch.live:
        officers = _officers_in(norm(text), True)
        r = Route(crew=text, addressed=officers or ((ctx.facing,) if ctx.facing in BRIDGE else ()), how="no_channel")
        if ch and ch.open and ch.muted:
            n = norm(text)
            if _party_vocative(n) and (_EXT_STRONG.search(n) or _EXT_MED.search(n)):
                r.unsure = True                        # he seems to speak to them, but the channel is muted
        r.ms = (time.perf_counter() - t0) * 1000
        return r
    d = decide(text, ctx)
    if d.dest == "unsure":
        return None
    return Route(crew=d.crew, external=d.external, party=ch.party if d.external else "", addressed=d.officers, how="rules",
                 unsure=d.unsure, ms=(time.perf_counter() - t0) * 1000)


async def route(llm: OpenRouter | None, text: str, ctx: Context, allow_model: bool = True, wait_s: float = 1.5) -> Route:
    """Whom the Captain's words are for. Rules first; the model only for what they cannot settle (and never for longer than
    `wait_s`); if it does not answer, the words stay on the bridge."""
    r = quick(text, ctx)
    if r is not None:
        return r
    d = decide(text, ctx)
    fallback = Route(crew=text.strip(), addressed=d.officers, how="fallback", unsure=True)
    if not allow_model or llm is None:
        return fallback
    try:
        got = await asyncio.wait_for(route_llm(llm, text, ctx), timeout=wait_s)
    except asyncio.TimeoutError:
        return fallback
    if got is None:
        return fallback
    got.addressed = d.officers
    return got
