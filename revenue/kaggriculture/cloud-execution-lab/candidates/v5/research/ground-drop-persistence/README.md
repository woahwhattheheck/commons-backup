# V5-19 ground-state DROP persistence

This package executes V5 seed #19 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The infinite
ground-storage hypothesis is **falsified**.

`DROP` has no ground-item path. Away from a shed-access coordinate it is a
silent no-op, including on empty and ordinary locked tiles. On any of the four
shed-access coordinates it transfers inventory directly into the actor's shed
up to `shedCapacity`, then discards the overflow. The end-of-day sweep applies
the same capped-shed behavior to remaining worker inventories and never creates
tile inventory.

The executable full-interpreter probe covers an empty non-shed tile, an ordinary
locked tile, a locked shed-access tile, and the end-of-day boundary with 500
Fertilizer against a capacity of 100. No case persists a ground item.

Run from this directory:

```bash
python3 -m unittest -v test_ground_drop.py
python3 verify_ground_drop.py
```

No TITAN runtime, policy/default, archive, opponent, seed panel, or Kaggle state
is changed.
