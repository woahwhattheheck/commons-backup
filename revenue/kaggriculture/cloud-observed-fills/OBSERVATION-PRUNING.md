# Observation-constrained purchase reconciliation

The existing `reconcile_shed_fills` now discards purchase branches that cannot
match the supplied next own inventory. The public call signature, ledger,
quantity-verdict helper, parser, output schema and cash-unknown contract are
unchanged. Only that one runtime function changes; ten other top-level
function/class definitions are AST-identical to the original.

## Necessary condition, not a price or affordability model

Let `s` be a product's current quantity during a candidate own-stock path. If
its last effective stock-changing market order is a BUY, and no positive
post-market deposit can add that product, then its next observed quantity `z`
requires that last buy to fill exactly `z - s`. The search retains that quantity
only when it also obeys the original request, shared-capacity and iteration
ceilings. No feasible path to `z` is removed by this necessary condition.

The test is built lazily at the first purchase. SELL-only queues retain their
original simulation work. Earlier purchases, repeated same-product orders,
buy/sell round trips and positive same-product automatic deposits keep their
existing uncertainty. In particular, end-of-day capacity clipping can conceal a
smaller purchase; the optimization does not infer it away. Truncated or invalid
orders do not become effective updates. All subsequent ordered capacity checks
and final-shed comparisons remain in place.

With sufficient budget the semantic result is unchanged. Work counters can be
smaller. With the same bounded budget, an earlier `unknown` can now become a
complete exact or ambiguous answer. Cash receipts remain null; the underlying
purchase model is still a superset rather than proof of affordability. Marginal
fill intervals remain correlated.

## Executed result

The changed-path suite passes **28 methods**, including **6,000** deterministic
mixed-queue comparisons and **2,176** separately enumerated small-model cases.
Every complete semantic result matches the original implementation. Its **98**
constructed official-market cases also retain the actual per-slot fills, and
every traced complete state matches its uninstrumented control. The existing
**32-method** suite passes on the same source, including its separate **42**
market cases and controls. These are component tests, not game outcomes.

The original source fails nine new work-budget/coverage expectations, with no
execution errors. Four deliberately unsound local controls fail all five of
their targeted checks: ignoring deposits, using the first rather than last
update, ignoring shared capacity, or ignoring the request ceiling. Their exact
sources and logs are retained in the delivery package.

The old budget fixture used a single buy with observed final quantity zero;
that quantity now has a direct answer. The fixture instead uses a genuine
BUY/SELL round trip. Both original budget assertions remain unchanged and pass
on both original and improved implementations. No test is skipped or removed.

The constructed WHEAT40/FERTILIZER60 witness changes from unknown after **4,198
transitions** to exact after **two**. It is a relaxed-model witness, not a claim
that those fills occurred in a real game. A separate actual high-cash market
case in both seats buys WHEAT100/FERTILIZER0 and demonstrates the same bounded
coverage improvement.

Nine alternating-order microbenchmark rounds retain both benefits and costs.
The large two-buy input takes a median 2,307.084 microseconds before versus
13.569 after; the old default result is incomplete, so this is not a comparison
of equally complete answers. A small terminal purchase takes 12.469 versus
9.899 microseconds. The unchanged-ambiguity round trip takes 24.331 versus
26.468, and a deposit-obscured purchase takes 15.716 versus 19.881. SELL-only
work counts and outputs are identical; its timing samples are not evidence of
an algorithmic speedup. These are constructed call costs, not whole-agent
speed, a natural incidence rate, or greater playing strength.

`PRUNING-RESULTS.json` binds the source and retained reports. The complete raw
case reports, both benchmark checkpoints, original failure log, mutation
controls and unchanged engine inputs are preserved in the delivery ZIP.

## Reproduce without a new source export

From a normal repository checkout, recover the existing original source:

```sh
git show e3ab46552c7a6cd8f22d40a1d1007423a0d18ee3:revenue/kaggriculture/cloud-observed-fills/observed_fills.py > /tmp/original_observed_fills.py
LAB=revenue/kaggriculture/cloud-execution-lab
FILL=revenue/kaggriculture/cloud-observed-fills
python "$FILL/test_observation_pruning.py" \
  --baseline /tmp/original_observed_fills.py \
  --engine-loader "$LAB/reference/evaluator/loader.py" \
  --engine-cache "$LAB/reference/engine" \
  --report /tmp/pruning-results.json --benchmark
python "$FILL/check_observed_fills.py" \
  --engine-loader "$LAB/reference/evaluator/loader.py" \
  --engine-cache "$LAB/reference/engine" \
  --json-output /tmp/fill-compatibility.json
```

The local run used the exact same engine from existing artifact10005621438 and
its unchanged loader. The test checks the pinned engine hashes before loading.
Official source is Kaggle/kaggle-environments commit
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`, Apache-2.0. This component adds no
vendor source, workflow, controller, source export or game seed.

ASH's continuation consumer and CEDAR's history consumer can use the same
import. The canonical builder retains the single release; its vendored source
and current archive have not been changed by this component delivery. A later
normal incorporation needs its own archive identity and consumer result; old
frozen panels are not evidence for the new bytes.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
