import numpy as np

from smartguard.core.config import Camera, Settings
from smartguard.core.db import BLADE, FIREARM
from smartguard.vision import pipeline
from smartguard.vision.tracking import Track
from smartguard.vision.weapons import WeaponDetection, WeaponDetector, person_region

PERSON = Track(1, "persona", 0.9, (100, 100, 200, 400))
CAR = Track(2, "auto", 0.9, (300, 300, 600, 500))
FRAME = np.zeros((720, 1280, 3), np.uint8)


def test_person_region_includes_the_hands_and_stays_inside_the_frame():
    assert person_region(PERSON.box, 1280, 720) == (65, 0, 235, 505)
    assert person_region((1200, 600, 1280, 720), 1280, 720) == (1172, 558, 1280, 720)


def detector_seeing(found: list[WeaponDetection]) -> tuple[WeaponDetector, list[tuple[int, int]]]:
    """Detector cuyo modelo devuelve ``found`` (coordenadas del recorte) y anota el tamaño de cada recorte."""
    detector = WeaponDetector.__new__(WeaponDetector)
    crops = []
    detector._detect = lambda image: crops.append(image.shape[:2]) or found
    return detector, crops


def test_looks_only_at_people_and_maps_boxes_back_to_the_frame():
    detector, crops = detector_seeing([WeaponDetection(FIREARM, 0.8, (10, 20, 30, 40))])
    assert detector.detect_on_people(FRAME, [CAR]) == []
    assert crops == []

    [(detection, person)] = detector.detect_on_people(FRAME, [CAR, PERSON])
    assert crops == [(505, 170)]
    assert person == PERSON
    assert detection.box == (75, 20, 95, 40)


def test_biggest_people_are_checked_first():
    detector, crops = detector_seeing([])
    small = Track(3, "persona", 0.9, (500, 100, 520, 140))
    detector.detect_on_people(FRAME, [small, PERSON])
    assert crops[0] == (505, 170)


class FakeTracker:
    def __init__(self, *args):
        self.tracks = [PERSON, Track(4, "persona", 0.9, (150, 100, 250, 400))]

    def track(self, frame):
        return self.tracks


class TwoPeopleSameKnife:
    def __init__(self, *args):
        pass

    def detect_on_people(self, frame, tracks):
        knife = WeaponDetection(BLADE, 0.9, (190, 250, 210, 290))
        return [(knife, tracks[0]), (knife, tracks[1])]


def test_a_weapon_seen_by_two_crops_votes_once_per_frame(monkeypatch):
    monkeypatch.setattr(pipeline, "ObjectTracker", FakeTracker)
    monkeypatch.setattr(pipeline, "WeaponDetector", TwoPeopleSameKnife)
    camera = Camera(read_plates=False, count_objects=False, save_vehicle_photos=False, detect_weapons=True)
    p = pipeline.Pipeline(Settings(device="cpu", weapon_votes_required=3), camera)

    assert [len(p.process(FRAME).weapon_alerts) for _ in range(3)] == [0, 0, 1]
