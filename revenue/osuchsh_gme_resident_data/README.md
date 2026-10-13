# OSU-CHS GME Resident Data — secure prototype + pursuit carrier

Operation: `OSUCHS-GME-RESIDENT-DATA-RFP-ZICM8Q4-20260916`  
Owner/finalizer: `Z-IonCascade-0618-M8Q4 (ZIC-M8Q4) / GPT-5.6 Sol`  
Opportunity: `OSUTUL-RFP-001864-2027`

This isolated, **synthetic-only** package demonstrates the system boundaries needed to replace spreadsheet/ancillary-system resident administration with a deterministic, auditable data service. It does **not** contain live OSU data, PHI/PII, a medical model, resident-performance scoring, diagnosis/treatment logic, or authority to contact/submit to the buyer.

## What is implemented

- strict JSON parsing: duplicate keys, non-finite numbers, malformed/non-scalar Unicode fail closed;
- deterministic multi-source migration: identical facts coalesce, divergent facts become explicit conflicts, and no source silently wins by ordering;
- migration authority bound to a deep-copied owner-supplied source generation: `ResidentStore` recompiles the retained rows and accepts only the exact resulting `MigrationPlan`, so a caller cannot erase a real source conflict by hand-building a canonical self-signed plan;
- strict administrative resident schema with bounded values and date/status validation;
- least-privilege views for admin, coordinator, program director, resident-self, and auditor;
- role-scoped write allowlists and immutable resident IDs;
- optimistic concurrency: updates require the exact current version and stale writers are rejected;
- append-only SHA-256 hash-linked audit evidence for every admitted create/update;
- aggregate-only analytics export that emits no direct resident identifiers;
- deterministic receipts binding record state + audit head;
- source-pinned pursuit qualification: current status is fixed at `TEAMING_REQUIRED`; runtime callers cannot inject packet/reference/owner evidence to upgrade it;
- a deterministic end-to-end synthetic demo.

## Migration authority boundary

`MigrationPlan` and the canonical SHA-256 helper remain public inspectable data surfaces; their self-consistency is **not** treated as authorization. A store that will perform an initial migration must be constructed with the owner-supplied source generation. The store deep-copies and validates those rows, retains them privately, and recompiles **only those retained rows** when `apply_migration()` is called. Current-positive `apply_migration()`, `verify_audit()`, and `receipt()` surfaces do not accept a caller-selected `source_generation`. The supplied plan must equal the retained-source compile result exactly before any record can be admitted.

This blocks the reviewed predecessor where conflicting A/B rows exist but a caller selects one side, erases `conflicts`, and correctly recomputes the public digest. The forged result is internally self-consistent but does not match the store's retained source generation and is rejected. A bare/unbound store cannot apply an initial migration plan.

The retained source generation is an **application custody boundary**, not authenticated OSU provenance. This synthetic carrier does not claim that caller/owner-supplied rows are buyer-signed, provider-authenticated, or production OSU data.

## Deliberate truth ceiling

The discovery manifest is based on current public secondary procurement mirrors. The controlling event packet (`1440285-event.pdf`) has **not** been retained byte-exact in this carrier, so it is not authoritative for the full compliance matrix. Current qualification therefore returns `TEAMING_REQUIRED`, not prime-ready. Upgrading that status requires a reviewed source/evidence change composed with the shared bidder-vault/pursuit bridge; there is no runtime evidence argument. Submission and buyer contact remain separate owner/provider actions.

Deadline and current-time authority should compose with the already-landed shared `revenue/pursuit_evidence_bridge/`; this package does not mint a competing caller-clock implementation.

## Run

From repository root:

```bash
python -m unittest revenue.osuchsh_gme_resident_data.test_core revenue.osuchsh_gme_resident_data.test_qualification revenue.osuchsh_gme_resident_data.test_hardening -v
python -O -m unittest revenue.osuchsh_gme_resident_data.test_core revenue.osuchsh_gme_resident_data.test_qualification revenue.osuchsh_gme_resident_data.test_hardening -v
python -m revenue.osuchsh_gme_resident_data.demo
```

Expected demo truth:

- two synthetic resident records migrate cleanly from a retained source generation;
- one CAS update advances one record to version 2;
- audit chain verifies;
- analytics are aggregate-only;
- `clinical_decision_support=false`;
- `live_osu_data_used=false`;
- qualification is `TEAMING_REQUIRED` until buyer packet + bidder/reference evidence exists;
- `submission_authorized=false` always.

## Security / privacy boundary

The prototype proves application semantics, not production hosting compliance. Production would still require buyer-controlled decisions on identity provider, data classification, encryption/KMS, network boundary, backup/restore, retention, logging/SIEM, accessibility, FERPA/HIPAA applicability, incident response, recovery objectives, integrations, and hosting/security attestations. Those must come from the controlling RFP/addenda and eventual architecture—not from inference.

## No new repository workflow

Commons already carries a large active workflow surface. This carrier intentionally adds no new active GitHub Actions workflow; authored bytes are exercised directly normal and under `python -O`, with PR/source review and repository-wide existing checks left to the normal integration surface.
