from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import threading
import uuid
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .backends.mock import MockBackend
from .backends.pysoem_backend import PysoemBackend
from .esc_profiles.profiles import ProfileRegistry
from .esi import EsiParser
from .infrastructure import AuditLogger, default_audit_path
from .models import AccessSemantics, BackendMode, EtherCatState, OperationProgress, PdoDirection
from .services.eeprom_service import EepromService, compare_images
from .services.register_service import RegisterService, RegisterWritePlan, ResetService
from .sii.generator import SiiGenerationReport, SiiGenerator
from .sii.parser import SiiParser
from .worker import EtherCatWorker
from .worker.ethercat_worker import Priority


def _json_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, bytes):
        return value.hex(" ").upper()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return value


def _auto_scan_adapters(backend: Any, preferred_adapter: str = "") -> dict[str, Any]:
    """Scan adapters in priority order and leave only a successful adapter connected."""
    adapters = list(backend.enumerate_adapters())
    ordered = list(adapters)
    preferred = next((item for item in adapters if item.name == preferred_adapter), None)
    if preferred is not None:
        ordered = [preferred, *(item for item in adapters if item.name != preferred_adapter)]

    if backend.connected:
        backend.disconnect()

    attempts: list[dict[str, Any]] = []
    for item in ordered:
        try:
            backend.connect(item.name)
            slaves = list(backend.scan())
        except Exception as exc:
            attempts.append({"adapter": item.name, "slave_count": 0, "error": str(exc)})
            if backend.connected:
                try:
                    backend.disconnect()
                except Exception as disconnect_exc:
                    attempts[-1]["disconnect_error"] = str(disconnect_exc)
            continue

        attempts.append({"adapter": item.name, "slave_count": len(slaves)})
        if slaves:
            return {
                "adapters": adapters,
                "selected_adapter": item.name,
                "connected": True,
                "slaves": slaves,
                "attempts": attempts,
            }
        backend.disconnect()

    selected = preferred.name if preferred is not None else (adapters[0].name if adapters else "")
    return {
        "adapters": adapters,
        "selected_adapter": selected,
        "connected": False,
        "slaves": [],
        "attempts": attempts,
    }


class JsonWriter:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        encoded = json.dumps(_json_value(message), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            sys.stdout.write(encoded + "\n")
            sys.stdout.flush()

    def event(self, kind: str, payload: Any) -> None:
        self.send({"type": "event", "payload": {"kind": kind, "data": payload}})


class BridgeRuntime:
    """Long-lived JSON bridge. The Worker remains the sole EtherCAT Master owner."""

    def __init__(
        self,
        writer: JsonWriter,
        mode: BackendMode = BackendMode.REAL,
        *,
        audit_path: Path | None = None,
        stability_wait_s: float = 10.0,
        rediscovery_wait_s: float = 1.0,
    ) -> None:
        self.writer = writer
        self.mode = mode
        self.worker = self._new_worker(self.mode)
        self.connected = False
        self.slaves: list[Any] = []
        self.cycle_running = False
        self.cancel = threading.Event()
        self.documents: dict[str, Any] = {}
        self.targets: dict[str, tuple[bytes, Any]] = {}
        self.write_plans: dict[str, RegisterWritePlan] = {}
        self.audit = AuditLogger(audit_path)
        self.stability_wait_s = stability_wait_s
        self.rediscovery_wait_s = rediscovery_wait_s
        self._command_lock = threading.Lock()
        self._worker_lock = threading.Lock()
        self._stopped = threading.Event()
        self._events = threading.Thread(target=self._event_loop, name="Bridge events", daemon=True)
        self._events.start()

    @staticmethod
    def _new_worker(mode: BackendMode) -> EtherCatWorker:
        worker = EtherCatWorker(MockBackend if mode is BackendMode.DEMO else PysoemBackend)
        worker.start()
        return worker

    def _event_loop(self) -> None:
        while not self._stopped.wait(0.02):
            with self._worker_lock:
                worker = self.worker
            for event in worker.poll_events():
                if event.kind == "cycle_started":
                    self.cycle_running = True
                    if event.payload is not None:
                        self.slaves = list(event.payload)
                elif event.kind in {"cycle_stopped", "cycle_fault"}:
                    self.cycle_running = False
                    if event.kind == "cycle_stopped" and event.payload is not None:
                        self.slaves = list(event.payload)
                elif event.kind == "slaves_changed":
                    self.slaves = list(event.payload)
                self.writer.event(event.kind, event.payload)

    def _submit(
        self,
        operation: str | Any,
        *args: Any,
        priority: Priority = Priority.NORMAL,
        timeout: float = 190.0,
        **kwargs: Any,
    ) -> Any:
        with self._worker_lock:
            future = self.worker.submit(operation, *args, priority=priority, **kwargs)
        return future.result(timeout=timeout)

    def _progress(self, progress: OperationProgress) -> None:
        self.writer.event("progress", progress)

    def _audited(self, action: str, details: dict[str, Any], operation: Any) -> Any:
        try:
            result = operation()
        except BaseException as exc:
            self.audit.record(action, details, outcome="failed", error=str(exc))
            raise
        self.audit.record(action, details, outcome="succeeded")
        return result

    def _slave(self, position: int) -> Any:
        if not 1 <= position <= len(self.slaves):
            raise ValueError(f"Slave {position} is not available")
        return self.slaves[position - 1]

    def dispatch(self, method: str, params: dict[str, Any]) -> Any:
        if method == "cancel":
            self.cancel.set()
            return {"cancelled": True}
        if method == "shutdown":
            self.shutdown()
            return {"stopped": True}
        with self._command_lock:
            return self._dispatch_serial(method, params)

    def _dispatch_serial(self, method: str, params: dict[str, Any]) -> Any:
        if method == "status":
            return {
                "mode": self.mode.value,
                "connected": self.connected,
                "cycle_running": self.cycle_running,
                "slaves": self.slaves,
            }
        if method == "switch_mode":
            mode = BackendMode(params["mode"])
            if self.connected or self.cycle_running:
                raise RuntimeError("切换模式前必须停止周期通信并断开网卡")
            with self._worker_lock:
                old_worker = self.worker
                old_worker.shutdown()
                self.worker = self._new_worker(mode)
            self.mode = mode
            self.slaves = []
            return {"mode": mode.value}
        if method == "enumerate_adapters":
            return self._submit("enumerate_adapters")
        if method == "auto_scan":
            preferred = str(params.get("preferred_adapter") or "")
            result = self._submit(lambda backend: _auto_scan_adapters(backend, preferred))
            self.connected = bool(result["connected"])
            self.cycle_running = False
            self.slaves = list(result["slaves"])
            return result
        if method == "connect":
            self._submit("connect", str(params["adapter"]))
            self.connected = True
            return {"connected": True}
        if method == "disconnect":
            if self.cycle_running:
                with self._worker_lock:
                    self.worker.stop_cycle().result(timeout=10)
            self._submit("disconnect")
            self.connected = False
            self.cycle_running = False
            self.slaves = []
            return {"connected": False}
        if method == "scan":
            self.slaves = list(self._submit("scan"))
            return self.slaves
        if method == "read_states":
            self.slaves = list(self._submit("read_states"))
            return self.slaves
        if method == "request_state":
            raw_position = params.get("position")
            position = None if raw_position in {None, 0} else int(raw_position)
            state = EtherCatState(int(params["state"]))
            self.slaves = list(self._submit("request_state", position, state, 2_000_000))
            return self.slaves
        if method in {"reconfig", "recover"}:
            position = int(params["position"])
            succeeded = bool(self._submit(method, position, 2_000_000))
            if not succeeded:
                raise RuntimeError(f"从站 {position} {method} 未成功")
            self.slaves = list(self._submit("read_states"))
            return {"succeeded": True, "slaves": self.slaves}
        if method == "sdo_read":
            data = self._submit(
                "sdo_read",
                int(params["position"]),
                int(params["index"]),
                int(params["subindex"]),
            )
            return {"data": data}
        if method == "sdo_write":
            data = bytes.fromhex(str(params["data"]))
            position = int(params["position"])
            index = int(params["index"])
            subindex = int(params["subindex"])
            self._submit("sdo_write", position, index, subindex, data)
            readback = self._submit("sdo_read", position, index, subindex)
            return {"data": data, "readback": readback, "verified": readback == data}
        if method == "object_dictionary":
            return self._submit("read_object_dictionary", int(params["position"]))
        if method == "pdo_mapping":
            position = int(params["position"])
            rx = self._submit("read_pdo_mapping", position, PdoDirection.RX)
            tx = self._submit("read_pdo_mapping", position, PdoDirection.TX)
            return {"rx": rx, "tx": tx}
        if method == "set_output":
            data = bytes.fromhex(str(params["data"]))
            self._submit("set_output", int(params["position"]), data)
            return {"applied": True, "data": data}
        if method == "start_cycle":
            with self._worker_lock:
                self.worker.start_cycle(float(params["period_ms"]), 2000, 5).result(timeout=10)
            self.cycle_running = True
            return {"running": True}
        if method == "stop_cycle":
            with self._worker_lock:
                result = self.worker.stop_cycle().result(timeout=10)
            self.cycle_running = False
            if result is not None:
                self.slaves = list(result)
            return {"running": False, "slaves": self.slaves}
        if method == "register_catalog":
            return ProfileRegistry().standard_registers()
        if method == "register_read":
            result = self._submit(
                lambda backend: RegisterService(backend).read(
                    int(params["position"]), int(params["address"]), int(params["size"])
                )
            )
            return result
        if method == "register_watch":
            requests = tuple((int(item["address"]), int(item["size"])) for item in params["requests"])
            return self._submit(
                lambda backend: list(
                    RegisterService(backend).read_merged(requests, int(params["position"])).values()
                ),
                priority=Priority.WATCH,
            )
        if method == "register_prepare_write":
            semantics = AccessSemantics(str(params["semantics"]))
            known_register = bool(params.get("known_register", False))
            expected_width = None
            expected_semantics = None
            if known_register:
                address = int(params["address"])
                definition = next(
                    (
                        item
                        for item in ProfileRegistry().standard_registers()
                        if int(item["address"]) == address
                    ),
                    None,
                )
                if definition is None:
                    raise ValueError(f"Known register 0x{address:04X} is not in the catalog")
                expected_width = int(definition["width"])
                expected_semantics = AccessSemantics(str(definition["access"]))
            plan = self._submit(
                lambda backend: RegisterService(backend).prepare_write(
                    int(params["position"]),
                    int(params["address"]),
                    bytes.fromhex(str(params["data"])),
                    semantics,
                    known_register,
                    expected_width=expected_width,
                    expected_semantics=expected_semantics,
                )
            )
            plan_id = uuid.uuid4().hex
            self.write_plans[plan_id] = plan
            return {"plan_id": plan_id, "plan": plan}
        if method == "register_execute_write":
            plan = self.write_plans.pop(str(params["plan_id"]))
            details = {
                "position": plan.position,
                "address": f"0x{plan.address:04X}",
                "semantics": plan.semantics.value,
                "current": plan.current.hex(" ").upper(),
                "target": plan.target.hex(" ").upper(),
                "changed_mask": plan.changed_mask.hex(" ").upper(),
                "known_register": plan.known_register,
            }
            try:
                result = self._submit(lambda backend: RegisterService(backend).execute_write(plan))
            except BaseException as exc:
                self.audit.record("register_write", details, outcome="failed", error=str(exc))
                raise
            if result.verified is False:
                self.audit.record("register_write", details, outcome="failed", error=result.conclusion)
                raise RuntimeError(result.conclusion)
            self.audit.record("register_write", details, outcome="succeeded")
            return result
        if method == "register_reset":
            position = int(params["position"])
            slave = self._slave(position)
            profile = ProfileRegistry().get(slave.chip_model)
            if not profile.reset_supported:
                raise RuntimeError(f"{slave.chip_model} 未声明支持 ESC RES 复位序列")
            return self._audited(
                "register_reset_ecat",
                {"position": position, "address": "0x0040", "sequence": "52 45 53"},
                lambda: self._submit(lambda backend: ResetService(backend).reset_ecat(position)),
            )
        if method == "eeprom_read":
            if self.cycle_running:
                raise RuntimeError("完整读取 EEPROM 前必须先安全停止周期通信")
            self.cancel.clear()
            raw = self._submit(
                lambda backend: EepromService(backend).read_full(
                    int(params["position"]), progress=self._progress, cancel=self.cancel.is_set
                )
            )
            response: dict[str, Any] = {
                "data": raw,
                "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "read_at": datetime.now(UTC).isoformat(),
            }
            try:
                parsed = SiiParser().parse(raw)
            except Exception as exc:
                response.update({"sii_valid": False, "sii_error": str(exc)})
            else:
                response.update(
                    {
                        "sii_valid": True,
                        "identity": {
                            "vendor_id": parsed.vendor_id,
                            "product_code": parsed.product_code,
                            "revision": parsed.revision,
                            "serial_number": parsed.serial_number,
                        },
                        "category_count": len(parsed.categories),
                        "categories": [category.kind for category in parsed.categories],
                        "end_offset": parsed.end_offset,
                    }
                )
            target_id = str(params.get("target_id") or "")
            if target_id and target_id in self.targets:
                response["comparison"] = compare_images(self.targets[target_id][0], raw)
            return response
        if method == "eeprom_capacity":
            size = self._submit(lambda backend: EepromService(backend).read_capacity(int(params["position"])))
            return {"size": size}
        if method == "eeprom_backup":
            if self.cycle_running:
                raise RuntimeError("备份 EEPROM 前必须先安全停止周期通信")
            self.cancel.clear()
            position = int(params["position"])
            return self._submit(
                lambda backend: EepromService(backend).backup(
                    position,
                    Path(params["directory"]),
                    self._slave(position),
                    progress=self._progress,
                    cancel=self.cancel.is_set,
                )
            )
        if method == "esi_load":
            document = EsiParser().parse(Path(params["path"]))
            document_id = uuid.uuid4().hex
            self.documents[document_id] = document
            return {
                "document_id": document_id,
                "path": document.path,
                "sha256": document.sha256,
                "vendor_id": document.vendor_id,
                "vendor_name": document.vendor_name,
                "devices": document.devices,
            }
        if method == "sii_generate":
            document = self.documents[str(params["document_id"])]
            ordinal = int(params["ordinal"])
            device = document.devices[ordinal]
            report: SiiGenerationReport = SiiGenerator().generate(device)
            target_id = uuid.uuid4().hex
            self.targets[target_id] = (report.image, device)
            return {
                "target_id": target_id,
                "size": len(report.image),
                "sha256": hashlib.sha256(report.image).hexdigest(),
                "supported": report.supported,
                "omitted": report.omitted,
                "device": device,
            }
        if method == "eeprom_flash":
            position = int(params["position"])
            slave = self._slave(position)
            if self.cycle_running:
                raise RuntimeError("必须先安全停止周期通信")
            if slave.state is not EtherCatState.INIT:
                raise RuntimeError("目标从站必须先切换到 INIT")
            target, device = self.targets[str(params["target_id"])]
            self.cancel.clear()
            details = {
                "position": position,
                "target_sha256": hashlib.sha256(target).hexdigest(),
                "size": len(target),
                "vendor_id": device.vendor_id,
                "product_code": device.product_code,
                "revision": device.revision,
            }
            try:
                result = self._submit(
                    lambda backend: EepromService(
                        backend,
                        stability_wait_s=self.stability_wait_s,
                        rediscovery_wait_s=self.rediscovery_wait_s,
                    ).flash(
                        position,
                        target,
                        device,
                        auto_reset=bool(params.get("auto_reset", True)),
                        progress=self._progress,
                        cancel=self.cancel.is_set,
                    )
                )
            except BaseException as exc:
                self.audit.record("eeprom_flash", details, outcome="failed", error=str(exc))
                raise
            details.update(
                {
                    "image_success": result.image_success,
                    "rediscovered": result.rediscovered,
                    "reload_verified": result.reload_verified,
                }
            )
            self.audit.record(
                "eeprom_flash",
                details,
                outcome="succeeded" if result.image_success else "failed",
                error=None if result.image_success else result.image_verification,
            )
            if result.rediscovered:
                try:
                    self.slaves = list(self._submit("read_states"))
                except Exception:
                    pass
            return {"success": result.image_success, "result": result, "slaves": self.slaves}
        if method == "eeprom_restore":
            position = int(params["position"])
            slave = self._slave(position)
            if self.cycle_running or slave.state is not EtherCatState.INIT:
                raise RuntimeError("必须停止周期通信并将目标从站切换到 INIT")
            self.cancel.clear()
            path = Path(params["path"])
            details = {"position": position, "path": str(path)}
            try:
                result = self._submit(
                    lambda backend: EepromService(
                        backend,
                        stability_wait_s=self.stability_wait_s,
                        rediscovery_wait_s=self.rediscovery_wait_s,
                    ).restore(
                        position,
                        path,
                        auto_reset=bool(params.get("auto_reset", True)),
                        progress=self._progress,
                        cancel=self.cancel.is_set,
                    )
                )
            except BaseException as exc:
                self.audit.record("eeprom_restore", details, outcome="failed", error=str(exc))
                raise
            details.update(
                {
                    "image_success": result.image_success,
                    "rediscovered": result.rediscovered,
                    "reload_verified": result.reload_verified,
                }
            )
            self.audit.record(
                "eeprom_restore",
                details,
                outcome="succeeded" if result.image_success else "failed",
                error=None if result.image_success else result.image_verification,
            )
            if result.rediscovered:
                try:
                    self.slaves = list(self._submit("read_states"))
                except Exception:
                    pass
            return {"success": result.image_success, "result": result, "slaves": self.slaves}
        raise ValueError(f"Unknown bridge method: {method}")

    def shutdown(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        with self._worker_lock:
            self.worker.shutdown()


def _handle_request(runtime: BridgeRuntime, writer: JsonWriter, request: dict[str, Any]) -> None:
    request_id = int(request.get("id", 0))
    try:
        result = runtime.dispatch(str(request["method"]), dict(request.get("params") or {}))
    except BaseException as exc:
        writer.send({"type": "response", "id": request_id, "ok": False, "error": str(exc)})
    else:
        writer.send({"type": "response", "id": request_id, "ok": True, "result": result})


def main() -> int:
    writer = JsonWriter()
    mode = BackendMode(os.environ.get("ETHERCAT_WORKBENCH_MODE", BackendMode.REAL.value))
    runtime = BridgeRuntime(writer, mode, audit_path=default_audit_path())
    writer.event("ready", {"mode": runtime.mode.value})
    threads: list[threading.Thread] = []
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                writer.event("protocol_error", str(exc))
                continue
            thread = threading.Thread(
                target=_handle_request,
                args=(runtime, writer, request),
                name=f"Bridge request {request.get('id', 0)}",
                daemon=True,
            )
            thread.start()
            threads.append(thread)
            if request.get("method") == "shutdown":
                break
    finally:
        runtime.shutdown()
        for thread in threads:
            if thread is not threading.current_thread():
                thread.join(timeout=0.2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
