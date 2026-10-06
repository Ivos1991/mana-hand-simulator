# Mana Hand Simulator

A configurable Monte Carlo simulator for analyzing MTG Commander opening hands and mulligans.

## Quick start

1. Put your deck in `data/decklist.txt`.
2. Configure lands and card weights in `data/card_config.csv`.
3. Run:

```bash
python -m mana_hand_simulator.cli --iterations 100000
```

Outputs A/B/C/D hand-quality percentages for the opening seven, free mulligan, and London mulligan to six.

Deck data and scoring inputs live outside the Python code so the simulator can be reused for different decks.
