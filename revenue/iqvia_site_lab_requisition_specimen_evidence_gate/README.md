# IQVIA Site Lab requisition → specimen declared-evidence gate

Operation: `IQVIA-SPECIMEN-SOURCE-PROVENANCE-ZBFR8V5-20260913`  
Owner/finalizer: Z-BesselForge-914032-R8V5 (`ZBF-R8V5`) / GPT-5.6 Sol  
Tracking: Commons #14002; post-merge fix-forward for #13987

This package is a **synthetic/deidentified, read-only evidence carrier** for the IQVIA Laboratories Site Lab Navigator / e-Requisition operating seam. Version 2 closes the v1 provenance defect: a candidate packet can no longer provide both an operational value and a separate caller-selected “expected/allowed” value, attach arbitrary 64-hex source labels, and grade itself READY.

## V2 evidence contract

Each packet has only `schema`, `packet_id`, `sources`, and `source_refs`.

`sources` contains eight exact, closed source-record projections:

- `protocol` — protocol + expected visit;
- `requisition` — protocol/visit/version, collection window, required sample type;
- `kit` — lot, expiry, allowed transport temperature;
- `collection` — collection time, sample type, used kit lot, requisition generation;
- `courier` — scan, observed temperature, carried kit lot;
- `accession` — accession, sample type, method, requisition generation;
- `method` — method identity + allowed sample types;
- `queries` — requisition generation + bounded query-resolution records.

Before evaluating any operational relationship, the gate canonicalizes **each exact declared source record**, recomputes its SHA-256, and requires exact equality with the corresponding `source_refs` entry. Semantic mutation under a stale hash and cross-source hash transplant therefore fail before READY/HOLD evaluation.

The refs are mechanically labeled:

`CANONICAL_DECLARED_SOURCE_RECORD_SHA256`

They are **not claimed to be hashes of raw IQVIA/provider documents**, and this package does not authenticate the external origin of a declared source record. `source_authenticity_verified` is always `false`. A production pilot would need a separate credential-owning acquisition/attestation boundary.

## Output

Output is only:

- `EVIDENCE_CONSISTENT_FOR_HUMAN_REVIEW` — the exact declared source generation is internally consistent under this bounded contract;
- `HOLD` — one or more stable evidence conflicts require human resolution.

Current hold families:

1. `PROTOCOL_VISIT_MISMATCH`
2. `REQUISITION_GENERATION_MISMATCH`
3. `KIT_INVALID_FOR_COLLECTION`
4. `COLLECTION_WINDOW_BREACH`
5. `COURIER_EVIDENCE_INVALID`
6. `ACCESSION_METHOD_INCOMPATIBLE`
7. `UNRESOLVED_QUERY`

A positive result is deliberately **not** called specimen-ready, clinically ready, release-ready, authenticated, or accepted. Human site/lab staff own every consequential decision.

## Frozen synthetic acceptance

```bash
python -m revenue.iqvia_site_lab_requisition_specimen_evidence_gate.acceptance
python -m unittest revenue.iqvia_site_lab_requisition_specimen_evidence_gate.test_gate
python -O -m unittest revenue.iqvia_site_lab_requisition_specimen_evidence_gate.test_gate
```

The frozen generator creates 180 packets: 145 evidence-consistent and 35 HOLD, exactly five in each of seven hold families, with byte-identical JSON/CSV/manifest replay and exact full-report recompilation.

Hostiles additionally prove stale-hash semantic mutation, cross-source hash transplant, deprecated self-grading fields, requisition-generation drift, kit/courier/method/query source drift, unknown source fields, non-finite values, result tamper, and the all-false source-authenticity ceiling.

## Authority boundary

`AUTHORITY = EVIDENCE_ONLY_HUMAN_SITE_LAB_RESOLUTION`

No participant eligibility, patient instruction, specimen disposition, result interpretation, database lock, clinical/regulatory decision, provider credential/data access, production mutation, buyer acceptance, payment, or revenue authority is created.

## Commercial boundary

A landed synthetic carrier may support a separately hard-deduped **paid nonproduction pilot inquiry** through a verified business route. This code does not contact IQVIA, infer interest, or prove that IQVIA uses or accepts the carrier.
