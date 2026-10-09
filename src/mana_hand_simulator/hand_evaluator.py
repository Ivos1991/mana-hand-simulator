from __future__ import annotations

from collections.abc import Iterable

from .models import CardConfig, HandEvaluation, HandTier

COLORS = ("W", "U", "B", "R", "G")


def calculate_color_access(
    cards: tuple[str, ...],
    card_config: dict[str, CardConfig],
) -> tuple[str, ...]:
    """Return the colored mana symbols available from sources in this hand."""
    available: set[str] = set()
    for card in cards:
        config = card_config.get(card)
        if not config:
            continue
        available.update(color for color in config.produces if color in COLORS)
    return tuple(color for color in COLORS if color in available)


def calculate_color_coverage(
    cards: tuple[str, ...],
    card_config: dict[str, CardConfig],
    color_demand: dict[str, float] | None,
) -> float:
    """Return 0..1 coverage of the deck's colored demand by this hand's sources.

    Colorless demand is treated as "no colored requirement", not as a literal
    requirement for {C}. This keeps ordinary artifacts/colorless spells from
    forcing dedicated colorless sources.
    """
    if not color_demand:
        return 1.0

    colored_demand = {
        color: max(0.0, float(color_demand.get(color, 0.0)))
        for color in COLORS
    }
    total_colored = sum(colored_demand.values())
    if total_colored <= 0:
        return 1.0

    mana_sources = [
        card_config[card]
        for card in cards
        if card in card_config and card_config[card].produces
    ]
    if not mana_sources:
        return 0.0

    source_slots = len(mana_sources)
    weighted_coverage = 0.0

    for color, raw_demand in colored_demand.items():
        if raw_demand <= 0:
            continue

        demand_share = raw_demand / total_colored
        expected_sources = max(1.0, source_slots * demand_share)
        available_sources = sum(color in source.produces for source in mana_sources)
        color_coverage = min(1.0, available_sources / expected_sources)
        weighted_coverage += demand_share * color_coverage

    # If part of the deck is colorless, colored requirements matter less overall.
    colored_pressure = min(1.0, total_colored / 100.0)
    return 1.0 - colored_pressure * (1.0 - weighted_coverage)


def _cap_tier_for_color_coverage(tier: HandTier, coverage: float) -> HandTier:
    """Prevent color-starved hands from receiving unrealistically high tiers."""
    if coverage < 0.55:
        return HandTier.D
    if coverage < 0.70 and tier in {HandTier.A, HandTier.B}:
        return HandTier.C
    if coverage < 0.85 and tier is HandTier.A:
        return HandTier.B
    return tier


def evaluate_hand(
    hand: Iterable[str],
    card_config: dict[str, CardConfig],
    color_demand: dict[str, float] | None = None,
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

    base_tier = classify_hand(lands=lands, score=score)
    color_coverage = calculate_color_coverage(cards, card_config, color_demand)
    color_access = calculate_color_access(cards, card_config)
    tier = _cap_tier_for_color_coverage(base_tier, color_coverage)

    return HandEvaluation(
        tier=tier,
        score=score,
        lands=lands,
        weighted_cards=scored_cards,
        color_coverage=color_coverage,
        color_access=color_access,
    )


def classify_hand(*, lands: int, score: float) -> HandTier:
    """Default A/B/C/D heuristic for opening-hand quality."""
    if lands < 2 or lands > 5:
        return HandTier.D

    if lands in {2, 3} and score >= 7:
        return HandTier.A

    if lands in {2, 3, 4} and score >= 4:
        return HandTier.B

    if lands in {2, 3, 4} and score >= 1:
        return HandTier.C

    return HandTier.D
