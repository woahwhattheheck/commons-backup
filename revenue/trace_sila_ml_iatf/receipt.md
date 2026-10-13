# trace-sila-ml-iatf-lims-01 receipt

State: TESTED
Binary: `python3 test_trace_sila_ml_iatf.py` → 9/9 OK
CLI: `python3 trace_sila_ml_iatf.py` → ok true, failures []

| check | value |
|---|---|
| fixture | SILA-ML-01 |
| inbound analytics | 13 (12 unique + 1 duplicate) |
| canonical results | 12 |
| duplicate log | 1 (B001-A01) |
| dossiers | 4 |
| B001 | REVIEW_READY |
| B002 | HOLD_UNIT_MISMATCH |
| B003 | HOLD_SPEC_OOS |
| B004 | HOLD_GENEALOGY_GAP |
| released dossiers | 0 |
| replay added results | 0 |
| adapter writes | denied |
| manifest_sha256 | eaac92bc73e0aaa2d84b29fccf05221c090ce77c00d7324eb0d9f8536fe739b6 |
| audit_sha256 | 8a436b41eca5fb2737206eea2f0c36c3179b187e21a1ad81aa87767bcde32a7a |

Interfaces simulated read-only. No production writes, recipes, or real thresholds. Human disposition mandatory. AquaTrace HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
