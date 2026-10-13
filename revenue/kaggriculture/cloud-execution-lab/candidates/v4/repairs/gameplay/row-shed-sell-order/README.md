# V4 row-shed SELL ordering

This repair recovers the strongest unported V3.1 sale-order theorem into the sole canonical V4 workspace without importing the V3 router or creating a new controller. `repairs/gameplay/row-shed-sell-order` is the authoritative source package; the race-created `row-shed-ordering` carrier from PR #12768 is superseded and removed during consolidation rather than becoming a second implementation.

## Provenance

- V3.1 evidence commit: `7cbe552087626d09dbd8a84be8fa89efc7320ad0`
- historical router blob: `21210f396335431e81d300e118487dd859d54468`
- historical focused regression: `candidates/v3/overlay/checks/test_v31_row_shed.py`
- historical source SHA-256: `569b515c89f56a8f060ce94de218a341ae0e5b3c8e0e2c6428a8a0f08a462b05`
- historical focused-test SHA-256: `b8f81248e37078d15e767f2883c59589a670353c248c5d5eab126b58f41cabee`
- historical S34 field gate: 1,280 games per arm, 1273 W / 7 L and +540.0 margin/game against V3.0
- historical top-40 recorded replay bench: 96 W / 64 L

Those scores are historical provenance, not a V4 strength claim.

## Current-ABI contract

`RowShedSellOrder.transform(...)` consumes the current stack's already-owned `post_unit_shed` projection. It constructs no producer, invokes no parent controller, and never mutates the selected action.

Only the **engine-executable prefix** of the leading contiguous SELL block can move. The prefix length follows the official market rule: missing configuration uses the current default of 10, while an exact integer `maxMarketOrdersPerTurn` is normalized with `max(1, value)`. Bool, float, string, or other type-poisoned cap values fail closed. Within that executable prefix, each SELL row is ranked by the market-price drop caused by the units it can actually fill: `min(requested_quantity, post_unit_shed[item])`.

The first falsey row, non-SELL row, or plain-integer SELL with requested quantity `<= 0` inside the executable prefix is a hard barrier. Every market row at or beyond the executable-prefix boundary is engine-inert evidence for this transform and is preserved byte-for-byte in content and order, including truthy malformed values that the official engine never parses after prefix truncation. In particular, a high-impact SELL or malformed poison beyond the engine cap cannot enter or veto an otherwise valid executable-prefix reorder.

The transform fails closed to the caller action on missing/incomplete/type-poisoned stock evidence, malformed rows inside the executable prefix, malformed market/configuration input, invalid inventory/quote evidence, or a pricing failure. This is intentionally stricter than V3.1's incumbent requested-quantity fallback: V4 does not activate a second legacy ROW_ORDER policy when the post-unit projection is ambiguous. The expanded regression suite contains explicit divergence witnesses so that this safety decision cannot be accidentally “fixed” back into the V3 behavior.

Current ABI market parameters are passed through to the current quote function. Historical V3.1 parity remains provenance for the predecessor donor; current V4 correctness is additionally bounded by the official executable market-prefix semantics and must be judged on that engine-visible prefix rather than on inert suffix ordering.

## Pressure-novel admission

`novel_rank_guard.py` is an additive admission layer for the current V4 stack, where the already-enabled LARK market-pressure transform can independently choose a leading-SELL order. It does not construct either ranking and remains source-only pending current-stack composition/evidence.

The guard was authored as a fail-closed comparison primitive over supplied parent, row-shed, and pressure candidates. Any future composition must preserve the executable-prefix boundary above and prove novelty on the actual downstream returned action; a difference in pre-downstream rank alone is not production evidence. Missing/malformed executable-prefix evidence, cardinality drift, row/quantity changes, suffix movement in the parent-to-row-shed arm, or non-market mutation remain fail-closed conditions. Final-action bytes beyond the executable market prefix are ignored for engine-effect novelty because the engine never parses them.

This is deliberately an admission primitive rather than a new controller or a new pressure implementation. The canonical pressure transform remains the rank authority; later composition may consume it only through the single canonical graph/postimage route.

## Composition

Intended seam:

1. caller-owned current selected-action unit projection;
2. `RowShedSellOrder` using that packet's `post_unit_shed` and the official executable market-prefix bound;
3. optional pressure-novel admission against the canonical market-pressure candidate, revalidated on the same executable prefix;
4. current `SelectedActionSell` / `OrderedSelectedSell` economics;
5. existing composer/materializer;
6. final returned-action evidence proving any credited rank survives downstream transforms inside the executable prefix.

LOOM PR #12777 registered this package as `row-shed-sell-order` in the canonical composition graph. PR #12998 subsequently added the sole authenticated graph-postimage field carrier: it materializes the exact graph predecessor, overlays only the existing row-shed source bytes, and measures natural both-seat official-engine engagement with action-transparent diagnostics. That carrier is evidence-only and does not activate row-shed in production. The field carrier must be rebound to the current donor/composer identities and prefix-scoped diagnostics before it can mint new positive evidence.

Do not fork the scheduler, producer, market engine, evaluator, canonical pressure family, or canonical V4 tree to consume this repair.

## Validation

`test_row_shed_sell_order.py` retains the original current-ABI boundary contract plus a literal independent V3.1 reference implementation and predecessor validation history. Because the donor source changed to enforce the executable-prefix theorem, prior 14/14 normal, 14/14 optimized, and 1,600-case parity counts are predecessor evidence until rerun on the exact repaired source.

`test_row_shed_market_prefix.py` adds focused current-source predecessors for:

- a high-impact SELL beyond `maxMarketOrdersPerTurn` that must not enter or move the executable prefix;
- truthy malformed suffix poison beyond the cap that must neither veto nor move a valid in-prefix reorder, while the same poison inside the prefix fails closed;
- zero and negative exact-integer caps normalizing to one executable market row;
- plain-integer non-positive SELL rows acting as engine-dead ordering barriers; and
- bool/float/string cap poison failing closed to the caller fallback.

`test_novel_rank_guard.py` retains its source-only pressure-rank admission contracts, but final novelty remains gated on executable-prefix and downstream-return evidence in the sole field route.

A current official-engine/full-game both-seat economic gate remains required before any production/default activation. No queued or pending hosted run is treated as green evidence.
