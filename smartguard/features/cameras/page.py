"""Mosaico con todas las cámaras habilitadas del condominio."""

import math

from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from smartguard.core.camera_manager import CameraManager
from smartguard.core.config import Settings
from smartguard.ui.widgets import VideoView


class CameraTile(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.title = QLabel(f"<b>{name}</b>")
        self.status = QLabel()
        self.status.setProperty("role", "kpi-caption")
        self.video = VideoView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.title)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.status)


class CamerasPage(QWidget):
    def __init__(self, settings: Settings, manager: CameraManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.tiles: dict[str, CameraTile] = {}
        self.grid = QGridLayout(self)
        self.empty = QLabel("No hay cámaras habilitadas. Agregue una en Configuración.")
        self.grid.addWidget(self.empty, 0, 0)
        manager.frameReady.connect(self._on_frame)
        manager.statusChanged.connect(self._on_status)
        self.set_settings(settings)

    def set_settings(self, settings: Settings) -> None:
        for tile in self.tiles.values():
            tile.deleteLater()
        self.tiles.clear()
        cameras = [c for c in settings.cameras if c.enabled]
        self.empty.setVisible(not cameras)
        columns = math.ceil(math.sqrt(len(cameras)))
        for i, camera in enumerate(cameras):
            tile = CameraTile(camera.name)
            tile.status.setText(self.manager.status(camera.id))
            self.tiles[camera.id] = tile
            self.grid.addWidget(tile, i // columns, i % columns)

    def _on_frame(self, camera_id: str, image) -> None:
        if self.isVisible() and (tile := self.tiles.get(camera_id)):
            tile.video.set_image(image)

    def _on_status(self, camera_id: str, text: str) -> None:
        if tile := self.tiles.get(camera_id):
            tile.status.setText(text)
