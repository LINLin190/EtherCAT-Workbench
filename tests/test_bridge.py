from __future__ import annotations

import json
from typing import Any

import pytest

from ethercat_debug_tool.bridge import BridgeRuntime, _auto_scan_adapters, _json_value
from ethercat_debug_tool.infrastructure.audit import AuditLogger
from ethercat_debug_tool.models import AdapterInfo, BackendMode


class RecordingWriter:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def event(self, kind: str, payload: Any) -> None:
        self.events.append((kind, payload))


class MultiAdapterBackend:
    def __init__(self, slave_adapter: str | None) -> None:
        self.connected = False
        self.current = ""
        self.slave_adapter = slave_adapter
        self.calls: list[str] = []

    def enumerate_adapters(self) -> list[AdapterInfo]:
        return [
            AdapterInfo("adapter-a", "Adapter A"),
            AdapterInfo("adapter-b", "Adapter B"),
            AdapterInfo("adapter-c", "Adapter C"),
        ]

    def connect(self, adapter: str) -> None:
        self.calls.append(f"connect:{adapter}")
        self.current = adapter
        self.connected = True

    def scan(self) -> list[str]:
        self.calls.append(f"scan:{self.current}")
        return ["slave"] if self.current == self.slave_adapter else []

    def disconnect(self) -> None:
        self.calls.append(f"disconnect:{self.current}")
        self.connected = False
        self.current = ""


def test_auto_scan_prioritizes_preferred_adapter_and_stops_on_first_slave() -> None:
    backend = MultiAdapterBackend("adapter-c")

    result = _auto_scan_adapters(backend, "adapter-b")

    assert result["selected_adapter"] == "adapter-c"
    assert result["connected"] is True
    assert result["slaves"] == ["slave"]
    assert backend.calls == [
        "connect:adapter-b",
        "scan:adapter-b",
        "disconnect:adapter-b",
        "connect:adapter-a",
        "scan:adapter-a",
        "disconnect:adapter-a",
        "connect:adapter-c",
        "scan:adapter-c",
    ]


def test_auto_scan_restores_preferred_selection_and_disconnects_when_empty() -> None:
    backend = MultiAdapterBackend(None)

    result = _auto_scan_adapters(backend, "adapter-b")

    assert result["selected_adapter"] == "adapter-b"
    assert result["connected"] is False
    assert result["slaves"] == []
    assert backend.connected is False


def test_bridge_demo_core_commands(tmp_path) -> None:
    writer = RecordingWriter()
    audit_path = tmp_path / "audit.jsonl"
    runtime = BridgeRuntime(writer, BackendMode.DEMO, audit_path=audit_path)  # type: ignore[arg-type]
    try:
        automatic = runtime.dispatch("auto_scan", {"preferred_adapter": "demo0"})
        assert automatic["adapters"][0].name == "demo0"
        assert automatic["selected_adapter"] == "demo0"
        assert automatic["connected"] is True
        slaves = automatic["slaves"]
        assert len(slaves) == 3
        assert runtime.dispatch("status", {})["connected"] is True

        sdo = runtime.dispatch("sdo_read", {"position": 1, "index": 0x1000, "subindex": 0})
        assert sdo["data"] == bytes.fromhex("92 01 02 00")

        register = runtime.dispatch("register_read", {"position": 1, "address": 0x0130, "size": 2})
        assert register.data == bytes.fromhex("02 00")

        prepared = runtime.dispatch(
            "register_prepare_write",
            {
                "position": 1,
                "address": 0x0010,
                "data": "34 12",
                "semantics": "RW",
                "known_register": True,
            },
        )
        written = runtime.dispatch("register_execute_write", {"plan_id": prepared["plan_id"]})
        assert written.verified is True
        with pytest.raises(ValueError, match="exactly 4 bytes"):
            runtime.dispatch(
                "register_prepare_write",
                {
                    "position": 1,
                    "address": 0x0100,
                    "data": "12",
                    "semantics": "RW",
                    "known_register": True,
                },
            )

        assert runtime.dispatch("eeprom_capacity", {"position": 1}) == {"size": 2048}

        backup = runtime.dispatch("eeprom_backup", {"position": 1, "directory": str(tmp_path)})
        assert backup.binary_path.suffix == ".bin"
        assert backup.binary_path.exists()
        assert list(tmp_path.glob("*.json")) == []

        serializable = _json_value(runtime.dispatch("status", {}))
        assert serializable["mode"] == "demo"
        assert serializable["slaves"][0]["state"] == 2
        audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        assert audit[-1]["level"] == "AUDIT"
        assert audit[-1]["action"] == "register_write"
        assert audit[-1]["outcome"] == "succeeded"
    finally:
        runtime.shutdown()


def test_audit_log_rotates_without_losing_new_record(tmp_path) -> None:
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path, max_bytes=1, backups=2)

    logger.record("first", {"value": 1}, outcome="succeeded")
    logger.record("second", {"value": 2}, outcome="succeeded")

    assert json.loads(path.read_text(encoding="utf-8"))["action"] == "second"
    assert json.loads((tmp_path / "audit.jsonl.1").read_text(encoding="utf-8"))["action"] == "first"


def test_lyw_esi_full_flash_flow(tmp_path, workspace) -> None:
    writer = RecordingWriter()
    audit_path = tmp_path / "audit.jsonl"
    runtime = BridgeRuntime(
        writer,
        BackendMode.DEMO,
        audit_path=audit_path,
        stability_wait_s=0,
        rediscovery_wait_s=0,
    )  # type: ignore[arg-type]
    try:
        runtime.dispatch("auto_scan", {"preferred_adapter": "demo0"})
        runtime.dispatch("request_state", {"position": 1, "state": 1})
        assert runtime.dispatch("status", {})["slaves"][0].state.value == 1

        loaded = runtime.dispatch(
            "esi_load", {"path": str(workspace / "LYW_CanMotor_SIP-V2.2" / "XHD_CAN_Motor_18x8.xml")}
        )
        target = runtime.dispatch("sii_generate", {"document_id": loaded["document_id"], "ordinal": 0})
        assert target["size"] == 2048
        assert any("PDO categories omitted" in item for item in target["omitted"])
        assert runtime.dispatch("eeprom_capacity", {"position": 1}) == {"size": 2048}

        result = runtime.dispatch(
            "eeprom_flash",
            {"position": 1, "target_id": target["target_id"], "auto_reset": True},
        )
        assert result["success"] is True
        flash = result["result"]
        assert flash.comparison.equal and flash.sii_valid and flash.semantic_valid
        assert flash.reset_sequence == (True, True, True)
        assert flash.rediscovered is True and flash.reload_verified is True

        read = runtime.dispatch("eeprom_read", {"position": 1, "target_id": target["target_id"]})
        assert read["sii_valid"] is True
        assert read["comparison"].equal is True
        assert read["identity"]["vendor_id"] == 0x153
        audit = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
        assert audit[-1]["action"] == "eeprom_flash"
        assert audit[-1]["outcome"] == "succeeded"
        assert audit[-1]["details"]["vendor_id"] == 0x153
    finally:
        runtime.shutdown()
