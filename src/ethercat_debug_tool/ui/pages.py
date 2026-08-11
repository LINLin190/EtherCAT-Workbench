from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..esc_profiles.profiles import ProfileRegistry
from ..esi import EsiDocument, EsiParser
from ..infrastructure.settings import AppSettings
from ..models import AccessSemantics, OperationProgress, PdoEntry, ProcessDataSnapshot, SlaveInfo
from ..services.eeprom_service import EepromFlashResult
from ..services.register_service import RegisterWritePlan, RegisterWriteResult
from ..services.sdo_codec import encode_value, format_bytes, parse_hex_bytes
from ..sii.generator import SiiGenerationReport, SiiGenerator
from ..sii.parser import SiiParser


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setDefaultSectionSize(32)
    return table


class OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.labels: dict[str, QLabel] = {}
        self.health = QLabel("○ 尚未选择从站")
        self.health.setObjectName("infoBanner")
        form = QFormLayout()
        for key, title in (
            ("name", "名称"),
            ("position", "位置"),
            ("chip", "实际 ESC"),
            ("family", "寄存器参考族"),
            ("pram", "PRAM"),
            ("resources", "FMMU / SM"),
            ("vendor", "Vendor ID"),
            ("product", "Product Code"),
            ("revision", "Revision"),
            ("serial", "Serial Number"),
            ("state", "状态"),
            ("al", "AL Status"),
            ("io", "输入 / 输出"),
        ):
            self.labels[key] = QLabel("—")
            form.addRow(title, self.labels[key])
        layout = QVBoxLayout(self)
        title = QLabel("从站概览")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        layout.addWidget(self.health)
        layout.addLayout(form)
        layout.addStretch()

    def set_slave(self, slave: SlaveInfo | None) -> None:
        if slave is None:
            for label in self.labels.values():
                label.setText("—")
            self.health.setText("○ 尚未选择从站")
            return
        i = slave.identity
        self.labels["name"].setText(slave.name)
        self.labels["position"].setText(str(slave.position))
        self.labels["chip"].setText(slave.chip_model)
        self.labels["family"].setText(slave.register_family)
        self.labels["pram"].setText(
            "0x1000–0x2FFF" if slave.chip_model in {"E101", "E252", "E253"} else "在线读取"
        )
        self.labels["resources"].setText(
            "8 / 8" if slave.chip_model in {"E101", "E252", "E253"} else "在线读取"
        )
        self.labels["vendor"].setText(f"0x{i.vendor_id:08X}")
        self.labels["product"].setText(f"0x{i.product_code:08X}")
        self.labels["revision"].setText(f"0x{i.revision:08X}")
        self.labels["serial"].setText(f"0x{i.serial_number:08X}")
        self.labels["state"].setText(f"● {slave.state.label}")
        self.labels["al"].setText(f"0x{slave.al_status:04X}")
        self.labels["io"].setText(f"{slave.input_size} bytes / {slave.output_size} bytes")
        if slave.al_status:
            self.health.setText(
                f"! {slave.state.label} · AL Status 0x{slave.al_status:04X} · 请查看错误详情或刷新状态"
            )
        else:
            self.health.setText(f"✓ 通信正常 · 当前状态 {slave.state.label} · AL Status 无错误")


class CoePage(QWidget):
    read_requested = Signal(int, int, int, int)
    write_requested = Signal(int, int, int, bytes)
    online_dictionary_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0
        self.index = QLineEdit("0x1018")
        self.subindex = QLineEdit("0x01")
        self.data_type = QComboBox()
        self.data_type.addItems(
            [
                "UNSIGNED32",
                "UNSIGNED16",
                "INTEGER32",
                "INTEGER16",
                "UNSIGNED8",
                "INTEGER8",
                "BOOL",
                "VISIBLE_STRING",
                "RAW",
            ]
        )
        self.value = QLineEdit()
        self.raw = QLineEdit()
        self.raw.setReadOnly(True)
        read = QPushButton("读取 SDO")
        write = QPushButton("写入并读回验证")
        dictionary = QPushButton("在线读取对象字典")
        read.clicked.connect(self._read)
        write.clicked.connect(self._write)
        dictionary.clicked.connect(lambda: self.online_dictionary_requested.emit(self.position))
        form = QFormLayout()
        form.addRow("Index", self.index)
        form.addRow("SubIndex", self.subindex)
        form.addRow("数据类型", self.data_type)
        form.addRow("当前/目标值", self.value)
        form.addRow("最终字节", self.raw)
        buttons = QHBoxLayout()
        buttons.addWidget(read)
        buttons.addWidget(write)
        buttons.addWidget(dictionary)
        form.addRow(buttons)
        self.objects = _table(["Index", "Sub", "Name", "Type", "Access", "Value"])
        info = QLabel("在线对象字典不可用时，将使用已匹配的 ESI；手动对象访问始终可用。")
        info.setObjectName("infoBanner")
        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(self.objects)

    def _address(self) -> tuple[int, int]:
        return int(self.index.text(), 0), int(self.subindex.text(), 0)

    def _read(self) -> None:
        try:
            index, sub = self._address()
            self.read_requested.emit(self.position, index, sub, 0)
        except ValueError:
            self.index.setToolTip("请输入合法 Index/SubIndex")

    def _write(self) -> None:
        try:
            index, sub = self._address()
            data = (
                parse_hex_bytes(self.value.text())
                if self.data_type.currentText() == "RAW"
                else encode_value(self.value.text(), self.data_type.currentText())
            )
        except ValueError as exc:
            self.value.setToolTip(str(exc))
            return
        self.raw.setText(format_bytes(data))
        answer = QMessageBox.question(
            self,
            "确认 SDO 写入",
            f"目标：Slave {self.position}\n对象：0x{index:04X}:{sub:02X}\n目标值：{self.value.text()}\n最终字节：{format_bytes(data)}",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.write_requested.emit(self.position, index, sub, data)

    def show_read(self, index: int, subindex: int, data: bytes) -> None:
        self.index.setText(f"0x{index:04X}")
        self.subindex.setText(f"0x{subindex:02X}")
        self.raw.setText(format_bytes(data))
        self.value.setText(f"0x{int.from_bytes(data, 'little'):X}")

    def show_objects(self, entries: object, source: str) -> None:
        values = list(entries)
        self.objects.setRowCount(len(values))
        for row, entry in enumerate(values):
            data = (
                f"0x{entry.index:04X}",
                f"0x{entry.subindex:02X}",
                entry.name or "—",
                str(entry.data_type),
                str(entry.access),
                source,
            )
            for col, value in enumerate(data):
                self.objects.setItem(row, col, QTableWidgetItem(value))


class PdoPage(QWidget):
    refresh_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0
        self.summary = QLabel("尚未读取 PDO 映射")
        refresh = QPushButton("读取实际映射")
        refresh.clicked.connect(lambda: self.refresh_requested.emit(self.position))
        self.tabs = QTabWidget()
        self.rx = _table(["PDO", "Entry", "Name", "Type", "Bits", "Byte Offset", "Bit Offset"])
        self.tx = _table(["PDO", "Entry", "Name", "Type", "Bits", "Byte Offset", "Bit Offset"])
        self.tabs.addTab(self.rx, "RxPDO（主站→从站）")
        self.tabs.addTab(self.tx, "TxPDO（从站→主站）")
        top = QHBoxLayout()
        top.addWidget(self.summary)
        top.addStretch()
        top.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.tabs)

    @staticmethod
    def _fill(table: QTableWidget, entries: list[PdoEntry]) -> None:
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = (
                f"0x{entry.pdo_index:04X}",
                f"0x{entry.index:04X}:{entry.subindex:02X}",
                entry.name or "—",
                entry.data_type or "Unknown",
                str(entry.bit_length),
                str(entry.byte_offset),
                str(entry.bit_in_byte),
            )
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(value))

    def set_mapping(self, rx: list[PdoEntry], tx: list[PdoEntry]) -> None:
        self._fill(self.rx, rx)
        self._fill(self.tx, tx)
        self.summary.setText(f"RxPDO {len(rx)} Entry / TxPDO {len(tx)} Entry")


class IoPage(QWidget):
    output_requested = Signal(int, bytes)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0
        self.control_mode = False
        self.mode = QPushButton("监视模式")
        self.mode.clicked.connect(self._toggle_mode)
        self.inputs = QTextEdit()
        self.inputs.setReadOnly(True)
        self.outputs = QLineEdit()
        self.outputs.setEnabled(False)
        self.outputs.textEdited.connect(self._mark_pending)
        self.apply = QPushButton("应用输出")
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self._apply)
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("Inputs · TxPDO"))
        left_l.addWidget(self.inputs)
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.addWidget(QLabel("Outputs · RxPDO"))
        right_l.addWidget(self.outputs)
        right_l.addWidget(self.apply)
        right_l.addStretch()
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([500, 500])
        top = QHBoxLayout()
        top.addWidget(QLabel("周期停止后保留最后值并标记为过期"))
        top.addStretch()
        top.addWidget(self.mode)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(split)
        self.mode.setEnabled(False)

    def _toggle_mode(self) -> None:
        if not self.control_mode:
            QMessageBox.information(
                self, "输出控制模式", "编辑值只进入待应用状态；点击“应用输出”后才更新周期输出缓冲区。"
            )
        self.control_mode = not self.control_mode
        self.mode.setText("输出控制模式" if self.control_mode else "监视模式")
        self.outputs.setEnabled(self.control_mode)
        self.apply.setEnabled(False)
        self.apply.setText("应用输出")

    def _mark_pending(self) -> None:
        if self.control_mode:
            self.apply.setEnabled(True)
            self.apply.setText("● 待应用 · 应用输出")

    def _apply(self) -> None:
        try:
            data = parse_hex_bytes(self.outputs.text())
        except ValueError as exc:
            self.outputs.setToolTip(str(exc))
            return
        self.output_requested.emit(self.position, data)
        self.apply.setEnabled(False)
        self.apply.setText("✓ 已应用")

    def update_snapshot(self, snapshot: ProcessDataSnapshot) -> None:
        idx = self.position - 1
        if not 0 <= idx < len(snapshot.inputs):
            return
        self.inputs.setPlainText(format_bytes(snapshot.inputs[idx]))
        if not self.outputs.hasFocus():
            self.outputs.setText(format_bytes(snapshot.outputs[idx]))

    def set_stale(self, stale: bool) -> None:
        self.inputs.setPlaceholderText("⚠ 周期已停止，显示的最后值已过期" if stale else "等待周期数据…")

    def set_cycle_running(self, running: bool) -> None:
        self.mode.setEnabled(running)
        if not running and self.control_mode:
            self.control_mode = False
            self.mode.setText("监视模式")
            self.outputs.setEnabled(False)
            self.apply.setEnabled(False)
            self.apply.setText("应用输出")


class RegisterPage(QWidget):
    read_requested = Signal(int, int, int)
    prepare_write_requested = Signal(int, int, bytes, object, bool)
    execute_write_requested = Signal(object)
    watch_requested = Signal(int, object)

    def __init__(self) -> None:
        super().__init__()
        self.position = 0
        self.address = QLineEdit("0x0130")
        self.length = QComboBox()
        self.length.addItems(["1", "2", "4", "8", "16"])
        self.length.setCurrentText("2")
        self.result = QTextEdit()
        self.result.setReadOnly(True)
        self.bitfields = _table(["位域", "Mask", "当前", "目标", "说明"])
        self.bitfields.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self._last_register_data = b""
        build_bits = QPushButton("从位域目标生成最终字节")
        build_bits.clicked.connect(self._build_target_from_bits)
        self.write_mode = QCheckBox("开启寄存器写入模式")
        self.semantics = QComboBox()
        self.semantics.addItems([item.value for item in AccessSemantics if item is not AccessSemantics.RO])
        self.target = QLineEdit()
        self.target.setPlaceholderText("最终字节，例如 08 00")
        self.write = QPushButton("重新读取并准备写入")
        self.write.setEnabled(False)
        self.write_mode.toggled.connect(self._write_mode_changed)
        self.write.clicked.connect(self._prepare_write)
        self.watch_items: list[tuple[int, int]] = []
        self.watch = _table(["地址", "长度", "当前值", "时间"])
        add_watch = QPushButton("加入监视")
        add_watch.clicked.connect(self._add_watch)
        self.monitor = QPushButton("▶ 启动低优先级监视")
        self.monitor.setCheckable(True)
        self.monitor.toggled.connect(self._monitor)
        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(1000)
        self.watch_timer.timeout.connect(
            lambda: self.watch_requested.emit(self.position, tuple(self.watch_items))
        )
        self.standard = _table(["地址", "名称", "宽度", "访问", "诊断组"])
        self.definitions = ProfileRegistry.standard_registers()
        self.standard.setRowCount(len(self.definitions))
        for row, item in enumerate(self.definitions):
            for col, value in enumerate(
                (f"0x{item['address']:04X}", item["name"], item["width"], item["access"], item["group"])
            ):
                self.standard.setItem(row, col, QTableWidgetItem(str(value)))
        read = QPushButton("读取")
        read.clicked.connect(self._read)
        form = QFormLayout()
        form.addRow("起始地址", self.address)
        form.addRow("长度 (bytes)", self.length)
        form.addRow(read)
        form.addRow(self.write_mode)
        form.addRow("访问语义", self.semantics)
        form.addRow("目标/最终字节", self.target)
        form.addRow(self.write)
        watch_actions = QHBoxLayout()
        watch_actions.addWidget(add_watch)
        watch_actions.addWidget(self.monitor)
        watch_actions.addStretch()
        warning = QLabel("● 默认只读。未知寄存器允许原始读取，但不会推断位语义。")
        warning.setObjectName("infoBanner")
        tabs = QTabWidget()
        tabs.addTab(self.standard, "标准寄存器地图 / 快捷诊断")
        tabs.addTab(self.watch, "监视列表")
        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addLayout(form)
        layout.addLayout(watch_actions)
        layout.addWidget(self.result)
        layout.addWidget(self.bitfields)
        layout.addWidget(build_bits)
        layout.addWidget(tabs)

    def _read(self) -> None:
        try:
            self.read_requested.emit(
                self.position, int(self.address.text(), 0), int(self.length.currentText())
            )
        except ValueError:
            self.address.setToolTip("地址必须是 0x0000–0xFFFF")

    def _write_mode_changed(self, enabled: bool) -> None:
        if enabled:
            answer = QMessageBox.warning(
                self,
                "开启寄存器写入模式",
                "寄存器写入可能导致掉线、复位或不可预期副作用。未知地址无法检查位语义。是否继续？",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.write_mode.blockSignals(True)
                self.write_mode.setChecked(False)
                self.write_mode.blockSignals(False)
                enabled = False
        self.write.setEnabled(enabled)

    def _prepare_write(self) -> None:
        try:
            address = int(self.address.text(), 0)
            target = parse_hex_bytes(self.target.text())
            semantics = AccessSemantics(self.semantics.currentText())
        except ValueError as exc:
            self.target.setToolTip(str(exc))
            return
        definition = next(
            (
                item
                for item in self.definitions
                if item["address"] == address and item["width"] == len(target)
            ),
            None,
        )
        if definition is not None:
            declared = AccessSemantics(str(definition["access"]))
            if declared is AccessSemantics.RO:
                self.target.setToolTip("标准地图将此寄存器标记为只读")
                return
            semantics = declared
        self.prepare_write_requested.emit(self.position, address, target, semantics, definition is not None)

    def _add_watch(self) -> None:
        try:
            item = (int(self.address.text(), 0), int(self.length.currentText()))
        except ValueError:
            return
        if item not in self.watch_items:
            self.watch_items.append(item)
        self.watch.setRowCount(len(self.watch_items))
        for row, (address, size) in enumerate(self.watch_items):
            self.watch.setItem(row, 0, QTableWidgetItem(f"0x{address:04X}"))
            self.watch.setItem(row, 1, QTableWidgetItem(str(size)))

    def _monitor(self, enabled: bool) -> None:
        self.monitor.setText("■ 停止监视" if enabled else "▶ 启动低优先级监视")
        if enabled and self.watch_items:
            self.watch_timer.start()
        else:
            self.watch_timer.stop()

    def show_watch(self, values: dict[tuple[int, int], object]) -> None:
        for row, key in enumerate(self.watch_items):
            value = values.get(key)
            if value is not None:
                self.watch.setItem(row, 2, QTableWidgetItem(format_bytes(value.data)))
                self.watch.setItem(row, 3, QTableWidgetItem(f"{value.timestamp:.3f}"))

    def confirm_plan(self, plan: RegisterWritePlan) -> None:
        warning = "未知地址：无法检查位语义和副作用。\n" if not plan.known_register else ""
        text = (
            f"目标：Slave {plan.position}\n地址：0x{plan.address:04X}\n语义：{plan.semantics.value}\n"
            f"当前值：{format_bytes(plan.current)}\n目标值：{format_bytes(plan.target)}\n"
            f"变化掩码：{format_bytes(plan.changed_mask)}\n最终字节：{format_bytes(plan.target)}"
        )
        if (
            QMessageBox.question(
                self,
                "确认 FPWR 寄存器写入",
                warning + text,
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.execute_write_requested.emit(plan)

    def show_write_result(self, plan: RegisterWritePlan, result: RegisterWriteResult) -> None:
        readback = "不适用" if result.readback is None else format_bytes(result.readback)
        self.result.setPlainText(
            f"{result.conclusion}\nFPWR WKC: {result.fpwr_wkc}\n回读: {readback}\n验证: {result.verified}"
        )

    def show_read(self, address: int, data: bytes) -> None:
        self._last_register_data = data
        self.result.setPlainText(
            f"范围 0x{address:04X}–0x{address + len(data) - 1:04X}\nRaw {format_bytes(data)}\nHex 0x{int.from_bytes(data, 'little'):0{len(data) * 2}X}\nUnsigned {int.from_bytes(data, 'little')}"
        )
        definition = next(
            (item for item in self.definitions if item["address"] == address and item["width"] == len(data)),
            None,
        )
        fields = [] if definition is None else list(definition.get("bit_fields", []))
        self.bitfields.setRowCount(len(fields))
        raw = int.from_bytes(data, "little")
        for row, field in enumerate(fields):
            mask = ((1 << field["bits"]) - 1) << field["shift"]
            current = (raw & mask) >> field["shift"]
            values = (
                field["name"],
                f"0x{mask:0{len(data) * 2}X}",
                current,
                current,
                definition["description"],
            )
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col != 3:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, field if col == 3 else None)
                self.bitfields.setItem(row, col, item)

    def _build_target_from_bits(self) -> None:
        if not self._last_register_data or not self.write_mode.isChecked():
            self.target.setToolTip("请先读取寄存器并开启写入模式")
            return
        value = int.from_bytes(self._last_register_data, "little")
        try:
            for row in range(self.bitfields.rowCount()):
                item = self.bitfields.item(row, 3)
                field = item.data(Qt.ItemDataRole.UserRole)
                desired = int(item.text(), 0)
                if not 0 <= desired < (1 << field["bits"]):
                    raise ValueError(field["name"])
                mask = ((1 << field["bits"]) - 1) << field["shift"]
                value = (value & ~mask) | (desired << field["shift"])
        except (TypeError, ValueError) as exc:
            self.target.setToolTip(f"位域目标值超出范围：{exc}")
            return
        self.target.setText(format_bytes(value.to_bytes(len(self._last_register_data), "little")))


class EepromPage(QWidget):
    esi_loaded = Signal(object)
    read_requested = Signal(int)
    backup_requested = Signal(int, object)
    flash_requested = Signal(int, bytes, object, object, bool)
    restore_requested = Signal(int, object, object, bool)
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.parser = EsiParser()
        self.settings = AppSettings()
        self.document: EsiDocument | None = None
        self.position = 0
        self.current_raw: bytes | None = None
        self.generated: SiiGenerationReport | None = None
        self.file = QLabel("将 XML 文件拖到这里，或点击选择")
        self.select = QPushButton("选择 XML 文件")
        self.select.clicked.connect(self._select)
        self.devices = QComboBox()
        self.devices.setEnabled(False)
        self.recent = QComboBox()
        self.recent.addItem("最近 XML…", "")
        for item in self.settings.recent_esi:
            self.recent.addItem(item, item)
        self.recent.activated.connect(self._load_recent)
        self.preview = _table(["字段", "当前设备", "目标 XML", "结果"])
        self.hex_view = QTextEdit()
        self.hex_view.setReadOnly(True)
        views = QTabWidget()
        views.addTab(self.preview, "Smart View")
        views.addTab(self.hex_view, "Hex View（只读）")
        self.status = QLabel("尚未选择目标 XML")
        self.read = QPushButton("完整读取 EEPROM")
        self.read.clicked.connect(lambda: self.read_requested.emit(self.position))
        self.backup = QPushButton("仅备份 BIN + JSON")
        self.backup.clicked.connect(self._backup)
        self.generate = QPushButton("生成完整 SII 目标并预览")
        self.generate.clicked.connect(self._generate)
        self.flash = QPushButton("强制备份并烧录")
        self.flash.clicked.connect(self._flash)
        self.flash.setEnabled(False)
        self.restore = QPushButton("从 BIN 备份恢复")
        self.restore.clicked.connect(self._restore)
        self.cancel = QPushButton("安全取消")
        self.cancel.clicked.connect(self.cancel_requested)
        self.auto_reset = QCheckBox("EEPROM 校验成功后自动复位 ESC")
        self.auto_reset.setChecked(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        actions = QHBoxLayout()
        for button in (self.read, self.backup, self.generate, self.flash, self.restore, self.cancel):
            actions.addWidget(button)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("EEPROM 快速烧录"))
        layout.addWidget(self.file)
        layout.addWidget(self.select)
        layout.addWidget(self.recent)
        layout.addWidget(QLabel("XML 中的目标 Device"))
        layout.addWidget(self.devices)
        layout.addLayout(actions)
        layout.addWidget(self.auto_reset)
        layout.addWidget(self.progress)
        layout.addWidget(views)
        layout.addWidget(self.status)
        layout.addStretch()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls() and any(
            url.toLocalFile().lower().endswith(".xml") for url in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        self.load_path(Path(event.mimeData().urls()[0].toLocalFile()))

    def _select(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 ESI XML", "", "EtherCAT ESI XML (*.xml)")
        if path:
            self.load_path(Path(path))

    def load_path(self, path: Path) -> None:
        try:
            self.document = self.parser.parse(path)
        except Exception as exc:
            self.status.setText(f"× XML 解析失败：{exc}")
            return
        self.file.setText(f"✓ {path.name}\n{path.resolve()}")
        resolved = str(path.resolve())
        self.settings.remember_esi(resolved)
        if self.recent.findData(resolved) < 0:
            self.recent.insertItem(1, resolved, resolved)
        self.devices.clear()
        for device in self.document.devices:
            self.devices.addItem(
                f"{device.name} · 0x{device.product_code:08X} · 0x{device.revision:08X}", device.ordinal
            )
        self.devices.setEnabled(True)
        self.status.setText(
            f"✓ XML 已解析，包含 {len(self.document.devices)} 个 Device；尚未执行任何硬件写入"
        )
        self.esi_loaded.emit(self.document)

    def _load_recent(self, index: int) -> None:
        path = self.recent.itemData(index)
        if path:
            self.load_path(Path(path))

    def selected_device(self):
        if self.document is None or self.devices.currentIndex() < 0:
            return None
        return self.document.devices[int(self.devices.currentData())]

    def _backup_directory(self) -> Path:
        path = QFileDialog.getExistingDirectory(self, "选择自动备份目录")
        return Path(path) if path else Path()

    def _backup(self) -> None:
        directory = self._backup_directory()
        if directory != Path():
            self.backup_requested.emit(self.position, directory)

    def _generate(self) -> None:
        device = self.selected_device()
        if device is None:
            self.status.setText("× 请先选择有效 XML/Device")
            return
        try:
            self.generated = SiiGenerator().generate(device)
        except Exception as exc:
            self.status.setText(f"× SII 无法生成：{exc}")
            self.flash.setEnabled(False)
            return
        fields = (
            ("Vendor ID", "—", f"0x{device.vendor_id:08X}"),
            ("Product Code", "—", f"0x{device.product_code:08X}"),
            ("Revision", "—", f"0x{device.revision:08X}"),
            (
                "容量",
                str(len(self.current_raw)) if self.current_raw else "未读取",
                f"{len(self.generated.image)} bytes",
            ),
            ("转换限制", "—", "；".join(self.generated.omitted)),
        )
        self.preview.setRowCount(len(fields))
        for row, (field, current, target) in enumerate(fields):
            for col, value in enumerate(
                (field, current, target, "提示但不因身份不匹配阻止" if row < 3 else "—")
            ):
                self.preview.setItem(row, col, QTableWidgetItem(value))
        self.status.setText("✓ 已生成完整 SII 二进制目标；未从旧 EEPROM 合并 Serial/Alias/私有数据")
        self.flash.setEnabled(True)

    def _flash(self) -> None:
        device = self.selected_device()
        if device is None or self.generated is None:
            return
        directory = self._backup_directory()
        if directory == Path():
            return
        text = (
            f"目标：Slave {self.position}\nDevice：{device.name}\n目标容量：{len(self.generated.image)} bytes\n"
            "烧录前将强制完整备份。身份不匹配仅提示；目标完全来自所选 XML，不合并旧 EEPROM 数据。"
        )
        if (
            QMessageBox.warning(
                self,
                "确认 EEPROM 烧录",
                text,
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.flash_requested.emit(
                self.position, self.generated.image, device, directory, self.auto_reset.isChecked()
            )

    def _restore(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择 EEPROM BIN 备份", "", "EEPROM binary (*.bin)")
        if not path:
            return
        directory = self._backup_directory()
        if directory == Path():
            return
        if (
            QMessageBox.warning(
                self,
                "确认从备份恢复",
                f"目标：Slave {self.position}\n备份：{path}\n恢复前仍会再次强制完整备份当前 EEPROM。",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.restore_requested.emit(self.position, Path(path), directory, self.auto_reset.isChecked())

    def show_read(self, raw: bytes) -> None:
        self.current_raw = raw
        lines = []
        for offset in range(0, len(raw), 16):
            chunk = raw[offset : offset + 16]
            lines.append(
                f"{offset:08X}  {format_bytes(chunk):47}  {''.join(chr(x) if 32 <= x < 127 else '.' for x in chunk)}"
            )
        self.hex_view.setPlainText("\n".join(lines))
        try:
            parsed = SiiParser().parse(raw)
            detail = f"SII v{parsed.version}，{len(parsed.categories)} categories，SHA-256 {parsed.sha256}"
        except Exception as exc:
            detail = f"SII 结构错误：{exc}"
        self.status.setText(f"✓ 已完整读取 {len(raw)} 字节；Hex View 只读\n{detail}")

    def show_progress(self, progress: OperationProgress) -> None:
        percent = 0 if not progress.total else round(progress.completed * 100 / progress.total)
        self.progress.setValue(percent)
        self.progress.setFormat(f"{progress.stage} · {progress.detail} · %p%")

    def show_flash_result(self, result: EepromFlashResult) -> None:
        c = result.comparison
        reset = "未启用" if result.reset_sequence is None else str(result.reset_sequence)
        self.status.setText(
            f"{'✓' if result.image_success else '×'} EEPROM 镜像校验：{result.image_verification}\n"
            f"完整回读：{result.bytes_read_back} bytes；逐字节差异：{c.differing_bytes}\n"
            f"目标 SHA-256：{c.target_sha256}\n回读 SHA-256：{c.readback_sha256}\n"
            f"SII 结构：{result.sii_valid}；XML 语义：{result.semantic_valid}\n"
            f"ESC 复位序列：{reset}；重新发现：{result.rediscovered}；重新加载复核：{result.reload_verified}"
        )
