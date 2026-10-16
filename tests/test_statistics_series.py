from smartguard.features.statistics.page import ANIMALS, SERIES
from smartguard.vision.tracking import TRACKED_CLASSES


def test_every_tracked_class_has_a_chart_series():
    assert set(TRACKED_CLASSES.values()) <= {key for key, *_ in SERIES} | ANIMALS
