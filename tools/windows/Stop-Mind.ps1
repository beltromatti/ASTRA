<#
.SYNOPSIS
Stops the crew's mind (astra-mind) if one is left running: the Windows twin of `pkill -f astra-mind` in tools/ricompila.sh.

.DESCRIPTION
The game starts the mind hidden and stops it when it quits; in the editor it stays up between play sessions, and after a crash it stops by itself
only after 20 minutes without a game. This ends it (and uv, its parent) at once. Run it before rebuilding, or when the game says the mind's door is taken.

.EXAMPLE
powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Stop-Mind.ps1
#>
$mine = $PID
$found = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $mine -and $_.CommandLine -and ($_.CommandLine -match "astra-mind" -or $_.CommandLine -match "astra_mind\.server")
}
if (-not $found) { Write-Host "No mind is running."; exit 0 }
foreach ($p in $found) {
    Write-Host ("Stopping {0} (process {1})" -f $p.Name, $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Write-Host "Done."
