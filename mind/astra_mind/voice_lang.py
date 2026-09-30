"""Which language does the Captain speak? The crew answers in it, so a wrong guess flips the whole bridge into another
language (a two-word "Mi sentite?" once came back as Spanish and the crew answered in Spanish).

Short phrases carry little evidence, so several weak signals are combined instead of trusting one: the text detector
(lingua) over the languages the game handles, the crew's own vocabulary per language (roles, orders, navigation: a
"scudi a prua" is Italian even though lingua cannot tell it from Spanish), the language the recogniser itself reported
(Whisper does; Parakeet does not) and, most of all, what the Captain spoke a moment ago: people do not switch language
between orders. A new language wins only against real evidence."""
from __future__ import annotations

import logging
import re
import unicodedata
from functools import lru_cache

log = logging.getLogger("astra.lang")

# languages the crew can be addressed in (crew.py LANG_NAMES) plus a few that people speak to games
CANDIDATES = ("it", "en", "es", "fr", "de", "pt", "nl", "ru", "pl", "ja", "zh", "ar", "ko", "tr")
TTS_LANGS = ("it", "en", "es", "fr", "de", "pt", "nl")             # the ones the local voices speak natively

# words a bridge officer hears: enough to settle a short order (accents stripped, lower case)
DOMAIN: dict[str, set[str]] = {
    "it": set("""capitano timoniere tattico comunicazioni sensori ingegneria ingegnere macchine volo rotta avanti indietro tutta mezza
        scudi prua poppa dritta babordo fuoco cessate armi siluri missili bersaglio nemico nemici nave navi allarme rosso giallo
        canale apri chiudi rapporto stato danni velocita manetta virata virare gradi quanti quante sono ci dove quale sentite
        sentiti portaci portami avvicinati allontanati contatto visivo schermo vedere voglio ordine agli ordini ricevuto
        dottoressa medico feriti infermeria ponte hangar caccia squadriglia lanciate richiamate lancia motori reattore calore
        radiatori dimmi dammi mostrami ripeti puoi potete grazie bene male subito ancora della dello degli nella sul""".split()),
    "en": set("""captain helm tactical comms communications sensors engineering flight course heading ahead astern full half
        shields bow stern starboard port fire cease weapons torpedoes missiles target enemy hostile ship ships alert red yellow
        channel open close report status damage speed throttle turn degrees how many are there where which can you hear
        take us bring me approach close contact visual screen see want order aye understood doctor wounded medbay deck hangar
        fighters squadron launch recall engines reactor heat radiators tell give show repeat please thanks good bad now again
        the and with what this that from""".split()),
    "es": set("""capitan timonel tactico comunicaciones sensores ingenieria vuelo rumbo adelante atras toda media escudos proa popa
        estribor babor fuego alto armas torpedos misiles objetivo enemigo nave naves alerta roja amarilla canal abre cierra
        informe estado danos velocidad acelerador girar grados cuantos cuantas hay donde cual puede oye llevanos acerquese
        contacto visual pantalla ver quiero orden recibido doctora heridos enfermeria cubierta hangar cazas escuadron lanzar
        motores reactor calor radiadores dime dame muestrame repite gracias bien mal ahora otra vez los las con que este esa""".split()),
    "fr": set("""capitaine barreur tactique communications capteurs ingenierie vol cap avant arriere toute demi boucliers proue poupe
        tribord babord feu cessez armes torpilles missiles cible ennemi vaisseau vaisseaux alerte rouge jaune canal ouvrez
        fermez rapport etat degats vitesse manette virez degres combien sont il y a ou quel pouvez entendez emmenez approchez
        contact visuel ecran voir veux ordre recu docteur blesses infirmerie pont hangar chasseurs escadrille lancez
        moteurs reacteur chaleur radiateurs dites donnez montrez repetez merci bien mal maintenant encore les des avec que""".split()),
    "de": set("""kapitan steuermann taktik kommunikation sensoren technik flug kurs voraus achteraus volle halbe schilde bug heck
        steuerbord backbord feuer einstellen waffen torpedos raketen ziel feind schiff schiffe alarm rot gelb kanal offnen
        schliessen bericht zustand schaden geschwindigkeit schub drehen grad wie viele sind gibt wo welche konnen horen
        bringen naher kontakt sichtkontakt bildschirm sehen will befehl verstanden doktor verwundete krankenstation deck hangar
        jager staffel starten triebwerke reaktor hitze kuhler sagen geben zeigen wiederholen bitte danke gut schlecht jetzt
        noch die der das und mit was diese""".split()),
    "pt": set("""capitao timoneiro tatico comunicacoes sensores engenharia voo rumo avante re toda meia escudos proa popa estibordo
        bombordo fogo cessar armas torpedos misseis alvo inimigo nave naves alerta vermelho amarelo canal abra feche relatorio
        estado danos velocidade acelerador virar graus quantos quantas ha onde qual pode ouve leve aproxime contato visual
        tela ver quero ordem recebido doutora feridos enfermaria convoo hangar cacas esquadrao lancar motores reator calor
        radiadores diga de mostre repita obrigado bem mal agora outra vez os as com que esta essa""".split()),
    "nl": set("""kapitein roerganger tactisch communicatie sensoren techniek vlucht koers vooruit achteruit volle halve schilden boeg
        achtersteven stuurboord bakboord vuur staakt wapens torpedos raketten doel vijand schip schepen alarm rood geel kanaal
        open sluit rapport status schade snelheid gas draai graden hoeveel zijn er waar welke kunt hoort breng kom dichterbij
        contact zicht scherm zien wil bevel begrepen dokter gewonden ziekenboeg dek hangar jagers eskader lanceer motoren
        reactor hitte radiatoren zeg geef toon herhaal alsjeblieft dank goed slecht nu weer de het een met wat deze""".split()),
}


def _fold(s: str) -> str:
    """Lower case without accents."""
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@lru_cache(maxsize=1)
def _detector():
    from lingua import Language as L, LanguageDetectorBuilder
    table = {"it": L.ITALIAN, "en": L.ENGLISH, "es": L.SPANISH, "fr": L.FRENCH, "de": L.GERMAN, "pt": L.PORTUGUESE,
             "nl": L.DUTCH, "ru": L.RUSSIAN, "pl": L.POLISH, "ja": L.JAPANESE, "zh": L.CHINESE, "ar": L.ARABIC,
             "ko": L.KOREAN, "tr": L.TURKISH}
    det = LanguageDetectorBuilder.from_languages(*table.values()).build()
    back = {v: k for k, v in table.items()}
    return det, back


def text_scores(text: str) -> dict[str, float]:
    """Probability-like score per candidate language from the text alone (lingua), 0 for the ones it does not rank."""
    try:
        det, back = _detector()
        return {back[c.language]: c.value for c in det.compute_language_confidence_values(text)}
    except Exception:  # noqa: BLE001 - a missing detector must not stop the crew from hearing the Captain
        log.exception("language detector failed")
        return {}


def domain_hits(text: str) -> dict[str, int]:
    words = [_fold(w) for w in _WORD.findall(text)]
    return {lang: sum(1 for w in words if w in vocab) for lang, vocab in DOMAIN.items()}


def resolve_language(text: str, prior: str = "en", backend_lang: str | None = None, backend_weight: float = 0.35) -> tuple[str, float]:
    """(language code, confidence 0..1). `prior` is the language the Captain spoke last; `backend_lang` what the
    recogniser reported (None when it does not say)."""
    text = (text or "").strip()
    if not text:
        return (backend_lang or prior), 0.0
    words = _WORD.findall(text)
    score = {k: 0.0 for k in CANDIDATES}
    for k, v in text_scores(text).items():
        score[k] = v
    hits = domain_hits(text)
    for k, n in hits.items():
        score[k] += min(0.6, 0.25 * n)
    if backend_lang in score:
        score[backend_lang] += backend_weight
    # the language of the last words is the best guess: the shorter the phrase, the more it counts
    score[prior if prior in score else "en"] += 0.55 if len(words) <= 2 else 0.40 if len(words) <= 4 else 0.25 if len(words) <= 8 else 0.10
    total = sum(score.values()) or 1.0
    best = max(score, key=score.get)
    return best, score[best] / total
