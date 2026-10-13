# made-scientific-princeton-rapid-qc-lims-01

LabVantage Rapid-QC Scale-Up Pack for **Made Scientific Princeton / Irving Ford**.

Exact posted buyer fixture. Not a generalization. Not a core replacement.

## Boundary

Synthetic / mocked read-only. No live methods, batches, QMS, ERP, billing, or material disposition. No PHI. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. Named human must act before release. No automatic release.

Cite, do not remint: `weck-coc-preaccession-validator-lims-01` (blob `3e837ad3`), `kincell-rtp-qc-release-bridge-lims-01` (blob `ac87ae7b`), `roslinct-hopkinton-paperless-qc-lims-01`, `organabio-multisite-donor-coa-lims-01`, `elevatebio-pittsburgh-replication-lims-01`, `baddl-eia-accession-release-lims-01`, Billings Bid 1421, PR 6206.

## Fixture command

```bash
python3 revenue/made_scientific_princeton_rapid_qc/runner.py
python3 -m unittest test_made_scientific_princeton_rapid_qc.py
```

## Expected vs actual

| Check | Expected | Actual |
| --- | ---: | ---: |
| batches | 200 | 200 |
| samples | 2400 | 2400 |
| failures | 40 | 40 |
| OOS / duplicate / late / interface-failure | 10 / 10 / 10 / 10 | 10 / 10 / 10 / 10 |
| specified holds / deviations | 40 | 40 |
| valid states reconciled across four endpoints | 2360 | 2360 |
| four-endpoint reconciled (incl. holds) | 2400 | 2400 |
| duplicate samples | 0 | 0 |
| orphans | 0 | 0 |
| released without named QA | 0 | 0 |
| released after named QA | 2360 | 2360 |
| failure HOLD | 40 | 40 |
| replay changed records | 0 | 0 |

## Golden hashes

- `audit_sha256` `96550d36dbd40fd0c95c8905a19c2d64e67fc78eee61ec98525cd3f4978238d4`
- `labvantage_bundle_sha256` `ca6d714ba637eeadedda54bd89bc9eeef20f975a658301217a36c9574b1346ea`
- `mes_bundle_sha256` `6e4790a27074e43f86c1beb56fb601adaf5028916456e6f39bb33263c43834ae`
- `qms_bundle_sha256` `53627381f8aefca2c9dde702d9463d58af10521566186be414b25a2e1628a79b`
- `erp_bundle_sha256` `b0d92ccc58e74243cbd312844a344144ca11a238ce23260b077269f95a2f9104`

Replay of the entire 2,400-sample corpus changes zero records and reprints the same audit hash.

## Files

- `fixture.json` — exact 200/2400/40 contract
- `runner.py` — official binary
- `source.json` — leftover provenance
- `../../test_made_scientific_princeton_rapid_qc.py` — focused unittest
- `../../made-scientific-princeton-rapid-qc-lims.html` — login-free door
- `../../p/made-scientific-princeton-rapid-qc-lims-01.md` — leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
