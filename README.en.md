# EtherCAT Workbench

[简体中文](README.md) | [English](README.en.md)

A PySide6 desktop application for Windows 11 and Python 3.11+ that helps engineers inspect and debug EtherCAT slaves. It starts in the safe Demo/Mock mode by default. All PDO, SDO, EEPROM, and register requests for a Master are serialized by one dedicated `EtherCAT Worker`; the GUI thread never calls pySOEM directly.

This project uses [pySOEM](https://github.com/bnjmnp/pysoem) for EtherCAT master communication. Real mode on Windows depends on the official [Npcap](https://npcap.com/) driver; Npcap is not included in this repository or its installer.

## User guide

### Windows and Npcap requirements

Real mode is pinned to the official Windows wheel `pysoem==1.1.13`. It requires:

- Windows 10/11 x64;
- Python 3.11 or newer;
- Npcap installed with **WinPcap API-compatible Mode** enabled;
- administrator/raw-packet access to the selected adapter;
- preferably, a dedicated EtherCAT adapter that carries no ordinary network traffic.

The application reports actionable errors when Npcap/wpcap is missing, an adapter cannot be opened, or the installed pySOEM version is incompatible.

### Install and run

End users can install `EtherCATWorkbench-<version>-Setup-x64.exe` from GitHub Releases without installing Python. The setup program checks the Npcap version and WinPcap compatibility mode. If the requirement is not met, it asks whether to download Npcap 1.88 from the official website. Declining does not cancel application setup; Demo/Mock mode remains available.

This project does not bundle or redistribute the free Npcap installer. After explicit confirmation, the default browser opens the official `npcap-1.88.exe` download URL. Users must enable **WinPcap API-compatible Mode** during Npcap setup. The application checks the dependency again when switching to Real mode.

### Recommended workflow

The top bar follows the sequence `1. Connect and scan -> 2. Select target and state -> 3. Cyclic communication`:

1. Select Demo or Real mode and an adapter, then click **Connect**.
2. Click **Scan slaves**, then select the Master or a slave in the tree on the left.
3. Confirm the target shown at the top and click `INIT`, `PRE-OP`, `SAFE-OP`, or `OP` directly.
4. Follow the recommended next action on the right to read PDO mapping, prepare all slave states, and start cyclic communication.
5. The log drawer is collapsed by default. Use the status-bar **Log** control to open it; errors open it automatically.

The **Advanced recovery** section is not part of the normal workflow. **Refresh bus state** performs a read-only refresh of slave and AL status. **Reconfigure slave** is for a reachable slave with invalid configuration or state. **Recover lost slave** attempts to rediscover a slave after a link interruption or power cycle.

### Implemented functionality

- Windows adapter enumeration, connect/disconnect, scan, identity information, AL Status, and direct INIT/PRE-OP/SAFE-OP/OP transitions;
- normal SDO reads and writes with `ca=False`, online SDO Info object dictionary, and ESI fallback;
- live PDO assignment/mapping with ESI names and types plus byte and bit offsets;
- cyclic PDO exchange, Actual/Expected WKC, timeout/error counters, and safe stop after consecutive failures;
- raw process inputs and controlled outputs following `monitor mode -> output control mode -> pending -> apply output`;
- ESI XML import, drag and drop, recent files, multiple Device entries per XML, and automatic settings persistence;
- SII structural parsing, complete image generation, Smart View, and read-only Hex View;
- complete EEPROM reads; BIN plus JSON metadata backups; changed-word writes; batched readback; mandatory settling delay; full-capacity reread; byte comparison; SHA-256; structural and XML identity/category/name semantic validation;
- exclusive three-frame ESC ECAT reset using `0x0040 <- 0x52/0x45/0x53` after successful verification, with separate rediscovery and reload results;
- restore from a BIN backup, while still requiring a fresh backup before restoration;
- seven distinct profiles: E101, E252, E253, ET1100, LAN9252, LAN9253, and Generic ESC;
- standard register map, raw reads, explicit write mode, pre-write reread, change masks, and semantic verification for RW/W1C/W1S/WO/self-clearing/volatile registers, plus merged low-priority monitoring;
- UI logs and rotating JSONL logs under `%LOCALAPPDATA%\EtherCATWorkbench\logs`; every write operation is recorded as `AUDIT`.

### EEPROM safety rules

The UI permits EEPROM programming only when cyclic exchange is stopped and the target slave is in INIT. A complete, parseable backup of the current image is mandatory before the first write. The selected XML/Device fully defines the target image: the application does not merge Serial Number, Station Alias, or private data from the old EEPROM, and it never writes raw XML text bytes to EEPROM.

Vendor ID, Product Code, and Revision mismatches produce warnings but do not block programming. Programming is blocked when the XML cannot be parsed, a structurally valid SII cannot be generated, the target does not exactly fit the physical capacity, or EEPROM communication fails.

`image_success` is true only when the complete readback is byte-for-byte identical to the target, both SHA-256 values match, the SII structure is valid, and XML semantic validation passes. A temporary disconnect caused by reset, rediscovery failure, or reload verification failure is displayed separately and does not alter the completed image-verification result.

#### Current ESI-to-SII conversion boundary

The converter explicitly supports the ConfigData header and CRC-8, identity, BootStrap/standard mailbox fields, mailbox protocols, Strings, General, FMMU usage, SyncManager, RxPDO/TxPDO, and DC OpMode. It supports standard primitive CoE data types and BIT1 through BIT8 PDO type numbers.

It does not generate vendor-private Categories, the complete custom DataTypes dictionary, or protocol-specific EoE/FoE data. These omissions are reported by the generation report and UI rather than being presented as supported. Included BIN files are independent parse/validation vectors; they are not claimed to be byte-identical to XML-generated images because real devices can contain different configuration headers and vendor Categories.

### ESC profiles and identification

`chip_model` and `register_family` are stored separately. E101, E252, and E253 are never displayed as original ET1100, LAN9252, or LAN9253 devices. The domestic ESC models are identified only from ESI model text or chip-type register `0x0E00`; FMMU/SM counts and RAM ranges are never used to guess a model. Because datasheets for these three ESCs are unavailable, vendor-specific registers, EEPROM timing, and reset compatibility remain unverified.

## Developer guide

### Run from source

Run the following commands in PowerShell:

```powershell
git clone https://github.com/LINLin190/EtherCAT-Workbench.git
cd EtherCAT-Workbench
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ethercat-workbench
```

Alternative entry points:

```powershell
python -m ethercat_debug_tool
python -m ethercat_debug_tool --real
```

`--real` selects the Real backend only; it does not automatically open an adapter, scan the bus, or write hardware. Starting without arguments always selects the safe Demo/Mock backend.

### Build the Windows installer

Install [Inno Setup 6](https://jrsoftware.org/isdl.php) on Windows x64 and run:

```powershell
python -m pip install -e ".[dev]"
.\packaging\build.ps1
```

Build outputs:

- `dist\EtherCATWorkbench\`: the PyInstaller onedir application;
- `release\EtherCATWorkbench-0.1.0-Setup-x64.exe`: the single-file end-user installer.

Use `.\packaging\build.ps1 -SkipInstaller` to build only the application directory.

### Tests

All automated tests use only the Mock backend and included ESI/BIN fixtures. They do not open a real adapter or write real PDO outputs, EEPROM, or registers.

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m ruff check src tests
python -m pytest
```

## Current limitations and unverified behavior

- Npcap adapter opening, state transitions, cyclic PDO, SDO Info, FPRD/FPWR, and EEPROM timing have not been verified against a physical EtherCAT slave;
- vendor bit fields, private registers, and exact `0x0E00` codes for E101/E252/E253 require datasheets or hardware captures;
- vendor-private SII Categories and arbitrary complete ESI-schema conversion are unsupported;
- post-reset rediscovery currently performs one settling wait and one bus rescan; complex topologies may require a manual Reconfigure/Recover operation;
- the UI includes the standard public register map and raw access, but does not claim complete coverage of every vendor extension.

Start physical-device validation with read-only operations: enumerate, connect, scan, read state, read SDO/PDO mapping, read registers, and back up EEPROM. Confirm that the backup parses correctly and is stored offline before validating writes on an isolated test slave.

## Safety notice

EtherCAT output, register, and EEPROM writes can affect machinery or make a slave temporarily unavailable. Use Real mode only on an isolated test setup, verify the selected slave and address before each write, keep a known-good EEPROM backup, and ensure the connected equipment is in a safe state.

## License

EtherCAT Workbench is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). It is **source-available software**, not open-source software as defined by the OSI.

The license permits personal, educational, research, and other noncommercial use, modification, and distribution. Without separate written permission from the copyright holder, the software may not be used in commercial products, paid services, paid support, commercial internal operations, or for other commercial purposes. Original or modified distributions must retain the complete license, Required Notice, copyright notice, and original project URL, and must clearly identify modifications. Modified versions must not imply maintenance, endorsement, or warranty by the original author.

Bundled third-party components remain subject to their respective licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Contributing

[GitHub Issues](https://github.com/LINLin190/EtherCAT-Workbench/issues) are welcome for bug reports, feature requests, and physical-hardware validation results. You are also welcome to fork the repository, create a focused fix branch, and submit a pull request. Please describe the problem, scope, verification, and affected EtherCAT slave or ESC model. Do not contribute automated tests that write real EEPROM, PDO outputs, or registers.
