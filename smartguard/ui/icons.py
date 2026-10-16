"""Iconos SVG del paquete, coloreados con el color de texto del tema activo (claro u oscuro)."""

from functools import cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from smartguard.core.paths import asset


@cache
def _render(name: str, color: str, size: int) -> QPixmap:
    svg = Path(asset("icons", f"{name}.svg")).read_text(encoding="utf-8").replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def icon(name: str, color: QColor | None = None) -> QIcon:
    color = color or QApplication.palette().windowText().color()
    return QIcon(_render(name, color.name(), 128))
