from pathlib import Path

from mana_hand_simulator.simulator import run_simulation


def test_run_simulation(tmp_path: Path) -> None:
    deck = tmp_path / "deck.txt"
    config = tmp_path / "config.csv"

    deck.write_text(
        "30 Swamp\n"
        "20 Sol Ring\n"
        "20 Arcane Signet\n"
        "30 Filler\n",
        encoding="utf-8",
    )
    config.write_text(
        "card_name,weight,type,is_land\n"
        "Swamp,0,land,true\n"
        "Sol Ring,3,premium_acceleration,false\n"
        "Arcane Signet,2,mana_rock,false\n",
        encoding="utf-8",
    )

    result = run_simulation(deck, config, iterations=100, seed=7)

    assert result.opening.total == 100
    assert result.final.total == 100
