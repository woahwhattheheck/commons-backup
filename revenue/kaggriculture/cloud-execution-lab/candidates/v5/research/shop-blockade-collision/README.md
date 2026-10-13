# V5-21 physical shop-blockade collision

This package executes V5 seed #21 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The physical
shop-blockade hypothesis is **falsified**.

Farms use separate tile grids and workers never enter a shared town coordinate
space. Market orders are submitted directly in the action's `market` list and
are processed after unit actions; they do not require a worker to path to a shop.
Unlocked town shops affect inventory consumption, not physical access.

The executable probe places the opposing farmer plus ten hands on the same
shed-access coordinate, then verifies in both seats that the actor can still buy
a Carrot seed, buy Wheat, and sell Carrot through full `interpreter()` turns.
All transactions execute despite the maximal opposing occupancy panel.

Run from this directory:

```bash
python3 -m unittest -v test_shop_blockade.py
python3 verify_shop_blockade.py
```

No TITAN runtime, policy/default, archive, opponent, seed panel, or Kaggle state
is changed.
