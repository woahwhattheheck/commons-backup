# qlabs-qconnect-cutover-verification-lims-01 receipt

State: TESTED
Binary: `python3 test_qlabs_qconnect_cutover.py` → 9/9 OK
CLI: `python3 revenue/qlabs_qconnect_cutover/runner.py` → ok true, failures []

| check | value |
|---|---|
| input rows | 240 |
| accessioned once | 200 |
| held | 40 |
| hold codes | 8 OBSOLETE_CODE, 8 WRONG_DEPARTMENT, 8 MISSING_FIELD, 3 INVALID_ACCOUNT, 3 INVALID_USER, 2 SHARED_CREDENTIAL, 8 TIMEOUT_RETRY |
| obsolete in testing | 0 |
| shared-credential accessions | 0 |
| replay added accessions | 0 |
| provenance | complete |
| audit_sha256 | c551c9a1d98fd421823119b1d52f2df5f6f4e40cc9fd9427960d8497f3ac8c0b |
| manifest_sha256 | d484e7c953fb8aa2acff16044596f39684b44ba5d84bfb83dc6b68b64ba37ef5 |

Interfaces simulated. Read-only shadowing. No production writes. No outreach. No automatic release. Named human QA (`SYN-QA-OFFICER`) releases the build. HOLD / BUILD-AND-VERIFY. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
