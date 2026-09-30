"""Labelled utterances for the router: whom is the Captain talking to, with or without a channel open?

Three sets, so that what is tuned and what is measured never mix:
  DEV       written first, used to build and tune the rules (errors here are read and fixed);
  PLAYTEST  the Captain's real words from the first game (29/9), typed and spoken, exactly as logged (with their typos);
  TEST      written after the rules were frozen, measured once (bench/router_test_set.py).

Each item: the words, language, style (typed = lowercase, no accents or punctuation, typos; spoken = what the speech
recogniser writes), the channel state, and the right destination: crew | external | both. `hard` marks the ones that are
ambiguous even to a person; their gold answer follows the policy (no clear address to the party = the crew, comms may offer to
relay). Channel states:
    none        no channel open
    enemy       open with the Cocytus's captain (Ferryman Irina Vael), quiet for minutes
    live        open with her, and she spoke to the Captain a few seconds ago (an exchange is going on)
    fleet       open with the fleet (Vice Admiral Rourke), quiet
    fleet_live  the same, and he just spoke
    muted       open with her but muted: nothing the Captain says goes out
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    text: str
    lang: str
    style: str                     # typed | spoken
    chan: str                      # none | enemy | live | fleet | fleet_live | muted
    dest: str                      # crew | external | both
    facing: str | None = None      # an officer id or "viewscreen"
    hard: bool = False
    ext: str = ""                  # both: a phrase the external part must contain (lower case, no accents)
    crew: str = ""                 # both: a phrase the crew part must contain
    src: str = "dev"


def _mk(src: str):
    def make(text: str, lang: str, style: str, chan: str, dest: str, facing: str | None = None, hard: bool = False,
             ext: str = "", crew: str = "") -> Item:
        return Item(text, lang, style, chan, dest, facing, hard, ext, crew, src)
    return make


D = _mk("dev")

DEV: list[Item] = [
    # ---- Italian, typed, channel open and quiet: orders and questions to the bridge, no name (the playtest's misroutes)
    D("fuoco a volonta", "it", "typed", "enemy", "crew"),
    D("sparate con tutto", "it", "typed", "enemy", "crew"),
    D("sparate tutto quello che avete", "it", "typed", "enemy", "crew"),
    D("rapporto armamenti", "it", "typed", "enemy", "crew"),
    D("ci sono navi nemiche", "it", "typed", "enemy", "crew"),
    D("quali armi abbiamo", "it", "typed", "enemy", "crew"),
    D("a che velocita ci muoviamo", "it", "typed", "enemy", "crew"),
    D("siamo in raggio per usare le armi", "it", "typed", "enemy", "crew"),
    D("alzate gli scudi", "it", "typed", "enemy", "crew"),
    D("fate partire i caccia", "it", "typed", "enemy", "crew"),
    D("imposta codice rosso", "it", "typed", "enemy", "crew"),
    D("voglio vedere a schermo i nemici", "it", "typed", "enemy", "crew"),
    D("avvicinati a nemici veloce", "it", "typed", "enemy", "crew"),
    D("fuoco sul cocytus", "it", "typed", "enemy", "crew"),
    D("scappiamo via", "it", "typed", "enemy", "crew"),
    D("quanti missili ci restano", "it", "typed", "enemy", "crew"),
    D("portaci a contatto visivo", "it", "typed", "enemy", "crew"),
    D("stiamo perdendo scudi", "it", "typed", "enemy", "crew"),
    D("voglio i caccia in volo adesso", "it", "typed", "enemy", "crew"),
    D("come sta lo scafo", "it", "typed", "enemy", "crew"),
    D("qual e la distanza dal cocytus", "it", "typed", "enemy", "crew"),
    D("tienilo a schermo", "it", "typed", "enemy", "crew"),
    D("richiamate tutto", "it", "typed", "enemy", "crew"),
    D("quanta energia abbiamo agli scudi", "it", "typed", "enemy", "crew"),
    D("spegnete i motori", "it", "typed", "enemy", "crew"),
    D("cosa stanno facendo i nemici", "it", "typed", "enemy", "crew"),
    D("la nave nemica e in portata", "it", "typed", "enemy", "crew"),
    D("mandate una squadra antincendio al ponte quattro", "it", "typed", "enemy", "crew"),
    D("mandate i droni in ricognizione", "it", "typed", "enemy", "crew"),
    D("chi ci sta sparando addosso", "it", "typed", "enemy", "crew"),
    D("vedi qualcosa ai sensori", "it", "typed", "enemy", "crew"),
    D("chiudi il canale", "it", "typed", "enemy", "crew"),
    D("lanciate due missili sul cocytus", "it", "typed", "enemy", "crew"),
    D("intercettalo e tienilo a sei chilometri", "it", "typed", "enemy", "crew"),
    D("quanto manca al gate", "it", "typed", "enemy", "crew"),
    D("mi sentite", "it", "typed", "enemy", "crew", hard=True),
    # ---- Italian, typed, the enemy is addressed
    D("qui il capitano dell'aquila fermatevi o verrete annientati", "it", "typed", "enemy", "external"),
    D("cocytus arrendetevi", "it", "typed", "enemy", "external"),
    D("ferryman vael mi ascolti", "it", "typed", "enemy", "external"),
    D("cosa volete da noi", "it", "typed", "enemy", "external"),
    D("perche ci attaccate", "it", "typed", "enemy", "external"),
    D("avete un minuto per ritirarvi", "it", "typed", "enemy", "external"),
    D("identificatevi", "it", "typed", "enemy", "external"),
    D("vi offro una tregua", "it", "typed", "enemy", "external"),
    D("non voglio combattere parliamo", "it", "typed", "enemy", "external"),
    D("abbassate le armi e nessuno si fara male", "it", "typed", "enemy", "external"),
    D("chi comanda la vostra flotta", "it", "typed", "enemy", "external"),
    D("vael sono il capitano dell'aquila", "it", "typed", "enemy", "external"),
    D("vi conviene arrendervi", "it", "typed", "enemy", "external"),
    D("ritiratevi dal sistema", "it", "typed", "enemy", "external"),
    D("comandante ci stia a sentire", "it", "typed", "enemy", "external"),
    D("cocytus qui l'aquila rispondete", "it", "typed", "enemy", "external"),
    # ---- Italian, spoken
    D("Cocytus, qui è il capitano dell'Aquila. Ritiratevi immediatamente o apriremo il fuoco.", "it", "spoken", "enemy", "external"),
    D("Ferryman Vael, mi sente?", "it", "spoken", "enemy", "external"),
    D("Tattico, fuoco sul Cocytus.", "it", "spoken", "enemy", "crew"),
    D("Timoniere, portaci a dieci chilometri dal Cocytus.", "it", "spoken", "enemy", "crew"),
    D("Voss, tieni i missili pronti.", "it", "spoken", "enemy", "crew"),
    D("Qual è la situazione dei nostri scudi?", "it", "spoken", "enemy", "crew"),
    D("Ferryman, ascolti bene: avete sessanta secondi per arrendervi. Tattico, missili pronti sul Cocytus.", "it", "spoken",
      "enemy", "both", ext="sessanta secondi", crew="missili pronti"),
    D("Comunicazioni, chiudete il canale.", "it", "spoken", "enemy", "crew"),
    D("Vael, non è troppo tardi per fermarvi.", "it", "spoken", "enemy", "external"),
    D("Quanto siamo lontani dal Cocytus?", "it", "spoken", "enemy", "crew"),
    D("Ferri, portaci in avvicinamento. Voss, armi pronte.", "it", "spoken", "enemy", "crew"),
    D("Sensori, che cosa vedete dietro il Cocytus?", "it", "spoken", "enemy", "crew"),
    D("Capitano Vael, sono pronto a trattare le condizioni della vostra ritirata.", "it", "spoken", "enemy", "external"),
    D("Serra, che ne pensi di questa offerta?", "it", "spoken", "live", "crew"),
    D("Non siamo qui per uccidervi, Ferryman. Lasciateci passare.", "it", "spoken", "enemy", "external"),
    D("Martin, apri un canale con l'ammiraglio Rourke.", "it", "spoken", "enemy", "crew"),
    D("Mi passi il rapporto sui danni, Tanaka.", "it", "spoken", "enemy", "crew"),
    D("Aspetti, Ferryman: prima voglio sapere chi vi ha mandato.", "it", "spoken", "enemy", "external"),
    # ---- Italian, an exchange is going on (the party spoke a moment ago)
    D("no", "it", "typed", "live", "external"),
    D("non ci credo", "it", "typed", "live", "external"),
    D("va bene accetto le vostre condizioni", "it", "typed", "live", "external"),
    D("perche dovrei fidarmi di voi", "it", "typed", "live", "external"),
    D("quanto tempo mi date", "it", "typed", "live", "external"),
    D("sparate", "it", "typed", "live", "crew"),
    D("tattico armi pronte", "it", "typed", "live", "crew"),
    D("mai", "it", "typed", "live", "external"),
    D("ce ne andremo se voi fate lo stesso", "it", "typed", "live", "external"),
    D("avete la mia parola", "it", "typed", "live", "external"),
    D("silenzio elettronico", "it", "typed", "live", "crew"),
    D("sensori attivi", "it", "typed", "live", "crew"),
    D("la vostra offerta e inaccettabile", "it", "typed", "live", "external"),
    D("cosa intende con questo", "it", "typed", "live", "external"),
    D("Non ho intenzione di cedere.", "it", "spoken", "live", "external"),
    D("Va bene, ma solo se ritirate anche i caccia.", "it", "spoken", "live", "external"),
    D("Sentito? Tattico, prepara una salva.", "it", "spoken", "live", "both", ext="sentito", crew="salva"),
    # ---- no channel: everything is for the bridge (and comms makes the call)
    D("cocytus arrendetevi", "it", "typed", "none", "crew"),
    D("qui il capitano dell'aquila fermatevi", "it", "typed", "none", "crew"),
    D("chiama il cocytus", "it", "typed", "none", "crew"),
    D("comunicazioni apri un canale con l'ammiraglio", "it", "typed", "none", "crew"),
    D("mandate una squadra al ponte sei", "it", "typed", "none", "crew"),
    D("fuoco a volonta", "it", "typed", "none", "crew"),
    D("Ferryman Vael, qui il capitano dell'Aquila.", "it", "spoken", "none", "crew"),
    # ---- muted: the words cannot go out
    D("vael arrendetevi", "it", "typed", "muted", "crew"),
    D("cosa volete", "it", "typed", "muted", "crew"),
    D("fuoco a volonta", "it", "typed", "muted", "crew"),
    D("Ferryman, ci lasci passare.", "it", "spoken", "muted", "crew"),
    # ---- the fleet channel (an admiral and allied ships)
    D("ammiraglio chiediamo rinforzi", "it", "typed", "fleet", "external"),
    D("praetorian concentrate il fuoco sull'acheron", "it", "typed", "fleet", "external"),
    D("comunicazioni chiedete rinforzi all'ammiraglio", "it", "typed", "fleet", "crew"),
    D("ammiraglio qui l'aquila rapporto della situazione", "it", "typed", "fleet", "external"),
    D("rapporto danni", "it", "typed", "fleet", "crew"),
    D("abbiamo bisogno di supporto ammiraglio", "it", "typed", "fleet", "external"),
    D("come siamo messi con i missili", "it", "typed", "fleet", "crew"),
    D("ferri portaci vicino al praetorian", "it", "typed", "fleet", "crew"),
    D("Ammiraglio Rourke, il Mandato ha rotto la linea. Richiedo supporto immediato.", "it", "spoken", "fleet", "external"),
    D("Praetorian, Vigilant: fuoco concentrato sull'Acheron.", "it", "spoken", "fleet", "external"),
    D("Che cosa ha detto l'ammiraglio, Martin?", "it", "spoken", "fleet_live", "crew"),
    D("Ricevuto, ammiraglio. Resistiamo ancora dieci minuti.", "it", "spoken", "fleet_live", "external"),
    # ---- who the Captain is facing
    D("portaci piu vicini", "it", "typed", "enemy", "crew", facing="helm"),
    D("cosa vedi", "it", "typed", "enemy", "crew", facing="sensors"),
    D("cosa volete da noi", "it", "typed", "live", "external", facing="viewscreen"),
    D("fuoco", "it", "typed", "enemy", "crew", facing="tactical"),
    # ---- English, typed
    D("fire everything we have", "en", "typed", "enemy", "crew"),
    D("weapons report", "en", "typed", "enemy", "crew"),
    D("are there any hostiles left", "en", "typed", "enemy", "crew"),
    D("whats our speed", "en", "typed", "enemy", "crew"),
    D("shields to maximum", "en", "typed", "enemy", "crew"),
    D("launch all fighters", "en", "typed", "enemy", "crew"),
    D("how many missiles left", "en", "typed", "enemy", "crew"),
    D("put the enemy on screen", "en", "typed", "enemy", "crew"),
    D("give me a status report", "en", "typed", "enemy", "crew"),
    D("fire on the cocytus", "en", "typed", "enemy", "crew"),
    D("can you hear me", "en", "typed", "enemy", "crew", hard=True),
    D("this is the captain of the aquila stand down", "en", "typed", "enemy", "external"),
    D("cocytus surrender now", "en", "typed", "enemy", "external"),
    D("vael listen to me", "en", "typed", "enemy", "external"),
    D("what do you want", "en", "typed", "enemy", "external"),
    D("we will destroy you if you do not withdraw", "en", "typed", "enemy", "external"),
    D("you have one minute", "en", "typed", "enemy", "external"),
    D("i am willing to talk", "en", "typed", "enemy", "external"),
    D("captain vael this is the captain of the aquila", "en", "typed", "enemy", "external"),
    D("who sent you", "en", "typed", "enemy", "external"),
    D("send a damage control team to deck four", "en", "typed", "enemy", "crew"),
    D("hold your fire", "en", "typed", "enemy", "crew", hard=True),
    D("cut the engines", "en", "typed", "enemy", "crew"),
    D("how far is the cocytus", "en", "typed", "enemy", "crew"),
    # ---- English, spoken
    D("Helm, take us to ten kilometres from the Cocytus.", "en", "spoken", "enemy", "crew"),
    D("Tactical, all weapons on the Cocytus.", "en", "spoken", "enemy", "crew"),
    D("Ferryman Vael, this is the Captain of the ASN Aquila. Stand down or we will open fire.", "en", "spoken", "enemy", "external"),
    D("Commander, I don't want to kill your crew. Withdraw.", "en", "spoken", "enemy", "external"),
    D("Mr. Ferri, come about to two-seven-zero.", "en", "spoken", "enemy", "crew"),
    D("Comms, mute the channel.", "en", "spoken", "enemy", "crew"),
    D("Ops, put the Cocytus on the main screen.", "en", "spoken", "enemy", "crew"),
    D("You have thirty seconds to lower your shields. Tactical, lock missiles on the Cocytus.", "en", "spoken", "enemy", "both",
      ext="thirty seconds", crew="lock missiles"),
    D("What's their status, Nair?", "en", "spoken", "enemy", "crew"),
    D("I'm not going to negotiate with a pirate.", "en", "spoken", "live", "external"),
    D("Fine. Tell me your terms.", "en", "spoken", "live", "external"),
    D("Voss, hold fire until I say so.", "en", "spoken", "live", "crew"),
    D("No.", "en", "spoken", "live", "external"),
    D("Stand by, Captain Vael, I'm consulting my officers. Serra, thoughts?", "en", "spoken", "live", "both", ext="stand by", crew="thoughts"),
    D("Admiral, the Acheron is breaking through. Request immediate support.", "en", "spoken", "fleet", "external"),
    D("Ops, damage report on all decks.", "en", "spoken", "fleet", "crew"),
    D("Cocytus, this is the Aquila, respond.", "en", "spoken", "none", "crew"),
    # ---- Spanish
    D("fuego a discrecion", "es", "typed", "enemy", "crew"),
    D("informe de armas", "es", "typed", "enemy", "crew"),
    D("hay naves enemigas", "es", "typed", "enemy", "crew"),
    D("escudos al maximo", "es", "typed", "enemy", "crew"),
    D("lanzad los cazas", "es", "typed", "enemy", "crew"),
    D("cuantos misiles nos quedan", "es", "typed", "enemy", "crew"),
    D("aqui el capitan del aquila rindanse", "es", "typed", "enemy", "external"),
    D("cocytus rindanse", "es", "typed", "enemy", "external"),
    D("que quieren de nosotros", "es", "typed", "enemy", "external"),
    D("tienen un minuto para retirarse", "es", "typed", "enemy", "external"),
    D("vael me escucha", "es", "typed", "enemy", "external"),
    D("Timonel, rumbo cero-nueve-cero.", "es", "spoken", "enemy", "crew"),
    D("Táctico, fuego sobre el Cocytus.", "es", "spoken", "enemy", "crew"),
    D("Ferryman Vael, aquí el capitán del Aquila. Retírense de inmediato.", "es", "spoken", "enemy", "external"),
    D("Comunicaciones, corten el canal.", "es", "spoken", "enemy", "crew"),
    D("¿Cuál es la distancia al Cocytus?", "es", "spoken", "enemy", "crew"),
    D("No aceptamos sus condiciones.", "es", "spoken", "live", "external"),
    D("Oigan bien, Ferryman: bajen las armas o abrimos fuego.", "es", "spoken", "enemy", "external"),
    # ---- French
    D("feu a volonte", "fr", "typed", "enemy", "crew"),
    D("rapport sur les armes", "fr", "typed", "enemy", "crew"),
    D("y a t il des navires ennemis", "fr", "typed", "enemy", "crew"),
    D("boucliers au maximum", "fr", "typed", "enemy", "crew"),
    D("lancez les chasseurs", "fr", "typed", "enemy", "crew"),
    D("combien de missiles il nous reste", "fr", "typed", "enemy", "crew"),
    D("ici le capitaine de l'aquila rendez vous", "fr", "typed", "enemy", "external"),
    D("cocytus rendez vous", "fr", "typed", "enemy", "external"),
    D("que voulez vous", "fr", "typed", "enemy", "external"),
    D("vous avez une minute pour vous retirer", "fr", "typed", "enemy", "external"),
    D("Timonier, cap au deux-sept-zéro.", "fr", "spoken", "enemy", "crew"),
    D("Tactique, feu sur le Cocytus.", "fr", "spoken", "enemy", "crew"),
    D("Ferryman Vael, ici le capitaine de l'Aquila. Retirez-vous immédiatement.", "fr", "spoken", "enemy", "external"),
    D("Communications, coupez le canal.", "fr", "spoken", "enemy", "crew"),
    D("Quelle est la distance jusqu'au Cocytus ?", "fr", "spoken", "enemy", "crew"),
    D("Nous n'acceptons pas vos conditions.", "fr", "spoken", "live", "external"),
    # ---- German
    D("feuer frei", "de", "typed", "enemy", "crew"),
    D("waffenbericht", "de", "typed", "enemy", "crew"),
    D("gibt es feindliche schiffe", "de", "typed", "enemy", "crew"),
    D("schilde auf maximum", "de", "typed", "enemy", "crew"),
    D("startet die jaeger", "de", "typed", "enemy", "crew"),
    D("wie viele raketen haben wir noch", "de", "typed", "enemy", "crew"),
    D("hier ist der kapitaen der aquila ergebt euch", "de", "typed", "enemy", "external"),
    D("cocytus ergebt euch", "de", "typed", "enemy", "external"),
    D("was wollt ihr von uns", "de", "typed", "enemy", "external"),
    D("ihr habt eine minute zum rueckzug", "de", "typed", "enemy", "external"),
    D("Steuermann, Kurs zwei-sieben-null.", "de", "spoken", "enemy", "crew"),
    D("Taktik, Feuer auf die Cocytus.", "de", "spoken", "enemy", "crew"),
    D("Ferryman Vael, hier spricht der Kapitän der Aquila. Ziehen Sie sich sofort zurück.", "de", "spoken", "enemy", "external"),
    D("Kommunikation, schließen Sie den Kanal.", "de", "spoken", "enemy", "crew"),
    D("Wie weit ist die Cocytus entfernt?", "de", "spoken", "enemy", "crew"),
    D("Wir akzeptieren Ihre Bedingungen nicht.", "de", "spoken", "live", "external"),
]

P = _mk("playtest")
# The Captain's real words in the first game (29/9), from the mind's log — typed with their typos, or as the recogniser wrote them.
# The channel to the Mandate commander was open for most of it; he almost never spoke to it.
PLAYTEST: list[Item] = [
    P("timoniere portaci a contatto visivo con le navi nemiche", "it", "typed", "enemy", "crew"),
    P("a che velocita ci muoviamo?", "it", "typed", "enemy", "crew"),
    P("tutta velocita punta verso i nemici", "it", "typed", "enemy", "crew"),
    P("siamo in raggio per usare le armi?", "it", "typed", "enemy", "crew"),
    P("fuoco a volonta usiamo tutte le armi", "it", "typed", "enemy", "crew"),
    P("scappiamo via", "it", "typed", "enemy", "crew"),
    P("abbandonare la nave", "it", "typed", "enemy", "crew"),
    P("timoniere fai rotta verso le navi nemiche, puntale cosi le vedo", "it", "typed", "enemy", "crew"),
    P("scudi al massimo", "it", "typed", "enemy", "crew"),
    P("fuoco con tutte le armi", "it", "typed", "enemy", "crew"),
    P("voglio vederre a schermo i nemici", "it", "typed", "enemy", "crew"),
    P("a tutta velocita verso la nostra nave alleata, mettiamoci tra loro e i nemici", "it", "typed", "enemy", "crew"),
    P("fuoco a volonta", "it", "typed", "enemy", "crew"),
    P("rapporto armamenti", "it", "typed", "enemy", "crew"),
    P("secondo ufficiale rapporto armamenti", "it", "typed", "enemy", "crew"),
    P("comunicazioni: fammi parlare con il nemico", "it", "typed", "enemy", "crew"),
    P("qui il capitano dell'aquila, fermatevi o verrete annientati", "it", "typed", "enemy", "external"),
    P("intercettiamo la nave nemica, a tutta velocita", "it", "typed", "enemy", "crew"),
    P("voglio tutti i caccia decollino ora", "it", "typed", "enemy", "crew"),
    P("timoniere quanto ci vuole a raggiungere la nave nemica", "it", "typed", "enemy", "crew"),
    P("richiamiamo i caccia in base", "it", "typed", "enemy", "crew"),
    P("voglio rapporto danni dei caccia", "it", "typed", "enemy", "crew"),
    P("fuoco con i siluri sulla nave nemica", "it", "typed", "enemy", "crew"),
    P("voglio scanner della nave nemica", "it", "typed", "enemy", "crew"),
    P("fuoco a volonta sul cocktopus", "it", "typed", "enemy", "crew"),
    P("timoniere a massima velocita verso il cocktops mantieni la rotta", "it", "typed", "enemy", "crew"),
    P("fuoco con i siluri", "it", "typed", "enemy", "crew"),
    P("rapporto morti e feriti sulla nave, infermeria", "it", "typed", "enemy", "crew"),
    P("quante navi nemiche ci sono? e alleate?", "it", "typed", "enemy", "crew"),
    P("fuoco a volonta e continuo sulla cocytus  con tutte le armi", "it", "typed", "enemy", "crew"),
    P("timoniere portaci dalla seconda nave nemica e tienici a 6000", "it", "typed", "enemy", "crew"),
    P("ci sono navi nemiche?", "it", "typed", "enemy", "crew"),
    P("fuoco a volonta sulla nave nemica", "it", "typed", "enemy", "crew"),
    P("inseguiamo la nave nemica a tutta velocita", "it", "typed", "enemy", "crew"),
    P("ci sono navi nemiche", "it", "typed", "enemy", "crew"),
    P("timoniere vai veloce raggiungi la nave nemica", "it", "typed", "enemy", "crew"),
    P("¿Mi sentite?", "es", "spoken", "enemy", "crew", hard=True),
    P("sparate con tutto", "it", "typed", "enemy", "crew"),
    P("alzate gli scudi", "it", "typed", "enemy", "crew"),
    P("teletrasporto in hangar", "it", "typed", "enemy", "crew"),
    P("fate partire i caccia", "it", "typed", "enemy", "crew"),
    P("imposta codice rosso", "it", "typed", "enemy", "crew"),
    P("fai decollare i caccia, scudi al massimo", "it", "typed", "enemy", "crew"),
    P("lanciate i missili", "it", "typed", "enemy", "crew"),
    P("timoniere portaci lontano veloce", "it", "typed", "enemy", "crew"),
    P("avvicinati a nemici veloce", "it", "typed", "enemy", "crew"),
    P("sparate tutto quello che avete", "it", "typed", "enemy", "crew"),
    P("allarme rosso", "it", "typed", "enemy", "crew"),
    P("sparate i missili", "it", "typed", "enemy", "crew"),
    P("quali armi abbiamo?", "it", "typed", "enemy", "crew"),
]

ALL = DEV + PLAYTEST
