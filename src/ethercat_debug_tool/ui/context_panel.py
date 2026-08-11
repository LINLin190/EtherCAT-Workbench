from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget


class ContextPanel(QWidget):
    recommended_requested = Signal()
    refresh_requested = Signal()
    reconfig_requested = Signal()
    recover_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumWidth(265)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        target_card = QFrame()
        target_card.setObjectName("contextCard")
        target_layout = QVBoxLayout(target_card)
        target_title = QLabel("当前目标")
        target_title.setObjectName("sectionLabel")
        self.target = QLabel("尚未连接 EtherCAT 网卡")
        self.target.setWordWrap(True)
        target_layout.addWidget(target_title)
        target_layout.addWidget(self.target)

        next_title = QLabel("建议下一步")
        next_title.setObjectName("sectionLabel")
        self.recommendation = QLabel("先选择模式和网卡，然后建立连接。")
        self.recommendation.setObjectName("recommendation")
        self.recommendation.setWordWrap(True)
        self.next_action = QPushButton("连接网卡")
        self.next_action.setObjectName("primaryButton")
        self.next_action.clicked.connect(self.recommended_requested)
        self.refresh = QPushButton("↻ 刷新总线状态")
        self.refresh.setToolTip("只读：重新读取所有从站状态和 AL Status，不改变配置。")
        self.refresh.clicked.connect(self.refresh_requested)

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText("故障恢复（高级）")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        self.advanced_panel = QFrame()
        advanced_layout = QVBoxLayout(self.advanced_panel)
        advanced_layout.setContentsMargins(0, 4, 0, 0)
        warning = QLabel("仅在状态切换失败、从站掉线或重新接入时使用。正常调试无需操作。")
        warning.setWordWrap(True)
        warning.setObjectName("recommendation")
        self.reconfig = QPushButton("重新配置从站")
        self.reconfig.setToolTip("对仍可通信但配置或状态异常的从站重新执行配置。")
        self.reconfig.clicked.connect(self.reconfig_requested)
        self.recover = QPushButton("恢复丢失从站")
        self.recover.setObjectName("dangerButton")
        self.recover.setToolTip("用于网线恢复或从站重新上电后，尝试找回已丢失从站。")
        self.recover.clicked.connect(self.recover_requested)
        advanced_layout.addWidget(warning)
        advanced_layout.addWidget(self.reconfig)
        advanced_layout.addWidget(self.recover)
        self.advanced_panel.setVisible(False)

        layout.addWidget(target_card)
        layout.addWidget(next_title)
        layout.addWidget(self.recommendation)
        layout.addWidget(self.next_action)
        layout.addWidget(self.refresh)
        layout.addSpacing(8)
        layout.addWidget(self.advanced_toggle)
        layout.addWidget(self.advanced_panel)
        layout.addStretch()

    def _toggle_advanced(self, expanded: bool) -> None:
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.advanced_panel.setVisible(expanded)
