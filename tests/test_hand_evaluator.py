from mana_hand_simulator.hand_evaluator import (
    calculate_color_coverage,
    classify_hand,
    evaluate_hand,
)
from mana_hand_simulator.models import CardConfig, HandTier


def test_explosive_hand() -> None:
    assert classify_hand(lands=3, score=5) is HandTier.A


def test_strong_hand() -> None:
    assert classify_hand(lands=3, score=3) is HandTier.B


def test_bad_land_count_is_mulligan() -> None:
    assert classify_hand(lands=1, score=10) is HandTier.D


def test_color_coverage_penalizes_missing_required_color() -> None:
    config = {
        "Island": CardConfig("Island", 0, "land", True, ("U",)),
        "Sol Ring": CardConfig("Sol Ring", 3, "rock", False, ("C",)),
        "Ramp": CardConfig("Ramp", 2, "ramp", False, ()),
    }
    hand = ("Island", "Island", "Sol Ring", "Ramp", "Filler", "Filler", "Filler")
    demand = {"U": 50, "B": 50, "C": 0}

    coverage = calculate_color_coverage(hand, config, demand)
    result = evaluate_hand(hand, config, demand)

    assert coverage < 0.70
    assert result.tier in {HandTier.C, HandTier.D}


def test_mono_color_hand_keeps_full_coverage() -> None:
    config = {
        "Swamp": CardConfig("Swamp", 0, "land", True, ("B",)),
        "Sol Ring": CardConfig("Sol Ring", 3, "rock", False, ("C",)),
        "Ramp": CardConfig("Ramp", 2, "ramp", False, ()),
    }
    hand = ("Swamp", "Swamp", "Swamp", "Sol Ring", "Ramp", "Filler", "Filler")
    demand = {"B": 80, "C": 20}

    result = evaluate_hand(hand, config, demand)

    assert result.color_coverage > 0.75
    assert result.tier in {HandTier.A, HandTier.B}
