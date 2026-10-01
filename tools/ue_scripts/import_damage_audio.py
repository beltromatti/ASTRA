"""Import the damage sounds (art/_cache/audio/SW_*.wav of the list below, made by tools/art/damage_sounds.py) as SoundWaves in /Game/ASTRA/Audio,
the loops flagged as looping. What the game does with them: AstraDamageFx.cpp (a fire's roar, air venting, a containment field's hum, the suppression's
hiss near the Captain; a bulkhead slamming; a blow going off inside; a hole opening). The game is tolerant of any of them being missing.
Run: uv run --with numpy --with soundfile --with scipy python tools/art/damage_sounds.py
     tools/ue.py py "exec(open('tools/ue_scripts/import_damage_audio.py').read())"
"""
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
SRC = globals().get("SRC", os.path.join(ROOT, "art", "_cache", "audio"))
DST = "/Game/ASTRA/Audio"
NAMES = ["SW_Fire_Loop", "SW_Vent_Loop", "SW_Field_Hum", "SW_Suppress_Loop", "SW_Bulkhead_Slam", "SW_Blast_Inside", "SW_Decompression"]
LOOPS = {"SW_Fire_Loop", "SW_Vent_Loop", "SW_Field_Hum", "SW_Suppress_Loop"}

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
for t in tasks:
    name = os.path.splitext(os.path.basename(t.filename))[0]
    sw = unreal.load_asset(f"{DST}/{name}")
    if sw and name in LOOPS:
        sw.set_editor_property("looping", True)
        unreal.EditorAssetLibrary.save_loaded_asset(sw, only_if_is_dirty=False)
    done.append((name, bool(sw), round(sw.get_editor_property("duration"), 2) if sw else None))
print("DAMAGE_AUDIO_OK", done)
