"""Detección y seguimiento de personas, vehículos y animales con YOLO26 + ByteTrack (Ultralytics)."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Clases COCO que interesan y su nombre en la interfaz.
TRACKED_CLASSES = {
    0: "persona",
    1: "bicicleta",
    2: "auto",
    3: "moto",
    5: "bus",
    7: "camión",
    15: "gato",
    16: "perro",
    17: "caballo",
    18: "oveja",
    19: "vaca",
}
VEHICLE_LABELS = frozenset({"auto", "moto", "bus", "camión"})

Box = tuple[int, int, int, int]
"""Caja ``(x1, y1, x2, y2)`` en píxeles del frame."""


def to_box(xyxy) -> Box:
    x1, y1, x2, y2 = (int(v) for v in xyxy)
    return x1, y1, x2, y2


@dataclass(frozen=True)
class Track:
    id: int
    label: str
    confidence: float
    box: Box

    @property
    def is_vehicle(self) -> bool:
        return self.label in VEHICLE_LABELS

    @property
    def area(self) -> int:
        x1, y1, x2, y2 = self.box
        return max(x2 - x1, 0) * max(y2 - y1, 0)

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2

    def contains(self, box: Box) -> bool:
        """``True`` si el centro de ``box`` cae dentro de este objeto."""
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        x1, y1, x2, y2 = self.box
        return x1 <= cx <= x2 and y1 <= cy <= y2


class ObjectTracker:
    def __init__(self, model_path: Path, confidence: float, device: str):
        from ultralytics import YOLO  # import diferido: torch tarda varios segundos en cargar

        model_path.parent.mkdir(parents=True, exist_ok=True)
        self.model = YOLO(str(model_path))
        self.confidence = confidence
        self.device = device

    def track(self, frame: np.ndarray) -> list[Track]:
        result = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            classes=list(TRACKED_CLASSES),
            conf=self.confidence,
            device=self.device,
            verbose=False,
        )[0]
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return []
        return [
            Track(int(track_id), TRACKED_CLASSES[int(cls)], float(conf), to_box(xyxy))
            for track_id, cls, conf, xyxy in zip(
                boxes.id.tolist(), boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist(), strict=True
            )
        ]
