# TITAN V4: observation-bounded fill reconciliation

**Status: LOCAL COMPONENT TESTED; NOT POSTED, MERGED OR RUNTIME-PROMOTED.**

Canonical integration line: `main`.
Carrier: `revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/performance/observed-fill-pruning/`.
Production target: `revenue/kaggriculture/cloud-execution-lab/reference/titan-history/observed_fills.py`.
This is a repair/evidence packet for that one workspace, not another V4 tree,
feature key, strategy, materializer, or submission.

## Exact source custody

The full predecessor was read through the connected GitHub API at commit
`200e84a569596a87e7a965fa2dce98b18a675ad7`, reconstructed into the local workspace,
and byte-verified against Git blob `cabe10ad3d683351077c9597ad7bb36cb58ce9c6`.
A later direct read of the same path on `main` returned that same blob.

Source: https://github.com/woahwhattheheck/commons/blob/200e84a569596a87e7a965fa2dce98b18a675ad7/revenue/kaggriculture/cloud-execution-lab/reference/titan-history/observed_fills.py

Materialized output Git blob: `73a402401fd4ce56469349ab1d891996b98d3fa0`.

Only `reconcile_shed_fills` changes. The transformer checks that function and
nine supporting definitions/constants before making the replacement. Unrelated
source bytes survive unchanged. Reapplying to the authenticated postimage is
idempotent. Source drift in the target or its checked dependencies requires a
fresh review; it is not silently overwritten.

## Failure recovered

With a 100-unit shed, an empty post-unit inventory, and final market rows
`BUY_PRODUCT WHEAT 100`, `BUY_PRODUCT FERTILIZER 100`, a next observation of
50 WHEAT and 50 FERTILIZER identifies both purchases in the existing relaxed
inventory model. Nevertheless, the predecessor first enumerates many impossible
intermediate stocks. Under its unchanged defaults it stops at 4,097 states /
4,198 transitions and returns `unknown: state_budget_exceeded`.

The replacement uses the already-supplied next inventory to eliminate impossible
intermediate stocks before expanding them. The witness needs one live state and
two transitions, and returns both exact 50-unit quantity ranges. No requested
purchase is treated as a fill merely because it was submitted.

## Why the pruning preserves every compatible path

After a market row, let `x` be stock of one item and `F` its observed final stock.
Let `B`, `S`, and `D` be its future purchases, future sales, and admitted end-of-day
deposits. The existing model has

```
F = x + B - S + D
0 <= B <= sum(future bounded BUY quantities)
0 <= S <= sum(future bounded SELL quantities)
0 <= D <= sum(known later deposited quantities)
```

Therefore every compatible path must satisfy

```
max(0, F - B_max - D_max) <= x <= F + S_max.
```

These are necessary coordinate bounds, not sufficient joint-state claims.
The original ordered stock transitions, shared capacity, exact SELL truncation,
99,999-unit per-row ceiling, and ordered end-of-day deposit admission still run.
Only states/quantities outside the necessary bounds are skipped. For histories
merged into the same stock vector, future possibilities depend on that stock,
not the path's prior fill vector; pruning cannot selectively lose a compatible
prior fill-vector bound.

Purchase-free queues skip bound construction. Genuine ambiguity remains:
`BUY WHEAT 100 -> SELL WHEAT 100 -> observed empty` still yields correlated
0..100 ranges for both rows. Neither endpoint is converted into a cash receipt,
a joint fill vector, or a rival prediction.

## Validation executed

The checker loads the full externally supplied original module and a fresh
materialization of the replacement. Its independent test oracle uses individual
paths rather than the production parser, merged states, or pruning helper.

- 34/34 checks in normal Python, and 34/34 with `python -O -B`.
- 6,156 exhaustive small-state cases and 4,000 seeded random cases in each mode;
  all agree three ways on status, per-slot ranges, compatible final states and
  other semantic receipt fields whenever the predecessor completes.
- Source/dependency drift, idempotence, preservation of unrelated source bytes,
  malformed inputs, raw suffix slots, parser coercions, zero configured slots,
  per-row limits, initial over-capacity, end-of-day deposit order, true ambiguity,
  retained state/transition limits, both player seats, detached action bindings,
  duplicate observations and nonadjacent observations are covered.

Computational counters may shrink. Some budget-exhausted predecessor inputs can
now produce valid receipts; budgets themselves have not increased. Unknown
input/deposit evidence still produces unknown results. The output carries no
cash receipt or non-shed acquisition inference.

## Controlled workload results and cost trade-off

These are synthetic local component measurements, not game-score evidence.

| Workload | Original transitions | Replacement transitions | Original / replacement median time |
| --- | ---: | ---: | ---: |
| Two uniquely observed buys | 4,198, then unknown | 2, exact | 132.428x |
| One uniquely observed buy | 101 | 1 | 5.964x |
| Three uniquely observed buys | 4,198, then unknown | 3, exact | 105.395x |
| Buy, sell, correlated buy | 4,078 | 53 | 43.141x |
| Genuine buy/sell ambiguity | 202 | 202 | 0.810x |
| Sale-only queue | 2 | 2 | 0.959x |
| Saturated deposit ambiguity | 101 | 101 | 0.967x |

The genuine-ambiguity case was about 24% slower, the sale-only case about 4%
slower, and saturated-deposit ambiguity about 3% slower. There is no blanket
speedup claim. The complete inputs, outputs, clock measurements, and methodology
are in `BENCHMARK.json`. Actual V4 callback and match distributions are needed
before deciding whether to promote this optimization.

## Reproduce from repository root

```sh
ROOT=revenue/kaggriculture/cloud-execution-lab
PKG=$ROOT/candidates/v4/repairs/performance/observed-fill-pruning
SOURCE=$ROOT/reference/titan-history/observed_fills.py
python "$PKG/test_observed_fill_pruning.py" --baseline "$SOURCE"
python -O -B "$PKG/test_observed_fill_pruning.py" --baseline "$SOURCE"
python "$PKG/benchmark.py" --baseline "$SOURCE" --receipt /tmp/fill-pruning-benchmark.json
python "$PKG/repair_observed_fill_pruning.py" --source "$SOURCE" --output /tmp/observed_fills.pruned.py
```

Use a fresh output path. The transformer never writes directly over its input.
The packet does not execute a legacy r04 materializer, change feature defaults,
modify an evaluator, submit to Kaggle, or force-move any ref.

## Remaining integration gates

This session had read-only GitHub/Slack actions. Slack initially yielded live
messages, then channel/thread/search refreshes repeatedly returned HTTP 429.
No Slack claim or handoff was sent, and no GitHub write or merge occurred.
The later `main` performance-repair directory listing contained fast-tape-clone,
its fold helper, and s1-exact-route, but no observed-fill-pruning carrier. That
listing is not proof that no peer holds an unpublished claim.

Before any landing, the active integrator must check live claims and exact current
source, retain this single canonical carrier, and perform the usual source
review. Runtime promotion additionally needs full current-V4 receipt-consumer
integration, representative deadline/callback measurements, and paired match
validation. Official-interpreter validation, full-V4 materialization, matches,
ratings, production archive regeneration and Kaggle upload were NOT RUN.
