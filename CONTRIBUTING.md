# Contributing to ASTRA

Thanks for looking. ASTRA is a concept, built in the open: a war in space where every character is a mind of its own. Bug reports, playtest
notes, fixes and ideas are all welcome.

## Playing and reporting

- Download the latest release, start it, paste your OpenRouter key when it asks, and play. The in-game introduction shows the basics; F1
  also works on PC; K shows every control on all platforms.
- Found a bug? Open an issue with what you did, what you expected and what happened. Attach the logs if you can:
  - macOS: `astra-mind.log` (the crew's log) in `~/Library/Application Support/Epic/ASTRA/Saved/Logs/`, and the crash report macOS
    offers if the game closes by itself.
  - Windows: `ASTRA\Saved\Logs\astra-mind.log` next to `ASTRA.exe`.
- Never paste your OpenRouter key in an issue. The logs never contain it.

## Building from source

You need **Unreal Engine 5.8.3**, **uv** (docs.astral.sh/uv) and git with **git-lfs** (the assets are in LFS).

1. `git lfs install && git clone https://github.com/beltromatti/ASTRA.git`
2. Copy `.env.example` to `.env` and put your OpenRouter key in `OPENROUTER_API_KEY` (only this one is needed to play).
3. Copy Epic's mannequins into the project (they are not in git): `tools/setup_epic_content.sh` on macOS,
   `tools\windows\Setup-EpicContent.ps1` on Windows.
4. Open `ASTRA.uproject` (Unreal builds the module the first time) or build it from the command line, then press Play on `L_Bridge`.
   The game starts the crew's mind by itself (`mind/`, Python 3.13 through uv); the first start downloads the voice and listening models.

Packaging: `tools/pacchetto.sh` on macOS, `tools/windows/Pacchetto-Windows.ps1` on Windows (Unreal cannot build Windows from a Mac).

## Working on the code

- Read [CLAUDE.md](CLAUDE.md): the principles and the conventions hold for people as much as for coding agents. The most important one:
  the characters' intelligence comes from their prompts, their context and their tools, never from code that filters what a model says.
- English everywhere in the game and the code. Most of the design documents in `docs/` are in Italian; new ones are in English.
- Keep it portable (`python3 tools/portability.py`) and measured: the game must hold 60 fps in space on a MacBook Air M4.
- Test what you change in the game, as a player would. The harness (`tools/play.py`), the war bench (`tools/war.py`) and the mind's tests
  (`mind/bench`) are there for that.
- One topic per pull request, small commits, English commit messages.
- Third-party assets only with a licence that allows redistribution, registered in `docs/licenze.csv` and in [CREDITS.md](CREDITS.md).

By contributing you agree that your work is published under the project's [MIT licence](LICENSE).
