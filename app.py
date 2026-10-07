from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
import streamlit as st

from mana_hand_simulator.deck_loader import parse_deck_text
from mana_hand_simulator.models import CardConfig, HandTier
from mana_hand_simulator.simulator import run_simulation_from_data


ROOT = Path(__file__).resolve().parent
DEFAULT_DECK = ROOT / "data" / "decklist.txt"
DEFAULT_CONFIG = ROOT / "data" / "card_config.csv"


def load_default_deck() -> str:
    return DEFAULT_DECK.read_text(encoding="utf-8")


def load_default_config() -> pd.DataFrame:
    return pd.read_csv(DEFAULT_CONFIG)


def dataframe_to_config(frame: pd.DataFrame) -> dict[str, CardConfig]:
    config: dict[str, CardConfig] = {}

    required = {"card_name", "weight", "type", "is_land"}
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

        config[name] = CardConfig(
            name=name,
            weight=float(row["weight"]),
            category=str(row["type"]).strip(),
            is_land=is_land,
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
    }


st.set_page_config(
    page_title="Mana Hand Simulator",
    page_icon="🃏",
    layout="wide",
)

st.title("Mana Hand Simulator")
st.caption(
    "Monte Carlo opening-hand and mulligan analysis for MTG Commander decks."
)

with st.expander("How scoring works", expanded=False):
    st.markdown(
        """
Each hand is graded from its **land count** and the sum of its configured
**acceleration weights**.

| Tier | Default criteria |
|---|---|
| **A — Explosive** | 2–3 lands and score ≥ 5 |
| **B — Strong** | 2–4 lands and score ≥ 3 |
| **C — Keepable** | 2–4 lands and score ≥ 1 |
| **D — Mulligan** | Too few/many lands or insufficient acceleration |

The simulator keeps **A/B** hands. If the opening seven is not A/B, it takes
the free Commander mulligan. If that also fails, it performs a London
mulligan and evaluates every possible six-card hand after bottoming one card.
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

st.subheader("3. Card configuration")
uploaded_config = st.file_uploader(
    "Upload card config (.csv)",
    type=["csv"],
    help="Columns: card_name, weight, type, is_land",
)

if uploaded_config is not None:
    config_frame = pd.read_csv(StringIO(uploaded_config.getvalue().decode("utf-8")))
else:
    config_frame = load_default_config()

edited_config = st.data_editor(
    config_frame,
    width="stretch",
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "card_name": st.column_config.TextColumn("Card", required=True),
        "weight": st.column_config.NumberColumn(
            "Weight", min_value=0.0, step=0.5, format="%.1f"
        ),
        "type": st.column_config.TextColumn("Type"),
        "is_land": st.column_config.CheckboxColumn("Land"),
    },
)

st.caption(
    "Weight 0 = unscored. Mark lands/MDFCs with Land so they count toward the hand's land total."
)

if st.button("Run simulation", type="primary", width="stretch"):
    try:
        deck = parse_deck_text(deck_text)
        card_config = dataframe_to_config(edited_config)

        unconfigured = sorted(set(deck) - set(card_config))
        if unconfigured:
            st.warning(
                f"{len(unconfigured)} card name(s) are not in the config. "
                "They will count as nonland, weight-0 cards."
            )

        with st.spinner(f"Simulating {iterations:,} mulligan sequences..."):
            result = run_simulation_from_data(
                deck,
                card_config,
                iterations=iterations,
                seed=int(seed) if use_seed else None,
            )

        rows = [
            percentages_row("Opening 7", result.opening),
            percentages_row("Free mulligan 7", result.free_mulligan),
            percentages_row("Final hand", result.final),
        ]
        results = pd.DataFrame(rows)

        st.subheader("Results")

        metric1, metric2, metric3 = st.columns(3)
        opening_keep = results.loc[0, "A/B Keep"]
        final_keep = results.loc[2, "A/B Keep"]

        metric1.metric("Opening A/B", f"{opening_keep:.1f}%")
        metric2.metric(
            "A/B seen by free mulligan",
            f"{result.seen_ab_after_free_mulligan:.1f}%",
        )
        metric3.metric("Final A/B", f"{final_keep:.1f}%")

        formatted = results.copy()
        for column in ["A", "B", "C", "D", "A/B Keep"]:
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

    except Exception as exc:
        st.error(str(exc))
