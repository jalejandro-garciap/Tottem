# -*- coding: utf-8 -*-
# ui/widgets/osk.py — Simple on-screen keyboard dialog for kiosk usage.
# Spanish labels for user-facing buttons; code/comments in English.

from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLineEdit, QSizePolicy, QWidget, QLabel
)
from PySide6.QtCore import Qt, QSize

KEY_ROWS_LOWER = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
KEY_ROWS_UPPER = [ [c.upper() for c in row] for row in KEY_ROWS_LOWER ]

KEY_NUMBERS = list("1234567890")
KEY_SYMBOLS = ["@", ".", "_", "-", "+", "/", "\\", ":", ";", ",", "!", "?"]

class OnScreenKeyboard(QDialog):
    """
    Modal keyboard:
      - Toggle lower/upper with Shift
      - Toggle symbols/numbers
      - Backspace, Clear, Space, OK/Cancel
      - Optional password mode (echo as Password)
    """
    def __init__(self, title: str = "Teclado", initial_text: str = "",
                 password_mode: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self._shift = False
        self._symbols = False

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Title
        top = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setObjectName("SectionTitle")
        lbl.setAlignment(Qt.AlignCenter)
        top.addWidget(lbl)
        root.addLayout(top)

        # Line edit
        self.ed = QLineEdit(initial_text)
        if password_mode:
            self.ed.setEchoMode(QLineEdit.Password)
        self.ed.setMinimumHeight(60)
        self.ed.setStyleSheet("font-size: 24px; font-weight: 600; padding: 10px;")
        root.addWidget(self.ed)

        # Key area
        self.grid = QGridLayout()
        self.grid.setSpacing(8)
        root.addLayout(self.grid)

        # Bottom actions
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.btn_shift = QPushButton("Shift")
        self.btn_nums  = QPushButton("123")
        self.btn_space = QPushButton("Espacio")
        self.btn_clear = QPushButton("Limpiar")
        self.btn_bsp   = QPushButton("←")
        self.btn_cancel= QPushButton("Cancelar")
        self.btn_ok    = QPushButton("OK")
        
        self.btn_ok.setProperty("role", "primary")
        self.btn_clear.setProperty("role", "danger")

        for b in (self.btn_shift, self.btn_nums, self.btn_space, self.btn_clear, self.btn_bsp, self.btn_cancel, self.btn_ok):
            b.setMinimumHeight(60)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        actions.addWidget(self.btn_shift)
        actions.addWidget(self.btn_nums)
        actions.addWidget(self.btn_space, 2)
        actions.addWidget(self.btn_clear)
        actions.addWidget(self.btn_bsp)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_ok)
        root.addLayout(actions)

        # Connections
        self.btn_shift.clicked.connect(self._toggle_shift)
        self.btn_nums.clicked.connect(self._toggle_symbols)
        self.btn_space.clicked.connect(lambda: self._append(" "))
        self.btn_clear.clicked.connect(self._clear)
        self.btn_bsp.clicked.connect(self._backspace)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.accept)

        self._rebuild_keys()

    def _rebuild_keys(self):
        # Clear existing buttons
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Decide layout
        if self._symbols:
            rows = [KEY_NUMBERS, KEY_SYMBOLS[:6], KEY_SYMBOLS[6:]]
        else:
            rows = KEY_ROWS_UPPER if self._shift else KEY_ROWS_LOWER

        # Build buttons
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                btn = QPushButton(ch)
                btn.setMinimumSize(QSize(60, 60))
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.clicked.connect(lambda _=None, s=ch: self._append(s))
                # Add a class/object name to apply special styles if needed
                btn.setObjectName("KeypadButton") 
                self.grid.addWidget(btn, r, c)

