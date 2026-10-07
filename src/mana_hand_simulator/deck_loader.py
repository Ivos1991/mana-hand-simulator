from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from .models import CardConfig


def parse_deck_text(text: str) -> list[str]:
    cards: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            quantity_text, card_name = line.split(maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid decklist line: {raw_line!r}. Expected 'quantity card name'."
            ) from exc

        quantity = int(quantity_text)
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive: {raw_line!r}")

        cards.extend([card_name.strip()] * quantity)

    if not cards:
        raise ValueError("Decklist is empty.")

    return cards


def load_deck(path: str | Path) -> list[str]:
    return parse_deck_text(Path(path).read_text(encoding="utf-8"))


def parse_card_config_csv(text: str) -> dict[str, CardConfig]:
    configs: dict[str, CardConfig] = {}
    reader = csv.DictReader(StringIO(text))
    required = {"card_name", "weight", "type", "is_land"}

    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError(
            "Card config CSV must contain card_name, weight, type, and is_land."
        )

    for row in reader:
        name = row["card_name"].strip()
        if not name:
            continue

        is_land = row["is_land"].strip().casefold() in {"1", "true", "yes", "y"}
        configs[name] = CardConfig(
            name=name,
            weight=float(row["weight"]),
            category=row["type"].strip(),
            is_land=is_land,
        )

    return configs


def load_card_config(path: str | Path) -> dict[str, CardConfig]:
    return parse_card_config_csv(Path(path).read_text(encoding="utf-8"))
