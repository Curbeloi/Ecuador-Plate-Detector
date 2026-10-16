"""Configuración persistente de la app (``settings.json`` en la carpeta de datos)."""

import dataclasses
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from smartguard.core.paths import DEMO_VIDEO, data_dir

log = logging.getLogger(__name__)

TRACKING_MODELS = ("yolo26n.pt", "yolo26s.pt", "yolo26m.pt")
PLATE_DETECTOR_MODELS = (
    "yolo-v9-t-640-license-plate-end2end",
    "yolo-v9-s-608-license-plate-end2end",
    "yolo-v9-t-416-license-plate-end2end",
)
OCR_MODELS = ("cct-s-v2-global-model", "cct-xs-v2-global-model")
DEVICES = ("auto", "cpu", "mps", "cuda")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Camera:
    name: str = "Garita"
    source: str = "0"
    """Índice de cámara local (``0``), URL RTSP/HTTP o ruta a un archivo de video."""
    enabled: bool = True
    read_plates: bool = True
    count_objects: bool = True
    save_vehicle_photos: bool = True
    detect_weapons: bool = True
    counter: dict | None = None
    """``CounterConfig.to_dict()``; ``None`` cuenta todo lo que aparece."""
    loop_video: bool = True
    id: str = field(default_factory=_new_id)


def _default_cameras() -> list[Camera]:
    source = str(DEMO_VIDEO) if DEMO_VIDEO.exists() else "0"
    return [Camera(name="Garita (demo)" if DEMO_VIDEO.exists() else "Garita", source=source)]


@dataclass
class Settings:
    cameras: list[Camera] = field(default_factory=_default_cameras)
    device: str = "auto"
    tracking_model: str = TRACKING_MODELS[0]
    tracking_confidence: float = 0.4
    plate_detector_model: str = PLATE_DETECTOR_MODELS[0]
    plate_confidence: float = 0.4
    ocr_model: str = OCR_MODELS[0]
    ocr_min_confidence: float = 0.75
    votes_required: int = 3
    repeat_cooldown_s: float = 60.0
    weapon_model: str = "smartguard-armas-v1.pt"
    weapon_confidence: float = 0.5
    weapon_votes_required: int = 3
    """Detecciones del mismo tipo de arma en ``WEAPON_WINDOW_S`` para disparar la alerta."""
    weapon_cooldown_s: float = 30.0
    captures_dir: str = ""
    """Vacío = ``<datos>/captures``."""

    @property
    def captures_path(self) -> Path:
        return Path(self.captures_dir) if self.captures_dir else data_dir() / "captures"

    def camera(self, camera_id: str) -> Camera | None:
        return next((c for c in self.cameras if c.id == camera_id), None)

    @classmethod
    def path(cls) -> Path:
        return data_dir() / "settings.json"

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in dataclasses.fields(cls)}
        values = {k: v for k, v in data.items() if k in known}
        if "cameras" in values:
            camera_fields = {f.name for f in dataclasses.fields(Camera)}
            values["cameras"] = [
                Camera(**{k: v for k, v in c.items() if k in camera_fields}) for c in values["cameras"]
            ]
        return cls(**values)

    @classmethod
    def load(cls) -> "Settings":
        path = cls.path()
        if not path.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            log.exception("settings.json ilegible; se usan valores por defecto")
            return cls()

    def save(self) -> None:
        self.path().write_text(json.dumps(dataclasses.asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def copy(self) -> "Settings":
        return Settings.from_dict(dataclasses.asdict(self))
