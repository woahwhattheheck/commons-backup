# preinnewhof-pfas-fieldblank-gate-lims-01 receipt

State: TESTED
Binary: `python3 test_preinnewhof_pfas_fieldblank_gate.py` → 10/10 OK
CLI: `python3 preinnewhof_pfas_fieldblank_gate.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 150 |
| valid accessions | 120 once, method + field-blank parentage |
| Grand Rapids / Holland / Muskegon | 40 / 40 / 40 |
| held | 30 |
| HOLD_MISSING_FIELD_BLANK | 5 |
| HOLD_BOTTLE_COC_MISMATCH | 5 |
| HOLD_DUPLICATE_SAMPLE_ID | 5 |
| HOLD_INVALID_RECEIPT_WINDOW | 5 |
| HOLD_WRONG_PRESERVATION | 5 |
| HOLD_UNSUPPORTED_METHOD_LOCATION | 5 |
| held worksheets / portal results | 0 / 0 |
| hashes reconciled | 120 |
| reports released | 0 |
| replay added accessions | 0 |
| replay added holds | 0 |
| fixture_sha256 | a6a04faf00a6f2be1ab0bd4ecf55031cc7a6c5e0089199019151f9ec959864a6 |
| manifest_sha256 | d59f935752025c3a82e124151294daaa7178b537d3fe060f0565a0b79459bb2b |

Simulated adapters. No autonomous certification or release. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
