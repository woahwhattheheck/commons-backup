# pcl-scope-sla-routing-lims-01

Working program for **Packaging Compliance Labs / Ryan Ott**: post-acquisition scope-controlled sterile-package study routing + SLA evidence.

The runner is the product. `python3 revenue/pcl_scope_sla_routing/runner.py` performs intake → route → SLA clocks → HOLD/release. Tests prove that program. Receipts are evidence of that run. Not a markdown toy. Not a second SKU.

Exact posted 180/150/30 fixture. No core replacement.

## Boundary

Synthetic / read-only adapters (LIMS, instruments, scheduling, billing, delivery). No production writes. No PHI. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. Named human must act before report release. No automatic release.

Cite, do not remint: `canyon-multisite-regulated-intake-lims-01` (Adam), `made-scientific-princeton-rapid-qc-lims-01` (blob `e9469ada` PR 6720), `weck-coc-preaccession-validator-lims-01` (blob `3e837ad3`), `kincell-rtp-qc-release-bridge-lims-01` (blob `ac87ae7b`), `organabio-multisite-donor-coa-lims-01` (blob `8edbf578`), `elevatebio-pittsburgh-replication-lims-01` (blob `0f9048a9`), `roslinct-hopkinton-paperless-qc-lims-01`, leftover `p/pcl-scope-sla-routing-lims-01.md` (blob `6484c590`), SKUs 1–7, Billings Bid 1421, PR 6206.

## Official command

```bash
python3 revenue/pcl_scope_sla_routing/runner.py
python3 revenue/pcl_scope_sla_routing/runner.py --replay
python3 -m unittest test_pcl_scope_sla_routing.py
```

The no-arg command writes `state/journal.json` plus `receipts/{run,orders,blocks,clocks,audit,replay}.json`.

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| orders | 180 | 180 |
| valid | 150 | 150 |
| blocked | 30 | 30 |
| integrity / aging / distribution / product | 40 / 40 / 40 / 30 | 40 / 40 / 40 / 30 |
| incomplete / outside site scope | 15 / 15 | 15 / 15 |
| routed to exact facility / revision / sequence | 150 | 150 |
| blocked with expected reason | 30 | 30 |
| custody complete | 150 | 150 |
| 24-hour dock-to-start exact | 150 | 150 |
| 48-hour report exact | 150 | 150 |
| released without named QA | 0 | 0 |
| released after named QA | 150 | 150 |
| blocked released | 0 | 0 |
| replay changed records | 0 | 0 |

## Golden hashes

- `audit_sha256` `c01bfafdb625bca1d84091c9f595dbbb0406b3031539ee3004dd7e5daa33ae9b`

Replay of the entire 180-order corpus changes zero records and reprints the same audit hash.

## Files

- `runner.py` — working program
- `fixture.json` — exact 180/150/30 contract
- `source.json` — leftover provenance
- `contract.json` — generated HOLD / BUILD-AND-VERIFY contract
- `state/journal.json` — last official run
- `receipts/` — evidence of that run
- `../../test_pcl_scope_sla_routing.py` — proves the program
- `../../pcl-scope-sla-routing-lims.html` — login-free door
- `../../p/pcl-scope-sla-routing-lims-01.md` — first leftover receipt (do not remint)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
