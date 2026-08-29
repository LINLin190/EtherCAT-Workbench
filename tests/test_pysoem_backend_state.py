import pytest

from ethercat_debug_tool.backends.pysoem_backend import PysoemBackend
from ethercat_debug_tool.models import EtherCatState, SlaveIdentity, SlaveInfo


class FakeSlave:
    def __init__(self, name: str, al_status: int, al_code: int) -> None:
        self.name = name
        self.al_status = al_status
        self._al_code = al_code

    def _fprd(self, address: int, size: int, timeout_us: int) -> bytes:
        assert (address, size) == (0x0134, 2)
        return self._al_code.to_bytes(2, "little")


class FakeMaster:
    def __init__(self, slaves: list[FakeSlave]) -> None:
        self.slaves = slaves

    def read_state(self) -> None:
        pass


def test_bus_state_error_reports_each_slave_without_using_master_fprd() -> None:
    backend = PysoemBackend()
    backend._master = FakeMaster(
        [FakeSlave("XHD_Device", 0x0002, 0x001B), FakeSlave("Other", 0x0011, 0x0000)]
    )
    error = backend._state_transition_error(
        backend._master, EtherCatState.OP, int(EtherCatState.PRE_OP), 2_000_000
    )

    message = str(error)
    assert "State transition to OP failed" in message
    assert "XHD_Device AL status 0x0002, AL status code 0x001B" in message
    assert "SyncManager 看门狗超时" in message
    assert "Other AL status 0x0011, AL status code 0x0000" in message


def test_targeted_state_error_reports_only_target_slave() -> None:
    backend = PysoemBackend()
    first = FakeSlave("XHD_Device", 0x0002, 0x001B)
    second = FakeSlave("Other", 0x0011, 0x0000)
    backend._master = FakeMaster([first, second])
    error = backend._state_transition_error(first, EtherCatState.SAFE_OP, 0x02, 2_000_000)

    message = str(error)
    assert "XHD_Device AL status 0x0002, AL status code 0x001B" in message
    assert "Other" not in message


def test_read_states_reuses_static_scan_information(monkeypatch) -> None:
    backend = PysoemBackend()
    slave = FakeSlave("XHD_Device", 0x001B, 0)
    slave.state = int(EtherCatState.OP)
    backend._master = FakeMaster([slave])
    backend._connected = True
    cached = SlaveInfo(
        1,
        "XHD_Device",
        SlaveIdentity(0x153, 0x1234, 1, 99),
        EtherCatState.PRE_OP,
        0,
        18,
        8,
        0x1001,
        "E253",
        "LAN9253_COMPATIBLE",
    )
    backend._slaves = [cached]
    monkeypatch.setattr(backend, "_info", lambda *_: pytest.fail("static information was re-read"))

    refreshed = backend.read_states()

    assert refreshed == [
        SlaveInfo(
            1,
            "XHD_Device",
            cached.identity,
            EtherCatState.OP,
            0x001B,
            18,
            8,
            0x1001,
            "E253",
            "LAN9253_COMPATIBLE",
        )
    ]


def test_scan_serial_uses_sii_without_optional_sdo_probe() -> None:
    class IdentitySlave:
        def eeprom_read(self, word_address: int) -> bytes:
            assert word_address == 0x0E
            return bytes.fromhex("78 56 34 12")

        def sdo_read(self, *_args, **_kwargs) -> bytes:
            pytest.fail("scan must not wait for optional CoE identity object")

    assert PysoemBackend()._serial(IdentitySlave()) == 0x12345678


def test_disconnect_clears_internal_state_even_when_master_close_fails() -> None:
    class BrokenMaster:
        def close(self) -> None:
            raise RuntimeError("close failed")

    backend = PysoemBackend()
    backend._master = BrokenMaster()
    backend._connected = True
    backend._mapped = True
    backend._slaves = [object()]

    with pytest.raises(RuntimeError, match="close failed"):
        backend.disconnect()

    assert backend._master is None
    assert backend.connected is False
    assert backend._mapped is False
    assert backend._slaves == []
