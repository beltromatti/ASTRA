#!/usr/bin/env python3
"""Crea il progetto Unreal ASTRA (C++) nella radice del repository a partire dal
template First Person di UE 5.8, come fa la procedura guidata "New Project":
copia, rinomina modulo e classi (TP_FirstPerson -> ASTRA), rimuove le varianti
Shooter/Horror, aggiunge i reindirizzamenti per i Blueprint e applica la
configurazione di ASTRA (Mac M4 16 GB, MCP ufficiale, Python, prestazioni).

Uso:  /opt/homebrew/bin/python3.13 tools/crea_progetto.py
"""
import json
import os
import shutil
import sys
import uuid

UE = "/Users/Shared/Epic Games/UE_5.8"
TEMPLATE = f"{UE}/Templates/TP_FirstPerson"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD, NEW = "TP_FirstPerson", "ASTRA"


def die(msg: str) -> None:
    print("ERRORE:", msg)
    sys.exit(1)


def main() -> None:
    if os.path.exists(os.path.join(ROOT, f"{NEW}.uproject")):
        die("il progetto esiste già")

    # 1) copia di Config, Content, Source
    for d in ("Config", "Content", "Source"):
        dst = os.path.join(ROOT, d)
        if os.path.exists(dst):
            die(f"{dst} esiste già")
        shutil.copytree(os.path.join(TEMPLATE, d), dst)
    for f in ("Config/TemplateDefs.ini", "Config/config.ini"):
        p = os.path.join(ROOT, f)
        if os.path.exists(p):
            os.remove(p)

    # 2) rimozione delle varianti Shooter / Horror (codice e contenuti)
    for base in (f"Source/{OLD}", "Content", "Content/__ExternalActors__", "Content/__ExternalObjects__"):
        b = os.path.join(ROOT, base)
        if not os.path.isdir(b):
            continue
        for name in os.listdir(b):
            if name.startswith("Variant_"):
                shutil.rmtree(os.path.join(b, name))

    # 3) rinomina di file e cartelle del codice
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "Source"), topdown=False):
        for n in filenames + dirnames:
            if OLD in n:
                os.rename(os.path.join(dirpath, n), os.path.join(dirpath, n.replace(OLD, NEW)))

    # 4) sostituzione del testo nel codice
    for dirpath, _, filenames in os.walk(os.path.join(ROOT, "Source")):
        for n in filenames:
            fp = os.path.join(dirpath, n)
            with open(fp, encoding="utf-8-sig") as fh:
                s = fh.read()
            s = s.replace("TP_FIRSTPERSON_API", "ASTRA_API").replace(OLD, NEW)
            if n.endswith(".Build.cs"):
                s = "\n".join(line for line in s.splitlines() if "/Variant_" not in line) + "\n"
            with open(fp, "w", encoding="utf-8") as fh:
                fh.write(s)

    # 5) file .uproject
    uproject = {
        "FileVersion": 3,
        "EngineAssociation": "5.8",
        "Category": "",
        "Description": "ASTRA - capitano di una nave stellare con equipaggio AI",
        "Modules": [{
            "Name": NEW, "Type": "Runtime", "LoadingPhase": "Default",
            "AdditionalDependencies": ["Engine", "AIModule", "UMG"],
        }],
        "Plugins": [
            {"Name": "ModelingToolsEditorMode", "Enabled": True, "TargetAllowList": ["Editor"]},
            {"Name": "StateTree", "Enabled": True},
            {"Name": "GameplayStateTree", "Enabled": True},
            {"Name": "ModelContextProtocol", "Enabled": True, "TargetAllowList": ["Editor"]},
            {"Name": "AllToolsets", "Enabled": True, "TargetAllowList": ["Editor"]},
            {"Name": "PythonScriptPlugin", "Enabled": True, "TargetAllowList": ["Editor"]},
            {"Name": "EditorScriptingUtilities", "Enabled": True, "TargetAllowList": ["Editor"]},
            {"Name": "GeometryScripting", "Enabled": True},
            {"Name": "PCG", "Enabled": True},
            {"Name": "PCGGeometryScriptInterop", "Enabled": True},
            {"Name": "UdpMessaging", "Enabled": False},
        ],
    }
    with open(os.path.join(ROOT, f"{NEW}.uproject"), "w", encoding="utf-8") as fh:
        json.dump(uproject, fh, indent="\t")
        fh.write("\n")

    # 6) configurazione: reindirizzamenti + impostazioni di ASTRA
    engine_ini = os.path.join(ROOT, "Config", "DefaultEngine.ini")
    with open(engine_ini, encoding="utf-8-sig") as fh:
        s = fh.read()
    classes = ("CameraManager", "Character", "GameMode", "PlayerController")
    redirects = "\n".join(
        [f'+ActiveGameNameRedirects=(OldGameName="{OLD}",NewGameName="/Script/{NEW}")',
         f'+ActiveGameNameRedirects=(OldGameName="/Script/{OLD}",NewGameName="/Script/{NEW}")']
        + [f'+ActiveClassRedirects=(OldClassName="{OLD}{c}",NewClassName="{NEW}{c}")' for c in classes])
    s = s.replace("[/Script/Engine.Engine]\n", "[/Script/Engine.Engine]\n" + redirects + "\n", 1)
    s = s.replace("[/Script/Engine.RendererSettings]\n", "[/Script/Engine.RendererSettings]\n"
                  "; --- ASTRA: profilo base per MacBook Air M4 (vedi docs/ricerca/11) ---\n"
                  "r.AntiAliasingMethod=4\n"
                  "r.RayTracing=False\n"
                  "r.Lumen.HardwareRayTracing=False\n"
                  "r.Substrate=False\n"
                  "r.Nanite.ProjectEnabled=True\n", 1)
    with open(engine_ini, "w", encoding="utf-8") as fh:
        fh.write(s)

    project_id = uuid.uuid4().hex.upper()
    with open(os.path.join(ROOT, "Config", "DefaultGame.ini"), "w", encoding="utf-8") as fh:
        fh.write("[/Script/EngineSettings.GeneralProjectSettings]\n"
                 f"ProjectID={project_id}\n"
                 "ProjectName=ASTRA\n"
                 "CompanyName=ASTRA\n"
                 "ProjectVersion=0.1.0.0\n"
                 "Description=Simulatore in prima persona di capitano di nave stellare con equipaggio AI\n")

    with open(os.path.join(ROOT, "Config", "DefaultEditorPerProjectUserSettings.ini"), "a", encoding="utf-8") as fh:
        fh.write("\n[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]\n"
                 "bAutoStartServer=True\n"
                 "ServerPortNumber=8000\n"
                 "bEnableToolSearch=True\n"
                 "\n[/Script/PythonScriptPlugin.PythonScriptPluginUserSettings]\n"
                 "bDeveloperMode=True\n"
                 "\n[/Script/UnrealEd.EditorPerformanceSettings]\n"
                 "bThrottleCPUWhenNotForeground=False\n"
                 "bMonitorEditorPerformance=False\n"
                 "\n[/Script/ToolsetRegistry.ToolsetRegistrySettings]\n"
                 "+BlockedNames=GetNodeDataView\n"
                 "+BlockedNames=DrawSpline\n")

    mac_dir = os.path.join(ROOT, "Config", "Mac")
    os.makedirs(mac_dir, exist_ok=True)
    with open(os.path.join(mac_dir, "MacEngine.ini"), "w", encoding="utf-8") as fh:
        fh.write("; ASTRA: memoria per MacBook Air M4 16 GB (docs/ricerca/11)\n"
                 "[TextureStreaming]\n"
                 "PoolSizeVRAMPercentage=0\n"
                 "\n[SystemSettings]\n"
                 "r.Streaming.PoolSize=2000\n"
                 "r.ShaderCompiler.MemoryLimit=3072\n")

    print("Progetto ASTRA creato in", ROOT)


if __name__ == "__main__":
    main()
