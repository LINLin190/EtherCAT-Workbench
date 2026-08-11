from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSignalBlocker, Qt, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDockWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..controller import AppController
from ..infrastructure.npcap import NPCAP_DOWNLOAD_URL, detect_npcap
from ..infrastructure.settings import AppSettings
from ..models import AdapterInfo, BackendMode, EtherCatState, LogRecord, ProcessDataSnapshot, SlaveInfo
from .context_panel import ContextPanel
from .pages import CoePage, EepromPage, IoPage, OverviewPage, PdoPage, RegisterPage, _table
from .styles import STYLE


class MainWindow(QMainWindow):
    def __init__(self, controller: AppController) -> None:
        super().__init__()
        self.controller = controller
        self.settings = AppSettings()
        self.current_position = 0
        self.slaves: list[SlaveInfo] = []
        self.current_esi_device = None
        self.pdo_mapped: set[int] = set()
        self.busy = False
        self.setWindowTitle("EtherCAT Workbench")
        self.resize(1440, 900)
        self.setMinimumSize(1280, 720)
        self.setStyleSheet(STYLE)
        self._build_menu()
        self._build_toolbar()
        self._build_central()
        self._build_docks()
        self._build_status()
        self._wire()
        self._apply_state()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        load_esi = QAction("加载 ESI XML…", self)
        load_esi.triggered.connect(self._show_eeprom)
        file_menu.addAction(load_esi)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        view = self.menuBar().addMenu("视图")
        self._view_menu = view
        help_menu = self.menuBar().addMenu("帮助")
        npcap = QAction("Npcap 安装说明", self)
        npcap.triggered.connect(self._show_npcap_help)
        help_menu.addAction(npcap)
        help_menu.addAction(
            "关于",
            lambda: QMessageBox.about(
                self, "关于", "EtherCAT Workbench 0.1.0\nPython 3.11+ · pysoem 1.1.13"
            ),
        )

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("连接与扫描", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.mode = QComboBox()
        self.mode.addItem("Demo / Mock（安全）", BackendMode.DEMO)
        self.mode.addItem("Real pySOEM", BackendMode.REAL)
        self.mode.setCurrentIndex(self.mode.findData(self.controller.mode))
        self.adapter = QComboBox()
        self.adapter.setMinimumWidth(300)
        self.refresh_adapters = QPushButton("↻ 刷新网卡")
        self.connect_button = QPushButton("连接")
        self.connect_button.setObjectName("primaryButton")
        self.scan_button = QPushButton("扫描从站")
        self.connection_label = QLabel("○ 未连接")
        self.connection_label.setObjectName("sectionLabel")
        for widget in (
            self._section("① 连接与扫描"),
            self.mode,
            self.adapter,
            self.refresh_adapters,
            self.connect_button,
            self.scan_button,
        ):
            toolbar.addWidget(widget)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        toolbar.addWidget(self.connection_label)

        self.addToolBarBreak()
        state_toolbar = QToolBar("目标状态与周期通信", self)
        state_toolbar.setObjectName("stateToolbar")
        state_toolbar.setMovable(False)
        self.addToolBar(state_toolbar)
        self.target_label = QLabel("操作目标：尚未扫描")
        self.target_label.setObjectName("targetLabel")
        self.state_group = QButtonGroup(self)
        self.state_group.setExclusive(True)
        self.state_buttons: dict[EtherCatState, QPushButton] = {}
        for state in (EtherCatState.INIT, EtherCatState.PRE_OP, EtherCatState.SAFE_OP, EtherCatState.OP):
            button = QPushButton(state.label)
            button.setObjectName("stateButton")
            button.setCheckable(True)
            button.setToolTip(f"直接请求当前操作目标进入 {state.label}")
            button.clicked.connect(lambda checked=False, target=state: self._request_state(target))
            self.state_group.addButton(button)
            self.state_buttons[state] = button
        self.period = QComboBox()
        self.period.addItems(["1 ms", "2 ms", "4 ms", "10 ms"])
        self.period.setCurrentText("10 ms")
        self.cycle_button = QPushButton("▶ 启动周期")
        self.cycle_button.setObjectName("primaryButton")
        self.wkc_label = QLabel("WKC — / —")
        self.wkc_label.setObjectName("sectionLabel")
        state_toolbar.addWidget(self._section("② 当前目标与状态"))
        state_toolbar.addWidget(self.target_label)
        for button in self.state_buttons.values():
            state_toolbar.addWidget(button)
        state_spacer = QWidget()
        state_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        state_toolbar.addWidget(state_spacer)
        state_toolbar.addWidget(self._section("③ 周期通信"))
        state_toolbar.addWidget(self.period)
        state_toolbar.addWidget(self.cycle_button)
        state_toolbar.addWidget(self.wkc_label)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _build_central(self) -> None:
        self.stack = QStackedWidget()
        home = QWidget()
        home_l = QVBoxLayout(home)
        home_l.addStretch()
        home_card = QFrame()
        home_card.setObjectName("homeCard")
        home_card.setMaximumWidth(680)
        card_l = QVBoxLayout(home_card)
        card_l.setContentsMargins(42, 34, 42, 34)
        title = QLabel("开始 EtherCAT 调试")
        title.setObjectName("heroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        intro = QLabel("按照下面的顺序开始。Demo 模式不会访问真实网卡或写入硬件，适合先熟悉完整操作流程。")
        intro.setObjectName("heroText")
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignmentFlag.AlignCenter)
        steps = QLabel(
            "① 选择模式和网卡　　② 连接并扫描从站\n③ 选择操作目标　　　④ 读取状态、PDO 或启动周期通信"
        )
        steps.setObjectName("recommendation")
        steps.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.home_action = QPushButton("连接 Demo 网卡")
        self.home_action.setObjectName("primaryButton")
        self.home_action.clicked.connect(self._home_primary)
        card_l.addWidget(title)
        card_l.addSpacing(8)
        card_l.addWidget(intro)
        card_l.addSpacing(18)
        card_l.addWidget(steps)
        card_l.addSpacing(14)
        card_l.addWidget(self.home_action)
        home_row = QHBoxLayout()
        home_row.addStretch()
        home_row.addWidget(home_card)
        home_row.addStretch()
        home_l.addLayout(home_row)
        home_l.addStretch()
        self.master_table = _table(
            [
                "Position",
                "Name",
                "ESC",
                "State",
                "Vendor ID",
                "Product Code",
                "Revision",
                "Input",
                "Output",
                "AL Status",
            ]
        )
        master = QWidget()
        ml = QVBoxLayout(master)
        mt = QLabel("总线概览")
        mt.setObjectName("pageTitle")
        self.master_hint = QLabel("选择左侧从站查看详细信息；顶部状态按钮在选择 Master 时作用于全部从站。")
        self.master_hint.setObjectName("infoBanner")
        ml.addWidget(mt)
        ml.addWidget(self.master_hint)
        ml.addWidget(self.master_table)
        self.pages = QTabWidget()
        self.overview = OverviewPage()
        self.coe = CoePage()
        self.pdo = PdoPage()
        self.io = IoPage()
        self.registers = RegisterPage()
        self.eeprom = EepromPage()
        for page, name in (
            (self.overview, "概览"),
            (self.coe, "CoE"),
            (self.pdo, "PDO映射"),
            (self.io, "在线I/O"),
            (self.registers, "寄存器"),
            (self.eeprom, "EEPROM"),
        ):
            self.pages.addTab(page, name)
        self.stack.addWidget(home)
        self.stack.addWidget(master)
        self.stack.addWidget(self.pages)
        self.setCentralWidget(self.stack)

    def _build_docks(self) -> None:
        self.slave_dock = QDockWidget("从站导航", self)
        self.slave_dock.setObjectName("slaveDock")
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(220)
        self.slave_dock.setWidget(self.tree)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.slave_dock)
        self.context_dock = QDockWidget("当前目标与下一步", self)
        self.context_dock.setObjectName("contextDock")
        self.context_panel = ContextPanel()
        self.context_panel.recommended_requested.connect(self._run_recommended)
        self.context_panel.refresh_requested.connect(self.controller.refresh_states)
        self.context_panel.reconfig_requested.connect(self._confirm_reconfig)
        self.context_panel.recover_requested.connect(self._confirm_recover)
        self.context = self.context_panel.target
        self.recommendation = self.context_panel.recommendation
        self.next_action = self.context_panel.next_action
        self.refresh_state = self.context_panel.refresh
        self.advanced_toggle = self.context_panel.advanced_toggle
        self.reconfig = self.context_panel.reconfig
        self.recover = self.context_panel.recover
        self.context_dock.setWidget(self.context_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.context_dock)
        self.log_dock = QDockWidget("日志 (0)", self)
        self.log_dock.setObjectName("logDock")
        log_widget = QWidget()
        ll = QVBoxLayout(log_widget)
        actions = QHBoxLayout()
        self.pause_log = QPushButton("暂停滚动")
        self.pause_log.setCheckable(True)
        copy = QPushButton("复制")
        clear = QPushButton("清空")
        copy.clicked.connect(self._copy_log)
        clear.clicked.connect(self._clear_log)
        actions.addWidget(self.pause_log)
        actions.addWidget(copy)
        actions.addWidget(clear)
        actions.addStretch()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        ll.addLayout(actions)
        ll.addWidget(self.log)
        self.log_dock.setWidget(log_widget)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        for dock in (self.slave_dock, self.context_dock, self.log_dock):
            self._view_menu.addAction(dock.toggleViewAction())
        self.resizeDocks([self.slave_dock, self.context_dock], [260, 300], Qt.Orientation.Horizontal)
        self.resizeDocks([self.log_dock], [210], Qt.Orientation.Vertical)
        self.log_dock.hide()

    def _build_status(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_text = QLabel("就绪")
        self.status_adapter = QLabel("Adapter: —")
        self.status_slaves = QLabel("Slaves: 0")
        self.status_target = QLabel("Target: —")
        self.status_cycle = QLabel("Cycle: ■ Stopped")
        self.status_metrics = QLabel("WKC: —/— · Timeout: 0 · Errors: 0")
        self.log_button = QPushButton("日志 0")
        self.log_button.setToolTip("展开或收起运行日志；发生错误时自动展开。")
        self.log_button.clicked.connect(lambda: self.log_dock.setVisible(not self.log_dock.isVisible()))
        status.addWidget(self.status_text, 1)
        for label in (
            self.status_adapter,
            self.status_slaves,
            self.status_target,
            self.status_cycle,
            self.status_metrics,
        ):
            status.addPermanentWidget(label)
        status.addPermanentWidget(self.log_button)

    def _wire(self) -> None:
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.refresh_adapters.clicked.connect(self.controller.enumerate_adapters)
        self.connect_button.clicked.connect(self._connect)
        self.scan_button.clicked.connect(self.controller.scan)
        self.cycle_button.clicked.connect(self._cycle)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.controller.adapters_changed.connect(self._adapters)
        self.controller.connection_changed.connect(self._connection)
        self.controller.slaves_changed.connect(self._slaves)
        self.controller.pdo_mapping_ready.connect(self._mapping)
        self.controller.process_data.connect(self._process_data)
        self.controller.operation_error.connect(self._error)
        self.controller.log_added.connect(self._log)
        self.controller.busy_changed.connect(self._busy_changed)
        self.controller.cycle_changed.connect(self._cycle_changed)
        self.controller.result_ready.connect(self._result)
        self.coe.read_requested.connect(self.controller.sdo_read)
        self.coe.write_requested.connect(self.controller.sdo_write)
        self.coe.online_dictionary_requested.connect(self.controller.read_object_dictionary)
        self.pdo.refresh_requested.connect(self.controller.read_pdo_mapping)
        self.io.output_requested.connect(self.controller.set_output)
        self.registers.read_requested.connect(self.controller.register_read)
        self.registers.prepare_write_requested.connect(self.controller.register_prepare_write)
        self.registers.execute_write_requested.connect(self.controller.register_execute_write)
        self.registers.watch_requested.connect(self.controller.watch_registers)
        self.eeprom.read_requested.connect(self.controller.read_eeprom)
        self.eeprom.backup_requested.connect(self.controller.backup_eeprom)
        self.eeprom.flash_requested.connect(self.controller.flash_eeprom)
        self.eeprom.restore_requested.connect(self.controller.restore_eeprom)
        self.eeprom.cancel_requested.connect(self.controller.cancel_long_operation)
        self.eeprom.esi_loaded.connect(self._esi_loaded)
        self.controller.progress_changed.connect(self.eeprom.show_progress)
        self.eeprom.auto_reset.setChecked(self.settings.auto_reset_esc)
        self.eeprom.auto_reset.toggled.connect(lambda value: setattr(self.settings, "auto_reset_esc", value))

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        if mode is BackendMode.REAL and not detect_npcap().ready:
            self._show_npcap_help()
            with QSignalBlocker(self.mode):
                self.mode.setCurrentIndex(self.mode.findData(BackendMode.DEMO))
            self.status_text.setText("⚠ Real 模式需要 Npcap 1.88+ 和 WinPcap 兼容模式")
            return
        self.controller.switch_mode(mode)

    def _show_npcap_help(self) -> None:
        status = detect_npcap()
        if status.ready:
            QMessageBox.information(
                self,
                "Npcap 已就绪",
                status.guidance + "\n\nReal 模式通常仍需要管理员权限。",
            )
            return
        answer = QMessageBox.question(
            self,
            "安装或升级 Npcap 1.88",
            status.guidance
            + "\n\nReal EtherCAT 模式需要 Npcap 1.88 或更高版本，并启用 "
            "WinPcap API-compatible Mode。\n\n是否从 Npcap 官方网站下载 1.88 安装程序？",
            QMessageBox.StandardButton.No | QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            QDesktopServices.openUrl(QUrl(NPCAP_DOWNLOAD_URL))

    def _home_primary(self) -> None:
        if not self.controller.connected:
            self._connect()
        elif not self.slaves:
            self.controller.scan()

    def _request_state(self, state: EtherCatState) -> None:
        selected = self._selected_slave()
        if selected is not None and selected.state is state:
            self.status_text.setText(f"✓ Slave {selected.position} 已处于 {state.label}")
            return
        if self.current_position == 0 and self.slaves and all(slave.state is state for slave in self.slaves):
            self.status_text.setText(f"✓ 全部从站已处于 {state.label}")
            return
        self.controller.request_state(self.current_position or None, state)

    def _selected_slave(self) -> SlaveInfo | None:
        if 1 <= self.current_position <= len(self.slaves):
            return self.slaves[self.current_position - 1]
        return None

    def _update_state_buttons(self) -> None:
        state: EtherCatState | None = None
        selected = self._selected_slave()
        if selected is not None:
            state = selected.state
        elif self.slaves and all(slave.state is self.slaves[0].state for slave in self.slaves):
            state = self.slaves[0].state
        self.state_group.setExclusive(False)
        for candidate, button in self.state_buttons.items():
            button.setChecked(candidate is state)
        self.state_group.setExclusive(True)

    def _update_context(self) -> None:
        selected = self._selected_slave()
        if not self.controller.connected:
            self.context.setText("未连接\n当前处于安全的离线状态。")
            self.recommendation.setText("选择 Demo 或 Real 模式、确认网卡，然后建立连接。")
            self.next_action.setText("连接网卡")
            self._recommended_action = "connect"
            self.target_label.setText("操作目标：尚未连接")
            self.status_target.setText("Target: —")
        elif not self.slaves:
            self.context.setText(f"Master\n{self.adapter.currentText()}\n尚未发现从站")
            self.recommendation.setText("连接已建立。扫描总线以发现从站并读取身份信息。")
            self.next_action.setText("扫描从站")
            self._recommended_action = "scan"
            self.target_label.setText("操作目标：Master · 尚未扫描")
            self.status_target.setText("Target: Master")
        elif selected is None:
            self.context.setText(f"Master 总线\n{len(self.slaves)} 个从站\n状态按钮作用于全部从站")
            self.recommendation.setText("从左侧选择一个从站查看详情；也可在顶部对全部从站切换状态。")
            self.next_action.setText("选择第一个从站")
            self._recommended_action = "select-first"
            self.target_label.setText(f"操作目标：全部从站（{len(self.slaves)}）")
            self.status_target.setText("Target: All slaves")
        else:
            self.context.setText(
                f"Slave {selected.position} · {selected.name}\n"
                f"实际 ESC：{selected.chip_model}\n参考族：{selected.register_family}\n"
                f"当前状态：{selected.state.label}\nAL Status：0x{selected.al_status:04X}"
            )
            self.target_label.setText(f"操作目标：Slave {selected.position} · {selected.chip_model}")
            self.status_target.setText(f"Target: Slave {selected.position} · {selected.state.label}")
            if self.controller.cycle_running:
                self.recommendation.setText("周期通信正在运行。可在“在线 I/O”查看实时数据和受控输出。")
                self.next_action.setText("打开在线 I/O")
                self._recommended_action = "io"
            elif selected.state is EtherCatState.INIT:
                self.recommendation.setText("从站处于 INIT。普通 SDO/PDO 调试通常从 PRE-OP 开始。")
                self.next_action.setText("进入 PRE-OP")
                self._recommended_action = "preop"
            elif selected.state is EtherCatState.PRE_OP:
                if selected.position in self.pdo_mapped:
                    self.recommendation.setText(
                        "PDO 映射已读取。下一步可进入 SAFE-OP，检查输入并准备周期通信。"
                    )
                    self.next_action.setText("进入 SAFE-OP")
                    self._recommended_action = "safeop"
                else:
                    self.recommendation.setText("建议先读取实际 PDO 映射，确认输入输出布局后再进入 SAFE-OP。")
                    self.next_action.setText("读取 PDO 映射")
                    self._recommended_action = "pdo"
            else:
                if all(slave.state in {EtherCatState.SAFE_OP, EtherCatState.OP} for slave in self.slaves):
                    self.recommendation.setText(
                        "全部从站已准备过程数据。启动周期通信后可观察 WKC 和在线 I/O。"
                    )
                    self.next_action.setText("启动周期通信")
                    self._recommended_action = "cycle"
                else:
                    self.recommendation.setText("其他从站尚未准备过程数据。建议先将全部从站切换到 SAFE-OP。")
                    self.next_action.setText("全部从站进入 SAFE-OP")
                    self._recommended_action = "all-safeop"

    def _run_recommended(self) -> None:
        action = getattr(self, "_recommended_action", "connect")
        if action == "connect":
            self._connect()
        elif action == "scan":
            self.controller.scan()
        elif action == "select-first" and self.tree.topLevelItemCount():
            root = self.tree.topLevelItem(0)
            if root.childCount():
                self.tree.setCurrentItem(root.child(0))
        elif action == "preop":
            self._request_state(EtherCatState.PRE_OP)
        elif action == "pdo":
            self.pages.setCurrentWidget(self.pdo)
            self.controller.read_pdo_mapping(self.current_position)
        elif action == "safeop":
            self._request_state(EtherCatState.SAFE_OP)
        elif action == "all-safeop":
            self.controller.request_state(None, EtherCatState.SAFE_OP)
        elif action == "cycle":
            self._cycle()
        elif action == "io":
            self.pages.setCurrentWidget(self.io)

    def _confirm_reconfig(self) -> None:
        if (
            QMessageBox.question(
                self,
                "重新配置从站",
                f"目标：Slave {self.current_position}\n\n"
                "用于仍可通信、但配置或状态异常的从站。操作会重新下发配置并可能改变状态。是否继续？",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.controller.reconfig(self.current_position)

    def _confirm_recover(self) -> None:
        if (
            QMessageBox.warning(
                self,
                "恢复丢失从站",
                f"目标：Slave {self.current_position}\n\n"
                "仅用于网线恢复、从站重新上电或被标记为丢失的情况。将执行恢复和重新配置通信。是否继续？",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.controller.recover(self.current_position)

    def _adapters(self, adapters: list[AdapterInfo]) -> None:
        self.adapter.clear()
        for item in adapters:
            self.adapter.addItem(f"{item.description}", item.name)
        self.home_action.setEnabled(bool(adapters))
        self._apply_state()

    def _connect(self) -> None:
        if self.controller.connected:
            self.controller.disconnect_adapter()
        elif self.adapter.currentData():
            self.controller.connect_adapter(self.adapter.currentData())

    def _connection(self, connected: bool, text: str) -> None:
        self.connection_label.setText(("✓ " if connected else "○ ") + text)
        self.connect_button.setText("断开" if connected else "连接")
        self.connect_button.setObjectName("dangerButton" if connected else "primaryButton")
        self.connect_button.style().unpolish(self.connect_button)
        self.connect_button.style().polish(self.connect_button)
        self.status_adapter.setText(f"Adapter: {self.adapter.currentText() if connected else '—'}")
        self.stack.setCurrentIndex(1 if connected else 0)
        self.home_action.setText("扫描从站" if connected else "连接 Demo 网卡")
        self._apply_state()

    def _slaves(self, slaves: list[SlaveInfo]) -> None:
        previous_position = self.current_position
        self.slaves = slaves
        self.pdo_mapped.intersection_update(slave.position for slave in slaves)
        self.tree.clear()
        root = QTreeWidgetItem([f"● Master · {len(slaves)} Slaves"])
        root.setData(0, Qt.ItemDataRole.UserRole, 0)
        self.tree.addTopLevelItem(root)
        for slave in slaves:
            icon = (
                "●"
                if slave.state is EtherCatState.OP
                else "!"
                if slave.state is EtherCatState.SAFE_OP
                else "○"
            )
            item = QTreeWidgetItem(
                [f"{icon} {slave.position}  [{slave.chip_model}]  {slave.name}  {slave.state.label}"]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, slave.position)
            root.addChild(item)
        root.setExpanded(True)
        selected_item = root
        if previous_position:
            for index in range(root.childCount()):
                candidate = root.child(index)
                if candidate.data(0, Qt.ItemDataRole.UserRole) == previous_position:
                    selected_item = candidate
                    break
        self.tree.setCurrentItem(selected_item)
        self.master_table.setRowCount(len(slaves))
        for row, s in enumerate(slaves):
            i = s.identity
            values = (
                s.position,
                s.name,
                s.chip_model,
                s.state.label,
                f"0x{i.vendor_id:08X}",
                f"0x{i.product_code:08X}",
                f"0x{i.revision:08X}",
                f"{s.input_size} B",
                f"{s.output_size} B",
                f"0x{s.al_status:04X}",
            )
            for col, value in enumerate(values):
                self.master_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.status_slaves.setText(f"Slaves: {len(slaves)}")
        self.master_hint.setText(
            f"已发现 {len(slaves)} 个从站。选择左侧从站查看详情；选择 Master 时，顶部状态按钮作用于全部从站。"
        )
        self._apply_state()

    def _tree_selected(self, current: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        self.current_position = int(current.data(0, Qt.ItemDataRole.UserRole) or 0)
        if self.current_position == 0:
            self.stack.setCurrentIndex(1)
            self.overview.set_slave(None)
        else:
            self.stack.setCurrentIndex(2)
            slave = self.slaves[self.current_position - 1]
            self.overview.set_slave(slave)
            self.coe.position = self.pdo.position = self.io.position = self.registers.position = (
                self.eeprom.position
            ) = self.current_position
        self._apply_state()

    def _mapping(self, position: int, rx: object, tx: object) -> None:
        self.pdo_mapped.add(position)
        if position == self.current_position:
            rx_entries, tx_entries = list(rx), list(tx)
            if self.current_esi_device is not None:
                names = {
                    (entry.index, entry.subindex): (entry.name, entry.data_type)
                    for pdo in (*self.current_esi_device.rx_pdos, *self.current_esi_device.tx_pdos)
                    for entry in pdo.entries
                }
                from dataclasses import replace

                rx_entries = [
                    replace(
                        entry,
                        name=names.get((entry.index, entry.subindex), (None, None))[0],
                        data_type=names.get((entry.index, entry.subindex), (None, None))[1],
                    )
                    for entry in rx_entries
                ]
                tx_entries = [
                    replace(
                        entry,
                        name=names.get((entry.index, entry.subindex), (None, None))[0],
                        data_type=names.get((entry.index, entry.subindex), (None, None))[1],
                    )
                    for entry in tx_entries
                ]
            self.pdo.set_mapping(rx_entries, tx_entries)
            self._apply_state()

    def _esi_loaded(self, document: object) -> None:
        if not self.current_position or not self.slaves:
            return
        slave = self.slaves[self.current_position - 1]
        self.current_esi_device = next(
            (
                device
                for device in document.devices
                if (device.vendor_id, device.product_code, device.revision)
                == (slave.identity.vendor_id, slave.identity.product_code, slave.identity.revision)
            ),
            None,
        )
        if self.current_esi_device is None:
            self.current_esi_device = document.devices[self.eeprom.devices.currentIndex()]
        self.coe.show_objects(self.current_esi_device.objects, "ESI fallback")

    def _process_data(self, snapshot: ProcessDataSnapshot) -> None:
        self.wkc_label.setText(f"WKC {snapshot.actual_wkc} / {snapshot.expected_wkc}")
        mark = "✓" if snapshot.actual_wkc == snapshot.expected_wkc else "!"
        self.status_metrics.setText(
            f"{mark} WKC: {snapshot.actual_wkc}/{snapshot.expected_wkc} · Timeout: {snapshot.timeout_count} · Errors: {snapshot.wkc_error_count}"
        )
        self.io.update_snapshot(snapshot)

    def _cycle(self) -> None:
        if self.controller.cycle_running:
            self.controller.stop_cycle()
        else:
            if not self.slaves or not all(
                slave.state in {EtherCatState.SAFE_OP, EtherCatState.OP} for slave in self.slaves
            ):
                QMessageBox.information(
                    self,
                    "周期通信尚未就绪",
                    "启动周期通信前，请将全部从站切换到 SAFE-OP 或 OP。\n"
                    "可选择左侧 Master，然后点击顶部 SAFE-OP。",
                )
                return
            self.controller.start_cycle(float(self.period.currentText().split()[0]))

    def _cycle_changed(self, running: bool) -> None:
        self.cycle_button.setText("■ 停止周期" if running else "▶ 启动周期")
        self.cycle_button.setObjectName("dangerButton" if running else "primaryButton")
        self.cycle_button.style().unpolish(self.cycle_button)
        self.cycle_button.style().polish(self.cycle_button)
        self.status_cycle.setText(f"Cycle: {'▶ ' + self.period.currentText() if running else '■ Stopped'}")
        self.io.set_stale(not running)
        self.io.set_cycle_running(running)
        self._apply_state()

    def _result(self, kind: str, payload: object) -> None:
        if kind == "sdo_read":
            _, index, sub, data = payload
            self.coe.show_read(index, sub, data)
        elif kind == "sdo_write":
            position, index, sub, _ = payload
            self.controller.sdo_read(position, index, sub)
        elif kind == "register_read":
            _, address, data = payload
            self.registers.show_read(address, data)
        elif kind == "object_dictionary":
            self.coe.show_objects(payload, "online SDO Info")
        elif kind == "register_plan":
            self.registers.confirm_plan(payload)
        elif kind == "register_write":
            plan, result = payload
            self.registers.show_write_result(plan, result)
        elif kind == "register_watch":
            self.registers.show_watch(payload)
        elif kind == "eeprom_read":
            self.eeprom.show_read(payload)
        elif kind == "eeprom_backup":
            self.eeprom.status.setText(f"✓ 备份完成：{payload.binary_path}\nSHA-256：{payload.sha256}")
        elif kind == "eeprom_flash":
            self.eeprom.show_flash_result(payload)
        elif kind in {"reconfig", "recover"}:
            position, result = payload
            self.status_text.setText(f"Slave {position} {kind}: {'成功' if result else '失败'}")
            self.controller.refresh_states()

    def _error(self, message: str) -> None:
        self.status_text.setText(message)
        self.log_dock.show()
        if "Npcap" in message or "wpcap" in message:
            self._show_npcap_help()
        else:
            QMessageBox.warning(self, "EtherCAT 操作失败", message)

    def _busy_changed(self, busy: bool, text: str) -> None:
        self.busy = busy
        self.status_text.setText(("⏳ " if busy else "✓ ") + text)
        self._apply_state()

    def _log(self, record: LogRecord) -> None:
        stamp = datetime.fromtimestamp(record.timestamp).strftime("%H:%M:%S.%f")[:-3]
        self.log.append(
            f"{stamp}  {record.level:<5}  {record.source:<10}  {record.event:<10}  {record.message}"
        )
        self.log_dock.setWindowTitle(f"日志 ({self.log.document().blockCount()})")
        self.log_button.setText(f"日志 {self.log.document().blockCount()}")
        if record.level == "ERROR":
            self.log_dock.show()
        if not self.pause_log.isChecked():
            self.log.moveCursor(self.log.textCursor().MoveOperation.End)

    def _copy_log(self) -> None:
        QApplication.clipboard().setText(self.log.textCursor().selectedText() or self.log.toPlainText())

    def _clear_log(self) -> None:
        self.log.clear()
        self.log_dock.setWindowTitle("日志 (0)")
        self.log_button.setText("日志 0")

    def _show_eeprom(self) -> None:
        self.stack.setCurrentIndex(2)
        self.pages.setCurrentWidget(self.eeprom)
        self.eeprom._select()

    def _apply_state(self) -> None:
        connected = self.controller.connected
        scanned = bool(self.slaves)
        running = self.controller.cycle_running
        idle = not self.busy
        self.adapter.setEnabled(not connected and not running and idle)
        self.mode.setEnabled(not connected and not running and idle)
        self.refresh_adapters.setEnabled(not connected and not running and idle)
        self.connect_button.setEnabled(bool(self.adapter.count()) and not running and idle)
        self.scan_button.setEnabled(connected and not running and idle)
        self.connect_button.setToolTip(
            "周期通信运行时请先停止" if running else "打开所选网卡" if not connected else "安全断开当前网卡"
        )
        self.scan_button.setToolTip(
            "连接网卡后扫描 EtherCAT 从站" if not connected else "重新扫描总线上的从站"
        )
        for button in self.state_buttons.values():
            button.setEnabled(scanned and not running and idle)
            button.setToolTip(
                "周期通信运行时请先安全停止" if running else f"直接请求当前操作目标进入 {button.text()}"
            )
        self.cycle_button.setEnabled(scanned and idle)
        self.cycle_button.setToolTip(
            "需要先连接并扫描从站" if not scanned else "启动后持续交换 PDO，并显示 WKC、超时和错误计数"
        )
        self.refresh_state.setEnabled(scanned and idle)
        self.next_action.setEnabled(idle and (connected or bool(self.adapter.count())))
        self.advanced_toggle.setEnabled(scanned and self.current_position > 0 and not running)
        self.reconfig.setEnabled(scanned and self.current_position > 0 and not running and idle)
        self.recover.setEnabled(scanned and self.current_position > 0 and not running and idle)
        can_eeprom = scanned and self.current_position > 0 and not running and idle
        self.eeprom.read.setEnabled(can_eeprom)
        self.eeprom.backup.setEnabled(can_eeprom)
        self.eeprom.restore.setEnabled(can_eeprom)
        self.eeprom.flash.setEnabled(can_eeprom and self.eeprom.generated is not None)
        self.period.setEnabled(not running and idle)
        self.home_action.setEnabled(bool(self.adapter.count()) and idle)
        self._update_state_buttons()
        self._update_context()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.controller.cycle_running:
            answer = QMessageBox.question(
                self,
                "停止并退出",
                "周期通信正在运行。是否安全停止并退出？",
                QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.controller.close()
        event.accept()
