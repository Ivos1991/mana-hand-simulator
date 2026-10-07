from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path

from .models import CardConfig


MOXFIELD_TAG_RE = re.compile(r"\\s+#.*$")
MOXFIELD_FOIL_RE = re.compile(r"\\s+\\*[^*]+\\*\\s*$")
MOXFIELD_PRINTING_RE = re.compile(
    r"\\s+\\([A-Za-z0-9]+\\)\\s+\\S+\\s*$"
)


def clean_exported_card_name(raw_name: str) -> str:
    """Remove common Moxfield printing metadata/tags while preserving card names.

    Examples:
      "Alpha Deathclaw (PIP) 91 #Removal" -> "Alpha Deathclaw"
      "Commercial District (PMKM) 259p *F*" -> "Commercial District"
      "Disciple of Freyalise / Garden of Freyalise (MH3) 250 #Draw"
        -> "Disciple of Freyalise / Garden of Freyalise"
    """
    name = raw_name.strip()

    # Moxfield tags are appended after a whitespace-prefixed '#'.
    name = MOXFIELD_TAG_RE.sub("", name).rstrip()

    # Foil / finish markers such as *F* can appear after collector metadata.
    name = MOXFIELD_FOIL_RE.sub("", name).rstrip()

    # Printing metadata is normally "(SET) collector-number". Collector
    # numbers may contain suffixes, hyphens, stars, etc., so treat the final
    # token opaquely rather than trying to enumerate every possible format.
    name = MOXFIELD_PRINTING_RE.sub("", name).rstrip()

    return name


def parse_deck_text(text: str) -> list[str]:
    cards: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        try:
            quantity_text, raw_card_name = line.split(maxsplit=1)
        except ValueError as exc:
            raise ValueError(
                f"Invalid decklist line: {raw_line!r}. Expected 'quantity card name'."
            ) from exc

        try:
            quantity = int(quantity_text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid quantity in decklist line: {raw_line!r}."
            ) from exc

        if quantity <= 0:
            raise ValueError(f"Quantity must be positive: {raw_line!r}")

        card_name = clean_exported_card_name(raw_card_name)
        if not card_name:
            raise ValueError(f"Missing card name after parsing: {raw_line!r}")

        cards.extend([card_name] * quantity)

    if not cards:
        raise ValueError("Decklist is empty.")

    return cards


def load_deck(path: str | Path) -> list[str]:
    return parse_deck_text(Path(path).read_text(encoding="utf-8"))


def _parse_produces(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    raw = value.strip().upper()
    if raw in {"", "NONE", "N/A"}:
        return ()
    return tuple(color for color in "WUBRGC" if color in raw)


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
            produces=_parse_produces(row.get("produces")),
        )

    return configs


def load_card_config(path: str | Path) -> dict[str, CardConfig]:
    return parse_card_config_csv(Path(path).read_text(encoding="utf-8"))
