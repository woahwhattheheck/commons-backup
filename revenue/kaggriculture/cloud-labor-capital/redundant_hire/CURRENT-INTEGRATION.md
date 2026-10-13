# Current TITAN redundant-hire integration

This change consumes the landed T10 `redundant_hire.py` component from PR10295 inside the existing `TitanAgent`. It does not create another producer or controller.

## Call order

For the supported frozen, non-terminal mode, the selected parent action is passed through:

1. existing frozen SELL,
2. the byte-identical redundant-hire physical certificate,
3. existing ALDER seed demand and funding.

This order matters. A removed HIRE must be visible to the later cash-coupling logic, and the certificate must inspect the final frozen-SELL market queue. Ordered and terminal-route combinations remain rejected until separately composed. The current package default is unchanged: `Features.redundant_hire` defaults to `False`. A caller can exercise the candidate with `TitanAgent(Features(redundant_hire=True))`.

The component is loaded lazily from `reference/titan-current/redundant_hire.py` only for that feature. The copied source is byte-identical to PR10295 (`4a0bf316…`, SHA-256 `a881284d…`). A no-HIRE action takes a cheap bypass. `transform_selected` never invokes the producer.

## Exact-current result

Base input is the owner-designated checkpoint archive `a8af2b83…`, source manifest `e2c25daa…`, merge `c7627b63…`. The candidate changes only `titan_runtime.py`, adds the exact component to the runtime closure, and enables the feature in the evaluation copy.

Seven focused integration methods pass. They execute the current runtime and byte-identical component with an explicit route. The component removes a trailing hire whose only remaining task duplicates an earlier retained watering, preserves inputs, and leaves the feature-disabled actor unchanged. Mode guards, no-HIRE bypass, source identity, call order and no-second-parent behavior are covered.

Eight source-fixed full games were executed on the already-used development seeds 9957001 and 9957019, both seats versus intact Arlene. Control and candidate each finish 4W/0T/0L. Every candidate cell adds exactly $5 own cash and $0 rival cash; no verdict changes. Candidate action maximum was 0.078858 seconds under its existing internal 1-second budget. A repeated diagnostic pair on 9957001/seat0 found exactly one own authored-action difference, at step 121, and zero rival-action differences. That replay is attribution, not another independent cell.

Full figures and source hashes are in `CURRENT-INTEGRATION-RESULTS.json`. The original PR10295 component evidence remains separate and credited.

## Reproduce the focused integration

From a Commons checkout containing these files:

```sh
python -B revenue/kaggriculture/cloud-labor-capital/redundant_hire/test_titan_runtime_integration.py
```

Set `TITAN_CURRENT_DIR` to exercise another extracted runtime tree. The test constructs a visible-state route fixture and does not use rival private state, future observations, episode seeds, or outcomes.

## Scope

No canonical archive, CURRENT pointer, submitted package, upload, game seed reservation, terminal/history mode, ordered consumer, opponent source, or default configuration changes here. The single canonical builder can consume this source and set the feature in a later package after the owner chooses the next checkpoint.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
