<#
.SYNOPSIS
Costruisce il gioco giocabile di ASTRA per Windows (Packaged\Windows\): compila, cuoce i contenuti, impacchetta, poi mette la mente Python
accanto al gioco (mind\: i sorgenti, uv.lock, un uv.exe) e lo script della prima configurazione. E' l'equivalente di tools/pacchetto.sh del Mac.

.DESCRIPTION
Va eseguito su un PC Windows con la stessa versione di Unreal Engine del progetto (5.8.3, dal Launcher di Epic) e Visual Studio con il carico
di lavoro "Sviluppo di giochi con C++" (docs/WINDOWS.md, "Il giorno del PC Windows"). L'editor deve essere chiuso. Il repository va clonato in un
percorso corto (C:\ASTRA): i percorsi dei contenuti sono lunghi. Il log di UAT e' in Saved\Logs\package_last_windows.log.

Compatibile con Windows PowerShell 5.1 (quella che c'e' di serie) e con PowerShell 7; il file e' solo ASCII di proposito (la 5.1 legge i file senza
BOM nella tabella di caratteri del sistema).

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1 -Config Shipping -Zip
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1 -SoloMente     # rimette solo la mente in un pacchetto gia' fatto
#>
[CmdletBinding()]
param(
    # Development ha la console, il banco di prova (-astra_harness) e i log; Shipping e' la build di rilascio
    [ValidateSet("Development", "Shipping")]
    [string]$Config = "Development",
    # la cartella di Unreal Engine 5.8 (default: UE_ROOT, il registro di Epic, C:\Program Files\Epic Games\UE_5.8)
    [string]$UE = "",
    # il uv.exe da mettere accanto alla mente (default: quello nel PATH)
    [string]$Uv = "",
    # salta compilazione e cottura: rimette solo la mente e gli script in un pacchetto gia' fatto
    [switch]$SoloMente,
    # alla fine crea Packaged\ASTRA-Windows.zip (con tar.exe di Windows 10 o successivo)
    [switch]$Zip
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) { Write-Host ""; Write-Host "== $Message" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host ""; Write-Host "PACCHETTO FALLITO: $Message" -ForegroundColor Red; exit 1 }

$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Out = Join-Path $Repo "Packaged"
$LogDir = Join-Path $Repo "Saved\Logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (-not (Test-Path (Join-Path $Repo "ASTRA.uproject"))) { Fail "non trovo ASTRA.uproject in $Repo (lo script sta in tools\windows\ del repository)" }

# ---------------------------------------------------------------------------------------------------------- Unreal Engine
function Find-UnrealEngine {
    $candidates = @()
    if ($UE) { $candidates += $UE }
    if ($env:UE_ROOT) { $candidates += $env:UE_ROOT }
    try {
        $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\EpicGames\Unreal Engine\5.8" -ErrorAction Stop
        if ($reg.InstalledDirectory) { $candidates += $reg.InstalledDirectory }
    }
    catch { }
    $candidates += "C:\Program Files\Epic Games\UE_5.8"
    foreach ($c in $candidates) {
        if (Test-Path (Join-Path $c "Engine\Build\BatchFiles\RunUAT.bat")) { return $c }
    }
    return $null
}

# un file di Git LFS non scaricato e' un puntatore di tre righe: il pacchetto verrebbe cotto con contenuti finti
function Test-LfsPointer([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $buffer = New-Object byte[] 40
        $count = $stream.Read($buffer, 0, 40)
        return [System.Text.Encoding]::ASCII.GetString($buffer, 0, $count).StartsWith("version https://git-lfs")
    }
    finally { $stream.Dispose() }
}

if (-not $SoloMente) {
    Step "Controlli"
    $UEDir = Find-UnrealEngine
    if (-not $UEDir) { Fail "Unreal Engine 5.8 non trovato: indica -UE 'C:\Program Files\Epic Games\UE_5.8' (o imposta UE_ROOT)" }
    Write-Host "Unreal Engine: $UEDir"
    if (Get-Process -Name "UnrealEditor" -ErrorAction SilentlyContinue) { Fail "chiudi prima l'editor" }
    $assets = Get-ChildItem -Path (Join-Path $Repo "Content") -Recurse -File -Include *.uasset, *.umap | Select-Object -First 25
    foreach ($a in $assets) {
        if (Test-LfsPointer $a.FullName) { Fail "$($a.FullName) e' un puntatore di Git LFS: esegui 'git lfs pull' nel repository" }
    }
    if ($Repo.Length -gt 40) { Write-Host "ATTENZIONE: il repository sta in un percorso lungo ($Repo): Windows limita i percorsi a 260 caratteri; se la cottura fallisce con 'path too long', clonalo in C:\ASTRA" -ForegroundColor Yellow }

    Step "Compilazione, cottura e impacchettamento di ASTRA ($Config, Win64): ore la prima volta (gli shader), minuti le successive"
    if (Test-Path (Join-Path $Out "Windows")) { Remove-Item -Recurse -Force (Join-Path $Out "Windows") }   # (solo il nostro: un pacchetto vecchio non deve passare per quello nuovo)
    $uat = Join-Path $UEDir "Engine\Build\BatchFiles\RunUAT.bat"
    $uatArgs = "BuildCookRun -project=`"$Repo\ASTRA.uproject`" -platform=Win64 -clientconfig=$Config -build -cook -stage -pak -iostore -package -archive -archivedirectory=`"$Out`" -prereqs -nop4 -utf8output -unattended"
    $proc = Start-Process -FilePath $uat -ArgumentList $uatArgs -NoNewWindow -Wait -PassThru
    $uatLog = Join-Path $UEDir "Engine\Programs\AutomationTool\Saved\Logs\Log.txt"
    if (Test-Path $uatLog) { Copy-Item $uatLog (Join-Path $LogDir "package_last_windows.log") -Force }
    if ($proc.ExitCode -ne 0) { Fail "UAT ha risposto $($proc.ExitCode) (log: $LogDir\package_last_windows.log; cerca 'Error:' e 'error C')" }
}

# ---------------------------------------------------------------------------------------------------------- la cartella del pacchetto
Step "La mente accanto al gioco"
$Stage = $null
if (Test-Path $Out) {
    $Stage = Get-ChildItem -Path $Out -Directory | Where-Object { Test-Path (Join-Path $_.FullName "ASTRA.exe") } | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Stage) { Fail "non trovo il pacchetto (una cartella con ASTRA.exe) in $Out" }
Write-Host "Pacchetto: $Stage"

# la mente: solo i sorgenti e uv.lock (il suo ambiente Python nasce nei dati di ASTRA, con uv, alla prima configurazione); non l'helper del Mac
# (stt_server), non gli ambienti, non le cache; bin\ (uv.exe) e' escluso cosi' che /MIR non lo cancelli
$MindOut = Join-Path $Stage "mind"
robocopy (Join-Path $Repo "mind") $MindOut /MIR /XD ".venv" "__pycache__" ".cache" ".ruff_cache" ".build" ".swiftpm" "stt_server" "bin" /XF ".DS_Store" "*.pyc" /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "robocopy della mente ha risposto $LASTEXITCODE" }
if (-not (Test-Path (Join-Path $MindOut "pyproject.toml"))) { Fail "la mente non e' stata copiata in $MindOut" }

# un uv.exe accanto alla mente: e' il primo che il gioco cerca, cosi' il PC di destinazione non ha bisogno di installarlo
$UvSource = $Uv
if (-not $UvSource) {
    $found = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($found) { $UvSource = $found.Source }
}
if (-not $UvSource -or -not (Test-Path $UvSource)) {
    Fail "uv.exe non trovato: installalo (winget install --id astral-sh.uv -e   oppure   powershell -c ""irm https://astral.sh/uv/install.ps1 | iex"") o indica -Uv C:\percorso\uv.exe"
}
$item = Get-Item $UvSource
if ($item.LinkType -and $item.Target) { $UvSource = @($item.Target)[0] }       # (il collegamento di winget: il file vero)
New-Item -ItemType Directory -Force -Path (Join-Path $MindOut "bin") | Out-Null
Copy-Item $UvSource (Join-Path $MindOut "bin\uv.exe") -Force
Write-Host ("uv: " + (& (Join-Path $MindOut "bin\uv.exe") --version))

# la prima configurazione e il foglio per chi riceve il pacchetto
Copy-Item (Join-Path $PSScriptRoot "Setup-ASTRA.ps1") $Stage -Force
Copy-Item (Join-Path $PSScriptRoot "Setup-ASTRA.bat") $Stage -Force
$Readme = @"
ASTRA for Windows
=================

1. Run Setup-ASTRA.bat once (it needs the internet: it makes the crew's Python environment and downloads their voice and listening models,
   a few GB). If you have a key file (.env) for the crew's minds, drag it onto Setup-ASTRA.bat or run:
       Setup-ASTRA.bat -EnvFile C:\path\to\.env
2. Start ASTRA.exe.

The crew's data (their key, models, caches) lives in %LOCALAPPDATA%\ASTRA; the game's own log and saved games in
%LOCALAPPDATA%\ASTRA\Saved; the crew's log is %LOCALAPPDATA%\ASTRA\Saved\Logs\astra-mind.log.
If the crew is silent: read that log, and see docs\WINDOWS.md in the project.
"@
Set-Content -Path (Join-Path $Stage "README-WINDOWS.txt") -Value $Readme -Encoding ASCII

if ($Zip) {
    Step "Archivio"
    $zipPath = Join-Path $Out "ASTRA-Windows.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    & tar.exe -a -c -f $zipPath -C $Out (Split-Path -Leaf $Stage)
    if ($LASTEXITCODE -ne 0) { Fail "tar.exe ha risposto $LASTEXITCODE" }
    Write-Host "Archivio: $zipPath"
}

$bytes = (Get-ChildItem -Path $Stage -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host ("Pacchetto pronto ($Config): $Stage ({0:N1} GB)" -f ($bytes / 1GB)) -ForegroundColor Green
Write-Host "Sul PC di prova: copia la cartella, esegui Setup-ASTRA.bat (una volta, con la rete), poi ASTRA.exe."
