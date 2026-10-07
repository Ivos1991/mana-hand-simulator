from mana_hand_simulator.scryfall import (
    calculate_card_color_distribution,
    colored_pip_counts,
    deck_summary,
    is_mdfc_land,
)


def test_colored_pips_count_actual_symbols() -> None:
    card = {
        "type_line": "Creature — Wizard",
        "mana_cost": "{1}{U}{B}{B}",
    }
    counts = colored_pip_counts(card)
    assert counts["U"] == 1
    assert counts["B"] == 2


def test_color_distribution_uses_pips_and_colorless_spells() -> None:
    deck = ["Blue Spell", "Black Spell", "Colorless Spell", "Island"]
    cards = {
        "Blue Spell": {
            "type_line": "Instant",
            "mana_cost": "{1}{U}{U}",
        },
        "Black Spell": {
            "type_line": "Sorcery",
            "mana_cost": "{B}",
        },
        "Colorless Spell": {
            "type_line": "Artifact",
            "mana_cost": "{3}",
        },
        "Island": {
            "type_line": "Basic Land — Island",
            "mana_cost": "",
        },
    }

    result = calculate_card_color_distribution(deck, cards)

    assert result["U"] == 50.0
    assert result["B"] == 25.0
    assert result["C"] == 25.0


def test_mdfc_land_detection() -> None:
    card = {
        "layout": "modal_dfc",
        "type_line": "Sorcery // Land",
        "card_faces": [
            {"type_line": "Sorcery", "mana_cost": "{2}{B}"},
            {"type_line": "Land", "mana_cost": ""},
        ],
    }
    assert is_mdfc_land(card)


def test_deck_summary_uses_existing_card_data() -> None:
    deck = ["Spell", "Swamp"]
    cards = {
        "Spell": {
            "type_line": "Creature — Zombie",
            "mana_cost": "{1}{B}",
            "cmc": 2,
            "color_identity": ["B"],
            "legalities": {"commander": "legal"},
        },
        "Swamp": {
            "type_line": "Basic Land — Swamp",
            "mana_cost": "",
            "cmc": 0,
            "color_identity": [],
            "legalities": {"commander": "legal"},
        },
    }

    result = deck_summary(deck, cards)

    assert result["deck_size"] == 2
    assert result["land_count"] == 1
    assert result["average_mana_value"] == 2.0
    assert result["color_identity"] == "B"
