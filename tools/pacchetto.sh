#!/bin/zsh
# Costruisce l'app giocabile di ASTRA per macOS (Packaged/Mac/ASTRA.app): compila, cuoce i contenuti, impacchetta,
# poi mette la mente Python dentro l'app (Contents/Resources/mind: solo i sorgenti) e prepara i suoi dati in
# ~/Library/Application Support/ASTRA (la chiave e i modelli della voce sono collegamenti al repository, mai copie).
# L'editor deve essere chiuso. Log: Saved/Logs/package_last.log
# Uso: tools/pacchetto.sh [shipping|development]   (shipping: la build di rilascio, ottimizzata, senza console)
cd "$(dirname "$0")/.."
UE="/Users/Shared/Epic Games/UE_5.8"
OUT="$PWD/Packaged"
LOG="$PWD/Saved/Logs/package_last.log"
CONFIG=Development
[[ "${1:l}" == "shipping" ]] && CONFIG=Shipping
mkdir -p Saved/Logs
if pgrep -f "UnrealEditor.app/Contents/MacOS/UnrealEditor" >/dev/null; then echo "chiudi prima l'editor"; exit 1; fi
rm -rf "$OUT/Mac"          # (only our own build output: a previous app must not be picked up instead of this one)
"$UE/Engine/Build/BatchFiles/RunUAT.sh" BuildCookRun -project="$PWD/ASTRA.uproject" -platform=Mac -clientconfig=$CONFIG \
  -build -cook -stage -pak -iostore -package -archive -archivedirectory="$OUT" -nop4 -utf8output -unattended -NoCodeSign > "$LOG" 2>&1
if ! grep -q "BUILD SUCCESSFUL" "$LOG"; then echo "PACCHETTO FALLITO (log: $LOG)"; grep -E "Error|error:" "$LOG" | head -20; exit 1; fi
APP=$(find "$OUT" -maxdepth 3 -name "*.app" -type d | head -1)
[[ -z "$APP" ]] && { echo "app non trovata in $OUT"; exit 1; }
# la mente: solo i sorgenti (il suo ambiente Python nasce al primo avvio in Application Support, con uv)
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .cache mind/ "$APP/Contents/Resources/mind/"
# i dati della mente in Application Support: niente che punti al Desktop (macOS chiederebbe il permesso d'accesso alla
# Scrivania a ogni processo figlio dell'app). La chiave è una copia locale del .env (mai su git; rilancia lo script se
# la cambi), i modelli della voce una copia APFS (clonefile: nessuno spazio in più)
DATA="$HOME/Library/Application Support/ASTRA"
mkdir -p "$DATA/voice"
[[ -f .env ]] && { rm -f "$DATA/.env"; cp .env "$DATA/.env"; chmod 600 "$DATA/.env"; }
[[ -d voice/models ]] && { rm -rf "$DATA/voice/models"; cp -cR voice/models "$DATA/voice/models"; }
codesign --force --deep -s - "$APP" >/dev/null 2>&1 || true
# installata in ~/Applications (fuori dalle cartelle protette: Scrivania, Documenti, Download)
mkdir -p "$HOME/Applications"
rm -rf "$HOME/Applications/ASTRA.app"
cp -cR "$APP" "$HOME/Applications/ASTRA.app"
echo "pacchetto pronto ($CONFIG): $HOME/Applications/ASTRA.app ($(du -sh "$APP" | cut -f1))"
