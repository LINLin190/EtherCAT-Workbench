from __future__ import annotations

import io
import struct
import threading

import pytest

from ethercat_debug_tool.bridge import JsonWriter
from ethercat_debug_tool.framing import (
    FrameError,
    IncrementalFrameReader,
    encode_frame,
    read_frame,
)


class CaptureStream:
    def __init__(self, max_chunk: int | None = None) -> None:
        self.data = bytearray()
        self.closed = False
        self._lock = threading.Lock()
        self.max_chunk = max_chunk

    def write(self, data: bytes | memoryview) -> int:
        count = len(data) if self.max_chunk is None else min(len(data), self.max_chunk)
        with self._lock:
            self.data.extend(data[:count])
        return count

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_incremental_reader_waits_for_complete_frames_and_retains_following_frame() -> None:
    first = encode_frame({"id": 1}, 1024)
    second = encode_frame({"id": 2}, 1024)
    reader = IncrementalFrameReader(1024)

    reader.feed(first[:3])
    assert not reader._frames
    reader.feed(first[3:] + second)

    assert reader._frames.popleft() == {"id": 1}
    assert reader._frames.popleft() == {"id": 2}


def test_incremental_reader_rejects_oversized_length_before_allocating_payload() -> None:
    reader = IncrementalFrameReader(16)

    with pytest.raises(FrameError, match="frame too large"):
        reader.feed(struct.pack("<I", 17))


def test_json_writer_serializes_on_its_dedicated_writer_thread() -> None:
    stream = CaptureStream(max_chunk=3)
    writer = JsonWriter(stream, 1024)

    writer.send({"type": "response", "id": 7})
    writer.close()

    assert stream.closed
    assert read_frame(io.BytesIO(stream.data), 1024) == {"type": "response", "id": 7}
