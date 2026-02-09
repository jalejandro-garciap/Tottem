"""
Themes Service - Manages application themes and color schemes.

Provides predefined themes (Dark Obsidian, Light) and supports
custom theme creation and persistence via config.yaml.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import yaml
from services.settings import load_config, save_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"


# ═══════════════════════════════════════════════════════════════════════════════
# PREDEFINED THEMES
# ═══════════════════════════════════════════════════════════════════════════════

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "name": "Obsidian Oscuro",
        "name_en": "Dark Obsidian",
        # Background colors
        "bg_deep": "#0a0a0f",
        "bg_mid": "#12121a",
        "surface": "#1a1a24",
        "surface_elevated": "#22222e",
        # Text colors
        "text_primary": "#f8fafc",
        "text_secondary": "#94a3b8",
        "text_muted": "#64748b",
        # Accent colors
        "accent_primary": "#6366f1",
        "accent_glow": "#818cf8",
        # Status colors
        "success": "#10b981",
        "warning": "#f59e0b",
        "danger": "#ef4444",
        # UI elements
        "border": "#2a2a3a",
        "border_hover": "#3a3a4a",
    },
    "light": {
        "name": "Claro",
        "name_en": "Light",
        # Background colors
        "bg_deep": "#f8fafc",
        "bg_mid": "#f1f5f9",
        "surface": "#e2e8f0",
        "surface_elevated": "#ffffff",
        # Text colors
        "text_primary": "#0f172a",
        "text_secondary": "#475569",
        "text_muted": "#64748b",
        # Accent colors
        "accent_primary": "#4f46e5",
        "accent_glow": "#6366f1",
        # Status colors
        "success": "#059669",
        "warning": "#d97706",
        "danger": "#dc2626",
        # UI elements
        "border": "#cbd5e1",
        "border_hover": "#94a3b8",
    },
}


# Using load_config and save_config from services.settings


def get_current_theme() -> str:
    """Get the currently active theme name."""
    cfg = load_config()
    return cfg.get("ui", {}).get("theme", "dark")


def set_current_theme(name: str) -> None:
    """Set the active theme."""
    cfg = load_config()
    if "ui" not in cfg:
        cfg["ui"] = {}
    cfg["ui"]["theme"] = name
    save_config(cfg)


def get_theme(name: str) -> Optional[Dict[str, str]]:
    """Get theme colors by name."""
    # Check predefined
    if name in THEMES:
        return THEMES[name].copy()
    # Check custom
    cfg = load_config()
    custom = cfg.get("ui", {}).get("custom_themes", {})
    return custom.get(name)


def list_themes() -> List[Dict[str, Any]]:
    """List all available themes with metadata."""
    themes = []
    # Predefined themes
    for key, data in THEMES.items():
        themes.append({
            "id": key,
            "name": data["name"],
            "name_en": data["name_en"],
            "is_custom": False,
            "colors": data,
        })
    # Custom themes
    cfg = load_config()
    custom = cfg.get("ui", {}).get("custom_themes", {})
    for key, data in custom.items():
        themes.append({
            "id": key,
            "name": data.get("name", key),
            "name_en": data.get("name_en", key),
            "is_custom": True,
            "colors": data,
        })
    return themes


def save_custom_theme(theme_id: str, colors: Dict[str, str]) -> None:
    """Save a custom theme to config."""
    cfg = load_config()
    if "ui" not in cfg:
        cfg["ui"] = {}
    if "custom_themes" not in cfg["ui"]:
        cfg["ui"]["custom_themes"] = {}
    cfg["ui"]["custom_themes"][theme_id] = colors
    save_config(cfg)


def delete_custom_theme(theme_id: str) -> bool:
    """Delete a custom theme. Returns True if deleted."""
    cfg = load_config()
    custom = cfg.get("ui", {}).get("custom_themes", {})
    if theme_id in custom:
        del custom[theme_id]
        save_config(cfg)
        return True
    return False


def generate_qss(colors: Dict[str, str]) -> str:
    """Generate complete QSS stylesheet from color dictionary."""
    return f'''/*
 * TOTTEM POS · GENERATED THEME
 * Auto-generated from theme colors
 */

/* ═══════════════════════════════════════════════════════════════════════════
   FOUNDATION
   ═══════════════════════════════════════════════════════════════════════════ */

QWidget {{
    font-family: "SF Pro Display", "Inter", "Segoe UI", -apple-system, sans-serif;
    font-size: 15px;
    color: {colors["text_primary"]};
    background: {colors["bg_deep"]};
}}

QMainWindow {{
    background: {colors["bg_deep"]};
}}

QDialog {{
    background: {colors["bg_mid"]};
    border: 1px solid {colors["border"]};
    border-radius: 24px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TYPOGRAPHY
   ═══════════════════════════════════════════════════════════════════════════ */

QLabel {{
    font-size: 15px;
    font-weight: 500;
    color: {colors["text_secondary"]};
    background: transparent;
    border: none;
}}

QLabel#SectionTitle {{
    font-size: 24px;
    font-weight: 700;
    color: {colors["text_primary"]};
    letter-spacing: -0.5px;
}}

QLabel#TotalLabel {{
    font-size: 42px;
    font-weight: 800;
    color: {colors["text_primary"]};
}}

QLabel#SubtotalLabel {{
    font-size: 18px;
    font-weight: 600;
    color: {colors["text_secondary"]};
}}

QLabel#EmptyStateLabel {{
    font-size: 16px;
    color: {colors["text_muted"]};
    padding: 40px;
    background: {colors["bg_mid"]};
    border: 2px dashed {colors["border"]};
    border-radius: 20px;
}}

QLabel#PriceTag {{
    font-size: 20px;
    font-weight: 700;
    color: {colors["success"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   CONTAINERS
   ═══════════════════════════════════════════════════════════════════════════ */

#CartPanel {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 {colors["surface"]}, 
                                stop:1 {colors["bg_mid"]});
    border: 1px solid {colors["border"]};
    border-radius: 28px;
    padding: 24px;
}}

#GridPanel {{
    background: transparent;
    border: none;
    border-radius: 28px;
    padding: 24px;
}}

#AdminPanel {{
    background: {colors["bg_mid"]};
    border: 1px solid {colors["surface_elevated"]};
    border-radius: 24px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

QPushButton {{
    font-size: 15px;
    font-weight: 600;
    padding: 16px 24px;
    min-height: 56px;
    border-radius: 16px;
    border: none;
    background: {colors["surface"]};
    color: {colors["text_primary"]};
}}

QPushButton:hover {{
    background: {colors["surface_elevated"]};
}}

QPushButton:pressed {{
    background: {colors["border"]};
}}

QPushButton:disabled {{
    background: {colors["bg_mid"]};
    color: {colors["text_muted"]};
}}

QPushButton[role="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {colors["accent_primary"]}, stop:1 {colors["accent_glow"]});
    color: #ffffff;
    font-weight: 700;
}}

QPushButton[role="primary"]:hover {{
    background: {colors["accent_glow"]};
}}

QPushButton[role="success"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 {colors["success"]}, stop:1 {colors["success"]});
    color: #ffffff;
    font-weight: 700;
}}

QPushButton[role="danger"] {{
    background: rgba(239, 68, 68, 0.15);
    color: {colors["danger"]};
    border: 1px solid {colors["danger"]};
}}

QPushButton[role="danger"]:hover {{
    background: rgba(239, 68, 68, 0.25);
}}

QPushButton[role="ghost"] {{
    background: transparent;
    color: {colors["text_secondary"]};
}}

QPushButton[role="ghost"]:hover {{
    background: {colors["surface"]};
    color: {colors["text_primary"]};
}}

QPushButton[role="outline"] {{
    background: transparent;
    color: {colors["accent_primary"]};
    border: 2px solid {colors["accent_primary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   PRODUCT BUTTONS
   ═══════════════════════════════════════════════════════════════════════════ */

#ProductButton {{
    font-size: 14px;
    font-weight: 600;
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 20px;
    padding: 16px;
    color: {colors["text_primary"]};
}}

#ProductButton:hover {{
    background: {colors["surface_elevated"]};
    border-color: {colors["accent_primary"]};
}}

#CategoryButton {{
    font-size: 16px;
    font-weight: 700;
    background: {colors["surface_elevated"]};
    border: 1px solid {colors["border_hover"]};
    border-radius: 20px;
    color: {colors["text_primary"]};
}}

#CategoryButton:hover {{
    border-color: {colors["accent_primary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   INPUTS
   ═══════════════════════════════════════════════════════════════════════════ */

QLineEdit {{
    font-size: 16px;
    min-height: 56px;
    padding: 14px 20px;
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    background: {colors["bg_mid"]};
    color: {colors["text_primary"]};
    selection-background-color: {colors["accent_primary"]};
}}

QLineEdit:hover {{
    border-color: {colors["border_hover"]};
}}

QLineEdit:focus {{
    border-color: {colors["accent_primary"]};
    background: {colors["surface"]};
}}

QComboBox {{
    font-size: 16px;
    min-height: 56px;
    padding: 14px 20px;
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    background: {colors["bg_mid"]};
    color: {colors["text_primary"]};
}}

QComboBox:hover {{
    border-color: {colors["border_hover"]};
    background: {colors["surface"]};
}}

QComboBox:focus {{
    border-color: {colors["accent_primary"]};
    background: {colors["surface"]};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 40px;
    border-left-width: 0px;
    border-top-right-radius: 16px;
    border-bottom-right-radius: 16px;
    background: transparent;
}}

QComboBox::down-arrow {{
    width: 12px;
    height: 12px;
    margin-right: 12px;
    /* Drawing a simplified CSS arrow using borders if image fails */
    border-left: 2px solid {colors["text_secondary"]};
    border-bottom: 2px solid {colors["text_secondary"]};
    /* Since we can't rotate, we can use a small Unicode character or a simpler indicator */
}}

QComboBox QAbstractItemView {{
    background: {colors["surface"]};
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    selection-background-color: {colors["accent_primary"]};
    selection-color: #ffffff;
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 50px;
    padding: 10px;
    border-radius: 8px;
    margin: 4px;
}}

QSpinBox, QDoubleSpinBox {{
    font-size: 16px;
    min-height: 56px;
    padding: 14px 20px;
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    background: {colors["bg_mid"]};
    color: {colors["text_primary"]};
}}

QTextEdit, QPlainTextEdit {{
    font-size: 15px;
    padding: 16px;
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    background: {colors["bg_mid"]};
    color: {colors["text_primary"]};
}}

QCheckBox {{
    font-size: 15px;
    color: {colors["text_secondary"]};
    spacing: 14px;
}}

QCheckBox::indicator {{
    width: 26px;
    height: 26px;
    border: 2px solid {colors["border_hover"]};
    border-radius: 8px;
    background: {colors["bg_mid"]};
}}

QCheckBox::indicator:checked {{
    background: {colors["accent_primary"]};
    border-color: {colors["accent_primary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   LISTS
   ═══════════════════════════════════════════════════════════════════════════ */

QListWidget {{
    background: transparent;
    border: none;
}}

QListWidget::item {{
    font-size: 15px;
    background: {colors["surface"]};
    border-radius: 14px;
    margin: 6px 0;
    padding: 18px 20px;
    color: {colors["text_primary"]};
}}

QListWidget::item:hover {{
    background: {colors["surface_elevated"]};
}}

QListWidget::item:selected {{
    background: {colors["accent_primary"]};
    color: #ffffff;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   DATE PICKERS
   ═══════════════════════════════════════════════════════════════════════════ */

QDateEdit {{
    font-size: 16px;
    min-height: 56px;
    padding: 14px 20px;
    border: 2px solid {colors["border"]};
    border-radius: 16px;
    background: {colors["bg_mid"]};
    color: {colors["text_primary"]};
}}

QDateEdit:hover, QDateEdit:focus {{
    border-color: {colors["accent_primary"]};
}}

QCalendarWidget {{
    background: {colors["surface"]};
    border: 2px solid {colors["accent_primary"]};
    border-radius: 20px;
}}

QCalendarWidget QToolButton {{
    background: {colors["surface_elevated"]};
    color: {colors["text_primary"]};
    border-radius: 10px;
}}

QCalendarWidget QToolButton:hover {{
    background: {colors["accent_primary"]};
}}

QCalendarWidget QAbstractItemView {{
    background: {colors["surface"]};
    selection-background-color: {colors["accent_primary"]};
    color: {colors["text_primary"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TABLES
   ═══════════════════════════════════════════════════════════════════════════ */

QTableWidget {{
    background: {colors["bg_mid"]};
    border: none;
    border-radius: 20px;
    gridline-color: {colors["surface"]};
    selection-background-color: {colors["accent_primary"]};
}}

QTableWidget::item {{
    padding: 16px 20px;
    color: {colors["text_primary"]};
}}

QTableWidget::item:selected {{
    background: {colors["accent_primary"]};
    color: #ffffff;
}}

QHeaderView::section {{
    font-size: 12px;
    font-weight: 700;
    background: {colors["surface"]};
    color: {colors["text_muted"]};
    padding: 18px 20px;
    border: none;
    border-bottom: 1px solid {colors["border"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════════════════════ */

QTabWidget::pane {{
    background: {colors["bg_mid"]};
    border: 1px solid {colors["border"]};
    border-radius: 24px;
    padding: 20px;
}}

QTabBar::tab {{
    font-size: 14px;
    font-weight: 600;
    background: transparent;
    color: {colors["text_muted"]};
    padding: 16px 28px;
    border-radius: 12px;
}}

QTabBar::tab:hover {{
    background: {colors["surface"]};
    color: {colors["text_secondary"]};
}}

QTabBar::tab:selected {{
    background: {colors["accent_primary"]};
    color: #ffffff;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   SCROLLBARS
   ═══════════════════════════════════════════════════════════════════════════ */

QScrollBar:vertical {{
    background: transparent;
    width: 20px;
    margin: 8px 2px;
}}

QScrollBar::handle:vertical {{
    background: {colors["border_hover"]};
    min-height: 60px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: {colors["text_muted"]};
}}

QScrollBar::handle:vertical:pressed {{
    background: {colors["accent_primary"]};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 20px;
}}

QScrollBar::handle:horizontal {{
    background: {colors["border_hover"]};
    min-width: 60px;
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   KEYPAD
   ═══════════════════════════════════════════════════════════════════════════ */

#KeypadButton {{
    font-size: 28px;
    font-weight: 700;
    min-width: 80px;
    min-height: 80px;
    border-radius: 20px;
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    color: {colors["text_primary"]};
}}

#KeypadButton:hover {{
    background: {colors["surface_elevated"]};
}}

#KeypadButton:pressed {{
    background: {colors["border"]};
    border-color: {colors["accent_primary"]};
}}

#KeypadButton[role="primary"] {{
    background: {colors["accent_primary"]};
    color: #ffffff;
}}

#KeypadButton[role="danger"] {{
    background: rgba(239, 68, 68, 0.15);
    color: {colors["danger"]};
}}

/* ═══════════════════════════════════════════════════════════════════════════
   TOASTS
   ═══════════════════════════════════════════════════════════════════════════ */

#ToastFrame {{
    background: {colors["surface_elevated"]};
    color: {colors["text_primary"]};
    border-radius: 16px;
    border: 1px solid {colors["border"]};
    padding: 18px 28px;
}}

#ToastFrame[toastLevel="success"] {{
    background: {colors["success"]};
    border: none;
}}

#ToastFrame[toastLevel="error"] {{
    background: {colors["danger"]};
    border: none;
}}

#ToastFrame[toastLevel="warning"] {{
    background: {colors["warning"]};
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   GROUP BOX
   ═══════════════════════════════════════════════════════════════════════════ */

QGroupBox {{
    font-size: 12px;
    font-weight: 700;
    color: {colors["text_muted"]};
    border: 1px solid {colors["surface_elevated"]};
    border-radius: 20px;
    margin-top: 24px;
    padding: 24px 20px 20px 20px;
    background: {colors["bg_mid"]};
}}

QGroupBox::title {{
    background: {colors["bg_mid"]};
    padding: 0 16px;
}}

/* ═══════════════════════════════════════════════════════════════════════════
   MISC
   ═══════════════════════════════════════════════════════════════════════════ */

QScrollArea {{
    background: transparent;
    border: none;
}}

QProgressBar {{
    background: {colors["surface"]};
    border: none;
    border-radius: 10px;
    height: 20px;
    color: {colors["text_secondary"]};
}}

QProgressBar::chunk {{
    background: {colors["accent_primary"]};
    border-radius: 10px;
}}

QMenu {{
    background: {colors["surface"]};
    border: 1px solid {colors["border"]};
    border-radius: 16px;
}}

QMenu::item {{
    padding: 14px 24px;
    border-radius: 10px;
    color: {colors["text_primary"]};
}}

QMenu::item:selected {{
    background: {colors["accent_primary"]};
    color: #ffffff;
}}

QToolTip {{
    font-size: 13px;
    background: {colors["surface_elevated"]};
    color: {colors["text_primary"]};
    border: 1px solid {colors["border_hover"]};
    border-radius: 10px;
    padding: 10px 14px;
}}

QMessageBox {{
    background: {colors["bg_mid"]};
}}

QMessageBox QLabel {{
    color: {colors["text_primary"]};
}}

QLabel#IconLabel {{
    font-family: "Font Awesome 6 Free";
    font-weight: 900;
    color: {colors["accent_glow"]};
    background: transparent;
}}

QLabel#IconLabel[state="error"] {{
    color: {colors["danger"]};
}}

QLabel#IconLabel[state="success"] {{
    color: {colors["success"]};
}}

QLabel#IconLabel[state="warning"] {{
    color: {colors["warning"]};
}}
'''


def apply_theme(app, theme_name: str) -> bool:
    """Apply a theme to the application. Returns True if successful."""
    colors = get_theme(theme_name)
    if not colors:
        return False
    
    qss = generate_qss(colors)
    app.setStyleSheet(qss)
    set_current_theme(theme_name)
    return True
