from __future__ import annotations

from io import StringIO
from itertools import combinations
from pathlib import Path

import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, DataReturnMode, GridUpdateMode, JsCode

from mana_hand_simulator.deck_loader import parse_deck_text
from mana_hand_simulator.models import CardConfig, HandTier
from mana_hand_simulator.scryfall import (
    calculate_card_color_distribution,
    card_image_url,
    fetch_cards,
    produced_mana,
)
from mana_hand_simulator.simulator import run_simulation_from_data


ROOT = Path(__file__).resolve().parent
DEFAULT_DECK = ROOT / "data" / "decklist.txt"
DEFAULT_CONFIG = ROOT / "data" / "card_config.csv"
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


@st.cache_data(ttl=86_400, show_spinner=False)
def cached_scryfall_lookup(card_names: tuple[str, ...]):
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
    frame["produces"] = frame["produces"].fillna("").astype(str)
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

        type_line = str(card.get("type_line", ""))
        is_land = "Land" in type_line
        produces = produced_mana(card)

        if name in by_name:
            index = by_name[name]
            if is_land:
                frame.at[index, "is_land"] = True
            if produces:
                frame.at[index, "produces"] = produces
        else:
            rows_to_add.append(
                {
                    "card_name": name,
                    "weight": 0.0,
                    "type": "land" if is_land else "unscored",
                    "is_land": is_land,
                    "produces": produces,
                }
            )

    if rows_to_add:
        frame = pd.concat([frame, pd.DataFrame(rows_to_add)], ignore_index=True)

    return frame


st.set_page_config(
    page_title="Mana Hand Simulator",
    page_icon="🃏",
    layout="wide",
)

for color in COLORS:
    st.session_state.setdefault(f"color_{color}", 100.0 if color == "B" else 0.0)
st.session_state.setdefault("config_editor_version", 0)

st.title("Mana Hand Simulator")
st.caption(
    "Monte Carlo opening-hand, mulligan, and color-access analysis for MTG Commander decks."
)

with st.expander("How scoring works", expanded=False):
    st.markdown(
        """
Each hand is graded from **land count**, **acceleration score**, and — when a
color distribution is supplied — **color coverage**.

| Tier | Base criteria |
|---|---|
| **A — Explosive** | 2–3 lands and score ≥ 5 |
| **B — Strong** | 2–4 lands and score ≥ 3 |
| **C — Keepable** | 2–4 lands and score ≥ 1 |
| **D — Mulligan** | Too few/many lands or insufficient acceleration |

Color-starved hands are capped to a lower tier. The simulator keeps **A/B**
hands, then tries the free Commander mulligan, then a London mulligan to six.

**Colorless** in the distribution means cards with no colored casting
requirement. It does not mean the deck literally requires {C} mana.
"""
    )

deck_col, settings_col = st.columns([2, 1])

with deck_col:
    st.subheader("1. Decklist")
    uploaded_deck = st.file_uploader(
        "Upload decklist (.txt)",
        type=["txt"],
        help="Format: one card per line as 'quantity card name'.",
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
    use_seed = st.checkbox("Use deterministic seed", value=False)
    seed = st.number_input(
        "Seed",
        min_value=0,
        value=42,
        step=1,
        disabled=not use_seed,
    )
    st.info(
        "Higher iteration counts reduce Monte Carlo noise but take longer to run."
    )

try:
    parsed_deck = parse_deck_text(deck_text)
except Exception:
    parsed_deck = []

with st.container(border=True):
    st.subheader("3. Deck Color Distribution")
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
            "Multicolor cards are split evenly across their colors; lands are excluded from demand."
        )

    if auto_detect:
        try:
            with st.spinner("Looking up cards on Scryfall..."):
                scryfall_cards, missing = cached_scryfall_lookup(
                    tuple(dict.fromkeys(parsed_deck))
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

st.subheader("4. Card Configuration")
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

card_tooltip = JsCode(
    """
class CardImageTooltip {
  init(params) {
    this.eGui = document.createElement('div');
    this.eGui.style.background = '#111827';
    this.eGui.style.border = '1px solid #374151';
    this.eGui.style.borderRadius = '10px';
    this.eGui.style.padding = '8px';
    this.eGui.style.boxShadow = '0 8px 24px rgba(0,0,0,.35)';
    this.eGui.style.maxWidth = '260px';

    const url = params.data && params.data.image_url;
    if (!url) {
      this.eGui.innerHTML = '<div style="padding:6px;color:#ddd">Load Scryfall data to enable card previews.</div>';
      return;
    }

    const img = document.createElement('img');
    img.src = url;
    img.alt = params.value || 'Card image';
    img.style.width = '240px';
    img.style.display = 'block';
    img.style.borderRadius = '8px';
    this.eGui.appendChild(img);
  }

  getGui() {
    return this.eGui;
  }
}
"""
)

mana_renderer = JsCode(
    """
function(params) {
  const value = params.value || '';

  const container = document.createElement('div');
  container.style.display = 'flex';
  container.style.alignItems = 'center';
  container.style.gap = '4px';
  container.style.height = '100%';

  if (!value) {
    return container;
  }

  Array.from(value).forEach(symbol => {
    const img = document.createElement('img');
    img.src = 'https://svgs.scryfall.io/card-symbols/' + symbol + '.svg';
    img.alt = symbol;
    img.title = symbol;
    img.style.width = '22px';
    img.style.height = '22px';
    img.style.display = 'block';
    container.appendChild(img);
  });

  return container;
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
            "tooltipComponent": card_tooltip,
            "tooltipValueGetter": JsCode("function(params) { return params.value; }"),
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
            "headerName": "Type",
            "field": "type",
            "minWidth": 170,
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
    "Weight 0 = unscored. 'Produces' is used for color coverage; Scryfall can prefill many mana sources automatically."
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
