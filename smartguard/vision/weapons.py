"""Detección de armas de fuego y armas blancas.

El detector no mira el cuadro entero sino un recorte ampliado alrededor de cada persona que la cámara
sigue. En una cámara de vigilancia el arma ocupa pocos píxeles; ampliada, el modelo la ve. En 90 videos de
vigilancia reales (UCLM, 640x480) los recortes subieron las alertas correctas de 18 % a 45 % de los videos con
arma y bajaron las falsas de 13 % a 3 % de los videos sin arma. Además, así solo cuentan las armas en manos
de alguien: no las de carteles, pantallas o vitrinas.

Una alerta exige ver el mismo tipo de arma en varios cuadros seguidos (``Voter``).

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
MAX_PEOPLE = 6
"""Personas revisadas por cuadro, las más grandes (cercanas) primero: el costo crece con cada recorte."""
MIN_CROP_PX = 16


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


def person_region(person: Box, width: int, height: int, margin: float = PERSON_MARGIN) -> Box:
    """Caja de la persona agrandada para incluir lo que sostiene en las manos, dentro del cuadro.

    El margen deja dentro las manos y un arma corta completa; de un rifle largo sostenido al frente
    entra la parte cercana al cuerpo, que basta para reconocerlo.
    """
    x1, y1, x2, y2 = person
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return int(max(0, x1 - mx)), int(max(0, y1 - my)), int(min(width, x2 + mx)), int(min(height, y2 + my))


class WeaponDetector:
    def __init__(self, models_dir: Path, model_name: str, confidence: float, device: str):
        from ultralytics import YOLO

        self.spec = WEAPON_MODELS[model_name]
        self.model = YOLO(str(self.spec.path(models_dir)))
        self.confidence = confidence
        self.device = device

    def detect_on_people(self, frame: np.ndarray, tracks: list[Track]) -> list[tuple[WeaponDetection, Track]]:
        """Armas en los recortes de las personas seguidas, con coordenadas del cuadro completo."""
        h, w = frame.shape[:2]
        people = sorted((t for t in tracks if t.label == "persona"), key=lambda t: t.area, reverse=True)
        found = []
        for person in people[:MAX_PEOPLE]:
            x1, y1, x2, y2 = person_region(person.box, w, h)
            if x2 - x1 < MIN_CROP_PX or y2 - y1 < MIN_CROP_PX:
                continue
            for detection in self._detect(frame[y1:y2, x1:x2]):
                bx1, by1, bx2, by2 = detection.box
                box = (bx1 + x1, by1 + y1, bx2 + x1, by2 + y1)
                found.append((WeaponDetection(detection.kind, detection.confidence, box), person))
        return found

    def _detect(self, image: np.ndarray) -> list[WeaponDetection]:
        result = self.model.predict(
            image, classes=list(self.spec.classes), conf=self.confidence, device=self.device, verbose=False
        )[0]
        return [
            WeaponDetection(self.spec.classes[int(cls)], float(conf), to_box(xyxy))
            for cls, conf, xyxy in zip(result.boxes.cls.tolist(), result.boxes.conf.tolist(),
                                       result.boxes.xyxy.tolist(), strict=True)
        ]
