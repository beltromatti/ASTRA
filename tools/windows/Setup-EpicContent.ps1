<#
.SYNOPSIS
Copies the free template content of Epic that ASTRA uses as placeholders and that is not in git: the Manny and Quinn mannequins and their animations
(Content\Characters). The Windows twin of tools/setup_epic_content.sh.

.DESCRIPTION
The crew and the fighters' pilots on foot are Epic's mannequins until the MetaHuman crew is in the game; their assets are the engine's own, so the
repository does not carry them (.gitignore: Content/Characters/). A fresh clone has to copy them once, before it is compiled or packaged: without
them the game starts with a crew that has no bodies. Pacchetto-Windows.ps1 runs this by itself when they are missing.

Run it again at any time: what is already there is left as it is. Nothing here needs administrator rights.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Setup-EpicContent.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Setup-EpicContent.ps1 -UE "D:\Epic\UE_5.8"
#>
[CmdletBinding()]
param(
    # the folder of Unreal Engine 5.8 (default: UE_ROOT, the Epic registry key, C:\Program Files\Epic Games\UE_5.8)
    [string]$UE = ""
)

$ErrorActionPreference = "Stop"

function Fail([string]$Message) { Write-Host ""; Write-Host "SETUP FAILED: $Message" -ForegroundColor Red; exit 1 }

$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Repo "ASTRA.uproject"))) { Fail "I cannot find ASTRA.uproject in $Repo (this script lives in tools\windows\ of the repository)." }

$Template = "Templates\TemplateResources\High\Characters\Content"
$candidates = @()
if ($UE) { $candidates += $UE }
if ($env:UE_ROOT) { $candidates += $env:UE_ROOT }
try {
    $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\EpicGames\Unreal Engine\5.8" -ErrorAction Stop
    if ($reg.InstalledDirectory) { $candidates += $reg.InstalledDirectory }
}
catch { }
$candidates += "C:\Program Files\Epic Games\UE_5.8"
$Source = $null
foreach ($c in $candidates) {
    try {      # (Join-Path stops with an error on a drive that does not exist)
        if (Test-Path (Join-Path $c $Template)) { $Source = Join-Path $c $Template; break }
    }
    catch { }
}
if (-not $Source) {
    Fail "Epic's mannequins are not in the engine I found ($($candidates -join ', ')). Install Unreal Engine 5.8 with the option 'Templates and Feature Packs' from the Epic Games Launcher, or point -UE at it."
}

$Target = Join-Path $Repo "Content\Characters"
New-Item -ItemType Directory -Force -Path $Target | Out-Null
Write-Host "Copying $Source"
Write-Host "     to $Target"
robocopy $Source $Target /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "robocopy answered $LASTEXITCODE." }
if (-not (Test-Path (Join-Path $Target "Mannequins\Meshes\SKM_Manny_Simple.uasset"))) { Fail "the copy finished but Mannequins\Meshes\SKM_Manny_Simple.uasset is not in $Target." }

$bytes = (Get-ChildItem -Path $Target -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Done: Content\Characters has the mannequins ({0:N0} MB)." -f ($bytes / 1MB)) -ForegroundColor Green
exit 0
