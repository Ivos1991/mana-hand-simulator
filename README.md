# Mana Hand Simulator

A configurable Monte Carlo simulator for evaluating opening hands and mulligan quality in Magic: The Gathering Commander decks.

## Usage

1. Edit `data/decklist.txt`.
2. Edit `data/card_weights.csv` to assign acceleration values and categories.
3. Run:

```bash
python -m mana_hand_simulator.cli --iterations 100000
```

The simulator reports A/B/C/D hand-quality percentages for the opening seven, free mulligan, and London mulligan to six.

The scoring logic is intentionally configurable so different decks can reuse the same simulation engine without editing the code.
