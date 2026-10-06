from __future__ import annotations

import argparse

from .simulator import run_simulation
from .statistics import format_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Simulate opening hands and mulligans for a configurable MTG deck."
    )
    parser.add_argument("--deck", default="data/decklist.txt")
    parser.add_argument("--config", default="data/card_config.csv")
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--seed", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    result = run_simulation(
        args.deck,
        args.config,
        iterations=args.iterations,
        seed=args.seed,
    )

    print(format_result("Opening 7", result.opening))
    print()
    print(format_result("Free mulligan 7", result.free_mulligan))
    print()
    print(
        f"Chance of seeing A/B by the end of the free mulligan: "
        f"{result.seen_ab_after_free_mulligan:.2f}%"
    )
    print()
    print(format_result("Final after London mulligan to 6", result.final))


if __name__ == "__main__":
    main()
