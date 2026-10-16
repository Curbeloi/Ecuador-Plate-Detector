"""Detección (open-image-models, YOLOv9) y lectura (fast-plate-ocr) de placas."""

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

from smartguard.vision.ecuador import Plate, parse_plate
from smartguard.vision.tracking import Box

ort.set_default_logger_severity(3)  # oculta avisos de particionado de CoreML en cada sesión


@dataclass(frozen=True)
class PlateRead:
    box: Box
    raw_text: str
    confidence: float
    """Confianza media por carácter del OCR (0-1)."""
    plate: Plate | None
    """``None`` si la lectura no es una placa ecuatoriana válida."""


class PlateRecognizer:
    def __init__(self, detector_model: str, detector_confidence: float, ocr_model: str, min_confidence: float):
        from fast_plate_ocr import LicensePlateRecognizer
        from open_image_models import create_detector

        # El proveedor CoreML falla con frames sin placas (salida de tamaño cero): se fuerza CPU.
        self.detector = create_detector(
            detector_model, conf_thresh=detector_confidence, providers=["CPUExecutionProvider"]
        )
        self.ocr = LicensePlateRecognizer(ocr_model)
        self.ocr_rgb = self.ocr.config.image_color_mode == "rgb"
        self.min_confidence = min_confidence

    def detect(self, frame: np.ndarray) -> list[Box]:
        h, w = frame.shape[:2]
        boxes = []
        for detection in self.detector.predict(frame):
            b = detection.bounding_box
            x1, y1, x2, y2 = max(b.x1, 0), max(b.y1, 0), min(b.x2, w), min(b.y2, h)
            if x2 - x1 >= 8 and y2 - y1 >= 4:
                boxes.append((x1, y1, x2, y2))
        return boxes

    def read(self, frame: np.ndarray, box: Box) -> PlateRead:
        x1, y1, x2, y2 = box
        crop = frame[y1:y2, x1:x2]
        crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB if self.ocr_rgb else cv2.COLOR_BGR2GRAY)
        prediction = self.ocr.run(crop, return_confidence=True)[0]
        confidence = float(np.mean(prediction.char_probs)) if prediction.char_probs is not None else 0.0
        plate = parse_plate(prediction.plate) if confidence >= self.min_confidence else None
        return PlateRead(box, prediction.plate, confidence, plate)
