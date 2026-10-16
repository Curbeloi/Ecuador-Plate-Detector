"""Widgets reutilizables: vista de video, selector de cámara y panel de cámara en vivo."""

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from smartguard.core.config import Settings

if TYPE_CHECKING:
    from smartguard.core.camera_manager import CameraManager


class VideoView(QWidget):
    """Muestra el último frame escalado sin deformarlo y traduce clics a coordenadas del frame."""

    clicked = Signal(QPointF)
    rightClicked = Signal()

    def __init__(self, placeholder: str = "Esperando video…", parent=None):
        super().__init__(parent)
        self.placeholder = placeholder
        self.image: QImage | None = None
        self.overlay: list[QPointF] = []
        """Puntos en coordenadas del frame que se están dibujando (línea o zona de conteo)."""
        self.overlay_closed = False
        self.setMinimumSize(320, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, image: QImage) -> None:
        self.image = image
        self.update()

    def clear(self, placeholder: str | None = None) -> None:
        self.image = None
        if placeholder:
            self.placeholder = placeholder
        self.update()

    def _target(self) -> QRectF:
        if self.image is None:
            return QRectF()
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def to_frame(self, pos: QPointF) -> QPointF | None:
        target = self._target()
        if self.image is None or not target.contains(pos):
            return None
        scale = self.image.width() / target.width()
        return QPointF((pos.x() - target.x()) * scale, (pos.y() - target.y()) * scale)

    def to_widget(self, point: QPointF) -> QPointF:
        target = self._target()
        scale = target.width() / self.image.width()
        return QPointF(target.x() + point.x() * scale, target.y() + point.y() * scale)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111"))
        if self.image is None:
            painter.setPen(QColor("#bbb"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self._target(), self.image)
        if self.overlay:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(QPen(QColor("#00e5ff"), 3, Qt.PenStyle.DashLine))
            points = [self.to_widget(p) for p in self.overlay]
            for a, b in zip(points, points[1:], strict=False):
                painter.drawLine(a, b)
            if self.overlay_closed and len(points) > 2:
                painter.drawLine(points[-1], points[0])
            painter.setBrush(QColor("#00e5ff"))
            for p in points:
                painter.drawEllipse(p, 5, 5)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.rightClicked.emit()
        elif (point := self.to_frame(event.position())) is not None:
            self.clicked.emit(point)


class CameraSelector(QComboBox):
    """Combo con las cámaras habilitadas; ``currentData()`` es el id de la cámara."""

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.set_settings(settings)

    def set_settings(self, settings: Settings) -> None:
        current = self.currentData()
        self.blockSignals(True)
        self.clear()
        for camera in settings.cameras:
            if camera.enabled:
                self.addItem(camera.name, camera.id)
        index = self.findData(current)
        self.setCurrentIndex(max(index, 0))
        self.blockSignals(False)
        self.currentIndexChanged.emit(self.currentIndex())


class LiveCameraPanel(QWidget):
    """Selector de cámara + estado + video en vivo de la cámara elegida."""

    cameraChanged = Signal()

    def __init__(self, settings: Settings, manager: "CameraManager", parent=None):
        super().__init__(parent)
        self.manager = manager
        self.selector = CameraSelector(settings)
        self.status = QLabel()
        self.status.setProperty("role", "kpi-caption")
        self.video = VideoView()
        header = QHBoxLayout()
        header.addWidget(QLabel("Cámara:"))
        header.addWidget(self.selector, 1)
        header.addWidget(self.status)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.video, 1)
        self.selector.currentIndexChanged.connect(self._camera_changed)
        manager.frameReady.connect(self._on_frame)
        manager.statusChanged.connect(self._on_status)
        self._camera_changed()

    @property
    def camera_id(self) -> str:
        return self.selector.currentData() or ""

    def set_settings(self, settings: Settings) -> None:
        self.selector.set_settings(settings)

    def _camera_changed(self) -> None:
        self.video.clear("Esperando video…")
        self.status.setText(self.manager.status(self.camera_id))
        self.cameraChanged.emit()

    def _on_frame(self, camera_id: str, image) -> None:
        if camera_id == self.camera_id and self.isVisible():
            self.video.set_image(image)

    def _on_status(self, camera_id: str, text: str) -> None:
        if camera_id == self.camera_id:
            self.status.setText(text)
