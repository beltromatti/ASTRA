#!/bin/zsh
# Rebuild the C++ module with the editor closed: save everything, quit the editor (and the mind), build, relaunch the
# editor and wait for its MCP server. Usage: tools/ricompila.sh [--no-launch]
cd "$(dirname "$0")/.."
PY=/opt/homebrew/bin/python3.13
EDITOR_BIN="UnrealEditor.app/Contents/MacOS/UnrealEditor"
# the editor (or a game the harness started): not the commandlets the helpers run from the same binary (-run=...), which do not hold this checkout's module
# (this checkout's only: a helper's editor or test game in its own worktree has its own binaries, 5 Oct: the build waited four minutes for VFX-2's game)
editor_up() { pgrep -fl "$EDITOR_BIN" | grep -v -- "-run=" | grep -F "$PWD/ASTRA.uproject" | grep -q .; }
# a game started by the playtest harness runs the same binary: close it first
pgrep -f "astra_harness_port=8770" >/dev/null && $PY tools/play.py quit >/dev/null 2>&1
if editor_up; then
  $PY tools/ue.py pie stop >/dev/null 2>&1
  $PY tools/ue.py py "import unreal
unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
unreal.SystemLibrary.quit_editor()" >/dev/null 2>&1
fi
pkill -f astra-mind
for i in {1..120}; do editor_up || break; sleep 2; done
if editor_up; then echo "l'editor non si chiude"; exit 1; fi
LOG=Saved/Logs/build_last.log
mkdir -p Saved/Logs
"/Users/Shared/Epic Games/UE_5.8/Engine/Build/BatchFiles/Mac/Build.sh" ASTRAEditor Mac Development -Project="$PWD/ASTRA.uproject" -WaitMutex > "$LOG" 2>&1
grep -E "error|warning: " "$LOG" | head -20
if ! grep -q "Result: Succeeded" "$LOG"; then echo "BUILD FALLITA (log: $LOG)"; exit 1; fi
echo "build ok"
[[ "$1" == "--no-launch" ]] && exit 0
tools/avvia_editor.sh >/dev/null 2>&1 &
for i in {1..90}; do $PY tools/ue.py stato 2>/dev/null | grep -q "MCP attivo" && { echo "editor pronto"; exit 0; }; sleep 5; done
echo "editor avviato ma MCP non risponde"; exit 1
