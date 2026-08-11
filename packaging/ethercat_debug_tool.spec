from pathlib import Path
import sys
from importlib.metadata import PackageNotFoundError, distribution

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

project_root = Path(SPECPATH).parent
source_root = project_root / "src"

datas = collect_data_files("ethercat_debug_tool")
binaries = collect_dynamic_libs("pysoem")
hidden_imports = collect_submodules("pysoem")

for package_name in (
    "pysoem",
    "PySide6",
    "PySide6-Essentials",
    "PySide6-Addons",
    "shiboken6",
    "pyinstaller",
):
    try:
        package = distribution(package_name)
    except PackageNotFoundError:
        continue
    for item in package.files or ():
        lowered = str(item).lower()
        if "/licenses/" in lowered.replace("\\", "/") or item.name.lower().startswith(("license", "copying")):
            source = Path(package.locate_file(item))
            if source.is_file():
                datas.append((str(source), f"licenses/{package_name}"))

python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/Python"))
datas.extend(
    [
        (str(project_root / "LICENSE.md"), "."),
        (str(project_root / "THIRD_PARTY_NOTICES.md"), "."),
    ]
)

a = Analysis(
    [str(project_root / "packaging" / "launcher.py")],
    pathex=[str(source_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "pytestqt", "ruff"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EtherCATWorkbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(project_root / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="EtherCATWorkbench",
)
