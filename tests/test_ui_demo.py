from PySide6.QtCore import Qt

from ethercat_debug_tool.controller import AppController
from ethercat_debug_tool.models import EtherCatState
from ethercat_debug_tool.ui.main_window import MainWindow


def test_demo_ui_p0_end_to_end(qtbot) -> None:
    controller = AppController()
    window = MainWindow(controller)
    qtbot.addWidget(window)
    window.show()
    try:
        assert window.windowTitle() == "EtherCAT Workbench"
        qtbot.waitUntil(lambda: window.adapter.count() == 1, timeout=2000)
        qtbot.mouseClick(window.connect_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controller.connected, timeout=2000)
        qtbot.mouseClick(window.scan_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: len(controller.slaves) == 3, timeout=2000)
        window.tree.setCurrentItem(window.tree.topLevelItem(0).child(0))
        assert "Slave 1" in window.target_label.text()
        assert window.state_buttons[EtherCatState.PRE_OP].isChecked()
        qtbot.mouseClick(window.state_buttons[EtherCatState.SAFE_OP], Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controller.slaves[0].state is EtherCatState.SAFE_OP, timeout=2000)
        assert window.state_buttons[EtherCatState.SAFE_OP].isChecked()
        window.tree.setCurrentItem(window.tree.topLevelItem(0))
        qtbot.mouseClick(window.state_buttons[EtherCatState.SAFE_OP], Qt.MouseButton.LeftButton)
        qtbot.waitUntil(
            lambda: all(slave.state is EtherCatState.SAFE_OP for slave in controller.slaves), timeout=2000
        )
        window.tree.setCurrentItem(window.tree.topLevelItem(0).child(0))
        controller.read_pdo_mapping(1)
        qtbot.waitUntil(lambda: window.pdo.rx.rowCount() == 2 and window.pdo.tx.rowCount() == 2, timeout=2000)
        qtbot.mouseClick(window.cycle_button, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: controller.cycle_running and "9 / 9" in window.wkc_label.text(), timeout=2000)
        controller.stop_cycle()
        qtbot.waitUntil(lambda: not controller.cycle_running, timeout=2000)
        assert not window.log_dock.isVisible()
    finally:
        controller.close()
