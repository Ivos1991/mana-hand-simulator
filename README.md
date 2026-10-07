# Mana Hand Simulator

A configurable Monte Carlo simulator for evaluating MTG Commander opening
hands, mulligan decisions, acceleration, and colored mana access.

## Web app

The Streamlit UI lets you:

- paste or upload a Commander decklist
- edit acceleration weights and land flags
- assign which colors each mana source can produce
- enter deck color demand manually
- **auto-detect deck colors and mana production with Scryfall**
- preview card images returned by Scryfall
- simulate opening 7 → free Commander mulligan → London 6
- compare A / B / C / D hand rates and average color coverage

Run locally:

```bash
pip install -e .
streamlit run app.py
```

For Streamlit Community Cloud, deploy `app.py` from the `main` branch.

## Color-aware simulation

The app separates two ideas:

- **Color demand** — the color distribution of the spells in the deck.
- **Color supply** — the colors the mana sources in an opening hand can produce.

The color distribution can be edited manually or calculated from Scryfall.
For automatic calculation, lands are excluded from spell demand. Each nonland
card contributes one unit; multicolor cards divide that unit across their
colors, and cards with no colored casting color are counted as **Colorless**.

Colorless distribution means "no colored casting requirement." It does not
mean the deck requires literal `{C}` mana.

A hand that has enough lands and acceleration but poor access to colors the
deck needs can be capped to a lower tier.

## Base hand ratings

| Tier | Base criteria |
|---|---|
| **A — Explosive** | 2–3 lands and score **5+** |
| **B — Strong** | 2–4 lands and score **3+** |
| **C — Keepable** | 2–4 lands and score **1+** |
| **D — Mulligan** | Too few/many lands or insufficient acceleration |

A/B hands are treated as keeps.

## Mulligan simulation

For every iteration:

1. Draw an opening 7.
2. If it is not A/B, take the free Commander mulligan to 7.
3. If that is still not A/B, draw a London 7 and evaluate every possible
   six-card hand after bottoming one card.

The London chooser considers tier, color coverage, acceleration score, and
land count.

## Card configuration

The config CSV now supports:

```csv
card_name,weight,type,is_land,produces
Swamp,0,land,true,B
Sol Ring,3,premium_acceleration,false,C
Arcane Signet,2,mana_rock,false,WUBRG
"Watery Grave",0,land,true,UB
```

`produces` uses the mana symbols `W U B R G C`. In the web app it is a
dropdown rather than free text.

Scryfall can prefill many land/mana-source values from its public card data,
and the user can override them afterward.

## CLI

The original command-line simulator remains available:

```bash
pip install -e .
mana-hand-simulator --iterations 100000
```

Optional deterministic run:

```bash
mana-hand-simulator --iterations 100000 --seed 42
```

The CLI remains backward-compatible with configs that omit `produces`; color
analysis is enabled when color demand is supplied by a caller such as the web
app.

## Data

- `data/decklist.txt` — the default Avacyn 99-card library
- `data/card_config.csv` — default weights, land flags, and mana-production metadata
- `examples/avacyn-angel-of-horror/` — preserved Avacyn example data

## Scryfall

The web app uses Scryfall's public API for optional card metadata lookup.
Results are cached by Streamlit to avoid repeated API requests.
