import sqlite3

import pytest

from smartguard.core.db import (
    AUTHORIZED,
    BLOCKED,
    CONFIRMED,
    FALSE_ALARM,
    FIREARM,
    PENDING,
    UNKNOWN,
    Database,
    PlateEvent,
    Vehicle,
    WeaponEvent,
)


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def test_vehicle_crud_and_lookup_by_any_plate_format(db):
    vehicle = db.save_vehicle(Vehicle(plate="pbz-5579", owner_name="Ana Pérez", unit="Casa 12"))
    assert vehicle.id and vehicle.plate == "PBZ5579"
    assert db.find_vehicle("PBZ 5579").owner_name == "Ana Pérez"
    vehicle.status = BLOCKED
    db.save_vehicle(vehicle)
    assert db.find_vehicle("PBZ5579").status == BLOCKED
    assert [v.plate for v in db.list_vehicles("casa 12")] == ["PBZ5579"]
    assert [v.plate for v in db.list_vehicles("5579")] == ["PBZ5579"]
    db.delete_vehicle(vehicle.id)
    assert db.find_vehicle("PBZ5579") is None


def test_duplicate_plate_rejected(db):
    db.save_vehicle(Vehicle(plate="PBZ5579"))
    with pytest.raises(sqlite3.IntegrityError):
        db.save_vehicle(Vehicle(plate="PBZ-5579"))


def test_plate_events_filter_and_stats(db):
    for ts, plate, decision in [
        ("2026-10-15 08:00:00", "PBZ5579", AUTHORIZED),
        ("2026-10-16 09:00:00", "PBZ5579", AUTHORIZED),
        ("2026-10-16 10:00:00", "PCX7679", UNKNOWN),
    ]:
        db.add_plate_event(PlateEvent(ts=ts, plate=plate, raw_text=plate, confidence=0.9, decision=decision))
    assert [e.plate for e in db.plate_events("pcx")] == ["PCX7679"]
    assert len(db.plate_events(start="2026-10-16", end="2026-10-17")) == 2
    assert db.decisions_per_day("2026-10-01", "2026-11-01") == {
        "2026-10-15": {AUTHORIZED: 1},
        "2026-10-16": {AUTHORIZED: 1, UNKNOWN: 1},
    }


def test_count_events_with_photo(db):
    event_id = db.add_count_event("Garita", "auto", 7, "in")
    db.add_count_event("Garita", "persona", 8, "in")
    db.set_count_image(event_id, "/tmp/a.jpg")
    rows = db.count_events("2000-01-01", "2100-01-01", label="auto")
    assert [(r["camera"], r["image_path"]) for r in rows] == [("Garita", "/tmp/a.jpg")]
    [per_day] = db.counts_per_day("2000-01-01", "2100-01-01").values()
    assert per_day == {"auto": 1, "persona": 1}
    assert db.counts_per_label("2000-01-01", "2100-01-01") == {"auto": 1, "persona": 1}


def test_weapon_events_and_review(db):
    first = db.add_weapon_event(WeaponEvent(ts="2026-10-16 10:00:00", camera="Garita", kind=FIREARM, confidence=0.8))
    db.add_weapon_event(WeaponEvent(ts="2026-10-16 11:00:00", camera="Piscina", kind="blade", confidence=0.6))
    assert [e.camera for e in db.weapon_events(review=PENDING)] == ["Piscina", "Garita"]
    db.set_weapon_review(first.id, CONFIRMED)
    assert [e.camera for e in db.weapon_events(review=CONFIRMED)] == ["Garita"]
    assert db.weapon_events(review=FALSE_ALARM) == []


def test_migrates_a_version_1_database(tmp_path):
    import sqlite3 as sq

    from smartguard.core.db import _SCHEMA

    path = tmp_path / "v1.db"
    conn = sq.connect(path)
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.close()
    database = Database(path)
    assert database.weapon_events() == []
    assert database.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    database.close()
