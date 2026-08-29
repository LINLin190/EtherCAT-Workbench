param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$desktopRoot = Join-Path $PSScriptRoot 'desktop'
$cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'

if ((Test-Path $cargoBin) -and -not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    $env:Path = "$cargoBin;$env:Path"
}

$pnpmCommand = Get-Command pnpm -ErrorAction SilentlyContinue
$corepackCommand = Get-Command corepack -ErrorAction SilentlyContinue
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$corepackPnpmRoot = Join-Path $env:LOCALAPPDATA 'node\corepack\v1\pnpm'
$cachedPnpm = $null
if (-not $pnpmCommand -and $nodeCommand -and $corepackCommand -and (Test-Path $corepackPnpmRoot)) {
    $cachedPnpm = Get-ChildItem $corepackPnpmRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName 'bin\pnpm.cjs') } |
        Sort-Object { [version]$_.Name } -Descending |
        Select-Object -First 1
}

if (-not $pnpmCommand -and -not $cachedPnpm -and -not $corepackCommand) {
    throw '未找到 pnpm 或 Corepack。请先安装 Node.js。'
}
if (-not $pnpmCommand -and -not $cachedPnpm) {
    $env:COREPACK_ENABLE_DOWNLOAD_PROMPT = '0'
}
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw '未找到 Rust/Cargo。请先安装 Rust MSVC 工具链。'
}

if (-not $pnpmCommand) {
    $pnpmShimRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'EtherCATWorkbench\bin'
    $pnpmShimPath = Join-Path $pnpmShimRoot 'pnpm.cmd'
    [System.IO.Directory]::CreateDirectory($pnpmShimRoot) | Out-Null
    if ($cachedPnpm) {
        $shimCommand = '"{0}" pnpm@{1} --pm-on-fail=ignore %*' -f $corepackCommand.Source, $cachedPnpm.Name
    } else {
        $shimCommand = '"{0}" pnpm %*' -f $corepackCommand.Source
    }
    [System.IO.File]::WriteAllLines($pnpmShimPath, @('@echo off', $shimCommand), [System.Text.Encoding]::ASCII)
    $env:Path = "$pnpmShimRoot;$env:Path"
}

function Invoke-Pnpm {
    if ($pnpmCommand) {
        & $pnpmCommand.Source @args
    } elseif ($cachedPnpm) {
        & $corepackCommand.Source "pnpm@$($cachedPnpm.Name)" --pm-on-fail=ignore @args
    } else {
        & $corepackCommand.Source pnpm @args
    }
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm 命令执行失败，退出码：$LASTEXITCODE"
    }
}

if ($pnpmCommand) {
    Write-Host "使用 pnpm：$($pnpmCommand.Source)" -ForegroundColor DarkGray
} elseif ($cachedPnpm) {
    Write-Host "未找到全局 pnpm，使用本机缓存版本 $($cachedPnpm.Name)。" -ForegroundColor Cyan
} else {
    Write-Host '未找到本机 pnpm，Corepack 将下载项目所需版本，请稍候...' -ForegroundColor Cyan
}

if ($Check) {
    Invoke-Pnpm --version
    Write-Host '启动环境检查通过。' -ForegroundColor Green
    exit 0
}

# A previous interrupted Tauri/Vite run can leave the dev server listening on
# the configured port. Reclaim only a matching project-owned Vite process;
# never terminate an unrelated service that happens to use the same port.
$devPort = 1420
$projectPath = [System.IO.Path]::GetFullPath($desktopRoot).TrimEnd('\')
$listeners = @(Get-NetTCPConnection -LocalPort $devPort -State Listen -ErrorAction SilentlyContinue)
foreach ($listener in $listeners) {
    $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $commandLine = [string]$processInfo.CommandLine
    $isProjectVite = $processInfo.Name -eq 'node.exe' -and
        $commandLine.IndexOf($projectPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $commandLine -match '(?i)(vite|node_modules)'
    if ($isProjectVite) {
        Write-Host "清理上次残留的 Vite 开发服务器（PID $($listener.OwningProcess)）。" -ForegroundColor DarkGray
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    } else {
        throw "端口 $devPort 已被其他进程占用（PID $($listener.OwningProcess)）。请先停止该服务后重试。"
    }
}

Push-Location $desktopRoot
try {
    if (-not (Test-Path 'node_modules')) {
        Write-Host '首次启动：正在安装前端依赖...' -ForegroundColor Cyan
        Invoke-Pnpm install
    }
    Invoke-Pnpm tauri:dev
} finally {
    Pop-Location
}
