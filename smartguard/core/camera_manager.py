"""Arranca un ``CameraWorker`` por cámara habilitada y reenvía sus señales a la interfaz."""

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from smartguard.core.camera_worker import CameraWorker
from smartguard.core.config import Settings
from smartguard.vision.counting import CounterConfig


class CameraManager(QObject):
    frameReady = Signal(str, object)
    accessEvent = Signal(str, object)
    countsChanged = Signal(str, object)
    statusChanged = Signal(str, str)
    weaponAlert = Signal(str, object)

    def __init__(self, settings: Settings, db_path: Path, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.db_path = db_path
        self.workers: dict[str, CameraWorker] = {}

    def start(self) -> None:
        for camera in self.settings.cameras:
            if camera.enabled:
                worker = CameraWorker(camera, self.settings, self.db_path, self)
                worker.frameReady.connect(self.frameReady)
                worker.accessEvent.connect(self.accessEvent)
                worker.countsChanged.connect(self.countsChanged)
                worker.statusChanged.connect(self.statusChanged)
                worker.weaponAlert.connect(self.weaponAlert)
                self.workers[camera.id] = worker
                worker.start()

    def stop(self) -> None:
        for worker in self.workers.values():
            worker.stop()
        for worker in self.workers.values():
            worker.wait(5000)
        self.workers.clear()

    def restart(self, settings: Settings) -> None:
        self.stop()
        self.settings = settings
        self.start()

    def status(self, camera_id: str) -> str:
        worker = self.workers.get(camera_id)
        return worker.status if worker else "Deshabilitada"

    def set_counter(self, camera_id: str, config: CounterConfig | None) -> None:
        if worker := self.workers.get(camera_id):
            worker.set_counter(config)
