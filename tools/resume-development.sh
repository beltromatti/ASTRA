#!/bin/bash
# Restore ASTRA and its sibling website after development storage was paused.
# Default: local LFS assets, locked Python/Node environments and the editor module.
set -euo pipefail
cd "$(dirname "$0")/.."
ASTRA_RESUME_ROOT="$PWD"
ASTRA_RESUME_PY="/opt/homebrew/bin/python3.13"
ASTRA_RESUME_BUILD=1
ASTRA_RESUME_DRY=0
ASTRA_RESUME_ACTION=default
ASTRA_RESUME_ARGUMENT=''
while (($#)); do
  case "$1" in
    --dry-run) ASTRA_RESUME_DRY=1 ;;
    --no-build) ASTRA_RESUME_BUILD=0 ;;
    --worktree) ASTRA_RESUME_ACTION=worktree; ASTRA_RESUME_ARGUMENT="${2:?provide a preserved worktree name}"; shift ;;
    --samples) ASTRA_RESUME_ACTION=samples ;;
    --release)
      ASTRA_RESUME_ACTION=release
      ASTRA_RESUME_ARGUMENT=v0.1.1-alpha
      if [[ "${2:-}" == v* ]]; then ASTRA_RESUME_ARGUMENT="$2"; shift; fi
      [[ "$ASTRA_RESUME_ARGUMENT" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?$ ]] || exit 2 ;;
    *) echo "Usage: $0 [--dry-run] [--no-build] [--worktree NAME | --samples | --release TAG]"; exit 2 ;;
  esac
  shift
done
run() {
  if ((ASTRA_RESUME_DRY)); then printf 'Would run:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}
case "$ASTRA_RESUME_ACTION" in
  worktree) run "$ASTRA_RESUME_PY" tools/pause_storage.py worktree "$ASTRA_RESUME_ARGUMENT"; exit ;;
  samples) run "$ASTRA_RESUME_PY" tools/pause_storage.py samples; exit ;;
  release)
    run mkdir -p Packaged/Release
    run gh release download "$ASTRA_RESUME_ARGUMENT" --repo beltromatti/ASTRA --pattern "ASTRA-${ASTRA_RESUME_ARGUMENT#v}-macOS-AppleSilicon.zip" --pattern "ASTRA-${ASTRA_RESUME_ARGUMENT#v}-macOS-AppleSilicon.zip.sha256" --dir Packaged/Release --skip-existing
    if ((ASTRA_RESUME_DRY)); then echo 'Would verify the downloaded SHA-256 checksum.'
    else (cd Packaged/Release && shasum -a 256 -c "ASTRA-${ASTRA_RESUME_ARGUMENT#v}-macOS-AppleSilicon.zip.sha256"); fi
    exit ;;
esac
run git lfs checkout
if [[ ! -d Content/Characters ]]; then run tools/setup_epic_content.sh; fi
run uv sync --directory mind --frozen --python "$ASTRA_RESUME_PY"
run uv sync --directory voice --frozen --python "$ASTRA_RESUME_PY"
if [[ ! -x mind/stt_server/bin/astra-stt ]]; then run mind/stt_server/build.sh; fi
if ((ASTRA_RESUME_BUILD)); then
  run '/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh' ASTRAEditor Mac Development "-Project=$ASTRA_RESUME_ROOT/ASTRA.uproject" -WaitMutex
fi
if [[ -f ../astra-site/package-lock.json ]]; then
  (cd ../astra-site && run npm ci)
fi
if ((ASTRA_RESUME_DRY)); then echo 'Restore plan shown; no files changed.'
else echo 'Restore completed. Launch the editor with tools/avvia_editor.sh; use npm run dev in astra-site for the website.'; fi
