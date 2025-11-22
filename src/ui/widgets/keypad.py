from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QPushButton, QLineEdit, QHBoxLayout
)
from PySide6.QtCore import Qt


class NumKeypad(QDialog):
    """
    Modal numeric keypad that supports integers or decimals.
    Usage:
        dlg = NumKeypad(title="Cantidad", allow_decimal=True)
        if dlg.exec() == QDialog.Accepted:
            value = dlg.value_float()  # use this; caller clamps range if needed
    """

    def __init__(self, title: str = "Cantidad", allow_decimal: bool = True):
        super().__init__()
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setWindowTitle(title)
        self.allow_decimal = bool(allow_decimal)

        root = QVBoxLayout(self)

        self.edit = QLineEdit()
        self.edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit.setReadOnly(True)
        self.edit.setMinimumHeight(48)
        root.addWidget(self.edit)

        grid = QGridLayout()

        # First three rows: 1..9
        buttons = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
        ]
        for text, r, c in buttons:
            b = QPushButton(text)
            b.setMinimumHeight(56)
            b.setObjectName("KeypadButton")
            b.clicked.connect(lambda _=None, t=text: self._press(t))
            grid.addWidget(b, r, c)

        # Last row: C, 0, (.) if decimals enabled
        last_row = []
        last_row.append("C")
        last_row.append("0")
        if self.allow_decimal:
            last_row.append(".")

        for idx, text in enumerate(last_row):
            b = QPushButton(text)
            b.setMinimumHeight(56)
            b.setObjectName("KeypadButton")
            b.clicked.connect(lambda _=None, t=text: self._press(t))
            grid.addWidget(b, 3, idx)

        root.addLayout(grid)

        row = QHBoxLayout()
        ok = QPushButton("OK")
        ok.setMinimumHeight(48)
        ok.setProperty("role", "primary")
        ok.setObjectName("KeypadButton")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancelar")
        cancel.setMinimumHeight(48)
        cancel.setObjectName("KeypadButton")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        row.addWidget(ok)
        root.addLayout(row)

    # ---- input handling
    def _press(self, t: str):
        s = self.edit.text()
        if t == "C":
            self.edit.setText("")
            return
        if t == ".":
            if not self.allow_decimal:
                return
            if "." in s:
                return  # only one dot
            if not s:
                self.edit.setText("0.")
            else:
                self.edit.setText(s + ".")
            return
        # digits
        if len(s) < 12:
            self.edit.setText(s + t)

    # ---- value accessors
    def value_float(self) -> float:
        s = (self.edit.text() or "").strip()
        if not s or s == ".":
            return 0.0
        try:
            return float(s)
        except ValueError:
            return 0.0

