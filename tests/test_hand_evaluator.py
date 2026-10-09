from mana_hand_simulator.hand_evaluator import (
    calculate_color_access,
    calculate_color_coverage,
    classify_hand,
    evaluate_hand,
)
from mana_hand_simulator.models import CardConfig, HandTier


def test_explosive_hand() -> None:
    assert classify_hand(lands=3, score=7) is HandTier.A


def test_strong_hand() -> None:
    assert classify_hand(lands=3, score=4) is HandTier.B


def test_bad_land_count_is_mulligan() -> None:
    assert classify_hand(lands=1, score=10) is HandTier.D


def test_color_coverage_penalizes_missing_required_color() -> None:
    config = {
        "Island": CardConfig("Island", 0, "land", True, ("U",)),
        "Sol Ring": CardConfig("Sol Ring", 4, "rock", False, ("C",)),
        "Ramp": CardConfig("Ramp", 3, "ramp", False, ()),
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


def test_color_access_tracks_each_available_color() -> None:
    config = {
        "Watery Grave": CardConfig("Watery Grave", 0, "Land", True, ("U", "B")),
        "Mountain": CardConfig("Mountain", 0, "Land", True, ("R",)),
    }
    hand = ("Watery Grave", "Mountain", "Filler", "Filler", "Filler", "Filler", "Filler")

    access = calculate_color_access(hand, config)
    result = evaluate_hand(hand, config, {"U": 40, "B": 40, "R": 20})

    assert access == ("U", "B", "R")
    assert result.color_access == ("U", "B", "R")
