# EVENTPATH: sparse MarketPath scoring

Status: **component verified and delivered to canonical main; not activated**.
One TITAN V4 workspace, no new controller, policy key, default, or release line.

The native `consumer=frozen` path uses `frozen_selected.optimize_lot` from
`selected_sell_core.py`, not the standalone scheduler optimizer. Both source
surfaces are supported. The active core already caches absorption; timings below
compare against that real predecessor, not an older uncached implementation.

## Change and source boundaries

`build_score_eventpath.py::compose(source)` replaces only the verified
`MarketPath.score`, retaining its exact original as a fallback. It scores dated
own/rival order events instead of repeatedly calling `joint` on empty turns.
Cumulative town consumption is applied before each event and after the last one,
with market-before-town timing preserved. Cache identity includes dates, product,
shop multiplicity, and both consumption intervals. Short horizons retain the
reference loop. Non-native lot values use the reference fallback.

Floor admission, all scenario objectives, residual carry, terminal handling,
optimizer candidate families, tie-breaks, diagnostics, and ordered capacity
callbacks are unchanged. All other input bytes are retained, including independent
receipt-prefix, scheduler-prefix, and optimizer edits. The composer authenticates
the score and absorption methods, rejects drift, and refuses existing outputs.

Verified predecessor Git blobs:

- `selected_sell_core.py`: `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`
- `scheduler.py`: `a483b24dd72b580d7d8811636b54d2d44f391575`

Exact output SHA256s and all source identities are in `VALIDATION.json`.

## Reproduce without modifying a runtime

Run from this directory. `TITAN_RUNTIME` must identify the unmodified, authenticated
109-file b567 checked runtime. Existing GitHub artifact 10175943272 contains it
under `final-pressure-runtime/`; no workflow dispatch or new game run is required.

```bash
export TITAN_RUNTIME=/absolute/path/to/final-pressure-runtime
OUT=$(mktemp -d)
python test_score_eventpath.py
python -O test_score_eventpath.py
python build_score_eventpath.py "$TITAN_RUNTIME/selected_sell_core.py" "$OUT/selected_sell_core.py"
python build_score_eventpath.py "$TITAN_RUNTIME/scheduler.py" "$OUT/scheduler.py"

# Reuse CALENDAR's existing independent oracle; do not copy or replace it.
for MODE in normal optimized; do
  OPT=""; [ "$MODE" = optimized ] && OPT="-O"
  for SURFACE in selected_sell_core scheduler; do
    PIN=$(python -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' "$OUT/$SURFACE.py")
    python $OPT ../test_eventpath_engine.py \
      --runtime-root "$TITAN_RUNTIME" \
      --candidate "$OUT/$SURFACE.py" --candidate-sha256 "$PIN" \
      --surface "$SURFACE" --output "$OUT/$SURFACE-$MODE.json"
  done
done
python benchmark_score_eventpath.py --repeats 7 --output "$OUT/timing.json"
```

Verify the generated candidates against `VALIDATION.json` before interpreting
new results. The independent oracle is the existing sibling
`../test_eventpath_engine.py`, Git blob `7779873e04a0e3af5651ef9a9230f391dc51761f`.
Its entire 109-member runtime manifest is authenticated before candidate loading.
These commands create scratch candidates; they do not patch the checked runtime.

## Executed evidence

Own suite: **26/26 normal and 26/26 optimized**, zero failures/errors, compile PASS.
Per mode: 13,824 exhaustive score pairs, 1,600 seeded all-product pairs, 112 complete
optimizer/capacity-order pairs, and 216 official market/town worlds. Three semantic
mutants are rejected on each source surface. A nine-tick witness reduces `joint`
calls from nine to three with an identical returned score tuple.

Independent peer oracle: **four isolated runs**, both source surfaces in normal
and optimized Python, each **8/8 PASS with zero skips**. Each run authenticates
109 runtime members and executes 930 worlds, 8,554 official market calls, 8,307
town calls, 1,944 score comparisons, 36 optimizer/callback-order pairs, and four
mutant rejections. This includes the active frozen-consumer import-path check.

## Timing and limitations

Seven interleaved repetitions of 36 cold-model optimizer cases per source/horizon,
with exact outputs checked every repetition, produced these local medians:

| Active selected-core horizon (`end-now`) | Base seconds | Candidate seconds | Elapsed reduction |
|---|---:|---:|---:|
| 1 | 0.079124 | 0.082335 | -4.06% |
| 3 | 0.155451 | 0.158700 | -2.09% |
| 8 | 0.191281 | 0.180016 | 5.89% |
| 24 | 0.292033 | 0.195471 | 33.07% |

The short-horizon 2–4% overhead is real in this local run despite reference-loop
fallback. The standalone scheduler shows 21.24% and 53.84% reductions at horizons
8 and 24, but those are **not** the active frozen-consumer optimizer's gains.
Raw wall-time samples and output hashes are retained in `VALIDATION.json`.
This is not whole-agent deadline, game-profit, or field-strength evidence.

## Single-V4 integration handoff

Consume this one component within `main:candidates/v4`. Prioritize the active
selected-core surface. Preserve MEADOW's receipt work, SIEVE's bound pruning,
CACHELIFE's resource-lifetime work, and the scheduler-prefix owners' edits.
The composer preserves unrelated bytes; that is not a claim that every future
combination has been executed. The sole runtime serializer must compose the exact
current methods, rerun independent parity and whole-package timing, and account
for short-horizon overhead before activation. No production source, default,
archive, Actions configuration, or Kaggle submission was changed by this package.
