from __future__ import annotations

import json
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COLORS = ("W", "U", "B", "R", "G")
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
USER_AGENT = "ManaHandSimulator/0.2 (https://github.com/Ivos1991/mana-hand-simulator)"


def fetch_cards(card_names: list[str]) -> tuple[dict[str, dict], list[str]]:
    """Fetch Scryfall card objects in batches using the public collection endpoint."""
    unique_names = list(dict.fromkeys(card_names))
    cards: dict[str, dict] = {}
    missing: list[str] = []

    for start in range(0, len(unique_names), 75):
        batch = unique_names[start : start + 75]
        payload = json.dumps(
            {"identifiers": [{"name": name} for name in batch]}
        ).encode("utf-8")
        request = Request(
            SCRYFALL_COLLECTION_URL,
            data=payload,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=20) as response:
                result = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Scryfall lookup failed: {exc}") from exc

        for card in result.get("data", []):
            cards[card["name"]] = card

        for item in result.get("not_found", []):
            name = item.get("name")
            if name:
                missing.append(name)

        # Scryfall asks API clients to keep request rates modest.
        if start + 75 < len(unique_names):
            time.sleep(0.12)

    # Exact-name lookup is normally sufficient, but preserve the requested names
    # when Scryfall canonicalizes punctuation/casing.
    by_casefold = {name.casefold(): card for name, card in cards.items()}
    normalized: dict[str, dict] = {}
    for requested in unique_names:
        match = by_casefold.get(requested.casefold())
        if match is not None:
            normalized[requested] = match

    return normalized, missing


def calculate_card_color_distribution(
    deck: list[str],
    cards: dict[str, dict],
) -> dict[str, float]:
    """Calculate spell color distribution, excluding lands.

    Each nonland card contributes one unit. A multicolor card divides that unit
    evenly among its colors. A colorless nonland card contributes to C.
    """
    counts = Counter(deck)
    totals = {color: 0.0 for color in (*COLORS, "C")}
    considered = 0.0

    for name, quantity in counts.items():
        card = cards.get(name)
        if not card:
            continue

        type_line = str(card.get("type_line", ""))
        if "Land" in type_line:
            continue

        colors = list(card.get("colors") or [])
        considered += quantity

        if not colors:
            totals["C"] += quantity
            continue

        share = quantity / len(colors)
        for color in colors:
            if color in COLORS:
                totals[color] += share

    if considered == 0:
        return {color: 0.0 for color in (*COLORS, "C")}

    raw = {
        color: totals[color] * 100.0 / considered
        for color in (*COLORS, "C")
    }
    rounded = {color: round(value, 1) for color, value in raw.items()}

    # Keep the editable UI total at exactly 100.0 after display rounding.
    residual = round(100.0 - sum(rounded.values()), 1)
    if residual:
        largest = max(raw, key=raw.get)
        rounded[largest] = round(rounded[largest] + residual, 1)

    return rounded


def produced_mana(card: dict) -> str:
    """Return a compact WUBRGC string from Scryfall's produced_mana field."""
    values = set(card.get("produced_mana") or [])
    return "".join(color for color in "WUBRGC" if color in values)


def card_image_url(card: dict) -> str | None:
    image_uris = card.get("image_uris") or {}
    if image_uris.get("normal"):
        return image_uris["normal"]

    for face in card.get("card_faces") or []:
        face_images = face.get("image_uris") or {}
        if face_images.get("normal"):
            return face_images["normal"]

    return None
