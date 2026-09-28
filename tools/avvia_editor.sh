#!/bin/zsh
# Avvia l'editor di ASTRA in background con il server MCP attivo.
# -unattended: niente finestre di dialogo bloccanti e niente limite a 3 fps quando lo schermo è bloccato
# (UEditorEngine::ShouldThrottleCPUUsage), così catture e misure restano affidabili anche senza utente.
UE="/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app"
PROJ="/Users/beltromatti/Desktop/ASTRA/ASTRA.uproject"
# the MCP server does not retry if its port is still held by a previous instance (LISTEN or TIME_WAIT, which
# lasts ~30 s on macOS): wait until no socket at all uses port 8000
for i in {1..90}; do netstat -an -p tcp 2>/dev/null | grep -qE '[.:]8000 ' || break; sleep 1; done
open -g -a "$UE" --args "$PROJ" -ModelContextProtocolStartServer -unattended "$@"
for i in {1..90}; do
  sleep 2
  if curl -s -m 2 -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -d '{}' | grep -qE "200|400|406"; then
    echo "MCP pronto dopo $((i*2)) s"; exit 0
  fi
done
echo "MCP non raggiungibile" >&2; exit 1
