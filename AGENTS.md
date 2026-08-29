# Repository Guidelines

## Project Structure & Module Organization

The only desktop UI lives in `desktop/`: React/TypeScript pages are under `desktop/src/`, and the Tauri 2 Rust host is under `desktop/src-tauri/`. The headless Python core lives in `src/ethercat_debug_tool/`: `bridge.py` is the IPC boundary, `worker/` serializes EtherCAT requests, and `backends/` contains Real and Mock implementations. Protocol logic belongs in `services/`, `esi/`, `sii/`, and `esc_profiles/`; shared types belong in `models.py`.

Before changing behavior, read the maintainer-local `约束/功能点.md` completely. It is the Chinese source of truth for features, safety rules, and validation boundaries. Update it whenever a feature or constraint changes, but never stage, commit, or publish it. If it is absent in a clone, follow the README and issue requirements instead.

## Build, Test, and Development Commands

Use PowerShell on Windows 10/11 with Python 3.11+, Node.js 20+, pnpm, and the Rust MSVC toolchain:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m pytest -q
Set-Location desktop
pnpm install
pnpm build
Set-Location ..
.\start-desktop.ps1
```

Do not build a Tauri bundle or change the version for ordinary fixes/features unless explicitly requested. Never restore the retired desktop framework, freezing scripts, or installer project.

## Coding Style & Naming Conventions

Use four spaces in Python, core-logic type annotations, and Ruff’s 110-character limit. Use existing TypeScript formatting and strict types. Keep React pages thin. Every Master operation must pass through the Python bridge and Worker; never call pySOEM from the webview or Rust host.

## Testing Guidelines

Use `pytest` for the Python core and the TypeScript/Vite build for the frontend. Name Python files `test_<area>.py` and tests `test_<behavior>`. Exercise Worker scheduling, codecs, ESI/SII, EEPROM, profiles, bridge commands, and register semantics. Tests must use Mock data and never write real hardware.

## Visual Validation

常用分辨率：`1920×1080`、`2560×1440`、`1280×720`；默认使用 `2560×1440`。

## Commit & Pull Request Guidelines

Use concise imperative subjects with prefixes such as `fix:`, `feat:`, `docs:`, or `chore:`. Exclude generated artifacts. Pull requests must describe the problem, approach, verification, safety impact, and affected hardware/profile. Link issues, include UI screenshots, and label Mock-only verification.

## Safety & Configuration

Real mode requires the official `pysoem==1.1.13` Windows wheel and Npcap with WinPcap-compatible mode. Do not bundle Npcap. Preserve write confirmations, audit logging, cancellation, EEPROM backup/verification, and safe Worker shutdown when changing hardware-facing flows.
