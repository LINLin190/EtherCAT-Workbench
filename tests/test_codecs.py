import pytest

from ethercat_debug_tool.services.pdo_codec import extract_bits, insert_bits
from ethercat_debug_tool.services.sdo_codec import decode_value, encode_value, parse_hex_bytes


def test_sdo_integer_float_bool_and_hex() -> None:
    assert decode_value(encode_value(-123, "INTEGER16"), "INTEGER16") == -123
    assert decode_value(encode_value(1.25, "REAL32"), "REAL32") == pytest.approx(1.25)
    assert encode_value("true", "BOOL") == b"\x01"
    assert parse_hex_bytes("01 0A ff") == b"\x01\x0a\xff"


def test_pdo_offsets_cross_bytes_without_touching_neighbors() -> None:
    original = bytes.fromhex("AA 55 F0")
    changed = insert_bits(original, 7, 9, 0x1A5)
    assert extract_bits(changed, 7, 9) == 0x1A5
    outside_mask = ~(((1 << 9) - 1) << 7) & ((1 << 24) - 1)
    assert (
        int.from_bytes(changed, "little") & outside_mask == int.from_bytes(original, "little") & outside_mask
    )


def test_invalid_ranges_are_rejected() -> None:
    with pytest.raises(ValueError):
        encode_value(256, "UNSIGNED8")
    with pytest.raises(ValueError):
        insert_bits(b"\x00", 5, 4, 0)
