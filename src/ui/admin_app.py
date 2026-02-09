import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor
from PySide6.QtCore import Qt

from ui.widgets.admin_window import AdminWindow


def run():
    # Configuración del framebuffer para Raspberry Pi OS Lite
    os.environ.setdefault("QT_QPA_PLATFORM", "linuxfb")
    os.environ.setdefault("QT_QPA_FB_FORCE_FULLSCREEN", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.input=false;qt.qpa.input.devices=false")

    app = QApplication(sys.argv)

    qss_path = Path(__file__).resolve().parent / "theme.qss"
    
    # Apply saved theme or fall back to theme.qss
    try:
        from services import themes as theme_svc
        current_theme = theme_svc.get_current_theme()
        if current_theme and current_theme != "dark":
            theme_svc.apply_theme(app, current_theme)
        elif qss_path.exists():
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    except Exception:
        if qss_path.exists():
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    app.setOverrideCursor(QCursor(Qt.BlankCursor))

    w = AdminWindow()
    w.showFullScreen()
    sys.exit(app.exec())

