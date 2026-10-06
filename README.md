# Mana Hand Simulator

A configurable Monte Carlo simulator for evaluating MTG Commander opening hands and mulligan decisions.

## How it works

Each simulated hand is evaluated using two inputs:

- **Land count** — cards marked `is_land=true` in `card_config.csv`.
- **Acceleration score** — the sum of the weights of scored cards in the hand.

Example:

```csv
card_name,weight,type,is_land
Swamp,0,land,true
Sol Ring,3,premium_acceleration,false
Arcane Signet,2,mana_rock,false
Blood Pet,1,ramp,false
```

A hand with 3 lands, `Sol Ring`, and `Blood Pet` has an acceleration score of **4**.

## Hand ratings

| Tier | Criteria |
|---|---|
| **A — Explosive** | 2–3 lands and score **5+** |
| **B — Strong** | 2–4 lands and score **3+** |
| **C — Keepable** | 2–4 lands and score **1+** |
| **D — Mulligan** | Fewer than 2 lands, more than 5 lands, or insufficient acceleration |

The simulator treats **A/B hands as keeps**.

## Mulligan simulation

For every iteration it simulates:

1. **Opening 7**
2. If not A/B → **free Commander mulligan to 7**
3. If still not A/B → **London mulligan to 6**

For the London mulligan, all seven possible cards to bottom are evaluated and the simulator keeps the best six-card hand based on:

1. Hand tier
2. Acceleration score
3. Land count closest to 3

The final output shows the percentage of **A / B / C / D** hands at each stage and the overall **A/B keep rate**.

## Use your own deck

Put your deck in:

`data/decklist.txt`

```text
36 Swamp
1 Sol Ring
1 Arcane Signet
...
```

Configure relevant cards in:

`data/card_config.csv`

```csv
card_name,weight,type,is_land
Swamp,0,land,true
Sol Ring,3,premium_acceleration,false
Arcane Signet,2,mana_rock,false
```

Cards that do not affect land count or acceleration do not need a config entry.

## Run

```bash
pip install -e .
mana-hand-simulator --iterations 100000
```

Optional deterministic run:

```bash
mana-hand-simulator --iterations 100000 --seed 42
```

## Avacyn example

The exact deck and weights used while developing the simulator are included in:

`examples/avacyn-angel-of-horror/`

Run the 1,000,000-hand simulation with:

```bash
mana-hand-simulator \
  --deck examples/avacyn-angel-of-horror/decklist.txt \
  --config examples/avacyn-angel-of-horror/card_config.csv \
  --iterations 1000000
```
