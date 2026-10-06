from __future__ import annotations

from collections.abc import Iterable

from .models import CardConfig, HandEvaluation, HandTier


def evaluate_hand(
    hand: Iterable[str],
    card_config: dict[str, CardConfig],
) -> HandEvaluation:
    cards = tuple(hand)
    lands = sum(
        1
        for card in cards
        if card in card_config and card_config[card].is_land
    )

    scored_cards = tuple(
        card
        for card in cards
        if card in card_config and card_config[card].weight > 0
    )
    score = sum(card_config[card].weight for card in scored_cards)

    tier = classify_hand(lands=lands, score=score)

    return HandEvaluation(
        tier=tier,
        score=score,
        lands=lands,
        weighted_cards=scored_cards,
    )


def classify_hand(*, lands: int, score: float) -> HandTier:
    """Default A/B/C/D heuristic for opening-hand quality."""
    if lands < 2 or lands > 5:
        return HandTier.D

    if lands in {2, 3} and score >= 5:
        return HandTier.A

    if lands in {2, 3, 4} and score >= 3:
        return HandTier.B

    if lands in {2, 3, 4} and score >= 1:
        return HandTier.C

    return HandTier.D
