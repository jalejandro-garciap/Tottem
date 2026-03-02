"""
TOTTEM POS · Responsive Scaling Helper
Calculates a scale factor based on screen resolution for adaptive UI sizing.

Reference: 1920×1080 (22" Full HD) → scale = 1.0
Floor: 0.55 (~12" 1366×768)
Ceiling: 1.0 (never scale up beyond reference)
"""

from __future__ import annotations

_scale: float = 1.0
_initialized: bool = False


def _init_scale() -> None:
    """Compute the scale factor once from the primary screen geometry."""
    global _scale, _initialized
    if _initialized:
        return
    _initialized = True
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            sx = geo.width() / 1920.0
            sy = geo.height() / 1080.0
            raw = min(sx, sy)
            _scale = max(0.55, min(raw, 1.0))
    except Exception:
        _scale = 1.0


def get_scale() -> float:
    """Return the current scale factor (0.55–1.0)."""
    _init_scale()
    return _scale


def s(px: int | float) -> int:
    """Scale a pixel value according to the screen factor.

    Usage::

        widget.setMinimumHeight(s(64))
        widget.setContentsMargins(s(16), s(16), s(16), s(16))
    """
    _init_scale()
    return max(1, int(round(px * _scale)))


def font_css(base_px: int | float) -> str:
    """Return a ``font-size: Npx;`` string scaled to the current factor.

    Usage::

        label.setStyleSheet(font_css(28))  # → "font-size: 22px;" on a 12" screen
    """
    return f"font-size: {s(base_px)}px;"
