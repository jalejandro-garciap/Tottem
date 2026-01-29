from __future__ import annotations
from pathlib import Path
import yaml
from argon2 import PasswordHasher, exceptions as argon_exc

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _load_settings() -> dict:
    try:
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


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
    s = _load_settings()
    h = s.get("security", {}).get("admin_pin_hash", "")
    if not h or not pin:
        return False
    ph = PasswordHasher()
    try:
        ph.verify(h, pin)
        return True
    except (argon_exc.VerifyMismatchError, Exception):
        return False

