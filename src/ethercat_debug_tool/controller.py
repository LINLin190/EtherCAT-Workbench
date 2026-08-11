from __future__ import annotations

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from .backends.mock import MockBackend
from .backends.pysoem_backend import PysoemBackend
from .infrastructure.logging import ApplicationLogger
from .models import BackendMode, EtherCatState, LogRecord, PdoDirection, SlaveInfo
from .services.eeprom_service import EepromService
from .services.register_service import RegisterService, RegisterWritePlan
from .worker import EtherCatWorker
from .worker.ethercat_worker import Priority


class AppController(QObject):
    adapters_changed = Signal(object)
    connection_changed = Signal(bool, str)
    slaves_changed = Signal(object)
    pdo_mapping_ready = Signal(int, object, object)
    process_data = Signal(object)
    operation_error = Signal(str)
    log_added = Signal(object)
    busy_changed = Signal(bool, str)
    cycle_changed = Signal(bool)
    result_ready = Signal(str, object)
    progress_changed = Signal(object)

    def __init__(self, mode: BackendMode = BackendMode.DEMO) -> None:
        super().__init__()
        self.mode = mode
        self._application_log = ApplicationLogger()
        self.slaves: list[SlaveInfo] = []
        self.connected = False
        self.cycle_running = False
        self._pending: list[tuple[Future[Any], str, Callable[[Any], None] | None]] = []
        self._worker = self._make_worker(mode)
        self._cancel_operation = threading.Event()
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self.enumerate_adapters()

    @staticmethod
    def _make_worker(mode: BackendMode) -> EtherCatWorker:
        worker = EtherCatWorker(MockBackend if mode is BackendMode.DEMO else PysoemBackend)
        worker.start()
        return worker

    def switch_mode(self, mode: BackendMode) -> None:
        if mode is self.mode:
            return
        if self.cycle_running:
            self.stop_cycle()
        self._worker.shutdown()
        self.mode = mode
        self.connected = False
        self.slaves = []
        self._pending.clear()
        self._worker = self._make_worker(mode)
        self.connection_changed.emit(False, "未连接")
        self.slaves_changed.emit([])
        self.enumerate_adapters()

    def _track(self, future: Future[Any], name: str, callback: Callable[[Any], None] | None = None) -> None:
        self._pending.append((future, name, callback))
        self.busy_changed.emit(True, name)

    def _submit(
        self,
        operation: str | Callable[..., Any],
        *args: Any,
        name: str,
        callback: Callable[[Any], None] | None = None,
        priority: Priority = Priority.NORMAL,
        **kwargs: Any,
    ) -> None:
        self._track(self._worker.submit(operation, *args, priority=priority, **kwargs), name, callback)

    def _poll(self) -> None:
        remaining: list[tuple[Future[Any], str, Callable[[Any], None] | None]] = []
        for future, name, callback in self._pending:
            if not future.done():
                remaining.append((future, name, callback))
                continue
            try:
                result = future.result()
                if callback:
                    callback(result)
            except Exception as exc:
                self._error(name, exc)
        self._pending = remaining
        if not remaining:
            self.busy_changed.emit(False, "就绪")
        for event in self._worker.poll_events():
            if event.kind == "process_data":
                self.process_data.emit(event.payload)
            elif event.kind == "cycle_started":
                self.cycle_running = True
                self.cycle_changed.emit(True)
                self._log("INFO", "Master", "PDO", "周期通信已启动")
            elif event.kind in {"cycle_stopped", "cycle_fault"}:
                self.cycle_running = False
                self.cycle_changed.emit(False)
                if event.kind == "cycle_fault":
                    self._error(
                        "周期通信",
                        event.payload
                        if isinstance(event.payload, Exception)
                        else RuntimeError("连续通信错误"),
                    )

    def _error(self, operation: str, exc: BaseException) -> None:
        message = f"{operation}：{exc}"
        self.operation_error.emit(message)
        self._log("ERROR", "Master", operation, message)

    def _log(self, level: str, source: str, event: str, message: str) -> None:
        record = LogRecord(time.time(), level, source, event, message)
        self._application_log.write(record)
        self.log_added.emit(record)

    def enumerate_adapters(self) -> None:
        self._submit("enumerate_adapters", name="枚举网卡", callback=self.adapters_changed.emit)

    def connect_adapter(self, adapter: str) -> None:
        def done(_: Any) -> None:
            self.connected = True
            self.connection_changed.emit(True, "已连接")
            self._log("INFO", "Master", "CONNECT", f"已连接 {adapter}")

        self._submit("connect", adapter, name="连接网卡", callback=done)

    def disconnect_adapter(self) -> None:
        def done(_: Any) -> None:
            self.connected = False
            self.slaves = []
            self.connection_changed.emit(False, "未连接")
            self.slaves_changed.emit([])
            self._log("INFO", "Master", "DISCONNECT", "已断开")

        self._submit("disconnect", name="断开网卡", callback=done)

    def scan(self) -> None:
        def done(slaves: list[SlaveInfo]) -> None:
            self.slaves = slaves
            self.slaves_changed.emit(slaves)
            self._log("INFO", "Master", "SCAN", f"扫描完成，发现 {len(slaves)} 个从站")

        self._submit("scan", name="扫描从站", callback=done)

    def request_state(self, position: int | None, state: EtherCatState) -> None:
        def done(slaves: list[SlaveInfo]) -> None:
            self.slaves = slaves
            self.slaves_changed.emit(slaves)
            self._log(
                "AUDIT",
                "Master" if position is None else f"Slave {position}",
                "STATE",
                f"已进入 {state.label}",
            )

        self._submit("request_state", position, state, 2_000_000, name=f"切换到 {state.label}", callback=done)

    def refresh_states(self) -> None:
        def done(slaves: list[SlaveInfo]) -> None:
            self.slaves = slaves
            self.slaves_changed.emit(slaves)

        self._submit("read_states", name="刷新状态", callback=done)

    def read_pdo_mapping(self, position: int) -> None:
        state: dict[str, Any] = {}

        def rx_done(entries: Any) -> None:
            state["rx"] = entries
            if "tx" in state:
                self.pdo_mapping_ready.emit(position, state["rx"], state["tx"])

        def tx_done(entries: Any) -> None:
            state["tx"] = entries
            if "rx" in state:
                self.pdo_mapping_ready.emit(position, state["rx"], state["tx"])

        self._submit("read_pdo_mapping", position, PdoDirection.RX, name="读取 RxPDO", callback=rx_done)
        self._submit("read_pdo_mapping", position, PdoDirection.TX, name="读取 TxPDO", callback=tx_done)

    def start_cycle(self, period_ms: float, timeout_us: int = 2000) -> None:
        self._track(self._worker.start_cycle(period_ms, timeout_us), "启动周期通信")

    def stop_cycle(self) -> None:
        self._track(self._worker.stop_cycle(), "停止周期通信")

    def sdo_read(self, position: int, index: int, subindex: int, size: int = 0) -> None:
        self._submit(
            "sdo_read",
            position,
            index,
            subindex,
            size,
            name="读取 SDO",
            callback=lambda data: self.result_ready.emit("sdo_read", (position, index, subindex, data)),
        )

    def sdo_write(self, position: int, index: int, subindex: int, data: bytes) -> None:
        def done(_: Any) -> None:
            self._log(
                "AUDIT",
                f"Slave {position}",
                "SDO",
                f"写入 0x{index:04X}:{subindex:02X}，{data.hex(' ').upper()}",
            )
            self.result_ready.emit("sdo_write", (position, index, subindex, data))

        self._submit("sdo_write", position, index, subindex, data, name="写入 SDO", callback=done)

    def read_object_dictionary(self, position: int) -> None:
        self._submit(
            "read_object_dictionary",
            position,
            name="在线读取对象字典",
            callback=lambda entries: self.result_ready.emit("object_dictionary", entries),
        )

    def set_output(self, position: int, data: bytes) -> None:
        self._submit(
            "set_output",
            position,
            data,
            name="应用 PDO 输出",
            callback=lambda _: self._log(
                "AUDIT",
                f"Slave {position}",
                "PDO-WRITE",
                f"已应用 {len(data)} 字节输出：{data.hex(' ').upper()}",
            ),
        )

    def register_read(self, position: int, address: int, size: int, timeout_us: int = 2000) -> None:
        self._submit(
            "register_read",
            position,
            address,
            size,
            timeout_us,
            name="读取寄存器",
            callback=lambda data: self.result_ready.emit("register_read", (position, address, data)),
        )

    def watch_registers(self, position: int, requests: object) -> None:
        def operation(backend: Any) -> Any:
            return RegisterService(backend).read_merged(requests, position)

        self._submit(
            operation,
            name="寄存器监视轮询",
            priority=Priority.WATCH,
            callback=lambda result: self.result_ready.emit("register_watch", result),
        )

    def reconfig(self, position: int) -> None:
        self._submit(
            "reconfig",
            position,
            2_000_000,
            name="重新配置从站",
            callback=lambda result: self.result_ready.emit("reconfig", (position, result)),
        )

    def recover(self, position: int) -> None:
        self._submit(
            "recover",
            position,
            2_000_000,
            name="恢复从站",
            callback=lambda result: self.result_ready.emit("recover", (position, result)),
        )

    def register_prepare_write(
        self, position: int, address: int, target: bytes, semantics: Any, known_register: bool
    ) -> None:
        def operation(backend: Any) -> RegisterWritePlan:
            return RegisterService(backend).prepare_write(
                position, address, target, semantics, known_register
            )

        self._submit(
            operation,
            name="准备寄存器写入",
            callback=lambda plan: self.result_ready.emit("register_plan", plan),
        )

    def register_execute_write(self, plan: RegisterWritePlan) -> None:
        def operation(backend: Any) -> Any:
            return RegisterService(backend).execute_write(plan)

        def done(result: Any) -> None:
            self._log(
                "AUDIT",
                f"Slave {plan.position}",
                "FPWR",
                f"0x{plan.address:04X} {plan.semantics.value} current={plan.current.hex()} "
                f"target={plan.target.hex()} mask={plan.changed_mask.hex()} result={result.conclusion}",
            )
            self.result_ready.emit("register_write", (plan, result))

        self._submit(operation, name="写入寄存器", callback=done)

    def read_eeprom(self, position: int) -> None:
        self._cancel_operation.clear()

        def operation(backend: Any) -> bytes:
            return EepromService(backend).read_full(
                position, progress=self.progress_changed.emit, cancel=self._cancel_operation.is_set
            )

        self._submit(
            operation, name="完整读取 EEPROM", callback=lambda raw: self.result_ready.emit("eeprom_read", raw)
        )

    def backup_eeprom(self, position: int, directory: Path) -> None:
        slave = self.slaves[position - 1]
        self._cancel_operation.clear()

        def operation(backend: Any) -> Any:
            return EepromService(backend).backup(
                position,
                directory,
                slave,
                progress=self.progress_changed.emit,
                cancel=self._cancel_operation.is_set,
            )

        self._submit(
            operation,
            name="备份 EEPROM",
            callback=lambda value: self.result_ready.emit("eeprom_backup", value),
        )

    def flash_eeprom(
        self, position: int, target: bytes, device: Any, directory: Path, auto_reset: bool
    ) -> None:
        slave = self.slaves[position - 1]
        if self.cycle_running:
            self._error("EEPROM 烧录", RuntimeError("必须先安全停止周期通信"))
            return
        if slave.state is not EtherCatState.INIT:
            self._error("EEPROM 烧录", RuntimeError("目标从站必须先切换到 INIT"))
            return
        self._cancel_operation.clear()

        def operation(backend: Any) -> Any:
            return EepromService(backend).flash(
                position,
                target,
                device,
                directory,
                slave,
                auto_reset=auto_reset,
                progress=self.progress_changed.emit,
                cancel=self._cancel_operation.is_set,
            )

        def done(value: Any) -> None:
            self._log(
                "AUDIT",
                f"Slave {position}",
                "EEPROM-FLASH",
                f"image_success={value.image_success} target_sha256={value.comparison.target_sha256} "
                f"readback_sha256={value.comparison.readback_sha256} backup={value.backup.binary_path}",
            )
            self.result_ready.emit("eeprom_flash", value)

        self._submit(operation, name="EEPROM 烧录与完整校验", callback=done)

    def restore_eeprom(self, position: int, backup_path: Path, directory: Path, auto_reset: bool) -> None:
        slave = self.slaves[position - 1]
        if self.cycle_running or slave.state is not EtherCatState.INIT:
            self._error("EEPROM 恢复", RuntimeError("必须停止周期通信并将目标从站切换到 INIT"))
            return
        self._cancel_operation.clear()

        def operation(backend: Any) -> Any:
            return EepromService(backend).restore(
                position,
                backup_path,
                directory,
                slave,
                auto_reset=auto_reset,
                progress=self.progress_changed.emit,
                cancel=self._cancel_operation.is_set,
            )

        def done(value: Any) -> None:
            self._log(
                "AUDIT",
                f"Slave {position}",
                "EEPROM-RESTORE",
                f"source={backup_path} image_success={value.image_success} backup={value.backup.binary_path}",
            )
            self.result_ready.emit("eeprom_flash", value)

        self._submit(operation, name="从备份恢复 EEPROM", callback=done)

    def cancel_long_operation(self) -> None:
        self._cancel_operation.set()
        self._log("WARN", "Application", "CANCEL", "已请求在下一个安全边界取消耗时操作")

    def close(self) -> bool:
        self._timer.stop()
        return self._worker.shutdown()
