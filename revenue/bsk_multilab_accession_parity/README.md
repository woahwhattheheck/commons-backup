# bsk-multilab-accession-parity-lims-01

Working program for **BSK Associates Analytical Division / Belinda Vega**: multi-lab accession parity across six synthetic laboratories.

The runner is the product. `python3 bsk_multilab_accession_parity.py` performs intake → facility-specific COC normalize → client/project/sample/matrix/analysis map → collection/receipt/custody/temperature/TAT/regulatory validate → deterministic six-lab route → HOLD/release. Tests prove that program. The HTML window is not the product.

Exact posted 600/480/120 fixture from Slack `#build-demand` `1788149949.285219`. No live LIMS. No production writes. No phone. No personal email.

## Boundary

Synthetic / read-only adapters (COC, LIMS, instrument, report, billing). No production writes. No automatic release. Named human required before any release. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. No outreach.

Cite, do not remint: `chemtechford-short-hold-intake-lims-01`, `sanair-asbestos-coc-router-lims-01` (PR 6859), AquaTrace B/C/F, `torrent-workorder-commissioning-lims-01`, westpak PR 6815, ddl PR 6820, highpower, wadsworth, sharp, weck, pcl, canyon. Off SKUs 1–7, fire_action, $5 tip.

## Official command

```bash
python3 bsk_multilab_accession_parity.py
python3 revenue/bsk_multilab_accession_parity/runner.py
python3 test_bsk_multilab_accession_parity.py
```

The no-arg command writes `state/journal.json` plus `receipts/{run,accessions,holds,routes,audit,replay}.json`.

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| COCs | 600 | 600 |
| valid | 480 | 480 |
| blocked | 120 | 120 |
| per lab | 100 | 100 |
| valid per lab | 80 | 80 |
| blocked per lab | 20 | 20 |
| routed to exact lab / mapped once | 480 | 480 |
| blocked with expected reason | 120 | 120 |
| cross-facility routes | 0 | 0 |
| released without named human | 0 | 0 |
| released after named human | 480 | 480 |
| replay added records | 0 | 0 |

## Golden hash

- `audit_sha256` `d2c8d0827a041291ed70aea346eb273795c0715d27ef58cbf548b1aa2e1b4a00`

Replay of the entire 600-COC corpus creates zero new records and reprints the same audit hash.

## Files

- `runner.py` — working program
- `fixture.json` — exact 600/480/120 contract
- `source.json` — leftover provenance
- `../../bsk_multilab_accession_parity.py` — thin official command
- `../../test_bsk_multilab_accession_parity.py` — fail-closed binary
- `../../bsk-multilab-accession-parity-lims.html` — window, not the product
- `../../p/bsk-multilab-accession-parity-lims-01.md` — first leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../plant-downtime-handoff.html)

