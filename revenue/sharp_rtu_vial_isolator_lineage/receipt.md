# Sharp Sterile RTU-vial isolator lineage LIMS — TESTED

Demand: `sharp-rtu-vial-isolator-lineage-lims-01`
Buyer: James Hamilton / Sharp Sterile Manufacturing

Binary: `python3 test_sharp_rtu_vial_isolator_lineage.py` → 10/10 OK
CLI: `python3 sharp_rtu_vial_isolator_lineage.py`

- 120 synthetic records
- 90 READY staged batch evidence packs
- 30 HOLD: 8 DUPLICATE_COMPONENT_BATCH, 7 FORMAT_LINE_MISMATCH, 5 MISSING_METHOD_VERSION, 5 WEIGHT_SLOT_CONFLICT, 5 QC_STERILITY_FAIL
- 100 jobs; intake holds scheduled 0
- held records staged 0 / released 0
- cycle / weight / result / unit / source hashes match
- replay added 0 records
- released_packs = 0 without named approval
- named-human-release proof: `RELEASER` + `james-hamilton-qa` releases a READY pack; SYSTEM / unnamed / held records are denied
- fixture_sha256 `2d8fb72fa37908bcb7187d21f1ec1082e02de4f950c7b8a5772afd958ca80b84`
- audit_sha256 `d248f9b13cdc38c76d1be2e4d8c2d753a77aa1d3f8efc7fcf6bc30cf7e0c95a8`
- evidence_digest `d255a5866b7d1a34c697a2f653d56e9c95fc98a271e2da5f7290c623e324ca01`

AquaTrace HOLD / BUILD-AND-VERIFY. Synthetic/read-only adapters. No GMP/compliance/clinical/public-health decision. PRE-SALE TRANSPORT: NONE. cash_usd=0.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../titanmcp.html). Cite Latch Pad KEEP.
