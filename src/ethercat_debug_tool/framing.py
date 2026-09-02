from __future__ import annotations

import json
import os
import struct
import time
from collections import deque
from collections.abc import Callable
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


class IncrementalFrameReader:
    """Read only bytes already buffered by the pipe and assemble complete frames."""

    def __init__(self, max_bytes: int) -> None:
        self._max_bytes = max_bytes
        self._buffer = bytearray()
        self._frames: deque[dict[str, Any]] = deque()

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)
        while len(self._buffer) >= 4:
            size = struct.unpack_from("<I", self._buffer)[0]
            if size > self._max_bytes:
                raise FrameError(f"frame too large: {size} > {self._max_bytes}")
            frame_size = 4 + size
            if len(self._buffer) < frame_size:
                return
            payload = bytes(self._buffer[4:frame_size])
            del self._buffer[:frame_size]
            value = json.loads(payload.decode("utf-8"))
            if not isinstance(value, dict):
                raise FrameError("frame root must be a JSON object")
            self._frames.append(value)

    def read(
        self,
        stream: BinaryIO,
        *,
        poll_interval_s: float = 0.005,
        stopped: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if self._frames:
            return self._frames.popleft()
        if os.name != "nt":
            return read_frame(stream, self._max_bytes)

        import ctypes
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        available = ctypes.c_ulong()
        handle = msvcrt.get_osfhandle(stream.fileno())
        while True:
            if stopped is not None and stopped():
                raise OSError("transport writer stopped")
            succeeded = kernel32.PeekNamedPipe(
                ctypes.c_void_p(handle),
                None,
                0,
                None,
                ctypes.byref(available),
                None,
            )
            if not succeeded:
                error = ctypes.get_last_error()
                if error in {109, 232}:  # ERROR_BROKEN_PIPE / ERROR_NO_DATA
                    if self._buffer:
                        raise FrameError("transport closed with a truncated frame")
                    raise EOFError("transport closed while waiting for a frame")
                raise OSError(error, ctypes.FormatError(error))
            if available.value:
                chunk = stream.read(available.value)
                if not chunk:
                    if self._buffer:
                        raise FrameError("transport closed with a truncated frame")
                    raise EOFError("transport closed while reading a frame")
                self.feed(chunk)
                if self._frames:
                    return self._frames.popleft()
                continue
            time.sleep(poll_interval_s)


def write_frame(stream: BinaryIO, message: dict[str, Any], max_bytes: int) -> None:
    remaining = memoryview(encode_frame(message, max_bytes))
    while remaining:
        written = stream.write(remaining)
        if written is None or written <= 0:
            raise OSError("transport closed while writing a frame")
        remaining = remaining[written:]
    stream.flush()
