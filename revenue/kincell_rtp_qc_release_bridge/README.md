# kincell-rtp-qc-release-bridge-lims-01

Commercial QC-release LIMS bridge for **Kincell Bio RTP / Melodie Bryce**.

Exact posted buyer fixture. Not a generalization. Not an incumbent replacement.

## Boundary

Simulated / de-identified only. No live QMS, ERP, or LIMS. No production writes. No PHI. `cash_usd=0`. STATE remains **HOLD / BUILD-AND-VERIFY**. Named QA must act before release. No automatic release.

Cite, do not remint: `weck-coc-preaccession-validator-lims-01`, `roslinct-hopkinton-paperless-qc-lims-01`, `baddl-eia-accession-release-lims-01`, `trace-sila-ml-iatf-lims-01`, Billings Bid 1421.

## Fixture command

```bash
python3 revenue/kincell_rtp_qc_release_bridge/runner.py
python3 -m unittest test_kincell_rtp_qc_release_bridge.py
```

## Expected counts

| Check | Expected |
| --- | ---: |
| samples | 300 |
| batches | 30 |
| exceptions | 30 |
| qms_events | 30 |
| duplicate samples / results | 0 |
| truth_set_matches | 300 |
| released without named QA | 0 |
| released after named QA | 270 |
| exception HOLD | 30 |
| replay changed records | 0 |

## Golden hashes

- `audit_sha256` `3771349f17f020256269857d865601789f3f41271df4fa51a90ce73231609e26`
- `erp_bundle_sha256` `75e17c264aeb1a0e800ad686871f61d261c878e5fd027cfd5ea9681b19adc615`
- `qms_bundle_sha256` `8e5fd0345773ecf87377d6429f9c0e2c6c19548d03c396385bac582d8ca4f3fc`

Repeated import changes zero records and reprints the same audit hash.

## Files

- `fixture.json` — exact 300/30 contract
- `runner.py` — official binary
- `source.json` — leftover provenance
- `../../test_kincell_rtp_qc_release_bridge.py` — focused unittest
- `../../kincell-rtp-qc-release-bridge-lims.html` — login-free door
- `../../p/kincell-rtp-qc-release-bridge-lims-01.md` — leftover receipt

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
