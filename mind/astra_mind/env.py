"""The keys, from the .env file (the repository's, or the packaged mind's data folder): never printed."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# A packaged game launches the mind from inside its app bundle with ASTRA_HOME (the mind's own data: the key, the voice
# models, caches — in Application Support) and ASTRA_SAVED (the game's Saved folder, where the campaign lives). Run from
# the repository, both are the repository itself.
HOME = Path(os.environ["ASTRA_HOME"]) if os.environ.get("ASTRA_HOME") else REPO_ROOT
SAVED = Path(os.environ["ASTRA_SAVED"]) if os.environ.get("ASTRA_SAVED") else REPO_ROOT / "Saved"
CACHE = HOME / "cache" if os.environ.get("ASTRA_HOME") else REPO_ROOT / "mind" / ".cache"


@lru_cache(maxsize=1)
def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = HOME / ".env"
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


def reload_env() -> None:
    """The .env changed (the player entered or replaced the OpenRouter key in the game): read it again on the next use."""
    load_env.cache_clear()


def require(key: str) -> str:
    value = load_env().get(key, "")
    if not value:
        load_env.cache_clear()                    # (perhaps written since: the player's key arrives while the mind is running)
        value = load_env().get(key, "")
    if not value:
        raise RuntimeError(f"missing in the .env: {key}")
    return value
