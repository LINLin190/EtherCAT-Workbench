# EtherCAT Workbench

An EtherCAT slave debugging and diagnostics workbench for Windows.

The desktop application uses **Tauri 2, Rust, React, TypeScript, Material UI, and Emotion**. Python owns the EtherCAT hardware core behind a persistent local JSON bridge; the WebView never accesses pySOEM directly.

[简体中文](README.md)

> [!WARNING]
> The application defaults to **Real** mode, but startup does not open an adapter, connect, scan the bus, or write hardware automatically. Real-mode state transitions, register writes, cyclic I/O, and EEPROM operations can disconnect a slave or affect equipment. Start with read-only operations on an isolated, recoverable test setup.

## Why EtherCAT Workbench

EtherCAT Workbench brings bus discovery, state diagnostics, ESC register inspection, and EEPROM maintenance into one desktop workflow while isolating hardware requests in one communication Worker:

| Concern | Implementation |
| --- | --- |
| Safe first contact | Real mode does not auto-connect; Demo/Mock is enabled only in Settings and remains visibly marked |
| Responsive UI | The WebView never calls pySOEM; hardware work runs asynchronously in the Python Bridge |
| Request consistency | One Worker serializes requests for one Master |
| Write control | Registers use two-stage plans and readback; EEPROM uses capacity, structure, semantic, and full-image verification |
| Hardware-free development | Mock Backend, Demo data, and automated tests require no EtherCAT device |
| Traceability | UI progress, JSONL logs, and `AUDIT` write records retain diagnostic context |

EtherCAT master communication is provided by [pySOEM](https://github.com/bnjmnp/pysoem). Real mode on Windows depends on [Npcap](https://npcap.com/); neither this repository nor the application includes or redistributes Npcap.

## Capabilities

| Module | Current capability |
| --- | --- |
| Bus and state | Adapter detection and selection, manual connect/disconnect, bus scan, slave identities, AL status, INIT/PRE-OP/SAFE-OP/OP requests, reconfigure, and recovery |
| ESC registers | ET1100, LAN9252, and LAN9253 catalogs with search, categories, bit fields, raw address access, fixed monitoring, change highlighting, and copy |
| Register writes | 60-second plans bound to slave identity, semantic readback verification, and `AUDIT`; raw writes require HEX length to match width |
| ESI / SII | XML selection, drag and drop, five recent files, multiple Device selection, SII generation, Smart View with category/offset/length/content preview, and capacity checks |
| EEPROM | Full reads, BIN backups, changed-word writes, per-word readback, stability wait, full reread, byte/SHA-256/structure/identity-semantic verification, programming, and BIN restore |
| Reset and rediscovery | Three-frame ESC ECAT reset at `0x0040`; bounded rediscovery polling after reset, with rediscovery and reload verification reported separately |
| State diagnostics | Overview shows bus phase, recent communication errors, actual slave state, and AL status; Settings switches AL status language between Chinese and English |
| Page scope | Overview, Registers, EEPROM, and Settings are public in the main navigation; CoE, PDO mapping, and online I/O code remains present but hidden for this release |

## Architecture

```text
React + Material UI + Emotion
              |
              v
        Tauri 2 / Rust
              | persistent JSON channel
              v
       Python Bridge
              |
              v
EtherCatWorker -> Services -> Real/Mock Backend -> pySOEM
```

All requests for one EtherCAT Master are serialized by a single Worker. State checks, confirmations, and verification remain in the Python service layer rather than relying on page state. During EEPROM programming or restore, other hardware commands immediately return `EEPROM_BUSY`; while cyclic communication is running, state controls, reconfigure, recovery, and EEPROM operations are disabled or rejected. A successful `recover()` is followed by actual-state and AL-status verification.

## User guide

### System and Npcap requirements

| Item | Requirement |
| --- | --- |
| Operating system | Windows 10/11 x64 |
| Node.js | 20 or newer, with pnpm or Corepack |
| Python | 3.11 or newer |
| Rust | MSVC toolchain |
| WebView | Windows WebView2 |
| pySOEM | Real mode is pinned to `pysoem==1.1.13` |
| Npcap | Npcap 1.88+, with **WinPcap API-compatible Mode** enabled |
| Adapter | Prefer a dedicated EtherCAT adapter with no ordinary network traffic |

Npcap is not included with the repository or application. Demo mode does not open a physical adapter. In Real mode, missing Npcap/wpcap, permissions, or an unavailable adapter is reported in the UI.

### Install and run

The project is currently source-first. Tauri has `bundle.active=false`, so an installer or GitHub Release artifact is not guaranteed to exist. Run in PowerShell:

```powershell
git clone https://github.com/LINLin190/EtherCAT-Workbench.git
Set-Location "EtherCAT-Workbench\apps\EtherCAT Workbench"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\start-desktop.ps1
```

You can also double-click `Start-EtherCAT-Workbench.cmd`. The launcher prefers global pnpm, a locally cached Corepack version, or Corepack, and before startup removes only project-owned stale Vite processes. Vite uses port `1420`; if an unrelated process owns it, the launcher reports the conflict and leaves that process untouched.

Browser-only layout preview:

```powershell
Set-Location desktop
pnpm install
pnpm dev
```

The browser preview uses Mock data and does not access a physical adapter.

### Interface and recommended workflow

The public workflow is:

```text
1. Detect adapter -> 2. Connect -> 3. Scan -> 4. Select slave
-> 5. Read state and AL -> 6. Register or EEPROM diagnostics
```

| Page | Purpose |
| --- | --- |
| Overview | Bus phase, identity, actual state, AL status, state requests, reconfigure, and recovery |
| Registers | Catalogs, search/categories, reads, fixed monitoring, raw address tool, and two-stage writes |
| EEPROM | ESI/Device target, Smart View, capacity, reads, BIN backup, programming, verification, and restore |
| Settings | Real/Demo mode, AL status language (Chinese/English), and About information |

Recommended sequence:

1. Start with the top bar disconnected; in Real mode, detect and select the EtherCAT adapter.
2. Click **Connect**, then **Scan**, and select the target in the slave tree.
3. Read the Overview state and AL status first. Request states in the required sequence, normally `INIT -> PRE-OP -> SAFE-OP -> OP`; controls are unavailable during cyclic communication.
4. In Registers, read before writing and confirm the slave, catalog, address, current value, and target value. Regenerate plans older than 60 seconds.
5. For EEPROM, stop cyclic communication and put the target in INIT. Back up a BIN first, then select XML/Device, inspect Smart View and capacity, and program or restore.

## AL status codes

Overview reads the ESC standard AL status register `0x0134` and shows the code, name, details, and troubleshooting action. Use **Settings -> AL status language** to switch between Chinese and English; the choice is persisted locally.

| Range/code | Meaning |
| --- | --- |
| `0x0000` | No error |
| `0x0001`-`0x0083`, `0x00F0` (some values reserved) | Built-in common catalog covering firmware/SII, state transitions, mailbox, SyncManager, PDO, watchdog, synchronization, DC, power, temperature, and application-controller conditions |
| `0x8000`-`0xFFFF` | Vendor-specific; the UI does not guess its meaning. Consult the device manual, ESI, and vendor diagnostic objects |
| Other values | Unlisted, reserved, or newer extension candidates; reread `0x0134` and consult device documentation |

Typical diagnostic directions:

| Group | Example codes | First checks |
| --- | --- | --- |
| State/configuration | `0x0011`, `0x0016`, `0x0017`, `0x0021`-`0x0026` | Current/requested state, mailbox, SyncManager, RxPDO/TxPDO, and ESI/SII |
| Watchdog/synchronization | `0x001A`, `0x001B`, `0x002A`, `0x002C`-`0x0037` | Cycle time, WKC, Sync0/Sync1, DC, and firmware task load |
| Mailbox | `0x0041`-`0x0045`, `0x004F` | Protocol, mailbox size, object dictionary, and diagnostic log |
| EEPROM | `0x0050`, `0x0051` | EEPROM control/status/error registers and SII image |
| Power/environment | `0x0080`-`0x0083` | Supply, cooling, environment, and external-ready signals |

The complete bilingual catalog and per-code actions are in [al_status_codes.json](src/ethercat_debug_tool/protocol/al_status_codes.json) and the frontend English mapping.

### `0x0050` EEPROM no access

`0x0050` means **EEPROM no access**: the SII EEPROM is not assigned to the PDI, or the slave firmware cannot obtain the access it requires. This code alone does not prove that PDI has taken ownership or that the EEPROM is locked; `0x0500 == 0` is not positive proof either. Read `0x0500`, `0x0501`, and `0x0502` together, inspect ECAT/PDI ownership and Busy/error bits, and correlate them with the firmware state machine, logs, and captures. `0x0051` is more consistent with an EEPROM read/write, acknowledgement, or verification failure.

When a state transition fails, the backend includes the slave name, actual state, and `0x0134` code in the error. A real INIT-to-PRE-OP failure may still require firmware, PDI-path, or hardware investigation; Demo tests cannot establish the physical cause.

## Write safety

### ESC registers

- Registers are read-only by default. Writing requires a generated plan and explicit confirmation; plans are bound to the current session, full slave identity, and configured address and expire after 60 seconds.
- The current value is reread before writing, and the target slave, address, current value, target value, change mask, and final bytes are shown.
- RW, W1C, W1S, WO, self-clearing, and volatile registers use semantic verification. Unknown raw addresses clearly warn that bit semantics and side effects cannot be determined.
- The raw address tool uses width for both read length and write HEX byte count; mismatched lengths are rejected. Every write is recorded in `AUDIT` logs.
- The LAN9252-compatible profile does not treat error counter `0x0300` as a generic WAC write. A dedicated, safe clear operation is required if counter clearing is later supported.
- ESC ECAT reset at `0x0040` uses an explicitly confirmed exclusive sequence of `0x52`, `0x45`, and `0x53`.

### EEPROM workflow

> [!WARNING]
> EEPROM programming is allowed only with cyclic communication stopped and the target slave in INIT. Any mismatch in readback bytes, SHA-256, SII structure, or XML identity semantics prevents image verification from being reported as successful.

```text
Select XML / Device -> generate complete SII target -> inspect capacity and Smart View
-> back up or read current EEPROM -> write changed words only -> read each word back
-> stability wait -> full reread -> byte/SHA-256/structure/semantic verification
-> optional ESC reset -> bounded rediscovery polling -> reload verification
```

Key rules:

- The target image is generated entirely from the selected XML/Device or BIN. XML text is never written directly, and Serial Number, Station Alias, or private data is not silently merged from the old image.
- Vendor ID, Product Code, and Revision mismatches are warnings. They do not require extra confirmation or independently block programming; the operator must verify the target.
- Invalid XML, failed SII generation, unreadable or mismatched physical capacity, running cyclic communication, a target outside INIT, another EEPROM operation, or communication failure blocks the operation.
- During EEPROM programming or restore, other hardware commands immediately return `EEPROM_BUSY`, avoiding a Host deadline termination during the long operation.
- Cancellation is shown as neutral **Cancelled**, not as a communication failure. Technical details show the `first_difference` offset, and the complete backup path is shown after backup.
- Rediscovery and reload verification after reset are reported separately. Failure to rediscover does not change the completed image byte-verification result.

### ESI -> SII conversion boundary

| Status | Elements |
| --- | --- |
| Supported | ConfigData/CRC-8, Identity, standard Mailbox, Strings, General, FMMU, SyncManager, RxPDO/TxPDO, DC OpMode, standard primitive CoE types, and BIT1-BIT8 |
| Not claimed | Vendor-private Categories, a complete custom DataTypes dictionary, EoE/FoE-specific data, or arbitrary complete ESI Schema coverage |

Unsupported content is reported in the generation report and UI instead of being silently ignored. Smart View shows category name, type, offset, length, and content preview.

## ESC profiles and identification

`chip_model` and `register_family` are stored separately. Profiles include E101, E252, E253, ET1100, LAN9252, LAN9253, and Generic ESC; domestic models are not displayed as the original vendor chips. Identification uses ESI model text or chip-type register `0x0E00`, not guesses from FMMU/SM counts or RAM ranges.

Vendor-private registers, exact `0x0E00` encodings, EEPROM timing, and reset compatibility for E101/E252/E253 have not been verified on physical hardware. Beckhoff and other vendor ESC identification should likewise be checked against real hardware and documentation.

## Developer guide

### Architecture principles

- React pages handle presentation and interaction; Tauri Rust handles desktop lifecycle and bridging.
- Python Bridge is the only hardware entry point; the WebView never calls pySOEM directly.
- EtherCatWorker is the sole Backend owner and serializes hardware requests for one Master.
- Mock and Real Backends share an interface; Mock does not claim physical verification.
- Conditions and verification for EEPROM, registers, and state actions are enforced in services; cyclic communication and EEPROM exclusivity are enforced by the backend.

### Logs and data locations

| Content | Location |
| --- | --- |
| UI logs and progress | In the application window |
| Bridge JSONL logs | `%LOCALAPPDATA%\EtherCATWorkbench\logs` |
| Write audit | Same log directory, marked `AUDIT` |
| EEPROM BIN backup | Full path shown on the EEPROM page after completion |
| Bridge exit diagnostics | stderr and `log_path` shown in the UI, with an action to open the log location |

### Tests and build checks

Automated tests use only the Mock Backend and included ESI/BIN fixtures. They do not open a physical adapter or write real PDO outputs, EEPROM, or registers:

```powershell
python -m ruff check src tests
python -m pytest -q
Set-Location desktop
pnpm build       # TypeScript check + Vite build
pnpm test        # Vitest
```

Current visual acceptance targets are `2560 x 1440` (default), `1920 x 1080`, and `1280 x 720` (minimum window size).

## Current limitations and physical verification

> [!CAUTION]
> Passing Mock tests does not establish physical EtherCAT hardware verification.

- Npcap opening, real state transitions, EEPROM timing, and complex-topology rediscovery after reset require an isolated test device.
- The firmware/PDI paths behind INIT-to-PRE-OP `0x0050`/`0x0051` require device documentation or captures.
- Vendor bit fields, private registers, and exact chip encodings for E101/E252/E253 require datasheets or hardware captures.
- Vendor-private SII Categories and arbitrary complete ESI Schema conversion are outside the current support claim.
- The standard public register catalog does not claim complete coverage of every vendor extension.
- CoE, PDO mapping, and online I/O pages are hidden in this release; their retained backend code is not a public UI commitment.

For first physical contact, use read-only steps: enumerate adapters, connect, scan, read state/AL, read registers, and read and store an EEPROM BIN offline. Confirm that the backup parses and that the equipment is safe before validating writes on an isolated test slave.

## License and contributing

This project uses the [PolyForm Noncommercial License 1.0.0](LICENSE.md). It is source-available software, not open source as defined by the OSI. Personal, educational, research, and other noncommercial use, modification, and distribution are permitted under the license. Commercial products, paid services, commercial internal operations, and paid support require separate written permission. Distributions must retain the complete license, Required Notice, copyright notice, project URL, and a clear description of modifications. Third-party components remain under their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Use [GitHub Issues](https://github.com/LINLin190/EtherCAT-Workbench/issues) for bug reports, feature requests, or clearly labeled physical-hardware read-only validation results. Include reproduction steps, expected/actual behavior, slave and ESC model, ESI file, system environment, and verification method. Do not submit tests that automatically write real EEPROM, PDO outputs, or registers, and do not publish device serial numbers, production configuration, or private ESI files.
