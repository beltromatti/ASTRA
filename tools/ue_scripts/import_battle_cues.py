"""Import the bridge's sensor cues (art/_cache/audio, made by tools/art/battle_cues.py) as SoundWaves in /Game/ASTRA/Audio.
What the game does with them: AstraViewscreen.cpp (a warship's death rendered on the bridge's speakers). The game is tolerant of them being missing.
Run: uv run --with numpy --with soundfile --with scipy python tools/art/battle_cues.py
     tools/ue.py py "exec(open('/Users/beltromatti/Desktop/ASTRA/tools/ue_scripts/import_battle_cues.py').read())"
"""
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = os.path.join(ROOT, "art", "_cache", "audio")
DST = "/Game/ASTRA/Audio"
NAMES = ["SW_Sensor_Kill"]

tasks = []
for name in NAMES:
    path = os.path.join(SRC, name + ".wav")
    if not os.path.exists(path):
        print("missing", path)
        continue
    t = unreal.AssetImportTask()
    t.filename = path
    t.destination_path = DST
    t.destination_name = name
    t.automated = True
    t.replace_existing = True
    t.save = True
    tasks.append(t)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
done = []
for name in NAMES:
    sw = unreal.load_asset(f"{DST}/{name}")
    done.append((name, bool(sw), round(sw.get_editor_property("duration"), 2) if sw else None))
print("BATTLE_CUES_OK", done)
