"""Conversión de frames de OpenCV a imágenes de Qt."""

import numpy as np
from PySide6.QtGui import QImage, QPixmap


def to_qimage(frame: np.ndarray) -> QImage:
    """BGR (OpenCV) -> QImage. ``copy()`` desliga la imagen del buffer de numpy, que se reutiliza."""
    frame = np.ascontiguousarray(frame)
    h, w = frame.shape[:2]
    if frame.ndim == 2:
        return QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_Grayscale8).copy()
    return QImage(frame.data, w, h, frame.strides[0], QImage.Format.Format_BGR888).copy()


def load_pixmap(path: str, width: int, height: int) -> QPixmap:
    from PySide6.QtCore import Qt

    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
