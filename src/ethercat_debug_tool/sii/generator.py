from __future__ import annotations

import struct
from dataclasses import dataclass

from ..esi.parser import EsiDcMode, EsiDevice, EsiEntry, EsiPdo, EsiSyncManager
from .parser import SiiParser, crc8

DATA_TYPES = {
    "BOOL": 0x01,
    "SINT": 0x02,
    "INT": 0x03,
    "DINT": 0x04,
    "USINT": 0x05,
    "UINT": 0x06,
    "UDINT": 0x07,
    "REAL": 0x08,
    "STRING": 0x09,
    "LINT": 0x15,
    "ULINT": 0x1B,
    "LREAL": 0x11,
    "BIT1": 0x30,
    "BIT2": 0x31,
    "BIT3": 0x32,
    "BIT4": 0x33,
    "BIT5": 0x34,
    "BIT6": 0x35,
    "BIT7": 0x36,
    "BIT8": 0x37,
}


@dataclass(frozen=True, slots=True)
class SiiGenerationReport:
    image: bytes
    supported: tuple[str, ...]
    omitted: tuple[str, ...]


class _Strings:
    def __init__(self) -> None:
        self.values: list[str] = []

    def index(self, value: str) -> int:
        if not value:
            return 0
        clean = value.encode("latin-1", errors="replace")[:255].decode("latin-1")
        if clean not in self.values:
            self.values.append(clean)
        return self.values.index(clean) + 1

    def payload(self) -> bytes:
        chunks = [bytes([len(self.values)])]
        for value in self.values:
            encoded = value.encode("latin-1")
            chunks.append(bytes([len(encoded)]) + encoded)
        return b"".join(chunks)


class SiiGenerator:
    """Converts the supported standard ESI subset into a complete SII image."""

    def generate(self, device: EsiDevice) -> SiiGenerationReport:
        capacity = device.byte_size
        if capacity < 128 or capacity % 128:
            raise ValueError("EEPROM ByteSize must be a positive multiple of 128")
        image = bytearray(b"\xff" * capacity)
        config = device.config_data[:10].ljust(10, b"\x00") + b"\x00" * 4
        image[:14] = config
        image[14] = crc8(config)
        image[15] = 0
        struct.pack_into(
            "<IIII", image, 0x10, device.vendor_id, device.product_code, device.revision, device.serial_number
        )
        if device.bootstrap:
            image[0x28:0x30] = device.bootstrap[:8].ljust(8, b"\x00")
        if device.sync_managers:
            for sm in device.sync_managers[:2]:
                if sm.kind.lower() == "mailboxout":
                    struct.pack_into("<HH", image, 0x30, sm.start_address, sm.default_size)
                elif sm.kind.lower() == "mailboxin":
                    struct.pack_into("<HH", image, 0x34, sm.start_address, sm.default_size)
        struct.pack_into("<H", image, 0x38, device.mailbox_protocol)
        struct.pack_into("<HH", image, 0x7C, capacity // 128 - 1, 1)

        strings = _Strings()
        group_index = strings.index(device.group_type)
        image_index = 0
        order_index = strings.index(device.type_name)
        name_index = strings.index(device.name)
        for pdo in (*device.tx_pdos, *device.rx_pdos):
            strings.index(pdo.name)
            for entry in pdo.entries:
                strings.index(entry.name)
        for mode in device.dc_modes:
            strings.index(mode.name)
            strings.index(mode.description)

        categories: list[tuple[int, bytes]] = [(0x000A, strings.payload())]
        general = bytearray(32)
        general[0:4] = bytes([group_index, image_index, order_index, name_index])
        general[5] = device.coe_details & 0xFF
        general[11:13] = struct.pack("<H", device.general_flags)
        general[14] = self._physical_port(device.physics)
        categories.append((0x001E, bytes(general)))
        if device.fmmu:
            mapping = {"outputs": 2, "inputs": 1, "mboxstate": 3}
            categories.append((0x0028, bytes(mapping.get(x.strip().lower(), 0) for x in device.fmmu)))
        if device.sync_managers:
            categories.append((0x0029, b"".join(self._sm(sm) for sm in device.sync_managers)))
        if device.mailbox_protocol:
            categories.append((0x002B, b"\xff\xff"))
        if device.tx_pdos:
            categories.append((0x0032, self._pdos(device.tx_pdos, strings)))
        if device.rx_pdos:
            categories.append((0x0033, self._pdos(device.rx_pdos, strings)))
        if device.dc_modes:
            categories.append((0x003C, b"".join(self._dc(mode, strings) for mode in device.dc_modes)))

        offset = SiiParser.CATEGORY_START
        for kind, payload in categories:
            if len(payload) % 2:
                payload += b"\x00"
            encoded = struct.pack("<HH", kind, len(payload) // 2) + payload
            if offset + len(encoded) + 2 > capacity:
                raise ValueError(f"Generated SII image exceeds EEPROM capacity at category 0x{kind:04X}")
            image[offset : offset + len(encoded)] = encoded
            offset += len(encoded)
        image[offset : offset + 2] = b"\xff\xff"
        result = bytes(image)
        SiiParser().parse(result)
        return SiiGenerationReport(
            result,
            (
                "ConfigData header",
                "identity",
                "mailbox",
                "strings",
                "general",
                "FMMU",
                "SyncManager",
                "PDO",
                "DC",
            ),
            (
                "vendor-specific categories",
                "EoE/FoE protocol-specific data",
                "explicit ESI DataTypes dictionary",
            ),
        )

    @staticmethod
    def _physical_port(physics: str) -> int:
        mapping = {"Y": 1, "K": 2, "H": 3}
        value = 0
        # ESI lists physical ports 0,1,2,3; the SII descriptor stores 0,3,1,2.
        shifts = (0, 4, 6, 2)
        for index, character in enumerate(physics[:4]):
            value |= mapping.get(character.upper(), 0) << shifts[index]
        return value

    @staticmethod
    def _sm(sm: EsiSyncManager) -> bytes:
        kind = sm.kind.lower()
        sm_type = {"mailboxout": 1, "mailboxin": 2, "outputs": 3, "inputs": 4}.get(kind, 0)
        return struct.pack(
            "<HHBBBB", sm.start_address, sm.default_size, sm.control_byte, 0, int(sm.enable), sm_type
        )

    @staticmethod
    def _entry(entry: EsiEntry, strings: _Strings) -> bytes:
        data_type = DATA_TYPES.get((entry.data_type or "").upper(), 0)
        return struct.pack(
            "<HBBBBH",
            entry.index,
            entry.subindex,
            strings.index(entry.name),
            data_type,
            entry.bit_length,
            entry.flags,
        )

    def _pdos(self, pdos: tuple[EsiPdo, ...], strings: _Strings) -> bytes:
        chunks = []
        for pdo in pdos:
            sm = 0xFF if pdo.sync_manager is None else pdo.sync_manager
            chunks.append(
                struct.pack("<HBBBBH", pdo.index, len(pdo.entries), sm, 0, strings.index(pdo.name), pdo.flags)
            )
            chunks.extend(self._entry(entry, strings) for entry in pdo.entries)
        return b"".join(chunks)

    @staticmethod
    def _dc(mode: EsiDcMode, strings: _Strings) -> bytes:
        return struct.pack(
            "<IIiIiHBB",
            mode.cycle_time_sync0,
            0,
            mode.shift_time_sync0,
            mode.cycle_time_sync1,
            mode.shift_time_sync1,
            mode.assign_activate,
            strings.index(mode.name),
            strings.index(mode.description),
        )
