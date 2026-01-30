from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QHBoxLayout, QComboBox,
    QMessageBox, QSpinBox, QGridLayout, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QCheckBox, QDialog, QListWidget, QApplication,
    QFrame, QStackedLayout, QTextEdit, QDialogButtonBox
)
from PySide6.QtCore import Qt, QObject, QEvent, QTimer
from pathlib import Path

import sys
import subprocess
import os
import yaml

from argon2 import PasswordHasher, exceptions as argon_exc
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
    list_shifts_since,
    shift_totals,
    close_current_shift,
)
from services.reports import (
    report_x, report_z, render_shift_text, render_range_text,
    csv_tickets_bytes, csv_items_bytes
)
from services.receipts import render_ticket
from services.emailer import send_mail, recent_emails
from services.settings import is_categories_enabled, set_categories_enabled
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


def _load_settings() -> dict:
    try:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_settings(data: dict) -> None:
    CONFIG_PATH.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8"
    )


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
                # Usar el valor actual como texto inicial
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
            color: #64748b;
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
        
        # Touch-friendly styling
        self.combo_icon.setStyleSheet("""
            QComboBox {
                font-size: 16px;
                padding: 12px;
            }
            QComboBox::drop-down {
                width: 50px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 56px;
                padding: 12px 16px;
                font-size: 16px;
            }
        """)
        
        # Add "No icon" option first
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
            color: #64748b;
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
            color: #64748b;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        # Info del turno
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
            expected_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #10b981;")
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
        except:
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
            color: #64748b;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        # Detalles del ticket
        self.txt_details = QTextEdit()
        self.txt_details.setReadOnly(True)
        self.txt_details.setStyleSheet("""
            QTextEdit {
                background: #16161e;
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

        # Cargar detalles si se proporcionó ticket_id
        if ticket_id:
            self.load_ticket(ticket_id)

    def load_ticket(self, ticket_id: int):
        """Carga y muestra los detalles de un ticket."""
        from services.sales import get_ticket_details, cents_to_money
        
        self.ticket_id = ticket_id
        self.ticket_details = get_ticket_details(ticket_id)
        
        if not self.ticket_details:
            self.txt_details.setPlainText("Error: No se pudo cargar el ticket.")
            return
        
        # Formatear detalles con mejor diseño
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
        
        from services.sales import cents_to_money
        for item in self.ticket_details["items"]:
            qty_str = f"x{item.qty}".ljust(6)
            price_str = f"$ {cents_to_money(item.price)}".rjust(12)
            lines.append(f"{qty_str}{item.name}")
            lines.append(f"      {price_str}")
            lines.append("")
        
        lines.append("─" * 50)
        total_str = f"$ {cents_to_money(self.ticket_details['total'])}".rjust(12)
        lines.append(f"{'TOTAL:'.ljust(38)}{total_str}")
        
        # Mostrar pago y cambio si están disponibles
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
        
        from services.receipts import render_ticket
        from drivers.printer_escpos import EscposPrinter
        
        # Generar ticket con todos los parámetros
        ticket_text = render_ticket(
            self.ticket_details["items"],
            ticket_number=self.ticket_details["id"],
            timestamp=self.ticket_details["ts"],
            served_by=self.ticket_details["served_by"],
            paid_cents=self.ticket_details.get('paid', 0),
            change_cents=self.ticket_details.get('change_amount', 0)
        )
        
        # Imprimir
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
            color: #64748b;
        """)

        root.addWidget(icon)
        root.addWidget(title)

        # Panel de información del turno
        if shift_id:
            info_panel = self._build_info_panel()
            root.addWidget(info_panel)

        # Lista de tickets
        lbl_tickets = QLabel("Tickets del turno:")
        lbl_tickets.setStyleSheet("font-weight: 600; font-size: 14px;")
        root.addWidget(lbl_tickets)
        
        self.lst_tickets = QListWidget()
        self.lst_tickets.setStyleSheet("""
            QListWidget {
                background: #16161e;
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
                background: #1f1f28;
                cursor: pointer;
            }
            QListWidget::item:selected {
                background: #2a2a37;
            }
        """)
        self.lst_tickets.itemDoubleClicked.connect(self._open_ticket_details)
        root.addWidget(self.lst_tickets, 1)
        
        hint = QLabel("💡 Haz doble clic en un ticket para ver detalles y reimprimir")
        hint.setStyleSheet("color: #64748b; font-size: 12px; font-style: italic;")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

        # Botón cerrar
        btn_close = QPushButton("Cerrar")
        btn_close.setMinimumHeight(60)
        btn_close.clicked.connect(self.reject)
        root.addWidget(btn_close)

        # Cargar datos
        if shift_id:
            self._load_data()

    def _build_info_panel(self) -> QWidget:
        """Construye panel de información del turno."""
        from services.shifts import shift_totals
        from services.sales import cents_to_money
        from core.db import connect
        
        # Obtener datos del turno
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
        
        # Panel con grid de información
        panel = QWidget()
        panel.setStyleSheet("""
            QWidget {
                background: #16161e;
                border-radius: 12px;
                padding: 16px;
            }
        """)
        
        grid = QGridLayout(panel)
        grid.setSpacing(12)
        grid.setContentsMargins(16, 16, 16, 16)
        
        # Fila 1: Turno # y Estado
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
        
        # Fila 2: Apertura y Cierre
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
        
        # Fila 3: Cajeros
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
        
        # Separador
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background: #2a2a37;")
        grid.addWidget(line, 3, 0, 1, 4)
        
        # Fila 4: Resumen
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
        
        # Fila 5: Totales
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
            
            # Formatear hora
            try:
                if " " in timestamp:
                    hora = timestamp.split(" ")[1][:5]
                elif "T" in timestamp:
                    hora = timestamp.split("T")[1][:5]
                else:
                    hora = timestamp[-8:-3]
            except:
                hora = "??:??"
            
            # Formato: "#123  |  14:30  |  $ 150.00"
            text = f"#{ticket_id:<6} | {hora} | $ {cents_to_money(total):>10}"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, ticket_id)  # Guardar ID para recuperar después
            self.lst_tickets.addItem(item)

    def _open_ticket_details(self, item):
        """Abre TicketDetailDialog para el ticket seleccionado."""
        ticket_id = item.data(Qt.UserRole)
        if ticket_id:
            dlg = TicketDetailDialog(self, ticket_id=ticket_id)
            dlg.exec()




class AdminWindow(QMainWindow):
    """Premium Administration Interface"""
    
    def __init__(self):
        super().__init__()
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
        title_lbl = QLabel(f"{get_icon_char('gear') or '⚙'}  " + (i18n.t("admin_title") or "Administración"))
        title_lbl.setObjectName("SectionTitle")
        title_lbl.setStyleSheet("""
            font-size: 26px;
            font-weight: 700;
            color: #f8fafc;
        """)

        self.lang_btn = QPushButton(i18n.t("lang"))
        self.lang_btn.setMinimumSize(72, 48)
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)

        from ui.icon_helper import get_icon_char
        btn_close = QPushButton(f"{get_icon_char('arrow-left') or '←'}  " + (i18n.t("exit") or "Salir"))
        btn_close.setMinimumHeight(52)
        btn_close.setProperty("role", "danger")
        btn_close.setStyleSheet("""
            QPushButton {
                padding-left: 20px;
                padding-right: 20px;
            }
        """)
        btn_close.clicked.connect(self._exit_to_kiosk)

        top.addWidget(title_lbl)
        top.addStretch(1)
        top.addWidget(self.lang_btn)
        top.addWidget(btn_close)

        # ─── Tab Widget ───────────────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setObjectName("AdminTabs")
        from ui.icon_helper import get_icon_char
        self.tabs.addTab(self._tab_security(), f"{get_icon_char('lock') or '🔐'}  " + i18n.t("tab_security"))
        self.tabs.addTab(self._tab_devices(), f"{get_icon_char('print') or '🖨'}  " + i18n.t("tab_devices"))
        self.tabs.addTab(self._tab_store(), f"{get_icon_char('store') or '🏪'}  " + i18n.t("tab_store"))
        self.tabs.addTab(self._tab_products(), f"{get_icon_char('box') or '📦'}  " + i18n.t("tab_products"))
        self.tabs.addTab(self._tab_shifts(), f"{get_icon_char('chart-bar') or '📊'}  " + (i18n.t("tab_shifts") or "Turnos"))
        self.tabs.addTab(self._tab_tickets(), f"{get_icon_char('receipt') or '🧾'}  Tickets")
        self.tabs.addTab(self._tab_reports(), f"{get_icon_char('chart-line') or '📈'}  " + i18n.t("tab_reports"))
        self.tabs.addTab(self._tab_system(), f"{get_icon_char('computer') or '💻'}  " + i18n.t("tab_system"))

        # ─── Main Container ───────────────────────────────────────────────
        wrap = QWidget()
        wrap.setObjectName("GridPanel")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)
        lay.addWidget(top_wrap)
        lay.addWidget(self.tabs)
        self.setCentralWidget(wrap)
        self.toast_mgr = ToastManager(self)

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

        # Para seguridad usamos keypad numérico en lugar de OSK completo
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
        data = _load_settings()
        data.setdefault("security", {})["admin_pin_hash"] = h
        _save_settings(data)
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
        cur = _load_settings()
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
        cur = _load_settings().get("hardware", {}).get("printer", {})
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
        data = _load_settings()
        pr = data.setdefault("hardware", {}).setdefault("printer", {})
        pr["vendor_id"] = _intval(d.get("vid", "0"))
        pr["product_id"] = _intval(d.get("pid", "0"))
        pr["interface"] = int(d.get("interface", 0))
        pr["out_ep"] = int(d["eps_out"][0]) if d.get("eps_out") else None
        pr["in_ep"] = int(d["eps_in"][0]) if d.get("eps_in") else None
        _save_settings(data)
        self.vendor_id.setText(_fmt_hex(pr["vendor_id"]))
        self.product_id.setText(_fmt_hex(pr["product_id"]))
        self.iface_spin.setValue(int(pr["interface"]))
        self.out_ep.setText(_fmt_hex(pr["out_ep"]))
        self.in_ep.setText(_fmt_hex(pr["in_ep"]))
        QMessageBox.information(self, i18n.t("devices"), i18n.t("saved_ok"))

    def _save_printer_advanced(self):
        data = _load_settings()
        pr = data.setdefault("hardware", {}).setdefault("printer", {})
        pr["vendor_id"] = _intval(self.vendor_id.text())
        pr["product_id"] = _intval(self.product_id.text())
        pr["interface"] = int(self.iface_spin.value())
        out_txt = (self.out_ep.text() or "").strip()
        in_txt = (self.in_ep.text() or "").strip()
        pr["out_ep"] = _intval(out_txt) if out_txt else None
        pr["in_ep"] = _intval(in_txt) if in_txt else None
        _save_settings(data)
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
        s = _load_settings()
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
        data = _load_settings()
        data["store"] = {
            "name": self.name.text(),
            "rfc": self.rfc.text(),
            "ticket_header": self.header.text(),
            "ticket_footer": self.footer.text(),
        }
        _save_settings(data)
        QMessageBox.information(self, i18n.t("tab_store"), i18n.t("store_saved"))

    # ---------- Products (con Categoría + filtros)
    def _tab_products(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        # Filtros: categoría + búsqueda
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

        # Tabla: agregamos columna de Categoría
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

        # reconstruye categorías disponibles desde TODOS los productos (no solo filtrados)
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
        # intentar restaurar selección previa
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

        # Barra de búsqueda
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

        # Keypad numérico para el campo de búsqueda
        self.ed_ticket_search.installEventFilter(self._keypad_filter)

        # Tabla de tickets
        self.tbl_tickets = QTableWidget(0, 5)
        self.tbl_tickets.setHorizontalHeaderLabels([
            "Ticket", "Fecha", "Empleado", "Turno", "Total"
        ])
        self.tbl_tickets.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_tickets.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl_tickets.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_tickets.verticalHeader().setVisible(False)
        # NO usar alternating row colors para evitar problemas visuales en tema oscuro
        self.tbl_tickets.setAlternatingRowColors(False)
        
        # Evento de doble clic para mostrar detalles
        self.tbl_tickets.itemDoubleClicked.connect(self._tickets_show_details_dialog)
        
        # Continuar con responsive columns después de la tabla
        from PySide6.QtWidgets import QHeaderView
        header = self.tbl_tickets.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Ticket
        header.setSectionResizeMode(1, QHeaderView.Stretch)           # Fecha
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)  # Empleado
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Turno
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Total
        
        v.addWidget(self.tbl_tickets, 1)

        # Paginación
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

        # Instrucción para el usuario
        hint_label = QLabel("💡 Haz doble clic en un ticket para ver detalles y reimprimir")
        hint_label.setStyleSheet("color: #64748b; font-size: 12px; font-style: italic;")
        hint_label.setAlignment(Qt.AlignCenter)
        v.addWidget(hint_label)

        # Inicializar variables de paginación
        self.tickets_offset = 0
        self.tickets_page_size = 15

        # Cargar tickets iniciales
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
        
        # Actualizar label de página
        page_num = (offset // self.tickets_page_size) + 1
        self.lbl_tickets_page.setText(f"Página {page_num}")
        
        # Habilitar/deshabilitar botones de navegación
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
        
        # Mostrar solo ese ticket en la tabla
        self.tbl_tickets.setRowCount(0)
        self.tbl_tickets.insertRow(0)
        self.tbl_tickets.setItem(0, 0, QTableWidgetItem(str(ticket["id"])))
        self.tbl_tickets.setItem(0, 1, QTableWidgetItem(ticket["ts"] or ""))
        self.tbl_tickets.setItem(0, 2, QTableWidgetItem(ticket["served_by"] or "—"))
        self.tbl_tickets.setItem(0, 3, QTableWidgetItem(f"{ticket['shift_id']}" if ticket['shift_id'] else "—"))
        self.tbl_tickets.setItem(0, 4, QTableWidgetItem(f"$ {cents_to_money(ticket['total'])}"))
        
        # Deshabilitar paginación durante búsqueda
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
        
        # Abrir diálogo con detalles del ticket
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


    # ---------- Reports (solo rango de fechas + correo)
    def _tab_reports(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(14)

        # --- Enviar reporte por correo (rango de fechas) ---
        v.addWidget(QLabel(i18n.t("send_mail") or "Enviar reporte por correo"))

        mail_row1 = QHBoxLayout()
        mail_row1.setSpacing(12)
        self.date_from = QLineEdit()
        self.date_from.setMinimumWidth(170)
        self.date_from.setPlaceholderText("YYYY-MM-DD")
        self.date_to = QLineEdit()
        self.date_to.setMinimumWidth(170)
        self.date_to.setPlaceholderText("YYYY-MM-DD")
        mail_row1.addWidget(QLabel(i18n.t("dates_from") or "Desde"))
        mail_row1.addWidget(self.date_from)
        mail_row1.addWidget(QLabel(i18n.t("dates_to") or "Hasta"))
        mail_row1.addWidget(self.date_to)
        v.addLayout(mail_row1)

        mail_row2 = QHBoxLayout()
        mail_row2.setSpacing(12)
        self.ed_emails = QLineEdit()
        self.ed_emails.setPlaceholderText(
            i18n.t("emails_placeholder")
            or "correo1@ejemplo.com, correo2@ejemplo.com"
        )
        self.cb_recent = QComboBox()
        self.cb_recent.setMinimumHeight(52)
        self.cb_recent.addItem("")
        for e in recent_emails():
            self.cb_recent.addItem(e)
        btn_add_recent = QPushButton(i18n.t("add") or "Agregar")
        btn_add_recent.clicked.connect(self._add_recent_email)
        btn_send = QPushButton(i18n.t("send_mail") or "Enviar reporte")
        btn_send.clicked.connect(self._send_mail)
        for b in (btn_add_recent, btn_send):
            b.setMinimumHeight(38)
        mail_row2.addWidget(self.ed_emails, 1)
        mail_row2.addWidget(QLabel(i18n.t("recent_emails") or "Correos recientes"))
        mail_row2.addWidget(self.cb_recent)
        mail_row2.addWidget(btn_add_recent)
        mail_row2.addWidget(btn_send)
        v.addLayout(mail_row2)

        for wle in (self.date_from, self.date_to, self.ed_emails):
            wle.installEventFilter(self._osk_filter)

        # --- Turnos de la semana + impresión de reporte de turno ---
        v.addWidget(
            QLabel(i18n.t("print_shift_report") or "Imprimir reporte de turno")
        )

        self.list_shifts = QListWidget()
        self.list_shifts.setObjectName("ShiftList")
        self.list_shifts.setAlternatingRowColors(True)
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

        # Cargar los turnos de los últimos 7 días
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
        # Tomar empleado seleccionado
        emp_code = None
        if hasattr(self, "cmb_shift_employee"):
            emp_code = self.cmb_shift_employee.currentData() or None

        if not emp_code:
            self._toast(
                "Selecciona el empleado que abre el turno.", level="error"
            )
            return

        # opening_cash en centavos; por ahora 0
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
        
        # Abrir diálogo premium
        dlg = ShiftPreviewDialog(self, shift_id=sh["id"])
        dlg.exec()

    def _do_close(self):
        """
        Cierra el turno actual con diálogo de conteo de efectivo,
        genera reporte resumido e imprime.
        """
        # Comprobamos que haya turno abierto antes de intentar cerrar
        sh = current_shift()
        if not sh:
            self._toast("No hay turno abierto.", level="error")
            return

        # Mostrar diálogo de cierre para capturar efectivo y cajero
        dlg = ShiftCloseDialog(self, shift_info=sh)
        if dlg.exec() != QDialog.Accepted:
            return
        
        close_data = dlg.data()
        closing_cash = close_data.get("closing_cash", 0)
        closed_by = close_data.get("closed_by", "")

        # Cerrar turno en BD
        try:
            close_shift(closed_by=closed_by, closing_cash=closing_cash)
        except Exception as e:
            QMessageBox.critical(
                self,
                i18n.t("tab_shifts") or "Turnos",
                f"Error al cerrar turno: {e}"
            )
            return

        # Generar reporte resumido (sin detalles de ítems, solo lista de tickets)
        txt = render_shift_text(sh["id"], detailed=False)

        # Intentar imprimir el reporte del turno
        try:
            EscposPrinter().print_text(txt)
            self._toast(
                f"Turno #{sh['id']} cerrado e impreso.", level="success"
            )
        except Exception as e:
            # Mostrar el reporte en pantalla si no se puede imprimir
            QMessageBox.information(
                self,
                "Reporte de Turno",
                txt[:2000] + ("..." if len(txt) > 2000 else "")
            )
            self._toast(
                f"Turno cerrado. Error al imprimir: {e}", level="error"
            )

        # Actualizar etiqueta (ya no debe haber turno abierto)
        self.lbl_shift.setText(self._shift_label_text())

        # Refrescar lista de turnos en pestaña de reportes, si existe
        if hasattr(self, "list_shifts"):
            self._reload_week_shifts()

    def _add_recent_email(self):
        e = self.cb_recent.currentText().strip()
        if not e:
            return
        exists = [
            x.strip()
            for x in (self.ed_emails.text() or "").split(",")
            if x.strip()
        ]
        if e not in exists:
            exists.append(e)
            self.ed_emails.setText(", ".join(exists))

    def _send_mail(self):
        df = (self.date_from.text() or "").strip()
        dt = (self.date_to.text() or "").strip()
        rec_raw = (self.ed_emails.text() or "").strip()
        recipients = [x.strip() for x in rec_raw.split(",") if x.strip()]
        if not df or not dt or not recipients:
            for field, empty in (
                (self.date_from, not df),
                (self.date_to, not dt),
                (self.ed_emails, not recipients),
            ):
                self._mark_field_state(field, "error" if empty else None)
            self._toast(
                "Fechas y correos requeridos.", level="error", duration_ms=4200
            )
            return
        for field in (self.date_from, self.date_to, self.ed_emails):
            self._mark_field_state(field, None)
        body = render_range_text(df, dt)
        att = [
            (f"tickets_{df}_a_{dt}.csv", csv_tickets_bytes(df, dt)),
            (f"items_{df}_a_{dt}.csv", csv_items_bytes(df, dt)),
        ]
        ok, msg = send_mail(
            subject=f"Reporte POS {df} a {dt}",
            body=body,
            recipients=recipients,
            attachments=att,
        )
        if ok:
            for field in (self.date_from, self.date_to, self.ed_emails):
                self._mark_field_state(field, "success")
            self._toast(
                i18n.t("report_sent_ok") or "Reporte enviado.", level="success"
            )
            self.cb_recent.clear()
            self.cb_recent.addItem("")
            for e in recent_emails():
                self.cb_recent.addItem(e)
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

    # ---------- Shifts (Turnos) + Empleados
    def _tab_shifts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(10)

        # --- Sección turnos ---
        self.lbl_shift = QLabel(self._shift_label_text())
        self.lbl_shift.setWordWrap(True)
        v.addWidget(self.lbl_shift)

        # Selector de empleado para el turno
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

        # --- Sección empleados ---
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
        
        # Configure responsive columns for 22" display (en lugar de widths fijos)
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
        # Actualizar combo de empleados de turno si existe
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
            # Guardamos como dato el emp_no (podría ser el ID si lo prefieres)
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

    # ---------- System
    def _tab_system(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        row = QHBoxLayout()
        self.ssid_combo = QComboBox()
        btn_scan = QPushButton(
            i18n.t("scan_usb_printers").replace("impresoras USB", "redes")
        )
        btn_scan.clicked.connect(self._scan_wifi)
        row.addWidget(self.ssid_combo)
        row.addWidget(btn_scan)
        self.wifi_pass = QLineEdit()
        self.wifi_pass.setEchoMode(QLineEdit.Password)
        self.wifi_pass.setPlaceholderText(
            i18n.t("password").replace(":", "")
        )
        btn_conn = QPushButton(i18n.t("connect_wifi"))
        btn_conn.clicked.connect(self._connect_wifi)
        self.wifi_state = QLabel("(—)")
        btn_state = QPushButton(i18n.t("update_status"))
        btn_state.clicked.connect(self._refresh_wifi)
        btn_reboot = QPushButton(i18n.t("reboot"))
        btn_reboot.clicked.connect(self._confirm_reboot)
        btn_power = QPushButton(i18n.t("poweroff"))
        btn_power.clicked.connect(self._confirm_poweroff)
        f.addRow(i18n.t("wifi_ssid"), row)
        f.addRow(i18n.t("password"), self.wifi_pass)
        f.addRow(btn_conn)
        f.addRow(i18n.t("status"), self.wifi_state)
        f.addRow(btn_state)
        f.addRow(btn_reboot, btn_power)

        self.wifi_pass.installEventFilter(self._osk_filter)
        return w

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
        env = os.environ.copy()
        cmd = [sys.executable, "-m", "cli", "run-kiosk"]
        try:
            subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env=env,
            )
        except Exception as e:
            QMessageBox.critical(self, "POS", f"No se pudo abrir caja:\n{e}")
            return

        QApplication.instance().quit()

    # ---------- Language toggle ----------
    def _toggle_lang(self):
        # Cambiar idioma global
        i18n.toggle()

        # Cambiar textos de la barra superior
        self.setWindowTitle(i18n.t("admin_title"))
        self.lang_btn.setText(i18n.t("lang"))

        # --- Actualizar los textos de las pestañas ---
        # Indices fijos según __init__
        self.tabs.setTabText(0, i18n.t("tab_security") or "Seguridad")
        self.tabs.setTabText(1, i18n.t("tab_devices") or "Dispositivos")
        self.tabs.setTabText(2, i18n.t("tab_store") or "Tienda")
        self.tabs.setTabText(3, i18n.t("tab_products") or "Productos")
        self.tabs.setTabText(4, i18n.t("tab_shifts") or "Turnos")
        self.tabs.setTabText(5, "Tickets")  # Nuevo tab de Tickets (sin i18n por ahora)
        self.tabs.setTabText(6, i18n.t("tab_reports") or "Reportes")
        self.tabs.setTabText(7, i18n.t("tab_system") or "Sistema")


        # Productos – actualizar textos visibles
        if hasattr(self, "tbl"):
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

        if hasattr(self, "chk_enable_categories"):
            self.chk_enable_categories.setText(
                i18n.t("enable_categories") or "Habilitar Categorías"
            )

        # Empleados
        if hasattr(self, "tbl_employees"):
            self.tbl_employees.setHorizontalHeaderLabels(
                [
                    "ID",
                    i18n.t("emp_no") or "No. empleado",
                    i18n.t("emp_name") or "Nombre completo",
                    i18n.t("emp_phone") or "Contacto",
                    i18n.t("emp_active") or "Activo",
                ]
            )

        # Reportes: placeholder correos
        if hasattr(self, "ed_emails"):
            self.ed_emails.setPlaceholderText(
                i18n.t("emails_placeholder")
                or "correo1@ejemplo.com, correo2@ejemplo.com"
            )

        # Turno actual / lista de turnos
        if hasattr(self, "lbl_shift"):
            self.lbl_shift.setText(self._shift_label_text())
        if hasattr(self, "list_shifts"):
            self._reload_week_shifts()
