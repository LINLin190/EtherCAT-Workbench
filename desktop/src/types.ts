export type Mode = "real" | "demo";

export interface AdapterInfo {
  name: string;
  description: string;
  volatile?: boolean;
}

export interface SlaveIdentity {
  vendor_id: number;
  product_code: number;
  revision: number;
  serial_number: number;
}

export interface SlaveInfo {
  position: number;
  name: string;
  identity: SlaveIdentity;
  state: number;
  al_status: number;
  input_size: number;
  output_size: number;
  configured_address?: number;
  chip_model: string;
  register_family: string;
}

export interface WorkbenchStatus {
  mode: Mode;
  connected: boolean;
  cycle_running: boolean;
  slaves: SlaveInfo[];
}

export interface AutoScanAttempt {
  adapter: string;
  slave_count: number;
  error?: string;
  disconnect_error?: string;
}

export interface AutoScanResult {
  adapters: AdapterInfo[];
  selected_adapter: string;
  connected: boolean;
  slaves: SlaveInfo[];
  attempts: AutoScanAttempt[];
}

export interface BridgeEvent<T = unknown> {
  kind: string;
  data: T;
}

export interface PdoEntry {
  direction: "rx" | "tx";
  pdo_index: number;
  index: number;
  subindex: number;
  bit_length: number;
  bit_offset: number;
  name?: string;
  data_type?: string;
}

export interface RegisterDefinition {
  address: number;
  size?: number;
  width?: number;
  name: string;
  group: string;
  access: string;
  description: string;
  bit_fields?: { name: string; shift: number; bits: number }[];
}

export interface OperationProgress {
  operation: string;
  stage: string;
  completed: number;
  total: number;
  detail: string;
}

export interface EsiDevice {
  ordinal?: number;
  name: string;
  type_name: string;
  product_code: number;
  revision?: number;
  revision_number?: number;
  serial_number: number;
  group_type?: string;
  eeprom_byte_size?: number;
  byte_size?: number;
  [key: string]: unknown;
}

export const stateLabel = (state: number) =>
  ({ 0: "NONE", 1: "INIT", 2: "PRE-OP", 3: "BOOT", 4: "SAFE-OP", 8: "OP" })[state] ??
  `0x${state.toString(16).toUpperCase()}`;

export const hex = (value: number, width = 4) =>
  `0x${value.toString(16).toUpperCase().padStart(width, "0")}`;
