from __future__ import annotations

from io import StringIO
from itertools import combinations
from math import comb
from pathlib import Path

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode

from mana_hand_simulator.commander_simulator import commander_mana_cost, simulate_commander_cast_turns
from mana_hand_simulator.deck_loader import parse_deck_text
from mana_hand_simulator.models import CardConfig, HandTier
from mana_hand_simulator.scryfall import (
    calculate_card_color_distribution,
    card_image_url,
    deck_summary,
    fetch_cards,
    is_land_card,
    is_mdfc_land,
    produced_mana,
)
from mana_hand_simulator.simulator import run_simulation_from_data


ROOT = Path(__file__).resolve().parent
DEFAULT_DECK = ROOT / "data" / "decklist.txt"
DEFAULT_CONFIG = ROOT / "data" / "card_config.csv"
DEFAULT_COMMANDER = "Avacyn, Angel of Horror"
COLORS = ("W", "U", "B", "R", "G", "C")
COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
    "C": "Colorless",
}
MANA_SYMBOLS = {
    color: f"https://svgs.scryfall.io/card-symbols/{color}.svg"
    for color in COLORS
}
PRODUCES_OPTIONS = [""] + [
    "".join(combo)
    for size in range(1, 7)
    for combo in combinations("WUBRGC", size)
]

CATEGORY_OPTIONS = [
    "Other / Unscored",
    "Land",
    "MDFC Land",
    "Mana Rock",
    "Ramp / Accelerator",
    "Cost Discount",
    "Big Mana",
    "Conditional Mana",
    "Premium Acceleration",
]
CATEGORY_ALIASES = {
    "unscored": "Other / Unscored",
    "land": "Land",
    "mdfc_land": "MDFC Land",
    "mana_rock": "Mana Rock",
    "ramp": "Ramp / Accelerator",
    "acceleration": "Ramp / Accelerator",
    "accelerator": "Ramp / Accelerator",
    "discount": "Cost Discount",
    "big_mana": "Big Mana",
    "conditional_mana": "Conditional Mana",
    "premium_acceleration": "Premium Acceleration",
}


SCRYFALL_CACHE_VERSION = "mdfc-v3"

@st.cache_data(ttl=86_400, show_spinner=False)
def cached_scryfall_lookup(
    card_names: tuple[str, ...],
    cache_version: str,
):
    # cache_version intentionally participates in the key so parser/matching
    # fixes do not leave users stuck with stale 24-hour Scryfall data.
    return fetch_cards(list(card_names))


def load_default_deck() -> str:
    return DEFAULT_DECK.read_text(encoding="utf-8")


def load_default_config() -> pd.DataFrame:
    frame = pd.read_csv(DEFAULT_CONFIG)
    if "produces" not in frame.columns:
        frame["produces"] = ""
    return frame


def ensure_config_shape(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    if "produces" not in frame.columns:
        frame["produces"] = ""
    if "type" not in frame.columns:
        frame["type"] = "Other / Unscored"
    frame["produces"] = frame["produces"].fillna("").astype(str)
    frame["type"] = (
        frame["type"]
        .fillna("Other / Unscored")
        .astype(str)
        .map(lambda value: CATEGORY_ALIASES.get(value.strip(), value.strip()))
    )
    frame.loc[~frame["type"].isin(CATEGORY_OPTIONS), "type"] = "Other / Unscored"
    return frame


def dataframe_to_config(frame: pd.DataFrame) -> dict[str, CardConfig]:
    config: dict[str, CardConfig] = {}

    required = {"card_name", "weight", "type", "is_land", "produces"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "Card config is missing column(s): " + ", ".join(sorted(missing))
        )

    for _, row in frame.iterrows():
        name = str(row["card_name"]).strip()
        if not name or name.lower() == "nan":
            continue

        is_land_raw = row["is_land"]
        if isinstance(is_land_raw, bool):
            is_land = is_land_raw
        else:
            is_land = str(is_land_raw).strip().casefold() in {
                "1",
                "true",
                "yes",
                "y",
            }

        produces = str(row["produces"]).strip().upper()
        if produces.lower() == "nan":
            produces = ""

        config[name] = CardConfig(
            name=name,
            weight=float(row["weight"]),
            category=str(row["type"]).strip(),
            is_land=is_land,
            produces=tuple(color for color in "WUBRGC" if color in produces),
        )

    return config


def percentages_row(label: str, result) -> dict[str, float | str]:
    pct = result.percentages()
    return {
        "Stage": label,
        "A": pct[HandTier.A],
        "B": pct[HandTier.B],
        "C": pct[HandTier.C],
        "D": pct[HandTier.D],
        "A/B Keep": pct[HandTier.A] + pct[HandTier.B],
        "Avg color coverage": result.average_color_coverage * 100,
    }


def enrich_config_from_scryfall(
    frame: pd.DataFrame,
    deck: list[str],
    cards: dict[str, dict],
) -> pd.DataFrame:
    frame = ensure_config_shape(frame)
    by_name = {
        str(row["card_name"]).strip(): index
        for index, row in frame.iterrows()
        if str(row["card_name"]).strip()
    }

    rows_to_add: list[dict] = []

    for name in dict.fromkeys(deck):
        card = cards.get(name)
        if not card:
            continue

        is_land = is_land_card(card)
        is_mdfc = is_mdfc_land(card)
        produces = produced_mana(card)

        if name in by_name:
            index = by_name[name]
            if is_land:
                frame.at[index, "is_land"] = True
            if is_mdfc and str(frame.at[index, "type"]).strip() in {"", "Other / Unscored"}:
                frame.at[index, "type"] = "MDFC Land"
            elif is_land and str(frame.at[index, "type"]).strip() in {"", "Other / Unscored"}:
                frame.at[index, "type"] = "Land"
            if produces:
                frame.at[index, "produces"] = produces
        else:
            rows_to_add.append(
                {
                    "card_name": name,
                    "weight": 0.0,
                    "type": "MDFC Land" if is_mdfc else ("Land" if is_land else "Other / Unscored"),
                    "is_land": is_land,
                    "produces": produces,
                }
            )

    if rows_to_add:
        frame = pd.concat([frame, pd.DataFrame(rows_to_add)], ignore_index=True)

    return frame



def source_count_by_color(
    deck: list[str],
    card_config: dict[str, CardConfig],
) -> dict[str, int]:
    return {
        color: sum(
            1
            for card in deck
            if card in card_config and color in card_config[card].produces
        )
        for color in ("W", "U", "B", "R", "G")
    }


def opening_access_probability(deck_size: int, sources: int, hand_size: int = 7) -> float:
    if sources <= 0:
        return 0.0
    if sources >= deck_size:
        return 100.0
    misses = comb(deck_size - sources, hand_size) / comb(deck_size, hand_size)
    return (1.0 - misses) * 100.0


def recommended_sources_for_demand(
    deck_size: int,
    demand_share: float,
) -> tuple[int, float]:
    # Stronger demand deserves a higher target chance of seeing at least one
    # source in the opening seven. Splash colors use a softer target.
    if demand_share >= 30:
        target = 90.0
    elif demand_share >= 15:
        target = 85.0
    elif demand_share >= 5:
        target = 75.0
    else:
        target = 65.0

    for sources in range(deck_size + 1):
        if opening_access_probability(deck_size, sources) >= target:
            return sources, target
    return deck_size, target


def build_diagnostics(
    deck: list[str],
    card_config: dict[str, CardConfig],
    color_demand: dict[str, float],
    result,
) -> list[tuple[str, str]]:
    notes: list[tuple[str, str]] = []
    final_pct = result.final.percentages()
    final_ab = final_pct[HandTier.A] + final_pct[HandTier.B]
    opening = result.opening

    if final_ab >= 70:
        notes.append(("good", f"Opening consistency is strong: {final_ab:.1f}% of final hands are A/B."))
    elif final_ab >= 60:
        notes.append(("good", f"Opening consistency is healthy: {final_ab:.1f}% of final hands are A/B."))
    elif final_ab >= 50:
        notes.append(("warn", f"Opening consistency is a little shaky: {final_ab:.1f}% of final hands are A/B."))
    else:
        notes.append(("bad", f"Opening consistency is low: only {final_ab:.1f}% of final hands are A/B."))

    if opening.low_land_rate >= 18:
        notes.append((
            "bad",
            f"{opening.low_land_rate:.1f}% of opening hands have fewer than 2 lands. "
            "Consider adding land-capable cards or replacing narrow nonlands."
        ))
    elif opening.high_land_rate >= 18:
        notes.append((
            "warn",
            f"{opening.high_land_rate:.1f}% of opening hands have 5+ lands. "
            "You may be slightly land-heavy for this acceleration package."
        ))
    elif final_ab < 60 and opening.average_score < 2.0:
        notes.append((
            "warn",
            "Land count is not the main problem; early acceleration is light. "
            "Consider more Mana Rocks, Ramp / Accelerators, Cost Discounts, or Premium Acceleration."
        ))

    demanded = {
        color: float(color_demand.get(color, 0.0))
        for color in ("W", "U", "B", "R", "G")
        if float(color_demand.get(color, 0.0)) > 0
    }
    access_rates = opening.color_access_rates or {}
    source_counts = source_count_by_color(deck, card_config)

    if len(demanded) > 1:
        full = opening.full_color_access_rate
        if full < 50:
            notes.append((
                "bad",
                f"Only {full:.1f}% of opening hands contain a source for every deck color. "
                "Color fixing is a major bottleneck."
            ))
        elif full < 70:
            notes.append((
                "warn",
                f"{full:.1f}% of opening hands contain all deck colors. "
                "Your mana works, but fixing could be more consistent."
            ))

    for color, demand in sorted(demanded.items(), key=lambda item: item[1], reverse=True):
        access = float(access_rates.get(color, 0.0))
        current_sources = source_counts.get(color, 0)
        target_sources, target_access = recommended_sources_for_demand(len(deck), demand)
        shortfall = max(0, target_sources - current_sources)

        if access + 0.01 < target_access and shortfall > 0:
            name = COLOR_NAMES[color]
            notes.append((
                "bad" if access < 60 else "warn",
                f"{name}: {demand:.1f}% of colored demand, but only {access:.1f}% of opening hands "
                f"contain a {color} source. You currently have {current_sources} source(s). "
                f"Consider about {shortfall} more source(s) that can produce {color}, ideally by "
                "swapping colorless or off-color sources rather than only increasing deck size."
            ))

    if len(notes) == 1 and final_ab >= 60:
        notes.append(("good", "No obvious mana-base bottleneck was detected from these opening-hand results."))

    return notes


st.set_page_config(
    page_title="Mana Hand Simulator",
    page_icon="🃏",
    layout="wide",
)

for color in COLORS:
    st.session_state.setdefault(f"color_{color}", 100.0 if color == "B" else 0.0)
st.session_state.setdefault("config_editor_version", 0)
st.session_state.setdefault("commander_name", DEFAULT_COMMANDER)

st.title("Mana Hand Simulator")
st.caption(
    "Monte Carlo opening-hand, mulligan, and color-access analysis for MTG Commander decks."
)

with st.expander("Quick guide — what to set and what the results mean", expanded=True):
    st.markdown(
        """
**1. Paste your 99-card deck** and set your **Commander** separately. Click **Detect with Scryfall** to fill card data automatically.

**2. Review Card Configuration**
- **Category** = what kind of mana/setup card it is.
- **Weight** = how valuable it is in an opening hand: **0** not acceleration, **1** small boost, **1.5–2** strong, **3** premium/explosive.
- **Land** and **Produces** are usually filled automatically; adjust only if needed.

Use these categories: **Mana Rock**, **Ramp / Accelerator**, **Cost Discount**, **Big Mana**, **Conditional Mana**, **Premium Acceleration**, **Land/MDFC Land**, or **Other / Unscored**.

**3. Read the result:** **A = explosive**, **B = strong keep**, **C = marginal/keepable**, **D = mulligan**.  
**A/B Keep** is the main number to watch; **Color Coverage** shows how often your opening mana can support your deck's color needs. The **Commander** section estimates the chance your commander is castable by Turns 1–10.
"""
    )

deck_col, settings_col = st.columns([2, 1])

with deck_col:
    st.subheader("1. Decklist")
    uploaded_deck = st.file_uploader(
        "Upload decklist (.txt)",
        type=["txt"],
        help="Paste a plain list or a Moxfield export. Printing info, foil markers, and #tags are ignored automatically.",
    )

    if uploaded_deck is not None:
        deck_default = uploaded_deck.getvalue().decode("utf-8")
    else:
        deck_default = load_default_deck()

    deck_text = st.text_area(
        "Deck",
        value=deck_default,
        height=360,
        help="The default is the Avacyn example used to develop the simulator.",
    )

with settings_col:
    st.subheader("2. Simulation")
    iterations = st.select_slider(
        "Iterations",
        options=[10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000],
        value=100_000,
    )
    st.caption("More iterations = steadier percentages, but a slower run.")

    with st.expander("Advanced: repeatable results"):
        use_seed = st.checkbox(
            "Use the same random sequence every run",
            value=False,
            help="Useful for testing changes: the same seed produces the same simulated hands.",
        )
        seed = st.number_input(
            "Seed",
            min_value=0,
            value=42,
            step=1,
            disabled=not use_seed,
            help="42 is only an arbitrary example seed. Any integer works.",
        )
        st.caption(
            "Seed = the starting point for the simulator's random number generator. "
            "Using the same seed makes the app draw the same simulated hands again, "
            "which is useful for fair before/after comparisons. Leave it off for normal use."
        )

try:
    parsed_deck = parse_deck_text(deck_text)
except Exception:
    parsed_deck = []

with st.container(border=True):
    st.subheader("3. Commander")
    st.caption(
        "The commander starts in the command zone and is not shuffled into the 99-card library."
    )

    commander_col, load_col = st.columns([4, 1])
    with commander_col:
        commander_name = st.text_input(
            "Commander name",
            key="commander_name",
            help="Enter the card name exactly or close to it; Scryfall will resolve it.",
        )
    with load_col:
        st.write("")
        st.write("")
        load_commander = st.button(
            "Load Commander",
            type="secondary",
            width="stretch",
            disabled=not commander_name.strip(),
        )

    if load_commander:
        try:
            with st.spinner("Loading commander from Scryfall..."):
                commander_cards, commander_missing = cached_scryfall_lookup(
                    (commander_name.strip(),),
                    SCRYFALL_CACHE_VERSION,
                )
            commander_card = commander_cards.get(commander_name.strip())
            if not commander_card:
                raise ValueError("Commander could not be matched on Scryfall.")
            st.session_state["commander_card"] = commander_card
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    commander_card = st.session_state.get("commander_card")
    if commander_card:
        loaded_name = str(commander_card.get("name", commander_name))
        mana_cost = commander_mana_cost(commander_card) or "—"
        identity = [
            color for color in ("W", "U", "B", "R", "G")
            if color in (commander_card.get("color_identity") or [])
        ]

        info1, info2, info3 = st.columns(3)
        info1.metric("Commander", loaded_name)
        info2.metric("Mana cost", mana_cost)

        if identity:
            symbols = " ".join(
                f'<img src="{MANA_SYMBOLS[color]}" width="24" title="{COLOR_NAMES[color]}">'
                for color in identity
            )
            info3.markdown(
                f"<div style='padding-top:8px'><strong>Color identity</strong><br>{symbols}</div>",
                unsafe_allow_html=True,
            )
        else:
            info3.metric("Color identity", "Colorless")

        st.caption(
            "Turn percentages are calculated when you run the simulation. "
            "They mean: chance the commander is castable by that turn."
        )

with st.container(border=True):
    st.subheader("4. Deck Color Distribution")
    st.caption(
        "Set these manually, or let Scryfall calculate them from the nonland cards in your deck."
    )

    auto_col, note_col = st.columns([1, 3])
    with auto_col:
        auto_detect = st.button(
            "Detect with Scryfall",
            type="secondary",
            disabled=not parsed_deck,
            width="stretch",
        )
    with note_col:
        st.caption(
            "Auto-detect now uses actual colored mana pips from casting costs; lands are excluded from demand."
        )

    if auto_detect:
        try:
            with st.spinner("Looking up cards on Scryfall..."):
                lookup_names = tuple(
                    dict.fromkeys([
                        *parsed_deck,
                        *([commander_name.strip()] if commander_name.strip() else []),
                    ])
                )
                scryfall_cards, missing = cached_scryfall_lookup(
                    lookup_names,
                    SCRYFALL_CACHE_VERSION,
                )
                distribution = calculate_card_color_distribution(
                    parsed_deck, scryfall_cards
                )

            for color in COLORS:
                st.session_state[f"color_{color}"] = float(distribution[color])

            base_frame = st.session_state.get("config_frame", load_default_config())
            st.session_state["config_frame"] = enrich_config_from_scryfall(
                base_frame, parsed_deck, scryfall_cards
            )
            st.session_state["scryfall_cards"] = scryfall_cards
            if commander_name.strip() and commander_name.strip() in scryfall_cards:
                st.session_state["commander_card"] = scryfall_cards[commander_name.strip()]
            st.session_state["deck_summary"] = deck_summary(parsed_deck, scryfall_cards)
            st.session_state["config_editor_version"] += 1

            if missing:
                st.session_state["scryfall_missing"] = missing
            else:
                st.session_state.pop("scryfall_missing", None)

            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    color_columns = st.columns(6)
    for column, color in zip(color_columns, COLORS):
        with column:
            st.markdown(
                f'<div style="text-align:center"><img src="{MANA_SYMBOLS[color]}" '
                f'width="30"><br><strong>{COLOR_NAMES[color]}</strong></div>',
                unsafe_allow_html=True,
            )
            st.number_input(
                f"{COLOR_NAMES[color]} %",
                min_value=0.0,
                max_value=100.0,
                step=1.0,
                key=f"color_{color}",
                label_visibility="collapsed",
            )

    color_total = sum(float(st.session_state[f"color_{color}"]) for color in COLORS)
    if abs(color_total - 100.0) <= 0.11:
        st.success(f"Total: {color_total:.1f}%")
    else:
        st.warning(f"Total: {color_total:.1f}% — adjust the values to 100%.")

    if st.session_state.get("scryfall_missing"):
        missing = st.session_state["scryfall_missing"]
        st.warning(
            "Scryfall could not match: " + ", ".join(missing[:10])
            + ("…" if len(missing) > 10 else "")
        )

    summary = st.session_state.get("deck_summary")
    if summary:
        st.markdown("#### Deck Analysis")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Deck size", summary["deck_size"])
        m2.metric("Land-capable cards", summary["land_count"])
        m3.metric("Average mana value", f'{summary["average_mana_value"]:.2f}')
        m4.metric("Color identity", summary["color_identity"])

        if summary["mdfc_land_count"]:
            st.caption(
                f'Includes {summary["mdfc_land_count"]} modal double-faced land card(s).'
            )

        analysis_left, analysis_right = st.columns(2)

        with analysis_left:
            st.markdown("**Mana Curve**")
            curve_frame = pd.DataFrame(
                {
                    "Mana value": list(summary["curve"].keys()),
                    "Cards": list(summary["curve"].values()),
                }
            ).set_index("Mana value")
            st.bar_chart(curve_frame)

        with analysis_right:
            st.markdown("**Card Types**")
            type_frame = pd.DataFrame(
                {
                    "Type": list(summary["type_counts"].keys()),
                    "Cards": list(summary["type_counts"].values()),
                }
            ).set_index("Type")
            st.bar_chart(type_frame)

        illegal = summary["commander_illegal"]
        if illegal:
            st.warning(
                "Not currently marked Commander-legal by Scryfall: "
                + ", ".join(illegal)
            )
        else:
            st.success("All matched cards are marked Commander-legal by Scryfall.")

st.subheader("5. Card Configuration")
uploaded_config = st.file_uploader(
    "Upload card config (.csv)",
    type=["csv"],
    help="Columns: card_name, weight, type, is_land, produces",
)

if uploaded_config is not None:
    config_frame = ensure_config_shape(
        pd.read_csv(StringIO(uploaded_config.getvalue().decode("utf-8")))
    )
    st.session_state["config_frame"] = config_frame
elif "config_frame" not in st.session_state:
    st.session_state["config_frame"] = load_default_config()

config_frame = ensure_config_shape(st.session_state["config_frame"])

scryfall_cards = st.session_state.get("scryfall_cards", {})
grid_frame = config_frame.copy()
grid_frame["image_url"] = grid_frame["card_name"].map(
    lambda name: card_image_url(scryfall_cards.get(str(name), {}))
    if str(name) in scryfall_cards
    else ""
)

card_renderer = JsCode(
    """
class CardNameRenderer {
  init(params) {
    this.params = params;
    this.eGui = document.createElement('span');
    this.eGui.textContent = params.value || '';
    this.eGui.style.cursor = params.data && params.data.image_url ? 'help' : 'default';

    this.showPreview = (event) => {
      const url = params.data && params.data.image_url;
      if (!url || this.preview) return;

      const preview = document.createElement('div');
      preview.style.position = 'fixed';
      preview.style.zIndex = '999999';
      preview.style.pointerEvents = 'none';
      preview.style.background = '#111827';
      preview.style.border = '1px solid #4b5563';
      preview.style.borderRadius = '10px';
      preview.style.padding = '7px';
      preview.style.boxShadow = '0 12px 32px rgba(0,0,0,.55)';

      const img = document.createElement('img');
      img.src = url;
      img.alt = params.value || 'Card image';
      img.style.width = '240px';
      img.style.display = 'block';
      img.style.borderRadius = '8px';

      preview.appendChild(img);
      document.body.appendChild(preview);
      this.preview = preview;
      this.movePreview(event);
    };

    this.movePreview = (event) => {
      if (!this.preview) return;
      const margin = 14;
      const width = 260;
      const height = 350;

      let left = event.clientX + margin;
      let top = event.clientY + margin;

      if (left + width > window.innerWidth) {
        left = event.clientX - width - margin;
      }
      if (top + height > window.innerHeight) {
        top = Math.max(margin, window.innerHeight - height - margin);
      }

      this.preview.style.left = left + 'px';
      this.preview.style.top = top + 'px';
    };

    this.hidePreview = () => {
      if (this.preview) {
        this.preview.remove();
        this.preview = null;
      }
    };

    this.eGui.addEventListener('mouseenter', this.showPreview);
    this.eGui.addEventListener('mousemove', this.movePreview);
    this.eGui.addEventListener('mouseleave', this.hidePreview);
  }

  getGui() {
    return this.eGui;
  }

  refresh(params) {
    this.eGui.textContent = params.value || '';
    return true;
  }

  destroy() {
    this.hidePreview();
  }
}
"""
)
mana_renderer = JsCode(
    """
class ManaSymbolRenderer {
  init(params) {
    this.eGui = document.createElement('div');
    this.eGui.style.display = 'flex';
    this.eGui.style.alignItems = 'center';
    this.eGui.style.gap = '4px';
    this.eGui.style.height = '100%';

    const value = params.value || '';
    Array.from(value).forEach(symbol => {
      const img = document.createElement('img');
      img.src = 'https://svgs.scryfall.io/card-symbols/' + symbol + '.svg';
      img.alt = symbol;
      img.title = symbol;
      img.style.width = '22px';
      img.style.height = '22px';
      img.style.display = 'block';
      this.eGui.appendChild(img);
    });
  }

  getGui() {
    return this.eGui;
  }

  refresh(params) {
    return false;
  }
}
"""
)

mana_editor = JsCode(
    """
class ManaSymbolEditor {
  init(params) {
    this.params = params;
    this.value = params.value || '';
    this.eGui = document.createElement('div');
    this.eGui.style.background = '#111827';
    this.eGui.style.border = '1px solid #4b5563';
    this.eGui.style.borderRadius = '8px';
    this.eGui.style.padding = '5px';
    this.eGui.style.maxHeight = '280px';
    this.eGui.style.overflowY = 'auto';
    this.eGui.style.minWidth = '170px';
    this.eGui.style.boxShadow = '0 10px 28px rgba(0,0,0,.4)';

    const values = (params.values || []).slice();

    values.forEach(value => {
      const option = document.createElement('div');
      option.style.display = 'flex';
      option.style.alignItems = 'center';
      option.style.gap = '4px';
      option.style.padding = '6px 8px';
      option.style.cursor = 'pointer';
      option.style.borderRadius = '6px';

      option.onmouseenter = () => option.style.background = '#374151';
      option.onmouseleave = () => option.style.background = 'transparent';

      if (!value) {
        const label = document.createElement('span');
        label.textContent = 'None';
        label.style.color = '#d1d5db';
        option.appendChild(label);
      } else {
        Array.from(value).forEach(symbol => {
          const img = document.createElement('img');
          img.src = 'https://svgs.scryfall.io/card-symbols/' + symbol + '.svg';
          img.alt = symbol;
          img.title = symbol;
          img.style.width = '22px';
          img.style.height = '22px';
          option.appendChild(img);
        });
      }

      option.addEventListener('mousedown', event => {
        event.preventDefault();
        this.value = value;
        if (this.params.stopEditing) {
          this.params.stopEditing();
        } else if (this.params.api) {
          this.params.api.stopEditing();
        }
      });

      this.eGui.appendChild(option);
    });
  }

  getGui() {
    return this.eGui;
  }

  afterGuiAttached() {}

  getValue() {
    return this.value;
  }

  isPopup() {
    return true;
  }
}
"""
)

grid_options = {
    "defaultColDef": {
        "resizable": True,
        "sortable": True,
        "filter": True,
        "editable": True,
    },
    "columnDefs": [
        {
            "headerName": "Card",
            "field": "card_name",
            "minWidth": 260,
            "cellRenderer": card_renderer,
        },
        {
            "headerName": "Weight",
            "field": "weight",
            "width": 110,
            "type": "numericColumn",
            "cellEditor": "agNumberCellEditor",
            "cellEditorParams": {"min": 0, "step": 0.5},
        },
        {
            "headerName": "Category",
            "field": "type",
            "minWidth": 190,
            "cellEditor": "agSelectCellEditor",
            "cellEditorParams": {"values": CATEGORY_OPTIONS},
        },
        {
            "headerName": "Land",
            "field": "is_land",
            "width": 95,
            "cellRenderer": "agCheckboxCellRenderer",
            "cellEditor": "agCheckboxCellEditor",
        },
        {
            "headerName": "Produces",
            "field": "produces",
            "minWidth": 180,
            "cellRenderer": mana_renderer,
            "cellEditor": mana_editor,
            "cellEditorParams": {"values": PRODUCES_OPTIONS},
        },
        {
            "field": "image_url",
            "hide": True,
            "editable": False,
        },
    ],
    "tooltipShowDelay": 250,
    "tooltipHideDelay": 5000,
    "stopEditingWhenCellsLoseFocus": True,
}

grid_response = AgGrid(
    grid_frame,
    gridOptions=grid_options,
    height=520,
    theme="streamlit",
    data_return_mode=DataReturnMode.AS_INPUT,
    update_mode=GridUpdateMode.VALUE_CHANGED,
    allow_unsafe_jscode=True,
    fit_columns_on_grid_load=True,
)

edited_config = pd.DataFrame(grid_response["data"]).drop(
    columns=["image_url"], errors="ignore"
)
edited_config = ensure_config_shape(edited_config)
st.session_state["config_frame"] = edited_config

st.caption(
    "Tip: most cards should stay Other / Unscored with weight 0. Only give weight to cards that genuinely improve an opening hand's mana/setup."
)

if st.button("Run simulation", type="primary", width="stretch"):
    try:
        deck = parse_deck_text(deck_text)
        card_config = dataframe_to_config(edited_config)

        if abs(color_total - 100.0) > 0.11:
            raise ValueError("Deck Color Distribution must total 100%.")

        color_demand = {
            color: float(st.session_state[f"color_{color}"])
            for color in COLORS
        }

        unconfigured = sorted(set(deck) - set(card_config))
        if unconfigured:
            st.warning(
                f"{len(unconfigured)} card name(s) are not in the config. "
                "They will count as nonland, weight-0 cards with no mana production."
            )

        with st.spinner(f"Simulating {iterations:,} mulligan sequences..."):
            result = run_simulation_from_data(
                deck,
                card_config,
                iterations=iterations,
                seed=int(seed) if use_seed else None,
                color_demand=color_demand,
            )

        rows = [
            percentages_row("Opening 7", result.opening),
            percentages_row("Free mulligan 7", result.free_mulligan),
            percentages_row("Final hand", result.final),
        ]
        results = pd.DataFrame(rows)

        st.subheader("Results")

        metric1, metric2, metric3, metric4 = st.columns(4)
        opening_keep = results.loc[0, "A/B Keep"]
        final_keep = results.loc[2, "A/B Keep"]

        metric1.metric("Opening A/B", f"{opening_keep:.1f}%")
        metric2.metric(
            "A/B seen by free mulligan",
            f"{result.seen_ab_after_free_mulligan:.1f}%",
        )
        metric3.metric("Final A/B", f"{final_keep:.1f}%")
        metric4.metric(
            "Opening color coverage",
            f"{result.opening.average_color_coverage * 100:.1f}%",
        )

        formatted = results.copy()
        for column in ["A", "B", "C", "D", "A/B Keep", "Avg color coverage"]:
            formatted[column] = formatted[column].map(lambda value: f"{value:.2f}%")
        st.dataframe(formatted, hide_index=True, width="stretch")

        chart_data = results.set_index("Stage")[["A", "B", "C", "D"]]
        st.bar_chart(chart_data)

        st.subheader("Commander Cast Probability")
        active_commander = st.session_state.get("commander_card")
        if not active_commander and commander_name.strip():
            commander_cards, _ = cached_scryfall_lookup(
                (commander_name.strip(),),
                SCRYFALL_CACHE_VERSION,
            )
            active_commander = commander_cards.get(commander_name.strip())
            if active_commander:
                st.session_state["commander_card"] = active_commander

        if active_commander:
            commander_iterations = min(int(iterations), 50_000)
            with st.spinner(
                f"Estimating commander cast turns with {commander_iterations:,} samples..."
            ):
                commander_result = simulate_commander_cast_turns(
                    deck,
                    card_config,
                    active_commander,
                    iterations=commander_iterations,
                    seed=int(seed) if use_seed else None,
                    max_turn=10,
                )

            commander_rows = [
                {
                    "Turn": turn,
                    "First cast on this turn": f"{commander_result.first_cast_turn[turn]:.1f}%",
                    "Castable by this turn": f"{commander_result.cast_by_turn[turn]:.1f}%",
                }
                for turn in range(1, 11)
            ]
            st.dataframe(
                pd.DataFrame(commander_rows),
                hide_index=True,
                width="stretch",
            )

            curve = pd.DataFrame(
                {
                    "Turn": list(range(1, 11)),
                    "Castable by turn (%)": [
                        commander_result.cast_by_turn[turn]
                        for turn in range(1, 11)
                    ],
                }
            ).set_index("Turn")
            st.line_chart(curve)

            st.caption(
                "This is an estimate using your land flags, mana colors, categories and weights. "
                "It models one land drop per turn and category-based acceleration/discount timing; "
                "unusual cards such as Coffers-style scaling or variable mana can differ in real games."
            )
        else:
            st.info("Load a commander above to calculate Turns 1–10.")

        st.subheader("Deck Diagnosis")
        st.caption(
            "These are deterministic recommendations from the simulation — not hard deck-building rules."
        )
        diagnostics = build_diagnostics(deck, card_config, color_demand, result)
        for severity, message in diagnostics:
            if severity == "good":
                st.success(message)
            elif severity == "bad":
                st.error(message)
            else:
                st.warning(message)

        if result.opening.color_access_rates:
            st.markdown("**Opening color access**")
            color_rows = []
            source_counts = source_count_by_color(deck, card_config)
            for color in ("W", "U", "B", "R", "G"):
                demand = float(color_demand.get(color, 0.0))
                if demand <= 0:
                    continue
                target_sources, target_access = recommended_sources_for_demand(len(deck), demand)
                color_rows.append(
                    {
                        "Color": COLOR_NAMES[color],
                        "Demand": f"{demand:.1f}%",
                        "Sources": source_counts[color],
                        "Opening access": f"{result.opening.color_access_rates.get(color, 0.0):.1f}%",
                        "Suggested target": f"{target_sources} sources / ~{target_access:.0f}% access",
                    }
                )
            st.dataframe(pd.DataFrame(color_rows), hide_index=True, width="stretch")
            if len(color_rows) > 1:
                st.caption(
                    f"All required colors appear together in {result.opening.full_color_access_rate:.1f}% of opening hands."
                )

        with st.expander("Simulation details"):
            st.write(f"Deck size: **{len(deck)}** cards")
            st.write(f"Configured card names: **{len(card_config)}**")
            st.write(f"Iterations: **{iterations:,}**")
            st.write(
                "Seed: **"
                + (str(int(seed)) if use_seed else "random")
                + "**"
            )
            st.write(
                "Color distribution: **"
                + ", ".join(
                    f"{color} {color_demand[color]:.1f}%"
                    for color in COLORS
                    if color_demand[color] > 0
                )
                + "**"
            )

    except Exception as exc:
        st.error(str(exc))
