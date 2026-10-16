"""Lectura de cámaras (locales o IP por RTSP/HTTP) y archivos de video.

``FrameGrabber`` lee en su propio hilo y conserva solo el último frame. Así la inferencia,
que es más lenta que la cámara, siempre trabaja sobre la imagen más reciente y un stream RTSP
no acumula segundos de retraso.
"""

import threading
import time
from pathlib import Path

import cv2
import numpy as np

OPEN_TIMEOUT_MS = 8000


def describe_source(source: str) -> str:
    if source.strip().isdigit():
        return f"cámara local {source.strip()}"
    if "://" in source:
        return source.split("@")[-1]  # no mostrar usuario y contraseña de la URL
    return Path(source).name


class VideoSource:
    def __init__(self, source: str, loop: bool = True):
        self.source = source.strip()
        self.loop = loop
        self.is_file = not self.source.isdigit() and "://" not in self.source
        self.cap: cv2.VideoCapture | None = None
        self.fps = 25.0

    def open(self) -> bool:
        if self.source.isdigit():
            cap = cv2.VideoCapture(int(self.source))
        elif self.is_file:
            if not Path(self.source).is_file():
                return False
            cap = cv2.VideoCapture(self.source)
        else:
            cap = cv2.VideoCapture(
                self.source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, OPEN_TIMEOUT_MS,
                                             cv2.CAP_PROP_READ_TIMEOUT_MSEC, OPEN_TIMEOUT_MS]
            )
        if not cap.isOpened():
            cap.release()
            return False
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 <= fps <= 120 else 25.0
        self.cap = cap
        return True

    def read(self) -> np.ndarray | None:
        if self.cap is None:
            return None
        ok, frame = self.cap.read()
        if not ok and self.is_file and self.loop:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return frame if ok else None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def probe_source(source: str) -> tuple[bool, str]:
    """Abre la fuente y lee un frame. Para el botón "Probar" de la configuración."""
    video = VideoSource(source, loop=False)
    if not video.open():
        return False, f"No se pudo abrir {describe_source(source)}"
    try:
        frame = video.read()
        if frame is None:
            return False, "La fuente abrió pero no entregó imágenes"
        h, w = frame.shape[:2]
        return True, f"OK: {w}×{h} a {video.fps:.0f} fps"
    finally:
        video.release()


class FrameGrabber(threading.Thread):
    MAX_FAILURES = 50

    def __init__(self, video: VideoSource):
        super().__init__(daemon=True, name="FrameGrabber")
        self.video = video
        self.ended = False
        self._stop_event = threading.Event()
        self._cond = threading.Condition()
        self._frame: np.ndarray | None = None
        self._seq = 0

    def run(self) -> None:
        failures = 0
        interval = 1.0 / self.video.fps
        while not self._stop_event.is_set():
            started = time.monotonic()
            frame = self.video.read()
            if frame is None:
                failures += 1
                if self.video.is_file or failures >= self.MAX_FAILURES:
                    break
                time.sleep(0.1)
                continue
            failures = 0
            with self._cond:
                self._frame = frame
                self._seq += 1
                self._cond.notify_all()
            if self.video.is_file:  # un archivo se lee a su velocidad real, no tan rápido como se pueda
                self._stop_event.wait(max(interval - (time.monotonic() - started), 0))
        self.ended = not self._stop_event.is_set()
        self.video.release()
        with self._cond:
            self._cond.notify_all()

    def next_frame(self, last_seq: int, timeout: float = 0.5) -> tuple[int, np.ndarray | None]:
        """Espera un frame más nuevo que ``last_seq``; devuelve ``(seq, frame)`` o ``(last_seq, None)``."""
        with self._cond:
            self._cond.wait_for(lambda: self._seq > last_seq or not self.is_alive(), timeout)
            if self._seq > last_seq:
                return self._seq, self._frame
            return last_seq, None

    def stop(self) -> None:
        self._stop_event.set()
