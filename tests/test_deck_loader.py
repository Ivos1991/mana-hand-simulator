from pathlib import Path

from mana_hand_simulator.deck_loader import load_card_config, load_deck


def test_load_deck(tmp_path: Path) -> None:
    path = tmp_path / "deck.txt"
    path.write_text("2 Swamp\n1 Sol Ring\n", encoding="utf-8")

    assert load_deck(path) == ["Swamp", "Swamp", "Sol Ring"]


def test_load_card_config(tmp_path: Path) -> None:
    path = tmp_path / "config.csv"
    path.write_text(
        "card_name,weight,type,is_land\n"
        "Swamp,0,land,true\n"
        "Sol Ring,3,premium_acceleration,false\n",
        encoding="utf-8",
    )

    config = load_card_config(path)

    assert config["Sol Ring"].weight == 3
    assert config["Sol Ring"].category == "premium_acceleration"
    assert config["Swamp"].is_land is True
