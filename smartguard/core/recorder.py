"""Convierte los resultados del pipeline en registros: decisión de acceso, evidencia y conteos."""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2

from smartguard.core.db import UNKNOWN, Database, PlateEvent, Vehicle, WeaponEvent, now_ts
from smartguard.vision.counting import CountEvent
from smartguard.vision.ecuador import Plate
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
    def __init__(self, db: Database, captures_dir: Path, camera_name: str):
        self.db = db
        self.captures_dir = captures_dir
        self.camera_name = camera_name
        self._count_ids: dict[int, int] = {}
        """track_id -> id del conteo, para adjuntarle la foto cuando el vehículo se va."""

    def _folder(self, kind: str) -> Path:
        folder = self.captures_dir / datetime.now().strftime("%Y-%m-%d") / _slug(self.camera_name) / kind
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def record_plate(self, confirmed: ConfirmedPlate) -> AccessEvent:
        plate = confirmed.plate
        vehicle = self.db.find_vehicle(plate.text)
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
