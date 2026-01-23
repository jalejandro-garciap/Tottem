"""
TOTTEM POS · Rewritten AdminPinDialog
Onscreen Keypad Implementation
"""


class AdminPinDialog(QDialog):
    """Secure Admin Access with Onscreen Keypad"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(480)
        
        self.pin_value = ""
        self.max_length = 16

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(24)

        # ─── Icon ─────────────────────────────────────────────────────────
        from ui.icon_helper import get_icon_char
        
        self.icon_lbl = QLabel(get_icon_char("lock") or "🔐")
        self.icon_lbl.setObjectName("IconLabel")
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size: 48px;")

        # ─── Title & Subtitle ─────────────────────────────────────────────
        title = QLabel(i18n.t("admin_pin_prompt") or "Acceso Administrador")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px;")

        subtitle = QLabel("Ingrese su PIN de seguridad")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #64748b; font-size: 14px;")

        # ─── PIN Display (Read-only) ──────────────────────────────────────
        self.display = QLabel()
        self.display.setAlignment(Qt.AlignCenter)
        self.display.setMinimumHeight(72)
        self.display.setStyleSheet("""
            QLabel {
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 12px;
                background: #16161e;
                border: 2px solid #2a2a3a;
                border-radius: 18px;
                padding: 16px;
                color:#f8fafc;
            }
        """)
        self._update_display()

        # ─── Error Label ──────────────────────────────────────────────────
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: 600;")
        self.error_label.hide()

        # ─── Numeric Keypad ───────────────────────────────────────────────
        keypad_grid = QGridLayout()
        keypad_grid.setSpacing(10)

        # Numbers 1-9
        buttons = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
        ]
        for text, r, c in buttons:
            btn = QPushButton(text)
            btn.setObjectName("KeypadButton")
            btn.setMinimumSize(70, 70)
            btn.clicked.connect(lambda _=None, t=text: self._press_digit(t))
            keypad_grid.addWidget(btn, r, c)

        # Bottom row: C, 0, ←
        btn_clear = QPushButton("C")
        btn_clear.setObjectName("KeypadButton")
        btn_clear.setProperty("role", "danger")
        btn_clear.setMinimumSize(70, 70)
        btn_clear.clicked.connect(self._clear)
        keypad_grid.addWidget(btn_clear, 3, 0)

        btn_zero = QPushButton("0")
        btn_zero.setObjectName("KeypadButton")
        btn_zero.setMinimumSize(70, 70)
        btn_zero.clicked.connect(lambda: self._press_digit("0"))
        keypad_grid.addWidget(btn_zero, 3, 1)

        btn_back = QPushButton(get_icon_char("arrow-left") or "←")
        btn_back.setObjectName("KeypadButton")
        btn_back.setMinimumSize(70, 70)
        btn_back.clicked.connect(self._backspace)
        keypad_grid.addWidget(btn_back, 3, 2)

        # ─── Action Buttons ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(64)
        btn_cancel.clicked.connect(self.reject)
        
        btn_ok = QPushButton(f"{get_icon_char('arrow-right') or '→'}  Acceder")
        btn_ok.setMinimumHeight(64)
        btn_ok.setProperty("role", "primary")
        btn_ok.clicked.connect(self._on_ok)
        
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        # ─── Assembly ─────────────────────────────────────────────────────
        layout.addWidget(self.icon_lbl)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(self.display)
        layout.addWidget(self.error_label)
        layout.addSpacing(12)
        layout.addLayout(keypad_grid)
        layout.addSpacing(8)
        layout.addLayout(btn_row)

    def _update_display(self):
        """Update display with bullet points"""
        if self.pin_value:
            self.display.setText("• " * len(self.pin_value))
        else:
            self.display.setText("• • • •")
            self.display.setStyleSheet(self.display.styleSheet().replace("color:#f8fafc", "color:#4a4a5a"))
            return
        self.display.setStyleSheet(self.display.styleSheet().replace("color:#4a4a5a", "color:#f8fafc"))

    def _press_digit(self, digit: str):
        """Add digit to PIN"""
        if len(self.pin_value) < self.max_length:
            self.pin_value += digit
            self._update_display()
            self._reset_error_state()

    def _backspace(self):
        """Remove last digit"""
        if self.pin_value:
            self.pin_value = self.pin_value[:-1]
            self._update_display()
            self._reset_error_state()

    def _clear(self):
        """Clear all digits"""
        self.pin_value = ""
        self._update_display()
        self._reset_error_state()

    def _reset_error_state(self):
        """Reset visual error indicators"""
        self.error_label.hide()
        from ui.icon_helper import get_icon_char
        self.icon_lbl.setText(get_icon_char("lock") or "🔐")
        self.icon_lbl.setProperty("state", "")
        self.icon_lbl.style().unpolish(self.icon_lbl)
        self.icon_lbl.style().polish(self.icon_lbl)
        
        # Reset display border
        self.display.setStyleSheet("""
            QLabel {
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 12px;
                background: #16161e;
                border: 2px solid #2a2a3a;
                border-radius: 18px;
                padding: 16px;
                color:#f8fafc;
            }
        """)

    def _show_error(self):
        """Show error state visually"""
        from ui.icon_helper import get_icon_char
        
        # Change icon to error state
        self.icon_lbl.setText(get_icon_char("lock") or "🔐")
        self.icon_lbl.setProperty("state", "error")
        self.icon_lbl.style().unpolish(self.icon_lbl)
        self.icon_lbl.style().polish(self.icon_lbl)
        
        # Show error label
        self.error_label.setText("❌ PIN incorrecto. Intente nuevamente.")
        self.error_label.show()
        
        # Red border on display
        self.display.setStyleSheet("""
            QLabel {
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 12px;
                background: rgba(239, 68, 68, 0.1);
                border: 2px solid #ef4444;
                border-radius: 18px;
                padding: 16px;
                color:#f8fafc;
            }
        """)

    def _on_ok(self):
        """Validate PIN and accept or show error"""
        if not self.pin_value:
            QMessageBox.warning(self, "PIN", i18n.t("pin_required") or "Capture el PIN.")
            return
        
        if check_admin_pin(self.pin_value):
            self.accept()
        else:
            self._show_error()
            self.pin_value = ""
            self._update_display()
            QMessageBox.critical(self, "PIN", i18n.t("pin_bad") or "PIN incorrecto.")
