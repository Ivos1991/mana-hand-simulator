from __future__ import annotations

import csv
from pathlib import Path

from .models import CardConfig


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


def load_card_config(path: str | Path) -> dict[str, CardConfig]:
    configs: dict[str, CardConfig] = {}

    with Path(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"card_name", "weight", "type", "is_land"}

        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                "Card config CSV must contain card_name, weight, type, and is_land."
            )

        for row in reader:
            name = row["card_name"].strip()
            is_land = row["is_land"].strip().casefold() in {"1", "true", "yes", "y"}
            configs[name] = CardConfig(
                name=name,
                weight=float(row["weight"]),
                category=row["type"].strip(),
                is_land=is_land,
            )

    return configs
