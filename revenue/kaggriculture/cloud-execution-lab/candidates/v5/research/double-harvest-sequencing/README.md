# V5-22 same-tick double-harvest sequencing

This package executes V5 seed #22 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The crop-yield
duplication hypothesis is **falsified**.

The engine resolves the farmer first, followed by hands in list order. HARVEST
copies the current `yield_units` into the first executing actor's inventory and
immediately sets the tile yield to zero. Later actors at the same coordinate in
the same interpreter turn therefore observe zero yield and no-op.

The executable probe places one farmer and two hands on a mature three-unit
Carrot tile, varies which actor is the first active harvester, and submits all
later same-tick harvest attempts. Every ordering conserves exactly three units,
depletes the tile once, credits only the first executing actor, and leaves the
rival farm unchanged.

Run from this directory:

```bash
python3 -m unittest -v test_double_harvest.py
python3 verify_double_harvest.py
```

No TITAN runtime, policy, default, archive, opponent, or seed panel is changed.
