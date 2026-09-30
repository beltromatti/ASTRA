#!/bin/bash
# Builds the MetalFX probes (standalone Objective-C++ tools, no Unreal involved).
# Usage: tools/metalfx_probe/build.sh [name ...]   (default: all .mm files in this folder)
# Output: tools/metalfx_probe/.build/<name>
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .build
if [ "$#" -gt 0 ]; then names=("$@"); else names=(); for f in *.mm; do names+=("${f%.mm}"); done; fi
for n in "${names[@]}"; do
	echo "== building $n"
	clang++ -std=c++17 -O2 -fobjc-arc -Wall -Wno-unused-function -Wno-deprecated-declarations \
		-framework Foundation -framework Metal -framework MetalFX -framework CoreFoundation \
		"$n.mm" -o ".build/$n"
done
