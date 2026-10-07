# ASTRA: instructions for coding agents

ASTRA is an Unreal Engine 5.8 game in C++ with a Python service, the **mind** (`mind/`), that gives every character a language model, a
voice and real tools. This file is for AI coding agents (Claude Code and the like) working in this repository; people start from
[CONTRIBUTING.md](CONTRIBUTING.md).

## Read first

- [docs/STATO.md](docs/STATO.md): where the project stands and what comes next. The section at the top is the current one.
- [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md): the modules and their contracts. [docs/PIANO.md](docs/PIANO.md): the plan.
  [docs/BIBBIA.md](docs/BIBBIA.md): the world (names, factions, ships). [docs/STILE.md](docs/STILE.md): the look and the sound.
- Most of `docs/` was written in Italian and stays so. Everything new is written in English: documents, code, comments, commit messages.

## Principles

1. **Intelligence by prompt and tools, never by code filters.** The characters think with language models. Never clip, regex or rule-filter
   what a model says or decides. Shape behaviour through the prompt, the context the model reads and the tools it can call. Code does the
   mechanics (physics, damage, the ship's state, timing), not the judgment.
2. **English in the game and the code.** Lore names, places, ships, factions, signs, screens, logs, assets, identifiers, comments. The only
   exception is speech: the characters answer in the language the player speaks to them (seven languages have voices: en, it, es, fr, de,
   pt, nl). Proper names stay in English in every language.
3. **Measured, not felt.** Visual work is checked with screenshots against the checklist in `docs/ricerca/08`; performance against the gates
   in `docs/ricerca/11`; the minds against the bench in `docs/ricerca/09` and `mind/bench`.
4. **The reference machine is a fanless MacBook Air M4 with 16 GB**: 60 fps in space, 45 fps or more indoors once it is hot, the game under
   9 GB of memory. Windows (DX12, SM6) is the main platform for players: keep every change portable and run `tools/portability.py`.
5. **No friction for the player.** A non-developer installs the game and plays it: every failure (no key, no credit, no network, no
   microphone) is told on screen in plain words, and nothing needs a terminal.

## Layout

| Path | What it is |
|---|---|
| `ASTRA.uproject`, `Config/`, `Content/`, `Source/ASTRA/`, `Plugins/` | the Unreal project (the game module is `Source/ASTRA`, ~240 files) |
| `mind/` | the mind: `astra_mind/` (server, crew, war, story, voice), `bench/` (tests), `stt_server/` (speech recognition helper for Apple Silicon) |
| `data/war/` | ship classes and scenarios of the war (`tools/war.py embed` compiles `classes.json` into the game) |
| `art/`, `tools/art/` | the art pipeline: Blender generators, texture packers, import scripts |
| `tools/` | the harness, benches, build and release scripts (`tools/windows/` for Windows) |
| `docs/` | design, status, research, licences |

## Build and run

- On the maintainer's Mac the development checkout was paused on 7 October 2026. Run `tools/resume-development.sh` before opening Unreal:
  Content LFS payloads were replaced with pointers while their verified local objects remain in `.git/lfs`. See
  [docs/DEVELOPMENT-PAUSE.md](docs/DEVELOPMENT-PAUSE.md) for dependency preparation and historical-worktree recovery. Do not delete `.pause/` or `.git/`.

- Unreal Engine 5.8.3. On a Mac there is no Live Coding: close the editor, build with
  `tools/ricompila.sh --no-launch` (it prints `build ok` or `BUILD FALLITA` and the errors; the full log is `Saved/Logs/build_last.log`).
  The game module builds as a unity build with `-Wshadow -Werror`: a name in an anonymous namespace of one file can break another file of
  the same unity blob, so give file-level names distinctive names.
- The mind: `cd mind && uv run astra-mind` (Python 3.13 through `uv`). The game starts it by itself when nothing listens on its port.
  The OpenRouter key is in `.env` (`OPENROUTER_API_KEY`, see `.env.example`); a packaged game asks the player for it on its first start.
- Packages: `tools/pacchetto.sh [development|shipping]` (macOS), `tools/windows/Pacchetto-Windows.ps1` (on a Windows PC: Unreal cannot build
  Windows from a Mac), `tools/release_mac.sh <version>` (the signed, notarized macOS release; its keys come from `.release.env`).

## Tests

- `tools/play.py`: the playtest harness. It launches the game with `-astra_harness` on port 8770 and drives it over HTTP
  (`launch`, `say`, `cmd`, `key`, `shot`, `state`, `timeline`, `quit`). It keeps its own `Saved_Harness` folder (never the player's
  campaign) and the game ignores the keyboard and mouse of whoever is using the computer. If it does not answer, a crash reporter left by a
  crash may hold the port: end it.
- `tools/war.py`: the war bench, headless battles from fixed seeds (`suite`, `classes`, `--only`, `--tag`, `--exec "astra.war.tune ..."`).
- `mind/bench/*_unit.py`: the mind's tests (`cd mind && uv run python bench/<name>.py`). They run without a network or a model.
- `UnrealEditor-Cmd ASTRA.uproject -run=AstraMindLaunch -nullrhi -unattended -nosound -nopause`: how the game finds and starts the mind
  on every system.
- Test what you change in the game itself, as a player would, and look at it: a screenshot says more than a log.

## Rules

- Small, frequent commits on `main` with English messages, and the attribution line your tool requires.
- Secrets live only in `.env` and `.release.env` (both ignored by git; the hook in `.githooks/` refuses keys). Never print a key's value.
- Every third-party asset goes in [docs/licenze.csv](docs/licenze.csv) (source, author, licence, URL, changes) and the credits. Raw
  third-party files stay out of git (`Content/ThirdParty/`, `art/_downloads/`); ASTRA's own reworked assets live in `Content/ASTRA/`.
- Spend on AI only through OpenRouter, with cheap and fast models (`mind/astra_mind/models.py` has the roles and their fallbacks).
- Update `docs/STATO.md` after each meaningful step: it is how the next session picks the work up.

## The maintainer's machine

These notes apply to sessions on the project owner's Mac (Mattia Beltrami, who directs the vision; the agent directs the technical work end
to end and challenges ideas when there is a better way). Reply to him in Italian.

- The project is `~/Desktop/ASTRA`; Unreal Engine 5.8.3 is in `/Users/Shared/Epic Games/UE_5.8`; Xcode 26.2 (do not update it: 26.4 and
  later break UE 5.8). Tools use `/opt/homebrew/bin/python3.13` or `uv` (the python.org build lacks SSL certificates). Blender 5.2.2, git-lfs,
  uv and espeak-ng are installed; the GitHub CLI is signed in as `beltromatti`.
- The editor is driven through Epic's MCP server (`127.0.0.1:8000/mcp`, started with `-ModelContextProtocolStartServer`), the project's
  `AgentPythonTools` toolset and Unreal's remote execution as a fallback.
- He has granted broad, standing permission for this project (docs/COSA_MI_SERVE.md §6): open-source installs, free downloads from the
  listed sources (ask above 5 GB), claiming free Fab items, accepting gated model licences, his signed-in sessions in the built-in browser.
  Never purchases. Never: creating accounts, typing passwords or one-time codes, payments or money transfers, changes to system or security
  settings, getting around CAPTCHAs or Cloudflare. If an account is needed, write it in `docs/RICHIESTE.md` and carry on with something else.
- Budget: nothing for anything that is not AI. AI only through OpenRouter on a limited credit: keep the count in `docs/STATO.md` and warn in
  `docs/RICHIESTE.md` below 3 dollars.
