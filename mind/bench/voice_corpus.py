"""Test speech for the voice benchmark: the Captain's orders in the seven languages of the game, made by two independent speech
synthesisers (Pocket TTS and the macOS voices), clean and with the noise of a bridge (ventilation, reactor hum, console
bleeps, a second voice talking, explosions, a little reverb). Generated once and cached in mind/.cache/voice_bench/.

There are no recordings of real people here (nobody to record them, and the owner's audio is private): this is a proxy,
and the report says so. Synthetic speech is easier than a tired human on a laptop microphone; what it does measure is the
relative difference between engines, the effect of the game's names, of noise, and of the language."""
from __future__ import annotations

import hashlib
import subprocess
import tempfile
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, lfilter

from astra_mind.env import CACHE
from astra_mind.voice_audio import resample

RATE = 16000
CACHE_DIR = CACHE / "voice_bench"

# (text, the game's names in it)
CORPUS: dict[str, list[tuple[str, list[str]]]] = {
    "en": [("Helm, come to heading two one seven.", ["Helm"]),
           ("Full ahead.", []),
           ("Tactical, fire on the Acheron.", ["Acheron"]),
           ("Comms, open a channel to the Praetorian.", ["Praetorian"]),
           ("Red alert, shields to maximum.", []),
           ("Ferri, take us through the Janus Gate to Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, what is the reactor temperature?", ["Mensah"]),
           ("Sensors, are there any hostile contacts within fifty kilometres?", []),
           ("Voss, launch missiles at the Lethe and keep the railguns on the Styx.", ["Voss", "Lethe", "Styx", "railguns"]),
           ("Doctor Lindqvist, how are the wounded on Deck six?", ["Lindqvist"]),
           ("Captain's log: we held Aurelia today, but the Vigilant is badly damaged.", ["Aurelia", "Vigilant"]),
           ("Bring us to visual contact, I want the enemy on screen.", [])],
    "it": [("Timoniere, rotta due uno sette.", []),
           ("Avanti tutta.", []),
           ("Tattico, fuoco sull'Acheron.", ["Acheron"]),
           ("Comunicazioni, apri un canale con la Praetorian.", ["Praetorian"]),
           ("Allarme rosso, scudi al massimo.", []),
           ("Ferri, portaci attraverso il Janus Gate verso Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, qual è la temperatura del reattore?", ["Mensah"]),
           ("Sensori, ci sono contatti ostili entro cinquanta chilometri?", []),
           ("Voss, lancia i missili sulla Lethe e tieni i railgun puntati sulla Styx.", ["Voss", "Lethe", "Styx", "railgun"]),
           ("Dottoressa Lindqvist, come stanno i feriti del ponte sei?", ["Lindqvist"]),
           ("Diario del capitano: oggi abbiamo difeso Aurelia, ma la Vigilant è gravemente danneggiata.", ["Aurelia", "Vigilant"]),
           ("Portaci a contatto visivo, voglio vedere il nemico sullo schermo.", [])],
    "es": [("Timonel, rumbo dos uno siete.", []),
           ("Avante toda.", []),
           ("Táctico, fuego sobre el Acheron.", ["Acheron"]),
           ("Comunicaciones, abra un canal con el Praetorian.", ["Praetorian"]),
           ("Alerta roja, escudos al máximo.", []),
           ("Ferri, llévenos a través de la Janus Gate hacia Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, ¿cuál es la temperatura del reactor?", ["Mensah"]),
           ("Sensores, ¿hay contactos hostiles a menos de cincuenta kilómetros?", []),
           ("Voss, lance misiles contra el Lethe y mantenga los railguns sobre el Styx.", ["Voss", "Lethe", "Styx", "railguns"]),
           ("Doctora Lindqvist, ¿cómo están los heridos de la cubierta seis?", ["Lindqvist"]),
           ("Diario del capitán: hoy defendimos Aurelia, pero el Vigilant está muy dañado.", ["Aurelia", "Vigilant"]),
           ("Acérquenos hasta contacto visual, quiero ver al enemigo en pantalla.", [])],
    "fr": [("Barreur, cap deux un sept.", []),
           ("En avant toute.", []),
           ("Tactique, feu sur l'Acheron.", ["Acheron"]),
           ("Transmissions, ouvrez un canal avec le Praetorian.", ["Praetorian"]),
           ("Alerte rouge, boucliers au maximum.", []),
           ("Ferri, faites-nous traverser la Janus Gate vers Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, quelle est la température du réacteur ?", ["Mensah"]),
           ("Capteurs, y a-t-il des contacts hostiles à moins de cinquante kilomètres ?", []),
           ("Voss, lancez les missiles sur le Lethe et gardez les railguns sur le Styx.", ["Voss", "Lethe", "Styx", "railguns"]),
           ("Docteur Lindqvist, comment vont les blessés du pont six ?", ["Lindqvist"]),
           ("Journal du capitaine : nous avons défendu Aurelia aujourd'hui, mais le Vigilant est gravement endommagé.", ["Aurelia", "Vigilant"]),
           ("Amenez-nous à portée visuelle, je veux voir l'ennemi à l'écran.", [])],
    "de": [("Steuermann, Kurs zwei eins sieben.", []),
           ("Volle Kraft voraus.", []),
           ("Taktik, Feuer auf die Acheron.", ["Acheron"]),
           ("Kommunikation, öffnen Sie einen Kanal zur Praetorian.", ["Praetorian"]),
           ("Roter Alarm, Schilde auf Maximum.", []),
           ("Ferri, bringen Sie uns durch das Janus Gate nach Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, wie hoch ist die Reaktortemperatur?", ["Mensah"]),
           ("Sensoren, gibt es feindliche Kontakte innerhalb von fünfzig Kilometern?", []),
           ("Voss, starten Sie Raketen auf die Lethe und halten Sie die Railguns auf die Styx.", ["Voss", "Lethe", "Styx", "Railguns"]),
           ("Doktor Lindqvist, wie geht es den Verwundeten auf Deck sechs?", ["Lindqvist"]),
           ("Logbuch des Kapitäns: Heute haben wir Aurelia verteidigt, aber die Vigilant ist schwer beschädigt.", ["Aurelia", "Vigilant"]),
           ("Bringen Sie uns auf Sichtkontakt, ich will den Feind auf dem Bildschirm sehen.", [])],
    "pt": [("Timoneiro, rumo dois um sete.", []),
           ("Avante toda.", []),
           ("Tático, fogo sobre o Acheron.", ["Acheron"]),
           ("Comunicações, abra um canal com o Praetorian.", ["Praetorian"]),
           ("Alerta vermelho, escudos ao máximo.", []),
           ("Ferri, leve-nos através do Janus Gate até Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, qual é a temperatura do reator?", ["Mensah"]),
           ("Sensores, há contatos hostis a menos de cinquenta quilômetros?", []),
           ("Voss, lance mísseis contra o Lethe e mantenha os railguns no Styx.", ["Voss", "Lethe", "Styx", "railguns"]),
           ("Doutora Lindqvist, como estão os feridos do convés seis?", ["Lindqvist"]),
           ("Diário do capitão: hoje defendemos Aurelia, mas o Vigilant está muito danificado.", ["Aurelia", "Vigilant"]),
           ("Leve-nos ao contato visual, quero ver o inimigo na tela.", [])],
    "nl": [("Roerganger, koers twee een zeven.", []),
           ("Volle kracht vooruit.", []),
           ("Tactisch, vuur op de Acheron.", ["Acheron"]),
           ("Communicatie, open een kanaal naar de Praetorian.", ["Praetorian"]),
           ("Rood alarm, schilden op maximum.", []),
           ("Ferri, breng ons door de Janus Gate naar Cassia.", ["Ferri", "Janus Gate", "Cassia"]),
           ("Mensah, wat is de temperatuur van de reactor?", ["Mensah"]),
           ("Sensoren, zijn er vijandelijke contacten binnen vijftig kilometer?", []),
           ("Voss, lanceer raketten op de Lethe en houd de railguns op de Styx.", ["Voss", "Lethe", "Styx", "railguns"]),
           ("Dokter Lindqvist, hoe gaat het met de gewonden op dek zes?", ["Lindqvist"]),
           ("Logboek van de kapitein: vandaag hebben we Aurelia verdedigd, maar de Vigilant is zwaar beschadigd.", ["Aurelia", "Vigilant"]),
           ("Breng ons in zichtcontact, ik wil de vijand op het scherm zien.", [])],
}

# languages the crew is not spoken in natively but the Captain may speak (STT path only): one phrase each
OTHER = {
    "ja": ("Kyoko", "艦長、針路二一七、全速前進します。"),
    "zh": ("Tingting", "舰长，航向二一七，全速前进。"),
    "ko": ("Yuna", "함장님, 침로 217, 전속 전진합니다."),
    "ar": ("Majed", "أيها القبطان، الاتجاه مئتان وسبعة عشر، بأقصى سرعة."),
    "hi": ("Lekha", "कप्तान, दिशा दो सौ सत्रह, पूरी रफ्तार से आगे।"),
    "tr": ("Yelda", "Kaptan, rota iki yüz on yedi, tam gaz ileri."),
    "ru": ("Milena", "Капитан, курс двести семнадцать, полный вперёд."),
    "pl": ("Zosia", "Kapitanie, kurs dwieście siedemnaście, cała naprzód."),
}

# macOS system voices per language (two each, tried in order; the first two that exist are used)
SAY_VOICES = {
    "en": ["Samantha", "Daniel", "Karen"], "it": ["Alice", "Eddy (Italian (Italy))", "Reed (Italian (Italy))"],
    "es": ["Mónica", "Paulina", "Eddy (Spanish (Spain))"], "fr": ["Thomas", "Jacques", "Eddy (French (France))"],
    "de": ["Anna", "Eddy (German (Germany))", "Reed (German (Germany))"], "pt": ["Luciana", "Joana", "Eddy (Portuguese (Brazil))"],
    "nl": ["Xander", "Ellen"],
}
POCKET_VOICES = ["alba", "giovanni", "jean"]
CONDITIONS = ["clean", "noisy", "hard"]


@dataclass
class Clip:
    lang: str
    text: str
    entities: list[str]
    speaker: str                  # "pocket:alba" / "say:Alice"
    condition: str                # clean | noisy | hard
    pcm: np.ndarray = field(repr=False, default=None)   # float32, 16 kHz

    @property
    def seconds(self) -> float:
        return len(self.pcm) / RATE


def _key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def say_clip(voice: str, text: str) -> np.ndarray | None:
    """One utterance from a macOS voice (16 kHz float32), None when the voice is not installed."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        r = subprocess.run(["say", "-v", voice, "-o", f.name, "--data-format=LEI16@16000", text], capture_output=True)
        if r.returncode != 0:
            return None
        x, sr = sf.read(f.name, dtype="float32")
    return x if x.ndim == 1 else x[:, 0]


def installed_say_voices() -> set[str]:
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    names = set()
    for line in out.splitlines():
        head = line.split("#")[0].rstrip()
        parts = head.rsplit(None, 1)
        if parts:
            names.add(parts[0].strip())
    return names


def pocket_clip(tts, voice: str, lang: str, text: str) -> np.ndarray:
    x = tts.render(text, voice, lang, speed=1.0, gain_db=0.0, limit=False)
    return resample(x, tts.sample_rate, RATE)


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    w = rng.standard_normal(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    p = lfilter(b, a, w)
    return p / (np.std(p) + 1e-9)


def bridge_noise(n: int, rng: np.random.Generator, babble: np.ndarray | None = None, battle: bool = False) -> np.ndarray:
    """Ventilation (pink noise, band-limited), reactor hum (50/100/150 Hz), console bleeps; in battle also a second voice and
    explosions (decaying low thumps)."""
    t = np.arange(n) / RATE
    vent = _pink(n, rng)
    bb, ba = butter(2, [100 / (RATE / 2), 3500 / (RATE / 2)], btype="band")
    vent = lfilter(bb, ba, vent)
    hum = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) / (i + 1) for i, f in enumerate((50, 100, 150)))
    x = 0.8 * vent / np.std(vent) + 0.5 * hum / np.std(hum)
    for _ in range(int(t[-1] / 2.5) + 1):
        c = int(rng.uniform(0, max(1, n - 1000)))
        f0 = rng.uniform(800, 2200)
        m = min(int(0.06 * RATE), n - c)
        x[c:c + m] += 0.9 * np.sin(2 * np.pi * f0 * t[:m]) * np.hanning(m)
    if battle:
        for _ in range(int(t[-1] / 2.0) + 1):
            c = int(rng.uniform(0, max(1, n - 4000)))
            m = min(int(0.6 * RATE), n - c)
            tt = t[:m]
            x[c:c + m] += 3.0 * np.sin(2 * np.pi * rng.uniform(35, 70) * tt) * np.exp(-tt * 6.0)
        if babble is not None and len(babble):
            reps = int(np.ceil(n / len(babble)))
            x += 1.2 * np.tile(babble, reps)[:n] / (np.std(babble) + 1e-9)
    return x.astype(np.float32)


def reverb(x: np.ndarray, rng: np.random.Generator, rt60: float = 0.35, wet: float = 0.3) -> np.ndarray:
    n = int(rt60 * RATE)
    h = rng.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)
    h[0] = 0
    y = fftconvolve(x, h)[: len(x)]
    y = y / (np.std(y) + 1e-9) * np.std(x)
    return ((1 - wet) * x + wet * y).astype(np.float32)


def mix(speech: np.ndarray, condition: str, rng: np.random.Generator, babble: np.ndarray | None = None) -> np.ndarray:
    """The speech as the microphone hears it: `noisy` 15 dB above ventilation, hum and bleeps; `hard` 6 dB with reverb, a
    second voice and explosions. The recording starts and ends with a little silence, as a key press does."""
    lead, tail = int(0.25 * RATE), int(0.20 * RATE)
    x = np.concatenate([np.zeros(lead, np.float32), speech, np.zeros(tail, np.float32)])
    if condition == "clean":
        return (x + rng.standard_normal(len(x)).astype(np.float32) * 1e-4).astype(np.float32)
    snr = {"noisy": 15.0, "hard": 6.0}[condition]
    if condition == "hard":
        x = reverb(x, rng)
    noise = bridge_noise(len(x), rng, babble, battle=(condition == "hard"))
    sp = float(np.sqrt(np.mean(speech.astype(np.float64) ** 2)) + 1e-9)
    nz = float(np.sqrt(np.mean(noise.astype(np.float64) ** 2)) + 1e-9)
    y = x + noise * (sp / nz) * 10 ** (-snr / 20)
    return (y / max(1.0, float(np.abs(y).max()) / 0.95)).astype(np.float32)


def build(tts, langs: list[str], conditions: list[str] = CONDITIONS, pocket: list[str] | None = None,
          say_n: int = 2, per_lang: int | None = None) -> list[Clip]:
    """The benchmark clips: every order of every language by the Pocket voices and the macOS voices, in every condition."""
    pocket = pocket or POCKET_VOICES
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    have = installed_say_voices()
    clips: list[Clip] = []
    rng = np.random.default_rng(7)
    for lang in langs:
        items = CORPUS[lang][:per_lang] if per_lang else CORPUS[lang]
        say_voices = [v for v in SAY_VOICES.get(lang, []) if v in have][:say_n]
        babble = pocket_clip(tts, "george", lang, "Report from the flight deck, all fighters are fuelled and armed, waiting for launch orders.")
        for text, ents in items:
            speakers = [("pocket", v) for v in pocket] + [("say", v) for v in say_voices]
            for kind, v in speakers:
                f = CACHE_DIR / f"clean_{_key(kind, v, lang, text)}.npy"
                if f.exists():
                    x = np.load(f)
                else:
                    x = pocket_clip(tts, v, lang, text) if kind == "pocket" else say_clip(v, text)
                    if x is None:
                        continue
                    np.save(f, x)
                for cond in conditions:
                    fc = CACHE_DIR / f"{cond}_{_key(kind, v, lang, text)}.npy"
                    if fc.exists():
                        y = np.load(fc)
                    else:
                        y = mix(x, cond, rng, babble)
                        np.save(fc, y)
                    clips.append(Clip(lang, text, ents, f"{kind}:{v}", cond, y))
    return clips
