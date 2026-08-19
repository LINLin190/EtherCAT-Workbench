# EtherCAT Workbench

An EtherCAT slave debugging and diagnostics workbench for Windows.

The desktop application uses **Tauri 2, React, TypeScript, Material UI, and Emotion**. Python owns the EtherCAT hardware core behind a persistent local bridge; the webview never accesses pySOEM directly.

## Capabilities

- Adapter discovery, connection, bus scan, and slave identities
- INIT / PRE-OP / SAFE-OP / OP state control and recovery
- CoE object dictionary, SDO access, and write readback verification
- RxPDO / TxPDO mapping and bit offsets
- Cyclic I/O, WKC and error monitoring, and guarded PDO outputs
- Searchable ESC register catalog, reads, monitoring, and two-step guarded writes
- ESI-to-SII generation, Smart View, capacity checks, full reads, BIN backups, programming, verification, and restore
- Real and Demo backends; Real is the default, while Demo is enabled only in Settings and is visibly marked

## Architecture

```text
React + Material UI + Emotion
              │
              ▼
        Tauri 2 / Rust
              │ private stdin/stdout JSON
              ▼
       Python Bridge
              │
              ▼
EtherCatWorker → Services → Real/Mock Backend → pySOEM
```

All requests for one EtherCAT Master are serialized by a single Worker. EEPROM, register, and PDO write guards and verification remain in the Python services rather than relying on page state.

## Development

Requirements: Windows 10/11 x64, Node.js 20+, pnpm, the Rust MSVC toolchain, Python 3.11+, and WebView2. Real mode additionally requires `pysoem==1.1.13` and Npcap with WinPcap API-compatible Mode enabled.

```powershell
python -m pip install -e ".[dev]"
Set-Location desktop
pnpm install
Set-Location ..
.\start-desktop.ps1
```

Checks:

```powershell
python -m ruff check src tests
python -m pytest -q
Set-Location desktop
pnpm build
```

The primary design targets are `2560 × 1440` and `1920 × 1080`; `1280 × 720` is the compatibility floor.

## Safety

PDO output, ESC register, and EEPROM writes can affect machinery immediately. Use Real mode only with an isolated adapter and safe equipment state, and verify the selected slave, address, and target before writing.

This repository does not include or redistribute the Npcap installer. See [LICENSE.md](LICENSE.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
