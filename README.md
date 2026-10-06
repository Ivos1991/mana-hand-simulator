# Mana Hand Simulator

Configurable Monte Carlo simulator for MTG Commander opening hands and mulligans.

## Quick start

```bash
pip install -e .
mana-hand-simulator --iterations 100000
```

Edit:
- `data/decklist.txt` — deck contents
- `data/card_config.csv` — land flags, card weights, and categories

The simulator reports A/B/C/D hand-quality percentages for the opening seven, free mulligan, and London mulligan to six. Deck data stays outside the Python code so different decks can reuse the same engine.
