"""Caricamento delle chiavi dal file .env nella radice del repository (mai stampate)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    for key, value in os.environ.items():
        if key.isupper() and value:
            values.setdefault(key, value)
    return values


def require(key: str) -> str:
    value = load_env().get(key, "")
    if not value:
        raise RuntimeError(f"Chiave mancante nel .env: {key}")
    return value
