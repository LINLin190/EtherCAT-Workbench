from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from .controller import AppController
from .models import BackendMode
from .ui import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EtherCAT Workbench")
    parser.add_argument("--real", action="store_true", help="start with the real pySOEM backend")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args, qt_args = parser.parse_known_args(argv)
    app = QApplication([sys.argv[0], *qt_args])
    controller = AppController(BackendMode.REAL if args.real else BackendMode.DEMO)
    window = MainWindow(controller)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(1_000, window.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
