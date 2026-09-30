"""Text for the voice: what the crew's language model writes is not always what a speech model can read.

Pocket TTS has no text front end: "Rotta 217, manetta al 50%" comes out as "Rotta tag Mark Mark Manetta Alde" (measured: digits, "%",
"km" and contact ids like "T-21" are read as noise in every language). `speakable(text, lang)` writes them out the way a bridge
officer would say them, in the language of the line: numbers in words, "%" and "km" as words, bearings digit by digit ("045" ->
"zero four five"), contact ids letter and number ("T-21" -> "T twenty-one"), typographic dashes and quotes as pauses. The
subtitle keeps the original text: only the voice reads the expanded one."""
from __future__ import annotations

import re

try:
    from num2words import num2words
except ImportError:  # noqa: BLE001 - without it digits are left alone (and read badly)
    num2words = None

_N2W = {"en": "en", "it": "it", "es": "es", "fr": "fr", "de": "de", "pt": "pt_BR", "nl": "nl"}
_DIGITS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "niner"],
    "it": ["zero", "uno", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove"],
    "es": ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"],
    "fr": ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf"],
    "de": ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"],
    "pt": ["zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove"],
    "nl": ["nul", "één", "twee", "drie", "vier", "vijf", "zes", "zeven", "acht", "negen"],
}
_DIGITS["en"][9] = "nine"
_UNITS = {
    "en": {"%": "percent", "km/h": "kilometres per hour", "km/s": "kilometres per second", "m/s": "metres per second", "km": "kilometres",
           "°": "degrees", "m": "metres"},
    "it": {"%": "per cento", "km/h": "chilometri orari", "km/s": "chilometri al secondo", "m/s": "metri al secondo", "km": "chilometri",
           "°": "gradi", "m": "metri"},
    "es": {"%": "por ciento", "km/h": "kilómetros por hora", "km/s": "kilómetros por segundo", "m/s": "metros por segundo", "km": "kilómetros",
           "°": "grados", "m": "metros"},
    "fr": {"%": "pour cent", "km/h": "kilomètres à l'heure", "km/s": "kilomètres par seconde", "m/s": "mètres par seconde", "km": "kilomètres",
           "°": "degrés", "m": "mètres"},
    "de": {"%": "Prozent", "km/h": "Kilometer pro Stunde", "km/s": "Kilometer pro Sekunde", "m/s": "Meter pro Sekunde", "km": "Kilometer",
           "°": "Grad", "m": "Meter"},
    "pt": {"%": "por cento", "km/h": "quilômetros por hora", "km/s": "quilômetros por segundo", "m/s": "metros por segundo", "km": "quilômetros",
           "°": "graus", "m": "metros"},
    "nl": {"%": "procent", "km/h": "kilometer per uur", "km/s": "kilometer per seconde", "m/s": "meter per seconde", "km": "kilometer",
           "°": "graden", "m": "meter"},
}
_POINT = {"en": "point", "it": "virgola", "es": "coma", "fr": "virgule", "de": "Komma", "pt": "vírgula", "nl": "komma"}
# words after which a three-digit number is a compass direction and is said digit by digit (bearing, heading, course, mark...)
_DIRECTION = re.compile(r"(?i)\b(bearing|heading|course|mark|azimuth|rilevamento|rotta|prua|rumbo|marcación|marca|cap|relèvement|kurs|peilung|rumo|"
                        r"koers|peiling|richting)\s+(\d{1,3})\b")
_UNIT_AFTER = re.compile(r"(\d)\s?(km/h|km/s|m/s|%|°|km|m)(?![A-Za-z])")


def _say_int(n: int, lang: str) -> str:
    if num2words is None or n > 9_999_999:
        return " ".join(_DIGITS[lang][int(c)] for c in str(n))
    return num2words(n, lang=_N2W[lang]).replace(",", "")           # (English writes "one thousand, two hundred": a comma is a pause)


def _digit_by_digit(s: str, lang: str) -> str:
    return " ".join(_DIGITS[lang][int(c)] for c in s)


def speakable(text: str, lang: str) -> str:
    """`text` as it should be read aloud in `lang` (the seven languages of the local voices; others come back unchanged)."""
    if lang not in _N2W or not text:
        return text
    t = text
    # dashes and quotes the model reads as noise, ellipses, brackets: pauses
    t = re.sub(r"\s*[—–]\s*", ", ", t)
    t = t.replace("…", ".").replace("’", "'").replace("‘", "'")
    t = re.sub(r"[“”«»\"*_#`]", "", t)
    t = re.sub(r"\s*[()\[\]]\s*", ", ", t)
    # contact ids: T-21 -> "T twenty-one"
    t = re.sub(r"\b([A-Z])-(\d{1,3})\b", lambda m: f"{m.group(1)} {_say_int(int(m.group(2)), lang)}", t)
    # directions: a compass number after its keyword, and three digits with a leading zero, digit by digit
    t = _DIRECTION.sub(lambda m: f"{m.group(1)} {_digit_by_digit(m.group(2), lang) if len(m.group(2)) == 3 else _say_int(int(m.group(2)), lang)}", t)
    t = re.sub(r"\b0\d{2}\b", lambda m: _digit_by_digit(m.group(0), lang), t)
    # numbers with a unit: 45 km -> forty-five kilometres (decimals first: 3,5 km)
    units = _UNITS[lang]

    def with_unit(m: re.Match) -> str:
        return f"{m.group(1)} {units[m.group(2)]}"
    t = _UNIT_AFTER.sub(lambda m: with_unit(m), t)
    # decimals: 3,5 (3.5 in English; outside English a dot with one or two decimals too: a model writing Italian often writes 3.2)
    def decimal(m: re.Match) -> str:
        return f"{_say_int(int(m.group(1)), lang)} {_POINT[lang]} {_digit_by_digit(m.group(2), lang) if len(m.group(2)) > 1 else _say_int(int(m.group(2)), lang)}"
    if lang == "en":
        t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)                       # a comma between groups of three digits: 1,200 -> 1200
        t = re.sub(r"(\d+)\.(\d+)", decimal, t)
    else:
        t = re.sub(r"(\d+),(\d+)", decimal, t)
        t = re.sub(r"(?<![\d.])(\d+)\.(\d{1,2})\b(?!\.\d)", decimal, t)
        # a dot between groups of three digits is a thousands separator outside English: 1.200 -> 1200
        t = re.sub(r"(?<=\d)\.(?=\d{3}\b)", "", t)
    t = re.sub(r"\d+", lambda m: _say_int(int(m.group(0)), lang) if len(m.group(0)) <= 7 else _digit_by_digit(m.group(0), lang), t)
    t = t.replace("&", " and ").replace("+", " plus ")
    t = re.sub(r"\s+,", ",", t)
    t = re.sub(r",(\s*,)+", ",", t)                         # ", ," from a bracket next to a comma
    t = re.sub(r",\s*([.!?:;])", r"\1", t)                  # ", ." from a bracket before a full stop
    return re.sub(r"\s+", " ", t).strip(" ,")
