from __future__ import annotations

import random
from collections.abc import Sequence

from .hand_evaluator import evaluate_hand
from .models import CardConfig, HandEvaluation, HandTier


KEEP_TIERS = {HandTier.A, HandTier.B}


def draw_hand(deck: Sequence[str], size: int, rng: random.Random) -> list[str]:
    if size > len(deck):
        raise ValueError("Hand size cannot exceed deck size.")
    return rng.sample(list(deck), size)


def choose_london_six(
    hand: Sequence[str],
    card_config: dict[str, CardConfig],
) -> list[str]:
    """Choose the best six-card subset from a seven-card London mulligan hand."""
    if len(hand) != 7:
        raise ValueError("London mulligan input must contain exactly seven cards.")

    candidates: list[tuple[tuple[int, float, int], list[str]]] = []

    for index in range(7):
        candidate = list(hand[:index]) + list(hand[index + 1 :])
        evaluation = evaluate_hand(candidate, card_config)
        tier_rank = {
            HandTier.A: 4,
            HandTier.B: 3,
            HandTier.C: 2,
            HandTier.D: 1,
        }[evaluation.tier]
        candidates.append(
            ((tier_rank, evaluation.score, -abs(evaluation.lands - 3)), candidate)
        )

    return max(candidates, key=lambda item: item[0])[1]


def simulate_mulligan_sequence(
    deck: Sequence[str],
    card_config: dict[str, CardConfig],
    rng: random.Random,
) -> tuple[HandEvaluation, HandEvaluation, HandEvaluation]:
    opening = draw_hand(deck, 7, rng)
    opening_eval = evaluate_hand(opening, card_config)

    free = draw_hand(deck, 7, rng)
    free_eval = evaluate_hand(free, card_config)

    london_seven = draw_hand(deck, 7, rng)
    london_six = choose_london_six(london_seven, card_config)
    london_eval = evaluate_hand(london_six, card_config)

    return opening_eval, free_eval, london_eval
