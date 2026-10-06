from mana_hand_simulator.hand_evaluator import classify_hand
from mana_hand_simulator.models import HandTier


def test_explosive_hand() -> None:
    assert classify_hand(lands=3, score=5) is HandTier.A


def test_strong_hand() -> None:
    assert classify_hand(lands=3, score=3) is HandTier.B


def test_bad_land_count_is_mulligan() -> None:
    assert classify_hand(lands=1, score=10) is HandTier.D
