# American Injectables synthetic tech-transfer lineage LIMS

This bounded product models **evidence lineage only** for the owner-assigned
`americaninj-vial-syringe-techtransfer-lims-01` build demand. It uses synthetic
records and simulated/read-only adapters. It does not make GMP, release,
sterility, quality, or compliance decisions and it performs no provider or
production-system writes.

## What it does

`americaninj_lims.py` preserves sponsor-program, formulation/method-version,
batch/material-lot, container route, result value/unit, and source identity in a
hash-bound lineage record.

The compact deterministic fixture spec expands to 120 immutable synthetic submissions:

- 90 `READY`
- 8 `DUPLICATE_PROGRAM_BATCH_ID`
- 7 `CONTAINER_LINE_MISMATCH`
- 5 `MISSING_FORMULATION_OR_METHOD_VERSION`
- 5 `IPC_FILL_FAILURE`
- 5 `STERILITY_QC_FAILURE`

The 20 intake defects never schedule a job. The 10 post-intake failures can
have a scheduled job but never stage a dossier. Only the 90 READY records stage
a dossier, and every dossier begins as `STAGED_HUMAN_REVIEW`.

## Run

```bash
python3 -B americaninj_lims.py fixtures/americaninj_120_records.json --ledger /tmp/americaninj-ledger.json
```

Re-running the same expanded fixture against the same ledger is idempotent: all 120
submission IDs are recognized as replays and the ledger bytes remain unchanged.

## Human-only release boundary

The library does not release automatically. `release_dossier(...)` requires
both an explicit `named_human=True` assertion and a non-blank named reviewer,
and it rejects HOLD records. The focused test suite exercises both allowed and
denied paths.

## Focused acceptance

```bash
PYTHONWARNINGS=error::ResourceWarning python3 -B -m unittest -v test_americaninj_lims.py
python3 -m py_compile americaninj_lims.py test_americaninj_lims.py
```

All fixtures are synthetic. No customer data, production LIMS, external model,
provider account, purchase, outreach, or autonomous dossier release is used.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
