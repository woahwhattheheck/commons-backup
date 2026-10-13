# LIVEPATH: active projection-state copying

One candidate-only component in `main:revenue/kaggriculture/cloud-execution-lab/candidates/v4`.
No second V4, controller, feature key, production edit or release archive.

## What was built

An actual 719-callback `main.py::agent` profile located active copy work in
`represented_shed_event` and `early_capital._project_post_unit_private`.
`projection_clone.py` specializes exact builtin dict/list copying while retaining
memo lookup, alias/cycle topology, dictionary key/value copy order, original-object
lifetime and real `deepcopy` fallback for subclasses/foreign objects. Separate farm
and private copies deliberately use separate memos, as the predecessor did.
This is **not** the existing JSON-normalizing observation clone or action-tape clone.
Standard builtin `copy` dispatch is assumed; monkeypatching its private tables is
outside this component's contract. Python 3.13.5 was executed; 3.11 was not.

`compose.py` authenticates complete method spans, then changes only their two copy
sites. It preserves every byte outside those spans and adds a pinned helper. It
accepts the original event function and its exact UNITFLOW postimage. Unrecognized,
decorated, duplicated or already-modified methods fail closed. CLI output must be a
new directory; source/helper validation precedes creating it. No defaults, actions,
market admission, clocks, economic objectives or history commits are rewritten.

## Executed evidence

* 23/23 own tests in normal Python and 23/23 with `-O`, including 500 generated
  alias/cycle graphs per mode. Eight deliberately incorrect helpers are rejected
  by behavioral assertions in each mode, with zero error-only credit.
* 90 inherited early-capital, funding, joint-market, crop-release and feed-stock
  tests pass in **each** of four arms (baseline, copy repair, UNITFLOW, combined)
  in both modes. Six missing and six altered native dependencies are rejected
  per mode; altered SOURCE and helper pins also fail before execution.
* 32 completed full games in the formal receipt, 23,008 actual native callbacks,
  23,040 complete interpreter calls including initialization. Every call completed;
  zero fallback. Sixteen candidate runs match a source/mode/seed/seat parent in
  complete raw-action and full-observation/reward/status trace hashes. Both seats,
  seeds 17/9922999, normal/optimized and UNITFLOW-composed checks are represented;
  this is not a fully crossed 32-cell panel. Twelve games are timing repetitions.
* Separate instrumented native games prove engagement: seed17/seat0 calls the new
  copier 670 times from represented events and 426 from early capital. The combined
  optimized seed9922999/seat1 game calls it 632 and 420 times respectively, with
  identical uninstrumented-parent traces. These runs are excluded from timings.
* Six serial alternating-order, uninstrumented timing pairs (seed9922999, seat0)
  reduce summed agent wall time in all six pairs: median paired reduction **1.42%**,
  range **0.48% to 4.20%**. All totals are retained in `VALIDATION.json`.
  An earlier seed17/seat1 comparison was slower. This small local result is not a
  universal speedup, competitive-strength gain, or deadline-rescue claim.

`PROFILE.json` contains measured call attribution, not a speed benchmark. The
formal profiler preserves the requested seed separately from the engine's consumed
configuration field and verifies `env.info.seed`. A preliminary exploratory profile
had a null displayed configuration seed; it is not the formal receipt source.

## Reproduce offline

Recover existing Actions artifact **10175943272**, run **34537404363**. Set `PKG` to
its `final-pressure-runtime` directory. `run_native.py` authenticates the exact
SOURCE manifest and **all 109 runtime members** before copying/importing anything.
The checked archive in the same artifact has SHA256
`b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`.
Do not substitute moving source HEAD or run the old R04 materializer.

From the repository root:

```sh
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
HERE=$V4/repairs/performance/projection-state-clone
UNIT=$V4/repairs/runtime/joint-unit-projection/compose.py
python "$HERE/test_projection_clone.py" --package "$PKG" --unitflow "$UNIT"
python -O "$HERE/test_projection_clone.py" --package "$PKG" --unitflow "$UNIT"
python "$HERE/run_controls.py" --package "$PKG" --unitflow "$UNIT" --output /tmp/livepath-mutants.json
python -O "$HERE/run_controls.py" --package "$PKG" --unitflow "$UNIT" --output /tmp/livepath-mutants-opt.json
python "$HERE/compose.py" --package "$PKG" --output /tmp/livepath-source
python "$HERE/run_native.py" --package "$PKG" --arm base --seed 9922999 --seat 0 --output /tmp/livepath-base.json
python "$HERE/run_native.py" --package "$PKG" --arm clone --seed 9922999 --seat 0 --output /tmp/livepath-clone.json
python "$HERE/run_native.py" --package "$PKG" --arm unitflow-clone --unitflow "$UNIT" --seed 9922999 --seat 1 --count-clones --output /tmp/livepath-engagement.json
python "$HERE/run_timing.py" --package "$PKG" --output /tmp/livepath-timing
```

Native runner options `--profile`, `--count-clones`, `--seed`, `--seat` and the four
source arms reproduce the individual checks. Every result retains source hashes,
engine/config/seed identity, complete trace hashes and all per-callback timings.
The published receipt retains every complete-game total and original-result hash;
full per-callback output files were not uploaded. No timed sample was filtered.
`make_receipt.py` rebuilds the compact receipt from the formal run directory,
rejecting incomplete/fallback games, baseline self-disagreement and changed actions,
states or scores. It expects the six named timing pairs from `run_timing.py`.

## Composition and disposition

The exact existing UNITFLOW composer is blob
`e1127c4aad842278a9e617903b0718d21c00f348`. Source tests prove both source orders
commute byte-for-byte and preserve the atomic PLANT gate. No UNITFLOW code is
republished or replaced here. This component leaves FUNDING-PERF, selected snapshot,
QUARRY observation normalization, TAPEPORT action cloning and WEAVE optimizer math
untouched. CLEARING's newer represented-market admission and MOSAIC's horizon work
need an explicit fresh same-method composition when their event method changes;
**do not relax pins or overwrite those semantics with an old full file**.

Disposition: **ready source component for the existing single V4 composer**, not
activation of a finished V4. Only official-starter games were run. Current combined
V4, competitive opponents, constrained-deadline interruption and hosted CI were not
certified. Production/default/archive/Actions definitions/Kaggle remain unchanged.
The executed engine reward 190,363 versus 3,550 also refutes the proposed 65,000
margin cap; that correction was sent directly to the swarm without changing score
analysis policy in this patch.
