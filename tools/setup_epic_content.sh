#!/bin/zsh
# Copies Epic's free template content used as placeholders (not in git: it can always be re-copied from the engine).
# - Manny/Quinn mannequins + animations (crew placeholders until the MetaHuman crew of M3)
set -e
ENGINE="/Users/Shared/Epic Games/UE_5.8"
PROJ="/Users/beltromatti/Desktop/ASTRA"
mkdir -p "$PROJ/Content/Characters"
rsync -a "$ENGINE/Templates/TemplateResources/High/Characters/Content/" "$PROJ/Content/Characters/"
echo "mannequins copied to Content/Characters"
