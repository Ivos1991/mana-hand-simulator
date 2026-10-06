from __future__ import annotations

import csv
from pathlib import Path

from .models import WeightedCard


def load_deck(path: str | Path) -> list[str]:
    cards: list[str] = []

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        quantity_text, card_name = line.split(maxsplit=1)
        quantity = int(quantity_text)
        cards.extend([card_name.strip()] * quantity)

    if not cards:
        raise ValueError("Decklist is empty.")

    return cards


def load_weights(path: str | Path) -> dict[str, WeightedCard]:
    weighted_cards: dict[str, WeightedCard] = {}

    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"card_name", "weight", "type"}

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Weight CSV must contain card_name, weight, and type columns."
            )

        for row in reader:
            name = row["card_name"].strip()
            weighted_cards[name] = WeightedCard(
                name=name,
                weight=float(row["weight"]),
                category=row["type"].strip(),
            )

    return weighted_cards
