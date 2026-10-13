# Clinical-model provenance & accreditation-scope evidence gate

This package is an offline, deterministic acceptance core for a **synthetic / non-production** study-evidence fixture. It binds an opaque sponsor/study, model line and passage, declared use, site, assay/version, declared accreditation scope, sample custody/QC state, and artifact checksum into a content-addressed `STUDY_READY` or `HOLD` decision.

`STUDY_READY` has a deliberately narrow meaning: the supplied machine evidence is complete and mutually consistent under the declared fixture contract. It is **not** Crown Bioscience approval; CAP/CLIA certification or compliance; sponsor, scientist, clinician, QA/QP, or regulator approval; assay validity or scientific efficacy; patient eligibility; diagnosis/treatment advice; sample or clinical release authority; or authorization to mutate any production system.

## Fail-closed behavior

The gate rejects unknown fields, dict/list subclasses, malformed identifiers/times/digests, and person/medical keys. It holds mismatched study/model/passage lineage, out-of-range passage or use, site/scope mismatch, assay/version outside the declared scope, stale scope dates, QC states other than `released_for_study`, and placeholder all-zero artifact digests. Event IDs are exactly-once: identical retries collapse; a changed payload under the same event ID becomes an audited `EVENT_ID_CHANGED_PAYLOAD` hold.

The canonical manifest is sorted independently of arrival order, includes every non-replay decision, and carries a SHA-256 digest. Decision and manifest verifiers are offline and perform no network I/O.

## Deterministic acceptance

```bash
python -m revenue.crownbio_clinical_model_provenance_gate.acceptance
python -m unittest revenue.crownbio_clinical_model_provenance_gate.test_gate -v
python -O -m unittest revenue.crownbio_clinical_model_provenance_gate.test_gate -v
```

The acceptance fixture has exactly 150 packets: **126 `STUDY_READY` and 24 deliberate `HOLD`**. The 24 holds are six groups of four: model-lineage mismatch, study-lineage mismatch, assay/version outside declared scope, stale accreditation-scope date, QC not ready, and all-zero artifact-digest sentinel. It also proves ten exact retries collapse with no new rows, while one changed-payload reuse of an event ID creates an explicit audited hold.

No patient/PHI payloads, buyer credentials, production APIs, payment/provider actions, customer contact, deployment, certification, contract, buyer acceptance, or recognized revenue are part of this package.
