param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$version = (& python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])").Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to read the project version.'
}

Push-Location $projectRoot
try {
    & python -m PyInstaller --noconfirm --clean 'packaging\ethercat_debug_tool.spec'
    if ($LASTEXITCODE -ne 0) {
        throw 'PyInstaller build failed.'
    }

    $bundledNpcap = Get-ChildItem 'dist\EtherCATWorkbench' -Recurse -Filter 'npcap-*.exe' -ErrorAction SilentlyContinue
    if ($bundledNpcap) {
        throw 'The free Npcap installer must not be included in the application bundle.'
    }

    if ($SkipInstaller) {
        Write-Host "Application bundle: $projectRoot\dist\EtherCATWorkbench"
        return
    }

    $compilerCommand = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    $compilerPath = if ($compilerCommand) { $compilerCommand.Source } else { $null }
    if (-not $compilerPath) {
        $standardCompiler = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
        if (Test-Path $standardCompiler) {
            $compilerPath = $standardCompiler
        }
    }
    if (-not $compilerPath) {
        throw 'Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php and run this script again.'
    }

    & $compilerPath "/DMyAppVersion=$version" 'packaging\installer.iss'
    if ($LASTEXITCODE -ne 0) {
        throw 'Inno Setup build failed.'
    }
    Write-Host "Installer: $projectRoot\release\EtherCATWorkbench-$version-Setup-x64.exe"
}
finally {
    Pop-Location
}
