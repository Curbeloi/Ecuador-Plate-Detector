from smartguard.vision.tracking import Track
from smartguard.vision.weapons import near_person

PERSON = Track(1, "persona", 0.9, (100, 100, 200, 400))
CAR = Track(2, "auto", 0.9, (300, 300, 600, 500))


def test_weapon_in_hand_is_near_person():
    assert near_person((180, 250, 230, 280), [PERSON]) == PERSON  # mano extendida, fuera de la caja estricta


def test_weapon_far_from_people_is_ignored():
    assert near_person((500, 50, 560, 90), [PERSON]) is None


def test_only_people_count():
    assert near_person((400, 350, 450, 380), [CAR]) is None


def test_long_rifle_held_by_person_counts_even_if_its_center_is_away():
    shooter = Track(3, "persona", 0.9, (817, 123, 1227, 713))
    assert near_person((169, 182, 968, 494), [shooter]) == shooter  # caso real de la escena 3
