import { describe, expect, it } from "vitest";
import {
  decodeConfigData, fixedEsiKey, loadEepromAutoReset, loadFixedEsiState, loadFlashHistory, loadQuickFlashTab,
  normalizeConfigData, pdiMeaning, saveEepromAutoReset, saveFixedEsiState, saveFlashHistory, saveQuickFlashTab,
  type FixedEsiEntry, type FlashHistoryEntry,
} from "./eepromConfig";

describe("EEPROM ConfigData helpers", () => {
  it("decodes the ten-byte configuration area", () => {
    const decoded = decodeConfigData("05 0E 03 44 0A 00 00 00 00 00");
    expect(decoded).toMatchObject({
      pdiCode: 0x05,
      pdiLabel: "Beckhoff SPI",
      escConfiguration: 0x0E,
      pdiConfiguration: 0x03,
      syncLatchConfiguration: 0x44,
      syncPulse: 0x000A,
      extendedPdiConfiguration: 0,
      stationAlias: 0,
    });
  });

  it("uses one common PDI vocabulary for every ESC", () => {
    expect(pdiMeaning(0x05)).toBe("Beckhoff SPI");
    expect(pdiMeaning(0x80)).toBe("SPI-LAN9252 Compat");
    expect(pdiMeaning(0x82)).toBe("SPI-ECAT DirectMap");
    expect(pdiMeaning(0x8D)).toBe("HBI Index 16bit");
    expect(pdiMeaning(0x95)).toBe("HBI Index 16bit DirectMap");
    expect(pdiMeaning(0xFF)).toBe("含义未收录");
  });

  it("normalizes compact hex and rejects non-ten-byte input", () => {
    expect(normalizeConfigData("8d0e03440a0000000000").formatted).toBe("8D 0E 03 44 0A 00 00 00 00 00");
    expect(normalizeConfigData("05 0E").error).toContain("10 byte");
  });

  it("keeps the effective ConfigData in recent flash history", () => {
    let stored = "";
    const storage = { setItem: (_key: string, value: string) => { stored = value; } };
    const entry: FlashHistoryEntry = {
      path: "C:\\device.xml", documentSha256: "abc", ordinal: 0, deviceName: "Device",
      vendorId: 1, productCode: 2, revision: 3, byteSize: 2048,
      originalConfigData: "05 0E 03 44 0A 00 00 00 00 00",
      effectiveConfigData: "8D 0E 03 44 0A 00 00 00 00 00",
      flashedAt: "2026-09-02T00:00:00Z", slaveKey: "slave",
    };
    const result = saveFlashHistory(entry, storage, []);
    expect(result[0].effectiveConfigData).toBe(entry.effectiveConfigData);
    expect(JSON.parse(stored)[0].path).toBe(entry.path);
  });

  it("keeps at most twenty recent flash records", () => {
    const entries = Array.from({ length: 21 }, (_, index): FlashHistoryEntry => ({
      path: `C:\\device-${index}.xml`, documentSha256: String(index), ordinal: 0, deviceName: `Device ${index}`,
      vendorId: 1, productCode: index, revision: 1, byteSize: 2048,
      originalConfigData: "05 0E 03 44 0A 00 00 00 00 00",
      effectiveConfigData: "05 0E 03 44 0A 00 00 00 00 00",
      flashedAt: "2026-09-02T00:00:00Z", slaveKey: `slave-${index}`,
    }));
    const storage = { getItem: () => JSON.stringify(entries) };
    expect(loadFlashHistory(storage)).toHaveLength(20);
    expect(loadFlashHistory(storage).at(-1)?.path).toBe("C:\\device-19.xml");
  });

  it("persists fixed entries, removed entries, and the selected tab", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    const favorite: FixedEsiEntry = {
      path: "C:\\device.xml", sha256: "abc", vendor_id: 1, vendor_name: "Vendor", ordinal: 0,
      device_name: "Device", type_name: "Device", product_code: 2, revision: 3, byte_size: 2048,
      config_data: "8D 0E 03 44 0A 00 00 00 00 00",
    };
    saveFixedEsiState({ favorites: [favorite], hidden: [fixedEsiKey(favorite)] }, storage);
    expect(loadFixedEsiState(storage)).toEqual({ favorites: [favorite], hidden: ["c:\\device.xml|0"] });
    expect(saveQuickFlashTab(1, storage)).toBe(1);
    expect(loadQuickFlashTab(storage)).toBe(1);
  });

  it("defaults EEPROM auto reset to enabled and persists an explicit choice", () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    expect(loadEepromAutoReset(storage)).toBe(true);
    expect(saveEepromAutoReset(false, storage)).toBe(false);
    expect(loadEepromAutoReset(storage)).toBe(false);
    expect(saveEepromAutoReset(true, storage)).toBe(true);
    expect(loadEepromAutoReset(storage)).toBe(true);
  });
});
