# UNITFLOW: native joint-unit projection

One repair component in the canonical `main:candidates/v4` workspace. This is
not another V4 root, controller, feature key, or production package.

## Demonstrated defect

The current unit snapshot already checks joint seed demand. Three future
replays did not: `SellScheduler.receipt_profile`, `_funding_trace`, and
`represented_shed_event` applied actors sequentially. The official interpreter
instead blocks **every** PLANT request for a crop when its raw request count
exceeds pre-unit seeds. Nonexistent actors and impossible planting tiles still
contribute to that count.

Constructed full-interpreter witness: shed 99 (WHEAT 98, MILK 1), three actors
each carrying one FERTILIZER, two WHEAT seeds. Sell the MILK, then request three
PLANTs, three FERTILIZEs, return and DROP. The predecessor certifies capacity:
it incorrectly plants two crops and spends two fertilizer units. The engine
blocks all three plants; all fertilizer remains, and the final DROP discards
one unit. The repaired capacity certificate rejects that same schedule.

Additional witnesses cover understated realized future sale revenue and a
missed future shed-load event. Both seats are exercised. No full-game or
leaderboard improvement is asserted.

## One shared repair, four consumers

`compose.py` installs `apply_projected_units` in the existing native scheduler,
then routes current snapshots and all three future consumers through it. The
frozen seller consumes the same helper through its existing scheduler import.
Authored action vectors remain untouched. Per-crop admission, raw list shapes,
extra actors and short PLANT no-ops match the pinned interpreter.

Only two materialized source files change. All market-prefix, economic,
clock, objective, feature/default, route and archive bytes remain outside this
repair. The transformer requires exact seams and explicit input Git blobs;
partial or repeated application fails. It writes only a new output directory.

## Reproduction

Use the complete extracted archive from existing GitHub Actions artifact
`10175943272`, run `34537404363`. Archive SHA-256 is
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
No new Actions run, Kaggle access, package installation or network is needed.

From the repository root, with `PKG` pointing to that extracted package:

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
UNIT=$V4/repairs/runtime/joint-unit-projection
PREFIX=$V4/repairs/scheduler-action-prefix/scheduler_action_prefix.py
python "$UNIT/test_joint_units.py" --package "$PKG" --prefix-transformer "$PREFIX"
python -O "$UNIT/test_joint_units.py" --package "$PKG" --prefix-transformer "$PREFIX"
python "$UNIT/compose.py" --package "$PKG" --output /tmp/unitflow-new-output
```

The test verifies all 109 runtime members against the pinned SOURCE manifest.
It runs 16 tests, 672 unit-state matrix cases, 803 complete interpreter calls
and four behavioral mutation discriminators per mode. The CLI output contains
source only; it is **not** a rebuilt or authorized release.

## Preserve the already-landed market-prefix repair

Consume existing transformer `2958bff92c7d95d9e113b2406e7de1bb7a28de08`
first. It maps scheduler `a483b24d...` to `742a200e...`. Applying UNITFLOW to
that exact postimage produces scheduler `8e224e53298f633ed976c71eea6019eb5faf6e67`
and frozen seller `8188020d514bad7c2030ef0b6966c60a8f1aa96b`.

The focused suite actually executes this composition and verifies that
reversing only UNITFLOW recovers the complete peer postimage byte-for-byte.
Use the CLI's `--scheduler-blob 742a200e9a72e303ad18c51c104895013a7f3a4b`
when the input package already contains that prefix postimage. Do not reset
newer peer code to the standalone baseline. Further source drift needs fresh
composition and validation, not a forced transplant.

## Validation boundary

Python 3.13.5 only; no hosted-CI claim. Existing funding (8 tests) and joint
market slots (28 tests) pass on baseline, UNITFLOW, and prefix+UNITFLOW in both
normal and optimized modes. The old selected-pruning suite retains exactly
50 pre-existing subcase failures in all six runs; normalized failure records
match. Its diagnostic-schema mismatch was relayed to the active performance
owners, not silently hidden or repaired in this lane.

No production source/default/archive or Kaggle submission was changed.
Current-runtime serialization and competitive evaluation remain separate.
