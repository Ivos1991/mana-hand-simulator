from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from .deck_loader import load_card_config, load_deck
from .models import CardConfig, HandEvaluation, SimulationResult
from .mulligan import KEEP_TIERS, simulate_mulligan_sequence
from .statistics import summarize


@dataclass(frozen=True)
class MulliganSimulation:
    opening: SimulationResult
    free_mulligan: SimulationResult
    final: SimulationResult
    seen_ab_after_free_mulligan: float


def run_simulation_from_data(
    deck: list[str],
    card_config: dict[str, CardConfig],
    *,
    iterations: int = 100_000,
    seed: int | None = None,
    color_demand: dict[str, float] | None = None,
) -> MulliganSimulation:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")
    if len(deck) < 7:
        raise ValueError("Deck must contain at least seven cards.")

    rng = random.Random(seed)

    opening_evals: list[HandEvaluation] = []
    free_evals: list[HandEvaluation] = []
    final_evals: list[HandEvaluation] = []

    seen_ab_after_free = 0

    for _ in range(iterations):
        opening, free, london = simulate_mulligan_sequence(
            deck, card_config, rng, color_demand
        )

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


def run_simulation(
    deck_path: str | Path,
    config_path: str | Path,
    *,
    iterations: int = 100_000,
    seed: int | None = None,
    color_demand: dict[str, float] | None = None,
) -> MulliganSimulation:
    return run_simulation_from_data(
        load_deck(deck_path),
        load_card_config(config_path),
        iterations=iterations,
        seed=seed,
        color_demand=color_demand,
    )
