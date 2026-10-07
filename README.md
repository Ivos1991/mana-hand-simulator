# Mana Hand Simulator

A configurable Monte Carlo simulator for evaluating MTG Commander opening hands and mulligan decisions.

## How it works

Each simulated hand is evaluated using:

- **Land count** — cards marked `is_land=true`
- **Acceleration score** — the sum of the configured card weights

| Tier | Criteria |
|---|---|
| **A — Explosive** | 2–3 lands and score **5+** |
| **B — Strong** | 2–4 lands and score **3+** |
| **C — Keepable** | 2–4 lands and score **1+** |
| **D — Mulligan** | Too few/many lands or insufficient acceleration |

**A/B hands are keeps.** The simulator tests the opening 7, a free Commander mulligan to 7, and then a London mulligan to 6. For the London mulligan it evaluates every possible card to bottom and chooses the best six by tier, score, then land count closest to 3.

## Web app

The Streamlit UI lets you paste/upload a decklist, edit card weights and land flags, choose the number of iterations, and run the simulation in your browser.

Run locally:

```bash
pip install -e .
streamlit run app.py
```

To deploy for free on **Streamlit Community Cloud**, connect this GitHub repo and use `app.py` as the entrypoint.

## CLI

```bash
pip install -e .
mana-hand-simulator --iterations 100000
```

Optional deterministic run:

```bash
mana-hand-simulator --iterations 100000 --seed 42
```

## Data

- `data/decklist.txt` — default decklist
- `data/card_config.csv` — card weights, categories, and land flags
- `examples/avacyn-angel-of-horror/` — preserved Avacyn example data

Deck format:

```text
36 Swamp
1 Sol Ring
1 Arcane Signet
```

Config format:

```csv
card_name,weight,type,is_land
Swamp,0,land,true
Sol Ring,3,premium_acceleration,false
Arcane Signet,2,mana_rock,false
```
