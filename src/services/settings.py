from __future__ import annotations
from pathlib import Path
from typing import Any, Dict
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"

def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
    if "ui" not in data or not isinstance(data["ui"], dict):
        data["ui"] = {}
    return data


def save_config(cfg: Dict[str, Any]) -> None:
    """Save config.yaml with safety checks."""
    if not isinstance(cfg, dict) or not cfg:
        print("Warning: Attempted to save invalid or empty config. Aborting.")
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)


def is_categories_enabled() -> bool:
    cfg = load_config()
    return bool(cfg.get("ui", {}).get("categories_enabled", True))


def set_categories_enabled(enabled: bool) -> None:
    cfg = load_config()
    ui = cfg.setdefault("ui", {})
    ui["categories_enabled"] = bool(enabled)
    save_config(cfg)


# Default PIN 1234 hashed with argon2id
_DEFAULT_PIN_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$JFE4XiXJTD9iEGWnQdnmuw$G9953rMEA4eGchNqHDFj6FhJZqTf2AlWlk38juIO7/w"
)

_DEFAULT_CONFIG: dict = {
    "store": {
        "name": "Mi Tienda",
        "rfc": "XAXX010101000",
        "ticket_header": "Mi Tienda\n\nRFC: XAXX010101000\n\n",
        "ticket_footer": "Gracias por su compra\n\n",
    },
    "hardware": {
        "printer": {
            "vendor_id": 0x0416,
            "product_id": 0x5011,
            "interface": 0,
            "out_ep": 0x03,
            "in_ep": 0x82,
        },
    },
    "ui": {
        "font_family": "Sans",
        "kiosk_fullscreen": True,
        "categories_enabled": False,
    },
    "security": {
        "admin_pin_hash": _DEFAULT_PIN_HASH,
    },
    "notifications": {
        "email": {
            "gmail_user": "tottem.reports@gmail.com",
            "gmail_pass": "mfexwikphlncahve",
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "use_tls": True,
            "username": "tottem.reports@gmail.com",
            "password": "mfexwikphlncahve",
            "from_addr": "Tottem Reports <tottem.reports@gmail.com>",
        },
        "recent_emails": [],
    },
}


def reset_config_to_defaults() -> None:
    """Overwrite config.yaml with factory defaults."""
    import copy
    save_config(copy.deepcopy(_DEFAULT_CONFIG))
