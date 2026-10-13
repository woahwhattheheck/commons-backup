# V5-25 cross-farm ownership boundary

This package executes the Tier 9 #25 cross-border HARVEST/CLEAR hypothesis
against the repository's pinned Kaggriculture engine (git blob `3c202c7e...`,
SHA-256 `bc8a5487...`). The hypothesis is **falsified**.

The engine does not accept a farm selector or coordinates for worker HARVEST.
`interpreter()` selects `obs0.farms[i]` for the acting player and passes that
single farm into `_apply_unit_action()`. A `HARVEST` coordinate tail is ignored;
the action applies only to the unit's current tile in its own farm. `CLEAR` is
not a supported worker verb. The supported destructive verb, `DIG`, is likewise
confined to the current tile of the acting farm.

`verify_cross_farm_boundary.py` proves those properties through full
`interpreter()` turns, including a mature rival crop, a local mature crop, the
unsupported CLEAR form, and DIG. It compiles the pinned engine source unchanged
except for the unavailable framework seed-import shim and rejects any source or
configuration hash drift.

Run from this directory:

```bash
python3 -m unittest -v test_cross_farm_boundary.py
python3 verify_cross_farm_boundary.py
```

No TITAN runtime, policy flag, default, archive, opponent, or seed panel is
changed. There is no cross-farm exploit to promote from this lane.
