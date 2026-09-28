#!/bin/zsh
# Automated performance capture: runs the game standalone (uncooked, editor binaries) on a map,
# records N frames with the CSV profiler, then prints the summary (tools/perf/csv_summary.py).
# Usage: tools/perf/run_perf.sh [map] [frames] [resX] [resY] [extra args...]
set -e
setopt nullglob
PROJ="/Users/beltromatti/Desktop/ASTRA"
MAP="${1:-/Game/ASTRA/Maps/L_CorridorTest}"
FRAMES="${2:-1500}"
RX="${3:-1920}"; RY="${4:-1080}"
shift $(( $# < 4 ? $# : 4 ))
BIN="/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor"
OUTDIR="$HOME/Library/Application Support/Epic/UnrealEngine/5.8/Saved/Profiling/CSV"  # where -game writes on Mac
mkdir -p "$OUTDIR" "$PROJ/Saved/Logs"
before=$(ls -1t "$OUTDIR"/*.csv 2>/dev/null | head -1)
"$BIN" "$PROJ/ASTRA.uproject" "$MAP" -game -windowed -ResX=$RX -ResY=$RY -unattended -nosound -NoVerifyGC -astra_campaign=new \
  -csvCaptureFrames=$FRAMES -ExitAfterCsvProfiling -csvGpuStats -csvMetadata="map=$MAP,res=${RX}x${RY}" \
  -ExecCmds="t.MaxFPS 0, r.VSync 0${ASTRA_PERF_CMDS:+, $ASTRA_PERF_CMDS}" "$@" > "$PROJ/Saved/Logs/perf_last_stdout.log" 2>&1 || true
after=$(ls -1t "$OUTDIR"/*.csv 2>/dev/null | head -1)
if [[ -z "$after" || "$after" == "$before" ]]; then echo "no CSV produced" >&2; exit 1; fi
/opt/homebrew/bin/python3.13 "$PROJ/tools/perf/csv_summary.py" "$after"
