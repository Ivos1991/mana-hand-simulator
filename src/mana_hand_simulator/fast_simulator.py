from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import CardConfig, HandTier, SimulationResult

COLORS = ("W", "U", "B", "R", "G")
# Compact numeric order used only inside the vectorized engine.
TIER_D = 0
TIER_C = 1
TIER_B = 2
TIER_A = 3
BATCH_SIZE = 20_000


@dataclass(frozen=True)
class PreparedDeck:
    names: tuple[str, ...]
    is_land: np.ndarray
    weight: np.ndarray
    source_any: np.ndarray
    color_sources: np.ndarray
    demand_share: np.ndarray
    colored_pressure: float
    demanded_mask: np.ndarray


@dataclass(frozen=True)
class BatchEvaluation:
    tier: np.ndarray
    score: np.ndarray
    lands: np.ndarray
    coverage: np.ndarray
    access: np.ndarray


class ResultAccumulator:
    def __init__(self, demanded_mask: np.ndarray) -> None:
        self.total = 0
        self.tier_counts = np.zeros(4, dtype=np.int64)
        self.coverage_sum = 0.0
        self.score_sum = 0.0
        self.low_land_count = 0
        self.high_land_count = 0
        self.access_counts = np.zeros(5, dtype=np.int64)
        self.full_access_count = 0
        self.demanded_mask = demanded_mask

    def add(self, evaluation: BatchEvaluation, mask: np.ndarray | None = None) -> None:
        if mask is None:
            tier = evaluation.tier
            score = evaluation.score
            lands = evaluation.lands
            coverage = evaluation.coverage
            access = evaluation.access
        else:
            tier = evaluation.tier[mask]
            score = evaluation.score[mask]
            lands = evaluation.lands[mask]
            coverage = evaluation.coverage[mask]
            access = evaluation.access[mask]

        count = int(tier.size)
        if count == 0:
            return

        self.total += count
        self.tier_counts += np.bincount(tier, minlength=4)
        self.coverage_sum += float(np.sum(coverage, dtype=np.float64))
        self.score_sum += float(np.sum(score, dtype=np.float64))
        self.low_land_count += int(np.count_nonzero(lands < 2))
        self.high_land_count += int(np.count_nonzero(lands > 4))
        self.access_counts += np.sum(access, axis=0, dtype=np.int64)

        if np.any(self.demanded_mask):
            self.full_access_count += int(
                np.count_nonzero(np.all(access[:, self.demanded_mask], axis=1))
            )
        else:
            self.full_access_count += count

    def result(self) -> SimulationResult:
        if self.total == 0:
            return SimulationResult(
                total=0,
                counts={tier: 0 for tier in HandTier},
                average_color_coverage=1.0,
                color_access_rates={},
                full_color_access_rate=100.0,
            )

        numeric_to_tier = {
            TIER_A: HandTier.A,
            TIER_B: HandTier.B,
            TIER_C: HandTier.C,
            TIER_D: HandTier.D,
        }
        counts = {
            tier: int(self.tier_counts[numeric])
            for numeric, tier in numeric_to_tier.items()
        }

        access_rates = {
            color: float(self.access_counts[index] * 100.0 / self.total)
            for index, color in enumerate(COLORS)
            if self.demanded_mask[index]
        }

        return SimulationResult(
            total=self.total,
            counts=counts,
            average_color_coverage=self.coverage_sum / self.total,
            color_access_rates=access_rates,
            full_color_access_rate=self.full_access_count * 100.0 / self.total,
            average_score=self.score_sum / self.total,
            low_land_rate=self.low_land_count * 100.0 / self.total,
            high_land_rate=self.high_land_count * 100.0 / self.total,
        )


def prepare_deck(
    deck: list[str],
    card_config: dict[str, CardConfig],
    color_demand: dict[str, float] | None,
) -> PreparedDeck:
    names = tuple(deck)
    size = len(names)

    is_land = np.zeros(size, dtype=np.int8)
    weight = np.zeros(size, dtype=np.float64)
    source_any = np.zeros(size, dtype=np.int8)
    color_sources = np.zeros((size, 5), dtype=np.int8)

    for index, name in enumerate(names):
        config = card_config.get(name)
        if config is None:
            continue

        is_land[index] = int(config.is_land)
        weight[index] = float(config.weight)
        source_any[index] = int(bool(config.produces))
        for color_index, color in enumerate(COLORS):
            color_sources[index, color_index] = int(color in config.produces)

    demand = np.array(
        [
            max(0.0, float((color_demand or {}).get(color, 0.0)))
            for color in COLORS
        ],
        dtype=np.float64,
    )
    total_colored = float(np.sum(demand))
    if total_colored > 0:
        demand_share = demand / total_colored
        colored_pressure = min(1.0, total_colored / 100.0)
    else:
        demand_share = np.zeros(5, dtype=np.float64)
        colored_pressure = 0.0

    return PreparedDeck(
        names=names,
        is_land=is_land,
        weight=weight,
        source_any=source_any,
        color_sources=color_sources,
        demand_share=demand_share,
        colored_pressure=colored_pressure,
        demanded_mask=demand > 0,
    )


def _tier_from_metrics(
    lands: np.ndarray,
    score: np.ndarray,
    coverage: np.ndarray,
) -> np.ndarray:
    tier = np.full(lands.shape, TIER_D, dtype=np.int8)

    valid = (lands >= 2) & (lands <= 4)
    tier[valid & (score >= 1)] = TIER_C
    tier[valid & (score >= 3)] = TIER_B
    tier[((lands == 2) | (lands == 3)) & (score >= 5)] = TIER_A

    # Five-land hands remain D, matching classify_hand's current behavior.
    tier[(lands > 5) | (lands < 2)] = TIER_D

    tier[coverage < 0.55] = TIER_D
    tier[(coverage < 0.70) & (tier >= TIER_B)] = TIER_C
    tier[(coverage < 0.85) & (tier == TIER_A)] = TIER_B

    return tier


def _coverage_from_counts(
    source_slots: np.ndarray,
    color_counts: np.ndarray,
    prepared: PreparedDeck,
) -> np.ndarray:
    leading_shape = source_slots.shape

    if not np.any(prepared.demanded_mask):
        return np.ones(leading_shape, dtype=np.float64)

    expected_sources = np.maximum(
        1.0,
        source_slots[..., None] * prepared.demand_share,
    )
    per_color = np.minimum(
        1.0,
        np.divide(
            color_counts,
            expected_sources,
            out=np.zeros_like(color_counts, dtype=np.float64),
            where=expected_sources > 0,
        ),
    )
    weighted = np.sum(per_color * prepared.demand_share, axis=-1)
    coverage = 1.0 - prepared.colored_pressure * (1.0 - weighted)

    # Preserve the original evaluator behavior: a hand with zero configured
    # mana sources has zero color coverage whenever colored demand exists.
    return np.where(source_slots > 0, coverage, 0.0)


def evaluate_index_hands(
    indices: np.ndarray,
    prepared: PreparedDeck,
) -> BatchEvaluation:
    lands = np.sum(prepared.is_land[indices], axis=1, dtype=np.int16)
    score = np.sum(prepared.weight[indices], axis=1, dtype=np.float64)
    source_slots = np.sum(prepared.source_any[indices], axis=1, dtype=np.int16)
    color_counts = np.sum(
        prepared.color_sources[indices],
        axis=1,
        dtype=np.int16,
    )

    coverage = _coverage_from_counts(source_slots, color_counts, prepared)
    tier = _tier_from_metrics(lands, score, coverage)
    access = color_counts > 0

    return BatchEvaluation(
        tier=tier,
        score=score,
        lands=lands,
        coverage=coverage,
        access=access,
    )


def draw_index_hands(
    rng: np.random.Generator,
    batch_size: int,
    deck_size: int,
    hand_size: int = 7,
) -> np.ndarray:
    """Draw many independent hands without replacement inside each hand.

    Random-key sampling moves the expensive inner loop into NumPy's compiled
    argpartition implementation. Batching bounds memory even for 1M+ trials.
    """
    keys = rng.random((batch_size, deck_size), dtype=np.float32)
    return np.argpartition(keys, hand_size - 1, axis=1)[:, :hand_size]


def choose_london_six_fast(
    seven_indices: np.ndarray,
    prepared: PreparedDeck,
) -> BatchEvaluation:
    """Evaluate all seven possible bottom choices at once and pick the best."""

    full_lands = np.sum(prepared.is_land[seven_indices], axis=1, dtype=np.int16)
    full_score = np.sum(prepared.weight[seven_indices], axis=1, dtype=np.float64)
    full_sources = np.sum(
        prepared.source_any[seven_indices], axis=1, dtype=np.int16
    )
    full_colors = np.sum(
        prepared.color_sources[seven_indices],
        axis=1,
        dtype=np.int16,
    )

    lands = full_lands[:, None] - prepared.is_land[seven_indices]
    score = full_score[:, None] - prepared.weight[seven_indices]
    source_slots = full_sources[:, None] - prepared.source_any[seven_indices]
    color_counts = (
        full_colors[:, None, :] - prepared.color_sources[seven_indices]
    )

    coverage = _coverage_from_counts(source_slots, color_counts, prepared)
    tier = _tier_from_metrics(lands, score, coverage)
    access = color_counts > 0

    # Lexicographic order exactly mirrors choose_london_six:
    # tier -> coverage -> score -> closeness to 3 lands.
    best = np.zeros(seven_indices.shape[0], dtype=np.int8)
    rows = np.arange(seven_indices.shape[0])

    for candidate in range(1, 7):
        current = best
        better = tier[:, candidate] > tier[rows, current]

        tied = tier[:, candidate] == tier[rows, current]
        better |= tied & (coverage[:, candidate] > coverage[rows, current])

        tied &= coverage[:, candidate] == coverage[rows, current]
        better |= tied & (score[:, candidate] > score[rows, current])

        tied &= score[:, candidate] == score[rows, current]
        candidate_distance = np.abs(lands[:, candidate] - 3)
        current_distance = np.abs(lands[rows, current] - 3)
        better |= tied & (candidate_distance < current_distance)

        best = np.where(better, candidate, best).astype(np.int8, copy=False)

    return BatchEvaluation(
        tier=tier[rows, best],
        score=score[rows, best],
        lands=lands[rows, best],
        coverage=coverage[rows, best],
        access=access[rows, best, :],
    )
