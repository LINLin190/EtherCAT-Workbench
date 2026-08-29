from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO


class FrameError(RuntimeError):
    pass


def encode_frame(message: dict[str, Any], max_bytes: int) -> bytes:
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > max_bytes:
        raise FrameError(f"frame too large: {len(payload)} > {max_bytes}")
    return struct.pack("<I", len(payload)) + payload


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            raise EOFError("transport closed while reading a frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(stream: BinaryIO, max_bytes: int) -> dict[str, Any]:
    size = struct.unpack("<I", _read_exact(stream, 4))[0]
    if size > max_bytes:
        raise FrameError(f"frame too large: {size} > {max_bytes}")
    value = json.loads(_read_exact(stream, size).decode("utf-8"))
    if not isinstance(value, dict):
        raise FrameError("frame root must be a JSON object")
    return value


def write_frame(stream: BinaryIO, message: dict[str, Any], max_bytes: int) -> None:
    stream.write(encode_frame(message, max_bytes))
    stream.flush()
