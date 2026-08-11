from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DataTypeSpec:
    name: str
    bits: int | None
    struct_format: str | None
    minimum: int | float | None = None
    maximum: int | float | None = None


_SPECS = {
    "BOOL": DataTypeSpec("BOOL", 1, None, 0, 1),
    "BOOLEAN": DataTypeSpec("BOOLEAN", 1, None, 0, 1),
    "SINT": DataTypeSpec("SINT", 8, "b", -128, 127),
    "INTEGER8": DataTypeSpec("INTEGER8", 8, "b", -128, 127),
    "USINT": DataTypeSpec("USINT", 8, "B", 0, 255),
    "UNSIGNED8": DataTypeSpec("UNSIGNED8", 8, "B", 0, 255),
    "INT": DataTypeSpec("INT", 16, "h", -(2**15), 2**15 - 1),
    "INTEGER16": DataTypeSpec("INTEGER16", 16, "h", -(2**15), 2**15 - 1),
    "UINT": DataTypeSpec("UINT", 16, "H", 0, 2**16 - 1),
    "UNSIGNED16": DataTypeSpec("UNSIGNED16", 16, "H", 0, 2**16 - 1),
    "DINT": DataTypeSpec("DINT", 32, "i", -(2**31), 2**31 - 1),
    "INTEGER32": DataTypeSpec("INTEGER32", 32, "i", -(2**31), 2**31 - 1),
    "UDINT": DataTypeSpec("UDINT", 32, "I", 0, 2**32 - 1),
    "UNSIGNED32": DataTypeSpec("UNSIGNED32", 32, "I", 0, 2**32 - 1),
    "LINT": DataTypeSpec("LINT", 64, "q", -(2**63), 2**63 - 1),
    "INTEGER64": DataTypeSpec("INTEGER64", 64, "q", -(2**63), 2**63 - 1),
    "ULINT": DataTypeSpec("ULINT", 64, "Q", 0, 2**64 - 1),
    "UNSIGNED64": DataTypeSpec("UNSIGNED64", 64, "Q", 0, 2**64 - 1),
    "REAL": DataTypeSpec("REAL", 32, "f"),
    "REAL32": DataTypeSpec("REAL32", 32, "f"),
    "LREAL": DataTypeSpec("LREAL", 64, "d"),
    "REAL64": DataTypeSpec("REAL64", 64, "d"),
    "VISIBLE_STRING": DataTypeSpec("VISIBLE_STRING", None, None),
    "STRING": DataTypeSpec("STRING", None, None),
    "OCTET_STRING": DataTypeSpec("OCTET_STRING", None, None),
}


def normalize_type(name: str) -> str:
    upper = name.strip().upper()
    if upper.startswith("STRING("):
        return "STRING"
    return upper


def spec_for(name: str) -> DataTypeSpec | None:
    return _SPECS.get(normalize_type(name))


def decode_value(data: bytes, data_type: str) -> Any:
    key = normalize_type(data_type)
    if key in {"VISIBLE_STRING", "STRING"}:
        return data.rstrip(b"\x00").decode("utf-8", errors="replace")
    if key == "OCTET_STRING":
        return bytes(data)
    if key in {"BOOL", "BOOLEAN"}:
        return bool(data[0] & 1) if data else False
    spec = _SPECS.get(key)
    if spec is None or spec.struct_format is None:
        raise ValueError(f"Unsupported data type: {data_type}")
    expected = struct.calcsize("<" + spec.struct_format)
    if len(data) != expected:
        raise ValueError(f"{spec.name} requires {expected} bytes, got {len(data)}")
    return struct.unpack("<" + spec.struct_format, data)[0]


def encode_value(value: Any, data_type: str) -> bytes:
    key = normalize_type(data_type)
    if key in {"VISIBLE_STRING", "STRING"}:
        return str(value).encode("utf-8")
    if key == "OCTET_STRING":
        if not isinstance(value, (bytes, bytearray)):
            raise ValueError("OCTET_STRING requires bytes")
        return bytes(value)
    if key in {"BOOL", "BOOLEAN"}:
        if value in (True, 1, "1", "true", "True"):
            return b"\x01"
        if value in (False, 0, "0", "false", "False"):
            return b"\x00"
        raise ValueError("BOOL value must be true/false or 1/0")
    spec = _SPECS.get(key)
    if spec is None or spec.struct_format is None:
        raise ValueError(f"Unsupported data type: {data_type}")
    converted: int | float = float(value) if spec.struct_format in {"f", "d"} else int(str(value), 0)
    if spec.minimum is not None and not spec.minimum <= converted <= spec.maximum:  # type: ignore[operator]
        raise ValueError(f"Value outside {spec.name} range [{spec.minimum}, {spec.maximum}]")
    return struct.pack("<" + spec.struct_format, converted)


def parse_hex_bytes(text: str) -> bytes:
    compact = "".join(text.replace("0x", "").split())
    if not compact or len(compact) % 2:
        raise ValueError("Enter complete hexadecimal bytes")
    try:
        return bytes.fromhex(compact)
    except ValueError as exc:
        raise ValueError("Only hexadecimal byte values are accepted") from exc


def format_bytes(data: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in data)
