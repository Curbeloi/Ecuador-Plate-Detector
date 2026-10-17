"""Un hilo por cámara: lee video, ejecuta el pipeline y registra los eventos."""

import logging
import threading
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from smartguard.core.config import Camera, Settings
from smartguard.core.db import Database
from smartguard.core.frame_utils import to_qimage
from smartguard.core.recorder import EventRecorder
from smartguard.core.video_source import FrameGrabber, VideoSource, describe_source
from smartguard.vision.counting import CounterConfig, CountTotals

log = logging.getLogger(__name__)

RETRY_SECONDS = 5


def _snapshot(totals: CountTotals | None) -> CountTotals | None:
    """Copia para la interfaz: el hilo de la cámara sigue modificando el original."""
    return CountTotals(totals.by_label.copy(), totals.by_direction.copy()) if totals else None


class CameraWorker(QThread):
    frameReady = Signal(str, object)
    """(camera_id, QImage)"""
    accessEvent = Signal(str, object)
    """(camera_id, AccessEvent)"""
    countsChanged = Signal(str, object)
    """(camera_id, CountTotals)"""
    weaponAlert = Signal(str, object)
    """(camera_id, WeaponEvent)"""
    statusChanged = Signal(str, str)
    """(camera_id, texto)"""

    def __init__(self, camera: Camera, settings: Settings, db_path: Path, parent=None):
        super().__init__(parent)
        self.camera = camera
        self.settings = settings
        self.db_path = db_path
        self.status = "Detenida"
        self._lock = threading.Lock()
        self._pending_counter: tuple[CounterConfig | None] | None = None
        self._stop_event = threading.Event()

    # --- API para el hilo de la interfaz ----------------------------------------------------

    def set_counter(self, config: CounterConfig | None) -> None:
        with self._lock:
            self._pending_counter = (config,)

    def stop(self) -> None:
        self._stop_event.set()

    # --- Hilo de la cámara -------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self.status = text
        self.statusChanged.emit(self.camera.id, text)

    def run(self) -> None:
        from smartguard.vision.pipeline import Pipeline  # carga torch/onnx fuera del hilo de la interfaz

        db = Database(self.db_path)
        recorder = EventRecorder(db, self.settings.captures_path, self.camera.name, self.settings.repeat_cooldown_s)
        pipeline = None
        try:
            self._set_status("Cargando modelos…")
            try:
                pipeline = Pipeline(self.settings, self.camera)
            except Exception as error:  # sin internet en la primera descarga, modelo corrupto...
                log.exception("No se pudieron cargar los modelos")
                self._set_status(f"Error al cargar modelos: {error}")
                return
            while not self._stop_event.is_set():
                if not self._stream(pipeline, recorder):
                    break
        finally:
            if pipeline:
                for shot in pipeline.finish():
                    recorder.record_shot(shot)
            db.close()
            self._set_status("Detenida")

    def _stream(self, pipeline, recorder: EventRecorder) -> bool:
        """Transmite hasta que la fuente se corta. Devuelve ``False`` si no hay que reintentar."""
        name = describe_source(self.camera.source)
        video = VideoSource(self.camera.source, loop=self.camera.loop_video)
        self._set_status(f"Conectando a {name}…")
        if not video.open():
            self._set_status(f"No se pudo abrir {name}. Reintento en {RETRY_SECONDS} s")
            self._stop_event.wait(RETRY_SECONDS)
            return True
        grabber = FrameGrabber(video)
        grabber.start()
        seq, frames, window_start = 0, 0, time.monotonic()
        interval = 1 / max(self.camera.max_fps, 1)
        next_due = time.monotonic()
        try:
            while not self._stop_event.is_set():
                # El grabber guarda solo el último cuadro, así que esperar no acumula retraso.
                if self._stop_event.wait(max(0.0, next_due - time.monotonic())):
                    break
                next_due = max(next_due + interval, time.monotonic())
                self._apply_pending(pipeline)
                seq, frame = grabber.next_frame(seq)
                if frame is None:
                    if not grabber.is_alive():
                        break
                    continue
                self._process(pipeline, recorder, frame)
                frames += 1
                if (elapsed := time.monotonic() - window_start) >= 2:
                    self._set_status(f"En vivo · {frames / elapsed:.1f} fps")
                    frames, window_start = 0, time.monotonic()
        finally:
            grabber.stop()
            grabber.join(timeout=2)
        if self._stop_event.is_set():
            return False
        if video.is_file and not self.camera.loop_video:
            self._set_status("Video terminado")
            return False
        self._set_status(f"Se perdió la señal de {name}. Reintento en {RETRY_SECONDS} s")
        self._stop_event.wait(RETRY_SECONDS)
        return True

    def _apply_pending(self, pipeline) -> None:
        with self._lock:
            pending, self._pending_counter = self._pending_counter, None
        if pending is not None:
            pipeline.set_counter(pending[0])
            self.countsChanged.emit(self.camera.id, _snapshot(pipeline.totals))

    def _process(self, pipeline, recorder: EventRecorder, frame) -> None:
        try:
            result = pipeline.process(frame)
            for alert in result.weapon_alerts:
                self.weaponAlert.emit(self.camera.id, recorder.record_weapon(alert))
            for confirmed in result.confirmed:
                if access := recorder.record_plate(confirmed):
                    self.accessEvent.emit(self.camera.id, access)
            for event in result.count_events:
                recorder.record_count(event)
            for shot in result.shots:
                recorder.record_shot(shot)
        except Exception:  # un frame defectuoso no debe detener la cámara
            log.exception("Error procesando un frame de %s", self.camera.name)
            return
        if result.count_events:
            self.countsChanged.emit(self.camera.id, _snapshot(pipeline.totals))
        self.frameReady.emit(self.camera.id, to_qimage(result.annotated))
