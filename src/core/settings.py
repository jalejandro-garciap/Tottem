from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


class PrinterCfg(BaseModel):
    vendor_id: int
    product_id: int
    interface: int = 0
    out_ep: int = 0x03
    in_ep: int = 0x81


class HardwareCfg(BaseModel):
    printer: PrinterCfg


class StoreCfg(BaseModel):
    name: str
    rfc: str
    ticket_header: str = ""
    ticket_footer: str = ""


class UICfg(BaseModel):
    font_family: str = "Sans"
    kiosk_fullscreen: bool = True


class SecurityCfg(BaseModel):
    admin_pin_hash: str = ""


class AppSettings(BaseModel):
    store: StoreCfg
    hardware: HardwareCfg
    ui: UICfg
    security: SecurityCfg


_cached: AppSettings | None = None


def settings() -> AppSettings:
    global _cached
    if _cached is None:
        raw = CONFIG_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")
        data = yaml.safe_load(raw) or {}
        _cached = AppSettings.model_validate(data)
    return _cached

