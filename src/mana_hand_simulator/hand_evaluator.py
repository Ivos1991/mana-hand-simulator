from __future__ import annotations

from collections.abc import Iterable

from .models import HandEvaluation, HandTier, WeightedCard


def is_land(card_name: str) -> bool:
    normalized = card_name.casefold()
    land_tokens = (
        "swamp",
        "island",
        "forest",
        "mountain",
        "plains",
        "tomb",
        "coffers",
        "nykthos",
        "stronghold",
        "bog",
        "castle",
        "tower",
        "cave",
        "beacon",
        "market",
    )
    return any(token in normalized for token in land_tokens)


def evaluate_hand(
    hand: Iterable[str],
    weights: dict[str, WeightedCard],
) -> HandEvaluation:
    cards = tuple(hand)
    lands = sum(1 for card in cards if is_land(card))

    scored_cards = tuple(card for card in cards if card in weights)
    score = sum(weights[card].weight for card in scored_cards)

    tier = classify_hand(lands=lands, score=score)

    return HandEvaluation(
        tier=tier,
        score=score,
        lands=lands,
        weighted_cards=scored_cards,
    )


def classify_hand(*, lands: int, score: float) -> HandTier:
    """Default heuristic. Edit this module to change tier semantics."""
    if lands < 2 or lands > 5:
        return HandTier.D

    if lands in {2, 3} and score >= 5:
        return HandTier.A

    if lands in {2, 3, 4} and score >= 3:
        return HandTier.B

    if lands in {2, 3, 4} and score >= 1:
        return HandTier.C

    return HandTier.D
