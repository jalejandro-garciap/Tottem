import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt

from ui.widgets.admin_window import AdminWindow
from services.settings import load_config


def run():
    # Configuración del framebuffer para Raspberry Pi OS Lite
    os.environ.setdefault("QT_QPA_PLATFORM", "linuxfb")
    os.environ.setdefault("QT_QPA_FB_FORCE_FULLSCREEN", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.input=false;qt.qpa.input.devices=false")

    app = QApplication(sys.argv)

    cfg = load_config()
    theme = str(cfg.get("ui", {}).get("theme", "dark")).lower()
    qss_name = "theme_light.qss" if theme == "light" else "theme.qss"
    qss_path = Path(__file__).resolve().parent / qss_name
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    app.setOverrideCursor(QCursor(Qt.BlankCursor))

    w = AdminWindow()
    w.showFullScreen()
    sys.exit(app.exec())
