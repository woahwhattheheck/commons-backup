# FLORA KAG-PRODUCTION

This lane integrates an observable-state production system into the exact
selected KAG-COMPOSE dispatcher. It adds the official strawberry lifecycle,
fertilizer retention/pickup/application, finite-horizon crop valuation, timed
land purchases, and labor sizing. Visible unlocked shops affect crop value;
no hidden episode seed, opponent identity, replay fingerprint, network, or
external state is used.

`build.py` refuses drift from the selected KAG-COMPOSE SHA-256 and emits the
standalone `candidate.py`. Its production-event projection is frozen from
ROWAN's landed `cloud-frontier-trace/events.py` contract (blob
`48b3c0df949e13bf4c63ee86f5d5b3a58ec00aec`). Market commitments use a
single sequential cash ledger: seeds are protected first, then only the exact
feed deficit is bought at per-unit repriced cost. Crop capacity is no longer a
fixed 16: it expands up to 24 only when observable worker effect capacity can
cover installed animals, crop service, and pending placements.

## Current evidence

- Same seed as the merged checkpoint: **+21,501.5** versus KAG-COMPOSE,
  with the Kaito and Igor gaps reduced to **-22,541.5** and **-21,259.0**.
- Two additional development seeds: 4/4 wins over the merged checkpoint,
  mean margin **+8,120.0**.
- Those additional seeds still lost 0/4 to each strong public reference;
  Kaito mean margin **-21,415.5**, Igor **-27,495.75**.
- All 20 selected-policy games completed without agent failures and each
  report's first game replayed with identical scores and trace.
- Dynamic crop capacity then beat the shipped checkpoint by **+5,315.75** mean
  over four paired games on development seeds `9200131` and `9200157`.
- Across those seeds it improved the worst pinned-reference mean gap from
  **-45,830.5** to **-36,309.5**. Igor improved to **-19,282.75**, while
  Kaito worsened from **-21,008.25** to **-36,309.5**.

The public references remain materially stronger. These are official-
interpreter development results, not hosted Kaggle scores or evidence of
leaderboard leadership. The initially corrected feed-before-seed ledger was
rejected after losing both same-seed seats to the merged policy by 14,139 mean;
its bytes are not shipped.
An independently tested labor-throttling arm also lost both paired games by
7,888 mean and is excluded. Dynamic crop capacity is the only promoted arm.

Run the focused source contract:

```bash
python -B revenue/kaggriculture/cloud-production/test_production.py
```

The official interpreter remains pinned to
`28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c`. Development compute was run in
the cloud workspace only. No competition submission or account mutation was
performed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
