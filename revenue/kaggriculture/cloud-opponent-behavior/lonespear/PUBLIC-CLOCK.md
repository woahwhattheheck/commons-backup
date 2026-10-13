# Public-clock and zero-cost hiring compatibility

This is an in-place repair of `behavior.py` in the existing lonespear model.
It changes neither the sale-timing proposal nor the shared whole-queue comparator.
It is not a second controller or release; the current canonical TITAN package
remains with its integration owner.

## Existing callable, wider valid inputs

`predict(observation, configuration=None, actor=None)` retains a supplied integer
`step`. If `step` is missing or null, it derives the step from public `day`,
`hour`, and `configuration.turnsPerDay` (default 24). An incomplete or invalid
sparse clock returns unknown, not an invented step zero. Existing explicit-step
behavior is not reinterpreted using a different configuration period.

`observed_fill(before, after, actor=..., configuration=None)` adds only the
optional configuration keyword. Each frame can use an explicit or public clock.
The same per-match configuration applies to both. Consecutive same-day frames
retain the original public hire/hand delta; skipped turns, repeats and daily
resets stay unknown. No mutable history or additional opponent input is retained.

`farmHandCostMult=0` is a valid pinned-engine configuration: its schema minimum
is zero and the actual hire cost multiplies the Fibonacci value by that setting.
The predictor now permits it. A named-source hiring request is still distinct
from a filled request; following feed direction and private stock remain unknown.

The unchanged `queue_response.evaluate_wheat_response` receives the normalized
step through its existing prediction. It invokes the same comparator at most
once, retains the selected fallback, and never selects a policy from a partial
or complete conditional comparison. No simulator, model-identification rule,
controller, timer, source exporter, or package builder is added.

## Executed evidence

Fourteen new methods pass. The original twelve model and twelve queue-consumer
methods also pass against the changed shared source. Those 24 regressions are
not new methods or a repeat of any scored panel. The prior source produces 46
assertion/subtest failures and two unsupported-keyword errors in the new suite;
these are boundary coverage counts, not 48 independent defects.

The two sparse-clock forms of the same six original development cases reproduce
all 240 complete farm/private/market state comparisons and their original action
and cash effects. Buyer gains and seller losses are both retained. Six new
configured-zero-cost prefix cases match the exact source requests and official
market hiring fills. Eighteen mixed-clock fill comparisons cover both positions.
The expired-deadline case still emits no proposal or aggregate bounds.

Only original saved cases and isolated market calls are consumed. There are no
new full games, held samples, seeds, hosted results or competitive gains here.
The initial test-development attempt used the wrong key for a no-feed cash label;
its log is retained separately. The completed test reads cash from the original
paired states and performs no reconstruction of missing observations.

## Reproduce in a cloud workspace

Use the exact inputs already delivered in
`TITAN-IRIS-Lonespear-Queue-Consumer-20260907.zip` and
`TITAN-IRIS-Lonespear-D-20260907.zip`. Their Library locators remain in the
preceding T07 delivery; no new retrieval job is needed. The companion
`TITAN-IRIS-Lonespear-Public-Clock-20260908.zip` contains the complete inputs,
licenses, before/after source and logs for this repair.

From the extracted companion archive:

```sh
export TITAN_QUEUE_SOURCE="$PWD/dependencies/queue_delta.py"
export TITAN_ENGINE="$PWD/engine"
export TITAN_LONESPEAR_SOURCE="$PWD/upstream/lonespear/main_v18.py"
export TITAN_LONESPEAR_CASES="$PWD/evidence/cases.json.gz"
export TITAN_EVALUATOR="$PWD/upstream/cloud-eval/evaluate.py"
python source/test_public_clock.py
python source/test_behavior.py
python source/test_queue_response.py
```

The test checks the original cases SHA256
`3850381a54e1fcaf0c83a7073fce53787cae03b6f246fc1027c4f6724d200077`.
Exact source/engine identities and executed test logs are recorded in
`PUBLIC-CLOCK-VALIDATION.json`. The existing model/source notices remain in force;
no upstream policy or engine bytes are modified.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
