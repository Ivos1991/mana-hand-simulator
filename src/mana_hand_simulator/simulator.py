from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from .deck_loader import load_deck, load_weights
from .models import HandEvaluation, SimulationResult
from .mulligan import KEEP_TIERS, simulate_mulligan_sequence
from .statistics import summarize


@dataclass(frozen=True)
class MulliganSimulation:
    opening: SimulationResult
    free_mulligan: SimulationResult
    final: SimulationResult
    seen_ab_after_free_mulligan: float


def run_simulation(
    deck_path: str | Path,
    weights_path: str | Path,
    *,
    iterations: int = 100_000,
    seed: int | None = None,
) -> MulliganSimulation:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")

    deck = load_deck(deck_path)
    weights = load_weights(weights_path)
    rng = random.Random(seed)

    opening_evals: list[HandEvaluation] = []
    free_evals: list[HandEvaluation] = []
    final_evals: list[HandEvaluation] = []

    seen_ab_after_free = 0

    for _ in range(iterations):
        opening, free, london = simulate_mulligan_sequence(deck, weights, rng)

        opening_evals.append(opening)
        free_evals.append(free)

        if opening.tier in KEEP_TIERS:
            final_evals.append(opening)
            seen_ab_after_free += 1
            continue

        if free.tier in KEEP_TIERS:
            final_evals.append(free)
            seen_ab_after_free += 1
            continue

        final_evals.append(london)

    return MulliganSimulation(
        opening=summarize(opening_evals),
        free_mulligan=summarize(free_evals),
        final=summarize(final_evals),
        seen_ab_after_free_mulligan=seen_ab_after_free * 100 / iterations,
    )
