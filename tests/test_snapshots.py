import numpy as np

from smartguard.vision.snapshots import BestShotKeeper
from smartguard.vision.tracking import Track


def test_keeps_largest_crop_and_releases_when_gone():
    frame = np.zeros((200, 200, 3), np.uint8)
    keeper = BestShotKeeper(lost_after=2, margin=0)
    keeper.update(frame, [Track(1, "auto", 0.9, (0, 0, 50, 50)), Track(2, "persona", 0.9, (0, 0, 90, 90))])
    keeper.update(frame, [Track(1, "auto", 0.9, (0, 0, 120, 80))])
    keeper.update(frame, [Track(1, "auto", 0.9, (0, 0, 60, 60))])
    assert keeper.update(frame, []) == []
    assert keeper.update(frame, []) == []
    [shot] = keeper.update(frame, [])
    assert (shot.track_id, shot.label, shot.image.shape[:2]) == (1, "auto", (80, 120))


def test_tiny_far_away_vehicles_produce_no_photo():
    keeper = BestShotKeeper(lost_after=0)
    keeper.update(np.zeros((200, 200, 3), np.uint8), [Track(1, "auto", 0.9, (0, 0, 30, 20))])
    assert keeper.update(np.zeros((200, 200, 3), np.uint8), []) == []


def test_flush_returns_pending():
    keeper = BestShotKeeper()
    keeper.update(np.zeros((100, 100, 3), np.uint8), [Track(3, "moto", 0.9, (5, 5, 75, 75))])
    assert [s.track_id for s in keeper.flush()] == [3]
    assert keeper.flush() == []
