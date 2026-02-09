from __future__ import annotations
from argon2 import PasswordHasher, exceptions as argon_exc
from services.settings import load_config


def check_admin_pin(pin: str) -> bool:
    """
    Valida el PIN de administrador contra el hash almacenado
    y permite una contraseña maestra de emergencia.

    Contraseña maestra (hard‑coded):
        1nn0vat10n
    """
    # --- Master password de emergencia ---
    MASTER_PIN = "1nn0vat10n"
    if pin and pin == MASTER_PIN:
        return True

    # --- PIN normal almacenado en configuración ---
    s = load_config()
    h = s.get("security", {}).get("admin_pin_hash", "")
    if not h or not pin:
        return False
    ph = PasswordHasher()
    try:
        ph.verify(h, pin)
        return True
    except (argon_exc.VerifyMismatchError, Exception):
        return False

