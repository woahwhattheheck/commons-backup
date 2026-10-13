# V4 JIT all-actor occupancy repair

Source repair for `donor/overlay/jit_pass_fertilize.py`, built independently from the live
canonical predecessor `6ef7ddcd9590e3cb3f55ceb708b8026235d59410`.

The predecessor deduplicated only qualifying `PASS -> next authored WATER` matches. A
co-located public actor that was *not* a qualifying match (for example an actor already
emitting `FERTILIZE`) could therefore be invisible to duplicate suppression, allowing the
JIT helper to spend another fertilizer on the same tile coverage update.

This repair:
- counts every public own-farm actor position before matching;
- allows JIT only on uniquely occupied tiles;
- preserves independent unique-tile activations;
- fails closed on malformed public actor positions;
- rejects non-string crop values before `_ANNUAL` lookup, avoiding unhashable-key errors;
- preserves literal default/OFF identity, next-authored-WATER scope, annual/headroom rules,
  action nonmutation, and existing runtime wiring.

Focused source-level regression: 8/8 normal and 8/8 under `python -O`; `py_compile` passes.
This is not a package/economics/leaderboard or default-activation claim.
