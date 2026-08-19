# Desktop architecture

EtherCAT Workbench uses Tauri 2, React, TypeScript, Material UI, and Emotion for its only desktop interface. The Python package is a headless EtherCAT hardware core.

## Runtime

```text
React + MUI + Emotion
        │ typed commands/events
        ▼
Tauri 2 host (Rust)
        │ newline-delimited JSON over private stdio
        ▼
Python bridge process
        │ exclusive requests/events
        ▼
EtherCatWorker → services → Real/Mock backend → pySOEM
```

- The webview never imports or calls pySOEM.
- The Rust host owns one long-lived Python process.
- The Worker remains the sole owner of the EtherCAT Master and serializes all requests.
- Binary data crosses the IPC boundary as uppercase hexadecimal strings.
- Real is the default mode. Demo can only be enabled in Settings and is visibly marked.

## Interface structure

The shell has a compact labeled navigation rail, a contextual slave panel, and one content canvas. The currently visible workspaces are:

1. Overview
2. Registers
3. EEPROM
4. Settings

CoE objects, PDO mapping, and Online I/O remain implemented but are temporarily hidden while the three primary workspaces are refined. On startup, the bridge performs one serialized adapter scan: the last manually selected adapter is tried first, remaining adapters retain enumeration order, and unsuccessful adapters are disconnected before the next attempt.

At 2560×1440 the content is capped at 1840 px. At 1920×1080 it is fluid. The compatibility floor is 1280×720.

## Verification gates

1. TypeScript type-check and Vite production build.
2. Python Ruff and MockBackend tests.
3. Rust `cargo check` and Tauri build.
4. Visual checks at 1920×1080 and 2560×1440.
5. Real-hardware verification before a production release.
