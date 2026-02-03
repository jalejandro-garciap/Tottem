from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QHBoxLayout, QComboBox,
    QMessageBox, QSpinBox, QGridLayout, QTableWidget, QTableWidgetItem,
    QAbstractItemView, QCheckBox, QDialog, QListWidget, QApplication,
    QFrame, QStackedLayout
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
from services.sales import money_to_cents, cents_to_money
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
from services.emailer import send_mail, recent_emails
from services.settings import is_categories_enabled, set_categories_enabled
from ui.widgets.osk import OnScreenKeyboard
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


class ProductDialog(QDialog):
    """Diálogo de producto con soporte de categoría y venta parcial."""

    def __init__(self, parent=None, *, product: dict | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        title = QLabel(i18n.t("tab_products") or "Producto")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ed_name = QLineEdit(product["name"] if product else "")
        self.ed_price = QLineEdit(cents_to_money(product["price"]) if product else "")
        self.ed_unit = QLineEdit(product["unit"] if product else "pz")
        self.ed_category = QLineEdit(
            (product.get("category") if product else None) or "General"
        )

        self.cb_active = QCheckBox(i18n.t("prod_active"))
        self.cb_active.setChecked(bool(product["active"]) if product else True)
        self.cb_partial = QCheckBox(i18n.t("prod_allow_partial"))
        self.cb_partial.setChecked(bool(product.get("allow_decimal")) if product else False)

        for ed in (self.ed_name, self.ed_price, self.ed_unit, self.ed_category):
            ed.setMinimumHeight(52)

        form.addRow(i18n.t("prod_name"), self.ed_name)
        form.addRow(i18n.t("prod_price"), self.ed_price)
        form.addRow(i18n.t("prod_unit"), self.ed_unit)
        form.addRow(i18n.t("category") or "Categoría", self.ed_category)
        
        checks = QHBoxLayout()
        checks.addWidget(self.cb_active)
        checks.addWidget(self.cb_partial)
        form.addRow(checks)

        root.addLayout(form)

        row = QHBoxLayout()
        row.setSpacing(12)
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(56)
        btn_ok = QPushButton(i18n.t("ok") or "OK")
        btn_ok.setMinimumHeight(56)
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        root.addLayout(row)

        # OSK en los campos del diálogo
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
        return {
            "name": name,
            "price": cents,
            "active": self.cb_active.isChecked(),
            "unit": unit,
            "allow_decimal": self.cb_partial.isChecked(),
            "category": category,
        }


class EmployeeDialog(QDialog):
    """Diálogo para alta/edición de empleados."""

    def __init__(self, parent=None, *, employee: dict | None = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)
        
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        title = QLabel(i18n.t("employees_title") or "Empleado")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ed_emp_no = QLineEdit(employee["emp_no"] if employee else "")
        self.ed_full_name = QLineEdit(employee["full_name"] if employee else "")
        self.ed_phone = QLineEdit(employee.get("phone", "") if employee else "")
        self.cb_active = QCheckBox(i18n.t("emp_active") or "Activo")
        self.cb_active.setChecked(bool(employee.get("active", 1)) if employee else True)

        for ed in (self.ed_emp_no, self.ed_full_name, self.ed_phone):
            ed.setMinimumHeight(52)

        form.addRow(i18n.t("emp_no") or "No. empleado", self.ed_emp_no)
        form.addRow(i18n.t("emp_name") or "Nombre completo", self.ed_full_name)
        form.addRow(i18n.t("emp_phone") or "Contacto", self.ed_phone)
        form.addRow(self.cb_active)

        root.addLayout(form)

        row = QHBoxLayout()
        row.setSpacing(12)
        btn_cancel = QPushButton(i18n.t("cancel") or "Cancelar")
        btn_cancel.setMinimumHeight(56)
        btn_ok = QPushButton(i18n.t("ok") or "OK")
        btn_ok.setMinimumHeight(56)
        btn_ok.setProperty("role", "primary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        root.addLayout(row)

        # OSK en campos de texto
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


class AdminWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowTitle(i18n.t("admin_title"))
        self._osk_guard = False  # evita reentrancia del OSK
        self._osk_filter = _OskFocusFilter(self)  # <-- crear ANTES de addTab

        top_wrap = QWidget()
        top = QHBoxLayout(top_wrap)
        top.setContentsMargins(16, 16, 16, 8)
        top.setSpacing(16)
        
        title_lbl = QLabel(i18n.t("admin_title") or "Administración")
        title_lbl.setObjectName("SectionTitle")
        title_lbl.setStyleSheet("font-size: 24px;")
        
        self.lang_btn = QPushButton(i18n.t("lang"))
        self.lang_btn.setFixedWidth(80)
        self.lang_btn.setMinimumHeight(52)
        self.lang_btn.setProperty("role", "ghost")
        self.lang_btn.clicked.connect(self._toggle_lang)
        
        btn_close = QPushButton(i18n.t("exit"))
        btn_close.setMinimumHeight(52)
        btn_close.setProperty("role", "danger")
        btn_close.clicked.connect(self._exit_to_kiosk)
        
        top.addWidget(title_lbl)
        top.addStretch(1)
        top.addWidget(self.lang_btn)
        top.addWidget(btn_close)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("AdminTabs")
        self.tabs.addTab(self._tab_security(), i18n.t("tab_security"))
        self.tabs.addTab(self._tab_devices(), i18n.t("tab_devices"))
        self.tabs.addTab(self._tab_store(), i18n.t("tab_store"))
        self.tabs.addTab(self._tab_products(), i18n.t("tab_products"))
        self.tabs.addTab(self._tab_shifts(), i18n.t("tab_shifts") or "Turnos")
        self.tabs.addTab(self._tab_reports(), i18n.t("tab_reports"))
        self.tabs.addTab(self._tab_system(), i18n.t("tab_system"))

        wrap = QWidget()
        wrap.setObjectName("GridPanel") # Reuse GridPanel style for background
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
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

        for wle in (self.pin_in, self.pin_new, self.pin_new2):
            wle.installEventFilter(self._osk_filter)
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
        dlg = ProductDialog(self)
        if dlg.exec():
            data = dlg.data()
            if not data:
                return
            # create_product(*, name, price_money, unit, allow_decimal, active, category)
            create_product(
                name=data["name"],
                price_money=data["price"],  # ya está en centavos; el wrapper acepta int/float/str
                unit=data["unit"],
                allow_decimal=data["allow_decimal"],
                active=data["active"],
                category=data["category"],
            )
            QMessageBox.information(self, i18n.t("tab_products"), i18n.t("prod_saved"))
            self._prod_refresh()

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
            # update_product(product_id, *, name, price_money, unit, allow_decimal, active, category)
            update_product(
                product_id=pid,
                name=data["name"],
                price_money=data["price"],
                unit=data["unit"],
                allow_decimal=data["allow_decimal"],
                active=data["active"],
                category=data["category"],
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

    # ---------- Reports (solo rango de fechas + correo)
    def _tab_reports(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(14)

        # --- Enviar reporte por correo (rango de fechas) ---
        v.addWidget(QLabel(i18n.t("send_mail") or "Enviar reporte"))

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
        txt, _ = report_x()
        QMessageBox.information(self, i18n.t("tab_shifts") or "Turnos", txt)

    def _do_close(self):
        """
        Cierra el turno actual usando report_z() (que ya llama close_shift internamente),
        imprime el reporte y refresca el estado.
        """
        # Comprobamos que haya turno abierto antes de intentar cerrar
        sh = current_shift()
        if not sh:
            self._toast("No hay turno abierto.", level="error")
            return

        # Genera reporte Z (incluye close_shift() por dentro)
        try:
            txt = report_z()
        except Exception as e:
            QMessageBox.critical(
                self,
                i18n.t("tab_shifts") or "Turnos",
                f"Error al cerrar turno: {e}"
            )
            return

        # Intentar imprimir el reporte del turno que acabamos de cerrar
        try:
            EscposPrinter().print_text(txt)
            self._toast(
                f"Turno #{sh['id']} cerrado e impreso.", level="success"
            )
        except Exception as e:
            self._toast(
                f"Turno cerrado pero error al imprimir: {e}", level="error"
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
        self.tbl_employees.setColumnWidth(0, 60)
        self.tbl_employees.setColumnWidth(1, 110)
        self.tbl_employees.setColumnWidth(2, 200)
        self.tbl_employees.setColumnWidth(3, 140)
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
        self.tabs.setTabText(5, i18n.t("tab_reports") or "Reportes")
        self.tabs.setTabText(6, i18n.t("tab_system") or "Sistema")

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

