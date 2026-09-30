#!/bin/bash
# Builds and runs the checks that decide whether the MetalFX plugin's Metal side still works on this machine (after a macOS or
# Xcode update, on another Mac): the plugin's own Metal code against synthetic Unreal-like frames (probe_core), its motion kernel
# against a geometric ground truth (probe_motion), the end-to-end scene (probe_e2e) and the hazard-tracking ordering (probe_hazard).
# Does not start Unreal. About a minute; keep the GPU otherwise idle. Usage: tools/metalfx_probe/run_all.sh
set -uo pipefail
cd "$(dirname "$0")"
./build.sh probe_core probe_motion probe_e2e probe_hazard > /dev/null || { echo "BUILD FAILED"; exit 1; }
status=0
echo "== probe_core (the plugin's Metal code, pipelined frames, bad frames refused)"
./.build/probe_core 2>&1 | grep -v "core log" | grep -E "FAIL|PASS|PSNR|frames completed" || status=1
./.build/probe_core > /dev/null 2>&1 || { echo "probe_core FAILED"; status=1; }
echo "== probe_motion (motion kernel vs geometric truth)"
./.build/probe_motion | tail -3 || status=1
./.build/probe_motion > /dev/null 2>&1 || { echo "probe_motion FAILED"; status=1; }
echo "== probe_e2e (3D scene: MetalFX with the kernel's motion vs bilinear, zero and negated motion)"
./.build/probe_e2e 48 55 | tail -4
echo "== probe_hazard (separate command buffers ordered by hazard tracking: tracked must show no race)"
./.build/probe_hazard 100 | grep -E "^(tracked|untracked)"
if ./.build/probe_hazard 60 | grep -E "^tracked .*RACE" > /dev/null; then echo "probe_hazard FAILED: a tracked texture raced"; status=1; fi
[ "$status" -eq 0 ] && echo "ALL OK" || echo "SOMETHING FAILED"
exit $status
