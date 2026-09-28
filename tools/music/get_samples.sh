#!/bin/zsh
# The orchestral samples for the score: VSCO 2 Community Edition (CC0), only the instruments the score uses.
cd "$(dirname "$0")/../../art/_cache" || exit 1
[[ -d vsco2 ]] || git clone --depth 1 --filter=blob:none --sparse https://github.com/sgossner/VSCO-2-CE.git vsco2
cd vsco2 && git sparse-checkout set "Strings/Violin Section" "Strings/Viola Section" "Strings/Cello Section" "Strings/Solo Contrabass" \
  "Strings/Harp" "Brass/F Horn" "Brass/Tenor Trombone" "Brass/Tuba" "Brass/Trumpet" "Percussion" "Woodwinds/Flute" "Woodwinds/Clarinet"
echo "samples ready: $(du -sh . | cut -f1)"
