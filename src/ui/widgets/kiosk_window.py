"""
TOTTEM POS · Kiosk Interface
Premium Point of Sale Experience
"""
import math
from ui.responsive import s
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QGridLayout, QListWidget, QHBoxLayout, QSizePolicy, QScrollArea,
    QMessageBox, QDialog, QLineEdit, QFrame
)
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QCursor, QGuiApplication, QFontMetrics

from services.sales import (
    get_active_products, CartItem, save_ticket,
    get_last_ticket_id, get_ticket_items
)
from services.settings import is_categories_enabled
from drivers.printer_escpos import EscposPrinter
from services import i18n
from ui.widgets.keypad import NumKeypad
from services.auth import check_admin_pin
from ui.icon_helper import get_icon_char

ROOT = Path(__file__).resolve().parents[2]


class PaymentDialog(QDialog):
    """Premium Payment Experience"""
    
    def __init__(self, total_cents: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(s(520))
        self.total = int(total_cents)
        self.received = 0
        self.payment_method = "cash"

        root = QVBoxLayout(self)
        root.setContentsMargins(s(48), s(48), s(48), s(48))
        root.setSpacing(s(32))

        # ─── Header ───────────────────────────────────────────────────────
        header = QVBoxLayout()
        header.setSpacing(s(12))
        header.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(i18n.t('charge_total') or 'TOTAL A COBRAR')
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"""
            font-size: {s(12)}px;
            font-weight: 700;
            letter-spacing: {s(3)}px;
        """)

        total_display = QLabel(f"${self._fmt(self.total)}")
        total_display.setAlignment(Qt.AlignCenter)
        total_display.setStyleSheet(f"""
            font-size: {s(56)}px;
            font-weight: 800;
            letter-spacing: -2px;
        """)

        header.addWidget(subtitle)
        header.addWidget(total_display)
        root.addLayout(header)

        # ─── Stats Display ────────────────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(0, 0, 0, 0.2);
                border-radius: {s(20)}px;
                padding: {s(20)}px;
            }}
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(s(24), s(20), s(24), s(20))
        stats_layout.setSpacing(s(40))

        # Received
        rec_box = QVBoxLayout()
        rec_box.setSpacing(6)
        rec_title = QLabel(i18n.t('received') or 'Recibido')
        rec_title.setStyleSheet(f"font-size: {s(13)}px; font-weight: 600;")
        rec_title.setAlignment(Qt.AlignCenter)
        self.lbl_received = QLabel("$0.00")
        self.lbl_received.setStyleSheet(f"""
            font-size: {s(28)}px;
            font-weight: 700;
            color: #10b981;
        """)
        self.lbl_received.setAlignment(Qt.AlignCenter)
        rec_box.addWidget(rec_title)
        rec_box.addWidget(self.lbl_received)

        # Change
        chg_box = QVBoxLayout()
        chg_box.setSpacing(6)
        chg_title = QLabel(i18n.t('change') or 'Cambio')
        chg_title.setStyleSheet(f"font-size: {s(13)}px; font-weight: 600;")
        chg_title.setAlignment(Qt.AlignCenter)
        self.lbl_change = QLabel("$0.00")
        self.lbl_change.setStyleSheet(f"""
            font-size: {s(28)}px;
            font-weight: 700;
            color: #818cf8;
        """)
        self.lbl_change.setAlignment(Qt.AlignCenter)
        chg_box.addWidget(chg_title)
        chg_box.addWidget(self.lbl_change)

        stats_layout.addLayout(rec_box)
        stats_layout.addLayout(chg_box)
        root.addWidget(stats_frame)

        # ─── Bill Buttons ─────────────────────────────────────────────────
        bills_grid = QGridLayout()
        bills_grid.setSpacing(s(12))
        bills = [20, 50, 100, 200, 500, 1000]
        for idx, val in enumerate(bills):
            btn = QPushButton(f"${val}")
            btn.setMinimumHeight(s(72))
            btn.setStyleSheet(f"""
                QPushButton {{
                    font-size: {s(20)}px;
                    font-weight: 700;
                    background: rgba(0, 0, 0, 0.1);
                    border: 1px solid palette(mid);
                    border-radius: {s(16)}px;
                }}
                QPushButton:hover {{
                    background: rgba(0, 0, 0, 0.2);
                    border-color: palette(highlight);
                }}
                QPushButton:pressed {{
                    background: rgba(0, 0, 0, 0.3);
                }}
            """)
            btn.clicked.connect(lambda _=None, v=val: self._add_bill(v))
            bills_grid.addWidget(btn, idx // 3, idx % 3)
        root.addLayout(bills_grid)

        # ─── Quick Actions ────────────────────────────────────────────────
        quick_row = QHBoxLayout()
        quick_row.setSpacing(s(12))

        btn_exact = QPushButton((get_icon_char('check') or '✓') + "  " + (i18n.t('exact') or "Exacto"))
        btn_exact.setMinimumHeight(s(64))
        btn_exact.setProperty("role", "success")
        btn_exact.clicked.connect(self._exact)

        btn_other = QPushButton((get_icon_char('keyboard') or '⌨') + "  " + (i18n.t('other_amount') or "Otro monto"))
        btn_other.setMinimumHeight(s(64))
        btn_other.clicked.connect(self._other)

        btn_card = QPushButton((
            get_icon_char('credit-card') or '💳') + "  " + (i18n.t('pay_card') or "Tarjeta"))
        btn_card.setMinimumHeight(s(64))
        btn_card.setProperty("role", "primary")
        btn_card.clicked.connect(self._card)

        quick_row.addWidget(btn_exact)
        quick_row.addWidget(btn_card)
        quick_row.addWidget(btn_other)
        root.addLayout(quick_row)

        # ─── Action Buttons ───────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(s(16))

        btn_cancel = QPushButton(i18n.t('cancel') or "Cancelar")
        btn_cancel.setMinimumHeight(s(72))
        btn_cancel.clicked.connect(self.reject)

        btn_charge = QPushButton((get_icon_char('arrow-right') or '→') + "  " + (i18n.t('charge') or "COBRAR"))
        btn_charge.setMinimumHeight(s(72))
        btn_charge.setProperty("role", "primary")
        btn_charge.setStyleSheet(f"""
            QPushButton {{
                font-size: {s(18)}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
        """)
        btn_charge.clicked.connect(self._try_accept)

        action_row.addWidget(btn_cancel, 1)
        action_row.addWidget(btn_charge, 2)
        root.addLayout(action_row)

    def _fmt(self, cents: int) -> str:
        return f"{cents/100:,.2f}"

    def _refresh(self):
        change = max(0, self.received - self.total)
        self.lbl_received.setText(f"${self._fmt(self.received)}")
        self.lbl_change.setText(f"${self._fmt(change)}")
        
        if self.received >= self.total:
            self.lbl_received.setStyleSheet(f"""
                font-size: {s(28)}px; font-weight: 700; color: #10b981;
            """)
        else:
            self.lbl_received.setStyleSheet(f"""
                font-size: {s(28)}px; font-weight: 700; color: #f59e0b;
            """)

    def _auto_accept_if_enough(self):
        if self.received >= self.total:
            self.accept()

    def _add_bill(self, pesos: int):
        self.received += pesos * 100
        self._refresh()
        self._auto_accept_if_enough()

    def _exact(self):
        self.received = self.total
        self._refresh()
        self._auto_accept_if_enough()

    def _other(self):
        dlg = NumKeypad(title=i18n.t('amount') or "Monto", allow_decimal=True)
        if dlg.exec() == QDialog.Accepted:
            val = max(0.0, dlg.value_float())
            self.received = int(round(val * 100))
            self._refresh()
            self._auto_accept_if_enough()

    def _card(self):
        self.payment_method = "card"
        self.received = self.total
        self._refresh()
        self.accept()

    def _try_accept(self):
        if self.received < self.total:
            QMessageBox.warning(self, i18n.t('charge') or "Cobro",
                                i18n.t('amount_less_total') or "El monto recibido es menor al total.")
            return
        self.accept()

    def result_values(self) -> tuple[int, int, str]:
        return self.received, max(0, self.received - self.total), self.payment_method


class AdminPinDialog(QDialog):
    """Secure Admin Access"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(s(420))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(48), s(48), s(48), s(48))
        layout.setSpacing(s(28))

        # Icon/Title
        from ui.icon_helper import get_icon_char
        icon_lbl = QLabel(get_icon_char("lock") or "🔐")
        icon_lbl.setObjectName("IconLabel")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(f"font-size: {s(48)}px;")

        title = QLabel(i18n.t("admin_pin_prompt") or "Acceso Administrador")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: {s(20)}px;")

        subtitle = QLabel(i18n.t("admin_pin_subtitle") or "Ingrese su PIN de seguridad")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"font-size: {s(14)}px;")

        self.ed_pin = QLineEdit()
        self.ed_pin.setEchoMode(QLineEdit.Password)
        self.ed_pin.setMaxLength(16)
        self.ed_pin.setMinimumHeight(s(72))
        self.ed_pin.setAlignment(Qt.AlignCenter)
        self.ed_pin.setStyleSheet(f"""
            QLineEdit {{
                font-size: {s(32)}px;
                font-weight: 700;
                letter-spacing: {s(8)}px;
                background: rgba(0, 0, 0, 0.2);
                border: 2px solid palette(mid);
                border-radius: {s(18)}px;
            }}
        """)
        self.ed_pin.setPlaceholderText("• • • •")

        keypad = QGridLayout()
        keypad.setSpacing(s(8))

        nums = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
        ]
        for txt, r, c in nums:
            b = QPushButton(txt)
            b.setMinimumHeight(s(48))
            b.setObjectName("KeypadButton")
            b.clicked.connect(lambda _=None, t=txt: self._press_digit(t))
            keypad.addWidget(b, r, c)

        btn_clear = QPushButton("C")
        btn_clear.setMinimumHeight(s(48))
        btn_clear.setProperty("role", "danger")
        btn_clear.setObjectName("KeypadButton")
        btn_clear.clicked.connect(self._clear_pin)
        keypad.addWidget(btn_clear, 3, 0)

        btn_zero = QPushButton("0")
        btn_zero.setMinimumHeight(s(48))
        btn_zero.setObjectName("KeypadButton")
        btn_zero.clicked.connect(lambda _=None: self._press_digit("0"))
        keypad.addWidget(btn_zero, 3, 1)

        btn_back = QPushButton("⌫")
        btn_back.setMinimumHeight(s(48))
        btn_back.setObjectName("KeypadButton")
        btn_back.clicked.connect(self._backspace_pin)
        keypad.addWidget(btn_back, 3, 2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(s(16))
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(s(64))
        btn_ok = QPushButton(f"→  {i18n.t('admin_access') or 'Acceder'}")
        btn_ok.setMinimumHeight(s(64))
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout.addWidget(icon_lbl)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(8)
        layout.addWidget(self.ed_pin)
        layout.addSpacing(8)
        layout.addLayout(keypad)
        layout.addSpacing(8)
        layout.addLayout(btn_row)

        self.ed_pin.setFocus()

    def _press_digit(self, digit: str):
        """Agrega un dígito al PIN respetando la longitud máxima."""
        self.ed_pin.insert(digit)

    def _backspace_pin(self):
        """Elimina el último dígito capturado."""
        self.ed_pin.backspace()

    def _clear_pin(self):
        """Limpia completamente el PIN capturado."""
        self.ed_pin.clear()

    def _on_ok(self):
        pin = self.ed_pin.text() or ""
        if not pin:
            QMessageBox.warning(self, i18n.t("admin_pin_title") or "PIN", i18n.t("pin_required") or "Capture el PIN.")
            return
        if check_admin_pin(pin):
            self.accept()
        else:
            self.ed_pin.clear()
            self.ed_pin.setStyleSheet(f"""
                QLineEdit {{
                    font-size: {s(32)}px;
                    font-weight: 700;
                    letter-spacing: {s(8)}px;
                    background: rgba(239, 68, 68, 0.1);
                    border: 2px solid palette(highlight);
                    border-radius: {s(18)}px;
                }}
            """)
            QMessageBox.critical(self, i18n.t("admin_pin_title") or "PIN", i18n.t("pin_bad") or "PIN incorrecto.")


class QtyModeDialog(QDialog):
    """Dialog to choose between quantity or amount input."""
    
    MODE_QUANTITY = "qty"
    MODE_AMOUNT = "amount"
    
    def __init__(self, product_name: str, unit: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(s(400))
        self.selected_mode = None
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(s(32), s(32), s(32), s(32))
        layout.setSpacing(s(20))
        
        # Title
        title = QLabel(i18n.t("qty_mode_title") or "¿Cómo desea agregar?")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"font-size: {s(18)}px; font-weight: 700;")
        layout.addWidget(title)
        
        # Product name
        prod_lbl = QLabel(product_name)
        prod_lbl.setAlignment(Qt.AlignCenter)
        prod_lbl.setStyleSheet(f"font-size: {s(14)}px;")
        prod_lbl.setWordWrap(True)
        layout.addWidget(prod_lbl)
        
        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(s(16))
        
        # Quantity button
        btn_qty = QPushButton(f"#  {i18n.t('qty_mode_quantity') or 'Cantidad'}\n({unit})")
        btn_qty.setMinimumHeight(s(90))
        btn_qty.setStyleSheet(f"""
            QPushButton {{
                font-size: {s(16)}px;
                font-weight: 600;
                background: rgba(0, 0, 0, 0.1);
                border: 2px solid palette(mid);
                border-radius: {s(16)}px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.2);
                border-color: palette(highlight);
            }}
            QPushButton:pressed {{
                background: #2a2a3a;
            }}
        """)
        btn_qty.clicked.connect(self._select_qty)
        btn_row.addWidget(btn_qty)
        
        # Amount button
        btn_amt = QPushButton(f"$  {i18n.t('qty_mode_amount') or 'Monto'}\n{i18n.t('qty_mode_amount_currency') or '(pesos)'}")
        btn_amt.setMinimumHeight(s(90))
        btn_amt.setStyleSheet(f"""
            QPushButton {{
                font-size: {s(16)}px;
                font-weight: 600;
                background: rgba(0, 0, 0, 0.1);
                border: 2px solid palette(mid);
                border-radius: {s(16)}px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.2);
                border-color: palette(highlight);
            }}
            QPushButton:pressed {{
                background: #2a2a3a;
            }}
        """)
        btn_amt.clicked.connect(self._select_amount)
        btn_row.addWidget(btn_amt)
        
        layout.addLayout(btn_row)
        
        # Cancel button
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(s(56))
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)
    
    def _select_qty(self):
        self.selected_mode = self.MODE_QUANTITY
        self.accept()
    
    def _select_amount(self):
        self.selected_mode = self.MODE_AMOUNT
        self.accept()


class POSWindow(QMainWindow):
    """
    Premium Point of Sale Interface
    Designed for speed, elegance, and touch-first interaction
    """
    
    def __init__(self):
        super().__init__()
        self._admin_win = None
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowTitle(i18n.t("title"))

        # ─── Main Container ───────────────────────────────────────────────
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(container)
        root.setContentsMargins(s(16), s(16), s(16), s(16))
        root.setSpacing(s(16))

        # ═══════════════════════════════════════════════════════════════════
        # LEFT PANEL - Products Grid
        # ═══════════════════════════════════════════════════════════════════
        self.products_area = QScrollArea()
        self.products_area.setFrameShape(QScrollArea.NoFrame)
        self.products_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.products_area.setWidgetResizable(True)
        self.products_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        products_panel = QWidget()
        products_panel.setObjectName("GridPanel")
        self.grid_wrap = QVBoxLayout(products_panel)
        self.grid_wrap.setContentsMargins(s(24), s(24), s(24), s(24))
        self.grid_wrap.setSpacing(s(20))

        # Header
        head = QHBoxLayout()
        head.setSpacing(s(16))

        self.btn_back = QPushButton("←  " + (i18n.t("back") or "Atrás"))
        self.btn_back.setMinimumHeight(s(52))
        self.btn_back.setProperty("role", "ghost")
        self.btn_back.clicked.connect(self._back_to_categories)

        self.lbl_grid_title = QLabel(i18n.t("categories") or "Categorías")
        self.lbl_grid_title.setObjectName("SectionTitle")

        head.addWidget(self.btn_back)
        head.addStretch(1)
        head.addWidget(self.lbl_grid_title)
        head.addStretch(10)
        self.grid_wrap.addLayout(head)

        # Products Grid
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(s(14))
        self.grid_wrap.addLayout(self.grid, 1)

        self.products_area.setWidget(products_panel)

        # ═══════════════════════════════════════════════════════════════════
        # RIGHT PANEL - Cart
        # ═══════════════════════════════════════════════════════════════════
        self.right_wrap = QWidget()
        self.right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.right_wrap.setObjectName("CartPanel")
        right = QVBoxLayout(self.right_wrap)
        right.setContentsMargins(s(24), s(24), s(24), s(24))
        right.setSpacing(s(16))

        # ─── Top Bar ──────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, s(12))
        top_bar.setSpacing(s(12))

        self.title_lbl = QLabel(i18n.t("cart") or "Carrito")
        self.title_lbl.setObjectName("SectionTitle")

        self.lang_btn = QPushButton(i18n.lang_switch_label())
        self.lang_btn.setMinimumSize(s(56), s(48))
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)

        self.btn_reprint = QPushButton(get_icon_char('print') or '🖨')
        self.btn_reprint.setMinimumSize(s(56), s(48))
        self.btn_reprint.setProperty("role", "ghost")
        self.btn_reprint.setToolTip(i18n.t("reprint") or "Reimprimir")
        self.btn_reprint.clicked.connect(self._reprint_last)

        self.btn_admin = QPushButton(get_icon_char('gear') or '⚙')
        self.btn_admin.setMinimumSize(s(56), s(48))
        self.btn_admin.setProperty("role", "ghost")
        self.btn_admin.setToolTip(i18n.t("admin") or "Admin")
        self.btn_admin.clicked.connect(self._go_admin)

        top_bar.addWidget(self.title_lbl)
        top_bar.addStretch(1)
        top_bar.addWidget(self.btn_reprint)
        top_bar.addWidget(self.btn_admin)
        top_bar.addWidget(self.lang_btn)

        # ─── Cart List ────────────────────────────────────────────────────
        self.list = QListWidget()
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list.setSpacing(4)

        # ─── Cart Controls ────────────────────────────────────────────────
        ctrls = QHBoxLayout()
        ctrls.setSpacing(s(10))

        ctrl_buttons = [
            ("-", None, self._dec_qty),
            ("+", None, self._inc_qty),
            ("#", None, self._set_qty),
            (get_icon_char('xmark') or "✕", "danger", self._remove_item),
            (i18n.t("clear_cart") or "Vaciar", "danger", self._clear_cart),
        ]

        for text, role, callback in ctrl_buttons:
            btn = QPushButton(text)
            btn.setMinimumHeight(s(56))
            if len(text) == 1:
                btn.setStyleSheet(f"font-size: {s(22)}px; font-weight: 700;")
            if role:
                btn.setProperty("role", role)
            btn.clicked.connect(callback)
            ctrls.addWidget(btn)
            
            # Store references
            if text == "−":
                self.btn_minus = btn
            elif text == "+":
                self.btn_plus = btn
            elif text == "#":
                self.btn_qty = btn
            elif text == get_icon_char('xmark') or text == "✕":
                self.btn_remove = btn
            else:
                self.btn_clear = btn

        # ─── Total Display ────────────────────────────────────────────────
        total_frame = QFrame()
        total_frame.setStyleSheet(f"""
            QFrame {{
                border-radius: {s(18)}px;
                padding: {s(16)}px;
            }}
        """)
        total_layout = QVBoxLayout(total_frame)
        total_layout.setContentsMargins(s(20), s(16), s(20), s(16))
        total_layout.setSpacing(s(4))

        total_label_title = QLabel("TOTAL")
        total_label_title.setStyleSheet(f"""
            font-size: {s(12)}px;
            font-weight: 700;
            letter-spacing: {s(2)}px;
        """)
        total_label_title.setAlignment(Qt.AlignRight)

        self.total_label = QLabel("$0.00")
        self.total_label.setObjectName("TotalLabel")
        self.total_label.setAlignment(Qt.AlignRight)

        total_layout.addWidget(total_label_title)
        total_layout.addWidget(self.total_label)

        # ─── Charge Button ────────────────────────────────────────────────
        self.btn_charge = QPushButton("→  " + (i18n.t("pay_print") or "COBRAR"))
        self.btn_charge.setMinimumHeight(s(80))
        self.btn_charge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_charge.setProperty("role", "primary")
        self.btn_charge.setStyleSheet(f"""
            QPushButton {{
                font-size: {s(20)}px;
                font-weight: 700;
                letter-spacing: 1px;
            }}
        """)
        self.btn_charge.clicked.connect(self.charge)

        # ─── Assemble Right Panel ─────────────────────────────────────────
        right.addLayout(top_bar)
        right.addWidget(self.list, 1)
        right.addLayout(ctrls)
        right.addWidget(total_frame)
        right.addWidget(self.btn_charge)

        # ═══════════════════════════════════════════════════════════════════
        # DATA INITIALIZATION
        # ═══════════════════════════════════════════════════════════════════
        self.products = get_active_products()
        self.prod_meta = {}
        for p in self.products:
            key = ("id", p["id"]) if p.get("id") is not None else ("name", p.get("name", ""))
            self.prod_meta[key] = {
                "allow_decimal": bool(p.get("allow_decimal", 0)),
                "unit": (p.get("unit") or "pz").strip()
            }

        self.categories_enabled = is_categories_enabled()
        self.categories = self._extract_categories(self.products)
        self.current_category: str | None = None
        self._current_cols = 0
        self._current_rows = 0

        self._populate_grid()

        # Layout assembly
        root.addWidget(self.products_area, 3)
        root.addWidget(self.right_wrap, 2)

        self.setCentralWidget(container)

        self.cart: list[CartItem] = []
        self.printer = EscposPrinter()
        self._reprint_in_progress = False

        self.installEventFilter(self)
        self._refresh_total()

    # ═══════════════════════════════════════════════════════════════════════
    # GRID & CATEGORIES
    # ═══════════════════════════════════════════════════════════════════════
    def _extract_categories(self, items: list[dict]) -> list[str]:
        cats = []
        for p in items:
            c = (p.get("category") or "General").strip() or "General"
            if c not in cats:
                cats.append(c)
        cats.sort(key=lambda s: s.lower())
        return cats or ["General"]

    def _target_right_min_width(self, total_width: int) -> int:
        if total_width <= 800:
            return 280
        if total_width <= 1024:
            return 340
        if total_width <= 1280:
            return 400
        return 460

    def _target_button_min_size(self, avail_width: int) -> QSize:
        if avail_width <= 500:
            return QSize(130, 100)
        if avail_width <= 800:
            return QSize(150, 110)
        if avail_width <= 1200:
            return QSize(170, 120)
        return QSize(190, 130)

    def _target_category_button_min_size(self, avail_width: int) -> QSize:
        base = self._target_button_min_size(avail_width)
        return QSize(int(base.width() * 1.40), int(base.height()))

    def _calc_cols(self, avail_width: int, min_btn_w: int, spacing: int, margins: int) -> int:
        usable = max(0, avail_width - 2 * margins)
        cols = max(2, (usable + spacing) // (min_btn_w + spacing))
        if avail_width > 1600:
            return min(cols, 8)
        return min(cols, 6)

    def _elide_two_lines(self, text: str, fm: QFontMetrics, width: int, max_lines: int = 2) -> str:
        words = text.split()
        lines = []
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if fm.horizontalAdvance(test) <= width:
                cur = test
            else:
                lines.append(cur)
                cur = w
                if len(lines) == max_lines - 1:
                    break
        if cur:
            lines.append(cur)
        if lines:
            lines[-1] = fm.elidedText(lines[-1], Qt.ElideRight, width)
        return "\n".join(lines[:max_lines])

    def _available_grid_width(self) -> int:
        """Calcula el ancho disponible para el grid de productos.
        
        Resta:
        - Ancho del panel derecho (Total/Cart)
        - Márgenes del contenedor raíz (16px × 2 = 32px)
        - Spacing entre paneles (16px)
        """
        viewport = self.products_area.viewport()
        viewport_width = viewport.width() if viewport else 0
        if viewport_width > 0:
            return viewport_width

        screen = QGuiApplication.primaryScreen()
        total_w = screen.geometry().width() if screen else self.width()
        right_min = self._target_right_min_width(total_w)
        self.right_wrap.setMinimumWidth(right_min)

        container_margins = 16 * 2  # Left + Right margins del contenedor principal
        panel_spacing = 16           # Spacing entre grid panel y cart panel

        available = total_w - right_min - container_margins - panel_spacing
        return max(0, available)

    def _make_category_button(self, name: str, btn_min: QSize) -> QPushButton:
        btn = QPushButton(name)
        btn.setObjectName("CategoryButton")
        btn.setMinimumSize(btn_min)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.clicked.connect(lambda _=None, cat=name: self._open_category(cat))
        return btn

    def _make_product_button(self, p: dict, btn_min: QSize, est_width: int) -> QPushButton:
        from ui.icon_helper import get_icon_char
        
        btn = QPushButton()
        btn.setObjectName("ProductButton")
        btn.setMinimumSize(btn_min)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        fm = btn.fontMetrics()
        name = self._elide_two_lines(p.get("name", ""), fm, est_width, max_lines=2)
        price = "${:,.2f}".format(p.get("price", 0) / 100.0)
        unit = (p.get("unit") or "pz").strip()
        
        # Icon rendering logic: icon + text OR text-only
        icon_name = (p.get("icon") or "").strip()
        icon_char = get_icon_char(icon_name) if icon_name else ""
        
        if icon_char:
            # With icon: show icon on first line, then name, price/unit
            btn.setText(f"{icon_char}\n{name}\n{price} / {unit}")
        else:
            # Without icon: show name, price/unit (original behavior)
            btn.setText(f"{name}\n{price} / {unit}")
        
        # Apply optional card color
        card_color = (p.get("card_color") or "").strip()
        if card_color:
            from PySide6.QtGui import QColor
            bg = QColor(card_color)
            # Calculate luminance to pick readable text color
            lum = 0.299 * bg.redF() + 0.587 * bg.greenF() + 0.114 * bg.blueF()
            text_color = "#ffffff" if lum < 0.55 else "#1a1a2e"
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {card_color};
                    color: {text_color};
                    border: 2px solid rgba(255,255,255,0.15);
                }}
                QPushButton:hover {{
                    background: {bg.lighter(115).name()};
                    border-color: rgba(255,255,255,0.3);
                }}
                QPushButton:pressed {{
                    background: {bg.darker(115).name()};
                }}
            """)
        
        btn.clicked.connect(lambda _=None, prod=p: self.add_item(prod))
        return btn

    def _populate_grid(self):
        self.categories_enabled = is_categories_enabled()

        for row in range(50):
            self.grid.setRowStretch(row, 0)
            self.grid.setRowMinimumHeight(row, 0)

        for col in range(50):
            self.grid.setColumnStretch(col, 0)
            self.grid.setColumnMinimumWidth(col, 0)

        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        avail_w = self._available_grid_width()
        spacing = self.grid.spacing()
        margins = self.grid_wrap.contentsMargins().left()

        def _layout_items(items, is_category=False):
            num_items = len(items)
            base_min = self._target_category_button_min_size(avail_w) if is_category else self._target_button_min_size(avail_w)
            
            self._base_cols = self._calc_cols(avail_w, base_min.width(), spacing, margins)
            
            scale_w = 1.0
            scale_h = 1.0
            if num_items <= 3:
                scale_w = 1.6
                scale_h = 2.2
            elif num_items <= 6:
                scale_w = 1.3
                scale_h = 1.8

            adj_w = int(base_min.width() * scale_w)
            adj_h = int(base_min.height() * scale_h)
            adj_size = QSize(adj_w, adj_h)
            
            grid_cols = self._calc_cols(avail_w, adj_w, spacing, margins)
            grid_cols = max(1, grid_cols)
            if num_items > 0 and num_items < grid_cols:
                grid_cols = num_items
            
            self._current_cols = grid_cols
            
            # Left and Right Stretches for horizontal centering
            self.grid.setColumnStretch(0, 1)
            self.grid.setColumnStretch(grid_cols + 1, 1)
            
            rows = math.ceil(num_items / grid_cols) if grid_cols > 0 else 0
            
            # Top and Bottom Stretches for vertical centering
            if num_items <= 6:
                # Bottom stretch is larger to compensate for the header above the grid
                self.grid.setRowStretch(0, 1)
                self.grid.setRowStretch(rows + 1, 2)
            else:
                # Normal top-alignment for many items
                self.grid.setRowStretch(0, 0)
                self.grid.setRowStretch(rows + 1, 1)
            
            self._current_rows = rows

            est_text_w = max(60, adj_w - 24)

            for idx, item in enumerate(items):
                r_idx = idx // grid_cols
                c_idx = idx % grid_cols
                
                if is_category:
                    btn = self._make_category_button(item, adj_size)
                else:
                    btn = self._make_product_button(item, adj_size, est_text_w)
                
                # Set fixed size or tightly constrained max size so they don't stretch uglily
                btn.setMinimumSize(adj_size)
                btn.setMaximumSize(QSize(int(adj_w * 1.05), int(adj_h * 1.05)))
                
                self.grid.addWidget(btn, r_idx + 1, c_idx + 1, alignment=Qt.AlignCenter)

        if not self.categories_enabled:
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("products") or "Productos")
            _layout_items(self.products, is_category=False)
            return

        if self.current_category is None:
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("categories") or "Categorías")
            _layout_items(self.categories, is_category=True)
        else:
            self.btn_back.setVisible(True)
            self.lbl_grid_title.setText(self.current_category)
            prods = [p for p in self.products if (p.get("category") or "General") == self.current_category]
            _layout_items(prods, is_category=False)

    def _open_category(self, name: str):
        if not self.categories_enabled:
            return
        self.current_category = name
        self._populate_grid()

    def _back_to_categories(self):
        if not self.categories_enabled:
            return
        self.current_category = None
        self._populate_grid()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Show, QEvent.Resize):
            avail_w = self._available_grid_width()
            if self.categories_enabled and self.current_category is None:
                min_size = self._target_category_button_min_size(avail_w)
            else:
                min_size = self._target_button_min_size(avail_w)
            margins = self.grid_wrap.contentsMargins().left() if hasattr(self, 'grid_wrap') else 0
            new_cols = self._calc_cols(avail_w, min_size.width(), self.grid.spacing(), margins)
            if new_cols != getattr(self, '_base_cols', -1):
                self._populate_grid()
        return super().eventFilter(obj, event)

    # ═══════════════════════════════════════════════════════════════════════
    # CART OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════
    def _fmt_qty(self, q: float) -> str:
        if abs(q - round(q)) < 1e-6:
            return str(int(round(q)))
        s = f"{q:.3f}".rstrip("0").rstrip(".")
        return s or "0"

    def _format_row(self, it: CartItem) -> str:
        subtotal = round(it.price * it.qty) / 100.0
        return f"{it.name}  ×{self._fmt_qty(it.qty)} {it.unit or 'pz'}    ${subtotal:,.2f}"

    def _refresh_list_row(self, idx: int):
        if 0 <= idx < len(self.cart) and self.list.item(idx):
            self.list.item(idx).setText(self._format_row(self.cart[idx]))

    def _rebuild_list(self):
        self.list.clear()
        for it in self.cart:
            self.list.addItem(self._format_row(it))

    def _find_cart_index_by_product(self, product_id, name: str) -> int:
        if product_id is not None:
            for i, it in enumerate(self.cart):
                if it.product_id == product_id:
                    return i
        for i, it in enumerate(self.cart):
            if (it.product_id is None) and (it.name == name):
                return i
        return -1

    def _selected_index(self) -> int:
        idx = self.list.currentRow()
        if (idx is None or idx < 0) and self.list.count() > 0:
            last = self.list.count() - 1
            self.list.setCurrentRow(last)
            return last
        return int(idx) if idx is not None else -1

    def add_item(self, p: dict):
        prod_id = p.get("id")
        name = p.get("name", "")
        price = int(p.get("price", 0))
        unit = (p.get("unit") or "pz").strip()
        idx = self._find_cart_index_by_product(prod_id, name)
        if idx >= 0:
            self.cart[idx].qty += 1.0
            self._refresh_list_row(idx)
            self.list.setCurrentRow(idx)
        else:
            it = CartItem(prod_id, name, price, 1.0, unit)
            self.cart.append(it)
            self.list.addItem(self._format_row(it))
            self.list.setCurrentRow(self.list.count() - 1)
        self._refresh_total()

    def _inc_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart):
            return
        q = self.cart[idx].qty
        self.cart[idx].qty = math.floor(q) + 1.0
        self._refresh_list_row(idx)
        self._refresh_total()

    def _dec_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart):
            return
        q = self.cart[idx].qty
        self.cart[idx].qty = max(1.0, math.ceil(q) - 1.0)
        self._refresh_list_row(idx)
        self._refresh_total()

    def _set_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart):
            return
        it = self.cart[idx]
        meta = self.prod_meta.get(("id", it.product_id), self.prod_meta.get(("name", it.name), {}))
        allow_decimal = bool(meta.get("allow_decimal", False))
        unit = meta.get("unit", "pz") or "pz"
        
        if allow_decimal:
            # Show selection dialog for decimal products
            mode_dlg = QtyModeDialog(it.name, unit, self)
            if mode_dlg.exec() != QDialog.Accepted:
                return
            
            if mode_dlg.selected_mode == QtyModeDialog.MODE_AMOUNT:
                # Input by amount
                self._set_qty_by_amount(idx, it)
                return
        
        # Default: input by quantity
        dlg = NumKeypad(title=i18n.t("quantity") or "Cantidad", allow_decimal=allow_decimal)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.value_float()
            if allow_decimal:
                q = max(0.001, min(9999.0, q))
            else:
                q = max(1.0, float(int(round(q or 0.0)) or 1))
            self.cart[idx].qty = q
            self._refresh_list_row(idx)
            self._refresh_total()
    
    def _set_qty_by_amount(self, idx: int, item: CartItem):
        """Set quantity by entering a dollar amount."""
        if item.price <= 0:
            QMessageBox.warning(self, i18n.t("error") or "Error", 
                                i18n.t("error_zero_price") or "El producto tiene precio cero.")
            return
        
        # Get amount in dollars
        dlg = NumKeypad(title=i18n.t("input_amount") or "Monto ($)", allow_decimal=True)
        if dlg.exec() == QDialog.Accepted:
            amount = dlg.value_float()
            if amount <= 0:
                return
            # Calculate quantity: amount_cents / unit_price
            amount_cents = int(round(amount * 100))
            qty = amount_cents / item.price
            qty = max(0.001, min(9999.0, qty))
            self.cart[idx].qty = qty
            self._refresh_list_row(idx)
            self._refresh_total()

    def _remove_item(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart):
            return
        self.cart.pop(idx)
        self.list.takeItem(idx)
        self._refresh_total()

    def _clear_cart(self):
        if not self.cart:
            return
        if QMessageBox.question(self, i18n.t("cart") or "Carrito", i18n.t("confirm_clear") or "¿Vaciar carrito?") == QMessageBox.Yes:
            self.cart.clear()
            self.list.clear()
            self._refresh_total()

    def _total_amount(self) -> float:
        cents = sum(round(i.price * i.qty) for i in self.cart)
        return cents / 100.0

    def _refresh_total(self):
        total = self._total_amount()
        self.total_label.setText(f"${total:,.2f}")

    # ═══════════════════════════════════════════════════════════════════════
    # CHECKOUT
    # ═══════════════════════════════════════════════════════════════════════
    def charge(self):
        """Procesar pago y guardar ticket.
        
        Valida que exista un turno activo antes de permitir la venta.
        """
        if not self.cart:
            return
        
        from services.shifts import current_shift
        sh = current_shift()
        if not sh:
            QMessageBox.critical(
                self,
                i18n.t("no_active_shift_title") or "Sin Turno Activo",
                i18n.t("no_active_shift_msg") or "No hay un turno abierto.\n\n"
                "Debe abrir un turno desde el panel de administracion "
                "antes de realizar ventas."
            )
            return
        
        total_cents = int(round(sum(round(i.price * i.qty) for i in self.cart)))
        dlg = PaymentDialog(total_cents, self)
        if dlg.exec() != QDialog.Accepted:
            return
        paid_cents, change_cents, payment_method = dlg.result_values()

        ticket_id = save_ticket(
            self.cart, shift_id=sh["id"],
            paid_cents=paid_cents, change_cents=change_cents,
            payment_method=payment_method
        )
        
        try:
            from services.receipts import render_ticket
            from services.sales import get_ticket_details
            td = get_ticket_details(ticket_id)
            if td:
                text = render_ticket(
                    td["items"],
                    ticket_number=td["id"],
                    timestamp=td["ts"],
                    served_by=td.get("served_by", ""),
                    paid_cents=td.get("paid", 0),
                    change_cents=td.get("change_amount", 0),
                    payment_method=td.get("payment_method", "cash")
                )
            else:
                text = render_ticket(
                    self.cart, paid_cents=paid_cents,
                    change_cents=change_cents,
                    payment_method=payment_method
                )

            if payment_method != "card":
                # Combined print + drawer open in a single USB session
                # The drawer opens even if print fails (e.g. paper out)
                try:
                    self.printer.print_and_open_drawer(text)
                except Exception as e:
                    print("Print+Drawer error:", e)
                    # Fallback: try each operation separately
                    try:
                        self.printer.print_text(text)
                    except Exception as e2:
                        print("Print fallback error:", e2)
                    # Always try to open drawer, even if print failed
                    try:
                        self.printer.open_drawer()
                    except Exception as e3:
                        print("Drawer fallback error:", e3)
            else:
                self.printer.print_text(text)
        except Exception as e:
            print("Print error:", e)

        self.cart.clear()
        self.list.clear()
        self._refresh_total()

    def _reprint_last(self):
        if self._reprint_in_progress:
            return
        tid = get_last_ticket_id()
        if not tid:
            QMessageBox.information(self, "Ticket", i18n.t("no_last_ticket") or "No hay tickets previos.")
            return
        self._reprint_in_progress = True
        self.btn_reprint.setEnabled(False)
        try:
            from services.receipts import render_ticket
            from services.sales import get_ticket_details
            td = get_ticket_details(tid)
            if td:
                text = render_ticket(
                    td["items"],
                    ticket_number=td["id"],
                    timestamp=td["ts"],
                    served_by=td.get("served_by", ""),
                    paid_cents=td.get("paid", 0),
                    change_cents=td.get("change_amount", 0),
                    payment_method=td.get("payment_method", "cash")
                )
            else:
                items = get_ticket_items(tid)
                text = render_ticket(items)
            self.printer.print_text(text)
        except Exception as e:
            print("Reprint error:", e)
            QMessageBox.critical(self, "Ticket", f"{i18n.t('reprint_error') or 'No se pudo reimprimir.'}\n{e}")
        finally:
            self.btn_reprint.setEnabled(True)
            self._reprint_in_progress = False

    def _go_admin(self):
        dlg = AdminPinDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        from ui.widgets.admin_window import AdminWindow
        from PySide6.QtCore import QTimer

        # Create and show admin window first to avoid white flash
        try:
            self._admin_win = AdminWindow()
            self._admin_win.showFullScreen()
        except Exception as e:
            QMessageBox.critical(self, "Admin", f"Error al iniciar administrador: {e}")
            print(f"AdminWindow Error: {e}")
            return
        
        # Hide kiosk after a small delay to ensure admin is rendered
        QTimer.singleShot(100, self.hide)

        def _back_to_kiosk():
            self._admin_win = None
            self._reload_products()
            self.showFullScreen()

        self._admin_win.destroyed.connect(lambda _obj=None: _back_to_kiosk())

    def _reload_products(self):
        """Reload products and categories from DB and refresh grid."""
        self.products = get_active_products()
        self.prod_meta.clear()
        for p in self.products:
            key = ("id", p["id"]) if p.get("id") is not None else ("name", p.get("name", ""))
            self.prod_meta[key] = {
                "allow_decimal": bool(p.get("allow_decimal", 0)),
                "unit": (p.get("unit") or "pz").strip()
            }
        
        self.categories_enabled = is_categories_enabled()
        self.categories = self._extract_categories(self.products)
        if self.current_category and self.current_category not in self.categories:
            self.current_category = None
            
        self._populate_grid()

    # ═══════════════════════════════════════════════════════════════════════
    # LANGUAGE
    # ═══════════════════════════════════════════════════════════════════════
    def _toggle_lang(self):
        i18n.toggle()
        self.setWindowTitle(i18n.t("title"))
        self.title_lbl.setText(i18n.t("cart"))
        self.lang_btn.setText(i18n.lang_switch_label())
        self.btn_reprint.setToolTip(i18n.t("reprint") or "Reimprimir")
        self.btn_remove.setToolTip(i18n.t("delete") or "Eliminar")
        self.btn_clear.setText(i18n.t("clear_cart") or "Vaciar")
        self.btn_charge.setText("→  " + (i18n.t("pay_print") or "COBRAR"))
        self._refresh_total()
        self.btn_back.setText("←  " + (i18n.t("back") or "Atrás"))
        if self.categories_enabled:
            self.lbl_grid_title.setText(i18n.t("categories") if self.current_category is None else self.current_category)
        else:
            self.lbl_grid_title.setText(i18n.t("products") or "Productos")
        self._populate_grid()
        self._rebuild_list()
