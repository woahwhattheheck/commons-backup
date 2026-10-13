# sgspsi-high-throughput-thermal-rheology-lineage-lims-01 receipt

State: TESTED
Binary: `python3 test_sgspsi_thermal_rheology_lineage.py`
CLI: `python3 sgspsi_thermal_rheology_lineage.py`

| check | expected | actual |
|---|---|---|
| input rows | 120 | 120 |
| READY | 90 | 90 |
| HOLD | 30 | 30 |
| HOLD codes | 8 MISSING_LINKAGE + 6 DUPLICATE_CONTAINER + 6 METHOD_INSTRUMENT_MISMATCH + 5 SLOT_COLLISION + 5 QC_FAILURE | exact |
| reserved slots occupied | 90, one sample each | exact |
| released reports (autonomous) | 0 | 0 |
| staged reports | 90 pending named APPROVER | 90 |
| replay added records | 0 | 0 |
| fixture_sha256 | 3914c61ed2dfe51c4601c773cc03816e53c13a12cbc9815ec2ddec2e9ac4016b | match |
| audit_sha256 | 22c85bf6a5658eb4b2460bca3d07a23e3756590a55cfc336348d4a4cc631565d | match |
| lineage_sha256 | 87f0ed13ee7ab7cbbdb30ef9daec7505c61c22ceb57611efb1f0f6be5c2f9e26 | match |
| report_digest | 3341fe765f072d291c9c3422d40651edbb7f2041839d3e103e3b5880de439738 | match |

Buyer: Kyle Copeland / SGS Polymer Solutions. DSC-250 / HR-20 lineage lane. Interfaces simulated. No production write, outreach, or automatic release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
