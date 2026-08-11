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
    assert general.payload[14] == 0x11
    assert "vendor-specific categories" in report.omitted


def test_corrupt_header_and_missing_end_marker_are_rejected(workspace: Path) -> None:
    raw = bytearray((workspace / "ESI示例" / "Box 1 (ET1100_402).bin").read_bytes())
    raw[0] ^= 1
    with pytest.raises(SiiValidationError, match="CRC"):
        SiiParser().parse(raw)
    raw = bytearray((workspace / "ESI示例" / "Box 1 (ET1100_402).bin").read_bytes())
    raw[0x1A4:] = b"\x00" * (len(raw) - 0x1A4)
    with pytest.raises(SiiValidationError, match="end marker"):
        SiiParser().parse(raw)
