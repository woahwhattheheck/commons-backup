# torrent-workorder-commissioning-lims-01

New-Facility Work-Order Commissioning Harness for Torrent Laboratory / Mukesh Jani.

Current Watson COC normalization, work-order creation, TAT/EDD/matrix/container parity, cooler/custody/receipt gates, old/current facility-ID mapping, exception quarantine, and named-human release.

Complements the incumbent LIMS. Not a replacement. Synthetic only. Simulated/read-only adapters. No production write. No live LIMS. No outreach. No phone numbers or personal emails. cash_usd=0. HOLD / BUILD-AND-VERIFY. Named-human release is mandatory.

## Official commands

```bash
python3 torrent_workorder_commissioning.py
python3 test_torrent_workorder_commissioning.py
```

## Acceptance

| check | expected | actual |
|---|---|---|
| input Watson COCs | 500 | 500 |
| valid | 400 | 400 |
| predefined defects | 100 | 100 |
| work orders | 400 | 400 |
| quarantines | 100 | 100 |
| replay added work orders | 0 | 0 |
| replay added quarantines | 0 | 0 |
| autonomous released | 0 | 0 |
| human released | 400 | 400 |
| production writes | 0 | 0 |
| audit_sha256 | `7d89b0bfe74dbc142d1717c36e292b08ace0c3587ce7b5b1581bfb584701c446` | same |

Ten quarantine codes, ten each. Every defect blocks with that exact code. Old and current facility identifiers normalize to `SYN-TOR-CUR-MILPITAS`. Replay of the 500-COC corpus adds nothing and keeps the same audit hash.

## Paths

- `fixture.json` — 500 synthetic Watson-form COCs (written by the official command)
- official command `../../torrent_workorder_commissioning.py` — the working program
- Door: `../../torrent-workorder-commissioning-lims.html` (window, not the product)

Cite, do not remint: bsk-multilab-accession-parity-lims-01, chemtechford-short-hold-intake-lims-01, sanair-asbestos-coc-router-lims-01, aquatrace work-order B/F/C, westpak, ddl, highpower, wadsworth, sharp, weck, pcl, canyon.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
