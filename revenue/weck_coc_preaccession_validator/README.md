# weck-coc-preaccession-validator-lims-01

COC-to-LIMS Pre-Accession Validator for Weck Laboratories / Agustin Pierri.

Complements the incumbent LIMS. Not a replacement. Synthetic only. Simulated/read-only adapters. No production write. No live reporting. No PHI. cash_usd=0. HOLD / BUILD-AND-VERIFY. Named-human release is mandatory.

## Official commands

```bash
python3 test_weck_coc_preaccession_validator.py
python3 revenue/weck_coc_preaccession_validator/runner.py
```

## Acceptance

| check | expected | actual |
|---|---|---|
| input COCs | 400 | 400 |
| valid | 320 | 320 |
| truth-set exceptions | 80 | 80 |
| accessions | 320 | 320 |
| holds | 80 | 80 |
| orphan tests | 0 | 0 |
| duplicate accessions | 0 | 0 |
| autonomous released | 0 | 0 |
| human released | 320 | 320 |
| COA releasable | 320 | 320 |
| EDD releasable | 320 | 320 |
| production writes | 0 | 0 |
| audit_sha256 | `75c9c6ffa53e9c6cbaa025ad63254f6134ef9f9ba239d546e758c1c15476e5f3` | same |

Ten hold codes, eight each. Every exception blocks with that exact code. Replay of the 400-COC corpus adds nothing and keeps the same audit hash. COA plus GeoTracker EDD and EPA SEDD fixture formats match the golden field digests.

## Paths

- `fixture.json` — 400 synthetic COCs
- `runner.py` — validator, accession map, exception ownership, COA/EDD, audit
- `source.json` — source kinds, method catalog, release officer
- Door: `../../weck-coc-preaccession-validator-lims.html`

Do not remint `baddl-eia-accession-release-lims-01`, `trace-sila-ml-iatf-lims-01`, `roslinct-hopkinton-paperless-qc-lims-01`, or Billings Bid 1421 / AquaTrace instrument fixtures.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
