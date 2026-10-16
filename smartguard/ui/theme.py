"""Colores y estilos compartidos por las páginas."""

from smartguard.core.db import AUTHORIZED, BLOCKED, UNKNOWN

DECISION_COLORS = {AUTHORIZED: "#1e8e3e", BLOCKED: "#d93025", UNKNOWN: "#f29900"}


def text_color_for(background: str) -> str:
    """Negro o blanco según la luminancia del fondo, para que el texto siempre se lea."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    return "#202124" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 else "#ffffff"


def badge_style(background: str) -> str:
    return f"background:{background}; color:{text_color_for(background)}; border-radius:6px; padding:2px 8px;"

STYLESHEET = """
QToolBar { spacing: 6px; padding: 4px; }
QToolButton { padding: 6px 10px; border-radius: 8px; }
QToolButton:checked { background: palette(highlight); color: palette(highlighted-text); }
QGroupBox { font-weight: 600; }
QLabel[role="kpi"] { font-size: 26px; font-weight: 700; }
QLabel[role="kpi-caption"] { color: palette(placeholder-text); }
QLabel[role="title"] { font-size: 18px; font-weight: 700; }
"""
