# STOCKBRIDGE: one native stock composition and its executable gate

## Result and boundary

This contribution consumes STOCKPORT's exact FERT-prefix port, PASTURE's exact
feed-harvest repair, and HERON's exact terminal-feed gate. It adds test tooling to
this existing canonical V4 package; it does not add another controller, feature
key, production installer, successor branch, or submission archive.

The source composition is **prefix first, harvest second**. The first transform
requires the original whole helper; the second authenticates only `_feed_window`
and preserves all prior FERT edits. Original `781aa90d` becomes `a353e122`.
The existing method-scoped runtime port produces `a43339a1` from `b952c9c2`.
Other runtime bytes are preserved, not silently certified as equivalent.

HERON is a separate, explicit test-run experiment. `StockProbe` calls the exact
gate with the actual feed consumer's input, which already contains prior FERT
reservations. The release must restore that **post-FERT input**, never the original
parent action. Shadow mode returns the exact delegate action/report objects;
feature-OFF produces no stock calls. Installation is process-local and restores
both original functions even after an exception. No runtime key is installed.

## Executed evidence

Both normal Python and `python -O` passed **55 inherited stock tests plus 20 new
independent tests**. Each mode executes 180 mixed raw-slot cases, 182 paired
full-interpreter examples (4,732 interpreter calls including initialization), and
rejects seven broken variants by behavioral assertions, not merely hash errors.
Counts overlap across test categories and are not games. The synthetic native
hook tests use controlled controller/receipt collaborators; they are not complete
production-agent executions.

A wrong pre-FERT restore destroys one STRAWBERRY yield on each of two targets,
for both seats and all 90 distinct FERT/WHEAT slot positions per seat. Correct
post-FERT restoration retains both yields. A separate harvest witness preserves
FERT protection while two harvested wheat cover the same feeds; unnecessary
wheat retention costs **78 cash in this fixture's market**, not the 46 cash of the
source owner's different fixture. Neither is a measured full-game advantage.

The separate full-agent panel executes the archived **actual `main.py::agent`**
with its normal deadline and final-pressure boundary, unchanged configuration,
and the pinned official interpreter. It preserves surplus hands, empty orders,
and over-cap suffixes exactly; there is no driver-side action trimming.

There are **18 complete games, 12,942 completed native callbacks, zero deadline
fallbacks**: two seeds (2027, 9922023), both seats, baseline-shadow versus
composed-shadow versus composed-release (12 games), two plain observer controls,
and four explicit feature-OFF test controls. All matched complete action/state
trace hashes and scores are identical. In the four composed-release games there
are 186 feed and 360 FERT calls, four feed calls during steps 672-694, but **zero
changed stock reservations and zero terminal-gate matches**. This is no-engagement
evidence, not permission to enable the terminal gate or a claim of stronger play.

The opponent is only the pinned official starter. Inputs come from existing
artifact **10175943272**, `final-pressure-runtime`; 110 files including metadata
are hashed. This directory is not represented as latest-main/all-lane source.
Source/archive early-capital and SELL differences remain outside this receipt.
The unrelated broad old-artifact discovery failures are not cleared. The source
owners' separately reported 39/25/13 test suites are not counted as our reruns.

## Files and source custody

`stock_bridge.py` consumes the three original files in their existing sibling
packages with exact Git-blob checks. `test_stock_bridge.py` provides independent
mixed-input/native/engine assertions. `check_stock_bridge_mutants.py` runs each
broken composition in a fresh interpreter. `check_stock_bridge_games.py` runs
one isolated full game and records exact source hashes, returned-action windows,
helper calls, completed status and action/state trace digest.

`STOCK-BRIDGE-RECEIPT.json` binds code and scope. `STOCK-BRIDGE-RESULTS.json`
contains all 18 compact actual game records (shared fields and per-cell digests),
raw unit-log tails, all 14 mutant outcomes and truncated assertion prefixes. Full-game traces are
represented by digests, not replay frames. Complete helper telemetry, the full
source map and returned-action windows are reproduced by the checked-in runner;
they are not embedded in this compact record.

## Reproduce without changing production

Use the already-existing artifact; no workflow dispatch or Kaggle operation is
needed. Set `BASE` to its extracted `final-pressure-runtime`, and `GAMEPLAY` to
this checkout's `candidates/v4/repairs/gameplay`. Choose an unused directory
outside the production checkout for `COMPOSED` and an existing empty `RESULTS`
directory. For example:

```sh
export BASE=/tmp/titan-artifact/final-pressure-runtime
export GAMEPLAY="$PWD/revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/gameplay"
export TOOLS="$GAMEPLAY/operating-stock-prefix"
export COMPOSED=/tmp/titan-stockbridge-test-copy
export RESULTS=/tmp/titan-stockbridge-results
mkdir "$RESULTS"
PYTHONPATH="$TOOLS" python - <<'PY'
import os, shutil
from pathlib import Path
from stock_bridge import compose
base, out = Path(os.environ['BASE']), Path(os.environ['COMPOSED'])
stock, runtime, receipt = compose((base/'operating_stock.py').read_bytes(),
                                (base/'titan_runtime.py').read_bytes())
shutil.copytree(base, out, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
(out/'operating_stock.py').write_bytes(stock)
(out/'titan_runtime.py').write_bytes(runtime)
print(receipt)
PY
export STOCKBRIDGE_SOURCE="$BASE" STOCKBRIDGE_COMPOSED="$COMPOSED"
for mode in '' '-O'; do
  PYTHONPATH="$COMPOSED:$COMPOSED/checks:$TOOLS" python $mode -m unittest test_operating_stock test_feed_stock
  python $mode "$TOOLS/test_stock_bridge.py"
  python $mode "$TOOLS/check_stock_bridge_mutants.py" --source "$BASE" --composed "$COMPOSED"
done
for seed in 2027 9922023; do
  for seat in 0 1; do
    for spec in 'baseline shadow' 'composed shadow' 'composed release'; do
      set -- $spec
      python "$TOOLS/check_stock_bridge_games.py" --source "$BASE" --seed "$seed" --seat "$seat" \
        --variant "$1" --probe "$2" --output "$RESULTS/$seed-$seat-$1-$2.json"
    done
  done
done
for seat in 0 1; do
  python "$TOOLS/check_stock_bridge_games.py" --source "$BASE" --seed 2027 --seat "$seat" \
    --variant baseline --probe plain --output "$RESULTS/2027-$seat-baseline-plain.json"
  for spec in 'baseline shadow' 'composed release'; do
    set -- $spec
    python "$TOOLS/check_stock_bridge_games.py" --source "$BASE" --seed 2027 --seat "$seat" \
      --variant "$1" --probe "$2" --stock-off --output "$RESULTS/2027-$seat-$1-$2-off.json"
  done
done
python - <<'PY'
import json, os
from pathlib import Path
raw = json.loads((Path(os.environ['TOOLS'])/'STOCK-BRIDGE-RESULTS.json').read_text())
print('Stored full-game results:', len(raw['games']))
print('Source files hashed:', raw['source_file_count'])
PY
```

The current shared native composer owns wider integration. Consume these exact
source owners in the stated order and rerun on its final dependency set. Do not
reset a newer helper to the archived baseline, bypass the source checks, execute
the legacy r04 materializer, or infer an activation recommendation from synthetic
witnesses or an inert starter panel. This source/evidence claim is complete, not
an orphaned build demand.
