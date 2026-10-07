from __future__ import annotations

import json
import re
import time
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

COLORS = ("W", "U", "B", "R", "G")
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
USER_AGENT = "ManaHandSimulator/0.3 (https://github.com/Ivos1991/mana-hand-simulator)"
MANA_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def fetch_cards(card_names: list[str]) -> tuple[dict[str, dict], list[str]]:
    """Fetch Scryfall card objects in batches using the public collection endpoint.

    Scryfall's collection endpoint accepts up to 75 identifiers per request, so
    a normal 99-card singleton Commander library needs only two API requests.
    The returned card objects already contain mana cost, mana value, type,
    legality, oracle text, produced mana, images, and other metadata.
    """
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

        if start + 75 < len(unique_names):
            time.sleep(0.12)

    by_casefold = {name.casefold(): card for name, card in cards.items()}
    normalized: dict[str, dict] = {}
    for requested in unique_names:
        match = by_casefold.get(requested.casefold())
        if match is not None:
            normalized[requested] = match

    return normalized, missing


def _nonland_faces(card: dict) -> list[dict]:
    faces = card.get("card_faces") or []
    if not faces:
        return [card] if "Land" not in str(card.get("type_line", "")) else []

    nonland = [
        face for face in faces
        if "Land" not in str(face.get("type_line", ""))
    ]
    return nonland


def colored_pip_counts(card: dict) -> Counter[str]:
    """Count W/U/B/R/G pips in the casting costs of a card's nonland face(s)."""
    counts: Counter[str] = Counter()

    for face in _nonland_faces(card):
        mana_cost = str(face.get("mana_cost", ""))
        for symbol in MANA_SYMBOL_RE.findall(mana_cost):
            parts = symbol.upper().split("/")
            for color in COLORS:
                if color in parts:
                    counts[color] += 1

    return counts


def calculate_card_color_distribution(
    deck: list[str],
    cards: dict[str, dict],
) -> dict[str, float]:
    """Calculate deck color demand from actual colored casting pips.

    Every colored pip contributes one demand unit. A nonland spell with no
    colored pips contributes one Colorless unit. Lands are excluded.
    """
    quantities = Counter(deck)
    totals = {color: 0.0 for color in (*COLORS, "C")}

    for name, quantity in quantities.items():
        card = cards.get(name)
        if not card:
            continue

        if is_land_card(card) and not _nonland_faces(card):
            continue

        pips = colored_pip_counts(card)
        colored_total = sum(pips.values())

        if colored_total == 0:
            totals["C"] += quantity
            continue

        for color in COLORS:
            totals[color] += pips[color] * quantity

    total_units = sum(totals.values())
    if total_units <= 0:
        return {color: 0.0 for color in (*COLORS, "C")}

    raw = {
        color: totals[color] * 100.0 / total_units
        for color in (*COLORS, "C")
    }
    rounded = {color: round(value, 1) for color, value in raw.items()}
    residual = round(100.0 - sum(rounded.values()), 1)
    if residual:
        largest = max(raw, key=raw.get)
        rounded[largest] = round(rounded[largest] + residual, 1)

    return rounded


def is_land_card(card: dict) -> bool:
    if "Land" in str(card.get("type_line", "")):
        return True
    return any(
        "Land" in str(face.get("type_line", ""))
        for face in card.get("card_faces") or []
    )


def is_mdfc_land(card: dict) -> bool:
    return (
        card.get("layout") == "modal_dfc"
        and any(
            "Land" in str(face.get("type_line", ""))
            for face in card.get("card_faces") or []
        )
    )


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


def commander_illegal_cards(deck: list[str], cards: dict[str, dict]) -> list[str]:
    """Return cards Scryfall does not mark legal in Commander."""
    illegal: list[str] = []
    for name in dict.fromkeys(deck):
        card = cards.get(name)
        if not card:
            continue
        if (card.get("legalities") or {}).get("commander") != "legal":
            illegal.append(name)
    return illegal


def deck_summary(deck: list[str], cards: dict[str, dict]) -> dict:
    """Build useful deck statistics from already-fetched Scryfall objects."""
    quantities = Counter(deck)
    type_counts: Counter[str] = Counter()
    curve: Counter[int] = Counter()
    total_mv = 0.0
    nonland_count = 0
    land_count = 0
    mdfc_land_count = 0

    for name, quantity in quantities.items():
        card = cards.get(name)
        if not card:
            continue

        if is_land_card(card):
            land_count += quantity
            if is_mdfc_land(card):
                mdfc_land_count += quantity

        nonland_faces = _nonland_faces(card)
        if not nonland_faces:
            type_counts["Land"] += quantity
            continue

        # Use the main/nonland face type for broad deck composition.
        type_line = str(nonland_faces[0].get("type_line", card.get("type_line", "")))
        if "Creature" in type_line:
            bucket = "Creature"
        elif "Artifact" in type_line:
            bucket = "Artifact"
        elif "Enchantment" in type_line:
            bucket = "Enchantment"
        elif "Planeswalker" in type_line:
            bucket = "Planeswalker"
        elif "Instant" in type_line:
            bucket = "Instant"
        elif "Sorcery" in type_line:
            bucket = "Sorcery"
        elif "Battle" in type_line:
            bucket = "Battle"
        else:
            bucket = "Other"
        type_counts[bucket] += quantity

        mv = float(card.get("cmc") or 0.0)
        total_mv += mv * quantity
        nonland_count += quantity
        curve[min(int(mv), 7)] += quantity

    average_mv = total_mv / nonland_count if nonland_count else 0.0
    color_identity = sorted(
        {
            color
            for card in cards.values()
            for color in (card.get("color_identity") or [])
            if color in COLORS
        },
        key="WUBRG".index,
    )

    return {
        "deck_size": len(deck),
        "land_count": land_count,
        "mdfc_land_count": mdfc_land_count,
        "nonland_count": nonland_count,
        "average_mana_value": average_mv,
        "color_identity": "".join(color_identity) or "C",
        "type_counts": dict(type_counts),
        "curve": {str(mv): curve.get(mv, 0) for mv in range(0, 7)}
        | {"7+": curve.get(7, 0)},
        "commander_illegal": commander_illegal_cards(deck, cards),
    }
