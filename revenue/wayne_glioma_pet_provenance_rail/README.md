# Wayne State R01CA309136 Glioma PET Tracer-to-Map Provenance Rail — synthetic delivery core

This package is an **internal synthetic provenance implementation** of the approved product definition. It proves lineage mechanics over synthetic identifiers and SHA-256 evidence pointers only. It is not a clinical, imaging, IND, NIH-reporting, dosing, tracer-release, or treatment-planning system.

## What the core proves

The reconciler builds a deterministic chain:

`tracer batch release-evidence pointer → synthetic dose receipt → PET/CT acquisition evidence pointer → scan-QC evidence pointer → quantitative map version → downstream handoff receipt`

The contract includes:

- strict synthetic-subject IDs and flat, bounded schemas; PII-shaped fields, nested payloads, raw images, dose quantities, diagnoses and treatment fields are refused;
- exact event idempotency: identical retries collapse with zero duplicate effect; changed content under one event ID fails closed;
- resynthesis lineage with explicit batch revisions and parent links;
- strict same-synthetic-subject and protocol association through dose, acquisition, QC, map and handoff;
- exact map-version uniqueness, supersession lineage and stale-handoff quarantine;
- missing-link and cross-subject cases quarantine before any complete-lineage count;
- order-invariant content roots and a SHA-256 integrity receipt with offline verification.

## Acceptance fixture

`acceptance.py` emits **100 complete synthetic episodes**. The positive set remains 100 even while the same fixture includes adversarial evidence:

- five cross-subject acquisition attempts;
- five map records with unavailable scan-QC evidence;
- five pairs of conflicting map records claiming the same explicit version (ten quarantined map records);
- five stale handoffs to superseded map versions;
- six exact retry replays spanning event classes.

The expected result is 100 complete synthetic subjects, 25 named quarantine rows, six replay collapses, and an identical receipt when the entire input order is reversed.

## Run

From the Commons repository root:

```bash
python -m unittest revenue.wayne_glioma_pet_provenance_rail.test_rail -v
python -O -m unittest revenue.wayne_glioma_pet_provenance_rail.test_rail -v
python -m revenue.wayne_glioma_pet_provenance_rail.acceptance --write-receipt /tmp/wayne-provenance-receipt.json
python -m revenue.wayne_glioma_pet_provenance_rail.acceptance --verify-receipt /tmp/wayne-provenance-receipt.json
```

Validation does not rely on Python `assert`, so optimized mode retains the same fail-closed behavior.

## Boundary

Use synthetic IDs and hash pointers only. This package does **not** accept PHI, names/contact data, real patient/participant identifiers, DICOM or other imaging payloads, actual administered activity/dose quantities, diagnoses, recurrence classifications, treatment recommendations, planning instructions, or clinical notes. It does not approve tracer batches or scan QC, determine protocol/IND/NIH compliance, operate scanners, write to clinical systems, select an analysis method, or authorize a downstream clinical action. All release, interpretation, scientific and clinical decisions remain outside the package.
