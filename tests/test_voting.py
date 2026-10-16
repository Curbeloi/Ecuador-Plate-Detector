from smartguard.vision.voting import Voter


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_confirms_after_required_votes_once():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=3, window_s=4, cooldown_s=60, clock=clock)
    assert [voter.add("PBZ5579") for _ in range(5)] == [False, False, True, False, False]
    assert voter.recently_confirmed("PBZ5579")


def test_votes_outside_window_do_not_count():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=2, window_s=1, cooldown_s=60, clock=clock)
    assert not voter.add("PBZ5579")
    clock.now = 2
    assert not voter.add("PBZ5579")
    clock.now = 2.5
    assert voter.add("PBZ5579")


def test_misread_does_not_steal_confirmation():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=2, clock=clock)
    assert not voter.add("PBZ5579")
    assert not voter.add("PBZ5572")
    assert voter.add("PBZ5579")


def test_confirms_again_after_cooldown():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=1, cooldown_s=10, clock=clock)
    assert voter.add("PBZ5579")
    clock.now = 5
    assert not voter.add("PBZ5579")
    clock.now = 11
    assert voter.add("PBZ5579")


def test_near_duplicate_of_recent_plate_is_ignored():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=1, cooldown_s=10, clock=clock)
    assert voter.add("PDN7651")
    assert not voter.add("PON7651")
    assert voter.add("PCS7709")
    clock.now = 11
    assert voter.add("PON7651")


def test_stale_misreads_are_forgotten():
    clock = FakeClock()
    voter = Voter(merge_near_duplicates=True, votes_required=3, window_s=1, clock=clock)
    for i in range(300):
        voter.add(f"MISREAD{i}")
    clock.now = 5
    voter.add("PBZ5579")
    assert len(voter._reads) < 10


def test_without_merging_similar_keys_are_independent():
    clock = FakeClock()
    voter = Voter(votes_required=1, cooldown_s=10, clock=clock)
    assert voter.add("firearm")
    assert not voter.add("firearm")
    assert voter.add("blade")
