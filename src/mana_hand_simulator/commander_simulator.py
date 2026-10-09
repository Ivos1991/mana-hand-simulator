from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from .models import CardConfig

COLORS = ("W", "U", "B", "R", "G")
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")
COMMANDER_BATCH_SIZE = 50_000


@dataclass(frozen=True)
class CommanderCastResult:
    iterations: int
    first_cast_turn: dict[int, float]
    cast_by_turn: dict[int, float]


def commander_mana_cost(card: dict) -> str:
    mana_cost = str(card.get("mana_cost") or "")
    if mana_cost:
        return mana_cost
    for face in card.get("card_faces") or []:
        mana_cost = str(face.get("mana_cost") or "")
        if mana_cost:
            return mana_cost
    return ""


def commander_requirements(card: dict) -> tuple[int, dict[str, int]]:
    mana_cost = commander_mana_cost(card)
    colored = {color: 0 for color in COLORS}
    generic = 0

    for symbol in MANA_SYMBOL_RE.findall(mana_cost):
        upper = symbol.upper()
        if upper.isdigit():
            generic += int(upper)
            continue

        parts = upper.split("/")
        present = [color for color in COLORS if color in parts]
        if present:
            for color in present:
                colored[color] += 1
        elif upper == "X":
            continue

    mana_value = int(float(card.get("cmc") or 0))
    colored_total = sum(colored.values())
    if generic == 0 and mana_value > colored_total:
        generic = mana_value - colored_total

    return generic + colored_total, colored


def _category_activation_turn(
    category: str,
    mana_value: float | None = None,
) -> int:
    """Conservative turn when a setup card can start contributing."""
    base = {
        "Premium Acceleration": 1,
        "Mana Rock": 2,
        "Ramp / Accelerator": 2,
        "Cost Discount": 2,
        "Conditional Mana": 3,
        "Big Mana": 4,
    }.get(category, 99)

    if mana_value is None:
        return base

    mv = max(0, int(mana_value))
    if mv == 0 and category == "Premium Acceleration":
        return 1

    return max(base, mv + 1)


def _mana_bonus(config: CardConfig) -> int:
    if config.category == "Premium Acceleration":
        return 2
    if config.category in {
        "Mana Rock",
        "Ramp / Accelerator",
        "Conditional Mana",
    }:
        return 1
    if config.category == "Big Mana":
        return 2
    return 0


def _discount_amount(config: CardConfig) -> int:
    if config.category != "Cost Discount":
        return 0
    return max(1, int(round(config.weight / 2)))


@dataclass(frozen=True)
class _PreparedCommanderDeck:
    is_land: np.ndarray
    colors: np.ndarray
    color_mask: np.ndarray
    mask_onehot: np.ndarray
    activation_turn: np.ndarray
    mana_bonus: np.ndarray
    discount: np.ndarray
    land_priority: np.ndarray


def _prepare_commander_deck(
    deck: list[str],
    card_config: dict[str, CardConfig],
    demanded_colors: np.ndarray,
    card_data: dict[str, dict] | None = None,
) -> _PreparedCommanderDeck:
    size = len(deck)
    is_land = np.zeros(size, dtype=bool)
    colors = np.zeros((size, 5), dtype=np.int8)
    color_mask = np.zeros(size, dtype=np.int8)
    activation_turn = np.full(size, 99, dtype=np.int8)
    mana_bonus = np.zeros(size, dtype=np.int8)
    discount = np.zeros(size, dtype=np.int8)
    land_priority = np.full(size, -1, dtype=np.int16)

    for index, name in enumerate(deck):
        config = card_config.get(name)
        if config is None:
            continue

        is_land[index] = config.is_land
        for color_index, color in enumerate(COLORS):
            colors[index, color_index] = int(color in config.produces)
            if color in config.produces:
                color_mask[index] |= 1 << color_index

        metadata = (card_data or {}).get(name, {})
        mana_value = metadata.get("cmc")
        activation_turn[index] = _category_activation_turn(
            config.category,
            float(mana_value) if mana_value is not None else None,
        )
        mana_bonus[index] = _mana_bonus(config)
        discount[index] = _discount_amount(config)

        if config.is_land:
            demanded_count = int(
                np.sum(colors[index].astype(bool) & demanded_colors)
            )
            # Mirrors the old tuple sort:
            # (number of demanded colors produced, total colors produced).
            land_priority[index] = demanded_count * 10 + int(
                np.sum(colors[index])
            )

    mask_onehot = np.eye(32, dtype=np.int8)[color_mask]

    return _PreparedCommanderDeck(
        is_land=is_land,
        colors=colors,
        color_mask=color_mask,
        mask_onehot=mask_onehot,
        activation_turn=activation_turn,
        mana_bonus=mana_bonus,
        discount=discount,
        land_priority=land_priority,
    )


def _draw_order_batch(
    rng: np.random.Generator,
    batch_size: int,
    deck_size: int,
    draw_count: int,
) -> np.ndarray:
    """Generate an ordered sample without replacement using sparse retries."""
    if draw_count > deck_size:
        raise ValueError("Draw count cannot exceed deck size.")

    draws = np.empty((batch_size, draw_count), dtype=np.int16)

    for column in range(draw_count):
        candidate = rng.integers(
            0, deck_size, size=batch_size, dtype=np.int16
        )

        if column:
            duplicate = np.any(
                draws[:, :column] == candidate[:, None],
                axis=1,
            )
            while np.any(duplicate):
                candidate[duplicate] = rng.integers(
                    0,
                    deck_size,
                    size=int(np.count_nonzero(duplicate)),
                    dtype=np.int16,
                )
                duplicate = np.any(
                    draws[:, :column] == candidate[:, None],
                    axis=1,
                )

        draws[:, column] = candidate

    return draws


def _selected_land_stats(
    seen: np.ndarray,
    turn: int,
    prepared: _PreparedCommanderDeck,
) -> tuple[np.ndarray, np.ndarray]:
    batch, width = seen.shape
    priority = prepared.land_priority[seen]

    positions = np.arange(width, dtype=np.int16)
    stable_score = np.where(
        priority >= 0,
        priority.astype(np.int32) * 1000 + (width - positions),
        -1,
    )

    take = min(turn, width)
    chosen_positions = np.argpartition(
        -stable_score, take - 1, axis=1
    )[:, :take]
    chosen_cards = np.take_along_axis(seen, chosen_positions, axis=1)
    valid = np.take_along_axis(priority, chosen_positions, axis=1) >= 0

    land_count = np.sum(valid, axis=1, dtype=np.int16)
    mask_counts = np.sum(
        prepared.mask_onehot[chosen_cards] * valid[..., None],
        axis=1,
        dtype=np.int16,
    )
    return land_count, mask_counts


def _hall_color_check(
    mask_counts: np.ndarray,
    requirement: np.ndarray,
) -> np.ndarray:
    """Vectorized Hall check for assigning flexible sources to colored pips."""
    subset_ids = np.arange(1, 32, dtype=np.int16)
    source_masks = np.arange(32, dtype=np.int16)

    intersects = (
        (subset_ids[:, None] & source_masks[None, :]) != 0
    ).astype(np.int16)

    color_bits = (1 << np.arange(5, dtype=np.int16))
    subset_contains_color = (
        (subset_ids[:, None] & color_bits[None, :]) != 0
    ).astype(np.int16)
    required_by_subset = subset_contains_color @ requirement.astype(np.int16)

    active_subsets = required_by_subset > 0
    if not np.any(active_subsets):
        return np.ones(mask_counts.shape[0], dtype=bool)

    available_by_subset = mask_counts @ intersects.T
    return np.all(
        available_by_subset[:, active_subsets]
        >= required_by_subset[active_subsets],
        axis=1,
    )


def simulate_commander_cast_turns(
    deck: list[str],
    card_config: dict[str, CardConfig],
    commander_card: dict,
    *,
    iterations: int = 50_000,
    seed: int | None = None,
    max_turn: int = 10,
    batch_size: int = COMMANDER_BATCH_SIZE,
    card_data: dict[str, dict] | None = None,
) -> CommanderCastResult:
    if not deck:
        raise ValueError("Deck is empty.")
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")
    if max_turn <= 0:
        raise ValueError("max_turn must be greater than zero.")
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero.")

    commander_mv, colored_requirements = commander_requirements(commander_card)
    requirement = np.array(
        [colored_requirements[color] for color in COLORS],
        dtype=np.int16,
    )
    demanded_colors = requirement > 0
    colored_total = int(np.sum(requirement))
    generic_requirement = max(0, commander_mv - colored_total)

    prepared = _prepare_commander_deck(
        deck, card_config, demanded_colors, card_data
    )
    rng = np.random.default_rng(seed)
    first_counts = np.zeros(max_turn + 1, dtype=np.int64)

    max_draws = min(len(deck), 7 + max_turn)
    remaining = iterations

    while remaining:
        current_batch = min(batch_size, remaining)
        drawn_order = _draw_order_batch(
            rng,
            current_batch,
            len(deck),
            max_draws,
        )
        unresolved = np.ones(current_batch, dtype=bool)

        for turn in range(1, max_turn + 1):
            if not np.any(unresolved):
                break

            seen_count = min(max_draws, 7 + turn)
            seen = drawn_order[:, :seen_count]

            land_mana, source_mask_counts = _selected_land_stats(
                seen, turn, prepared
            )

            seen_activation = prepared.activation_turn[seen]
            active_nonlands = (
                (~prepared.is_land[seen])
                & (seen_activation <= turn)
            )

            bonuses = prepared.mana_bonus[seen] * active_nonlands
            bonus_mana = np.sum(bonuses, axis=1, dtype=np.int16)
            total_mana = land_mana + bonus_mana

            bonus_mask_counts = np.sum(
                prepared.mask_onehot[seen] * bonuses[..., None],
                axis=1,
                dtype=np.int16,
            )
            source_mask_counts = source_mask_counts + bonus_mask_counts

            discounts = prepared.discount[seen] * active_nonlands
            total_discount = np.sum(
                discounts, axis=1, dtype=np.int16
            )
            effective_cost = colored_total + np.maximum(
                0, generic_requirement - total_discount
            )

            enough_total = total_mana >= effective_cost
            enough_colors = _hall_color_check(
                source_mask_counts,
                requirement,
            )
            castable = unresolved & enough_total & enough_colors

            first_counts[turn] += int(np.count_nonzero(castable))
            unresolved &= ~castable

        remaining -= current_batch

    first_pct = {
        turn: float(first_counts[turn] * 100.0 / iterations)
        for turn in range(1, max_turn + 1)
    }

    running = 0.0
    cumulative: dict[int, float] = {}
    for turn in range(1, max_turn + 1):
        running += first_pct[turn]
        cumulative[turn] = running

    return CommanderCastResult(
        iterations=iterations,
        first_cast_turn=first_pct,
        cast_by_turn=cumulative,
    )
