# Native return-boundary port of the existing EOD rescue

This closes a native **component** integration gap in the single V4 workspace on
`main`. It consumes the existing mixed-product donor, not the older single-product
custody copy beside this README. It does not introduce another policy/controller,
change production defaults, execute a legacy materializer, or authorize a release.

## Exact transformation

The pinned caller is `main.py` blob `4a8cf7bcda1f0fea231a144692cb84a779a9e73e`
and its full runtime is `b952c9c228ecbde592bf3d2df01638677abb0d24`.
`port_native_eod.py` makes a new local staging copy. Disabled staging preserves
package source/data bytes. Explicit `--enabled` performs only these edits:

1. In the existing `FinalPressureAgent._early_capital_selected`, consume the
   final pressure result and apply the existing rescue before returning it.
   Native feed/stock/crop/capital/pressure guards therefore precede rescue, and
   spatial/crop/history receipts see the resulting action. The existing
   non-completed-status exit and `finally` flag restoration remain unchanged.
2. In donor `9ad4092453e2332b0914f90ca89791b18f2229c2`, replace only
   `import r04_full_router as r04` with `import mechanics as r04`.
   Native mechanics `044a4f9c0a4a44dde10ada57563238bcaf82075d` supplies the same
   official product list. No other rescue logic changes.
3. Carry H3c dependency `79c3fd029054a2db5931609db06f6b9aa4d4be3c` unchanged.
   No H3c controller is installed or enabled by this operation.

The generated caller is `7fa8ea7f39ccd54ae400e7b234756acaece5eb65`; generated
rescue is `6dc0930dee66b81a7e319fc21f8de80d9937241b`. The runtime, configuration,
and all other package files are unchanged. This staging composer rejects source
drift, existing outputs, source/output overlap, and conflicting composed helper
files. **Do not weaken the pins to stack a different native lifecycle revision.**
The single integration owner must reconcile that revision and repeat execution.

## Reproduce

Use a complete native package matching the source pins, with its preserved
`checks/reference/engine` and `checks/reference/evaluator` directories. Existing
Actions artifact `10123395668` contains `final-pressure-runtime`; its main file
is the older `2e70a9e7` and must be replaced with exact canonical `4a8cf7bc` before
this composer accepts it. Other package dependencies retain that artifact's
lineage; this packet does not claim it is the latest complete production archive.

From the repository root, set `PACKAGE` to that materialized native package:

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
HOME_EOD="$V4/repairs/gameplay/eod-capacity-rescue"
DONOR="$V4/donor/overlay/r04_eod_capacity_rescue.py"
H3C="$V4/donor/overlay/h3c_goose_eod_cap_rescue.py"
python "$HOME_EOD/test_native_eod.py" --package "$PACKAGE" --donor "$DONOR" --h3c "$H3C"
python -O "$HOME_EOD/test_native_eod.py" --package "$PACKAGE" --donor "$DONOR" --h3c "$H3C"
python "$HOME_EOD/run_native_eod_controls.py" --package "$PACKAGE" --donor "$DONOR" --h3c "$H3C"
python -O "$HOME_EOD/run_native_eod_controls.py" --package "$PACKAGE" --donor "$DONOR" --h3c "$H3C"
python "$HOME_EOD/port_native_eod.py" --package "$PACKAGE" --donor "$DONOR" --h3c "$H3C" --output /tmp/native-eod-trial --enabled
```

The output directory must not exist. Omit `--enabled` for unchanged control
staging. No network fetch, paid compute, owner-PC work, or hosted workflow is
started by this packet. Python 3.13.5 was used for the recorded checks.

## Executed boundary

Normal and optimized Python each passed **20/20 tests**. Each mode directly
counted 84 full native-finalizer calls and 40 paired full-interpreter transitions
with 20 positive rescues. Both seats, floor prices, mixed cargo, ambiguous actor
boundaries, full raw-order budgets, final-season exclusions, and rival purchases
are covered. The official interpreter is unchanged blob `3c202c7e...`; its
existing evaluator verifies all three upstream engine-source files offline.

There are also 48 actual native `act` opening callbacks per mode. Their off/on
actions and resulting states match, with every status completed. These are
no-overflow identity controls, **not natural rescue engagement or a season score**.

Boundary tests spy on real methods rather than substitute the finalizer.
Controlled completed-producer witnesses exercise the real public entrypoint:
one returns the rescue, and one raises its actual active timer's expiration
object inside rescue. Cancellation returns the original selected action, skips
later receipts, restores the pressure flag, and discards the interrupted instance.
This is deterministic cancellation injection, not a wall-clock stress benchmark.

All six mutated ports are rejected in both modes after running all 20 tests:
rescue disconnected; stale pre-pressure queue; fallback enabled; rescue after
receipts; incomplete raw-order budget; and legacy router import restored. Each
must trip its designated assertion (or the intentional runtime-import error).
A setup failure cannot count as a successful mutation rejection.

## What remains open

The prior ASTRA-EOD-ENGINE mixed-vector mechanism work is credited, not repeated
as new discovery. This packet closes the pinned native return seam only. It does
not prove simultaneous composition with every other V4 repair, current-head
full-package behavior, full-season economics, or ranking strength. Default stays
off pending those gates and a natural activation census.

Cash attribution remains separate: the native co-buy witness produced own
`+500`, rival `+40`, margin `+460` in each seat. Quoted cash telemetry is not
realized value, and unchanged private shed composition is not proof that public
market/rival effects are beneficial over a season. No production archive or
Kaggle submission was changed.
