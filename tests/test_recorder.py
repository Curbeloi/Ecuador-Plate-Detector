import numpy as np
import pytest

from smartguard.core.db import AUTHORIZED, BLOCKED, Database, Vehicle
from smartguard.core.recorder import EventRecorder
from smartguard.vision.ecuador import parse_plate
from smartguard.vision.pipeline import ConfirmedPlate


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup(tmp_path):
    db = Database(":memory:")
    db.save_vehicle(Vehicle(plate="PON7651", status=AUTHORIZED))
    db.save_vehicle(Vehicle(plate="PDN7651", status=BLOCKED))
    clock = FakeClock()
    yield db, EventRecorder(db, tmp_path, "Garita", repeat_cooldown_s=60, clock=clock), clock
    db.close()


def confirmed(text):
    image = np.zeros((40, 80, 3), np.uint8)
    return ConfirmedPlate(parse_plate(text), text, 0.99, image, image)


def test_blocked_plate_one_char_from_recent_authorized_is_still_recorded(setup):
    _db, recorder, _clock = setup
    assert recorder.record_plate(confirmed("PON7651")).event.decision == AUTHORIZED
    blocked = recorder.record_plate(confirmed("PDN7651"))
    assert blocked is not None and blocked.event.decision == BLOCKED


def test_unregistered_misread_of_recent_plate_is_skipped(setup):
    db, recorder, clock = setup
    recorder.record_plate(confirmed("PON7651"))
    assert recorder.record_plate(confirmed("POM7651")) is None  # mala lectura de la placa recién vista
    clock.now = 61
    assert recorder.record_plate(confirmed("POM7651")) is not None  # pasado el intervalo, cuenta
    assert len(db.plate_events()) == 2


def test_unrelated_unknown_plate_is_recorded(setup):
    _db, recorder, _clock = setup
    recorder.record_plate(confirmed("PON7651"))
    assert recorder.record_plate(confirmed("GSA1234")).event.decision == "unknown"
