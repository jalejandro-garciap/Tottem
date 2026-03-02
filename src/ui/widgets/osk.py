"""
TOTTEM POS · On-Screen Keyboard
Premium Text Input Experience
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QLineEdit, QSizePolicy, QWidget, QLabel, QFrame
)
from PySide6.QtCore import Qt, QSize
from services import i18n
from ui.responsive import s

KEY_ROWS_LOWER = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    list("zxcvbnm"),
]
KEY_ROWS_UPPER = [[c.upper() for c in row] for row in KEY_ROWS_LOWER]

KEY_NUMBERS = list("1234567890")
KEY_SYMBOLS = ["@", ".", "_", "-", "+", "/", "\\", ":", ";", ",", "!", "?"]


class OnScreenKeyboard(QDialog):
    """
    Premium on-screen keyboard with elegant design.
    
    Features:
      - Toggle lower/upper with Shift
      - Toggle symbols/numbers
      - Backspace, Clear, Space, OK/Cancel
      - Optional password mode
    """

    def __init__(self, title: str = None, initial_text: str = "",
                 password_mode: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self._shift = False
        self._symbols = False

        title_text = title if title is not None else (i18n.t("keyboard_title") or "Teclado")

        root = QVBoxLayout(self)
        root.setContentsMargins(s(28), s(28), s(28), s(28))
        root.setSpacing(s(16))

        # ─── Header ───────────────────────────────────────────────────────
        header = QHBoxLayout()
        lbl = QLabel(title_text.upper())
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"""
            font-size: {s(12)}px;
            font-weight: 700;
            letter-spacing: {s(3)}px;
        """)
        header.addWidget(lbl)
        root.addLayout(header)

        # ─── Input Display ────────────────────────────────────────────────
        display_frame = QFrame()
        display_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(0, 0, 0, 0.2);
                border-radius: {s(16)}px;
            }}
        """)
        display_layout = QVBoxLayout(display_frame)
        display_layout.setContentsMargins(s(20), s(16), s(20), s(16))

        self.ed = QLineEdit(initial_text)
        if password_mode:
            self.ed.setEchoMode(QLineEdit.Password)
        self.ed.setStyleSheet(f"""
            QLineEdit {{
                font-size: {s(28)}px;
                font-weight: 600;
                background: transparent;
                border: none;
                padding: {s(8)}px 0;
            }}
        """)
        self.ed.setPlaceholderText(i18n.t("osk_placeholder"))
        display_layout.addWidget(self.ed)
        root.addWidget(display_frame)

        # ─── Key Grid ─────────────────────────────────────────────────────
        self.grid = QGridLayout()
        self.grid.setSpacing(s(8))
        root.addLayout(self.grid)

        # ─── Control Row ──────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(s(8))

        self.btn_shift = QPushButton("⇧")
        self.btn_shift.setToolTip("Shift")
        self.btn_nums = QPushButton("123")
        self.btn_space = QPushButton("━━━━━━━━")
        self.btn_space.setToolTip(i18n.t("osk_space_tooltip"))
        self.btn_bsp = QPushButton("⌫")
        self.btn_bsp.setToolTip(i18n.t("osk_backspace_tooltip"))
        from ui.icon_helper import get_icon_char
        self.btn_clear = QPushButton(get_icon_char('xmark') or "✕")
        self.btn_clear.setToolTip(i18n.t("osk_clear_tooltip"))
        self.btn_clear.setProperty("role", "danger")

        for b in (self.btn_shift, self.btn_nums, self.btn_space, self.btn_bsp, self.btn_clear):
            b.setMinimumHeight(s(56))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self.btn_space.setMinimumWidth(s(200))

        controls.addWidget(self.btn_shift)
        controls.addWidget(self.btn_nums)
        controls.addWidget(self.btn_space, 3)
        controls.addWidget(self.btn_bsp)
        controls.addWidget(self.btn_clear)
        root.addLayout(controls)

        # ─── Action Buttons ───────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(s(12))

        self.btn_cancel = QPushButton(i18n.t("osk_cancel"))
        self.btn_cancel.setMinimumHeight(s(60))

        from ui.icon_helper import get_icon_char
        self.btn_ok = QPushButton(f"{get_icon_char('arrow-right') or '→'}  {i18n.t('osk_accept')}")
        self.btn_ok.setMinimumHeight(s(60))
        self.btn_ok.setProperty("role", "primary")

        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.btn_ok)
        root.addLayout(actions)

        # ─── Connections ──────────────────────────────────────────────────
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
                btn.setMinimumSize(QSize(s(56), s(56)))
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                btn.clicked.connect(lambda _=None, ch_=ch: self._append(ch_))
                btn.setObjectName("KeypadButton")
                self.grid.addWidget(btn, r, c)

        # Update shift button style
        if self._shift:
            self.btn_shift.setProperty("role", "primary")
        else:
            self.btn_shift.setProperty("role", "")
        self.btn_shift.style().unpolish(self.btn_shift)
        self.btn_shift.style().polish(self.btn_shift)

        # Update numbers button style
        if self._symbols:
            self.btn_nums.setProperty("role", "primary")
            self.btn_nums.setText("ABC")
        else:
            self.btn_nums.setProperty("role", "")
            self.btn_nums.setText("123")
        self.btn_nums.style().unpolish(self.btn_nums)
        self.btn_nums.style().polish(self.btn_nums)

    # ─── Public API ───────────────────────────────────────────────────────
    def text(self) -> str:
        return self.ed.text()

    # ─── Internal ─────────────────────────────────────────────────────────
    def _toggle_shift(self):
        self._shift = not self._shift
        self._rebuild_keys()

    def _toggle_symbols(self):
        self._symbols = not self._symbols
        self._rebuild_keys()

    def _append(self, ch: str):
        self.ed.insert(ch)

    def _backspace(self):
        txt = self.ed.text()
        if txt:
            self.ed.setText(txt[:-1])

    def _clear(self):
        self.ed.clear()
