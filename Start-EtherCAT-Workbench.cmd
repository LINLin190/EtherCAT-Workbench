@echo off
setlocal
cd /d "%~dp0"
title EtherCAT Workbench
echo Starting EtherCAT Workbench...
echo Project: %CD%
echo.

where pwsh.exe >nul 2>nul
if %errorlevel% equ 0 (
    pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-desktop.ps1"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-desktop.ps1"
)

if errorlevel 1 (
    echo.
    echo EtherCAT Workbench failed to start. See the error above.
    pause
)
endlocal
