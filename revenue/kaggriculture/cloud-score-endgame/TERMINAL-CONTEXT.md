# Terminal decision-context continuity

This changes only the existing `score_endgame.py` terminal retry path. PRISM's
PR10022 parent/action checks remain in place. POLY's producer, PORT's receipt
builder, the absolute objective, exact solver, sampler, generic `choose`, and
single-product schedule transform remain unchanged.

## Contract

A terminal draw is now bound to the current player/step, public farms, market,
town, own private state, six native economic configuration fields, and PORT's
normalized plan/scenario/receipt matrix. This includes complete actions, paired
cash, completion flags and any supplied plan/scenario/public-state bindings.
Native mapping insertion order is retained. Raw receipt-list order and cash
number spelling are normalized by the existing receipt builder. Omitted native
configuration defaults equal their explicit values. Evaluator-only top-level
observation/configuration fields and diagnostic source labels are not consumed.

An identical retry preserves the original draw and rechecks current physical
feasibility. A changed, incomplete or malformed same-decision context clears the
active commitment and cached objective, retires that key through the existing
fallback operation, and returns the current complete caller action. Returning
to the old document cannot revive or resample the retired decision. A first
incomplete call that has never drawn can still accept a later complete input.
Cancellation derived from `BaseException` continues to propagate.

This is conservative continuity checking, not a new observation-to-rollout
validator. It does not prove the first table is causal, infer hidden rival
inventory, choose better scenario probabilities, or provide a new optimization
for a changed state. A new match still requires a fresh selector instance.

## Executed evidence

Original runtime Git blob `543ab5b4536a2b9605ee4c7c69aabfb637811760`;
new runtime Git blob `c79cf08a29862525bc947f38464fc38a234dc12f`, SHA256
`1ef5836c5c0a2e5b32d6593c5c914eaf365e47d7814c160395193417a52e5a6b`.
Base checkout `8f085e155ab60a7e5732363695187f233c6de6a5` contained the original
runtime unchanged. Exact remaining source hashes are in the adjacent result.

The new actual-component suite passes 25 methods. Original source fails 16
methods / 24 assertion records including subtests, with zero errors. PRISM's
existing 13 retry methods also pass; their method bodies and assertions are
unchanged. Its isolated AST loader now includes the real context helper and
`hashlib`, and its compiled-table fixture includes the existing scenario IDs.
The unchanged POLY producer suite passes 20 methods on the new selector, with
257 conditional market cells, 30 unit snapshots and 59 full native-interpreter
comparisons. These are separate executions and scopes, not a hosted 58-test run.

The source-bound native witness uses the existing constructed lead-33 fixture
in both seats. Initially WHEAT-first has margins +4/+2 and absolute value 1.
After reducing current own cash by 3 and rebuilding the same complete action
family, the original runtime returns that old draw/certificate despite margins
+1/-1 and a fresh optimum of 1/2. The corrected runtime returns the supplied
baseline, clears its stale certificate and performs no new draw. This baseline
has margins -4/-2: the repair is contract preservation, NOT a cash or win gain.
Original and corrected witnesses each retain 8 full terminal transitions,
24 conditional producer market calls and 4 unit snapshots, separately.

No full games, seeds, policy promotion, held evidence, hosted deadline claim,
workflow change, source exporter or new spend. The exploratory 81-inventory
search found no strict baseline dominance; that negative diagnostic is retained
privately, separate from the cash-change witness and regression counts.

## Reproduce using the existing source package

Use POLY's existing private `TITAN-POLY-terminal-inputs-20260907.zip`, Library
file `file_00000000c23881f59332b623f19071b9`, SHA256
`af693707f97eea60e068a094af075255c107407c067eb82977a84a2ad74c1cd4`.
Extract once to `$P`; do not feed its evaluation-only records to runtime.
The commands below use only its existing source, dependencies and native
constructed fixture, not the private development record file.

```sh
D=revenue/kaggriculture/cloud-score-endgame
python "$D/test_terminal_context.py" --runtime "$D/score_endgame.py" \
  --consumers "$P/dependencies" --report /tmp/context.json
python "$D/test_terminal_retry.py" --runtime "$D/score_endgame.py" \
  --report /tmp/retry.json
python "$D/validate_terminal_context.py" --runtime "$D/score_endgame.py" \
  --producer-dir "$P/source" --consumers "$P/dependencies" \
  --engine-dir "$P/engine" --expect bound --report /tmp/native.json
```

For the negative control, pass `$P/dependencies/score_endgame.py` as `--runtime`
to the new context suite (expected failed assertions), or to the native witness
with `--expect original` (expected successful reproduction of the old behavior).

For the unchanged producer integration suite, copy only the existing flattened
`$P/dependencies/*.py` into a fresh temporary consumer directory, replace its
`score_endgame.py` with this runtime, then run the existing
`$P/source/test_terminal_inputs.py --loader "$P/dependencies/engine_loader.py"
--engine-dir "$P/engine" --consumers "$C" --core-file
"$P/dependencies/full_support.py" --output /tmp/producer-joined.json`.
No original archive or dependency is overwritten.

## Next consumer

T15/T08 and the already-owned causal-history input road can use the same
`make_score_selector(...).transform_terminal(...)` interface at their next
ordinary source pin. No wrapper, solver, scenario producer or running-panel
restart is needed. Keep prior source-specific evidence and selected policy
unchanged. Full before/after outputs, source and logs are retained in the
ANCHOR Library evidence package; the adjacent JSON is the compact receipt.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
