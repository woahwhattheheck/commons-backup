# GRAINDEBT — WHEAT sale / feed-stock causal audit

Status: **DIAGNOSTIC-ONLY / NO POLICY MUTATION / CURRENT-V4**.

This extends the existing `operating-stock-prefix` evidence family. It does not create another seller, feed controller, V4 tree, feature flag, default, archive, workflow, or Kaggle candidate.

## Why this lane exists

The current canonical runtime already protects some WHEAT from returned `SELL` rows for physically reachable planned FEED obligations. Production configuration has `operating_stock=true`, and the final returned-action path invokes `_feed_stock_selected()` after crop/idle composition. A generic “reserve feed before selling wheat” repair would therefore duplicate active V4 behavior.

The exact current `protect_feed_stock()` source has a narrower unresolved boundary:

```python
permitted = min(stock, max(0, stock + returned_wheat - required))
withheld = max(0, min(stock, offered) - permitted)
if withheld > 2:raise ValueError('feed_reservation_exceeds_two_units')
```

The helper catches that exception and returns the original selected action. Thus a certified-looking algebraic case can require more than two units of withholding yet receive **no sale clipping**. Example boundary witness: shed WHEAT=5, offered current WHEAT sale=5, reachable feed requirement=3, returned EOD credit=0. The formula permits sale2, requires withholding3, hits the `>2` ceiling, and leaves the original sale5 untouched.

That is a source-level counterexample to *unbounded protection*, not proof of a natural starvation event or an economic improvement from raising the cap. Existing feed-stock work also documents real false-positive reservations and terminal no-value feed, so “reserve more wheat” is not automatically good.

## What the audit classifies

`grain_debt_audit.py` consumes JSON/JSONL records containing an exact returned action and `TitanAgent.diagnostics`. It only counts executable-prefix (`market[:10]`) WHEAT sales and separates:

- `CAP_BYPASS_RETURNED_SALE`: current diagnostic reason is `feed_reservation_exceeds_two_units` while a WHEAT sale still returns;
- `GUARD_RESERVED_FEED`: active guard changed and certified the returned action;
- `FEED_ALREADY_COVERED`: guard certified no reservation was needed;
- `BINDING_GAP_RETURNED_SALE`: the completed snapshot/crop-repair binding prevented feed-stock admission;
- other certified/uncertified sales and no-sale callbacks.

A cap-bypass observation remains causally unresolved until the same trace shows a downstream missed FEED, animal escape, or CARE/output loss attributable to the missing wheat. The tool deliberately reports `REQUIRES_DOWNSTREAM_FEED_OUTCOME_CORRELATION` rather than calling the sale harmful.

## Riot / wheat-merchant handoff

For the 16-cell `r04_wheat_merchant` gate, recover or rerun native callbacks and retain at least:

- step, seat, seed and exact returned action;
- full `diagnostics.feed_stock` report;
- observed shed/carried WHEAT where available;
- later FEED success/failure, animal survival/escape and CARE/output consequences;
- cell margin delta.

Run:

```sh
python grain_debt_audit.py merchant-events.jsonl --output grain-debt-summary.json
```

Decision gate:

1. **zero `CAP_BYPASS_RETURNED_SALE` events**: this precise cap mechanism does not explain the merchant losses; do not build a cap-raising v2 from this hypothesis;
2. **positive cap-bypass, no downstream service loss**: mechanism engaged but starvation claim is falsified for those cells;
3. **positive cap-bypass + attributable downstream service loss**: authorize a separate, default-OFF repair experiment inside the existing feed-stock authority, with capacity/harvest/terminal false-positive controls and both-seat economics before any activation.

## Source custody and tests

The repository-only test authenticates the current operating-stock source Git blob `781aa90da0d85d0ba23c665e29d6087d182c085e`, requires the exact cap algebra/error, confirms the current runtime calls `_feed_stock_selected`, and confirms `TITAN-CONFIG.json` keeps `operating_stock=true`.

Isolated authored preflight (outside a full checkout) passed 12 executable tests plus one intentionally skipped repository source-custody test in both normal and optimized Python; `py_compile` passed. The checkout suite is therefore 13 tests with no expected skip when run from the repository.

Authored source SHA256: `13459c025c4dbf6a51d45ecba02806d40914632bac20233b7909dfa6d18933f7`.
Authored test SHA256: `09a1f52e45418f4137161a4b57b540ce68df9f26c131e3cc95bd0e81fb840061`.

No whole-agent game, native merchant replay, field-EV gate, runtime edit, or cap change is claimed by this packet.
