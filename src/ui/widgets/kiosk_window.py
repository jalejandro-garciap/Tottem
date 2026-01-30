"""
TOTTEM POS · Kiosk Interface
Premium Point of Sale Experience
"""
import subprocess
import sys
import os
import math
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QGridLayout, QListWidget, QHBoxLayout, QSizePolicy, QScrollArea,
    QMessageBox, QDialog, QLineEdit, QApplication, QStyle, QFrame,
    QListWidgetItem
)
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QCursor, QGuiApplication, QFontMetrics, QIcon, QFont

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
        self.setMinimumWidth(520)
        self.total = int(total_cents)
        self.received = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 48, 48, 48)
        root.setSpacing(32)

        # ─── Header ───────────────────────────────────────────────────────
        header = QVBoxLayout()
        header.setSpacing(12)
        header.setAlignment(Qt.AlignCenter)

        subtitle = QLabel(i18n.t('charge_total') or 'TOTAL A COBRAR')
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
            color: #64748b;
        """)

        total_display = QLabel(f"${self._fmt(self.total)}")
        total_display.setAlignment(Qt.AlignCenter)
        total_display.setStyleSheet("""
            font-size: 56px;
            font-weight: 800;
            color: #f8fafc;
            letter-spacing: -2px;
        """)

        header.addWidget(subtitle)
        header.addWidget(total_display)
        root.addLayout(header)

        # ─── Stats Display ────────────────────────────────────────────────
        stats_frame = QFrame()
        stats_frame.setStyleSheet("""
            QFrame {
                background: #16161e;
                border-radius: 20px;
                padding: 20px;
            }
        """)
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(24, 20, 24, 20)
        stats_layout.setSpacing(40)

        # Received
        rec_box = QVBoxLayout()
        rec_box.setSpacing(6)
        rec_title = QLabel(i18n.t('received') or 'Recibido')
        rec_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 600;")
        rec_title.setAlignment(Qt.AlignCenter)
        self.lbl_received = QLabel("$0.00")
        self.lbl_received.setStyleSheet("""
            font-size: 28px;
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
        chg_title.setStyleSheet("font-size: 13px; color: #64748b; font-weight: 600;")
        chg_title.setAlignment(Qt.AlignCenter)
        self.lbl_change = QLabel("$0.00")
        self.lbl_change.setStyleSheet("""
            font-size: 28px;
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
        bills_grid.setSpacing(12)
        bills = [20, 50, 100, 200, 500, 1000]
        for idx, val in enumerate(bills):
            btn = QPushButton(f"${val}")
            btn.setMinimumHeight(72)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 20px;
                    font-weight: 700;
                    background: #1a1a26;
                    border: 1px solid #2a2a3a;
                    border-radius: 16px;
                    color: #e2e8f0;
                }
                QPushButton:hover {
                    background: #22222e;
                    border-color: #6366f1;
                }
                QPushButton:pressed {
                    background: #2a2a3a;
                }
            """)
            btn.clicked.connect(lambda _=None, v=val: self._add_bill(v))
            bills_grid.addWidget(btn, idx // 3, idx % 3)
        root.addLayout(bills_grid)

        # ─── Quick Actions ────────────────────────────────────────────────
        quick_row = QHBoxLayout()
        quick_row.setSpacing(12)

        btn_exact = QPushButton((get_icon_char('check') or '✓') + "  " + (i18n.t('exact') or "Exacto"))
        btn_exact.setMinimumHeight(64)
        btn_exact.setProperty("role", "success")
        btn_exact.clicked.connect(self._exact)

        btn_other = QPushButton((get_icon_char('keyboard') or '⌨') + "  " + (i18n.t('other_amount') or "Otro monto"))
        btn_other.setMinimumHeight(64)
        btn_other.clicked.connect(self._other)

        quick_row.addWidget(btn_exact)
        quick_row.addWidget(btn_other)
        root.addLayout(quick_row)

        # ─── Action Buttons ───────────────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(16)

        btn_cancel = QPushButton(i18n.t('cancel') or "Cancelar")
        btn_cancel.setMinimumHeight(72)
        btn_cancel.clicked.connect(self.reject)

        btn_charge = QPushButton((get_icon_char('arrow-right') or '→') + "  " + (i18n.t('charge') or "COBRAR"))
        btn_charge.setMinimumHeight(72)
        btn_charge.setProperty("role", "primary")
        btn_charge.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: 700;
                letter-spacing: 1px;
            }
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
        
        # Color feedback
        if self.received >= self.total:
            self.lbl_received.setStyleSheet("""
                font-size: 28px; font-weight: 700; color: #10b981;
            """)
        else:
            self.lbl_received.setStyleSheet("""
                font-size: 28px; font-weight: 700; color: #f59e0b;
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

    def _try_accept(self):
        if self.received < self.total:
            QMessageBox.warning(self, i18n.t('charge') or "Cobro",
                                i18n.t('amount_less_total') or "El monto recibido es menor al total.")
            return
        self.accept()

    def result_values(self) -> tuple[int, int]:
        return self.received, max(0, self.received - self.total)


class AdminPinDialog(QDialog):
    """Secure Admin Access"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        layout.setSpacing(28)

        # Icon/Title
        from ui.icon_helper import get_icon_char
        icon_lbl = QLabel(get_icon_char("lock") or "🔐")
        icon_lbl.setObjectName("IconLabel")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 48px;")

        title = QLabel(i18n.t("admin_pin_prompt") or "Acceso Administrador")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px;")

        subtitle = QLabel("Ingrese su PIN de seguridad")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #64748b; font-size: 14px;")

        self.ed_pin = QLineEdit()
        self.ed_pin.setEchoMode(QLineEdit.Password)
        self.ed_pin.setMaxLength(16)
        self.ed_pin.setMinimumHeight(72)
        self.ed_pin.setAlignment(Qt.AlignCenter)
        self.ed_pin.setStyleSheet("""
            QLineEdit {
                font-size: 32px;
                font-weight: 700;
                letter-spacing: 8px;
                background: #16161e;
                border: 2px solid #2a2a3a;
                border-radius: 18px;
            }
            QLineEdit:focus {
                border-color: #6366f1;
            }
        """)
        self.ed_pin.setPlaceholderText("• • • •")

        # ─── Keypad numérico integrado ─────────────────────────────────────
        keypad = QGridLayout()
        keypad.setSpacing(8)

        # Números 1–9
        nums = [
            ("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("7", 2, 0), ("8", 2, 1), ("9", 2, 2),
        ]
        for txt, r, c in nums:
            b = QPushButton(txt)
            b.setMinimumHeight(48)
            b.setObjectName("KeypadButton")
            b.clicked.connect(lambda _=None, t=txt: self._press_digit(t))
            keypad.addWidget(b, r, c)

        # Fila inferior: Limpiar, 0, Borrar
        btn_clear = QPushButton("C")
        btn_clear.setMinimumHeight(48)
        btn_clear.setProperty("role", "danger")
        btn_clear.setObjectName("KeypadButton")
        btn_clear.clicked.connect(self._clear_pin)
        keypad.addWidget(btn_clear, 3, 0)

        btn_zero = QPushButton("0")
        btn_zero.setMinimumHeight(48)
        btn_zero.setObjectName("KeypadButton")
        btn_zero.clicked.connect(lambda _=None: self._press_digit("0"))
        keypad.addWidget(btn_zero, 3, 1)

        btn_back = QPushButton("⌫")
        btn_back.setMinimumHeight(48)
        btn_back.setObjectName("KeypadButton")
        btn_back.clicked.connect(self._backspace_pin)
        keypad.addWidget(btn_back, 3, 2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(16)
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(64)
        btn_ok = QPushButton("→  Acceder")
        btn_ok.setMinimumHeight(64)
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
            QMessageBox.warning(self, "PIN", i18n.t("pin_required") or "Capture el PIN.")
            return
        if check_admin_pin(pin):
            self.accept()
        else:
            self.ed_pin.clear()
            self.ed_pin.setStyleSheet("""
                QLineEdit {
                    font-size: 32px;
                    font-weight: 700;
                    letter-spacing: 8px;
                    background: rgba(239, 68, 68, 0.1);
                    border: 2px solid #ef4444;
                    border-radius: 18px;
                }
            """)
            QMessageBox.critical(self, "PIN", i18n.t("pin_bad") or "PIN incorrecto.")


class POSWindow(QMainWindow):
    """
    Premium Point of Sale Interface
    Designed for speed, elegance, and touch-first interaction
    """
    
    def __init__(self):
        super().__init__()
        self._admin_win = None
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setCursor(QCursor(Qt.BlankCursor))
        self.setWindowTitle(i18n.t("title"))

        # ─── Main Container ───────────────────────────────────────────────
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(container)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

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
        self.grid_wrap.setContentsMargins(24, 24, 24, 24)
        self.grid_wrap.setSpacing(20)

        # Header
        head = QHBoxLayout()
        head.setSpacing(16)

        self.btn_back = QPushButton("←  " + (i18n.t("back") or "Atrás"))
        self.btn_back.setMinimumHeight(52)
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
        self.grid.setSpacing(14)
        self.grid_wrap.addLayout(self.grid, 1)

        self.products_area.setWidget(products_panel)

        # ═══════════════════════════════════════════════════════════════════
        # RIGHT PANEL - Cart
        # ═══════════════════════════════════════════════════════════════════
        self.right_wrap = QWidget()
        self.right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.right_wrap.setObjectName("CartPanel")
        right = QVBoxLayout(self.right_wrap)
        right.setContentsMargins(24, 24, 24, 24)
        right.setSpacing(16)

        # ─── Top Bar ──────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 12)
        top_bar.setSpacing(12)

        self.title_lbl = QLabel(i18n.t("cart") or "Carrito")
        self.title_lbl.setObjectName("SectionTitle")

        self.lang_btn = QPushButton(i18n.t("lang"))
        self.lang_btn.setMinimumSize(56, 48)
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)

        self.btn_reprint = QPushButton(get_icon_char('print') or '🖨')
        self.btn_reprint.setMinimumSize(56, 48)
        self.btn_reprint.setProperty("role", "ghost")
        self.btn_reprint.setToolTip(i18n.t("reprint") or "Reimprimir")
        self.btn_reprint.clicked.connect(self._reprint_last)

        self.btn_admin = QPushButton(get_icon_char('gear') or '⚙')
        self.btn_admin.setMinimumSize(56, 48)
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
        ctrls.setSpacing(10)

        ctrl_buttons = [
            ("-", None, self._dec_qty),
            ("+", None, self._inc_qty),
            ("#", None, self._set_qty),
            (get_icon_char('xmark') or "✕", "danger", self._remove_item),
            (i18n.t("clear_cart") or "Vaciar", "danger", self._clear_cart),
        ]

        for text, role, callback in ctrl_buttons:
            btn = QPushButton(text)
            btn.setMinimumHeight(56)
            if len(text) == 1:
                btn.setStyleSheet("font-size: 22px; font-weight: 700;")
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
        total_frame.setStyleSheet("""
            QFrame {
                background: #16161e;
                border-radius: 18px;
                padding: 16px;
            }
        """)
        total_layout = QVBoxLayout(total_frame)
        total_layout.setContentsMargins(20, 16, 20, 16)
        total_layout.setSpacing(4)

        total_label_title = QLabel("TOTAL")
        total_label_title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 2px;
            color: #64748b;
        """)
        total_label_title.setAlignment(Qt.AlignRight)

        self.total_label = QLabel("$0.00")
        self.total_label.setObjectName("TotalLabel")
        self.total_label.setAlignment(Qt.AlignRight)

        total_layout.addWidget(total_label_title)
        total_layout.addWidget(self.total_label)

        # ─── Charge Button ────────────────────────────────────────────────
        self.btn_charge = QPushButton("→  " + (i18n.t("pay_print") or "COBRAR"))
        self.btn_charge.setMinimumHeight(80)
        self.btn_charge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_charge.setProperty("role", "primary")
        self.btn_charge.setStyleSheet("""
            QPushButton {
                font-size: 20px;
                font-weight: 700;
                letter-spacing: 1px;
            }
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

        # Restar: panel derecho + márgenes del root (16*2) + spacing entre paneles (16)
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
        
        btn.clicked.connect(lambda _=None, prod=p: self.add_item(prod))
        return btn

    def _populate_grid(self):
        self.categories_enabled = is_categories_enabled()

        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        avail_w = self._available_grid_width()
        btn_min = self._target_button_min_size(avail_w)
        spacing = self.grid.spacing()
        margins = self.grid_wrap.contentsMargins().left()
        cols = self._calc_cols(avail_w, btn_min.width(), spacing, margins)
        self._current_cols = cols
        est_text_w = max(60, btn_min.width() - 24)

        if not self.categories_enabled:
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("products") or "Productos")

            prods = self.products
            for idx, p in enumerate(prods):
                btn = self._make_product_button(p, btn_min, est_text_w)
                self.grid.addWidget(btn, idx // cols, idx % cols)
            self.grid.setRowStretch((len(prods) // cols) + 1, 1)
            return

        if self.current_category is None:
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("categories") or "Categorías")
            cat_btn_min = self._target_category_button_min_size(avail_w)
            cols = self._calc_cols(avail_w, cat_btn_min.width(), spacing, margins)
            self._current_cols = cols
            for idx, c in enumerate(self.categories):
                btn = self._make_category_button(c, cat_btn_min)
                self.grid.addWidget(btn, idx // cols, idx % cols)
            self.grid.setRowStretch((len(self.categories) // cols) + 1, 1)
        else:
            self.btn_back.setVisible(True)
            self.lbl_grid_title.setText(self.current_category)
            prods = [p for p in self.products if (p.get("category") or "General") == self.current_category]
            for idx, p in enumerate(prods):
                btn = self._make_product_button(p, btn_min, est_text_w)
                self.grid.addWidget(btn, idx // cols, idx % cols)
            self.grid.setRowStretch((len(prods) // cols) + 1, 1)

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
            new_cols = self._calc_cols(avail_w, min_size.width(), self.grid.spacing(), 0)
            if new_cols != self._current_cols:
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
        allow_decimal = bool(
            self.prod_meta.get(("id", it.product_id), self.prod_meta.get(("name", it.name), {})).get("allow_decimal", False)
        )
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
        
        # CRÍTICO: Validar que hay turno activo
        from services.shifts import current_shift
        sh = current_shift()
        if not sh:
            QMessageBox.critical(
                self,
                "Sin Turno Activo",
                "No hay un turno abierto.\n\n"
                "Debe abrir un turno desde el panel de administración "
                "antes de realizar ventas."
            )
            return
        
        total_cents = int(round(sum(round(i.price * i.qty) for i in self.cart)))
        dlg = PaymentDialog(total_cents, self)
        if dlg.exec() != QDialog.Accepted:
            return
        paid_cents, change_cents = dlg.result_values()

        # Guardar ticket asociado al turno activo
        ticket_id = save_ticket(self.cart, shift_id=sh["id"])
        
        try:
            try:
                from services.receipts import render_ticket
                text = render_ticket(self.cart, paid_cents=paid_cents, change_cents=change_cents)
                self.printer.print_text(text)
            except Exception:
                self.printer.print_cart(self.cart)
            self.printer.open_drawer()
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
        items = get_ticket_items(tid)
        self._reprint_in_progress = True
        self.btn_reprint.setEnabled(False)
        try:
            self.printer.print_cart(items)
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

        self.hide()
        self._admin_win = AdminWindow()

        def _back_to_kiosk():
            self._admin_win = None
            self.showFullScreen()

        self._admin_win.destroyed.connect(lambda _obj=None: _back_to_kiosk())
        self._admin_win.showFullScreen()

    # ═══════════════════════════════════════════════════════════════════════
    # LANGUAGE
    # ═══════════════════════════════════════════════════════════════════════

    def _toggle_lang(self):
        i18n.toggle()
        self.setWindowTitle(i18n.t("title"))
        self.title_lbl.setText(i18n.t("cart"))
        self.lang_btn.setText(i18n.t("lang"))
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
