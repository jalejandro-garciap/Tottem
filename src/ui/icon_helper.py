"""
TOTTEM POS · Icon Helper
FontAwesome 6 Free Integration for Raspbian Lite
"""
from PySide6.QtGui import QFontDatabase, QFont
from PySide6.QtCore import QFile
from pathlib import Path

# Icon font path
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONT_PATH = ASSETS_DIR / "fonts" / "fa-solid-900.ttf"

# FontAwesome 6 Free Solid icon mapping (common POS icons)
ICON_MAP = {
    # Products & Food
    "utensils": "\uf2e7",
    "coffee": "\uf0f4",
    "pizza-slice": "\uf818",
    "burger": "\uf805",
    "ice-cream": "\uf810",
    "bottle-water": "\ue4c5",
    "wine-glass": "\uf4e3",
    "cookie": "\uf563",
    "bread-slice": "\uf7ec",
    "cheese": "\uf7ef",
    "fish": "\uf578",
    "drumstick-bite": "\uf6d7",
    "carrot": "\uf787",
    "apple-whole": "\uf5d1",
    "lemon": "\uf094",
    
    # Categories
    "tags": "\uf02c",
    "box": "\uf466",
    "bags-shopping": "\uf847",
    "basket-shopping": "\uf291",
    "cart-shopping": "\uf07a",
    
    # Actions
    "print": "\uf02f",
    "gear": "\uf013",
    "lock": "\uf023",
    "check": "\uf00c",
    "xmark": "\uf00d",
    "plus": "\u002b",
    "minus": "\u2212",
    "arrow-right": "\uf061",
    "arrow-left": "\uf060",
    "keyboard": "\uf11c",
    
    # Money
    "dollar-sign": "\u0024",
    "coins": "\uf51e",
    "money-bill": "\uf0d6",
    "cash-register": "\uf788",
    "circle-check": "\uf058",
}


class IconHelper:
    """Helper class for FontAwesome icon management"""
    
    _font_loaded = False
    _font_family = None
    
    @classmethod
    def load_font(cls) -> bool:
        """Load FontAwesome font into application. Call once at startup."""
        if cls._font_loaded:
            return True
        
        if not FONT_PATH.exists():
            print(f"WARNING: FontAwesome font not found at {FONT_PATH}")
            return False
        
        font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
        if font_id < 0:
            print(f"ERROR: Failed to load FontAwesome font from {FONT_PATH}")
            return False
        
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            cls._font_family = families[0]
            cls._font_loaded = True
            print(f"✓ FontAwesome loaded: {cls._font_family}")
            return True
        
        return False
    
    @classmethod
    def get_icon_char(cls, icon_name: str) -> str:
        """Get Unicode character for icon name. Returns empty string if not found."""
        return ICON_MAP.get(icon_name, "")
    
    @classmethod
    def get_font(cls, size: int = 16, weight: int = 900) -> QFont:
        """Create QFont configured for FontAwesome icons."""
        if not cls._font_loaded:
            cls.load_font()
        
        font = QFont(cls._font_family or "Font Awesome 6 Free", size)
        font.setWeight(weight)
        return font
    
    @classmethod
    def has_icon(cls, icon_name: str) -> bool:
        """Check if icon name exists in map."""
        return icon_name in ICON_MAP
    
    @classmethod
    def format_with_icon(cls, icon_name: str, text: str) -> str:
        """Format text with icon character prefix. Returns text only if icon not found."""
        icon_char = cls.get_icon_char(icon_name)
        if icon_char:
            return f"{icon_char}  {text}"
        return text


def get_icon_char(icon_name: str) -> str:
    """Convenience function to get icon character."""
    return IconHelper.get_icon_char(icon_name)


def load_icon_font() -> bool:
    """Convenience function to load icon font."""
    return IconHelper.load_font()
