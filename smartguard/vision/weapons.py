"""Detección de armas de fuego y armas blancas.

Una alerta se dispara solo si:
1. el detector ve el mismo tipo de arma varias veces seguidas (``Voter``), y
2. el arma está junto a una persona que la cámara está siguiendo (descarta armas en carteles,
   pantallas o vitrinas, y la mayoría de detecciones sueltas sobre objetos del fondo).

Aun así la detección automática se equivoca: cada alerta queda pendiente de revisión humana.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from smartguard.core.db import BLADE, FIREARM
from smartguard.core.paths import ASSETS_DIR
from smartguard.vision.tracking import Box, Track, to_box

PERSON_MARGIN = 0.35
"""Cuánto se agranda la caja de la persona (proporción de su ancho/alto) al buscar el arma en sus manos."""


@dataclass(frozen=True)
class WeaponModel:
    file: str
    classes: dict[int, str]
    """Id de clase del modelo -> ``firearm`` / ``blade``."""
    description: str
    bundled: bool = False
    """Viene dentro del paquete (``assets/models``) en vez de descargarse de Ultralytics."""

    def path(self, models_dir: Path) -> Path:
        return ASSETS_DIR / "models" / self.file if self.bundled else models_dir / self.file


WEAPON_MODELS = {
    # YOLO26-S ajustado con Open Images (pistolas, rifles, escopetas, cuchillos, dagas, espadas y ~4.000 imágenes de
    # personas sin armas). En imágenes no vistas (Open Images val+test), con umbral 0,5: detecta 83 % de armas de
    # fuego y 89 % de armas blancas con 2,6 % de falsas alarmas por imagen. Los modelos genéricos (Objects365, COCO,
    # YOLOE por texto) no pasaban de 44 % / 48 % con las mismas falsas alarmas.
    "smartguard-armas-v1.pt": WeaponModel(
        "smartguard-armas-v1.pt", {0: FIREARM, 1: BLADE}, "SmartGuard armas v1 (YOLO26-S ajustado)", bundled=True
    ),
}


@dataclass(frozen=True)
class WeaponDetection:
    kind: str
    confidence: float
    box: Box


def near_person(box: Box, tracks: list[Track], margin: float = PERSON_MARGIN) -> Track | None:
    """Persona cuya caja (agrandada) toca la caja del arma.

    Se exige contacto y no que el centro del arma caiga sobre la persona: un rifle largo sostenido
    al frente tiene su centro lejos del cuerpo.
    """
    for track in tracks:
        if track.label != "persona":
            continue
        x1, y1, x2, y2 = track.box
        mx, my = (x2 - x1) * margin, (y2 - y1) * margin
        if box[0] <= x2 + mx and box[2] >= x1 - mx and box[1] <= y2 + my and box[3] >= y1 - my:
            return track
    return None


class WeaponDetector:
    def __init__(self, models_dir: Path, model_name: str, confidence: float, device: str):
        from ultralytics import YOLO

        self.spec = WEAPON_MODELS[model_name]
        self.model = YOLO(str(self.spec.path(models_dir)))
        self.confidence = confidence
        self.device = device

    def detect(self, frame: np.ndarray) -> list[WeaponDetection]:
        result = self.model.predict(
            frame, classes=list(self.spec.classes), conf=self.confidence, device=self.device, verbose=False
        )[0]
        return [
            WeaponDetection(self.spec.classes[int(cls)], float(conf), to_box(xyxy))
            for cls, conf, xyxy in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist(),
                                       result.boxes.xyxy.tolist(), strict=True)
        ]
