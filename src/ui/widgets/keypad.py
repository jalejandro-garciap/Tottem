"""
TOTTEM POS · Numeric Keypad
Premium Touch Input Experience
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QPushButton, QLineEdit, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt


class NumKeypad(QDialog):
    """
    Premium numeric keypad with elegant design.
    Supports integers or decimals.
    
    Usage:
        dlg = NumKeypad(title="Cantidad", allow_decimal=True)
        if dlg.exec() == QDialog.Accepted:
            value = dlg.value_float()
    """

    def __init__(self, title: str = "Cantidad", allow_decimal: bool = True):
        super().__init__()
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        self.allow_decimal = bool(allow_decimal)

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        # ─── Header ───────────────────────────────────────────────────────
        title_lbl = QLabel(title.upper())
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)
        root.addWidget(title_lbl)

        # ─── Display ──────────────────────────────────────────────────────
        display_frame = QFrame()
        display_frame.setStyleSheet("""
            QFrame {
                border-radius: 18px;
            }
        """)
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(24, 20, 24, 20)

        self.edit = QLineEdit()
        self.edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit.setReadOnly(True)
        self.edit.setStyleSheet("""
            QLineEdit {
                font-size: 48px;
                font-weight: 700;
                background: transparent;
                border: none;
                padding: 8px 0;
            }
        """)
        self.edit.setPlaceholderText("0")
        display_layout.addWidget(self.edit)
        root.addWidget(display_frame)

        # ─── Keypad Grid ──────────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)

        # Number buttons 1-9
        buttons = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
        ]
        for text, r, c in buttons:
            b = QPushButton(text)
            b.setObjectName("KeypadButton")
            b.clicked.connect(lambda _=None, t=text: self._press(t))
            grid.addWidget(b, r, c)

        # Bottom row
        b_clear = QPushButton("C")
        b_clear.setObjectName("KeypadButton")
        b_clear.setProperty("role", "danger")
        b_clear.clicked.connect(lambda: self._press("C"))
        grid.addWidget(b_clear, 3, 0)

        b_zero = QPushButton("0")
        b_zero.setObjectName("KeypadButton")
        b_zero.clicked.connect(lambda: self._press("0"))
        grid.addWidget(b_zero, 3, 1)

        if self.allow_decimal:
            b_dot = QPushButton("•")
            b_dot.setObjectName("KeypadButton")
            b_dot.clicked.connect(lambda: self._press("."))
            grid.addWidget(b_dot, 3, 2)
        else:
            # Backspace button when no decimal
            b_back = QPushButton("⌫")
            b_back.setObjectName("KeypadButton")
            b_back.clicked.connect(self._backspace)
            grid.addWidget(b_back, 3, 2)

        root.addLayout(grid)

        # ─── Action Buttons ───────────────────────────────────────────────
        row = QHBoxLayout()
        row.setSpacing(12)

        cancel = QPushButton("Cancelar")
        cancel.setMinimumHeight(64)
        cancel.clicked.connect(self.reject)

        from ui.icon_helper import get_icon_char
        ok = QPushButton(f"{get_icon_char('arrow-right') or '→'}  Aceptar")
        ok.setMinimumHeight(64)
        ok.setProperty("role", "primary")
        ok.clicked.connect(self.accept)

        row.addWidget(cancel)
        row.addWidget(ok)
        root.addLayout(row)

    def _press(self, t: str):
        s = self.edit.text()
        if t == "C":
            self.edit.setText("")
            return
        if t == ".":
            if not self.allow_decimal:
                return
            if "." in s:
                return
            if not s:
                self.edit.setText("0.")
            else:
                self.edit.setText(s + ".")
            return
        # digits
        if len(s) < 12:
            self.edit.setText(s + t)

    def _backspace(self):
        s = self.edit.text()
        if s:
            self.edit.setText(s[:-1])

    def value_text(self) -> str:
        """
        Devuelve el texto tal cual fue capturado en el display.
        Útil para campos como PIN donde no se requiere convertir a número.
        """
        return (self.edit.text() or "").strip()

    def value_float(self) -> float:
        s = (self.edit.text() or "").strip()
        if not s or s == ".":
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0
