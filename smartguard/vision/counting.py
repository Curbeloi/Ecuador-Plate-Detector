"""Conteo de personas, vehículos y animales.

Tres modos:
- ``all``: cuenta todo lo que aparece en la cámara (no hace falta dibujar nada).
- ``line``: cuenta lo que cruza una línea A→B, con dirección.
- ``zone``: cuenta lo que entra en un polígono.

Cada objeto se identifica por su ``track_id`` del tracker, así que se cuenta una sola vez
aunque aparezca en cientos de frames.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import cv2
import numpy as np

from smartguard.vision.tracking import Track

Point = tuple[float, float]

MIN_FRAMES_SEEN = 5
"""En modo ``all`` un objeto debe seguirse varios frames antes de contarse: descarta detecciones fugaces."""


@dataclass(frozen=True)
class CounterConfig:
    kind: str = "all"
    points: tuple[Point, ...] = ()

    def __post_init__(self):
        if self.kind not in ("all", "line", "zone"):
            raise ValueError(f"Tipo de contador desconocido: {self.kind}")
        if self.kind == "line" and len(self.points) != 2:
            raise ValueError("Una línea necesita exactamente 2 puntos")
        if self.kind == "zone" and len(self.points) < 3:
            raise ValueError("Una zona necesita al menos 3 puntos")

    def to_dict(self) -> dict:
        return {"kind": self.kind, "points": [list(p) for p in self.points]}

    @classmethod
    def from_dict(cls, data: dict | None) -> "CounterConfig":
        if not data:
            return cls()
        return cls(data["kind"], tuple((float(x), float(y)) for x, y in data.get("points", ())))


@dataclass(frozen=True)
class CountEvent:
    track_id: int
    label: str
    direction: str
    """En una línea A→B: ``in`` si cruza de izquierda a derecha de la flecha vista en pantalla,
    ``out`` al revés. En los modos ``zone`` y ``all`` siempre es ``in``."""


@dataclass
class CountTotals:
    by_label: Counter = field(default_factory=Counter)
    by_direction: Counter = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.by_label.values())


def _side(a: Point, b: Point, p: Point) -> float:
    """Signo del producto cruz: a qué lado de la recta a→b queda p."""
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    d1, d2 = _side(q1, q2, p1), _side(q1, q2, p2)
    d3, d4 = _side(p1, p2, q1), _side(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 <= 0


class ObjectCounter:
    def __init__(self, config: CounterConfig):
        self.config = config
        self.totals = CountTotals()
        self._last_center: dict[int, Point] = {}
        self._frames_seen: defaultdict[int, int] = defaultdict(int)
        self._counted: set[int] = set()
        self._polygon = np.array(config.points, dtype=np.float32)

    def update(self, tracks: list[Track]) -> list[CountEvent]:
        events = []
        for track in tracks:
            center = track.center
            previous = self._last_center.get(track.id)
            self._last_center[track.id] = center
            self._frames_seen[track.id] += 1
            if track.id in self._counted:
                continue
            direction = self._crossing(track.id, previous, center)
            if direction is None:
                continue
            self._counted.add(track.id)
            self.totals.by_label[track.label] += 1
            self.totals.by_direction[direction] += 1
            events.append(CountEvent(track.id, track.label, direction))
        self._forget_lost(tracks)
        return events

    def _crossing(self, track_id: int, previous: Point | None, center: Point) -> str | None:
        if self.config.kind == "all":
            return "in" if self._frames_seen[track_id] >= MIN_FRAMES_SEEN else None
        if self.config.kind == "zone":
            inside = cv2.pointPolygonTest(self._polygon, center, False) >= 0
            return "in" if inside else None
        if previous is None:
            return None
        a, b = self.config.points
        if not _segments_intersect(previous, center, a, b):
            return None
        return "in" if _side(a, b, previous) < 0 else "out"

    def _forget_lost(self, tracks: list[Track]) -> None:
        """Limita la memoria: conserva solo los tracks recientes (ByteTrack no reutiliza IDs)."""
        if len(self._last_center) > 2048:
            alive = {t.id for t in tracks}
            self._last_center = {k: v for k, v in self._last_center.items() if k in alive}
            self._frames_seen = defaultdict(int, {k: v for k, v in self._frames_seen.items() if k in alive})
            self._counted &= alive

    def draw(self, frame: np.ndarray) -> None:
        if self.config.kind == "all":
            return
        points = np.array(self.config.points, dtype=np.int32)
        color = (0, 200, 255)
        if self.config.kind == "line":
            cv2.arrowedLine(frame, tuple(points[0]), tuple(points[1]), color, 3, cv2.LINE_AA, tipLength=0.04)
        else:
            overlay = frame.copy()
            cv2.fillPoly(overlay, [points], color)
            cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, dst=frame)
            cv2.polylines(frame, [points], True, color, 2, cv2.LINE_AA)
