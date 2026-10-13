# Dated-flow completion deadline

The existing conditional market producer now checks the shared cooperative deadline after a delegated price callback, after final town consumption and receipt construction, and after assembling the entire route/scenario vector. An overdue result remains `complete=False`, `reason="incomplete_budget"`, with no consumable rows. Direct `value_route` calls raise the existing `BudgetExceeded` instead of returning a late successful result.

This is a completion check, not hard preemption. A delegated callback can still run beyond the budget before returning. No economic formula, scenario, quantity assumption, selector, controller, game panel, or selected default changes. The original engine/quantity limits and cancellation behavior stay intact. Historical PR10043 and PR10102 results remain tied to their original source.

The source-bound PR10102 saved-input reader adopts the new flow blob explicitly. Its only change is the `DEPENDENCIES['flow']` hash; reader behavior, all other source identities, and original tests remain unchanged. Updating only the producer would leave that exact-source CLI unable to load, so the two source changes are delivered together.

## Executed evidence

Sixteen new completion-boundary methods pass. The original `dated_flow.py` blob `1070bcade1c0c3ed72f1f5ea7858621d875c130d` fails eight of those tests. Coverage includes a final price return, last scenario, final whole-vector return, final shop and town-center consumption, receipt construction, exact deadline, on-time results, disabled wall clock with unit limits retained, and cancellation propagation. Clocks are injected; no sleeps or game simulations are used.

The unchanged eighteen-method PR10102 consumer suite passes on the joined updated source, including both actual CLI paths and the retained natural DELVE226 input. Its original 29-member Library source/evidence package was hash-checked and reused. All 870 variable cash rows and all economic, coverage, route, input and scenario fields match the original complete report exactly; only the declared flow source provenance changes. The four conditional final-cash values remain MAIN/SHEEP 86,920/81,878 and 106,810/115,617. DATE over both scenarios keeps MAIN. These are conditional scheduled-volume valuations, not game scores, physical fills or probabilities.

Two direct source joins reproduce the corrected boundary. A one-unit terminal quote from the existing mechanics returns at injected clock 2 under a 1-second budget: original FLOW returns a selectable alternative, updated FLOW returns incomplete and DATE is not called. Separately, the real saved-input consumer completes its four actual route evaluations before an injected final return crosses the same clock deadline: the original calls DATE three times; the updated consumer calls it zero times and returns no partial rows. No controller action, game, fresh seed or future-state reconstruction was performed.

## Exact identities

- Updated flow blob: `ddbbe439c93082ab68b2e7e8dcfe302bbee052e7`; SHA-256 `077473fc5a1818505a9b27e42b82d9bdbb46996614e68b7c2de58716eb5f3855`.
- Updated reader blob: `794b56813daf89e06b76aaa8cbb291498e15c73c`; original `e8851922cedbf0692a02fa372599e9dbdc3798fa`.
- Unchanged HAZEL quotation blob: `00abee3c99641eb0ab1729fd80e6f9a5c783f373`.
- Unchanged DATE selector blob: `5e418aeca191e71d281f669a9fdd9f4b0730617f`.
- Reused package: `osprey-reached-quote-case.zip`, Library file `file_00000000d93881f5949750cf2733e3ad`, ZIP SHA-256 `6b04149783b95a12fd7418628eacc376944fe6b26b984283d3dbd37cb441d849`.
- Complete on-time report excluding source pins, canonical JSON SHA-256: `bd3367659abea759b617478068ae86b8bebc9ac014bfb22b7e20bc2691c9a350`.

## Reproduce

The boundary suite imports only the local component:

```sh
cd revenue/kaggriculture/cloud-capital-route-flow
python3 -B -m unittest -v test_completion_deadline
```

For the actual-source consumer check, use the original Library package's extracted `source/` as `ORIGINAL_ROOT` and the updated repository's `revenue/kaggriculture/` closure as `UPDATED_ROOT`. All other dependency blobs listed by `reached_quote_case.py` stay on their declared versions. The package's retained input/scenarios are unchanged:

```sh
python3 -B revenue/kaggriculture/cloud-capital-route-flow/check_deadline_consumer.py \
  --baseline-root "$ORIGINAL_ROOT" --updated-root "$UPDATED_ROOT" \
  --input "$PACKAGE/evidence/saved-226-row.json" \
  --scenarios "$PACKAGE/evidence/scenarios.json" \
  --output /tmp/route-flow-deadline-consumer.json
```

The checker retains both source maps, full input/scenario hashes, original and corrected outcomes, on-time report identity, and zero actor/game counts. It creates a fresh output rather than overwriting an existing receipt. There is no download or export job in either command. New checks and documentation retain Apache-2.0 attribution; peer implementations and existing evidence keep their own provenance.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
