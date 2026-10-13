# Native lifecycle traversal: tested source, cold default probes

**Disposition: source-only / unactivated. This is not a current-default speedup.**

ASTRA-PHENOLOGY is complete in the single `main:candidates/v4` workspace.
The package contains one method-pinned row-local traversal component, independent
official-engine tests, negative controls, component timings and actual native-game
evidence. No new controller, configuration key, V4 branch or production install.

## Result and scope

The original root `mechanics.py` repeatedly resolves `farm["tiles"][y][x]`.
`repair_source` binds the existing tiles, row and immutable column range locally
inside `_decay_plants`, `_daily_refresh_plants` and `_daily_refresh_animals`.
It changes no physiology: watering, fertilizer deadlines, starvation, lifespan,
production intervals, care carry and animal escape remain unchanged. It preserves
the original square-prefix traversal, row/tile aliasing, replacement order and
partial-state exceptions on wide/ragged/immutable rows. This is a plain JSON
list/dict contract, not a claim for side-effecting custom mapping subclasses.

Executed with Python 3.13.5, normal and optimized (`-O`):

- **17/17 tests per mode**; 4,353 native/official/candidate comparison triplets,
  a 720-step serviced sequence, and 120 full-interpreter paired worlds per mode
  (360 interpreter calls including initialization). The primitive reference is
  the actual pinned official module, with exact original definition comparison.
- **7/7 wrong variants assertion-rejected per mode** through seven small witnesses
  each. Covered parity, water starvation, fertilizer without watering, animal
  escape, care carry, extra-column traversal and incorrectly copied rows.
- **Eight uninstrumented native game pairs**: two seeds, both seats, normal and
  optimized. All actions, complete interpreter states, completion traces and
  rewards match; normal/optimized results also match. Two additional instrumented
  pairs cover both seats of seed 9600913. All 20 games completed: **14,380 actual
  `main.py::agent` calls**, no fallback or incomplete call, maximum observed call
  0.182 seconds. All raw extra hand rows were preserved, not truncated.

The critical negative result is **zero calls to all three root lifecycle
functions in both instrumented native probes** after step zero. Instrumentation
binds both loaded root mechanics modules; six explicit empty-farm calls per game
prove that the counters work, and those control counts are excluded. The probe
itself preserves the uninstrumented action/state hashes. Step zero is not counted
so imports are not moved outside the real first-call deadline.

Current frozen defaults disable ordered continuation, terminal route,
fourth-quadrant and spatial tempo/pathing. The remaining root spatial decay
call belongs to the optional weed-witness path. This explains why local component
medians (roughly 1.04–1.31x normal; 1.07–1.31x optimized on these workloads) are
**not native speed or strength evidence**. Keep the component source-only unless
a genuine consuming path is measured. Do not flip a policy to make a benchmark
look active, and do not add these ratios to the live optimizer stack's gains.

This gate used artifact **10175943272**, exact **b567** native foundation, not a
whole-current assembled V4 or Kaggle-hosted runner. Every pair authenticates all
109 manifest members before/after and changes only `mechanics.py` in a disposable
candidate copy. Broad baseline unittest discovery, Python 3.11, multi-repair
composition, opponent-diverse economics and hosted deadline rates are not claimed.

## Reproduce offline

Unpack the existing artifact's `checked-package/exports/titan-current.tar.gz` into
an empty directory. Set `R` to that absolute runtime path and `M` to its original
`checked-package/runtime/integrated-selected/CURRENT-SOURCE.json`. No new workflow
or Kaggle request is needed. Run these commands from this package directory:

```sh
export PHENOLOGY_RUNTIME="$R"
python -m unittest -v test_lifecycle
python -O -m unittest -v test_lifecycle
python measure_lifecycle.py --runtime "$R" --mutations --output controls-normal
python measure_lifecycle.py --runtime "$R" --mutations --optimized --output controls-optimized
python measure_lifecycle.py --runtime "$R" --output benchmark-normal.json
python -O measure_lifecycle.py --runtime "$R" --output benchmark-optimized.json
mkdir pairs
for seed in 9600913 9922031; do
  for seat in 0 1; do
    python native_gate.py --runtime "$R" --manifest "$M" --seed "$seed" --seat "$seat" --output "pairs/normal-$seed-$seat.json"
    python native_gate.py --runtime "$R" --manifest "$M" --seed "$seed" --seat "$seat" --optimized --output "pairs/optimized-$seed-$seat.json"
  done
done
for seat in 0 1; do
  python native_gate.py --runtime "$R" --manifest "$M" --seed 9600913 --seat "$seat" --count --output "pairs/probe-9600913-$seat.json"
done
```

Each native command executes one bounded pair in fresh processes. Existing result
paths fail closed. Final receipts all bind the exact published driver digest;
earlier interrupted monolithic trials were excluded and their games rerun.

## Source custody and composition

`repair_lifecycle.py::repair_source(source)` is the only source transformation.
It authenticates the three exact method bodies, rejects missing/duplicate/drifted
or already-transformed targets, and preserves all surrounding bytes. It does not
replace an entire peer module. PORTAGE/SPATIAL-COST retain transfer/geometry;
optimizer and runtime lifecycle owners retain their independent sources.

```sh
# Staging only; this command refuses an existing output.
python repair_lifecycle.py "$R/mechanics.py" /tmp/phenology-mechanics.py
```

The input Git blob is `044a4f9c0a4a44dde10ada57563238bcaf82075d`;
exact output, function and evidence identities are in [RECEIPT.json](RECEIPT.json).
The four `EVIDENCE.b64.00` through `EVIDENCE.b64.03` files encode one gzip
containing full component/negative-control logs, raw benchmark samples and all
ten final pair receipts as a JSON `files` mapping. Reconstruct it in part order
and verify the SHA256 from the receipt before unpacking:

```sh
cat EVIDENCE.b64.0[0-3] | base64 --decode > evidence.json.gz
sha256sum evidence.json.gz
gzip -dc evidence.json.gz > evidence.json
```

The reconstructed gzip SHA256 is
`fe390c4346585303118a01337943e6eb81684473a52bf677abb9dbff687593c6`.
Part-level identities are also in the receipt. This encoding is transport only,
not a second evidence set. The code and evidence are a completed reusable
component, not a queued build or activation.

Coordination claim: `#titan-kaggriculture`, timestamp `1789181913.287849`.
