# PRISM: scalar pricing cost and native-contract gate

**Disposition: NO_RUNTIME_INTEGRATION.** This is executed research inside the
single canonical TITAN V4 workspace, not another agent, controller, feature key,
or production patch. Both tempting quote replacements remain experimental.

## What was built and executed

`quote_cost_gate.py` authenticates the actual `selected_sell_core.py` dependency
closure before import. It runs the complete native `optimize_lot` implementation
under four isolated quote arms: unchanged native, a live-parameter amplitude
cache, an immutable snapshot, and a closed-input precomputed quote table. It
compares every returned plan, all report fields, and the complete capacity-check
callback sequence. Local module substitutions are restored even on interruption.

`check_quote_cost_gate.py` passes **20/20 normal and 20/20 with Python -O**. Per
mode, its counted matrices include 14,319 native-versus-official scalar comparisons,
27,684 experimental quote comparisons, and 243 complete optimizer comparisons.
Four broken arithmetic implementations and three changed native source files are
rejected. Coverage includes all seven shape dispatches (including the unknown
fallback), custom parameters, rounding ties, negative inventories, the distant
EGG floor, large prices, live mutation, and closed-oracle/import cleanup.
These counts are component evidence, not games, market transitions, or field EV.

## Measured result

The fixed panel has 81 optimizer inputs: nine products, three inventory regimes,
and all three existing acceptance rules. Each arm has seven rotated timing
repetitions; cyclic garbage collection stays enabled. Per-model setup is timed.
The existing source produced only 3,036 distinct traced quote entries across the
81 models. Source, fixture and complete-output digests are in `RESULTS.json`.

| Arm | Normal optimizer speedup | -O optimizer speedup |
| --- | ---: | ---: |
| Live-parameter amplitude cache | 0.9968x | 0.9893x |
| Immutable snapshot | 0.9879x | 0.9845x |
| Precomputed quote-table ablation | 0.9909x | 1.0008x |

A value below 1 is a slower measured median. These small timing differences are
not a statistical claim of universal regression. **There is no demonstrated
whole-optimizer acceleration in this panel.** In contrast, the warm immutable
scalar microbenchmark shows about 1.77-1.92x. That primitive-only gain must not be
advertised as a TITAN speedup. Instrumented scalar quote cost is about 0.75-0.76%
of this profile; that is not an unprofiled bound or a whole-agent cost estimate.
The quote table is precomputed outside timing from baseline traces and refuses
unseen inputs. It is an ablation, not a deployable optimization or a proof of the
best possible implementation. Candidate adapter setup also remains in its timing.

The snapshot additionally fails two concrete native-contract discriminators:
changing WHEAT base 25 to 50 after construction leaves a newly requested quote
stale; and an invalid unused above-price branch fails eagerly during construction
although the native below-branch quote remains valid. Fixed immutable-fixture
parity does not repair either issue. The amplitude arm has a deliberately limited
Python-hook contract, documented in its source, and is not promoted either.

## Reproduce offline

Use the authenticated `final-pressure-runtime` directory from existing artifact
10175943272, or an exact matching native checkout. No network acquisition, workflow
dispatch, or paid compute is performed by either script. Changed source pins fail
closed rather than silently converting this receipt into current-head evidence.

```sh
ROOT=/path/to/authenticated/final-pressure-runtime
python check_quote_cost_gate.py --native-root "$ROOT" --output checks-new.json
python -O check_quote_cost_gate.py --native-root "$ROOT" --output checks-O-new.json
python quote_cost_gate.py --native-root "$ROOT" --output timings-new.json
python -O quote_cost_gate.py --native-root "$ROOT" --output timings-O-new.json
```

Run from this directory. Output files must not already exist. Python 3.13.5 was
used for the attached receipt; other interpreters need their own timing results.
`RESULTS.json` preserves the raw optimizer repetition times and summarizes the
per-product microbenchmarks. The runner emits all per-product raw repetitions.
Normal and -O runs have identical complete-output digest
`1b2e1dd44fc718d35ff70c3beabbb100ca165c4ff361018f4fdb68397aba6246`.

Exact executed source blobs: runner `5e0d656abe3abf269110376dca3a5c023bc5ad5b`,
checks `9c8af20e75e1e1194186c9e033db8c8287a1ee8e`.
Native core is `f23d3a8b5ee5e82029026e7f8f44eb36c143a5a3`; official engine is
`3c202c7ee921da239356789e266b694635103fc4`. The runner verifies all other required
pins before the corresponding imports.

## Swarm handoff

Claim: ASTRA-PRISM, #titan-kaggriculture TS1789180982.565389. Profile findings were
sent directly to MEADOW's earlier TS1789180222.658529 numeric-performance thread.
MEADOW retains `_single`/`_joint`; EVENTPATH retains `score`; CACHELIFE retains
optimizer resource lifetime. No second implementation of their loops is included.
This closes the scalar-pricing investigation; do not revive it as an abandoned
kernel-wiring demand or install either experimental arm from its microbenchmark.
No production source, default configuration, archive, workflow, or Kaggle change.
