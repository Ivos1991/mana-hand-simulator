from pathlib import Path

from mana_hand_simulator.deck_loader import load_deck, load_weights


def test_load_deck(tmp_path: Path) -> None:
    path = tmp_path / "deck.txt"
    path.write_text("2 Swamp\n1 Sol Ring\n", encoding="utf-8")

    assert load_deck(path) == ["Swamp", "Swamp", "Sol Ring"]


def test_load_weights(tmp_path: Path) -> None:
    path = tmp_path / "weights.csv"
    path.write_text(
        "card_name,weight,type\nSol Ring,3,premium_acceleration\n",
        encoding="utf-8",
    )

    weights = load_weights(path)

    assert weights["Sol Ring"].weight == 3
    assert weights["Sol Ring"].category == "premium_acceleration"
