@echo off
setlocal
cd /d "%~dp0"
title EtherCAT Workbench
echo Starting EtherCAT Workbench...
echo Project: %CD%
echo.

rem Clean up a previous project-owned Vite process before starting Tauri.
rem Do not terminate unrelated services that may use port 1420.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$desktop = [IO.Path]::GetFullPath('%~dp0desktop').TrimEnd('\'); $listeners = @(Get-NetTCPConnection -LocalPort 1420 -State Listen -ErrorAction SilentlyContinue); foreach ($listener in $listeners) { $p = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $listener.OwningProcess) -ErrorAction SilentlyContinue; $cmd = [string]$p.CommandLine; if ($p.Name -eq 'node.exe' -and $cmd.IndexOf($desktop, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $cmd -match '(?i)(vite|node_modules)') { Write-Host ('Stopping stale Vite process (PID ' + $listener.OwningProcess + ').'); Stop-Process -Id $listener.OwningProcess -Force } }"

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
