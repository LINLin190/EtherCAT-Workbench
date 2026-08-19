import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import type { AdapterInfo, AutoScanResult, BridgeEvent, EsiDevice, Mode, SlaveInfo, WorkbenchStatus } from "./types";

const isTauri = "__TAURI_INTERNALS__" in window;
type Handler = (event: BridgeEvent) => void;

const demoSlaves: SlaveInfo[] = [
  {
    position: 1,
    name: "EL1809 Digital Input",
    identity: { vendor_id: 2, product_code: 0x07113052, revision: 0x00120000, serial_number: 0 },
    state: 2,
    al_status: 0,
    input_size: 2,
    output_size: 0,
    configured_address: 1001,
    chip_model: "ET1100",
    register_family: "ET1100",
  },
  {
    position: 2,
    name: "EL2008 Digital Output",
    identity: { vendor_id: 2, product_code: 0x07d83052, revision: 0x00110000, serial_number: 0 },
    state: 2,
    al_status: 0,
    input_size: 0,
    output_size: 1,
    configured_address: 1002,
    chip_model: "ET1200",
    register_family: "ET1100",
  },
  {
    position: 3,
    name: "Servo Drive",
    identity: { vendor_id: 0x11111111, product_code: 0x00006010, revision: 0x00010000, serial_number: 42 },
    state: 2,
    al_status: 0,
    input_size: 16,
    output_size: 16,
    configured_address: 1003,
    chip_model: "LAN9252",
    register_family: "LAN9252",
  },
];

class PreviewBridge {
  mode: Mode = "demo";
  connected = true;
  running = false;
  scanned: SlaveInfo[] = structuredClone(demoSlaves);
  handlers = new Set<Handler>();

  emit(kind: string, data: unknown) {
    this.handlers.forEach((handler) => handler({ kind, data }));
  }

  async request<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    await new Promise((resolve) => setTimeout(resolve, method === "scan" || method === "auto_scan" ? 450 : 120));
    switch (method) {
      case "status":
        return { mode: this.mode, connected: this.connected, cycle_running: this.running, slaves: this.scanned } as T;
      case "switch_mode":
        this.mode = String(params.mode) as Mode;
        return { mode: this.mode } as T;
      case "enumerate_adapters":
        return [{ name: "preview0", description: "Intel(R) Ethernet Controller I225-V" }] as T;
      case "auto_scan": {
        const adapters = [{ name: "preview0", description: "Intel(R) Ethernet Controller I225-V" }];
        this.connected = true;
        this.scanned = structuredClone(demoSlaves);
        return {
          adapters,
          selected_adapter: "preview0",
          connected: true,
          slaves: this.scanned,
          attempts: [{ adapter: "preview0", slave_count: this.scanned.length }],
        } satisfies AutoScanResult as T;
      }
      case "connect":
        this.connected = true;
        return { connected: true } as T;
      case "disconnect":
        this.connected = false;
        this.running = false;
        this.scanned = [];
        return { connected: false } as T;
      case "scan":
        this.scanned = structuredClone(demoSlaves);
        this.emit("slaves_changed", this.scanned);
        return this.scanned as T;
      case "read_states":
        return this.scanned as T;
      case "request_state": {
        const position = Number(params.position ?? 0);
        const state = Number(params.state);
        this.scanned = this.scanned.map((slave) =>
          position === 0 || position === slave.position ? { ...slave, state } : slave,
        );
        this.emit("slaves_changed", this.scanned);
        return this.scanned as T;
      }
      case "object_dictionary":
        return [
          { index: 0x1000, subindex: 0, name: "Device type", data_type: "UNSIGNED32", bit_length: 32, access: "RO", source: "online" },
          { index: 0x1018, subindex: 1, name: "Vendor ID", data_type: "UNSIGNED32", bit_length: 32, access: "RO", source: "online" },
          { index: 0x6040, subindex: 0, name: "Controlword", data_type: "UNSIGNED16", bit_length: 16, access: "RW", source: "online" },
        ] as T;
      case "sdo_read":
        return { data: "11 22 33 44" } as T;
      case "sdo_write":
        return { data: params.data, readback: params.data, verified: true } as T;
      case "pdo_mapping":
        return {
          rx: [{ direction: "rx", pdo_index: 0x1600, index: 0x7000, subindex: 1, bit_length: 8, bit_offset: 0, name: "Outputs", data_type: "UNSIGNED8" }],
          tx: [{ direction: "tx", pdo_index: 0x1a00, index: 0x6000, subindex: 1, bit_length: 16, bit_offset: 0, name: "Inputs", data_type: "UNSIGNED16" }],
        } as T;
      case "start_cycle":
        this.running = true;
        this.emit("cycle_started", this.scanned.map((slave) => ({ ...slave, state: 8 })));
        window.setTimeout(() => this.emit("process_data", {
          inputs: ["34 12", "", "08 00 00 00"], outputs: ["", "01", "0F 00 00 00"],
          actual_wkc: 6, expected_wkc: 6, cycle_count: 18420, timeout_count: 0,
          wkc_error_count: 0, consecutive_errors: 0, timestamp: Date.now() / 1000,
        }), 250);
        return { running: true } as T;
      case "stop_cycle":
        this.running = false;
        this.emit("cycle_stopped", this.scanned.map((slave) => ({ ...slave, state: 4 })));
        return { running: false, slaves: this.scanned } as T;
      case "set_output":
        return { applied: true, data: params.data } as T;
      case "register_catalog":
        return [
          { address: 0x0000, size: 1, name: "Type", group: "标识", access: "RO", description: "ESC 类型" },
          { address: 0x0130, size: 2, name: "AL Status", group: "状态机", access: "RO", description: "当前 EtherCAT AL 状态" },
          { address: 0x0134, size: 2, name: "AL Status Code", group: "状态机", access: "RO", description: "最近一次 AL 错误码" },
          { address: 0x0300, size: 8, name: "Invalid Frame Counter", group: "链路诊断", access: "RO", description: "各端口无效帧计数" },
        ] as T;
      case "register_read":
        return { position: params.position, address: params.address, data: "08 00", wkc: 1, duration_ms: 0.38, timestamp: Date.now() / 1000 } as T;
      case "register_watch": {
        const requests = Array.isArray(params.requests) ? params.requests as Array<Record<string, unknown>> : [];
        return requests.map((request) => ({
          position: params.position,
          address: request.address,
          data: Number(request.length ?? 2) === 1 ? "08" : "08 00",
          wkc: 1,
          duration_ms: 0.31,
          timestamp: Date.now() / 1000,
        })) as T;
      }
      case "register_prepare_write":
        return {
          plan_id: "preview-register-plan",
          plan: { current: "00 00", target: params.data, changed_mask: "FF FF" },
        } as T;
      case "register_execute_write":
        return { fpwr_wkc: 1, readback: "01 00", verified: true, conclusion: "写入后回读一致" } as T;
      case "register_reset":
        return { reset_sequence: [true, true, true] } as T;
      case "esi_load": {
        const device: EsiDevice = { name: "Demo EtherCAT Device", type_name: "Demo-IO", product_code: 0x12345678, revision_number: 0x00010000, serial_number: 0, eeprom_byte_size: 2048 };
        return { document_id: "preview-document", path: params.path, sha256: "preview", vendor_id: 2, vendor_name: "Demo Automation", devices: [device] } as T;
      }
      case "sii_generate":
        return { target_id: "preview-target", size: 2048, sha256: "9f3b…d120", supported: ["Identity", "Strings", "PDO", "FMMU", "SyncM"], omitted: ["Vendor category 0x9000"], device: { name: "Demo EtherCAT Device", product_code: 0x12345678, revision_number: 0x10000 } } as T;
      case "eeprom_read":
        return {
          data: "FF ".repeat(2048).trim(),
          size: 2048,
          sha256: "9f3b…d120",
          read_at: new Date().toISOString(),
          sii_valid: true,
          identity: { vendor_id: 2, product_code: 0x12345678, revision: 0x00010000, serial_number: 0 },
          category_count: 6,
          categories: [10, 30, 40, 41, 42, 50],
          end_offset: 1536,
          comparison: {
            equal: true,
            differing_bytes: 0,
            target_sha256: "9f3b…d120",
            readback_sha256: "9f3b…d120",
          },
        } as T;
      case "eeprom_capacity":
        return { size: 2048 } as T;
      case "eeprom_backup":
        return { binary_path: `${params.directory}\\slave-2-eeprom.bin`, size: 2048, sha256: "6ad4…51c2" } as T;
      case "eeprom_flash":
      case "eeprom_restore":
        for (const completed of [10, 35, 68, 100]) {
          this.emit("progress", { operation: "flash", stage: completed < 100 ? "写入 EEPROM" : "校验完成", completed, total: 100, detail: `${completed}%` });
        }
        return {
          success: true,
          result: {
            bytes_read_back: 2048,
            words_written: 1024,
            comparison: {
              equal: true,
              differing_bytes: 0,
              target_sha256: "9f3b…d120",
              readback_sha256: "9f3b…d120",
            },
            sii_valid: true,
            semantic_valid: true,
            image_verification: "完整镜像与语义校验通过",
            reset_sequence: [true, true, true],
            rediscovered: true,
            reload_verified: true,
          },
          slaves: this.scanned,
        } as T;
      case "cancel":
        return { cancelled: true } as T;
      default:
        return {} as T;
    }
  }
}

const preview = new PreviewBridge();

export async function bridgeRequest<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!isTauri) return preview.request<T>(method, params);
  return invoke<T>("bridge_request", { method, params });
}

export async function onBridgeEvent(handler: Handler): Promise<UnlistenFn> {
  if (!isTauri) {
    preview.handlers.add(handler);
    return () => preview.handlers.delete(handler);
  }
  return listen<BridgeEvent>("bridge-event", (event) => handler(event.payload));
}

export async function pickFile(extensions: string[]): Promise<string | null> {
  if (!isTauri) return `C:\\EtherCAT\\device.${extensions[0]}`;
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({ multiple: false, filters: [{ name: "支持的文件", extensions }] });
  return typeof selected === "string" ? selected : null;
}

export async function pickDirectory(): Promise<string | null> {
  if (!isTauri) return "C:\\EtherCAT\\Backups";
  const { open } = await import("@tauri-apps/plugin-dialog");
  const selected = await open({ directory: true, multiple: false });
  return typeof selected === "string" ? selected : null;
}

export async function revealPath(path: string): Promise<void> {
  if (!isTauri) return;
  await invoke("reveal_path", { path });
}

export async function openExternal(url: string): Promise<void> {
  if (!isTauri) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }
  await invoke("open_external", { url });
}

export const previewMode = !isTauri;
export type { AdapterInfo, WorkbenchStatus };
