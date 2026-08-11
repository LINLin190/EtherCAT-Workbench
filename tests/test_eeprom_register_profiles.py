from dataclasses import replace

import pytest

from ethercat_debug_tool.backends.mock import MockBackend
from ethercat_debug_tool.esc_profiles.profiles import ProfileRegistry, RegisterFamily
from ethercat_debug_tool.models import AccessSemantics
from ethercat_debug_tool.services.eeprom_service import EepromService, compare_images
from ethercat_debug_tool.services.register_service import RegisterService
from ethercat_debug_tool.sii.generator import SiiGenerator


def test_compare_reports_first_byte_and_hash() -> None:
    result = compare_images(b"\x00\x01", b"\x00\x02")
    assert not result.equal and result.differing_bytes == 1 and result.first_difference == 1
    assert result.target_sha256 != result.readback_sha256


def test_mock_flash_forces_backup_and_full_verification(tmp_path, sample_esi) -> None:
    backend = MockBackend()
    backend.connect("demo0")
    try:
        slave = backend.scan()[0]
        device = replace(
            sample_esi.devices[0],
            vendor_id=slave.identity.vendor_id,
            product_code=slave.identity.product_code,
            revision=slave.identity.revision,
        )
        target = SiiGenerator().generate(device).image
        result = EepromService(backend, stability_wait_s=0, rediscovery_wait_s=0).flash(
            1, target, device, tmp_path, slave, auto_reset=True
        )
        assert result.backup.binary_path.exists() and result.backup.metadata_path.exists()
        assert result.bytes_read_back == 2048
        assert result.image_success
        assert result.comparison.target_sha256 == result.comparison.readback_sha256
        assert result.reset_sequence == (True, True, True)
        assert result.rediscovered is True and result.reload_verified is True
    finally:
        backend.disconnect()


def test_profiles_are_distinct_and_not_inferred_from_counts() -> None:
    profiles = ProfileRegistry()
    assert profiles.resolve(esi_type="E252").chip_model == "E252"
    assert profiles.resolve(chip_register=(0xE253).to_bytes(4, "little")).chip_model == "E253"
    assert profiles.get("E101").register_family is RegisterFamily.ET1100_COMPATIBLE
    assert profiles.get("E101").chip_model != "ET1100"
    assert profiles.resolve(esi_type="unknown").chip_model == "Generic ESC"
    al_control = next(item for item in profiles.standard_registers() if item["address"] == 0x0120)
    assert al_control["access"] == "RW" and len(al_control["bit_fields"]) >= 2


def test_register_write_semantics_and_concurrent_change_guard() -> None:
    backend = MockBackend()
    backend.connect("demo0")
    try:
        service = RegisterService(backend)
        plan = service.prepare_write(1, 0x0100, b"\x12\x34", AccessSemantics.RW, True)
        result = service.execute_write(plan)
        assert result.verified and result.readback == b"\x12\x34"
        stale = service.prepare_write(1, 0x0100, b"\x56\x78", AccessSemantics.RW, True)
        backend.register_write(1, 0x0100, b"\x00\x00", 2000)
        with pytest.raises(RuntimeError, match="changed"):
            service.execute_write(stale)
        with pytest.raises(PermissionError):
            service.prepare_write(1, 0x0000, b"\x01", AccessSemantics.RO, True)
    finally:
        backend.disconnect()
