# Submission gate

This file intentionally separates **engineering readiness** from **competition eligibility/submission**.

## Engineering gate

- [x] normal and `python -O` unit tests pass (13/13 in the pre-publication execution runtime)
- [x] repeatability benchmark reports identical analysis hashes across >=5 runs on the 20-document public synthetic fixture
- [x] synthetic leave-one-out metrics are captured as fixture evidence only (`evidence/synthetic-20-validation.json`)
- [ ] Docker build/run is tested on an available container runtime
- [ ] resource receipt is captured on the final candidate container
- [x] public synthetic benchmark inputs/source/analysis are content-addressed in receipts
- [x] 500-document public scale fixture can be deterministically regenerated and matches its checked-in manifest hash

## Competition gate — BLOCKED until provider/account evidence exists

- [ ] pre-screening questionnaire accepted by sponsor
- [ ] participant/team eligibility verified (published rules require U.S. citizenship and age 18+ for individuals/team members)
- [ ] official GFI access granted
- [ ] official GFI stays private and inside the permitted environment
- [ ] official technical package requirements re-read immediately before submission
- [ ] measured 30-minute, CPU/RAM, replication, and validation evidence captured
- [ ] required Docker/code/schema/ETL/visualization/validation/dependency deliverables assembled
- [ ] final submission sent through sponsor portal with provider receipt
- [ ] no prize/revenue claim until sponsor adjudication/payment evidence

No checkbox in the second section may be inferred from this public codebase.
