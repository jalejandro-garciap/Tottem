import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt

from ui.widgets.admin_window import AdminWindow


def run():

    os.environ["QT_QPA_PLATFORM"] = "linuxfb"

    os.environ["QT_QPA_FB_HIDPI"] = "1"
    os.environ["QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS"] = "/dev/input/event0"

    app = QApplication(sys.argv)

    qss_path = Path(__file__).resolve().parent / "theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    app.setOverrideCursor(QCursor(Qt.BlankCursor))

    w = AdminWindow()
    w.showFullScreen()
    sys.exit(app.exec())

