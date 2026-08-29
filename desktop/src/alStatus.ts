import catalog from "../../src/ethercat_debug_tool/protocol/al_status_codes.json";
import { englishAlStatusNames } from "./alStatusEnglish";

export type AlStatusLanguage = "zh" | "en";

export interface AlStatusInfo {
  name: string;
  detail: string;
  action: string;
  known: boolean;
}

const codes = catalog.codes as Record<string, Omit<AlStatusInfo, "known">>;
const vendorSpecific = catalog.ranges["0x8000-0xFFFF"];
const unknown = catalog.unknown;

export function alStatusInfo(code: number, language: AlStatusLanguage = "zh"): AlStatusInfo {
  const normalized = code & 0xffff;
  const key = `0x${normalized.toString(16).toUpperCase().padStart(4, "0")}`;
  const info = codes[key];
  if (info) {
    if (language === "zh") return { ...info, known: true };
    const name = englishAlStatusNames[key] ?? "Recognized AL status code";
    if (normalized === 0x0050) return {
      name,
      detail: "The SII EEPROM is not assigned to the PDI, or the firmware cannot obtain the EEPROM access it requires.",
      action: "Read 0x0500, 0x0501 and 0x0502 together; inspect ECAT/PDI ownership, Busy/error bits, and the slave firmware state machine.",
      known: true,
    };
    return {
      name,
      detail: normalized === 0 ? "The slave reports no AL status error." : `The slave reported “${name}” while processing its EtherCAT state or configuration.`,
      action: normalized === 0 ? "No action is required." : "Check the current and requested states, AL Status registers, ESI/SII configuration, and the device diagnostic log.",
      known: true,
    };
  }
  if (normalized >= 0x8000) {
    return language === "zh" ? { ...vendorSpecific, known: false } : { name: "Vendor-specific AL status code", detail: "This code is defined by the device vendor, not by the common EtherCAT AL status table.", action: "Consult the device manual, ESI annotations, and vendor diagnostic objects.", known: false };
  }
  return language === "zh" ? { ...unknown, known: false } : { name: "Unlisted AL status code", detail: "This value is not in the current common status table and may be reserved or a newer extension.", action: "Read register 0x0134 and consult the device manual, ESI, and slave log.", known: false };
}

export const standardAlStatusCodeCount = Object.keys(codes).length;
