# Observed-state copy cost in the existing queue consumer

This changes `queue_delta.py` in place. It does not add a policy, public API,
simulator, wrapper, canonical release, or new experiment. The actual consumer is
IRIS's `evaluate_wheat_response` from `cloud-opponent-behavior/lonespear/`.

## Change

Only `_view` and the three initial state-copy sites use `_snapshot_copy`.
Exact built-in dictionaries, lists, and JSON scalar values take a smaller
recursive traversal. Other types use the existing `copy.deepcopy` with the same
memo. This retains subclasses' hooks, repeated references, cross-path aliases,
cycles, dictionary traversal order, source lifetimes, and detached output.
The initial farm/private pair is copied together, preserving shared references.
Market calls, order copying, report fields, budget/deadline checkpoints and
fallback/action-selection behavior are unchanged. The prior snapshot-reuse
optimization remains intact. No global dispatch table is modified.

## Actual consumer workload

Inputs are the six already-retained decision697 cases from IRIS's public-clock
package, plus their existing no-feed interventions. Rival private values are
explicit **offline test fixtures**, never inferred runtime observations. No
controller, game, fresh seed or new scenario family is executed.

Each measurement is the complete warm `evaluate_wheat_response` call, including
its proposal, two scenario comparisons and full report creation. Imports,
serialization, complete actors, hosted timing and game strength are not measured.
There are31 alternating before/after pairs per case (186 total); every timed
report matches after excluding only the comparator's elapsed-time field.

| Retained case | Before median (ms) | After median (ms) | Reduction |
|---|---:|---:|---:|
| 9881001 / position0 | 4.3438 | 3.4715 | 20.08% |
| 9881001 / position1 | 4.4364 | 3.5038 | 21.02% |
| 9881019 / position0 | 4.1390 | 3.2870 | 20.59% |
| 9881019 / position1 | 4.2379 | 3.4128 | 19.47% |
| 9881037 / position0 | 4.2917 | 3.4104 | 20.54% |
| 9881037 / position1 | 4.2862 | 3.4194 | 20.22% |

The sum of case medians falls25.7350 to20.5049ms (20.32%). These are repeated
runtime measurements on six retained inputs, not independent economic samples.
The raw sample arrays, first profile and original logs are preserved in the
Library evidence package named below; `state-copy-results.json` is the compact
source-bound result. The profile motivated this change but overlapping cumulative
costs are not added together as independent timings.

## Correctness and integration

21 new methods pass:49 exact original/candidate report comparisons and144
independent complete official `_process_market` reference calls. Tests cover
sparse clocks, configured free hires, repeated orders, unknown inputs, input/output
isolation, exact-type fallbacks, custom hooks and exceptions, list/dict cycles,
partial deadlines, checkpoint counts and foreign cancellation identity. An exact
ordinary `_view` witness refuses the generic traversal on the candidate and
intentionally distinguishes the original implementation.

The unchanged IRIS suites also run once on the changed comparator:12 model,
12 queue consumer and14 public-clock methods,38/38 passing. Their original
source-specific receipts remain unchanged; this is a new composed-path result.
The initial compatibility invocation omitted the evaluator path and failed setup;
its log is retained separately from the corrected complete38-method run.

## Source and reproduction

Baseline is PR10035 / merge`4dcda7adbbca5187303a8161b7774a263954c03c`,
`queue_delta.py` Git blob`b95dff0010cf70941cc96e7f416798d36a8aa57d`.
Input Library file is `TITAN-IRIS-Lonespear-Public-Clock-20260908.zip`,120853B,
SHA256`d4ebe8529e2e712b5df4fce97b2e5c9d763252783a51657269a8d9468987f23b`.
Its existing consumer, behavior, cases and engine hashes are recorded in the
result JSON. Engine is the Apache-2.0 official source at
`Kaggle/kaggle-environments@28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`.
No vendor source or license is replaced.

Extract the existing IRIS package into`$IRIS`. The test needs no network or new
package installation. Its baseline is already supplied at
`$IRIS/dependencies/queue_delta.py`:

```sh
D=revenue/kaggriculture/cloud-market-queue-delta
python -B "$D/check_snapshot_copy.py" \
  --baseline "$IRIS/dependencies/queue_delta.py" \
  --iris-package "$IRIS" --report /tmp/state-copy.json \
  --benchmark-samples 31
```

For compatibility:

```sh
cd "$IRIS/source"
TITAN_EVALUATOR="$IRIS/upstream/cloud-eval/evaluate.py" \
TITAN_QUEUE_SOURCE="$QUEUE/queue_delta.py" \
TITAN_ENGINE="$IRIS/engine" \
TITAN_LONESPEAR_SOURCE="$IRIS/upstream/lonespear/main_v18.py" \
TITAN_LONESPEAR_CASES="$IRIS/evidence/cases.json.gz" \
python -B -m unittest -v test_behavior test_queue_response test_public_clock
```

`$QUEUE` is the absolute path to this comparator directory. Full source, exact
baseline and original IRIS package, raw samples, profile and both compatibility
attempts are saved as`TITAN-QUEUE-observed-state-copy-20260908.zip` in Library.
This is optional consumer performance work; the canonical TITAN package/default
and the owners' current upload/evaluation checkpoint are untouched.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
