# WAYFINDER — exact native work-route search

**Built and gated component in the ONE `main:candidates/v4` workspace.**
The current package does **not** enable `spatial_pathing`; this component remains
cold by default. It is not a new controller, policy, feature key, release archive,
or Kaggle submission. Do not promote it as an active-default speed improvement.

## What changes

The existing `SpatialTempo.transform` visits up to six distinct work sites.
It constructs every permutation's complete movement/work action list, filters
by the available segment length, and chooses the first minimum-movement list.
WAYFINDER computes that exact winner before constructing an action list.

For one through three sites it enumerates scalar costs. For four through six it
uses a bounded Held–Karp dynamic program over `(visited sites, final site)`.
Each state retains the lexicographically earliest minimum-cost prefix, and the
final choice includes the distance back to the original endpoint. Six sites
require at most 192 states instead of 720 complete route lists.

The native `path` length is Manhattan distance. Work length is constant across
orders and contains no movement actions. Consequently the shortest travel order
is also the shortest total route. If it cannot fit, no permutation fits. If it
fits, `(travel cost, input-index tuple)` produces exactly the original stable
permutation tie-break. For a fixed DP state, every suffix has the same remaining
sites and starting point, so discarding a more expensive or lexicographically
later equal-cost prefix cannot change the final winner.

Only the winning native movement segments are constructed. Work rows retain
order within their site and original object identity. Native movement-row alias
shape, caller PASS padding, positive-savings check, exact own-unit state veto,
optional tempo logic, market rows, route edits and commit lifecycle are unchanged.
This theorem concerns supported native integer-grid observations and the pinned
caller; it is not a claim about arbitrary monkeypatched path functions.

## Source custody and safe composition

Input `spatial_tempo.py`: Git blob `edbc423023479dbe2e78131495334384a87b607f`.
Generated source: `bea9e4a9456b450d2a41fc7ae2812862ead437f9`, SHA-256
`32e46f9f0a46696fb83abf150394ae4512540e1a19008dca360c15eb801dfcbb`.
Live main matched that input when this build began.

`compose_work_route.py` authenticates the whole native `transform` method,
`path`, `distance`, movement/work vocabularies and permutations import. It rejects
partial applications or changed helpers, is idempotent, and preserves every
byte outside its helper insertion and replacement search block. Edits to other
methods remain intact. The CLI refuses in-place output. Changed transform
methods require explicit source review, not a relaxed hash or stale postimage.

Known overlap: TAPEPORT's `port_native_action_copies.py` changes action-copy
expressions inside this same method. Apply WAYFINDER first, then use TAPEPORT's
supported **reviewed input-pin** facility for the resulting spatial blob, while
preserving its exact callsite/count checks. That order is a composition recipe,
not a combined-stack validation claim. TAPEPORT/TAPESTRY retain their copy/helper
ownership; their global gate and the existing single native assembler remain
authoritative. Do not overwrite those peers with this historical full module.

## What actually ran

17/17 focused tests pass in both normal Python and `python -O`, with no errors or
skips. Per mode this includes 480 random full-action comparisons against a
literal independent exhaustive reference, all 720 labelings of a symmetric
six-site grid, 216 exact feasibility-boundary cases, 36 alias cases, and native
transform comparison across six site counts, both seats and farmer/hand actors.
The full pinned official interpreter executes 1,152 transitions per mode across
48 constructed complete-day trajectories. These are not ladder games.

Eight deliberately broken composed variants each fail behavioral assertions in
both modes: goal cost, tie order, length budget, within-site work order, endpoint
path, DP objective, state veto, and PASS padding. Error-only rejection receives
no credit. Four separate unchanged controls pass before those fault groups.

The existing process-isolated evaluator ran **16 complete games / 11,504 TITAN
callbacks**, seeds 2027 and 6607, both seats, official starter, four arms:
original/candidate with unchanged default config and original/candidate with the
existing `spatial_pathing=True` key in scratch config only. The unchanged
`main.py::agent` is called through a diagnostic wrapper which rejects any
non-completed status. All eight before/after pairs have identical raw-action,
cash-stream and final-observation hashes, scores and search histograms. All
callbacks complete. Native workers are normal Python; the component and mutation
suites separately cover `-O`.

Default arms execute zero searches. Enabled arms execute 3,487 searches per game
on seed 2027 and 3,492 on 6607, including 111 six-site searches per game. Before/after scores within each flag setting
are unchanged. Seed 2027 gives our 91,632 vs starter 3,856 in both settings.
Seed 6607 gives our 124,781 OFF versus 124,767 ON, against starter 3,884: the
existing pathing flag costs 14 own cash/margin in BOTH seats. That inherited
flag behavior is not introduced by this exact solver. Keep the flag OFF.
These controls show reachability/equivalence,
not new economic gain or playing strength. Two oversized initial invocations
hit the container command limit; the final counted panel was rerun in bounded
four-game invocations and only finalized reports count.

All 109 runtime-map members authenticate against the recovered published b567
package. Artifact 10175943272 ZIP SHA-256 is
`3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`.
This archive is **not** the unassembled later current-main V4 dependency set.
No final-current-stack or hosted Kaggle gate was run.

### Performance and counterweights

Nine alternating local batches, 96 tours/batch: six-site search is 12.72x normal /
12.69x optimized faster than the exhaustive reference. Twelve actual native
transforms/batch: six-site transform is 6.77x / 7.08x faster. Four-site transforms
are about 1.10x. One-site tour is **slower** (0.676x / 0.716x). These are local
batch measurements, not default, universal or whole-agent speed claims.

The inherited four-module selection is **not green**: all four baseline/candidate
normal/optimized runs have 87 tests, 86 passes and the same one failure:
`test_prelude_fallback_returns_and_sells_already_collected_unit` expects SOUTH but
receives PASS. The separate runtime/prelude repair owner retains that seam.
No result here clears that pre-existing package failure or claims hosted CI green.

## Reproduce offline

Use the exact extracted runtime as ROOT and its CURRENT-SOURCE.json as MANIFEST.
Run from this component directory. No script dispatches Actions or accesses Kaggle.

```sh
export TITAN_ROOT=/path/to/authenticated/final-pressure-runtime
MANIFEST=/path/to/checked-package/runtime/integrated-selected/CURRENT-SOURCE.json
python compose_work_route.py "$TITAN_ROOT/spatial_tempo.py" /tmp/spatial-after.py
python test_work_route.py
python -O test_work_route.py
python run_controls.py --root "$TITAN_ROOT" --output /tmp/faults.json
python -O run_controls.py --root "$TITAN_ROOT" --output /tmp/faults-optimized.json
python benchmark.py --output /tmp/benchmark.json
python -O benchmark.py --output /tmp/benchmark-optimized.json
for seed in 2027 6607; do
  for seat in 0 1; do
    python run_native.py --root "$TITAN_ROOT" --manifest "$MANIFEST" \
      --seeds "$seed" --seats "$seat" --output "/tmp/native-$seed-$seat.json"
  done
done
```

The mutation runner supports `--mutants name1,name2` to bound each command; every
invocation still runs an unchanged control. Every native invocation creates and
removes separate scratch copies; it never changes ROOT. Inherited selection:

```sh
PYTHONPATH="$TITAN_ROOT/checks:$TITAN_ROOT" python -m unittest \
  test_weed_continuation test_idle_fertilizer test_crop_release test_feed_stock
```

Repeat with `-O` and the separately composed scratch tree. Preserve the disclosed
failure rather than deleting it to manufacture a green report. VALIDATION.json
contains compact exact identities/results; runnable scripts reproduce full
reports. Completion closes claim `1789182780.349239`; do not treat it as an
orphaned source build or commission another route-search controller.
