"""Convierte los resultados del pipeline en registros: decisión de acceso, evidencia y conteos."""

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from smartguard.core.db import UNKNOWN, Database, PlateEvent, Vehicle, WeaponEvent, now_ts
from smartguard.vision.counting import CountEvent
from smartguard.vision.ecuador import Plate, differs_by_one_char
from smartguard.vision.pipeline import ConfirmedPlate, WeaponAlert
from smartguard.vision.snapshots import BestShot
from smartguard.vision.tracking import VEHICLE_LABELS


@dataclass(frozen=True)
class AccessEvent:
    event: PlateEvent
    plate: Plate
    vehicle: Vehicle | None
    """Vehículo registrado con esa placa, o ``None`` si no está en el registro."""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_") or "camara"


class EventRecorder:
    def __init__(self, db: Database, captures_dir: Path, camera_name: str, repeat_cooldown_s: float = 60.0,
                 clock: Callable[[], float] = time.monotonic):
        self.db = db
        self.captures_dir = captures_dir
        self.camera_name = camera_name
        self.repeat_cooldown_s = repeat_cooldown_s
        self._clock = clock
        self._recent_plates: dict[str, float] = {}
        """Placa -> momento en que se registró, para reconocer malas lecturas de la misma placa."""
        self._count_ids: dict[int, int] = {}
        """track_id -> id del conteo, para adjuntarle la foto cuando el vehículo se va."""

    def _folder(self, kind: str) -> Path:
        folder = self.captures_dir / datetime.now().strftime("%Y-%m-%d") / _slug(self.camera_name) / kind
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _misread_of_recent(self, text: str) -> bool:
        now = self._clock()
        self._recent_plates = {p: at for p, at in self._recent_plates.items() if now - at < self.repeat_cooldown_s}
        return any(differs_by_one_char(text, recent) for recent in self._recent_plates)

    def record_plate(self, confirmed: ConfirmedPlate) -> AccessEvent | None:
        """Registra el acceso. Devuelve ``None`` si es una mala lectura de una placa recién registrada.

        Solo se descartan placas *no registradas*: una placa del registro (autorizada o bloqueada)
        siempre genera evento, aunque se parezca a otra recién vista.
        """
        plate = confirmed.plate
        vehicle = self.db.find_vehicle(plate.text)
        if vehicle is None and self._misread_of_recent(plate.text):
            return None
        self._recent_plates[plate.text] = self._clock()
        stamp = datetime.now().strftime("%H%M%S")
        folder = self._folder("placas")
        snapshot = folder / f"{stamp}_{plate.text}.jpg"
        crop = folder / f"{stamp}_{plate.text}_placa.jpg"
        cv2.imwrite(str(snapshot), confirmed.frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        cv2.imwrite(str(crop), confirmed.crop)
        event = self.db.add_plate_event(
            PlateEvent(
                ts=now_ts(),
                plate=plate.text,
                raw_text=confirmed.raw_text,
                confidence=round(confirmed.confidence, 3),
                decision=vehicle.status if vehicle else UNKNOWN,
                vehicle_id=vehicle.id if vehicle else None,
                snapshot_path=str(snapshot),
                crop_path=str(crop),
                camera=self.camera_name,
            )
        )
        return AccessEvent(event, plate, vehicle)

    def record_weapon(self, alert: WeaponAlert) -> WeaponEvent:
        stamp = datetime.now().strftime("%H%M%S")
        folder = self._folder("armas")
        snapshot = folder / f"{stamp}_{alert.kind}.jpg"
        crop = folder / f"{stamp}_{alert.kind}_detalle.jpg"
        cv2.imwrite(str(snapshot), alert.frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        cv2.imwrite(str(crop), alert.crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
        return self.db.add_weapon_event(
            WeaponEvent(ts=now_ts(), camera=self.camera_name, kind=alert.kind, confidence=round(alert.confidence, 3),
                        snapshot_path=str(snapshot), crop_path=str(crop))
        )

    def record_count(self, count: CountEvent) -> None:
        event_id = self.db.add_count_event(self.camera_name, count.label, count.track_id, count.direction)
        if count.label in VEHICLE_LABELS:
            self._count_ids[count.track_id] = event_id
            if len(self._count_ids) > 1000:  # vehículos contados cuya foto nunca llegó
                self._count_ids.pop(next(iter(self._count_ids)))

    def record_shot(self, shot: BestShot) -> None:
        """Guarda la foto del vehículo y la adjunta a su conteo. Sin conteo (no pasó la línea), no se guarda."""
        event_id = self._count_ids.pop(shot.track_id, None)
        if event_id is None or shot.image.size == 0:
            return
        path = self._folder("vehiculos") / f"{datetime.now():%H%M%S}_{shot.label}_{event_id}.jpg"
        cv2.imwrite(str(path), shot.image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        self.db.set_count_image(event_id, str(path))
