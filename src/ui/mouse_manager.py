"""
TOTTEM POS · Dynamic Mouse Cursor Manager
Detects USB mouse presence and toggles cursor visibility automatically.

On Linux (Raspberry Pi):
  Polls /dev/input/event* devices every 2 seconds.
  If a device with EV_REL capability (relative movement) is found, the cursor
  is shown; otherwise it is hidden.

On non-Linux systems (development):
  Cursor is always hidden (BlankCursor) to match kiosk behaviour.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# Bit position for EV_REL in the Linux input event capabilities bitmap.
_EV_REL_BIT = 2  # EV_REL = 0x02 → bit 2


def _has_mouse_linux() -> bool:
    """Check /sys/class/input for devices with EV_REL capability (mice)."""
    sys_input = Path("/sys/class/input")
    if not sys_input.is_dir():
        return False
    for entry in sys_input.iterdir():
        if not entry.name.startswith("event"):
            continue
        rel_path = entry / "device" / "capabilities" / "rel"
        if rel_path.is_file():
            try:
                val = int(rel_path.read_text().strip().split()[-1], 16)
                # Check if any relative axis is supported (typical for mice)
                if val > 0:
                    return True
            except (ValueError, IndexError, OSError):
                continue
    return False


class MouseManager(QObject):
    """Manages cursor visibility based on USB mouse presence.

    Usage::

        app = QApplication(sys.argv)
        mouse_mgr = MouseManager(app)
        # … rest of setup …
        sys.exit(app.exec())
    """

    mouse_state_changed = Signal(bool)  # True = mouse detected

    def __init__(self, app: QApplication, poll_interval_ms: int = 2000):
        super().__init__(app)
        self._app = app
        self._is_linux = platform.system() == "Linux"
        self._mouse_present: bool | None = None  # unknown initially

        # Initial check
        self._check_mouse()

        # Periodic polling
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_mouse)
        self._timer.start(poll_interval_ms)

    def _check_mouse(self) -> None:
        """Poll for mouse presence and update cursor accordingly."""
        if self._is_linux:
            detected = _has_mouse_linux()
        else:
            # On non-Linux (development), always hide cursor
            detected = False

        if detected == self._mouse_present:
            return  # no change

        self._mouse_present = detected

        # Remove any existing override cursor first
        while self._app.overrideCursor() is not None:
            self._app.restoreOverrideCursor()

        if detected:
            # Show normal arrow cursor
            pass  # no override → default cursor
        else:
            # Hide cursor completely
            self._app.setOverrideCursor(QCursor(Qt.BlankCursor))

        self.mouse_state_changed.emit(detected)

    @property
    def is_mouse_connected(self) -> bool:
        """Return True if a mouse is currently detected."""
        return bool(self._mouse_present)
