from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .deck_loader import load_card_config, load_deck
from .fast_simulator import (
    BATCH_SIZE,
    ResultAccumulator,
    choose_london_six_fast,
    draw_index_hands,
    evaluate_index_hands,
    prepare_deck,
)
from .models import CardConfig, SimulationResult


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
    batch_size: int = BATCH_SIZE,
) -> MulliganSimulation:
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")
    if len(deck) < 7:
        raise ValueError("Deck must contain at least seven cards.")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")

    prepared = prepare_deck(deck, card_config, color_demand)
    rng = np.random.default_rng(seed)

    opening_acc = ResultAccumulator(prepared.demanded_mask)
    free_acc = ResultAccumulator(prepared.demanded_mask)
    final_acc = ResultAccumulator(prepared.demanded_mask)

    seen_ab_after_free = 0
    remaining = iterations

    while remaining:
        current_batch = min(batch_size, remaining)

        opening_indices = draw_index_hands(
            rng, current_batch, len(deck), hand_size=7
        )
        opening = evaluate_index_hands(opening_indices, prepared)
        opening_acc.add(opening)

        opening_keep = opening.tier >= 2
        final_acc.add(opening, opening_keep)
        seen_ab_after_free += int(np.count_nonzero(opening_keep))

        free_indices = draw_index_hands(
            rng, current_batch, len(deck), hand_size=7
        )
        free = evaluate_index_hands(free_indices, prepared)
        free_acc.add(free)

        needs_free = ~opening_keep
        free_keep = needs_free & (free.tier >= 2)
        final_acc.add(free, free_keep)
        seen_ab_after_free += int(np.count_nonzero(free_keep))

        needs_london = needs_free & ~(free.tier >= 2)
        london_count = int(np.count_nonzero(needs_london))

        if london_count:
            london_indices = draw_index_hands(
                rng, london_count, len(deck), hand_size=7
            )
            london = choose_london_six_fast(london_indices, prepared)
            final_acc.add(london)

        remaining -= current_batch

    return MulliganSimulation(
        opening=opening_acc.result(),
        free_mulligan=free_acc.result(),
        final=final_acc.result(),
        seen_ab_after_free_mulligan=seen_ab_after_free * 100.0 / iterations,
    )


def run_simulation(
    deck_path: str | Path,
    config_path: str | Path,
    *,
    iterations: int = 100_000,
    seed: int | None = None,
    color_demand: dict[str, float] | None = None,
    batch_size: int = BATCH_SIZE,
) -> MulliganSimulation:
    return run_simulation_from_data(
        load_deck(deck_path),
        load_card_config(config_path),
        iterations=iterations,
        seed=seed,
        color_demand=color_demand,
        batch_size=batch_size,
    )
