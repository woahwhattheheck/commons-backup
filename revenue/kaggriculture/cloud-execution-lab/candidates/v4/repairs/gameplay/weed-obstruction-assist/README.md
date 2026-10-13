# TITAN V4 WEED same-turn obstruction assist

Status: **additive source donor; default OFF; not composed by this package**.

This package stays inside the single canonical `candidates/v4` tree. It does not create a
second controller, runtime, config key, COMPOSITION row, archive, evaluator, or Kaggle
submission.

## Source-real seam

The pinned official interpreter
`reference/engine/kaggriculture.py` Git blob
`3c202c7ee921da239356789e266b694635103fc4` establishes all of the relevant mechanics:

1. `PLANT`, `BUILD_COOP`, and `BUILD_PASTURE` require the actor's current tile to be
   `None`; a `{"kind": "WEED"}` tile therefore makes those authored actions silent no-ops.
2. `DIG` clears a weed to `None`.
3. Atomic PLANT demand is counted over the raw farmer row plus **every raw hand row**
   before unit dispatch. If raw crop demand exceeds private seeds, all PLANT rows for
   that crop are replaced by PASS for execution.
4. Unit dispatch is strictly main farmer first, then live hands in ascending index order.

Apex V7's visible wrapper recognized the same obstruction class but uses a persistent
one-step retry: it DIGs with the blocked actor, remembers the intended action, then
restores that action on the next callback. That broad shape has avoidable hazards:
next-callback action theft, end-of-day actor resets, state leakage across episodes, and
a possible WEED→empty side effect even when the delayed intended action never executes.

## Stronger same-turn construction

`weed_assist.py::assist_same_turn_weed_obstructions()` uses the interpreter's actor
ordering instead of persistent retry state.

For a later live actor whose current tile is WEED and whose authored action is one exact
valid `PLANT`, `BUILD_COOP`, or `BUILD_PASTURE`, the helper may replace an **earlier
co-located live actor's literal `["PASS"]`** with `["DIG"]`. The intended target action
is left byte-for-byte where it already is. During the same interpreter turn, the helper
actor clears the WEED and the later actor then sees `None`.

The transform fails closed unless all of these conditions hold:

- helper and target are both live actors with exact observable positions;
- helper is earlier in engine dispatch order and is exactly `["PASS"]`;
- the target action has the exact conservative action shape supported by this donor;
- the observed target tile is exactly `{"kind": "WEED", ...}`;
- every intervening co-located actor is only PASS, DIG, or movement, so nothing can
  occupy the newly empty tile before the target executes;
- for PLANT, the engine's **raw** farmer + all-hand crop demand is no greater than the
  exact available seed count. Engine-dead suffix hand rows therefore cannot be ignored.

Surplus raw hand rows are never used as helpers and are never edited. They remain
significant to the PLANT census exactly as the engine treats them.

Multiple independent coordinates can be assisted in one action. At most one target per
coordinate is admitted in a call, and each helper can be consumed only once.

When disabled or when no certified rewrite exists, the exact input action object is
returned by identity. Inputs are never mutated.

## Local receipt

Local source-only execution on the published candidate bytes:

- `python -S test_weed_assist.py`: **19/19 PASS**
- `python -S -O test_weed_assist.py`: **19/19 PASS**
- `py_compile weed_assist.py test_weed_assist.py`: **PASS**

Coverage includes:

- farmer→hand and hand→later-hand same-turn assists;
- PLANT and BUILD witnesses;
- exact disabled/no-op identity and non-mutation;
- later-helper rejection;
- non-co-located rejection;
- raw suffix PLANT demand poisoning;
- raw suffix preservation;
- unsafe intervening same-position occupancy rejection;
- latest-helper selection;
- movement between helper and target;
- two independent assists in one turn;
- player-1 farm selection;
- malformed action/observation poison;
- minimal interpreter-order witnesses showing baseline WEED no-op versus repaired
  same-turn PLANT/BUILD success.

Local candidate source identities before publication:

- `weed_assist.py`: 7,393 bytes, SHA-256
  `b20f0bbe48231a4704da3c9a736692edd5d1a40690e692d46b04980a22759ba9`,
  Git blob `2d3cb5c4af86056ee184644279cf66fffb7722dd`.
- `test_weed_assist.py`: 10,514 bytes, SHA-256
  `54722d05bb343c52f28c85840b28b27de6675f1d5ff84623c0d48dd1df913b60`,
  Git blob `05026f3da24d9c427a3fcf2760578863908e1218`.

## Promotion boundary

This package does **not** wire the assist into `main.py` or `titan_runtime.py` and does
not flip any default. Before composition, the single-V4 owner should require:

1. a current-native natural-engagement census proving co-located PASS→blocked-target
   situations actually occur;
2. exact official-engine both-seat games on a current authenticated runtime;
3. receipt binding to the final returned action, not an internal candidate;
4. collision review against action finalizers, seed admission, movement legality,
   SHOPSTREAM/RNG-sensitive end-of-day occupancy work, and any later same-coordinate
   transform;
5. competitive economics, with OFF/ON parity for all non-engaging cells.

A future deferred retry variant belongs in this same obstruction-recovery authority, but
it should not be promoted unless the next action slot is explicitly reserved and
episode/day/actor identity is source-bound. The blind Apex-style persistent override is
not certified by this package.
