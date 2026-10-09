from mana_hand_simulator.commander_simulator import (
    _can_pay_colored_pips,
    _category_activation_turn,
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


def test_two_mana_ramp_does_not_contribute_on_turn_two() -> None:
    assert _category_activation_turn("Ramp / Accelerator", 2) == 3
    assert _category_activation_turn("Mana Rock", 2) == 3


def test_multicolor_source_pays_only_one_colored_pip() -> None:
    # A single Jund source cannot pay B, R and G simultaneously.
    jund_mask = (1 << 2) | (1 << 3) | (1 << 4)
    assert not _can_pay_colored_pips(
        (jund_mask,),
        (0, 0, 1, 1, 1),
    )

    # Three Jund sources can each choose one of the three colors.
    assert _can_pay_colored_pips(
        (jund_mask, jund_mask, jund_mask),
        (0, 0, 1, 1, 1),
    )


def test_henzie_style_commander_has_zero_turn_two_without_zero_cost_acceleration() -> None:
    deck = (
        ["Jund Land"] * 36
        + ["Two Mana Ramp"] * 10
        + ["Filler"] * 53
    )
    config = {
        "Jund Land": CardConfig(
            "Jund Land", 0, "Land", True, ("B", "R", "G")
        ),
        "Two Mana Ramp": CardConfig(
            "Two Mana Ramp", 1.5, "Ramp / Accelerator", False, ("G",)
        ),
        "Filler": CardConfig(
            "Filler", 0, "Other / Unscored", False, ()
        ),
    }
    card_data = {
        "Two Mana Ramp": {"cmc": 2},
    }
    commander = {"mana_cost": "{B}{R}{G}", "cmc": 3}

    result = simulate_commander_cast_turns(
        deck,
        config,
        commander,
        iterations=2_000,
        seed=19,
        max_turn=4,
        card_data=card_data,
    )

    assert result.cast_by_turn[2] == 0.0
