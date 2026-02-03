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


def get_theme() -> str:
    cfg = load_config()
    theme = str(cfg.get("ui", {}).get("theme", "dark")).lower()
    return "light" if theme == "light" else "dark"


def set_theme(theme: str) -> None:
    cfg = load_config()
    ui = cfg.setdefault("ui", {})
    ui["theme"] = "light" if str(theme).lower() == "light" else "dark"
    save_config(cfg)
