# Resuming development after the storage cleanup

Development was paused at the owner's request on 7 October 2026. The installed game in `/Applications/ASTRA.app`, its current campaign,
OpenRouter key and voice data in Application Support, and the deployed website are independent of these development folders.

From this Mac, prepare both ASTRA and its sibling `astra-site` checkout with one command:

```sh
~/Desktop/ASTRA/tools/resume-development.sh
```

This restores the checked-out Content assets from the existing local Git LFS objects, installs the exact Python and Node dependencies
from the lockfiles, and rebuilds the Unreal editor module and plugin. The first editor opening regenerates shaders and derived caches.
It does not start a mind, open a campaign, deploy the website, replace the installed game, or change a credential.

`--dry-run` shows the commands without changing files; `--no-build` restores dependencies/assets while deferring the editor compilation.
After preparing the checkout, use `tools/avvia_editor.sh` for Unreal, or `npm run dev` inside `astra-site` for the website.

## What was removed and how it returns

| Material | Recovery |
|---|---|
| Project/plugin binaries, Intermediate, cook/staging/shader caches | The default command rebuilds the editor; normal editor/package operations generate their caches |
| Development Python environments and bytecode | `uv sync --frozen`, included in the default command |
| Website node_modules, .next and TypeScript build cache | `npm ci`, included in the default command; `npm run dev` or `npm run build` regenerates Next's output |
| Duplicate working copies of Content LFS assets | `git lfs checkout`, included in the default command; their verified objects remain local |
| Old helper worktrees | Restore one explicitly, as below; the default command keeps them archived |
| Published macOS ZIPs and duplicate packaged apps | `tools/resume-development.sh --release v0.1.1-alpha` downloads and checks the exact published archive; new packages use `tools/pacchetto.sh` |
| Downloaded VSCO sample-library clone | `tools/resume-development.sh --samples`, using its recorded revision and instrument selection |

The original Blender exports, downloaded art sources, generated creative assets, current developer campaign and screenshots, design
documents, code, release metadata, credentials and Git history were retained. Shared Unreal/Xcode installations, global caches and the
player's installed-game data were outside the cleanup scope.

## Historical worktree recovery

All fifteen old worktree heads were already ancestors of main. Three also had local changes, which were preserved before removal:

- `agent-a56b88eaae19a3600`: Space Life C++ changes and its design notes.
- `agent-a744b27da57aae0d4`: boarding C++/Python changes and its design notes.
- `agent-a7d3df7e6454139e6`: an untracked `AstraWrecks.h`.

The tracked changes have private Git snapshot references and inspectable patches. Non-reproducible ignored/untracked worktree material,
including historical test results, logs, configurations and images, is stored as verified, deduplicated gzip blobs. Identical Epic template
content, known build outputs and Python environments were excluded because they are reproducible. Unknown material was preserved.

To recover a particular old checkout with its changes and evidence:

```sh
tools/resume-development.sh --worktree agent-a56b88eaae19a3600
```

The original branch is retained; its local snapshot is reapplied and evidence files are restored with hash checks. This does not merge the
experimental changes into main. Generated caches/environments are rebuilt when needed. The restoration refuses to overwrite an existing
worktree. Restore old worktrees only when inspecting their history; they are not needed for current development.

The private `.pause/state.json`, `.pause/blobs/`, patches and `refs/astra/pause/*` references are required for this local recovery. Keep
`.pause/` and `.git/`; they are deliberately excluded from public Git commits. Validate the compressed evidence with:

```sh
/opt/homebrew/bin/python3.13 tools/pause_storage.py verify
```

Source backups and the cleanup/restore commands were preserved; the current project folders intentionally need preparation before opening
the Unreal editor. The normal installed game remains ready to play throughout the development pause.
