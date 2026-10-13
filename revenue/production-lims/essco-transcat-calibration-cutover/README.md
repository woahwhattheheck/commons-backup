# Essco / Transcat Calibration Cutover — synthetic read-only shadow

Demand: `essco-transcat-calibration-cutover-lims-01`

This directory is a **synthetic, read-only reconciliation harness**. It does not connect to, write to, or release anything in Essco, EsscoNet, Transcat, MET/CAL, courier, certificate, customer, payment, or production systems. Existing systems remain authoritative.

## Acceptance contract

The frozen fixture materializes exactly **500** deterministic synthetic calibration histories from a compact deterministic generation recipe:

- **400 CLEAN** histories that must map exactly once through instrument → customer/site → service order → pickup/receipt → scope/procedure → MET/CAL run → as-found/as-left → certificate → EsscoNet document → Transcat receipt.
- **100 HOLD** histories with exact truth-set codes:
  - `DUPLICATE_ASSET_ID`: 15
  - `CUSTOMER_SITE_MISMATCH`: 15
  - `OUT_OF_SCOPE_PROCEDURE`: 14
  - `MISSING_AS_FOUND`: 14
  - `CERTIFICATE_VERSION_CONFLICT`: 14
  - `COURIER_CUSTODY_BREAK`: 14
  - `LEGACY_NEW_SYSTEM_MISMATCH`: 14

The compact fixture is the frozen source of truth; its recipe expands deterministically into all 500 full instrument histories before validation. The signed manifest binds the exact fixture bytes and the SHA-256 of the complete expanded 500-history record set.

The harness verifies:

1. frozen dataset SHA-256 and expanded-record-set SHA-256 against the manifest;
2. a deterministic content-envelope manifest signature (`sha256-content-envelope-v1`, synthetic-integrity-only);
3. exact truth-set HOLD classification;
4. clean mapping count = 1 end to end;
5. values, units, uncertainty, procedure revision, and certificate hashes survive the clean mapping unchanged;
6. no asset or certificate crosses customers;
7. repeat replay is byte-deterministic/idempotent;
8. rollback restores the exact prior shadow snapshot;
9. authoritative input state remains unchanged; and
10. automatic release is impossible — all CLEAN rows remain `QA_REQUIRED`, and only human QA may control any real release outside this harness.

## Frozen evidence

- fixture SHA-256: `daba9caee1ee285820ba381a5fa62897d4d1cb703d17f03dcfb595eb2d254568`
- expanded 500-history SHA-256: `a6b37eef17e8424f4d1bb49118a7b574bd4a07f18e5054e986daf46b9fe79765`
- manifest content-envelope signature: `ed190e587a078bad95ed8c64673d8592b5f032989d128cbb542f341a4843aaaf`
- deterministic replay outcome SHA-256: `ca3ec8193bce4b52d3ffacdbe0f71156c2ab90ee4726a8bb7b2b70024b753912`
- expected result: `400 CLEAN / 100 HOLD / 0 auto-released`

## Run

```bash
python -m unittest -v test_essco_transcat_cutover.py
```

No third-party packages are required.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
