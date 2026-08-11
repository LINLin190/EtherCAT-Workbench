from __future__ import annotations

from ..models import PdoEntry


def extract_bits(data: bytes, bit_offset: int, bit_length: int) -> int:
    if bit_offset < 0 or bit_length <= 0 or bit_offset + bit_length > len(data) * 8:
        raise ValueError("PDO bit range is outside the buffer")
    value = int.from_bytes(data, "little")
    return (value >> bit_offset) & ((1 << bit_length) - 1)


def insert_bits(data: bytes, bit_offset: int, bit_length: int, value: int) -> bytes:
    if bit_offset < 0 or bit_length <= 0 or bit_offset + bit_length > len(data) * 8:
        raise ValueError("PDO bit range is outside the buffer")
    if not 0 <= value < (1 << bit_length):
        raise ValueError(f"Value does not fit in {bit_length} bits")
    current = int.from_bytes(data, "little")
    mask = ((1 << bit_length) - 1) << bit_offset
    current = (current & ~mask) | (value << bit_offset)
    return current.to_bytes(len(data), "little")


def extract_entry(data: bytes, entry: PdoEntry) -> int:
    return extract_bits(data, entry.bit_offset, entry.bit_length)
