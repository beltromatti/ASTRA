@echo off
rem ASTRA first-run setup: runs Setup-ASTRA.ps1 for this one run only (the execution policy switch is not a system setting).
rem Double-click it, or: Setup-ASTRA.bat -EnvFile C:\path\to\.env -Langs en,it
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Setup-ASTRA.ps1" %*
echo.
pause
