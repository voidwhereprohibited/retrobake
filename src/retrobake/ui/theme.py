"""Plain, high-contrast theme for the RetroBake wizard.

Fonts are always set in points (never pixels) so the whole app scales with
the user's system setting and with RetroBake's own Ctrl+/Ctrl- zoom.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

BASE_POINT_SIZE = 11
MIN_SCALE = 0.8
MAX_SCALE = 2.0
SCALE_STEP = 0.1


@dataclass(frozen=True)
class Colors:
    window: str
    surface: str
    text: str
    muted: str
    accent: str
    accent_text: str
    border: str
    focus: str


LIGHT = Colors(
    window="#F4F1EA",
    surface="#FFFFFF",
    text="#1B1B1F",
    muted="#4A4A55",
    accent="#B3261E",
    accent_text="#FFFFFF",
    border="#8A8A95",
    focus="#1A56DB",
)

DARK = Colors(
    window="#17171C",
    surface="#24242B",
    text="#F2F2F5",
    muted="#C4C4CF",
    accent="#FF8A7A",
    accent_text="#1B1B1F",
    border="#6E6E7A",
    focus="#8AB4FF",
)


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    chans = []
    for v in (c.redF(), c.greenF(), c.blueF()):
        chans.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = chans
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two colors."""
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def system_prefers_dark() -> bool:
    hints = QGuiApplication.styleHints()
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt < 6.5
        return False


def palette_for(colors: Colors) -> QPalette:
    p = QPalette()
    role = QPalette.ColorRole
    p.setColor(role.Window, QColor(colors.window))
    p.setColor(role.WindowText, QColor(colors.text))
    p.setColor(role.Base, QColor(colors.surface))
    p.setColor(role.AlternateBase, QColor(colors.window))
    p.setColor(role.Text, QColor(colors.text))
    p.setColor(role.Button, QColor(colors.surface))
    p.setColor(role.ButtonText, QColor(colors.text))
    p.setColor(role.Highlight, QColor(colors.accent))
    p.setColor(role.HighlightedText, QColor(colors.accent_text))
    p.setColor(role.PlaceholderText, QColor(colors.muted))
    p.setColor(role.ToolTipBase, QColor(colors.surface))
    p.setColor(role.ToolTipText, QColor(colors.text))
    p.setColor(role.Link, QColor(colors.focus))
    return p


def stylesheet(colors: Colors) -> str:
    # No font sizes here on purpose: sizes come from QFont so zoom works.
    return f"""
    QWidget#WizardRoot {{ background: {colors.window}; }}
    QLabel[role="title"] {{ color: {colors.text}; font-weight: 700; }}
    QLabel[role="subtitle"], QLabel[role="hint"] {{ color: {colors.muted}; }}
    QProgressBar {{ background: {colors.surface}; border: 1px solid {colors.border};
        border-radius: 4px; }}
    QProgressBar::chunk {{ background: {colors.accent}; border-radius: 3px; }}
    QFrame#Card {{
        background: {colors.surface}; border: 1px solid {colors.border}; border-radius: 12px;
    }}
    QPushButton {{
        min-height: 2.4em; padding: 6px 22px; border-radius: 10px;
        border: 1px solid {colors.border}; background: {colors.surface}; color: {colors.text};
    }}
    QPushButton:default, QPushButton[primary="true"] {{
        background: {colors.accent}; color: {colors.accent_text};
        border: 1px solid {colors.accent};
    }}
    QPushButton:disabled {{ color: {colors.muted}; background: {colors.window}; }}
    QPushButton:focus, QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus,
    QRadioButton:focus, QCheckBox:focus {{
        outline: none; border: 3px solid {colors.focus};
    }}
    QComboBox, QLineEdit, QPlainTextEdit {{
        min-height: 2.2em; padding: 4px 8px; border-radius: 8px;
        border: 1px solid {colors.border}; background: {colors.surface}; color: {colors.text};
    }}
    QScrollArea {{ border: none; background: transparent; }}
    """


def apply_theme(app: QApplication, dark: bool | None = None, scale: float = 1.0) -> Colors:
    """Apply palette, stylesheet and base font. Returns the colors used."""
    if dark is None:
        dark = system_prefers_dark()
    colors = DARK if dark else LIGHT
    app.setStyle("Fusion")  # same modern look on Windows and Ubuntu
    app.setPalette(palette_for(colors))
    app.setStyleSheet(stylesheet(colors))
    set_font_scale(app, scale)
    return colors


def clamp_scale(scale: float) -> float:
    return round(max(MIN_SCALE, min(MAX_SCALE, scale)), 2)


def set_font_scale(app: QApplication, scale: float) -> float:
    scale = clamp_scale(scale)
    font = QFont(app.font())
    font.setPointSizeF(BASE_POINT_SIZE * scale)
    app.setFont(font)
    return scale
