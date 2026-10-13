# sanair-asbestos-coc-router-lims-01

Rapid-TAT Asbestos COC Router for SanAir Technologies / Sandra C. Sobrino.

Routes signed synthetic asbestos COCs across Richmond, Cincinnati, and Boston by lab/method capability. TAT clocks start from fixture receipt. Recipient permissions must match the COC. Written email/fax amendments keep provenance. Release is named-human only.

Adapters stay synthetic and read-only. No live sample or test action. No production write. No outreach. cash_usd=0. HOLD / BUILD-AND-VERIFY.

## Official commands

```bash
python3 sanair_asbestos_coc_router.py
python3 test_sanair_asbestos_coc_router.py
```

## Acceptance

| check | expected |
|---|---|
| input COCs | 360 = 300 valid + 60 exceptions |
| routed | 300, one per valid, designated lab once, field parity |
| labs | Richmond 100 / Cincinnati 100 / Boston 100 |
| HOLD | 60, fifteen each of four exact codes |
| TAT clocks | fixture receipt start, not collection |
| permissions | match the COC |
| replay | adds 0 routes / 0 holds; same audit hash |
| autonomous released | 0 |
| human released | 300 after SYN-SANAIR-RELEASE-OFFICER |
| audit_sha256 | `7e90246b6ab1cfaf8b5fac41669f968fa3cd2c8ed8c27381835387ea407483cf` |

Hold codes: `HOLD_MISSING_SIGNATURE`, `HOLD_DUPLICATE_SAMPLE_ID`, `HOLD_INVALID_LAB_METHOD`, `HOLD_TAT_CUTOFF`.

## Paths

- `fixture.json` — 360 frozen synthetic COCs
- `runner.py` — router, TAT clock, permissions, lineage, human release
- `source.json` — lab/method/TAT catalogs
- Door: `../../sanair-asbestos-coc-router-lims.html`

Cite, do not remint: wadsworth-five-site-consolidation-lims-01, highpower-ssf-receiving-gate-lims-01, westpak-scope-capacity-routing-lims-01, ddl-crosssite-method-proficiency-lims-01, sharp-rtu-vial-isolator-lineage-lims-01, canyon, pcl, organabio, billings.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
