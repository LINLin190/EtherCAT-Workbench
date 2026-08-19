import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ethercat_debug_tool.esi.parser import EsiParser
from ethercat_debug_tool.sii.generator import SiiGenerator
from ethercat_debug_tool.sii.parser import SiiParser, SiiValidationError


def test_sample_esi_device_and_pdo_fields(sample_esi) -> None:
    device = sample_esi.devices[0]
    assert device.name == "ET1100_402"
    assert device.product_code == 0x26483052
    assert device.byte_size == 2048
    assert device.rx_pdos[0].entries[0].bit_length == 16
    assert any(entry.index == 0x1018 and entry.subindex == 1 for entry in device.objects)


def test_one_xml_can_expose_multiple_devices(workspace: Path, tmp_path: Path) -> None:
    root = ET.parse(workspace / "ESI示例" / "SlaveCTT_900e80.xml").getroot()
    devices = next(node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "Devices")
    clone = copy.deepcopy(next(iter(devices)))
    devices.append(clone)
    path = tmp_path / "multi-device.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    assert len(EsiParser().parse(path).devices) == 2


def test_parse_supplied_binary_vector(workspace: Path) -> None:
    raw = (workspace / "ESI示例" / "Box 1 (ET1100_402).bin").read_bytes()
    image = SiiParser().parse(raw)
    assert image.capacity == 2048
    assert image.vendor_id == 9
    assert image.product_code == 0x26483052
    assert image.end_offset % 2 == 0
    assert {category.kind for category in image.categories} >= {0x0A, 0x1E, 0x28, 0x29, 0x32, 0x33, 0x3C}


def test_generate_complete_image_and_semantic_roundtrip(sample_esi) -> None:
    device = sample_esi.devices[0]
    report = SiiGenerator().generate(device)
    image = SiiParser().parse(report.image)
    assert len(report.image) == device.byte_size
    assert (image.vendor_id, image.product_code, image.revision) == (
        device.vendor_id,
        device.product_code,
        device.revision,
    )
    assert report.image[image.end_offset : image.end_offset + 2] == b"\xff\xff"
    general = next(category for category in image.categories if category.kind == 0x001E)
    assert general.payload[16] == 0x11
    assert "vendor-specific categories" in report.omitted


def test_mailbox_fixed_area_follows_standard_layout(sample_esi) -> None:
    import struct

    device = sample_esi.devices[0]
    image = SiiGenerator().generate(device).image
    # Standard mailbox: MBoxOut 0x1000/128 at 0x30, MBoxIn 0x1100/128 at 0x34.
    assert image[0x30:0x32] == (0x1000).to_bytes(2, "little")
    assert image[0x32:0x34] == (128).to_bytes(2, "little")
    assert image[0x34:0x36] == (0x1100).to_bytes(2, "little")
    assert image[0x36:0x38] == (128).to_bytes(2, "little")
    # Bootstrap mailbox comes from the ESI BootStrap hex at 0x28.
    assert image[0x28:0x30] == bytes.fromhex("0010800080108000")
    # CoE-only mailbox; the bootstrap protocol word mirrors the standard one.
    assert image[0x38:0x3A] == (0x0004).to_bytes(2, "little")
    assert image[0x3A:0x3C] == (0x0004).to_bytes(2, "little")
    # Reserved fixed area is zero-filled like SSC-generated images; the
    # EEPROM size word sits at 0x7C.
    assert image[0x20:0x28] == b"\x00" * 8
    assert image[0x3C:0x7C] == b"\x00" * (0x7C - 0x3C)
    assert image[0x7C:0x80] == struct.pack("<HH", 2048 // 128 - 1, 1)


def test_sync_manager_category_uses_standard_type_codes(sample_esi) -> None:
    import struct

    report = SiiGenerator().generate(sample_esi.devices[0])
    image = SiiParser().parse(report.image)
    sm = next(category for category in image.categories if category.kind == 0x0029)
    types = [struct.unpack_from("<HHBBBB", sm.payload, offset)[5] for offset in range(0, len(sm.payload), 8)]
    assert types == [1, 2, 3, 4]


def test_pdo_header_uses_uint16_name_and_flags_follow(sample_esi) -> None:
    import struct
    from dataclasses import replace

    from ethercat_debug_tool.esi.parser import EsiEntry, EsiPdo

    device = replace(
        sample_esi.devices[0],
        byte_size=2048,
        tx_pdos=(
            EsiPdo(0x1A00, "DI TxPDO-Map", 3, (EsiEntry(0x6041, 0, 16, "Status", "UINT", 0x0010),), 0x0011),
        ),
        rx_pdos=(),
        dc_modes=(),
    )
    report = SiiGenerator().generate(device)
    image = SiiParser().parse(report.image)
    category = next(category for category in image.categories if category.kind == 0x0032)
    index, entries, sm, name, flags = struct.unpack_from("<HBBHH", category.payload, 0)
    assert (index, entries, sm, flags) == (0x1A00, 1, 3, 0x0011)
    assert name >= 1
    entry_index, subindex, _, _, bit_length, entry_flags = struct.unpack_from("<HBBBBH", category.payload, 8)
    assert (entry_index, subindex, bit_length, entry_flags) == (0x6041, 0, 16, 0x0010)


def test_dc_entry_layout_matches_etg2010() -> None:
    import struct

    from ethercat_debug_tool.esi.parser import EsiDcMode

    class Strings:
        @staticmethod
        def index(value):
            return 1 if value else 0

    mode = EsiDcMode("DC", "DC-Synchron", 0x0300, 1_000_000, 500, 2_000_000, -250, 1, 2)
    payload = SiiGenerator._dc(mode, Strings())
    assert len(payload) == 24
    unpacked = struct.unpack("<IHiIHiHBB", payload)
    assert unpacked == (1_000_000, 1, 500, 2_000_000, 2, -250, 0x0300, 1, 1)


def test_corrupt_header_and_missing_end_marker_are_rejected(workspace: Path) -> None:
    raw = bytearray((workspace / "ESI示例" / "Box 1 (ET1100_402).bin").read_bytes())
    raw[0] ^= 1
    with pytest.raises(SiiValidationError, match="CRC"):
        SiiParser().parse(raw)
    raw = bytearray((workspace / "ESI示例" / "Box 1 (ET1100_402).bin").read_bytes())
    raw[0x1A4:] = b"\x00" * (len(raw) - 0x1A4)
    with pytest.raises(SiiValidationError, match="end marker"):
        SiiParser().parse(raw)


def test_large_lyw_esi_generates_capacity_safe_sii(workspace: Path) -> None:
    import struct

    document = EsiParser().parse(workspace / "LYW_CanMotor_SIP-V2.2" / "XHD_CAN_Motor_18x8.xml")
    device = document.devices[0]

    report = SiiGenerator().generate(device)
    image = SiiParser().parse(report.image)
    raw = report.image

    assert len(report.image) == 2048
    assert (image.vendor_id, image.product_code, image.revision) == (0x153, 1, 1)
    # Standard mailbox: MBoxOut 0x1000/128, MBoxIn 0x1080/128, CoE protocol.
    assert raw[0x30:0x32] == (0x1000).to_bytes(2, "little")
    assert raw[0x32:0x34] == (128).to_bytes(2, "little")
    assert raw[0x34:0x36] == (0x1080).to_bytes(2, "little")
    assert raw[0x36:0x38] == (128).to_bytes(2, "little")
    assert raw[0x38:0x3A] == (0x0004).to_bytes(2, "little")
    assert raw[0x3A:0x3C] == b"\x00\x00"
    # No BootStrap in the LYW ESI: the bootstrap mailbox area stays zero.
    assert raw[0x28:0x30] == b"\x00" * 8
    # Sync Manager category keeps the standard type codes.
    sm = next(category for category in image.categories if category.kind == 0x0029)
    types = [struct.unpack_from("<HHBBBB", sm.payload, offset)[5] for offset in range(0, len(sm.payload), 8)]
    assert types == [1, 2, 3, 4]
    # DC category: both modes with ETG.2010 layout and factors.
    dc = next(category for category in image.categories if category.kind == 0x003C)
    first = struct.unpack_from("<IHiIHiHBB", dc.payload, 0)
    second = struct.unpack_from("<IHiIHiHBB", dc.payload, 24)
    assert first[6] == 0x0000 and first[1] == 1 and first[4] == 1
    assert second[6] == 0x0300 and second[1] == 1 and second[4] == 1
    # 367 unique PDO entry names cannot fit the 255-entry SII string table,
    # and even the nameless PDO encoding exceeds 2048 bytes: PDO categories
    # are omitted and the report states the measured reason.
    assert not ({0x0032, 0x0033} & {category.kind for category in image.categories})
    assert any("PDO categories omitted" in item for item in report.omitted)
    assert any("2048" in item for item in report.omitted)


def test_pdo_names_dropped_before_categories_when_strings_exceed_limit(sample_esi) -> None:
    import struct
    from dataclasses import replace

    from ethercat_debug_tool.esi.parser import EsiEntry, EsiPdo

    pdos = tuple(
        EsiPdo(
            0x1A00 + index,
            f"Big TxPDO {index}",
            3,
            tuple(
                EsiEntry(0x6000, slot + 1, 8, f"UNIQUE_ENTRY_{index}_{slot:03d}", "USINT", 0)
                for slot in range(100)
            ),
            0x0001,
        )
        for index in range(3)
    )
    device = replace(
        sample_esi.devices[0],
        byte_size=8192,
        tx_pdos=pdos,
        rx_pdos=(),
        dc_modes=(),
    )
    report = SiiGenerator().generate(device)
    image = SiiParser().parse(report.image)
    category = next(category for category in image.categories if category.kind == 0x0032)
    assert len(category.payload) == 3 * (8 + 100 * 8)
    # Entries survive with empty name indices once the string table is full.
    assert struct.unpack_from("<HBBBBH", category.payload, 8 + 5 * 8)[2] == 0
    assert any("names omitted" in item for item in report.omitted)
    assert "PDO" in report.supported
