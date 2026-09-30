#!/bin/zsh
# Build the speech-recognition helper (Parakeet on the Neural Engine) and put it where the mind looks first:
# mind/stt_server/bin/astra-stt. Needs Xcode's Swift toolchain (6.0+) and the network the first time (SwiftPM fetches FluidAudio, pinned
# in Package.resolved). The Parakeet model itself (~600 MB) is downloaded by the helper on its first start:
#     uv run python -m astra_mind.stt --fetch
set -euo pipefail
cd "$(dirname "$0")"
swift build -c release
mkdir -p bin
cp .build/release/astra-stt bin/astra-stt
echo "built: $(pwd)/bin/astra-stt ($(du -h bin/astra-stt | cut -f1))"
