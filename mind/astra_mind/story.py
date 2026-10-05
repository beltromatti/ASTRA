"""The story's narrated cards: a line on a black screen, read aloud by the narrator in the player's language. The next card comes only when
the voice has finished, and the game holds still under them (`story_pause`), so nothing happens unseen while the screen is dark. Used by
the end of a chapter (finale.py) and the introduction (intro.py)."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

log = logging.getLogger("astra.story")

NARRATOR = "narrator"
NARRATOR_NAME = "Narrator"
NARRATOR_VOICE = "javert"           # (a deep, even voice; the war's other speakers are rarely heard with it)


async def wait_voice(voice_busy: Callable[[], float], extra: float = 0.0, limit: float = 45.0) -> None:
    """Until nobody is speaking (the line in the air, and what is queued behind it), then `extra` seconds."""
    await asyncio.sleep(0.4)
    t0 = time.monotonic()
    while voice_busy() > 0.2 and time.monotonic() - t0 < limit:
        await asyncio.sleep(0.25)
    await asyncio.sleep(extra)


async def tell(command: Callable[[str, dict[str, Any]], Awaitable[Any]], say: Callable[..., Awaitable[Any]],
               voice_busy: Callable[[], float], cards: list[tuple[str, str]], lang: str, *, pause: bool = True) -> None:
    """Show and read the cards: (title, text) pairs; the title is shown (a name, a place: never read), the text is shown and read. The game is
    paused for the whole telling and goes on after it, whatever happens in between."""
    if pause:
        await _cmd(command, "story_pause", {"on": True})
    try:
        for title, text in cards:
            text = (text or "").strip()
            hold = 2.0 + len(text) / 13.0 + 3.0           # (shown at least as long as it takes to read; the voice usually ends sooner)
            await _cmd(command, "story_card", {"title": title, "sub": text, "hold": hold, "black": True})
            await asyncio.sleep(1.0)                       # (the card fades in before the voice)
            if text:
                try:
                    await say(NARRATOR, text, lang, "measured")
                except Exception:  # noqa: BLE001
                    log.exception("the narrator could not read a card")
                await wait_voice(voice_busy, 1.0)
            else:
                await asyncio.sleep(3.0)
    finally:
        if pause:
            await _cmd(command, "story_pause", {"on": False})


async def _cmd(command: Callable[[str, dict[str, Any]], Awaitable[Any]], name: str, args: dict[str, Any]) -> None:
    try:
        await command(name, args)
    except Exception:  # noqa: BLE001
        log.warning("story command %s failed", name)
