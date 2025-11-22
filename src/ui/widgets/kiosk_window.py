import subprocess
import sys
import os
import math
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton,
    QGridLayout, QListWidget, QHBoxLayout, QSizePolicy, QScrollArea,
    QMessageBox, QDialog, QLineEdit, QApplication, QStyle
)
from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QCursor, QGuiApplication, QFontMetrics, QIcon

from services.sales import (
    get_active_products, CartItem, save_ticket,
    get_last_ticket_id, get_ticket_items
)
from services.settings import is_categories_enabled
from drivers.printer_escpos import EscposPrinter
from services import i18n
from ui.widgets.keypad import NumKeypad
from services.auth import check_admin_pin

ROOT = Path(__file__).resolve().parents[2]

class PaymentDialog(QDialog):
    def __init__(self, total_cents: int, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(520)
        self.total = int(total_cents)
        self.received = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        root.setSpacing(16)
        root.addWidget(QLabel(f"{i18n.t('charge_total') or 'Total a cobrar'}: $ {self._fmt(self.total)}"))

        self.lbl_received = QLabel(f"{i18n.t('received') or 'Recibido'}: $ 0.00")
        self.lbl_change   = QLabel(f"{i18n.t('change') or 'Cambio'}: $ 0.00")
        root.addWidget(self.lbl_received)
        root.addWidget(self.lbl_change)

        row1 = QHBoxLayout(); row1.setSpacing(12)
        for val in (20, 50, 100, 200, 500, 1000):
            b = QPushButton(f"${val}")
            b.setMinimumHeight(56)
            b.clicked.connect(lambda _=None, v=val: self._add_bill(v))
            row1.addWidget(b)
        root.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(12)
        btn_exact = QPushButton(i18n.t('exact') or "Exacto")
        btn_exact.setMinimumHeight(56)
        btn_exact.clicked.connect(self._exact)
        btn_other = QPushButton(i18n.t('other_amount') or "Otro monto")
        btn_other.setMinimumHeight(56)
        btn_other.clicked.connect(self._other)
        row2.addWidget(btn_exact)
        row2.addWidget(btn_other)
        root.addLayout(row2)

        row3 = QHBoxLayout(); row3.setSpacing(12)
        btn_cancel = QPushButton(i18n.t('cancel') or "Cancelar")
        btn_ok     = QPushButton(i18n.t('charge') or "Cobrar")
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._try_accept)
        row3.addWidget(btn_cancel)
        row3.addWidget(btn_ok)
        root.addLayout(row3)

        self._refresh()

    def _fmt(self, cents: int) -> str:
        return f"{cents/100:.2f}"

    def _refresh(self):
        change = max(0, self.received - self.total)
        self.lbl_received.setText(f"{i18n.t('received') or 'Recibido'}: $ {self._fmt(self.received)}")
        self.lbl_change.setText(f"{i18n.t('change') or 'Cambio'}: $ {self._fmt(change)}")

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        lbl = QLabel(i18n.t("admin_pin_prompt") or "Ingrese PIN de administrador")
        lbl.setAlignment(Qt.AlignCenter)
        self.ed_pin = QLineEdit()
        self.ed_pin.setEchoMode(QLineEdit.Password)
        self.ed_pin.setMaxLength(16)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_ok = QPushButton(i18n.t("ok") or "OK")
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)

        layout.addWidget(lbl)
        layout.addWidget(self.ed_pin)
        layout.addLayout(btn_row)

        self.ed_pin.setFocus()

    def _on_ok(self):
        pin = self.ed_pin.text() or ""
        if not pin:
            QMessageBox.warning(self, i18n.t("admin_pin_title") or "PIN", i18n.t("pin_required") or "Capture el PIN.")
            return
        if check_admin_pin(pin):
            self.accept()
        else:
            QMessageBox.critical(self, i18n.t("admin_pin_title") or "PIN", i18n.t("pin_bad") or "PIN incorrecto.")


class POSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setCursor(QCursor(Qt.BlankCursor))
        self.setWindowTitle(i18n.t("title"))

        container = QWidget(); container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QHBoxLayout(container)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Right (cart)
        self.right_wrap = QWidget(); self.right_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.right_wrap.setObjectName("CartPanel")
        right = QVBoxLayout(self.right_wrap)
        right.setContentsMargins(10, 10, 10, 10)
        right.setSpacing(8)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 4)
        top_bar.setSpacing(8)
        self.title_lbl = QLabel()
        self.title_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title_lbl.setObjectName("SectionTitle")
        self.title_lbl.setToolTip(i18n.t("cart"))
        self.title_lbl.setText(i18n.t("cart"))

        self.lang_btn = QPushButton(i18n.t("lang"))
        self.lang_btn.setMinimumHeight(44)
        self.lang_btn.setFixedWidth(70)
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)

        self.btn_reprint = QPushButton()
        self.btn_reprint.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        self.btn_reprint.setIconSize(QSize(20, 20))
        self.btn_reprint.setContentsMargins(28, 0, 0, 0)
        self.btn_reprint.setMinimumHeight(44)
        self.btn_reprint.setProperty("role", "ghost")
        self.btn_reprint.clicked.connect(self._reprint_last)
        self.btn_reprint.setToolTip(i18n.t("reprint") or "Reimprimir")

        # NUEVO: botón Admin
        self.btn_admin = QPushButton(i18n.t("admin") or "Admin")
        self.btn_admin.setMinimumHeight(44)
        self.btn_admin.setFixedWidth(90)
        self.btn_admin.setProperty("role", "ghost")
        self.btn_admin.clicked.connect(self._go_admin)

        top_bar.addWidget(self.title_lbl)
        top_bar.addStretch(1)
        top_bar.addWidget(self.btn_reprint)
        top_bar.addWidget(self.btn_admin)   # <-- aquí
        top_bar.addWidget(self.lang_btn)

        self.list = QListWidget(); self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list.setSpacing(4)
        self.list.setMinimumHeight(200)

        ctrls = QHBoxLayout()
        ctrls.setSpacing(6)
        self.btn_minus = QPushButton("−")
        self.btn_plus  = QPushButton("+")
        self.btn_qty   = QPushButton("N")
        self.btn_remove= QPushButton("X")
        font_remove = self.btn_remove.font()
        font_remove.setBold(True)
        self.btn_remove.setFont(font_remove)
        self.btn_clear = QPushButton(i18n.t("clear_cart") or "Vaciar")
        for b in (self.btn_minus, self.btn_plus, self.btn_qty, self.btn_remove, self.btn_clear):
            b.setMinimumHeight(44)
        self.btn_remove.setProperty("role", "danger")
        self.btn_clear.setProperty("role", "danger")
        self.btn_remove.setToolTip(i18n.t("delete") or "Eliminar")
        self.btn_plus.clicked.connect(self._inc_qty)
        self.btn_minus.clicked.connect(self._dec_qty)
        self.btn_qty.clicked.connect(self._set_qty)
        self.btn_remove.clicked.connect(self._remove_item)
        self.btn_clear.clicked.connect(self._clear_cart)
        ctrls.addWidget(self.btn_minus); ctrls.addWidget(self.btn_plus); ctrls.addWidget(self.btn_qty)
        ctrls.addWidget(self.btn_remove); ctrls.addWidget(self.btn_clear)

        self.total_label = QLabel(i18n.t("total", amount="{:.2f}".format(0.0)))
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.total_label.setObjectName("TotalLabel")
        self.total_label.mousePressEvent = lambda ev: self.charge()

        btn_row = QHBoxLayout()
        self.btn_charge = QPushButton(i18n.t("pay_print"))
        self.btn_charge.setMinimumHeight(48)
        self.btn_charge.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_charge.setProperty("role", "primary")
        self.btn_charge.clicked.connect(self.charge)
        btn_row.addWidget(self.btn_charge)

        self.total_label.setProperty("role", "total")
        right.addLayout(top_bar); right.addWidget(self.list, 1); right.addLayout(ctrls)
        right.addWidget(self.total_label); right.addLayout(btn_row)

        # Left (categories/products)
        self.products_area = QScrollArea(); self.products_area.setFrameShape(QScrollArea.NoFrame)
        self.products_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.products_area.setWidgetResizable(True)

        products_panel = QWidget()
        products_panel.setObjectName("GridPanel")
        self.grid_wrap = QVBoxLayout(products_panel)
        self.grid_wrap.setContentsMargins(10, 10, 10, 10)
        self.grid_wrap.setSpacing(8)

        head = QHBoxLayout(); head.setSpacing(10)
        self.btn_back = QPushButton("← " + (i18n.t("back") or "Atrás"))
        self.btn_back.setMinimumHeight(48)
        self.btn_back.clicked.connect(self._back_to_categories)
        self.lbl_grid_title = QLabel(i18n.t("categories") or "Categorías")
        self.lbl_grid_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_grid_title.setObjectName("SectionTitle")
        head.addWidget(self.btn_back)
        head.addStretch(1)
        head.addWidget(self.lbl_grid_title)
        head.addStretch(10)
        self.grid_wrap.addLayout(head)

        self.grid = QGridLayout(); self.grid.setContentsMargins(0,0,0,0); self.grid.setSpacing(10)
        self.grid_wrap.addLayout(self.grid, 1)

        self.products_area.setWidget(products_panel)

        # Data
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
        self.current_category: str | None = None  # usado solo cuando categories_enabled = True
        self._current_cols = 0

        self._populate_grid()
        root.addWidget(self.products_area, 1)
        root.addWidget(self.right_wrap, 0)
        root.setStretch(0, 3)
        root.setStretch(1, 2)
        self.setCentralWidget(container)

        self.cart: list[CartItem] = []
        self.printer = EscposPrinter()
        self._reprint_in_progress = False

        self.installEventFilter(self)
        self._refresh_total()

    # ----- Categories / Grid -----
    def _extract_categories(self, items: list[dict]) -> list[str]:
        cats = []
        for p in items:
            c = (p.get("category") or "General").strip() or "General"
            if c not in cats:
                cats.append(c)
        cats.sort(key=lambda s: s.lower())
        return cats or ["General"]

    def _target_right_min_width(self, total_width: int) -> int:
        if total_width <= 800: return 260
        if total_width <= 1024: return 320
        if total_width <= 1280: return 380
        return 440

    def _target_button_min_size(self, avail_width: int) -> QSize:
        if avail_width <= 500: return QSize(150, 96)
        if avail_width <= 700: return QSize(170, 104)
        if avail_width <= 900: return QSize(190, 112)
        if avail_width <= 1100: return QSize(210, 122)
        return QSize(230, 132)

    def _calc_cols(self, avail_width: int, min_btn_w: int, spacing: int, margins: int) -> int:
        usable = max(0, avail_width - 2*margins)
        cols = max(1, (usable + spacing) // (min_btn_w + spacing))
        return max(2, min(cols, 5))

    def _elide_two_lines(self, text: str, fm: QFontMetrics, width: int, max_lines: int = 2) -> str:
        words = text.split(); lines = []; cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if fm.horizontalAdvance(test) <= width: cur = test
            else:
                lines.append(cur); cur = w
                if len(lines) == max_lines - 1: break
        if cur: lines.append(cur)
        if lines: lines[-1] = fm.elidedText(lines[-1], Qt.ElideRight, width)
        return "\n".join(lines[:max_lines])

    def _available_grid_width(self) -> int:
        screen = QGuiApplication.primaryScreen()
        total_w = screen.geometry().width() if screen else self.width()
        right_min = self._target_right_min_width(total_w)
        self.right_wrap.setMinimumWidth(right_min)
        return max(0, total_w - right_min)

    def _make_category_button(self, name: str, btn_min: QSize) -> QPushButton:
        btn = QPushButton(name)
        btn.setMinimumSize(btn_min)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn.clicked.connect(lambda _=None, cat=name: self._open_category(cat))
        return btn

    def _make_product_button(self, p: dict, btn_min: QSize, est_width: int) -> QPushButton:
        btn = QPushButton()
        btn.setMinimumSize(btn_min)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        fm = btn.fontMetrics()
        name = self._elide_two_lines(p.get("name", ""), fm, est_width, max_lines=2)
        price = "$ {:.2f}".format(p.get("price", 0) / 100.0)
        unit = (p.get("unit") or "pz").strip()
        btn.setText("{}\n{} / {}".format(name, price, unit))
        btn.clicked.connect(lambda _=None, prod=p: self.add_item(prod))
        return btn

    def _populate_grid(self):
        # Clear grid
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        avail_w = self._available_grid_width()
        btn_min = self._target_button_min_size(avail_w)
        spacing = self.grid.spacing()
        margins = 0
        cols = self._calc_cols(avail_w, btn_min.width(), spacing, margins)
        self._current_cols = cols
        est_text_w = max(60, btn_min.width() - 22)

        if not self.categories_enabled:
            # --- MODO SIN CATEGORÍAS: un solo menú de productos ---
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("products") or "Productos")

            prods = self.products  # todos los productos activos
            for idx, p in enumerate(prods):
                btn = self._make_product_button(p, btn_min, est_text_w)
                self.grid.addWidget(btn, idx // cols, idx % cols)
            self.grid.setRowStretch((len(prods) // cols) + 1, 1)
            return

        # --- MODO CON CATEGORÍAS (como antes) ---
        if self.current_category is None:
            # Vista de categorías
            self.btn_back.setVisible(False)
            self.lbl_grid_title.setText(i18n.t("categories") or "Categorías")
            for idx, c in enumerate(self.categories):
                btn = self._make_category_button(c, btn_min)
                self.grid.addWidget(btn, idx // cols, idx % cols)
            self.grid.setRowStretch((len(self.categories) // cols) + 1, 1)
        else:
            # Vista de productos de la categoría
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
            new_cols = self._calc_cols(avail_w, self._target_button_min_size(avail_w).width(), self.grid.spacing(), 0)
            if new_cols != self._current_cols:
                self._populate_grid()
        return super().eventFilter(obj, event)

    # ----- Cart helpers -----
    def _fmt_qty(self, q: float) -> str:
        if abs(q - round(q)) < 1e-6:
            return str(int(round(q)))
        s = f"{q:.3f}".rstrip("0").rstrip(".")
        return s or "0"

    def _format_row(self, it: CartItem) -> str:
        subtotal = round(it.price * it.qty) / 100.0
        return "{} x{} {}  $ {:.2f}".format(it.name, self._fmt_qty(it.qty), (it.unit or 'pz'), subtotal)

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

    # ----- Cart operations -----
    def add_item(self, p: dict):
        prod_id = p.get("id"); name = p.get("name", ""); price = int(p.get("price", 0))
        unit = (p.get("unit") or "pz").strip()
        idx = self._find_cart_index_by_product(prod_id, name)
        if idx >= 0:
            self.cart[idx].qty += 1.0
            self._refresh_list_row(idx); self.list.setCurrentRow(idx)
        else:
            it = CartItem(prod_id, name, price, 1.0, unit)
            self.cart.append(it)
            self.list.addItem(self._format_row(it))
            self.list.setCurrentRow(self.list.count() - 1)
        self._refresh_total()

    def _inc_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart): return
        q = self.cart[idx].qty
        self.cart[idx].qty = math.floor(q) + 1.0
        self._refresh_list_row(idx); self._refresh_total()

    def _dec_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart): return
        q = self.cart[idx].qty
        self.cart[idx].qty = max(1.0, math.ceil(q) - 1.0)
        self._refresh_list_row(idx); self._refresh_total()

    def _set_qty(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart): return
        it = self.cart[idx]
        allow_decimal = bool(self.prod_meta.get(("id", it.product_id), self.prod_meta.get(("name", it.name), {})).get("allow_decimal", False))
        dlg = NumKeypad(title=i18n.t("quantity") or "Cantidad", allow_decimal=allow_decimal)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.value_float()
            if allow_decimal:
                q = max(0.001, min(9999.0, q))
            else:
                q = max(1.0, float(int(round(q or 0.0)) or 1))
            self.cart[idx].qty = q
            self._refresh_list_row(idx); self._refresh_total()

    def _remove_item(self):
        idx = self._selected_index()
        if idx < 0 or idx >= len(self.cart): return
        self.cart.pop(idx); self.list.takeItem(idx); self._refresh_total()

    def _clear_cart(self):
        if not self.cart: return
        if QMessageBox.question(self, i18n.t("cart") or "Carrito", i18n.t("confirm_clear") or "¿Vaciar carrito?") == QMessageBox.Yes:
            self.cart.clear(); self.list.clear(); self._refresh_total()

    def _total_amount(self) -> float:
        cents = sum(round(i.price * i.qty) for i in self.cart)
        return cents / 100.0

    def _refresh_total(self):
        self.total_label.setText(i18n.t("total", amount="{:.2f}".format(self._total_amount())))

    # ----- Checkout with auto-charge -----
    def charge(self):
        if not self.cart: return
        total_cents = int(round(sum(round(i.price * i.qty) for i in self.cart)))
        dlg = PaymentDialog(total_cents, self)
        if dlg.exec() != QDialog.Accepted:
            return
        paid_cents, change_cents = dlg.result_values()

        _ = save_ticket(self.cart)
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

        self.cart.clear(); self.list.clear(); self._refresh_total()

    def _reprint_last(self):
        if self._reprint_in_progress:
            return
        tid = get_last_ticket_id()
        if not tid:
            QMessageBox.information(self, "Ticket", i18n.t("no_last_ticket") or "No hay tickets previos."); return
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
            return  # PIN cancelado o incorrecto

        from PySide6.QtWidgets import QApplication

        try:
            env = os.environ.copy()
            cmd = [sys.executable, "-m", "cli", "run-admin"]
            subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env=env,
            )
        except Exception as e:
            QMessageBox.critical(self, "Admin", f"No se pudo abrir Admin:\n{e}")
            return

        QApplication.instance().quit()


    # ----- Language toggle -----
    def _toggle_lang(self):
        i18n.toggle()
        self.setWindowTitle(i18n.t("title"))
        self.title_lbl.setText(i18n.t("cart"))
        self.lang_btn.setText(i18n.t("lang"))
        self.btn_reprint.setToolTip(i18n.t("reprint") or "Reimprimir")
        self.btn_remove.setToolTip(i18n.t("delete") or "Eliminar")
        self.btn_clear.setText(i18n.t("clear_cart") or "Vaciar")
        self.btn_charge.setText(i18n.t("pay_print"))
        self.total_label.setText(i18n.t("total", amount="{:.2f}".format(self._total_amount())))
        self.btn_back.setText("← " + (i18n.t("back") or "Atrás"))
        if self.categories_enabled:
            self.lbl_grid_title.setText(i18n.t("categories") if self.current_category is None else self.current_category)
        else:
            self.lbl_grid_title.setText(i18n.t("products") or "Productos")
        self._populate_grid()
        self._rebuild_list()

