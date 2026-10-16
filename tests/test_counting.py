import pytest

from smartguard.vision.counting import MIN_FRAMES_SEEN, CounterConfig, ObjectCounter
from smartguard.vision.tracking import Track


def track(track_id, x, y, label="auto"):
    return Track(track_id, label, 0.9, (x - 10, y - 10, x + 10, y + 10))


LINE = CounterConfig("line", ((0, 100), (200, 100)))


def test_line_counts_each_track_once_with_direction():
    counter = ObjectCounter(LINE)
    assert counter.update([track(1, 50, 50), track(2, 150, 150)]) == []
    # La flecha A→B apunta a la derecha: su izquierda en pantalla es arriba.
    events = counter.update([track(1, 50, 150), track(2, 150, 50)])
    assert sorted((e.track_id, e.direction) for e in events) == [(1, "in"), (2, "out")]
    # Volver a cruzar no suma
    assert counter.update([track(1, 50, 50)]) == []
    assert counter.totals.total == 2
    assert counter.totals.by_direction == {"in": 1, "out": 1}


def test_crossing_outside_segment_is_ignored():
    counter = ObjectCounter(LINE)
    counter.update([track(1, 400, 50)])
    assert counter.update([track(1, 400, 150)]) == []


def test_zone_counts_entries_by_label():
    counter = ObjectCounter(CounterConfig("zone", ((0, 0), (100, 0), (100, 100), (0, 100))))
    counter.update([track(1, 200, 200), track(2, 50, 50, "moto")])
    counter.update([track(1, 50, 50), track(2, 60, 60, "moto")])
    assert counter.totals.by_label == {"auto": 1, "moto": 1}


def test_all_mode_counts_every_stable_track_once():
    counter = ObjectCounter(CounterConfig())
    counter.update([track(9, 10, 10, "persona")])  # aparece un frame y desaparece: no cuenta
    events = []
    for _ in range(MIN_FRAMES_SEEN + 3):
        events += counter.update([track(1, 50, 50), track(2, 80, 80, "perro")])
    assert sorted((e.track_id, e.label) for e in events) == [(1, "auto"), (2, "perro")]
    assert counter.totals.by_label == {"auto": 1, "perro": 1}


def test_config_validation_and_roundtrip():
    with pytest.raises(ValueError):
        CounterConfig("line", ((0, 0),))
    with pytest.raises(ValueError):
        CounterConfig("zone", ((0, 0), (1, 1)))
    config = CounterConfig("zone", ((0, 0), (10, 0), (10, 10)))
    assert CounterConfig.from_dict(config.to_dict()) == config
    assert CounterConfig.from_dict(None) == CounterConfig("all")
