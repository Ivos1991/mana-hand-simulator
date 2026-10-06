from pathlib import Path

from mana_hand_simulator.simulator import run_simulation


def test_run_simulation(tmp_path: Path) -> None:
    deck = tmp_path / "deck.txt"
    weights = tmp_path / "weights.csv"

    deck.write_text(
        "30 Swamp\n"
        "20 Sol Ring\n"
        "20 Arcane Signet\n"
        "30 Filler\n",
        encoding="utf-8",
    )
    weights.write_text(
        "card_name,weight,type\n"
        "Sol Ring,3,premium_acceleration\n"
        "Arcane Signet,2,mana_rock\n",
        encoding="utf-8",
    )

    result = run_simulation(deck, weights, iterations=100, seed=7)

    assert result.opening.total == 100
    assert result.final.total == 100
