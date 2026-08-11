import time

from ethercat_debug_tool.backends.mock import MockBackend
from ethercat_debug_tool.models import EtherCatState
from ethercat_debug_tool.worker.ethercat_worker import EtherCatWorker


def test_mock_p0_and_worker_serialization() -> None:
    worker = EtherCatWorker(MockBackend)
    worker.start()
    try:
        assert worker.submit("enumerate_adapters").result(timeout=2)[0].name == "demo0"
        worker.submit("connect", "demo0").result(timeout=2)
        assert len(worker.submit("scan").result(timeout=2)) == 3
        states = worker.submit("request_state", 1, EtherCatState.SAFE_OP, 1000).result(timeout=2)
        assert states[0].state is EtherCatState.SAFE_OP
        assert worker.submit("sdo_read", 1, 0x1018, 1, 4).result(timeout=2) == bytes.fromhex("34120000")
        worker.start_cycle(2, 1000).result(timeout=2)
        deadline = time.monotonic() + 1
        snapshots = []
        while time.monotonic() < deadline and not snapshots:
            snapshots.extend(event.payload for event in worker.poll_events() if event.kind == "process_data")
            time.sleep(0.005)
        assert snapshots and snapshots[-1].actual_wkc == snapshots[-1].expected_wkc
        worker.stop_cycle().result(timeout=2)
    finally:
        assert worker.shutdown()


def test_output_width_is_guarded() -> None:
    backend = MockBackend()
    backend.connect("demo0")
    try:
        backend.set_output(1, b"\x00" * 6)
        try:
            backend.set_output(1, b"\x00")
            raise AssertionError("short output should be rejected")
        except ValueError:
            pass
    finally:
        backend.disconnect()
