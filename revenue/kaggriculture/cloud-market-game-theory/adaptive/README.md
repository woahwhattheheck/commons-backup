# Adaptive complete-plan recourse

This executable T15 experiment consumes the current integrated selected parent
from PR9997 and the existing ASH continuation consumer. `AdaptiveTransform`
constructs no production controller. `Agent.act` calls one
`IntegratedSelectedAgent` and passes its action and current projection ledger
to the transform. The original T15 v1/v2 files and selected SELL are unchanged.

`compile_policy(model, plans, quantity, streams, branch, absorption)` requires
complete feasible plans with an identical executed prefix. It groups whole
correlated streams by shared product inventory at the future branch. Grouping
is intentionally coarse: ignored public fields retain additional hypotheses;
equal inventory never identifies rival cash receipts, exact quantity or slot.
Only the real next observation selects a suffix. Unrepresented observations
return the entire supplied fallback. Floor-price nonadmission stays grouped.

Each information set selects a row only if every included relative margin is
nonnegative, then maximizes its minimum and sum. Baseline wins exact ties.
This is an explicit weak-dominance objective. The sum is a deterministic
tie-break, not a probability-weighted expectation. Alpha remains zero. The
finite conditional bound applies to included complete streams and complete
execution, not every possible opponent or an individual full-game promise.

Current constituent and continuation feasibility comes from the existing
selected-action `ProjectionLedger`, including ordered cash, stock, production
arrivals, committed capacity, operating resources and order slots. ASH retains
its existing retry/skipped-date behavior. Previously emitted prefixes remain
unchanged; the selected suffix persists. Other products and unit fields are
preserved. Future route changes can retire a commitment to the supplied action.

## Final measured result

`RESULTS.md` and `RESULTS.json` retain all 104 new attempts, 102 complete.
The 48-game broad development panel is 10W/2L for the integrated control and
12W for each fixed/static/adaptive arm. All three flip both SELL losses; the
adaptive arm has no extra win flip over its ablations. On the separate held
seed, baseline/fixed/static each have 10W/2L. Adaptive has 8W/2L and two
candidate-side games ending at the RPC deadline against COK. These are kept
incomplete with null final scores, not assigned invented wins or losses.
No held win improvement or default promotion is established.

Four conditional engine tables retain 4,068 serialized transitions; one uses
the reached WOOL admission's actual public parameters and own slot. Eighteen
recorded development comparisons have identical full observations and trees
but different adaptive versus fixed/static market actions; all non-market
fields match. `CAUSAL-ATTRIBUTION.json` links those existing receipts.

The official raw loader supplies `configuration['__raw_path__']` when it does
not set `__file__`. The three entrypoints now use that source path. Six fresh
process calls match the evaluator, maximum cold setup plus call264.89ms. The
original entrypoint remains preserved. `HELD-FREEZE.json` records the source
before held execution; no decision tuning followed its outcomes. Current
`report.py` retains null final scores for incomplete episodes; its earlier
frozen version also remains preserved.

Production entrypoints are `main.py` (adaptive), `fixed_main.py` and
`static_main.py`. They return ordinary actions without evaluator metadata.
The entire existing repository dependency layout is required; no extra source
bank export or duplicate standalone archive was created.

## Executed development checkpoint

The initial 386 single-burst cases found no adaptive advantage. Three later
constructed EGG cases with correlated two-burst streams match 3,456 serialized
official transitions in both seats. For EGG2 at inventory9998 with BAKERY and
BRUNCH_SPOT, the baseline sells at249. At the real observation242, inventory
10000 selects one sale now and one at249. Its 32-column causal vector is zero
except +1/+2 on two correlated paths; every static alternative has a losing
column. The same public observation with different simulator-private stock
produces the same decision. An unknown inventory takes the entire fallback.

Fresh development9943001 has eight completed full games, both seats versus
frozen SELL. The current integrated control scores103532 own/103443 rival.
The fixed-plan arm scores103531/103444; static weak dominance and adaptive each
score103531/103449. All remain wins. At reached step656, the adaptive arm
selects WOOL2 for661 from new shared inventory9906. That is an executed economic
selection, but this seed provides no improvement over the static arm and loses
relative cash against the integrated control. Preserve all four arms.

The initial discovery runtime is preserved byte-exact in
`versions/discovery/runtime.py`; its manifest records all original source hashes.
The next revision changes diagnostic weights and counts projection fallbacks
separately from active-plan retirements; decision logic is unchanged. Six
focused tests cover the explicit objective and the actual ASH/selected-action
integration. The old T11/T12/T15 panels and peer suites were not rerun.

The existing public bank artifact10032525998 was reused for the broad
development and held comparisons, not exported again. The preceding eight-game
checkpoint is preserved separately from the final results. Exact game receipts
are under `results/`.

## Call and reproduce

With the repository-relative dependencies present, `main.py::agent` is the
production entrypoint. Construction and imports occur inside the first call.
The callable economic transform is
`AdaptiveTransform.transform(obs, cfg, supplied_action, ledger=..., offers=...)`.
An offer contains `tree`, `item`, `quantity` and `end`; the compiled tree retains
every original plan and column index. The ledger is the caller's current
`selected_action_sell.ProjectionLedger`, not a second producer.

```sh
python revenue/kaggriculture/cloud-market-game-theory/adaptive/test_recourse.py -v
python revenue/kaggriculture/cloud-market-game-theory/adaptive/panel.py \
  --engine-dir /path/to/engine --opponents /path/to/opponents.json \
  --seeds FRESH_AGREED_DEVELOPMENT_SEED --arms baseline,fixed,static,adaptive \
  --output /path/to/new-results
```

The opponent file maps names to existing runnable entrypoints. Evaluation-only
metadata is removed by the parent Actor before the official interpreter. All
market actions received by the engine are ordinary game actions.

New implementation is Apache-2.0 under the repository LICENSE. T12 flow/scenario
source remains MIT in its original directory; ASH, integrated SELL, producer
dependencies and their original licenses/notices remain in their owned paths.
No upstream source or license was copied into this component or reclassified.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
