from __future__ import annotations

from collections import Counter

from .models import HandEvaluation, HandTier, SimulationResult


def summarize(
    evaluations: list[HandEvaluation],
    color_demand: dict[str, float] | None = None,
) -> SimulationResult:
    counts = Counter(evaluation.tier for evaluation in evaluations)
    average_color_coverage = (
        sum(evaluation.color_coverage for evaluation in evaluations) / len(evaluations)
        if evaluations
        else 1.0
    )

    demanded_colors = [
        color
        for color in ("W", "U", "B", "R", "G")
        if color_demand and float(color_demand.get(color, 0.0)) > 0
    ]
    color_access_rates = {
        color: (
            sum(color in evaluation.color_access for evaluation in evaluations)
            * 100
            / len(evaluations)
            if evaluations
            else 0.0
        )
        for color in demanded_colors
    }
    full_color_access_rate = (
        sum(
            all(color in evaluation.color_access for color in demanded_colors)
            for evaluation in evaluations
        )
        * 100
        / len(evaluations)
        if evaluations and demanded_colors
        else 100.0
    )

    average_score = (
        sum(evaluation.score for evaluation in evaluations) / len(evaluations)
        if evaluations
        else 0.0
    )
    low_land_rate = (
        sum(evaluation.lands < 2 for evaluation in evaluations)
        * 100
        / len(evaluations)
        if evaluations
        else 0.0
    )
    high_land_rate = (
        sum(evaluation.lands > 4 for evaluation in evaluations)
        * 100
        / len(evaluations)
        if evaluations
        else 0.0
    )

    return SimulationResult(
        total=len(evaluations),
        counts={tier: counts.get(tier, 0) for tier in HandTier},
        average_color_coverage=average_color_coverage,
        color_access_rates=color_access_rates,
        full_color_access_rate=full_color_access_rate,
        average_score=average_score,
        low_land_rate=low_land_rate,
        high_land_rate=high_land_rate,
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
        f"  A/B: {ab_total:6.2f}%\n"
        f"  Avg color coverage: {result.average_color_coverage * 100:6.2f}%"
    )
