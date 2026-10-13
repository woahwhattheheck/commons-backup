# V5-26 animal crop-box pathing

This package executes V5 seed #26 against the pinned official Kaggriculture
engine (git blob `3c202c7e...`, SHA-256 `bc8a5487...`). The crop-box pathing
hypothesis is **falsified**.

Animals do not wander or pathfind in this engine. An animal is state embedded in
its fixed structure tile. At the day-4 production boundary, a fed Goose at the
center of a 3×3 Wheat ring has exactly the same state and coordinate as a Goose
in an open field. Harvesting its Egg therefore requires visiting its fixed Coop,
but never chasing a moving animal. A Goose starved for two days disappears and
leaves the Coop in place; it does not relocate through or around the crop ring.

The full-interpreter probe compares boxed and open-field twins, exercises daily
production, harvest, and the two-day unfed escape lifecycle, and checks for any
secondary animal location.

Run from this directory:

```bash
python3 -m unittest -v test_animal_box.py
python3 verify_animal_box.py
```

No TITAN runtime, policy/default, archive, opponent, seed panel, or Kaggle state
is changed.
