# MSU Denver beverage QA/QC reconciliation

Demand ID: `msudenver-beverage-qaqc-lims-01`

This is a synthetic/read-only reference adapter for request-to-accession reconciliation across a small beverage QA/QC catalog. It does not connect to a production LIMS, make a compliance decision, release a real report, contact a customer, or write to any provider.

## Frozen acceptance

The bundled fixture recipe expands deterministically to exactly 100 synthetic requests:

- 80 `READY`
- 8 `MISSING_SAMPLE_TEST_IDENTITY`
- 5 `DUPLICATE_CLIENT_ID`
- 4 `INCOMPATIBLE_PACKAGE_TEST_SELECTION`
- 3 `QC_CONTROL_FAIL`

The 80 READY rows create exactly 80 accessions, 180 catalog jobs, and 80 `STAGED_HUMAN_REVIEW` reports. All 20 HOLD rows create no accession, job, or report. First-pass processing creates exactly 100 events. Replaying all 100 rows against the same ledger is idempotent and adds nothing.

Catalog jobs copy the fixture's golden value, unit, rounding, and method-version fields only after validating them against the declared package metadata. QC-control failures are held before accession/report creation.

## Identity and replay

Each first-seen `request_id` is bound to the canonical SHA-256 of its complete synthetic payload. An exact replay returns `IDEMPOTENT`. A changed payload under an existing request ID raises `ReplayPayloadMismatch` before any mutation.

Unique client request IDs are also reserved on first processing; a later different request that reuses a prior client ID is held as `DUPLICATE_CLIENT_ID`.

## Human release boundary

Reports remain stored as `STAGED_HUMAN_REVIEW` with `sent=false`. `release_report_copy()` accepts only an explicit two-token-or-longer named-human label after normalized alphabetic tokenization and rejects automation/service tokens such as system, AI, bot, agent, automation, robot, and service. It returns a copy labeled `RELEASED_BY_NAMED_HUMAN_COPY`; it never mutates the stored report or sends anything.

## Run

```bash
cd revenue/production-lims/msudenver-beverage-qaqc
python -m py_compile beverage_qaqc.py test_beverage_qaqc.py
python test_beverage_qaqc.py -v
python beverage_qaqc.py --fixture fixtures/msudenver_100_requests.json --manifest fixtures/manifest.json
```

Expected CLI summary includes `READY=80`, the exact four HOLD counts above, `accessions=80`, `jobs=180`, `reports=80`, `holds=20`, `events=100`, `replay_idempotent=100`, and all external-write counters equal to zero.

## Boundary

This implementation is a fresh successor rebuild after the earlier frozen-but-unpublished byte bundle was lost from repository custody. Its hashes are intentionally new; no claim is made that these bytes reproduce the earlier unpublished Git blobs. Synthetic fixture truth is the acceptance surface.
