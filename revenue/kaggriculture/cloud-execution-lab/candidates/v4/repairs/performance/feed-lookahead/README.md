# FEEDPATH: native feed and operating-stock lookahead

**Built, executed, and landed in the single `main:candidates/v4` workspace. This is a source component, not an activated runtime or a second V4.**

The native stock module called `_action(row, actor)` inside three actor loops. That helper rebuilt `[farmer, *hands]` for every actor. This component inlines the exact lookup at those three sites and indexes ordinary lists directly. It retains the original materialization fallback for other iterables. It does not cache rows, observations, actions, or mutable state.

The three consumers are `_feed_window`, `_bonus_water_service`, and `protect_operating_stock`. Original `_units` and `_action` remain unchanged for other callers. Farmer/hands lookup order, false-value fallback, fresh PASS lists, action aliases, list-subclass iteration, one-shot iterables, and mutations between actor evaluations have independent controls. The actor index is known nonnegative because each source seam includes its exact `enumerate(positions)` header.

## Integration and custody

Use `compose_feedpath.py` on a scratch copy of the native `operating_stock.py`. The composer authenticates both reference helper bodies, verifies all three loop seams, rejects partial composition and reserved-local collisions, and is idempotent. It replaces only the three lookup sites, not entire method postimages. Other correctness edits are preserved; that property has an explicit test.

GRAFT, STOCKBRIDGE, PASTURE, and STOCKPORT retain operating-input correctness ownership. WEAVE and the shared current-native assembler retain combined activation. Apply any whole-input-pinned correctness composers first, then FEEDPATH. A changed helper or loop fails closed and requires reconciliation; never replace their whole module with this experiment's old postimage. This package does not certify that combined stack and does not create another build demand.

Original live-main source readback matched Git blob `781aa90da0d85d0ba23c665e29d6087d182c085e`, SHA256 `aade61ed3bcaca175998ab2871b97042dde0036950f038aef6326482e0fdd21c`. The emitted module has SHA256 `e2723b5eb24ae3fdb30f51b6c9f2338cd6c458458a9b67d40be43add65f3027e`. The four program blobs are recorded in `VALIDATION.json` and were read back equal to the locally executed bytes.

## Executed results

Python 3.13.5, normal and `-O`: 17 independent tests per mode, including 280 schema cells, 2,000 randomized lookup rows, 60 full-consumer cells, and malformed-route/reset cases. All 55 inherited feed/operating-stock tests pass in both baseline and candidate, in both modes. Six deliberately broken semantic variants produce assertion-only failures in each mode, with no test errors or skipped controls.

The pinned full official interpreter is Git blob `3c202c7ee921da239356789e266b694635103fc4` (SHA256 and companion-source hashes are in the runner). Each mode executes 36 constructed both-seat cases: 72 full transitions, or 144 interpreter calls including initialization. Returned proposals, reports, and complete resulting state match.

Eight uninstrumented native games cover baseline/candidate, both seats, normal/optimized Python. Two additional profiled games match those same uninstrumented traces. All 7,190 TITAN callbacks complete without fallback. The panel is only seed 17 versus the official starter using the authenticated historical `b567` package; it is not the latest all-component V4 or a competitive strength panel. Whole action and state trace digests and final rewards are preserved in `VALIDATION.json`; the runner regenerates per-step digests and callback timings.

The baseline profile executes 11,397 actor lookups, constructing crew lists with 131,590 copied action references. The candidate avoids the helper calls. Both runs still execute 48 feed-window scans, 50 feed proposals, and 84 fertilizer proposals. Neither run changes a stock reservation in this starter game. That is zero policy activation, not zero computation: the actual lookup work is observed and exercised.

## Timing and rejected approaches

Two nine-round alternating baseline/candidate full-consumer timing runs are retained in `TIMING.json`, including every measured round. The final run added 11/12-hand cells because those sizes dominate the native lookup census. Ratios below are baseline elapsed time divided by candidate elapsed time, not whole-agent speedups.

| Complete consumer | 11 hands | 12 hands |
| --- | ---: | ---: |
| Feed stock | 1.058x | 1.067x |
| Fertilizer stock | 1.149x | 1.132x |

The earlier four-hand feed cell is also retained: 0.963x, a slowdown. Small-cell timing is noisy. Large synthetic crews show larger savings, but are not representative of this native game's crew sizes. An initial conservative standalone accessor and a size-switched accessor were rejected because their guards slowed small crews. No new adaptive branch or threshold was promoted.

There is **no whole-agent speed, deadline headroom, competitive expected-value, or production activation claim**. Python 3.11/3.12 execution is NOT_RUN. Production source, feature defaults, release archive, and Kaggle submission are unchanged. A draft local runner over-rejected excess hand rows; the final runner preserves raw rows and lets the full interpreter perform admission. A transported digest typo was immediately corrected before final source readback.

## Reproduce

Recover GitHub Actions artifact `10175943272` from `woahwhattheheck/commons`. Its ZIP SHA256 is `3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8`. Use its `final-pressure-runtime` directory and `checked-package/exports/titan-current.tar.gz`; the runner authenticates the archive and all 110 file members including metadata, plus engine/loader/fixture sources before execution. It performs no downloads.

Set `UNPACK` to the extracted artifact and `PKG` to this directory, then:

```sh
set -eu
export TITAN_NATIVE="$UNPACK/final-pressure-runtime"
ARC="$UNPACK/checked-package/exports/titan-current.tar.gz"
OUT="$(mktemp -d)"
python "$PKG/check_feedpath.py"
python -O "$PKG/check_feedpath.py"
python "$PKG/check_feedpath_faults.py" --root "$TITAN_NATIVE" --output "$OUT/faults-normal.json"
python -O "$PKG/check_feedpath_faults.py" --root "$TITAN_NATIVE" --output "$OUT/faults-optimized.json"
python "$PKG/run_feedpath.py" --root "$TITAN_NATIVE" --archive "$ARC" --task engine --output "$OUT/engine-normal.json"
python -O "$PKG/run_feedpath.py" --root "$TITAN_NATIVE" --archive "$ARC" --task engine --output "$OUT/engine-optimized.json"
python "$PKG/run_feedpath.py" --root "$TITAN_NATIVE" --archive "$ARC" --task benchmark --output "$OUT/benchmark.json"

for mode in normal optimized; do
  flag=''; [ "$mode" = normal ] || flag='-O'
  for arm in baseline candidate; do
    for seat in 0 1; do
      python $flag "$PKG/run_feedpath.py" --root "$TITAN_NATIVE" --archive "$ARC" \
        --variant "$arm" --seat "$seat" --output "$OUT/$arm-$seat-$mode.json"
    done
  done
done
for arm in baseline candidate; do
  python "$PKG/run_feedpath.py" --root "$TITAN_NATIVE" --archive "$ARC" \
    --variant "$arm" --seat 0 --profile --output "$OUT/profile-$arm.json"
done

mkdir "$OUT/native-candidate"
cp -a "$TITAN_NATIVE/." "$OUT/native-candidate/"
python "$PKG/compose_feedpath.py" "$TITAN_NATIVE/operating_stock.py" "$OUT/native-candidate/operating_stock.py"
for root in "$TITAN_NATIVE" "$OUT/native-candidate"; do
  (cd "$root"; python -m unittest discover -s checks -p 'test_*stock.py' -v)
  (cd "$root"; python -O -m unittest discover -s checks -p 'test_*stock.py' -v)
done
```

For each native baseline/candidate pair, compare `trace`, `rewards`, `action_trace_sha256`, and `state_trace_sha256`. Do not require elapsed-time arrays to match. Profiled traces must additionally equal their uninstrumented counterpart. `run_feedpath.py` refuses incomplete games and any fallback; the independent test/fault commands require their exact test counts. Component work always takes the original baseline root and compares both variants, preventing a candidate-versus-itself false pass.
