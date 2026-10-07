from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HandTier(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class CardConfig:
    name: str
    weight: float
    category: str
    is_land: bool = False
    produces: tuple[str, ...] = ()


@dataclass(frozen=True)
class HandEvaluation:
    tier: HandTier
    score: float
    lands: int
    weighted_cards: tuple[str, ...]
    color_coverage: float = 1.0
    color_access: tuple[str, ...] = ()


@dataclass(frozen=True)
class SimulationResult:
    total: int
    counts: dict[HandTier, int]
    average_color_coverage: float = 1.0
    color_access_rates: dict[str, float] | None = None
    full_color_access_rate: float = 1.0

    def percentages(self) -> dict[HandTier, float]:
        if self.total == 0:
            return {tier: 0.0 for tier in HandTier}
        return {
            tier: self.counts.get(tier, 0) * 100 / self.total
            for tier in HandTier
        }
