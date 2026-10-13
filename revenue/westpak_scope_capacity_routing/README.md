# westpak-scope-capacity-routing-lims-01

Working program for **WESTPAK / Angela Barber**: scope- and capacity-aware multi-site test routing across San Jose, San Diego, and Union City under one QMS.

The runner is the product. `python3 westpak_scope_capacity_routing.py` performs intake → eligibility → site/equipment/method/sequence route → authorized transfer/custody → HOLD/release. Tests prove that program. The HTML window is not the product.

Exact posted 240/200/40 fixture from Slack `#build-demand` `1788149884.835659`. No core replacement. No live LIMS.

## Boundary

Synthetic / read-only adapters (scheduling, LIMS, instruments, QMS, transfers, reporting). No production writes. No automatic release. Named human required before any release. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. No outreach. No City contact. No bid submission. No phone. No personal email.

Cite, do not remint: `pcl-scope-sla-routing-lims-01` (blob `6484c590`), `canyon-multisite-regulated-intake-lims-01` (blob `a4ea30a9`), `savant-fe8-order-report-lims-01`, weck, kincell, organabio, elevatebio, made-scientific, roslinct. Leave `highpower-ssf-receiving-gate-lims-01` and `ddl-crosssite-method-proficiency-lims-01`. Off SKUs 1–7, AquaTrace, PR 6813, fire_action, $5 tip.

## Official command

```bash
python3 westpak_scope_capacity_routing.py
python3 revenue/westpak_scope_capacity_routing/runner.py
python3 test_westpak_scope_capacity_routing.py
```

The no-arg command writes `state/journal.json` plus `receipts/{run,jobs,holds,routes,custody,audit,replay}.json`.

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| jobs | 240 | 240 |
| valid | 200 | 200 |
| blocked | 40 | 40 |
| integrity / stability / conditioning / vibration / thermal | 40 each | 40 each |
| San Jose / San Diego / Union City | 88 / 80 / 32 | 88 / 80 / 32 |
| routed to exact site / equipment / sequence | 200 | 200 |
| blocked with expected reason | 40 | 40 |
| authorized transfers | 24 | 24 |
| unauthorized transfers executed | 0 | 0 |
| released without named human | 0 | 0 |
| released after named human | 200 | 200 |
| replay duplicate job / custody events | 0 / 0 | 0 / 0 |

## Golden hash

- `audit_sha256` `ca48bfcc283cc7f014c44cdbb469b3d3b16d553a94ccde0c1a4530ae5d55eb3b`

Replay of the entire 240-job corpus creates zero duplicate job or custody events and reprints the same audit hash.

## Files

- `runner.py` — working program
- `fixture.json` — exact 240/200/40 contract
- `source.json` — leftover provenance
- `../../westpak_scope_capacity_routing.py` — thin official command
- `../../test_westpak_scope_capacity_routing.py` — fail-closed binary
- `../../westpak-scope-capacity-routing-lims.html` — window, not the product
- `../../p/westpak-scope-capacity-routing-lims-01.md` — first leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
