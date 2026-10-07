import numpy as np

from mana_hand_simulator.fast_simulator import (
    choose_london_six_fast,
    evaluate_index_hands,
    prepare_deck,
)
from mana_hand_simulator.hand_evaluator import evaluate_hand
from mana_hand_simulator.models import CardConfig
from mana_hand_simulator.mulligan import choose_london_six
from mana_hand_simulator.simulator import run_simulation_from_data


def _config() -> dict[str, CardConfig]:
    return {
        "Swamp": CardConfig("Swamp", 0.0, "Land", True, ("B",)),
        "Island": CardConfig("Island", 0.0, "Land", True, ("U",)),
        "Sol Ring": CardConfig("Sol Ring", 3.0, "Premium Acceleration", False, ("C",)),
        "Signet": CardConfig("Signet", 2.0, "Mana Rock", False, ("U", "B")),
        "Ramp": CardConfig("Ramp", 1.5, "Ramp / Accelerator", False, ()),
        "Filler": CardConfig("Filler", 0.0, "Other / Unscored", False, ()),
    }


def test_vectorized_hand_evaluation_matches_reference() -> None:
    deck = ["Swamp", "Island", "Sol Ring", "Signet", "Ramp", "Filler", "Filler"]
    config = _config()
    demand = {"U": 40.0, "B": 60.0}

    prepared = prepare_deck(deck, config, demand)
    fast = evaluate_index_hands(np.array([[0, 1, 2, 3, 4, 5, 6]]), prepared)
    reference = evaluate_hand(deck, config, demand)

    assert fast.lands[0] == reference.lands
    assert fast.score[0] == reference.score
    assert abs(float(fast.coverage[0]) - reference.color_coverage) < 1e-12
    assert tuple(color for i, color in enumerate(("W", "U", "B", "R", "G")) if fast.access[0, i]) == reference.color_access


def test_fast_london_choice_matches_reference_metrics() -> None:
    hand = ["Swamp", "Island", "Sol Ring", "Signet", "Ramp", "Filler", "Filler"]
    config = _config()
    demand = {"U": 40.0, "B": 60.0}

    prepared = prepare_deck(hand, config, demand)
    fast = choose_london_six_fast(np.array([[0, 1, 2, 3, 4, 5, 6]]), prepared)
    chosen = choose_london_six(hand, config, demand)
    reference = evaluate_hand(chosen, config, demand)

    assert fast.lands[0] == reference.lands
    assert fast.score[0] == reference.score
    assert abs(float(fast.coverage[0]) - reference.color_coverage) < 1e-12


def test_vectorized_simulation_is_repeatable_with_seed() -> None:
    deck = ["Swamp"] * 35 + ["Island"] * 15 + ["Sol Ring"] * 5 + ["Signet"] * 10 + ["Ramp"] * 10 + ["Filler"] * 25
    config = _config()
    demand = {"U": 35.0, "B": 65.0}

    first = run_simulation_from_data(
        deck,
        config,
        iterations=2_000,
        seed=42,
        color_demand=demand,
        batch_size=500,
    )
    second = run_simulation_from_data(
        deck,
        config,
        iterations=2_000,
        seed=42,
        color_demand=demand,
        batch_size=500,
    )

    assert first == second
    assert first.opening.total == 2_000
    assert first.free_mulligan.total == 2_000
    assert first.final.total == 2_000
