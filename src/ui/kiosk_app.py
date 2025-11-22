import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtCore import Qt
from pathlib import Path

from ui.widgets.kiosk_window import POSWindow


def run():
    os.environ["QT_QPA_PLATFORM"] = "linuxfb"
    os.environ.setdefault("QT_QPA_FB_FORCE_FULLSCREEN", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.input=false;qt.qpa.input.devices=false;qt.qpa.evdev=false;qt.qpa.evdev.touch=false")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    qss_path = Path(__file__).resolve().parent / "theme.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    app.setOverrideCursor(QCursor(Qt.BlankCursor))

    w = POSWindow()

    screen = QGuiApplication.primaryScreen()
    if screen:
        geo = screen.geometry()
        w.setGeometry(geo)
        w.setFixedSize(geo.size())
        w.move(geo.topLeft())

    w.showFullScreen()
    sys.exit(app.exec())

