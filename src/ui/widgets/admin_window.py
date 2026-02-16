from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QHBoxLayout, QComboBox,
    QMessageBox, QSpinBox, QGridLayout, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QCheckBox, QDialog, QListWidget, QListWidgetItem, QApplication,
    QFrame, QStackedLayout, QTextEdit, QDateEdit,
    QSizePolicy
)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer, QDate, QLocale
from pathlib import Path

import sys
import subprocess
import os

from argon2 import PasswordHasher
from services.osctl import wifi_list, wifi_connect, wifi_status, reboot, poweroff
from drivers.printer_escpos import EscposPrinter
from services import i18n
from services.products import (
    list_products, get_product, create_product, update_product,
    set_active, delete_product
)
from services.employees import (
    list_employees, get_employee, create_employee,
    update_employee, set_employee_active, delete_employee
)
from services.sales import (
    money_to_cents, cents_to_money, list_tickets,
    search_tickets_by_id, get_ticket_details
)
from services.shifts import (
    open_shift,
    current_shift,
    close_shift,
    list_shifts_since,
    shift_totals,
)
from services.reports import (
    render_shift_text, render_range_text,
    csv_sales_detailed_bytes
)
from services.receipts import render_ticket
from services.emailer import send_mail, recent_emails
from services.settings import load_config, save_config, is_categories_enabled, set_categories_enabled, reset_config_to_defaults
from ui.icon_helper import get_icon_char
from ui.widgets.osk import OnScreenKeyboard
from ui.widgets.keypad import NumKeypad
from services.auth import check_admin_pin

try:
    import usb.core
    import usb.util
    HAS_PYUSB = True
except Exception:
    HAS_PYUSB = False

ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = ROOT / "config" / "config.yaml"


# Removed local _load_settings and _save_settings. 
# Using load_config and save_config from services.settings instead.


def _intval(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 0
    return int(s, 16) if s.lower().startswith("0x") else int(s)


def _fmt_hex(v: int | None) -> str:
    try:
        return f"0x{int(v):04x}"
    except Exception:
        return ""


def _scan_usb_printers() -> list[dict]:
    devices = []
    if not HAS_PYUSB:
        return devices
    for dev in usb.core.find(find_all=True):
        info = {
            "vid": f"0x{dev.idVendor:04x}",
            "pid": f"0x{dev.idProduct:04x}",
            "product": "",
            "manufacturer": "",
            "interface": 0,
            "eps_out": [],
            "eps_in": [],
        }
        try:
            if dev.iProduct:
                info["product"] = usb.util.get_string(dev, dev.iProduct) or ""
            if dev.iManufacturer:
                info["manufacturer"] = usb.util.get_string(dev, dev.iManufacturer) or ""
        except Exception:
            pass
        cfg = None
        try:
            cfg = dev.get_active_configuration()
        except usb.core.USBError:
            try:
                dev.set_configuration()
                cfg = dev.get_active_configuration()
            except Exception:
                cfg = None
        if cfg:
            for i, iface in enumerate(cfg):
                eps_out, eps_in = [], []
                for ep in iface.endpoints():
                    addr = int(ep.bEndpointAddress)
                    if addr & 0x80:
                        eps_in.append(addr)
                    else:
                        eps_out.append(addr)
                if eps_out or eps_in:
                    info["interface"] = i
                    info["eps_out"] = sorted(set(eps_out))
                    info["eps_in"] = sorted(set(eps_in))
                    break
        devices.append(info)
    uniq, seen = [], set()
    for d in devices:
        key = (d["vid"], d["pid"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(d)
    return uniq


class ToastManager(QObject):
    """Muestra mensajes flotantes apilados para evitar encimarse."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.host = host
        self.queue: list[tuple[str, str, int]] = []
        self.container = QWidget(host)
        self.container.setObjectName("ToastContainer")
        self.container.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.layout = QVBoxLayout(self.container)
        self.layout.setAlignment(Qt.AlignTop | Qt.AlignRight)
        self.layout.setSpacing(10)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.active: list[QFrame] = []
        self.sync_geometry()

    def sync_geometry(self):
        margin = 18
        self.container.setGeometry(
            margin,
            margin,
            max(0, self.host.width() - (margin * 2)),
            max(0, self.host.height() - (margin * 2)),
        )

    def show_toast(self, message: str, level: str = "info", duration_ms: int = 3600):
        self.queue.append((message, level, duration_ms))
        if len(self.queue) == 1:
            self._dequeue()

    def _dequeue(self):
        if not self.queue:
            return
        msg, level, timeout = self.queue[0]

        frame = QFrame(self.container)
        frame.setObjectName("ToastFrame")
        frame.setProperty("toastLevel", level)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        label = QLabel(msg)
        label.setWordWrap(True)
        layout.addWidget(label)
        self.layout.addWidget(frame)
        self.active.append(frame)
        self.container.raise_()
        self.container.show()

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._finish(frame))
        timer.start(timeout)
        frame._toast_timer = timer

    def _finish(self, frame: QFrame):
        if frame in self.active:
            self.layout.removeWidget(frame)
            self.active.remove(frame)
            frame.deleteLater()
        if self.queue:
            self.queue.pop(0)
        if self.queue:
            self._dequeue()
        elif not self.active:
            self.container.hide()


class _OskFocusFilter(QObject):
    """Abre el OSK cuando un QLineEdit recibe foco (con guarda anti reentrancia)."""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.win = parent_window

    def eventFilter(self, obj, event):
        if isinstance(obj, QLineEdit) and event.type() == QEvent.FocusIn:
            if getattr(self.win, "_osk_guard", False):
                return False
            self.win._osk_guard = True
            try:
                is_password = (obj.echoMode() == QLineEdit.Password)
                dlg = OnScreenKeyboard(
                    title=i18n.t("keyboard_title") or "Teclado",
                    initial_text=obj.text(),
                    password_mode=is_password,
                    parent=self.win
                )
                if dlg.exec():
                    obj.setText(dlg.text())
                    obj.setCursorPosition(len(obj.text()))
            finally:
                self.win._osk_guard = False
            return False
        return False


class _PinKeypadFocusFilter(QObject):
    """Abre el keypad numérico cuando un QLineEdit de PIN recibe foco (sin OSK)."""

    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.win = parent_window

    def eventFilter(self, obj, event):
        if isinstance(obj, QLineEdit) and event.type() == QEvent.FocusIn:
            if getattr(self.win, "_pinpad_guard", False):
                return False
            self.win._pinpad_guard = True
            try:
                dlg = NumKeypad(title=i18n.t("keypad_title") or "Teclado", allow_decimal=False)
                if obj.text():
                    dlg.edit.setText(obj.text())
                if dlg.exec():
                    obj.setText(dlg.value_text())
                    obj.setCursorPosition(len(obj.text()))
            finally:
                self.win._pinpad_guard = False
            return False
        return False


class ProductDialog(QDialog):
    """Premium Product Editor"""

    def __init__(self, parent=None, *, product: dict | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(28)

        # Header
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char("box") or "📦")
        icon.setObjectName("IconLabel")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")

        title = QLabel("PRODUCTO")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        # Form
        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignCenter)

        self.ed_name = QLineEdit(product["name"] if product else "")
        self.ed_price = QLineEdit(cents_to_money(product["price"]) if product else "")
        self.ed_unit = QLineEdit(product["unit"] if product else "pz")
        self.ed_category = QLineEdit(
            (product.get("category") if product else None) or "General"
        )
        
        # Icon selector
        from ui.icon_helper import ICON_MAP, get_icon_char
        self.combo_icon = QComboBox()
        self.combo_icon.setMinimumHeight(64)  # Touch-friendly height
        self.combo_icon.setMaxVisibleItems(8)  # Reduce scroll, show 8 items at once
        
        # Touch-friendly settings
        self.combo_icon.setMinimumHeight(64)
        self.combo_icon.setMaxVisibleItems(8)
        
        self.combo_icon.addItem("(Sin ícono)", "")
        
        # Add available icons sorted by name
        for icon_name in sorted(ICON_MAP.keys()):
            icon_char = get_icon_char(icon_name)
            display_text = f"{icon_char}  {icon_name}"
            self.combo_icon.addItem(display_text, icon_name)
        
        # Select current icon if exists
        if product and product.get("icon"):
            idx = self.combo_icon.findData(product.get("icon"))
            if idx >= 0:
                self.combo_icon.setCurrentIndex(idx)

        self.cb_active = QCheckBox(i18n.t("prod_active"))
        self.cb_active.setChecked(bool(product["active"]) if product else True)
        self.cb_partial = QCheckBox(i18n.t("prod_allow_partial"))
        self.cb_partial.setChecked(bool(product.get("allow_decimal")) if product else False)

        for ed in (self.ed_name, self.ed_price, self.ed_unit, self.ed_category):
            ed.setMinimumHeight(56)

        form.addRow(i18n.t("prod_name"), self.ed_name)
        form.addRow(i18n.t("prod_price"), self.ed_price)
        form.addRow(i18n.t("prod_unit"), self.ed_unit)
        form.addRow(i18n.t("category") or "Categoría", self.ed_category)
        form.addRow("Ícono", self.combo_icon)

        checks = QHBoxLayout()
        checks.setSpacing(24)
        checks.addWidget(self.cb_active)
        checks.addWidget(self.cb_partial)
        form.addRow(checks)

        root.addLayout(form)

        # Actions
        row = QHBoxLayout()
        row.setSpacing(16)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setMinimumHeight(60)
        from ui.icon_helper import get_icon_char
        btn_ok = QPushButton(f"{get_icon_char('arrow-right') or '→'}  Guardar")
        btn_ok.setMinimumHeight(60)
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        root.addLayout(row)

        # OSK
        self._osk_filter = _OskFocusFilter(self)
        for w in (self.ed_name, self.ed_price, self.ed_unit, self.ed_category):
            w.installEventFilter(self._osk_filter)

    def data(self) -> dict | None:
        name = (self.ed_name.text() or "").strip()
        if not name:
            QMessageBox.warning(self, i18n.t("tab_products") or "Productos", i18n.t("prod_err_name"))
            return None
        try:
            cents = money_to_cents(self.ed_price.text())
        except Exception:
            QMessageBox.warning(self, i18n.t("tab_products") or "Productos", i18n.t("prod_err_price"))
            return None
        unit = (self.ed_unit.text() or "pz").strip() or "pz"
        category = (self.ed_category.text() or "General").strip() or "General"
        icon = self.combo_icon.currentData() or ""
        return {
            "name": name,
            "price": cents,
            "active": self.cb_active.isChecked(),
            "unit": unit,
            "allow_decimal": self.cb_partial.isChecked(),
            "category": category,
            "icon": icon,
        }


class EmployeeDialog(QDialog):
    """Premium Employee Editor"""

    def __init__(self, parent=None, *, employee: dict | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(28)

        # Header
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char("user") or "👤")
        icon.setObjectName("IconLabel")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")

        title = QLabel("EMPLEADO")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        # Form
        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ed_emp_no = QLineEdit(employee["emp_no"] if employee else "")
        self.ed_full_name = QLineEdit(employee["full_name"] if employee else "")
        self.ed_phone = QLineEdit(employee.get("phone", "") if employee else "")
        self.cb_active = QCheckBox(i18n.t("emp_active") or "Activo")
        self.cb_active.setChecked(bool(employee.get("active", 1)) if employee else True)

        for ed in (self.ed_emp_no, self.ed_full_name, self.ed_phone):
            ed.setMinimumHeight(56)

        form.addRow(i18n.t("emp_no") or "No. empleado", self.ed_emp_no)
        form.addRow(i18n.t("emp_name") or "Nombre completo", self.ed_full_name)
        form.addRow(i18n.t("emp_phone") or "Contacto", self.ed_phone)
        form.addRow(self.cb_active)

        root.addLayout(form)

        # Actions
        row = QHBoxLayout()
        row.setSpacing(16)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setMinimumHeight(60)
        from ui.icon_helper import get_icon_char
        btn_ok = QPushButton(f"{get_icon_char('arrow-right') or '→'}  Guardar")
        btn_ok.setMinimumHeight(60)
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        root.addLayout(row)

        # OSK
        self._osk_filter = _OskFocusFilter(self)
        for w in (self.ed_emp_no, self.ed_full_name, self.ed_phone):
            w.installEventFilter(self._osk_filter)

    def data(self) -> dict | None:
        emp_no = (self.ed_emp_no.text() or "").strip()
        full_name = (self.ed_full_name.text() or "").strip()
        phone = (self.ed_phone.text() or "").strip()
        if not emp_no or not full_name:
            QMessageBox.warning(
                self,
                i18n.t("employees_title") or "Empleados",
                i18n.t("emp_required") or "Número de empleado y nombre son obligatorios.",
            )
            return None
        return {
            "emp_no": emp_no,
            "full_name": full_name,
            "phone": phone,
            "active": self.cb_active.isChecked(),
        }


class ShiftCloseDialog(QDialog):
    """Dialog for closing shift with cash count"""

    def __init__(self, parent=None, shift_info: dict | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(500)
        
        self.shift_info = shift_info or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(24)

        # Header
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char("chart-bar") or "📊")
        icon.setObjectName("IconLabel")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")

        title = QLabel("CORTE DE CAJA")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        if shift_info:
            sums = shift_totals(shift_info.get("id", 0))
            opening = shift_info.get("opening_cash", 0)
            expected = opening + sums.get("total", 0)
            
            info_frame = QFrame()
            info_frame.setStyleSheet("""
                QFrame {
                    background: #16161e;
                    border-radius: 16px;
                    padding: 16px;
                }
            """)
            info_layout = QVBoxLayout(info_frame)
            info_layout.setSpacing(8)

            info_layout.addWidget(QLabel(f"Turno #{shift_info.get('id', '?')}"))
            info_layout.addWidget(QLabel(f"Ventas: {sums.get('tickets', 0)} tickets"))
            info_layout.addWidget(QLabel(f"Total ventas: ${cents_to_money(sums.get('total', 0))}"))
            
            expected_lbl = QLabel(f"Efectivo esperado: ${cents_to_money(expected)}")
            expected_lbl.setStyleSheet("font-size: 18px; font-weight: 700;")
            expected_lbl.setProperty("role", "success")
            info_layout.addWidget(expected_lbl)
            
            root.addWidget(info_frame)
            self._expected = expected
        else:
            self._expected = 0

        # Form
        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ed_cash = QLineEdit()
        self.ed_cash.setMinimumHeight(64)
        self.ed_cash.setPlaceholderText("0.00")
        self.ed_cash.setStyleSheet("""
            QLineEdit {
                font-size: 28px;
                font-weight: 700;
                text-align: right;
            }
        """)

        self.ed_closed_by = QLineEdit()
        self.ed_closed_by.setMinimumHeight(56)
        self.ed_closed_by.setPlaceholderText("Nombre del cajero")

        form.addRow("Efectivo en caja $:", self.ed_cash)
        form.addRow("Cerrado por:", self.ed_closed_by)

        root.addLayout(form)

        # Actions
        row = QHBoxLayout()
        row.setSpacing(16)

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setMinimumHeight(60)
        btn_cancel.clicked.connect(self.reject)

        from ui.icon_helper import get_icon_char
        btn_close = QPushButton(f"{get_icon_char('arrow-right') or '→'}  Cerrar Turno")
        btn_close.setMinimumHeight(60)
        btn_close.setProperty("role", "primary")
        btn_close.setStyleSheet("font-size: 16px; font-weight: 700;")
        btn_close.clicked.connect(self._validate_and_accept)

        row.addWidget(btn_cancel)
        row.addWidget(btn_close)
        root.addLayout(row)

        # OSK
        self._osk_filter = _OskFocusFilter(self)
        self.ed_cash.installEventFilter(self._osk_filter)
        self.ed_closed_by.installEventFilter(self._osk_filter)

    def _validate_and_accept(self):
        cash_text = self.ed_cash.text().strip()
        if not cash_text:
            QMessageBox.warning(
                self,
                "Corte de Caja",
                "Debe ingresar el efectivo contado en caja."
            )
            return
        self.accept()

    def data(self) -> dict:
        cash_text = self.ed_cash.text().strip().replace(",", "")
        try:
            cash_cents = money_to_cents(cash_text)
        except (KeyError, TypeError, ValueError, IndexError):
            cash_cents = 0
        
        return {
            "closing_cash": cash_cents,
            "closed_by": self.ed_closed_by.text().strip(),
        }


class TicketDetailDialog(QDialog):
    """Dialog reutilizable para mostrar detalles de ticket con opción de reimpresión."""

    def __init__(self, parent=None, ticket_id: int | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(600)
        
        self.ticket_id = ticket_id
        self.ticket_details = None
        
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(24)

        # Header
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char('receipt') or '🧾')
        icon.setObjectName("IconLabel")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")

        title = QLabel("DETALLES DEL TICKET")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setStyleSheet("""
            QTextEdit {
                border-radius: 12px;
                padding: 16px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        root.addWidget(self.txt_details, 1)

        # Actions
        row = QHBoxLayout()
        row.setSpacing(16)

        btn_cancel = QPushButton("Cerrar")
        btn_cancel.setMinimumHeight(60)
        btn_cancel.clicked.connect(self.reject)

        from ui.icon_helper import get_icon_char
        btn_print = QPushButton(f"{get_icon_char('print') or '🖨'}  Reimprimir Ticket")
        btn_print.setMinimumHeight(60)
        btn_print.setProperty("role", "primary")
        btn_print.setStyleSheet("font-size: 16px; font-weight: 700;")
        btn_print.clicked.connect(self._reprint_ticket)

        row.addWidget(btn_cancel)
        row.addWidget(btn_print)
        root.addLayout(row)

        if ticket_id:
            self.load_ticket(ticket_id)

    def load_ticket(self, ticket_id: int):
        """Carga y muestra los detalles de un ticket."""
        from services.sales import cents_to_money
        
        self.ticket_id = ticket_id
        self.ticket_details = get_ticket_details(ticket_id)
        
        if not self.ticket_details:
            self.txt_details.setPlainText("Error: No se pudo cargar el ticket.")
            return
        
        lines = []
        lines.append("═" * 50)
        lines.append(f"  Ticket: {self.ticket_details['id']}")
        lines.append(f"  Cajero: {self.ticket_details['served_by'] or '—'}")
        lines.append(f"  Fecha:  {self.ticket_details['ts']}")
        if self.ticket_details['shift_id']:
            lines.append(f"  Turno:  #{self.ticket_details['shift_id']}")
        lines.append("═" * 50)
        lines.append("")
        lines.append("PRODUCTOS:")
        lines.append("")
        
        for item in self.ticket_details["items"]:
            qty_str = f"x{item.qty}".ljust(6)
            price_str = f"$ {cents_to_money(item.price)}".rjust(12)
            lines.append(f"{qty_str}{item.name}")
            lines.append(f"      {price_str}")
            lines.append("")
        
        lines.append("─" * 50)
        total_str = f"$ {cents_to_money(self.ticket_details['total'])}".rjust(12)
        lines.append(f"{'TOTAL:'.ljust(38)}{total_str}")
        
        paid = self.ticket_details.get('paid', 0)
        change_amt = self.ticket_details.get('change_amount', 0)
        if paid > 0:
            paid_str = f"$ {cents_to_money(paid)}".rjust(12)
            lines.append(f"{'Pago:'.ljust(38)}{paid_str}")
        if change_amt > 0:
            change_str = f"$ {cents_to_money(change_amt)}".rjust(12)
            lines.append(f"{'Cambio:'.ljust(38)}{change_str}")
        
        lines.append("═" * 50)
        
        self.txt_details.setPlainText("\n".join(lines))

    def _reprint_ticket(self):
        """Reimprimir el ticket actual."""
        if not self.ticket_details:
            QMessageBox.warning(self, "Error", "No hay ticket cargado.")
            return
        
        from drivers.printer_escpos import EscposPrinter
        
        ticket_text = render_ticket(
            self.ticket_details["items"],
            ticket_number=self.ticket_details["id"],
            timestamp=self.ticket_details["ts"],
            served_by=self.ticket_details["served_by"],
            paid_cents=self.ticket_details.get('paid', 0),
            change_cents=self.ticket_details.get('change_amount', 0)
        )
        
        try:
            EscposPrinter().print_text(ticket_text)
            QMessageBox.information(self, "Éxito", f"Ticket #{self.ticket_id} enviado a impresión.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al imprimir: {e}")


class ShiftPreviewDialog(QDialog):
    """Diálogo premium para vista previa de turno con lista de tickets clickeable."""

    def __init__(self, parent=None, shift_id: int | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        self.setMinimumWidth(750)
        self.setMinimumHeight(700)
        
        self.shift_id = shift_id
        self.shift_data = None
        self.shift_totals = None
        
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(24)

        # Header
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char('chart-bar') or '📊')
        icon.setObjectName("IconLabel")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 48px;")

        title = QLabel("VISTA PREVIA DEL TURNO")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 3px;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        if shift_id:
            info_panel = self._build_info_panel()
            root.addWidget(info_panel)

        lbl_tickets = QLabel("Tickets del turno:")
        lbl_tickets.setStyleSheet("font-weight: 600; font-size: 14px;")
        root.addWidget(lbl_tickets)
        
        self.lst_tickets = QListWidget()
        self.lst_tickets.setStyleSheet("""
            QListWidget {
                border-radius: 12px;
                padding: 8px;
                font-family: 'Courier New', monospace;
            }
            QListWidget::item {
                padding: 12px;
                border-radius: 6px;
                margin: 2px 0;
            }
            QListWidget::item:hover {
                cursor: pointer;
            }
        """)
        self.lst_tickets.itemDoubleClicked.connect(self._open_ticket_details)
        root.addWidget(self.lst_tickets, 1)
        
        hint = QLabel("💡 Haz doble clic en un ticket para ver detalles y reimprimir")
        hint.setStyleSheet("font-size: 12px; font-style: italic;")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

        btn_close = QPushButton("Cerrar")
        btn_close.setMinimumHeight(60)
        btn_close.clicked.connect(self.reject)
        root.addWidget(btn_close)

        if shift_id:
            self._load_data()

    def _build_info_panel(self) -> QWidget:
        """Construye panel de información del turno."""
        from services.shifts import shift_totals
        from services.sales import cents_to_money
        from core.db import connect
        
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, opened_at, opened_by, closed_at, closed_by, opening_cash, closing_cash 
            FROM shift WHERE id=?
        """, (int(self.shift_id),))
        sh = cur.fetchone()
        
        if not sh:
            lbl = QLabel("Error: Turno no encontrado")
            lbl.setStyleSheet("color: #ef4444;")
            return lbl
        
        self.shift_data = sh
        self.shift_totals = shift_totals(self.shift_id)
        
        
        panel = QWidget()
        
        grid = QGridLayout(panel)
        grid.setSpacing(12)
        grid.setContentsMargins(16, 16, 16, 16)
        
        lbl_turno = QLabel("Turno #:")
        lbl_turno.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_turno = QLabel(str(sh[0]))
        val_turno.setStyleSheet("color: #f8fafc; font-size: 14px;")
        
        estado = "CERRADO" if sh[3] else "EN CURSO"
        color_estado = "#ef4444" if sh[3] else "#10b981"
        lbl_estado = QLabel("Estado:")
        lbl_estado.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_estado = QLabel(estado)
        val_estado.setStyleSheet(f"color: {color_estado}; font-weight: 700; font-size: 14px;")
        
        grid.addWidget(lbl_turno, 0, 0)
        grid.addWidget(val_turno, 0, 1)
        grid.addWidget(lbl_estado, 0, 2)
        grid.addWidget(val_estado, 0, 3)
        
        lbl_apertura = QLabel("Apertura:")
        lbl_apertura.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_apertura = QLabel(sh[1] or "-")
        val_apertura.setStyleSheet("color: #f8fafc;")
        
        lbl_cierre = QLabel("Cierre:")
        lbl_cierre.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_cierre = QLabel(sh[3] or "EN CURSO")
        val_cierre.setStyleSheet("color: #f8fafc;")
        
        grid.addWidget(lbl_apertura, 1, 0)
        grid.addWidget(val_apertura, 1, 1)
        grid.addWidget(lbl_cierre, 1, 2)
        grid.addWidget(val_cierre, 1, 3)
        
        if sh[2]:  # opened_by
            lbl_abierto = QLabel("Abierto por:")
            lbl_abierto.setStyleSheet("color: #94a3b8; font-weight: 600;")
            val_abierto = QLabel(sh[2])
            val_abierto.setStyleSheet("color: #f8fafc;")
            grid.addWidget(lbl_abierto, 2, 0)
            grid.addWidget(val_abierto, 2, 1)
        
        if sh[4]:  # closed_by
            lbl_cerrado = QLabel("Cerrado por:")
            lbl_cerrado.setStyleSheet("color: #94a3b8; font-weight: 600;")
            val_cerrado = QLabel(sh[4])
            val_cerrado.setStyleSheet("color: #f8fafc;")
            grid.addWidget(lbl_cerrado, 2, 2)
            grid.addWidget(val_cerrado, 2, 3)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #2a2a37;")
        grid.addWidget(line, 3, 0, 1, 4)
        
        lbl_tickets = QLabel("Tickets:")
        lbl_tickets.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_tickets = QLabel(str(self.shift_totals['tickets']))
        val_tickets.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: 700;")
        
        lbl_items = QLabel("Artículos:")
        lbl_items.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_items = QLabel(str(self.shift_totals['items']))
        val_items.setStyleSheet("color: #f8fafc; font-size: 16px; font-weight: 700;")
        
        grid.addWidget(lbl_tickets, 4, 0)
        grid.addWidget(val_tickets, 4, 1)
        grid.addWidget(lbl_items, 4, 2)
        grid.addWidget(val_items, 4, 3)
        
        lbl_total = QLabel("Total Ventas:")
        lbl_total.setStyleSheet("color: #94a3b8; font-weight: 600;")
        val_total = QLabel(f"$ {cents_to_money(self.shift_totals['total'])}")
        val_total.setStyleSheet("color: #10b981; font-size: 18px; font-weight: 700;")
        
        grid.addWidget(lbl_total, 5, 0)
        grid.addWidget(val_total, 5, 1, 1, 3)
        
        return panel

    def _load_data(self):
        """Carga lista de tickets del turno."""
        from core.db import connect
        from services.sales import cents_to_money
        
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, ts, total 
            FROM ticket 
            WHERE shift_id=? 
            ORDER BY id
        """, (int(self.shift_id),))
        tickets = cur.fetchall()
        
        self.lst_tickets.clear()
        
        for t in tickets:
            ticket_id = t[0]
            timestamp = t[1]
            total = t[2]
            
            try:
                if " " in timestamp:
                    hora = timestamp.split(" ")[1][:5]
                elif "T" in timestamp:
                    hora = timestamp.split("T")[1][:5]
                else:
                    hora = timestamp[-8:-3]
            except (KeyError, TypeError, ValueError, IndexError):
                hora = "??:??"
            
            text = f"#{ticket_id:<6} | {hora} | $ {cents_to_money(total):>10}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, ticket_id)
            self.lst_tickets.addItem(item)

    def _open_ticket_details(self, item):
        """Abre TicketDetailDialog para el ticket seleccionado."""
        ticket_id = item.data(Qt.UserRole)
        if ticket_id:
            dlg = TicketDetailDialog(self, ticket_id=ticket_id)
            dlg.exec()




# --- Loading Overlay ---
class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LoadingOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.hide()
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        
        container = QFrame()
        container.setObjectName("LoadingContainer")
        container.setFixedSize(280, 160)
        container.setStyleSheet("""
            QFrame#LoadingContainer {
                background: palette(window);
                border: 2px solid palette(highlight);
                border-radius: 24px;
            }
        """)
        
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(24, 24, 24, 24)
        c_layout.setSpacing(16)
        
        from ui.icon_helper import get_icon_char
        icon = QLabel(get_icon_char("spinner") or "⏳")
        icon.setStyleSheet("font-size: 32px; color: palette(highlight);")
        icon.setAlignment(Qt.AlignCenter)
        
        msg = QLabel("Aplicando tema...")
        msg.setStyleSheet("font-weight: 700; font-size: 16px;")
        msg.setAlignment(Qt.AlignCenter)
        
        c_layout.addWidget(icon)
        c_layout.addWidget(msg)
        layout.addWidget(container)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

    def show_event(self):
        if not self.parent():
            return
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

class AdminWindow(QMainWindow):
    """Premium Administration Interface"""
    
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowTitle(i18n.t("admin_title"))
        self._osk_guard = False
        self._osk_filter = _OskFocusFilter(self)
        self._pinpad_guard = False
        self._keypad_filter = _PinKeypadFocusFilter(self)
        self._prod_dialog_open = False
        self._prod_save_in_progress = False

        # ─── Header Bar ───────────────────────────────────────────────────
        top_wrap = QWidget()
        top_wrap.setStyleSheet("background: transparent;")
        top = QHBoxLayout(top_wrap)
        top.setContentsMargins(24, 20, 24, 16)
        top.setSpacing(16)

        from ui.icon_helper import get_icon_char
        self.title_lbl = QLabel(f"{get_icon_char('gear') or '⚙'}  " + (i18n.t("admin_title") or "Administración"))
        self.title_lbl.setObjectName("SectionTitle")
        self.title_lbl.setStyleSheet("""
            font-size: 26px;
            font-weight: 700;
        """)

        self.lang_btn = QPushButton(i18n.lang_switch_label())
        self.lang_btn.setMinimumSize(72, 48)
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)

        from ui.icon_helper import get_icon_char
        self.btn_close = QPushButton(f"{get_icon_char('arrow-left') or '←'}  " + (i18n.t("exit") or "Salir"))
        self.btn_close.setMinimumHeight(52)
        self.btn_close.setProperty("role", "danger")
        self.btn_close.setStyleSheet("""
            QPushButton {
                padding-left: 20px;
                padding-right: 20px;
            }
        """)
        self.btn_close.clicked.connect(self._exit_to_kiosk)

        top.addWidget(self.title_lbl)
        top.addStretch(1)
        top.addWidget(self.lang_btn)
        top.addWidget(self.btn_close)

        # ─── Tab Widget ───────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setObjectName("AdminTabs")
        from ui.icon_helper import get_icon_char
        self.tabs.addTab(self._tab_security(), f"{get_icon_char('lock') or '🔐'}  " + i18n.t("tab_security"))
        self.tabs.addTab(self._tab_devices(), f"{get_icon_char('print') or '🖨'}  " + i18n.t("tab_devices"))
        self.tabs.addTab(self._tab_store(), f"{get_icon_char('store') or '🏪'}  " + i18n.t("tab_store"))
        self.tabs.addTab(self._tab_products(), f"{get_icon_char('box') or '📦'}  " + i18n.t("tab_products"))
        self.tabs.addTab(self._tab_shifts(), f"{get_icon_char('chart-bar') or '📊'}  " + (i18n.t("tab_shifts") or "Turnos"))
        self.tabs.addTab(self._tab_tickets(), f"{get_icon_char('receipt') or '🧾'}  " + (i18n.t("tickets") if i18n.t("tickets") != "tickets" else "Tickets"))
        self.tabs.addTab(self._tab_reports(), f"{get_icon_char('chart-line') or '📈'}  " + i18n.t("tab_reports"))
        self.tabs.addTab(self._tab_themes(), f"{get_icon_char('palette') or '🎨'}  " + i18n.t("tab_themes"))
        self.tabs.addTab(self._tab_system(), f"{get_icon_char('computer') or '💻'}  " + i18n.t("tab_system"))

        # ─── Main Container ───────────────────────────────────────────────
        wrap = QWidget()
        wrap.setObjectName("GridPanel")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(24)
        lay.addWidget(top_wrap)
        lay.addWidget(self.tabs)
        self.setCentralWidget(wrap)
        self.toast_mgr = ToastManager(self)
        self.loading_overlay = LoadingOverlay(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.toast_mgr.sync_geometry()

    def _toast(self, message: str, *, level: str = "info", duration_ms: int = 3600):
        self.toast_mgr.show_toast(message, level=level, duration_ms=duration_ms)

    def _mark_field_state(self, widget: QWidget, state: str | None):
        widget.setProperty("state", state or "")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # ---------- Security
    def _tab_security(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.pin_in = QLineEdit()
        self.pin_in.setEchoMode(QLineEdit.Password)
        self.pin_new = QLineEdit()
        self.pin_new.setEchoMode(QLineEdit.Password)
        self.pin_new2 = QLineEdit()
        self.pin_new2.setEchoMode(QLineEdit.Password)
        btn_check = QPushButton(i18n.t("validate_pin"))
        btn_check.clicked.connect(self._check_pin)
        btn_set = QPushButton(i18n.t("change_pin"))
        btn_set.clicked.connect(self._set_pin)
        f.addRow(i18n.t("current_pin"), self.pin_in)
        f.addRow(btn_check)
        f.addRow(QLabel(i18n.t("change_pin")))
        f.addRow(i18n.t("new_pin"), self.pin_new)
        f.addRow(i18n.t("repeat_pin"), self.pin_new2)
        f.addRow(btn_set)

        for wle in (self.pin_in, self.pin_new, self.pin_new2):
            wle.installEventFilter(self._keypad_filter)
        return w

    def _check_pin(self):
        if check_admin_pin(self.pin_in.text() or ""):
            QMessageBox.information(self, "PIN", i18n.t("pin_ok"))
        else:
            QMessageBox.critical(self, "PIN", i18n.t("pin_bad"))

    def _set_pin(self):
        new1, new2 = self.pin_new.text(), self.pin_new2.text()
        if not new1 or new1 != new2:
            QMessageBox.warning(self, "PIN", i18n.t("pins_mismatch"))
            return
        ph = PasswordHasher()
        h = ph.hash(new1)
        data = load_config()
        data.setdefault("security", {})["admin_pin_hash"] = h
        save_config(data)
        QMessageBox.information(self, "PIN", i18n.t("pin_saved"))

    # ---------- Devices
    def _tab_devices(self) -> QWidget:
        w = QWidget()
        root = QVBoxLayout(w)
        root.setSpacing(10)
        root.setContentsMargins(10, 10, 10, 10)
        self.dev_tabs = QTabWidget()

        simple = QWidget()
        g = QGridLayout(simple)
        g.setColumnStretch(1, 1)
        self.combo_printers = QComboBox()
        self.lbl_desc = QLabel("—")
        self.lbl_desc.setWordWrap(True)
        btn_scan = QPushButton(i18n.t("scan_usb_printers"))
        btn_scan.clicked.connect(self._scan_printers)
        btn_save = QPushButton(i18n.t("save"))
        btn_save.clicked.connect(self._save_from_simple)
        btn_test = QPushButton(i18n.t("test_print"))
        btn_test.clicked.connect(self._test_print)
        btn_cash = QPushButton(i18n.t("open_drawer"))
        btn_cash.clicked.connect(self._open_drawer)
        g.addWidget(QLabel(i18n.t("select_printer")), 0, 0)
        g.addWidget(self.combo_printers, 0, 1)
        g.addWidget(btn_scan, 0, 2)
        g.addWidget(QLabel(i18n.t("description")), 1, 0)
        g.addWidget(self.lbl_desc, 1, 1, 1, 2)
        g.addWidget(btn_save, 2, 0)
        g.addWidget(btn_test, 2, 1)
        g.addWidget(btn_cash, 2, 2)

        advanced = QWidget()
        f = QFormLayout(advanced)
        self.vendor_id = QLineEdit()
        self.product_id = QLineEdit()
        self.iface_spin = QSpinBox()
        self.iface_spin.setRange(0, 9)
        self.out_ep = QLineEdit()
        self.in_ep = QLineEdit()
        cur = load_config()
        pr = cur.get("hardware", {}).get("printer", {})
        self.vendor_id.setText(_fmt_hex(pr.get("vendor_id")))
        self.product_id.setText(_fmt_hex(pr.get("product_id")))
        self.iface_spin.setValue(int(pr.get("interface", 0)))
        self.out_ep.setText(_fmt_hex(pr.get("out_ep")))
        self.in_ep.setText(_fmt_hex(pr.get("in_ep")))
        f.addRow(i18n.t("vendor_id"), self.vendor_id)
        f.addRow(i18n.t("product_id"), self.product_id)
        f.addRow(i18n.t("interface"), self.iface_spin)
        f.addRow(i18n.t("endpoint_out"), self.out_ep)
        f.addRow(i18n.t("endpoint_in"), self.in_ep)
        btn_save_adv = QPushButton(i18n.t("save_advanced"))
        btn_save_adv.clicked.connect(self._save_printer_advanced)
        f.addRow(btn_save_adv)

        self.dev_tabs.addTab(simple, i18n.t("printer_simple_title"))
        self.dev_tabs.addTab(advanced, i18n.t("advanced"))
        root.addWidget(self.dev_tabs)
        self._prefill_printer_combo_from_config(pr)
        self.combo_printers.currentIndexChanged.connect(self._on_printer_changed)
        return w

    def _prefill_printer_combo_from_config(self, pr: dict):
        self.combo_printers.clear()
        label = i18n.t("preferred_from_config")
        data = {
            "vid": _fmt_hex(pr.get("vendor_id")),
            "pid": _fmt_hex(pr.get("product_id")),
            "manufacturer": "",
            "product": "",
            "interface": int(pr.get("interface", 0)),
            "eps_out": [int(pr.get("out_ep"))] if pr.get("out_ep") is not None else [],
            "eps_in": [int(pr.get("in_ep"))] if pr.get("in_ep") is not None else [],
        }
        self.combo_printers.addItem(label, data)
        self.lbl_desc.setText(i18n.t("use_scan_hint"))

    def _scan_printers(self):
        items = _scan_usb_printers()
        if not items:
            QMessageBox.warning(self, i18n.t("devices"), i18n.t("no_printers"))
            return
        cur = load_config().get("hardware", {}).get("printer", {})
        self._prefill_printer_combo_from_config(cur)
        for d in items:
            vendor = d.get("manufacturer") or "USB"
            name = d.get("product") or "Device"
            label = f"{vendor} {name}  (VID:PID {d['vid']}:{d['pid']})"
            self.combo_printers.addItem(label, d)
        self.combo_printers.setCurrentIndex(1 if self.combo_printers.count() > 1 else 0)
        self._on_printer_changed(self.combo_printers.currentIndex())

    def _on_printer_changed(self, idx: int):
        d = self.combo_printers.currentData()
        if not d:
            return
        vendor = d.get("manufacturer") or "USB"
        name = d.get("product") or "Device"
        iface = d.get("interface", 0)
        out_eps = ", ".join(_fmt_hex(x) for x in d.get("eps_out", [])) or "—"
        in_eps = ", ".join(_fmt_hex(x) for x in d.get("eps_in", [])) or "—"
        self.lbl_desc.setText(
            f"{vendor} {name}\nInterfaz {iface}  •  EP OUT: {out_eps}  •  EP IN: {in_eps}"
        )

    def _save_from_simple(self):
        d = self.combo_printers.currentData()
        if not d:
            QMessageBox.warning(self, i18n.t("devices"), i18n.t("select_valid_printer"))
            return
        data = load_config()
        pr = data.setdefault("hardware", {}).setdefault("printer", {})
        pr["vendor_id"] = _intval(d.get("vid", "0"))
        pr["product_id"] = _intval(d.get("pid", "0"))
        pr["interface"] = int(d.get("interface", 0))
        pr["out_ep"] = int(d["eps_out"][0]) if d.get("eps_out") else None
        pr["in_ep"] = int(d["eps_in"][0]) if d.get("eps_in") else None
        save_config(data)
        self.vendor_id.setText(_fmt_hex(pr["vendor_id"]))
        self.product_id.setText(_fmt_hex(pr["product_id"]))
        self.iface_spin.setValue(int(pr["interface"]))
        self.out_ep.setText(_fmt_hex(pr["out_ep"]))
        self.in_ep.setText(_fmt_hex(pr["in_ep"]))
        QMessageBox.information(self, i18n.t("devices"), i18n.t("saved_ok"))

    def _save_printer_advanced(self):
        data = load_config()
        pr = data.setdefault("hardware", {}).setdefault("printer", {})
        pr["vendor_id"] = _intval(self.vendor_id.text())
        pr["product_id"] = _intval(self.product_id.text())
        pr["interface"] = int(self.iface_spin.value())
        out_txt = (self.out_ep.text() or "").strip()
        in_txt = (self.in_ep.text() or "").strip()
        pr["out_ep"] = _intval(out_txt) if out_txt else None
        pr["in_ep"] = _intval(in_txt) if in_txt else None
        save_config(data)
        QMessageBox.information(self, i18n.t("devices"), i18n.t("saved_adv_ok"))

    def _test_print(self):
        try:
            EscposPrinter().selftest()
            QMessageBox.information(self, i18n.t("printer"), "OK")
        except Exception as e:
            QMessageBox.critical(self, i18n.t("printer"), f"Error: {e}")

    def _open_drawer(self):
        try:
            EscposPrinter().open_drawer()
            QMessageBox.information(self, i18n.t("drawer"), "OK")
        except Exception as e:
            QMessageBox.critical(self, i18n.t("drawer"), f"Error: {e}")

    # ---------- Store
    def _tab_store(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        s = load_config()
        st = s.get("store", {})
        self.name = QLineEdit(st.get("name", ""))
        self.rfc = QLineEdit(st.get("rfc", ""))
        self.header = QLineEdit(st.get("ticket_header", ""))
        self.footer = QLineEdit(st.get("ticket_footer", ""))
        btn = QPushButton(i18n.t("save"))
        btn.clicked.connect(self._save_store)
        f.addRow(i18n.t("store_name"), self.name)
        f.addRow(i18n.t("store_rfc"), self.rfc)
        f.addRow(i18n.t("ticket_header"), self.header)
        f.addRow(i18n.t("ticket_footer"), self.footer)
        f.addRow(btn)

        for wle in (self.name, self.rfc, self.header, self.footer):
            wle.installEventFilter(self._osk_filter)
        return w

    def _save_store(self):
        data = load_config()
        data["store"] = {
            "name": self.name.text(),
            "rfc": self.rfc.text(),
            "ticket_header": self.header.text(),
            "ticket_footer": self.footer.text(),
        }
        save_config(data)
        QMessageBox.information(self, i18n.t("tab_store"), i18n.t("store_saved"))

    # ---------- Products (category + filters)
    def _tab_products(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        fl = QHBoxLayout()
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItem(i18n.t("all") or "Todas", "_ALL_")
        self.prod_search = QLineEdit()
        self.prod_search.setPlaceholderText(i18n.t("prod_search_placeholder"))
        btn_apply = QPushButton(i18n.t("prod_search") or "Buscar")
        btn_apply.clicked.connect(self._prod_refresh)
        btn_refresh = QPushButton(i18n.t("prod_refresh") or "Refrescar")
        btn_refresh.clicked.connect(self._prod_refresh_all)
        fl.addWidget(QLabel(i18n.t("category") or "Categoría"))
        fl.addWidget(self.cmb_cat, 0)
        fl.addWidget(self.prod_search, 1)
        fl.addWidget(btn_apply)
        fl.addWidget(btn_refresh)
        self.prod_search.installEventFilter(self._osk_filter)

        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(
            [
                i18n.t("prod_id"),
                i18n.t("prod_name"),
                i18n.t("prod_price"),
                i18n.t("prod_active"),
                i18n.t("prod_unit"),
                i18n.t("prod_allow_partial"),
                i18n.t("category") or "Categoría",
            ]
        )
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.verticalHeader().setVisible(False)
        
        # Configure responsive columns for 22" display
        from PySide6.QtWidgets import QHeaderView
        header = self.tbl.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID: auto-size
        header.setSectionResizeMode(1, QHeaderView.Stretch)           # Nombre: espacio restante
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Precio: auto-size
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Activo: auto-size
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Unidad: auto-size
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Decimal: auto-size
        header.setSectionResizeMode(6, QHeaderView.Interactive)       # Categoría: ajustable

        self.tbl.setColumnWidth(0, 60)
        self.tbl.setColumnWidth(2, 100)
        self.tbl.setColumnWidth(3, 90)
        self.tbl.setColumnWidth(4, 90)
        self.tbl.setColumnWidth(5, 100)
        self.tbl.setColumnWidth(6, 140)

        actions = QHBoxLayout()
        btn_new = QPushButton(i18n.t("prod_new"))
        btn_new.clicked.connect(self._prod_new)
        btn_edit = QPushButton(i18n.t("prod_edit"))
        btn_edit.clicked.connect(self._prod_edit)
        btn_toggle = QPushButton(i18n.t("prod_toggle"))
        btn_toggle.clicked.connect(self._prod_toggle)
        btn_delete = QPushButton(i18n.t("prod_delete"))
        btn_delete.clicked.connect(self._prod_delete)

        actions.addWidget(btn_new)
        actions.addWidget(btn_edit)
        actions.addWidget(btn_toggle)
        actions.addWidget(btn_delete)

        self.chk_enable_categories = QCheckBox(
            i18n.t("enable_categories") or "Habilitar Categorías"
        )
        self.chk_enable_categories.setChecked(is_categories_enabled())
        self.chk_enable_categories.toggled.connect(self._on_toggle_categories)
        actions.addWidget(self.chk_enable_categories)

        actions.addStretch(1)

        v.addLayout(fl)
        v.addWidget(self.tbl, 1)
        v.addLayout(actions)
        self._prod_refresh_all()
        return w

    def _current_prod_id(self) -> int | None:
        r = self.tbl.currentRow()
        if r is None or r < 0:
            return None
        item = self.tbl.item(r, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except Exception:
            return None

    def _fill_table(self, items: list[dict]):
        """Pinta la tabla y actualiza el combo de categorías a partir de los ítems visibles."""
        self.tbl.setRowCount(0)
        for p in items:
            cat = p.get("category") or "General"
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(str(p["id"])))
            self.tbl.setItem(r, 1, QTableWidgetItem(p["name"]))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"$ {cents_to_money(p['price'])}"))
            self.tbl.setItem(r, 3, QTableWidgetItem("Sí" if p.get("active") else "No"))
            self.tbl.setItem(r, 4, QTableWidgetItem(p.get("unit") or "pz"))
            self.tbl.setItem(r, 5, QTableWidgetItem("Sí" if p.get("allow_decimal") else "No"))
            self.tbl.setItem(r, 6, QTableWidgetItem(cat))

        try:
            all_items = list_products(q="", include_inactive=True)
        except Exception:
            all_items = items
        cats = sorted({(it.get("category") or "General") for it in (all_items or [])})
        cur_data = self.cmb_cat.currentData()
        self.cmb_cat.blockSignals(True)
        self.cmb_cat.clear()
        self.cmb_cat.addItem(i18n.t("all") or "Todas", "_ALL_")
        for c in cats:
            self.cmb_cat.addItem(c, c)
        if cur_data is not None:
            idx = max(
                0,
                next(
                    (
                        i
                        for i in range(self.cmb_cat.count())
                        if self.cmb_cat.itemData(i) == cur_data
                    ),
                    0,
                ),
            )
            self.cmb_cat.setCurrentIndex(idx)
        self.cmb_cat.blockSignals(False)

    def _prod_refresh(self):
        """Aplica búsqueda + filtro de categoría (si existe campo 'category'; si no, usa 'General')."""
        q = (self.prod_search.text() or "").strip()
        items = list_products(q=q, include_inactive=True)
        sel = self.cmb_cat.currentData()
        if sel and sel != "_ALL_":
            filtered = []
            for it in items:
                cat = (it.get("category") or "General")
                if cat == sel:
                    filtered.append(it)
            items = filtered
        self._fill_table(items)

    def _prod_refresh_all(self):
        items = list_products(q="", include_inactive=True)
        self._fill_table(items)

    def _prod_new(self):
        if self._prod_dialog_open:
            return
        self._prod_dialog_open = True
        try:
            dlg = ProductDialog(self)
            if dlg.exec():
                data = dlg.data()
                if not data:
                    return
                if self._prod_save_in_progress:
                    return
                self._prod_save_in_progress = True
                try:
                    # create_product(*, name, price_money, unit, allow_decimal, active, category, icon)
                    create_product(
                        name=data["name"],
                        price_money=data["price"],  # ya está en centavos; el wrapper acepta int/float/str
                        unit=data["unit"],
                        allow_decimal=data["allow_decimal"],
                        active=data["active"],
                        category=data["category"],
                        icon=data.get("icon", ""),
                    )
                finally:
                    self._prod_save_in_progress = False
                QMessageBox.information(self, i18n.t("tab_products"), i18n.t("prod_saved"))
                self._prod_refresh()
        finally:
            self._prod_dialog_open = False

    def _prod_edit(self):
        pid = self._current_prod_id()
        if pid is None:
            QMessageBox.warning(self, i18n.t("tab_products"), i18n.t("prod_err_select"))
            return
        prod = get_product(pid)
        if not prod:
            QMessageBox.warning(self, i18n.t("tab_products"), i18n.t("prod_err_select"))
            return
        dlg = ProductDialog(self, product=prod)
        if dlg.exec():
            data = dlg.data()
            if not data:
                return
            # update_product(product_id, *, name, price_money, unit, allow_decimal, active, category, icon)
            update_product(
                product_id=pid,
                name=data["name"],
                price_money=data["price"],
                unit=data["unit"],
                allow_decimal=data["allow_decimal"],
                active=data["active"],
                category=data["category"],
                icon=data.get("icon", ""),
            )
            QMessageBox.information(self, i18n.t("tab_products"), i18n.t("prod_saved"))
            self._prod_refresh()

    def _prod_toggle(self):
        pid = self._current_prod_id()
        if pid is None:
            QMessageBox.warning(self, i18n.t("tab_products"), i18n.t("prod_err_select"))
            return
        prod = get_product(pid)
        if not prod:
            QMessageBox.warning(self, i18n.t("tab_products"), i18n.t("prod_err_select"))
            return
        set_active(pid, not bool(prod.get("active")))
        QMessageBox.information(self, i18n.t("tab_products"), "OK")
        self._prod_refresh()

    def _prod_delete(self):
        pid = self._current_prod_id()
        if pid is None:
            QMessageBox.warning(self, i18n.t("tab_products"), i18n.t("prod_err_select"))
            return
        if (
            QMessageBox.question(
                self, i18n.t("tab_products"), i18n.t("prod_confirm_delete")
            )
            != QMessageBox.Yes
        ):
            return
        delete_product(pid)
        QMessageBox.information(self, i18n.t("tab_products"), i18n.t("prod_deleted"))
        self._prod_refresh()

    def _on_toggle_categories(self, checked: bool):
        set_categories_enabled(checked)
        if checked:
            QMessageBox.information(
                self,
                i18n.t("tab_products") or "Productos",
                i18n.t("categories_enabled") or "Categorías habilitadas. El kiosko mostrará submenús por categoría.",
            )
        else:
            QMessageBox.information(
                self,
                i18n.t("tab_products") or "Productos",
                i18n.t("categories_disabled") or "Categorías deshabilitadas. El kiosko mostrará un solo menú de productos.",
            )

    # ---------- Tickets
    def _tab_tickets(self) -> QWidget:
        """Tab para visualizar, buscar y reimprimir tickets de venta."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        search_row = QHBoxLayout()
        search_row.setSpacing(12)
        self.ed_ticket_search = QLineEdit()
        self.ed_ticket_search.setPlaceholderText("Buscar por número de ticket...")
        self.ed_ticket_search.setMinimumHeight(52)
        btn_search = QPushButton("Buscar")
        btn_search.setMinimumHeight(52)
        btn_search.clicked.connect(self._tickets_search)
        btn_clear = QPushButton("Limpiar")
        btn_clear.setMinimumHeight(52)
        btn_clear.clicked.connect(self._tickets_clear_search)
        search_row.addWidget(self.ed_ticket_search, 1)
        search_row.addWidget(btn_search)
        search_row.addWidget(btn_clear)
        v.addLayout(search_row)

        self.ed_ticket_search.installEventFilter(self._keypad_filter)

        self.tbl_tickets = QTableWidget(0, 5)
        self.tbl_tickets.setHorizontalHeaderLabels([
            "Ticket", "Fecha", "Empleado", "Turno", "Total"
        ])
        self.tbl_tickets.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_tickets.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_tickets.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_tickets.verticalHeader().setVisible(False)
        self.tbl_tickets.setAlternatingRowColors(False)
        
        self.tbl_tickets.itemDoubleClicked.connect(self._tickets_show_details_dialog)
        
        from PySide6.QtWidgets import QHeaderView
        header = self.tbl_tickets.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Ticket
        header.setSectionResizeMode(1, QHeaderView.Stretch)           # Fecha
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Empleado
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Turno
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Total
        
        v.addWidget(self.tbl_tickets, 1)

        page_row = QHBoxLayout()
        self.btn_tickets_prev = QPushButton("◀ Anterior")
        self.btn_tickets_prev.setMinimumHeight(40)
        self.btn_tickets_prev.clicked.connect(self._tickets_prev_page)
        self.lbl_tickets_page = QLabel("Página 1")
        self.lbl_tickets_page.setAlignment(Qt.AlignCenter)
        self.btn_tickets_next = QPushButton("Siguiente ▶")
        self.btn_tickets_next.setMinimumHeight(40)
        self.btn_tickets_next.clicked.connect(self._tickets_next_page)
        page_row.addWidget(self.btn_tickets_prev)
        page_row.addWidget(self.lbl_tickets_page, 1)
        page_row.addWidget(self.btn_tickets_next)
        v.addLayout(page_row)

        hint_label = QLabel("💡 Haz doble clic en un ticket para ver detalles y reimprimir")
        hint_label.setStyleSheet("font-size: 12px; font-style: italic;")
        hint_label.setAlignment(Qt.AlignCenter)
        v.addWidget(hint_label)

        self.tickets_offset = 0
        self.tickets_page_size = 15

        self._tickets_refresh()

        return w

    def _tickets_refresh(self, offset: int = 0):
        """Carga tickets desde la BD y llena la tabla."""
        self.tickets_offset = offset
        tickets = list_tickets(limit=self.tickets_page_size, offset=offset)
        
        self.tbl_tickets.setRowCount(0)
        for t in tickets:
            r = self.tbl_tickets.rowCount()
            self.tbl_tickets.insertRow(r)
            self.tbl_tickets.setItem(r, 0, QTableWidgetItem(str(t["id"])))
            self.tbl_tickets.setItem(r, 1, QTableWidgetItem(t["ts"] or ""))
            self.tbl_tickets.setItem(r, 2, QTableWidgetItem(t["served_by"] or "—"))
            self.tbl_tickets.setItem(r, 3, QTableWidgetItem(f"{t['shift_id']}" if t['shift_id'] else "—"))
            self.tbl_tickets.setItem(r, 4, QTableWidgetItem(f"$ {cents_to_money(t['total'])}"))
        
        page_num = (offset // self.tickets_page_size) + 1
        self.lbl_tickets_page.setText(f"Página {page_num}")
        
        self.btn_tickets_prev.setEnabled(offset > 0)
        self.btn_tickets_next.setEnabled(len(tickets) == self.tickets_page_size)

    def _tickets_search(self):
        """Busca ticket específico por número ingresado."""
        search_text = self.ed_ticket_search.text().strip()
        if not search_text:
            self._toast("Ingresa un número de ticket para buscar.", level="error")
            return
        
        try:
            ticket_id = int(search_text)
        except ValueError:
            self._toast("El número de ticket debe ser un número válido.", level="error")
            return
        
        ticket = search_tickets_by_id(ticket_id)
        if not ticket:
            self._toast(f"No se encontró el ticket #{ticket_id}.", level="error")
            self.tbl_tickets.setRowCount(0)
            return
        
        self.tbl_tickets.setRowCount(0)
        self.tbl_tickets.insertRow(0)
        self.tbl_tickets.setItem(0, 0, QTableWidgetItem(str(ticket["id"])))
        self.tbl_tickets.setItem(0, 1, QTableWidgetItem(ticket["ts"] or ""))
        self.tbl_tickets.setItem(0, 2, QTableWidgetItem(ticket["served_by"] or "—"))
        self.tbl_tickets.setItem(0, 3, QTableWidgetItem(f"{ticket['shift_id']}" if ticket['shift_id'] else "—"))
        self.tbl_tickets.setItem(0, 4, QTableWidgetItem(f"$ {cents_to_money(ticket['total'])}"))
        
        self.btn_tickets_prev.setEnabled(False)
        self.btn_tickets_next.setEnabled(False)
        self.lbl_tickets_page.setText("Búsqueda")

    def _tickets_clear_search(self):
        """Limpia la búsqueda y regresa a mostrar todos los tickets."""
        self.ed_ticket_search.clear()
        self._tickets_refresh(0)

    def _tickets_show_details_dialog(self):
        """Muestra el diálogo de detalles del ticket seleccionado."""
        row = self.tbl_tickets.currentRow()
        if row < 0:
            return
        
        ticket_id_item = self.tbl_tickets.item(row, 0)
        if not ticket_id_item:
            return
        
        try:
            ticket_id = int(ticket_id_item.text())
        except ValueError:
            return
        
        dlg = TicketDetailDialog(self, ticket_id=ticket_id)
        dlg.exec()

    def _tickets_next_page(self):
        """Navegar a la siguiente página de tickets."""
        new_offset = self.tickets_offset + self.tickets_page_size
        self._tickets_refresh(new_offset)

    def _tickets_prev_page(self):
        """Navegar a la página anterior de tickets."""
        new_offset = max(0, self.tickets_offset - self.tickets_page_size)
        self._tickets_refresh(new_offset)


    # ---------- Reports (date range + email)
    def _tab_reports(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(14)

        v.addWidget(QLabel(i18n.t("send_mail") or "Enviar reporte"))

        # Main Layout: Left (Inputs) | Right (Action)
        main_layout = QHBoxLayout()
        main_layout.setSpacing(16)

        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Row 1: Dates
        loc = QLocale(QLocale.Spanish) if i18n.current_lang() == "es" else QLocale(QLocale.English)
        
        dates_row = QHBoxLayout()
        self.date_from = QDateEdit()
        self.date_from.setLocale(loc)
        self.date_from.setMinimumHeight(56)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setDate(QDate.currentDate().addDays(-7))
        self.date_from.removeEventFilter(self._osk_filter)

        self.date_to = QDateEdit()
        self.date_to.setLocale(loc)
        self.date_to.setMinimumHeight(56)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setDate(QDate.currentDate())
        self.date_to.removeEventFilter(self._osk_filter)

        dates_row.addWidget(QLabel(i18n.t("dates_from") or "Desde"))
        dates_row.addWidget(self.date_from, 1)
        dates_row.addWidget(QLabel(i18n.t("dates_to") or "Hasta"))
        dates_row.addWidget(self.date_to, 1)
        
        left_col.addLayout(dates_row)

        # Row 2: Emails + Recent ComboBox
        mail_row2 = QHBoxLayout()
        mail_row2.setSpacing(8)
        
        self.ed_emails = QLineEdit()
        self.ed_emails.setPlaceholderText(i18n.t("emails_placeholder") or "usuario@gmail.com, usuario2@gmail.com, usuario3@gmail.com, ...")
        self.ed_emails.setMinimumHeight(42)
        
        lbl_recent = QLabel(i18n.t("recent_emails") or "Recientes")
        lbl_recent.setStyleSheet("font-weight: 600;")
        
        self.cb_recent = QComboBox()
        self.cb_recent.setMinimumHeight(42)
        self.cb_recent.setMinimumWidth(180)
        
        btn_add_recent = QPushButton("+")
        btn_add_recent.setFixedSize(60, 40)
        btn_add_recent.setToolTip("Agregar seleccionado")
        btn_add_recent.setProperty("role", "primary")
        btn_add_recent.setStyleSheet("font-weight: bold; border-radius: 6px;")
        btn_add_recent.clicked.connect(self._add_recent_email_from_combo)
        
        btn_del_recent = QPushButton("x")
        btn_del_recent.setFixedSize(60, 40)
        btn_del_recent.setToolTip("Eliminar seleccionado")
        btn_del_recent.setProperty("role", "danger")
        btn_del_recent.setStyleSheet("font-weight: bold; border-radius: 6px;")
        btn_del_recent.clicked.connect(self._remove_recent_email_from_combo)

        mail_row2.addWidget(self.ed_emails, 1) # Stretch
        mail_row2.addWidget(lbl_recent)
        mail_row2.addWidget(self.cb_recent)
        mail_row2.addWidget(btn_add_recent)
        mail_row2.addWidget(btn_del_recent)
        
        left_col.addLayout(mail_row2)
        main_layout.addLayout(left_col, 3) # Take 3/4 space

        icon_char = get_icon_char("envelope") or "📧"
        btn_send = QPushButton(f" {icon_char} \n{i18n.t('send_mail') or 'Enviar'}")
        btn_send.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        btn_send.setMaximumWidth(180)
        btn_send.setProperty("role", "primary")
        btn_send.setStyleSheet("""
            QPushButton {
                font-size: 16px;
                font-weight: 700;
                border-radius: 12px;
                padding: 10px;
                text-align: center;
            }
        """)
        btn_send.clicked.connect(self._send_mail)
        
        main_layout.addWidget(btn_send, 1) # Take 1/4 space

        v.addLayout(main_layout)

        self._reload_recent_combo()

        self.ed_emails.installEventFilter(self._osk_filter)

        v.addWidget(QLabel(i18n.t("print_shift_report") or "Imprimir reporte de turno"))

        self.list_shifts = QListWidget()
        self.list_shifts.setObjectName("ShiftList")
        self.list_shifts.setSpacing(6)
        self.list_shifts.setUniformItemSizes(True)
        v.addWidget(QLabel(i18n.t("week_shifts") or "Turnos de la semana"))
        self.shifts_stack = QStackedLayout()
        self.lbl_shifts_empty = QLabel(
            i18n.t("no_shifts")
            or "Sin turnos recientes. Abre un turno para poder imprimir reportes."
        )
        self.lbl_shifts_empty.setObjectName("EmptyStateLabel")
        self.lbl_shifts_empty.setAlignment(Qt.AlignCenter)
        self.lbl_shifts_empty.setWordWrap(True)
        self.shifts_stack.addWidget(self.list_shifts)
        self.shifts_stack.addWidget(self.lbl_shifts_empty)
        v.addLayout(self.shifts_stack, 1)

        self.btn_print = QPushButton(
            i18n.t("print_shift_report") or "Imprimir reporte del turno"
        )
        self.btn_print.clicked.connect(self._print_selected_shift)
        v.addWidget(self.btn_print)

        self._reload_week_shifts()

        return w

    def _shift_label_text(self) -> str:
        sh = current_shift()
        if not sh:
            return i18n.t("shift_label_closed")
        sums = shift_totals(sh["id"])
        opened_by = sh.get("opened_by") or ""
        base = i18n.t(
            "shift_label_open_fmt",
            id=sh["id"],
            opened_at=sh["opened_at"],
            tickets=sums["tickets"],
            total=cents_to_money(sums["total"])
        )
        if opened_by:
            return f"{base}  •  Empleado: {opened_by}"
        return base

    def _open_shift(self):
        emp_code = None
        if hasattr(self, "cmb_shift_employee"):
            emp_code = self.cmb_shift_employee.currentData() or None

        if not emp_code:
            self._toast(
                "Selecciona el empleado que abre el turno.", level="error"
            )
            return

        open_shift(opened_by=emp_code, opening_cash=0)

        self.lbl_shift.setText(self._shift_label_text())
        if hasattr(self, "list_shifts"):
            self._reload_week_shifts()
        self._toast("Turno abierto.", level="success")

    def _do_preview(self):
        """Muestra vista previa del turno actual con lista de tickets clickeable."""
        sh = current_shift()
        if not sh:
            self._toast("No hay turno abierto.", level="error")
            return
        
        dlg = ShiftPreviewDialog(self, shift_id=sh["id"])
        dlg.exec()

    def _do_close(self):
        """
        Cierra el turno actual con diálogo de conteo de efectivo,
        genera reporte resumido e imprime.
        """
        sh = current_shift()
        if not sh:
            self._toast("No hay turno abierto.", level="error")
            return

        dlg = ShiftCloseDialog(self, shift_info=sh)
        if dlg.exec() != QDialog.Accepted:
            return
        
        close_data = dlg.data()
        closing_cash = close_data.get("closing_cash", 0)
        closed_by = close_data.get("closed_by", "")

        try:
            close_shift(closed_by=closed_by, closing_cash=closing_cash)
        except Exception as e:
            QMessageBox.critical(
                self,
                i18n.t("tab_shifts") or "Turnos",
                f"Error al cerrar turno: {e}"
            )
            return

        txt = render_shift_text(sh["id"], detailed=False)

        try:
            EscposPrinter().print_text(txt)
            self._toast(
                f"Turno #{sh['id']} cerrado e impreso.", level="success"
            )
        except Exception as e:
            QMessageBox.information(
                self,
                "Reporte de Turno",
                txt[:2000] + ("..." if len(txt) > 2000 else "")
            )
            self._toast(
                f"Turno cerrado. Error al imprimir: {e}", level="error"
            )

        self.lbl_shift.setText(self._shift_label_text())

        if hasattr(self, "list_shifts"):
            self._reload_week_shifts()

    def _reload_recent_combo(self):
        """Recarga el combobox de correos recientes."""
        self.cb_recent.clear()
        self.cb_recent.addItem("") # Opción vacía inicial
        for e in recent_emails():
            self.cb_recent.addItem(e)

    def _add_recent_email_from_combo(self):
        """Agrega el email seleccionado en el combo al campo de texto."""
        email = self.cb_recent.currentText().strip()
        if not email:
            return

        current = self.ed_emails.text().strip()
        if current:
            emails_list = [e.strip() for e in current.split(",") if e.strip()]
            if email not in emails_list:
                emails_list.append(email)
            self.ed_emails.setText(", ".join(emails_list))
        else:
            self.ed_emails.setText(email)
            
        self.ed_emails.setStyleSheet("border: 1px solid #10b981;")
        QTimer.singleShot(1000, lambda: self.ed_emails.setStyleSheet(""))

    def _remove_recent_email_from_combo(self):
        """Elimina el email seleccionado de la lista de recientes."""
        email = self.cb_recent.currentText().strip()
        if not email:
            return
            
        from services.emailer import remove_recent_email
        remove_recent_email(email)
        self._reload_recent_combo()
        self._toast("Email eliminado", level="warning")


    def _send_mail(self):
        from datetime import datetime
        from core.db import connect
        from services.emailer import _create_html_email_report
        
        df = self.date_from.date().toString("yyyy-MM-dd")
        dt = self.date_to.date().toString("yyyy-MM-dd")
        rec_raw = (self.ed_emails.text() or "").strip()
        recipients = [x.strip() for x in rec_raw.split(",") if x.strip()]
        
        if not recipients:
            self._mark_field_state(self.ed_emails, "error")
            self._toast(
                "Correos requeridos.", level="error", duration_ms=4200
            )
            return
        
        if self.date_from.date() > self.date_to.date():
            self._toast(
                "La fecha inicial debe ser anterior a la fecha final.", level="error", duration_ms=4200
            )
            return
        self._mark_field_state(self.ed_emails, None)
        
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(DISTINCT t.id) as tickets,
                SUM(ti.quantity) as items,
                SUM(t.total) as total_cents
            FROM ticket t
            LEFT JOIN ticket_item ti ON ti.ticket_id = t.id
            WHERE DATE(t.ts) BETWEEN DATE(?) AND DATE(?)
        """, (df, dt))
        row = cur.fetchone()
        stats = {
            'tickets': row[0] or 0,
            'items': int(row[1] or 0),
            'total_cents': row[2] or 0
        }
        
        html_body = _create_html_email_report(df, dt, stats)
        plain_body = render_range_text(df, dt)
        
        date_from_obj = datetime.strptime(df, "%Y-%m-%d")
        date_to_obj = datetime.strptime(dt, "%Y-%m-%d")
        from_str = date_from_obj.strftime("%d-%b-%Y")  # 01-Feb-2026
        to_str = date_to_obj.strftime("%d-%b-%Y")  # 07-Feb-2026
        filename = f"Tottem_Ventas_{from_str}_al_{to_str}.csv"
        
        att = [
            (filename, csv_sales_detailed_bytes(df, dt)),
        ]
        
        ok, msg = send_mail(
            subject=f"Reporte de Ventas {date_from_obj.strftime('%d/%m/%Y')} - {date_to_obj.strftime('%d/%m/%Y')}",
            body=plain_body,
            recipients=recipients,
            attachments=att,
            html_body=html_body
        )
        
        if ok:
            self._mark_field_state(self.ed_emails, "success")
            self._toast(
                i18n.t("report_sent_ok") or "Reporte enviado.", level="success"
            )
        else:
            self._toast(
                i18n.t("report_sent_err", err=msg)
                or f"Error al enviar reporte: {msg}",
                level="error",
                duration_ms=5200
            )

    def _reload_week_shifts(self):
        self.list_shifts.clear()
        for sh in list_shifts_since(7):
            label = (
                f"#{sh['id']}  {sh['opened_at']}  "
                f"{'(cerrado)' if sh['closed_at'] else '(abierto)'}"
            )
            self.list_shifts.addItem(label)
        self._update_shift_empty_state()

    def _update_shift_empty_state(self):
        has_rows = self.list_shifts.count() > 0
        if hasattr(self, "shifts_stack"):
            self.shifts_stack.setCurrentWidget(
                self.list_shifts if has_rows else self.lbl_shifts_empty
            )
        if hasattr(self, "btn_print"):
            self.btn_print.setEnabled(has_rows)

    def _print_selected_shift(self):
        row = self.list_shifts.currentRow()
        if row is None or row < 0:
            self._toast(i18n.t("select_shift") or "Selecciona un turno.", level="error")
            return
        text = self.list_shifts.item(row).text()
        try:
            sid = int(text.split()[0].lstrip("#"))
        except Exception:
            self._toast(i18n.t("select_shift") or "Selecciona un turno.", level="error")
            return
        try:
            report = render_shift_text(sid)
            EscposPrinter().print_text(report)
            self._toast("Reporte de turno enviado a impresión.", level="success")
        except Exception as e:
            self._toast(f"Error al imprimir reporte: {e}", level="error")

    # ---------- Shifts + Employees
    def _tab_shifts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        self.lbl_shift = QLabel(self._shift_label_text())
        self.lbl_shift.setWordWrap(True)
        v.addWidget(self.lbl_shift)

        emp_row = QHBoxLayout()
        emp_row.addWidget(QLabel(i18n.t("emp_for_shift") or "Empleado del turno"))
        self.cmb_shift_employee = QComboBox()
        self._reload_shift_employees()
        emp_row.addWidget(self.cmb_shift_employee, 1)
        v.addLayout(emp_row)

        row1 = QHBoxLayout()
        btn_open = QPushButton(i18n.t("open_shift") or "Abrir turno")
        btn_open.clicked.connect(self._open_shift)
        btn_prev = QPushButton(i18n.t("preview_shift") or "Vista previa")
        btn_prev.clicked.connect(self._do_preview)
        btn_close = QPushButton(i18n.t("close_shift") or "Cerrar turno")
        btn_close.clicked.connect(self._do_close)
        for b in (btn_open, btn_prev, btn_close):
            b.setMinimumHeight(40)
        row1.addWidget(btn_open)
        row1.addWidget(btn_prev)
        row1.addWidget(btn_close)
        v.addLayout(row1)

        v.addWidget(QLabel(i18n.t("employees_title") or "Empleados"))

        self.tbl_employees = QTableWidget(0, 5)
        self.tbl_employees.setHorizontalHeaderLabels(
            [
                "ID",
                i18n.t("emp_no") or "No. empleado",
                i18n.t("emp_name") or "Nombre completo",
                i18n.t("emp_phone") or "Contacto",
                i18n.t("emp_active") or "Activo",
            ]
        )
        self.tbl_employees.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_employees.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_employees.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_employees.verticalHeader().setVisible(False)
        
        from PySide6.QtWidgets import QHeaderView
        header = self.tbl_employees.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # ID: auto-size
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # No. Empleado: auto-size
        header.setSectionResizeMode(2, QHeaderView.Stretch)           # Nombre: espacio restante
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Contacto: auto-size
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Activo: auto-size
        self.tbl_employees.setColumnWidth(4, 70)
        v.addWidget(self.tbl_employees, 2)

        row_emp = QHBoxLayout()
        btn_emp_new = QPushButton(i18n.t("emp_new") or "Nuevo")
        btn_emp_edit = QPushButton(i18n.t("emp_edit") or "Editar")
        btn_emp_toggle = QPushButton(
            i18n.t("emp_toggle") or "Activar / Desactivar"
        )
        btn_emp_delete = QPushButton(i18n.t("emp_delete") or "Eliminar")
        btn_emp_new.clicked.connect(self._emp_new)
        btn_emp_edit.clicked.connect(self._emp_edit)
        btn_emp_toggle.clicked.connect(self._emp_toggle)
        btn_emp_delete.clicked.connect(self._emp_delete)
        row_emp.addWidget(btn_emp_new)
        row_emp.addWidget(btn_emp_edit)
        row_emp.addWidget(btn_emp_toggle)
        row_emp.addWidget(btn_emp_delete)
        row_emp.addStretch(1)
        v.addLayout(row_emp)

        self._emp_refresh()

        return w

    # ---------- Employees helpers ----------
    def _emp_refresh(self):
        self.tbl_employees.setRowCount(0)
        rows = list_employees()
        for r in rows:
            idx = self.tbl_employees.rowCount()
            self.tbl_employees.insertRow(idx)
            self.tbl_employees.setItem(idx, 0, QTableWidgetItem(str(r["id"])))
            self.tbl_employees.setItem(
                idx, 1, QTableWidgetItem(r.get("emp_no", ""))
            )
            self.tbl_employees.setItem(
                idx, 2, QTableWidgetItem(r.get("full_name", ""))
            )
            self.tbl_employees.setItem(
                idx, 3, QTableWidgetItem(r.get("phone", ""))
            )
            self.tbl_employees.setItem(
                idx, 4, QTableWidgetItem("Sí" if r.get("active") else "No")
            )
        if hasattr(self, "cmb_shift_employee"):
            self._reload_shift_employees()

    def _reload_shift_employees(self):
        """Rellena el combo de empleados que pueden abrir turno."""
        if not hasattr(self, "cmb_shift_employee"):
            return
        self.cmb_shift_employee.clear()
        emps = [e for e in list_employees() if e.get("active")]
        if not emps:
            self.cmb_shift_employee.addItem("(sin empleados)", "")
            return
        for e in emps:
            label = f"{e['emp_no']} - {e['full_name']}"
            self.cmb_shift_employee.addItem(label, e["emp_no"])

    def _emp_current_id(self) -> int | None:
        r = self.tbl_employees.currentRow()
        if r is None or r < 0:
            return None
        item = self.tbl_employees.item(r, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except Exception:
            return None

    def _emp_new(self):
        dlg = EmployeeDialog(self)
        if dlg.exec():
            data = dlg.data()
            if not data:
                return
            create_employee(
                emp_no=data["emp_no"],
                full_name=data["full_name"],
                phone=data["phone"],
                active=data["active"],
            )
            QMessageBox.information(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_saved") or "Guardado.")
            self._emp_refresh()

    def _emp_edit(self):
        eid = self._emp_current_id()
        if eid is None:
            QMessageBox.warning(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_select") or "Selecciona un empleado.")
            return
        emp = get_employee(eid)
        if not emp:
            QMessageBox.warning(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_not_found") or "Empleado no encontrado.")
            return
        dlg = EmployeeDialog(self, employee=emp)
        if dlg.exec():
            data = dlg.data()
            if not data:
                return
            update_employee(
                employee_id=eid,
                emp_no=data["emp_no"],
                full_name=data["full_name"],
                phone=data["phone"],
                active=data["active"],
            )
            QMessageBox.information(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_saved") or "Guardado.")
            self._emp_refresh()

    def _emp_toggle(self):
        eid = self._emp_current_id()
        if eid is None:
            QMessageBox.warning(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_select") or "Selecciona un empleado.")
            return
        emp = get_employee(eid)
        if not emp:
            QMessageBox.warning(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_not_found") or "Empleado no encontrado.")
            return
        set_employee_active(eid, not bool(emp.get("active")))
        QMessageBox.information(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_saved") or "OK")
        self._emp_refresh()

    def _emp_delete(self):
        eid = self._emp_current_id()
        if eid is None:
            QMessageBox.warning(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_select") or "Selecciona un empleado.")
            return
        if (
            QMessageBox.question(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_delete") or "¿Eliminar empleado?")
            != QMessageBox.Yes
        ):
            return
        delete_employee(eid)
        QMessageBox.information(self, i18n.t("employees_title") or "Empleados", i18n.t("emp_deleted") or "Eliminado.")
        self._emp_refresh()

    # ---------- Themes
    def _tab_themes(self) -> QWidget:
        """Tab for theme selection and customization."""
        
        w = QWidget()
        main_layout = QHBoxLayout(w)
        main_layout.setSpacing(24)
        main_layout.setContentsMargins(16, 16, 16, 16)
        
        left_panel = QVBoxLayout()
        left_panel.setSpacing(16)
        
        # Header
        header = QLabel(i18n.t("tab_themes") or "Temas")
        header.setStyleSheet("font-size: 18px; font-weight: 700;")
        left_panel.addWidget(header)
        
        # Theme list
        self.theme_list = QListWidget()
        self.theme_list.setMinimumWidth(280)
        self.theme_list.itemClicked.connect(self._on_theme_selected)
        left_panel.addWidget(self.theme_list, 1)
        
        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        
        btn_apply = QPushButton(i18n.t("ok") or "Aplicar")
        btn_apply.setProperty("role", "primary")
        btn_apply.setMinimumHeight(56)
        btn_apply.clicked.connect(self._apply_theme)
        
        btn_new = QPushButton(i18n.t("theme_new") or "Nuevo")
        btn_new.setMinimumHeight(56)
        btn_new.clicked.connect(self._new_theme)
        
        btn_delete = QPushButton(i18n.t("delete") or "Eliminar")
        btn_delete.setProperty("role", "danger")
        btn_delete.setMinimumHeight(56)
        btn_delete.clicked.connect(self._delete_theme)
        
        btn_row.addWidget(btn_apply)
        btn_row.addWidget(btn_new)
        btn_row.addWidget(btn_delete)
        left_panel.addLayout(btn_row)
        
        main_layout.addLayout(left_panel)
        
        right_panel = QVBoxLayout()
        right_panel.setSpacing(16)
        
        preview_header = QLabel(i18n.t("preview") or "Vista previa")
        preview_header.setStyleSheet("font-size: 16px; font-weight: 600;")
        right_panel.addWidget(preview_header)
        
        # Color preview grid
        preview_frame = QFrame()
        preview_frame.setObjectName("ThemePreviewFrame")
        preview_frame.setStyleSheet("""
            QFrame#ThemePreviewFrame {
                border-radius: 16px;
                padding: 16px;
                border: 1px solid palette(mid);
            }
        """)
        preview_grid = QGridLayout(preview_frame)
        preview_grid.setSpacing(12)
        
        # Color preview boxes
        self.color_previews = {}
        color_labels = [
            ("bg_deep", i18n.t("color_background") or "Fondo"),
            ("surface", i18n.t("color_surface") or "Superficie"),
            ("text_primary", i18n.t("color_text") or "Texto"),
            ("accent_primary", i18n.t("color_accent") or "Acento"),
            ("success", "Success"),
            ("warning", "Warning"),
            ("danger", "Danger"),
        ]
        
        for i, (key, label) in enumerate(color_labels):
            row = i // 4
            col = i % 4
            
            box = QFrame()
            box.setFixedSize(60, 60)
            box.setStyleSheet("border-radius: 12px; background: #333;")
            box.setCursor(Qt.PointingHandCursor)
            box.setProperty("color_key", key)
            box.mousePressEvent = lambda e, k=key: self._pick_color(k)
            
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 11px; color: #94a3b8;")
            lbl.setAlignment(Qt.AlignCenter)
            
            col_layout = QVBoxLayout()
            col_layout.setSpacing(4)
            col_layout.addWidget(box, alignment=Qt.AlignCenter)
            col_layout.addWidget(lbl, alignment=Qt.AlignCenter)
            
            self.color_previews[key] = box
            preview_grid.addLayout(col_layout, row, col)
        
        right_panel.addWidget(preview_frame)
        
        # Theme name for custom themes
        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        name_lbl = QLabel(i18n.t("theme_name") or "Nombre:")
        self.theme_name_edit = QLineEdit()
        self.theme_name_edit.setPlaceholderText(i18n.t("theme_custom") or "Mi tema")
        self.theme_name_edit.setMinimumHeight(48)
        self.theme_name_edit.installEventFilter(self._osk_filter)  # Enable OSK for touchscreen
        name_row.addWidget(name_lbl)
        name_row.addWidget(self.theme_name_edit, 1)
        right_panel.addLayout(name_row)
        
        # Save custom button
        btn_save_custom = QPushButton(f"{get_icon_char('save') or '💾'}  " + (i18n.t("save") or "Guardar tema"))
        btn_save_custom.setProperty("role", "success")
        btn_save_custom.setMinimumHeight(56)
        btn_save_custom.clicked.connect(self._save_custom_theme)
        right_panel.addWidget(btn_save_custom)
        
        right_panel.addStretch(1)
        main_layout.addLayout(right_panel, 1)
        
        # Store current editing colors
        self._editing_colors = {}
        self._current_theme_id = None
        
        # Load themes
        self._refresh_theme_list()
        
        return w
    
    def _refresh_theme_list(self):
        """Reload the theme list."""
        from services import themes as theme_svc
        
        self.theme_list.clear()
        current = theme_svc.get_current_theme()
        
        for theme in theme_svc.list_themes():
            name = theme["name"] if i18n.current_lang() == "es" else theme.get("name_en", theme["name"])
            suffix = " ✨" if theme["is_custom"] else ""
            item = QListWidgetItem(f"{name}{suffix}")
            item.setData(Qt.UserRole, theme["id"])
            item.setData(Qt.UserRole + 1, theme["colors"])
            item.setData(Qt.UserRole + 2, theme["is_custom"])
            self.theme_list.addItem(item)
            
            if theme["id"] == current:
                item.setSelected(True)
                self._on_theme_selected(item)
    
    def _on_theme_selected(self, item):
        """Handle theme selection."""
        theme_id = item.data(Qt.UserRole)
        colors = item.data(Qt.UserRole + 1)
        is_custom = item.data(Qt.UserRole + 2)
        
        self._current_theme_id = theme_id
        self._editing_colors = colors.copy()
        
        # Update preview boxes
        for key, box in self.color_previews.items():
            color = colors.get(key, "#333333")
            box.setStyleSheet(f"border-radius: 12px; background: {color};")
        
        # Update name field for custom themes
        if is_custom:
            self.theme_name_edit.setText(colors.get("name", theme_id))
        else:
            self.theme_name_edit.setText("")
    
    def _pick_color(self, key: str):
        """Open color picker for a specific color key."""
        from PySide6.QtWidgets import QColorDialog
        from PySide6.QtGui import QColor
        
        current = self._editing_colors.get(key, "#333333")
        color = QColorDialog.getColor(QColor(current), self, i18n.t("color_accent") or "Seleccionar color")
        
        if color.isValid():
            hex_color = color.name()
            self._editing_colors[key] = hex_color
            if key in self.color_previews:
                self.color_previews[key].setStyleSheet(f"border-radius: 12px; background: {hex_color};")
    
    def _apply_theme(self):
        """Apply the selected theme with a loading indicator."""
        
        if not self._current_theme_id:
            self._toast(i18n.t("theme_select") or "Selecciona un tema.", level="warning")
            return
            
        self.loading_overlay.show_event()
        # Use QTimer to allow UI to render the overlay before blocking for QSS apply
        QTimer.singleShot(100, self._do_apply_theme)

    def _do_apply_theme(self):
        from services import themes as theme_svc
        from PySide6.QtWidgets import QApplication
        
        app = QApplication.instance()
        if theme_svc.apply_theme(app, self._current_theme_id):
            self._toast(i18n.t("theme_applied") or "Tema aplicado.", level="success")
        else:
            self._toast("Error applying theme.", level="error")
            
        self.loading_overlay.hide()
        # Refresh current tab UI if needed (some objects might need manual refresh)
        self.style().unpolish(self)
        self.style().polish(self)
    
    def _new_theme(self):
        """Start creating a new custom theme based on current."""
        from services import themes as theme_svc
        
        # Start with dark theme as base
        base = theme_svc.get_theme("dark")
        if base:
            self._editing_colors = base.copy()
            for key, box in self.color_previews.items():
                color = self._editing_colors.get(key, "#333333")
                box.setStyleSheet(f"border-radius: 12px; background: {color};")
        
        self._current_theme_id = None
        self.theme_name_edit.setText("")
        self.theme_name_edit.setFocus()
        self._toast(i18n.t("theme_new") or "Personaliza los colores y guarda.", level="info")
    
    def _save_custom_theme(self):
        """Save the current colors as a custom theme."""
        from services import themes as theme_svc
        
        name = self.theme_name_edit.text().strip()
        if not name:
            self._toast(i18n.t("theme_name_required") or "Ingresa un nombre.", level="warning")
            return
        
        # Create theme ID from name
        theme_id = name.lower().replace(" ", "_")[:20]
        
        # Save colors with name
        colors = self._editing_colors.copy()
        colors["name"] = name
        colors["name_en"] = name
        
        theme_svc.save_custom_theme(theme_id, colors)
        self._toast(i18n.t("theme_saved") or "Tema guardado.", level="success")
        self._refresh_theme_list()
    
    def _delete_theme(self):
        """Delete the selected custom theme."""
        from services import themes as theme_svc
        
        item = self.theme_list.currentItem()
        if not item:
            self._toast(i18n.t("theme_select") or "Selecciona un tema.", level="warning")
            return
        
        is_custom = item.data(Qt.UserRole + 2)
        if not is_custom:
            self._toast(i18n.t("theme_cannot_delete") or "No se puede eliminar.", level="warning")
            return
        
        theme_id = item.data(Qt.UserRole)
        if QMessageBox.question(
            self,
            i18n.t("tab_themes") or "Temas",
            i18n.t("theme_confirm_delete") or "¿Eliminar tema?"
        ) == QMessageBox.Yes:
            theme_svc.delete_custom_theme(theme_id)
            self._toast(i18n.t("theme_deleted") or "Tema eliminado.", level="success")
            self._refresh_theme_list()

    # ---------- System
    def _tab_system(self) -> QWidget:
        w = QWidget()
        main_layout = QVBoxLayout(w)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        top_container = QHBoxLayout()
        top_container.setSpacing(16)
        
        wifi_frame = QFrame()
        wifi_frame.setObjectName("SystemCard")
        wifi_frame.setStyleSheet("""
            QFrame#SystemCard {
                border-radius: 10px;
            }
        """)
        wifi_layout = QVBoxLayout(wifi_frame)
        wifi_layout.setSpacing(8)
        wifi_layout.setContentsMargins(12, 12, 12, 12)
        
        wifi_icon = get_icon_char("network-wired") or "🌐"
        wifi_title = QLabel(f"{wifi_icon}  Configuración WiFi")
        wifi_title.setObjectName("SectionTitleSmall")
        wifi_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        wifi_layout.addWidget(wifi_title)
        
        # SSID row
        ssid_row = QHBoxLayout()
        ssid_row.setSpacing(6)
        self.ssid_combo = QComboBox()
        self.ssid_combo.setMinimumHeight(32)
        btn_scan = QPushButton("Buscar")
        btn_scan.setMinimumSize(90, 32)
        btn_scan.setToolTip("Escanear redes WiFi")
        btn_scan.clicked.connect(self._scan_wifi)
        ssid_row.addWidget(self.ssid_combo, 1)
        ssid_row.addWidget(btn_scan)
        wifi_layout.addLayout(ssid_row)
        
        # Password
        self.wifi_pass = QLineEdit()
        self.wifi_pass.setEchoMode(QLineEdit.Password)
        self.wifi_pass.setPlaceholderText("Contraseña de red")
        self.wifi_pass.setMinimumHeight(32)
        wifi_layout.addWidget(self.wifi_pass)
        
        # Connect button
        btn_conn = QPushButton(i18n.t("connect_wifi"))
        btn_conn.setMinimumHeight(32)
        btn_conn.clicked.connect(self._connect_wifi)
        wifi_layout.addWidget(btn_conn)
        
        # Status row
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_lbl = QLabel("Estado:")
        status_lbl.setStyleSheet("font-size: 11px;")
        self.wifi_state = QLabel("(—)")
        self.wifi_state.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.wifi_state.setProperty("role", "success")
        btn_state = QPushButton("Actualizar")
        btn_state.setMinimumSize(90, 28)
        btn_state.setToolTip("Actualizar estado")
        btn_state.clicked.connect(self._refresh_wifi)
        status_row.addWidget(status_lbl)
        status_row.addWidget(self.wifi_state, 1)
        status_row.addWidget(btn_state)
        wifi_layout.addLayout(status_row)
        
        # Power buttons row
        power_row = QHBoxLayout()
        power_row.setSpacing(6)
        btn_reboot = QPushButton("Reiniciar")
        btn_reboot.setMinimumHeight(28)
        btn_reboot.clicked.connect(self._confirm_reboot)
        btn_power = QPushButton("Apagar")
        btn_power.setMinimumHeight(28)
        btn_power.clicked.connect(self._confirm_poweroff)
        power_row.addWidget(btn_reboot)
        power_row.addWidget(btn_power)
        wifi_layout.addLayout(power_row)
        
        wifi_layout.addStretch()
        self.wifi_pass.installEventFilter(self._osk_filter)
        
        top_container.addWidget(wifi_frame, 1)
        
        email_frame = QFrame()
        email_frame.setObjectName("SystemCard")
        email_frame.setStyleSheet("""
            QFrame#SystemCard {
                border-radius: 10px;
            }
        """)
        email_layout = QVBoxLayout(email_frame)
        email_layout.setSpacing(8)
        email_layout.setContentsMargins(12, 12, 12, 12)
        
        email_icon = get_icon_char("envelope") or "📧"
        email_title = QLabel(f"{email_icon}  Configuración Gmail")
        email_title.setObjectName("SectionTitleSmall")
        email_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        
        # Gmail user
        user_lbl = QLabel("Cuenta Gmail:")
        user_lbl.setStyleSheet("font-size: 11px;")
        email_layout.addWidget(user_lbl)
        
        self.gmail_user = QLineEdit()
        self.gmail_user.setPlaceholderText("tucuenta@gmail.com")
        self.gmail_user.setMinimumHeight(32)
        email_layout.addWidget(self.gmail_user)
        
        # Gmail password
        pass_lbl = QLabel("Contraseña de App:")
        pass_lbl.setStyleSheet("font-size: 11px;")
        email_layout.addWidget(pass_lbl)
        
        self.gmail_pass = QLineEdit()
        self.gmail_pass.setEchoMode(QLineEdit.Password)
        self.gmail_pass.setPlaceholderText("Contraseña de aplicación")
        self.gmail_pass.setMinimumHeight(32)
        email_layout.addWidget(self.gmail_pass)
        
        # Save button
        save_icon = get_icon_char("floppy-disk") or "💾"
        btn_save_email = QPushButton(f"{save_icon} Guardar")
        btn_save_email.setMinimumHeight(32)
        btn_save_email.setProperty("role", "primary")
        btn_save_email.clicked.connect(self._save_gmail_config)
        email_layout.addWidget(btn_save_email)
        
        # Note
        note = QLabel("Usa contraseña de aplicación.\nmyaccount.google.com/apppasswords")
        note.setStyleSheet("font-size: 10px;")
        note.setWordWrap(True)
        email_layout.addWidget(note)
        
        email_layout.addStretch()
        
        self.gmail_user.installEventFilter(self._osk_filter)
        self.gmail_pass.installEventFilter(self._osk_filter)
        
        top_container.addWidget(email_frame, 1)
        
        main_layout.addLayout(top_container, 1)
        
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("max-height: 1px; border: 1px solid palette(mid);")
        main_layout.addWidget(separator)
        
        bottom_container = QHBoxLayout()
        bottom_container.setSpacing(16)
        
        # === Public IP and Remote Support (60-70% left) ===
        ip_frame = QFrame()
        ip_frame.setObjectName("SystemCard")
        ip_frame.setStyleSheet("""
            QFrame#SystemCard {
                border-radius: 10px;
            }
        """)
        ip_layout = QVBoxLayout(ip_frame)
        ip_layout.setSpacing(8)
        ip_layout.setContentsMargins(12, 12, 12, 12)
        
        server_icon = get_icon_char("server") or "🖥"
        ip_title = QLabel(f"{server_icon}  Conectividad & Soporte")
        ip_title.setObjectName("SectionTitleSmall")
        ip_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        ip_layout.addWidget(ip_title)
        
        # Public IP row
        ip_row = QHBoxLayout()
        ip_row.setSpacing(8)
        ip_lbl = QLabel(i18n.t("public_ip") or "IP Pública:")
        ip_lbl.setStyleSheet("font-size: 11px;")
        self.lbl_public_ip = QLabel("—")
        self.lbl_public_ip.setStyleSheet("font-weight: 700; font-size: 14px;")
        self.lbl_public_ip.setProperty("role", "success")
        self.lbl_public_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.btn_refresh_ip = QPushButton(i18n.t("prod_refresh") or "Actualizar")
        self.btn_refresh_ip.setMinimumSize(90, 28)
        self.btn_refresh_ip.setToolTip(i18n.t("update_status") or "Actualizar IP")
        self.btn_refresh_ip.clicked.connect(self._refresh_public_ip)
        ip_row.addWidget(ip_lbl)
        ip_row.addWidget(self.lbl_public_ip, 1)
        ip_row.addWidget(self.btn_refresh_ip)
        ip_layout.addLayout(ip_row)
        
        # SSH note
        ssh_note = QLabel(i18n.t("ssh_support_note") or "Para soporte remoto, usa SSH con esta IP.")
        ssh_note.setStyleSheet("font-size: 10px;")
        ssh_note.setWordWrap(True)
        ip_layout.addWidget(ssh_note)
        
        ip_layout.addStretch()
        
        bottom_container.addWidget(ip_frame, 2)  # 60-70% del espacio
        
        # === Factory Reset (30-40% right) ===
        reset_frame = QFrame()
        reset_frame.setObjectName("SystemCard")
        reset_frame.setStyleSheet("""
            QFrame#SystemCard {
                border-radius: 10px;
            }
        """)
        reset_layout = QVBoxLayout(reset_frame)
        reset_layout.setSpacing(8)
        reset_layout.setContentsMargins(12, 12, 12, 12)
        
        gear_icon = get_icon_char("gears") or "⚙️"
        reset_title = QLabel(f"{gear_icon}  Sistema")
        reset_title.setObjectName("SectionTitleSmall")
        reset_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        reset_layout.addWidget(reset_title)
        
        reset_layout.addStretch()
        
        # Factory Reset button (smaller, aligned bottom right)
        btn_factory_reset = QPushButton(i18n.t("factory_reset") or "Restaurar de Fábrica")
        btn_factory_reset.setMinimumHeight(48)
        btn_factory_reset.setProperty("role", "danger")
        btn_factory_reset.setStyleSheet("""
            QPushButton {
                font-weight: 600;
                font-size: 11px;
            }
        """)
        btn_factory_reset.clicked.connect(self._confirm_factory_reset)
        reset_layout.addWidget(btn_factory_reset)
        
        factory_note = QLabel(i18n.t("factory_reset_warning") or "⚠ Elimina todos los datos")
        factory_note.setStyleSheet("font-size: 9px;")
        factory_note.setProperty("role", "danger")
        factory_note.setAlignment(Qt.AlignCenter)
        reset_layout.addWidget(factory_note)
        
        bottom_container.addWidget(reset_frame, 1)  # 30-40% del espacio
        
        main_layout.addLayout(bottom_container)
        
        self._load_gmail_config()
        
        return w
    
    def _confirm_factory_reset(self):
        """Factory reset with double confirmation (yes/no + type RESET) and OSK."""
        # --- First confirmation ---
        ans = QMessageBox.warning(
            self,
            i18n.t("factory_reset"),
            i18n.t("factory_reset_confirm"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return

        # --- Second confirmation: type RESET in a custom dialog w/ OSK ---
        dlg = QDialog(self)
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet("""
            QDialog { border: 2px solid #ef4444; border-radius: 14px; padding: 18px; }
            QLabel#ResetTitle { font-size: 16px; font-weight: 700; color: #ef4444; }
        """)

        lay = QVBoxLayout(dlg)
        lay.setSpacing(14)
        lay.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"⚠  {i18n.t('factory_reset')}")
        title.setObjectName("ResetTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        lbl = QLabel(i18n.t("factory_reset_type_confirm"))
        lbl.setStyleSheet("font-size: 13px;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        ed_confirm = QLineEdit()
        ed_confirm.setPlaceholderText("RESET")
        ed_confirm.setMinimumHeight(48)
        ed_confirm.setAlignment(Qt.AlignCenter)
        ed_confirm.setStyleSheet("font-size: 16px; font-weight: 700; letter-spacing: 4px;")
        # Install OSK filter for touchscreen support
        ed_confirm.installEventFilter(self._osk_filter)
        lay.addWidget(ed_confirm)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(48)
        btn_cancel.clicked.connect(dlg.reject)

        btn_ok = QPushButton(i18n.t("factory_reset"))
        btn_ok.setMinimumHeight(48)
        btn_ok.setProperty("role", "danger")
        btn_ok.setStyleSheet("font-weight: 700;")

        def _try_accept():
            if ed_confirm.text().strip().upper() == "RESET":
                dlg.accept()
            else:
                ed_confirm.setStyleSheet(
                    "font-size: 16px; font-weight: 700; letter-spacing: 4px; border: 2px solid #ef4444;"
                )

        btn_ok.clicked.connect(_try_accept)

        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        if dlg.exec() != QDialog.Accepted:
            return

        # --- Execute factory reset ---
        try:
            # 1. Delete custom themes
            themes_dir = ROOT / "config" / "themes"
            if themes_dir.exists():
                import shutil
                shutil.rmtree(themes_dir, ignore_errors=True)

            # 2. Reset config.yaml to factory defaults
            reset_config_to_defaults()

            # 3. Wipe and recreate database
            from core.db import factory_reset
            ok = factory_reset()
            if not ok:
                raise RuntimeError("factory_reset() returned False")

            # 4. Show success and restart app
            QMessageBox.information(
                self,
                i18n.t("factory_reset"),
                i18n.t("factory_reset_success"),
            )

            # Restart app (same mechanism as _exit_to_kiosk)
            # Restart app — close admin to return to kiosk
            self.close()

        except Exception as exc:
            QMessageBox.critical(
                self,
                i18n.t("factory_reset"),
                i18n.t("factory_reset_error", err=str(exc)),
            )
    
    def _refresh_public_ip(self):
        """Gets and displays the system's public IP address (thread-safe)."""
        import urllib.request
        import threading

        # Disable button during fetch
        if hasattr(self, "btn_refresh_ip"):
            self.btn_refresh_ip.setEnabled(False)

        def _set_ip(text, style=None):
            """Marshal widget update to the main Qt thread."""
            def _update():
                if hasattr(self, "lbl_public_ip"):
                    self.lbl_public_ip.setText(text)
                    if style:
                        self.lbl_public_ip.setStyleSheet(style)
                if hasattr(self, "btn_refresh_ip"):
                    self.btn_refresh_ip.setEnabled(True)
            QTimer.singleShot(0, _update)

        def fetch_ip():
            try:
                with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
                    ip = response.read().decode("utf-8").strip()
                    _set_ip(ip, "font-weight: 700; font-size: 14px;")
            except Exception:
                _set_ip(
                    i18n.t("ip_not_available") or "Sin conexión",
                    "color: #f87171; font-weight: 700; font-size: 14px;",
                )

        # Show loading state
        if hasattr(self, "lbl_public_ip"):
            self.lbl_public_ip.setText(i18n.t("getting_ip") or "Obteniendo...")
            self.lbl_public_ip.setStyleSheet("color: #10b981; font-weight: 700; font-size: 14px;")
        thread = threading.Thread(target=fetch_ip, daemon=True)
        thread.start()
    
    def _load_gmail_config(self):
        """Carga la configuración de Gmail desde config.yaml"""
        cfg = load_config()
        email_cfg = cfg.get("notifications", {}).get("email", {})
        
        default_gmail_user = "tottem.reports@gmail.com"
        default_gmail_pass = "mfexwikphlncahve"
        
        gmail_user = email_cfg.get("gmail_user", default_gmail_user)
        self.gmail_user.setText(gmail_user)
        
        if not email_cfg.get("gmail_user"):
            if "notifications" not in cfg:
                cfg["notifications"] = {}
            if "email" not in cfg["notifications"]:
                cfg["notifications"]["email"] = {}
            cfg["notifications"]["email"]["gmail_user"] = default_gmail_user
            cfg["notifications"]["email"]["gmail_pass"] = default_gmail_pass
            save_config(cfg)
    
    def _save_gmail_config(self):
        """Guarda la configuración de Gmail en config.yaml"""
        gmail_user = self.gmail_user.text().strip()
        gmail_pass = self.gmail_pass.text().strip()
        
        if gmail_user and not gmail_user.endswith("@gmail.com"):
            QMessageBox.warning(
                self,
                "Configuración de Email",
                "Por favor ingresa una cuenta de Gmail válida (debe terminar en @gmail.com)"
            )
            return
        
        if not gmail_user and gmail_pass:
            QMessageBox.warning(
                self,
                "Configuración de Email",
                "Por favor ingresa una cuenta de Gmail"
            )
            return
        
        cfg = load_config()
        if "notifications" not in cfg:
            cfg["notifications"] = {}
        if "email" not in cfg["notifications"]:
            cfg["notifications"]["email"] = {}
        
        cfg["notifications"]["email"]["gmail_user"] = gmail_user
        if gmail_pass:
            cfg["notifications"]["email"]["gmail_pass"] = gmail_pass
        
        save_config(cfg)
        
        QMessageBox.information(
            self,
            "Configuración de Email",
            "Configuración de Gmail guardada correctamente."
        )
        
        self.gmail_pass.clear()


    def _scan_wifi(self):
        nets = wifi_list()
        self.ssid_combo.clear()
        for n in nets:
            label = f"{n['ssid']}  ({n['signal']})"
            self.ssid_combo.addItem(label, n["ssid"])

    def _connect_wifi(self):
        ssid = self.ssid_combo.currentData()
        ok, msg = wifi_connect(ssid or "", self.wifi_pass.text())
        QMessageBox.information(self, i18n.t("wifi_msg"), msg)
        self._refresh_wifi()

    def _refresh_wifi(self):
        self.wifi_state.setText(wifi_status())

    def _confirm_reboot(self):
        if (
            QMessageBox.question(
                self, i18n.t("reboot"), i18n.t("confirm_reboot")
            )
            == QMessageBox.Yes
        ):
            reboot()

    def _confirm_poweroff(self):
        if (
            QMessageBox.question(
                self, i18n.t("poweroff"), i18n.t("confirm_poweroff")
            )
            == QMessageBox.Yes
        ):
            poweroff()

    def _exit_to_kiosk(self):
        self.close()

    # ---------- Language toggle ----------
    def _toggle_lang(self):
        i18n.toggle()

        self.setWindowTitle(i18n.t("admin_title"))
        self.lang_btn.setText(i18n.lang_switch_label())
        self.title_lbl.setText(f"{get_icon_char('gear') or '⚙'}  " + (i18n.t("admin_title") or "Administración"))
        self.btn_close.setText(f"{get_icon_char('arrow-left') or '←'}  " + (i18n.t("exit") or "Salir"))

        current_idx = self.tabs.currentIndex()
        
        self.tabs.clear()
        
        self.tabs.addTab(self._tab_security(), f"{get_icon_char('lock') or '🔐'}  " + i18n.t("tab_security"))
        self.tabs.addTab(self._tab_devices(), f"{get_icon_char('print') or '🖨'}  " + i18n.t("tab_devices"))
        self.tabs.addTab(self._tab_store(), f"{get_icon_char('store') or '🏪'}  " + i18n.t("tab_store"))
        self.tabs.addTab(self._tab_products(), f"{get_icon_char('box') or '📦'}  " + i18n.t("tab_products"))
        self.tabs.addTab(self._tab_shifts(), f"{get_icon_char('chart-bar') or '📊'}  " + (i18n.t("tab_shifts") or "Turnos"))
        self.tabs.addTab(self._tab_tickets(), f"{get_icon_char('receipt') or '🧾'}  " + (i18n.t("tickets") if i18n.t("tickets") != "tickets" else "Tickets"))
        self.tabs.addTab(self._tab_reports(), f"{get_icon_char('chart-line') or '📈'}  " + i18n.t("tab_reports"))
        self.tabs.addTab(self._tab_themes(), f"{get_icon_char('palette') or '🎨'}  " + i18n.t("tab_themes"))
        self.tabs.addTab(self._tab_system(), f"{get_icon_char('computer') or '💻'}  " + i18n.t("tab_system"))
        
        self.tabs.setCurrentIndex(current_idx)
        if hasattr(self, "lbl_shift"):
            self.lbl_shift.setText(self._shift_label_text())
