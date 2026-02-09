import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtCore import Qt
from pathlib import Path

from ui.widgets.kiosk_window import POSWindow


def run():
    # Configuración del framebuffer para Raspberry Pi OS Lite
    # Estas variables se configuran aquí como fallback si no están en el entorno
    os.environ.setdefault("QT_QPA_PLATFORM", "linuxfb")
    os.environ.setdefault("QT_QPA_FB_FORCE_FULLSCREEN", "1")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.input=false;qt.qpa.input.devices=false;qt.qpa.evdev=false;qt.qpa.evdev.touch=false")

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Load FontAwesome icons (before creating UI)
    try:
        from ui.icon_helper import load_icon_font
        if not load_icon_font():
            print("WARNING: FontAwesome font not loaded. Icons may not display correctly.")
            print("Please download fa-solid-900.ttf to src/ui/assets/fonts/")
    except Exception as e:
        print(f"WARNING: Failed to load icon font: {e}")

    qss_path = Path(__file__).resolve().parent / "theme.qss"
    
    # Apply saved theme or fall back to theme.qss
    try:
        from services import themes as theme_svc
        current_theme = theme_svc.get_current_theme()
        if current_theme and current_theme != "dark":
            # Apply custom theme
            theme_svc.apply_theme(app, current_theme)
        elif qss_path.exists():
            # Default to theme.qss for dark theme
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
    except Exception:
        # Fallback to theme.qss on any error
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

