from mana_hand_simulator.commander_simulator import (
    commander_requirements,
    simulate_commander_cast_turns,
)
from mana_hand_simulator.models import CardConfig


def test_commander_requirements_count_colored_pips() -> None:
    card = {"mana_cost": "{5}{B}{B}{B}", "cmc": 8}
    mana_value, colors = commander_requirements(card)

    assert mana_value == 8
    assert colors["B"] == 3


def test_basic_commander_curve_is_cumulative() -> None:
    deck = ["Swamp"] * 60 + ["Filler"] * 39
    config = {
        "Swamp": CardConfig("Swamp", 0, "Land", True, ("B",)),
        "Filler": CardConfig("Filler", 0, "Other / Unscored", False, ()),
    }
    commander = {"mana_cost": "{2}{B}", "cmc": 3}

    result = simulate_commander_cast_turns(
        deck,
        config,
        commander,
        iterations=500,
        seed=7,
        max_turn=5,
    )

    assert result.cast_by_turn[1] <= result.cast_by_turn[2]
    assert result.cast_by_turn[2] <= result.cast_by_turn[3]
    assert result.cast_by_turn[3] <= result.cast_by_turn[4]
    assert result.cast_by_turn[4] <= result.cast_by_turn[5]
    assert result.cast_by_turn[3] > 0
