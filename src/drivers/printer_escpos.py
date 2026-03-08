# src/drivers/printer_escpos.py
from __future__ import annotations
from typing import Iterable, Callable
from pathlib import Path
import time
import yaml

import usb.core
import usb.util
from usb.core import USBError

from services.receipts import render_ticket
from services.sales import CartItem


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"

_MAX_RETRIES = 3
_RETRY_DELAY = 0.4  # seconds between retries


def _load_cfg() -> dict:
    try:
        raw = CONFIG_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        return yaml.safe_load(raw) or {}
    except Exception:
        return {}


class EscposPrinter:
    """
    ESC/POS driver using pyusb directly.

    - Lee VID/PID/interface/EPs de config/config.yaml.
    - Abre y cierra el dispositivo en CADA operación (no mantiene 'self.dev' abierto).
    - Implementa reintentos automáticos para recuperarse de errores USB transitorios.
    """

    def __init__(self):
        cfg = _load_cfg().get("hardware", {}).get("printer", {}) or {}
        self.vid = int(cfg.get("vendor_id") or 0)
        self.pid = int(cfg.get("product_id") or 0)
        self.interface = int(cfg.get("interface") or 0)
        self.cfg_out_ep = cfg.get("out_ep")
        self.cfg_in_ep = cfg.get("in_ep")

    # ---------- low level open/close ----------

    def _open_dev(self) -> tuple[usb.core.Device, int]:
        """Abre el dispositivo y devuelve (dev, out_ep)."""
        if not self.vid or not self.pid:
            raise RuntimeError("Impresora ESC/POS no configurada (VID/PID).")

        dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if dev is None:
            raise RuntimeError("USB printer not found")

        try:
            if dev.is_kernel_driver_active(self.interface):
                dev.detach_kernel_driver(self.interface)
        except Exception:
            pass

        dev.set_configuration()
        cfg = dev.get_active_configuration()
        intf = cfg[(self.interface, 0)]

        out_ep = self.cfg_out_ep
        if out_ep is None:
            for ep in intf.endpoints():
                addr = ep.bEndpointAddress
                if not (addr & 0x80):  # OUT
                    out_ep = addr
                    break

        if out_ep is None:
            usb.util.dispose_resources(dev)
            raise RuntimeError("No OUT endpoint found for printer")

        return dev, out_ep

    def _close_dev(self, dev: usb.core.Device | None):
        """Libera la interfaz USB y los recursos del dispositivo de forma segura."""
        if dev is None:
            return
        try:
            usb.util.release_interface(dev, self.interface)
        except Exception:
            pass
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass

    def _with_printer(self, fn: Callable[[Callable[[bytes], None]], None]):
        """
        Abre el dispositivo, ejecuta fn(write) y cierra al terminar.
        Incluye reintentos automáticos para recuperarse de errores USB transitorios.

        fn: función que recibe 'write(data: bytes)' para enviar datos al printer.
        """
        last_err = None
        for attempt in range(_MAX_RETRIES):
            dev = None
            try:
                dev, out_ep = self._open_dev()

                def write(data: bytes):
                    dev.write(out_ep, data, timeout=3000)

                fn(write)
                return  # success
            except USBError as e:
                last_err = e
                print(f"[WARN] USB attempt {attempt + 1}/{_MAX_RETRIES} failed: {e}")
            except Exception as e:
                last_err = e
                print(f"[WARN] Printer attempt {attempt + 1}/{_MAX_RETRIES} failed: {e}")
            finally:
                self._close_dev(dev)

            # Wait before retry
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_DELAY)

        # All retries exhausted
        raise RuntimeError(f"Printer operation failed after {_MAX_RETRIES} attempts: {last_err}")

    # ---------- ESC/POS helpers ----------

    @staticmethod
    def _normalize_text(text: str) -> str:
        txt = text.replace("\r\n", "\n").replace("\r", "\n")
        if not txt.endswith("\n"):
            txt += "\n"
        return txt

    # ---------- Public API used by the app ----------

    def selftest(self):
        """Imprime una prueba simple de impresora."""
        def _do(write):
            # ESC @ (init)
            write(b"\x1b\x40")
            write(b"*** PRUEBA DE IMPRESORA ***\n\n")
            write(b"1234567890\nABCDEFGHIJKLMNOPQRSTUVWXYZ\n\n")
            # corte parcial
            write(b"\x1d\x56\x42\x00")

        self._with_printer(_do)

    def open_drawer(self):
        """Pulso de cajón de dinero (pin 2)."""
        def _do(write):
            # ESC p m t1 t2  -> pin 0, 50ms on, 50ms off
            write(b"\x1b\x70\x00\x32\x32")

        self._with_printer(_do)

    def print_cart(self, items: Iterable[CartItem]):
        """Imprime un ticket a partir de una lista de CartItem."""
        text = render_ticket(items)
        self.print_text(text)

    def print_text(self, text: str):
        """Imprime texto plano (más dos saltos de línea y corte)."""
        normalized = self._normalize_text(text)

        def _do(write):
            # ESC @ (init)
            write(b"\x1b\x40")
            write(normalized.encode("utf-8", errors="ignore"))
            write(b"\n\n")
            # corte parcial
            write(b"\x1d\x56\x42\x00")

        self._with_printer(_do)

    def print_and_open_drawer(self, text: str) -> tuple[bool, bool]:
        """Imprime texto y abre el cajón en una sola sesión USB.
        
        Combina ambas operaciones para evitar problemas de reconexión USB
        cuando se ejecutan print_text + open_drawer en secuencia rápida.
        
        El cajón se abre SIEMPRE, incluso si la impresión falla (e.g. sin papel).
        
        Returns:
            (print_ok, drawer_ok) — tupla indicando si cada operación fue exitosa.
        """
        normalized = self._normalize_text(text)
        results = {"print_ok": False, "drawer_ok": False}

        def _do(write):
            # --- Intentar imprimir (puede fallar por falta de papel) ---
            try:
                # ESC @ (init)
                write(b"\x1b\x40")
                write(normalized.encode("utf-8", errors="ignore"))
                write(b"\n\n")
                # corte parcial
                write(b"\x1d\x56\x42\x00")
                results["print_ok"] = True
            except Exception as e:
                print(f"[WARN] Print failed (paper out?): {e}")

            # --- Siempre intentar abrir cajón ---
            try:
                time.sleep(0.15)
                # ESC p m t1 t2  -> abrir cajón pin 0, 50ms on, 50ms off
                write(b"\x1b\x70\x00\x32\x32")
                results["drawer_ok"] = True
            except Exception as e:
                print(f"[WARN] Drawer open failed: {e}")

        self._with_printer(_do)
        return (results["print_ok"], results["drawer_ok"])
