"""Procesamiento de un frame de una cámara: seguimiento, conteo, fotos de vehículos y placas."""

import unicodedata
from dataclasses import dataclass, field

import cv2
import numpy as np

from smartguard.core.config import Camera, Settings
from smartguard.core.paths import models_dir
from smartguard.vision.counting import CounterConfig, CountEvent, CountTotals, ObjectCounter
from smartguard.vision.ecuador import Plate
from smartguard.vision.plates import PlateRecognizer
from smartguard.vision.snapshots import BestShot, BestShotKeeper
from smartguard.vision.tracking import Box, ObjectTracker, Track
from smartguard.vision.voting import Voter
from smartguard.vision.weapons import WeaponDetector

# Colores BGR
VEHICLE_COLOR = (255, 170, 60)
PERSON_COLOR = (240, 120, 200)
ANIMAL_COLOR = (120, 200, 120)
PLATE_COLOR = (0, 215, 255)
CONFIRMED_COLOR = (90, 200, 60)
WEAPON_COLOR = (40, 40, 230)
WEAPON_WINDOW_S = 2.0
WEAPON_TEXT = {"firearm": "ARMA DE FUEGO", "blade": "ARMA BLANCA"}


@dataclass(frozen=True)
class ConfirmedPlate:
    plate: Plate
    raw_text: str
    confidence: float
    frame: np.ndarray
    """Frame completo sin anotaciones, para la evidencia."""
    crop: np.ndarray


@dataclass(frozen=True)
class WeaponAlert:
    kind: str
    confidence: float
    frame: np.ndarray
    """Frame anotado: la evidencia muestra dónde se detectó el arma."""
    crop: np.ndarray
    """Recorte de la persona con el arma."""


@dataclass
class FrameResult:
    annotated: np.ndarray
    confirmed: list[ConfirmedPlate] = field(default_factory=list)
    count_events: list[CountEvent] = field(default_factory=list)
    shots: list[BestShot] = field(default_factory=list)
    weapon_alerts: list[WeaponAlert] = field(default_factory=list)


def resolve_device(preference: str) -> str:
    if preference != "auto":
        return preference
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _ascii(text: str) -> str:
    """cv2.putText no dibuja tildes."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _label(frame: np.ndarray, text: str, origin: tuple[int, int], color: tuple[int, int, int]) -> None:
    text = _ascii(text)
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    x, y = origin
    y = max(y, h + base + 4)
    cv2.rectangle(frame, (x, y - h - base - 4), (x + w + 6, y), color, cv2.FILLED)
    cv2.putText(frame, text, (x + 3, y - base - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 2, cv2.LINE_AA)


def _track_color(track: Track) -> tuple[int, int, int]:
    if track.is_vehicle:
        return VEHICLE_COLOR
    return PERSON_COLOR if track.label == "persona" else ANIMAL_COLOR


class Pipeline:
    def __init__(self, settings: Settings, camera: Camera):
        self.device = resolve_device(settings.device)
        self.tracker = ObjectTracker(models_dir() / settings.tracking_model, settings.tracking_confidence, self.device)
        self.plates = (
            PlateRecognizer(
                settings.plate_detector_model,
                settings.plate_confidence,
                settings.ocr_model,
                settings.ocr_min_confidence,
            )
            if camera.read_plates
            else None
        )
        self.voter = Voter(settings.votes_required, cooldown_s=settings.repeat_cooldown_s)
        self.shots = BestShotKeeper() if camera.save_vehicle_photos else None
        self.weapons = (
            WeaponDetector(models_dir(), settings.weapon_model, settings.weapon_confidence, self.device)
            if camera.detect_weapons
            else None
        )
        self.weapon_voter = Voter(settings.weapon_votes_required, WEAPON_WINDOW_S, settings.weapon_cooldown_s)
        self.counter: ObjectCounter | None = None
        self.set_counter(CounterConfig.from_dict(camera.counter) if camera.count_objects else None)

    def set_counter(self, config: CounterConfig | None) -> None:
        self.counter = ObjectCounter(config) if config else None

    @property
    def totals(self) -> CountTotals | None:
        return self.counter.totals if self.counter else None

    def process(self, frame: np.ndarray) -> FrameResult:
        result = FrameResult(annotated=frame.copy())
        tracks = self.tracker.track(frame)
        if self.counter:
            result.count_events = self.counter.update(tracks)
            self.counter.draw(result.annotated)
        if self.shots:
            result.shots = self.shots.update(frame, tracks)
        for track in tracks:
            x1, y1, x2, y2 = track.box
            color = _track_color(track)
            cv2.rectangle(result.annotated, (x1, y1), (x2, y2), color, 2)
            _label(result.annotated, f"{track.label} #{track.id}", (x1, y1), color)
        if self.plates:
            for box in self.plates.detect(frame):
                self._handle_plate(frame, box, result)
        if self.weapons:
            self._handle_weapons(frame, tracks, result)
        return result

    def _handle_weapons(self, frame: np.ndarray, tracks: list[Track], result: FrameResult) -> None:
        voted = set()  # un voto por tipo de arma y cuadro, aunque la vean los recortes de dos personas
        for detection, person in self.weapons.detect_on_people(frame, tracks):
            x1, y1, x2, y2 = detection.box
            cv2.rectangle(result.annotated, (x1, y1), (x2, y2), WEAPON_COLOR, 3)
            _label(result.annotated, f"{WEAPON_TEXT[detection.kind]} {detection.confidence:.0%}", (x1, y1),
                   WEAPON_COLOR)
            if detection.kind in voted:
                continue
            voted.add(detection.kind)
            if self.weapon_voter.add(detection.kind):
                h, w = frame.shape[:2]
                px1, py1 = max(min(x1, person.box[0]) - 20, 0), max(min(y1, person.box[1]) - 20, 0)
                px2, py2 = min(max(x2, person.box[2]) + 20, w), min(max(y2, person.box[3]) + 20, h)
                result.weapon_alerts.append(WeaponAlert(
                    detection.kind, detection.confidence, result.annotated.copy(), frame[py1:py2, px1:px2].copy()
                ))

    def _handle_plate(self, frame: np.ndarray, box: Box, result: FrameResult) -> None:
        """Lee cada placa detectada en cada frame. No se reutiliza la placa de un vehículo seguido:
        si el tracker confunde dos autos, el segundo heredaría la placa (autorizada) del primero."""
        x1, y1, x2, y2 = box
        read = self.plates.read(frame, box)
        text = read.plate.formatted if read.plate else "?"
        color = CONFIRMED_COLOR if read.plate and self.voter.recently_confirmed(read.plate.text) else PLATE_COLOR
        if read.plate and self.voter.add(read.plate.text):
            result.confirmed.append(
                ConfirmedPlate(read.plate, read.raw_text, read.confidence, frame.copy(), frame[y1:y2, x1:x2].copy())
            )
            color = CONFIRMED_COLOR
        cv2.rectangle(result.annotated, (x1, y1), (x2, y2), color, 2)
        _label(result.annotated, text, (x1, y2 + 26), color)

    def finish(self) -> list[BestShot]:
        """Fotos pendientes de los vehículos aún a la vista (al detener la cámara)."""
        return self.shots.flush() if self.shots else []

