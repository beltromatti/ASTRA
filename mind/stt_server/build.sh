#!/bin/zsh
# Build the speech-recognition helper (Parakeet on the Neural Engine) and put it where the mind looks first:
# mind/stt_server/bin/astra-stt. Needs Xcode's Swift toolchain (6.0+) and the network the first time (SwiftPM fetches FluidAudio, pinned
# in Package.resolved). The Parakeet model itself (~600 MB) is downloaded by the helper on its first start:
#     uv run python -m astra_mind.stt --fetch
# The compilation folder (900 MB: FluidAudio and what it builds on) is kept outside mind/, because tools/pacchetto.sh copies mind/
# into the app; ASTRA_STT_BUILD moves it elsewhere.
set -euo pipefail
cd "$(dirname "$0")"
SCRATCH="${ASTRA_STT_BUILD:-$HOME/Library/Caches/ASTRA/stt_server-build}"
swift build -c release --scratch-path "$SCRATCH"
mkdir -p bin
cp "$SCRATCH/release/astra-stt" bin/astra-stt
echo "built: $(pwd)/bin/astra-stt ($(du -h bin/astra-stt | cut -f1))"
