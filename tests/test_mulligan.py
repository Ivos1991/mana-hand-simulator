import random

from mana_hand_simulator.mulligan import draw_hand


def test_draw_hand_size() -> None:
    deck = [f"Card {index}" for index in range(100)]
    hand = draw_hand(deck, 7, random.Random(1))

    assert len(hand) == 7
    assert len(set(hand)) == 7
