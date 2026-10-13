# R04 SELL queue-order census

Research-only recovery of the dangling `r04_sell_queue_order` lane.

The official engine does not process the market as one unordered batch. It truncates each player's market queue to `maxMarketOrdersPerTurn`, walks queue indices in order, and at one index quotes both players against the same pre-commit inventory before committing. It completes that order's per-unit loop before advancing to the next queue index. Therefore the same product sold at different queue indices across the two players is structurally non-simultaneous: an earlier-index sale can mutate that product's market inventory before the later-index seller receives a quote.

That is a source theorem, not an uplift theorem. Whether an authored index mismatch matters in a real game still depends on shed inventory, the realized market inventory and rounding/floor regime, the opponent's actual queue, and prior state. No queue permutation is safe merely because the census finds an exposure.

`r04_sell_queue_order.py` authenticates exact official sources before doing any census:

- engine Git blob `3c202c7ee921da239356789e266b694635103fc4`;
- engine-spec Git blob `b354d06b742fe48402513792253f1a5c29366b20` and standard `maxMarketOrdersPerTurn=10`;
- canonical 13×719 tape bank Git blob `a43289b9cc5e34a2481fddf652762a7d92f427ef`;
- canonical R04 router Git blob `a3e2fe87c717d128e43c9b65bae2265f40d1d76d`.

It reconstructs the live R04 route splice exactly (plan 0 opening, selected plan midgame, plan 2 endgame), scans all 13 routes for callbacks containing at least two executable SELL slots, and scans all 13×13 fixed-route pairings for shared products authored at different SELL queue indices.

The output deliberately separates two facts:

- `authored_reorderable_steps`: one route callback has at least two executable SELL slots, so a SELL-slot permutation exists syntactically;
- `cross_route_index_exposures`: two fixed routes sell the same product at different executable queue indices on the same callback, so quote timing is structurally exposed.

A structural exposure can exist even when neither side has two SELL slots (for example a HIRE before a single SELL). Such a row is evidence about queue-index timing but is **not** repairable by merely permuting SELL slots. The per-mismatch flags make that distinction explicit.

## Run

From the repository root:

```bash
V4=revenue/kaggriculture/cloud-execution-lab/candidates/v4
python -B "$V4/research/r04-sell-queue-order/r04_sell_queue_order.py" \
  --output /tmp/titan-v4-r04-sell-queue-order.json
python -B -m unittest -v \
  "$V4/research/r04-sell-queue-order/test_r04_sell_queue_order.py"
python -O -B -m unittest -v \
  "$V4/research/r04-sell-queue-order/test_r04_sell_queue_order.py"
python -m py_compile \
  "$V4/research/r04-sell-queue-order/r04_sell_queue_order.py" \
  "$V4/research/r04-sell-queue-order/test_r04_sell_queue_order.py"
```

The mounted gate should report exact source blobs plus the three totals: authored reorderable steps, cross-route index exposures, and exposure mismatches. Zeroes are a valid useful result and close the lane as negative evidence. Nonzero results authorize only a replay target: pair the exact callback/plan cells under current-native execution and compare complete economic postimages before proposing any queue transformation.

## Not claimed

- shed inventory sufficiency;
- strict price improvement at realized inventory;
- opponent queue prediction;
- economic uplift;
- safe SELL reorder;
- runtime activation/default promotion;
- composer/COMPOSITION/INTEGRATION/archive/Kaggle mutation.
