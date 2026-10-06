from __future__ import annotations

from collections import Counter

from .models import HandEvaluation, HandTier, SimulationResult


def summarize(evaluations: list[HandEvaluation]) -> SimulationResult:
    counts = Counter(evaluation.tier for evaluation in evaluations)
    return SimulationResult(
        total=len(evaluations),
        counts={tier: counts.get(tier, 0) for tier in HandTier},
    )


def format_result(label: str, result: SimulationResult) -> str:
    percentages = result.percentages()
    ab_total = percentages[HandTier.A] + percentages[HandTier.B]

    return (
        f"{label}\n"
        f"  A: {percentages[HandTier.A]:6.2f}%\n"
        f"  B: {percentages[HandTier.B]:6.2f}%\n"
        f"  C: {percentages[HandTier.C]:6.2f}%\n"
        f"  D: {percentages[HandTier.D]:6.2f}%\n"
        f"  A/B: {ab_total:6.2f}%"
    )
