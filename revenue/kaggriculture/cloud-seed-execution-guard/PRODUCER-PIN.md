# Explicit producer snapshots in the existing compatibility CLI

`test_seed_adapter.py --producer <file>` now has a matching
`--producer-blob <full Git blob>` option. The supplied file must match that value
before its module is loaded. Omitting the option keeps the original
`78bd08b00a8b7fcf934dcf25c54ece51746a5f5e` expectation and existing behavior.
Wrong, truncated or malformed expected values do not disable the comparison.

The result always reports the actual `producer_git_blob`. For the original
producer it retains the original published commit field. For any other explicit
producer, `producer_commit` is null: the CLI validates file bytes, not their
membership in a Git commit. A caller can bind the result to its fetched source
separately. This prevents a newer result from being labeled as the old PR9961
checkpoint.

The seven `ProducerCompatibilityTests` methods and `proposal` helper are
AST-identical. The guard, market kernel and support suite are byte-identical;
there is no change to seed demand or accept/fallback behavior. Historical
COMPATIBILITY*.json files remain their original source-specific evidence.

## Run the current source join

Use the existing engine/evaluator/mechanics inputs; no download is performed:

```sh
K=revenue/kaggriculture
python "$K/cloud-seed-execution-guard/test_seed_adapter.py" \
  --engine-cache /path/to/existing/engine \
  --evaluator "$K/cloud-eval/evaluate.py" \
  --engine-loader "$K/20260907-offline-agent/evaluate.py" \
  --mechanics "$K/cloud-titan-composition/vendor/sell/mechanics.py" \
  --producer "$K/cloud-selected-seed-budget/selected_seed_budget.py" \
  --producer-blob 595c1c1692cb9dd63999b866bd9de3119fad41d0 \
  --report /tmp/current-producer.json
```

That producer is PR10246's clock-compatible source. A later edit requires its own
exact expected blob and produces its own result; do not reuse this pin for
changed bytes. `--producer-blob` is source metadata for this offline test command,
not a policy identifier or runtime capability rule.

## Focused reproduction

Ordinary `python test_producer_pin_cli.py` runs five CLI boundary methods and
explicitly skips native setup when none of the native inputs is configured.
For all nine methods, set the following paths to existing files:

```sh
export KAG_ENGINE_DIR=/path/to/existing/engine
export TITAN_PIN_EVALUATOR="$K/cloud-eval/evaluate.py"
export TITAN_PIN_LOADER="$K/20260907-offline-agent/evaluate.py"
export TITAN_PIN_MECHANICS="$K/cloud-titan-composition/vendor/sell/mechanics.py"
export TITAN_PIN_CURRENT="$K/cloud-selected-seed-budget/selected_seed_budget.py"
export TITAN_PIN_ORIGINAL=/path/to/retained/selected_seed_budget.original.py
TITAN_PIN_REPORT=/tmp/pin-checks.json python -B \
  "$K/cloud-seed-execution-guard/test_producer_pin_cli.py"
```

The original file is the PR9961 producer at the unchanged default blob above.
`TITAN_PIN_CONSUMER` optionally selects a retained consumer for the negative
control. Partial native configuration is an error, not a passing native result.

## Executed result

All nine focused methods pass with zero skips. Two methods run the seven
unchanged compatibility methods on the changed CLI, once with the original
default producer and once with explicit PR10246 bytes; both reports pass. These
are seven existing methods on two source combinations, not fourteen new tests.
The old CLI on this same new suite produces eight assertion/subtest records,
zero execution errors, across nine methods.

Eight additional producer-to-guard fixtures cover two positions, missing/null
step, and two cash regimes. Public day29/hour22 yields decision718; funded hires
preserve the 90-cash seed saving, while the 233-cash case retains the original
action when the proposal would leave 143 less cash. Input objects are unchanged.
These are bounded market fixtures using explicit rival scenarios, not full games,
new strategy evidence, universal rival guarantees or canonical-package changes.
Exact identities and log digests are in PRODUCER-PIN-VALIDATION.json; the companion
Library ZIP retains original/current source, complete reports and offline inputs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
