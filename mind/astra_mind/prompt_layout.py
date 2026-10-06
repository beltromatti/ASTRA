"""Keep instructions cacheable while carrying every changing fact in the current turn.

This rearranges prompt data, not model output. A named reference stays at the original
location; its full value appears once in the current context. No summarization or clipping.
"""
from __future__ import annotations

from typing import Any


def cached_prompt(template: str, fields: dict[str, Any], dynamic: tuple[str, ...]) -> tuple[str, str]:
    stable = dict(fields)
    blocks = []
    for name in dynamic:
        stable[name] = f"[read {name} in the current context below]"
        blocks.append(f"{name}\n{fields[name]}")
    return template.format(**stable), "[Current context]\n" + "\n\n".join(blocks) + "\n[end of current context]"
