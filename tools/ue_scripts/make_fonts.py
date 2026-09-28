"""ASTRA UI fonts as runtime Unreal fonts (docs/STILE.md §7): Barlow Condensed for titles/labels, IBM Plex Mono for data.
Imports the TTFs (OFL, art/_downloads/fonts) as FontFace assets and builds composite fonts on top. Idempotent.

  /Game/ASTRA/UI/Fonts/F_ASTRA_Title   Barlow Condensed SemiBold (Regular = SemiBold, Medium, Light = Regular)
  /Game/ASTRA/UI/Fonts/F_ASTRA_Mono    IBM Plex Mono (Regular, Bold = Medium)

tools/ue.py pyfile tools/ue_scripts/make_fonts.py
"""
import json
import os

import unreal

eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()
SRC = "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts"
DST = "/Game/ASTRA/UI/Fonts"
FACES = {"FF_BarlowCondensed_SemiBold": "BarlowCondensed-SemiBold.ttf", "FF_BarlowCondensed_Medium": "BarlowCondensed-Medium.ttf",
         "FF_BarlowCondensed_Regular": "BarlowCondensed-Regular.ttf", "FF_IBMPlexMono_Regular": "IBMPlexMono-Regular.ttf",
         "FF_IBMPlexMono_Medium": "IBMPlexMono-Medium.ttf"}
log = []

tasks = []
for asset_name, ttf in FACES.items():
    if eal.does_asset_exist(f"{DST}/{asset_name}"):
        continue
    t = unreal.AssetImportTask()
    t.filename = os.path.join(SRC, ttf)
    t.destination_path = DST
    t.destination_name = asset_name
    t.automated = True
    t.replace_existing = True
    t.save = True
    t.factory = unreal.FontFileImportFactory()
    tasks.append(t)
if tasks:
    tools.import_asset_tasks(tasks)
for asset_name in FACES:
    face = eal.load_asset(f"{DST}/{asset_name}")
    if not isinstance(face, unreal.FontFace):
        raise RuntimeError(f"{asset_name} did not import as a FontFace: {face}")
    face.set_editor_property("loading_policy", unreal.FontLoadingPolicy.INLINE)   # packaged inside the asset
    eal.save_loaded_asset(face, only_if_is_dirty=False)
log.append("faces ok")


def composite(name, entries):
    path = f"{DST}/{name}"
    font = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(name, DST, unreal.Font, unreal.FontFactory())
    font.set_editor_property("font_cache_type", unreal.FontCacheType.RUNTIME)
    fonts = ",".join(f'(Name="{n}",Font=(FontFaceAsset="/Script/Engine.FontFace\'{DST}/{f}.{f}\'"))' for n, f in entries)
    cf = unreal.CompositeFont()
    cf.import_text(f"(DefaultTypeface=(Fonts=({fonts})),FallbackTypeface=(Typeface=(Fonts=((Name=\"Regular\",Font=(FontFaceAsset="
                   f"\"/Script/Engine.FontFace'/Engine/EngineFonts/Faces/DroidSansFallback.DroidSansFallback'\")))),"
                   f"ScalingFactor=1.000000),SubTypefaces=,bEnableAscentDescentOverride=True)")
    font.set_editor_property("composite_font", cf)
    font.set_editor_property("legacy_font_size", 24)
    eal.save_loaded_asset(font, only_if_is_dirty=False)
    return font.get_editor_property("composite_font").export_text()[:200]


log.append(composite("F_ASTRA_Title", [("Regular", "FF_BarlowCondensed_SemiBold"), ("Medium", "FF_BarlowCondensed_Medium"),
                                        ("Light", "FF_BarlowCondensed_Regular")]))
log.append(composite("F_ASTRA_Mono", [("Regular", "FF_IBMPlexMono_Regular"), ("Bold", "FF_IBMPlexMono_Medium")]))
print(json.dumps(log, indent=1))
