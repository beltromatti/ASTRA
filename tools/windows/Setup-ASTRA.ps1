<#
.SYNOPSIS
ASTRA first-run setup (Windows): makes the crew's minds ready before the first game.

.DESCRIPTION
The crew of ASTRA thinks and speaks in a small Python program (the folder "mind" next to the game). The game starts it by itself, but its Python
environment and its voice and listening models have to be downloaded once: a few GB, with the internet. If you skip this the game does it in the
background on its first start (the crew is silent for some minutes); doing it here shows you what is happening and anything that goes wrong.

What it does, in order:
  1. makes the data folder  %LOCALAPPDATA%\ASTRA  and, if you give it a key file, keeps the crew's key there (it is never printed);
  2. makes the Python environment with uv (the program that comes in mind\bin\uv.exe, or the one on your PATH);
  3. downloads the speech models (Parakeet and faster-whisper for listening, Pocket TTS for the crew's voices in -Langs) and checks the machine:
     the key, the microphone, the libraries, the voices.
Nothing here needs administrator rights and no system setting is changed. Run it again at any time: what is already there is left alone.

.EXAMPLE
Setup-ASTRA.bat
Setup-ASTRA.bat -EnvFile C:\path\to\.env -Langs en,it
Setup-ASTRA.bat -NoModels          # only looks (and makes the Python environment): downloads no model
#>
[CmdletBinding()]
param(
    # a file with OPENROUTER_API_KEY=... for the crew's minds (copied to %LOCALAPPDATA%\ASTRA\.env)
    [string]$EnvFile = "",
    # the languages of the crew's voices to download (about 440 MB each): any of en,it,es,fr,de,pt,nl
    [string]$Langs = "en",
    # do not download models: only the Python environment and the check
    [switch]$NoModels
)

$ErrorActionPreference = "Stop"

function Step([string]$Message) { Write-Host ""; Write-Host "== $Message" -ForegroundColor Cyan }
function Fail([string]$Message) { Write-Host ""; Write-Host "SETUP FAILED: $Message" -ForegroundColor Red; exit 1 }

# the packaged game: mind\ is next to this script. A repository checkout (tools\windows\): the mind is two folders up and the game uses its own mind\.venv
$Root = $PSScriptRoot
$Mind = Join-Path $Root "mind"
$Packaged = $true
if (-not (Test-Path (Join-Path $Mind "pyproject.toml"))) {
    $Mind = Join-Path (Split-Path -Parent (Split-Path -Parent $Root)) "mind"
    $Packaged = $false
}
if (-not (Test-Path (Join-Path $Mind "pyproject.toml"))) { Fail "I cannot find the crew's folder (mind\pyproject.toml) next to this script." }

$Uv = Join-Path $Mind "bin\uv.exe"
if (-not (Test-Path $Uv)) {
    $found = Get-Command "uv.exe" -ErrorAction SilentlyContinue
    if ($found) { $Uv = $found.Source }
    elseif (Test-Path (Join-Path $env:USERPROFILE ".local\bin\uv.exe")) { $Uv = Join-Path $env:USERPROFILE ".local\bin\uv.exe" }
}
if (-not (Test-Path $Uv)) { Fail "uv (the program that makes the Python environment) is missing. Install it with:  winget install --id astral-sh.uv -e   and run this again." }
Write-Host ("uv: " + (& $Uv --version))

$Data = Join-Path $env:LOCALAPPDATA "ASTRA"
if ($Packaged) {
    New-Item -ItemType Directory -Force -Path $Data | Out-Null
    $env:ASTRA_HOME = $Data
    $env:UV_PROJECT_ENVIRONMENT = Join-Path $Data "venv"
    Write-Host "Data folder: $Data"
}
$env:PYTHONUTF8 = "1"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

if ($EnvFile) {
    if (-not (Test-Path $EnvFile)) { Fail "The key file $EnvFile does not exist." }
    $target = Join-Path (Split-Path -Parent $Mind) ".env"
    if ($Packaged) { $target = Join-Path $Data ".env" }
    Copy-Item -Path $EnvFile -Destination $target -Force
    Write-Host "The crew's key file is in place ($target)."
}

Push-Location $Mind
try {
    Step "Making the crew's Python environment (about 2.5 GB, a few minutes the first time)"
    & $Uv sync --frozen
    if ($LASTEXITCODE -ne 0) { Fail "uv sync stopped with code $LASTEXITCODE. Is the internet on? Run Setup again; what was downloaded is kept." }

    if ($NoModels) { Step "Looking at this machine" } else { Step "Downloading the speech models (a few GB, the first time only) and looking at this machine" }
    $firstrun = @("--langs", $Langs)
    if ($NoModels) { $firstrun = @("--check") }
    & $Uv run --frozen python -m astra_mind.firstrun @firstrun
    $problems = $LASTEXITCODE
}
finally { Pop-Location }

Write-Host ""
if ($problems -eq 0) { Write-Host "Setup finished: start ASTRA.exe." -ForegroundColor Green }
else { Write-Host "Setup finished, with $problems thing(s) above marked FAIL to fix before the crew can work (a missing key: run again with -EnvFile)." -ForegroundColor Yellow }
exit 0
