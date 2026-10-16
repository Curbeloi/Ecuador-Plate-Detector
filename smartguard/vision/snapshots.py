"""Mejor foto de cada vehículo que pasa por la cámara.

Mientras el vehículo está a la vista se conserva el recorte de mayor tamaño (suele ser el más
cercano y nítido); cuando deja de verse durante ``lost_after`` frames, se entrega esa foto.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from smartguard.vision.tracking import VEHICLE_LABELS, Track

MIN_SIDE_PX = 48
"""Vehículos más pequeños que esto (lejanos) no producen foto útil."""


@dataclass
class BestShot:
    track_id: int
    label: str
    image: np.ndarray
    area: int
    last_seen: int


def _big_enough(shot: BestShot) -> bool:
    h, w = shot.image.shape[:2]
    return min(h, w) >= MIN_SIDE_PX


class BestShotKeeper:
    def __init__(self, labels: Iterable[str] = VEHICLE_LABELS, lost_after: int = 30, margin: float = 0.08):
        self.labels = frozenset(labels)
        self.lost_after = lost_after
        self.margin = margin
        self._frame_index = 0
        self._shots: dict[int, BestShot] = {}

    def update(self, frame: np.ndarray, tracks: list[Track]) -> list[BestShot]:
        """Actualiza las fotos y devuelve las de los vehículos que ya se fueron."""
        self._frame_index += 1
        for track in tracks:
            if track.label not in self.labels:
                continue
            shot = self._shots.get(track.id)
            if shot is None or track.area > shot.area:
                self._shots[track.id] = BestShot(track.id, track.label, self._crop(frame, track), track.area,
                                                 self._frame_index)
            else:
                shot.last_seen = self._frame_index
        gone = [k for k, s in self._shots.items() if self._frame_index - s.last_seen > self.lost_after]
        return [shot for shot in (self._shots.pop(k) for k in gone) if _big_enough(shot)]

    def flush(self) -> list[BestShot]:
        """Entrega todas las fotos pendientes (al detener la cámara)."""
        shots = [shot for shot in self._shots.values() if _big_enough(shot)]
        self._shots.clear()
        return shots

    def _crop(self, frame: np.ndarray, track: Track) -> np.ndarray:
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = track.box
        mx, my = int((x2 - x1) * self.margin), int((y2 - y1) * self.margin)
        return frame[max(y1 - my, 0):min(y2 + my, h), max(x1 - mx, 0):min(x2 + mx, w)].copy()
