from __future__ import annotations

import random
import re
from dataclasses import dataclass
from functools import lru_cache

from .models import CardConfig

COLORS = ("W", "U", "B", "R", "G")
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


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
            # For ordinary colored pips this is exact. Hybrid/Phyrexian symbols
            # are intentionally conservative in this v1 estimator.
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
    """Earliest conservative turn an acceleration piece can contribute.

    The old estimator let a 2-mana ramp spell both get cast and provide
    extra mana on turn 2, effectively spending the same mana twice.
    """
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
    if config.category in {"Mana Rock", "Ramp / Accelerator", "Conditional Mana"}:
        return 1
    if config.category == "Big Mana":
        return 2
    return 0


def _discount_amount(config: CardConfig) -> int:
    if config.category != "Cost Discount":
        return 0
    # The current weighting convention maps well enough for the known
    # discounts: 1.5-2 ~= 1 mana, 3 ~= 2 mana.
    return max(1, int(round(config.weight / 2)))


def _selected_lands(
    drawn: list[str],
    card_config: dict[str, CardConfig],
    land_slots: int,
    demanded_colors: tuple[str, ...],
) -> list[CardConfig]:
    lands = [
        card_config[name]
        for name in drawn
        if name in card_config and card_config[name].is_land
    ]
    lands.sort(
        key=lambda config: (
            sum(color in config.produces for color in demanded_colors),
            len(config.produces),
        ),
        reverse=True,
    )
    return lands[:land_slots]


COLOR_BITS = {
    "W": 1 << 0,
    "U": 1 << 1,
    "B": 1 << 2,
    "R": 1 << 3,
    "G": 1 << 4,
}


def _source_mask(produces: tuple[str, ...]) -> int:
    mask = 0
    for color in produces:
        mask |= COLOR_BITS.get(color, 0)
    return mask


@lru_cache(maxsize=50_000)
def _can_pay_colored_pips(
    source_masks: tuple[int, ...],
    requirements: tuple[int, int, int, int, int],
) -> bool:
    """Assign each mana source to at most one colored pip.

    A dual/tri-land can choose among its colors; it cannot pay several colored
    pips at once. This fixes the old estimator's multicolor over-counting.
    """
    required_colors: list[int] = []
    for index, count in enumerate(requirements):
        required_colors.extend([1 << index] * count)

    if not required_colors:
        return True
    if len(source_masks) < len(required_colors):
        return False

    # Hardest pips first: colors supported by fewer sources.
    required_colors.sort(
        key=lambda bit: sum(bool(mask & bit) for mask in source_masks)
    )

    def search(position: int, used: int) -> bool:
        if position == len(required_colors):
            return True

        bit = required_colors[position]
        for source_index, mask in enumerate(source_masks):
            flag = 1 << source_index
            if used & flag or not (mask & bit):
                continue
            if search(position + 1, used | flag):
                return True
        return False

    return search(0, 0)


def _castable_by_turn(
    drawn: list[str],
    turn: int,
    commander_mv: int,
    colored_requirements: dict[str, int],
    card_config: dict[str, CardConfig],
    card_data: dict[str, dict] | None = None,
) -> bool:
    demanded_colors = tuple(
        color for color in COLORS if colored_requirements.get(color, 0) > 0
    )

    land_count = sum(
        1
        for name in drawn
        if name in card_config and card_config[name].is_land
    )
    land_slots = min(turn, land_count)
    active_lands = _selected_lands(
        drawn, card_config, land_slots, demanded_colors
    )

    total_mana = len(active_lands)
    colored_source_masks: list[int] = [
        _source_mask(land.produces)
        for land in active_lands
    ]

    total_discount = 0

    for name in drawn:
        config = card_config.get(name)
        if not config or config.is_land:
            continue

        card = (card_data or {}).get(name, {})
        mana_value = card.get("cmc")
        activation_turn = _category_activation_turn(
            config.category,
            float(mana_value) if mana_value is not None else None,
        )
        if turn < activation_turn:
            continue

        bonus = _mana_bonus(config)
        total_mana += bonus

        if bonus > 0:
            mask = _source_mask(config.produces)
            colored_source_masks.extend([mask] * bonus)

        total_discount += _discount_amount(config)

    colored_total = sum(colored_requirements.values())
    generic_requirement = max(0, commander_mv - colored_total)
    effective_cost = colored_total + max(0, generic_requirement - total_discount)

    if total_mana < effective_cost:
        return False

    requirements = tuple(
        int(colored_requirements[color])
        for color in COLORS
    )
    return _can_pay_colored_pips(
        tuple(sorted(colored_source_masks)),
        requirements,
    )


def simulate_commander_cast_turns(
    deck: list[str],
    card_config: dict[str, CardConfig],
    commander_card: dict,
    *,
    iterations: int = 50_000,
    seed: int | None = None,
    max_turn: int = 10,
    card_data: dict[str, dict] | None = None,
) -> CommanderCastResult:
    if not deck:
        raise ValueError("Deck is empty.")
    if iterations <= 0:
        raise ValueError("iterations must be greater than zero.")

    commander_mv, colored_requirements = commander_requirements(commander_card)
    rng = random.Random(seed)
    first_counts = {turn: 0 for turn in range(1, max_turn + 1)}

    max_draws = min(len(deck), 7 + max_turn)

    for _ in range(iterations):
        drawn_order = rng.sample(deck, max_draws)
        first_turn: int | None = None

        for turn in range(1, max_turn + 1):
            # Multiplayer Commander draws on turn 1, so by turn N the player
            # has seen opening 7 + N cards before the main phase.
            seen = min(len(drawn_order), 7 + turn)
            drawn = drawn_order[:seen]

            if _castable_by_turn(
                drawn,
                turn,
                commander_mv,
                colored_requirements,
                card_config,
                card_data,
            ):
                first_turn = turn
                break

        if first_turn is not None:
            first_counts[first_turn] += 1

    first_pct = {
        turn: first_counts[turn] * 100.0 / iterations
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
