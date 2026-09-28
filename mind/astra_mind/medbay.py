"""The Medbay's wounded as voices: each patient speaks with a voice of their own, picked from the Pocket TTS catalogue
voices no officer or enemy commander uses (by gender, stable for the same person)."""
from __future__ import annotations

import zlib
from typing import Any

# free voices, clearest first (docs/bench/voci_casting_2026-09-28.md)
FREE_VOICES = {"f": ["eponine", "fantine", "cosette", "azelma", "anna", "estelle"],
               "m": ["michael", "juergen", "paul", "marius", "stuart_bell"]}


def patient_voice(patient: dict[str, Any]) -> str:
    pool = FREE_VOICES.get(patient.get("gender", "m"), FREE_VOICES["m"])
    return pool[zlib.crc32(patient.get("name", "").encode("utf-8")) % len(pool)]
